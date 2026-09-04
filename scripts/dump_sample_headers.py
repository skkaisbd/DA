import sys, os, json
sys.path.insert(0, "/app/backend")
from core.marketing_import_schema import get_source_type, SOURCE_TYPES
from core import marketing_import_engine as eng

DIR = "/app/samples/marketplace_2026"
target = sys.argv[1]
st = get_source_type(sys.argv[2]) if len(sys.argv) > 2 else get_source_type("orders")
raw = open(os.path.join(DIR, target), "rb").read()
headers, rows = eng.parse_table(raw, target, st)
print(f"HEADERS ({len(headers)}):")
for h in headers:
    print("  -", repr(h))
print("\nROW SAMPLES:")
for r in rows[:3]:
    print(json.dumps({k: str(v)[:40] for k, v in r.items()}, ensure_ascii=False, indent=0)[:2500])
    print("---")
