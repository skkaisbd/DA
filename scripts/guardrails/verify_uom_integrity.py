#!/usr/bin/env python3
"""INV-UOM-01 — Integritas Satuan (Unit of Measure) material.

Menegakkan invarian yang dirumuskan di `docs/RANCANGAN_MULTI_UOM.md` §2 dan
`memory/INVARIANTS.md` §U. Dibuat setelah audit 2026-07-27 menemukan bahwa
harga tidak ikut dikonversi saat input per kemasan (nilai persediaan & jurnal
membengkak sebesar `pack_size`).

Invarian yang diperiksa
-----------------------
  INV-UOM-3  `uoms` valid: tepat 1 satuan dasar berfaktor 1, kode unik,
             setiap faktor > 0, maksimal 3 satuan (dasar + 2 tingkat kemasan),
             induk harus ada di daftar yang sama.
  INV-UOM-4  `unit` (lama) == `base_uom` (baru), dan cermin `pack_unit`/
             `pack_size` konsisten dengan `uoms`.
  INV-UOM-6  `factor` relatif ke satuan dasar — dideteksi lewat urutan menaik
             dan kecocokan dengan induknya.
  INV-STK-UOM  Setiap baris `rahaza_material_stock.unit` (bila ada) harus sama
             dengan satuan dasar materialnya — menjamin INV-UOM-2 (semua qty
             tersimpan dalam satuan dasar).
  INV-UOM-1  Tidak ada material dengan `cost_uom` yang bukan satuan dasar.
             (`unit_cost` WAJIB per satuan dasar; `cost_uom` hanya boleh dipakai
             sebagai penanda entri sementara, tidak boleh persist.)

Jalankan:  python3 scripts/guardrails/verify_uom_integrity.py
Keluar 0 = HIJAU, 1 = MERAH.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Guard  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core import uom as U  # noqa: E402

MAX_REPORT = 15  # jangan banjiri layar


async def run() -> int:
    g = Guard("INV-UOM-01", "Integritas satuan material (multi-UOM)")
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]

    shown = 0

    def report(msg: str):
        nonlocal shown
        if shown < MAX_REPORT:
            g.add(msg)
        else:
            g.violations.append(msg)
        shown += 1

    # ── Material ────────────────────────────────────────────────────────────
    async for m in db.rahaza_materials.find({}, {"_id": 0}):
        g.bump()
        code = m.get("code") or m.get("id")
        base = U.base_uom_of(m)

        # INV-UOM-4 — unit lama == base_uom baru
        unit_lama = U.normalize_code(m.get("unit"))
        if m.get("base_uom") and unit_lama and unit_lama != base:
            report(f"[{code}] INV-UOM-4: unit='{unit_lama}' ≠ base_uom='{base}'")

        rows = m.get("uoms")
        if isinstance(rows, list) and rows:
            # INV-UOM-3
            ok, errs = U.validate_uoms(rows, base)
            if not ok:
                report(f"[{code}] INV-UOM-3: " + "; ".join(errs[:3]))

            # INV-UOM-6 — faktor relatif ke satuan dasar, bukan ke induk.
            # Kalau faktor sebuah baris <= faktor induknya, hampir pasti
            # pengisinya memakai basis induk (bug klasik).
            by_code = {U.normalize_code(r.get("code")): U._num(r.get("factor"), 0)  # noqa: SLF001
                       for r in rows if isinstance(r, dict)}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                c = U.normalize_code(r.get("code"))
                p = U.normalize_code(r.get("parent"))
                if p and p in by_code and by_code.get(c, 0) <= by_code[p]:
                    report(f"[{code}] INV-UOM-6: faktor '{c}'({by_code.get(c)}) "
                           f"≤ induk '{p}'({by_code[p]}) — faktor harus relatif ke satuan dasar")

            # INV-UOM-4 — cermin pack_* konsisten
            mirror = U.mirror_legacy(rows, base)
            if U.normalize_code(m.get("pack_unit")) != mirror["pack_unit"]:
                report(f"[{code}] INV-UOM-4: pack_unit='{m.get('pack_unit')}' "
                       f"≠ cermin uoms='{mirror['pack_unit']}'")
            elif abs(U._num(m.get("pack_size"), 1) - mirror["pack_size"]) > 1e-6:  # noqa: SLF001
                report(f"[{code}] INV-UOM-4: pack_size={m.get('pack_size')} "
                       f"≠ cermin uoms={mirror['pack_size']}")

        # INV-UOM-1 — `unit_cost` wajib per satuan dasar
        cost_uom = U.normalize_code(m.get("cost_uom"))
        if cost_uom and cost_uom != base:
            report(f"[{code}] INV-UOM-1: cost_uom='{cost_uom}' ≠ satuan dasar '{base}'. "
                   f"unit_cost WAJIB per satuan dasar.")

        # pack_size tidak boleh <= 0 (pembagi nol)
        ps = U._num(m.get("pack_size"), 1)  # noqa: SLF001
        if "pack_size" in m and ps <= 0:
            report(f"[{code}] pack_size={ps} tidak valid (harus > 0)")

    # ── Baris stok ──────────────────────────────────────────────────────────
    mats = {}
    async for m in db.rahaza_materials.find({}, {"_id": 0, "id": 1, "unit": 1,
                                                 "base_uom": 1, "code": 1}):
        mats[m["id"]] = m

    async for s in db.rahaza_material_stock.find({}, {"_id": 0, "material_id": 1, "unit": 1}):
        g.bump()
        mat = mats.get(s.get("material_id"))
        if not mat:
            continue
        su = U.normalize_code(s.get("unit"))
        if su and su != U.base_uom_of(mat):
            report(f"[{mat.get('code')}] INV-STK-UOM: baris stok bersatuan '{su}' "
                   f"padahal satuan dasar '{U.base_uom_of(mat)}' — qty stok wajib satuan dasar")

    cli.close()
    if shown > MAX_REPORT:
        print(f"    … dan {shown - MAX_REPORT} pelanggaran lain (dipotong).")
    return g.finish()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
