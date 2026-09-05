"""Iteration 110: Rekonsiliasi Bank (H-05/H-06) + COGS fulfillment online memakai FIFO batch (H-07 review).

Run serially:  python3 -m pytest tests/test_iter110_bank_recon.py -q -p no:cacheprovider -n 0
"""
import asyncio
import io
import os
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
be = dotenv_values("/app/backend/.env")
db = MongoClient(os.environ.get("MONGO_URL") or be["MONGO_URL"])[os.environ.get("DB_NAME") or be["DB_NAME"]]

_tok = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60).json()["token"]
H = {"Authorization": f"Bearer {_tok}", "Content-Type": "application/json"}
HA = {"Authorization": f"Bearer {_tok}"}
SFX = uuid.uuid4().hex[:6].upper()
R = f"{BASE}/api/finance/bank-recon"
S = {}


def _txn(amount):
    return db.bank_recon_txns.find_one({"session_id": S["sid"], "amount": amount}, {"_id": 0})


class TestBankRecon:
    def test_00_setup_account_and_gl(self):
        r = requests.post(f"{BASE}/api/rahaza/cash-accounts", headers=H, timeout=60, json={
            "code": f"RC-{SFX}", "name": f"Bank Recon {SFX}", "type": "bank", "gl_account_code": "1-1201", "opening_balance": 0})
        assert r.status_code == 200, r.text
        S["acc"] = r.json()
        assert S["acc"]["gl_account_code"]
        pid = f"qa-cmt-rc-{SFX.lower()}"
        db.dewi_cmt_payments.insert_one({"id": pid, "payment_code": f"PAY-RC-{SFX}", "cmt_name": "QA Vendor", "po_id": "po-int-demo-2",
                                         "subtotal": 150000, "total_penalty": 0, "net_amount": 150000, "total_amount": 150000,
                                         "status": "draft", "payment_date": "2026-09-04"})
        r = requests.post(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{pid}/pay", headers=H, timeout=60,
                          json={"cash_account_id": S["acc"]["id"], "amount": 150000, "payment_date": "2026-09-05"})
        assert r.status_code == 200, r.text
        S["pay_je"] = r.json()["gl_je_number"]

    def test_01_session_requires_cash_account(self):
        r = requests.post(f"{R}/sessions", headers=H, timeout=60, json={"period": "2026-09", "bank_name": "X"})
        assert r.status_code == 400
        r = requests.post(f"{R}/sessions", headers=H, timeout=60, json={"period": "2026-09", "cash_account_id": S["acc"]["id"], "closing_balance": -156500})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["gl_account_code"] == S["acc"]["gl_account_code"] and s["account_name"] == S["acc"]["name"]
        S["sid"] = s["id"]
        r = requests.post(f"{R}/sessions", headers=H, timeout=60, json={"period": "2026-09", "cash_account_id": S["acc"]["id"]})
        assert r.status_code == 409

    def test_02_gl_lines_only_bank_account(self):
        r = requests.get(f"{R}/sessions/{S['sid']}", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["gl_lines"]) == 1
        g = d["gl_lines"][0]
        assert g["je_number"] == S["pay_je"] and g["direction"] == "out" and g["amount"] == 150000 and not g["is_matched"]
        assert d["summary"]["gl_balance_end"] == -150000

    def test_03_import_csv_direction(self):
        csv = ("Tanggal,Keterangan,Debit,Kredit,Referensi\n"
               "06/09/2026,TRF KE QA VENDOR,\"150.500\",,TRF1\n"
               "07/09/2026,BIAYA ADM,\"6.500\",,ADM1\n"
               "03/09/2026,SETORAN,,\"1.000.000\",DEP1\n")
        r = requests.post(f"{R}/sessions/{S['sid']}/import-csv", headers=HA, timeout=60,
                          files={"file": ("koran.csv", io.BytesIO(csv.encode()), "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 3
        assert _txn(150500)["direction"] == "out" and _txn(1000000)["direction"] == "in"
        assert _txn(150500)["txn_date"] == "2026-09-06"

    def test_04_auto_match_tolerance(self):
        r = requests.post(f"{R}/sessions/{S['sid']}/auto-match", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["matched"] == 1 and d["rule"] == {"amount_tolerance": 1000.0, "days_tolerance": 3}
        t = _txn(150500)
        assert t["is_matched"] and t["auto_matched"] and t["amount_diff"] == 500
        assert db.bank_recon_matches.count_documents({"session_id": S["sid"]}) == 1
        assert db.rahaza_journal_entries.count_documents({"is_matched": True}) == 0, "SSOT jurnal tidak boleh ditulis"

    def test_05_adjust_from_txn_uses_session_bank_account(self):
        t = _txn(6500)
        r = requests.post(f"{R}/sessions/{S['sid']}/transactions/{_txn(1000000)['id']}/adjust", headers=H, timeout=60, json={"adjustment_type": "bank_charge"})
        assert r.status_code == 400
        r = requests.post(f"{R}/sessions/{S['sid']}/transactions/{t['id']}/adjust", headers=H, timeout=60, json={"adjustment_type": "bank_charge"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["matched"] and d["je_number"]
        je = db.rahaza_journal_entries.find_one({"je_number": d["je_number"]}, {"_id": 0})
        codes = {l["account_code"]: (l["debit"], l["credit"]) for l in je["lines"]}
        assert codes[S["acc"]["gl_account_code"]] == (0, 6500) and "1-1201" not in codes
        assert db.rahaza_cash_movements.find_one({"ref_id": d["adjustment_id"]})["gl_je_id"] == je["id"]
        assert db.rahaza_cash_accounts.find_one({"id": S["acc"]["id"]})["balance"] == -156500

    def test_06_manual_unmatch_match_direction_guard(self):
        t = _txn(6500)
        assert requests.post(f"{R}/sessions/{S['sid']}/unmatch", headers=H, timeout=60, json={"txn_id": t["id"]}).status_code == 200
        assert not _txn(6500)["is_matched"]
        c = requests.get(f"{R}/sessions/{S['sid']}/transactions/{t['id']}/candidates", headers=H, timeout=60).json()
        assert c["items"] and c["items"][0]["within_rule"] and c["items"][0]["amount"] == 6500
        key = c["items"][0]["key"]
        dep = _txn(1000000)
        r = requests.post(f"{R}/sessions/{S['sid']}/match", headers=H, timeout=60, json={"txn_id": dep["id"], "target_key": key})
        assert r.status_code == 400 and "Arah" in r.text
        r = requests.post(f"{R}/sessions/{S['sid']}/match", headers=H, timeout=60, json={"txn_id": t["id"], "target_key": key})
        assert r.status_code == 200, r.text
        assert _txn(6500)["is_matched"] and _txn(6500)["auto_matched"] is False

    def test_07_internal_check_and_summary(self):
        r = requests.get(f"{R}/sessions/{S['sid']}/internal-check", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["movements"]) == 2 and all(m["status"] == "ok" for m in d["movements"])
        assert d["card_balance"] == d["gl_balance_now"] == -156500
        s = requests.get(f"{R}/sessions/{S['sid']}", headers=H, timeout=60).json()["summary"]
        assert s["gl_balance_end"] == -156500 and s["difference"] == 0
        assert s["unmatched_bank_count"] == 1 and s["unmatched_bank_in"] == 1000000 and s["explained"] is False

    def test_08_approve_guard_then_approve(self):
        r = requests.post(f"{R}/sessions/{S['sid']}/approve", headers=H, timeout=60)
        assert r.status_code == 400
        dep = _txn(1000000)
        assert requests.delete(f"{R}/sessions/{S['sid']}/transactions/{dep['id']}", headers=H, timeout=60).status_code == 200
        r = requests.post(f"{R}/sessions/{S['sid']}/approve", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved" and r.json()["approved_summary"]["explained"] is True
        r = requests.post(f"{R}/sessions/{S['sid']}/transactions", headers=H, timeout=60, json={"txn_date": "2026-09-09", "amount": 1})
        assert r.status_code == 400


class TestFulfillmentCogsFifo:
    def test_00_post_cogs_shipment_uses_fifo_layers(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        from routes.rahaza_posting import post_cogs_shipment
        from core import fg_cost_layers as fcl
        mid = f"mat-qa-{SFX}"
        db.fg_cost_layers.insert_one({"id": f"ly-{SFX}", "material_id": mid, "qty_in": 10, "qty_remaining": 10, "unit_cost": 40000,
                                      "total_cost": 400000, "breakdown": {"material_cost": 25000, "sewing_cost": 12000, "overhead_cost": 3000},
                                      "batch": {"po_number": "PO-QA"}, "created_at": "2026-09-01T00:00:00"})

        async def run():
            adb = AsyncIOMotorClient(be["MONGO_URL"])[be["DB_NAME"]]
            c = await fcl.consume_fifo(adb, material_id=mid, qty=4, ref={"source": "fulfillment"}, actor={"name": "qa"})
            ship = {"id": f"ship-{SFX}", "shipment_number": f"FUL-{SFX}", "dispatched_at": "2026-09-05T10:00:00",
                    "items": [{"material_id": mid, "qty": 4, "sku_code": "QA", "fg_cogs": c["cogs"],
                               "fg_cogs_layers": c["layers_used"], "fg_cogs_uncosted_qty": c["uncosted_qty"]}]}
            r1 = await post_cogs_shipment(adb, ship, {"id": "qa", "name": "QA"})
            r2 = await post_cogs_shipment(adb, ship, {"id": "qa", "name": "QA"})
            r3 = await post_cogs_shipment(adb, {"id": f"ship0-{SFX}", "shipment_number": "FUL-0", "items": [{"material_id": "x", "qty": 1}]},
                                          {"id": "qa", "name": "QA"})
            return r1, r2, r3
        r1, r2, r3 = asyncio.run(run())
        assert r1["ok"] and r1["basis"] == "fifo_batch" and r1["total_cogs"] == 160000 and r1["uncosted_qty"] == 0
        je = db.rahaza_journal_entries.find_one({"id": r1["je_id"]}, {"_id": 0})
        codes = {l["account_code"]: (l["debit"], l["credit"]) for l in je["lines"]}
        assert codes["1-1404"] == (0, 160000) and codes["5-1000"][0] == 100000 and codes["5-2000"][0] == 48000
        assert "biaya batch FIFO" in je["memo"]
        assert r2.get("already_posted")
        assert r3["ok"] is False and r3["reason"] == "zero_cogs"
        assert db.fg_cost_layers.find_one({"id": f"ly-{SFX}"})["qty_remaining"] == 6

    def test_01_balance_sheet(self):
        r = requests.get(f"{BASE}/api/rahaza/finance/reports/balance-sheet", headers=H, timeout=120)
        assert r.status_code == 200 and r.json().get("balanced") is True


class TestRbacAndCleanup:
    def test_00_non_finance_role_forbidden(self):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": "gudang@dewiaditya.id", "password": "Dewi@123"}, timeout=60)
        if r.status_code != 200:
            return  # akun seed gudang tidak ada — lewati
        hg = {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}
        assert requests.get(f"{R}/sessions", headers=hg, timeout=60).status_code == 403
        assert requests.post(f"{R}/sessions", headers=hg, timeout=60, json={"period": "2026-01", "cash_account_id": "x"}).status_code == 403
        assert requests.post(f"{R}/sessions/{S['sid']}/auto-match", headers=hg, timeout=60, json={}).status_code == 403

    def test_99_cleanup_test_data(self):
        """Bersihkan SEMUA jejak uji dari GL/subledger supaya DB seed tetap bersih (temuan audit iter 111)."""
        je_ids = set()
        acc = S.get("acc") or {}
        for j in db.rahaza_journal_entries.find({"$or": [
                {"source_module": "bank_recon_adjustment", "lines.account_code": acc.get("gl_account_code", "-")},
                {"source_module": "ap_payment", "lines.account_code": acc.get("gl_account_code", "-")},
                {"source_module": "cogs_shipment", "source_ref": {"$in": [f"cogs:ship-{SFX}", f"cogs:ship0-{SFX}"]}},
                {"source_module": "cmt_ap_invoice", "source_ref": {"$regex": f"qa-cmt-rc-{SFX.lower()}"}}]}, {"_id": 0, "id": 1}):
            je_ids.add(j["id"])
        if je_ids:
            db.rahaza_journal_entries.delete_many({"id": {"$in": list(je_ids)}})
            db.rahaza_journal_lines.delete_many({"je_id": {"$in": list(je_ids)}})
        if S.get("sid"):
            db.bank_recon_sessions.delete_one({"id": S["sid"]})
            db.bank_recon_txns.delete_many({"session_id": S["sid"]})
            db.bank_recon_matches.delete_many({"session_id": S["sid"]})
            db.rahaza_bank_recon_adjustments.delete_many({"session_id": S["sid"]})
        if acc.get("id"):
            db.rahaza_cash_movements.delete_many({"account_id": acc["id"]})
            db.rahaza_cash_accounts.delete_one({"id": acc["id"]})
            if acc.get("gl_account_code") and acc["gl_account_code"] != "1-1201":
                db.rahaza_coa_accounts.delete_one({"code": acc["gl_account_code"]})
        pid = f"qa-cmt-rc-{SFX.lower()}"
        db.dewi_cmt_payments.delete_one({"id": pid})
        db.dewi_cmt_disbursements.delete_many({"payment_id": pid})
        db.fg_cost_layers.delete_one({"id": f"ly-{SFX}"})
        db.fg_cost_consumptions.delete_many({"layer_id": f"ly-{SFX}"})
        db.rahaza_shipments.delete_many({"id": {"$in": [f"ship-{SFX}", f"ship0-{SFX}"]}})
        assert db.rahaza_journal_entries.count_documents({"id": {"$in": list(je_ids)}}) == 0
