"""
E2E API-level POC test — Alur CMT Vendor / Sub-contract (Maklon).

Bagian A — Dispatch (kirim komponen ke vendor CMT):
  login
  -> buat dispatch (draft, lines komponen)            [POST /api/wms/cmt-dispatches]
  -> execute dispatch -> dispatched + auto SJ-CMT     [POST /api/wms/cmt-dispatches/{id}/dispatch]
  -> return-line -> fully_returned                    [POST /api/wms/cmt-dispatches/{id}/return-line]
Bagian B — Receipt + QC (terima hasil jadi dari vendor):
  -> buat receipt (Draft)                             [POST /api/prod/cmt-receipts]
  -> tambah line (qty_expected)                       [POST /api/prod/cmt-receipts/{id}/lines]
  -> hitung fisik (qty_actual) [QC count]             [PUT  /api/prod/cmt-receipts/{id}/lines/{lid}]
  -> submit -> Submitted                              [POST /api/prod/cmt-receipts/{id}/submit]
  -> approve -> Approved (posting FG)                 [POST /api/prod/cmt-receipts/{id}/approve]
  -> jalur reject: receipt lain -> Rejected           [POST /api/prod/cmt-receipts/{id}/reject]
Guards:
  -> execute dispatch dua kali ditolak (400, hanya draft)
  -> return-line pada draft ditolak (400)
  -> submit receipt tanpa qty_actual ditolak (400)
  -> submit receipt dua kali ditolak (400)
Self-cleanup (hard): dispatches + delivery_notes(SJ-CMT) + receipts + lines + FG stock + fg_movements.
"""
import sys
import requests

BASE = "http://localhost:8001"
S = requests.Session()
CMT = "E2E CMT Vendor"
SKU = "E2ECMTSKU"
st = {"dispatches": [], "receipts": [], "sj_numbers": []}


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


def create_dispatch(cmt=CMT):
    body = {
        "wo_number": "E2E-WO-CMT", "cmt_name": cmt, "cmt_address": "Jl. E2E No.1",
        "notes": "E2E CMT dispatch",
        "lines": [{"material_code": "E2E-KAIN", "material_name": "E2E Kain Katun",
                   "roll_nos": ["R1", "R2"], "qty": 200, "unit": "meter", "unit_cost": 25000,
                   "remarks": "komponen potong"}],
    }
    r = S.post(f"{BASE}/api/wms/cmt-dispatches", json=body)
    assert r.status_code == 200, f"create dispatch {r.status_code}: {r.text}"
    d = r.json()["dispatch"]
    st["dispatches"].append(d["id"])
    return d


def main():
    login()

    # ══ Bagian A: Dispatch ═══════════════════════════════════════════════════
    d = create_dispatch()
    assert d["status"] == "draft" and len(d["lines"]) == 1, f"dispatch draft {d}"
    print(f"PASS buat dispatch {d['dispatch_no']} status=draft (1 komponen)")

    r = S.post(f"{BASE}/api/wms/cmt-dispatches/{d['id']}/dispatch",
               json={"shipper_name": "E2E Kurir", "vehicle_no": "B1234E2E"})
    assert r.status_code == 200 and r.json().get("sj_number"), f"execute dispatch {r.status_code}: {r.text}"
    st["sj_numbers"].append(r.json()["sj_number"])
    assert r.json()["dispatch"]["status"] == "dispatched", "dispatch bukan dispatched"
    print(f"PASS kirim ke vendor -> status=dispatched + auto SJ-CMT {r.json()['sj_number']}")

    rg = S.post(f"{BASE}/api/wms/cmt-dispatches/{d['id']}/dispatch", json={})
    assert rg.status_code >= 400, f"expected reject re-dispatch got {rg.status_code}"
    print("PASS guard: execute dispatch dua kali ditolak (400)")

    r = S.post(f"{BASE}/api/wms/cmt-dispatches/{d['id']}/return-line",
               json={"material_code": "E2E-KAIN", "qty_returned": 200, "unit": "meter"})
    assert r.status_code == 200 and r.json()["dispatch"]["status"] == "fully_returned", f"return-line {r.text}"
    print("PASS terima kembali (return-line) -> status=fully_returned")

    d2 = create_dispatch()  # fresh draft untuk guard return-line
    rg = S.post(f"{BASE}/api/wms/cmt-dispatches/{d2['id']}/return-line",
                json={"material_code": "E2E-KAIN", "qty_returned": 10})
    assert rg.status_code >= 400, f"expected reject return-line on draft got {rg.status_code}"
    print("PASS guard: return-line pada draft ditolak (400)")

    # ══ Bagian B: Receipt + QC ═══════════════════════════════════════════════
    r = S.post(f"{BASE}/api/prod/cmt-receipts",
               json={"cmt_name": CMT, "wo_number": "E2E-WO-CMT", "delivery_note": "SJ-VENDOR-E2E",
                     "notes": "E2E terima hasil jadi"})
    assert r.status_code in (200, 201), f"create receipt {r.status_code}: {r.text}"
    rc = r.json()
    st["receipts"].append(rc["id"])
    assert rc["status"] == "Draft", f"receipt status {rc['status']}"
    print(f"PASS buat receipt {rc['receipt_code']} status=Draft")

    r = S.post(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/lines",
               json={"sku_code": SKU, "product_name": "E2E Kemeja Jadi", "color": "Biru",
                     "size": "M", "qty_expected": 100})
    assert r.status_code in (200, 201), f"add line {r.status_code}: {r.text}"
    line = r.json()
    print("PASS tambah line (qty_expected=100, qty_actual belum dihitung)")

    rg = S.post(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/submit", json={})
    assert rg.status_code >= 400, f"expected reject submit tanpa qty_actual got {rg.status_code}"
    print("PASS guard: submit receipt tanpa qty_actual ditolak (400)")

    r = S.put(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/lines/{line['id']}",
              json={"qty_actual": 95})
    assert r.status_code == 200, f"count qty_actual {r.status_code}: {r.text}"
    print("PASS QC count qty_actual=95 (dari 100 dikirim, 5 kurang)")

    r = S.post(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/submit", json={})
    assert r.status_code == 200 and r.json()["status"] == "Submitted", f"submit {r.text}"
    print("PASS submit -> status=Submitted")

    rg = S.post(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/submit", json={})
    assert rg.status_code >= 400, f"expected reject double submit got {rg.status_code}"
    print("PASS guard: submit receipt dua kali ditolak (400)")

    r = S.post(f"{BASE}/api/prod/cmt-receipts/{rc['id']}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "Approved", f"approve {r.text}"
    print("PASS approve (QC lolos) -> status=Approved + posting FG")

    # verifikasi posting FG
    cli, db = _mongo()
    fg = db.rahaza_material_stock.find_one({"material_id": f"FG-{SKU}"}, {"_id": 0})
    cli.close()
    assert fg and fg.get("quantity") == 95, f"FG stock expected qty 95 got {fg.get('quantity') if fg else None}"
    print("PASS posting FG: rahaza_material_stock FG-E2ECMTSKU qty=95 (fg_internal, cv_da)")

    # jalur reject
    r = S.post(f"{BASE}/api/prod/cmt-receipts",
               json={"cmt_name": CMT, "wo_number": "E2E-WO-CMT", "notes": "E2E reject path"})
    rc2 = r.json(); st["receipts"].append(rc2["id"])
    S.post(f"{BASE}/api/prod/cmt-receipts/{rc2['id']}/lines",
           json={"sku_code": SKU + "R", "product_name": "E2E Reject", "qty_expected": 10})
    r = S.post(f"{BASE}/api/prod/cmt-receipts/{rc2['id']}/reject", json={"reason": "kualitas jahitan buruk"})
    assert r.status_code == 200 and r.json()["status"] == "Rejected", f"reject {r.text}"
    print("PASS jalur reject: receipt -> status=Rejected")

    # sanity summary
    assert S.get(f"{BASE}/api/prod/cmt-receipts/summary").status_code == 200, "summary gagal"
    assert S.get(f"{BASE}/api/wms/cmt-dispatches").status_code == 200, "list dispatch gagal"
    print("PASS summary receipt + list dispatch 200")

    print("\n=== CMT VENDOR / MAKLON FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        dn = 0
        for did in st["dispatches"]:
            db.wh_cmt_dispatches.delete_one({"id": did})
        dn = db.wh_cmt_dispatches.delete_many({"cmt_name": CMT}).deleted_count
        sj = db.wh_delivery_notes.delete_many({"recipient_name": CMT}).deleted_count
        for rid in st["receipts"]:
            db.cmt_receipt_lines.delete_many({"receipt_id": rid})
            db.cmt_receipts.delete_one({"id": rid})
        rc = db.cmt_receipts.delete_many({"cmt_name": CMT}).deleted_count
        fg = db.rahaza_material_stock.delete_many({"material_id": {"$regex": f"FG-{SKU}"}}).deleted_count
        mv = db.rahaza_fg_movements.delete_many({"ref_number": {"$regex": "CMT-RCV"}, "notes": {"$regex": "E2E|UNIFIED"}}).deleted_count
        # sapu movement E2E berdasar sku
        mv += db.rahaza_fg_movements.delete_many({"sku_code": {"$regex": SKU}}).deleted_count
        cli.close()
        print(f"CLEANUP: dispatch({dn}) + SJ-CMT({sj}) + receipt({rc}) + FG({fg}) + movement({mv}) dihapus (DB pristine)")
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
