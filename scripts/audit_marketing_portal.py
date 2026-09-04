#!/usr/bin/env python3
"""
AUDIT PORTAL MARKETING — harness pembuktian cacat (bukan dugaan).

Menjawab 4 pertanyaan yang diminta owner, semuanya dengan BUKTI file:line:

  A. ENDPOINT HANTU  — layar memanggil endpoint yang TIDAK ADA di backend
                       (fitur mati / tombol tidak berfungsi).
  B. ENDPOINT SALAH  — layar memanggil endpoint yang ADA tapi milik domain lain
                       (mis. layar marketing menarik data produksi).
  C. LUBANG FE       — endpoint marketing yang ADA di backend tapi TIDAK PERNAH
                       dipanggil layar mana pun (fitur backend tak terpakai).
  D. KOLEKSI         — koleksi Mongo yang dirujuk kode marketing tapi KOSONG /
                       TIDAK ADA di DB (indikasi salah nama koleksi).

Pakai:
  python3 scripts/audit_marketing_portal.py            # ringkas
  python3 scripts/audit_marketing_portal.py --verbose  # semua bukti
  python3 scripts/audit_marketing_portal.py --json out.json
"""
import os
import re
import sys
import json
import glob
import argparse
import urllib.request

APP = "/app"
FE = os.path.join(APP, "frontend/src")
BE = os.path.join(APP, "backend")
BACKEND_URL = "http://localhost:8001"

# ── 1. Berkas layar yang termasuk PORTAL MARKETING ───────────────────────────
FE_GLOBS = [
    "components/erp/marketing/**/*.jsx",
    "components/erp/hubs/Marketing*.jsx",
    "components/erp/livehost/**/*.jsx",
    "components/erp/creator/**/*.jsx",
    "hooks/useMarketingAccounts.js",
    "hooks/useActiveMarketingAccount.js",
]
# Modul marketing yang tinggal di components/erp/ (bukan di sub-folder marketing/)
FE_EXTRA = [
    "components/erp/AccountManagementModule.jsx",
    "components/erp/SalesDataEntryModule.jsx",
    "components/erp/ImportCenterModule.jsx",
    "components/erp/KOLCreatorModule.jsx",
    "components/erp/CatalogManagementModule.jsx",
    "components/erp/TaskManagementModule.jsx",
    "components/erp/TaskTemplatesModule.jsx",
    "components/erp/MarketingTaskHubModule.jsx",
    "components/erp/MarketingAfterSalesHub.jsx",
    "components/erp/MarketingReportsHub.jsx",
    "components/erp/MarketingARBridgeModule.jsx",
    "components/erp/TokoProductCatalogModule.jsx",
    "components/erp/MarketingDashboard.jsx",
    "components/erp/CatalogItemPickerDialog.jsx",
    "components/erp/FGProductPickerDialog.jsx",
    "components/erp/ApprovalInboxModule.jsx",
    "components/erp/NotificationCenterModule.jsx",
]

# ── 2. Prefix backend yang dianggap "milik" domain marketing ─────────────────
MARKETING_PREFIXES = ("/api/marketing", "/api/toko")
# Prefix domain LAIN (kalau layar marketing memanggil ini => perlu penalaran)
FOREIGN_PREFIXES = {
    "/api/rahaza": "keuangan/master/produksi (rahaza)",
    "/api/production": "produksi",
    "/api/wms": "gudang",
    "/api/dewi/maklon": "maklon",
    "/api/dewi/rnd": "RnD",
    "/api/cmt": "CMT",
    "/api/procurement": "pengadaan",
    "/api/warehouse": "gudang",
    "/api/fulfillment": "fulfillment",
    "/api/universal-import": "import universal",
}


def fe_files():
    out = []
    for g in FE_GLOBS:
        out += glob.glob(os.path.join(FE, g), recursive=True)
    for f in FE_EXTRA:
        p = os.path.join(FE, f)
        if os.path.exists(p):
            out.append(p)
    return sorted(set(out))


# ── 3. Ekstraksi path API dari layar ────────────────────────────────────────
# Bentuk yang dipakai repo ini:
#   `${API}/api/marketing/accounts`
#   apiGet('/marketing/accounts')        -> /api/marketing/accounts
#   apiFetch(`/marketing/x/${id}`)
CALL_RE = re.compile(
    r"""(?:apiGet|apiPost|apiPut|apiDelete|apiFetch|apiDownload|fetch)\s*\(\s*
        (?P<q>['"`])(?P<path>[^'"`]*?)(?P=q)""",
    re.X,
)
TPL_RE = re.compile(r"""\$\{API(?:_BASE)?\}(?P<path>/api/[A-Za-z0-9_\-/{}$.]*)""")
BARE_API_RE = re.compile(r"""(?P<q>['"`])(?P<path>/api/[A-Za-z0-9_\-/{}$.]+)(?P=q)""")


def normalize(path: str) -> str:
    """`${x}` / :id / angka -> {p}; buang query string; buang trailing slash."""
    p = path.split("?")[0].split("#")[0]
    p = re.sub(r"\$\{[^}]*\}", "{p}", p)
    p = re.sub(r"\$\{", "{p}", p)
    p = re.sub(r"/:[A-Za-z0-9_]+", "/{p}", p)
    p = re.sub(r"/\d+(?=/|$)", "/{p}", p)
    if not p.startswith("/api"):
        if p.startswith("/"):
            p = "/api" + p
        else:
            return ""
    p = re.sub(r"/+", "/", p)
    if len(p) > 5 and p.endswith("/"):
        p = p[:-1]
    return p


def extract_fe_calls():
    """-> { normalized_path: [ (file, line, raw) ] }"""
    calls = {}
    for f in fe_files():
        rel = os.path.relpath(f, APP)
        try:
            src = open(f, encoding="utf-8").read()
        except Exception:
            continue
        lines = src.split("\n")
        for idx, line in enumerate(lines, 1):
            found = set()
            for m in TPL_RE.finditer(line):
                found.add(m.group("path"))
            for m in CALL_RE.finditer(line):
                raw = m.group("path")
                if raw.startswith("/") or raw.startswith("$"):
                    found.add(raw)
            for m in BARE_API_RE.finditer(line):
                found.add(m.group("path"))
            for raw in found:
                n = normalize(raw)
                if not n or n == "/api":
                    continue
                calls.setdefault(n, []).append((rel, idx, raw))
    return calls


# ── 4. Daftar route backend (dari OpenAPI app yang berjalan) ─────────────────
def be_routes():
    """-> { normalized_path: set(methods) }  + raw list."""
    url = BACKEND_URL + "/api/openapi.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        spec = json.load(r)
    routes = {}
    for path, item in spec.get("paths", {}).items():
        methods = {m.upper() for m in item.keys() if m.lower() in
                   ("get", "post", "put", "patch", "delete")}
        n = re.sub(r"\{[^}]*\}", "{p}", path)
        n = re.sub(r"/+", "/", n)
        if len(n) > 5 and n.endswith("/"):
            n = n[:-1]
        routes.setdefault(n, set()).update(methods)
    return routes


def route_exists(fe_path, routes):
    """Cocokkan dengan toleransi: {p} FE bisa jadi segmen literal BE & sebaliknya."""
    if fe_path in routes:
        return fe_path
    fe_seg = fe_path.strip("/").split("/")
    for r in routes:
        r_seg = r.strip("/").split("/")
        if len(r_seg) != len(fe_seg):
            continue
        ok = True
        for a, b in zip(fe_seg, r_seg):
            if a == b or a == "{p}" or b == "{p}":
                continue
            ok = False
            break
        if ok:
            return r
    return None


# ── 5. Koleksi Mongo yang dirujuk kode marketing ─────────────────────────────
COLL_RE = re.compile(r"""db\.(?P<c>[a-z][a-z0-9_]{2,})\b|db\[\s*['"](?P<c2>[^'"]+)['"]\s*\]""")
BE_MARKETING_FILES = ["routes/marketing_*.py", "routes/dewi_toko.py",
                      "routes/_toko_adapter.py", "routes/universal_import.py",
                      "core/marketing*.py", "services/ai/*.py"]
DB_METHODS = {"list_collection_names", "command", "client", "name", "get_collection",
              "drop_collection", "create_collection"}


def be_marketing_files():
    out = []
    for g in BE_MARKETING_FILES:
        out += glob.glob(os.path.join(BE, g))
    return sorted(set(out))


def extract_collections():
    colls = {}
    for f in be_marketing_files():
        rel = os.path.relpath(f, APP)
        src = open(f, encoding="utf-8").read()
        for idx, line in enumerate(src.split("\n"), 1):
            for m in COLL_RE.finditer(line):
                c = m.group("c") or m.group("c2")
                if not c or c in DB_METHODS:
                    continue
                colls.setdefault(c, []).append((rel, idx))
    return colls


def db_collection_counts():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BE, ".env"))
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    return {c: db[c].estimated_document_count() for c in db.list_collection_names()}


# ── 6. Laporan ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    fe = extract_fe_calls()
    routes = be_routes()

    def is_base_url(path):
        """Bukan cacat: konstanta URL DASAR yang dipakai lewat helper.

        Pola nyata di repo ini:
          `const BASE = `${API}/api/marketing/data-import``
          `const cat = (path) => fetch(`${API}/api/marketing/catalogs${path}`)`
        Path seperti itu tidak pernah dipanggil utuh, jadi melaporkannya sebagai
        "endpoint hantu" hanya melahirkan temuan palsu yang lama-lama diabaikan.
        """
        base = path.rstrip('/').removesuffix('{p}').rstrip('/')
        if len(base) < 8:
            return False
        return any(r.startswith(base + '/') for r in routes)

    ghost, foreign, ok = [], [], []
    for p, sites in sorted(fe.items()):
        match = route_exists(p, routes)
        if match is None and is_base_url(p):
            continue
        if match is None:
            ghost.append((p, sites))
        else:
            ok.append((p, match))
            for pref, dom in FOREIGN_PREFIXES.items():
                if p.startswith(pref):
                    foreign.append((p, dom, sites))
                    break

    fe_matched = {route_exists(p, routes) for p in fe}
    # Banyak layar memanggil lewat helper: `const cat = (path) => fetch(`${API}/api/marketing/catalogs${path}`)`
    # sehingga path penuh tak pernah muncul utuh. Karena itu route dianggap
    # DIPAKAI bila ekor path-nya (2-3 segmen terakhir) muncul sebagai teks di layar.
    fe_blob = "\n".join(open(f, encoding="utf-8").read() for f in fe_files())

    def tail_seen(route):
        seg = [x for x in route.strip("/").split("/") if x]
        for n in (3, 2):
            if len(seg) >= n:
                tail = "/".join(seg[-n:]).replace("{p}", "")
                tail = re.sub(r"/+", "/", tail)
                if len(tail) > 6 and tail.strip("/") and tail in fe_blob:
                    return True
        # ekor 1 segmen hanya kalau cukup khas (>=10 char)
        if seg and seg[-1] != "{p}" and len(seg[-1]) >= 10 and seg[-1] in fe_blob:
            return True
        return False

    orphan = []
    for r, methods in sorted(routes.items()):
        if not r.startswith(MARKETING_PREFIXES):
            continue
        if r in fe_matched:
            continue
        if tail_seen(r):
            continue
        orphan.append((r, sorted(methods)))

    colls = extract_collections()
    counts = db_collection_counts()
    coll_missing, coll_empty = [], []
    if counts is not None:
        for c, sites in sorted(colls.items()):
            if c not in counts:
                coll_missing.append((c, sites))
            elif counts[c] == 0:
                coll_empty.append((c, sites))

    W = 78
    print("=" * W)
    print("AUDIT PORTAL MARKETING")
    print("=" * W)
    print(f"berkas layar diperiksa : {len(fe_files())}")
    print(f"path API dipanggil FE  : {len(fe)}")
    print(f"route backend total    : {len(routes)}")
    print()

    print(f"[A] ENDPOINT HANTU (FE memanggil, backend TIDAK ADA) : {len(ghost)}")
    for p, sites in ghost:
        print(f"  ✗ {p}")
        for rel, ln, raw in (sites if args.verbose else sites[:2]):
            print(f"      {rel}:{ln}  ({raw})")
    print()

    print(f"[B] LINTAS DOMAIN (layar marketing → endpoint domain lain) : {len(foreign)}")
    for p, dom, sites in foreign:
        print(f"  ? {p}   [{dom}]")
        for rel, ln, raw in (sites if args.verbose else sites[:1]):
            print(f"      {rel}:{ln}")
    print()

    print(f"[C] ENDPOINT MARKETING TANPA PEMAKAI DI LAYAR : {len(orphan)}")
    if args.verbose:
        for r, methods in orphan:
            print(f"  - {','.join(methods):22s} {r}")
    else:
        for r, methods in orphan[:25]:
            print(f"  - {','.join(methods):22s} {r}")
        if len(orphan) > 25:
            print(f"  ... {len(orphan)-25} lagi (pakai --verbose)")
    print()

    print(f"[D] KOLEKSI DIRUJUK TAPI TIDAK ADA DI DB : {len(coll_missing)}")
    for c, sites in coll_missing:
        print(f"  ✗ {c}")
        for rel, ln in (sites if args.verbose else sites[:2]):
            print(f"      {rel}:{ln}")
    print(f"\n[D2] KOLEKSI ADA TAPI KOSONG (0 dokumen) : {len(coll_empty)}")
    for c, sites in coll_empty:
        print(f"  ! {c}  ({len(sites)} rujukan)")
        if args.verbose:
            for rel, ln in sites[:4]:
                print(f"      {rel}:{ln}")
    print()
    print("=" * W)
    print(f"RINGKAS: hantu={len(ghost)} lintas_domain={len(foreign)} "
          f"orphan={len(orphan)} koleksi_hilang={len(coll_missing)} "
          f"koleksi_kosong={len(coll_empty)}")
    print("=" * W)

    if args.json_out:
        json.dump({
            "ghost": [{"path": p, "sites": s} for p, s in ghost],
            "foreign": [{"path": p, "domain": d, "sites": s} for p, d, s in foreign],
            "orphan": [{"path": r, "methods": m} for r, m in orphan],
            "coll_missing": [{"coll": c, "sites": s} for c, s in coll_missing],
            "coll_empty": [{"coll": c, "sites": s} for c, s in coll_empty],
        }, open(args.json_out, "w"), indent=2, ensure_ascii=False)
        print(f"JSON -> {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
