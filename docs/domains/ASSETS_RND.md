# Assets & RnD Domain — Technical Reference

> **Portal:** Asset Management (`asset-portal`) + RnD (`rnd-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready

---

## 1. Business Overview

### Asset Management
- Company asset register (equipment, machines, vehicles, IT assets)
- Asset acquisition, transfer, maintenance, disposal
- Depreciation tracking
- Asset QR code scanning
- Predictive maintenance scheduling
- Asset purchase requests (with approval chain)

### RnD (Research & Development)
- Style/pattern development
- HPP (Harga Pokok Produksi) calculation
- RnD materials management
- Design management
- Sample production coordination
- Style master integration with production

---

## 2. Key MongoDB Collections

### Asset Management
| Collection | Purpose | SSOT? |
|---|---|---|
| `dewi_assets` | Asset register (main) | ✅ SSOT |
| `dewi_asset_movements` | Transfer/movement history | ✅ SSOT |
| `dewi_asset_maintenance` | Maintenance records | ✅ SSOT |
| `dewi_asset_photos` | Asset photos (base64/URL) | ✅ SSOT |
| `rahaza_asset_purchase_reqs` | Asset purchase requests | ✅ SSOT |
| `rahaza_fixed_assets` | Financial fixed asset register | ✅ SSOT (Finance) |

### RnD
| Collection | Purpose | SSOT? |
|---|---|---|
| `dewi_rnd_styles` | Style/design catalog | ✅ SSOT |
| `dewi_rnd_designs` | Design variants | ✅ SSOT |
| `dewi_rnd_materials` | RnD material specs | ✅ SSOT |
| `dewi_rnd_samples` | Sample production records | ✅ SSOT |
| `dewi_rnd_hpp` | HPP calculations per style | ✅ SSOT |
| `dewi_rnd_overview` | RnD project overview | ✅ SSOT |
| `dewi_rnd_shared` | Shared RnD config | ✅ SSOT |

---

## 3. Key API Endpoints

### Asset Management
```
GET  /api/dewi/assets                 — list assets
POST /api/dewi/assets                 — create asset
GET  /api/dewi/assets/{id}            — asset detail (scannable by Universal Scan)
PUT  /api/dewi/assets/{id}            — update asset
POST /api/dewi/assets/{id}/transfer   — transfer to another location/dept
POST /api/dewi/assets/{id}/upload-photo — upload photo
POST /api/dewi/assets/{id}/maintenance — log maintenance
GET  /api/dewi/assets/by-location     — assets by location
GET  /api/dewi/assets/low-maintenance — assets due for maintenance
```

### Asset Purchase Requests (with Approval Chain)
```
GET  /api/rahaza/asset-purchase-reqs  — list purchase requests
POST /api/rahaza/asset-purchase-reqs  — create request
POST /api/rahaza/asset-purchase-reqs/{id}/approve — approve
POST /api/rahaza/asset-purchase-reqs/{id}/reject  — reject
```

### Predictive Maintenance
```
GET  /api/dewi/predictive-maintenance  — maintenance predictions
GET  /api/dewi/predictive-maintenance/overdue — overdue maintenance list
POST /api/dewi/predictive-maintenance/schedule — schedule maintenance
```

### RnD
```
GET  /api/dewi/rnd/styles             — list styles
POST /api/dewi/rnd/styles             — create style
GET  /api/dewi/rnd/styles/{id}        — style detail
GET  /api/dewi/rnd/designs            — list designs
POST /api/dewi/rnd/designs            — create design
GET  /api/dewi/rnd/hpp                — list HPP calculations
POST /api/dewi/rnd/hpp                — create HPP
GET  /api/dewi/rnd/samples            — list samples
POST /api/dewi/rnd/samples            — create sample request
GET  /api/dewi/rnd/materials          — RnD material specs
GET  /api/dewi/rnd/overview           — RnD project overview
```

---

## 4. Key Frontend Modules

### Asset Management
| Module File | Portal Nav ID | Description |
|---|---|---|
| `AssetManagementPortal.jsx` | `asset-portal` | Main asset portal (refactored Session #6) |
| `AssetScannerModal.jsx` | (modal) | Asset QR scanner |

### RnD
| Module File | Portal Nav ID | Description |
|---|---|---|
| `RnDPortalModule.jsx` | `rnd-dashboard` | RnD portal overview |
| `RnDStylesModule.jsx` | `rnd-styles` | Style catalog |
| `RnDDesignModule.jsx` | `rnd-designs` | Design management |
| `RnDSamplesModule.jsx` | `rnd-samples` | Sample management |
| `RnDMaterialsModule.jsx` | `rnd-materials` | RnD materials |
| `RnDHPPModule.jsx` | `rnd-hpp` | HPP calculation |

---

## 5. Business Flows

### Asset Lifecycle
```
Asset Purchase Request → Approval Chain
  → Approved → PO created
  → GRN received → Asset registered (dewi_assets)
  → Photo uploaded + QR generated
  → Assigned to department/location
  → Maintenance schedule created
  → Regular maintenance logged
  → Predictive alerts when overdue
  → Transfer to other dept if needed
  → Disposal / write-off → GL entry
```

### HPP Calculation
```
Style defined in RnD (dewi_rnd_styles)
  → BOM materials specified (fabric, trims, accessories)
  → Labour cost per process added
  → Overhead allocation applied
  → HPP = Materials + Labour + Overhead
  → HPP used for pricing (maklon quotes, retail)
```

### Style → Production Flow
```
RnD Style approved
  → Linked to rahaza_models (production master)
  → BOM created (rahaza_boms)
  → Available for Work Order creation
```

---

## 6. Asset Portal Refactor (Session #6)

Session #6 (2026-05-23): Asset Management Portal refactored from 1 large file to modular structure:
- Main portal file size reduced significantly
- Sub-components: AssetList, AssetDetail, AssetMaintenanceLog, AssetTransferDialog, AssetPurchaseRequest
- QR code scanning integrated via `AssetScannerModal.jsx`
- Universal Scan (Session #11.19): `asset` entity type supported

---

## 7. Key Backend Files

| File | Purpose |
|---|---|
| `routes/dewi_asset_management.py` | Asset CRUD + transfers + photos |
| `routes/dewi_assets.py` | Asset endpoints (older entry) |
| `routes/dewi_predictive_maintenance.py` | Predictive maintenance |
| `routes/dewi_rnd.py` | RnD overview |
| `routes/dewi_rnd_styles.py` | Style management |
| `routes/dewi_rnd_design.py` | Design management |
| `routes/dewi_rnd_samples.py` | Sample management |
| `routes/dewi_rnd_materials.py` | RnD materials |
| `routes/dewi_rnd_hpp.py` | HPP calculation |
| `routes/dewi_rnd_overview.py` | RnD project overview |

---

## 8. Recent Relevant Sessions

- **#11.19 (2026-05-27):** Asset purchase requests with approval chain; Universal Scan for assets
- **Session #6 (2026-05-23):** Asset Management Portal full refactor (Phase 4)
- **Session #2 (2026-05-23):** P2 tasks — Asset Utilization, Predictive Maintenance |

---

## 9. Notes

- Asset IDs are QR-code scannable (Universal Scan supports `asset` entity type)
- `dewi_assets` and `rahaza_fixed_assets` serve different purposes:
  - `dewi_assets`: operational asset tracking (who has it, maintenance status)
  - `rahaza_fixed_assets`: financial fixed asset register (depreciation, book value)
- RnD samples can trigger Maklon sample production (cross-domain link)
