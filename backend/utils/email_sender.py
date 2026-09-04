"""utils.email_sender — pengirim email SMTP yang mendukung LAMPIRAN.

KENAPA ADA
`routes/dewi_notifications._try_send_email` (pengirim lama) hanya bisa:
  * teks polos — TIDAK bisa melampirkan file (rapor Excel/PDF), dan
  * mode STARTTLS + login WAJIB — sehingga server SMTP internal/relay tanpa
    autentikasi (atau tanpa enkripsi) selalu ditolak dengan "SMTP not configured".
Rapor valuasi bulanan butuh dua-duanya: lampiran + mode SMTP yang fleksibel.

DESAIN
  * `send_email()` async, tapi pekerjaan smtplib (blocking) dijalankan di thread
    lewat `asyncio.to_thread` supaya event-loop FastAPI tidak ikut tertahan.
  * Mode keamanan eksplisit (`smtp_security`): `starttls` (default, port 587),
    `ssl` (port 465), atau `none` (server internal / relay tanpa enkripsi).
  * Login HANYA dilakukan bila `smtp_user` DAN `smtp_password` terisi — banyak
    relay internal memang tanpa autentikasi.
  * Tidak pernah melempar exception: selalu balas dict {ok, error, ...} supaya
    pemanggil (job scheduler) bisa mencatat kegagalan tanpa ikut mati.

Konfigurasi dibaca dari koleksi `dewi_provider_config` (_type='main') — sama dengan
Pengaturan Notifikasi di UI, jadi user hanya mengisi satu tempat.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

_log = logging.getLogger(__name__)

SEC_STARTTLS = "starttls"
SEC_SSL = "ssl"
SEC_NONE = "none"
VALID_SECURITY = (SEC_STARTTLS, SEC_SSL, SEC_NONE)

DEFAULT_TIMEOUT = 30


def resolve_security(config: dict) -> str:
    """Mode keamanan efektif. Kompatibel ke belakang: kalau tidak diisi → tebak dari port."""
    sec = str((config or {}).get("smtp_security") or "").strip().lower()
    if sec in VALID_SECURITY:
        return sec
    try:
        port = int((config or {}).get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587
    return SEC_SSL if port == 465 else SEC_STARTTLS


def smtp_status(config: dict) -> dict:
    """Ringkas kesiapan SMTP untuk ditampilkan di UI (tanpa membocorkan password)."""
    cfg = config or {}
    host = str(cfg.get("smtp_host") or "").strip()
    user = str(cfg.get("smtp_user") or "").strip()
    pwd = str(cfg.get("smtp_password") or "").strip()
    sec = resolve_security(cfg)
    ready = bool(host)
    reason = "" if ready else "Host SMTP belum diisi di Pengaturan Notifikasi."
    if ready and sec != SEC_NONE and not (user and pwd):
        # bukan blokir: banyak server 587 menerima tanpa auth, tapi beri tahu user
        reason = "Host terisi, tetapi user/password kosong — pastikan server mengizinkan relay tanpa autentikasi."
    return {
        "configured": ready,
        "host": host,
        "port": int(cfg.get("smtp_port") or 587),
        "security": sec,
        "auth": bool(user and pwd),
        "from_email": str(cfg.get("smtp_from_email") or user or "").strip(),
        "from_name": str(cfg.get("smtp_from_name") or "CV. Dewi Aditya").strip(),
        "note": reason,
    }


def _build_message(*, from_email: str, from_name: str, to: str, subject: str,
                   body_text: str, body_html: str | None,
                   attachments: list[dict] | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject or "CV. Dewi Aditya"
    msg["From"] = formataddr((from_name or "CV. Dewi Aditya", from_email))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="dewiaditya.id")
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for att in attachments or []:
        data = att.get("content")
        if not data:
            continue
        mime = str(att.get("mime") or "application/octet-stream")
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.get("filename") or "lampiran.bin",
        )
    return msg


def _send_blocking(*, host: str, port: int, security: str, user: str, password: str,
                   from_email: str, recipients: list[str], raw: bytes,
                   timeout: int) -> None:
    if security == SEC_SSL:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        server.ehlo()
        if security == SEC_STARTTLS:
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.sendmail(from_email, recipients, raw)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 — koneksi sudah tertutup, bukan kegagalan kirim
            pass


async def send_email(config: dict, *, to: str, subject: str, body_text: str,
                     body_html: str | None = None,
                     attachments: list[dict] | None = None,
                     timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Kirim satu email (opsional berlampiran). SELALU balas dict, tidak melempar.

    `attachments`: list of {filename, content(bytes), mime}
    Balasan: {"ok": bool, "error": str|None, "security": str, "host": str,
              "attachments": n, "bytes": n}
    """
    cfg = config or {}
    host = str(cfg.get("smtp_host") or "").strip()
    if not host:
        return {"ok": False, "error": "SMTP belum dikonfigurasi (host kosong).",
                "security": None, "host": "", "attachments": 0, "bytes": 0}
    try:
        port = int(cfg.get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587
    user = str(cfg.get("smtp_user") or "").strip()
    password = str(cfg.get("smtp_password") or "").strip()
    security = resolve_security(cfg)
    from_email = str(cfg.get("smtp_from_email") or user or f"no-reply@{host}").strip()
    from_name = str(cfg.get("smtp_from_name") or "CV. Dewi Aditya").strip()
    to = str(to or "").strip()
    if not to:
        return {"ok": False, "error": "Alamat tujuan kosong.", "security": security,
                "host": host, "attachments": 0, "bytes": 0}

    try:
        msg = _build_message(from_email=from_email, from_name=from_name, to=to,
                             subject=subject, body_text=body_text, body_html=body_html,
                             attachments=attachments)
        raw = msg.as_bytes()
    except Exception as e:  # noqa: BLE001
        _log.exception("[email] gagal menyusun pesan")
        return {"ok": False, "error": f"Gagal menyusun email: {e}", "security": security,
                "host": host, "attachments": len(attachments or []), "bytes": 0}

    try:
        await asyncio.to_thread(
            _send_blocking, host=host, port=port, security=security, user=user,
            password=password, from_email=from_email, recipients=[to], raw=raw,
            timeout=timeout,
        )
        return {"ok": True, "error": None, "security": security, "host": host,
                "attachments": len(attachments or []), "bytes": len(raw)}
    except Exception as e:  # noqa: BLE001 — kegagalan kirim tidak boleh mematikan job
        _log.warning("[email] gagal kirim ke %s via %s:%s (%s): %s", to, host, port, security, e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "security": security,
                "host": host, "attachments": len(attachments or []), "bytes": len(raw)}
