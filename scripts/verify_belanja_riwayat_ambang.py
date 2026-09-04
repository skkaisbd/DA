#!/usr/bin/env python3
"""verify_belanja_riwayat_ambang.py — GATE **INV-F38** (2026-08-23, sesi #33).

MENJAGA TIGA PEKERJAAN SESI #33 AGAR TIDAK DIAM-DIAM MATI
---------------------------------------------------------
(1) **Isi Ambang Massal.** Layar Ambang Stok sudah ada sejak W3, tetapi usulannya
    HANYA lahir dari pemakaian 30 hari; terukur di data hidup hanya **5 dari 335
    material** yang punya pemakaian ⇒ 330 material tidak punya jalan massal apa
    pun. Sekarang ada empat DASAR (`usage_30d`/`purchase_lot`/`percent_onhand`/
    `fixed`) yang selalu bisa dipratinjau, bisa dikosongkan, dan MENYIMPAN
    dasarnya + siapa + kapan.
(2) **Riwayat Harga Barang.** `rahaza_material_cost_history` dipakai semua jenis
    material, tetapi satu-satunya pembacanya adalah layar AKSESORIS — tanpa
    filter jenis, sehingga layar itu menampilkan riwayat KAIN.
(3) **Daftar Belanja Mingguan.** Sebelum sesi #33 tidak ada layar yang menjawab
    "minggu ini beli apa, berapa, berapa uangnya", dan alert stok tidak punya
    jembatan ke Permintaan Pengadaan.

ANGKA UJI — DIHITUNG TANGAN LEBIH DAHULU
----------------------------------------
  KAIN-G  terima 100 m @20.000 ; 100 m @30.000 (stok 100)
          ⇒ (100×20.000 + 100×30.000)/200 = **25.000/m** · riwayat +25,00%
          rata-rata 1 kali beli (100+100)/2 = 100 m ⇒ `purchase_lot` ×0,5 = min **50** / rp **60**
  ACC-G   terima 120 pcs @1.000 ⇒ 1.000/pcs · satuan beli lusin (12 pcs)
          `percent_onhand` 25% dari 120 ⇒ min **30** / rp **36**
  KAIN-H  terima 50 m @0 ⇒ tanpa harga ⇒ **unvalued**
  ACC-H   tidak pernah dibeli ⇒ riwayat KOSONG + alasannya

  BELANJA MINGGUAN (ambang `fixed`)
    KAIN-G min 300, stok 200 ⇒ kurang 100 m × 25.000 = **Rp2.500.000**
    ACC-G  min 200, stok 120 ⇒ kurang 80 pcs ⇒ 80/12 = 6,67 ⇒ **7 lusin** (84 pcs)
                              × Rp12.000/lusin = **Rp84.000**
    KAIN-H min 100, stok  50 ⇒ kurang 50 m TANPA harga ⇒ tidak menambah total
    total baris uji = **Rp2.584.000** · PR dari 2 baris = **Rp2.584.000**

INVARIAN (16)
-------------
  C1  statik: SSOT belanja mingguan memakai `stock_thresholds` + `stock_service`
      (satu definisi "perlu beli", bukan rumus kedua)
  C2  statik: `core/stock_thresholds` punya bulk_fill/bulk_clear/purchase_lot_map
      dan endpointnya terdaftar
  C3  statik: PR dari belanja mingguan memakai SSOT Portal Pengadaan `build_pr_doc`
  C4  statik: LAYAR terdaftar (registry + sidebar) & panel Isi Massal ada di layar
  C5  statik: riwayat harga aksesoris DISARING jenis (kain tidak bisa bocor lagi)
  C6  runtime: riwayat harga lahir dari pembelian (old → new + % perubahan + ringkasan)
  C7  runtime: barang tanpa riwayat ⇒ kosong + ALASAN (bukan error/tabel bisu)
  C8  runtime: `/api/acc/valuation/cost-history` tidak memuat material kain
  C9  runtime: `purchase_lot` mengisi barang yang belum pernah dipakai; dry-run TIDAK menulis
  C10 runtime: `percent_onhand` & `fixed` aritmetikanya persis + dasar/siapa/kapan tercatat
  C11 runtime: sesudah ambang terisi, alert stok berbunyi dengan kekurangan yang benar
  C12 runtime: kosongkan massal ⇒ ambang & alert kembali seperti semula
  C13 runtime: daftar belanja: kekurangan → qty beli (dibulatkan ke atas ke satuan
      beli) → harga → total; unvalued tidak menambah total; tanpa ambang DIKATAKAN
  C14 runtime: create-pr ⇒ PR draft benar + ANTI DOBEL BELANJA + tercatat di riwayat layar
  C15 KEADAAN AKHIR: tidak ada artefak uji tertinggal (material/PR/ambang) dan
      total stok kembali — penjaga terhadap alat ukur yang bocor (pola C12 INV-F37)
  C16 KEADAAN AKHIR: **0 baris riwayat harga YATIM** di seluruh database. Layar
      Riwayat Harga Barang membuat kebocoran alat ukur KELIHATAN: gate INV-F35 &
      INV-F24 membeli + memotong kain lalu menghapus MATERIALNYA tanpa menghapus
      riwayat harganya ⇒ 3 baris yatim menumpuk tiap kali `gate.sh` dijalankan
      (terukur: 10 dari 19 baris di container ini adalah sampah alat ukur).

Pakai:  python3 scripts/verify_belanja_riwayat_ambang.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("%H%M%S")
PREFIX = f"GATE38-{STAMP}"
MARK = f"GATE INV-F38 {STAMP}"


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓ {code}{X} {msg}" + (f"\n         {C}{detail}{X}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} {msg}{X}" + (f"\n         {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}▶ {t}{X}")


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d):
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:240]


def near(a, b, tol=0.51):
    try:
        return abs(float(a or 0) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def money(v):
    try:
        return f"Rp{float(v or 0):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def rd(p):
    try:
        return (ROOT / p).read_text(errors="ignore")
    except OSError:
        return ""


def total_stock(db):
    row = list(db.rahaza_material_stock.aggregate(
        [{"$group": {"_id": None, "t": {"$sum": "$qty"}}}]))
    return round(float(row[0]["t"]) if row else 0.0, 4)


def row_of(rows, val, key="material_id"):
    return next((r for r in (rows or []) if r.get(key) == val), None)


# ══════════════════════════════════════════════════════════════════════════════
# BAGIAN STATIK — kontrak kode & layar (murah, tak butuh backend)
# ══════════════════════════════════════════════════════════════════════════════
def static_checks():
    head("STATIK — satu definisi, satu SSOT, dan layarnya benar-benar ada")

    sl = rd("backend/core/shopping_list.py")
    mch = rd("backend/core/material_cost_history.py")
    if (sl and mch and "stock_thresholds.resolve_threshold" in sl
            and "stock_service.onhand_map" in sl and "status_of" in sl):
        ok("C1", "belanja mingguan memakai SSOT ambang + stok kanonik (tidak ada rumus kedua)",
           "core/shopping_list.py → stock_thresholds.resolve_threshold + "
           "stock_service.onhand_map")
    else:
        bad("C1", "SSOT belanja mingguan tidak ada / memakai rumusnya sendiri",
            f"shopping_list={len(sl)}B material_cost_history={len(mch)}B")

    th = rd("backend/core/stock_thresholds.py")
    route_th = rd("backend/routes/rahaza_inventory_thresholds.py")
    need_fn = ["async def bulk_fill", "async def bulk_clear", "async def purchase_lot_map",
               "BASIS_LABEL"]
    miss_fn = [n for n in need_fn if n not in th]
    need_ep = ['@router.post("/stock-thresholds/bulk-fill")',
               '@router.post("/stock-thresholds/bulk-clear")']
    miss_ep = [n for n in need_ep if n not in route_th]
    if not miss_fn and not miss_ep and "threshold_basis" in th:
        ok("C2", "isi/kosongkan ambang massal ada di SSOT + endpointnya terdaftar",
           "bulk_fill · bulk_clear · purchase_lot_map · 4 dasar (BASIS_LABEL) · "
           "jejak threshold_basis")
    else:
        bad("C2", "fitur isi ambang massal tidak lengkap",
            f"fungsi hilang={miss_fn} endpoint hilang={miss_ep}")

    route_sl = rd("backend/routes/rahaza_shopping_list.py")
    proc = rd("backend/routes/dewi_procurement.py")
    if ("build_pr_doc" in route_sl and "async def build_pr_doc" in proc
            and "origin" in proc):
        ok("C3", "PR belanja mingguan memakai SSOT Portal Pengadaan (bukan dokumen tandingan)",
           "routes/rahaza_shopping_list.py → dewi_procurement.build_pr_doc(origin=…)")
    else:
        bad("C3", "PR dari belanja mingguan menyusun dokumennya sendiri (bisa menyimpang)",
            f"route_sl={'build_pr_doc' in route_sl} proc_fn={'async def build_pr_doc' in proc}")

    reg = rd("frontend/src/components/erp/moduleRegistry.js")
    nav = rd("frontend/src/components/erp/portal-shell/portalNav.js")
    thr_ui = rd("frontend/src/components/erp/StockThresholdsModule.jsx")
    shop_ui = rd("frontend/src/components/erp/WeeklyShoppingListModule.jsx")
    cost_ui = rd("frontend/src/components/erp/MaterialCostHistoryModule.jsx")
    need_ui = {
        "registry wh-shopping-list": "'wh-shopping-list':" in reg,
        "registry wh-cost-history": "'wh-cost-history':" in reg,
        "sidebar wh-shopping-list": "'wh-shopping-list'" in nav,
        "sidebar wh-cost-history": "'wh-cost-history'" in nav,
        "panel isi massal": 'data-testid="threshold-bulk-panel"' in thr_ui,
        "dasar purchase_lot": 'threshold-mode-${m.key}' in thr_ui and "purchase_lot" in thr_ui,
        "pratinjau": 'data-testid="threshold-bulk-preview"' in thr_ui,
        "terapkan": 'data-testid="threshold-bulk-apply"' in thr_ui,
        "kosongkan": 'data-testid="threshold-bulk-clear"' in thr_ui,
        "kolom dasar": "threshold-basis-" in thr_ui,
        "tabel belanja": 'data-testid="shopping-table"' in shop_ui,
        "tombol buat PR": 'data-testid="shopping-create-pr"' in shop_ui,
        "peringatan tanpa ambang": 'data-testid="shopping-threshold-notice"' in shop_ui,
        "grafik riwayat harga": 'data-testid="cost-chart"' in cost_ui,
        "alasan riwayat kosong": 'data-testid="cost-empty-reason"' in cost_ui,
    }
    miss_ui = [k for k, v in need_ui.items() if not v]
    if not miss_ui:
        ok("C4", "layar lengkap: dua pintu baru terdaftar + panel Isi Massal + kolom Dasar",
           f"{len(need_ui)} penanda layar ditemukan (registry · sidebar · testid)")
    else:
        bad("C4", "ada fitur backend tanpa pintu/penanda di layar", f"hilang: {miss_ui}")

    acc_core = rd("backend/core/accessory_valuation.py")
    acc_route = rd("backend/routes/dewi_accessories_valuation.py")
    if ("ACCESSORY_TYPES" in acc_core and "types" in acc_core.split("async def cost_history")[1][:600]
            and "ACCESSORY_TYPES" in acc_route):
        ok("C5", "riwayat harga aksesoris disaring jenis (kain tidak bisa bocor ke layar itu)",
           "accessory_valuation.cost_history(types=ACCESSORY_TYPES) dipanggil route aksesoris")
    else:
        bad("C5", "layar aksesoris masih membaca riwayat semua jenis material",
            f"core={'ACCESSORY_TYPES' in acc_core} route={'ACCESSORY_TYPES' in acc_route}")


# ══════════════════════════════════════════════════════════════════════════════
def receive(token, mat, qty, price, loc, rolls=None):
    item = {
        "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
        "expected_qty": qty, "received_qty": qty, "rejected_qty": 0,
        "unit": mat.get("unit") or "pcs", "unit_price": price,
        "inspection_status": "passed", "lot_number": f"LOT-{STAMP}",
    }
    if rolls:
        item["rolls"] = rolls
    st, gr = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": f"Pemasok {PREFIX}",
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": MARK, "items": [item]})
    if st not in (200, 201) or not (gr or {}).get("id"):
        return None, f"GR gagal HTTP {st} · {det(gr)}"
    st, upd = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        return None, f"terima GR gagal HTTP {st} · {det(upd)}"
    return gr, ""


def fill_fixed(token, mid, mn, rp=0):
    return call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
        "mode": "fixed", "dry_run": False,
        "params": {"min_stock_qty": mn, "reorder_point": rp},
        "scope": {"material_ids": [mid]}})


def cleanup(db, ctx):
    mat_ids = [v for k, v in ctx.items() if k.startswith("mat_")]
    gr_ids = [v for k, v in ctx.items() if k.startswith("gr_")]
    pr_ids = [v for k, v in ctx.items() if k.startswith("pr_")]
    counts = {}
    for name, coll, q in (
        ("PR", "dewi_procurement_requests", {"id": {"$in": pr_ids}}),
        ("kartu", "rahaza_material_movements", {"material_id": {"$in": mat_ids}}),
        ("wh_mv", "warehouse_movements", {"material_id": {"$in": mat_ids}}),
        ("roll_mv", "wh_fabric_roll_movements", {"material_id": {"$in": mat_ids}}),
        ("roll", "wh_fabric_rolls", {"material_id": {"$in": mat_ids}}),
        ("GR", "warehouse_receiving", {"id": {"$in": gr_ids}}),
        ("stok", "rahaza_material_stock", {"material_id": {"$in": mat_ids}}),
        ("ledger", "rahaza_stock_ledger", {"material_id": {"$in": mat_ids}}),
        ("harga", "rahaza_material_cost_history", {"material_id": {"$in": mat_ids}}),
        # jaring pengaman: apa pun yang lahir dengan awalan kode gate ini
        ("master", "rahaza_materials", {"$or": [{"id": {"$in": mat_ids}},
                                                {"code": {"$regex": f"^{PREFIX}"}}]}),
    ):
        try:
            counts[name] = db[coll].delete_many(q).deleted_count
        except Exception:  # noqa: BLE001
            counts[name] = -1
    print(f"  {Y}bersih-bersih: " + " · ".join(f"{k}={v}" for k, v in counts.items()) + X)


# ══════════════════════════════════════════════════════════════════════════════
def main():  # noqa: C901 — satu alur uji berurutan, sengaja dibaca atas→bawah
    print(f"{C}{B}INV-F38 — BELANJA MINGGUAN · RIWAYAT HARGA · ISI AMBANG MASSAL{X}")
    static_checks()

    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    ctx: dict = {}
    stock0 = total_stock(db)
    th0 = db.rahaza_materials.count_documents(
        {"active": True, "$or": [{"min_stock_qty": {"$gt": 0}}, {"reorder_point": {"$gt": 0}}]})

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        bad("SETUP", f"login gagal (HTTP {st})", det(d))
        return 1

    try:
        head("SIAPKAN — barang dibeli sungguhan (harga lahir dari pembelian)")
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), None)
        if not loc:
            bad("SETUP", "tidak ada lokasi gudang")
            return 1

        mats = {}
        for key, payload in (
            ("mat_kain_g", {"code": f"{PREFIX}-KAIN-G", "name": f"Kain Gate38 G {STAMP}",
                            "type": "fabric", "unit": "m", "notes": MARK}),
            ("mat_kain_h", {"code": f"{PREFIX}-KAIN-H", "name": f"Kain Gate38 H {STAMP}",
                            "type": "fabric", "unit": "m", "notes": MARK}),
            ("mat_acc_g", {"code": f"{PREFIX}-ACC-G", "name": f"Aksesoris Gate38 G {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK,
                           "uoms": [{"code": "pcs", "name": "Pcs", "factor": 1, "is_base": True},
                                    {"code": "lusin", "name": "Lusin", "factor": 12}],
                           "purchase_uom": "lusin"}),
            ("mat_acc_h", {"code": f"{PREFIX}-ACC-H", "name": f"Aksesoris Gate38 H {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK}),
        ):
            stx, m = call("POST", "/api/rahaza/materials", token, payload)
            if stx != 200 or not (m or {}).get("id"):
                bad("SETUP", f"gagal membuat {payload['code']} HTTP {stx}", det(m))
                return 1
            ctx[key] = m["id"]
            mats[key] = m

        for key, qty, price, rolls in (
            ("mat_kain_g", 100, 20000, [{"qty": 100, "color_lot": f"L1-{STAMP}", "notes": ""}]),
            ("mat_acc_g", 120, 1000, None),
            ("mat_kain_h", 50, 0, [{"qty": 50, "color_lot": f"L2-{STAMP}", "notes": ""}]),
            ("mat_kain_g", 100, 30000, [{"qty": 100, "color_lot": f"L3-{STAMP}", "notes": ""}]),
        ):
            gr, err = receive(token, mats[key], qty, price, loc, rolls)
            if not gr:
                bad("SETUP", f"penerimaan {mats[key]['code']} gagal", err)
                return 1
            ctx[f"gr_{key}_{qty}_{price}"] = gr["id"]

        mg = db.rahaza_materials.find_one({"id": ctx["mat_kain_g"]}, {"_id": 0}) or {}
        if not near(mg.get("unit_cost"), 25000, 1):
            bad("SETUP", "rata-rata bergerak pembelian tidak seperti hitungan tangan",
                f"KAIN-G unit_cost={mg.get('unit_cost')} (harap 25.000)")
            return 1

        # ── RIWAYAT HARGA ────────────────────────────────────────────────────
        head("RUNTIME — RIWAYAT HARGA BARANG")
        st, h = call("GET",
                     f"/api/rahaza/material-costs/history?material_id={ctx['mat_kain_g']}", token)
        items = (h or {}).get("items") or []
        s = (h or {}).get("summary") or {}
        if (st == 200 and len(items) == 2
                and near(items[1].get("new_unit_cost"), 20000)
                and near(items[0].get("old_unit_cost"), 20000)
                and near(items[0].get("new_unit_cost"), 25000)
                and near(items[0].get("change_pct"), 25, 0.05)
                and near(s.get("current_unit_cost"), 25000)
                and near(s.get("first_unit_cost"), 20000)
                and near(s.get("max_unit_cost"), 25000)
                and int(s.get("changes") or 0) == 2):
            ok("C6", "riwayat harga lahir dari pembelian: old → new, % perubahan, ringkasan benar",
               f"0 → {money(20000)} lalu {money(20000)} → {money(25000)} (+{items[0]['change_pct']}%) "
               f"· ringkasan: kini {money(s['current_unit_cost'])}, pertama "
               f"{money(s['first_unit_cost'])}, {s['changes']} kali berubah")
        else:
            bad("C6", "riwayat/ringkasan harga tidak seperti hitungan tangan",
                f"HTTP {st} · {len(items)} baris · items={json.dumps(items)[:200]} · "
                f"summary={json.dumps(s)[:150]}")

        st, h0 = call("GET",
                      f"/api/rahaza/material-costs/history?material_id={ctx['mat_acc_h']}", token)
        reason = str((h0 or {}).get("reason") or "")
        if st == 200 and (h0 or {}).get("items") == [] and len(reason) > 20:
            ok("C7", "barang tanpa riwayat: kosong + ALASAN + jalan keluarnya (bukan tabel bisu)",
               reason[:140])
        else:
            bad("C7", "keadaan kosong tidak dijelaskan",
                f"HTTP {st} · items={(h0 or {}).get('items')} · reason='{reason[:80]}'")

        st, accs = call("GET", "/api/acc/valuation/cost-history?limit=300", token)
        arows = accs if isinstance(accs, list) else (accs or {}).get("items") or []
        aids = {r.get("material_id") for r in arows}
        leak = {ctx["mat_kain_g"], ctx["mat_kain_h"]} & aids
        if st == 200 and not leak and ctx["mat_acc_g"] in aids:
            ok("C8", "layar Valuasi Aksesoris hanya berisi aksesoris",
               f"{len(arows)} baris · aksesoris uji ADA · kain uji TIDAK ada")
        else:
            bad("C8", "riwayat aksesoris masih mencampur material kain",
                f"HTTP {st} · kain_bocor={len(leak)} · acc_ada={ctx['mat_acc_g'] in aids}")

        # ── ISI AMBANG MASSAL ────────────────────────────────────────────────
        head("RUNTIME — ISI AMBANG MASSAL (4 dasar, pratinjau, jejak, pembatal)")
        st, dry = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "purchase_lot", "dry_run": True, "params": {"lot_multiplier": 0.5},
            "scope": {"material_ids": [ctx["mat_kain_g"], ctx["mat_acc_h"]]}})
        after_dry = db.rahaza_materials.find_one({"id": ctx["mat_kain_g"]}, {"_id": 0}) or {}
        st2, appl = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "purchase_lot", "dry_run": False, "params": {"lot_multiplier": 0.5},
            "scope": {"material_ids": [ctx["mat_kain_g"]]}})
        mg = db.rahaza_materials.find_one({"id": ctx["mat_kain_g"]}, {"_id": 0}) or {}
        skipped_h = any(x.get("material_id") == ctx["mat_acc_h"]
                        for x in ((dry or {}).get("skipped") or []))
        if (st == 200 and st2 == 200
                and int((dry or {}).get("applied") or 0) == 0
                and not float(after_dry.get("min_stock_qty") or 0)
                and int((dry or {}).get("eligible") or 0) == 1 and skipped_h
                and near(mg.get("min_stock_qty"), 50) and near(mg.get("reorder_point"), 60)
                and mg.get("threshold_basis") == "purchase_lot"):
            ok("C9", "dasar `purchase_lot` mengisi barang tanpa pemakaian; pratinjau tidak menulis",
               f"pratinjau: 1 layak, 1 dilewati (tanpa pembelian) & 0 ditulis → terapkan: "
               f"min {mg.get('min_stock_qty')} · pesan ulang {mg.get('reorder_point')} "
               f"(rata-rata 1 kali beli 100 m × 0,5)")
        else:
            bad("C9", "purchase_lot / pratinjau tidak bekerja seperti kontraknya",
                f"HTTP {st}/{st2} · dry_applied={(dry or {}).get('applied')} "
                f"eligible={(dry or {}).get('eligible')} dilewati_h={skipped_h} "
                f"min={mg.get('min_stock_qty')} rp={mg.get('reorder_point')} "
                f"basis={mg.get('threshold_basis')}")

        st, pc = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "percent_onhand", "dry_run": False, "params": {"percent": 25},
            "scope": {"material_ids": [ctx["mat_acc_g"]]}})
        ma = db.rahaza_materials.find_one({"id": ctx["mat_acc_g"]}, {"_id": 0}) or {}
        st2, fx = fill_fixed(token, ctx["mat_kain_h"], 100, 0)
        mh = db.rahaza_materials.find_one({"id": ctx["mat_kain_h"]}, {"_id": 0}) or {}
        if (st == 200 and st2 == 200
                and near(ma.get("min_stock_qty"), 30) and near(ma.get("reorder_point"), 36)
                and ma.get("threshold_basis") == "percent_onhand"
                and (ma.get("threshold_set_by") or "") and (ma.get("threshold_set_at") or "")
                and (ma.get("threshold_basis_note") or "")
                and near(mh.get("min_stock_qty"), 100) and mh.get("threshold_basis") == "fixed"):
            ok("C10", "`percent_onhand` & `fixed` persis + DASAR/siapa/kapan tercatat",
               f"25% dari 120 pcs ⇒ min {ma['min_stock_qty']} · pesan ulang {ma['reorder_point']} "
               f"· '{ma['threshold_basis_note']}' oleh {ma['threshold_set_by']} "
               f"{str(ma['threshold_set_at'])[:19]}")
        else:
            bad("C10", "aritmetika/jejak dasar ambang salah",
                f"HTTP {st}/{st2} · acc min={ma.get('min_stock_qty')} rp={ma.get('reorder_point')} "
                f"basis={ma.get('threshold_basis')} by={ma.get('threshold_set_by')} "
                f"kain_h min={mh.get('min_stock_qty')} · {det(pc)} {det(fx)}")

        st, _ = fill_fixed(token, ctx["mat_kain_g"], 300, 0)
        st, alerts = call("GET", "/api/rahaza/materials/reorder-alerts", token)
        arows = alerts if isinstance(alerts, list) else (alerts or {}).get("items") or []
        a_g = row_of(arows, ctx["mat_kain_g"], "id")
        st2, summ = call("GET", "/api/rahaza/stock-thresholds/summary", token)
        if a_g and near(a_g.get("shortage"), 100) and int((summ or {}).get("alerts") or 0) >= 1:
            ok("C11", "alert stok berbunyi sesudah ambang terisi, kekurangannya benar",
               f"KAIN-G stok 200 vs ambang 300 ⇒ kurang {a_g.get('shortage')} m · "
               f"ringkasan menyebut {summ.get('alerts')} alert")
        else:
            bad("C11", "alert tidak berbunyi / kekurangan salah",
                f"shortage={(a_g or {}).get('shortage')} (harap 100) · "
                f"ringkasan={json.dumps(summ)[:150]}")

        st, clr = call("POST", "/api/rahaza/stock-thresholds/bulk-clear", token,
                       {"material_ids": [ctx["mat_kain_g"]]})
        mg = db.rahaza_materials.find_one({"id": ctx["mat_kain_g"]}, {"_id": 0}) or {}
        st2, alerts2 = call("GET", "/api/rahaza/materials/reorder-alerts", token)
        arows2 = alerts2 if isinstance(alerts2, list) else (alerts2 or {}).get("items") or []
        if (st == 200 and int((clr or {}).get("cleared") or 0) == 1
                and not float(mg.get("min_stock_qty") or 0)
                and not float(mg.get("reorder_point") or 0)
                and not float(mg.get("min_stock") or 0)
                and row_of(arows2, ctx["mat_kain_g"], "id") is None):
            ok("C12", "kosongkan massal: ambang benar-benar bersih & alertnya diam lagi",
               "min_stock_qty · reorder_point · min_stock (legacy) semuanya dikosongkan")
        else:
            bad("C12", "kosongkan massal tidak tuntas (ambang atau alert masih tersisa)",
                f"cleared={(clr or {}).get('cleared')} min={mg.get('min_stock_qty')} "
                f"rp={mg.get('reorder_point')} legacy={mg.get('min_stock')} "
                f"masih_alert={row_of(arows2, ctx['mat_kain_g'], 'id') is not None}")

        # ── DAFTAR BELANJA MINGGUAN ──────────────────────────────────────────
        head("RUNTIME — DAFTAR BELANJA MINGGUAN & JEMBATAN KE PR")
        fill_fixed(token, ctx["mat_kain_g"], 300, 0)
        fill_fixed(token, ctx["mat_acc_g"], 200, 0)
        fill_fixed(token, ctx["mat_kain_h"], 100, 0)

        st, wk = call("GET", "/api/rahaza/shopping-list/weekly", token)
        rows = (wk or {}).get("rows") or []
        summary = (wk or {}).get("summary") or {}
        r_g, r_a, r_h = (row_of(rows, ctx["mat_kain_g"]), row_of(rows, ctx["mat_acc_g"]),
                         row_of(rows, ctx["mat_kain_h"]))
        poc_total = sum(float((row_of(rows, m) or {}).get("est_total") or 0)
                        for m in (ctx["mat_kain_g"], ctx["mat_acc_g"], ctx["mat_kain_h"]))
        if (st == 200 and r_g and r_a and r_h
                and near(r_g.get("shortage"), 100) and near(r_g.get("qty_buy"), 100)
                and near(r_g.get("est_total"), 2_500_000, 1)
                and near(r_a.get("shortage"), 80) and near(r_a.get("qty_buy"), 7)
                and r_a.get("purchase_uom") == "lusin" and near(r_a.get("qty_buy_base"), 84)
                and near(r_a.get("est_total"), 84_000, 1)
                and r_h.get("value_status") == "unvalued" and near(r_h.get("est_total"), 0)
                and near(poc_total, 2_584_000, 1)
                and int(summary.get("unvalued_count") or 0) >= 1
                and int(summary.get("without_threshold") or 0) >= 1
                and len(str(summary.get("without_threshold_note") or "")) > 20):
            ok("C13", "daftar belanja: kurang → qty beli (dibulatkan ke satuan beli) → harga → total",
               f"KAIN-G kurang 100 m ⇒ 100 m = {money(r_g['est_total'])} · ACC-G kurang 80 pcs ⇒ "
               f"7 lusin (84 pcs) = {money(r_a['est_total'])} · KAIN-H unvalued (tidak menambah "
               f"total) · total baris uji {money(poc_total)} · "
               f"{summary['without_threshold']} barang tanpa ambang DIKATAKAN")
        else:
            bad("C13", "angka daftar belanja tidak seperti hitungan tangan",
                f"HTTP {st} · G={json.dumps(r_g)[:160]} · A={json.dumps(r_a)[:160]} · "
                f"H={json.dumps(r_h)[:120]} · total={poc_total}")

        st, pr = call("POST", "/api/rahaza/shopping-list/create-pr", token,
                      {"material_ids": [ctx["mat_kain_g"], ctx["mat_acc_g"]], "notes": MARK})
        doc = (pr or {}).get("request") or {}
        if doc.get("id"):
            ctx["pr_1"] = doc["id"]
        p_g = row_of(doc.get("items") or [], ctx["mat_kain_g"])
        p_a = row_of(doc.get("items") or [], ctx["mat_acc_g"])
        st2, wk2 = call("GET", "/api/rahaza/shopping-list/weekly", token)
        rows2 = (wk2 or {}).get("rows") or []
        s2 = (wk2 or {}).get("summary") or {}
        q_g, q_a = row_of(rows2, ctx["mat_kain_g"]), row_of(rows2, ctx["mat_acc_g"])
        st3, hist = call("GET", "/api/rahaza/shopping-list/history?limit=50", token)
        in_hist = any(x.get("number") == doc.get("request_number")
                      for x in ((hist or {}).get("items") or []))
        if (st in (200, 201) and doc.get("request_number") and doc.get("status") == "draft"
                and p_g and near(p_g.get("qty"), 100) and near(p_g.get("qty_base"), 100)
                and near(p_g.get("estimated_price"), 25000, 1)
                and p_a and near(p_a.get("qty"), 7) and p_a.get("uom") == "lusin"
                and near(p_a.get("qty_base"), 84)
                and near(p_a.get("estimated_price_base"), 1000, 1)
                and near(doc.get("total_estimated"), 2_584_000, 1)
                and q_g and q_a and q_g.get("already_requested") and q_a.get("already_requested")
                and int(s2.get("need_buy") or 0) == max(0, int(summary.get("need_buy") or 0) - 2)
                and in_hist):
            ok("C14", "PR draft benar + ANTI DOBEL BELANJA + tercatat di riwayat layar",
               f"{doc['request_number']} total {money(doc['total_estimated'])} · KAIN-G 100 m @"
               f"{money(p_g['estimated_price'])} · ACC-G 7 lusin (84 pcs, "
               f"{money(p_a['estimated_price_base'])}/pcs) · perlu dibeli "
               f"{summary.get('need_buy')} → {s2.get('need_buy')}")
        else:
            bad("C14", "jembatan ke PR / penjaga anti dobel belanja tidak bekerja",
                f"HTTP {st}/{st2}/{st3} · doc={json.dumps(doc)[:220]} · "
                f"g_ber_pr={(q_g or {}).get('already_requested')} "
                f"a_ber_pr={(q_a or {}).get('already_requested')} · "
                f"need_buy {summary.get('need_buy')}→{s2.get('need_buy')} · riwayat={in_hist}")

    finally:
        head("BERSIH-BERSIH & KEADAAN AKHIR")
        call("POST", "/api/rahaza/stock-thresholds/bulk-clear", token,
             {"material_ids": [v for k, v in ctx.items() if k.startswith("mat_")]})
        cleanup(db, ctx)
        left_mat = db.rahaza_materials.count_documents({"code": {"$regex": "^GATE38-"}})
        left_pr = db.dewi_procurement_requests.count_documents({"description": {"$regex": MARK}})
        s1 = total_stock(db)
        th1 = db.rahaza_materials.count_documents(
            {"active": True, "$or": [{"min_stock_qty": {"$gt": 0}}, {"reorder_point": {"$gt": 0}}]})
        if left_mat == 0 and left_pr == 0 and near(s1, stock0, 0.01) and th1 == th0:
            ok("C15", "KEADAAN AKHIR bersih: alat ukur tidak meninggalkan sampah",
               f"0 master uji · 0 PR uji · total stok {s1:,.2f} == {stock0:,.2f} · "
               f"material berambang {th1} == {th0}")
        else:
            bad("C15", "alat ukur MEMBOCORKAN data ke database pemilik",
                f"master tersisa={left_mat} · PR tersisa={left_pr} · stok {s1:,.2f} vs "
                f"{stock0:,.2f} · berambang {th1} vs {th0}")

        # C16 — KEADAAN AKHIR: tidak boleh ada baris RIWAYAT HARGA YATIM.
        # Pola yang sama dengan C12 INV-F37: layar baru (Riwayat Harga Barang)
        # membuat kebocoran alat ukur KELIHATAN. Terukur sesi #33: gate INV-F35
        # & INV-F24 membeli + memotong kain lalu menghapus MATERIALNYA tanpa
        # menghapus riwayat harganya ⇒ 3 baris yatim menumpuk SETIAP kali
        # gate.sh dijalankan (10 dari 19 baris di container ini adalah sampah).
        # Gate ini berjalan PALING AKHIR di rangkaian F-gate, jadi kebocoran
        # gate mana pun akan MERAH di sini.
        ids = {m["id"] for m in db.rahaza_materials.find({}, {"_id": 0, "id": 1}) if m.get("id")}
        orphan = [h for h in db.rahaza_material_cost_history.find({}, {"_id": 0})
                  if h.get("material_id") not in ids]
        if not orphan:
            print(f"  {C}riwayat harga: "
                  f"{db.rahaza_material_cost_history.count_documents({})} baris, 0 yatim{X}")
            ok("C16", "0 baris riwayat harga yatim — tidak ada alat ukur yang membocorkan riwayat",
               "setiap baris riwayat masih punya master barangnya")
        else:
            sample = "; ".join(
                f"{str(o.get('created_at'))[:19]} {o.get('source')} "
                f"{o.get('old_unit_cost')}→{o.get('new_unit_cost')} "
                f"({str(o.get('notes'))[:40]})" for o in orphan[:4])
            bad("C16", f"{len(orphan)} baris riwayat harga YATIM tertinggal "
                       f"(materialnya sudah dihapus alat ukur)", sample)

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian belanja mingguan · riwayat harga · "
          f"ambang massal terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
