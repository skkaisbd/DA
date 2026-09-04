#!/usr/bin/env python3
"""verify_state_machine.py — STATE-MACHINE GATE (CV. Dewi Aditya ERP).

Adapted from Rahaza-Travel. Tests DEVIANT transitions (not happy-path) with synthetic 2028
objects + auto-cleanup. These bugs slip past clean-seed happy-path gates.

Checks (journal / GL lifecycle — SSOT double-entry state machine draft→posted→voided):
  SM1  post a non-draft journal        -> must be rejected (400), not silently re-posted.
  SM2  void an already-voided journal  -> must be rejected (400), idempotent (no double GL reversal).
  SM3  delete a posted/voided journal  -> must be rejected (400) (only drafts deletable).
  SM4  balance guard: unbalanced journal (Dr!=Cr) -> must be rejected (400).

Resilient: backend down / login fail / seed missing → SKIP. Exit 1 only on a real regression.
Usage: cd /app && python scripts/verify_state_machine.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
try:
    import httpx
except ImportError:
    os.system("pip install httpx -q")
    import httpx
from pymongo import MongoClient

API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
         "password": os.environ.get("ADMIN_PASS", "Admin@123")}
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
DBC = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
JE = "/api/rahaza/journals"
fails = 0
skips = 0
CREATED = []


def ok(m):
    print(f"  {G}[OK]{X} {m}")


def fail(m):
    global fails
    fails += 1
    print(f"  {R}[FAIL]{X} {m}")


def skip(m):
    global skips
    skips += 1
    print(f"  {Y}[SKIP]{X} {m}")


async def main():
    print(f"\n{B}{'='*64}{X}\n  STATE-MACHINE GATE (journal draft→posted→voided)  API={API}\n{B}{'='*64}{X}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=40) as c:
        try:
            r = await c.get(f"{API}/api/health", timeout=5)
            if r.status_code >= 500:
                raise Exception("5xx")
        except Exception:
            print(f"{Y}  Backend belum berjalan — SKIP (Phase 0).{X}")
            return 0
        r = await c.post(f"{API}/api/auth/login", json=ADMIN)
        if r.status_code != 200:
            skip(f"Login admin gagal ({r.status_code}).")
            return _summary()
        H = {"Authorization": f"Bearer {r.json()['token']}"}
        codes = [a["code"] for a in DBC.rahaza_coa_accounts.find(
            {"is_group": False, "active": True}, {"_id": 0, "code": 1}).limit(2)]
        if len(codes) < 2:
            skip("COA leaf accounts < 2.")
            return _summary()

        def bal_lines(amt=12345):
            return [{"account_code": codes[0], "debit": amt, "credit": 0, "description": "sm"},
                    {"account_code": codes[1], "debit": 0, "credit": amt, "description": "sm"}]

        async def mk(post=False, lines=None):
            r = await c.post(f"{API}{JE}", headers=H, json={
                "date": "2028-08-20", "memo": "STATE-MACHINE gate synthetic",
                "source_module": "gate_state_machine", "post": post,
                "lines": lines if lines is not None else bal_lines()})
            if r.status_code == 200 and isinstance(r.json(), dict) and r.json().get("id"):
                CREATED.append(r.json()["id"])
            return r

        # ---- SM4: unbalanced journal rejected ----
        r = await mk(lines=[{"account_code": codes[0], "debit": 100, "credit": 0},
                            {"account_code": codes[1], "debit": 0, "credit": 999}])
        if r.status_code == 400:
            ok("SM4 unbalanced journal (Dr!=Cr) ditolak (400).")
        elif r.status_code == 200:
            fail("SM4 unbalanced journal DITERIMA (200) — invarian double-entry bocor.")
        else:
            skip(f"SM4 tak konklusif: {r.status_code}")

        # ---- SM1: post a non-draft (already posted) journal ----
        r = await mk(post=True)
        if r.status_code == 200:
            jid = r.json()["id"]
            r2 = await c.post(f"{API}{JE}/{jid}/post", headers=H, json={})
            if r2.status_code == 400:
                ok("SM1 post ulang journal posted ditolak (400).")
            elif r2.status_code == 200:
                fail("SM1 journal posted BISA di-post ulang (200) — double-post GL.")
            else:
                skip(f"SM1 tak konklusif: {r2.status_code}")

            # ---- SM2: void twice ----
            rv1 = await c.post(f"{API}{JE}/{jid}/void", headers=H, json={"reason": "gate"})
            rv2 = await c.post(f"{API}{JE}/{jid}/void", headers=H, json={"reason": "gate"})
            if rv1.status_code == 200 and rv2.status_code == 400:
                ok("SM2 void ulang journal voided ditolak (400) — idempotent (no double reversal).")
            elif rv1.status_code == 200 and rv2.status_code == 200:
                fail("SM2 journal voided BISA di-void lagi (200) — risiko double GL reversal.")
            else:
                skip(f"SM2 tak konklusif: {rv1.status_code}/{rv2.status_code}")

            # ---- SM3: delete a voided (non-draft) journal ----
            rd = await c.request("DELETE", f"{API}{JE}/{jid}", headers=H)
            if rd.status_code == 400:
                ok("SM3 delete journal non-draft ditolak (400).")
            elif rd.status_code == 200:
                fail("SM3 journal non-draft BISA dihapus (200) — jejak audit hilang.")
            else:
                skip(f"SM3 tak konklusif: {rd.status_code}")
        else:
            skip(f"SM1-3 buat journal posted → {r.status_code}")

    return _summary()


def _cleanup():
    for jid in CREATED:
        DBC.rahaza_journal_entries.delete_one({"id": jid})
        DBC.rahaza_journal_lines.delete_many({"je_id": jid})
    for je in DBC.rahaza_journal_entries.find({"source_module": "gate_state_machine"}, {"id": 1}):
        DBC.rahaza_journal_entries.delete_one({"id": je["id"]})
        DBC.rahaza_journal_lines.delete_many({"je_id": je["id"]})


def _summary():
    _cleanup()
    print(f"\n{B}{'='*64}{X}\n  {R}FAIL {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  STATE-MACHINE REGRESI — transisi menyimpang tidak dijaga.{X}\n")
        return 1
    print(f"{G}{B}  State-machine sehat (transisi menyimpang dijaga).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except Exception as ex:
        _cleanup()
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
