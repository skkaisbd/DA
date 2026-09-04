"""
PT Rahaza ERP — Shipments / Surat Jalan (Phase 14.1)

Koleksi:
  - rahaza_shipments {id, shipment_number, order_id, order_number_snapshot,
                       customer_id, customer_name_snapshot, customer_address_snapshot,
                       shipment_date, driver_name, vehicle_number, notes,
                       status: 'draft'|'dispatched'|'delivered'|'cancelled',
                       dispatched_at, delivered_at, created_at, created_by,
                       items: [{wo_id, wo_number, model_code, model_name, size_code, qty}],
                       auto_invoice_id, auto_invoice_number}

Lifecycle:
  draft → dispatched (terima konfirmasi kurir keluar)
         → delivered (POD diterima)
  draft → cancelled (batal)

Fitur utama:
  1. CRUD shipment
  2. Status transition dengan audit + (saat dispatched) auto-generate AR invoice draft dari Order
  3. PDF Surat Jalan (A5 printable)
  4. Filter + search via DataTable v2 (client-side)

Integrasi:
  - Saat POST /shipments/{id}/dispatch:
      * update status → dispatched
      * log_audit
      * auto create AR invoice draft (Phase 14.2) bila order.auto_invoice_on_ship=true
        atau default True untuk sekarang. Prevent duplicate via field order.auto_invoiced
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_audit import log_audit
from routes.rahaza_notifications import publish_notification
from routes.rahaza_posting import post_cogs_shipment
from datetime import datetime, timezone
from io import BytesIO
import logging
import uuid

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rahaza/shipments", tags=["Rahaza Shipments (DEPRECATED)"])

# ──────────────────────────────────────────────────────────────────────────────
# DEPRECATION NOTICE (P2 Consolidation #12, Session #11.8)
# ──────────────────────────────────────────────────────────────────────────────
# This module's collection `rahaza_shipments` has been superseded by
# `wh_delivery_notes` (Customer Shipping SSOT). Endpoints below remain
# functional for backward compatibility (per TD-008 rule: 1-week monitor
# before deletion), but new integrations should target:
#
#     /api/wms/delivery-notes/*  →  wh_delivery_notes collection
#
# A migration script is available at:
#     scripts/migrate_shipping_consolidation.py
#
# To dry-run / migrate existing docs:
#     python scripts/migrate_shipping_consolidation.py --dry-run
#     python scripts/migrate_shipping_consolidation.py
# ──────────────────────────────────────────────────────────────────────────────
log.info(
    "[DEPRECATION] /api/rahaza/shipments/* is DEPRECATED — superseded by "
    "/api/wms/delivery-notes/* (wh_delivery_notes SSOT). See P2 Consolidation #12."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


async def _gen_shipment_number(db) -> str:
    today = _today()
    prefix = f"SJ-{today.strftime('%Y%m%d')}"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    return await gen_prefixed_number(db, "rahaza_shipments", "shipment_number", f"{prefix}-", 3)


# ─── CRUD ────────────────────────────────────────────────────────────────────
@router.get("")
async def list_shipments(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    q = {}
    if sp.get("status"):
        q["status"] = sp["status"]
    if sp.get("order_id"):
        q["order_id"] = sp["order_id"]
    if sp.get("customer_id"):
        q["customer_id"] = sp["customer_id"]
    # Dual-mode: paginated or full list
    if sp.get("page") or sp.get("limit"):
        from routes.shared import get_pagination_params, paginated_response
        page, limit, skip = get_pagination_params(request, default_limit=50)
        total = await db.rahaza_shipments.count_documents(q)
        rows = await db.rahaza_shipments.find(q, {"_id": 0}).sort("shipment_date", -1).skip(skip).limit(limit).to_list(limit)
        return paginated_response(rows, total, page, limit)
    rows = await db.rahaza_shipments.find(q, {"_id": 0}).sort("shipment_date", -1).to_list(500)
    return rows


@router.get("/{sid}")
async def get_shipment(sid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Shipment tidak ditemukan")
    return doc


@router.post("")
async def create_shipment(body: dict, request: Request):
    user = await require_auth(request)
    db = get_db()

    order_id = body.get("order_id")
    if not order_id:
        raise HTTPException(400, "order_id wajib diisi")
    order = await db.rahaza_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order tidak ditemukan")

    items = body.get("items") or []
    if not items:
        raise HTTPException(400, "Minimal 1 item (WO) dikirim")

    # Snapshot WO items — batch fetch all WOs in single query
    wo_ids = [it.get("wo_id") for it in items if it.get("wo_id")]
    wo_map = {}
    if wo_ids:
        async for w in db.rahaza_work_orders.find({"id": {"$in": wo_ids}}, {"_id": 0}):
            wo_map[w["id"]] = w
    enriched = []
    for it in items:
        wo_id = it.get("wo_id")
        qty = float(it.get("qty") or 0)
        if not wo_id or qty <= 0:
            raise HTTPException(400, "Item shipment tidak valid (wo_id & qty wajib)")
        wo = wo_map.get(wo_id)
        if not wo:
            raise HTTPException(404, f"WO {wo_id} tidak ditemukan")
        if wo.get("order_id") != order_id:
            raise HTTPException(400, f"WO {wo.get('wo_number')} bukan milik order ini")
        enriched.append({
            "wo_id": wo_id,
            "wo_number": wo.get("wo_number"),
            "model_code": wo.get("model_code_snapshot") or wo.get("model_code"),
            "model_name": wo.get("model_name_snapshot") or wo.get("model_name"),
            "size_code":  wo.get("size_code"),
            "qty": qty,
            "unit_price": float(it.get("unit_price") or 0),
        })

    customer = None
    if order.get("customer_id"):
        customer = await db.rahaza_customers.find_one({"id": order["customer_id"]}, {"_id": 0})

    shp_num = await _gen_shipment_number(db)
    doc = {
        "id": str(uuid.uuid4()),
        "shipment_number": shp_num,
        "order_id": order_id,
        "order_number_snapshot": order.get("order_number"),
        "customer_id": order.get("customer_id"),
        "customer_name_snapshot": (customer or {}).get("name") or order.get("customer_name_snapshot"),
        "customer_address_snapshot": (customer or {}).get("address"),
        "shipment_date": body.get("shipment_date") or _today().isoformat(),
        "driver_name": body.get("driver_name") or "",
        "vehicle_number": body.get("vehicle_number") or "",
        "notes": body.get("notes") or "",
        "status": "draft",
        "items": enriched,
        "total_qty": sum(i["qty"] for i in enriched),
        "created_at": _now(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.rahaza_shipments.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.shipment", shp_num)
    await log_audit(db, entity_type="rahaza_shipment", entity_id=doc["id"], action="create",
                    before=None, after={k: v for k, v in doc.items() if k != "_id"},
                    user=user, request=request)
    return serialize_doc(doc)


@router.put("/{sid}")
async def update_shipment(sid: str, body: dict, request: Request):
    user = await require_auth(request)
    db = get_db()
    shp = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not shp:
        raise HTTPException(404, "Shipment tidak ditemukan")
    if shp["status"] != "draft":
        raise HTTPException(400, "Hanya shipment draft yang bisa diedit")
    allowed = {k: v for k, v in body.items() if k in (
        "shipment_date", "driver_name", "vehicle_number", "notes", "items"
    )}
    # Re-validate items jika ada
    if "items" in allowed:
        items = allowed["items"] or []
        # Batch fetch all WOs in single query
        wo_ids = [it.get("wo_id") for it in items if it.get("wo_id")]
        wo_map = {}
        if wo_ids:
            async for w in db.rahaza_work_orders.find({"id": {"$in": wo_ids}}, {"_id": 0}):
                wo_map[w["id"]] = w
        enriched = []
        for it in items:
            wo = wo_map.get(it.get("wo_id"))
            if not wo:
                continue
            enriched.append({
                "wo_id": wo["id"],
                "wo_number": wo.get("wo_number"),
                "model_code": wo.get("model_code_snapshot") or wo.get("model_code"),
                "model_name": wo.get("model_name_snapshot") or wo.get("model_name"),
                "size_code": wo.get("size_code"),
                "qty": float(it.get("qty") or 0),
                "unit_price": float(it.get("unit_price") or 0),
            })
        allowed["items"] = enriched
        allowed["total_qty"] = sum(i["qty"] for i in enriched)
    allowed["updated_at"] = _now()
    await db.rahaza_shipments.update_one({"id": sid}, {"$set": allowed})
    out = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    await log_audit(db, entity_type="rahaza_shipment", entity_id=sid, action="update",
                    before=shp, after=out, user=user, request=request)
    return serialize_doc(out)


@router.delete("/{sid}")
async def delete_shipment(sid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    shp = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not shp:
        raise HTTPException(404, "Shipment tidak ditemukan")
    if shp["status"] != "draft":
        raise HTTPException(400, "Hanya shipment draft yang bisa dihapus")
    await db.rahaza_shipments.delete_one({"id": sid})
    await log_audit(db, entity_type="rahaza_shipment", entity_id=sid, action="delete",
                    before=shp, after=None, user=user, request=request)
    return {"deleted": sid}


# ─── STATUS TRANSITIONS ──────────────────────────────────────────────────────
ALLOWED = {
    "draft":      {"dispatched", "cancelled"},
    "dispatched": {"delivered", "cancelled"},
    "delivered":  set(),
    "cancelled":  set(),
}


@router.post("/{sid}/status")
async def change_status(sid: str, body: dict, request: Request):
    user = await require_auth(request)
    db = get_db()
    shp = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not shp:
        raise HTTPException(404, "Shipment tidak ditemukan")
    new_status = body.get("status")
    if new_status not in ALLOWED.get(shp["status"], set()):
        raise HTTPException(400, f"Transisi {shp['status']} → {new_status} tidak diizinkan")

    upd = {"status": new_status, "updated_at": _now()}
    if new_status == "dispatched":
        upd["dispatched_at"] = _now()
    if new_status == "delivered":
        upd["delivered_at"] = _now()

    await db.rahaza_shipments.update_one({"id": sid}, {"$set": upd})

    await log_audit(db, entity_type="rahaza_shipment", entity_id=sid, action="status_change",
                    before={"status": shp["status"]}, after={"status": new_status},
                    user=user, request=request)

    # ─── Phase 14.2 — Auto AR Invoice Draft saat dispatch ────────────────────
    auto_invoice = None
    posting_result = None
    if new_status == "dispatched":
        try:
            auto_invoice = await _create_ar_invoice_from_shipment(db, shp, user, request)
            if auto_invoice:
                await db.rahaza_shipments.update_one(
                    {"id": sid},
                    {"$set": {
                        "auto_invoice_id": auto_invoice["id"],
                        "auto_invoice_number": auto_invoice["invoice_number"],
                    }}
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Auto AR invoice draft failed: {e}")

        # ─── F3 — Auto-post COGS JE (Dr COGS / Cr FG Inventory) ──────────
        try:
            shp_refresh = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
            posting_result = await post_cogs_shipment(db, shp_refresh, user)
        except Exception as e:
            log.exception("COGS shipment auto-post failed")
            posting_result = {"ok": False, "error": str(e)}

        # ─── FG Outbound → PENDING OUTBOUND (WMS, butuh Scan-Out) ─────────
        try:
            ship_items = shp.get("items", [])
            valid_items = [(it.get("wo_id"), int(it.get("qty", 0)))
                            for it in ship_items if it.get("wo_id") and int(it.get("qty", 0)) > 0]
            if valid_items:
                wo_ids = list({wo_id for wo_id, _ in valid_items})
                wo_map = {}
                async for w in db.rahaza_work_orders.find({"id": {"$in": wo_ids}}, {"_id": 0}):
                    wo_map[w["id"]] = w
                m_ids = list({wo_map[wid].get("model_id") for wid in wo_map if wo_map[wid].get("model_id")})
                s_ids = list({wo_map[wid].get("size_id") for wid in wo_map if wo_map[wid].get("size_id")})
                model_map = {}
                size_map = {}
                if m_ids:
                    async for m in db.rahaza_models.find({"id": {"$in": m_ids}}, {"_id": 0}):
                        model_map[m["id"]] = m
                if s_ids:
                    async for sz in db.rahaza_sizes.find({"id": {"$in": s_ids}}, {"_id": 0}):
                        size_map[sz["id"]] = sz

                # INV-9 FIX: resolve FG KANONIK via variant SSOT (code == variant.sku,
                # format {MODEL}-{WARNA}-{SIZE}, TANPA prefix 'FG-'). Jika tak ter-resolusi
                # → catat eksplisit (bukan skip diam) agar terlihat & bisa ditindaklanjuti.
                from utils.variant_ssot import resolve_variant, ensure_fg_material
                from routes.wms_receiving import helper_create_pending_outbound_fg

                qty_by_wo = {}
                for wo_id, q in valid_items:
                    qty_by_wo[wo_id] = qty_by_wo.get(wo_id, 0) + q

                unresolved = []
                for wo_id, qty_shipped in qty_by_wo.items():
                    wo_doc = wo_map.get(wo_id)
                    if not wo_doc:
                        unresolved.append({"wo_id": wo_id, "reason": "WO tidak ditemukan"})
                        continue
                    # 1) resolve varian kanonik dari hint yang tersedia di WO
                    variant = await resolve_variant(
                        db,
                        variant_id=wo_doc.get("variant_id") or wo_doc.get("rahaza_variant_id"),
                        sku=wo_doc.get("sku"),
                        model_id=wo_doc.get("model_id"),
                        color_id=wo_doc.get("color_id"),
                        size_id=wo_doc.get("size_id"),
                    )
                    # 2) fallback: cocokkan varian TUNGGAL berdasar (model, size) bila warna tak diketahui
                    if not variant and wo_doc.get("model_id") and wo_doc.get("size_id"):
                        cand = await db.rahaza_model_variants.find(
                            {"model_id": wo_doc["model_id"], "size_id": wo_doc["size_id"]}, {"_id": 0}
                        ).to_list(10)
                        if len(cand) == 1:
                            variant = cand[0]
                        elif len(cand) > 1:
                            unresolved.append({"wo_id": wo_id, "wo_number": wo_doc.get("wo_number"),
                                               "reason": f"warna ambigu: {len(cand)} varian utk model+size — WO tidak menyimpan warna"})
                            continue
                    if not variant:
                        unresolved.append({"wo_id": wo_id, "wo_number": wo_doc.get("wo_number"),
                                           "reason": "varian/FG kanonik tidak ter-resolusi (model/size/warna)"})
                        continue
                    fg = await ensure_fg_material(db, variant, user=user)
                    if not fg:
                        unresolved.append({"wo_id": wo_id, "wo_number": wo_doc.get("wo_number"),
                                           "reason": "ensure_fg_material mengembalikan kosong"})
                        continue
                    await helper_create_pending_outbound_fg(
                        db,
                        material_id=fg["id"],
                        material_code=fg["code"],
                        material_name=fg.get("name", fg["code"]),
                        qty=float(qty_shipped),
                        unit="pcs",
                        source_type="shipment",
                        source_id=sid,
                        source_ref=shp.get("shipment_number", ""),
                        notes=f"Dispatch {shp.get('shipment_number','')} (WO {wo_doc.get('wo_number','')})",
                        created_by="shipment_portal",
                    )
                    log.info(f"Pending OUTBOUND FG {qty_shipped} pcs for {fg['code']} (Shipment {shp.get('shipment_number')})")

                if unresolved:
                    log.error(
                        "[INV-9] Shipment %s: %d item FG TIDAK ter-resolusi ke stok kanonik → outbound dilewati. Detail: %s",
                        shp.get("shipment_number"), len(unresolved), unresolved,
                    )
                    await db.rahaza_shipments.update_one(
                        {"id": sid}, {"$set": {"fg_outbound_unresolved": unresolved}}
                    )
        except Exception as e:
            log.warning(f"FG pending outbound creation failed: {e}")

    # Notify
    await publish_notification(
        db,
        type_="shipment_status",
        severity="success" if new_status in ("dispatched", "delivered") else "info",
        title=f"Shipment {shp['shipment_number']}: {new_status}",
        message=f"Order {shp.get('order_number_snapshot', '')} · {shp.get('total_qty', 0)} pcs"
                + (f" → AR draft {auto_invoice['invoice_number']}" if auto_invoice else ""),
        link_module="fin-ar-invoices" if auto_invoice else None,
        link_id=auto_invoice["id"] if auto_invoice else None,
        target_roles=["superadmin", "finance", "production_manager"],
        dedup_key=f"ship_status::{sid}::{new_status}",
    )

    return {
        "status": new_status,
        "shipment_id": sid,
        "auto_invoice_id": auto_invoice["id"] if auto_invoice else None,
        "auto_invoice_number": auto_invoice["invoice_number"] if auto_invoice else None,
        "cogs_posting_result": posting_result,
    }


@router.post("/{sid}/post-cogs")
async def retry_post_cogs(sid: str, request: Request):
    """F3: manual retry post COGS JE for shipment (idempotent)."""
    user = await require_auth(request)
    db = get_db()
    shp = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not shp:
        raise HTTPException(404, "Shipment tidak ditemukan")
    if shp.get("status") not in ("dispatched", "delivered"):
        raise HTTPException(400, "Hanya shipment dispatched/delivered yang bisa di-post COGS.")
    result = await post_cogs_shipment(db, shp, user)
    out = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    out["_posting_result"] = result
    return serialize_doc(out)


# ─── AR INVOICE AUTO-DRAFT ──────────────────────────────────────────────────
async def _gen_ar_invoice_number(db) -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    from utils.counters import gen_prefixed_number
    today = _today()
    return await gen_prefixed_number(
        db, "rahaza_ar_invoices", "invoice_number", f"INV-{today.strftime('%Y%m%d')}-", 3)


async def _create_ar_invoice_from_shipment(db, shp: dict, user: dict, request):
    """
    Phase 14.2 — Generate AR Invoice draft otomatis dari Shipment.
    Tidak duplicate: cek field shp['auto_invoice_id'] dulu.
    """
    if shp.get("auto_invoice_id"):
        return None

    items = shp.get("items") or []
    if not items:
        return None

    # Total = sum (qty × unit_price); bila unit_price 0 semuanya, tetap buat draft (user bisa isi nanti).
    total = 0.0
    invoice_items = []
    for it in items:
        up = float(it.get("unit_price") or 0)
        qty = float(it.get("qty") or 0)
        amount = qty * up
        total += amount
        invoice_items.append({
            "description": f"{it.get('model_name', '')} · {it.get('size_code', '')} ({it.get('wo_number', '')})",
            "qty": qty,
            "unit_price": up,
            "amount": amount,
        })

    inv_num = await _gen_ar_invoice_number(db)
    inv = {
        "id": str(uuid.uuid4()),
        "invoice_number": inv_num,
        "customer_id": shp.get("customer_id"),
        "customer_name": shp.get("customer_name_snapshot"),
        "customer_address": shp.get("customer_address_snapshot"),
        "order_id": shp.get("order_id"),
        "order_number": shp.get("order_number_snapshot"),
        "shipment_id": shp.get("id"),
        "shipment_number": shp.get("shipment_number"),
        "issue_date": _today().isoformat(),
        "due_date": _today().isoformat(),  # default sama; user edit sesuai TOP customer
        "items": invoice_items,
        "subtotal": total,
        "tax": 0,
        "total": total,
        "paid": 0,
        "balance": total,
        "status": "draft",
        "notes": f"Auto-draft dari Shipment {shp.get('shipment_number')}",
        "auto_generated": True,
        "created_at": _now(),
        "created_by": user.get("name") or user.get("email"),
    }
    await db.rahaza_ar_invoices.insert_one(dict(inv))
    await log_audit(db, entity_type="rahaza_ar_invoice", entity_id=inv["id"], action="auto_create",
                    before=None, after={k: v for k, v in inv.items() if k != "_id"},
                    user=user, request=request)
    return inv


# ─── PDF SURAT JALAN ─────────────────────────────────────────────────────────
@router.get("/{sid}/pdf")
async def shipment_pdf(sid: str, request: Request):
    await require_auth(request)
    db = get_db()
    shp = await db.rahaza_shipments.find_one({"id": sid}, {"_id": 0})
    if not shp:
        raise HTTPException(404, "Shipment tidak ditemukan")

    # Load company info
    company = await db.company_settings.find_one({}, {"_id": 0}) or {}

    pdf_bytes = _build_surat_jalan_pdf(shp, company)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="surat-jalan-{shp["shipment_number"]}.pdf"'},
    )


def _build_surat_jalan_pdf(shp: dict, company: dict) -> bytes:
    """Build Surat Jalan PDF (A5 portrait)."""
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rcanvas

    buf = BytesIO()
    w, h = A5  # 148 × 210 mm
    c = rcanvas.Canvas(buf, pagesize=A5)

    # ── Header ────────────────────────────────
    y = h - 12 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(10 * mm, y, (company.get("name") or "PT Rahaza Garment").upper())
    y -= 4 * mm
    c.setFont("Helvetica", 8)
    if company.get("address"):
        c.drawString(10 * mm, y, str(company["address"])[:80])
        y -= 3.5 * mm
    if company.get("phone") or company.get("email"):
        c.drawString(10 * mm, y, f"Telp: {company.get('phone', '-')} · {company.get('email', '')}")
        y -= 3.5 * mm

    # Garis pemisah
    y -= 1 * mm
    c.line(10 * mm, y, w - 10 * mm, y)
    y -= 5 * mm

    # ── Title ─────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, y, "SURAT JALAN")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, y, f"No: {shp['shipment_number']}")
    y -= 6 * mm

    # ── Metadata 2 kolom ──────────────────────
    c.setFont("Helvetica", 9)
    left_x = 10 * mm
    right_x = w / 2 + 2 * mm

    def row(label, val, lx, ly):
        c.setFont("Helvetica", 8)
        c.drawString(lx, ly, label)
        c.setFont("Helvetica", 9)
        c.drawString(lx, ly - 4 * mm, str(val) if val else "-")

    row("Tanggal Kirim", shp.get("shipment_date"), left_x, y)
    row("Kendaraan", shp.get("vehicle_number"), right_x, y)
    y -= 10 * mm
    row("Pengemudi", shp.get("driver_name"), left_x, y)
    row("Order #", shp.get("order_number_snapshot"), right_x, y)
    y -= 10 * mm

    # ── Kepada ────────────────────────────────
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left_x, y, "Kepada Yth:")
    y -= 4 * mm
    c.setFont("Helvetica", 9)
    c.drawString(left_x, y, shp.get("customer_name_snapshot") or "-")
    y -= 4 * mm
    if shp.get("customer_address_snapshot"):
        addr = str(shp["customer_address_snapshot"])[:100]
        c.setFont("Helvetica", 8)
        c.drawString(left_x, y, addr)
        y -= 4 * mm
    y -= 2 * mm

    # ── Items table ───────────────────────────
    c.setFont("Helvetica-Bold", 8)
    c.drawString(left_x, y, "No")
    c.drawString(left_x + 10 * mm, y, "Model · Size")
    c.drawString(w - 40 * mm, y, "WO")
    c.drawRightString(w - 10 * mm, y, "Qty")
    y -= 1 * mm
    c.line(10 * mm, y, w - 10 * mm, y)
    y -= 4 * mm

    c.setFont("Helvetica", 8)
    total_q = 0
    for idx, it in enumerate(shp.get("items", []), start=1):
        if y < 30 * mm:
            c.showPage()
            y = h - 15 * mm
            c.setFont("Helvetica", 8)
        q = float(it.get("qty") or 0)
        total_q += q
        c.drawString(left_x, y, str(idx))
        label = f"{it.get('model_name') or it.get('model_code', '')} · {it.get('size_code', '')}"
        c.drawString(left_x + 10 * mm, y, label[:45])
        c.drawString(w - 40 * mm, y, (it.get("wo_number") or "")[:15])
        c.drawRightString(w - 10 * mm, y, f"{q:.0f} pcs")
        y -= 4.5 * mm

    y -= 1 * mm
    c.line(10 * mm, y, w - 10 * mm, y)
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left_x + 10 * mm, y, "Total")
    c.drawRightString(w - 10 * mm, y, f"{total_q:.0f} pcs")
    y -= 8 * mm

    # ── Notes ─────────────────────────────────
    if shp.get("notes"):
        c.setFont("Helvetica", 8)
        c.drawString(left_x, y, f"Catatan: {str(shp['notes'])[:120]}")
        y -= 6 * mm

    # ── Tanda tangan ──────────────────────────
    y = max(y, 35 * mm)  # ensure space
    c.setFont("Helvetica", 8)
    c.drawCentredString(left_x + 18 * mm, y, "Pengirim")
    c.drawCentredString(w / 2, y, "Pengemudi")
    c.drawCentredString(w - left_x - 18 * mm, y, "Penerima")
    y -= 18 * mm
    c.line(left_x + 4 * mm, y, left_x + 32 * mm, y)
    c.line(w / 2 - 14 * mm, y, w / 2 + 14 * mm, y)
    c.line(w - left_x - 32 * mm, y, w - left_x - 4 * mm, y)
    y -= 4 * mm
    c.setFont("Helvetica", 7)
    c.drawCentredString(left_x + 18 * mm, y, "(nama jelas & ttd)")
    c.drawCentredString(w / 2, y, shp.get("driver_name") or "(nama jelas & ttd)")
    c.drawCentredString(w - left_x - 18 * mm, y, "(nama jelas & ttd)")

    # Footer
    c.setFont("Helvetica-Oblique", 6)
    c.drawRightString(w - 10 * mm, 6 * mm, f"Dicetak: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    c.showPage()
    c.save()
    return buf.getvalue()


# ─── CUSTOMER STATEMENT (Phase 14.4 — bonus) ────────────────────────────────
@router.get("/customer-statement/{customer_id}")
async def customer_statement(customer_id: str, request: Request):
    """DEPRECATED alias — dipindah ke engine AR: GET /api/rahaza/customer-statement/{id}.
    Alias tipis dipertahankan sementara untuk backward-compat; frontend sudah memakai path baru.
    """
    from routes.rahaza_finance import customer_statement as _cs
    return await _cs(customer_id, request)
