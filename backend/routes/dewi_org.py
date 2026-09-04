"""Phase 6.5 — Organization Chart & Structure
Modul: Unit organisasi, posisi, bagan organisasi, headcount planning
"""
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api/dewi/org", tags=["OrgChart"])

def now_utc():
    return datetime.now(timezone.utc)

def sid():
    return str(uuid.uuid4())

def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

# ──────────────────────────────────────────────────────────────────────────────
# ORG UNITS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/units")
async def list_units(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    docs = await db.dewi_org_units.find({}).sort("level", 1).to_list(200)
    return {"ok": True, "units": [serialize(d) for d in docs]}

@router.post("/units")
async def create_unit(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    # compute level based on parent
    parent_id = body.get("parent_id", None)
    level = 0
    if parent_id:
        parent = await db.dewi_org_units.find_one({"unit_id": parent_id})
        level = (parent.get("level", 0) + 1) if parent else 1
    
    doc = {
        "unit_id": sid(),
        "name": body.get("name", "Unit Baru"),
        "code": body.get("code", ""),
        "type": body.get("type", "department"),  # company/division/department/team/section
        "parent_id": parent_id,
        "level": level,
        "head_employee_id": body.get("head_employee_id", None),
        "head_employee_name": body.get("head_employee_name", ""),
        "headcount_actual": body.get("headcount_actual", 0),
        "headcount_target": body.get("headcount_target", 0),
        "color": body.get("color", ""),
        "description": body.get("description", ""),
        "is_active": True,
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_org_units.insert_one(doc)
    return {"ok": True, "unit": serialize(doc)}

@router.get("/units/{unit_id}")
async def get_unit(
    unit_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_org_units.find_one({"unit_id": unit_id})
    if not doc:
        raise HTTPException(404, "Unit tidak ditemukan")
    return {"ok": True, "unit": serialize(doc)}

@router.put("/units/{unit_id}")
async def update_unit(
    unit_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    allowed = ["name","code","type","parent_id","head_employee_id","head_employee_name",
               "headcount_actual","headcount_target","color","description","is_active"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = now_utc()
    res = await db.dewi_org_units.update_one({"unit_id": unit_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Unit tidak ditemukan")
    doc = await db.dewi_org_units.find_one({"unit_id": unit_id})
    return {"ok": True, "unit": serialize(doc)}

@router.delete("/units/{unit_id}")
async def delete_unit(
    unit_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    # check no children
    children = await db.dewi_org_units.count_documents({"parent_id": unit_id})
    if children > 0:
        raise HTTPException(400, "Hapus unit anak terlebih dahulu sebelum menghapus unit ini")
    res = await db.dewi_org_units.delete_one({"unit_id": unit_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Unit tidak ditemukan")
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# POSITIONS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/positions")
async def list_positions(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    unit_id: Optional[str] = None,
):
    filt = {}
    if unit_id:
        filt["unit_id"] = unit_id
    docs = await db.dewi_org_positions.find(filt).sort("grade", -1).to_list(200)
    return {"ok": True, "positions": [serialize(d) for d in docs]}

@router.post("/positions")
async def create_position(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = {
        "position_id": sid(),
        "title": body.get("title", "Posisi Baru"),
        "unit_id": body.get("unit_id", ""),
        "unit_name": body.get("unit_name", ""),
        "grade": body.get("grade", 1),  # 1-10
        "reports_to_position_id": body.get("reports_to_position_id", None),
        "reports_to_title": body.get("reports_to_title", ""),
        "headcount_target": body.get("headcount_target", 1),
        "headcount_actual": body.get("headcount_actual", 0),
        "salary_grade": body.get("salary_grade", ""),
        "is_active": True,
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_org_positions.insert_one(doc)
    return {"ok": True, "position": serialize(doc)}

@router.put("/positions/{position_id}")
async def update_position(
    position_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    allowed = ["title","unit_id","unit_name","grade","reports_to_position_id",
               "reports_to_title","headcount_target","headcount_actual","salary_grade","is_active"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = now_utc()
    res = await db.dewi_org_positions.update_one({"position_id": position_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Posisi tidak ditemukan")
    doc = await db.dewi_org_positions.find_one({"position_id": position_id})
    return {"ok": True, "position": serialize(doc)}

@router.delete("/positions/{position_id}")
async def delete_position(
    position_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    res = await db.dewi_org_positions.delete_one({"position_id": position_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Posisi tidak ditemukan")
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# ORG CHART TREE
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/chart")
async def get_org_chart(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Return org chart as tree structure"""
    all_units = await db.dewi_org_units.find({"is_active": True}).sort("level", 1).to_list(200)
    
    if not all_units:
        return {"ok": True, "tree": None, "flat": []}
    
    # Build tree
    unit_map = {u["unit_id"]: {**serialize(u), "children": []} for u in all_units}
    
    # Attach employee counts from HR
    emps = await db.rahaza_employees.find({"status": "aktif"}).to_list(500)
    dept_counts = {}
    for emp in emps:
        dept = emp.get("department", "")
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
    
    roots = []
    for u in all_units:
        uid = u["unit_id"]
        parent_id = u.get("parent_id")
        # update headcount from actual employees
        unit_name = u.get("name", "")
        actual = dept_counts.get(unit_name, unit_map[uid].get("headcount_actual", 0))
        unit_map[uid]["headcount_actual"] = actual
        
        if parent_id and parent_id in unit_map:
            unit_map[parent_id]["children"].append(unit_map[uid])
        else:
            roots.append(unit_map[uid])
    
    # Compute total headcount bottom-up
    def compute_total(node):
        if not node["children"]:
            return node["headcount_actual"]
        children_total = sum(compute_total(c) for c in node["children"])
        node["total_headcount"] = children_total + node["headcount_actual"]
        return node["total_headcount"]
    
    for root in roots:
        compute_total(root)
    
    return {
        "ok": True,
        "tree": roots[0] if len(roots) == 1 else roots,
        "flat": [serialize(u) for u in all_units],
        "total_employees": sum(dept_counts.values()),
    }

# ──────────────────────────────────────────────────────────────────────────────
# HEADCOUNT PLANNING
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/headcount")
async def headcount_analysis(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Headcount: target vs actual per unit"""
    units = await db.dewi_org_units.find({"is_active": True}).to_list(200)
    
    # get actual employee counts per department
    emps = await db.rahaza_employees.find({"status": "aktif"}).to_list(500)
    dept_counts = {}
    for emp in emps:
        dept = emp.get("department", "")
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
    
    result = []
    for u in units:
        actual = dept_counts.get(u["name"], u.get("headcount_actual", 0))
        target = u.get("headcount_target", 0)
        gap = target - actual
        result.append({
            "unit_id": u["unit_id"],
            "name": u["name"],
            "type": u.get("type", ""),
            "actual": actual,
            "target": target,
            "gap": gap,
            "gap_pct": round((gap / target * 100), 1) if target else 0,
            "status": "over" if gap < 0 else ("ok" if gap == 0 else "under"),
        })
    
    total_actual = sum(r["actual"] for r in result)
    total_target = sum(r["target"] for r in result)
    
    return {
        "ok": True,
        "summary": {
            "total_actual": total_actual,
            "total_target": total_target,
            "gap": total_target - total_actual,
        },
        "units": result,
    }

# ──────────────────────────────────────────────────────────────────────────────
# SEED
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed_org(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_org_units.delete_many({})
    await db.dewi_org_positions.delete_many({})
    
    units = [
        # Level 0 - Company
        {"unit_id": "u-00", "name": "CV. Dewi Aditya Official", "code": "CVD", "type": "company",
         "parent_id": None, "level": 0, "head_employee_name": "Direktur Utama",
         "headcount_actual": 0, "headcount_target": 60, "color": "#6366f1",
         "description": "Induk perusahaan garmen", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        
        # Level 1 - Divisions
        {"unit_id": "u-01", "name": "Operasional & Produksi", "code": "OPS", "type": "division",
         "parent_id": "u-00", "level": 1, "head_employee_name": "GM Operasional",
         "headcount_actual": 0, "headcount_target": 40, "color": "#10b981",
         "description": "Divisi produksi garmen", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-02", "name": "Keuangan & Administrasi", "code": "FIN", "type": "division",
         "parent_id": "u-00", "level": 1, "head_employee_name": "Finance Director",
         "headcount_actual": 0, "headcount_target": 8, "color": "#f59e0b",
         "description": "Divisi keuangan dan administrasi", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-03", "name": "SDM & Pengembangan", "code": "HR", "type": "division",
         "parent_id": "u-00", "level": 1, "head_employee_name": "HR Manager",
         "headcount_actual": 0, "headcount_target": 5, "color": "#8b5cf6",
         "description": "Divisi SDM", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-04", "name": "Penjualan & Pemasaran", "code": "SALES", "type": "division",
         "parent_id": "u-00", "level": 1, "head_employee_name": "Sales Manager",
         "headcount_actual": 0, "headcount_target": 7, "color": "#ef4444",
         "description": "Divisi penjualan", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        
        # Level 2 - Departments under Ops
        {"unit_id": "u-11", "name": "Produksi", "code": "PRD", "type": "department",
         "parent_id": "u-01", "level": 2, "head_employee_name": "Kepala Produksi",
         "headcount_actual": 0, "headcount_target": 25, "color": "#14b8a6",
         "description": "Departemen produksi (cutting, sewing, finishing)", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-12", "name": "Quality Control", "code": "QC", "type": "department",
         "parent_id": "u-01", "level": 2, "head_employee_name": "QC Manager",
         "headcount_actual": 0, "headcount_target": 6, "color": "#06b6d4",
         "description": "Departemen quality control", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-13", "name": "Gudang", "code": "WHZ", "type": "department",
         "parent_id": "u-01", "level": 2, "head_employee_name": "Kepala Gudang",
         "headcount_actual": 0, "headcount_target": 6, "color": "#84cc16",
         "description": "Departemen pergudangan", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        
        # Level 3 - Teams under Produksi
        {"unit_id": "u-21", "name": "Lini Cutting", "code": "CUT", "type": "team",
         "parent_id": "u-11", "level": 3, "head_employee_name": "Supervisor Cutting",
         "headcount_actual": 0, "headcount_target": 8, "color": "#f97316",
         "description": "Tim operator cutting", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-22", "name": "Lini Jahit CMT", "code": "CMT", "type": "team",
         "parent_id": "u-11", "level": 3, "head_employee_name": "Supervisor CMT",
         "headcount_actual": 0, "headcount_target": 12, "color": "#ec4899",
         "description": "Tim operator jahit CMT", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"unit_id": "u-23", "name": "Lini Finishing", "code": "FIN", "type": "team",
         "parent_id": "u-11", "level": 3, "head_employee_name": "Supervisor Finishing",
         "headcount_actual": 0, "headcount_target": 5, "color": "#a855f7",
         "description": "Tim finishing dan packing", "is_active": True,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
    ]
    
    for u in units:
        await db.dewi_org_units.insert_one(u)
    
    # Positions
    positions = [
        {"position_id": "pos-001", "title": "Direktur Utama", "unit_id": "u-00", "unit_name": "CV. Dewi Aditya Official",
         "grade": 10, "reports_to_position_id": None, "headcount_target": 1, "headcount_actual": 1,
         "salary_grade": "A", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-002", "title": "GM Operasional", "unit_id": "u-01", "unit_name": "Operasional & Produksi",
         "grade": 8, "reports_to_position_id": "pos-001", "headcount_target": 1, "headcount_actual": 1,
         "salary_grade": "B", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-003", "title": "HR Manager", "unit_id": "u-03", "unit_name": "SDM & Pengembangan",
         "grade": 7, "reports_to_position_id": "pos-001", "headcount_target": 1, "headcount_actual": 1,
         "salary_grade": "B", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-004", "title": "Kepala Produksi", "unit_id": "u-11", "unit_name": "Produksi",
         "grade": 7, "reports_to_position_id": "pos-002", "headcount_target": 1, "headcount_actual": 1,
         "salary_grade": "C", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-005", "title": "Supervisor CMT", "unit_id": "u-22", "unit_name": "Lini Jahit CMT",
         "grade": 5, "reports_to_position_id": "pos-004", "headcount_target": 2, "headcount_actual": 2,
         "salary_grade": "D", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-006", "title": "Operator Jahit", "unit_id": "u-22", "unit_name": "Lini Jahit CMT",
         "grade": 2, "reports_to_position_id": "pos-005", "headcount_target": 12, "headcount_actual": 10,
         "salary_grade": "F", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"position_id": "pos-007", "title": "QC Inspector", "unit_id": "u-12", "unit_name": "Quality Control",
         "grade": 4, "reports_to_position_id": "pos-002", "headcount_target": 4, "headcount_actual": 3,
         "salary_grade": "D", "is_active": True, "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
    ]
    for p in positions:
        await db.dewi_org_positions.insert_one(p)
    
    return {"ok": True, "message": "Org chart seed selesai", "units": len(units), "positions": len(positions)}
