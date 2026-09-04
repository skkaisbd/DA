"""Iteration 96 — INV-F44 independent verification.

Module under test: routes/rahaza_posting.post_cogs_on_buyer_dispatch
                   (+ helper _fifo_cogs_for_dispatch) and core/fg_cost_layers.

All DB artifacts use a synthetic material_id (uuid) so no real FG master /
cost layer / marketing catalog row is ever touched, and every document is
marked with a unique MARK so cleanup is exhaustive.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values, load_dotenv

ROOT = Path("/app")
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(str(ROOT / "backend/.env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from core import fg_cost_layers as fcl  # noqa: E402
from routes.rahaza_posting import post_cogs_on_buyer_dispatch  # noqa: E402

_fe = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

MARK = f"T1-F44-{datetime.now(timezone.utc).strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
USER = {"id": "t1-iter96", "name": "T1 Tester iter96"}
BD = {"material_cost": 6000, "sewing_cost": 2000, "permak_cost": 400,
      "internal_labor_cost": 100, "overhead_cost": 1500}  # Σ = 10.000
UNIT_COST = 10000.0


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _mk_shipment(db, mat_id, sku, qty, *, fg_cogs=None, layers=None,
                       uncosted=0, job_id=None):
    sid, iid = str(uuid.uuid4()), str(uuid.uuid4())
    await db.buyer_shipments.insert_one({
        "id": sid, "shipment_number": f"{MARK}-{sid[:4]}", "notes": MARK,
        "receiver_type": "buyer", "business_type": "internal",
        "shipment_date": date.today().isoformat(),
        "customer_name": "T1 Buyer", "created_at": datetime.now(timezone.utc)})
    row = {"id": iid, "shipment_id": sid, "sku": sku, "qty_shipped": qty,
           "notes": MARK, "fg_material_id": mat_id, "dispatch_seq": 1}
    if fg_cogs is not None:
        row.update({"fg_cogs": fg_cogs, "fg_cogs_layers": layers or [],
                    "fg_cogs_uncosted_qty": uncosted})
    if job_id:
        row["job_id"] = job_id
    await db.buyer_shipment_items.insert_one(row)
    shp = await db.buyer_shipments.find_one({"id": sid}, {"_id": 0})
    item = await db.buyer_shipment_items.find_one({"id": iid}, {"_id": 0})
    return shp, item


async def _cleanup(db, je_ids, layer_ids, ship_ids):
    for je_id in je_ids:
        await db.rahaza_journal_entries.delete_many({"id": je_id})
        await db.rahaza_journal_lines.delete_many({"je_id": je_id})
    await db.rahaza_journal_entries.delete_many({"memo": {"$regex": MARK}})
    await db.rahaza_journal_lines.delete_many({"source_ref": {"$regex": MARK}})
    await db.buyer_shipment_items.delete_many({"notes": MARK})
    await db.buyer_shipments.delete_many({"notes": MARK})
    await db.rahaza_hpp_snapshots.delete_many({"notes": MARK})
    await db[fcl.LAYERS].delete_many({"id": {"$in": layer_ids}})
    await db[fcl.CONSUMPTIONS].delete_many({"ref.source": MARK})
    for sid in ship_ids:
        await db.rahaza_journal_entries.delete_many(
            {"source_ref": {"$regex": sid}})
        await db.rahaza_journal_lines.delete_many(
            {"source_ref": {"$regex": sid}})
    return {
        "je": await db.rahaza_journal_entries.count_documents({"memo": {"$regex": MARK}}),
        "je_lines": await db.rahaza_journal_lines.count_documents({"source_ref": {"$regex": MARK}}),
        "ships": await db.buyer_shipments.count_documents({"notes": MARK}),
        "items": await db.buyer_shipment_items.count_documents({"notes": MARK}),
        "layers": await db[fcl.LAYERS].count_documents({"id": {"$in": layer_ids}}),
        "cons": await db[fcl.CONSUMPTIONS].count_documents({"ref.source": MARK}),
        "snaps": await db.rahaza_hpp_snapshots.count_documents({"notes": MARK}),
    }


# ── Scenario runner: everything inside one event loop, results asserted after ──
async def _scenarios():
    db = _db()
    mat_id = f"T1MAT-{uuid.uuid4()}"
    sku = f"{MARK}-SKU"
    out = {}
    je_ids, layer_ids, ship_ids = [], [], []
    try:
        # ---- A: FIFO batch basis -------------------------------------------
        layer = await fcl.push_layer(
            db, material_id=mat_id, qty=10, unit_cost=UNIT_COST, breakdown=dict(BD),
            po_item={"sku": sku, "po_number": MARK}, ref={"type": MARK}, actor=USER)
        layer_ids.append(layer["id"])
        cons = await fcl.consume_fifo(db, material_id=mat_id, qty=4,
                                      ref={"source": MARK}, actor=USER)
        shp, item = await _mk_shipment(db, mat_id, sku, 4, fg_cogs=cons["cogs"],
                                      layers=cons["layers_used"])
        ship_ids.append(shp["id"])
        res_a = await post_cogs_on_buyer_dispatch(db, shp, [item], 1, USER)
        if res_a.get("je_id"):
            je_ids.append(res_a["je_id"])
        je_a = await db.rahaza_journal_entries.find_one(
            {"id": res_a.get("je_id")}, {"_id": 0}) if res_a.get("je_id") else None
        out["A"] = {"res": res_a, "je": je_a, "fg_cogs": cons["cogs"],
                    "layer_unit": layer["unit_cost"]}

        # ---- B: idempotency -------------------------------------------------
        res_b = await post_cogs_on_buyer_dispatch(db, shp, [item], 1, USER)
        n_je = await db.rahaza_journal_entries.count_documents(
            {"source_module": "buyer_dispatch",
             "source_ref": f"cogs_job:{shp['id']}:seq1",
             "status": {"$ne": "voided"}})
        out["B"] = {"res": res_b, "count": n_je}

        # ---- C: uncosted qty reported --------------------------------------
        layer2 = await fcl.push_layer(
            db, material_id=mat_id, qty=3, unit_cost=UNIT_COST, breakdown=dict(BD),
            po_item={"sku": sku, "po_number": MARK}, ref={"type": MARK}, actor=USER)
        layer_ids.append(layer2["id"])
        cons2 = await fcl.consume_fifo(db, material_id=mat_id, qty=12,
                                       ref={"source": MARK}, actor=USER)
        shp_c, item_c = await _mk_shipment(db, mat_id, sku, 12, fg_cogs=cons2["cogs"],
                                          layers=cons2["layers_used"],
                                          uncosted=cons2["uncosted_qty"])
        ship_ids.append(shp_c["id"])
        res_c = await post_cogs_on_buyer_dispatch(db, shp_c, [item_c], 1, USER)
        if res_c.get("je_id"):
            je_ids.append(res_c["je_id"])
        out["C"] = {"res": res_c, "cons": cons2}

        # ---- D: hpp_snapshot fallback --------------------------------------
        job_id = f"T1JOB-{uuid.uuid4()}"
        await db.rahaza_hpp_snapshots.insert_one({
            "id": str(uuid.uuid4()), "job_id": job_id, "notes": MARK,
            "qty_completed": 10, "material_cost": 30000, "labor_cost": 15000,
            "overhead_cost": 5000, "hpp_unit": 5000,
            "total_cost": 50000, "created_at": datetime.now(timezone.utc)})
        shp_d, item_d = await _mk_shipment(db, mat_id, sku, 10, job_id=job_id)
        ship_ids.append(shp_d["id"])
        res_d = await post_cogs_on_buyer_dispatch(db, shp_d, [item_d], 1, USER)
        if res_d.get("je_id"):
            je_ids.append(res_d["je_id"])
        je_d = await db.rahaza_journal_entries.find_one(
            {"id": res_d.get("je_id")}, {"_id": 0}) if res_d.get("je_id") else None
        out["D"] = {"res": res_d, "je": je_d}

        # ---- E: neither layers nor snapshot -> no invented journal ----------
        shp_e, item_e = await _mk_shipment(db, mat_id, sku, 5,
                                          job_id=f"T1JOB-{uuid.uuid4()}")
        ship_ids.append(shp_e["id"])
        res_e = await post_cogs_on_buyer_dispatch(db, shp_e, [item_e], 1, USER)
        n_e = await db.rahaza_journal_entries.count_documents(
            {"source_ref": f"cogs_job:{shp_e['id']}:seq1"})
        out["E"] = {"res": res_e, "count": n_e}

        # ---- F: mixed dispatch, one line FULLY uncosted (no layers at all) --
        layer3 = await fcl.push_layer(
            db, material_id=mat_id, qty=4, unit_cost=UNIT_COST, breakdown=dict(BD),
            po_item={"sku": sku, "po_number": MARK}, ref={"type": MARK}, actor=USER)
        layer_ids.append(layer3["id"])
        cons3 = await fcl.consume_fifo(db, material_id=mat_id, qty=4,
                                       ref={"source": MARK}, actor=USER)
        sid = str(uuid.uuid4())
        await db.buyer_shipments.insert_one({
            "id": sid, "shipment_number": f"{MARK}-F", "notes": MARK,
            "shipment_date": date.today().isoformat(),
            "created_at": datetime.now(timezone.utc)})
        ship_ids.append(sid)
        f1 = {"id": str(uuid.uuid4()), "shipment_id": sid, "sku": sku, "qty_shipped": 4,
              "notes": MARK, "dispatch_seq": 1, "fg_cogs": cons3["cogs"],
              "fg_cogs_layers": cons3["layers_used"], "fg_cogs_uncosted_qty": 0}
        f2 = {"id": str(uuid.uuid4()), "shipment_id": sid, "sku": f"{sku}-B",
              "qty_shipped": 10, "notes": MARK, "dispatch_seq": 1, "fg_cogs": 0.0,
              "fg_cogs_layers": [], "fg_cogs_uncosted_qty": 10}
        await db.buyer_shipment_items.insert_many([dict(f1), dict(f2)])
        shp_f = await db.buyer_shipments.find_one({"id": sid}, {"_id": 0})
        res_f = await post_cogs_on_buyer_dispatch(db, shp_f, [f1, f2], 1, USER)
        if res_f.get("je_id"):
            je_ids.append(res_f["je_id"])
        out["F"] = {"res": res_f}
    finally:
        out["cleanup"] = await _cleanup(db, je_ids, layer_ids, ship_ids)
    return out


@pytest.fixture(scope="module")
def SC():
    return run(_scenarios())


# ══════════════ FIFO batch COGS journal (routes/rahaza_posting) ══════════════
class TestFifoCogsJournal:

    def test_a_basis_is_fifo_batch_and_amount_equals_fg_cogs(self, SC):
        a = SC["A"]
        assert a["res"].get("ok") is True, a["res"]
        assert a["res"]["basis"] == "fifo_batch", a["res"]
        assert a["fg_cogs"] == 4 * UNIT_COST, a["fg_cogs"]
        assert round(float(a["res"]["amount"]), 2) == round(float(a["fg_cogs"]), 2)

    def test_a_journal_balanced_and_fg_credit_equals_total(self, SC):
        je = SC["A"]["je"]
        assert je is not None, "journal entry not found in DB"
        total = float(SC["A"]["res"]["amount"])
        assert round(je["total_debit"], 2) == round(je["total_credit"], 2) == round(total, 2)
        credits = [l for l in je["lines"] if float(l["credit"]) > 0]
        assert len(credits) == 1, credits
        assert round(float(credits[0]["credit"]), 2) == round(total, 2)
        assert je["status"] == "posted"
        assert je["source_module"] == "buyer_dispatch"

    def test_a_split_across_three_debit_accounts_from_breakdown(self, SC):
        je = SC["A"]["je"]
        debits = {l["account_code"]: float(l["debit"])
                  for l in je["lines"] if float(l["debit"]) > 0}
        assert len(debits) == 3, debits
        qty = 4
        expected = {
            "material": BD["material_cost"] * qty,
            "labor": (BD["sewing_cost"] + BD["permak_cost"]
                      + BD["internal_labor_cost"]) * qty,
            "overhead": BD["overhead_cost"] * qty,
        }
        got = sorted(round(v, 2) for v in debits.values())
        assert got == sorted(round(v, 2) for v in expected.values()), (debits, expected)
        assert round(sum(debits.values()), 2) == round(float(SC["A"]["res"]["amount"]), 2)

    def test_a_memo_states_the_cost_basis(self, SC):
        memo = SC["A"]["je"]["memo"]
        assert "batch" in memo.lower() or "fifo" in memo.lower(), memo

    def test_b_idempotent_single_journal(self, SC):
        b = SC["B"]
        assert b["res"].get("already_posted") is True, b["res"]
        assert b["res"].get("je_id") == SC["A"]["res"]["je_id"]
        assert b["count"] == 1, f"expected exactly 1 non-voided JE, got {b['count']}"

    def test_c_uncosted_qty_reported_with_note(self, SC):
        c = SC["C"]
        assert c["cons"]["uncosted_qty"] > 0, c["cons"]
        assert c["res"].get("ok") is True, c["res"]
        assert int(c["res"].get("uncosted_qty") or 0) == c["cons"]["uncosted_qty"]
        note = c["res"].get("note") or ""
        assert note and "COGS" in note, c["res"]

    def test_d_hpp_snapshot_fallback(self, SC):
        d = SC["D"]
        assert d["res"].get("ok") is True, d["res"]
        assert d["res"]["basis"] == "hpp_snapshot", d["res"]
        assert round(float(d["res"]["amount"]), 2) == 50000.0, d["res"]
        je = d["je"]
        assert round(je["total_debit"], 2) == round(je["total_credit"], 2) == 50000.0
        assert "perkiraan" in je["memo"].lower() or "hpp" in je["memo"].lower(), je["memo"]

    def test_e_no_layers_no_snapshot_means_no_journal(self, SC):
        e = SC["E"]
        assert e["res"].get("ok") is False, e["res"]
        assert e["res"].get("reason") == "zero_cogs", e["res"]
        assert e["count"] == 0, "a phantom Rp 0 journal was created"

    def test_f_fully_uncosted_line_must_still_be_disclosed(self, SC):
        """BUG (iter96): a shipment line that leaves with NO cost layer at all
        (fg_cogs == 0, fg_cogs_layers == []) is skipped by the `continue` in
        _fifo_cogs_for_dispatch BEFORE uncosted_qty is accumulated, so the
        journal understates COGS by 10 pcs with no `uncosted_qty` and no note."""
        f = SC["F"]["res"]
        assert f.get("ok") is True, f
        assert f["basis"] == "fifo_batch", f
        assert int(f.get("uncosted_qty") or 0) == 10, (
            f"10 pcs left the warehouse with no cost layer but uncosted_qty="
            f"{f.get('uncosted_qty')} and note={f.get('note')!r}")
        assert f.get("note"), "no human-readable warning for the uncosted qty"

    def test_z_no_test_artifacts_left_behind(self, SC):
        left = SC["cleanup"]
        assert not any(left.values()), left


# ══════════════ Regression: buyer shipment endpoints (HTTP) ══════════════
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"},
                      timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tk = r.json().get("access_token") or r.json().get("token")
    assert tk, r.json()
    return tk


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


class TestBuyerShipmentApiRegression:

    def test_list_buyer_shipments(self, client):
        r = client.get(f"{BASE_URL}/api/buyer-shipments", timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("data"))
        assert isinstance(rows, list), type(data)
        assert not any("_id" in (x or {}) for x in rows), "mongo _id leaked"
        TestBuyerShipmentApiRegression.rows = rows

    def test_detail_buyer_shipment_has_items(self, client):
        rows = getattr(TestBuyerShipmentApiRegression, "rows", None)
        if not rows:
            pytest.skip("no buyer shipments in DB to fetch detail for")
        sid = rows[0]["id"]
        r = client.get(f"{BASE_URL}/api/buyer-shipments/{sid}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("id") == sid
        assert "items" in d, list(d.keys())
        assert isinstance(d["items"], list)
        assert "_id" not in d

    def test_detail_unknown_id_returns_404(self, client):
        r = client.get(f"{BASE_URL}/api/buyer-shipments/{uuid.uuid4()}", timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"
