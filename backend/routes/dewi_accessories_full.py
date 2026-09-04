"""
Dewi Accessories - Orchestrator
"""
from fastapi import APIRouter
from routes import (
    dewi_accessories_items,
    dewi_accessories_stock,
    dewi_accessories_requests,
    dewi_accessories_loans,
    dewi_accessories_opname,
    dewi_accessories_purchase,
    dewi_accessories_dashboard,
    dewi_accessories_valuation,  # FASE 8: valuasi HPP aksesoris
)

router = APIRouter(prefix="/api/acc", tags=["accessories"])

router.include_router(dewi_accessories_items.router, prefix="")
router.include_router(dewi_accessories_stock.router, prefix="")
router.include_router(dewi_accessories_requests.router, prefix="")
router.include_router(dewi_accessories_loans.router, prefix="")
router.include_router(dewi_accessories_opname.router, prefix="")
router.include_router(dewi_accessories_purchase.router, prefix="")
router.include_router(dewi_accessories_dashboard.router, prefix="")
router.include_router(dewi_accessories_valuation.router, prefix="")  # FASE 8
