#!/usr/bin/env python3
"""verify_potongan_nilai_dan_yatim.py — GATE **INV-F37** (2026-08-23, sesi #32).

MENJAGA DUA CACAT YANG DILAPORKAN PEMILIK AGAR TIDAK KEMBALI
------------------------------------------------------------
(1) **Nilai potongan.** Nilai kain yang KELUAR harus berpindah menjadi nilai
    POTONGAN yang MASUK, **saat progres dilaporkan**, memakai harga kain SAAT ITU
    dan **rata-rata bergerak** (SSOT `core.accessory_valuation`) — bukan menunggu
    `complete` lalu MENIMPA dengan harga yang di-snapshot saat order dibuat.
(2) **Potongan yatim.** Master POTONGAN dibuat otomatis oleh `start`. Ia tidak
    boleh tertinggal tanpa induk — baik karena alur produk (`cancel`/`delete`)
    maupun karena ALAT UKUR sendiri (gate INV-F24 dulu menghapus order + kain +
    dokumen tetapi meninggalkan masternya karena mencocokkan REGEX KODE).

INVARIAN (12)
-------------
  C1  statik: `add_progress` memanggil `cut_panel_value.apply_progress_value`
  C2  statik: `complete` memakai Σ nilai progres (`order_value_totals`) dan TIDAK
      menimpa master tanpa syarat
  C3  statik: `cancel` & `delete` memanggil penjaga `remove_if_unused`
  C4  statik: LAYAR Master Potongan punya kolom nilai + kartu yatim + tombol bersihkan
  C5  runtime: progres #1 ⇒ HPP potongan = nilai kain keluar / pcs
  C6  runtime: progres #2 (harga kain berubah) ⇒ RATA-RATA BERGERAK, bukan ditimpa
  C7  runtime: kekekalan nilai — Σ nilai kain keluar == nilai stok potongan
  C8  runtime: kain belum bernilai ⇒ potongan `unvalued` + alasan dikatakan
  C9  runtime: `cancel` membuang master potongan yang belum pernah bergerak
  C10 runtime: potongan yatim TERDETEKSI + bisa dibersihkan + IDEMPOTEN
  C11 runtime: potongan yatim yang MASIH BERSTOK tidak dihapus (stok tak jadi hantu)
  C12 KEADAAN AKHIR: **tidak ada potongan yatim tertinggal di database** — ini
      penjaga terhadap alat ukur yang bocor (dijalankan SESUDAH bersih-bersih,
      persis pola C14 INV-F24).

Pakai:  python3 scripts/verify_potongan_nilai_dan_yatim.py
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
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

STAMP = time.strftime("%H%M%S")
MARK = f"GATE F37 {STAMP}"
CUTTING_ROUTE = ROOT / "backend/routes/cutting.py"
VALUE_CORE = ROOT / "backend/core/cut_panel_value.py"
HEALTH_CORE = ROOT / "backend/core/cut_panel_health.py"
FE_PANELS = ROOT / "frontend/src/components/erp/cutting/CuttingPanelsModule.jsx"

PASS: list[str] = []
FAIL: list[str] = []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


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


# ═══════════════════════ BAGIAN 1 — STATIK (murah) ═══════════════════════════
def part_static():
    print(f"\n{B}[1] STATIK — nilai lahir per progres · penjaga yatim · layar{X}")
    src = CUTTING_ROUTE.read_text(encoding="utf-8")

    i_add = src.find("async def add_progress")
    i_complete = src.find("async def complete_order")
    i_cancel = src.find("async def cancel_order")
    body_add = src[i_add:i_complete] if i_add != -1 < i_complete else ""
    body_complete = src[i_complete:i_cancel] if i_complete != -1 < i_cancel else ""
    body_cancel = src[i_cancel:] if i_cancel != -1 else ""

    if ("cut_panel_value.apply_progress_value" in body_add
            and "panel_onhand" in body_add
            and body_add.find("panel_onhand") < body_add.find("stock_service.add")):
        ok("C1", "nilai potongan dihitung SAAT progres, stok potongan dibaca SEBELUM add",
           "core.cut_panel_value.apply_progress_value + panel_onhand mendahului stock_service.add")
    else:
        bad("C1", "progres cutting tidak memindahkan nilai kain ke potongan",
            "panggil cut_panel_value.apply_progress_value dan baca panel_onhand SEBELUM "
            "stock_service.add (kalau sesudah, rata-rata bergeraknya salah penyebut)")

    if ("order_value_totals" in body_complete
            and "panel_cost <= 0" in body_complete):
        ok("C2", "complete memakai Σ nilai progres & tidak menimpa HPP master tanpa syarat",
           "penimpaan hanya untuk order lama yang HPP masternya masih 0")
    else:
        bad("C2", "complete masih menghitung ulang dengan harga basi / menimpa master",
            "pakai cut_panel_value.order_value_totals; master hanya diisi bila unit_cost <= 0")

    if ("cut_panel_health.remove_if_unused" in body_cancel
            and src.count("cut_panel_health.remove_if_unused") >= 2):
        ok("C3", "cancel & delete order memanggil penjaga anti-potongan-yatim",
           f"{src.count('cut_panel_health.remove_if_unused')} pemanggilan remove_if_unused")
    else:
        bad("C3", "membatalkan/menghapus order masih bisa meninggalkan potongan yatim",
            "panggil cut_panel_health.remove_if_unused di cancel_order DAN delete_order")

    if not VALUE_CORE.exists() or not HEALTH_CORE.exists():
        bad("C4", "modul SSOT nilai/kesehatan potongan tidak ada")
        return
    fe = FE_PANELS.read_text(encoding="utf-8") if FE_PANELS.exists() else ""
    need = ["cutting-panels-orphan-card", "cutting-panels-cleanup-btn", "cutting-panels-value"]
    miss = [t for t in need if t not in fe]
    if not miss:
        ok("C4", "layar Master Potongan: kolom nilai + kartu yatim + tombol bersihkan",
           ", ".join(need))
    else:
        bad("C4", "layar Master Potongan belum punya pintu untuk fitur ini",
            f"data-testid hilang: {miss} di {FE_PANELS.name}")


# ═══════════════════════ BAGIAN 2 — RUNTIME (data nyata) ═════════════════════
def receive(token, mat, qty, price, loc, rolls):
    st, gr = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": f"Pemasok F37 {STAMP}",
        "location_id": loc.get("id"), "location_name": loc.get("name"), "notes": MARK,
        "items": [{
            "product_name": mat["name"], "sku": mat["code"], "material_id": mat["id"],
            "expected_qty": qty, "received_qty": qty, "rejected_qty": 0,
            "unit": mat.get("unit") or "m", "unit_price": price,
            "inspection_status": "passed", "lot_number": f"LOT-F37-{STAMP}",
            "rolls": rolls,
        }]})
    if st not in (200, 201) or not (gr or {}).get("id"):
        raise RuntimeError(f"GR gagal HTTP {st} · {det(gr)}")
    st, upd = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        raise RuntimeError(f"terima GR gagal HTTP {st} · {det(upd)}")
    return gr


def setup(db, token, ctx):
    st, locs = call("GET", "/api/warehouse/locations", token)
    locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
    loc = next((x for x in locs if x.get("id")), None)
    if not loc:
        raise RuntimeError("tidak ada lokasi gudang")
    ctx["loc"] = loc

    st, sizes = call("GET", "/api/rahaza/sizes", token)
    sizes = sizes if isinstance(sizes, list) else (sizes or {}).get("items") or []
    if len(sizes) < 3:
        raise RuntimeError("master ukuran kurang dari 3")
    ctx["sizes"] = sizes[:3]

    for key, code in (("mat_a", f"GF37-KAIN-A-{STAMP}"), ("mat_b", f"GF37-KAIN-B-{STAMP}")):
        st, m = call("POST", "/api/rahaza/materials", token, {
            "code": code, "name": f"Kain Gate F37 {code[-6:]}", "type": "fabric",
            "unit": "m", "color": "Navy", "notes": MARK})
        if st != 200 or not (m or {}).get("id"):
            raise RuntimeError(f"gagal membuat {code}: {det(m)}")
        ctx[key] = m

    ctx["gr_a"] = receive(token, ctx["mat_a"], 100, 20000, loc,
                          [{"qty": 100, "color_lot": f"LOT-{STAMP}", "notes": ""}])
    ctx["gr_b"] = receive(token, ctx["mat_b"], 40, 0, loc,
                          [{"qty": 40, "color_lot": f"LOT-{STAMP}", "notes": ""}])

    st, model = call("POST", "/api/rahaza/models", token, {
        "code": f"MDL-GF37-{STAMP}", "name": f"Potongan Gate F37 {STAMP}", "description": MARK})
    if st != 200 or not (model or {}).get("id"):
        raise RuntimeError(f"gagal membuat model: {det(model)}")
    ctx["model"] = model

    def rolls_of(mid):
        rows = list(db.wh_fabric_rolls.find({"material_id": mid}, {"_id": 0}))
        rows.sort(key=lambda d: str(d.get("roll_no", "")))
        return rows
    ctx["rolls_a"] = rolls_of(ctx["mat_a"]["id"])
    ctx["rolls_b"] = rolls_of(ctx["mat_b"]["id"])
    if not ctx["rolls_a"] or not ctx["rolls_b"]:
        raise RuntimeError("gulungan tidak terbit dari penerimaan")
    return ctx


def order_start(token, ctx, mat, size, pin, pout):
    st, o = call("POST", "/api/cutting/orders", token, {
        "input_material_id": mat["id"], "planned_input_qty": pin,
        "planned_output_qty": pout, "model_id": ctx["model"]["id"],
        "size_id": size["id"], "location_id": ctx["loc"].get("id"), "notes": MARK})
    if st not in (200, 201) or not (o or {}).get("id"):
        raise RuntimeError(f"order gagal HTTP {st} · {det(o)}")
    st, started = call("POST", f"/api/cutting/orders/{o['id']}/start", token)
    if st != 200:
        raise RuntimeError(f"start gagal HTTP {st} · {det(started)}")
    ctx.setdefault("orders", []).append(o["id"])
    return started


def part_runtime(db, token, ctx):
    print(f"\n{B}[2] RUNTIME — nilai berpindah, yatim terdeteksi & bisa dibersihkan{X}")
    size_a, size_b, size_c = ctx["sizes"]

    # C5 — progres #1: 5 m × 20.000 = 100.000 ⇒ 10 pcs @ 10.000
    o1 = order_start(token, ctx, ctx["mat_a"], size_a, 50, 100)
    panel_id = o1.get("output_material_id")
    st, p1 = call("POST", f"/api/cutting/orders/{o1['id']}/progress", token,
                  {"input_consumed": 5, "output_qty": 10,
                   "roll_ids": [ctx["rolls_a"][0]["id"]], "note": MARK})
    pm = db.rahaza_materials.find_one({"id": panel_id}, {"_id": 0}) or {}
    if st == 200 and near(pm.get("unit_cost"), 10000, 0.5):
        ok("C5", "HPP potongan lahir saat progres (nilai kain keluar / pcs jadi)",
           f"5 m × Rp20.000 = Rp100.000 ÷ 10 pcs = Rp{float(pm['unit_cost']):,.0f}/pcs")
    else:
        bad("C5", "nilai kain tidak berpindah saat progres",
            f"HTTP {st} · unit_cost potongan={pm.get('unit_cost')} · {det(p1)}")

    # C6 — harga kain naik jadi 40.000 utk 100 m berikutnya:
    #      WAC kain = (95×20.000 + 100×40.000)/195 = 30.256,4103
    #      progres #2: 5 m ⇒ 5 pcs ⇒ masuk 30.256,4103/pcs
    #      WAC potongan = (10×10.000 + 5×30.256,4103)/15 = 16.752,1368
    receive(token, ctx["mat_a"], 100, 40000, ctx["loc"],
            [{"qty": 100, "color_lot": f"LOT2-{STAMP}", "notes": ""}])
    ctx["rolls_a"] = list(db.wh_fabric_rolls.find({"material_id": ctx["mat_a"]["id"]}, {"_id": 0}))
    st, p2 = call("POST", f"/api/cutting/orders/{o1['id']}/progress", token,
                  {"input_consumed": 5, "output_qty": 5,
                   "roll_ids": [ctx["rolls_a"][0]["id"]], "note": MARK})
    pm2 = db.rahaza_materials.find_one({"id": panel_id}, {"_id": 0}) or {}
    if st == 200 and near(pm2.get("unit_cost"), 16752.14, 1.0):
        ok("C6", "HPP potongan = RATA-RATA BERGERAK (angka lama tidak ditimpa)",
           f"(10×10.000 + 5×30.256,41)/15 = Rp{float(pm2['unit_cost']):,.2f}/pcs")
    else:
        bad("C6", "HPP potongan ditimpa / salah hitung",
            f"HTTP {st} · unit_cost={pm2.get('unit_cost')} (harusnya ≈16.752,14) · {det(p2)}")

    # C7 — kekekalan nilai
    progs = list(db.cutting_progress.find({"cutting_order_id": o1["id"]}, {"_id": 0}))
    value_out = round(sum(float(p.get("value_out") or 0) for p in progs), 2)
    st, panels = call("GET", "/api/cutting/output-materials", token)
    prow = next((p for p in (panels if isinstance(panels, list) else [])
                 if p.get("id") == panel_id), {})
    stock_value = round(float(prow.get("stock_value") or 0), 2)
    if value_out > 0 and abs(value_out - stock_value) <= 1.0:
        ok("C7", "nilai kain yang keluar diterima SELURUHNYA oleh potongan",
           f"kain keluar Rp{value_out:,.2f} == nilai stok potongan Rp{stock_value:,.2f}")
    else:
        bad("C7", "nilai bocor antara kain dan potongan",
            f"kain keluar {value_out} vs stok potongan {stock_value}")

    # C8 — kain tanpa harga: jujur
    o2 = order_start(token, ctx, ctx["mat_b"], size_b, 20, 40)
    st, pb = call("POST", f"/api/cutting/orders/{o2['id']}/progress", token,
                  {"input_consumed": 4, "output_qty": 8,
                   "roll_ids": [ctx["rolls_b"][0]["id"]], "note": MARK})
    pbm = db.rahaza_materials.find_one({"id": o2.get("output_material_id")}, {"_id": 0}) or {}
    warn = str((pb or {}).get("value_warning") or "")
    if (st == 200 and pbm.get("value_status") == "unvalued"
            and "belum" in warn.lower() and "harga" in warn.lower()):
        ok("C8", "kain belum bernilai ⇒ potongan ditandai `unvalued` + jalan keluarnya disebut",
           warn[:150])
    else:
        bad("C8", "kekurangan harga kain tidak dikatakan (0 dianggap benar)",
            f"HTTP {st} · status={pbm.get('value_status')} · pesan={warn[:150]}")

    # C9 — cancel membuang potongan yang belum pernah bergerak
    o3 = order_start(token, ctx, ctx["mat_b"], size_c, 10, 20)
    panel_c = o3.get("output_material_id")
    st, canc = call("POST", f"/api/cutting/orders/{o3['id']}/cancel", token, {"reason": MARK})
    left = db.rahaza_materials.find_one({"id": panel_c}, {"_id": 0})
    if st == 200 and left is None:
        ok("C9", "membatalkan order membuang master potongan yang belum pernah dipakai",
           str((canc or {}).get("notice"))[:140])
    else:
        bad("C9", "cancel meninggalkan master potongan yatim",
            f"HTTP {st} · masih ada={bool(left)}")

    # C10 — deteksi + pembersih idempoten (meniru alat ukur yang menghapus order)
    # size_c dipakai ulang DENGAN SENGAJA: potongannya sudah dibuang oleh C9,
    # jadi `start` di bawah melahirkan master BARU dengan kode yang sama —
    # sekaligus membuktikan pembersihan C9 benar-benar tuntas.
    o4 = order_start(token, ctx, ctx["mat_b"], size_c, 10, 20)
    panel_d = o4.get("output_material_id")
    if panel_d in (o1.get("output_material_id"), o2.get("output_material_id")):
        panel_d = None
    db.cutting_orders.delete_one({"id": o4["id"]})
    st, health = call("GET", "/api/cutting/panels/health", token)
    rows = (health or {}).get("items") or []
    if panel_d:
        hit = next((r for r in rows if r.get("id") == panel_d), None)
        if hit and "order_missing" in (hit.get("reasons") or []) and hit.get("cleanable"):
            st, res = call("POST", "/api/cutting/panels/cleanup", token, {"ids": [panel_d]})
            gone = db.rahaza_materials.find_one({"id": panel_d}, {"_id": 0}) is None
            st2, res2 = call("POST", "/api/cutting/panels/cleanup", token, {"ids": [panel_d]})
            if st == 200 and gone and int((res2 or {}).get("removed") or 0) == 0:
                ok("C10", "potongan yatim terdeteksi, dibersihkan, dan idempoten",
                   f"alasan={hit.get('reasons')} · dibersihkan={(res or {}).get('removed')}")
            else:
                bad("C10", "pembersihan tidak tuntas / tidak idempoten",
                    f"HTTP {st} gone={gone} ulang={(res2 or {}).get('removed')}")
        else:
            bad("C10", "potongan yatim tidak terdeteksi / salah kelayakan",
                json.dumps(hit or {})[:220])
    else:
        bad("C10", "master potongan dipakai ulang — uji yatim tidak bisa dijalankan",
            "ukuran uji harus berbeda supaya kode potongannya berbeda")

    # C11 — yatim berstok TIDAK dihapus
    db.rahaza_materials.delete_one({"id": ctx["mat_a"]["id"]})
    st, health = call("GET", "/api/cutting/panels/health", token)
    hit = next((r for r in ((health or {}).get("items") or []) if r.get("id") == panel_id), None)
    if hit and "source_missing" in (hit.get("reasons") or []) and not hit.get("cleanable"):
        st, res = call("POST", "/api/cutting/panels/cleanup", token, {"ids": [panel_id]})
        still = db.rahaza_materials.find_one({"id": panel_id}, {"_id": 0}) is not None
        if still and int((res or {}).get("removed") or 0) == 0:
            ok("C11", "yatim yang masih berstok DIPERTAHANKAN + alasannya disebut",
               f"stok {hit.get('stock_qty')} · {str(hit.get('block_reason'))[:110]}")
        else:
            bad("C11", "potongan berstok ikut dihapus ⇒ stok jadi hantu",
                f"masih ada={still} · {det(res)}")
    else:
        bad("C11", "kain sumber hilang tidak terdeteksi / kelayakan salah",
            json.dumps(hit or {})[:220])


def cleanup(db, ctx):
    orders = ctx.get("orders") or []
    mats = [ctx[k]["id"] for k in ("mat_a", "mat_b") if isinstance(ctx.get(k), dict)]
    panels = [m["id"] for m in db.rahaza_materials.find(
        {"$or": [{"cutting_order_id": {"$in": orders}},
                 {"source_material_id": {"$in": mats}},
                 {"code": {"$regex": f"^CUT-POTONGAN-GATE-F37-{STAMP}", "$options": "i"}}]},
        {"_id": 0, "id": 1})]
    # jaring terakhir: master potongan milik MODEL uji ini (kode diturunkan dari nama model)
    model_name = ((ctx.get("model") or {}).get("name") or "").upper().replace(" ", "-")
    if model_name:
        panels += [m["id"] for m in db.rahaza_materials.find(
            {"is_cut_panel": True, "code": {"$regex": f"^CUT-{model_name}", "$options": "i"}},
            {"_id": 0, "id": 1})]
    all_mats = list({*mats, *panels})
    grs = [(ctx.get(k) or {}).get("id") for k in ("gr_a", "gr_b") if ctx.get(k)]
    rolls = [r["id"] for r in db.wh_fabric_rolls.find(
        {"material_id": {"$in": mats}}, {"_id": 0, "id": 1})]
    mis = [m["id"] for m in db.rahaza_material_issues.find(
        {"cutting_order_id": {"$in": orders}}, {"_id": 0, "id": 1})]
    counts = {}
    for name, coll, q in (
        ("MI", "rahaza_material_issues", {"cutting_order_id": {"$in": orders}}),
        ("kartu", "rahaza_material_movements", {"$or": [{"ref_id": {"$in": mis}},
                                                        {"material_id": {"$in": all_mats}}]}),
        ("wh_mv", "warehouse_movements", {"material_id": {"$in": all_mats}}),
        ("progres", "cutting_progress", {"cutting_order_id": {"$in": orders}}),
        ("order", "cutting_orders", {"id": {"$in": orders}}),
        ("roll_mv", "wh_fabric_roll_movements", {"roll_id": {"$in": rolls}}),
        ("roll", "wh_fabric_rolls", {"id": {"$in": rolls}}),
        ("GR", "warehouse_receiving", {"id": {"$in": grs}}),
        ("stok", "rahaza_material_stock", {"material_id": {"$in": all_mats}}),
        ("ledger", "rahaza_stock_ledger", {"material_id": {"$in": all_mats}}),
        ("harga", "rahaza_material_cost_history", {"material_id": {"$in": all_mats}}),
        ("master", "rahaza_materials", {"id": {"$in": all_mats}}),
        ("model", "rahaza_models", {"id": (ctx.get("model") or {}).get("id")}),
    ):
        try:
            counts[name] = db[coll].delete_many(q).deleted_count
        except Exception:  # noqa: BLE001
            counts[name] = -1
    print(f"\n{Y}  bersih-bersih: " + " · ".join(f"{k}={v}" for k, v in counts.items()) + X)


def part_no_orphan(db):
    """C12 — KEADAAN AKHIR: tidak boleh ada potongan yatim tertinggal.

    Dijalankan SESUDAH bersih-bersih karena justru kebocoran ALAT UKUR yang
    paling mungkin lolos (INV-F24 dulu meninggalkan satu master potongan tiap
    kali dijalankan).
    """
    print(f"\n{B}[3] KEADAAN AKHIR — tidak ada potongan yatim tertinggal{X}")
    left = []
    for p in db.rahaza_materials.find({"is_cut_panel": True}, {"_id": 0}):
        pid = p["id"]
        src_id = (p.get("source_material_id") or "").strip()
        src_gone = bool(src_id) and db.rahaza_materials.count_documents({"id": src_id}) == 0
        order_id = (p.get("cutting_order_id") or "").strip()
        maker = bool(order_id) and db.cutting_orders.count_documents({"id": order_id}) > 0
        no_order = db.cutting_orders.count_documents({"output_material_id": pid}) == 0 and not maker
        if src_gone or no_order:
            left.append(f"{p.get('code')} ("
                        + ", ".join(x for x in ["kain sumber hilang" if src_gone else "",
                                                "order hilang" if no_order else ""] if x)
                        + ")")
    if not left:
        ok("C12", "0 potongan yatim di database sesudah seluruh uji dijalankan")
    else:
        bad("C12", f"{len(left)} potongan yatim tertinggal — alat ukur/alur membocorkan master",
            "; ".join(left[:6]) + (" …" if len(left) > 6 else "")
            + "\n         Bersihkan: POST /api/cutting/panels/cleanup "
              "(atau layar Cutting → Master Potongan → Bersihkan)")


def main():
    print(f"{C}{B}INV-F37 — NILAI POTONGAN LAHIR SAAT DIPOTONG & TIDAK ADA POTONGAN YATIM{X}")
    db = db_handle()
    part_static()
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token") if isinstance(d, dict) else None
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    ctx: dict = {}
    try:
        setup(db, token, ctx)
        part_runtime(db, token, ctx)
    except Exception as e:  # noqa: BLE001
        bad("SETUP", "penyiapan/uji runtime gagal", str(e)[:300])
    finally:
        cleanup(db, ctx)
    part_no_orphan(db)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian nilai & kesehatan potongan terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
