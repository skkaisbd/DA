#!/usr/bin/env python3
"""INV-CONTRACT-01 — Gate kontrak Frontend ↔ Backend.

Menutup blindspot RC-1/RC-3 (“200 OK tapi layar/tabel kosong”) & 404 senyap:

  CHECK A — Duplicate route (BLOCKING/HIGH): (METHOD, path) sama didefinisikan >1x
            lintas file router. FastAPI memakai definisi TERAKHIR → handler pertama
            mati diam-diam (mis. filter hilang). Deteksi via AST (sumber file).

  CHECK B — FE call → endpoint backend ADA (WARN / TRIAGE, tak mem-blok): setiap
            `${API}/api/...` yang dipanggil FE dicocokkan (segment + wildcard) dgn
            daftar route AUTORITATIF dari /api/openapi.json (runtime) bila backend
            hidup, jatuh ke AST bila mati. Tidak cocok = kandidat endpoint dihapus/
            typo (404 senyap) ATAU komposisi path dinamis (wrapper) → perlu triase
            manusia. Sengaja WARN agar tak menghasilkan “merah palsu”.

  CHECK C — Orphan BE (INFO): route backend yang TIDAK pernah dipanggil FE
            (kandidat dead-code / permukaan serang tersembunyi).

Usage: cd /app && python scripts/preflight/verify_fe_be_contract.py [--report-only]
"""
import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import (  # noqa: E402
    Report, all_routes, fe_calls, norm_path, api_base, http, backend_up,
)
from route_table import (  # noqa: E402
    describe_duplicate, duplicate_routes, runtime_route_table,
)
import json
import urllib.request


def websocket_shapes():
    """Shape endpoint WebSocket — dipanen dari SUMBER, bukan OpenAPI.

    FASE 20 — BLINDSPOT: OpenAPI **tidak pernah** memuat route WebSocket
    (spesifikasi OpenAPI 3 tak punya representasinya). Karena CHECK B memakai
    OpenAPI sebagai daftar autoritatif, setiap `new WebSocket(...)` di FE selalu
    dilaporkan FE_DEAD_CALL — mis. `/api/comm/ws` yang JELAS ADA dan berfungsi.
    False positive permanen membuat gate ini dianggap "berisik" lalu diabaikan,
    dan itu cara paling cepat sebuah guardrail jadi tak berguna.

    Router WebSocket sering didefinisikan di file yang MENGIMPOR `router` dari
    modul lain (`from ._helpers import router`), jadi prefix-nya harus dicari
    ke file sumber tersebut — bukan cuma di file yang memuat `@router.websocket`.
    """
    shapes = set()
    prefix_cache: dict[Path, str] = {}

    def _prefix_of(py: Path) -> str:
        if py in prefix_cache:
            return prefix_cache[py]
        prefix_cache[py] = ""
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
        m = re.search(r"APIRouter\((?:[^)]*?)prefix\s*=\s*[\"']([^\"']+)[\"']", text, re.S)
        if m:
            prefix_cache[py] = m.group(1)
            return prefix_cache[py]
        # `router` diimpor dari modul lain → ikuti impor relatifnya
        for imp in re.finditer(r"from\s+(\.[\w.]*)\s+import\s+([^\n]+)", text):
            if "router" not in imp.group(2):
                continue
            rel = imp.group(1)
            depth = len(rel) - len(rel.lstrip("."))
            mod = rel[depth:]
            base = py.parent
            for _ in range(depth - 1):
                base = base.parent
            cand = base / (mod.replace(".", "/") + ".py") if mod else base / "__init__.py"
            if cand.exists() and cand != py:
                prefix_cache[py] = _prefix_of(cand)
                break
        return prefix_cache[py]

    for py in _BACKEND.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if ".websocket(" not in text:
            continue
        for m in re.finditer(r"@(?:api_)?(?:router|app)\.websocket\(\s*[\"']([^\"']*)[\"']", text):
            shapes.add(norm_path(_prefix_of(py) + m.group(1)))
    return shapes


def openapi_shapes():
    """Set shape path dari runtime OpenAPI (autoritatif). None bila gagal."""
    if not backend_up():
        return None
    try:
        with urllib.request.urlopen(api_base() + "/api/openapi.json", timeout=20) as r:
            spec = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    shapes = set()
    for p in spec.get("paths", {}):
        shapes.add(norm_path(p))
    return shapes


def _segs(shape):
    return [s for s in shape.strip("/").split("/") if s != ""]


# ═════════════════════════════════════════════════════════════════════════════
# CHECK D — ORPHAN HANDLER: fungsi bergaya endpoint TANPA dekorator route
# ═════════════════════════════════════════════════════════════════════════════
_BACKEND = Path("/app/backend")
_ROUTE_DECOS = ("get", "post", "put", "patch", "delete", "head", "options",
                "api_route", "websocket")
_AUTH_HINTS = ("require_auth", "_require_", "require_role", "get_current_user",
               "Depends")


def _is_route_decorator(dec: ast.AST) -> bool:
    """True untuk `@router.get(...)`, `@app.post(...)`, `@router.api_route(...)`, dst."""
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr in _ROUTE_DECOS


def _takes_request(fn: ast.AST) -> bool:
    args = list(getattr(fn.args, "args", [])) + list(getattr(fn.args, "kwonlyargs", []))
    for a in args:
        if a.arg == "request":
            return True
        ann = getattr(a, "annotation", None)
        if isinstance(ann, ast.Name) and ann.id == "Request":
            return True
        if isinstance(ann, ast.Attribute) and ann.attr == "Request":
            return True
    return False


def _code_referenced_names() -> set[str]:
    """Nama yang BENAR-BENAR dirujuk oleh KODE di seluruh backend (bukan teks).

    Kenapa AST dan bukan regex: percobaan pertama memakai `re.findall` atas teks
    mentah, sehingga nama fungsi yang cuma DISEBUT DI KOMENTAR terhitung sebagai
    "dipakai" — dan CHECK D gagal menjadi MERAH saat bug ditanam ulang
    (`scripts/prove_guardrail_red.sh` yang menangkapnya). Guard yang tidak bisa
    merah bukan guard; jadi deteksinya harus melihat KODE, bukan tulisan.
    """
    names: set[str] = set()
    for f in _BACKEND.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception:  # noqa: BLE001 — file rusak ditangkap gate lain
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):        # from x import nama
                names.add(node.asname or node.name.split(".")[-1])
    return names


def find_orphan_handlers() -> list[dict]:
    """Fungsi di `backend/routes/**` yang JELAS endpoint tapi tanpa dekorator route.

    Kriteria (sengaja konservatif supaya tidak berisik):
      1. berada di modul yang memang punya route (ada ≥1 dekorator route), bukan helper;
      2. menerima parameter `Request`;
      3. TIDAK punya dekorator sama sekali;
      4. namanya TIDAK dirujuk KODE mana pun di backend (bukan helper yang dipanggil);
      5. DAN (memanggil auth) ATAU (diapit dua fungsi ber-dekorator) —
         dua tanda terkuat bahwa dekoratornya memang HILANG, bukan sengaja.
    """
    files = [f for f in _BACKEND.rglob("routes/**/*.py")
             if "_archive" not in f.parts and "__pycache__" not in f.parts]
    referenced = _code_referenced_names()

    out: list[dict] = []
    for f in files:
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
        except Exception:  # noqa: BLE001 — file rusak ditangkap gate lain
            continue
        fns = [n for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        decorated = [bool(any(_is_route_decorator(d) for d in n.decorator_list))
                     for n in fns]
        if not any(decorated):
            continue  # bukan modul router
        for i, fn in enumerate(fns):
            if decorated[i] or fn.name.startswith("_"):
                continue
            if fn.decorator_list:
                continue  # ada dekorator lain (mis. @lru_cache) → sengaja bukan route
            if not _takes_request(fn):
                continue
            if fn.name in referenced:
                continue  # helper yang sah: dipanggil kode lain
            body_src = ast.get_source_segment(src, fn) or ""
            has_auth = any(h in body_src for h in _AUTH_HINTS)
            sandwiched = (i > 0 and decorated[i - 1]
                          and i + 1 < len(fns) and decorated[i + 1])
            if not (has_auth or sandwiched):
                continue
            out.append({
                "file": str(f.relative_to(_BACKEND)), "line": fn.lineno,
                "func": fn.name, "auth": has_auth, "sandwiched": sandwiched,
            })
    return out


def _seg_match(fe, be):
    """Cocokkan shape FE → shape BE. **SENGAJA ASIMETRIS.**

    `{}` di sisi BACKEND = path parameter: menerima nilai apa pun, jadi ia cocok
    dengan segmen FE apa pun — termasuk literal seperti `by-code`.

    `{}` di sisi FRONTEND = nilai yang DISISIPKAN saat runtime (`${id}`). Ia TIDAK
    boleh dianggap cocok dengan segmen LITERAL backend: kalau backend menuntut
    literal `assign` di posisi itu, memanggilnya dengan `LP-001` menghasilkan
    **404** — justru kelas bug yang CHECK B harus tangkap.

    BUG LAMA (ditemukan FASE 20): aturannya simetris
    (`if a == "{}" or b == "{}" ... : continue`) sehingga sisi FE ikut dianggap
    wildcard. Akibatnya FE `/api/dewi/assets/by-code/{}` "cocok" dengan BE
    `/api/dewi/assets/{}/assign` dan **404 nyatanya tidak pernah dilaporkan**
    (fitur scan QR aset mati diam-diam). Guard yang menutupi bug yang seharusnya
    ia tangkap lebih berbahaya daripada tidak ada guard.
    """
    if len(fe) != len(be):
        return False
    for a, b in zip(fe, be):
        if "{}" in b:      # BE path param → wildcard sejati
            continue
        if "{}" in a:      # FE dinamis vs BE literal → BUKAN cocok
            return False
        if a != b:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    rep = Report("INV-CONTRACT-01", "Kontrak FE↔BE (duplicate route / FE→route ada / orphan BE)",
                 block_sev=() if args.report_only else ("HIGH",))

    routes = all_routes()
    exact_seen = defaultdict(list)
    ast_shapes = set()
    for r in routes:
        rep.bump()
        ast_shapes.add(norm_path(r["path"]))
        exact_seen[(r["method"], r["path"])].append(f"{r['file']}:{r['line']}")

    # ─── CHECK A: duplicate routes → ground truth tabel route runtime ───
    # FASE 14 — dulu CHECK A memakai path DEKORATOR dari AST tanpa me-resolve
    # `prefix=`. Hasilnya berbohong dua arah: 5 HIGH palsu (`/dashboard` di 4
    # router dengan prefix berbeda dilaporkan "saling menimpa") dan 7 duplikat
    # NYATA terlewat (`marketing_task_templates` di-include DUA KALI — mustahil
    # terlihat dari scan dekorator). Sekarang sumbernya `app.routes` yang PERSIS
    # dipakai FastAPI. Lihat scripts/lib/route_table.py.
    rt_table = runtime_route_table()
    dup = {k: v for k, v in exact_seen.items() if len(v) > 1}  # kandidat dari AST dekorator
    if rt_table:
        rt_dup = duplicate_routes(rt_table)
        print(f"  [INFO] CHECK A — sumber: tabel route RUNTIME (ground truth), "
              f"{len(rt_table)} (method,path) terdaftar.")
        if not rt_dup:
            print("  [OK  ] CHECK A — tidak ada duplicate route.")
        for (m, p), owners in sorted(rt_dup.items()):
            msg, loc = describe_duplicate(m, p, owners)
            rep.add("HIGH", "DUP_ROUTE", msg, loc)
        # Kandidat AST yang TERBUKTI bukan duplikat (prefix router berbeda) tetap
        # dilaporkan INFO — supaya hilangnya 5 "HIGH" bisa diaudit, bukan misterius.
        rt_keys = set(rt_dup.keys())
        for (m, p), locs in sorted(dup.items()):
            if (m, p) not in rt_keys:
                rep.add("INFO", "DUP_ROUTE_FALSE_POSITIVE",
                        f"{m} {p} terlihat duplikat di level dekorator, tetapi runtime "
                        f"membuktikan path akhirnya BERBEDA (prefix router) — bukan temuan",
                        "; ".join(locs[:4]))
    else:
        # Fallback jujur: beri tahu bahwa hasilnya BUKAN ground truth.
        print("  [WARN] CHECK A — tabel route runtime tak bisa dimuat; "
              "jatuh ke AST dekorator (bisa false positive karena prefix router).")
        if not dup:
            print(f"  [OK  ] CHECK A — tidak ada duplicate route ({len(exact_seen)} route unik).")
        for (m, p), locs in sorted(dup.items()):
            rep.add("WARN", "DUP_ROUTE_AST_ONLY",
                    f"{m} {p} didefinisikan {len(locs)}x di level dekorator — "
                    f"BELUM diverifikasi ke runtime (prefix router bisa membedakannya)",
                    "; ".join(locs[:4]))

    # ─── sumber route autoritatif utk CHECK B/C ───
    oapi = openapi_shapes()
    be_shapes = oapi if oapi is not None else ast_shapes
    src_label = "OpenAPI runtime" if oapi is not None else "AST (backend mati)"
    # FASE 20 — WebSocket tak pernah ada di OpenAPI ⇒ harus ditambahkan dari
    # sumber, kalau tidak setiap `new WebSocket()` di FE jadi false positive.
    ws_shapes = websocket_shapes()
    be_shapes = set(be_shapes) | ws_shapes
    be_seglists = [_segs(s) for s in be_shapes]
    print(f"  [INFO] sumber route BE utk CHECK B/C: {src_label} "
          f"({len(be_shapes)} shape, termasuk {len(ws_shapes)} WebSocket).")

    # ─── CHECK B: FE call -> route exists (WARN / triage) ───
    calls = fe_calls()
    seen = set()
    dead = 0
    base_prefix = 0
    for shape, raw, src in calls:
        # buang query-string & artefak template setelah spasi/backslash
        shape = shape.split("?")[0]
        if shape in seen:
            continue
        seen.add(shape)
        if shape in be_shapes:
            continue
        fe_seg = _segs(shape)
        if any(_seg_match(fe_seg, bs) for bs in be_seglists):
            continue
        # FASE 20 — KELAS FALSE POSITIVE: deklarasi BASE, bukan panggilan.
        # Pola umum: `const BASE = `${API}/api/finance/petty-cash`;` lalu dipakai
        # sebagai `${BASE}/funds`. Template `${BASE}/funds` TIDAK memuat "/api/"
        # sehingga tak pernah terlihat oleh `fe_calls()`; yang terlihat hanya
        # konstanta BASE-nya, yang memang bukan endpoint. Ditandai INFO agar
        # tidak mencemari daftar triase 404 yang sesungguhnya.
        if any(b == shape or b.startswith(shape + "/") for b in be_shapes):
            base_prefix += 1
            rep.add("INFO", "FE_BASE_PREFIX",
                    f"`{shape}` bukan endpoint melainkan PREFIX/konstanta BASE "
                    f"(ada route backend di bawahnya) — bukan temuan",
                    f"{src}")
            continue
        dead += 1
        rep.add("WARN", "FE_DEAD_CALL",
                f"FE memanggil `{shape}` — tak cocok route backend (triase: dihapus/typo atau path dinamis)",
                f"{src}")
    if dead == 0:
        print(f"  [OK  ] CHECK B — {len(seen)} shape API FE unik semua cocok route backend.")
    else:
        print(f"  [WARN] CHECK B — {dead} shape FE perlu triase "
              f"({base_prefix} konstanta BASE dikecualikan; WARN = tak mem-blok).")

    # ─── CHECK C: orphan BE (informational) ───
    fe_shapes = {c[0].split("?")[0] for c in calls}
    fe_seglists = [_segs(s) for s in fe_shapes]
    orphan = []
    for s in sorted(be_shapes):
        bs = _segs(s)
        if s in fe_shapes or any(_seg_match(fs, bs) for fs in fe_seglists):
            continue
        orphan.append(s)
    print(f"  [INFO] CHECK C — {len(orphan)} shape route backend tak dipanggil FE (kandidat dead/hidden).")
    for s in orphan[:10]:
        rep.add("INFO", "ORPHAN_BE", s)

    # ─── CHECK D: ORPHAN HANDLER (dekorator hilang) → HIGH ───
    # FASE 14 — kelas bug yang LOLOS dari semua pemeriksa yang ada:
    # fungsi yang JELAS ditulis sebagai endpoint (parameter `Request`, memanggil
    # `require_auth`, di antara endpoint lain) tetapi **dekoratornya hilang**.
    # FastAPI tidak mendaftarkannya ⇒ fitur hilang DIAM-DIAM, dan karena tidak ada
    # route-nya, pemeriksa duplikat/kontrak mana pun tidak punya apa pun untuk dilihat.
    # Ditemukan nyata: `rahaza_production.update_assignment` (PUT /line-assignments/{aid})
    # — saudaranya create & delete terdaftar, update-nya tidak.
    orphan_handlers = find_orphan_handlers()
    if not orphan_handlers:
        print("  [OK  ] CHECK D — tidak ada handler tanpa dekorator (fungsi 'endpoint' yatim).")
    else:
        print(f"  [HIGH] CHECK D — {len(orphan_handlers)} handler tampak endpoint tapi TIDAK terdaftar.")
    for h in orphan_handlers:
        rep.add("HIGH", "ORPHAN_HANDLER",
                f"`{h['func']}()` bergaya endpoint (param Request{', auth' if h['auth'] else ''}"
                f"{', diapit endpoint lain' if h['sandwiched'] else ''}) tetapi TIDAK punya "
                f"dekorator route — FastAPI tidak mendaftarkannya, fitur hilang diam-diam",
                f"{h['file']}:{h['line']}")

    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
