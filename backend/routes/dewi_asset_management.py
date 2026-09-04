"""
CV. Dewi Aditya ERP — Asset Management (Thin Orchestrator).

[REFACTORED 2026-05-24 — was 2392 LOC monolith; now split into routes/asset/*]

This file's sole job is to:
  1. Import the shared `router` and `create_asset_indexes` from `routes.asset._helpers`.
  2. Trigger registration of all endpoints by importing each sub-module in the
     correct order (literal paths BEFORE catch-all `/{asset_id}` routes).
  3. Re-export `router` (so `server.py` import remains backward-compatible).

No behavior change — every endpoint preserves its original path, method,
request schema, and response shape. Backed by the SAME MongoDB collections:
  dewi_assets, dewi_asset_categories, dewi_asset_assignments,
  dewi_asset_maintenance, dewi_asset_depreciation,
  dewi_asset_disposal_requests, dewi_asset_transfers, dewi_asset_scans,
  dewi_asset_pm_acknowledgments

Endpoint groups (file-by-file):
  dashboard.py              → GET    /dashboard
  categories.py             → (GET|POST|PUT|DELETE) /categories[/{id}]
  bulk_import.py            → (POST|GET) /bulk-import/(preview|execute|template|execute-file)
  expiring_my.py            → GET    /expiring-alerts, /my-assets
  disposal.py               → GET    /disposal-requests, PATCH /disposal-requests/{id}/(approve|reject),
                               POST   /{asset_id}/(dispose|request-disposal)
  depreciation_batch.py     → POST   /batch-depreciate/{period}
  scan_lookup.py            → GET    /scan-by-number/{asset_number}
  reports.py                → GET    /reports/utilization(.csv)
  predictive_maintenance.py → GET    /predictive-maintenance/(alerts|acknowledgments),
                               POST   /predictive-maintenance/acknowledge
  loans.py                  → (GET|POST) /loans[/{id}][/return], GET /loans/summary,
                               GET /loanable-assets   ← ACC-3 (peminjaman ALAT pindah dari Aksesoris)
  assets_core.py            → (GET|POST) /, (GET|PUT) /{asset_id}
  assignments.py            → POST   /{asset_id}/(assign|unassign|maintenance), GET /{asset_id}/(assignments|maintenance)
  depreciation_per.py       → POST   /{asset_id}/depreciate/{period}, GET /{asset_id}/depreciation-history
  transfer.py               → POST   /{asset_id}/transfer, GET /{asset_id}/transfer-history
  scan_label.py             → POST   /{asset_id}/scan, GET /{asset_id}/(scan-history|barcode|qrcode|label-pdf)
  photo.py                  → POST   /{asset_id}/upload-photo
"""
# Shared router instance + indexes helper
from routes.asset._helpers import router, create_asset_indexes  # noqa: F401  (re-exported)

# ─── IMPORT ORDER MATTERS ───────────────────────────────────────────────────
# FastAPI matches by registration order: literal/specific paths first, then catch-all.
# Step 1: all LITERAL paths
from routes.asset import dashboard                  # noqa: F401, E402  /dashboard
from routes.asset import categories                 # noqa: F401, E402  /categories[/...]
from routes.asset import bulk_import                # noqa: F401, E402  /bulk-import/*
from routes.asset import expiring_my                # noqa: F401, E402  /expiring-alerts, /my-assets
from routes.asset import disposal                   # noqa: F401, E402  /disposal-requests/* + /{id}/(dispose|request-disposal)
from routes.asset import depreciation_batch         # noqa: F401, E402  /batch-depreciate/{period}
from routes.asset import scan_lookup                # noqa: F401, E402  /scan-by-number/{num}
from routes.asset import reports                    # noqa: F401, E402  /reports/*
from routes.asset import predictive_maintenance     # noqa: F401, E402  /predictive-maintenance/*
from routes.asset import loans                      # noqa: F401, E402  /loans[/...], /loanable-assets  (ACC-3)

# Step 2: catch-all /{asset_id} and /{asset_id}/* routes
from routes.asset import assets_core                # noqa: F401, E402  /, /{id} (GET/POST/PUT)
from routes.asset import assignments                # noqa: F401, E402  /{id}/(assign|unassign|assignments|maintenance)
from routes.asset import depreciation_per           # noqa: F401, E402  /{id}/depreciate, /{id}/depreciation-history
from routes.asset import transfer                   # noqa: F401, E402  /{id}/transfer, /{id}/transfer-history
from routes.asset import scan_label                 # noqa: F401, E402  /{id}/(scan|scan-history|barcode|qrcode|label-pdf)
from routes.asset import photo                      # noqa: F401, E402  /{id}/upload-photo

__all__ = ["router", "create_asset_indexes"]
