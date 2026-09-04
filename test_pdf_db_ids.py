#!/usr/bin/env python3
"""
Get sample IDs from MongoDB for comprehensive PDF testing
"""

from pymongo import MongoClient
import requests
import io
from PyPDF2 import PdfReader

# MongoDB connection
client = MongoClient("mongodb://localhost:27017")
db = client["test_database"]

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@garment.com"
LOGIN_PASSWORD = "Admin@123"

def login():
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=30
    )
    return resp.json().get("token")

def get_pdf_text(token, pdf_type, pdf_id):
    url = f"{BASE_URL}/export-pdf?type={pdf_type}&id={pdf_id}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=60)
    
    if resp.status_code != 200:
        return None, resp.status_code, resp.text[:200]
    
    pdf_file = io.BytesIO(resp.content)
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text, 200, f"{len(resp.content)} bytes"

def main():
    print("="*80)
    print("COMPREHENSIVE PDF TESTING - Get IDs from DB")
    print("="*80)
    
    token = login()
    
    # Get sample IDs from various collections
    print("\n📋 Getting sample IDs from database...")
    
    # 1. Article catalog with sop_steps
    print("\n1. Article Catalog (dewi_maklon_buyer_catalog) with sop_steps:")
    catalog_items = list(db.dewi_maklon_buyer_catalog.find(
        {"sop_steps": {"$exists": True, "$ne": []}},
        {"_id": 1, "article_code": 1, "article_name": 1}
    ).limit(2))
    
    for item in catalog_items:
        article_id = item["_id"]
        code = item.get("article_code", "N/A")
        name = item.get("article_name", "N/A")
        print(f"   - ID: {article_id}, Code: {code}, Name: {name}")
        
        # Test production-guide with this article ID
        text, status, info = get_pdf_text(token, "production-guide", article_id)
        if status == 200 and text:
            if "PANDUAN PRODUK" in text and code in text:
                print(f"     ✅ production-guide PDF OK: {info}")
            else:
                print(f"     ⚠️  PDF generated but missing expected content")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    # 2. Production jobs
    print("\n2. Production Jobs (production_jobs):")
    jobs = list(db.production_jobs.find({}, {"_id": 1, "job_number": 1}).limit(2))
    
    for job in jobs:
        job_id = job["_id"]
        job_number = job.get("job_number", "N/A")
        print(f"   - ID: {job_id}, Job Number: {job_number}")
        
        # Test production-guide with this job ID
        text, status, info = get_pdf_text(token, "production-guide", job_id)
        if status == 200 and text:
            if "PANDUAN PRODUK" in text:
                print(f"     ✅ production-guide PDF OK: {info}")
            else:
                print(f"     ⚠️  PDF generated but content unclear")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    # 3. Production POs
    print("\n3. Production POs (production_pos):")
    pos = list(db.production_pos.find({}, {"_id": 1, "po_number": 1}).limit(2))
    
    for po in pos:
        po_id = po["_id"]
        po_number = po.get("po_number", "N/A")
        print(f"   - ID: {po_id}, PO Number: {po_number}")
        
        # Test production-po PDF
        text, status, info = get_pdf_text(token, "production-po", po_id)
        if status == 200 and text:
            print(f"     ✅ production-po PDF OK: {info}")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    # 4. Buyer shipments
    print("\n4. Buyer Shipments (buyer_shipments):")
    shipments = list(db.buyer_shipments.find({}, {"_id": 1, "shipment_number": 1}).limit(2))
    
    for ship in shipments:
        ship_id = ship["_id"]
        ship_number = ship.get("shipment_number", "N/A")
        print(f"   - ID: {ship_id}, Shipment Number: {ship_number}")
        
        # Test buyer-shipment PDF
        text, status, info = get_pdf_text(token, "buyer-shipment", ship_id)
        if status == 200 and text:
            print(f"     ✅ buyer-shipment PDF OK: {info}")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    # 5. Material requests
    print("\n5. Material Requests (material_requests):")
    requests_docs = list(db.material_requests.find({}, {"_id": 1, "request_number": 1}).limit(2))
    
    for req in requests_docs:
        req_id = req["_id"]
        req_number = req.get("request_number", "N/A")
        print(f"   - ID: {req_id}, Request Number: {req_number}")
        
        # Test material-request PDF
        text, status, info = get_pdf_text(token, "material-request", req_id)
        if status == 200 and text:
            print(f"     ✅ material-request PDF OK: {info}")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    # 6. Production returns
    print("\n6. Production Returns (production_returns):")
    returns = list(db.production_returns.find({}, {"_id": 1, "return_number": 1}).limit(2))
    
    for ret in returns:
        ret_id = ret["_id"]
        ret_number = ret.get("return_number", "N/A")
        print(f"   - ID: {ret_id}, Return Number: {ret_number}")
        
        # Test production-return PDF
        text, status, info = get_pdf_text(token, "production-return", ret_id)
        if status == 200 and text:
            print(f"     ✅ production-return PDF OK: {info}")
        else:
            print(f"     ❌ Failed: {status} - {info}")
    
    print("\n" + "="*80)
    print("COMPREHENSIVE TESTING COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
