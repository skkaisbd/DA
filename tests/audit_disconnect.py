"""Systematic 'disconnect' audit across Produksi / Maklon / Vendor portal flows.

For each core collection in the chain, collect the union of stored field names
(sampling several docs), then check whether each field is REFERENCED anywhere in
the frontend source (displayed) and in the backend routes (consumed/returned).

A field that is stored but has ZERO frontend refs AND is not obviously a
relation/internal key is a DISCONNECT candidate (stored-but-never-surfaced) —
the same class of bug as SOP (write-only) and buyer_ref_code.
"""
import os, subprocess
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from pymongo import MongoClient

db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]

# collections grouped by portal flow
FLOWS = {
    'MAKLON (catalog/PO)': [
        'dewi_maklon_buyer_catalog', 'dewi_maklon_pos', 'po_items',
    ],
    'PRODUKSI (jobs)': [
        'production_pos', 'production_jobs', 'production_job_items',
    ],
    'VENDOR (receiving/ship)': [
        'vendor_shipments', 'vendor_shipment_items', 'po_accessories',
    ],
}

# fields we intentionally ignore (internal plumbing / obviously not display fields)
IGNORE = {
    '_id', 'id', 'created_at', 'updated_at', 'created_by', 'updated_by',
    'deleted', 'is_deleted', 'tenant_id', 'org_id', '__v', 'seq', 'v',
}
# suffixes that are relation keys (checked separately — should be *used* not displayed)
REL_SUFFIX = ('_id', '_ids')


def frontend_refs(field):
    try:
        r = subprocess.run(
            ['grep', '-rl', '--include=*.jsx', '--include=*.js', field, '/app/frontend/src'],
            capture_output=True, text=True, timeout=30)
        files = [f for f in r.stdout.strip().split('\n') if f]
        return len(files)
    except Exception:
        return -1


def backend_refs(field):
    try:
        r = subprocess.run(
            ['grep', '-rl', '--include=*.py', field, '/app/backend/routes', '/app/backend/services'],
            capture_output=True, text=True, timeout=30)
        files = [f for f in r.stdout.strip().split('\n') if f]
        return len(files)
    except Exception:
        return -1


def collect_fields(coll, sample=15):
    fields = {}
    n = 0
    for doc in db[coll].find({}).limit(sample):
        n += 1
        for k, val in doc.items():
            if k not in fields:
                fields[k] = val
    return fields, n


print("=" * 90)
print("DISCONNECT AUDIT — stored fields with NO frontend reference (display gap candidates)")
print("=" * 90)

disconnects = []
for flow, colls in FLOWS.items():
    print(f"\n########## FLOW: {flow} ##########")
    for coll in colls:
        cnt = db[coll].count_documents({})
        fields, sampled = collect_fields(coll)
        print(f"\n--- {coll} (docs={cnt}, sampled={sampled}, fields={len(fields)}) ---")
        if cnt == 0:
            print("   (empty — skipped)")
            continue
        for f in sorted(fields):
            if f in IGNORE:
                continue
            fe = frontend_refs(f)
            be = backend_refs(f)
            is_rel = f.endswith(REL_SUFFIX)
            flag = ''
            if fe == 0 and not is_rel:
                flag = '  <<< DISCONNECT? (no frontend ref)'
                disconnects.append((flow, coll, f, be))
            elif fe == 0 and is_rel:
                flag = '  (relation key; used in code, not displayed — OK if backend uses it)'
            print(f"   {f:32s} fe={fe:>2} be={be:>2}{flag}")

print("\n" + "=" * 90)
print(f"DISCONNECT CANDIDATES (no frontend ref, not a relation key): {len(disconnects)}")
print("=" * 90)
for flow, coll, f, be in disconnects:
    print(f"  [{flow}] {coll}.{f}   (backend refs={be})")
