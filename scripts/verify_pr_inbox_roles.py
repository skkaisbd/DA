#!/usr/bin/env python3
"""Bukti bug + verifikasi perbaikan: inbox approval PR harus terlihat oleh
peran keuangan NYATA di aplikasi ini (`accounting`, `staff_keuangan`,
`manager_keuangan`), bukan hanya nama peran generik ('finance'/'accountant').

Alur: admin buat PR → submit → admin setujui (jadi `dept_approved`) →
inbox finance@ HARUS memuat PR itu.

2026-08-07 — DUA PENYESUAIAN (perilaku baru yang DISENGAJA, bukan regresi):
  1. Kedalaman rantai persetujuan kini mengikuti NILAI PR (ambang diatur owner).
     PR uji lama bernilai Rp 50.000 ⇒ sekarang cukup 1 tahap, jadi setelah satu
     persetujuan ia langsung `approved` dan memang TIDAK pantas muncul di inbox
     keuangan. Nilai PR uji dinaikkan ke Rp 50.000.000 supaya tahap keuangan
     benar-benar ada — itulah yang ingin diuji berkas ini.
  2. Pembersihan tidak lagi mengandalkan `DELETE /requests/{id}` "best-effort"
     (endpoint itu dulu TIDAK ADA, dan 404-nya ditelan diam-diam — itulah
     sebabnya PR "UJI INBOX — kancing plastik" menumpuk di data demo).
     Endpoint DELETE sekarang ada, tapi pembersihan tetap dipastikan lewat Mongo
     di blok `finally` agar alat uji tidak pernah meninggalkan data palsu.
"""
import os
import sys
from datetime import date

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")


def login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def cleanup(pr_id, pr_no):
    """Hapus jejak uji langsung di Mongo (PR + notifikasi + pesan hub)."""
    try:
        from dotenv import load_dotenv
        from pymongo import MongoClient
        load_dotenv("/app/backend/.env")
        cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        n1 = db.dewi_procurement_requests.delete_many({"id": pr_id}).deleted_count
        n2 = db.notifications.delete_many({"source_id": pr_id}).deleted_count
        n3 = db.comm_messages.delete_many({"meta.pr_id": pr_id}).deleted_count
        # bersihkan juga sisa PR uji dari sesi-sesi lama yang tak pernah terhapus
        n4 = db.dewi_procurement_requests.delete_many(
            {"title": "UJI INBOX — kancing plastik"}).deleted_count
        cli.close()
        print(f"  bersih: PR={n1} notif={n2} pesan={n3} sisa_PR_uji_lama={n4} ({pr_no})")
    except Exception as e:  # noqa: BLE001
        print(f"  ! pembersihan gagal: {e}")


def main():
    admin = login("admin@garment.com", "Admin@123")
    ah = {"Authorization": f"Bearer {admin}"}

    pr = requests.post(f"{BASE}/api/procurement/requests", headers=ah, timeout=30, json={
        "title": "UJI INBOX — kancing plastik",
        "description": "Cek inbox approval per peran",
        "justification": "verifikasi alur persetujuan",
        "priority": "medium",
        "request_type": "consumable",
        "department": "Produksi",
        "needed_by": date.today().isoformat(),
        # Rp 50.000.000 → rantai 3 tahap, jadi tahap KEUANGAN pasti ada.
        "items": [{"name": "Kancing plastik 15mm", "uom": "pcs", "qty": 100,
                   "estimated_price": 500_000}],
    })
    pr.raise_for_status()
    prid = pr.json()["id"]
    prno = pr.json().get("request_number")
    print(f"  PR dibuat: {prno} (nilai Rp {pr.json().get('total_estimated'):,.0f})".replace(",", "."))

    ok = True
    try:
        sub = requests.post(f"{BASE}/api/procurement/requests/{prid}/submit",
                            headers=ah, json={}, timeout=30)
        chain = sub.json().get("approval_chain") if sub.status_code == 200 else None
        print(f"  rantai persetujuan: {chain}")
        if chain != ["dept", "finance", "final"]:
            ok = False
            print("  GAGAL: PR bernilai besar seharusnya 3 tahap")

        r = requests.post(f"{BASE}/api/procurement/requests/{prid}/approve", headers=ah,
                          json={"comment": "OK dept"}, timeout=30)
        cur = requests.get(f"{BASE}/api/procurement/requests/{prid}", headers=ah, timeout=30).json()
        print(f"  status setelah 1x approve: {cur.get('status')} (rc={r.status_code})")
        if cur.get("status") != "dept_approved":
            ok = False
            print("  GAGAL: status seharusnya dept_approved")

        for email, pw, must_see in [
            ("finance@dewiaditya.id", "Dewi@123", True),      # role accounting → tahap keuangan
            ("hr@dewiaditya.id", "Dewi@123", False),          # bukan approver pengadaan
        ]:
            t = login(email, pw)
            inbox = requests.get(f"{BASE}/api/procurement/inbox",
                                 headers={"Authorization": f"Bearer {t}"}, timeout=30)
            items = inbox.json() if inbox.status_code == 200 else []
            items = items if isinstance(items, list) else items.get("items", [])
            seen = any(i.get("id") == prid for i in items)
            verdict = "OK" if seen == must_see else "GAGAL"
            if seen != must_see:
                ok = False
            print(f"  {email:26s} http={inbox.status_code} inbox={len(items)} "
                  f"melihat_PR={seen} harusnya={must_see} → {verdict}")
    finally:
        cleanup(prid, prno)

    print("\nHASIL:", "LULUS" if ok else "MASIH BERMASALAH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
