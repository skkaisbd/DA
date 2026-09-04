"""
POC — Vendor Portal "Panduan Produksi" end-to-end (backend proof).

Proves the P0 feature works before UI E2E:
  1. Admin login
  2. Seed maklon-full (creates vendor user + partner + model INT_MODEL)
  3. Admin sets SOP (sop_steps + videos + ref images) on the model
  4. Admin creates a vendor_job linked to that model (partner A)
  5. Admin creates a SECOND partner + vendor account + job (partner B) -> scoping test
  6. Vendor A login -> my-jobs shows only partner-A job; production-guide has_model=true w/ SOP
  7. Scoping: Vendor A can NOT read partner-B's job guide (404)

Uses only REAL endpoints (no mocking).
"""
import sys
import requests

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
VENDOR_A = {"email": "cmtvendor@dewiaditya.id", "password": "Dewi@123"}  # created by maklon-full seed
PARTNER_A = "mk-vendor-demo-1"
MODEL_ID = "int-demo-model-1"

passed, failed = [], []


def ok(msg):
    passed.append(msg)
    print(f"  [PASS] {msg}")


def bad(msg):
    failed.append(msg)
    print(f"  [FAIL] {msg}")


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("== 1. Admin login ==")
    admin_tok = login(ADMIN)
    ok("admin login")

    print("== 2. Seed maklon-full ==")
    r = requests.post(f"{BASE}/seed/maklon-full", headers=H(admin_tok), timeout=120)
    if r.status_code == 200:
        ok(f"maklon-full seed ({r.status_code})")
    else:
        bad(f"maklon-full seed returned {r.status_code}: {r.text[:200]}")

    print("== 3. Admin sets SOP on model ==")
    sop_body = {
        "sop_steps": [
            {"title": "Potong kain sesuai pola", "description": "Gunakan pola ukuran M/L. Sisakan margin 1cm."},
            {"title": "Jahit badan", "description": "Jahit sisi kiri-kanan, rapikan overdeck."},
            {"title": "Pasang label & finishing", "description": "Pasang label woven DA di leher belakang."},
        ],
        "reference_videos": [
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Teknik jahit overdeck"},
        ],
        "reference_images": [
            {"url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab", "caption": "Contoh kaos jadi"},
        ],
    }
    r = requests.put(f"{BASE}/rahaza/models/{MODEL_ID}/sop", headers=H(admin_tok), json=sop_body, timeout=30)
    if r.status_code == 200 and len(r.json().get("sop_steps", [])) == 3:
        ok("SOP saved (3 steps) on model")
    else:
        bad(f"SOP save failed {r.status_code}: {r.text[:200]}")

    print("== 4. Admin creates vendor_job (partner A + model) ==")
    job_body = {
        "title": "Jahit Kaos Basic DA - 300 pcs",
        "partner_id": PARTNER_A,
        "model_id": MODEL_ID,
        "qty_target": 300,
        "process": "SEWING",
        "notes": "POC job with SOP",
    }
    r = requests.post(f"{BASE}/vendor-portal/jobs", headers=H(admin_tok), json=job_body, timeout=30)
    if r.status_code == 200:
        job_a = r.json()
        ok(f"vendor_job A created {job_a['job_number']} model_code={job_a.get('model_code')}")
        if job_a.get("model_id") == MODEL_ID:
            ok("job A has model_id linked")
        else:
            bad("job A model_id NOT linked")
    else:
        bad(f"create job A failed {r.status_code}: {r.text[:200]}")
        job_a = {}

    print("== 5. Create partner B + vendor account B + job B (scoping) ==")
    r = requests.post(f"{BASE}/vendor-portal/partners", headers=H(admin_tok),
                      json={"name": "CV Vendor Lain B", "code": "VLB"}, timeout=30)
    partner_b = r.json().get("id") if r.status_code == 200 else None
    if partner_b:
        ok(f"partner B created {partner_b}")
    else:
        bad(f"partner B create failed {r.status_code}: {r.text[:150]}")

    vendor_b_email = "vendorb_poc@dewiaditya.id"
    if partner_b:
        # idempotent-ish: ignore 'already exists'
        r = requests.post(f"{BASE}/vendor-portal/accounts", headers=H(admin_tok),
                          json={"email": vendor_b_email, "name": "Vendor B POC",
                                "password": "Dewi@123", "partner_id": partner_b}, timeout=30)
        if r.status_code in (200, 400):
            ok(f"vendor account B ({r.status_code})")
        else:
            bad(f"vendor account B failed {r.status_code}: {r.text[:150]}")
        r = requests.post(f"{BASE}/vendor-portal/jobs", headers=H(admin_tok),
                          json={"title": "Job Rahasia B", "partner_id": partner_b,
                                "model_id": MODEL_ID, "qty_target": 50, "process": "QC"}, timeout=30)
        job_b = r.json() if r.status_code == 200 else {}
        if job_b:
            ok(f"vendor_job B created {job_b.get('job_number')}")
        else:
            bad(f"create job B failed {r.status_code}")
    else:
        job_b = {}

    print("== 6. Vendor A login + my-jobs + production-guide ==")
    vtok = login(VENDOR_A)
    ok("vendor A login")

    r = requests.get(f"{BASE}/vendor-portal/my-jobs", headers=H(vtok), timeout=30)
    jobs = r.json() if r.status_code == 200 else []
    job_ids = {j["id"] for j in jobs}
    print(f"    vendor A sees {len(jobs)} jobs")
    if job_a and job_a.get("id") in job_ids:
        ok("vendor A sees own job A")
    else:
        bad("vendor A does NOT see own job A")

    # SCOPING: vendor A must NOT see partner B's job in the list
    if job_b and job_b.get("id") in job_ids:
        bad("SCOPING BREACH: vendor A sees partner B's job in list")
    else:
        ok("scoping OK: vendor A does not see partner B job in list")

    if job_a:
        r = requests.get(f"{BASE}/vendor-portal/my-jobs/{job_a['id']}/production-guide", headers=H(vtok), timeout=30)
        if r.status_code == 200:
            g = r.json()
            if g.get("has_model") and len(g.get("model", {}).get("sop_steps", [])) == 3:
                ok("production-guide for job A has_model=true w/ 3 SOP steps")
            else:
                bad(f"production-guide job A missing SOP: {str(g)[:200]}")
            if g.get("model", {}).get("reference_videos"):
                ok("production-guide includes reference_videos")
            else:
                bad("production-guide missing reference_videos")
        else:
            bad(f"production-guide job A failed {r.status_code}: {r.text[:150]}")

    print("== 7. Scoping: vendor A cannot read partner B's guide ==")
    if job_b:
        r = requests.get(f"{BASE}/vendor-portal/my-jobs/{job_b['id']}/production-guide", headers=H(vtok), timeout=30)
        if r.status_code == 404:
            ok("scoping OK: vendor A gets 404 on partner B guide")
        else:
            bad(f"SCOPING BREACH: vendor A read partner B guide -> {r.status_code}")

    print("\n================= SUMMARY =================")
    print(f"PASSED: {len(passed)}  FAILED: {len(failed)}")
    for f in failed:
        print(f"  FAIL: {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
