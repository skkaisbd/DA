# Maklon & CMT Domain — Technical Reference

> **Portal:** Maklon (`maklon-portal`) + Production CMT section  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready, P1.B consolidation complete

---

## 1. Business Overview

CV. Dewi Aditya operates as a CMT (Cut-Make-Trim) contractor AND subcontracts work to CMT vendors:

**As CMT Contractor (receiving work from clients):**
- Client provides fabric + specs
- Dewi Aditya produces garments
- Billing to client (Maklon billing)

**As Maklon Buyer (sending work to CMT vendors):**
- PO to CMT vendors
- Dispatch fabric/materials to vendor
- Receive finished goods
- QC + receive billing from vendor

Modules:
- Maklon PO management (360° view)
- CMT progress tracking (per-DO-CMT progress)
- CMT delivery orders
- Maklon billing (invoicing)
- CMT lifecycle (start → in-progress → complete)
- CMT packing & QC
- Client portal (client views their order status)
- Maklon samples
- SLA management

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? | Notes |
|---|---|---|---|
| `dewi_maklon_pos` | Maklon Purchase Orders | ✅ SSOT | Replaced `dewi_maklon_orders` (P1.B) |
| `dewi_maklon_billing` | Maklon billing invoices | ✅ SSOT | |
| `dewi_cmt_progress` | CMT DO progress (DO-CMT-YYYYMMDD-NNN) | ✅ SSOT | |
| `dewi_cmt_delivery_orders` | CMT delivery orders | ✅ SSOT | |
| `dewi_cmt_packing` | CMT packing records | ✅ SSOT | |
| `dewi_maklon_quotes` | Maklon quotations | ✅ SSOT | |
| `dewi_maklon_samples` | Sample production requests | ✅ SSOT | |
| `dewi_maklon_qc` | QC for maklon production | ✅ SSOT | |
| `dewi_maklon_sla` | SLA definitions & tracking | ✅ SSOT | |
| `dewi_maklon_finance` | Maklon finance records | ✅ SSOT | |
| `dewi_client_uploads` | Client-uploaded files | ✅ SSOT | |
| `dewi_maklon_components` | CMT component requests | ✅ SSOT | |
| `wms_cmt_dispatches` | WMS dispatches to CMT vendor | ✅ SSOT (WMS) | |
| `counters` | Sequence numbers | ✅ SSOT (shared) | |

**Deprecated (empty):**
- `dewi_maklon_orders` — replaced by `dewi_maklon_pos` (P1.B)

---

## 3. Key API Endpoints

### Maklon PO 360°
```
GET  /api/dewi/maklon/po-360          — 360° view per PO
GET  /api/dewi/maklon/po-360/{id}     — single PO 360°
GET  /api/dewi/maklon/pos             — list all maklon POs
POST /api/dewi/maklon/pos             — create maklon PO
PUT  /api/dewi/maklon/pos/{id}        — update PO
POST /api/dewi/maklon/pos/{id}/dispatch — dispatch to CMT vendor
```

### CMT Progress
```
GET  /api/dewi/cmt/progress           — list all CMT DOs
POST /api/dewi/cmt/progress           — create DO-CMT (DO-CMT-YYYYMMDD-NNN)
PUT  /api/dewi/cmt/progress/{id}      — update progress
GET  /api/dewi/cmt/progress/{id}      — DO detail with line items
```

### CMT Lifecycle
```
POST /api/dewi/cmt/lifecycle/start    — start CMT production
POST /api/dewi/cmt/lifecycle/{id}/progress — update progress
POST /api/dewi/cmt/lifecycle/{id}/complete — mark complete
```

### CMT Delivery Orders
```
GET  /api/dewi/cmt/delivery-orders    — list CMT DOs
POST /api/dewi/cmt/delivery-orders    — create CMT DO
POST /api/dewi/cmt/delivery-orders/{id}/receive — receive finished goods
```

### CMT QC & Packing
```
GET  /api/dewi/maklon/qc              — QC records
POST /api/dewi/maklon/qc             — create QC entry
GET  /api/dewi/cmt/packing            — packing records
POST /api/dewi/cmt/packing/start      — start packing
```

### Maklon Billing
```
GET  /api/dewi/maklon/billing         — list billing invoices
POST /api/dewi/maklon/billing         — create billing invoice
POST /api/dewi/maklon/billing/{id}/pay — record payment
```

### Client Portal
```
GET  /api/dewi/client-portal/orders   — client's orders (client-auth)
GET  /api/dewi/client-portal/status   — order status summary
POST /api/dewi/client-portal/uploads  — client uploads spec files
```

### Quotes & Samples
```
GET  /api/dewi/maklon/quotes          — list quotes
POST /api/dewi/maklon/quotes          — create quote
GET  /api/dewi/maklon/samples         — list samples
POST /api/dewi/maklon/samples         — create sample request
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `MaklonPO360Module.jsx` | `maklon-po-360` | Maklon PO 360° view |
| `MaklonPOModule.jsx` | `maklon-po` | Maklon PO list |
| `CMTProgressModule.jsx` | `prod-cmt` | CMT progress (in Production portal) |
| `CMTLifecycleModule.jsx` | `prod-cmt-lifecycle` | CMT lifecycle |
| `CMTManagementModule.jsx` | `prod-cmt-mgmt` | CMT management |
| `CMTPackingModule.jsx` | `prod-cmt-packing` | CMT packing |
| `CMTComponentRequestModule.jsx` | `prod-cmt-components` | CMT component requests |
| `MaklonBillingModule.jsx` | `maklon-billing` | Maklon billing |
| `MaklonQCModule.jsx` | `maklon-qc` | Maklon QC |
| `ClientPortalModule.jsx` | `maklon-client-portal` | Client portal |
| `MaklonSamplesModule.jsx` | `maklon-samples` | Sample management |
| `MaklonSLAModule.jsx` | `maklon-sla` | SLA tracking |
| `MaklonFinanceModule.jsx` | `maklon-finance` | Maklon finance |

---

## 5. Business Flows

### As CMT Contractor (Client → Dewi Aditya)
```
Client uploads specs (dewi_client_uploads)
  → Quote prepared (dewi_maklon_quotes)
  → Maklon PO from client (dewi_maklon_pos)
  → Client dispatches fabric → WMS receives
  → CMT Lifecycle: start → cutting → sewing → QC → finish
  → CMT Packing
  → Delivery to client (wms_delivery_notes)
  → Billing (dewi_maklon_billing)
  → Payment received
```

### As Maklon Buyer (Dewi Aditya → CMT Vendor)
```
Maklon PO to vendor (dewi_maklon_pos, type='external_cmt')
  → WMS dispatches fabric to vendor (wms_cmt_dispatches)
  → CMT Progress tracking (dewi_cmt_progress, DO-CMT-YYYYMMDD-NNN)
  → QC at vendor / receive goods
  → WMS receives finished goods
  → Vendor billing → AP Invoice
```

---

## 6. Key Backend Files

| File | Purpose |
|---|---|
| `routes/dewi_maklon_pos.py` | Maklon PO management (SSOT) |
| `routes/dewi_maklon_po_360.py` | 360° view aggregation |
| `routes/dewi_cmt_progress.py` | CMT progress tracking |
| `routes/dewi_cmt_delivery_orders.py` | CMT delivery orders |
| `routes/dewi_cmt_lifecycle.py` | CMT lifecycle state machine |
| `routes/dewi_cmt_packing.py` | CMT packing |
| `routes/dewi_maklon_billing.py` | Billing invoices |
| `routes/dewi_maklon_qc.py` | QC for maklon |
| `routes/dewi_maklon_quote.py` | Quotation management |
| `routes/dewi_maklon_samples.py` | Sample requests |
| `routes/dewi_maklon_sla.py` | SLA management |
| `routes/dewi_maklon_finance.py` | Finance integration |
| `routes/dewi_client_portal.py` | Client portal |
| `routes/dewi_client_uploads.py` | Client file uploads |
| `routes/dewi_cmt_component_requests.py` | CMT component requests |
| `routes/_maklon_adapter.py` | Adapter for legacy maklon_orders → maklon_pos |

---

## 7. Legacy Adapter Note (P1.B)

Session #1 P1.B: `dewi_maklon_orders` deprecated, `dewi_maklon_pos` is now SSOT.  
`_maklon_adapter.py` provides backward-compat adapter for any remaining legacy reads.

---

## 8. Recent Relevant Sessions

- **Session #1 P1.B (2026-05-22):** Maklon Orders Consolidation — `dewi_maklon_orders` → `dewi_maklon_pos`
- **Session #11.16 Phase C (2026-05-25):** Maklon KOL migration via deprecation stub
- **Session #9 (2026-05-24):** Maklon PO 360° view consolidation (P2 #5)
- **Session #2 Phase 4 (2026-05-23):** CMT Lifecycle module full implementation

---

## 9. Notes

- DO-CMT numbers: `DO-CMT-YYYYMMDD-NNN` (via `counters` SSOT, namespace='dewi')
- Maklon billing invoice numbers: sequential via `counters` SSOT
- CMT progress is shown in Production portal (not Maklon portal) — moved during P0 cleanup
- `maklon-cmt` and `maklon-packing` nav items removed from Maklon sidebar in P0 (redirect to Production)
