"""
FLOW backend test — "Alur Inbound Gudang" (Warehouse Inbound Flow).

Alur happy-path lintas modul di layer API + DB:
    Buat PO (draft) -> Ajukan (pending_approval) -> Setujui (approved)
    -> Penerimaan/GRN (POST /receiving draft, PUT status=received)
       -> stok bertambah (warehouse_stock + rahaza_material_stock) + PO qty_received naik
    -> Penyimpanan/Putaway (pindah stok lokasi terima -> lokasi simpan).

Strategi = AMAN untuk DB live + SELF-CLEANUP penuh:
  - Membuat fixture: 1 material + 2 lokasi (receiving & storage), ditandai created_by.
  - Menjalankan seluruh alur dengan qty kecil & SKU unik.
  - Di blok finally: menghapus PO, GRN, stok (warehouse_stock/material_stock),
    movements, putaway, dan fixture. Tidak menyentuh data lain.

Tipe kasus: [H]appy [E]dge [N]egative [S]tate.
Jalankan: python3 tests/flow_gudang_inbound_test.py
"""
import sys
import uuid
import datetime
from pathlib import Path

import requests
from pymongo import MongoClient

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
SKU = "ZZ-GD-SKU"
PNAME = "Flow Gudang Material"

results = []
def rec(tc, verdict, detail=""):
    results.append((tc, verdict, detail))
    print(f"[{tc}] {verdict} | {detail}")

def H(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
def G(p, t): return requests.get(f"{BASE}{p}", headers=H(t), timeout=30)
def P(p, t, b=None): return requests.post(f"{BASE}{p}", headers=H(t), json=(b or {}), timeout=60)
def PUT(p, t, b=None): return requests.put(f"{BASE}{p}", headers=H(t), json=(b or {}), timeout=60)

# ── DB handle ────────────────────────────────────────────────────────────────
env = {}
for line in Path(__file__).resolve().parents[1].joinpath("backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
mongo = MongoClient(env["MONGO_URL"])
db = mongo[env.get("DB_NAME", "test_database")]

# ── Login ─────────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
r.raise_for_status()
admin = r.json()["token"]
print("admin login OK")

today = datetime.date.today().isoformat()
FIX_MARK = "flow-gudang-test"
material_id = f"flowgd-mat-{uuid.uuid4().hex[:8]}"
loc_recv_id = f"flowgd-recv-{uuid.uuid4().hex[:6]}"
loc_store_id = f"flowgd-store-{uuid.uuid4().hex[:6]}"
po_id = None
gr_id = None

try:
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    db.rahaza_materials.insert_one({
        "id": material_id, "code": "ZZ-GD-MAT", "name": PNAME, "unit": "pcs",
        "active": True, "created_by": FIX_MARK, "created_at": now_dt,
    })
    db.warehouse_locations.insert_one({
        "id": loc_recv_id, "code": "ZZ-RECV", "name": "ZZ Receiving Dock",
        "type": "receiving", "active": True, "created_by": FIX_MARK, "created_at": now_dt,
    })
    db.warehouse_locations.insert_one({
        "id": loc_store_id, "code": "ZZ-STORE", "name": "ZZ Storage Rack",
        "type": "storage", "active": True, "created_by": FIX_MARK, "created_at": now_dt,
    })
    rec("TC-00", "PASS", f"[S] fixture material + 2 lokasi dibuat")

    # ── STEP 1: Buat PO — negatif ────────────────────────────────────────────
    r = P("/api/rahaza/purchase-orders", admin, {"vendor_name": "", "items": [{"material_id": material_id, "qty_ordered": 10}]})
    rec("TC-01", "PASS" if r.status_code == 400 else "FAIL", f"[N] PO tanpa vendor -> 400 ({r.status_code})")

    r = P("/api/rahaza/purchase-orders", admin, {"vendor_name": "ZZ Vendor", "items": []})
    rec("TC-02", "PASS" if r.status_code == 400 else "FAIL", f"[N] PO tanpa item -> 400 ({r.status_code})")

    # ── STEP 1b: Buat PO happy ───────────────────────────────────────────────
    r = P("/api/rahaza/purchase-orders", admin, {
        "vendor_name": "ZZ Flow Vendor", "po_date": today,
        "items": [{"material_id": material_id, "qty_ordered": 100, "unit_cost": 5000}],
    })
    pj = r.json() if r.status_code == 200 else {}
    po_id = pj.get("id")
    po_number = pj.get("po_number")
    po_item_id = (pj.get("items") or [{}])[0].get("id")
    ok = r.status_code == 200 and pj.get("status") == "draft" and po_number
    rec("TC-03", "PASS" if ok else "FAIL", f"[H] buat PO {po_number} status={pj.get('status')} ({r.status_code})")

    # ── STEP 2: Ajukan + Setujui ─────────────────────────────────────────────
    r = P(f"/api/rahaza/purchase-orders/{po_id}/submit", admin)
    ok = r.status_code == 200 and r.json().get("status") == "pending_approval"
    rec("TC-04", "PASS" if ok else "FAIL", f"[S] submit PO -> pending_approval ({r.status_code})")

    r = P(f"/api/rahaza/purchase-orders/{po_id}/approve", admin)
    ok = r.status_code == 200 and r.json().get("status") == "approved"
    rec("TC-05", "PASS" if ok else "FAIL", f"[S] approve PO -> approved ({r.status_code})")

    # ── STEP 3: Penerimaan (GRN) ─────────────────────────────────────────────
    gr_items = [{
        "material_id": material_id, "sku": SKU, "product_name": PNAME,
        "po_item_id": po_item_id, "expected_qty": 100, "received_qty": 100,
        "rejected_qty": 0, "unit": "pcs",
    }]
    r = P("/api/wms/legacy/receiving", admin, {
        "po_id": po_id, "po_number": po_number, "source_type": "supplier",
        "supplier_name": "ZZ Flow Vendor",
        "location_id": loc_recv_id, "location_name": "ZZ Receiving Dock",
        "items": gr_items,
    })
    grj = r.json() if r.status_code == 200 else {}
    gr_id = grj.get("id")
    ok = r.status_code == 200 and gr_id and grj.get("status") == "draft" and grj.get("receipt_number")
    rec("TC-06", "PASS" if ok else "FAIL", f"[H] buat GRN {grj.get('receipt_number')} status={grj.get('status')} ({r.status_code})")

    # ── STEP 3b: over-receive ditolak ────────────────────────────────────────
    over = [{**gr_items[0], "received_qty": 999}]
    r = PUT(f"/api/wms/legacy/receiving/{gr_id}", admin, {"status": "received", "items": over})
    rec("TC-07", "PASS" if r.status_code == 400 else "FAIL", f"[N] over-receive (999 > sisa 100) -> 400 ({r.status_code})")

    # ── STEP 3c: terima (received) ───────────────────────────────────────────
    r = PUT(f"/api/wms/legacy/receiving/{gr_id}", admin, {"status": "received", "items": gr_items})
    ok = r.status_code == 200 and r.json().get("status") == "received"
    rec("TC-08", "PASS" if ok else "FAIL", f"[H] GRN -> received ({r.status_code})")

    # ── STEP 3d: verifikasi stok bertambah (dual-ledger) ─────────────────────
    ws = db.warehouse_stock.find_one({"location_id": loc_recv_id, "sku": SKU})
    ms_total = sum(float(d.get("qty", 0)) for d in db.rahaza_material_stock.find({"material_id": material_id}))
    ok = ws and float(ws.get("quantity", 0)) == 100 and ms_total == 100
    rec("TC-09", "PASS" if ok else "FAIL",
        f"[S] stok +100 (warehouse_stock={ws.get('quantity') if ws else None}, material_stock={ms_total})")
    source_stock_id = ws.get("id") if ws else None

    # ── STEP 3e: PO qty_received naik -> fully_received ──────────────────────
    r = G(f"/api/rahaza/purchase-orders/{po_id}", admin)
    poj = r.json() if r.status_code == 200 else {}
    got = float((poj.get("items") or [{}])[0].get("qty_received", 0))
    ok = r.status_code == 200 and got == 100 and poj.get("status") == "fully_received"
    rec("TC-10", "PASS" if ok else "FAIL",
        f"[S] PO qty_received=100, status={poj.get('status')} ({r.status_code})")

    # ── STEP 4: Putaway parsial (60) ─────────────────────────────────────────
    r = P("/api/wms/legacy/putaway", admin, {
        "source_stock_id": source_stock_id, "target_location_id": loc_store_id, "quantity": 60,
    })
    ok = r.status_code == 200 and r.json().get("quantity") == 60
    rec("TC-11", "PASS" if ok else "FAIL", f"[H] putaway 60 -> ZZ Storage ({r.status_code})")

    recv_stock = db.warehouse_stock.find_one({"location_id": loc_recv_id, "sku": SKU})
    store_stock = db.warehouse_stock.find_one({"location_id": loc_store_id, "sku": SKU})
    ok = recv_stock and float(recv_stock.get("quantity", 0)) == 40 and store_stock and float(store_stock.get("quantity", 0)) == 60
    rec("TC-12", "PASS" if ok else "FAIL",
        f"[S] setelah putaway 60: terima={recv_stock.get('quantity') if recv_stock else None}, simpan={store_stock.get('quantity') if store_stock else None}")

    # ── STEP 4b: putaway melebihi tersedia ───────────────────────────────────
    r = P("/api/wms/legacy/putaway", admin, {
        "source_stock_id": source_stock_id, "target_location_id": loc_store_id, "quantity": 100,
    })
    rec("TC-13", "PASS" if r.status_code == 400 else "FAIL", f"[N] putaway 100 > tersedia 40 -> 400 ({r.status_code})")

    # ── STEP 4c: putaway sisa (40) ───────────────────────────────────────────
    r = P("/api/wms/legacy/putaway", admin, {
        "source_stock_id": source_stock_id, "target_location_id": loc_store_id, "quantity": 40,
    })
    store_stock = db.warehouse_stock.find_one({"location_id": loc_store_id, "sku": SKU})
    recv_stock = db.warehouse_stock.find_one({"location_id": loc_recv_id, "sku": SKU})
    ok = (r.status_code == 200 and store_stock and float(store_stock.get("quantity", 0)) == 100
          and recv_stock and float(recv_stock.get("quantity", 0)) == 0)
    rec("TC-14", "PASS" if ok else "FAIL",
        f"[H] putaway sisa 40 -> simpan=100, terima=0 ({r.status_code})")

finally:
    # ── SELF-CLEANUP ─────────────────────────────────────────────────────────
    deleted = {}
    try:
        if po_id:
            deleted["pos"] = db.rahaza_purchase_orders.delete_many({"id": po_id}).deleted_count
        if gr_id:
            deleted["receiving"] = db.warehouse_receiving.delete_many({"id": gr_id}).deleted_count
        deleted["warehouse_stock"] = db.warehouse_stock.delete_many({"sku": SKU}).deleted_count
        deleted["warehouse_movements"] = db.warehouse_movements.delete_many({"sku": SKU}).deleted_count
        deleted["warehouse_putaway"] = db.warehouse_putaway.delete_many({"sku": SKU}).deleted_count
        deleted["material_stock"] = db.rahaza_material_stock.delete_many({"material_id": material_id}).deleted_count
        deleted["material_movements"] = db.rahaza_material_movements.delete_many({"material_id": material_id}).deleted_count
        deleted["materials"] = db.rahaza_materials.delete_many({"id": material_id}).deleted_count
        deleted["locations"] = db.warehouse_locations.delete_many({"created_by": FIX_MARK}).deleted_count
        rec("CLEANUP", "PASS", f"[S] dokumen dihapus: {deleted}")
    except Exception as e:
        rec("CLEANUP", "FAIL", f"[S] cleanup error: {e}")

# ── Ringkasan ────────────────────────────────────────────────────────────────
n_pass = sum(1 for _, v, _ in results if v == "PASS")
n_fail = sum(1 for _, v, _ in results if v == "FAIL")
print("\n" + "=" * 70)
print(f" RINGKASAN: {n_pass} PASS · {n_fail} FAIL · total {len(results)}")
print("=" * 70)
if n_fail:
    print(" STATUS: FAIL")
    sys.exit(1)
print(" STATUS: PASS — Alur Inbound Gudang happy-path terverifikasi end-to-end.")
sys.exit(0)
