#!/usr/bin/env python3
"""INV-DEADCODE-01 — Handler TERGABUNG: statement mati setelah `return`.

KELAS BUG YANG LOLOS SEMUA GATE SEBELUMNYA (ditemukan FASE 20)
--------------------------------------------------------------
`rahaza_payroll_runs.export_run_excel()` berakhir dengan
`return StreamingResponse(...)`, lalu **31 baris berikutnya masih di dalam fungsi
yang sama**: sebuah handler CSV yang lengkap (`await require_auth`, query Mongo,
`csv.writer`, `return StreamingResponse(media_type="text/csv")`).

Artinya dua endpoint TERGABUNG jadi satu fungsi dan dekorator
`@router.get("/payroll-runs/{run_id}/export")` HILANG. FastAPI tidak pernah
mendaftarkan route CSV-nya, sehingga tombol "Download CSV" di
`RahazaPayrollRunModule` selalu gagal — tanpa error di log, tanpa test merah.

Kenapa gate lain buta:
  · CHECK D (orphan handler) mencari `def` TANPA dekorator → di sini tidak ada
    `def` baru sama sekali, jadi tidak ada yang bisa dilihat.
  · CHECK B (kontrak FE↔BE) hanya bisa bilang "FE memanggil path yang tak ada",
    tanpa tahu implementasinya SUDAH ADA namun tak terjangkau.
  · Linter Python default tidak menandai unreachable code.

─────────────────────────────────────────────────────────────────────────────────
2026-08-07 — CEK KEDUA DITAMBAHKAN: DEKORATOR ROUTE MENGGANTUNG
─────────────────────────────────────────────────────────────────────────────────
Titik buta gate ini SENDIRI (diakui docstring di atas: "tidak ada `def` baru sama
sekali") ternyata punya varian kedua yang JUGA lolos, dan ditemukan di
`routes/rahaza_finance.py`:

    @router.get("/ar-aging")          # ← dekorator MENGGANTUNG, tak ada def di bawahnya


    # ═══════════════════════════════════════════
    # PHASE 9A: BAD DEBT WRITE-OFF
    # ═══════════════════════════════════════════
    @router.post("/ar-invoices/{iid}/write-off-bad-debt")
    async def write_off_bad_debt(iid: str, request: Request):

Python MENUMPUK dekorator yang dipisahkan baris kosong & komentar, jadi
`@router.get("/ar-aging")` menempel ke `write_off_bad_debt`. Dua akibat serius:

  1. `GET /api/rahaza/ar-aging` sebenarnya menjalankan **write-off piutang macet**
     — operasi yang MEMPOSTING JURNAL GL — lewat metode GET. Karena path
     `/ar-aging` tidak punya `{iid}`, FastAPI menjadikan `iid` sebagai query
     parameter WAJIB, sehingga endpoint tampak "rusak / minta iid" alih-alih
     terlihat sebagai salah sambung.
  2. Fungsi `ar_aging()` yang sesungguhnya TIDAK PERNAH terdaftar ⇒ laporan aging
     AR adalah kode mati.

Tanda tangan bug: satu fungsi memegang ≥2 dekorator route yang **TIDAK
berdampingan** (ada baris kosong/komentar di antaranya). Alias yang SENGAJA selalu
ditulis berdampingan:

    @router.get("/a")
    @router.get("/b")
    async def h(): ...

SEVERITY
  HIGH  `return` diikuti statement yang memuat `return` lain ⇒ dua handler
        tergabung / dekorator hilang ⇒ fitur mati diam-diam. MEM-BLOK.
  HIGH  dekorator route menggantung (≥2 dekorator route tidak berdampingan).
        MEM-BLOK.
  INFO  `raise` di awal fungsi lalu badan lama ditinggal ⇒ pola DEPREKASI yang
        SENGAJA (mis. K5 Phase C: `raise HTTPException(410, ...)`). Bukan bug.
  INFO  ≥2 dekorator route BERDAMPINGAN ⇒ alias path yang disengaja.

Usage: cd /app && python scripts/guardrails/verify_unreachable_code.py [--report-only]
       cd /app && python scripts/guardrails/verify_unreachable_code.py --self-test
"""
import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from gr_common import Report, ROOT  # noqa: E402

BACKEND = ROOT / "backend"
SKIP_PARTS = {"__pycache__", "tests", "migrations", "_archive"}
TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _scan_fn(fn, path: Path, out: list):
    """Cari statement setelah terminator DI LEVEL BODY fungsi (bukan dalam if/try)."""
    body = fn.body
    for i, stmt in enumerate(body):
        if not isinstance(stmt, TERMINATORS):
            continue
        rest = [s for s in body[i + 1:] if not isinstance(s, ast.Pass)]
        if not rest:
            continue
        has_return = any(isinstance(s, ast.Return) for s in rest)
        sev = "HIGH" if isinstance(stmt, ast.Return) and has_return else "INFO"
        out.append({
            "sev": sev,
            "file": str(path.relative_to(ROOT)),
            "func": fn.name,
            "func_line": fn.lineno,
            "terminator": type(stmt).__name__,
            "terminator_line": stmt.lineno,
            "from_line": rest[0].lineno,
            "to_line": max(getattr(s, "end_lineno", s.lineno) or s.lineno for s in rest),
            "n": len(rest),
            "has_return": has_return,
        })
        return  # satu temuan per fungsi cukup


# ─── CEK 2: DEKORATOR ROUTE MENGGANTUNG ──────────────────────────────────────
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}
ROUTE_OBJECTS = {"router", "app"}


def _is_route_dec(d) -> bool:
    f = d.func if isinstance(d, ast.Call) else d
    if isinstance(f, ast.Attribute) and f.attr in ROUTE_METHODS:
        base = f.value
        if isinstance(base, ast.Name) and base.id in ROUTE_OBJECTS:
            return True
    return False


def _dec_label(d) -> str:
    f = d.func if isinstance(d, ast.Call) else d
    meth = (f.attr if isinstance(f, ast.Attribute) else "?").upper()
    path = ""
    if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant):
        path = str(d.args[0].value)
    return f"{meth} {path}".strip()


def _scan_dangling_decorators(fn, path: Path, out: list):
    """≥2 dekorator route pada satu fungsi; TIDAK berdampingan ⇒ ada yang menggantung."""
    routes = [d for d in fn.decorator_list if _is_route_dec(d)]
    if len(routes) < 2:
        return
    routes = sorted(routes, key=lambda d: d.lineno)
    gaps = []
    for prev, nxt in zip(routes, routes[1:]):
        prev_end = getattr(prev, "end_lineno", prev.lineno) or prev.lineno
        if nxt.lineno > prev_end + 1:          # ada baris kosong/komentar di antaranya
            gaps.append((prev_end, nxt.lineno))
    out.append({
        "sev": "HIGH" if gaps else "INFO",
        "file": str(path.relative_to(ROOT)),
        "func": fn.name,
        "func_line": fn.lineno,
        "decs": [_dec_label(d) for d in routes],
        "gaps": gaps,
    })


def _self_test() -> int:
    """Buktikan detektor BISA MERAH — penjaga yang tak pernah merah tak bernilai."""
    kasus_bug = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        '@router.get("/menggantung")\n'
        "\n"
        "\n"
        "# komentar pemisah\n"
        '@router.post("/asli/{iid}")\n'
        "async def handler(iid: str):\n"
        "    return {}\n"
        "\n"
        "\n"
        '@router.get("/alias-a")\n'
        '@router.get("/alias-b")\n'
        "async def alias_handler():\n"
        "    return {}\n"
    )
    hits: list = []
    tree = ast.parse(kasus_bug)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_dangling_decorators(node, ROOT / "sintetis.py", hits)
    high = [h for h in hits if h["sev"] == "HIGH"]
    info = [h for h in hits if h["sev"] == "INFO"]
    ok = len(high) == 1 and high[0]["func"] == "handler" and len(info) == 1
    print(f"    self-test: {len(high)} HIGH (harap 1: 'handler'), "
          f"{len(info)} INFO alias berdampingan (harap 1)")
    print("    self-test: " + ("LULUS — detektor terbukti bisa merah, dan alias "
                               "berdampingan TIDAK dianggap bug."
                               if ok else "GAGAL — detektor buta!"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="buktikan detektor dekorator menggantung bisa merah")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    rep = Report(
        "INV-DEADCODE-01",
        "Handler tergabung / kode mati setelah return (dekorator hilang)",
        block_sev=() if args.report_only else ("HIGH",),
    )

    findings: list[dict] = []
    dangling: list[dict] = []
    for py in sorted(BACKEND.rglob("*.py")):
        if any(p in SKIP_PARTS for p in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rep.bump()
                _scan_fn(node, py, findings)
                _scan_dangling_decorators(node, py, dangling)

    for f in sorted(findings, key=lambda x: (x["sev"] != "HIGH", x["file"])):
        where = f"{f['file']}:{f['func_line']} {f['func']}()"
        if f["sev"] == "HIGH":
            rep.add("HIGH", "MERGED_HANDLER",
                    f"{f['terminator']} di baris {f['terminator_line']} membuat baris "
                    f"{f['from_line']}-{f['to_line']} ({f['n']} statement, memuat `return`) "
                    f"TAK TERJANGKAU — kemungkinan endpoint yang kehilangan dekorator",
                    where)
        else:
            rep.add("INFO", "DEPRECATED_BODY",
                    f"{f['terminator']} di baris {f['terminator_line']} → baris "
                    f"{f['from_line']}-{f['to_line']} tak terjangkau (pola deprekasi disengaja)",
                    where)

    for d in sorted(dangling, key=lambda x: (x["sev"] != "HIGH", x["file"])):
        where = f"{d['file']}:{d['func_line']} {d['func']}()"
        if d["sev"] == "HIGH":
            celah = ", ".join(f"baris {a}→{b}" for a, b in d["gaps"])
            rep.add("HIGH", "DANGLING_ROUTE_DEC",
                    f"fungsi ini memegang {len(d['decs'])} dekorator route yang TIDAK "
                    f"berdampingan ({celah}) — {' | '.join(d['decs'])}. Dekorator yang "
                    f"terpisah itu MENGGANTUNG: Python menumpuknya ke fungsi ini, jadi "
                    f"path-nya salah sambung DAN handler aslinya tak pernah terdaftar",
                    where)
        else:
            rep.add("INFO", "ROUTE_ALIAS",
                    f"{len(d['decs'])} dekorator route berdampingan (alias disengaja): "
                    f"{' | '.join(d['decs'])}", where)

    n_high = sum(1 for f in findings if f["sev"] == "HIGH")
    n_dangling = sum(1 for d in dangling if d["sev"] == "HIGH")
    if n_high == 0 and n_dangling == 0:
        print(f"    {rep.checked} fungsi diperiksa — tidak ada handler tergabung "
              f"maupun dekorator route menggantung.")
    else:
        print(f"    {rep.checked} fungsi diperiksa — {n_high} handler tergabung, "
              f"{n_dangling} dekorator route menggantung DITEMUKAN.")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
