#!/usr/bin/env python3
"""
POC — PDF branding + signature (item#3 P1b/P1c/P1d).
- _build_payslip_pdf() menghasilkan PDF valid dgn nama tanda tangan (custom + dari field).
- Surat Jalan SSOT PDF: company profile + tanda tangan configurable + preview inline.
Self-clean. Exit 0 = PASS.
"""
import os, sys, io, uuid, asyncio, requests
sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
BASE = "http://localhost:8001/api"
PASS = FAIL = 0

def check(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  ✅ {m}")
    else: FAIL += 1; print(f"  ❌ {m}")

def login():
    r = requests.post(f"{BASE}/auth/login", json={"email":"admin@garment.com","password":"Admin@123"}, timeout=15)
    return r.json()["token"]

def test_payslip_unit():
    print("\n== A: payslip PDF unit (branding + signature custom & field) ==")
    from routes.rahaza_payroll_payslips import _build_payslip_pdf
    slip = {"employee_name": "Budi Santoso", "employee_code": "EMP-001",
            "period_from": "2026-07-01", "period_to": "2026-07-31",
            "earnings": [{"label": "Gaji Pokok", "amount": 5000000}],
            "deductions": [{"label": "BPJS", "amount": 100000}],
            "gross": 5000000, "total_deductions": 100000, "net_pay": 4900000,
            "run_id": "x"}
    run = {"run_number": "RUN-202607", "approved_by_name": "Manager A"}
    profile = {"company_name": "CV. DEWI ADITYA OFFICIAL", "tagline": "Garment & Maklon"}
    doc_settings = {"show_logo": True, "show_signatures": True, "signatures": [
        {"label": "Disetujui", "name_source": "custom", "custom_name": "Bu Dewi", "role_label": "Direktur"},
        {"label": "Diterima", "name_source": "field", "field_key": "employee_name", "role_label": "Karyawan"},
    ]}
    buf = _build_payslip_pdf(slip, run, profile=profile, doc_settings=doc_settings)
    data = buf.getvalue()
    check(data[:4] == b"%PDF", f"payslip PDF valid (%PDF, {len(data)} bytes)")
    check(len(data) > 1500, "payslip PDF non-trivial size")
    # show_signatures=False → tetap valid & lebih pendek
    ds2 = {**doc_settings, "show_signatures": False}
    buf2 = _build_payslip_pdf(slip, run, profile=profile, doc_settings=ds2)
    check(buf2.getvalue()[:4] == b"%PDF", "payslip PDF valid tanpa tanda tangan")

def test_sj_pdf(token):
    print("\n== B: Surat Jalan SSOT PDF (endpoint) + preview inline ==")
    sj_id = str(uuid.uuid4())
    db.wh_delivery_notes.insert_one({
        "id": sj_id, "sj_number": "SJ-POC/2026/07/0001", "sj_type": "SJ-MAKLON",
        "recipient_name": "PT Klien Uji", "recipient_address": "Jakarta",
        "shipper_name": "Gudang A", "driver_name": "Pak Joko", "vehicle_no": "B 1234 XY",
        "status": "issued", "issued_at": "2026-07-12",
        "lines": [{"line_no": 1, "description": "Kaos Polos", "qty": 100, "unit": "pcs", "remarks": ""}],
        "is_poc": True,
    })
    try:
        # set custom signature config for delivery-note
        requests.put(f"{BASE}/pdf-doc-settings/delivery-note",
                     headers={"Authorization": f"Bearer {token}"},
                     json={"signatures": [
                         {"key":"sender","label":"Pengirim","name_source":"field","field_key":"issued_by","role_label":"Gudang"},
                         {"key":"driver","label":"Sopir","name_source":"field","field_key":"driver_name","role_label":"Ekspedisi"},
                         {"key":"receiver","label":"Penerima","name_source":"blank","role_label":"Klien"},
                     ]}, timeout=15)
        r = requests.get(f"{BASE}/wms/delivery-notes/{sj_id}/pdf?preview=1&token={token}", timeout=20)
        check(r.status_code == 200, f"SJ pdf -> {r.status_code}")
        check(r.headers.get("content-type","").startswith("application/pdf"), f"content-type pdf ({r.headers.get('content-type')})")
        check(r.content[:4] == b"%PDF", f"SJ PDF valid (%PDF, {len(r.content)} bytes)")
        check("inline" in r.headers.get("content-disposition",""), f"preview=1 -> inline disposition ({r.headers.get('content-disposition')})")
        # attachment mode
        r2 = requests.get(f"{BASE}/wms/delivery-notes/{sj_id}/pdf?token={token}", timeout=20)
        check("attachment" in r2.headers.get("content-disposition",""), "tanpa preview -> attachment")
    finally:
        db.wh_delivery_notes.delete_many({"is_poc": True})
        # reset delivery-note settings created during test
        db.pdf_document_settings.delete_many({"doc_type": "delivery-note"})

if __name__ == "__main__":
    try:
        token = login()
        test_payslip_unit()
        test_sj_pdf(token)
    except Exception as e:
        import traceback; traceback.print_exc(); FAIL += 1
    print(f"\n==== RESULT: {PASS} PASS / {FAIL} FAIL ====")
    sys.exit(0 if FAIL == 0 else 1)
