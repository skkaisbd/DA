"""fe_static.py — Pembaca STATIK berkas frontend untuk keperluan guardrail.

Kenapa file ini ada (FASE IA-D, 2026-07-26)
───────────────────────────────────────────
Guard `check_nav_map.py` sebelumnya hanya memeriksa **peta menu** (id ada/tidak di
registry). Ia buta pada dua kelas cacat yang sudah TERBUKTI lolos ke produksi:

  1. **Pintu yang komponennya memanggil endpoint tak ada** (cacat A, 2026-07-26):
     `apiGet('/production-monitoring-v2')` → 404 → `catch → setData([])` → layar
     "Tidak ada data" padahal DB penuh. Gate kontrak (`verify_fe_be_contract.py`)
     TIDAK melihatnya karena ia hanya memindai template string yang memuat literal
     `/api/`, sedangkan wrapper `apiGet()` menambahkan `/api` sendiri
     (lihat `frontend/src/lib/api.js:44`).

  2. **Pintu yang isinya sama persis dengan TAB pintu lain** (cacat C): satu modul
     bisa dibuka dari 2 tempat dengan nama berbeda ⇒ pengguna tak tahu mana yang
     "benar", dan perbaikan cuma kena satu sisi.

Untuk memeriksa keduanya, guard butuh 3 kemampuan baca statik yang dipakai bersama
(README singkat tiap fungsi ada di docstring-nya):

  * `resolve_imports(file)`   — nama komponen → berkas sumbernya (lazy & statik).
  * `api_calls(file)`         — semua path API literal yang dipanggil berkas itu,
                                termasuk lewat wrapper tanpa literal `/api`.
  * `tab_components(file)`    — berkas komponen yang dirender sebagai TAB
                                (pola `HubTabs` maupun `<TabsContent>` biasa).

READ-ONLY: tidak mengeksekusi kode frontend, tidak menyentuh DB.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # /app
FE_SRC = ROOT / "frontend" / "src"

_EXTS = (".jsx", ".js", ".tsx", ".ts")

# ── komentar dinetralkan (tanpa mengubah jumlah baris) ──────────────────────
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT_RE = re.compile(r"(?m)^([^\n\"'`]*?)//.*$")


def strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _LINE_COMMENT_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)


@lru_cache(maxsize=2048)
def read(path: Path) -> str:
    try:
        return strip_comments(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def resolve_module(spec: str, from_file: Path) -> Path | None:
    """Ubah spesifier import ('./engine/X', '@/lib/y') jadi berkas nyata."""
    if not spec:
        return None
    if spec.startswith("@/"):
        base = FE_SRC / spec[2:]
    elif spec.startswith("."):
        base = (Path(from_file).parent / spec).resolve()
    else:
        return None  # paket node_modules — bukan urusan guard ini
    if base.is_file():
        return base
    for ext in _EXTS:
        cand = Path(str(base) + ext)
        if cand.is_file():
            return cand
    for ext in _EXTS:
        cand = base / ("index" + ext)
        if cand.is_file():
            return cand
    return None


_LAZY_RE = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*lazy\(\s*\(\s*\)\s*=>\s*import\(\s*['"]([^'"]+)['"]\s*\)(\s*\.then\([^)]*?default\s*:\s*\w+\.([A-Za-z_$][\w$]*))?""")
_IMPORT_DEFAULT_RE = re.compile(
    r"""(?m)^\s*import\s+([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\})?\s*from\s*['"]([^'"]+)['"]""")
_IMPORT_NAMED_RE = re.compile(
    r"""(?ms)^\s*import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""")


@lru_cache(maxsize=2048)
def resolve_imports(file: Path) -> dict:
    """nama simbol → "berkas::export" (identitas komponen).

    Export ikut dicatat karena SATU berkas bisa mengekspor beberapa komponen berbeda:
    `lazy(() => import('../WMSModule').then(m => ({ default: m.PositionsTab })))` BUKAN
    modul yang sama dengan `WMSModule` default — menyamakan keduanya membuat guard
    NAV-DUPTAB melapor merah palsu (terbukti pada 4 pintu Gudang).
    """
    file = Path(file)
    txt = read(file)
    out: dict[str, str] = {}
    for name, spec, _then, exp in _LAZY_RE.findall(txt):
        p = resolve_module(spec, file)
        if p:
            out[name] = f"{p}::{exp or 'default'}"
    for name, spec in _IMPORT_DEFAULT_RE.findall(txt):
        p = resolve_module(spec, file)
        if p:
            out.setdefault(name, f"{p}::default")
    for names, spec in _IMPORT_NAMED_RE.findall(txt):
        p = resolve_module(spec, file)
        if not p:
            continue
        for raw in names.split(","):
            nm = raw.split(" as ")[-1].strip()
            if nm:
                out.setdefault(nm, f"{p}::{raw.split(' as ')[0].strip()}")
    return out


def comp_path(comp: str) -> Path:
    """Ambil bagian BERKAS dari identitas komponen "berkas::export"."""
    return Path(str(comp).split("::")[0])


# ═══════════════ PANGGILAN API ═══════════════
# wrapper lib/api.js  → apiGet('/x')  == fetch(`${BACKEND}/api/x`)
_WRAPPER_RE = re.compile(
    r"""\bapi(?:Get|Post|Put|Patch|Delete|Fetch|Download|Upload)\s*\(\s*(['"`])([^'"`]+)\1""")
# template literal apa pun yang memuat /api/ (axios/fetch langsung)
_TMPL_RE = re.compile(r"`([^`]*)`")
_QUOTED_API_RE = re.compile(r"""(['"])(/api/[^'"]*)\1""")


def api_calls(file: Path) -> list:
    """[(raw_path, line, kind)] — path API (selalu berawalan /api) yang dipakai berkas ini.

    Menangkap DUA gaya sekaligus:
      · `apiGet('/production-jobs')`      → /api/production-jobs   ← titik buta lama
      · `` fetch(`${API}/api/foo`) ``     → /api/foo

    `kind`:
      'wrapper'  — path UTUH (argumen apiGet/apiPost/…): boleh dihakimi keras.
      'template' — template literal; bisa jadi KONSTANTA BASIS
                   (`const BASE = \`${API}/api/finance/petty-cash\`;` lalu `${BASE}/funds`),
                   jadi pemeriksa harus menerima kecocokan AWALAN. Tanpa pembedaan ini
                   guard melaporkan merah palsu pada tiap modul yang memakai konstanta basis.
    """
    txt = read(Path(file))
    out = []
    for i, line in enumerate(txt.split("\n"), 1):
        for m in _WRAPPER_RE.finditer(line):
            p = m.group(2)
            if not p.startswith("/"):
                continue                      # path dinamis (variabel) — dilewati
            out.append((p if p.startswith("/api") else "/api" + p, i, "wrapper"))
        for m in _TMPL_RE.finditer(line):
            lit = m.group(1)
            idx = lit.find("/api/")
            if idx != -1:
                out.append((lit[idx:], i, "template"))
        for m in _QUOTED_API_RE.finditer(line):
            out.append((m.group(2), i, "template"))
    return out


# ═══════════════ TAB ═══════════════
_HUBTABS_COMPONENT_RE = re.compile(r"Component\s*:\s*([A-Za-z_$][\w$]*)")
_TABSCONTENT_RE = re.compile(r"<TabsContent\b[\s\S]*?</TabsContent>")
_JSX_COMPONENT_RE = re.compile(r"<([A-Z][\w$]*)\b")


def tab_components(file: Path) -> dict:
    """nama komponen → identitas "berkas::export" komponen yang dirender sebagai TAB.

    Dua pola dipakai di repo ini:
      · `HubTabs` generik  → `tabs={[{ key, label, Component: X }]}`
      · Tabs shadcn biasa  → `<TabsContent value="x"><X /></TabsContent>`
    """
    txt = read(Path(file))
    imports = resolve_imports(Path(file))
    found: dict[str, str] = {}
    for name in _HUBTABS_COMPONENT_RE.findall(txt):
        if name in imports:
            found[name] = imports[name]
    for block in _TABSCONTENT_RE.findall(txt):
        for name in _JSX_COMPONENT_RE.findall(block):
            if name in imports:
                found[name] = imports[name]
    return found
