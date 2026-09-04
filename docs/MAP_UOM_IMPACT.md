# Peta Dampak Perombakan Satuan (UOM)
Dihasilkan otomatis oleh `scripts/map_uom_impact.py`.
Dipakai sebagai daftar periksa agar perombakan multi-satuan tidak melahirkan bug baru di domain lain.

## Ringkasan

- File backend tersentuh: **132**
- File frontend tersentuh: **64**
- Domain terdampak: **12**

| Domain | File BE | File FE | Titik tulis stok | Sudah sadar pack |
|---|---:|---:|---:|---:|
| Aksesoris | 12 | 7 | 14 | 5 |
| BOM / MRP | 2 | 1 | 0 | 0 |
| Cutting | 1 | 2 | 2 | 2 |
| Finance / HPP | 4 | 2 | 0 | 0 |
| Gudang / WMS | 25 | 9 | 30 | 1 |
| Lain-lain | 40 | 23 | 2 | 1 |
| Maklon / CMT | 18 | 9 | 2 | 0 |
| Marketing | 12 | 0 | 0 | 0 |
| Pengadaan | 2 | 2 | 0 | 0 |
| Pengiriman | 4 | 4 | 1 | 0 |
| Produksi | 8 | 1 | 1 | 0 |
| RnD | 4 | 4 | 0 | 0 |

## Backend — rinci per domain

### Aksesoris

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/dewi_accessories_stock.py` | 7 | 40 | **17** | 2 | 35 | `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |
| `routes/dewi_accessories_items.py` | 8 | 13 | **41** | 1 | 4 | `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |
| `core/accessory_valuation.py` | 6 | 30 | 0 | 0 | 17 | `rahaza_material_movements`, `rahaza_materials` |
| `core/accessory_issue.py` | 5 | 9 | **5** | 1 | 20 | `rahaza_materials` |
| `routes/dewi_accessories_opname.py` | 5 | 10 | 0 | 2 | 18 | `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials`, `wh_opname_sessions2` |
| `routes/dewi_accessories_purchase.py` | 1 | 0 | **13** | 2 | 13 | `acc_purchase_requests`, `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |
| `routes/dewi_accessories_valuation.py` | 3 | 12 | 0 | 0 | 5 | `dewi_provider_config`, `notifications`, `rahaza_material_movements`, `rahaza_materials` |
| `core/accessory_stock.py` | 0 | 0 | 0 | 4 | 13 | `rahaza_locations` |
| `routes/dewi_accessory_requests.py` | 6 | 2 | 0 | 0 | 8 | `dewi_accessory_requests`, `dewi_rnd_styles` |
| `routes/dewi_accessories_dashboard.py` | 3 | 1 | 0 | 0 | 7 | `acc_purchase_requests`, `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |
| `routes/dewi_accessories_loans.py` | 3 | 0 | 0 | 1 | 4 | `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |
| `routes/dewi_accessories_requests.py` | 1 | 0 | 0 | 1 | 2 | `dewi_accessory_requests`, `dewi_asset_loans`, `rahaza_material_movements`, `rahaza_materials` |

### BOM / MRP

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/rahaza_bom.py` | 13 | 0 | 0 | 0 | 21 | `rahaza_boms`, `rahaza_materials`, `rahaza_models`, `rahaza_sizes` |
| `routes/rahaza_material_requirements.py` | 4 | 16 | 0 | 0 | 4 | `po_items`, `production_pos`, `rahaza_boms`, `rahaza_costing_settings`, `rahaza_material_stock` |

### Cutting

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/cutting.py` | 4 | 19 | **8** | 2 | 14 | `rahaza_locations`, `rahaza_material_stock`, `rahaza_materials`, `wh_fabric_roll_movements`, `wh_fabric_rolls` |

### Finance / HPP

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/rahaza_hpp.py` | 5 | 18 | 0 | 0 | 43 | `dewi_hpp_snapshots_maklon`, `dewi_hpp_snapshots_po`, `dewi_maklon_clients`, `dewi_maklon_material_issues`, `production_pos` |
| `routes/rahaza_posting.py` | 0 | 25 | 0 | 0 | 35 | `production_job_items`, `rahaza_ar_invoices`, `rahaza_cash_accounts`, `rahaza_channel_gl_mapping`, `rahaza_coa_accounts` |
| `routes/rahaza_ap_from_gr.py` | 4 | 14 | 0 | 0 | 6 | `rahaza_ap_invoices`, `rahaza_purchase_orders`, `warehouse_receiving` |
| `routes/rahaza_finance.py` | 2 | 0 | 0 | 0 | 12 | `rahaza_ap_invoices`, `rahaza_ar_invoices`, `rahaza_cash_accounts`, `rahaza_cash_movements`, `rahaza_cost_centers` |

### Gudang / WMS

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/wms_quarantine.py` | 7 | 6 | 0 | 0 | 51 | `rahaza_material_movements` |
| `routes/wms_receiving.py` | 14 | 0 | 0 | 4 | 43 | `rahaza_fg_movements`, `rahaza_locations`, `rahaza_material_stock`, `rahaza_materials`, `wh_pending_movements` |
| `routes/wms_opname3.py` | 10 | 7 | 0 | 1 | 34 | `rahaza_materials`, `wh_buildings`, `wh_racks`, `wh_zones` |
| `core/quarantine.py` | 5 | 9 | 0 | 5 | 32 | `rahaza_locations`, `rahaza_materials` |
| `routes/warehouse.py` | 7 | 2 | 0 | 4 | 30 | `rahaza_fixed_assets`, `rahaza_material_movements`, `rahaza_material_stock`, `rahaza_materials`, `rahaza_purchase_orders` |
| `routes/rahaza_inventory_materials.py` | 3 | 11 | **23** | 0 | 2 | `rahaza_material_categories`, `rahaza_material_stock`, `rahaza_materials` |
| `routes/rahaza_inventory_stock.py` | 8 | 2 | 0 | 4 | 25 | `rahaza_locations`, `rahaza_material_movements`, `rahaza_material_stock`, `rahaza_materials`, `wh_zones` |
| `routes/wms_units.py` | 1 | 0 | 0 | 0 | 7 | `wh_unit_conversions`, `wh_unit_master` |
| `routes/wms_putaway.py` | 7 | 0 | 0 | 0 | 26 | `rahaza_materials`, `wh_buildings`, `wh_placement_movements`, `wh_positions`, `wh_racks` |
| `routes/dewi_warehouse_smart.py` | 10 | 0 | 0 | 8 | 9 | `rahaza_material_stock`, `rahaza_materials`, `rahaza_racks`, `rahaza_stock_ledger` |
| `routes/wms_picklist.py` | 12 | 0 | 0 | 0 | 12 | `dewi_material_issues`, `rahaza_material_issues`, `rahaza_shipments`, `wh_pending_movements`, `wh_picklists` |
| `routes/wms_fabric_rolls.py` | 1 | 5 | 0 | 0 | 16 | `wh_fabric_roll_movements`, `wh_fabric_rolls` |
| `routes/rahaza_inventory_fg.py` | 2 | 0 | 0 | 1 | 16 | `rahaza_customers`, `rahaza_fg_issues`, `rahaza_fg_movements`, `rahaza_locations`, `rahaza_material_stock` |
| `routes/wms_structure.py` | 6 | 0 | 0 | 0 | 11 | `rahaza_locations`, `rahaza_materials`, `wh_buildings`, `wh_location_migration_map`, `wh_positions` |
| `routes/rahaza_inventory_issues.py` | 0 | 0 | 0 | 1 | 15 | `rahaza_material_issues`, `rahaza_material_stock`, `wh_pending_movements` |
| `routes/wms_cmt_dispatches.py` | 3 | 2 | 0 | 0 | 11 | `rahaza_materials`, `wh_cmt_dispatches`, `wh_delivery_notes` |
| `routes/wms_audit.py` | 0 | 0 | 0 | 0 | 15 | `rahaza_fg_movements`, `wh_positions`, `wh_rca_audit` |
| `routes/rahaza_inventory_workflow.py` | 0 | 0 | 0 | 1 | 13 | `rahaza_material_issues`, `rahaza_material_movements`, `rahaza_material_stock` |
| `routes/rahaza_inventory_shared.py` | 3 | 0 | 0 | 1 | 6 | `rahaza_locations`, `rahaza_material_movements`, `rahaza_material_stock`, `rahaza_materials` |
| `routes/unified_inventory.py` | 0 | 0 | 0 | 0 | 10 | `rahaza_material_movements`, `rahaza_material_stock` |
| `routes/wms_delivery_notes.py` | 2 | 0 | 0 | 0 | 7 | `rahaza_materials`, `wh_delivery_notes` |
| `routes/wms_material_labels.py` | 0 | 0 | 0 | 0 | 7 | `rahaza_material_stock`, `rahaza_materials`, `wh_positions` |
| `routes/wms_capacity_planning.py` | 0 | 0 | 0 | 0 | 5 | `capacity_config`, `rahaza_employees`, `rahaza_machine_downtime`, `rahaza_wip_events`, `rahaza_work_orders` |
| `routes/wms_fg_labels.py` | 0 | 0 | 0 | 0 | 2 | `rahaza_fg_matrix` |
| `routes/wms_stock_schema.py` | 0 | 0 | 0 | 0 | 1 | — |

### Lain-lain

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `core/stock_service.py` | 0 | 0 | 0 | 0 | 112 | — |
| `routes/dewi_demo_seed.py` | 0 | 0 | 0 | 0 | 46 | `dewi_cmt_deliveries`, `dewi_cmt_jobs`, `dewi_cmt_partners`, `dewi_cmt_payments`, `dewi_cutting_batches` |
| `core/stock_reconcile.py` | 3 | 0 | 0 | 0 | 33 | `rahaza_locations`, `rahaza_materials` |
| `routes/operations_pdf.py` | 10 | 0 | 0 | 0 | 21 | `accessory_shipment_items`, `accessory_shipments`, `buyer_shipment_items`, `buyer_shipments`, `company_settings` |
| `routes/rahaza_fg_matrix.py` | 4 | 0 | 0 | 0 | 23 | `rahaza_fg_movements`, `rahaza_fg_reservations`, `rahaza_material_stock`, `rahaza_materials`, `rahaza_sizes` |
| `routes/rahaza_reports.py` | 1 | 0 | 0 | 0 | 25 | `rahaza_ap_invoices`, `rahaza_ar_invoices`, `rahaza_attendance_events`, `rahaza_cash_accounts`, `rahaza_customers` |
| `routes/rahaza_grn_qc.py` | 1 | 0 | 0 | 0 | 19 | `rahaza_grn_inspections`, `warehouse_receiving` |
| `routes/rahaza_payroll_shared.py` | 4 | 0 | 0 | 0 | 15 | `da_payroll_allowances`, `dewi_kasbon_requests`, `rahaza_attendance_events`, `rahaza_leave_requests`, `rahaza_leave_types` |
| `routes/rahaza_sprint22.py` | 6 | 0 | 0 | 0 | 12 | `rahaza_boms`, `rahaza_employees`, `rahaza_line_assignments`, `rahaza_lines`, `rahaza_material_issues` |
| `routes/rahaza_admin_shared.py` | 8 | 8 | 0 | 0 | 0 | — |
| `routes/exceptions.py` | 2 | 7 | 0 | 0 | 6 | `accessory_shipment_items`, `buyer_shipment_items`, `material_defect_reports`, `material_requests`, `po_items` |
| `routes/rahaza_admin_helpers.py` | 7 | 2 | 0 | 0 | 5 | `rahaza_boms`, `rahaza_cash_accounts`, `rahaza_coa_accounts`, `rahaza_cost_centers`, `rahaza_customers` |
| `routes/rahaza_setup.py` | 2 | 4 | 0 | 0 | 8 | `rahaza_boms`, `rahaza_employees`, `rahaza_lines`, `rahaza_locations`, `rahaza_materials` |
| `core/stock_schema.py` | 0 | 0 | 0 | 2 | 10 | — |
| `routes/dashboard_routes.py` | 2 | 0 | 0 | 0 | 8 | `attachments`, `production_job_items`, `production_jobs`, `rahaza_ap_invoices`, `rahaza_ar_invoices` |
| `routes/rahaza_alerts.py` | 1 | 0 | 0 | 0 | 8 | `rahaza_alert_settings`, `rahaza_employees`, `rahaza_line_assignments`, `rahaza_lines`, `rahaza_material_stock` |
| `routes/dewi_phase7_reports.py` | 0 | 0 | 0 | 0 | 7 | `dewi_cmt_delivery_orders`, `dewi_cmt_jobs`, `dewi_cmt_progress_reports`, `dewi_maklon_dispatches`, `dewi_maklon_invoices` |
| `routes/fg_matrix_seed.py` | 2 | 0 | 0 | 0 | 5 | `rahaza_locations`, `rahaza_material_stock`, `rahaza_materials` |
| `routes/operations_excel.py` | 0 | 0 | 0 | 0 | 7 | `buyer_shipment_items`, `buyer_shipments`, `po_items`, `production_job_items`, `production_pos` |
| `routes/rahaza_orders.py` | 0 | 0 | 0 | 0 | 7 | `rahaza_customers`, `rahaza_models`, `rahaza_orders`, `rahaza_sizes` |
| `routes/operations_reports.py` | 2 | 0 | 0 | 0 | 4 | `accessory_shipment_items`, `accessory_shipments`, `buyer_shipment_items`, `buyer_shipments`, `material_defect_reports` |
| `routes/universal_scan.py` | 2 | 0 | 0 | 0 | 4 | `dewi_assets`, `dewi_cmt_delivery_orders`, `dewi_delivery_orders`, `dewi_universal_scans`, `rahaza_bundles` |
| `routes/operations_serials.py` | 0 | 0 | 0 | 0 | 5 | `buyer_shipment_items`, `buyer_shipments`, `po_items`, `production_job_items`, `production_jobs` |
| `routes/rahaza_next_actions.py` | 0 | 0 | 0 | 0 | 5 | `rahaza_line_assignments`, `rahaza_lines`, `rahaza_material_issues`, `rahaza_material_stock`, `rahaza_materials` |
| `routes/rahaza_notifications.py` | 0 | 0 | 0 | 0 | 5 | `notifications`, `rahaza_work_orders` |
| `routes/dewi_executive_report.py` | 0 | 0 | 0 | 0 | 4 | `dewi_maklon_pos`, `marketing_kol_campaigns`, `marketing_live_sessions`, `marketing_orders`, `rahaza_ar_invoices` |
| `routes/dewi_kpi_reports.py` | 4 | 0 | 0 | 0 | 0 | `da_kpi_goals`, `da_kpi_perform`, `da_kpi_periods`, `da_kpi_results`, `da_kpi_submissions` |
| `routes/dewi_wh_returns.py` | 0 | 0 | 0 | 0 | 4 | `marketing_returns`, `rahaza_fg_inventory`, `rahaza_fg_movements`, `wh_returns` |
| `routes/operations_import.py` | 1 | 0 | 0 | 0 | 3 | `garments`, `po_items`, `product_variants`, `production_pos`, `products` |
| `routes/analytics_ai.py` | 0 | 0 | 0 | 0 | 3 | `ai_rca_history`, `rahaza_defect_codes`, `rahaza_lines`, `rahaza_models`, `rahaza_qc_events` |
| `routes/dewi_org.py` | 3 | 0 | 0 | 0 | 0 | `dewi_org_positions`, `dewi_org_units`, `rahaza_employees` |
| `core/material_fields.py` | 1 | 1 | 0 | 0 | 0 | — |
| `routes/operations_pdf_configs.py` | 0 | 0 | 0 | 0 | 2 | `pdf_export_configs` |
| `routes/rahaza_payroll_payslips.py` | 1 | 0 | 0 | 0 | 1 | `rahaza_payroll_runs`, `rahaza_payslips` |
| `routes/data_transfer.py` | 0 | 1 | 0 | 0 | 0 | — |
| `routes/dewi_kreator_requests.py` | 0 | 0 | 0 | 0 | 1 | `dewi_kreator_requests` |
| `routes/rahaza_ai.py` | 0 | 0 | 0 | 0 | 1 | `rahaza_ai_audit_logs`, `rahaza_ai_chat_history` |
| `routes/rahaza_payroll_runs.py` | 0 | 0 | 0 | 0 | 1 | `rahaza_coa_accounts`, `rahaza_employees`, `rahaza_payroll_profiles`, `rahaza_payroll_runs`, `rahaza_payslips` |
| `routes/rahaza_shift_handover.py` | 0 | 0 | 0 | 0 | 1 | `rahaza_handover_templates`, `rahaza_shift_handovers`, `rahaza_shifts`, `rahaza_work_orders` |
| `routes/vendor_portal.py` | 0 | 0 | 0 | 0 | 1 | `rahaza_models`, `users`, `vendor_jobs`, `vendor_partners`, `vendor_progress_reports` |

### Maklon / CMT

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/dewi_cmt_permak.py` | 0 | 0 | 0 | 0 | 49 | `cmt_receipt_lines`, `cmt_receipts`, `dewi_cmt_permak`, `dewi_system_config`, `po_items` |
| `routes/dewi_maklon.py` | 4 | 0 | 0 | 0 | 35 | `dewi_maklon_clients`, `dewi_maklon_material_issues`, `dewi_provider_config`, `rahaza_materials`, `rahaza_processes` |
| `routes/maklon_seed.py` | 11 | 2 | 0 | 0 | 17 | `buyer_shipment_items`, `buyer_shipments`, `dewi_maklon_bom_templates`, `dewi_maklon_pos`, `po_accessories` |
| `routes/dewi_maklon_pos.py` | 4 | 0 | 0 | 0 | 24 | `dewi_maklon_advance_payments`, `dewi_maklon_bom`, `dewi_maklon_buyer_catalog`, `dewi_maklon_clients`, `dewi_maklon_dispatches` |
| `routes/dewi_cmt_packing.py` | 2 | 0 | 0 | 2 | 22 | `buyer_shipment_items`, `buyer_shipments`, `cmt_receipt_lines`, `cmt_receipts`, `rahaza_fg_movements` |
| `routes/production_maklon_bridge.py` | 0 | 0 | 0 | 0 | 24 | `buyer_shipment_items`, `buyer_shipments`, `cmt_receipt_lines`, `cmt_receipts`, `dewi_cmt_partners` |
| `routes/dewi_cmt_lifecycle.py` | 0 | 0 | 0 | 0 | 16 | `cmt_receipts`, `dewi_cmt_delivery_orders`, `dewi_cmt_jobs`, `dewi_cmt_partners`, `dewi_cmt_payments` |
| `routes/_maklon_adapter.py` | 0 | 0 | 0 | 0 | 15 | `dewi_maklon_pos` |
| `routes/dewi_maklon_quote.py` | 0 | 0 | 0 | 0 | 9 | — |
| `routes/dewi_cmt_component_requests.py` | 4 | 0 | 0 | 0 | 4 | `dewi_cmt_component_requests` |
| `routes/maklon_client_tracking.py` | 0 | 0 | 0 | 0 | 7 | `buyer_shipment_items`, `buyer_shipments`, `po_items`, `production_job_items`, `production_pos` |
| `routes/dewi_maklon_billing.py` | 1 | 2 | 0 | 0 | 3 | `company_settings`, `dewi_maklon_clients`, `dewi_maklon_hpp`, `dewi_maklon_invoices`, `dewi_maklon_payments` |
| `routes/dewi_maklon_qc.py` | 0 | 0 | 0 | 0 | 4 | `dewi_maklon_qc_checks`, `dewi_system_config` |
| `routes/dewi_maklon_po_360.py` | 0 | 1 | 0 | 0 | 2 | `activity_logs`, `dewi_maklon_bom`, `dewi_maklon_dispatches`, `dewi_maklon_invoices`, `dewi_maklon_material_receive` |
| `routes/dewi_maklon_bom_templates.py` | 2 | 0 | 0 | 0 | 0 | `dewi_maklon_bom`, `dewi_maklon_bom_templates`, `dewi_maklon_buyer_catalog`, `dewi_maklon_pos` |
| `routes/dewi_maklon_buyer_catalog.py` | 0 | 0 | 0 | 0 | 2 | `attachments`, `dewi_maklon_buyer_catalog`, `dewi_maklon_clients`, `dewi_maklon_samples`, `rahaza_colors` |
| `routes/cmt_belanja.py` | 0 | 0 | 0 | 0 | 1 | — |
| `routes/dewi_maklon_sla.py` | 0 | 0 | 0 | 0 | 1 | `dewi_maklon_clients` |

### Marketing

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/marketing_discounts_routes.py` | 11 | 0 | 0 | 0 | 0 | `marketing_discounts` |
| `routes/marketing_catalog_stock.py` | 0 | 0 | 0 | 0 | 8 | `marketing_catalog_items`, `marketing_catalogs`, `marketing_platform_accounts`, `marketing_stock_syncs`, `rahaza_material_stock` |
| `routes/marketing_catalog_items.py` | 2 | 0 | 0 | 0 | 4 | `marketing_catalog_items`, `marketing_catalogs`, `rahaza_locations`, `rahaza_material_stock`, `rahaza_materials` |
| `routes/marketing_orders_routes.py` | 0 | 0 | 0 | 0 | 6 | `marketing_orders` |
| `routes/marketing_catalog_mgmt.py` | 0 | 0 | 0 | 0 | 4 | `marketing_catalog_items`, `marketing_catalogs`, `marketing_platform_accounts`, `marketing_stock_syncs`, `rahaza_locations` |
| `routes/marketing_catalog_shared.py` | 0 | 0 | 0 | 0 | 3 | `marketing_catalog_items`, `marketing_catalogs` |
| `routes/marketing_returns_routes.py` | 1 | 0 | 0 | 0 | 2 | `marketing_platform_accounts`, `marketing_returns`, `rahaza_credit_notes`, `rahaza_customers`, `wh_returns` |
| `routes/marketing_webhooks.py` | 0 | 0 | 0 | 0 | 3 | `marketing_orders`, `marketing_webhook_events` |
| `routes/_toko_adapter.py` | 0 | 0 | 0 | 0 | 2 | `marketing_catalogs` |
| `routes/marketing_import.py` | 0 | 0 | 0 | 0 | 2 | `marketing_import_history`, `marketing_import_templates`, `marketing_import_uploads`, `marketing_platform_accounts`, `marketing_sales_data` |
| `routes/marketing_complaints_routes.py` | 0 | 0 | 0 | 0 | 1 | `marketing_complaints`, `marketing_platform_accounts` |
| `routes/marketing_product_launches_routes.py` | 1 | 0 | 0 | 0 | 0 | `marketing_product_launches`, `rahaza_materials` |

### Pengadaan

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/rahaza_po.py` | 10 | 13 | 0 | 0 | 36 | `rahaza_materials`, `rahaza_purchase_orders`, `warehouse_receiving` |
| `routes/dewi_procurement.py` | 4 | 1 | 0 | 0 | 7 | `comm_channels`, `comm_conversations`, `comm_messages`, `dewi_procurement_requests`, `rahaza_purchase_orders` |

### Pengiriman

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/buyer_shipment.py` | 0 | 0 | 0 | 0 | 40 | `buyer_shipment_items`, `buyer_shipments`, `cmt_receipt_lines`, `cmt_receipts`, `po_items` |
| `routes/rahaza_shipments.py` | 0 | 0 | 0 | 0 | 21 | `company_settings`, `rahaza_ar_invoices`, `rahaza_customers`, `rahaza_model_variants`, `rahaza_models` |
| `routes/fulfillment.py` | 0 | 0 | 0 | 1 | 10 | `marketing_orders`, `rahaza_material_stock`, `rahaza_shipments`, `wh_pending_movements` |
| `routes/vendor_shipment.py` | 5 | 0 | 0 | 0 | 6 | `accessory_shipment_items`, `material_requests`, `po_accessories`, `po_items`, `production_job_items` |

### Produksi

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/production_internal_adapter.py` | 10 | 9 | 0 | 0 | 39 | `po_accessories`, `po_items`, `production_job_items`, `production_jobs`, `production_pos` |
| `routes/production_pos.py` | 7 | 7 | 0 | 0 | 35 | `buyer_shipment_items`, `buyer_shipments`, `dewi_accessory_requests`, `material_defect_reports`, `po_accessories` |
| `routes/production_execution.py` | 2 | 0 | 0 | 0 | 26 | `buyer_shipment_items`, `dewi_maklon_buyer_catalog`, `garments`, `material_defect_reports`, `po_items` |
| `routes/dewi_production_reports.py` | 0 | 5 | 0 | 0 | 21 | `dewi_maklon_clients`, `dewi_maklon_material_issues`, `production_pos`, `rahaza_material_issues`, `rahaza_models` |
| `routes/production_material_returns.py` | 0 | 0 | 0 | 1 | 12 | `production_material_returns`, `rahaza_locations`, `rahaza_material_issues`, `rahaza_material_movements`, `rahaza_materials` |
| `routes/rahaza_production.py` | 0 | 0 | 0 | 0 | 11 | `attachments`, `rahaza_line_assignments`, `rahaza_lines`, `rahaza_models`, `rahaza_processes` |
| `routes/production_stage_tracking.py` | 0 | 0 | 0 | 0 | 8 | `po_items`, `production_pos`, `rahaza_orders`, `rahaza_processes`, `rahaza_wip_events` |
| `routes/production_control_tower.py` | 0 | 0 | 0 | 0 | 6 | `cmt_receipts`, `dewi_maklon_pos`, `rahaza_bundles`, `rahaza_work_orders` |

### RnD

| File | unit | unit_cost | pack | tulis stok | qty | Koleksi disentuh |
|---|---:|---:|---:|---:|---:|---|
| `routes/dewi_rnd_hpp.py` | 2 | 27 | 0 | 0 | 8 | `dewi_rnd_hpp`, `dewi_rnd_materials`, `dewi_rnd_tech_packs`, `marketing_catalog_items`, `rahaza_materials` |
| `routes/dewi_rnd_overview.py` | 3 | 3 | 0 | 0 | 5 | `dewi_rnd_hpp`, `dewi_rnd_materials`, `dewi_rnd_patterns`, `dewi_rnd_revisions`, `dewi_rnd_sample_costing` |
| `routes/dewi_rnd_techpack_import.py` | 1 | 0 | 0 | 0 | 1 | `dewi_rnd_styles`, `dewi_rnd_tech_packs`, `dewi_rnd_variants` |
| `routes/marketing_samples_routes.py` | 0 | 0 | 0 | 0 | 2 | `marketing_samples` |

## Frontend — rinci per domain

### Aksesoris  (7 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/AccessoryModule.jsx` | 35 | **58** | 28 |
| `components/erp/accessory/AccessoryValuationTab.jsx` | 13 | 0 | 14 |
| `components/erp/AccessoryRequestInbox.jsx` | 2 | 0 | 2 |
| `components/erp/accessory/AccessoryValuationLedger.jsx` | 2 | 0 | 2 |
| `components/erp/AccessoriesDashboard.jsx` | 1 | 0 | 0 |
| `components/erp/AccessoriesReports.jsx` | 1 | 0 | 6 |
| `components/erp/accessory/AccessoryValuationAutomation.jsx` | 1 | 0 | 0 |

### BOM / MRP  (1 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/RahazaBOMModuleV2.jsx` | 6 | 0 | 15 |

### Cutting  (2 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/cutting/CuttingOrdersModule.jsx` | 7 | **4** | 3 |
| `components/erp/cutting/CuttingDashboard.jsx` | 4 | 0 | 0 |

### Finance / HPP  (2 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/RahazaHPPModule.jsx` | 2 | 0 | 11 |
| `components/erp/FinanceKasbonModule.jsx` | 1 | 0 | 3 |

### Gudang / WMS  (9 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/UnifiedInventoryModule.jsx` | 11 | 0 | 7 |
| `components/erp/ReceivingModule.jsx` | 9 | 0 | 7 |
| `components/erp/PutAwayModule.jsx` | 5 | 0 | 12 |
| `components/erp/QuarantineModule.jsx` | 5 | 0 | 30 |
| `components/erp/WarehouseSmartModule.jsx` | 4 | 0 | 2 |
| `components/erp/WMSPickListModule.jsx` | 3 | 0 | 8 |
| `components/erp/InventoryScrapModule.jsx` | 1 | 0 | 17 |
| `components/erp/WarehouseDashboard.jsx` | 1 | 0 | 1 |
| `components/erp/engine/VendorReceiving.jsx` | 1 | 0 | 0 |

### Lain-lain  (23 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/RahazaMaterialsModule.jsx` | 8 | **28** | 2 |
| `components/erp/WMSModule.jsx` | 23 | 0 | 14 |
| `components/erp/RahazaStockModule.jsx` | 8 | 0 | 36 |
| `components/erp/RahazaMaterialRequirementsModule.jsx` | 5 | 0 | 7 |
| `components/erp/OKRTrackerModule.jsx` | 4 | 0 | 0 |
| `components/erp/bom/InlineMaterialPicker.jsx` | 4 | 0 | 0 |
| `components/erp/engine/VendorMaterialInspection.jsx` | 4 | 0 | 3 |
| `components/erp/HRKPIModule.jsx` | 3 | 0 | 1 |
| `components/erp/ThreeWayMatchModule.jsx` | 3 | 0 | 4 |
| `components/erp/WMSFabricRollsModule.jsx` | 3 | 0 | 7 |
| `components/erp/asset/dialogs/CreatePRDialog.jsx` | 3 | 0 | 8 |
| `components/erp/FGProductPickerDialog.jsx` | 2 | 0 | 5 |
| `components/erp/HROrgChartModule.jsx` | 2 | 0 | 0 |
| `components/erp/RahazaMaterialIssueModule.jsx` | 2 | 0 | 7 |
| `components/erp/ReportsModule.jsx` | 2 | 0 | 18 |
| `components/erp/bom/RequirementsPreviewCard.jsx` | 2 | 0 | 6 |
| `components/erp/marketing/DiscountCampaignModule.jsx` | 2 | 0 | 0 |
| `components/client/ClientInvoices.jsx` | 1 | 0 | 2 |
| `components/erp/CatalogManagementModule.jsx` | 1 | 0 | 13 |
| `components/erp/HRKasbonModule.jsx` | 1 | 0 | 1 |
| `components/erp/StockSchemaHealthModule.jsx` | 1 | 0 | 8 |
| `components/erp/asset/drawers/PRDetailDrawer.jsx` | 1 | 0 | 1 |
| `components/erp/portal/MyAnnualReviewModule.jsx` | 1 | 0 | 0 |

### Maklon / CMT  (9 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/MaklonMaterialIssuePanel.jsx` | 8 | 0 | 17 |
| `components/erp/MaklonPOModule.jsx` | 6 | 0 | 30 |
| `components/erp/WMSCMTDispatchesModule.jsx` | 6 | 0 | 25 |
| `components/erp/CMTComponentRequestModule.jsx` | 5 | 0 | 9 |
| `components/erp/CMTMonitorModule.jsx` | 3 | 0 | 6 |
| `components/erp/MaklonHppModule.jsx` | 3 | 0 | 13 |
| `components/erp/MaklonBuyerCatalogDetailDialog.jsx` | 2 | 0 | 1 |
| `components/erp/MaklonBillingModule.jsx` | 1 | 0 | 4 |
| `components/erp/MaklonPO360Module.jsx` | 1 | 0 | 8 |

### Pengadaan  (2 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/PurchaseOrderModule.jsx` | 6 | 0 | 5 |
| `components/erp/ProcurementRequestModule.jsx` | 5 | 0 | 8 |

### Pengiriman  (4 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/WMSDeliveryNotesModule.jsx` | 5 | 0 | 16 |
| `components/erp/engine/VendorShipmentModule.jsx` | 3 | 0 | 16 |
| `components/erp/FulfillmentModule.jsx` | 1 | 0 | 4 |
| `components/erp/RahazaShipmentsModule.jsx` | 1 | 0 | 20 |

### Produksi  (1 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/engine/ProductionPOModule.jsx` | 5 | 0 | 34 |

### RnD  (4 file)

| File | tampil satuan | pack-aware | qty |
|---|---:|---:|---:|
| `components/erp/RnDCostingTab.jsx` | 8 | 0 | 16 |
| `components/erp/RnDTechPackModule.jsx` | 5 | 0 | 7 |
| `components/erp/RnDSamplesTab.jsx` | 2 | 0 | 9 |
| `components/erp/RnDStyleDetailPage.jsx` | 1 | 0 | 1 |

