"""
PT Rahaza ERP — Notifications & Alerts (Phase 12.2)

In-app notification engine:
  - Koleksi: notifications SSOT (type='rahaza')
  - Helper: publish_notification(...) — dipanggil dari trigger points
            (low-stock, qc-fail, wo-due).
  - Endpoint:
      GET    /api/notifications                — daftar notifikasi untuk user (unread dulu)
      GET    /api/notifications/stream         — Server-Sent Events realtime
      POST   /api/notifications/{id}/read      — mark read by current user
      POST   /api/notifications/mark-all-read  — mark all unread-for-user as read
      GET    /api/notifications/unread-count   — badge count
      POST   /api/notifications/trigger/wo-due-scan  — trigger manual scan (debug/cron)

Semua notifikasi dikirim via SSE stream; client pakai EventSource subscribe.

P3 TD-010 Phase B (Session #11.12): Reads/writes are now backed by the
unified SSOT `notifications` collection (`type='rahaza'`). Multi-recipient
fields (target_roles, target_user_ids, read_by, dismissed, dedup_key) are
stored under `meta` and reshaped back to the legacy schema in responses.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from datetime import datetime, timezone, timedelta
from auth import require_auth as _require_auth_std, JWT_SECRET
from utils.notif_unified import (
    notif_insert,
    reshape_as_rahaza,
    rahaza_check_dedup,
    rahaza_mark_read_by,
    rahaza_mark_read_by_many,
    rahaza_matches_user,
)
import jwt as _jwt
import json
import asyncio
import logging
from utils.query_guards import q_int

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

# P3 TD-010 Phase B (Session #11.12): writes go to unified SSOT.
logger.info(
    "[NOTIF-CONSOLIDATION] rahaza_notifications router now writes/reads SSOT "
    "(collection: notifications, type='rahaza')."
)


# ─── AUTH HELPER ─────────────────────────────────────────────────────────────
async def require_auth(request: Request):
    """
    Standard auth (reuse from auth.py).
    Khusus untuk SSE /stream, token bisa via query param karena EventSource
    tidak bisa set Authorization header.
    """
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return await _require_auth_std(request)
    # Fallback: token via query (untuk SSE EventSource)
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(401, "Tidak ada token")
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(401, "Token tidak valid")


def _now():
    return datetime.now(timezone.utc).isoformat()


# ─── PUBLISH HELPER (dipakai route lain) ─────────────────────────────────────
async def publish_notification(
    db,
    *,
    type_: str,
    severity: str,           # 'info' | 'warning' | 'error' | 'success'
    title: str,
    message: str,
    link_module: str = None,
    link_id: str = None,
    target_roles: list = None,
    target_user_ids: list = None,
    dedup_key: str = None,   # jika diisi, cek duplikat 10 menit terakhir
):
    """
    Insert notifikasi ke SSOT `notifications` (type='rahaza').

    Dedup: bila dedup_key ada dan notif dengan key sama + belum dismissed
    dibuat < 10 menit yang lalu, skip.
    """
    if severity not in ("info", "warning", "error", "success"):
        severity = "info"
    if not target_roles and not target_user_ids:
        # default broadcast ke super_admin agar tidak hilang
        target_roles = ["superadmin"]

    # Dedup
    if dedup_key:
        dup = await rahaza_check_dedup(db, dedup_key=dedup_key, within_minutes=10)
        if dup:
            return None

    nid = await notif_insert(
        db,
        type='rahaza',
        body=message,
        subtype=type_,
        severity=severity,
        title=title,
        source_id=link_id,
        meta={
            'link_module':     link_module,
            'target_roles':    target_roles or [],
            'target_user_ids': target_user_ids or [],
            'dedup_key':       dedup_key,
            'read_by':         [],
            'dismissed':       False,
        },
    )

    # Build broadcast doc in legacy shape for live SSE subscribers
    notif_doc = {
        'id':              nid,
        'type':            type_,
        'severity':        severity,
        'title':           title,
        'message':         message,
        'link_module':     link_module,
        'link_id':         link_id,
        'target_roles':    target_roles or [],
        'target_user_ids': target_user_ids or [],
        'dedup_key':       dedup_key,
        'read_by':         [],
        'dismissed':       False,
        'created_at':      _now(),
    }

    # Push ke live SSE subscribers
    await _push_to_subscribers(notif_doc)
    logger.info(f"[notif] {severity.upper()} :: {title}")
    return notif_doc


# ─── SSE SUBSCRIBER REGISTRY ─────────────────────────────────────────────────
_subscribers: dict = {}  # key=user_id, val=asyncio.Queue


async def _push_to_subscribers(notif: dict):
    """Broadcast notifikasi ke semua subscriber yang matching role/user."""
    doc_out = {k: v for k, v in notif.items() if k != "_id"}
    for uid, q in list(_subscribers.items()):
        try:
            # Filter berdasarkan target — keep simple: kalau broadcast ke role, setiap subscriber
            # yang punya role itu akan dapat. Simpan role di registry saat subscribe.
            target_roles = notif.get("target_roles") or []
            target_users = notif.get("target_user_ids") or []
            sub_role = _subscribers_meta.get(uid, {}).get("role", "")
            if target_users and uid in target_users:
                await q.put(doc_out)
            elif target_roles and (sub_role in target_roles or "superadmin" == sub_role):
                # superadmin selalu dapat
                await q.put(doc_out)
            elif not target_roles and not target_users:
                await q.put(doc_out)
        except Exception as e:
            logger.warning(f"[notif] push to {uid} failed: {e}")


_subscribers_meta: dict = {}  # key=user_id, val={"role": str, "name": str}


# ─── SSE STREAM ───────────────────────────────────────────────────────────────
@router.get("/stream")
async def notification_stream(request: Request):
    """Server-Sent Events endpoint. Client connect via EventSource('/api/notifications/stream?token=<jwt>')."""
    user = await require_auth(request)
    uid = user.get("user_id") or user.get("sub") or user.get("email")
    role = (user.get("role") or "").lower()
    name = user.get("name") or user.get("email") or "unknown"

    q: asyncio.Queue = asyncio.Queue()
    _subscribers[uid] = q
    _subscribers_meta[uid] = {"role": role, "name": name}
    logger.info(f"[notif] SSE subscribe: {name} ({role}) — total subs: {len(_subscribers)}")

    async def event_generator():
        try:
            # Ping awal
            yield f"event: ready\ndata: {json.dumps({'subscribed_at': _now()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    notif = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"event: notification\ndata: {json.dumps(notif)}\n\n"
                except asyncio.TimeoutError:
                    # heartbeat agar koneksi tidak mati
                    yield "event: ping\ndata: {}\n\n"
        finally:
            _subscribers.pop(uid, None)
            _subscribers_meta.pop(uid, None)
            logger.info(f"[notif] SSE unsub: {name}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


# ─── CRUD ─────────────────────────────────────────────────────────────────────
def _user_id_of(user: dict) -> str:
    return user.get("user_id") or user.get("id") or user.get("sub") or user.get("email")


def _user_for_match(user: dict) -> dict:
    """Build the shape rahaza_matches_user expects (id + role)."""
    return {
        'id':   _user_id_of(user),
        'role': (user.get("role") or "").lower(),
    }


@router.get("")
async def list_notifications(request: Request):
    """List notifikasi untuk user saat ini. unread dulu, lalu sortir by created_at desc."""
    user = await require_auth(request)
    db = get_db()
    limit = q_int(request.query_params.get("limit"), default=50, name="limit", minimum=1, maximum=500)
    cursor = db.notifications.find(
        {'type': 'rahaza', 'meta.dismissed': {'$ne': True}},
        {'_id': 0},
    ).sort('created_at', -1).limit(limit * 2)
    user_match = _user_for_match(user)
    uid = _user_id_of(user)
    out = []
    async for n in cursor:
        if not rahaza_matches_user(n, user_match):
            continue
        shaped = reshape_as_rahaza(n, current_user_id=uid)
        out.append(shaped)
        if len(out) >= limit:
            break
    # Sort: unread dulu, lalu created_at desc
    def _key(x):
        try:
            ts = -datetime.fromisoformat(x["created_at"]).timestamp()
        except Exception:
            ts = 0
        return (x.get("read", False), ts)
    out.sort(key=_key)
    return {"items": out, "total": len(out)}


@router.get("/unread-count")
async def unread_count(request: Request):
    """Jumlah notifikasi rahaza yang belum dibaca oleh user ini.

    2026-08-07: memakai aturan audiens tunggal (`notif_audience_query`) +
    status baca per orang. Sebelumnya notifikasi tanpa target dihitung untuk
    SEMUA user (bocor lintas role) dan status baca dibaca dari field global.
    """
    user = await require_auth(request)
    db = get_db()
    from utils.notif_unified import notif_count_unread_for
    cnt = await notif_count_unread_for(db, _user_for_match(user), type='rahaza')
    return {"count": cnt}


@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    uid = _user_id_of(user)
    await rahaza_mark_read_by(db, notif_id, uid)
    return {"ok": True}


@router.post("/mark-all-read")
async def mark_all_read(request: Request):
    user = await require_auth(request)
    db = get_db()
    uid = _user_id_of(user)
    role = (user.get("role") or "").lower()
    cursor = db.notifications.find(
        {
            'type': 'rahaza',
            'meta.dismissed': {'$ne': True},
            'meta.read_by': {'$ne': uid},
        },
        {'_id': 0, 'id': 1, 'meta': 1},
    )
    ids = []
    async for n in cursor:
        meta = n.get('meta') or {}
        target_users = meta.get('target_user_ids') or []
        target_roles = meta.get('target_roles') or []
        if uid in target_users or role in target_roles or role == 'superadmin':
            ids.append(n['id'])
        elif not target_users and not target_roles:
            ids.append(n['id'])
    if ids:
        await rahaza_mark_read_by_many(db, ids, uid)
    return {"updated": len(ids)}


# ─── TRIGGER SCANS (manual / cron) ───────────────────────────────────────────
@router.post("/trigger/wo-due-scan")
async def scan_wo_due(request: Request):
    """
    Cron/manual scan: cari WO status in_progress dengan due_date dalam 2 hari,
    progress < 80 %. Publish alert.
    """
    await require_auth(request)
    db = get_db()
    today = datetime.now(timezone.utc).date()
    deadline = (today + timedelta(days=2)).isoformat()

    wos = await db.rahaza_work_orders.find(
        {"status": {"$in": ["in_progress", "pending"]},
         "due_date": {"$lte": deadline, "$gte": today.isoformat()}},
        {"_id": 0}
    ).to_list(500)

    published = 0
    for w in wos:
        qty = float(w.get("qty") or 0)
        progress_qty = float(w.get("progress_qty") or 0)
        pct = (progress_qty / qty * 100) if qty > 0 else 0
        if pct < 80:
            d_id = w.get("id")
            due = w.get("due_date", "")
            await publish_notification(
                db,
                type_="wo_due_soon",
                severity="warning",
                title=f"WO {w.get('wo_number', '')} mendekati tenggat",
                message=f"Due {due} · progress {pct:.0f}% ({progress_qty:.0f}/{qty:.0f} pcs). Perlu percepatan.",
                link_module="prod-work-orders",
                link_id=d_id,
                target_roles=["production_manager", "supervisor", "superadmin"],
                dedup_key=f"wo_due::{d_id}",
            )
            published += 1

    return {"scanned": len(wos), "published": published}
