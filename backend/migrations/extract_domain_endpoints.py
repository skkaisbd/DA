"""Extract GET endpoints (prefix+path) from domain route files for empirical testing."""
import os, re

BACKEND = "/app/backend/routes"

DOMAINS = {
 "marketing": ("market","kol","livehost","live_","toko","creator","product_launch"),
 "rnd": ("rnd","style","sample","_bom","pattern","hpp","costing"),
 "wms": ("wms","warehouse","opname","fabric","putaway","picklist","receiving","delivery","dispatch","fg_label","wh_"),
}

RE_PREFIX = re.compile(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']')
RE_GET = re.compile(r'@router\.get\(\s*["\']([^"\']*)["\']')

def domain_of(fn):
    f = fn.lower()
    for dom, keys in DOMAINS.items():
        if any(k in f for k in keys):
            return dom
    return None

out = {"marketing": [], "rnd": [], "wms": []}
for fn in sorted(os.listdir(BACKEND)):
    if not fn.endswith(".py"): continue
    dom = domain_of(fn)
    if not dom: continue
    if any(h in fn.lower() for h in ("seed","backup","_archive")): continue
    txt = open(os.path.join(BACKEND, fn), encoding="utf-8").read()
    prefixes = RE_PREFIX.findall(txt)
    prefix = prefixes[0] if prefixes else ""
    for path in RE_GET.findall(txt):
        full = prefix + path
        # only simple GETs (no path params) for auto-testing
        if "{" in full: continue
        out[dom].append((fn, full))

for dom, items in out.items():
    print(f"\n===== {dom.upper()} GET endpoints (no path param): {len(items)} =====")
    seen=set()
    for fn, full in items:
        if full in seen: continue
        seen.add(full)
        print(f"  {full:60s}  <- {os.path.splitext(fn)[0]}")
