# FORENSIC AUDIT — 04: DATA ARCHITECTURE
## DB Collection Classification & SSOT Decisions

**Lensa:** L8 Data Architecture Audit

---

## METODOLOGI KLASIFIKASI

Setiap collection diklasifikasi menjadi salah satu dari:
- **AUTHORITATIVE** — Single Source of Truth, harus dipertahankan
- **DERIVED/VIEW** — Aggregated/computed dari collection lain
- **DUPLICATE** — Memiliki collection lain dengan tujuan sama
- **ORPHAN** — Tidak ada route yang menulis ke sini lagi
- **LEGACY** — Sistem lama, ada replacement modern
- **KEEP** — Spesifik untuk satu use case, tidak perlu diubah

---

## CLUSTER 1: ACCESSORY (🔴 CRITICAL CONSOLIDATION)

### Current State (4 systems)

| Collection | Type | Routes | Recommendation |
|------------|------|--------|----------------|
| `rahaza_materials` (filter type=accessory) | AUTHORITATIVE | `rahaza_inventory.py`, `dewi_cmt.py`, etc. | **KEEP as SSOT** |
| `rahaza_material_stock` (filter accessory) | AUTHORITATIVE | (multiple) | **KEEP as SSOT for stock** |
| `rahaza_material_movements` (filter accessory) | AUTHORITATIVE | (multiple) | **KEEP as SSOT for log** |
| `acc_items` | DUPLICATE | `dewi_accessories_full.py` | **MIGRATE → `rahaza_materials`** |
| `acc_stock_movements` | DUPLICATE | `dewi_accessories_full.py` | **MIGRATE → `rahaza_material_movements`** |
| `acc_purchase_requests` | UNIQUE FEATURE | `dewi_accessories_full.py` | **PRESERVE** (procurement-specific) |
| `acc_internal_requests` | DUPLICATE | `dewi_accessory_requests.py`, `dewi_accessories_full.py` | **MIGRATE → `dewi_accessory_requests`** |
| `acc_loans` | UNIQUE FEATURE | `dewi_accessories_full.py` | **PRESERVE** (loan-specific) |
| `acc_opname_sessions` | DUPLICATE | `dewi_accessories_full.py` | **MIGRATE → wh_opname2_cycles** |
| `acc_opname_lines` | DUPLICATE | `dewi_accessories_full.py` | **MIGRATE → wh_opname2_variances** |
| `accessories` (no prefix) | LEGACY ORPHAN | (none active) | **DELETE** |
| `accessory_requests` (no prefix) | DUPLICATE | (potentially `rahaza_alerts.py`) | **MERGE into `dewi_accessory_requests`** |
| `dewi_accessory_requests` | AUTHORITATIVE | `dewi_accessory_requests.py` | **KEEP as SSOT for requests** |
| `accessory_inspection_items` | UNIQUE | (QC for accessory) | **PRESERVE** |
| `accessory_inspections` | UNIQUE | (QC for accessory) | **PRESERVE** |
| `accessory_shipment_items` | UNIQUE | (shipment-specific) | **CONSOLIDATE w/ buyer_shipment_items** |
| `accessory_shipments` | UNIQUE | (shipment-specific) | **CONSOLIDATE w/ buyer_shipments** |
| `accessory_defects` | UNIQUE | (defect log) | **PRESERVE** |

### Target State (1 SSOT + specialized side-tables)

```
MASTER: rahaza_materials (filter: type='accessory' OR type='material' OR type='fg')
  + rahaza_material_stock
  + rahaza_material_movements

SPECIALIZED (preserved for unique features):
  + acc_purchase_requests → RENAME to: accessory_purchase_requests OR move into rahaza_purchase_orders
  + acc_loans → RENAME to: accessory_loans (UNIQUE feature)
  + dewi_accessory_requests → KEEP as: accessory_requests (consolidated)
  + accessory_defects + accessory_inspections → keep for QC tracking
```

### Migration Effort
- DB Schema mapping: 4 hours
- Data migration script: 4 hours
- Backend route consolidation: 8 hours
- Frontend UI consolidation: 4 hours (remove wh-accessory-master, wh-accessory-stock; keep wh-accessory-ops re-pointed)
- Testing: 4 hours
- **Total: ~24 hours | Risk: Medium**

---

## CLUSTER 2: MAKLON ORDERS (🔴 DEPRECATE LEGACY)

### Current State

| Collection | Type | Routes | Status |
|------------|------|--------|--------|
| `dewi_maklon_orders` | LEGACY | `dewi_maklon.py` | ⚠️ Old schema, tied to WO |
| `dewi_maklon_pos` | AUTHORITATIVE | `dewi_maklon_pos.py` | ✅ New, comprehensive |
| `dewi_maklon_clients` | AUTHORITATIVE | `dewi_maklon.py` | ✅ Used by both |
| `dewi_maklon_bom` | AUTHORITATIVE | `dewi_maklon_pos.py` | ✅ Tied to PO |
| `dewi_maklon_samples` | AUTHORITATIVE | `dewi_maklon_samples.py` | ✅ |
| `dewi_maklon_sample_revisions` | AUTHORITATIVE | `dewi_maklon_samples.py` | ✅ |
| `dewi_maklon_qc_checks` | AUTHORITATIVE | `dewi_maklon_qc.py` | ✅ |
| `dewi_maklon_inventory` | UNIQUE | `dewi_maklon.py` | ✅ |
| `dewi_maklon_material_issues` | UNIQUE | `dewi_maklon.py` | ✅ |
| `dewi_maklon_material_receive` | UNIQUE | `dewi_maklon.py` | ✅ |
| `dewi_maklon_dispatches` | AUTHORITATIVE | `dewi_maklon_pos.py` | ✅ |
| `dewi_maklon_invoices` | AUTHORITATIVE | `dewi_maklon_billing.py` | ✅ |
| `dewi_maklon_payments` | AUTHORITATIVE | `dewi_maklon_billing.py` | ✅ |
| `dewi_maklon_advance_payments` | AUTHORITATIVE | `dewi_maklon_billing.py` | ✅ |
| `dewi_maklon_hpp` | AUTHORITATIVE | `dewi_maklon_finance.py` | ✅ |
| `dewi_hpp_snapshots_maklon` | AUTHORITATIVE | `dewi_maklon_finance.py` | ✅ |
| `dewi_hpp_snapshots_po` | AUTHORITATIVE | `dewi_maklon_finance.py` | ✅ |

### Decision
**MIGRATE** `dewi_maklon_orders` → `dewi_maklon_pos`:
1. Audit production endpoints yang reference `dewi_maklon_orders`
2. Migrate orphan data dari `dewi_maklon_orders` ke `dewi_maklon_pos`
3. Update all routes
4. Remove sidebar item `maklon-orders` (atau redirect ke `maklon-po`)
5. Eventually drop collection `dewi_maklon_orders`

### Effort
- Data migration: 2 hours
- Backend route update: 4 hours
- Frontend update: 2 hours
- Testing: 4 hours
- **Total: ~12 hours | Risk: Medium**

---

## CLUSTER 3: WAREHOUSE/INVENTORY (🔴 3 SYSTEMS PARALEL)

### Current State

| Generation | Collections | Purpose | Status |
|-----------|-------------|---------|--------|
| **GEN 1 (oldest)** | `warehouse_locations`, `warehouse_movements`, `warehouse_opname`, `warehouse_putaway`, `warehouse_receiving`, `warehouse_stock` | Generic legacy | **LEGACY — deprecate** |
| **GEN 2 (rahaza)** | `rahaza_materials`, `rahaza_material_stock`, `rahaza_material_movements`, `rahaza_material_issues`, `rahaza_material_reservations`, `rahaza_fg_inventory`, `rahaza_fg_movements`, `rahaza_fg_issues` | Production-integrated | **KEEP as Material SSOT** |
| **GEN 3 (WMS modern)** | `wh_buildings`, `wh_zones`, `wh_racks`, `wh_positions`, `wh_unit_master`, `wh_unit_conversions`, `wh_fabric_rolls`, `wh_fabric_roll_movements`, `wh_cmt_dispatches`, `wh_delivery_notes`, `wh_picklists`, `wh_opname2_cycles`, `wh_opname2_variances`, `wh_returns`, `wh_pending_movements`, `wh_rack_alerts`, `wh_counters` | Modern WMS w/ barcode | **KEEP as Operations SSOT** |
| **MID (orphan)** | `wh_opname_sessions`, `wh_opname_lines`, `wh_opname_sessions2`, `wh_fg_movements`, `wms_*` | Mid-generation | **AUDIT — likely deprecate** |

### Recommended Architecture

```
LAYER 1: Material Master & Stock (Rahaza generation)
  - rahaza_materials (master data: items, types, units, cost)
  - rahaza_material_stock (current on-hand)
  - rahaza_material_movements (movement log = audit trail)
  - rahaza_material_issues (issues to production)
  - rahaza_material_reservations (reservations for WO)

LAYER 2: Physical Storage (WMS generation)
  - wh_buildings, wh_zones, wh_racks, wh_positions (location hierarchy)
  - wh_unit_master, wh_unit_conversions (UOM standardization)

LAYER 3: Item Tracking (WMS generation)
  - wh_fabric_rolls + wh_fabric_roll_movements (roll-level tracking)
  - rahaza_fg_inventory + rahaza_fg_movements (FG tracking)

LAYER 4: Operations (WMS generation)
  - wh_cmt_dispatches (outbound to CMT)
  - wh_delivery_notes (outbound to customer)
  - wh_picklists (pick instructions)
  - wh_opname2_cycles + wh_opname2_variances (cycle counting)
  - wh_returns (returns processing)
  - wh_pending_movements (queue)
  - wh_rack_alerts (alerts)
  - wh_counters (number sequences)
```

### DELETE (Legacy GEN 1)
```
warehouse_locations → superseded by wh_positions
warehouse_movements → superseded by rahaza_material_movements
warehouse_opname → superseded by wh_opname2_cycles
warehouse_putaway → superseded by wh_pending_movements
warehouse_receiving → needs migration (still used by ReceivingModule!)
warehouse_stock → superseded by rahaza_material_stock
```

### DELETE (Mid orphan)
```
wh_opname_sessions, wh_opname_lines, wh_opname_sessions2 → superseded by wh_opname2_*
wms_* (older WMS) → superseded by wh_* (newer WMS)
wh_fg_movements → evaluate vs rahaza_fg_movements (may be duplicate)
```

### Effort
- Architecture spec: 4 hours
- Migration scripts (6 legacy collections): 12 hours
- Backend route consolidation (5+ files): 12 hours
- Frontend UI update (4 modules): 4 hours
- Testing comprehensive: 8 hours
- **Total: ~40 hours | Risk: High**

---

## CLUSTER 4: ORDERS & WORK ORDERS

### Current State

| Collection | Purpose | Status |
|------------|---------|--------|
| `rahaza_orders` | Production sales orders | ✅ AUTHORITATIVE |
| `rahaza_work_orders` | Internal work orders | ✅ AUTHORITATIVE |
| `work_orders` (no prefix) | Legacy generic | 🔴 LEGACY |
| `production_work_orders` | Legacy production-specific | 🔴 LEGACY |
| `production_pos` | Production POs | ✔️ Unique purpose (PO untuk production batch) |
| `dewi_maklon_orders` | Maklon orders (lama) | 🔴 LEGACY (see Cluster 2) |
| `dewi_maklon_pos` | Maklon POs (baru) | ✅ AUTHORITATIVE |
| `dewi_toko_orders` | Marketplace orders (lama) | 🔴 LEGACY |
| `marketing_orders` | Marketplace orders (baru) | ✅ AUTHORITATIVE |

### Decision
Keep clear separation:
- **Sales/Production Order:** `rahaza_orders`
- **Internal Work Order:** `rahaza_work_orders`
- **Production PO:** `production_pos` (specialized)
- **Maklon PO:** `dewi_maklon_pos`
- **Marketplace Order:** `marketing_orders`

**DELETE:** `work_orders`, `production_work_orders`, `dewi_maklon_orders`, `dewi_toko_orders`

---

## CLUSTER 5: INVOICES & PAYMENTS

### Current State

| Collection | Purpose | Status |
|------------|---------|--------|
| `invoices` (no prefix) | Legacy generic | 🔴 LEGACY — evaluate |
| `dewi_invoices` | Modern invoices | ✅ AUTHORITATIVE |
| `dewi_maklon_invoices` | Maklon-specific | ✅ KEEP (specialized) |
| `rahaza_ar_invoices` | Production AR | ✅ AUTHORITATIVE for AR |
| `rahaza_invoices` | Legacy production | 🔴 LEGACY |
| `rahaza_ap_invoices` | AP invoices | ✅ AUTHORITATIVE |
| `invoice_adjustments` | Adjustment log | ✅ KEEP |
| `invoice_change_history` | Audit log | ✅ KEEP |
| `invoice_edit_requests` | Workflow | ✅ KEEP |

### Payments
| Collection | Purpose | Status |
|------------|---------|--------|
| `payments` (no prefix) | Legacy generic | 🔴 LEGACY |
| `rahaza_payments` | Production payments | ✅ KEEP |
| `rahaza_ar_receipts` | AR receipts | ✅ AUTHORITATIVE |
| `rahaza_ap_payments` | AP payments | ✅ AUTHORITATIVE |
| `dewi_maklon_payments` | Maklon payments | ✅ KEEP |
| `dewi_maklon_advance_payments` | Down payments | ✅ KEEP |

### Decision
- **AR Invoices:** `rahaza_ar_invoices` (SSOT) + `dewi_maklon_invoices` (specialized for Maklon)
- **AP Invoices:** `rahaza_ap_invoices` (SSOT)
- **DELETE:** `invoices`, `rahaza_invoices`, `payments`, `dewi_invoices` (if orphan)

---

## CLUSTER 6: KOL & CREATOR (3 SYSTEMS)

### Current State

| Collection | Generation | Status |
|------------|-----------|--------|
| `dewi_kol_creators` | OLD | 🔴 LEGACY |
| `dewi_kol_deals` | OLD | 🔴 LEGACY |
| `dewi_kol_samples` | OLD | 🔴 LEGACY |
| `marketing_kol_creators` | MID | ✅ KEEP |
| `marketing_kol_login_attempts` | MID | ✅ KEEP |
| `marketing_creator_catalog` | NEW | ✅ AUTHORITATIVE |
| `marketing_creator_item_requests` | NEW | ✅ AUTHORITATIVE |
| `marketing_creator_sessions` | NEW | ✅ AUTHORITATIVE |
| `marketing_creator_targets` | NEW | ✅ AUTHORITATIVE |

### Decision
- **MIGRATE** `dewi_kol_*` → `marketing_kol_creators` + `marketing_creator_*`
- **DELETE** sidebar items: `toko-kol`, `toko-deals`, `toko-samples` (orphan in registry)

---

## CLUSTER 7: LEGACY TOKO (🔴 DEPRECATE/MIGRATE)

### Current State (8 collections)

| Collection | Replacement | Decision |
|------------|-------------|----------|
| `dewi_toko_channels` | `marketing_platform_accounts` | **MIGRATE → marketing_platform_accounts** |
| `dewi_toko_channel_syncs` | `marketing_stock_syncs` | **MIGRATE** |
| `dewi_toko_flashsales` | `marketing_discounts` (type=flashsale) | **MIGRATE** |
| `dewi_toko_orders` | `marketing_orders` | **MIGRATE** |
| `dewi_toko_pack_batches` | (no direct replacement) | **EVALUATE — maybe keep or move to fulfillment** |
| `dewi_toko_products` | `marketing_catalog_items` | **MIGRATE** |
| `dewi_toko_returns` | `marketing_returns` | **MIGRATE** |
| `dewi_toko_reviews` | `marketing_reviews` | **MIGRATE** |

### Decision
**MIGRATE ALL** then delete legacy. Hapus sidebar items:
- `toko-channels` → redirect to `marketing-accounts`
- `toko-pricing` → redirect to `marketing-discounts`

### Effort: ~16 hours | Risk: Medium

---

## CLUSTER 8: USERS & AUTH

| Collection | Purpose | Decision |
|------------|---------|----------|
| `users` | Main user table | ✅ KEEP |
| `rahaza_users` | Production-specific (with employee_id link) | ✅ KEEP (different schema) |
| `dewi_client_users` | External client portal | ✅ KEEP (external auth) |
| `marketing_kol_creators` | KOL/Creator auth | ✅ KEEP (specialized) |
| `login_attempts` | Login log | ✅ KEEP |
| `client_login_attempts` | Client portal log | ✅ KEEP |
| `marketing_kol_login_attempts` | KOL log | ✅ KEEP |
| `rahaza_webauthn_challenges` | Auto-attendance | ✅ KEEP |
| `rahaza_webauthn_credentials` | Auto-attendance | ✅ KEEP |
| `rahaza_zkteco_devices` | Attendance device | ✅ KEEP |
| `rate_limit_buckets` | Rate limiting | ✅ KEEP |

**Decision:** No change needed. All justified.

---

## CLUSTER 9: NOTIFICATIONS

| Collection | Purpose | Decision |
|------------|---------|----------|
| `dewi_notifications` | Main notification | ✅ KEEP as SSOT |
| `rahaza_notifications` | Legacy duplicate | 🔴 **MERGE into `dewi_notifications`** |
| `collab_notifications` | Collaboration-specific | ⚠️ **CONSOLIDATE into `dewi_notifications` (with type filter)** |
| `marketing_livehost_notifications` | LiveHost-specific | ⚠️ **CONSOLIDATE into `dewi_notifications` (with type filter)** |
| `push_subscriptions` | Push notification subs | ✅ KEEP (different concern) |
| `reminders` | Reminder system | ✅ KEEP (different model) |

### Recommendation
Buat **unified notification service** dengan:
- 1 collection: `notifications` (atau `dewi_notifications`)
- Field `type` untuk segregasi (general, comm, collab, marketing, etc.)
- Field `target_user_id` untuk routing
- Field `meta` JSON untuk data spesifik tipe

---

## CLUSTER 10: COUNTERS / NUMBER SEQUENCES

| Collection | Purpose | Decision |
|------------|---------|----------|
| `counters` | Generic counter | 🔴 MERGE |
| `dewi_counters` | Dewi prefix sequences | 🔴 MERGE |
| `rahaza_counters` | Rahaza prefix sequences | 🔴 MERGE |
| `rahaza_bundle_counters` | Bundle-specific | ⚠️ Consider merging |
| `wh_counters` | Warehouse-specific | ⚠️ Consider merging |

### Recommendation
Unify into **1 collection `counters`** with `namespace` field:
```javascript
{ namespace: 'PO', current: 12345, prefix: 'PO-2026-' }
{ namespace: 'WO', current: 8901, prefix: 'WO-2026-' }
{ namespace: 'BUNDLE', current: 99887, prefix: 'BND-' }
```

**Effort: ~8 hours | Risk: Medium (touches many flows)**

---

## CLUSTER 11: ATTENDANCE & PERFORMANCE

### Attendance
| Collection | Status |
|------------|--------|
| `rahaza_attendance` | ✅ AUTHORITATIVE (daily summary) |
| `rahaza_attendance_events` | ✅ AUTHORITATIVE (event log) |
| `dewi_attendance` | 🔴 DUPLICATE — evaluate, likely orphan |

### Performance
| Collection | Status |
|------------|--------|
| `hris_cycles` + `hris_assignments` + `hris_reviews` + `hris_kpi_assignments` + `hris_training_completions` | ✅ KEEP as HRIS SSOT |
| `dewi_perf_cycles` + `dewi_perf_assignments` + `dewi_perf_kpis` + `dewi_perf_reviews` | 🔴 DUPLICATE of hris_* |

**Decision:** **DELETE** `dewi_attendance` (if orphan), **MIGRATE** `dewi_perf_*` → `hris_*`.

---

## CLUSTER 12: SHIPMENTS (consolidation opportunity)

| Collection | Purpose | Decision |
|------------|---------|----------|
| `rahaza_shipments` | Sales shipments | ✅ KEEP as Sales SSOT |
| `wh_delivery_notes` | Modern delivery notes | ✅ KEEP as Delivery SSOT |
| `buyer_shipments` | Buyer-side log | ⚠️ Consider merge |
| `vendor_shipments` | Vendor inbound | ✅ KEEP (different direction) |
| `accessory_shipments` | Accessory-specific | ⚠️ MERGE into vendor_shipments |
| `dewi_maklon_dispatches` | Maklon dispatches | ✅ KEEP (specialized) |
| `buyer_shipment_items` | Items log | ⚠️ Consider merge |
| `vendor_shipment_items` | Items log | ✅ KEEP |
| `accessory_shipment_items` | Items log | ⚠️ MERGE |

---

## DATA ARCHITECTURE TARGET STATE

```
Master Data Layer:
  rahaza_materials      ← single SSOT for items (material, accessory, fg)
  rahaza_customers      ← customer master
  rahaza_employees      ← employee master
  dewi_maklon_clients   ← maklon clients
  dewi_cmt_partners     ← CMT vendor master
  users + rahaza_users  ← auth (parallel allowed)

Transaction Layer:
  rahaza_orders         ← sales/production orders
  rahaza_work_orders    ← internal WO
  dewi_maklon_pos       ← maklon POs
  rahaza_purchase_orders← material POs
  marketing_orders      ← marketplace orders

Inventory Layer:
  rahaza_material_stock + movements + issues + reservations
  rahaza_fg_inventory + fg_movements + fg_issues
  wh_fabric_rolls (specialized)

WMS Operations:
  wh_buildings/zones/racks/positions (locations)
  wh_picklists + wh_pending_movements
  wh_opname2_cycles + variances
  wh_returns
  wh_delivery_notes + wh_cmt_dispatches

Finance Layer:
  COA: rahaza_coa + rahaza_coa_accounts
  Journal: rahaza_journal_entries + rahaza_journal_lines
  GL: gl_entries + rahaza_periods
  AR: rahaza_ar_invoices + rahaza_ar_receipts
  AP: rahaza_ap_invoices + rahaza_ap_payments
  Cash: rahaza_cash_accounts + rahaza_cash_movements + bank_recon_*
  Reports: rahaza_*_aging + derived

HR Layer:
  Employee: rahaza_employees + da_*
  Attendance: rahaza_attendance + rahaza_attendance_events
  Leave: rahaza_leave_requests + rahaza_leave_balances + rahaza_leave_types
  Payroll: rahaza_payroll_profiles + runs + payslips + adjustments
  Performance: hris_cycles + assignments + reviews + kpi_assignments
  LMS: dewi_lms_*
  Documents: hr_issued_documents + employee_documents

Marketing Layer:
  Accounts: marketing_platform_accounts
  Sales: marketing_sales_data
  Orders: marketing_orders
  Catalog: marketing_catalog_items + marketing_catalogs
  KOL: marketing_kol_creators + marketing_creator_*
  Campaigns: marketing_discounts + marketing_product_launches
  Content: marketing_content_calendar
  Performance: marketing_account_health + marketing_account_targets
  AI: marketing_ai_content_history + marketing_dynamic_pricing_*
  LiveHost: marketing_livehost_* (specialized cluster)
  Reports: marketing_targets + marketing_alert_*

Collaboration Layer:
  Comm: comm_conversations + comm_channels + comm_messages + comm_read_receipts
  Workspace: workspace_documents + workspace_shares + workspace_versions
  Files: attachments
  LMS: study_groups + dewi_lms_*
  Activity: activity_logs

Notification Layer (UNIFIED):
  notifications (with type field)  ← consolidate dewi_/rahaza_/collab_/marketing_livehost_
  push_subscriptions
  reminders

System Layer:
  counters (unified with namespace field)
  role_permissions + roles
  rahaza_audit_logs + activity_logs
  rate_limit_buckets
  rahaza_company_settings + company_settings (consolidate)
```

---

## SUMMARY: COLLECTIONS TO DELETE/MIGRATE

### DELETE (Orphan/Legacy, no migration needed)
- `accessories`
- `wh_opname_sessions`, `wh_opname_lines`, `wh_opname_sessions2`
- `warehouse_*` (after data migrated)
- `work_orders`, `production_work_orders` (after audit)
- `invoices`, `rahaza_invoices`, `payments` (after audit)
- `dewi_perf_*` (4 collections, after data migrated to `hris_*`)
- `dewi_attendance` (after audit confirms orphan)
- `dewi_kol_*` (3 collections, after migration to `marketing_kol_*`)

### MIGRATE (Data must be preserved)
- `acc_items` → `rahaza_materials` (with type=accessory)
- `acc_stock_movements` → `rahaza_material_movements`
- `acc_internal_requests` → `dewi_accessory_requests`
- `acc_opname_*` → `wh_opname2_*`
- `dewi_maklon_orders` → `dewi_maklon_pos`
- `dewi_toko_*` (8 collections) → `marketing_*` cluster
- `rahaza_notifications` → `notifications` (unified)
- `collab_notifications` → `notifications` (with type)
- `marketing_livehost_notifications` → `notifications` (with type)
- `counters` + `dewi_counters` + `rahaza_counters` → unified `counters`

### CONSOLIDATE / RENAME (no data loss)
- `accessory_shipments` + `accessory_shipment_items` → merge into vendor_shipments cluster
- `dewi_perf_*` → `hris_*`
- Various "da_*" duplicates of "dewi_*"

**TOTAL: ~40 collections affected** (out of 280)

**Estimated reduction: ~40 collections → ~12 collections remaining after merge = net reduction of ~28 collections**

Final target: **~252 collections** (vs 280 now) — cleaner data architecture.
