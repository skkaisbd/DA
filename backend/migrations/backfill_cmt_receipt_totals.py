#!/usr/bin/env python3
"""backfill_cmt_receipt_totals.py — perbaiki total header `cmt_receipts` + flag varian.

LATAR (FASE IA-C, 2026-07-26)
─────────────────────────────
`POST /api/prod/cmt-receipts/{id}/lines` DULU tidak menghitung ulang total header
(hanya `PUT .../lines/{lid}` yang melakukannya). Akibatnya penerimaan yang dibuat
lewat alur normal (buat header → tambah baris) menyimpan `total_shipped_by_cmt = 0`,
dan saat approve `mature_ap_from_cmt_receipt()` membandingkan:

    total_shipped_by_cmt (0)  !=  qty_actual + reject_qty

sehingga **setiap** tagihan CMT lahir dengan `variance_flagged = True` — alarm
"kiriman tidak cocok" yang selalu menyala = alarm yang diabaikan orang.

Penyebabnya sudah ditutup di `routes/dewi_cmt_packing.py` (helper `_recalc_receipt_totals`
dipanggil dari POST maupun PUT). Script ini membereskan dokumen yang terlanjur ditulis
kode lama: hitung ulang total header, lalu hitung ulang `variance_flagged` tagihan
yang bersumber dari penerimaan itu.

Properti: IDEMPOTEN · non-destruktif (tak menghapus apa pun) · `--dry-run` didukung ·
aman saat koleksi kosong. TIDAK menyentuh nilai uang tagihan (subtotal/net_amount) —
hanya bendera varian, karena nilai dihitung dari qty_actual × tarif yang tak berubah.

Jalankan:  cd /app && python3 backend/migrations/backfill_cmt_receipt_totals.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    receipts = list(db.cmt_receipts.find({}, {"_id": 0}))
    fixed_r = fixed_p = 0
    for r in receipts:
        lines = list(db.cmt_receipt_lines.find({"receipt_id": r["id"]}, {"_id": 0}))
        if not lines:
            continue
        totals = {
            "total_actual": sum(int(ln.get("qty_actual", 0) or 0) for ln in lines),
            "total_rejected": sum(int(ln.get("reject_qty", 0) or 0) for ln in lines),
            "total_shipped_by_cmt": sum(int(ln.get("qty_shipped_by_cmt", 0) or 0) for ln in lines),
        }
        if any(int(r.get(k, 0) or 0) != v for k, v in totals.items()):
            print(f"  {r.get('receipt_code')}: "
                  f"shipped {r.get('total_shipped_by_cmt', 0)}→{totals['total_shipped_by_cmt']} "
                  f"actual {r.get('total_actual', 0)}→{totals['total_actual']} "
                  f"reject {r.get('total_rejected', 0)}→{totals['total_rejected']}")
            fixed_r += 1
            if not args.dry_run:
                db.cmt_receipts.update_one({"id": r["id"]}, {"$set": totals})

        # flag varian tagihan yang bersumber dari penerimaan ini
        shipped = totals["total_shipped_by_cmt"]
        for p in db.dewi_cmt_payments.find({"source_receipt_id": r["id"]}, {"_id": 0}):
            should = shipped != (int(p.get("total_pcs", 0) or 0) + int(p.get("total_rejected", 0) or 0))
            if bool(p.get("variance_flagged")) != should:
                print(f"    tagihan {p.get('payment_code')}: variance_flagged "
                      f"{bool(p.get('variance_flagged'))} → {should}")
                fixed_p += 1
                if not args.dry_run:
                    db.dewi_cmt_payments.update_one({"id": p["id"]}, {"$set": {"variance_flagged": should}})

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Selesai — {len(receipts)} penerimaan diperiksa, "
          f"{fixed_r} header diperbaiki, {fixed_p} bendera varian tagihan diperbaiki.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
