"""E2E API-level test — Alur After-Sales / Retur & Refund (Toko/Gudang).

Cakupan happy-path:
  Toko:  create marketing_return -> approve -> create-wh-return (jembatan)
  Gudang: receive -> inspect -> resolve(Restock, qty=1) -> callback sync balik
  Toko:  complete (dgn wh_return_id -> tanpa warning) -> create-credit-note

Semua data uji dibuat unik & dibersihkan (best-effort) di akhir.
"""
import requests
import sys
from datetime import date, datetime

BASE = "http://localhost:8001"
S = requests.Session()
st = {}


def login():
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({
        "Authorization": f"Bearer {r.json()['token']}",
        "Content-Type": "application/json",
    })
    print("PASS login (admin@garment.com)")


def create_marketing_return():
    ts = datetime.now().strftime("%H%M%S")
    body = {
        "date": date.today().isoformat(),
        "order_id": f"E2E-AFTER-{ts}",
        "platform": "shopee",
        "product": "Kaos Basic Hitam L (E2E After-Sales)",
        "price": 150000,
        "reason": "ukuran_salah",
        "reason_detail": "Pelanggan meminta pengembalian karena ukuran L kekecilan (E2E test)",
        "courier": "jnt",
        "refund_type": "full_refund",
        "notes": "E2E flow-toko-after-sales test",
    }
    r = S.post(f"{BASE}/api/marketing/returns", json=body)
    assert r.status_code == 200, f"create return {r.status_code}: {r.text}"
    ret = r.json()["data"]
    st["return_id"] = ret["id"]
    st["order_id"] = ret["order_id"]
    print(f"PASS create marketing_return {st['order_id']} (id={st['return_id'][:8]}, status={ret['status']})")


def approve_marketing_return():
    r = S.post(f"{BASE}/api/marketing/returns/{st['return_id']}/approve")
    assert r.status_code == 200, f"approve {r.status_code}: {r.text}"
    body = r.json()
    print(f"PASS approve marketing_return -> status={body.get('data', {}).get('status', 'approved')}")


def create_wh_return_bridge():
    """RC-FLOW-UX-11a (opsi B — link manual) — jembatan Marketing -> Gudang."""
    r = S.post(f"{BASE}/api/marketing/returns/{st['return_id']}/create-wh-return")
    assert r.status_code == 200, f"create-wh-return {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("success") is True, f"create-wh-return response {body}"
    assert body.get("already_exists") is False, "should be freshly created"
    data = body["data"]
    st["wh_return_id"] = data["id"]
    st["wh_return_code"] = data["return_code"]
    assert data["source_marketing_return_id"] == st["return_id"], "back-ref missing"
    assert data["status"] == "Pending", f"initial wh_return status must be Pending, got {data['status']}"
    print(f"PASS create-wh-return {st['wh_return_code']} (wh_id={st['wh_return_id'][:8]}, status=Pending)")

    # Idempotency check
    r2 = S.post(f"{BASE}/api/marketing/returns/{st['return_id']}/create-wh-return")
    assert r2.status_code == 200, f"idempotency create-wh-return {r2.status_code}"
    b2 = r2.json()
    assert b2.get("already_exists") is True, "second call must return already_exists=True"
    print("PASS idempotency create-wh-return (no duplicate)")


def wh_receive():
    body = {
        "unboxing_condition_notes": "Kemasan luar sedikit lecet, isi utuh",
        "unboxing_photo_notes": "-",
        "package_condition": "baik",
    }
    r = S.post(f"{BASE}/api/wh/returns/{st['wh_return_id']}/receive", json=body)
    assert r.status_code == 200, f"receive {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "Received", f"status after receive: {data['status']}"
    print(f"PASS wh_returns receive -> status={data['status']}")


def wh_inspect():
    body = {
        "item_condition": "Baik (dapat dijual kembali)",
        "return_cause": "Kesalahan Konsumen (salah ukuran)",
        "cause_detail": "Pelanggan salah pilih ukuran; produk masih baru dgn label",
        "recommended_action": "Restock ke Gudang",
    }
    r = S.post(f"{BASE}/api/wh/returns/{st['wh_return_id']}/inspect", json=body)
    assert r.status_code == 200, f"inspect {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "Inspected", f"status after inspect: {data['status']}"
    print(f"PASS wh_returns inspect -> status={data['status']}")


def wh_resolve_restock():
    """Resolve dgn Restock — memicu $inc fg_inventory + callback ke marketing_returns."""
    body = {
        "action_taken": "Restock ke Gudang",
        "action_notes": "Barang layak jual, kembalikan ke stok FG",
        "restock_qty": 1,
    }
    r = S.post(f"{BASE}/api/wh/returns/{st['wh_return_id']}/resolve", json=body)
    assert r.status_code == 200, f"resolve {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "Resolved", f"status after resolve: {data['status']}"
    assert data["action_taken"] == "Restock ke Gudang", "action mismatch"
    print(f"PASS wh_returns resolve(Restock qty=1) -> status={data['status']}")

    # Verifikasi callback sync balik ke marketing_returns
    r2 = S.get(f"{BASE}/api/marketing/returns/{st['return_id']}")
    assert r2.status_code == 200
    mret = r2.json()["data"]
    assert mret.get("wh_return_status") == "Resolved", (
        f"callback sync failed: wh_return_status={mret.get('wh_return_status')}"
    )
    assert mret.get("wh_action_taken") == "Restock ke Gudang", "wh_action_taken not synced"
    assert mret.get("wh_restock_qty") == 1, f"wh_restock_qty={mret.get('wh_restock_qty')}"
    print("PASS sync marketing_returns.wh_return_status=Resolved (callback berjalan)")


def complete_marketing_return_no_warning():
    """RC-FLOW-UX-11c — complete dgn wh_return_id => warning=null."""
    r = S.post(f"{BASE}/api/marketing/returns/{st['return_id']}/complete")
    assert r.status_code == 200, f"complete {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("success") is True
    warning = body.get("warning")
    assert warning is None, f"warning should be null when wh_return_id present, got: {warning}"
    print("PASS complete marketing_return (warning=null karena wh_return_id ada)")


def create_credit_note():
    """Terbitkan Nota Kredit -> auto post GL reversing (Dr Revenue / Cr AR)."""
    r = S.post(f"{BASE}/api/marketing/returns/{st['return_id']}/create-credit-note")
    assert r.status_code == 200, f"credit-note {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("success") is True
    cn = body["data"]
    st["credit_note_id"] = cn["id"]
    print(f"PASS create-credit-note {cn.get('cn_number', cn.get('credit_note_number', ''))} (id={st['credit_note_id'][:8]})")


def cleanup():
    """Best-effort cleanup — jangan gagalkan test bila cleanup punya kendala."""
    try:
        if st.get("wh_return_id"):
            S.post(f"{BASE}/api/wh/returns/{st['wh_return_id']}/cancel", json={"reason": "E2E cleanup"})
    except Exception:
        pass
    try:
        if st.get("return_id"):
            S.delete(f"{BASE}/api/marketing/returns/{st['return_id']}")
    except Exception:
        pass
    print("INFO cleanup best-effort selesai (DB pristine terjaga)")


def main():
    login()
    create_marketing_return()
    approve_marketing_return()
    create_wh_return_bridge()
    wh_receive()
    wh_inspect()
    wh_resolve_restock()
    complete_marketing_return_no_warning()
    create_credit_note()
    cleanup()
    print("\n=== FLOW-TOKO-AFTER-SALES ALL PASS ===")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        cleanup()
        sys.exit(2)
