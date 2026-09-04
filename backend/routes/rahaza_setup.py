"""
PT Rahaza ERP — Setup Wizard Backend (Phase 16.1)

Endpoint support untuk First-Run Setup Wizard:
  GET  /api/rahaza/setup/status        → cek kelengkapan master data & transaksi
  POST /api/rahaza/setup/seed-sample   → one-click: seed 2 line, 3 operator, 1 model+sizes+BOM, 1 demo order
  POST /api/rahaza/setup/skip          → user mark wizard sebagai 'skipped' (per user)
  POST /api/rahaza/setup/dismiss       → mark user sebagai 'completed' (jangan tampil lagi)

Storage: koleksi `rahaza_setup_state` = { user_id, status, completed_steps[], updated_at }
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, date
import uuid
import logging
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*
from core import product_master as pm  # T1: SATU definisi "model masih hidup"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/setup", tags=["Setup Wizard"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _count(db, col: str, filt: dict = None) -> int:
    return await db[col].count_documents(filt or {})


async def _uid_of_user(user: dict) -> str:
    return user.get("id") or user.get("user_id") or user.get("sub") or user.get("email") or "anon"


# ─── STATUS ──────────────────────────────────────────────────────────────────
@router.get("/status")
async def setup_status(request: Request):
    """
    Return kelengkapan setup sekaligus state user untuk wizard.

    Response:
      {
        "ready": bool,                # true = wizard tidak perlu ditampilkan
        "needs_wizard": bool,         # true = tampilkan wizard (first time / incomplete)
        "skipped_by_user": bool,
        "dismissed_by_user": bool,
        "steps": [
          {key, label, done, count, required}
        ],
        "summary": {"master_ok": bool, "transaction_ok": bool}
      }
    """
    user = await require_auth(request)
    db = get_db()
    uid = await _uid_of_user(user)

    # Base counts
    loc = await _count(db, "rahaza_locations", {"active": True})
    proc = await _count(db, "rahaza_processes", {})
    shifts = await _count(db, "rahaza_shifts", {"active": True})
    lines = await _count(db, "rahaza_lines", {"active": True})
    emps = await _count(db, "rahaza_employees", {"active": True})
    models = await _count(db, "rahaza_models", pm.LIVE_MODEL_FILTER)
    sizes = await _count(db, "rahaza_sizes", {"active": True})
    boms = await _count(db, "rahaza_boms", {"active": True})
    orders = await _count(db, "rahaza_orders", {})

    steps = [
        {"key": "locations", "label": "Gedung & Lokasi", "done": loc > 0, "count": loc, "required": True},
        {"key": "processes", "label": "Proses Produksi", "done": proc > 0, "count": proc, "required": True},
        {"key": "shifts", "label": "Shift Kerja", "done": shifts > 0, "count": shifts, "required": True},
        {"key": "lines", "label": "Line Produksi", "done": lines > 0, "count": lines, "required": True},
        {"key": "employees", "label": "Karyawan / Operator", "done": emps > 0, "count": emps, "required": True},
        {"key": "models_sizes", "label": "Model & Size", "done": (models > 0 and sizes > 0),
         "count": models + sizes, "required": True},
        {"key": "boms", "label": "BOM (Bill of Material)", "done": boms > 0, "count": boms, "required": True},
        {"key": "demo_order", "label": "Order / Transaksi Pertama", "done": orders > 0, "count": orders, "required": False},
    ]

    all_required_done = all(s["done"] for s in steps if s["required"])
    master_ok = loc > 0 and proc > 0 and shifts > 0 and lines > 0 and emps > 0 and models > 0 and sizes > 0 and boms > 0
    transaction_ok = orders > 0

    state_doc = await db.rahaza_setup_state.find_one({"user_id": uid}, {"_id": 0})
    skipped = bool(state_doc and state_doc.get("status") == "skipped")
    dismissed = bool(state_doc and state_doc.get("status") == "dismissed")

    needs_wizard = (not all_required_done) and (not dismissed) and (not skipped)

    return {
        "ready": all_required_done,
        "needs_wizard": needs_wizard,
        "skipped_by_user": skipped,
        "dismissed_by_user": dismissed,
        "steps": steps,
        "summary": {"master_ok": master_ok, "transaction_ok": transaction_ok},
    }


# ─── SEED SAMPLE (one-click starter pack) ─────────────────────────────────────
@router.post("/seed-sample")
async def seed_sample_data(request: Request):
    """
    One-click seed minimal untuk pabrik baru. Idempotent — skip record yang
    sudah ada (berdasarkan code unik).

    Seeded:
      - 1 Line per proses utama non-rework (e.g. Rajut, Linking, Sewing, QC, Steam, Packing)
      - 3 Karyawan/Operator (OP-001, OP-002, OP-003)
      - 1 Model (MDL-SWEATER-DEMO)
      - 4 Size (S, M, L, XL) — skip jika sudah ada
      - 1 BOM untuk MDL x size M (akrilik 0.35kg + kancing 6 pcs)
      - 1 Demo Order internal (qty 20 pcs per size)
    """
    user = await require_auth(request)
    db = get_db()

    # Require admin/superadmin
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(403, "Hanya admin yang boleh seed sample data")

    out = {
        "created": {
            "lines": 0, "employees": 0, "models": 0, "sizes": 0,
            "boms": 0, "orders": 0,
        },
        "messages": [],
    }

    # ── Line ── (pakai location & process yang ada). Phase 17C: seed 1 line per
    # proses utama (non-rework) supaya operator bisa walk-through bundle sampai PACKING
    # tanpa perlu buat line manual dulu.
    first_location = await db.rahaza_locations.find_one({"active": True}, sort=[("code", 1)])
    main_procs = await db.rahaza_processes.find(
        {"active": {"$ne": False}, "is_rework": {"$ne": True}},
        {"_id": 0},
    ).sort("order_seq", 1).to_list(500)

    # capacity defaults per code (tweak as needed)
    _capacity_default = {
        "RAJUT": 15, "LINKING": 22, "SEWING": 20,
        "QC": 30, "STEAM": 40, "PACKING": 50,
    }

    lines_to_seed = []
    for proc in main_procs:
        pcode = (proc.get("code") or "").upper()
        line_code = f"LN-{pcode}-01"
        lines_to_seed.append({
            "code": line_code,
            "name": f"Line {proc.get('name') or pcode} 1 (Demo)",
            "location_id": first_location["id"] if first_location else None,
            "process_id": proc["id"],
            "capacity_per_hour": _capacity_default.get(pcode, 20),
        })
    line_codes = [ln["code"] for ln in lines_to_seed]
    existing_line_codes = set()
    if line_codes:
        async for d in db.rahaza_lines.find(
            {"code": {"$in": line_codes}, "active": True}, {"_id": 0, "code": 1}
        ):
            existing_line_codes.add(d["code"])
    for ln in lines_to_seed:
        if ln["code"] in existing_line_codes:
            continue
        await db.rahaza_lines.insert_one({
            "id": _uid(), **ln, "active": True,
            "created_at": _now(), "updated_at": _now(),
        })
        out["created"]["lines"] += 1

    # ── Karyawan / Operator ──
    default_emps = [
        {"employee_code": "OP-001", "name": "Budi Operator", "role_hint": "operator"},
        {"employee_code": "OP-002", "name": "Siti Operator", "role_hint": "operator"},
        {"employee_code": "OP-003", "name": "Andi Leader", "role_hint": "leader"},
    ]
    emp_codes = [e["employee_code"] for e in default_emps]
    existing_emp_codes = set()
    if emp_codes:
        async for d in db.rahaza_employees.find(
            {"employee_code": {"$in": emp_codes}, "active": True}, {"_id": 0, "employee_code": 1}
        ):
            existing_emp_codes.add(d["employee_code"])
    for e in default_emps:
        if e["employee_code"] in existing_emp_codes:
            continue
        await db.rahaza_employees.insert_one({
            "id": _uid(),
            "employee_code": e["employee_code"],
            "name": e["name"],
            "role_hint": e["role_hint"],
            "phone": "",
            "join_date": date.today().isoformat(),
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        })
        out["created"]["employees"] += 1

    # ── Size ──
    default_sizes = [
        {"code": "S", "name": "Small", "order_seq": 1},
        {"code": "M", "name": "Medium", "order_seq": 2},
        {"code": "L", "name": "Large", "order_seq": 3},
        {"code": "XL", "name": "Extra Large", "order_seq": 4},
    ]
    size_id_by_code = {}
    size_codes = [s["code"] for s in default_sizes]
    existing_sizes = {}
    if size_codes:
        async for d in db.rahaza_sizes.find(
            {"code": {"$in": size_codes}, "active": True}, {"_id": 0}
        ):
            existing_sizes[d["code"]] = d
    for s in default_sizes:
        existing = existing_sizes.get(s["code"])
        if existing:
            size_id_by_code[s["code"]] = existing["id"]
            continue
        sid = _uid()
        await db.rahaza_sizes.insert_one({
            "id": sid, **s, "active": True,
            "created_at": _now(), "updated_at": _now(),
        })
        size_id_by_code[s["code"]] = sid
        out["created"]["sizes"] += 1

    # ── Model ──
    model_code = "MDL-SWEATER-DEMO"
    model = await db.rahaza_models.find_one(pm.live_model_filter({"code": model_code}))
    if not model:
        mid = _uid()
        await db.rahaza_models.insert_one({
            "id": mid, "code": model_code, "name": "Sweater Demo Klasik",
            "description": "Sample model untuk onboarding. Sweater rajut benang akrilik dengan kancing.",
            "active": True, "created_at": _now(), "updated_at": _now(),
        })
        model_id = mid
        out["created"]["models"] += 1
    else:
        model_id = model["id"]

    # ── BOM untuk Model × Size M ──
    size_m_id = size_id_by_code.get("M")
    if size_m_id:
        # ACC-2 — pastikan master material demo ADA lebih dulu supaya baris BOM
        # (khususnya AKSESORIS) langsung tertaut (`material_id`). Sebelumnya BOM
        # demo lahir dengan `material_id: None` → link-health selalu "tidak sehat"
        # dan "Perbaiki Otomatis" pun tak bisa menolong karena kode aksesorisnya
        # (ACC-BTN-12 / ACC-LBL-01) memang belum pernah ada di master material.
        _demo_bom_mats = [
            # (code, name, unit, type, unit_cost, qty/pcs, category_name, notes)
            ("YRN-ACR-28-BLU", "Benang Akrilik 2/28 Biru", "kg",  "yarn",      45000, 0.35, "Benang",    "warna utama"),
            ("ACC-BTN-12",     "Kancing bulat plastik",    "pcs", "accessory", 200,   6,    "Aksesoris", "uk. 12mm"),
            ("ACC-LBL-01",     "Label merek",              "pcs", "accessory", 350,   1,    "Aksesoris", ""),
        ]
        _bom_lines = []
        for code, name, unit, mtype, cost, qty, cat_name, notes in _demo_bom_mats:
            mat = await db.rahaza_materials.find_one({"code": code}, {"_id": 0})
            if not mat:
                mat = {
                    "id": _uid(), "code": code, "name": name, "type": mtype, "unit": unit,
                    # FASE 6.6-B: kanonik `composition` + alias legacy `yarn_type`
                    **material_fields.mirror("composition", "acrylic" if mtype == "yarn" else ""),
                    "color": "",
                    "min_stock": 0, "unit_cost": cost, "active": True,
                    "created_at": _now(), "updated_at": _now(),
                }
                await db.rahaza_materials.insert_one(mat)
                out["created"]["materials"] = out["created"].get("materials", 0) + 1
            elif not mat.get("unit_cost"):
                await db.rahaza_materials.update_one(
                    {"id": mat["id"]}, {"$set": {"unit_cost": cost, "updated_at": _now()}})
            _bom_lines.append({
                "material_id": mat["id"], "name": name, "code": code,
                "material_type": mtype, "category": "", "category_name": cat_name,
                "qty": qty, "unit": unit, "notes": notes,
            })

        existing_bom = await db.rahaza_boms.find_one({
            "model_id": model_id, "size_id": size_m_id, "active": True
        })
        if not existing_bom:
            await db.rahaza_boms.insert_one({
                "id": _uid(),
                "model_id": model_id,
                "size_id": size_m_id,
                "color": "",
                "version": 1,
                "is_active": True,
                "materials": _bom_lines,
                "notes": "BOM sample — Sweater Demo Size M",
                "active": True,
                "created_at": _now(),
                "updated_at": _now(),
            })
            out["created"]["boms"] += 1
        else:
            # Idempoten & self-healing: BOM demo lama (dibuat versi seeder
            # sebelumnya) masih menyimpan `material_id: None`. Tautkan by-code
            # tanpa mengubah qty/notes yang mungkin sudah diedit user.
            _code_to_id = {ln["code"]: ln["material_id"] for ln in _bom_lines}
            _lines = existing_bom.get("materials") or []
            _touched = False
            for ln in _lines:
                if not ln.get("material_id") and _code_to_id.get(ln.get("code")):
                    ln["material_id"] = _code_to_id[ln["code"]]
                    _touched = True
            if _touched:
                await db.rahaza_boms.update_one(
                    {"id": existing_bom["id"]},
                    {"$set": {"materials": _lines, "updated_at": _now()}})
                out["created"]["bom_lines_relinked"] = out["created"].get("bom_lines_relinked", 0) + 1

    # ── Demo Order internal ──
    existing_order = await db.rahaza_orders.find_one({"order_number": {"$regex": "^DEMO-"}})
    if not existing_order:
        order_id = _uid()
        # Count orders hari ini untuk order_number
        today_iso = date.today().strftime("%Y%m%d")
        order_number = f"DEMO-{today_iso}-001"
        items = []
        for sz_code in ["S", "M", "L", "XL"]:
            sid = size_id_by_code.get(sz_code)
            if not sid:
                continue
            items.append({
                "id": _uid(),
                "model_id": model_id,
                "size_id": sid,
                "size_code": sz_code,
                "qty": 20,
                "notes": "",
            })
        await db.rahaza_orders.insert_one({
            "id": order_id,
            "order_number": order_number,
            "order_date": date.today().isoformat(),
            "due_date": None,
            "customer_id": None,
            "customer_name": "Produksi Internal (Demo)",
            "is_internal": True,
            "status": "draft",
            "items": items,
            "item_count": len(items),
            "total_qty": sum(i["qty"] for i in items),
            "notes": "Order demo dibuat otomatis oleh Setup Wizard untuk uji coba alur.",
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": user.get("email") or user.get("name"),
        })
        out["created"]["orders"] += 1
        # AUDIT 2026-09-03: menu 'Order Produksi' & 'Work Order' sudah tidak ada di Portal
        # Produksi (engine multi-stage dihapus FASE 4). Order demo langsung dijadikan
        # PO Internal lewat adapter resmi supaya data contoh muncul di alur yang nyata.
        try:
            from routes.production_internal_adapter import create_po_from_order
            po = await create_po_from_order(order_id, request)
            out["created"]["production_pos"] = 1
            out["messages"].append(
                f"PO Internal demo '{(po or {}).get('po_number', '')}' dibuat dari order "
                f"'{order_number}'. Buka Produksi Internal → PO Internal untuk mulai alur.")
        except Exception as e:  # noqa: BLE001
            logger.warning("seed-sample: konversi order→PO gagal: %s", e)
            out["messages"].append(
                f"Order demo '{order_number}' dibuat, tetapi belum jadi PO Internal ({e}). "
                f"Buat PO lewat Produksi Internal → PO Internal.")
    else:
        existing_po = await db.production_pos.find_one(
            {"source_order_id": existing_order["id"]}, {"_id": 0, "po_number": 1, "status": 1})
        if existing_po:
            out["messages"].append(
                f"PO Internal demo sudah ada: '{existing_po.get('po_number', '')}' "
                f"(status {existing_po.get('status', '-')}). Buka Produksi Internal → PO Internal.")
        else:
            out["messages"].append(
                f"Order demo '{existing_order.get('order_number', '')}' sudah ada tetapi belum "
                f"menjadi PO Internal. Buat PO lewat Produksi Internal → PO Internal.")

    # ── Update setup state ──
    uid = await _uid_of_user(user)
    await db.rahaza_setup_state.update_one(
        {"user_id": uid},
        {"$set": {
            "user_id": uid,
            "status": "seeded",
            "last_action": "seed_sample",
            "updated_at": _now(),
        }},
        upsert=True,
    )

    out["message"] = ("Sample data sudah lengkap — tidak ada yang ditambahkan. "
                      if not any(out["created"].values()) else
                      "Sample data berhasil diseed. ") + "Silakan lanjutkan eksplorasi menu Produksi."
    return out


# ─── SKIP ────────────────────────────────────────────────────────────────────
@router.post("/skip")
async def skip_wizard(request: Request):
    """Mark wizard sebagai 'skipped' untuk user saat ini (24 jam)."""
    user = await require_auth(request)
    db = get_db()
    uid = await _uid_of_user(user)
    await db.rahaza_setup_state.update_one(
        {"user_id": uid},
        {"$set": {
            "user_id": uid,
            "status": "skipped",
            "updated_at": _now(),
        }},
        upsert=True,
    )
    return {"ok": True, "status": "skipped"}


# ─── DISMISS ─────────────────────────────────────────────────────────────────
@router.post("/dismiss")
async def dismiss_wizard(request: Request):
    """Mark wizard sebagai 'dismissed' (permanent — tidak akan auto-tampil lagi)."""
    user = await require_auth(request)
    db = get_db()
    uid = await _uid_of_user(user)
    await db.rahaza_setup_state.update_one(
        {"user_id": uid},
        {"$set": {
            "user_id": uid,
            "status": "dismissed",
            "updated_at": _now(),
        }},
        upsert=True,
    )
    return {"ok": True, "status": "dismissed"}


# ─── RESET ───────────────────────────────────────────────────────────────────
@router.post("/reset")
async def reset_wizard_state(request: Request):
    """Admin-only: reset state user agar wizard muncul lagi (untuk testing)."""
    user = await require_auth(request)
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(403, "Hanya admin")
    db = get_db()
    uid = await _uid_of_user(user)
    await db.rahaza_setup_state.delete_one({"user_id": uid})
    return {"ok": True}
