"""Idempotent seeder for the 5 RBAC test/role login accounts.

These accounts historically lived in the archived `production_seed_full.py`
seeder (now returning 410/404). They are required for role-based login and are
linked to real employees for Portal Saya / self-service endpoints.

Run:  python3 /app/backend/scripts/seed_role_accounts.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# TEMUAN 2026-07-26: skrip ini TIDAK memuat `/app/backend/.env`, sehingga
# `DB_NAME` jatuh ke default "test_database" dan 7 akun role ter-seed ke
# database YANG SALAH (login 401, employee_id=None). Muat .env dulu.
load_dotenv("/app/backend/.env")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def now():
    return datetime.now(timezone.utc)


ROLE_USERS = [
    # (name, email, role, department, linked employee_code)
    ("HR / SDM",            "hr@dewiaditya.id",      "hr",                  "Manajemen SDM", "DA-002"),
    ("Staff Keuangan",      "finance@dewiaditya.id", "accounting",          "Keuangan",      "DA-009"),
    ("Supervisor Produksi", "spv@dewiaditya.id",     "supervisor_produksi", "Produksi",      "DA-003"),
    ("Admin Gudang",        "gudang@dewiaditya.id",  "admin_gudang",        "Gudang",        "DA-005"),
    ("Admin Maklon",        "maklon@dewiaditya.id",  "admin_maklon",        "Maklon",        "DA-006"),
    # FASE 6 — fixture RBAC gudang tingkat STAF. Punya akses Portal Gudang
    # (PORTAL_ACCESS['warehouse'] memuat 'tim_packing') dan BOLEH Lepas/Retur
    # karantina, tapi TIDAK BOLEH Scrap (write-off) → dipakai untuk uji negatif
    # RBAC yang sebelumnya tak bisa dilakukan karena semua akun gudang yang ada
    # ber-role 'admin_gudang' (yang memang berhak scrap).
    ("Tim Packing Gudang",  "packing@dewiaditya.id", "tim_packing",         "Gudang",        "DA-007"),
    # FASE 8+/10 — penerima alarm & digest "aksesoris belum dinilai". Sebelumnya tidak
    # ada akun ber-role `admin_aksesoris` sama sekali, sehingga uji penerima notifikasi
    # (verify_fase8plus A2d) selalu gagal di DB baru walau kodenya benar.
    ("Admin Aksesoris",     "aksesoris@dewiaditya.id", "admin_aksesoris",   "Gudang",        "DA-008"),
    # 2026-08-07 — TAHAP FINAL PERSETUJUAN PR. Temuan nyata: tidak ada satu pun
    # akun berperan `director`/`cfo`/`ceo`/`owner` di DB, sehingga PR bernilai
    # besar (yang wajib lewat tahap final) TIDAK BISA diselesaikan siapa pun
    # kecuali admin memakai override — rantai persetujuan mentok di tahap 3.
    # `employee_id` dibiarkan kosong (None): DA-001 "Direktur Operasional" sudah
    # ditautkan ke admin@garment.com, dan dua akun yang menunjuk satu karyawan
    # akan bertabrakan di absensi (`rahaza_attendance_events` di-key employee_id).
    ("Direktur",            "direktur@dewiaditya.id",  "director",          "Manajemen",     None),
    # 2026-08-12 (#5) — TEMUAN: tidak ada SATU PUN akun ber-role Portal Marketing
    # (`portalAccess.js` → toko: pic_toko / pic_marketing / staff_marketing /
    # marketing_kol / cs_staff / manager_marketing). Akibatnya setiap pembuktian
    # layar marketing (Monitoring Pengiriman, Laporan Rapat Mingguan, Katalog dari
    # Master, Wizard Impor) hanya pernah dilakukan sebagai `superadmin` — peran yang
    # MELEWATI seluruh penyaringan portal/menu. Jadi "terbukti jalan" tidak pernah
    # berarti "bisa dipakai staf marketing". Dua akun di bawah menutup lubang uji itu:
    #   · manager_marketing → SPV Marketing (semua toko)
    #   · staff_marketing   → staf/PIC toko (dasar uji negatif F6 RBAC per toko nanti)
    ("Manager Marketing",   "marketing@dewiaditya.id", "manager_marketing", "Marketing",     None),
    ("Staff Marketing",     "staffmkt@dewiaditya.id",  "staff_marketing",   "Marketing",     None),
]


async def main():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "garment_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Build employee_code -> id map
    emp_map = {}
    async for e in db.rahaza_employees.find({}, {"id": 1, "employee_code": 1}):
        if e.get("employee_code"):
            emp_map[e["employee_code"]] = e.get("id")

    count = 0
    for name, email, role, dept, link_code in ROLE_USERS:
        emp_id = emp_map.get(link_code)
        await db.users.update_one(
            {"email": email},
            {
                "$set": {
                    "name": name,
                    "role": role,
                    "department": dept,
                    "status": "active",
                    "employee_id": emp_id,
                    "updated_at": now(),
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "email": email,
                    "password": hash_password("Dewi@123"),
                    "created_at": now(),
                },
            },
            upsert=True,
        )
        count += 1
        print(f"  upserted {email} (role={role}, employee_id={emp_id})")

    # Link admin to owner DA-001
    admin_emp = emp_map.get("DA-001")
    if admin_emp:
        await db.users.update_one(
            {"email": "admin@garment.com"},
            {"$set": {"employee_id": admin_emp, "updated_at": now()}},
        )
        print(f"  linked admin@garment.com -> DA-001 ({admin_emp})")

    print(f"DONE: {count} role accounts upserted.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
