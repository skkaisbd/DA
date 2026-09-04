"""Audit runtime Portal Produksi: modul → komponen → panggilan API → status HTTP nyata."""
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path

FE = Path('/app/frontend/src')
REG = (FE / 'components/erp/moduleRegistry.js').read_text()
NAV = (FE / 'components/erp/portal-shell/portalNav.js').read_text()
API = [l.split('=', 1)[1].strip() for l in open('/app/frontend/.env') if l.startswith('REACT_APP_BACKEND_URL')][0]

prod_block = NAV[NAV.index('  production: {'):]
prod_block = prod_block[:prod_block.index('\n  },\n')]
ids = re.findall(r"id: '([^']+)'", prod_block)

def comp_for(mid):
    m = re.search(rf"'{re.escape(mid)}':\s*([A-Za-z0-9_]+)", REG)
    return m.group(1) if m else None

def file_for(comp):
    m = re.search(rf"const {comp}\s*=\s*lazy\(\(\) => import\('([^']+)'\)\)", REG)
    if not m:
        m = re.search(rf"import {comp} from '([^']+)'", REG)
    if not m:
        return None
    p = (FE / 'components/erp' / m.group(1)).resolve()
    for cand in [p, Path(str(p) + '.jsx'), Path(str(p) + '.js'), p / 'index.jsx', p / 'index.js']:
        if cand.is_file():
            return cand
    return None

def deps(path, seen):
    if path in seen or path is None:
        return
    seen.add(path)
    txt = path.read_text(errors='ignore')
    for imp in re.findall(r"from '(\.[^']+)'", txt):
        base = (path.parent / imp).resolve()
        for cand in [base, Path(str(base) + '.jsx'), Path(str(base) + '.js'), base / 'index.jsx', base / 'index.js']:
            if cand.is_file():
                deps(cand, seen); break

def calls(files):
    out = set()
    for f in files:
        t = f.read_text(errors='ignore')
        for m in re.findall(r"[`'\"](/api/[A-Za-z0-9_\-/{}$.?=&]+)", t):
            out.add(m)
        for m in re.findall(r"api(?:Get|Post|Put|Delete|Patch)\(\s*[`'\"](/[A-Za-z0-9_\-/{}$.?=&]+)", t):
            out.add('/api' + m if not m.startswith('/api') else m)
    return out

login = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{API}/api/auth/login", data=json.dumps({"email": "admin@garment.com", "password": "Admin@123"}).encode(),
    headers={"Content-Type": "application/json", "User-Agent": "curl/8"})).read())
TOK = login['token']

def get(path):
    req = urllib.request.Request(f"{API}{path}", headers={"Authorization": f"Bearer {TOK}", "User-Agent": "curl/8"})
    try:
        r = urllib.request.urlopen(req, timeout=60); return r.status, r.read()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200]
    except Exception as e:
        return 0, str(e).encode()

report = {}
for mid in ids:
    comp = comp_for(mid)
    f = file_for(comp) if comp else None
    seen = set(); deps(f, seen)
    cs = sorted(c for c in calls(seen) if '$' not in c and '{' not in c and '?' not in c)
    entry = {'component': comp, 'file': str(f).replace('/app/frontend/src/', '') if f else None, 'calls': {}}
    for c in cs:
        code, body = get(c.rstrip('/'))
        if code in (404, 405, 500, 0):
            entry['calls'][c] = {'status': code, 'body': body.decode(errors='ignore')[:120]}
    report[mid] = entry
    bad = {k: v for k, v in entry['calls'].items()}
    print(f"{mid:32} {comp or '??':34} {'MISSING-FILE' if not f else ''} bad={len(bad)}")
    for k, v in bad.items():
        print(f"    {v['status']} GET {k}  {v['body'][:90]}")
json.dump(report, open('/app/test_reports/prod_audit_runtime.json', 'w'), indent=1)
