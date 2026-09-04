"""
PT Rahaza — Phase 21D: Machine Downtime Log

Endpoints (prefix /api/rahaza):
  GET  /downtime               — list events
  POST /downtime               — log event
  PUT  /downtime/{id}          — update (end, resolve, notes)
  GET  /downtime/summary?from=&to=&machine_id=  — aggregated summary
  GET  /downtime/reason-codes  — list standard reason codes
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from routes.shared import get_pagination_params, paginated_response
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-downtime"])


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


STANDARD_REASON_CODES = [
    {"code": "MECH-001", "name": "Kerusakan Mekanik",         "category": "Mekanik"},
    {"code": "MECH-002", "name": "Jarum Patah / Aus",          "category": "Mekanik"},
    {"code": "MECH-003", "name": "Tegangan Benang Macet",      "category": "Mekanik"},
    {"code": "MECH-004", "name": "Sensor Error",               "category": "Elektrik"},
    {"code": "MECH-005", "name": "Masalah Listrik",            "category": "Elektrik"},
    {"code": "MAT-001",  "name": "Ganti Material / Warna",     "category": "Material"},
    {"code": "MAT-002",  "name": "Benang Habis",               "category": "Material"},
    {"code": "PLAN-001", "name": "Ganti Model / Setup",        "category": "Perencanaan"},
    {"code": "PLAN-002", "name": "PM (Preventive Maintenance)","category": "Perencanaan"},
    {"code": "OP-001",   "name": "Operator Tidak Ada",          "category": "Operator"},
    {"code": "OP-002",   "name": "Operator Istirahat",          "category": "Operator"},
    {"code": "QC-001",   "name": "Henti karena Defect",         "category": "Kualitas"},
    {"code": "OTH-001",  "name": "Lainnya",                     "category": "Lainnya"},
]


@router.get("/downtime/reason-codes")
async def get_reason_codes(request: Request):
    await require_auth(request)
    return STANDARD_REASON_CODES


@router.get("/downtime")
async def list_downtime(
    request: Request,
    machine_id: Optional[str] = None,
    line_id: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
):
    await require_auth(request)
    db = get_db()
    q = {}
    if machine_id:
        q["machine_id"] = machine_id
    if line_id:
        q["line_id"] = line_id
    if status:
        q["status"] = status
    if from_ or to:
        q["start_at"] = {}
        if from_:
            q["start_at"]["$gte"] = from_
        if to:
            q["start_at"]["$lte"] = to + "T23:59:59Z"

    use_pagination = "page" in request.query_params
    if use_pagination:
        page, pg_limit, pg_skip = get_pagination_params(request, default_limit=50)
        total = await db.rahaza_machine_downtime.count_documents(q)
        rows = await db.rahaza_machine_downtime.find(q, {"_id": 0}).sort("start_at", -1).skip(pg_skip).limit(pg_limit).to_list(length=10000)
    else:
        rows = await db.rahaza_machine_downtime.find(q, {"_id": 0}).sort("start_at", -1).limit(limit).to_list(500)

    # Enrich with machine name
    m_ids = list({r.get("machine_id") for r in rows if r.get("machine_id")})
    machines = await db.rahaza_machines.find({"id": {"$in": m_ids}}, {"_id": 0}).to_list(500) if m_ids else []
    m_map = {m["id"]: m for m in machines}

    for r in rows:
        m = m_map.get(r.get("machine_id"), {})
        r["machine_code"] = m.get("code", "")
        r["machine_name"] = m.get("name", "")
        if r.get("status") == "open" and r.get("start_at"):
            try:
                start = datetime.fromisoformat(r["start_at"].replace("Z", "+00:00"))
                r["duration_min"] = int((_now() - start).total_seconds() / 60)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    if use_pagination:
        return paginated_response(serialize_doc(rows), total, page, pg_limit)
    return rows


@router.post("/downtime")
async def create_downtime(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    if not body.get("machine_id"):
        raise HTTPException(400, "machine_id wajib diisi.")
    now_iso = _now().isoformat()
    doc = {
        "id": _uid(),
        "machine_id": body["machine_id"],
        "line_id": body.get("line_id"),
        "reason_code": body.get("reason_code") or "OTH-001",
        "reason_name": body.get("reason_name") or "Lainnya",
        "start_at": body.get("start_at") or now_iso,
        "end_at": body.get("end_at"),
        "duration_min": body.get("duration_min"),
        "notes": body.get("notes") or "",
        "status": "closed" if body.get("end_at") else "open",
        "reported_by": user.get("id"),
        "created_at": now_iso,
    }
    # Auto-calculate duration if both times provided
    if doc["start_at"] and doc["end_at"]:
        try:
            s = datetime.fromisoformat(doc["start_at"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(doc["end_at"].replace("Z", "+00:00"))
            doc["duration_min"] = max(0, int((e - s).total_seconds() / 60))
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    await db.rahaza_machine_downtime.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/downtime/{dt_id}")
async def update_downtime(dt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now().isoformat()
    # Auto-close if end_at provided
    if body.get("end_at"):
        body["status"] = "closed"
        existing = await db.rahaza_machine_downtime.find_one({"id": dt_id}, {"_id": 0})
        if existing and existing.get("start_at"):
            try:
                s = datetime.fromisoformat(existing["start_at"].replace("Z", "+00:00"))
                e = datetime.fromisoformat(body["end_at"].replace("Z", "+00:00"))
                body["duration_min"] = max(0, int((e - s).total_seconds() / 60))
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    res = await db.rahaza_machine_downtime.update_one({"id": dt_id}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Downtime event tidak ditemukan.")
    return serialize_doc(await db.rahaza_machine_downtime.find_one({"id": dt_id}, {"_id": 0}))


@router.delete("/downtime/{dt_id}")
async def delete_downtime(dt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await db.rahaza_machine_downtime.delete_one({"id": dt_id})
    return {"ok": True}


@router.get("/downtime/summary")
async def downtime_summary(
    request: Request,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    machine_id: Optional[str] = None,
    line_id: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    if not from_:
        from_ = (date.today() - timedelta(days=30)).isoformat()
    if not to:
        to = date.today().isoformat()
    q = {"start_at": {"$gte": from_, "$lte": to + "T23:59:59Z"}}
    if machine_id:
        q["machine_id"] = machine_id
    if line_id:
        q["line_id"] = line_id

    events = await db.rahaza_machine_downtime.find(q, {"_id": 0}).to_list(500)
    total_events = len(events)
    total_min = sum(e.get("duration_min") or 0 for e in events)

    # By reason
    by_reason: dict = {}
    for e in events:
        rc = e.get("reason_code", "OTH-001")
        if rc not in by_reason:
            by_reason[rc] = {"reason_code": rc, "reason_name": e.get("reason_name", rc), "count": 0, "total_min": 0}
        by_reason[rc]["count"] += 1
        by_reason[rc]["total_min"] += e.get("duration_min") or 0

    # By machine
    by_machine: dict = {}
    m_ids = list({e.get("machine_id") for e in events if e.get("machine_id")})
    machines = await db.rahaza_machines.find({"id": {"$in": m_ids}}, {"_id": 0}).to_list(500) if m_ids else []
    m_map = {m["id"]: m for m in machines}
    for e in events:
        mid = e.get("machine_id", "unknown")
        if mid not in by_machine:
            m = m_map.get(mid, {})
            by_machine[mid] = {"machine_id": mid, "machine_name": m.get("name", mid), "count": 0, "total_min": 0}
        by_machine[mid]["count"] += 1
        by_machine[mid]["total_min"] += e.get("duration_min") or 0

    return {
        "from": from_, "to": to,
        "total_events": total_events,
        "total_downtime_min": total_min,
        "total_downtime_hours": round(total_min / 60, 1),
        "by_reason": sorted(by_reason.values(), key=lambda x: x["total_min"], reverse=True),
        "by_machine": sorted(by_machine.values(), key=lambda x: x["total_min"], reverse=True)[:10],
    }
