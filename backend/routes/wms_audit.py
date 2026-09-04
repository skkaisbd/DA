"""
WMS — Audit Trail for Stock Adjustments
Menampilkan history semua adjustment stok (saat ini: opname_adjustment)
dengan filter by operator, posisi, rak, gedung, dan tanggal.

Sumber data: rahaza_fg_movements where source in (opname_adjustment, ...)

Routes:
  GET  /api/wms/audit/adjustments       — list + pagination + filters
  GET  /api/wms/audit/adjustments/stats — ringkasan statistik
  GET  /api/wms/audit/adjustments/export-csv — download CSV
"""

import io
import csv
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth, serialize_doc, verify_token_str

router = APIRouter(prefix="/api/wms/audit", tags=["wms-audit"])


# Sources that count as "stock adjustments" for the audit trail
ADJUSTMENT_SOURCES = ["opname_adjustment"]


async def _auth_or_token(request: Request, token: Optional[str] = None):
    if token:
        user = verify_token_str(token)
        if user:
            return user
    return await require_auth(request)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Accept "YYYY-MM-DD" or full ISO
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def _build_query(db, *,
    operator: Optional[str] = None,
    position_barcode: Optional[str] = None,
    rack_id: Optional[str] = None,
    building_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    direction: Optional[str] = None,
) -> dict:
    q: dict = {"source": {"$in": ADJUSTMENT_SOURCES}}
    if operator:
        q["created_by"] = {"$regex": operator, "$options": "i"}
    if position_barcode:
        q["position_barcode"] = {"$regex": position_barcode, "$options": "i"}
    if direction in ("adjust_in", "adjust_out"):
        q["direction"] = direction

    # Scope by rack/building → resolve to position_ids first
    if rack_id or building_id:
        pos_q = {}
        if rack_id:
            pos_q["rack_id"] = rack_id
        if building_id:
            pos_q["building_id"] = building_id
        pos_ids = await db.wh_positions.distinct("id", pos_q)
        q["position_id"] = {"$in": pos_ids or ["__none__"]}

    # Date range
    df = _parse_iso(date_from)
    dt = _parse_iso(date_to)
    if df or dt:
        ts_q = {}
        if df:
            ts_q["$gte"] = df
        if dt:
            ts_q["$lte"] = dt
        q["timestamp"] = ts_q
    return q


@router.get("/adjustments")
async def list_adjustments(
    request: Request,
    operator: Optional[str] = None,
    position_barcode: Optional[str] = None,
    rack_id: Optional[str] = None,
    building_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = Query(100, le=500),
    skip: int = 0,
):
    """
    Daftar semua adjustment stok dengan filter.
    Response: {items: [...], total, limit, skip}
    """
    await require_auth(request)
    db = get_db()
    q = await _build_query(
        db, operator=operator, position_barcode=position_barcode,
        rack_id=rack_id, building_id=building_id,
        date_from=date_from, date_to=date_to, direction=direction,
    )
    total = await db.rahaza_fg_movements.count_documents(q)
    rows = await db.rahaza_fg_movements.find(q, {"_id": 0})\
        .sort("timestamp", -1).skip(skip).limit(limit).to_list(500)

    # Enrich position path (building/zone/rack)
    pos_ids = [r.get("position_id") for r in rows if r.get("position_id")]
    pos_map = {}
    if pos_ids:
        async for p in db.wh_positions.find({"id": {"$in": pos_ids}}, {"_id": 0}):
            pos_map[p["id"]] = p
    for r in rows:
        p = pos_map.get(r.get("position_id"))
        if p:
            r["position_label"] = p.get("label")
            r["rack_code"] = p.get("rack_code")
            r["zone_code"] = p.get("zone_code")
            r["building_code"] = p.get("building_code")

    return serialize_doc({
        "items": rows,
        "total": total, "limit": limit, "skip": skip,
    })


@router.get("/adjustments/stats")
async def adjustment_stats(
    request: Request,
    operator: Optional[str] = None,
    position_barcode: Optional[str] = None,
    rack_id: Optional[str] = None,
    building_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """
    Ringkasan: total adjustment, total surplus/shortage qty,
    breakdown by operator, by direction.
    """
    await require_auth(request)
    db = get_db()
    q = await _build_query(
        db, operator=operator, position_barcode=position_barcode,
        rack_id=rack_id, building_id=building_id,
        date_from=date_from, date_to=date_to,
    )
    # Overall stats
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$direction",
            "count": {"$sum": 1},
            "total_qty": {"$sum": "$qty"},
        }}
    ]
    dir_rows = await db.rahaza_fg_movements.aggregate(pipeline).to_list(500)
    surplus_count = 0
    surplus_qty = 0.0
    shortage_count = 0
    shortage_qty = 0.0
    for r in dir_rows:
        if r["_id"] == "adjust_in":
            surplus_count = r["count"]
            surplus_qty = round(r["total_qty"], 4)
        elif r["_id"] == "adjust_out":
            shortage_count = r["count"]
            shortage_qty = round(r["total_qty"], 4)

    # By operator (top 10)
    op_pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$created_by",
            "count": {"$sum": 1},
            "surplus_qty": {"$sum": {"$cond": [{"$eq": ["$direction", "adjust_in"]}, "$qty", 0]}},
            "shortage_qty": {"$sum": {"$cond": [{"$eq": ["$direction", "adjust_out"]}, "$qty", 0]}},
            "last_activity": {"$max": "$timestamp"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    by_operator = await db.rahaza_fg_movements.aggregate(op_pipeline).to_list(500)
    by_operator = [
        {
            "operator": r["_id"] or "unknown",
            "count": r["count"],
            "surplus_qty": round(r.get("surplus_qty", 0), 4),
            "shortage_qty": round(r.get("shortage_qty", 0), 4),
            "net_qty": round(r.get("surplus_qty", 0) - r.get("shortage_qty", 0), 4),
            "last_activity": r.get("last_activity").isoformat() if r.get("last_activity") else None,
        }
        for r in by_operator
    ]

    # By position (top 10 hotspots)
    pos_pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$position_barcode",
            "count": {"$sum": 1},
            "total_net": {"$sum": {"$cond": [{"$eq": ["$direction", "adjust_in"]}, "$qty", {"$multiply": ["$qty", -1]}]}},
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    by_position = await db.rahaza_fg_movements.aggregate(pos_pipeline).to_list(500)
    by_position = [
        {"position_barcode": r["_id"], "count": r["count"], "net_qty": round(r.get("total_net", 0), 4)}
        for r in by_position
    ]

    total = surplus_count + shortage_count
    return serialize_doc({
        "total_adjustments": total,
        "surplus_count": surplus_count, "surplus_qty": surplus_qty,
        "shortage_count": shortage_count, "shortage_qty": shortage_qty,
        "net_qty": round(surplus_qty - shortage_qty, 4),
        "by_operator": by_operator,
        "by_position_hotspots": by_position,
    })


@router.get("/adjustments/export-csv")
async def export_adjustments_csv(
    request: Request,
    token: Optional[str] = Query(None),
    operator: Optional[str] = None,
    position_barcode: Optional[str] = None,
    rack_id: Optional[str] = None,
    building_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    direction: Optional[str] = None,
):
    """Download CSV for compliance / audit."""
    await _auth_or_token(request, token)
    db = get_db()
    q = await _build_query(
        db, operator=operator, position_barcode=position_barcode,
        rack_id=rack_id, building_id=building_id,
        date_from=date_from, date_to=date_to, direction=direction,
    )
    rows = await db.rahaza_fg_movements.find(q, {"_id": 0}).sort("timestamp", -1).to_list(500)

    # Enrich positions
    pos_ids = [r.get("position_id") for r in rows if r.get("position_id")]
    pos_map = {}
    if pos_ids:
        async for p in db.wh_positions.find({"id": {"$in": pos_ids}}, {"_id": 0}):
            pos_map[p["id"]] = p

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Timestamp", "Session Ref", "Operator", "Building", "Zone", "Rack",
        "Position Barcode", "Position Label", "Material Code", "Direction",
        "Qty", "Notes",
    ])
    for r in rows:
        p = pos_map.get(r.get("position_id"), {})
        writer.writerow([
            r.get("timestamp").isoformat() if r.get("timestamp") else "",
            r.get("session_ref", ""),
            r.get("created_by", ""),
            p.get("building_code", ""),
            p.get("zone_code", ""),
            p.get("rack_code", ""),
            r.get("position_barcode", ""),
            p.get("label", ""),
            r.get("fg_code", ""),
            r.get("direction", ""),
            r.get("qty", 0),
            r.get("notes", ""),
        ])

    buf.seek(0)
    filename = f"wms_audit_adjustments_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _uid_for_audit():
    import uuid
    return uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════════════
# AI ROOT-CAUSE ANALYSIS — untuk hotspot posisi dengan adjustment berulang
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/hotspot/{position_barcode}/rca")
async def hotspot_rca(position_barcode: str, request: Request):
    """
    AI Root-Cause Analysis untuk posisi hotspot.
    Ambil N adjustment terakhir → Claude Sonnet analisis pola → rekomendasi action item.
    Butuh EMERGENT_LLM_KEY.
    """
    import os
    user = await require_auth(request)
    db = get_db()

    # Ambil last 30 adjustments untuk posisi ini
    rows = await db.rahaza_fg_movements.find(
        {"source": "opname_adjustment", "position_barcode": position_barcode},
        {"_id": 0}
    ).sort("timestamp", -1).limit(30).to_list(500)

    if len(rows) < 3:
        raise HTTPException(400, f"Posisi {position_barcode} belum punya cukup data (minimal 3 adjustment, ada {len(rows)}).")

    # Enrich position info
    pos = await db.wh_positions.find_one({"barcode": position_barcode}, {"_id": 0})
    pos_info = {
        "barcode": position_barcode,
        "label": pos.get("label") if pos else "",
        "building": pos.get("building_code") if pos else "",
        "zone": pos.get("zone_code") if pos else "",
        "rack": pos.get("rack_code") if pos else "",
        "current_material": pos.get("material_name") if pos else "",
        "current_qty": pos.get("qty") if pos else 0,
    }

    # Summarize data for LLM
    surplus_count = sum(1 for r in rows if r.get("direction") == "adjust_in")
    shortage_count = sum(1 for r in rows if r.get("direction") == "adjust_out")
    surplus_qty = sum(r.get("qty", 0) for r in rows if r.get("direction") == "adjust_in")
    shortage_qty = sum(r.get("qty", 0) for r in rows if r.get("direction") == "adjust_out")
    operators = list({r.get("created_by", "unknown") for r in rows})

    # Build timeline (last 10 to keep prompt concise)
    timeline = []
    for r in rows[:10]:
        timeline.append({
            "waktu": r.get("timestamp").isoformat() if r.get("timestamp") else "",
            "operator": r.get("created_by", ""),
            "arah": "Surplus" if r.get("direction") == "adjust_in" else "Shortage",
            "qty": r.get("qty"),
            "catatan": r.get("notes", ""),
            "session_ref": r.get("session_ref", ""),
        })

    # Get LLM key
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY belum dikonfigurasi.")

    prompt = f"""Kamu adalah analis WMS (Warehouse Management System) yang sangat berpengalaman.
Analisis pola adjustment stok di posisi berikut dan berikan root-cause analysis + rekomendasi action.

POSISI:
- Barcode: {pos_info['barcode']}
- Lokasi: {pos_info['building']} / {pos_info['zone']} / {pos_info['rack']}
- Label rak: {pos_info['label']}
- Material saat ini: {pos_info['current_material']} ({pos_info['current_qty']} unit)

DATA {len(rows)} ADJUSTMENT TERAKHIR:
- Total Surplus: {surplus_count}x dengan qty {surplus_qty:.2f}
- Total Shortage: {shortage_count}x dengan qty {shortage_qty:.2f}
- Net discrepancy: {(surplus_qty - shortage_qty):+.2f}
- Operator terlibat: {', '.join(operators)}

TIMELINE 10 ADJUSTMENT TERAKHIR:
{chr(10).join([f"  {i+1}. {t['waktu'][:19]} · {t['operator']} · {t['arah']} {t['qty']} · {t['catatan'][:80]}" for i, t in enumerate(timeline)])}

TUGAS:
Berikan analisis Root-Cause (RCA) dengan format JSON berikut:
{{
  "root_cause_hypothesis": "hipotesis penyebab utama dalam 1 kalimat (pilih salah satu: 'shrinkage/kehilangan', 'miscounting operator', 'mis-placement barang', 'systematic mislabel', 'fluktuasi normal')",
  "confidence": "tinggi|sedang|rendah",
  "reasoning": "penjelasan singkat 2-3 kalimat kenapa hipotesis ini paling mungkin",
  "risk_level": "tinggi|sedang|rendah",
  "recommended_actions": [
    "aksi 1 dalam bahasa Indonesia (imperative)",
    "aksi 2",
    "aksi 3"
  ]
}}

Balas HANYA dengan JSON valid tanpa markdown code fence. Gunakan Bahasa Indonesia."""

    try:
        from ai_llm import LlmChat, UserMessage
        chat = LlmChat(
            api_key=key,
            session_id=f"wms-rca-{position_barcode}-{user['id'][:8]}",
            system_message="Kamu adalah analis WMS yang memberikan RCA singkat, akurat, actionable dalam format JSON."
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text=prompt))
        raw = resp if isinstance(resp, str) else str(resp)
        # Strip any markdown fences just in case
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().startswith("json"):
                raw = raw.lstrip()[4:]
        import json as _json
        try:
            analysis = _json.loads(raw.strip())
        except Exception:
            analysis = {
                "root_cause_hypothesis": "Tidak terdeteksi — jawaban AI tidak valid JSON",
                "confidence": "rendah",
                "reasoning": raw[:500],
                "risk_level": "sedang",
                "recommended_actions": ["Retry analisa AI", "Review manual riwayat adjustment"],
            }
    except Exception as e:
        raise HTTPException(500, f"AI RCA gagal: {e}")

    # Log audit
    await db.wh_rca_audit.insert_one({
        "id": str(_uid_for_audit()),
        "position_barcode": position_barcode,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "analysis": analysis,
        "created_at": datetime.now(timezone.utc),
    })

    return {
        "position": pos_info,
        "data_points": len(rows),
        "stats": {
            "surplus_count": surplus_count, "shortage_count": shortage_count,
            "surplus_qty": round(surplus_qty, 4), "shortage_qty": round(shortage_qty, 4),
            "net_qty": round(surplus_qty - shortage_qty, 4),
            "operators": operators,
        },
        "analysis": analysis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _uid_for_audit():
    import uuid
    return uuid.uuid4()
