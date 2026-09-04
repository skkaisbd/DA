#!/usr/bin/env python3
"""
audit_testids.py -- Static Auditor data-testid untuk React (DA37 ERP doc toolchain)
====================================================================================
Tujuan: MENCEGAH bug testabilitas DOM secara proaktif SEBELUM sampai ke E2E/testing
agent. Dua bug historis yang ingin dicegah script ini:
  - PD-BUG-001: DUA komponen memakai `data-testid="production-dashboard"` yang sama
                -> selector ambigu (duplikat lintas-file).
  - BDL-BUG-001: komponen wrapper (`<Modal>`) TIDAK meneruskan `data-testid` ke DOM
                -> testid ada di JSX tapi tak pernah muncul di DOM (prop tak diteruskan).

Pemakaian:
    # audit berdasarkan moduleId (crawl pohon komponen dari registry)
    python3 scripts/docgen/audit_testids.py --module-id prod-wizard prod-simple-input

    # audit file eksplisit
    python3 scripts/docgen/audit_testids.py --file frontend/src/components/erp/X.jsx

    # gabungan + mode strict (WARN interaktif-tanpa-testid ikut menggagalkan)
    python3 scripts/docgen/audit_testids.py --module-id prod-wizard --strict

Aturan (exit != 0 bila ada FAIL):
  A1 (FAIL)  Duplikat LINTAS-FILE: satu literal testid statik muncul di >= 2 file
             berbeda dalam scope -> selector ambigu (pola PD-BUG-001).
  A2 (WARN)  Duplikat DALAM-FILE: literal testid statik berulang >= 2x di file yang
             sama (bisa sah utk 2 cabang render; tetap ditandai utk ditinjau).
  A3 (WARN)  Prop-forwarding: komponen wrapper lokal menerima prop `data-testid`/
             `testId` TAPI tidak pernah merender atribut `data-testid=` di DOM
             (pola BDL-BUG-001).
  A4 (WARN)  Elemen interaktif TANPA data-testid (button/input/select/textarea/
             a[href]/Button/Input/Select/Checkbox/Switch/IconButton).

Dependency: hanya Python stdlib + extract_module.py (di direktori yang sama).
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path

# --- pakai ulang crawler & scanner dari extract_module.py ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_module as EM  # noqa: E402

REPO_ROOT = EM.REPO_ROOT
FRONTEND_SRC = EM.FRONTEND_SRC
ERP_DIR = EM.ERP_DIR


# elemen interaktif yang "sepatutnya" punya data-testid (untuk A4)
INTERACTIVE_TAG_RE = re.compile(
    r"<\s*(button|input|select|textarea|a|Button|Input|Select|Textarea|"
    r"Checkbox|Switch|IconButton|RadioGroup|Toggle)\b"
)
# prop data-testid / testId yang DITERIMA sebuah komponen (untuk A3)
PROP_RECEIVES_RE = re.compile(r"""(?:data-testid|['"]data-testid['"]|\btestId\b)""")
# apakah file benar-benar MERENDER atribut data-testid di DOM
RENDERS_TESTID_RE = re.compile(r"data-testid\s*=")


class Report:
    def __init__(self):
        self.rows = []

    def add(self, lvl, code, title, detail=""):
        self.rows.append((lvl, code, title, detail))

    def fails(self):
        return [r for r in self.rows if r[0] == "FAIL"]

    def warns(self):
        return [r for r in self.rows if r[0] == "WARN"]

    def render(self):
        icon = {"PASS": "[ OK ]", "FAIL": "[FAIL]", "WARN": "[WARN]"}
        for lvl, code, title, detail in self.rows:
            print(f"{icon[lvl]} {code}  {title}")
            for line in (detail.splitlines() if detail else []):
                print(f"         {line}")


def collect_files(module_ids, files, include_ui):
    """Kumpulkan set file yang akan diaudit (absolut, dedup, urut)."""
    collected: dict[str, str] = {}  # path -> kind

    for mid in module_ids or []:
        comp_file, _name, info = EM.find_component_file(mid)
        if not comp_file:
            print(f"[audit] WARNING: moduleId '{mid}' gagal resolusi: {info.get('error')}")
            continue
        crawled = EM.crawl(comp_file)
        for cur in crawled["order"]:
            d = crawled["visited"][str(cur)]
            kind = d["kind"]
            if kind == "ui" and not include_ui:
                continue
            collected[str(cur)] = kind

    for f in files or []:
        p = (REPO_ROOT / f).resolve() if not os.path.isabs(f) else Path(f)
        if p.is_file():
            collected[str(p)] = EM.classify(p)
        else:
            print(f"[audit] WARNING: file '{f}' tidak ditemukan.")

    return collected


def scan_testids(path: Path):
    """Ambil data-testid (statik & dinamis) + line, pakai scanner extract_module."""
    d = EM.scan_file(path)
    return d["testids"]


def main():
    ap = argparse.ArgumentParser(description="Static auditor data-testid React (DA37 ERP)")
    ap.add_argument("--module-id", nargs="*", default=[], help="satu/lebih moduleId (crawl dari registry)")
    ap.add_argument("--file", nargs="*", default=[], help="file .jsx/.js eksplisit (relatif ke repo)")
    ap.add_argument("--include-ui", action="store_true", help="ikutkan komponen ui/ (default: diabaikan)")
    ap.add_argument("--strict", action="store_true", help="WARN A4 (interaktif tanpa testid) ikut menggagalkan")
    ap.add_argument("--allow", nargs="*", default=[], help="literal testid yang diizinkan duplikat lintas-file")
    args = ap.parse_args()

    if not args.module_id and not args.file:
        print("[audit] FATAL: berikan --module-id dan/atau --file.")
        return 2

    files = collect_files(args.module_id, args.file, args.include_ui)
    if not files:
        print("[audit] FATAL: tidak ada file untuk diaudit.")
        return 2

    allow = set(args.allow)

    print("=" * 78)
    print(" AUDIT data-testid  |  DA37 ERP")
    print(f" scope    : {len(files)} file (erp{'+ui' if args.include_ui else ''})")
    if args.module_id:
        print(f" modules  : {', '.join(args.module_id)}")
    print("=" * 78)

    # index: literal statik -> [(file, line)]
    static_index: dict[str, list] = {}
    per_file_static: dict[str, dict] = {}    # file -> {literal: count}
    interactive_missing: dict[str, int] = {}
    forwarding_issues = []

    for fpath_s, kind in sorted(files.items()):
        fpath = Path(fpath_s)
        rel = EM.rel(fpath)
        testids = scan_testids(fpath)
        # kumpulkan literal statik
        seen_in_file: dict[str, int] = {}
        for t in testids:
            if t.get("dynamic"):
                continue
            lit = t["raw"].strip()
            if not lit:
                continue
            static_index.setdefault(lit, []).append((rel, t["line"]))
            seen_in_file[lit] = seen_in_file.get(lit, 0) + 1
        per_file_static[rel] = seen_in_file

        # A3: prop-forwarding (hanya file erp/lib, bukan ui primitives)
        raw_text = EM.read(fpath)
        text = EM.strip_comments_js(raw_text)
        receives = bool(PROP_RECEIVES_RE.search(text)) and (
            "props" in text or "data-testid" in text or "testId" in text
        )
        # heuristik: file yang MENERIMA prop testid via destructuring/params
        receives_prop = bool(re.search(
            r"""(\{[^}]*\btestId\b[^}]*\}|['"]data-testid['"]\s*:|\bprops\.testId\b|"""
            r"""\bprops\[['"]data-testid['"]\])""", text))
        renders = bool(RENDERS_TESTID_RE.search(text))
        if receives_prop and not renders:
            forwarding_issues.append(rel)

        # A4: elemen interaktif tanpa data-testid (per-tag, cek baris)
        miss = 0
        for m in INTERACTIVE_TAG_RE.finditer(text):
            start = m.start()
            # ambil blok tag sampai '>' terdekat (cukup untuk cek atribut testid)
            end = text.find(">", start)
            tag_block = text[start: end + 1 if end != -1 else start + 200]
            if "data-testid" not in tag_block:
                miss += 1
        if miss:
            interactive_missing[rel] = miss

    rep = Report()

    # A1 duplikat lintas-file
    cross = {lit: locs for lit, locs in static_index.items()
             if len({f for f, _ in locs}) >= 2 and lit not in allow}
    if cross:
        detail = []
        for lit, locs in sorted(cross.items()):
            detail.append(f"'{lit}' di {len({f for f,_ in locs})} file:")
            for f, ln in locs:
                detail.append(f"    - {f}:{ln}")
        rep.add("FAIL", "A1", f"Duplikat testid LINTAS-FILE ({len(cross)})", "\n".join(detail))
    else:
        rep.add("PASS", "A1", "Tidak ada duplikat testid lintas-file")

    # A2 duplikat dalam-file
    within = []
    for f, counts in per_file_static.items():
        for lit, c in counts.items():
            if c >= 2:
                within.append(f"{f}: '{lit}' x{c}")
    if within:
        rep.add("WARN", "A2", f"Duplikat testid DALAM-FILE ({len(within)})", "\n- ".join([""] + within).strip())
    else:
        rep.add("PASS", "A2", "Tidak ada duplikat testid dalam-file")

    # A3 prop-forwarding
    if forwarding_issues:
        rep.add("WARN", "A3", f"Kemungkinan testid tak diteruskan ({len(forwarding_issues)})",
                "\n- ".join([""] + forwarding_issues).strip())
    else:
        rep.add("PASS", "A3", "Prop-forwarding data-testid aman")

    # A4 interaktif tanpa testid
    if interactive_missing:
        detail = [f"{f}: {n} elemen" for f, n in sorted(interactive_missing.items())]
        lvl = "FAIL" if args.strict else "WARN"
        rep.add(lvl, "A4", f"Elemen interaktif tanpa data-testid ({sum(interactive_missing.values())})",
                "\n- ".join([""] + detail).strip())
    else:
        rep.add("PASS", "A4", "Semua elemen interaktif memiliki data-testid")

    rep.render()
    print("-" * 78)
    nf = len(rep.fails()); nw = len(rep.warns())
    npass = len([r for r in rep.rows if r[0] == "PASS"])
    n_static = len(static_index)
    print(f" testid statik unik: {n_static} · file: {len(files)}")
    print(f" HASIL: {npass} PASS · {nw} WARN · {nf} FAIL")
    if nf == 0:
        print(" STATUS: ✅ LULUS — tidak ada blocker testabilitas.")
        return 0
    print(" STATUS: ❌ GAGAL — perbaiki FAIL (duplikat lintas-file / strict).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
