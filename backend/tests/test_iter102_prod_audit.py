"""ITERATION 102 — Audit Portal Produksi: regresi 4 perbaikan + alur produksi
internal end-to-end (PO internal → job → material issue → progress → konsistensi
angka lintas endpoint → pengiriman buyer → penutupan PO).

Modul yang diuji:
- routes/production_control_tower.py  (GET /api/prod/control-tower*)
- routes/production_stage_tracking.py (GET /api/production-pos/{id}/stage-summary)
- routes/rahaza_setup.py              (POST /api/rahaza/setup/seed-sample)
- routes/production_pos.py            (POST /production-pos, /status, /fulfillment,
                                       /quantity-summary, /close, /close-short)
- routes/production_execution.py      (POST /production-jobs, /production-progress,
                                       GET /production-jobs, /production-tracking)
- routes/production_internal_adapter.py (draft-from-job, wip mirror)
- routes/rahaza_inventory_*           (MI submit/approve/confirm, material-receive)
- routes/buyer_shipment.py            (POST /buyer-shipments)
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

DEMO_PO = "79dbaa6b-e019-4d48-8938-3cd498aa4d37"
DEMO_JOB = "b6ed9cc7-88c2-4557-89e8-dca750d4b664"

STATE = {}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


class TestIter102:
    # ── 1. REGRESI FIX #1: Pusat Kendali membaca production_jobs ─────────────
    def test_01_control_tower(self, api):
        r = api.get(f"{BASE}/api/prod/control-tower", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        k = d["kpis"]
        STATE["ct_before"] = k
        assert k["active_wos"] >= 1, f"active_wos={k['active_wos']} (harus >=1)"
        assert k["total_target_qty"] >= 80, f"total_target_qty={k['total_target_qty']}"
        assert d["wo_status_breakdown"], "wo_status_breakdown kosong"

    def test_02_control_tower_wo_list(self, api):
        r = api.get(f"{BASE}/api/prod/control-tower/wo-list", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d["total"] >= 1 and d["items"], "wo-list kosong"
        demo = [i for i in d["items"] if i.get("po_id") == DEMO_PO]
        assert demo, f"job demo PO tidak muncul di wo-list; items={[i.get('wo_number') for i in d['items']]}"
        it = demo[0]
        for f in ("wo_number", "client_name", "qty", "qty_produced", "risk_status", "source"):
            assert f in it, f"field {f} hilang dari item wo-list"
        assert it["client_name"] == "Produksi Internal", it["client_name"]
        assert it["source"] == "internal", it["source"]
        assert it["qty"] == 80, f"qty={it['qty']} (harap 80)"
        assert "deadline" in it

        r2 = api.get(f"{BASE}/api/prod/control-tower/wo-list?source=internal", timeout=120)
        assert r2.status_code == 200, r2.text[:300]
        assert any(i.get("po_id") == DEMO_PO for i in r2.json()["items"])

        r3 = api.get(f"{BASE}/api/prod/control-tower/wo-list?source=maklon", timeout=120)
        assert r3.status_code == 200, r3.text[:300]
        assert not [i for i in r3.json()["items"] if i.get("po_id") == DEMO_PO], \
            "job internal bocor ke filter source=maklon"

    def test_03_control_tower_alerts(self, api):
        r = api.get(f"{BASE}/api/prod/control-tower/alerts", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        for f in ("total", "overdue", "at_risk", "cmt_pending_review"):
            assert f in d, f"field {f} hilang"
        assert isinstance(d["overdue"], list) and isinstance(d["at_risk"], list)

    # ── 2. REGRESI FIX #2: stage-summary PO demo ─────────────────────────────
    def test_04_stage_summary_demo_po(self, api):
        r = api.get(f"{BASE}/api/production-pos/{DEMO_PO}/stage-summary", timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        STATE["ss_before"] = d
        assert d["qty_ordered"] == 80, f"qty_ordered={d['qty_ordered']}"
        assert d["total_wo_qty"] == 80, f"total_wo_qty={d['total_wo_qty']}"
        assert d["wo_count"] == 1, f"wo_count={d['wo_count']}"
        assert d["wip_data_available"] is True

    # ── 3. REGRESI FIX #3: seed-sample idempotent & tidak bikin PO ganda ─────
    def test_05_seed_sample_idempotent(self, api):
        r = api.post(f"{BASE}/api/rahaza/setup/seed-sample", json={}, timeout=180)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:600]}"
        STATE["seed_resp"] = r.json()
        print("SEED RESPONSE:", str(r.json())[:1200])

        r2 = api.get(f"{BASE}/api/production-pos?business_type=internal&per_page=200", timeout=120)
        assert r2.status_code == 200, r2.text[:300]
        body = r2.json()
        pos = body if isinstance(body, list) else body.get("data") or body.get("items") or []
        demo_nums = [p["po_number"] for p in pos if str(p.get("po_number", "")).startswith("PO-INT-DEMO-")]
        print("DEMO PO NUMBERS:", demo_nums)
        assert len(demo_nums) == len(set(demo_nums)), f"nomor PO demo duplikat: {demo_nums}"
        assert len(demo_nums) <= 1, f"seed-sample membuat PO demo ganda: {demo_nums}"

    # ── 4. ALUR PENUH: (a) buat PO internal baru ─────────────────────────────
    def test_06_create_internal_po(self, api):
        rb = api.get(f"{BASE}/api/rahaza/boms?per_page=100", timeout=120)
        assert rb.status_code == 200, f"boms {rb.status_code}: {rb.text[:300]}"
        bb = rb.json()
        boms = bb if isinstance(bb, list) else bb.get("data") or bb.get("items") or []
        boms = [b for b in boms if b.get("model_id") and b.get("size_id")
                and (b.get("is_active") is not False)]
        assert boms, "tidak ada BOM aktif — MI draft-from-job pasti gagal"
        bom = boms[0]
        STATE["model_id"], STATE["size_id"] = bom["model_id"], bom["size_id"]

        # Penomoran PO Internal disetel MANUAL: pola PO-INT-{YYYY}{MM}-{SEQ:4}
        po_number = f"PO-INT-{date.today():%Y%m}-{random.randint(9000, 9899)}"
        payload = {
            "po_number": po_number,
            "business_type": "internal",
            "customer_name": "TEST_ITER102 Buyer",
            "po_date": date.today().isoformat(),
            "deadline": (date.today() + timedelta(days=20)).isoformat(),
            "delivery_deadline": (date.today() + timedelta(days=25)).isoformat(),
            "notes": "TEST_ITER102 audit produksi internal",
            "items": [{"model_id": bom["model_id"], "size_id": bom["size_id"], "qty": 25}],
        }
        r = api.post(f"{BASE}/api/production-pos", json=payload, timeout=120)
        assert r.status_code == 201, f"create PO {r.status_code}: {r.text[:600]}"
        po = r.json()
        STATE["po_id"] = po["id"]
        STATE["po_number"] = po["po_number"]
        assert po["status"] == "Draft", po["status"]
        assert len(po["items"]) == 1
        assert po["items"][0]["qty"] == 25 and po["items"][0]["qty_ordered"] == 25
        STATE["po_item_id"] = po["items"][0]["id"]
        print("PO created:", po["po_number"], po["id"])

        g = api.get(f"{BASE}/api/production-pos/{po['id']}", timeout=60)
        assert g.status_code == 200 and g.json()["po_number"] == po["po_number"]

    # ── (b) Confirmed → job ──────────────────────────────────────────────────
    def test_07_confirm_po_and_create_job(self, api):
        pid = STATE["po_id"]
        r = api.post(f"{BASE}/api/production-pos/{pid}/status",
                     json={"status": "Confirmed"}, timeout=60)
        assert r.status_code == 200, f"status Confirmed {r.status_code}: {r.text[:400]}"

        r = api.post(f"{BASE}/api/production-jobs", json={"po_id": pid}, timeout=180)
        assert r.status_code == 201, f"create job {r.status_code}: {r.text[:600]}"
        job = r.json()
        STATE["job_id"] = job["id"]
        assert job["business_type"] == "internal"
        assert job["vendor_name"] == "Produksi Internal"
        assert len(job["items"]) == 1 and job["items"][0]["available_qty"] == 25
        STATE["job_item_id"] = job["items"][0]["id"]
        mi = job.get("material_issue_draft")
        print("AUTO MI DRAFT:", str(mi)[:500])
        assert isinstance(mi, dict) and not mi.get("error"), f"auto MI draft gagal: {mi}"
        STATE["mi_id"] = mi.get("id")

        gi = api.get(f"{BASE}/api/production-job-items?job_id={STATE['job_id']}", timeout=60)
        assert gi.status_code == 200, gi.text[:300]
        items = gi.json()
        items = items if isinstance(items, list) else items.get("data") or items.get("items") or []
        assert len(items) == 1, f"job items = {len(items)}"

        # PO auto-moved to In Production by adapter
        g = api.get(f"{BASE}/api/production-pos/{pid}", timeout=60)
        STATE["po_status_after_job"] = g.json().get("status")
        assert g.json()["status"] == "In Production", g.json()["status"]

    # ── (c) Material Issue: draft → submit → approve(=issued) ────────────────
    def test_08_material_issue_to_issued(self, api):
        r = api.post(f"{BASE}/api/rahaza/material-issues/draft-from-job",
                     json={"job_id": STATE["job_id"]}, timeout=120)
        assert r.status_code == 200, f"draft-from-job {r.status_code}: {r.text[:600]}"
        mi = r.json()
        STATE["mi_id"] = mi["id"]
        assert mi["job_id"] == STATE["job_id"]
        assert mi["status"] == "draft", mi["status"]
        assert mi["items"], "MI tanpa item"
        print("MI:", mi["mi_number"], "items:", len(mi["items"]), "missing:", mi.get("missing_codes"))

        # lokasi gudang
        rl = api.get(f"{BASE}/api/rahaza/locations", timeout=60)
        assert rl.status_code == 200, rl.text[:300]
        locs = rl.json()
        locs = locs if isinstance(locs, list) else locs.get("data") or locs.get("items") or []
        assert locs, "tidak ada lokasi gudang (rahaza/locations kosong)"
        loc_id = locs[0]["id"]
        STATE["loc_id"] = loc_id

        # set lokasi tiap item MI
        items = [{**it, "location_id": loc_id} for it in mi["items"]]
        ru = api.put(f"{BASE}/api/rahaza/material-issues/{mi['id']}",
                     json={"items": items}, timeout=60)
        assert ru.status_code == 200, f"PUT MI {ru.status_code}: {ru.text[:400]}"

        # pastikan stok cukup (top-up)
        for it in items:
            need = float(it.get("qty_required") or 0) + 10
            rr = api.post(f"{BASE}/api/rahaza/material-receive",
                          json={"material_id": it["material_id"], "location_id": loc_id,
                                "qty": need, "unit_cost": 10000,
                                "notes": "TEST_ITER102 top-up"}, timeout=120)
            assert rr.status_code in (200, 201), f"material-receive {rr.status_code}: {rr.text[:400]}"

        rs = api.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/submit", json={}, timeout=60)
        assert rs.status_code == 200, f"submit {rs.status_code}: {rs.text[:400]}"
        assert rs.json()["status"] == "pending_approval", rs.json()["status"]

        ra = api.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/approve", json={}, timeout=180)
        assert ra.status_code == 200, f"approve {ra.status_code}: {ra.text[:600]}"
        out = ra.json()
        assert out["status"] == "issued", f"status setelah approve = {out['status']} (harap issued)"

    # ── (d) progress 10 pcs + WIP mirror ────────────────────────────────────
    def test_09_production_progress(self, api):
        re_ = api.get(f"{BASE}/api/rahaza/employees?per_page=50", timeout=60)
        assert re_.status_code == 200, re_.text[:300]
        emps = re_.json()
        emps = emps if isinstance(emps, list) else emps.get("data") or emps.get("items") or []
        assert emps, "rahaza_employees kosong"
        rp = api.get(f"{BASE}/api/rahaza/processes?per_page=50", timeout=60)
        assert rp.status_code == 200, rp.text[:300]
        procs = rp.json()
        procs = procs if isinstance(procs, list) else procs.get("data") or procs.get("items") or []
        procs = sorted([p for p in procs if p.get("active") is not False],
                       key=lambda p: p.get("order_seq") or 0)
        assert procs, "rahaza_processes kosong"
        # ITER-103: tahap dikenali dari nama/process_type dan event pada proses
        # REWORK tidak lagi dihitung sebagai sewing_output ⇒ progres uji harus
        # dicatat pada proses SEWING (bukan proses terakhir yang bisa Rework).
        sew = next((p for p in procs
                    if any(w in f"{p.get('process_type') or ''} {p.get('name') or ''}".lower()
                           for w in ("jahit", "sew"))), procs[-1])
        STATE["last_proc"] = sew

        r = api.post(f"{BASE}/api/production-progress", json={
            "job_id": STATE["job_id"], "job_item_id": STATE["job_item_id"],
            "completed_quantity": 10, "operator_id": emps[0]["id"],
            "process_id": sew["id"], "notes": "TEST_ITER102",
        }, timeout=180)
        assert r.status_code == 201, f"progress {r.status_code}: {r.text[:600]}"
        assert r.json()["new_total"] == 10, r.json()

    # ── (d/e) konsistensi angka lintas endpoint ─────────────────────────────
    def test_10_cross_endpoint_consistency(self, api):
        pid, jid = STATE["po_id"], STATE["job_id"]
        numbers = {}

        r = api.get(f"{BASE}/api/production-jobs?po_id={pid}", timeout=120)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        jobs = body if isinstance(body, list) else body.get("data") or body.get("items") or []
        mine = [j for j in jobs if j["id"] == jid]
        assert mine, "job tidak ditemukan di GET /production-jobs"
        numbers["production_jobs.total_produced"] = mine[0].get("total_produced")

        r = api.get(f"{BASE}/api/production-tracking", timeout=180)
        assert r.status_code == 200, f"tracking {r.status_code}: {r.text[:300]}"
        tr = r.json()
        rows = tr if isinstance(tr, list) else tr.get("data") or tr.get("items") or tr.get("groups") or []
        STATE["tracking_raw_keys"] = list(tr.keys()) if isinstance(tr, dict) else "list"
        tot = None
        grp_total = None
        for g in rows if isinstance(rows, list) else []:
            for j in (g.get("jobs") or []):
                if j.get("id") == jid:
                    # NOTE: field per-job di /production-tracking = `produced_qty`
                    tot = j.get("produced_qty")
                    grp_total = g.get("total_produced")
        numbers["production_tracking.job.produced_qty"] = tot
        numbers["production_tracking.group.total_produced"] = grp_total

        r = api.get(f"{BASE}/api/prod/control-tower", timeout=180)
        assert r.status_code == 200, r.text[:300]
        numbers["control_tower.total_produced_qty"] = r.json()["kpis"]["total_produced_qty"]
        STATE["ct_after"] = r.json()["kpis"]

        r = api.get(f"{BASE}/api/production-pos/{pid}/quantity-summary", timeout=120)
        assert r.status_code == 200, f"quantity-summary {r.status_code}: {r.text[:400]}"
        qs = r.json()
        numbers["quantity_summary"] = {k: v for k, v in qs.items()
                                       if "produc" in k.lower() or "qty" in k.lower()}
        STATE["qs"] = qs

        r = api.get(f"{BASE}/api/production-pos/{pid}/fulfillment", timeout=120)
        assert r.status_code == 200, f"fulfillment {r.status_code}: {r.text[:400]}"
        ff = r.json()
        numbers["fulfillment"] = {k: v for k, v in ff.items() if isinstance(v, (int, float))}
        STATE["ff"] = ff

        r = api.get(f"{BASE}/api/production-pos/{pid}/stage-summary", timeout=120)
        assert r.status_code == 200, f"stage-summary {r.status_code}: {r.text[:400]}"
        ss = r.json()
        numbers["stage_summary"] = {"sewing_output": ss["stage_qty"]["sewing_output"],
                                   "progress_pct": ss.get("progress_pct"),
                                   "qty_ordered": ss.get("qty_ordered"),
                                   "total_wo_qty": ss.get("total_wo_qty")}
        STATE["ss_new"] = ss
        print("CROSS-ENDPOINT NUMBERS:", numbers)
        STATE["numbers"] = numbers

        assert numbers["production_jobs.total_produced"] == 10, numbers
        assert ss["stage_qty"]["sewing_output"] == 10, f"sewing_output={ss['stage_qty']['sewing_output']}"
        assert ss["progress_pct"] > 0, ss["progress_pct"]
        assert ss["qty_ordered"] == 25 and ss["total_wo_qty"] == 25, numbers["stage_summary"]
        assert STATE["ct_after"]["total_produced_qty"] >= STATE["ct_before"]["total_produced_qty"] + 10, \
            (STATE["ct_before"]["total_produced_qty"], STATE["ct_after"]["total_produced_qty"])
        if tot is not None:
            assert tot == 10, f"tracking produced_qty={tot}"
        else:
            pytest.fail("job tidak ditemukan di /api/production-tracking")

        # quantity-summary harus melaporkan produced=10 (SSOT sama)
        qtot = (STATE["qs"].get("totals") or {})
        assert qtot.get("produced") == 10, f"quantity-summary totals={qtot}"
        # KONSISTENSI: fulfillment melaporkan total_received/shipped 0 padahal
        # produksi internal 10 pcs — dicatat sebagai temuan (lihat report).
        numbers["fulfillment_vs_produced_mismatch"] = {
            "produced": qtot.get("produced"), "fulfillment_received": STATE["ff"].get("total_received")}

    # ── (f) pengiriman buyer ────────────────────────────────────────────────
    def test_11_buyer_shipment(self, api):
        # a) daftar kekurangan kirim harus memuat PO internal yang sudah produksi
        ro = api.get(f"{BASE}/api/buyer-dispatch-outstanding?po_id={STATE['po_id']}", timeout=120)
        assert ro.status_code == 200, ro.text[:300]
        print("DISPATCH OUTSTANDING (internal PO):", str(ro.json())[:400])
        # b) kapasitas kirim per po_item
        rc = api.get(f"{BASE}/api/buyer-dispatch-capacity?po_item_ids={STATE['po_item_id']}", timeout=120)
        assert rc.status_code == 200, rc.text[:300]
        print("DISPATCH CAPACITY (po_item):", str(rc.json())[:400])

        payload = {
            "po_id": STATE["po_id"],
            "shipment_date": date.today().isoformat(),
            "items": [{"po_item_id": STATE["po_item_id"], "qty_shipped": 10}],
        }
        r = api.post(f"{BASE}/api/buyer-shipments", json=payload, timeout=120)
        STATE["bs_status"] = r.status_code
        STATE["bs_body"] = r.text[:600]
        print("BUYER SHIPMENT:", r.status_code, r.text[:600])
        assert r.status_code != 500, f"500 pada POST /buyer-shipments: {r.text[:600]}"
        if r.status_code in (200, 201):
            STATE["bs_id"] = r.json().get("id")
            f = api.get(f"{BASE}/api/production-pos/{STATE['po_id']}/fulfillment", timeout=120)
            assert f.status_code == 200, f.text[:300]
            print("FULFILLMENT AFTER SHIPMENT:", str(f.json())[:600])
        else:
            pytest.fail(f"buyer shipment untuk PO internal tertolak: {r.status_code} {r.text[:400]}")

    # ── (g) penutupan PO ────────────────────────────────────────────────────
    def test_12_po_closure_state_machine(self, api):
        pid = STATE["po_id"]
        r = api.post(f"{BASE}/api/production-pos/{pid}/close",
                     json={"close_reason": "TEST_ITER102"}, timeout=120)
        print("CLOSE from In Production:", r.status_code, r.text[:400])
        assert r.status_code != 500, r.text[:400]
        assert r.status_code == 400, f"close dari 'In Production' seharusnya ditolak, dapat {r.status_code}"

        r = api.post(f"{BASE}/api/production-pos/{pid}/status",
                     json={"status": "Production Complete"}, timeout=60)
        print("status → Production Complete:", r.status_code, r.text[:300])
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"

        r = api.post(f"{BASE}/api/production-pos/{pid}/close-short",
                     json={"closed_reason": "mutual_agreement",
                           "notes": "TEST_ITER102 sisa tidak diproduksi"}, timeout=120)
        print("CLOSE-SHORT:", r.status_code, r.text[:500])
        assert r.status_code != 500, r.text[:500]
        assert r.status_code in (200, 201), f"close-short gagal: {r.status_code} {r.text[:400]}"
        g = api.get(f"{BASE}/api/production-pos/{pid}", timeout=60)
        assert g.json()["status"] == "Closed Short", g.json()["status"]
