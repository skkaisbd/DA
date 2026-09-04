#!/usr/bin/env python3
"""test_core_returns_visibility.py — CORE TEST **RETUR**: omzet bruto vs omzet setelah retur.

═══════════════════════════════════════════════════════════════════════════════
KEPUTUSAN PEMILIK YANG DIJAGA (sesi #9)
═══════════════════════════════════════════════════════════════════════════════
*"Tampilkan dua-duanya — omzet bruto DAN omzet setelah retur — tanpa mengubah
angka lama."*

Itu keputusan yang mudah dilanggar TANPA SENGAJA, dan pelanggarannya tidak
memunculkan satu pun galat:

* `R-A` **Angka lama bergeser.** Begitu seseorang "membetulkan" omzet dengan
  memasukkan `returned` ke `EXCLUDED_FOR_REVENUE`, SELURUH angka historis
  (target, capaian, pace, ROAS, lampiran rapat yang sudah beredar) berubah arti
  dalam senyap. Gate ini menuntut `EXCLUDED_FOR_REVENUE == ('cancelled',)` dan
  menuntut `actual.revenue` (bruto) tetap MEMASUKKAN pesanan retur.
* `R-B` **Dua basis uang tertukar.** Nilai retur ada pada basis *omzet produk*
  dan basis *order amount* (yang dibayar pembeli, termasuk ongkir). Mengurangi
  order amount retur dari omzet produk memberi net yang terlalu kecil — dan
  tidak ada yang tahu, karena keduanya "angka retur".
* `R-C` **Rumus retur kedua.** Sebelum sesi ini, `returned` dihitung ulang di
  empat tempat; dua di antaranya memakai pembaca uang sendiri
  (`revenue_product or revenue`) yang memberi **Rp 0** untuk pesanan yang
  diinput staf lewat layar. Gate menjaga agar hanya `core/marketing_returns.py`
  yang menjadi kalkulatornya.
* `R-D` **"Belum diketahui" dibaca sebagai "nol".** Retur hanya diketahui dari
  pesanan per baris. Hari yang rekapnya DIIMPOR/DIKETIK tidak membawa informasi
  retur; melaporkannya sebagai 0 retur adalah kebohongan yang paling mudah
  dipercaya. Gate menuntut `coverage` + kalimat catatan yang menyebutnya.
* `R-E` **Layar tidak ikut berubah.** Angka yang hanya ada di JSON tidak menolong
  siapa pun. Gate memeriksa berkas layar (Siklus · Scorecard · Rapat Mingguan)
  benar-benar membaca field baru DAN memuatnya di unduhan CSV/Excel.
* `R-F` **Retur tetap TERMINAL & melepas reservasi.** Menampilkan retur di
  laporan tidak boleh melunakkan janji stok: `returned` harus tetap melepas
  reservasi dan tidak bisa dihidupkan lagi (anti-overselling).

DATA UJI: bertanda `QARET`, memakai bulan **jauh di masa depan** (2027-03) pada
toko demo yang sudah ada, lalu DIBERSIHKAN sendiri — jadi gate ini tidak pernah
menyentuh bulan kerja nyata dan tidak bergantung pada seed.

Pakai:  python3 /app/test_core_returns_visibility.py [--keep]
"""
from __future__ import annotations

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

from core import marketing_returns as _ret            # noqa: E402
from core import marketing_cycle as _cycle            # noqa: E402
from core import marketing_daily_rollup as _rollup    # noqa: E402
from core import order_status as _ostat               # noqa: E402
from core import marketing_sales_shape as _shape      # noqa: E402

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, X, B = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[1m"
RES: list = []

MARK = "QARET"
PERIOD = "2027-03"
DAY = "2027-03-05"
DAY2 = "2027-03-06"
# Nilai sengaja "bulat aneh" supaya kalau ada rumus kedua, selisihnya kelihatan.
REV_OK = 1_000_000.0        # pesanan selesai
REV_RET = 400_000.0         # pesanan RETUR  (40% dari bruto ⇒ flag merah wajib menyala)
REV_CANCEL = 777_777.0      # pesanan BATAL  (tidak boleh masuk bruto sama sekali)
SHIP = 20_000.0             # ongkir ⇒ membedakan basis produk vs order amount


def check(name: str, cond: bool, detail: str = "") -> bool:
    RES.append((name, bool(cond), detail))
    print(f"  {G}PASS{X}  {name}" if cond else f"  {R}FAIL{X}  {name}",
          f"— {detail}" if detail else "")
    return bool(cond)


def login() -> str:
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


def order_doc(account_id: str, status: str, rev: float, day: str,
              creator_id: str | None = None, units: int = 2) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "order_id": f"{MARK}-{status.upper()}-{uuid.uuid4().hex[:6]}",
        "account_id": account_id,
        "order_date": datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        "status": status,
        "revenue_product": rev,
        "order_amount": rev + SHIP,
        "shipping_cost": SHIP,
        "quantity": units,
        "buyer_username": f"{MARK}-pembeli",
        "items": [{"sku": f"{MARK}-SKU", "quantity": units,
                   "sku_subtotal_after_discount": rev}],
        "order_channel": "live",
        "_qa": MARK,
        **({"creator_id": creator_id, "creator_name": f"{MARK} kreator"} if creator_id else {}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# [A] KALKULATOR — tanpa DB, tanpa HTTP (kalau ini salah, sisanya tidak berarti)
# ═══════════════════════════════════════════════════════════════════════════════
def section_calculator() -> None:
    print(f"\n{Y}[A] KALKULATOR RETUR — satu rumus, dua basis, cakupan jujur{X}")
    orders = [
        {"status": "delivered", "revenue_product": REV_OK, "order_amount": REV_OK + SHIP,
         "quantity": 2},
        {"status": "returned", "revenue_product": REV_RET, "order_amount": REV_RET + SHIP,
         "quantity": 3},
        {"status": "cancelled", "revenue_product": REV_CANCEL,
         "order_amount": REV_CANCEL + SHIP, "quantity": 9},
    ]
    s = _ret.split_from_orders(orders)
    check("A-1 bruto = definisi LAMA (semua kecuali batal; retur IKUT)",
          s["gross_revenue_product"] == REV_OK + REV_RET,
          f"bruto produk {s['gross_revenue_product']:,.0f} "
          f"(batal Rp {REV_CANCEL:,.0f} TIDAK ikut)")
    check("A-2 nilai retur dipisah pada basis PRODUK",
          s["returned_revenue_product"] == REV_RET, f"{s['returned_revenue_product']:,.0f}")
    check("A-3 nilai retur juga pada basis ORDER AMOUNT (termasuk ongkir)",
          s["returned_order_amount"] == REV_RET + SHIP,
          f"{s['returned_order_amount']:,.0f} = produk + ongkir {SHIP:,.0f}")
    check("A-4 net = bruto − retur, pada masing-masing basis",
          s["net_revenue_product"] == REV_OK
          and s["net_order_amount"] == REV_OK + SHIP,
          f"net produk {s['net_revenue_product']:,.0f} · "
          f"net order amount {s['net_order_amount']:,.0f}")
    check("A-5 pcs retur ikut terhitung (bukan hanya rupiah)",
          s["returned_units"] == 3, f"{s['returned_units']} pcs")

    # basis toko menentukan angka mana yang dipakai — R-B
    rp_ = _ret.resolve(_shape.BASIS_PRODUCT, s["gross_revenue_product"], s)
    ra_ = _ret.resolve(_shape.BASIS_ORDER_AMOUNT, s["gross_order_amount"], s)
    check("A-6 basis PRODUK memakai retur produk (bukan order amount)",
          rp_["returned_amount"] == REV_RET
          and rp_["revenue_net_returns"] == REV_OK, f"net {rp_['revenue_net_returns']:,.0f}")
    check("A-7 basis ORDER AMOUNT memakai retur order amount",
          ra_["returned_amount"] == REV_RET + SHIP
          and ra_["revenue_net_returns"] == REV_OK + SHIP,
          f"net {ra_['revenue_net_returns']:,.0f}")
    check("A-8 persen retur dihitung dari bruto (bukan diketik)",
          abs(rp_["returns_pct"] - REV_RET / (REV_OK + REV_RET) * 100) < 0.02,
          f"{rp_['returns_pct']}%")
    check("A-9 retur > omzet ⇒ net TIDAK negatif, tetapi ditandai `over_returned`",
          _ret.resolve(_shape.BASIS_PRODUCT, 100_000, s)["revenue_net_returns"] == 0.0
          and _ret.resolve(_shape.BASIS_PRODUCT, 100_000, s)["over_returned"] is True,
          "keadaan nyata: pesanan bulan lalu diretur bulan ini")

    # cakupan — R-D
    rows = [
        {"source": _shape.SOURCE_ORDERS_AUTO,
         "fulfillment": {"returned_orders": 1, "returned_value": REV_RET + SHIP,
                         "returned_revenue_product": REV_RET, "returned_units": 3}},
        {"source": _shape.SOURCE_IMPORT, "fulfillment": {}},
    ]
    agg = _ret.from_daily_rows(rows)
    check("A-10 hari yang rekapnya DIIMPOR dilaporkan BELUM DIKETAHUI (bukan 0 retur)",
          agg["coverage"]["days_known"] == 1 and agg["coverage"]["days_total"] == 2
          and agg["coverage"]["complete"] is False,
          f"cakupan {agg['coverage']['coverage_pct']}% · "
          f"sumber tak diketahui {agg['coverage']['unknown_sources']}")
    stale = _ret.from_daily_rows([
        {"source": _shape.SOURCE_ORDERS_AUTO,
         "fulfillment": {"returned_orders": 2, "returned_value": 500_000}}])
    check("A-11 rekap turunan LAMA (tanpa nilai retur produk) ⇒ belum diketahui, "
          "bukan net yang salah",
          stale["coverage"]["complete"] is False
          and stale["returned_revenue_product"] == 0.0,
          f"{stale['coverage']['unknown_sources']}")
    note = _ret.data_note(rp_)
    check("A-12 kalimat catatan menyebut retur + menegaskan target memakai BRUTO",
          "RETUR" in note and "BRUTO" in note, note[:110])
    check("A-13 rupiah di kalimat dibentuk helper (koma prosa tidak jadi titik)",
          "ditampilkan" not in note and "Rp 1.400.000" in note, note[:60])
    fl = _ret.evaluate_flags(rp_)
    check("A-14 retur 28,6% ⇒ peringatan MERAH (ambang merah 10%)",
          bool(fl) and fl[0]["code"] == "returns_high" and fl[0]["severity"] == "red",
          f"{[(f['code'], f['severity']) for f in fl]}")
    check("A-15 tanpa retur ⇒ TIDAK ada peringatan palsu",
          _ret.evaluate_flags({"returns_pct": 0, "returned_orders": 0}) == [], "")


# ═══════════════════════════════════════════════════════════════════════════════
# [B] STATIK — angka lama tidak boleh bergeser & tidak boleh ada rumus kedua
# ═══════════════════════════════════════════════════════════════════════════════
def section_static() -> None:
    print(f"\n{Y}[B] PENJAGA STATIK — angka lama & satu rumus{X}")
    check("B-1 `EXCLUDED_FOR_REVENUE` tetap ('cancelled',) di rekap harian & siklus",
          tuple(_rollup.EXCLUDED_FOR_REVENUE) == ("cancelled",)
          and tuple(_cycle.EXCLUDED_FOR_REVENUE) == ("cancelled",),
          f"rollup={_rollup.EXCLUDED_FOR_REVENUE} cycle={_cycle.EXCLUDED_FOR_REVENUE}")
    check("B-2 `RETURNED_STATUSES` hanya hidup di kalkulator retur",
          tuple(_ret.RETURNED_STATUSES) == ("returned",), "")
    # R-C — tidak ada pembaca uang retur sendiri di berkas laporan
    wk = open("/app/backend/core/marketing_weekly_report.py", encoding="utf-8").read()
    check("B-3 laporan mingguan TIDAK lagi membaca uang dengan "
          "`revenue_product or revenue` (memberi Rp 0 untuk pesanan manual)",
          'r.get("revenue_product") or r.get("revenue")' not in wk,
          "memakai core.marketing_daily_rollup + core.marketing_returns")
    check("B-4 laporan mingguan memanggil kalkulator retur (bukan filter status sendiri)",
          "_ret.split_from_orders" in wk, "")
    tg = open("/app/backend/routes/marketing_targets.py", encoding="utf-8").read()
    check("B-5 scorecard kreator memakai `_ret.is_returned` (bukan == 'returned')",
          "_ret.is_returned" in tg and '== "returned"' not in tg, "")
    check("B-6 catatan 'PERLU KEPUTUSAN PEMILIK' sudah diganti keputusan yang diambil",
          "PERLU KEPUTUSAN PEMILIK" not in tg and "KEPUTUSAN PEMILIK (sesi #9)" in tg, "")
    # R-F — janji stok tidak dilunakkan
    check("B-7 `returned` tetap MELEPAS reservasi stok",
          "returned" in _ostat.RESERVATION_RELEASING_STATUSES, "")
    check("B-8 `returned` tetap TERMINAL (tidak bisa dihidupkan lagi)",
          "returned" in _ostat.TERMINAL_STATUSES, "")
    try:
        _ostat.check_transition("returned", "shipped")
        ok = False
        why = "transisi returned → shipped DITERIMA (risiko overselling)"
    except _ostat.InvalidOrderTransition as e:
        ok, why = True, str(e)[:90]
    check("B-9 returned → shipped ditolak dengan alasan yang bisa dibaca staf", ok, why)
    # R-E — layar & unduhan
    cy = open("/app/frontend/src/components/erp/marketing/CycleView.jsx",
              encoding="utf-8").read()
    sc = open("/app/frontend/src/components/erp/marketing/CreatorScorecardView.jsx",
              encoding="utf-8").read()
    we = open("/app/frontend/src/components/erp/marketing/WeeklyMeetingReportModule.jsx",
              encoding="utf-8").read()
    check("B-10 layar Siklus membaca omzet setelah retur + nilai retur",
          "revenue_net_returns" in cy and "returned_amount" in cy
          and "cycle-kpi-returns" in cy, "")
    check("B-11 unduhan CSV Siklus memuat kolom retur & setelah retur",
          "'Nilai retur'" in cy and "'Omzet setelah retur'" in cy, "")
    check("B-12 layar Scorecard Kreator memuat kolom retur & setelah retur (+CSV)",
          "order_revenue_net_returns" in sc and "'Nilai retur'" in sc
          and "scorecard-kpi-returns" in sc, "")
    check("B-13 layar Rapat Mingguan memuat retur & omzet setelah retur",
          "omzet_setelah_retur" in we and "weekly-tile-setelah-retur" in we, "")
    xl = open("/app/backend/utils/marketing_weekly_export.py", encoding="utf-8").read()
    check("B-14 Excel/PDF rapat mingguan memuat retur (lampiran = layar)",
          "Omzet setelah retur" in xl and "SETELAH RETUR" in xl, "")
    bs = open("/app/scripts/bootstrap.sh", encoding="utf-8").read()
    check("B-15 bootstrap menyemai keadaan retur (fitur tidak tampak 'belum jadi' "
          "di environment segar)",
          "seed_marketing_returns_demo.py" in bs, "")


# ═══════════════════════════════════════════════════════════════════════════════
# [C] RANTAI NYATA — pesanan → rekap harian → siklus → scorecard → mingguan
# ═══════════════════════════════════════════════════════════════════════════════
def section_chain(JH: dict, db, account: dict, creator_id: str | None) -> None:
    print(f"\n{Y}[C] RANTAI NYATA — pesanan retur → rekap harian → siklus{X}")
    aid = account["id"]
    docs = [
        order_doc(aid, "delivered", REV_OK, DAY, creator_id),
        order_doc(aid, "returned", REV_RET, DAY, creator_id, units=3),
        order_doc(aid, "cancelled", REV_CANCEL, DAY, creator_id),
        order_doc(aid, "delivered", REV_OK, DAY2, creator_id),
    ]
    db.marketing_orders.insert_many(docs)

    for d in (DAY, DAY2):
        r = requests.post(f"{BASE}/api/marketing/sales/recompute",
                          headers=JH, timeout=120,
                          params={"account_id": aid, "date_from": d})
        if r.status_code != 200:
            check(f"C-0 hitung ulang rekap {d}", False, f"HTTP {r.status_code} {r.text[:120]}")
            return
    check("C-0 rekap harian dihitung ulang lewat jalur resmi (2 tanggal)", True, "")

    daily = db.marketing_sales_data.find_one(
        {"account_id": aid, "date": DAY, "revenue_type": "total"}, {"_id": 0})
    ful = (daily or {}).get("fulfillment") or {}
    met = (daily or {}).get("metrics") or {}
    check("C-1 rekap harian menyimpan nilai retur pada KEDUA basis",
          ful.get("returned_revenue_product") == REV_RET
          and ful.get("returned_value") == REV_RET + SHIP,
          f"produk {ful.get('returned_revenue_product')} · "
          f"order amount {ful.get('returned_value')}")
    check("C-2 rekap harian menyimpan jumlah pesanan & pcs retur",
          ful.get("returned_orders") == 1 and ful.get("returned_units") == 3,
          f"{ful.get('returned_orders')} pesanan · {ful.get('returned_units')} pcs")
    check("C-3 omzet harian (bruto) TETAP memasukkan pesanan retur — angka lama "
          "tidak bergeser",
          met.get("revenue_product") == REV_OK + REV_RET,
          f"{met.get('revenue_product'):,.0f} = {REV_OK:,.0f} + {REV_RET:,.0f}")
    check("C-4 pesanan BATAL tidak ikut bruto maupun retur",
          met.get("revenue_product") != REV_OK + REV_RET + REV_CANCEL
          and ful.get("cancelled_orders") == 1, f"batal {ful.get('cancelled_orders')}")

    r = requests.get(f"{BASE}/api/marketing/cycle/summary", headers=JH, timeout=120,
                     params={"account_id": aid, "period": PERIOD})
    s = r.json() if r.status_code == 200 else {}
    act = s.get("actual") or {}
    ret = s.get("returns") or {}
    gross_expect = REV_OK * 2 + REV_RET
    check("C-5 siklus: omzet bruto = 2 pesanan selesai + 1 retur (definisi lama)",
          act.get("revenue") == gross_expect and act.get("revenue_gross") == gross_expect,
          f"revenue {act.get('revenue')} · revenue_gross {act.get('revenue_gross')}")
    check("C-6 siklus: nilai retur & omzet setelah retur muncul sebagai angka SENDIRI",
          act.get("returned_amount") == REV_RET
          and act.get("revenue_net_returns") == gross_expect - REV_RET,
          f"retur {act.get('returned_amount')} · net {act.get('revenue_net_returns')}")
    check("C-7 siklus: capaian target dihitung dari BRUTO (bukan net)",
          (act.get("revenue") or 0) > 0
          and abs((s.get("achievement") or {}).get("revenue_pct", 0)
                  - ((act["revenue"] / (s["target"]["revenue"] or 1)) * 100)) < 0.05
          if (s.get("target") or {}).get("revenue") else True,
          f"target {(s.get('target') or {}).get('revenue')} · "
          f"capaian {(s.get('achievement') or {}).get('revenue_pct')}%")
    check("C-8 siklus: cakupan retur LENGKAP (semua hari turunan pesanan)",
          (ret.get("coverage") or {}).get("complete") is True,
          f"{(ret.get('coverage') or {}).get('days_known')}/"
          f"{(ret.get('coverage') or {}).get('days_total')} hari")
    check("C-9 siklus: peringatan `returns_high` MERAH menyala (retur 16,7% > 10%)",
          any(f.get("code") == "returns_high" and f.get("severity") == "red"
              for f in (s.get("flags") or [])),
          f"{[(f['code'], f['severity']) for f in (s.get('flags') or [])]}")
    check("C-10 siklus: catatan kejujuran menyebut retur secara terbuka",
          any("RETUR" in n for n in (s.get("data_notes") or [])),
          next((n[:100] for n in (s.get("data_notes") or []) if "RETUR" in n), "—"))

    r = requests.get(f"{BASE}/api/marketing/cycle/overview", headers=JH, timeout=180,
                     params={"period": PERIOD})
    ov = r.json() if r.status_code == 200 else {}
    tot = ov.get("totals") or {}
    row = next((x for x in (ov.get("rows") or []) if x["account"]["id"] == aid), None)
    check("C-11 overview: total retur & total setelah retur dihitung BACKEND",
          tot.get("returned_amount") == REV_RET
          and tot.get("revenue_net_returns") == (tot.get("revenue") or 0) - REV_RET,
          f"total omzet {tot.get('revenue')} · retur {tot.get('returned_amount')} · "
          f"net {tot.get('revenue_net_returns')}")
    check("C-12 overview: baris toko sama dengan cycle/summary toko itu",
          bool(row) and (row.get("actual") or {}).get("revenue_net_returns")
          == act.get("revenue_net_returns"), "")

    # ── scorecard kreator ────────────────────────────────────────────────────
    if creator_id:
        r = requests.get(f"{BASE}/api/marketing/targets/creator/scorecard", headers=JH,
                         timeout=120, params={"year": 2027, "month": 3})
        sc = r.json() if r.status_code == 200 else {}
        mine = next((x for x in (sc.get("rows") or [])
                     if x["creator_id"] == creator_id), None)
        a = (mine or {}).get("actual") or {}
        check("C-13 scorecard kreator: bruto · retur · setelah retur untuk kreator uji",
              bool(mine) and a.get("order_revenue") == REV_OK * 2 + REV_RET
              and a.get("order_revenue_returned") == REV_RET
              and a.get("order_revenue_net_returns") == REV_OK * 2,
              f"bruto {a.get('order_revenue')} · retur {a.get('order_revenue_returned')} "
              f"· net {a.get('order_revenue_net_returns')}")
        r = requests.get(f"{BASE}/api/marketing/targets/creator/{creator_id}/detail",
                         headers=JH, timeout=120, params={"year": 2027, "month": 3})
        dt = r.json() if r.status_code == 200 else {}
        dtot = dt.get("totals") or {}
        check("C-14 rincian kreator: total setelah retur = bruto − retur "
              "(sama dengan baris scorecard)",
              dtot.get("order_revenue") == a.get("order_revenue")
              and dtot.get("order_revenue_net_returns") == a.get("order_revenue_net_returns"),
              f"rincian net {dtot.get('order_revenue_net_returns')} vs "
              f"scorecard {a.get('order_revenue_net_returns')}")
        ret_row = next((o for o in (dt.get("orders") or [])
                        if o.get("status") == "returned"), None)
        check("C-15 rincian: baris retur TETAP tampil, ditandai ikut bruto & "
              "dikurangkan di net",
              bool(ret_row) and ret_row.get("counted") is True
              and "setelah retur" in str(ret_row.get("note") or ""),
              str((ret_row or {}).get("note"))[:90])

    # ── laporan mingguan ─────────────────────────────────────────────────────
    r = requests.get(f"{BASE}/api/marketing/reports/weekly", headers=JH, timeout=180,
                     params={"week_start": DAY, "account_id": aid})
    wk = r.json() if r.status_code == 200 else {}
    gab = wk.get("gabungan") or {}
    check("C-16 laporan mingguan: nilai retur memakai pembaca kanonik (bukan Rp 0)",
          gab.get("nilai_retur") == REV_RET, f"{gab.get('nilai_retur')}")
    check("C-17 laporan mingguan: omzet setelah retur = omzet − nilai retur",
          gab.get("omzet_setelah_retur") == (gab.get("omzet") or 0) - REV_RET,
          f"omzet {gab.get('omzet')} − retur {gab.get('nilai_retur')} = "
          f"{gab.get('omzet_setelah_retur')}")
    check("C-18 laporan mingguan: catatan menyebut retur + BRUTO tetap dasar target",
          any("RETUR" in n and "BRUTO" in n for n in (wk.get("catatan_data") or [])),
          next((n[:90] for n in (wk.get("catatan_data") or []) if "RETUR" in n), "—"))
    for path, label in (("export-excel", "Excel"), ("export-pdf", "PDF")):
        rr = requests.get(f"{BASE}/api/marketing/reports/weekly/{path}", headers=JH,
                          timeout=180, params={"week_start": DAY, "account_id": aid})
        check(f"C-19 lampiran {label} rapat mingguan tetap terbentuk (kolom retur baru)",
              rr.status_code == 200 and len(rr.content) > 3000,
              f"HTTP {rr.status_code} · {len(rr.content)} byte")


def cleanup(JH: dict, db, aid: str, creator_id: str | None) -> None:
    n = db.marketing_orders.delete_many({"_qa": MARK}).deleted_count
    for d in (DAY, DAY2):
        requests.post(f"{BASE}/api/marketing/sales/recompute", headers=JH, timeout=120,
                      params={"account_id": aid, "date_from": d, "force": "true"})
    left = db.marketing_sales_data.delete_many(
        {"account_id": aid, "date": {"$in": [DAY, DAY2]}}).deleted_count
    if creator_id:
        db.marketing_kol_creators.delete_many({"id": creator_id, "_qa": MARK})
    # jejak perubahan HANYA yang bertanda gate (aturan A-2e sesi #8b)
    db.marketing_change_log.delete_many({"reason": {"$regex": MARK}})
    print(f"    data uji dibersihkan: {n} pesanan · {left} rekap harian")


def main() -> int:
    keep = "--keep" in sys.argv
    print(f"{B}{'=' * 88}{X}")
    print(f"{B}RETUR TERLIHAT — omzet bruto vs omzet setelah retur (INV-RETUR){X}")
    print(f"{B}{'=' * 88}{X}")

    section_calculator()
    section_static()

    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]
    aid = None
    creator_id = None
    try:
        token = login()
    except Exception as e:                                       # noqa: BLE001
        print(f"{R}  backend/login tidak siap: {e}{X}")
        return 1
    JH = {"Authorization": f"Bearer {token}"}

    account = db.marketing_platform_accounts.find_one(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "revenue_basis": 1},
        sort=[("account_name", 1)])
    if not account:
        check("C-0 ada toko aktif untuk uji", False, "tidak ada toko aktif")
    else:
        aid = account["id"]
        print(f"    toko uji: {account.get('account_name')} · bulan {PERIOD} "
              f"(sengaja jauh di masa depan)")
        creator_id = str(uuid.uuid4())
        db.marketing_kol_creators.insert_one({
            "id": creator_id, "creator_code": f"{MARK}-KRE",
            "name": f"{MARK} Kreator Uji", "status": "active", "_qa": MARK,
            "account_ids": [aid], "account_id": aid})
        try:
            section_chain(JH, db, account, creator_id)
        finally:
            if not keep:
                cleanup(JH, db, aid, creator_id)

    ok = sum(1 for _, c, _ in RES if c)
    bad = [n for n, c, _ in RES if not c]
    print(f"\n{B}{'-' * 88}{X}")
    print(f"  INV-RETUR: {len(RES)} diperiksa — {len(bad)} temuan")
    if bad:
        print(f"  {R}{B}✗ INV-RETUR MERAH{X}")
        for n in bad:
            print(f"    {R}{n}{X}")
    else:
        print(f"  {G}{B}✓ INV-RETUR HIJAU{X} — {ok}/{len(RES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
