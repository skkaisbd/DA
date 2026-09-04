"""
PT Rahaza — Phase F2 Accounting Core
Posting Profiles — mapping event_type → CoA account codes.

Collection: rahaza_posting_profiles
  id, event_type (unique), active (bool),
  mapping { <role>: <account_code> },  e.g. {'debit_ar': '1-1301', 'credit_revenue': '4-1100'}
  description, updated_at, updated_by

Seed defaults (garment manufacturing, PSAK):
  ar_invoice        : Dr AR (1-1301), Cr Revenue (4-1100), Cr Tax Output (2-1400)
  ar_payment        : Dr Bank (1-1201), Cr AR (akun jurnal penerbitan invoice)
  ap_invoice        : Dr Expense (6-2900) / Inventory RM (1-1401) / GRNI (2-1150), Cr AP (2-1100), Dr Tax Input (1-1501)
  ap_payment        : Dr AP (akun jurnal penerbitan invoice), Cr Bank (1-1201)
  expense           : Dr Expense (6-2900), Cr Bank (1-1201)
  payroll_finalize  : Dr Salary Expense (6-2100), Cr Hutang Gaji (2-1200)
  inventory_receive : Dr Inventory RM (1-1401), Cr GRNI (2-1150)
  inventory_issue   : Dr WIP (1-1403), Cr Inventory RM (1-1401)
  inventory_adjust  : Dr/Cr Inventory (1-1401) vs Expense (6-2400)
  cogs_shipment     : Dr COGS Material (5-1000), Dr COGS Labor (5-2000), Dr COGS Overhead (5-3000), Cr FG Inventory (1-1404)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/rahaza/posting-profiles", tags=["rahaza-posting-profiles"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


async def _require_fin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission finance.")


# ───────────────────────── SEED TEMPLATE ──────────────────────────────────────
# Each event_type maps role -> CoA code.
# `role` is a free-form key used by posting helpers when building JE lines.
DEFAULT_PROFILES = [
    # Skema akun KANONIK 4-digit (audit finance 2026-09-04). Tidak ada fallback kode
    # akun di posting engine — mapping yang hilang = posting ditolak dgn pesan jelas.
    {
        "event_type": "ar_invoice",
        "description": "AR Invoice sent → Dr AR / Cr Revenue (+Tax Output) (+Sales Discount)",
        "mapping": {
            "debit_ar": "1-1301",
            "credit_revenue": "4-1100",
            "credit_tax_output": "2-1400",
            "debit_sales_discount": "4-1300",
        },
    },
    {
        "event_type": "ar_payment",
        "description": "Pembayaran AR → Dr Bank / Cr AR (akun AR = akun jurnal penerbitan invoice)",
        "mapping": {
            "debit_cash_default": "1-1201",
            "credit_ar": "1-1301",
        },
    },
    {
        "event_type": "ap_invoice",
        "description": "AP Invoice → Dr Beban/Persediaan/GRNI / Cr AP (+Tax Input)",
        "mapping": {
            "debit_expense_default": "6-2900",
            "debit_inventory_rm": "1-1401",
            "debit_grni": "2-1150",
            "debit_tax_input": "1-1501",
            "credit_ap": "2-1100",
        },
    },
    {
        "event_type": "ap_payment",
        "description": "Pembayaran AP → Dr AP / Cr Bank (akun AP = akun jurnal penerbitan invoice)",
        "mapping": {
            "debit_ap": "2-1100",
            "credit_cash_default": "1-1201",
            "credit_purchase_discount": "4-2300",
        },
    },
    {
        "event_type": "expense",
        "description": "Expense operasional → Dr Expense / Cr Bank",
        "mapping": {
            "debit_expense_default": "6-2900",
            "credit_cash_default": "1-1201",
        },
    },
    {
        "event_type": "payroll_finalize",
        "description": "Payroll finalize → Dr Gaji Expense / Cr Hutang Gaji",
        "mapping": {
            "debit_salary_expense": "6-2100",
            "credit_salary_payable": "2-1200",
            "credit_tax_pph21": "2-1301",
            "credit_bpjs_payable": "2-1500",
        },
    },
    {
        "event_type": "payroll_payment",
        "description": "Pembayaran gaji → Dr Hutang Gaji / Cr Bank",
        "mapping": {
            "debit_salary_payable":  "2-1200",
            "credit_bank_default":   "1-1201",
        },
    },
    {
        "event_type": "inventory_receive",
        "description": "Penerimaan bahan (GR) → Dr Persediaan / Cr Hutang Belum Ditagih (GRNI)",
        "mapping": {
            "debit_inventory_rm": "1-1401",
            "credit_ap_clearing": "2-1150",
        },
    },
    {
        "event_type": "inventory_issue",
        "description": "Material issue ke WO → Dr WIP / Cr Inventory RM",
        "mapping": {
            "debit_wip": "1-1403",
            "credit_inventory_rm": "1-1401",
        },
    },
    {
        "event_type": "inventory_adjust",
        "description": "Material adjust → Dr/Cr Inventory vs Adjustment Expense",
        "mapping": {
            "inventory_rm": "1-1401",
            "adjustment_expense": "6-2400",
        },
    },
    {
        "event_type": "cogs_shipment",
        "description": "Shipment dispatched → Dr COGS / Cr FG Inventory (berdasarkan HPP snapshot)",
        "mapping": {
            "debit_cogs_material": "5-1000",
            "debit_cogs_labor": "5-2000",
            "debit_cogs_overhead": "5-3500",
            "credit_fg_inventory": "1-1404",
        },
    },
    {
        "event_type": "maklon_ar_invoice",
        "description": "Maklon AR Invoice → Dr AR Piutang / Cr Pendapatan Jasa Maklon",
        "mapping": {
            "debit_ar": "1-1301",
            "credit_revenue_maklon": "4-1100",
            "credit_tax_output": "2-1400",
        },
    },
    {
        "event_type": "cmt_ap_invoice",
        "description": "CMT Vendor AP Invoice → Dr Biaya Vendor CMT / Cr AP Vendor",
        "mapping": {
            # C-03 absorption: upah jahit PO INTERNAL dikapitalisasi ke WIP (bukan langsung COGS);
            # COGS lahir saat dispatch dari lapisan FG (bahan+jahit+overhead) — tidak dobel.
            "debit_cmt_wip_internal": "1-1403",
            "debit_cmt_expense_internal": "5-231",  # dipakai HANYA bila debit_cmt_wip_internal kosong
            "debit_cmt_expense_maklon": "7-120",    # Biaya Vendor CMT – Maklon (biaya proyek klien)
            "credit_ap": "2-1100",
            "debit_penalty_income": "4-9000",
        },
    },
    {
        "event_type": "maklon_advance_payment",
        "description": "DP Maklon dari klien → Dr Bank / Cr Uang Muka Diterima – Maklon",
        "mapping": {
            "debit_cash_default": "1-1201",
            "credit_advance_customer": "2-1700",
        },
    },
    {
        "event_type": "wip_to_fg_on_wo_complete",
        "description": "WO selesai: pindah nilai WIP ke Barang Jadi → Dr FG / Cr WIP",
        "mapping": {
            "debit_fg_inventory": "1-1404",
            "credit_wip":         "1-1403",
        },
    },
    {
        "event_type": "petty_cash_expense",
        "description": "Pengeluaran kas kecil → Dr Biaya / Cr Kas Kecil",
        "mapping": {
            "debit_expense_default": "6-2400",
            "credit_petty_cash":     "1-1101",
        },
    },
    {
        "event_type": "petty_cash_replenish",
        "description": "Pengisian ulang kas kecil dari bank → Dr Kas Kecil / Cr Bank",
        "mapping": {
            "debit_petty_cash":   "1-1101",
            "credit_bank_default": "1-1201",
        },
    },
    {
        "event_type": "bank_transfer",
        "description": "Transfer antar rekening bank → Dr Bank Tujuan / Cr Bank Sumber",
        "mapping": {
            "debit_bank_target":  "1-1202",
            "credit_bank_source": "1-1201",
        },
    },
    {
        "event_type": "credit_note",
        "description": "Credit note untuk retur → Dr Retur Penjualan / Cr AR (akun AR pelanggan/channel)",
        "mapping": {
            "debit_revenue":  "4-1200",
            "credit_ar":      "1-1301",
        },
    },
    {
        "event_type": "variance_overproduction",
        "description": "Overproduction variance → Dr FG Inventory / Cr Variance Income",
        "mapping": {
            "debit_inventory_fg":     "1-1404",
            "credit_variance_income": "4-9000",
        },
    },
    {
        "event_type": "variance_underproduction",
        "description": "Underproduction variance → Dr Variance Loss / Cr WIP",
        "mapping": {
            "debit_variance_loss": "6-4100",
            "credit_wip":          "1-1403",
        },
    },
    {
        "event_type": "asset_acquisition",
        "description": "Asset acquisition from GRN → Dr Fixed Asset / Cr GRNI",
        "mapping": {
            "debit_fixed_asset":  "1-2500",
            "credit_ap_clearing": "2-1150",
        },
    },
    {
        "event_type": "depreciation",
        "description": "Monthly depreciation → Dr Depreciation Expense / Cr Accumulated Depreciation",
        "mapping": {
            "debit_depr_expense":  "6-2700",
            "credit_accum_depr":   "1-2501",
        },
    },
    {
        "event_type": "accrual",
        "description": "Period-end accrual → Dr Expense / Cr Accrued Expenses",
        "mapping": {
            "debit_expense":   "6-2900",
            "credit_accrued":  "2-1600",
        },
    },
    {
        "event_type": "accrual_reversal",
        "description": "Accrual reversal (next period) → Dr Accrued Expenses / Cr Expense",
        "mapping": {
            "debit_accrued":   "2-1600",
            "credit_expense":  "6-2900",
        },
    },
    {
        "event_type": "bad_debt_writeoff",
        "description": "Bad debt write-off → Dr Bad Debt Expense / Cr AR (akun AR invoice asal)",
        "mapping": {
            "debit_bad_debt_expense": "6-4400",
            "credit_ar":              "1-1301",
        },
    },
    {
        "event_type": "bank_recon_charge",
        "description": "Bank charges adjustment → Dr Bank Charges / Cr Bank",
        "mapping": {
            "debit_bank_charges": "6-4100",
            "credit_bank":        "1-1201",
        },
    },
    {
        "event_type": "bank_recon_interest",
        "description": "Bank interest income → Dr Bank / Cr Interest Income",
        "mapping": {
            "debit_bank":             "1-1201",
            "credit_interest_income": "4-2100",
        },
    },
    {
        "event_type": "bank_recon_service_fee",
        "description": "Bank service fee → Dr Service Fee / Cr Bank",
        "mapping": {
            "debit_service_fee": "6-4101",
            "credit_bank":       "1-1201",
        },
    },
    {
        "event_type": "asset_disposal",
        "description": "Asset disposal (3-way: Dr Accum Depr + Dr Cash + Dr/Cr Gain/Loss, Cr Asset)",
        "mapping": {
            "credit_fixed_asset":       "1-2500",
            "debit_accum_depr":         "1-2501",
            "debit_cash":               "1-1201",
            "debit_loss_on_disposal":   "6-4200",
            "credit_gain_on_disposal":  "4-2200",
        },
    },
    {
        "event_type": "employee_loan_disbursement",
        "description": "Employee loan disbursement → Dr Employee Loan Receivable / Cr Bank",
        "mapping": {
            "debit_employee_loan_receivable": "1-1320",
            "credit_cash":                    "1-1201",
        },
    },
    {
        "event_type": "employee_loan_repayment_payroll",
        "description": "Employee loan repayment via payroll → Dr Salary Payable / Cr Employee Loan Receivable",
        "mapping": {
            "debit_salary_payable":             "2-1200",
            "credit_employee_loan_receivable":  "1-1320",
        },
    },
    {
        "event_type": "employee_loan_repayment_manual",
        "description": "Pelunasan kasbon manual → Dr Bank / Cr Employee Loan Receivable",
        "mapping": {
            "debit_bank":                       "1-1201",
            "credit_employee_loan_receivable":  "1-1320",
        },
    },
    {
        "event_type": "inventory_scrap",
        "description": "Material scrap/waste → Dr Scrap Expense / Cr Inventory RM",
        "mapping": {
            "debit_scrap_expense":   "6-4300",
            "credit_inventory_rm":   "1-1401",
        },
    },
]

# Perbaikan WAJIB pada profil yang sudah tersimpan di DB (idempoten):
# (event_type, role) → kode kanonik. Dipakai upgrade_posting_profiles().
PROFILE_CODE_FIXES = {
    ("asset_disposal", "credit_fixed_asset"): "1-2500",      # C-05: dulu 1-1501 PPN Masukan
    ("asset_disposal", "debit_accum_depr"): "1-2501",        # C-05: dulu 1-1502 PPh dibayar dimuka
    ("inventory_receive", "credit_ap_clearing"): "2-1150",   # C-02: GRNI
    ("asset_acquisition", "credit_ap_clearing"): "2-1150",
    ("ar_invoice", "debit_sales_discount"): "4-1300",        # H-10: dulu 6-1100 Iklan
    ("credit_note", "debit_revenue"): "4-1200",              # H-10: Retur Penjualan
    ("ap_invoice", "debit_expense_default"): "6-2900",       # C-02: dulu 6-2200 Listrik & Air
    ("expense", "debit_expense_default"): "6-2900",
    ("bad_debt_writeoff", "debit_bad_debt_expense"): "6-4400",
    ("cmt_ap_invoice", "debit_penalty_income"): "4-9000",
    ("variance_overproduction", "credit_variance_income"): "4-9000",
    ("bank_recon_interest", "credit_interest_income"): "4-2100",
    ("cogs_shipment", "debit_cogs_overhead"): "5-3500",
    ("cmt_ap_invoice", "debit_cmt_wip_internal"): "1-1403",   # C-03 absorption
}
# Kunci role legacy (dewi_kasbon) → kunci kanonik
PROFILE_ROLE_RENAMES = {
    "employee_loan_disbursement": {"debit_loan_receivable": "debit_employee_loan_receivable"},
    "employee_loan_repayment_payroll": {"credit_loan_receivable": "credit_employee_loan_receivable"},
    "employee_loan_repayment_manual": {"credit_loan_receivable": "credit_employee_loan_receivable"},
}


async def upgrade_posting_profiles(db) -> dict:
    """Idempoten: remap kode legacy 3-digit → 4-digit, terapkan PROFILE_CODE_FIXES,
    tambahkan role yang hilang dari DEFAULT_PROFILES, insert profil yang belum ada."""
    from routes.rahaza_coa import LEGACY_CODE_MAP
    defaults = {p["event_type"]: p for p in DEFAULT_PROFILES}
    changed = []
    inserted = (await seed_posting_profiles(db))["inserted"]
    async for doc in db.rahaza_posting_profiles.find({}, {"_id": 0}):
        et = doc["event_type"]
        mapping = dict(doc.get("mapping") or {})
        new_map = {}
        renames = PROFILE_ROLE_RENAMES.get(et, {})
        for role, code in mapping.items():
            role = renames.get(role, role)
            code = LEGACY_CODE_MAP.get(code, code)
            new_map[role] = code
        for (fet, role), code in PROFILE_CODE_FIXES.items():
            if fet == et:
                new_map[role] = code
        for role, code in (defaults.get(et, {}).get("mapping") or {}).items():
            new_map.setdefault(role, code)
        if new_map != mapping:
            await db.rahaza_posting_profiles.update_one(
                {"event_type": et},
                {"$set": {"mapping": new_map, "updated_at": _now(), "updated_by": "coa-canonical-migration"}})
            changed.append(et)
    return {"inserted": inserted, "updated": changed}


# ───────────────────────── ENDPOINTS ──────────────────────────────────────────
@router.get("")
async def list_profiles(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_posting_profiles.find({}, {"_id": 0}).sort("event_type", 1).to_list(500)
    return serialize_doc(rows)


@router.get("/{event_type}")
async def get_profile(event_type: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_posting_profiles.find_one({"event_type": event_type}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"Posting profile '{event_type}' tidak ditemukan.")
    return serialize_doc(doc)


@router.put("/{event_type}")
async def update_profile(event_type: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    doc = await db.rahaza_posting_profiles.find_one({"event_type": event_type})
    if not doc:
        raise HTTPException(404, f"Posting profile '{event_type}' tidak ditemukan. Jalankan seed dulu.")
    upd = {"updated_at": _now(), "updated_by": user["id"], "updated_by_name": user.get("name", "")}
    if "mapping" in body and isinstance(body["mapping"], dict):
        # validate each account_code exists + leaf + active (warning but not blocker if missing)
        mapping = body["mapping"]
        clean = {}
        # Batch fetch all referenced CoA accounts in one query
        codes = [str(c).strip() for c in mapping.values() if c]
        coa_map = {}
        if codes:
            async for d in db.rahaza_coa_accounts.find({"code": {"$in": codes}}, {"_id": 0}):
                coa_map[d["code"]] = d
        for role, code in mapping.items():
            if not code:
                continue
            code = str(code).strip()
            acc = coa_map.get(code)
            if not acc:
                raise HTTPException(400, f"Role '{role}': akun '{code}' tidak ditemukan di CoA.")
            if acc.get("is_group"):
                raise HTTPException(400, f"Role '{role}': akun '{code}' adalah header (non-postable). Pilih akun leaf.")
            if not acc.get("active"):
                raise HTTPException(400, f"Role '{role}': akun '{code}' tidak aktif.")
            clean[role] = code
        upd["mapping"] = clean
    if "description" in body:
        upd["description"] = (body.get("description") or "").strip()
    if "active" in body:
        upd["active"] = bool(body["active"])
    await db.rahaza_posting_profiles.update_one({"event_type": event_type}, {"$set": upd})
    out = await db.rahaza_posting_profiles.find_one({"event_type": event_type}, {"_id": 0})
    await log_activity(user["id"], user.get("name", ""), "update_posting_profile", "posting_profile", event_type)
    return serialize_doc(out)


async def seed_posting_profiles(db, user=None):
    """Seed default posting profiles idempotent (skip if exists).
    Reusable by both the startup auto-seed (server.py) and the /seed route."""
    uid = (user or {}).get("id", "system")
    uname = (user or {}).get("name", "system")
    inserted = 0
    skipped = 0
    # Batch fetch existing posting profiles
    event_types = [p["event_type"] for p in DEFAULT_PROFILES]
    existing_profiles_set = set()
    if event_types:
        async for d in db.rahaza_posting_profiles.find(
            {"event_type": {"$in": event_types}}, {"_id": 0, "event_type": 1}
        ):
            existing_profiles_set.add(d["event_type"])
    for p in DEFAULT_PROFILES:
        if p["event_type"] in existing_profiles_set:
            skipped += 1
            continue
        doc = {
            "id": _uid(),
            "event_type": p["event_type"],
            "description": p["description"],
            "mapping": p["mapping"],
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": uid,
            "created_by_name": uname,
        }
        await db.rahaza_posting_profiles.insert_one(doc)
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total_template": len(DEFAULT_PROFILES)}


@router.post("/seed")
async def seed_defaults(request: Request):
    """Seed default posting profiles idempotent (skip if exists)."""
    user = await _require_fin(request)
    db = get_db()
    result = await seed_posting_profiles(db, user)
    await log_activity(user["id"], user.get("name", ""), "seed_posting_profiles", "posting_profile",
                       f"inserted={result['inserted']} skipped={result['skipped']}")
    return {"ok": True, **result}


async def ensure_seed(db):
    """Internal helper: auto-seed if collection is empty. Called by posting helpers."""
    cnt = await db.rahaza_posting_profiles.count_documents({})
    if cnt > 0:
        return
    for p in DEFAULT_PROFILES:
        doc = {
            "id": _uid(),
            "event_type": p["event_type"],
            "description": p["description"],
            "mapping": p["mapping"],
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": "system",
            "created_by_name": "system",
        }
        await db.rahaza_posting_profiles.insert_one(doc)


async def get_mapping(db, event_type: str) -> dict:
    await ensure_seed(db)
    doc = await db.rahaza_posting_profiles.find_one({"event_type": event_type, "active": True}, {"_id": 0})
    if not doc:
        return {}
    return doc.get("mapping") or {}


@router.post("/seed-da")
async def seed_da_profiles(request: Request):
    """DIHENTIKAN: skema 4-digit kanonik (audit 2026-09-04). Pakai /api/rahaza/coa/migrate-canonical."""
    await _require_fin(request)
    raise HTTPException(410, "Profil DA 3-digit sudah tidak dipakai — skema akun kanonik 4-digit. "
                             "Jalankan POST /api/rahaza/coa/migrate-canonical.")
