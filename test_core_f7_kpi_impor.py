#!/usr/bin/env python3
"""test_core_f7_kpi_impor.py — CORE TEST **F7.2 Impor KPI Seller Center**,
**F6.4 Assign Toko**, dan **F7.4 Scorecard Kreator**.

Menguji bukti selesai untuk tiga permintaan owner (13 Agu 2026):

F7.2  Impor KPI Shopee tanpa AI, dari berkas ASLI Seller Center
      (`/app/samples/shopee/*` — contoh yang diunggah owner):
      1. penormal memotong baris judul grup/metadata/blok section, dan MENOLAK
         berkas yang periodenya menyeberang bulan (biaya iklan bulanan);
      2. upload+commit KPI Live/Video/Statistik Toko ⇒ `marketing_platform_kpi_daily`;
      3. impor ulang berkas yang sama ⇒ **diperbarui**, bukan baris kembar;
      4. KPI platform TIDAK pernah menulis ke `marketing_sales_data` (omzet SSOT)
         dan membawa penanda `is_platform_kpi`;
      5. laporan iklan CPC ⇒ `marketing_ads_data` dan realisasi anggaran F5
         kategori `ads` = Σ biaya;
      6. periode iklan yang BERIRISAN ditolak 409 (anti dobel hitung);
      7. KPI per konten memakai `published_url` sebagai kunci: link lama
         diperbarui **tanpa menimpa judul/rencana staf**, link baru dibuat
         berstatus `posted` + angka turunan dihitung; link ngawur ditolak.
F6.4  8. SPV meng-assign staf ⇒ staf melihat tokonya; di-unassign ⇒ **403**;
      9. staf mencoba meng-assign ⇒ **403**; peran yang sudah melihat semua toko
         ⇒ **400** (assign tidak ada artinya);
     10. setiap perubahan meninggalkan jejak `marketing_change_log` (LAMA & BARU).
F7.4 11. Scorecard kreator: target vs pencapaian, tiga sumber uang DIPISAH
         (pesanan · sesi · GMV KPI) + basis penilaian tertulis.

Pakai: python3 /app/test_core_f7_kpi_impor.py
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
MGR = {"email": "marketing@dewiaditya.id", "password": "Dewi@123"}
STAFF = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
SAMPLES = "/app/samples/shopee"
KPI_COL = "marketing_platform_kpi_daily"
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


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def login(cred):
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=cred, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(6)
    return None


def upload(headers, path, source_type, account_id, filename=None):
    with open(path, "rb") as fh:
        files = {"file": (filename or os.path.basename(path), fh.read(),
                          "application/octet-stream")}
    return requests.post(f"{BASE}/api/marketing/data-import/upload", headers=headers,
                         files=files,
                         data={"source_type": source_type, "account_id": account_id},
                         timeout=180)


def commit(headers, session_id, on_duplicate="skip"):
    return requests.post(
        f"{BASE}/api/marketing/data-import/sessions/{session_id}/commit",
        headers={**headers, "Content-Type": "application/json"},
        json={"on_duplicate": on_duplicate}, timeout=240)


def main() -> int:  # noqa: C901 — satu alur uji, sengaja dibaca berurutan
    print(f"{B}{'=' * 88}\nCORE TEST F7.2 (impor KPI Seller Center) · F6.4 (assign toko) · "
          f"F7.4 (scorecard kreator)\n{'=' * 88}{X}")
    db = db_conn()
    at = login(ADMIN)
    mt = login(MGR)
    st_tok = login(STAFF)
    if not (at and mt and st_tok):
        print("login gagal (admin/manager/staff)"); return 2
    AH = {"Authorization": f"Bearer {at}"}
    MH = {"Authorization": f"Bearer {mt}"}
    SH = {"Authorization": f"Bearer {st_tok}"}

    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=AH, timeout=60).json()
    shopee = [a for a in accounts if (a.get("platform") or "") == "shopee"]
    if not shopee:
        print("butuh minimal 1 toko Shopee"); return 2
    # ── PILIH TOKO UJI YANG TIDAK MENIMPA DATA KERJA ─────────────────────────
    # CACAT NYATA yang ditutup 2026-08-13 (ditemukan saat menjalankan gate sesudah
    # data demo diimpor): pembersihan gate dulu berbunyi
    #     db[KPI_COL].delete_many({"account_id": aid})
    #     db.marketing_ads_data.delete_many({"account_id": aid, "source_report": ...})
    # yaitu MENGHAPUS SELURUH KPI & baris iklan milik toko itu — termasuk yang
    # baru saja diimpor staf dari Seller Center. Artinya `bash scripts/gate.sh`,
    # perintah yang dianjurkan dijalankan berkali-kali sehari, **memusnahkan data
    # kerja owner** tanpa satu pun peringatan. Sekarang:
    #   1. gate memilih toko Shopee yang BELUM punya KPI/iklan sama sekali;
    #   2. gate MENANDAI setiap dokumen hasil impornya (`_gate_kpiimpor=True`);
    #   3. pembersihan HANYA membuang dokumen bertanda itu.
    def _has_real_data(_aid: str) -> bool:
        return bool(db[KPI_COL].count_documents(
            {"account_id": _aid, "_gate_kpiimpor": {"$ne": True}}, limit=1)
            or db.marketing_ads_data.count_documents(
            {"account_id": _aid, "_gate_kpiimpor": {"$ne": True}}, limit=1))

    acc = next((a for a in shopee if not _has_real_data(a["id"])), None)
    if acc is None:
        print(f"  {Y}DILEWATI{X} — semua toko Shopee sudah memuat KPI/iklan nyata. "
              "Gate menolak menimpa data kerja; buat satu toko Shopee kosong untuk uji.")
        return 0
    aid = acc["id"]
    staff_user = db.users.find_one({"email": STAFF["email"]}, {"_id": 0, "id": 1, "role": 1})
    if not staff_user:
        print("akun staf marketing tidak ada"); return 2

    # bersihkan jejak uji SEBELUMNYA — hanya yang bertanda gate (bukan data kerja)
    db[KPI_COL].delete_many({"_gate_kpiimpor": True})
    db.marketing_ads_data.delete_many({"_gate_kpiimpor": True})
    db.marketing_content_calendar.delete_many({"published_url": {"$regex": "UJI-F72"}})

    gate_sessions: list = []          # semua session impor milik gate ini

    def tag_gate_docs():
        """Tandai dokumen hasil impor gate supaya pembersihan bisa tepat sasaran."""
        if not gate_sessions:
            return
        for col in (KPI_COL, "marketing_ads_data"):
            db[col].update_many({"_import_session_id": {"$in": gate_sessions}},
                                {"$set": {"_gate_kpiimpor": True}})

    # ── 1. PENORMAL BERKAS (tanpa server) ─────────────────────────────────────
    print(f"\n{Y}[F7.2] PENORMAL BERKAS EKSPOR SELLER CENTER{X}")
    from core import marketing_import_prenorm as P  # noqa: E402

    def pre(fn, key):
        with open(f"{SAMPLES}/{fn}", "rb") as fh:
            return P.prenormalize(fh.read(), fn, key)

    try:
        _h, rows = pre("shopee_live_1d_contoh.csv", "shopee_content_kpi")
        check("F72-1 Live harian: baris judul grup dilewati, semua tanggal terbaca",
              len(rows) == 7 and all(r["channel"] == "live" for r in rows)
              and rows[0]["source"] == "shopee_live_1d",
              f"{len(rows)} baris · kanal={rows[0]['channel']} · sumber={rows[0]['source']}")
        check("F72-2 durasi teks ekspor ('00:01:19') diubah menjadi detik",
              rows[0].get("avg_watch_seconds") == 79.0,
              f"avg_watch_seconds={rows[0].get('avg_watch_seconds')}")
        _h, rows_ov = pre("shopee_live_overview_contoh.csv", "shopee_content_kpi")
        check("F72-3 Live ringkas: blok 'Sumber Penonton' TIDAK jadi baris data",
              len(rows_ov) == 1 and rows_ov[0].get("live_sessions") == "1"
              and float(rows_ov[0].get("live_minutes") or 0) > 600,
              f"{len(rows_ov)} baris · sesi={rows_ov[0].get('live_sessions')} · "
              f"menit={rows_ov[0].get('live_minutes')}")
        _h, rows_vid = pre("shopee_video_overview_contoh.csv", "shopee_content_kpi")
        check("F72-4 Video: kanal dikenali dari kolom penanda (bukan nama berkas)",
              len(rows_vid) == 1 and rows_vid[0]["channel"] == "video"
              and rows_vid[0].get("effective_viewers") == "19",
              f"kanal={rows_vid[0]['channel']} · penonton efektif="
              f"{rows_vid[0].get('effective_viewers')}")
        _h, rows_shop = pre("shopee_shop_stats_contoh.xlsx", "shopee_shop_stats")
        r0 = rows_shop[0]
        check("F72-5 Statistik toko (xlsx): 3 basis pesanan + kontribusi kanal",
              len(rows_shop) == 1 and r0.get("gmv_created") and r0.get("gmv_ready")
              and r0.get("gmv_paid") and r0.get("gmv_live") is not None
              and r0.get("gmv_ads") is not None,
              f"tgl={r0.get('date')} dibuat={r0.get('gmv_created')} "
              f"live={r0.get('gmv_live')} iklan={r0.get('gmv_ads')}")
        _h, rows_ads = pre("shopee_ads_cpc_contoh.csv", "shopee_ads_cpc")
        check("F72-6 Laporan iklan: 6 baris metadata dipotong, periode terbaca",
              len(rows_ads) == 4 and rows_ads[0]["period_start"] == "2026-08-07"
              and rows_ads[0]["period_end"] == "2026-08-13",
              f"{len(rows_ads)} iklan · periode {rows_ads[0]['period_start']}"
              f"..{rows_ads[0]['period_end']}")
    except Exception as e:  # noqa: BLE001
        bad("F72-1..6 penormal berkas contoh", f"{type(e).__name__}: {e}")

    # periode menyeberang bulan ⇒ DITOLAK (biaya iklan dipakai per bulan)
    with open(f"{SAMPLES}/shopee_ads_cpc_contoh.csv", "rb") as fh:
        raw = fh.read().replace(b"07/08/2026 - 13/08/2026", b"25/07/2026 - 05/08/2026")
    try:
        P.prenormalize(raw, "x.csv", "shopee_ads_cpc")
        bad("F72-7 laporan iklan 2 bulan ⇒ ditolak", "diterima (seharusnya ValueError)")
    except ValueError as e:
        check("F72-7 laporan iklan yang menyeberang bulan ⇒ ditolak dengan alasan",
              "dua bulan" in str(e).lower(), str(e)[:90])

    # ── 2. UPLOAD + COMMIT ────────────────────────────────────────────────────
    print(f"\n{Y}[F7.2] UPLOAD → COMMIT → KOLEKSI TUJUAN{X}")
    sales_before = db.marketing_sales_data.count_documents({"account_id": aid})
    total_ins = 0
    for fn, stype in (("shopee_live_1d_contoh.csv", "shopee_content_kpi"),
                      ("shopee_live_overview_contoh.csv", "shopee_content_kpi"),
                      ("shopee_video_overview_contoh.csv", "shopee_content_kpi"),
                      ("shopee_shop_stats_contoh.xlsx", "shopee_shop_kpi")):
        r = upload(AH, f"{SAMPLES}/{fn}", stype, aid)
        if r.status_code != 200:
            bad(f"F72-8 upload {fn}", f"status={r.status_code} {str(r.text)[:120]}")
            continue
        j = r.json()
        sid = j["session"]["id"]
        gate_sessions.append(sid)
        rc = commit(AH, sid)
        total_ins += (rc.json() or {}).get("inserted", 0) if rc.status_code == 200 else 0
    tag_gate_docs()
    kpi_rows = list(db[KPI_COL].find({"account_id": aid}, {"_id": 0}))
    check("F72-8 KPI Live/Video/Toko masuk marketing_platform_kpi_daily",
          len(kpi_rows) >= 9 and total_ins >= 9,
          f"{len(kpi_rows)} dokumen (7 live harian + 1 video + 1 statistik toko)")
    channels = {r.get("channel") for r in kpi_rows}
    check("F72-9 kanal tersimpan terpisah (shop/live/video)",
          {"shop", "live", "video"} <= channels, f"kanal={sorted(channels)}")
    check("F72-10 KPI platform TIDAK menulis omzet SSOT (marketing_sales_data)",
          db.marketing_sales_data.count_documents({"account_id": aid}) == sales_before,
          f"jumlah rekap harian tetap {sales_before}")
    check("F72-11 setiap dokumen KPI membawa penanda 'bukan omzet SSOT'",
          all(r.get("is_platform_kpi") and r.get("revenue_basis") == "platform_kpi"
              and r.get("not_sales_ssot_note") for r in kpi_rows),
          "is_platform_kpi + revenue_basis=platform_kpi + catatan terpasang")

    # impor ulang ⇒ diperbarui, bukan kembar
    r = upload(AH, f"{SAMPLES}/shopee_live_1d_contoh.csv", "shopee_content_kpi", aid)
    if r.status_code == 200:
        gate_sessions.append(r.json()["session"]["id"])
    rc = commit(AH, r.json()["session"]["id"]) if r.status_code == 200 else None
    tag_gate_docs()
    body = rc.json() if rc is not None and rc.status_code == 200 else {}
    check("F72-12 impor ulang berkas sama ⇒ DIPERBARUI (tanpa baris kembar)",
          body.get("updated") == 7 and body.get("inserted") == 0
          and db[KPI_COL].count_documents({"account_id": aid}) == len(kpi_rows),
          f"inserted={body.get('inserted')} updated={body.get('updated')} "
          f"total tetap {db[KPI_COL].count_documents({'account_id': aid})}")

    # ── 3. IKLAN → REALISASI ANGGARAN F5 ──────────────────────────────────────
    print(f"\n{Y}[F7.2] LAPORAN IKLAN CPC → REALISASI ANGGARAN (F5){X}")
    r = upload(AH, f"{SAMPLES}/shopee_ads_cpc_contoh.csv", "shopee_ads_cpc", aid)
    if check("F72-13 upload laporan iklan diterima", r.status_code == 200,
             f"status={r.status_code} {str(r.text)[:120]}"):
        rc = commit(AH, r.json()["session"]["id"])
        gate_sessions.append(r.json()["session"]["id"])
        tag_gate_docs()
        ads = list(db.marketing_ads_data.find(
            {"account_id": aid, "source_report": "shopee_ads_cpc"}, {"_id": 0}))
        spend = round(sum(float(a.get("spend") or 0) for a in ads), 2)
        check("F72-14 4 kampanye masuk marketing_ads_data + turunan dihitung",
              len(ads) == 4 and all(a.get("period_days") == 7 for a in ads)
              and any(a.get("roas") for a in ads),
              f"{len(ads)} kampanye · Σ biaya Rp{spend:,.0f} · periode 7 hari"
              .replace(",", "."))
        cyc = requests.get(f"{BASE}/api/marketing/cycle/summary"
                           f"?account_id={aid}&period=2026-08", headers=AH, timeout=180)
        cats = {c["category"]: c for c in
                ((cyc.json() or {}).get("budget") or {}).get("categories", [])}
        got = float((cats.get("ads") or {}).get("spend") or 0)
        check("F72-15 realisasi anggaran kategori 'ads' = Σ biaya iklan impor",
              cyc.status_code == 200 and abs(got - spend) < 1,
              f"realisasi Rp{got:,.0f} vs impor Rp{spend:,.0f}".replace(",", "."))

    # periode beririsan ⇒ 409
    with open(f"{SAMPLES}/shopee_ads_cpc_contoh.csv", "rb") as fh:
        raw = fh.read().replace(b"07/08/2026 - 13/08/2026", b"01/08/2026 - 31/08/2026")
    files = {"file": ("iklan_bulanan.csv", raw, "text/csv")}
    r = requests.post(f"{BASE}/api/marketing/data-import/upload", headers=AH, files=files,
                      data={"source_type": "shopee_ads_cpc", "account_id": aid}, timeout=120)
    if r.status_code == 200:
        rc = commit(AH, r.json()["session"]["id"])
        check("F72-16 periode iklan BERIRISAN ⇒ 409 (anti dobel hitung biaya)",
              rc.status_code == 409 and "dua kali" in str(rc.text).lower(),
              f"status={rc.status_code} {str(rc.text)[:110]}")
    else:
        bad("F72-16 periode iklan beririsan ⇒ 409", f"upload gagal {r.status_code}")

    # ── 4. KPI PER KONTEN (kunci published_url) ───────────────────────────────
    print(f"\n{Y}[F7.2] KPI PER KONTEN — KUNCI LINK TERBIT{X}")
    # MANDIRI DI LINGKUNGAN SEGAR (temuan 2026-08-13): gate ini dulu MERAH pada
    # clone baru hanya karena `marketing_kol_creators` masih kosong — kegagalan
    # LINGKUNGAN yang menyamar sebagai kegagalan FITUR. Gate yang merah karena
    # sebab palsu adalah gate yang mulai diabaikan (pelajaran RK-18). Jadi kalau
    # master kreator kosong, test membuat SATU kreator uji sendiri lalu
    # membuangnya di bagian bersih-bersih (jejak `created_by='gate_kpiimpor'`).
    creator = db.marketing_kol_creators.find_one({}, {"_id": 0, "id": 1, "name": 1,
                                                      "creator_code": 1})
    creator_temp = False
    if not creator:
        creator = {"id": "uji-f72-kreator", "name": "KREATOR UJI GATE",
                   "creator_code": "UJI-F72-KRE"}
        db.marketing_kol_creators.insert_one({
            **creator, "handle": "@uji_f72_kreator", "platform": "shopee",
            "tier": "Micro", "status": "active", "assigned_account_ids": [aid],
            "cost_config": {"fee_type": "commission", "fixed_fee": 0,
                            "commission_pct": 5},
            "created_by": "gate_kpiimpor", "created_at": _iso_now(),
        })
        creator_temp = True
    ok("F72-17a master kreator tersedia",
       f"{creator.get('name')} ({creator.get('creator_code')})"
       + (" — dibuat sementara oleh gate" if creator_temp else ""))
    url_old = "https://shopee.co.id/video/UJI-F72-LAMA"
    url_new = "https://shopee.co.id/video/UJI-F72-BARU"
    plan_title = "RENCANA konten UJI-F72 (judul harus tetap)"
    db.marketing_content_calendar.insert_one({
        "id": "uji-f72-konten-lama", "account_id": aid,
        "account_name": acc.get("account_name"), "platform": "shopee",
        "date": "2026-08-13", "content_type": "video_pendek", "title": plan_title,
        "status": "scheduled", "published_url": url_old, "creator_id": creator["id"],
    })
    csv_txt = ("Link Terbit,Tanggal Tayang,Kode/Username Kreator,Views,Suka,Komentar,"
               "Share,Order dari Konten,GMV Konten (Rp)\n"
               f"{url_old},2026-08-13,{creator.get('creator_code')},10000,800,120,80,40,6.000.000\n"
               f"{url_new},2026-08-12,{creator.get('creator_code')},4000,200,10,5,7,1.200.000\n"
               f"bukan-url,2026-08-12,{creator.get('creator_code')},100,1,0,0,0,0\n")
    files = {"file": ("kpi_konten.csv", csv_txt.encode(), "text/csv")}
    r = requests.post(f"{BASE}/api/marketing/data-import/upload", headers=AH, files=files,
                      data={"source_type": "content_performance", "account_id": aid},
                      timeout=120)
    if check("F72-17 upload KPI konten diterima", r.status_code == 200,
             f"status={r.status_code} {str(r.text)[:120]}"):
        rc = commit(AH, r.json()["session"]["id"])
        body = rc.json() if rc.status_code == 200 else {}
        check("F72-18 link lama DIPERBARUI, link baru DIBUAT, link ngawur DITOLAK",
              body.get("updated") == 1 and body.get("inserted") == 1
              and body.get("rejected") == 1,
              f"updated={body.get('updated')} inserted={body.get('inserted')} "
              f"rejected={body.get('rejected')}")
        old = db.marketing_content_calendar.find_one({"published_url": url_old}, {"_id": 0})
        check("F72-19 judul/rencana staf TIDAK tertimpa oleh impor",
              (old or {}).get("title") == plan_title
              and (old or {}).get("status") == "posted",
              f"judul='{(old or {}).get('title', '')[:40]}' status={(old or {}).get('status')}")
        der = (old or {}).get("kpi_derived") or {}
        check("F72-20 angka turunan KPI DIHITUNG (bukan diketik)",
              der.get("engagement") == 1000 and der.get("engagement_rate") == 10.0
              and der.get("cvr") == 0.4,
              f"engagement={der.get('engagement')} rate={der.get('engagement_rate')}% "
              f"cvr={der.get('cvr')}%")
        new = db.marketing_content_calendar.find_one({"published_url": url_new}, {"_id": 0})
        check("F72-21 konten baru dari impor: status 'posted' + pemilik kreator",
              (new or {}).get("status") == "posted"
              and (new or {}).get("creator_id") == creator["id"],
              f"status={(new or {}).get('status')} kreator={(new or {}).get('creator_name')}")

    # ── 5. F6.4 ASSIGN TOKO ───────────────────────────────────────────────────
    print(f"\n{Y}[F6.4] ASSIGN TOKO (SPV) + JEJAK PERUBAHAN{X}")
    A = f"{BASE}/api/marketing/account-assign"
    MHJ = {**MH, "Content-Type": "application/json"}
    before_staff = list((db.marketing_platform_accounts.find_one(
        {"id": aid}, {"_id": 0, "assigned_staff": 1}) or {}).get("assigned_staff") or [])
    try:
        r = requests.get(f"{A}/staff-options", headers=MHJ, timeout=60)
        opts = (r.json() or {}).get("options") or []
        check("F64-1 kandidat staf hanya peran berlingkup toko",
              r.status_code == 200 and any(o["id"] == staff_user["id"] for o in opts)
              and all(o["role"] in ("staff_marketing", "pic_toko", "host_live", "cs_staff")
                      for o in opts), f"{len(opts)} kandidat")
        r = requests.post(f"{A}/{aid}", headers=MHJ, timeout=60,
                          json={"staff_ids": [staff_user["id"]],
                                "reason": "uji F6.4 [gate-kpiimpor]"})
        check("F64-2 SPV/Manager meng-assign staf ⇒ 200",
              r.status_code == 200 and (r.json() or {}).get("changed") is True,
              f"status={r.status_code} {str((r.json() or {}).get('message'))[:70]}")
        seen = requests.get(f"{BASE}/api/marketing/accounts", headers=SH, timeout=60).json()
        ids = [x["id"] for x in seen] if isinstance(seen, list) else []
        check("F64-3 staf langsung melihat toko yang di-assign", ids == [aid],
              f"{len(ids)} toko terlihat")
        r = requests.get(f"{BASE}/api/marketing/platform-kpi/summary?account_id={aid}",
                         headers=SH, timeout=60)
        check("F64-4 staf boleh membuka KPI toko yang dipegangnya", r.status_code == 200,
              f"status={r.status_code}")
        r = requests.post(f"{A}/{aid}", headers={**SH, "Content-Type": "application/json"},
                          timeout=60, json={"staff_ids": []})
        check("F64-5 staf mencoba mengubah assignment ⇒ 403", r.status_code == 403,
              f"status={r.status_code}")
        mgr_user = db.users.find_one({"email": MGR["email"]}, {"_id": 0, "id": 1})
        r = requests.post(f"{A}/{aid}", headers=MHJ, timeout=60,
                          json={"staff_ids": [mgr_user["id"]]})
        check("F64-6 assign peran yang sudah melihat semua toko ⇒ 400 (tidak ada artinya)",
              r.status_code == 400, f"status={r.status_code} {str(r.text)[:90]}")
        r = requests.post(f"{A}/{aid}", headers=MHJ, timeout=60,
                          json={"staff_ids": [], "reason": "uji unassign [gate-kpiimpor]"})
        check("F64-7 unassign ⇒ 200 dan tercatat", r.status_code == 200
              and (r.json() or {}).get("changed") is True, f"status={r.status_code}")
        r = requests.get(f"{BASE}/api/marketing/platform-kpi/summary?account_id={aid}",
                         headers=SH, timeout=60)
        check("F64-8 staf yang dicabut LANGSUNG kehilangan akses ⇒ 403",
              r.status_code == 403, f"status={r.status_code}")
        r = requests.get(f"{A}/{aid}/history", headers=MHJ, timeout=60)
        rows = (r.json() or {}).get("rows") or []
        assign_log = next((x for x in rows if x.get("action") == "assign_staff"), None)
        check("F64-9 jejak memuat daftar LAMA & BARU + pelaku + alasan",
              bool(assign_log) and "assigned_staff" in (assign_log.get("before") or {})
              and bool(assign_log.get("actor_role")) and bool(assign_log.get("reason")),
              f"{len(rows)} baris jejak · pelaku={(assign_log or {}).get('actor_name')} "
              f"({(assign_log or {}).get('actor_role')})")
        r = requests.get(f"{A}/overview", headers=MHJ, timeout=60)
        check("F64-10 layar Assign Toko bisa membaca daftar toko + pemegangnya",
              r.status_code == 200 and (r.json() or {}).get("rows") is not None
              and (r.json() or {}).get("can_edit") is True,
              f"status={r.status_code} {len((r.json() or {}).get('rows') or [])} toko")
    finally:
        db.marketing_platform_accounts.update_one(
            {"id": aid}, {"$set": {"assigned_staff": before_staff}})

    # ── 6. F7.4 SCORECARD KREATOR ─────────────────────────────────────────────
    print(f"\n{Y}[F7.4] SCORECARD KREATOR — TARGET vs PENCAPAIAN{X}")
    # Target kreator bulan ini mungkin ADA dan dipakai sungguhan. Test menyimpan
    # salinannya lalu memulihkannya di akhir — gate tidak boleh menghapus data kerja.
    target_backup = db.marketing_creator_targets.find_one(
        {"creator_id": creator["id"], "year": 2026, "month": 8})
    r = requests.post(f"{BASE}/api/marketing/targets/creator", headers=MHJ, timeout=60,
                      json={"creator_id": creator["id"], "year": 2026, "month": 8,
                            "revenue_target": 10_000_000, "sessions_target": 10,
                            "viewers_target": 5000})
    check("F74-1 target kreator bisa ditetapkan manager ⇒ 200", r.status_code == 200,
          f"status={r.status_code}")
    r = requests.get(f"{BASE}/api/marketing/targets/creator/scorecard?year=2026&month=8",
                     headers=MHJ, timeout=120)
    j = r.json() if r.status_code == 200 else {}
    row = next((x for x in (j.get("rows") or []) if x["creator_id"] == creator["id"]), None)
    if check("F74-2 scorecard memuat baris kreator uji", bool(row),
             f"status={r.status_code} {len(j.get('rows') or [])} baris"):
        a, ach = row["actual"], row["achievement"]
        check("F74-3 target vs pencapaian dihitung (persen, bukan diketik)",
              row["target"]["revenue"] == 10_000_000 and ach["primary_pct"] is not None,
              f"target Rp10.000.000 · pencapaian {ach['primary_pct']}% "
              f"(basis {ach['primary_basis']})")
        check("F74-4 tiga sumber uang DIPISAH (pesanan · sesi · GMV KPI)",
              all(k in a for k in ("order_revenue", "session_revenue", "gmv_kpi"))
              and a["gmv_kpi"] >= 6_000_000,
              f"pesanan Rp{a['order_revenue']:,.0f} · sesi Rp{a['session_revenue']:,.0f} "
              f"· GMV KPI Rp{a['gmv_kpi']:,.0f}".replace(",", "."))
        check("F74-5 basis penilaian TERTULIS + cakupan KPI dilaporkan",
              ach["primary_basis"] in ("orders", "sessions", "gmv_kpi", "none")
              and a.get("kpi_coverage_pct") is not None,
              f"basis={ach['primary_basis']} cakupan KPI {a['kpi_coverage_pct']}%")
        check("F74-6 konten kreator terhitung (jumlah konten & views)",
              a["contents"] >= 1 and a["views"] >= 10000,
              f"{a['contents']} konten · {a['views']:.0f} views")
    notes = " ".join(j.get("data_notes") or [])
    check("F74-7 catatan kejujuran: tiga angka tidak boleh dijumlah",
          "tidak dijumlah" in notes and "beberapa kali" in notes, notes[:110])
    r = requests.get(f"{BASE}/api/marketing/targets/creator/scorecard?year=2026&month=8",
                     headers=SH, timeout=120)
    check("F74-8 staf tanpa toko: scorecard tetap 200 tapi KOSONG (bukan 500)",
          r.status_code == 200, f"status={r.status_code}")

    # ── bersih-bersih data uji ────────────────────────────────────────────────
    db.marketing_content_calendar.delete_many({"published_url": {"$regex": "UJI-F72"}})
    db.marketing_content_calendar.delete_many({"id": "uji-f72-konten-lama"})
    db.marketing_creator_targets.delete_many({"creator_id": creator["id"], "year": 2026,
                                              "month": 8})
    if creator_temp:
        db.marketing_kol_creators.delete_many({"created_by": "gate_kpiimpor"})
    if target_backup:
        db.marketing_creator_targets.insert_one(target_backup)
    # CACAT YANG DITUTUP 2026-08-14: baris ini dulu berbunyi
    #   delete_many({"account_id": aid, "entity": "marketing_platform_accounts"})
    # yang berarti SETIAP kali gate dijalankan, SELURUH riwayat "siapa memegang
    # toko ini" milik toko NYATA (toko uji = toko shopee aktif pertama) ikut
    # musnah. Padahal justru jejak itu satu-satunya jawaban untuk "siapa yang
    # mencabut akses toko saya?" — dan layar Assign Toko membacanya. Sekarang
    # hanya baris bertanda gate (lihat alasan "[gate-kpiimpor]") yang dihapus.
    db.marketing_change_log.delete_many({"account_id": aid,
                                         "entity": "marketing_platform_accounts",
                                         "reason": {"$regex": r"\[gate-kpiimpor\]"}})
    # HANYA dokumen bertanda gate — JANGAN pernah menghapus per account_id lagi
    # (itu memusnahkan KPI/iklan hasil impor staf; lihat catatan pemilihan toko uji).
    tag_gate_docs()
    db[KPI_COL].delete_many({"_gate_kpiimpor": True})
    db.marketing_ads_data.delete_many({"_gate_kpiimpor": True})
    print("    data uji dibersihkan (KPI, iklan, konten, target, jejak)")

    good = sum(1 for _, o, _ in RES if o)
    color = G if good == len(RES) else R
    print(f"\n{B}{'=' * 88}{X}\nRINGKAS F7.2 + F6.4 + F7.4: {color}{good}/{len(RES)} PASS{X}")
    for n, o, d in RES:
        if not o:
            print(f"  {R}GAGAL{X} {n} — {d}")
    print(f"{B}{'=' * 88}{X}")
    return 0 if good == len(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
