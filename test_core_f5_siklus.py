#!/usr/bin/env python3
"""test_core_f5_siklus.py — CORE TEST **FASE F5** (satu layar siklus: target →
anggaran → omzet · realisasi otomatis · kunci periode · peringatan).

Menguji **persis** daftar "BUKTI SELESAI F5" di
`memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`:

  1. `GET /api/marketing/cycle/summary` — SATU permintaan mengembalikan target,
     omzet (2 angka), anggaran, realisasi, marjin, ROI, flag.
  2. `budget/summary` kategori `diskon` **tidak 0** untuk bulan berpesanan,
     **tanpa satu pun entri manual**.
  3. Tutup periode ⇒ tulis target/anggaran/rekap/impor = **423**; buka ⇒ 200;
     keduanya tercatat di `marketing_change_log`.
  4. Target 100 jt & omzet 59,78 jt ⇒ flag `target_behind` (diuji pada hari ke-25
     memakai fungsi murni, dan lewat API untuk bulan yang sudah lewat).
  5. Anggaran 40 jt & terpakai > 40 jt ⇒ flag `budget_overrun` **merah**.
  6. `cycle/overview` (semua toko) menjumlah PERSIS sama dengan baris per toko.
  7. `margin.hpp_coverage_pct` selalu ada; cakupan rendah ⇒ catatan kejujuran.
  8. Kontrak layar: setiap field yang DIBACA layar Siklus ADA di respons.

Data uji memakai berkas NYATA `samples/TikTok_UntukDikirim_2026-07-19.xlsx`
(601 baris → 559 pesanan). Semua jejak uji dibersihkan di akhir.

Pakai:  python3 /app/test_core_f5_siklus.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
ACCOUNT_CODE = "TIKTOK-OUTFIT"
PERIOD = "2026-07"
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list[tuple[str, bool, str]] = []


def ok(n, d=""):
    RES.append((n, True, d)); print(f"  {G}PASS{X}  {n}" + (f" — {d}" if d else ""))


def bad(n, d=""):
    RES.append((n, False, d)); print(f"  {R}FAIL{X}  {n}" + (f" — {d}" if d else ""))


def check(n, cond, d=""):
    (ok if cond else bad)(n, d); return bool(cond)


def rp(v) -> str:
    return f"Rp {round(float(v or 0)):,}".replace(",", ".")


def money(v) -> int:
    return int(round(float(v or 0)))


def db_conn():
    c = MongoClient(os.environ["MONGO_URL"])
    return c[os.environ.get("DB_NAME", "test_database")]


def login() -> str:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
        if r.status_code == 200:
            j = r.json()
            return j.get("token") or j.get("access_token")
        time.sleep(6)
    raise SystemExit("login gagal")


# ══════════════════════════════════════════════════════════════════════════════
# PERSIAPAN — pastikan bulan 2026-07 punya pesanan NYATA
# ══════════════════════════════════════════════════════════════════════════════
def ensure_orders(H: dict, acc: dict) -> tuple[str | None, int]:
    """Impor berkas contoh bila bulan uji belum berdata. → (session_id|None, jumlah)."""
    db = db_conn()
    n = db.marketing_orders.count_documents({
        "account_id": acc["id"],
        "$or": [{"order_date": {"$regex": f"^{PERIOD}"}},
                {"order_date": {"$gte": datetime(2026, 7, 1), "$lt": datetime(2026, 8, 1)}}],
    })
    if n > 0:
        print(f"  {Y}(pakai data yang sudah ada: {n} pesanan {PERIOD}){X}")
        return None, n
    with open(SAMPLE, "rb") as fh:
        r = requests.post(
            f"{BASE}/api/marketing/data-import/upload", headers=H,
            files={"file": (os.path.basename(SAMPLE), fh,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"source_type": "marketplace_orders", "account_id": acc["id"]},
            timeout=240)
    if r.status_code != 200:
        bad("PRA upload berkas contoh", f"status={r.status_code} {r.text[:200]}")
        return None, 0
    sid = ((r.json().get("session") or {}).get("id"))
    rc = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/commit",
                       headers={**H, "Content-Type": "application/json"},
                       json={"on_duplicate": "skip"}, timeout=300)
    cb = rc.json() if rc.content else {}
    ok("PRA impor 559 pesanan nyata", f"inserted={cb.get('inserted')} rejected={cb.get('rejected')}")
    return sid, int(cb.get("inserted") or 0)


# ══════════════════════════════════════════════════════════════════════════════
# A — SATU PERMINTAAN = SEMUA ANGKA (bukti #1)
# ══════════════════════════════════════════════════════════════════════════════
def part_a(HJ: dict, acc: dict) -> dict:
    print(f"\n{Y}[A] SATU PERMINTAAN = SEMUA ANGKA (bukti #1){X}")
    r = requests.get(f"{BASE}/api/marketing/cycle/summary"
                     f"?account_id={acc['id']}&period={PERIOD}", headers=HJ, timeout=120)
    if not check("A1 endpoint cycle/summary hidup", r.status_code == 200,
                 f"status={r.status_code} {r.text[:200]}"):
        return {}
    s = r.json()
    groups = ("account", "period", "progress", "revenue_basis", "target", "actual",
              "achievement", "budget", "spend_sources", "margin", "roi", "flags",
              "locked", "label", "data_notes")
    miss = [g for g in groups if g not in s]
    check("A2 semua grup angka ada dalam SATU respons", not miss,
          f"{len(groups)} grup" if not miss else f"hilang: {miss}")

    db = db_conn()
    docs = list(db.marketing_orders.find({
        "account_id": acc["id"],
        "$or": [{"order_date": {"$regex": f"^{PERIOD}"}},
                {"order_date": {"$gte": datetime(2026, 7, 1), "$lt": datetime(2026, 8, 1)}}],
    }, {"_id": 0}))
    live = [d for d in docs if (d.get("status") or "") != "cancelled"]
    exp_rev_product = money(sum(d.get("revenue_product") or 0 for d in live))
    exp_orders = len(live)
    a = s.get("actual") or {}
    check("A3 omzet produk = jumlah pesanan di DB (bukan angka lain)",
          money(a.get("revenue_product")) == exp_rev_product,
          f"layar {rp(a.get('revenue_product'))} vs DB {rp(exp_rev_product)}")
    check("A4 jumlah pesanan = jumlah dokumen pesanan (tidak dobel)",
          int(a.get("orders") or 0) == exp_orders,
          f"layar {a.get('orders')} vs DB {exp_orders}")
    check("A5 DUA angka omzet dibawa sekaligus (produk & order amount)",
          money(a.get("revenue_order_amount")) > 0
          and money(a.get("revenue_order_amount")) != money(a.get("revenue_product")),
          f"produk {rp(a.get('revenue_product'))} · order amount {rp(a.get('revenue_order_amount'))}")
    check("A6 label 'sebelum potongan platform' ikut dibawa",
          "SEBELUM potongan platform" in (s.get("label") or ""), (s.get("label") or "")[:60])
    prog = s.get("progress") or {}
    check("A7 kemajuan bulan dihitung (hari berjalan / total hari)",
          prog.get("days_total") == 31 and prog.get("month_state") in
          ("running", "closed_month", "future"),
          f"{prog.get('days_elapsed')}/{prog.get('days_total')} · {prog.get('month_state')}")
    return s


# ══════════════════════════════════════════════════════════════════════════════
# B — REALISASI OTOMATIS (bukti #2)
# ══════════════════════════════════════════════════════════════════════════════
def part_b(HJ: dict, acc: dict, s: dict):
    print(f"\n{Y}[B] REALISASI ANGGARAN OTOMATIS — TANPA ENTRI MANUAL (bukti #2){X}")
    db = db_conn()
    n_manual = db.marketing_spend_entries.count_documents(
        {"account_id": acc["id"], "period": PERIOD})
    check("B1 tidak ada satu pun entri belanja manual bulan ini", n_manual == 0,
          f"{n_manual} entri manual")

    docs = list(db.marketing_orders.find({
        "account_id": acc["id"],
        "$or": [{"order_date": {"$regex": f"^{PERIOD}"}},
                {"order_date": {"$gte": datetime(2026, 7, 1), "$lt": datetime(2026, 8, 1)}}],
    }, {"_id": 0, "status": 1, "seller_discount_total": 1, "shipping_fee_seller_discount": 1}))
    live = [d for d in docs if (d.get("status") or "") != "cancelled"]
    exp_disc = money(sum(d.get("seller_discount_total") or 0 for d in live))
    exp_ship = money(sum(d.get("shipping_fee_seller_discount") or 0 for d in live))

    src = {x["category"]: x for x in (s.get("spend_sources") or [])}
    d = src.get("diskon") or {}
    check("B2 kategori `diskon` TIDAK 0 tanpa entri manual",
          money(d.get("amount")) > 0, rp(d.get("amount")))
    check("B3 diskon = diskon penjual + subsidi ongkir penjual (dari pesanan)",
          money(d.get("amount")) == exp_disc + exp_ship,
          f"layar {rp(d.get('amount'))} vs DB {rp(exp_disc)} + {rp(exp_ship)}")
    check("B4 angka otomatis membawa BUKTI (jumlah dokumen sumber)",
          d.get("source") == "auto" and d.get("docs") == len(live) and bool(d.get("evidence")),
          f"source={d.get('source')} docs={d.get('docs')} · {str(d.get('evidence'))[:70]}")
    check("B5 kategori otomatis lain ikut dilaporkan (ads/komisi/kol/livehost)",
          all(k in src for k in ("ads", "komisi", "kol", "livehost")),
          ", ".join(sorted(src.keys())))
    kom = src.get("komisi") or {}
    check("B6 komisi 0 disertai ALASAN (bukan 0 yang tampak seperti tak ada biaya)",
          money(kom.get("amount")) > 0 or "tidak memuat kreator" in str(kom.get("evidence")),
          str(kom.get("evidence"))[:80])

    r = requests.get(f"{BASE}/api/marketing/budget/summary"
                     f"?account_id={acc['id']}&period={PERIOD}", headers=HJ, timeout=120)
    if check("B7 budget/summary hidup", r.status_code == 200, f"status={r.status_code}"):
        bs = r.json()
        cats = {c["category"]: c for c in (bs.get("categories") or [])}
        check("B8 layar Anggaran lama IKUT melihat diskon otomatis",
              money(cats.get("diskon", {}).get("spend")) == money(d.get("amount")),
              rp(cats.get("diskon", {}).get("spend")))
        check("B9 kategori `komisi` ada di layar Anggaran (kategori baru F5)",
              "komisi" in cats, ", ".join(cats.keys()))
        check("B10 tiap kategori menandai auto vs manual",
              all("mode" in c and "auto" in c and "manual" in c for c in cats.values()),
              f"{len(cats)} kategori")
        db_docs = db.marketing_spend_entries.count_documents(
            {"account_id": acc["id"], "period": PERIOD})
        check("B11 angka otomatis TIDAK ditulis sebagai entri belanja (anti dobel)",
              db_docs == 0, f"{db_docs} entri di DB sesudah dibaca")


# ══════════════════════════════════════════════════════════════════════════════
# C — KUNCI PERIODE (bukti #3)
# ══════════════════════════════════════════════════════════════════════════════
def part_c(HJ: dict, acc: dict):
    print(f"\n{Y}[C] KUNCI PERIODE — 423, BUKAN 403 ATAU DIAM (bukti #3){X}")
    db = db_conn()
    aid = acc["id"]
    body = {"account_id": aid, "period": PERIOD, "action": "close", "reason": ""}
    r = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HJ, json=body, timeout=60)
    check("C1 tutup periode TANPA alasan ⇒ 400", r.status_code == 400,
          f"status={r.status_code} {str(r.text)[:90]}")

    body["reason"] = "Uji F5 — angka bulan ini dibekukan untuk rapat"
    r = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HJ, json=body, timeout=60)
    if not check("C2 tutup periode ⇒ 200", r.status_code == 200,
                 f"status={r.status_code} {str(r.text)[:120]}"):
        return
    lock = (r.json() or {}).get("lock") or {}
    check("C3 keadaan kunci tersimpan + siapa yang menutup",
          lock.get("locked") is True and bool(lock.get("closed_by_name")),
          f"locked={lock.get('locked')} oleh {lock.get('closed_by_name')}")

    y, m = int(PERIOD[:4]), int(PERIOD[5:7])
    r = requests.post(f"{BASE}/api/marketing/targets", headers=HJ, timeout=60, json={
        "account_id": aid, "year": y, "month": m, "revenue_target": 100_000_000,
        "orders_target": 600})
    check("C4 simpan TARGET di periode tertutup ⇒ 423", r.status_code == 423,
          f"status={r.status_code} {str(r.text)[:120]}")
    check("C5 pesan 423 menyebut jalan keluarnya (buka periode)",
          "buka" in str(r.text).lower() and PERIOD in str(r.text), str(r.text)[:140])

    r = requests.put(f"{BASE}/api/marketing/budget", headers=HJ, timeout=60, json={
        "account_id": aid, "period": PERIOD, "budget_by_category": {"ads": 1000}})
    check("C6 simpan ANGGARAN di periode tertutup ⇒ 423", r.status_code == 423,
          f"status={r.status_code}")

    r = requests.post(f"{BASE}/api/marketing/budget/spend", headers=HJ, timeout=60, json={
        "account_id": aid, "period": PERIOD, "category": "sample", "amount": 5000})
    check("C7 catat BELANJA di periode tertutup ⇒ 423", r.status_code == 423,
          f"status={r.status_code}")

    r = requests.post(f"{BASE}/api/marketing/sales-data", headers=HJ, timeout=60, json={
        "account_id": aid, "date": f"{PERIOD}-15", "revenue_type": "total",
        "revenue": 1_000_000, "orders": 5})
    check("C8 simpan REKAP HARIAN di periode tertutup ⇒ 423", r.status_code == 423,
          f"status={r.status_code}")

    # impor: berkas yang menyentuh bulan tertutup ditolak SEBELUM menulis
    with open(SAMPLE, "rb") as fh:
        ru = requests.post(
            f"{BASE}/api/marketing/data-import/upload",
            headers={"Authorization": HJ["Authorization"]},
            files={"file": (os.path.basename(SAMPLE), fh,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"source_type": "marketplace_orders", "account_id": aid}, timeout=240)
    sid = ((ru.json().get("session") or {}).get("id")) if ru.status_code == 200 else None
    if sid:
        n_before = db.marketing_orders.count_documents({"account_id": aid})
        rc = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/commit",
                           headers=HJ, json={"on_duplicate": "skip"}, timeout=300)
        n_after = db.marketing_orders.count_documents({"account_id": aid})
        check("C9 commit IMPOR ke bulan tertutup ⇒ 423", rc.status_code == 423,
              f"status={rc.status_code} {str(rc.text)[:120]}")
        check("C10 impor yang ditolak TIDAK menulis separuh data",
              n_after == n_before, f"{n_before} → {n_after} pesanan")
        requests.delete(f"{BASE}/api/marketing/data-import/sessions/{sid}", headers=HJ, timeout=60)

    r = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HJ, timeout=60, json={
        "account_id": aid, "period": PERIOD, "action": "reopen",
        "reason": "Uji F5 — dibuka kembali"})
    check("C11 buka periode ⇒ 200", r.status_code == 200, f"status={r.status_code}")
    r = requests.post(f"{BASE}/api/marketing/targets", headers=HJ, timeout=60, json={
        "account_id": aid, "year": y, "month": m, "revenue_target": 100_000_000,
        "orders_target": 600})
    check("C12 sesudah dibuka, simpan target ⇒ 200", r.status_code == 200,
          f"status={r.status_code}")

    logs = list(db.marketing_change_log.find(
        {"account_id": aid, "period": PERIOD}, {"_id": 0}))
    acts = [x.get("action") for x in logs]
    check("C13 tutup & buka periode tercatat di marketing_change_log",
          "period_close" in acts and "period_reopen" in acts, f"{len(logs)} baris: {acts[:6]}")
    check("C14 jejak menyimpan siapa & alasan",
          all(x.get("actor_name") is not None for x in logs)
          and any((x.get("reason") or "") for x in logs),
          f"actor={logs[0].get('actor_name') if logs else '—'}")


# ══════════════════════════════════════════════════════════════════════════════
# D & E — PERINGATAN (bukti #4 & #5)
# ══════════════════════════════════════════════════════════════════════════════
def part_de(HJ: dict, acc: dict):
    print(f"\n{Y}[D/E] PERINGATAN target_behind & budget_overrun (bukti #4 & #5){X}")
    aid = acc["id"]
    r = requests.put(f"{BASE}/api/marketing/budget", headers=HJ, timeout=60, json={
        "account_id": aid, "period": PERIOD,
        "budget_by_category": {"ads": 40_000_000}, "notes": "uji F5"})
    check("D1 rencana anggaran 40 jt tersimpan", r.status_code == 200, f"status={r.status_code}")

    r = requests.get(f"{BASE}/api/marketing/cycle/summary"
                     f"?account_id={aid}&period={PERIOD}", headers=HJ, timeout=120)
    s = r.json() if r.status_code == 200 else {}
    flags = {f["code"]: f for f in (s.get("flags") or [])}
    ach = s.get("achievement") or {}
    check("D2 capaian & pace dihitung terhadap target 100 jt",
          money((s.get("target") or {}).get("revenue")) == 100_000_000 and ach.get("revenue_pct") > 0,
          f"capaian {ach.get('revenue_pct')}% · pace {ach.get('pace_pct')}%")
    check("D3 flag `target_behind` muncul (omzet di bawah pace)",
          "target_behind" in flags,
          f"{flags.get('target_behind', {}).get('severity')} — "
          f"{str(flags.get('target_behind', {}).get('message'))[:80]}")
    bud = s.get("budget") or {}
    check("E1 anggaran 40 jt vs terpakai > 40 jt terlihat di ringkas",
          money(bud.get("total_plan")) == 40_000_000 and money(bud.get("total_spend")) > 40_000_000,
          f"rencana {rp(bud.get('total_plan'))} · terpakai {rp(bud.get('total_spend'))}")
    check("E2 flag `budget_overrun` MERAH",
          flags.get("budget_overrun", {}).get("severity") == "red",
          str(flags.get("budget_overrun", {}).get("message"))[:90])
    check("E3 pelampauan per KATEGORI juga ditandai (termasuk yang TANPA rencana)",
          any(f.get("code") in ("budget_overrun_category", "budget_unplanned_category")
              for f in (s.get("flags") or [])),
          str([(f.get("code"), f.get("category")) for f in (s.get("flags") or [])
               if f.get("code", "").startswith("budget_")]))

    # hari ke-25 (fungsi murni) — pace 80,6% vs capaian 59,8% ⇒ target_behind
    from core import marketing_cycle as _c
    prog = _c.month_progress(PERIOD, datetime(2026, 7, 25, 10, 0, tzinfo=_c.WIB))
    check("D4 pace hari ke-25 dari 31 = 80,65% (WIB, bukan UTC)",
          prog["pace_pct"] == round(25 / 31 * 100, 2),
          f"{prog['pace_pct']}% · hari {prog['days_elapsed']}/{prog['days_total']}")
    synth = {"target": {"revenue": 100_000_000},
             "achievement": {"revenue_pct": 59.78, "pace_pct": prog["pace_pct"]},
             "budget": {"total_plan": 40_000_000, "total_spend": 48_000_000, "categories": []},
             "margin": {"units_total": 0, "hpp_coverage_pct": 0},
             "progress": prog}
    fl = {f["code"]: f for f in _c.evaluate_flags(synth)}
    check("D5 hari ke-25: target 100 jt & omzet 59,78 jt ⇒ target_behind",
          "target_behind" in fl, f"selisih {fl.get('target_behind', {}).get('value')} poin")
    check("E4 anggaran 40 jt & terpakai 48 jt ⇒ budget_overrun MERAH",
          fl.get("budget_overrun", {}).get("severity") == "red",
          str(fl.get("budget_overrun", {}).get("message"))[:70])
    prog_future = _c.month_progress("2099-01", datetime(2026, 7, 25, tzinfo=_c.WIB))
    fl2 = {f["code"]: f for f in _c.evaluate_flags(
        {**synth, "progress": prog_future,
         "achievement": {"revenue_pct": 0, "pace_pct": prog_future["pace_pct"]}})}
    check("D6 bulan yang BELUM datang tidak dituduh tertinggal target",
          "target_behind" not in fl2, f"pace {prog_future['pace_pct']}%")


# ══════════════════════════════════════════════════════════════════════════════
# F & G — MARJIN + OVERVIEW (bukti #6 & #7)
# ══════════════════════════════════════════════════════════════════════════════
def part_fg(HJ: dict, acc: dict, s: dict):
    print(f"\n{Y}[F/G] MARJIN dengan CAKUPAN HPP & OVERVIEW semua toko (bukti #6 & #7){X}")
    m = s.get("margin") or {}
    need = ("revenue", "hpp", "gross_profit", "gross_margin_pct", "hpp_coverage_pct",
            "units_total", "units_covered", "trustworthy")
    check("F1 marjin selalu ditemani cakupan HPP",
          all(k in m for k in need), f"cakupan {m.get('hpp_coverage_pct')}% "
          f"({m.get('units_covered')}/{m.get('units_total')} unit)")
    notes = " ".join(s.get("data_notes") or [])
    check("F2 catatan kejujuran menyebut cakupan HPP secara terbuka",
          "HPP" in notes and ("cakupan" in notes or "belum bisa" in notes), notes[:110])
    if float(m.get("hpp_coverage_pct") or 0) < 80 and int(m.get("units_total") or 0) > 0:
        check("F3 cakupan < 80% ⇒ flag `hpp_coverage_low` muncul",
              any(f["code"] == "hpp_coverage_low" for f in (s.get("flags") or [])),
              "marjin ditandai belum bisa dipercaya")
    else:
        ok("F3 cakupan HPP memadai / belum ada pesanan — tidak perlu flag",
           f"{m.get('hpp_coverage_pct')}%")

    r = requests.get(f"{BASE}/api/marketing/cycle/overview?period={PERIOD}",
                     headers=HJ, timeout=300)
    if not check("G1 endpoint cycle/overview hidup", r.status_code == 200,
                 f"status={r.status_code} {r.text[:150]}"):
        return
    ov = r.json()
    rows = ov.get("rows") or []
    tot = ov.get("totals") or {}
    check("G2 semua toko aktif punya baris", len(rows) >= 9, f"{len(rows)} toko")
    sum_rev = money(sum(float((x.get("actual") or {}).get("revenue") or 0) for x in rows))
    check("G3 total omzet = jumlah baris (dihitung backend, bukan browser)",
          money(tot.get("revenue")) == sum_rev,
          f"total {rp(tot.get('revenue'))} vs Σ baris {rp(sum_rev)}")
    sum_plan = money(sum(float((x.get("budget") or {}).get("total_plan") or 0) for x in rows))
    check("G4 total rencana anggaran = jumlah baris",
          money(tot.get("total_plan")) == sum_plan, rp(tot.get("total_plan")))
    mine = next((x for x in rows if x["account"]["account_code"] == ACCOUNT_CODE), None)
    check("G5 baris toko uji di overview = angka cycle/summary (satu sumber)",
          bool(mine) and money((mine.get("actual") or {}).get("revenue"))
          == money((s.get("actual") or {}).get("revenue")),
          f"overview {rp((mine or {}).get('actual', {}).get('revenue'))} vs "
          f"summary {rp((s.get('actual') or {}).get('revenue'))}")
    check("G6 papan perhatian diurutkan backend (merah dulu)",
          isinstance(ov.get("attention"), list),
          f"{len(ov.get('attention') or [])} toko perlu perhatian")


# ══════════════════════════════════════════════════════════════════════════════
# H — KONTRAK LAYAR (bukti #8)
# ══════════════════════════════════════════════════════════════════════════════
def part_h(s: dict):
    print(f"\n{Y}[H] KONTRAK LAYAR — field yang DIBACA layar harus ADA{X}")
    paths = [
        "account.account_name", "account.account_code", "account.platform",
        "period", "locked", "revenue_basis", "label",
        "progress.days_elapsed", "progress.days_total", "progress.pace_pct",
        "target.revenue", "target.orders", "target.exists",
        "actual.revenue", "actual.revenue_product", "actual.revenue_order_amount",
        "actual.orders", "actual.units", "actual.aov", "actual.days_with_data",
        "achievement.revenue_pct", "achievement.orders_pct", "achievement.pace_pct",
        "achievement.status", "achievement.prorata_target", "achievement.run_rate",
        "budget.total_plan", "budget.total_spend", "budget.total_remaining",
        "budget.total_used_pct", "budget.categories",
        "margin.hpp", "margin.gross_profit", "margin.gross_margin_pct",
        "margin.hpp_coverage_pct",
        "roi.roas", "roi.roi_pct", "roi.spend_of_revenue_pct", "roi.reliable",
        "lock.history",
    ]
    missing = []
    for p in paths:
        cur = s
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                missing.append(p)
                break
    check(f"H1 {len(paths)} field yang dibaca layar Siklus semuanya ada",
          not missing, "lengkap" if not missing else f"hilang: {missing}")
    cats = (s.get("budget") or {}).get("categories") or []
    need = ("category", "plan", "spend", "manual", "auto", "mode", "variance",
            "used_pct", "status")
    check("H2 tiap baris kategori anggaran membawa 9 kolom layar",
          bool(cats) and all(all(k in c for k in need) for c in cats),
          f"{len(cats)} kategori")


# ══════════════════════════════════════════════════════════════════════════════
def part_i(HJ: dict, acc: dict):
    """MARJIN benar-benar MENJOIN HPP katalog (bukan selalu 0) — bukti tambahan.

    Cakupan HPP 0% pada data impor itu JUJUR (ekspor Seller Center tidak memuat
    HPP dan SKU-nya belum dipetakan). Tapi 0 yang selalu 0 tidak membuktikan
    rumusnya jalan. Bagian ini membuat SATU pesanan yang tertaut ke item katalog
    ber-HPP, lalu menuntut marjin & cakupannya berubah — dan membersihkannya.
    """
    print(f"\n{Y}[I] MARJIN MENJOIN HPP KATALOG (bukan 0 yang selalu 0){X}")
    db = db_conn()
    item = db.marketing_catalog_items.find_one(
        {"hpp": {"$gt": 0}, "$or": [{"price": {"$gt": 0}}, {"harga_jual": {"$gt": 0}}]},
        {"_id": 0})
    if not item:
        bad("I1 ada item katalog ber-HPP untuk diuji",
            "tidak ada item katalog ber-HPP — jalankan scripts/seed_katalog_order_demo.py")
        return
    harga = float(item.get("price") or item.get("harga_jual") or 0)
    cat = db.marketing_catalogs.find_one({"id": item.get("catalog_id")}, {"_id": 0}) or {}
    aid = cat.get("account_id") or acc["id"]
    period = _test_period_for(db, aid)
    before = requests.get(f"{BASE}/api/marketing/cycle/summary"
                          f"?account_id={aid}&period={period}", headers=HJ, timeout=120).json()
    m0 = before.get("margin") or {}
    payload = {
        "account_id": aid, "platform": (cat.get("platform") or "manual"),
        "customer_name": "UJI F5 MARJIN", "catalog_item_id": item["id"],
        "reserve_stock": False,
        "items": [{"sku_code": item.get("sku") or item.get("sku_code") or "UJI",
                   "product_name": item.get("name") or "uji", "qty": 1,
                   "price": harga, "catalog_item_id": item["id"]}],
        "quantity": 1, "price_final": harga,
        "total_payment": harga,
        "note": "pesanan uji F5 (dihapus otomatis)",
    }
    r = requests.post(f"{BASE}/api/marketing/orders", headers=HJ, json=payload, timeout=90)
    body = r.json() if r.content else {}
    oid = (body.get("order") or body).get("id") if isinstance(body, dict) else None
    if not check("I1 pesanan uji tertaut item katalog dibuat",
                 r.status_code in (200, 201) and bool(oid),
                 f"status={r.status_code} {str(body)[:160]}"):
        return
    try:
        after = requests.get(f"{BASE}/api/marketing/cycle/summary"
                             f"?account_id={aid}&period={period}", headers=HJ, timeout=120).json()
        m1 = after.get("margin") or {}
        check("I2 HPP terhitung dari item katalog (join bekerja)",
              money(m1.get("hpp")) >= money(item.get("hpp")),
              f"HPP {rp(m0.get('hpp'))} → {rp(m1.get('hpp'))} (HPP item {rp(item.get('hpp'))})")
        check("I3 cakupan HPP naik (unit ber-HPP dihitung)",
              float(m1.get("hpp_coverage_pct") or 0) > float(m0.get("hpp_coverage_pct") or 0)
              or int(m1.get("units_covered") or 0) > int(m0.get("units_covered") or 0),
              f"cakupan {m0.get('hpp_coverage_pct')}% → {m1.get('hpp_coverage_pct')}% "
              f"({m1.get('units_covered')}/{m1.get('units_total')} unit)")
        check("I4 marjin kotor = omzet item ber-HPP − HPP",
              abs(money(m1.get("gross_profit"))
                  - (money(m1.get("revenue")) - money(m1.get("hpp")))) <= 1,
              f"marjin {rp(m1.get('gross_profit'))} = {rp(m1.get('revenue'))} − {rp(m1.get('hpp'))}")
        check("I5 ROI ditandai bisa/tidak bisa dipercaya sesuai cakupan HPP",
              (after.get("roi") or {}).get("reliable") is (float(m1.get("hpp_coverage_pct") or 0) >= 80
                                                           and int(m1.get("units_total") or 0) > 0),
              f"reliable={(after.get('roi') or {}).get('reliable')} · "
              f"cakupan {m1.get('hpp_coverage_pct')}%")
    finally:
        rd = requests.delete(f"{BASE}/api/marketing/orders/{oid}", headers=HJ, timeout=60)
        if rd.status_code not in (200, 204):
            db.marketing_orders.delete_one({"id": oid})
        print(f"    pesanan uji dihapus (HTTP {rd.status_code})")


def _test_period_for(db, account_id: str) -> str:
    """Periode (YYYY-MM) hari ini WIB — pesanan uji dibuat hari ini."""
    sys.path.insert(0, "/app/backend")
    from core import marketing_cycle as _c
    return _c.today_wib().strftime("%Y-%m")


def cleanup(HJ: dict, acc: dict, sid: str | None):
    print(f"\n  {Y}(bersih-bersih){X}")
    aid = acc["id"]
    db = db_conn()
    y, m = int(PERIOD[:4]), int(PERIOD[5:7])
    db.marketing_account_targets.delete_many({"account_id": aid, "year": y, "month": m})
    db.marketing_budgets.delete_many({"account_id": aid, "period": PERIOD})
    db.marketing_spend_entries.delete_many({"account_id": aid, "period": PERIOD})
    db.marketing_period_locks.delete_many({"account_id": aid, "period": PERIOD})
    db.marketing_change_log.delete_many({"account_id": aid, "period": PERIOD})
    print("    target/anggaran/kunci/jejak uji dihapus")
    if sid:
        r = requests.post(f"{BASE}/api/marketing/data-import/sessions/{sid}/rollback",
                          headers=HJ, timeout=300)
        print(f"    rollback impor uji: {r.status_code}")


def main() -> int:
    print(f"{B}{'=' * 90}{X}")
    print(f"{B}CORE TEST F5 — SIKLUS TARGET · ANGGARAN · OMZET (HTTP nyata + verifikasi DB){X}")
    print(f"{B}{'=' * 90}{X}")
    if not os.path.exists(SAMPLE):
        print(f"berkas contoh tidak ada: {SAMPLE}")
        return 2
    token = login()
    H = {"Authorization": f"Bearer {token}"}
    HJ = {**H, "Content-Type": "application/json"}
    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=HJ, timeout=60).json()
    acc = next((a for a in accounts if a.get("account_code") == ACCOUNT_CODE), None)
    if not acc:
        print(f"toko {ACCOUNT_CODE} tidak ada — jalankan "
              "backend/scripts/seed_marketing_real_accounts.py --apply")
        return 2
    print(f"\n{Y}[PRA] DATA NYATA{X}")
    sid, _ = ensure_orders(H, acc)
    s = part_a(HJ, acc)
    if s:
        part_b(HJ, acc, s)
        part_c(HJ, acc)
        part_de(HJ, acc)
        s2 = requests.get(f"{BASE}/api/marketing/cycle/summary"
                          f"?account_id={acc['id']}&period={PERIOD}",
                          headers=HJ, timeout=120).json()
        part_fg(HJ, acc, s2)
        part_h(s2)
        part_i(HJ, acc)
    cleanup(HJ, acc, sid)
    good = sum(1 for _, o, _ in RES if o)
    print(f"\n{B}{'=' * 90}{X}")
    color = G if good == len(RES) else R
    print(f"RINGKAS F5: {color}{good}/{len(RES)} PASS{X} "
          "(satu permintaan · realisasi otomatis · kunci periode · peringatan)")
    if good != len(RES):
        for n, o, d in RES:
            if not o:
                print(f"  {R}GAGAL{X} {n} — {d}")
    print(f"{B}{'=' * 90}{X}")
    return 0 if good == len(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
