#!/usr/bin/env python3
"""verify_hpp_potong_dan_bom_cutting.py — GATE **INV-F36** (2026-08-23).

"HPP PER POTONG LAHIR DARI PEMBELIAN + BOM, DAN BOM MENGISI RENCANA CUTTING."

═══════════════════════════════════════════════════════════════════════════════
KEADAAN SEBELUM PERBAIKAN (terukur)
═══════════════════════════════════════════════════════════════════════════════
Sesi #30 membuat harga BAHAN lahir dari pembelian (rata-rata bergerak). Tetapi:
  · `rahaza_materials` type='fg' = **321 dokumen, semuanya `hpp: 0`,
    `hpp_source: 'none'`** ⇒ HPP produk jadi belum pernah lahir.
  · `core/product_master.resolve_hpp` hanya tahu `hpp_rnd` (kalkulator R&D) dan
    `base_hpp` (**KETIKAN MANUAL**) ⇒ bertabrakan dengan keputusan pemilik
    "harga jangan dari ketikan master".
  · Kolom HPP & margin di Katalog Marketing ada tetapi selalu 0 / "belum ada".
  · `planned_input_qty` (rencana pemakaian kain) pada Order Cutting diketik
    MANUAL walau BOM per model+size sudah menyimpan kebutuhan per pcs.

INVARIAN YANG DIJAGA
--------------------
  C1  Biaya bahan/pcs = Σ(BOM qty satuan dasar × unit_cost) — SADAR SATUAN
      (150 cm = 1,5 m; 0,5 lusin = 6 pcs), harga HANYA dari master hasil pembelian
  C2  Bahan tanpa harga TIDAK dihitung 0 diam-diam: jadi `gaps.material_unvalued`
      + baris ditandai `unvalued` + `computable=false`
  C3  Upah cutting/internal punya rantai sumber yang DILAPORKAN; proses jahit/CMT
      tidak pernah dihitung dua kali
  C4  Upah CMT kosong = kekurangan (bukan 0 diam-diam) + kandidat tarif NYATA
  C5  Upah yang dikunci pemilik dipakai & sumbernya 'owner'
  C6  Overhead OPSIONAL: default MATI (keputusan pemilik), bisa dihidupkan
  C7  Margin & usulan harga jual benar (margin atas harga jual)
  C8  TERAPKAN menulis HPP ke master (`hpp_bom`) + FG per ukuran
      (`hpp_source='bom'`) + item katalog; idempoten; ada snapshot audit
  C9  `resolve_hpp` mendahulukan sumber 'bom' TANPA mengubah model yang belum
      punya `hpp_bom`
  C10 BOM mengisi rencana cutting: kebutuhan/pcs & total dalam satuan kain,
      aksesoris ikut, dan kain di luar BOM / ukuran tanpa BOM DIKATAKAN
  C11 LAYAR: menu "HPP per Potong" terdaftar + testid kunci ada; kartu BOM +
      tombol "Pakai angka BOM" ada di dialog Cutting
  C12 ALAT UKUR BERSIH: semua artefak uji hilang & total stok kembali persis

Pakai:  python3 scripts/verify_hpp_potong_dan_bom_cutting.py
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
G, R, C, B, X = "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list[str] = []
FAIL: list[str] = []
STAMP = time.strftime("F36%H%M%S")
MARK = f"gate INV-F36 {STAMP}"

FE_COST = ROOT / "frontend/src/components/erp/costing/ProductCostingModule.jsx"
FE_CUT = ROOT / "frontend/src/components/erp/cutting/CuttingOrdersModule.jsx"
FE_REG = ROOT / "frontend/src/components/erp/moduleRegistry.js"
FE_NAV = ROOT / "frontend/src/components/erp/portal-shell/portalNav.js"


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
            return e.code, {"raw": raw[:200].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d):
    return str((d or {}).get("detail") or (d or {}).get("error") or d)[:160]


def near(a, b, tol=0.51):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def rp(v):
    return f"Rp{float(v or 0):,.0f}".replace(",", ".")


def total_stock(db):
    row = list(db.rahaza_material_stock.aggregate([{"$group": {"_id": None, "t": {"$sum": "$qty"}}}]))
    return round(float(row[0]["t"]) if row else 0.0, 4)


def buy(token, ctx, key, material_id, qty, price, loc_id):
    """PO → approve → GR → terima (harga lahir dari pembelian)."""
    st, po = call("POST", "/api/rahaza/purchase-orders", token, {
        "vendor_name": f"Pemasok Gate {STAMP}", "notes": MARK,
        "items": [{"material_id": material_id, "qty_input": qty, "unit_cost_input": price}]})
    if st != 200 or not po.get("id"):
        return False, f"PO gagal HTTP {st} · {det(po)}"
    ctx[f"po{key}"] = po["id"]
    call("POST", f"/api/rahaza/purchase-orders/{po['id']}/submit", token, {"notes": MARK})
    for _ in range(4):
        st, r = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/approve", token, {"notes": MARK})
        if (r or {}).get("status") == "approved":
            break
    st, gr = call("POST", f"/api/rahaza/purchase-orders/{po['id']}/create-gr", token, {})
    if st != 200 or not gr.get("id"):
        return False, f"GR gagal HTTP {st} · {det(gr)}"
    ctx[f"gr{key}"] = gr["id"]
    ctx[f"grno{key}"] = gr.get("receipt_number")
    items = [{**it, "received_qty": qty, "rejected_qty": 0, "location_id": loc_id}
             for it in (gr.get("items") or [])]
    st, upd = call("PUT", f"/api/warehouse/receiving/{gr['id']}", token,
                   {"status": "received", "items": items, "location_id": loc_id})
    if st != 200:
        return False, f"terima gagal HTTP {st} · {det(upd)}"
    return True, ""


def cleanup(db, ctx):
    mids = [m for m in (ctx.get("fabric"), ctx.get("acc"), ctx.get("label"), ctx.get("other")) if m]
    model_id = ctx.get("model")
    fg_ids = [f["id"] for f in db.rahaza_materials.find({"model_id": model_id}, {"_id": 0, "id": 1})] \
        if model_id else []
    allm = mids + fg_ids
    grnos = [ctx.get(f"grno{k}") for k in ("1", "2") if ctx.get(f"grno{k}")]
    for coll, q in (
        ("marketing_catalog_items", {"id": {"$in": [i for i in [ctx.get("item")] if i]}}),
        ("product_cost_snapshots", {"model_id": model_id}),
        ("rahaza_model_costing", {"model_id": model_id}),
        ("rahaza_boms", {"model_id": model_id}),
        ("rahaza_model_variants", {"model_id": model_id}),
        ("rahaza_stock_ledger", {"material_id": {"$in": allm}}),
        ("rahaza_material_stock", {"material_id": {"$in": allm}}),
        ("warehouse_movements", {"material_id": {"$in": allm}}),
        ("rahaza_material_movements", {"material_id": {"$in": allm}}),
        ("rahaza_material_cost_history", {"material_id": {"$in": allm}}),
        ("warehouse_receiving", {"id": {"$in": [ctx.get(f"gr{k}") for k in ("1", "2")
                                                if ctx.get(f"gr{k}")]}}),
        ("rahaza_purchase_orders", {"id": {"$in": [ctx.get(f"po{k}") for k in ("1", "2")
                                                   if ctx.get(f"po{k}")]}}),
        ("rahaza_journal_entries", {"reference": {"$in": grnos}}),
        ("journal_entries", {"reference": {"$in": grnos}}),
        ("rahaza_materials", {"id": {"$in": allm}}),
        ("rahaza_models", {"id": model_id}),
    ):
        try:
            db[coll].delete_many(q)
        except Exception:  # noqa: BLE001
            pass
    before = ctx.get("settings_before")
    try:
        if before:
            db.rahaza_costing_settings.replace_one({"id": "GLOBAL"}, before, upsert=True)
        elif before is not None:
            db.rahaza_costing_settings.delete_one({"id": "GLOBAL"})
    except Exception:  # noqa: BLE001
        pass


def main():  # noqa: C901
    print(f"{C}{B}INV-F36 — HPP PER POTONG DARI PEMBELIAN + BOM MENGISI RENCANA CUTTING{X}")
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    ctx: dict = {"settings_before": db.rahaza_costing_settings.find_one({"id": "GLOBAL"})}
    stock0 = total_stock(db)

    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2

    try:
        # ── C9 (statik + unit) — resolve_hpp mendahulukan 'bom' ─────────────
        head("C9 — sumber HPP model: 'bom' didahulukan, model lama tidak berubah")
        from core.product_master import resolve_hpp
        h_bom = resolve_hpp({"hpp_bom": 12345, "hpp_rnd": 999, "base_hpp": 111})
        h_rnd = resolve_hpp({"hpp_rnd": 999, "base_hpp": 111})
        h_man = resolve_hpp({"base_hpp": 111})
        h_non = resolve_hpp({})
        if h_bom != (12345.0, "bom") or h_rnd != (999.0, "rnd") or h_man != (111.0, "manual") \
                or h_non != (0.0, "none"):
            bad("C9", "urutan sumber HPP salah", f"{h_bom} {h_rnd} {h_man} {h_non}")
        else:
            ok("C9", "urutan sumber HPP: bom → rnd → manual → none (tanpa mengubah data lama)",
               f"{h_bom[1]}/{h_rnd[1]}/{h_man[1]}/{h_non[1]}")

        # ── siapkan alur nyata ─────────────────────────────────────────────
        head("C1/C2 — biaya bahan/pcs sadar satuan, harga hanya dari pembelian")
        st, locs = call("GET", "/api/warehouse/locations", token)
        locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
        loc = next((x for x in locs if x.get("id")), {})
        if not loc:
            bad("C1", "tidak ada lokasi gudang")
            return 1

        for key, payload in (
            ("fabric", {"code": f"GF36-KAIN-{STAMP}", "name": f"Kain Gate F36 {STAMP}",
                        "type": "fabric", "unit": "m"}),
            ("acc", {"code": f"GF36-KANCING-{STAMP}", "name": f"Kancing Gate {STAMP}",
                     "type": "accessory", "unit": "pcs"}),
            ("label", {"code": f"GF36-LABEL-{STAMP}", "name": f"Label Gate {STAMP}",
                       "type": "accessory", "unit": "pcs"}),
            ("other", {"code": f"GF36-KAIN2-{STAMP}", "name": f"Kain Lain Gate {STAMP}",
                       "type": "fabric", "unit": "m"}),
        ):
            st, m = call("POST", "/api/rahaza/materials", token, {**payload, "notes": MARK})
            if st != 200 or not m.get("id"):
                bad("C1", f"gagal menyiapkan material {payload['code']}", det(m))
                return 1
            ctx[key] = m["id"]

        for key, mid, qty, price in (("1", ctx["fabric"], 100, 25000), ("2", ctx["acc"], 120, 500)):
            okk, err = buy(token, ctx, key, mid, qty, price, loc.get("id"))
            if not okk:
                bad("C1", "pembelian bahan gagal", err)
                return 1

        st, model = call("POST", "/api/rahaza/models", token, {
            "code": f"MDL-F36-{STAMP}", "name": f"Model Gate F36 {STAMP}", "description": MARK})
        ctx["model"] = model.get("id")
        st, sizes = call("GET", "/api/rahaza/sizes", token)
        sizes = sizes if isinstance(sizes, list) else (sizes or {}).get("items") or []
        size_m = next((s for s in sizes if (s.get("code") or "").upper() == "M"), None) or sizes[0]
        size_l = next((s for s in sizes if (s.get("code") or "").upper() == "L"), None)
        st, colors = call("GET", "/api/rahaza/colors", token)
        colors = colors if isinstance(colors, list) else (colors or {}).get("items") or []
        st, variant = call("POST", "/api/rahaza/variants", token, {
            "model_id": ctx["model"], "size_id": size_m["id"], "color_id": colors[0]["id"],
            "notes": MARK})
        ctx["variant"] = variant.get("id")
        if size_l:
            call("POST", "/api/rahaza/variants", token, {
                "model_id": ctx["model"], "size_id": size_l["id"], "color_id": colors[0]["id"],
                "notes": MARK})
        st, bom = call("POST", "/api/rahaza/boms", token, {
            "model_id": ctx["model"], "size_id": size_m["id"], "notes": MARK,
            "materials": [
                {"material_id": ctx["fabric"], "code": f"GF36-KAIN-{STAMP}",
                 "name": "Kain", "material_type": "fabric", "qty": 150, "unit": "cm"},
                {"material_id": ctx["acc"], "code": f"GF36-KANCING-{STAMP}",
                 "name": "Kancing", "material_type": "accessory", "qty": 0.5, "unit": "lusin"},
                {"material_id": ctx["label"], "code": f"GF36-LABEL-{STAMP}",
                 "name": "Label", "material_type": "accessory", "qty": 1, "unit": "pcs"},
            ]})
        if st != 200 or not bom.get("id"):
            bad("C1", "gagal membuat BOM uji", det(bom))
            return 1

        call("PUT", "/api/costing/settings", token, {
            "include_overhead_in_product_hpp": False, "target_margin_pct": 40,
            "overhead_rate_per_pcs": 1000, "process_rates": []})
        st, cost = call("GET", f"/api/costing/models/{ctx['model']}", token)
        if st != 200:
            bad("C1", "endpoint HPP model gagal", f"HTTP {st} · {det(cost)}")
            return 1
        row = next((s for s in cost["sizes"] if s["size_id"] == size_m["id"]), {})
        if not near(row.get("material_cost"), 40500):
            bad("C1", "biaya bahan/pcs salah (satuan tidak dikonversi?)",
                f"{row.get('material_cost')} ≠ 40.500")
        else:
            ok("C1", "biaya bahan/pcs = BOM(satuan dasar) × harga pembelian",
               f"150 cm→1,5 m × {rp(25000)} + 0,5 lusin→6 pcs × {rp(500)} = "
               f"{rp(row['material_cost'])}")

        codes = [g["code"] for g in cost["gaps"]]
        lab = next((ln for ln in row.get("lines", []) if ln["material_id"] == ctx["label"]), {})
        if "material_unvalued" not in codes or lab.get("status") != "unvalued" \
                or row.get("computable") is not False:
            bad("C2", "bahan tanpa harga tidak dilaporkan jujur",
                f"gaps={codes} status={lab.get('status')} computable={row.get('computable')}")
        else:
            ok("C2", "bahan tanpa harga = kekurangan yang bisa ditindak (bukan 0 diam-diam)",
               f"{lab.get('code')} status={lab['status']} · gaps={codes}")

        # ── C3/C4 — upah ───────────────────────────────────────────────────
        head("C3/C4 — upah internal dari tarif proses (jahit/CMT tidak dobel) & CMT jujur")
        st, procs = call("GET", "/api/costing/processes", token)
        pm = {(p["code"] or "").upper(): p for p in (procs or {}).get("items", [])}
        rates = [{"process_id": pm[c]["process_id"], "code": c, "name": pm[c]["name"],
                  "rate_per_pcs": v} for c, v in (("CUTTING", 700), ("FINISHING", 300)) if c in pm]
        if "SEWING" in pm:
            rates.append({"process_id": pm["SEWING"]["process_id"], "code": "SEWING",
                          "name": "Jahit", "rate_per_pcs": 9999})
        call("PUT", "/api/costing/settings", token, {"process_rates": rates})
        st, cost = call("GET", f"/api/costing/models/{ctx['model']}", token)
        lb = cost["internal_labor"]
        if not near(lb["rate"], 1000) or lb["source"] != "settings_process_rates":
            bad("C3", "upah internal salah / sumber tidak dilaporkan",
                f"{lb['rate']} ({lb['source']}) — harus 1.000 dari tarif proses non-CMT")
        else:
            ok("C3", "upah internal = Σ tarif proses non-CMT; proses jahit dikecualikan",
               f"{rp(lb['rate'])}/pcs dari {len(lb['processes'])} proses (SEWING 9.999 diabaikan)")

        if "cmt_rate_missing" not in [g["code"] for g in cost["gaps"]] \
                or not cost["cmt"]["candidates"]:
            bad("C4", "upah CMT kosong tidak dilaporkan / tanpa kandidat nyata",
                f"gaps={[g['code'] for g in cost['gaps']]} kandidat={len(cost['cmt']['candidates'])}")
        else:
            ok("C4", "upah CMT kosong = kekurangan + kandidat tarif NYATA ditawarkan",
               f"{len(cost['cmt']['candidates'])} kandidat (partner/job CMT)")

        # ── C5/C6/C7 ───────────────────────────────────────────────────────
        head("C5/C6/C7 — upah dikunci, overhead opsional, margin & usulan harga")
        call("PUT", f"/api/costing/models/{ctx['model']}/labor", token,
             {"cmt_rate_per_pcs": 8500, "internal_labor_per_pcs": 1500, "notes": MARK})
        st, cost = call("GET", f"/api/costing/models/{ctx['model']}", token)
        row = next((s for s in cost["sizes"] if s["size_id"] == size_m["id"]), {})
        if not near(row.get("hpp_unit"), 50500) or cost["cmt"]["source"] != "owner":
            bad("C5", "HPP/pcs atau sumber upah salah setelah dikunci",
                f"hpp={row.get('hpp_unit')} sumber={cost['cmt']['source']}")
        else:
            ok("C5", "HPP/pcs = bahan + upah CMT + upah cutting/internal (sumber 'dikunci pemilik')",
               f"{rp(row['material_cost'])}+{rp(row['cmt_cost'])}+"
               f"{rp(row['internal_labor_cost'])} = {rp(row['hpp_unit'])}")

        st, cost_oh = call("GET", f"/api/costing/models/{ctx['model']}?include_overhead=1", token)
        row_oh = next((s for s in cost_oh["sizes"] if s["size_id"] == size_m["id"]), {})
        if row.get("overhead_cost") != 0 or not near(row_oh.get("hpp_unit"), 51500):
            bad("C6", "saklar overhead tidak sesuai keputusan pemilik (default MATI)",
                f"mati={row.get('overhead_cost')} hidup={row_oh.get('hpp_unit')}")
        else:
            ok("C6", "overhead opsional: default mati, bisa dihidupkan per permintaan",
               f"{rp(row['hpp_unit'])} → {rp(row_oh['hpp_unit'])}")

        fg = db.rahaza_materials.find_one(
            {"type": "fg", "model_id": ctx["model"], "size_id": size_m["id"]}, {"_id": 0})
        cat = db.marketing_catalogs.find_one({}, {"_id": 0, "id": 1})
        st, item = call("POST", f"/api/marketing/catalogs/{cat['id']}/items/from-fg", token,
                        {"fg_material_id": (fg or {}).get("id"), "price": 100000,
                         "platform_price": 100000})
        item_doc = (item or {}).get("item") if isinstance((item or {}).get("item"), dict) else item
        ctx["item"] = (item_doc or {}).get("id")
        st, cost2 = call("GET", f"/api/costing/models/{ctx['model']}", token)
        row2 = next((s for s in cost2["sizes"] if s["size_id"] == size_m["id"]), {})
        exp_sug = round(50500 / 0.6, 2)
        if not (near(row2.get("margin"), 49500) and near(row2.get("margin_pct"), 49.5, 0.1)
                and near(row2.get("suggested_price"), exp_sug, 1.0)):
            bad("C7", "margin / usulan harga jual salah",
                f"margin={row2.get('margin')} pct={row2.get('margin_pct')} "
                f"usul={row2.get('suggested_price')} (harus 49.500 / 49,5% / {exp_sug})")
        else:
            ok("C7", "margin & usulan harga jual benar (margin atas harga jual)",
               f"harga {rp(row2['price']['best_price'])} − HPP {rp(row2['hpp_unit'])} = "
               f"{rp(row2['margin'])} ({row2['margin_pct']}%) · target "
               f"{cost2['target_margin_pct']}% ⇒ usul {rp(row2['suggested_price'])}")

        # ── C8 — terapkan ──────────────────────────────────────────────────
        head("C8 — terapkan HPP: master + FG per ukuran + item katalog (idempoten)")
        st, ap = call("POST", f"/api/costing/models/{ctx['model']}/apply", token, {})
        st2, ap2 = call("POST", f"/api/costing/models/{ctx['model']}/apply", token, {})
        fg2 = db.rahaza_materials.find_one({"id": (fg or {}).get("id")}, {"_id": 0}) or {}
        md = db.rahaza_models.find_one({"id": ctx["model"]}, {"_id": 0}) or {}
        it = db.marketing_catalog_items.find_one({"id": ctx.get("item")}, {"_id": 0}) or {}
        snaps = db.product_cost_snapshots.count_documents({"model_id": ctx["model"]})
        if st != 200 or not near(fg2.get("hpp"), 50500) or fg2.get("hpp_source") != "bom":
            bad("C8", "HPP tidak tertulis ke FG per ukuran",
                f"HTTP {st} hpp={fg2.get('hpp')} src={fg2.get('hpp_source')}")
        elif not near(md.get("hpp_bom"), 50500) or md.get("hpp_source") != "bom":
            bad("C8", "HPP tidak tertulis ke master produk",
                f"hpp_bom={md.get('hpp_bom')} src={md.get('hpp_source')}")
        elif not near(it.get("hpp"), 50500) or it.get("hpp_source") != "bom":
            bad("C8", "margin item katalog Marketing tidak hidup",
                f"hpp={it.get('hpp')} src={it.get('hpp_source')}")
        elif st2 != 200 or snaps < 2:
            bad("C8", "penerapan kedua tidak idempoten / snapshot audit kurang",
                f"HTTP {st2} snapshot={snaps}")
        else:
            ok("C8", "HPP terpasang di master + FG per ukuran + item katalog, idempoten & terekam",
               f"FG {rp(fg2['hpp'])} · master {rp(md['hpp_bom'])} · item katalog {rp(it['hpp'])} · "
               f"{snaps} snapshot · ukuran tanpa BOM dilewati {len(ap.get('skipped') or [])}")

        # ── C10 — BOM mengisi rencana cutting ──────────────────────────────
        head("C10 — BOM mengisi rencana pemakaian kain di Order Cutting")
        st, req = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model']}"
                               f"&size_id={size_m['id']}&qty_pcs=100"
                               f"&input_material_id={ctx['fabric']}"), token)
        fb = (req or {}).get("fabric") or {}
        st, wrong = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model']}"
                                 f"&size_id={size_m['id']}&qty_pcs=10"
                                 f"&input_material_id={ctx['other']}"), token)
        nb_size = (size_l or {}).get("id") or "00000000-0000-0000-0000-000000000000"
        st, nobom = call("GET", (f"/api/cutting/bom-requirement?model_id={ctx['model']}"
                                 f"&size_id={nb_size}&qty_pcs=10"), token)
        if not (near(fb.get("qty_per_pcs"), 1.5, 0.001) and near(fb.get("qty_total"), 150, 0.01)
                and fb.get("unit") == "m" and len(req.get("accessories") or []) == 2):
            bad("C10", "kebutuhan kain/aksesoris dari BOM salah",
                f"per pcs={fb.get('qty_per_pcs')} total={fb.get('qty_total')} "
                f"satuan={fb.get('unit')} aksesoris={len(req.get('accessories') or [])}")
        elif "input_not_in_bom" not in [g["code"] for g in (wrong or {}).get("gaps", [])]:
            bad("C10", "kain di luar BOM tidak diperingatkan",
                str([g["code"] for g in (wrong or {}).get("gaps", [])]))
        elif "bom_missing" not in [g["code"] for g in (nobom or {}).get("gaps", [])] \
                or not nobom.get("other_sizes_with_bom"):
            bad("C10", "ukuran tanpa BOM tidak dikatakan / tanpa jalan keluar",
                f"{[g['code'] for g in (nobom or {}).get('gaps', [])]}")
        else:
            ok("C10", "kebutuhan kain & aksesoris dari BOM + kejujuran saat tidak cocok",
               f"1,5 m/pcs × 100 = {fb['qty_total']} m · kain lain → input_not_in_bom · "
               f"ukuran tanpa BOM → bom_missing + {len(nobom['other_sizes_with_bom'])} ukuran ber-BOM")

        # ── C11 — layar ────────────────────────────────────────────────────
        head("C11 — layar: menu HPP per Potong & kartu BOM di dialog Cutting")
        fe_cost = FE_COST.read_text(encoding="utf-8") if FE_COST.exists() else ""
        fe_cut = FE_CUT.read_text(encoding="utf-8") if FE_CUT.exists() else ""
        reg = FE_REG.read_text(encoding="utf-8") if FE_REG.exists() else ""
        nav = FE_NAV.read_text(encoding="utf-8") if FE_NAV.exists() else ""
        need_cost = ["product-costing-page", "costing-apply-all", "costing-table",
                     "costing-target-margin", "costing-toggle-overhead", "costing-gaps",
                     "costing-input-cmt", "costing-input-internal", "costing-save-labor"]
        need_cut = ["cutting-bom-card", "cutting-use-bom-qty", "cutting-bom-accessories"]
        miss = [k for k in need_cost if k not in fe_cost] + [k for k in need_cut if k not in fe_cut]
        if miss:
            bad("C11", "elemen layar wajib belum ada", f"hilang={miss}")
        elif "'fin-hpp-produk'" not in reg or "fin-hpp-produk" not in nav:
            bad("C11", "layar HPP per Potong belum terdaftar di menu",
                f"registry={'fin-hpp-produk' in reg} nav={'fin-hpp-produk' in nav}")
        else:
            ok("C11", "layar terdaftar & elemen kuncinya ada",
               f"{len(need_cost)} testid HPP + {len(need_cut)} testid kartu BOM · menu "
               f"'fin-hpp-produk' terdaftar")

    finally:
        head("C12 — ALAT UKUR BERSIH")
        cleanup(db, ctx)
        stock1 = total_stock(db)
        left = (db.rahaza_materials.count_documents({"notes": MARK})
                + db.rahaza_boms.count_documents({"model_id": ctx.get("model")})
                + db.product_cost_snapshots.count_documents({"model_id": ctx.get("model")})
                + db.marketing_catalog_items.count_documents({"id": ctx.get("item") or "-"}))
        if abs(stock1 - stock0) > 0.001 or left:
            bad("C12", "artefak uji tertinggal", f"stok {stock0} → {stock1} · sisa {left}")
        else:
            ok("C12", "artefak uji terhapus & stok kembali persis",
               f"stok {stock1:,.2f} · setelan costing dipulihkan")

    print(f"\n{B}INV-F36: {G}{len(PASS)} PASS{X} · " +
          (f"{R}{len(FAIL)} FAIL{X}" if FAIL else f"{G}0 FAIL{X}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
