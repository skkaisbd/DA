#!/usr/bin/env python3
"""test_core_potongan_nilai_dan_yatim.py — POC INTI SESI #32 (2026-08-23).

DUA CACAT YANG DIKELUHKAN PEMILIK (dibuktikan lewat API NYATA, data NYATA)
--------------------------------------------------------------------------
(1) **HPP/harga potongan = 0.** Nilai kain yang KELUAR dari gudang tidak pernah
    berpindah menjadi nilai POTONGAN yang MASUK. Master potongan lahir dengan
    `unit_cost: 0` dan baru diisi saat order **di-complete** — itupun dengan cara
    MENIMPA (bukan rata-rata bergerak), memakai harga kain yang di-snapshot saat
    order DIBUAT. Akibatnya: selama order masih berjalan, nilai persediaan
    berkurang (kain keluar bernilai) tanpa ada yang menerimanya ⇒ nilai
    persediaan bocor; dan bila satu master potongan dipakai dua order dengan
    harga kain berbeda, angka yang terakhir MENGHAPUS yang pertama.

(2) **Potongan jadi YATIM.** Master potongan menyimpan `source_material_id` ke
    kain asalnya, tetapi tidak ada penjaga maupun pembersih. Bukti hidup di
    container ini: satu master `CUT-JEPIT-JEDAI-NAVY-L` menunjuk kain
    `VFH6B-KAIN-174456` yang sudah TIDAK ADA, order cuttingnya juga tidak ada,
    dan `rahaza_material_issues` tidak punya satu pun baris `source='cutting'`.
    Jejaknya: gate INV-F24 (`scripts/verify_fase_h6b_cutting_issue.py`)
    membersihkan order + kain + dokumen MI + stok + kartu stok, tetapi MASTER
    potongannya dihapus memakai regex kode `^(VFH6B-|CUT-GATE-F24)` — sementara
    kode potongan diturunkan dari NAMA MODEL master ("CUT-JEPIT-JEDAI-…") ⇒
    tidak pernah cocok. Setiap kali alat ukur dijalankan, satu master sampah
    bertambah di Master Item milik pemilik. Alur PRODUK juga bisa
    menghasilkannya: `start` melahirkan master potongan, lalu `cancel`
    (diizinkan selama belum ada progres) meninggalkannya tanpa induk.

ANGKA UJI — DIHITUNG TANGAN LEBIH DAHULU (bukan "apa pun yang keluar")
---------------------------------------------------------------------
  Kain A diterima 200 m @ Rp30.000                  ⇒ unit_cost 30.000/m
  Progres #1: 10 m ⇒ 20 pcs
      nilai kain keluar   = 10 × 30.000 = Rp300.000
      HPP potongan        = 300.000 / 20 = **Rp15.000/pcs**   (stok potongan 20)
  Kain A diterima lagi 100 m @ Rp42.000 (stok saat itu 190 m)
      rata-rata bergerak  = (190×30.000 + 100×42.000) / 290 = **Rp34.137,931/m**
  Progres #2: 10 m ⇒ 10 pcs
      nilai kain keluar   = 10 × 34.137,931 = Rp341.379,31
      HPP potongan (WAC)  = (20×15.000 + 10×34.137,931) / 30 = **Rp21.379,310/pcs**
      (kalau ditimpa seperti sekarang, angkanya akan 34.137,93 — SALAH)
  Complete ⇒ nilai order = 641.379,31 ; per pcs = 641.379,31/30 = **21.379,31**
  KEKEKALAN NILAI: Σ nilai kain keluar (641.379,31) == nilai stok potongan
      (30 × 21.379,310 = 641.379,30)  ⇒ tidak ada nilai yang hilang.

  Kain B diterima 60 m TANPA harga (unit_price 0)   ⇒ unit_cost 0
  Progres kain B ⇒ potongan TETAP 0 **dan sistem MENGATAKANNYA** (status
  `unvalued` + jalan keluarnya), bukan diam-diam 0.

YANG DIBUKTIKAN (12 uji)
------------------------
  T1  harga kain lahir dari penerimaan (rata-rata bergerak)
  T2  `start` melahirkan master potongan yang MENUNJUK induknya
      (`cutting_order_id` + `source_material_id`), nilainya masih 0 (belum potong)
  T3  progres #1 ⇒ HPP potongan **15.000** (nilai kain berpindah SAAT ITU)
  T4  penerimaan kedua ⇒ harga kain jadi 34.137,931 (rata-rata bergerak)
  T5  progres #2 ⇒ HPP potongan **21.379,310** (RATA-RATA, bukan ditimpa)
  T6  kekekalan nilai: Σ nilai kain keluar == nilai stok potongan
  T7  complete ⇒ nilai order & per-pcs benar; master TIDAK ditimpa
  T8  kain belum bernilai ⇒ potongan berstatus `unvalued` + peringatan jujur
  T9  `cancel` sesudah `start` TIDAK meninggalkan potongan yatim (penjaga)
  T10 potongan yatim (order hilang) TERDETEKSI + bisa DIBERSIHKAN (idempoten)
  T11 potongan yatim yang MASIH BERSTOK **tidak** dihapus — dilaporkan apa adanya
  T12 layar Master Potongan menerima nilai + asal + status (bukan hanya qty)

SELF-CLEANING: semua artefak dihapus & TOTAL STOK dibuktikan kembali ke angka
sebelum uji. Pakai `--keep` untuk menyisakan data agar bisa dilihat di layar.

Pakai:  python3 test_core_potongan_nilai_dan_yatim.py [--keep]
"""
from __future__ import annotations

import json
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
MARK = f"POC potongan {STAMP}"
KEEP = "--keep" in sys.argv


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


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
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:220]


def near(a, b, tol=1.0):
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


# ══════════════════════════════════════════════════════════════════════════════
def receive(token, mat, qty, price, loc, roll_lines):
    """Penerimaan barang NYATA (jalur GR yang juga dipakai layar Gudang).

    Sekalian menerbitkan gulungan — kain yang dilacak per gulungan WAJIB punya
    gulungan sebelum bisa dipotong (FASE H-6).
    """
    st, gr = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": f"Pemasok POC {STAMP}",
        "location_id": loc.get("id"), "location_name": loc.get("name"),
        "notes": MARK,
        "items": [{
            "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
            "expected_qty": qty, "received_qty": qty, "rejected_qty": 0,
            "unit": mat.get("unit") or "m", "unit_price": price,
            "inspection_status": "passed", "lot_number": f"LOT-{STAMP}",
            "rolls": roll_lines,
        }]})
    if st not in (200, 201) or not (gr or {}).get("id"):
        return None, f"GR gagal HTTP {st} · {det(gr)}"
    st, upd = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        return None, f"terima GR gagal HTTP {st} · {det(upd)}"
    return gr, ""


def rolls_of(db, material_id):
    rows = list(db.wh_fabric_rolls.find({"material_id": material_id}, {"_id": 0}))
    rows.sort(key=lambda d: str(d.get("roll_no", "")))
    return rows


def make_order(token, ctx, key, mat, size, loc, planned_in, planned_out):
    st, o = call("POST", "/api/cutting/orders", token, {
        "input_material_id": mat["id"], "planned_input_qty": planned_in,
        "planned_output_qty": planned_out, "model_id": ctx["model_id"],
        "size_id": size["id"], "location_id": loc.get("id"), "notes": MARK})
    if st not in (200, 201) or not (o or {}).get("id"):
        return None, f"order gagal HTTP {st} · {det(o)}"
    ctx[f"order_{key}"] = o["id"]
    st, started = call("POST", f"/api/cutting/orders/{o['id']}/start", token)
    if st != 200:
        return None, f"start gagal HTTP {st} · {det(started)}"
    return started, ""


def panel_of(token, order_id):
    st, o = call("GET", f"/api/cutting/orders/{order_id}")
    return None


def mat_get(token, mid):
    st, m = call("GET", f"/api/rahaza/materials/{mid}", token)
    return m if st == 200 else {}


def cleanup(db, ctx):
    """Hapus SEMUA artefak uji (termasuk master POTONGAN — pelajaran sesi #32)."""
    mat_ids = [v for k, v in ctx.items() if k.startswith("mat_")]
    order_ids = [v for k, v in ctx.items() if k.startswith("order_")]
    # master potongan: dicari lewat TAUTAN (bukan tebakan kode), plus jaring
    # cadangan lewat kain sumber & nomor order.
    panel_ids = [m["id"] for m in db.rahaza_materials.find(
        {"$or": [{"cutting_order_id": {"$in": order_ids}},
                 {"source_material_id": {"$in": mat_ids}},
                 {"code": {"$regex": f"^CUT-.*{STAMP}", "$options": "i"}}]},
        {"_id": 0, "id": 1})]
    all_mats = mat_ids + panel_ids
    gr_ids = [v for k, v in ctx.items() if k.startswith("gr_")]
    roll_ids = [r["id"] for r in db.wh_fabric_rolls.find(
        {"material_id": {"$in": mat_ids}}, {"_id": 0, "id": 1})]
    mi_ids = [m["id"] for m in db.rahaza_material_issues.find(
        {"cutting_order_id": {"$in": order_ids}}, {"_id": 0, "id": 1})]
    counts = {}
    for name, coll, q in (
        ("MI", "rahaza_material_issues", {"cutting_order_id": {"$in": order_ids}}),
        ("MI_lines", "rahaza_material_issue_items", {"issue_id": {"$in": mi_ids}}),
        ("kartu", "rahaza_material_movements", {"$or": [{"ref_id": {"$in": mi_ids}},
                                                        {"material_id": {"$in": all_mats}}]}),
        ("wh_mv", "warehouse_movements", {"material_id": {"$in": all_mats}}),
        ("progres", "cutting_progress", {"cutting_order_id": {"$in": order_ids}}),
        ("order", "cutting_orders", {"id": {"$in": order_ids}}),
        ("roll_mv", "wh_fabric_roll_movements", {"roll_id": {"$in": roll_ids}}),
        ("roll", "wh_fabric_rolls", {"id": {"$in": roll_ids}}),
        ("GR", "warehouse_receiving", {"id": {"$in": gr_ids}}),
        ("stok", "rahaza_material_stock", {"material_id": {"$in": all_mats}}),
        ("ledger", "rahaza_stock_ledger", {"material_id": {"$in": all_mats}}),
        ("harga", "rahaza_material_cost_history", {"material_id": {"$in": all_mats}}),
        ("master", "rahaza_materials", {"id": {"$in": all_mats}}),
        ("model", "rahaza_models", {"id": ctx.get("model_id")}),
    ):
        try:
            counts[name] = db[coll].delete_many(q).deleted_count
        except Exception:  # noqa: BLE001
            counts[name] = -1
    print(f"  {Y}bersih-bersih: " + " · ".join(f"{k}={v}" for k, v in counts.items()) + X)


# ══════════════════════════════════════════════════════════════════════════════
def main():  # noqa: C901 — satu alur uji berurutan, sengaja dibaca atas→bawah
    print(f"{C}{B}POC #32 — NILAI POTONGAN LAHIR SAAT DIPOTONG & TIDAK ADA POTONGAN YATIM{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    ctx: dict = {}
    stock0 = total_stock(db)
    print(f"  {Y}stok total sebelum uji: {stock0:,.2f}{X}")

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}) — {det(d)}{X}")
        return 2

    try:
        # ── SIAPKAN DATA NYATA ───────────────────────────────────────────────
        head("SIAPKAN — kain dibeli (harga lahir dari penerimaan) + gulungan + model")
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), None)
        if not loc:
            bad("SETUP", "tidak ada lokasi gudang")
            return 1

        st, sizes = call("GET", "/api/rahaza/sizes", token)
        sizes = sizes if isinstance(sizes, list) else (sizes or {}).get("items") or []
        by_code = {str(s.get("code", "")).upper(): s for s in sizes}
        need = ["M", "L", "XL", "XXL"]
        chosen = [by_code.get(c) for c in need]
        chosen = [c for c in chosen if c] or sizes[:4]
        if len(chosen) < 4:
            bad("SETUP", "master ukuran kurang dari 4 — POC butuh 4 ukuran berbeda")
            return 1
        size_m, size_l, size_xl, size_xxl = chosen[:4]

        fabrics = {}
        for key, code, name in (("mat_a", f"POC32-KAIN-A-{STAMP}", f"Kain POC32 A {STAMP}"),
                                ("mat_b", f"POC32-KAIN-B-{STAMP}", f"Kain POC32 B {STAMP}")):
            st, m = call("POST", "/api/rahaza/materials", token, {
                "code": code, "name": name, "type": "fabric", "unit": "m",
                "color": "Navy", "notes": MARK})
            if st != 200 or not (m or {}).get("id"):
                bad("SETUP", f"gagal membuat {code}", det(m))
                return 1
            ctx[key] = m["id"]
            fabrics[key] = m

        gr, err = receive(token, fabrics["mat_a"], 200, 30000, loc,
                          [{"qty": 100, "color_lot": f"LOT-{STAMP}", "notes": ""},
                           {"qty": 100, "color_lot": f"LOT-{STAMP}", "notes": ""}])
        if not gr:
            bad("SETUP", "penerimaan kain A gagal", err)
            return 1
        ctx["gr_a1"] = gr["id"]
        gr, err = receive(token, fabrics["mat_b"], 60, 0, loc,
                          [{"qty": 60, "color_lot": f"LOT-{STAMP}", "notes": ""}])
        if not gr:
            bad("SETUP", "penerimaan kain B gagal", err)
            return 1
        ctx["gr_b1"] = gr["id"]

        st, model = call("POST", "/api/rahaza/models", token, {
            "code": f"MDL-POC32-{STAMP}", "name": f"Potongan POC32 {STAMP}",
            "description": MARK})
        if st != 200 or not (model or {}).get("id"):
            bad("SETUP", "gagal membuat model master", det(model))
            return 1
        ctx["model_id"] = model["id"]

        ma = mat_get(token, ctx["mat_a"])
        mb = mat_get(token, ctx["mat_b"])
        rolls_a = rolls_of(db, ctx["mat_a"])
        rolls_b = rolls_of(db, ctx["mat_b"])
        if len(rolls_a) != 2 or len(rolls_b) != 1:
            bad("SETUP", "gulungan tidak terbit dari penerimaan",
                f"A={len(rolls_a)} B={len(rolls_b)}")
            return 1

        if near(ma.get("unit_cost"), 30000, 0.01) and float(mb.get("unit_cost") or 0) == 0:
            ok("T1", "harga kain lahir dari PENERIMAAN; kain tanpa harga tetap 0",
               f"A {money(ma.get('unit_cost'))}/m · B {money(0)}/m · "
               f"gulungan A={len(rolls_a)} B={len(rolls_b)}")
        else:
            bad("T1", "harga kain tidak lahir dari penerimaan",
                f"A={ma.get('unit_cost')} B={mb.get('unit_cost')}")

        # ── T2 — master potongan lahir & MENUNJUK induknya ───────────────────
        head("T2 — `start` melahirkan master potongan yang menunjuk induknya")
        o1, err = make_order(token, ctx, "a", fabrics["mat_a"], size_m, loc, 60, 120)
        if not o1:
            bad("T2", "order/start kain A gagal", err)
            return 1
        panel_a_id = o1.get("output_material_id")
        panel_a = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) or {}
        if not panel_a:
            bad("T2", "master potongan tidak lahir saat start")
        elif (panel_a.get("cutting_order_id") == ctx["order_a"]
              and panel_a.get("source_material_id") == ctx["mat_a"]
              and float(panel_a.get("unit_cost") or 0) == 0):
            ok("T2", "potongan lahir menunjuk ORDER + KAIN asalnya, nilainya masih 0",
               f"{panel_a.get('code')} · order={o1.get('number')} · "
               f"kain={panel_a.get('source_material_code')}")
        else:
            bad("T2", "tautan induk potongan tidak lengkap",
                f"cutting_order_id={panel_a.get('cutting_order_id')} "
                f"source={panel_a.get('source_material_id')} "
                f"unit_cost={panel_a.get('unit_cost')}")

        # ── T3 — progres #1: nilai kain berpindah SAAT ITU ───────────────────
        head("T3 — progres #1: 10 m × Rp30.000 ⇒ 20 pcs @ Rp15.000")
        st, p1 = call("POST", f"/api/cutting/orders/{ctx['order_a']}/progress", token,
                      {"input_consumed": 10, "output_qty": 20,
                       "roll_ids": [rolls_a[0]["id"]], "note": MARK})
        if st != 200:
            bad("T3", "progres #1 ditolak", f"HTTP {st} · {det(p1)}")
        else:
            pa = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) or {}
            lp = (p1 or {}).get("last_progress") or {}
            if near(pa.get("unit_cost"), 15000, 1.0):
                ok("T3", "HPP potongan lahir SAAT dipotong (bukan menunggu complete)",
                   f"{money(pa.get('unit_cost'))}/pcs · nilai kain keluar "
                   f"{money(lp.get('value_out'))}")
            else:
                bad("T3", "HPP potongan bukan 15.000",
                    f"unit_cost={pa.get('unit_cost')} · last_progress={json.dumps(lp)[:200]}")

        # ── T4 — penerimaan kedua ⇒ harga kain rata-rata bergerak ────────────
        head("T4 — penerimaan kedua 100 m @ Rp42.000 ⇒ harga kain jadi 34.137,931")
        gr, err = receive(token, fabrics["mat_a"], 100, 42000, loc,
                          [{"qty": 100, "color_lot": f"LOT2-{STAMP}", "notes": ""}])
        if not gr:
            bad("T4", "penerimaan kedua gagal", err)
        else:
            ctx["gr_a2"] = gr["id"]
            ma2 = mat_get(token, ctx["mat_a"])
            if near(ma2.get("unit_cost"), 34137.931, 0.05):
                ok("T4", "harga kain = rata-rata bergerak", f"{money(ma2.get('unit_cost'))}/m")
            else:
                bad("T4", "harga kain bukan 34.137,931", str(ma2.get("unit_cost")))

        # ── T5 — progres #2: HPP potongan RATA-RATA (tidak ditimpa) ──────────
        head("T5 — progres #2: 10 m × 34.137,931 ⇒ 10 pcs ⇒ WAC potongan 21.379,310")
        st, p2 = call("POST", f"/api/cutting/orders/{ctx['order_a']}/progress", token,
                      {"input_consumed": 10, "output_qty": 10,
                       "roll_ids": [rolls_a[0]["id"]], "note": MARK})
        if st != 200:
            bad("T5", "progres #2 ditolak", f"HTTP {st} · {det(p2)}")
        else:
            pa = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) or {}
            if near(pa.get("unit_cost"), 21379.31, 1.0):
                ok("T5", "HPP potongan = RATA-RATA BERGERAK, angka lama tidak dihapus",
                   f"{money(pa.get('unit_cost'))}/pcs (bukan 34.137,93 yang menimpa)")
            else:
                bad("T5", "HPP potongan bukan 21.379,31", str(pa.get("unit_cost")))

        # ── T6 — kekekalan nilai ────────────────────────────────────────────
        head("T6 — kekekalan nilai: Σ nilai kain keluar == nilai stok potongan")
        progs = list(db.cutting_progress.find({"cutting_order_id": ctx["order_a"]}, {"_id": 0}))
        value_out = round(sum(float(p.get("value_out") or 0) for p in progs), 2)
        st, panels = call("GET", "/api/cutting/output-materials", token)
        prow = next((p for p in (panels if isinstance(panels, list) else [])
                     if p.get("id") == panel_a_id), {})
        stock_value = round(float(prow.get("stock_qty") or 0) * float(prow.get("unit_cost") or 0), 2)
        if value_out > 0 and abs(value_out - stock_value) <= 1.0:
            ok("T6", "nilai kain yang keluar diterima seluruhnya oleh potongan",
               f"kain keluar {money(value_out)} == stok potongan {money(stock_value)} "
               f"({prow.get('stock_qty')} pcs × {money(prow.get('unit_cost'))})")
        else:
            bad("T6", "nilai tidak kekal (bocor)",
                f"kain keluar {value_out} vs stok potongan {stock_value}")

        # ── T7 — complete ───────────────────────────────────────────────────
        head("T7 — complete: nilai order benar & master potongan TIDAK ditimpa")
        before = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) or {}
        st, done = call("POST", f"/api/cutting/orders/{ctx['order_a']}/complete", token)
        after = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) or {}
        if st != 200:
            bad("T7", "complete ditolak", f"HTTP {st} · {det(done)}")
        elif (near(done.get("output_unit_cost"), 21379.31, 1.0)
              and near(done.get("total_input_cost"), 641379.31, 2.0)
              and near(after.get("unit_cost"), before.get("unit_cost"), 0.01)):
            ok("T7", "nilai order = Σ nilai kain keluar; master potongan tidak berubah",
               f"order {money(done.get('total_input_cost'))} · "
               f"{money(done.get('output_unit_cost'))}/pcs · master tetap "
               f"{money(after.get('unit_cost'))}")
        else:
            bad("T7", "angka complete tidak sesuai",
                f"output_unit_cost={done.get('output_unit_cost')} "
                f"total_input_cost={done.get('total_input_cost')} "
                f"master {before.get('unit_cost')}→{after.get('unit_cost')}")

        # ── T8 — kain belum bernilai ⇒ JUJUR ────────────────────────────────
        head("T8 — kain tanpa harga: potongan berstatus `unvalued`, bukan diam-diam 0")
        o2, err = make_order(token, ctx, "b", fabrics["mat_b"], size_l, loc, 30, 60)
        if not o2:
            bad("T8", "order kain B gagal", err)
        else:
            panel_b_id = o2.get("output_material_id")
            st, pb = call("POST", f"/api/cutting/orders/{ctx['order_b']}/progress", token,
                          {"input_consumed": 5, "output_qty": 10,
                           "roll_ids": [rolls_b[0]["id"]], "note": MARK})
            pbm = db.rahaza_materials.find_one({"id": panel_b_id}, {"_id": 0}) or {}
            warn = str((pb or {}).get("value_warning") or (pb or {}).get("notice") or "")
            if st != 200:
                bad("T8", "progres kain B ditolak", f"HTTP {st} · {det(pb)}")
            elif (float(pbm.get("unit_cost") or 0) == 0
                  and pbm.get("value_status") == "unvalued"
                  and ("belum" in warn.lower() and "harga" in warn.lower())):
                ok("T8", "potongan dari kain tanpa harga DIKATAKAN belum bernilai",
                   f"status={pbm.get('value_status')} · pesan: {warn[:120]}")
            else:
                bad("T8", "kekurangan nilai tidak dikatakan",
                    f"unit_cost={pbm.get('unit_cost')} status={pbm.get('value_status')} "
                    f"pesan={warn[:150]}")

        # ── T9 — cancel tidak meninggalkan yatim ────────────────────────────
        head("T9 — `cancel` sesudah `start` tidak meninggalkan master potongan yatim")
        o3, err = make_order(token, ctx, "c", fabrics["mat_b"], size_xl, loc, 10, 20)
        if not o3:
            bad("T9", "order/start ke-3 gagal", err)
        else:
            panel_c_id = o3.get("output_material_id")
            st, canc = call("POST", f"/api/cutting/orders/{ctx['order_c']}/cancel", token,
                            {"reason": MARK})
            left = db.rahaza_materials.find_one({"id": panel_c_id}, {"_id": 0})
            notice = str((canc or {}).get("notice") or "")
            if st != 200:
                bad("T9", "cancel ditolak", f"HTTP {st} · {det(canc)}")
            elif left is None and "potongan" in notice.lower():
                ok("T9", "potongan yang belum pernah bergerak ikut dibersihkan saat cancel",
                   notice[:140])
            else:
                bad("T9", "cancel meninggalkan master potongan yatim",
                    f"panel_masih_ada={bool(left)} notice={notice[:140]}")

        # ── T10 — deteksi + pembersih (idempoten) ───────────────────────────
        head("T10 — potongan yatim (order dihapus alat ukur) terdeteksi & bisa dibersihkan")
        o4, err = make_order(token, ctx, "d", fabrics["mat_b"], size_xxl, loc, 10, 20)
        if not o4:
            bad("T10", "order/start ke-4 gagal", err)
        else:
            panel_d_id = o4.get("output_material_id")
            # meniru PERSIS yang dilakukan alat ukur: dokumen order dihapus
            # langsung dari database, master potongannya tertinggal.
            db.cutting_orders.delete_one({"id": ctx["order_d"]})
            st, health = call("GET", "/api/cutting/panels/health", token)
            rows = (health or {}).get("items") or []
            hit = next((r for r in rows if r.get("id") == panel_d_id), None)
            if st != 200:
                bad("T10", "endpoint kesehatan potongan tidak ada / gagal",
                    f"HTTP {st} · {det(health)}")
            elif not hit:
                bad("T10", "potongan yatim TIDAK terdeteksi",
                    f"{len(rows)} baris dilaporkan, panel_d tidak ada")
            elif "order_missing" not in (hit.get("reasons") or []) or not hit.get("cleanable"):
                bad("T10", "alasan/kelayakan pembersihan salah", json.dumps(hit)[:220])
            else:
                st, res = call("POST", "/api/cutting/panels/cleanup", token,
                               {"ids": [panel_d_id]})
                gone = db.rahaza_materials.find_one({"id": panel_d_id}, {"_id": 0}) is None
                st2, res2 = call("POST", "/api/cutting/panels/cleanup", token,
                                 {"ids": [panel_d_id]})
                again = int((res2 or {}).get("removed") or 0)
                if st == 200 and gone and again == 0:
                    ok("T10", "yatim terdeteksi (order_missing), dibersihkan, dan idempoten",
                       f"dibersihkan={(res or {}).get('removed')} · ulang={again} · "
                       f"alasan={hit.get('reasons')}")
                else:
                    bad("T10", "pembersihan tidak tuntas / tidak idempoten",
                        f"HTTP {st} gone={gone} ulang={again} · {det(res)}")

        # ── T11 — yatim BERSTOK tidak boleh dihapus ─────────────────────────
        head("T11 — potongan yatim yang MASIH BERSTOK tidak dihapus, hanya dilaporkan")
        db.rahaza_materials.delete_one({"id": ctx["mat_a"]})   # kain sumber hilang
        st, health = call("GET", "/api/cutting/panels/health", token)
        rows = (health or {}).get("items") or []
        hit = next((r for r in rows if r.get("id") == panel_a_id), None)
        if st != 200 or not hit:
            bad("T11", "potongan dengan kain sumber hilang tidak terdeteksi",
                f"HTTP {st} · {len(rows)} baris")
        elif ("source_missing" in (hit.get("reasons") or []) and not hit.get("cleanable")
              and hit.get("block_reason")):
            st, res = call("POST", "/api/cutting/panels/cleanup", token, {"ids": [panel_a_id]})
            still = db.rahaza_materials.find_one({"id": panel_a_id}, {"_id": 0}) is not None
            if still and int((res or {}).get("removed") or 0) == 0:
                ok("T11", "yatim berstok DIPERTAHANKAN + alasannya disebut",
                   f"stok={hit.get('stock_qty')} pcs · {hit.get('block_reason')[:110]}")
            else:
                bad("T11", "potongan berstok ikut terhapus (stok jadi hantu)",
                    f"masih_ada={still} · {det(res)}")
        else:
            bad("T11", "alasan yatim/penahan tidak lengkap", json.dumps(hit)[:220])

        # ── T12 — layar Master Potongan dapat nilai + asal + status ─────────
        head("T12 — daftar Master Potongan mengirim nilai, asal, dan status nilai")
        st, panels = call("GET", "/api/cutting/output-materials", token)
        rows = panels if isinstance(panels, list) else (panels or {}).get("items") or []
        prow = next((p for p in rows if p.get("id") == panel_a_id), {})
        needed = ["stock_qty", "unit_cost", "stock_value", "value_status",
                  "source_material_code", "cutting_order_number", "orphan"]
        missing = [k for k in needed if k not in prow]
        if not prow:
            bad("T12", "potongan tidak muncul di daftar Master Potongan")
        elif missing:
            bad("T12", "daftar potongan belum mengirim semua yang dibutuhkan layar",
                f"kurang: {missing}")
        else:
            ok("T12", "daftar potongan lengkap: nilai + asal + status + penanda yatim",
               f"{prow.get('code')} · {prow.get('stock_qty')} pcs × "
               f"{money(prow.get('unit_cost'))} = {money(prow.get('stock_value'))} · "
               f"status={prow.get('value_status')} · yatim={prow.get('orphan')}")

    finally:
        print()
        if KEEP:
            print(f"  {Y}--keep: data uji DIBIARKAN (order/potongan/kain POC32-{STAMP}){X}")
        else:
            cleanup(db, ctx)
            stock1 = total_stock(db)
            if abs(stock1 - stock0) < 0.01:
                ok("BERSIH", "alat ukur tidak mengotori data", f"stok total tetap {stock1:,.2f}")
            else:
                bad("BERSIH", "stok total berubah sesudah uji",
                    f"{stock0:,.2f} → {stock1:,.2f}")

    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} gagal / {len(PASS)} lulus: "
              f"{', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} uji lulus{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
