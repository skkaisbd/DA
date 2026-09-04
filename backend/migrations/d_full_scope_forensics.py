"""STEP D — FULL-SCOPE endpoint forensics (ALL domains, read-only).
Tests every GET endpoint (no-param 689 + path-param 269 with generic ID resolution).
Classifies: OK_DATA / OK_EMPTY / 4xx / 500 / TIMEOUT. Outputs /tmp/d_results.json.
Superadmin token from /tmp/admin_token.txt. NO writes performed.
"""
import json, re, time, urllib.request, urllib.error
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import os
from pymongo import MongoClient

URL = "http://localhost:8001"
TOKEN = open("/tmp/admin_token.txt").read().strip()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"].strip('"')]
COLLS = set(db.list_collection_names())

# ---------- domain mapping (for reporting) ----------
DOMAIN_RULES = [
    ("maklon_cmt",    ("maklon", "cmt", "vendor-portal", "vendor_portal", "buyer")),
    ("accessories",   ("/acc/", "accessor",)),
    ("assets",        ("/asset", "/assets", "/da/assets")),
    ("approval",      ("approval", "/inbox", "delegation")),
    ("toko",          ("/toko",)),
    ("hr_talent",     ("recruit", "onboarding", "/lms", "/kpi", "/okr", "career", "skill-gap", "360", "resignation", "/org", "job-board", "training", "study-group", "shift-handover", "shift-scheduler", "hr/shifts", "hr_shifts", "/hris", "leave-balance")),
    ("communication", ("/comm", "channel", "thread", "workspace", "activity", "announcement", "collab", "conversation")),
    ("procurement",   ("procurement", "purchase-request", "/po", "p2p", "/pr/")),
    ("finance_ext",   ("petty", "budget", "accrual", "fixed-asset", "bank-recon", "bank-transfer", "tax", "salary", "loan", "kasbon", "expense", "travel", "per-diem", "posting-profile", "coa", "periods", "cost-center", "journal", "/gl", "/fin")),
    ("production_ext",("downtime", "andon", "/lkp", "aql", "rework", "aps", "line-monitor", "/tv", "sprint22", "backlog", "next-action", "wizard", "bundle", "cutting", "finishing", "sewing", "grn-qc", "variance", "control-tower", "production", "/qc", "oee", "/wip", "sop", "lini")),
    ("marketing_p3",  ("market", "/kol", "livehost", "/live", "creator", "ads", "webhook", "catalog", "campaign", "discount", "complaint", "review", "launch", "content-calendar")),
    ("rnd_p3",        ("/rnd", "tech-pack", "pattern", "variant", "/hpp", "/bom", "style", "sample", "costing")),
    ("wms_p3",        ("/wms", "warehouse", "/wh/", "opname", "fabric", "putaway", "picklist", "receiving", "delivery", "dispatch", "capacity", "rack", "zone", "position", "/stock", "material", "inventory", "reorder", "unit")),
    ("core_p1p2",     ("executive", "dashboard", "payroll", "attendance", "portal-saya", "cashflow", "ar-360", "/ar", "/ap", "invoice", "payment", "employee", "/hr", "leave", "overtime", "payslip", "shift", "notification", "/auth", "user", "role", "audit", "search", "scan", "import", "export", "report", "health", "settings", "config", "master")),
]

def domain_of(p):
    pl = p.lower()
    for dom, keys in DOMAIN_RULES:
        if any(k in pl for k in keys):
            return dom
    return "other"

# ---------- generic id resolver for path-param GETs ----------
MANUAL_KW = {
    "creator": ["marketing_kol_creators"], "kol": ["marketing_kol_creators"],
    "livehost": ["marketing_livehosts", "marketing_livehost_hosts"],
    "live": ["marketing_live_sessions"], "session": ["marketing_live_sessions", "marketing_creator_sessions"],
    "toko": ["dewi_toko_orders"], "style": ["dewi_rnd_styles"], "sample": ["dewi_maklon_samples", "dewi_rnd_samples"],
    "maklon": ["dewi_maklon_pos", "dewi_maklon_samples"], "material": ["rahaza_materials"],
    "employee": ["rahaza_employees"], "karyawan": ["rahaza_employees"],
    "work-order": ["rahaza_work_orders"], "wo": ["rahaza_work_orders"],
    "invoice": ["rahaza_ar_invoices", "rahaza_ap_invoices", "dewi_maklon_invoices"],
    "vendor": ["rahaza_vendors"], "customer": ["rahaza_customers"], "order": ["rahaza_orders", "marketing_orders"],
    "asset": ["da_assets", "dewi_assets"], "machine": ["rahaza_machines"], "line": ["rahaza_production_lines"],
    "model": ["rahaza_models"], "bundle": ["rahaza_bundles"], "payslip": ["rahaza_payslips"],
    "payroll-run": ["rahaza_payroll_runs"], "leave": ["rahaza_leave_requests"], "overtime": ["rahaza_overtime_requests"],
    "shift": ["rahaza_shifts", "hr_shifts"], "expense": ["rahaza_expenses", "rahaza_expense_claims"],
    "claim": ["rahaza_expense_claims"], "travel": ["employee_travel_requests"],
    "kasbon": ["rahaza_kasbon", "dewi_kasbon"], "loan": ["rahaza_employee_loans"],
    "petty": ["rahaza_petty_cash_funds"], "budget": ["rahaza_budgets"],
    "period": ["rahaza_periods"], "account": ["rahaza_cash_accounts", "marketing_platform_accounts"],
    "journal": ["rahaza_journal_entries"], "po": ["rahaza_pos", "dewi_maklon_pos"],
    "grn": ["wh_grn"], "delivery": ["wh_delivery_notes"], "dispatch": ["wh_cmt_dispatches"],
    "roll": ["wh_fabric_rolls"], "rack": ["wh_racks"], "zone": ["wh_zones"], "building": ["wh_buildings"],
    "position": ["wh_positions"], "course": ["dewi_lms_courses"], "quiz": ["dewi_lms_quizzes"],
    "channel": ["comm_channels"], "notification": ["notifications"], "announcement": ["announcements"],
    "sop": ["rahaza_sop_documents", "rahaza_sops"], "campaign": ["marketing_ads_campaigns"],
    "complaint": ["marketing_complaints"], "discount": ["marketing_discounts"],
    "onboarding": ["dewi_onboarding_templates", "dewi_onboarding_checklists"],
    "candidate": ["dewi_candidates"], "job": ["dewi_job_postings", "production_jobs"],
    "kpi": ["dewi_kpi_periods"], "okr": ["dewi_okrs"],
}

def sample_ids(colls, n=2):
    out = []
    for c in colls:
        if c in COLLS:
            for d in db[c].find({}, {"id": 1, "_id": 0}).limit(n):
                if d.get("id"): out.append(str(d["id"]))
    return out

def resolve_ids(path):
    pl = path.lower()
    # 1) manual keyword map
    for kw, colls in MANUAL_KW.items():
        if kw in pl:
            ids = sample_ids(colls)
            if ids: return ids
    # 2) generic: use resource segment right before {param}
    m = re.search(r"/([a-z0-9_-]+)/\{[^}]+\}", pl)
    if m:
        seg = m.group(1).replace("-", "_").rstrip("s")
        cands = [c for c in COLLS if seg in c and db[c].estimated_document_count() > 0]
        # prefer shorter names (more canonical)
        for c in sorted(cands, key=len)[:3]:
            ids = sample_ids([c])
            if ids: return ids
    return []

def call(path, timeout=20):
    req = urllib.request.Request(URL + path, headers={"Authorization": f"Bearer {TOKEN}"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400)
            return r.status, body.decode("utf-8", "replace"), round((time.time()-t0)*1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read(250).decode("utf-8", "replace"), round((time.time()-t0)*1000)
    except Exception as e:
        return "TIMEOUT" if "timed out" in str(e).lower() else "ERR", str(e)[:120], round((time.time()-t0)*1000)

EMPTY_PAT = re.compile(r'^\s*(\[\s*\]|\{\s*\}|null)\s*$')
def is_emptyish(body):
    b = body.strip()
    if EMPTY_PAT.match(b): return True
    # common wrappers: {"data": []} / {"items": []} / {"total":0,...}
    try:
        j = json.loads(b) if len(b) < 400 else None
    except Exception:
        return False
    if isinstance(j, list): return len(j) == 0
    if isinstance(j, dict):
        vals = list(j.values())
        if not vals: return True
        nonmeta = [v for k, v in j.items() if k not in ("status", "ok", "message", "request_id", "page", "limit")]
        if nonmeta and all((v in (0, None, [], {}, "", False)) for v in nonmeta): return True
    return False

d = json.load(open("/tmp/openapi.json"))
paths = d["paths"]
get_noparam = sorted(p for p, m in paths.items() if "get" in m and "{" not in p)
get_param   = sorted(p for p, m in paths.items() if "get" in m and p.count("{") == 1)
get_multi   = sorted(p for p, m in paths.items() if "get" in m and p.count("{") > 1)

print(f"no-param GET: {len(get_noparam)} | single-param GET: {len(get_param)} | multi-param GET: {len(get_multi)} (skipped)")

results = []
t_start = time.time()
for i, p in enumerate(get_noparam):
    code, body, ms = call(p)
    cls = ("500" if code == 500 else
           "TIMEOUT" if code == "TIMEOUT" else
           "ERR" if code == "ERR" else
           f"{code}" if isinstance(code, int) and code >= 400 else
           ("OK_EMPTY" if is_emptyish(body) else "OK_DATA"))
    results.append({"path": p, "kind": "noparam", "domain": domain_of(p), "code": str(code), "cls": cls, "ms": ms, "body": body[:220]})
    if (i+1) % 100 == 0: print(f"  ..noparam {i+1}/{len(get_noparam)} ({round(time.time()-t_start)}s)")

for i, p in enumerate(get_param):
    param = re.search(r"\{([^}]+)\}", p).group(1)
    ids = resolve_ids(p)
    if not ids:
        results.append({"path": p, "kind": "param", "domain": domain_of(p), "code": "NO_ID", "cls": "NO_ID", "ms": 0, "body": ""})
        continue
    best = None
    for cid in ids[:2]:
        real = p.replace("{" + param + "}", cid)
        code, body, ms = call(real)
        cur = {"path": p, "kind": "param", "domain": domain_of(p), "code": str(code), "cls": "", "ms": ms, "body": body[:220], "tried": real}
        if code == 500: best = cur; break
        if code == 200: best = cur; break
        if best is None: best = cur
    c = best["code"]
    best["cls"] = ("500" if c == "500" else "TIMEOUT" if c == "TIMEOUT" else "ERR" if c == "ERR" else
                   c if c.isdigit() and int(c) >= 400 else
                   ("OK_EMPTY" if is_emptyish(best["body"]) else "OK_DATA"))
    results.append(best)
    if (i+1) % 60 == 0: print(f"  ..param {i+1}/{len(get_param)} ({round(time.time()-t_start)}s)")

json.dump(results, open("/tmp/d_results.json", "w"), indent=1)

# ---------- summary ----------
from collections import Counter, defaultdict
by_cls = Counter(r["cls"] for r in results)
print("\n===== GLOBAL SUMMARY =====")
print(dict(by_cls))
print("\n===== 500 CRASHES =====")
for r in results:
    if r["cls"] == "500":
        print(f"  {r['path']}  [{r['domain']}]  {r.get('tried','')}\n     {r['body'][:150]}")
print("\n===== TIMEOUTS =====")
for r in results:
    if r["cls"] == "TIMEOUT": print(f"  {r['path']} [{r['domain']}] {r['ms']}ms")
print("\n===== PER-DOMAIN =====")
dom_stat = defaultdict(Counter)
for r in results: dom_stat[r["domain"]][r["cls"]] += 1
for dom in sorted(dom_stat):
    s = dom_stat[dom]
    print(f"  {dom:16s} total={sum(s.values()):4d}  data={s['OK_DATA']:4d} empty={s['OK_EMPTY']:4d} 500={s['500']:2d} 4xx={sum(v for k,v in s.items() if k.isdigit() and k!='500'):3d} noid={s['NO_ID']:3d} tmo={s['TIMEOUT']}")
print(f"\nTotal tested: {len(results)} | duration {round(time.time()-t_start)}s")
