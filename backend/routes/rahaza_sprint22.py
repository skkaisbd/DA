"""
Sprint 22 — Supervisor & PPIC Power Tools
==========================================
Routes:
  Bulk MI Generator:
    POST /api/rahaza/supervisor/bulk-mi/preview     — preview MIs for multiple WOs
    POST /api/rahaza/supervisor/bulk-mi/generate    — generate MIs for multiple WOs

  Auto-assign Template:
    GET  /api/rahaza/supervisor/assignments/yesterday   — yesterday's assignments as template
    POST /api/rahaza/supervisor/assignments/bulk        — bulk-create assignments

  Line Balancing:
    GET  /api/rahaza/supervisor/line-balance            — balance analysis per line+shift

Author: Sprint 22
"""
# ruff: noqa: E741
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from core.stock_schema import read_qty
from auth import require_auth, log_activity
from utils.counters import next_counter_batch
from typing import Optional
import uuid
import logging
from datetime import datetime, timezone, date, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rahaza/supervisor", tags=["sprint22"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _today() -> str:
    return date.today().isoformat()


def _yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


async def _require_supervisor(request: Request):
    """Require supervisor, manager, or admin access."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    allowed = ("superadmin", "admin", "manager", "manager_produksi", "supervisor",
               "staff_produksi", "owner")
    if role in allowed:
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "production.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh akses Supervisor/Manager Produksi.")


# ────────────────────────────────────────────────────────────────────────────
# BULK MI GENERATOR
# ────────────────────────────────────────────────────────────────────────────

@router.post("/bulk-mi/preview")
async def preview_bulk_mi(request: Request):
    """
    Preview what MIs would be generated for a list of WO IDs.
    Returns per-WO: materials needed, availability, missing materials.
    """
    await _require_supervisor(request)
    db = get_db()
    body = await request.json()
    wo_ids: list = body.get("wo_ids") or []
    if not wo_ids:
        raise HTTPException(400, "wo_ids harus diisi.")
    if len(wo_ids) > 50:
        raise HTTPException(400, "Maksimum 50 WO per batch.")

    # Fetch WOs
    wos = await db.rahaza_work_orders.find({"id": {"$in": wo_ids}}, {"_id": 0}).to_list(500)
    wo_map = {w["id"]: w for w in wos}

    # Fetch current stock summary (material_id → total qty)
    stock_docs = await db.rahaza_material_stock.find({}, {"_id": 0, "material_id": 1, "qty": 1, "total_qty": 1, "quantity": 1}).to_list(500)
    stock_avail: dict = {}
    for s in stock_docs:
        mid = s.get("material_id")
        stock_avail[mid] = stock_avail.get(mid, 0.0) + read_qty(s)

    # Fetch all materials for name lookup
    all_mats = await db.rahaza_materials.find({"active": True}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1}).to_list(500)
    mat_map = {m["id"]: m for m in all_mats}

    # Batch prefetch existing draft/pending MIs for all WO ids
    existing_mi_map = {}
    if wo_ids:
        async for d in db.rahaza_material_issues.find({
            "work_order_id": {"$in": wo_ids},
            "status": {"$in": ["draft", "pending", "issued"]},
        }, {"_id": 0}):
            existing_mi_map[d["work_order_id"]] = d
    # Batch prefetch BOMs by (model_id, size_id) pairs for WOs without bom_snapshot
    pending_bom_keys = []
    for wid in wo_ids:
        w = wo_map.get(wid)
        if w and not (w.get("bom_snapshot") or []):
            pending_bom_keys.append((w.get("model_id"), w.get("size_id")))
    bom_by_key = {}
    if pending_bom_keys:
        m_ids = list({k[0] for k in pending_bom_keys if k[0]})
        s_ids = list({k[1] for k in pending_bom_keys if k[1]})
        if m_ids and s_ids:
            async for b in db.rahaza_boms.find({
                "model_id": {"$in": m_ids}, "size_id": {"$in": s_ids}, "active": True
            }, {"_id": 0}):
                bom_by_key[(b.get("model_id"), b.get("size_id"))] = b

    results = []
    for wo_id in wo_ids:
        wo = wo_map.get(wo_id)
        if not wo:
            results.append({"wo_id": wo_id, "error": "WO tidak ditemukan"})
            continue
        if wo.get("status") not in ("released", "in_progress"):
            results.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "error": f"WO status '{wo.get('status')}' tidak bisa generate MI (harus released/in_progress)"})
            continue

        # Check for existing draft/pending MI (from prefetched map)
        existing_mi = existing_mi_map.get(wo_id)
        if existing_mi:
            results.append({
                "wo_id": wo_id, "wo_number": wo.get("wo_number"),
                "warning": f"Sudah ada MI {existing_mi.get('mi_number')} (status: {existing_mi.get('status')}). MI baru tidak akan dibuat.",
                "skip": True,
            })
            continue

        # Resolve BOM (bom_snapshot on WO OR active BOM from DB)
        bom_items = []
        bom_snap = wo.get("bom_snapshot") or []
        if bom_snap:
            # bom_snapshot may use "qty" or "quantity" field
            bom_items = bom_snap
        else:
            bom = bom_by_key.get((wo.get("model_id"), wo.get("size_id")))
            if bom:
                bom_items = bom.get("materials") or bom.get("items") or []

        if not bom_items:
            results.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "warning": "Tidak ada BOM", "items": []})
            continue

        qty_wo = float(wo.get("qty") or 0)
        items_preview = []
        all_available = True
        for bi in bom_items:
            mid = bi.get("material_id")
            mat = mat_map.get(mid, {})
            # Support both "quantity" (from BOM.materials) and "qty" (from bom_snapshot)
            qty_per_unit = float(bi.get("quantity") or bi.get("qty") or 0)
            qty_needed = round(qty_per_unit * qty_wo, 4)
            avail = stock_avail.get(mid, 0.0)
            shortage = round(max(0, qty_needed - avail), 4)
            if shortage > 0:
                all_available = False
            items_preview.append({
                "material_id": mid,
                "material_code": mat.get("code", "?"),
                "material_name": mat.get("name", "?"),
                "unit": mat.get("unit", ""),
                "qty_required": qty_needed,
                "qty_available": round(avail, 4),
                "shortage": shortage,
                "can_fulfill": shortage == 0,
            })

        results.append({
            "wo_id": wo_id,
            "wo_number": wo.get("wo_number"),
            "model_code": wo.get("model_code"),
            "qty": qty_wo,
            "items": items_preview,
            "all_available": all_available,
            "skip": False,
        })

    return {"preview": results, "total_wo": len(wo_ids), "ready_count": sum(1 for r in results if not r.get("skip") and not r.get("error") and r.get("all_available"))}


@router.post("/bulk-mi/generate")
async def generate_bulk_mi(request: Request):
    """
    Generate Material Issues for multiple WOs in one batch.
    Skips WOs with existing MI or unavailable materials (if strict=True).
    """
    user = await _require_supervisor(request)
    db = get_db()
    body = await request.json()
    wo_ids: list = body.get("wo_ids") or []
    notes: str = body.get("notes") or "Bulk MI — Sprint 22"
    skip_shortage: bool = body.get("skip_shortage", False)  # If True, create MI even with shortage

    if not wo_ids:
        raise HTTPException(400, "wo_ids harus diisi.")
    if len(wo_ids) > 50:
        raise HTTPException(400, "Maksimum 50 WO per batch.")

    # Get next MI counter range — atomic batch reservation via unified counters SSOT
    start_seq = await next_counter_batch(db, "mi_number", count=len(wo_ids), namespace="rahaza")

    wos = await db.rahaza_work_orders.find({"id": {"$in": wo_ids}}, {"_id": 0}).to_list(500)
    wo_map = {w["id"]: w for w in wos}

    stock_docs = await db.rahaza_material_stock.find({}, {"_id": 0, "material_id": 1, "qty": 1, "total_qty": 1, "quantity": 1}).to_list(500)
    stock_avail: dict = {}
    for s in stock_docs:
        mid = s.get("material_id")
        stock_avail[mid] = stock_avail.get(mid, 0.0) + read_qty(s)

    mat_map = {m["id"]: m for m in await db.rahaza_materials.find({"active": True}, {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1}).to_list(500)}

    # Batch prefetch: existing MIs and BOMs (eliminate N+1)
    existing_mi_map2 = {}
    if wo_ids:
        async for d in db.rahaza_material_issues.find({
            "work_order_id": {"$in": wo_ids},
            "status": {"$in": ["draft", "pending", "issued"]},
        }, {"_id": 0}):
            existing_mi_map2[d["work_order_id"]] = d
    bom_keys2 = []
    for wid in wo_ids:
        w = wo_map.get(wid)
        if w and not (w.get("bom_snapshot") or []):
            bom_keys2.append((w.get("model_id"), w.get("size_id")))
    bom_by_key2 = {}
    if bom_keys2:
        m_ids2 = list({k[0] for k in bom_keys2 if k[0]})
        s_ids2 = list({k[1] for k in bom_keys2 if k[1]})
        if m_ids2 and s_ids2:
            async for b in db.rahaza_boms.find({
                "model_id": {"$in": m_ids2}, "size_id": {"$in": s_ids2}, "active": True
            }, {"_id": 0}):
                bom_by_key2[(b.get("model_id"), b.get("size_id"))] = b

    created = []
    skipped = []
    seq = start_seq

    for wo_id in wo_ids:
        wo = wo_map.get(wo_id)
        if not wo:
            skipped.append({"wo_id": wo_id, "reason": "WO tidak ditemukan"})
            continue
        if wo.get("status") not in ("released", "in_progress"):
            skipped.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "reason": f"Status '{wo.get('status')}'"})
            continue

        existing = existing_mi_map2.get(wo_id)
        if existing:
            skipped.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "reason": f"Sudah ada MI {existing.get('mi_number')}"})
            continue

        bom_items = wo.get("bom_snapshot") or []
        if not bom_items:
            bom = bom_by_key2.get((wo.get("model_id"), wo.get("size_id")))
            bom_items = (bom or {}).get("materials") or (bom or {}).get("items") or []

        if not bom_items:
            skipped.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "reason": "Tidak ada BOM"})
            continue

        qty_wo = float(wo.get("qty") or 0)
        items = []
        has_shortage = False
        for bi in bom_items:
            mid = bi.get("material_id")
            mat = mat_map.get(mid, {})
            qty_per_unit = float(bi.get("quantity") or bi.get("qty") or 0)
            qty_needed = round(qty_per_unit * qty_wo, 4)
            avail = stock_avail.get(mid, 0.0)
            if qty_needed > avail:
                has_shortage = True
            items.append({
                "material_id": mid,
                "material_code": mat.get("code", "?"),
                "material_name": mat.get("name", "?"),
                "unit": mat.get("unit", ""),
                "qty_required": qty_needed,
            })

        if has_shortage and not skip_shortage:
            skipped.append({"wo_id": wo_id, "wo_number": wo.get("wo_number"), "reason": "Stok tidak cukup (gunakan skip_shortage=true untuk tetap buat MI)"})
            continue

        mi_num = f"BMI-{str(seq).zfill(6)}"
        doc = {
            "id": _uid(),
            "mi_number": mi_num,
            "work_order_id": wo_id,
            "wo_number": wo.get("wo_number"),
            "model_code": wo.get("model_code"),
            "status": "draft",
            "items": items,
            "notes": notes,
            "issued_by": user["id"],
            "issued_by_name": user.get("name", ""),
            "bulk_batch": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.rahaza_material_issues.insert_one(doc)
        created.append({"mi_number": mi_num, "wo_number": wo.get("wo_number"), "wo_id": wo_id, "item_count": len(items)})
        seq += 1

    await log_activity(user["id"], user.get("name", ""), "bulk_mi", "supervisor", f"Generated {len(created)} MIs")
    return {
        "created": created, "skipped": skipped,
        "total_created": len(created), "total_skipped": len(skipped),
    }


# ────────────────────────────────────────────────────────────────────────────
# AUTO-ASSIGN TEMPLATE
# ────────────────────────────────────────────────────────────────────────────

@router.get("/assignments/yesterday")
async def get_yesterday_template(request: Request, shift_id: Optional[str] = None):
    """Returns yesterday's line assignments as a template for today."""
    await _require_supervisor(request)
    db = get_db()
    yesterday = _yesterday()
    q = {"assign_date": yesterday}
    if shift_id:
        q["shift_id"] = shift_id
    rows = await db.rahaza_line_assignments.find(q, {"_id": 0}).to_list(500)

    # Enrich with names
    line_ids = list({r.get("line_id") for r in rows if r.get("line_id")})
    emp_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    shift_ids = list({r.get("shift_id") for r in rows if r.get("shift_id")})

    lines = await db.rahaza_lines.find({"id": {"$in": line_ids}}, {"_id": 0}).to_list(500) if line_ids else []
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0}).to_list(500) if emp_ids else []
    shifts = await db.rahaza_shifts.find({"id": {"$in": shift_ids}}, {"_id": 0}).to_list(500) if shift_ids else []

    line_map = {l["id"]: l["name"] for l in lines}
    emp_map = {e["id"]: e["name"] for e in emps}
    shift_map = {s["id"]: s["name"] for s in shifts}

    template = []
    for r in rows:
        template.append({
            "line_id": r.get("line_id"),
            "line_name": line_map.get(r.get("line_id"), "?"),
            "employee_id": r.get("employee_id"),
            "employee_name": emp_map.get(r.get("employee_id"), "?"),
            "shift_id": r.get("shift_id"),
            "shift_name": shift_map.get(r.get("shift_id"), "?"),
            "model_id": r.get("model_id"),
            "size_id": r.get("size_id"),
            "target_pcs": r.get("target_pcs", 0),
            "notes": r.get("notes", ""),
        })

    return {
        "source_date": yesterday,
        "target_date": _today(),
        "assignments": template,
        "count": len(template),
    }


@router.post("/assignments/bulk")
async def bulk_create_assignments(request: Request):
    """
    Bulk-create line assignments for today (or specified date).
    Used by "Copy Yesterday" feature.
    """
    user = await _require_supervisor(request)
    db = get_db()
    body = await request.json()
    assign_date = body.get("assign_date") or _today()
    assignments: list = body.get("assignments") or []
    overwrite: bool = body.get("overwrite", False)

    if not assignments:
        raise HTTPException(400, "assignments harus diisi.")
    if len(assignments) > 200:
        raise HTTPException(400, "Maksimum 200 assignment per batch.")

    # Batch prefetch existing assignments matching all (line, emp, shift) tuples
    valid_assigns = [a for a in assignments
                       if a.get("line_id") and a.get("employee_id") and a.get("shift_id")]
    line_ids_set = list({a["line_id"] for a in valid_assigns})
    emp_ids_set = list({a["employee_id"] for a in valid_assigns})
    shift_ids_set = list({a["shift_id"] for a in valid_assigns})
    existing_assign_map = {}
    if line_ids_set:
        async for d in db.rahaza_line_assignments.find({
            "line_id": {"$in": line_ids_set},
            "employee_id": {"$in": emp_ids_set},
            "shift_id": {"$in": shift_ids_set},
            "assign_date": assign_date,
        }, {"_id": 0}):
            existing_assign_map[(d["line_id"], d["employee_id"], d["shift_id"])] = d

    created = []
    skipped = []
    for a in assignments:
        line_id = a.get("line_id")
        emp_id = a.get("employee_id")
        shift_id = a.get("shift_id")
        if not line_id or not emp_id or not shift_id:
            skipped.append({**a, "reason": "line_id, employee_id, shift_id wajib diisi"})
            continue

        # Check for existing assignment (from prefetched map)
        existing = existing_assign_map.get((line_id, emp_id, shift_id))
        if existing and not overwrite:
            skipped.append({**a, "reason": "Assignment sudah ada"})
            continue
        if existing and overwrite:
            await db.rahaza_line_assignments.delete_one({"id": existing["id"]})

        doc = {
            "id": _uid(),
            "line_id": line_id,
            "employee_id": emp_id,
            "shift_id": shift_id,
            "assign_date": assign_date,
            "model_id": a.get("model_id"),
            "size_id": a.get("size_id"),
            "target_pcs": int(a.get("target_pcs") or 0),
            "notes": a.get("notes") or "Dari template kemarin",
            "created_by": user["id"],
            "created_at": _now(),
        }
        await db.rahaza_line_assignments.insert_one(doc)
        created.append(doc["id"])

    await log_activity(user["id"], user.get("name", ""), "bulk_assign", "supervisor", f"Bulk assign {len(created)} rows for {assign_date}")
    return {"created": len(created), "skipped": len(skipped), "skipped_detail": skipped[:10], "assign_date": assign_date}


# ────────────────────────────────────────────────────────────────────────────
# LINE BALANCING
# ────────────────────────────────────────────────────────────────────────────

@router.get("/line-balance")
async def get_line_balance(
    request: Request,
    assign_date: Optional[str] = None,
    shift_id: Optional[str] = None,
):
    """
    Line balance analysis: shows operator count, target pcs, SAM-based capacity,
    and imbalance warnings per line.
    """
    await _require_supervisor(request)
    db = get_db()
    target_date = assign_date or _today()
    q = {"assign_date": target_date}
    if shift_id:
        q["shift_id"] = shift_id

    rows = await db.rahaza_line_assignments.find(q, {"_id": 0}).to_list(500)

    # Gather IDs
    line_ids = list({r.get("line_id") for r in rows if r.get("line_id")})
    emp_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    model_ids = list({r.get("model_id") for r in rows if r.get("model_id")})
    shift_ids = list({r.get("shift_id") for r in rows if r.get("shift_id")})

    lines = await db.rahaza_lines.find({"id": {"$in": line_ids}}, {"_id": 0}).to_list(500) if line_ids else []
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0}).to_list(500) if emp_ids else []
    models = await db.rahaza_models.find({"id": {"$in": model_ids}}, {"_id": 0}).to_list(500) if model_ids else []
    shifts = await db.rahaza_shifts.find({"id": {"$in": shift_ids}}, {"_id": 0}).to_list(500) if shift_ids else []

    line_map = {l["id"]: l for l in lines}
    emp_map = {e["id"]: e for e in emps}
    model_map = {m["id"]: m for m in models}
    shift_map = {s["id"]: s for s in shifts}

    # Shift duration in minutes (default 8h = 480 min)
    def _shift_minutes(s_id):
        s = shift_map.get(s_id, {})
        return float(s.get("duration_hours") or 8) * 60

    # Group assignments by line
    by_line: dict = {}
    for r in rows:
        lid = r.get("line_id")
        if lid not in by_line:
            by_line[lid] = []
        by_line[lid].append(r)

    line_summaries = []
    total_target = 0
    total_capacity = 0

    for lid, assignments in by_line.items():
        line = line_map.get(lid, {})
        operator_count = len(assignments)
        total_target_pcs = sum(int(a.get("target_pcs") or 0) for a in assignments)
        total_target += total_target_pcs

        # SAM-based capacity estimation
        # If model has SAM data, use it; otherwise use heuristic (operator_count * shift_minutes / avg_SAM)
        model_ids_line = list({a.get("model_id") for a in assignments if a.get("model_id")})
        avg_sam = 0.0
        avg_target_pcs = 0
        if model_ids_line:
            sops = await db.rahaza_model_process_sop.find(
                {"model_id": {"$in": model_ids_line}, "active": True},
                {"_id": 0, "sam_minutes": 1, "target_pcs_per_operator": 1}
            ).to_list(500)
            sams = [float(s.get("sam_minutes") or 0) for s in sops if s.get("sam_minutes")]
            targets = [int(s.get("target_pcs_per_operator") or 0) for s in sops if s.get("target_pcs_per_operator")]
            avg_sam = sum(sams) / len(sams) if sams else 0.0
            avg_target_pcs = int(sum(targets) / len(targets)) if targets else 0

        # Compute capacity
        shift_minutes = _shift_minutes(assignments[0].get("shift_id")) if assignments else 480
        if avg_sam > 0:
            estimated_capacity = round((operator_count * shift_minutes) / avg_sam, 0)
        elif avg_target_pcs > 0:
            # Use target_pcs_per_operator as direct fallback
            estimated_capacity = operator_count * avg_target_pcs
        else:
            # Last resort fallback: 400 pcs/operator/day
            estimated_capacity = operator_count * 400
        total_capacity += estimated_capacity

        # Balance ratio
        balance_ratio = round((total_target_pcs / estimated_capacity) * 100, 1) if estimated_capacity > 0 else None

        # Imbalance detection
        imbalance_type = None
        if balance_ratio is not None:
            if balance_ratio > 110:
                imbalance_type = "overloaded"  # target > capacity
            elif balance_ratio < 70:
                imbalance_type = "underutilized"  # target much below capacity

        # Operator details
        operators = []
        for a in assignments:
            emp = emp_map.get(a.get("employee_id"), {})
            operators.append({
                "employee_id": a.get("employee_id"),
                "name": emp.get("name", "?"),
                "job_title": emp.get("job_title", ""),
                "shift_id": a.get("shift_id"),
                "shift_name": shift_map.get(a.get("shift_id"), {}).get("name", "?"),
                "model_id": a.get("model_id"),
                "model_name": model_map.get(a.get("model_id"), {}).get("name", ""),
                "target_pcs": int(a.get("target_pcs") or 0),
            })

        line_summaries.append({
            "line_id": lid,
            "line_name": line.get("name", "?"),
            "line_code": line.get("code", "?"),
            "operator_count": operator_count,
            "total_target_pcs": total_target_pcs,
            "estimated_capacity": int(estimated_capacity),
            "balance_ratio_pct": balance_ratio,
            "avg_sam_minutes": round(avg_sam, 2) if avg_sam else None,
            "imbalance_type": imbalance_type,
            "operators": operators,
        })

    # Sort by imbalance (overloaded first)
    _order = {"overloaded": 0, "underutilized": 2, None: 1}
    line_summaries.sort(key=lambda x: (_order.get(x.get("imbalance_type"), 1), -x.get("total_target_pcs", 0)))

    # Overall factory balance
    factory_balance = round((total_target / total_capacity) * 100, 1) if total_capacity > 0 else None
    overloaded_count = sum(1 for l in line_summaries if l.get("imbalance_type") == "overloaded")
    underutilized_count = sum(1 for l in line_summaries if l.get("imbalance_type") == "underutilized")

    return {
        "assign_date": target_date,
        "lines": line_summaries,
        "summary": {
            "total_lines": len(line_summaries),
            "total_operators": sum(l["operator_count"] for l in line_summaries),
            "total_target_pcs": total_target,
            "total_estimated_capacity": int(total_capacity),
            "factory_balance_pct": factory_balance,
            "overloaded_lines": overloaded_count,
            "underutilized_lines": underutilized_count,
            "balanced_lines": len(line_summaries) - overloaded_count - underutilized_count,
        },
    }
