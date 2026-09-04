"""Verify the EXACT user complaint scenario end-to-end (Fix #1, maklon branch):
SOP input di ERP (Katalog Buyer -> Panduan Produksi)  ==>  terlihat oleh Vendor CMT.

Steps:
 1. Create buyer-catalog (client BUMI) via real ERP API.
 2. Write SOP via PUT /buyer-catalog/{id}/sop (real ERP API).
 3. Link JOB-PO-MK-DEMO-2 items -> catalog_item_id (simulates PO->job propagation fix).
 4. Login as vendor cmtvendor2 (RPK, owns JOB-PO-MK-DEMO-2).
 5. Vendor GET /production-jobs (scoped) must list the job.
 6. Vendor GET /production-jobs/{id}/production-guide must return SOP (source=buyer_catalog).
"""
import os, time, requests
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]

def login(email, pw, retries=5):
    for i in range(retries):
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=10)
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(8); continue
        raise SystemExit(f"login {email} failed {r.status_code}: {r.text[:200]}")
    raise SystemExit(f"login {email} rate-limited")

def main():
    admin = login("admin@garment.com", "Admin@123")
    ah = {"Authorization": f"Bearer {admin}"}

    # 1. Create buyer catalog for BUMI
    payload = {
        "client_id": "demo-cl-bumi", "artikel_code": "BUM-PL",
        "buyer_ref_code": "BUMI-POLO-01", "product_name": "Kaos Polo Bumi",
        "category": "Garment", "gender": "Unisex",
        "default_cmt_price": 12000, "color_options": ["Putih"], "size_options": ["M", "L"],
        "description": "Artikel maklon Bumi Sportwear (verifikasi SOP->vendor)",
    }
    r = requests.post(f"{BASE}/dewi/maklon/buyer-catalog", json=payload, headers=ah, timeout=15)
    if r.status_code == 409:  # already exists -> find it
        existing = db.dewi_maklon_buyer_catalog.find_one({"client_id": "demo-cl-bumi", "artikel_code": "BUM-PL"})
        cid = existing["id"]
        print(f"[1] buyer-catalog already exists id={cid}")
    else:
        assert r.status_code in (200, 201), f"create catalog {r.status_code}: {r.text[:300]}"
        cid = r.json()["id"]
        print(f"[1] created buyer-catalog id={cid} ({r.status_code})")

    # 2. Write SOP via ERP API
    sop = {
        "sop_steps": [
            {"seq": 1, "title": "Potong kain pique", "description": "Gelar kain pique, potong pola polo M/L."},
            {"seq": 2, "title": "Jahit body & kerah rib", "description": "Pasang kerah rib + placket 3 kancing."},
            {"seq": 3, "title": "Pasang kancing & label", "description": "3 kancing, label ukuran/brand, obras rapi."},
            {"seq": 4, "title": "QC & packing", "description": "Cek jahitan/ukuran/noda, setrika, polybag."},
        ],
        "reference_videos": [{"url": "https://youtu.be/polo-demo", "title": "Referensi jahit polo"}],
        "reference_images": [],
    }
    r = requests.put(f"{BASE}/dewi/maklon/buyer-catalog/{cid}/sop", json=sop, headers=ah, timeout=15)
    assert r.status_code == 200, f"write SOP {r.status_code}: {r.text[:300]}"
    print(f"[2] SOP written via ERP API ({len(sop['sop_steps'])} steps)")

    # 3. Link JOB-PO-MK-DEMO-2 items -> catalog_item_id (PO->job propagation)
    poi = db.po_items.update_many({"po_id": "po-mk-demo-2"}, {"$set": {"catalog_item_id": cid}})
    jbi = db.production_job_items.update_many({"job_id": "po-mk-demo-2-job1"}, {"$set": {"catalog_item_id": cid}})
    print(f"[3] linked po_items={poi.modified_count} job_items={jbi.modified_count} -> catalog {cid}")

    # 4. Vendor login (cmtvendor2 -> RPK -> owns JOB-PO-MK-DEMO-2)
    ven = login("cmtvendor2@dewiaditya.id", "Dewi@123")
    vh = {"Authorization": f"Bearer {ven}"}

    # 5. Vendor lists production jobs (scoped)
    r = requests.get(f"{BASE}/production-jobs", headers=vh, timeout=10)
    assert r.status_code == 200, f"vendor list jobs {r.status_code}: {r.text[:200]}"
    data = r.json()
    jobs = data if isinstance(data, list) else data.get("items", data.get("data", []))
    jn = [(j.get("id"), j.get("job_number"), j.get("vendor_id")) for j in jobs]
    print(f"[5] vendor sees {len(jobs)} job(s): {jn}")
    assert any(j.get("id") == "po-mk-demo-2-job1" for j in jobs), "vendor did NOT see own maklon job!"
    assert all(j.get("vendor_id") == "demo-vn-rpk" for j in jobs), "scope leak: vendor saw other vendor jobs!"

    # 6. Vendor opens production-guide -> SOP must be present, source=buyer_catalog
    r = requests.get(f"{BASE}/production-jobs/po-mk-demo-2-job1/production-guide", headers=vh, timeout=10)
    assert r.status_code == 200, f"vendor guide {r.status_code}: {r.text[:200]}"
    g = r.json()
    print(f"[6] has_guide={g.get('has_guide')} has_content={g.get('has_content')}")
    guides = g.get("guides", [])
    assert g.get("has_content"), f"SOP NOT visible to vendor! {g.get('message')}"
    for gd in guides:
        print(f"    SOURCE={gd.get('source_type')} code={gd.get('code')} name={gd.get('name')} steps={len(gd.get('sop_steps') or [])}")
    assert any(gd.get("source_type") == "buyer_catalog" and len(gd.get("sop_steps") or []) == 4 for gd in guides), \
        "buyer_catalog SOP (4 steps) not resolved for vendor"

    # 7. Negative scope check: other vendor (JMC) must NOT see this job
    ven2 = login("cmtvendor@dewiaditya.id", "Dewi@123")
    vh2 = {"Authorization": f"Bearer {ven2}"}
    r = requests.get(f"{BASE}/production-jobs/po-mk-demo-2-job1/production-guide", headers=vh2, timeout=10)
    print(f"[7] other vendor (JMC) accessing RPK's job -> HTTP {r.status_code} (expect 403)")
    assert r.status_code == 403, "SCOPE LEAK: other vendor accessed job guide!"

    print("\n==== VERIFY OK: SOP input di ERP -> terlihat Vendor CMT (source=Katalog Buyer). Scope aman. ====")

if __name__ == "__main__":
    main()
