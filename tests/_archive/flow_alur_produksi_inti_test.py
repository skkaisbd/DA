"""
FLOW backend test — "Alur Produksi Inti" (Core Production Flow).

Alur happy-path lintas modul yang diuji end-to-end di layer API + DB:
    Production Wizard (preview -> start)  ->  Work Order (released)
    ->  Input Harian Sederhana (SEWING -> FINISHING -> QC -> PACKING)
    ->  Auto-complete WO -> Auto-complete Order.

Strategi = AMAN untuk DB live + SELF-CLEANUP penuh:
  - Membuat 1 fixture model sementara (ditandai created_by='flow-test') via DB.
  - Menjalankan wizard start-production INTERNAL (tanpa pelanggan) qty kecil (10 pcs).
  - Menyelesaikan produksi via simple-input hingga WO/Order auto-complete.
  - Di blok finally: MENGHAPUS semua dokumen yang dibuat (order, WO, bundles,
    wip_events, material reservations, fixture model). Tidak menyentuh data lain.

Tipe kasus: [H]appy [E]dge [N]egative [S]tate.
Jalankan: python3 tests/flow_alur_produksi_inti_test.py
"""
import os
import sys
import uuid
import datetime
from pathlib import Path

import requests
from pymongo import MongoClient

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

results = []
def rec(tc, verdict, detail=""):
    results.append((tc, verdict, detail))
    print(f"[{tc}] {verdict} | {detail}")

def H(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
def G(p, t): return requests.get(f"{BASE}{p}", headers=H(t), timeout=30)
def P(p, t, b=None): return requests.post(f"{BASE}{p}", headers=H(t), json=(b or {}), timeout=60)

# ── DB handle (untuk fixture + cleanup) ─────────────────────────────────────
env = {}
for line in Path(__file__).resolve().parents[1].joinpath("backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
mongo = MongoClient(env["MONGO_URL"])
db = mongo[env.get("DB_NAME", "test_database")]

# ── Login ───────────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
r.raise_for_status()
admin = r.json()["token"]
print("admin login OK")

today = datetime.date.today().isoformat()

# ── Fixture: model + size sementara ─────────────────────────────────────────
FIX_MARK = "flow-test"
fixture_model_id = f"flowtest-model-{uuid.uuid4().hex[:8]}"
created_order_id = None
created_wo_ids = []

# Ambil 1 size yang ada (master sizes sudah tersedia di sistem)
sizes = G("/api/rahaza/sizes?active=true&limit=5", admin).json()
sizes = sizes if isinstance(sizes, list) else sizes.get("items", [])
if not sizes:
    print("FATAL: tidak ada master size — tidak bisa menjalankan flow test.")
    sys.exit(2)
size_id = sizes[0]["id"]

try:
    # Insert fixture model (bundle_size 30 -> qty 10 = tepat 1 bundle)
    db.rahaza_models.insert_one({
        "id": fixture_model_id,
        "code": f"ZZ-FLOWTEST-{uuid.uuid4().hex[:4].upper()}",
        "name": "Flow Test Model (auto)",
        "bundle_size": 30,
        "active": True,
        "created_by": FIX_MARK,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    })
    rec("TC-00", "PASS", f"[S] fixture model dibuat id={fixture_model_id}, size={size_id}")

    items = [{"model_id": fixture_model_id, "size_id": size_id, "qty": 10}]

    # ── STEP 1: Preview (dry-run) ────────────────────────────────────────────
    r = P("/api/rahaza/wizard/preview-production", admin, {"items": []})
    ok = r.status_code == 200 and r.json().get("wo_count") == 0
    rec("TC-01", "PASS" if ok else "FAIL", f"[E] preview items kosong -> wo_count 0 ({r.status_code})")

    r = P("/api/rahaza/wizard/preview-production", admin, {"items": items})
    pj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and pj.get("wo_count") == 1 and pj.get("total_bundles") == 1
    rec("TC-02", "PASS" if ok else "FAIL",
        f"[H] preview valid -> wo_count={pj.get('wo_count')} bundles={pj.get('total_bundles')} ({r.status_code})")

    # ── STEP 2: start-production — negatif ───────────────────────────────────
    r = P("/api/rahaza/wizard/start-production", admin,
          {"is_internal": False, "customer_id": None, "items": items})
    rec("TC-03", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] start tanpa customer & bukan internal -> 400 ({r.status_code})")

    r = P("/api/rahaza/wizard/start-production", admin,
          {"is_internal": True, "items": [{"model_id": fixture_model_id, "size_id": size_id, "qty": 0}]})
    rec("TC-04", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] start item qty<=0 -> 400 ({r.status_code})")

    # ── STEP 3: start-production — happy (INTERNAL) ──────────────────────────
    r = P("/api/rahaza/wizard/start-production", admin, {
        "is_internal": True,
        "order_date": today,
        "items": items,
        "auto_release_wo": True,
        "auto_generate_bundles": True,
        "notes": "flow-test order (auto)",
    })
    sj = r.json() if r.status_code == 200 else {}
    created_order_id = sj.get("order_id")
    created_wo_ids = [w["id"] for w in sj.get("wos", [])]
    wo0 = sj.get("wos", [{}])[0] if sj.get("wos") else {}
    ok = (r.status_code == 200 and sj.get("ok") and sj.get("wos_created") == 1
          and sj.get("bundles_created") == 1 and wo0.get("status") == "released")
    rec("TC-05", "PASS" if ok else "FAIL",
        f"[H] start-production -> order={sj.get('order_number')} wos={sj.get('wos_created')} "
        f"bundles={sj.get('bundles_created')} woStatus={wo0.get('status')} ({r.status_code})")

    wo_id = created_wo_ids[0] if created_wo_ids else None

    # ── STEP 4: Work Order muncul & released ─────────────────────────────────
    r = G("/api/rahaza/work-orders?limit=300", admin)
    wl = r.json() if r.status_code == 200 else []
    wl = wl if isinstance(wl, list) else wl.get("items", [])
    found = next((w for w in wl if w.get("id") == wo_id), None)
    rec("TC-06", "PASS" if (r.status_code == 200 and found) else "FAIL",
        f"[H] WO muncul di /work-orders (found={bool(found)}) ({r.status_code})")

    r = G(f"/api/rahaza/work-orders/{wo_id}", admin)
    wj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and wj.get("status") == "released" and int(wj.get("qty", 0)) == 10
    rec("TC-07", "PASS" if ok else "FAIL",
        f"[S] WO detail status=released qty=10 (status={wj.get('status')} qty={wj.get('qty')}) ({r.status_code})")

    # ── STEP 5: Eksekusi — negatif dulu ──────────────────────────────────────
    r = P("/api/rahaza/execution/simple-input", admin,
          {"process_code": "SEWING", "qty": 0, "work_order_id": wo_id, "input_date": today})
    rec("TC-08", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] simple-input qty<=0 -> 400 ({r.status_code})")

    r = P("/api/rahaza/execution/simple-input", admin,
          {"process_code": "QC", "qty": 5, "qty_fail": 9, "work_order_id": wo_id, "input_date": today})
    rec("TC-09", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] simple-input QC qty_fail>qty -> 400 ({r.status_code})")

    # ── STEP 5b: Eksekusi — happy per tahap ──────────────────────────────────
    def stage_input(code, qty, fail=0):
        return P("/api/rahaza/execution/simple-input", admin,
                 {"process_code": code, "qty": qty, "qty_fail": fail,
                  "work_order_id": wo_id, "input_date": today})

    r = stage_input("SEWING", 10)
    rec("TC-10", "PASS" if r.status_code == 200 and r.json().get("count") == 1 else "FAIL",
        f"[H] simple-input SEWING 10 ({r.status_code})")

    r = stage_input("FINISHING", 10)
    rec("TC-11", "PASS" if r.status_code == 200 and r.json().get("count") == 1 else "FAIL",
        f"[H] simple-input FINISHING 10 ({r.status_code})")

    r = stage_input("QC", 10, 0)  # 10 lolos, 0 gagal -> 1 event qc_pass
    rec("TC-12", "PASS" if r.status_code == 200 and r.json().get("count") >= 1 else "FAIL",
        f"[H] simple-input QC 10 (pass) count={r.json().get('count') if r.status_code==200 else '-'} ({r.status_code})")

    r = stage_input("PACKING", 10)  # memicu maybe_auto_complete_wo
    rec("TC-13", "PASS" if r.status_code == 200 and r.json().get("count") == 1 else "FAIL",
        f"[H] simple-input PACKING 10 -> trigger auto-complete ({r.status_code})")

    # ── STEP 6: Completion auto ──────────────────────────────────────────────
    r = G(f"/api/rahaza/work-orders/{wo_id}", admin)
    wj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and wj.get("status") == "completed"
    rec("TC-14", "PASS" if ok else "FAIL",
        f"[S] WO auto-completed (status={wj.get('status')} auto={wj.get('auto_completed')}) ({r.status_code})")

    r = G(f"/api/rahaza/orders/{created_order_id}", admin)
    oj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and oj.get("status") == "completed"
    rec("TC-15", "PASS" if ok else "FAIL",
        f"[S] Order auto-completed (status={oj.get('status')}) ({r.status_code})")

    # ── STEP 7: Riwayat input memuat event kita ──────────────────────────────
    r = G(f"/api/rahaza/execution/simple-input/history?date={today}", admin)
    hist = r.json() if r.status_code == 200 else []
    mine = [e for e in hist if e.get("work_order_id") == wo_id]
    ok = r.status_code == 200 and len(mine) >= 4
    rec("TC-16", "PASS" if ok else "FAIL",
        f"[H] history memuat >=4 event WO ini (n={len(mine)}) ({r.status_code})")

finally:
    # ── SELF-CLEANUP (hapus hanya dokumen buatan test) ───────────────────────
    deleted = {}
    try:
        if created_wo_ids:
            deleted["wip_events"] = db.rahaza_wip_events.delete_many({"work_order_id": {"$in": created_wo_ids}}).deleted_count
            deleted["bundles"] = db.rahaza_bundles.delete_many({"work_order_id": {"$in": created_wo_ids}}).deleted_count
            deleted["reservations"] = db.rahaza_material_reservations.delete_many({"wo_id": {"$in": created_wo_ids}}).deleted_count
            deleted["work_orders"] = db.rahaza_work_orders.delete_many({"id": {"$in": created_wo_ids}}).deleted_count
        if created_order_id:
            deleted["orders"] = db.rahaza_orders.delete_many({"id": created_order_id}).deleted_count
        deleted["fixture_model"] = db.rahaza_models.delete_many({"id": fixture_model_id}).deleted_count
        rec("CLEANUP", "PASS", f"[S] dokumen dihapus: {deleted}")
    except Exception as e:
        rec("CLEANUP", "FAIL", f"[S] cleanup error: {e}")

# ── Ringkasan ────────────────────────────────────────────────────────────────
n_pass = sum(1 for _, v, _ in results if v == "PASS")
n_fail = sum(1 for _, v, _ in results if v == "FAIL")
print("\n" + "=" * 70)
print(f" RINGKASAN: {n_pass} PASS · {n_fail} FAIL · total {len(results)}")
print("=" * 70)
if n_fail:
    print(" STATUS: FAIL")
    sys.exit(1)
print(" STATUS: PASS — Alur Produksi Inti happy-path terverifikasi end-to-end.")
sys.exit(0)
