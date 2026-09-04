"""
CLI Backfill — Phase 5 Auto-COA Subledger.
Buat akun COA subledger untuk semua entitas dari sebuah entity_type
(default: cmt_vendor). Idempotent.

Usage:
  cd /app/backend && /root/.venv/bin/python3 scripts/backfill_coa_subledger.py [entity_type] [--dry-run]

Contoh:
  ...backfill_coa_subledger.py cmt_vendor           # commit
  ...backfill_coa_subledger.py cmt_vendor --dry-run # pratinjau saja
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from routes.coa_auto import get_auto_settings, ensure_subledger_for_entity

USER = {"id": "cli-backfill", "name": "CLI Backfill"}


async def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    entity_type = next((a for a in args if not a.startswith("--")), "cmt_vendor")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "garment_erp")]

    settings = await get_auto_settings(db)
    cfg = (settings.get("entity_types") or {}).get(entity_type)
    if not cfg:
        print(f"entity_type '{entity_type}' tidak dikenal. Pilihan: {list(settings['entity_types'].keys())}")
        sys.exit(1)
    coll = cfg["collection"]
    print(f"Backfill entity_type={entity_type} collection={coll} parent={cfg['parent_code']} "
          f"(mode={'DRY-RUN' if dry else 'COMMIT'})")

    total = created = already = 0
    async for ent in db[coll].find({}, {"_id": 0}):
        total += 1
        eid = ent.get("id")
        exists = await db.rahaza_coa_accounts.find_one(
            {"flags.subledger_entity_type": entity_type, "flags.subledger_entity_id": eid},
            {"_id": 0, "code": 1})
        if exists:
            already += 1
            continue
        if dry:
            print(f"  akan buat: {ent.get('code') or eid} → (di bawah {cfg['parent_code']})")
        else:
            res = await ensure_subledger_for_entity(db, entity_type, ent, USER)
            if res.get("ok"):
                created += 1
                print(f"  dibuat: {ent.get('code') or eid} → {res.get('code')}")
            else:
                print(f"  GAGAL: {ent.get('code') or eid} → {res.get('error')}")

    print(f"\nSelesai. total={total} sudah_ada={already} {'akan_dibuat' if dry else 'dibuat'}={total - already if dry else created}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
