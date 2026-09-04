"""STEP B1 — Test path-param GET endpoints (detail/drill-down) for 3 domains.
Read-only. Resolves REAL ids from DB per route keyword. Flags 500 (crash) vs 404 (graceful) vs 200 (works)."""
import json, re, urllib.request, urllib.error
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import os
from pymongo import MongoClient

URL = "http://localhost:8001"
TOKEN = open("/tmp/admin_token.txt").read().strip()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# keyword in path  ->  collections to pull an id from (first with data wins)
KW_COLL = [
    ("creator",        ["marketing_kol_creators"]),
    ("kol",            ["marketing_kol_creators"]),
    ("livehost",       ["marketing_livehosts", "marketing_livehost_hosts"]),
    ("host",           ["marketing_livehosts", "marketing_livehost_hosts"]),
    ("live",           ["marketing_live_sessions"]),
    ("session",        ["marketing_live_sessions", "marketing_creator_sessions"]),
    ("account",        ["marketing_platform_accounts", "marketing_accounts"]),
    ("complaint",      ["marketing_complaints"]),
    ("discount",       ["marketing_discounts"]),
    ("campaign",       ["marketing_ads_campaigns"]),
    ("catalog",        ["marketing_catalogs"]),
    ("toko",           ["dewi_toko_orders"]),
    ("order",          ["marketing_orders", "dewi_toko_orders"]),
    ("shift",          ["marketing_livehost_shifts"]),
    ("style",          ["dewi_rnd_styles", "rahaza_styles"]),
    ("sample",         ["dewi_rnd_samples", "dewi_maklon_samples"]),
    ("pattern",        ["dewi_rnd_patterns"]),
    ("variant",        ["dewi_rnd_variants"]),
    ("tech-pack",      ["dewi_rnd_tech_packs"]),
    ("bom",            ["dewi_maklon_bom", "rahaza_boms"]),
    ("hpp",            ["dewi_rnd_hpp"]),
    ("maklon",         ["dewi_maklon_samples", "dewi_maklon_orders"]),
    ("fabric-roll",    ["wh_fabric_rolls"]),
    ("delivery",       ["wh_delivery_notes"]),
    ("dispatch",       ["wh_cmt_dispatches"]),
    ("position",       ["wh_positions"]),
    ("rack",           ["wh_racks"]),
    ("building",       ["wh_buildings"]),
    ("zone",           ["wh_zones"]),
    ("opname2",        ["wms_opname2_sessions", "wh_opname_sessions2", "wh_opname2_sessions"]),
    ("opname",         ["wms_opname2_sessions", "wh_opname_sessions2"]),
    ("receiving",      ["wh_grn", "warehouse_receiving"]),
    ("grn",            ["wh_grn"]),
    ("putaway",        ["wh_putaway"]),
    ("return",         ["wh_returns"]),
    ("unit",           ["wh_unit_master"]),
    ("material",       ["rahaza_materials"]),
    ("stock",          ["material_stock_canonical", "rahaza_material_stock"]),
    ("location",       ["warehouse_locations", "wh_positions"]),
]

names = set(db.list_collection_names())
def sample_ids(colls, n=2):
    out = []
    for c in colls:
        if c in names:
            for d in db[c].find({}, {"id": 1, "_id": 0}).limit(n):
                if d.get("id"): out.append(d["id"])
    return out

def ids_for_path(path):
    pl = path.lower()
    for kw, colls in KW_COLL:
        if kw in pl:
            ids = sample_ids(colls)
            if ids: return ids
    # fallback: none
    return []

def call(path):
    req = urllib.request.Request(URL + path, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(300).decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8","replace")
    except Exception as e:
        return "ERR", str(e)[:100]

d = json.load(open("/tmp/openapi.json"))
paths = d.get("paths", {})
DOM = {"marketing":("market","/kol","livehost","/live","toko","creator"),
       "rnd":("/rnd","rahaza/styles","rahaza/boms","rahaza/hpp","maklon/sample","maklon/bom","tech-pack","pattern","variant","product-variants"),
       "wms":("/wms","warehouse","/wh/","opname","fabric","putaway","picklist","receiving","delivery","dispatch","capacity")}

def domain_of(p):
    pl=p.lower()
    for dom,keys in DOM.items():
        if any(k in pl for k in keys): return dom
    return None

# single-param GET endpoints
single = [p for p,m in paths.items() if "get" in m and p.count("{")==1 and domain_of(p)]
print(f"Single-param GET endpoints in 3 domains: {len(single)}\n")

results={"marketing":[],"rnd":[],"wms":[]}
crashes=[]
for p in sorted(single):
    dom=domain_of(p)
    param=re.search(r"\{([^}]+)\}", p).group(1)
    cand=ids_for_path(p)
    if not cand:
        results[dom].append((p,"NO_ID",""))
        continue
    seen=[]
    for cid in cand:
        real=p.replace("{"+param+"}", str(cid))
        code,body=call(real)
        seen.append(code)
        if code==500:
            crashes.append((p, real, body[:150])); break
        if code==200: break
    best=200 if 200 in seen else (500 if 500 in seen else seen[0])
    results[dom].append((p,best,",".join(map(str,seen))))

for dom in ("marketing","rnd","wms"):
    rows=results[dom]
    n500=sum(1 for _,b,_ in rows if b==500)
    n200=sum(1 for _,b,_ in rows if b==200)
    noid=sum(1 for _,b,_ in rows if b=="NO_ID")
    print(f"=== {dom.upper()}: {len(rows)} endpoints | 200(works)={n200} 500(CRASH)={n500} no-id-resolved={noid} ===")
    for p,b,seen in rows:
        if b==500: print(f"   ❌500 {p}   (tried {seen})")

print("\n===== 500 CRASHES (detail endpoints) =====")
for p,real,body in crashes:
    print(f"  {p}\n     -> {real}\n     {body}")
json.dump({d:[(p,str(b),s) for p,b,s in results[d]] for d in results}, open("/tmp/b1_results.json","w"), indent=1)
