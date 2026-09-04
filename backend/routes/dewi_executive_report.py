"""Executive Report Hub — Phase 3 P1.

Consolidated cross-module KPI dashboard for management.

Endpoints:
  GET  /api/reports/executive/summary          — full executive snapshot
  GET  /api/reports/executive/kpi-comparison   — month-on-month KPI comparison
  GET  /api/reports/executive/finance-snapshot — finance KPIs (AR, revenue, cash)
  GET  /api/reports/executive/production-snapshot — production KPIs
  GET  /api/reports/executive/hr-snapshot      — HR KPIs
  GET  /api/reports/executive/marketing-snapshot — marketing KPIs
  GET  /api/reports/executive/trend            — multi-KPI trend (last N months)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request

from auth import require_auth
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports/executive", tags=["executive-report"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_range(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1).isoformat()
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end.isoformat()


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _delta_pct(curr: float, prev: float) -> Optional[float]:
    if not prev:
        return None
    return round((curr - prev) / prev * 100, 1)


# ---------------------------------------------------------------------------
# Finance aggregations
# ---------------------------------------------------------------------------
async def _finance_kpis(db, year: int, month: int) -> dict:
    start, end = _month_range(year, month)

    # Revenue (finalized invoices) — RC-02: SSOT rahaza_ar_invoices (field: total/balance/issue_date)
    rev_pipeline = [
        {"$match": {
            "issue_date": {"$gte": start, "$lte": end},
            "status": {"$in": ["paid", "partial", "sent", "overdue"]},
        }},
        {"$group": {"_id": None,
                    "total_revenue": {"$sum": {"$ifNull": ["$total", 0]}},
                    "total_paid": {"$sum": {"$subtract": [{"$ifNull": ["$total", 0]}, {"$ifNull": ["$balance", 0]}]}},
                    "invoice_count": {"$sum": 1}}},
    ]
    rev_rows = await db.rahaza_ar_invoices.aggregate(rev_pipeline).to_list(1)
    rev_data = rev_rows[0] if rev_rows else {}

    # Expenses — RC-02/W-D: SSOT rahaza_journal_lines (flat; account_type EXPENSE/COGS, sum debit)
    exp_pipeline = [
        {"$match": {"date": {"$gte": start, "$lte": end},
                    "account_type": {"$in": ["EXPENSE", "COGS"]}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$debit", 0]}}}},
    ]
    exp_rows = await db.rahaza_journal_lines.aggregate(exp_pipeline).to_list(1)
    total_expenses = exp_rows[0]["total"] if exp_rows else 0

    # AR overdue — SSOT rahaza_ar_invoices: belum lunas & due_date lewat
    today = date.today().isoformat()
    ar_overdue_pipeline = [
        {"$match": {"status": {"$in": ["sent", "partial", "overdue"]}, "due_date": {"$lte": today}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$balance", 0]}}, "count": {"$sum": 1}}},
    ]
    ar_rows = await db.rahaza_ar_invoices.aggregate(ar_overdue_pipeline).to_list(1)
    ar_data = ar_rows[0] if ar_rows else {}

    revenue = float(rev_data.get("total_revenue") or 0)
    net_income = revenue - total_expenses

    return {
        "revenue_rp": revenue,
        "paid_revenue_rp": float(rev_data.get("total_paid") or 0),
        "invoice_count": int(rev_data.get("invoice_count") or 0),
        "total_expenses_rp": total_expenses,
        "net_income_rp": net_income,
        "profit_margin_pct": round(net_income / max(revenue, 1) * 100, 1),
        "ar_overdue_rp": float(ar_data.get("total") or 0),
        "ar_overdue_count": int(ar_data.get("count") or 0),
    }


# ---------------------------------------------------------------------------
# Production aggregations
# ---------------------------------------------------------------------------
async def _production_kpis(db, year: int, month: int) -> dict:
    start, end = _month_range(year, month)
    wo_pipeline = [
        {"$match": {"start_date": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_qty": {"$sum": {"$ifNull": ["$qty", 0]}},
            "total_completed": {"$sum": {"$ifNull": ["$completed_qty", 0]}},
        }},
    ]
    # RC-02: SSOT rahaza_work_orders (field: qty/completed_qty/start_date)
    wo_rows = await db.rahaza_work_orders.aggregate(wo_pipeline).to_list(20)
    wo_by_status: dict = {}
    for r in wo_rows:
        wo_by_status[r["_id"] or "unknown"] = {"count": r["count"], "qty": r["total_qty"], "completed": r["total_completed"]}

    total_wo = sum(v["count"] for v in wo_by_status.values())
    completed_wo = wo_by_status.get("completed", {}).get("count", 0)
    active_wo = sum(v["count"] for k, v in wo_by_status.items() if k in ("in_progress", "pending", "released", "planned"))
    total_qty = sum(v["qty"] for v in wo_by_status.values())
    total_completed = sum(v["completed"] for v in wo_by_status.values())

    # CMT/Maklon orders — RC-02: SSOT dewi_maklon_pos (dewi_cmt_orders = phantom tanpa writer)
    cmt_count = await db.dewi_maklon_pos.count_documents(
        {"po_date": {"$gte": start, "$lte": end}}
    )

    # QC defect rate — RC-02: SSOT rahaza_qc_events (field: checked_qty/fail_qty, anchor created_at)
    qc_pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end + "T23:59:59+00:00"}}},
        {"$group": {
            "_id": None,
            "total_inspected": {"$sum": {"$ifNull": ["$checked_qty", 0]}},
            "total_defects": {"$sum": {"$ifNull": ["$fail_qty", 0]}},
        }},
    ]
    qc_rows = await db.rahaza_qc_events.aggregate(qc_pipeline).to_list(1)
    qc_data = qc_rows[0] if qc_rows else {}
    total_inspected = float(qc_data.get("total_inspected") or 0)
    total_defects = float(qc_data.get("total_defects") or 0)
    defect_rate = round(total_defects / max(total_inspected, 1) * 100, 2)

    return {
        "total_wo": total_wo,
        "completed_wo": completed_wo,
        "active_wo": active_wo,
        "completion_rate_pct": round(completed_wo / max(total_wo, 1) * 100, 1),
        "total_qty_ordered": total_qty,
        "total_qty_completed": total_completed,
        "fulfillment_rate_pct": round(total_completed / max(total_qty, 1) * 100, 1),
        "cmt_orders": cmt_count,
        "defect_rate_pct": defect_rate,
    }


# ---------------------------------------------------------------------------
# HR aggregations
# ---------------------------------------------------------------------------
async def _hr_kpis(db, year: int, month: int) -> dict:
    start, end = _month_range(year, month)

    total_active = await db.rahaza_employees.count_documents({"employment_status": "active"})

    # Attendance rate — RC-01: SSOT live rahaza_attendance_events (status hadir/izin/sakit;
    # 'present' ikut dihitung utk kompatibilitas seed demo)
    att_pipeline = [
        {"$match": {"date": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    att_rows = await db.rahaza_attendance_events.aggregate(att_pipeline).to_list(20)
    att_by_status: dict = {s["_id"]: s["count"] for s in att_rows}
    present = sum(v for k, v in att_by_status.items() if k in ("present", "hadir", "H"))
    absent = att_by_status.get("absent", 0) + att_by_status.get("alpha", 0)
    total_att = sum(att_by_status.values())
    attendance_rate = round(present / max(total_att, 1) * 100, 1)

    # Overtime hours — RC-01: SSOT rahaza_overtime_requests (field hours, status approved)
    ot_pipeline = [
        {"$match": {"date": {"$gte": start, "$lte": end}, "status": "approved"}},
        {"$group": {"_id": None, "total_hours": {"$sum": {"$ifNull": ["$hours", 0]}}}},
    ]
    ot_rows = await db.rahaza_overtime_requests.aggregate(ot_pipeline).to_list(1)
    ot_hours = ot_rows[0]["total_hours"] if ot_rows else 0

    # New hires this month
    new_hires = await db.rahaza_employees.count_documents(
        {"join_date": {"$gte": start, "$lte": end}}
    )

    # Payroll total (finalized runs this month)
    payroll_pipeline = [
        {"$match": {"status": "finalized", "created_at": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total_net_pay", 0]}}}},
    ]
    pr_rows = await db.rahaza_payroll_runs.aggregate(payroll_pipeline).to_list(1)
    payroll_total = pr_rows[0]["total"] if pr_rows else 0

    return {
        "total_active_employees": total_active,
        "new_hires": new_hires,
        "attendance_rate_pct": attendance_rate,
        "absent_count": absent,
        "overtime_hours": round(float(ot_hours), 1),
        "payroll_total_rp": payroll_total,
    }


# ---------------------------------------------------------------------------
# Marketing aggregations
# ---------------------------------------------------------------------------
async def _marketing_kpis(db, year: int, month: int) -> dict:
    start, end = _month_range(year, month)

    # Live sessions — RC-02: field SSOT = gmv/total_orders; session_date string "YYYY-MM-DD"
    live_pipeline = [
        {"$match": {"session_date": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": None,
            "total_sessions": {"$sum": 1},
            "total_revenue": {"$sum": {"$ifNull": ["$gmv", 0]}},
            "total_orders": {"$sum": {"$ifNull": ["$total_orders", 0]}},
        }},
    ]
    live_rows = await db.marketing_live_sessions.aggregate(live_pipeline).to_list(1)
    live_data = live_rows[0] if live_rows else {}

    # Webhook orders (from marketplace)
    webhook_orders = await db.marketing_orders.count_documents(
        {"created_at": {"$gte": start, "$lte": end}, "source": "webhook"}
    )

    # ── F10 (2026-08-13) — METRIK MATI DIGANTI SUMBER YANG BENAR ─────────────
    # Sebelumnya di sini ada `db.marketing_kol_campaigns.count_documents(...)`
    # yang hasilnya bahkan TIDAK pernah dipakai. Koleksi itu tidak pernah ditulis
    # oleh satu pun jalur aplikasi — jadi metrik "kampanye KOL" adalah metrik mati:
    # selalu 0, dan pembaca laporan menyimpulkan "bulan ini tidak ada kampanye".
    # Sumber yang benar untuk pekerjaan kreator adalah kalender konten (F7).
    # `start`/`end` di modul ini adalah string "YYYY-MM-DD" (lihat `_month_range`),
    # sama bentuknya dengan `marketing_content_calendar.date` — jadi bisa dibandingkan
    # langsung tanpa konversi (dan tanpa jebakan zona waktu).
    posted_q = {"status": "posted", "date": {"$gte": start, "$lte": end}}
    content_posted = await db.marketing_content_calendar.count_documents(posted_q)
    creators_rows = await db.marketing_content_calendar.distinct("creator_id", posted_q)
    content_gmv = 0.0
    async for c in db.marketing_content_calendar.find(
            {**posted_q, "kpi.gmv": {"$gt": 0}}, {"_id": 0, "kpi": 1}):
        content_gmv += float((c.get("kpi") or {}).get("gmv") or 0)

    return {
        "live_sessions": int(live_data.get("total_sessions") or 0),
        "live_revenue_rp": float(live_data.get("total_revenue") or 0),
        "live_orders": int(live_data.get("total_orders") or 0),
        "marketplace_orders_via_webhook": webhook_orders,
        # pekerjaan kreator — menggantikan metrik mati `marketing_kol_campaigns`
        "content_posted": content_posted,
        "active_creators": len([c for c in creators_rows if c]),
        # GMV KPI konten (angka PLATFORM). JANGAN dijumlah dengan omzet pesanan —
        # itu menghitung satu penjualan dua kali (aturan yang sama seperti F7.4).
        "content_gmv_kpi_rp": round(content_gmv, 2),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/summary")
async def executive_summary(
    request: Request,
    year: int = Query(default=None, ge=1970, le=2999),
    month: int = Query(default=None, ge=1, le=12),
):
    """Full cross-module executive snapshot for given year/month (default: current month)."""
    await require_auth(request)
    db = get_db()
    now = _now()
    y = year or now.year
    m = month or now.month

    prev_y, prev_m = _prev_month(y, m)
    start, end = _month_range(y, m)

    # Parallel fetch all domains
    import asyncio
    finance, production, hr = await asyncio.gather(
        _finance_kpis(db, y, m),
        _production_kpis(db, y, m),
        _hr_kpis(db, y, m),
    )

    # Marketing (sequential to avoid db.list_collection_names issues)
    try:
        marketing = await _marketing_kpis(db, y, m)
    except Exception as e:
        logger.warning("Marketing KPI error: %s", e)
        marketing = {"live_sessions": 0, "live_revenue_rp": 0, "live_orders": 0, "marketplace_orders_via_webhook": 0}

    # Prev period finance for delta
    try:
        prev_finance = await _finance_kpis(db, prev_y, prev_m)
    except Exception:
        prev_finance = {"revenue_rp": 0}

    return {
        "ok": True,
        "period": {"year": y, "month": m, "label": f"{y}-{m:02d}", "range": {"from": start, "to": end}},
        "finance": {
            **finance,
            "revenue_delta_vs_prev_pct": _delta_pct(finance["revenue_rp"], prev_finance["revenue_rp"]),
        },
        "production": production,
        "hr": hr,
        "marketing": marketing,
        "generated_at": now.isoformat(),
    }


@router.get("/ai-narrative")
async def executive_ai_narrative(
    request: Request,
    year: int = Query(default=None, ge=1970, le=2999),
    month: int = Query(default=None, ge=1, le=12),
    refresh: bool = Query(default=False),
):
    """WS-B (a) — AI-generated executive narrative + strategic recommendations.

    Reuses the same cross-module KPI data as /summary, then asks the central AI
    wrapper (tier 'executive' = Opus) to produce a concise management report.
    Cached 1h per period (bypass with refresh=true).
    """
    await require_auth(request)
    db = get_db()
    now = _now()
    y = year or now.year
    m = month or now.month
    prev_y, prev_m = _prev_month(y, m)

    import asyncio
    import json as _json
    finance, production, hr = await asyncio.gather(
        _finance_kpis(db, y, m),
        _production_kpis(db, y, m),
        _hr_kpis(db, y, m),
    )
    try:
        marketing = await _marketing_kpis(db, y, m)
    except Exception:
        marketing = {}
    try:
        prev_finance = await _finance_kpis(db, prev_y, prev_m)
    except Exception:
        prev_finance = {"revenue_rp": 0}

    metrics = {
        "periode": f"{y}-{m:02d}",
        "keuangan": {
            **finance,
            "revenue_delta_vs_prev_pct": _delta_pct(finance.get("revenue_rp", 0), prev_finance.get("revenue_rp", 0)),
        },
        "produksi": production,
        "sdm": hr,
        "marketing": marketing,
    }

    system = (
        "Anda adalah analis bisnis eksekutif untuk CV. Dewi Aditya, sebuah perusahaan "
        "garment dengan dua lini: produksi Internal dan jasa Maklon (CMT). "
        "Berdasarkan data KPI lintas divisi (JSON) untuk periode berjalan, tulis LAPORAN "
        "EKSEKUTIF ringkas dalam Bahasa Indonesia, format Markdown, dengan struktur PERSIS:\n"
        "## Ringkasan Eksekutif\n(2-3 kalimat kondisi bisnis periode ini)\n"
        "## Sorotan per Divisi\n- **Keuangan**: ...\n- **Produksi**: ...\n- **SDM**: ...\n- **Marketing**: ...\n"
        "(sebutkan angka kunci & bandingkan tren bila ada delta)\n"
        "## Risiko & Perhatian\n(bullet singkat)\n"
        "## Rekomendasi Strategis\n(3-5 bullet actionable, urut prioritas)\n\n"
        "Aturan: tulis nominal dengan format Rupiah Indonesia (mis. Rp 1.500.000). "
        "JANGAN mengarang data di luar yang diberikan; bila nilai 0/kosong, sampaikan apa adanya "
        "dan beri saran perbaikan. Maksimal ~400 kata."
    )

    from services.ai import cached_call_claude

    extra = [f"{y}-{m:02d}"]
    if refresh:
        extra.append(now.isoformat())  # force cache miss for a fresh generation

    try:
        res = await cached_call_claude(
            db,
            system_message=system,
            user_message=_json.dumps(metrics, default=str, ensure_ascii=False),
            cache_namespace="exec_narrative",
            cache_key_extra=extra,
            ttl_seconds=3600,
            session_tag="executive-narrative",
            tier="executive",
        )
    except Exception as e:
        # Surface AI/budget errors gracefully so the KPI dashboard still works.
        from fastapi import HTTPException as _HTTPExc
        if isinstance(e, _HTTPExc):
            raise
        logger.warning("Executive AI narrative failed: %s", e)
        return {
            "ok": False,
            "period": metrics["periode"],
            "narrative": "",
            "error": str(e),
            "generated_at": now.isoformat(),
        }

    return {
        "ok": True,
        "period": metrics["periode"],
        "narrative": res.get("text", ""),
        "cache_hit": res.get("cache_hit", False),
        "generated_at": res.get("generated_at", now.isoformat()),
        "metrics": metrics,
    }


@router.get("/kpi-comparison")
async def kpi_comparison(
    request: Request,
    months: int = Query(6, ge=2, le=24),
):
    """Month-on-month KPI comparison across the last N months."""
    await require_auth(request)
    db = get_db()
    now = _now()
    results = []

    for i in range(months - 1, -1, -1):
        target = now - timedelta(days=i * 30)
        y, m = target.year, target.month
        try:
            finance = await _finance_kpis(db, y, m)
            production = await _production_kpis(db, y, m)
        except Exception as e:
            logger.warning("KPI comparison error for %d-%02d: %s", y, m, e)
            continue
        results.append({
            "period": f"{y}-{m:02d}",
            "revenue_rp": finance["revenue_rp"],
            "net_income_rp": finance["net_income_rp"],
            "wo_completed": production["completed_wo"],
            "defect_rate_pct": production["defect_rate_pct"],
            "ar_overdue_rp": finance["ar_overdue_rp"],
        })

    return {"ok": True, "months": months, "data": results}


@router.get("/finance-snapshot")
async def finance_snapshot(
    request: Request,
    year: Optional[int] = Query(None, ge=1970, le=2999),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    await require_auth(request)
    db = get_db()
    now = _now()
    y, m = (year or now.year), (month or now.month)
    data = await _finance_kpis(db, y, m)
    prev_y, prev_m = _prev_month(y, m)
    prev = await _finance_kpis(db, prev_y, prev_m)
    return {
        "ok": True,
        "period": f"{y}-{m:02d}",
        "current": data,
        "previous": prev,
        "deltas": {
            "revenue_pct": _delta_pct(data["revenue_rp"], prev["revenue_rp"]),
            "net_income_pct": _delta_pct(data["net_income_rp"], prev["net_income_rp"]),
            "ar_overdue_pct": _delta_pct(data["ar_overdue_rp"], prev["ar_overdue_rp"]),
        },
    }


@router.get("/production-snapshot")
async def production_snapshot(
    request: Request,
    year: Optional[int] = Query(None, ge=1970, le=2999),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    await require_auth(request)
    db = get_db()
    now = _now()
    y, m = (year or now.year), (month or now.month)
    data = await _production_kpis(db, y, m)
    prev_y, prev_m = _prev_month(y, m)
    prev = await _production_kpis(db, prev_y, prev_m)
    return {
        "ok": True,
        "period": f"{y}-{m:02d}",
        "current": data,
        "previous": prev,
        "deltas": {
            "completion_rate_pct": _delta_pct(data["completion_rate_pct"], prev["completion_rate_pct"]),
            "defect_rate_pct": _delta_pct(data["defect_rate_pct"], prev["defect_rate_pct"]),
        },
    }


@router.get("/hr-snapshot")
async def hr_snapshot(
    request: Request,
    year: Optional[int] = Query(None, ge=1970, le=2999),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    await require_auth(request)
    db = get_db()
    now = _now()
    y, m = (year or now.year), (month or now.month)
    data = await _hr_kpis(db, y, m)
    return {"ok": True, "period": f"{y}-{m:02d}", "data": data}


@router.get("/marketing-snapshot")
async def marketing_snapshot(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
):
    await require_auth(request)
    db = get_db()
    now = _now()
    y, m = (year or now.year), (month or now.month)
    try:
        data = await _marketing_kpis(db, y, m)
    except Exception as e:
        data = {"error": str(e)}
    return {"ok": True, "period": f"{y}-{m:02d}", "data": data}


@router.get("/trend")
async def executive_trend(
    request: Request,
    months: int = Query(6, ge=2, le=12),
):
    """Multi-KPI revenue + production + HR trend for last N months."""
    await require_auth(request)
    db = get_db()
    now = _now()
    data = []
    for i in range(months - 1, -1, -1):
        target = now - timedelta(days=i * 30)
        y, m = target.year, target.month
        label = f"{y}-{m:02d}"
        try:
            fin = await _finance_kpis(db, y, m)
            prod = await _production_kpis(db, y, m)
            hr = await _hr_kpis(db, y, m)
        except Exception:
            continue
        data.append({
            "period": label,
            "revenue_rp": fin["revenue_rp"],
            "net_income_rp": fin["net_income_rp"],
            "ar_overdue_rp": fin["ar_overdue_rp"],
            "wo_completed": prod["completed_wo"],
            "defect_rate_pct": prod["defect_rate_pct"],
            "attendance_rate_pct": hr["attendance_rate_pct"],
            "payroll_total_rp": hr["payroll_total_rp"],
        })
    return {"ok": True, "months": months, "data": data}
