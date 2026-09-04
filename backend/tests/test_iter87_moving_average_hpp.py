"""
Iter 87 — BUG3: moving-average HPP flow.

Full lifecycle:
  1) Create material (accessory, no unit_cost)
  2) PO1 100 @ 10000 → submit → approve → create-GR → PUT receiving 'received'
  3) Verify material.unit_cost == 10000 & cost_method == 'moving_average'
  4) PO2 100 @ 20000 → submit → approve → create-GR → PUT receiving 'received'
  5) Verify material.unit_cost == 15000 (moving average)
  6) PUT /materials/{id} unit_cost=1 → 200 but harga_satuan_catatan present, price unchanged
  7) Cleanup all artefacts.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def artefacts():
    return {"material_id": None, "po_ids": [], "gr_ids": []}


def _approve_until(H, po_id, target="approved", max_loops=6):
    for _ in range(max_loops):
        r = requests.get(f"{API}/rahaza/purchase-orders/{po_id}", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        st = r.json().get("status")
        if st == target:
            return
        r2 = requests.post(f"{API}/rahaza/purchase-orders/{po_id}/approve",
                           headers=H, json={}, timeout=30)
        if r2.status_code >= 400:
            # already advanced by another step
            pass
        time.sleep(0.2)
    r = requests.get(f"{API}/rahaza/purchase-orders/{po_id}", headers=H, timeout=30)
    raise AssertionError(f"PO {po_id} tidak mencapai '{target}', status akhir={r.json().get('status')}")


def _do_po_and_receive(H, material_id, qty, unit_cost, artefacts):
    # 1) Create PO
    payload = {
        "vendor_name": "TEST_VENDOR_ITER87",
        "items": [{
            "material_id": material_id,
            "uom": "pcs",
            "qty_input": qty,
            "unit_cost_input": unit_cost,
        }],
        "notes": "TEST_ITER87",
    }
    r = requests.post(f"{API}/rahaza/purchase-orders", headers=H, json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    po = r.json()
    po_id = po["id"]
    artefacts["po_ids"].append(po_id)

    # 2) Submit
    r = requests.post(f"{API}/rahaza/purchase-orders/{po_id}/submit", headers=H, json={}, timeout=30)
    assert r.status_code == 200, r.text

    # 3) Approve loop
    _approve_until(H, po_id, "approved")

    # 4) Create GR
    r = requests.post(f"{API}/rahaza/purchase-orders/{po_id}/create-gr",
                      headers=H, json={}, timeout=30)
    assert r.status_code in (200, 201), r.text
    gr = r.json()
    gr_id = gr.get("id") or gr.get("receipt_id")
    assert gr_id, gr
    artefacts["gr_ids"].append(gr_id)

    # 5) PUT receiving to 'received' with received_qty=qty
    items = gr.get("items") or []
    assert items, gr
    for it in items:
        it["received_qty"] = qty
        it["rejected_qty"] = 0
    # Need to attach a location. Fetch first available location.
    r = requests.get(f"{API}/wms/locations?limit=1", headers=H, timeout=30)
    location_id = None
    location_name = None
    if r.status_code == 200:
        data = r.json()
        locs = data.get("items") or data if isinstance(data, list) else data.get("items", [])
        if locs:
            location_id = locs[0].get("id")
            location_name = locs[0].get("name") or locs[0].get("code")
    if not location_id:
        # Fallback to legacy warehouse locations
        r = requests.get(f"{API}/wms/legacy/locations", headers=H, timeout=30)
        if r.status_code == 200:
            locs = r.json()
            if isinstance(locs, list) and locs:
                location_id = locs[0].get("id")
                location_name = locs[0].get("name") or locs[0].get("code")

    put_body = {"status": "received", "items": items}
    if location_id:
        put_body["location_id"] = location_id
        put_body["location_name"] = location_name or ""
    r = requests.put(f"{API}/wms/legacy/receiving/{gr_id}",
                     headers=H, json=put_body, timeout=60)
    assert r.status_code == 200, f"PUT receiving failed: {r.status_code} {r.text}"
    return po_id, gr_id


class TestMovingAverageHPP:

    def test_01_create_material_without_price(self, H, artefacts):
        code = f"TEST{int(time.time())}"
        body = {
            "code": code,
            "name": "TEST_ITER87_ACC_MOVAVG",
            "type": "accessory",
            "unit": "pcs",
            "min_stock": 0,
        }
        r = requests.post(f"{API}/rahaza/materials", headers=H, json=body, timeout=30)
        assert r.status_code in (200, 201), r.text
        m = r.json()
        assert float(m.get("unit_cost") or 0) == 0, m
        artefacts["material_id"] = m["id"]

    def test_02_po1_receive_100_at_10000(self, H, artefacts):
        mid = artefacts["material_id"]
        _do_po_and_receive(H, mid, qty=100, unit_cost=10000, artefacts=artefacts)

        r = requests.get(f"{API}/rahaza/materials/{mid}", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        m = r.json()
        assert abs(float(m["unit_cost"]) - 10000) < 1e-3, m
        assert m.get("cost_method") == "moving_average", m
        assert abs(float(m.get("last_receipt_unit_cost") or 0) - 10000) < 1e-3, m

    def test_03_po2_receive_100_at_20000_gives_avg_15000(self, H, artefacts):
        mid = artefacts["material_id"]
        _do_po_and_receive(H, mid, qty=100, unit_cost=20000, artefacts=artefacts)

        r = requests.get(f"{API}/rahaza/materials/{mid}", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        m = r.json()
        assert abs(float(m["unit_cost"]) - 15000) < 1e-3, f"unit_cost={m.get('unit_cost')} — expected 15000"
        assert m.get("cost_method") == "moving_average", m
        assert abs(float(m.get("last_receipt_unit_cost") or 0) - 20000) < 1e-3, m

    def test_04_put_material_unit_cost_ignored(self, H, artefacts):
        mid = artefacts["material_id"]
        r = requests.put(f"{API}/rahaza/materials/{mid}", headers=H,
                         json={"unit_cost": 1}, timeout=30)
        assert r.status_code == 200, r.text
        out = r.json()
        assert "harga_satuan_catatan" in out, f"catatan hilang: {out}"

        r = requests.get(f"{API}/rahaza/materials/{mid}", headers=H, timeout=30)
        m = r.json()
        assert abs(float(m["unit_cost"]) - 15000) < 1e-3, f"unit_cost berubah! {m.get('unit_cost')}"

    def test_99_cleanup(self, H, artefacts):
        db_cleaned = True
        # Try to delete via mongo direct (safer than API which just deactivates)
        import subprocess
        mid = artefacts["material_id"]
        po_ids = artefacts["po_ids"]
        gr_ids = artefacts["gr_ids"]

        # Get DB_NAME
        db_name = None
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("DB_NAME="):
                        db_name = line.strip().split("=", 1)[1].strip('"').strip("'")
                        break
                    if line.startswith("MONGO_URL="):
                        pass
        except Exception:
            pass
        assert db_name, "DB_NAME tidak ditemukan"

        script = f"""
use {db_name};
db.rahaza_materials.deleteMany({{id: "{mid}"}});
db.rahaza_material_stock.deleteMany({{material_id: "{mid}"}});
db.rahaza_material_movements.deleteMany({{material_id: "{mid}"}});
db.rahaza_stock_ledger.deleteMany({{material_id: "{mid}"}});
db.rahaza_material_cost_history.deleteMany({{material_id: "{mid}"}});
db.warehouse_stock.deleteMany({{material_id: "{mid}"}});
db.rahaza_purchase_orders.deleteMany({{id: {{$in: {po_ids!r}}}}});
db.warehouse_receiving.deleteMany({{id: {{$in: {gr_ids!r}}}}});
db.rahaza_material_quarantine.deleteMany({{material_id: "{mid}"}});
"""
        p = subprocess.run(["mongosh", "--quiet", "--eval", script],
                           capture_output=True, text=True, timeout=30)
        # Not asserting — cleanup is best-effort
        print("CLEANUP mongo:", p.stdout, p.stderr)
        assert db_cleaned
