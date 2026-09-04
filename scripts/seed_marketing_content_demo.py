#!/usr/bin/env python3
"""seed_marketing_content_demo.py — DATA DEMO untuk layar **Konten & Kreator** (F7)
dan **KPI Platform** (F7.2).

KENAPA SKRIP INI ADA
--------------------
Tiga layar hasil sesi 2026-08-13 hanya bisa dinilai kalau ada isinya:

* **Kalender Konten → Performa Konten** butuh konten ber-`creator_id` **dan** KPI;
* **Kalender Konten → Scorecard Kreator** butuh `marketing_creator_targets`
  (target bulanan) supaya "pencapaian" punya pembanding;
* **Kalender Konten → KPI Platform** butuh `marketing_platform_kpi_daily`, yang
  **hanya** boleh lahir dari impor ekspor Seller Center.

Pada environment segar ketiganya kosong, dan `marketing_kol_creators` yang kosong
bahkan membuat gate **INV-KPIIMPOR** merah karena sebab LINGKUNGAN (sudah ditutup
di sisi gate; skrip ini menutupnya di sisi data).

ATURAN YANG DIPEGANG SKRIP INI
------------------------------
1. **Tidak ada angka omzet palsu.** Skrip TIDAK menulis satu baris pun ke
   `marketing_sales_data` / `marketing_orders`. Omzet tetap TURUNAN dari pesanan
   (F2) — lihat `core/marketing_daily_rollup`.
2. **KPI platform diimpor, bukan disuntik.** Angkanya datang dari berkas contoh
   ekspor Seller Center milik owner (`/app/samples/shopee/*`) lewat mesin impor
   yang sama dengan yang dipakai staf — jadi yang tampil di layar benar-benar
   hasil jalur produksi, bukan dokumen buatan skrip.
3. **KPI konten lewat endpoint resmi** (`POST /content-calendar/{id}/kpi`) supaya
   angka turunan (engagement rate, CVR, GMV/view) DIHITUNG backend.
4. **Idempoten & bisa dibatalkan.** Jalankan berkali-kali hasilnya sama.
   `--cleanup` membuang SEMUA jejaknya (kreator demo, target, konten demo, dan
   dokumen KPI hasil impor contoh yang ditandai `_seed_demo`).

Pakai:
    python3 /app/scripts/seed_marketing_content_demo.py
    python3 /app/scripts/seed_marketing_content_demo.py --cleanup
    python3 /app/scripts/seed_marketing_content_demo.py --skip-import   # tanpa impor KPI
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SAMPLES = "/app/samples/shopee"

# Penanda jejak demo — dipakai --cleanup. JANGAN diubah tanpa memperbarui cleanup.
CODE_PREFIX = "DEMO-KRE-"
TITLE_PREFIX = "[DEMO] "
SEED_FLAG = "content_demo_2026_08"

G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
WIB = timezone(timedelta(hours=7))


def ok(msg, detail=""):
    print(f"  {G}✓{X} {msg}" + (f"  {detail}" if detail else ""))


def warn(msg, detail=""):
    print(f"  {Y}!{X} {msg}" + (f"  {detail}" if detail else ""))


def fail(msg, detail=""):
    print(f"  {R}✗{X} {msg}" + (f"  {detail}" if detail else ""))


def db_conn():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


def login() -> str:
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


# ── kreator demo: 4 profil dengan pola kerja yang BERBEDA ─────────────────────
# Sengaja berbeda supaya layar scorecard memperlihatkan hal yang berguna:
# ada yang melampaui target, ada yang tertinggal, ada yang belum punya KPI sama
# sekali (kolom "cakupan KPI" jadi ada gunanya).
CREATORS = [
    {"code": f"{CODE_PREFIX}01", "name": "Ayu Pratiwi (Live Host)", "tier": "Micro",
     "email": "kreator.ayu@dewiaditya.id", "revenue_target": 25_000_000,
     "sessions_target": 20, "viewers_target": 40_000, "profile": "over"},
    {"code": f"{CODE_PREFIX}02", "name": "Bagas Nugraha (Video)", "tier": "Macro",
     "email": "kreator.bagas@dewiaditya.id", "revenue_target": 40_000_000,
     "sessions_target": 12, "viewers_target": 120_000, "profile": "behind"},
    {"code": f"{CODE_PREFIX}03", "name": "Citra Lestari (Affiliate)", "tier": "Micro",
     "email": "kreator.citra@dewiaditya.id", "revenue_target": 15_000_000,
     "sessions_target": 8, "viewers_target": 25_000, "profile": "partial"},
    {"code": f"{CODE_PREFIX}04", "name": "Dwi Saputra (Baru)", "tier": "Nano",
     "email": "kreator.dwi@dewiaditya.id", "revenue_target": 8_000_000,
     "sessions_target": 4, "viewers_target": 10_000, "profile": "nokpi"},
]

CONTENT_PLAN = [
    # (offset hari dari tgl 1 bulan ini, jenis, judul, status)
    (1,  "video_pendek", "Gamis busui friendly — 3 gaya sehari", "posted"),
    (3,  "live",         "Live sore: flash sale gamis premium", "posted"),
    (5,  "foto_produk",  "Katalog kerudung segiempat warna pastel", "posted"),
    (7,  "video_pendek", "Unboxing paket lebaran M–XXXL", "posted"),
    (9,  "live",         "Live malam: bundling 2 gamis + kerudung", "posted"),
    (11, "video_pendek", "Tutorial styling 60 detik", "posted"),
    (13, "foto_produk",  "Behind the scenes proses jahit", "posted"),
    (15, "live",         "Live siang: doorprize pelanggan setia", "scheduled"),
    (17, "video_pendek", "Review pelanggan bintang 5", "scheduled"),
    (19, "foto_produk",  "Koleksi warna baru — teaser", "draft"),
    (21, "live",         "Live akhir bulan: gudang bersih", "scheduled"),
    (23, "video_pendek", "Tips memilih bahan adem", "draft"),
]

# KPI per profil (dasar; dikalikan indeks konten supaya bervariasi tapi DETERMINISTIK)
KPI_BASE = {
    "over":    {"views": 18_000, "likes": 1_500, "comments": 180, "shares": 120,
                "saves": 90, "watch_time_avg_sec": 21, "ctr": 4.1, "orders": 62,
                "gmv": 4_200_000},
    "behind":  {"views": 26_000, "likes": 900, "comments": 70, "shares": 40,
                "saves": 30, "watch_time_avg_sec": 9, "ctr": 1.2, "orders": 18,
                "gmv": 1_100_000},
    "partial": {"views": 7_000, "likes": 420, "comments": 45, "shares": 22,
                "saves": 18, "watch_time_avg_sec": 14, "ctr": 2.4, "orders": 12,
                "gmv": 900_000},
    "nokpi":   None,   # sengaja TIDAK ada KPI — cakupan KPI < 100% harus terlihat
}


def month_bounds(now: datetime):
    first = now.replace(day=1)
    if now.month == 1:
        prev = now.replace(year=now.year - 1, month=12, day=1)
    else:
        prev = now.replace(month=now.month - 1, day=1)
    return first, prev


def cleanup(db, H) -> int:
    print(f"\n{B}CLEANUP — membuang jejak data demo konten & kreator{X}")
    creators = list(db.marketing_kol_creators.find(
        {"creator_code": {"$regex": f"^{CODE_PREFIX}"}}, {"_id": 0, "id": 1, "name": 1}))
    cids = [c["id"] for c in creators]
    n_t = db.marketing_creator_targets.delete_many({"creator_id": {"$in": cids}}).deleted_count
    n_c = db.marketing_content_calendar.delete_many(
        {"title": {"$regex": "^\\[DEMO\\] "}}).deleted_count
    n_k = db.marketing_kol_creators.delete_many(
        {"creator_code": {"$regex": f"^{CODE_PREFIX}"}}).deleted_count
    n_p = db.marketing_platform_kpi_daily.delete_many({"_seed_demo": SEED_FLAG}).deleted_count
    n_a = db.marketing_ads_data.delete_many({"_seed_demo": SEED_FLAG}).deleted_count
    n_u = db.users.delete_many({"email": {"$in": [c["email"] for c in CREATORS]}}).deleted_count
    ok(f"kreator demo dibuang: {n_k}", f"(login user: {n_u})")
    ok(f"target kreator dibuang: {n_t}")
    ok(f"konten demo dibuang: {n_c}")
    ok(f"dokumen KPI platform hasil impor contoh dibuang: {n_p}")
    ok(f"baris iklan hasil impor contoh dibuang: {n_a}")
    return 0


def main() -> int:  # noqa: C901 — satu alur seed, sengaja dibaca berurutan
    args = sys.argv[1:]
    do_cleanup = "--cleanup" in args
    skip_import = "--skip-import" in args
    db = db_conn()
    try:
        token = login()
    except Exception as exc:  # pragma: no cover
        fail("login admin gagal", str(exc)[:160]); return 2
    H = {"Authorization": f"Bearer {token}"}
    HJ = {**H, "Content-Type": "application/json"}

    if do_cleanup:
        return cleanup(db, H)

    print(f"{B}{'=' * 78}\nSEED DEMO KONTEN & KREATOR (F7) + KPI PLATFORM (F7.2)\n{'=' * 78}{X}")

    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=90).json()
    accounts = [a for a in accounts if (a.get("status") or "active") == "active"]
    if not accounts:
        fail("tidak ada toko aktif — jalankan backend/scripts/seed_marketing_real_accounts.py")
        return 2
    shopee = [a for a in accounts if a.get("platform") == "shopee"]
    tiktok = [a for a in accounts if a.get("platform") == "tiktokshop"]
    pool = (shopee[:2] + tiktok[:2]) or accounts[:2]
    ok(f"toko dipakai: {', '.join(a['account_name'] for a in pool)}")

    # ── 1. KREATOR (master) ───────────────────────────────────────────────────
    print(f"\n{Y}1/4 Master kreator{X}")
    _lr = requests.get(f"{BASE}/api/marketing/kol/creators?limit=100",
                       headers=H, timeout=90).json() or {}
    _list = (_lr.get("creators") if isinstance(_lr, dict) else None) \
        or (_lr.get("data") if isinstance(_lr, dict) else None) \
        or (_lr if isinstance(_lr, list) else [])
    existing = {c.get("creator_code"): c for c in _list}
    creators: list = []
    for idx, spec in enumerate(CREATORS):
        acc_ids = [pool[idx % len(pool)]["id"]]
        if spec["tier"] == "Macro" and len(pool) > 1:
            acc_ids.append(pool[(idx + 1) % len(pool)]["id"])
        cur = existing.get(spec["code"])
        if cur:
            requests.put(f"{BASE}/api/marketing/kol/creators/{cur['id']}", headers=HJ,
                         json={"assigned_account_ids": acc_ids, "status": "active"},
                         timeout=90)
            creators.append({**spec, "id": cur["id"]})
            continue
        r = requests.post(f"{BASE}/api/marketing/kol/creators", headers=HJ, json={
            "name": spec["name"], "creator_code": spec["code"],
            "login_email": spec["email"], "login_password": "Dewi@123",
            "assigned_account_ids": acc_ids,
            "notes": "Data demo (seed_marketing_content_demo.py) — boleh dihapus.",
        }, timeout=90)
        if r.status_code not in (200, 201):
            fail(f"kreator {spec['code']} gagal dibuat", f"HTTP {r.status_code} {r.text[:120]}")
            continue
        body = r.json() or {}
        cid = (body.get("creator") or body.get("data") or body).get("id")
        creators.append({**spec, "id": cid})
    ok(f"kreator siap: {len(creators)}",
       ", ".join(c["code"] for c in creators))
    if not creators:
        return 1

    # ── 2. TARGET BULANAN (bulan ini + bulan lalu) ────────────────────────────
    print(f"\n{Y}2/4 Target bulanan kreator{X}")
    now = datetime.now(WIB)
    first, prev = month_bounds(now)
    n_target = 0
    for c in creators:
        for per in (first, prev):
            r = requests.post(f"{BASE}/api/marketing/targets/creator", headers=HJ, json={
                "creator_id": c["id"], "year": per.year, "month": per.month,
                "revenue_target": c["revenue_target"],
                "sessions_target": c["sessions_target"],
                "viewers_target": c["viewers_target"],
                "notes": "target demo (seed_marketing_content_demo.py)",
            }, timeout=90)
            if r.status_code == 200:
                n_target += 1
            else:
                warn(f"target {c['code']} {per.year}-{per.month:02d} gagal",
                     f"HTTP {r.status_code} {r.text[:100]}")
    ok(f"target tersimpan/diperbarui: {n_target}",
       f"({prev.strftime('%Y-%m')} & {first.strftime('%Y-%m')})")

    # ── 3. KONTEN + KPI (lewat endpoint resmi) ────────────────────────────────
    print(f"\n{Y}3/4 Kalender konten + KPI per konten{X}")
    have = {e.get("title"): e for e in
            (requests.get(f"{BASE}/api/marketing/content-calendar?page_size=100",
                          headers=H, timeout=90).json() or {}).get("data", [])}
    n_new = n_kpi = 0
    for i, (day_off, ctype, title, status) in enumerate(CONTENT_PLAN):
        creator = creators[i % len(creators)]
        acc = next((a for a in pool if a["id"] in
                    [pool[i % len(pool)]["id"]]), pool[0])
        date = (first + timedelta(days=day_off)).strftime("%Y-%m-%d")
        full_title = f"{TITLE_PREFIX}{title}"
        slug = f"demo-{i + 1:02d}"
        url = (f"https://{'shopee.co.id/video' if acc['platform'] == 'shopee' else 'vt.tiktok.com'}"
               f"/{slug}-{acc['account_code'].lower()}")
        entry = have.get(full_title)
        if not entry:
            payload = {
                "account_id": acc["id"], "account_name": acc["account_name"],
                "platform": acc["platform"], "date": date, "content_type": ctype,
                "title": full_title,
                "description": "Konten demo untuk menguji layar Performa & Scorecard.",
                "cta": "Klik link di bio!", "post_time": "19:00",
                "status": status, "creator_id": creator["id"],
                "hook": title,
            }
            if status == "posted":
                payload["published_url"] = url
                payload["published_at"] = date
            r = requests.post(f"{BASE}/api/marketing/content-calendar", headers=HJ,
                              json=payload, timeout=90)
            if r.status_code not in (200, 201):
                warn(f"konten '{title}' gagal", f"HTTP {r.status_code} {r.text[:110]}")
                continue
            body = r.json() or {}
            entry = body.get("data") or body.get("entry") or body
            n_new += 1
        eid = entry.get("id")
        base = KPI_BASE[creator["profile"]]
        if status == "posted" and base and eid:
            mult = 1 + (i % 3) * 0.25
            kpi = {k: round(v * mult, 2) for k, v in base.items()}
            r = requests.post(f"{BASE}/api/marketing/content-calendar/{eid}/kpi",
                              headers=HJ, json={**kpi, "published_url": url,
                                                "source": "demo_seed"}, timeout=90)
            if r.status_code == 200:
                n_kpi += 1
            else:
                warn(f"KPI konten '{title}' gagal", f"HTTP {r.status_code} {r.text[:110]}")
    ok(f"konten demo: {n_new} baru · KPI terisi: {n_kpi}",
       f"(bulan {first.strftime('%Y-%m')})")

    # ── 4. KPI PLATFORM — DIIMPOR dari berkas contoh Seller Center ────────────
    print(f"\n{Y}4/4 KPI platform (impor ekspor Seller Center contoh){X}")
    if skip_import:
        warn("dilewati (--skip-import)")
    elif not shopee:
        warn("tidak ada toko Shopee — impor KPI dilewati")
    else:
        target = shopee[0]
        jobs = [
            ("shopee_live_1d_contoh.csv", "shopee_content_kpi"),
            ("shopee_video_overview_contoh.csv", "shopee_content_kpi"),
            ("shopee_shop_stats_contoh.xlsx", "shopee_shop_kpi"),
            ("shopee_ads_cpc_contoh.csv", "shopee_ads_cpc"),
        ]
        for fname, stype in jobs:
            path = f"{SAMPLES}/{fname}"
            if not os.path.exists(path):
                warn(f"{fname} tidak ada — dilewati"); continue
            with open(path, "rb") as fh:
                files = {"file": (fname, fh.read(), "application/octet-stream")}
            r = requests.post(f"{BASE}/api/marketing/data-import/upload", headers=H,
                              files=files, data={"source_type": stype,
                                                 "account_id": target["id"]}, timeout=240)
            if r.status_code != 200:
                warn(f"{fname}: upload gagal", f"HTTP {r.status_code} {r.text[:110]}")
                continue
            sid = ((r.json() or {}).get("session") or {}).get("id")
            rc = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/commit",
                               headers=HJ, json={"on_duplicate": "skip"}, timeout=300)
            if rc.status_code == 409:
                ok(f"{fname}: sudah ada (409 anti dobel hitung) — dilewati")
                continue
            if rc.status_code != 200:
                warn(f"{fname}: commit gagal", f"HTTP {rc.status_code} {rc.text[:110]}")
                continue
            res = rc.json() or {}
            # tandai supaya --cleanup bisa membuangnya tanpa menyentuh data asli
            for col in ("marketing_platform_kpi_daily", "marketing_ads_data"):
                db[col].update_many({"_import_session_id": sid},
                                    {"$set": {"_seed_demo": SEED_FLAG}})
            ok(f"{fname}: masuk", f"{res.get('inserted', 0)} baru · "
                                  f"{res.get('updated', 0)} diperbarui → {stype}")
        ok(f"toko KPI: {target['account_name']}")

    # ── RINGKAS ───────────────────────────────────────────────────────────────
    n_kre = db.marketing_kol_creators.count_documents(
        {"creator_code": {"$regex": f"^{CODE_PREFIX}"}})
    n_con = db.marketing_content_calendar.count_documents({"title": {"$regex": "^\\[DEMO\\] "}})
    n_kpi_doc = db.marketing_platform_kpi_daily.count_documents({})
    print(f"\n{B}KEADAAN LAYAR{X}")
    print(f"  kreator demo          : {n_kre}")
    print(f"  konten demo           : {n_con}")
    print(f"  dokumen KPI platform  : {n_kpi_doc}")
    print(f"  target kreator        : "
          f"{db.marketing_creator_targets.count_documents({})}")
    print(f"\n{B}SELESAI{X} — buka: Portal Marketing → Kalender Konten → tab "
          f"'Performa Konten' / 'Scorecard Kreator' / 'KPI Platform'.")
    print("  batalkan dengan: python3 /app/scripts/seed_marketing_content_demo.py --cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
