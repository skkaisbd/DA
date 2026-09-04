"""SESI #40 — bersihkan artefak UJI dari data nyata, lewat PINTU RESMI saja.

Dua artefak yang ditemukan audit (lihat `memory/TEMUAN_AUDIT_MARKETING_SESI40.md`):
  T-3  pencairan uji `SET-TEST-001` + jurnal POSTED `JE-20260820-0001` (Rp 10,1 jt)
  T-4  559 pesanan uji di TikTok Outfit Boutique (sesi impor belum di-rollback)

Semua langkah memakai endpoint resmi (void jurnal · hapus pencairan · rollback
impor) supaya jejaknya tercatat dan rekap harian turunan ikut dihitung ulang.
`--apply` untuk mengeksekusi; tanpa itu hanya melapor.
"""
from __future__ import annotations

import sys

import requests
from pymongo import MongoClient

BASE = "http://localhost:8001"
APPLY = "--apply" in sys.argv
env = dict(l.split("=", 1) for l in open("/app/backend/.env") if "=" in l)
DB = MongoClient(env["MONGO_URL"].strip().strip('"'))[env["DB_NAME"].strip().strip('"')]

SETTLEMENT_ID = "SET-TEST-001"
JE_NUMBER = "JE-20260820-0001"
IMPORT_SESSION = "00c29756-1d26-4abb-a2f9-d1933a12d060"


def login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=30).json()
    return {"Authorization": f"Bearer {r.get('access_token') or r.get('token')}"}


def main():
    fin = login("finance@dewiaditya.id", "Dewi@123")
    adm = login("admin@garment.com", "Admin@123")

    st = DB.marketing_settlements.find_one({"settlement_id": SETTLEMENT_ID}, {"_id": 0})
    je = DB.rahaza_journal_entries.find_one({"je_number": JE_NUMBER}, {"_id": 0})
    sess = DB.marketing_data_import_sessions.find_one({"id": IMPORT_SESSION}, {"_id": 0})
    n_orders = DB.marketing_orders.count_documents({"_import_session_id": IMPORT_SESSION})
    print(f"pencairan uji  : {'ADA' if st else 'tidak ada'}"
          f"{' · Rp ' + format(st.get('net_payout', 0), ',.0f') if st else ''}")
    print(f"jurnal {JE_NUMBER}: {je.get('status') if je else 'tidak ada'}"
          f"{' · Rp ' + format(je.get('total_debit', 0), ',.0f') if je else ''}")
    print(f"sesi impor     : {sess.get('status') if sess else 'tidak ada'} · "
          f"{n_orders} pesanan menempel")
    if not APPLY:
        print("\n(dry-run — jalankan ulang dengan --apply untuk mengeksekusi)")
        return 0

    if je and je.get("status") != "voided":
        r = requests.post(f"{BASE}/api/rahaza/journals/{je['id']}/void", headers=fin,
                          json={"reason": "artefak uji sesi #38 (pencairan SET-TEST-001) "
                                          "— dibersihkan sesi #40"}, timeout=60)
        print(f"void jurnal      → {r.status_code} {r.text[:160]}")

    if st:
        r = requests.delete(f"{BASE}/api/marketing/settlements/{st['id']}",
                            headers=fin, timeout=60)
        print(f"hapus pencairan  → {r.status_code} {r.text[:160]}")

    if sess and sess.get("status") == "committed":
        r = requests.post(f"{BASE}/api/marketing/data-import/sessions/"
                          f"{IMPORT_SESSION}/rollback", headers=adm, timeout=300)
        print(f"rollback impor   → {r.status_code} {r.text[:300]}")

    print("\n── sesudah ──")
    print("pencairan uji :", DB.marketing_settlements.count_documents(
        {"settlement_id": SETTLEMENT_ID}))
    je2 = DB.rahaza_journal_entries.find_one({"je_number": JE_NUMBER},
                                            {"_id": 0, "status": 1}) or {}
    print("jurnal        :", je2.get("status", "tidak ada"))
    print("pesanan uji   :", DB.marketing_orders.count_documents(
        {"_import_session_id": IMPORT_SESSION}))
    print("total pesanan :", DB.marketing_orders.count_documents({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
