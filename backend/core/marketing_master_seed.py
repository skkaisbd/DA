"""core.marketing_master_seed — data master demo Marketing yang BERLINGKUP TOKO.

KENAPA BERKAS INI ADA
---------------------
Portal Marketing punya tiga master yang menjadi tumpuan hampir semua layar:
akun toko, **host live**, dan **kreator/KOL**. Sebelum F14, dua yang terakhir
**kosong sama sekali** pada environment hasil bootstrap, padahal data demo untuk
sesi live dan pengiriman sample sudah ada 18 + 35 baris. Akibatnya:

* sesi live demo menyimpan `host_name` sebagai TEKS karangan ("Bella Fashion")
  yang tidak menunjuk siapa pun ⇒ jam kerja & bayaran host mustahil dihitung;
* sample demo memakai `username` karangan ("@ayufashion") ⇒ performa kreator
  mustahil dihitung, dan biaya sample tidak bisa dibebankan ke siapa pun;
* pemilih "host" dan "kreator" di layar tampak KOSONG, sehingga staf yang mencoba
  fitur pertama kali menyimpulkan fiturnya rusak.

Karena itu master host & kreator dibuat lebih dulu (idempoten), **selalu dengan
`assigned_account_ids` yang sah**, supaya seed transaksi bisa menautkan ke orang
yang benar-benar ada dan aturan "host/kreator harus sudah di-assign ke toko"
(`core.marketing_account_scope.assert_host_assigned`) tidak pernah dilanggar oleh
data buatan kita sendiri.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

HOSTS = "marketing_livehosts"
CREATORS = "marketing_kol_creators"

_DEMO_HOSTS = (
    {"name": "Septiyan Krisdiyanti", "email": "septiyan.host@dewiaditya.id",
     "employment_type": "full_time", "hourly_rate": 35000,
     "shift_preferences": ["evening", "night"],
     "product_expertise": ["Gamis", "Khimar"]},
    {"name": "Jofa Ayu Fandiya", "email": "jofa.host@dewiaditya.id",
     "employment_type": "part_time", "hourly_rate": 28000,
     "shift_preferences": ["afternoon", "evening"],
     "product_expertise": ["Tunik", "Rok"]},
    {"name": "Nadia Rahmawati", "email": "nadia.host@dewiaditya.id",
     "employment_type": "part_time", "hourly_rate": 25000,
     "shift_preferences": ["morning", "afternoon"],
     "product_expertise": ["Kerudung", "Mukena"]},
)

_DEMO_CREATORS = (
    {"name": "Dimas Tri", "creator_code": "KOL-001",
     "login_email": "dimas.kol@dewiaditya.id",
     "platforms": {"tiktok": "@dimastri.style", "instagram": "@dimastri"}},
    {"name": "Ayu Fashion", "creator_code": "KOL-002",
     "login_email": "ayu.kol@dewiaditya.id",
     "platforms": {"tiktok": "@ayufashion", "instagram": "@ayu.fashion"}},
    {"name": "Citra Muslimah", "creator_code": "KOL-003",
     "login_email": "citra.kol@dewiaditya.id",
     "platforms": {"tiktok": "@citramuslimah"}},
    {"name": "Farah Busana", "creator_code": "KOL-004",
     "login_email": "farah.kol@dewiaditya.id",
     "platforms": {"instagram": "@farahbusana"}},
)

_DEMO_PASSWORD = "Dewi@123"

# Produk demo — SATU sumber untuk katalog, order, retur, ulasan, dan sample.
# Sebelum F14 setiap seed punya daftar produknya sendiri, sehingga
# `marketing_orders.sku_id` menunjuk SKU yang tidak ada di katalog mana pun
# (audit: 60/60 yatim) dan alokasi stok dari order mustahil dikerjakan otomatis.
DEMO_PRODUCTS = (
    {"sku": "DA-GMB-001", "name": "Gamis Busui Friendly DA-001",
     "category": "Gamis", "harga_jual": 98000, "harga_coret": 135000,
     "hpp": 61000, "stock": 120, "sizes": ["M", "L", "XL", "XXL"],
     "colors": ["Navy", "Sage", "Black"]},
    {"sku": "DA-CKW-005", "name": "Celana Kulot Wanita DA-005",
     "category": "Celana", "harga_jual": 75000, "harga_coret": 99000,
     "hpp": 46000, "stock": 85, "sizes": ["S", "M", "L", "XL"],
     "colors": ["Hitam", "Cokelat"]},
    {"sku": "DA-KSE-010", "name": "Kerudung Segiempat DA-010",
     "category": "Kerudung", "harga_jual": 45000, "harga_coret": 60000,
     "hpp": 24000, "stock": 240, "sizes": ["All Size"],
     "colors": ["Putih", "Hitam", "Abu", "Cream"]},
    {"sku": "DA-BBM-020", "name": "Blouse Batik Modern DA-020",
     "category": "Blouse", "harga_jual": 110000, "harga_coret": 145000,
     "hpp": 68000, "stock": 60, "sizes": ["S", "M", "L", "XL"],
     "colors": ["Biru", "Merah"]},
    {"sku": "DL-RPP-010", "name": "Rok Plisket Premium DL-010",
     "category": "Rok", "harga_jual": 85000, "harga_coret": 110000,
     "hpp": 52000, "stock": 95, "sizes": ["S", "M", "L", "XL"],
     "colors": ["Black", "Navy"]},
    {"sku": "DL-GMS-001", "name": "Gamis Syari Daluna DL-001",
     "category": "Gamis", "harga_jual": 125000, "harga_coret": 165000,
     "hpp": 78000, "stock": 70, "sizes": ["M", "L", "XL", "XXL"],
     "colors": ["Dusty Pink", "Cream", "Sage", "Navy"]},
)


def _now():
    return datetime.now(timezone.utc)


async def ensure_demo_hosts(db) -> List[dict]:
    """Master host live: dibuat sekali, selalu ter-assign ke akun yang ada."""
    from auth import hash_password
    from core.marketing_account_scope import ensure_demo_accounts

    existing = await db[HOSTS].find({}, {"_id": 0}).to_list(500)
    if existing:
        return existing

    accounts = await ensure_demo_accounts(db)
    acc_ids = [a["id"] for a in accounts]
    docs = []
    for i, h in enumerate(_DEMO_HOSTS):
        # dibagi supaya tidak semua host di semua toko — assignment yang
        # "semua ke semua" membuat aturan assignment tidak pernah teruji.
        assigned = acc_ids if i == 0 else [acc_ids[i % len(acc_ids)]]
        docs.append({
            "id": str(uuid.uuid4()),
            **h,
            "email": h["email"].lower(),
            "password_hash": hash_password(_DEMO_PASSWORD),
            "phone": "",
            "language_skills": ["id"],
            "assigned_account_ids": assigned,
            "status": "active",
            "notes": "",
            "training_completed": [],
            "certification_expiry": {},
            "_seed_origin": True,
            "created_at": _now(),
            "created_by": "system",
            "last_login_at": None,
        })
    await db[HOSTS].insert_many(docs)
    logger.info("[marketing-master] %d host live demo dibuat (ter-assign ke akun)",
                len(docs))
    return [{k: v for k, v in d.items() if k != "_id"} for d in docs]


async def ensure_demo_creators(db) -> List[dict]:
    """Master kreator/KOL: dibuat sekali, selalu ter-assign ke akun yang ada."""
    from auth import hash_password
    from core.marketing_account_scope import ensure_demo_accounts

    existing = await db[CREATORS].find({}, {"_id": 0}).to_list(500)
    if existing:
        # SESI #34 — PERBAIKAN DATA LAMA: kreator demo yang lahir dari penyemai
        # versi lama TIDAK punya `login_email`/`login_password_hash`, sehingga
        # Portal Kreator mustahil dimasuki dan tidak ada layar yang bisa
        # memperbaikinya. Di sini kredensialnya dilengkapi (email diturunkan dari
        # kode kreator) supaya "akun demo tidak bisa login" berhenti terjadi.
        for c in existing:
            if c.get("login_email") and c.get("login_password_hash"):
                continue
            code = (c.get("creator_code") or c.get("id") or "kreator").lower().replace(" ", "-")
            email = (c.get("login_email") or f"{code}@creator.demo").lower()
            await db[CREATORS].update_one({"id": c["id"]}, {"$set": {
                "login_email": email,
                "login_password_hash": hash_password(_DEMO_PASSWORD),
                "portal_account_ready": True,
                "creator_type": c.get("creator_type") or "continue",
                "domicile": c.get("domicile") or "",
                "updated_at": _now(),
            }})
            c["login_email"] = email
            c["portal_account_ready"] = True
        return existing

    accounts = await ensure_demo_accounts(db)
    acc_ids = [a["id"] for a in accounts]
    docs = []
    for i, c in enumerate(_DEMO_CREATORS):
        assigned = acc_ids if i == 0 else [acc_ids[i % len(acc_ids)]]
        docs.append({
            "id": str(uuid.uuid4()),
            "creator_code": c["creator_code"],
            "name": c["name"],
            "login_email": c["login_email"].lower(),
            "login_password_hash": hash_password(_DEMO_PASSWORD),
            "phone": "",
            "platforms": c["platforms"],
            "assigned_account_ids": assigned,
            "kpi_targets": {"monthly_revenue": 25_000_000, "monthly_sessions": 8,
                            "monthly_viewers": 20_000},
            "notes": "",
            "status": "active",
            "last_login_at": None,
            "_seed_origin": True,
            "created_at": _now(),
            "created_by": "system",
            "updated_at": _now(),
        })
    await db[CREATORS].insert_many(docs)
    logger.info("[marketing-master] %d kreator demo dibuat (ter-assign ke akun)",
                len(docs))
    return [{k: v for k, v in d.items() if k != "_id"} for d in docs]


CATALOGS = "marketing_catalogs"
CATALOG_ITEMS = "marketing_catalog_items"


def _stock_status(qty: float, threshold: float) -> str:
    if qty <= 0:
        return "out_of_stock"
    return "low_stock" if qty <= threshold else "in_stock"


async def ensure_demo_catalogs(db) -> List[dict]:
    """Katalog toko demo + itemnya, SATU katalog per akun.

    Kenapa perlu: tanpa katalog, `marketing_orders.sku_id` menunjuk SKU yang tidak
    ada di mana pun (audit: 60/60 yatim) sehingga `catalog_item_id` selalu kosong
    dan Fulfillment WAJIB memilih barang dengan tangan untuk setiap pesanan —
    tepat cacat M9/K-8a yang sudah pernah diperbaiki untuk order manual, tapi
    dibiarkan hidup lewat data demo.

    Harga ditulis memakai field KANONIK F1–F9 (`harga_jual`/`harga_coret`/
    `harga_original`/`hpp`) sekaligus cermin legacy (`price`/`original_price`)
    supaya pembaca lama tidak rusak.
    """
    from core.marketing_account_scope import ensure_demo_accounts

    existing = await db[CATALOGS].find({}, {"_id": 0}).to_list(200)
    if existing:
        return existing

    accounts = await ensure_demo_accounts(db)
    catalogs, items = [], []
    for acc in accounts:
        cid = str(uuid.uuid4())
        catalogs.append({
            "id": cid,
            "account_id": acc["id"],
            "account_name": acc.get("account_name", ""),
            "platform": acc.get("platform", ""),
            "name": f"Katalog {acc.get('account_name', 'Toko')}",
            "description": "Katalog produk fashion muslimah CV. Dewi Aditya",
            "is_active": True,
            "item_count": len(DEMO_PRODUCTS),
            "total_stock": float(sum(p["stock"] for p in DEMO_PRODUCTS)),
            "low_stock_count": 0,
            "out_of_stock_count": 0,
            "_seed_origin": True,
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": "system",
        })
        for p in DEMO_PRODUCTS:
            qty = float(p["stock"])
            thr = 15.0
            items.append({
                "id": str(uuid.uuid4()),
                "catalog_id": cid,
                "account_id": acc["id"],
                "platform": acc.get("platform", ""),
                "sku": p["sku"],
                "name": p["name"],
                "description": "",
                "category": p["category"],
                "category_id": None,
                # ── harga kanonik (F1–F9) + cermin legacy ─────────────────────
                "harga_jual": float(p["harga_jual"]),
                "harga_coret": float(p["harga_coret"]),
                "harga_original": float(p["harga_coret"]),
                "hpp": float(p["hpp"]),
                "price": float(p["harga_jual"]),
                "original_price": float(p["harga_coret"]),
                "platform_price": float(p["harga_jual"]),
                "stock_quantity": qty,
                "stock_alert_threshold": thr,
                "stock_status": _stock_status(qty, thr),
                "material_id": None,
                "model_id": None,
                "variant_id": None,
                "variant_sku": "",
                "fg_material_id": None,
                "source": "seed_demo",
                "platform_url": "",
                "images": [],
                "tags": [],
                "weight_gram": 350.0,
                "variant_info": (f"Warna: {', '.join(p['colors'])} | "
                                 f"Size: {', '.join(p['sizes'])}"),
                "sizes": p["sizes"],
                "colors": p["colors"],
                "is_active": True,
                "last_stock_sync": None,
                "_seed_origin": True,
                "created_at": _now(),
                "updated_at": _now(),
                "created_by": "system",
            })
    await db[CATALOGS].insert_many(catalogs)
    await db[CATALOG_ITEMS].insert_many(items)
    logger.info("[marketing-master] %d katalog + %d item demo dibuat",
                len(catalogs), len(items))
    return [{k: v for k, v in c.items() if k != "_id"} for c in catalogs]


async def catalog_items_for_account(db, account_id: str) -> List[dict]:
    """Item katalog satu akun — dipakai seed transaksi supaya SKU tidak yatim."""
    await ensure_demo_catalogs(db)
    return await db[CATALOG_ITEMS].find(
        {"account_id": account_id},
        {"_id": 0, "id": 1, "sku": 1, "name": 1, "harga_jual": 1, "hpp": 1,
         "category": 1, "sizes": 1, "colors": 1, "catalog_id": 1}).to_list(200)
