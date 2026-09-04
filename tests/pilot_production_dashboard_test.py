"""
PILOT backend deep-contract test — production-dashboard (Dashboard Produksi hub).
Covers 26 endpoints across 5 tabs: Overview (WIP/material/CMT/locations/setup),
Performance (OEE + Line Balancing), Quality (Rework), Schedule (APS Gantt + Auto-Schedule),
AI (RCA + history).

Strategy = SAFE for a live DB:
 - Read-only GETs asserted for 200 + shape.
 - Mutating endpoints tested via their GUARDS only (invalid id -> 4xx) or idempotent
   (PUT settings same value back). NO WO reschedule/commit/seed mutation.
 - auto-schedule/preview creates 1 run doc -> cleaned up by id.
 - Optional LLM RCA probe (INFO, not FAIL) -> ai_rca_history rows cleaned by timestamp.
Types tagged: [H]appy [E]dge [N]egative [P]ermission [S]tate.
"""
import requests, os, sys, datetime

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
results = []
created_run_ids = []
test_start_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

def rec(tc, verdict, detail=""):
    results.append((tc, verdict, detail)); print(f"[{tc}] {verdict} | {detail}")
def H(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
def G(p, t): return requests.get(f"{BASE}{p}", headers=H(t), timeout=30)
def P(p, t, b=None): return requests.post(f"{BASE}{p}", headers=H(t), json=(b or {}), timeout=120)
def PUT(p, t, b): return requests.put(f"{BASE}{p}", headers=H(t), json=b, timeout=30)

r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15); r.raise_for_status()
lj = r.json(); admin = lj["token"]; admin_uid = (lj.get("user") or {}).get("id", "")
print("admin login OK, uid=", admin_uid)

today = datetime.date.today().isoformat()
week_ago = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
month_fwd = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()

# ---------- OVERVIEW TAB ----------
r = G("/api/rahaza/wip/summary", admin)
rec("TC-01", "PASS" if r.status_code == 200 and "processes" in r.json() else "FAIL", f"[H] wip/summary {r.status_code}")
r = G("/api/prod/material-summary-by-location", admin)
rec("TC-02", "PASS" if r.status_code == 200 else "FAIL", f"[H] material-summary-by-location {r.status_code}")
r = G("/api/prod/cmt-receipts/summary", admin)
rec("TC-03", "PASS" if r.status_code == 200 else "FAIL", f"[H] cmt-receipts/summary {r.status_code}")
r = G("/api/rahaza/locations", admin)
rec("TC-04", "PASS" if r.status_code == 200 and isinstance(r.json(), list) else "FAIL", f"[H] locations {r.status_code} n={len(r.json()) if r.status_code==200 else '-'}")
r = G("/api/rahaza/setup/status", admin)
sj = r.json() if r.status_code == 200 else {}
rec("TC-05", "PASS" if r.status_code == 200 and "steps" in sj and "needs_wizard" in sj else "FAIL", f"[H] setup/status {r.status_code} needs_wizard={sj.get('needs_wizard')}")

# ---------- PERFORMANCE TAB (OEE + Line Balance) ----------
r = G("/api/rahaza/lines", admin)
lines = r.json() if r.status_code == 200 else []
line_id = lines[0]["id"] if lines else None
rec("TC-06", "PASS" if r.status_code == 200 and isinstance(lines, list) else "FAIL", f"[H] lines {r.status_code} n={len(lines)}")
r = G("/api/rahaza/shifts", admin)
rec("TC-07", "PASS" if r.status_code == 200 and isinstance(r.json(), list) else "FAIL", f"[H] shifts {r.status_code}")
r = G(f"/api/rahaza/oee/summary?date={today}", admin)
rec("TC-08", "PASS" if r.status_code == 200 and ("kpis" in r.json()) else "FAIL", f"[H] oee/summary {r.status_code}")
r = G(f"/api/rahaza/oee/daily?from={week_ago}&to={today}", admin)
rec("TC-09", "PASS" if r.status_code == 200 and ("rows" in r.json()) else "FAIL", f"[H] oee/daily {r.status_code}")
if line_id:
    r = G(f"/api/rahaza/oee/line/{line_id}?date={today}", admin)
    rec("TC-10", "PASS" if r.status_code == 200 else "FAIL", f"[H] oee/line/{{id}} {r.status_code}")
else:
    rec("TC-10", "INFO", "[H] oee/line skipped (no line master)")
r = G(f"/api/rahaza/supervisor/line-balance?assign_date={today}", admin)
rec("TC-11", "PASS" if r.status_code == 200 and "summary" in r.json() else "FAIL", f"[H] supervisor/line-balance {r.status_code}")
r = G(f"/api/rahaza/oee/daily?from={week_ago}&to={today}&line_id={line_id or 'x'}", admin)
rec("TC-12", "PASS" if r.status_code == 200 else "FAIL", f"[E] oee/daily line_id filter {r.status_code}")

# ---------- SCHEDULE TAB (APS Gantt) ----------
r = G(f"/api/rahaza/aps/gantt?from={week_ago}&to={month_fwd}", admin)
gj = r.json() if r.status_code == 200 else {}
bars = gj.get("bars", [])
wo_id = bars[0]["wo_id"] if bars else None
ok_g = r.status_code == 200 and all(k in gj for k in ("days", "lines", "bars", "kpis"))
rec("TC-13", "PASS" if ok_g else "FAIL", f"[H] aps/gantt {r.status_code} days={len(gj.get('days',[]))} lines={len(gj.get('lines',[]))} bars={len(bars)}")
r = G(f"/api/rahaza/aps/gantt?from={week_ago}&to={month_fwd}&status=released", admin)
rec("TC-14", "PASS" if r.status_code == 200 else "FAIL", f"[E] aps/gantt status filter {r.status_code}")
if wo_id:
    r = G(f"/api/rahaza/aps/wo/{wo_id}", admin)
    rec("TC-15", "PASS" if r.status_code == 200 and "work_order" in r.json() else "FAIL", f"[H] aps/wo/{{id}} {r.status_code}")
else:
    rec("TC-15", "INFO", "[H] aps/wo detail skipped (no WO bars in range)")
r = G(f"/api/rahaza/aps/auto-schedule/runs?limit=10", admin)
rec("TC-16", "PASS" if r.status_code == 200 and isinstance(r.json(), list) else "FAIL", f"[H] auto-schedule/runs {r.status_code}")

# ---------- QUALITY TAB (Rework) ----------
r = G(f"/api/rahaza/rework/summary?from={week_ago}&to={today}", admin)
rec("TC-17", "PASS" if r.status_code == 200 and "kpis" in r.json() else "FAIL", f"[H] rework/summary {r.status_code}")
r = G("/api/rahaza/rework/open", admin)
oj = r.json() if r.status_code == 200 else {}
rec("TC-18", "PASS" if r.status_code == 200 and ("items" in oj) and ("total_open" in oj) else "FAIL", f"[H] rework/open {r.status_code} total_open={oj.get('total_open')}")
r = G("/api/rahaza/rework/settings", admin)
setj = r.json() if r.status_code == 200 else {}
cur_sla = setj.get("sla_minutes", 120)
rec("TC-19", "PASS" if r.status_code == 200 and "sla_minutes" in setj else "FAIL", f"[H] rework/settings {r.status_code} sla={cur_sla}")

# ---------- NEXT ACTIONS + AI history ----------
r = G("/api/rahaza/next-actions?portal=production&limit=12", admin)
rec("TC-20", "PASS" if r.status_code == 200 and "actions" in r.json() else "FAIL", f"[H] next-actions {r.status_code} n={len(r.json().get('actions',[])) if r.status_code==200 else '-'}")
r = G("/api/analytics/ai/history?limit=10", admin)
rec("TC-21", "PASS" if r.status_code == 200 and isinstance(r.json(), list) else "FAIL", f"[H] analytics/ai/history {r.status_code}")

# ---------- EDGE / STATE: idempotent settings PUT (same value) ----------
r = PUT("/api/rahaza/rework/settings", admin, {"sla_minutes": int(cur_sla)})
rec("TC-22", "PASS" if r.status_code == 200 and r.json().get("sla_minutes") == int(cur_sla) else "FAIL", f"[S] rework/settings PUT same value {r.status_code}")

# ---------- NEGATIVE (guards, no mutation) ----------
r = G("/api/rahaza/aps/wo/nonexistent-uuid", admin)
rec("TC-23", "PASS" if r.status_code == 404 else "FAIL", f"[N] aps/wo nonexistent -> {r.status_code} (exp 404)")
r = P("/api/rahaza/aps/auto-schedule/commit", admin, {"run_id": "nonexistent-run"})
rec("TC-24", "PASS" if r.status_code in (400, 404) else "FAIL", f"[N] commit invalid run_id -> {r.status_code} (exp 404)")
r = P("/api/rahaza/aps/auto-schedule/rollback", admin, {"run_id": "nonexistent-run"})
rec("TC-25", "PASS" if r.status_code in (400, 404) else "FAIL", f"[N] rollback invalid run_id -> {r.status_code} (exp 404)")
r = P("/api/rahaza/rework/bundle/nonexistent-bundle/close-manual", admin, {"reason": "test", "writeoff_qty": 0})
rec("TC-26", "PASS" if r.status_code == 404 else "FAIL", f"[N] close-manual nonexistent bundle -> {r.status_code} (exp 404)")
r = PUT("/api/rahaza/rework/settings", admin, {"sla_minutes": 99999})
rec("TC-27", "PASS" if r.status_code == 400 else "FAIL", f"[N] settings PUT out-of-range -> {r.status_code} (exp 400)")

# ---------- PERMISSION (no token -> 401/403) ----------
def NT(method, p, body=None):
    if method == "GET": return requests.get(f"{BASE}{p}", timeout=15)
    return requests.post(f"{BASE}{p}", json=(body or {}), timeout=15)
r = NT("GET", "/api/rahaza/wip/summary")
rec("TC-28", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] wip/summary no token -> {r.status_code}")
r = NT("GET", f"/api/rahaza/aps/gantt?from={week_ago}&to={today}")
rec("TC-29", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] aps/gantt no token -> {r.status_code}")
r = NT("POST", "/api/rahaza/setup/seed-sample")
rec("TC-30", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] setup/seed-sample no token -> {r.status_code}")
r = NT("POST", "/api/rahaza/aps/auto-schedule/commit", {"run_id": "x"})
rec("TC-31", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] auto-schedule/commit no token -> {r.status_code}")
r = NT("POST", "/api/analytics/ai/production/rca", {"days": 7})
rec("TC-32", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] analytics production/rca no token -> {r.status_code}")
r = NT("POST", "/api/rahaza/rework/bundle/x/close-manual", {"reason": "x"})
rec("TC-33", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] rework close-manual no token -> {r.status_code}")

# ---------- STATE: auto-schedule PREVIEW (needs active lines; else valid 400 guard) ----------
r = P("/api/rahaza/aps/auto-schedule/preview", admin, {"from": today, "to": month_fwd, "include_in_production": False})
if len(lines) > 0:
    if r.status_code == 200:
        j = r.json(); rid = j.get("id")
        if rid: created_run_ids.append(rid)
        ok_prev = ("proposal" in j) and (j.get("status") == "preview")
        rec("TC-34", "PASS" if ok_prev else "FAIL", f"[S] auto-schedule/preview 200 status={j.get('status')} run={str(rid)[:8]}")
    else:
        rec("TC-34", "FAIL", f"[S] auto-schedule/preview (lines exist) -> {r.status_code} {r.text[:80]}")
else:
    # fresh DB with no active lines -> planner guard must return 400
    ok_guard = r.status_code == 400 and "line aktif" in r.text
    rec("TC-34", "PASS" if ok_guard else "FAIL", f"[N] preview guard (no active line) -> {r.status_code} {r.text[:90]}")

# ---------- STATE: production RCA guard (needs >=5 WIP events; else valid 400) ----------
r = P("/api/analytics/ai/production/rca", admin, {"days": 7})
if r.status_code == 200 and isinstance(r.json(), dict) and "analysis" in r.json():
    rec("TC-35", "PASS", "[H] production/rca LLM OK 200 (Claude analysis present)")
elif r.status_code == 400 and ("belum cukup" in r.text or "min 5" in r.text):
    rec("TC-35", "PASS", f"[N] production/rca data-guard 400 (insufficient events) {r.text[:80]}")
else:
    rec("TC-35", "INFO", f"[H] production/rca returned {r.status_code} (non-blocking) {r.text[:80]}")

# ---------- CLEANUP ----------
print("\n--- CLEANUP ---")
import asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
async def cleanup():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ.get("DB_NAME", "test_database")]
    c_run = 0
    if created_run_ids:
        res = await db.rahaza_aps_schedule_runs.delete_many({"id": {"$in": created_run_ids}})
        c_run = res.deleted_count
    # also remove any 'preview' runs created during this test window (safety net)
    res2 = await db.rahaza_aps_schedule_runs.delete_many({"status": "preview", "created_at": {"$gte": test_start_iso}})
    # remove RCA history rows created during test window
    res3 = await db.ai_rca_history.delete_many({"created_at": {"$gte": test_start_iso}})
    print(f"cleaned aps_runs(byid)={c_run} aps_runs(window)={res2.deleted_count} rca_history={res3.deleted_count}")
    cli.close()
asyncio.get_event_loop().run_until_complete(cleanup())

passed = sum(1 for _, v, _ in results if v == "PASS")
info = [t for t in results if t[1] == "INFO"]
failed = [t for t in results if t[1] == "FAIL"]
print(f"\n===== SUMMARY: {passed} PASS, {len(info)} INFO, {len(failed)} FAIL of {len(results)} =====")
for t in failed: print("  FAIL:", t)
for t in info: print("  INFO:", t)
sys.exit(1 if failed else 0)
