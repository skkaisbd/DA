#!/usr/bin/env python3
"""fix_cmt_ap_posting_profile.py — perbaiki akun BIAYA pada profil `cmt_ap_invoice`.

LATAR (FASE IA-C, 2026-07-26)
─────────────────────────────
Profil bawaan menulis `debit_cmt_expense = "6-2200"` dengan komentar "# Biaya Jasa CMT",
padahal pada CoA yang ter-seed **6-2200 = "Listrik & Air Kantor"**. Setiap tagihan jasa
jahit CMT yang diposting ke GL (termasuk lewat pintu **Invoice** Produksi yang baru)
karena itu membebani akun Listrik & Air: HPP produksi kurang saji, beban kantor
membengkak, dan laporan biaya per-domain (internal vs maklon) tidak bisa dipercaya.

Script ini merapikan profil yang SUDAH tersimpan di DB menjadi pemisahan per domain:
    debit_cmt_expense_internal = 5-231  (Biaya Vendor CMT – Jahit, COGS produksi DA)
    debit_cmt_expense_maklon   = 7-120  (Biaya Vendor CMT – Maklon, biaya proyek klien)
Kunci lama `debit_cmt_expense` DIBIARKAN bila nilainya BUKAN 6-2200 (berarti pengguna
sengaja memilih akun sendiri) — script ini tidak menimpa keputusan pengguna.

Kode aplikasi juga sudah punya jaring pengaman (`dewi_maklon_finance._cmt_expense_account`)
sehingga DB lama tetap posting ke akun benar walau migrasi ini belum dijalankan.

Properti: IDEMPOTEN · `--dry-run` didukung · tidak menyentuh jurnal yang sudah terlanjur
diposting (perbaikan jurnal lama = void + posting ulang lewat UI, bukan edit diam-diam).

Jalankan:  cd /app && python3 backend/migrations/fix_cmt_ap_posting_profile.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

INTERNAL_ACC = "5-231"
MAKLON_ACC = "7-120"
WRONG_ACC = "6-2200"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv("/app/backend/.env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    prof = db.rahaza_posting_profiles.find_one({"event_type": "cmt_ap_invoice"}, {"_id": 0})
    if not prof:
        print("  Profil cmt_ap_invoice belum ada — akan dibuat oleh seed bawaan saat posting pertama.")
        return 0

    mapping = dict(prof.get("mapping") or {})
    before = dict(mapping)
    if mapping.get("debit_cmt_expense") == WRONG_ACC:
        mapping.pop("debit_cmt_expense")
    mapping.setdefault("debit_cmt_expense_internal", INTERNAL_ACC)
    mapping.setdefault("debit_cmt_expense_maklon", MAKLON_ACC)

    if mapping == before:
        print("  Profil cmt_ap_invoice sudah benar — tidak ada perubahan.")
        return 0

    print(f"  sebelum : {before}")
    print(f"  sesudah : {mapping}")
    for code in (INTERNAL_ACC, MAKLON_ACC):
        acc = db.rahaza_coa_accounts.find_one({"code": code}, {"_id": 0, "code": 1, "name": 1})
        print(f"    cek akun {code}: {acc['name'] if acc else 'TIDAK ADA DI CoA (periksa seed CoA)'}")
    if not args.dry_run:
        db.rahaza_posting_profiles.update_one(
            {"event_type": "cmt_ap_invoice"},
            {"$set": {"mapping": mapping,
                      "description": "CMT Vendor AP Invoice → Dr Biaya Vendor CMT "
                                     "(internal COGS / maklon) / Cr AP Vendor"}})
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Selesai.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
