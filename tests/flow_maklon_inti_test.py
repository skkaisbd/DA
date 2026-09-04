"""
FLOW backend test — "Alur Maklon Inti" (Core Maklon / CMT Flow).

Alur happy-path lintas modul di layer API + DB:
    Buat PO Maklon (draft)
    -> Confirm PO (confirmed + auto Work Order per item + auto Draft AR Invoice)
    -> Surat Jalan/Dispatch (buat + konfirmasi) -> PO partial_delivered/completed
    -> Posting AR Invoice ke Finance GL (issued).

Strategi = AMAN untuk DB live + SELF-CLEANUP penuh:
  - Membuat 1 fixture klien maklon sementara (ditandai created_by='flow-maklon-test').
  - Menjalankan seluruh alur dengan qty kecil.
  - Di blok finally: menghapus PO, WO, dispatch, AR invoice, jurnal (JE+lines),
    material receive/BOM, dan fixture klien. Tidak menyentuh data lain.

Tipe kasus: [H]appy [E]dge [N]egative [S]tate.
Jalankan: python3 tests/flow_maklon_inti_test.py
"""
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
def PUT(p, t, b=None): return requests.put(f"{BASE}{p}", headers=H(t), json=(b or {}), timeout=60)

# ── DB handle (fixture + cleanup) ────────────────────────────────────────────
env = {}
for line in Path(__file__).resolve().parents[1].joinpath("backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
mongo = MongoClient(env["MONGO_URL"])
db = mongo[env.get("DB_NAME", "test_database")]

# ── Login ─────────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
r.raise_for_status()
admin = r.json()["token"]
print("admin login OK")

today = datetime.date.today().isoformat()

# ── Fixture: klien maklon ────────────────────────────────────────────────────
FIX_MARK = "flow-maklon-test"
fixture_client_id = f"flowmkl-client-{uuid.uuid4().hex[:8]}"
po_id = None
ar_invoice_id = None

try:
    db.dewi_maklon_clients.insert_one({
        "id": fixture_client_id,
        "code": "ZZFT",
        "name": "Flow Maklon Test Client",
        "status": "active",
        "created_by": FIX_MARK,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    })
    rec("TC-00", "PASS", f"[S] fixture klien dibuat id={fixture_client_id}")

    items_payload = [{
        "seri_no": "S01", "artikel": "FLOWTEST-ART", "sku_code": "FT-001",
        "color": "Black", "size": "M", "qty": 20, "cmt_rate_per_pcs": 5000,
    }]

    # ── STEP 1: Buat PO — negatif dulu ──────────────────────────────────────
    r = P("/api/dewi/maklon/pos", admin, {"client_id": "does-not-exist", "items": items_payload})
    rec("TC-01", "PASS" if r.status_code == 404 else "FAIL",
        f"[N] buat PO klien tidak valid -> 404 ({r.status_code})")

    # ── STEP 1b: Buat PO happy ───────────────────────────────────────────────
    r = P("/api/dewi/maklon/pos", admin, {
        "client_id": fixture_client_id, "po_date": today, "payment_terms": "net_30",
        "items": items_payload, "notes": "flow-maklon-test (auto)",
    })
    pj = r.json() if r.status_code == 200 else {}
    po_id = pj.get("id")
    ok = (r.status_code == 200 and pj.get("status") == "draft"
          and pj.get("total_qty") == 20 and pj.get("total_value") == 100000
          and pj.get("po_number"))
    rec("TC-02", "PASS" if ok else "FAIL",
        f"[H] buat PO -> {pj.get('po_number')} status={pj.get('status')} qty={pj.get('total_qty')} value={pj.get('total_value')} ({r.status_code})")

    # ── STEP 1c: Detail PO -> ambil item_id ──────────────────────────────────
    r = G(f"/api/dewi/maklon/pos/{po_id}", admin)
    dj = r.json() if r.status_code == 200 else {}
    po_items = dj.get("items", [])
    item0 = po_items[0] if po_items else {}
    ok = r.status_code == 200 and item0.get("item_id") and dj.get("status") == "draft"
    rec("TC-03", "PASS" if ok else "FAIL",
        f"[S] detail PO: item_id ada, status draft ({r.status_code})")

    # ── STEP 2: Dispatch sebelum confirm -> 400 ─────────────────────────────
    r = P("/api/dewi/maklon/dispatches", admin, {
        "po_id": po_id,
        "items": [{"item_id": item0.get("item_id"), "seri_no": "S01", "artikel": "FLOWTEST-ART", "qty_dispatched": 5}],
    })
    rec("TC-04", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] dispatch saat PO masih draft -> 400 ({r.status_code})")

    # ── STEP 3: Confirm PO (auto WO + auto Draft AR Invoice) ─────────────────
    r = P(f"/api/dewi/maklon/pos/{po_id}/confirm", admin)
    cj = r.json() if r.status_code == 200 else {}
    ar_invoice_id = cj.get("ar_invoice_id")
    ok = (r.status_code == 200 and cj.get("status") == "confirmed"
          and len(cj.get("work_orders_created", [])) == 1 and cj.get("ar_invoice_number"))
    rec("TC-05", "PASS" if ok else "FAIL",
        f"[H] confirm PO -> {len(cj.get('work_orders_created', []))} WO + Invoice {cj.get('ar_invoice_number')} ({r.status_code})")

    # ── STEP 3b: FASE 4 — engine WO diarsip: wo_number tracking terisi di item,
    #    dan TIDAK ada dokumen rahaza_work_orders yang tercipta ──────────────
    wo_number_ok = bool((cj.get("work_orders_created") or [{}])[0].get("wo_number"))
    wo_count = db.rahaza_work_orders.count_documents({"maklon_po_id": po_id})
    rec("TC-06", "PASS" if (wo_number_ok and wo_count == 0) else "FAIL",
        f"[S] wo_number tracking terisi + rahaza_work_orders TIDAK dibuat (count={wo_count})")

    r = G(f"/api/dewi/maklon/pos/{po_id}", admin)
    ok = r.status_code == 200 and r.json().get("status") == "confirmed"
    rec("TC-07", "PASS" if ok else "FAIL",
        f"[S] status PO = confirmed ({r.status_code})")

    # ── STEP 3c: confirm ulang -> 400 ────────────────────────────────────────
    r = P(f"/api/dewi/maklon/pos/{po_id}/confirm", admin)
    rec("TC-08", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] confirm ulang (bukan draft) -> 400 ({r.status_code})")

    # ── STEP 4: Dispatch qty > sisa -> 400 ───────────────────────────────────
    r = P("/api/dewi/maklon/dispatches", admin, {
        "po_id": po_id,
        "items": [{"item_id": item0.get("item_id"), "seri_no": "S01", "artikel": "FLOWTEST-ART", "qty_dispatched": 999}],
    })
    rec("TC-09", "PASS" if r.status_code == 400 else "FAIL",
        f"[N] dispatch melebihi sisa qty -> 400 ({r.status_code})")

    # ── STEP 4b: Dispatch penuh (20) ─────────────────────────────────────────
    r = P("/api/dewi/maklon/dispatches", admin, {
        "po_id": po_id, "dispatch_date": today, "driver_name": "Pak Budi", "vehicle_no": "B 1234 XX",
        "items": [{"item_id": item0.get("item_id"), "seri_no": "S01", "artikel": "FLOWTEST-ART",
                   "color": "Black", "size": "M", "qty_dispatched": 20}],
    })
    dispj = r.json() if r.status_code == 200 else {}
    dispatch_id = dispj.get("id")
    ok = r.status_code == 200 and dispatch_id and dispj.get("status") == "draft"
    rec("TC-10", "PASS" if ok else "FAIL",
        f"[H] buat dispatch {dispj.get('dispatch_number')} status={dispj.get('status')} ({r.status_code})")

    # ── STEP 4c: Konfirmasi dispatch -> PO completed ─────────────────────────
    r = PUT(f"/api/dewi/maklon/dispatches/{dispatch_id}/confirm", admin)
    fj = r.json() if r.status_code == 200 else {}
    ok = (r.status_code == 200 and fj.get("status") == "dispatched"
          and fj.get("po_delivery_status") == "completed" and fj.get("total_dispatched") == 20)
    rec("TC-11", "PASS" if ok else "FAIL",
        f"[H] konfirmasi dispatch -> PO {fj.get('po_delivery_status')}, terkirim {fj.get('total_dispatched')} ({r.status_code})")

    r = G(f"/api/dewi/maklon/pos/{po_id}", admin)
    dj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and dj.get("status") == "completed" and dj.get("qty_dispatched") == 20
    rec("TC-12", "PASS" if ok else "FAIL",
        f"[S] PO status=completed, qty_dispatched=20 (status={dj.get('status')}, disp={dj.get('qty_dispatched')})")

    # ── STEP 5: Posting AR ke Finance GL ─────────────────────────────────────
    r = P(f"/api/dewi/maklon/finance/pos/{po_id}/post-ar", admin)
    arj = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and arj.get("status") == "posted" and arj.get("je_number")
    rec("TC-13", "PASS" if ok else "FAIL",
        f"[H] post-ar -> {arj.get('je_number')} (posted) ({r.status_code}) {'' if ok else r.text[:160]}")

    # verifikasi AR invoice issued + PO gl_je_id
    inv = db.rahaza_ar_invoices.find_one({"id": ar_invoice_id}) if ar_invoice_id else None
    po_doc = db.dewi_maklon_pos.find_one({"id": po_id})
    ok = bool(inv) and inv.get("status") == "issued" and po_doc and po_doc.get("gl_je_id")
    rec("TC-14", "PASS" if ok else "FAIL",
        f"[S] AR invoice status=issued & PO.gl_je_id terisi (inv={inv.get('status') if inv else None})")

    # ── STEP 5b: post-ar idempotent ──────────────────────────────────────────
    r = P(f"/api/dewi/maklon/finance/pos/{po_id}/post-ar", admin)
    ok = r.status_code == 200 and r.json().get("already_posted") is True
    rec("TC-15", "PASS" if ok else "FAIL",
        f"[E] post-ar idempotent -> already_posted=True ({r.status_code})")

finally:
    # ── SELF-CLEANUP ─────────────────────────────────────────────────────────
    deleted = {}
    try:
        if po_id:
            # FASE 4: rahaza_work_orders diarsip — tidak ada WO utk dibersihkan.
            deleted["dispatches"] = db.dewi_maklon_dispatches.delete_many({"po_id": po_id}).deleted_count
            deleted["material_receive"] = db.dewi_maklon_material_receive.delete_many({"po_id": po_id}).deleted_count
            deleted["bom"] = db.dewi_maklon_bom.delete_many({"po_id": po_id}).deleted_count
            deleted["pos"] = db.dewi_maklon_pos.delete_many({"id": po_id}).deleted_count
        if ar_invoice_id:
            # jurnal AR (JE + lines) yang tercipta dari post-ar
            je = db.rahaza_journal_entries.find_one({"source_ref": f"maklon_ar:{ar_invoice_id}"})
            if je:
                deleted["journal_lines"] = db.rahaza_journal_lines.delete_many({"je_id": je["id"]}).deleted_count
                deleted["journal_entries"] = db.rahaza_journal_entries.delete_many({"id": je["id"]}).deleted_count
            deleted["ar_invoices"] = db.rahaza_ar_invoices.delete_many({"id": ar_invoice_id}).deleted_count
        deleted["fixture_client"] = db.dewi_maklon_clients.delete_many({"id": fixture_client_id}).deleted_count
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
print(" STATUS: PASS — Alur Maklon Inti happy-path terverifikasi end-to-end.")
sys.exit(0)
