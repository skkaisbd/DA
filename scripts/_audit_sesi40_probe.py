"""Probe read-only: apa yang tersedia untuk audit impor marketing sesi #40."""
import os, json, requests

BASE = os.environ.get("BASE") or "http://localhost:8001"
r = requests.post(f"{BASE}/api/auth/login",
                  json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
r.raise_for_status()
TOK = r.json().get("access_token") or r.json().get("token")
H = {"Authorization": f"Bearer {TOK}"}

def g(p, **kw):
    return requests.get(f"{BASE}{p}", headers=H, timeout=60, **kw)

st = g("/api/marketing/data-import/source-types").json()
types = st.get("source_types") or st.get("items") or st
print("== SOURCE TYPES ==")
for t in (types if isinstance(types, list) else []):
    print(f"  {t.get('key'):32} coll={t.get('collection'):32} "
          f"update_only={t.get('update_only')} scope={t.get('account_scope')} "
          f"dedupe={t.get('dedupe')}")

grp = g("/api/marketing/data-import/source-groups").json()
print("\n== GROUPS ==")
print(json.dumps(grp, indent=1, ensure_ascii=False)[:1500])

acc = g("/api/marketing/accounts").json()
rows = acc.get("accounts") or acc.get("items") or acc
print("\n== AKUN TOKO ==")
for a in (rows if isinstance(rows, list) else [])[:20]:
    print(" ", a.get("id"), a.get("platform"), a.get("shop_name") or a.get("name"))
