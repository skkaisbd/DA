"""Portal Maklon RBAC audit probes (iteration 104). READ-ONLY.

Runs curl-equivalent GETs with three tokens and reports status + summary of leakage.
"""
import json, os, sys, requests

BACKEND = "http://localhost:8001"
ADMIN = open("/tmp/ta.tok").read().strip()
KLIEN = open("/tmp/tk.tok").read().strip()
CMT = open("/tmp/tc.tok").read().strip()

# endpoints to probe with (label, path, tokens_to_use)
PROBES = [
    ("maklon-pos", "/api/dewi/maklon/pos"),
    ("maklon-invoices", "/api/dewi/maklon/invoices"),
    ("maklon-clients", "/api/dewi/maklon/clients"),
    ("maklon-summary", "/api/dewi/maklon/summary"),
    ("prod-cmt-receipts", "/api/prod/cmt-receipts"),
    ("maklon-po-360-other", "/api/dewi/maklon/pos/po-mk-demo-3/360"),
    ("cmt-billing-scope-maklon", "/api/production/cmt-billing?scope=maklon"),
    ("maklon-payments", "/api/dewi/maklon/payments"),
    ("maklon-aging", "/api/dewi/maklon/reports/aging"),
]

results = {}

def summarize_body(body, label):
    """Return short description of what's in the body (po_numbers/client_names/counts)."""
    try:
        data = json.loads(body)
    except Exception:
        return {"raw": body[:200]}
    out = {}
    if isinstance(data, list):
        out["count"] = len(data)
        pns = list({str(d.get("po_number") or d.get("po_no") or d.get("number") or "") for d in data if isinstance(d, dict)})[:8]
        cns = list({str(d.get("client_name") or d.get("buyer_name") or d.get("customer_name") or "") for d in data if isinstance(d, dict)})[:8]
        out["po_numbers"] = [p for p in pns if p]
        out["client_names"] = [c for c in cns if c]
    elif isinstance(data, dict):
        # detect list inside
        for k, v in data.items():
            if isinstance(v, list):
                out[f"{k}_count"] = len(v)
                if v and isinstance(v[0], dict):
                    pns = list({str(d.get("po_number") or d.get("po_no") or "") for d in v})[:6]
                    cns = list({str(d.get("client_name") or d.get("buyer_name") or "") for d in v})[:6]
                    if any(pns): out[f"{k}_po_numbers"] = [p for p in pns if p]
                    if any(cns): out[f"{k}_client_names"] = [c for c in cns if c]
        if "detail" in data: out["detail"] = data["detail"]
        if "po_number" in data: out["po_number"] = data.get("po_number")
        if "client_name" in data: out["client_name"] = data.get("client_name")
    return out

def probe(tokname, tok, label, path):
    r = requests.get(BACKEND + path, headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    body = r.text
    entry = {"status": r.status_code, "summary": summarize_body(body, label)}
    results.setdefault(tokname, {})[label] = entry
    print(f"[{tokname}] {r.status_code} {path} -> {json.dumps(entry['summary'])[:220]}")

# Run
for name, tok in [("admin", ADMIN), ("klien", KLIEN), ("cmt", CMT)]:
    print(f"\n=== {name} ===")
    for label, path in PROBES:
        try:
            probe(name, tok, label, path)
        except Exception as e:
            print(f"[{name}] ERR {label}: {e}")

with open("/tmp/rbac_probe_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nSaved: /tmp/rbac_probe_results.json")
