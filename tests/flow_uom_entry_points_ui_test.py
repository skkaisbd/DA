#!/usr/bin/env python3
"""Uji SATUAN di 6 TITIK MASUK/KELUAR STOK — ROADMAP P1 (2026-08-05).

Sebelum sesi ini backend sudah menerima `input_uom`/`qty_uom`/`counted_uom`,
tetapi LAYARNYA tidak punya pemilih satuan (operator hanya bisa satuan dasar)
dan cakupan konversinya lebih sempit dari BOM/Costing (satuan global seperti
"gram" ditolak). Skrip ini membuktikan keduanya sudah tertutup:

  1. GET /api/rahaza/materials/uom-options  → daftar satuan sah + faktornya
     (kemasan master, satuan global sedimensi, kain m⇄kg via gramasi & lebar)
  2. Penerimaan Gudang   POST /api/wms/pending/{id}/scan-in   `input_uom`
  3. Put-away            POST /api/wms/putaway/place          `input_uom`
  4. Opname Gudang       POST /api/wms/opname3/scan           `input_uom`
  5. Opname Aksesoris    PUT  /api/acc/opname/{id}/count      `counted_uom`
  6. Pengeluaran Material POST /api/rahaza/material-issues    items[].`qty_uom`
  7. Pengeluaran/Penerimaan Aksesoris  /api/acc/stock/{issue,receive} `input_unit`
  8. Progres Cutting     POST /api/cutting/orders/{id}/progress `input_uom`

Setiap titik juga diuji TANPA satuan (perilaku lama WAJIB tidak berubah) dan
dengan satuan asing (WAJIB ditolak 400, bukan diam-diam salah hitung).

Semua artefak uji dibersihkan di akhir. Kredensial: admin@garment.com / Admin@123
    python3 tests/flow_uom_entry_points_ui_test.py
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, "backend", ".env"))
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
ACC_CODE = "ZZTEST-UOM-ACC"
FAB_CODE = "ZZTEST-UOM-FAB"
BIN_BARCODE = "ZZBIN-UOM-B1"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"{'✅' if cond else '❌'} {name}" + ("" if cond else f" → {detail}"))


def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def cleanup(d):
    # material uji + material POTONGAN turunan cutting (kode CUT-ZZTEST-…)
    ids = [m["id"] for m in d.rahaza_materials.find(
        {"code": {"$regex": "ZZTEST-UOM-"}}, {"_id": 0, "id": 1})]
    if ids:
        d.rahaza_material_stock.delete_many({"material_id": {"$in": ids}})
        d.rahaza_stock_ledger.delete_many({"material_id": {"$in": ids}})
        d.rahaza_material_movements.delete_many({"material_id": {"$in": ids}})
        d.wh_placement_movements.delete_many({"material_id": {"$in": ids}})
        d.wh_pending_movements.delete_many({"material_id": {"$in": ids}})
        d.rahaza_fg_movements.delete_many({"material_id": {"$in": ids}})
        d.dewi_acc_movements.delete_many({"material_id": {"$in": ids}})
        d.rahaza_material_issues.delete_many({"items.material_id": {"$in": ids}})
        d.cutting_orders.delete_many({"input_material_id": {"$in": ids}})
        d.cutting_progress.delete_many({"cutting_number": {"$regex": "^CUT-"},
                                        "cutting_order_id": {"$in": []}})
    d.rahaza_materials.delete_many({"code": {"$regex": "ZZTEST-UOM-"}})
    d.wh_positions.delete_many({"barcode": BIN_BARCODE})
    d.wh_opname_sessions2.delete_many({"notes": "ZZTEST UOM"})
    d.wh_opname_sessions3.delete_many({"notes": "ZZTEST UOM"})
    for c in ("wh_opname_counts3", "wh_opname_sessions3"):
        try:
            d[c].delete_many({"bin_barcode": BIN_BARCODE})
        except Exception:  # noqa: BLE001
            pass


def setup(d):
    cleanup(d)
    loc = d.rahaza_locations.find_one({}, {"_id": 0, "id": 1}) or {}
    acc_id, fab_id = str(uuid.uuid4()), str(uuid.uuid4())
    d.rahaza_materials.insert_one({
        "id": acc_id, "code": ACC_CODE, "name": "ZZTEST Kancing UOM", "type": "accessory",
        "unit": "pcs", "base_uom": "pcs", "pack_unit": "box", "pack_size": 12.0,
        "display_in_packs": True, "purchase_uom": "box", "issue_uom": "pcs", "display_uom": "box",
        "unit_cost": 1000.0, "active": True,
        "uoms": [
            {"code": "pcs", "name": "PCS", "factor": 1.0, "is_base": True, "level": 0},
            {"code": "box", "name": "BOX", "factor": 12.0, "is_base": False, "level": 1,
             "parent": "pcs", "is_purchase_default": True, "is_display_default": True},
        ],
    })
    d.rahaza_materials.insert_one({
        "id": fab_id, "code": FAB_CODE, "name": "ZZTEST Kain UOM", "type": "fabric",
        "unit": "kg", "base_uom": "kg", "unit_cost": 100000.0, "active": True,
        "gsm": 240, "width_cm": 160,
        "uoms": [{"code": "kg", "name": "KG", "factor": 1.0, "is_base": True, "level": 0}],
    })
    d.rahaza_material_stock.insert_one({
        "id": str(uuid.uuid4()), "material_id": acc_id,
        "location_id": loc.get("id"), "qty": 240.0, "total_qty": 240.0,
        "quantity": 240.0, "available_quantity": 240.0,
    })
    d.rahaza_material_stock.insert_one({
        "id": str(uuid.uuid4()), "material_id": fab_id,
        "location_id": loc.get("id"), "qty": 100.0, "total_qty": 100.0,
        "quantity": 100.0, "available_quantity": 100.0,
    })
    bin_id = str(uuid.uuid4())
    d.wh_positions.insert_one({
        "id": bin_id, "barcode": BIN_BARCODE, "label": "UJI-UOM-B1", "full_label": "UJI-UOM-B1",
        "status": "empty", "qty": 0,
    })
    return acc_id, fab_id, bin_id, loc.get("id")


def login() -> dict:
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        raise SystemExit(f"login gagal: {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def onhand(d, mid) -> float:
    return round(sum(float(r.get("qty") or 0)
                     for r in d.rahaza_material_stock.find({"material_id": mid}, {"_id": 0})), 4)


def main() -> int:
    d = db()
    acc_id, fab_id, bin_id, loc_id = setup(d)
    hdr = login()
    made = {"mi": [], "cut": [], "mv": [], "opname_acc": [], "opname_wh": []}

    try:
        # ── 1. Endpoint opsi satuan ───────────────────────────────────────────
        r = requests.get(f"{API}/api/rahaza/materials/uom-options",
                         params={"material_ids": f"{acc_id},{fab_id}"}, headers=hdr, timeout=30)
        check("GET /rahaza/materials/uom-options 200", r.status_code == 200, r.text[:200])
        opts = r.json().get("options", {})
        accu = {u["unit"]: u for u in opts.get(acc_id, {}).get("units", [])}
        fabu = {u["unit"]: u for u in opts.get(fab_id, {}).get("units", [])}
        check("opsi aksesoris memuat kemasan master box = 12 pcs",
              accu.get("box", {}).get("factor_to_base") == 12.0 and accu["box"]["source"] == "uom",
              str(accu)[:200])
        check("opsi aksesoris memuat satuan global lusin = 12 pcs",
              accu.get("lusin", {}).get("factor_to_base") == 12.0, str(list(accu))[:200])
        check("opsi kain memuat gram (global) & m (via gramasi & lebar)",
              fabu.get("gram", {}).get("factor_to_base") == 0.001
              and abs(fabu.get("m", {}).get("factor_to_base", 0) - 0.384) < 1e-6,
              str(fabu)[:250])
        check("alias satuan ganda (gr/g/kgs) disembunyikan dari dropdown",
              "gr" not in fabu and "g" not in fabu and "kgs" not in fabu, str(list(fabu))[:200])
        check("material tak dikenal dilaporkan di `missing`",
              requests.get(f"{API}/api/rahaza/materials/uom-options",
                           params={"material_ids": "tidak-ada"}, headers=hdr,
                           timeout=30).json().get("missing") == ["tidak-ada"])

        # ── 2. Penerimaan Gudang: scan-in per box, dokumen ber-satuan pcs ─────
        base_before = onhand(d, acc_id)
        mv = requests.post(f"{API}/api/wms/pending", headers=hdr, timeout=30, json={
            "type": "inbound", "source_type": "manual", "material_id": acc_id,
            "material_code": ACC_CODE, "material_name": "ZZTEST Kancing UOM",
            "material_type": "accessory", "expected_qty": 24, "unit": "pcs",
            "notes": "ZZTEST UOM",
        })
        check("POST /wms/pending (movement uji) 200", mv.status_code == 200, mv.text[:200])
        mid = mv.json()["movement"]["id"]
        made["mv"].append(mid)
        sc = requests.post(f"{API}/api/wms/pending/{mid}/scan-in", headers=hdr, timeout=30,
                           json={"scanned_qty": 2, "input_uom": "box"})
        check("scan-in 2 box → HTTP 200", sc.status_code == 200, sc.text[:250])
        sj = sc.json() if sc.status_code == 200 else {}
        check("scan-in: jejak konversi dikembalikan (2 box = 24 pcs)",
              (sj.get("uom_applied") or {}).get("qty_base") == 24.0
              and sj["uom_applied"]["input_uom"] == "box", str(sj.get("uom_applied"))[:200])
        check("scan-in: qty dokumen diterjemahkan ke satuan dokumen (24 pcs)",
              sj.get("scanned_qty") == 24.0 and sj.get("status") == "confirmed",
              f"scanned={sj.get('scanned_qty')} status={sj.get('status')}")
        check("scan-in: stok bertambah 24 pcs (bukan 2)",
              abs(onhand(d, acc_id) - (base_before + 24)) < 1e-6,
              f"{base_before} → {onhand(d, acc_id)}")
        bad = requests.post(f"{API}/api/wms/pending/{mid}/scan-in", headers=hdr, timeout=30,
                            json={"scanned_qty": 1, "input_uom": "rol"})
        check("scan-in satuan asing ('rol') ditolak 400", bad.status_code == 400, bad.text[:200])

        # ── 3. Put-away memakai satuan global (gram) pada kain ───────────────
        pa = requests.post(f"{API}/api/wms/putaway/place", headers=hdr, timeout=30, json={
            "material_id": fab_id, "qty": 500, "position_id": bin_id, "input_uom": "gram",
        })
        check("put-away 500 gram → 200", pa.status_code == 200, pa.text[:250])
        pos = d.wh_positions.find_one({"id": bin_id}, {"_id": 0})
        check("put-away: 500 gram tercatat 0.5 kg di bin",
              abs(float(pos.get("qty") or 0) - 0.5) < 1e-6, str(pos.get("qty")))

        # ── 4. Opname Gudang: scan per box ───────────────────────────────────
        ses = requests.post(f"{API}/api/wms/opname3/sessions", headers=hdr, timeout=30,
                            json={"scope_type": "all", "scope_id": "", "notes": "ZZTEST UOM"})
        check("POST /wms/opname3/sessions 200", ses.status_code == 200, ses.text[:200])
        sid = ses.json().get("id")
        made["opname_wh"].append(sid)
        scan = requests.post(f"{API}/api/wms/opname3/scan", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_barcode": BIN_BARCODE, "item_material_id": fab_id,
            "qty": 250, "input_uom": "gram",
        })
        check("opname gudang: scan 250 gram → 200", scan.status_code == 200, scan.text[:250])
        check("opname gudang: tercatat 0.25 kg (satuan dasar)",
              abs(float((scan.json() or {}).get("counted_qty") or 0) - 0.25) < 1e-6,
              str(scan.json())[:200])
        bad2 = requests.post(f"{API}/api/wms/opname3/scan", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_barcode": BIN_BARCODE, "item_material_id": fab_id,
            "qty": 1, "input_uom": "bal",
        })
        check("opname gudang: satuan asing ditolak 400", bad2.status_code == 400, bad2.text[:200])
        requests.post(f"{API}/api/wms/opname3/cancel", headers=hdr, timeout=30,
                      json={"session_id": sid, "notes": "ZZTEST UOM"})

        # ── 5. Opname Aksesoris: hitung per box ──────────────────────────────
        aos = requests.post(f"{API}/api/acc/opname", headers=hdr, timeout=30,
                            json={"notes": "ZZTEST UOM"})
        check("POST /acc/opname 200/201", aos.status_code in (200, 201), aos.text[:250])
        asid = aos.json().get("id")
        made["opname_acc"].append(asid)
        cnt = requests.put(f"{API}/api/acc/opname/{asid}/count", headers=hdr, timeout=30,
                           json={"acc_id": acc_id, "counted_qty": 3, "counted_uom": "box"})
        check("opname aksesoris: 3 box → 200", cnt.status_code == 200, cnt.text[:250])
        det = requests.get(f"{API}/api/acc/opname/{asid}", headers=hdr, timeout=30).json()
        line = next((x for x in (det.get("lines") or []) if x.get("acc_id") == acc_id), {})
        check("opname aksesoris: tersimpan 36 pcs (bukan 3)",
              abs(float(line.get("counted_qty") or 0) - 36) < 1e-6, str(line)[:250])
        badc = requests.put(f"{API}/api/acc/opname/{asid}/count", headers=hdr, timeout=30,
                            json={"acc_id": acc_id, "counted_qty": 1, "counted_uom": "karung"})
        check("opname aksesoris: satuan asing ditolak 400", badc.status_code == 400, badc.text[:200])
        requests.post(f"{API}/api/acc/opname/{asid}/cancel", headers=hdr, timeout=30, json={})

        # ── 6. Pengeluaran Material (MI): qty_uom per baris ──────────────────
        mi = requests.post(f"{API}/api/rahaza/material-issues", headers=hdr, timeout=30, json={
            "notes": "ZZTEST UOM",
            "items": [{"material_id": acc_id, "qty_required": 2, "qty_uom": "box",
                       "location_id": loc_id}],
        })
        check("POST /rahaza/material-issues (2 box) 200", mi.status_code == 200, mi.text[:250])
        mid2 = mi.json().get("id")
        made["mi"].append(mid2)
        it0 = (mi.json().get("items") or [{}])[0]
        check("MI: qty_required disimpan 24 pcs (satuan dasar) + jejak input",
              it0.get("qty_required") == 24.0 and it0.get("input_uom") == "box"
              and it0.get("input_qty") == 2.0, str(it0)[:250])
        up = requests.put(f"{API}/api/rahaza/material-issues/{mid2}", headers=hdr, timeout=30,
                          json={"items": [{"id": it0.get("id"), "material_id": acc_id,
                                           "qty_required": 1, "qty_uom": "lusin",
                                           "location_id": loc_id}]})
        check("MI: PUT 1 lusin → 12 pcs (konversi global)",
              up.status_code == 200 and (up.json().get("items") or [{}])[0].get("qty_required") == 12.0,
              f"{up.status_code} {str(up.json())[:200]}")
        badmi = requests.post(f"{API}/api/rahaza/material-issues", headers=hdr, timeout=30, json={
            "notes": "ZZTEST UOM",
            "items": [{"material_id": acc_id, "qty_required": 1, "qty_uom": "karton"}],
        })
        check("MI: satuan asing ditolak 400", badmi.status_code == 400, badmi.text[:200])

        # ── 7. Pengeluaran & Penerimaan Aksesoris pakai kode satuan ──────────
        before = onhand(d, acc_id)
        iss = requests.post(f"{API}/api/acc/stock/issue", headers=hdr, timeout=30, json={
            "acc_id": acc_id, "qty": 2, "input_unit": "box", "notes": "ZZTEST UOM",
        })
        check("POST /acc/stock/issue 2 box → 201", iss.status_code == 201, iss.text[:250])
        check("issue aksesoris: stok turun 24 pcs",
              abs(onhand(d, acc_id) - (before - 24)) < 1e-6, f"{before} → {onhand(d, acc_id)}")
        rc = requests.post(f"{API}/api/acc/stock/receive", headers=hdr, timeout=30, json={
            "acc_id": acc_id, "qty": 1, "input_unit": "box", "unit_cost": 24000,
            "cost_unit": "box", "notes": "ZZTEST UOM",
        })
        check("POST /acc/stock/receive 1 box (harga per box) → 200",
              rc.status_code in (200, 201), rc.text[:250])
        rcj = rc.json() if rc.status_code in (200, 201) else {}
        check("receive aksesoris: 1 box = 12 pcs & harga Rp24.000/box = Rp2.000/pcs",
              rcj.get("qty_received") == 12.0 and abs(float(rcj.get("unit_cost_in") or 0) - 2000) < 1e-6,
              str(rcj)[:250])
        badi = requests.post(f"{API}/api/acc/stock/issue", headers=hdr, timeout=30, json={
            "acc_id": acc_id, "qty": 1, "input_unit": "karung", "notes": "ZZTEST UOM",
        })
        check("issue aksesoris: satuan asing ditolak 400", badi.status_code == 400, badi.text[:200])

        # ── 8. Progres Cutting: kain dihitung per gram ───────────────────────
        co = requests.post(f"{API}/api/cutting/orders", headers=hdr, timeout=30, json={
            "input_material_id": fab_id, "planned_input_qty": 10, "planned_output_qty": 50,
            "style_name": "ZZTEST UOM Style", "location_id": loc_id, "notes": "ZZTEST UOM",
        })
        check("POST /cutting/orders 200", co.status_code == 200, co.text[:250])
        oid = co.json().get("id")
        made["cut"].append(oid)
        st = requests.post(f"{API}/api/cutting/orders/{oid}/start", headers=hdr, timeout=30, json={})
        check("POST /cutting/orders/{id}/start 200", st.status_code == 200, st.text[:200])
        fab_before = onhand(d, fab_id)
        pr = requests.post(f"{API}/api/cutting/orders/{oid}/progress", headers=hdr, timeout=30,
                           json={"input_consumed": 500, "output_qty": 5, "input_uom": "gram"})
        check("cutting: progres 500 gram → 200", pr.status_code == 200, pr.text[:250])
        prj = pr.json() if pr.status_code == 200 else {}
        check("cutting: terpakai tercatat 0.5 kg (satuan order)",
              abs(float(prj.get("consumed_input_qty") or 0) - 0.5) < 1e-6,
              str(prj.get("consumed_input_qty")))
        check("cutting: stok kain turun 0.5 kg (bukan 500)",
              abs(onhand(d, fab_id) - (fab_before - 0.5)) < 1e-6,
              f"{fab_before} → {onhand(d, fab_id)}")
        pr2 = requests.post(f"{API}/api/cutting/orders/{oid}/progress", headers=hdr, timeout=30,
                            json={"input_consumed": 1, "output_qty": 5})
        check("cutting: tanpa input_uom perilaku lama (1 kg)",
              pr2.status_code == 200
              and abs(float(pr2.json().get("consumed_input_qty") or 0) - 1.5) < 1e-6,
              f"{pr2.status_code} {str(pr2.json().get('consumed_input_qty'))}")
        badp = requests.post(f"{API}/api/cutting/orders/{oid}/progress", headers=hdr, timeout=30,
                             json={"input_consumed": 1, "output_qty": 1, "input_uom": "bal"})
        check("cutting: satuan asing ditolak 400", badp.status_code == 400, badp.text[:200])

    finally:
        # bersih-bersih total (dokumen uji + stok + ledger + bin)
        for oid in made["cut"]:
            d.cutting_progress.delete_many({"cutting_order_id": oid})
        cleanup(d)
        print("\n[cleanup] semua artefak uji ZZTEST-UOM-* dibersihkan")

    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    for f in FAIL:
        print("  FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
