#!/usr/bin/env python3
"""migrate_material_uoms.py — bangun field `uoms` dari data satuan lama.

APA YANG DILAKUKAN
------------------
Untuk setiap dokumen `rahaza_materials`, membangun daftar UOM baru dari field
lama (`unit` + `pack_unit`/`pack_size`) lalu menuliskannya bersama cermin field
lama agar keduanya konsisten:

    uoms, base_uom, purchase_uom, issue_uom, display_uom
    + cermin: unit, pack_unit, pack_size, display_in_packs

APA YANG **TIDAK** DILAKUKAN (penting)
--------------------------------------
* TIDAK mengubah satuan dasar material  (INV-UOM-5)
* TIDAK menyentuh `rahaza_material_stock` / `rahaza_stock_ledger`
* TIDAK mengubah `unit_cost` maupun `min_stock`
* TIDAK menghapus field lama

Artinya angka stok, HPP, dan seluruh laporan hilir **tidak bergeser sedikit pun**.
Perubahan satuan dasar hanya boleh lewat aksi khusus "Ubah Satuan Dasar" (F5).

Idempotent: dijalankan berkali-kali menghasilkan dokumen yang sama.

Pemakaian
---------
    python3 scripts/migrate_material_uoms.py            # pratinjau (dry-run)
    python3 scripts/migrate_material_uoms.py --execute  # tulis ke DB
    python3 scripts/migrate_material_uoms.py --execute --type accessory
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core import uom as U  # noqa: E402

FIELDS = ("uoms", "base_uom", "purchase_uom", "issue_uom", "display_uom",
          "unit", "pack_unit", "pack_size", "display_in_packs")


def build_patch(m: dict) -> dict:
    """Susun potongan `$set` untuk satu material — tanpa mengubah satuan dasar."""
    base = U.base_uom_of(m)
    rows = U.resolve_uoms(m)
    patch: dict = {"uoms": rows}
    patch.update(U.mirror_legacy(rows, base))

    # `display_in_packs` yang sudah diset manual tidak boleh dipaksa berubah
    if "display_in_packs" in m:
        patch["display_in_packs"] = bool(m["display_in_packs"])

    codes = {r["code"] for r in rows}
    patch["purchase_uom"] = U.purchase_uom_of(m) if U.purchase_uom_of(m) in codes else base
    patch["issue_uom"] = U.issue_uom_of(m) if U.issue_uom_of(m) in codes else base
    patch["display_uom"] = U.display_uom_of(m) if U.display_uom_of(m) in codes else base
    return patch


def is_same(m: dict, patch: dict) -> bool:
    for k, v in patch.items():
        cur = m.get(k)
        if k == "uoms":
            if not isinstance(cur, list) or len(cur) != len(v):
                return False
            for a, b in zip(cur, v):
                if {kk: a.get(kk) for kk in ("code", "factor", "is_base", "level")} != \
                   {kk: b.get(kk) for kk in ("code", "factor", "is_base", "level")}:
                    return False
        elif k == "pack_size":
            if abs(float(cur or 0) - float(v or 0)) > 1e-6:
                return False
        elif (cur or "") != (v or ""):
            if isinstance(v, bool) and bool(cur) == v:
                continue
            return False
    return True


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="tulis ke DB (default: pratinjau saja)")
    ap.add_argument("--type", default=None, help="batasi ke satu tipe material (fabric|accessory|fg)")
    ap.add_argument("--limit", type=int, default=0, help="batasi jumlah dokumen (untuk uji coba)")
    args = ap.parse_args()

    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]

    q: dict = {}
    if args.type:
        q["type"] = args.type

    total = 0
    changed = 0
    skipped = 0
    stat_uom_count = Counter()
    stat_by_type = Counter()
    samples: list[str] = []
    ops = []

    cursor = db.rahaza_materials.find(q, {"_id": 0})
    if args.limit:
        cursor = cursor.limit(args.limit)

    async for m in cursor:
        total += 1
        patch = build_patch(m)

        ok, errs = U.validate_uoms(patch["uoms"], patch["base_uom"])
        if not ok:
            print(f"  [LEWAT] {m.get('code')}: {'; '.join(errs)}")
            skipped += 1
            continue

        stat_uom_count[len(patch["uoms"])] += 1
        if is_same(m, patch):
            continue

        changed += 1
        stat_by_type[m.get("type") or "?"] += 1
        if len(samples) < 12:
            hier = " → ".join(f"{r['code']}×{r['factor']:g}" for r in patch["uoms"])
            samples.append(f"    {m.get('code'):<28} {hier}")
        ops.append((m["id"], patch))

    print("=" * 78)
    print(f"  Material diperiksa : {total}")
    print(f"  Perlu diperbarui   : {changed}")
    print(f"  Dilewati (invalid) : {skipped}")
    print(f"  Distribusi jml UOM : {dict(sorted(stat_uom_count.items()))}")
    print(f"  Per tipe           : {dict(stat_by_type)}")
    if samples:
        print("\n  Contoh hasil:")
        print("\n".join(samples))
    print("=" * 78)

    if not args.execute:
        print("  MODE PRATINJAU — tidak ada yang ditulis. Tambahkan --execute untuk menerapkan.")
        cli.close()
        return 0

    if not ops:
        print("  Tidak ada perubahan. DB sudah sinkron.")
        cli.close()
        return 0

    # tulis bertahap supaya aman di container kecil
    written = 0
    for i in range(0, len(ops), 200):
        batch = ops[i:i + 200]
        for mid, patch in batch:
            await db.rahaza_materials.update_one({"id": mid}, {"$set": patch})
            written += 1
        print(f"  … {written}/{len(ops)}")
    print(f"  SELESAI — {written} material diperbarui.")
    print("  Angka stok, unit_cost, dan min_stock TIDAK disentuh (INV-UOM-5).")
    cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
