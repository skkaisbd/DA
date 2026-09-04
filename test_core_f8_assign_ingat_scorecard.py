#!/usr/bin/env python3
"""test_core_f8_assign_ingat_scorecard.py — CORE TEST **F8**: tiga janji layar.

═══════════════════════════════════════════════════════════════════════════════
APA YANG DIBUKTIKAN (dan kenapa justru itu yang diuji)
═══════════════════════════════════════════════════════════════════════════════

**[A] ASSIGN TOKO (SPV).** Endpoint & layarnya sudah ada sejak F6.4, tetapi tiga
janjinya belum dijaga apa pun:

* `A-1` **Alasan wajib.** Kepala berkasnya menulis "setiap simpan wajib membawa
  alasan singkat" — padahal `reason` opsional. Jejak boleh lahir tanpa sebab, dan
  satu-satunya pertanyaan yang benar-benar ditanyakan staf ("kenapa akses toko
  saya dicabut?") tetap tidak terjawab walau riwayatnya lengkap.
* `A-2` **Jejak tidak boleh dimusnahkan gate.** `test_core_f7_kpi_impor.py` dulu
  membersihkan diri dengan
  ``delete_many({"account_id": aid, "entity": "marketing_platform_accounts"})``
  — yang berarti SETIAP kali gate dijalankan, SELURUH riwayat pemegang toko NYATA
  ikut hilang. Gate yang menghapus bukti adalah cacat, bukan kebersihan.
* `A-3` **Sudut pandang per ORANG & staf nonaktif.** Rotasi shift ditanyakan per
  orang ("Rina pegang toko apa?"), dan staf yang memegang 0 toko tidak muncul di
  mana pun pada daftar per-toko — padahal justru dia yang melihat layar kosong.
  Toko yang seluruh pemegangnya berakun NONAKTIF tampak "sudah dipegang".

**[B] INGAT PEMETAAN SAYA.** Mesin impor sudah mengingat pemetaan kolom, tetapi:

* `B-1` **diingat diam-diam** — layar tidak pernah menyebut bahwa pemetaan datang
  dari ingatan, jadi pemetaan yang salah dipakai ulang setiap hari sambil tampak
  "otomatis benar";
* `B-2` **tidak bisa dilupakan** — satu kesalahan yang pernah di-commit terpasang
  otomatis selamanya, tanpa jalan keluar di aplikasi;
* `B-3` **pemetaan basi diterima** — field yang sudah tidak ada di skema dulu
  dipakai apa adanya ⇒ kolomnya hilang dari hasil tanpa satu pun galat.

**[C] SCORECARD KREATOR.** Angkanya benar, tetapi tidak bisa DITELUSURI: tidak
ada satu pun jalan melihat konten/pesanan/sesi mana yang membentuk satu baris.
Angka yang tidak bisa ditelusuri akan dipercaya atau ditolak tanpa bukti.
`C-*` menjaga: total rincian **sama persis** dengan baris scorecard, tiga sumber
uang **tidak dijumlah**, pesanan yang dikecualikan tetap **tampil beserta
sebabnya**, dan kreator tanpa target ditandai **"belum ada target" (bukan 0%)**.

Semua data uji dibuat & DIBERSIHKAN sendiri (bertanda `QAF8`), jadi gate ini
tidak bergantung pada seed dan tidak meninggalkan sampah.

Pakai:  python3 /app/test_core_f8_assign_ingat_scorecard.py [--keep]
"""
from __future__ import annotations

import io
import csv
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
IMPORT_API = f"{BASE}/api/marketing/data-import"
ASSIGN_API = f"{BASE}/api/marketing/account-assign"
TARGET_API = f"{BASE}/api/marketing/targets"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []

MARK = "QAF8"
CRE_A = f"{MARK}-KRE-A"
CRE_B = f"{MARK}-KRE-B"


def check(name: str, cond: bool, detail: str = "") -> bool:
    RES.append((name, bool(cond), detail))
    print(f"  {G}PASS{X}  {name}" if cond else f"  {R}FAIL{X}  {name}",
          f"— {detail}" if detail else "")
    return bool(cond)


def bad(name: str, detail: str) -> None:
    check(name, False, detail)


def login() -> str:
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


def csv_bytes(header: list, rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# [A] ASSIGN TOKO
# ═══════════════════════════════════════════════════════════════════════════════
def section_assign(JH: dict, db, account: dict, staff: dict) -> None:
    print(f"\n{Y}[A] ASSIGN TOKO — alasan wajib · jejak tak boleh musnah · per-staf{X}")
    aid = account["id"]
    before = list((db.marketing_platform_accounts.find_one(
        {"id": aid}, {"_id": 0, "assigned_staff": 1}) or {}).get("assigned_staff") or [])
    try:
        # ── A-1 alasan WAJIB ─────────────────────────────────────────────────
        r = requests.post(f"{ASSIGN_API}/{aid}", headers=JH, timeout=60,
                          json={"staff_ids": [staff["id"]]})
        check("A-1a simpan TANPA alasan ⇒ 400 (bukan diterima diam-diam)",
              r.status_code == 400, f"HTTP {r.status_code} {str(r.text)[:110]}")
        check("A-1b pesan galat MENYEBUT alasan + contoh yang bisa dipakai",
              "alasan" in (r.text or "").lower() and "rotasi" in (r.text or "").lower(),
              str(r.text)[:140])
        r = requests.post(f"{ASSIGN_API}/{aid}", headers=JH, timeout=60,
                          json={"staff_ids": [staff["id"]], "reason": "abc"})
        check("A-1c alasan terlalu pendek ('abc') ⇒ 400", r.status_code == 400,
              f"HTTP {r.status_code}")

        # ── A-2 assign sah + jejak ───────────────────────────────────────────
        r = requests.post(f"{ASSIGN_API}/{aid}", headers=JH, timeout=60,
                          json={"staff_ids": [staff["id"]],
                                "reason": f"uji {MARK} rotasi shift"})
        j = r.json() if r.status_code == 200 else {}
        check("A-2a assign dengan alasan ⇒ 200 & berubah",
              r.status_code == 200 and j.get("changed") is True,
              f"HTTP {r.status_code} {str(j.get('message'))[:80]}")
        check("A-2b hasil menyebut EFEK-nya (staf dicabut langsung 403)",
              bool(j.get("effect_note")), str(j.get("effect_note"))[:90])
        r = requests.get(f"{ASSIGN_API}/history?page_size=5", headers=JH, timeout=60)
        rows = (r.json() or {}).get("rows") or []
        mine = next((x for x in rows if MARK in str(x.get("reason") or "")), None)
        check("A-2c riwayat GLOBAL (semua toko) memuat perubahan tadi",
              r.status_code == 200 and bool(mine),
              f"{len(rows)} baris · total={(r.json() or {}).get('total')}")
        check("A-2d baris riwayat memuat nama TOKO + nama staf ditambah/dicabut",
              bool(mine) and bool(mine.get("account_name"))
              and isinstance(mine.get("added_names"), list),
              f"toko={(mine or {}).get('account_name')} "
              f"+{(mine or {}).get('added_names')} -{(mine or {}).get('removed_names')}")

        # ── A-2e GATE TIDAK BOLEH MEMUSNAHKAN JEJAK ──────────────────────────
        # Penjaga statik: pembersihan gate F7.2 harus menyaring penanda gate,
        # bukan menghapus seluruh jejak toko itu. Bug ini pernah NYATA: satu kali
        # `bash scripts/gate.sh` menghapus semua riwayat pemegang toko demo.
        src = open("/app/test_core_f7_kpi_impor.py", encoding="utf-8").read()
        dels = re.findall(r"marketing_change_log\.delete_many\(([^;]*?)\)\n", src,
                          re.S)
        unsafe = [d for d in dels if "reason" not in d]
        check("A-2e gate F7.2 hanya menghapus jejak BERTANDA gate "
              "(tidak memusnahkan riwayat toko nyata)",
              bool(dels) and not unsafe,
              f"{len(dels)} pembersihan · tanpa filter alasan: {len(unsafe)}")

        # ── A-3 per-staf + staf nonaktif + ringkasan ─────────────────────────
        r = requests.get(f"{ASSIGN_API}/by-staff", headers=JH, timeout=60)
        js = r.json() or {}
        srow = next((x for x in (js.get("rows") or []) if x["id"] == staff["id"]), None)
        check("A-3a tampilan PER-STAF menyebut toko yang dipegangnya",
              r.status_code == 200 and bool(srow)
              and any(a["id"] == aid for a in (srow or {}).get("accounts") or []),
              f"{len(js.get('rows') or [])} staf · "
              f"{(srow or {}).get('accounts_count')} toko untuk {staff.get('name')}")
        check("A-3b staf yang memegang 0 toko tetap terdaftar (dia yang melihat "
              "layar kosong)",
              isinstance(js.get("without_account"), list),
              f"tanpa toko: {js.get('without_account')}")
        db.users.update_one({"id": staff["id"]}, {"$set": {"status": "inactive"}})
        r = requests.post(f"{ASSIGN_API}/{aid}", headers=JH, timeout=60,
                          json={"staff_ids": [staff["id"]],
                                "reason": f"uji {MARK} staf nonaktif"})
        w = (r.json() or {}).get("warnings") or []
        check("A-3c meng-assign staf berakun NONAKTIF ⇒ diberi PERINGATAN "
              "(bukan diam-diam dianggap terpegang)",
              r.status_code == 200 and any("NONAKTIF" in str(x) for x in w),
              f"HTTP {r.status_code} warnings={[str(x)[:70] for x in w]}")
        r = requests.get(f"{ASSIGN_API}/overview", headers=JH, timeout=60)
        jo = r.json() or {}
        check("A-3d ringkasan menghitung toko yang pemegangnya semua NONAKTIF "
              "sebagai belum terpegang",
              r.status_code == 200 and (jo.get("stale_count") or 0) >= 1,
              f"belum terpegang={jo.get('unassigned_count')} "
              f"pemegang nonaktif={jo.get('stale_count')}")
        db.users.update_one({"id": staff["id"]}, {"$set": {"status": "active"}})
        r = requests.post(f"{ASSIGN_API}/{aid}", headers=JH, timeout=60,
                          json={"staff_ids": [], "reason": f"uji {MARK} cabut"})
        jw = (r.json() or {}).get("warnings") or []
        check("A-3e mencabut SEMUA staf ⇒ peringatan 'toko tidak dipegang siapa pun'",
              r.status_code == 200 and any("TIDAK dipegang" in str(x) for x in jw),
              f"warnings={[str(x)[:70] for x in jw]}")
    finally:
        db.marketing_platform_accounts.update_one(
            {"id": aid}, {"$set": {"assigned_staff": before}})
        db.users.update_one({"id": staff["id"]}, {"$set": {"status": "active"}})


# ═══════════════════════════════════════════════════════════════════════════════
# [B] INGAT PEMETAAN SAYA
# ═══════════════════════════════════════════════════════════════════════════════
def section_memory(H: dict, JH: dict, db, account: dict) -> list:
    print(f"\n{Y}[B] INGAT PEMETAAN — asal-usul terlihat · bisa dilupakan · "
          f"pemetaan basi ditolak{X}")
    stype = "product_launches"
    head = ["Nama Produk", "Tanggal Launch", f"Kolom Ngawur {MARK}"]
    rows = [[f"{MARK} Kaos Uji", "2026-08-05", "abaikan"],
            [f"{MARK} Hoodie Uji", "2026-08-07", "abaikan"]]
    sessions: list = []

    def upload(fname: str):
        r = requests.post(f"{IMPORT_API}/upload", headers=H, timeout=180,
                          files={"file": (fname, csv_bytes(head, rows), "text/csv")},
                          data={"source_type": stype, "account_id": account["id"]})
        if r.status_code == 200:
            sid = r.json()["session"]["id"]
            sessions.append(sid)
            return r.json()["session"], sid
        return None, None

    s1, sid1 = upload(f"{MARK}_launch_1.csv")
    if not s1:
        bad("B-0 unggah berkas uji", "upload gagal")
        return sessions
    check("B-1a berkas dengan susunan kolom BARU: belum ada ingatan",
          s1.get("format_known") is False and s1.get("format_memory") in (None, {}),
          f"known={s1.get('format_known')} memory={s1.get('format_memory')}")
    fp = s1.get("format_fingerprint")
    rc = requests.post(f"{IMPORT_API}/sessions/{sid1}/commit", headers=JH, timeout=180,
                       json={"on_duplicate": "skip"})
    check("B-1b commit berhasil (ingatan disimpan sesudah dikonfirmasi manusia)",
          rc.status_code == 200, f"HTTP {rc.status_code} {str(rc.text)[:110]}")

    r = requests.get(f"{IMPORT_API}/formats?source_type={stype}", headers=JH, timeout=60)
    fmts = (r.json() or {}).get("formats") or []
    mine = next((f for f in fmts if f["fingerprint"] == fp), None)
    check("B-1c daftar 'susunan kolom yang diingat' bisa DILIHAT staf",
          r.status_code == 200 and bool(mine) and (mine or {}).get("use_count", 0) >= 1,
          f"{len(fmts)} format · use_count={(mine or {}).get('use_count')} "
          f"kolom={(mine or {}).get('columns')}")

    s2, sid2 = upload(f"{MARK}_launch_2.csv")
    mem = (s2 or {}).get("format_memory") or {}
    check("B-2a unggah berkas SAMA: pemetaan dipakai lagi DAN asalnya disebut",
          bool(s2) and s2.get("format_known") is True and bool(mem),
          f"known={(s2 or {}).get('format_known')} "
          f"use_count={mem.get('use_count')} oleh={mem.get('last_used_by')}")
    check("B-2b ingatan menyebut DIPAKAI BERAPA KALI & TERAKHIR OLEH SIAPA "
          "(bukan 'entah kenapa sudah terpetakan')",
          bool(mem.get("last_used_by")) and mem.get("use_count", 0) >= 1,
          f"{mem.get('use_count')}× · {mem.get('last_used_by')} · "
          f"{mem.get('last_used_at')}")

    # ── B-3 PEMETAAN BASI: field yang sudah tidak ada di skema ───────────────
    db.marketing_data_import_formats.update_one(
        {"source_type": stype, "fingerprint": fp},
        {"$set": {"mapping.0.field": "field_yang_sudah_dihapus"}})
    s3, sid3 = upload(f"{MARK}_launch_3.csv")
    mem3 = (s3 or {}).get("format_memory") or {}
    mp3 = {m["column"]: m for m in ((s3 or {}).get("mapping") or [])}
    check("B-3a pemetaan tersimpan yang menunjuk field TIDAK ADA dibuang, "
          "kolomnya dipetakan ulang mesin",
          mp3.get("Nama Produk", {}).get("field") == "product_name",
          f"field sekarang={mp3.get('Nama Produk', {}).get('field')}")
    check("B-3b pembuangan itu DILAPORKAN (tidak senyap)",
          any(d.get("field") == "field_yang_sudah_dihapus"
              for d in (mem3.get("dropped") or [])),
          f"dropped={mem3.get('dropped')}")

    # ── B-4 BISA DILUPAKAN ───────────────────────────────────────────────────
    rd = requests.delete(f"{IMPORT_API}/formats/{fp}?source_type={stype}",
                         headers=JH, timeout=60)
    check("B-4a 'Lupakan pemetaan ini' ⇒ 200 + menjelaskan akibatnya",
          rd.status_code == 200 and "DILUPAKAN" in str((rd.json() or {}).get("message")),
          f"HTTP {rd.status_code} {str((rd.json() or {}).get('message'))[:100]}")
    s4, sid4 = upload(f"{MARK}_launch_4.csv")
    check("B-4b sesudah dilupakan, berkas yang sama dipetakan ulang dari nol",
          bool(s4) and s4.get("format_known") is False,
          f"known={(s4 or {}).get('format_known')}")
    rd2 = requests.delete(f"{IMPORT_API}/formats/{fp}?source_type={stype}",
                          headers=JH, timeout=60)
    check("B-4c melupakan dua kali ⇒ 404 dengan alasan yang benar",
          rd2.status_code == 404 and "dilupakan" in str(rd2.text).lower(),
          f"HTTP {rd2.status_code} {str(rd2.text)[:90]}")
    check("B-5 kolom yang tak dikenal TIDAK ikut diingat sebagai terpetakan",
          mp3.get(f"Kolom Ngawur {MARK}", {}).get("field") in (None, ""),
          f"{mp3.get(f'Kolom Ngawur {MARK}')}")
    return sessions


# ═══════════════════════════════════════════════════════════════════════════════
# [C] SCORECARD KREATOR — RINCIAN YANG BISA DITELUSURI
# ═══════════════════════════════════════════════════════════════════════════════
def seed_creator_data(db, account: dict) -> dict:
    """Data uji sendiri: 2 kreator, konten (1 ber-KPI, 1 tanpa), sesi, target, pesanan."""
    now = _now()
    y, m = now.year, now.month
    d1 = f"{y:04d}-{m:02d}-04"
    d2 = f"{y:04d}-{m:02d}-06"
    ids = {"a": str(uuid.uuid4()), "b": str(uuid.uuid4())}
    db.marketing_kol_creators.insert_many([
        {"id": ids["a"], "creator_code": CRE_A, "name": f"{MARK} Kreator Bertarget",
         "status": "active", "platform": "shopee", "_qa": MARK},
        {"id": ids["b"], "creator_code": CRE_B, "name": f"{MARK} Kreator Tanpa Target",
         "status": "active", "platform": "shopee", "_qa": MARK},
    ])
    db.marketing_content_calendar.insert_many([
        {"id": f"{MARK}-c1", "date": d1, "creator_id": ids["a"],
         "account_id": account["id"], "title": f"{MARK} konten ber-KPI",
         "content_type": "video", "status": "posted",
         "published_url": f"https://demo.test/{MARK}-c1",
         "kpi": {"views": 1000, "likes": 100, "comments": 20, "shares": 5,
                 "saves": 10, "orders": 7, "gmv": 3000000},
         "kpi_source": "qa", "kpi_updated_at": now, "_qa": MARK},
        {"id": f"{MARK}-c2", "date": d2, "creator_id": ids["a"],
         "account_id": account["id"], "title": f"{MARK} konten TANPA KPI",
         "content_type": "video", "status": "posted",
         "published_url": f"https://demo.test/{MARK}-c2", "_qa": MARK},
    ])
    db.marketing_creator_sessions.insert_one(
        {"id": f"{MARK}-s1", "date": d1, "creator_id": ids["a"],
         "account_id": account["id"], "session_name": f"{MARK} live",
         "revenue": 2500000, "viewers": 800, "peak_viewers": 900, "orders": 12,
         "duration_minutes": 60, "_qa": MARK})
    db.marketing_creator_targets.insert_one(
        {"id": f"{MARK}-t1", "creator_id": ids["a"], "year": y, "month": m,
         "revenue_target": 10000000, "sessions_target": 2, "viewers_target": 1000,
         "_qa": MARK})
    db.marketing_orders.insert_many([
        {"id": f"{MARK}-o1", "order_id": f"{MARK}-O1", "creator_id": ids["a"],
         "account_id": account["id"], "platform": "shopee", "status": "delivered",
         "order_date": d1, "revenue_product": 4000000, "items": [], "_qa": MARK},
        {"id": f"{MARK}-o2", "order_id": f"{MARK}-O2", "creator_id": ids["a"],
         "account_id": account["id"], "platform": "shopee", "status": "cancelled",
         "order_date": d2, "revenue_product": 1500000, "items": [], "_qa": MARK},
    ])
    return {**ids, "year": y, "month": m}


def section_scorecard(JH: dict, ctx: dict) -> None:
    print(f"\n{Y}[C] SCORECARD KREATOR — angka yang BISA DITELUSURI{X}")
    y, m = ctx["year"], ctx["month"]
    r = requests.get(f"{TARGET_API}/creator/scorecard?year={y}&month={m}",
                     headers=JH, timeout=90)
    if r.status_code != 200:
        bad("C-0 scorecard bisa dibuka", f"HTTP {r.status_code} {r.text[:120]}")
        return
    rows = {x["creator_id"]: x for x in (r.json() or {}).get("rows") or []}
    row_a, row_b = rows.get(ctx["a"]), rows.get(ctx["b"])
    check("C-0 kedua kreator uji muncul di scorecard",
          bool(row_a) and bool(row_b), f"{len(rows)} kreator")
    if not row_a:
        return

    rd = requests.get(f"{TARGET_API}/creator/{ctx['a']}/detail?year={y}&month={m}",
                      headers=JH, timeout=90)
    if rd.status_code != 200:
        bad("C-1 rincian kreator bisa dibuka", f"HTTP {rd.status_code} {rd.text[:120]}")
        return
    det = rd.json() or {}
    t, a = det.get("totals") or {}, row_a["actual"]
    same = {k: (t.get(k), a.get(k)) for k in
            ("order_revenue", "session_revenue", "gmv_kpi", "contents", "posted",
             "with_kpi", "views", "engagement", "viewers", "kpi_coverage_pct")}
    beda = {k: v for k, v in same.items() if round(float(v[0] or 0), 2)
            != round(float(v[1] or 0), 2)}
    check("C-1 TOTAL rincian SAMA PERSIS dengan baris scorecard "
          "(satu sumber angka, bukan dua hitungan)",
          not beda, f"beda={beda}" if beda else
          f"order={t.get('order_revenue')} sesi={t.get('session_revenue')} "
          f"gmv={t.get('gmv_kpi')} konten={t.get('contents')} "
          f"cakupanKPI={t.get('kpi_coverage_pct')}%")
    check("C-2a rincian memuat KETIGA daftar sumber angka",
          all(isinstance(det.get(k), list) for k in ("contents", "orders", "sessions")),
          f"konten={len(det.get('contents') or [])} "
          f"pesanan={len(det.get('orders') or [])} sesi={len(det.get('sessions') or [])}")
    combined = [k for k in t if k in ("total_revenue", "revenue_total", "grand_total",
                                      "omzet_total")]
    check("C-2b TIDAK ADA satu pun angka gabungan tiga sumber "
          "(menjumlahkannya = menghitung satu penjualan 3×)",
          not combined, f"kunci gabungan={combined}")
    o2 = next((o for o in (det.get("orders") or [])
               if o.get("order_id") == f"{MARK}-O2"), None)
    check("C-3 pesanan yang DIKECUALIKAN tetap tampil + sebabnya "
          "(bukan disembunyikan sehingga total tampak kurang)",
          bool(o2) and o2.get("counted") is False and bool(o2.get("why_not_counted")),
          f"{(o2 or {}).get('status')} · dihitung={(o2 or {}).get('counted')} · "
          f"{(o2 or {}).get('why_not_counted')}")
    c2 = next((c for c in (det.get("contents") or [])
               if c.get("id") == f"{MARK}-c2"), None)
    check("C-4 konten TANPA KPI tetap tampil & ditandai (cakupan KPI jadi jujur)",
          bool(c2) and c2.get("has_kpi") is False
          and float(t.get("kpi_coverage_pct") or 0) == 50.0,
          f"cakupan={t.get('kpi_coverage_pct')}% (2 konten, 1 ber-KPI)")
    if row_b:
        check("C-5 kreator TANPA target ditandai 'belum ada target', bukan 0%",
              row_b["achievement"]["status"] == "no_target"
              and row_b["achievement"]["primary_pct"] is None
              and row_b["target"]["revenue"] is None,
              f"status={row_b['achievement']['status']} "
              f"pct={row_b['achievement']['primary_pct']}")
    rb = requests.get(f"{TARGET_API}/creator/{ctx['b']}/detail?year={y}&month={m}",
                      headers=JH, timeout=90)
    check("C-6 rincian kreator tanpa data ⇒ 200 & KOSONG (bukan 500)",
          rb.status_code == 200 and (rb.json() or {}).get("totals", {}).get(
              "order_revenue") == 0,
          f"HTTP {rb.status_code}")
    r404 = requests.get(f"{TARGET_API}/creator/ngawur-{MARK}/detail", headers=JH,
                        timeout=60)
    check("C-7 kreator ngawur ⇒ 404 (bukan 500 / daftar kosong yang menyesatkan)",
          r404.status_code == 404, f"HTTP {r404.status_code}")
    ret = [n for n in (det.get("data_notes") or []) if "returned" in n]
    check("C-8 catatan kejujuran ada di respons (dipakai layar, bukan hanya kode)",
          len(det.get("data_notes") or []) >= 3,
          f"{len(det.get('data_notes') or [])} catatan"
          + (" · termasuk peringatan status 'returned'" if ret else ""))



# ═══════════════════════════════════════════════════════════════════════════════
# [D] IMPOR BERTINDIH (1–7 lalu 5–12) — DUPLIKAT & PERUBAHAN STATUS
# ═══════════════════════════════════════════════════════════════════════════════
def section_overlap(H: dict, JH: dict, db, account: dict) -> list:
    """Pertanyaan pemilik: "kalau saya impor 1–7 lalu 5–12, apakah dobelnya terdeteksi,
    dan kalau baris yang sama berubah jadi dibatalkan apakah otomatis terupdate?"

    Yang dijaga di sini justru bagian yang paling mahal kalau salah: perubahan status
    lewat impor WAJIB melalui mesin status SSOT (reservasi stok dilepas, status tidak
    boleh MUNDUR) — bukan `$set` mentah.
    """
    print(f"\n{Y}[D] IMPOR BERTINDIH — deteksi dobel + status lewat aturan SSOT{X}")
    HEAD = ["Order ID", "Order Status", "SKU ID", "Quantity",
            "SKU Subtotal After Discount", "Created Time", "Purchase Channel"]
    sessions: list = []

    def rows_for(days, status):
        return [[f"{MARK}-OV-{d:02d}", status, "SKU-QAF8", 1, 100000,
                 f"{d:02d}/08/2026 10:00:00", "Shopee"] for d in days]

    def upload(name, days, status):
        r = requests.post(f"{IMPORT_API}/upload", headers=H, timeout=180,
                          files={"file": (name, csv_bytes(HEAD, rows_for(days, status)),
                                          "text/csv")},
                          data={"source_type": "marketplace_orders",
                                "account_id": account["id"]})
        if r.status_code != 200:
            return None, None, None
        j = r.json()
        sessions.append(j["session"]["id"])
        return j["session"]["id"], j.get("duplicates") or {}, j

    sid1, dup1, _ = upload(f"{MARK}_1-7.csv", range(1, 8), "Perlu dikirim")
    if not sid1:
        bad("D-0 unggah berkas tanggal 1–7", "upload gagal")
        return sessions
    check("D-1a berkas pertama: TIDAK ada baris yang sudah ada",
          dup1.get("checked") is True and dup1.get("existing") == 0
          and dup1.get("new") == 7,
          f"sudah ada={dup1.get('existing')} baru={dup1.get('new')} "
          f"kunci={dup1.get('dedupe')}")
    check("D-1b rentang tanggal berkas dilaporkan (bahan pesan di layar)",
          dup1.get("file_date_from") == "2026-08-01"
          and dup1.get("file_date_to") == "2026-08-07",
          f"{dup1.get('file_date_from')} … {dup1.get('file_date_to')}")
    rc = requests.post(f"{IMPORT_API}/sessions/{sid1}/commit", headers=JH, timeout=180,
                       json={"on_duplicate": "skip"})
    check("D-1c commit 1–7 memasukkan 7 pesanan",
          rc.status_code == 200 and (rc.json() or {}).get("inserted") == 7,
          f"HTTP {rc.status_code} masuk={(rc.json() or {}).get('inserted')}")

    # ── berkas kedua 5–12, dan baris 5–7 statusnya berubah jadi DIBATALKAN ──
    sid2, dup2, _ = upload(f"{MARK}_5-12.csv", range(5, 13), "Dibatalkan")
    check("D-2a berkas kedua (5–12): 3 baris DIKENALI sudah ada, 5 baru — "
          "deteksi per BARIS (kunci dedupe), bukan per rentang tanggal",
          dup2.get("existing") == 3 and dup2.get("new") == 5,
          f"sudah ada={dup2.get('existing')} baru={dup2.get('new')}")
    check("D-2b rentang tanggal yang BERTINDIH disebut (5–7 Agu)",
          dup2.get("overlap_date_from") == "2026-08-05"
          and dup2.get("overlap_date_to") == "2026-08-07",
          f"{dup2.get('overlap_date_from')} … {dup2.get('overlap_date_to')}")
    check("D-2c contoh baris yang sudah ada disebut beserta status sekarang "
          "(bukan hanya angka)",
          len(dup2.get("sample") or []) >= 1
          and all(x.get("ref") for x in dup2["sample"]),
          f"{[(x.get('ref'), x.get('status_now')) for x in (dup2.get('sample') or [])][:3]}")
    rc2 = requests.post(f"{IMPORT_API}/sessions/{sid2}/commit", headers=JH, timeout=180,
                        json={"on_duplicate": "update"})
    j2 = rc2.json() if rc2.status_code == 200 else {}
    check("D-3a commit 'Perbarui yang lama': 3 diperbarui + 5 masuk "
          "(tidak ada pesanan kembar)",
          rc2.status_code == 200 and j2.get("updated") == 3 and j2.get("inserted") == 5,
          f"HTTP {rc2.status_code} diperbarui={j2.get('updated')} "
          f"masuk={j2.get('inserted')}")
    o5 = db.marketing_orders.find_one({"order_id": f"{MARK}-OV-05"}, {"_id": 0})
    check("D-3b baris yang sama IKUT TERUPDATE statusnya (dipesan ⇒ dibatalkan)",
          (o5 or {}).get("status") == "cancelled",
          f"status={(o5 or {}).get('status')}")
    check("D-3c perubahan status lewat MESIN SSOT: reservasi stok dilepas & "
          "pesanan batal tidak tertinggal di antrean gudang",
          bool(o5) and not (o5.get("reserved_rows") or o5.get("stock_reserved"))
          and (o5.get("fulfillment_status") or "") not in ("pending_fulfillment",
                                                          "allocated", "picking"),
          f"reserved={o5.get('reserved_rows') if o5 else '?'} "
          f"fulfillment={(o5 or {}).get('fulfillment_status')} "
          f"riwayat_status={len((o5 or {}).get('status_history') or [])} entri")
    check("D-3d hasil commit MENYEBUT apa yang terjadi pada status "
          "(bukan 'diperbarui' tanpa keterangan)",
          any("status" in " ".join(n.get("why") or [])
              for n in (j2.get("row_notes") or [])),
          f"{[ (n.get('why') or [''])[0][:70] for n in (j2.get('row_notes') or [])][:2]}")

    # ── mengunggah ULANG berkas LAMA tidak boleh menghidupkan pesanan batal ──
    sid3, dup3, _ = upload(f"{MARK}_1-7_ulang.csv", range(1, 8), "Perlu dikirim")
    rc3 = requests.post(f"{IMPORT_API}/sessions/{sid3}/commit", headers=JH, timeout=180,
                        json={"on_duplicate": "update"})
    j3 = rc3.json() if rc3.status_code == 200 else {}
    o5b = db.marketing_orders.find_one({"order_id": f"{MARK}-OV-05"}, {"_id": 0})
    check("D-4a unggah ULANG berkas LAMA: 7 baris dikenali sudah ada",
          dup3.get("existing") == 7, f"sudah ada={dup3.get('existing')}")
    check("D-4b status TIDAK MUNDUR — pesanan yang sudah dibatalkan TETAP batal "
          "(kalau mundur, gudang mengirim barang yang uangnya sudah dikembalikan)",
          (o5b or {}).get("status") == "cancelled",
          f"status={(o5b or {}).get('status')}")
    check("D-4c penolakan transisi DIJELASKAN di catatan hasil",
          any("TETAP" in " ".join(n.get("why") or [])
              for n in (j3.get("row_notes") or [])),
          f"{[ ' '.join(n.get('why') or [])[:80] for n in (j3.get('row_notes') or [])][:2]}")
    return sessions


def cleanup(db, sessions: list) -> None:
    for col in ("marketing_kol_creators", "marketing_content_calendar",
               "marketing_creator_sessions", "marketing_creator_targets",
               "marketing_orders"):
        db[col].delete_many({"_qa": MARK})
    for sid in sessions:
        s = db.marketing_data_import_sessions.find_one({"id": sid}, {"_id": 0})
        for cid in ((s or {}).get("committed_ids") or []):
            db.marketing_product_launches.delete_one({"id": cid})
        db.marketing_data_import_sessions.delete_one({"id": sid})
    db.marketing_product_launches.delete_many({"product_name": {"$regex": MARK}})
    db.marketing_orders.delete_many({"order_id": {"$regex": MARK}})
    db.marketing_change_log.delete_many({"reason": {"$regex": MARK}})
    db.marketing_data_import_formats.delete_many(
        {"source_type": "product_launches",
         "headers": {"$elemMatch": {"$regex": MARK}}})


def main() -> int:
    keep = "--keep" in sys.argv
    print(f"{B}{'=' * 88}{X}\nCORE TEST F8 — Assign Toko · Ingat Pemetaan · "
          f"Scorecard Kreator\n{B}{'=' * 88}{X}")
    token = login()
    H = {"Authorization": f"Bearer {token}"}
    JH = {**H, "Content-Type": "application/json"}
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    account = db.marketing_platform_accounts.find_one(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1},
        sort=[("account_name", 1)])
    if not account:
        print(f"{R}TIDAK ADA toko aktif — jalankan seed marketing dulu.{X}")
        return 1
    staff = db.users.find_one({"role": {"$in": ["staff_marketing", "pic_toko",
                                                "host_live", "cs_staff"]}},
                              {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not staff:
        print(f"{R}TIDAK ADA pemakai berperan staf toko — jalankan "
              f"seed_role_accounts.py dulu.{X}")
        return 1
    print(f"  toko uji: {account['account_name']} · staf uji: {staff['name']}")

    cleanup(db, [])
    sessions: list = []
    ctx = {}
    try:
        section_assign(JH, db, account, staff)
        sessions = section_memory(H, JH, db, account)
        ctx = seed_creator_data(db, account)
        section_scorecard(JH, ctx)
        sessions += section_overlap(H, JH, db, account)
    finally:
        if keep:
            print(f"\n{Y}--keep: data uji DIBIARKAN (tanda {MARK}){X}")
        else:
            cleanup(db, sessions)
            print(f"\n{Y}data uji dibersihkan (tanda {MARK}){X}")

    ok = sum(1 for _, c, _ in RES if c)
    print(f"\n{B}{'=' * 88}{X}")
    color = G if ok == len(RES) else R
    print(f"  {color}{ok} PASS{X} · {len(RES) - ok} GAGAL — total {len(RES)}")
    print(f"{B}{'=' * 88}{X}")
    for n, c, d in RES:
        if not c:
            print(f"    {R}✗{X} {n} — {d}")
    return 0 if ok == len(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
