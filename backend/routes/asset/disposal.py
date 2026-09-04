"""/api/assets/disposal-requests (list + approve/reject) and /{asset_id}/(dispose|request-disposal).

This module MUST be imported BEFORE `assets_core` so that the literal
`/disposal-requests` paths are registered before the catch-all `/{asset_id}`.
"""
from datetime import date
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._accounts import line as _acc_line, resolve_asset_accounts
from ._helpers import router, _uid, _now, _ser, _create_finance_journal


# ─── List + approve + reject (LITERAL paths → must register early) ──────────────────

@router.get("/disposal-requests")
async def list_disposal_requests(request: Request, status: str = "pending"):
    """List permintaan disposal. Status: pending | approved | rejected | all."""
    await require_auth(request)
    db = get_db()
    filt = {}
    if status != "all":
        filt["status"] = status
    reqs = await db.dewi_asset_disposal_requests.find(filt, {"_id": 0}).sort("requested_at", -1).to_list(100)
    return [_ser(r) for r in reqs]


@router.patch("/disposal-requests/{req_id}/approve")
async def approve_disposal_request(req_id: str, request: Request):
    """Approve permintaan disposal → eksekusi dispose + jurnal Finance."""
    user = await require_auth(request)
    if user.get("role") not in ("admin", "superadmin", "finance", "manager"):
        raise HTTPException(403, "Hanya admin/finance/manager yang bisa approve disposal.")
    db = get_db()
    req = await db.dewi_asset_disposal_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] != "pending":
        raise HTTPException(400, f"Request sudah {req['status']}.")

    body = await request.json()
    notes = (body.get("notes") or "").strip()

    asset = await db.dewi_assets.find_one({"id": req["asset_id"]})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    cost = float(asset["purchase_cost"])
    accum = float(asset.get("accumulated_depreciation", 0))
    nbv = cost - accum
    disposal_value = float(req.get("disposal_value", 0))
    gain_loss = disposal_value - nbv

    # BUG-5 (FASE 11): kode akun DULU di-hardcode ("1590"/"1500"/"1100"/"8100"/"6300")
    # dan TIDAK ADA satupun di CoA. Sekarang diambil dari posting profile
    # `asset_disposal` (SSOT) lewat resolver bersama.
    _acc = await resolve_asset_accounts(db)
    lines = [
        _acc_line(_acc["accum_depr"], debit=accum,
                  description=f"Hapus akumulasi {asset['asset_number']}"),
        _acc_line(_acc["fixed_asset"], credit=cost,
                  description=f"Hapus aset {asset['asset_number']}"),
    ]
    if disposal_value > 0:
        lines.append(_acc_line(_acc["cash"], debit=disposal_value,
                               description="Penerimaan disposal"))
    if gain_loss > 0:
        lines.append(_acc_line(_acc["gain_on_disposal"], credit=gain_loss,
                               description="Keuntungan disposal"))
    elif gain_loss < 0:
        lines.append(_acc_line(_acc["loss_on_disposal"], debit=abs(gain_loss),
                               description="Kerugian disposal"))

    je_id = await _create_finance_journal(
        db, user["id"], user.get("name", ""),
        req["disposal_date"],
        f"Disposal Aset (Approved): {asset['name']} ({asset['asset_number']})",
        lines, source_ref=asset["asset_number"],
    )

    now = _now()
    await db.dewi_assets.update_one(
        {"id": asset["id"]},
        {"$set": {
            "status": "disposed", "disposed_at": now,
            "disposal_value": disposal_value,
            "disposal_reason": req.get("reason", ""),
            "disposal_journal_id": je_id,
            "updated_at": now,
        }},
    )
    await db.dewi_asset_disposal_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "approved", "reviewed_by": user["id"],
            "reviewed_by_name": user.get("name", ""),
            "reviewed_at": now, "review_notes": notes, "journal_id": je_id,
        }},
    )
    return {"ok": True, "gain_loss": round(gain_loss, 2), "journal_id": je_id}


@router.patch("/disposal-requests/{req_id}/reject")
async def reject_disposal_request(req_id: str, request: Request):
    """Reject permintaan disposal → kembalikan status aset ke active."""
    user = await require_auth(request)
    if user.get("role") not in ("admin", "superadmin", "finance", "manager"):
        raise HTTPException(403, "Hanya admin/finance/manager yang bisa reject disposal.")
    db = get_db()
    req = await db.dewi_asset_disposal_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] != "pending":
        raise HTTPException(400, f"Request sudah {req['status']}.")

    body = await request.json()
    notes = (body.get("notes") or "").strip()

    now = _now()
    await db.dewi_asset_disposal_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "rejected", "reviewed_by": user["id"],
            "reviewed_by_name": user.get("name", ""),
            "reviewed_at": now, "review_notes": notes,
        }},
    )
    await db.dewi_assets.update_one(
        {"id": req["asset_id"]},
        {"$set": {"status": "active", "updated_at": now}},
    )
    return {"ok": True}


# ─── Per-asset disposal actions (registered later for path-priority safety) ────────────────────────────
# NOTE: These start with /{asset_id}/ but they live AFTER `/disposal-requests`
# because that route is registered above. FastAPI matches by registration order.

@router.post("/{asset_id}/dispose")
async def dispose_asset(asset_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    if asset.get("status") == "disposed":
        raise HTTPException(400, "Aset sudah dilepas.")
    body = await request.json()
    disposal_date = (body.get("disposal_date") or date.today().isoformat())[:10]
    disposal_value = float(body.get("disposal_value") or 0)
    reason = (body.get("reason") or "").strip()

    cost = float(asset["purchase_cost"])
    accum = float(asset.get("accumulated_depreciation", 0))
    nbv = cost - accum
    gain_loss = disposal_value - nbv

    # BUG-5 (FASE 11): kode akun DULU di-hardcode ("1590"/"1500"/"1100"/"8100"/"6300")
    # dan TIDAK ADA satupun di CoA. Sekarang diambil dari posting profile
    # `asset_disposal` (SSOT) lewat resolver bersama.
    _acc = await resolve_asset_accounts(db)
    lines = [
        _acc_line(_acc["accum_depr"], debit=accum,
                  description=f"Hapus akumulasi {asset['asset_number']}"),
        _acc_line(_acc["fixed_asset"], credit=cost,
                  description=f"Hapus aset {asset['asset_number']}"),
    ]
    if disposal_value > 0:
        lines.append(_acc_line(_acc["cash"], debit=disposal_value,
                               description="Penerimaan disposal"))
    if gain_loss > 0:
        lines.append(_acc_line(_acc["gain_on_disposal"], credit=gain_loss,
                               description="Keuntungan disposal"))
    elif gain_loss < 0:
        lines.append(_acc_line(_acc["loss_on_disposal"], debit=abs(gain_loss),
                               description="Kerugian disposal"))

    je_id = await _create_finance_journal(
        db, user["id"], user.get("name", ""),
        disposal_date,
        f"Disposal Aset: {asset['name']} ({asset['asset_number']})",
        lines, source_ref=asset["asset_number"],
    )
    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {
            "status": "disposed",
            "disposed_at": _now(),
            "disposal_value": disposal_value,
            "disposal_reason": reason,
            "disposal_journal_id": je_id,
            "updated_at": _now(),
        }},
    )
    return {"ok": True, "gain_loss": gain_loss, "journal_id": je_id}


@router.post("/{asset_id}/request-disposal")
async def request_disposal(asset_id: str, request: Request):
    """Buat permintaan disposal untuk aset bernilai tinggi (NBV > threshold)."""
    user = await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    if asset.get("status") == "disposed":
        raise HTTPException(400, "Aset sudah dilepas.")

    cost = float(asset.get("purchase_cost", 0))
    accum = float(asset.get("accumulated_depreciation", 0))
    nbv = cost - accum

    existing = await db.dewi_asset_disposal_requests.find_one(
        {"asset_id": asset_id, "status": "pending"}
    )
    if existing:
        raise HTTPException(400, "Sudah ada permintaan disposal yang menunggu approval.")

    body = await request.json()
    disposal_date = (body.get("disposal_date") or date.today().isoformat())[:10]
    disposal_value = float(body.get("disposal_value") or 0)
    reason = (body.get("reason") or "").strip()

    if not reason:
        raise HTTPException(400, "Alasan disposal wajib diisi.")

    doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_number": asset.get("asset_number", ""),
        "asset_name": asset.get("name", ""),
        "nbv": round(nbv, 2),
        "disposal_date": disposal_date,
        "disposal_value": disposal_value,
        "reason": reason,
        "status": "pending",
        "requested_by": user["id"],
        "requested_by_name": user.get("name", ""),
        "requested_at": _now(),
        "reviewed_by": None,
        "reviewed_by_name": "",
        "reviewed_at": None,
        "review_notes": "",
        "journal_id": None,
    }
    await db.dewi_asset_disposal_requests.insert_one(doc)
    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {"status": "pending_disposal", "updated_at": _now()}},
    )
    return _ser(doc)
