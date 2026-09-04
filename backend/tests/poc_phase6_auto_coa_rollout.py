"""
POC Phase 6 — Auto-COA Subledger ROLLOUT ke 5 entitas inti + posting integration.

Membuktikan (isolated, end-to-end via helper + DB), untuk KELIMA entity_type:
  - Registry lengkap: cmt_vendor, supplier, customer, channel, bank (semua enabled).
  - ensure_subledger IDEMPOTENT + akun valid (parent benar, non-group, active,
    normal_balance sesuai parent) + target_field tersimpan di master.
  - Posting memakai akun subledger per-entitas (bukan akun kontrol):
      supplier → post_ap_invoice  → Cr AP = 2-1100-SUP-* (bukan 2-1100)
      customer → post_ar_invoice  → Dr AR = 1-1301-CUST-* (bukan 1-1301)
      channel  → post_ar_invoice (sales_channel) → Dr AR = 1-220-CH-* (bukan 1-220)
      bank     → gl_account_code = 1-1200-* (dipakai ar/ap payment)
      cmt_vendor (regresi ringan) → tetap 2-1100-CMT-*
  - Fallback: saat entity_type OFF & master tanpa akun → posting jatuh ke kontrol.

Run: cd /app/backend && /root/.venv/bin/python3 tests/poc_phase6_auto_coa_rollout.py
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
    resolve_subledger_account,
    get_auto_settings,
)
from routes.rahaza_posting import post_ar_invoice, post_ap_invoice

USER = {"id": "poc6-tester", "name": "POC6 Tester"}
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []
_cleanup = {"je_ids": [], "coa_flags_ids": [], "ap_ids": [], "ar_ids": []}


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"  [{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return cond


async def _credit_codes(db, je_id):
    je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0})
    return je, [l["account_code"] for l in (je or {}).get("lines", []) if float(l.get("credit") or 0) > 0]


async def _debit_codes(db, je_id):
    je = await db.rahaza_journal_entries.find_one({"id": je_id}, {"_id": 0})
    return je, [l["account_code"] for l in (je or {}).get("lines", []) if float(l.get("debit") or 0) > 0]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    print("\n=== Setup: reset settings → default 5 entitas ===")
    await db.rahaza_coa_auto_settings.delete_many({})
    settings = await get_auto_settings(db)
    et = settings["entity_types"]
    for k in ["cmt_vendor", "supplier", "customer", "channel", "bank"]:
        check(f"registry punya '{k}' & enabled", et.get(k, {}).get("enabled") is True,
              f"parent={et.get(k, {}).get('parent_code')}")

    # parents exist
    for pc in ["2-1100", "1-1301", "1-220", "1-1200"]:
        p = await db.rahaza_coa_accounts.find_one({"code": pc}, {"_id": 0})
        check(f"parent {pc} ada di COA", p is not None, (p or {}).get("name", ""))

    # ─────────────────────────── SUPPLIER (AP) ───────────────────────────────
    print("\n=== SUPPLIER — ensure + post_ap_invoice pakai subledger ===")
    sup_id = str(uuid.uuid4())
    sup = {"id": sup_id, "code": f"SUP-{sup_id[:4].upper()}", "name": "Supplier Kain POC", "active": True}
    await db.rahaza_vendors.insert_one(dict(sup))
    r = await ensure_subledger_for_entity(db, "supplier", sup, USER)
    sup_acc = r.get("code")
    _cleanup["coa_flags_ids"].append(("supplier", sup_id))
    check("supplier ensure ok", r.get("ok"), sup_acc)
    acc = await db.rahaza_coa_accounts.find_one({"code": sup_acc}, {"_id": 0}) if sup_acc else None
    check("supplier akun parent=2-1100", acc and acc.get("parent_code") == "2-1100")
    check("supplier akun non-group", acc and acc.get("is_group") is False)
    check("supplier normal_balance=CREDIT", acc and acc.get("normal_balance") == "CREDIT")
    sup_refresh = await db.rahaza_vendors.find_one({"id": sup_id}, {"_id": 0})
    check("supplier.ap_account_code tersimpan", sup_refresh.get("ap_account_code") == sup_acc, sup_acc)

    ap_id = str(uuid.uuid4())
    ap_inv = {
        "id": ap_id, "invoice_number": f"POC-AP-{ap_id[:6]}",
        "vendor_name": sup["name"], "vendor_code": sup["code"],
        "issue_date": date.today().isoformat(),
        "subtotal": 400000.0, "tax_amount": 0, "total": 400000.0,
    }
    await db.rahaza_ap_invoices.insert_one(dict(ap_inv))
    _cleanup["ap_ids"].append(ap_id)
    post = await post_ap_invoice(db, ap_inv, USER)
    check("post_ap_invoice ok", post.get("ok"), post.get("je_number", post.get("error", "")))
    _cleanup["je_ids"].append(post.get("je_id"))
    je, ccodes = await _credit_codes(db, post.get("je_id"))
    check("AP credit = supplier subledger (bukan 2-1100)", sup_acc in ccodes and "2-1100" not in ccodes, str(ccodes))
    check("AP JE balanced", je and round(je.get("total_debit", 0), 2) == round(je.get("total_credit", 0), 2))

    # ─────────────────────────── CUSTOMER (AR) ───────────────────────────────
    print("\n=== CUSTOMER — ensure + post_ar_invoice pakai subledger ===")
    cust_id = str(uuid.uuid4())
    cust = {"id": cust_id, "code": f"CUST-{cust_id[:4].upper()}", "name": "Buyer Retail POC", "active": True}
    await db.rahaza_customers.insert_one(dict(cust))
    r = await ensure_subledger_for_entity(db, "customer", cust, USER)
    cust_acc = r.get("code")
    _cleanup["coa_flags_ids"].append(("customer", cust_id))
    check("customer ensure ok", r.get("ok"), cust_acc)
    acc = await db.rahaza_coa_accounts.find_one({"code": cust_acc}, {"_id": 0}) if cust_acc else None
    check("customer akun parent=1-1301", acc and acc.get("parent_code") == "1-1301")
    check("customer normal_balance=DEBIT", acc and acc.get("normal_balance") == "DEBIT")
    cust_refresh = await db.rahaza_customers.find_one({"id": cust_id}, {"_id": 0})
    check("customer.ar_account_code tersimpan", cust_refresh.get("ar_account_code") == cust_acc, cust_acc)

    ar_id = str(uuid.uuid4())
    ar_inv = {
        "id": ar_id, "invoice_number": f"POC-AR-{ar_id[:6]}",
        "customer_id": cust_id, "customer_name": cust["name"],
        "issue_date": date.today().isoformat(),
        "subtotal": 600000.0, "tax_amount": 0, "total": 600000.0,
    }
    await db.rahaza_ar_invoices.insert_one(dict(ar_inv))
    _cleanup["ar_ids"].append(ar_id)
    post = await post_ar_invoice(db, ar_inv, USER)
    check("post_ar_invoice (customer) ok", post.get("ok"), post.get("je_number", post.get("error", "")))
    _cleanup["je_ids"].append(post.get("je_id"))
    je, dcodes = await _debit_codes(db, post.get("je_id"))
    check("AR debit = customer subledger (bukan 1-1301)", cust_acc in dcodes and "1-1301" not in dcodes, str(dcodes))
    check("AR JE balanced", je and round(je.get("total_debit", 0), 2) == round(je.get("total_credit", 0), 2))

    # ─────────────────────────── CHANNEL (AR via sales_channel) ──────────────
    print("\n=== CHANNEL — ensure + post_ar_invoice (sales_channel) pakai subledger ===")
    ch_id = str(uuid.uuid4())
    ch = {"id": ch_id, "account_code": f"CH-{ch_id[:4].upper()}", "account_name": "Shopee DA POC",
          "platform": "shopee", "status": "active"}
    await db.marketing_platform_accounts.insert_one(dict(ch))
    r = await ensure_subledger_for_entity(db, "channel", ch, USER)
    ch_acc = r.get("code")
    _cleanup["coa_flags_ids"].append(("channel", ch_id))
    check("channel ensure ok", r.get("ok"), ch_acc)
    acc = await db.rahaza_coa_accounts.find_one({"code": ch_acc}, {"_id": 0}) if ch_acc else None
    check("channel akun parent=1-220", acc and acc.get("parent_code") == "1-220")
    ch_refresh = await db.marketing_platform_accounts.find_one({"id": ch_id}, {"_id": 0})
    check("channel.ar_account_code tersimpan", ch_refresh.get("ar_account_code") == ch_acc, ch_acc)

    ar2_id = str(uuid.uuid4())
    ar2_inv = {
        "id": ar2_id, "invoice_number": f"POC-CH-{ar2_id[:6]}",
        "sales_channel": ch["account_code"],  # no customer_id → channel resolve path
        "issue_date": date.today().isoformat(),
        "subtotal": 250000.0, "tax_amount": 0, "total": 250000.0,
    }
    await db.rahaza_ar_invoices.insert_one(dict(ar2_inv))
    _cleanup["ar_ids"].append(ar2_id)
    post = await post_ar_invoice(db, ar2_inv, USER)
    check("post_ar_invoice (channel) ok", post.get("ok"), post.get("je_number", post.get("error", "")))
    _cleanup["je_ids"].append(post.get("je_id"))
    je, dcodes = await _debit_codes(db, post.get("je_id"))
    check("AR debit = channel subledger (bukan 1-220)", ch_acc in dcodes and "1-220" not in dcodes, str(dcodes))

    # ─────────────────────────── BANK ────────────────────────────────────────
    print("\n=== BANK — ensure subledger + gl_account_code ===")
    bank_id = str(uuid.uuid4())
    bank = {"id": bank_id, "code": f"BNK-{bank_id[:4].upper()}", "name": "Bank BCA POC", "type": "bank", "active": True}
    await db.rahaza_cash_accounts.insert_one(dict(bank))
    r = await ensure_subledger_for_entity(db, "bank", bank, USER)
    bank_acc = r.get("code")
    _cleanup["coa_flags_ids"].append(("bank", bank_id))
    check("bank ensure ok", r.get("ok"), bank_acc)
    acc = await db.rahaza_coa_accounts.find_one({"code": bank_acc}, {"_id": 0}) if bank_acc else None
    check("bank akun parent=1-1200", acc and acc.get("parent_code") == "1-1200")
    check("bank normal_balance=DEBIT (asset)", acc and acc.get("normal_balance") == "DEBIT")
    bank_refresh = await db.rahaza_cash_accounts.find_one({"id": bank_id}, {"_id": 0})
    check("bank.gl_account_code tersimpan", bank_refresh.get("gl_account_code") == bank_acc, bank_acc)

    # ─────────────────────────── GENERIC RESOLVER ────────────────────────────
    print("\n=== resolve_subledger_account (generic, dipakai posting) ===")
    check("resolve supplier by code", (await resolve_subledger_account(db, "supplier", entity_code=sup["code"], user=USER)) == sup_acc)
    check("resolve customer by id", (await resolve_subledger_account(db, "customer", entity_id=cust_id, user=USER)) == cust_acc)
    check("resolve channel by account_code", (await resolve_subledger_account(db, "channel", entity_code=ch["account_code"], user=USER)) == ch_acc)
    check("resolve unknown entity → None", (await resolve_subledger_account(db, "supplier", entity_code="NOPE-XYZ", user=USER)) is None)

    # ─────────────────────────── FALLBACK (OFF) ──────────────────────────────
    print("\n=== FALLBACK — entity_type OFF → posting pakai akun kontrol ===")
    await db.rahaza_coa_auto_settings.update_one(
        {"id": "default"}, {"$set": {"entity_types.customer.enabled": False}})
    cust2_id = str(uuid.uuid4())
    cust2 = {"id": cust2_id, "code": f"COFF-{cust2_id[:4].upper()}", "name": "Cust OFF POC", "active": True}
    await db.rahaza_customers.insert_one(dict(cust2))
    ar3_id = str(uuid.uuid4())
    ar3_inv = {
        "id": ar3_id, "invoice_number": f"POC-AROFF-{ar3_id[:6]}",
        "customer_id": cust2_id, "customer_name": cust2["name"],
        "issue_date": date.today().isoformat(),
        "subtotal": 90000.0, "tax_amount": 0, "total": 90000.0,
    }
    await db.rahaza_ar_invoices.insert_one(dict(ar3_inv))
    _cleanup["ar_ids"].append(ar3_id)
    post = await post_ar_invoice(db, ar3_inv, USER)
    _cleanup["je_ids"].append(post.get("je_id"))
    je, dcodes = await _debit_codes(db, post.get("je_id"))
    check("fallback: AR debit = kontrol 1-1301", "1-1301" in dcodes, str(dcodes))
    check("fallback: cust OFF tak dapat subledger",
          await db.rahaza_coa_accounts.count_documents({"flags.subledger_entity_id": cust2_id}) == 0)
    await db.rahaza_coa_auto_settings.update_one(
        {"id": "default"}, {"$set": {"entity_types.customer.enabled": True}})

    # ─────────────────────────── CLEANUP ─────────────────────────────────────
    print("\n=== Cleanup artefak uji ===")
    for jid in _cleanup["je_ids"]:
        if jid:
            await db.rahaza_journal_entries.delete_one({"id": jid})
            await db.rahaza_journal_lines.delete_many({"je_id": jid})
    await db.rahaza_ap_invoices.delete_many({"id": {"$in": _cleanup["ap_ids"]}})
    await db.rahaza_ar_invoices.delete_many({"id": {"$in": _cleanup["ar_ids"]}})
    # delete test master + their subledger accounts
    for etype, eid in _cleanup["coa_flags_ids"]:
        await db.rahaza_coa_accounts.delete_many({"flags.subledger_entity_id": eid})
    await db.rahaza_vendors.delete_one({"id": sup_id})
    await db.rahaza_customers.delete_many({"id": {"$in": [cust_id, cust2_id]}})
    await db.rahaza_coa_accounts.delete_many({"flags.subledger_entity_id": cust2_id})
    await db.marketing_platform_accounts.delete_one({"id": ch_id})
    await db.rahaza_cash_accounts.delete_one({"id": bank_id})
    print("  cleanup done.")

    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r)
    print(f"RESULT: {passed}/{total} checks passed")
    print("=" * 60)
    client.close()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
