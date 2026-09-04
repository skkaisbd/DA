#!/usr/bin/env python3
"""
Demo data Produksi & Maklon — TERHUBUNG end-to-end (bukan asal seed).

Memakai FUNGSI ENGINE ASLI aplikasi (explode BOM, create_internal_job,
insert_wip_mirror, sync_po_to_maklon_finance) sehingga status & dokumen
identik dengan input manual di UI. Master data (klien/vendor/produk/material)
dibuat realistis. Actor/created_by memakai nama staf, bukan 'seed'.

Menghasilkan (idempoten — hapus demo lama dulu):
  PRODUKSI INTERNAL (business_type='internal'):
    - PO-INT-DEMO-1  Draft
    - PO-INT-DEMO-2  In Production (job + material issued + progress + dispatch #1 parsial) -> Surat Jalan Buyer
    - PO-INT-DEMO-3  SELESAI (produksi penuh + dispatch penuh + PO Closed) -> Surat Jalan Buyer
  MAKLON (business_type='maklon'):
    - PO-MK-DEMO-1   Draft
    - PO-MK-DEMO-2   In Production (kirim material vendor + inspeksi + job + progress + dispatch #1) -> Surat Jalan Material + Buyer + AR draft
    - PO-MK-DEMO-3   SELESAI (kirim material + produksi penuh + dispatch penuh + PO Closed + Invoice Maklon terbit)
  VENDOR PORTAL: user cmtvendor@dewiaditya.id / Dewi@123 (role cmt_vendor) melihat shipment & job miliknya.

Jalankan: python3 /app/tests/seed_demo_produksi_maklon.py
"""
import os, sys, json as _json, asyncio, requests
sys.path.insert(0, "/app/backend"); os.chdir("/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from database import get_db
from core.helpers import new_id, now
from auth import hash_password
from cascade_delete import cascade_delete_po
from routes.production_maklon_bridge import sync_po_to_maklon_finance
from routes.production_internal_adapter import (
    explode_po_accessories_from_bom, create_internal_job,
    resolve_operator_process, insert_wip_mirror,
)

BASE = "http://localhost:8001/api"
ADMIN_PROD = "Andi Pratama (Admin Produksi)"
GUDANG = "Siti (Gudang)"
QC = "Dewi (QC)"

# ── Fixed IDs (idempoten) ────────────────────────────────────────────────────
CL = {"aruna": "demo-cl-aruna", "bumi": "demo-cl-bumi", "langit": "demo-cl-langit"}
VN = {"jmc": "demo-vn-jmc", "rpk": "demo-vn-rpk"}
INT_POS = ["po-int-demo-1", "po-int-demo-2", "po-int-demo-3"]
MK_POS = ["po-mk-demo-1", "po-mk-demo-2", "po-mk-demo-3"]
MODEL = "demo-model-ts"; BOM = "demo-bom-ts"; EMP = "demo-op-1"; LOC = "demo-loc-1"
MAT_YARN = "YRN-DA-CTN30"; MAT_ACC = "ACC-DA-LBL"

log = lambda m: print(f"  {m}")


def admin_token():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def login_token(email, password="Dewi@123"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    log("Cleanup demo lama...")
    for pid in INT_POS + MK_POS:
        po = await db.production_pos.find_one({"id": pid}, {"id": 1})
        if po:
            for j in await db.production_jobs.find({"po_id": pid}, {"id": 1}).to_list(None):
                await db.rahaza_material_issues.delete_many({"job_id": j["id"]})
                await db.rahaza_wip_events.delete_many({"job_id": j["id"]})
                await db.rahaza_hpp_snapshots.delete_many({"job_id": j["id"]})
                await db.production_job_items.delete_many({"job_id": j["id"]})
                await db.production_progress.delete_many({"job_id": j["id"]})
                await db.production_jobs.delete_one({"id": j["id"]})
            try:
                await cascade_delete_po(pid)
            except Exception as e:
                log(f"cascade {pid}: {e}")
        await db.dewi_maklon_pos.delete_one({"id": pid})
        await db.rahaza_ar_invoices.delete_many({"linked_maklon_po_id": pid})
        await db.dewi_maklon_invoices.delete_many({"order_id": pid})
        await db.vendor_shipments.delete_many({"po_id": pid})
        await db.buyer_shipments.delete_many({"po_id": pid})
    # Vendor portal jobs/progress milik partner demo (JMC/RPK)
    for vid in VN.values():
        for vj in await db.vendor_jobs.find({"partner_id": vid}, {"id": 1}).to_list(None):
            await db.vendor_progress_reports.delete_many({"job_id": vj["id"]})
        await db.vendor_jobs.delete_many({"partner_id": vid})
        await db.vendor_progress_reports.delete_many({"partner_id": vid})


async def seed_masters(db, t):
    log("Master: klien, vendor, user portal, model/BOM/material internal...")
    clients = [
        (CL["aruna"], "ARNA", "PT Aruna Activewear", "Bu Sari", "0812-1111-2222", "Bandung"),
        (CL["bumi"], "BUMI", "CV Bumi Sportwear", "Pak Deni", "0813-2222-3333", "Bekasi"),
        (CL["langit"], "LNGT", "PT Langit Apparel", "Bu Maya", "0814-3333-4444", "Solo"),
    ]
    for cid, code, name, cn, cp, addr in clients:
        await db.dewi_maklon_clients.update_one({"id": cid}, {"$set": {
            "id": cid, "code": code, "name": name, "contact_name": cn, "contact_phone": cp,
            "address": addr, "notes": "Klien demo maklon", "active": True,
            "created_at": t, "updated_at": t}}, upsert=True)
    vendors = [
        (VN["jmc"], "JMC", "CV Jahit Mitra CMT", "Pak Budi", "0813-3333-4444", "Sragen"),
        (VN["rpk"], "RPK", "CV Rapi Konveksi", "Pak Joko", "0815-5555-6666", "Klaten"),
    ]
    for vid, code, name, cn, cp, addr in vendors:
        await db.vendor_partners.update_one({"id": vid}, {"$set": {
            "id": vid, "code": code, "name": name, "garment_name": name,
            "contact_name": cn, "contact_phone": cp, "address": addr,
            "notes": "Vendor CMT demo", "active": True, "created_at": t, "updated_at": t}}, upsert=True)

    # Users portal (vendor CMT + klien) — idempoten
    portal_users = [
        ("cmtvendor@dewiaditya.id", "CV Jahit Mitra CMT (Vendor)", "cmt_vendor", {"cmt_vendor_id": VN["jmc"]}),
        ("cmtvendor2@dewiaditya.id", "CV Rapi Konveksi (Vendor)", "cmt_vendor", {"cmt_vendor_id": VN["rpk"]}),
        ("klienmaklon@dewiaditya.id", "PT Aruna Activewear (Klien)", "klien_maklon", {"buyer_id": CL["aruna"]}),
    ]
    for email, name, role, extra in portal_users:
        ex = await db.users.find_one({"email": email})
        if ex:
            await db.users.update_one({"email": email}, {"$set": {"role": role, **extra, "status": "active", "updated_at": t}})
        else:
            await db.users.insert_one({"id": new_id(), "name": name, "email": email,
                "password": hash_password("Dewi@123"), "role": role, "status": "active",
                **extra, "created_at": t, "updated_at": t})

    # Internal masters
    await db.rahaza_locations.update_one({"id": LOC}, {"$set": {
        "id": LOC, "code": "GDG-UTAMA", "name": "Gudang Utama", "active": True, "created_at": t}}, upsert=True)
    sizes = await db.rahaza_sizes.find({"active": {"$ne": False}}, {"_id": 0}).sort("code", 1).to_list(1)
    if not sizes:
        await db.rahaza_sizes.update_one({"id": "demo-size-m"}, {"$set": {"id": "demo-size-m", "code": "M", "name": "M", "active": True, "created_at": t}}, upsert=True)
        sizes = [{"id": "demo-size-m", "code": "M"}]
    size_id, size_code = sizes[0]["id"], sizes[0].get("code", "M")
    proc = await db.rahaza_processes.find_one({"active": {"$ne": False}}, {"_id": 0})
    if not proc:
        await db.rahaza_processes.update_one({"id": "demo-proc-sew"}, {"$set": {"id": "demo-proc-sew", "code": "SEW", "name": "Sewing", "active": True, "created_at": t}}, upsert=True)
        proc = {"id": "demo-proc-sew"}
    await db.rahaza_models.update_one({"id": MODEL}, {"$set": {
        "id": MODEL, "code": "DA-TS01", "name": "Kaos Basic Dewi Aditya",
        "bundle_size": 30, "active": True, "created_by": ADMIN_PROD, "created_at": t}}, upsert=True)
    await db.rahaza_boms.update_one({"id": BOM}, {"$set": {
        "id": BOM, "model_id": MODEL, "size_id": size_id, "version": 1, "is_active": True, "active": True,
        "yarn_materials": [{"name": "Benang Cotton 30s", "code": MAT_YARN, "yarn_type": "cotton", "qty_kg": 0.25}],
        "accessory_materials": [{"name": "Label Woven DA", "code": MAT_ACC, "qty": 1, "unit": "pcs"}],
        "created_by": ADMIN_PROD, "created_at": t}}, upsert=True)
    for code, name, mtype, unit, cost, stock in [
        (MAT_YARN, "Benang Cotton 30s", "yarn", "kg", 20000, 800.0),
        (MAT_ACC, "Label Woven DA", "accessory", "pcs", 500, 5000.0),
    ]:
        m = await db.rahaza_materials.find_one({"code": code}, {"_id": 0})
        if not m:
            m = {"id": new_id(), "code": code, "name": name, "type": mtype, "unit": unit,
                 "yarn_type": "cotton" if mtype == "yarn" else "", "color": "", "min_stock": 0,
                 "unit_cost": cost, "active": True, "created_at": t, "updated_at": t}
            await db.rahaza_materials.insert_one(m)
        else:
            await db.rahaza_materials.update_one({"id": m["id"]}, {"$set": {"unit_cost": cost, "active": True}})
        await db.rahaza_material_stock.update_one(
            {"material_id": m["id"], "location_id": LOC},
            {"$set": {"qty": stock, "updated_at": t}, "$setOnInsert": {"id": new_id()}}, upsert=True)
    await db.rahaza_employees.update_one({"id": EMP}, {"$set": {
        "id": EMP, "name": "Operator Borongan Demo", "employee_code": "OP-DEMO-1",
        "employment_type": "daily", "active": True, "created_at": t}}, upsert=True)
    await db.rahaza_payroll_profiles.update_one({"employee_id": EMP}, {"$set": {
        "pay_scheme": "pcs", "base_rate": 500, "pcs_process_rates": [], "active": True},
        "$setOnInsert": {"id": new_id(), "employee_id": EMP, "created_at": t}}, upsert=True)
    if not await db.rahaza_costing_settings.find_one({"id": "GLOBAL"}):
        await db.rahaza_costing_settings.insert_one({"id": "GLOBAL", "overhead_rate_per_pcs": 1000,
            "default_yarn_cost_per_kg": 0, "default_accessory_cost_per_unit": 0, "labor_rate_fallback_per_pcs": 0})
    return size_id, size_code, proc["id"]


async def seed_internal(db, t, size_id, size_code, proc_id):
    log("PRODUKSI INTERNAL: 3 PO (draft / in-prod / selesai)...")
    user = {"id": "demo-admin", "name": ADMIN_PROD}

    def int_po(pid, number, status, notes):
        return {"id": pid, "po_number": number, "customer_name": "Gudang FG Sendiri",
                "buyer_id": None, "vendor_id": None, "vendor_name": "Produksi Internal",
                "po_date": t, "deadline": None, "delivery_deadline": None, "status": status,
                "notes": notes, "business_type": "internal", "created_by": ADMIN_PROD,
                "created_at": t, "updated_at": t}

    def int_item(pid, number, qty, serial):
        return {"id": f"{pid}-i1", "po_id": pid, "po_number": number, "product_id": None,
                "product_name": "Kaos Basic Dewi Aditya", "variant_id": None,
                "model_id": MODEL, "size_id": size_id, "size": size_code, "color": "Hitam",
                "sku": f"DA-TS01-{size_code}", "qty": qty, "serial_number": serial,
                "selling_price_snapshot": 0.0, "cmt_price_snapshot": 0.0, "created_at": t}

    async def full_flow(pid, number, qty, serial, produce, dispatch, close):
        job_r = await create_internal_job(db, {"po_id": pid}, user)
        job = _json.loads(job_r.body) if hasattr(job_r, "body") else job_r
        ji = job["items"][0]
        mi = job.get("material_issue_draft") or {}
        if mi.get("id"):
            for it in mi.get("items", []):
                await db.rahaza_material_stock.update_one(
                    {"material_id": it["material_id"], "location_id": LOC},
                    {"$inc": {"qty": -float(it["qty_required"])}, "$set": {"updated_at": t}})
            await db.rahaza_material_issues.update_one({"id": mi["id"]}, {"$set": {
                "status": "issued", "issued_at": t, "issued_by": GUDANG,
                "items": [{**it, "qty_issued": it["qty_required"], "location_id": LOC} for it in mi.get("items", [])],
                "updated_at": t}})
        ctx = await resolve_operator_process(db, EMP, proc_id)
        prog_id = new_id()
        await db.production_progress.insert_one({
            "id": prog_id, "job_id": job["id"], "job_item_id": ji["id"], "sku": f"DA-TS01-{size_code}",
            "product_name": "Kaos Basic Dewi Aditya", "size": size_code, "color": "Hitam",
            "progress_date": t, "completed_quantity": produce, "operator_id": EMP, "process_id": proc_id,
            "notes": "Progress produksi", "recorded_by": ADMIN_PROD, "created_at": t})
        await insert_wip_mirror(db, job, ji, produce, ctx, user, progress_id=prog_id)
        await db.production_job_items.update_one({"id": ji["id"]}, {"$set": {"produced_qty": produce}})
        # Buyer dispatch (Surat Jalan Buyer)
        bs_id = f"{pid}-bs1"
        ship_status = "Shipped" if close else "Partially Shipped"
        await db.buyer_shipments.insert_one({
            "id": bs_id, "shipment_number": f"SJ-BYR-{number}", "vendor_id": None,
            "vendor_name": "Produksi Internal", "po_id": pid, "po_number": number,
            "customer_name": "Gudang FG Sendiri", "job_id": job["id"], "ship_status": ship_status,
            "business_type": "internal", "last_dispatch": t, "last_dispatch_seq": 1,
            "notes": "Dispatch barang jadi ke gudang FG", "created_by": GUDANG,
            "created_at": t, "updated_at": t})
        await db.buyer_shipment_items.insert_one({
            "id": new_id(), "shipment_id": bs_id, "dispatch_seq": 1, "dispatch_date": t,
            "po_item_id": f"{pid}-i1", "job_item_id": ji["id"], "job_id": job["id"],
            "product_name": "Kaos Basic Dewi Aditya", "serial_number": serial, "size": size_code,
            "color": "Hitam", "sku": f"DA-TS01-{size_code}", "ordered_qty": qty,
            "qty_shipped": dispatch, "created_at": t})
        if close:
            await db.production_pos.update_one({"id": pid}, {"$set": {"status": "Closed", "closed_at": t, "updated_at": t}})
            await db.production_jobs.update_one({"id": job["id"]}, {"$set": {"status": "Completed", "updated_at": t}})
        return job.get("job_number")

    # PO-1 Draft
    await db.production_pos.insert_one(int_po(INT_POS[0], "PO-INT-DEMO-1", "Draft", "Menunggu konfirmasi produksi"))
    await db.po_items.insert_one(int_item(INT_POS[0], "PO-INT-DEMO-1", 200, "SN-INT1-A"))
    await explode_po_accessories_from_bom(db, INT_POS[0])
    log("  PO-INT-DEMO-1 (Draft) ok")

    # PO-2 In Production (parsial)
    await db.production_pos.insert_one(int_po(INT_POS[1], "PO-INT-DEMO-2", "Confirmed", "Sedang produksi"))
    await db.po_items.insert_one(int_item(INT_POS[1], "PO-INT-DEMO-2", 200, "SN-INT2-A"))
    await explode_po_accessories_from_bom(db, INT_POS[1])
    j2 = await full_flow(INT_POS[1], "PO-INT-DEMO-2", 200, "SN-INT2-A", produce=120, dispatch=80, close=False)
    log(f"  PO-INT-DEMO-2 (In Production, job {j2}, produce 120, dispatch 80) ok")

    # PO-3 Selesai (penuh)
    await db.production_pos.insert_one(int_po(INT_POS[2], "PO-INT-DEMO-3", "Confirmed", "Selesai & barang terkirim"))
    await db.po_items.insert_one(int_item(INT_POS[2], "PO-INT-DEMO-3", 100, "SN-INT3-A"))
    await explode_po_accessories_from_bom(db, INT_POS[2])
    j3 = await full_flow(INT_POS[2], "PO-INT-DEMO-3", 100, "SN-INT3-A", produce=100, dispatch=100, close=True)
    log(f"  PO-INT-DEMO-3 (SELESAI/Closed, job {j3}, produce 100, dispatch 100) ok")


async def seed_maklon(db, t, admin_tok):
    log("MAKLON: 3 PO (draft / in-prod / selesai)...")
    user = {"id": "demo-admin", "name": ADMIN_PROD}
    products = [
        ("Jaket Hoodie Aruna", "ARN-HD", "Navy", 18000),
        ("Kaos Polo Bumi", "BUM-PL", "Putih", 12000),
        ("Celana Jogger Langit", "LNG-JG", "Hitam", 15000),
    ]
    clients = [(CL["aruna"], "PT Aruna Activewear"), (CL["bumi"], "CV Bumi Sportwear"), (CL["langit"], "PT Langit Apparel")]
    vendors = [(VN["jmc"], "CV Jahit Mitra CMT"), (VN["rpk"], "CV Rapi Konveksi"), (VN["jmc"], "CV Jahit Mitra CMT")]

    def mk_po(pid, number, status, cid, cname, vid, vname, notes):
        return {"id": pid, "po_number": number, "customer_name": cname, "buyer_id": cid,
                "vendor_id": vid, "vendor_name": vname, "po_date": t, "deadline": None,
                "delivery_deadline": None, "status": status, "notes": notes,
                "business_type": "maklon", "created_by": ADMIN_PROD, "created_at": t, "updated_at": t}

    def mk_item(pid, number, iid, pname, sku, size, color, serial, qty, cmt):
        return {"id": iid, "po_id": pid, "po_number": number, "product_id": None,
                "product_name": pname, "variant_id": None, "size": size, "color": color,
                "sku": sku, "qty": qty, "serial_number": serial, "selling_price_snapshot": 0.0,
                "cmt_price_snapshot": float(cmt), "created_at": t}

    async def mk_full_flow(pid, number, cid, cname, vid, vname, pname, sku_base, color, cmt, qtys, produce, dispatch, close):
        # PO + items
        item_ids = [f"{pid}-i{k+1}" for k in range(len(qtys))]
        for k, (iid, (size, qty)) in enumerate(zip(item_ids, qtys)):
            await db.po_items.insert_one(mk_item(pid, number, iid, pname, f"{sku_base}-{size}", size, color, f"SN-{pid[-3:]}-{k+1}", qty, cmt))
        # Vendor shipment (Surat Jalan Material) — kirim material ke vendor CMT
        ship_id = f"{pid}-vs1"
        total_recv = sum(q for _, q in qtys)
        await db.vendor_shipments.insert_one({
            "id": ship_id, "shipment_number": f"SJ-MTR-{number}", "delivery_note_number": f"DN-{number}",
            "vendor_id": vid, "vendor_name": vname, "po_id": pid, "po_number": number,
            "shipment_date": t, "shipment_type": "NORMAL", "parent_shipment_id": None,
            "status": "Received", "inspection_status": "Inspected", "total_received": total_recv,
            "total_missing": 0, "inspected_at": t, "business_type": "maklon",
            "notes": "Kirim material potongan ke vendor jahit", "created_by": GUDANG,
            "created_at": t, "updated_at": t})
        vsi_ids = []
        for k, (iid, (size, qty)) in enumerate(zip(item_ids, qtys)):
            vsi = f"{ship_id}-l{k+1}"; vsi_ids.append(vsi)
            await db.vendor_shipment_items.insert_one({
                "id": vsi, "shipment_id": ship_id, "shipment_number": f"SJ-MTR-{number}",
                "po_id": pid, "po_number": number, "po_item_id": iid, "source_po_item_id": iid,
                "product_name": pname, "sku": f"{sku_base}-{size}", "size": size, "color": color,
                "serial_number": f"SN-{pid[-3:]}-{k+1}", "qty_sent": qty, "ordered_qty": qty,
                "shipment_type": "NORMAL", "parent_shipment_id": None, "created_at": t})
        # Inspeksi material
        insp_id = f"{pid}-insp1"
        await db.vendor_material_inspections.insert_one({
            "id": insp_id, "shipment_id": ship_id, "shipment_number": f"SJ-MTR-{number}",
            "vendor_id": vid, "vendor_name": vname, "inspection_date": t, "total_received": total_recv,
            "total_missing": 0, "total_acc_received": 0, "total_acc_missing": 0,
            "overall_notes": "Material diterima vendor lengkap", "status": "Submitted",
            "submitted_by": QC, "created_at": t, "updated_at": t})
        for k, (vsi, (size, qty)) in enumerate(zip(vsi_ids, qtys)):
            await db.vendor_material_inspection_items.insert_one({
                "id": new_id(), "inspection_id": insp_id, "item_type": "material",
                "shipment_item_id": vsi, "sku": f"{sku_base}-{size}", "product_name": pname,
                "size": size, "color": color, "ordered_qty": qty, "received_qty": qty,
                "missing_qty": 0, "condition_notes": "", "created_at": t})
        # Production job + items + progress
        job_id = f"{pid}-job1"
        await db.production_jobs.insert_one({
            "id": job_id, "job_number": f"JOB-{number}", "parent_job_id": None, "parent_job_number": None,
            "vendor_id": vid, "vendor_name": vname, "po_id": pid, "po_number": number,
            "customer_name": cname, "vendor_shipment_id": ship_id, "shipment_number": f"SJ-MTR-{number}",
            "shipment_type": "NORMAL", "deadline": None, "delivery_deadline": None,
            "status": "Completed" if close else "In Progress", "business_type": "maklon",
            "notes": "Job jahit vendor CMT", "created_by": ADMIN_PROD, "created_at": t, "updated_at": t})
        ji_ids = []
        for k, (iid, vsi, (size, qty)) in enumerate(zip(item_ids, vsi_ids, qtys)):
            jid = f"{job_id}-ji{k+1}"; ji_ids.append(jid)
            prod_k = qty if close else int(qty * produce // 100)
            await db.production_job_items.insert_one({
                "id": jid, "job_id": job_id, "job_number": f"JOB-{number}", "po_item_id": iid,
                "vendor_shipment_item_id": vsi, "product_name": pname, "sku": f"{sku_base}-{size}",
                "size": size, "color": color, "serial_number": f"SN-{pid[-3:]}-{k+1}",
                "ordered_qty": qty, "shipment_qty": qty, "available_qty": qty, "produced_qty": prod_k,
                "created_at": t})
            await db.production_progress.insert_one({
                "id": new_id(), "job_id": job_id, "job_item_id": jid, "sku": f"{sku_base}-{size}",
                "product_name": pname, "size": size, "color": color, "progress_date": t,
                "completed_quantity": prod_k, "notes": "Progress jahit", "recorded_by": ADMIN_PROD, "created_at": t})
        # Buyer dispatch (Surat Jalan Buyer)
        bs_id = f"{pid}-bs1"
        await db.buyer_shipments.insert_one({
            "id": bs_id, "shipment_number": f"SJ-BYR-{number}", "vendor_id": vid, "vendor_name": vname,
            "po_id": pid, "po_number": number, "customer_name": cname, "job_id": job_id,
            "ship_status": "Shipped" if close else "Partially Shipped", "business_type": "maklon",
            "last_dispatch": t, "last_dispatch_seq": 1, "notes": "Dispatch barang jadi ke klien",
            "created_by": GUDANG, "created_at": t, "updated_at": t})
        for k, (iid, jid, (size, qty)) in enumerate(zip(item_ids, ji_ids, qtys)):
            disp_k = qty if close else int(qty * dispatch // 100)
            await db.buyer_shipment_items.insert_one({
                "id": new_id(), "shipment_id": bs_id, "dispatch_seq": 1, "dispatch_date": t,
                "po_item_id": iid, "job_item_id": jid, "job_id": job_id, "product_name": pname,
                "serial_number": f"SN-{pid[-3:]}-{k+1}", "size": size, "color": color,
                "sku": f"{sku_base}-{size}", "ordered_qty": qty, "qty_shipped": disp_k, "created_at": t})
        # Finance mirror + AR draft
        await sync_po_to_maklon_finance(db, pid, user)
        if close:
            await db.production_pos.update_one({"id": pid}, {"$set": {"status": "Closed", "closed_at": t, "updated_at": t}})

    # PO-1 Draft
    await db.production_pos.insert_one(mk_po(MK_POS[0], "PO-MK-DEMO-1", "Draft", CL["aruna"], "PT Aruna Activewear", VN["jmc"], "CV Jahit Mitra CMT", "Menunggu konfirmasi klien"))
    for k, (size, qty) in enumerate([("M", 150), ("L", 100)]):
        await db.po_items.insert_one(mk_item(MK_POS[0], "PO-MK-DEMO-1", f"{MK_POS[0]}-i{k+1}", "Jaket Hoodie Aruna", f"ARN-HD-{size}", size, "Navy", f"SN-MK1-{k+1}", qty, 18000))
    for acc, code, qn in [("Zipper YKK 60cm", "ZIP-60", 250), ("Label Woven Aruna", "LBL-ARN", 250)]:
        await db.po_accessories.insert_one({"id": new_id(), "po_id": MK_POS[0], "accessory_id": None,
            "accessory_name": acc, "accessory_code": code, "qty_needed": qn, "unit": "pcs", "notes": "", "created_at": t})
    log("  PO-MK-DEMO-1 (Draft) ok")

    # PO-2 In Production
    await db.production_pos.insert_one(mk_po(MK_POS[1], "PO-MK-DEMO-2", "In Production", CL["bumi"], "CV Bumi Sportwear", VN["rpk"], "CV Rapi Konveksi", "Sedang dijahit vendor"))
    await mk_full_flow(MK_POS[1], "PO-MK-DEMO-2", CL["bumi"], "CV Bumi Sportwear", VN["rpk"], "CV Rapi Konveksi",
                       "Kaos Polo Bumi", "BUM-PL", "Putih", 12000, [("M", 100), ("L", 50)], produce=80, dispatch=50, close=False)
    log("  PO-MK-DEMO-2 (In Production + Surat Jalan Material + Buyer + AR draft) ok")

    # PO-3 Selesai + Invoice
    await db.production_pos.insert_one(mk_po(MK_POS[2], "PO-MK-DEMO-3", "In Production", CL["langit"], "PT Langit Apparel", VN["jmc"], "CV Jahit Mitra CMT", "Selesai & siap ditagih"))
    await mk_full_flow(MK_POS[2], "PO-MK-DEMO-3", CL["langit"], "PT Langit Apparel", VN["jmc"], "CV Jahit Mitra CMT",
                       "Celana Jogger Langit", "LNG-JG", "Hitam", 15000, [("M", 120), ("L", 80)], produce=100, dispatch=100, close=True)
    # Invoice Maklon (printable) via API
    r = requests.post(f"{BASE}/dewi/maklon/invoices/generate", headers={"Authorization": f"Bearer {admin_tok}"},
                      json={"order_id": MK_POS[2]}, timeout=20)
    if r.status_code == 200:
        log(f"  PO-MK-DEMO-3 (SELESAI) + Invoice Maklon {r.json().get('invoice_number')} ok")
    else:
        log(f"  PO-MK-DEMO-3 SELESAI ok — invoice generate HTTP {r.status_code}: {r.text[:160]}")


async def seed_vendor_jobs(db, admin_tok):
    """Portal Vendor CMT (self-service) — assign job via API admin lalu vendor submit progress.
    Alur asli: admin POST /vendor-portal/jobs -> vendor login -> POST /my-jobs/{id}/progress.
    JMC (cmtvendor@) : 1 job Selesai (PO-MK-DEMO-3) + 1 job Belum Mulai (PO-MK-DEMO-1)
    RPK (cmtvendor2@): 1 job Berjalan (PO-MK-DEMO-2)
    """
    log("Portal Vendor CMT: assign vendor_jobs via API + progress vendor...")
    AH = {"Authorization": f"Bearer {admin_tok}"}

    def create_job(partner_id, title, qty, wo_number, notes):
        r = requests.post(f"{BASE}/vendor-portal/jobs", headers=AH, json={
            "title": title, "partner_id": partner_id, "wo_number": wo_number,
            "qty_target": qty, "process": "SEWING", "notes": notes}, timeout=20)
        r.raise_for_status()
        return r.json()

    def submit_progress(vendor_tok, job_id, qty_done, qty_reject=0, notes="Progress harian"):
        r = requests.post(f"{BASE}/vendor-portal/my-jobs/{job_id}/progress",
                          headers={"Authorization": f"Bearer {vendor_tok}"},
                          json={"qty_done": qty_done, "qty_reject": qty_reject, "notes": notes}, timeout=20)
        r.raise_for_status()
        return r.json()

    # JMC vendor
    j_done = create_job(VN["jmc"], "Jahit Celana Jogger Langit — 200 pcs", 200, "PO-MK-DEMO-3", "Job maklon PT Langit Apparel")
    create_job(VN["jmc"], "Jahit Jaket Hoodie Aruna — 250 pcs", 250, "PO-MK-DEMO-1", "Job maklon PT Aruna Activewear (menunggu mulai)")
    tok_jmc = login_token("cmtvendor@dewiaditya.id")
    submit_progress(tok_jmc, j_done["id"], 200, 0, "Selesai jahit penuh")  # -> status done

    # RPK vendor
    j_prog = create_job(VN["rpk"], "Jahit Kaos Polo Bumi — 150 pcs", 150, "PO-MK-DEMO-2", "Job maklon CV Bumi Sportwear")
    tok_rpk = login_token("cmtvendor2@dewiaditya.id")
    submit_progress(tok_rpk, j_prog["id"], 120, 3, "Progress jahit sebagian")  # -> status in_progress

    log("   vendor_jobs JMC: 1 Selesai + 1 Belum Mulai; RPK: 1 Berjalan")


async def verify(db, admin_tok):
    log("Verifikasi dokumen (surat) bisa dicetak...")
    H = {"Authorization": f"Bearer {admin_tok}"}
    checks = []
    # Surat Jalan Material (vendor shipment) untuk maklon in-prod & selesai
    for pid in (MK_POS[1], MK_POS[2]):
        vs = await db.vendor_shipments.find_one({"po_id": pid}, {"id": 1})
        if vs:
            r = requests.get(f"{BASE}/export-pdf?type=vendor-shipment&id={vs['id']}", headers=H, timeout=25)
            checks.append((f"SJ Material {pid}", r.status_code == 200 and r.content[:4] == b"%PDF"))
    # Surat Jalan Buyer (buyer shipment) — internal & maklon
    for pid in (INT_POS[1], INT_POS[2], MK_POS[1], MK_POS[2]):
        bs = await db.buyer_shipments.find_one({"po_id": pid}, {"id": 1})
        if bs:
            r = requests.get(f"{BASE}/export-pdf?type=buyer-shipment&id={bs['id']}", headers=H, timeout=25)
            checks.append((f"SJ Buyer {pid}", r.status_code == 200 and r.content[:4] == b"%PDF"))
    # Invoice Maklon
    inv = await db.dewi_maklon_invoices.find_one({"order_id": MK_POS[2]}, {"id": 1, "invoice_number": 1})
    if inv:
        r = requests.get(f"{BASE}/dewi/maklon/invoices/{inv['id']}/pdf", headers=H, timeout=25)
        checks.append((f"Invoice Maklon {inv.get('invoice_number')}", r.status_code == 200 and r.content[:4] == b"%PDF"))
    ok = 0
    for name, passed in checks:
        log(("   OK  " if passed else "   XX  ") + name)
        ok += 1 if passed else 0
    return ok, len(checks)


async def vendor_portal_check(db):
    log("Vendor Portal: data untuk cmtvendor@dewiaditya.id (vendor JMC)...")
    for vid, label in [(VN["jmc"], "JMC"), (VN["rpk"], "RPK")]:
        vs = await db.vendor_shipments.count_documents({"vendor_id": vid})
        jb = await db.production_jobs.count_documents({"vendor_id": vid})
        bs = await db.buyer_shipments.count_documents({"vendor_id": vid})
        vj = await db.vendor_jobs.count_documents({"partner_id": vid})
        vj_done = await db.vendor_jobs.count_documents({"partner_id": vid, "status": "done"})
        vj_prog = await db.vendor_jobs.count_documents({"partner_id": vid, "status": "in_progress"})
        vj_open = await db.vendor_jobs.count_documents({"partner_id": vid, "status": "open"})
        log(f"   Vendor {label}: {vs} SJ material, {jb} job engine, {bs} SJ buyer | Portal Vendor: {vj} job (open {vj_open}/berjalan {vj_prog}/selesai {vj_done})")


async def adopt_existing_masters(db):
    """Hindari tabrakan unique index `code`.

    Seeder lain (`POST /api/seed/maklon-full`, dijalankan `scripts/bootstrap.sh`)
    lebih dulu membuat klien/vendor dengan KODE yang sama tapi id berbeda
    (mis. `mk-client-demo-1` code=ARNA). Upsert by-id lalu meledak
    `E11000 duplicate key ... index: code_1`. Jadi: kalau kode sudah ada,
    ADOPSI id yang ada — jangan bikin kembar.
    """
    global MODEL, BOM, EMP, LOC
    pairs = [
        ("dewi_maklon_clients", CL, {"aruna": "ARNA", "bumi": "BUMI", "langit": "LNGT"}),
        ("vendor_partners", VN, {"jmc": "JMC", "rpk": "RPK"}),
    ]
    for coll, holder, codes in pairs:
        for key, code in codes.items():
            ex = await db[coll].find_one({"code": code}, {"id": 1})
            if ex and ex.get("id") and ex["id"] != holder[key]:
                log(f"adopsi {coll} code={code} → id={ex['id']} (sebelumnya {holder[key]})")
                holder[key] = ex["id"]
    # master ber-id konstanta (model / lokasi / karyawan) — kode unik juga
    singles = [
        ("rahaza_models", {"code": "DA-TS01"}, "MODEL", MODEL),
        ("rahaza_locations", {"code": "GDG-UTAMA"}, "LOC", LOC),
        ("rahaza_employees", {"employee_code": "OP-DEMO-1"}, "EMP", EMP),
    ]
    resolved = {}
    for coll, q, name, cur in singles:
        ex = await db[coll].find_one(q, {"id": 1})
        resolved[name] = ex["id"] if (ex and ex.get("id")) else cur
        if resolved[name] != cur:
            log(f"adopsi {coll} {q} → id={resolved[name]} (sebelumnya {cur})")
    MODEL, LOC, EMP = resolved["MODEL"], resolved["LOC"], resolved["EMP"]
    # BOM punya unique index (model,size,color,active) → adopsi BOM aktif model itu
    exb = await db.rahaza_boms.find_one({"model_id": MODEL, "is_active": True}, {"id": 1}) \
        or await db.rahaza_boms.find_one({"model_id": MODEL}, {"id": 1})
    if exb and exb.get("id") and exb["id"] != BOM:
        log(f"adopsi rahaza_boms model={MODEL} → id={exb['id']} (sebelumnya {BOM})")
        BOM = exb["id"]


async def main():
    db = get_db()
    t = now()
    admin_tok = admin_token()
    await adopt_existing_masters(db)
    await cleanup(db)
    size_id, size_code, proc_id = await seed_masters(db, t)
    await seed_internal(db, t, size_id, size_code, proc_id)
    await seed_maklon(db, t, admin_tok)
    await seed_vendor_jobs(db, admin_tok)
    ok, total = await verify(db, admin_tok)
    await vendor_portal_check(db)
    print(f"\n==== DEMO SEED SELESAI — dokumen tercetak {ok}/{total} ====")
    print("Login vendor portal: cmtvendor@dewiaditya.id / Dewi@123 (JMC)")
    print("Login vendor portal: cmtvendor2@dewiaditya.id / Dewi@123 (RPK)")
    print("Login klien maklon : klienmaklon@dewiaditya.id / Dewi@123")


if __name__ == "__main__":
    asyncio.run(main())
