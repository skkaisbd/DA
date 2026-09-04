# ruff: noqa: F401
"""
marketing_shared.py — Shared Helpers & Models
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
"""
import uuid
import html
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from typing import Optional, List

from core import marketing_sales_shape as _shape

def _uid():
    return str(uuid.uuid4())

def _now():
    return datetime.now(timezone.utc)

def _get_user(request):
    """Helper to safely get user from request.state"""
    return getattr(request.state, 'user', {"id": "system", "email": "system", "role": "admin"})

def _sanitize(value: str, max_len: int = 500) -> str:
    """Sanitize user input"""
    if not value:
        return ''
    sanitized = html.escape(str(value)[:max_len])
    return sanitized

# ═══ PYDANTIC MODELS ═══

class PlatformAccountCreate(BaseModel):
    account_code: str
    account_name: str
    platform: str
    username: Optional[str] = None
    group: Optional[str] = "other"
    has_api_integration: bool = False
    # ── F0.7 (2026-08-12) — tautan ke Finance & basis omzet ───────────────────
    # Kenapa: COA sudah punya akun pendapatan PER TOKO (`4-111`…`4-131`),
    # `1-220 Piutang Platform Online Shop`, `4-141 Potongan Platform`, tetapi
    # master toko tidak pernah menyimpan tautannya ⇒ akun-akun itu tidak pernah
    # terpakai, dan pencairan marketplace (F9) tidak punya alamat jurnal.
    coa_revenue_code: Optional[str] = None      # mis. 4-122 (TikTok Outfit Boutique)
    coa_cash_code: Optional[str] = None         # rekening penerima pencairan (1-131/1-154)
    coa_receivable_code: Optional[str] = None   # default 1-220
    platform_warehouse_name: Optional[str] = None   # nama gudang di ekspor platform
    platform_shop_id: Optional[str] = None
    revenue_basis: Optional[str] = None         # produk_setelah_diskon | order_amount
    pic_user_id: Optional[str] = None           # PIC toko — boleh diisi sejak pembuatan

class PlatformAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    username: Optional[str] = None
    group: Optional[str] = None
    status: Optional[str] = None
    has_api_integration: Optional[bool] = None
    pic_user_id: Optional[str] = None
    coa_revenue_code: Optional[str] = None
    coa_cash_code: Optional[str] = None
    coa_receivable_code: Optional[str] = None
    platform_warehouse_name: Optional[str] = None
    platform_shop_id: Optional[str] = None
    revenue_basis: Optional[str] = None
    needs_owner_review: Optional[bool] = None   # BD-5: ditutup setelah owner mengoreksi

class SalesDataEntry(BaseModel):
    account_id: str
    date: str
    revenue_type: str  # 'total' or 'live'
    revenue: float = 0
    orders: int = 0
    aov: Optional[float] = None
    gmv: Optional[float] = None
    conversion_rate: Optional[float] = Field(default=None, ge=0)
    fulfillment_rate: Optional[float] = Field(default=None, ge=0)
    cancellation_rate: Optional[float] = None
    return_rate: Optional[float] = Field(default=None, ge=0)
    late_shipment_rate: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[float] = None
    response_rate: Optional[float] = Field(default=None, ge=0)
    response_time_hours: Optional[float] = None
    viewers: Optional[float] = None
    avg_viewers: Optional[float] = None
    likes: Optional[float] = None
    shares: Optional[float] = None
    comments: Optional[float] = None
    new_followers: Optional[float] = None
    live_sessions: Optional[float] = None
    # F2 — wajib diisi bila SPV MENGGANTI angka turunan (?override=true)
    override_reason: Optional[str] = None

class TaskCreate(BaseModel):
    account_id: str
    task_type: str
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"
    assigned_to: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    completed_at: Optional[str] = None

class TaskCompleteAction(BaseModel):
    action_notes: Optional[str] = None

class TaskTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    task_type: str
    priority: str = "medium"
    duration_days: int = 7
    is_active: bool = True

class RecurrenceConfig(BaseModel):
    frequency: str
    interval: int = 1


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC & TASK HELPERS
# (Re-extracted from original marketing.py — Session #11.20 recovery)
# ═══════════════════════════════════════════════════════════════════════════════

# ── SKOR SEHAT AKUN: SKALA 1–5 (keputusan owner 2026-08-12) ──────────────────
# Skor internal tetap 0–100 (rumus lama, 41 pembaca memakainya), tetapi yang
# DILIHAT staf adalah 1–5 + label — lebih mudah dipakai dalam rapat harian.
HEALTH_GRADE_BANDS = (
    (85, 5, "Sangat Sehat"),
    (70, 4, "Sehat"),
    (55, 3, "Cukup"),
    (40, 2, "Perlu Perhatian"),
    (0,  1, "Kritis"),
)
HEALTH_NO_DATA_LABEL = "Belum ada data"


def health_grade_of(score):
    """0–100 → (grade 1–5, label). `None` ⇒ (None, 'Belum ada data')."""
    if score is None:
        return None, HEALTH_NO_DATA_LABEL
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None, HEALTH_NO_DATA_LABEL
    for minimum, grade, label in HEALTH_GRADE_BANDS:
        if s >= minimum:
            return grade, label
    return 1, "Kritis"


def _is_pic_role(user) -> bool:
    """
    Check if user has PIC Marketing-level role for approval workflow.
    Allowed roles: admin, owner, superadmin, manager_* (manager_marketing, manager_keuangan, dll), pic_marketing, pic_toko.
    """
    role = (user.get("role") or "").lower()
    if role in {"admin", "owner", "superadmin"}:
        return True
    if role.startswith("manager_") or role.startswith("manager-"):
        return True
    if role in {"pic_marketing", "pic_toko"}:
        return True
    return False


def _generate_task_code():
    """Generate unique task code: TSK-YYYYMMDD-XXXX"""
    now = _now()
    date_str = now.strftime("%Y%m%d")
    random_suffix = str(uuid.uuid4())[:8].upper()
    return f"TSK-{date_str}-{random_suffix}"


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH SCORE CALCULATION
# (Re-extracted from original marketing.py — Session #11.20 recovery)
# ═══════════════════════════════════════════════════════════════════════════════

async def _recalculate_health_score(db, account_id: str):
    """
    Calculate health score untuk account berdasarkan data 30 hari terakhir.

    Health Score = (
      Sales Performance (30%) +
      Fulfillment Quality (25%) +
      Customer Satisfaction (25%) +
      Engagement (10%) +
      Compliance (10%)
    ) / 5 × 100

    Score range: 0-100 → dipetakan ke **SKALA 1–5** (keputusan owner 2026-08-12):
      5 Sangat Sehat (≥85) · 4 Sehat (70–84) · 3 Cukup (55–69) ·
      2 Perlu Perhatian (40–54) · 1 Kritis (<40)
    Toko tanpa data 30 hari terakhir = **"Belum ada data"** (bukan 1) — memberi
    nilai 1 pada toko yang datanya belum masuk sama dengan menuduh tanpa bukti.
    Rincian per pilar disimpan (`health_breakdown`) supaya layar bisa menjawab
    "kenapa skornya segitu" tanpa menghitung ulang di browser.
    """
    date_to = _now().strftime("%Y-%m-%d")
    date_from = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")

    sales_data = await db.marketing_sales_data.find({
        "account_id": account_id,
        "date": {"$gte": date_from, "$lte": date_to}
    }, {"_id": 0}).to_list(500)

    sales_data = [s for s in sales_data if s.get("revenue_type") in ("total", "live")]

    if not sales_data:
        await db.marketing_platform_accounts.update_one(
            {"id": account_id},
            {"$set": {"health_score": None, "health_grade": None,
                      "health_label": HEALTH_NO_DATA_LABEL, "health_breakdown": {},
                      "health_days_with_data": 0, "health_updated_at": _now(),
                      "updated_at": _now()}}
        )
        return None

    # F0.3 (2026-08-12) — semua pembacaan grup lewat `core.marketing_sales_shape`
    # supaya dokumen berbentuk RATA (hasil impor sebelum F0.2) memberi skor yang
    # SAMA dengan entri manual. Sebelum ini: 1 baris Rp 12.500.000 lewat impor
    # menghasilkan skor 15, lewat entri manual 89 — angka yang sama, dua skor.
    # 1. Sales Performance (30 points)
    total_revenue = sum(_shape.read_metrics(s).get("revenue", 0)
                        for s in sales_data if s.get("revenue_type") == "total")
    total_orders = sum(_shape.read_metrics(s).get("orders", 0)
                       for s in sales_data if s.get("revenue_type") == "total")
    avg_conversion = (sum(_shape.to_fraction(_shape.read_metrics(s).get("conversion_rate", 0))
                          for s in sales_data)
                      / len(sales_data)) if sales_data else 0

    sales_score = 0
    if total_revenue > 0:
        sales_score += 15
    if total_orders > 100:
        sales_score += 10
    if avg_conversion > 0.02:
        sales_score += 5

    # 2. Fulfillment Quality (25 points)
    # F0.3 — rumus di bawah butuh FRAKSI 0–1, sedangkan satuan kanonik dokumen
    # adalah PERSEN 0–100 (lihat core/marketing_sales_shape.PCT_FIELDS).
    # `to_fraction()` menjembatani keduanya dalam satu tempat; tanpa ini, data yang
    # sama memberi skor 79 (jalur manual) vs 100 (jalur impor).
    _fr = _shape.to_fraction
    fulfillment_rows = [_shape.read_group(s, "fulfillment") for s in sales_data]
    fulfillment_data = [f for f in fulfillment_rows if f]
    if fulfillment_data:
        avg_fulfillment = sum(_fr(f.get("fulfillment_rate", 0)) for f in fulfillment_data) / len(fulfillment_data)
        avg_cancellation = sum(_fr(f.get("cancellation_rate", 0)) for f in fulfillment_data) / len(fulfillment_data)
        avg_return = sum(_fr(f.get("return_rate", 0)) for f in fulfillment_data) / len(fulfillment_data)
        avg_late = sum(_fr(f.get("late_shipment_rate", 0)) for f in fulfillment_data) / len(fulfillment_data)
        fulfillment_score = (avg_fulfillment * 10) + max(0, (1 - avg_cancellation) * 5) + max(0, (1 - avg_return) * 5) + max(0, (1 - avg_late) * 5)
    else:
        fulfillment_score = 0

    # 3. Customer Satisfaction (25 points)
    satisfaction_rows = [_shape.read_group(s, "customer_satisfaction") for s in sales_data]
    satisfaction_data = [c for c in satisfaction_rows if c]
    if satisfaction_data:
        avg_rating = sum(c.get("rating", 0) for c in satisfaction_data) / len(satisfaction_data)
        avg_response_rate = sum(_fr(c.get("response_rate", 0)) for c in satisfaction_data) / len(satisfaction_data)
        avg_response_time = sum(c.get("response_time_hours", 0) for c in satisfaction_data) / len(satisfaction_data)
        rating_score = (avg_rating / 5) * 15
        response_score = avg_response_rate * 5
        time_score = max(0, 5 - (avg_response_time / 5))
        satisfaction_score = rating_score + response_score + time_score
    else:
        satisfaction_score = 0

    # 4. Engagement (10 points)
    live_data = [_shape.read_group(s, "live_metrics") for s in sales_data
                 if s.get("revenue_type") == "live"]
    live_data = [lm for lm in live_data if lm]
    if live_data:
        total_viewers = sum(lm.get("viewers", 0) for lm in live_data)
        total_likes = sum(lm.get("likes", 0) for lm in live_data)
        total_shares = sum(lm.get("shares", 0) for lm in live_data)
        engagement_score = 0
        if total_viewers > 1000:
            engagement_score += 5
        if total_likes > 500:
            engagement_score += 3
        if total_shares > 50:
            engagement_score += 2
    else:
        engagement_score = 5

    # 5. Compliance (10 points)
    compliance_score = 10 if len(sales_data) >= 7 else 5

    total_score = sales_score + fulfillment_score + satisfaction_score + engagement_score + compliance_score
    health_score = min(100, max(0, round(total_score)))
    grade, label = health_grade_of(health_score)

    # Rincian "kenapa skornya segitu" — dipakai layar (tanpa hitung ulang di browser).
    breakdown = {
        "sales": {"label": "Penjualan", "score": round(sales_score, 1), "max": 30},
        "fulfillment": {"label": "Pemenuhan Pesanan",
                        "score": round(fulfillment_score, 1), "max": 25},
        "satisfaction": {"label": "Kepuasan Pembeli",
                         "score": round(satisfaction_score, 1), "max": 25},
        "engagement": {"label": "Keterlibatan (Live/Konten)",
                       "score": round(engagement_score, 1), "max": 10},
        "compliance": {"label": "Kelengkapan Data",
                       "score": round(compliance_score, 1), "max": 10},
    }

    await db.marketing_platform_accounts.update_one(
        {"id": account_id},
        {"$set": {"health_score": health_score,
                  "health_grade": grade,
                  "health_label": label,
                  "health_breakdown": breakdown,
                  "health_days_with_data": len({s.get("date") for s in sales_data}),
                  "health_updated_at": _now(),
                  "updated_at": _now()}}
    )

    return health_score
