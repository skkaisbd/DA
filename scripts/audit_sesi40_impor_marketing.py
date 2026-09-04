"""AUDIT SESI #40 — Portal Marketing: impor → pratinjau → commit → UNDO, ujung ke ujung.

READ + WRITE terukur, tetapi **membersihkan artefaknya sendiri** (rollback + hapus sesi).
Dipakai untuk MENGUKUR, bukan memperbaiki: setiap temuan dicetak sebagai TEMUAN.

Jalankan: `cd /app && python3 scripts/audit_sesi40_impor_marketing.py`
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime

import requests
from pymongo import MongoClient

BASE = os.environ.get("BASE") or "http://localhost:8001"
SAMPLES = "/app/samples/marketplace_2026"
MONGO = os.environ["MONGO_URL"] if "MONGO_URL" in os.environ else None
if not MONGO:
    for line in open("/app/backend/.env"):
        if line.startswith("MONGO_URL="):
            MONGO = line.split("=", 1)[1].strip().strip('"')
        if line.startswith("DB_NAME="):
            os.environ["DB_NAME"] = line.split("=", 1)[1].strip().strip('"')
DB = MongoClient(MONGO)[os.environ.get("DB_NAME", "test_database")]

OK, FIND = [], []


def ok(code, msg):
    OK.append(code)
    print(f"  \033[92m✓ {code}\033[0m {msg}")


def bad(code, msg):
    FIND.append((code, msg))
    print(f"  \033[91m✗ {code}\033[0m {msg}")


def head(t):
    print(f"\n\033[96m\033[1m▶ {t}\033[0m")


tok = requests.post(f"{BASE}/api/auth/login",
                    json={"email": "admin@garment.com", "password": "Admin@123"},
                    timeout=30).json()
H = {"Authorization": f"Bearer {tok.get('access_token') or tok.get('token')}"}


def api(method, path, **kw):
    return requests.request(method, f"{BASE}{path}", headers=H, timeout=180, **kw)


def upload(fname, source_type, account_id):
    with open(os.path.join(SAMPLES, fname), "rb") as fh:
        raw = fh.read()
    r = api("POST", "/api/marketing/data-import/upload",
            files={"file": (fname, io.BytesIO(raw))},
            data={"source_type": source_type, "account_id": account_id})
    return r


def je_count():
    return DB.rahaza_journal_entries.count_documents({})


ACC_SHOPEE = None
ACC_TIKTOK = None
for a in api("GET", "/api/marketing/accounts").json():
    if a.get("platform") == "shopee" and "DEMO" in (a.get("account_name") or ""):
        ACC_SHOPEE = a
    if a.get("platform") == "tiktokshop" and "DEMO" in (a.get("account_name") or ""):
        ACC_TIKTOK = a
if not (ACC_SHOPEE and ACC_TIKTOK):
    print("TIDAK BISA DIUKUR: akun toko DEMO tidak ada")
    sys.exit(2)
print(f"toko uji: {ACC_SHOPEE['account_name']} · {ACC_TIKTOK['account_name']}")

sessions_made = []

# ══════════════════════════════════════════════════════════════════════════════
head("A — DETEKSI JENIS untuk 7 berkas ASLI pemilik (tidak boleh 5xx / salah platform)")
DETECT_EXPECT = {
    "order_pesanan_shopee.xlsx": "shopee",
    "pesanan_tiktok.xlsx": "tiktok",
    "ads_shopee.csv": "shopee",
    "ads_shopee_keseluruhan.csv": "shopee",
    "ads_tiktok.xlsx": "tiktok",
    "retur_refund_shopee.xls": "shopee",
    "retur_refund_tiktok.xlsx": "tiktok",
}
detected = {}
for fn, plat in DETECT_EXPECT.items():
    with open(os.path.join(SAMPLES, fn), "rb") as fh:
        raw = fh.read()
    r = api("POST", "/api/marketing/data-import/detect",
            files={"file": (fn, io.BytesIO(raw))})
    if r.status_code != 200:
        bad(f"A-{fn}", f"deteksi menjawab HTTP {r.status_code}: {r.text[:200]}")
        continue
    d = r.json()
    best = (d.get("best") or {})
    detected[fn] = best.get("source_type")
    got_plat = (d.get("platform") or {}).get("platform") or ""
    if plat not in got_plat:
        bad(f"A-{fn}", f"platform terdeteksi '{got_plat}', diharap mengandung '{plat}'")
    elif not best.get("source_type"):
        bad(f"A-{fn}", "tidak ada usulan jenis impor sama sekali")
    elif not d.get("row_count"):
        # SESI #40 — berkas ekspor pemilik ini memang KOSONG (46 kolom, 0 baris).
        # Sejak INV-F45 (F45-11) layar MEMPERINGATKANNYA di panel deteksi sebelum
        # tombol Unggah ditekan, jadi ini bukan lagi temuan.
        ok(f"A-{fn}", f"usulan={best.get('source_type')} · berkas memang 0 baris "
                      f"({len(d.get('headers') or [])} kolom) — dilaporkan "
                      f"`row_count=0` dan layar memperingatkan (INV-F45 F45-11)")
    else:
        ok(f"A-{fn}", f"platform={got_plat} · usulan={best.get('source_type')} "
                      f"(skor {best.get('score')}) · {d.get('row_count')} baris")

# ══════════════════════════════════════════════════════════════════════════════
head("B — EKSPOR A (pesanan marketplace): upload → pratinjau → commit → rekap turunan")
je0 = je_count()
r = upload("order_pesanan_shopee.xlsx", "marketplace_orders", ACC_SHOPEE["id"])
if r.status_code != 200:
    bad("B1", f"upload gagal HTTP {r.status_code}: {r.text[:300]}")
    sid_a = None
else:
    s = r.json()
    sess = s.get("session") or {}
    sid_a = sess.get("id")
    sessions_made.append(sid_a)
    rep = sess.get("mapping_report") or {}
    if rep.get("ready"):
        ok("B1", f"pemetaan otomatis SIAP ({sess.get('total_rows')} baris berkas)")
    else:
        bad("B1", f"pemetaan otomatis TIDAK siap; wajib belum terpetakan: "
                  f"{rep.get('missing_required')} · report={list(rep.keys())}")

plan = None
if sid_a:
    rp = api("GET", f"/api/marketing/data-import/sessions/{sid_a}/plan")
    if rp.status_code != 200:
        bad("B2", f"pratinjau (plan) HTTP {rp.status_code}: {rp.text[:200]}")
    else:
        plan = rp.json()
        c = plan.get("counts") or {}
        ok("B2", f"pratinjau: {c.get('baru')} baru · {c.get('diperbarui')} perbarui · "
                 f"{c.get('ditolak')} ditolak · penghalang={plan.get('blockers')}")

    rc = api("POST", f"/api/marketing/data-import/sessions/{sid_a}/commit", json={})
    if rc.status_code != 200:
        bad("B3", f"commit HTTP {rc.status_code}: {rc.text[:300]}")
        res_a = {}
    else:
        res_a = rc.json()
        ok("B3", f"commit: {res_a.get('inserted')} masuk · {res_a.get('updated')} diperbarui "
                 f"· {res_a.get('rejected')} ditolak · rekap={res_a.get('daily_rollup')}")
        n_db = DB.marketing_orders.count_documents({"_import_session_id": sid_a})
        if n_db != res_a.get("inserted"):
            bad("B4", f"laporan commit {res_a.get('inserted')} baris, di DB {n_db}")
        else:
            ok("B4", f"jumlah yang dilaporkan = jumlah di DB ({n_db})")
        je1 = je_count()
        if je1 != je0:
            bad("B5", f"impor PENJUALAN HARIAN melahirkan {je1 - je0} jurnal GL "
                      f"(hanya pencairan yang boleh berjurnal)")
        else:
            ok("B5", "impor pesanan TIDAK melahirkan jurnal GL (benar)")
        rr = (res_a.get("daily_rollup") or {})
        if res_a.get("inserted") and not rr:
            bad("B6", "tidak ada rekap harian turunan yang dihitung padahal ada pesanan masuk")
        elif rr:
            ok("B6", f"rekap harian turunan dihitung: {rr}")

# ══════════════════════════════════════════════════════════════════════════════
head("C — EKSPOR C (retur/refund) di atas pesanan yang ada: update_only + UNDO")
sid_c = None
r = upload("retur_refund_tiktok.xlsx", "marketplace_fulfillment", ACC_SHOPEE["id"])
if r.status_code != 200:
    bad("C1", f"upload Ekspor C gagal HTTP {r.status_code}: {r.text[:300]}")
else:
    s = r.json()
    sid_c = (s.get("session") or {}).get("id")
    sessions_made.append(sid_c)
    rep = (s.get("session") or {}).get("mapping_report") or {}
    (ok if rep.get("ready") else bad)(
        "C1", f"pemetaan Ekspor C ready={rep.get('ready')} "
              f"missing={rep.get('missing_required')}")

before_status = {}
if sid_c:
    rc = api("POST", f"/api/marketing/data-import/sessions/{sid_c}/commit", json={})
    if rc.status_code != 200:
        bad("C2", f"commit Ekspor C HTTP {rc.status_code}: {rc.text[:300]}")
    else:
        res_c = rc.json()
        ok("C2", f"commit Ekspor C: {res_c.get('updated')} diperbarui · "
                 f"{res_c.get('rejected')} ditolak · undo_count={res_c.get('undo_count')}")
        if res_c.get("inserted"):
            bad("C3", f"jenis update_only MEMBUAT {res_c.get('inserted')} baris baru")
        else:
            ok("C3", "jenis update_only tidak membuat baris baru (benar)")
        if res_c.get("updated") and not res_c.get("undo_count"):
            bad("C4", f"{res_c.get('updated')} baris diubah tetapi 0 jejak UNDO tersimpan "
                      f"⇒ tombol 'Batalkan impor' tidak akan bisa memulihkan")
        elif res_c.get("updated"):
            ok("C4", f"jejak UNDO tersimpan untuk {res_c.get('undo_count')} baris")

        # UNDO
        rb = api("POST", f"/api/marketing/data-import/sessions/{sid_c}/rollback")
        if rb.status_code != 200:
            bad("C5", f"rollback Ekspor C HTTP {rb.status_code}: {rb.text[:300]}")
        else:
            rest = rb.json().get("restore") or {}
            ok("C5", f"rollback: dipulihkan={rest.get('restored')} · "
                     f"hanya field={rest.get('fields_only')} · "
                     f"hilang={rest.get('missing')} · pesan={rb.json().get('message')}")
            pend = DB.marketing_data_import_undo.count_documents(
                {"session_id": sid_c, "restored_at": None})
            if pend:
                bad("C6", f"{pend} jejak UNDO masih menggantung sesudah rollback")
            else:
                ok("C6", "semua jejak UNDO ditandai sudah dipulihkan")
            rb2 = api("POST", f"/api/marketing/data-import/sessions/{sid_c}/rollback")
            if rb2.status_code == 400 and "sudah dibatalkan" in rb2.text:
                ok("C7", "rollback kedua ditolak dengan pesan yang benar (idempoten)")
            else:
                bad("C7", f"rollback kedua menjawab {rb2.status_code}: {rb2.text[:200]}")

# ══════════════════════════════════════════════════════════════════════════════
head("D — IMPOR IKLAN dua kali (mode perbarui) → UNDO harus memulihkan nilai lama")
sid_d1 = sid_d2 = None
r = upload("ads_shopee.csv", "shopee_ads_cpc", ACC_SHOPEE["id"])
if r.status_code != 200:
    bad("D1", f"upload iklan #1 HTTP {r.status_code}: {r.text[:300]}")
else:
    sid_d1 = (r.json().get("session") or {}).get("id")
    sessions_made.append(sid_d1)
    rc = api("POST", f"/api/marketing/data-import/sessions/{sid_d1}/commit", json={})
    if rc.status_code != 200:
        bad("D1", f"commit iklan #1 HTTP {rc.status_code}: {rc.text[:300]}")
    else:
        ok("D1", f"commit iklan #1: {rc.json().get('inserted')} masuk · "
                 f"{rc.json().get('updated')} diperbarui")

if sid_d1:
    r = upload("ads_shopee.csv", "shopee_ads_cpc", ACC_SHOPEE["id"])
    sid_d2 = (r.json().get("session") or {}).get("id") if r.status_code == 200 else None
    if not sid_d2:
        bad("D2", f"upload iklan #2 HTTP {r.status_code}: {r.text[:200]}")
    else:
        sessions_made.append(sid_d2)
        rc = api("POST", f"/api/marketing/data-import/sessions/{sid_d2}/commit",
                 json={"on_duplicate": "update"})
        if rc.status_code != 200:
            bad("D2", f"commit iklan #2 HTTP {rc.status_code}: {rc.text[:300]}")
        else:
            res = rc.json()
            ok("D2", f"commit iklan #2: {res.get('inserted')} masuk · "
                     f"{res.get('updated')} diperbarui · undo_count={res.get('undo_count')}")
            if res.get("updated") and not res.get("undo_count"):
                bad("D3", "impor ulang menimpa baris tanpa menyimpan jejak UNDO")
            elif res.get("updated"):
                ok("D3", "impor ulang menyimpan jejak UNDO")
            rb = api("POST", f"/api/marketing/data-import/sessions/{sid_d2}/rollback")
            if rb.status_code != 200:
                bad("D4", f"rollback iklan #2 HTTP {rb.status_code}: {rb.text[:200]}")
            else:
                m = rb.json().get("message") or ""
                if "tidak ada yang perlu dibatalkan" in m and res.get("updated"):
                    bad("D4", "rollback membantah perubahan yang baru saja ia lakukan: " + m)
                else:
                    ok("D4", f"rollback iklan #2: {m}")

# ══════════════════════════════════════════════════════════════════════════════
head("E — UNDO Ekspor A: pesanan hilang lagi & rekap harian turunan ikut turun")
if sid_a:
    dates_before = list(DB.marketing_sales_data.find(
        {"account_id": ACC_SHOPEE["id"], "is_derived": True},
        {"_id": 0, "date": 1, "revenue": 1}).limit(5))
    rb = api("POST", f"/api/marketing/data-import/sessions/{sid_a}/rollback")
    if rb.status_code != 200:
        bad("E1", f"rollback Ekspor A HTTP {rb.status_code}: {rb.text[:300]}")
    else:
        j = rb.json()
        left = DB.marketing_orders.count_documents({"_import_session_id": sid_a})
        if left:
            bad("E1", f"{left} pesanan hasil impor masih ada sesudah rollback")
        else:
            ok("E1", f"semua pesanan sesi ini dihapus ({j.get('deleted')} baris) · "
                     f"rekap={j.get('daily_rollup')}")
        if j.get("deleted") and not j.get("daily_rollup"):
            bad("E2", "rekap harian turunan TIDAK dihitung ulang sesudah rollback "
                      "⇒ omzet dari pesanan yang sudah tidak ada masih terbaca")
        else:
            ok("E2", "rekap harian turunan ikut dihitung ulang sesudah rollback")

# ══════════════════════════════════════════════════════════════════════════════
head("F — RIWAYAT & laporan UNDO bisa dibaca lagi (bukan hanya toast)")
for sid, label in [(sid_a, "Ekspor A"), (sid_c, "Ekspor C"), (sid_d2, "iklan #2")]:
    if not sid:
        continue
    r = api("GET", f"/api/marketing/data-import/sessions/{sid}/undo-report")
    if r.status_code != 200:
        bad(f"F-{label}", f"undo-report HTTP {r.status_code}")
    else:
        d = r.json()
        ok(f"F-{label}", f"status={d.get('status')} undo={d.get('undo_count')} "
                         f"pending={d.get('undo_pending')} restored={d.get('undo_restored')} "
                         f"dibatalkan={d.get('rolled_back_at')}")
r = api("GET", "/api/marketing/data-import/history?page=1&page_size=5")
if r.status_code != 200:
    bad("F-hist", f"riwayat impor HTTP {r.status_code}")
else:
    ok("F-hist", f"riwayat impor: total {r.json().get('pagination', {}).get('total')}")

# ══════════════════════════════════════════════════════════════════════════════
head("G — bersih-bersih artefak audit")
for sid in [s for s in sessions_made if s]:
    s = DB.marketing_data_import_sessions.find_one({"id": sid}, {"_id": 0, "status": 1})
    if s and s.get("status") == "committed":
        api("POST", f"/api/marketing/data-import/sessions/{sid}/rollback")
    DB.marketing_data_import_sessions.delete_one({"id": sid})
    DB.marketing_data_import_undo.delete_many({"session_id": sid})
leftover = DB.marketing_orders.count_documents(
    {"_import_session_id": {"$in": [s for s in sessions_made if s]}})
leftover += DB.marketing_ads_data.count_documents(
    {"_import_session_id": {"$in": [s for s in sessions_made if s]}})
(ok if leftover == 0 else bad)("G1", f"sisa dokumen artefak audit = {leftover}")

print("\n" + "=" * 78)
print(f"HASIL AUDIT: {len(OK)} OK · {len(FIND)} TEMUAN")
for c, m in FIND:
    print(f"  TEMUAN {c}: {m}")
print("=" * 78)
sys.exit(0)
