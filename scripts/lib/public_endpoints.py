"""public_endpoints — SSOT endpoint PUBLIK by-design (FASE 19 / AUDIT-2).

## Kenapa modul ini ada

Sebelumnya daftar "endpoint yang memang boleh diakses tanpa token" ada di DUA
tempat dengan aturan berbeda:

  * `scripts/guardrails/verify_auth_coverage.py` → `PUBLIC_ALLOWLIST` + `PUBLIC_SUBSTR`
    + `PUBLIC_PREFIXES`
  * `scripts/audit_endpoint_sweep.py` → satu regex `PUBLIC` yang berbeda isinya

Akibatnya `GET /api/metrics` LOLOS di guardrail auth (karena tidak ada di
daftarnya ⇒ tak diperiksa? tidak — karena ia memang tidak punya `require_auth`
dan tidak masuk allowlist, ia mestinya merah) tetapi MERAH di endpoint sweep,
sehingga temuannya terlihat seperti bug baru setiap kali sweep dijalankan.

Satu daftar, satu ALASAN per entri, dipakai kedua alat.

## Aturan yang TIDAK boleh dilanggar

1. **Setiap entri WAJIB punya `reason`.** Allowlist tanpa alasan adalah cara
   membungkam temuan (pelajaran FASE 14: `DELEGATED_AUTH_PREFIXES` dihapus
   karena menyembunyikan temuan tanpa membuktikan apa pun).
2. **Entri hanya boleh ada bila endpointnya tidak membocorkan data sensitif.**
   Untuk itu ada `SENSITIVE_KEY_PATTERNS` + `assert_no_sensitive_payload()` yang
   dipakai sentinel: allowlist-nya DIBUKTIKAN aman, bukan dipercaya.
3. **Prefix/substring dipakai hanya untuk kelas endpoint** (webhook, health,
   login, TV display, kunci publik VAPID) — bukan untuk membungkam satu modul.
"""
from __future__ import annotations

import re

#: Path LENGKAP (termasuk prefix) + alasan mengapa boleh tanpa token.
#: Kunci: "METHOD /path".
PUBLIC_ALLOWLIST: dict[str, str] = {
    "POST /api/auth/login": "gerbang otentikasi — mustahil butuh token",
    "POST /api/auth/register": "pendaftaran akun",
    "POST /api/auth/logout": "pembatalan sesi; aman tanpa token",
    "POST /api/auth/forgot-password": "pemulihan sandi (rate-limited)",
    "POST /api/auth/reset-password": "pemulihan sandi via token sekali pakai",
    "GET /api/health": "probe kesehatan untuk ingress/monitoring",
    "GET /api/": "root API — hanya nama service",
    # ── FASE 19 / AUDIT-2 — keputusan user 2026-07-26 ─────────────────────────
    "GET /api/metrics": (
        "endpoint scrape monitoring (Prometheus/Grafana). Hanya AGREGAT: jumlah "
        "dokumen per koleksi + timestamp. Tidak ada PII, tidak ada dokumen mentah, "
        "tidak ada nilai uang. Scraper tidak bisa membawa JWT user. "
        "DIBUKTIKAN aman oleh assert_no_sensitive_payload() di "
        "scripts/verify_fase19_audit.py — bukan sekadar dipercaya."
    ),
}

#: Kelas endpoint publik by-design (substring path).
PUBLIC_SUBSTR: tuple[str, ...] = (
    "/webhook",           # webhook marketplace: auth via HMAC signature (utils/webhook_security.py)
    "/public/",           # aset/halaman publik by-design
    "/health",
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
)

#: Prefix path publik by-design + alasan.
PUBLIC_PREFIXES: dict[str, str] = {
    "/api/tv/": "display lantai produksi (read-only, tanpa data sensitif, tanpa keyboard)",
    "/api/push/vapid": "kunci PUBLIK VAPID web-push — memang harus bisa diambil siapa pun",
}

#: Pola field yang TIDAK BOLEH muncul di respons endpoint publik.
SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    r"password", r"secret", r"token", r"api_?key", r"private",
    r"email", r"phone", r"nik", r"npwp", r"address", r"alamat",
    r"salary", r"gaji", r"bank_account", r"rekening",
)
_SENSITIVE_RE = re.compile("|".join(SENSITIVE_KEY_PATTERNS), re.I)


def is_public(method: str, path: str) -> bool:
    """True bila endpoint ini memang boleh diakses tanpa token."""
    key = f"{(method or '').upper()} {path}"
    if key in PUBLIC_ALLOWLIST:
        return True
    if any(s in path for s in PUBLIC_SUBSTR):
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def reason_for(method: str, path: str) -> str:
    key = f"{(method or '').upper()} {path}"
    if key in PUBLIC_ALLOWLIST:
        return PUBLIC_ALLOWLIST[key]
    for p, why in PUBLIC_PREFIXES.items():
        if path.startswith(p):
            return why
    for s in PUBLIC_SUBSTR:
        if s in path:
            return f"kelas endpoint publik by-design ('{s}')"
    return ""


def find_sensitive_keys(payload, _path: str = "") -> list[str]:
    """Kembalikan daftar jalur field bernama sensitif di dalam payload."""
    hits: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            here = f"{_path}.{k}" if _path else str(k)
            if _SENSITIVE_RE.search(str(k)):
                hits.append(here)
            hits += find_sensitive_keys(v, here)
    elif isinstance(payload, list):
        for i, v in enumerate(payload[:50]):
            hits += find_sensitive_keys(v, f"{_path}[{i}]")
    return hits


def assert_no_sensitive_payload(payload) -> list[str]:
    """Dipakai sentinel: '' aman, selain itu daftar field yang melanggar."""
    return find_sensitive_keys(payload)
