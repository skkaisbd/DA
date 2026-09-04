#!/usr/bin/env python3
"""seed_marketing_cycle_demo.py — data demo untuk LAYAR SIKLUS MARKETING (F5).

KENAPA SEEDER INI ADA
---------------------
Layar Siklus hanya bisa dinilai (oleh owner maupun agen berikutnya) kalau ada
keadaan yang BERBEDA-BEDA di dalamnya. Kalau semua toko kosong, layar tampak
"rusak" padahal hanya belum berdata, dan tidak ada satu pun peringatan yang bisa
dibuktikan bekerja.

Yang dibuat (idempoten, semuanya lewat jalur resmi):
  · **Pesanan nyata** bulan 2026-07 dari `samples/TikTok_UntukDikirim_2026-07-19.xlsx`
    (601 baris → 559 pesanan → Rp 59.783.811) lewat mesin impor sungguhan, sehingga
    rekap harian turunan & realisasi diskon otomatis ikut lahir.
  · **TIKTOK-OUTFIT**  target 100 jt  · anggaran 40 jt  ⇒ TERTINGGAL TARGET +
    ANGGARAN TERLAMPAUI (diskon Rp 48 jt tidak direncanakan sepeser pun).
  · **Toko kedua**     target 5 jt    · anggaran 20 jt  ⇒ aman/di bawah pace nol
    (tidak berpesanan) — memperlihatkan bedanya "belum ada data" dengan "nol".
  · **Toko ketiga**    tanpa target                    ⇒ flag `target_missing`.

Pakai:
    python3 /app/scripts/seed_marketing_cycle_demo.py            # buat/segarkan
    python3 /app/scripts/seed_marketing_cycle_demo.py --cleanup  # buang jejak demo
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
PERIOD = "2026-07"
MAIN_CODE = "TIKTOK-OUTFIT"
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"


def ok(m):
    print(f"  {G}✓{X} {m}")


def warn(m):
    print(f"  {Y}!{X} {m}")


def db_conn():
    c = MongoClient(os.environ["MONGO_URL"])
    return c[os.environ.get("DB_NAME", "test_database")]


def login() -> str:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(5)
    raise SystemExit("login gagal")


def main() -> int:
    cleanup = "--cleanup" in sys.argv
    token = login()
    H = {"Authorization": f"Bearer {token}"}
    HJ = {**H, "Content-Type": "application/json"}
    db = db_conn()
    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=HJ, timeout=60).json()
    if not isinstance(accounts, list) or not accounts:
        print("Master toko kosong — jalankan backend/scripts/seed_marketing_real_accounts.py --apply")
        return 2
    main_acc = next((a for a in accounts if a.get("account_code") == MAIN_CODE), None)
    if not main_acc:
        print(f"Toko {MAIN_CODE} tidak ada.")
        return 2
    others = [a for a in accounts if a["id"] != main_acc["id"]][:2]
    y, m = int(PERIOD[:4]), int(PERIOD[5:7])

    print(f"\n{B}SEED DEMO SIKLUS MARKETING (F5) — periode {PERIOD}{X}")

    if cleanup:
        for a in [main_acc] + others:
            db.marketing_account_targets.delete_many({"account_id": a["id"], "year": y, "month": m})
            db.marketing_budgets.delete_many({"account_id": a["id"], "period": PERIOD})
            db.marketing_period_locks.delete_many({"account_id": a["id"], "period": PERIOD})
        sess = list(db.marketing_import_sessions.find(
            {"account_id": main_acc["id"], "status": "committed"}, {"_id": 0, "id": 1}))
        for s in sess:
            r = requests.post(f"{BASE}/api/marketing/data-import/sessions/{s['id']}/rollback",
                              headers=HJ, timeout=300)
            print(f"    rollback sesi impor {s['id'][:8]}: HTTP {r.status_code}")
        ok("jejak demo siklus dibuang (target, anggaran, kunci, pesanan impor)")
        return 0

    # ── 1. pesanan nyata ────────────────────────────────────────────────────
    n = db.marketing_orders.count_documents({
        "account_id": main_acc["id"],
        "$or": [{"order_date": {"$regex": f"^{PERIOD}"}},
                {"order_date": {"$gte": datetime(y, m, 1), "$lt": datetime(y, m + 1, 1)}}]})
    if n > 0:
        ok(f"pesanan {PERIOD} sudah ada ({n}) — impor dilewati (idempoten)")
    elif not os.path.exists(SAMPLE):
        warn(f"berkas contoh tidak ada: {SAMPLE} — bagian pesanan dilewati")
    else:
        with open(SAMPLE, "rb") as fh:
            r = requests.post(
                f"{BASE}/api/marketing/data-import/upload", headers=H,
                files={"file": (os.path.basename(SAMPLE), fh,
                                "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet")},
                data={"source_type": "marketplace_orders", "account_id": main_acc["id"]},
                timeout=240)
        if r.status_code != 200:
            warn(f"upload gagal: HTTP {r.status_code} {r.text[:160]}")
        else:
            sid = (r.json().get("session") or {}).get("id")
            rc = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/commit",
                               headers=HJ, json={"on_duplicate": "skip"}, timeout=300)
            cb = rc.json() if rc.content else {}
            if rc.status_code == 200:
                ok(f"impor pesanan nyata: {cb.get('inserted')} masuk · "
                   f"{cb.get('rejected')} ditolak")
            else:
                warn(f"commit gagal: HTTP {rc.status_code} {str(rc.text)[:160]}")

    # ── 2. target & anggaran yang MEMBUAT keadaan berbeda ───────────────────
    def set_target(acc, revenue, orders):
        r = requests.post(f"{BASE}/api/marketing/targets", headers=HJ, timeout=60, json={
            "account_id": acc["id"], "year": y, "month": m,
            "revenue_target": revenue, "orders_target": orders,
            "notes": "data demo siklus F5"})
        return r.status_code

    def set_budget(acc, by_cat):
        r = requests.put(f"{BASE}/api/marketing/budget", headers=HJ, timeout=60, json={
            "account_id": acc["id"], "period": PERIOD,
            "budget_by_category": by_cat, "notes": "data demo siklus F5"})
        return r.status_code

    c1 = set_target(main_acc, 100_000_000, 600)
    c2 = set_budget(main_acc, {"ads": 30_000_000, "sample": 10_000_000})
    ok(f"{main_acc['account_name']}: target 100 jt (HTTP {c1}) · anggaran 40 jt (HTTP {c2}) "
       "⇒ tertinggal target + anggaran terlampaui")
    if others:
        a = others[0]
        c3 = set_target(a, 5_000_000, 30)
        c4 = set_budget(a, {"ads": 20_000_000})
        ok(f"{a['account_name']}: target 5 jt (HTTP {c3}) · anggaran 20 jt (HTTP {c4}) "
           "⇒ belum ada data (bukan nol)")
    if len(others) > 1:
        b = others[1]
        db.marketing_account_targets.delete_many({"account_id": b["id"], "year": y, "month": m})
        ok(f"{b['account_name']}: sengaja TANPA target ⇒ flag `target_missing`")

    # ── 3. cetak keadaan yang akan tampil di layar ──────────────────────────
    r = requests.get(f"{BASE}/api/marketing/cycle/overview?period={PERIOD}",
                     headers=HJ, timeout=300)
    if r.status_code == 200:
        ovr = r.json()
        t = ovr.get("totals") or {}
        print(f"\n{B}KEADAAN LAYAR SIKLUS{X}")
        print(f"  toko                : {t.get('accounts')} ({t.get('accounts_with_target')} bertarget)")
        print(f"  omzet produk        : Rp {t.get('revenue_product'):,.0f}".replace(",", "."))
        print(f"  target gabungan     : Rp {t.get('target_revenue'):,.0f}".replace(",", "."))
        print(f"  capaian / pace      : {t.get('revenue_pct')}% / {t.get('pace_pct')}%")
        print(f"  anggaran terpakai   : Rp {t.get('total_spend'):,.0f} dari "
              f"Rp {t.get('total_plan'):,.0f}".replace(",", "."))
        print(f"  peringatan          : {t.get('flags_red')} merah · {t.get('flags_yellow')} kuning")
        print(f"  cakupan HPP         : {t.get('hpp_coverage_pct')}%")
    else:
        warn(f"cycle/overview HTTP {r.status_code}")
    print(f"\n{B}SELESAI{X} — buka layar: Portal Marketing → Target & Budget → tab "
          "\"Siklus Bulan Ini\" (atau Portal Manajemen → Siklus Marketing), "
          f"pilih bulan {PERIOD}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
