#!/usr/bin/env python3
"""gen_local_secrets — generator secret LOKAL yang idempoten (FASE 19 / AUDIT-2).

Mengisi `backend/.env` dengan kredensial yang **kita hasilkan sendiri** (bukan
milik pihak ketiga), supaya fitur berikut benar-benar HIDUP di environment baru
alih-alih mengembalikan 503 / menerima request tanpa auth:

  * **VAPID keypair** (Web Push) — `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`,
    `VAPID_CLAIMS_EMAIL`. Web Push TIDAK butuh akun pihak ketiga: VAPID adalah
    identitas server kita sendiri terhadap push service browser.
  * **Secret webhook marketplace** — `MARKETING_WEBHOOK_SECRET` +
    `SHOPEE_WEBHOOK_URL` + `TIKTOK_APP_KEY` (dev). Di PRODUKSI ketiga secret
    per-platform WAJIB diganti dengan nilai dari console masing-masing
    (`SHOPEE_WEBHOOK_SECRET`=partner_key, `TOKOPEDIA_WEBHOOK_SECRET`=client_secret,
    `TIKTOK_WEBHOOK_SECRET`=app_secret).

Sifat: **IDEMPOTEN**. Kunci yang sudah ada TIDAK PERNAH ditimpa (menimpa VAPID
membuat semua subscription browser yang tersimpan langsung tidak valid).
MONGO_URL / REACT_APP_BACKEND_URL tidak pernah disentuh.

Pakai:
    python3 scripts/gen_local_secrets.py            # isi yang belum ada
    python3 scripts/gen_local_secrets.py --print     # tampilkan status (tanpa nilai secret)
    python3 scripts/gen_local_secrets.py --force-vapid   # BUAT ULANG VAPID (subscription lama mati)
"""
from __future__ import annotations

import argparse
import base64
import re
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

APP = Path("/app")
BE_ENV = APP / "backend" / ".env"
FE_ENV = APP / "frontend" / ".env"

G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_vapid_keypair() -> tuple[str, str]:
    """(public_b64url_uncompressed_point, private_b64url_der).

    * public  → `applicationServerKey` untuk `PushManager.subscribe()`:
      X9.62 **uncompressed point** (65 byte, byte pertama 0x04), base64url tanpa padding.
    * private → argumen `vapid_private_key` pywebpush: DER **TraditionalOpenSSL**
      (SEC1 EC PRIVATE KEY), base64url tanpa padding — di-parse `Vapid.from_string()`.

    Format inilah sumber kegagalan #1 Web Push; jangan diganti tanpa menguji
    ulang `scripts/poc_fase19_core.py`.
    """
    priv = ec.generate_private_key(ec.SECP256R1())
    der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    assert len(pub_raw) == 65 and pub_raw[0] == 0x04, "public key bukan uncompressed point P-256"
    return b64u(pub_raw), b64u(der)


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def set_env(path: Path, key: str, value: str) -> str:
    """Tambah/ganti satu key. Balik 'added' | 'replaced'. Selalu diakhiri newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    line = f'{key}="{value}"'
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pat.search(text):
        text = pat.sub(line, text)
        action = "replaced"
    else:
        text += line + "\n"
        action = "added"
    path.write_text(text, encoding="utf-8")
    return action


def public_base_url() -> str:
    return (read_env(FE_ENV).get("REACT_APP_BACKEND_URL") or "").rstrip("/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-vapid", action="store_true",
                    help="buat ulang VAPID (SEMUA subscription browser lama jadi tidak valid)")
    ap.add_argument("--print", dest="only_print", action="store_true")
    args = ap.parse_args()

    env = read_env(BE_ENV)
    changed: list[str] = []

    if args.only_print:
        for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_CLAIMS_EMAIL",
                  "MARKETING_WEBHOOK_SECRET", "SHOPEE_WEBHOOK_SECRET",
                  "TOKOPEDIA_WEBHOOK_SECRET", "TIKTOK_WEBHOOK_SECRET",
                  "TIKTOK_APP_KEY", "SHOPEE_WEBHOOK_URL"):
            v = env.get(k, "")
            mark = f"{G}SET{X}" if v else f"{R}kosong{X}"
            extra = f" (len={len(v)})" if v and "URL" not in k else (f" = {v}" if v else "")
            print(f"  {k:28s} {mark}{extra}")
        return 0

    # ── VAPID ──────────────────────────────────────────────────────────────
    have_vapid = bool(env.get("VAPID_PUBLIC_KEY")) and bool(env.get("VAPID_PRIVATE_KEY"))
    if args.force_vapid or not have_vapid:
        pub, priv = generate_vapid_keypair()
        set_env(BE_ENV, "VAPID_PUBLIC_KEY", pub)
        set_env(BE_ENV, "VAPID_PRIVATE_KEY", priv)
        changed += ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"]
        print(f"  {G}✓{X} VAPID keypair dibuat (public {len(pub)} char base64url)")
    else:
        print(f"  · VAPID keypair sudah ada — TIDAK ditimpa")
    if not env.get("VAPID_CLAIMS_EMAIL"):
        set_env(BE_ENV, "VAPID_CLAIMS_EMAIL", "admin@dewiaditya.id")
        changed.append("VAPID_CLAIMS_EMAIL")

    # ── Webhook marketplace ────────────────────────────────────────────────
    if not env.get("MARKETING_WEBHOOK_SECRET"):
        set_env(BE_ENV, "MARKETING_WEBHOOK_SECRET", secrets.token_urlsafe(40))
        changed.append("MARKETING_WEBHOOK_SECRET")
        print(f"  {G}✓{X} MARKETING_WEBHOOK_SECRET dibuat (dev — ganti per-platform di produksi)")
    else:
        print("  · MARKETING_WEBHOOK_SECRET sudah ada")

    if not env.get("TIKTOK_APP_KEY"):
        set_env(BE_ENV, "TIKTOK_APP_KEY", "dev-tiktok-app-key")
        changed.append("TIKTOK_APP_KEY")

    if not env.get("SHOPEE_WEBHOOK_URL"):
        base = public_base_url()
        if base:
            set_env(BE_ENV, "SHOPEE_WEBHOOK_URL", f"{base}/api/marketing/webhooks/shopee")
            changed.append("SHOPEE_WEBHOOK_URL")
            print(f"  {G}✓{X} SHOPEE_WEBHOOK_URL = {base}/api/marketing/webhooks/shopee")
        else:
            print(f"  {Y}!{X} REACT_APP_BACKEND_URL tak terbaca — set SHOPEE_WEBHOOK_URL manual")

    if not env.get("WEBHOOK_REPLAY_TOLERANCE_SEC"):
        set_env(BE_ENV, "WEBHOOK_REPLAY_TOLERANCE_SEC", "300")
        changed.append("WEBHOOK_REPLAY_TOLERANCE_SEC")

    print(f"\n  {len(changed)} key ditulis: {', '.join(changed) if changed else '(tidak ada)'}")
    if changed:
        print("  ⇒ jalankan: sudo supervisorctl restart backend")
    return 0


if __name__ == "__main__":
    sys.exit(main())
