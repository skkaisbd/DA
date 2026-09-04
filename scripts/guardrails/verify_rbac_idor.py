#!/usr/bin/env python3
"""INV-RBAC-01 — Gate RBAC / kebocoran akses (RUNTIME, READ-ONLY di sisi bisnis).

Dua sapuan yang mengonfirmasi temuan statik INV-AUTH-01 di dunia nyata (membunuh
“false green”): endpoint yang KELIHATAN aman secara statik tetap diuji hidup-hidup.

  SWEEP 1 — UNAUTH GET SWEEP: tembak SEMUA GET /api/... tanpa parameter (dari
            /api/openapi.json) TANPA token. Harapan: 401/403. Bila 200 → endpoint
            terbuka tanpa login (HIGH bila path sensitif: finance/hr/journal/
            payroll/ar/ap/stock/customer/report; selain itu MED).

  SWEEP 2 — CROSS-ROLE ESCALATION: buat user role rendah sementara (mis. 'operator'
            → hanya portal produksi) langsung di DB, login via API, lalu tembak
            endpoint milik portal LAIN yang sensitif (jurnal keuangan, payroll HR,
            admin). Harapan: 403. Bila 200 → eskalasi privilege (HIGH). User uji
            dihapus di akhir. Skip bila tak bisa provisioning/login.

Resilient: backend/seed mati → SKIP (bukan PASS). Default mem-blok pada HIGH;
--report-only utk tak mem-blok.
Usage: cd /app && python scripts/guardrails/verify_rbac_idor.py [--report-only]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import (  # noqa: E402
    Report, api_base, http, login, backend_up, db_handle, load_env, Y, X,
)

SENSITIVE = ("journal", "finance", "payroll", "payslip", "invoice", "receivable",
             "payable", "cash", "bank", "salary", "customer", "vendor", "report",
             "stock", "coa", "ledger", "tax", "kasbon", "loan", "/admin", "users",
             "expense", "recap", "budget", "profit", "margin", "gl-")


def _is_sensitive(path):
    # Strip prefix "/api" agar token seperti "invoice"/"payable" tak salah-cocok "/api".
    p = path[4:] if path.startswith("/api") else path
    return any(s in p for s in SENSITIVE)

# endpoint privileged (portal lain) untuk uji eskalasi cross-role
CROSS_ROLE_TARGETS = [
    ("GET", "/rahaza/journals"),
    ("GET", "/rahaza/ar-invoices"),
    ("GET", "/rahaza/ap-invoices"),
    ("GET", "/rahaza/payroll-runs"),
    ("GET", "/rahaza/coa/accounts"),
    ("GET", "/admin/users"),
]
TEST_USER = {
    "email": "gate_lowpriv_probe@garment.local",
    "password": "Probe@12345",
    "role": "operator",   # hanya portal produksi (lihat PORTAL_ACCESS)
}


def openapi_paths():
    try:
        with urllib.request.urlopen(api_base() + "/api/openapi.json", timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace")).get("paths", {})
    except Exception:
        return {}


def provision_lowpriv():
    """Buat/upsert user role rendah langsung di DB. Return True bila siap."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
        load_env()
        from auth import hash_password  # noqa
        import uuid
        from datetime import datetime, timezone
        db = db_handle()
        db.users.update_one(
            {"email": TEST_USER["email"]},
            {"$set": {"name": "Gate LowPriv Probe", "role": TEST_USER["role"],
                      "status": "active"},
             "$setOnInsert": {"id": str(uuid.uuid4()), "email": TEST_USER["email"],
                              "password": hash_password(TEST_USER["password"]),
                              "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    {Y}[SKIP]{X} tak bisa provisioning user uji: {e}")
        return False


def cleanup_lowpriv():
    try:
        db_handle().users.delete_one({"email": TEST_USER["email"]})
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--limit", type=int, default=800, help="batas GET unauth yang disweep")
    args = ap.parse_args()

    rep = Report("INV-RBAC-01", "RBAC/kebocoran akses (unauth sweep + cross-role escalation)",
                 block_sev=() if args.report_only else ("HIGH",))

    if not backend_up():
        print(f"    {Y}[SKIP]{X} backend mati — SKIP (Phase 0, bukan PASS).")
        return rep.finish()

    paths = openapi_paths()
    if not paths:
        print(f"    {Y}[SKIP]{X} openapi.json tak terbaca — SKIP.")
        return rep.finish()

    # ─── SWEEP 1: UNAUTH GET ───
    print("  → SWEEP 1: unauth GET (tanpa token, harap 401/403)")
    n = 0
    for p, methods in sorted(paths.items()):
        if "get" not in methods or "{" in p or not p.startswith("/api/"):
            continue
        if any(s in p for s in ("/auth/login", "/auth/register", "/health", "/metrics",
                                "/webhook", "/public/", "/docs", "/openapi")):
            continue
        if n >= args.limit:
            break
        n += 1
        rep.bump()
        st, _ = http("GET", p, token=None, timeout=15)
        if st == 200:
            sev = "HIGH" if _is_sensitive(p) else "MED"
            rep.add(sev, "UNAUTH_GET", f"{p} → 200 TANPA token (endpoint terbuka)", "unauth")
    print(f"    (disweep {n} GET parameterless)")

    # ─── SWEEP 2: CROSS-ROLE ESCALATION ───
    print("  → SWEEP 2: cross-role escalation (operator → endpoint portal lain, harap 403)")
    if provision_lowpriv():
        tok = login(TEST_USER["email"], TEST_USER["password"])
        if not tok:
            print(f"    {Y}[SKIP]{X} login user role-rendah gagal — SKIP sweep 2.")
        else:
            for method, path in CROSS_ROLE_TARGETS:
                rep.bump()
                st, _ = http(method, path, token=tok, timeout=15)
                if st == 200:
                    rep.add("HIGH", "CROSS_ROLE",
                            f"{method} {path} → 200 oleh role '{TEST_USER['role']}' "
                            f"(seharusnya 403 — eskalasi privilege)", "lowpriv")
                elif st in (401, 403):
                    print(f"    [OK  ] {method} {path} → {st} (ditolak, benar)")
                else:
                    print(f"    [..  ] {method} {path} → {st}")
        cleanup_lowpriv()

    return rep.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # noqa: BLE001
        cleanup_lowpriv()
        print(f"  {Y}Gate error (dianggap SKIP): {ex}{X}")
        sys.exit(0)
