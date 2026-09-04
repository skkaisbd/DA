"""
PT Rahaza — Phase F1 Accounting Core
Chart of Accounts (PSAK / SAK-ETAP compliant) — Garment Manufacturing Template

Collection: rahaza_coa_accounts
Fields:
  id (uuid), code (unique string), name, type (ASSET/LIABILITY/EQUITY/REVENUE/COGS/EXPENSE/OTHER),
  parent_code (nullable), normal_balance (DEBIT|CREDIT), is_group (bool, non-postable header),
  flags (dict for integration hooks: is_cash, is_ar, is_ap, is_inventory_rm, ...),
  active (bool), created_at, updated_at, created_by, created_by_name
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from routes.shared import require_portal_dep
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import uuid
from datetime import datetime, timezone
import re

router = APIRouter(prefix="/api/rahaza/coa", tags=["rahaza-coa"],
                   dependencies=[Depends(require_portal_dep("finance"))])  # RBAC: portal finance (BUG-RBAC-1)

ACCOUNT_TYPES = ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "COGS", "EXPENSE", "OTHER_INCOME", "OTHER_EXPENSE"]
NORMAL_DEBIT = {"ASSET", "COGS", "EXPENSE", "OTHER_EXPENSE"}
NORMAL_CREDIT = {"LIABILITY", "EQUITY", "REVENUE", "OTHER_INCOME"}


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


def _normal_balance_for(acc_type: str) -> str:
    return "DEBIT" if acc_type in NORMAL_DEBIT else "CREDIT"


# ─────────────── CoA Seed Template (Garment Manufacturing, PSAK) ─────────────
# Format: (code, name, type, is_group, flags)
# is_group=True means header/non-postable (you post to child leaf accounts)
SEED_TEMPLATE = [
    # ASSETS ───────────────────────────────────────────────────────────────
    ("1-0000", "ASET", "ASSET", True, {}),
    ("1-1000", "ASET LANCAR", "ASSET", True, {}),
    ("1-1100", "Kas", "ASSET", True, {"is_cash": True}),
    ("1-1101", "Kas Kecil", "ASSET", False, {"is_cash": True}),
    ("1-1102", "Kas Besar", "ASSET", False, {"is_cash": True}),
    ("1-1200", "Bank", "ASSET", True, {"is_bank": True}),
    ("1-1201", "Bank BCA", "ASSET", False, {"is_bank": True}),
    ("1-1202", "Bank Mandiri", "ASSET", False, {"is_bank": True}),
    ("1-1300", "Piutang Usaha", "ASSET", True, {"is_ar": True}),
    ("1-1301", "Piutang Usaha — Dagang", "ASSET", False, {"is_ar": True}),
    ("1-1302", "Cadangan Piutang Ragu-Ragu", "ASSET", False, {"is_contra": True}),
    ("1-1303", "Piutang Platform Online Shop", "ASSET", False, {"is_ar": True}),
    ("1-1304", "Piutang COD Belum Cair", "ASSET", False, {"is_ar": True}),
    ("1-1400", "Persediaan", "ASSET", True, {}),
    ("1-1401", "Persediaan Bahan Baku (Benang/Kain)", "ASSET", False, {"is_inventory_rm": True}),
    ("1-1402", "Persediaan Bahan Pembantu (Aksesoris)", "ASSET", False, {"is_inventory_rm": True}),
    ("1-1403", "Persediaan Barang Dalam Proses (WIP)", "ASSET", False, {"is_inventory_wip": True}),
    ("1-1404", "Persediaan Barang Jadi (FG)", "ASSET", False, {"is_inventory_fg": True}),
    ("1-1500", "Pajak Dibayar Dimuka", "ASSET", True, {}),
    ("1-1501", "PPN Masukan", "ASSET", False, {"is_tax_input": True}),
    ("1-1502", "PPh 22/23 Dibayar Dimuka", "ASSET", False, {"is_tax_prepaid": True}),
    ("1-1600", "Uang Muka & Biaya Dibayar Dimuka", "ASSET", True, {}),
    ("1-1610", "Uang Muka Karyawan (Cash Advance)", "ASSET", False, {"is_employee_advance": True}),
    ("1-1620", "Uang Muka Lain-Lain", "ASSET", False, {}),
    ("1-2000", "ASET TETAP", "ASSET", True, {}),
    ("1-2100", "Tanah", "ASSET", False, {"is_fixed_asset": True}),
    ("1-2200", "Bangunan", "ASSET", False, {"is_fixed_asset": True}),
    ("1-2201", "Akum. Penyusutan Bangunan", "ASSET", False, {"is_contra": True, "is_accum_dep": True}),
    ("1-2300", "Mesin & Peralatan Produksi", "ASSET", False, {"is_fixed_asset": True}),
    ("1-2301", "Akum. Penyusutan Mesin", "ASSET", False, {"is_contra": True, "is_accum_dep": True}),
    ("1-2400", "Kendaraan", "ASSET", False, {"is_fixed_asset": True}),
    ("1-2401", "Akum. Penyusutan Kendaraan", "ASSET", False, {"is_contra": True, "is_accum_dep": True}),
    ("1-2500", "Inventaris Kantor", "ASSET", False, {"is_fixed_asset": True}),
    ("1-2501", "Akum. Penyusutan Inventaris", "ASSET", False, {"is_contra": True, "is_accum_dep": True}),

    # LIABILITIES ──────────────────────────────────────────────────────────
    ("2-0000", "LIABILITAS", "LIABILITY", True, {}),
    ("2-1000", "LIABILITAS JANGKA PENDEK", "LIABILITY", True, {}),
    ("2-1100", "Hutang Usaha", "LIABILITY", False, {"is_ap": True}),
    ("2-1150", "Hutang Belum Ditagih (GRNI)", "LIABILITY", False, {"is_grni": True}),
    ("2-1200", "Hutang Gaji & Upah", "LIABILITY", False, {"is_payroll_payable": True}),
    ("2-1300", "Hutang Pajak", "LIABILITY", True, {}),
    ("2-1301", "Hutang PPh 21", "LIABILITY", False, {"is_tax_payable": True}),
    ("2-1302", "Hutang PPh 23", "LIABILITY", False, {"is_tax_payable": True}),
    ("2-1303", "Hutang PPh 25/29", "LIABILITY", False, {"is_tax_payable": True}),
    ("2-1400", "Hutang PPN Keluaran", "LIABILITY", False, {"is_tax_output": True}),
    ("2-1500", "Hutang BPJS", "LIABILITY", False, {"is_bpjs_payable": True}),
    ("2-1600", "Hutang Jangka Pendek Lainnya", "LIABILITY", False, {}),
    ("2-1700", "Uang Muka Diterima – Maklon (Termin)", "LIABILITY", False, {"is_customer_advance": True}),
    ("2-2000", "LIABILITAS JANGKA PANJANG", "LIABILITY", True, {}),
    ("2-2100", "Hutang Bank Jangka Panjang", "LIABILITY", False, {"is_long_term": True}),

    # EQUITY ───────────────────────────────────────────────────────────────
    ("3-0000", "EKUITAS", "EQUITY", True, {}),
    ("3-1000", "Modal Disetor", "EQUITY", False, {"is_capital": True}),
    ("3-2000", "Laba Ditahan", "EQUITY", False, {"is_retained_earnings": True}),
    ("3-3000", "Laba/Rugi Tahun Berjalan", "EQUITY", False, {"is_current_earnings": True}),
    ("3-4000", "Prive / Dividen", "EQUITY", False, {"is_contra": True}),

    # REVENUE ──────────────────────────────────────────────────────────────
    ("4-0000", "PENDAPATAN", "REVENUE", True, {}),
    ("4-1000", "Penjualan", "REVENUE", True, {}),
    ("4-1100", "Penjualan Garment", "REVENUE", False, {"is_sales": True}),
    ("4-1200", "Retur Penjualan", "REVENUE", False, {"is_contra": True}),
    ("4-1300", "Diskon Penjualan", "REVENUE", False, {"is_contra": True}),
    ("4-9000", "Pendapatan Lain-Lain", "OTHER_INCOME", False, {}),

    # COGS ─────────────────────────────────────────────────────────────────
    ("5-0000", "HARGA POKOK PENJUALAN", "COGS", True, {}),
    ("5-1000", "HPP Bahan Baku", "COGS", False, {"is_cogs_material": True}),
    ("5-2000", "HPP Tenaga Kerja Langsung", "COGS", False, {"is_cogs_labor": True}),
    ("5-3000", "HPP Overhead Pabrik", "COGS", True, {}),
    ("5-3100", "Listrik Pabrik", "COGS", False, {"is_cogs_overhead": True}),
    ("5-3200", "Penyusutan Mesin Produksi", "COGS", False, {"is_cogs_overhead": True}),
    ("5-3300", "Maintenance Mesin", "COGS", False, {"is_cogs_overhead": True}),
    ("5-3400", "Bahan Pembantu Produksi", "COGS", False, {"is_cogs_overhead": True}),
    ("5-3500", "Overhead Pabrik Umum (BOP)", "COGS", False, {"is_cogs_overhead": True}),

    # EXPENSE ──────────────────────────────────────────────────────────────
    ("6-0000", "BEBAN OPERASIONAL", "EXPENSE", True, {}),
    ("6-1000", "Beban Penjualan & Pemasaran", "EXPENSE", True, {}),
    ("6-1100", "Biaya Iklan & Promosi", "EXPENSE", False, {}),
    ("6-1200", "Biaya Pengiriman", "EXPENSE", False, {}),
    ("6-2000", "Beban Administrasi & Umum", "EXPENSE", True, {}),
    ("6-2100", "Gaji Staff Kantor", "EXPENSE", False, {"is_salary_expense": True}),
    ("6-2200", "Listrik & Air Kantor", "EXPENSE", False, {}),
    ("6-2300", "Telepon & Internet", "EXPENSE", False, {}),
    ("6-2400", "ATK & Supplies", "EXPENSE", False, {}),
    ("6-2500", "Sewa Kantor", "EXPENSE", False, {}),
    ("6-2600", "Asuransi", "EXPENSE", False, {}),
    ("6-2700", "Penyusutan Bangunan & Inventaris", "EXPENSE", False, {"is_depreciation": True}),
    ("6-2800", "Biaya Bank & Administrasi", "EXPENSE", False, {}),
    ("6-2900", "Beban Umum & Lain-lain", "EXPENSE", False, {"is_general_expense": True}),
    ("6-3000", "Beban Karyawan Non-Produksi", "EXPENSE", True, {}),
    ("6-3100", "Tunjangan & Bonus", "EXPENSE", False, {}),
    ("6-3200", "BPJS Kesehatan (Employer)", "EXPENSE", False, {}),
    ("6-3300", "BPJS Ketenagakerjaan (Employer)", "EXPENSE", False, {}),
    ("6-3400", "Biaya Perjalanan Dinas", "EXPENSE", False, {"is_travel_expense": True}),
    ("6-3500", "Biaya Reimbursement Karyawan", "EXPENSE", False, {"is_reimbursement": True}),

    # OTHER ────────────────────────────────────────────────────────────────
    ("7-0000", "PENDAPATAN & BEBAN LAIN-LAIN", "OTHER_INCOME", True, {}),
    ("7-1000", "Pendapatan Bunga", "OTHER_INCOME", False, {}),
    ("7-2000", "Beban Bunga Pinjaman", "OTHER_EXPENSE", False, {}),
    ("7-3000", "Laba/Rugi Selisih Kurs", "OTHER_INCOME", False, {}),
    ("7-4000", "Pendapatan/Beban Lain-Lain", "OTHER_INCOME", False, {}),
    
    # Phase 9B: Bank Reconciliation Accounts ──────────────────────────────
    ("4-2100", "Pendapatan Bunga Bank", "REVENUE", False, {"is_interest_income": True}),
    ("6-4100", "Biaya Bank & Admin Bank", "EXPENSE", False, {"is_bank_charge": True}),
    ("6-4101", "Biaya Layanan Bank", "EXPENSE", False, {"is_service_fee": True}),
    
    # Phase 9A: Bad Debt Expense ──────────────────────────────────────────────
    ("6-4400", "Beban Kerugian Piutang (Bad Debt Expense)", "EXPENSE", False, {"is_bad_debt_expense": True}),

    # Phase 10A: Asset Disposal Accounts ───────────────────────────────────────
    ("4-2200", "Keuntungan Penjualan Aset Tetap", "REVENUE", False, {"is_gain_on_disposal": True}),
    ("6-4200", "Kerugian Penjualan Aset Tetap", "EXPENSE", False, {"is_loss_on_disposal": True}),
    
    # Phase 10B: Purchase Discount Account ─────────────────────────────────────
    
    # Phase 11A & 11B: Employee Loan Accounts ──────────────────────────────────
    ("1-1320", "Piutang Pinjaman Karyawan", "ASSET", False, {"is_employee_loan_receivable": True}),
    
    # Phase 11C: Scrap/Waste Expense Account ───────────────────────────────────
    ("6-4300", "Biaya Scrap & Material Rusak", "EXPENSE", False, {"is_scrap_expense": True}),

    ("4-2300", "Potongan Pembelian (Purchase Discount)", "REVENUE", False, {"is_purchase_discount": True}),

]


# ─────────────────────── ENDPOINTS ────────────────────────────────────────
@router.get("/accounts")
async def list_accounts(request: Request, active_only: bool = True, search: str = "", type: str = ""):
    await require_auth(request)
    db = get_db()
    q = {}
    if active_only:
        q["active"] = True
    if type:
        q["type"] = type.upper()
    if search:
        q["$or"] = [
            {"code": {"$regex": re.escape(search), "$options": "i"}},
            {"name": {"$regex": re.escape(search), "$options": "i"}},
        ]
    rows = await db.rahaza_coa_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(5000)
    return serialize_doc(rows)


@router.get("/tree")
async def coa_tree(request: Request, active_only: bool = True):
    """Return accounts as tree structure based on parent_code."""
    await require_auth(request)
    db = get_db()
    q = {"active": True} if active_only else {}
    rows = await db.rahaza_coa_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(5000)
    by_code = {r["code"]: {**r, "children": []} for r in rows}
    roots = []
    for r in rows:
        parent = r.get("parent_code")
        if parent and parent in by_code:
            by_code[parent]["children"].append(by_code[r["code"]])
        else:
            roots.append(by_code[r["code"]])
    return serialize_doc(roots)


@router.post("/accounts")
async def create_account(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    acc_type = (body.get("type") or "").strip().upper()

    if not code or not name:
        raise HTTPException(400, "code & name wajib.")
    if acc_type not in ACCOUNT_TYPES:
        raise HTTPException(400, f"type harus salah satu dari {ACCOUNT_TYPES}")
    if await db.rahaza_coa_accounts.find_one({"code": code}):
        raise HTTPException(409, f"Kode akun '{code}' sudah ada.")

    parent_code = body.get("parent_code") or None
    if parent_code:
        parent = await db.rahaza_coa_accounts.find_one({"code": parent_code})
        if not parent:
            raise HTTPException(400, f"Parent '{parent_code}' tidak ditemukan.")

    doc = {
        "id": _uid(),
        "code": code,
        "name": name,
        "type": acc_type,
        "parent_code": parent_code,
        "is_group": bool(body.get("is_group", False)),
        "normal_balance": _normal_balance_for(acc_type),
        "flags": body.get("flags") or {},
        "active": True,
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    await db.rahaza_coa_accounts.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create_account", "coa", f"{code} {name}")
    return serialize_doc(doc)


@router.put("/accounts/{aid}")
async def update_account(aid: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    acc = await db.rahaza_coa_accounts.find_one({"id": aid})
    if not acc:
        raise HTTPException(404, "Akun tidak ditemukan.")
    update = {"updated_at": _now()}
    if "name" in body:
        update["name"] = (body["name"] or "").strip() or acc["name"]
    if "parent_code" in body:
        update["parent_code"] = body["parent_code"] or None
    if "is_group" in body:
        update["is_group"] = bool(body["is_group"])
    if "flags" in body:
        update["flags"] = body["flags"] or {}
    if "active" in body:
        update["active"] = bool(body["active"])
    # note: type & code tidak bisa diubah agar tidak merusak jurnal historis
    await db.rahaza_coa_accounts.update_one({"id": aid}, {"$set": update})
    acc = await db.rahaza_coa_accounts.find_one({"id": aid}, {"_id": 0})
    await log_activity(user["id"], user.get("name", ""), "update_account", "coa", aid)
    return serialize_doc(acc)


@router.delete("/accounts/{aid}")
async def deactivate_account(aid: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    acc = await db.rahaza_coa_accounts.find_one({"id": aid})
    if not acc:
        raise HTTPException(404, "Akun tidak ditemukan.")
    # cek apakah pernah dipakai di jurnal (soft disable)
    used = await db.rahaza_journal_lines.count_documents({"account_code": acc["code"]})
    if used > 0:
        await db.rahaza_coa_accounts.update_one({"id": aid}, {"$set": {"active": False, "updated_at": _now()}})
        await log_activity(user["id"], user.get("name", ""), "deactivate_account", "coa", acc["code"])
        return {"ok": True, "soft_disabled": True, "used_count": used}
    await db.rahaza_coa_accounts.delete_one({"id": aid})
    await log_activity(user["id"], user.get("name", ""), "delete_account", "coa", acc["code"])
    return {"ok": True, "deleted": True}


@router.post("/seed")
async def seed_template(request: Request):
    """Seed CoA template garment manufacturing (PSAK). Skip akun yang sudah ada."""
    user = await _require_fin(request)
    db = get_db()
    inserted = 0
    skipped = 0
    template_codes = [c for c, *_ in SEED_TEMPLATE if c not in DUP_TEMPLATE_CODES]
    existing_coa_codes = set()
    if template_codes:
        async for d in db.rahaza_coa_accounts.find(
            {"code": {"$in": template_codes}}, {"_id": 0, "code": 1}
        ):
            existing_coa_codes.add(d["code"])
    for code, name, acc_type, is_group, flags in SEED_TEMPLATE:
        if code in DUP_TEMPLATE_CODES:   # G4: nama duplikat → kanonik DA 3-digit
            skipped += 1
            continue
        if code in existing_coa_codes:
            skipped += 1
            continue
        parent_code = PARENT_OVERRIDES.get(code) or _infer_parent_code(code, template_codes)
        doc = {
            "id": _uid(),
            "code": code,
            "name": name,
            "type": acc_type,
            "parent_code": parent_code,
            "is_group": is_group,
            "normal_balance": _normal_balance_for(acc_type),
            "flags": flags,
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
        }
        await db.rahaza_coa_accounts.insert_one(doc)
        inserted += 1
    await log_activity(user["id"], user.get("name", ""), "seed_coa", "coa", f"inserted={inserted} skipped={skipped}")
    return {"ok": True, "inserted": inserted, "skipped": skipped, "total_template": len(SEED_TEMPLATE)}



# ─────────────── CoA Seed DA (CV. Dewi Aditya — 3-digit format) ──────────────
# Format: (code, name, type, is_group, flags, parent_code, nb_override)
# nb_override: None = auto from type, "DEBIT"/"CREDIT" = explicit (for contra accounts)
DA_COA_SEED = [
    # ROOT GROUPS
    ("1-000","AKTIVA","ASSET",True,{},None,None),
    ("2-000","KEWAJIBAN","LIABILITY",True,{},None,None),
    ("3-000","EKUITAS","EQUITY",True,{},None,None),
    ("4-000","PENDAPATAN","REVENUE",True,{},None,None),
    ("5-000","HARGA POKOK PENJUALAN (HPP)","COGS",True,{},None,None),
    ("6-000","BIAYA OPERASIONAL ONLINE SHOP","EXPENSE",True,{},None,None),
    ("7-000","BIAYA OPERASIONAL MAKLON","EXPENSE",True,{},None,None),
    ("8-000","BIAYA PRODUKSI (OVERHEAD)","EXPENSE",True,{},None,None),
    ("9-000","BIAYA UMUM & ADMINISTRASI","EXPENSE",True,{},None,None),
    # AKTIVA LANCAR
    ("1-100","AKTIVA LANCAR","ASSET",True,{},"1-000",None),
    ("1-110","Kas Kecil","ASSET",False,{"is_cash":True},"1-100",None),
    ("1-120","Kasbon Karyawan","ASSET",False,{"is_employee_loan_receivable":True},"1-100",None),
    ("1-130","Rekening Bank Operasional","ASSET",True,{"is_bank":True},"1-100",None),
    ("1-131","Bank BCA – DA Official (Online Shop)","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-132","Bank BCA – CV Dekka Karya Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-133","Bank BCA – CV Dzaki Karya Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-134","Bank BCA – CV Sukma Mitra Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-135","Bank BCA – Aditya Sulistyo DW (CMT)","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-136","Bank BCA – Dewi Ratnasari","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-137","Bank BCA – Lainnya","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-141","Bank BRI – CV DA Official","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-142","Bank BRI – CV Dekka Karya Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-143","Bank BRI – CV Dzaki Karya Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-144","Bank BRI – CV Sukma Mitra Utama","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-145","Bank BRI – Hadi Supardi KBB","ASSET",False,{"is_bank":True},"1-130",None),
    ("1-150","Dompet Digital","ASSET",True,{"is_bank":True},"1-100",None),
    ("1-151","GoPay","ASSET",False,{"is_bank":True},"1-150",None),
    ("1-152","DANA","ASSET",False,{"is_bank":True},"1-150",None),
    ("1-153","DANA – Lain-lain","ASSET",False,{"is_bank":True},"1-150",None),
    ("1-154","ShopeePay","ASSET",False,{"is_bank":True},"1-150",None),
    ("1-155","Flazz BCA","ASSET",False,{"is_bank":True},"1-150",None),
    # PIUTANG
    ("1-200","Piutang","ASSET",True,{"is_ar":True},"1-000",None),
    ("1-210","Piutang Usaha – Maklon","ASSET",False,{"is_ar":True},"1-200",None),
    ("1-211","Cadangan Kerugian Piutang","ASSET",False,{"is_contra":True},"1-200","CREDIT"),
    ("1-220","Piutang Platform Online Shop","ASSET",False,{"is_ar":True},"1-200",None),
    ("1-230","Piutang COD Belum Cair","ASSET",False,{"is_ar":True},"1-200",None),
    # PERSEDIAAN
    ("1-300","Persediaan","ASSET",True,{},"1-000",None),
    ("1-310","Persediaan Bahan Baku (Kain/Tekstil)","ASSET",False,{"is_inventory_rm":True},"1-300",None),
    ("1-320","Persediaan Bahan Pembantu (Aksesori)","ASSET",False,{"is_inventory_rm":True},"1-300",None),
    ("1-330","Persediaan Barang Dalam Proses (WIP)","ASSET",False,{"is_inventory_wip":True},"1-300",None),
    ("1-340","Persediaan Barang Jadi – Online Shop","ASSET",False,{"is_inventory_fg":True},"1-300",None),
    ("1-350","Persediaan Barang Jadi – Maklon","ASSET",False,{"is_inventory_fg":True},"1-300",None),
    # UANG MUKA
    ("1-400","Uang Muka & Bayar Dimuka","ASSET",True,{},"1-000",None),
    ("1-410","Uang Muka Pembelian Bahan","ASSET",False,{},"1-400",None),
    ("1-420","Uang Muka Vendor CMT","ASSET",False,{},"1-400",None),
    ("1-430","Sewa Dibayar Dimuka","ASSET",False,{},"1-400",None),
    ("1-440","PPN Masukan (Pajak Dibayar Dimuka)","ASSET",False,{"is_tax_input":True},"1-400",None),
    ("1-450","Biaya Dibayar Dimuka Lainnya","ASSET",False,{},"1-400",None),
    # AKTIVA TETAP
    ("1-500","AKTIVA TETAP","ASSET",True,{"is_fixed_asset":True},"1-000",None),
    ("1-510","Tanah","ASSET",False,{"is_fixed_asset":True},"1-500",None),
    ("1-520","Bangunan","ASSET",False,{"is_fixed_asset":True},"1-500",None),
    ("1-521","Akumulasi Penyusutan – Bangunan","ASSET",False,{"is_contra":True,"is_accum_dep":True},"1-500","CREDIT"),
    ("1-530","Kendaraan (Bus)","ASSET",False,{"is_fixed_asset":True},"1-500",None),
    ("1-531","Akumulasi Penyusutan – Kendaraan","ASSET",False,{"is_contra":True,"is_accum_dep":True},"1-500","CREDIT"),
    ("1-540","Peralatan Produksi (Mesin Jahit, dll)","ASSET",False,{"is_fixed_asset":True},"1-500",None),
    ("1-541","Akumulasi Penyusutan – Peralatan Produksi","ASSET",False,{"is_contra":True,"is_accum_dep":True},"1-500","CREDIT"),
    ("1-550","Peralatan Kantor & IT","ASSET",False,{"is_fixed_asset":True},"1-500",None),
    ("1-551","Akumulasi Penyusutan – Peralatan Kantor","ASSET",False,{"is_contra":True,"is_accum_dep":True},"1-500","CREDIT"),
    # AKTIVA LAIN
    ("1-600","AKTIVA LAIN-LAIN","ASSET",True,{},"1-000",None),
    ("1-610","Bangunan Dalam Proses","ASSET",False,{},"1-600",None),
    ("1-620","Deposit Sewa","ASSET",False,{},"1-600",None),
    # KEWAJIBAN LANCAR
    ("2-100","KEWAJIBAN LANCAR","LIABILITY",True,{},"2-000",None),
    ("2-110","Hutang Usaha – Supplier Bahan Baku","LIABILITY",False,{"is_ap":True},"2-100",None),
    ("2-111","Hutang Usaha – Supplier Aksesori","LIABILITY",False,{"is_ap":True},"2-100",None),
    ("2-112","Hutang Vendor CMT (Termin)","LIABILITY",False,{"is_ap":True},"2-100",None),
    ("2-113","Hutang Ekspedisi & Logistik","LIABILITY",False,{"is_ap":True},"2-100",None),
    ("2-120","Hutang Gaji Karyawan","LIABILITY",False,{"is_payroll_payable":True},"2-100",None),
    ("2-121","Hutang Bonus Karyawan","LIABILITY",False,{},"2-100",None),
    ("2-122","Hutang BPJS Kesehatan","LIABILITY",False,{"is_bpjs_payable":True},"2-100",None),
    ("2-123","Hutang BPJS Ketenagakerjaan","LIABILITY",False,{"is_bpjs_payable":True},"2-100",None),
    ("2-130","Hutang Pajak – PPN Keluaran","LIABILITY",False,{"is_tax_output":True},"2-100",None),
    ("2-131","Hutang Pajak – PPh 21 Karyawan","LIABILITY",False,{"is_tax_payable":True},"2-100",None),
    ("2-132","Hutang Pajak – PPh 23 Jasa Vendor","LIABILITY",False,{"is_tax_payable":True},"2-100",None),
    ("2-133","Hutang Pajak – PPh Badan","LIABILITY",False,{"is_tax_payable":True},"2-100",None),
    ("2-140","Uang Muka Diterima – Maklon (Termin)","LIABILITY",False,{},"2-100",None),
    ("2-150","Hutang Angsuran Kendaraan/Inventaris","LIABILITY",False,{},"2-100",None),
    ("2-160","Hutang Lancar Lainnya","LIABILITY",False,{},"2-100",None),
    # KEWAJIBAN JANGKA PANJANG
    ("2-200","KEWAJIBAN JANGKA PANJANG","LIABILITY",True,{},"2-000",None),
    ("2-210","Hutang Bank – Kredit Lokal (3921555545)","LIABILITY",False,{"is_long_term":True},"2-200",None),
    ("2-211","Hutang Bank – Kredit Lokal (3923445567)","LIABILITY",False,{"is_long_term":True},"2-200",None),
    ("2-220","Hutang Jangka Panjang Lainnya","LIABILITY",False,{},"2-200",None),
    # EKUITAS
    ("3-100","Modal Disetor","EQUITY",False,{"is_capital":True},"3-000",None),
    ("3-200","Laba Ditahan","EQUITY",False,{"is_retained_earnings":True},"3-000",None),
    ("3-300","Laba / Rugi Tahun Berjalan","EQUITY",False,{"is_current_earnings":True},"3-000",None),
    ("3-400","Prive / Penarikan Pemilik","EQUITY",False,{"is_contra":True},"3-000","DEBIT"),
    # PENDAPATAN OS
    ("4-100","Pendapatan Online Shop","REVENUE",True,{},"4-000",None),
    ("4-111","Penjualan – Shopee Grosirhijabsragen","REVENUE",False,{"is_sales":True,"channel":"shopee"},"4-100",None),
    ("4-112","Penjualan – Shopee Daluna","REVENUE",False,{"is_sales":True,"channel":"shopee"},"4-100",None),
    ("4-113","Penjualan – Shopee Moen","REVENUE",False,{"is_sales":True,"channel":"shopee"},"4-100",None),
    ("4-114","Penjualan – Shopee Lain-lain","REVENUE",False,{"is_sales":True,"channel":"shopee"},"4-100",None),
    ("4-121","Penjualan – TikTok Daluna","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-122","Penjualan – TikTok Outfit Boutique","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-123","Penjualan – TikTok Style by Moen","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-124","Penjualan – TikTok Fatimahijab","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-125","Penjualan – TikTok Dezza Kids","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-126","Penjualan – TikTok Lain-lain","REVENUE",False,{"is_sales":True,"channel":"tiktok"},"4-100",None),
    ("4-131","Penjualan – Tokopedia","REVENUE",False,{"is_sales":True,"channel":"tokopedia"},"4-100",None),
    ("4-140","Retur Penjualan Online Shop","REVENUE",False,{"is_contra":True},"4-100","DEBIT"),
    ("4-141","Potongan Platform (Fee Shopee/TikTok)","REVENUE",False,{"is_contra":True},"4-100","DEBIT"),
    # PENDAPATAN MAKLON
    ("4-200","Pendapatan Maklon","REVENUE",True,{},"4-000",None),
    ("4-210","Pendapatan Maklon – SnBm","REVENUE",False,{"is_sales":True},"4-200",None),
    ("4-220","Pendapatan Maklon – Klien Lain-lain","REVENUE",False,{"is_sales":True},"4-200",None),
    ("4-230","Retur / Potongan Maklon","REVENUE",False,{"is_contra":True},"4-200","DEBIT"),
    # PENDAPATAN LAIN
    ("4-900","Pendapatan Lain-lain","OTHER_INCOME",True,{},"4-000",None),
    ("4-910","Pendapatan Bunga Bank","OTHER_INCOME",False,{"is_interest_income":True},"4-900",None),
    ("4-920","Pendapatan di Luar Usaha Lainnya","OTHER_INCOME",False,{},"4-900",None),
    # HPP OS
    ("5-100","HPP Online Shop","COGS",True,{},"5-000",None),
    ("5-110","Persediaan Awal Barang Dagangan","COGS",False,{},"5-100",None),
    ("5-120","Pembelian Barang Dagangan","COGS",False,{},"5-100",None),
    ("5-130","Persediaan Akhir Barang Dagangan","COGS",False,{"is_contra":True},"5-100","CREDIT"),
    # HPP PRODUKSI
    ("5-200","HPP Produksi / Maklon","COGS",True,{},"5-000",None),
    ("5-210","Pemakaian Bahan Baku (Kain)","COGS",False,{"is_cogs_material":True},"5-200",None),
    ("5-220","Pemakaian Bahan Pembantu (Aksesori)","COGS",False,{"is_cogs_material":True},"5-200",None),
    ("5-230","Biaya Vendor CMT – Cutting","COGS",False,{"is_cogs_labor":True},"5-200",None),
    ("5-231","Biaya Vendor CMT – Jahit","COGS",False,{"is_cogs_labor":True},"5-200",None),
    ("5-240","Biaya Ekspedisi Bahan Baku","COGS",False,{"is_cogs_overhead":True},"5-200",None),
    ("5-250","Biaya Overhead Pabrik (BOP)","COGS",False,{"is_cogs_overhead":True},"5-200",None),
    ("5-260","Persediaan Akhir WIP","COGS",False,{"is_contra":True},"5-200","CREDIT"),
    # BIAYA OS
    ("6-100","Biaya Pemasaran & Iklan","EXPENSE",True,{},"6-000",None),
    ("6-110","Biaya Iklan TikTok Ads","EXPENSE",False,{},"6-100",None),
    ("6-111","Biaya Iklan Facebook / Meta Ads","EXPENSE",False,{},"6-100",None),
    ("6-112","Biaya Iklan Shopee Ads","EXPENSE",False,{},"6-100",None),
    ("6-113","Biaya Iklan Tokopedia Ads","EXPENSE",False,{},"6-100",None),
    ("6-120","Biaya Endorsement","EXPENSE",False,{},"6-100",None),
    ("6-130","Biaya Pemasaran Lain-lain","EXPENSE",False,{},"6-100",None),
    ("6-200","Biaya Pengiriman & Logistik","EXPENSE",True,{},"6-000",None),
    ("6-210","Biaya Ongkir Penjualan (Subsidi Ongkir)","EXPENSE",False,{},"6-200",None),
    ("6-220","Biaya Penanganan COD","EXPENSE",False,{},"6-200",None),
    ("6-230","Biaya Retur & Klaim Pengiriman","EXPENSE",False,{},"6-200",None),
    ("6-300","Biaya Kemasan & Perlengkapan Toko","EXPENSE",True,{},"6-000",None),
    ("6-310","Biaya Plastik & Invoice Packaging","EXPENSE",False,{},"6-300",None),
    ("6-320","Biaya Perlengkapan Online Shop Lainnya","EXPENSE",False,{},"6-300",None),
    ("6-400","Biaya Admin & Platform OS","EXPENSE",True,{},"6-000",None),
    ("6-410","Biaya Admin & Tagihan Ekspedisi (JNT)","EXPENSE",False,{},"6-400",None),
    ("6-420","Biaya Langganan Aplikasi (SaaS/Data)","EXPENSE",False,{},"6-400",None),
    ("6-430","Biaya Bonus Target Karyawan OS","EXPENSE",False,{},"6-400",None),
    # BIAYA MAKLON
    ("7-100","Biaya Produksi Maklon","EXPENSE",True,{},"7-000",None),
    ("7-110","Biaya Bahan Klien Maklon","EXPENSE",False,{},"7-100",None),
    ("7-120","Biaya Vendor CMT – Maklon","EXPENSE",False,{},"7-100",None),
    ("7-130","Biaya Pengiriman ke Klien Maklon","EXPENSE",False,{},"7-100",None),
    ("7-140","Biaya Administrasi Maklon","EXPENSE",False,{},"7-100",None),
    # BIAYA PRODUKSI OVERHEAD
    ("8-100","Gaji & SDM Produksi","EXPENSE",True,{},"8-000",None),
    ("8-110","Gaji Karyawan Gudang","EXPENSE",False,{"is_salary_expense":True},"8-100",None),
    ("8-111","Tunjangan Kesehatan Karyawan Gudang","EXPENSE",False,{},"8-100",None),
    ("8-112","Bonus Komisi Karyawan Gudang","EXPENSE",False,{},"8-100",None),
    ("8-200","Utilitas Produksi","EXPENSE",True,{},"8-000",None),
    ("8-210","Listrik – Gudang / Produksi","EXPENSE",False,{},"8-200",None),
    ("8-220","Listrik – Unit Usaha Lain","EXPENSE",False,{},"8-200",None),
    ("8-230","Telpon & Internet – Operasional Produksi","EXPENSE",False,{},"8-200",None),
    ("8-300","Beban Penyusutan Aset","EXPENSE",True,{},"8-000",None),
    ("8-310","Beban Penyusutan – Bangunan","EXPENSE",False,{"is_depreciation":True},"8-300",None),
    ("8-320","Beban Penyusutan – Peralatan Produksi","EXPENSE",False,{"is_depreciation":True},"8-300",None),
    ("8-330","Beban Penyusutan – Kendaraan","EXPENSE",False,{"is_depreciation":True},"8-300",None),
    ("8-340","Beban Penyusutan – Peralatan Kantor","EXPENSE",False,{"is_depreciation":True},"8-300",None),
    # BIAYA UMUM & ADMIN
    ("9-100","Gaji & SDM Kantor","EXPENSE",True,{},"9-000",None),
    ("9-110","Gaji Pimpinan / Direksi","EXPENSE",False,{"is_salary_expense":True},"9-100",None),
    ("9-120","Gaji Karyawan Admin & Kantor","EXPENSE",False,{"is_salary_expense":True},"9-100",None),
    ("9-130","Tunjangan & BPJS Karyawan","EXPENSE",False,{},"9-100",None),
    ("9-200","Biaya Kantor & Umum","EXPENSE",True,{},"9-000",None),
    ("9-210","Alat Tulis & Perlengkapan Kantor","EXPENSE",False,{},"9-200",None),
    ("9-220","Biaya Sewa Tempat","EXPENSE",False,{},"9-200",None),
    ("9-230","Listrik & Air – Kantor","EXPENSE",False,{},"9-200",None),
    ("9-240","Telpon, Internet & Pulsa","EXPENSE",False,{},"9-200",None),
    ("9-250","Biaya Transportasi & Perjalanan Dinas","EXPENSE",False,{"is_travel_expense":True},"9-200",None),
    ("9-260","Biaya Makan & Representasi","EXPENSE",False,{},"9-200",None),
    ("9-270","Biaya Kesehatan (Non-Tunjangan)","EXPENSE",False,{},"9-200",None),
    ("9-280","Biaya Sosial & Kegiatan Karyawan","EXPENSE",False,{},"9-200",None),
    ("9-290","Biaya Administrasi Lainnya","EXPENSE",False,{},"9-200",None),
    ("9-300","Biaya Keuangan & Bank","EXPENSE",True,{},"9-000",None),
    ("9-310","Biaya Administrasi Bank","EXPENSE",False,{"is_bank_charge":True},"9-300",None),
    ("9-320","Biaya Bunga Pinjaman Bank","EXPENSE",False,{},"9-300",None),
    ("9-330","Pajak Bunga Tabungan","EXPENSE",False,{},"9-300",None),
    ("9-340","Biaya Transfer Antar Bank","EXPENSE",False,{},"9-300",None),
    ("9-350","Biaya Kartu Kredit / Fasilitas Pinjaman","EXPENSE",False,{},"9-300",None),
    ("9-400","Biaya Lain-lain","EXPENSE",True,{},"9-000",None),
    ("9-410","Biaya Pajak & Perizinan","EXPENSE",False,{},"9-400",None),
    ("9-420","Biaya di Luar Usaha Lainnya","EXPENSE",False,{},"9-400",None),
]


# ── Skema 4-digit KANONIK (audit finance 2026-09-04, keputusan owner) ─────────
# Dulu (G4) 11 akun SEED_TEMPLATE yang namanya sama dgn DA 3-digit tidak di-seed
# (kanonik = 3-digit). Sekarang dibalik: SEMUA akun 4-digit di-seed, akun legacy
# 3-digit NERACA (1-xxx/2-xxx/3-xxx) yang belum pernah dipakai jurnal DINONAKTIFKAN.
DUP_TEMPLATE_CODES: set = set()

# parent eksplisit bila _infer_parent_code menunjuk akun postable (bukan header)
PARENT_OVERRIDES = {"2-1150": "2-1000", "2-1700": "2-1000"}

# legacy 3-digit → akun 4-digit kanonik (dipakai remap profil + flag legacy_of)
LEGACY_CODE_MAP = {
    "1-110": "1-1101", "1-120": "1-1320",
    "1-131": "1-1201", "1-132": "1-1201", "1-133": "1-1201", "1-134": "1-1201",
    "1-135": "1-1201", "1-136": "1-1201", "1-137": "1-1201",
    "1-141": "1-1201", "1-142": "1-1201", "1-143": "1-1201", "1-144": "1-1201", "1-145": "1-1201",
    "1-151": "1-1201", "1-152": "1-1201", "1-153": "1-1201", "1-154": "1-1201", "1-155": "1-1201",
    "1-210": "1-1301", "1-211": "1-1302", "1-220": "1-1303", "1-230": "1-1304",
    "1-310": "1-1401", "1-320": "1-1402", "1-330": "1-1403", "1-340": "1-1404", "1-350": "1-1404",
    "1-410": "1-1620", "1-420": "1-1620", "1-430": "1-1620", "1-440": "1-1501", "1-450": "1-1620",
    "1-510": "1-2100", "1-520": "1-2200", "1-521": "1-2201", "1-530": "1-2400", "1-531": "1-2401",
    "1-540": "1-2300", "1-541": "1-2301", "1-550": "1-2500", "1-551": "1-2501",
    "1-610": "1-2200", "1-620": "1-1620",
    "2-110": "2-1100", "2-111": "2-1100", "2-112": "2-1100", "2-113": "2-1100",
    "2-120": "2-1200", "2-121": "2-1200", "2-122": "2-1500", "2-123": "2-1500",
    "2-130": "2-1400", "2-131": "2-1301", "2-132": "2-1302", "2-133": "2-1303",
    "2-140": "2-1700", "2-150": "2-1600", "2-160": "2-1600",
    "2-210": "2-2100", "2-211": "2-2100", "2-220": "2-2100",
    "3-100": "3-1000", "3-200": "3-2000", "3-300": "3-3000", "3-400": "3-4000",
}
LEGACY_TYPE_MAP = {"CURRENT_ASSET": "ASSET", "FIXED_ASSET": "ASSET", "OTHER": "OTHER_INCOME",
                   "INCOME": "REVENUE", "CURRENT_LIABILITY": "LIABILITY"}


async def migrate_coa_canonical(db) -> dict:
    """Idempoten. (1) normalisasi tipe akun tak dikenal, (2) perbaiki parent akun
    4-digit yang yatim, (3) nonaktifkan akun legacy 3-digit neraca yang belum pernah
    dipakai jurnal (akun yang sudah dipakai tetap aktif, hanya diberi flag)."""
    report = {"type_fixed": [], "parent_fixed": [], "deactivated": [], "legacy_still_used": [],
              "channel_mapping_remapped": 0, "subledger_parent_fixed": []}
    used_codes = set(await db.rahaza_journal_lines.distinct("account_code"))
    # rekening kas/bank yang menunjuk akun legacy tetap dianggap "dipakai" (jangan dinonaktifkan)
    used_codes |= {c for c in await db.rahaza_cash_accounts.distinct("gl_account_code") if c}
    # channel GL mapping & parent subledger Auto-COA → kode kanonik
    async for ch in db.rahaza_channel_gl_mapping.find({}, {"_id": 0, "id": 1, "debit_ar": 1, "credit_revenue": 1}):
        upd = {k: LEGACY_CODE_MAP[ch[k]] for k in ("debit_ar", "credit_revenue")
               if ch.get(k) in LEGACY_CODE_MAP}
        if upd:
            await db.rahaza_channel_gl_mapping.update_one({"id": ch["id"]}, {"$set": upd})
            report["channel_mapping_remapped"] += 1
    auto = await db.rahaza_coa_auto_settings.find_one({"id": "default"}, {"_id": 0}) or {}
    for et, cfg in (auto.get("entity_types") or {}).items():
        pc = (cfg or {}).get("parent_code")
        if pc in LEGACY_CODE_MAP:
            await db.rahaza_coa_auto_settings.update_one(
                {"id": "default"}, {"$set": {f"entity_types.{et}.parent_code": LEGACY_CODE_MAP[pc]}})
            report["subledger_parent_fixed"].append(f"{et}:{pc}->{LEGACY_CODE_MAP[pc]}")
    accounts = await db.rahaza_coa_accounts.find({}, {"_id": 0}).to_list(5000)
    codes = {a["code"] for a in accounts}
    four_digit_codes = [a["code"] for a in accounts
                        if len(a["code"].split("-")) == 2 and len(a["code"].split("-")[1]) == 4]
    for a in accounts:
        code = a["code"]
        upd = {}
        t = (a.get("type") or "").upper()
        if t not in ACCOUNT_TYPES:
            nt = LEGACY_TYPE_MAP.get(t) or {"1": "ASSET", "2": "LIABILITY", "3": "EQUITY", "4": "REVENUE",
                                            "5": "COGS"}.get(code[:1], "EXPENSE")
            upd["type"] = nt
            if not (a.get("flags") or {}).get("is_contra"):
                upd["normal_balance"] = _normal_balance_for(nt)
            report["type_fixed"].append(f"{code}:{t}->{nt}")
        if code in PARENT_OVERRIDES and a.get("parent_code") != PARENT_OVERRIDES[code]:
            upd["parent_code"] = PARENT_OVERRIDES[code]
            report["parent_fixed"].append(code)
        elif code in four_digit_codes and not a.get("parent_code"):
            p = _infer_parent_code(code, four_digit_codes)
            if p and p in codes:
                upd["parent_code"] = p
                report["parent_fixed"].append(code)
        if code in LEGACY_CODE_MAP:
            flags = dict(a.get("flags") or {})
            flags["legacy_of"] = LEGACY_CODE_MAP[code]
            if code in used_codes:
                flags["legacy_used_in_journal"] = True
                report["legacy_still_used"].append(code)
            elif a.get("active", True):
                upd["active"] = False
                flags["deactivated_reason"] = "legacy_3digit_canonical_4digit"
                report["deactivated"].append(code)
            if flags != (a.get("flags") or {}):
                upd["flags"] = flags
        if upd:
            upd["updated_at"] = _now()
            await db.rahaza_coa_accounts.update_one({"code": code}, {"$set": upd})
    return report


@router.post("/migrate-canonical")
async def migrate_canonical_endpoint(request: Request):
    """Jalankan ulang normalisasi COA kanonik 4-digit (aman diulang)."""
    user = await _require_fin(request)
    db = get_db()
    await seed_coa_accounts(db)
    report = await migrate_coa_canonical(db)
    from routes.rahaza_posting_profiles import upgrade_posting_profiles
    report["profiles"] = await upgrade_posting_profiles(db)
    await log_activity(user["id"], user.get("name", ""), "migrate_coa_canonical", "coa",
                       f"deactivated={len(report['deactivated'])} type_fixed={len(report['type_fixed'])}")
    return {"ok": True, **report}


@router.post("/seed-da")
async def seed_da_coa(request: Request, force: bool = False):
    """Seed CoA CV. Dewi Aditya (format 3-digit, 162 akun).
    force=true → hapus semua akun lama dulu (hati-hati jika sudah ada jurnal)."""
    user = await _require_fin(request)
    db = get_db()
    if force:
        await db.rahaza_coa_accounts.delete_many({})
    existing_codes: set = set()
    async for d in db.rahaza_coa_accounts.find({}, {"_id": 0, "code": 1}):
        existing_codes.add(d["code"])
    inserted = 0
    skipped = 0
    for row in DA_COA_SEED:
        code, name, acc_type, is_group, flags, parent_code, nb_override = row
        if code in existing_codes:
            skipped += 1
            continue
        normal_balance = nb_override if nb_override else _normal_balance_for(acc_type)
        doc = {
            "id": _uid(), "code": code, "name": name, "type": acc_type,
            "parent_code": parent_code, "is_group": is_group,
            "normal_balance": normal_balance, "flags": flags,
            "active": True, "created_at": _now(), "updated_at": _now(),
            "created_by": user["id"], "created_by_name": user.get("name", ""),
        }
        await db.rahaza_coa_accounts.insert_one(doc)
        inserted += 1
    await seed_coa_accounts(db)
    await migrate_coa_canonical(db)
    await log_activity(user["id"], user.get("name",""), "seed_da_coa", "coa",
                       f"inserted={inserted} skipped={skipped}")
    return {"ok": True, "inserted": inserted, "skipped": skipped, "total": len(DA_COA_SEED)}


async def seed_coa_accounts(db) -> dict:
    """RC-21: Seed COA idempotent (by code) — dipakai auto-seed startup server.py Phase 7D
    dan bisa dipanggil ulang kapan saja. Mengisi DUA template sekaligus:
      - SEED_TEMPLATE (format 4-digit, mis. 1-1101/6-3400/6-3500) — direferensikan
        posting engine & default expense/travel (RC-05) dan sebagian posting profiles.
      - DA_COA_SEED (format 3-digit, mis. 1-110/4-111/5-111) — direferensikan
        seed JE production_seed_full (coa_map) dan posting profiles DA.
    Tanpa Request — callable murni (db)."""
    existing_codes: set = set()
    async for d in db.rahaza_coa_accounts.find({}, {"_id": 0, "code": 1}):
        existing_codes.add(d["code"])
    inserted = 0
    skipped = 0
    template_codes = [c for c, *_ in SEED_TEMPLATE if c not in DUP_TEMPLATE_CODES]
    for code, name, acc_type, is_group, flags in SEED_TEMPLATE:
        if code in DUP_TEMPLATE_CODES:   # G4: nama duplikat → kanonik DA 3-digit
            skipped += 1
            continue
        if code in existing_codes:
            skipped += 1
            continue
        await db.rahaza_coa_accounts.insert_one({
            "id": _uid(), "code": code, "name": name, "type": acc_type,
            "parent_code": PARENT_OVERRIDES.get(code) or _infer_parent_code(code, template_codes),
            "is_group": is_group, "normal_balance": _normal_balance_for(acc_type),
            "flags": flags, "active": True,
            "created_at": _now(), "updated_at": _now(),
            "created_by": "system", "created_by_name": "auto-seed",
        })
        existing_codes.add(code)
        inserted += 1
    for row in DA_COA_SEED:
        code, name, acc_type, is_group, flags, parent_code, nb_override = row
        if code in existing_codes:
            skipped += 1
            continue
        await db.rahaza_coa_accounts.insert_one({
            "id": _uid(), "code": code, "name": name, "type": acc_type,
            "parent_code": parent_code, "is_group": is_group,
            "normal_balance": nb_override if nb_override else _normal_balance_for(acc_type),
            "flags": flags, "active": True,
            "created_at": _now(), "updated_at": _now(),
            "created_by": "system", "created_by_name": "auto-seed",
        })
        existing_codes.add(code)
        inserted += 1
    return {"inserted": inserted, "skipped": skipped,
            "total_template": len(SEED_TEMPLATE) + len(DA_COA_SEED)}


def _infer_parent_code(code: str, all_codes: list) -> str | None:
    """For code '1-1101' → parent '1-1100'; for '1-1100' → '1-1000'; for '1-1000' → '1-0000'; for '1-0000' → None."""
    # garment code format: x-abcd where each digit level
    try:
        root, rest = code.split("-")
        if len(rest) != 4 or not rest.isdigit():
            return None
        # find parent by zero-filling from least significant non-zero digit
        digits = list(rest)
        # Move from right: change first non-zero digit to 0
        for i in range(3, -1, -1):
            if digits[i] != "0":
                digits[i] = "0"
                candidate = f"{root}-{''.join(digits)}"
                if candidate != code and candidate in all_codes:
                    return candidate
                # continue to zero out higher
        return None
    except Exception:
        return None
