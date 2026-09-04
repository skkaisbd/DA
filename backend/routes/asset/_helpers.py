"""
Shared helpers, constants, and the FastAPI router instance for Asset Management.

All sub-modules import `router` from here and attach @router.<method>(...)
decorators to register their endpoints.
"""
from fastapi import APIRouter
from datetime import datetime, timezone, date
import uuid
import logging
from typing import Optional  # noqa: F401  (re-exported for sub-modules)

logger = logging.getLogger("asset_mgmt")

# ─── Router (shared across all asset sub-modules) ─────────────────────────
router = APIRouter(prefix="/api/assets", tags=["asset-management"])


# ─── Tiny utilities ──────────────────────────────────────────────────────
def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ser(doc):
    """Strip Mongo `_id` and stringify datetimes."""
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── Category seed ────────────────────────────────────────────────────────
DEFAULT_CATEGORIES = [
    {"name": "Peralatan IT",    "code": "IT",  "useful_life_years": 4,  "depr_method": "straight_line"},
    {"name": "Mesin Produksi",  "code": "MP",  "useful_life_years": 10, "depr_method": "straight_line"},
    {"name": "Kendaraan",       "code": "KD",  "useful_life_years": 5,  "depr_method": "double_declining"},
    {"name": "Bangunan",        "code": "BG",  "useful_life_years": 20, "depr_method": "straight_line"},
    {"name": "Perabot & Mebel", "code": "PM",  "useful_life_years": 8,  "depr_method": "straight_line"},
    {"name": "Alat & Perkakas", "code": "AP",  "useful_life_years": 5,  "depr_method": "straight_line"},
    {"name": "Lain-lain",       "code": "LN",  "useful_life_years": 5,  "depr_method": "straight_line"},
]

DISPOSAL_APPROVAL_THRESHOLD = 5_000_000  # 5 juta IDR


async def _ensure_default_categories(db):
    cnt = await db.dewi_asset_categories.count_documents({})
    if cnt == 0:
        seed = []
        for cat in DEFAULT_CATEGORIES:
            d = dict(cat)
            d["id"] = _uid()
            d["created_at"] = _now()
            seed.append(d)
        await db.dewi_asset_categories.insert_many(seed)


async def _gen_asset_number(db, category_code: str, requested: str = "") -> str:
    """Nomor aset inventaris — SATU PINTU kebijakan penomoran (SESI #27).

    `{KATEGORI}` menjaga satu seri per kategori aset seperti sebelumnya
    (`AST-<KATEGORI>-<TAHUN>-0001`) dan membuat formatnya bisa diatur owner.
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, "dewi_assets.asset_number",
                              ctx={"KATEGORI": category_code}, requested=requested)


def _calc_straight_line_monthly(cost: float, residual: float, life_months: int) -> float:
    if life_months <= 0:
        return 0.0
    return round((cost - residual) / life_months, 2)


def _calc_nbv(asset: dict) -> float:
    """Net Book Value = purchase_cost − accumulated_depreciation."""
    return round(
        float(asset.get("purchase_cost", 0)) - float(asset.get("accumulated_depreciation", 0)),
        2,
    )


async def _create_finance_journal(db, user_id: str, user_name: str, date_str: str,
                                   memo: str, lines: list,
                                   source_module: str = "asset_management",
                                   source_ref: Optional[str] = None) -> Optional[str]:
    """Create a draft journal entry in rahaza_journal_entries. Returns je_id (or None on failure)."""
    try:
        year_prefix = date_str[:7].replace("-", "")
        # RC-5 fix: atomic race-safe numbering (was count_documents()+1 -> dup/E11000 under concurrency)
        from utils.counters import gen_prefixed_number
        je_number = await gen_prefixed_number(
            db, "rahaza_journal_entries", "je_number", f"JE-{year_prefix}-", 5)
        je_id = _uid()
        total_debit = sum(float(ln.get("debit", 0)) for ln in lines)
        total_credit = sum(float(ln.get("credit", 0)) for ln in lines)
        doc = {
            "id": je_id,
            "je_number": je_number,
            "date": date_str,
            "memo": memo,
            "source_module": source_module,
            "source_ref": source_ref,
            "status": "draft",
            "total_debit": total_debit,
            "total_credit": total_credit,
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": user_id,
            "created_by_name": user_name,
            "posted_at": None,
            "posted_by": None,
            "voided_at": None,
            "voided_by": None,
            "lines": [
                {
                    "line_id": _uid(),
                    "account_code": ln.get("account_code", ""),
                    "account_name": ln.get("account_name", ""),
                    "account_type": ln.get("account_type", "asset"),
                    "debit": float(ln.get("debit", 0)),
                    "credit": float(ln.get("credit", 0)),
                    "description": ln.get("description", ""),
                    "cost_center_id": None,
                } for ln in lines
            ],
        }
        await db.rahaza_journal_entries.insert_one(doc)
        return je_id
    except Exception as e:
        logger.warning(f"[AssetMgmt] Journal creation failed: {e}")
        return None


# ─── Utilization-report date helpers ──────────────────────────────────────
def _parse_date_yyyymmdd(s: Optional[str], default: date) -> date:
    if not s:
        return default
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return default


def _days_between(d1: date, d2: date) -> int:
    """Inclusive day count between d1 and d2 (d2 >= d1)."""
    if d2 < d1:
        return 0
    return (d2 - d1).days + 1


def _intersect_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    """Overlap days between [a_start..a_end] and [b_start..b_end]."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _safe_avg_interval_days(dates_iso_desc):
    """Given maintenance date strings (YYYY-MM-DD), compute avg interval (days).
    Returns None if < 2 valid dates."""
    if len(dates_iso_desc) < 2:
        return None
    parsed = []
    for d in dates_iso_desc:
        try:
            parsed.append(datetime.strptime(str(d)[:10], "%Y-%m-%d").date())
        except Exception:
            continue
    if len(parsed) < 2:
        return None
    parsed.sort(reverse=True)
    diffs = [(parsed[i] - parsed[i + 1]).days for i in range(len(parsed) - 1)]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    return sum(diffs) / len(diffs)


# ─── Index creation (called at server startup if wired) ──────────────────
async def create_asset_indexes(db):
    await db.dewi_assets.create_index([("status", 1), ("category_id", 1)])
    await db.dewi_assets.create_index([("asset_number", 1)], unique=True, sparse=True)
    await db.dewi_assets.create_index([("assigned_to_id", 1)])
    await db.dewi_asset_depreciation.create_index([("asset_id", 1), ("period", 1)], unique=True)
    await db.dewi_asset_assignments.create_index([("asset_id", 1), ("status", 1)])
    await db.dewi_asset_maintenance.create_index([("asset_id", 1), ("maintenance_date", -1)])
    await db.dewi_asset_pm_acknowledgments.create_index([("asset_id", 1), ("acknowledged_at", -1)])
    # ACC-3 — peminjaman aset (dewi_asset_loans)
    await db.dewi_asset_loans.create_index([("status", 1), ("expected_return_date", 1)])
    await db.dewi_asset_loans.create_index([("asset_id", 1), ("status", 1)])
    await db.dewi_asset_loans.create_index([("loan_number", 1)], unique=True, sparse=True)
