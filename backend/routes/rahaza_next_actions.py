"""
PT Rahaza ERP — Next-Action Engine (Phase 16.2)

Rule-based deterministic engine yang menghasilkan "kartu next-action" untuk user
sesuai portal & state data saat ini. Bukan AI — semua rule eksplisit & testable.

Endpoint:
  GET /api/rahaza/next-actions?portal=production

Output schema:
  {
    "actions": [
      {
        "id": "unique-rule-id",
        "severity": "info"|"warning"|"error"|"success",
        "category": "setup"|"planning"|"execution"|"quality"|"inventory",
        "title": "...",
        "description": "...",
        "count": 3,             # optional, jumlah item yang kena
        "cta_label": "Buka ...",
        "cta_module": "prod-work-orders",   # moduleId sesuai PortalShell
        "cta_params": {...},    # opsional, state untuk deep-link
        "why": "Penjelasan kenapa ini penting",
        "created_at": iso
      }
    ],
    "meta": {"portal": "production", "generated_at": iso, "rule_count": 12}
  }

Aturan dismiss/snooze tersimpan di localStorage client (backend stateless).
"""
from fastapi import APIRouter, Request
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, timedelta, date
from typing import Optional
import logging
from utils.query_guards import q_int

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/next-actions", tags=["Next Actions"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


async def _count(db, collection: str, filter_: dict) -> int:
    return await db[collection].count_documents(filter_)


# ─── RULES ────────────────────────────────────────────────────────────────────
# Setiap rule adalah async function yang return None atau dict action card.

async def rule_setup_empty(db, portal: str) -> Optional[dict]:
    """Jika pabrik belum ada master minimum → tawarkan Setup Wizard."""
    loc = await _count(db, "rahaza_locations", {"active": True})
    proc = await _count(db, "rahaza_processes", {})
    lin = await _count(db, "rahaza_lines", {"active": True})
    emp = await _count(db, "rahaza_employees", {"active": True})
    mod = await _count(db, "rahaza_models", {"active": True})
    siz = await _count(db, "rahaza_sizes", {"active": True})

    missing = []
    if loc == 0:
        missing.append("Lokasi/Gedung")
    if proc == 0:
        missing.append("Proses Produksi")
    if lin == 0:
        missing.append("Line Produksi")
    if emp == 0:
        missing.append("Karyawan")
    if mod == 0:
        missing.append("Model Produk")
    if siz == 0:
        missing.append("Ukuran/Size")

    if not missing:
        return None

    return {
        "id": "setup-empty",
        "severity": "warning",
        "category": "setup",
        "title": "Setup dasar belum lengkap",
        "description": f"Belum ada: {', '.join(missing)}",
        "count": len(missing),
        "cta_label": "Mulai Setup Wizard",
        "cta_module": "__setup_wizard__",  # special action handled by frontend
        "cta_params": {"missing": missing},
        "why": "Tanpa master data dasar, Anda tidak bisa membuat Work Order, menugaskan operator, atau mencatat output. Ikuti wizard 7 langkah untuk mempercepat setup.",
    }


async def rule_wo_missing_bundles(db, portal: str) -> Optional[dict]:
    """WO released/in_production yang belum di-generate bundle-nya."""
    if portal != "production":
        return None
    wos = await db.rahaza_work_orders.find(
        {"status": {"$in": ["released", "in_production"]}},
        {"_id": 0, "id": 1, "wo_number": 1}
    ).to_list(500)

    orphan = []
    for w in wos:
        bc = await _count(db, "rahaza_bundles", {"work_order_id": w["id"]})
        if bc == 0:
            orphan.append(w)

    if not orphan:
        return None

    sample = ", ".join(w["wo_number"] for w in orphan[:3])
    more = f" (+{len(orphan)-3})" if len(orphan) > 3 else ""
    return {
        "id": "wo-missing-bundles",
        "severity": "warning",
        "category": "execution",
        "title": f"{len(orphan)} WO produksi belum di-generate bundle",
        "description": f"{sample}{more}",
        "count": len(orphan),
        "cta_label": "Buka Work Order",
        "cta_module": "prod-work-orders",
        "why": "Bundle adalah unit traceable berisi 20–50 pcs yang dipakai untuk tracking per-proses & QR scan. Tanpa bundle, WIP tidak granular dan operator harus input manual WO/model/size (rawan salah).",
    }


async def rule_orders_without_wo(db, portal: str) -> Optional[dict]:
    """Order confirmed/in_production yang belum ada WO aktif."""
    if portal != "production":
        return None
    orders = await db.rahaza_orders.find(
        {"status": {"$in": ["confirmed", "in_production"]}},
        {"_id": 0, "id": 1, "order_number": 1}
    ).to_list(500)

    orphan = []
    for o in orders:
        wo_count = await _count(db, "rahaza_work_orders", {
            "order_id": o["id"],
            "status": {"$ne": "cancelled"}
        })
        if wo_count == 0:
            orphan.append(o)

    if not orphan:
        return None

    sample = ", ".join(o["order_number"] for o in orphan[:3])
    more = f" (+{len(orphan)-3})" if len(orphan) > 3 else ""
    return {
        "id": "orders-without-wo",
        "severity": "warning",
        "category": "execution",
        "title": f"{len(orphan)} order siap tapi belum punya Work Order",
        "description": f"{sample}{more}",
        "count": len(orphan),
        "cta_label": "Buka Order Produksi",
        "cta_module": "prod-orders",
        "why": "Order yang confirmed tanpa WO berarti produksi belum dimulai. Generate WO langsung dari halaman Order — 1 klik akan membuat WO untuk semua item.",
    }


async def rule_wo_without_mi(db, portal: str) -> Optional[dict]:
    """WO released/in_production belum ada Material Issue."""
    if portal != "production":
        return None
    wos = await db.rahaza_work_orders.find(
        {"status": {"$in": ["released", "in_production"]}},
        {"_id": 0, "id": 1, "wo_number": 1, "bom_snapshot": 1}
    ).to_list(500)

    orphan = []
    for w in wos:
        # Skip kalau tidak ada BOM snapshot (tidak bisa di-MI anyway)
        if not (w.get("bom_snapshot") or {}).get("bom_id"):
            continue
        mi_count = await _count(db, "rahaza_material_issues", {
            "work_order_id": w["id"],
            "status": {"$ne": "cancelled"}
        })
        if mi_count == 0:
            orphan.append(w)

    if not orphan:
        return None

    sample = ", ".join(w["wo_number"] for w in orphan[:3])
    more = f" (+{len(orphan)-3})" if len(orphan) > 3 else ""
    return {
        "id": "wo-without-mi",
        "severity": "warning",
        "category": "execution",
        "title": f"{len(orphan)} WO produksi belum ada Material Issue",
        "description": f"{sample}{more}",
        "count": len(orphan),
        "cta_label": "Buat Material Issue",
        "cta_module": "wh-material-issue",
        "why": "Tanpa Material Issue, material belum resmi keluar dari gudang ke line. Gunakan 'Draft dari WO' untuk generate otomatis sesuai BOM.",
    }


async def rule_wo_missing_bom(db, portal: str) -> Optional[dict]:
    """WO draft/released tanpa BOM snapshot."""
    if portal != "production":
        return None
    wos = await db.rahaza_work_orders.find(
        {"status": {"$in": ["draft", "released", "in_production"]}},
        {"_id": 0, "id": 1, "wo_number": 1, "model_code": 1, "size_code": 1, "bom_snapshot": 1}
    ).to_list(500)

    missing = [w for w in wos if not (w.get("bom_snapshot") or {}).get("bom_id")]
    if not missing:
        return None

    # Unique model-size pairs
    pairs = sorted({f"{w.get('model_code','?')}·{w.get('size_code','?')}" for w in missing})
    return {
        "id": "wo-missing-bom",
        "severity": "error",
        "category": "planning",
        "title": f"{len(missing)} WO tidak punya BOM",
        "description": f"Model·Size yang belum ada BOM: {', '.join(pairs[:4])}{'…' if len(pairs)>4 else ''}",
        "count": len(missing),
        "cta_label": "Lengkapi BOM",
        "cta_module": "prod-bom",
        "why": "Tanpa BOM, sistem tidak tahu berapa benang dan aksesoris yang dibutuhkan. Material Issue juga tidak bisa dibuat. Definisikan BOM per Model & Size.",
    }


async def rule_lines_without_assignment_today(db, portal: str) -> Optional[dict]:
    """Line aktif yang belum di-assign hari ini."""
    if portal != "production":
        return None
    today = _today_iso()
    lines = await db.rahaza_lines.find(
        {"active": True},
        {"_id": 0, "id": 1, "code": 1, "name": 1}
    ).to_list(500)

    unassigned = []
    for ln in lines:
        a = await _count(db, "rahaza_line_assignments", {
            "line_id": ln["id"],
            "assign_date": today,
            "active": {"$ne": False},
        })
        if a == 0:
            unassigned.append(ln)

    if not unassigned:
        return None

    sample = ", ".join(ln["code"] for ln in unassigned[:4])
    more = f" (+{len(unassigned)-4})" if len(unassigned) > 4 else ""
    return {
        "id": "lines-no-assignment-today",
        "severity": "warning",
        "category": "execution",
        "title": f"{len(unassigned)} line aktif belum di-assign hari ini",
        "description": f"{sample}{more}",
        "count": len(unassigned),
        "cta_label": "Assign Line Hari Ini",
        "cta_module": "prod-assignments",
        "cta_params": {"date": today},
        "why": "Line tanpa assignment → operator tidak tahu apa yang harus dikerjakan, target tidak tercatat, dan output tidak bisa dianalisa. Tetapkan operator + shift + target per line setiap pagi.",
    }


async def rule_orders_due_soon(db, portal: str) -> Optional[dict]:
    """Order dengan due_date <= 3 hari & belum completed."""
    if portal not in ("production", "management"):
        return None
    today = date.today()
    limit = (today + timedelta(days=3)).isoformat()
    orders = await db.rahaza_orders.find(
        {"status": {"$nin": ["completed", "closed", "cancelled"]},
         "due_date": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "order_number": 1, "due_date": 1, "status": 1}
    ).to_list(500)

    soon = [o for o in orders if o.get("due_date") and today.isoformat() <= o["due_date"] <= limit]
    if not soon:
        return None

    sample = ", ".join(f"{o['order_number']} ({o['due_date']})" for o in soon[:2])
    more = f" (+{len(soon)-2})" if len(soon) > 2 else ""
    return {
        "id": "orders-due-soon",
        "severity": "warning",
        "category": "planning",
        "title": f"{len(soon)} order akan jatuh tempo ≤3 hari",
        "description": f"{sample}{more}",
        "count": len(soon),
        "cta_label": "Review Order",
        "cta_module": "prod-orders",
        "why": "Order yang hampir due perlu diprioritaskan. Cek progress WO terkait dan pastikan tidak ada hambatan material atau kapasitas.",
    }


async def rule_orders_overdue(db, portal: str) -> Optional[dict]:
    """Order overdue: due_date < today & belum completed."""
    if portal not in ("production", "management"):
        return None
    today = date.today().isoformat()
    orders = await db.rahaza_orders.find(
        {"status": {"$nin": ["completed", "closed", "cancelled"]},
         "due_date": {"$lt": today, "$nin": [None, ""]}},
        {"_id": 0, "id": 1, "order_number": 1, "due_date": 1}
    ).to_list(500)
    if not orders:
        return None

    sample = ", ".join(f"{o['order_number']} ({o['due_date']})" for o in orders[:2])
    more = f" (+{len(orders)-2})" if len(orders) > 2 else ""
    return {
        "id": "orders-overdue",
        "severity": "error",
        "category": "planning",
        "title": f"{len(orders)} order sudah overdue",
        "description": f"{sample}{more}",
        "count": len(orders),
        "cta_label": "Tindak Lanjuti",
        "cta_module": "prod-orders",
        "why": "Order yang lewat deadline berpengaruh ke on-time delivery rate & hubungan customer. Segera escalate ke manager produksi dan komunikasikan ke customer.",
    }


async def rule_low_stock_materials(db, portal: str) -> Optional[dict]:
    """Material dengan stok di bawah min_stock."""
    if portal not in ("production", "warehouse"):
        return None
    # Agregasi stok per material vs min_stock
    materials = await db.rahaza_materials.find(
        {"active": True, "min_stock": {"$gt": 0}},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "min_stock": 1}
    ).to_list(500)

    low = []
    for m in materials:
        stocks = await db.rahaza_material_stock.find(
            {"material_id": m["id"]},
            {"_id": 0, "qty": 1}
        ).to_list(500)
        total = sum(float(s.get("qty") or 0) for s in stocks)
        if total < float(m.get("min_stock") or 0):
            low.append({**m, "current": total})

    if not low:
        return None

    sample = ", ".join(m["code"] for m in low[:3])
    more = f" (+{len(low)-3})" if len(low) > 3 else ""
    return {
        "id": "low-stock",
        "severity": "error",
        "category": "inventory",
        "title": f"{len(low)} material di bawah stok minimum",
        "description": f"{sample}{more}",
        "count": len(low),
        "cta_label": "Buka Stok Material",
        "cta_module": "wh-stock",
        "why": "Stok yang rendah berisiko menghentikan produksi. Segera buat PO ke vendor atau transfer dari gudang lain.",
    }


async def rule_draft_mi_stale(db, portal: str) -> Optional[dict]:
    """Material Issue status draft > 24 jam."""
    if portal not in ("production", "warehouse"):
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = await db.rahaza_material_issues.find(
        {"status": "draft", "created_at": {"$lt": cutoff}},
        {"_id": 0, "id": 1, "mi_number": 1, "created_at": 1}
    ).to_list(500)
    if not rows:
        return None
    sample = ", ".join(r["mi_number"] for r in rows[:3])
    more = f" (+{len(rows)-3})" if len(rows) > 3 else ""
    return {
        "id": "mi-draft-stale",
        "severity": "warning",
        "category": "inventory",
        "title": f"{len(rows)} Material Issue draft > 24 jam",
        "description": f"{sample}{more}",
        "count": len(rows),
        "cta_label": "Review MI Draft",
        "cta_module": "wh-material-issue",
        "why": "MI yang mengendap di draft artinya material belum resmi keluar ke produksi. Konfirmasi atau batalkan agar stok akurat.",
    }


async def rule_qc_fail_rate_today(db, portal: str) -> Optional[dict]:
    """QC fail-rate hari ini > 8%."""
    if portal not in ("production", "management"):
        return None
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc).isoformat()
    events = await db.rahaza_wip_events.find(
        {"event_type": {"$in": ["qc_pass", "qc_fail"]}, "timestamp": {"$gte": start}},
        {"_id": 0, "event_type": 1, "qty": 1}
    ).to_list(500)
    total_pass = sum(float(e.get("qty") or 0) for e in events if e["event_type"] == "qc_pass")
    total_fail = sum(float(e.get("qty") or 0) for e in events if e["event_type"] == "qc_fail")
    total = total_pass + total_fail
    if total < 20:  # sample kecil, skip
        return None
    rate = (total_fail / total) * 100
    if rate < 8:
        return None
    return {
        "id": "qc-fail-rate-high",
        "severity": "error",
        "category": "quality",
        "title": f"QC fail rate hari ini {rate:.1f}%",
        "description": f"{int(total_fail)} pcs gagal dari {int(total)} pcs diperiksa",
        "count": int(total_fail),
        "cta_label": "Buka QC Station",
        "cta_module": "prod-exec-qc",
        "why": "Fail rate > 8% menandakan masalah sistematis (mesin, material, atau operator). Lakukan root-cause analisis dan hentikan proses bila perlu.",
    }


async def rule_assignments_missing_operator(db, portal: str) -> Optional[dict]:
    """Line assignment hari ini tanpa operator."""
    if portal != "production":
        return None
    today = _today_iso()
    rows = await db.rahaza_line_assignments.find(
        {"assign_date": today, "active": {"$ne": False},
         "$or": [{"operator_id": None}, {"operator_id": ""}]},
        {"_id": 0, "id": 1, "line_id": 1}
    ).to_list(500)
    if not rows:
        return None
    return {
        "id": "assignments-no-operator",
        "severity": "warning",
        "category": "execution",
        "title": f"{len(rows)} assignment hari ini tanpa operator",
        "description": "Line/shift sudah di-assign tapi operator belum ditetapkan.",
        "count": len(rows),
        "cta_label": "Lengkapi Operator",
        "cta_module": "prod-assignments",
        "why": "Tanpa operator, output tidak bisa di-attribute ke karyawan → payroll borongan & performance tracking tidak akurat.",
    }


async def rule_empty_database_hint(db, portal: str) -> Optional[dict]:
    """Pabrik baru, semua tabel transaksi kosong → saran demo."""
    if portal != "production":
        return None
    ord_count = await _count(db, "rahaza_orders", {})
    wo_count = await _count(db, "rahaza_work_orders", {})
    wip_count = await _count(db, "rahaza_wip_events", {})
    if ord_count > 0 or wo_count > 0 or wip_count > 0:
        return None
    # Hanya tampil kalau master data sudah ada (setup sudah jalan)
    mod_count = await _count(db, "rahaza_models", {"active": True})
    if mod_count == 0:
        return None
    return {
        "id": "empty-transactions",
        "severity": "info",
        "category": "setup",
        "title": "Belum ada transaksi apapun",
        "description": "Master data sudah lengkap — waktunya buat Order pertama atau WO internal.",
        "count": 0,
        "cta_label": "Buat Order Pertama",
        "cta_module": "prod-orders",
        "why": "Sistem siap dipakai! Mulai dengan satu Order pelanggan atau WO produksi internal untuk menguji alur end-to-end.",
    }


# ─── ENGINE ──────────────────────────────────────────────────────────────────
RULES = [
    rule_setup_empty,
    rule_empty_database_hint,
    rule_wo_missing_bom,
    rule_orders_overdue,
    rule_low_stock_materials,
    rule_qc_fail_rate_today,
    rule_wo_without_mi,
    rule_wo_missing_bundles,
    rule_lines_without_assignment_today,
    rule_orders_without_wo,
    rule_assignments_missing_operator,
    rule_orders_due_soon,
    rule_draft_mi_stale,
]

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2, "success": 3}


@router.get("")
async def get_next_actions(request: Request):
    """
    Return sorted actionable cards based on portal.

    Query params:
      - portal: production | management | warehouse | finance | hr (default: production)
      - limit: max cards (default 8, max 15)
    """
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    portal = (sp.get("portal") or "production").lower()
    limit = q_int(sp.get("limit"), default=8, name="limit", minimum=1, maximum=15, clamp=True)

    cards = []
    for rule in RULES:
        try:
            card = await rule(db, portal)
            if card:
                card["created_at"] = _now()
                cards.append(card)
        except Exception as e:
            logger.warning(f"NAE rule {rule.__name__} failed: {e}")
            continue

    # Sort by severity then by count desc
    cards.sort(key=lambda c: (SEVERITY_ORDER.get(c.get("severity"), 9), -int(c.get("count") or 0)))

    return {
        "actions": cards[:limit],
        "meta": {
            "portal": portal,
            "generated_at": _now(),
            "rule_count": len(RULES),
            "user": user.get("name") or user.get("email"),
        }
    }
