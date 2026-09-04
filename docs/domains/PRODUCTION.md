# Production Domain — Technical Reference

> **Portal:** Production (`production-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready, all P1/P2 tasks complete

---

## 1. Business Overview

Covers the full garment production lifecycle:
- Production orders (from rahaza_orders)
- Work order management (WO per style/model)
- Bundle tracking (scanning per bundle)
- Material management (BOM, issues, returns, reservations)
- Cutting operations (plans + execution)
- Line assignments & shift handovers
- QC (inline + AQL sampling)
- WIP monitoring (Andon, OEE, Control Tower)
- CMT/Sub-process production
- Finishing & packing

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? |
|---|---|---|
| `rahaza_orders` | Customer orders | ✅ SSOT |
| `rahaza_work_orders` | Work orders per style/size | ✅ SSOT |
| `rahaza_bundles` | Bundle tracking (BDL-YYYYMMDD-NNNN) | ✅ SSOT |
| `rahaza_wip_events` | WIP scan events per bundle/WO | ✅ SSOT |
| `rahaza_materials` | Material master (fabric, trims, accessories) | ✅ SSOT |
| `rahaza_material_stock` | Material stock per location | ✅ SSOT |
| `rahaza_material_movements` | Material movement log | ✅ SSOT |
| `rahaza_material_issues` | Material issues (MI-NNNNNN) | ✅ SSOT |
| `rahaza_material_reservations` | Material reservations for WOs | ✅ SSOT |
| `production_material_returns` | Material returns from production | ✅ SSOT |
| `rahaza_boms` | Bill of Materials per model/size | ✅ SSOT |
| `rahaza_models` | Style/model master | ✅ SSOT |
| `rahaza_sizes` | Size definitions | ✅ SSOT |
| `rahaza_customers` | Customer master | ✅ SSOT |
| `rahaza_locations` | Storage/production location master | ✅ SSOT |
| `rahaza_processes` | Process definitions (sewing, cutting, etc.) | ✅ SSOT |
| `rahaza_machines` | Machine master | ✅ SSOT |
| `rahaza_lines` | Production line master | ✅ SSOT |
| `rahaza_line_assignments` | Daily line assignment | ✅ SSOT |
| `rahaza_shift_handovers` | Shift handover records | ✅ SSOT |
| `rahaza_downtime_logs` | Machine downtime events | ✅ SSOT |
| `rahaza_rework_records` | Bundle rework tracking | ✅ SSOT |
| `rahaza_qc_events` | QC inspection events | ✅ SSOT |
| `rahaza_aql_samples` | AQL sampling records | ✅ SSOT |
| `rahaza_cutting_plans` | Cutting plans | ✅ SSOT |
| `rahaza_cutting_executions` | Cutting actual execution | ✅ SSOT |
| `rahaza_fg_matrix` | Finished goods matrix | ✅ SSOT |
| `counters` | Sequence counters (BDL, WO, MI numbers) | ✅ SSOT (shared) |

---

## 3. Key API Endpoints

### Work Orders
```
GET  /api/rahaza/work-orders          — list WOs
POST /api/rahaza/work-orders          — create WO
GET  /api/rahaza/work-orders/{id}     — WO detail
PUT  /api/rahaza/work-orders/{id}     — update WO
POST /api/rahaza/work-orders/{id}/start — start WO
POST /api/rahaza/work-orders/{id}/complete — complete WO
```

### Bundles
```
GET  /api/rahaza/bundles              — list bundles
POST /api/rahaza/bundles              — create bundle
GET  /api/rahaza/bundles/{id}         — bundle detail
POST /api/rahaza/bundles/{id}/scan    — scan bundle event
GET  /api/rahaza/bundles/{id}/history — scan history
POST /api/rahaza/bundles/rework       — flag for rework
```

### Material Issues
```
GET  /api/rahaza/material-issues      — list MIs
POST /api/rahaza/material-issues      — create MI (auto MI-NNNNNN)
GET  /api/rahaza/material-issues/{id}
POST /api/rahaza/material-issues/bulk — bulk MI (Sprint 22)
POST /api/rahaza/material-issues/{id}/confirm — confirm issue
```

### Material Returns (Session #11.19)
```
GET  /api/production/material-returns — list returns
POST /api/production/material-returns — create return request
POST /api/production/material-returns/{id}/approve — approve (with approval chain)
POST /api/production/material-returns/{id}/reject
```

### Cutting
```
GET  /api/rahaza/cutting/plans        — list cutting plans
POST /api/rahaza/cutting/plans        — create plan
GET  /api/rahaza/cutting/executions   — list executions
POST /api/rahaza/cutting/execute      — execute cut
GET  /api/rahaza/cutting/hub          — Cutting Hub consolidated view
```

### WIP & Line Monitoring
```
GET  /api/rahaza/wip-events           — list WIP events
POST /api/rahaza/wip-events           — post WIP scan
GET  /api/rahaza/line-monitoring      — live line monitoring
GET  /api/production/control-tower    — Control Tower overview
GET  /api/rahaza/oee                  — OEE metrics
```

### QC
```
GET  /api/qc/events                   — QC events
POST /api/qc/inline                   — inline QC entry
GET  /api/rahaza/aql                  — AQL samples
POST /api/rahaza/aql/sample           — create AQL sample
```

### Production Wizard
```
POST /api/rahaza/wizard/start         — start production wizard
GET  /api/rahaza/wizard/status        — wizard progress
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `ProductionDashboard.jsx` | `production-dashboard` | Production KPI overview |
| `ProductionControlTowerModule.jsx` | `prod-control-tower` | Consolidated control tower |
| `WorkOrderModule.jsx` | `prod-work-orders` | WO management |
| `BundleTrackerModule.jsx` | `prod-bundles` | Bundle scan & tracking |
| `BundleReworkBoard.jsx` | `prod-rework-board` | Rework management |
| `MaterialIssueModule.jsx` | `prod-bulk-mi` | Bulk material issue |
| `MaterialReservationModule.jsx` | `prod-material-reservation` | Material reservation |
| `ProductionMaterialReturnsModule.jsx` | `prod-material-returns` | Material returns |
| `CuttingHubModule.jsx` | `prod-cutting` | Cutting Hub (plans + exec) |
| `LineAssignmentModule.jsx` | `prod-assignments` | Daily line assignment |
| `ShiftHandoverModule.jsx` | `prod-shift-handover` | Shift handover form |
| `ProductionOrdersModule.jsx` | `prod-orders` | Production orders list |
| `AndonBoardModule.jsx` | `prod-andon` | Andon board (live display) |
| `OEEModule.jsx` | `prod-oee` | OEE dashboard |
| `APSGanttModule.jsx` | `prod-aps` | APS Gantt scheduler |
| `RahazaWizardModule.jsx` | `prod-wizard` | Production Wizard |

---

## 5. Business Flows

### Order to Production
```
Customer Order (rahaza_orders)
  → Work Order Created (rahaza_work_orders)
  → BOM Resolved (rahaza_boms)
  → Material Reservation (rahaza_material_reservations)
  → Material Issue (rahaza_material_issues, MI-NNNNNN)
  → Bundle Created (rahaza_bundles, BDL-YYYYMMDD-NNNN)
  → WIP Scanning (rahaza_wip_events per process)
  → QC (rahaza_qc_events + rahaza_aql_samples)
  → Finishing → FG Matrix → Shipment
```

### Cutting Flow (Consolidated — Session #11 Refactor #7)
```
1. Create Cutting Plan (model, sizes, quantity, marker)
2. Fabric Spread Plan (layers, width, efficiency)
3. Execute Cut → record actual vs planned
4. QC Bundles → assign to work orders
5. Bundle barcodes generated for scanning
```

### Material Return Flow (Session #11.19)
```
1. Production requests material return (excess/damaged)
2. Approval chain triggered (if configured)
3. Approved → WMS receives back into stock
4. GL entry: Dr Material Stock / Cr WIP
```

---

## 6. Key Backend Files

| File | Purpose |
|---|---|
| `routes/rahaza_work_orders.py` | Work order CRUD + status machine |
| `routes/rahaza_bundles.py` | Bundle creation + scan events |
| `routes/rahaza_bundles_mgmt.py` | Bundle management operations |
| `routes/rahaza_bundles_rework.py` | Bundle rework board |
| `routes/rahaza_execution.py` | WIP scan execution |
| `routes/production_material_returns.py` | Material return workflow |
| `routes/rahaza_material_reservation.py` | Material reservation |
| `routes/rahaza_inventory_issues.py` | Material issues |
| `routes/dewi_cutting.py` | Cutting plans + execution |
| `routes/production_control_tower.py` | Control Tower aggregation |
| `routes/rahaza_line_monitoring.py` | Line monitoring live data |
| `routes/rahaza_downtime.py` | Downtime logging |
| `routes/rahaza_rework.py` | Rework tracking |
| `routes/rahaza_qc_v2.py` | QC events (v2) |
| `routes/rahaza_aql.py` | AQL sampling |
| `routes/rahaza_bom.py` | BOM management |
| `routes/rahaza_sprint22.py` | Batch MI (bulk issue) |
| `routes/production_jobs.py` | Background production jobs |

---

## 7. Recent Relevant Sessions

- **#11.19 (2026-05-27):** Material returns approval chain, Universal Scan for bundles/WO/MI
- **#11.8 (2026-05-24):** Shipping flow redesign (last P2 consolidation)
- **Session #11 Refactor #7 (2026-05-24):** Cutting Hub consolidation (2 modules → 1 with tabs)
- **Session #9 (2026-05-24):** Production Control Tower (4 views → 1 hub)

---

## 8. Notes

- Bundle numbers: `BDL-YYYYMMDD-NNNN` (daily counter via `counters` SSOT)
- MI numbers: `MI-NNNNNN` (sequential via `counters` SSOT, namespace='rahaza')
- WO numbers: `WO-YYYYMMDD-NNN` (daily counter)
- CMT production is in the **Maklon/CMT** domain (see `MAKLON_CMT.md`)
