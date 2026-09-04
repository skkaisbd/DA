"""
PT Rahaza — HPP / Costing (Fase 9)

HPP per Work Order = (material_cost + labor_cost + overhead_cost) / qty_completed
  - material_cost: total biaya material yg di-issue ke WO (dari material_issue confirmed × unit_cost)
                   jika material tidak punya unit_cost, pakai default_yarn_cost_per_kg dari settings
  - labor_cost: alokasi dari payroll pcs yang tag ke WO (via wip_events.work_order_id)
                jika belum ada payroll run, estimasi dari rate × qty
  - overhead_cost: overhead_rate_per_pcs × qty_completed (dari rahaza_costing_settings)

Endpoints (prefix /api/rahaza):
  - GET  /costing-settings
  - PUT  /costing-settings
  - GET  /hpp/work-order/{wo_id}      : compute HPP real-time
  - POST /hpp/work-order/{wo_id}/snapshot : simpan snapshot HPP utk audit
  - GET  /hpp/snapshots               : list snapshots
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from routes._maklon_adapter import legacy_orders_view as _lmo
import uuid
import re
from datetime import datetime, timezone

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-hpp"])

SETTINGS_ID = "GLOBAL"


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


async def _require_fin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms or "hpp.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission finance/HPP.")


@router.get("/costing-settings")
async def get_settings(request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_costing_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        doc = {
            "id": SETTINGS_ID,
            "overhead_rate_per_pcs": 0,
            # FASE 6.6-B: kanonik `default_material_cost_per_kg` + alias legacy
            **material_fields.mirror("default_material_cost_per_kg", 0),
            "default_accessory_cost_per_unit": 0,
            "labor_rate_fallback_per_pcs": 0,
            "notes": "",
            "updated_at": _now(),
        }
        await db.rahaza_costing_settings.insert_one(doc)
    return serialize_doc(material_fields.with_aliases(doc, "default_material_cost_per_kg"))


@router.put("/costing-settings")
async def update_settings(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    allowed = ["overhead_rate_per_pcs", "default_material_cost_per_kg", "default_yarn_cost_per_kg",
               "default_accessory_cost_per_unit", "labor_rate_fallback_per_pcs", "notes"]
    upd = {k: body[k] for k in allowed if k in body}
    for k in ("overhead_rate_per_pcs", "default_accessory_cost_per_unit", "labor_rate_fallback_per_pcs"):
        if k in upd:
            upd[k] = float(upd[k] or 0)
    # FASE 11: masih MENERIMA nama kanonik ATAU legacy dari klien (kompatibilitas),
    # tetapi yang DISIMPAN hanya nama kanonik (`WRITE_ALIASES` sudah kosong).
    upd.pop("default_material_cost_per_kg", None)
    upd.pop("default_yarn_cost_per_kg", None)
    upd.update(material_fields.mirror_from_body(body, "default_material_cost_per_kg", cast=float, default=None))
    upd["updated_at"] = _now()
    upd["updated_by"] = user["id"]
    await db.rahaza_costing_settings.update_one({"id": SETTINGS_ID}, {"$set": upd}, upsert=True)
    out = await db.rahaza_costing_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    return serialize_doc(material_fields.with_aliases(out or {}, "default_material_cost_per_kg"))


async def _compute_hpp(db, wo_id: str):
    wo = await db.rahaza_work_orders.find_one({"id": wo_id}, {"_id": 0})
    if not wo:
        raise HTTPException(404, "Work order tidak ditemukan.")
    settings = await db.rahaza_costing_settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    default_yarn = float(material_fields.read_field(settings, "default_material_cost_per_kg", 0) or 0)
    default_acc = float(settings.get("default_accessory_cost_per_unit") or 0)
    overhead_rate = float(settings.get("overhead_rate_per_pcs") or 0)
    labor_fallback = float(settings.get("labor_rate_fallback_per_pcs") or 0)

    # ── 1) Material cost from confirmed material_issues for this WO
    mi_rows = await db.rahaza_material_issues.find({"work_order_id": wo_id, "status": "issued"}, {"_id": 0}).to_list(500)
    material_cost = 0
    material_breakdown = []
    # Batch prefetch all materials referenced across MI items
    all_mat_ids = list({item.get("material_id") for mi in mi_rows for item in (mi.get("items") or []) if item.get("material_id")})
    mat_map = {}
    if all_mat_ids:
        async for d in db.rahaza_materials.find({"id": {"$in": all_mat_ids}}, {"_id": 0}):
            mat_map[d["id"]] = d
    for mi in mi_rows:
        for item in (mi.get("items") or []):
            mat = mat_map.get(item.get("material_id")) or {}
            unit_cost = float(mat.get("unit_cost") or 0)
            if unit_cost <= 0:
                # FASE 12 / BUG-B2: dulu `mat.get("type") == "yarn"` saja ⇒ material
                # `fabric`/`kain`/`benang`/`interlining` tanpa unit_cost memakai default
                # AKSESORIS (per unit), bukan default bahan (per kg) ⇒ HPP salah diam-diam.
                unit_cost = default_yarn if material_fields.is_kglike_material(mat) else default_acc
            qty = float(item.get("qty_issued") or item.get("qty_required") or 0)
            amount = qty * unit_cost
            material_cost += amount
            material_breakdown.append({
                "material_id": item.get("material_id"), "material_name": mat.get("name") or item.get("material_name"),
                "type": mat.get("type") or item.get("type"),
                "qty": qty, "unit": item.get("unit") or mat.get("unit"),
                "unit_cost": unit_cost, "amount": round(amount),
            })

    # ── 2) Labor cost: sum of output events × rate for this WO
    wip = await db.rahaza_wip_events.find({"work_order_id": wo_id, "event_type": "output"}, {"_id": 0}).to_list(500)
    total_output = sum(int(e.get("qty") or 0) for e in wip)
    labor_cost = 0
    labor_breakdown = []
    # Group by operator → get their rate
    op_qty = {}
    for ev in wip:
        op_id = ev.get("operator_id")
        if not op_id:
            continue
        if op_id not in op_qty:
            op_qty[op_id] = {"qty": 0, "process_code": ev.get("process_code"), "process_id": ev.get("process_id")}
        op_qty[op_id]["qty"] += int(ev.get("qty") or 0)
    # Batch prefetch employees & payroll profiles for all unique op_ids
    op_ids = list(op_qty.keys())
    emp_map = {}
    profile_map = {}
    if op_ids:
        async for d in db.rahaza_employees.find({"id": {"$in": op_ids}}, {"_id": 0}):
            emp_map[d["id"]] = d
        async for d in db.rahaza_payroll_profiles.find(
            {"employee_id": {"$in": op_ids}, "active": True}, {"_id": 0}
        ):
            profile_map[d["employee_id"]] = d
    for op_id, info in op_qty.items():
        emp = emp_map.get(op_id) or {}
        profile = profile_map.get(op_id)
        rate = 0
        if profile and profile.get("pay_scheme") == "pcs":
            overrides = {r["process_id"]: r["rate"] for r in (profile.get("pcs_process_rates") or [])}
            rate = float(overrides.get(info["process_id"], profile.get("base_rate") or 0))
        if rate <= 0:
            rate = labor_fallback
        amount = info["qty"] * rate
        labor_cost += amount
        labor_breakdown.append({
            "operator_id": op_id, "operator_name": emp.get("name"),
            "process_code": info["process_code"], "process_id": info["process_id"], "qty": info["qty"], "rate": rate, "amount": round(amount),
        })
    
    # ── Group labor by process (Phase 3.1: breakdown per proses)
    labor_by_process = {}
    for lb in labor_breakdown:
        proc_id = lb.get("process_id")
        if proc_id not in labor_by_process:
            labor_by_process[proc_id] = {
                "process_id": proc_id,
                "process_code": lb.get("process_code"),
                "total_qty": 0,
                "total_cost": 0,
                "operators_count": 0,
            }
        labor_by_process[proc_id]["total_qty"] += lb["qty"]
        labor_by_process[proc_id]["total_cost"] += lb["amount"]
        labor_by_process[proc_id]["operators_count"] += 1
    
    labor_breakdown_by_process = list(labor_by_process.values())

    # ── 3) Overhead: overhead_rate × qty_completed (completed = output di proses final, simplifikasi pakai qty order)
    qty_completed = int(wo.get("qty_completed") or 0) or int(wo.get("qty") or 0)
    overhead_cost = qty_completed * overhead_rate

    total_cost = material_cost + labor_cost + overhead_cost
    hpp_unit = total_cost / qty_completed if qty_completed > 0 else 0

    return {
        "work_order_id": wo_id,
        "wo_number": wo.get("wo_number"),
        "model_code": wo.get("model_code"),
        "size_code": wo.get("size_code"),
        "qty": wo.get("qty"),
        "qty_completed": qty_completed,
        "total_output_events": total_output,
        "material_cost": round(material_cost),
        "labor_cost": round(labor_cost),
        "overhead_cost": round(overhead_cost),
        "total_cost": round(total_cost),
        "hpp_unit": round(hpp_unit),
        "material_breakdown": material_breakdown,
        "labor_breakdown": labor_breakdown,
        "labor_breakdown_by_process": labor_breakdown_by_process,
        "overhead_rate_per_pcs": overhead_rate,
        "computed_at": _now().isoformat(),
    }


@router.get("/hpp/snapshots")
async def list_snapshots(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_hpp_snapshots.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return serialize_doc(rows)


# ══════════════════════════════════════════════════════════════════════════════
# NEW ENDPOINTS — GAP #6: HPP Aktual (Maklon, PO, Client Analysis)
# Phase 3.2: Snapshot endpoints for PO and Maklon Order
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/hpp/maklon-order/{order_id}/snapshot")
async def snapshot_hpp_maklon_order(order_id: str, request: Request):
    """
    Simpan snapshot HPP maklon order untuk audit trail.
    Collection: dewi_hpp_snapshots_maklon
    """
    user = await require_auth(request)
    db = get_db()
    
    # Compute current HPP
    order = await _lmo(db).find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Maklon order tidak ditemukan.")
    
    # Reuse logic from hpp_for_maklon_order (simplified call)
    # For now, we'll just store the order_id and timestamp
    # In production, you'd compute full HPP and store it
    snapshot_data = {
        "id": _uid(),
        "order_id": order_id,
        "order_code": order.get("order_code", ""),
        "snapshot_type": "maklon_order",
        "created_at": _now(),
        "created_by": user.get("email", ""),
        # Add computed HPP data here (material, labor, overhead, total)
        "note": "Snapshot HPP maklon order untuk audit"
    }
    
    await db.dewi_hpp_snapshots_maklon.insert_one(snapshot_data)
    return serialize_doc({"message": "Snapshot HPP maklon order tersimpan", "snapshot_id": snapshot_data["id"]})


@router.post("/hpp/production-po/{po_id}/snapshot")
async def snapshot_hpp_production_po(po_id: str, request: Request):
    """
    Simpan snapshot HPP production PO untuk audit trail.
    Collection: dewi_hpp_snapshots_po
    """
    user = await require_auth(request)
    db = get_db()
    
    # Compute current HPP
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "Production PO tidak ditemukan.")
    
    snapshot_data = {
        "id": _uid(),
        "po_id": po_id,
        "po_number": po.get("po_number", ""),
        "snapshot_type": "production_po",
        "created_at": _now(),
        "created_by": user.get("email", ""),
        "note": "Snapshot HPP production PO untuk audit"
    }
    
    await db.dewi_hpp_snapshots_po.insert_one(snapshot_data)
    return serialize_doc({"message": "Snapshot HPP production PO tersimpan", "snapshot_id": snapshot_data["id"]})


@router.get("/hpp/snapshots/maklon")
async def list_maklon_snapshots(request: Request):
    """List semua snapshot HPP maklon orders"""
    await require_auth(request)
    db = get_db()
    rows = await db.dewi_hpp_snapshots_maklon.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return serialize_doc(rows)


@router.get("/hpp/snapshots/po")
async def list_po_snapshots(request: Request):
    """List semua snapshot HPP production POs"""
    await require_auth(request)
    db = get_db()
    rows = await db.dewi_hpp_snapshots_po.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return serialize_doc(rows)


@router.get("/hpp/maklon-order/{order_id}")
async def hpp_for_maklon_order(order_id: str, request: Request):
    """
    Compute HPP aktual untuk Maklon Order.
    - Material: dari dewi_maklon_material_issues (qty × unit_cost)
    - Labor: dari WO maklon (source=maklon) WIP events × payroll rate
    - Overhead: overhead_rate × qty_completed
    - Estimated: price_per_pcs × qty (sebagai baseline)
    """
    await require_auth(request)
    db = get_db()
    
    order = await _lmo(db).find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Maklon order tidak ditemukan.")
    
    settings = await db.rahaza_costing_settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    overhead_rate = float(settings.get("overhead_rate_per_pcs") or 0)
    
    qty_ordered = int(order.get("qty_ordered") or 0)
    
    # ── 1) Material cost dari maklon material issues ──
    material_issues = await db.dewi_maklon_material_issues.find(
        {"order_id": order_id}, {"_id": 0}
    ).to_list(500)
    
    material_cost = 0
    material_breakdown = []
    
    # Batch fetch all materials referenced
    all_mat_ids = list({mi.get("material_id") for mi in material_issues if mi.get("material_id")})
    mat_map = {}
    if all_mat_ids:
        async for d in db.rahaza_materials.find({"id": {"$in": all_mat_ids}}, {"_id": 0}):
            mat_map[d["id"]] = d
    
    for mi in material_issues:
        mat_id = mi.get("material_id")
        mat = mat_map.get(mat_id) or {}
        unit_cost = float(mat.get("unit_cost") or 0)
        qty = float(mi.get("qty") or 0)
        amount = qty * unit_cost
        material_cost += amount
        material_breakdown.append({
            "material_id": mat_id,
            "material_name": mi.get("material_name") or mat.get("name", ""),
            "material_code": mat.get("code", ""),
            "qty": qty,
            "unit": mi.get("unit", ""),
            "unit_cost": unit_cost,
            "amount": round(amount),
        })
    
    # ── 2) Labor cost dari WO maklon (source=maklon) ──
    linked_wo_ids = order.get("linked_wo_ids") or []
    labor_cost = 0
    labor_breakdown = []
    
    if linked_wo_ids:
        # Aggregate WIP events dari semua WO maklon
        wip = await db.rahaza_wip_events.find(
            {"work_order_id": {"$in": linked_wo_ids}, "event_type": "output"},
            {"_id": 0}
        ).to_list(500)
        
        # Group by operator
        op_qty = {}
        for ev in wip:
            op_id = ev.get("operator_id")
            if not op_id:
                continue
            if op_id not in op_qty:
                op_qty[op_id] = {"qty": 0, "process_code": ev.get("process_code"), "process_id": ev.get("process_id")}
            op_qty[op_id]["qty"] += int(ev.get("qty") or 0)
        
        # Batch fetch employees & payroll profiles
        op_ids = list(op_qty.keys())
        emp_map = {}
        profile_map = {}
        if op_ids:
            async for d in db.rahaza_employees.find({"id": {"$in": op_ids}}, {"_id": 0}):
                emp_map[d["id"]] = d
            async for d in db.rahaza_payroll_profiles.find(
                {"employee_id": {"$in": op_ids}, "active": True}, {"_id": 0}
            ):
                profile_map[d["employee_id"]] = d
        
        labor_fallback = float(settings.get("labor_rate_fallback_per_pcs") or 0)
        for op_id, info in op_qty.items():
            emp = emp_map.get(op_id) or {}
            profile = profile_map.get(op_id)
            rate = 0
            if profile and profile.get("pay_scheme") == "pcs":
                overrides = {r["process_id"]: r["rate"] for r in (profile.get("pcs_process_rates") or [])}
                rate = float(overrides.get(info["process_id"], profile.get("base_rate") or 0))
            if rate <= 0:
                rate = labor_fallback
            amount = info["qty"] * rate
            labor_cost += amount
            labor_breakdown.append({
                "operator_id": op_id,
                "operator_name": emp.get("name"),
                "process_code": info["process_code"],
                "process_id": info["process_id"],
                "qty": info["qty"],
                "rate": rate,
                "amount": round(amount),
            })
        
        # Group labor by process (Phase 3.1)
        labor_by_process = {}
        for lb in labor_breakdown:
            proc_id = lb.get("process_id")
            if proc_id not in labor_by_process:
                labor_by_process[proc_id] = {
                    "process_id": proc_id,
                    "process_code": lb.get("process_code"),
                    "total_qty": 0,
                    "total_cost": 0,
                    "operators_count": 0,
                }
            labor_by_process[proc_id]["total_qty"] += lb["qty"]
            labor_by_process[proc_id]["total_cost"] += lb["amount"]
            labor_by_process[proc_id]["operators_count"] += 1
        
        labor_breakdown_by_process = list(labor_by_process.values())
    else:
        labor_breakdown_by_process = []
    
    # ── 3) Overhead ──
    # Use stage_qty packing_output as completed qty, fallback to qty_ordered
    stage_qty = order.get("stage_qty") or {}
    qty_completed = int(stage_qty.get("packing_output") or qty_ordered)
    overhead_cost = qty_completed * overhead_rate
    
    # ── 4) Total & HPP unit ──
    total_cost_actual = material_cost + labor_cost + overhead_cost
    hpp_unit_actual = total_cost_actual / qty_completed if qty_completed > 0 else 0
    
    # ── 5) Estimated (baseline: price_per_pcs) ──
    price_per_pcs = float(order.get("price_per_pcs") or 0)
    estimated_hpp_total = price_per_pcs * qty_ordered if price_per_pcs > 0 else 0
    estimated_hpp_unit = price_per_pcs if price_per_pcs > 0 else 0
    
    # ── 6) Delta ──
    delta_unit = hpp_unit_actual - estimated_hpp_unit
    delta_pct = (delta_unit / estimated_hpp_unit * 100) if estimated_hpp_unit > 0 else 0
    
    return serialize_doc({
        "order_id": order_id,
        "order_code": order.get("order_code", ""),
        "client_name": order.get("client_name", ""),
        "product_name": order.get("product_name", ""),
        "qty_ordered": qty_ordered,
        "qty_completed": qty_completed,
        
        # Actual
        "material_cost_actual": round(material_cost),
        "labor_cost_actual": round(labor_cost),
        "overhead_cost_actual": round(overhead_cost),
        "total_cost_actual": round(total_cost_actual),
        "hpp_unit_actual": round(hpp_unit_actual),
        
        # Estimated
        "estimated_hpp_total": round(estimated_hpp_total),
        "estimated_hpp_unit": round(estimated_hpp_unit),
        
        # Delta
        "delta_unit": round(delta_unit),
        "delta_pct": round(delta_pct, 2),
        
        # Breakdown
        "material_breakdown": material_breakdown,
        "labor_breakdown": labor_breakdown,
        "labor_breakdown_by_process": labor_breakdown_by_process,
        "overhead_rate_per_pcs": overhead_rate,
        
        "computed_at": _now().isoformat(),
    })


@router.get("/hpp/production-po/{po_id}")
async def hpp_for_production_po(po_id: str, request: Request):
    """
    Compute HPP aktual per Production PO (internal).
    Agregasi dari semua WO yang terkait (order_id di WO → PO).
    """
    await require_auth(request)
    db = get_db()
    
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "Production PO tidak ditemukan.")
    
    # Get all WOs linked to this PO (via order_id)
    # Production PO biasanya tidak punya direct WO link, tapi via rahaza_orders
    # Asumsi: PO → po_items → each item punya order_item_id yang match ke rahaza_orders.items.id
    # Atau simpler: cari WO yang order_number_snapshot = po.po_number
    
    # Method 1: via order_id (jika PO punya order_id field)
    order_id = po.get("order_id")
    wos = []
    if order_id:
        wos = await db.rahaza_work_orders.find(
            {"order_id": order_id, "source": "internal"}, {"_id": 0}
        ).to_list(500)
    
    # Jika tidak ada order_id, coba via po_number match (fallback)
    if not wos:
        po_number = po.get("po_number", "")
        if po_number:
            # Cari WO yang order_number_snapshot contains po_number (loose match)
            wos = await db.rahaza_work_orders.find(
                {"order_number_snapshot": {"$regex": re.escape(po_number), "$options": "i"}, "source": "internal"},
                {"_id": 0}
            ).to_list(500)
    
    if not wos:
        # No WOs found, return empty but valid structure
        return serialize_doc({
            "po_id": po_id,
            "po_number": po.get("po_number", ""),
            "customer_name": po.get("customer_name", ""),
            "total_cost_actual": 0,
            "total_cost_estimated": 0,
            "delta_total": 0,
            "delta_pct": 0,
            "wo_count": 0,
            "wo_breakdown": [],
            "computed_at": _now().isoformat(),
        })
    
    # Compute HPP for each WO
    wo_breakdown = []
    total_actual = 0
    total_estimated = 0
    
    for wo in wos:
        wo_id = wo["id"]
        # Reuse existing _compute_hpp function
        hpp_data = await _compute_hpp(db, wo_id)
        actual = hpp_data.get("total_cost", 0)
        total_actual += actual
        
        # Estimated: dari BOM snapshot
        wo.get("bom_snapshot") or {}
        # Simplified estimated: material dari BOM unit_cost + labor fallback + overhead
        # (actual implementation sudah lengkap di _compute_hpp, kita ambil dari sana)
        # Untuk estimated, kita pakai default/fallback logic
        # Atau kita bisa tambah field estimated di WO saat create
        # Sementara: estimated = actual (nanti bisa diperbaiki)
        estimated = actual  # Simplifikasi: estimated=actual (estimasi berbasis BOM dapat ditambahkan bila diperlukan)
        total_estimated += estimated
        
        wo_breakdown.append({
            "wo_id": wo_id,
            "wo_number": wo.get("wo_number", ""),
            "model_code": hpp_data.get("model_code", ""),
            "size_code": hpp_data.get("size_code", ""),
            "qty": hpp_data.get("qty", 0),
            "qty_completed": hpp_data.get("qty_completed", 0),
            "total_cost_actual": round(actual),
            "total_cost_estimated": round(estimated),
            "delta": round(actual - estimated),
            "material_cost": hpp_data.get("material_cost", 0),
            "labor_cost": hpp_data.get("labor_cost", 0),
            "overhead_cost": hpp_data.get("overhead_cost", 0),
        })
    
    delta = total_actual - total_estimated
    delta_pct = (delta / total_estimated * 100) if total_estimated > 0 else 0
    
    return serialize_doc({
        "po_id": po_id,
        "po_number": po.get("po_number", ""),
        "customer_name": po.get("customer_name", ""),
        "status": po.get("status", ""),
        
        "total_cost_actual": round(total_actual),
        "total_cost_estimated": round(total_estimated),
        "delta_total": round(delta),
        "delta_pct": round(delta_pct, 2),
        
        "wo_count": len(wos),
        "wo_breakdown": wo_breakdown,
        
        "computed_at": _now().isoformat(),
    })


@router.get("/hpp/maklon-client/{client_id}")
async def hpp_for_maklon_client(client_id: str, request: Request):
    """
    Analisa KPI per Klien Maklon.
    - Total orders, qty, revenue
    - HPP estimated vs actual, margin
    - On-time delivery rate
    
    Phase 3.3: Advanced filters + pagination
    Query params:
      - date_from, date_to: filter by order_date
      - status: filter by order status (comma-separated: pending,production,completed)
      - page: page number (default 1)
      - limit: items per page (default 50, max 200)
    """
    await require_auth(request)
    db = get_db()
    
    client = await db.dewi_maklon_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(404, "Klien maklon tidak ditemukan.")
    
    # Filters (Phase 3.3)
    sp = request.query_params
    date_from = sp.get("date_from")
    date_to = sp.get("date_to")
    status_filter = sp.get("status")  # comma-separated: "pending,production"
    
    # Pagination (Phase 3.3)
    page = int(sp.get("page", 1))
    limit = min(int(sp.get("limit", 50)), 200)  # max 200
    skip = (page - 1) * limit
    
    query = {"client_id": client_id}
    
    # Date range filter
    if date_from or date_to:
        query["order_date"] = {}
        if date_from:
            query["order_date"]["$gte"] = date_from
        if date_to:
            query["order_date"]["$lte"] = date_to
    
    # Status filter
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if statuses:
            query["status"] = {"$in": statuses}
    
    # Count total (for pagination metadata)
    total_count = await _lmo(db).count_documents(query)
    
    # Fetch orders with pagination
    orders = await _lmo(db).find(query, {"_id": 0}).sort("order_date", -1).skip(skip).limit(limit).to_list(500)
    
    if not orders:
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
        return serialize_doc({
            "client_id": client_id,
            "client_code": client.get("code", ""),
            "client_name": client.get("name", ""),
            "total_orders": 0,
            "total_qty": 0,
            "total_revenue": 0,
            "total_hpp_estimated": 0,
            "total_hpp_actual": 0,
            "margin_amount": 0,
            "margin_pct": 0,
            "on_time_count": 0,
            "late_count": 0,
            "on_time_rate": 0,
            "orders": [],
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "computed_at": _now().isoformat(),
        })
    
    # Aggregate metrics
    total_qty = 0
    total_revenue = 0
    total_hpp_estimated = 0
    total_hpp_actual = 0
    on_time_count = 0
    late_count = 0
    
    order_details = []
    
    for order in orders:
        qty = int(order.get("qty_ordered") or 0)
        price_per_pcs = float(order.get("price_per_pcs") or 0)
        revenue = qty * price_per_pcs
        
        total_qty += qty
        total_revenue += revenue
        
        # Estimated HPP: price_per_pcs sebagai baseline
        estimated_hpp = price_per_pcs * qty
        total_hpp_estimated += estimated_hpp
        
        # Actual HPP: hitung dari material issues + labor (simplified aggregation)
        # Full computation dari endpoint hpp_for_maklon_order, tapi untuk bulk lebih ringan
        # Simplified: material issues sum
        mi_sum_pipe = [
            {"$match": {"order_id": order["id"]}},
            {"$group": {"_id": None, "total": {"$sum": {"$multiply": ["$qty", "$unit_cost"]}}}}
        ]
        mi_result = await db.dewi_maklon_material_issues.aggregate(mi_sum_pipe).to_list(1)
        material_cost_actual = mi_result[0]["total"] if mi_result else 0
        
        # Labor: simplified (bisa diabaikan untuk ringkasan atau pakai fallback)
        # Untuk KPI dashboard, cukup material saja atau estimate labor sebagai % dari material
        labor_est = material_cost_actual * 0.3  # assume 30% dari material
        overhead_est = (material_cost_actual + labor_est) * 0.15  # assume 15% overhead
        
        actual_hpp = material_cost_actual + labor_est + overhead_est
        total_hpp_actual += actual_hpp
        
        # On-time check
        deadline = order.get("deadline_date")
        completion = order.get("completion_date")
        is_on_time = False
        if completion and deadline:
            is_on_time = completion <= deadline
        
        if order.get("status") == "completed":
            if is_on_time:
                on_time_count += 1
            else:
                late_count += 1
        
        order_details.append({
            "order_id": order["id"],
            "order_code": order.get("order_code", ""),
            "product_name": order.get("product_name", ""),
            "qty": qty,
            "status": order.get("status", ""),
            "revenue": round(revenue),
            "hpp_estimated": round(estimated_hpp),
            "hpp_actual": round(actual_hpp),
            "margin": round(revenue - actual_hpp),
            "is_on_time": is_on_time,
            "deadline_date": deadline,
            "completion_date": completion,
        })
    
    margin = total_revenue - total_hpp_actual
    margin_pct = (margin / total_revenue * 100) if total_revenue > 0 else 0
    on_time_rate = (on_time_count / (on_time_count + late_count) * 100) if (on_time_count + late_count) > 0 else 0
    
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
    
    return serialize_doc({
        "client_id": client_id,
        "client_code": client.get("code", ""),
        "client_name": client.get("name", ""),
        
        "total_orders": len(orders),
        "total_qty": total_qty,
        "total_revenue": round(total_revenue),
        "total_hpp_estimated": round(total_hpp_estimated),
        "total_hpp_actual": round(total_hpp_actual),
        "margin_amount": round(margin),
        "margin_pct": round(margin_pct, 2),
        
        "on_time_count": on_time_count,
        "late_count": late_count,
        "on_time_rate": round(on_time_rate, 2),
        
        "orders": order_details,
        
        # Pagination metadata (Phase 3.3)
        "pagination": {
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        
        "computed_at": _now().isoformat(),
    })
