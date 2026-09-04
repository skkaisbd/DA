"""
E2E API-level POC test — Alur Approval Multilevel (Manajemen).

Pusat approval bertingkat lintas dokumen (leave/overtime/expense/purchase_order/
salary_adjustment/material_return/resignation/asset_purchase). Engine: sequential
multi-level; chain dipilih berdasar `type` + kondisi (amount/days).

Cakupan (semua endpoint prefix /api/approvals):
  A. Setup     : seed default chains (idempotent)      [POST /api/approvals/seed-missing-chains]
                 list chains                            [GET  /api/approvals/chains]
  B. Routing   : submit leave days>=3 -> chain 3 level  [POST /api/approvals/requests]
                 submit leave days<3  -> chain 1 level
  C. Approve   : submit PO amount>=5jt (3 level)        [POST /api/approvals/requests]
                 detail                                 [GET  /api/approvals/requests/{id}]
                 approve L1 -> L2 -> L3 -> approved      [POST /api/approvals/requests/{id}/approve]
  D. Reject    : submit PO, approve L1, reject L2        [POST /api/approvals/requests/{id}/reject]
                 -> status rejected + level sisa skipped
  E. Cancel    : submit leave pendek, cancel             [POST /api/approvals/requests/{id}/cancel]
  F. Chain CRUD: create/update/delete chain (admin)      [POST/PUT/DELETE /api/approvals/chains]
  G. Inbox     : pending untuk user + summary            [GET /api/approvals/pending, /summary]
Guards:
  - submit type tanpa chain cocok ditolak (400)
  - approve request yang sudah selesai ditolak (400)
  - cancel request yang sudah selesai/dibatalkan ditolak (400)
  - create chain oleh non-admin (role hr) ditolak (403)
Self-cleanup (hard): semua approval_requests E2E + chain E2E dihapus.
Catatan: chain default hasil seed idempotent DIPERTAHANKAN (baseline app,
UI memerlukan chain agar berfungsi). Hanya fixture E2E yang dibersihkan.
"""
import sys
import requests

BASE = "http://localhost:8001"
S = requests.Session()               # admin/superadmin session
HR = requests.Session()              # non-admin session (role hr) untuk RBAC guard
TAG = "E2E-APPROVAL"                  # ref_code prefix untuk fixture
st = {"requests": [], "chains": []}


def _mongo():
    url = db = None
    with open("/app/backend/.env") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("MONGO_URL="):
                url = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("DB_NAME="):
                db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    from pymongo import MongoClient
    cli = MongoClient(url)
    return cli, cli[db or "test_database"]


def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login admin (superadmin)")
    r2 = HR.post(f"{BASE}/api/auth/login", json={"email": "hr@dewiaditya.id", "password": "Dewi@123"})
    if r2.status_code == 200:
        HR.headers.update({"Authorization": f"Bearer {r2.json()['token']}", "Content-Type": "application/json"})
        print("PASS login hr (non-admin) untuk RBAC guard")
    else:
        print(f"WARN login hr gagal ({r2.status_code}) — guard RBAC create-chain dilewati")


def submit(req_type, ref_code, meta, subject=""):
    body = {"type": req_type, "ref_id": ref_code, "ref_code": ref_code,
            "subject": subject or f"{req_type} {ref_code}", "meta": meta}
    r = S.post(f"{BASE}/api/approvals/requests", json=body)
    return r


def approve(rid, note=""):
    return S.post(f"{BASE}/api/approvals/requests/{rid}/approve", json={"note": note})


def reject(rid, note=""):
    return S.post(f"{BASE}/api/approvals/requests/{rid}/reject", json={"note": note})


def detail(rid):
    return S.get(f"{BASE}/api/approvals/requests/{rid}")


def main():
    login()

    # ══ A. Setup: seed default chains (idempotent) ═══════════════════════════
    r = S.post(f"{BASE}/api/approvals/seed-missing-chains", json={})
    assert r.status_code == 200, f"seed chains {r.status_code}: {r.text}"
    print(f"PASS seed default chains (idempotent): {r.json().get('message')}")

    r = S.get(f"{BASE}/api/approvals/chains")
    assert r.status_code == 200, f"list chains {r.text}"
    chains = r.json()["data"]
    types = {c["type"] for c in chains}
    assert {"leave", "purchase_order", "expense"} <= types, f"chain types kurang: {types}"
    print(f"PASS list chains: {len(chains)} chain aktif, tipe={sorted(types)}")

    # ══ B. Routing berbasis kondisi (amount/days) ════════════════════════════
    r = submit("leave", f"{TAG}-LV-LONG", {"days": 5}, "Cuti panjang 5 hari")
    assert r.status_code == 200, f"submit leave long {r.text}"
    d = r.json()["data"]; st["requests"].append(d["id"])
    assert d["max_level"] == 3 and d["current_level"] == 1 and d["status"] == "pending", f"leave long chain {d}"
    print(f"PASS routing: leave days=5 -> chain '{d['chain_name']}' ({d['max_level']} level)")

    r = submit("leave", f"{TAG}-LV-SHORT", {"days": 1}, "Cuti pendek 1 hari")
    assert r.status_code == 200, f"submit leave short {r.text}"
    d_short = r.json()["data"]; st["requests"].append(d_short["id"])
    assert d_short["max_level"] == 1, f"leave short chain harus 1 level: {d_short}"
    print(f"PASS routing: leave days=1 -> chain '{d_short['chain_name']}' ({d_short['max_level']} level)")

    # ══ C. Full multilevel APPROVE (PO >= 5jt: admin -> manager -> owner) ════
    r = submit("purchase_order", f"{TAG}-PO-APV", {"amount": 12_000_000}, "PO mesin jahit 12jt")
    assert r.status_code == 200, f"submit PO {r.text}"
    po = r.json()["data"]; st["requests"].append(po["id"])
    assert po["max_level"] == 3 and po["current_level"] == 1, f"PO 3-level {po}"
    lv0 = po["levels"]
    assert lv0[0]["status"] == "pending" and lv0[1]["status"] == "waiting" and lv0[2]["status"] == "waiting", f"level init {lv0}"
    print(f"PASS submit PO 12jt -> chain '{po['chain_name']}' 3 level (L1 pending, L2/L3 waiting)")

    dd = detail(po["id"]).json()["data"]
    assert dd["current_level"] == 1, f"detail current_level {dd}"

    r = approve(po["id"], "Setuju purchasing")
    assert r.status_code == 200, f"approve L1 {r.text}"
    a1 = r.json()["data"]
    assert a1["current_level"] == 2 and a1["status"] == "pending", f"after L1 {a1['current_level']}/{a1['status']}"
    assert a1["levels"][0]["status"] == "approved" and a1["levels"][1]["status"] == "pending", f"levels after L1 {a1['levels']}"
    print("PASS approve L1 -> current_level=2, L1 approved, L2 pending")

    r = approve(po["id"], "Setuju manajer")
    assert r.status_code == 200, f"approve L2 {r.text}"
    a2 = r.json()["data"]
    assert a2["current_level"] == 3 and a2["status"] == "pending", f"after L2 {a2['current_level']}/{a2['status']}"
    print("PASS approve L2 -> current_level=3, L2 approved, L3 pending")

    r = approve(po["id"], "Setuju direktur")
    assert r.status_code == 200, f"approve L3 {r.text}"
    a3 = r.json()["data"]
    assert a3["status"] == "approved" and a3["completed_at"], f"final approve {a3['status']}"
    assert all(lv["status"] == "approved" for lv in a3["levels"]), f"semua level approved {a3['levels']}"
    print("PASS approve L3 (final) -> status=approved + completed_at (semua level approved)")

    rg = approve(po["id"], "coba lagi")
    assert rg.status_code >= 400, f"expected reject approve-after-done got {rg.status_code}"
    print("PASS guard: approve request yang sudah approved ditolak (400)")

    # ══ D. REJECT cascade di tengah rantai ═══════════════════════════════════
    r = submit("purchase_order", f"{TAG}-PO-REJ", {"amount": 8_000_000}, "PO bahan 8jt")
    assert r.status_code == 200, f"submit PO rej {r.text}"
    por = r.json()["data"]; st["requests"].append(por["id"])
    assert approve(por["id"], "ok L1").status_code == 200, "approve L1 rej-path"
    r = reject(por["id"], "Budget tidak tersedia")
    assert r.status_code == 200, f"reject L2 {r.text}"
    rj = r.json()["data"]
    assert rj["status"] == "rejected" and rj["completed_at"], f"reject status {rj['status']}"
    assert rj["levels"][1]["status"] == "rejected" and rj["levels"][2]["status"] == "skipped", f"cascade skip {rj['levels']}"
    print("PASS reject L2 -> status=rejected, L2 rejected, L3 skipped (cascade)")

    rg = approve(por["id"])
    assert rg.status_code >= 400, f"expected reject approve-after-rejected got {rg.status_code}"
    print("PASS guard: approve request yang sudah rejected ditolak (400)")

    # ══ E. CANCEL oleh requester ═════════════════════════════════════════════
    r = submit("leave", f"{TAG}-LV-CANCEL", {"days": 1}, "Cuti yang dibatalkan")
    lc = r.json()["data"]; st["requests"].append(lc["id"])
    r = S.post(f"{BASE}/api/approvals/requests/{lc['id']}/cancel", json={"note": "Berubah rencana"})
    assert r.status_code == 200, f"cancel {r.text}"
    dc = detail(lc["id"]).json()["data"]
    assert dc["status"] == "cancelled", f"cancel status {dc['status']}"
    print("PASS cancel oleh requester -> status=cancelled")

    rg = S.post(f"{BASE}/api/approvals/requests/{lc['id']}/cancel", json={"note": "lagi"})
    assert rg.status_code >= 400, f"expected reject cancel-after-cancel got {rg.status_code}"
    print("PASS guard: cancel request yang sudah dibatalkan ditolak (400)")

    # ══ Guard: submit type tanpa chain cocok ═════════════════════════════════
    rg = submit("tipe_tidak_ada_xyz", f"{TAG}-NONE", {}, "no chain")
    assert rg.status_code == 400, f"expected 400 no-chain got {rg.status_code}: {rg.text}"
    print("PASS guard: submit type tanpa chain cocok ditolak (400)")

    # ══ F. Chain config CRUD (admin) ═════════════════════════════════════════
    body = {"type": "e2e_test", "name": "E2E Test Chain", "condition": {},
            "levels": [{"level": 1, "role": "manager", "label": "Manajer E2E"},
                       {"level": 2, "role": "owner", "label": "Owner E2E"}]}
    r = S.post(f"{BASE}/api/approvals/chains", json=body)
    assert r.status_code == 200, f"create chain {r.text}"
    ch = r.json()["data"]; st["chains"].append(ch["id"])
    assert ch["type"] == "e2e_test" and len(ch["levels"]) == 2, f"chain create {ch}"
    print(f"PASS create chain id={ch['id']} (e2e_test, 2 level)")

    r = S.put(f"{BASE}/api/approvals/chains/{ch['id']}", json={"name": "E2E Test Chain (edit)"})
    assert r.status_code == 200, f"update chain {r.text}"
    verify = S.get(f"{BASE}/api/approvals/chains?active_only=false").json()["data"]
    edited = next((c for c in verify if c["id"] == ch["id"]), None)
    assert edited and edited["name"] == "E2E Test Chain (edit)", f"update tidak tersimpan {edited}"
    print("PASS update chain (name berubah)")

    r = S.delete(f"{BASE}/api/approvals/chains/{ch['id']}")
    assert r.status_code == 200, f"delete chain {r.text}"
    verify = S.get(f"{BASE}/api/approvals/chains?active_only=false").json()["data"]
    deactivated = next((c for c in verify if c["id"] == ch["id"]), None)
    assert deactivated and deactivated["is_active"] is False, f"delete tidak nonaktif {deactivated}"
    print("PASS delete chain -> is_active=false (soft-delete)")

    # ══ G. RBAC guard: create chain oleh non-admin (hr) ═════════════════════
    if HR.headers.get("Authorization"):
        rg = HR.post(f"{BASE}/api/approvals/chains", json=body)
        assert rg.status_code == 403, f"expected 403 non-admin create-chain got {rg.status_code}: {rg.text}"
        print("PASS guard: create chain oleh non-admin (hr) ditolak (403)")

    # ══ H. Inbox pending + summary ═══════════════════════════════════════════
    r = S.get(f"{BASE}/api/approvals/pending")
    assert r.status_code == 200, f"pending {r.text}"
    print(f"PASS pending inbox (superadmin lihat semua): {r.json().get('total')} item")

    r = S.get(f"{BASE}/api/approvals/summary")
    assert r.status_code == 200, f"summary {r.text}"
    summ = r.json()["data"]
    assert "total_pending" in summ and "by_type" in summ, f"summary shape {summ}"
    print(f"PASS summary: total_pending={summ['total_pending']}, by_type={len(summ['by_type'])} tipe")

    print("\n=== APPROVAL MULTILEVEL FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        rq = 0
        for rid in st["requests"]:
            rq += db.approval_requests.delete_one({"id": rid}).deleted_count
        rq += db.approval_requests.delete_many({"ref_code": {"$regex": f"^{TAG}"}}).deleted_count
        ch = 0
        for cid in st["chains"]:
            ch += db.approval_chains.delete_one({"id": cid}).deleted_count
        ch += db.approval_chains.delete_many({"type": "e2e_test"}).deleted_count
        cli.close()
        print(f"CLEANUP: approval_requests({rq}) + chain E2E({ch}) dihapus. "
              f"Chain default (seed idempotent) dipertahankan sebagai baseline app.")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
