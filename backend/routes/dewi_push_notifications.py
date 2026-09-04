"""
CV. Dewi Aditya — Browser Push Notifications (Web Push / VAPID)

Endpoints:
  GET  /api/push/vapid-public-key  - kunci PUBLIK VAPID untuk PushManager.subscribe()
  GET  /api/push/config            - status konfigurasi push (untuk UI, tanpa nilai privat)
  POST /api/push/subscribe         - simpan subscription user aktif
  POST /api/push/unsubscribe       - hapus subscription
  POST /api/push/test              - kirim push uji ke user aktif
  POST /api/push/send              - (Admin) kirim push ke semua / user tertentu
  GET  /api/push/status            - apakah user punya subscription aktif

─── FASE 19 / AUDIT-2 — apa yang diperbaiki ──────────────────────────────────
1. **503 permanen.** `VAPID_PUBLIC_KEY` dibaca **saat import** dan tidak pernah ada,
   sehingga `GET /api/push/vapid-public-key` selalu 503 (temuan SRV-5XX di
   `scripts/audit_endpoint_sweep.py`) dan seluruh fitur notifikasi mati.
   Sekarang env dibaca **saat dipanggil** dan keypair-nya benar-benar dibuat oleh
   `scripts/gen_local_secrets.py` (Web Push TIDAK butuh akun pihak ketiga — VAPID
   adalah identitas server kita sendiri terhadap push service browser).
2. **`pywebpush` tidak terpasang.** `_send_webpush` selalu masuk `except` lalu
   mengembalikan False, jadi "terkirim 0" tanpa sebab yang bisa dilihat siapa pun.
   Sekarang paket terpasang dan kegagalan dilaporkan beserta status HTTP push service.
3. **Subscription mati tidak dibedakan dari gangguan sementara.** Dulu SEMUA
   kegagalan menghapus subscription — termasuk 500/timeout milik push service —
   sehingga user harus mengaktifkan ulang tanpa sebab. Sekarang HANYA
   **404/410 Gone** (subscription memang dicabut browser) yang di-prune.
"""
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request

from auth import require_auth
from database import get_db

load_dotenv(Path(__file__).parent.parent / '.env')

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push", tags=["push-notifications"])

#: Status HTTP dari push service yang berarti "subscription ini sudah mati permanen".
_GONE_STATUSES = (404, 410)


# ─── Konfigurasi (DIBACA SAAT DIPANGGIL, bukan saat import) ───────────────────
def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def vapid_public_key() -> str:
    return _env("VAPID_PUBLIC_KEY")


def vapid_private_key() -> str:
    return _env("VAPID_PRIVATE_KEY")


def vapid_email() -> str:
    return _env("VAPID_CLAIMS_EMAIL", "admin@dewiaditya.id")


def is_configured() -> bool:
    return bool(vapid_public_key()) and bool(vapid_private_key())


def _vapid_claims():
    # `aud` TIDAK diisi manual: pywebpush menurunkannya dari endpoint subscription.
    return {"sub": f"mailto:{vapid_email()}"}


def _send_webpush(subscription_info: dict, payload: dict):
    """Kirim satu web push. Balik (sukses, http_status_push_service, pesan).

    `http_status` dipakai pemanggil untuk membedakan subscription MATI (404/410 ⇒
    boleh dihapus) dari gangguan sementara (⇒ JANGAN dihapus).
    """
    if not is_configured():
        return False, None, "VAPID belum dikonfigurasi"
    try:
        from pywebpush import WebPushException, webpush
    except ImportError as e:  # pragma: no cover — dependensi wajib ada di requirements
        logger.error("pywebpush tidak terpasang: %s", e)
        return False, None, "pywebpush tidak terpasang"
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key(),
            vapid_claims=_vapid_claims(),
            timeout=10,
        )
        return True, 201, ""
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.warning("Push gagal (status=%s): %s", status, e)
        return False, status, str(e)[:300]
    except Exception as e:  # noqa: BLE001
        logger.warning("Push gagal (non-HTTP): %s", e)
        return False, None, str(e)[:300]


async def _broadcast(db, subs, payload: dict) -> dict:
    sent, failed, stale = 0, [], []
    for s in subs:
        sub_info = s.get("subscription") or {
            "endpoint": s.get("endpoint", ""), "keys": s.get("keys", {})}
        ok, status, msg = _send_webpush(sub_info, payload)
        if ok:
            sent += 1
            continue
        failed.append({"endpoint": s.get("endpoint", "")[:80], "status": status, "error": msg})
        # HANYA subscription yang memang sudah dicabut browser yang dihapus.
        if status in _GONE_STATUSES:
            stale.append(s.get("endpoint", ""))
    for ep in stale:
        if ep:
            await db.push_subscriptions.delete_one({"endpoint": ep})
    return {"sent": sent, "failed": failed, "stale_removed": len(stale)}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Kunci PUBLIK VAPID untuk `PushManager.subscribe()`.

    PUBLIK by-design (didaftarkan di `scripts/lib/public_endpoints.py`): browser
    membutuhkannya sebelum ada sesi apa pun, dan kunci publik memang tidak rahasia.
    """
    pub = vapid_public_key()
    if not pub:
        raise HTTPException(503, "Web Push belum dikonfigurasi. Jalankan "
                                "`python3 scripts/gen_local_secrets.py` lalu restart backend.")
    # `vapid_public_key` = nama lama yang dipakai FE; `publicKey` = konvensi Web Push.
    return {"vapid_public_key": pub, "publicKey": pub, "configured": True}


@router.get("/config")
async def push_config(request: Request):
    """Status konfigurasi push untuk UI (tanpa membocorkan kunci privat)."""
    await require_auth(request)
    db = get_db()
    return {
        "configured": is_configured(),
        "public_key_present": bool(vapid_public_key()),
        "private_key_present": bool(vapid_private_key()),
        "claims_email": vapid_email(),
        "total_subscriptions": await db.push_subscriptions.count_documents({}),
        "how_to_configure": "python3 scripts/gen_local_secrets.py && sudo supervisorctl restart backend",
    }


@router.post("/subscribe")
async def subscribe(request: Request):
    """Save/update push subscription for authenticated user."""
    user = await require_auth(request)
    if not is_configured():
        raise HTTPException(503, "Web Push belum dikonfigurasi di server.")
    db = get_db()
    body = await request.json()
    sub = body.get("subscription") or body
    if not isinstance(sub, dict) or not sub.get("endpoint"):
        raise HTTPException(400, "Objek subscription tidak valid (endpoint wajib).")
    endpoint = sub["endpoint"]
    await db.push_subscriptions.update_one(
        {"user_id": user["id"], "endpoint": endpoint},
        {"$set": {
            "user_id": user["id"],
            "user_email": user.get("email", ""),
            "endpoint": endpoint,
            "keys": sub.get("keys", {}),
            "subscription": sub,
            "user_agent": request.headers.get("user-agent", ""),
        }},
        upsert=True,
    )
    return {"ok": True, "message": "Subscription disimpan."}


@router.post("/unsubscribe")
async def unsubscribe(request: Request):
    """Remove push subscription."""
    user = await require_auth(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    endpoint = (body or {}).get("endpoint")
    if endpoint:
        res = await db.push_subscriptions.delete_one({"user_id": user["id"], "endpoint": endpoint})
    else:
        res = await db.push_subscriptions.delete_many({"user_id": user["id"]})
    return {"ok": True, "removed": res.deleted_count}


@router.post("/test")
async def send_test_push(request: Request):
    """Send a test push to the current user's subscriptions."""
    user = await require_auth(request)
    if not is_configured():
        raise HTTPException(503, "Web Push belum dikonfigurasi di server.")
    db = get_db()
    subs = await db.push_subscriptions.find({"user_id": user["id"]}, {"_id": 0}).to_list(20)
    if not subs:
        raise HTTPException(404, "Tidak ada subscription aktif. Aktifkan notifikasi browser terlebih dahulu.")
    payload = {
        "title": "CV. Dewi Aditya ERP",
        "body": "Notifikasi browser berhasil diaktifkan!",
        "icon": "/logo192.png",
        "data": {"url": "/"},
    }
    result = await _broadcast(db, subs, payload)
    return {"ok": result["sent"] > 0, "total_subs": len(subs), **result}


@router.post("/send")
async def send_push(request: Request):
    """(Admin/System) Send push notification to specific user or all subscribers."""
    await require_auth(request)
    if not is_configured():
        raise HTTPException(503, "Web Push belum dikonfigurasi di server.")
    db = get_db()
    body = await request.json()
    target_user_id = body.get("user_id")
    title = body.get("title", "CV. Dewi Aditya")
    message = body.get("body", "")
    url = body.get("url", "/")
    if not message:
        raise HTTPException(400, "body (pesan) wajib diisi.")
    query = {"user_id": target_user_id} if target_user_id else {}
    subs = await db.push_subscriptions.find(query, {"_id": 0}).to_list(500)
    payload = {"title": title, "body": message, "icon": "/logo192.png", "data": {"url": url}}
    result = await _broadcast(db, subs, payload)
    return {"ok": True, "total_subs": len(subs), **result}


@router.get("/status")
async def push_status(request: Request):
    """Check if user has active push subscriptions."""
    user = await require_auth(request)
    db = get_db()
    count = await db.push_subscriptions.count_documents({"user_id": user["id"]})
    return {
        "active_subscriptions": count,
        "push_enabled": count > 0,
        "server_configured": is_configured(),
    }
