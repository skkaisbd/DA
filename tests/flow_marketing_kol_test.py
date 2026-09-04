"""
E2E API-level POC test — Alur Marketing / KOL (Toko/Marketing).

Alur bisnis kritikal lintas-modul untuk tim Marketing & KOL CV. Dewi Aditya:
KONTEN (rencana konten multi-platform, termasuk kolaborasi KOL)
  -> CAMPAIGN (peluncuran produk / product launch, auto-create FG saat launched)
  -> REVIEW (rating & ulasan pelanggan, balas ulasan)
  -> KOMPLAIN (penanganan komplain dengan SLA 48 jam).

Happy path:
  login (superadmin)
  === 1. KONTEN (Content Calendar) ===
  -> GET  /api/marketing/content-calendar/types                 (master jenis konten)
  -> POST /api/marketing/content-calendar (kolaborasi_kol,draft) -> content_id
  -> POST /api/marketing/content-calendar/{id}/status scheduled
  -> POST /api/marketing/content-calendar/{id}/status posted
  -> GET  /api/marketing/content-calendar/summary
  === 2. CAMPAIGN (Product Launch) ===
  -> POST /api/marketing/product-launches (planning)            -> launch_id
  -> POST /api/marketing/product-launches/{id}/status ready
  -> POST /api/marketing/product-launches/{id}/status launched  -> fg_auto_created=True
  -> GET  /api/marketing/product-launches/summary
  === 3. REVIEW (Rating & Review) ===
  -> POST /api/marketing/reviews (rating=2, pending)            -> review_id
  -> POST /api/marketing/reviews/{id}/respond                   -> status=reviewed
  -> GET  /api/marketing/reviews/{id}
  -> GET  /api/marketing/reviews/summary
  === 4. KOMPLAIN (Complaints, SLA) ===
  (komplain berasal dari import/webhook/seed -> fixture disisipkan langsung)
  -> GET   /api/marketing/complaints/{id}                        (open, sla on_time)
  -> PATCH /api/marketing/complaints/{id}/status in_progress
  -> POST  /api/marketing/complaints/{id}/notes
  -> PATCH /api/marketing/complaints/{id}/status resolved        -> sla_status=resolved
  -> GET   /api/marketing/complaints/summary

Guards:
  -> content status invalid ditolak (400)
  -> launch status invalid ditolak (400)
  -> review respond tanpa response_text ditolak (400)
  -> complaint status invalid ditolak (400)

Self-cleanup (hard): hapus semua fixture (content/launch/FG/review/complaint) -> DB pristine.
"""
import sys
import uuid
from datetime import datetime, timezone, timedelta

import requests

BASE = "http://localhost:8001"
S = requests.Session()
st = {
    "content_id": None,
    "launch_id": None,
    "fg_id": None,
    "review_id": None,
    "complaint_id": None,
}
TAG = "E2E-KOL"
LAUNCH_CODE = "E2E-KOL-CAMP"


# ── util: baca MONGO_URL dari backend/.env untuk fixture + hard-cleanup ─────────
def _mongo_cfg():
    url = db = None
    try:
        with open("/app/backend/.env") as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith("MONGO_URL="):
                    url = ln.split("=", 1)[1].strip().strip('"').strip("'")
                elif ln.startswith("DB_NAME="):
                    db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return url, (db or "test_database")


def _db():
    from pymongo import MongoClient
    url, dbn = _mongo_cfg()
    cli = MongoClient(url)
    return cli, cli[dbn]


def login():
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    print("PASS login superadmin")


# ══════════════════════════ 1. KONTEN ══════════════════════════
def content_master():
    r = S.get(f"{BASE}/api/marketing/content-calendar/types")
    assert r.status_code == 200, f"content types {r.status_code}: {r.text}"
    types = r.json().get("types", [])
    assert any(t["value"] == "kolaborasi_kol" for t in types), "jenis kolaborasi_kol tidak ada"
    print(f"PASS [KONTEN] master jenis konten {len(types)} item (termasuk 'kolaborasi_kol')")


def content_create():
    today = datetime.now(timezone.utc).date().isoformat()
    body = {
        "account_name": f"{TAG} DA Official Shopee",
        "platform": "shopee",
        "date": today,
        "content_type": "kolaborasi_kol",
        "title": f"{TAG} Kolaborasi KOL - Gamis Daluna",
        "description": "Konten kolaborasi bersama KOL untuk campaign launch.",
        "cta": "Klik link di bio!",
        "post_time": "19:00",
        "status": "draft",
    }
    r = S.post(f"{BASE}/api/marketing/content-calendar", json=body)
    assert r.status_code == 200, f"create content {r.status_code}: {r.text}"
    d = r.json()["data"]
    st["content_id"] = d["id"]
    assert d["status"] == "draft" and d["content_type_label"] == "Kolaborasi KOL", f"content body {d}"
    print(f"PASS [KONTEN] buat konten draft (kolaborasi_kol) id={d['id'][:8]}")


def content_status_scheduled():
    r = S.post(f"{BASE}/api/marketing/content-calendar/{st['content_id']}/status",
               json={"status": "scheduled"})
    assert r.status_code == 200 and r.json()["status"] == "scheduled", f"schedule {r.status_code}: {r.text}"
    print("PASS [KONTEN] konten dijadwalkan (draft -> scheduled)")


def content_status_posted():
    r = S.post(f"{BASE}/api/marketing/content-calendar/{st['content_id']}/status",
               json={"status": "posted"})
    assert r.status_code == 200 and r.json()["status"] == "posted", f"posted {r.status_code}: {r.text}"
    print("PASS [KONTEN] konten tayang (scheduled -> posted)")


def guard_content_invalid_status():
    r = S.post(f"{BASE}/api/marketing/content-calendar/{st['content_id']}/status",
               json={"status": "flying"})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] status konten invalid ditolak (400)")


def content_summary():
    r = S.get(f"{BASE}/api/marketing/content-calendar/summary")
    assert r.status_code == 200 and r.json()["success"], f"content summary {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["posted"] >= 1, f"summary posted {data}"
    print(f"PASS [KONTEN] ringkasan konten total={data['total']} posted={data['posted']}")


# ══════════════════════════ 2. CAMPAIGN ══════════════════════════
def launch_create():
    launch_date = (datetime.now(timezone.utc).date()).isoformat()
    body = {
        "product_name": f"{TAG} Gamis Daluna Campaign Series",
        "launch_date": launch_date,
        "material": "Katun Linen Premium",
        "model": "Syari",
        "original_price": 165000,
        "flash_sale_price": 130000,
        "platforms": ["shopee", "tiktok"],
        "description": "Campaign launch produk hasil kolaborasi KOL.",
        "status": "planning",
        "style_code": LAUNCH_CODE,
    }
    r = S.post(f"{BASE}/api/marketing/product-launches", json=body)
    assert r.status_code == 200, f"create launch {r.status_code}: {r.text}"
    d = r.json()["data"]
    st["launch_id"] = d["id"]
    assert d["status"] == "planning" and d["status_label"] == "Perencanaan", f"launch body {d}"
    print(f"PASS [CAMPAIGN] buat product launch planning id={d['id'][:8]}")


def launch_status_ready():
    r = S.post(f"{BASE}/api/marketing/product-launches/{st['launch_id']}/status",
               json={"status": "ready"})
    assert r.status_code == 200 and r.json()["status"] == "ready", f"ready {r.status_code}: {r.text}"
    print("PASS [CAMPAIGN] campaign siap (planning -> ready)")


def launch_status_launched():
    r = S.post(f"{BASE}/api/marketing/product-launches/{st['launch_id']}/status",
               json={"status": "launched"})
    assert r.status_code == 200, f"launched {r.status_code}: {r.text}"
    j = r.json()
    assert j["status"] == "launched", f"status {j}"
    assert j["fg_auto_created"] is True and j.get("fg"), f"expected FG auto-create, got {j}"
    st["fg_id"] = j["fg"]["id"]
    print(f"PASS [CAMPAIGN] campaign launched + FG auto-create code={j['fg']['code']}")


def guard_launch_invalid_status():
    r = S.post(f"{BASE}/api/marketing/product-launches/{st['launch_id']}/status",
               json={"status": "teleport"})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] status launch invalid ditolak (400)")


def launch_summary():
    r = S.get(f"{BASE}/api/marketing/product-launches/summary")
    assert r.status_code == 200 and r.json()["success"], f"launch summary {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["launched"] >= 1, f"launch summary {data}"
    print(f"PASS [CAMPAIGN] ringkasan launch total={data['total']} launched={data['launched']}")


# ══════════════════════════ 3. REVIEW ══════════════════════════
def review_create():
    today = datetime.now(timezone.utc).date().isoformat()
    body = {
        "account_name": f"{TAG} DA Official Shopee",
        "date": today,
        "order_id": f"{TAG}-ORD-0001",
        "platform": "shopee",
        "rating": 2,
        "product": f"{TAG} Gamis Daluna Campaign Series",
        "category": "ukuran_tidak_sesuai",
        "review_text": "Ukuran XL terasa kecil, mohon diperbaiki size chart-nya.",
    }
    r = S.post(f"{BASE}/api/marketing/reviews", json=body)
    assert r.status_code == 200, f"create review {r.status_code}: {r.text}"
    d = r.json()["data"]
    st["review_id"] = d["id"]
    assert d["status"] == "pending" and d["rating"] == 2, f"review body {d}"
    print(f"PASS [REVIEW] buat ulasan rating=2 status=pending id={d['id'][:8]}")


def guard_review_respond_empty():
    r = S.post(f"{BASE}/api/marketing/reviews/{st['review_id']}/respond",
               json={"response_text": ""})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] balas ulasan tanpa teks ditolak (400)")


def review_respond():
    r = S.post(f"{BASE}/api/marketing/reviews/{st['review_id']}/respond",
               json={"response_text": "Halo kak, mohon maaf. Silakan retur, kami bantu tukar ukuran."})
    assert r.status_code == 200, f"respond {r.status_code}: {r.text}"
    print("PASS [REVIEW] balas ulasan terkirim")


def review_get_reviewed():
    r = S.get(f"{BASE}/api/marketing/reviews/{st['review_id']}")
    assert r.status_code == 200, f"get review {r.status_code}: {r.text}"
    d = r.json()["data"]
    assert d["status"] == "reviewed" and d["response_text"], f"expected reviewed, got {d}"
    print("PASS [REVIEW] ulasan berubah pending -> reviewed (ada tanggapan)")


def review_summary():
    r = S.get(f"{BASE}/api/marketing/reviews/summary")
    assert r.status_code == 200 and r.json()["success"], f"review summary {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert "avg_rating" in data and "rating_distribution" in data, f"review summary {data}"
    print(f"PASS [REVIEW] ringkasan ulasan total={data['total']} avg={data['avg_rating']} low={data['low_rating']}")


# ══════════════════════════ 4. KOMPLAIN ══════════════════════════
def complaint_fixture_insert():
    """Komplain berasal dari import/webhook/seed. Sisipkan fixture langsung agar
    alur transisi status + SLA + notes bisa diuji end-to-end via API."""
    cli, db = _db()
    try:
        cdate = datetime.now(timezone.utc)  # baru masuk -> SLA on_time
        doc = {
            "id": str(uuid.uuid4()),
            "complaint_number": f"KOMP-{TAG}-0001",
            "platform": "shopee",
            "account_id": None,
            "account_name": f"{TAG} DA Official Shopee",
            "customer_name": f"{TAG} Siti Rahayu",
            "product_name": f"{TAG} Gamis Daluna Campaign Series",
            "price": 130000,
            "complaint_date": cdate,
            "complaint_text": "Kak barangnya cuma dateng 1 padahal beli 2.",
            "category": "missing_item",
            "category_label": "Produk Kurang",
            "severity": "high",
            "status": "open",
            "sla_due_at": cdate + timedelta(hours=48),
            "sla_status": "on_time",
            "orders": [{"order_id": f"{TAG}-SHP-0001", "qty": 2, "price": 130000, "courier": "J&T Express"}],
            "ai_confidence": 0.9,
            "response_template": "Halo kak, mohon maaf. Tim kami memproses kekurangan produk.",
            "resolution_text": "",
            "notes": [],
            "_source_type": "complaints",
            "_import_session_id": f"{TAG}-poc",
            "created_at": cdate,
            "updated_at": cdate,
        }
        db.marketing_complaints.insert_one(doc)
        st["complaint_id"] = doc["id"]
    finally:
        cli.close()
    print(f"PASS [KOMPLAIN] fixture komplain disisipkan (KOMP-{TAG}-0001, open)")


def complaint_get_open():
    r = S.get(f"{BASE}/api/marketing/complaints/{st['complaint_id']}")
    assert r.status_code == 200, f"get complaint {r.status_code}: {r.text}"
    c = r.json()
    assert c["status"] == "open" and c["sla_status"] in ("on_time", "at_risk"), f"complaint {c.get('status')}/{c.get('sla_status')}"
    print(f"PASS [KOMPLAIN] komplain open, sla={c['sla_status']} due={c['sla_due_at'][:16]}")


def guard_complaint_invalid_status():
    r = S.patch(f"{BASE}/api/marketing/complaints/{st['complaint_id']}/status",
                json={"status": "banished"})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] status komplain invalid ditolak (400)")


def complaint_in_progress():
    r = S.patch(f"{BASE}/api/marketing/complaints/{st['complaint_id']}/status",
                json={"status": "in_progress", "note": "Cek stok ke gudang."})
    assert r.status_code == 200 and r.json()["new_status"] == "in_progress", f"in_progress {r.status_code}: {r.text}"
    print("PASS [KOMPLAIN] komplain diproses (open -> in_progress) + catatan")


def complaint_add_note():
    r = S.post(f"{BASE}/api/marketing/complaints/{st['complaint_id']}/notes",
               json={"text": "Barang pengganti disiapkan tim packing."})
    assert r.status_code == 200 and r.json()["ok"], f"note {r.status_code}: {r.text}"
    print("PASS [KOMPLAIN] catatan penanganan ditambahkan")


def complaint_resolved():
    r = S.patch(f"{BASE}/api/marketing/complaints/{st['complaint_id']}/status",
                json={"status": "resolved", "note": "Kekurangan 1 pcs sudah dikirim (resi baru)."})
    assert r.status_code == 200, f"resolve {r.status_code}: {r.text}"
    j = r.json()
    assert j["new_status"] == "resolved" and j["sla_status"] == "resolved", f"resolve body {j}"
    print("PASS [KOMPLAIN] komplain selesai (in_progress -> resolved), sla_status=resolved")


def complaint_summary():
    r = S.get(f"{BASE}/api/marketing/complaints/summary")
    assert r.status_code == 200, f"complaint summary {r.status_code}: {r.text}"
    data = r.json()
    assert "total" in data and "resolve_rate" in data and "by_status" in data, f"complaint summary {data}"
    print(f"PASS [KOMPLAIN] ringkasan komplain total={data['total']} resolve_rate={data['resolve_rate']}%")


def main():
    login()
    print("\n--- 1. KONTEN (Content Calendar) ---")
    content_master()
    content_create()
    content_status_scheduled()
    content_status_posted()
    guard_content_invalid_status()
    content_summary()

    print("\n--- 2. CAMPAIGN (Product Launch) ---")
    launch_create()
    launch_status_ready()
    launch_status_launched()
    guard_launch_invalid_status()
    launch_summary()

    print("\n--- 3. REVIEW (Rating & Review) ---")
    review_create()
    guard_review_respond_empty()
    review_respond()
    review_get_reviewed()
    review_summary()

    print("\n--- 4. KOMPLAIN (Complaints, SLA 48h) ---")
    complaint_fixture_insert()
    complaint_get_open()
    guard_complaint_invalid_status()
    complaint_in_progress()
    complaint_add_note()
    complaint_resolved()
    complaint_summary()

    print("\n=== MARKETING/KOL FLOW ALL PASS ===")


def cleanup():
    url, dbn = _mongo_cfg()
    if not url:
        print("CLEANUP WARN: MONGO_URL tidak terbaca, lewati hard-clean")
        return
    try:
        from pymongo import MongoClient
        cli = MongoClient(url)
        db = cli[dbn]
        n = {}
        if st.get("content_id"):
            n["content"] = db.marketing_content_calendar.delete_one({"id": st["content_id"]}).deleted_count
        if st.get("launch_id"):
            n["launch"] = db.marketing_product_launches.delete_one({"id": st["launch_id"]}).deleted_count
        # FG auto-created (by id or by code fallback)
        n["fg"] = db.rahaza_materials.delete_many(
            {"$or": [{"id": st.get("fg_id")}, {"code": LAUNCH_CODE, "type": "fg"}]}
        ).deleted_count
        if st.get("review_id"):
            n["review"] = db.marketing_reviews.delete_one({"id": st["review_id"]}).deleted_count
        if st.get("complaint_id"):
            n["complaint"] = db.marketing_complaints.delete_one({"id": st["complaint_id"]}).deleted_count
        # safety net: bersihkan sisa fixture bertag TAG
        db.marketing_content_calendar.delete_many({"account_name": {"$regex": f"^{TAG}"}})
        db.marketing_reviews.delete_many({"order_id": {"$regex": f"^{TAG}"}})
        db.marketing_complaints.delete_many({"complaint_number": {"$regex": f"^KOMP-{TAG}"}})
        db.marketing_product_launches.delete_many({"product_name": {"$regex": f"^{TAG}"}})
        cli.close()
        print(f"CLEANUP: {n} fixture dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(2)
