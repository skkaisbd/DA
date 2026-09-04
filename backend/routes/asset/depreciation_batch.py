"""/api/assets/batch-depreciate/{period} — LITERAL path; must precede /{asset_id}."""
from fastapi import Request

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _calc_straight_line_monthly, _create_finance_journal


@router.post("/batch-depreciate/{period}")
async def batch_depreciate(period: str, request: Request):
    """Posting depresiasi massal untuk semua aset aktif pada periode YYYY-MM. Idempotent per aset."""
    user = await require_auth(request)
    db = get_db()
    assets = await db.dewi_assets.find(
        {"status": {"$ne": "disposed"}}, {"_id": 0}
    ).to_list(1000)
    results = {"posted": [], "skipped": [], "errors": []}
    for asset in assets:
        asset_id = asset["id"]
        existing = await db.dewi_asset_depreciation.find_one({"asset_id": asset_id, "period": period})
        if existing:
            results["skipped"].append({"id": asset_id, "number": asset.get("asset_number"), "reason": "Sudah diposting"})
            continue
        cost = float(asset.get("purchase_cost", 0))
        residual = float(asset.get("residual_value", 0))
        accum = float(asset.get("accumulated_depreciation", 0))
        nbv = cost - accum
        if nbv <= residual:
            results["skipped"].append({"id": asset_id, "number": asset.get("asset_number"), "reason": "Sudah habis"})
            continue
        try:
            monthly = float(asset.get("monthly_depreciation") or
                            _calc_straight_line_monthly(cost, residual, asset.get("useful_life_months", 60)))
            depr_amount = min(monthly, nbv - residual)
            new_accum = accum + depr_amount
            je_id = await _create_finance_journal(
                db, user["id"], user.get("name", ""),
                f"{period}-28",
                f"Depresiasi Massal: {asset['name']} ({asset.get('asset_number', '')}) - {period}",
                [
                    {"account_code": "6200", "account_name": "Beban Depresiasi", "account_type": "expense",
                     "debit": depr_amount, "credit": 0.0, "description": f"Depresiasi {asset.get('asset_number', '')}"},
                    {"account_code": "1590", "account_name": "Akumulasi Depresiasi", "account_type": "asset",
                     "debit": 0.0, "credit": depr_amount, "description": f"Akumulasi {asset.get('asset_number', '')}"},
                ],
                source_ref=asset.get("asset_number", ""),
            )
            depr_doc = {
                "id": _uid(), "asset_id": asset_id, "asset_number": asset.get("asset_number", ""),
                "asset_name": asset["name"], "period": period,
                "amount": depr_amount, "cumulative": new_accum,
                "nbv_before": nbv, "nbv_after": cost - new_accum,
                "journal_id": je_id, "created_by": user["id"], "created_at": _now(),
            }
            await db.dewi_asset_depreciation.insert_one(depr_doc)
            await db.dewi_assets.update_one(
                {"id": asset_id}, {"$set": {"accumulated_depreciation": new_accum, "updated_at": _now()}}
            )
            results["posted"].append({"id": asset_id, "number": asset.get("asset_number"), "amount": depr_amount})
        except Exception as e:
            results["errors"].append({"id": asset_id, "number": asset.get("asset_number"), "error": str(e)})
    return {
        "period": period,
        "total_posted": len(results["posted"]),
        "total_skipped": len(results["skipped"]),
        "total_errors": len(results["errors"]),
        "details": results,
    }
