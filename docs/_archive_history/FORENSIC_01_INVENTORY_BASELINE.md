# FORENSIC AUDIT — 01: INVENTORY BASELINE
## Inventarisasi Lengkap Aset Sistem

**Method:** Static code scan + DB collection grep + sidebar parsing

---

## 1. PORTAL INVENTORY (11 portals)

| ID | Label | Sections | Total Items | Status |
|----|-------|----------|-------------|--------|
| `management` | Manajemen | 3 | 16 | 🟢 Active |
| `production` | Produksi | 4 | 38 | 🟢 Active (2 broken items) |
| `warehouse` | Gudang | 3 | 24 | 🟢 Active (1 duplicate view) |
| `finance` | Keuangan | 3 | 25 | 🟢 Active |
| `hr` | SDM | 6 | 30 | 🟢 Active |
| `rnd` | RnD & Desain | 3 | 12 | 🟢 Active |
| `self` | Portal Saya | 3 | 13 | 🟢 Active |
| `maklon` | Maklon | 4 | 14 | 🟡 Active (2 broken items) |
| `toko` | Marketing | 5 | 26 | 🟢 Active (2 legacy items) |
| `collaboration` | Portal Kolaborasi | 1 | 2 | 🟡 Minimal coverage |
| `assets` | Manajemen Aset | 1 | 3 | 🟡 Minimal coverage |
| **TOTAL** | — | **36** | **~203** | — |

---

## 2. FRONTEND COMPONENT INVENTORY

### 2.1 Top-Level (270 in /erp/)

**By Category:**
- Dashboard components: ~25 (Production, HR, Finance, Marketing, Maklon, RnD, etc.)
- Module components (CRUD): ~120
- Sub-component (atoms/widgets): ~60
- Pages/Portals: ~12
- AI-specific modules: ~15
- Marketing sub-folder: ~30
- Other (utils, contexts): ~8

### 2.2 Notable Subfolders
- `/erp/marketing/` — 32 modules
- `/erp/hr/` — 6 modules
- `/erp/finance/` — 2 modules
- `/erp/portal/` — 4 modules
- `/erp/collaboration/` — 4 sub-folders (communication, learning, shared, workspace)
- `/erp/bom/` — 3 modules
- `/erp/userGuide/` — guide components

### 2.3 Suspicious Files
- `RahazaHPPModule.jsx.backup` — Backup file in source tree (should be removed)
- Multiple "Placeholder" files: `HRDashboardPlaceholder.jsx`, `ProductionDashboardPlaceholder.jsx` (legacy)

---

## 3. BACKEND ROUTE INVENTORY (194 files)

### 3.1 By Prefix Domain

| Prefix | File Count | Sample Routes |
|--------|-----------|---------------|
| `/api/rahaza/*` | ~70 | Master data, production, finance, HR (heavy) |
| `/api/dewi/*` | ~40 | Marketing, CMT, Maklon, RnD, AI, HR-AI, Notifications |
| `/api/wms/*` | ~15 | Warehouse Management System (newest) |
| `/api/wh/*` | ~5 | Warehouse legacy bridge |
| `/api/marketing/*` | ~20 | Marketing portal (newest) |
| `/api/hr/*` | ~5 | HR AI features |
| `/api/maklon/*` | ~3 | SLA, AI Quote |
| `/api/finance/*` | ~3 | Bank recon, etc. |
| `/api/portal-saya/*` | ~5 | Self-service portal |
| `/api/comm` `/api/assets` `/api/workspace` `/api/notifications` etc. | ~10 | New modules (NL collab portal) |
| `/api/acc/*` | ~5 | Accessory standalone system |
| Others | ~13 | Search, file storage, websocket, etc. |

### 3.2 Fragmentation Indicators

- **70 files with `rahaza_*` prefix** — namespace from earlier system (PT Rahaza)
- **40 files with `dewi_*` prefix** — newer namespace (CV. Dewi Aditya rebrand)
- **Same business domain split across both prefixes** (e.g., Maklon ada di `/api/rahaza/maklon-*` DAN `/api/dewi/*` DAN `/api/maklon/*`)

### 3.3 Likely Orphan/Unused Route Files (need verification)

Files that look like they may not be wired anymore:
- `routes/production.py` — generic, possibly superseded by `production_po.py` + `rahaza_production.py`
- `routes/master_data.py` — generic, possibly superseded by `rahaza_master.py`
- `routes/warehouse.py` — superseded by `wms_*` files
- `routes/dewi_toko.py` — legacy storefront
- `routes/dewi_kol.py` vs `marketing_kol.py` — likely duplicate
- `routes/dewi_online_orders.py` — superseded by marketing_orders_routes.py

---

## 4. MONGODB COLLECTION INVENTORY (~280 collections)

### 4.1 By Namespace Prefix

| Prefix | Count | Notes |
|--------|-------|-------|
| `rahaza_*` | ~90 | Production, master data, finance, HR (largest) |
| `dewi_*` | ~55 | Marketing, KOL, Maklon, CMT, Assets, AI, RnD |
| `marketing_*` | ~40 | Modern marketing portal |
| `wh_*` | ~20 | WMS structure & ops |
| `wms_*` | ~5 | WMS legacy bridge |
| `acc_*` | ~7 | Accessory standalone system |
| `hr_*` `hris_*` `comm_*` `da_*` | ~25 | Cross-domain newer |
| Generic (no prefix) | ~30 | `users`, `roles`, `invoices`, `products`, `payments`, etc. (legacy) |
| `production_*` `qc_*` `material_*` | ~15 | Production legacy |
| `workspace_*` `collab_*` | ~5 | New collaboration portal |

### 4.2 Critical Multi-SSOT Clusters

**Cluster A — Materials/Inventory:**
- `rahaza_materials` (master, production-integrated)
- `acc_items` (accessory standalone)
- `accessories` (legacy)
- `products` (legacy)

**Cluster B — Stock:**
- `rahaza_material_stock` + `rahaza_material_movements`
- `warehouse_stock` + `warehouse_movements` (legacy)
- `acc_stock_movements`
- `wh_fg_movements`

**Cluster C — Maklon Orders:**
- `dewi_maklon_orders` (lama)
- `dewi_maklon_pos` (baru)
- `rahaza_orders` (parsial)

**Cluster D — Invoices:**
- `invoices` (legacy)
- `dewi_invoices`
- `dewi_maklon_invoices`
- `rahaza_ar_invoices`
- `rahaza_invoices`
- `rahaza_ap_invoices`

**Cluster E — Users/Identity:**
- `users` (main)
- `rahaza_users` (production)
- `dewi_client_users` (client portal)
- Multiple `*_login_attempts` collections

**Cluster F — Counters/Sequences:**
- `counters`
- `dewi_counters`
- `rahaza_counters`
- `rahaza_bundle_counters`
- `wh_counters`

**Cluster G — Shipments:**
- `rahaza_shipments` (sales out)
- `buyer_shipments` (buyer-facing)
- `vendor_shipments` (incoming)
- `wh_delivery_notes` (WMS-tagged)
- `accessory_shipments`
- `dewi_maklon_dispatches`

**Cluster H — KOL/Creator:**
- `dewi_kol_creators` + `dewi_kol_deals` + `dewi_kol_samples` (old)
- `marketing_kol_creators` + `marketing_kol_login_attempts`
- `marketing_creator_*` (newest)

**Cluster I — Toko (Legacy Marketplace):**
- `dewi_toko_channels` + `dewi_toko_channel_syncs`
- `dewi_toko_flashsales`
- `dewi_toko_orders` + `dewi_toko_pack_batches`
- `dewi_toko_products`
- `dewi_toko_returns` + `dewi_toko_reviews`

**Cluster J — Notifications:**
- `dewi_notifications`
- `rahaza_notifications`
- `collab_notifications`
- `marketing_livehost_notifications`
- `push_subscriptions`

---

## 5. KEY ENVIRONMENTAL ASSETS

### Python Backend
- FastAPI app at `/app/backend/server.py` (1542 lines)
- 280+ MongoDB collections via Motor async
- APScheduler for cron jobs
- WebAuthn for HR Auto-Attendance
- 300+ Pydantic models distributed across route files

### React Frontend
- 270 .jsx files in `/app/frontend/src/components/erp/`
- Heavy lazy loading via `React.lazy()`
- Shadcn/UI components in `/components/ui/`
- 1 page only: `/pages/AbsenPage.jsx` (rest are component-driven via PortalShell)

### Documentation Files (Pre-existing)
- `/app/README.md` — main project overview
- `/app/GAP_ANALYSIS_REPORT.md` — Identifies 3 gaps (Comm Hub, Assets, Workspace)
- `/app/MENU_ANALYSIS_REPORT_2026-05-22.md` — Sidebar audit
- `/app/DEEP_ANALYSIS_GUDANG_2026-05-22.md` — Warehouse forensic
- `/app/DEEP_ANALYSIS_PRODUKSI_2026-05-22.md` — Production forensic
- `/app/DEEP_ANALYSIS_HR_MARKETING_2026-05-22.md` — HR + Marketing forensic
- `/app/MARKETING_PORTAL_AUDIT_REPORT.md`
- `/app/MARKETING_KOL_LIVEHOST_DOCUMENTATION.md`
- `/app/WORKSPACE_DESIGN.md`
- `/app/design_guidelines.md`

---

## 6. CREDENTIALS & ACCESS

- Admin login: `admin@garment.com` / `Admin@123`
- Backend URL: configured in `frontend/.env` via `REACT_APP_BACKEND_URL`
- DB URL: configured in `backend/.env` via `MONGO_URL`
- Emergent LLM Key: available for OpenAI GPT-4o integration (smart attendance, insights)

---

## 7. SUMMARY

Sistem ini adalah **ERP enterprise full-stack** dengan cakupan sangat luas (Production, HR, Finance, Warehouse, Marketing, Maklon, RnD, Self-Service, Asset Mgmt, Collaboration). 

**Major Strength:** Coverage bisnis end-to-end yang comprehensive.

**Major Weakness:** Heavy technical debt akibat:
- 3 generasi namespace berbeda (rahaza/dewi/wms+marketing+wh)
- Banyak fitur yang dibangun paralel tanpa konsolidasi
- Tidak ada single source of truth untuk beberapa domain kunci
- UI menjadi cognitive overload

**Recommendation:** Refactoring strategis selama 2 bulan untuk mencapai enterprise-grade architecture (see FORENSIC_11 untuk roadmap).
