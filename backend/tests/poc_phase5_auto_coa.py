"""
POC Phase 5 — Auto-Create COA Subledger + Posting Integration (CMT Vendor / AP).

Membuktikan (isolated, end-to-end via helper + DB):
  A. ensure_subledger_account IDEMPOTENT (2x panggil → 1 akun) + akun valid
     (parent 2-1100, non-group, active, normal_balance CREDIT) + ap_account_code tersimpan.
  B. Backfill: semua dewi_cmt_partners punya akun subledger.
  C. Posting cmt_ap_invoice MEMAKAI akun AP per-vendor (bukan kontrol 2-1100).
  D. GL: saldo AP per-vendor = nilai payment; kontrol 2-1100 TIDAK kena posting itu.
  E. Fallback: bila setting cmt_vendor.enabled=false & vendor tanpa ap_account_code
     → posting jatuh ke akun kontrol 2-1100.

Run: cd /app/backend && /root/.venv/bin/python3 tests/poc_phase5_auto_coa.py
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from routes.coa_auto import (
    ensure_subledger_for_entity,
    ensure_subledger_account,
    get_auto_settings,
)
from routes.dewi_maklon_finance import post_cmt_ap_invoice

USER = {"id": "poc-tester", "name": "POC Tester"}
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return cond


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "garment_erp")]

    print("\n=== Setup ===")
    # ensure settings enabled for cmt_vendor
    await db.rahaza_coa_auto_settings.delete_many({})  # reset to defaults for clean POC
    settings = await get_auto_settings(db)
    cmt_cfg = settings["entity_types"]["cmt_vendor"]
    check("settings.cmt_vendor.enabled default = true", cmt_cfg.get("enabled") is True)
    check("settings.cmt_vendor.parent_code = 2-1100", cmt_cfg.get("parent_code") == "2-1100")

    # parent account exists
    parent = await db.rahaza_coa_accounts.find_one({"code": "2-1100"}, {"_id": 0})
    check("parent akun 2-1100 (Hutang Usaha) ada", parent is not None,
          (parent or {}).get("name", ""))

    # pick a seeded CMT partner
    partner = await db.dewi_cmt_partners.find_one({}, {"_id": 0})
    if not partner:
        print("  Tidak ada dewi_cmt_partners; buat dummy untuk POC.")
        partner = {"id": str(uuid.uuid4()), "code": "CMT-POC", "name": "CMT POC Vendor", "status": "active"}
        await db.dewi_cmt_partners.insert_one(dict(partner))
    pid = partner["id"]
    print(f"  Partner uji: {partner.get('code')} / {partner.get('name')} ({pid[:8]})")

    print("\n=== Test A — ensure_subledger IDEMPOTENT ===")
    # clean any prior POC account for deterministic run
    await db.rahaza_coa_accounts.delete_many(
        {"flags.subledger_entity_type": "cmt_vendor", "flags.subledger_entity_id": pid}
    )
    await db.dewi_cmt_partners.update_one({"id": pid}, {"$unset": {"ap_account_code": ""}})

    r1 = await ensure_subledger_for_entity(db, "cmt_vendor", partner, USER)
    r2 = await ensure_subledger_for_entity(db, "cmt_vendor", partner, USER)
    check("panggilan #1 ok", r1.get("ok"), r1.get("code", r1.get("error", "")))
    check("panggilan #1 created=True", r1.get("created") is True)
    check("panggilan #2 created=False (idempotent)", r2.get("created") is False)
    check("kode akun sama di 2 panggilan", r1.get("code") == r2.get("code"), r1.get("code"))

    acc_code = r1.get("code")
    acc = await db.rahaza_coa_accounts.find_one({"code": acc_code}, {"_id": 0})
    check("akun subledger ter-create di COA", acc is not None)
    check("parent_code = 2-1100", acc and acc.get("parent_code") == "2-1100")
    check("is_group = False (postable)", acc and acc.get("is_group") is False)
    check("active = True", acc and acc.get("active") is True)
    check("normal_balance = CREDIT (liability)", acc and acc.get("normal_balance") == "CREDIT")
    check("hanya 1 akun untuk entitas ini (no dup)",
          await db.rahaza_coa_accounts.count_documents(
              {"flags.subledger_entity_type": "cmt_vendor", "flags.subledger_entity_id": pid}) == 1)

    partner_refresh = await db.dewi_cmt_partners.find_one({"id": pid}, {"_id": 0})
    check("partner.ap_account_code tersimpan", partner_refresh.get("ap_account_code") == acc_code, acc_code)

    print("\n=== Test B — Backfill semua CMT vendor ===")
    total_partners = await db.dewi_cmt_partners.count_documents({})
    for ent in await db.dewi_cmt_partners.find({}, {"_id": 0}).to_list(1000):
        await ensure_subledger_for_entity(db, "cmt_vendor", ent, USER)
    with_acct = await db.dewi_cmt_partners.count_documents({"ap_account_code": {"$exists": True, "$ne": None}})
    check(f"semua {total_partners} partner punya ap_account_code", with_acct == total_partners,
          f"{with_acct}/{total_partners}")

    print("\n=== Test C — Posting cmt_ap_invoice memakai akun per-vendor ===")
    pay_id = str(uuid.uuid4())
    amount = 750000.0
    payment = {
        "id": pay_id,
        "payment_code": f"POC-PAY-{pay_id[:6]}",
        "payment_number": f"POC-PAY-{pay_id[:6]}",
        "cmt_partner_id": pid,
        "cmt_name": partner.get("name"),
        "subtotal": amount,
        "total_penalty": 0,
        "payment_date": date.today().isoformat(),
        "status": "approved",
        "created_at": datetime.now(timezone.utc),
    }
    await db.dewi_cmt_payments.insert_one(dict(payment))
    post = await post_cmt_ap_invoice(db, payment, USER)
    check("post_cmt_ap_invoice ok", post.get("ok"), post.get("je_number", post.get("error", "")))

    je = await db.rahaza_journal_entries.find_one({"id": post.get("je_id")}, {"_id": 0})
    credit_lines = [l for l in (je or {}).get("lines", []) if float(l.get("credit") or 0) > 0]
    credit_codes = [l["account_code"] for l in credit_lines]
    check("JE punya credit line", len(credit_lines) >= 1, str(credit_codes))
    check("credit line = akun AP per-vendor (subledger)", acc_code in credit_codes,
          f"expected {acc_code}, got {credit_codes}")
    check("credit line BUKAN akun kontrol 2-1100", "2-1100" not in credit_codes)
    check("JE balanced (Dr==Cr)",
          round((je or {}).get("total_debit", 0), 2) == round((je or {}).get("total_credit", 0), 2))

    print("\n=== Test D — GL saldo AP per-vendor ===")
    agg = await db.rahaza_journal_lines.aggregate([
        {"$match": {"account_code": acc_code}},
        {"$group": {"_id": None, "debit": {"$sum": "$debit"}, "credit": {"$sum": "$credit"}}},
    ]).to_list(1)
    bal_credit = (agg[0]["credit"] - agg[0]["debit"]) if agg else 0
    check(f"saldo (credit) akun {acc_code} = {amount}", round(bal_credit, 2) == round(amount, 2),
          f"balance={bal_credit}")

    print("\n=== Test E — Fallback ke kontrol saat fitur OFF ===")
    # disable + vendor tanpa ap_account_code
    await db.rahaza_coa_auto_settings.update_one(
        {"id": "default"}, {"$set": {"entity_types.cmt_vendor.enabled": False}})
    p2_id = str(uuid.uuid4())
    p2 = {"id": p2_id, "code": f"CMT-OFF-{p2_id[:4]}", "name": "CMT Fallback Test", "status": "active"}
    await db.dewi_cmt_partners.insert_one(dict(p2))
    pay2_id = str(uuid.uuid4())
    payment2 = {
        "id": pay2_id, "payment_code": f"POC-OFF-{pay2_id[:6]}", "payment_number": f"POC-OFF-{pay2_id[:6]}",
        "cmt_partner_id": p2_id, "cmt_name": p2["name"], "subtotal": 100000.0, "total_penalty": 0,
        "payment_date": date.today().isoformat(), "status": "approved", "created_at": datetime.now(timezone.utc),
    }
    await db.dewi_cmt_payments.insert_one(dict(payment2))
    post2 = await post_cmt_ap_invoice(db, payment2, USER)
    je2 = await db.rahaza_journal_entries.find_one({"id": post2.get("je_id")}, {"_id": 0})
    credit_codes2 = [l["account_code"] for l in (je2 or {}).get("lines", []) if float(l.get("credit") or 0) > 0]
    check("fallback: credit line = kontrol 2-1100", "2-1100" in credit_codes2, str(credit_codes2))
    check("fallback: vendor OFF tak dapat akun subledger",
          await db.rahaza_coa_accounts.count_documents(
              {"flags.subledger_entity_id": p2_id}) == 0)

    print("\n=== Cleanup (hapus artefak uji) ===")
    # void/remove test JEs + payments + fallback vendor + its (none) account
    for je_doc in [je, je2]:
        if je_doc:
            await db.rahaza_journal_entries.delete_one({"id": je_doc["id"]})
            await db.rahaza_journal_lines.delete_many({"je_id": je_doc["id"]})
    await db.dewi_cmt_payments.delete_many({"id": {"$in": [pay_id, pay2_id]}})
    await db.dewi_cmt_partners.delete_one({"id": p2_id})
    # re-enable setting (leave defaults)
    await db.rahaza_coa_auto_settings.update_one(
        {"id": "default"}, {"$set": {"entity_types.cmt_vendor.enabled": True}})
    print("  cleanup done (akun subledger vendor asli DIPERTAHANKAN — data valid).")

    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r)
    print(f"RESULT: {passed}/{total} checks passed")
    print("=" * 60)
    client.close()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
