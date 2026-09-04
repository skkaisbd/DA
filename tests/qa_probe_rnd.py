#!/usr/bin/env python3
"""RND portal deep probe — output correctness + state machine + adversarial."""
import sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
from qa_common import Probe, login

P = Probe(login())
created = []
print("="*70+"\nRND DEEP PROBE\n"+"="*70)

# 1. dashboard KPI vs actual
dash = P.g("/api/dewi/rnd/dashboard")
if dash.status_code == 200:
    kpi = dash.json().get("kpi", {})
    lst = P.g("/api/dewi/rnd/styles?limit=1000").json()
    actual = len(lst) if isinstance(lst, list) else -1
    P.rec("dashboard total_styles == list length", kpi.get("total_styles")==actual, f"kpi={kpi.get('total_styles')} vs list={actual}")
else:
    P.rec("dashboard reachable", False, f"HTTP {dash.status_code}")

# 2. adversarial limit (expect 4xx not 5xx)
for qp in ["limit=-1","limit=0","limit=abc","limit=999999999999"]:
    r = P.g(f"/api/dewi/rnd/styles?{qp}")
    P.rec(f"styles?{qp} not 5xx", r.status_code < 500, f"HTTP {r.status_code}")
for ep in ["sample-requests","revisions","materials","sample-costing"]:
    r = P.g(f"/api/dewi/rnd/{ep}?limit=-1")
    P.rec(f"{ep}?limit=-1 not 5xx", r.status_code < 500, f"HTTP {r.status_code}")

# 3. create -> verify in list
code = f"QA-STYLE-{int(time.time())}"
cr = P.p("/api/dewi/rnd/styles", {"style_code":code,"style_name":"QA Deep Test","category":"Kaos","rnd_type":"internal_product"})
sid = None
if cr.status_code == 200:
    sid = cr.json().get("id"); created.append(sid)
    lst = P.g("/api/dewi/rnd/styles?limit=1000").json()
    P.rec("created style appears in list", any(s.get('id')==sid for s in lst), f"id={sid}")
    P.rec("created style status=draft", cr.json().get("status")=="draft", cr.json().get("status"))
    dup = P.p("/api/dewi/rnd/styles", {"style_code":code,"style_name":"dup"})
    P.rec("dup code -> 409", dup.status_code==409, f"HTTP {dup.status_code}")
else:
    P.rec("create style", False, f"HTTP {cr.status_code} {cr.text[:120]}")

# 4. state machine
if sid:
    r1 = P.p(f"/api/dewi/rnd/styles/{sid}/submit-for-review", {"notes":"qa"})
    P.rec("submit -> pending_owner_review", r1.status_code==200 and r1.json().get("status")=="pending_owner_review", f"HTTP {r1.status_code}")
    pend = P.g("/api/dewi/rnd/styles/pending-review")
    P.rec("appears in pending-review", pend.status_code==200 and any(s.get('id')==sid for s in pend.json()), f"HTTP {pend.status_code}")
    bad = P.p(f"/api/dewi/rnd/styles/{sid}/promote-to-production")
    P.rec("promote before approve -> 400", bad.status_code==400, f"HTTP {bad.status_code}")
    r2 = P.p(f"/api/dewi/rnd/styles/{sid}/owner-approve", {"notes":"ok"})
    P.rec("owner-approve -> approved_for_launch", r2.status_code==200 and r2.json().get("status")=="approved_for_launch", f"HTTP {r2.status_code}")
    r2b = P.p(f"/api/dewi/rnd/styles/{sid}/owner-approve", {"notes":"again"})
    P.rec("double approve -> 400", r2b.status_code==400, f"HTTP {r2b.status_code}")
    r3 = P.p(f"/api/dewi/rnd/styles/{sid}/promote-to-production")
    P.rec("promote -> promoted", r3.status_code==200 and r3.json().get("status")=="promoted", f"HTTP {r3.status_code}")
    if r3.status_code==200:
        st = P.g(f"/api/dewi/rnd/styles/{sid}").json()
        P.rec("style.promoted_to_model_id set", st.get("promoted_to_model_id")==r3.json().get("model_id"), str(st.get("promoted_to_model_id")))
        r3b = P.p(f"/api/dewi/rnd/styles/{sid}/promote-to-production")
        P.rec("double promote -> 400", r3b.status_code==400, f"HTTP {r3b.status_code}")

# 5. approve/update/delete NON-EXISTENT -> 404 (green-but-broken fixes)
P.rec("approve NON-EXISTENT pattern -> 404", P.p("/api/dewi/rnd/patterns/NOPE/approve").status_code==404, "")
P.rec("approve NON-EXISTENT tech-pack -> 404", P.p("/api/dewi/rnd/tech-packs/NOPE/approve").status_code==404, "")
P.rec("update NON-EXISTENT variant -> 404", P.put("/api/dewi/rnd/variants/NOPE", {"notes":"z"}).status_code==404, "")
P.rec("update NON-EXISTENT pattern -> 404", P.put("/api/dewi/rnd/patterns/NOPE", {"notes":"z"}).status_code==404, "")
P.rec("update NON-EXISTENT hpp -> 404", P.put("/api/dewi/rnd/hpp-calculator/NOPE", {}).status_code==404, "")
P.rec("update NON-EXISTENT tech-pack -> 404", P.put("/api/dewi/rnd/tech-packs/NOPE", {"title":"z"}).status_code==404, "")
P.rec("update NON-EXISTENT revision -> 404", P.put("/api/dewi/rnd/revisions/NOPE", {"reason":"z"}).status_code==404, "")
P.rec("delete NON-EXISTENT variant -> 404", P.d("/api/dewi/rnd/variants/NOPE").status_code==404, "")
P.rec("delete NON-EXISTENT pattern -> 404", P.d("/api/dewi/rnd/patterns/NOPE").status_code==404, "")
P.rec("delete NON-EXISTENT hpp -> 404", P.d("/api/dewi/rnd/hpp-calculator/NOPE").status_code==404, "")
P.rec("delete NON-EXISTENT tech-pack -> 404", P.d("/api/dewi/rnd/tech-packs/NOPE").status_code==404, "")

# 6. real pattern create->approve->verify status persisted
if sid:
    pc = P.p("/api/dewi/rnd/patterns", {"pattern_code":"QA-PAT-1","style_id":sid,"style_name":"QA"})
    if pc.status_code==200:
        pid = pc.json().get("id")
        ap = P.p(f"/api/dewi/rnd/patterns/{pid}/approve")
        lst = P.g(f"/api/dewi/rnd/patterns?style_id={sid}").json()
        got = next((x for x in lst if x.get('id')==pid), {})
        P.rec("pattern approve persists status=approved", got.get("status")=="approved", f"status={got.get('status')}")
        P.d(f"/api/dewi/rnd/patterns/{pid}")

for s in created: P.d(f"/api/dewi/rnd/styles/{s}")
print("cleanup done.")
sys.exit(1 if P.summary("RND PROBE") else 0)
