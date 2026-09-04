"""Empirical endpoint tester for Marketing/RnD/WMS domains (Part 3 forensic)."""
import json, urllib.request, urllib.error

URL = "http://localhost:8001"
TOKEN = open("/tmp/admin_token.txt").read().strip()
sel = json.load(open("/tmp/domain_gets.json"))

def call(path):
    req = urllib.request.Request(URL + path, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")[:120]
    except Exception as e:
        return "ERR", str(e)[:120]
    return code, body

def shape(body):
    """Describe response: list length / items count / zero-metric hint."""
    try:
        d = json.loads(body)
    except Exception:
        return "non-json"
    if isinstance(d, list):
        return f"list[{len(d)}]"
    if isinstance(d, dict):
        # common list wrappers
        for k in ("items","data","rows","results","sessions","creators","accounts","orders","hosts"):
            if k in d and isinstance(d[k], list):
                return f"{k}[{len(d[k])}]"
        # summary/overview dicts: check if all numeric values are zero
        nums = [v for v in d.values() if isinstance(v,(int,float))]
        if nums and all((n==0) for n in nums):
            return f"dict ALL-ZERO ({len(d)} keys)"
        # nested numeric
        return "dict{" + ",".join(list(d.keys())[:6]) + "}"
    return type(d).__name__

results = {}
for dom, paths in sel.items():
    results[dom] = []
    for p in paths:
        code, body = call(p)
        s = shape(body) if code == 200 else (body if isinstance(body,str) else "")
        results[dom].append({"path": p, "code": code, "shape": s})

json.dump(results, open("/tmp/domain_test_results.json","w"), indent=1)

# Print summary: focus on problems (non-200, empty lists, all-zero)
for dom, rows in results.items():
    problems = [r for r in rows if r["code"]!=200 or "list[0]" in str(r["shape"]) or "[0]" in str(r["shape"]) or "ALL-ZERO" in str(r["shape"])]
    print(f"\n{'='*72}\n{dom.upper()}: {len(rows)} endpoints, {len(problems)} PROBLEM (non-200/empty/all-zero)\n{'='*72}")
    for r in rows:
        mark = "  " if (r["code"]==200 and "[0]" not in str(r["shape"]) and "ALL-ZERO" not in str(r["shape"])) else "!!"
        print(f" {mark} [{str(r['code']):>3}] {r['path']:52s} {str(r['shape'])[:40]}")
