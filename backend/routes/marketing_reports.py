"""
Marketing PIC Reports — Laporan Harian & Bulanan
=================================================
Endpoint ringkasan operasional untuk PIC Portal Marketing.

Laporan Harian:
  GET /api/marketing/reports/daily?date=YYYY-MM-DD

Laporan Bulanan:
  GET /api/marketing/reports/monthly?year=YYYY&month=MM

Export PDF:
  GET /api/marketing/reports/monthly/export-pdf?year=YYYY&month=MM
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone, timedelta
import calendar

from database import get_db
from auth import require_auth, serialize_doc
from core import marketing_sales_shape as _shape
# F6 (sesi #9) — layar daftar WAJIB berlingkup toko: staf pemegang satu toko
# tidak boleh melihat omzet/tugas delapan toko lain di laporan harian & bulanan.
from core import marketing_account_scope as _scope

router = APIRouter(prefix="/api/marketing/reports", tags=["marketing-reports"])


def _now(): return datetime.now(timezone.utc)


# ── LAPORAN HARIAN ────────────────────────────────────────────────────────────
@router.get("/daily")
async def daily_report(
    request: Request,
    date: Optional[str] = Query(None, description="YYYY-MM-DD, default: kemarin"),
):
    """
    Laporan harian untuk PIC:
    - Status input sales per akun (apakah sudah diinput untuk tanggal target)
    - Actionable tasks pending (belum dieksekusi)
    - Overdue tasks
    - Ringkasan KPI
    """
    user = await require_auth(request)
    db = get_db()
    now = _now()

    # Target date: kemarin (karena sales input biasanya untuk hari sebelumnya)
    if date:
        target_date = date[:10]
    else:
        target_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # Today for task queries
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Akun aktif YANG BOLEH DILIHAT pemakai ini (F6)
    accounts = await _scope.visible_accounts(db, user, base={"status": "active"})

    accounts_status = []
    total_entered   = 0
    total_missing   = 0

    for acc in accounts:
        acc_id = acc["id"]

        # Cek apakah sales data sudah diinput
        sales = await db.marketing_sales_data.find(
            {"account_id": acc_id, "date": target_date},
            {"_id": 0, "revenue_type": 1, "metrics": 1}
        ).to_list(10)

        total_data = [s for s in sales if s.get("revenue_type") == "total"]
        live_data  = [s for s in sales if s.get("revenue_type") == "live"]

        has_total = len(total_data) > 0
        has_live  = len(live_data) > 0

        m_total = _shape.read_metrics(total_data[0]) if has_total else {}
        rev_total = m_total.get("revenue", 0) if has_total else 0
        ord_total = m_total.get("orders", 0) if has_total else 0

        # Pending actionable tasks untuk akun ini
        pending_tasks = await db.marketing_tasks.find(
            {
                "account_id": acc_id,
                "status":     {"$in": ["to_do", "in_progress"]},
                "action_type": {"$exists": True, "$ne": None},
            },
            {"_id": 0, "id": 1, "title": 1, "action_type": 1, "task_code": 1,
             "priority": 1, "due_date": 1, "related_entity": 1}
        ).sort("priority", 1).limit(5).to_list(5)

        # Overdue tasks
        overdue_count = await db.marketing_tasks.count_documents({
            "account_id": acc_id,
            "status":     {"$in": ["to_do", "in_progress"]},
            "due_date":   {"$lt": now.isoformat()},
        })

        entered = has_total
        if entered:
            total_entered += 1
        else:
            total_missing += 1

        accounts_status.append({
            "account_id":    acc_id,
            "account_name":  acc.get("account_name", ""),
            "account_code":  acc.get("account_code", ""),
            "platform":      acc.get("platform", ""),
            "health_score":  acc.get("health_score"),
            "sales_status": {
                "entered_total": has_total,
                "entered_live":  has_live,
                "revenue":       rev_total,
                "orders":        ord_total,
            },
            "pending_action_tasks": serialize_doc(pending_tasks),
            "overdue_count":        overdue_count,
        })

    # Global task stats (semua akun, hari ini)
    task_done    = await db.marketing_tasks.count_documents({
        "created_at": {"$gte": today_start}, "status": "done"
    })
    task_overdue = await db.marketing_tasks.count_documents({
        "status": {"$in": ["to_do", "in_progress"]},
        "due_date": {"$lt": now.isoformat()},
    })
    task_pending_approval = await db.marketing_tasks.count_documents({
        "status": "pending_approval"
    })

    # Health alerts (akun health < 60)
    critical_accounts = [a for a in accounts_status if a["health_score"] is not None and a["health_score"] < 60]

    return serialize_doc({
        "generated_at":   now.isoformat(),
        "target_date":    target_date,
        "summary": {
            "accounts_total":          len(accounts),
            "accounts_sales_entered":  total_entered,
            "accounts_sales_missing":  total_missing,
            "sales_input_rate":        round(total_entered / len(accounts) * 100, 1) if accounts else 0,
            "tasks_done_today":        task_done,
            "tasks_overdue":           task_overdue,
            "tasks_pending_approval":  task_pending_approval,
            "critical_health_count":   len(critical_accounts),
        },
        "accounts": accounts_status,
    })


# ── LAPORAN BULANAN ───────────────────────────────────────────────────────────
@router.get("/monthly")
async def monthly_report(
    request: Request,
    year:  Optional[int] = Query(None, ge=1970, le=2999),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    """
    Laporan bulanan untuk PIC — target vs actual per akun + statistik operasional.
    Default: bulan & tahun berjalan.
    """
    user = await require_auth(request)
    db  = get_db()
    now = _now()
    y   = year  or now.year
    m   = month or now.month

    month_start = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
    if m == 12:
        month_end = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        month_end = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    date_from  = f"{y:04d}-{m:02d}-01"
    last_day   = calendar.monthrange(y, m)[1]
    date_to    = f"{y:04d}-{m:02d}-{last_day:02d}"
    total_days = last_day

    accounts = await _scope.visible_accounts(db, user, base={"status": "active"})

    result = []
    for acc in accounts:
        acc_id = acc["id"]

        # Target
        tgt = await db.marketing_account_targets.find_one(
            {"account_id": acc_id, "year": y, "month": m}, {"_id": 0}
        )

        # Actual sales per day (total type)
        sales = await db.marketing_sales_data.find(
            {"account_id": acc_id, "date": {"$gte": date_from, "$lte": date_to},
             "revenue_type": "total"},
            # F0.3 — proyeksi TIDAK boleh dibatasi ke `metrics` saja: dokumen lama
            # berbentuk rata menaruh `revenue` di akar, dan proyeksi sempit membuat
            # angkanya hilang tanpa galat.
            {"_id": 0}
        ).sort("date", 1).to_list(500)

        rev_actual  = sum(_shape.read_metrics(s).get("revenue", 0) for s in sales)
        ord_actual  = sum(_shape.read_metrics(s).get("orders", 0) for s in sales)
        sales_days  = len({s["date"] for s in sales})
        input_rate  = round(sales_days / total_days * 100, 1)

        # Daily chart data
        daily_chart = [
            {"date": s["date"], "revenue": _shape.read_metrics(s).get("revenue", 0),
             "orders": _shape.read_metrics(s).get("orders", 0)}
            for s in sales
        ]

        # Task stats
        tasks_all  = await db.marketing_tasks.count_documents({
            "account_id": acc_id,
            "created_at": {"$gte": month_start, "$lt": month_end},
            "status":     {"$ne": "cancelled"},
        })
        tasks_done = await db.marketing_tasks.count_documents({
            "account_id": acc_id,
            "created_at": {"$gte": month_start, "$lt": month_end},
            "status": "done",
        })

        rev_tgt  = tgt["revenue_target"] if tgt else None
        ord_tgt  = tgt["orders_target"]  if tgt else None
        rev_pct  = round(rev_actual / rev_tgt * 100, 1) if rev_tgt and rev_tgt > 0 else None
        ord_pct  = round(ord_actual / ord_tgt * 100, 1) if ord_tgt and ord_tgt > 0 else None

        # Status warna: merah < 70%, kuning 70-89%, hijau >= 90%
        def _status(pct):
            if pct is None:
                return "no_target"
            if pct >= 90:
                return "on_track"
            if pct >= 70:
                return "warning"
            return "behind"

        result.append({
            "account_id":   acc_id,
            "account_name": acc.get("account_name", ""),
            "account_code": acc.get("account_code", ""),
            "platform":     acc.get("platform", ""),
            "health_score": acc.get("health_score"),
            "target": {
                "revenue":      rev_tgt,
                "orders":       ord_tgt,
                "health_score": tgt["health_score_target"] if tgt else None,
            },
            "actual": {
                "revenue":    rev_actual,
                "orders":     ord_actual,
                "sales_days": sales_days,
                "input_rate": input_rate,
            },
            "achievement": {
                "revenue_pct":    rev_pct,
                "orders_pct":     ord_pct,
                "revenue_status": _status(rev_pct),
                "orders_status":  _status(ord_pct),
            },
            "task_stats": {
                "total":           tasks_all,
                "done":            tasks_done,
                "completion_rate": round(tasks_done / tasks_all * 100, 1) if tasks_all > 0 else None,
            },
            "daily_chart": daily_chart,
        })

    # Overall summary
    tot_rev_tgt    = sum(r["target"]["revenue"] or 0  for r in result)
    tot_rev_actual = sum(r["actual"]["revenue"]       for r in result)
    tot_ord_tgt    = sum(r["target"]["orders"]  or 0  for r in result)
    tot_ord_actual = sum(r["actual"]["orders"]        for r in result)
    tot_tasks      = sum(r["task_stats"]["total"]     for r in result)
    tot_done       = sum(r["task_stats"]["done"]      for r in result)
    avg_input      = round(sum(r["actual"]["input_rate"] for r in result) / len(result), 1) if result else 0

    return serialize_doc({
        "period": {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "summary": {
            "total_accounts":     len(accounts),
            "rev_target":         tot_rev_tgt,
            "rev_actual":         tot_rev_actual,
            "rev_pct":            round(tot_rev_actual / tot_rev_tgt * 100, 1) if tot_rev_tgt > 0 else None,
            "ord_target":         tot_ord_tgt,
            "ord_actual":         tot_ord_actual,
            "task_completion":    round(tot_done / tot_tasks * 100, 1) if tot_tasks > 0 else None,
            "avg_sales_input_rate": avg_input,
        },
        "accounts": result,
    })


# ── EXPORT PDF ────────────────────────────────────────────────────────────────
@router.get("/monthly/export-pdf")
async def export_monthly_report_pdf(
    request: Request,
    year:  Optional[int] = Query(None, ge=1970, le=2999),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    """
    Generate dan download PDF Laporan Bulanan Marketing.
    Reuses monthly_report logic, lalu build PDF via ReportLab.
    """
    user = await require_auth(request)
    # Reuse monthly report logic
    await monthly_report.__wrapped__(request, year=year, month=month) \
        if hasattr(monthly_report, '__wrapped__') else None

    # Call the internal function directly
    now = _now()
    y = year  or now.year
    m = month or now.month
    db = get_db()

    month_start = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
    if m == 12:
        month_end = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        month_end = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    date_from = f"{y:04d}-{m:02d}-01"
    last_day  = calendar.monthrange(y, m)[1]
    date_to   = f"{y:04d}-{m:02d}-{last_day:02d}"
    total_days = last_day

    accounts = await _scope.visible_accounts(db, user, base={"status": "active"})
    result = []
    for acc in accounts:
        acc_id = acc["id"]
        tgt = await db.marketing_account_targets.find_one(
            {"account_id": acc_id, "year": y, "month": m}, {"_id": 0}
        )
        sales = await db.marketing_sales_data.find(
            {"account_id": acc_id, "date": {"$gte": date_from, "$lte": date_to}, "revenue_type": "total"},
            {"_id": 0}      # F0.3 — jangan batasi ke `metrics` (dokumen lama = rata)
        ).to_list(500)
        rev_actual  = sum(_shape.read_metrics(s).get("revenue", 0) for s in sales)
        ord_actual  = sum(_shape.read_metrics(s).get("orders", 0) for s in sales)
        sales_days  = len({s["date"] for s in sales})
        input_rate  = round(sales_days / total_days * 100, 1)
        tasks_all   = await db.marketing_tasks.count_documents({
            "account_id": acc_id, "created_at": {"$gte": month_start, "$lt": month_end}, "status": {"$ne": "cancelled"}
        })
        tasks_done  = await db.marketing_tasks.count_documents({
            "account_id": acc_id, "created_at": {"$gte": month_start, "$lt": month_end}, "status": "done"
        })
        rev_tgt = tgt["revenue_target"] if tgt else None
        ord_tgt = tgt["orders_target"]  if tgt else None
        rev_pct = round(rev_actual / rev_tgt * 100, 1) if rev_tgt and rev_tgt > 0 else None
        ord_pct = round(ord_actual / ord_tgt * 100, 1) if ord_tgt and ord_tgt > 0 else None
        def _status(pct):
            if pct is None:
                return "no_target"
            if pct >= 90:
                return "on_track"
            if pct >= 70:
                return "warning"
            return "behind"
        result.append({
            "account_id": acc_id, "account_name": acc.get("account_name",""),
            "account_code": acc.get("account_code",""), "platform": acc.get("platform",""),
            "health_score": acc.get("health_score"),
            "target": {"revenue": rev_tgt, "orders": ord_tgt},
            "actual": {"revenue": rev_actual, "orders": ord_actual, "sales_days": sales_days, "input_rate": input_rate},
            "achievement": {"revenue_pct": rev_pct, "orders_pct": ord_pct, "revenue_status": _status(rev_pct), "orders_status": _status(ord_pct)},
            "task_stats": {"total": tasks_all, "done": tasks_done, "completion_rate": round(tasks_done/tasks_all*100,1) if tasks_all else None},
        })

    tot_rev_tgt    = sum(r["target"]["revenue"] or 0 for r in result)
    tot_rev_actual = sum(r["actual"]["revenue"]      for r in result)
    tot_ord_tgt    = sum(r["target"]["orders"]  or 0 for r in result)
    tot_ord_actual = sum(r["actual"]["orders"]       for r in result)
    tot_tasks      = sum(r["task_stats"]["total"]    for r in result)
    tot_done       = sum(r["task_stats"]["done"]     for r in result)
    avg_input      = round(sum(r["actual"]["input_rate"] for r in result) / len(result), 1) if result else 0

    report_payload = {
        "period": {"year": y, "month": m, "date_from": date_from, "date_to": date_to},
        "summary": {
            "total_accounts": len(accounts),
            "rev_target": tot_rev_tgt, "rev_actual": tot_rev_actual,
            "rev_pct": round(tot_rev_actual / tot_rev_tgt * 100, 1) if tot_rev_tgt > 0 else None,
            "ord_target": tot_ord_tgt, "ord_actual": tot_ord_actual,
            "task_completion": round(tot_done / tot_tasks * 100, 1) if tot_tasks > 0 else None,
            "avg_sales_input_rate": avg_input,
        },
        "accounts": result,
    }

    from utils.monthly_report_pdf import build_monthly_report_pdf
    pdf_bytes = build_monthly_report_pdf(report_payload)

    month_names = ['','Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des']
    filename = f"laporan-marketing-{month_names[m]}-{y}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



# ── MIGRATION: Link seed data ke real platform accounts ─────────────────────
@router.post("/admin/migrate-seed-accounts")
async def migrate_seed_accounts(request: Request):
    """
    Migrasi seed data (complaints/reviews/returns/health) agar terhubung ke
    marketing_platform_accounts nyata.

    Algoritma:
    1. Fetch semua platform accounts aktif
    2. Update complaints/reviews/returns tanpa account_id — assign round-robin ke platform accounts
    3. Clear & re-seed marketing_account_health dengan platform accounts nyata

    Admin only.
    """
    user = await require_auth(request)
    if user.get("role") not in ["admin", "superadmin", "owner"]:
        from fastapi import HTTPException
        raise HTTPException(403, "Admin only")

    db = get_db()

    # Fetch all active platform accounts
    accounts = await db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}
    ).to_list(200)

    if not accounts:
        return serialize_doc({"message": "Tidak ada platform account aktif, buat akun dahulu", "migrated": 0})

    stats = {"complaints": 0, "reviews": 0, "returns": 0, "health_reset": False}

    # Helper: pick account by platform, fallback to first
    def pick_account(platform: str):
        matches = [a for a in accounts if a["platform"] == platform or
                   (platform in ("tiktok", "tiktokshop") and a["platform"] in ("tiktok", "tiktokshop"))]
        return matches[0] if matches else accounts[0]

    # ── Update complaints ──
    async for doc in db.marketing_complaints.find({"account_id": None}, {"_id": 0, "id": 1, "platform": 1}):
        acc = pick_account(doc.get("platform", ""))
        await db.marketing_complaints.update_one(
            {"id": doc["id"]},
            {"$set": {"account_id": acc["id"], "account_name": acc["account_name"]}}
        )
        stats["complaints"] += 1

    # ── Update reviews ──
    async for doc in db.marketing_reviews.find({"account_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "platform": 1}):
        acc = pick_account(doc.get("platform", ""))
        await db.marketing_reviews.update_one(
            {"id": doc["id"]},
            {"$set": {"account_id": acc["id"], "account_name": acc["account_name"]}}
        )
        stats["reviews"] += 1

    # ── Update returns ──
    async for doc in db.marketing_returns.find({"account_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "platform": 1}):
        acc = pick_account(doc.get("platform", ""))
        await db.marketing_returns.update_one(
            {"id": doc["id"]},
            {"$set": {"account_id": acc["id"], "account_name": acc["account_name"]}}
        )
        stats["returns"] += 1

    # ── Reset & re-seed health collection dengan real accounts ──
    # Cek apakah health collection hanya punya dummy data (tanpa account_id FK)
    dummy_count = await db.marketing_account_health.count_documents({"account_id": None})
    total_health = await db.marketing_account_health.count_documents({})
    if dummy_count == total_health and total_health > 0:
        # Semua data adalah dummy — clear dan re-seed
        await db.marketing_account_health.delete_many({})
        from routes.marketing_account_health_routes import seed_health_if_empty
        await seed_health_if_empty()
        stats["health_reset"] = True

    return serialize_doc({
        "message": "Migrasi selesai",
        "stats": stats,
        "accounts_used": [{"code": a.get("account_code", a["id"][:8]), "name": a["account_name"], "platform": a["platform"]} for a in accounts],
    })
