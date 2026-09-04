# DA25 ERP — System Architecture Reference

> **Last Updated:** 2026-05-27 (Session #11.20)

---

## 1. Tech Stack

| Layer | Technology | Detail |
|---|---|---|
| Frontend | React 18 (CRA) | Lazy-loaded modules via `moduleRegistry.js` |
| Backend | FastAPI (Python 3.11) | Motor (async MongoDB driver) |
| Database | MongoDB (local) | See collections below |
| Auth | JWT (HS256) | `JWT_SECRET` env var, 24h expiry |
| Task Queue | APScheduler | `utils/scheduler.py` |
| Real-time | SSE (Server-Sent Events) | Rahaza notifications, Livehost |
| State Mgmt | React Context + localStorage | Per-portal active account |

---

## 2. Service Architecture

```
Kubernetes Ingress
  ├── /api/*  →  FastAPI (port 8001, bind 0.0.0.0)
  └── /*      →  React CRA dev server (port 3000)

MongoDB: mongodb://localhost:27017
DB_NAME: from environment variable
```

### Environment Variables

| Variable | Location | Purpose |
|---|---|---|
| `MONGO_URL` | `/app/backend/.env` | MongoDB connection string |
| `DB_NAME` | `/app/backend/.env` | Database name |
| `JWT_SECRET` | `/app/backend/.env` | JWT signing secret |
| `REACT_APP_BACKEND_URL` | `/app/frontend/.env` | Frontend → Backend URL |

---

## 3. Backend Structure

```
/app/backend/
├── server.py              # FastAPI app entrypoint, router registration, indexes
├── requirements.txt
├── routes/                # 200+ route modules (see Domain sections)
├── utils/
│   ├── counters.py        # SSOT counter helper (next_counter, next_counter_batch)
│   ├── notif_unified.py   # SSOT notification helper (notif_insert, notif_list)
│   ├── scheduler.py       # APScheduler jobs (birthday, leave carry-forward, etc.)
│   └── shared.py          # Shared utilities (serialize_doc, etc.)
├── migrations/
│   ├── drop_legacy_notif_collections.py
│   ├── migrate_counters_unification.py
│   └── migrate_notifications_unification.py
└── scripts/
    └── seed_marketing_demo.py
```

---

## 4. Frontend Structure

```
/app/frontend/src/
├── App.js                 # Main router + portal switcher
├── App.css
├── components/
│   ├── erp/
│   │   ├── portal-shell/
│   │   │   ├── PortalShell.jsx        # Main shell (refactored Session #11 — was 3200 LOC)
│   │   │   ├── portalNav.js           # Navigation config per portal
│   │   │   └── moduleRegistry.js      # Lazy module registry (portal → module map)
│   │   ├── [domain]/                  # 279 domain modules
│   │   └── ...other components
│   └── ui/                            # shadcn/ui components
├── hooks/
│   ├── useActiveMarketingAccount.js
│   └── ...
└── lib/
```

### Module Registry Pattern

Each portal entry in `portalNav.js` has an `id`. `moduleRegistry.js` maps `id → React.lazy(component)`. `PortalShell.jsx` renders the active module based on current nav id.

---

## 5. SSOT Collections (Single Source of Truth)

After P0→P3 tech debt cleanup (Sessions #1–#11.20), these are the canonical SSOTs:

| Domain | SSOT Collection | Discriminator | Notes |
|---|---|---|---|
| Counters | `counters` | `namespace` | Replaces 5 legacy counter collections |
| Notifications | `notifications` | `type` | Replaces 4 legacy notif collections |
| Materials (incl. Accessories) | `rahaza_materials` | `type` field | `type='accessory'` for accessories |
| Material Movements | `rahaza_material_movements` | — | Replaces legacy movement collections |
| Accessory Requests | `dewi_accessory_requests` | `request_type` | Replaces 3 parallel systems |
| Maklon PO | `dewi_maklon_pos` | — | Replaces legacy `dewi_maklon_orders` |
| Marketing Accounts | `marketing_platform_accounts` | `platform` | Shopee, TikTok, Tokopedia, etc. |
| Opname | `wh_opname2_sessions` + `wh_opname2_items` | — | Replaces warehouse_opname Gen1 |
| Bundles | `rahaza_bundles` | — | Production bundle tracking |
| WIP Events | `rahaza_wip_events` | `event_type` | Production scan events |

---

## 6. Auth & RBAC

- **JWT** in `Authorization: Bearer <token>` header
- **Users** → `users` collection (email + bcrypt password)
- **Roles** → `roles` collection (linked to users)
- **Permissions** → `permissions` collection (per role)
- **Role Matrix** — UI at `/mgmt-role-matrix`
- **Activity Log** — `activity_logs` collection, all write ops logged
- **Approval Chains** — `approval_chains` + `approval_requests` collections

### Test Credentials
```
Email:    admin@garment.com
Password: Admin@123
Role:     Super Admin (all permissions)
```

---

## 7. Approval System (Session #11.18–#11.20)

Centralized approval hub at `/unified-approval-hub`.

**Supported approval types:**
```
leave           rahaza_leave_requests
overtimeRequest rahaza_overtime_requests  
salary          rahaza_salary_adjustments
expense         rahaza_expense_claims
po              rahaza_pos
material_return production_material_returns
resignation     rahaza_resignations
asset_purchase  rahaza_asset_purchase_reqs
purchase_request dewi_purchase_requests
```

**API Endpoints:**
```
GET  /api/approval/chains          — list all chains
POST /api/approval/chains          — create chain
GET  /api/approval/requests        — list pending requests
POST /api/approval/requests/{id}/approve
POST /api/approval/requests/{id}/reject
```

---

## 8. Universal Scan (Session #11.19)

FAB button (bottom-right corner of all portals). Scans any entity by ID/code.

**Supported entity types:**
```
asset          /api/dewi/assets/{id}
bundle         /api/rahaza/bundles/{id}
material_issue /api/rahaza/material-issues/{id}
work_order     /api/rahaza/work-orders/{id}
po             /api/rahaza/pos/{id}
roll           /api/wms/fabric-rolls/{id}
delivery_order /api/wms/delivery-notes/{id}
```

**API:** `GET /api/universal-scan/{entity_type}/{code}`

---

## 9. Notification Architecture

Post Session #11.12, all notifications flow through a single SSOT:

```
SSO: notifications (collection)
  type='dewi'              → WhatsApp/Email notifications (dewi_notifications.py)
  type='rahaza'            → In-app alerts (rahaza_notifications.py)  
  type='collab'            → Collaboration notifications (notifications.py)
  type='marketing_livehost' → Livehost shift notifications
```

**Helper functions** in `utils/notif_unified.py`:
- `notif_insert(db, *, type, body, **kwargs)` — write to SSOT
- `notif_list(...)` — paginated query
- `notif_count_unread(...)` — unread counter
- `notif_mark_read(...)` — toggle read

---

## 10. Counter Architecture

Post Session #11.11, all sequence counters use single SSOT:

```
SSO: counters (collection)
  namespace='generic'  → LKP, AP, GR, PO
  namespace='rahaza'   → Bundles, Work Orders
  namespace='wms'      → WMS receiving, opname
  namespace='dewi'     → Maklon billing, CMT DO
```

**Helper functions** in `utils/counters.py`:
- `next_counter(db, key, namespace)` — atomic increment +1
- `next_counter_batch(db, key, count, namespace)` — batch reserve
- `peek_counter(db, key)` — read without increment

---

## 11. Scheduler Jobs (`utils/scheduler.py`)

| Job | Schedule | Purpose |
|---|---|---|
| `job_birthday_anniversary_reminders` | Daily 08:00 | Send birthday/anniversary notifs |
| `job_scan_overdue_invoices` | Daily 01:00 | Flag overdue AR invoices |
| `leave_carry_forward` | Jan 1 01:00 | Carry forward leave balances (max 5 days) |
| APS scheduler | Configurable | Production line scheduling |

---

## 12. Performance & Bundle Stats

- **Backend:** 1,485 registered endpoints across 200+ route modules
- **Frontend:** 279 ERP modules (lazy-loaded), main bundle 222kB (gzip)
- **Tests:** Jest 204 tests (last run), iteration_92 backend 27/27 pass
- **DB Latency:** <1ms (local MongoDB)

---

## 13. Key Files Quick Reference

| File | Purpose |
|---|---|
| `backend/server.py` | App entry, router registration, startup indexes |
| `backend/utils/counters.py` | Atomic counter helper |
| `backend/utils/notif_unified.py` | Unified notification helper |
| `backend/utils/scheduler.py` | Cron-like scheduler jobs |
| `frontend/src/App.js` | Main router |
| `frontend/src/components/erp/portal-shell/PortalShell.jsx` | Portal shell (refactored) |
| `frontend/src/components/erp/portal-shell/portalNav.js` | Nav config |
| `frontend/src/components/erp/portal-shell/moduleRegistry.js` | Lazy module map |
| `backend/routes/approval_multilevel.py` | Unified approval chains |
| `backend/routes/universal_scan.py` | Universal entity scanner |

---

## 14. Tech Debt History Summary

| Phase | Session | Status | Description |
|---|---|---|---|
| P0 Quick Wins | #1 (2026-05-22) | ✅ DONE | Fix broken menus, clean badges, remove duplicates |
| P1.A | #1 (2026-05-22) | ✅ DONE | Accessory Consolidation → rahaza_materials |
| P1.B | #1 (2026-05-22) | ✅ DONE | Maklon Orders → dewi_maklon_pos |
| P1.C | #1 (2026-05-22) | ✅ DONE | P2P Flow: Create GR from PO |
| P1.D | #1 (2026-05-23) | ✅ DONE | Legacy Toko Migration → marketing_* |
| P2 Workflow | #2–#11.8 | ✅ DONE | 14 workflow consolidations |
| P3 TD-008 | #11.9 | ✅ DONE | Opname Systems Consolidation |
| P3 TD-009 | #11.10 | ✅ DONE | Accessory Request SSOT |
| P3 TD-010A | #11.11 | ✅ DONE | Counters + Notifications SSOT |
| P3 TD-010B | #11.12 | ✅ DONE | Notification Writer Refactor (17 sites) |
| P3 Monitor | #11.13 | ✅ DONE | 4 legacy collections dropped |
| P3 Shipping | #11.14 | ✅ DONE | Shipping module consolidation (last P2) |
| P3 Orphan | #11.15–#11.16 | ✅ DONE | Drop orphan collections (KOL+Finance+Marketing) |
| UI-UX | #11.17 | ✅ DONE | Hash routing fix + Jest 204 tests + bundle 51% reduction |
| Scan | #11.19 | ✅ DONE | Universal Multi-Entity Scan |
| PR→PO | #11.19 | ✅ DONE | Purchase Request → PO full workflow |
| Approval | #11.20 | ✅ DONE | Approval Chain Completion (9 entity types) |

**ALL P1/P2/P3/UI-UX tasks: COMPLETE ✅**

---

## 15. Forensic Audit Documents

Results from deep forensic audit (Session #1 / 2026-05-22):

| File | Content |
|---|---|
| `FORENSIC_00_EXECUTIVE_SUMMARY.md` | Top 10 findings + score per dimension |
| `FORENSIC_01_INVENTORY_BASELINE.md` | 194 routes, 270 components, 280+ collections |
| `FORENSIC_02_DEPENDENCY_GRAPH.md` | Menu→Route→Component→API→DB trace |
| `FORENSIC_03_BUSINESS_PROCESS_MAP.md` | 10 E2E flows (P2P, O2C, M2S, Maklon, CMT, H2R, Asset, Marketing, Opname, Accessory) |
| `FORENSIC_04_DATA_ARCHITECTURE.md` | 12 cluster DB consolidation plan |
| `FORENSIC_05_UX_EFFICIENCY_REPORT.md` | Cognitive load, click depth, friction |
| `FORENSIC_06_DESIGN_SYSTEM_AUDIT.md` | UI consistency findings |
| `FORENSIC_07_INFORMATION_ARCHITECTURE.md` | Sidebar restructure (before/after) |
| `FORENSIC_08_DEAD_CODE_INVENTORY.md` | Files/routes/collections to remove |
| `FORENSIC_09_CONSOLIDATION_PLAN.md` | 14 concrete consolidations |
| `FORENSIC_10_FUTURE_STATE_ARCHITECTURE.md` | Target DDD 8 bounded contexts |
| `FORENSIC_11_MIGRATION_ROADMAP.md` | Execution P0→P3 (438 hours total) |

---

*See [SESSION_LOG.md](./SESSION_LOG.md) for full session history.*  
*See [domains/](./domains/) for per-domain technical reference.*
