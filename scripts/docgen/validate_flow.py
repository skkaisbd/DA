#!/usr/bin/env python3
"""
validate_flow.py -- Definition-of-Done Gate untuk DOKUMEN BERBASIS FLOW (DA37 ERP)
==================================================================================
Strategi v4 (flow-centric): satu dokumen = satu ALUR bisnis kritikal (lintas modul).
Happy-path dibahas mendalam; fitur lain cukup ringkas. Validator ini LEBIH LONGGAR
dari validate_module.py pada CAKUPAN (tidak wajib 100% testid & tidak wajib 100%
endpoint per-modul) — cukup happy-path. TAPI mutu inti tetap dijaga KETAT:
kedalaman minimum >= 800 baris (kualitas SAP-grade), anti-halusinasi, cakupan
endpoint happy-path, dan bukti uji nyata.

Pakai:
    python3 scripts/docgen/validate_flow.py --flow-id alur-produksi-inti

Aturan:
  F1  Struktur section wajib (Metadata, Ikhtisar Alur, Langkah kritikal,
      Kontrak Endpoint, RBAC, Uji, Fitur pendukung ringkas).
  F2  Diagram wajib: >=1 flowchart/graph DAN >=1 sequenceDiagram/stateDiagram.
  F3  Anti-halusinasi: SEMUA /api di dokumen grounded ke route backend.
  F4  Cakupan endpoint kritikal: SEMUA critical_endpoints di flow-spec muncul di doc.
  F5  Bebas-placeholder (TODO/TBD/PERLU VERIFIKASI/<<ISI>>).
  F6  Bebas-bug (tidak ada tag BUG-/OBS- atau heading temuan di materi training).
  F7  Bukti uji: dokumen menyebut skrip uji (flow-spec.test_script) + kata 'PASS'.
  F8  Skor rubrik >= 95/100.
  F9  Kedalaman minimum (>= MIN_FLOW_LINES) — standar SAP-grade dipertahankan.
  F10 (WARN) modules_touched flow-spec disebut di dokumen.

Exit 0 bila tidak ada FAIL.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "docs" / "user-guide" / "_manifests"
FLOW_DIR = REPO_ROOT / "docs" / "user-guide" / "_flows"
DOC_ROOT = REPO_ROOT / "docs" / "user-guide"
MIN_FLOW_LINES = 800

# ---- endpoint utils (selaras dgn validate_module.py) ----
def norm_endpoint(p: str) -> str:
    p = p.split("?")[0].split("#")[0]
    p = re.sub(r"\$\{[^}]*\}", "{}", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    p = re.sub(r"\$?\{[^}]*$", "", p)
    segs = []
    for seg in p.split("/"):
        if re.fullmatch(r"[0-9]+", seg) or re.fullmatch(r"[0-9a-fA-F]{6,}", seg) or \
           re.fullmatch(r"[0-9a-fA-F-]{8,}", seg):
            segs.append("{}")
        else:
            segs.append(seg)
    p = "/".join(segs)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p

API_RE = re.compile(r"/api/[A-Za-z0-9_\-./${}:]+")

def endpoints_in_text(text: str) -> set:
    out = set()
    for m in API_RE.findall(text):
        if "..." in m or m.strip() in ("/api", "/api/"):
            continue
        out.add(norm_endpoint(m))
    return out

def load_all_backend_paths() -> set:
    paths = set()
    for mp in MANIFEST_DIR.glob("*.manifest.json"):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
            for p in d.get("all_backend_paths", []):
                paths.add(p)
        except Exception:
            pass
    return paths

def grounded(p: str, backend: set) -> bool:
    if p in backend:
        return True
    if any(b == p or b.startswith(p + "/") for b in backend):
        return True
    for b in backend:
        if len(b) > 2 and p != b and p.endswith(b) and p[:-len(b)].startswith("/api"):
            return True
    return False

class Report:
    def __init__(self): self.rows = []
    def add(self, lvl, code, title, detail=""): self.rows.append((lvl, code, title, detail))
    def fails(self): return [r for r in self.rows if r[0] == "FAIL"]
    def render(self):
        icon = {"PASS": "[ OK ]", "FAIL": "[FAIL]", "WARN": "[WARN]"}
        for lvl, code, title, detail in self.rows:
            print(f"{icon[lvl]} {code}  {title}")
            for line in (detail.splitlines() if detail else []):
                print(f"         {line}")

def main():
    ap = argparse.ArgumentParser(description="Validator dokumen FLOW DA37 ERP")
    ap.add_argument("--flow-id", required=True)
    ap.add_argument("--doc", default=None)
    args = ap.parse_args()

    spec_path = FLOW_DIR / f"{args.flow_id}.flow.json"
    if not spec_path.is_file():
        print(f"[validate-flow] FATAL: flow-spec {spec_path} tidak ada.")
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    doc_path = Path(args.doc) if args.doc else None
    if not doc_path:
        hits = [h for h in DOC_ROOT.rglob("*.md")
                if args.flow_id in h.stem and "_qa" not in h.parts]
        if not hits:
            print(f"[validate-flow] FATAL: dokumen flow '{args.flow_id}' tidak ditemukan.")
            return 2
        doc_path = sorted(hits, key=lambda p: len(p.stem))[0]
    doc = doc_path.read_text(encoding="utf-8", errors="ignore")

    print("=" * 78)
    print(f" VALIDATE FLOW DOC  |  flowId={args.flow_id}")
    print(f" doc      : {doc_path.relative_to(REPO_ROOT)}  ({len(doc.splitlines())} baris)")
    print(f" flow-spec: {spec_path.relative_to(REPO_ROOT)}")
    print("=" * 78)

    rep = Report()

    # F1 structure
    required = {
        "Metadata": r"(?im)^#{1,4}.*metadata",
        "Ikhtisar Alur": r"(?im)(ikhtisar alur|peta alur|alur kritikal|flow overview)",
        "Langkah kritikal": r"(?im)(langkah kritikal|step-by-step|langkah\s*\d)",
        "Kontrak Endpoint": r"(?im)(kontrak endpoint|katalog.*endpoint|endpoint happy-path)",
        "RBAC": r"(?im)(rbac|hak akses)",
        "Uji": r"(?im)(hasil uji|spesifikasi uji|skenario uji|test scenario)",
        "Fitur pendukung (ringkas)": r"(?im)(fitur pendukung|penjelasan singkat|fitur terkait|fitur lain)",
    }
    miss = [n for n, pat in required.items() if not re.search(pat, doc)]
    rep.add("FAIL" if miss else "PASS", "F1", f"Struktur section ({len(required)-len(miss)}/{len(required)})",
            ("HILANG:\n- " + "\n- ".join(miss)) if miss else "")

    # F2 diagrams
    has_flow = bool(re.search(r"(flowchart|graph\s+(TD|LR|TB))", doc))
    has_seq = bool(re.search(r"(sequenceDiagram|stateDiagram(-v2)?)", doc))
    if has_flow and has_seq:
        rep.add("PASS", "F2", "Diagram wajib (flowchart + sequence/state)")
    else:
        d = []
        if not has_flow: d.append("flowchart/graph tidak ada")
        if not has_seq: d.append("sequenceDiagram/stateDiagram tidak ada")
        rep.add("FAIL", "F2", "Diagram wajib", "\n".join(d))

    # F3 anti-hallucination
    backend = load_all_backend_paths()
    doc_eps = endpoints_in_text(doc)
    halluc = sorted([p for p in doc_eps if not grounded(p, backend)])
    rep.add("FAIL" if halluc else "PASS", "F3",
            f"Anti-halusinasi ({len(doc_eps)-len(halluc)}/{len(doc_eps)} grounded)",
            ("TANPA route backend:\n- " + "\n- ".join(halluc)) if halluc else "")

    # F4 critical endpoint coverage
    crit = [norm_endpoint(e) for e in spec.get("critical_endpoints", [])]
    missing = [e for e in crit if e not in doc_eps]
    rep.add("FAIL" if missing else "PASS", "F4",
            f"Cakupan endpoint kritikal ({len(crit)-len(missing)}/{len(crit)})",
            ("TIDAK ada di dokumen:\n- " + "\n- ".join(missing)) if missing else "")

    # F5 placeholder
    ph = [f"{p}: {len(re.findall(p, doc))}" for p in
          [r"<<\s*ISI", r"<<\s*FILL", r"\bTODO\b", r"\bTBD\b", r"PERLU VERIFIKASI"]
          if re.findall(p, doc)]
    rep.add("FAIL" if ph else "PASS", "F5", "Bebas-placeholder", "\n- ".join(ph))

    # F6 no-bug
    bug = []
    for pat, lab in [(r"\bBUG-\d+", "tag BUG-"), (r"\bOBS-\d+", "tag OBS-"),
                     (r"(?im)^#{1,6}.*temuan", "heading Temuan"),
                     (r"(?im)^#{1,6}.*changelog\s*perbaikan", "heading Changelog Perbaikan")]:
        if re.findall(pat, doc): bug.append(lab)
    rep.add("FAIL" if bug else "PASS", "F6", "Bebas-bug (materi training)",
            (", ".join(bug) + " -> pindahkan ke _qa/") if bug else "")

    # F7 test evidence
    ts = spec.get("test_script", "")
    ts_name = Path(ts).name if ts else ""
    has_ts = bool(ts_name and ts_name in doc)
    has_pass = bool(re.search(r"\bPASS\b", doc))
    if has_ts and has_pass:
        rep.add("PASS", "F7", "Bukti uji (skrip + hasil PASS disebut)")
    else:
        d = []
        if not has_ts: d.append(f"skrip uji '{ts_name}' tidak disebut di dokumen")
        if not has_pass: d.append("kata 'PASS' (hasil uji) tidak ditemukan")
        rep.add("FAIL", "F7", "Bukti uji", "\n".join(d))

    # F8 rubric
    scores = [int(x) for x in re.findall(r"(\d{1,3})\s*/\s*100", doc)]
    if scores and max(scores) >= 95:
        rep.add("PASS", "F8", f"Skor rubrik ({max(scores)}/100 >= 95)")
    else:
        rep.add("FAIL", "F8", f"Skor rubrik ({max(scores) if scores else 'N/A'}/100 < 95)")

    # F9 depth
    n = len(doc.splitlines())
    rep.add("PASS" if n >= MIN_FLOW_LINES else "FAIL", "F9",
            f"Kedalaman ({n} baris {'>=' if n>=MIN_FLOW_LINES else '<'} {MIN_FLOW_LINES})")

    # F10 modules touched (WARN)
    mods = spec.get("modules_touched", [])
    mmiss = [m for m in mods if m not in doc]
    rep.add("WARN" if mmiss else "PASS", "F10",
            f"Modul tersentuh disebut ({len(mods)-len(mmiss)}/{len(mods)})",
            ("belum disebut: " + ", ".join(mmiss)) if mmiss else "")

    rep.render()
    print("-" * 78)
    nf = len(rep.fails()); npass = len([r for r in rep.rows if r[0] == "PASS"]); nw = len([r for r in rep.rows if r[0] == "WARN"])
    print(f" HASIL: {npass} PASS · {nw} WARN · {nf} FAIL")
    if nf == 0:
        print(" STATUS: ✅ LULUS — dokumen flow boleh ditandai 'Done'.")
        return 0
    print(" STATUS: ❌ GAGAL — perbaiki semua FAIL.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
