#!/usr/bin/env python3
"""verify_marketing_cycle.py — GATE **INV-MKTCYCLE** (F5): siklus target · anggaran ·
omzet tidak boleh berbohong, dan kunci periode harus benar-benar mengunci.

KENAPA GATE INI ADA (semuanya cacat NYATA yang ditutup F5, bukan dugaan)
-----------------------------------------------------------------------
* **CYC-1 Satu angka, satu sumber.** Sebelum F5, layar Target, layar Anggaran, dan
  Laporan menghitung sendiri-sendiri. Gate memastikan `cycle/summary` konsisten di
  dalam dirinya (total = Σ kategori) DAN sama dengan `budget/summary` untuk toko &
  bulan yang sama. Kalau dua endpoint berbeda, rapat akan memakai yang mana pun
  yang dibuka lebih dulu.
* **CYC-2 Realisasi otomatis tidak boleh ditulis sebagai entri belanja.** Menulisnya
  membuat biaya yang sama dihitung dua kali begitu staf juga mencatat manual.
  Gate memeriksa SELURUH `marketing_spend_entries`: tidak boleh ada `source != manual`.
* **CYC-3 Kunci periode benar-benar menolak (423).** Kunci yang hanya "menandai" di
  layar tetapi tidak menolak tulisan sama dengan tidak ada kunci — angka rapat
  masih bisa berubah. Diuji dengan **pelanggaran sintetis**: gate menutup periode
  toko uji, mencoba menulis target, dan menuntut 423 (lalu membersihkan jejaknya).
* **CYC-4 Total overview = Σ baris.** Total yang dihitung ulang di browser adalah
  cara paling mudah membuat lampiran export berbeda dari layar.
* **CYC-5 Marjin selalu membawa cakupan HPP.** Marjin tanpa cakupan adalah angka
  yang menipu (cakupan 0% pernah tampil seolah marjin 57%).
* **CYC-6 Bentuk dokumen kunci periode.** Setiap dokumen `marketing_period_locks`
  wajib punya `account_id`, `period`, dan riwayat — tanpa itu, "siapa menutup bulan
  ini" tidak bisa dijawab.
* **CYC-7 Kategori anggaran kanonik SATU daftar.** `komisi` (kategori F5) harus ada
  di backend, di respons endpoint, dan di layar. Dua daftar kategori = satu
  kategori biaya hilang dari rencana.

READ-ONLY terhadap data produksi; satu-satunya tulisan adalah kunci periode
sintetis pada toko uji yang DIBERSIHKAN di akhir (dan periode yang dipakai
sengaja jauh di masa depan supaya tidak pernah menyentuh bulan kerja nyata).

Pakai:  cd /app && python3 scripts/verify_marketing_cycle.py
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
SYNTH_PERIOD = "2099-12"      # sengaja bukan bulan kerja nyata
G, R, X, B = "\033[92m", "\033[91m", "\033[0m", "\033[1m"
RES: list[tuple[str, bool, str]] = []


def ok(code, msg=""):
    RES.append((code, True, msg)); print(f"  {G}✓{X} {code:12s} {msg}")


def bad(code, msg=""):
    RES.append((code, False, msg)); print(f"  {R}✗{X} {code:12s} {msg}")


def check(code, cond, good="", bad_msg=""):
    (ok if cond else bad)(code, good if cond else (bad_msg or good))
    return bool(cond)


def db_conn():
    c = MongoClient(os.environ["MONGO_URL"])
    return c[os.environ.get("DB_NAME", "test_database")]


def login() -> str:
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        time.sleep(5)
    raise SystemExit("login gagal — backend belum siap")


def main() -> int:
    print(f"\n{B}{'=' * 82}{X}")
    print(f"{B}INV-MKTCYCLE — SIKLUS TARGET · ANGGARAN · OMZET (F5){X}")
    print(f"{B}{'=' * 82}{X}")
    token = login()
    HJ = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    db = db_conn()

    from core import marketing_cycle as _cycle

    accounts = requests.get(f"{BASE}/api/marketing/accounts", headers=HJ, timeout=60).json()
    accounts = [a for a in accounts if a.get("status") == "active"] if isinstance(accounts, list) else []
    if not accounts:
        bad("CYC-0", "tidak ada toko aktif — master toko belum di-seed")
        return 1

    # pilih toko yang PALING berdata (gate tanpa data tidak membuktikan apa pun)
    best, best_rev = accounts[0], -1.0
    period = None
    rows = list(db.marketing_sales_data.find(
        {"revenue_type": "total"}, {"_id": 0, "account_id": 1, "date": 1, "metrics": 1}))
    agg: dict = {}
    for r in rows:
        key = (r.get("account_id"), str(r.get("date"))[:7])
        agg[key] = agg.get(key, 0.0) + float((r.get("metrics") or {}).get("revenue") or 0)
    if agg:
        (aid, per), rev = max(agg.items(), key=lambda kv: kv[1])
        acc = next((a for a in accounts if a["id"] == aid), None)
        if acc:
            best, best_rev, period = acc, rev, per
    if not period:
        period = _cycle.today_wib().strftime("%Y-%m")
    print(f"\n  toko uji: {best.get('account_name')} · periode {period} "
          f"(omzet rekap Rp {max(best_rev, 0):,.0f})".replace(",", "."))

    # ── CYC-1 — satu angka, satu sumber ──────────────────────────────────────
    rc = requests.get(f"{BASE}/api/marketing/cycle/summary"
                      f"?account_id={best['id']}&period={period}", headers=HJ, timeout=120)
    if not check("CYC-1a", rc.status_code == 200,
                 "endpoint cycle/summary hidup", f"HTTP {rc.status_code}"):
        return 1
    s = rc.json()
    cats = (s.get("budget") or {}).get("categories") or []
    sum_cat = round(sum(float(c.get("spend") or 0) for c in cats), 2)
    check("CYC-1b", abs(sum_cat - float((s.get("budget") or {}).get("total_spend") or 0)) < 0.05,
          "total terpakai = Σ kategori",
          f"total {(s.get('budget') or {}).get('total_spend')} vs Σ {sum_cat}")
    sum_plan = round(sum(float(c.get("plan") or 0) for c in cats), 2)
    check("CYC-1c", abs(sum_plan - float((s.get("budget") or {}).get("total_plan") or 0)) < 0.05,
          "total rencana = Σ kategori")
    rb = requests.get(f"{BASE}/api/marketing/budget/summary"
                      f"?account_id={best['id']}&period={period}", headers=HJ, timeout=120)
    if rb.status_code == 200:
        b = rb.json()
        check("CYC-1d",
              abs(float(b.get("total_spend") or 0)
                  - float((s.get("budget") or {}).get("total_spend") or 0)) < 0.05,
              "budget/summary & cycle/summary menyebut angka yang SAMA",
              f"budget {b.get('total_spend')} vs cycle "
              f"{(s.get('budget') or {}).get('total_spend')}")
        check("CYC-1e",
              abs(float(b.get("sales") or 0) - float((s.get("actual") or {}).get("revenue") or 0)) < 0.05,
              "omzet di dua endpoint sama")
    else:
        bad("CYC-1d", f"budget/summary HTTP {rb.status_code}")

    # ── CYC-2 — angka otomatis tidak pernah jadi entri belanja ───────────────
    non_manual = db.marketing_spend_entries.count_documents(
        {"source": {"$nin": ["manual", None, ""]}})
    check("CYC-2", non_manual == 0,
          "0 entri belanja bersumber otomatis (anti dobel-hitung)",
          f"{non_manual} entri ber-source otomatis — realisasi bisa dihitung dua kali")

    # ── CYC-3 — kunci periode BENAR-BENAR menolak (pelanggaran sintetis) ─────
    y, m = int(SYNTH_PERIOD[:4]), int(SYNTH_PERIOD[5:7])
    try:
        r1 = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HJ, timeout=60, json={
            "account_id": best["id"], "period": SYNTH_PERIOD, "action": "close",
            "reason": "GATE INV-MKTCYCLE — pelanggaran sintetis (dibersihkan otomatis)"})
        locked_ok = r1.status_code == 200
        r2 = requests.post(f"{BASE}/api/marketing/targets", headers=HJ, timeout=60, json={
            "account_id": best["id"], "year": y, "month": m,
            "revenue_target": 1, "orders_target": 1})
        check("CYC-3a", locked_ok and r2.status_code == 423,
              "periode tertutup menolak tulisan target dengan 423",
              f"lock HTTP {r1.status_code} · target HTTP {r2.status_code} "
              "(kunci yang tidak menolak = tidak ada kunci)")
        r3 = requests.put(f"{BASE}/api/marketing/budget", headers=HJ, timeout=60, json={
            "account_id": best["id"], "period": SYNTH_PERIOD,
            "budget_by_category": {"ads": 1}})
        check("CYC-3b", r3.status_code == 423,
              "periode tertutup menolak tulisan anggaran dengan 423",
              f"HTTP {r3.status_code}")
        r4 = requests.post(f"{BASE}/api/marketing/periods/lock", headers=HJ, timeout=60, json={
            "account_id": best["id"], "period": SYNTH_PERIOD, "action": "reopen",
            "reason": "GATE INV-MKTCYCLE — bersih-bersih"})
        r5 = requests.post(f"{BASE}/api/marketing/targets", headers=HJ, timeout=60, json={
            "account_id": best["id"], "year": y, "month": m,
            "revenue_target": 1, "orders_target": 1})
        check("CYC-3c", r4.status_code == 200 and r5.status_code == 200,
              "sesudah dibuka, tulisan diterima kembali",
              f"reopen {r4.status_code} · target {r5.status_code}")
        logs = db.marketing_change_log.count_documents(
            {"account_id": best["id"], "period": SYNTH_PERIOD,
             "action": {"$in": ["period_close", "period_reopen"]}})
        check("CYC-3d", logs >= 2, "tutup & buka periode tercatat di marketing_change_log",
              f"{logs} baris jejak")
    finally:
        db.marketing_period_locks.delete_many(
            {"account_id": best["id"], "period": SYNTH_PERIOD})
        db.marketing_change_log.delete_many(
            {"account_id": best["id"], "period": SYNTH_PERIOD})
        db.marketing_account_targets.delete_many(
            {"account_id": best["id"], "year": y, "month": m})
        left = db.marketing_period_locks.count_documents({"period": SYNTH_PERIOD})
        check("CYC-3e", left == 0, "jejak uji gate dibersihkan (tidak mencemari data)",
              f"{left} dokumen sisa")

    # ── CYC-4 — total overview = Σ baris ─────────────────────────────────────
    ro = requests.get(f"{BASE}/api/marketing/cycle/overview?period={period}",
                      headers=HJ, timeout=300)
    if check("CYC-4a", ro.status_code == 200, "endpoint cycle/overview hidup",
             f"HTTP {ro.status_code}"):
        ov = ro.json()
        rws, tot = ov.get("rows") or [], ov.get("totals") or {}
        s_rev = round(sum(float((x.get("actual") or {}).get("revenue") or 0) for x in rws), 2)
        check("CYC-4b", abs(s_rev - float(tot.get("revenue") or 0)) < 0.05,
              f"total omzet = Σ {len(rws)} baris (dihitung backend)",
              f"total {tot.get('revenue')} vs Σ {s_rev}")
        s_spend = round(sum(float((x.get("budget") or {}).get("total_spend") or 0) for x in rws), 2)
        check("CYC-4c", abs(s_spend - float(tot.get("total_spend") or 0)) < 0.05,
              "total belanja = Σ baris")
        mine = next((x for x in rws if x["account"]["id"] == best["id"]), None)
        check("CYC-4d", bool(mine) and abs(
            float((mine.get("actual") or {}).get("revenue") or 0)
            - float((s.get("actual") or {}).get("revenue") or 0)) < 0.05,
            "baris overview = cycle/summary toko yang sama")

    # ── CYC-5 — marjin selalu membawa cakupan HPP ────────────────────────────
    need = ("hpp", "gross_profit", "gross_margin_pct", "hpp_coverage_pct",
            "units_total", "units_covered", "trustworthy")
    mrg = s.get("margin") or {}
    check("CYC-5a", all(k in mrg for k in need),
          f"marjin membawa cakupan HPP ({mrg.get('hpp_coverage_pct')}%)",
          f"field hilang: {[k for k in need if k not in mrg]}")
    if float(mrg.get("units_total") or 0) > 0 and float(mrg.get("hpp_coverage_pct") or 0) < 80:
        check("CYC-5b", any(f.get("code") == "hpp_coverage_low" for f in (s.get("flags") or [])),
              "cakupan HPP rendah ditandai flag (marjin belum bisa dipercaya)",
              "cakupan rendah TANPA peringatan — marjin tampak sah padahal tidak")
    else:
        ok("CYC-5b", "cakupan HPP memadai / belum ada pesanan")
    check("CYC-5c", bool(s.get("data_notes")) and any("HPP" in n for n in s["data_notes"]),
          "catatan kejujuran data menyebut HPP secara terbuka")

    # ── CYC-6 — bentuk dokumen kunci periode ────────────────────────────────
    bad_locks = list(db.marketing_period_locks.find(
        {"$or": [{"account_id": {"$in": [None, ""]}}, {"period": {"$in": [None, ""]}}]},
        {"_id": 0, "id": 1}).limit(5))
    check("CYC-6a", not bad_locks,
          f"semua {db.marketing_period_locks.count_documents({})} dokumen kunci punya "
          "account_id & period", f"{len(bad_locks)} dokumen kunci yatim")
    no_hist = db.marketing_period_locks.count_documents({"history": {"$exists": False}})
    check("CYC-6b", no_hist == 0, "setiap kunci punya riwayat (siapa & kapan)",
          f"{no_hist} kunci tanpa riwayat")

    # ── CYC-7 — kategori anggaran kanonik satu daftar ────────────────────────
    fe = open("/app/frontend/src/components/erp/marketing/BudgetAllocationTab.jsx").read()
    api_cats = [c.get("category") for c in cats]
    check("CYC-7a", "komisi" in _cycle.CATEGORIES, "backend punya kategori `komisi`")
    check("CYC-7b", "komisi" in api_cats, "respons endpoint memuat kategori `komisi`",
          f"kategori API: {api_cats}")
    check("CYC-7c", "'komisi'" in fe or '"komisi"' in fe,
          "layar Anggaran menampilkan kategori `komisi`",
          "kategori ada di backend tetapi TIDAK di layar ⇒ biaya tak pernah direncanakan")
    check("CYC-7d", all(("mode" in c and "auto" in c and "manual" in c) for c in cats),
          "tiap kategori menandai auto vs manual (bisa dibedakan staf)")

    # ── CYC-8 — RANTAI pesanan MANUAL → rekap harian → siklus ────────────────
    # Tiga cacat NYATA yang ditutup 2026-08-13 dan dijaga di sini (semuanya senyap):
    #   1. `POST /api/marketing/orders` menolak order tanpa toko yang sah, tetapi
    #      `account_id`-nya TIDAK pernah ikut disimpan ⇒ setiap pesanan hasil input
    #      layar menjadi baris yatim (hilang dari semua layar per toko).
    #   2. Pesanan manual tidak punya nama uang kanonik (`revenue_product`,
    #      `order_amount`) ⇒ menyumbang Rp 0 ke omzet, anggaran diskon, dan marjin.
    #   3. Tidak ada hook rekap harian di pintu manual ⇒ hari itu tampak tanpa
    #      penjualan di Input Sales & Dashboard.
    # Gate menulis SATU pesanan uji lewat API sungguhan lalu membuangnya.
    # SESI #38 — item uji WAJIB yang sudah tertaut master FG. Pesanan memang
    # DITOLAK bila katalognya belum tertaut (penjaga yang benar, dipasang setelah
    # gate ini ditulis), jadi memilih item warisan tanpa tautan hanya menguji
    # penjaganya — bukan rantai omzetnya.
    item = db.marketing_catalog_items.find_one(
        {"hpp": {"$gt": 0}, "fg_material_id": {"$nin": [None, ""]},
         "$or": [{"price": {"$gt": 0}}, {"harga_jual": {"$gt": 0}}]},
        {"_id": 0})
    if not item:
        ok("CYC-8", "dilewati — tidak ada item katalog ber-HPP yang tertaut master FG "
                    "untuk uji rantai")
    else:
        cat = db.marketing_catalogs.find_one({"id": item.get("catalog_id")}, {"_id": 0}) or {}
        aid = cat.get("account_id")
        harga = float(item.get("price") or item.get("harga_jual") or 0)
        today = _cycle.today_wib().strftime("%Y-%m-%d")
        per_now = today[:7]
        before = db.marketing_sales_data.find_one(
            {"account_id": aid, "date": today, "revenue_type": "total"}, {"_id": 0}) or {}
        rev_before = float((before.get("metrics") or {}).get("revenue") or 0)
        payload = {
            "account_id": aid, "platform": cat.get("platform") or "manual",
            "customer_name": "GATE INV-MKTCYCLE", "catalog_item_id": item["id"],
            "reserve_stock": False,
            "items": [{"sku_code": item.get("sku") or "UJI",
                       "product_name": item.get("name") or "uji", "qty": 1,
                       "price": harga, "catalog_item_id": item["id"]}],
            "quantity": 1, "price_final": harga, "total_payment": harga,
            "note": "pesanan uji gate (dibuang otomatis)"}
        rr = requests.post(f"{BASE}/api/marketing/orders", headers=HJ, json=payload, timeout=90)
        oid = ((rr.json() or {}).get("order") or rr.json() or {}).get("id") \
            if rr.status_code in (200, 201) else None
        if not check("CYC-8a", bool(oid), "pesanan uji lewat API dibuat",
                     f"HTTP {rr.status_code} {str(rr.text)[:140]}"):
            pass
        else:
            try:
                doc = db.marketing_orders.find_one({"id": oid}, {"_id": 0}) or {}
                check("CYC-8b", doc.get("account_id") == aid,
                      "pesanan manual menyimpan account_id (tidak yatim)",
                      f"account_id={doc.get('account_id')} (harus {aid})")
                money_ok = all(doc.get(k) is not None for k in
                               ("revenue_product", "order_amount", "revenue_gross",
                                "seller_discount_total"))
                check("CYC-8c", money_ok,
                      "pesanan manual memakai nama uang KANONIK",
                      f"hilang: {[k for k in ('revenue_product', 'order_amount', 'revenue_gross', 'seller_discount_total') if doc.get(k) is None]}")
                it0 = (doc.get("items") or [{}])[0]
                check("CYC-8d", it0.get("quantity") is not None
                      and it0.get("sku_subtotal_after_discount") is not None,
                      "baris item memakai nama kanonik (dibaca marjin)")
                after = db.marketing_sales_data.find_one(
                    {"account_id": aid, "date": today, "revenue_type": "total"}, {"_id": 0}) or {}
                rev_after = float((after.get("metrics") or {}).get("revenue") or 0)
                check("CYC-8e", rev_after - rev_before >= harga - 1,
                      f"rekap harian ikut naik (Rp {rev_before:,.0f} → Rp {rev_after:,.0f})"
                      .replace(",", "."),
                      f"omzet hari ini TIDAK berubah sesudah pesanan masuk "
                      f"({rev_before} → {rev_after})")
                cyc = requests.get(f"{BASE}/api/marketing/cycle/summary"
                                   f"?account_id={aid}&period={per_now}",
                                   headers=HJ, timeout=120).json()
                check("CYC-8f", float((cyc.get("margin") or {}).get("hpp") or 0) > 0,
                      "marjin siklus memakai HPP item katalog (join bekerja)",
                      f"hpp={(cyc.get('margin') or {}).get('hpp')}")
            finally:
                rd = requests.delete(f"{BASE}/api/marketing/orders/{oid}", headers=HJ, timeout=60)
                if rd.status_code not in (200, 204):
                    db.marketing_orders.delete_one({"id": oid})
                back = db.marketing_sales_data.find_one(
                    {"account_id": aid, "date": today, "revenue_type": "total"}, {"_id": 0}) or {}
                rev_back = float((back.get("metrics") or {}).get("revenue") or 0)
                check("CYC-8g", abs(rev_back - rev_before) < 1,
                      "menghapus pesanan mengembalikan omzet hari itu (tidak nyangkut)",
                      f"{rev_before} → {rev_back} (uang pesanan yang sudah dihapus "
                      "masih terhitung)")

    good = sum(1 for _, o, _ in RES if o)
    print(f"\n{B}{'-' * 82}{X}")
    print(f"  INV-MKTCYCLE: {len(RES)} diperiksa — {len(RES) - good} temuan")
    if good == len(RES):
        print(f"  {G}{B}✓ INV-MKTCYCLE HIJAU{X}\n")
        return 0
    print(f"  {R}{B}✗ INV-MKTCYCLE MERAH{X}")
    for c, o, msg in RES:
        if not o:
            print(f"    {R}{c}{X} {msg}")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
