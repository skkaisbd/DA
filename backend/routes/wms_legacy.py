"""
WMS Legacy Bridge Router
========================

Phase 3 Migration — Dual API Conflict Resolution
-------------------------------------------------
The original `routes/warehouse.py` exposed endpoints under `/api/warehouse/*`
prefix. The new modular WMS system uses the `/api/wms/*` prefix.

To consolidate everything under a single `/api/wms` namespace WITHOUT breaking
existing data/flows, this bridge router exposes the same legacy handlers under
the new canonical path `/api/wms/legacy/*`.

**Migration Strategy:**
- ✅ Same handlers, same database collections (no data migration risk)
- ✅ Frontend can switch URLs gradually (`/api/warehouse/X` → `/api/wms/legacy/X`)
- ✅ Legacy `/api/warehouse/*` routes remain for backward compatibility
- 🚧 Future: deprecate `/api/warehouse/*` once all clients migrated

**Endpoints mirrored:**
- GET/POST/PUT/DELETE  /locations[/{id}]
- GET/POST/PUT/DELETE  /receiving[/{id}]
- GET                  /stock, /stock/summary, /movements
- GET                  /dashboard, /dashboard-kpi
- GET/POST             /putaway
- GET/POST/PUT         /opname[/{id}]
"""
from fastapi import APIRouter, Request
from routes import warehouse as legacy

router = APIRouter(prefix="/api/wms/legacy", tags=["wms-legacy-bridge"])


# ── Locations ─────────────────────────────────────────────────────────────────

@router.get("/locations")
async def get_locations(request: Request):
    return await legacy.get_locations(request)


@router.post("/locations")
async def create_location(request: Request):
    return await legacy.create_location(request)


@router.put("/locations/{location_id}")
async def update_location(location_id: str, request: Request):
    return await legacy.update_location(location_id, request)


@router.delete("/locations/{location_id}")
async def delete_location(location_id: str, request: Request):
    return await legacy.delete_location(location_id, request)


# ── Goods Receiving ───────────────────────────────────────────────────────────

@router.get("/receiving")
async def get_receiving(request: Request):
    return await legacy.get_receiving(request)


@router.get("/receiving/{receipt_id}")
async def get_receipt(receipt_id: str, request: Request):
    return await legacy.get_receipt(receipt_id, request)


@router.post("/receiving")
async def create_receiving(request: Request):
    return await legacy.create_receiving(request)


@router.put("/receiving/{receipt_id}")
async def update_receiving(receipt_id: str, request: Request):
    return await legacy.update_receiving(receipt_id, request)


@router.delete("/receiving/{receipt_id}")
async def delete_receiving(receipt_id: str, request: Request):
    return await legacy.delete_receiving(receipt_id, request)


# ── Stock & Movements ─────────────────────────────────────────────────────────

@router.get("/stock")
async def get_stock(request: Request, location_id: str = None, sku: str = None):
    return await legacy.get_stock(request, location_id=location_id, sku=sku)


@router.get("/stock/summary")
async def get_stock_summary(request: Request):
    return await legacy.get_stock_summary(request)


@router.get("/movements")
async def get_movements(request: Request, location_id: str = None, sku: str = None, limit: int = 100):
    return await legacy.get_movements(request, location_id=location_id, sku=sku, limit=limit)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard-kpi")
async def warehouse_dashboard_kpi(request: Request):
    return await legacy.warehouse_dashboard_kpi(request)


@router.get("/dashboard")
async def warehouse_dashboard(request: Request):
    return await legacy.warehouse_dashboard(request)


# ── Put-Away & Stock Opname (legacy) — DIHAPUS (Fase 5 cleanup, 2026-07-23) ──────
# Put-Away kanonik     → /api/wms/putaway/*   (routes/wms_putaway.py, sadar-lokasi)
# Stock Opname kanonik → /api/wms/opname3/*   (routes/wms_opname3.py, scan-driven + finance)
# Endpoint bridge lama /putaway & /opname dihapus: tidak ada consumer UI aktif.
# Endpoint bridge yang MASIH LIVE dipertahankan di atas:
#   /locations, /receiving, /stock, /stock/summary, /movements, /dashboard-kpi, /dashboard
