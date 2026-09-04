#!/usr/bin/env python3
"""test_core_hpp_potong_dan_bom_cutting.py — POC INTI SESI 2026-08-23.

MEMBUKTIKAN DUA HAL YANG DIMINTA PEMILIK (lewat API NYATA, data NYATA):

  A. **HPP per potong & per model** lahir dari data, bukan ketikan:
     BOM × harga bahan hasil PEMBELIAN (rata-rata bergerak, SADAR SATUAN)
     + upah CMT + upah cutting/internal [+ overhead OPSIONAL]
     → margin & usulan harga jual sebelum harga jual ditetapkan
     → diterapkan ke master/FG/katalog sehingga kolom margin Marketing HIDUP.

  B. **BOM di dialog Cutting**: kebutuhan kain per pcs & total datang dari BOM
     model+size (tidak lagi ditebak), aksesoris ikut terlihat, dan kejujuran
     dijaga (BOM tidak ada / kain tidak ada di BOM / satuan belum jelas).

KENAPA POC INI PERLU (fakta terukur sebelum pekerjaan ini)
---------------------------------------------------------
  · `rahaza_materials` type='fg' = 321 dokumen, **semuanya `hpp: 0`,
    `hpp_source: 'none'`** ⇒ HPP produk jadi belum pernah lahir.
  · Satu-satunya sumber HPP model: `hpp_rnd` (kalkulator R&D) atau `base_hpp`
    (KETIKAN MANUAL) ⇒ bertentangan dengan keputusan pemilik sesi #30
    ("harga jangan dari ketikan master").
  · `planned_input_qty` order cutting diketik manual walau BOM per model+size
    sudah menyimpan kebutuhan per pcs.

ANGKA UJI (dihitung tangan lebih dulu — tidak boleh "apa pun yang keluar")
-------------------------------------------------------------------------
  Kain   : dibeli 100 m @ Rp25.000  ⇒ unit_cost 25.000/m
  Kancing: dibeli 120 pcs @ Rp500   ⇒ unit_cost 500/pcs
  Label  : TIDAK PERNAH dibeli      ⇒ unit_cost 0  (harus jadi KEKURANGAN)
  BOM (ukuran M):
    · kain 150 **cm**   → 1,5 m  × 25.000 = 37.500   (bukti: cm→m, tidak 150 m)
    · kancing 0,5 **lusin** → 6 pcs × 500 =  3.000   (bukti: lusin→pcs, tidak 0,5 pcs)
    · label 1 pcs × 0                     =      0   (bukti: TIDAK diam-diam 0)
    biaya bahan/pcs = **40.500**
  Upah tarif standar proses: CUTTING 700 + FINISHING 300 = **1.000**
  Upah dikunci pemilik: CMT **8.500** · internal **1.500**
  HPP/pcs = 40.500 + 8.500 + 1.500 = **50.500**  (overhead MATI)
  HPP/pcs + overhead 1.000 = **51.500**          (saklar overhead HIDUP)
  Target margin 40% ⇒ usulan harga jual = 50.500 / 0,6 = **84.166,67**
  Harga jual katalog 100.000 ⇒ margin 49.500 (**49,5%**)
  BOM di cutting untuk 100 pcs ⇒ kain **150 m** (1,5 m × 100)

SELF-CLEANING (INV-F30 V15): semua artefak uji dihapus, setelan costing
dipulihkan, dan TOTAL STOK dibuktikan kembali ke angka sebelum uji.

Pakai:  python3 test_core_hpp_potong_dan_bom_cutting.py [--keep]
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
STAMP = time.strftime("HPP%H%M%S")
MARK = f"POC HPP potong {STAMP}"
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
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None, method=method)
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
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:200]


def near(a, b, tol=0.51):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def money(v):
    try:
        return f"Rp{float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


# ══════════════════════════════════════════════════════════════════════════════
def total_stock(db):
    row = list(db.rahaza_material_stock.aggregate(
        [{"$group": {"_id": None, "t": {"$sum": "$qty"}}}]))
    return round(float(row[0]["t"]) if row else 0.0, 4)


def cleanup(db, ctx):
    """Hapus SEMUA artefak uji + pulihkan setelan costing (self-cleaning)."""
    mids = [m for m in (ctx.get("mat_fabric"), ctx.get("mat_acc"), ctx.get("mat_label"),
                        ctx.get("mat_other")) if m]
    model_id = ctx.get("model_id")
    fg_ids = []
    if model_id:
        fg_ids = [f["id"] for f in db.rahaza_materials.find(
            {"model_id": model_id}, {"_id": 0, "id": 1})]
    all_mat = mids + fg_ids
    gr_nos = [g for g in [ctx.get("gr_no"), ctx.get("gr_no2"), ctx.get("gr_no3")] if g]
    for coll, q in (
        ("marketing_catalog_items", {"id": {"$in": [i for i in [ctx.get("cat_item")] if i]}}),
        ("product_cost_snapshots", {"model_id": model_id}),
        ("rahaza_model_costing", {"model_id": model_id}),
        ("rahaza_boms", {"model_id": model_id}),
        ("rahaza_model_variants", {"model_id": model_id}),
        ("rahaza_stock_ledger", {"material_id": {"$in": all_mat}}),
        ("rahaza_material_stock", {"material_id": {"$in": all_mat}}),
        ("warehouse_movements", {"material_id": {"$in": all_mat}}),
        ("rahaza_material_movements", {"material_id": {"$in": all_mat}}),
        ("rahaza_material_cost_history", {"material_id": {"$in": all_mat}}),
        ("warehouse_receiving", {"id": {"$in": [g for g in [ctx.get("gr_id"), ctx.get("gr_id2"),
                                                            ctx.get("gr_id3")] if g]}}),
        ("rahaza_purchase_orders", {"id": {"$in": [p for p in [ctx.get("po_id"), ctx.get("po_id2"),
                                                               ctx.get("po_id3")] if p]}}),
        ("rahaza_journal_entries", {"reference": {"$in": gr_nos}}),
        ("journal_entries", {"reference": {"$in": gr_nos}}),
        ("rahaza_materials", {"id": {"$in": all_mat}}),
        ("rahaza_models", {"id": model_id}),
    ):
        if not q:
            continue
        try:
            db[coll].delete_many(q)
        except Exception:  # noqa: BLE001
            pass
    # setelan costing dipulihkan APA ADANYA
    before = ctx.get("settings_before")
    if before is not None:
        try:
            if before:
                db.rahaza_costing_settings.replace_one({"id": "GLOBAL"}, before, upsert=True)
            else:
                db.rahaza_costing_settings.delete_one({"id": "GLOBAL"})
        except Exception:  # noqa: BLE001
            pass


# ══════════════════════════════════════════════════════════════════════════════
def buy(token, ctx, key, material_id, qty, price, loc_id):
    """PO → approve → GR → terima: HARGA LAHIR DARI PEMBELIAN (jalur nyata)."""
    st, po = call("POST", "/api/rahaza/purchase-orders", token, {
        "vendor_name": f"Pemasok POC {STAMP}", "notes": MARK,
        "items": [{"material_id": material_id, "qty_input": qty, "unit_cost_input": price}]})
    if st != 200 or not po.get("id"):
        return False, f"PO gagal: HTTP {st} · {det(po)}"
    ctx[f"po_id{key}"] = po["id"]
    call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", token, {"notes": MARK})
    for _ in range(4):
        st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", token, {"notes": MARK})
        if (r or {}).get("status") == "approved":
            break
    st, gr = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/create-gr", token, {})
    if st != 200 or not gr.get("id"):
        return False, f"GR gagal: HTTP {st} · {det(gr)}"
    ctx[f"gr_id{key}"] = gr["id"]
    ctx[f"gr_no{key}"] = gr.get("receipt_number")
    items = [{**it, "received_qty": qty, "rejected_qty": 0, "location_id": loc_id}
             for it in (gr.get("items") or [])]
    st, upd = call("PUT", f"/api/warehouse/receiving/{gr['id']}", token,
                   {"status": "received", "items": items, "location_id": loc_id})
    if st != 200:
        return False, f"terima barang gagal: HTTP {st} · {det(upd)}"
    return True, ""


def main():  # noqa: C901 - satu alur uji berurutan, sengaja dibaca dari atas ke bawah
    print(f"{C}{B}POC — HPP PER POTONG & PER MODEL + BOM DI DIALOG CUTTING{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    ctx: dict = {"settings_before": db.rahaza_costing_settings.find_one({"id": "GLOBAL"})}
    stock0 = total_stock(db)
    print(f"  {Y}stok total sebelum uji: {stock0:,.2f}{X}")

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2

    try:
        # ══════════════════════════════════════════════════════════════════
        head("SIAPKAN DATA NYATA — bahan dibeli, model+varian, BOM sadar satuan")
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), {})
        if not loc:
            bad("SETUP", "tidak ada lokasi gudang untuk menerima barang")
            return 1

        mats = {
            "mat_fabric": {"code": f"POC-KAIN-{STAMP}", "name": f"Kain POC {STAMP}",
                           "type": "fabric", "unit": "m", "color": "Navy"},
            "mat_acc": {"code": f"POC-KANCING-{STAMP}", "name": f"Kancing POC {STAMP}",
                        "type": "accessory", "unit": "pcs"},
            "mat_label": {"code": f"POC-LABEL-{STAMP}", "name": f"Label POC {STAMP}",
                          "type": "accessory", "unit": "pcs"},
            "mat_other": {"code": f"POC-KAIN2-{STAMP}", "name": f"Kain Lain POC {STAMP}",
                          "type": "fabric", "unit": "m"},
        }
        for key, payload in mats.items():
            st, m = call("POST", "/api/rahaza/materials", token, {**payload, "notes": MARK})
            if st != 200 or not m.get("id"):
                bad("SETUP", f"gagal membuat material {payload['code']}", det(m))
                return 1
            ctx[key] = m["id"]

        okk, err = buy(token, ctx, "", ctx["mat_fabric"], 100, 25000, loc.get("id"))
        if not okk:
            bad("SETUP", "pembelian kain gagal", err)
            return 1
        okk, err = buy(token, ctx, "2", ctx["mat_acc"], 120, 500, loc.get("id"))
        if not okk:
            bad("SETUP", "pembelian kancing gagal", err)
            return 1

        st, mf = call("GET", f"/api/rahaza/materials/{ctx['mat_fabric']}", token)
        st, ma = call("GET", f"/api/rahaza/materials/{ctx['mat_acc']}", token)
        st, ml = call("GET", f"/api/rahaza/materials/{ctx['mat_label']}", token)
        if not (near(mf.get("unit_cost"), 25000, 0.01) and near(ma.get("unit_cost"), 500, 0.01)):
            bad("T1", "harga bahan TIDAK lahir dari pembelian",
                f"kain={mf.get('unit_cost')} kancing={ma.get('unit_cost')}")
        elif float(ml.get("unit_cost") or 0) != 0:
            bad("T1", "bahan yang belum pernah dibeli malah punya harga",
                f"label={ml.get('unit_cost')}")
        else:
            ok("T1", "harga bahan lahir dari PEMBELIAN (rata-rata bergerak), yang belum dibeli tetap 0",
               f"kain {money(mf['unit_cost'])}/m · kancing {money(ma['unit_cost'])}/pcs · "
               f"label {money(0)} (metode {mf.get('cost_method')})")

        # model + varian (FG otomatis lahir dari varian) + BOM
        st, model = call("POST", "/api/rahaza/models", token, {
            "code": f"MDL-POC-{STAMP}", "name": f"Kemeja POC {STAMP}",
            "description": MARK})
        if st != 200 or not model.get("id"):
            bad("SETUP", "gagal membuat model master", det(model))
            return 1
        ctx["model_id"] = model["id"]

        st, sizes = call("GET", "/api/rahaza/sizes", token)
        sizes = sizes if isinstance(sizes, list) else (sizes or {}).get("items") or []
        size_m = next((s for s in sizes if (s.get("code") or "").upper() == "M"), None) or sizes[0]
        size_l = next((s for s in sizes if (s.get("code") or "").upper() == "L"), None)
        ctx["size_m"] = size_m["id"]
        st, colors = call("GET", "/api/rahaza/colors", token)
        colors = colors if isinstance(colors, list) else (colors or {}).get("items") or []
        color = colors[0] if colors else None
        if not color:
            bad("SETUP", "master warna kosong — varian tidak bisa dibuat")
            return 1
        st, variant = call("POST", "/api/rahaza/variants", token, {
            "model_id": ctx["model_id"], "size_id": size_m["id"], "color_id": color["id"],
            "notes": MARK})
        if st != 200 or not variant.get("id"):
            bad("SETUP", "gagal membuat varian", det(variant))
            return 1
        ctx["variant_id"] = variant["id"]
        if size_l:
            call("POST", "/api/rahaza/variants", token, {
                "model_id": ctx["model_id"], "size_id": size_l["id"], "color_id": color["id"],
                "notes": MARK})
            ctx["size_l"] = size_l["id"]

        st, bom = call("POST", "/api/rahaza/boms", token, {
            "model_id": ctx["model_id"], "size_id": size_m["id"], "notes": MARK,
            "materials": [
                {"material_id": ctx["mat_fabric"], "code": mats["mat_fabric"]["code"],
                 "name": mats["mat_fabric"]["name"], "material_type": "fabric",
                 "qty": 150, "unit": "cm"},
                {"material_id": ctx["mat_acc"], "code": mats["mat_acc"]["code"],
                 "name": mats["mat_acc"]["name"], "material_type": "accessory",
                 "qty": 0.5, "unit": "lusin"},
                {"material_id": ctx["mat_label"], "code": mats["mat_label"]["code"],
                 "name": mats["mat_label"]["name"], "material_type": "accessory",
                 "qty": 1, "unit": "pcs"},
            ]})
        if st != 200 or not bom.get("id"):
            bad("SETUP", "gagal membuat BOM", det(bom))
            return 1
        ctx["bom_id"] = bom["id"]
        print(f"  {Y}siap: model {model.get('code')} · BOM v{bom.get('version')} ukuran "
              f"{size_m.get('code')} · 3 baris bahan{X}")

        # ══════════════════════════════════════════════════════════════════
        head("T2/T3 — biaya bahan per pcs SADAR SATUAN + kekurangan yang jujur")
        call("PUT", "/api/costing/settings", token,
             {"include_overhead_in_product_hpp": False, "target_margin_pct": 40,
              "overhead_rate_per_pcs": 1000, "process_rates": []})
        st, cost = call("GET", f"/api/costing/models/{ctx['model_id']}", token)
        if st != 200:
            bad("T2", "endpoint HPP model gagal", f"HTTP {st} · {det(cost)}")
            return 1
        row = next((s for s in cost["sizes"] if s["size_id"] == size_m["id"]), None)
        if not row:
            bad("T2", "ukuran M tidak muncul di hasil HPP", str([s["size_code"] for s in cost["sizes"]]))
        elif not near(row["material_cost"], 40500):
            lines = [f"{ln['code']} {ln['qty_input']}{ln['unit_input']}→{ln['qty_base']}{ln['unit_base']} "
                     f"× {ln['unit_cost']} = {ln['amount']}" for ln in row["lines"]]
            bad("T2", "biaya bahan/pcs SALAH (satuan tidak dikonversi?)",
                f"dapat {row['material_cost']} (harus 40.500) · {lines}")
        else:
            fab = next((ln for ln in row["lines"] if ln["material_id"] == ctx["mat_fabric"]), {})
            acc = next((ln for ln in row["lines"] if ln["material_id"] == ctx["mat_acc"]), {})
            ok("T2", "biaya bahan/pcs benar & satuan BOM dikonversi ke satuan dasar",
               f"kain 150 cm → {fab.get('qty_base')} m × {money(fab.get('unit_cost'))} = "
               f"{money(fab.get('amount'))} · kancing 0,5 lusin → {acc.get('qty_base')} pcs × "
               f"{money(acc.get('unit_cost'))} = {money(acc.get('amount'))} ⇒ total "
               f"{money(row['material_cost'])}")

        gap_codes = [g["code"] for g in cost["gaps"]]
        label_line = next((ln for ln in (row or {}).get("lines", [])
                           if ln["material_id"] == ctx["mat_label"]), {})
        if "material_unvalued" not in gap_codes:
            bad("T3", "bahan tanpa harga TIDAK dilaporkan sebagai kekurangan", str(gap_codes))
        elif label_line.get("status") != "unvalued" or row["computable"] is not False:
            bad("T3", "baris bahan tanpa harga tidak ditandai / HPP diklaim lengkap",
                f"status={label_line.get('status')} computable={row['computable']}")
        else:
            g = next(x for x in cost["gaps"] if x["code"] == "material_unvalued")
            ok("T3", "bahan tanpa harga jadi KEKURANGAN yang bisa ditindak (bukan diam-diam 0)",
               f"'{g['message'][:60]}…' → aksi: {g['action']} (layar {g['target']})")

        # ══════════════════════════════════════════════════════════════════
        head("T4 — upah cutting/internal dari tarif standar proses (bukan tebakan)")
        st, procs = call("GET", "/api/costing/processes", token)
        pmap = {(p["code"] or "").upper(): p for p in (procs or {}).get("items", [])}
        rates = []
        for code, rate in (("CUTTING", 700), ("FINISHING", 300)):
            if code in pmap:
                rates.append({"process_id": pmap[code]["process_id"], "code": code,
                              "name": pmap[code]["name"], "rate_per_pcs": rate})
        if pmap.get("SEWING"):
            rates.append({"process_id": pmap["SEWING"]["process_id"], "code": "SEWING",
                          "name": "Jahit (CMT)", "rate_per_pcs": 9999})
        call("PUT", "/api/costing/settings", token, {"process_rates": rates})
        st, cost = call("GET", f"/api/costing/models/{ctx['model_id']}", token)
        lab = cost["internal_labor"]
        if not near(lab["rate"], 1000):
            bad("T4", "upah internal tidak mengikuti tarif standar proses",
                f"dapat {lab['rate']} (harus 1.000 = 700+300; SEWING 9.999 harus DIKECUALIKAN)")
        elif lab["source"] != "settings_process_rates":
            bad("T4", "sumber upah internal tidak dilaporkan benar", lab["source"])
        elif "cmt_rate_missing" not in [g["code"] for g in cost["gaps"]]:
            bad("T4", "upah CMT kosong tidak dilaporkan sebagai kekurangan",
                str([g["code"] for g in cost["gaps"]]))
        else:
            ok("T4", "upah internal = tarif standar proses; proses JAHIT/CMT tidak dihitung dua kali",
               f"{money(lab['rate'])}/pcs dari {len(lab['processes'])} proses ({lab['source']}) · "
               f"upah CMT masih kosong → kekurangan dilaporkan, kandidat "
               f"{len(cost['cmt']['candidates'])} tarif nyata")

        # ══════════════════════════════════════════════════════════════════
        head("T5/T6 — upah dikunci pemilik → HPP/pcs & saklar overhead")
        st, ovr = call("PUT", f"/api/costing/models/{ctx['model_id']}/labor", token,
                       {"cmt_rate_per_pcs": 8500, "internal_labor_per_pcs": 1500,
                        "notes": MARK})
        st, cost = call("GET", f"/api/costing/models/{ctx['model_id']}", token)
        row = next((s for s in cost["sizes"] if s["size_id"] == size_m["id"]), {})
        if not near(row.get("hpp_unit"), 50500):
            bad("T5", "HPP/pcs salah setelah upah dikunci",
                f"dapat {row.get('hpp_unit')} (harus 50.500 = 40.500+8.500+1.500) · "
                f"cmt={cost['cmt']['rate']} internal={cost['internal_labor']['rate']}")
        elif cost["cmt"]["source"] != "owner" or cost["internal_labor"]["source"] != "owner":
            bad("T5", "sumber upah tidak menyebut 'dikunci pemilik'",
                f"{cost['cmt']['source']}/{cost['internal_labor']['source']}")
        else:
            ok("T5", "HPP/pcs = bahan + upah CMT + upah cutting/internal",
               f"{money(row['material_cost'])} + {money(row['cmt_cost'])} + "
               f"{money(row['internal_labor_cost'])} = {money(row['hpp_unit'])}/pcs")

        st, cost_oh = call("GET", f"/api/costing/models/{ctx['model_id']}?include_overhead=1", token)
        row_oh = next((s for s in cost_oh["sizes"] if s["size_id"] == size_m["id"]), {})
        if row.get("overhead_cost") != 0 or not near(row_oh.get("hpp_unit"), 51500):
            bad("T6", "saklar overhead tidak bekerja seperti keputusan pemilik",
                f"tanpa overhead={row.get('overhead_cost')} dengan overhead={row_oh.get('hpp_unit')}")
        else:
            ok("T6", "overhead OPSIONAL: default mati, bisa dihidupkan tanpa mengubah HPP tersimpan",
               f"mati {money(row['hpp_unit'])} → hidup {money(row_oh['hpp_unit'])} "
               f"(+{money(row_oh['overhead_cost'])})")

        # ══════════════════════════════════════════════════════════════════
        head("T7 — margin & usulan harga jual (sebelum harga jual ditetapkan)")
        exp_sug = round(50500 / 0.6, 2)
        if not near(row.get("suggested_price"), exp_sug, 1.0):
            bad("T7", "usulan harga jual dari target margin salah",
                f"dapat {row.get('suggested_price')} (harus ±{exp_sug} untuk margin 40%)")
        elif row.get("has_price") is not False:
            bad("T7", "produk tanpa harga jual diklaim punya harga", str(row.get("price")))
        else:
            ok("T7", "usulan harga jual lahir dari target margin, dan 'belum ada harga' dikatakan jujur",
               f"HPP {money(row['hpp_unit'])} · target {cost['target_margin_pct']}% ⇒ usul "
               f"{money(row['suggested_price'])} · kekurangan harga jual dilaporkan: "
               f"{'selling_price_missing' in [g['code'] for g in cost['gaps']]}")

        # harga jual nyata lewat katalog Marketing → margin harus hidup
        fg = db.rahaza_materials.find_one(
            {"type": "fg", "model_id": ctx["model_id"], "size_id": size_m["id"]}, {"_id": 0})
        if not fg:
            bad("T8", "FG varian tidak lahir dari master varian — tidak bisa uji margin katalog")
        else:
            ctx["fg_id"] = fg["id"]
            cat = db.marketing_catalogs.find_one({}, {"_id": 0, "id": 1})
            st, item = call("POST", f"/api/marketing/catalogs/{cat['id']}/items/from-fg", token,
                            {"fg_material_id": fg["id"], "price": 100000,
                             "platform_price": 100000, "stock_alert_threshold": 5})
            item_doc = (item or {}).get("item") if isinstance((item or {}).get("item"), dict) else item
            if st not in (200, 201) or not (item_doc or {}).get("id"):
                bad("T8", "gagal membuat item katalog uji", f"HTTP {st} · {det(item)}")
            else:
                ctx["cat_item"] = item_doc["id"]
                st, cost2 = call("GET", f"/api/costing/models/{ctx['model_id']}", token)
                row2 = next((s for s in cost2["sizes"] if s["size_id"] == size_m["id"]), {})
                if not (near(row2.get("margin"), 49500) and near(row2.get("margin_pct"), 49.5, 0.1)):
                    bad("T7b", "margin terhadap harga jual nyata salah",
                        f"margin={row2.get('margin')} pct={row2.get('margin_pct')} "
                        f"harga={row2.get('price')}")
                else:
                    ok("T7b", "margin dihitung terhadap harga jual yang BERLAKU di katalog",
                       f"harga {money(row2['price']['best_price'])} − HPP {money(row2['hpp_unit'])} "
                       f"= {money(row2['margin'])} ({row2['margin_pct']}%) · sumber harga "
                       f"{row2['price']['price_source']}")

        # ══════════════════════════════════════════════════════════════════
        head("T8 — TERAPKAN: HPP masuk master + FG per ukuran + item katalog Marketing")
        st, applied = call("POST", f"/api/costing/models/{ctx['model_id']}/apply", token, {})
        if st != 200 or not applied.get("ok"):
            bad("T8", "penerapan HPP gagal", f"HTTP {st} · {det(applied)}")
        else:
            fg_after = db.rahaza_materials.find_one({"id": ctx.get("fg_id")}, {"_id": 0}) or {}
            model_after = db.rahaza_models.find_one({"id": ctx["model_id"]}, {"_id": 0}) or {}
            item_after = db.marketing_catalog_items.find_one(
                {"id": ctx.get("cat_item")}, {"_id": 0}) if ctx.get("cat_item") else {}
            if not near(fg_after.get("hpp"), 50500) or fg_after.get("hpp_source") != "bom":
                bad("T8", "HPP tidak tertulis ke FG per ukuran",
                    f"hpp={fg_after.get('hpp')} source={fg_after.get('hpp_source')}")
            elif not near(model_after.get("hpp_bom"), 50500) or model_after.get("hpp_source") != "bom":
                bad("T8", "HPP tidak tertulis ke master produk",
                    f"hpp_bom={model_after.get('hpp_bom')} source={model_after.get('hpp_source')}")
            elif ctx.get("cat_item") and (not near((item_after or {}).get("hpp"), 50500)
                                          or (item_after or {}).get("hpp_source") != "bom"):
                bad("T8", "margin di Katalog Marketing tidak hidup",
                    f"item.hpp={(item_after or {}).get('hpp')} "
                    f"source={(item_after or {}).get('hpp_source')}")
            else:
                skipped = [s["size_code"] for s in applied["skipped"]]
                ok("T8", "HPP diterapkan: master + FG per ukuran + item katalog (margin HIDUP)",
                   f"{len(applied['applied'])} ukuran diterapkan @{money(applied['hpp_model'])} · "
                   f"FG diperbarui {applied['fg_updated']} · item katalog "
                   f"{applied['catalog_items_updated']} · ukuran tanpa BOM dilewati: "
                   f"{skipped or '—'} · HPP sebelumnya {money(applied['hpp_before'])} "
                   f"({applied['hpp_source_before']})")

            st, applied2 = call("POST", f"/api/costing/models/{ctx['model_id']}/apply", token, {})
            fg2 = db.rahaza_materials.find_one({"id": ctx.get("fg_id")}, {"_id": 0}) or {}
            snaps = db.product_cost_snapshots.count_documents({"model_id": ctx["model_id"]})
            if st != 200 or not near(fg2.get("hpp"), 50500) or snaps < 2:
                bad("T9", "penerapan kedua tidak idempoten / tanpa jejak audit",
                    f"HTTP {st} hpp={fg2.get('hpp')} snapshot={snaps}")
            else:
                ok("T9", "penerapan idempoten + jejak audit tersimpan",
                   f"HPP tetap {money(fg2['hpp'])} setelah 2× terapkan · {snaps} snapshot audit")

        # daftar model juga harus menampilkan model ini dengan angka yang sama
        st, lst = call("GET", f"/api/costing/models?q=POC-{STAMP}", token)
        mine = next((r for r in (lst or {}).get("items", [])
                     if r["model_id"] == ctx["model_id"]), None)
        if not mine:
            bad("T10", "model tidak muncul di daftar HPP", det(lst))
        elif not near(mine["hpp_avg"], 50500) or mine["status"] != "partial" \
                or "material_unvalued" not in mine["gap_codes"]:
            bad("T10", "ringkasan daftar HPP tidak sama dengan rincian / status tidak jujur",
                f"avg={mine['hpp_avg']} status={mine['status']} (harus 'partial' selama ada "
                f"bahan tanpa harga) gaps={mine['gap_codes']}")
        else:
            ok("T10", "daftar HPP sejalan dengan rincian & status JUJUR selagi ada kekurangan",
               f"{mine['code']} · HPP {money(mine['hpp_avg'])} · margin {mine['margin_pct']}% · "
               f"kekurangan {mine['gap_count']} ({', '.join(mine['gap_codes'])}) · status "
               f"{mine['status']}")

        # ══════════════════════════════════════════════════════════════════
        head("T10b — kekurangan TERTUTUP begitu datanya datang (label akhirnya dibeli)")
        okk, err = buy(token, ctx, "3", ctx["mat_label"], 100, 250, loc.get("id"))
        if not okk:
            bad("T10b", "pembelian label gagal", err)
        else:
            st, cost3 = call("GET", f"/api/costing/models/{ctx['model_id']}", token)
            row3 = next((s for s in cost3["sizes"] if s["size_id"] == size_m["id"]), {})
            st, lst3 = call("GET", f"/api/costing/models?q=POC-{STAMP}", token)
            mine3 = next((r for r in (lst3 or {}).get("items", [])
                          if r["model_id"] == ctx["model_id"]), {})
            if not (near(row3.get("material_cost"), 40750) and near(row3.get("hpp_unit"), 50750)):
                bad("T10b", "HPP tidak ikut naik saat bahan terakhir akhirnya punya harga",
                    f"bahan={row3.get('material_cost')} (harus 40.750) hpp={row3.get('hpp_unit')} "
                    f"(harus 50.750)")
            elif row3.get("confidence") != "full" or mine3.get("status") != "ready":
                bad("T10b", "status tidak berubah menjadi lengkap/siap",
                    f"confidence={row3.get('confidence')} status={mine3.get('status')}")
            elif "material_unvalued" in [g["code"] for g in cost3["gaps"]]:
                bad("T10b", "kekurangan lama masih dilaporkan padahal sudah dibeli",
                    str([g["code"] for g in cost3["gaps"]]))
            else:
                ok("T10b", "kekurangan hilang sendiri setelah bahan dibeli — HPP naik sesuai harga beli",
                   f"label dibeli @{money(250)} ⇒ bahan {money(row3['material_cost'])} · HPP "
                   f"{money(row3['hpp_unit'])}/pcs · status {mine3['status']} "
                   f"(confidence {row3['confidence']})")

        # ══════════════════════════════════════════════════════════════════
        head("T11/T12 — BOM di dialog Cutting: kebutuhan kain tidak lagi ditebak")
        st, req = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model_id']}"
                               f"&size_id={size_m['id']}&qty_pcs=100"
                               f"&input_material_id={ctx['mat_fabric']}"), token)
        fabr = (req or {}).get("fabric") or {}
        accs = (req or {}).get("accessories") or []
        if st != 200 or not req.get("has_bom"):
            bad("T11", "endpoint kebutuhan BOM cutting gagal", f"HTTP {st} · {det(req)}")
        elif not (near(fabr.get("qty_per_pcs"), 1.5, 0.001) and near(fabr.get("qty_total"), 150, 0.01)
                  and fabr.get("unit") == "m"):
            bad("T11", "kebutuhan kain salah",
                f"per pcs={fabr.get('qty_per_pcs')} total={fabr.get('qty_total')} "
                f"satuan={fabr.get('unit')} (harus 1,5 m/pcs → 150 m untuk 100 pcs)")
        elif fabr.get("matches_input") is not True or len(accs) != 2:
            bad("T11", "kain terpilih tidak dikenali / aksesoris tidak ikut tampil",
                f"matches_input={fabr.get('matches_input')} aksesoris={len(accs)}")
        else:
            acc_txt = ", ".join(
                f"{a['name'][:14]} {a['qty_total']:g} {a['unit']}" for a in accs)
            ok("T11", "kebutuhan kain & aksesoris datang dari BOM model+ukuran",
               f"kain {fabr['qty_per_pcs']} {fabr['unit']}/pcs × 100 pcs = "
               f"{fabr['qty_total']} {fabr['unit']} (nilai {money(fabr['amount_total'])}) · "
               f"aksesoris {acc_txt}")

        st, wrong = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model_id']}"
                                 f"&size_id={size_m['id']}&qty_pcs=10"
                                 f"&input_material_id={ctx['mat_other']}"), token)
        codes_wrong = [g["code"] for g in (wrong or {}).get("gaps", [])]
        no_bom_size = ctx.get("size_l") or "00000000-0000-0000-0000-000000000000"
        st2, nobom = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model_id']}"
                                  f"&size_id={no_bom_size}&qty_pcs=10"), token)
        codes_nobom = [g["code"] for g in (nobom or {}).get("gaps", [])]
        if "input_not_in_bom" not in codes_wrong:
            bad("T12", "kain yang TIDAK ada di BOM tidak diperingatkan", str(codes_wrong))
        elif "bom_missing" not in codes_nobom or not nobom.get("other_sizes_with_bom"):
            bad("T12", "ukuran tanpa BOM tidak dikatakan jujur / tanpa jalan keluar",
                f"{codes_nobom} · size lain ber-BOM: {nobom.get('other_sizes_with_bom')}")
        else:
            ok("T12", "kejujuran dijaga: kain di luar BOM diperingatkan, ukuran tanpa BOM diarahkan",
               f"kain lain → {codes_wrong} · ukuran tanpa BOM → {codes_nobom} + "
               f"{len(nobom['other_sizes_with_bom'])} ukuran yang sudah punya BOM")

    finally:
        head("T13 — ALAT UKUR BERSIH (self-cleaning)")
        if KEEP:
            print(f"  {Y}--keep: artefak uji DIBIARKAN (model {ctx.get('model_id')}){X}")
        else:
            cleanup(db, ctx)
            stock1 = total_stock(db)
            left = (db.rahaza_materials.count_documents({"notes": MARK})
                    + db.rahaza_boms.count_documents({"model_id": ctx.get("model_id")})
                    + db.product_cost_snapshots.count_documents({"model_id": ctx.get("model_id")}))
            if abs(stock1 - stock0) > 0.001 or left:
                bad("T13", "artefak uji masih tertinggal",
                    f"stok {stock0:,.2f} → {stock1:,.2f} · dokumen sisa {left}")
            else:
                ok("T13", "semua artefak uji dihapus & stok kembali persis",
                   f"stok {stock1:,.2f} (sama seperti sebelum uji) · setelan costing dipulihkan")

    print(f"\n{B}HASIL: {G}{len(PASS)} PASS{X} · " +
          (f"{R}{len(FAIL)} FAIL{X}" if FAIL else f"{G}0 FAIL{X}"))
    if FAIL:
        print(f"{R}{B}GAGAL: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}POC HIJAU — inti HPP per potong & BOM di cutting TERBUKTI.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
