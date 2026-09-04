"""gr_common.py — Pustaka bersama ekosistem guardrails CV. Dewi Aditya ERP.

Menyediakan (READ-ONLY, tidak memodifikasi kode/DB):
  • Warna terminal + path proyek (ROOT/BACKEND/ROUTES_DIR/FE_SRC/REPORT_DIR)
  • load_env() — baca backend/.env (MONGO_URL, DB_NAME, JWT_SECRET, dst)
  • Ekstraksi route backend via AST + resolusi prefix APIRouter -> all_routes()
  • Ekstraksi panggilan API frontend (axios/fetch `${API}/api/...`) -> fe_calls()
  • login() — helper login admin (urllib, tanpa dependensi tambahan)
  • Finding + Report — akumulator temuan + penulis laporan JSON & Markdown
    ke test_reports/guardrails/<gate>.json

Dipakai oleh semua skrip di scripts/preflight, scripts/guardrails, scripts/meta.
Konvensi: exit 0 = lolos (untuk severity yang MEMBLOKIR), !=0 = ada pelanggaran blok.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ─── Path proyek ───
ROOT = Path(__file__).resolve().parent.parent.parent  # /app
BACKEND = ROOT / "backend"
ROUTES_DIR = BACKEND / "routes"
FE_SRC = ROOT / "frontend" / "src"
REPORT_DIR = ROOT / "test_reports" / "guardrails"

# ─── Warna ───
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# ─── Konfigurasi runtime ───
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@garment.com")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Admin@123")
METHODS = {"get", "post", "put", "patch", "delete"}
MUT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SEV_ORDER = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3, "WARN": 4, "INFO": 5}


def load_env():
    """Muat backend/.env agar MONGO_URL/DB_NAME tersedia."""
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    except Exception:
        pass


def api_base() -> str:
    return os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")


def db_handle():
    """Sync PyMongo handle ke DB aplikasi (butuh MONGO_URL di env)."""
    from pymongo import MongoClient
    load_env()
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]


# ═══════════════ EKSTRAKSI ROUTE BACKEND (AST) ═══════════════
def iter_route_files():
    """Yield semua file router AKTIF (skip _archive, __pycache__, *.old, *_backup)."""
    for p in sorted(ROUTES_DIR.rglob("*.py")):
        s = str(p)
        if "__pycache__" in s or "_archive" in s:
            continue
        low = p.name.lower()
        if low.endswith((".old", ".pre-refactor-backup")) or "_backup" in low or low == "__init__.py":
            continue
        yield p


def _prefix_of(tree) -> str:
    """Cari prefix pada `router = APIRouter(prefix=\"...\")`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if fname == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return kw.value.value or ""
    return ""


def extract_routes(path):
    """[(METHOD, full_path, func_name, line_start, line_end)] untuk satu file."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    pref = _prefix_of(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            attr = dec.func.attr.lower()
            obj = dec.func.value
            objname = obj.id if isinstance(obj, ast.Name) else ""
            if objname not in ("router", "api", "app") or attr not in METHODS:
                continue
            rpath = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else ""
            start = node.body[0].lineno if node.body else node.lineno
            end = node.end_lineno or start
            out.append((attr.upper(), pref + (rpath or ""), node.name, start, end))
    return out


def all_routes():
    """Semua route backend terdaftar: list of dict."""
    routes = []
    for p in iter_route_files():
        for m, path, fn, s, e in extract_routes(p):
            routes.append({
                "method": m, "path": path, "func": fn,
                "file": str(p.relative_to(BACKEND)), "line": s, "line_end": e,
            })
    return routes


def norm_path(path: str) -> str:
    """Normalisasi path -> shape: buang query, {x}/${x} -> {}, buang trailing slash."""
    p = (path or "").split("?")[0]
    p = re.sub(r"\$\{[^}]+\}", "{}", p)   # ${id}
    p = re.sub(r"\{[^}]+\}", "{}", p)     # {id}
    p = re.sub(r"/{2,}", "/", p)
    p = p.rstrip("/")
    return p or "/"


# ═══════════════ EKSTRAKSI PANGGILAN API FRONTEND ═══════════════
_TMPL_RE = re.compile(r"`([^`]*)`")
# FASE 20 — Komentar HARUS dibuang sebelum mencari template literal.
# Alasannya nyata: menulis dokumentasi seperti
#     // dulu `/api/rahaza/master/employees` (404 senyap) → sekarang ...
# membuat gate kontrak MELAPORKAN path yang justru sudah diperbaiki, sebab path
# itu masih tertulis (di dalam backtick) pada komentar. Guard yang menghukum
# tindakan mendokumentasikan perbaikan akan mendorong orang berhenti memberi
# komentar — jadi komentar dinetralkan lebih dulu, bukan dilarang.
_LINE_COMMENT_RE = re.compile(r"(?m)^([^\n\"'`]*?)//.*$")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _strip_js_comments(text: str) -> str:
    """Hapus komentar /*...*/ dan // ... TANPA mengubah jumlah baris.

    Nomor baris dipertahankan (komentar diganti spasi) supaya laporan tetap
    menunjuk baris yang benar. Baris `//` hanya dipotong bila sebelum `//` tidak
    ada tanda kutip/backtick — supaya URL berisi `//` (mis. `https://`) dan
    string yang memuat `//` tidak ikut terpotong.
    """
    text = _BLOCK_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _LINE_COMMENT_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)


def fe_calls():
    """[(norm_shape, raw, srcfile)] untuk tiap template string FE yang memuat /api/."""
    calls = []
    for f in list(FE_SRC.rglob("*.jsx")) + list(FE_SRC.rglob("*.js")):
        if "node_modules" in str(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        text = _strip_js_comments(text)
        for m in _TMPL_RE.finditer(text):
            lit = m.group(1)
            idx = lit.find("/api/")
            if idx == -1:
                continue
            raw = lit[idx:]
            calls.append((norm_path(raw), raw, str(f.relative_to(FE_SRC))))
    return calls


# ═══════════════ LOGIN HELPER (urllib) ═══════════════
def http(method, path, token=None, body=None, timeout=30):
    """Return (status_code, text). status -1 = error transport.

    FASE 19: `e.read()` di cabang HTTPError DULU tidak dilindungi. Bila koneksi
    time-out SAAT MEMBACA body error, `TimeoutError` naik keluar dari fungsi ini
    dan — karena `audit_endpoint_sweep.py` memanggilnya di dalam ThreadPool —
    MEROBOHKAN seluruh sweep 2115 endpoint karena satu endpoint lambat.
    Alat audit yang mati karena satu request flaky tidak bisa dipercaya, jadi
    status HTTP tetap dikembalikan walau body-nya gagal dibaca.
    """
    url = api_base() + "/api" + path if not path.startswith("/api") else api_base() + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                return resp.status, resp.read(4000).decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001 — status sudah diketahui, body opsional
                return resp.status, f"<body tak terbaca: {e}>"
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(4000).decode("utf-8", "replace")
        except Exception as inner:  # noqa: BLE001
            return e.code, f"<body error tak terbaca: {inner}>"
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def login(email=None, password=None):
    """Login admin -> token, atau None bila backend/seed belum siap."""
    st, txt = http("POST", "/auth/login",
                   body={"email": email or ADMIN_EMAIL, "password": password or ADMIN_PASS})
    if st != 200:
        return None
    try:
        return json.loads(txt).get("token")
    except Exception:
        return None


def backend_up() -> bool:
    st, _ = http("GET", "/health", timeout=5)
    return 0 <= st < 500


def test_doc_number(key: str, token=None, band: int = 9000) -> str:
    """Nomor dokumen UJI yang MENGIKUTI pola resmi jenis dokumen `key`.

    FASE G (2026-08-16): sejak nomor MANUAL wajib mengikuti polanya
    (`core/doc_number_policy.py`), gate tidak boleh lagi mengarang nomor seperti
    `__CMTOVTEST__-PO-9F2A1B` — nomor itu ditolak backend, dan gate yang gagal
    karena aturan yang BENAR hanya mengajari orang untuk mematikan aturannya.

    Nomor uji diambil dari pita 9xxx supaya:
      (a) tetap sah menurut pola yang sedang disetel owner (diambil dari
          `/api/doc-number-policy`, jadi ikut berubah bila formatnya diubah),
      (b) TIDAK menghabiskan nomor urut resmi — mode manual tidak menyentuh
          counter, sehingga dokumen asli tidak berlubang nomornya,
      (c) mudah dikenali kalau ada sisa data uji yang lupa dihapus.
    """
    import random
    st, txt = http("GET", f"/doc-number-policy?key={key}", token or login())
    sample = ""
    if st == 200:
        try:
            sample = (json.loads(txt) or {}).get("contoh") or ""
        except Exception:  # noqa: BLE001
            sample = ""
    m = re.search(r"(\d+)\s*$", sample)
    if not m:
        return sample or f"UJI-{int(time.time())}"
    width = len(m.group(1))
    return sample[:m.start(1)] + str(band + random.randint(0, 999)).zfill(width)[-width:]


# ═══════════════ MODEL TEMUAN + LAPORAN ═══════════════
@dataclass
class Finding:
    sev: str            # CRIT/HIGH/MED/LOW/WARN/INFO
    code: str           # kode singkat, mis. NO_AUTH
    msg: str
    loc: str = ""


class Report:
    """Akumulator temuan + penulis laporan. block_sev = severity yang memblokir."""

    def __init__(self, gate: str, title: str, block_sev=("CRIT", "HIGH")):
        self.gate = gate
        self.title = title
        self.block_sev = set(block_sev)
        self.findings: list[Finding] = []
        self.checked = 0
        self.t0 = time.time()
        print(f"\n{B}{'='*66}{X}\n  {C}{gate}{X} — {title}\n{B}{'='*66}{X}")

    def bump(self, n: int = 1):
        self.checked += n

    def add(self, sev: str, code: str, msg: str, loc: str = ""):
        self.findings.append(Finding(sev, code, msg, loc))
        col = {"CRIT": R, "HIGH": R, "MED": Y, "LOW": Y, "WARN": Y, "INFO": C}.get(sev, Y)
        print(f"    {col}[{sev:4}]{X} {code}: {msg}" + (f"  {col}@ {loc}{X}" if loc else ""))

    def _counts(self):
        c = {}
        for f in self.findings:
            c[f.sev] = c.get(f.sev, 0) + 1
        return c

    def n_blocking(self) -> int:
        return sum(1 for f in self.findings if f.sev in self.block_sev)

    def write(self):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "gate": self.gate, "title": self.title,
            "checked": self.checked,
            "counts": self._counts(),
            "blocking": self.n_blocking(),
            "block_sev": sorted(self.block_sev),
            "duration_s": round(time.time() - self.t0, 2),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "findings": [asdict(f) for f in sorted(
                self.findings, key=lambda x: SEV_ORDER.get(x.sev, 9))],
        }
        (REPORT_DIR / f"{self.gate}.json").write_text(json.dumps(payload, indent=2))
        return payload

    def finish(self) -> int:
        self.write()
        counts = self._counts()
        parts = " | ".join(f"{k} {v}" for k, v in sorted(counts.items(),
                            key=lambda kv: SEV_ORDER.get(kv[0], 9))) or "0 temuan"
        blocking = self.n_blocking()
        print(f"\n{B}{'-'*66}{X}")
        print(f"  {self.gate}: {self.checked} diperiksa — {parts}")
        if blocking:
            print(f"  {R}{B}✗ {self.gate} MERAH — {blocking} pelanggaran blok "
                  f"({'/'.join(sorted(self.block_sev))}).{X}\n")
            return 1
        print(f"  {G}{B}✓ {self.gate} HIJAU — 0 pelanggaran blok "
              f"(WARN/MED/LOW = laporan saja).{X}\n")
        return 0
