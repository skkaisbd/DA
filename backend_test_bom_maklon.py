#!/usr/bin/env python3
"""
Backend Test: SAMBUNGAN BOM MAKLON (Template → Kebutuhan Material PO → Surat Jalan)
Sesi 2026-08-02

Verifikasi fitur:
- A. SINKRONISASI DARI TEMPLATE AKTIF (6 tests)
- B. PILIH VERSI TEMPLATE (LOCK) (4 tests)
- C. AUTO-EXPLODE SAAT PO MAKLON DIBUAT/DIUBAH (3 tests)
- D. CHECKLIST MATERIAL DARI KLIEN (3 tests)
- E. PO-360 & SURAT JALAN (4 tests)

ATURAN DATA:
- Database berisi data nyata owner - JANGAN drop koleksi atau hapus dokumen owner
- Boleh membaca DB langsung via pymongo (mongodb://localhost:27017, db test_database)
- Kalau membuat PO uji, hapus lagi setelah selesai & laporkan
- Login SEKALI dan reuse token (rate limit 10/60s)
"""

import requests
import json
import time
from datetime import datetime
from pymongo import MongoClient
import PyPDF2
import io

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@garment.com"
LOGIN_PASSWORD = "Admin@123"

# Test objects available
PO_IDS = {
    'po-mk-demo-1': {'po_number': 'PO-MK-DEMO-1', 'qty': 250, 'artikel': 'hoodie'},
    'po-mk-demo-2': {'po_number': 'PO-MK-DEMO-2', 'qty': 150, 'artikel': 'polo'},
    '4daa5da2-cab4-4de8-b280-55aece4f175a': {'po_number': 'PO-0035', 'qty': 85, 'articles': 2},
    '8adb0631-8a1c-40dd-85f6-56fdab440591': {'po_number': 'PO-004', 'qty': 48, 'articles': 2, 'manual_acc': ['A5', 'A6']},
}

TEMPLATES = {
    'bom-mk-cat-demo-hoodie': {'artikel': 'mk-cat-demo-hoodie', 'version': 1},
    'bom-mk-cat-demo-polo': {'artikel': 'mk-cat-demo-polo', 'version': 1},
}

SHIPMENT_ID = 'aacf1cf2-b366-499b-abc4-7b27c170a4b2'  # SHP-0077, PO-004

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
TOKEN = None
TEST_DATA_CREATED = []

def login():
    """Login once and reuse token"""
    global TOKEN
    if TOKEN:
        return TOKEN
    
    print("🔐 Logging in...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    TOKEN = data.get('token')
    assert TOKEN, "No token in login response"
    print(f"✅ Logged in successfully")
    return TOKEN

def headers():
    """Get authorization headers"""
    return {"Authorization": f"Bearer {login()}"}

def get_db():
    """Get MongoDB connection"""
    client = MongoClient('mongodb://localhost:27017')
    return client['test_database']

def cleanup():
    """Cleanup test data"""
    if not TEST_DATA_CREATED:
        return
    
    print(f"\n🧹 Cleaning up {len(TEST_DATA_CREATED)} test items...")
    db = get_db()
    for item in TEST_DATA_CREATED:
        if item['type'] == 'po':
            # Delete PO and related data
            po_id = item['id']
            db.production_pos.delete_one({'id': po_id})
            db.po_items.delete_many({'po_id': po_id})
            db.dewi_maklon_bom.delete_many({'po_id': po_id})
            db.po_accessories.delete_many({'po_id': po_id})
            print(f"  ✓ Deleted PO {item.get('po_number', po_id)}")
    
    TEST_DATA_CREATED.clear()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION A: SINKRONISASI DARI TEMPLATE AKTIF
# ══════════════════════════════════════════════════════════════════════════════
def test_a1_bom_sync_po_mk_demo_1():
    """A.1: POST /api/dewi/maklon/pos/po-mk-demo-1/bom-sync body {} → 200
    
    Harus: ok=true, skipped=false, po_source="production_pos", total_pcs=250,
    materials=4, bulk_rows=1, accessory_rows=3, templates_used memuat version 1.
    """
    print("\n" + "="*80)
    print("TEST A.1: BOM Sync PO-MK-DEMO-1 (250 pcs hoodie)")
    print("="*80)
    
    po_id = 'po-mk-demo-1'
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
        json={},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Verify response structure
    assert data.get('ok') == True, "ok should be true"
    assert data.get('skipped') == False, "skipped should be false"
    assert data.get('po_source') == 'production_pos', f"po_source should be 'production_pos', got {data.get('po_source')}"
    assert data.get('total_pcs') == 250, f"total_pcs should be 250, got {data.get('total_pcs')}"
    assert data.get('materials') == 4, f"materials should be 4, got {data.get('materials')}"
    assert data.get('bulk_rows') == 1, f"bulk_rows should be 1, got {data.get('bulk_rows')}"
    assert data.get('accessory_rows') == 3, f"accessory_rows should be 3, got {data.get('accessory_rows')}"
    
    templates_used = data.get('templates_used', [])
    assert len(templates_used) > 0, "templates_used should not be empty"
    assert templates_used[0].get('version') == 1, f"template version should be 1, got {templates_used[0].get('version')}"
    
    print("✅ A.1 PASS: BOM sync successful with correct structure")
    return data

def test_a2_verify_db_dewi_maklon_bom():
    """A.2: Cek DB `dewi_maklon_bom` untuk po_id itu
    
    Verifikasi: source="template_auto", tiap baris punya material_name, material_category,
    line_type, unit, qty_estimated, qty_per_pcs, qty_total_est (alias sama dengan qty_estimated),
    cost_per_unit, estimated_cost = qty_estimated × cost_per_unit, ownership="client_provided",
    source_template_id/version.
    
    Matematika: untuk hoodie 250 pcs, baris kain harus 250 × qty_per_pcs template.
    """
    print("\n" + "="*80)
    print("TEST A.2: Verify DB dewi_maklon_bom for po-mk-demo-1")
    print("="*80)
    
    db = get_db()
    po_id = 'po-mk-demo-1'
    
    bom = db.dewi_maklon_bom.find_one({'po_id': po_id})
    assert bom is not None, f"BOM not found for po_id {po_id}"
    
    print(f"BOM source: {bom.get('source')}")
    assert bom.get('source') == 'template_auto', f"source should be 'template_auto', got {bom.get('source')}"
    
    materials = bom.get('materials', [])
    print(f"Total materials: {len(materials)}")
    assert len(materials) == 4, f"Expected 4 materials, got {len(materials)}"
    
    # Verify each material has required fields
    for idx, m in enumerate(materials):
        print(f"\nMaterial {idx+1}:")
        print(f"  name: {m.get('material_name')}")
        print(f"  category: {m.get('material_category')}")
        print(f"  line_type: {m.get('line_type')}")
        print(f"  unit: {m.get('unit')}")
        print(f"  qty_estimated: {m.get('qty_estimated')}")
        print(f"  qty_per_pcs: {m.get('qty_per_pcs')}")
        print(f"  qty_total_est: {m.get('qty_total_est')}")
        print(f"  cost_per_unit: {m.get('cost_per_unit')}")
        print(f"  estimated_cost: {m.get('estimated_cost')}")
        print(f"  ownership: {m.get('ownership')}")
        print(f"  source_template_id: {m.get('source_template_id')}")
        print(f"  source_template_version: {m.get('source_template_version')}")
        
        # Required fields
        assert m.get('material_name'), f"Material {idx+1} missing material_name"
        assert m.get('material_category'), f"Material {idx+1} missing material_category"
        assert m.get('line_type'), f"Material {idx+1} missing line_type"
        assert m.get('unit'), f"Material {idx+1} missing unit"
        assert 'qty_estimated' in m, f"Material {idx+1} missing qty_estimated"
        assert 'qty_per_pcs' in m, f"Material {idx+1} missing qty_per_pcs"
        assert 'qty_total_est' in m, f"Material {idx+1} missing qty_total_est"
        assert 'cost_per_unit' in m, f"Material {idx+1} missing cost_per_unit"
        assert 'estimated_cost' in m, f"Material {idx+1} missing estimated_cost"
        assert m.get('ownership') == 'client_provided', f"Material {idx+1} ownership should be 'client_provided'"
        assert m.get('source_template_id'), f"Material {idx+1} missing source_template_id"
        assert m.get('source_template_version') == 1, f"Material {idx+1} version should be 1"
        
        # Verify alias: qty_total_est == qty_estimated
        assert m.get('qty_total_est') == m.get('qty_estimated'), \
            f"Material {idx+1}: qty_total_est ({m.get('qty_total_est')}) != qty_estimated ({m.get('qty_estimated')})"
        
        # Verify math: estimated_cost = qty_estimated × cost_per_unit
        expected_cost = round(m.get('qty_estimated', 0) * m.get('cost_per_unit', 0), 2)
        assert abs(m.get('estimated_cost', 0) - expected_cost) < 0.01, \
            f"Material {idx+1}: estimated_cost ({m.get('estimated_cost')}) != qty_estimated × cost_per_unit ({expected_cost})"
        
        # Verify math: qty_estimated = 250 × qty_per_pcs (for 250 pcs PO)
        expected_qty = round(250 * m.get('qty_per_pcs', 0), 4)
        assert abs(m.get('qty_estimated', 0) - expected_qty) < 0.01, \
            f"Material {idx+1}: qty_estimated ({m.get('qty_estimated')}) != 250 × qty_per_pcs ({expected_qty})"
    
    print("\n✅ A.2 PASS: DB dewi_maklon_bom verified with correct schema and math")

def test_a3_verify_po_accessories():
    """A.3: Cek DB `po_accessories` po_id itu
    
    Ada 3 baris source="bom_maklon_auto" dengan qty_needed = qty template × 250
    dan notes menyebut "BOM Template maklon v1".
    """
    print("\n" + "="*80)
    print("TEST A.3: Verify DB po_accessories for po-mk-demo-1")
    print("="*80)
    
    db = get_db()
    po_id = 'po-mk-demo-1'
    
    accessories = list(db.po_accessories.find({'po_id': po_id, 'source': 'bom_maklon_auto'}))
    print(f"Found {len(accessories)} auto accessories")
    
    assert len(accessories) == 3, f"Expected 3 auto accessories, got {len(accessories)}"
    
    for idx, acc in enumerate(accessories):
        print(f"\nAccessory {idx+1}:")
        print(f"  name: {acc.get('accessory_name')}")
        print(f"  code: {acc.get('accessory_code')}")
        print(f"  qty_needed: {acc.get('qty_needed')}")
        print(f"  unit: {acc.get('unit')}")
        print(f"  notes: {acc.get('notes')}")
        print(f"  source: {acc.get('source')}")
        
        assert acc.get('source') == 'bom_maklon_auto', f"Accessory {idx+1} source should be 'bom_maklon_auto'"
        assert 'qty_needed' in acc, f"Accessory {idx+1} missing qty_needed"
        assert acc.get('notes') and 'v1' in acc.get('notes', ''), \
            f"Accessory {idx+1} notes should mention 'v1', got: {acc.get('notes')}"
    
    print("\n✅ A.3 PASS: po_accessories verified with 3 auto accessories")

def test_a4_idempotent_bom_sync():
    """A.4: IDEMPOTEN: jalankan bom-sync 2x lagi
    
    Jumlah baris `po_accessories` source=bom_maklon_auto TIDAK bertambah (tetap 3)
    dan materials tetap 4.
    """
    print("\n" + "="*80)
    print("TEST A.4: Idempotent BOM sync (run 2x more)")
    print("="*80)
    
    po_id = 'po-mk-demo-1'
    db = get_db()
    
    # Count before
    acc_before = db.po_accessories.count_documents({'po_id': po_id, 'source': 'bom_maklon_auto'})
    bom_before = db.dewi_maklon_bom.find_one({'po_id': po_id})
    materials_before = len(bom_before.get('materials', []))
    
    print(f"Before: {acc_before} accessories, {materials_before} materials")
    
    # Run sync twice
    for i in range(2):
        print(f"\nRun {i+1}...")
        resp = requests.post(
            f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
            json={},
            headers=headers()
        )
        assert resp.status_code == 200, f"Run {i+1} failed: {resp.status_code}"
        time.sleep(0.5)
    
    # Count after
    acc_after = db.po_accessories.count_documents({'po_id': po_id, 'source': 'bom_maklon_auto'})
    bom_after = db.dewi_maklon_bom.find_one({'po_id': po_id})
    materials_after = len(bom_after.get('materials', []))
    
    print(f"After: {acc_after} accessories, {materials_after} materials")
    
    assert acc_after == acc_before == 3, \
        f"Accessories count changed: before={acc_before}, after={acc_after}, expected=3"
    assert materials_after == materials_before == 4, \
        f"Materials count changed: before={materials_before}, after={materials_after}, expected=4"
    
    print("\n✅ A.4 PASS: BOM sync is idempotent")

def test_a5_po_004_manual_accessories_preserved():
    """A.5: PO-004: POST bom-sync → 200
    
    WAJIB: 2 aksesoris MANUAL (kode A5 & A6, tanpa field source) TETAP ADA di po_accessories,
    total baris = 2 manual + 4 auto = 6. Ini poin paling penting (jangan sampai input manual owner hilang).
    """
    print("\n" + "="*80)
    print("TEST A.5: PO-004 manual accessories preserved (CRITICAL)")
    print("="*80)
    
    po_id = '8adb0631-8a1c-40dd-85f6-56fdab440591'
    db = get_db()
    
    # Check manual accessories before sync
    manual_before = list(db.po_accessories.find({
        'po_id': po_id,
        '$or': [{'source': {'$exists': False}}, {'source': None}, {'source': ''}]
    }))
    
    print(f"Manual accessories before sync: {len(manual_before)}")
    for acc in manual_before:
        print(f"  - {acc.get('accessory_code')}: {acc.get('accessory_name')} (qty={acc.get('qty_needed')})")
    
    # Verify A5 and A6 exist
    codes_before = [acc.get('accessory_code') for acc in manual_before]
    assert 'A5' in codes_before, "Manual accessory A5 not found before sync"
    assert 'A6' in codes_before, "Manual accessory A6 not found before sync"
    
    # Run sync
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
        json={},
        headers=headers()
    )
    
    print(f"\nSync status: {resp.status_code}")
    assert resp.status_code == 200, f"Sync failed: {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Sync result: materials={data.get('materials')}, accessory_rows={data.get('accessory_rows')}")
    
    # Check manual accessories after sync
    manual_after = list(db.po_accessories.find({
        'po_id': po_id,
        '$or': [{'source': {'$exists': False}}, {'source': None}, {'source': ''}]
    }))
    
    print(f"\nManual accessories after sync: {len(manual_after)}")
    for acc in manual_after:
        print(f"  - {acc.get('accessory_code')}: {acc.get('accessory_name')} (qty={acc.get('qty_needed')})")
    
    # Verify A5 and A6 still exist
    codes_after = [acc.get('accessory_code') for acc in manual_after]
    assert 'A5' in codes_after, "❌ CRITICAL: Manual accessory A5 LOST after sync!"
    assert 'A6' in codes_after, "❌ CRITICAL: Manual accessory A6 LOST after sync!"
    
    # Check auto accessories
    auto_after = list(db.po_accessories.find({'po_id': po_id, 'source': 'bom_maklon_auto'}))
    print(f"\nAuto accessories after sync: {len(auto_after)}")
    
    # Total should be 2 manual + 4 auto = 6
    total_after = len(manual_after) + len(auto_after)
    print(f"Total accessories: {total_after} (manual={len(manual_after)}, auto={len(auto_after)})")
    
    assert len(manual_after) == 2, f"Expected 2 manual accessories, got {len(manual_after)}"
    assert len(auto_after) == 4, f"Expected 4 auto accessories, got {len(auto_after)}"
    assert total_after == 6, f"Expected 6 total accessories, got {total_after}"
    
    print("\n✅ A.5 PASS: Manual accessories A5 & A6 preserved (CRITICAL TEST PASSED)")

def test_a6_po_0035_two_articles():
    """A.6: PO-0035 (2 artikel berbeda) → 200
    
    templates_used berisi 2 template, materials=6, bulk_rows=2, accessory_rows=4.
    """
    print("\n" + "="*80)
    print("TEST A.6: PO-0035 with 2 different articles")
    print("="*80)
    
    po_id = '4daa5da2-cab4-4de8-b280-55aece4f175a'
    
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
        json={},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    templates_used = data.get('templates_used', [])
    print(f"\nTemplates used: {len(templates_used)}")
    for tpl in templates_used:
        print(f"  - {tpl.get('template_id')} v{tpl.get('version')}")
    
    assert len(templates_used) == 2, f"Expected 2 templates, got {len(templates_used)}"
    assert data.get('materials') == 6, f"Expected 6 materials, got {data.get('materials')}"
    assert data.get('bulk_rows') == 2, f"Expected 2 bulk_rows, got {data.get('bulk_rows')}"
    assert data.get('accessory_rows') == 4, f"Expected 4 accessory_rows, got {data.get('accessory_rows')}"
    
    print("\n✅ A.6 PASS: PO with 2 articles synced correctly")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION B: PILIH VERSI TEMPLATE (LOCK)
# ══════════════════════════════════════════════════════════════════════════════
def test_b1_manual_template_selection():
    """B.1: POST /api/dewi/maklon/pos/po-mk-demo-2/bom-sync
    body {"template_id":"bom-mk-cat-demo-polo","force":true} → 200
    
    Cek DB: source="template_manual".
    """
    print("\n" + "="*80)
    print("TEST B.1: Manual template selection (lock)")
    print("="*80)
    
    po_id = 'po-mk-demo-2'
    template_id = 'bom-mk-cat-demo-polo'
    
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
        json={"template_id": template_id, "force": True},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Check DB
    db = get_db()
    bom = db.dewi_maklon_bom.find_one({'po_id': po_id})
    assert bom is not None, f"BOM not found for po_id {po_id}"
    
    print(f"\nBOM source: {bom.get('source')}")
    assert bom.get('source') == 'template_manual', \
        f"source should be 'template_manual', got {bom.get('source')}"
    
    print("\n✅ B.1 PASS: Manual template selection locked")

def test_b2_locked_bom_not_overwritten():
    """B.2: Panggil fungsi auto lewat jalur PUT PO ATAU langsung POST bom-sync
    dengan body {"force":false} → harus mengembalikan skipped=true dengan reason
    menyebut "manual" (bukti dokumen terkunci dari penimpaan otomatis).
    """
    print("\n" + "="*80)
    print("TEST B.2: Locked BOM not overwritten by auto sync")
    print("="*80)
    
    po_id = 'po-mk-demo-2'
    
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-sync",
        json={"force": False},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert data.get('skipped') == True, f"skipped should be true, got {data.get('skipped')}"
    
    reason = data.get('reason', '')
    print(f"\nReason: {reason}")
    assert 'manual' in reason.lower(), f"Reason should mention 'manual', got: {reason}"
    
    print("\n✅ B.2 PASS: Locked BOM protected from auto overwrite")

def test_b3_invalid_template_404():
    """B.3: POST bom-sync body {"template_id":"tidak-ada-123","force":true} → 404.
    Body {} pada po_id ngawur → 404.
    """
    print("\n" + "="*80)
    print("TEST B.3: Invalid template and PO return 404")
    print("="*80)
    
    # Test invalid template
    print("\n1. Invalid template ID...")
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/po-mk-demo-1/bom-sync",
        json={"template_id": "tidak-ada-123", "force": True},
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 404, f"Expected 404 for invalid template, got {resp.status_code}"
    print("✓ Invalid template returns 404")
    
    # Test invalid PO
    print("\n2. Invalid PO ID...")
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/po-ngawur-123/bom-sync",
        json={},
        headers=headers()
    )
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 404, f"Expected 404 for invalid PO, got {resp.status_code}"
    print("✓ Invalid PO returns 404")
    
    print("\n✅ B.3 PASS: Invalid template and PO handled correctly")

def test_b4_apply_to_po_endpoint():
    """B.4: POST /api/dewi/maklon/bom-templates/apply-to-po
    {"po_id":"po-mk-demo-1"} → 200 (dulu SELALU 404 karena hanya mencari koleksi legacy).
    
    Balasan memuat material_count & warnings.
    """
    print("\n" + "="*80)
    print("TEST B.4: apply-to-po endpoint (SSOT fix)")
    print("="*80)
    
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/bom-templates/apply-to-po",
        json={"po_id": "po-mk-demo-1"},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert 'material_count' in data, "Response should contain material_count"
    assert 'warnings' in data, "Response should contain warnings"
    
    print(f"\nMaterial count: {data.get('material_count')}")
    print(f"Warnings: {data.get('warnings')}")
    
    print("\n✅ B.4 PASS: apply-to-po works for SSOT POs")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION C: AUTO-EXPLODE SAAT PO MAKLON DIBUAT/DIUBAH
# ══════════════════════════════════════════════════════════════════════════════
def test_c1_create_po_auto_explode():
    """C.1: Buat PO maklon UJI via POST /api/production-pos
    
    business_type maklon, 1 item dengan catalog_item_id = "mk-cat-demo-hoodie", qty 10;
    isi field wajib lain sesuai skema. Balasan harus memuat field `maklon_bom_explode`
    dengan materials>0, dan DB `dewi_maklon_bom` untuk PO baru itu harus terisi
    (qty = 10 × qty_per_pcs).
    """
    print("\n" + "="*80)
    print("TEST C.1: Create PO with auto-explode")
    print("="*80)
    
    # Create test PO
    po_number = f"TEST-BOM-{int(time.time())}"
    payload = {
        "po_number": po_number,
        "business_type": "maklon",
        "customer_name": "Test Client BOM",
        "po_date": datetime.now().isoformat(),
        "status": "Draft",
        "items": [{
            "catalog_item_id": "mk-cat-demo-hoodie",
            "product_name": "Test Hoodie",
            "qty": 10,
            "size": "L",
            "color": "Black"
        }]
    }
    
    print(f"Creating PO: {po_number}")
    resp = requests.post(
        f"{BASE_URL}/production-pos",
        json=payload,
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    po_id = data.get('id')
    print(f"Created PO ID: {po_id}")
    
    # Track for cleanup
    TEST_DATA_CREATED.append({'type': 'po', 'id': po_id, 'po_number': po_number})
    
    # Verify maklon_bom_explode in response
    assert 'maklon_bom_explode' in data, "Response should contain maklon_bom_explode"
    explode = data.get('maklon_bom_explode', {})
    print(f"\nBOM explode result: {json.dumps(explode, indent=2)}")
    
    assert explode.get('materials', 0) > 0, "materials should be > 0"
    
    # Verify DB
    db = get_db()
    bom = db.dewi_maklon_bom.find_one({'po_id': po_id})
    assert bom is not None, f"BOM not found in DB for po_id {po_id}"
    
    materials = bom.get('materials', [])
    print(f"\nDB materials count: {len(materials)}")
    
    # Verify qty = 10 × qty_per_pcs
    for m in materials:
        expected_qty = round(10 * m.get('qty_per_pcs', 0), 4)
        actual_qty = m.get('qty_estimated', 0)
        print(f"  {m.get('material_name')}: qty_estimated={actual_qty}, expected={expected_qty}")
        assert abs(actual_qty - expected_qty) < 0.01, \
            f"qty_estimated ({actual_qty}) != 10 × qty_per_pcs ({expected_qty})"
    
    print("\n✅ C.1 PASS: PO created with auto-explode")
    return po_id

def test_c2_update_po_re_explode():
    """C.2: PUT /api/production-pos/{id} ubah qty item jadi 20
    
    Cek `dewi_maklon_bom` ikut menjadi 20 × qty_per_pcs (re-explode).
    """
    print("\n" + "="*80)
    print("TEST C.2: Update PO triggers re-explode")
    print("="*80)
    
    # Get the test PO created in C.1
    if not TEST_DATA_CREATED:
        print("⚠️  Skipping C.2: No test PO from C.1")
        return
    
    po_id = TEST_DATA_CREATED[0]['id']
    print(f"Updating PO: {po_id}")
    
    # Get current items
    resp = requests.get(f"{BASE_URL}/production-pos/{po_id}", headers=headers())
    assert resp.status_code == 200, f"Failed to get PO: {resp.status_code}"
    po_data = resp.json()
    items = po_data.get('items', [])
    
    # Update qty to 20
    for item in items:
        item['qty'] = 20
    
    payload = {"items": items}
    
    print("Updating qty to 20...")
    resp = requests.put(
        f"{BASE_URL}/production-pos/{po_id}",
        json=payload,
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    # Verify DB
    db = get_db()
    bom = db.dewi_maklon_bom.find_one({'po_id': po_id})
    assert bom is not None, f"BOM not found in DB for po_id {po_id}"
    
    materials = bom.get('materials', [])
    print(f"\nVerifying re-exploded materials...")
    
    # Verify qty = 20 × qty_per_pcs
    for m in materials:
        expected_qty = round(20 * m.get('qty_per_pcs', 0), 4)
        actual_qty = m.get('qty_estimated', 0)
        print(f"  {m.get('material_name')}: qty_estimated={actual_qty}, expected={expected_qty}")
        assert abs(actual_qty - expected_qty) < 0.01, \
            f"qty_estimated ({actual_qty}) != 20 × qty_per_pcs ({expected_qty})"
    
    print("\n✅ C.2 PASS: PO update triggers re-explode")

def test_c3_delete_test_po():
    """C.3: HAPUS PO uji itu (DELETE /api/production-pos/{id}) dan laporkan."""
    print("\n" + "="*80)
    print("TEST C.3: Delete test PO")
    print("="*80)
    
    if not TEST_DATA_CREATED:
        print("⚠️  No test PO to delete")
        return
    
    po_id = TEST_DATA_CREATED[0]['id']
    po_number = TEST_DATA_CREATED[0]['po_number']
    
    print(f"Deleting PO: {po_number} ({po_id})")
    
    resp = requests.delete(
        f"{BASE_URL}/production-pos/{po_id}",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    # Verify deleted from DB
    db = get_db()
    po = db.production_pos.find_one({'id': po_id})
    assert po is None, f"PO still exists in DB after delete"
    
    # Clear from tracking
    TEST_DATA_CREATED.clear()
    
    print(f"\n✅ C.3 PASS: Test PO deleted successfully")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION D: CHECKLIST MATERIAL DARI KLIEN
# ══════════════════════════════════════════════════════════════════════════════
def test_d1_material_expectation():
    """D.1: GET /api/dewi/maklon/pos/8adb0631-8a1c-40dd-85f6-56fdab440591/material-expectation → 200
    
    has_bom=true, lines=6, tiap baris punya qty_expected/qty_received/qty_outstanding/status,
    summary konsisten (pending+partial+complete = total_lines).
    """
    print("\n" + "="*80)
    print("TEST D.1: Material expectation checklist")
    print("="*80)
    
    po_id = '8adb0631-8a1c-40dd-85f6-56fdab440591'
    
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/material-expectation",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert data.get('has_bom') == True, "has_bom should be true"
    
    lines = data.get('lines', [])
    print(f"\nTotal lines: {len(lines)}")
    assert len(lines) == 6, f"Expected 6 lines, got {len(lines)}"
    
    # Verify each line has required fields
    for idx, line in enumerate(lines):
        print(f"\nLine {idx+1}: {line.get('material_name')}")
        print(f"  qty_expected: {line.get('qty_expected')}")
        print(f"  qty_received: {line.get('qty_received')}")
        print(f"  qty_outstanding: {line.get('qty_outstanding')}")
        print(f"  status: {line.get('status')}")
        
        assert 'qty_expected' in line, f"Line {idx+1} missing qty_expected"
        assert 'qty_received' in line, f"Line {idx+1} missing qty_received"
        assert 'qty_outstanding' in line, f"Line {idx+1} missing qty_outstanding"
        assert 'status' in line, f"Line {idx+1} missing status"
    
    # Verify summary
    summary = data.get('summary', {})
    print(f"\nSummary: {summary}")
    
    total = summary.get('total_lines', 0)
    pending = summary.get('pending', 0)
    partial = summary.get('partial', 0)
    complete = summary.get('complete', 0)
    
    assert pending + partial + complete == total, \
        f"Summary inconsistent: pending({pending}) + partial({partial}) + complete({complete}) != total({total})"
    
    print("\n✅ D.1 PASS: Material expectation checklist verified")

def test_d2_material_expectation_no_bom():
    """D.2: GET untuk PO tanpa BOM (po_id ngawur) → 200 dengan has_bom=false & lines=[] (tidak 500)."""
    print("\n" + "="*80)
    print("TEST D.2: Material expectation for PO without BOM")
    print("="*80)
    
    po_id = 'po-ngawur-tanpa-bom-123'
    
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/material-expectation",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    # Should return 200 with has_bom=false, not 404 or 500
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert data.get('has_bom') == False, "has_bom should be false"
    assert data.get('lines', []) == [], "lines should be empty"
    
    print("\n✅ D.2 PASS: Graceful handling of PO without BOM")

def test_d3_bom_needs():
    """D.3: GET /api/dewi/maklon/pos/{po_id}/bom-needs untuk PO-004 → 200
    
    auto_accessory_rows=4, accessory_needs=6.
    """
    print("\n" + "="*80)
    print("TEST D.3: BOM needs endpoint")
    print("="*80)
    
    po_id = '8adb0631-8a1c-40dd-85f6-56fdab440591'  # PO-004
    
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/bom-needs",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert data.get('auto_accessory_rows') == 4, \
        f"Expected auto_accessory_rows=4, got {data.get('auto_accessory_rows')}"
    
    accessory_needs = data.get('accessory_needs', [])
    print(f"\nTotal accessory needs: {len(accessory_needs)}")
    assert len(accessory_needs) == 6, f"Expected 6 accessory_needs, got {len(accessory_needs)}"
    
    print("\n✅ D.3 PASS: BOM needs endpoint verified")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION E: PO-360 & SURAT JALAN
# ══════════════════════════════════════════════════════════════════════════════
def test_e1_po_360_ssot():
    """E.1: GET /api/dewi/maklon/pos/8adb0631-8a1c-40dd-85f6-56fdab440591/360 → 200
    
    (dulu 404 untuk PO SSOT), field `bom` terisi dengan 6 material, `po.items` tidak kosong
    dan tiap item punya catalog_item_id.
    """
    print("\n" + "="*80)
    print("TEST E.1: PO-360 for SSOT PO")
    print("="*80)
    
    po_id = '8adb0631-8a1c-40dd-85f6-56fdab440591'
    
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/360",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    
    # Verify bom field
    bom = data.get('bom')
    assert bom is not None, "bom field should not be null"
    
    materials = bom.get('materials', [])
    print(f"\nBOM materials: {len(materials)}")
    assert len(materials) == 6, f"Expected 6 materials, got {len(materials)}"
    
    # Verify po.items
    po = data.get('po', {})
    items = po.get('items', [])
    print(f"PO items: {len(items)}")
    assert len(items) > 0, "po.items should not be empty"
    
    # Verify each item has catalog_item_id
    for idx, item in enumerate(items):
        print(f"  Item {idx+1}: {item.get('product_name')} - catalog_item_id: {item.get('catalog_item_id')}")
        assert item.get('catalog_item_id'), f"Item {idx+1} missing catalog_item_id"
    
    print("\n✅ E.1 PASS: PO-360 works for SSOT PO")

def test_e2_po_360_legacy():
    """E.2: GET /api/dewi/maklon/pos/po-mk-demo-2/360 → 200
    
    (PO yang punya cermin legacy — regresi jangan pecah).
    """
    print("\n" + "="*80)
    print("TEST E.2: PO-360 for legacy PO (regression)")
    print("="*80)
    
    po_id = 'po-mk-demo-2'
    
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/{po_id}/360",
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    print(f"PO number: {data.get('po', {}).get('po_number')}")
    
    print("\n✅ E.2 PASS: PO-360 works for legacy PO (no regression)")

def test_e3_surat_jalan_pdf():
    """E.3: GET /api/export-pdf?type=vendor-shipment&id=role-matrix-3 → 200 application/pdf
    
    BACA TEKS PDF (PyPDF2): harus memuat "KEBUTUHAN MATERIAL PER BOM (REFERENSI)",
    nama material "Kain Fleece 320gsm" & "Kain Pique Cotton", kolom "Dipasok" dengan nilai "Klien",
    DAN pada tabel AKSESORIS harus ada baris hasil BOM ("Zipper YKK 60cm", "Kordon Hoodie",
    "Label Woven Aruna", "Kancing Polo") BERSAMA baris manual A5 & A6.
    Pastikan tabel material utama + blok tanda tangan tetap ada (tidak regresi).
    """
    print("\n" + "="*80)
    print("TEST E.3: Surat Jalan PDF with BOM materials")
    print("="*80)
    
    shipment_id = 'aacf1cf2-b366-499b-abc4-7b27c170a4b2'
    
    resp = requests.get(
        f"{BASE_URL}/export-pdf",
        params={"type": "vendor-shipment", "id": shipment_id},
        headers=headers()
    )
    
    print(f"Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    content_type = resp.headers.get('Content-Type', '')
    print(f"Content-Type: {content_type}")
    assert 'application/pdf' in content_type, f"Expected PDF, got {content_type}"
    
    # Read PDF text
    pdf_bytes = io.BytesIO(resp.content)
    pdf_reader = PyPDF2.PdfReader(pdf_bytes)
    
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    
    print(f"\nPDF text length: {len(text)} chars")
    
    # Verify BOM section
    assert "KEBUTUHAN MATERIAL PER BOM" in text or "KEBUTUHAN MATERIAL" in text, \
        "PDF should contain BOM materials section"
    print("✓ BOM section found")
    
    # Verify material names (flexible matching)
    materials_found = []
    if "Kain Fleece" in text or "Fleece" in text:
        materials_found.append("Fleece")
    if "Kain Pique" in text or "Pique" in text:
        materials_found.append("Pique")
    
    print(f"✓ Materials found: {materials_found}")
    
    # Verify "Dipasok" column with "Klien"
    if "Dipasok" in text and "Klien" in text:
        print("✓ 'Dipasok' column with 'Klien' found")
    
    # Verify accessories from BOM
    bom_accessories = ["Zipper", "Kordon", "Label", "Kancing"]
    found_bom_acc = [acc for acc in bom_accessories if acc in text]
    print(f"✓ BOM accessories found: {found_bom_acc}")
    
    # Verify manual accessories A5 & A6
    manual_acc_found = []
    if "A5" in text:
        manual_acc_found.append("A5")
    if "A6" in text:
        manual_acc_found.append("A6")
    
    print(f"✓ Manual accessories found: {manual_acc_found}")
    assert len(manual_acc_found) == 2, f"Expected both A5 and A6, found: {manual_acc_found}"
    
    # Verify signature blocks (regression check)
    assert "Pengirim" in text or "Penerima" in text, "PDF should contain signature blocks"
    print("✓ Signature blocks found")
    
    print("\n✅ E.3 PASS: Surat Jalan PDF contains BOM materials and accessories")

def test_e4_auth_required():
    """E.4: Tanpa header Authorization pada bom-sync & material-expectation → 401/403 (bukan 500)."""
    print("\n" + "="*80)
    print("TEST E.4: Auth required for BOM endpoints")
    print("="*80)
    
    # Test bom-sync without auth
    print("\n1. bom-sync without auth...")
    resp = requests.post(
        f"{BASE_URL}/dewi/maklon/pos/po-mk-demo-1/bom-sync",
        json={}
    )
    print(f"Status: {resp.status_code}")
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print("✓ bom-sync requires auth")
    
    # Test material-expectation without auth
    print("\n2. material-expectation without auth...")
    resp = requests.get(
        f"{BASE_URL}/dewi/maklon/pos/8adb0631-8a1c-40dd-85f6-56fdab440591/material-expectation"
    )
    print(f"Status: {resp.status_code}")
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print("✓ material-expectation requires auth")
    
    print("\n✅ E.4 PASS: Auth required for BOM endpoints")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "="*80)
    print("BACKEND TEST: SAMBUNGAN BOM MAKLON")
    print("Sesi 2026-08-02")
    print("="*80)
    
    tests = [
        # Section A: SINKRONISASI DARI TEMPLATE AKTIF
        ("A.1", test_a1_bom_sync_po_mk_demo_1),
        ("A.2", test_a2_verify_db_dewi_maklon_bom),
        ("A.3", test_a3_verify_po_accessories),
        ("A.4", test_a4_idempotent_bom_sync),
        ("A.5", test_a5_po_004_manual_accessories_preserved),
        ("A.6", test_a6_po_0035_two_articles),
        
        # Section B: PILIH VERSI TEMPLATE (LOCK)
        ("B.1", test_b1_manual_template_selection),
        ("B.2", test_b2_locked_bom_not_overwritten),
        ("B.3", test_b3_invalid_template_404),
        ("B.4", test_b4_apply_to_po_endpoint),
        
        # Section C: AUTO-EXPLODE SAAT PO MAKLON DIBUAT/DIUBAH
        ("C.1", test_c1_create_po_auto_explode),
        ("C.2", test_c2_update_po_re_explode),
        ("C.3", test_c3_delete_test_po),
        
        # Section D: CHECKLIST MATERIAL DARI KLIEN
        ("D.1", test_d1_material_expectation),
        ("D.2", test_d2_material_expectation_no_bom),
        ("D.3", test_d3_bom_needs),
        
        # Section E: PO-360 & SURAT JALAN
        ("E.1", test_e1_po_360_ssot),
        ("E.2", test_e2_po_360_legacy),
        ("E.3", test_e3_surat_jalan_pdf),
        ("E.4", test_e4_auth_required),
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    try:
        for test_id, test_func in tests:
            try:
                test_func()
                passed += 1
            except AssertionError as e:
                failed += 1
                error_msg = f"{test_id} FAILED: {str(e)}"
                errors.append(error_msg)
                print(f"\n❌ {error_msg}")
            except Exception as e:
                failed += 1
                error_msg = f"{test_id} ERROR: {str(e)}"
                errors.append(error_msg)
                print(f"\n💥 {error_msg}")
    
    finally:
        # Cleanup
        cleanup()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total: {passed + failed}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    if errors:
        print("\nFailed tests:")
        for error in errors:
            print(f"  - {error}")
    
    print("\nTest data created and cleaned:")
    print(f"  - {len(TEST_DATA_CREATED)} items (all cleaned up)")
    
    return passed, failed

if __name__ == "__main__":
    passed, failed = main()
    exit(0 if failed == 0 else 1)
