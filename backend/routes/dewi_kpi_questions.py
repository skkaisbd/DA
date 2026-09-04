# ruff: noqa: F401
"""
dewi_kpi_questions.py — Question Bank Management
Extracted from dewi_kpi.py (2729 LOC monolith)

Refactored: Session #11.19 Final - CAREFUL APPROACH
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.dewi_kpi_shared import (
    _uid, _now, _s, _grade,
    _require_hr, _get_linked_employee,
    _calc_section_score, _calc_attitude_score, _calc_absensi_score,
    DEFAULT_QUESTIONS,
)
from routes.shared import get_pagination_params, paginated_response
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-questions"])

@router.get("/questions")
async def list_questions(
    request: Request,
    eval_type: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    filt = {"is_active": True}
    if eval_type:
        filt["eval_type"] = eval_type
    sp = request.query_params
    # Dual-mode: paginated or full list
    if sp.get("page") or sp.get("limit"):
        page, limit, skip = get_pagination_params(request, default_limit=50)
        total = await db.da_kpi_questions.count_documents(filt)
        docs = await db.da_kpi_questions.find(filt, {"_id": 0}).sort([("eval_type", 1), ("order", 1)]).skip(skip).limit(limit).to_list(limit)
        return paginated_response([_s(d) for d in docs], total, page, limit)
    docs = await db.da_kpi_questions.find(filt, {"_id": 0}).sort([("eval_type", 1), ("order", 1)]).to_list(500)
    return {"ok": True, "questions": [_s(d) for d in docs]}


@router.post("/questions")
async def create_question(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    eval_type = body.get("eval_type")
    valid_types = ["self", "peer", "supervisor_to_staff", "staff_to_supervisor"]
    if eval_type not in valid_types:
        raise HTTPException(400, f"eval_type harus salah satu: {valid_types}")

    doc = {
        "question_id": _uid(),
        "eval_type": eval_type,
        "category": (body.get("category") or "").strip(),
        "category_weight": float(body.get("category_weight") or 0.10),
        "question_text": (body.get("question_text") or "").strip(),
        "order": int(body.get("order") or 99),
        "is_active": True,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    if not doc["question_text"] or not doc["category"]:
        raise HTTPException(400, "question_text dan category wajib diisi.")

    await db.da_kpi_questions.insert_one(doc)
    return {"ok": True, "question": _s(doc)}


@router.put("/questions/{question_id}")
async def update_question(question_id: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    allowed = ["category", "category_weight", "question_text", "order", "is_active"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = _now()
    upd["updated_by"] = user["id"]

    res = await db.da_kpi_questions.update_one({"question_id": question_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Pertanyaan tidak ditemukan.")
    doc = await db.da_kpi_questions.find_one({"question_id": question_id}, {"_id": 0})
    return {"ok": True, "question": _s(doc)}


@router.delete("/questions/{question_id}")
async def delete_question(question_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    await db.da_kpi_questions.update_one(
        {"question_id": question_id},
        {"$set": {"is_active": False, "updated_at": _now()}}
    )
    return {"ok": True}


@router.post("/questions/seed-defaults")
async def seed_default_questions(request: Request):
    user = await _require_hr(request)
    db = get_db()
    existing = await db.da_kpi_questions.count_documents({})
    if existing > 0:
        return {"ok": True, "message": f"Bank soal sudah terisi ({existing} soal). Tidak di-seed ulang."}

    docs = []
    for q in DEFAULT_QUESTIONS:
        docs.append({
            "question_id": _uid(),
            **q,
            "is_active": True,
            "created_by": user["id"],
            "created_at": _now(),
            "updated_at": _now(),
        })
    await db.da_kpi_questions.insert_many(docs)
    return {"ok": True, "seeded": len(docs), "message": "Bank soal default DA berhasil di-seed."}


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORM SCORES (HR / SUPERVISOR)
# ═══════════════════════════════════════════════════════════════════════════════

