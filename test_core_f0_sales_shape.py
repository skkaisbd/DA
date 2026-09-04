#!/usr/bin/env python3
"""test_core_f0_sales_shape.py — BUKTI SELESAI FASE F0 (D01/D02).

Menjawab satu pertanyaan dengan angka, bukan pendapat:

    Untuk SATU baris rekap harian Rp 12.500.000 / 48 pesanan, apakah jalur
    **entri manual** dan jalur **impor** sekarang memberi angka yang SAMA di
    Target, Dashboard, ROI Anggaran, dan Skor Kesehatan?

Sebelum F0 (terukur 2026-08-12):
    Target      manual Rp 12.500.000   impor **Rp 0**
    Dashboard   manual HTTP 200        impor **HTTP 500**
    Health      manual 89              impor **15**

Skrip ini memakai HTTP (endpoint sungguhan, bukan fungsi internal), membuat 2 toko
uji, lalu MEMBERSIHKAN semua yang dibuatnya.

Jalankan:  cd /app && python3 test_core_f0_sales_shape.py
"""
from __future__ import annotations

import io
import os
import sys
import json
import time
import urllib.request
import urllib.error

BASE = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN = ("admin@garment.com", "Admin@123")

DATE = "2026-08-01"
REVENUE = 12_500_000
ORDERS = 48
# Angka non-omzet supaya skor kesehatan benar-benar bisa dibandingkan
EXTRA = {
    "conversion_rate": 0.03,
    "fulfillment_rate": 0.98,
    "cancellation_rate": 0.01,
    "return_rate": 0.02,
    "late_shipment_rate": 0.01,
    "rating": 4.8,
    "review_count": 120,
    "response_rate": 0.95,
    "response_time_hours": 1.2,
}

G, R, Y, B, E = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"
_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _results.append((ok, label))
    print(f"  {G + 'LULUS' + E if ok else R + 'GAGAL' + E}  {label}" + (f"  — {detail}" if detail else ""))
    return ok


def req(method: str, path: str, token: str | None = None, body=None,
        files=None, form=None, expect_status=False):
    url = BASE + path
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif files or form:
        boundary = "----f0proof"
        buf = io.BytesIO()
        for k, v in (form or {}).items():
            buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (fname, content, ctype) in (files or {}).items():
            buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                      f"filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
            buf.write(content if isinstance(content, bytes) else content.encode())
            buf.write(b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        data = buf.getvalue()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    rq = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=90) as resp:
            payload = json.loads(resp.read() or b"null")
            return (resp.status, payload) if expect_status else payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        if expect_status:
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw[:400]}
        raise RuntimeError(f"{method} {path} → HTTP {e.code}: {raw[:400]}") from None


def main() -> int:
    print(f"\n{B}════ BUKTI FASE F0 — satu bentuk rekap harian untuk semua pintu ════{E}\n")
    _login = req("POST", "/api/auth/login", body={"email": ADMIN[0], "password": ADMIN[1]})
    token = _login.get("token") or _login.get("access_token")
    assert token, f"login gagal: {_login}"

    suffix = str(int(time.time()))[-6:]
    accounts = {}
    for tag in ("MANUAL", "IMPOR"):
        acc = req("POST", "/api/marketing/accounts", token, body={
            "account_code": f"F0-{tag}-{suffix}",
            "account_name": f"Uji F0 {tag} {suffix}",
            "platform": "tiktokshop",
            "username": f"f0{tag.lower()}{suffix}",
            "group": "official_store",
        })
        accounts[tag] = (acc.get("account") or acc).get("id") or acc.get("id")
        assert accounts[tag], f"gagal membuat akun uji {tag}: {acc}"
    print(f"  toko uji: MANUAL={accounts['MANUAL'][:8]}…  IMPOR={accounts['IMPOR'][:8]}…\n")

    try:
        # ── JALUR 1: entri manual ────────────────────────────────────────────
        req("POST", "/api/marketing/sales-data", token, body={
            "account_id": accounts["MANUAL"], "date": DATE, "revenue_type": "total",
            "revenue": REVENUE, "orders": ORDERS, **EXTRA,
        })

        # ── JALUR 2: impor lewat wizard resmi (tanpa AI) ─────────────────────
        csv_txt = (
            "Tanggal,Jenis Revenue,Revenue (Rp),Jumlah Order,Conversion Rate (%),"
            "Fulfillment Rate (%),Cancellation Rate (%),Return Rate (%),Late Shipment (%),"
            "Rating Toko,Jumlah Ulasan,Response Rate (%),Waktu Respon (jam)\n"
            f"{DATE},total,{REVENUE},{ORDERS},{EXTRA['conversion_rate']},"
            f"{EXTRA['fulfillment_rate']},{EXTRA['cancellation_rate']},{EXTRA['return_rate']},"
            f"{EXTRA['late_shipment_rate']},{EXTRA['rating']},{EXTRA['review_count']},"
            f"{EXTRA['response_rate']},{EXTRA['response_time_hours']}\n"
        )
        up = req("POST", "/api/marketing/data-import/upload", token,
                 files={"file": ("rekap.csv", csv_txt, "text/csv")},
                 form={"source_type": "sales_daily", "account_id": accounts["IMPOR"]})
        sess = up.get("session") or {}
        sid = sess.get("id") or up.get("session_id")
        assert sid, f"upload tidak mengembalikan sesi: {list(up.keys())}"
        rep = sess.get("mapping_report") or up.get("mapping_report") or {}
        check(bool(rep.get("ready")), "pemetaan kolom siap tanpa AI",
              f"terpetakan={rep.get('mapped')}/{rep.get('total_columns')}")
        commit = req("POST", f"/api/marketing/data-import/sessions/{sid}/commit", token, body={})
        check(commit.get("inserted") == 1, "impor commit 1 baris",
              f"inserted={commit.get('inserted')} rejected={commit.get('rejected')}")
        check(commit.get("target_collection") == "marketing_sales_data",
              "koleksi tujuan benar", commit.get("target_collection", "?"))

        # ── D01a: bentuk dokumen IDENTIK ─────────────────────────────────────
        docs = {}
        for tag in ("MANUAL", "IMPOR"):
            raw = req("GET", f"/api/marketing/accounts/{accounts[tag]}/sales", token)
            if isinstance(raw, list):
                arr = raw
            elif isinstance(raw, dict):
                arr = raw.get("sales") or raw.get("data") or raw.get("items") or []
            else:
                arr = []
            docs[tag] = next((d for d in arr if d.get("date") == DATE), None)
            check(docs[tag] is not None, f"[{tag}] dokumen rekap tersimpan")
        if docs["MANUAL"] and docs["IMPOR"]:
            for grp in ("metrics", "fulfillment", "customer_satisfaction"):
                a, b = docs["MANUAL"].get(grp), docs["IMPOR"].get(grp)
                check(isinstance(a, dict) and isinstance(b, dict) and bool(a) and bool(b),
                      f"grup `{grp}` ADA di kedua jalur")
                if isinstance(a, dict) and isinstance(b, dict):
                    check(set(a.keys()) == set(b.keys()),
                          f"grup `{grp}` punya field yang SAMA",
                          f"beda={sorted(set(a.keys()) ^ set(b.keys()))}")
            check(float(docs["MANUAL"]["metrics"].get("revenue", 0)) == float(REVENUE),
                  "[MANUAL] metrics.revenue benar", str(docs["MANUAL"]["metrics"].get("revenue")))
            check(float(docs["IMPOR"]["metrics"].get("revenue", 0)) == float(REVENUE),
                  "[IMPOR] metrics.revenue benar (DULU field ini tidak ada)",
                  str(docs["IMPOR"]["metrics"].get("revenue")))

        # ── D01b: TARGET membaca angka yang sama ─────────────────────────────
        req("POST", "/api/marketing/targets", token, body={
            "account_id": accounts["MANUAL"], "year": 2026, "month": 8,
            "revenue_target": 20_000_000, "orders_target": 100})
        req("POST", "/api/marketing/targets", token, body={
            "account_id": accounts["IMPOR"], "year": 2026, "month": 8,
            "revenue_target": 20_000_000, "orders_target": 100})
        summ = req("GET", "/api/marketing/targets/monthly-summary?year=2026&month=8", token)
        rows = (summ.get("accounts") or summ.get("data") or summ.get("items") or []
                if isinstance(summ, dict) else summ)
        by_id = {r.get("account_id"): r for r in rows if isinstance(r, dict)}
        for tag in ("MANUAL", "IMPOR"):
            row = by_id.get(accounts[tag]) or {}
            actual = ((row.get("actual") or {}).get("revenue")
                      if isinstance(row.get("actual"), dict) else row.get("revenue_actual"))
            check(float(actual or 0) == float(REVENUE),
                  f"[{tag}] Target: actual.revenue = Rp {REVENUE:,}",
                  f"dapat Rp {float(actual or 0):,.0f}")

        # ── D02: DASHBOARD tidak mati ────────────────────────────────────────
        st, _ = req("GET", "/api/marketing/dashboard/overview", token, expect_status=True)
        check(st == 200, "Dashboard overview HTTP 200 (DULU 500 karena `sale['metrics']`)", f"HTTP {st}")
        for tag in ("MANUAL", "IMPOR"):
            st2, body2 = req("GET", f"/api/marketing/accounts/{accounts[tag]}/dashboard", token,
                             expect_status=True)
            rev = 0
            if isinstance(body2, dict):
                rev = ((body2.get("total_revenue_stream") or {}).get("revenue")
                       or (body2.get("totals") or {}).get("total_revenue")
                       or body2.get("total_revenue") or 0)
            check(st2 == 200, f"[{tag}] Dashboard per toko HTTP 200", f"HTTP {st2}")
            check(float(rev or 0) == float(REVENUE), f"[{tag}] Dashboard omzet = Rp {REVENUE:,}",
                  f"dapat Rp {float(rev or 0):,.0f} · kunci={sorted(body2.keys()) if isinstance(body2, dict) else '?'}")

        # ── ROI ANGGARAN membaca angka yang sama ─────────────────────────────
        for tag in ("MANUAL", "IMPOR"):
            bs = req("GET", f"/api/marketing/budget/summary?account_id={accounts[tag]}&period=2026-08", token)
            check(float(bs.get("sales") or 0) == float(REVENUE),
                  f"[{tag}] ROI Anggaran: sales = Rp {REVENUE:,}",
                  f"dapat Rp {float(bs.get('sales') or 0):,.0f}")

        # ── SKOR KESEHATAN sama ──────────────────────────────────────────────
        scores = {}
        for tag in ("MANUAL", "IMPOR"):
            acc = req("GET", f"/api/marketing/accounts/{accounts[tag]}", token)
            acc = acc.get("account") or acc
            scores[tag] = acc.get("health_score")
        check(scores["MANUAL"] is not None and scores["MANUAL"] == scores["IMPOR"],
              "Skor Kesehatan IDENTIK antara manual & impor (DULU 89 vs 15)",
              f"manual={scores['MANUAL']} impor={scores['IMPOR']}")

        # ── Jalur impor lama benar-benar hilang ──────────────────────────────
        st3, _ = req("POST", "/api/marketing/import/sessions", token, body={}, expect_status=True)
        check(st3 == 404, "jalur impor AI lama sudah TIDAK ADA (404)", f"HTTP {st3}")
        st4, _ = req("POST", "/api/marketing/import/upload", token, body={}, expect_status=True)
        check(st4 == 404, "jalur impor sales lama sudah TIDAK ADA (404)", f"HTTP {st4}")

    finally:
        # ── bersihkan ────────────────────────────────────────────────────────
        for tag, aid in accounts.items():
            try:
                req("DELETE", f"/api/marketing/accounts/{aid}?hard=true", token, expect_status=True)
            except Exception:
                try:
                    req("DELETE", f"/api/marketing/accounts/{aid}", token, expect_status=True)
                except Exception:
                    print(f"  {Y}catatan{E}: akun uji {tag} ({aid[:8]}…) perlu dihapus manual")

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{B}RINGKAS: {passed}/{total} lulus{E}")
    if passed != total:
        print(f"{R}GAGAL:{E} " + "; ".join(lbl for ok, lbl in _results if not ok))
        return 1
    print(f"{G}FASE F0 TERBUKTI: satu angka, satu jawaban di semua layar.{E}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
