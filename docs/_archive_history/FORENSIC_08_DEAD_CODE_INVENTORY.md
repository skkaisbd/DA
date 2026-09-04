# FORENSIC AUDIT — 08: DEAD CODE INVENTORY
## List Code/Routes/Collections untuk Dihapus

**Lensa:** L9 Cross-Module Dependencies + L7 DDD

---

## METODOLOGI

Kategori "dead" yang teridentifikasi:
1. **Orphan Frontend Components** — File ada, tidak ada import yang aktif
2. **Orphan Backend Routes** — Route ada, tidak punya UI yang call
3. **Orphan MongoDB Collections** — Tidak ada write activity
4. **Legacy Redirects** — Backward-compat stubs yang sudah lama
5. **Backup Files** — `.backup`, `.old`, `.legacy`
6. **Placeholder Files** — Stubs yang harusnya sudah di-replace

---

## 1. ORPHAN FRONTEND COMPONENTS (kandidat hapus)

### Confirmed Backup/Placeholder Files
| File | Reason | Action |
|------|--------|--------|
| `RahazaHPPModule.jsx.backup` | Backup file leaked to git | **DELETE** |
| `HRDashboardPlaceholder.jsx` | Replaced by `HRDashboard.jsx` | **DELETE** (after verify no import) |
| `ProductionDashboardPlaceholder.jsx` | Replaced by `ProductionDashboardModule.jsx` | **DELETE** (after verify) |

### Suspected Orphan (need import verification)
Komponen yang ID-nya di registry tapi tidak ada di sidebar manapun:
- `BuyersModule.jsx` (replaced by RahazaCustomersModule)
- `TokoDashboard.jsx` (legacy fallback)
- `TokoDashboardModule.jsx` (legacy classic)
- `TokoProductCatalogModule.jsx` (replaced by CatalogManagementModule)
- `TokoOrdersModule.jsx` (replaced by UnifiedOrdersDashboard)
- `TokoKOLModule.jsx` (replaced by KOLCreatorModule + KOLLeaderboardModule)
- `TokoCSReturnsModule.jsx` (replaced by ComplaintsManagementModule + ReturnsRefundsModule)
- `RnDModule.jsx` (umbrella, replaced by separate rnd-* modules)
- `SelfServicePortal.jsx` (replaced by PortalSayaDashboard)
- `Dashboard.jsx` (generic, possibly orphan)

### Bundle-related (suspected duplicate)
- `BundleDetailPage.jsx` vs `bundleTickets.js` — verify usage
- `BundleScannerModal.jsx` vs `AssetScannerModal.jsx` vs main scanner — consolidate

### "V1 vs V2" Pairs (deprecate V1)
| V1 (delete) | V2 (keep) |
|-------------|-----------|
| `DataTable.jsx` | `DataTableV2.jsx` |
| `RahazaBOMModule.jsx` | `RahazaBOMModuleV2.jsx` |

### Recommendation
Create verification script:
```bash
for file in suspect_files; do
  count=$(grep -r "import.*$file" /app/frontend/src/ | wc -l)
  if [ $count -eq 0 ]; then echo "DELETE: $file"; fi
done
```

---

## 2. ORPHAN BACKEND ROUTES

### Likely Orphan (need verification via API call tracing)

| Route File | Reason | Verification Needed |
|------------|--------|---------------------|
| `routes/production.py` | Generic, superseded by `rahaza_production.py` | Check imports in server.py |
| `routes/master_data.py` | Generic, superseded by `rahaza_master.py` | Check imports |
| `routes/warehouse.py` | Superseded by `wms_*` files | Check imports |
| `routes/dewi_toko.py` | Legacy storefront, marketing replaces it | Check imports |
| `routes/dewi_kol.py` | Duplicate of `marketing_kol.py` | Check imports |
| `routes/dewi_online_orders.py` | Superseded by `marketing_orders_routes.py` | Check imports |
| `routes/operations.py` | Generic, possibly orphan | Check imports |
| `routes/finishing.py` | Generic finishing, vs rahaza-specific? | Check |
| `routes/qc.py` | Generic QC, vs rahaza_qc_v2? | Check |
| `routes/production_po.py` | Generic vs rahaza? | Check |
| `routes/finance.py` | Generic finance, vs rahaza_finance | Check |
| `routes/admin.py` | Generic admin | Check |
| `routes/dashboard_routes.py` | Generic dashboard | Check |
| `routes/notifications.py` | Vs `dewi_notifications.py`, `rahaza_notifications.py` | Multi-system overlap |
| `routes/fulfillment.py` | Used by Fulfillment module | Likely KEEP |
| `routes/search.py` + `routes/unified_search.py` | 2 search systems | Consolidate |
| `routes/universal_import.py` + `routes/marketing_import.py` | 2 import systems | Consolidate |
| `routes/universal_import_indexes.py` | Standalone indexes? | Verify |

### Confirmed To Keep
All `rahaza_*` (heavy usage)
All `dewi_maklon_*` (active maklon flows)
All `marketing_*` (active marketing portal)
All `wms_*` and `wh_*` (active warehouse)
All AI/integration routes (active features)

---

## 3. ORPHAN MONGODB COLLECTIONS

### High Confidence Orphan (no recent write activity expected)
```
accessories                      → legacy, fully replaced
warehouse_locations              → superseded by wh_positions
warehouse_movements              → superseded by rahaza_material_movements
warehouse_stock                   → superseded by rahaza_material_stock
warehouse_putaway                 → superseded by wh_pending_movements
warehouse_opname                  → superseded by wh_opname2_cycles
wh_opname_sessions                → mid-generation, superseded
wh_opname_lines                   → mid-generation
wh_opname_sessions2               → mid-generation
work_orders                       → superseded by rahaza_work_orders
production_work_orders            → superseded by rahaza_work_orders
invoices (no prefix)              → superseded by rahaza_*_invoices
payments (no prefix)              → superseded by rahaza_*_payments
garments                          → legacy product collection?
```

### Need Verification
```
rahaza_notifications              → consolidate to unified notifications
dewi_attendance                   → vs rahaza_attendance, likely orphan
dewi_perf_*                       → vs hris_*, likely duplicate
da_kpi_*                          → vs hris_kpi_*, likely duplicate
da_assets, da_asset_assignments  → vs dewi_assets, likely duplicate
dewi_kol_*                        → vs marketing_kol_*, likely orphan
dewi_invoices                     → vs rahaza_ar_invoices, verify usage
products                          → vs marketing_catalog_items, likely orphan
buyers                            → vs rahaza_customers, likely orphan
```

---

## 4. LEGACY REDIRECTS DI moduleRegistry.js

Ini adalah redirects untuk backward compatibility. Beberapa sudah lama dan bisa dihapus:

```javascript
// Legacy PT Rahaza terminology (PT Rahaza was earlier system name)
'prod-exec-rajut'    → makeRedirect('prod-exec-cutting')
'prod-exec-linking'  → makeRedirect('prod-exec-sewing')
'prod-exec-steam'    → makeRedirect('prod-exec-finishing')
'prod-exec-washer'   → makeRedirect('prod-exec-rework')
'prod-exec-sontek'   → makeRedirect('prod-exec-rework')
```

**Decision:** Setelah ~6 bulan ada di sistem, redirect ini bisa dihapus. **DELETE setelah konfirmasi tidak ada user yang masih bookmark URL lama.**

Redirects yang masih relevan (keep):
```javascript
// Recent (Navigation Refinement Phase 1)
'mgmt-products'           → prod-models-bom
'wh-material-reservation' → prod-material-reservation
'prod-oee', 'prod-line-balance', 'prod-rework-analytics', 'prod-aps-gantt' → production-dashboard
'prod-models', 'prod-bom', 'prod-sizes' → prod-models-bom
```

---

## 5. UNUSED SIDEBAR ITEMS (yang ID-nya tidak ada di mana pun)

Sudah diidentifikasi 4 broken menu:
```
maklon-cmt                  → NOT in registry → FIX or REMOVE
maklon-packing              → NOT in registry → FIX or REMOVE
prod-rework-board           → NOT in registry → FIX or REMOVE
prod-alert-settings         → NOT in registry → FIX or REMOVE
```

**Decision:** Either implement the missing modules OR remove from sidebar.
Lihat FORENSIC_07 untuk recommended action.

---

## 6. UNUSED REGISTRY IDS (di registry, tidak di sidebar)

Dari moduleRegistry.js, terdapat ~30 IDs yang tidak referenced dari PortalShell sidebar:
```
mgmt-customers              → obsolete (replaced by mgmt-rahaza-customers)
wh-accessory                → obsolete (renamed)
self-dashboard              → obsolete
toko-dashboard-legacy       → backup access only
toko-dashboard-classic      → backup access only
toko-products               → obsolete
toko-orders                 → obsolete
toko-packing, toko-shipping → obsolete tab variants
toko-kol, toko-deals, toko-samples → obsolete
toko-cs, toko-returns       → obsolete
rnd-module                  → obsolete umbrella
rnd-style-detail            → modal-only, not routable
collab-communication        → hidden direct access (kept)
prod-exec-rajut, linking, steam, washer, sontek → legacy PT Rahaza terms
```

**Decision:** Most can be removed from registry. Keep only those with active redirect logic.

---

## 7. CMT "REQUESTS" DUPLIKAT

Di registry ada:
```javascript
'production-cmt-component-requests': CMTComponentRequestModule,
'cmt-component-requests': CMTComponentRequestModule,  // alias generic
```

Dan untuk RnD alias:
```javascript
'rnd-kreator-requests': KREATORRequestModule,
'rnd-accessory-requests': AccessoryRequestInbox,
```

**Decision:** Aliases ini OK untuk cross-portal access. Keep.

---

## 8. DEAD CODE SUMMARY

### Quick-Win Deletions (Low Risk)
- 1 backup file: `RahazaHPPModule.jsx.backup`
- 2 placeholder files: `HRDashboardPlaceholder.jsx`, `ProductionDashboardPlaceholder.jsx`
- 5 legacy redirect entries (PT Rahaza terminology)
- ~10 obsolete registry IDs

### Medium-Risk Deletions
- 1 backup module: `RahazaBOMModule.jsx` (after V2 migration verified)
- `DataTable.jsx` v1 (after migrating ~30 modules to V2)
- 10+ orphan backend routes (after API call tracing)
- 10-15 legacy collections (after verifying no writes)

### High-Risk Deletions (need migration plan)
- Generation 1 warehouse collections (after migration)
- Legacy Toko collections (after migration to marketing_*)
- Legacy KOL collections (after migration)

---

## 9. CLEANUP CHECKLIST

### Phase 1: Safe deletions (1 hari)
- [ ] Delete `RahazaHPPModule.jsx.backup`
- [ ] Verify & delete `HRDashboardPlaceholder.jsx`, `ProductionDashboardPlaceholder.jsx`
- [ ] Remove 5 PT Rahaza legacy redirect entries
- [ ] Remove 10 obsolete registry IDs
- [ ] Clean up commented-out code blocks (>100 lines saved)

### Phase 2: Verification + Delete (3 hari)
- [ ] Run import-tracing script untuk frontend
- [ ] Run API-call tracing untuk backend routes
- [ ] Run write-activity check untuk DB collections (need data, not just code)
- [ ] Delete verified orphans

### Phase 3: Migration + Delete (1-2 minggu)
- [ ] Migrate accessories collections (see FORENSIC_04)
- [ ] Migrate Toko collections to Marketing
- [ ] Migrate KOL collections
- [ ] Migrate Maklon orders
- [ ] Delete legacy collections after migration verified

---

## 10. EXPECTED IMPACT

| Metric | Before | After Cleanup |
|--------|--------|---------------|
| Backend route files | 194 | ~165 |
| Frontend components | 270 | ~250 |
| MongoDB collections | 280 | ~250 |
| Bundle size (frontend) | ? | -10-15% |
| Time to find module | High | Lower (less noise) |
| Maintenance burden | High | Lower |

**Estimated total cleanup effort: ~40 hours**  
**Estimated risk: Medium** (mostly low-risk items, with careful migration plan for medium-risk)
