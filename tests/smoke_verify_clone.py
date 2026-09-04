#!/usr/bin/env python3
"""smoke_verify_clone.py — verifikasi cepat hasil clone repo `da` ke /app.

Cakupan (sesuai permintaan user: SMOKE TEST):
  1. /api/health  → status + koneksi DB
  2. Login 6 akun (admin + 5 role) → token valid & /api/auth/me
  3. Isi database per-domain (deteksi domain kosong)
  4. Sweep sampel endpoint GET tanpa parameter → deteksi 5xx / crash router
  5. Frontend static bundle (HTTP 200 + index.html berisi bundle)

Pakai:  python3 /app/tests/smoke_verify_clone.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = "http://localhost:8001"
FE = "http://localhost:3000"
G, R, Y, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"

ACCOUNTS = [
    ("admin@garment.com", "Admin@123"),
    ("hr@dewiaditya.id", "Dewi@123"),
    ("finance@dewiaditya.id", "Dewi@123"),
    ("spv@dewiaditya.id", "Dewi@123"),
    ("gudang@dewiaditya.id", "Dewi@123"),
    ("maklon@dewiaditya.id", "Dewi@123"),
]

results: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = f"{G}PASS{X}" if ok else f"{R}FAIL{X}"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


# ── 1. HEALTH ───────────────────────────────────────────────────────────────
def test_health() -> None:
    print(f"\n{C}1. HEALTH{X}")
    try:
        r = requests.get(f"{BASE}/api/health", timeout=15)
        d = r.json()
        rec("GET /api/health 200", r.status_code == 200, f"status={d.get('status')}")
        rec("MongoDB connected", d.get("db") == "connected",
            f"db={d.get('db')} latency={d.get('db_latency_ms')}ms")
        rec("service name", bool(d.get("service")), str(d.get("service")))
    except Exception as e:  # noqa: BLE001
        rec("GET /api/health", False, repr(e))


# ── 2. LOGIN 6 AKUN ─────────────────────────────────────────────────────────
def test_logins() -> dict[str, str]:
    print(f"\n{C}2. LOGIN 6 AKUN{X}")
    tokens: dict[str, str] = {}
    for email, pwd in ACCOUNTS:
        try:
            r = requests.post(f"{BASE}/api/auth/login",
                              json={"email": email, "password": pwd}, timeout=30)
            tok = (r.json() or {}).get("token") if r.status_code == 200 else None
            rec(f"login {email}", bool(tok), f"HTTP {r.status_code}")
            if tok:
                tokens[email] = tok
                me = requests.get(f"{BASE}/api/auth/me",
                                  headers={"Authorization": f"Bearer {tok}"}, timeout=20)
                mj = me.json() if me.status_code == 200 else {}
                rec(f"  /api/auth/me {email}", me.status_code == 200,
                    f"role={mj.get('role')} name={mj.get('full_name') or mj.get('name')}")
        except Exception as e:  # noqa: BLE001
            rec(f"login {email}", False, repr(e))
        time.sleep(0.4)  # hormati rate-limit login (10/60s)
    return tokens


# ── 3. ISI DATABASE PER DOMAIN ──────────────────────────────────────────────
DOMAIN_ENDPOINTS = [
    ("HR — karyawan", "/api/rahaza/employees"),
    ("Master — material", "/api/rahaza/materials"),
    ("Master — produk/style", "/api/dewi/rnd/styles"),
    ("Gudang — stok", "/api/wms/stock/unified/summary"),
    ("Produksi — order", "/api/rahaza/orders"),
    ("Maklon — PO", "/api/dewi/maklon/pos"),
    ("CMT — lifecycle", "/api/dewi/cmt/lifecycle"),
    ("Marketing — katalog", "/api/marketing/catalogs"),
    ("Keuangan — AR invoice", "/api/rahaza/ar-invoices"),
    ("Keuangan — AP invoice", "/api/rahaza/ap-invoices"),
    ("Aset", "/api/assets"),
    ("Notifikasi", "/api/notifications"),
]


def _count(payload) -> int | str:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for k in ("total", "count", "total_items"):
            if isinstance(payload.get(k), int):
                return payload[k]
        for k in ("items", "data", "results", "employees", "materials", "stock", "rows"):
            if isinstance(payload.get(k), list):
                return len(payload[k])
        return "dict"
    return "?"


def test_domain_data(token: str) -> list[str]:
    print(f"\n{C}3. ISI DATA PER DOMAIN{X}")
    h = {"Authorization": f"Bearer {token}"}
    empty: list[str] = []
    for label, path in DOMAIN_ENDPOINTS:
        try:
            r = requests.get(f"{BASE}{path}", headers=h, timeout=45)
            if r.status_code != 200:
                rec(f"{label} ({path})", False, f"HTTP {r.status_code}")
                continue
            n = _count(r.json())
            if isinstance(n, int) and n == 0:
                empty.append(label)
                print(f"  [{Y}KOSONG{X}] {label} ({path}) — 0 baris")
                results.append((f"{label} reachable", True, "0 baris"))
            else:
                rec(f"{label} ({path})", True, f"{n} baris")
        except Exception as e:  # noqa: BLE001
            rec(f"{label} ({path})", False, repr(e))
    return empty


# ── 4. SWEEP GET ENDPOINTS ──────────────────────────────────────────────────
SWEEP_SKIP = ("/api/health", "/api/openapi.json", "/api/backup", "/api/admin/backup")


def test_sweep(token: str, sample: int = 150) -> None:
    print(f"\n{C}4. SWEEP ENDPOINT GET (sampel {sample}){X}")
    try:
        spec = requests.get(f"{BASE}/api/openapi.json", timeout=60).json()
    except Exception as e:  # noqa: BLE001
        rec("ambil openapi.json", False, repr(e))
        return
    gets = [p for p, v in spec.get("paths", {}).items()
            if "get" in v and "{" not in p and not p.startswith(SWEEP_SKIP)]
    random.seed(7)
    picked = sorted(random.sample(gets, min(sample, len(gets))))
    h = {"Authorization": f"Bearer {token}"}

    def probe(path: str):
        try:
            r = requests.get(f"{BASE}{path}", headers=h, timeout=60)
            return path, r.status_code, (r.text[:160] if r.status_code >= 500 else "")
        except Exception as e:  # noqa: BLE001
            return path, -1, repr(e)[:160]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(probe, picked))
    dist: dict[int, int] = {}
    bad: list[tuple[str, int, str]] = []
    for path, code, body in out:
        dist[code] = dist.get(code, 0) + 1
        if code >= 500 or code == -1:
            bad.append((path, code, body))
    print(f"    distribusi status: {dict(sorted(dist.items()))} "
          f"({len(picked)} endpoint, {time.time() - t0:.1f}s)")
    rec(f"0 error 5xx dari {len(picked)} endpoint GET", not bad,
        "; ".join(f"{p} → {c} {b}" for p, c, b in bad[:6]) if bad else "semua < 500")
    Path("/tmp/sweep_detail.json").write_text(
        json.dumps([{"path": p, "code": c, "body": b} for p, c, b in out], indent=1))


# ── 5. FRONTEND ─────────────────────────────────────────────────────────────
def test_frontend() -> None:
    print(f"\n{C}5. FRONTEND STATIC BUNDLE{X}")
    try:
        r = requests.get(FE + "/", timeout=20)
        rec("GET :3000/ 200", r.status_code == 200, f"HTTP {r.status_code}")
        html = r.text
        rec("index.html memuat bundle JS", "static/js" in html,
            f"{len(html)} byte")
    except Exception as e:  # noqa: BLE001
        rec("GET :3000/", False, repr(e))
    idx = Path("/app/frontend/build/index.html")
    rec("build/index.html ada", idx.exists(),
        f"{idx.stat().st_size} byte" if idx.exists() else "tidak ada")


def main() -> int:
    print(f"{C}{'=' * 68}\nSMOKE VERIFY — DA37 ERP (hasil clone repo `da`)\n{'=' * 68}{X}")
    test_health()
    tokens = test_logins()
    admin = tokens.get("admin@garment.com")
    empty: list[str] = []
    if admin:
        empty = test_domain_data(admin)
        test_sweep(admin)
    else:
        rec("token admin tersedia", False, "tidak bisa lanjut tes ber-auth")
    test_frontend()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{C}{'=' * 68}{X}")
    print(f"  HASIL: {G}{passed} PASS{X} / {R}{total - passed} FAIL{X} (dari {total} cek)")
    if empty:
        print(f"  {Y}Domain tanpa data (kandidat seed): {', '.join(empty)}{X}")
    for name, ok, detail in results:
        if not ok:
            print(f"    {R}✗{X} {name} — {detail}")
    print(f"{C}{'=' * 68}{X}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
