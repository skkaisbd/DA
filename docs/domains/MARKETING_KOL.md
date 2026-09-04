# Marketing & KOL Domain — Technical Reference

> **Portal:** Marketing (`marketing-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready; P1.D Toko migration complete

---

## 1. Business Overview

Covers end-to-end e-commerce and marketing operations for CV. Dewi Aditya:
- Multi-platform marketplace account management (Shopee, TikTok, Tokopedia, Instagram, Lazada)
- Daily sales data entry per account
- KOL (Key Opinion Leader) / Creator management
- LiveHost management & shift scheduling
- Marketing orders & fulfillment
- Product catalog & inventory
- Marketing reports & AI insights
- Campaign & content management
- Customer complaints & returns
- Webhooks & integrations

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? | Notes |
|---|---|---|---|
| `marketing_platform_accounts` | Marketplace accounts | ✅ SSOT | Replaces legacy `dewi_toko_accounts` |
| `marketing_sales_data` | Daily sales per account | ✅ SSOT | |
| `marketing_kol_creators` | KOL/creator profiles | ✅ SSOT | Merged from multiple sources |
| `marketing_livehost_hosts` | LiveHost profiles | ✅ SSOT | |
| `marketing_livehost_shifts` | LiveHost shift records | ✅ SSOT | |
| `marketing_orders` | Marketing (online) orders | ✅ SSOT | |
| `marketing_catalog_items` | Product catalog | ✅ SSOT | |
| `marketing_targets` | Monthly sales targets | ✅ SSOT | |
| `marketing_tasks` | Marketing task management | ✅ SSOT | |
| `marketing_campaigns` | Marketing campaigns | ✅ SSOT | |
| `marketing_content_calendar` | Content calendar | ✅ SSOT | |
| `marketing_complaints` | Customer complaints | ✅ SSOT | |
| `marketing_returns` | Online order returns | ✅ SSOT | |
| `marketing_reviews` | Product reviews | ✅ SSOT | |
| `marketing_discounts` | Discount/promo management | ✅ SSOT | |
| `marketing_ads` | Paid ads tracking | ✅ SSOT | |
| `marketing_product_launches` | Product launch tracking | ✅ SSOT | |
| `marketing_samples` | Marketing samples | ✅ SSOT | |
| `marketing_live_sessions` | Live streaming sessions | ✅ SSOT | |
| `marketing_alerts` | Marketing alert configs | ✅ SSOT | |
| `marketing_webhooks` | Webhook configurations | ✅ SSOT | |
| `marketing_integration_settings` | API integration settings | ✅ SSOT | |

**Deprecated (empty, P1.D migration complete):**
- `dewi_toko_accounts` — migrated to `marketing_platform_accounts`
- `dewi_toko_sales` — migrated to `marketing_sales_data`
- `dewi_toko_channels` — removed from sidebar
- `dewi_toko_pricing` — removed from sidebar
- `dewi_kol_creators` — migrated to `marketing_kol_creators`
- `dewi_kol_performances` — migrated
- `dewi_kol_contracts` — migrated

---

## 3. Key API Endpoints

### Platform Accounts
```
GET  /api/marketing/accounts          — list platform accounts
POST /api/marketing/accounts          — create account
GET  /api/marketing/accounts/{id}     — account detail + health score
PUT  /api/marketing/accounts/{id}     — update account
GET  /api/marketing/accounts/{id}/health — health metrics
GET  /api/marketing/accounts/active   — active accounts summary
```

### Sales Data
```
GET  /api/marketing/sales             — list sales records
POST /api/marketing/sales             — enter daily sales
GET  /api/marketing/sales/by-account  — sales per account
GET  /api/marketing/sales/performance — sales performance report
GET  /api/marketing/targets           — monthly targets
POST /api/marketing/targets           — set target
```

### KOL / Creator
```
GET  /api/marketing/kol/creators      — list creators
POST /api/marketing/kol/creators      — create creator profile
GET  /api/marketing/kol/creators/{id} — creator detail
PUT  /api/marketing/kol/creators/{id} — update profile
GET  /api/marketing/kol/leaderboard   — performance leaderboard
GET  /api/marketing/kol/portal        — creator self-portal
POST /api/marketing/kol/operations    — KOL content operations
```

### LiveHost
```
GET  /api/marketing/livehost/hosts    — list hosts
POST /api/marketing/livehost/hosts    — create host
GET  /api/marketing/livehost/shifts   — list shifts
POST /api/marketing/livehost/shifts   — schedule shift
GET  /api/marketing/livehost/portal   — host self-portal
GET  /api/marketing/livehost/analytics — performance analytics
GET  /api/marketing/livehost/live-sessions — active live sessions
```

### Orders & Catalog
```
GET  /api/marketing/orders            — marketing orders
POST /api/marketing/orders            — create order
GET  /api/marketing/catalog           — product catalog
POST /api/marketing/catalog           — add catalog item
GET  /api/marketing/catalog/stock     — catalog stock levels
```

### Reports & AI
```
GET  /api/marketing/reports/summary   — marketing summary report
GET  /api/marketing/reports/by-platform — breakdown by platform
GET  /api/marketing/ai/insights       — AI marketing insights
GET  /api/marketing/ai/content-tools  — AI content generation tools
POST /api/marketing/ai/advanced       — advanced AI analysis
```

### Campaigns & Content
```
GET  /api/marketing/campaigns         — list campaigns
POST /api/marketing/campaigns         — create campaign
GET  /api/marketing/content-calendar  — content calendar
POST /api/marketing/product-launches  — product launch
```

### Complaints & Returns
```
GET  /api/marketing/complaints        — list complaints
POST /api/marketing/complaints        — create complaint
GET  /api/marketing/returns           — list returns
POST /api/marketing/returns           — process return
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `MarketingDashboard.jsx` | `marketing-dashboard` | Marketing overview + account cards |
| `AccountManagementModule.jsx` | `marketing-accounts` | Account CRUD |
| `SalesDataEntryModule.jsx` | `marketing-sales-entry` | Daily sales entry |
| `KOLCreatorModule.jsx` | `marketing-kol` | KOL/Creator management |
| `LiveHostModule.jsx` | `marketing-livehost` | LiveHost management (refactored S#11) |
| `CatalogManagementModule.jsx` | `marketing-catalog` | Product catalog |
| `MarketingOrdersModule.jsx` | `marketing-orders` | Online orders |
| `MarketingReportsModule.jsx` | `marketing-reports` | Consolidated reports hub |
| `ContentCalendarModule.jsx` | `marketing-content-calendar` | Content calendar |
| `MarketingComplaintsModule.jsx` | `marketing-complaints` | Complaints |
| `MarketingReturnsModule.jsx` | `marketing-returns` | Returns |
| `MarketingAIInsightsModule.jsx` | `marketing-ai` | AI insights |
| `MarketingWebhooksModule.jsx` | `marketing-webhooks` | Webhook management |

### Active Account Bar
`ActiveAccountBar.jsx` — appears at top of Marketing portal, allows switching active account.  
`useActiveMarketingAccount.js` — hook, stores active account in `localStorage`.

---

## 5. Business Flows

### Daily Sales Entry
```
Staff selects active platform account
  → Enters daily sales (orders, GMV, returns)
  → Data stored in marketing_sales_data
  → Health score auto-recalculated (7-day trend)
  → Targets comparison updated in dashboard
```

### KOL Campaign Flow
```
KOL created in system
  → Assigned to platform account(s)
  → Content calendar entry created
  → KOL posts content
  → Performance tracked (views, conversions)
  → Leaderboard updated
  → Monthly performance review
```

### LiveHost Shift Flow
```
Host profile created
  → Assigned to platform accounts
  → Shift scheduled (livehost_shifts)
  → Live session starts (livehost_live_sessions)
  → Real-time analytics tracked
  → Session ends → performance recorded
  → Host notification via SSE
```

---

## 6. Account Health Score

Auto-calculated on each account based on:
- 7-day sales trend (vs target)
- Return rate
- Response rate
- Review average
- Stock coverage

Result stored in `marketing_platform_accounts.health_score` (0-100).

---

## 7. P1.D — Toko Migration (Complete)

Session #1 P1.D & Phase B/C:
- All `dewi_toko_*` data migrated → `marketing_*`
- Frontend cutover: all Toko module routes now point to Marketing modules
- Legacy sidebar items removed: `toko-channels`, `toko-pricing`
- Adapter: `_toko_adapter.py` for any legacy reads

---

## 8. Key Backend Files

| File | Purpose |
|---|---|
| `routes/marketing_accounts.py` | Platform account CRUD |
| `routes/marketing_account_health_routes.py` | Health score calculation |
| `routes/marketing_sales.py` | Sales data entry |
| `routes/marketing_kol.py` | KOL management |
| `routes/marketing_kol_creators.py` | Creator profiles |
| `routes/marketing_kol_leaderboard.py` | KOL leaderboard |
| `routes/marketing_kol_portal.py` | KOL self-portal |
| `routes/marketing_livehost_hosts.py` | Host management |
| `routes/marketing_livehost_shifts.py` | Shift scheduling |
| `routes/marketing_livehost_analytics.py` | LiveHost analytics |
| `routes/marketing_catalog_items.py` | Catalog management |
| `routes/marketing_reports.py` | Marketing reports |
| `routes/marketing_ai_insights_routes.py` | AI insights |
| `routes/marketing_ai_content_tools.py` | AI content tools |
| `routes/marketing_complaints_routes.py` | Complaints |
| `routes/marketing_webhooks.py` | Webhook management |
| `routes/marketing_dashboard.py` | Dashboard aggregations |
| `routes/_toko_adapter.py` | Legacy toko adapter |

---

## 9. Recent Relevant Sessions

- **#11.16 Phase C (2026-05-25):** KOL collection migration via deprecation stub
- **Session #1 P1.D (2026-05-23):** Legacy Toko migration → marketing_*
- **Session #1 P1.D Phase B/C (2026-05-23):** Frontend cutover + route removal
- **Session #0 (2026-05-22):** Marketing seed data (5 accounts, 10 catalog, 6 KOL, 150 sales, 50 orders)

---

## 10. Demo Seed Data

Seed script: `backend/scripts/seed_marketing_demo.py`

Seeded data:
- 5 Platform Accounts: Shopee, TikTok, Tokopedia, Instagram, Lazada
- 10 Catalog Items
- 6 KOL Creators (2 Macro / 2 Mid / 2 Micro)
- 150 Daily Sales Records (30 days × 5 platforms)
- 5 Monthly Targets
- 50 Marketing Orders
