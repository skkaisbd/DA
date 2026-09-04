#!/usr/bin/env python3
"""health_check.py — Endpoint kritis reachable (RUNTIME).

Memastikan tulang punggung sistem hidup sebelum klaim "aman":
  - GET /api/health → 2xx
  - POST /api/auth/login (admin) → 200 + token
  - beberapa GET modul inti → status < 500 (tak crash)

BLOCKING: exit != 0 bila /health gagal, login gagal, atau ada endpoint 5xx.
Usage: cd /app && python scripts/health_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import Report, http, login, G, R, X  # noqa: E402

# GET endpoints inti (path setelah /api). Toleran: hanya 5xx yang dianggap gagal.
CRITICAL_GETS = [
    "/health", "/auth/me", "/dashboard/summary", "/rahaza/journals",
    "/rahaza/coa/accounts", "/warehouse/items", "/hr/employees",
]


def main() -> int:
    rep = Report("HEALTH-01", "Endpoint kritis reachable", block_sev=("CRIT", "HIGH"))
    st, _ = http("GET", "/health", timeout=8)
    rep.bump()
    if not (200 <= st < 300):
        rep.add("CRIT", "HEALTH-DOWN", f"GET /api/health = {st} (backend tak sehat)")
        return rep.finish()
    tok = login()
    rep.bump()
    if not tok:
        rep.add("HIGH", "HEALTH-AUTH", "login admin gagal — runtime tak dapat divalidasi")
        return rep.finish()
    for path in CRITICAL_GETS:
        st, _ = http("GET", path, token=tok, timeout=12)
        rep.bump()
        if st >= 500:
            rep.add("HIGH", "HEALTH-5XX", f"GET {path} = {st} (crash server)")
        elif st == -1:
            rep.add("HIGH", "HEALTH-CONN", f"GET {path}: transport error")
        else:
            print(f"    {G}ok{X} GET {path} = {st}")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
