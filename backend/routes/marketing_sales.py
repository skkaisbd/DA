# ruff: noqa: F401
"""
marketing_sales.py — Sales Data Management
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: POST /sales-data, GET /accounts/{account_id}/sales
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, SalesDataEntry, _recalculate_health_score, _is_pic_role
from core import marketing_sales_shape as _shape
from core import marketing_cycle as _cycle

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Sales'])

@router.post("/sales-data")
async def create_sales_data(
    data: SalesDataEntry,
    request: Request,
    override: bool = Query(False, description="SPV: ganti angka turunan (wajib beralasan)"),
    override_reason: Optional[str] = Query(None, description="alasan penggantian angka"),
):
    """
    Entri rekap harian per toko.

    F2 (2026-08-12) — **angka omzet & jumlah pesanan tidak lagi diketik** untuk
    tanggal yang sudah punya pesanan hasil impor: dokumennya `source='orders_auto'`
    dan `locked_source=true` ⇒ permintaan manual ditolak **409** dengan jalan keluar
    yang jelas. SPV/Manager Marketing boleh MENGGANTI angka lewat `?override=true`
    **dengan alasan** — hasilnya `source='manual_override'` + jejak siapa/kapan,
    dan rollup otomatis tidak akan menimpanya (kecuali "Hitung Ulang (paksa)").
    """
    await require_auth(request)
    db = get_db()

    # Validate account exists
    account = await db.marketing_platform_accounts.find_one({"id": data.account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Akun toko tidak ditemukan")

    # Validate revenue_type
    if data.revenue_type not in ["total", "live"]:
        raise HTTPException(400, "revenue_type harus 'total' atau 'live'")

    # F5.3 — bulan yang sudah DITUTUP tidak bisa lagi menerima rekap baru maupun
    # override (HTTP 423). Kunci periode adalah satu-satunya cara membuat angka
    # yang sudah dirapatkan berhenti berubah diam-diam.
    await _cycle.assert_period_open(db, data.account_id, data.date,
                                    action='menyimpan rekap harian')

    # Check duplicate entry (same account + date + revenue_type)
    existing = await db.marketing_sales_data.find_one({
        "account_id": data.account_id,
        "date": data.date,
        "revenue_type": data.revenue_type
    }, {"_id": 0})

    user = _get_user(request)
    reason = (override_reason or getattr(data, "override_reason", None) or "").strip()

    if existing:
        derived = _shape.is_derived(existing)
        if not override:
            if derived:
                raise HTTPException(409,
                    f"Angka omzet & jumlah pesanan {data.date} DITURUNKAN dari pesanan toko "
                    f"ini (sumber: {existing.get('source')}). Untuk mengubahnya: perbaiki "
                    f"pesanannya di menu Pesanan/Impor, atau minta SPV memakai tombol "
                    f"'Ganti Angka (Override)' dan menuliskan alasannya.")
            raise HTTPException(400, f"Rekap {data.date} ({data.revenue_type}) sudah ada "
                                     f"untuk toko ini — buka barisnya untuk mengubah")
        # ── jalur OVERRIDE (SPV) ─────────────────────────────────────────────
        if not _is_pic_role(user):
            raise HTTPException(403, "Hanya SPV/Manager Marketing (atau admin) yang boleh "
                                     "mengganti angka turunan")
        if not reason:
            raise HTTPException(400, "Alasan wajib diisi saat mengganti angka turunan — "
                                     "ini yang membuat perubahan bisa dipertanggungjawabkan")
        doc = _shape.build_daily_doc(
            account=account,
            date=data.date,
            revenue_type=data.revenue_type,
            flat=data.dict(exclude={"account_id", "date", "revenue_type", "override_reason"}),
            source=_shape.SOURCE_MANUAL_OVERRIDE,
            extra={
                "override_reason": reason,
                "override_by": user.get("email", "system"),
                "override_at": _now(),
                "previous_source": existing.get("source"),
                "previous_metrics": existing.get("metrics") or {},
                "updated_by": user.get("email", "system"),
            },
        )
        # grup milik sumber lain tidak boleh hilang gara-gara override omzet
        for g in ("funnel", "buyers_mix", "customer_satisfaction",
                  "live_metrics", "content_metrics"):
            if not doc.get(g) and existing.get(g):
                doc[g] = existing[g]
        await db.marketing_sales_data.update_one({"id": existing["id"]}, {"$set": doc})
        await _recalculate_health_score(db, data.account_id)
        await log_activity(
            user.get("id", "system"),
            user.get("name") or user.get("email", "system"),
            "override", "marketing_sales_data",
            f"OVERRIDE rekap harian {account['account_name']} {data.date} "
            f"({data.revenue_type}) — alasan: {reason}")
        saved = await db.marketing_sales_data.find_one({"id": existing["id"]}, {"_id": 0})
        return serialize_doc({"message": "Angka diganti (override) dan alasannya dicatat",
                              "entry": saved})

    # F0.2 (2026-08-12) — bentuk dokumen dibuat oleh SATU pembuat kanonik
    # (`core.marketing_sales_shape`). Dulu dict-nya disusun di sini, dan pintu
    # impor menyusun bentuk yang BERBEDA ⇒ satu angka, empat jawaban di layar (D01).
    sales_entry = _shape.build_daily_doc(
        account=account,
        date=data.date,
        revenue_type=data.revenue_type,
        flat=data.dict(exclude={"account_id", "date", "revenue_type", "override_reason"}),
        source=_shape.SOURCE_MANUAL,
        extra={
            "id": _uid(),
            "import_history_id": None,   # entri manual, bukan hasil impor
            "created_at": _now(),
            "created_by": _get_user(request).get("email", "system"),
        },
    )

    await db.marketing_sales_data.insert_one(sales_entry)
    
    # Update account health score after new data
    await _recalculate_health_score(db, data.account_id)
    
    await log_activity(
        (_get_user(request)).get("id", "system"),
        (_get_user(request)).get("name") or (_get_user(request)).get("email", "system"),
        "create",
        "marketing_sales_data",
        f"Added sales data: {account['account_name']} - {data.date} ({data.revenue_type})"
    )
    
    return serialize_doc({"message": "Sales data created", "entry": sales_entry})


@router.post("/sales/recompute")
async def recompute_daily_from_orders(
    request: Request,
    account_id: str = Query(..., description="toko yang dihitung ulang"),
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (default = date_from)"),
    force: bool = Query(False, description="timpa juga angka hasil override SPV"),
):
    """F2 — hitung ulang rekap harian **dari pesanan** untuk rentang tanggal.

    Dipakai tombol "Hitung Ulang" di layar Input Sales. `force=true` (SPV) juga
    memulihkan tanggal yang sebelumnya di-override manual menjadi angka turunan.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    if not _is_pic_role(user):
        raise HTTPException(403, "Hanya SPV/Manager Marketing (atau admin) yang boleh "
                                 "menghitung ulang rekap harian")
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Akun toko tidak ditemukan")

    from core import marketing_daily_rollup as rollup
    result = await rollup.recompute_range(
        db, account_id, date_from, date_to or date_from,
        force=force, actor=user.get("email", "system"))
    await _recalculate_health_score(db, account_id)
    await log_activity(
        user.get("id", "system"), user.get("name") or user.get("email", "system"),
        "recompute", "marketing_sales_data",
        f"Hitung ulang rekap harian {account['account_name']} "
        f"{date_from}..{date_to or date_from} (paksa={force}): "
        f"{result['upserted']} diperbarui, {result['deleted']} dihapus")
    return serialize_doc({
        "ok": True,
        "account_id": account_id,
        "range": {"from": date_from, "to": date_to or date_from},
        "forced": force,
        **{k: v for k, v in result.items() if k != "details"},
        "details": result.get("details", [])[:60],
        "message": (f"{result['upserted']} tanggal dihitung ulang dari pesanan, "
                    f"{result['deleted']} dihapus (tidak ada pesanan), "
                    f"{result['skipped_override']} dilewati karena di-override SPV"),
    })


@router.get("/accounts/{account_id}/sales")
async def get_account_sales_data(
    account_id: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    revenue_type: Optional[str] = Query(None, description="total | live | all")
):
    """
    Get sales data for an account with date range filter.
    revenue_type='all' returns both total and live data.
    """
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Account not found")
    
    query = {"account_id": account_id}
    
    # Date range filter
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    
    # Revenue type filter
    if revenue_type and revenue_type != "all":
        if revenue_type not in ["total", "live"]:
            raise HTTPException(400, "revenue_type must be 'total', 'live', or 'all'")
        query["revenue_type"] = revenue_type
    
    sales_data = await db.marketing_sales_data.find(query, {"_id": 0}).sort("date", -1).to_list(500)
    
    return serialize_doc(sales_data)



# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7A: MARKETING SALES → AR INVOICE BATCH GENERATION
# ══════════════════════════════════════════════════════════════════════════════

class ARBatchRequest(BaseModel):
    date_from: str = Field(..., description="YYYY-MM-DD")
    date_to: str = Field(..., description="YYYY-MM-DD")
    account_id: Optional[str] = None
    platform: Optional[str] = None
    revenue_type: str = Field(default="total", description="total | live")
    grouping: str = Field(default="daily", description="daily | weekly | monthly | platform")
    customer_id: Optional[str] = None  # Default: generic "Marketplace Customer"
    notes: Optional[str] = ""


@router.post("/sales-data/generate-ar-batch")
async def generate_ar_batch_from_sales(data: ARBatchRequest, request: Request):
    """
    [DINONAKTIFKAN — KEPUTUSAN #1] Jalur otomatis Marketing Sales -> AR Finance
    telah dimatikan. Pendapatan marketplace kini dicatat Finance via Jurnal Manual
    (rahaza_journals). Input sales harian (POST /sales-data) tetap tersedia untuk
    dashboard marketing (analitik) dan TIDAK memicu AR/GL.

    Modul AR Finance (rahaza_finance) & Journal Entry (rahaza_journals) TIDAK
    terpengaruh. Endpoint ini sengaja dipertahankan (bukan dihapus) agar UI lama
    yang masih memanggilnya mendapat pesan jelas, bukan 404, dan TIDAK menulis
    apa pun ke rahaza_ar_invoices / GL.
    """
    # Tetap wajib auth: caller tak berwenang -> 401 (perilaku konsisten).
    await require_auth(request)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "MARKETING_AR_DISABLED",
            "message": (
                "Fitur 'Buat Invoice AR dari Sales Marketing' telah dinonaktifkan "
                "(Keputusan #1). Pendapatan marketplace dicatat oleh Finance melalui "
                "Jurnal Manual (Manual Journal Entry). Input sales harian tetap "
                "tersedia untuk dashboard marketing."
            ),
        },
    )


async def _gen_ar_number(db):
    """Generate AR invoice number with date prefix (RC-5 fix: atomic counter)."""
    from utils.counters import gen_prefixed_number
    today = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    return await gen_prefixed_number(db, "rahaza_ar_invoices", "invoice_number", f"AR-{today}-", 3)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD (Basic for Phase 1)
