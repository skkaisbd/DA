"""
Approval Chain Service — Multi-Level Sequential Approval Engine
CV. Dewi Aditya — Task 2.4

Supports: leave, overtime, salary_adjustment, expense, purchase_order,
          material_request, resignation, asset_purchase

Flow:
  requester submit → Level 1 approver → Level 2 approver → ... → APPROVED/REJECTED

Collections:
  approval_chains         — konfigurasi rantai approval per tipe+threshold
  approval_requests       — instance approval request yang aktif
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from utils.counters import next_counter

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return str(v)


# ─── Default approval chains ─────────────────────────────────────────────────

DEFAULT_CHAINS: List[Dict] = [
    {
        "type": "leave",
        "name": "Cuti Panjang (≥ 3 hari)",
        "condition": {"days_gte": 3},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer / Supervisor"},
            {"level": 2, "role": "hr",           "label": "HR Department"},
            {"level": 3, "role": "owner",        "label": "Direktur"},
        ],
    },
    {
        "type": "leave",
        "name": "Cuti Pendek (< 3 hari)",
        "condition": {"days_lt": 3},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer / Supervisor"},
        ],
    },
    {
        "type": "overtime",
        "name": "Lembur",
        "condition": {},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer"},
            {"level": 2, "role": "hr",           "label": "HR"},
        ],
    },
    {
        "type": "salary_adjustment",
        "name": "Penyesuaian Gaji",
        "condition": {},
        "levels": [
            {"level": 1, "role": "hr",           "label": "HR Department"},
            {"level": 2, "role": "owner",        "label": "Direktur / Owner"},
        ],
    },
    {
        "type": "expense",
        "name": "Expense Claim ≥ 1jt",
        "condition": {"amount_gte": 1_000_000},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer"},
            {"level": 2, "role": "owner",        "label": "Owner / Direktur"},
        ],
    },
    {
        "type": "expense",
        "name": "Expense Claim < 1jt",
        "condition": {"amount_lt": 1_000_000},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer"},
        ],
    },
    {
        "type": "purchase_order",
        "name": "Purchase Order ≥ 5jt",
        "condition": {"amount_gte": 5_000_000},
        "levels": [
            {"level": 1, "role": "admin",        "label": "Admin Purchasing"},
            {"level": 2, "role": "manager",      "label": "Manajer"},
            {"level": 3, "role": "owner",        "label": "Owner"},
        ],
    },
    {
        "type": "material_return",
        "name": "Return Material Produksi",
        "condition": {},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Supervisor Produksi"},
            {"level": 2, "role": "admin",        "label": "Gudang"},
        ],
    },
    # ── Resignation (Pengunduran Diri) ─────────────────────────────────────────
    {
        "type": "resignation",
        "name": "Pengunduran Diri Karyawan",
        "condition": {},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer / Supervisor Langsung"},
            {"level": 2, "role": "hr",           "label": "HR Department"},
            {"level": 3, "role": "owner",        "label": "Direktur / Owner"},
        ],
    },
    # ── Asset Purchase (Pembelian Aset Baru) ───────────────────────────────────
    {
        "type": "asset_purchase",
        "name": "Pembelian Aset ≥ 10jt",
        "condition": {"amount_gte": 10_000_000},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer Departemen"},
            {"level": 2, "role": "admin",        "label": "Admin Purchasing"},
            {"level": 3, "role": "owner",        "label": "Owner / Direktur"},
        ],
    },
    {
        "type": "asset_purchase",
        "name": "Pembelian Aset < 10jt",
        "condition": {"amount_lt": 10_000_000},
        "levels": [
            {"level": 1, "role": "manager",      "label": "Manajer Departemen"},
            {"level": 2, "role": "admin",        "label": "Admin Purchasing"},
        ],
    },
]


async def seed_default_chains(db) -> None:
    """Seed default chains jika belum ada (hanya saat collection kosong)."""
    existing = await db.approval_chains.count_documents({})
    if existing > 0:
        return
    for idx, chain in enumerate(DEFAULT_CHAINS):
        chain_id = await next_counter(db, "approval_chains")
        doc = {
            **chain,
            "id": chain_id,
            "is_active": True,
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        }
        await db.approval_chains.insert_one(doc)
    logger.info("Seeded %d default approval chains.", len(DEFAULT_CHAINS))


async def seed_missing_chains(db) -> dict:
    """Upsert chains yang belum ada by (type, name) — idempotent, aman dijalankan berulang.

    Returns:
        {"added": N, "skipped": M, "types_added": [...]}
    """
    added, skipped = 0, 0
    types_added = []
    for chain in DEFAULT_CHAINS:
        existing = await db.approval_chains.find_one(
            {"type": chain["type"], "name": chain["name"]}
        )
        if existing:
            skipped += 1
            continue
        chain_id = await next_counter(db, "approval_chains")
        doc = {
            **chain,
            "id": chain_id,
            "is_active": True,
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        }
        await db.approval_chains.insert_one(doc)
        added += 1
        types_added.append(f"{chain['type']}: {chain['name']}")
        logger.info("Seeded missing chain: type=%s name=%s", chain["type"], chain["name"])
    return {"added": added, "skipped": skipped, "types_added": types_added}


# ─── Chain matching ───────────────────────────────────────────────────────────

def _match_condition(cond: Dict, meta: Dict) -> bool:
    """Check if request metadata matches a chain condition."""
    if not cond:
        return True
    amount = meta.get("amount", 0) or 0
    days   = meta.get("days", 0) or 0
    for key, val in cond.items():
        if key == "amount_gte" and amount < val:
            return False
        if key == "amount_lt" and amount >= val:
            return False
        if key == "days_gte" and days < val:
            return False
        if key == "days_lt" and days >= val:
            return False
    return True


async def find_chain(db, req_type: str, meta: Dict) -> Optional[Dict]:
    """Return the first matching active chain for this type + metadata."""
    chains = await db.approval_chains.find(
        {"type": req_type, "is_active": True}, {"_id": 0}
    ).to_list(length=50)
    for ch in chains:
        if _match_condition(ch.get("condition", {}), meta):
            return ch
    return None


# ─── Create approval request ──────────────────────────────────────────────────

async def create_approval_request(
    db,
    req_type: str,
    ref_id: str,
    ref_code: str,
    requester: Dict,
    meta: Optional[Dict] = None,
    subject: str = "",
) -> Optional[Dict]:
    """Create a multi-level approval request. Returns None if no matching chain."""
    meta = meta or {}
    chain = await find_chain(db, req_type, meta)
    if not chain:
        logger.warning("No approval chain found for type=%s meta=%s", req_type, meta)
        return None

    levels_state = [
        {
            "level": lv["level"],
            "role": lv["role"],
            "label": lv["label"],
            "status": "pending" if lv["level"] == 1 else "waiting",
            "approver_id": None,
            "approver_name": None,
            "note": "",
            "actioned_at": None,
        }
        for lv in chain.get("levels", [])
    ]

    request_id = await next_counter(db, "approval_requests")
    now = _now().isoformat()
    doc = {
        "id": request_id,
        "type": req_type,
        "ref_id": ref_id,
        "ref_code": ref_code,
        "subject": subject or f"{req_type} — {ref_code}",
        "chain_id": chain["id"],
        "chain_name": chain["name"],
        "requester_id": requester.get("id") or requester.get("_id") or "",
        "requester_name": requester.get("name") or requester.get("full_name") or requester.get("email") or "",
        "current_level": 1,
        "max_level": len(levels_state),
        "status": "pending",       # pending | approved | rejected | cancelled
        "levels": levels_state,
        "meta": meta,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    await db.approval_requests.insert_one({"_id": request_id, **doc})
    return doc


# ─── Process action ───────────────────────────────────────────────────────────

# RBAC rantai approval (2026-08-07): role tahap ("manager"/"hr"/"owner"/"admin")
# dipetakan ke role nyata di sistem. Admin/owner/superadmin selalu boleh.
LEVEL_ROLE_ALIASES = {
    "manager": {"manager", "manager_produksi", "manager_keuangan", "manager_hr",
                "hr_manager", "manager_marketing", "supervisor", "supervisor_produksi",
                "spv_packing", "spv_cuting", "spv_aksesoris", "director"},
    "hr": {"hr", "hr_manager", "manager_hr", "staff_hr"},
    "owner": {"owner", "director"},
    "admin": {"admin", "admin_produksi", "admin_gudang", "admin_maklon",
              "admin_aksesoris", "admin_marketing"},
    "finance": {"accounting", "staff_keuangan", "manager_keuangan"},
}
LEVEL_SUPER_ROLES = {"superadmin", "admin", "owner"}


def _may_act_on_level(user: Dict, lv_entry: Dict) -> bool:
    role = (user.get("role") or "").lower()
    if role in LEVEL_SUPER_ROLES:
        return True
    want = str(lv_entry.get("role") or "").lower()
    if not want:
        return True          # rantai tanpa role → jangan blokir alur lama
    return role in LEVEL_ROLE_ALIASES.get(want, {want})


async def process_action(
    db,
    request_id,      # int atau str — dihandle oleh _coerce
    action: str,       # "approve" | "reject"
    user: Dict,
    note: str = "",
) -> Dict:
    """Process approve/reject at current level. Returns updated request doc."""
    _id = int(request_id) if str(request_id).isdigit() else request_id
    doc = await db.approval_requests.find_one({"id": _id}, {"_id": 0})
    if not doc:
        raise ValueError(f"Approval request {request_id!r} tidak ditemukan.")
    if doc["status"] not in ("pending",):
        raise ValueError(f"Request sudah {doc['status']}, tidak bisa diubah.")

    current_level = doc["current_level"]
    levels = doc["levels"]
    # Find current level entry
    lv_entry = next((lv for lv in levels if lv["level"] == current_level), None)
    if not lv_entry:
        raise ValueError("Level entry tidak ditemukan.")

    now = _now().isoformat()
    lv_entry["status"] = "approved" if action == "approve" else "rejected"
    lv_entry["approver_id"] = str(user.get("id") or user.get("_id") or "")
    lv_entry["approver_name"] = user.get("full_name") or user.get("name") or user.get("email") or ""
    lv_entry["note"] = note
    lv_entry["actioned_at"] = now

    if action == "reject":
        # Rejection cascades — mark remaining levels as skipped
        for lv in levels:
            if lv["level"] > current_level:
                lv["status"] = "skipped"
        new_status = "rejected"
        completed_at = now
    elif current_level >= doc["max_level"]:
        # Final level approved
        new_status = "approved"
        completed_at = now
    else:
        # Move to next level
        next_level = current_level + 1
        next_lv = next((lv for lv in levels if lv["level"] == next_level), None)
        if next_lv:
            next_lv["status"] = "pending"
        new_status = "pending"
        current_level = next_level
        completed_at = None

    update = {
        "status": new_status,
        "current_level": current_level,
        "levels": levels,
        "updated_at": now,
        "completed_at": completed_at if action == "reject" or new_status == "approved" else doc.get("completed_at"),
    }
    await db.approval_requests.update_one({"id": _id}, {"$set": update})

    current_level = doc["current_level"]
    levels = doc["levels"]
    # Find current level entry
    lv_entry = next((lv for lv in levels if lv["level"] == current_level), None)
    if not lv_entry:
        raise ValueError("Level entry tidak ditemukan.")

    now = _now().isoformat()
    lv_entry["status"] = "approved" if action == "approve" else "rejected"
    lv_entry["approver_id"] = str(user.get("id") or user.get("_id") or "")
    lv_entry["approver_name"] = user.get("full_name") or user.get("name") or user.get("email") or ""
    lv_entry["note"] = note
    lv_entry["actioned_at"] = now

    if action == "reject":
        # Rejection cascades — mark remaining levels as skipped
        for lv in levels:
            if lv["level"] > current_level:
                lv["status"] = "skipped"
        new_status = "rejected"
        completed_at = now
    elif current_level >= doc["max_level"]:
        # Final level approved
        new_status = "approved"
        completed_at = now
    else:
        # Move to next level
        next_level = current_level + 1
        next_lv = next((lv for lv in levels if lv["level"] == next_level), None)
        if next_lv:
            next_lv["status"] = "pending"
        new_status = "pending"
        current_level = next_level
        completed_at = None

    update = {
        "status": new_status,
        "current_level": current_level,
        "levels": levels,
        "updated_at": now,
        "completed_at": completed_at if action == "reject" or new_status == "approved" else doc.get("completed_at"),
    }
    await db.approval_requests.update_one({"id": request_id}, {"$set": update})
    return {**doc, **update}


# ─── Pending for user ─────────────────────────────────────────────────────────

async def get_pending_for_user(
    db,
    user_role: str,
    user_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    """Return pending approval requests that this user (by role) should action."""
    role = (user_role or "").lower()
    # Find all requests that are pending AND current level matches user's role
    all_pending = await db.approval_requests.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).limit(200).to_list(200)

    result = []
    for req in all_pending:
        current_level = req.get("current_level", 1)
        levels = req.get("levels", [])
        lv = next((lv for lv in levels if lv["level"] == current_level), None)
        if not lv:
            continue
        required_role = (lv.get("role") or "").lower()
        # superadmin/owner can see everything
        if role in ("superadmin", "owner") or role == required_role:
            result.append(req)
        if len(result) >= limit:
            break
    return result
