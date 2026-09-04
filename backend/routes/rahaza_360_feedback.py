"""
CV. Dewi Aditya — 360 Degree Feedback (Phase 9.6 P2)

Multi-source performance feedback: self + manager + peers + subordinates.

Collection: rahaza_360_cycles
  { cycle_id, period_name, target_employee_id, target_name,
    reviewers: [ { reviewer_id, reviewer_name, relationship (self|manager|peer|subordinate),
                   status (pending|submitted), submitted_at, responses: [...] } ],
    status (open | closed), created_by, created_at, closed_at }

Question template (stored inline per cycle):
  questions: [ { id, text, category (performance|collaboration|leadership|technical),
                 min_score, max_score, require_comment } ]
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from utils.waktu import now_wib

router = APIRouter(prefix="/api/rahaza/360-feedback", tags=["rahaza-360-feedback"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(d):
    if not d:
        return None
    d = dict(d)
    d.pop("_id", None)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


DEFAULT_QUESTIONS = [
    {"id": "q1", "text": "Seberapa efektif orang ini mencapai target pekerjaan?", "category": "performance", "min_score": 1, "max_score": 5},
    {"id": "q2", "text": "Seberapa baik kualitas pekerjaan yang dihasilkan?", "category": "performance", "min_score": 1, "max_score": 5},
    {"id": "q3", "text": "Seberapa baik kolaborasi dengan rekan tim?", "category": "collaboration", "min_score": 1, "max_score": 5},
    {"id": "q4", "text": "Seberapa proaktif dan inisiatifnya?", "category": "leadership", "min_score": 1, "max_score": 5},
    {"id": "q5", "text": "Seberapa kompeten skill teknis untuk perannya?", "category": "technical", "min_score": 1, "max_score": 5},
    {"id": "q6", "text": "Kekuatan utama orang ini?", "category": "open", "type": "text", "require_comment": True},
    {"id": "q7", "text": "Area yang perlu ditingkatkan?", "category": "open", "type": "text", "require_comment": True},
]


@router.post("/cycles")
async def create_cycle(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    target_id = body.get("target_employee_id")
    if not target_id:
        raise HTTPException(400, "target_employee_id wajib.")

    target = await db.rahaza_employees.find_one({"id": target_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Target karyawan tidak ditemukan.")

    reviewers_input = body.get("reviewers") or []
    reviewers = []
    for r in reviewers_input:
        reviewers.append({
            "reviewer_id": r.get("reviewer_id"),
            "reviewer_name": r.get("reviewer_name", ""),
            "relationship": r.get("relationship", "peer"),
            "status": "pending",
            "submitted_at": None,
            "responses": [],
        })

    doc = {
        "cycle_id": _uid(),
        "period_name": body.get("period_name") or f"360 Review - {target.get('name','')} - {now_wib().strftime('%Y-Q')}{(now_wib().month - 1) // 3 + 1}",
        "target_employee_id": target_id,
        "target_employee_name": target.get("name", ""),
        "target_employee_code": target.get("employee_code", ""),
        "questions": body.get("questions") or DEFAULT_QUESTIONS,
        "reviewers": reviewers,
        "status": "open",
        "deadline": body.get("deadline") or None,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "closed_at": None,
    }
    await db.rahaza_360_cycles.insert_one(doc)
    return {"ok": True, "cycle": _s(doc)}


@router.get("/cycles")
async def list_cycles(request: Request, status: Optional[str] = None,
                       target_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    filt = {}
    if status:
        filt["status"] = status
    if target_id:
        filt["target_employee_id"] = target_id
    docs = await db.rahaza_360_cycles.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"ok": True, "cycles": [_s(d) for d in docs]}


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_360_cycles.find_one({"cycle_id": cycle_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Cycle tidak ditemukan.")
    return {"ok": True, "cycle": _s(doc)}


@router.post("/cycles/{cycle_id}/submit")
async def submit_feedback(cycle_id: str, request: Request):
    """Reviewer submits their responses for a cycle."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    cycle = await db.rahaza_360_cycles.find_one({"cycle_id": cycle_id}, {"_id": 0})
    if not cycle:
        raise HTTPException(404, "Cycle tidak ditemukan.")
    if cycle.get("status") != "open":
        raise HTTPException(400, "Cycle sudah ditutup.")

    responses = body.get("responses") or []
    # Find reviewer entry
    reviewers = cycle.get("reviewers") or []
    found = False
    for r in reviewers:
        if r.get("reviewer_id") == user["id"]:
            r["status"] = "submitted"
            r["submitted_at"] = _now().isoformat()
            r["responses"] = responses
            found = True
            break
    if not found:
        raise HTTPException(403, "Anda bukan reviewer terdaftar untuk cycle ini.")

    await db.rahaza_360_cycles.update_one(
        {"cycle_id": cycle_id}, {"$set": {"reviewers": reviewers}}
    )
    return {"ok": True}


@router.post("/cycles/{cycle_id}/close")
async def close_cycle(cycle_id: str, request: Request):
    """HR closes cycle, compute aggregate scores."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr", "manager"):
        raise HTTPException(403, "Hanya HR yang dapat tutup cycle.")
    db = get_db()

    cycle = await db.rahaza_360_cycles.find_one({"cycle_id": cycle_id}, {"_id": 0})
    if not cycle:
        raise HTTPException(404, "Cycle tidak ditemukan.")

    # Aggregate: average score per question from submitted reviewers
    aggregate = {}
    for q in cycle.get("questions", []):
        if q.get("type") == "text":
            continue
        qid = q["id"]
        scores = []
        by_relation = {}
        for r in cycle.get("reviewers", []):
            if r.get("status") != "submitted":
                continue
            for resp in r.get("responses", []):
                if resp.get("question_id") == qid and isinstance(resp.get("score"), (int, float)):
                    scores.append(resp["score"])
                    rel = r.get("relationship", "peer")
                    by_relation.setdefault(rel, []).append(resp["score"])
        avg = round(sum(scores) / len(scores), 2) if scores else 0
        aggregate[qid] = {
            "question": q["text"],
            "category": q.get("category", ""),
            "avg_score": avg,
            "total_responses": len(scores),
            "by_relation": {k: round(sum(v) / len(v), 2) for k, v in by_relation.items()},
        }

    await db.rahaza_360_cycles.update_one(
        {"cycle_id": cycle_id},
        {"$set": {"status": "closed", "closed_at": _now(),
                  "aggregate": aggregate, "closed_by": user.get("name", "")}}
    )
    return {"ok": True, "aggregate": aggregate}
