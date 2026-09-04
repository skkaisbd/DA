#!/usr/bin/env python3
"""2026_08_12_sales_data_nested.py — F0.4: rapikan dokumen `marketing_sales_data` lama.

MASALAH (D01, terukur 2026-08-12)
--------------------------------
Sebelum F0.2, jenis impor `sales_daily` menulis dokumen **RATA**
(`revenue`/`orders`/`aov` di akar) sedangkan entri manual menulis **BERSARANG**
(`metrics{}` + `fulfillment{}` + `customer_satisfaction{}` + `live_metrics{}`).
Pembaca membaca `metrics.revenue`, jadi dokumen rata terbaca **Rp 0** —
dan Dashboard mati HTTP 500 karena mengindeks `sale["metrics"]` langsung.

Mesin impor lama `marketing_import.py` (dihapus di F0.6) menulis bentuk KE-TIGA:
`metrics{… quantity, rating}` tanpa 3 grup lain, dan upsert-nya menyertakan
`"id": <uuid baru>` sehingga `id` dokumen yang sudah ada BERUBAH.

Satuan juga tidak konsisten: form manual meminta rate dalam **fraksi 0–1**,
mesin impor menyimpan **persen 0–100**. Untuk data yang sama, skor kesehatan
memberi **79** vs **100**. Satuan kanonik sekarang: **persen 0–100**.

YANG DILAKUKAN SKRIP INI (idempoten)
------------------------------------
1. Dokumen tanpa `metrics` (bentuk rata) ⇒ dibangun ulang lewat
   `core.marketing_sales_shape.build_daily_doc()` — persis pembuat yang dipakai
   semua penulis sekarang.
2. Dokumen yang punya `metrics` tetapi belum ber-`shape_version` ⇒ dilengkapi
   grup yang hilang + normalisasi satuan persen, **tanpa mengubah angka omzet**.
3. Duplikat `(account_id, date, revenue_type)` ⇒ digabung: dokumen tertua
   dipertahankan (id-nya tetap), angka dijumlahkan, `merged_from[]` dicatat.
   Wajib dilakukan SEBELUM indeks unik F0.5 dipasang.
4. Skor kesehatan tiap akun terdampak dihitung ulang di akhir.

Pakai:
    python3 backend/migrations/2026_08_12_sales_data_nested.py            # dry-run
    python3 backend/migrations/2026_08_12_sales_data_nested.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app/backend")

from database import get_db                                   # noqa: E402
from core import marketing_sales_shape as shape               # noqa: E402

COLL = "marketing_sales_data"

# Kunci identitas/metadata: TIDAK boleh ikut sebagai "angka" ke pembuat bentuk,
# kalau ikut ia akan mendarat di `extra_raw` sebagai sampah.
META_KEYS = ("account_id", "account_code", "account_name", "platform", "date",
             "revenue_type", "source", "revenue_basis", "locked_source",
             "shape_version", "unit_pct_scale")


def _clean_flat(flat: dict) -> dict:
    return {k: v for k, v in (flat or {}).items() if k not in META_KEYS}


async def main(apply: bool) -> int:
    db = get_db()
    accounts = {a["id"]: a async for a in db.marketing_platform_accounts.find({}, {"_id": 0})}

    docs = await db[COLL].find({}, {"_id": 0}).to_list(200_000)
    print("=" * 78)
    print(f"F0.4 rapikan {COLL} — mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 78)
    print(f"  total dokumen                        : {len(docs)}")

    flat = [d for d in docs if not isinstance(d.get("metrics"), dict) or not d.get("metrics")]
    old_shape = [d for d in docs if d.get("shape_version") != 2 and d not in flat]
    print(f"  bentuk RATA (tanpa metrics)          : {len(flat)}")
    print(f"  bentuk lama (ada metrics, belum v2)  : {len(old_shape)}")

    groups: dict[tuple, list] = defaultdict(list)
    for d in docs:
        groups[(d.get("account_id"), d.get("date"), d.get("revenue_type"))].append(d)
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"  kunci duplikat (account,date,type)   : {len(dups)}"
          f"  (dokumen berlebih: {sum(len(v) - 1 for v in dups.values())})")

    touched_accounts: set = set()
    n_fixed = n_merged = n_skipped = 0

    # ── 1 & 2: bentuk dokumen ────────────────────────────────────────────────
    for d in docs:
        if d.get("shape_version") == 2:
            continue
        acc = accounts.get(d.get("account_id")) or {"id": d.get("account_id")}
        rtype = d.get("revenue_type") or "total"
        if rtype not in shape.REVENUE_TYPES:
            n_skipped += 1
            print(f"    ! dilewati (revenue_type '{rtype}' tidak dikenali) id={d.get('id')}")
            continue
        newdoc = shape.build_daily_doc(
            account=acc,
            date=d.get("date"),
            revenue_type=rtype,
            flat=_clean_flat(shape.flatten(d)),
            source=d.get("source") or (shape.SOURCE_IMPORT if d.get("import_history_id")
                                       else shape.SOURCE_MANUAL),
        )
        # jangan sentuh identitas & jejak
        for keep in ("id", "created_at", "created_by", "import_history_id",
                     "_import_session_id", "_import_source_type", "task_id"):
            if keep in d:
                newdoc[keep] = d[keep]
        newdoc["migrated_from_shape"] = "flat" if (d in flat) else "v1"
        n_fixed += 1
        touched_accounts.add(d.get("account_id"))
        if apply:
            await db[COLL].replace_one({"id": d["id"]}, newdoc)

    # ── 3: gabung duplikat ───────────────────────────────────────────────────
    for key, rows in dups.items():
        rows = sorted(rows, key=lambda r: str(r.get("created_at") or ""))
        keep, drop = rows[0], rows[1:]
        acc = accounts.get(keep.get("account_id")) or {"id": keep.get("account_id")}
        # Akumulasi angka dari SEMUA baris lewat `read_metrics` (bukan campuran
        # `flatten`+`read_metrics`) supaya `revenue` dan `revenue_product` tidak
        # dijumlahkan dengan aturan berbeda — cacat yang tertangkap saat uji migrasi.
        merged_flat = _clean_flat(shape.flatten(keep))
        base = shape.read_metrics(keep)
        SUM_FIELDS = ("revenue", "revenue_product", "revenue_order_amount",
                      "gross_before_discount", "seller_discount", "platform_discount",
                      "orders", "units", "buyers")
        for f in SUM_FIELDS:
            merged_flat[f] = shape._num(base.get(f))
        for extra in drop:
            em = shape.read_metrics(extra)
            for f in SUM_FIELDS:
                merged_flat[f] = shape._num(merged_flat.get(f)) + shape._num(em.get(f))
        merged_flat.pop("aov", None)     # dihitung ulang dari revenue/orders
        newdoc = shape.build_daily_doc(
            account=acc, date=keep.get("date"),
            revenue_type=keep.get("revenue_type") or "total",
            flat=merged_flat,
            source=keep.get("source") or shape.SOURCE_MANUAL,
        )
        for k in ("id", "created_at", "created_by"):
            if k in keep:
                newdoc[k] = keep[k]
        newdoc["merged_from"] = [x.get("id") for x in drop]
        n_merged += len(drop)
        touched_accounts.add(keep.get("account_id"))
        print(f"    gabung {len(drop)+1} dokumen untuk {key} → id={keep.get('id')}")
        if apply:
            await db[COLL].replace_one({"id": keep["id"]}, newdoc)
            await db[COLL].delete_many({"id": {"$in": [x["id"] for x in drop]}})

    print(f"\n  dokumen dirapikan bentuknya          : {n_fixed}")
    print(f"  dokumen duplikat digabung/dihapus    : {n_merged}")
    print(f"  dilewati (perlu diperiksa manual)    : {n_skipped}")

    # ── 4: skor kesehatan ────────────────────────────────────────────────────
    if apply and touched_accounts:
        from routes.marketing_shared import _recalculate_health_score
        for aid in touched_accounts:
            if aid:
                try:
                    await _recalculate_health_score(db, aid)
                except Exception as e:      # pragma: no cover
                    print(f"    ! recalc health gagal untuk {aid}: {e}")
        print(f"  skor kesehatan dihitung ulang        : {len(touched_accounts)} akun")

    left = await db[COLL].count_documents({"metrics": {"$exists": False}})
    print(f"\n  SISA dokumen tanpa `metrics`         : {left}   (target: 0)")
    if not apply:
        print("\n  DRY-RUN: tidak ada yang diubah. Jalankan ulang dengan --apply.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    os.chdir("/app/backend")
    raise SystemExit(asyncio.run(main(a.apply)))
