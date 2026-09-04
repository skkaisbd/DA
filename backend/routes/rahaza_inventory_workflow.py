"""rahaza_inventory — MI workflow legacy (confirm/cancel/delete) + post-to-gl."""
# ruff: noqa: E741
from fastapi import Request, HTTPException
from database import get_db
from auth import serialize_doc, log_activity
from routes.rahaza_inventory_shared import (
    router, log, _now, _require_admin,
    _add_stock, _enrich_mi, _log_movement,
)
from routes.rahaza_posting import (
    post_inventory_issue,
    post_inventory_receive,
    post_inventory_adjust,
)


@router.post("/material-issues/{mid}/confirm")
async def confirm_mi(mid: str, request: Request):  # noqa: C901
    """DEPRECATED: Legacy direct confirm (draft → issued without approval)."""
    user = await _require_admin(request)
    db = get_db()
    mi = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    if not mi:
        raise HTTPException(404, "MI tidak ditemukan.")
    if mi.get("status") != "draft":
        raise HTTPException(400, f"MI status '{mi.get('status')}' tidak bisa di-confirm langsung. Gunakan workflow submit/approve.")
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    loc_overrides = body.get("location_overrides") or {}
    plan = []
    shortages = []
    raw_items = list(mi.get("items") or [])
    pairs = set()
    for it in raw_items:
        loc = loc_overrides.get(it["material_id"]) or it.get("location_id")
        if loc and float(it.get("qty_required") or 0) > 0:
            pairs.add((it["material_id"], loc))
    stock_map = {}
    if pairs:
        mids = list({p[0] for p in pairs})
        locs = list({p[1] for p in pairs})
        async for s in db.rahaza_material_stock.find({"material_id": {"$in": mids}, "location_id": {"$in": locs}}):
            stock_map[(s.get("material_id"), s.get("location_id"))] = s
    for it in raw_items:
        loc = loc_overrides.get(it["material_id"]) or it.get("location_id")
        if not loc:
            raise HTTPException(400, f"Item belum punya lokasi: material {it.get('material_id')}.")
        qty = float(it.get("qty_required") or 0)
        if qty <= 0:
            continue
        stock = stock_map.get((it["material_id"], loc))
        avail = float((stock or {}).get("qty") or 0)
        if avail < qty:
            shortages.append({"material_id": it["material_id"], "required": qty, "available": avail, "location_id": loc})
        plan.append({"material_id": it["material_id"], "location_id": loc, "qty": qty, "item_id": it["id"]})
    if shortages:
        raise HTTPException(400, {"message": "Stok tidak cukup untuk issue.", "shortages": shortages})
    for p in plan:
        await _add_stock(db, p["material_id"], p["location_id"], -p["qty"])
        await _log_movement(db, user,
            type="issue", material_id=p["material_id"], qty=p["qty"],
            from_location_id=p["location_id"], to_location_id=None,
            ref_type="wo_issue" if mi.get("work_order_id") else "manual_issue",
            ref_id=mi["id"], notes=f"MI {mi['mi_number']}",
        )
    new_items = []
    for it in (mi.get("items") or []):
        new_items.append({**it, "qty_issued": float(it.get("qty_required") or 0),
                         "location_id": loc_overrides.get(it["material_id"]) or it.get("location_id")})
    await db.rahaza_material_issues.update_one({"id": mid}, {"$set": {
        "items": new_items, "status": "issued", "issued_at": _now(), "issued_by": user["id"], "updated_at": _now(),
    }})
    await log_activity(user["id"], user.get("name", ""), "confirm", "rahaza.mi", mi["mi_number"])
    out = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    await _enrich_mi(db, out)
    posting_result = None
    try:
        posting_result = await post_inventory_issue(db, out, user)
    except Exception as e:
        log.exception("Inventory issue auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    out_refresh = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    await _enrich_mi(db, out_refresh)
    out_refresh["_posting_result"] = posting_result
    return serialize_doc(out_refresh)


@router.post("/material-issues/{mid}/post-to-gl")
async def retry_post_mi(mid: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    mi = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    if not mi:
        raise HTTPException(404, "MI tidak ditemukan.")
    if mi.get("status") != "issued":
        raise HTTPException(400, "Hanya MI issued yang bisa di-post.")
    # ── FASE H-6b (2026-08-17) — LUBANG YANG DITUTUP DI SINI ─────────────────
    # Dokumen Cutting (`cutting_issue`) lahir berstatus `issued`, jadi TANPA
    # penjaga ini satu klik admin cukup untuk menjurnal Dr WIP / Cr Persediaan
    # atas kain yang nilainya BUKAN hilang, melainkan berpindah menjadi nilai
    # potongan (potongan masih tercatat sebagai persediaan). Akibatnya nilai
    # persediaan di buku besar turun sementara barangnya masih ada di sistem stok.
    if mi.get("ref_type") == "cutting_issue" or mi.get("source") == "cutting":
        raise HTTPException(400, (
            "Dokumen ini berasal dari Portal Cutting dan memang TIDAK dijurnal. "
            "Kalau nilai persediaan perlu dikoreksi, pakai Penyesuaian Stok di Gudang. "
            "Alasan: " + (mi.get("gl_skip_reason") or "")))
    result = await post_inventory_issue(db, mi, user)
    out = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    await _enrich_mi(db, out)
    out["_posting_result"] = result
    return serialize_doc(out)


@router.post("/material-movements/{mv_id}/post-to-gl")
async def retry_post_movement(mv_id: str, request: Request):
    user = await _require_admin(request)
    db = get_db()
    mv = await db.rahaza_material_movements.find_one({"id": mv_id}, {"_id": 0})
    if not mv:
        raise HTTPException(404, "Movement tidak ditemukan.")
    if mv["type"] == "receive":
        result = await post_inventory_receive(db, mv, user)
    elif mv["type"] == "adjust":
        result = await post_inventory_adjust(db, mv, user)
    else:
        raise HTTPException(400, f"Type '{mv['type']}' tidak bisa di-post.")
    out = await db.rahaza_material_movements.find_one({"id": mv_id}, {"_id": 0})
    out["_posting_result"] = result
    return serialize_doc(out)


@router.post("/material-issues/{mid}/cancel")
async def cancel_mi(mid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    mi = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    if not mi:
        raise HTTPException(404, "MI tidak ditemukan.")
    if mi.get("status") not in ("draft", "pending_approval"):
        raise HTTPException(400, "Hanya MI Draft atau Menunggu Approval yang bisa di-cancel.")
    await db.rahaza_material_issues.update_one({"id": mid}, {"$set": {"status": "cancelled", "updated_at": _now()}})
    return {"status": "cancelled"}


@router.delete("/material-issues/{mid}")
async def delete_mi(mid: str, request: Request):
    await _require_admin(request)
    db = get_db()
    mi = await db.rahaza_material_issues.find_one({"id": mid}, {"_id": 0})
    if not mi:
        raise HTTPException(404, "MI tidak ditemukan.")
    if mi.get("status") not in ("draft", "cancelled"):
        raise HTTPException(400, "Hanya MI Draft/Cancelled yang bisa dihapus.")
    await db.rahaza_material_issues.delete_one({"id": mid})
    return {"status": "deleted"}
