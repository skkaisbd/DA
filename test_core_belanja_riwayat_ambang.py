#!/usr/bin/env python3
"""test_core_belanja_riwayat_ambang.py — POC INTI SESI #33 (2026-08-23).

TIGA PEKERJAAN YANG DIMINTA PEMILIK (dibuktikan lewat API NYATA, data NYATA)
---------------------------------------------------------------------------
(1) **Isi Ambang Massal.** Layar "Ambang Stok" SUDAH ADA (tab di `wh-master`,
    sesi #29/W3) tetapi terukur di container ini: `GET /api/rahaza/stock-thresholds`
    → `{total_materials: 335, with_threshold: 0, missing_threshold: 335}` dan
    HANYA **5 dari 335** material punya usulan (`no_usage_data=false`), karena
    usulan HANYA lahir dari pemakaian 30 hari di `rahaza_stock_ledger`. Artinya
    tombol "Pakai semua usulan" secara STRUKTURAL hanya bisa mengisi 5 material;
    **330 material (98,5%) tidak punya jalan massal apa pun.** Selain itu ambang
    yang tersimpan tidak menyebut DASARNYA, siapa yang mengisi, dan kapan.

(2) **Riwayat Harga Barang.** `rahaza_material_cost_history` sudah terisi tiap
    pembelian (SSOT `core/accessory_valuation`), tetapi satu-satunya PEMBACA
    adalah `GET /api/acc/valuation/cost-history` milik layar **AKSESORIS** — dan
    query-nya TANPA filter jenis, sehingga layar "Valuasi Aksesoris" saat ini
    menampilkan riwayat material **KAIN** (terukur: 2 dari 7 material di daftar
    bertipe `fabric`). Tidak ada layar riwayat harga untuk 335 material, padahal
    HPP potongan (sesi #32) dan HPP produk (sesi #31) LAHIR dari angka ini.

(3) **Daftar Belanja Mingguan.** Belum ada sama sekali (grep: tidak ada
    endpoint/koleksi/layar). `smart-reorder` hanya mengusulkan TITIK PESAN ULANG,
    bukan "beli berapa minggu ini", dan tidak ada jembatan dari alert stok ke
    Permintaan Pengadaan ⇒ hasil alert harus diketik ulang manual sebagai PR.
    Keputusan pemilik sesi ini: basis kebutuhan **HANYA min_stock/reorder point**
    (bukan BOM/kebutuhan produksi).

ANGKA UJI — DIHITUNG TANGAN LEBIH DAHULU (bukan "apa pun yang keluar")
---------------------------------------------------------------------
  KAIN-A  terima 200 m @25.000                      ⇒ unit_cost 25.000/m
          terima 100 m @37.000 (stok saat itu 200)  ⇒ (200×25.000 + 100×37.000)/300
                                                    = 8.700.000/300 = **29.000/m**
          riwayat: [0 → 25.000] lalu [25.000 → 29.000] ⇒ perubahan **+16,00%**
          rata-rata 1 kali beli = (200+100)/2 = **150 m**
  ACC-A   terima 240 pcs @1.500 ; 120 pcs @1.800 (stok 240)
                                                    ⇒ (360.000+216.000)/360 = **1.600/pcs**
          satuan beli **lusin** (1 lusin = 12 pcs) ; rata-rata 1 kali beli = 180 pcs
  KAIN-B  terima 60 m @0 (tanpa harga)              ⇒ unit_cost 0  ⇒ **unvalued**
  ACC-D   terima 100 pcs @500                        (stok cukup — tak boleh masuk daftar)
  ACC-E   terima 100 pcs @1.000 + daftar harga supplier 1.200/pcs, MOQ 500 pcs
  ACC-C   TIDAK pernah dibeli                        ⇒ riwayat harga KOSONG + alasannya

  AMBANG MASSAL
    mode `fixed`         min 500 / pesan-ulang 600 ke [KAIN-A, ACC-A]
       ⇒ alert: KAIN-A stok 300 < 500 ⇒ kurang (600−300) = **300**
                ACC-A  stok 360 < 500 ⇒ kurang (600−360) = **240**
    mode `percent_onhand` 20%  ke KAIN-A (stok 300) ⇒ min **60**, pesan-ulang **72** (×1,2)
    mode `purchase_lot`  ×0,5  ke ACC-A (lot 180)   ⇒ min **90**, pesan-ulang **108**
    mode `usage_30d`     harus SAMA dengan usulan `core/stock_thresholds.suggest`
    kosongkan massal     ⇒ ambang kembali 0 dan alertnya diam lagi

  DAFTAR BELANJA MINGGUAN (ambang dipasang khusus untuk tahap ini)
    KAIN-A min 400, stok 300 ⇒ kurang **100 m**  · beli 100 m   × 29.000 = **Rp2.900.000**
    ACC-A  min 500, stok 360 ⇒ kurang **140 pcs** · 140/12 = 11,67 ⇒ dibulatkan KE ATAS
                              **12 lusin** (=144 pcs) × Rp19.200/lusin = **Rp230.400**
    ACC-E  min 300, stok 100 ⇒ kurang **200 pcs** · MOQ supplier 500 ⇒ beli **500 pcs**
                              × Rp1.200 (harga supplier) = **Rp600.000**
    KAIN-B min 100, stok  60 ⇒ kurang 40 m tetapi **belum berharga** ⇒ tidak dihitung
    ACC-D  min  50, stok 100 ⇒ **tidak masuk daftar** (stok cukup)
    ACC-C  tanpa ambang       ⇒ **tidak masuk daftar** tetapi DIHITUNG & DIKATAKAN
    total perkiraan baris POC = 2.900.000 + 230.400 + 600.000 = **Rp3.730.400**
    PR dari [KAIN-A, ACC-A]  = 2.900.000 + 230.400 = **Rp3.130.400**

YANG DIBUKTIKAN (18 uji)
------------------------
  T1  harga barang lahir dari pembelian & riwayatnya tercatat (old → new)
  T2  riwayat harga LINTAS material bisa dibaca + ringkasan (%, terendah, tertinggi)
  T3  barang yang belum pernah dibeli ⇒ riwayat kosong + ALASANNYA (bukan error)
  T4  layar Valuasi Aksesoris tidak lagi mencampur riwayat material KAIN
  T5  isi ambang massal mode `fixed` + pratinjau + DASAR/siapa/kapan tercatat
  T6  mode `percent_onhand` aritmetikanya persis
  T7  mode `purchase_lot` — jalan massal untuk barang yang belum pernah dipakai
  T8  mode `usage_30d` SAMA dengan usulan SSOT lama (tak ada dua angka berbeda)
  T9  sesudah ambang terisi, alert stok BERBUNYI dengan kekurangan yang benar
  T10 kosongkan ambang massal ⇒ kembali seperti semula, alert diam
  T11 daftar belanja mingguan: kekurangan, qty beli (SATUAN BELI), harga, total
  T12 barang tanpa ambang tidak diusulkan TETAPI dihitung & dikatakan
  T13 barang berambang yang stoknya cukup tidak diusulkan
  T14 barang belum berharga muncul `unvalued` & tidak diam-diam menambah Rp0
  T15 "Buat PR Pengadaan" dari baris terpilih ⇒ PR draft, qty & harga dasar benar
  T16 ANTI DOBEL BELANJA: sesudah PR, barangnya bertanda & tidak diusulkan lagi
  T17 idempoten: daftar dibaca dua kali, angkanya sama
  T18 harga & MOQ supplier NYATA dipakai (qty dinaikkan ke MOQ, sumber disebut)

SELF-CLEANING: semua artefak dihapus & TOTAL STOK dibuktikan kembali ke angka
sebelum uji. Pakai `--keep` untuk menyisakan data agar bisa dilihat di layar.

Pakai:  python3 test_core_belanja_riwayat_ambang.py [--keep]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

API = os.environ.get("API_BASE", "http://localhost:8001")
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("%H%M%S")
MARK = f"POC33 belanja {STAMP}"
KEEP = "--keep" in sys.argv


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f"\n         {C}{detail}{X}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f"\n         {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


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
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:260]


def near(a, b, tol=0.51):
    try:
        return abs(float(a or 0) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def money(v):
    try:
        return f"Rp{float(v or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(v)


def total_stock(db):
    row = list(db.rahaza_material_stock.aggregate(
        [{"$group": {"_id": None, "t": {"$sum": "$qty"}}}]))
    return round(float(row[0]["t"]) if row else 0.0, 4)


def receive(token, mat, qty, price, loc, rolls=None):
    """Penerimaan barang NYATA — jalur GR yang juga dipakai layar Gudang."""
    item = {
        "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
        "expected_qty": qty, "received_qty": qty, "rejected_qty": 0,
        "unit": mat.get("unit") or "pcs", "unit_price": price,
        "inspection_status": "passed", "lot_number": f"LOT-{STAMP}",
    }
    if rolls:
        item["rolls"] = rolls
    st, gr = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": f"Pemasok POC33 {STAMP}",
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": MARK, "items": [item]})
    if st not in (200, 201) or not (gr or {}).get("id"):
        return None, f"GR gagal HTTP {st} · {det(gr)}"
    st, upd = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        return None, f"terima GR gagal HTTP {st} · {det(upd)}"
    return gr, ""


def mk_material(token, ctx, key, payload):
    st, m = call("POST", "/api/rahaza/materials", token, payload)
    if st != 200 or not (m or {}).get("id"):
        return None, f"gagal membuat {payload.get('code')} HTTP {st} · {det(m)}"
    ctx[key] = m["id"]
    return m, ""


def set_threshold(token, mid, min_qty, rp=0):
    """Pasang ambang lewat endpoint massal `fixed` (satu jalan, satu SSOT)."""
    return call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
        "mode": "fixed", "dry_run": False,
        "params": {"min_stock_qty": min_qty, "reorder_point": rp},
        "scope": {"material_ids": [mid]}})


def row_of(rows, mid, key="material_id"):
    return next((r for r in rows if r.get(key) == mid), None)


def cleanup(db, ctx):
    mat_ids = [v for k, v in ctx.items() if k.startswith("mat_")]
    gr_ids = [v for k, v in ctx.items() if k.startswith("gr_")]
    pr_ids = [v for k, v in ctx.items() if k.startswith("pr_")]
    counts = {}
    for name, coll, q in (
        ("PR", "dewi_procurement_requests", {"id": {"$in": pr_ids}}),
        ("harga_sup", "rahaza_supplier_price_lists", {"material_id": {"$in": mat_ids}}),
        ("kartu", "rahaza_material_movements", {"material_id": {"$in": mat_ids}}),
        ("wh_mv", "warehouse_movements", {"material_id": {"$in": mat_ids}}),
        ("roll_mv", "wh_fabric_roll_movements", {"material_id": {"$in": mat_ids}}),
        ("roll", "wh_fabric_rolls", {"material_id": {"$in": mat_ids}}),
        ("GR", "warehouse_receiving", {"id": {"$in": gr_ids}}),
        ("stok", "rahaza_material_stock", {"material_id": {"$in": mat_ids}}),
        ("ledger", "rahaza_stock_ledger", {"material_id": {"$in": mat_ids}}),
        ("harga", "rahaza_material_cost_history", {"material_id": {"$in": mat_ids}}),
        ("notif", "rahaza_notifications", {"body": {"$regex": STAMP}}),
        ("master", "rahaza_materials", {"id": {"$in": mat_ids}}),
    ):
        try:
            counts[name] = db[coll].delete_many(q).deleted_count
        except Exception:  # noqa: BLE001
            counts[name] = -1
    print(f"  {Y}bersih-bersih: " + " · ".join(f"{k}={v}" for k, v in counts.items()) + X)


# ══════════════════════════════════════════════════════════════════════════════
def main():  # noqa: C901 — satu alur uji berurutan, sengaja dibaca atas→bawah
    print(f"{C}{B}POC #33 — BELANJA MINGGUAN · RIWAYAT HARGA · ISI AMBANG MASSAL{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    ctx: dict = {}
    stock0 = total_stock(db)
    th0 = db.rahaza_materials.count_documents(
        {"active": True, "$or": [{"min_stock_qty": {"$gt": 0}}, {"reorder_point": {"$gt": 0}}]})
    print(f"  {Y}sebelum uji: total stok {stock0:,.2f} · material berambang {th0}{X}")

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}) — {det(d)}{X}")
        return 2
    admin_email = ((d or {}).get("user") or {}).get("email") or ""

    try:
        # ── SIAPKAN DATA NYATA ───────────────────────────────────────────────
        head("SIAPKAN — barang dibeli sungguhan (harga lahir dari pembelian)")
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), None)
        if not loc:
            bad("SETUP", "tidak ada lokasi gudang")
            return 1

        mats = {}
        specs = [
            ("mat_a", {"code": f"POC33-KAIN-A-{STAMP}", "name": f"Kain POC33 A {STAMP}",
                       "type": "fabric", "unit": "m", "color": "Navy", "notes": MARK}),
            ("mat_b", {"code": f"POC33-KAIN-B-{STAMP}", "name": f"Kain POC33 B {STAMP}",
                       "type": "fabric", "unit": "m", "color": "Hitam", "notes": MARK}),
            ("mat_acc_a", {"code": f"POC33-ACC-A-{STAMP}", "name": f"Aksesoris POC33 A {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK,
                           "uoms": [{"code": "pcs", "name": "Pcs", "factor": 1, "is_base": True},
                                    {"code": "lusin", "name": "Lusin", "factor": 12}],
                           "purchase_uom": "lusin"}),
            ("mat_acc_c", {"code": f"POC33-ACC-C-{STAMP}", "name": f"Aksesoris POC33 C {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK}),
            ("mat_acc_d", {"code": f"POC33-ACC-D-{STAMP}", "name": f"Aksesoris POC33 D {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK}),
            ("mat_acc_e", {"code": f"POC33-ACC-E-{STAMP}", "name": f"Aksesoris POC33 E {STAMP}",
                           "type": "accessory", "unit": "pcs", "notes": MARK}),
        ]
        for key, payload in specs:
            m, err = mk_material(token, ctx, key, payload)
            if not m:
                bad("SETUP", err)
                return 1
            mats[key] = m
        print(f"  {Y}6 master barang uji dibuat{X}")

        # penerimaan pertama
        for key, qty, price, rolls in (
            ("mat_a", 200, 25000, [{"qty": 200, "color_lot": f"LOT-{STAMP}", "notes": ""}]),
            ("mat_acc_a", 240, 1500, None),
            ("mat_b", 60, 0, [{"qty": 60, "color_lot": f"LOT-{STAMP}", "notes": ""}]),
            ("mat_acc_d", 100, 500, None),
            ("mat_acc_e", 100, 1000, None),
        ):
            gr, err = receive(token, mats[key], qty, price, loc, rolls)
            if not gr:
                bad("SETUP", f"penerimaan {mats[key]['code']} gagal", err)
                return 1
            ctx[f"gr_{key}_1"] = gr["id"]
        # penerimaan kedua (harga berubah ⇒ rata-rata bergerak)
        for key, qty, price, rolls in (
            ("mat_a", 100, 37000, [{"qty": 100, "color_lot": f"LOT2-{STAMP}", "notes": ""}]),
            ("mat_acc_a", 120, 1800, None),
        ):
            gr, err = receive(token, mats[key], qty, price, loc, rolls)
            if not gr:
                bad("SETUP", f"penerimaan ke-2 {mats[key]['code']} gagal", err)
                return 1
            ctx[f"gr_{key}_2"] = gr["id"]

        # daftar harga supplier NYATA untuk ACC-E (harga 1.200/pcs, MOQ 500)
        st, sups = call("GET", "/api/procurement/suppliers", token)
        srows = (sups or {}).get("items") if isinstance(sups, dict) else sups
        sup = next((s for s in (srows or []) if s.get("id")), None)
        if not sup:
            bad("SETUP", "tidak ada master supplier untuk uji harga+MOQ")
            return 1
        st, pl = call("POST", f"/api/procurement/suppliers/{sup['id']}/price-list", token, {
            "material_id": mats["mat_acc_e"]["id"], "uom": "pcs", "price": 1200,
            "moq": 500, "lead_time_days": 5, "notes": MARK})
        if st not in (200, 201):
            bad("SETUP", f"gagal menambah daftar harga supplier HTTP {st}", det(pl))
            return 1
        ctx["sup_id"] = sup["id"]

        m_a = db.rahaza_materials.find_one({"id": ctx["mat_a"]}, {"_id": 0})
        m_acc = db.rahaza_materials.find_one({"id": ctx["mat_acc_a"]}, {"_id": 0})
        print(f"  {Y}KAIN-A unit_cost = {money(m_a.get('unit_cost'))} (harap 29.000) · "
              f"ACC-A = {money(m_acc.get('unit_cost'))} (harap 1.600){X}")
        if not near(m_a.get("unit_cost"), 29000, 1) or not near(m_acc.get("unit_cost"), 1600, 1):
            bad("SETUP", "rata-rata bergerak harga pembelian tidak seperti hitungan tangan",
                f"KAIN-A={m_a.get('unit_cost')} ACC-A={m_acc.get('unit_cost')}")
            return 1

        # ══ BAGIAN 1 — RIWAYAT HARGA BARANG ═══════════════════════════════════
        head("BAGIAN 1 — RIWAYAT HARGA BARANG (semua barang, bukan hanya aksesoris)")

        st, h = call("GET", f"/api/rahaza/material-costs/history?material_id={ctx['mat_a']}", token)
        items = (h or {}).get("items") or []
        if st == 200 and len(items) == 2:
            newest, oldest = items[0], items[1]
            if (near(oldest.get("old_unit_cost"), 0) and near(oldest.get("new_unit_cost"), 25000)
                    and near(newest.get("old_unit_cost"), 25000)
                    and near(newest.get("new_unit_cost"), 29000)):
                ok("T1", "harga lahir dari pembelian & riwayatnya tercatat (terbaru dulu)",
                   f"0 → 25.000 lalu 25.000 → 29.000 · sumber '{newest.get('source')}'")
            else:
                bad("T1", "angka riwayat tidak seperti hitungan tangan", json.dumps(items)[:260])
        else:
            bad("T1", f"riwayat harga per barang tidak terbaca (HTTP {st}, {len(items)} baris)",
                det(h))

        s = (h or {}).get("summary") or {}
        if (near(s.get("current_unit_cost"), 29000) and near(s.get("first_unit_cost"), 25000)
                and near(s.get("min_unit_cost"), 25000) and near(s.get("max_unit_cost"), 29000)
                and near(s.get("change_pct"), 16, 0.05) and int(s.get("changes") or 0) == 2
                and near((items[0] if items else {}).get("change_pct"), 16, 0.05)):
            ok("T2", "ringkasan riwayat benar (harga kini, terendah, tertinggi, % perubahan)",
               f"kini {money(s.get('current_unit_cost'))} · pertama {money(s.get('first_unit_cost'))} · "
               f"perubahan {s.get('change_pct')}% · {s.get('changes')} kali berubah")
        else:
            bad("T2", "ringkasan riwayat harga salah / tidak ada", json.dumps(s)[:260])

        st, h0 = call("GET", f"/api/rahaza/material-costs/history?material_id={ctx['mat_acc_c']}",
                      token)
        rows0 = (h0 or {}).get("items")
        reason = str((h0 or {}).get("reason") or "")
        if st == 200 and rows0 == [] and len(reason) > 15:
            ok("T3", "barang yang belum pernah dibeli: riwayat kosong + ALASANNYA disebut",
               reason[:150])
        else:
            bad("T3", "keadaan kosong tidak dijelaskan (atau error)",
                f"HTTP {st} · rows={rows0} · reason='{reason}'")

        st, accs = call("GET", "/api/acc/valuation/cost-history?limit=200", token)
        arows = accs if isinstance(accs, list) else (accs or {}).get("items") or []
        aids = {r.get("material_id") for r in arows}
        fabric_leak = {ctx["mat_a"], ctx["mat_b"]} & aids
        if st == 200 and ctx["mat_acc_a"] in aids and not fabric_leak:
            ok("T4", "layar Valuasi Aksesoris hanya berisi aksesoris (kain tidak lagi bocor)",
               f"{len(arows)} baris · ACC-A ada · KAIN-A/KAIN-B tidak ada")
        else:
            bad("T4", "riwayat aksesoris masih mencampur material kain",
                f"HTTP {st} · bocor={len(fabric_leak)} · acc_a_ada={ctx['mat_acc_a'] in aids}")

        # ══ BAGIAN 2 — ISI AMBANG MASSAL ══════════════════════════════════════
        head("BAGIAN 2 — ISI AMBANG MASSAL (jalan untuk 330 barang tanpa pemakaian)")

        st, prev = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "fixed", "dry_run": True,
            "params": {"min_stock_qty": 500, "reorder_point": 600},
            "scope": {"material_ids": [ctx["mat_a"], ctx["mat_acc_a"]]}})
        st2, appl = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "fixed", "dry_run": False,
            "params": {"min_stock_qty": 500, "reorder_point": 600},
            "scope": {"material_ids": [ctx["mat_a"], ctx["mat_acc_a"]]}})
        ma = db.rahaza_materials.find_one({"id": ctx["mat_a"]}, {"_id": 0}) or {}
        if (st == 200 and int((prev or {}).get("eligible") or 0) == 2
                and int((prev or {}).get("applied") or 0) == 0
                and st2 == 200 and int((appl or {}).get("applied") or 0) == 2
                and near(ma.get("min_stock_qty"), 500) and near(ma.get("reorder_point"), 600)
                and ma.get("threshold_basis") == "fixed"
                and (ma.get("threshold_set_by") or "") != ""
                and (ma.get("threshold_set_at") or "") != ""):
            ok("T5", "isi massal `fixed`: pratinjau dulu, lalu tersimpan + DASAR/siapa/kapan",
               f"pratinjau {prev.get('eligible')} barang (0 ditulis) → diterapkan "
               f"{appl.get('applied')} · dasar '{ma.get('threshold_basis')}' oleh "
               f"{ma.get('threshold_set_by')} pada {str(ma.get('threshold_set_at'))[:19]}")
        else:
            bad("T5", "isi massal `fixed` gagal / tidak mencatat dasarnya",
                f"HTTP {st}/{st2} · prev={json.dumps(prev)[:120]} · min={ma.get('min_stock_qty')} "
                f"rp={ma.get('reorder_point')} basis={ma.get('threshold_basis')} "
                f"by={ma.get('threshold_set_by')}")

        st, alerts = call("GET", "/api/rahaza/materials/reorder-alerts", token)
        arows = alerts if isinstance(alerts, list) else (alerts or {}).get("items") or []
        a1 = row_of(arows, ctx["mat_a"], "id") or row_of(arows, ctx["mat_a"])
        a2 = row_of(arows, ctx["mat_acc_a"], "id") or row_of(arows, ctx["mat_acc_a"])
        if a1 and a2 and near(a1.get("shortage"), 300) and near(a2.get("shortage"), 240):
            ok("T9", "alert stok BERBUNYI sesudah ambang terisi, kekurangannya benar",
               f"KAIN-A kurang {a1.get('shortage')} m · ACC-A kurang {a2.get('shortage')} pcs")
        else:
            bad("T9", "alert tidak berbunyi / kekurangan salah",
                f"KAIN-A={(a1 or {}).get('shortage')} (harap 300) · "
                f"ACC-A={(a2 or {}).get('shortage')} (harap 240)")

        st, pc = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "percent_onhand", "dry_run": False, "params": {"percent": 20},
            "scope": {"material_ids": [ctx["mat_a"]]}})
        ma = db.rahaza_materials.find_one({"id": ctx["mat_a"]}, {"_id": 0}) or {}
        if st == 200 and near(ma.get("min_stock_qty"), 60) and near(ma.get("reorder_point"), 72) \
                and ma.get("threshold_basis") == "percent_onhand":
            ok("T6", "mode `percent_onhand` aritmetikanya persis (20% dari stok 300)",
               f"min {ma.get('min_stock_qty')} (harap 60) · pesan ulang "
               f"{ma.get('reorder_point')} (harap 72 = 60 × 1,2)")
        else:
            bad("T6", "mode percent_onhand salah hitung",
                f"HTTP {st} · min={ma.get('min_stock_qty')} rp={ma.get('reorder_point')} "
                f"basis={ma.get('threshold_basis')} · {det(pc)}")

        st, lot = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "purchase_lot", "dry_run": False, "params": {"lot_multiplier": 0.5},
            "scope": {"material_ids": [ctx["mat_acc_a"]]}})
        mc = db.rahaza_materials.find_one({"id": ctx["mat_acc_a"]}, {"_id": 0}) or {}
        if st == 200 and near(mc.get("min_stock_qty"), 90) and near(mc.get("reorder_point"), 108) \
                and mc.get("threshold_basis") == "purchase_lot":
            ok("T7", "mode `purchase_lot`: barang tanpa pemakaian akhirnya bisa diisi massal",
               f"rata-rata 1 kali beli 180 pcs × 0,5 ⇒ min {mc.get('min_stock_qty')} · "
               f"pesan ulang {mc.get('reorder_point')} · dasar '{mc.get('threshold_basis')}'")
        else:
            bad("T7", "mode purchase_lot salah / tidak jalan",
                f"HTTP {st} · min={mc.get('min_stock_qty')} rp={mc.get('reorder_point')} "
                f"basis={mc.get('threshold_basis')} · {det(lot)}")

        st, thl = call("GET", "/api/rahaza/stock-thresholds?limit=1000", token)
        trows = (thl or {}).get("items") or []
        usable = [r for r in trows if not (r.get("suggestion") or {}).get("no_usage_data")]
        ids_usable = [r["material_id"] for r in usable]
        st, dry = call("POST", "/api/rahaza/stock-thresholds/bulk-fill", token, {
            "mode": "usage_30d", "dry_run": True, "params": {},
            "scope": {"material_ids": ids_usable + [ctx["mat_acc_c"]]}})
        prows = (dry or {}).get("preview") or []
        same = all(near(row_of(prows, r["material_id"], "material_id").get("min_stock_qty"),
                        r["suggestion"]["suggested_min_stock"], 0.02)
                   for r in usable if row_of(prows, r["material_id"], "material_id"))
        skipped_c = any(s.get("material_id") == ctx["mat_acc_c"]
                        for s in ((dry or {}).get("skipped") or []))
        if st == 200 and usable and len(prows) == len(usable) and same and skipped_c:
            ok("T8", "mode `usage_30d` sama dengan usulan SSOT lama; tanpa pemakaian DILEWATI",
               f"{len(usable)} barang berpemakaian nyata cocok 100% · barang tanpa pemakaian "
               f"masuk daftar dilewati beserta alasannya")
        else:
            bad("T8", "usulan pemakaian tidak konsisten dengan SSOT / tidak melewatkan yang kosong",
                f"HTTP {st} · usable={len(usable)} preview={len(prows)} sama={same} "
                f"dilewati_acc_c={skipped_c}")

        st, clr = call("POST", "/api/rahaza/stock-thresholds/bulk-clear", token,
                       {"material_ids": [ctx["mat_a"], ctx["mat_acc_a"]]})
        ma = db.rahaza_materials.find_one({"id": ctx["mat_a"]}, {"_id": 0}) or {}
        st2, alerts2 = call("GET", "/api/rahaza/materials/reorder-alerts", token)
        arows2 = alerts2 if isinstance(alerts2, list) else (alerts2 or {}).get("items") or []
        gone = not (row_of(arows2, ctx["mat_a"], "id") or row_of(arows2, ctx["mat_a"]))
        if st == 200 and int((clr or {}).get("cleared") or 0) == 2 \
                and not float(ma.get("min_stock_qty") or 0) \
                and not float(ma.get("reorder_point") or 0) and gone:
            ok("T10", "kosongkan ambang massal ⇒ kembali seperti semula & alertnya diam",
               f"{clr.get('cleared')} barang dikosongkan · KAIN-A hilang dari daftar alert")
        else:
            bad("T10", "kosongkan massal tidak tuntas",
                f"HTTP {st} · cleared={(clr or {}).get('cleared')} min={ma.get('min_stock_qty')} "
                f"rp={ma.get('reorder_point')} alert_hilang={gone}")

        # ══ BAGIAN 3 — DAFTAR BELANJA MINGGUAN ════════════════════════════════
        head("BAGIAN 3 — DAFTAR BELANJA MINGGUAN (basis ambang, pilihan pemilik)")
        for mid, mn in ((ctx["mat_a"], 400), (ctx["mat_acc_a"], 500), (ctx["mat_b"], 100),
                        (ctx["mat_acc_d"], 50), (ctx["mat_acc_e"], 300)):
            stx, rr = set_threshold(token, mid, mn, 0)
            if stx != 200:
                bad("SETUP", f"gagal memasang ambang {mn} untuk {mid[:8]}", det(rr))
                return 1

        st, wk = call("GET", "/api/rahaza/shopping-list/weekly", token)
        rows = (wk or {}).get("rows") or []
        summ = (wk or {}).get("summary") or {}
        r_a, r_acc = row_of(rows, ctx["mat_a"]), row_of(rows, ctx["mat_acc_a"])
        if (st == 200 and r_a and r_acc
                and near(r_a.get("shortage"), 100) and near(r_a.get("qty_buy"), 100)
                and (r_a.get("purchase_uom") or "m") == "m"
                and near(r_a.get("est_total"), 2_900_000, 1)
                and near(r_acc.get("shortage"), 140) and near(r_acc.get("qty_buy"), 12)
                and r_acc.get("purchase_uom") == "lusin"
                and near(r_acc.get("qty_buy_base"), 144)
                and near(r_acc.get("est_total"), 230_400, 1)):
            ok("T11", "daftar belanja: kekurangan, qty beli dalam SATUAN BELI, harga & total benar",
               f"KAIN-A kurang 100 m ⇒ beli 100 m = {money(r_a.get('est_total'))} · "
               f"ACC-A kurang 140 pcs ⇒ beli 12 lusin (144 pcs) = {money(r_acc.get('est_total'))}")
        else:
            bad("T11", "angka daftar belanja tidak seperti hitungan tangan",
                f"HTTP {st} · KAIN-A={json.dumps(r_a)[:180]} · ACC-A={json.dumps(r_acc)[:180]}")

        if row_of(rows, ctx["mat_acc_c"]) is None and int(summ.get("without_threshold") or 0) >= 1 \
                and len(str(summ.get("without_threshold_note") or "")) > 15:
            ok("T12", "barang tanpa ambang tidak diusulkan TETAPI dihitung & dikatakan",
               f"{summ.get('without_threshold')} barang belum berambang — "
               f"{str(summ.get('without_threshold_note'))[:110]}")
        else:
            bad("T12", "layar tidak jujur soal barang yang belum berambang",
                f"acc_c_ada={row_of(rows, ctx['mat_acc_c']) is not None} · "
                f"tanpa_ambang={summ.get('without_threshold')} · "
                f"catatan='{summ.get('without_threshold_note')}'")

        if row_of(rows, ctx["mat_acc_d"]) is None:
            ok("T13", "barang berambang yang stoknya cukup tidak diusulkan",
               "ACC-D stok 100 ≥ ambang 50 ⇒ tidak masuk daftar belanja")
        else:
            bad("T13", "barang berstok cukup ikut diusulkan (belanja mubazir)")

        r_b = row_of(rows, ctx["mat_b"])
        est_all = float(summ.get("est_total_value") or 0)
        poc_est = sum(float(row_of(rows, m).get("est_total") or 0)
                      for m in (ctx["mat_a"], ctx["mat_acc_a"], ctx["mat_acc_e"])
                      if row_of(rows, m))
        if (r_b and r_b.get("value_status") == "unvalued"
                and near(r_b.get("est_total"), 0) and near(r_b.get("shortage"), 40)
                and int(summ.get("unvalued_count") or 0) >= 1
                and near(poc_est, 3_730_400, 1)):
            ok("T14", "barang belum berharga: ditandai `unvalued`, tidak diam-diam menambah Rp0",
               f"KAIN-B kurang 40 m tanpa harga · total perkiraan baris POC "
               f"{money(poc_est)} (harap Rp3.730.400) · seluruh daftar {money(est_all)}")
        else:
            bad("T14", "barang tanpa harga tidak ditangani jujur",
                f"KAIN-B={json.dumps(r_b)[:200]} · unvalued={summ.get('unvalued_count')} · "
                f"total_poc={poc_est}")

        r_e = row_of(rows, ctx["mat_acc_e"])
        if (r_e and near(r_e.get("qty_buy_base"), 500) and near(r_e.get("est_total"), 600_000, 1)
                and r_e.get("price_source") == "supplier_price_list"
                and (r_e.get("supplier") or {}).get("name")
                and "moq" in str(r_e.get("qty_note") or "").lower()):
            ok("T18", "harga & MOQ supplier NYATA dipakai, dan alasannya disebut",
               f"kurang 200 pcs → beli {r_e.get('qty_buy_base')} pcs (MOQ) × Rp1.200 = "
               f"{money(r_e.get('est_total'))} · dari {(r_e.get('supplier') or {}).get('name')} · "
               f"'{r_e.get('qty_note')}'")
        else:
            bad("T18", "harga/MOQ supplier tidak dipakai atau tidak dijelaskan",
                json.dumps(r_e)[:260])

        st, pr = call("POST", "/api/rahaza/shopping-list/create-pr", token, {
            "material_ids": [ctx["mat_a"], ctx["mat_acc_a"]],
            "notes": MARK})
        prdoc = (pr or {}).get("request") or pr or {}
        if prdoc.get("id"):
            ctx["pr_1"] = prdoc["id"]
        pitems = prdoc.get("items") or []
        p_a = row_of(pitems, ctx["mat_a"])
        p_acc = row_of(pitems, ctx["mat_acc_a"])
        if (st in (200, 201) and prdoc.get("request_number") and len(pitems) == 2
                and p_a and near(p_a.get("qty"), 100) and near(p_a.get("qty_base"), 100)
                and near(p_a.get("estimated_price"), 29000, 1)
                and p_acc and near(p_acc.get("qty"), 12) and p_acc.get("uom") == "lusin"
                and near(p_acc.get("qty_base"), 144)
                and near(p_acc.get("estimated_price"), 19200, 1)
                and near(p_acc.get("estimated_price_base"), 1600, 1)
                and near(prdoc.get("total_estimated"), 3_130_400, 1)):
            ok("T15", "Buat PR Pengadaan: PR draft lahir, qty & harga per satuan dasar benar",
               f"{prdoc.get('request_number')} · 2 baris · total "
               f"{money(prdoc.get('total_estimated'))} (harap Rp3.130.400) · "
               f"status {prdoc.get('status')}")
        else:
            bad("T15", "PR dari daftar belanja gagal / angkanya salah",
                f"HTTP {st} · {json.dumps(prdoc)[:300]}")

        st, wk2 = call("GET", "/api/rahaza/shopping-list/weekly", token)
        rows2 = (wk2 or {}).get("rows") or []
        summ2 = (wk2 or {}).get("summary") or {}
        q_a, q_acc = row_of(rows2, ctx["mat_a"]), row_of(rows2, ctx["mat_acc_a"])
        if (q_a and q_acc and q_a.get("already_requested") and q_acc.get("already_requested")
                and (q_a.get("pr") or {}).get("number") == prdoc.get("request_number")
                and int(summ2.get("already_requested_count") or 0) >= 2
                and int(summ2.get("need_buy") or 0) == max(0, int(summ.get("need_buy") or 0) - 2)):
            ok("T16", "ANTI DOBEL BELANJA: barang yang sudah ber-PR ditandai & tidak dihitung lagi",
               f"KAIN-A & ACC-A ⇒ '{(q_a.get('pr') or {}).get('number')}' · perlu dibeli turun "
               f"{summ.get('need_buy')} → {summ2.get('need_buy')}")
        else:
            bad("T16", "daftar masih mengusulkan barang yang sudah dibuatkan PR",
                f"a={json.dumps(q_a)[:170]} · sudah_ber_pr={summ2.get('already_requested_count')} "
                f"· need_buy {summ.get('need_buy')} → {summ2.get('need_buy')}")

        st, wk3 = call("GET", "/api/rahaza/shopping-list/weekly", token)
        s3 = (wk3 or {}).get("summary") or {}
        if (st == 200 and len((wk3 or {}).get("rows") or []) == len(rows2)
                and near(s3.get("est_total_value"), summ2.get("est_total_value"), 0.01)
                and s3.get("week") == summ2.get("week")):
            ok("T17", "idempoten: daftar dibaca dua kali, angkanya sama",
               f"minggu {s3.get('week')} · {len(rows2)} baris · "
               f"{money(s3.get('est_total_value'))}")
        else:
            bad("T17", "daftar berubah tanpa ada transaksi baru",
                f"baris {len(rows2)} vs {len((wk3 or {}).get('rows') or [])} · "
                f"{summ2.get('est_total_value')} vs {s3.get('est_total_value')}")

    finally:
        head("BERSIH-BERSIH")
        if KEEP:
            print(f"  {Y}--keep: data uji DIBIARKAN (kode ber-awalan POC33-…-{STAMP}){X}")
        else:
            call("POST", "/api/rahaza/stock-thresholds/bulk-clear", token,
                 {"material_ids": [v for k, v in ctx.items() if k.startswith("mat_")]})
            cleanup(db, ctx)
            s1 = total_stock(db)
            th1 = db.rahaza_materials.count_documents(
                {"active": True, "$or": [{"min_stock_qty": {"$gt": 0}},
                                         {"reorder_point": {"$gt": 0}}]})
            if near(s1, stock0, 0.01) and th1 == th0:
                ok("BERSIH", "alat ukur tidak mengotori data",
                   f"total stok {s1:,.2f} == {stock0:,.2f} · material berambang {th1} == {th0}")
            else:
                bad("BERSIH", "keadaan tidak kembali seperti sebelum uji",
                    f"stok {s1:,.2f} vs {stock0:,.2f} · berambang {th1} vs {th0}")

    print(f"\n{B}HASIL: {G}{len(PASS)} PASS{X} · {R}{len(FAIL)} FAIL{X}")
    if FAIL:
        print(f"{R}{B}  GAGAL: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}  SEMUA UJI INTI HIJAU — inti sesi #33 terbukti bekerja.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
