"""QA iter112 helper: snapshot / verify DB counts for finance collections."""
import asyncio
import os
import sys
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or env.get("DB_NAME")


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    out = {}
    out["journal_entries"] = await db.rahaza_journal_entries.count_documents({})
    out["journal_lines"] = await db.rahaza_journal_lines.count_documents({})
    out["je_by_module"] = await db.rahaza_journal_entries.aggregate([
        {"$group": {"_id": {"m": "$source_module", "s": "$status"}, "n": {"$sum": 1}}}]).to_list(100)
    out["je_by_module"] = sorted([f"{r['_id'].get('m')}/{r['_id'].get('s')}={r['n']}" for r in out["je_by_module"]])
    out["bank_recon_sessions"] = await db.bank_recon_sessions.count_documents({})
    out["bank_recon_txns"] = await db.bank_recon_txns.count_documents({})
    out["bank_recon_matches"] = await db.bank_recon_matches.count_documents({})
    out["cash_accounts"] = await db.rahaza_cash_accounts.count_documents({})
    out["cash_movements"] = await db.rahaza_cash_movements.count_documents({})
    out["adjustments"] = await db.rahaza_bank_recon_adjustments.count_documents({})
    out["coa_1_1200_sub"] = await db.rahaza_coa_accounts.count_documents({"code": {"$regex": "^1-1200-"}})
    out["coa_total"] = await db.rahaza_coa_accounts.count_documents({})
    # orphan mirror lines
    je_ids = set(await db.rahaza_journal_entries.distinct("id"))
    orphans = []
    async for ln in db.rahaza_journal_lines.find({}, {"_id": 0, "je_id": 1, "id": 1}):
        if ln.get("je_id") not in je_ids:
            orphans.append(ln.get("je_id"))
    out["orphan_line_je_ids"] = sorted(set(orphans))
    out["orphan_line_count"] = len(orphans)
    print(json.dumps(out, indent=2, default=str))
    client.close()


asyncio.run(main())
sys.exit(0)
