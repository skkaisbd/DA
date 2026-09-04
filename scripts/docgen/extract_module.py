#!/usr/bin/env python3
"""
extract_module.py  --  Ground-Truth Extractor (DA37 ERP doc toolchain)
=======================================================================
Tujuan: memaksa dokumentasi modul GROUNDED ke kode (anti-halusinasi & anti-dangkal).

Diberi sebuah `moduleId` (dari frontend/src/components/erp/moduleRegistry.js),
skrip ini:
  1. Menemukan komponen React induk yang dipetakan ke moduleId tsb.
  2. Meng-crawl pohon import komponen secara REKURSIF (induk -> semua anak lokal).
  3. Mengekstrak SEMUA panggilan endpoint `/api/...` + SEMUA `data-testid` (dengan file:line).
  4. Membangun tabel route backend (scan backend/routes/*.py + server.py, hitung prefix).
  5. Cross-reference endpoint FE -> route backend (verified / hallucination).
  6. Menulis manifest JSON = "permukaan modul yang PASTI".

Output: docs/user-guide/_manifests/<moduleId>.manifest.json

Dependency: hanya Python stdlib (re, json, os, argparse, pathlib).
Dipakai berpasangan dengan scripts/docgen/validate_module.py (gerbang Definition of Done).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Konfigurasi path (relatif terhadap root repo /app)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]        # /app
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ERP_DIR = FRONTEND_SRC / "components" / "erp"
REGISTRY = ERP_DIR / "moduleRegistry.js"
BACKEND_DIR = REPO_ROOT / "backend"
ROUTES_DIR = BACKEND_DIR / "routes"
SERVER_PY = BACKEND_DIR / "server.py"
OUT_DIR = REPO_ROOT / "docs" / "user-guide" / "_manifests"

JS_EXT_CANDIDATES = ["", ".jsx", ".js", ".tsx", ".ts", "/index.jsx", "/index.js"]
MAX_COMPONENTS = 400          # pengaman ledakan crawl

# ---------------------------------------------------------------------------
# Util
# ---------------------------------------------------------------------------

def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _blank_keep_newlines(match) -> str:
    """Ganti teks komentar dengan spasi, TAPI pertahankan '\n' agar nomor baris tak bergeser."""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments_js(text: str) -> str:
    """Hapus komentar JS/JSX (blok /* */ dan baris //) tanpa mengubah jumlah baris.
    Mencegah false-positive (mis. contoh data-testid di dalam komentar)."""
    text = re.sub(r"/\*.*?\*/", _blank_keep_newlines, text, flags=re.DOTALL)
    # baris // ... (hindari '://' pada URL seperti http://)
    text = re.sub(r"(?<!:)//[^\n]*", lambda m: " " * len(m.group(0)), text)
    return text


def strip_comments_py(text: str) -> str:
    """Hapus komentar Python (# ...) tanpa mengubah jumlah baris."""
    return re.sub(r"(?<!['\"])#[^\n]*", lambda m: " " * len(m.group(0)), text)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def norm_path(p: str) -> str:
    """Normalisasi path endpoint agar bisa dicocokkan FE<->BE.
    - `${...}` dan `{...}` -> `{}`
    - buang query string setelah `?`
    - buang trailing slash
    """
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]*\}", "{}", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    # buang ekspresi template yang TIDAK tertutup di ujung (mis. `...generate-bundles${cond ? ...`)
    p = re.sub(r"\$?\{[^}]*$", "", p)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


# ---------------------------------------------------------------------------
# 1. Registry: moduleId -> file komponen induk
# ---------------------------------------------------------------------------

def resolve_import_source(source: str, from_file: Path) -> Path | None:
    """Resolusi string import ('./X', '../X', '@/x') -> file nyata."""
    if source.startswith("@/"):
        base = FRONTEND_SRC / source[2:]
    elif source.startswith("."):
        base = (from_file.parent / source)
    else:
        return None  # node_modules / package
    for ext in JS_EXT_CANDIDATES:
        cand = Path(str(base) + ext)
        if cand.is_file():
            return cand.resolve()
    return None


def find_component_file(module_id: str) -> tuple[Path | None, str, dict]:
    """Cari file komponen induk untuk moduleId dari registry.
    Return (file_path, component_name, info)."""
    txt = read(REGISTRY)
    info = {"registry": rel(REGISTRY)}
    # Cari entri map:  'module-id': <RHS>,
    m = re.search(r"""['"]%s['"]\s*:\s*([^,\n]+)""" % re.escape(module_id), txt)
    if not m:
        return None, "", {**info, "error": f"moduleId '{module_id}' tidak ditemukan di registry"}
    rhs = m.group(1).strip()
    info["registry_rhs"] = rhs

    # Kasus redirect / wrapper
    redirect = re.match(r"makeRedirect\(\s*['\"]([^'\"]+)['\"]", rhs)
    if redirect:
        info["is_redirect"] = True
        info["redirect_target"] = redirect.group(1)
        # resolusi target
        return find_component_file(redirect.group(1))[0], "", {**info, "note": "redirect"}

    wrap = re.match(r"makeModuleWithTab\(\s*(\w+)", rhs)
    comp_name = wrap.group(1) if wrap else rhs

    # comp_name -> import path (lazy() atau import statik) di registry
    im = re.search(r"""(?:const\s+%s\s*=\s*lazy\(\s*\(\)\s*=>\s*import\(\s*['"]([^'"]+)['"]|import\s+%s\s+from\s+['"]([^'"]+)['"])"""
                   % (re.escape(comp_name), re.escape(comp_name)), txt)
    if not im:
        return None, comp_name, {**info, "error": f"import untuk komponen '{comp_name}' tidak ditemukan"}
    source = im.group(1) or im.group(2)
    fpath = resolve_import_source(source, REGISTRY)
    if not fpath:
        return None, comp_name, {**info, "error": f"file untuk '{source}' tidak dapat diresolusi"}
    return fpath, comp_name, info


# ---------------------------------------------------------------------------
# 2. Crawl pohon komponen + ekstraksi endpoint & testid per file
# ---------------------------------------------------------------------------
IMPORT_RE = re.compile(r"""import\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]""")
API_RE = re.compile(r"/api/[A-Za-z0-9_\-./${}():]+")
TESTID_RES = [
    re.compile(r"""data-testid\s*=\s*"([^"]+)\""""),
    re.compile(r"""data-testid\s*=\s*'([^']+)'"""),
    re.compile(r"data-testid\s*=\s*\{\s*`([^`]+)`\s*\}"),
    re.compile(r"data-testid\s*=\s*\{\s*([^}`]+?)\s*\}"),
]


def classify(path: Path) -> str:
    s = rel(path)
    if "/components/erp/" in s:
        return "erp"
    if "/components/ui/" in s:
        return "ui"
    return "lib"


def static_prefix(testid: str) -> str:
    """Ambil bagian statis sebelum bagian dinamis (${...} atau {...})."""
    cut = len(testid)
    for marker in ("${", "{", "`"):
        idx = testid.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    return testid[:cut]


def scan_file(path: Path) -> dict:
    """Ekstrak import lokal, endpoint /api, dan data-testid (dengan line)."""
    text = strip_comments_js(read(path))
    lines = text.splitlines()

    # imports (lokal saja -> file nyata)
    child_files = []
    for src in IMPORT_RE.findall(text):
        resolved = resolve_import_source(src, path)
        if resolved:
            child_files.append(resolved)

    # endpoints + testids per baris (untuk line number akurat)
    endpoints = []
    testids = []
    for i, line in enumerate(lines, start=1):
        for mm in API_RE.findall(line):
            endpoints.append({"raw": mm, "norm": norm_path(mm), "line": i})
        for rx in TESTID_RES:
            for val in rx.findall(line):
                val = val.strip()
                # abaikan ekspresi murni yang jelas bukan testid (mis. hanya nama variabel tanpa huruf/tanda)
                dynamic = ("$" in val) or ("`" in val) or (rx is TESTID_RES[3])
                testids.append({
                    "raw": val,
                    "prefix": static_prefix(val),
                    "dynamic": dynamic,
                    "line": i,
                })
    return {
        "file": rel(path),
        "kind": classify(path),
        "child_files": child_files,
        "endpoints": endpoints,
        "testids": testids,
    }


def crawl(root_file: Path) -> dict:
    visited: dict[str, dict] = {}
    order: list[Path] = []
    queue = [root_file]
    while queue and len(visited) < MAX_COMPONENTS:
        cur = queue.pop(0)
        key = str(cur)
        if key in visited:
            continue
        # hanya crawl file di dalam frontend/src
        try:
            cur.relative_to(FRONTEND_SRC)
        except ValueError:
            continue
        data = scan_file(cur)
        visited[key] = data
        order.append(cur)
        for child in data["child_files"]:
            if str(child) not in visited:
                queue.append(child)
    return {"visited": visited, "order": order}


# ---------------------------------------------------------------------------
# 3. Tabel route backend (scan semua routes + server.py)
# ---------------------------------------------------------------------------
ROUTER_DECL_RE = re.compile(r"(\w+)\s*=\s*APIRouter\((.*?)\)", re.DOTALL)
PREFIX_RE = re.compile(r"""prefix\s*=\s*['"]([^'"]*)['"]""")
DECORATOR_RE = re.compile(r"""@(\w+)\.(get|post|put|delete|patch|options|head)\(\s*['"]([^'"]*)['"]""", re.IGNORECASE)
APP_DECORATOR_RE = re.compile(r"""@app\.(get|post|put|delete|patch|options|head)\(\s*['"]([^'"]*)['"]""", re.IGNORECASE)

# pola file dead-code / arsip yang HARUS diabaikan (jangan dikutip sebagai sumber)
DEADCODE_MARKERS = ("_backup", ".old", ".pre-refactor", "_archive", "/_archive/", ".bak")


def is_dead_code(path: Path) -> bool:
    s = str(path)
    return any(mark in s for mark in DEADCODE_MARKERS)


def build_backend_route_table() -> list[dict]:
    routes = []
    files = list(ROUTES_DIR.rglob("*.py")) + [SERVER_PY]
    for f in files:
        if not f.is_file() or is_dead_code(f):
            continue
        text = strip_comments_py(read(f))
        # peta variabel router -> prefix
        prefix_map = {}
        for m in ROUTER_DECL_RE.finditer(text):
            var, args = m.group(1), m.group(2)
            pm = PREFIX_RE.search(args)
            prefix_map[var] = pm.group(1) if pm else ""
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            dm = DECORATOR_RE.search(line)
            if dm:
                var, method, rpath = dm.group(1), dm.group(2).upper(), dm.group(3)
                prefix = prefix_map.get(var, "")
                full = norm_path(prefix + rpath)
                routes.append({"method": method, "path": full, "file": rel(f), "line": i})
                continue
            am = APP_DECORATOR_RE.search(line)
            if am:
                method, rpath = am.group(1).upper(), am.group(2)
                routes.append({"method": method, "path": norm_path(rpath), "file": rel(f), "line": i})
    return routes


def match_backend(fe_path: str, route_index: dict) -> tuple[list, str]:
    """Cari route backend untuk sebuah path FE.
    1) cocok persis (prefix router terdeteksi langsung).
    2) fallback SUFFIX: menangani `include_router(sub, prefix=..)` bersarang di mana
       sub-router memakai prefix "" sehingga path-nya adalah akhiran dari path FE
       (mis. FE `/api/rahaza/work-orders/{}/generate-bundles`
        = `/api/rahaza` + route sub `/work-orders/{}/generate-bundles`).
       Ambil akhiran TERPANJANG agar tidak salah cocok.
    """
    exact = route_index.get(fe_path, [])
    if exact:
        return exact, "exact"
    best = None
    for bpath, routes_list in route_index.items():
        if not bpath.startswith("/") or bpath == fe_path or len(bpath) <= 2:
            continue
        if fe_path.endswith(bpath) and fe_path[:-len(bpath)].startswith("/api"):
            if best is None or len(bpath) > len(best[0]):
                best = (bpath, routes_list)
    if best:
        return best[1], "suffix"
    return [], "none"


# ---------------------------------------------------------------------------
# 4. Rakit manifest
# ---------------------------------------------------------------------------

def build_manifest(module_id: str) -> dict:
    comp_file, comp_name, reg_info = find_component_file(module_id)
    if not comp_file:
        return {"module_id": module_id, "error": reg_info.get("error", "gagal resolusi komponen"), "registry_info": reg_info}

    crawled = crawl(comp_file)
    visited = crawled["visited"]

    # Kumpulan endpoint FE (unik, dengan bukti file:line)
    fe_endpoints: dict[str, dict] = {}
    testid_prefixes: dict[str, dict] = {}
    components = []
    for cur in crawled["order"]:
        d = visited[str(cur)]
        name = Path(d["file"]).stem
        components.append({
            "name": name,
            "file": d["file"],
            "kind": d["kind"],
            "n_endpoints": len(d["endpoints"]),
            "n_testids": len(d["testids"]),
        })
        for ep in d["endpoints"]:
            key = ep["norm"]
            fe_endpoints.setdefault(key, {"norm": key, "evidence": []})
            fe_endpoints[key]["evidence"].append({"file": d["file"], "line": ep["line"], "raw": ep["raw"]})
        for t in d["testids"]:
            pfx = t["prefix"]
            if not pfx:
                continue
            testid_prefixes.setdefault(pfx, {"prefix": pfx, "dynamic": t["dynamic"], "evidence": []})
            testid_prefixes[pfx]["evidence"].append({"file": d["file"], "line": t["line"], "raw": t["raw"]})

    # Tabel route backend + cross-ref
    routes = build_backend_route_table()
    route_index: dict[str, list] = {}
    for r in routes:
        route_index.setdefault(r["path"], []).append(r)

    matched = []      # endpoint FE yang PUNYA route backend
    unmatched = []    # endpoint FE TANPA route backend (indikasi masalah)
    for key, ep in sorted(fe_endpoints.items()):
        backend_hits, how = match_backend(key, route_index)
        entry = {
            "path": key,
            "frontend_evidence": ep["evidence"],
            "backend_routes": [{"method": r["method"], "file": r["file"], "line": r["line"]} for r in backend_hits],
            "verified": bool(backend_hits),
            "match_type": how,
        }
        (matched if backend_hits else unmatched).append(entry)

    erp_components = [c for c in components if c["kind"] == "erp"]

    manifest = {
        "module_id": module_id,
        "component_name": comp_name,
        "component_file": rel(comp_file),
        "registry_info": reg_info,
        "generated_from": "scripts/docgen/extract_module.py",
        "summary": {
            "components_total": len(components),
            "components_erp": len(erp_components),
            "components_ui": len([c for c in components if c["kind"] == "ui"]),
            "components_lib": len([c for c in components if c["kind"] == "lib"]),
            "frontend_endpoints_unique": len(fe_endpoints),
            "frontend_endpoints_verified": len(matched),
            "frontend_endpoints_unverified": len(unmatched),
            "testid_prefixes": len(testid_prefixes),
            "backend_routes_total": len(routes),
        },
        "components": components,
        "endpoints": {
            "verified": matched,
            "unverified": unmatched,
        },
        "testids": sorted(testid_prefixes.values(), key=lambda x: x["prefix"]),
        # daftar SEMUA path backend (untuk anti-halusinasi lintas modul di validator)
        "all_backend_paths": sorted(set(r["path"] for r in routes)),
    }
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Ground-Truth Extractor untuk dokumentasi modul DA37 ERP")
    ap.add_argument("--module-id", required=True, help="moduleId di moduleRegistry.js (mis. prod-orders)")
    ap.add_argument("--out", default=None, help="path output manifest (default: docs/user-guide/_manifests/<id>.manifest.json)")
    ap.add_argument("--print", action="store_true", help="cetak ringkasan ke stdout")
    args = ap.parse_args()

    manifest = build_manifest(args.module_id)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else (OUT_DIR / f"{args.module_id}.manifest.json")
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    if manifest.get("error"):
        print(f"[extract] ERROR: {manifest['error']}")
        print(f"[extract] manifest ditulis ke {rel(out_path)} (berisi error)")
        return 2

    s = manifest["summary"]
    print(f"[extract] moduleId       : {manifest['module_id']}")
    print(f"[extract] komponen induk : {manifest['component_name']}  ({manifest['component_file']})")
    print(f"[extract] komponen total : {s['components_total']} (erp={s['components_erp']}, ui={s['components_ui']}, lib={s['components_lib']})")
    print(f"[extract] endpoint FE    : {s['frontend_endpoints_unique']} unik  ->  verified={s['frontend_endpoints_verified']}, UNVERIFIED={s['frontend_endpoints_unverified']}")
    print(f"[extract] data-testid    : {s['testid_prefixes']} prefix")
    print(f"[extract] route backend  : {s['backend_routes_total']} total di tabel")
    if manifest["endpoints"]["unverified"]:
        print("[extract] !! endpoint FE TANPA route backend (cek manual):")
        for e in manifest["endpoints"]["unverified"]:
            print(f"           - {e['path']}  (dari {e['frontend_evidence'][0]['file']}:{e['frontend_evidence'][0]['line']})")
    print(f"[extract] manifest       : {rel(out_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
