"""
POC / E2E API test — Flow Maklon: Client Portal (Portal Klien Maklon)
=====================================================================
flow_id: flow-maklon-client-portal

Membuktikan happy-path + guardrail portal EKSTERNAL untuk klien maklon:
  1. Admin Maklon PROVISION akun portal klien (email + password sekali-pakai)
  2. Klien LOGIN (JWT audience 'maklon-client') -> WAJIB ganti password (gate 428)
  3. Klien LIHAT dashboard + daftar ORDER (PO) miliknya
  4. Klien LIHAT detail order + TIMELINE (tracking) + QC + sample
  5. Klien UPLOAD lampiran foto (validasi tipe & ukuran)
  6. Klien SETUJUI/TOLAK/REVISI sample (hanya saat submitted/revision_requested)
  7. Klien LIHAT invoice, profil, badge-counts
  + Guard keamanan: isolasi antar-klien (404), pemisahan token staf vs klien (401),
    wrong password (401), must_change (428), sample tak-aktif (400).

Menjalankan:
    python3 tests/flow_maklon_client_portal_test.py

Self-cleanup: akun klien + login-attempts + sample fixture + file upload yang dibuat
skrip ini dihapus di blok finally. Data SEED (klien/PO/sample/invoice) TIDAK disentuh.
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

TAG = uuid.uuid4().hex[:8]
POC_EMAIL = f"poc_client_{TAG}@example.com"
PW1 = "ClientTemp@123"
PW2 = "ClientNew@456"

A = requests.Session()   # admin staf
C = requests.Session()   # klien maklon

st = {"passes": 0, "client_id": None, "account_id": None, "sample_id": None,
      "upload_file": None, "bf_email": POC_EMAIL.lower().strip()}


def ok(msg):
    st["passes"] += 1
    print(f"PASS {msg}")


def _db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL)[DB_NAME]


# ── SETUP: pilih klien seed yang punya order ─────────────────────────────────
def setup_fixtures():
    db = _db()
    # klien A dengan >=1 PO
    client_id = None
    order_a = None
    for po in db.dewi_maklon_pos.find({}, {"id": 1, "client_id": 1}):
        if po.get("client_id"):
            client_id = po["client_id"]
            order_a = po["id"]
            break
    assert client_id and order_a, "seed: tidak ada PO maklon dengan client_id"
    st["client_id"] = client_id
    st["order_a"] = order_a
    # order milik KLIEN LAIN (untuk uji isolasi); fallback uuid acak (tetap 404)
    other = db.dewi_maklon_pos.find_one({"client_id": {"$ne": client_id}}, {"id": 1})
    st["order_b"] = other["id"] if other else str(uuid.uuid4())
    ok(f"setup: klien={client_id[:8]} orderA={order_a[:8]} orderB(lain)={str(st['order_b'])[:8]}")


def admin_login():
    r = A.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    A.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    ok("admin (staf) login")


# ── 1. PROVISION AKUN PORTAL ─────────────────────────────────────────────────
def provision():
    cid = st["client_id"]
    r = A.post(f"{BASE}/api/dewi/maklon/clients/{cid}/provision-portal",
               json={"email": POC_EMAIL, "name": "Kontak POC", "password": PW1})
    assert r.status_code == 200, f"provision {r.status_code}: {r.text}"
    d = r.json()
    assert d["must_change_password"] is True and d["email"] == POC_EMAIL.lower(), d
    ok("provision: akun portal klien dibuat (must_change_password=true)")

    # Guard: email duplikat -> 400
    r = A.post(f"{BASE}/api/dewi/maklon/clients/{cid}/provision-portal",
               json={"email": POC_EMAIL, "password": PW1})
    assert r.status_code == 400, f"expected 400 duplikat email, got {r.status_code}"
    ok("provision GUARD: email duplikat ditolak (400)")

    # portal-status -> has_account true
    r = A.get(f"{BASE}/api/dewi/maklon/clients/{cid}/portal-status")
    assert r.status_code == 200 and r.json()["has_account"] is True, r.text
    accts = r.json()["accounts"]
    st["account_id"] = next((a["id"] for a in accts if a["email"] == POC_EMAIL.lower()), None)
    assert st["account_id"], "account_id tak ditemukan di portal-status"
    ok("provision: portal-status has_account=true")


# ── 2. LOGIN KLIEN + GANTI PASSWORD ──────────────────────────────────────────
def client_login_and_change_pw():
    # Guard: password salah -> 401
    r = C.post(f"{BASE}/api/dewi/client-portal/auth/login",
               json={"email": POC_EMAIL, "password": "salah-sekali"})
    assert r.status_code == 401, f"expected 401 wrong pw, got {r.status_code}"
    ok("login GUARD: password salah ditolak (401)")

    # Login benar
    r = C.post(f"{BASE}/api/dewi/client-portal/auth/login",
               json={"email": POC_EMAIL, "password": PW1})
    assert r.status_code == 200, f"client login {r.status_code}: {r.text}"
    d = r.json()
    assert d["user"]["must_change_password"] is True, d
    C.headers.update({"Authorization": f"Bearer {d['token']}", "Content-Type": "application/json"})
    ok("login: klien login (JWT audience maklon-client), must_change_password=true")

    # Guard: akses non-/auth saat must_change -> 428
    r = C.get(f"{BASE}/api/dewi/client-portal/dashboard")
    assert r.status_code == 428, f"expected 428 must-change gate, got {r.status_code}: {r.text}"
    ok("gate GUARD: akses dashboard sebelum ganti password ditolak (428)")

    # Guard: ganti password dengan old salah -> 400
    r = C.post(f"{BASE}/api/dewi/client-portal/auth/change-password",
               json={"old_password": "bukan-ini", "new_password": PW2})
    assert r.status_code == 400, f"expected 400 wrong old pw, got {r.status_code}"
    ok("change-pw GUARD: password lama salah ditolak (400)")

    # Ganti password benar
    r = C.post(f"{BASE}/api/dewi/client-portal/auth/change-password",
               json={"old_password": PW1, "new_password": PW2})
    assert r.status_code == 200, f"change-pw {r.status_code}: {r.text}"
    ok("change-pw: password klien berhasil diganti (gate terbuka)")


# ── 3-4. LIHAT ORDER + TIMELINE (TRACKING) ───────────────────────────────────
def view_orders_and_tracking():
    r = C.get(f"{BASE}/api/dewi/client-portal/auth/me")
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False, r.text
    ok("me: profil sesi klien (must_change_password=false)")

    r = C.get(f"{BASE}/api/dewi/client-portal/dashboard")
    assert r.status_code == 200, f"dashboard {r.status_code}: {r.text}"
    dash = r.json()
    assert "orders" in dash and "invoices" in dash and "samples" in dash, dash
    ok(f"dashboard: orders.total={dash['orders']['total']} invoices.outstanding={dash['invoices']['outstanding_count']}")

    r = C.get(f"{BASE}/api/dewi/client-portal/orders")
    assert r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1, r.text
    ok(f"orders: daftar order klien total={len(r.json())}")

    oid = st["order_a"]
    r = C.get(f"{BASE}/api/dewi/client-portal/orders/{oid}")
    assert r.status_code == 200, f"order detail {r.status_code}: {r.text}"
    od = r.json()
    assert isinstance(od.get("timeline"), list) and len(od["timeline"]) >= 1, f"timeline hilang: {od}"
    ok(f"tracking: detail order + timeline {len(od['timeline'])} tahap (status={od.get('status')})")

    r = C.get(f"{BASE}/api/dewi/client-portal/orders/{oid}/qc")
    assert r.status_code == 200 and isinstance(r.json(), list), r.text
    ok(f"tracking: laporan QC order (n={len(r.json())})")

    r = C.get(f"{BASE}/api/dewi/client-portal/orders/{oid}/samples")
    assert r.status_code == 200 and isinstance(r.json(), list), r.text
    ok(f"tracking: sample per order (n={len(r.json())})")

    # Guard isolasi: order klien lain -> 404
    r = C.get(f"{BASE}/api/dewi/client-portal/orders/{st['order_b']}")
    assert r.status_code == 404, f"expected 404 cross-client, got {r.status_code}"
    ok("keamanan GUARD: akses order klien lain ditolak (404 scoping client_id)")


# ── 5. UPLOAD LAMPIRAN ───────────────────────────────────────────────────────
def upload_attachment():
    # multipart: kirim HANYA header Authorization (biar requests set boundary content-type)
    auth_h = {"Authorization": C.headers["Authorization"]}
    up = f"{BASE}/api/dewi/client-portal/uploads"
    png = b"\x89PNG\r\n\x1a\n" + bytes(600)  # valid-signature, >100 byte
    r = requests.post(up, files={"file": ("bukti.png", png, "image/png")}, headers=auth_h)
    assert r.status_code == 200, f"upload {r.status_code}: {r.text}"
    d = r.json()
    assert d.get("url") and d.get("filename"), d
    st["upload_file"] = d["filename"]
    ok(f"upload: lampiran foto tersimpan ({d['size']} byte, {d['content_type']})")

    # Guard: tipe tak didukung -> 415
    r = requests.post(up, files={"file": ("doc.pdf", b"%PDF-1.4" + bytes(200), "application/pdf")}, headers=auth_h)
    assert r.status_code == 415, f"expected 415 tipe file, got {r.status_code}"
    ok("upload GUARD: tipe file tak didukung ditolak (415)")

    # Guard: file terlalu kecil -> 400
    r = requests.post(up, files={"file": ("tiny.png", b"\x89PNG", "image/png")}, headers=auth_h)
    assert r.status_code == 400, f"expected 400 file kecil, got {r.status_code}"
    ok("upload GUARD: file terlalu kecil ditolak (400)")


# ── 6. AKSI SAMPLE (approve/reject/revision) ─────────────────────────────────
def sample_actions():
    db = _db()
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.dewi_maklon_samples.insert_one({
        "id": sid, "order_id": st["order_a"], "po_id": st["order_a"],
        "sample_code": f"SMP-POC-{TAG}", "product_name": "Kaos POC",
        "client_id": st["client_id"], "client_name": "POC",
        "status": "submitted", "revision_number": 0,
        "submitted_at": now, "created_at": now, "updated_at": now,
    })
    st["sample_id"] = sid

    r = C.get(f"{BASE}/api/dewi/client-portal/samples")
    assert r.status_code == 200 and any(s["id"] == sid for s in r.json()), "sample fixture tak muncul di list"
    ok("sample: sample fixture (submitted) muncul di daftar klien")

    r = C.get(f"{BASE}/api/dewi/client-portal/samples/{sid}")
    assert r.status_code == 200 and isinstance(r.json().get("revisions"), list), r.text
    ok("sample: detail sample + histori revisi")

    # Minta revisi (submitted -> revision_requested)
    r = C.post(f"{BASE}/api/dewi/client-portal/samples/{sid}/revision",
               json={"reason": "Warna kurang sesuai", "changes_required": "Ubah ke navy"})
    assert r.status_code == 200 and r.json().get("revision_number") == 1, r.text
    ok("sample: minta revisi #1 (submitted -> revision_requested)")

    # Approve (revision_requested juga actionable)
    r = C.post(f"{BASE}/api/dewi/client-portal/samples/{sid}/approve",
               json={"feedback": "Oke lanjut produksi"})
    assert r.status_code == 200, f"approve {r.status_code}: {r.text}"
    ok("sample: sample disetujui (revision_requested -> approved)")

    # Guard: approve sample yang sudah approved -> 400 (tak actionable)
    r = C.post(f"{BASE}/api/dewi/client-portal/samples/{sid}/approve", json={})
    assert r.status_code == 400, f"expected 400 sample not actionable, got {r.status_code}"
    ok("sample GUARD: aksi pada sample non-aktif ditolak (400)")


# ── 7. INVOICE / PROFIL / BADGE ──────────────────────────────────────────────
def invoices_profile_badges():
    r = C.get(f"{BASE}/api/dewi/client-portal/invoices")
    assert r.status_code == 200 and isinstance(r.json(), list), r.text
    ok(f"invoice: daftar invoice klien (n={len(r.json())})")

    r = C.get(f"{BASE}/api/dewi/client-portal/profile")
    assert r.status_code == 200 and r.json().get("id") == st["client_id"], r.text
    ok("profil: data profil klien")

    r = C.get(f"{BASE}/api/dewi/client-portal/badge-counts")
    assert r.status_code == 200 and "samples" in r.json() and "invoices" in r.json(), r.text
    ok("badge: badge-counts (samples/invoices)")


# ── 8. PEMISAHAN TOKEN staf vs klien ─────────────────────────────────────────
def token_separation():
    # tanpa token -> 401
    r = requests.get(f"{BASE}/api/dewi/client-portal/dashboard")
    assert r.status_code == 401, f"expected 401 no token, got {r.status_code}"
    # token STAF (audience beda) -> 401
    r = requests.get(f"{BASE}/api/dewi/client-portal/dashboard",
                     headers={"Authorization": A.headers.get("Authorization", "")})
    assert r.status_code == 401, f"expected 401 staff token on client portal, got {r.status_code}"
    ok("keamanan GUARD: tanpa token & token staf ditolak di portal klien (401)")


def cleanup():
    try:
        db = _db()
    except Exception as e:  # pragma: no cover
        print(f"WARN cleanup skip (pymongo): {e}")
        return
    if st["sample_id"]:
        db.dewi_maklon_samples.delete_one({"id": st["sample_id"]})
        db.dewi_maklon_sample_revisions.delete_many({"sample_id": st["sample_id"]})
    # hapus akun portal POC + login attempts
    db.dewi_client_users.delete_many({"email": POC_EMAIL.lower()})
    db.client_login_attempts.delete_many({"identifier": {"$regex": st["bf_email"]}})
    # hapus file upload
    if st["upload_file"] and st["client_id"]:
        fp = Path(f"/app/uploads/client/{st['client_id']}/{st['upload_file']}")
        try:
            if fp.exists():
                fp.unlink()
        except Exception:
            pass
    print("CLEANUP: akun portal POC + sample fixture + login-attempts + file upload dihapus — SEED utuh.")


def main():
    try:
        admin_login()
        setup_fixtures()
        provision()
        client_login_and_change_pw()
        view_orders_and_tracking()
        upload_attachment()
        sample_actions()
        invoices_profile_badges()
        token_separation()
        print(f"\n=== CLIENT PORTAL MAKLON FLOW: ALL PASS ({st['passes']} assertions) ===")
    finally:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(2)
