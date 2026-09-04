"""Per-asset depreciation:
  POST /{asset_id}/depreciate/{period}
  GET  /{asset_id}/depreciation-history
"""
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser, _calc_straight_line_monthly, _create_finance_journal


@router.post("/{asset_id}/depreciate/{period}")
async def post_depreciation(asset_id: str, period: str, request: Request):
    """Post depresiasi untuk 1 aset pada periode YYYY-MM. Idempotent."""
    user = await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    if asset.get("status") == "disposed":
        raise HTTPException(400, "Aset sudah dilepas, tidak bisa depresiasi.")

    existing = await db.dewi_asset_depreciation.find_one({"asset_id": asset_id, "period": period})
    if existing:
        raise HTTPException(400, f"Depresiasi periode {period} sudah diposting.")

    cost = float(asset["purchase_cost"])
    residual = float(asset.get("residual_value", 0))
    accum = float(asset.get("accumulated_depreciation", 0))
    nbv = cost - accum

    if nbv <= residual:
        raise HTTPException(400, "Aset sudah habis didepresiasi (NBV = nilai residu).")

    monthly = float(asset.get("monthly_depreciation") or
                    _calc_straight_line_monthly(cost, residual, asset.get("useful_life_months", 60)))
    depr_amount = min(monthly, nbv - residual)
    new_accum = accum + depr_amount

    period_date = f"{period}-28"
    je_id = await _create_finance_journal(
        db, user["id"], user.get("name", ""),
        period_date,
        f"Depresiasi Aset: {asset['name']} ({asset['asset_number']}) - {period}",
        [
            {"account_code": "6200", "account_name": "Beban Depresiasi", "account_type": "expense",
             "debit": depr_amount, "credit": 0.0, "description": f"Depresiasi {asset['asset_number']}"},
            {"account_code": "1590", "account_name": "Akumulasi Depresiasi", "account_type": "asset",
             "debit": 0.0, "credit": depr_amount, "description": f"Akumulasi {asset['asset_number']}"},
        ],
        source_ref=asset["asset_number"],
    )

    depr_doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_number": asset["asset_number"],
        "asset_name": asset["name"],
        "period": period,
        "amount": depr_amount,
        "cumulative": new_accum,
        "nbv_before": nbv,
        "nbv_after": cost - new_accum,
        "journal_id": je_id,
        "created_by": user["id"],
        "created_at": _now(),
    }
    await db.dewi_asset_depreciation.insert_one(depr_doc)
    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {"accumulated_depreciation": new_accum, "updated_at": _now()}},
    )
    return _ser(depr_doc)


@router.get("/{asset_id}/depreciation-history")
async def get_depreciation_history(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    recs = await db.dewi_asset_depreciation.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("period", -1).to_list(100)
    return [_ser(r) for r in recs]
