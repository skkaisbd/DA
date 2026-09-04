#!/usr/bin/env python3
"""
validate_module.py  --  Automated Definition-of-Done Gate (DA37 ERP doc toolchain)
==================================================================================
Ini adalah "FORCING FUNCTION": mengubah standar kualitatif (01_DEEP_STANDARD)
menjadi aturan yang DICEK MESIN. Sebuah dokumen modul TIDAK BOLEH dinyatakan
"Done" sebelum skrip ini keluar dengan exit code 0.

Cara pakai:
    python3 scripts/docgen/validate_module.py --module-id prod-orders
    python3 scripts/docgen/validate_module.py --module-id prod-orders --doc docs/user-guide/produksi/prod-orders.md

Aturan yang dipaksakan (ringkas):
  C1  Struktur section wajib ada (Metadata, Bagian A/B/C, Peta Komponen,
      Inventaris Elemen, Katalog Endpoint, State Machine, Uji).
  C2  Diagram wajib: >=1 stateDiagram-v2 dan >=1 diagram alur (flowchart/sequence).
  C3  Coverage endpoint: SEMUA endpoint (verified) di manifest muncul di dokumen.
  C4  Anti-halusinasi endpoint: SEMUA /api di dokumen ada di tabel route backend.
  C5  Coverage komponen: SEMUA komponen erp di manifest disebut di dokumen.
  C6  Coverage data-testid: SEMUA testid konkret di manifest disebut di dokumen.
  C7  Bebas-bug: dokumen training TIDAK memuat tag BUG-/OBS- atau section bug.
  C8  Bebas-placeholder: tidak ada <<ISI>>, TODO, TBD, atau "PERLU VERIFIKASI".
  C9  Skor rubrik ada dan >= 95/100.
  C10 (WARN) Konsistensi metadata jumlah endpoint.

Exit code: 0 bila TIDAK ada FAIL; selain itu 1.
Butuh manifest hasil extract_module.py (auto-dijalankan bila belum ada).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "docs" / "user-guide" / "_manifests"
DOC_ROOT = REPO_ROOT / "docs" / "user-guide"
EXTRACTOR = REPO_ROOT / "scripts" / "docgen" / "extract_module.py"

# testid prefix yang di-skip dari coverage (false-positive dari prop passthrough / generik)
TESTID_IGNORE = {"testId", "testid"}

# ---------------------------------------------------------------------------
# util
# ---------------------------------------------------------------------------

def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def norm_endpoint(p: str) -> str:
    """Normalisasi path endpoint agar bisa dicocokkan (FE, doc, BE):
    - buang query string
    - ${...} / {...} -> {}
    - segmen yang tampak seperti ID (uuid/hex/angka panjang) -> {}
    - buang trailing slash
    """
    p = p.split("?")[0].split("#")[0]
    p = re.sub(r"\$\{[^}]*\}", "{}", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    # buang ekspresi template yang TIDAK tertutup di ujung
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


def endpoints_in_text(text: str) -> set[str]:
    out = set()
    for m in API_RE.findall(text):
        if "..." in m or m.strip() == "/api" or m.strip() == "/api/":
            continue
        out.add(norm_endpoint(m))
    return out


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

def load_manifest(module_id: str) -> dict:
    mp = MANIFEST_DIR / f"{module_id}.manifest.json"
    if not mp.is_file():
        print(f"[validate] manifest belum ada, menjalankan extractor untuk '{module_id}'...")
        subprocess.run([sys.executable, str(EXTRACTOR), "--module-id", module_id], check=False)
    if not mp.is_file():
        print(f"[validate] FATAL: manifest {rel(mp)} tetap tidak ada.")
        sys.exit(2)
    return json.loads(mp.read_text(encoding="utf-8"))


def find_doc(module_id: str, doc_arg: str | None) -> Path:
    if doc_arg:
        return Path(doc_arg)
    hits = list(DOC_ROOT.rglob(f"{module_id}.md"))
    hits = [h for h in hits if "_qa" not in h.parts and "_manifests" not in h.parts]
    if not hits:
        print(f"[validate] FATAL: dokumen {module_id}.md tidak ditemukan di {rel(DOC_ROOT)}")
        sys.exit(2)
    return hits[0]


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
class Report:
    def __init__(self):
        self.rows = []  # (level, code, title, detail)

    def add(self, level, code, title, detail=""):
        self.rows.append((level, code, title, detail))

    def fails(self):
        return [r for r in self.rows if r[0] == "FAIL"]

    def render(self):
        icon = {"PASS": "[ OK ]", "FAIL": "[FAIL]", "WARN": "[WARN]"}
        for level, code, title, detail in self.rows:
            print(f"{icon[level]} {code}  {title}")
            if detail:
                for line in detail.splitlines():
                    print(f"         {line}")


def check_structure(doc: str, rep: Report):
    required = {
        "Metadata": r"(?im)^#{1,4}.*metadata",
        "Bagian A (Panduan Pengguna)": r"(?im)bagian a",
        "Bagian B (Lampiran Teknis)": r"(?im)bagian b",
        "Bagian C (Uji)": r"(?im)bagian c",
        "Peta Komponen": r"(?im)peta komponen",
        "Inventaris Elemen": r"(?im)inventaris elemen",
        "Katalog/Referensi Endpoint": r"(?im)(katalog.*endpoint|referensi api|kontrak endpoint)",
        "State Machine": r"(?im)state machine",
        "Test/Uji (scenario/case)": r"(?im)(test\s*case|test\s*scenario|skenario uji|spesifikasi uji)",
    }
    missing = [name for name, pat in required.items() if not re.search(pat, doc)]
    if missing:
        rep.add("FAIL", "C1", "Struktur section wajib", "Section HILANG:\n- " + "\n- ".join(missing))
    else:
        rep.add("PASS", "C1", "Struktur section wajib (9/9 ada)")


def check_diagrams(doc: str, rep: Report):
    has_state = bool(re.search(r"stateDiagram(-v2)?", doc))
    flows = len(re.findall(r"```mermaid", doc))
    has_flow = bool(re.search(r"(flowchart|graph\s+(TD|LR|TB)|sequenceDiagram)", doc))
    if has_state and has_flow:
        rep.add("PASS", "C2", f"Diagram wajib (stateDiagram + flow; total {flows} blok mermaid)")
    else:
        miss = []
        if not has_state:
            miss.append("stateDiagram-v2 tidak ditemukan")
        if not has_flow:
            miss.append("diagram alur (flowchart/graph/sequenceDiagram) tidak ditemukan")
        rep.add("FAIL", "C2", "Diagram wajib", "\n".join(miss))


def check_endpoint_coverage(doc: str, manifest: dict, rep: Report):
    doc_eps = endpoints_in_text(doc)
    verified = [e["path"] for e in manifest["endpoints"]["verified"]]
    missing = [p for p in verified if p not in doc_eps]
    if missing:
        rep.add("FAIL", "C3", f"Coverage endpoint ({len(verified)-len(missing)}/{len(verified)})",
                "Endpoint manifest TIDAK ada di dokumen:\n- " + "\n- ".join(missing))
    else:
        rep.add("PASS", "C3", f"Coverage endpoint ({len(verified)}/{len(verified)} tercakup)")


def check_endpoint_hallucination(doc: str, manifest: dict, rep: Report):
    doc_eps = endpoints_in_text(doc)
    backend = set(manifest["all_backend_paths"])

    def grounded(p: str) -> bool:
        # cocok persis dengan route backend
        if p in backend:
            return True
        # atau merupakan PREFIX router yang sah (mis. '/api/rahaza' -> '/api/rahaza/orders')
        if any(b == p or b.startswith(p + "/") for b in backend):
            return True
        # atau route backend adalah AKHIRAN dari path FE (nested include_router prefix "",
        # mis. FE '/api/rahaza/work-orders/{}/generate-bundles' = '/api/rahaza' + '/work-orders/{}/generate-bundles')
        for b in backend:
            if len(b) > 2 and p != b and p.endswith(b) and p[:-len(b)].startswith("/api"):
                return True
        return False

    halluc = sorted([p for p in doc_eps if not grounded(p)])
    if halluc:
        rep.add("FAIL", "C4", "Anti-halusinasi endpoint",
                "Endpoint di dokumen TANPA route backend (halusinasi?):\n- " + "\n- ".join(halluc))
    else:
        rep.add("PASS", "C4", f"Anti-halusinasi endpoint ({len(doc_eps)} path dokumen semua grounded)")


def check_component_coverage(doc: str, manifest: dict, rep: Report):
    erp = [c["name"] for c in manifest["components"] if c["kind"] == "erp"]
    missing = [n for n in erp if n not in doc]
    if missing:
        rep.add("FAIL", "C5", f"Coverage komponen erp ({len(erp)-len(missing)}/{len(erp)})",
                "Komponen manifest TIDAK disebut di dokumen:\n- " + "\n- ".join(missing))
    else:
        rep.add("PASS", "C5", f"Coverage komponen erp ({len(erp)}/{len(erp)} disebut)")


def check_testid_coverage(doc: str, manifest: dict, rep: Report):
    concrete = []
    for t in manifest["testids"]:
        pfx = t["prefix"]
        if pfx in TESTID_IGNORE:
            continue
        # butuh konkret: mengandung '-' atau bukan dinamis
        if ("-" in pfx) or (not t["dynamic"]):
            concrete.append(pfx)
    missing = [p for p in concrete if p not in doc]
    if missing:
        rep.add("FAIL", "C6", f"Coverage data-testid ({len(concrete)-len(missing)}/{len(concrete)})",
                "testid manifest TIDAK disebut di dokumen:\n- " + "\n- ".join(missing))
    else:
        rep.add("PASS", "C6", f"Coverage data-testid ({len(concrete)}/{len(concrete)} disebut)")


def check_no_bug(doc: str, rep: Report):
    hits = []
    for pat, label in [
        (r"\bBUG-\d+", "tag BUG-xxx"),
        (r"\bOBS-\d+", "tag OBS-xxx"),
        (r"(?im)^#{1,6}.*bug\s*findings", "heading 'Bug Findings'"),
        (r"(?im)^#{1,6}.*bug\s*&", "heading 'Bug &'"),
        (r"(?im)^#{1,6}.*temuan", "heading 'Temuan'"),
        (r"(?im)^#{1,6}.*changelog\s*perbaikan", "heading 'Changelog Perbaikan'"),
    ]:
        found = re.findall(pat, doc)
        if found:
            hits.append(f"{label}: {len(found)} kemunculan")
    if hits:
        rep.add("FAIL", "C7", "Bebas-bug (dokumen training tidak boleh memuat bug)",
                "\n".join(hits) + "\n-> Pindahkan ke docs/user-guide/_qa/<moduleId>_bugs.md")
    else:
        rep.add("PASS", "C7", "Bebas-bug (tidak ada tag/section bug di dokumen training)")


def check_no_placeholder(doc: str, rep: Report):
    hits = []
    for pat in [r"<<\s*ISI", r"<<\s*FILL", r"\bTODO\b", r"\bTBD\b", r"PERLU VERIFIKASI"]:
        n = len(re.findall(pat, doc))
        if n:
            hits.append(f"{pat}: {n}")
    if hits:
        rep.add("FAIL", "C8", "Bebas-placeholder", "Placeholder tersisa:\n- " + "\n- ".join(hits))
    else:
        rep.add("PASS", "C8", "Bebas-placeholder (tidak ada TODO/TBD/PERLU VERIFIKASI)")


def check_rubric(doc: str, rep: Report):
    scores = [int(x) for x in re.findall(r"(\d{1,3})\s*/\s*100", doc)]
    if not scores:
        rep.add("FAIL", "C9", "Skor rubrik", "Tidak menemukan skor 'NN/100' di dokumen")
        return
    best = max(scores)
    if best >= 95:
        rep.add("PASS", "C9", f"Skor rubrik ({best}/100 >= 95)")
    else:
        rep.add("FAIL", "C9", f"Skor rubrik ({best}/100 < 95)", "Naikkan kualitas hingga >=95")


def check_metadata_consistency(doc: str, manifest: dict, rep: Report):
    verified = len(manifest["endpoints"]["verified"])
    m = re.search(r"[Ee]ndpoint[^\n]*?\((\d+)\)", doc)
    if m:
        claimed = int(m.group(1))
        if claimed != verified:
            rep.add("WARN", "C10", "Konsistensi metadata endpoint",
                    f"Dokumen menyebut ({claimed}) path, manifest {verified} path unik verified. "
                    f"(Perbedaan wajar bila dokumen menghitung per-method.)")
        else:
            rep.add("PASS", "C10", f"Konsistensi metadata endpoint ({claimed})")
    else:
        rep.add("WARN", "C10", "Konsistensi metadata endpoint", "Jumlah endpoint tidak dinyatakan eksplisit di metadata")


MIN_DOC_LINES = 800  # kedalaman minimum "SAP-grade" untuk modul mayor


def check_depth(doc: str, rep: Report):
    n = len(doc.splitlines())
    if n >= MIN_DOC_LINES:
        rep.add("PASS", "C11", f"Kedalaman dokumen ({n} baris ≥ {MIN_DOC_LINES})")
    else:
        rep.add("FAIL", "C11", f"Kedalaman dokumen ({n} baris < {MIN_DOC_LINES})",
                "Perdalam dengan konten nyata (kamus field, kontrak endpoint lengkap, "
                "logika/state, sequence, worked example) — bukan padding.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Validator Definition-of-Done dokumen modul DA37 ERP")
    ap.add_argument("--module-id", required=True)
    ap.add_argument("--doc", default=None, help="path dokumen .md (default: cari <id>.md di docs/user-guide)")
    args = ap.parse_args()

    manifest = load_manifest(args.module_id)
    if manifest.get("error"):
        print(f"[validate] FATAL manifest error: {manifest['error']}")
        return 2

    doc_path = find_doc(args.module_id, args.doc)
    doc = doc_path.read_text(encoding="utf-8", errors="ignore")

    print("=" * 78)
    print(f" VALIDATE MODULE DOC  |  moduleId={args.module_id}")
    print(f" doc      : {rel(doc_path)}  ({len(doc.splitlines())} baris)")
    print(f" manifest : {rel(MANIFEST_DIR / (args.module_id + '.manifest.json'))}")
    print("=" * 78)

    rep = Report()
    check_structure(doc, rep)
    check_diagrams(doc, rep)
    check_endpoint_coverage(doc, manifest, rep)
    check_endpoint_hallucination(doc, manifest, rep)
    check_component_coverage(doc, manifest, rep)
    check_testid_coverage(doc, manifest, rep)
    check_no_bug(doc, rep)
    check_no_placeholder(doc, rep)
    check_rubric(doc, rep)
    check_metadata_consistency(doc, manifest, rep)
    check_depth(doc, rep)

    rep.render()
    print("-" * 78)
    n_fail = len(rep.fails())
    n_pass = len([r for r in rep.rows if r[0] == "PASS"])
    n_warn = len([r for r in rep.rows if r[0] == "WARN"])
    print(f" HASIL: {n_pass} PASS · {n_warn} WARN · {n_fail} FAIL")
    if n_fail == 0:
        print(" STATUS: ✅ LULUS — dokumen boleh ditandai 'Done'.")
        return 0
    print(" STATUS: ❌ GAGAL — perbaiki semua FAIL sebelum menandai 'Done'.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
