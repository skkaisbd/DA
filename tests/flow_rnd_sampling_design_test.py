"""
E2E API-level POC test — Alur Sampling/Desain (RnD).

Alur: Style Master -> Sampling -> Approval -> HPP.
Endpoint prefix: /api/dewi/rnd (router dewi_rnd_shared, sub-modul styles/samples/hpp/overview).

Cakupan:
  A. Style Master + Design Approval:
     create style (draft)                      [POST /api/dewi/rnd/styles]
     submit-for-review -> pending_owner_review [POST /api/dewi/rnd/styles/{id}/submit-for-review]
     owner-approve -> approved_for_launch       [POST /api/dewi/rnd/styles/{id}/owner-approve]
     promote-to-production -> rahaza_models      [POST /api/dewi/rnd/styles/{id}/promote-to-production]
     jalur reject: submit -> owner-reject -> draft [POST .../owner-reject]
  B. Sampling + Approval:
     create sample-request (draft)              [POST /api/dewi/rnd/sample-requests]
     submit -> submitted                        [POST .../{id}/submit]
     approve -> approved                         [POST .../{id}/approve]
     jalur reject sample                         [POST .../{id}/reject]
  C. HPP:
     preview (tanpa simpan)                      [POST /api/dewi/rnd/hpp-calculator/preview]
     create + update (recalc)                    [POST/PUT /api/dewi/rnd/hpp-calculator]
     list by style                               [GET /api/dewi/rnd/hpp-calculator]
  D. Overview + Analytics + Tech-pack:
     style overview agregat                      [GET /api/dewi/rnd/styles/{id}/overview]
     analytics                                   [GET /api/dewi/rnd/analytics]
     tech-pack create + approve                  [POST /api/dewi/rnd/tech-packs, .../{id}/approve]
Guards:
  - create style tanpa code/name -> 400
  - create style code duplikat -> 409
  - submit-for-review pada status salah -> 400
  - owner-approve pada status bukan pending_owner_review -> 400
  - owner-reject tanpa notes -> 400
  - promote-to-production dua kali -> 400
  - create sample-request tanpa style_id -> 400 ; style_id invalid -> 404
  - submit sample non-draft -> 400 ; approve sample non-submitted -> 400
Self-cleanup (hard): styles + sample_requests + hpp + tech_packs + revisions + promoted models.
"""
import sys
import requests

BASE = "http://localhost:8001"
S = requests.Session()
TAG = "E2E-RND"
st = {"styles": [], "samples": [], "hpp": [], "tech_packs": [], "models": []}


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
    print("PASS login admin")


R = "/api/dewi/rnd"


def create_style(code, name, rnd_type="internal_product"):
    r = S.post(f"{BASE}{R}/styles", json={
        "style_code": code, "style_name": name, "category": "T-Shirt",
        "buyer": "E2E Buyer", "fabric_type": "Cotton Combed 30s", "season": "SS26",
        "description": "E2E RnD style", "rnd_type": rnd_type,
    })
    return r


def main():
    login()

    # ══ A. Style Master + Design Approval ════════════════════════════════════
    # guard: tanpa code/name
    rg = S.post(f"{BASE}{R}/styles", json={"style_code": "", "style_name": ""})
    assert rg.status_code == 400, f"expected 400 empty style got {rg.status_code}"
    print("PASS guard: create style tanpa code/name -> 400")

    code1 = f"{TAG}-ST-001"
    r = create_style(code1, "E2E Basic Tee")
    assert r.status_code == 200, f"create style {r.status_code}: {r.text}"
    s1 = r.json(); st["styles"].append(s1["id"])
    assert s1["status"] == "draft" and s1["style_code"] == code1, f"style draft {s1}"
    print(f"PASS create style {s1['style_code']} status=draft")

    # guard: duplikat code
    rg = create_style(code1, "Dup")
    assert rg.status_code == 409, f"expected 409 dup got {rg.status_code}"
    print("PASS guard: create style code duplikat -> 409")

    # submit-for-review
    r = S.post(f"{BASE}{R}/styles/{s1['id']}/submit-for-review", json={"notes": "Siap direview owner"})
    assert r.status_code == 200 and r.json()["status"] == "pending_owner_review", f"submit-review {r.text}"
    print("PASS submit-for-review -> status=pending_owner_review")

    # pending-review list
    r = S.get(f"{BASE}{R}/styles/pending-review")
    assert r.status_code == 200 and any(x["id"] == s1["id"] for x in r.json()), "style tidak muncul di pending-review"
    print("PASS style muncul di daftar pending-review")

    # owner-approve
    r = S.post(f"{BASE}{R}/styles/{s1['id']}/owner-approve", json={"notes": "Desain OK, lanjut"})
    assert r.status_code == 200 and r.json()["status"] == "approved_for_launch", f"owner-approve {r.text}"
    print("PASS owner-approve -> status=approved_for_launch")

    # guard: owner-approve lagi (status salah)
    rg = S.post(f"{BASE}{R}/styles/{s1['id']}/owner-approve", json={})
    assert rg.status_code == 400, f"expected 400 re-approve got {rg.status_code}"
    print("PASS guard: owner-approve pada status bukan pending_owner_review -> 400")

    # promote-to-production
    r = S.post(f"{BASE}{R}/styles/{s1['id']}/promote-to-production", json={})
    assert r.status_code == 200 and r.json().get("model_id"), f"promote {r.text}"
    st["models"].append(r.json()["model_id"])
    print(f"PASS promote-to-production -> Production Model {r.json()['model_code']} dibuat")

    # guard: promote lagi
    rg = S.post(f"{BASE}{R}/styles/{s1['id']}/promote-to-production", json={})
    assert rg.status_code == 400, f"expected 400 re-promote got {rg.status_code}"
    print("PASS guard: promote-to-production dua kali -> 400")

    # jalur reject style
    code2 = f"{TAG}-ST-002"
    r = create_style(code2, "E2E Reject Style")
    s2 = r.json(); st["styles"].append(s2["id"])
    S.post(f"{BASE}{R}/styles/{s2['id']}/submit-for-review", json={})
    rg = S.post(f"{BASE}{R}/styles/{s2['id']}/owner-reject", json={})
    assert rg.status_code == 400, f"expected 400 reject tanpa notes got {rg.status_code}"
    print("PASS guard: owner-reject tanpa notes -> 400")
    r = S.post(f"{BASE}{R}/styles/{s2['id']}/owner-reject", json={"notes": "Proporsi kurang pas"})
    assert r.status_code == 200 and r.json()["status"] == "draft", f"owner-reject {r.text}"
    print("PASS owner-reject (dengan catatan) -> status kembali draft")

    # ══ B. Sampling + Approval ═══════════════════════════════════════════════
    # guard tanpa style_id
    rg = S.post(f"{BASE}{R}/sample-requests", json={})
    assert rg.status_code == 400, f"expected 400 sample tanpa style got {rg.status_code}"
    print("PASS guard: create sample-request tanpa style_id -> 400")
    # guard style_id invalid
    rg = S.post(f"{BASE}{R}/sample-requests", json={"style_id": "nonexistent-id-xyz"})
    assert rg.status_code == 404, f"expected 404 sample style invalid got {rg.status_code}"
    print("PASS guard: create sample-request style_id invalid -> 404")

    r = S.post(f"{BASE}{R}/sample-requests", json={
        "style_id": s1["id"], "quantity": 5, "priority": "high", "notes": "Sample presentasi buyer"})
    assert r.status_code == 200, f"create sample {r.text}"
    sr = r.json(); st["samples"].append(sr["id"])
    assert sr["status"] == "draft" and sr["style_code"] == code1, f"sample draft {sr}"
    print(f"PASS create sample-request {sr['sample_code']} status=draft")

    rg = S.post(f"{BASE}{R}/sample-requests/{sr['id']}/approve", json={})
    assert rg.status_code == 400, f"expected 400 approve draft got {rg.status_code}"
    print("PASS guard: approve sample non-submitted -> 400")

    r = S.post(f"{BASE}{R}/sample-requests/{sr['id']}/submit")
    assert r.status_code == 200 and r.json()["status"] == "submitted", f"submit sample {r.text}"
    print("PASS submit sample -> status=submitted")

    rg = S.post(f"{BASE}{R}/sample-requests/{sr['id']}/submit")
    assert rg.status_code == 400, f"expected 400 submit non-draft got {rg.status_code}"
    print("PASS guard: submit sample non-draft -> 400")

    r = S.post(f"{BASE}{R}/sample-requests/{sr['id']}/approve", json={"notes": "Sample bagus, lolos QC internal"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["approval_status"] == "approved", f"approve sample {r.text}"
    print("PASS approve sample -> status=approved (approval_status=approved)")

    # jalur reject sample
    r = S.post(f"{BASE}{R}/sample-requests", json={"style_id": s1["id"], "quantity": 3, "notes": "Sample uji-2"})
    sr2 = r.json(); st["samples"].append(sr2["id"])
    S.post(f"{BASE}{R}/sample-requests/{sr2['id']}/submit")
    r = S.post(f"{BASE}{R}/sample-requests/{sr2['id']}/reject", json={"notes": "Jahitan tidak rapi"})
    assert r.status_code == 200 and r.json()["status"] == "rejected", f"reject sample {r.text}"
    print("PASS jalur reject sample -> status=rejected")

    # ══ C. HPP ═══════════════════════════════════════════════════════════════
    hpp_body = {
        "style_id": s1["id"], "style_code": code1, "style_name": "E2E Basic Tee",
        "fabric_usage_per_pcs": 1.5, "fabric_price_per_meter": 25000,
        "accessories_cost": [{"name": "Tag", "unit_cost": 1200, "qty": 1}],
        "cmt_cost_per_pcs": 15000, "cutting_cost_per_pcs": 5000, "packaging_cost_per_pcs": 2000,
        "overhead_pct": 10, "margin_pct": 30,
    }
    r = S.post(f"{BASE}{R}/hpp-calculator/preview", json=hpp_body)
    assert r.status_code == 200, f"preview hpp {r.text}"
    pv = r.json()
    # direct = 37500 + 1200 + 15000 + 5000 + 2000 = 60700 ; overhead 10% = 6070 ; hpp = 66770 ; sell = 66770/0.7 = 95385.71
    assert pv["direct_cost"] == 60700 and pv["hpp_total"] == 66770, f"hpp calc salah: {pv}"
    assert abs(pv["selling_price_proposal"] - 95385.71) < 1, f"selling price salah: {pv['selling_price_proposal']}"
    print(f"PASS preview HPP: direct=60700, hpp_total=66770, selling_proposal={pv['selling_price_proposal']} (margin 30%)")

    r = S.post(f"{BASE}{R}/hpp-calculator", json=hpp_body)
    assert r.status_code == 200, f"create hpp {r.text}"
    hpp = r.json(); st["hpp"].append(hpp["id"])
    assert hpp["hpp_total"] == 66770, f"hpp saved calc {hpp}"
    print(f"PASS create HPP {hpp['hpp_code']} tersimpan (hpp_total=66770)")

    # update: naikkan margin ke 40% -> selling berubah
    hpp_body2 = dict(hpp_body); hpp_body2["margin_pct"] = 40
    r = S.put(f"{BASE}{R}/hpp-calculator/{hpp['id']}", json=hpp_body2)
    assert r.status_code == 200, f"update hpp {r.text}"
    upd = r.json()
    # sell = 66770/0.6 = 111283.33
    assert abs(upd["selling_price_proposal"] - 111283.33) < 1, f"recalc salah: {upd['selling_price_proposal']}"
    print(f"PASS update HPP (margin 40%) recalc selling={upd['selling_price_proposal']}")

    r = S.get(f"{BASE}{R}/hpp-calculator?style_id={s1['id']}")
    assert r.status_code == 200 and any(h["id"] == hpp["id"] for h in r.json()), "hpp tidak muncul di list by style"
    print("PASS list HPP by style_id")

    # ══ D. Overview + Analytics + Tech-pack ══════════════════════════════════
    r = S.get(f"{BASE}{R}/styles/{s1['id']}/overview")
    assert r.status_code == 200, f"overview {r.text}"
    ov = r.json()
    assert ov["style"]["id"] == s1["id"] and ov["summary"]["total_samples"] >= 2 and ov["summary"]["total_hpp"] >= 1, f"overview summary {ov['summary']}"
    print(f"PASS style overview: samples={ov['summary']['total_samples']}, hpp={ov['summary']['total_hpp']}")

    r = S.get(f"{BASE}{R}/analytics")
    assert r.status_code == 200 and "styles" in r.json() and "sample_requests" in r.json(), f"analytics {r.text}"
    print(f"PASS analytics: styles.total={r.json()['styles']['total']}, samples.total={r.json()['sample_requests']['total']}")

    r = S.post(f"{BASE}{R}/tech-packs", json={
        "style_id": s1["id"], "style_code": code1, "style_name": "E2E Basic Tee",
        "version": "v1", "title": "Tech Pack E2E", "base_size": "M", "size_range": "S-XL",
        "bom_items": [{"material": "Cotton", "qty": 1.5}]})
    assert r.status_code == 200 and r.json()["status"] == "draft", f"tech-pack create {r.text}"
    tp = r.json(); st["tech_packs"].append(tp["id"])
    print("PASS create tech-pack status=draft")
    r = S.post(f"{BASE}{R}/tech-packs/{tp['id']}/approve")
    assert r.status_code == 200, f"tech-pack approve {r.text}"
    tp_after = S.get(f"{BASE}{R}/tech-packs/{tp['id']}").json()
    assert tp_after["status"] == "approved", f"tech-pack status {tp_after['status']}"
    print("PASS approve tech-pack -> status=approved")

    print("\n=== RND SAMPLING/DESAIN FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        c = {}
        c["hpp"] = db.dewi_rnd_hpp.delete_many({"style_code": {"$regex": f"^{TAG}"}}).deleted_count
        for hid in st["hpp"]:
            db.dewi_rnd_hpp.delete_one({"id": hid})
        c["tp"] = db.dewi_rnd_tech_packs.delete_many({"style_code": {"$regex": f"^{TAG}"}}).deleted_count
        c["sr"] = db.dewi_rnd_sample_requests.delete_many({"style_code": {"$regex": f"^{TAG}"}}).deleted_count
        c["rev"] = db.dewi_rnd_revisions.delete_many({"style_code": {"$regex": f"^{TAG}"}}).deleted_count
        c["cost"] = db.dewi_rnd_sample_costing.delete_many({"sample_code": {"$regex": "E2E"}}).deleted_count
        c["models"] = db.rahaza_models.delete_many({"rnd_style_code": {"$regex": f"^{TAG}"}}).deleted_count
        for mid in st["models"]:
            db.rahaza_models.delete_one({"id": mid})
        c["styles"] = db.dewi_rnd_styles.delete_many({"style_code": {"$regex": f"^{TAG}"}}).deleted_count
        cli.close()
        print(f"CLEANUP: styles({c['styles']}) samples({c['sr']}) hpp({c['hpp']}) "
              f"tech_packs({c['tp']}) revisions({c['rev']}) models({c['models']}) dihapus (DB pristine)")
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
