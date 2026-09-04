# FORENSIC AUDIT — 10: FUTURE STATE ARCHITECTURE
## Target Arsitektur Ideal Pasca-Refactoring

**Lensa:** L7 Domain-Driven Design + L8 Data Architecture + L5 Human-Centered

---

## VISI

Membangun **Enterprise-Grade ERP** untuk CV. Dewi Aditya dengan:
- **1 Single Source of Truth** untuk setiap domain bisnis
- **Clear Domain Boundaries** sesuai DDD
- **Unified User Experience** dengan minimal cognitive load
- **Scalable** untuk growth bisnis (multi-factory, multi-brand)
- **Maintainable** dengan namespace yang clean

---

## 1. BOUNDED CONTEXTS (DDD)

Sistem dibagi menjadi **8 Bounded Contexts** yang clear:

```
┌─────────────────────────────────────────────┐
│           SHARED KERNEL (Cross-Cutting)               │
│   Users · Auth · Notifications · Counters · Audit Log  │
│   Activity Feed · Files · Search · AI Services         │
└──────────────────────────────────────────────────┘
         │         │        │        │         │
   ┌────┴────┐┐ ┌────┐ ┌─────┐ ┌────┴─────┐
   │ PRODUCTION  │ │INVTRY│ │FINANCE│ │HUMAN RES │
   │ (Manufacture)││(Stock)││ (AR/AP)││ (HRIS)  │
   └────┬─────┘┘ └──┬──┘ └──┬──┘ └───┬────┘
        │        │      │        │
   ┌────┴─────┐ ┌─┴───┐ ┌─┴──────┐ ┌──┴────┐
   │  MAKLON   │ │ RnD │  │MARKETING│ │COLLAB     │
   │ (B2B Orders)│ │     │  │         │ │(Comm+Work)│
   └───────────┘ └─────┘  └─────────┘ └──────────┘
```

### Context Definitions

#### CTX-1: Production (Manufacturing)
**Domain:** Mengelola pembuatan produk garment dari order hingga pengiriman.  
**Capabilities:** Orders, Work Orders, Bundles, Cutting, Sewing/CMT, Finishing, QC, Packing, Line Mgmt, Shift Handover, Andon, Pareto, FPY, Downtime, Predictive Maintenance.

**Aggregates:**
- `Order` (rahaza_orders)
- `WorkOrder` (rahaza_work_orders)
- `Bundle` (rahaza_bundles)
- `ProcessExecution` (rahaza_process_execution)
- `CMTJob` (dewi_cmt_jobs)

#### CTX-2: Inventory (Stock & Warehouse)
**Domain:** Mengelola fisik barang dari penerimaan ke pengeluaran.  
**Capabilities:** Items, Stock, Movements, GRN, Put-away, Pick, Opname, Returns, FG Tracking, Fabric Roll Tracking, Delivery Notes.

**Aggregates:**
- `Item` (rahaza_materials, with type field)
- `Stock` (rahaza_material_stock + rahaza_fg_inventory)
- `Movement` (rahaza_material_movements + rahaza_fg_movements)
- `PurchaseOrder` (rahaza_purchase_orders)
- `GoodsReceipt` (NEW: unified GRN with PO link)
- `OpnameCycle` (wh_opname2_cycles)
- `Location` (wh_buildings + wh_zones + wh_racks + wh_positions)

#### CTX-3: Finance (AR/AP/Accounting)
**Domain:** Mengelola transaksi keuangan, akuntansi, pelaporan.  
**Capabilities:** AR, AP, Cash, Bank Recon, Payments, Invoices, COA, Journals, GL, Reports (P&L, BS, Cash Flow), Budget, Fixed Assets.

**Aggregates:**
- `Invoice` (AR: rahaza_ar_invoices; AP: rahaza_ap_invoices)
- `Payment` (rahaza_ar_receipts + rahaza_ap_payments)
- `Journal` (rahaza_journal_entries + rahaza_journal_lines)
- `Account` (rahaza_coa + rahaza_coa_accounts)
- `Period` (rahaza_periods)
- `FixedAsset` (rahaza_fixed_assets + rahaza_depr_schedules)

#### CTX-4: Human Resources (HRIS)
**Domain:** Mengelola karyawan dari rekrutmen hingga exit.  
**Capabilities:** Employees, Org Chart, Recruitment, Onboarding, Attendance, Leave, Overtime, Shift, KPI, Performance Reviews, Salary, Payroll, LMS, AI Insights.

**Aggregates:**
- `Employee` (rahaza_employees)
- `Attendance` (rahaza_attendance + rahaza_attendance_events)
- `Leave` (rahaza_leave_requests + balances)
- `PerformanceCycle` (hris_cycles + assignments + reviews)
- `Payroll` (rahaza_payroll_runs + payslips)
- `Recruitment` (dewi_recruitment_jobs + candidates)

#### CTX-5: Maklon (B2B Client Orders)
**Domain:** Mengelola order dari klien eksternal (Maklon).  
**Capabilities:** Client Mgmt, PO (Maklon), BOM, Sampling, Production tracking (via Production CTX), QC, Dispatch, Billing, HPP.

**Aggregates:**
- `MaklonClient` (dewi_maklon_clients)
- `MaklonPO` (dewi_maklon_pos) — SSOT
- `MaklonSample` (dewi_maklon_samples)
- `MaklonInvoice` (dewi_maklon_invoices)
- `MaklonHPP` (dewi_maklon_hpp)

#### CTX-6: RnD (Research & Design)
**Domain:** Mengelola desain, sampling, tech pack, costing.  
**Capabilities:** Styles, Variants, Patterns, Materials Research, Sample Requests, Revisions, Tech Pack, HPP Calculator, Analytics.

**Aggregates:**
- `Style` (dewi_rnd_styles)
- `Sample` (dewi_rnd_sample_requests)
- `TechPack` (dewi_rnd_tech_packs)
- `Variant` (dewi_rnd_variants)

#### CTX-7: Marketing (Multi-Channel Sales)
**Domain:** Mengelola akun marketplace, sales, kampanye, KOL.  
**Capabilities:** Platform Accounts, Sales Tracking, Orders, KOL/Creator Mgmt, Content Calendar, Discounts, Product Launch, Live Sessions, Ads, AI Insights, Reports.

**Aggregates:**
- `PlatformAccount` (marketing_platform_accounts)
- `SalesData` (marketing_sales_data)
- `MarketingOrder` (marketing_orders)
- `KOLCreator` (marketing_kol_creators + marketing_creator_*)
- `Campaign` (marketing_discounts + marketing_product_launches)
- `LiveHost` (marketing_livehosts + marketing_livehost_*)

#### CTX-8: Collaboration (Comm + Workspace + Learning + Assets)
**Domain:** Inter-employee communication, knowledge sharing, asset tracking.  
**Capabilities:** Chat, Channels, Messages, Workspace Documents (spreadsheet), LMS, Study Groups, Assets (operational), Activity Feed.

**Aggregates:**
- `Conversation` (comm_conversations + comm_messages)
- `Document` (workspace_documents)
- `Course` (dewi_lms_courses + enrollments)
- `Asset` (dewi_assets + assignments + maintenance)

---

## 2. SHARED KERNEL

Layanan cross-cutting yang dipakai semua bounded contexts:

### 2.1 Identity & Access
```
/api/auth/*
  - Login (employee, client, kol)
  - JWT issuance
  - Role permissions
  - RBAC matrix
DB: users + rahaza_users + role_permissions + roles
```

### 2.2 Notifications (UNIFIED)
```
/api/notifications/*
  - Multi-channel: in-app, email, push
  - Type-based routing
  - Mark read/unread
  - Subscription preferences
DB: notifications (unified) + push_subscriptions + reminders
```

### 2.3 Audit & Activity
```
/api/audit/*           → immutable audit trail
/api/activity-feed/*   → user-facing activity feed
DB: rahaza_audit_logs + activity_logs
```

### 2.4 Counters / Sequences
```
/api/counters/next?namespace=PO
DB: counters (unified with namespace)
```

### 2.5 Files & Attachments
```
/api/files/*
  - Upload (with auth)
  - Stream/download
  - Multi-tenant storage
DB: attachments
```

### 2.6 Search (Global)
```
/api/search/global?q=...
  - Cross-context search (modules + records)
  - Indexed fields per aggregate
Uses: aggregations across contexts
```

### 2.7 AI Services
```
/api/ai/*
  - Chat (LLM proxy)
  - Insights (domain-specific)
  - Cost monitoring
DB: rahaza_ai_chat_history + rahaza_ai_audit_logs + rahaza_ai_usage_logs
```

---

## 3. CONTEXT INTERACTIONS (Anti-Corruption Layer)

Komunikasi antar contexts via well-defined APIs, NOT direct DB access:

```
Maklon CTX → "Create Production WO" → Production CTX
   API: POST /api/production/work-orders { source: 'maklon', source_id: ... }

Production CTX → "Issue Material" → Inventory CTX
   API: POST /api/inventory/issues { work_order_id: ..., items: [...] }

Inventory CTX → "Update Stock Movement" → Inventory CTX (internal)
   Direct DB write OK within same context

Finance CTX ← "AR Invoice Generated" ← Production CTX
   Event: "shipment.completed" → Finance subscribes → auto-create AR draft

Marketing CTX → "Online Order Received" → Production CTX (for stock check)
   API: GET /api/production/stock-availability?items=...
   If stock low: API POST /api/production/work-orders

HR CTX → "Employee Skill Update" → Production CTX (line assignment eligibility)
   Event: "employee.skill.added" → Production listener updates eligibility
```

**Pattern:** Event-driven untuk async, API call untuk sync. **No direct cross-context DB query.**

---

## 4. UNIFIED USER EXPERIENCE LAYER

### 4.1 Global Workspace (Entry Point)
```
After login → "Workspace Saya" sebagai default page
  - Cross-context inbox (Approvals dari HR, Finance, Production)
  - Today's tasks (cross-context)
  - Quick stats (role-based)
  - Recent items (last viewed across all portals)
  - Favorites & shortcuts
  - AI digest of important things
```

### 4.2 Per-Portal Optimized
Lihat FORENSIC_07 untuk detail. Setiap portal:
- Max 25 sidebar items (vs current 30-38)
- Consistent naming (glossary-driven)
- No legacy/badge clutter
- Task-oriented grouping

### 4.3 Cross-Portal Shortcuts
- Cross-context shortcuts di Workspace (e.g., HR Manager dapat akses Marketing dashboard summary)
- Role-based portal pinning

---

## 5. DATA MODEL OPTIMIZATIONS

### 5.1 SSOT Achievement
Setiap entitas bisnis hanya 1 collection authoritative:
- Material Master = `rahaza_materials` (with type field)
- Stock = `rahaza_material_stock`
- Stock Movement Log = `rahaza_material_movements`
- Customer = `rahaza_customers`
- Maklon Client = `dewi_maklon_clients`
- CMT Partner = `dewi_cmt_partners`
- Employee = `rahaza_employees`
- Order = `rahaza_orders` (Sales/Production)
- Maklon PO = `dewi_maklon_pos`
- Marketplace Order = `marketing_orders`
- Work Order = `rahaza_work_orders`
- Bundle = `rahaza_bundles`
- Purchase Order = `rahaza_purchase_orders`
- AR Invoice = `rahaza_ar_invoices`
- AP Invoice = `rahaza_ap_invoices`
- Payment Out = `rahaza_ap_payments`
- Payment In = `rahaza_ar_receipts`
- Journal = `rahaza_journal_entries`
- KOL = `marketing_kol_creators`
- Notification = `notifications` (unified)
- Counter = `counters` (unified)

### 5.2 Specialized Side Tables (justified)
Kolesi yang tetap terpisah karena alasan domain:
- `accessory_loans` (unique: peminjaman aksesoris ke internal)
- `wh_fabric_rolls` (specialized: per-roll tracking)
- `dewi_maklon_hpp` (specialized: maklon costing)
- `rahaza_fixed_assets` (specialized: depreciable assets)
- `marketing_livehost_*` cluster (specialized: live commerce)

### 5.3 Audit & Snapshot Collections (preserved)
- All `*_history`, `*_snapshots`, `*_log` collections
- All `*_audit` collections
- These are append-only and serve compliance/audit purposes

---

## 6. NAMING CONVENTION (Target State)

### Phase Out Sequence (Long-term)
```
Phase 1 (Current):     rahaza_*, dewi_*, wh_*, wms_*, acc_*, marketing_*, hr_*, hris_*, generic
Phase 2 (6 months):    production_*, inventory_*, finance_*, hr_*, marketing_*, maklon_*, rnd_*, collab_*
Phase 3 (12 months):   Same as Phase 2, with all `rahaza_*` and `dewi_*` migrated/aliased
```

Migrasi gradual dengan **collection alias** untuk backward compat:
```python
# Backend supports both names during transition
MATERIAL_COLLECTION = "rahaza_materials"  # legacy
MATERIAL_COLLECTION_NEW = "inventory_items"  # future
# Until full migration, write to both, read from new with fallback to old
```

---

## 7. PERFORMANCE & SCALABILITY

### 7.1 Indexes
- Verify all `_id` UUID indexes
- Add compound indexes for common queries:
  - `(employee_id, date)` on attendance
  - `(work_order_id, process_code)` on process execution
  - `(customer_id, status)` on orders
  - `(client_id, status)` on maklon POs
  - `(account_id, date)` on marketing sales

### 7.2 Caching Strategy
- Redis for: master data lookups, session data, rate limits
- In-memory cache for: COA tree, role permissions

### 7.3 Background Jobs
- APScheduler sudah ada — expand usage:
  - Daily KPI calc
  - Inventory reorder alerts
  - Marketing daily report aggregation
  - Payroll pre-run validation

---

## 8. TECHNOLOGY UPGRADES (Optional)

### Short-term (no urgent)
- Migrate ke FastAPI 1.0 jika sudah release
- Upgrade Motor (MongoDB async) ke latest
- Tailwind CSS v4 (when stable)

### Long-term (consider)
- Event sourcing via message queue (RabbitMQ/Kafka) untuk audit-heavy contexts
- Read-replica MongoDB untuk reports
- Elasticsearch untuk search global
- Multi-tenant architecture (if multi-factory expansion)

---

## 9. TESTING STRATEGY

### Current State
- Backend tests: `backend_test.py` (1 monolithic file)
- Frontend tests: minimal

### Target State
- Backend: pytest dengan per-context test files
- Frontend: Vitest/Jest untuk component tests + Playwright untuk E2E
- Integration tests untuk cross-context flows
- Coverage target: 60%+ for critical paths

---

## 10. SECURITY & COMPLIANCE

### Current Strength
- JWT-based auth
- Role permissions matrix
- Rate limiting (`rate_limit_buckets`)
- Audit logs
- WebAuthn for HR attendance

### Improvements
- 2FA for critical actions
- Field-level encryption for PII (salary, bank info)
- GDPR-compliant data export/delete (employee right to data)
- SOC2 audit-ready logging

---

## 11. UI/UX TARGET

### Design Tokens (Existing)
Sudah ada CSS variables. **TARGET:** 100% token usage (no hardcoded colors).

### Component Library Target
- Shadcn/UI 100% adoption
- Custom components only when truly unique
- Storybook untuk documentation

### Accessibility
- WCAG AA compliance minimum
- All `data-testid` for testability
- Keyboard navigation full coverage

---

## 12. ARCHITECTURE BENEFITS POST-REFACTOR

| Aspect | Before | After |
|--------|--------|-------|
| Sidebar items | 205 | ~140 |
| Backend route files | 194 | ~150 |
| Frontend components | 270 | ~220 |
| MongoDB collections | 280 | ~230 |
| Avg time-to-task | 3.6x optimal | 1.5x optimal |
| Cognitive load | High | Medium-Low |
| Code maintainability | 5/10 | 8/10 |
| Onboarding new dev | 4 weeks | 2 weeks |
| Bug surface area | High | Reduced ~30% |
| Performance (avg API) | Variable | Consistent |
| Scalability | Limited | Multi-factory ready |

---

## 13. ARCHITECTURE DIAGRAM (Simplified)

```
┌───────────────────────────────────────────────────────┐
│                       USER (Browser)                            │
└──────────────────────────────┬───────────────────────────────┘
                          │ HTTPS
                          ▼
┌───────────────────────────────────────────────────────┐
│           React Frontend (PortalShell + Modules)                │
│         + Global Workspace (entry) + Cross-portal nav           │
└──────────────────────────────┬───────────────────────────────┘
                          │ /api/* (REST + WebSocket)
                          ▼
┌───────────────────────────────────────────────────────┐
│                FastAPI Backend (server.py)                      │
│   ┌───────────────────────────────────────────────┐ │
│   │  Middleware: Auth (JWT) · Logging · Rate Limit         │ │
│   └───────────────────────────────────────────────┘ │
│                                                                 │
│   ┌───────────────────────────────────────────────┐ │
│   │  SHARED KERNEL                                          │ │
│   │  /api/auth /notifications /counters /files /search /ai  │ │
│   └───────────────────────────────────────────────┘ │
│                                                                 │
│   ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐                 │
│   │Producti│ │Inventory│ │Finance  │ │  HR    │                 │
│   └─────────┘ └──────────┘ └─────────┘ └───────┘                 │
│                                                                 │
│   ┌───────┐ ┌────┐ ┌──────────┐ ┌──────────┐                │
│   │Maklon │ │ RnD│ │Marketing│ │Collaboration│                  │
│   └───────┘ └────┘ └──────────┘ └──────────┘                  │
└────────────────────────────┬───────────────────────────────────┘
                          │ Motor (async MongoDB driver)
                          ▼
┌───────────────────────────────────────────────────────┐
│                       MongoDB (~230 collections)                │
│   Master Data · Transactions · Logs · Audit · Counters · Files │
└───────────────────────────────────────────────────────┘
                          │ (read-only)
                          ▼
┌───────────────────────────────────────────────────────┐
│  External Services (via Integrations)                           │
│  OpenAI · Email · Push (FCM) · ZKTeco (HR Attendance)            │
│  Marketplace APIs (Shopee/Tokopedia/TikTok for Marketing CTX)    │
└───────────────────────────────────────────────────────┘
```

---

## 14. SUMMARY

Future-state architecture mengubah sistem dari:
- **Monolith with feature silos** (current)
- **Multiple namespaces per domain** (rahaza/dewi/wms/marketing mixing)
- **3 generations of warehouse code coexisting**
- **180+ sidebar items**

Menjadi:
- **Domain-driven dengan 8 bounded contexts**
- **Shared kernel cross-cutting**
- **Single source of truth per entity**
- **140 sidebar items dengan task-oriented grouping**
- **Event-driven inter-context communication**
- **Scalable & maintainable**

Lihat `FORENSIC_11_MIGRATION_ROADMAP.md` untuk urutan eksekusi.
