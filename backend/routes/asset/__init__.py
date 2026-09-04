"""
CV. Dewi Aditya ERP — Asset Management sub-package.

This package splits the original monolithic `dewi_asset_management.py` (2392 LOC)
into per-aggregate sub-modules. The shared `router` lives in `_helpers.py` and is
imported by each sub-module to register its endpoints.

Load-order is enforced by the orchestrator `routes/dewi_asset_management.py`:
literal paths (e.g. /disposal-requests, /reports/utilization) MUST be registered
BEFORE the catch-all `/{asset_id}` route in `assets_core`.
"""
