#!/usr/bin/env python3
"""round6_verify.py — RE-VERIFIKASI pasca-FIX (isolated + cleanup).

Membuktikan EMPIRIS bahwa BUG-NUM-1/2/3/4 kini DITOLAK (SAFE) + positive control tetap jalan,
plus spot-check kelas numeric-bounds (Field(ge=0)) via Pydantic 422.

Prinsip: seed data bertanda 'R6-VERIFY' → picu skenario → assert status → CLEANUP semua.
Usage: cd /app && python scripts/round6_verify.py
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import http, login, db_handle, REPORT_DIR, G, R, Y, C, B, X  # noqa: E402

MARK = "R6-VERIFY"
RESULTS = []
CREATED = {"ar": [], "ap": [], "maklon_clients": [], "customers": []}


def _count_orphan_ar_ap_je(db) -> int:
    """Hitung jurnal AR/AP yang invoice sumbernya sudah tidak ada (jurnal YATIM).

    FASE 11 — dipakai sebagai penjaga: kalau angkanya > 0 berarti cleanup skrip ini
    (atau skrip lain) bocor dan meninggalkan jejak di buku besar.
    `source_ref` berbentuk "ar:<invoice_id>" / "arpay:<invoice_id>:<tgl>:<nominal>".
    """
    ar_ids = {x["id"] for x in db.rahaza_ar_invoices.find({}, {"id": 1}) if x.get("id")}
    ap_ids = {x["id"] for x in db.rahaza_ap_invoices.find({}, {"id": 1}) if x.get("id")}
    known = ar_ids | ap_ids
    orphan = 0
    for je in db.rahaza_journal_entries.find(
            {"source_module": {"$in": ["ar_invoice", "ar_payment", "ap_invoice", "ap_payment"]}},
            {"source_ref": 1}):
        ref = str(je.get("source_ref") or "")
        parts = ref.split(":")
        inv_id = parts[1] if len(parts) > 1 else ""
        if inv_id and inv_id not in known:
            orphan += 1
    return orphan


def check(name, got, expect_set, extra=""):
    ok = got in expect_set
    verdict = "SAFE" if ok else "FAIL"
    col = G if ok else R
    RESULTS.append({"test": name, "status": got, "expected": sorted(expect_set), "verdict": verdict, "detail": extra})
    print(f"  {col}[{verdict:4}]{X} {name}: HTTP {got} (expect {sorted(expect_set)}) {extra}")
    return ok


def main():
    print(f"{B}{C}{'='*70}{X}\n  ROUND-6 RE-VERIFY (pasca-fix BUG-NUM-1/2/3/4 + bounds)\n{B}{C}{'='*70}{X}")
    token = login()
    if not token:
        print(f"{R}login gagal — abort{X}"); return 1
    db = db_handle()

    # ── SEED isolated customer (untuk AR) ──
    cust_id = str(uuid.uuid4())
    db.rahaza_customers.insert_one({
        "id": cust_id, "name": f"{MARK} Customer", "notes": MARK,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    CREATED["customers"].append(cust_id)

    def ar_body(items, tax_pct=11, discount=0):
        return {"customer_id": cust_id, "items": items, "tax_pct": tax_pct,
                "discount_amount": discount, "notes": MARK}

    # ═══ BUG-NUM-2: AR invoice bounds ═══
    print(f"\n{B}BUG-NUM-2 — AR invoice create bounds{X}")
    st, txt = http("POST", "/rahaza/ar-invoices", token=token,
                   body=ar_body([{"description": "x", "qty": 10, "price": 1000}]))
    if check("AR positive control (qty10 price1000)", st, {200}):
        try: CREATED["ar"].append(json.loads(txt)["id"])
        except Exception: pass
    for nm, items, disc in [
        ("AR negative qty", [{"description": "x", "qty": -10, "price": 1000}], 0),
        ("AR negative price", [{"description": "x", "qty": 10, "price": -1000}], 0),
    ]:
        st, txt = http("POST", "/rahaza/ar-invoices", token=token, body=ar_body(items, discount=disc))
        if not check(nm, st, {400}) and st == 200:
            try: CREATED["ar"].append(json.loads(txt)["id"])
            except Exception: pass
    st, _ = http("POST", "/rahaza/ar-invoices", token=token,
                 body=ar_body([{"description": "x", "qty": 10, "price": 1000}], tax_pct=-50))
    check("AR negative tax_pct", st, {400})
    st, txt = http("POST", "/rahaza/ar-invoices", token=token,
                   body=ar_body([{"description": "x", "qty": 10, "price": 1000}], discount=999999))
    if not check("AR discount>total", st, {400}) and st == 200:
        try: CREATED["ar"].append(json.loads(txt)["id"])
        except Exception: pass
    st, _ = http("POST", "/rahaza/ar-invoices", token=token,
                 body=ar_body([{"description": "x", "qty": "abc", "price": 1000}]))
    check("AR non-numeric qty (no 5xx)", st, {400})

    # ═══ BUG-NUM-4: AP invoice bounds ═══
    print(f"\n{B}BUG-NUM-4 — AP invoice create bounds{X}")
    st, txt = http("POST", "/rahaza/ap-invoices", token=token,
                   body={"vendor_name": f"{MARK} Vendor", "items": [{"qty": 10, "price": 1000}], "tax_pct": 11, "notes": MARK})
    if check("AP positive control", st, {200}):
        try: CREATED["ap"].append(json.loads(txt)["id"])
        except Exception: pass
    for nm, items in [
        ("AP negative price", [{"qty": 10, "price": -1000}]),
        ("AP negative qty", [{"qty": -10, "price": 1000}]),
    ]:
        st, txt = http("POST", "/rahaza/ap-invoices", token=token,
                       body={"vendor_name": f"{MARK} Vendor", "items": items, "tax_pct": 11, "notes": MARK})
        if not check(nm, st, {400}) and st == 200:
            try: CREATED["ap"].append(json.loads(txt)["id"])
            except Exception: pass

    # ═══ BUG-NUM-3: pay cancelled AR invoice ═══
    print(f"\n{B}BUG-NUM-3 — payment ke invoice cancelled{X}")
    st, txt = http("POST", "/rahaza/ar-invoices", token=token,
                   body=ar_body([{"description": "x", "qty": 10, "price": 1000}]))
    if st == 200:
        iid = json.loads(txt)["id"]; CREATED["ar"].append(iid)
        # positive control: pay valid draft invoice
        stp, _ = http("POST", f"/rahaza/ar-invoices/{iid}/payment", token=token, body={"amount": 500})
        check("AR payment positive control (draft)", stp, {200})
        # cancel then pay -> must reject
        http("POST", f"/rahaza/ar-invoices/{iid}/status", token=token, body={"status": "cancelled"})
        stc, _ = http("POST", f"/rahaza/ar-invoices/{iid}/payment", token=token, body={"amount": 1000})
        check("AR payment to CANCELLED invoice", stc, {400})
    else:
        check("AR setup for cancel-test", st, {200})

    # ═══ BUG-NUM-1: maklon client negative rate ═══
    print(f"\n{B}BUG-NUM-1 — maklon client negative rate{X}")
    code = "R6CLT" + uuid.uuid4().hex[:6].upper()
    st, txt = http("POST", "/dewi/maklon/clients", token=token,
                   body={"code": code, "name": f"{MARK} Client", "standard_rate_per_pcs": 5000, "notes": MARK})
    if check("Maklon client positive control (rate 5000)", st, {200}):
        try: CREATED["maklon_clients"].append(json.loads(txt)["id"])
        except Exception: pass
    st, txt = http("POST", "/dewi/maklon/clients", token=token,
                   body={"code": code + "N", "name": f"{MARK} Client Neg", "standard_rate_per_pcs": -99999, "notes": MARK})
    if not check("Maklon client NEGATIVE rate", st, {422, 400}) and st == 200:
        try: CREATED["maklon_clients"].append(json.loads(txt)["id"])
        except Exception: pass

    # ═══ Spot-check kelas bounds (Pydantic 422 sebelum lookup parent) ═══
    print(f"\n{B}Spot-check numeric bounds (codemod Field(ge=0)){X}")
    st, _ = http("POST", "/marketing/catalogs/FAKE-CID/items", token=token,
                 body={"sku": "R6SKU", "name": "R6 Item", "price": -100})
    check("Catalog item negative price -> 422", st, {422})

    # ── CLEANUP ──
    print(f"\n{Y}cleanup…{X}")
    dc = {}
    # FASE 11 — TAMBAL KEBOCORAN: membuat + membayar AR invoice juga MEM-POSTING
    # jurnal (`source_module` ar_invoice / ar_payment, `source_ref` = "ar:<id>" /
    # "arpay:<id>:…"). Sebelumnya hanya invoice-nya yang dihapus, jurnalnya
    # tertinggal jadi YATIM — menumpuk 2 JE setiap kali gate dijalankan.
    ar_ids = list(CREATED["ar"] or [])
    ar_ids += [x["id"] for x in db.rahaza_ar_invoices.find({"notes": MARK}, {"id": 1}) if x.get("id")]
    ap_ids = list(CREATED["ap"] or [])
    ap_ids += [x["id"] for x in db.rahaza_ap_invoices.find({"notes": MARK}, {"id": 1}) if x.get("id")]

    dc["ar_by_id"] = db.rahaza_ar_invoices.delete_many({"id": {"$in": CREATED["ar"]}}).deleted_count if CREATED["ar"] else 0
    dc["ar_by_mark"] = db.rahaza_ar_invoices.delete_many({"notes": MARK}).deleted_count
    dc["ap_by_id"] = db.rahaza_ap_invoices.delete_many({"id": {"$in": CREATED["ap"]}}).deleted_count if CREATED["ap"] else 0
    dc["ap_by_mark"] = db.rahaza_ap_invoices.delete_many({"notes": MARK}).deleted_count
    dc["clients"] = db.dewi_maklon_clients.delete_many({"notes": MARK}).deleted_count
    dc["customers"] = db.rahaza_customers.delete_many({"notes": MARK}).deleted_count

    # jurnal turunan dari invoice uji di atas
    je_ids = []
    for inv_id in set(ar_ids + ap_ids):
        for je in db.rahaza_journal_entries.find(
                {"source_ref": {"$regex": inv_id}}, {"id": 1}):
            if je.get("id"):
                je_ids.append(je["id"])
    if je_ids:
        dc["journal_entries"] = db.rahaza_journal_entries.delete_many({"id": {"$in": je_ids}}).deleted_count
        dc["journal_lines"] = db.rahaza_journal_lines.delete_many({"je_id": {"$in": je_ids}}).deleted_count
    print(f"  deleted: {dc}")
    residual = {
        "ar_mark": db.rahaza_ar_invoices.count_documents({"notes": MARK}),
        "ap_mark": db.rahaza_ap_invoices.count_documents({"notes": MARK}),
        "clients_mark": db.dewi_maklon_clients.count_documents({"notes": MARK}),
        "cust_mark": db.rahaza_customers.count_documents({"notes": MARK}),
        "neg_ar": db.rahaza_ar_invoices.count_documents({"total": {"$lt": 0}}),
        "neg_ap": db.rahaza_ap_invoices.count_documents({"total": {"$lt": 0}}),
        # jurnal yatim: JE ber-source AR/AP yang invoice-nya sudah tidak ada
        "orphan_je": _count_orphan_ar_ap_je(db),
    }
    print(f"  residual: {residual}")

    fails = [r for r in RESULTS if r["verdict"] == "FAIL"]
    payload = {"round": 6, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "total": len(RESULTS), "safe": len(RESULTS) - len(fails), "fail": len(fails),
               "cleanup": dc, "residual": residual, "results": RESULTS}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "round6_verify.json").write_text(json.dumps(payload, indent=2))
    all_clean = all(v == 0 for v in residual.values())
    print(f"\n{B}{'-'*70}{X}")
    print(f"  R6: {len(RESULTS)-len(fails)}/{len(RESULTS)} SAFE, {len(fails)} FAIL | residual clean: {all_clean}")
    if fails:
        print(f"  {R}{B}✗ ADA FAIL — fix belum tuntas:{X}")
        for f in fails: print(f"     - {f['test']}: HTTP {f['status']} (expect {f['expected']})")
        return 1
    if not all_clean:
        print(f"  {R}{B}✗ RESIDUAL artefak tersisa — cleanup gagal{X}"); return 1
    print(f"  {G}{B}✓ SEMUA FIX TERVERIFIKASI SAFE + DB bersih.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
