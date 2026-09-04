"""
CV. Dewi Aditya ERP — MASTER SUPPLIER (SSOT Pengadaan)

LATAR BELAKANG (audit 2026-08-06)
--------------------------------
Sebelum modul ini, TIDAK ADA master supplier sama sekali:
  · `rahaza_po.py` menerima `vendor_name` sebagai TEKS BEBAS (tanpa relasi).
  · `rahaza_grn_qc.py` `/supplier-scorecard` meng-agregat berdasarkan STRING
    `supplier_name` di `rahaza_grn_inspections` ⇒ satu supplier dengan dua ejaan
    ("PT Benang Jaya" vs "PT. Benang Jaya") memecah scorecard menjadi dua.
  · `vendor_partners` BUKAN supplier material — itu vendor CMT (jahit/subkontrak)
    yang dipakai flow maklon/produksi. Jangan dicampur.

Modul ini menjadi **satu-satunya** master supplier material/jasa pengadaan.

KOLEKSI
-------
`rahaza_suppliers`
    {
      id, code (unik), name, name_key (nama ternormalisasi utk dedup),
      npwp, tax_name, address, city, province, postal_code, country,
      contacts: [{name, position, phone, email, is_primary}],
      phone, email, website,
      payment_terms ('cod'|'net7'|'net14'|'net30'|'net45'|'net60'|'net90'),
      currency ('IDR'|'USD'|...), tax_type ('ppn'|'non_ppn'),
      bank_accounts: [{bank_name, account_number, account_holder, branch, is_primary}],
      categories: [str]  # kategori barang yang disuplai
      material_types: [str]   # yarn/fabric/accessory/packaging/service/asset
      lead_time_days: int, min_order_value: float,
      rating_manual: 1..5|None, is_active: bool, notes,
      source ('manual'|'migrated'),
      created_at, created_by, updated_at
    }

`rahaza_supplier_price_lists`
    {
      id, supplier_id, material_id, material_code, material_name,
      uom (satuan beli), factor_to_base, base_uom,
      price (per `uom`), price_base (per satuan dasar — INV-UOM-1),
      currency, moq (dalam `uom`), lead_time_days,
      valid_from (ISO date), valid_to (ISO date|None),
      is_active, notes, created_at, updated_at
    }

INVARIAN
--------
* SUP-1  `code` unik & tidak pernah berubah setelah dibuat.
* SUP-2  `name_key` = nama di-lowercase, tanda baca & spasi ganda dibuang →
         dipakai untuk dedup saat migrasi dan saat create manual.
* SUP-3  `price_base` SELALU harga per satuan DASAR material (INV-UOM-1) supaya
         konsumen hilir (PO, HPP, jurnal) tidak pernah salah kali/bagi.
* SUP-4  Migrasi TIDAK PERNAH menghapus string asli (`vendor_name` /
         `supplier_name` tetap ada) — hanya MENAMBAH `supplier_id`/`supplier_code`.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth, serialize_doc, log_activity
from core import bom_uom, uom as uom_core
from core.pr_approval import ACC_PR_COLLECTION, ACC_PR_SUPPLIER_FIELD
from routes.shared import require_portal
from database import get_db
from utils.counters import gen_prefixed_number

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/procurement", tags=["procurement-suppliers"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


PAYMENT_TERMS = [
    {"value": "cod", "label": "COD / Bayar di Tempat", "days": 0},
    {"value": "cbd", "label": "CBD / Bayar di Muka", "days": 0},
    {"value": "net7", "label": "NET 7 Hari", "days": 7},
    {"value": "net14", "label": "NET 14 Hari", "days": 14},
    {"value": "net30", "label": "NET 30 Hari", "days": 30},
    {"value": "net45", "label": "NET 45 Hari", "days": 45},
    {"value": "net60", "label": "NET 60 Hari", "days": 60},
    {"value": "net90", "label": "NET 90 Hari", "days": 90},
]
PAYMENT_TERM_DAYS = {t["value"]: t["days"] for t in PAYMENT_TERMS}

SUPPLIER_CATEGORIES = [
    {"value": "yarn", "label": "Benang"},
    {"value": "fabric", "label": "Kain"},
    {"value": "accessory", "label": "Aksesoris"},
    {"value": "packaging", "label": "Kemasan"},
    {"value": "chemical", "label": "Kimia / Pewarna"},
    {"value": "spare_part", "label": "Suku Cadang Mesin"},
    {"value": "office", "label": "ATK / Kantor"},
    {"value": "asset", "label": "Aset / Mesin"},
    {"value": "service", "label": "Jasa"},
    {"value": "other", "label": "Lainnya"},
]

CURRENCIES = ["IDR", "USD", "CNY", "SGD", "EUR", "JPY"]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: normalisasi nama (SUP-2)
# ─────────────────────────────────────────────────────────────────────────────
_LEGAL_PREFIX = re.compile(
    r"^(pt|cv|ud|pd|toko|koperasi|kop|firma|fa|pt\.|cv\.|ud\.|pd\.)[\s\.]+", re.I
)


def name_key(name: str) -> str:
    """Kunci dedup nama supplier.

    "PT. Benang Jaya  Abadi" → "benang jaya abadi"
    "CV Benang-Jaya Abadi"   → "benang jaya abadi"
    Prefiks badan usaha dibuang supaya ejaan "PT X" dan "PT. X" menyatu.
    """
    s = str(name or "").strip().lower()
    s = s.replace("&", " dan ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _LEGAL_PREFIX.sub("", s + " ").strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _gen_supplier_code(db, name: str = "") -> str:
    """Kode supplier: SUP-0001 — race-safe (pakai counter terpusat)."""
    return await gen_prefixed_number(db, "rahaza_suppliers", "code", "SUP-", 4)


async def _require_procurement(request: Request):
    """Butuh peran pengadaan / gudang / keuangan / manajemen."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in (
        "superadmin", "admin", "owner", "manager",
        "admin_pengadaan", "manager_pengadaan", "purchasing",
        "admin_gudang", "accounting", "staff_keuangan", "manager_keuangan",
        "manager_produksi", "supervisor",
    ):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "purchasing.manage" in perms or "warehouse.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh peran pengadaan/gudang/keuangan.")


async def _require_procurement_read(request: Request):
    """Penjaga BACA data pengadaan = butuh AKSES PORTAL Pengadaan, bukan cuma login.

    BUG-RBAC-PROC-1 (2026-08-06, ditemukan testing agent): seluruh endpoint baca di
    modul ini hanya memakai `require_auth`, sehingga SIAPA PUN yang berhasil login
    (mis. staf HR) bisa membaca Master Supplier LENGKAP — rekening bank, NPWP,
    termin pembayaran, dan DAFTAR HARGA. Itu data komersial yang sensitif.

    Memakai `require_portal` (SSOT di routes/shared.py) supaya:
      · SUPER_ROLES tetap lolos,
      · konfigurasi portal per-role milik owner (Manajemen Role) dihormati,
      · izin eksplisit (`purchasing.*`, `proc.supplier.*`) tetap bisa memberi akses
        tanpa harus menambah role ke daftar bawaan.
    """
    return await require_portal(
        request, "procurement",
        allow_perms=("purchasing.view", "purchasing.manage",
                     "proc.supplier.view", "proc.supplier.manage"),
    )


def _clean_contacts(raw) -> list:
    out = []
    for c in (raw or []):
        if not isinstance(c, dict):
            continue
        nm = (c.get("name") or "").strip()
        if not nm and not (c.get("phone") or c.get("email")):
            continue
        out.append({
            "id": c.get("id") or _uid(),
            "name": nm,
            "position": (c.get("position") or "").strip(),
            "phone": (c.get("phone") or "").strip(),
            "email": (c.get("email") or "").strip().lower(),
            "is_primary": bool(c.get("is_primary")),
        })
    if out and not any(c["is_primary"] for c in out):
        out[0]["is_primary"] = True
    return out


def _clean_banks(raw) -> list:
    out = []
    for b in (raw or []):
        if not isinstance(b, dict):
            continue
        acc = (b.get("account_number") or "").strip()
        bank = (b.get("bank_name") or "").strip()
        if not acc and not bank:
            continue
        out.append({
            "id": b.get("id") or _uid(),
            "bank_name": bank,
            "account_number": acc,
            "account_holder": (b.get("account_holder") or "").strip(),
            "branch": (b.get("branch") or "").strip(),
            "is_primary": bool(b.get("is_primary")),
        })
    if out and not any(b["is_primary"] for b in out):
        out[0]["is_primary"] = True
    return out


def _str_list(raw) -> list:
    out = []
    for v in (raw or []):
        s = str(v or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _supplier_doc_from_body(body: dict, *, current: dict | None = None) -> dict:
    cur = current or {}
    name = (body.get("name") if "name" in body else cur.get("name")) or ""
    name = str(name).strip()
    terms = str(body.get("payment_terms") if "payment_terms" in body
                else cur.get("payment_terms") or "net30").strip().lower()
    if terms not in PAYMENT_TERM_DAYS:
        terms = "net30"
    currency = str(body.get("currency") if "currency" in body
                   else cur.get("currency") or "IDR").strip().upper()
    if currency not in CURRENCIES:
        currency = "IDR"

    def pick(key, default=""):
        return (body.get(key) if key in body else cur.get(key, default)) or default

    doc = {
        "name": name,
        "name_key": name_key(name),
        "npwp": str(pick("npwp")).strip(),
        "tax_name": str(pick("tax_name")).strip(),
        "tax_type": (str(pick("tax_type", "ppn")).strip().lower() or "ppn"),
        "address": str(pick("address")).strip(),
        "city": str(pick("city")).strip(),
        "province": str(pick("province")).strip(),
        "postal_code": str(pick("postal_code")).strip(),
        "country": str(pick("country", "Indonesia")).strip() or "Indonesia",
        "phone": str(pick("phone")).strip(),
        "email": str(pick("email")).strip().lower(),
        "website": str(pick("website")).strip(),
        "payment_terms": terms,
        "payment_term_days": PAYMENT_TERM_DAYS[terms],
        "currency": currency,
        "lead_time_days": int(float(pick("lead_time_days", 0) or 0)),
        "min_order_value": round(float(pick("min_order_value", 0) or 0), 2),
        "notes": str(pick("notes")).strip(),
    }
    doc["contacts"] = _clean_contacts(
        body.get("contacts") if "contacts" in body else cur.get("contacts"))
    doc["bank_accounts"] = _clean_banks(
        body.get("bank_accounts") if "bank_accounts" in body else cur.get("bank_accounts"))
    doc["categories"] = _str_list(
        body.get("categories") if "categories" in body else cur.get("categories"))
    doc["material_types"] = _str_list(
        body.get("material_types") if "material_types" in body else cur.get("material_types"))
    rm = body.get("rating_manual") if "rating_manual" in body else cur.get("rating_manual")
    try:
        doc["rating_manual"] = int(rm) if rm not in (None, "") else None
    except (TypeError, ValueError):
        doc["rating_manual"] = None
    if "is_active" in body:
        doc["is_active"] = bool(body["is_active"])
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/suppliers/meta")
async def supplier_meta(request: Request):
    """Daftar termin bayar, kategori, mata uang untuk form (dropdown)."""
    await _require_procurement_read(request)
    return {
        "payment_terms": PAYMENT_TERMS,
        "categories": SUPPLIER_CATEGORIES,
        "currencies": CURRENCIES,
        "tax_types": [
            {"value": "ppn", "label": "PKP (kena PPN)"},
            {"value": "non_ppn", "label": "Non-PKP"},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/suppliers")
async def list_suppliers(
    request: Request,
    search: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    with_stats: bool = Query(False),
):
    """Daftar supplier (paginated). `with_stats=true` menambahkan jumlah PO & nilai."""
    await _require_procurement_read(request)
    db = get_db()
    q: dict = {}
    if is_active is not None and str(is_active) != "":
        q["is_active"] = str(is_active).lower() in ("1", "true", "yes")
    if category:
        q["categories"] = category
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"name": rx}, {"code": rx}, {"npwp": rx}, {"city": rx}, {"phone": rx}]

    total = await db.rahaza_suppliers.count_documents(q)
    rows = await (db.rahaza_suppliers.find(q, {"_id": 0})
                  .sort("name", 1).skip((page - 1) * limit).limit(limit)
                  .to_list(limit))

    if with_stats and rows:
        ids = [r["id"] for r in rows]
        agg = await db.rahaza_purchase_orders.aggregate([
            {"$match": {"supplier_id": {"$in": ids}}},
            {"$group": {"_id": "$supplier_id", "po_count": {"$sum": 1},
                        "last_po_date": {"$max": "$po_date"}}},
        ]).to_list(len(ids) + 5)
        stat = {a["_id"]: a for a in agg}
        pl_agg = await db.rahaza_supplier_price_lists.aggregate([
            {"$match": {"supplier_id": {"$in": ids}, "is_active": True}},
            {"$group": {"_id": "$supplier_id", "n": {"$sum": 1}}},
        ]).to_list(len(ids) + 5)
        pl = {a["_id"]: a["n"] for a in pl_agg}
        for r in rows:
            s = stat.get(r["id"]) or {}
            r["po_count"] = int(s.get("po_count") or 0)
            r["last_po_date"] = s.get("last_po_date")
            r["price_list_count"] = int(pl.get(r["id"]) or 0)

    return {
        "items": serialize_doc(rows),
        "pagination": {
            "page": page, "page_size": limit, "total": total,
            "total_pages": max(1, -(-total // limit)),
        },
    }


@router.get("/suppliers/options")
async def supplier_options(request: Request, search: Optional[str] = None):
    """Bentuk ringkas untuk picker PO/PR (id, code, name, terms, currency)."""
    await _require_procurement_read(request)
    db = get_db()
    q: dict = {"is_active": {"$ne": False}}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"name": rx}, {"code": rx}]
    rows = await db.rahaza_suppliers.find(
        q,
        {"_id": 0, "id": 1, "code": 1, "name": 1, "payment_terms": 1, "currency": 1,
         "phone": 1, "email": 1, "address": 1, "lead_time_days": 1, "contacts": 1},
    ).sort("name", 1).to_list(1000)
    return {"items": serialize_doc(rows)}


@router.post("/suppliers")
async def create_supplier(request: Request):
    user = await _require_procurement(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama supplier wajib diisi.")

    nk = name_key(name)
    dup = await db.rahaza_suppliers.find_one({"name_key": nk}, {"_id": 0, "code": 1, "name": 1})
    if dup:
        raise HTTPException(
            400, f"Supplier '{dup.get('name')}' ({dup.get('code')}) sudah ada dengan nama serupa.")

    code = (body.get("code") or "").strip().upper()
    if code:
        if await db.rahaza_suppliers.find_one({"code": code}, {"_id": 1}):
            raise HTTPException(400, f"Kode supplier '{code}' sudah dipakai.")
    else:
        code = await _gen_supplier_code(db, name)

    doc = {
        "id": _uid(),
        "code": code,
        **_supplier_doc_from_body(body),
        "is_active": bool(body.get("is_active", True)),
        "source": "manual",
        "created_at": _now(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "updated_at": _now(),
    }
    await db.rahaza_suppliers.insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza_suppliers",
                       f"Master supplier baru: {code} — {name}")
    return serialize_doc({k: v for k, v in doc.items() if k != "_id"})


@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, request: Request):
    await _require_procurement_read(request)
    db = get_db()
    sup = await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(404, "Supplier tidak ditemukan.")
    sup["price_list"] = serialize_doc(await db.rahaza_supplier_price_lists.find(
        {"supplier_id": supplier_id}, {"_id": 0}).sort("material_code", 1).to_list(500))
    # Ringkasan PO
    agg = await db.rahaza_purchase_orders.aggregate([
        {"$match": {"supplier_id": supplier_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]).to_list(20)
    sup["po_stats"] = {a["_id"]: a["n"] for a in agg}
    return serialize_doc(sup)


@router.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, request: Request):
    user = await _require_procurement(request)
    db = get_db()
    cur = await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Supplier tidak ditemukan.")
    body = await request.json()
    if "name" in body:
        nm = (body.get("name") or "").strip()
        if not nm:
            raise HTTPException(400, "Nama supplier wajib diisi.")
        nk = name_key(nm)
        dup = await db.rahaza_suppliers.find_one(
            {"name_key": nk, "id": {"$ne": supplier_id}}, {"_id": 0, "code": 1, "name": 1})
        if dup:
            raise HTTPException(
                400, f"Nama bentrok dengan supplier '{dup.get('name')}' ({dup.get('code')}).")

    upd = _supplier_doc_from_body(body, current=cur)
    upd["updated_at"] = _now()
    await db.rahaza_suppliers.update_one({"id": supplier_id}, {"$set": upd})

    # Nama berubah → sinkronkan cache nama di PO (bukan SSOT, hanya cermin tampilan)
    if upd.get("name") and upd["name"] != cur.get("name"):
        await db.rahaza_purchase_orders.update_many(
            {"supplier_id": supplier_id}, {"$set": {"vendor_name": upd["name"]}})

    await log_activity(user["id"], user.get("name", ""), "update", "rahaza_suppliers",
                       f"Update supplier {cur.get('code')} — {upd.get('name')}")
    out = await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/suppliers/{supplier_id}")
async def deactivate_supplier(supplier_id: str, request: Request):
    """Nonaktifkan supplier (soft delete). Ditolak bila masih ada PO berjalan."""
    user = await _require_procurement(request)
    db = get_db()
    sup = await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(404, "Supplier tidak ditemukan.")
    open_po = await db.rahaza_purchase_orders.count_documents({
        "supplier_id": supplier_id,
        "status": {"$in": ["draft", "pending_approval", "approved", "partially_received"]},
    })
    if open_po:
        raise HTTPException(
            400, f"Tidak bisa dinonaktifkan: masih ada {open_po} PO berjalan untuk supplier ini.")
    await db.rahaza_suppliers.update_one(
        {"id": supplier_id}, {"$set": {"is_active": False, "updated_at": _now()}})
    await log_activity(user["id"], user.get("name", ""), "deactivate", "rahaza_suppliers",
                       f"Nonaktifkan supplier {sup.get('code')} — {sup.get('name')}")
    return {"ok": True, "id": supplier_id, "is_active": False}


@router.post("/suppliers/{supplier_id}/activate")
async def activate_supplier(supplier_id: str, request: Request):
    user = await _require_procurement(request)
    db = get_db()
    res = await db.rahaza_suppliers.update_one(
        {"id": supplier_id}, {"$set": {"is_active": True, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Supplier tidak ditemukan.")
    await log_activity(user["id"], user.get("name", ""), "activate", "rahaza_suppliers",
                       f"Aktifkan supplier {supplier_id}")
    return {"ok": True, "id": supplier_id, "is_active": True}


# ─────────────────────────────────────────────────────────────────────────────
# PRICE LIST (per material + satuan beli)
# ─────────────────────────────────────────────────────────────────────────────
async def _price_row_from_body(db, supplier_id: str, body: dict, cur: dict | None = None) -> dict:
    cur = cur or {}
    material_id = (body.get("material_id") or cur.get("material_id") or "").strip()
    if not material_id:
        raise HTTPException(400, "material_id wajib diisi.")
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(400, f"Material {material_id} tidak ditemukan.")

    base = uom_core.base_uom_of(mat)
    uom_in = str(body.get("uom") if "uom" in body else (cur.get("uom") or base)).strip().lower() or base
    try:
        factor, source = bom_uom.factor_to_base(mat, uom_in)
    except uom_core.UomError as e:
        raise HTTPException(400, str(e))

    price = float(body.get("price") if "price" in body else cur.get("price") or 0)
    if price < 0:
        raise HTTPException(400, "Harga tidak boleh negatif.")
    moq = float(body.get("moq") if "moq" in body else cur.get("moq") or 0)
    valid_from = (body.get("valid_from") if "valid_from" in body
                  else cur.get("valid_from")) or date.today().isoformat()
    valid_to = body.get("valid_to") if "valid_to" in body else cur.get("valid_to")
    return {
        "supplier_id": supplier_id,
        "material_id": material_id,
        "material_code": mat.get("code") or "",
        "material_name": mat.get("name") or "",
        "material_type": mat.get("type") or "",
        "base_uom": base,
        "uom": uom_in,
        "factor_to_base": round(float(factor), 8),
        "uom_source": source,
        "price": round(price, 4),
        # SUP-3 / INV-UOM-1: selalu simpan harga per satuan dasar
        "price_base": round(price / float(factor), 6) if factor else round(price, 6),
        "currency": str(body.get("currency") or cur.get("currency") or "IDR").upper(),
        "moq": round(moq, 4),
        "moq_base": round(moq * float(factor), 4),
        "lead_time_days": int(float(body.get("lead_time_days")
                                    if "lead_time_days" in body
                                    else cur.get("lead_time_days") or 0) or 0),
        "valid_from": valid_from,
        "valid_to": valid_to or None,
        "is_active": bool(body.get("is_active", cur.get("is_active", True))),
        "notes": str(body.get("notes") if "notes" in body else cur.get("notes") or "").strip(),
        "updated_at": _now(),
    }


@router.get("/suppliers/{supplier_id}/price-list")
async def list_price_list(supplier_id: str, request: Request,
                          material_id: Optional[str] = None,
                          active_only: bool = Query(True)):
    await _require_procurement_read(request)
    db = get_db()
    q: dict = {"supplier_id": supplier_id}
    if material_id:
        q["material_id"] = material_id
    if active_only:
        q["is_active"] = True
    rows = await db.rahaza_supplier_price_lists.find(q, {"_id": 0}).sort("material_code", 1).to_list(500)
    return {"items": serialize_doc(rows)}


@router.post("/suppliers/{supplier_id}/price-list")
async def add_price_list(supplier_id: str, request: Request):
    user = await _require_procurement(request)
    db = get_db()
    if not await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 1}):
        raise HTTPException(404, "Supplier tidak ditemukan.")
    body = await request.json()
    row = await _price_row_from_body(db, supplier_id, body)
    row["id"] = _uid()
    row["created_at"] = _now()
    row["created_by"] = user["id"]
    # Non-aktifkan harga lama untuk kombinasi material+uom yang sama (histori tetap ada)
    await db.rahaza_supplier_price_lists.update_many(
        {"supplier_id": supplier_id, "material_id": row["material_id"],
         "uom": row["uom"], "is_active": True},
        {"$set": {"is_active": False, "superseded_at": _now(), "updated_at": _now()}})
    await db.rahaza_supplier_price_lists.insert_one(dict(row))
    return serialize_doc({k: v for k, v in row.items() if k != "_id"})


@router.put("/suppliers/{supplier_id}/price-list/{row_id}")
async def update_price_list(supplier_id: str, row_id: str, request: Request):
    await _require_procurement(request)
    db = get_db()
    cur = await db.rahaza_supplier_price_lists.find_one(
        {"id": row_id, "supplier_id": supplier_id}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Baris harga tidak ditemukan.")
    body = await request.json()
    row = await _price_row_from_body(db, supplier_id, body, cur)
    await db.rahaza_supplier_price_lists.update_one({"id": row_id}, {"$set": row})
    out = await db.rahaza_supplier_price_lists.find_one({"id": row_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/suppliers/{supplier_id}/price-list/{row_id}")
async def delete_price_list(supplier_id: str, row_id: str, request: Request):
    await _require_procurement(request)
    db = get_db()
    res = await db.rahaza_supplier_price_lists.delete_one(
        {"id": row_id, "supplier_id": supplier_id})
    if not res.deleted_count:
        raise HTTPException(404, "Baris harga tidak ditemukan.")
    return {"ok": True, "deleted": row_id}


@router.get("/price-lookup")
async def price_lookup(request: Request, material_id: str, supplier_id: Optional[str] = None,
                       uom: Optional[str] = None):
    """Harga berlaku untuk material (opsional dibatasi supplier).

    Dipakai FE untuk auto-isi harga saat membuat PR/PO. Mengembalikan daftar
    penawaran terurut dari termurah (per satuan dasar) supaya pembeli bisa
    membandingkan supplier.
    """
    await _require_procurement_read(request)
    db = get_db()
    today = date.today().isoformat()
    q: dict = {"material_id": material_id, "is_active": True,
               "valid_from": {"$lte": today}}
    if supplier_id:
        q["supplier_id"] = supplier_id
    if uom:
        q["uom"] = uom.strip().lower()
    rows = await db.rahaza_supplier_price_lists.find(q, {"_id": 0}).to_list(200)
    rows = [r for r in rows if not r.get("valid_to") or str(r["valid_to"]) >= today]
    sup_ids = list({r["supplier_id"] for r in rows})
    sups = await db.rahaza_suppliers.find({"id": {"$in": sup_ids}},
                                          {"_id": 0, "id": 1, "code": 1, "name": 1,
                                           "payment_terms": 1, "lead_time_days": 1}).to_list(200)
    smap = {s["id"]: s for s in sups}
    for r in rows:
        s = smap.get(r["supplier_id"]) or {}
        r["supplier_code"] = s.get("code")
        r["supplier_name"] = s.get("name")
        r["supplier_payment_terms"] = s.get("payment_terms")
    rows.sort(key=lambda r: float(r.get("price_base") or 0))
    return {"items": serialize_doc(rows), "best": serialize_doc(rows[0]) if rows else None}


# ─────────────────────────────────────────────────────────────────────────────
# MIGRASI: nama teks-bebas → master supplier + backfill supplier_id (SUP-4)
# ─────────────────────────────────────────────────────────────────────────────
async def _collect_legacy_names(db) -> dict:
    """Kumpulkan nama supplier teks-bebas dari SEMUA koleksi terkait.

    Menjawab keluhan "tidak lengkap dalam mengambil collection datanya":
    sumbernya bukan satu koleksi, tetapi 4 (PO, inspeksi GRN, dokumen
    penerimaan gudang, dan PR aksesoris).
    """
    sources = [
        ("rahaza_purchase_orders", "vendor_name"),
        ("rahaza_grn_inspections", "supplier_name"),
        ("warehouse_receiving", "supplier_name"),
        # 2026-08-07 — DUA nama koleksi lama di sini TIDAK PERNAH ADA
        # (`dewi_accessories_purchase_requests`, `dewi_acc_purchase_requests`),
        # dan field-nya juga salah (`supplier_name`; yang benar `supplier`).
        # Akibatnya nama supplier yang diketik di Request Pembelian Aksesoris
        # tidak pernah ikut migrasi ke Master Supplier. Nama koleksi & field
        # sekarang diambil dari SSOT core/pr_approval.py.
        (ACC_PR_COLLECTION, ACC_PR_SUPPLIER_FIELD),
        ("rahaza_ap_invoices", "vendor_name"),
    ]
    found: dict = {}
    existing = set(await db.list_collection_names())
    for coll, field in sources:
        if coll not in existing:
            continue
        try:
            names = await db[coll].distinct(field)
        except Exception:
            log.warning("migrasi supplier: gagal distinct %s.%s", coll, field, exc_info=True)
            continue
        for n in names:
            s = str(n or "").strip()
            if not s:
                continue
            k = name_key(s)
            if not k:
                continue
            entry = found.setdefault(k, {"variants": [], "sources": [], "display": s})
            if s not in entry["variants"]:
                entry["variants"].append(s)
            if coll not in entry["sources"]:
                entry["sources"].append(coll)
            # Nama tampilan = varian terpanjang (paling lengkap ejaannya)
            if len(s) > len(entry["display"]):
                entry["display"] = s
    return found


@router.get("/suppliers/migrate/preview")
async def migrate_preview(request: Request):
    """Pratinjau migrasi: nama apa yang akan dibuat / sudah cocok."""
    await _require_procurement(request)
    db = get_db()
    found = await _collect_legacy_names(db)
    existing = {s["name_key"]: s for s in await db.rahaza_suppliers.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1, "name_key": 1}).to_list(5000)}
    to_create, matched = [], []
    for k, v in sorted(found.items()):
        row = {"name_key": k, "name": v["display"], "variants": v["variants"],
               "sources": v["sources"]}
        if k in existing:
            row["supplier_code"] = existing[k]["code"]
            matched.append(row)
        else:
            to_create.append(row)
    return {"to_create": to_create, "already_matched": matched,
            "summary": {"legacy_names": len(found), "to_create": len(to_create),
                        "already_matched": len(matched)}}


@router.post("/suppliers/migrate-from-legacy")
async def migrate_from_legacy(request: Request):
    """Buat master supplier dari nama teks-bebas + backfill `supplier_id`.

    Idempoten: dijalankan berulang tidak membuat duplikat (dedup via `name_key`).
    String asli TIDAK dihapus (SUP-4) — hanya ditambahkan `supplier_id`/`supplier_code`.
    """
    user = await _require_procurement(request)
    db = get_db()
    found = await _collect_legacy_names(db)

    existing = {s["name_key"]: s for s in await db.rahaza_suppliers.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1, "name_key": 1}).to_list(5000)}

    created = []
    for k, v in sorted(found.items()):
        if k in existing:
            continue
        code = await _gen_supplier_code(db, v["display"])
        doc = {
            "id": _uid(),
            "code": code,
            "name": v["display"],
            "name_key": k,
            "npwp": "", "tax_name": "", "tax_type": "ppn",
            "address": "", "city": "", "province": "", "postal_code": "",
            "country": "Indonesia", "phone": "", "email": "", "website": "",
            "payment_terms": "net30", "payment_term_days": 30, "currency": "IDR",
            "contacts": [], "bank_accounts": [], "categories": [], "material_types": [],
            "lead_time_days": 0, "min_order_value": 0.0, "rating_manual": None,
            "is_active": True,
            "notes": ("Dibuat otomatis dari data lama. Ejaan yang ditemukan: "
                      + ", ".join(v["variants"])),
            "source": "migrated",
            "legacy_names": v["variants"],
            "legacy_sources": v["sources"],
            "created_at": _now(),
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "updated_at": _now(),
        }
        await db.rahaza_suppliers.insert_one(dict(doc))
        existing[k] = {"id": doc["id"], "code": code, "name": doc["name"], "name_key": k}
        created.append({"code": code, "name": doc["name"], "variants": v["variants"]})

    # ── Backfill supplier_id ke dokumen lama ────────────────────────────────
    backfill = {}
    targets = [
        ("rahaza_purchase_orders", "vendor_name"),
        ("rahaza_grn_inspections", "supplier_name"),
        ("warehouse_receiving", "supplier_name"),
        # Lihat catatan di `_collect_legacy_names`: nama koleksi & field Request
        # Aksesoris diambil dari SSOT, dulu keduanya salah ⇒ backfill tak jalan.
        (ACC_PR_COLLECTION, ACC_PR_SUPPLIER_FIELD),
        ("rahaza_ap_invoices", "vendor_name"),
    ]
    coll_names = set(await db.list_collection_names())
    for coll, field in targets:
        if coll not in coll_names:
            continue
        n = 0
        cursor = db[coll].find(
            {"$or": [{"supplier_id": {"$exists": False}}, {"supplier_id": None},
                     {"supplier_id": ""}]},
            {"_id": 1, field: 1},
        )
        async for doc in cursor:
            k = name_key(doc.get(field) or "")
            sup = existing.get(k)
            if not sup:
                continue
            await db[coll].update_one(
                {"_id": doc["_id"]},
                {"$set": {"supplier_id": sup["id"], "supplier_code": sup["code"]}})
            n += 1
        backfill[coll] = n

    await log_activity(user["id"], user.get("name", ""), "migrate", "rahaza_suppliers",
                       f"Migrasi master supplier: {len(created)} dibuat, backfill {backfill}")
    return {
        "ok": True,
        "created": created,
        "created_count": len(created),
        "legacy_names_found": len(found),
        "backfilled": backfill,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCORECARD berbasis supplier_id (bukan string)
# ─────────────────────────────────────────────────────────────────────────────
def _grade(rate: float) -> str:
    if rate >= 99:
        return "A+"
    if rate >= 97:
        return "A"
    if rate >= 93:
        return "B"
    if rate >= 85:
        return "C"
    return "D"


async def _scorecard_rows(db, period_days: int = 90, supplier_id: str | None = None) -> list:
    since = _now() - timedelta(days=period_days)
    match: dict = {"inspected_at": {"$gte": since}}
    # 2026-08-06 — JANGAN memfilter `supplier_id` di query. Inspeksi LAMA belum
    # punya `supplier_id` dan hanya bisa dikenali lewat `name_key` (itulah inti
    # perbaikan "nama pecah"). Kalau difilter di Mongo, detail satu supplier akan
    # KEHILANGAN riwayat lamanya padahal di daftar riwayat itu ikut terhitung —
    # angka daftar dan angka detail jadi berbeda untuk supplier yang sama.
    insp = await db.rahaza_grn_inspections.find(match, {"_id": 0}).to_list(5000)

    # Kelompokkan berdasarkan supplier_id; dokumen lama tanpa supplier_id
    # dipetakan lewat name_key supaya tidak ada data yang hilang.
    sups = await db.rahaza_suppliers.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1, "name_key": 1,
             "payment_terms": 1, "lead_time_days": 1, "rating_manual": 1}).to_list(5000)
    by_id = {s["id"]: s for s in sups}
    by_key = {s["name_key"]: s for s in sups}

    groups: dict = {}
    for i in insp:
        sid = i.get("supplier_id")
        sup = by_id.get(sid) if sid else None
        if not sup:
            sup = by_key.get(name_key(i.get("supplier_name") or ""))
        key = (sup or {}).get("id") or f"unlinked::{name_key(i.get('supplier_name') or '') or 'tanpa-nama'}"
        g = groups.setdefault(key, {
            "supplier_id": (sup or {}).get("id"),
            "supplier_code": (sup or {}).get("code"),
            "supplier_name": (sup or {}).get("name") or (i.get("supplier_name") or "(tanpa nama)"),
            "linked": bool(sup),
            "payment_terms": (sup or {}).get("payment_terms"),
            "rating_manual": (sup or {}).get("rating_manual"),
            "total_grns": 0, "total_received": 0.0, "total_accepted": 0.0,
            "total_rejected": 0.0, "accepted_count": 0, "partial_count": 0,
            "rejected_count": 0, "last_inspection_at": None,
        })
        g["total_grns"] += 1
        g["total_received"] += float(i.get("total_received_qty") or 0)
        g["total_accepted"] += float(i.get("total_accepted_qty") or 0)
        g["total_rejected"] += float(i.get("total_rejected_qty") or 0)
        res = i.get("overall_result")
        if res == "accepted":
            g["accepted_count"] += 1
        elif res == "partial":
            g["partial_count"] += 1
        elif res == "rejected":
            g["rejected_count"] += 1
        ts = i.get("inspected_at")
        if ts and (not g["last_inspection_at"] or str(ts) > str(g["last_inspection_at"])):
            g["last_inspection_at"] = ts

    # On-time rate dari GR ↔ PO expected_delivery_date
    grs = await db.warehouse_receiving.find(
        {"status": {"$in": ["received", "completed", "partial_received"]}},
        {"_id": 0, "supplier_id": 1, "supplier_name": 1, "po_id": 1, "updated_at": 1,
         "created_at": 1}).to_list(2000)
    po_ids = [g["po_id"] for g in grs if g.get("po_id")]
    pos = await db.rahaza_purchase_orders.find(
        {"id": {"$in": po_ids}}, {"_id": 0, "id": 1, "expected_delivery_date": 1}).to_list(2000)
    po_due = {p["id"]: p.get("expected_delivery_date") for p in pos}
    ontime: dict = {}
    for gr in grs:
        sid = gr.get("supplier_id") or (by_key.get(name_key(gr.get("supplier_name") or "")) or {}).get("id")
        if not sid:
            continue
        due = po_due.get(gr.get("po_id"))
        if not due:
            continue
        recv_at = gr.get("updated_at") or gr.get("created_at")
        recv_day = str(recv_at)[:10] if recv_at else None
        if not recv_day:
            continue
        t = ontime.setdefault(sid, {"n": 0, "ok": 0})
        t["n"] += 1
        if recv_day <= str(due):
            t["ok"] += 1

    out = []
    for g in groups.values():
        recv = g["total_received"] or 0.0
        acc = g["total_accepted"] or 0.0
        rej = g["total_rejected"] or 0.0
        accept_rate = round((acc / recv * 100) if recv else 0.0, 2)
        ot = ontime.get(g["supplier_id"] or "") or {}
        g.update({
            "total_received": round(recv, 4),
            "total_accepted": round(acc, 4),
            "total_rejected": round(rej, 4),
            "accept_rate": accept_rate,
            "defect_rate": round((rej / recv * 100) if recv else 0.0, 2),
            "on_time_rate": round((ot["ok"] / ot["n"] * 100), 2) if ot.get("n") else None,
            "on_time_samples": ot.get("n", 0),
            "quality_grade": _grade(accept_rate) if recv else "-",
        })
        out.append(g)
    out.sort(key=lambda r: (-(r["total_grns"] or 0), r["supplier_name"] or ""))
    if supplier_id:
        out = [r for r in out if r.get("supplier_id") == supplier_id]
    return out


@router.get("/supplier-scorecard")
async def supplier_scorecard(request: Request, period_days: int = Query(90, ge=7, le=730)):
    """Penilaian supplier — DIKELOMPOKKAN berdasarkan `supplier_id` (SSOT).

    Dokumen inspeksi lama yang belum punya `supplier_id` tetap dihitung: dipetakan
    lewat `name_key` sehingga "PT. Benang Jaya" & "PT Benang Jaya" menjadi SATU.
    """
    await _require_procurement_read(request)
    db = get_db()
    rows = await _scorecard_rows(db, period_days)
    linked = [r for r in rows if r["linked"]]
    return {
        "items": serialize_doc(rows),
        "period_days": period_days,
        "summary": {
            "suppliers": len(rows),
            "linked": len(linked),
            "unlinked": len(rows) - len(linked),
            "avg_accept_rate": round(
                sum(r["accept_rate"] for r in rows) / len(rows), 2) if rows else 0.0,
            "total_grns": sum(r["total_grns"] for r in rows),
        },
    }


async def _supplier_inspections(db, sup: dict, period_days: int) -> list:
    """Semua inspeksi QC milik satu supplier — via `supplier_id` ATAU ejaan nama lama.

    2026-08-06 — inti perbaikan "nama pecah" (user story 5). Riwayat lama yang
    hanya menyimpan `supplier_name` (mis. "PT. Benang Jaya" vs "PT Benang Jaya")
    HARUS ikut terhitung; kalau tidak, detail supplier menampilkan angka lebih
    kecil daripada daftar penilaian dan pengguna kehilangan kepercayaan pada data.
    """
    since = _now() - timedelta(days=period_days)
    key = sup.get("name_key") or name_key(sup.get("name") or "")
    rows = await db.rahaza_grn_inspections.find(
        {"inspected_at": {"$gte": since}}, {"_id": 0}).sort("inspected_at", -1).to_list(5000)
    out = []
    for i in rows:
        if i.get("supplier_id") == sup["id"]:
            out.append(i)
        elif not i.get("supplier_id") and name_key(i.get("supplier_name") or "") == key:
            out.append(i)
    return out


@router.get("/suppliers/{supplier_id}/scorecard")
async def one_supplier_scorecard(supplier_id: str, request: Request,
                                 period_days: int = Query(180, ge=7, le=730)):
    """Detail penilaian satu supplier: ringkasan, tren bulanan, alasan reject,
    inspeksi terbaru, dan rekap PO per status — semuanya berbasis Master Supplier."""
    await _require_procurement_read(request)
    db = get_db()
    sup = await db.rahaza_suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(404, "Supplier tidak ditemukan.")
    rows = await _scorecard_rows(db, period_days, supplier_id)
    card = rows[0] if rows else {
        "supplier_id": supplier_id, "supplier_code": sup.get("code"),
        "supplier_name": sup.get("name"), "linked": True, "total_grns": 0,
        "total_received": 0.0, "total_accepted": 0.0, "total_rejected": 0.0,
        "accept_rate": 0.0, "defect_rate": 0.0, "on_time_rate": None,
        "on_time_samples": 0, "quality_grade": "-",
    }
    po_agg = await db.rahaza_purchase_orders.aggregate([
        {"$match": {"supplier_id": supplier_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1},
                    "value": {"$sum": "$total_value"}}},
    ]).to_list(20)

    # ── Detail kualitas (tren bulanan / alasan reject / inspeksi terbaru) ──────
    # Import lazy: katalog alasan reject & normalisasi bentuk lama tinggal di
    # modul QC (SSOT-nya di sana) — tidak diduplikasi di sini.
    from utils.reject_reasons import normalize_reject_reasons
    from routes.rahaza_grn_qc import REJECT_CATEGORIES

    insps = await _supplier_inspections(db, sup, period_days)
    by_month: dict = {}
    reason_qty: dict = {}
    for i in insps:
        dt = i.get("inspected_at")
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                dt = None
        if dt:
            k = dt.strftime("%Y-%m")
            m = by_month.setdefault(k, {"month": k, "grns": 0, "received": 0.0,
                                        "accepted": 0.0, "rejected": 0.0})
            m["grns"] += 1
            m["received"] += float(i.get("total_received_qty") or 0)
            m["accepted"] += float(i.get("total_accepted_qty") or 0)
            m["rejected"] += float(i.get("total_rejected_qty") or 0)
        for line in (i.get("items") or []):
            if not isinstance(line, dict):
                continue
            for rr in normalize_reject_reasons(line.get("reject_reasons"),
                                               default_qty=float(line.get("rejected_qty") or 0)):
                code = rr.get("code") or "OTHER"
                reason_qty[code] = reason_qty.get(code, 0.0) + float(rr.get("qty") or 0)

    monthly_trend = sorted(by_month.values(), key=lambda m: m["month"])
    for m in monthly_trend:
        m["accept_rate"] = round((m["accepted"] / m["received"] * 100), 2) if m["received"] else 0.0
        for f in ("received", "accepted", "rejected"):
            m[f] = round(m[f], 2)
    cat_map = {c["code"]: c for c in REJECT_CATEGORIES}
    top_reject_reasons = [{
        "code": code,
        "label": (cat_map.get(code) or {}).get("label", code),
        "severity": (cat_map.get(code) or {}).get("severity", "minor"),
        "total_qty": round(qty, 2),
    } for code, qty in sorted(reason_qty.items(), key=lambda x: -x[1])[:5] if qty > 0]

    recent = [{
        "id": i.get("id"),
        "inspection_no": i.get("inspection_no"),
        "receipt_number": i.get("receipt_number"),
        "overall_result": i.get("overall_result") or "-",
        "defect_rate": round(
            (float(i.get("total_rejected_qty") or 0) / float(i["total_received_qty"]) * 100), 2)
        if float(i.get("total_received_qty") or 0) else 0.0,
        "inspected_at": i.get("inspected_at"),
        "supplier_name_recorded": i.get("supplier_name"),
        "legacy_unlinked": not i.get("supplier_id"),
    } for i in insps[:12]]

    return serialize_doc({
        "supplier": sup,
        "scorecard": card,
        "po_by_status": {a["_id"]: {"count": a["n"], "value": round(a.get("value") or 0, 2)}
                         for a in po_agg},
        "period_days": period_days,
        "monthly_trend": monthly_trend,
        "top_reject_reasons": top_reject_reasons,
        "recent_inspections": recent,
        "name_variants_merged": sorted({
            (i.get("supplier_name") or "").strip() for i in insps if i.get("supplier_name")
        }),
    })
