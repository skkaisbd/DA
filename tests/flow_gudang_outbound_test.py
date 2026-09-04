"""E2E API-level test for Warehouse Outbound Flow (Pick List + Surat Jalan)."""
import requests, sys

BASE = "http://localhost:8001"
S = requests.Session()
created = {"picklists": [], "sjs": [], "material": None}

def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")

def ensure_material():
    # create a temporary FG material for picklist
    body = {"code": "E2E-OUT-FG", "name": "E2E Outbound FG", "type": "fg", "unit": "pcs"}
    r = S.post(f"{BASE}/api/rahaza/materials", json=body)
    if r.status_code == 200:
        created["material"] = r.json()["id"]
    elif r.status_code == 409:
        mats = S.get(f"{BASE}/api/rahaza/materials?search=E2E-OUT-FG").json()
        mats = mats if isinstance(mats, list) else mats.get("data", [])
        created["material"] = next(m["id"] for m in mats if m["code"] == "E2E-OUT-FG")
    else:
        raise AssertionError(f"material create failed {r.status_code}: {r.text}")
    print(f"PASS material E2E-OUT-FG ({created['material'][:8]})")

def test_picklist():
    # Create picklist from manual items
    body = {"source_type": "manual", "source_ref": "E2E-OUT", "items": [
        {"material_id": created["material"], "qty": 50, "unit": "pcs"}
    ]}
    r = S.post(f"{BASE}/api/wms/picklist", json=body)
    assert r.status_code == 200, f"picklist create {r.status_code}: {r.text}"
    pl = r.json()["picklist"]
    pid = pl["picklist_id"]
    created["picklists"].append(pid)
    assert pl["status"] == "pending", f"expected pending got {pl['status']}"
    print(f"PASS picklist created {pl['ref_number']} status=pending")

    # Mark each item picked
    for it in pl["items"]:
        r = S.put(f"{BASE}/api/wms/picklist/{pid}/item/{it['pick_item_id']}/pick", json={"picked_qty": it["qty_to_pick"]})
        assert r.status_code == 200, f"pick item {r.status_code}: {r.text}"
    print("PASS picklist items picked")

    # Complete
    r = S.post(f"{BASE}/api/wms/picklist/{pid}/complete")
    assert r.status_code == 200, f"complete {r.status_code}: {r.text}"
    detail = S.get(f"{BASE}/api/wms/picklist/{pid}").json()["picklist"]
    assert detail["status"] == "completed", f"expected completed got {detail['status']}"
    print("PASS picklist completed")

def test_surat_jalan():
    # Create draft SJ
    body = {
        "sj_type": "SJ-ONLINE", "recipient_name": "E2E Penerima Test",
        "recipient_address": "Jl. E2E No.1", "recipient_phone": "08123",
        "shipper_name": "Kurir E2E", "vehicle_no": "B 1234 XYZ",
        "reference_type": "order", "reference_no": "E2E-OUT",
        "lines": [{"description": "E2E Outbound FG", "qty": 50, "unit": "pcs", "material_code": "E2E-OUT-FG"}],
    }
    r = S.post(f"{BASE}/api/wms/delivery-notes", json=body)
    assert r.status_code == 200, f"SJ create {r.status_code}: {r.text}"
    sj = r.json()["sj"]
    sid = sj["id"]
    created["sjs"].append(sid)
    assert sj["status"] == "draft", f"expected draft got {sj['status']}"
    print(f"PASS SJ created {sj['sj_number']} status=draft")

    # Issue
    r = S.post(f"{BASE}/api/wms/delivery-notes/{sid}/issue", json={})
    assert r.status_code == 200, f"SJ issue {r.status_code}: {r.text}"
    assert r.json()["sj"]["status"] == "issued"
    print("PASS SJ issued")

    # Receive
    r = S.post(f"{BASE}/api/wms/delivery-notes/{sid}/receive", json={"received_by": "E2E QA"})
    assert r.status_code == 200, f"SJ receive {r.status_code}: {r.text}"
    assert r.json()["sj"]["status"] == "received"
    print("PASS SJ received")

def cleanup():
    for pid in created["picklists"]:
        S.delete(f"{BASE}/api/wms/picklist/{pid}")
    # SJ received cannot be deleted; cancel not allowed for received. Leave to final DB cleanup.
    print("CLEANUP picklists deleted; SJ received retained (final DB cleanup handles it)")

def main():
    login(); ensure_material(); test_picklist(); test_surat_jalan()
    print("\n=== OUTBOUND ALL PASS ===")
    cleanup()

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
