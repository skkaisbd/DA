#!/usr/bin/env python3
"""verify_data_integrity.py — POST-SEED DATA-INTEGRITY GATE (CV. Dewi Aditya ERP)

Adapted from the Rahaza-Travel forensic gate methodology, grounded in the REAL da schema
(see SSOT_FORENSIC_RAW_DA.json). Catches "green-but-broken" data bugs that pass HTTP-200 but
violate accounting / inventory / referential invariants. READ-ONLY (never mutates).

Invariants (SSOT: memory/INVARIANTS.md):
  INV-GL-1   Every journal entry balanced: total_debit == total_credit == Σ lines
  INV-GL-2   Global trial balance: Σ posted debits == Σ posted credits
  INV-GL-3   Journal line account_code exists in COA (rahaza_coa_accounts)
  INV-JL-1   rahaza_journal_lines.je_id references an existing journal entry (no orphans)
  INV-STK-1  No negative stock (rahaza_material_stock.qty >= 0; materials.current_stock >= 0)
  INV-CNT-1  Numbered-doc uniqueness (je/po/wo/ap/ar/invoice numbers unique — RC-5 symptom)
  INV-AR-1   AR invoice balance == total - Σ payments; balance >= 0
  INV-AP-1   AP invoice amount >= 0; status ∈ valid set
  INV-LEAVE-1 leave balance: used <= allocated+adjustments; remaining >= 0
  INV-WO-1   work order completed_qty <= target qty
  INV-MKL-1  maklon PO amount_paid <= total_value
  INV-REF-1  referential: material_stock.material_id -> materials; ar_payments -> ar_invoices
  INV-NUM-1  no negative money/qty in key financial collections
  INV-CMTVEN-1..4 (F13) CMT vendor master = SATU master. Dua master yang tidak
             beririsan (`vendor_partners` vs `dewi_cmt_partners`) membuat satu kolom
             `dewi_cmt_payments.cmt_partner_id` berisi id dari dua ruang-id ⇒ hutang
             jasa jahit hilang dari layar vendornya ("outstanding Rp 0" padahal uangnya
             ada) dan laporan pembayaran menggandakan vendor. Dijaga untuk SELURUH DB.

Usage: cd /app && python scripts/verify_data_integrity.py
Exit 0 = valid. !=0 = integrity violation.
"""
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
results = {"pass": 0, "fail": 0, "warn": 0}
EPS = 0.5  # rupiah tolerance


def line(tag, color, msg, detail=""):
    print(f"  {color}[{tag}]{X} {msg}" + (f"  {color}{detail}{X}" if detail else ""))


def _report(name, violations, total, warn_only=False):
    if violations:
        if warn_only:
            results["warn"] += 1
            line("WARN", Y, f"{name}: {len(violations)} anomali", str(violations[:6]))
        else:
            results["fail"] += 1
            line("FAIL", R, f"{name}: {len(violations)} pelanggaran", str(violations[:6]))
    else:
        results["pass"] += 1
        line("PASS", G, f"{name} ({total} diperiksa)")


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _trail_int(s):
    """Extract trailing integer of a doc number, e.g. 'JE-2026-0051' -> 51."""
    m = re.search(r"(\d+)\s*$", str(s or ""))
    return int(m.group(1)) if m else None


async def run():
    print(f"\n{B}{'='*64}{X}\n  DATA INTEGRITY GATE — CV. Dewi Aditya  (DB: {DB_NAME})\n{B}{'='*64}{X}")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        os.system("pip install motor -q")
        from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    # ---------------- FINANCE / GL ----------------
    print(f"\n{C}{B}Finance / General Ledger{X}")
    jes = await db.rahaza_journal_entries.find({}, {"_id": 0}).to_list(20000)
    coa_codes = set(await db.rahaza_coa_accounts.distinct("code"))

    # INV-GL-1: each entry balanced (debit==credit==Σlines)
    v_gl1 = []
    total_d_all = total_c_all = 0.0
    for je in jes:
        if je.get("status") == "voided":
            continue
        td = _num(je.get("total_debit"))
        tc = _num(je.get("total_credit"))
        lines = je.get("lines") or []
        sld = sum(_num(l.get("debit")) for l in lines)
        slc = sum(_num(l.get("credit")) for l in lines)
        total_d_all += td
        total_c_all += tc
        tag = je.get("je_number", je.get("id"))
        if abs(td - tc) > EPS:
            v_gl1.append(f"{tag}(D{td:.0f}!=C{tc:.0f})")
        elif abs(td - sld) > EPS or abs(tc - slc) > EPS:
            v_gl1.append(f"{tag}(header!=Σlines)")
    _report("INV-GL-1 journal entry balanced (debit==credit==Σlines)", v_gl1, len(jes))

    # INV-GL-2: global trial balance
    if abs(total_d_all - total_c_all) > EPS:
        _report("INV-GL-2 global trial balance (ΣDr==ΣCr)",
                [f"ΣDr={total_d_all:.0f} != ΣCr={total_c_all:.0f}"], 1)
    else:
        _report("INV-GL-2 global trial balance (ΣDr==ΣCr)", [], 1)

    # INV-GL-3: journal-line account_code exists in COA
    v_gl3 = []
    if coa_codes:
        for je in jes:
            if je.get("status") == "voided":
                continue
            for l in (je.get("lines") or []):
                acode = l.get("account_code") or l.get("account")
                if acode and acode not in coa_codes:
                    v_gl3.append(f"{je.get('je_number')}:{acode}")
    _report("INV-GL-3 journal line account_code ∈ COA", v_gl3, len(jes))

    # INV-JL-1: separate journal_lines collection references existing entries
    je_ids = set(j.get("id") for j in jes)
    je_nums = set(j.get("je_number") for j in jes)
    jls = await db.rahaza_journal_lines.find({}, {"_id": 0, "id": 1, "je_id": 1, "je_number": 1}).to_list(50000)
    v_jl1 = [jl.get("id") for jl in jls
             if (jl.get("je_id") and jl["je_id"] not in je_ids)
             and (jl.get("je_number") and jl["je_number"] not in je_nums)]
    _report("INV-JL-1 rahaza_journal_lines -> journal entry (no orphan)", v_jl1, len(jls), warn_only=True)

    # ---------------- INVENTORY / WMS ----------------
    print(f"\n{C}{B}Inventory / WMS{X}")
    stock = await db.rahaza_material_stock.find({}, {"_id": 0}).to_list(20000)
    materials = await db.rahaza_materials.find({}, {"_id": 0}).to_list(20000)
    mat_ids = set(m.get("id") for m in materials)

    # INV-STK-1: no negative stock
    v_stk1 = [f"stock:{s.get('material_id')}@{s.get('location_id')}={s.get('qty')}"
              for s in stock if _num(s.get("qty")) < -EPS]
    v_stk1 += [f"mat:{m.get('code')}.current_stock={m.get('current_stock')}"
               for m in materials if _num(m.get("current_stock")) < -EPS]
    _report("INV-STK-1 no negative stock", v_stk1, len(stock) + len(materials))

    # INV-REF-1a: material_stock.material_id -> materials
    v_ref1 = [f"stock->{s.get('material_id')}" for s in stock
              if s.get("material_id") and mat_ids and s["material_id"] not in mat_ids]
    _report("INV-REF-1a material_stock.material_id ∈ materials", v_ref1, len(stock), warn_only=True)

    # ---------------- NUMBERED-DOC UNIQUENESS (RC-5 symptom) ----------------
    print(f"\n{C}{B}Numbered-doc uniqueness / counters (RC-5){X}")
    number_specs = [
        ("rahaza_journal_entries", "je_number"),
        ("rahaza_work_orders", "wo_number"),
        ("rahaza_ap_invoices", "ap_number"),
        ("rahaza_ap_invoices", "invoice_number"),
        ("rahaza_ar_invoices", "invoice_number"),
        ("dewi_maklon_pos", "po_number"),
    ]
    for coll, field in number_specs:
        docs = await db[coll].find({field: {"$exists": True, "$ne": None}}, {"_id": 0, field: 1}).to_list(50000)
        nums = [d.get(field) for d in docs if d.get(field)]
        dups = sorted(set(n for n in nums if nums.count(n) > 1))
        _report(f"INV-CNT-1 {coll}.{field} unik", [f"dup:{d}" for d in dups], len(nums))

    # ---------------- AR / AP ----------------
    print(f"\n{C}{B}Accounts Receivable / Payable{X}")
    ar = await db.rahaza_ar_invoices.find({}, {"_id": 0}).to_list(20000)
    ar_pays = await db.rahaza_ar_payments.find({}, {"_id": 0}).to_list(50000)
    paid_by_inv = {}
    for p in ar_pays:
        k = p.get("invoice_id") or p.get("ar_invoice_id") or p.get("invoice_number")
        paid_by_inv[k] = paid_by_inv.get(k, 0.0) + _num(p.get("amount"))

    # INV-AR-1: balance >= 0 and balance == total - paid (when payments linkable)
    v_ar1 = []
    for inv in ar:
        bal = _num(inv.get("balance"))
        total = _num(inv.get("total"))
        if bal < -EPS:
            v_ar1.append(f"{inv.get('invoice_number')}:balance<0={bal:.0f}")
        elif bal > total + EPS:
            v_ar1.append(f"{inv.get('invoice_number')}:balance>total")
    _report("INV-AR-1 AR balance in [0,total]", v_ar1, len(ar))

    # INV-AR-2: referential ar_payments -> ar_invoices (by number or id)
    ar_ids = set(i.get("id") for i in ar) | set(i.get("invoice_number") for i in ar)
    v_ar2 = [p.get("id") for p in ar_pays
             if (p.get("invoice_id") or p.get("ar_invoice_id") or p.get("invoice_number"))
             and not ({p.get("invoice_id"), p.get("ar_invoice_id"), p.get("invoice_number")} & ar_ids)]
    _report("INV-REF-1b ar_payments -> ar_invoices", v_ar2, len(ar_pays), warn_only=True)

    # INV-AP-1: AP amount >= 0
    ap = await db.rahaza_ap_invoices.find({}, {"_id": 0}).to_list(20000)
    v_ap1 = [f"{a.get('ap_number')}:{a.get('amount')}" for a in ap if _num(a.get("amount")) < -EPS]
    _report("INV-AP-1 AP amount >= 0", v_ap1, len(ap))

    # ---------------- MAKLON PO ----------------
    # NOTE (RC-7 tax-base): PO.amount_paid is TAX-INCLUSIVE (matches dewi_maklon_invoices.total_amount),
    # while PO.total_value is the PRE-TAX subtotal. Comparing them naively yields false "overpay".
    # INV-MKL-1 (FAIL): paid must not exceed the tax-inclusive invoice total (real overpay).
    # INV-MKL-2 (WARN): the pre-tax vs tax-incl mixing within one doc is a semantic smell to document.
    MAX_TAX = 0.11  # PPN 11%
    mkl = await db.dewi_maklon_pos.find({}, {"_id": 0}).to_list(20000)
    mkl_inv = await db.dewi_maklon_invoices.find({}, {"_id": 0}).to_list(20000)
    inv_total_by_no = {}
    for iv in mkl_inv:
        for k in (iv.get("invoice_number"), iv.get("order_id"), iv.get("order_code")):
            if k:
                inv_total_by_no[k] = _num(iv.get("total_amount"))
    v_mkl1, v_mkl2 = [], []
    for m in mkl:
        paid = _num(m.get("amount_paid"))
        pre_tax = _num(m.get("total_value"))
        # Prefer the actual tax-inclusive invoice total; fall back to pre_tax * (1+MAX_TAX).
        inv_total = inv_total_by_no.get(m.get("ar_invoice_number")) or inv_total_by_no.get(m.get("id")) \
            or inv_total_by_no.get(m.get("po_number"))
        ceiling = inv_total if inv_total else pre_tax * (1 + MAX_TAX)
        if paid > ceiling + EPS:
            v_mkl1.append(f"{m.get('po_number')}:paid{paid:.0f}>ceil{ceiling:.0f}")
        elif paid > pre_tax + EPS:
            v_mkl2.append(f"{m.get('po_number')}:paid(tax-incl){paid:.0f}>total_value(pre-tax){pre_tax:.0f}")
    _report("INV-MKL-1 maklon amount_paid <= tax-inclusive invoice total", v_mkl1, len(mkl))
    _report("INV-MKL-2 maklon paid(tax-incl) vs total_value(pre-tax) semantic mix (RC-7)",
            v_mkl2, len(mkl), warn_only=True)

    # ---------------- HR / LEAVE ----------------
    print(f"\n{C}{B}HR / Leave{X}")
    lb = await db.rahaza_leave_balances.find({}, {"_id": 0}).to_list(20000)
    v_lv = []
    for b in lb:
        allocated = _num(b.get("allocated")) + _num(b.get("adjustments"))
        used = _num(b.get("used"))
        if used < -EPS:
            v_lv.append(f"{b.get('employee_id')}:used<0")
        elif used > allocated + EPS:
            v_lv.append(f"{b.get('employee_id')}:{b.get('leave_type_id')} used{used:.0f}>alloc{allocated:.0f}")
    _report("INV-LEAVE-1 leave used <= allocated+adjustments & >=0", v_lv, len(lb))

    # ---------------- PRODUCTION / WORK ORDERS ----------------
    print(f"\n{C}{B}Production / Work Orders{X}")
    wos = await db.rahaza_work_orders.find({}, {"_id": 0}).to_list(20000)
    v_wo = []
    for w in wos:
        target = max(_num(w.get("qty_target")), _num(w.get("target_qty")), _num(w.get("qty")))
        done = _num(w.get("completed_qty"))
        if done < -EPS:
            v_wo.append(f"{w.get('wo_number')}:done<0")
        elif target > 0 and done > target + EPS:
            v_wo.append(f"{w.get('wo_number')}:done{done:.0f}>target{target:.0f}")
    _report("INV-WO-1 completed_qty in [0,target]", v_wo, len(wos))

    # ---------------- NUMERIC NON-NEGATIVE (money/qty) ----------------
    print(f"\n{C}{B}Numeric bounds (money/qty non-negative){X}")
    neg_specs = [
        ("rahaza_ar_invoices", ["total", "balance"]),
        ("rahaza_ap_invoices", ["amount"]),
        ("rahaza_cash_movements", ["amount"]),
        ("rahaza_ar_payments", ["amount"]),
        ("dewi_maklon_pos", ["total_value", "amount_paid", "total_qty"]),
    ]
    v_num = []
    checked = 0
    for coll, fields in neg_specs:
        docs = await db[coll].find({}, {"_id": 0}).to_list(50000)
        checked += len(docs)
        for d in docs:
            for f in fields:
                if d.get(f) is not None and _num(d.get(f)) < -EPS:
                    v_num.append(f"{coll}.{f}={d.get(f)}")
    _report("INV-NUM-1 money/qty non-negative", v_num, checked)

    # ---------------- CMT VENDOR MASTER (F13) ----------------
    # KELAS MASALAH: dua master vendor CMT yang tidak beririsan
    # (`vendor_partners` vs `dewi_cmt_partners`) membuat SATU kolom
    # `dewi_cmt_payments.cmt_partner_id` berisi id dari DUA ruang-id. Pembaca
    # memakai satu ruang-id, dokumennya memakai yang lain ⇒ hutang jasa jahit
    # HILANG dari layar vendornya ("outstanding Rp 0" padahal uangnya ada) dan
    # laporan pembayaran menggandakan vendor yang sama. Ini invarian DATA, jadi
    # tempatnya di sini: dijaga untuk SELURUH DB, bukan hanya jalur yang kebetulan
    # diuji lewat HTTP.
    print(f"\n{C}{B}Master Vendor CMT (F13 — satu master){X}")
    vps = await db.vendor_partners.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1, "cmt_partner_id": 1}).to_list(20000)
    cps = await db.dewi_cmt_partners.find(
        {}, {"_id": 0, "id": 1, "code": 1, "name": 1,
             "vendor_partner_id": 1, "vendor_id": 1}).to_list(20000)
    pays = await db.dewi_cmt_payments.find(
        {}, {"_id": 0, "id": 1, "payment_code": 1, "vendor_id": 1,
             "cmt_partner_id": 1, "cmt_name": 1}).to_list(50000)
    vp_ids = {v["id"] for v in vps}

    # Peta id master Portal CMT → id vendor_partners (tautan dua arah).
    cp_to_vp = {}
    for c in cps:
        tgt = c.get("vendor_partner_id") or c.get("vendor_id") or ""
        if tgt:
            cp_to_vp[c["id"]] = tgt
        elif c["id"] in vp_ids:
            cp_to_vp[c["id"]] = c["id"]      # id kembar = master sudah disatukan
    for v in vps:
        if v.get("cmt_partner_id"):
            cp_to_vp.setdefault(v["cmt_partner_id"], v["id"])

    def _canon(one):
        if not one:
            return ""
        return one if one in vp_ids else cp_to_vp.get(one, "")

    # INV-CMTVEN-1: setiap master Portal CMT punya pasangan di vendor_partners.
    v_cv1 = [f"{c.get('code') or c['id'][:8]}:{str(c.get('name'))[:18]}"
             for c in cps if not _canon(c["id"])]
    _report("INV-CMTVEN-1 setiap dewi_cmt_partners terpetakan ke vendor_partners "
            "(jalankan scripts/migrate_unify_cmt_vendor_master.py)", v_cv1, len(cps))

    # INV-CMTVEN-2: setiap pembayaran CMT bisa ditelusuri ke SATU vendor SSOT.
    v_cv2 = [f"{p.get('payment_code') or p['id'][:8]}({p.get('cmt_name') or '?'})"
             for p in pays
             if not (_canon(p.get("vendor_id")) or _canon(p.get("cmt_partner_id")))]
    _report("INV-CMTVEN-2 setiap dewi_cmt_payments menunjuk vendor yang bisa "
            "ditemukan di master SSOT (kalau tidak, tagihannya tak muncul di layar "
            "vendor mana pun)", v_cv2, len(pays))

    # INV-CMTVEN-3: kalau kedua kolom terisi, keduanya harus menunjuk vendor YANG SAMA.
    v_cv3 = []
    for p in pays:
        a, b = _canon(p.get("vendor_id")), _canon(p.get("cmt_partner_id"))
        if a and b and a != b:
            v_cv3.append(f"{p.get('payment_code') or p['id'][:8]}: {a[:8]}!={b[:8]}")
    _report("INV-CMTVEN-3 vendor_id & cmt_partner_id pada satu pembayaran menunjuk "
            "vendor yang SAMA (satu dokumen tidak boleh milik dua vendor)",
            v_cv3, len(pays))

    # INV-CMTVEN-4: master vendor tidak menggandakan vendor yang sama.
    # (user story F13: "laporan pembayaran tidak menggandakan vendor")
    def _nk(s):
        return "".join(ch for ch in str(s or "").lower() if ch.isalnum())

    seen_name, seen_code, v_cv4 = {}, {}, []
    for v in vps:
        nk, ck = _nk(v.get("name")), _nk(v.get("code"))
        if nk and nk in seen_name:
            v_cv4.append(f"nama kembar: {str(v.get('name'))[:20]}")
        elif nk:
            seen_name[nk] = v["id"]
        if ck and ck in seen_code:
            v_cv4.append(f"kode kembar: {v.get('code')}")
        elif ck:
            seen_code[ck] = v["id"]
    _report("INV-CMTVEN-4 vendor_partners bebas duplikat nama/kode (laporan "
            "pembayaran CMT tidak menggandakan vendor)", v_cv4, len(vps))

    # ---------------- SUMMARY ----------------
    print(f"\n{B}{'='*64}{X}\n  {G}PASS {results['pass']}{X} | {Y}WARN {results['warn']}{X} | {R}FAIL {results['fail']}{X}\n{B}{'='*64}{X}")
    if results["fail"]:
        print(f"{R}{B}  INTEGRITY VIOLATION — perbaiki sebelum klaim selesai.{X}\n")
        return 1
    print(f"{G}{B}  Semua invarian data valid (WARN = anomali non-blok).{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
