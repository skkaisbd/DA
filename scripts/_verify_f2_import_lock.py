#!/usr/bin/env python3
"""_verify_f2_import_lock.py — BUKTI: pagar F2 (omzet turunan) juga harus berlaku
untuk **jalur IMPOR** `sales_daily`, bukan hanya entri manual.

LUBANG YANG DIUJI
-----------------
`POST /api/marketing/sales-data` (entri manual) sudah menolak 409 untuk tanggal
yang omzetnya diturunkan dari pesanan. Tetapi Wizard Impor punya jenis data
"Sales Harian per Akun" (`sales_daily`) yang menulis ke koleksi **yang sama**
(`marketing_sales_data`) dengan kunci alami yang sama `(account_id, date,
revenue_type)`. Kalau jalur itu tidak diberi pagar, satu berkas Excel bisa
MENIMPA omzet turunan (mode "perbarui") atau dilewati tanpa penjelasan
(mode "lewati") ⇒ dua angka omzet untuk satu hari kembali lagi, tepat cacat
yang F2 dibuat untuk menutup.

Yang HARUS terjadi (kontrak):
  1. Angka turunan (`metrics.revenue`, `metrics.orders`) TIDAK berubah.
  2. Dokumen tetap `source='orders_auto'` + `locked_source=True`.
  3. Baris impor itu dilaporkan dengan alasan yang menyebut "diturunkan"
     (bukan diam-diam "dilewati (duplikat)").
  4. Field yang BUKAN turunan (mis. rating, response_rate) tetap boleh masuk —
     data tidak dibuang, hanya angka omzetnya yang dilindungi.
  5. Tanggal tanpa pesanan tetap bisa diimpor normal (`source='import'`).

Pakai:  python3 /app/scripts/_verify_f2_import_lock.py
"""
from __future__ import annotations

import io
import sys

import requests

BASE = "http://localhost:8001"
SAMPLE = "/app/samples/TikTok_UntukDikirim_2026-07-19.xlsx"
CODE = "TIKTOK-OUTFIT"
LOCKED_DATE = "2026-07-19"      # ada pesanan di berkas contoh ⇒ turunan
FREE_DATE = "2026-08-01"        # tidak ada pesanan ⇒ impor biasa boleh
FAILED: list[str] = []


def check(name: str, cond, detail: str = "") -> bool:
    mark = "\033[92mPASS\033[0m" if cond else "\033[91mFAIL\033[0m"
    print(f"  {mark}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)
    return bool(cond)


def sales_daily_csv(rows: list[dict]) -> bytes:
    """Berkas CSV `sales_daily` seminimal mungkin (header memakai label resmi)."""
    head = ["Tanggal", "Jenis Revenue", "Revenue (Rp)", "Jumlah Order",
            "Rating Toko", "Response Rate (%)"]
    out = [",".join(head)]
    for r in rows:
        out.append(",".join([
            r["date"], r.get("revenue_type", "total"), str(r["revenue"]),
            str(r.get("orders", 0)), str(r.get("rating", "")),
            str(r.get("response_rate", "")),
        ]))
    return ("\n".join(out) + "\n").encode()


def main() -> int:
    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    IMP = f"{BASE}/api/marketing/data-import"

    accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=30).json()
    accs = accs.get("accounts", accs) if isinstance(accs, dict) else accs
    acc = next((a for a in accs if a.get("account_code") == CODE), None)
    if not check("toko TIKTOK-OUTFIT ada", acc is not None):
        return 1
    aid = acc["id"]

    def daily(date: str) -> dict:
        r = requests.get(f"{BASE}/api/marketing/accounts/{aid}/sales", headers=H,
                         params={"date_from": date, "date_to": date,
                                 "revenue_type": "total"}, timeout=30)
        rows = r.json() if r.status_code == 200 else []
        return (rows or [{}])[0]

    sessions: list[str] = []
    try:
        # ── 1. impor pesanan ⇒ rekap harian turunan ──────────────────────────
        with open(SAMPLE, "rb") as fh:
            up = requests.post(f"{IMP}/upload", headers=H, files={
                "file": (SAMPLE.rsplit("/", 1)[-1], fh,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"source_type": "marketplace_orders", "account_id": aid}, timeout=300)
        if not check("impor pesanan: upload 200", up.status_code == 200, str(up.status_code)):
            print(up.text[:400])
            return 1
        sid_orders = up.json()["session"]["id"]
        sessions.append(sid_orders)
        cm = requests.post(f"{IMP}/sessions/{sid_orders}/commit", headers=H,
                           json={"on_duplicate": "skip"}, timeout=300)
        check("impor pesanan: 559 masuk", cm.json().get("inserted") == 559,
              str(cm.json().get("inserted")))

        before = daily(LOCKED_DATE)
        rev0 = (before.get("metrics") or {}).get("revenue")
        ord0 = (before.get("metrics") or {}).get("orders")
        check("rekap turunan tanggal terkunci ada & terkunci",
              before.get("locked_source") is True and before.get("source") == "orders_auto",
              f"source={before.get('source')} locked={before.get('locked_source')} rev={rev0}")

        # ── 2. impor `sales_daily` mode PERBARUI ke tanggal turunan ──────────
        csv = sales_daily_csv([
            {"date": LOCKED_DATE, "revenue": 1_000_000, "orders": 5,
             "rating": 4.8, "response_rate": 91},
            {"date": FREE_DATE, "revenue": 2_500_000, "orders": 9,
             "rating": 4.5, "response_rate": 88},
        ])
        up2 = requests.post(f"{IMP}/upload", headers=H, files={
            "file": ("rekap-harian.csv", io.BytesIO(csv), "text/csv")},
            data={"source_type": "sales_daily", "account_id": aid}, timeout=120)
        if not check("impor sales_daily: upload 200", up2.status_code == 200,
                     f"{up2.status_code} {up2.text[:200]}"):
            return 1
        sid_daily = up2.json()["session"]["id"]
        sessions.append(sid_daily)
        cm2 = requests.post(f"{IMP}/sessions/{sid_daily}/commit", headers=H,
                            json={"on_duplicate": "update"}, timeout=120)
        check("impor sales_daily: commit 200", cm2.status_code == 200,
              f"{cm2.status_code} {cm2.text[:200]}")
        body2 = cm2.json() if cm2.status_code == 200 else {}
        notes = body2.get("row_notes") or []

        # ── 3. KONTRAK ──────────────────────────────────────────────────────
        after = daily(LOCKED_DATE)
        m = after.get("metrics") or {}
        check("KONTRAK-1 omzet turunan TIDAK ditimpa impor",
              m.get("revenue") == rev0 and m.get("orders") == ord0,
              f"sesudah rev={m.get('revenue')} orders={m.get('orders')} "
              f"(sebelum rev={rev0} orders={ord0})")
        check("KONTRAK-2 dokumen tetap turunan & terkunci",
              after.get("source") == "orders_auto" and after.get("locked_source") is True,
              f"source={after.get('source')} locked={after.get('locked_source')}")
        why = " ".join(str(n.get("why")) for n in notes).lower()
        check("KONTRAK-3 baris dilaporkan dengan alasan 'diturunkan'",
              "diturunkan" in why,
              (why[:220] or "(tidak ada catatan baris)"))
        sat = after.get("customer_satisfaction") or {}
        check("KONTRAK-4 field non-turunan (rating) tetap masuk",
              float(sat.get("rating") or 0) == 4.8, str(sat.get("rating")))
        free = daily(FREE_DATE)
        check("KONTRAK-5 tanggal tanpa pesanan tetap bisa diimpor",
              (free.get("metrics") or {}).get("revenue") == 2_500_000
              and free.get("source") == "import",
              f"rev={(free.get('metrics') or {}).get('revenue')} source={free.get('source')}")
    finally:
        for sid in reversed(sessions):
            rb = requests.post(f"{IMP}/sessions/{sid}/rollback", headers=H, timeout=300)
            print(f"  (rollback {sid[:8]}: {rb.status_code})")
        requests.post(f"{BASE}/api/marketing/accounts/health/recompute-all",
                      headers=H, timeout=180)

    print()
    if FAILED:
        print(f"\033[91mGAGAL: {len(FAILED)}\033[0m — {FAILED}")
        return 1
    print("\033[92mSEMUA PASS — pagar F2 berlaku juga di jalur impor\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
