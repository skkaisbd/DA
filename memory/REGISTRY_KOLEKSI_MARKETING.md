# REGISTRY KOLEKSI — domain Marketing (dihasilkan mesin, jangan diketik ulang)

Sumber: `memory/FORENSIC_SSOT_V3.json` (dibuat `scripts/_forensic_ssot_v3.py`). Dipakai untuk mengisi `backend/core/collection_registry.py` (F0.1).

Total koleksi `marketing_*` yang disebut kode: **49**

| Koleksi | dok di DB | penulis (berkas) | pembaca (berkas) | catatan |
|---|---|---|---|---|
| `marketing_ab_experiments` | — | 1: routes/marketing_advanced_ai_routes.py | 1: routes/marketing_advanced_ai_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_account_health` | 0 | 2: routes/marketing_account_health_routes.py, routes/marketing_reports.py | 3: routes/marketing_account_health_routes.py, routes/marketing_ai_insights_routes.py, routes/marketing_reports.py | OK |
| `marketing_account_targets` | — | 1: routes/marketing_targets.py | 2: routes/marketing_reports.py, routes/marketing_targets.py | belum ada di DB |
| `marketing_ads_data` | 0 | 1: routes/marketing_ads_routes.py | 1: routes/marketing_ads_routes.py | PULAU (1 berkas) |
| `marketing_ai_content_history` | — | 1: routes/marketing_ai_content_tools.py | 1: routes/marketing_ai_content_tools.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_alert_runs` | 1 | 1: routes/marketing_alerts.py | 1: routes/marketing_alerts.py | PULAU (1 berkas) |
| `marketing_alert_settings` | 1 | 1: routes/marketing_alerts.py | 1: routes/marketing_alerts.py | PULAU (1 berkas) |
| `marketing_budgets` | — | 1: routes/marketing_budget.py | 1: routes/marketing_budget.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_catalog_items` | 0 | 9: core/catalog_stock.py, core/marketing_master_seed.py, core/product_master.py … | 16: core/marketing_live_products.py, core/marketing_master_seed.py, core/order_status.py … | OK |
| `marketing_catalogs` | 0 | 7: core/marketing_master_seed.py, poc_variant_ssot.py, routes/_toko_adapter.py … | 8: core/marketing_live_products.py, core/marketing_master_seed.py, routes/_toko_adapter.py … | OK |
| `marketing_churn_scores` | — | 1: routes/marketing_advanced_ai_routes.py | 1: routes/marketing_advanced_ai_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_complaints` | 0 | 2: routes/marketing_complaints_routes.py, routes/marketing_reports.py | 5: routes/marketing_advanced_ai_routes.py, routes/marketing_ai_insights_routes.py, routes/marketing_alerts.py … | OK |
| `marketing_content_calendar` | 0 | 1: routes/marketing_content_calendar_routes.py | 3: routes/marketing_ai_insights_routes.py, routes/marketing_alerts.py, routes/marketing_content_calendar_routes.py | OK |
| `marketing_creator_catalog` | — | 1: routes/marketing_kol_ops.py | 2: routes/marketing_kol_ops.py, routes/marketing_kol_portal.py | belum ada di DB |
| `marketing_creator_item_requests` | 0 | 2: routes/marketing_kol_ops.py, routes/marketing_kol_portal.py | 2: routes/marketing_kol_ops.py, routes/marketing_kol_portal.py | OK |
| `marketing_creator_sessions` | 0 | 2: routes/marketing_kol_ops.py, routes/marketing_kol_portal.py | 7: routes/marketing_budget.py, routes/marketing_kol_creators.py, routes/marketing_kol_leaderboard.py … | OK |
| `marketing_creator_targets` | — | 1: routes/marketing_targets.py | 1: routes/marketing_targets.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_data_import_sessions` | — | 1: routes/marketing_data_import.py | 1: routes/marketing_data_import.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_discounts` | — | 1: routes/marketing_discounts_routes.py | 3: routes/marketing_ai_insights_routes.py, routes/marketing_alerts.py, routes/marketing_discounts_routes.py | belum ada di DB |
| `marketing_dynamic_pricing_events` | — | 1: routes/marketing_advanced_ai_routes.py | 1: routes/marketing_advanced_ai_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_dynamic_pricing_settings` | — | 1: routes/marketing_advanced_ai_routes.py | 1: routes/marketing_advanced_ai_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_dynamic_pricing_suggestions` | — | 1: routes/marketing_advanced_ai_routes.py | 1: routes/marketing_advanced_ai_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_import_history` | — | 1: routes/marketing_import.py | 1: routes/marketing_import.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_import_sessions` | 0 | 1: routes/universal_import.py | 1: routes/universal_import.py | PULAU (1 berkas) |
| `marketing_import_templates` | 0 | 2: routes/marketing_import.py, routes/universal_import.py | 2: routes/marketing_import.py, routes/universal_import.py | OK |
| `marketing_import_uploads` | 0 | 1: routes/marketing_import.py | 1: routes/marketing_import.py | PULAU (1 berkas) |
| `marketing_integration_settings` | — | 1: routes/marketing_integration_settings_routes.py | 1: routes/marketing_integration_settings_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_kol_campaigns` | — | 0: — | 1: routes/dewi_executive_report.py | **tak pernah ditulis** · PULAU (1 berkas) · belum ada di DB |
| `marketing_kol_creators` | 0 | 5: core/marketing_master_seed.py, routes/marketing_budget.py, routes/marketing_kol_creators.py … | 9: core/marketing_account_scope.py, core/marketing_master_seed.py, routes/marketing_budget.py … | OK |
| `marketing_kol_login_attempts` | 0 | 1: routes/marketing_kol_shared.py | 1: routes/marketing_kol_shared.py | PULAU (1 berkas) |
| `marketing_live_session_products` | — | 1: core/marketing_live_products.py | 1: core/marketing_live_products.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_live_sessions` | 0 | 2: core/marketing_live_products.py, routes/marketing_live_sessions_routes.py | 7: core/marketing_live_products.py, routes/dewi_executive_report.py, routes/dewi_management_tools.py … | OK |
| `marketing_livehost_scripts` | 0 | 1: routes/marketing_livehost_scripts.py | 2: routes/marketing_livehost_portal.py, routes/marketing_livehost_scripts.py | OK |
| `marketing_livehost_shifts` | 0 | 3: routes/marketing_livehost_analytics.py, routes/marketing_livehost_portal.py, routes/marketing_livehost_shifts.py | 5: routes/marketing_budget.py, routes/marketing_live_sales_sync.py, routes/marketing_livehost_analytics.py … | OK |
| `marketing_livehost_training` | 0 | 1: routes/marketing_livehost_training.py | 2: routes/marketing_livehost_portal.py, routes/marketing_livehost_training.py | OK |
| `marketing_livehost_training_progress` | 0 | 2: routes/marketing_livehost_portal.py, routes/marketing_livehost_training.py | 2: routes/marketing_livehost_portal.py, routes/marketing_livehost_training.py | OK |
| `marketing_livehosts` | 0 | 4: core/marketing_master_seed.py, routes/marketing_livehost_hosts.py, routes/marketing_livehost_portal.py … | 8: core/marketing_account_scope.py, core/marketing_master_seed.py, routes/marketing_live_sessions_routes.py … | OK |
| `marketing_orders` | 0 | 4: core/order_status.py, routes/fulfillment.py, routes/marketing_orders_routes.py … | 14: core/order_status.py, routes/dewi_executive_report.py, routes/dewi_online_orders.py … | OK |
| `marketing_platform_accounts` | 3 | 6: core/marketing_account_scope.py, routes/marketing_accounts.py, routes/marketing_catalog_stock.py … | 27: core/marketing_account_scope.py, routes/marketing_account_health_routes.py, routes/marketing_accounts.py … | OK |
| `marketing_product_launches` | 0 | 1: routes/marketing_product_launches_routes.py | 3: routes/marketing_ai_insights_routes.py, routes/marketing_alerts.py, routes/marketing_product_launches_routes.py | OK |
| `marketing_returns` | — | 4: routes/dewi_wh_returns.py, routes/marketing_reports.py, routes/marketing_returns_routes.py … | 2: routes/marketing_reports.py, routes/marketing_returns_routes.py | belum ada di DB |
| `marketing_reviews` | 0 | 3: routes/marketing_reports.py, routes/marketing_reviews_routes.py, routes/marketing_tasks.py | 4: routes/marketing_advanced_ai_routes.py, routes/marketing_ai_insights_routes.py, routes/marketing_reports.py … | OK |
| `marketing_sales_data` | 0 | 4: routes/marketing_import.py, routes/marketing_live_sales_sync.py, routes/marketing_sales.py … | 9: routes/marketing_budget.py, routes/marketing_dashboard.py, routes/marketing_live_sales_sync.py … | OK |
| `marketing_samples` | — | 1: routes/marketing_samples_routes.py | 1: routes/marketing_samples_routes.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_spend_entries` | — | 1: routes/marketing_budget.py | 1: routes/marketing_budget.py | PULAU (1 berkas) · belum ada di DB |
| `marketing_stock_syncs` | 0 | 2: routes/marketing_catalog_stock.py, routes/marketing_toko_sync_routes.py | 3: routes/marketing_catalog_mgmt.py, routes/marketing_catalog_stock.py, routes/marketing_toko_sync_routes.py | OK |
| `marketing_task_templates` | — | 1: routes/marketing_task_templates.py | 2: routes/marketing_task_templates.py, utils/scheduler.py | belum ada di DB |
| `marketing_tasks` | 0 | 2: routes/marketing_tasks.py, utils/scheduler.py | 5: routes/marketing_reports.py, routes/marketing_targets.py, routes/marketing_task_templates.py … | OK |
| `marketing_webhook_events` | 0 | 1: routes/marketing_webhooks.py | 1: routes/marketing_webhooks.py | PULAU (1 berkas) |

## Koleksi LUAR domain yang WAJIB dipakai marketing (jangan buat duplikatnya)

| Koleksi | Peran untuk marketing | Modul pemilik |
|---|---|---|
| `rahaza_models` | Master Produk (induk): nama, kategori, HPP, retail_price, image_paths (foto RnD), aktif/dihentikan | routes/rahaza_master.py + core/product_master.py |
| `rahaza_materials` | FG (varian jadi) `type=fg`: kode/SKU, warna, size, unit — target tautan `fg_material_id` | routes/rahaza_inventory_* |
| `rahaza_material_stock` | Baris stok per lokasi — SATU-SATUNYA sumber stok jual (lewat core/catalog_stock) | routes/rahaza_inventory_stock.py |
| `rahaza_locations` | Lokasi gudang + tanda blocked/karantina (K-6a) | routes/rahaza_master.py |
| `rahaza_coa_accounts` | COA: akun pendapatan per toko (4-111…4-131), 1-220 Piutang Platform, 4-141 Potongan Platform, 6-400 Biaya Admin Platform | routes/rahaza_finance.py |
| `rahaza_posting_profiles` | Peta jurnal per event — tempat profil `marketplace_settlement` (F9) | routes/rahaza_posting_profiles.py |
| `rahaza_journal_entries` | Jurnal (draft→posted→voided) — HANYA dari settlement (F9) | routes/rahaza_journals.py |
| `rahaza_periods` | Kunci periode KEUANGAN (jangan dicampur dengan marketing_period_locks) | routes/rahaza_finance.py |
| `users / roles` | Identitas + role (pic_id, assigned_staff mengacu users.id) | backend/auth.py |
| `cmt_receipts / cmt_receipt_lines` | Penerimaan FG dari CMT — jalur "qty bertambah dari produksi" | routes/dewi_cmt_packing.py |
