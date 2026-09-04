# Phase 3.4 Data Hygiene - Cleanup Backup Log
**Date:** 27 Mei 2026
**Strategy:** Conservative (Opsi A)
**Total collections to drop:** 30

## Collections to Drop (Conservative - Safe)

### Category 1: Marketing Old Features (15 collections)
- `marketing_kol_creators` - KOL creator management (deprecated, moved to different structure)
- `marketing_kol_login_attempts` - Login tracking for KOL (unused)
- `marketing_livehost_scripts` - Live host scripts (deprecated feature)
- `marketing_livehost_shifts` - Live host shift scheduling (deprecated)
- `marketing_livehost_training` - Training records (deprecated)
- `marketing_livehost_training_progress` - Training progress (deprecated)
- `marketing_livehosts` - Live host data (deprecated)
- `marketing_live_sessions` - Live session tracking (deprecated)
- `marketing_catalog_items` - Catalog items (deprecated)
- `marketing_catalogs` - Catalogs (deprecated)
- `marketing_platform_accounts` - Platform account linking (deprecated)
- `marketing_sales_data` - Sales data aggregation (deprecated)
- `marketing_ads_data` - Ads performance data (deprecated)
- `marketing_account_health` - Account health metrics (deprecated)
- `marketing_reviews` - Product reviews (unused)

### Category 2: FX/Multi-Currency Unused (2 collections)
- `fx_rates` - Foreign exchange rates (multi-currency not implemented)
- `fx_revaluation_runs` - FX revaluation runs (multi-currency not implemented)

### Category 3: Communication/Chat Unused (5 collections)
- `comm_channels` - Communication channels (chat feature not implemented)
- `comm_conversations` - Conversations (chat feature not implemented)
- `comm_messages` - Messages (chat feature not implemented)
- `comm_read_receipts` - Read receipts (chat feature not implemented)
- `marketing_complaints` - Customer complaints (moved to different system)

### Category 4: Study Groups Unused (1 collection)
- `study_groups` - Study groups feature (not implemented)

### Category 5: Login Attempts Old/Duplicate (2 collections)
- `login_attempts` - Old login tracking (consolidated to user audit)
- `client_login_attempts` - Client login tracking (deprecated)

### Category 6: Old Payroll (1 collection)
- `payroll_entries` - Old payroll structure (migrated to `rahaza_payslips`)

### Category 7: Generic Unused (4 collections)
- `attachments` - Generic attachment storage (not used, files stored elsewhere)
- `portal_quick_links` - Quick links feature (not implemented)
- `rate_limit_buckets` - Rate limiting (not implemented at DB level)
- `permissions` - Old permissions table (moved to role-based)

---

## Collections to KEEP (Not dropping)

### Active Features (Recently Implemented)
- `rahaza_leave_requests` - Leave management (Task 2.x, new feature)
- `rahaza_leave_types` - Leave types config
- `rahaza_material_reservations` - Material reservation (Task 1.1)
- `rahaza_material_issues` - Material issues/returns
- `approval_chains` - Multi-level approval config (Task 2.4)

### Maklon Module (Large module ready for use)
- All `dewi_maklon_*` collections (15 total) - Keep for future Maklon operations

### RnD/Sample Module (Active development area)
- All `dewi_rnd_*` collections (5 total) - Keep for R&D operations

### Asset Management (Future feature)
- `da_assets`, `da_asset_assignments` - Asset tracking feature

### Security/Auth (Future features)
- `rahaza_webauthn_credentials`, `rahaza_webauthn_challenges` - WebAuthn 2FA
- `push_subscriptions` - PWA push notifications

### L&D/Training (Future features)
- `dewi_lms_courses`, `dewi_lms_enrollments`, `dewi_lms_materials` - LMS

---

## Backup Strategy
- Collections are empty (0 documents), no data loss risk
- This document serves as audit trail
- Can recreate collections via backend seeding if needed

## Risk Assessment
- **Risk Level:** LOW
- **Reason:** All collections are empty, clearly deprecated/unused
- **Rollback:** Can recreate via backend migrations if needed
- **Impact:** Cleanup 30/121 empty collections (24.8%)

## Verification Checklist
- [ ] Backend compile successful
- [ ] Frontend compile successful
- [ ] Services running normally
- [ ] No errors in logs
- [ ] Key features tested (approval, notifications, opname)
