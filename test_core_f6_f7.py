#!/usr/bin/env python3
"""test_core_f6_f7.py — CORE TEST **F6 (RBAC per toko + jejak)** & **F7 (konten & kreator)**.

Menguji bukti selesai yang tertulis di `memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`:

F6  1. staf marketing yang di-assign 1 toko ⇒ `GET /api/marketing/accounts` hanya 1 toko;
       toko lain ⇒ **403** (pesanan, siklus).
    2. `POST /api/marketing/targets` sebagai staf ⇒ **403**; sebagai manager ⇒ **200**.
    3. ubah target ⇒ `marketing_change_log` memuat nilai LAMA & BARU + peran pelaku,
       dan bisa dibaca layar lewat `GET /api/marketing/periods/change-log`.
F7  4. `status='posted'` tanpa link terbit ⇒ **400**; link ngawur ⇒ **400**.
    5. KPI konten diisi ⇒ angka turunan (engagement rate, CVR) dihitung, bukan diketik.
    6. `GET /api/marketing/content-calendar/performance?group_by=creator` ⇒ per kreator:
       konten, views, engagement, GMV KPI **dan** omzet pesanan (dipisah, tidak dijumlah).

Pakai: python3 /app/test_core_f6_f7.py
"""
from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
MGR = {"email": "marketing@dewiaditya.id", "password": "Dewi@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []


def ok(n, d=""):
    RES.append((n, True, d)); print(f"  {G}PASS{X}  {n}" + (f" — {d}" if d else ""))


def bad(n, d=""):
    RES.append((n, False, d)); print(f"  {R}FAIL{X}  {n}" + (f" — {d}" if d else ""))


def check(n, c, d=""):
    (ok if c else bad)(n, d); return bool(c)


def db_conn():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def login(cred) -> str | None:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=cred, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(6)
    return None


def main() -> int:
    print(f"{B}{'=' * 88}\nCORE TEST F6 (RBAC per toko + jejak) & F7 (konten & kreator)\n{'=' * 88}{X}")
    db = db_conn()
    at = login(ADMIN)
    if not at:
        print("login admin gagal"); return 2
    AH = {"Authorization": f"Bearer {at}", "Content-Type": "application/json"}
    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=AH, timeout=60).json()
    if len(accounts) < 2:
        print("butuh ≥2 toko"); return 2
    a1, a2 = accounts[0], accounts[1]

    # ── F6 ────────────────────────────────────────────────────────────────────
    print(f"\n{Y}[F6] VISIBILITAS PER PEMAKAI + JEJAK PERUBAHAN{X}")
    staff = db.users.find_one({"email": STAFF["email"]}, {"_id": 0, "id": 1, "role": 1})
    if not staff:
        bad("F6-0 akun staf marketing ada",
            "jalankan backend/scripts/seed_role_accounts.py"); return 1
    ok("F6-0 akun staf marketing ada", f"role={staff.get('role')}")
    db.marketing_platform_accounts.update_one({"id": a1["id"]},
                                             {"$addToSet": {"assigned_staff": staff["id"]}})
    db.marketing_platform_accounts.update_one({"id": a2["id"]},
                                              {"$pull": {"assigned_staff": staff["id"]}})
    st = login(STAFF)
    SH = {"Authorization": f"Bearer {st}", "Content-Type": "application/json"}
    try:
        seen = requests.get(f"{BASE}/api/marketing/accounts", headers=SH, timeout=60).json()
        ids = [x["id"] for x in seen] if isinstance(seen, list) else []
        check("F6-1 staf hanya melihat toko yang di-assign",
              ids == [a1["id"]], f"{len(ids)} toko: {[x.get('account_name') for x in seen][:4]}")
        r = requests.get(f"{BASE}/api/marketing/cycle/summary"
                         f"?account_id={a2['id']}&period=2026-07", headers=SH, timeout=90)
        check("F6-2 buka siklus toko orang lain ⇒ 403", r.status_code == 403,
              f"status={r.status_code} {str(r.text)[:90]}")
        r = requests.get(f"{BASE}/api/marketing/orders?account_id={a2['id']}&limit=1",
                         headers=SH, timeout=60)
        check("F6-3 daftar pesanan toko orang lain ⇒ 403", r.status_code == 403,
              f"status={r.status_code}")
        r = requests.get(f"{BASE}/api/marketing/cycle/overview?period=2026-07",
                         headers=SH, timeout=180)
        rows = (r.json() or {}).get("rows") or []
        check("F6-4 overview staf hanya memuat tokonya",
              r.status_code == 200 and len(rows) == 1
              and rows[0]["account"]["id"] == a1["id"], f"{len(rows)} baris")
        r = requests.post(f"{BASE}/api/marketing/targets", headers=SH, timeout=60, json={
            "account_id": a1["id"], "year": 2026, "month": 9,
            "revenue_target": 1_000_000, "orders_target": 5})
        check("F6-5 staf menetapkan target ⇒ 403 (keputusan SPV)", r.status_code == 403,
              f"status={r.status_code} {str(r.text)[:90]}")
    finally:
        db.marketing_platform_accounts.update_one({"id": a1["id"]},
                                                 {"$pull": {"assigned_staff": staff["id"]}})

    mt = login(MGR)
    MH = {"Authorization": f"Bearer {mt}", "Content-Type": "application/json"}
    r = requests.post(f"{BASE}/api/marketing/targets", headers=MH, timeout=60, json={
        "account_id": a1["id"], "year": 2026, "month": 9,
        "revenue_target": 7_000_000, "orders_target": 40})
    check("F6-6 manager marketing menetapkan target ⇒ 200", r.status_code == 200,
          f"status={r.status_code}")
    r = requests.post(f"{BASE}/api/marketing/targets", headers=MH, timeout=60, json={
        "account_id": a1["id"], "year": 2026, "month": 9,
        "revenue_target": 9_500_000, "orders_target": 55})
    logs = list(db.marketing_change_log.find(
        {"account_id": a1["id"], "period": "2026-09"}, {"_id": 0}).sort("at", -1))
    upd = next((x for x in logs if x.get("action") == "target_update"), None)
    check("F6-7 jejak menyimpan nilai LAMA & BARU + peran pelaku",
          bool(upd) and (upd.get("before") or {}).get("revenue_target") == 7_000_000
          and (upd.get("after") or {}).get("revenue_target") == 9_500_000
          and bool(upd.get("actor_role")),
          f"{(upd or {}).get('before')} → {(upd or {}).get('after')} oleh "
          f"{(upd or {}).get('actor_name')} ({(upd or {}).get('actor_role')})")
    r = requests.get(f"{BASE}/api/marketing/periods/change-log"
                     f"?account_id={a1['id']}&period=2026-09", headers=MH, timeout=60)
    check("F6-8 layar bisa membaca jejak lewat endpoint change-log",
          r.status_code == 200 and (r.json() or {}).get("total", 0) >= 2,
          f"status={r.status_code} total={(r.json() or {}).get('total')}")
    db.marketing_change_log.delete_many({"account_id": a1["id"], "period": "2026-09"})
    db.marketing_account_targets.delete_many({"account_id": a1["id"], "year": 2026, "month": 9})

    # ── F7 ────────────────────────────────────────────────────────────────────
    print(f"\n{Y}[F7] KONTEN: LINK TERBIT + KPI + LAPORAN KREATOR{X}")
    creator = db.marketing_kol_creators.find_one({}, {"_id": 0, "id": 1, "name": 1})
    if not creator:
        bad("F7-0 master kreator ada", "marketing_kol_creators kosong"); return 1
    ok("F7-0 master kreator ada", creator.get("name"))
    body = {"account_id": a1["id"], "account_name": a1.get("account_name"),
            "platform": a1.get("platform") or "tiktokshop", "date": "2026-08-05",
            "content_type": "video", "title": "UJI F7 konten",
            "creator_id": creator["id"], "status": "posted"}
    r = requests.post(f"{BASE}/api/marketing/content-calendar", headers=MH, json=body, timeout=60)
    check("F7-1 status 'posted' TANPA link terbit ⇒ 400", r.status_code == 400,
          f"status={r.status_code} {str(r.text)[:110]}")
    r = requests.post(f"{BASE}/api/marketing/content-calendar", headers=MH, timeout=60,
                      json={**body, "published_url": "sudah tayang"})
    check("F7-2 link terbit ngawur (bukan URL) ⇒ 400", r.status_code == 400,
          f"status={r.status_code}")
    r = requests.post(f"{BASE}/api/marketing/content-calendar", headers=MH, timeout=60,
                      json={**body, "creator_id": "kreator-palsu",
                            "published_url": "https://tiktok.com/@x/video/1"})
    check("F7-3 kreator yang tidak ada di master ⇒ 400", r.status_code == 400,
          f"status={r.status_code}")
    r = requests.post(f"{BASE}/api/marketing/content-calendar", headers=MH, timeout=60,
                      json={**body, "published_url": "https://tiktok.com/@dewi/video/999"})
    cid = ((r.json() or {}).get("data") or {}).get("id")
    if not check("F7-4 konten sah dibuat (link + kreator)", r.status_code == 200 and bool(cid),
                 f"status={r.status_code} {str(r.text)[:110]}"):
        return 1
    try:
        r = requests.post(f"{BASE}/api/marketing/content-calendar/{cid}/kpi", headers=MH,
                          timeout=60, json={"views": 10000, "likes": 800, "comments": 120,
                                            "shares": 80, "saves": 200, "ctr": 3.2,
                                            "orders": 40, "gmv": 6_000_000})
        d = ((r.json() or {}).get("data") or {})
        der = d.get("kpi_derived") or {}
        check("F7-5 KPI tersimpan + angka turunan DIHITUNG (bukan diketik)",
              r.status_code == 200 and der.get("engagement") == 1000
              and der.get("engagement_rate") == 10.0 and der.get("cvr") == 0.4,
              f"engagement={der.get('engagement')} rate={der.get('engagement_rate')}% "
              f"cvr={der.get('cvr')}% gmv/view={der.get('gmv_per_view')}")
        r = requests.get(f"{BASE}/api/marketing/content-calendar/performance"
                         f"?group_by=creator&date_from=2026-08-01&date_to=2026-08-31",
                         headers=MH, timeout=90)
        j = r.json() if r.status_code == 200 else {}
        row = next((x for x in (j.get("rows") or []) if x["key"] == creator["id"]), None)
        check("F7-6 laporan per kreator memuat baris kreator uji",
              bool(row), f"status={r.status_code} {len(j.get('rows') or [])} baris")
        if row:
            check("F7-7 angka kreator: konten · views · engagement · GMV KPI",
                  row["contents"] >= 1 and row["views"] >= 10000
                  and row["engagement"] >= 1000 and row["gmv_kpi"] >= 6_000_000,
                  f"{row['contents']} konten · {row['views']:.0f} views · "
                  f"eng {row['engagement']:.0f} · GMV {row['gmv_kpi']:.0f}")
            check("F7-8 omzet pesanan kreator DIPISAH dari GMV KPI (tidak dijumlah)",
                  "order_revenue" in row and "gmv_kpi" in row,
                  f"gmv_kpi={row['gmv_kpi']:.0f} vs order_revenue={row['order_revenue']:.0f}")
            check("F7-9 cakupan KPI dilaporkan (angka tanpa KPI tidak disembunyikan)",
                  row.get("kpi_coverage_pct") is not None,
                  f"cakupan {row.get('kpi_coverage_pct')}%")
        notes = " ".join(j.get("data_notes") or [])
        check("F7-10 catatan kejujuran: GMV KPI ≠ omzet pesanan",
              "tidak" in notes and "dua kali" in notes, notes[:100])
        r = requests.get(f"{BASE}/api/marketing/content-calendar/performance?group_by=content_type",
                         headers=MH, timeout=90)
        check("F7-11 pengelompokan lain bekerja (per jenis konten)",
              r.status_code == 200 and bool((r.json() or {}).get("rows")),
              f"status={r.status_code}")
    finally:
        requests.delete(f"{BASE}/api/marketing/content-calendar/{cid}", headers=MH, timeout=60)
        db.marketing_content_calendar.delete_many({"title": "UJI F7 konten"})
        print("    konten uji dihapus")

    good = sum(1 for _, o, _ in RES if o)
    color = G if good == len(RES) else R
    print(f"\n{B}{'=' * 88}{X}\nRINGKAS F6+F7: {color}{good}/{len(RES)} PASS{X}")
    for n, o, d in RES:
        if not o:
            print(f"  {R}GAGAL{X} {n} — {d}")
    print(f"{B}{'=' * 88}{X}")
    return 0 if good == len(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
