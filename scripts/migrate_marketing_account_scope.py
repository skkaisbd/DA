#!/usr/bin/env python3
"""
MIGRASI F14 — memberi lingkup toko (`account_id`) pada data marketing lama.

APA YANG DIPERBAIKI
-------------------
Audit 2026-08-11 mengukur: 60/60 order, 25/25 iklan, 18/18 sesi live, 35/35 sample,
30/30 kalender konten, 10/10 diskon, 8/8 peluncuran **tidak punya `account_id`**.
Baris tanpa lingkup toko tidak akan pernah muncul di layar yang difilter per akun
dan tidak akan pernah ikut dijumlahkan pada laporan per toko — tanpa error, hanya
angka yang lebih kecil dari kenyataan.

TIGA JALAN, DIPILIH PER DOKUMEN (dan SELALU dilaporkan)
-------------------------------------------------------
1. **Dipetakan dari nama.** Dokumen punya `account_name`/`account_code` yang cocok
   ke master akun ⇒ `account_id` diisi, `account_name`/`platform` diselaraskan ke
   master (supaya dua ejaan satu toko tidak lahir lagi).
2. **Akun baru dibuat dari nama yang belum ada di master.** File lama membawa nama
   toko yang memang dipakai perusahaan tetapi belum pernah didaftarkan. Membuang
   barisnya berarti menghilangkan penjualan; karena itu akunnya DIBUAT, ditandai
   `created_by='migrate-f14'`, dan dicantumkan di laporan agar bisa dirapikan.
3. **Baris demo tanpa nama toko dihapus.** Iklan/sesi live/sample demo lama tidak
   membawa nama toko sama sekali, jadi tidak ada yang bisa dipetakan. Baris itu
   lahir dari `seed_*_if_empty` (penanda: `created_by` ∈ {system, seed} atau
   `_import_session_id='seed-demo'`) dan seed-nya SUDAH diperbaiki, sehingga
   menghapusnya membuat data demo dibuat ulang dengan lingkup toko yang benar.
   **Dokumen yang BUKAN dari seed tidak pernah dihapus** — dilaporkan sebagai
   "perlu ditetapkan manual" supaya tidak ada data pengguna yang hilang diam-diam.

Pakai:
  python3 scripts/migrate_marketing_account_scope.py             # dry-run (default)
  python3 scripts/migrate_marketing_account_scope.py --execute
  python3 scripts/migrate_marketing_account_scope.py --execute --no-create-accounts
  python3 scripts/migrate_marketing_account_scope.py --execute --keep-demo
"""
import os
import re
import sys
import uuid
import asyncio
import argparse
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv                             # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient          # noqa: E402

load_dotenv("/app/backend/.env")

ACCOUNTS = "marketing_platform_accounts"
COLLS = [
    "marketing_orders", "marketing_sales_data", "marketing_ads_data",
    "marketing_live_sessions", "marketing_samples",
    "marketing_content_calendar", "marketing_discounts",
    "marketing_product_launches", "marketing_reviews", "marketing_returns",
    "marketing_complaints", "marketing_account_health", "marketing_tasks",
    "marketing_livehost_shifts", "marketing_catalogs",
]
SEED_MARKERS = {"system", "seed", "system-auto", "migrate-f14"}
# Koleksi yang SEBELUM F14 tidak punya satu pun endpoint tulis (dibuktikan audit
# 2026-08-11: `marketing_ads_routes.py` & `marketing_live_sessions_routes.py`
# hanya punya GET). Dokumen di sini yang tidak punya `created_by` PASTI lahir dari
# `seed_*_if_empty` — bukan tebakan, tapi kesimpulan dari tidak adanya penulis lain.
SEED_ONLY_BEFORE_F14 = {"marketing_ads_data", "marketing_live_sessions"}


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").strip().lower())


def now():
    return datetime.now(timezone.utc)


async def build_index(db):
    docs = await db[ACCOUNTS].find({}, {"_id": 0}).to_list(1000)
    by_name, by_code = {}, {}
    for d in docs:
        if not d.get("id"):
            continue
        if norm(d.get("account_name")):
            by_name.setdefault(norm(d["account_name"]), d)
        if norm(d.get("name")):
            by_name.setdefault(norm(d["name"]), d)
        if norm(d.get("account_code")):
            by_code.setdefault(norm(d["account_code"]), d)
    return docs, by_name, by_code


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="benar-benar menulis (default: hanya melaporkan)")
    ap.add_argument("--no-create-accounts", action="store_true",
                    help="jangan membuat akun baru dari nama yang belum terdaftar")
    ap.add_argument("--keep-demo", action="store_true",
                    help="jangan menghapus baris demo tanpa nama toko")
    args = ap.parse_args()
    WRITE = args.execute

    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ.get("DB_NAME", "test_database")]

    print("=" * 84)
    print("MIGRASI F14 — lingkup toko data marketing   "
          + ("[EXECUTE]" if WRITE else "[DRY-RUN — tidak ada yang ditulis]"))
    print("=" * 84)

    accounts, by_name, by_code = await build_index(db)
    valid_ids = {a["id"] for a in accounts if a.get("id")}
    print(f"\nmaster akun saat ini: {len(accounts)}")
    for a in accounts:
        print(f"  · {a.get('account_code','?'):<16} {a.get('account_name') or a.get('name','?'):<34} "
              f"{a.get('platform','?')}")

    created_accounts, total = [], {"mapped": 0, "created": 0, "deleted": 0,
                                   "manual": 0, "already": 0, "orphan_fixed": 0}
    manual_rows = []

    for coll in COLLS:
        if coll not in await db.list_collection_names():
            continue
        n = await db[coll].count_documents({})
        if n == 0:
            continue
        bad = await db[coll].find(
            {"$or": [{"account_id": {"$exists": False}}, {"account_id": None},
                     {"account_id": ""},
                     {"account_id": {"$nin": list(valid_ids)}}]}
        ).to_list(100000)
        if not bad:
            print(f"\n{coll}: {n} dokumen — sudah berlingkup toko semuanya ✓")
            total["already"] += n
            continue

        mapped = created = deleted = manual = orphan = 0
        for d in bad:
            was_orphan = bool(d.get("account_id"))
            name = d.get("account_name") or d.get("name") or ""
            code = d.get("account_code") or ""
            acc = by_code.get(norm(code)) or by_name.get(norm(name))

            if acc is None and name and not args.no_create_accounts:
                # nama toko dipakai data tapi belum terdaftar → daftarkan
                plat = (d.get("platform") or "shopee").lower()
                acc = {
                    "id": str(uuid.uuid4()),
                    "account_code": (re.sub(r"[^A-Z0-9]+", "-", name.upper())[:24]
                                     or f"MIG-{uuid.uuid4().hex[:6].upper()}"),
                    "account_name": name,
                    "platform": plat,
                    "username": norm(name)[:24],
                    "status": "active",
                    "group": "official_store",
                    "credentials": {"has_api_integration": False},
                    "import_config": {"saved_templates": []},
                    "assigned_staff": [],
                    "health_score": 0,
                    "created_at": now(),
                    "updated_at": now(),
                    "created_by": "migrate-f14",
                    "migration_note": (f"dibuat dari nama toko yang ditemukan di "
                                       f"{coll}; periksa & rapikan bila perlu"),
                }
                if WRITE:
                    await db[ACCOUNTS].insert_one(dict(acc))
                by_name[norm(name)] = acc
                valid_ids.add(acc["id"])
                created_accounts.append((acc["account_name"], acc["platform"], coll))
                created += 1

            if acc is not None:
                upd = {"account_id": acc["id"],
                       "account_name": acc.get("account_name") or acc.get("name", ""),
                       "_scope_migrated_at": now()}
                if acc.get("platform"):
                    upd["platform"] = acc["platform"]
                if WRITE:
                    await db[coll].update_one({"_id": d["_id"]}, {"$set": upd})
                mapped += 1
                if was_orphan:
                    orphan += 1
                continue

            # tak ada nama toko yang bisa dipetakan
            is_seed = (d.get("_seed_origin") is True
                       or str(d.get("created_by", "")).lower() in SEED_MARKERS
                       or d.get("_import_session_id") == "seed-demo"
                       or (coll in SEED_ONLY_BEFORE_F14 and not d.get("created_by")
                           and not d.get("_import_session_id")))
            if is_seed and not args.keep_demo:
                if WRITE:
                    await db[coll].delete_one({"_id": d["_id"]})
                deleted += 1
            else:
                manual += 1
                if len(manual_rows) < 40:
                    manual_rows.append((coll, str(d.get("id")),
                                        d.get("created_by", "?")))

        total["mapped"] += mapped
        total["created"] += created
        total["deleted"] += deleted
        total["manual"] += manual
        total["orphan_fixed"] += orphan
        print(f"\n{coll}: {n} dokumen, {len(bad)} tanpa lingkup/yatim")
        print(f"   dipetakan dari nama : {mapped}"
              + (f"  (termasuk {orphan} yang account_id-nya yatim)" if orphan else ""))
        print(f"   akun baru dibuat    : {created}")
        print(f"   baris demo dihapus  : {deleted}"
              + ("  (seed sudah diperbaiki; data demo akan dibuat ulang)" if deleted else ""))
        print(f"   perlu manual        : {manual}")

    print("\n" + "=" * 84)
    print("RINGKAS")
    print(f"  dipetakan          : {total['mapped']}")
    print(f"  account_id yatim   : {total['orphan_fixed']} diperbaiki")
    print(f"  akun baru dibuat   : {total['created']}")
    print(f"  baris demo dihapus : {total['deleted']}")
    print(f"  perlu manual       : {total['manual']}")
    if created_accounts:
        print("\nAKUN BARU (dari nama yang ditemukan di data — periksa sekali):")
        for name, plat, src in created_accounts:
            print(f"  + {name}  [{plat}]  (ditemukan di {src})")
    if manual_rows:
        print("\nPERLU DITETAPKAN MANUAL (tidak dihapus, tidak ditebak):")
        for coll, did, by in manual_rows:
            print(f"  ? {coll}  id={did}  dibuat_oleh={by}")
    if not WRITE:
        print("\nIni DRY-RUN. Jalankan ulang dengan --execute untuk menerapkan.")
    print("=" * 84)
    cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
