#!/usr/bin/env python3
"""verify_fase_d_dashboard_marketing.py — FASE D (2026-08-16).

Keluhan pemilik: *"dashboard marketing hilang dari menu dan angkanya tidak nyambung."*

YANG TERUKUR SEBELUM PERBAIKAN:
  · `toko-dashboard` sudah lama menjadi modul BAWAAN Portal Marketing
    (`App.js` → `PORTAL_DEFAULT_MODULE.toko`), tetapi **tidak tercantum di satu pun
    section sidebar**. Jadi begitu pemakai membuka menu lain, tidak ada jalan pulang
    ke dashboard selain memuat ulang portal. Menu yang tidak ada tidak bisa
    dilaporkan rusak — ia hanya "hilang".
  · Dashboard sama sekali tidak memuat **target · anggaran · ROI**, padahal seluruh
    siklus kerja marketing bulanan berdiri di atas tiga angka itu
    (`core/marketing_cycle.py`, F5). Yang tampil hanya penjumlahan input harian
    **30 hari terakhir** — rentang yang selalu menyerempet dua bulan, sehingga
    omzetnya mustahil disandingkan dengan targetnya. Itulah "angkanya usang".

INVARIAN:
  D1  pintu `toko-dashboard` ada di sidebar Portal Marketing & termap di registry
  D2  dashboard mengambil angka resmi dari SSOT siklus (`/marketing/cycle/overview`)
  D3  layar TIDAK menjumlah ulang angka siklus di browser (tanpa `.reduce(`)
  D4  bawaan rentang dashboard = **bulan berjalan** (biar bisa dibanding target)
  D5  semua endpoint yang dipanggil dashboard HIDUP (bukan 404)
  D6  `totals` dari backend = jumlah baris toko (backend yang menjumlah, bukan layar)
  D7  lingkup toko tetap ditegakkan: staf tanpa toko tidak melihat omzet toko lain
  D8  ROI tidak pernah diklaim sahih saat cakupan HPP < 80%

Pakai:
    python3 scripts/verify_fase_d_dashboard_marketing.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

NAV = ROOT / "frontend/src/components/erp/portal-shell/portalNav.js"
REG = ROOT / "frontend/src/components/erp/moduleRegistry.js"
DASH = ROOT / "frontend/src/components/erp/MarketingDashboard.jsx"
STRIP = ROOT / "frontend/src/components/erp/marketing/MarketingCycleStrip.jsx"

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except json.JSONDecodeError:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def login(email, pwd):
    st, r = call("POST", "/api/auth/login", None, {"email": email, "password": pwd})
    return r.get("token") if st == 200 else None


def toko_nav(text: str) -> str:
    i = text.index("  toko: {")
    j = text.index("  collaboration: {", i)
    return text[i:j]


def part_static():
    print(f"\n{B}[1] PINTU & SUMBER ANGKA{X}")
    nav = NAV.read_text()
    reg = REG.read_text()
    toko = toko_nav(nav)
    if "id: 'toko-dashboard'" in toko and "'toko-dashboard'" in reg:
        ok("D1", "pintu Dashboard Marketing ada di sidebar Portal Marketing",
           "sebelumnya 0 pintu di seluruh nav walau ia modul bawaan portal")
    else:
        bad("D1", "pintu dashboard masih tidak ada di sidebar Marketing")

    dash = DASH.read_text()
    strip = STRIP.read_text() if STRIP.exists() else ""
    if "MarketingCycleStrip" in dash and "marketing/cycle/overview" in strip:
        ok("D2", "angka resmi bulanan diambil dari SSOT siklus marketing",
           "target · omzet · anggaran · ROAS/ROI · papan perhatian")
    else:
        bad("D2", "dashboard belum memakai SSOT siklus (`/marketing/cycle/overview`)")

    if strip and ".reduce(" not in strip:
        ok("D3", "layar tidak menjumlah ulang angka siklus (semua dari `totals` backend)")
    else:
        bad("D3", "ada penjumlahan di browser — layar & ekspor bisa berbeda angka",
            "aturan F5: peringkat & total dihitung backend")

    if re.search(r"date_from: `\$\{d\.getFullYear\(\)\}", dash):
        ok("D4", "bawaan rentang dashboard = bulan berjalan (sebanding dengan target)")
    else:
        bad("D4", "bawaan rentang bukan bulan berjalan ⇒ omzet tak bisa dibanding target")


def part_runtime():
    print(f"\n{B}[2] ENDPOINT & ANGKA{X}")
    tok = login("admin@garment.com", "Admin@123")
    if not tok:
        bad("D5", "login admin gagal — invarian runtime tidak bisa diuji")
        return
    today = date.today()
    period = today.strftime("%Y-%m")
    first = today.replace(day=1).isoformat()

    st_acc, accounts = call("GET", "/api/marketing/accounts?status=active", tok)
    acc_id = (accounts or [{}])[0].get("id") if isinstance(accounts, list) and accounts else None
    checks = [
        ("/api/marketing/dashboard/overview?date_from=%s&date_to=%s" % (first, today.isoformat()), "ringkasan rentang"),
        ("/api/marketing/accounts?status=active", "daftar toko"),
        (f"/api/marketing/cycle/overview?period={period}", "siklus bulanan (SSOT)"),
    ]
    if acc_id:
        checks.append((f"/api/marketing/accounts/{acc_id}/sales?date_from={first}"
                       f"&date_to={today.isoformat()}", "tren penjualan per toko"))
    dead = []
    for path, label in checks:
        st, _ = call("GET", path, tok)
        if st != 200:
            dead.append(f"{label} → HTTP {st} ({path})")
    if dead:
        bad("D5", "endpoint yang dipanggil layar dashboard TIDAK hidup", "; ".join(dead))
    else:
        ok("D5", f"{len(checks)} endpoint layar dashboard hidup semua",
           "termasuk SSOT siklus — pintu menu tanpa data hanyalah menu kosong")

    st, cyc = call("GET", f"/api/marketing/cycle/overview?period={period}", tok)
    if st != 200:
        bad("D6", f"SSOT siklus gagal (HTTP {st})")
        bad("D8", "tidak bisa diuji tanpa SSOT siklus")
        return
    rows = cyc.get("rows") or []
    t = cyc.get("totals") or {}

    def s(*path):
        tot = 0.0
        for r in rows:
            cur = r
            for p in path:
                cur = (cur or {}).get(p) if isinstance(cur, dict) else 0
            tot += float(cur or 0)
        return round(tot, 2)

    checks6 = {
        "target_revenue": (s("target", "revenue"), float(t.get("target_revenue") or 0)),
        "revenue": (s("actual", "revenue"), float(t.get("revenue") or 0)),
        "total_plan": (s("budget", "total_plan"), float(t.get("total_plan") or 0)),
        "total_spend": (s("budget", "total_spend"), float(t.get("total_spend") or 0)),
    }
    wrong = [f"{k}: baris {a:,.2f} vs total {b:,.2f}"
             for k, (a, b) in checks6.items() if abs(a - b) > 0.05]
    if wrong:
        bad("D6", "total tidak sama dengan jumlah baris toko", "; ".join(wrong))
    else:
        ok("D6", f"total = jumlah {len(rows)} baris toko, dihitung backend",
           " · ".join(f"{k} {b:,.0f}" for k, (a, b) in checks6.items()))

    cov = float(t.get("hpp_coverage_pct") or 0)
    reliable = bool(t.get("roi_reliable"))
    if cov < 80 and reliable:
        bad("D8", f"ROI diklaim sahih padahal cakupan HPP hanya {cov:.0f}%",
            "ROI −100% karena HPP belum tertaut pernah dibaca sebagai kerugian nyata")
    else:
        ok("D8", "ROI hanya diklaim sahih bila cakupan HPP ≥ 80%",
           f"cakupan HPP {cov:.0f}% · roi_reliable={reliable} · ROAS {t.get('roas')}×")

    # D7 — lingkup toko (F6) tetap ditegakkan sesudah layar diubah.
    tok_staff = login("staffmkt@dewiaditya.id", "Dewi@123")
    if not tok_staff:
        bad("D7", "akun staf marketing tanpa toko tidak bisa login — lingkup tak teruji")
        return
    st_a, admin_ov = call("GET", "/api/marketing/dashboard/overview", tok)
    st_s, staff_ov = call("GET", "/api/marketing/dashboard/overview", tok_staff)
    if st_a != 200 or st_s != 200:
        bad("D7", f"ringkasan gagal (admin {st_a}, staf {st_s})")
        return
    a_rev = float((admin_ov.get("summary") or {}).get("total_revenue") or 0)
    s_rev = float((staff_ov.get("summary") or {}).get("total_revenue") or 0)
    s_acc = int((staff_ov.get("summary") or {}).get("active_accounts") or 0)
    if s_acc == 0 and s_rev == 0 and a_rev > 0:
        ok("D7", "staf tanpa toko tidak melihat omzet toko lain",
           f"admin Rp {a_rev:,.0f} dari {(admin_ov.get('summary') or {}).get('active_accounts')} toko · staf Rp 0 dari 0 toko")
    elif s_rev > 0 and s_acc == 0:
        bad("D7", f"staf tanpa toko melihat omzet Rp {s_rev:,.0f} dari 0 toko")
    else:
        bad("D7", "lingkup toko tidak terbukti",
            f"admin {a_rev:,.0f}/{(admin_ov.get('summary') or {}).get('active_accounts')} toko · "
            f"staf {s_rev:,.0f}/{s_acc} toko")


def main():
    print(f"{C}{B}FASE D — Dashboard Marketing: pintu menu + angka resmi bulanan{X}")
    part_static()
    part_runtime()
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian Dashboard Marketing terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
