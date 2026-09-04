"""
E2E API-level POC test — Alur Manajemen Aset (Asset Management).

Alur bisnis kritikal siklus hidup aset tetap CV. Dewi Aditya (portal 'assets'):
KATEGORI & REGISTRASI (daftar aset + jurnal pembelian otomatis)
  -> DEPRESIASI per-aset (posting bulanan + jurnal beban depresiasi, idempotent)
  -> DEPRESIASI MASSAL (batch semua aset aktif, idempotent per aset)
  -> PENUGASAN (assign aset ke karyawan)
  -> PENGEMBALIAN (unassign / return).

Happy path:
  login (superadmin)
  === 1. KATEGORI & REGISTRASI ===
  -> GET  /api/assets/categories                 (master kategori, auto-seed 7 default)
  -> POST /api/assets (Peralatan IT)             -> asset1 (status active, jurnal beli)
  -> GET  /api/assets/{id}                        (nbv = cost, fully_depreciated=false)
  === 2. DEPRESIASI per-aset ===
  -> POST /api/assets/{id}/depreciate/2097-01     -> amount = monthly_depreciation
  -> GET  /api/assets/{id}/depreciation-history   -> 1 record
  -> GET  /api/assets/{id}                         -> nbv turun
  === 3. DEPRESIASI MASSAL (batch) ===
  -> POST /api/assets (asset2) + (asset tiny life=1bln)
  -> POST /api/assets/batch-depreciate/2097-02    -> total_posted 3 (asset1,asset2,tiny)
  -> POST /api/assets/batch-depreciate/2097-02    -> idempotent: total_posted 0, skipped 3
  === 4. PENUGASAN ===
  -> POST /api/assets/{asset1}/assign             -> assignment active
  -> GET  /api/assets/{asset1}/assignments        -> 1 active
  === 5. PENGEMBALIAN ===
  -> POST /api/assets/{asset1}/unassign           -> asset.assigned_to = null
  -> GET  /api/assets/dashboard                   -> KPI

Guards:
  -> registrasi tanpa nama ditolak (400)
  -> registrasi harga <= 0 ditolak (400)
  -> depresiasi periode duplikat ditolak (400)
  -> depresiasi aset yang sudah habis (fully depreciated) ditolak (400)
  -> assign tanpa user_id ditolak (400)

Self-cleanup (hard): hapus semua aset uji + depresiasi + assignment + jurnal + kategori
-> DB pristine (koleksi aset kembali kosong seperti kondisi awal).
"""
import sys
import uuid

import requests

BASE = "http://localhost:8001"
S = requests.Session()
TAG = "E2E-AST"
st = {"asset1": None, "asset2": None, "tiny": None,
      "asset1_no": None, "asset2_no": None, "tiny_no": None,
      "cat_it_id": None}


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


def login():
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    print("PASS login superadmin")


# ══════════════════════════ 1. KATEGORI & REGISTRASI ══════════════════════════
def categories_master():
    r = S.get(f"{BASE}/api/assets/categories")
    assert r.status_code == 200, f"categories {r.status_code}: {r.text}"
    cats = r.json()
    assert isinstance(cats, list) and len(cats) >= 7, f"expected >=7 kategori, got {len(cats)}"
    it = next((c for c in cats if c["code"] == "IT"), None)
    assert it, "kategori Peralatan IT (IT) tidak ada"
    st["cat_it_id"] = it["id"]
    print(f"PASS [KATEGORI] master kategori {len(cats)} item (termasuk IT: {it['name']}, umur {it['useful_life_years']}th)")


def register_asset1():
    body = {
        "name": f"{TAG} Laptop Dell Latitude 5540",
        "category_id": st["cat_it_id"],
        "purchase_cost": 12000000,
        "purchase_date": "2097-01-05",
        "serial_number": f"{TAG}-SN-0001",
        "brand": "Dell", "model": "Latitude 5540",
        "location": "Kantor Pusat", "department": "IT",
    }
    r = S.post(f"{BASE}/api/assets", json=body)
    assert r.status_code == 200, f"register asset1 {r.status_code}: {r.text}"
    d = r.json()
    st["asset1"] = d["id"]
    st["asset1_no"] = d["asset_number"]
    assert d["status"] == "active", f"status {d}"
    assert d["asset_number"].startswith("AST-IT-"), f"asset_number {d['asset_number']}"
    assert d["monthly_depreciation"] > 0, f"monthly_depreciation {d}"
    assert d["journal_purchase_id"], "jurnal pembelian tidak dibuat"
    st["asset1_monthly"] = d["monthly_depreciation"]
    print(f"PASS [REGISTRASI] aset terdaftar {d['asset_number']} (active) + jurnal beli, "
          f"depr/bln={d['monthly_depreciation']}")


def get_asset1_detail():
    r = S.get(f"{BASE}/api/assets/{st['asset1']}")
    assert r.status_code == 200, f"get asset1 {r.status_code}: {r.text}"
    d = r.json()
    assert d["nbv"] == d["purchase_cost"], f"nbv awal harus = cost, got {d['nbv']} vs {d['purchase_cost']}"
    assert d["fully_depreciated"] is False, "aset baru tidak boleh fully_depreciated"
    print(f"PASS [REGISTRASI] detail aset nbv={d['nbv']} fully_depreciated={d['fully_depreciated']}")


def guard_register_no_name():
    r = S.post(f"{BASE}/api/assets", json={"purchase_cost": 1000000})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] registrasi tanpa nama ditolak (400)")


def guard_register_bad_cost():
    r = S.post(f"{BASE}/api/assets", json={"name": f"{TAG} Invalid", "purchase_cost": 0})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] registrasi harga <= 0 ditolak (400)")


# ══════════════════════════ 2. DEPRESIASI per-aset ══════════════════════════
def depreciate_asset1():
    r = S.post(f"{BASE}/api/assets/{st['asset1']}/depreciate/2097-01")
    assert r.status_code == 200, f"depreciate {r.status_code}: {r.text}"
    d = r.json()
    assert d["period"] == "2097-01", f"period {d}"
    assert d["amount"] == st["asset1_monthly"], f"amount {d['amount']} != monthly {st['asset1_monthly']}"
    assert d["journal_id"], "jurnal depresiasi tidak dibuat"
    st["depr1_amount"] = d["amount"]
    print(f"PASS [DEPRESIASI] posting 2097-01 amount={d['amount']} nbv_after={d['nbv_after']} + jurnal")


def depreciation_history_asset1():
    r = S.get(f"{BASE}/api/assets/{st['asset1']}/depreciation-history")
    assert r.status_code == 200, f"history {r.status_code}: {r.text}"
    recs = r.json()
    assert len(recs) == 1 and recs[0]["period"] == "2097-01", f"history {recs}"
    print(f"PASS [DEPRESIASI] riwayat depresiasi {len(recs)} record")


def asset1_nbv_decreased():
    r = S.get(f"{BASE}/api/assets/{st['asset1']}")
    d = r.json()
    expected = d["purchase_cost"] - st["depr1_amount"]
    assert abs(d["nbv"] - expected) < 0.5, f"nbv {d['nbv']} != {expected}"
    assert d["accumulated_depreciation"] == st["depr1_amount"], f"accum {d['accumulated_depreciation']}"
    print(f"PASS [DEPRESIASI] nbv turun ke {d['nbv']} (akumulasi={d['accumulated_depreciation']})")


def guard_depreciate_duplicate():
    r = S.post(f"{BASE}/api/assets/{st['asset1']}/depreciate/2097-01")
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] depresiasi periode duplikat ditolak (400)")


# ══════════════════════════ 3. DEPRESIASI MASSAL (batch) ══════════════════════════
def register_asset2_and_tiny():
    r = S.post(f"{BASE}/api/assets", json={
        "name": f"{TAG} Printer Epson L3210", "category_id": st["cat_it_id"],
        "purchase_cost": 3000000, "purchase_date": "2097-01-10",
    })
    assert r.status_code == 200, f"register asset2 {r.status_code}: {r.text}"
    st["asset2"] = r.json()["id"]
    st["asset2_no"] = r.json()["asset_number"]

    # aset "tiny": life 1 bulan, residu 0 -> setelah 1x depresiasi langsung fully depreciated
    r = S.post(f"{BASE}/api/assets", json={
        "name": f"{TAG} Mouse Wireless", "category_id": st["cat_it_id"],
        "purchase_cost": 1000, "residual_value": 0, "useful_life_months": 1,
        "purchase_date": "2097-01-10",
    })
    assert r.status_code == 200, f"register tiny {r.status_code}: {r.text}"
    st["tiny"] = r.json()["id"]
    st["tiny_no"] = r.json()["asset_number"]
    print(f"PASS [BATCH] registrasi 2 aset tambahan ({st['asset2_no']}, {st['tiny_no']})")


def batch_depreciate():
    r = S.post(f"{BASE}/api/assets/batch-depreciate/2097-02")
    assert r.status_code == 200, f"batch {r.status_code}: {r.text}"
    d = r.json()
    # 3 aset aktif belum posting 2097-02 -> semua terposting
    assert d["total_posted"] == 3, f"expected 3 posted, got {d['total_posted']} ({d})"
    assert d["total_errors"] == 0, f"errors {d}"
    print(f"PASS [BATCH] depresiasi massal 2097-02 posted={d['total_posted']} skipped={d['total_skipped']}")


def batch_depreciate_idempotent():
    r = S.post(f"{BASE}/api/assets/batch-depreciate/2097-02")
    assert r.status_code == 200, f"batch2 {r.status_code}: {r.text}"
    d = r.json()
    assert d["total_posted"] == 0 and d["total_skipped"] == 3, f"expected idempotent skip 3, got {d}"
    print(f"PASS [BATCH] idempotent: rerun 2097-02 posted={d['total_posted']} skipped={d['total_skipped']}")


def guard_depreciate_fully():
    # tiny sudah fully depreciated setelah batch 2097-02 -> periode lain ditolak
    r = S.post(f"{BASE}/api/assets/{st['tiny']}/depreciate/2097-09")
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] depresiasi aset yang sudah habis (fully depreciated) ditolak (400)")


# ══════════════════════════ 4. PENUGASAN ══════════════════════════
def assign_asset1():
    r = S.post(f"{BASE}/api/assets/{st['asset1']}/assign", json={
        "user_id": f"{TAG}-EMP-001", "user_name": f"{TAG} Budi Santoso",
        "assigned_date": "2097-02-01", "notes": "Untuk kebutuhan kerja harian",
    })
    assert r.status_code == 200, f"assign {r.status_code}: {r.text}"
    d = r.json()
    assert d["status"] == "active" and d["assigned_to_id"] == f"{TAG}-EMP-001", f"assign body {d}"
    r2 = S.get(f"{BASE}/api/assets/{st['asset1']}")
    assert r2.json()["assigned_to_id"] == f"{TAG}-EMP-001", "asset.assigned_to_id belum terset"
    print(f"PASS [PENUGASAN] aset ditugaskan ke {d['assigned_to_name']}")


def assignments_history():
    r = S.get(f"{BASE}/api/assets/{st['asset1']}/assignments")
    assert r.status_code == 200, f"assignments {r.status_code}: {r.text}"
    recs = r.json()
    assert len(recs) == 1 and recs[0]["status"] == "active", f"assignments {recs}"
    print(f"PASS [PENUGASAN] riwayat penugasan {len(recs)} record (active)")


def guard_assign_no_user():
    r = S.post(f"{BASE}/api/assets/{st['asset2']}/assign", json={"user_name": "Tanpa ID"})
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
    print("PASS [GUARD] penugasan tanpa user_id ditolak (400)")


# ══════════════════════════ 5. PENGEMBALIAN ══════════════════════════
def unassign_asset1():
    r = S.post(f"{BASE}/api/assets/{st['asset1']}/unassign")
    assert r.status_code == 200 and r.json().get("ok"), f"unassign {r.status_code}: {r.text}"
    r2 = S.get(f"{BASE}/api/assets/{st['asset1']}")
    assert r2.json()["assigned_to_id"] is None, "asset.assigned_to_id belum dikosongkan"
    r3 = S.get(f"{BASE}/api/assets/{st['asset1']}/assignments")
    assert any(a["status"] == "returned" for a in r3.json()), "assignment belum returned"
    print("PASS [PENGEMBALIAN] aset dikembalikan (assigned_to=null, assignment=returned)")


def dashboard():
    r = S.get(f"{BASE}/api/assets/dashboard")
    assert r.status_code == 200, f"dashboard {r.status_code}: {r.text}"
    d = r.json()
    assert "total_assets" in d or "total_cost" in d or "recent_assets" in d, f"dashboard shape {list(d.keys())}"
    print(f"PASS [DASHBOARD] KPI aset dimuat ({', '.join(list(d.keys())[:6])})")


def main():
    login()
    print("\n--- 1. KATEGORI & REGISTRASI ---")
    categories_master()
    register_asset1()
    get_asset1_detail()
    guard_register_no_name()
    guard_register_bad_cost()

    print("\n--- 2. DEPRESIASI per-aset ---")
    depreciate_asset1()
    depreciation_history_asset1()
    asset1_nbv_decreased()
    guard_depreciate_duplicate()

    print("\n--- 3. DEPRESIASI MASSAL (batch) ---")
    register_asset2_and_tiny()
    batch_depreciate()
    batch_depreciate_idempotent()
    guard_depreciate_fully()

    print("\n--- 4. PENUGASAN ---")
    assign_asset1()
    assignments_history()
    guard_assign_no_user()

    print("\n--- 5. PENGEMBALIAN ---")
    unassign_asset1()
    dashboard()

    print("\n=== MANAJEMEN ASET FLOW ALL PASS ===")


def cleanup():
    url, dbn = _mongo_cfg()
    if not url:
        print("CLEANUP WARN: MONGO_URL tidak terbaca")
        return
    try:
        from pymongo import MongoClient
        cli = MongoClient(url)
        db = cli[dbn]
        asset_ids = [st.get(k) for k in ("asset1", "asset2", "tiny") if st.get(k)]
        asset_nos = [st.get(k) for k in ("asset1_no", "asset2_no", "tiny_no") if st.get(k)]
        n = {}
        n["assets"] = db.dewi_assets.delete_many(
            {"$or": [{"id": {"$in": asset_ids}}, {"name": {"$regex": f"^{TAG}"}}]}
        ).deleted_count
        n["depr"] = db.dewi_asset_depreciation.delete_many({"asset_id": {"$in": asset_ids}}).deleted_count
        n["assign"] = db.dewi_asset_assignments.delete_many({"asset_id": {"$in": asset_ids}}).deleted_count
        n["maint"] = db.dewi_asset_maintenance.delete_many({"asset_id": {"$in": asset_ids}}).deleted_count
        n["je"] = db.rahaza_journal_entries.delete_many(
            {"source_module": "asset_management", "source_ref": {"$in": asset_nos}}
        ).deleted_count
        # restore kondisi awal: dewi_asset_categories & dewi_assets kosong (semula 0)
        n["categories"] = db.dewi_asset_categories.delete_many({}).deleted_count
        cli.close()
        print(f"CLEANUP: {n} (DB pristine — koleksi aset dikosongkan)")
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
