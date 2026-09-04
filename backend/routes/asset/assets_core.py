"""Core CRUD for assets: list (GET /), create (POST /), get (GET /{id}), update (PUT /{id}).

The LITERAL `/{asset_id}` path MUST be registered AFTER all other literal endpoints
(disposal-requests, expiring-alerts, my-assets, scan-by-number, batch-depreciate,
reports/*, predictive-maintenance/*, bulk-import/*).
The orchestrator `dewi_asset_management.py` enforces this load order.
"""
from datetime import date
import math
from typing import Optional
from fastapi import Request, HTTPException, Query

from database import get_db
from auth import require_auth
from ._accounts import line as _acc_line, resolve_asset_accounts
from ._helpers import (
    router, _uid, _now, _ser,
    _calc_straight_line_monthly, _create_finance_journal,
    _ensure_default_categories, _gen_asset_number,
)


@router.get("")
async def list_assets(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    assigned_to: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    if category_id:
        query["category_id"] = category_id
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"asset_number": {"$regex": search, "$options": "i"}},
            {"serial_number": {"$regex": search, "$options": "i"}},
        ]
    if assigned_to:
        query["assigned_to_id"] = assigned_to

    total = await db.dewi_assets.count_documents(query)
    skip = (page - 1) * limit
    assets = await db.dewi_assets.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": [_ser(a) for a in assets],
        "pagination": {
            "page": page, "page_size": limit, "total": total,
            "total_pages": math.ceil(total / limit) if total else 1,
        },
    }


@router.post("")
async def create_asset(request: Request):
    user = await require_auth(request)
    db = get_db()
    await _ensure_default_categories(db)
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama aset wajib diisi.")
    purchase_cost = float(body.get("purchase_cost") or 0)
    if purchase_cost <= 0:
        raise HTTPException(400, "Harga beli harus lebih dari 0.")

    cat = None
    if body.get("category_id"):
        cat = await db.dewi_asset_categories.find_one({"id": body["category_id"]}, {"_id": 0})
    if not cat:
        cat = {"id": "", "name": "Lain-lain", "code": "LN",
               "useful_life_years": 5, "depr_method": "straight_line"}

    useful_life_months = int(body.get("useful_life_months") or (cat["useful_life_years"] * 12))
    residual_value = float(body.get("residual_value") or purchase_cost * 0.05)
    depr_method = body.get("depr_method") or cat.get("depr_method", "straight_line")

    asset_number = await _gen_asset_number(db, cat["code"],
                                           (body.get("asset_number") or "").strip())
    purchase_date = (body.get("purchase_date") or date.today().isoformat())[:10]
    monthly_depr = _calc_straight_line_monthly(purchase_cost, residual_value, useful_life_months)

    doc = {
        "id": _uid(),
        "asset_number": asset_number,
        "name": name,
        "category_id": cat["id"],
        "category_name": cat["name"],
        "purchase_date": purchase_date,
        "purchase_cost": purchase_cost,
        "residual_value": residual_value,
        "useful_life_months": useful_life_months,
        "depreciation_method": depr_method,
        "monthly_depreciation": monthly_depr,
        "accumulated_depreciation": 0.0,
        "location": (body.get("location") or "").strip(),
        "serial_number": (body.get("serial_number") or "").strip(),
        "brand": (body.get("brand") or "").strip(),
        "model": (body.get("model") or "").strip(),
        "department": (body.get("department") or "").strip(),
        "status": "active",
        "assigned_to_id": None,
        "assigned_to_name": None,
        "notes": (body.get("notes") or "").strip(),
        "procurement_request_id": body.get("procurement_request_id"),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "disposed_at": None,
        "journal_purchase_id": None,
        "warranty_expiry_date": (body.get("warranty_expiry_date") or "")[:10] or None,
        "warranty_provider":    (body.get("warranty_provider") or "").strip(),
        "warranty_terms":       (body.get("warranty_terms") or "").strip(),
        "insurance_policy_number": (body.get("insurance_policy_number") or "").strip(),
        "insurance_provider":      (body.get("insurance_provider") or "").strip(),
        "insurance_expiry_date":   (body.get("insurance_expiry_date") or "")[:10] or None,
        "insurance_value":         float(body.get("insurance_value") or 0),
    }

    # BUG-5 (FASE 11): kode akun DULU di-hardcode "1500"/"1100" — tidak ada di CoA
    # (CoA proyek ini berformat "1-2500"/"1-110"). Sekarang diambil dari posting
    # profile `asset_acquisition` lewat resolver bersama.
    _acc = await resolve_asset_accounts(db)
    je_id = await _create_finance_journal(
        db, user["id"], user.get("name", ""),
        purchase_date,
        f"Pembelian Aset: {name} ({asset_number})",
        [
            _acc_line(_acc["fixed_asset"], debit=purchase_cost,
                      description=f"Pembelian {name}"),
            _acc_line(_acc["cash"], credit=purchase_cost,
                      description=f"Pembayaran {name}"),
        ],
        source_ref=asset_number,
    )
    doc["journal_purchase_id"] = je_id
    await db.dewi_assets.insert_one(doc)
    return _ser(doc)


@router.get("/{asset_id}")
async def get_asset(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    cost = float(asset.get("purchase_cost", 0))
    residual = float(asset.get("residual_value", 0))
    accum = float(asset.get("accumulated_depreciation", 0))
    nbv = cost - accum

    depr_history = await db.dewi_asset_depreciation.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("period", -1).limit(12).to_list(12)

    asset_out = _ser(asset)
    asset_out["nbv"] = round(nbv, 2)
    asset_out["depreciation_history"] = [_ser(d) for d in depr_history]
    asset_out["fully_depreciated"] = nbv <= residual
    return asset_out


@router.put("/{asset_id}")
async def update_asset(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    body = await request.json()
    allowed = [
        "name", "location", "serial_number", "brand", "model",
        "department", "notes", "status",
        "warranty_expiry_date", "warranty_provider", "warranty_terms",
        "insurance_policy_number", "insurance_provider",
        "insurance_expiry_date", "insurance_value",
    ]
    update = {k: body[k] for k in allowed if k in body}
    if update:
        update["updated_at"] = _now()
        await db.dewi_assets.update_one({"id": asset_id}, {"$set": update})
    return {"ok": True}
