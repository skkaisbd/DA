"""WMS aggregates for AI endpoints (fabric rolls, CMT dispatches, opname)."""
from __future__ import annotations


async def low_stock_count(db) -> int:
    """Active materials below reorder point."""
    return await db.rahaza_materials.count_documents(
        {"active": True, "$expr": {"$lt": ["$total_qty", "$reorder_point"]}}
    )


async def critical_materials_count(db) -> int:
    """Active materials below min_stock (vs reorder_point)."""
    return await db.rahaza_materials.count_documents(
        {"active": True, "$expr": {"$lt": ["$total_qty", {"$ifNull": ["$min_stock", 0]}]}}
    )


async def fabric_quality_breakdown(
    db, *, roll_ids: list[str] | None = None, max_groups: int = 50, max_rolls: int = 100,
) -> dict:
    """Group fabric rolls in QC partial/reject status by supplier+color.

    Returns: {"total_rejections": int, "breakdown": list[{supplier_color, count, materials[]}], "affected_suppliers": int}
    """
    match: dict = {"qc_status": {"$in": ["partial", "reject"]}}
    if roll_ids:
        match["id"] = {"$in": roll_ids}

    pipeline = [
        {"$match": match},
        {"$project": {
            "_id": 0,
            "supplier_name": {"$ifNull": ["$supplier_name", "Unknown"]},
            "color": {"$ifNull": ["$color", "N/A"]},
            "material_name": {"$ifNull": ["$material_name", "Unknown"]},
        }},
        {"$group": {
            "_id": {"supplier": "$supplier_name", "color": "$color"},
            "count": {"$sum": 1},
            "materials": {"$addToSet": "$material_name"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": max_groups},
    ]
    rows = await db.wh_fabric_rolls.aggregate(pipeline).to_list(max_groups)
    if not rows:
        return {"total_rejections": 0, "breakdown": [], "affected_suppliers": 0}

    # Get fast count (capped, single query)
    total = await db.wh_fabric_rolls.count_documents(match)
    total = min(total, max_rolls)

    breakdown = [
        {
            "supplier_color": f"{r['_id'].get('supplier', 'Unknown')} - {r['_id'].get('color', 'N/A')}",
            "count": int(r.get("count") or 0),
            "materials": [m for m in (r.get("materials") or []) if m],
        }
        for r in rows
    ]
    return {
        "total_rejections": total,
        "breakdown": breakdown,
        "affected_suppliers": len(breakdown),
    }


async def cmt_dispatch_performance(
    db, *, cmt_partner_id: str, max_materials: int = 20,
) -> dict:
    """Aggregate completed/dispatched CMT dispatches grouped by material.

    Returns: {"dispatch_count": int, "materials": [{material_name, dispatch_count, total_sent, total_returned, return_rate}]}
    """
    pipeline = [
        {"$match": {
            "cmt_partner_id": cmt_partner_id,
            "status": {"$in": ["completed", "dispatched"]},
        }},
        {"$project": {
            "_id": 0,
            "material_name": {"$ifNull": ["$material_name", "Unknown"]},
            "qty_sent": {"$toDouble": {"$ifNull": ["$qty_sent", 0]}},
            "qty_returned": {"$toDouble": {"$ifNull": ["$qty_returned", 0]}},
        }},
        {"$group": {
            "_id": "$material_name",
            "dispatch_count": {"$sum": 1},
            "total_sent": {"$sum": "$qty_sent"},
            "total_returned": {"$sum": "$qty_returned"},
        }},
        {"$sort": {"dispatch_count": -1}},
        {"$limit": max_materials},
    ]
    rows = await db.wh_cmt_dispatches.aggregate(pipeline).to_list(max_materials)
    total_dispatch = await db.wh_cmt_dispatches.count_documents({
        "cmt_partner_id": cmt_partner_id,
        "status": {"$in": ["completed", "dispatched"]},
    })
    materials = []
    for r in rows:
        sent = float(r.get("total_sent") or 0)
        ret = float(r.get("total_returned") or 0)
        return_rate = (ret / sent * 100) if sent > 0 else 0.0
        materials.append({
            "material_name": r.get("_id") or "Unknown",
            "dispatch_count": int(r.get("dispatch_count") or 0),
            "total_sent": sent,
            "total_returned": ret,
            "return_rate": round(return_rate, 2),
            "success_score": round(100 - return_rate, 2),
        })
    return {"dispatch_count": total_dispatch, "materials": materials}


async def opname_variance_history(db, *, max_sessions: int = 20) -> dict:
    """Read approved opname sessions with at least one variance item.

    Returns variance grouped by zone (scope_id/scope_label).
    """
    pipeline = [
        {"$match": {
            "status": "approved",
            "total_variance_items": {"$gt": 0},
            "$or": [
                {"domain": {"$exists": False}},
                {"domain": {"$ne": "accessory"}},
            ],
        }},
        {"$sort": {"approved_at": -1}},
        {"$limit": max_sessions},
        # Project minimal fields plus the count_items array (still needed for breakdown).
        {"$project": {
            "_id": 0,
            "id": 1,
            "scope_id": 1,
            "scope_label": 1,
            "approved_at": 1,
            "count_items": 1,
        }},
    ]
    sessions = await db.wh_opname_sessions2.aggregate(pipeline).to_list(max_sessions)

    variance_by_zone: dict[str, dict] = {}
    total_variances = 0
    for sess in sessions:
        zone_key = sess.get("scope_id") or sess.get("scope_label") or "Unknown"
        for item in (sess.get("count_items") or []):
            if not item.get("counted"):
                continue
            variance = item.get("variance")
            if variance in (None, 0):
                continue
            slot = variance_by_zone.setdefault(zone_key, {"count": 0, "materials": set()})
            slot["count"] += 1
            slot["materials"].add(
                item.get("material_name") or item.get("material_code") or "Unknown"
            )
            total_variances += 1

    breakdown = [
        {"zone": zone, "variance_count": data["count"], "distinct_materials": len(data["materials"])}
        for zone, data in sorted(variance_by_zone.items(), key=lambda kv: kv[1]["count"], reverse=True)
    ]
    return {
        "sessions_analysed": len(sessions),
        "total_variances": total_variances,
        "breakdown": breakdown,
    }
