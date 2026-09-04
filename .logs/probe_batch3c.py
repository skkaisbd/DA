#!/usr/bin/env python3
"""Probe batch-3C: ACC PR · Aset Tetap · Aset Inventaris · Sampel Maklon · FG Issue."""
import sys
import time

import requests

API = "http://localhost:8001"
S = requests.Session()
MARK = f"PROBE3C-{time.strftime('%H%M%S')}"


def login():
    r = S.post(f"{API}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=25)
    r.raise_for_status()
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def mode(t, key, m):
    return S.put(f"{API}/api/admin/doc-numbering", headers=H(t),
                 json={"key": key, "mode": m, "active": True}, timeout=30).status_code


def show(label, r):
    try:
        d = r.json()
    except Exception:
        d = {"raw": r.text[:120]}
    det = d.get("detail") if isinstance(d, dict) else d
    print(f"  {label}: HTTP {r.status_code} — {str(det)[:130]}")
    return d if isinstance(d, dict) else {}


def main():
    t = login()
    ym = time.strftime("%Y%m")

    print("\n[1] Permintaan Beli Aksesoris (acc_purchase_requests.pr_number)")
    key = "acc_purchase_requests.pr_number"
    body = {"purpose": MARK, "priority": "Normal", "notes": MARK,
            "items": [{"acc_id": "", "accessory_name": MARK, "qty_requested": 1,
                       "unit": "pcs", "estimated_price": 1000}]}
    mode(t, key, "auto")
    show("auto + ketikan (400)", S.post(f"{API}/api/acc/purchase-requests", headers=H(t),
                                       json={**body, "pr_number": "BEBAS-9"}, timeout=30))
    d = show("auto (200/201)", S.post(f"{API}/api/acc/purchase-requests", headers=H(t),
                                     json=body, timeout=30))
    mode(t, key, "manual")
    show("manual kosong (400)", S.post(f"{API}/api/acc/purchase-requests", headers=H(t),
                                       json=body, timeout=30))
    show("manual pola bebas (400)", S.post(f"{API}/api/acc/purchase-requests", headers=H(t),
                                          json={**body, "pr_number": "PR/BEBAS"}, timeout=30))
    d2 = show("manual benar ACC-PR-9901 (200/201)",
              S.post(f"{API}/api/acc/purchase-requests", headers=H(t),
                     json={**body, "pr_number": "ACC-PR-9901"}, timeout=30))
    mode(t, key, "auto")
    print("   nomor:", d.get("pr_number"), "/", d2.get("pr_number"))

    print("\n[2] Aset Tetap (rahaza_fixed_assets.code)")
    key = "rahaza_fixed_assets.code"
    ab = {"name": MARK, "category": "peralatan", "purchase_cost": 1000000,
          "useful_life_months": 60, "notes": MARK}
    mode(t, key, "auto")
    show("auto + ketikan (400)",
         S.post(f"{API}/api/rahaza/finance/fixed-assets", headers=H(t),
                json={**ab, "code": "BEBAS-9"}, timeout=40))
    d = show("auto tanpa kode (200)",
             S.post(f"{API}/api/rahaza/finance/fixed-assets", headers=H(t), json=ab, timeout=40))
    mode(t, key, "manual")
    show("manual kosong (400)",
         S.post(f"{API}/api/rahaza/finance/fixed-assets", headers=H(t), json=ab, timeout=40))
    d2 = show("manual benar FA-99001 (200)",
              S.post(f"{API}/api/rahaza/finance/fixed-assets", headers=H(t),
                     json={**ab, "code": "FA-99001"}, timeout=40))
    mode(t, key, "auto")
    print("   kode:", d.get("code") or (d.get("asset") or {}).get("code"), "/",
          d2.get("code") or (d2.get("asset") or {}).get("code"))

    print("\n[3] Aset Inventaris (dewi_assets.asset_number)")
    key = "dewi_assets.asset_number"
    cats = S.get(f"{API}/api/assets/categories", headers=H(t), timeout=30).json()
    cats = cats if isinstance(cats, list) else cats.get("items", [])
    cid = cats[0]["id"] if cats else ""
    ib = {"name": MARK, "category_id": cid, "purchase_cost": 500000, "notes": MARK}
    mode(t, key, "auto")
    show("auto + ketikan (400)", S.post(f"{API}/api/assets", headers=H(t),
                                        json={**ib, "asset_number": "BEBAS-9"}, timeout=40))
    d = show("auto (200)", S.post(f"{API}/api/assets", headers=H(t), json=ib, timeout=40))
    print("   nomor:", d.get("asset_number"), "· kategori:", cats[0].get("code") if cats else "-")
    mode(t, key, "auto")

    print("\n[4] Sampel Maklon (dewi_maklon_samples.sample_code)")
    key = "dewi_maklon_samples.sample_code"
    orders = S.get(f"{API}/api/dewi/maklon/pos?limit=5", headers=H(t), timeout=30).json()
    rows = orders if isinstance(orders, list) else orders.get("items", [])
    oid = rows[0]["id"] if rows else ""
    sb = {"order_id": oid, "product_name": MARK, "sample_qty": 1, "notes": MARK}
    mode(t, key, "auto")
    show("auto + ketikan (400)", S.post(f"{API}/api/dewi/maklon/samples", headers=H(t),
                                       json={**sb, "sample_code": "BEBAS-9"}, timeout=30))
    d = show("auto (200/201)", S.post(f"{API}/api/dewi/maklon/samples", headers=H(t),
                                     json=sb, timeout=30))
    print("   kode:", d.get("sample_code"))
    mode(t, key, "auto")

    print("\n[5] Pengeluaran FG (rahaza_fg_issues.issue_number) — jalur penolakan")
    key = "rahaza_fg_issues.issue_number"
    mode(t, key, "auto")
    show("auto + ketikan pada material tak ada (harus 400/404, BUKAN 500)",
         S.post(f"{API}/api/rahaza/fg-issue", headers=H(t),
                json={"material_id": "tidak-ada", "qty": 1, "reason": "lainnya",
                      "issue_number": "BEBAS-9"}, timeout=30))
    mode(t, key, "auto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
