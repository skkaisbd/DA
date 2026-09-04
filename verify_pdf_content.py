#!/usr/bin/env python3
"""
Detailed PDF content verification - extract and display actual text
"""

import requests
import io
from PyPDF2 import PdfReader

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
        return f"ERROR: {resp.status_code}"
    
    pdf_file = io.BytesIO(resp.content)
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def main():
    print("="*80)
    print("DETAILED PDF CONTENT VERIFICATION")
    print("="*80)
    
    token = login()
    
    # Test 1: SHP-0077 with 2 accessories
    print("\n" + "="*80)
    print("TEST 1: SHP-0077 (aacf1cf2-b366-499b-abc4-7b27c170a4b2)")
    print("Expected: 2 accessories (A5 Label merk Hitam 25 pcs, A6 Label merk premium pink 25 pcs)")
    print("="*80)
    text = get_pdf_text(token, "vendor-shipment", "aacf1cf2-b366-499b-abc4-7b27c170a4b2")
    print(text)
    
    # Test 2: SHP-002 with 1 accessory
    print("\n" + "="*80)
    print("TEST 2: SHP-002 (a9886906-b603-4d7a-b2c7-273f16848cfd)")
    print("Expected: 1 accessory (A6 from PO-0035)")
    print("="*80)
    text = get_pdf_text(token, "vendor-shipment", "a9886906-b603-4d7a-b2c7-273f16848cfd")
    print(text)
    
    # Test 3: SJ-MK-DEMO-2 without accessories
    print("\n" + "="*80)
    print("TEST 3: SJ-MK-DEMO-2 (po-mk-demo-2-vs1)")
    print("Expected: Message 'tidak ada aksesoris pada pengiriman ini'")
    print("="*80)
    text = get_pdf_text(token, "vendor-shipment", "po-mk-demo-2-vs1")
    print(text)
    
    # Test 4: Production guide
    print("\n" + "="*80)
    print("TEST 4: Production Guide (a9886906-b603-4d7a-b2c7-273f16848cfd)")
    print("Expected: PANDUAN PRODUK, ARN-HD, Jaket Hoodie Aruna, SOP steps")
    print("="*80)
    text = get_pdf_text(token, "production-guide", "a9886906-b603-4d7a-b2c7-273f16848cfd")
    print(text)

if __name__ == "__main__":
    main()
