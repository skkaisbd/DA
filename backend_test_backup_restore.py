#!/usr/bin/env python3
"""
Backend Test: Database Backup & Restore Bug Fixes
Sesi 2026-08-01 - Verifikasi perbaikan download & upload
"""

import requests
import time
import os
import zipfile
import io
import json
from pathlib import Path

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
BACKUP_FILE = "/tmp/bk/backup.zip"

# Test artifacts tracking
created_backups = []
created_files = []

def login_once():
    """Login sekali dan reuse token (rate limit 10/60s)"""
    print("\n=== LOGIN ===")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    print(f"✅ Login successful, token: {token[:20]}...")
    return token

def test_a_download_via_ticket(token):
    """A. UNDUH lewat TIKET (fitur baru — akar bug 'tidak bisa download')"""
    print("\n" + "="*80)
    print("SECTION A: DOWNLOAD VIA TICKET")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # A1: GET /list → ambil backup_id, pastikan tidak ada .uploads_tmp/.download_tmp
    print("\n[A1] GET /api/admin/backup/list")
    resp = requests.get(f"{BASE_URL}/admin/backup/list", headers=headers)
    assert resp.status_code == 200, f"List failed: {resp.status_code}"
    data = resp.json()
    backups = data.get("backups", [])
    assert len(backups) > 0, "No backups found"
    
    # Check no internal folders
    internal_folders = [b for b in backups if b.get("backup_id", "").startswith(".")]
    assert len(internal_folders) == 0, f"Found internal folders: {internal_folders}"
    print(f"✅ A1 PASS: Found {len(backups)} backups, no internal folders (.uploads_tmp/.download_tmp)")
    
    # Pick first backup
    backup_id = backups[0]["backup_id"]
    print(f"   Using backup_id: {backup_id}")
    
    # A2: POST /download-ticket/{backup_id} → 200 dengan ticket, url, filename, expires_in
    print(f"\n[A2] POST /api/admin/backup/download-ticket/{backup_id}")
    resp = requests.post(f"{BASE_URL}/admin/backup/download-ticket/{backup_id}", headers=headers)
    assert resp.status_code == 200, f"Download ticket failed: {resp.status_code} {resp.text}"
    ticket_data = resp.json()
    assert "ticket" in ticket_data, "No ticket in response"
    assert "url" in ticket_data, "No url in response"
    assert "filename" in ticket_data, "No filename in response"
    assert "expires_in" in ticket_data, "No expires_in in response"
    print(f"✅ A2 PASS: Ticket issued")
    print(f"   ticket: {ticket_data['ticket'][:20]}...")
    print(f"   url: {ticket_data['url']}")
    print(f"   filename: {ticket_data['filename']}")
    print(f"   expires_in: {ticket_data['expires_in']}s")
    
    download_url = ticket_data["url"]
    ticket = ticket_data["ticket"]
    
    # A3: GET {url} TANPA Authorization → 200, ZIP valid
    # URL is relative, need to prepend base URL
    if download_url.startswith("/api"):
        full_download_url = f"https://da37-cmt-bridge.preview.emergentagent.com{download_url}"
    else:
        full_download_url = download_url
    
    print(f"\n[A3] GET {full_download_url} (WITHOUT Authorization header)")
    resp = requests.get(full_download_url)  # NO headers
    assert resp.status_code == 200, f"Download failed: {resp.status_code}"
    assert resp.headers.get("Content-Type") == "application/zip", f"Wrong content type: {resp.headers.get('Content-Type')}"
    assert "attachment" in resp.headers.get("Content-Disposition", ""), "No attachment disposition"
    
    # Check ZIP magic bytes
    content = resp.content
    assert len(content) > 4, "Content too short"
    assert content[:4] == b'PK\x03\x04', f"Not a valid ZIP (magic bytes: {content[:4].hex()})"
    
    # Verify ZIP can be opened and contains .bson.gz
    zip_buffer = io.BytesIO(content)
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        files = zf.namelist()
        bson_files = [f for f in files if f.endswith('.bson') or f.endswith('.bson.gz')]
        assert len(bson_files) > 0, f"No .bson/.bson.gz files in ZIP (found: {files[:5]})"
    
    print(f"✅ A3 PASS: Downloaded {len(content)} bytes, valid ZIP with {len(bson_files)} BSON files")
    
    # A4: GET /download/{backup_id}?ticket=FAKE → 403
    print(f"\n[A4] GET /api/admin/backup/download/{backup_id}?ticket=FAKE-TICKET-123")
    resp = requests.get(f"{BASE_URL}/admin/backup/download/{backup_id}?ticket=FAKE-TICKET-123")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    print(f"✅ A4 PASS: Fake ticket rejected with 403")
    
    # A5: GET /download/{backup_id} WITH Authorization (jalur lama) → 200
    print(f"\n[A5] GET /api/admin/backup/download/{backup_id} (WITH Authorization header - old path)")
    resp = requests.get(f"{BASE_URL}/admin/backup/download/{backup_id}", headers=headers)
    assert resp.status_code == 200, f"Old path failed: {resp.status_code}"
    assert resp.content[:4] == b'PK\x03\x04', "Not a valid ZIP"
    print(f"✅ A5 PASS: Old path (with Authorization) still works, {len(resp.content)} bytes")
    
    # A6: Path traversal protection
    print(f"\n[A6] GET /api/admin/backup/download/..%2F..%2Fetc (path traversal)")
    resp = requests.get(f"{BASE_URL}/admin/backup/download/..%2F..%2Fetc", headers=headers)
    assert resp.status_code in [400, 404], f"Expected 400/404, got {resp.status_code}"
    print(f"✅ A6 PASS: Path traversal blocked with {resp.status_code}")
    
    # A7: Check .download_tmp cleanup
    print(f"\n[A7] Check /app/backups/.download_tmp cleanup")
    download_tmp = Path("/app/backups/.download_tmp")
    if download_tmp.exists():
        remaining = list(download_tmp.iterdir())
        assert len(remaining) < 2, f"Too many temp folders: {len(remaining)}"
        print(f"✅ A7 PASS: .download_tmp has {len(remaining)} items (acceptable)")
    else:
        print(f"✅ A7 PASS: .download_tmp does not exist (cleaned)")

def test_b_upload_single_request(token):
    """B. UNGGAH satu-permintaan"""
    print("\n" + "="*80)
    print("SECTION B: UPLOAD SINGLE REQUEST")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # B1: Upload REAL owner backup
    print(f"\n[B1] POST /api/admin/backup/upload-file (real backup: {BACKUP_FILE})")
    with open(BACKUP_FILE, 'rb') as f:
        files = {'file': ('backup.zip', f, 'application/zip')}
        resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", headers=headers, files=files)
    
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    upload_data = resp.json()
    assert "backup_id" in upload_data, "No backup_id in response"
    assert "database_in_backup" in upload_data, "No database_in_backup in response"
    assert "collections_found" in upload_data, "No collections_found in response"
    assert upload_data["collections_found"] > 100, f"Too few collections: {upload_data['collections_found']}"
    
    backup_id = upload_data["backup_id"]
    created_backups.append(backup_id)
    
    print(f"✅ B1 PASS: Upload successful")
    print(f"   backup_id: {backup_id}")
    print(f"   database_in_backup: {upload_data['database_in_backup']}")
    print(f"   collections_found: {upload_data['collections_found']}")
    
    # B2: GET /{backup_id}/collections
    print(f"\n[B2] GET /api/admin/backup/{backup_id}/collections")
    resp = requests.get(f"{BASE_URL}/admin/backup/{backup_id}/collections", headers=headers)
    assert resp.status_code == 200, f"Get collections failed: {resp.status_code}"
    coll_data = resp.json()
    assert coll_data.get("total_collections", 0) > 100, f"Too few collections: {coll_data.get('total_collections')}"
    assert coll_data.get("database") == "test_database", f"Wrong database: {coll_data.get('database')}"
    print(f"✅ B2 PASS: Collections readable, total={coll_data['total_collections']}, database={coll_data['database']}")
    
    # B3: NEGATIVE VALIDATION
    print(f"\n[B3] NEGATIVE VALIDATION")
    
    # B3a: Upload text file renamed to .zip
    print(f"  [B3a] Upload text file renamed to .zip")
    fake_zip = io.BytesIO(b"This is not a ZIP file")
    files = {'file': ('fake.zip', fake_zip, 'application/zip')}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", headers=headers, files=files)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    error_data = resp.json()
    # Check if it's the new format (message/reason/hint) or old format (detail)
    if "message" in error_data:
        assert "reason" in error_data, "No reason in error"
        assert "hint" in error_data, "No hint in error"
        print(f"  ✅ B3a PASS: Fake ZIP rejected with 400 (new format)")
        print(f"     message: {error_data['message']}")
        print(f"     reason: {error_data['reason']}")
    elif "detail" in error_data:
        # Old format - check if detail is an object with message/reason/hint
        detail = error_data["detail"]
        if isinstance(detail, dict):
            assert "message" in detail and "reason" in detail and "hint" in detail, f"Detail missing fields: {detail}"
            print(f"  ✅ B3a PASS: Fake ZIP rejected with 400 (detail object format)")
            print(f"     message: {detail['message']}")
            print(f"     reason: {detail['reason']}")
        else:
            print(f"  ✅ B3a PASS: Fake ZIP rejected with 400 (detail string format)")
            print(f"     detail: {detail}")
    else:
        raise AssertionError(f"Unexpected error format: {error_data}")
    
    # B3b: Upload valid ZIP without .bson files
    print(f"  [B3b] Upload valid ZIP without .bson files")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("readme.txt", "This is a text file")
    zip_buffer.seek(0)
    files = {'file': ('no_bson.zip', zip_buffer, 'application/zip')}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", headers=headers, files=files)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    error_data = resp.json()
    # Check format
    if "message" in error_data:
        assert "reason" in error_data and "hint" in error_data
        print(f"  ✅ B3b PASS: ZIP without BSON rejected with 400 (new format)")
        print(f"     message: {error_data['message']}")
    elif "detail" in error_data:
        detail = error_data["detail"]
        if isinstance(detail, dict):
            assert "message" in detail and "reason" in detail and "hint" in detail
            print(f"  ✅ B3b PASS: ZIP without BSON rejected with 400 (detail object)")
            print(f"     message: {detail['message']}")
        else:
            print(f"  ✅ B3b PASS: ZIP without BSON rejected with 400")
            print(f"     detail: {detail}")
    
    # B3c: Upload 0 byte file
    print(f"  [B3c] Upload 0 byte file")
    empty_file = io.BytesIO(b"")
    files = {'file': ('empty.zip', empty_file, 'application/zip')}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", headers=headers, files=files)
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    error_data = resp.json()
    # Check format
    if "message" in error_data:
        assert "reason" in error_data and "hint" in error_data
        print(f"  ✅ B3c PASS: Empty file rejected with 400 (new format)")
        print(f"     message: {error_data['message']}")
    elif "detail" in error_data:
        detail = error_data["detail"]
        if isinstance(detail, dict):
            assert "message" in detail and "reason" in detail and "hint" in detail
            print(f"  ✅ B3c PASS: Empty file rejected with 400 (detail object)")
            print(f"     message: {detail['message']}")
        else:
            print(f"  ✅ B3c PASS: Empty file rejected with 400")
            print(f"     detail: {detail}")
    
    # B4: NESTED STRUCTURE
    print(f"\n[B4] NESTED STRUCTURE (wrapper folder)")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Create nested structure: manual_x/test_database/dummy_col.bson.gz
        import gzip
        dummy_bson = gzip.compress(b'{"_id": 1, "test": "data"}')
        zf.writestr("manual_x/test_database/dummy_col.bson.gz", dummy_bson)
        zf.writestr("manual_x/metadata.json", '{"created_at": "2026-08-01"}')
    
    zip_buffer.seek(0)
    files = {'file': ('nested.zip', zip_buffer, 'application/zip')}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", headers=headers, files=files)
    assert resp.status_code == 200, f"Nested upload failed: {resp.status_code} {resp.text}"
    nested_data = resp.json()
    nested_backup_id = nested_data["backup_id"]
    created_backups.append(nested_backup_id)
    
    # Check collections
    resp = requests.get(f"{BASE_URL}/admin/backup/{nested_backup_id}/collections", headers=headers)
    assert resp.status_code == 200, f"Get nested collections failed: {resp.status_code}"
    coll_data = resp.json()
    collections = coll_data.get("collections", [])
    collection_names = [c.get("name") for c in collections]
    assert "dummy_col" in collection_names, f"dummy_col not found in {collection_names}"
    print(f"✅ B4 PASS: Nested structure flattened, dummy_col found in collections")

def test_c_chunked_upload(token):
    """C. UNGGAH BERPOTONG (chunked)"""
    print("\n" + "="*80)
    print("SECTION C: CHUNKED UPLOAD")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Read backup file
    with open(BACKUP_FILE, 'rb') as f:
        file_content = f.read()
    
    file_size = len(file_content)
    chunk_size = file_size // 3 + 1
    chunks = [file_content[i:i+chunk_size] for i in range(0, file_size, chunk_size)]
    total_chunks = len(chunks)
    
    print(f"File size: {file_size} bytes, splitting into {total_chunks} chunks")
    
    # C1: POST /upload-init
    print(f"\n[C1] POST /api/admin/backup/upload-init")
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-init", headers=headers, json={
        "filename": "uji_chunk.zip",
        "total_size": file_size,
        "total_chunks": total_chunks
    })
    assert resp.status_code == 200, f"Upload init failed: {resp.status_code} {resp.text}"
    init_data = resp.json()
    assert "upload_id" in init_data, "No upload_id in response"
    upload_id = init_data["upload_id"]
    print(f"✅ C1 PASS: Upload session created, upload_id: {upload_id}")
    
    # C2: POST /upload-chunk for each chunk
    print(f"\n[C2] POST /api/admin/backup/upload-chunk (x{total_chunks})")
    for idx, chunk in enumerate(chunks):
        chunk_file = io.BytesIO(chunk)
        files = {
            'file': (f'chunk_{idx}', chunk_file, 'application/octet-stream')
        }
        data = {
            'upload_id': upload_id,
            'index': str(idx)
        }
        resp = requests.post(f"{BASE_URL}/admin/backup/upload-chunk", headers=headers, files=files, data=data)
        assert resp.status_code == 200, f"Chunk {idx} upload failed: {resp.status_code} {resp.text}"
        chunk_data = resp.json()
        assert chunk_data.get("received_chunks") == idx + 1, f"Wrong received_chunks: {chunk_data.get('received_chunks')}"
        print(f"  Chunk {idx}: {len(chunk)} bytes, received_chunks={chunk_data['received_chunks']}")
    
    print(f"✅ C2 PASS: All {total_chunks} chunks uploaded")
    
    # C3: POST /upload-complete
    print(f"\n[C3] POST /api/admin/backup/upload-complete")
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-complete", headers=headers, json={
        "upload_id": upload_id
    })
    assert resp.status_code == 200, f"Upload complete failed: {resp.status_code} {resp.text}"
    complete_data = resp.json()
    assert "backup_id" in complete_data, "No backup_id in response"
    assert complete_data.get("collections_found", 0) > 100, f"Too few collections: {complete_data.get('collections_found')}"
    
    chunked_backup_id = complete_data["backup_id"]
    created_backups.append(chunked_backup_id)
    
    print(f"✅ C3 PASS: Chunked upload completed")
    print(f"   backup_id: {chunked_backup_id}")
    print(f"   collections_found: {complete_data['collections_found']}")
    
    # Verify collections readable
    resp = requests.get(f"{BASE_URL}/admin/backup/{chunked_backup_id}/collections", headers=headers)
    assert resp.status_code == 200, f"Get collections failed: {resp.status_code}"
    print(f"✅ C3 PASS: Collections readable from chunked upload")
    
    # C4: NEGATIVE TESTS
    print(f"\n[C4] NEGATIVE TESTS")
    
    # C4a: upload-chunk with fake upload_id
    print(f"  [C4a] upload-chunk with fake upload_id")
    chunk_file = io.BytesIO(b"fake chunk")
    files = {'file': ('chunk', chunk_file, 'application/octet-stream')}
    data = {'upload_id': 'FAKE-UPLOAD-ID', 'index': '0'}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-chunk", headers=headers, files=files, data=data)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    print(f"  ✅ C4a PASS: Fake upload_id rejected with 404")
    
    # C4b: upload-complete with insufficient chunks
    print(f"  [C4b] upload-complete with insufficient chunks")
    # Create new session
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-init", headers=headers, json={
        "filename": "incomplete.zip",
        "total_size": 1000,
        "total_chunks": 3
    })
    incomplete_upload_id = resp.json()["upload_id"]
    
    # Upload only 1 chunk
    chunk_file = io.BytesIO(b"x" * 300)
    files = {'file': ('chunk', chunk_file, 'application/octet-stream')}
    data = {'upload_id': incomplete_upload_id, 'index': '0'}
    requests.post(f"{BASE_URL}/admin/backup/upload-chunk", headers=headers, files=files, data=data)
    
    # Try to complete
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-complete", headers=headers, json={
        "upload_id": incomplete_upload_id
    })
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    print(f"  ✅ C4b PASS: Incomplete chunks rejected with 400")
    
    # C4c: upload-complete with fake upload_id
    print(f"  [C4c] upload-complete with fake upload_id")
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-complete", headers=headers, json={
        "upload_id": "FAKE-UPLOAD-ID"
    })
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    print(f"  ✅ C4c PASS: Fake upload_id rejected with 404")

def test_d_restore_regression(token):
    """D. REGRESI restore (INGAT ATURAN KESELAMATAN)"""
    print("\n" + "="*80)
    print("SECTION D: RESTORE REGRESSION (SAFETY RULES APPLIED)")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get existing backup
    resp = requests.get(f"{BASE_URL}/admin/backup/list", headers=headers)
    backups = resp.json().get("backups", [])
    existing_backup = backups[0]["backup_id"]
    
    # D1: restore-selective with mode 'merge' on unimportant collection
    print(f"\n[D1] POST /api/admin/backup/restore-selective (SAFE: rate_limit_buckets, mode=merge)")
    resp = requests.post(f"{BASE_URL}/admin/backup/restore-selective", headers=headers, json={
        "backup_id": existing_backup,
        "collections": ["rate_limit_buckets"],
        "mode": "merge",
        "confirm": True
    })
    assert resp.status_code == 200, f"Restore selective failed: {resp.status_code} {resp.text}"
    restore_data = resp.json()
    print(f"✅ D1 PASS: Selective restore successful")
    print(f"   total_restored: {restore_data.get('total_restored', 0)}")
    print(f"   total_failed: {restore_data.get('total_failed', 0)}")
    
    # D2: restore-selective without confirm
    print(f"\n[D2] POST /api/admin/backup/restore-selective (without confirm)")
    resp = requests.post(f"{BASE_URL}/admin/backup/restore-selective", headers=headers, json={
        "backup_id": existing_backup,
        "collections": ["rate_limit_buckets"],
        "mode": "merge"
        # NO confirm field
    })
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    print(f"✅ D2 PASS: Missing confirm rejected with 400")
    
    # D3: Create backup, verify, delete
    print(f"\n[D3] POST /api/admin/backup/create (create test backup)")
    resp = requests.post(f"{BASE_URL}/admin/backup/create", headers=headers, json={
        "backup_name": "uji_agent_backup",
        "notify": False
    })
    assert resp.status_code == 200, f"Create backup failed: {resp.status_code} {resp.text}"
    print(f"✅ D3a PASS: Backup creation started")
    
    # Wait for completion
    print(f"  Waiting 10 seconds for backup to complete...")
    time.sleep(10)
    
    # Check list
    resp = requests.get(f"{BASE_URL}/admin/backup/list", headers=headers)
    backups = resp.json().get("backups", [])
    test_backup = [b for b in backups if b["backup_id"] == "uji_agent_backup"]
    assert len(test_backup) == 1, f"Test backup not found in list"
    assert test_backup[0].get("status") == "success", f"Backup status: {test_backup[0].get('status')}"
    print(f"✅ D3b PASS: Backup 'uji_agent_backup' found with status=success")
    
    # Delete
    resp = requests.delete(f"{BASE_URL}/admin/backup/uji_agent_backup", headers=headers)
    assert resp.status_code == 200, f"Delete backup failed: {resp.status_code}"
    print(f"✅ D3c PASS: Backup deleted successfully")
    
    # D4: Non-superadmin/empty token
    print(f"\n[D4] Auth checks on download-ticket & upload-file")
    
    # download-ticket without token
    resp = requests.post(f"{BASE_URL}/admin/backup/download-ticket/{existing_backup}")
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print(f"  ✅ D4a PASS: download-ticket without token → {resp.status_code}")
    
    # upload-file without token
    fake_file = io.BytesIO(b"test")
    files = {'file': ('test.zip', fake_file, 'application/zip')}
    resp = requests.post(f"{BASE_URL}/admin/backup/upload-file", files=files)
    assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
    print(f"  ✅ D4b PASS: upload-file without token → {resp.status_code}")

def test_e_data_integrity(token):
    """E. Verify owner data not decreased"""
    print("\n" + "="*80)
    print("SECTION E: DATA INTEGRITY CHECK")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n[E1] GET /api/admin/backup/live-collections")
    resp = requests.get(f"{BASE_URL}/admin/backup/live-collections", headers=headers)
    assert resp.status_code == 200, f"Live collections failed: {resp.status_code}"
    data = resp.json()
    
    total_docs = data.get("total_documents", 0)
    collections = data.get("collections", [])
    
    # Find users collection
    users_coll = [c for c in collections if c.get("name") == "users"]
    users_count = users_coll[0].get("count", 0) if users_coll else 0
    
    print(f"  total_documents: {total_docs}")
    print(f"  users count: {users_count}")
    
    assert total_docs >= 3700, f"Total documents decreased: {total_docs} < 3700"
    assert users_count >= 35, f"Users count decreased: {users_count} < 35"
    
    print(f"✅ E1 PASS: Data integrity verified")
    print(f"   total_documents: {total_docs} (≥3700) ✅")
    print(f"   users: {users_count} (≥35) ✅")

def cleanup_test_artifacts(token):
    """Cleanup all test backups"""
    print("\n" + "="*80)
    print("CLEANUP TEST ARTIFACTS")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\nCreated backups to delete: {created_backups}")
    
    for backup_id in created_backups:
        try:
            resp = requests.delete(f"{BASE_URL}/admin/backup/{backup_id}", headers=headers)
            if resp.status_code == 200:
                print(f"  ✅ Deleted: {backup_id}")
            else:
                print(f"  ⚠️  Failed to delete {backup_id}: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠️  Error deleting {backup_id}: {e}")
    
    # Check for upload_* folders
    backups_dir = Path("/app/backups")
    upload_folders = [d for d in backups_dir.iterdir() if d.is_dir() and d.name.startswith("upload_")]
    print(f"\nUpload folders found: {len(upload_folders)}")
    for folder in upload_folders:
        print(f"  - {folder.name}")

def main():
    print("="*80)
    print("BACKEND TEST: Database Backup & Restore Bug Fixes")
    print("Sesi 2026-08-01 - Verifikasi perbaikan download & upload")
    print("="*80)
    
    try:
        # Login once
        token = login_once()
        
        # Run all tests
        test_a_download_via_ticket(token)
        test_b_upload_single_request(token)
        test_c_chunked_upload(token)
        test_d_restore_regression(token)
        test_e_data_integrity(token)
        
        # Cleanup
        cleanup_test_artifacts(token)
        
        print("\n" + "="*80)
        print("ALL TESTS PASSED ✅")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
