"""Independent verification of PO state machine fix (iteration_93).

Verifies:
- FIX 1: PO_STATUS_TRANSITIONS enforced on /status and /close endpoints
- FIX 2: LIVE RBAC for cmt_vendor (cmtvendor@dewiaditya.id)
- Regression: no happy path break
"""
import time
import requests

BASE = "http://localhost:8001"
ADMIN = ("admin@garment.com", "Admin@123")
CMT_VENDOR = ("cmtvendor@dewiaditya.id", "Dewi@123")
KLIEN_MAKLON = ("klienmaklon@dewiaditya.id", "Dewi@123")

results = []

def rec(ok, name, detail=""):
    icon = "✅" if ok else "❌"
    results.append((ok, name, detail))
    print(f"{icon} {name}" + (f"  →  {detail}" if detail else ""))


def login(email, password, retries=3):
    for i in range(retries):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(15)
            continue
        raise RuntimeError(f"login failed {email}: {r.status_code} {r.text[:200]}")
    raise RuntimeError(f"login retries exhausted for {email}")


def H(t):
    return {"Authorization": f"Bearer {t}"}


def main():
    # --- login admin once ---
    admin_tok = login(*ADMIN)
    print(f"Admin login OK")
    time.sleep(2)

    # ---- Seed maklon (idempotent) ----
    r = requests.post(f"{BASE}/api/seed/maklon-full", headers=H(admin_tok))
    rec(r.status_code in (200, 201), "seed/maklon-full idempotent", f"HTTP {r.status_code}")

    # ---- Create a fresh maklon PO (Draft) ----
    po_payload = {
        "po_number": f"PO-MK-VERIFY-{int(time.time())}",
        "business_type": "maklon",
        "customer_name": "Verify Client",
        "buyer_id": "mk-client-demo-1",
        "vendor_id": "mk-vendor-demo-1",
        "delivery_date": "2026-12-31",
        "items": [{
            "product_id": "prod-verify",
            "product_name": "Verify Product",
            "quantity": 100,
            "unit_price": 10000,
            "total": 1000000,
        }],
        "notes": "verify_po_state_machine_test"
    }
    r = requests.post(f"{BASE}/api/production-pos", headers=H(admin_tok), json=po_payload)
    if r.status_code not in (200, 201):
        rec(False, "create PO", f"HTTP {r.status_code} {r.text[:300]}")
        return
    po = r.json()
    po_id = po.get("id")
    po_status = po.get("status", "Draft")
    rec(po_status == "Draft", "PO created Draft", f"id={po_id} status={po_status}")

    created_pos = [po_id]

    try:
        # ==== FIX 1: State machine =====
        # 1) Draft → Closed via /status must be 400
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Closed"})
        rec(r.status_code == 400, "Draft→Closed via /status ⇒ 400", f"HTTP {r.status_code}")

        # Verify DB still Draft
        r2 = requests.get(f"{BASE}/api/production-pos/{po_id}", headers=H(admin_tok))
        cur = r2.json().get("status") if r2.status_code == 200 else "?"
        rec(cur == "Draft", "PO status still Draft after illegal /status", f"cur={cur}")

        # 2) Draft → In Production (skip) must be 400
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "In Production"})
        rec(r.status_code == 400, "Draft→In Production (skip) ⇒ 400", f"HTTP {r.status_code}")

        # 3) Draft → Confirmed (adjacent) must be 200
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Confirmed"})
        rec(r.status_code == 200, "Draft→Confirmed (adjacent) ⇒ 200", f"HTTP {r.status_code}")

        # 4) Confirmed → Draft (backward) must be 400
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Draft"})
        rec(r.status_code == 400, "Confirmed→Draft (backward) ⇒ 400", f"HTTP {r.status_code}")

        # 5) /close from Confirmed must be 400
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/close",
                          headers=H(admin_tok), json={"close_reason": "test"})
        rec(r.status_code == 400, "/close from Confirmed ⇒ 400", f"HTTP {r.status_code} body={r.text[:120]}")

        # Also: /close from Draft — create another PO
        r = requests.post(f"{BASE}/api/production-pos", headers=H(admin_tok), json={**po_payload, "po_number": f"PO-MK-VERIFY-{int(time.time())}-2"})
        po2_id = r.json().get("id") if r.status_code in (200, 201) else None
        if po2_id:
            created_pos.append(po2_id)
            r = requests.post(f"{BASE}/api/production-pos/{po2_id}/close",
                              headers=H(admin_tok), json={"close_reason": "test"})
            rec(r.status_code == 400, "/close from Draft ⇒ 400", f"HTTP {r.status_code}")

        # 6) Try quick-complete then close: advance existing PO
        # Confirmed → Distributed via /status
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Distributed"})
        rec(r.status_code == 200, "Confirmed→Distributed ⇒ 200", f"HTTP {r.status_code}")
        # Distributed → In Production
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "In Production"})
        rec(r.status_code == 200, "Distributed→In Production ⇒ 200", f"HTTP {r.status_code}")
        # In Production → Production Complete
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Production Complete"})
        rec(r.status_code == 200, "In Production→Production Complete ⇒ 200", f"HTTP {r.status_code}")
        # Now /close should be allowed
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/close",
                          headers=H(admin_tok), json={"close_reason": "test-completed"})
        rec(r.status_code == 200, "/close from Production Complete ⇒ 200", f"HTTP {r.status_code}")

        # Verify Closed is final
        r = requests.post(f"{BASE}/api/production-pos/{po_id}/status",
                          headers=H(admin_tok), json={"status": "Ready to Close"})
        rec(r.status_code == 400, "Closed→any ⇒ 400 (final)", f"HTTP {r.status_code}")

        # ==== FIX 2: LIVE RBAC cmt_vendor ====
        time.sleep(3)  # spacing to avoid rate limit
        try:
            vend_tok = login(*CMT_VENDOR)
            rec(True, "cmt_vendor login OK", "cmtvendor@dewiaditya.id")
        except Exception as e:
            rec(False, "cmt_vendor login", str(e))
            vend_tok = None

        if vend_tok:
            # GET vendor-shipments: 200 and only vendor_id=mk-vendor-demo-1
            r = requests.get(f"{BASE}/api/vendor-shipments", headers=H(vend_tok))
            ok = r.status_code == 200
            data = r.json() if ok else {}
            items = data.get("data") if isinstance(data, dict) else data
            items = items or []
            all_own = all((x.get("vendor_id") == "mk-vendor-demo-1") for x in items) if items else True
            rec(ok and all_own, "GET /vendor-shipments (cmt_vendor scoped)",
                f"HTTP {r.status_code}, count={len(items)}, all_own={all_own}")

            # GET production-jobs
            r = requests.get(f"{BASE}/api/production-jobs", headers=H(vend_tok))
            ok = r.status_code == 200
            data = r.json() if ok else {}
            items = data.get("data") if isinstance(data, dict) else data
            items = items or []
            all_own = all((x.get("vendor_id") == "mk-vendor-demo-1") for x in items) if items else True
            rec(ok and all_own, "GET /production-jobs (cmt_vendor scoped)",
                f"HTTP {r.status_code}, count={len(items)}, all_own={all_own}")

            # POST /production-pos ⇒ 403
            r = requests.post(f"{BASE}/api/production-pos", headers=H(vend_tok), json=po_payload)
            rec(r.status_code == 403, "cmt_vendor POST /production-pos ⇒ 403", f"HTTP {r.status_code}")

            # DELETE /production-pos/{seed} ⇒ 403 (use po-mk-demo-1 seed id)
            r = requests.delete(f"{BASE}/api/production-pos/po-mk-demo-1", headers=H(vend_tok))
            rec(r.status_code == 403, "cmt_vendor DELETE seed PO ⇒ 403", f"HTTP {r.status_code}")

            # POST /production-pos/{id}/status ⇒ 403
            r = requests.post(f"{BASE}/api/production-pos/po-mk-demo-1/status",
                              headers=H(vend_tok), json={"status": "Confirmed"})
            rec(r.status_code == 403, "cmt_vendor POST /status ⇒ 403", f"HTTP {r.status_code}")

        # ==== Audit guards spot-check ====
        # vendor-shipments: no shipment to easily target here; rely on suite
        # Try illegal buyer-shipment status manual
        r = requests.get(f"{BASE}/api/buyer-shipments", headers=H(admin_tok))
        if r.status_code == 200:
            data = r.json()
            items = data.get("data") if isinstance(data, dict) else data
            items = items or []
            if items:
                bsid = items[0].get("id")
                r = requests.put(f"{BASE}/api/buyer-shipments/{bsid}",
                                 headers=H(admin_tok), json={"ship_status": "Shipped"})
                rec(r.status_code == 400, "PUT buyer-shipment ship_status manual ⇒ 400",
                    f"HTTP {r.status_code} body={r.text[:150]}")
            else:
                rec(True, "buyer-shipment spot-check skipped (no data)", "n/a")

    finally:
        # cleanup created POs (best-effort)
        for pid in created_pos:
            try:
                requests.delete(f"{BASE}/api/production-pos/{pid}", headers=H(admin_tok))
            except Exception:
                pass

    # ---- summary ----
    passed = sum(1 for r in results if r[0])
    total = len(results)
    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{total} PASS")
    for ok, name, _ in results:
        if not ok:
            print(f"  FAILED: {name}")
    return passed == total


if __name__ == "__main__":
    ok = main()
    exit(0 if ok else 1)
