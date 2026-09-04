"""
Unified Search API
Provides smart search across all data types in the ERP system
"""
import logging
from fastapi import APIRouter, Query, Request
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/search", tags=["search"])


async def search_orders(db, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search production orders"""
    try:
        # Search by order_no, style_code, buyer_name
        regex_pattern = {"$regex": query, "$options": "i"}
        orders = await db["rahaza_orders"].find({
            "$or": [
                {"order_no": regex_pattern},
                {"style_code": regex_pattern},
                {"buyer_name": regex_pattern},
            ]
        }).limit(limit).to_list(length=limit)
        
        return [{
            "type": "order",
            "id": str(o.get("_id")),
            "title": f"Order {o.get('order_no', 'N/A')}",
            "subtitle": f"{o.get('style_code', '')} - {o.get('buyer_name', '')}",
            "metadata": {
                "quantity": o.get("quantity", 0),
                "status": o.get("status", "unknown"),
                "delivery_date": o.get("delivery_date"),
            },
            "url": f"/portal/production?module=order-management&order={o.get('order_no')}"
        } for o in orders]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error searching orders: {e}")
        return []


async def search_employees(db, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search employees"""
    try:
        regex_pattern = {"$regex": query, "$options": "i"}
        employees = await db["rahaza_employees"].find({
            "$or": [
                {"name": regex_pattern},
                {"employee_code": regex_pattern},
                {"department": regex_pattern},
                {"job_title": regex_pattern},
            ]
        }).limit(limit).to_list(length=limit)
        
        return [{
            "type": "employee",
            "id": str(e.get("_id")) or e.get("employee_code"),
            "title": e.get("name", "N/A"),
            "subtitle": f"{e.get('job_title', '')} - {e.get('department', '')}",
            "metadata": {
                "code": e.get("employee_code"),
                "status": e.get("status", "active"),
                "hire_date": e.get("hire_date"),
            },
            "url": f"/portal/hr?module=hr-dashboard&employee={e.get('employee_code')}"
        } for e in employees]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error searching employees: {e}")
        return []


async def search_products(db, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search products/styles"""
    try:
        regex_pattern = {"$regex": query, "$options": "i"}
        products = await db["rahaza_styles"].find({
            "$or": [
                {"style_code": regex_pattern},
                {"style_name": regex_pattern},
                {"category": regex_pattern},
            ]
        }).limit(limit).to_list(length=limit)
        
        return [{
            "type": "product",
            "id": str(p.get("_id")),
            "title": p.get("style_code", "N/A"),
            "subtitle": p.get("style_name", ""),
            "metadata": {
                "category": p.get("category"),
                "sam": p.get("sam_value"),
            },
            "url": f"/portal/production?module=style-master&style={p.get('style_code')}"
        } for p in products]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error searching products: {e}")
        return []


async def search_invoices(db, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search invoices"""
    try:
        regex_pattern = {"$regex": query, "$options": "i"}
        # RC-14: SSOT rahaza_ar_invoices (field: invoice_number/customer_name/total/issue_date)
        invoices = await db["rahaza_ar_invoices"].find({
            "$or": [
                {"invoice_number": regex_pattern},
                {"customer_name": regex_pattern},
            ]
        }).limit(limit).to_list(length=limit)
        
        return [{
            "type": "invoice",
            "id": inv.get("id") or str(inv.get("_id")),
            "title": f"Invoice {inv.get('invoice_number', 'N/A')}",
            "subtitle": inv.get("customer_name", ""),
            "metadata": {
                "amount": inv.get("total", 0),
                "status": inv.get("status", "unknown"),
                "date": inv.get("issue_date"),
            },
            "url": f"/portal/finance?module=invoice-list&invoice={inv.get('invoice_number')}"
        } for inv in invoices]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error searching invoices: {e}")
        return []


async def search_maklon_clients(db, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search maklon clients"""
    try:
        regex_pattern = {"$regex": query, "$options": "i"}
        clients = await db["dewi_maklon_clients"].find({
            "$or": [
                {"client_name": regex_pattern},
                {"brand_name": regex_pattern},
                {"contact_person": regex_pattern},
            ]
        }).limit(limit).to_list(length=limit)
        
        return [{
            "type": "client",
            "id": str(c.get("_id")),
            "title": c.get("client_name", "N/A"),
            "subtitle": f"{c.get('brand_name', '')} - {c.get('contact_person', '')}",
            "metadata": {
                "tier": c.get("tier"),
                "status": c.get("status", "active"),
            },
            "url": f"/portal/maklon?module=client-database&client={c.get('_id')}"
        } for c in clients]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error searching maklon clients: {e}")
        return []


@router.get("")
async def unified_search(
    request: Request,
    q: str = Query(..., min_length=2, description="Search query"),
    types: Optional[str] = Query(None, description="Comma-separated list of types to search (order,employee,product,invoice,client)"),
    limit: int = Query(5, ge=1, le=20, description="Max results per type"),
):
    """
    Unified search across all ERP data types
    
    Query parameters:
    - q: Search query (min 2 characters)
    - types: Optional filter by types (comma-separated: order,employee,product,invoice,client)
    - limit: Max results per type (default: 5, max: 20)
    
    Returns:
    - results: List of search results grouped by type
    - total: Total number of results
    - query: Original search query
    """
    
    await require_auth(request)
    db = get_db()
    
    # Determine which types to search
    search_types = []
    if types:
        search_types = [t.strip() for t in types.split(",")]
    else:
        search_types = ["order", "employee", "product", "invoice", "client"]
    
    results = []
    
    # Execute searches in parallel (conceptually - asyncio handles this)
    if "order" in search_types:
        results.extend(await search_orders(db, q, limit))
    
    if "employee" in search_types:
        results.extend(await search_employees(db, q, limit))
    
    if "product" in search_types:
        results.extend(await search_products(db, q, limit))
    
    if "invoice" in search_types:
        results.extend(await search_invoices(db, q, limit))
    
    if "client" in search_types:
        results.extend(await search_maklon_clients(db, q, limit))
    
    # Sort by relevance (simple: exact matches first, then partial)
    # Exact match scoring
    def score_result(r):
        title_lower = r["title"].lower()
        query_lower = q.lower()
        
        if title_lower == query_lower:
            return 100
        elif title_lower.startswith(query_lower):
            return 80
        elif query_lower in title_lower:
            return 60
        else:
            return 40
    
    results.sort(key=score_result, reverse=True)
    
    return {
        "success": True,
        "data": {
            "results": results,
            "total": len(results),
            "query": q,
            "types_searched": search_types,
        },
        "metadata": {
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }
    }

