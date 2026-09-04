"""ITERATION 103 — Dispatch buyer untuk PO INTERNAL + Pusat Kendali/stage-summary.

Modul yang diuji:
- core/dispatch_capacity.py            (_apply_internal_produced, _shippable, outstanding)
- routes/buyer_shipment.py             (POST /buyer-shipments internal tanpa source_receipt_ids,
                                        /buyer-dispatch-capacity, /buyer-dispatch-outstanding)
- routes/production_maklon_bridge.py   (compute_po_fulfillment basis='produced')
- routes/production_pos.py             (close_po_short, quantity-summary)
- routes/production_control_tower.py   (all_active_wos, kpis.unknown_deadline)
- routes/production_stage_tracking.py  (by_process, klasifikasi tahap, rework != sewing)
- routes/rahaza_setup.py               (seed-sample messages idempotent)
"""
import os
import random
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"

EXISTING_INT_PO = "d4384a3a-031d-482b-9364-06f2b87561ea"  # PO-INT-202609-9023
PRODUCED = 10
ORDERED = 25

STATE = {}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _list(body):
    return body if isinstance(body, list) else (body.get("data") or body.get("items") or [])


class TestA_InternalDispatchFlow:
    """A1/A2/A4: alur produksi internal → dispatch buyer."""

    # ── A1.a buat PO internal + job + MI issued + progress 10 ────────────────
    def test_01_setup_internal_po_produced_10(self, api):
        rb = api.get(f"{BASE}/api/rahaza/boms?per_page=100", timeout=120)
        assert rb.status_code == 200, rb.text[:300]
        boms = [b for b in _list(rb.json())
                if b.get("model_id") and b.get("size_id") and b.get("is_active") is not False]
        assert boms, "tidak ada BOM aktif"
        bom = boms[0]

        po_number = f"PO-INT-{date.today():%Y%m}-{random.randint(9000, 9899)}"
        payload = {
            "po_number": po_number,
            "business_type": "internal",
            "customer_name": "TEST_ITER103 Buyer",
            "po_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=20)).isoformat(),
            "delivery_deadline": (date.today() + timedelta(days=25)).isoformat(),
            "notes": "TEST_ITER103 dispatch internal",
            "items": [{"model_id": bom["model_id"], "size_id": bom["size_id"], "qty": ORDERED}],
        }
        r = api.post(f"{BASE}/api/production-pos", json=payload, timeout=120)
        assert r.status_code == 201, f"create PO {r.status_code}: {r.text[:600]}"
        po = r.json()
        STATE.update(po_id=po["id"], po_number=po["po_number"],
                     po_item_id=po["items"][0]["id"])
        assert po["items"][0]["qty_ordered"] == ORDERED

        r = api.post(f"{BASE}/api/production-pos/{po['id']}/status",
                     json={"status": "Confirmed"}, timeout=60)
        assert r.status_code == 200, r.text[:400]

        r = api.post(f"{BASE}/api/production-jobs", json={"po_id": po["id"]}, timeout=180)
        assert r.status_code == 201, f"create job {r.status_code}: {r.text[:600]}"
        job = r.json()
        STATE.update(job_id=job["id"], job_item_id=job["items"][0]["id"])
        assert job["business_type"] == "internal"
        mi = job.get("material_issue_draft")
        assert isinstance(mi, dict) and not mi.get("error"), f"auto MI draft gagal: {mi}"

        # MI: draft → lokasi → top-up stok → submit → approve(issued)
        r = api.post(f"{BASE}/api/rahaza/material-issues/draft-from-job",
                     json={"job_id": job["id"]}, timeout=120)
        assert r.status_code == 200, r.text[:600]
        mi = r.json()
        rl = api.get(f"{BASE}/api/rahaza/locations", timeout=60)
        locs = _list(rl.json())
        assert locs, "rahaza/locations kosong"
        loc_id = locs[0]["id"]
        items = [{**it, "location_id": loc_id} for it in mi["items"]]
        ru = api.put(f"{BASE}/api/rahaza/material-issues/{mi['id']}",
                     json={"items": items}, timeout=60)
        assert ru.status_code == 200, ru.text[:400]
        for it in items:
            rr = api.post(f"{BASE}/api/rahaza/material-receive",
                          json={"material_id": it["material_id"], "location_id": loc_id,
                                "qty": float(it.get("qty_required") or 0) + 10,
                                "unit_cost": 10000, "notes": "TEST_ITER103 top-up"}, timeout=120)
            assert rr.status_code in (200, 201), rr.text[:300]
        rs = api.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/submit", json={}, timeout=60)
        assert rs.status_code == 200, rs.text[:400]
        ra = api.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/approve", json={}, timeout=180)
        assert ra.status_code == 200, ra.text[:600]
        assert ra.json()["status"] == "issued", ra.json()["status"]

        # progress 10 pcs pada proses SEWING (bukan rework) agar stage-summary benar
        emps = _list(api.get(f"{BASE}/api/rahaza/employees?per_page=50", timeout=60).json())
        procs = [p for p in _list(api.get(f"{BASE}/api/rahaza/processes?per_page=50",
                                          timeout=60).json()) if p.get("active") is not False]
        assert emps and procs
        sew = next((p for p in procs
                    if any(w in f"{p.get('process_type') or ''} {p.get('name') or ''}".lower()
                           for w in ("jahit", "sew"))), procs[0])
        STATE["proc"] = sew
        r = api.post(f"{BASE}/api/production-progress", json={
            "job_id": job["id"], "job_item_id": STATE["job_item_id"],
            "completed_quantity": PRODUCED, "operator_id": emps[0]["id"],
            "process_id": sew["id"], "notes": "TEST_ITER103"}, timeout=180)
        assert r.status_code == 201, f"progress {r.status_code}: {r.text[:600]}"
        assert r.json()["new_total"] == PRODUCED, r.json()
        print("SETUP OK:", STATE["po_number"], "proses:", sew.get("name"))

    # ── A1.b kapasitas kirim dari hasil produksi internal ────────────────────
    def test_02_dispatch_capacity_internal(self, api):
        r = api.get(f"{BASE}/api/buyer-dispatch-capacity"
                    f"?po_item_ids={STATE['po_item_id']}&with_fg_stock=1", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        print("CAPACITY:", str(d)[:600])
        it = d["items"][0]
        assert it["internal_produced"] == PRODUCED, it
        assert it["source"] == "internal", it
        assert it["shippable"] == PRODUCED, it
        assert it["dispatched"] == 0, it
        assert d["totals"]["internal_produced"] == PRODUCED, d["totals"]
        STATE["sku"] = it.get("sku")
        STATE["fg_stock"] = it.get("fg_stock")

    # ── A1.c daftar kekurangan kirim memuat item PO internal ─────────────────
    def test_03_dispatch_outstanding_internal(self, api):
        r = api.get(f"{BASE}/api/buyer-dispatch-outstanding?po_id={STATE['po_id']}", timeout=180)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        rows = body.get("items") if isinstance(body, dict) else body
        mine = [x for x in rows if x.get("po_item_id") == STATE["po_item_id"]]
        assert mine, f"item PO internal tidak muncul di outstanding: {str(body)[:400]}"
        assert mine[0]["shippable"] == PRODUCED, mine[0]

    # ── A2 pagar kapasitas: 11 > produced 10 ─────────────────────────────────
    def test_04_over_capacity_rejected(self, api):
        r = api.post(f"{BASE}/api/buyer-shipments", json={
            "po_id": STATE["po_id"], "receiver_type": "buyer",
            "shipment_date": date.today().isoformat(),
            "items": [{"po_item_id": STATE["po_item_id"], "sku": STATE.get("sku"),
                       "qty_shipped": PRODUCED + 1}]}, timeout=120)
        assert r.status_code == 400, f"harus 400, dapat {r.status_code}: {r.text[:400]}"
        assert "melebihi qty diproduksi" in r.text, r.text[:400]

    # ── A1.d surat jalan buyer TANPA source_receipt_ids ──────────────────────
    def test_05_create_buyer_shipment_internal(self, api):
        payload = {"po_id": STATE["po_id"], "receiver_type": "buyer",
                   "shipment_date": date.today().isoformat(),
                   "items": [{"po_item_id": STATE["po_item_id"], "sku": STATE.get("sku"),
                              "qty_shipped": PRODUCED}]}
        r = api.post(f"{BASE}/api/buyer-shipments", json=payload, timeout=180)
        print("SHIPMENT ATTEMPT 1:", r.status_code, r.text[:500])
        if r.status_code == 400 and "Stok FG" in r.text:
            # scan-in pending inbound FG lalu ulangi (pagar stok FG yang benar)
            rp = api.get(f"{BASE}/api/wms/pending?type=inbound&status=pending&per_page=200",
                         timeout=120)
            assert rp.status_code == 200, rp.text[:300]
            pend = [p for p in _list(rp.json())
                    if (p.get("sku") or p.get("material_code")) == STATE.get("sku")]
            print("PENDING FG:", len(pend))
            for p in pend[:5]:
                rs = api.post(f"{BASE}/api/wms/pending/{p['id']}/scan-in", json={}, timeout=120)
                print("scan-in", p["id"], rs.status_code, rs.text[:200])
            r = api.post(f"{BASE}/api/buyer-shipments", json=payload, timeout=180)
            print("SHIPMENT ATTEMPT 2:", r.status_code, r.text[:500])
        assert r.status_code in (200, 201), f"dispatch internal ditolak: {r.status_code} {r.text[:500]}"
        sh = r.json()
        STATE["shipment_id"] = sh.get("id")
        assert (sh.get("business_type") or "internal") == "internal", sh.get("business_type")
        assert not (sh.get("source_receipt_ids") or []), sh.get("source_receipt_ids")

    # ── A2.b kapasitas setelah kirim ─────────────────────────────────────────
    def test_06_capacity_after_shipment(self, api):
        r = api.get(f"{BASE}/api/buyer-dispatch-capacity?po_item_ids={STATE['po_item_id']}",
                    timeout=120)
        assert r.status_code == 200, r.text[:300]
        it = r.json()["items"][0]
        assert it["dispatched"] == PRODUCED, it
        assert it["shippable"] == 0, it

    # ── A4 fulfillment basis produced ────────────────────────────────────────
    def test_07_fulfillment_internal_basis_produced(self, api):
        r = api.get(f"{BASE}/api/production-pos/{STATE['po_id']}/fulfillment", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print("FULFILLMENT:", str(d)[:500])
        assert d["basis"] == "produced", d.get("basis")
        assert d["total_produced"] == PRODUCED, d
        assert d["total_fulfilled"] == PRODUCED, d
        assert d["qty_short"] == ORDERED - PRODUCED, d
        assert d["qty_short_pct"] == 60.0, d

    # ── A4.b close-short ─────────────────────────────────────────────────────
    def test_08_close_short_internal(self, api):
        r = api.post(f"{BASE}/api/production-pos/{STATE['po_id']}/status",
                     json={"status": "Production Complete"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        r = api.post(f"{BASE}/api/production-pos/{STATE['po_id']}/close-short",
                     json={"closed_reason": "deadline_expired",
                           "notes": "TEST_ITER103"}, timeout=180)
        assert r.status_code in (200, 201), f"close-short {r.status_code}: {r.text[:500]}"
        d = r.json()
        print("CLOSE-SHORT:", str(d)[:500])
        assert d["qty_produced"] == PRODUCED, d
        assert d["qty_fulfilled"] == PRODUCED, d
        assert d["qty_short"] == ORDERED - PRODUCED, d
        assert d["qty_short_pct"] == 60.0, d
        g = api.get(f"{BASE}/api/production-pos/{STATE['po_id']}", timeout=60)
        assert g.json()["status"] == "Closed Short", g.json()["status"]


class TestB_MaklonUnchanged:
    """A3: PO maklon tetap wajib source_receipt_ids[]."""

    def test_09_maklon_requires_source_receipts(self, api):
        r = api.get(f"{BASE}/api/production-pos?business_type=maklon&per_page=50", timeout=120)
        assert r.status_code == 200, r.text[:300]
        pos = _list(r.json())
        target = None
        for p in pos:
            g = api.get(f"{BASE}/api/production-pos/{p['id']}", timeout=60)
            if g.status_code == 200 and (g.json().get("items") or []):
                target = g.json()
                break
        if not target:
            # DB tidak punya PO maklon — buat satu PO maklon uji (TEST_)
            cr = api.post(f"{BASE}/api/production-pos", json={
                "po_number": f"PO-MKL-{date.today():%Y%m}-{random.randint(9000, 9899)}",
                "business_type": "maklon",
                "customer_name": "TEST_ITER103 Maklon Buyer",
                "po_date": date.today().isoformat(),
                "deadline": (date.today() + timedelta(days=20)).isoformat(),
                "notes": "TEST_ITER103 maklon guard",
                "items": [{"product_name": "TEST_ITER103 Kaos", "sku": "TEST-ITER103-MKL",
                           "size": "M", "color": "Hitam", "qty": 5}]}, timeout=120)
            assert cr.status_code == 201, f"create PO maklon {cr.status_code}: {cr.text[:500]}"
            target = cr.json()
            STATE["maklon_po_id"] = target["id"]
        assert target.get("items"), "PO maklon tanpa item"
        r = api.post(f"{BASE}/api/buyer-shipments", json={
            "po_id": target["id"], "receiver_type": "buyer",
            "shipment_date": date.today().isoformat(),
            "items": [{"po_item_id": target["items"][0]["id"], "qty_shipped": 1}]}, timeout=120)
        assert r.status_code == 400, f"harus 400, dapat {r.status_code}: {r.text[:400]}"
        assert "source_receipt_ids" in r.text, r.text[:400]


class TestC_ExistingPOandReports:
    """A5 / B1 / B2 / B3."""

    # A5 quantity-summary PO internal existing
    def test_10_quantity_summary_existing_internal(self, api):
        r = api.get(f"{BASE}/api/production-pos/{EXISTING_INT_PO}/quantity-summary", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        print("QUANTITY SUMMARY:", str(d)[:700])
        it = (d.get("items") or [])[0]
        assert it["received_qty"] == 25, it
        assert it["available_qty"] == 25, it
        assert (d.get("totals") or {}).get("produced") == 10, d.get("totals")

    # B1 control tower
    def test_11_control_tower_all_wos(self, api):
        r = api.get(f"{BASE}/api/prod/control-tower?days_window=7", timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "all_active_wos" in d, list(d.keys())
        assert "unknown_deadline" in d["kpis"], d["kpis"]
        assert len(d["all_active_wos"]) == d["kpis"]["active_wos"], \
            (len(d["all_active_wos"]), d["kpis"]["active_wos"])
        print("CT kpis:", d["kpis"])

    # B2 stage-summary by_process + rework bukan sewing
    def test_12_stage_summary_by_process(self, api):
        r = api.get(f"{BASE}/api/production-pos/{EXISTING_INT_PO}/stage-summary", timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        bp = d.get("by_process")
        assert isinstance(bp, list) and bp, f"by_process kosong: {str(d)[:400]}"
        for row in bp:
            assert {"name", "stage", "qty"} <= set(row.keys()), row
        expect = {"cutting": "cutting", "jahit (cmt)": "sewing", "finishing": "finishing",
                  "qc final": "qc", "packing": "packing", "rework/revisi": "rework"}
        got = {(row.get("name") or "").strip().lower(): row.get("stage") for row in bp}
        for name, stage in expect.items():
            if name in got:
                assert got[name] == stage, f"{name} → {got[name]} (harap {stage})"
        rework = [row for row in bp if row.get("stage") == "rework"]
        assert rework and rework[0]["qty"] == 10, rework
        assert d["stage_qty"]["sewing_output"] == 0, d["stage_qty"]

    # B3 seed-sample messages
    def test_13_seed_sample_messages(self, api):
        r = api.post(f"{BASE}/api/rahaza/setup/seed-sample", json={}, timeout=240)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        d = r.json()
        msgs = " | ".join(d.get("messages") or [])
        print("SEED:", d.get("message"), "||", msgs[:600])
        assert "PO Internal demo sudah ada:" in msgs and "PO-INT-DEMO-" in msgs, msgs[:600]
        assert "Sample data sudah lengkap" in (d.get("message") or ""), d.get("message")
