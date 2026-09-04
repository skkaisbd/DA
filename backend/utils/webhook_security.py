"""webhook_security — SSOT verifikasi HMAC webhook marketplace (FASE 19 / AUDIT-2).

## Kenapa modul ini ada

`routes/marketing_webhooks.py` MENDEKLARASIKAN header signature
(`x-tokopedia-hmac-signature`, `x-shopee-signature`) tetapi **tidak pernah
memverifikasinya**. Akibatnya siapa pun di internet bisa menulis ke koleksi
`marketing_webhook_events` **dan** `marketing_orders` tanpa kredensial apa pun.
`scripts/audit_endpoint_sweep.py` menandainya sebagai **WRITE-NOAUTH** — tulis
tanpa auth, 3 endpoint sekaligus.

Webhook TIDAK BISA memakai JWT (pengirimnya marketplace, bukan browser user),
jadi otentikasinya adalah **HMAC atas raw body** dengan secret yang hanya
diketahui kita dan platform.

## 4 prinsip yang tidak boleh dilanggar

1. **FAIL-CLOSED.** Secret belum diset / header tidak ada / digest beda ⇒ **401**.
   Tidak pernah "karena secret belum diset, ya sudah diterima saja" — itu justru
   membuat lubangnya permanen di environment yang belum dikonfigurasi.
2. **RAW BYTES.** Base string SELALU dari `await request.body()`.
   `json.dumps(await request.json())` mengubah spasi + urutan kunci ⇒ digest beda
   ⇒ semua webhook sah ikut ditolak. Ini penyebab gagal #1 di lapangan.
3. **CONSTANT-TIME.** `hmac.compare_digest`, bukan `==` (kebocoran timing).
4. **ENV DIBACA SAAT DIPANGGIL**, bukan saat import — supaya secret yang baru
   ditulis `bootstrap.sh`/`gen_webhook_secrets.py` langsung berlaku setelah
   reload, dan supaya bisa di-monkeypatch di test.

## Skema tanda tangan per platform (base string yang DITANDATANGANI)

| Platform    | Secret        | Header kanonik  | Base string                     |
|-------------|---------------|-----------------|---------------------------------|
| `shopee`    | partner_key   | `Authorization` | `f"{webhook_url}|{raw_body}"`   |
| `tiktok`    | app_secret    | `Authorization` | `f"{app_key}{raw_body}"`        |
| `tokopedia` | client_secret | `Authorization` | `raw_body`                      |

Digest: **HMAC-SHA256, hex lowercase** (ketiga platform).

### Header alternatif yang diterima
Proxy/ingress kadang MEMBUANG `Authorization`. Karena itu selain header kanonik
kita juga menerima (urutan prioritas): header khas platform
(`X-Shopee-Signature`, `X-Tiktok-Signature`, `X-Tokopedia-Hmac-Signature`) lalu
`X-Webhook-Signature` generik. Nilainya boleh berawalan `Bearer ` atau `sha256=`.

### Shopee: JANGAN pakai `str(request.url)`
Shopee menandatangani URL PUBLIK yang mereka panggil. Di belakang ingress,
`request.url` menjadi `http://127.0.0.1:8001/...` ⇒ digest tidak akan pernah
cocok. URL-nya WAJIB dari env `SHOPEE_WEBHOOK_URL` (fallback: dibangun dari
`REACT_APP_BACKEND_URL` frontend + path kanonik).

## Proteksi replay (opsional, otomatis aktif bila ada timestamp)
Bila payload/header membawa `timestamp` epoch detik dan `WEBHOOK_REPLAY_TOLERANCE_SEC`
> 0 (default 300), request yang terlalu tua/terlalu masa depan ditolak 401.
Dimatikan dengan `WEBHOOK_REPLAY_TOLERANCE_SEC=0`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)

ALGO = "hmac-sha256"
PLATFORMS = ("shopee", "tiktok", "tokopedia")

#: Secret bersama untuk dev/preview. Dipakai HANYA bila secret per-platform kosong.
#: Tetap fail-closed: kalau dua-duanya kosong ⇒ 401.
SHARED_SECRET_ENV = "MARKETING_WEBHOOK_SECRET"

_SECRET_ENV = {
    "shopee": "SHOPEE_WEBHOOK_SECRET",
    "tiktok": "TIKTOK_WEBHOOK_SECRET",
    "tokopedia": "TOKOPEDIA_WEBHOOK_SECRET",
}

_HEADER_PRIORITY = {
    "shopee": ("authorization", "x-shopee-signature", "x-webhook-signature"),
    "tiktok": ("authorization", "x-tiktok-signature", "x-webhook-signature"),
    "tokopedia": ("authorization", "x-tokopedia-hmac-signature", "x-webhook-signature"),
}

_CANONICAL_PATH = {
    "shopee": "/api/marketing/webhooks/shopee",
    "tiktok": "/api/marketing/webhooks/tiktok",
    "tokopedia": "/api/marketing/webhooks/tokopedia",
}

_BASE_STRING_SCHEME = {
    "shopee": "{webhook_url}|{raw_body}",
    "tiktok": "{app_key}{raw_body}",
    "tokopedia": "{raw_body}",
}

# Kode galat — dipakai FE/ops untuk membedakan "salah tanda tangan" vs "belum dikonfigurasi".
ERR_UNKNOWN_PLATFORM = "WEBHOOK_UNKNOWN_PLATFORM"
ERR_SECRET_NOT_CONFIGURED = "WEBHOOK_SECRET_NOT_CONFIGURED"
ERR_SIGNATURE_MISSING = "WEBHOOK_SIGNATURE_MISSING"
ERR_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"
ERR_REPLAY = "WEBHOOK_TIMESTAMP_OUT_OF_TOLERANCE"


class WebhookAuthError(Exception):
    """Ditolak — selalu 401 supaya penyerang tidak bisa membedakan sebabnya dari status."""

    http_status = 401

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_detail(self) -> dict:
        return {"error": self.message, "code": self.code}


# ─────────────────────────────────────────────────────────────────────────────
# Konfigurasi (dibaca saat dipanggil — JANGAN cache di level modul)
# ─────────────────────────────────────────────────────────────────────────────
def _env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def secret_for(platform: str) -> str:
    """Secret aktif platform (per-platform dulu, lalu secret bersama). '' = belum diset."""
    return _env(_SECRET_ENV.get(platform, "")) or _env(SHARED_SECRET_ENV)


def webhook_url_for(platform: str) -> str:
    """URL PUBLIK yang ditandatangani Shopee. Wajib dari env, bukan `request.url`."""
    explicit = _env(f"{platform.upper()}_WEBHOOK_URL")
    if explicit:
        return explicit
    base = _env("PUBLIC_BASE_URL") or _env("REACT_APP_BACKEND_URL") or _env("APP_URL")
    if base:
        return base.rstrip("/") + _CANONICAL_PATH.get(platform, "")
    return ""


def app_key_for(platform: str) -> str:
    """app_key TikTok ikut ditandatangani (prefix base string)."""
    if platform == "tiktok":
        return _env("TIKTOK_APP_KEY")
    return ""


def replay_tolerance_sec() -> int:
    raw = _env("WEBHOOK_REPLAY_TOLERANCE_SEC")
    if raw == "":
        return 300
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return 300


def is_configured(platform: str) -> bool:
    """True bila endpoint platform ini bisa menerima webhook sah."""
    if platform not in PLATFORMS:
        return False
    if not secret_for(platform):
        return False
    if platform == "shopee" and not webhook_url_for("shopee"):
        return False
    if platform == "tiktok" and not app_key_for("tiktok"):
        return False
    return True


def config_status() -> dict:
    """Ringkasan aman untuk UI ops — TIDAK PERNAH memuat nilai secret."""
    out = {}
    for p in PLATFORMS:
        out[p] = {
            "configured": is_configured(p),
            "secret_set": bool(secret_for(p)),
            "uses_shared_secret": (not _env(_SECRET_ENV[p])) and bool(_env(SHARED_SECRET_ENV)),
            "signature_algo": ALGO,
            "base_string_scheme": _BASE_STRING_SCHEME[p],
            "canonical_header": _HEADER_PRIORITY[p][0],
            "accepted_headers": list(_HEADER_PRIORITY[p]),
            "webhook_url": webhook_url_for(p) if p == "shopee" else None,
            "app_key_set": bool(app_key_for(p)) if p == "tiktok" else None,
            "replay_tolerance_sec": replay_tolerance_sec(),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Perhitungan tanda tangan
# ─────────────────────────────────────────────────────────────────────────────
def base_string(platform: str, raw_body: bytes, *, webhook_url: str = "", app_key: str = "") -> bytes:
    """Bangun base string per spesifikasi platform. `raw_body` WAJIB bytes mentah."""
    if not isinstance(raw_body, (bytes, bytearray)):
        raise TypeError("raw_body harus bytes mentah (await request.body()), bukan dict/str")
    raw = bytes(raw_body)
    if platform == "shopee":
        return webhook_url.encode("utf-8") + b"|" + raw
    if platform == "tiktok":
        return app_key.encode("utf-8") + raw
    if platform == "tokopedia":
        return raw
    raise WebhookAuthError(ERR_UNKNOWN_PLATFORM, f"platform webhook tidak dikenal: {platform}")


def compute_signature(
    platform: str,
    raw_body: bytes,
    *,
    secret: str | None = None,
    webhook_url: str | None = None,
    app_key: str | None = None,
) -> str:
    """Digest hex lowercase yang SEHARUSNYA dikirim platform. Dipakai juga oleh test."""
    if platform not in PLATFORMS:
        raise WebhookAuthError(ERR_UNKNOWN_PLATFORM, f"platform webhook tidak dikenal: {platform}")
    sec = secret if secret is not None else secret_for(platform)
    if not sec:
        raise WebhookAuthError(
            ERR_SECRET_NOT_CONFIGURED,
            f"secret webhook {platform} belum dikonfigurasi ({_SECRET_ENV[platform]} "
            f"atau {SHARED_SECRET_ENV})",
        )
    url = webhook_url if webhook_url is not None else webhook_url_for(platform)
    key = app_key if app_key is not None else app_key_for(platform)
    if platform == "shopee" and not url:
        raise WebhookAuthError(
            ERR_SECRET_NOT_CONFIGURED,
            "SHOPEE_WEBHOOK_URL belum diset — Shopee menandatangani URL publik, "
            "jadi URL-nya tidak boleh ditebak dari request.url di belakang ingress",
        )
    if platform == "tiktok" and not key:
        raise WebhookAuthError(
            ERR_SECRET_NOT_CONFIGURED,
            "TIKTOK_APP_KEY belum diset — app_key ikut ditandatangani di base string",
        )
    msg = base_string(platform, raw_body, webhook_url=url, app_key=key)
    return hmac.new(sec.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _clean_sig(value: str) -> str:
    v = (value or "").strip()
    for prefix in ("bearer ", "sha256=", "hmac-sha256="):
        if v.lower().startswith(prefix):
            v = v[len(prefix):].strip()
    return v.lower()


def extract_signature(platform: str, headers: Mapping[str, Any]) -> tuple[str, str]:
    """(signature_bersih, nama_header). ('', '') bila tidak ada satu pun header."""
    lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    for name in _HEADER_PRIORITY.get(platform, ()):
        raw = lowered.get(name)
        if raw:
            cleaned = _clean_sig(str(raw))
            if cleaned:
                return cleaned, name
    return "", ""


def _extract_timestamp(raw_body: bytes, headers: Mapping[str, Any]) -> int | None:
    lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    for name in ("x-webhook-timestamp", "x-shopee-timestamp", "x-tiktok-timestamp", "x-timestamp"):
        if lowered.get(name):
            try:
                return int(float(lowered[name]))
            except (TypeError, ValueError):
                return None
    try:
        payload = json.loads(raw_body or b"{}")
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("timestamp", "create_time", "event_time"):
        val = payload.get(key)
        if val in (None, "", 0):
            continue
        try:
            num = int(float(val))
        except (TypeError, ValueError):
            continue
        # milidetik → detik
        if num > 10_000_000_000:
            num //= 1000
        return num
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Verifikasi (dipakai route)
# ─────────────────────────────────────────────────────────────────────────────
def verify(
    platform: str,
    raw_body: bytes,
    headers: Mapping[str, Any],
    *,
    now: float | None = None,
) -> dict:
    """Verifikasi HMAC. Balik metadata audit bila sah, `WebhookAuthError` bila tidak.

    Metadata sengaja disimpan bersama event supaya jejak audit menjawab
    "benarkah event ini datang dari platform?" tanpa menyimpan secret.
    """
    if platform not in PLATFORMS:
        raise WebhookAuthError(ERR_UNKNOWN_PLATFORM, f"platform webhook tidak dikenal: {platform}")

    signature, header_name = extract_signature(platform, headers)
    if not signature:
        raise WebhookAuthError(
            ERR_SIGNATURE_MISSING,
            f"header tanda tangan webhook tidak ada — kirim salah satu dari "
            f"{', '.join(_HEADER_PRIORITY[platform])}",
        )

    expected = compute_signature(platform, raw_body)  # raise bila secret belum diset

    if not hmac.compare_digest(expected, signature):
        logger.warning(
            "Webhook %s DITOLAK: tanda tangan tidak cocok (header=%s, len_body=%d)",
            platform, header_name, len(raw_body or b""),
        )
        raise WebhookAuthError(ERR_SIGNATURE_INVALID, "tanda tangan webhook tidak sah")

    tol = replay_tolerance_sec()
    ts = _extract_timestamp(raw_body, headers) if tol else None
    if tol and ts is not None:
        skew = abs((now if now is not None else time.time()) - ts)
        if skew > tol:
            raise WebhookAuthError(
                ERR_REPLAY,
                f"timestamp webhook di luar toleransi ({int(skew)}s > {tol}s) — dugaan replay",
            )

    return {
        "signature_present": True,
        "signature_valid": True,
        "signature_header": header_name,
        "signature_algo": ALGO,
        "base_string_scheme": _BASE_STRING_SCHEME[platform],
        "uses_shared_secret": (not _env(_SECRET_ENV[platform])) and bool(_env(SHARED_SECRET_ENV)),
        "payload_timestamp": ts,
        "replay_tolerance_sec": tol,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
