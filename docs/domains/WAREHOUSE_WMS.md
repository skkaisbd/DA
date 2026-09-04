# Warehouse & WMS Domain — Technical Reference

> **Portal:** Warehouse/Gudang (`warehouse-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready, P3 TD-008 complete

---

## 1. Business Overview

Covers warehouse and inventory management:
- Material receiving (GRN from PO)
- WMS structure (zones, racks, bins)
- Fabric roll management (roll tracking by roll number)
- Inventory stock (material stock per location)
- Stock opname / cycle counting
- Delivery notes (inbound + outbound)
- Picklist management (pick, pack, ship)
- CMT material dispatches (WMS → CMT)
- Capacity planning
- Returns processing
- Smart inventory AI insights

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? |
|---|---|---|
| `rahaza_materials` | Material master | ✅ SSOT (shared with Production) |
| `rahaza_material_stock` | Stock per location | ✅ SSOT |
| `rahaza_material_movements` | Movement log | ✅ SSOT |
| `warehouse_receiving` | GRN / receiving records | ✅ SSOT |
| `wms_structure` | Zone/rack/bin structure | ✅ SSOT |
| `wms_fabric_rolls` | Fabric roll tracking | ✅ SSOT |
| `wms_delivery_notes` | Delivery notes (in/out) | ✅ SSOT |
| `wms_picklists` | Picklist records | ✅ SSOT |
| `wms_cmt_dispatches` | CMT material dispatches | ✅ SSOT |
| `wms_opname2_sessions` | Opname sessions (Gen2) | ✅ SSOT |
| `wms_opname2_items` | Opname line items (Gen2) | ✅ SSOT |
| `wms_capacity_plans` | Zone capacity plans | ✅ SSOT |
| `wms_unit_conversions` | Unit conversion rates | ✅ SSOT |
| `rahaza_wh_returns` | WH return requests | ✅ SSOT |
| `counters` | GR/OP sequence numbers | ✅ SSOT (shared) |

**Deprecated (empty, safe to drop after monitoring):**
- `warehouse_opname` (Gen1) — replaced by `wms_opname2_*`
- `warehouse_opname_items` (Gen1)

---

## 3. Key API Endpoints

### Receiving
```
GET  /api/warehouse/receiving         — list GRNs
POST /api/warehouse/receiving         — create GRN (GR-NNNNN)
POST /api/warehouse/receiving/{id}/confirm — confirm receipt
GET  /api/wms/receiving/pending       — pending receipts
```

### WMS Structure
```
GET  /api/wms/structure               — zone/rack/bin tree
POST /api/wms/structure/zone          — create zone
POST /api/wms/structure/rack          — create rack
POST /api/wms/structure/bin           — create bin
GET  /api/wms/structure/map           — visual map
```

### Fabric Rolls
```
GET  /api/wms/fabric-rolls            — list rolls
POST /api/wms/fabric-rolls            — register roll
GET  /api/wms/fabric-rolls/{id}       — roll detail (scannable)
PUT  /api/wms/fabric-rolls/{id}/status — update status
GET  /api/wms/fabric-rolls/by-material/{material_id} — rolls by material
```

### Delivery Notes
```
GET  /api/wms/delivery-notes          — list DNs
POST /api/wms/delivery-notes          — create DN
GET  /api/wms/delivery-notes/{id}     — DN detail (scannable)
PUT  /api/wms/delivery-notes/{id}/dispatch — dispatch
GET  /api/wms/delivery-notes/pending  — pending dispatch
```

### Opname (Gen2 SSOT — after Session #11.9)
```
GET  /api/wms/opname2/sessions        — list sessions
POST /api/wms/opname2/sessions        — start session (OPN-NNNNN)
GET  /api/wms/opname2/sessions/{id}/items — items to count
POST /api/wms/opname2/sessions/{id}/count — submit count
POST /api/wms/opname2/sessions/{id}/close — finalize session
GET  /api/wms/opname2/sessions/{id}/variance — variance report
```

### Picklist
```
GET  /api/wms/picklists               — list picklists
POST /api/wms/picklists               — create picklist
POST /api/wms/picklists/{id}/pick     — scan & pick item
POST /api/wms/picklists/{id}/pack     — confirm packing
```

### CMT Dispatch
```
GET  /api/wms/cmt-dispatches          — list CMT dispatches
POST /api/wms/cmt-dispatches          — dispatch to CMT vendor
PUT  /api/wms/cmt-dispatches/{id}/return — return from CMT
```

### Labels
```
POST /api/wms/labels/roll             — print roll label
POST /api/wms/labels/dn              — print DN label
GET  /api/wms/labels/templates        — label templates
```

### AI Insights
```
GET  /api/wms/ai/slow-moving          — slow-moving inventory
GET  /api/wms/ai/reorder-suggestions  — reorder point suggestions
GET  /api/wms/ai/stock-health         — stock health overview
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `WarehouseModule.jsx` | `wh-dashboard` | WH overview |
| `FabricRollsModule.jsx` | `wh-fabric-rolls` | Roll tracking |
| `DOManagementModule.jsx` | `wh-delivery-notes` | Delivery notes |
| `PicklistModule.jsx` | `wh-picklist` | Picklist management |
| `OpnameModule.jsx` | `wh-opname` | Stock opname (uses Gen2) |
| `CapacityPlanningModule.jsx` | `wh-capacity` | WMS capacity planning |
| `WMSStructureModule.jsx` | `wh-structure` | Zone/rack/bin setup |
| `ReceivingModule.jsx` | `wh-receiving` | Goods receiving |
| `CMTDispatchModule.jsx` | `wh-cmt-dispatch` | CMT material dispatch |
| `WMSAIInsightsModule.jsx` | `wh-ai-insights` | AI inventory insights |

---

## 5. Business Flows

### Inbound (Purchase → Warehouse)
```
PO Approved (rahaza_pos)
  → GRN Created (warehouse_receiving, GR-NNNNN)
  → Receive + QC Check
  → Stock Updated (rahaza_material_stock)
  → AP Invoice Created (rahaza_ap_invoices)
```

### Outbound (Production Material Issue)
```
Work Order Created
  → Material Reservation (rahaza_material_reservations)
  → Picklist Generated (wms_picklists)
  → Pick + Issue (rahaza_material_issues)
  → Stock Decremented (rahaza_material_stock)
```

### Stock Opname (Cycle Count)
```
1. Start Opname Session (wms_opname2_sessions, OPN-NNNNN)
2. System generates count sheet (items from material_stock)
3. Warehouse staff scans & counts each item
4. System calculates variance (actual - system)
5. Approve → adjustments posted to GL
6. Close session
```

### CMT Dispatch Flow
```
Fabric rolls selected for CMT vendor
  → CMT Dispatch (wms_cmt_dispatches)
  → Rolls marked 'dispatched'
  → CMT vendor processes
  → Return: wms_cmt_dispatches/{id}/return
  → Rolls marked 'returned'
```

---

## 6. Opname Consolidation (Session #11.9)

Before: 3 separate opname systems (`warehouse_opname`, `wh_accessory_opname`, `wh_accessory_opname_items`)
After: 1 SSOT (`wms_opname2_sessions` + `wms_opname2_items`) with `scope` discriminator:
```
scope='material'    — fabric, trims, general inventory
scope='accessory'   — accessories (merged)
scope='fg'          — finished goods
```

---

## 7. Key Backend Files

| File | Purpose |
|---|---|
| `routes/warehouse.py` | Receiving + base WH operations |
| `routes/wms_fabric_rolls.py` | Fabric roll tracking |
| `routes/wms_delivery_notes.py` | Delivery notes |
| `routes/wms_picklist.py` | Picklist management |
| `routes/wms_opname2.py` | Gen2 opname (SSOT) |
| `routes/wms_opname.py` | Gen1 opname (deprecated, kept for compat) |
| `routes/wms_structure.py` | Zone/rack/bin structure |
| `routes/wms_cmt_dispatches.py` | CMT dispatch |
| `routes/wms_receiving.py` | Receiving (Gen2 unified) |
| `routes/wms_capacity_planning.py` | Capacity planning |
| `routes/wms_ai_insights.py` | AI insights |
| `routes/wms_labels.py` | Label printing |
| `routes/wms_units.py` | Unit conversions |
| `routes/rahaza_wh_returns.py` | WH returns |
| `routes/rahaza_inventory_materials.py` | Material master management |
| `routes/rahaza_inventory_stock.py` | Stock management |

---

## 8. Recent Relevant Sessions

- **#11.9 (2026-05-24):** Opname consolidation — 3 systems merged into 1 SSOT (`wms_opname2_*`)
- **#11.16 Phase A (2026-05-25):** Dropped 6 truly orphan collections including legacy WH collections
- **Session #7 (2026-05-23):** Accessory opname migrated to `wms_opname2_*`, old `acc_opname_*` dropped

---

## 9. Notes

- Opname sequence: `OPN-NNNNN` (via `counters` SSOT, namespace='wms')
- GRN sequence: `GR-NNNNN` (via `counters` SSOT, namespace='generic')
- Fabric roll IDs are barcode-scannable (Universal Scan supports `roll` entity type)
- Delivery notes are barcode-scannable (Universal Scan supports `delivery_order` entity type)
- WMS Gen1 collections (`warehouse_opname`, `warehouse_opname_items`) are empty — safe to drop
