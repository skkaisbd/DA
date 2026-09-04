#!/usr/bin/env python3
"""seed_marketing_real_accounts.py — F0.7: master 9 TOKO NYATA + tautan Finance.

KENAPA (D22, terukur 2026-08-12)
--------------------------------
`marketing_platform_accounts` hanya berisi **3 akun DEMO** (\"Shopee Official Store
DEMO\", dst.), sementara bagan akun (`rahaza_coa_accounts`) sudah memuat akun
pendapatan **per toko nyata** (`4-111`…`4-131`) yang **tidak pernah dipakai**.
Akibatnya: seluruh data marketing menempel ke toko demo, dan pencairan
marketplace (F9) tidak punya alamat jurnal.

Skrip ini IDEMPOTEN:
  · toko dikenali dari `account_code`; kalau sudah ada, hanya field yang KOSONG
    yang dilengkapi (tidak pernah menimpa yang sudah diisi manusia);
  · 3 akun DEMO ditandai `status='inactive'` + `is_demo=True` — **tidak dihapus**
    karena dipakai skrip uji;
  · setiap toko diberi `coa_revenue_code` yang benar-benar ADA di COA; kalau
    akunnya tidak ada, toko itu dilaporkan dan DILEWATI (tidak mengarang akun).

Daftar toko diambil dari COA (bukan karangan). Owner WAJIB mengoreksi nama,
username, PIC, dan rekening pencairan sebelum dipakai produksi (BD-5).

Pakai:
    python3 backend/scripts/seed_marketing_real_accounts.py            # dry-run
    python3 backend/scripts/seed_marketing_real_accounts.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

from database import get_db          # noqa: E402

# (account_code, account_name, platform, coa_revenue_code, platform_warehouse_name)
TOKO = [
    ("SHOPEE-GROSIRHIJAB", "Shopee Grosirhijabsragen", "shopee",    "4-111", ""),
    ("SHOPEE-DALUNA",      "Shopee Daluna",            "shopee",    "4-112", ""),
    ("SHOPEE-MOEN",        "Shopee Moen",              "shopee",    "4-113", ""),
    ("TIKTOK-DALUNA",      "TikTok Daluna",            "tiktokshop", "4-121", ""),
    ("TIKTOK-OUTFIT",      "TikTok Outfit Boutique",   "tiktokshop", "4-122", "Outfit Boutique"),
    ("TIKTOK-MOEN",        "TikTok Style by Moen",     "tiktokshop", "4-123", ""),
    ("TIKTOK-FATIMAHIJAB", "TikTok Fatimahijab",       "tiktokshop", "4-124", ""),
    ("TIKTOK-DEZZAKIDS",   "TikTok Dezza Kids",        "tiktokshop", "4-125", ""),
    ("TOKPED-DA",          "Tokopedia",                "tokopedia",  "4-131", ""),
]
DEFAULT_CASH = "1-131"        # Bank BCA – DA Official (Online Shop)
DEFAULT_RECV = "1-220"        # Piutang Platform Online Shop
DEFAULT_BASIS = "produk_setelah_diskon"


def _now():
    return datetime.now(timezone.utc)


async def main(apply: bool) -> int:
    db = get_db()
    coa = {c["code"] async for c in db.rahaza_coa_accounts.find({}, {"_id": 0, "code": 1})}
    print("=" * 78)
    print(f"F0.7 master toko nyata — mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 78)
    for code in (DEFAULT_CASH, DEFAULT_RECV):
        print(f"  akun default {code:8s} {'ADA di COA' if code in coa else '!! TIDAK ADA di COA'}")

    n_new = n_filled = n_skip = 0
    for acc_code, name, platform, coa_rev, wh in TOKO:
        if coa_rev not in coa:
            print(f"  {'DILEWATI':>10s}  {name:28s} — COA pendapatan {coa_rev} tidak ada")
            n_skip += 1
            continue
        existing = await db.marketing_platform_accounts.find_one(
            {"account_code": acc_code}, {"_id": 0})
        payload = {
            "account_name": name,
            "platform": platform,
            "coa_revenue_code": coa_rev,
            "coa_cash_code": DEFAULT_CASH if DEFAULT_CASH in coa else "",
            "coa_receivable_code": DEFAULT_RECV if DEFAULT_RECV in coa else "",
            "platform_warehouse_name": wh,
            "revenue_basis": DEFAULT_BASIS,
        }
        if existing:
            patch = {k: v for k, v in payload.items() if not existing.get(k)}
            if patch:
                print(f"  {'LENGKAPI':>10s}  {name:28s} → {sorted(patch)}")
                n_filled += 1
                if apply:
                    patch["updated_at"] = _now()
                    await db.marketing_platform_accounts.update_one(
                        {"id": existing["id"]}, {"$set": patch})
            else:
                print(f"  {'SUDAH OK':>10s}  {name}")
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "account_code": acc_code,
            "username": "",
            "status": "active",
            "group": "official_store",
            "credentials": {"api_key": "", "api_secret": "", "has_api_integration": False},
            "import_config": {"saved_templates": []},
            "assigned_staff": [],
            "pic_id": "",
            "health_score": None,
            "platform_shop_id": "",
            "seeded_by": "F0.7",
            "needs_owner_review": True,   # BD-5: nama/username/PIC/rekening harus dikoreksi
            "created_at": _now(),
            "created_by": "seed-f0.7",
            "updated_at": _now(),
            **payload,
        }
        print(f"  {'BARU':>10s}  {name:28s} COA {coa_rev}"
              + (f" · gudang platform '{wh}'" if wh else ""))
        n_new += 1
        if apply:
            await db.marketing_platform_accounts.insert_one(doc)

    # 3 akun DEMO: dinonaktifkan, TIDAK dihapus
    demo_q = {"account_code": {"$in": ["SHOPEE-OFFICIAL", "SHOPEE-RESELLER", "TIKTOK-STORE"]}}
    n_demo = await db.marketing_platform_accounts.count_documents(demo_q)
    print(f"\n  akun DEMO ditandai nonaktif (tidak dihapus): {n_demo}")
    if apply and n_demo:
        await db.marketing_platform_accounts.update_many(
            demo_q, {"$set": {"status": "inactive", "is_demo": True, "updated_at": _now()}})

    # Akun COA piutang PER TOKO (subledger anak `1-220`). Jalur API membuatnya
    # otomatis; skrip seed menulis langsung ke DB sehingga harus memanggilnya
    # sendiri — kalau tidak, toko nyata tidak punya akun buku besar sendiri dan
    # pencairan marketplace (F9) tak punya alamat jurnal per toko. IDEMPOTEN.
    if apply:
        from routes.coa_auto import ensure_subledger_for_entity  # noqa: PLC0415
        n_sub = 0
        for acc in await db.marketing_platform_accounts.find({}, {"_id": 0}).to_list(1000):
            if acc.get("ar_account_code"):
                continue
            res = await ensure_subledger_for_entity(
                db, "channel", acc, {"id": "system", "name": "seed-f0.7"})
            if res.get("ok"):
                n_sub += 1
                print(f"  {'COA':>10s}  {acc.get('account_name','?')[:28]:28s} → {res.get('code')}")
            else:
                print(f"  {'COA GAGAL':>10s}  {acc.get('account_name','?')[:28]:28s} → "
                      f"{res.get('error') or res.get('reason')}")
        print(f"\n  akun COA piutang toko dibuat/dilengkapi: {n_sub}")

    total = await db.marketing_platform_accounts.count_documents({})
    aktif = await db.marketing_platform_accounts.count_documents({"status": "active"})
    print(f"\n  ringkas: baru={n_new} dilengkapi={n_filled} dilewati={n_skip}")
    print(f"  total akun di DB: {total} (aktif: {aktif})")
    if not apply:
        print("\n  DRY-RUN: tidak ada yang diubah. Jalankan ulang dengan --apply.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    os.chdir("/app/backend")
    raise SystemExit(asyncio.run(main(a.apply)))
