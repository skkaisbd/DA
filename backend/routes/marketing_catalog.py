"""
Marketing Catalog - Orchestrator
"""
from fastapi import APIRouter
from routes import (
    marketing_catalog_mgmt,
    marketing_catalog_items,
    marketing_catalog_search,
    marketing_catalog_stock
)

router = APIRouter(tags=['Marketing-Catalog'])

router.include_router(marketing_catalog_mgmt.router)
router.include_router(marketing_catalog_items.router)
# F9b — pencarian item katalog LINTAS-katalog (pemilih produk di layar order).
# Prefix-nya sendiri (`/api/marketing/catalog-items`), jadi tidak bertabrakan
# dengan rute `/api/marketing/catalogs/{catalog_id}/items`.
router.include_router(marketing_catalog_search.router)
router.include_router(marketing_catalog_stock.router)
