"""
E2E API-level POC test — Alur Aksesoris Inti (Portal Aksesoris).

Alur bisnis: Purchase Request -> Stok -> Request Internal -> Opname.

Happy path:
  login
  -> buat master aksesoris (fixture)                              [POST /api/acc/items]
  --- FASE 1: PURCHASE REQUEST -------------------------------------------------
  -> buat PR draft (items)                                        [POST /api/acc/purchase-requests]
  -> submit -> approve -> ordered -> received (auto +stok)        [PUT  /api/acc/purchase-requests/{id}]
  -> verifikasi stok bertambah                                    [GET  /api/acc/stock]
  --- FASE 2: STOK -------------------------------------------------------------
  -> terima stok manual (+)                                       [POST /api/acc/stock/receive]
  -> keluarkan stok (-)                                           [POST /api/acc/stock/issue]
  -> movements terbaca                                            [GET  /api/acc/stock/movements]
  --- FASE 3: REQUEST INTERNAL (SSOT) ------------------------------------------
  -> buat request internal (request_type=internal_issuance)       [POST /api/dewi/accessory-requests]
  -> submit -> allocate -> deliver                                [POST /api/dewi/accessory-requests/{id}/...]
  -> stats summary                                                [GET  /api/dewi/accessory-requests/stats/summary]
  --- FASE 4: OPNAME -----------------------------------------------------------
  -> start sesi opname (snapshot semua aksesoris)                 [POST /api/acc/opname]
  -> input hitung fisik (selisih)                                 [PUT  /api/acc/opname/{id}/count]
  -> complete (apply adjustment + posting stok)                   [POST /api/acc/opname/{id}/complete]
  -> verifikasi stok ter-adjust ke angka fisik                    [GET  /api/acc/stock]
Guards:
  -> issue melebihi stok ditolak (400)
  -> submit request internal non-draft (allocate lagi) ditolak (400)
  -> start opname kedua saat masih ada sesi aktif ditolak (400)
  -> count pada sesi opname yang sudah complete ditolak (400)
Self-cleanup (hard): hapus master aksesoris + PR + request internal + sesi opname
  + stok + movements uji (DB pristine).
"""
import sys
import uuid
import requests

BASE = "http://localhost:8001"
S = requests.Session()

ACC_CODE = f"E2E-ACC-{uuid.uuid4().hex[:6].upper()}"
ACC_NAME = "E2E Kancing Flow Test"
st = {"acc_id": None, "pr_id": None, "req_id": None, "opname_id": None}


def _mongo():
    url = db = None
    with open("/app/backend/.env") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("MONGO_URL="):
                url = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("DB_NAME="):
                db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    from pymongo import MongoClient
    cli = MongoClient(url)
    return cli, cli[db or "test_database"]


def login():
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    print("PASS login")


def _acc_stock_qty(acc_id):
    """Ambil stock_qty item dari GET /api/acc/stock."""
    r = S.get(f"{BASE}/api/acc/stock")
    assert r.status_code == 200, f"stock list {r.status_code}: {r.text}"
    for row in r.json():
        if row["id"] == acc_id:
            return float(row["stock_qty"])
    return None


def pre_clean():
    """Batalkan sesi opname aksesoris yang masih 'open' agar guard tidak salah blokir."""
    cli, db = _mongo()
    n = db.wh_opname_sessions2.update_many(
        {"domain": "accessory", "status": "open"},
        {"$set": {"status": "cancelled"}},
    ).modified_count
    cli.close()
    if n:
        print(f"PRE-CLEAN: {n} sesi opname aksesoris 'open' lama dibatalkan")


def main():
    login()
    pre_clean()

    # ── Fixture: master aksesoris ────────────────────────────────────────────
    r = S.post(f"{BASE}/api/acc/items", json={
        "code": ACC_CODE, "name": ACC_NAME, "unit": "pcs",
        "category": "Kancing", "min_stock": 10,
    })
    assert r.status_code == 201, f"create item {r.status_code}: {r.text}"
    acc = r.json()
    st["acc_id"] = acc["id"]
    assert acc["code"] == ACC_CODE and acc["stock_qty"] == 0, f"item awal {acc}"
    print(f"PASS buat master aksesoris {ACC_CODE} (stok awal 0)")

    # ═══════════ FASE 1 — PURCHASE REQUEST ═══════════════════════════════════
    r = S.post(f"{BASE}/api/acc/purchase-requests", json={
        "purpose": "Restock kancing produksi",
        "supplier": "PT Supplier Aksesoris",
        "priority": "Normal",
        "items": [{
            "acc_id": st["acc_id"], "acc_code": ACC_CODE, "acc_name": ACC_NAME,
            "qty_requested": 50, "unit": "pcs", "estimated_price": 100,
        }],
        "notes": "E2E fixture PR",
    })
    assert r.status_code == 201, f"create PR {r.status_code}: {r.text}"
    pr = r.json()
    st["pr_id"] = pr["id"]
    assert pr["status"] == "Draft" and pr["pr_number"].startswith("ACC-PR-"), f"PR awal {pr}"
    print(f"PASS buat PR {pr['pr_number']} status=Draft")

    for status in ("Submitted", "Approved", "Ordered"):
        r = S.put(f"{BASE}/api/acc/purchase-requests/{st['pr_id']}",
                  json={"status": status, "finance_notes": "E2E approve"})
        assert r.status_code == 200 and r.json()["status"] == status, \
            f"PR->{status} {r.status_code}: {r.text}"
    print("PASS PR transisi Draft->Submitted->Approved->Ordered")

    r = S.put(f"{BASE}/api/acc/purchase-requests/{st['pr_id']}", json={"status": "Received"})
    assert r.status_code == 200 and r.json()["status"] == "Received", \
        f"PR->Received {r.status_code}: {r.text}"
    qty_after_pr = _acc_stock_qty(st["acc_id"])
    assert qty_after_pr == 50, f"stok setelah PR Received harus 50, dapat {qty_after_pr}"
    print("PASS PR Received => stok aksesoris auto +50 (verified GET /api/acc/stock)")

    # ═══════════ FASE 2 — STOK ════════════════════════════════════════════════
    r = S.post(f"{BASE}/api/acc/stock/receive",
               json={"acc_id": st["acc_id"], "qty": 20, "notes": "E2E receive manual"})
    assert r.status_code == 200 and r.json()["new_stock_qty"] == 70, \
        f"receive {r.status_code}: {r.text}"
    print("PASS terima stok manual +20 => 70")

    r = S.post(f"{BASE}/api/acc/stock/issue",
               json={"acc_id": st["acc_id"], "qty": 10, "notes": "E2E issue"})
    assert r.status_code == 201 and r.json()["new_qty"] == 60, \
        f"issue {r.status_code}: {r.text}"
    print("PASS keluarkan stok -10 => 60")

    # Guard: issue melebihi stok
    rg = S.post(f"{BASE}/api/acc/stock/issue",
                json={"acc_id": st["acc_id"], "qty": 999999})
    assert rg.status_code >= 400, f"expected reject over-issue got {rg.status_code}"
    print("PASS guard: issue melebihi stok ditolak (400)")

    r = S.get(f"{BASE}/api/acc/stock/movements", params={"acc_id": st["acc_id"]})
    assert r.status_code == 200, f"movements {r.status_code}: {r.text}"
    print(f"PASS GET movements 200 (list len={len(r.json())})")

    # ═══════════ FASE 3 — REQUEST INTERNAL (SSOT) ════════════════════════════
    r = S.post(f"{BASE}/api/dewi/accessory-requests", json={
        "request_type": "internal_issuance",
        "divisi": "Produksi",
        "purpose": "Kebutuhan lini jahit",
        "items": [{"material_code": ACC_CODE, "material_name": ACC_NAME,
                   "qty": 5, "unit": "pcs"}],
        "notes": "E2E internal request",
    })
    assert r.status_code == 200, f"create internal req {r.status_code}: {r.text}"
    req = r.json()
    st["req_id"] = req["id"]
    assert req["request_type"] == "internal_issuance" and req["status"] == "draft", f"req awal {req}"
    print(f"PASS buat request internal {req['request_code']} status=draft")

    r = S.post(f"{BASE}/api/dewi/accessory-requests/{st['req_id']}/submit")
    assert r.status_code == 200, f"submit req {r.status_code}: {r.text}"
    r = S.post(f"{BASE}/api/dewi/accessory-requests/{st['req_id']}/allocate",
               json={"notes": "alokasi E2E"})
    assert r.status_code == 200, f"allocate req {r.status_code}: {r.text}"

    # Guard: allocate lagi (status sudah allocated, bukan submitted)
    rg = S.post(f"{BASE}/api/dewi/accessory-requests/{st['req_id']}/allocate", json={})
    assert rg.status_code >= 400, f"expected reject re-allocate got {rg.status_code}"
    print("PASS guard: allocate request non-submitted ditolak (400)")

    r = S.post(f"{BASE}/api/dewi/accessory-requests/{st['req_id']}/deliver",
               json={"notes": "diserahkan E2E"})
    assert r.status_code == 200, f"deliver req {r.status_code}: {r.text}"
    detail = S.get(f"{BASE}/api/dewi/accessory-requests/{st['req_id']}").json()
    assert detail["status"] == "delivered", f"req akhir {detail['status']}"
    print("PASS request internal draft->submitted->allocated->delivered")

    r = S.get(f"{BASE}/api/dewi/accessory-requests/stats/summary")
    assert r.status_code == 200 and "by_request_type" in r.json(), f"stats {r.status_code}: {r.text}"
    print("PASS GET stats/summary 200 (by_request_type ada)")

    # ═══════════ FASE 4 — OPNAME ══════════════════════════════════════════════
    r = S.post(f"{BASE}/api/acc/opname", json={"notes": "E2E opname aksesoris"})
    assert r.status_code == 201, f"start opname {r.status_code}: {r.text}"
    sess = r.json()
    st["opname_id"] = sess["id"]
    assert sess["status"] == "Active", f"opname start {sess}"
    print(f"PASS start opname {sess['ref_number']} status=Active total_items={sess['total_items']}")

    # Guard: start opname kedua saat ada sesi aktif
    rg = S.post(f"{BASE}/api/acc/opname", json={"notes": "E2E opname 2"})
    assert rg.status_code >= 400, f"expected reject 2nd opname got {rg.status_code}"
    print("PASS guard: start opname kedua (sesi aktif) ditolak (400)")

    # Detail: pastikan baris item kita ada dgn system_qty=60
    detail = S.get(f"{BASE}/api/acc/opname/{st['opname_id']}").json()
    line = next((l for l in detail["lines"] if l["acc_id"] == st["acc_id"]), None)
    assert line and line["system_qty"] == 60, f"baris opname item system_qty {line}"
    print("PASS detail opname: baris item ditemukan system_qty=60")

    # Count fisik 57 => selisih -3
    r = S.put(f"{BASE}/api/acc/opname/{st['opname_id']}/count",
              json={"acc_id": st["acc_id"], "counted_qty": 57, "notes": "hitung fisik E2E"})
    assert r.status_code == 200 and r.json()["diff"] == -3, f"count {r.status_code}: {r.text}"
    print("PASS input hitung fisik 57 (system 60 => selisih -3)")

    # Complete => apply adjustment + posting stok
    r = S.post(f"{BASE}/api/acc/opname/{st['opname_id']}/complete")
    assert r.status_code == 200 and r.json()["adjustments_made"] >= 1, \
        f"complete {r.status_code}: {r.text}"
    qty_final = _acc_stock_qty(st["acc_id"])
    assert qty_final == 57, f"stok setelah opname harus 57, dapat {qty_final}"
    print("PASS complete opname => stok ter-adjust 60 -> 57 (verified)")

    # Guard: count setelah complete
    rg = S.put(f"{BASE}/api/acc/opname/{st['opname_id']}/count",
               json={"acc_id": st["acc_id"], "counted_qty": 1})
    assert rg.status_code >= 400, f"expected reject count-after-complete got {rg.status_code}"
    print("PASS guard: count pada sesi opname yang sudah complete ditolak (400)")

    # Verifikasi audit movement (adjust) via DB
    cli, db = _mongo()
    n_adj = db.rahaza_material_movements.count_documents(
        {"material_id": st["acc_id"], "reference_type": "opname"})
    cli.close()
    assert n_adj >= 1, "movement audit opname (adjust) tidak tercatat"
    print(f"PASS audit: {n_adj} movement opname (adjust) tercatat di rahaza_material_movements")

    print("\n=== ALUR AKSESORIS INTI ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        acc_id = st.get("acc_id")
        n_i = db.rahaza_materials.delete_many({"code": ACC_CODE}).deleted_count
        n_pr = db.acc_purchase_requests.delete_many(
            {"id": st.get("pr_id")}).deleted_count if st.get("pr_id") else 0
        n_rq = db.dewi_accessory_requests.delete_many(
            {"id": st.get("req_id")}).deleted_count if st.get("req_id") else 0
        n_op = db.wh_opname_sessions2.delete_many(
            {"id": st.get("opname_id")}).deleted_count if st.get("opname_id") else 0
        n_mv = n_stk = 0
        if acc_id:
            n_mv = db.rahaza_material_movements.delete_many({"material_id": acc_id}).deleted_count
            n_stk = db.rahaza_material_stock.delete_many({"material_id": acc_id}).deleted_count
        cli.close()
        print(f"CLEANUP: item={n_i} pr={n_pr} req={n_rq} opname={n_op} "
              f"stok={n_stk} movement={n_mv} dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
