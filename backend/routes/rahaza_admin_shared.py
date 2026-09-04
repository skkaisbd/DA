"""rahaza_admin — shared constants, router, seed data arrays, utility helpers."""
# ruff: noqa: E741
from fastapi import APIRouter
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/admin", tags=["rahaza-admin"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# Collections that store TRANSACTIONAL + MASTER data (to be purged on demo reset).
# Users / roles / permissions / company_settings NEVER purged.
PURGE_COLLECTIONS = [
    # Warehouse (legacy + active)
    "warehouse_locations", "warehouse_receiving", "warehouse_stock",
    "warehouse_movements", "warehouse_opname", "accessories",
    # Rahaza master
    "rahaza_locations", "rahaza_processes", "rahaza_shifts",
    "rahaza_machines", "rahaza_lines", "rahaza_employees",
    "rahaza_models", "rahaza_sizes", "rahaza_customers",
    # Rahaza production
    "rahaza_line_assignments", "rahaza_wip_events",
    "rahaza_orders", "rahaza_boms", "rahaza_work_orders",
    "rahaza_bundles", "rahaza_model_process_sop",
    # Rahaza inventory
    "rahaza_materials", "rahaza_material_stock",
    "rahaza_material_movements", "rahaza_material_issues",
    # Rahaza HR
    "rahaza_attendance_events", "rahaza_payroll_profiles",
    "rahaza_payroll_runs", "rahaza_payslips",
    # Rahaza finance operasional
    "rahaza_cost_centers",
    "rahaza_ar_invoices", "rahaza_ap_invoices",
    "rahaza_cash_accounts", "rahaza_cash_movements",
    "rahaza_expenses",
    # Rahaza costing / HPP
    "rahaza_costing_settings", "rahaza_hpp_snapshots",
    # Rahaza andon
    "rahaza_andon_events", "rahaza_andon_rules",
    # Rahaza alerts
    "rahaza_alerts", "rahaza_alert_rules",
    # Rahaza notifications
    "rahaza_notifications",
    # Rahaza shipments
    "rahaza_shipments",
    # Rahaza setup / next-action
    "rahaza_setup_state", "rahaza_next_action_dismissals",
    # Rahaza APS
    "rahaza_aps_schedules", "rahaza_aps_runs",
    # Rahaza OEE / rework
    "rahaza_oee_snapshots", "rahaza_rework_cases",
    # Rahaza QC v2
    "rahaza_qc_events", "rahaza_defect_codes",
    # Rahaza Accounting Core (F1-F3)
    "rahaza_coa_accounts",
    "rahaza_journal_entries", "rahaza_journal_lines",
    "rahaza_periods", "rahaza_posting_profiles",
    # Legacy production / operations
    "purchase_orders", "work_orders", "production_logs",
    "invoices", "payments", "manual_invoices",
    "qc_inspections", "finishing_records",
    # Audit (optional purge)
    "rahaza_audit_log",
]

# ──────────────────────────────────────────────────────────────────────────────
# Seed data constants
# ──────────────────────────────────────────────────────────────────────────────

CUSTOMER_SEED = [
    {"code": "CUST-001", "name": "PT Matahari Retail",          "payment_terms": "net_30", "address": "Jakarta Selatan"},
    {"code": "CUST-002", "name": "CV Sumber Rejeki Sandang",    "payment_terms": "net_14", "address": "Bandung"},
    {"code": "CUST-003", "name": "Toko Berkah Fashion",          "payment_terms": "net_7",  "address": "Surabaya"},
    {"code": "CUST-004", "name": "PT Alam Busana Sejahtera",    "payment_terms": "net_30", "address": "Semarang"},
    {"code": "CUST-005", "name": "Butik Eva Store",             "payment_terms": "cash",   "address": "Denpasar"},
    {"code": "CUST-006", "name": "PT Orient Knit Export",       "payment_terms": "net_30", "address": "Jakarta Pusat"},
]

MODEL_SEED = [
    {"code": "SWT-BASIC",   "name": "Sweater Basic Knit",       "base_hpp":  85000, "retail_price": 185000},
    {"code": "CRD-CLASSIC", "name": "Cardigan Classic Wool",    "base_hpp": 110000, "retail_price": 245000},
    {"code": "POL-SPORT",   "name": "Polo Sport Knit",          "base_hpp":  65000, "retail_price": 145000},
    {"code": "TRT-WARM",    "name": "Turtle Neck Warm",         "base_hpp":  95000, "retail_price": 215000},
    {"code": "KID-CUTE",    "name": "Kids Sweater Cute Series", "base_hpp":  55000, "retail_price": 125000},
]

SIZE_SEED = [
    {"code": "S",  "name": "Small"},
    {"code": "M",  "name": "Medium"},
    {"code": "L",  "name": "Large"},
    {"code": "XL", "name": "Extra Large"},
]

MATERIAL_SEED = [
    {"code": "YRN-ACR-001", "name": "Benang Akrilik Premium 2/28",  "type": "yarn",      "unit": "kg",  "unit_cost":  95000, "min_stock":   50, "max_stock":  300, "min_stock_qty":   80, "reorder_point": 100},
    {"code": "YRN-ACR-002", "name": "Benang Akrilik Standard 2/32", "type": "yarn",      "unit": "kg",  "unit_cost":  75000, "min_stock":   50, "max_stock":  300, "min_stock_qty":   80, "reorder_point": 100},
    {"code": "YRN-WOL-001", "name": "Benang Wool Blend 80/20",      "type": "yarn",      "unit": "kg",  "unit_cost": 145000, "min_stock":   30, "max_stock":  200, "min_stock_qty":   50, "reorder_point":  70},
    {"code": "YRN-COT-001", "name": "Benang Cotton Combed 30s",     "type": "yarn",      "unit": "kg",  "unit_cost": 110000, "min_stock":   40, "max_stock":  250, "min_stock_qty":   60, "reorder_point":  80},
    {"code": "YRN-NYL-001", "name": "Benang Nylon Stretch",         "type": "yarn",      "unit": "kg",  "unit_cost":  85000, "min_stock":   30, "max_stock":  200, "min_stock_qty":   50, "reorder_point":  70},
    {"code": "ACC-BTN-001", "name": "Kancing Plastik Resin 18mm",   "type": "accessory", "unit": "pcs", "unit_cost":    350, "min_stock": 2000, "max_stock": 10000, "min_stock_qty": 3000, "reorder_point": 4000},
    {"code": "ACC-ZIP-001", "name": "Resleting YKK 60cm",           "type": "accessory", "unit": "pcs", "unit_cost":   4500, "min_stock":  500, "max_stock":  3000, "min_stock_qty":  800, "reorder_point": 1000},
    {"code": "ACC-LBL-001", "name": "Label Woven Brand Rahaza",     "type": "accessory", "unit": "pcs", "unit_cost":    600, "min_stock": 2000, "max_stock": 10000, "min_stock_qty": 3000, "reorder_point": 4000},
]

EMPLOYEE_SEED = [
    # Supervisors
    {"code": "EMP-S001", "name": "Budi Santoso",     "job_title": "Supervisor Produksi", "wage_scheme": "bulanan",      "base_rate": 6500000},
    {"code": "EMP-S002", "name": "Sri Wahyuni",      "job_title": "Supervisor Gudang",   "wage_scheme": "bulanan",      "base_rate": 6000000},
    # Operators - Rajut
    {"code": "EMP-R001", "name": "Ahmad Fauzi",      "job_title": "Operator Rajut",      "wage_scheme": "borongan_pcs", "base_rate": 3500},
    {"code": "EMP-R002", "name": "Siti Aminah",      "job_title": "Operator Rajut",      "wage_scheme": "borongan_pcs", "base_rate": 3500},
    {"code": "EMP-R003", "name": "Dedi Kurniawan",   "job_title": "Operator Rajut",      "wage_scheme": "borongan_pcs", "base_rate": 3500},
    {"code": "EMP-R004", "name": "Yuni Lestari",     "job_title": "Operator Rajut",      "wage_scheme": "borongan_pcs", "base_rate": 3500},
    # Operators - Linking
    {"code": "EMP-L001", "name": "Indah Permata",    "job_title": "Operator Linking",    "wage_scheme": "borongan_pcs", "base_rate": 4000},
    {"code": "EMP-L002", "name": "Rini Susanti",     "job_title": "Operator Linking",    "wage_scheme": "borongan_pcs", "base_rate": 4000},
    # Operators - Sewing
    {"code": "EMP-J001", "name": "Mariana Dewi",     "job_title": "Operator Sewing",     "wage_scheme": "borongan_pcs", "base_rate": 4500},
    {"code": "EMP-J002", "name": "Lia Kartika",      "job_title": "Operator Sewing",     "wage_scheme": "borongan_pcs", "base_rate": 4500},
    # QC
    {"code": "EMP-Q001", "name": "Bambang Hariyanto", "job_title": "QC Inspector",       "wage_scheme": "bulanan",      "base_rate": 5000000},
    {"code": "EMP-Q002", "name": "Wati Suryani",     "job_title": "QC Inspector",        "wage_scheme": "bulanan",      "base_rate": 5000000},
    # Steam / Packing
    {"code": "EMP-P001", "name": "Joko Susilo",      "job_title": "Operator Steam",      "wage_scheme": "borongan_jam", "base_rate": 25000},
    {"code": "EMP-P002", "name": "Nita Rosmala",     "job_title": "Operator Packing",    "wage_scheme": "mingguan",     "base_rate": 900000},
    # Warehouse / Admin
    {"code": "EMP-W001", "name": "Agung Prasetyo",   "job_title": "Staff Gudang",        "wage_scheme": "bulanan",      "base_rate": 4500000},
    {"code": "EMP-W002", "name": "Fitri Handayani",  "job_title": "Admin Produksi",      "wage_scheme": "bulanan",      "base_rate": 4800000},
    {"code": "EMP-A001", "name": "Dewi Anjani",      "job_title": "Admin Keuangan",      "wage_scheme": "bulanan",      "base_rate": 5500000},
    {"code": "EMP-A002", "name": "Hendro Wibowo",    "job_title": "Akuntan",             "wage_scheme": "bulanan",      "base_rate": 7000000},
]

COST_CENTER_SEED = [
    {"code": "CC-PROD", "name": "Produksi",     "description": "Biaya lini produksi"},
    {"code": "CC-MKT",  "name": "Marketing",    "description": "Biaya pemasaran & sales"},
    {"code": "CC-ADM",  "name": "Administrasi", "description": "Biaya admin & office"},
    {"code": "CC-FIN",  "name": "Keuangan",     "description": "Biaya departemen keuangan"},
]

CASH_ACCOUNT_SEED = [
    {"code": "CASH-BSR", "name": "Kas Besar",    "account_type": "cash", "coa_code": "1-1102", "opening_balance":  25_000_000},
    {"code": "BANK-BCA", "name": "Bank BCA",     "account_type": "bank", "coa_code": "1-1201", "opening_balance": 250_000_000},
    {"code": "BANK-MDR", "name": "Bank Mandiri", "account_type": "bank", "coa_code": "1-1202", "opening_balance": 150_000_000},
]

MACHINE_SEED = [
    {"code": "MSN-001", "name": "Shima Seiki SES122-RT", "machine_type": "Rajut",   "gauge": "7gg",  "location_code": "ZNA-RAJUT"},
    {"code": "MSN-002", "name": "Shima Seiki SES122-RT", "machine_type": "Rajut",   "gauge": "7gg",  "location_code": "ZNA-RAJUT"},
    {"code": "MSN-003", "name": "Stoll CMS ADF 830",     "machine_type": "Rajut",   "gauge": "12gg", "location_code": "ZNA-RAJUT"},
    {"code": "MSN-004", "name": "Stoll CMS ADF 830",     "machine_type": "Rajut",   "gauge": "12gg", "location_code": "ZNA-RAJUT"},
    {"code": "MSN-005", "name": "Linking Manual Santoni", "machine_type": "Linking", "gauge": "",     "location_code": "ZNA-LINKING"},
    {"code": "MSN-006", "name": "Linking Manual Santoni", "machine_type": "Linking", "gauge": "",     "location_code": "ZNA-LINKING"},
]

LINE_SEED = [
    {"code": "LINE-A", "name": "Line A — Rajut Premium",   "process_code": "RAJUT",   "location_code": "ZNA-RAJUT",   "capacity_per_hour": 20},
    {"code": "LINE-B", "name": "Line B — Rajut Reguler",   "process_code": "RAJUT",   "location_code": "ZNA-RAJUT",   "capacity_per_hour": 25},
    {"code": "LINE-C", "name": "Line C — Linking",         "process_code": "LINKING", "location_code": "ZNA-LINKING", "capacity_per_hour": 30},
]
