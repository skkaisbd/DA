"""rahaza_admin — master setup helper functions."""
# ruff: noqa: E741
from fastapi import Request, HTTPException
from auth import require_auth, hash_password
from routes.rahaza_master import seed_rahaza_master_data
from routes.rahaza_coa import SEED_TEMPLATE, _normal_balance_for, _infer_parent_code
from routes.rahaza_posting_profiles import DEFAULT_PROFILES as PROFILE_TEMPLATES
import random
import logging
from datetime import datetime, timedelta, date
from utils.waktu import now_wib

from routes.rahaza_admin_shared import (
    _uid, _now,
    MACHINE_SEED, LINE_SEED, EMPLOYEE_SEED, MODEL_SEED, SIZE_SEED,
    CUSTOMER_SEED, MATERIAL_SEED, COST_CENTER_SEED, CASH_ACCOUNT_SEED,
)

logger = logging.getLogger(__name__)


async def _require_super(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in ("superadmin", "admin"):
        raise HTTPException(403, "Forbidden: butuh role superadmin/admin.")
    return user


async def _ensure_period(db, d: date) -> str:
    """Ensure period exists for date d (status=open)."""
    year = d.year
    month = d.month
    period_code = f"{year}-{month:02d}"
    existing = await db.rahaza_periods.find_one({"period_code": period_code}, {"_id": 0})
    if existing:
        return period_code
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    await db.rahaza_periods.insert_one({
        "id": _uid(),
        "period_code": period_code,
        "year": year,
        "month": month,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "status": "open",
        "closed_at": None,
        "closed_by": None,
        "locked": False,
        "created_at": _now(),
        "updated_at": _now(),
    })
    return period_code


async def _seed_coa(db, user: dict):
    inserted = 0
    codes_in_template = [c for c, *_ in SEED_TEMPLATE]
    existing_codes = set()
    async for d in db.rahaza_coa_accounts.find({"code": {"$in": codes_in_template}}, {"_id": 0, "code": 1}):
        existing_codes.add(d["code"])
    for code, name, acc_type, is_group, flags in SEED_TEMPLATE:
        if code in existing_codes:
            continue
        parent_code = _infer_parent_code(code, codes_in_template)
        await db.rahaza_coa_accounts.insert_one({
            "id": _uid(),
            "code": code, "name": name, "type": acc_type,
            "parent_code": parent_code, "is_group": is_group,
            "normal_balance": _normal_balance_for(acc_type),
            "flags": flags, "active": True,
            "created_at": _now(), "updated_at": _now(),
            "created_by": user["id"], "created_by_name": user.get("name", ""),
        })
        inserted += 1
    return inserted


async def _seed_posting_profiles(db, user: dict):
    """Seed default posting profiles (proper schema with `mapping` dict)."""
    count = 0
    event_types = [p["event_type"] for p in PROFILE_TEMPLATES]
    existing_events = set()
    async for d in db.rahaza_posting_profiles.find(
        {"event_type": {"$in": event_types}}, {"_id": 0, "event_type": 1}
    ):
        existing_events.add(d["event_type"])
    for p in PROFILE_TEMPLATES:
        if p["event_type"] in existing_events:
            continue
        await db.rahaza_posting_profiles.insert_one({
            "id": _uid(),
            "event_type": p["event_type"],
            "description": p["description"],
            "mapping": p["mapping"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
        })
        count += 1
    return count


async def _seed_master_data(db, user: dict) -> dict:
    """Seed full master dataset. Returns ID maps for referencing."""
    maps: dict = {
        "locations": {}, "processes": {}, "shifts": {},
        "machines": {}, "lines": {}, "employees": {},
        "models": {}, "sizes": {}, "customers": {},
        "materials": {}, "cash_accounts": {}, "cost_centers": {},
        "employee_users": {},
    }

    await seed_rahaza_master_data()
    for r in await db.rahaza_locations.find({}, {"_id": 0}).to_list(500):
        maps["locations"][r["code"]] = r["id"]
    for r in await db.rahaza_processes.find({}, {"_id": 0}).to_list(500):
        maps["processes"][r["code"]] = r["id"]
    for r in await db.rahaza_shifts.find({}, {"_id": 0}).to_list(500):
        maps["shifts"][r["code"]] = r["id"]

    # Machines
    for m in MACHINE_SEED:
        doc = {
            "id": _uid(), "code": m["code"], "name": m["name"],
            "machine_type": m["machine_type"], "gauge": m.get("gauge", ""),
            "location_id": maps["locations"].get(m["location_code"]),
            "status": "active", "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_machines.insert_one(doc)
        maps["machines"][m["code"]] = doc["id"]

    # Lines
    for ln in LINE_SEED:
        doc = {
            "id": _uid(), "code": ln["code"], "name": ln["name"],
            "process_id": maps["processes"].get(ln["process_code"]),
            "location_id": maps["locations"].get(ln["location_code"]),
            "capacity_per_hour": ln["capacity_per_hour"],
            "notes": "", "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_lines.insert_one(doc)
        maps["lines"][ln["code"]] = doc["id"]

    # Employees
    for e in EMPLOYEE_SEED:
        doc = {
            "id": _uid(), "employee_code": e["code"], "name": e["name"],
            "job_title": e["job_title"],
            "location_id": maps["locations"].get("ZNA-RAJUT"),
            "phone": f"0812-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
            "wage_scheme": e["wage_scheme"],
            "base_rate": e["base_rate"],
            "joined_at": (_now() - timedelta(days=365)).isoformat(),
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_employees.insert_one(doc)
        maps["employees"][e["code"]] = doc["id"]

        emp_user_pwd = "Employee@123"
        emp_user_hash = hash_password(emp_user_pwd)
        emp_username = e["code"].lower().replace("-", "") + "@garment.com"
        emp_user_doc = {
            "id": _uid(),
            "email": emp_username,
            "password": emp_user_hash,
            "name": e["name"],
            "role": "karyawan",
            "employee_id": doc["id"],
            "portal_access": ["self", "production"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.users.update_one({"email": emp_username}, {"$setOnInsert": emp_user_doc}, upsert=True)
        maps["employee_users"][e["code"]] = emp_user_doc["id"]

        scheme_map = {
            "bulanan": "monthly", "mingguan": "weekly",
            "borongan_pcs": "pcs", "borongan_jam": "hourly",
        }
        profile_doc = {
            "id": _uid(),
            "employee_id": doc["id"],
            "employee_code": e["code"],
            "employee_name": e["name"],
            "pay_scheme": scheme_map.get(e["wage_scheme"], "monthly"),
            "wage_scheme": e["wage_scheme"],
            "base_rate": e["base_rate"],
            "overtime_multiplier": 1.5,
            "meal_allowance": 20000,
            "transport_allowance": 15000,
            "bpjs_kes": 0.01,
            "bpjs_tk": 0.02,
            "pph21_bracket": "progressive",
            "effective_from": (_now() - timedelta(days=365)).isoformat(),
            "effective_to": None,
            "active": True,
            "created_at": _now(), "updated_at": _now(),
            "created_by": user["id"],
        }
        await db.rahaza_payroll_profiles.insert_one(profile_doc)

    # Models
    for m in MODEL_SEED:
        doc = {
            "id": _uid(), "code": m["code"], "name": m["name"],
            "category": "Sweater Rajut",
            "base_hpp": m["base_hpp"],
            "retail_price": m["retail_price"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_models.insert_one(doc)
        maps["models"][m["code"]] = doc["id"]

    # Sizes
    for s in SIZE_SEED:
        doc = {
            "id": _uid(), "code": s["code"], "name": s["name"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_sizes.insert_one(doc)
        maps["sizes"][s["code"]] = doc["id"]

    # Customers
    for c in CUSTOMER_SEED:
        doc = {
            "id": _uid(), "code": c["code"], "name": c["name"],
            "company_type": "company",
            "npwp": f"01.{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(1, 9)}-000.000",
            "phone": f"021-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
            "email": f"{c['code'].lower()}@example.co.id",
            "address": c["address"],
            "payment_terms": c["payment_terms"],
            "payment_terms_custom": "",
            "credit_limit": 500_000_000,
            "notes": "",
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_customers.insert_one(doc)
        maps["customers"][c["code"]] = doc["id"]

    # Materials (+ opening stock)
    default_loc_id = maps["locations"].get("ZNA-GDG-A") or list(maps["locations"].values())[0]
    for m in MATERIAL_SEED:
        doc = {
            "id": _uid(), "code": m["code"], "name": m["name"],
            "type": m["type"], "unit": m["unit"],
            "unit_cost": m["unit_cost"],
            "min_stock": m["min_stock"],
            "max_stock": m["max_stock"],
            "min_stock_qty": m.get("min_stock_qty"),
            "min_stock_percentage": m.get("min_stock_pct"),
            "reorder_point": m.get("reorder_point"),
            "description": "",
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_materials.insert_one(doc)
        maps["materials"][m["code"]] = doc["id"]
        qty = (
            round(m["max_stock"] * random.uniform(0.1, 0.25), 2)
            if m["type"] == "accessory"
            else round(m["max_stock"] * random.uniform(0.4, 0.7), 2)
        )
        await db.rahaza_material_stock.insert_one({
            "id": _uid(),
            "material_id": doc["id"],
            "location_id": default_loc_id,
            "qty": qty,
            "updated_at": _now(),
        })

    # Cost Centers
    for cc in COST_CENTER_SEED:
        doc = {
            "id": _uid(), "code": cc["code"], "name": cc["name"],
            "description": cc["description"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_cost_centers.insert_one(doc)
        maps["cost_centers"][cc["code"]] = doc["id"]

    # Cash Accounts
    for ca in CASH_ACCOUNT_SEED:
        doc = {
            "id": _uid(), "code": ca["code"], "name": ca["name"],
            "account_type": ca["account_type"],
            "coa_code": ca["coa_code"],
            "currency": "IDR",
            "opening_balance": ca["opening_balance"],
            "current_balance": ca["opening_balance"],
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_cash_accounts.insert_one(doc)
        maps["cash_accounts"][ca["code"]] = doc["id"]

    # BOMs (Phase 7A Fase 1 — skema materials[] kanonik)
    yarn_materials = [m for m in MATERIAL_SEED if m["type"] == "yarn"]
    acc_materials  = [m for m in MATERIAL_SEED if m["type"] == "accessory"]
    for m_code, m_id in maps["models"].items():
        for s_code, s_id in maps["sizes"].items():
            chosen_yarn = random.choice(yarn_materials)
            chosen_acc  = random.choice(acc_materials)
            yarn_qty = {"S": 0.35, "M": 0.42, "L": 0.50, "XL": 0.58}.get(s_code, 0.45)
            await db.rahaza_boms.insert_one({
                "id": _uid(),
                "model_id": m_id, "size_id": s_id, "color": "",
                "version": 1, "is_active": True, "active": True,
                "materials": [
                    {
                        "material_id": maps["materials"][chosen_yarn["code"]],
                        "code": chosen_yarn["code"],
                        "name": chosen_yarn["name"],
                        "material_type": "yarn",
                        "category": "", "category_name": "Benang",
                        "qty": yarn_qty, "unit": chosen_yarn["unit"],
                        "notes": "",
                    },
                    {
                        "material_id": maps["materials"][chosen_acc["code"]],
                        "code": chosen_acc["code"],
                        "name": chosen_acc["name"],
                        "material_type": "accessory",
                        "category": "", "category_name": "Aksesoris",
                        "qty": 4 if chosen_acc["unit"] == "pcs" else 1,
                        "unit": chosen_acc["unit"],
                        "notes": "",
                    },
                ],
                "notes": "",
                "created_at": _now(), "updated_at": _now(),
            })

    return maps


async def _gen_order_number(db, i: int) -> str:
    return f"ORD-{now_wib().year}-{i:04d}"


async def _gen_wo_number(db, i: int) -> str:
    return f"WO-{now_wib().year}-{i:04d}"


async def _gen_inv_number(db, prefix: str, i: int) -> str:
    return f"{prefix}-{now_wib().year}{now_wib().month:02d}-{i:04d}"
