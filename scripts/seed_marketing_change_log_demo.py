#!/usr/bin/env python3
"""seed_marketing_change_log_demo.py — data demo untuk LAYAR "JEJAK PERUBAHAN" (F6.5).

KENAPA SEEDER INI ADA
---------------------
Layar *Jejak Perubahan Marketing* menjawab pertanyaan rapat yang paling sering
tidak terjawab: **"siapa mengubah angka ini, dari berapa ke berapa, kapan, dan
kenapa?"** — plus **"kenapa akses toko saya dicabut?"**. Di environment yang baru
di-bootstrap, `marketing_change_log` hanya berisi 4 baris (target & anggaran dari
seeder Siklus) dengan SATU pelaku, SATU jenis, dan TANPA satu pun perubahan
kewenangan. Akibatnya layarnya tampak "belum jadi": filter *Hanya perubahan
kewenangan* mengosongkan tabel, pemilih *Pelaku* hanya punya satu nama, dan tidak
ada satu pun baris yang memperlihatkan nilai LAMA → BARU (semuanya "belum ada →
X"). Itu bukan cacat produk, itu **kekosongan data** — dan kekosongan yang
membuat fitur tidak bisa dinilai sama merugikannya dengan bug.

Seeder ini membuat keadaan yang REALISTIS lewat **API resmi** (bukan tulis
langsung ke koleksi jejak — jejak yang bisa dikarang bukan jejak):

* **Kewenangan** — SPV Marketing (`marketing@dewiaditya.id`) meng-assign toko ke
  dua staf pemegang toko demo (Nia & Rio) dengan alasan yang bisa dibaca.
* **Angka** — admin membuat lalu MENGUBAH target (jadi ada nilai lama → baru),
  mengubah rencana anggaran, serta menutup & membuka periode lama.
* **Dua pelaku berbeda** supaya pemilih "Pelaku" di layar punya arti.

YANG SENGAJA **TIDAK** DILAKUKAN
--------------------------------
`staffmkt@dewiaditya.id` **tidak diberi toko**. Dialah bukti hidup keadaan "staf
baru sebelum SPV meng-assign": layar marketing-nya kosong DAN menjelaskan
sebabnya ("minta SPV Marketing meng-assign toko"). Kalau seeder ini memberinya
toko, keadaan itu hilang dan uji negatif F6 kehilangan subjeknya.

Aman dijalankan berulang (idempoten): baris yang alasannya sudah ada di jejak
tidak dibuat ulang, dan assign yang sudah benar tidak disentuh.

Pakai:
    python3 /app/scripts/seed_marketing_change_log_demo.py
    python3 /app/scripts/seed_marketing_change_log_demo.py --cleanup
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SPV = {"email": "marketing@dewiaditya.id", "password": "Dewi@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"

# Periode demo untuk perubahan ANGKA. Sengaja BUKAN 2026-07: bulan itu dipakai
# gate INV-RETUR/INV-MKTCYCLE dengan angka target/anggaran yang pasti (Rp 100 jt),
# dan seeder tidak boleh menggeser angka yang sudah dijadikan bukti.
PERIOD = "2026-08"
# Toko yang dipakai seeder Siklus (F5) — jangan disentuh angkanya.
CYCLE_CODES = ("TIKTOK-OUTFIT",)

STAFF_DEMO = [
    ("Nia Pemegang Toko", "stafnia@dewiaditya.id"),
    ("Rio Pemegang Toko", "stafrio@dewiaditya.id"),
]

# Alasan = tanda pengenal baris demo (dipakai untuk idempoten & --cleanup).
REASONS = {
    "assign_nia": "Nia pegang 2 toko mulai rotasi shift Agustus",
    "assign_rio": "Rio pindah dari CS ke pemegang toko Shopee",
    "target_new": "Target Agustus disepakati di rapat mingguan 1 Agustus",
    "target_up": "Target dinaikkan setelah kampanye 8.8 disetujui owner",
    "budget_new": "Rencana anggaran Agustus mengikuti target baru",
    "budget_up": "Anggaran iklan ditambah, anggaran sample dipotong",
    "lock_close": "Periode ditutup sesudah angka dipakai rapat bulanan",
    "lock_open": "Dibuka sebentar karena ada 3 pesanan yang belum masuk",
}


def ok(m):
    print(f"  {G}✓{X} {m}")


def warn(m):
    print(f"  {Y}!{X} {m}")


def db_conn():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def login(creds: dict) -> str | None:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(4)
    return None


def ensure_staff(db) -> list:
    """Dua akun staf pemegang toko demo (idempoten, password Dewi@123)."""
    import bcrypt
    out = []
    for name, email in STAFF_DEMO:
        db.users.update_one(
            {"email": email},
            {"$set": {"name": name, "role": "staff_marketing",
                      "department": "Marketing", "status": "active",
                      "updated_at": datetime.now(timezone.utc)},
             "$setOnInsert": {"id": str(uuid.uuid4()), "email": email,
                              "password": bcrypt.hashpw(b"Dewi@123",
                                                        bcrypt.gensalt(10)).decode(),
                              "created_at": datetime.now(timezone.utc)}},
            upsert=True)
        out.append(db.users.find_one({"email": email}, {"_id": 0, "id": 1, "name": 1}))
    ok(f"akun staf pemegang toko demo siap: {', '.join(e for _, e in STAFF_DEMO)} "
       "(password Dewi@123)")
    return out


def main() -> int:
    cleanup = "--cleanup" in sys.argv
    db = db_conn()
    at = login(ADMIN)
    if not at:
        print("login admin gagal — backend belum siap?")
        return 2
    HA = {"Authorization": f"Bearer {at}", "Content-Type": "application/json"}
    st = login(SPV)
    HS = {"Authorization": f"Bearer {st}", "Content-Type": "application/json"} if st else HA
    if not st:
        warn("login SPV Marketing gagal — perubahan kewenangan dicatat sebagai admin")

    accounts = [a for a in requests.get(f"{BASE}/api/marketing/accounts",
                                        headers=HA, timeout=60).json()
                if isinstance(a, dict)]
    if len(accounts) < 4:
        print("Master toko kurang dari 4 — jalankan "
              "backend/scripts/seed_marketing_real_accounts.py --apply dulu")
        return 2
    accounts.sort(key=lambda a: (a.get("account_name") or ""))
    free = [a for a in accounts if a.get("account_code") not in CYCLE_CODES]
    # Toko yang PUNYA data (pesanan hasil impor nyata) — satu staf demo wajib
    # memegangnya, kalau tidak "staf pemegang toko" selalu melihat layar NOL dan
    # lingkup yang benar tidak bisa dibedakan dari layar rusak. Meng-assign staf
    # TIDAK mengubah satu pun angka toko itu (target/anggarannya tidak disentuh).
    with_data = next((a for a in accounts if a.get("account_code") in CYCLE_CODES), None)

    print(f"\n{B}SEED DEMO JEJAK PERUBAHAN MARKETING (F6.5){X}")

    if cleanup:
        n = db.marketing_change_log.delete_many(
            {"reason": {"$in": list(REASONS.values())}}).deleted_count
        staff_ids = [s["id"] for s in
                     db.users.find({"email": {"$in": [e for _, e in STAFF_DEMO]}},
                                   {"_id": 0, "id": 1})]
        db.marketing_platform_accounts.update_many(
            {"assigned_staff": {"$in": staff_ids}},
            {"$pull": {"assigned_staff": {"$in": staff_ids}}})
        db.marketing_account_targets.delete_many(
            {"year": int(PERIOD[:4]), "month": int(PERIOD[5:7]),
             "notes": "data demo jejak F6.5"})
        ok(f"{n} baris jejak demo dibuang · assign staf demo dilepas")
        return 0

    staff = ensure_staff(db)
    existing_reasons = set(db.marketing_change_log.distinct("reason"))

    # ── 1. KEWENANGAN — SPV meng-assign toko ke staf pemegang ───────────────
    def assign(acc_list, person, reason_key):
        reason = REASONS[reason_key]
        done = []
        for acc in acc_list:
            cur = list((db.marketing_platform_accounts.find_one(
                {"id": acc["id"]}, {"_id": 0, "assigned_staff": 1}) or {}
            ).get("assigned_staff") or [])
            if person["id"] in cur and reason in existing_reasons:
                done.append(f"{acc['account_name']} (sudah)")
                continue
            r = requests.post(f"{BASE}/api/marketing/account-assign/{acc['id']}",
                              headers=HS, timeout=60,
                              json={"staff_ids": sorted(set(cur + [person["id"]])),
                                    "reason": reason})
            done.append(f"{acc['account_name']} (HTTP {r.status_code})")
        ok(f"{person['name']} memegang: {' · '.join(done)}")

    assign([a for a in ([with_data] if with_data else []) + free[:1] if a],
           staff[0], "assign_nia")
    assign(free[1:2], staff[1], "assign_rio")

    # ── 2. ANGKA — target dibuat lalu DIUBAH (biar ada lama → baru) ─────────
    y, m = int(PERIOD[:4]), int(PERIOD[5:7])
    tgt_acc = free[0]

    def set_target(rev, orders, reason_key):
        reason = REASONS[reason_key]
        if reason in existing_reasons:
            return "sudah ada"
        r = requests.post(f"{BASE}/api/marketing/targets", headers=HA, timeout=60,
                          json={"account_id": tgt_acc["id"], "year": y, "month": m,
                                "revenue_target": rev, "orders_target": orders,
                                "notes": "data demo jejak F6.5", "reason": reason})
        return f"HTTP {r.status_code}"

    c1 = set_target(80_000_000, 400, "target_new")
    c2 = set_target(120_000_000, 600, "target_up")
    ok(f"{tgt_acc['account_name']} target {PERIOD}: 80 jt ({c1}) lalu naik 120 jt ({c2}) "
       "⇒ jejak memuat nilai LAMA → BARU + alasannya")

    def set_budget(by_cat, reason_key):
        reason = REASONS[reason_key]
        if reason in existing_reasons:
            return "sudah ada"
        r = requests.put(f"{BASE}/api/marketing/budget", headers=HA, timeout=60,
                         json={"account_id": tgt_acc["id"], "period": PERIOD,
                               "budget_by_category": by_cat,
                               "notes": "data demo jejak F6.5", "reason": reason})
        return f"HTTP {r.status_code}"

    c3 = set_budget({"ads": 12_000_000, "sample": 4_000_000}, "budget_new")
    c4 = set_budget({"ads": 18_000_000, "sample": 2_000_000}, "budget_up")
    ok(f"{tgt_acc['account_name']} anggaran {PERIOD}: iklan 12→18 jt, sample 4→2 jt "
       f"({c3} · {c4})")

    # ── 3. KUNCI PERIODE — ditutup lalu dibuka (dua aksi berbeda) ──────────
    lock_acc = free[1] if len(free) > 1 else tgt_acc
    old_period = "2026-06"

    def lock(action, reason_key):
        reason = REASONS[reason_key]
        if reason in existing_reasons:
            return "sudah ada"
        r = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HA, timeout=60,
                          json={"account_id": lock_acc["id"], "period": old_period,
                                "action": action, "reason": reason})
        return f"HTTP {r.status_code}"

    c5 = lock("close", "lock_close")
    c6 = lock("reopen", "lock_open")
    ok(f"{lock_acc['account_name']} periode {old_period}: ditutup ({c5}) lalu dibuka ({c6}) "
       "⇒ keadaan akhir TERBUKA (tidak menghalangi input)")

    # ── 4. keadaan akhir yang akan tampil di layar ──────────────────────────
    r = requests.get(f"{BASE}/api/marketing/change-log?page_size=1", headers=HA, timeout=60)
    s = requests.get(f"{BASE}/api/marketing/change-log/stats?days=30", headers=HA, timeout=60)
    tot = (r.json() or {}).get("total") if r.status_code == 200 else "?"
    stat = s.json() if s.status_code == 200 else {}
    print(f"\n{B}KEADAAN LAYAR JEJAK PERUBAHAN{X}")
    print(f"  baris jejak (semua)      : {tot}")
    print(f"  30 hari: {stat.get('total')} perubahan — {stat.get('number_changes')} angka · "
          f"{stat.get('permission_changes')} kewenangan")
    print(f"  pelaku                   : {stat.get('actors')} orang · "
          f"toko tersentuh {stat.get('accounts_touched')}")
    print(f"  tanpa alasan             : {stat.get('without_reason')}")
    print(f"\n{B}SELESAI{X} — buka: Portal Marketing → ANALITIK, LIVE & AI → "
          "\"Jejak Perubahan\" (atau Portal Manajemen → \"Jejak Marketing\").")
    print("  Catatan: staffmkt@dewiaditya.id SENGAJA tanpa toko (bukti layar kosong "
          "yang menjelaskan dirinya).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
