# ruff: noqa: F401
"""
rahaza_payroll_profiles.py — Payroll Profile Management
Extracted from rahaza_payroll.py (1539 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #4
Endpoints: GET /payroll-profiles, GET /payroll-profiles/{id}, POST /payroll-profiles, PUT /payroll-profiles/{id}, DELETE /payroll-profiles/{id}
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_payroll_shared import (
    _uid, _now, VALID_SCHEMES, VALID_PERIOD_TYPES, VALID_RUN_STATUS,
    _get_applicable_allowances, _require_hr,
)
from routes.rahaza_posting import post_payroll_run
from utils.saga import SagaExecutor
import uuid
import io
import csv
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-payroll-profiles"])

@router.get("/payroll-profiles")
async def list_profiles(request: Request, employee_id: Optional[str] = None, active_only: bool = True):
    await require_auth(request)
    db = get_db()
    q = {}
    if active_only:
        q["active"] = True
    if employee_id:
        q["employee_id"] = employee_id
    rows = await db.rahaza_payroll_profiles.find(q, {"_id": 0}).to_list(500)
    # Enrich with employee info
    emp_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0}).to_list(500) if emp_ids else []
    e_map = {e["id"]: e for e in emps}
    for r in rows:
        e = e_map.get(r.get("employee_id")) or {}
        r["employee_code"] = e.get("employee_code")
        r["employee_name"] = e.get("name")
    rows.sort(key=lambda r: r.get("employee_code") or "")
    return serialize_doc(rows)


@router.get("/payroll-profiles/{employee_id}")
async def get_profile(employee_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    row = await db.rahaza_payroll_profiles.find_one({"employee_id": employee_id, "active": True}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Profile payroll belum dibuat untuk pegawai ini.")
    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0}) or {}
    row["employee_code"] = emp.get("employee_code")
    row["employee_name"] = emp.get("name")
    return serialize_doc(row)


def _normalize_profile(body: dict) -> dict:
    pay_scheme = (body.get("pay_scheme") or "monthly").lower()
    period_type = (body.get("period_type") or "monthly").lower()
    if pay_scheme not in VALID_SCHEMES:
        raise HTTPException(400, f"pay_scheme harus salah satu: {VALID_SCHEMES}")
    if period_type not in VALID_PERIOD_TYPES:
        raise HTTPException(400, f"period_type harus salah satu: {VALID_PERIOD_TYPES}")
    cutoff = body.get("cutoff_config") or {}
    # Defaults
    if period_type == "weekly" and "week_start_day" not in cutoff:
        cutoff["week_start_day"] = 1  # Monday
    if period_type == "monthly" and "start_day" not in cutoff:
        cutoff["start_day"] = 1  # 1st of month
    # Validate ranges
    wsd = cutoff.get("week_start_day")
    if wsd is not None and (not isinstance(wsd, int) or not (0 <= wsd <= 6)):
        raise HTTPException(400, "week_start_day harus 0..6 (0=Senin..6=Minggu)")
    sd = cutoff.get("start_day")
    if sd is not None and (not isinstance(sd, int) or not (1 <= sd <= 28)):
        raise HTTPException(400, "start_day harus 1..28")
    pcs_rates = body.get("pcs_process_rates") or []
    norm_pcs_rates = []
    for r in pcs_rates:
        if not r.get("process_id"):
            continue
        norm_pcs_rates.append({
            "process_id": r["process_id"],
            "process_code": (r.get("process_code") or "").upper(),
            "rate": float(r.get("rate") or 0),
        })
    return {
        "employee_id": body.get("employee_id"),
        "pay_scheme": pay_scheme,
        "period_type": period_type,
        "cutoff_config": cutoff,
        "base_rate": float(body.get("base_rate") or 0),
        "overtime_rate": float(body.get("overtime_rate") or 0),
        "pcs_process_rates": norm_pcs_rates,
        "notes": body.get("notes") or "",
    }


@router.post("/payroll-profiles")
async def upsert_profile(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()
    emp_id = body.get("employee_id")
    if not emp_id:
        raise HTTPException(400, "employee_id wajib.")
    emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, f"Pegawai dengan id={emp_id} tidak ditemukan.")
    doc = _normalize_profile(body)
    existing = await db.rahaza_payroll_profiles.find_one({"employee_id": emp_id, "active": True}, {"_id": 0})
    now = _now()
    doc.update({
        "active": True,
        "updated_at": now,
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    })
    if existing:
        await db.rahaza_payroll_profiles.update_one({"id": existing["id"]}, {"$set": doc})
        out = await db.rahaza_payroll_profiles.find_one({"id": existing["id"]}, {"_id": 0})
    else:
        doc["id"] = _uid()
        doc["created_at"] = now
        doc["created_by"] = user["id"]
        doc["created_by_name"] = user.get("name", "")
        await db.rahaza_payroll_profiles.insert_one(doc)
        out = await db.rahaza_payroll_profiles.find_one({"id": doc["id"]}, {"_id": 0})
    await log_activity(user["id"], user.get("name", ""), "upsert", "rahaza.payroll_profile", emp_id)
    out["employee_code"] = emp.get("employee_code")
    out["employee_name"] = emp.get("name")
    return serialize_doc(out)


@router.put("/payroll-profiles/{pid}")
async def update_profile(pid: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    existing = await db.rahaza_payroll_profiles.find_one({"id": pid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Profile tidak ditemukan.")
    body = await request.json()
    body["employee_id"] = existing["employee_id"]  # cannot change
    doc = _normalize_profile(body)
    doc.update({
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    })
    await db.rahaza_payroll_profiles.update_one({"id": pid}, {"$set": doc})
    out = await db.rahaza_payroll_profiles.find_one({"id": pid}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/payroll-profiles/{pid}")
async def delete_profile(pid: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    res = await db.rahaza_payroll_profiles.update_one({"id": pid, "active": True}, {"$set": {"active": False, "updated_at": _now(), "updated_by": user["id"]}})
    if res.matched_count == 0:
        raise HTTPException(404, "Profile tidak ditemukan atau sudah nonaktif.")
    return {"status": "deleted"}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ FASE 8c — PAYROLL RUN & PAYSLIP                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _date_range_filter(from_iso: str, to_iso: str) -> dict:
    return {"$gte": from_iso, "$lte": to_iso}


async def _generate_run_number(db) -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    from utils.counters import gen_prefixed_number
    today = date.today().strftime("%Y%m%d")
    return await gen_prefixed_number(db, "rahaza_payroll_runs", "run_number", f"PR-{today}-", 3)


# FASE 15 — fungsi `_compute_payslip_for_employee` DIHAPUS dari modul ini.
# Dulu ada DUA versi bernama sama: yang di sini punya PPh21/BPJS/LWOP tapi TIDAK
# PERNAH DIPANGGIL, sementara `rahaza_payroll_runs.py` memakai versi di
# `rahaza_payroll_shared.py` yang TIDAK punya pajak/BPJS ⇒ potongan pajak & BPJS
# hilang dari payroll run sungguhan. Sekarang SSOT-nya satu, di shared.py
# (sudah diimpor di baris `from routes.rahaza_payroll_shared import ...` di atas).


