"""
universal_scan.py — Universal Multi-Entity Barcode / QR Code Resolver

GET  /api/scan/{code}   — Resolve kode ke entity (asset/bundle/material/WO/PO/roll/DO)
POST /api/scan/resolve  — Sama, tapi lewat body (untuk QR JSON panjang)
GET  /api/scan/history  — Riwayat scan terbaru (audit trail)
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth

logger = logging.getLogger("universal_scan")

router = APIRouter(prefix="/api/scan", tags=["universal_scan"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _ser(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop("_id", None)
    for k, v in list(doc.items()):
        if hasattr(v, "isoformat"):
            doc[k] = v.isoformat()
    return doc


# ─── Entity Resolvers ─────────────────────────────────────────────────────────

async def _resolve_asset(db, code: str):
    doc = await db.dewi_assets.find_one(
        {"asset_number": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "asset_number": 1, "name": 1, "status": 1,
         "category_name": 1, "location": 1, "assigned_to_name": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "asset",
        "entity_type_label": "Aset",
        "entity_id": doc["id"],
        "entity_number": doc.get("asset_number", ""),
        "display_name": doc.get("name", ""),
        "status": doc.get("status", ""),
        "meta": {
            "Kategori": doc.get("category_name", "-"),
            "Lokasi": doc.get("location", "-"),
            "Dipegang": doc.get("assigned_to_name", "-"),
        },
        "quick_actions": [
            {"id": "view_asset", "label": "Lihat Detail Aset", "module": "fin-assets", "entity_id": doc["id"]},
            {"id": "scan_asset", "label": "Catat Scan / Update Lokasi", "action": "scan_asset",
             "entity_id": doc["id"], "asset_number": doc.get("asset_number", "")},
        ],
    }


async def _resolve_bundle(db, code: str):
    doc = await db.rahaza_bundles.find_one(
        {"bundle_number": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "bundle_number": 1, "style_name": 1, "status": 1,
         "wo_number": 1, "qty": 1, "cutting_no": 1, "current_process": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "bundle",
        "entity_type_label": "Bundle Produksi",
        "entity_id": doc["id"],
        "entity_number": doc.get("bundle_number", ""),
        "display_name": doc.get("style_name") or doc.get("bundle_number", ""),
        "status": doc.get("status", ""),
        "meta": {
            "No. WO": doc.get("wo_number", "-"),
            "Qty": str(doc.get("qty", "-")),
            "Proses": doc.get("current_process", "-"),
        },
        "quick_actions": [
            {"id": "view_bundle", "label": "Lihat Detail Bundle", "module": "prod-bundles", "entity_id": doc["id"]},
        ],
    }


async def _resolve_material(db, code: str):
    pattern = {"$regex": f"^{re.escape(code)}$", "$options": "i"}
    doc = await db.rahaza_materials.find_one(
        {"$or": [{"material_code": pattern}, {"barcode": pattern}]},
        {"_id": 0, "id": 1, "material_code": 1, "name": 1, "type": 1,
         "unit": 1, "current_stock": 1, "location": 1, "barcode": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "material",
        "entity_type_label": "Material / Aksesori",
        "entity_id": doc["id"],
        "entity_number": doc.get("material_code", "") or doc.get("barcode", ""),
        "display_name": doc.get("name", ""),
        "status": doc.get("type", ""),
        "meta": {
            "Kode": doc.get("material_code", "-"),
            "Stok": f"{doc.get('current_stock', 0)} {doc.get('unit', '')}".strip(),
            "Lokasi": doc.get("location", "-"),
        },
        "quick_actions": [
            {"id": "view_material", "label": "Lihat Stok", "module": "wh-materials", "entity_id": doc["id"]},
        ],
    }


async def _resolve_work_order(db, code: str):
    doc = await db.rahaza_work_orders.find_one(
        {"wo_number": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "wo_number": 1, "style_name": 1, "status": 1,
         "qty": 1, "due_date": 1, "buyer": 1, "order_number": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "work_order",
        "entity_type_label": "Work Order",
        "entity_id": doc["id"],
        "entity_number": doc.get("wo_number", ""),
        "display_name": doc.get("style_name") or doc.get("wo_number", ""),
        "status": doc.get("status", ""),
        "meta": {
            "Buyer": doc.get("buyer", "-"),
            "Qty": str(doc.get("qty", "-")),
            "Deadline": (doc.get("due_date") or "-")[:10],
        },
        "quick_actions": [
            {"id": "view_wo", "label": "Lihat Work Order", "module": "prod-work-orders", "entity_id": doc["id"]},
        ],
    }


async def _resolve_purchase_order(db, code: str):
    doc = await db.rahaza_purchase_orders.find_one(
        {"po_number": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "po_number": 1, "vendor_name": 1, "status": 1,
         "po_date": 1, "expected_delivery_date": 1, "from_pr_number": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "purchase_order",
        "entity_type_label": "Purchase Order",
        "entity_id": doc["id"],
        "entity_number": doc.get("po_number", ""),
        "display_name": f"PO ke {doc.get('vendor_name', '-')}",
        "status": doc.get("status", ""),
        "meta": {
            "Vendor": doc.get("vendor_name", "-"),
            "Tgl PO": (doc.get("po_date") or "-")[:10],
            "Dari PR": doc.get("from_pr_number", "-") or "-",
        },
        "quick_actions": [
            {"id": "view_po", "label": "Lihat Purchase Order", "module": "proc-purchase-orders", "entity_id": doc["id"]},
        ],
    }


async def _resolve_fabric_roll(db, code: str):
    pattern = {"$regex": f"^{re.escape(code)}$", "$options": "i"}
    doc = await db.wms_fabric_rolls.find_one(
        {"$or": [{"roll_number": pattern}, {"barcode": pattern}]},
        {"_id": 0, "id": 1, "roll_number": 1, "fabric_name": 1, "status": 1,
         "remaining_m": 1, "remaining_kg": 1, "location": 1, "color": 1},
    )
    if not doc:
        return None
    return {
        "entity_type": "fabric_roll",
        "entity_type_label": "Roll Kain",
        "entity_id": doc["id"],
        "entity_number": doc.get("roll_number", ""),
        "display_name": doc.get("fabric_name", "") or doc.get("roll_number", ""),
        "status": doc.get("status", ""),
        "meta": {
            "Warna": doc.get("color", "-"),
            "Sisa (m)": str(doc.get("remaining_m", "-")),
            "Lokasi": doc.get("location", "-"),
        },
        "quick_actions": [
            {"id": "view_roll", "label": "Lihat Roll Kain", "module": "wh-fabric-rolls", "entity_id": doc["id"]},
        ],
    }


async def _resolve_delivery_order(db, code: str):
    pattern = {"$regex": f"^{re.escape(code)}$", "$options": "i"}
    doc = await db.dewi_cmt_delivery_orders.find_one(
        {"do_number": pattern},
        {"_id": 0, "id": 1, "do_number": 1, "customer_name": 1, "status": 1,
         "delivery_date": 1, "total_qty": 1},
    )
    if not doc:
        doc = await db.dewi_delivery_orders.find_one(
            {"do_number": pattern},
            {"_id": 0, "id": 1, "do_number": 1, "customer_name": 1, "status": 1,
             "delivery_date": 1, "total_qty": 1},
        )
    if not doc:
        return None
    return {
        "entity_type": "delivery_order",
        "entity_type_label": "Delivery Order",
        "entity_id": doc["id"],
        "entity_number": doc.get("do_number", ""),
        "display_name": f"DO ke {doc.get('customer_name', '-')}",
        "status": doc.get("status", ""),
        "meta": {
            "Customer": doc.get("customer_name", "-"),
            "Tgl Kirim": (doc.get("delivery_date") or "-")[:10],
            "Qty": str(doc.get("total_qty", "-")),
        },
        "quick_actions": [
            {"id": "view_do", "label": "Lihat DO", "module": "prod-delivery-orders", "entity_id": doc["id"]},
        ],
    }


# ─── Main Resolver ────────────────────────────────────────────────────────────

RESOLVERS = [
    _resolve_asset,
    _resolve_bundle,
    _resolve_material,
    _resolve_work_order,
    _resolve_purchase_order,
    _resolve_fabric_roll,
    _resolve_delivery_order,
]


async def _do_resolve(db, raw_code: str, user: dict):
    code = raw_code.strip()

    # 1. Try JSON parse (from QR codes with embedded data)
    result = None
    if code.startswith("{"):
        try:
            payload = json.loads(code)
            entity_type = payload.get("type", "")
            entity_id = payload.get("asset_id") or payload.get("id") or payload.get("entity_id")
            if entity_type == "asset" and entity_id:
                doc = await db.dewi_assets.find_one({"id": entity_id}, {"_id": 0})
                if doc:
                    result = await _resolve_asset(db, doc.get("asset_number", ""))
            # Extend for other embedded QR types as needed
        except (json.JSONDecodeError, Exception):
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # 2. Sequential resolver chain (try each entity type)
    if not result:
        for resolver in RESOLVERS:
            try:
                result = await resolver(db, code)
                if result:
                    break
            except Exception as e:
                logger.warning(f"Resolver {resolver.__name__} error: {e}")
                continue

    # 3. Log scan event
    scan_doc = {
        "id": _uid(),
        "raw_code": code,
        "scanned_by": user["id"],
        "scanned_by_name": user.get("name", ""),
        "found": result is not None,
        "entity_type": result["entity_type"] if result else None,
        "entity_id": result["entity_id"] if result else None,
        "entity_number": result["entity_number"] if result else None,
        "display_name": result["display_name"] if result else None,
        "scanned_at": _now(),
    }
    try:
        await db.dewi_universal_scans.insert_one(scan_doc)
    except Exception as e:
        logger.warning(f"Failed to log scan: {e}")

    if not result:
        return {"found": False, "raw_code": code, "scan_id": scan_doc["id"]}

    return {"found": True, "scan_id": scan_doc["id"], **result}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/history")
async def get_scan_history(request: Request, limit: int = 50):
    """Riwayat scan universal (50 terbaru)."""
    await require_auth(request)
    db = get_db()
    docs = await db.dewi_universal_scans.find(
        {}, {"_id": 0}
    ).sort("scanned_at", -1).limit(max(1, min(limit, 200))).to_list(200)
    return [_ser(d) for d in docs]


@router.post("/resolve")
async def resolve_scan_post(request: Request):
    """Resolve kode dari body JSON (untuk QR code panjang)."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Field 'code' tidak boleh kosong.")
    return await _do_resolve(db, code, user)


@router.get("/{code:path}")
async def resolve_scan_get(code: str, request: Request):
    """Resolve kode dari URL path parameter."""
    user = await require_auth(request)
    db = get_db()
    if not code or not code.strip():
        raise HTTPException(400, "Kode tidak boleh kosong.")
    return await _do_resolve(db, code.strip(), user)
