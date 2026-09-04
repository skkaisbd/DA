"""
E2E API-level POC test — Alur Stock Opname (Gudang, wms/opname2).

Happy path:
  login
  -> seed fixture position (wh_positions) di rack unik            [DB]
  -> start sesi opname (scope rack)                               [POST /api/wms/opname2/start]
  -> scan/count item (counted < system => selisih)               [POST /api/wms/opname2/{id}/scan]
  -> submit untuk approval                                        [POST /api/wms/opname2/{id}/submit]
  -> approve + apply adjustments (posting ke wh_positions)        [POST /api/wms/opname2/{id}/approve]
  -> verifikasi qty posisi ter-adjust + movement audit tercatat   [DB]
Guards:
  -> submit sesi tanpa item ter-count ditolak (400)
  -> approve sesi non-pending ditolak (400)
  -> hanya 1 sesi open sekaligus (start kedua ditolak 400)
  -> scan pada sesi non-open (approved) ditolak (400)
  -> cancel sesi approved ditolak (400)
Self-cleanup (hard): hapus sesi uji + fixture position + movement audit.
"""
import sys
import uuid
import requests

BASE = "http://localhost:8001"
S = requests.Session()
POS_BARCODE = "E2E-OPN-POS"
RACK_ID = "E2E-OPN-RACK"
MAT_CODE = "E2E-OPN-MAT"
st = {"sessions": [], "pos_id": None}


def _mongo():
    url = db = None
    with open("/app/backend/.env") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("MONGO_URL="):
                url = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("DB_NAME="):
                db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    from pymongo import MongoClient
    cli = MongoClient(url)
    return cli, cli[db or "test_database"]


def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")


def seed_position():
    cli, db = _mongo()
    db.wh_positions.delete_many({"barcode": POS_BARCODE})
    pos_id = str(uuid.uuid4())
    db.wh_positions.insert_one({
        "id": pos_id, "barcode": POS_BARCODE, "rack_id": RACK_ID,
        "material_code": MAT_CODE, "material_name": "E2E Opname Material",
        "qty": 100.0, "unit": "pcs",
    })
    cli.close()
    st["pos_id"] = pos_id
    print("PASS seed fixture position qty=100 di rack E2E-OPN-RACK")


def start_session(label="E2E Opname"):
    body = {"mode": "cycle_count", "scope_type": "rack", "scope_id": RACK_ID,
            "scope_label": label, "notes": "E2E opname fixture"}
    r = S.post(f"{BASE}/api/wms/opname2/start", json=body)
    return r


def main():
    login()
    seed_position()

    # ── Fase 1: start sesi (open) ────────────────────────────────────────────
    r = start_session()
    assert r.status_code == 200, f"start {r.status_code}: {r.text}"
    s1 = r.json()["session"]
    st["sessions"].append(s1["id"])
    assert s1["status"] == "open" and s1["total_items"] == 1, f"session start {s1}"
    print(f"PASS start sesi {s1['session_no']} status=open total_items=1")

    # ── Fase 2: scan/count (counted=95 => selisih -5) ────────────────────────
    r = S.post(f"{BASE}/api/wms/opname2/{s1['id']}/scan",
               json={"position_barcode": POS_BARCODE, "material_code": MAT_CODE, "counted_qty": 95})
    assert r.status_code == 200 and r.json()["counted_items"] == 1, f"scan {r.status_code}: {r.text}"
    print("PASS scan count=95 (system=100 => selisih -5) counted_items=1")

    # ── Fase 3: submit => pending_approval ───────────────────────────────────
    r = S.post(f"{BASE}/api/wms/opname2/{s1['id']}/submit", json={})
    assert r.status_code == 200 and r.json().get("pending_approval"), f"submit {r.status_code}: {r.text}"
    print("PASS submit => pending_approval")

    # ── Guard: submit tanpa item ter-count + approve non-pending ─────────────
    r = start_session("E2E Guard Empty")
    assert r.status_code == 200, f"start S2 {r.status_code}: {r.text}"
    s2 = r.json()["session"]; st["sessions"].append(s2["id"])
    rg = S.post(f"{BASE}/api/wms/opname2/{s2['id']}/submit", json={})
    assert rg.status_code >= 400, f"expected reject submit-empty got {rg.status_code}"
    print("PASS guard: submit sesi tanpa item ter-count ditolak (400)")
    rg = S.post(f"{BASE}/api/wms/opname2/{s2['id']}/approve", json={"apply_adjustments": False})
    assert rg.status_code >= 400, f"expected reject approve-non-pending got {rg.status_code}"
    print("PASS guard: approve sesi non-pending ditolak (400)")
    r = S.post(f"{BASE}/api/wms/opname2/{s2['id']}/cancel", json={"reason": "E2E"})
    assert r.status_code == 200, f"cancel S2 {r.status_code}: {r.text}"

    # ── Guard: hanya 1 sesi open sekaligus ───────────────────────────────────
    r = start_session("E2E Open A")
    assert r.status_code == 200, f"start S3 {r.status_code}: {r.text}"
    s3 = r.json()["session"]; st["sessions"].append(s3["id"])
    rg = start_session("E2E Open B")
    assert rg.status_code >= 400, f"expected reject 2nd open session got {rg.status_code}"
    print("PASS guard: hanya 1 sesi open sekaligus (start kedua ditolak 400)")
    r = S.post(f"{BASE}/api/wms/opname2/{s3['id']}/cancel", json={"reason": "E2E"})
    assert r.status_code == 200, f"cancel S3 {r.status_code}"

    # ── Fase 4: approve S1 + apply adjustments (posting) ─────────────────────
    r = S.post(f"{BASE}/api/wms/opname2/{s1['id']}/approve",
               json={"apply_adjustments": True, "notes": "E2E approve posting"})
    assert r.status_code == 200 and r.json().get("adjustments_applied"), f"approve {r.status_code}: {r.text}"
    sess = S.get(f"{BASE}/api/wms/opname2/{s1['id']}").json()
    assert sess["status"] == "approved", f"expected approved got {sess['status']}"
    print("PASS approve + apply adjustments => status=approved")

    # ── Verifikasi posting: qty posisi ter-adjust + movement audit ───────────
    cli, db = _mongo()
    pos = db.wh_positions.find_one({"barcode": POS_BARCODE}, {"_id": 0})
    assert pos and pos["qty"] == 95, f"expected position qty adjusted to 95 got {pos.get('qty') if pos else None}"
    mov = db.wh_fg_movements.count_documents({"session_id": s1["id"], "source": "opname_adjustment"})
    cli.close()
    assert mov >= 1, "movement audit opname_adjustment tidak tercatat"
    print(f"PASS posting: wh_positions qty -> 95 + {mov} movement audit (opname_adjustment) tercatat")

    # ── Guard: scan pada sesi approved + cancel approved ─────────────────────
    rg = S.post(f"{BASE}/api/wms/opname2/{s1['id']}/scan",
                json={"position_barcode": POS_BARCODE, "counted_qty": 10})
    assert rg.status_code >= 400, f"expected reject scan non-open got {rg.status_code}"
    print("PASS guard: scan pada sesi approved (non-open) ditolak (400)")
    rg = S.post(f"{BASE}/api/wms/opname2/{s1['id']}/cancel", json={"reason": "E2E"})
    assert rg.status_code >= 400, f"expected reject cancel approved got {rg.status_code}"
    print("PASS guard: cancel sesi approved ditolak (400)")

    # ── Sanity: list & stats ─────────────────────────────────────────────────
    assert S.get(f"{BASE}/api/wms/opname2").status_code == 200, "list sessions gagal"
    assert S.get(f"{BASE}/api/wms/opname2/stats").status_code == 200, "stats gagal"
    print("PASS list sesi + stats 200")

    print("\n=== STOCK OPNAME FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        # sapu sesi uji berdasar id + fixture-notes
        ids = set(st["sessions"])
        n_s = db.wh_opname_sessions2.delete_many({"$or": [
            {"id": {"$in": list(ids)}},
            {"notes": "E2E opname fixture"},
        ]}).deleted_count
        n_p = db.wh_positions.delete_many({"barcode": POS_BARCODE}).deleted_count
        n_m = db.wh_fg_movements.delete_many({"position_barcode": POS_BARCODE}).deleted_count
        cli.close()
        print(f"CLEANUP: {n_s} sesi + {n_p} posisi + {n_m} movement dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
