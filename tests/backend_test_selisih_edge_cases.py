#!/usr/bin/env python3
"""backend_test_selisih_edge_cases.py — Edge case & negative testing for shipment discrepancies.

Tests scenarios NOT covered by scenario_selisih_ssot.py:
- Invalid inputs (negative quantities, missing fields)
- RBAC (vendor trying to resolve CMT shorts, non-admin corrections)
- Idempotency (double complete-qc, double resolve)
- Boundary conditions (zero quantities, exact matches)
- Error messages clarity
"""
import sys
import time
from datetime import date

import requests
from pymongo import MongoClient

API = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
VENDOR_EMAIL = "ujicmt@dewiaditya.id"
VENDOR_PASS = "Dewi@123"
VENDOR_ID = "uji-vendor-cmt-ssot"
MARK = "UJITEST-EDGE"

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
S = time.strftime("%H%M%S")

env = {}
for line in open("/app/backend/.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

PASS: list[str] = []
FAIL: list[str] = []


def ok(name, detail=""):
    PASS.append(name)
    print(f"  {G}✓ {name}{X} {detail}")


def bad(name, detail=""):
    FAIL.append(name)
    print(f"  {R}✗ {name}{X} {detail}")


def check(name, cond, detail=""):
    (ok if cond else bad)(name, detail)
    return bool(cond)


TOK = ""
VTOK = ""


def H(tok=None):
    return {"Authorization": f"Bearer {tok or TOK}", "Content-Type": "application/json"}


def call(m, p, body=None, ok_codes=(200, 201), tok=None, quiet=False):
    r = requests.request(m, f"{API}{p}", headers=H(tok), json=body, timeout=180)
    try:
        d = r.json()
    except Exception:
        d = {"raw": r.text[:200]}
    if not quiet:
        tag = f"{G}{r.status_code}{X}" if r.status_code in ok_codes else f"{R}{r.status_code}{X}"
        print(f"    {tag} {m} {p}")
    return r.status_code, d


def bootstrap():
    global TOK, VTOK
    TOK = requests.post(f"{API}/api/auth/login", json=ADMIN, timeout=60).json()["token"]
    if not db.vendor_partners.find_one({"id": VENDOR_ID}):
        db.vendor_partners.insert_one({
            "id": VENDOR_ID, "code": "UJI-CMT-EDGE", "name": "CV Uji Edge",
            "partner_type": "cmt", "phone": "0800000000", "address": "Uji",
            "active": True, "notes": MARK,
        })
    u = db.users.find_one({"email": VENDOR_EMAIL})
    if not u:
        call("POST", "/api/users", {
            "name": "Vendor Uji Edge", "email": VENDOR_EMAIL, "password": VENDOR_PASS,
            "role": "cmt_vendor", "vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
        }, ok_codes=(201, 409))
    else:
        db.users.update_one({"email": VENDOR_EMAIL},
                            {"$set": {"vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
                                      "role": "cmt_vendor", "status": "active"}})
    VTOK = requests.post(f"{API}/api/auth/login",
                         json={"email": VENDOR_EMAIL, "password": VENDOR_PASS},
                         timeout=60).json().get("token", "")


def make_po(sku: str, qty: int, label: str):
    """Create PO with full flow up to vendor declaration."""
    st, po = call("POST", "/api/production-pos", {
        "po_number": f"{MARK}-{label}-{S}", "business_type": "maklon", "vendor_id": VENDOR_ID,
        "customer_name": "UJI Edge Buyer", "status": "Confirmed", "notes": MARK,
        "po_date": str(date.today()), "deadline": str(date.today()),
        "items": [{"product_name": f"Kaos Edge {label}", "sku": sku, "size": "L",
                   "color": "Hitam", "qty": qty}]}, quiet=True)
    poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})
    st, vs = call("POST", "/api/vendor-shipments", {
        "shipment_number": f"{MARK}-SJM-{label}-{S}", "vendor_id": VENDOR_ID, "po_id": po["id"],
        "po_number": po["po_number"], "shipment_date": str(date.today()),
        "shipment_type": "NORMAL", "notes": MARK,
        "items": [{"po_id": po["id"], "po_item_id": poi["id"], "sku": sku,
                   "product_name": poi.get("product_name", ""), "size": poi.get("size", ""),
                   "color": poi.get("color", ""), "qty_sent": qty}]}, quiet=True)
    call("PUT", f"/api/vendor-shipments/{vs['id']}", {"status": "Received"}, quiet=True)
    vsi = db.vendor_shipment_items.find_one({"shipment_id": vs["id"]}, {"_id": 0})
    call("POST", "/api/vendor-material-inspections", {
        "shipment_id": vs["id"], "vendor_id": VENDOR_ID, "inspection_date": str(date.today()),
        "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi["id"], "sku": sku, "ordered_qty": qty,
                   "received_qty": qty, "missing_qty": 0}]}, quiet=True)
    st, job = call("POST", "/api/production-jobs",
                   {"vendor_shipment_id": vs["id"], "vendor_id": VENDOR_ID, "po_id": po["id"]},
                   quiet=True)
    ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
    call("POST", "/api/production-progress", {"job_item_id": ji["id"], "completed_quantity": qty,
                                              "progress_date": str(date.today())}, quiet=True)
    st, d = call("POST", "/api/buyer-shipments", {
        "po_id": po["id"], "job_id": job["id"], "shipment_date": str(date.today()),
        "notes": MARK,
        "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
                   "product_name": ji.get("product_name", ""), "qty_shipped": qty}]},
        tok=VTOK, quiet=True)
    rec = db.cmt_receipts.find_one({"related_shipment_id": d.get("id")}, {"_id": 0},
                                   sort=[("created_at", -1)])
    line = db.cmt_receipt_lines.find_one({"receipt_id": rec["id"]}, {"_id": 0})
    return po, rec, line, ji


def clean():
    po_ids = [p["id"] for p in db.production_pos.find({"notes": MARK}, {"_id": 0, "id": 1})]
    n = 0
    for pid in po_ids:
        item_ids = [i["id"] for i in db.po_items.find({"po_id": pid}, {"_id": 0, "id": 1})]
        job_ids = [j["id"] for j in db.production_jobs.find({"po_id": pid}, {"_id": 0, "id": 1})]
        ji_ids = [j["id"] for j in db.production_job_items.find(
            {"po_item_id": {"$in": item_ids}}, {"_id": 0, "id": 1})]
        rc_ids = [r["id"] for r in db.cmt_receipts.find({"po_id": pid}, {"_id": 0, "id": 1})]
        bs_ids = [s["id"] for s in db.buyer_shipments.find(
            {"$or": [{"po_id": pid}, {"po_ids": pid}]}, {"_id": 0, "id": 1})]
        for coll, q in (
            ("po_items", {"po_id": pid}), ("production_jobs", {"po_id": pid}),
            ("production_job_items", {"id": {"$in": ji_ids}}),
            ("cmt_receipt_lines", {"receipt_id": {"$in": rc_ids}}),
            ("cmt_receipts", {"id": {"$in": rc_ids}}),
            ("cmt_short_shipments", {"po_id": pid}),
            ("buyer_short_records", {"po_id": pid}),
            ("buyer_shipment_items", {"shipment_id": {"$in": bs_ids}}),
            ("buyer_shipments", {"id": {"$in": bs_ids}}),
            ("vendor_shipment_items", {"po_id": pid}),
            ("vendor_shipments", {"po_id": pid}),
            ("production_pos", {"id": pid}),
        ):
            try:
                n += db[coll].delete_many(q).deleted_count
            except Exception:
                pass
    for coll in ("rahaza_fg_movements", "rahaza_stock_ledger", "rahaza_material_stock",
                 "rahaza_materials", "notifications"):
        try:
            if coll == "rahaza_materials":
                mats = [m["id"] for m in db.rahaza_materials.find(
                    {"code": {"$regex": f"^{MARK}"}}, {"_id": 0, "id": 1})]
                n += db.rahaza_material_stock.delete_many({"material_id": {"$in": mats}}).deleted_count
                n += db.rahaza_materials.delete_many({"id": {"$in": mats}}).deleted_count
            elif coll == "notifications":
                n += db.notifications.delete_many({"body": {"$regex": MARK}}).deleted_count
            else:
                n += db[coll].delete_many({"sku_code": {"$regex": f"^{MARK}"}}).deleted_count
        except Exception:
            pass
    print(f"  cleanup: {n} docs deleted")


def main():  # noqa: C901
    print(f"{C}{B}{'═' * 88}\nEDGE CASE & NEGATIVE TESTING — SHIPMENT DISCREPANCIES\n{'═' * 88}{X}")
    print(f"\n{C}0. Bootstrap{X}")
    bootstrap()

    # ═══════════════════════════════════════════════════════════════════════════
    # NEGATIVE TESTS — Invalid inputs
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}1. Invalid inputs for koreksi-hasil-qc{X}")
    sku1 = f"{MARK}-NEG1-{S}"
    po1, rec1, line1, ji1 = make_po(sku1, 50, "NEG1")
    call("PUT", f"/api/prod/cmt-receipts/{rec1['id']}/lines/{line1['id']}",
         {"qty_actual": 45, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec1['id']}/complete-qc", {}, quiet=True)

    # Missing reason
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rec1['id']}/lines/{line1['id']}/koreksi-hasil-qc",
                 {"qty_actual": 50, "reject_qty": 0}, ok_codes=(400,))
    check("1a koreksi tanpa reason ditolak 400", st == 400, f"http={st}")

    # Negative quantity
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rec1['id']}/lines/{line1['id']}/koreksi-hasil-qc",
                 {"qty_actual": -10, "reject_qty": 0, "reason": "test"}, ok_codes=(400,))
    check("1b koreksi dengan qty negatif ditolak 400", st == 400, f"http={st}")

    # Koreksi on receipt that's not done yet
    sku2 = f"{MARK}-NEG2-{S}"
    po2, rec2, line2, ji2 = make_po(sku2, 30, "NEG2")
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rec2['id']}/lines/{line2['id']}/koreksi-hasil-qc",
                 {"qty_actual": 30, "reject_qty": 0, "reason": "test"}, ok_codes=(400,))
    check("1c koreksi pada penerimaan yang belum selesai QC ditolak 400", st == 400, f"http={st}")

    # ═══════════════════════════════════════════════════════════════════════════
    # IDEMPOTENCY TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}2. Idempotency — double complete-qc{X}")
    sku3 = f"{MARK}-IDEMP1-{S}"
    po3, rec3, line3, ji3 = make_po(sku3, 40, "IDEMP1")
    call("PUT", f"/api/prod/cmt-receipts/{rec3['id']}/lines/{line3['id']}",
         {"qty_actual": 35, "reject_qty": 0}, quiet=True)
    st1, _ = call("POST", f"/api/prod/cmt-receipts/{rec3['id']}/complete-qc", {}, quiet=True)
    st2, _ = call("POST", f"/api/prod/cmt-receipts/{rec3['id']}/complete-qc", {}, quiet=True)
    check("2a complete-qc kedua kali idempoten (200 atau 400 dengan pesan jelas)",
          st2 in (200, 400), f"http={st2}")

    # Check data integrity after double call
    ji3_after = db.production_job_items.find_one({"id": ji3["id"]}, {"_id": 0})
    check("2b angka tidak dobel setelah complete-qc ganda",
          int(ji3_after.get("qty_accepted") or 0) == 35,
          f"accepted={ji3_after.get('qty_accepted')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # RBAC TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}3. RBAC — vendor tidak boleh resolve CMT short{X}")
    sku4 = f"{MARK}-RBAC1-{S}"
    po4, rec4, line4, ji4 = make_po(sku4, 60, "RBAC1")
    call("PUT", f"/api/prod/cmt-receipts/{rec4['id']}/lines/{line4['id']}",
         {"qty_actual": 50, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec4['id']}/complete-qc", {}, quiet=True)
    short4 = db.cmt_short_shipments.find_one({"receipt_line_id": line4["id"]}, {"_id": 0})

    if short4:
        st, _ = call("POST", f"/api/prod/short-shipments/{short4['id']}/resolve",
                     {"resolution": "dikirim_ulang", "notes": "vendor coba resolve"},
                     ok_codes=(403,), tok=VTOK)
        check("3a vendor tidak boleh resolve CMT short (403)", st == 403, f"http={st}")

    # ═══════════════════════════════════════════════════════════════════════════
    # BOUNDARY CONDITIONS
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}4. Boundary — qty_actual = qty_claimed (tidak ada selisih){X}")
    sku5 = f"{MARK}-BOUND1-{S}"
    po5, rec5, line5, ji5 = make_po(sku5, 25, "BOUND1")
    call("PUT", f"/api/prod/cmt-receipts/{rec5['id']}/lines/{line5['id']}",
         {"qty_actual": 25, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec5['id']}/complete-qc", {}, quiet=True)
    ji5_after = db.production_job_items.find_one({"id": ji5["id"]}, {"_id": 0})
    short5 = db.cmt_short_shipments.find_one({"receipt_line_id": line5["id"]}, {"_id": 0})
    check("4a tidak ada dokumen selisih bila qty sama persis",
          not short5 and int(ji5_after.get("qty_short_open") or 0) == 0,
          f"short_doc={bool(short5)} qty_short_open={ji5_after.get('qty_short_open')}")

    print(f"\n{C}5. Boundary — qty_actual = 0 (semua tidak sampai){X}")
    sku6 = f"{MARK}-BOUND2-{S}"
    po6, rec6, line6, ji6 = make_po(sku6, 20, "BOUND2")
    call("PUT", f"/api/prod/cmt-receipts/{rec6['id']}/lines/{line6['id']}",
         {"qty_actual": 0, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec6['id']}/complete-qc", {}, quiet=True)
    ji6_after = db.production_job_items.find_one({"id": ji6["id"]}, {"_id": 0})
    short6 = db.cmt_short_shipments.find_one({"receipt_line_id": line6["id"]}, {"_id": 0})
    check("5a selisih 100% (qty_actual=0) tercatat dengan benar",
          bool(short6) and int((short6 or {}).get("qty_short") or 0) == 20
          and int(ji6_after.get("qty_short_open") or 0) == 20,
          f"short_qty={(short6 or {}).get('qty_short')} ledger_short={ji6_after.get('qty_short_open')}")

    # ═══════════════════════════════════════════════════════════════════════════
    # BUYER SHORT EDGE CASES
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}6. Buyer short — invalid resolution{X}")
    sku7 = f"{MARK}-BSHORT1-{S}"
    po7, rec7, line7, ji7 = make_po(sku7, 30, "BSHORT1")
    call("PUT", f"/api/prod/cmt-receipts/{rec7['id']}/lines/{line7['id']}",
         {"qty_actual": 30, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec7['id']}/complete-qc", {}, quiet=True)

    # Ship to buyer
    src_ids = [rec7["id"]]
    st, bs = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": src_ids, "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji7["po_item_id"], "job_item_id": ji7["id"], "sku": sku7,
                   "qty_shipped": 30}]}, quiet=True)
    bsi = db.buyer_shipment_items.find_one({"shipment_id": bs.get("id")}, {"_id": 0})
    call("PUT", f"/api/buyer-shipment-items/{bsi['id']}/received",
         {"qty_received": 25, "reason": "test"}, quiet=True)
    bshort = db.buyer_short_records.find_one({"shipment_item_id": bsi["id"]}, {"_id": 0})

    if bshort:
        st, _ = call("POST", f"/api/buyer-shorts/{bshort['id']}/resolve",
                     {"resolution": "invalid_option", "notes": "test"}, ok_codes=(400,))
        check("6a resolve buyer short dengan resolution tidak valid ditolak 400", st == 400, f"http={st}")

        # Try to resolve already resolved
        call("POST", f"/api/buyer-shorts/{bshort['id']}/resolve",
             {"resolution": "tanggungan_da", "notes": "test"}, quiet=True)
        st, _ = call("POST", f"/api/buyer-shorts/{bshort['id']}/resolve",
                     {"resolution": "tanggungan_cmt", "notes": "test kedua"}, ok_codes=(400,))
        check("6b resolve buyer short yang sudah resolved ditolak 400", st == 400, f"http={st}")

    # ═══════════════════════════════════════════════════════════════════════════
    # DELETE BUYER SHIPMENT (should restore FG stock)
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}7. DELETE buyer shipment harus kembalikan stok FG{X}")
    sku8 = f"{MARK}-DEL1-{S}"
    po8, rec8, line8, ji8 = make_po(sku8, 15, "DEL1")
    call("PUT", f"/api/prod/cmt-receipts/{rec8['id']}/lines/{line8['id']}",
         {"qty_actual": 15, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec8['id']}/complete-qc", {}, quiet=True)

    # Check FG stock
    mat8 = db.rahaza_materials.find_one({"code": sku8}, {"_id": 0, "id": 1})
    stok_before = sum(float(x.get("qty") or 0) for x in
                      db.rahaza_material_stock.find({"material_id": mat8["id"]}, {"_id": 0, "qty": 1}))

    st, bs8 = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": [rec8["id"]], "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji8["po_item_id"], "job_item_id": ji8["id"], "sku": sku8,
                   "qty_shipped": 15}]}, quiet=True)

    stok_after_ship = sum(float(x.get("qty") or 0) for x in
                          db.rahaza_material_stock.find({"material_id": mat8["id"]}, {"_id": 0, "qty": 1}))

    # Delete shipment (superadmin only)
    st, _ = call("DELETE", f"/api/buyer-shipments/{bs8.get('id')}", ok_codes=(200, 204))
    stok_after_delete = sum(float(x.get("qty") or 0) for x in
                            db.rahaza_material_stock.find({"material_id": mat8["id"]}, {"_id": 0, "qty": 1}))

    check("7a DELETE buyer shipment mengembalikan stok FG",
          stok_before == 15 and stok_after_ship == 0 and stok_after_delete == 15,
          f"before={stok_before} after_ship={stok_after_ship} after_delete={stok_after_delete}")

    # ═══════════════════════════════════════════════════════════════════════════
    # OVER-SHIP VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{C}8. Over-ship validation — kirim melebihi stok FG{X}")
    sku9 = f"{MARK}-OVER1-{S}"
    po9, rec9, line9, ji9 = make_po(sku9, 10, "OVER1")
    call("PUT", f"/api/prod/cmt-receipts/{rec9['id']}/lines/{line9['id']}",
         {"qty_actual": 10, "reject_qty": 0}, quiet=True)
    call("POST", f"/api/prod/cmt-receipts/{rec9['id']}/complete-qc", {}, quiet=True)

    # Try to ship 15 (more than available 10)
    st, resp = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": [rec9["id"]], "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji9["po_item_id"], "job_item_id": ji9["id"], "sku": sku9,
                   "qty_shipped": 15}]}, ok_codes=(400,))
    # Check for clear error message (Indonesian or English)
    resp_str = str(resp).lower()
    has_clear_msg = any(word in resp_str for word in ["melebihi", "maksimal", "stok", "stock", 
                                                        "insufficient", "exceed", "available", "capacity"])
    check("8a kirim melebihi stok FG ditolak 400 dengan pesan jelas",
          st == 400 and has_clear_msg,
          f"http={st}")

    return finish()


def finish():
    print(f"\n{B}{'─' * 88}{X}")
    print(f"  PASS {len(PASS)} · FAIL {len(FAIL)}")
    if FAIL:
        print(f"  {R}{B}MERAH — {len(FAIL)} edge cases gagal:{X}")
        for f in FAIL:
            print(f"    {R}· {f}{X}")
        return 1
    print(f"  {G}{B}HIJAU — semua edge cases terpenuhi{X}")
    return 0


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
        sys.exit(0)
    rc = 1
    try:
        rc = main()
    finally:
        if "--keep" not in sys.argv:
            print()
            clean()
    sys.exit(rc)
