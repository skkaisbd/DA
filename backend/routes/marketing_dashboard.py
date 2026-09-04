# ruff: noqa: F401
"""
marketing_dashboard.py — Dashboard & Analytics
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: GET /dashboard/overview, GET /accounts/{id}/dashboard, POST /accounts/{id}/recalculate-health, GET /dashboard/comparison, POST /seed-sample-data
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity
# F6 (sesi #9) — dashboard gabungan WAJIB berlingkup toko.
from core import marketing_account_scope as _scope
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, _recalculate_health_score
from core import marketing_sales_shape as _shape

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Dashboard'])

@router.get("/dashboard/overview")
async def get_dashboard_overview(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Consolidated dashboard for all accounts.
    Shows: Total revenue (all accounts), Total orders, Account count, etc.
    """
    user = await require_auth(request)
    db = get_db()

    # Bug #3 fix: Query ALL accounts first, then derive active subset
    # F6 (sesi #9): hanya toko yang boleh dilihat pemakai ini yang ikut dijumlah —
    # dulu staf pemegang satu toko melihat "total omzet" sembilan toko.
    all_accounts = await _scope.visible_accounts(db, user, limit=500)
    active_accounts_list = [a for a in all_accounts if a.get("status") == "active"]
    active_ids = [a["id"] for a in active_accounts_list]
    
    # Date range default: last 30 days
    if not date_to:
        date_to = _now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Bug #2 fix: Filter sales ONLY for active account_ids
    query = {
        "date": {"$gte": date_from, "$lte": date_to},
        "account_id": {"$in": active_ids} if active_ids else {"$in": []}
    }
    
    # Total revenue (both total + live types, but we'll separate in response)
    total_sales = await db.marketing_sales_data.find(query, {"_id": 0}).to_list(500)
    
    total_revenue = 0
    total_revenue_live = 0
    total_orders = 0
    
    for sale in total_sales:
        # F0.3 — DULU `sale["metrics"]` diindeks LANGSUNG: satu dokumen berbentuk
        # rata (hasil impor sebelum F0.2) membuat SELURUH layar mati HTTP 500.
        # `read_metrics()` tetap benar untuk dokumen lama maupun kanonik.
        m = _shape.read_metrics(sale)
        if sale.get("revenue_type") == "total":
            total_revenue += m.get("revenue", 0)
            total_orders += m.get("orders", 0)
        elif sale.get("revenue_type") == "live":
            total_revenue_live += m.get("revenue", 0)
    
    # Top performing account (by revenue) — only from active accounts
    account_revenue = {}
    for sale in total_sales:
        acc_id = sale.get("account_id")
        if not acc_id:
            continue
        if sale.get("revenue_type") == "total":
            account_revenue[acc_id] = account_revenue.get(acc_id, 0) + \
                _shape.read_metrics(sale).get("revenue", 0)
    
    top_account_id = max(account_revenue, key=account_revenue.get) if account_revenue else None
    top_account = None
    if top_account_id:
        top_account = await db.marketing_platform_accounts.find_one({"id": top_account_id}, {"_id": 0, "account_name": 1, "platform": 1})
    
    return serialize_doc({
        "period": {
            "date_from": date_from,
            "date_to": date_to
        },
        "summary": {
            "total_accounts": len(all_accounts),
            "active_accounts": len(active_accounts_list),
            "total_revenue": round(total_revenue),
            "total_revenue_live": round(total_revenue_live),
            "total_orders": total_orders,
            "avg_order_value": round(total_revenue / total_orders) if total_orders > 0 else 0
        },
        "top_account": {
            "account_id": top_account_id,
            "account_name": top_account.get("account_name") if top_account else None,
            "platform": top_account.get("platform") if top_account else None,
            "revenue": round(account_revenue.get(top_account_id, 0)) if top_account_id else 0
        } if top_account else None
    })


@router.get("/accounts/{account_id}/dashboard")
async def get_account_dashboard(
    account_id: str,
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Per-account dashboard with detailed metrics.
    Shows dual revenue stream (total + live) separately.
    """
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Account not found")
    
    # Date range default: last 30 days
    if not date_to:
        date_to = _now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Get sales data for this account
    query = {
        "account_id": account_id,
        "date": {"$gte": date_from, "$lte": date_to}
    }
    
    sales_data = await db.marketing_sales_data.find(query, {"_id": 0}).sort("date", 1).to_list(500)
    
    # Separate total vs live
    total_revenue = 0
    total_orders = 0
    live_revenue = 0
    live_orders = 0
    
    daily_chart_total = []
    daily_chart_live = []
    
    # Latest metrics for health indicators
    latest_fulfillment = {}
    latest_satisfaction = {}
    
    for sale in sales_data:
        m = _shape.read_metrics(sale)      # F0.3 — aman untuk dokumen lama & kanonik
        if sale.get("revenue_type") == "total":
            total_revenue += m.get("revenue", 0)
            total_orders += m.get("orders", 0)
            daily_chart_total.append({
                "date": sale.get("date"),
                "revenue": m.get("revenue", 0),
                "orders": m.get("orders", 0)
            })
            # Get latest fulfillment & satisfaction
            if _shape.read_group(sale, "fulfillment"):
                latest_fulfillment = _shape.read_group(sale, "fulfillment")
            if _shape.read_group(sale, "customer_satisfaction"):
                latest_satisfaction = _shape.read_group(sale, "customer_satisfaction")
        elif sale.get("revenue_type") == "live":
            live_revenue += m.get("revenue", 0)
            live_orders += m.get("orders", 0)
            daily_chart_live.append({
                "date": sale.get("date"),
                "revenue": m.get("revenue", 0),
                "orders": m.get("orders", 0)
            })
    
    return serialize_doc({
        "account": {
            "id": account["id"],
            "account_code": account["account_code"],
            "account_name": account["account_name"],
            "platform": account["platform"],
            "status": account["status"],
            "health_score": account.get("health_score", 0)
        },
        "period": {
            "date_from": date_from,
            "date_to": date_to
        },
        "total_revenue_stream": {
            "revenue": round(total_revenue),
            "orders": total_orders,
            "aov": round(total_revenue / total_orders) if total_orders > 0 else 0,
            "daily_chart": daily_chart_total
        },
        "live_revenue_stream": {
            "revenue": round(live_revenue),
            "orders": live_orders,
            "aov": round(live_revenue / live_orders) if live_orders > 0 else 0,
            "daily_chart": daily_chart_live
        },
        "health_metrics": {
            "rating": latest_satisfaction.get("rating", 0),
            "review_count": latest_satisfaction.get("review_count", 0),
            "response_rate": latest_satisfaction.get("response_rate", 0),
            "fulfillment_rate": latest_fulfillment.get("fulfillment_rate", 0),
            "cancellation_rate": latest_fulfillment.get("cancellation_rate", 0),
            "return_rate": latest_fulfillment.get("return_rate", 0),
            "late_shipment_rate": latest_fulfillment.get("late_shipment_rate", 0)
        }
    })


@router.post("/accounts/{account_id}/recalculate-health")
async def recalculate_account_health(account_id: str, request: Request):
    """
    Manually trigger health score recalculation for an account.
    Useful after bulk data import or corrections.
    """
    await require_auth(request)
    db = get_db()
    
    account = await db.marketing_platform_accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        raise HTTPException(404, "Account not found")
    
    new_score = await _recalculate_health_score(db, account_id)
    
    return serialize_doc({
        "message": "Health score recalculated",
        "account_id": account_id,
        "account_name": account["account_name"],
        "new_health_score": new_score
    })


@router.get("/dashboard/comparison")
async def get_comparison_dashboard(
    request: Request,
    accounts: str = Query(..., description="Comma-separated account IDs (max 5)"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Comparison dashboard for side-by-side account analysis.
    Max 5 accounts can be compared at once.
    """
    user = await require_auth(request)
    db = get_db()

    # Parse account IDs
    account_ids = [aid.strip() for aid in accounts.split(",") if aid.strip()]
    # F6: membandingkan toko orang lain juga dilarang (jaring pengaman middleware
    # sudah menolak, ini penjaga eksplisit supaya alasannya jelas di route).
    for aid in account_ids:
        await _scope.assert_account_visible(db, user, aid)
    if len(account_ids) > 5:
        raise HTTPException(400, "Maximum 5 accounts can be compared at once")
    if len(account_ids) < 2:
        raise HTTPException(400, "At least 2 accounts required for comparison")
    
    # Date range default: last 30 days
    if not date_to:
        date_to = _now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    comparison_data = []

    # ── FIX N+1: Batch fetch accounts + sales in 2 queries instead of N×2 ─────
    accounts_list = await db.marketing_platform_accounts.find(
        {"id": {"$in": account_ids}}, {"_id": 0}
    ).to_list(500)
    accounts_map = {a["id"]: a for a in accounts_list}

    all_sales = await db.marketing_sales_data.find(
        {
            "account_id": {"$in": account_ids},
            "date": {"$gte": date_from, "$lte": date_to},
            "revenue_type": "total"
        },
        {"_id": 0}
    ).to_list(500)

    # Group sales by account_id in memory
    from collections import defaultdict as _defaultdict
    sales_by_account = _defaultdict(list)
    for s in all_sales:
        sales_by_account[s["account_id"]].append(s)

    for account_id in account_ids:
        account = accounts_map.get(account_id)
        if not account:
            continue  # Skip invalid IDs

        sales_data = sales_by_account.get(account_id, [])

        total_revenue = sum(_shape.read_metrics(s).get("revenue", 0) for s in sales_data)
        total_orders = sum(_shape.read_metrics(s).get("orders", 0) for s in sales_data)

        # Get latest satisfaction
        latest_rating = 0
        if sales_data:
            last_sale = sales_data[-1]
            latest_rating = _shape.read_group(last_sale, "customer_satisfaction").get("rating", 0)

        comparison_data.append({
            "account_id": account["id"],
            "account_code": account["account_code"],
            "account_name": account["account_name"],
            "platform": account["platform"],
            "health_score": account.get("health_score"),  # None = N/A
            "total_revenue": round(total_revenue),
            "total_orders": total_orders,
            "aov": round(total_revenue / total_orders) if total_orders > 0 else 0,
            "rating": latest_rating
        })
    
    return serialize_doc({
        "period": {
            "date_from": date_from,
            "date_to": date_to
        },
        "accounts": comparison_data
    })


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY: Seed sample data for testing
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/seed-sample-data")
async def seed_sample_data(request: Request):
    """
    Seed sample platform accounts and sales data for testing.
    USE ONLY FOR DEVELOPMENT/TESTING.
    """
    await require_auth(request)
    db = get_db()
    
    # Create 3 sample accounts
    accounts = [
        {
            "id": _uid(),
            "account_code": "SHOPEE-OFFICIAL",
            "account_name": "Shopee Official Store DEMO",
            "platform": "shopee",
            "username": "demobrand_official",
            "status": "active",
            "group": "official_store",
            "credentials": {"has_api_integration": False},
            "import_config": {"saved_templates": []},
            "assigned_staff": [],
            "pic_id": _get_user(request).get("id"),
            "health_score": 0,
            "created_at": _now(),
            "created_by": "seed",
            "updated_at": _now()
        },
        {
            "id": _uid(),
            "account_code": "SHOPEE-RESELLER",
            "account_name": "Shopee Reseller A",
            "platform": "shopee",
            "username": "demobrand_reseller",
            "status": "active",
            "group": "reseller",
            "credentials": {"has_api_integration": False},
            "import_config": {"saved_templates": []},
            "assigned_staff": [],
            "pic_id": _get_user(request).get("id"),
            "health_score": 0,
            "created_at": _now(),
            "created_by": "seed",
            "updated_at": _now()
        },
        {
            "id": _uid(),
            "account_code": "TIKTOK-STORE",
            "account_name": "TikTok Shop DEMO",
            "platform": "tiktokshop",
            "username": "demobrand_tiktok",
            "status": "active",
            "group": "official_store",
            "credentials": {"has_api_integration": False},
            "import_config": {"saved_templates": []},
            "assigned_staff": [],
            "pic_id": _get_user(request).get("id"),
            "health_score": 0,
            "created_at": _now(),
            "created_by": "seed",
            "updated_at": _now()
        }
    ]
    
    # Insert accounts
    for acc in accounts:
        existing = await db.marketing_platform_accounts.find_one({"account_code": acc["account_code"]}, {"_id": 0})
        if not existing:
            await db.marketing_platform_accounts.insert_one(acc)
    
    return serialize_doc({"message": "Sample data seeded", "accounts_created": len(accounts)})



# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: TASK MANAGEMENT SYSTEM (Trello-style)
# ══════════════════════════════════════════════════════════════════════════════

