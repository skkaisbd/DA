# Next Agent Instructions — DA47 ERP

> **Quick Start Guide untuk Agent Baru**  
> **Last Updated:** 2026-05-27 (Documentation Split Session)

---

## ⚡ Quick Start (3 Steps)

### Step 1: Baca Mandatory Docs
```
1. /app/AGENT_DEVELOPMENT_RULES.md    — Rules WAJIB (anti-tech-debt)
2. /app/memory/PRD.md                  — Index + current state
3. /app/docs/SYSTEM_ARCHITECTURE.md   — Stack + SSOT + auth
4. /app/NEXT_AGENT_INSTRUCTIONS.md    — (this file)
```

### Step 2: Cek Domain Yang Relevan
```
/app/docs/domains/HR_PAYROLL.md       — HR, payroll, KPI, leave
/app/docs/domains/PRODUCTION.md       — WO, bundles, cutting, QC
/app/docs/domains/FINANCE.md          — AR/AP, P2P, GL, bank recon
/app/docs/domains/WAREHOUSE_WMS.md    — WMS, opname, fabric rolls
/app/docs/domains/MAKLON_CMT.md       — CMT, maklon PO, billing
/app/docs/domains/MARKETING_KOL.md    — Marketplace, KOL, LiveHost
/app/docs/domains/ASSETS_RND.md       — Asset register, RnD, HPP
```

### Step 3: Verify System Running
```bash
curl http://localhost:8001/api/health
# Expected: {"status":"ok","db":"connected",...}

# Login test
curl -X POST http://localhost:8001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@garment.com","password":"Admin@123"}'
# Expected: {"token":"eyJ...", ...}
```

---

## 📊 Current System State

| Item | Value |
|---|---|
| **Session** | #11.20 (latest) |
| **Date** | 2026-05-27 |
| **Test Iteration** | 92 (100% pass) |
| **Endpoints** | 1,485 |
| **Frontend Modules** | 279 (lazy-loaded) |
| **Bundle Size** | 222kB |
| **Health Score** | 100% (39/39 flows) |
| **All Tech Debt** | ✅ COMPLETE |

---

## 🏳️ System State: ALL COMPLETE

Semua major tech debt phases sudah selesai:
- ✅ **P0** — Broken menus, sidebar cleanup
- ✅ **P1** — Data consolidation (Accessories, Maklon, Toko, P2P)
- ✅ **P2** — 14 workflow consolidations
- ✅ **P3** — Opname, Counters, Notifications SSOT
- ✅ **UI-UX** — Bundle optimization, hash routing, Jest 204 tests
- ✅ **Approval Chains** — 11 chains, 8 entity types
- ✅ **Universal Scan** — FAB, 7 entity types
- ✅ **PR→PO Workflow** — Full Procure-to-Pay
- ✅ **Docs** — PRD.md split to per-domain docs

---

## 🔧 Task Options for Next Session

### Option 1: Business Feature Request 🌟
**Recommended if user has specific business need**  
Examples:
- Tambah modul baru (misal: Fleet Management, Customer CRM)
- Tambah fitur ke modul existing (misal: export PDF per-modul)
- Integration eksternal (WhatsApp, Shopee API, BPJS API)
- Dashboard tambahan atau laporan baru

**Start with:** Tanya user fitur apa yang dibutuhkan

### Option 2: Performance & Monitoring 📊
**Recommended for production readiness**
- Tambah proper error tracking (Sentry integration)
- Database query optimization (slow queries)
- API rate limiting per user/role
- Health check dashboard yang lebih detail

### Option 3: Testing & Quality 🧪
**Recommended for stability**
- Backend pytest formal test suite
- Frontend RTL coverage tambahan
- Load testing (k6 atau locust)
- API contract testing

### Option 4: Documentation 📝
**Recommended for team onboarding**
- OpenAPI spec auto-generation dari FastAPI
- Per-module README files
- Developer onboarding guide
- API changelog

### Option 5: DevOps & Security 🔒
**Recommended for production deployment**
- Docker Compose production setup
- Environment secrets management
- HTTPS + TLS configuration
- Database backup automation
- CI/CD pipeline

---

## ⚠️ Anti-Patterns to Avoid

1. **JANGAN buat collections baru** tanpa cek `/app/AGENT_DEVELOPMENT_RULES.md`
2. **JANGAN hardcode** apapun — selalu dari env vars
3. **JANGAN overwrite** `/app/backend/.env` atau `/app/frontend/.env`
4. **JANGAN** duplikasi logic yang sudah ada di SSOT helpers:
   - Counters: gunakan `utils/counters.py` `next_counter()`
   - Notifications: gunakan `utils/notif_unified.py` `notif_insert()`
5. **JANGAN skip** membaca domain doc sebelum modifikasi domain tersebut
6. **JANGAN** buat route baru tanpa register di `server.py`

---

## 📦 SSOT Reference

Selalu gunakan SSOT collections ini (BUKAN duplikasi baru):

| Domain | SSOT Collection | Discriminator |
|---|---|---|
| Counters | `counters` | `namespace` |
| Notifications | `notifications` | `type` |
| Materials | `rahaza_materials` | `type` |
| Accessory Requests | `dewi_accessory_requests` | `request_type` |
| Maklon PO | `dewi_maklon_pos` | — |
| Marketing Accounts | `marketing_platform_accounts` | `platform` |
| Opname | `wms_opname2_sessions` | `scope` |

---

## 🔑 Auth & Access

```
Production URL: https://da37-cmt-bridge.preview.emergentagent.com
Admin:          admin@garment.com / Admin@123
JWT Header:     Authorization: Bearer <token>
Expiry:         24 hours
```

---

## 📁 Documentation Structure

```
/app/
├── memory/
│   └── PRD.md                    ← YOU ARE HERE (index)
├── docs/
│   ├── SYSTEM_ARCHITECTURE.md    ← Tech stack + SSOT + architecture
│   ├── SESSION_LOG.md            ← Full session history (35+ sessions)
│   └── domains/
│       ├── HR_PAYROLL.md
│       ├── PRODUCTION.md
│       ├── FINANCE.md
│       ├── WAREHOUSE_WMS.md
│       ├── MAKLON_CMT.md
│       ├── MARKETING_KOL.md
│       └── ASSETS_RND.md
├── AGENT_DEVELOPMENT_RULES.md    ← WAJIB BACA: anti-tech-debt rules
├── NEXT_AGENT_INSTRUCTIONS.md    ← THIS FILE
├── FORENSIC_00_EXECUTIVE_SUMMARY.md → FORENSIC_11_MIGRATION_ROADMAP.md
├── test_reports/                 ← iteration_*.json test results
└── backend/ & frontend/          ← Application source code
```

---

## 🤝 For Users (Business Owners)

Sistem ERP sudah **LENGKAP** dan **STABIL**. Semua P0→P3 tech debt selesai.

Session selanjutnya bisa fokus ke:
- 🔧 Fitur bisnis baru sesuai kebutuhan operasional
- 📊 Integrasi dengan sistem eksternal (marketplace API, dll)
- 📱 Mobile-responsive improvements
- 🤖 AI/ML features tambahan

**Ceritakan kebutuhan Anda dan agent akan membantu!**
