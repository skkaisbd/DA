"""
CV. Dewi Aditya ERP — Procurement Request (Request Pengadaan)

Workflow pengadaan aset/barang internal dengan approval multi-level:
  Draft → Submitted → Dept Approval → Finance Approval → Approved / Rejected

Collections:
  dewi_procurement_requests — request utama
  dewi_procurement_items    — item detail per request
  dewi_procurement_approvals — log approval per request

Endpoints:
  GET    /api/procurement/dashboard         — summary stats
  GET    /api/procurement/requests          — list requests (paginated)
  POST   /api/procurement/requests          — buat request baru
  GET    /api/procurement/requests/{id}     — detail request
  PUT    /api/procurement/requests/{id}     — update (only draft)
  POST   /api/procurement/requests/{id}/submit   — submit ke approval
  POST   /api/procurement/requests/{id}/approve  — approve (dept/finance)
  POST   /api/procurement/requests/{id}/reject   — reject
  POST   /api/procurement/requests/{id}/cancel   — cancel (by requester)
  POST   /api/procurement/requests/{id}/complete — mark completed + optional link asset
  GET    /api/procurement/inbox             — items awaiting my approval
  GET    /api/procurement/requests/{id}/timeline — approval timeline
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from utils.counters import gen_prefixed_number
from core.doc_number_policy import issue_number
from auth import require_auth
from routes.shared import require_portal
from core import uom as _uom          # SSOT konversi satuan (INV-UOM-1/2)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain
from datetime import datetime, timezone, date
from typing import Optional
import uuid
import math
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/procurement", tags=["procurement"])
# SESI #19 — kunci kebijakan penomoran PR (registry `data/doc_number_registry.py`).
PR_DOCNUM_KEY = "dewi_procurement_requests.request_number"


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ─── Communication Hub Notification Helper ────────────────────────────────
PROCUREMENT_CHANNEL_NAME = "procurement-notifications"


async def _get_or_create_procurement_channel(db) -> dict:
    """Lazily create the system channel for procurement notifications.

    Channel ini bersifat public (semua user dapat join/lihat). Initial members
    diisi user yang berperan sebagai dept_head/finance/admin/manager.
    """
    ch = await db.comm_channels.find_one({"name": PROCUREMENT_CHANNEL_NAME}, {"_id": 0})
    if ch:
        return ch
    # Auto-populate members with privileged roles (best-effort)
    initial_members = []
    try:
        users_cursor = db.users.find(
            {"$or": [
                {"role": {"$in": ["admin", "manager", "dept_head", "finance"]}},
                {"is_admin": True},
            ]},
            {"_id": 0, "id": 1},
        )
        async for u in users_cursor:
            if u.get("id"):
                initial_members.append(u["id"])
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    # Also add ALL active users so everyone gets procurement notifications
    try:
        all_users_cursor = db.users.find({"is_active": {"$ne": False}}, {"_id": 0, "id": 1})
        async for u in all_users_cursor:
            if u.get("id"):
                initial_members.append(u["id"])
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    initial_members = list(set(initial_members))
    doc = {
        "id": _uid(),
        "name": PROCUREMENT_CHANNEL_NAME,
        "description": "Notifikasi otomatis approval/penolakan permintaan pengadaan.",
        "type": "public",
        "members": initial_members,
        "department": None,
        "created_by": "system",
        "created_by_name": "System",
        "archived": False,
        "created_at": _now(),
        "updated_at": _now(),
        "last_message": None,
        "last_message_at": None,
        "is_system": True,
    }
    await db.comm_channels.insert_one(dict(doc))
    return doc


async def _notify_procurement_event(
    db,
    pr: dict,
    actor: dict,
    action: str,            # "approved" | "rejected" | "final_approved"
    new_status: str,
    comment: str = "",
):
    """Post system message ke channel #procurement-notifications dan DM ke requester.

    Best-effort: error apapun di-log tapi tidak mem-block flow approval utama.
    """
    try:
        # Lazy import untuk hindari circular dependency
        from routes.dewi_communication import comm_manager  # type: ignore

        req_no = pr.get("request_number", "")
        title = pr.get("title", "")
        requester_id = pr.get("requested_by")
        status_label = STATUS_LABELS.get(new_status, new_status)
        action_label = {
            "approved": "✅ Disetujui",
            "rejected": "❌ Ditolak",
            "final_approved": "🎉 Disetujui (Final)",
        }.get(action, action.capitalize())

        body_lines = [
            f"{action_label} — Permintaan Pengadaan",
            f"No: {req_no}",
            f"Judul: {title}",
            f"Status: {status_label}",
            f"Oleh: {actor.get('name', '') or actor.get('email', '')}",
        ]
        if comment:
            body_lines.append(f"Catatan: {comment}")
        content = "\n".join(body_lines)

        # 1) Post ke channel #procurement-notifications
        try:
            ch = await _get_or_create_procurement_channel(db)
            ch_msg = {
                "id": _uid(),
                "channel_id": ch["id"],
                "conversation_id": None,
                "sender_id": "system",
                "sender_name": "System",
                "sender_email": "",
                "content": content,
                "message_type": "system_procurement",
                "file_url": None,
                "file_name": None,
                "file_size": None,
                "reply_to_id": None,
                "reply_to_preview": None,
                "reactions": {},
                "edited": False,
                "deleted": False,
                "meta": {
                    "pr_id": pr.get("id"),
                    "request_number": req_no,
                    "action": action,
                    "new_status": new_status,
                },
                "created_at": _now(),
                "updated_at": _now(),
            }
            await db.comm_messages.insert_one(ch_msg)
            await db.comm_channels.update_one(
                {"id": ch["id"]},
                {"$set": {
                    "last_message": content.split("\n", 1)[0],
                    "last_message_at": _now(),
                    "updated_at": _now(),
                }},
            )
            # Pastikan requester ada di channel agar bisa melihat
            if requester_id and requester_id not in (ch.get("members") or []):
                await db.comm_channels.update_one(
                    {"id": ch["id"]},
                    {"$addToSet": {"members": requester_id}},
                )
            members = list(set((ch.get("members") or []) + ([requester_id] if requester_id else [])))
            msg_out = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in ch_msg.items() if k != "_id"}
            await comm_manager.broadcast_to_users(members, {
                "type": "new_message",
                "data": {"message": msg_out, "channel_id": ch["id"], "scope": "channel"},
            })
        except Exception as e:
            logger.warning(f"[procurement-notif] gagal post ke channel: {e}")

        # 2) DM ke requester (jika bukan dirinya sendiri)
        if requester_id and requester_id != actor.get("id"):
            try:
                from routes.dewi_communication import _get_or_create_conversation  # type: ignore
                conv = await _get_or_create_conversation(db, "system", requester_id)
                dm_msg = {
                    "id": _uid(),
                    "channel_id": None,
                    "conversation_id": conv["id"],
                    "sender_id": "system",
                    "sender_name": "System",
                    "sender_email": "",
                    "content": content,
                    "message_type": "system_procurement",
                    "file_url": None,
                    "file_name": None,
                    "file_size": None,
                    "reply_to_id": None,
                    "reply_to_preview": None,
                    "reactions": {},
                    "edited": False,
                    "deleted": False,
                    "meta": {
                        "pr_id": pr.get("id"),
                        "request_number": req_no,
                        "action": action,
                        "new_status": new_status,
                    },
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                await db.comm_messages.insert_one(dm_msg)
                await db.comm_conversations.update_one(
                    {"id": conv["id"]},
                    {"$set": {
                        "last_message": content.split("\n", 1)[0],
                        "last_message_at": _now(),
                        "updated_at": _now(),
                    }},
                )
                dm_out = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dm_msg.items() if k != "_id"}
                await comm_manager.send_to_user(requester_id, {
                    "type": "new_message",
                    "data": {"message": dm_out, "conv_id": conv["id"], "scope": "dm"},
                })
            except Exception as e:
                logger.warning(f"[procurement-notif] gagal DM requester: {e}")
    except Exception as e:
        # Top-level safety net — jangan pernah mem-block flow approval karena notif
        logger.warning(f"[procurement-notif] error tak terduga: {e}")


def _ser(doc):
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != '_id'}
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
        elif isinstance(v, list):
            doc[k] = [_ser(i) if isinstance(i, dict) else i for i in v]
    return doc


STATUS_FLOW = {
    "draft":            ["submitted", "cancelled"],
    "submitted":        ["dept_approved", "rejected", "cancelled"],
    "dept_approved":    ["finance_approved", "rejected"],
    "finance_approved": ["approved"],
    "approved":         ["in_procurement", "completed"],
    "in_procurement":   ["completed"],
    "rejected":         [],
    "completed":        [],
    "cancelled":        [],
}

STATUS_LABELS = {
    "draft":            "Draft",
    "submitted":        "Menunggu Persetujuan Dept",
    "dept_approved":    "Menunggu Persetujuan Finance",
    "finance_approved": "Menunggu Final Approval",
    "approved":         "Disetujui",
    "in_procurement":   "Sedang Pengadaan",
    "completed":        "Selesai",
    "rejected":         "Ditolak",
    "cancelled":        "Dibatalkan",
}


async def _gen_pr_number(db, requested: str = "") -> str:
    """Nomor PR lewat SATU PINTU kebijakan penomoran (SESI #19).

    Dulu selalu otomatis (`gen_prefixed_number`), sehingga owner yang memindah
    "Permintaan Pengadaan (PR)" ke MANUAL di Administrasi Sistem → Penomoran Dokumen
    melihat setelannya tersimpan tetapi PR baru tetap bernomor otomatis.
    `issue_number` menegakkan modenya: MANUAL → nomor wajib diisi & wajib mengikuti
    pola; OTOMATIS → nomor ketikan ditolak dengan menyebut nomor yang akan dipakai.
    """
    return await issue_number(db, PR_DOCNUM_KEY, requested=requested)


# ─── Dashboard ────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def procurement_dashboard(request: Request):
    user = await require_auth(request)
    db = get_db()
    total = await db.dewi_procurement_requests.count_documents({})
    pending = await db.dewi_procurement_requests.count_documents(
        {"status": {"$in": ["submitted", "dept_approved", "finance_approved"]}}
    )
    approved = await db.dewi_procurement_requests.count_documents({"status": "approved"})
    completed = await db.dewi_procurement_requests.count_documents({"status": "completed"})
    rejected = await db.dewi_procurement_requests.count_documents({"status": "rejected"})
    my_requests = await db.dewi_procurement_requests.count_documents({"requested_by": user["id"]})
    # "Menunggu persetujuan SAYA" — dulu menghitung SEMUA PR di status
    # submitted/dept_approved tanpa peduli apakah user memang approvernya (dan
    # melewatkan finance_approved sama sekali), jadi angkanya menyesatkan.
    # Sekarang memakai mesin yang sama dengan inbox.
    _pending = await db.dewi_procurement_requests.find(
        {"status": {"$in": list(PENDING_STATUSES)}}, {"_id": 0}
    ).to_list(500)
    _cfg = await _chain_config(db)
    _u = await _with_department(db, user)
    try:
        from core.pr_approval import pending_for_user
        my_pending_approval = len(await pending_for_user(db, user))
    except Exception:  # noqa: BLE001
        # F13 — DULU jatuh ke perhitungan lama TANPA SUARA. Bahayanya spesifik:
        # angka badge di dashboard akan dihitung dengan ATURAN BERBEDA dari inbox
        # (`pending_for_user` adalah SSOT-nya). Jadi dashboard bilang "3 menunggu
        # persetujuan Anda" sementara inbox-nya kosong — dan karena mesinnya
        # rusak diam-diam, tidak ada yang tahu mana yang benar. Fallback tetap
        # dipakai supaya dashboard tidak 500, tapi kini bersuara.
        logger.exception(
            "[procurement] mesin persetujuan SSOT (core.pr_approval.pending_for_user) "
            "gagal — badge dashboard memakai perhitungan cadangan yang bisa BERBEDA "
            "dari inbox; user=%s", (user or {}).get('id'))
        my_pending_approval = sum(
            1 for p in _pending
            if _eval_approval(p, _u, _pr_chain(p, _cfg))["can_approve"]
        )

    # Total value approved this month
    month_start = f"{date.today().strftime('%Y-%m')}-01"
    agg = await db.dewi_procurement_requests.aggregate([
        {"$match": {"status": {"$in": ["approved", "completed"]}, "submitted_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_estimated"}}}
    ]).to_list(1)
    total_value_approved = agg[0]["total"] if agg else 0

    recent = await db.dewi_procurement_requests.find(
        {}, {"_id": 0, "id": 1, "request_number": 1, "title": 1, "status": 1, "total_estimated": 1,
             "created_at": 1, "requested_by_name": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    return {
        "summary": {"total": total, "pending": pending, "approved": approved,
                    "completed": completed, "rejected": rejected,
                    "my_requests": my_requests, "my_pending_approval": my_pending_approval,
                    "total_value_approved_this_month": round(total_value_approved, 2)},
        "recent": [_ser(r) for r in recent],
    }


# ─── Requests CRUD ────────────────────────────────────────────────────────

@router.get("/requests")
async def list_requests(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    my_only: bool = Query(False),
    search: Optional[str] = None,
    priority: Optional[str] = None,
    # F13-B (sesi #12) — pengurutan WAJIB dikerjakan SERVER.
    # Kalau layar mengurutkan sendiri, ia hanya bisa mengurutkan halaman yang
    # sedang dibuka. Pertanyaan yang membuat kolom ini ada — "PR mana yang
    # nilainya PALING BESAR?" — akan dijawab dengan urutan 15 baris pertama,
    # dan jawabannya terlihat meyakinkan padahal salah. Itu lebih berbahaya
    # daripada tidak ada pengurutan sama sekali.
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    user = await require_auth(request)
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if my_only:
        query["requested_by"] = user["id"]
    if priority:
        query["priority"] = priority
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"request_number": {"$regex": search, "$options": "i"}},
        ]
    total = await db.dewi_procurement_requests.count_documents(query)
    skip = (page - 1) * limit
    # Daftar putih: nama kolom datang dari browser, jadi ia tidak boleh langsung
    # masuk ke kueri. Kolom yang tidak dikenal jatuh ke `created_at` — diam-diam
    # mengurutkan dengan kolom karangan akan menghasilkan urutan acak yang
    # terlihat sah.
    _SORTABLE = {
        "created_at", "submitted_at", "needed_by", "total_estimated",
        "request_number", "title", "priority", "status", "department",
        "request_type", "requested_by_name",
    }
    _key = sort_by if sort_by in _SORTABLE else "created_at"
    _dir = -1 if sort_dir == "desc" else 1
    items = await db.dewi_procurement_requests.find(
        query, {"_id": 0}
    ).sort(_key, _dir).skip(skip).limit(limit).to_list(limit)
    # Flag izin dari SERVER (SSOT). Frontend dilarang menghitung ulang daftar
    # peran — itulah penyebab tombol Setujui/Tolak hilang bagi approver asli.
    cfg = await _chain_config(db)
    out_items = []
    _u = await _with_department(db, user)
    for i in items:
        o = _ser(i)
        o.update(_eval_approval(i, _u, _pr_chain(i, cfg)))
        out_items.append(o)
    return {
        "items": out_items,
        "pagination": {"page": page, "page_size": limit, "total": total,
                       "total_pages": math.ceil(total / limit) if total else 1}
    }


async def _norm_pr_items(db, raw_items):
    """Normalisasi item PR **dengan dukungan material master + satuan SSOT**.

    2026-08-06 (Portal Pengadaan) — sebelumnya item PR hanya teks bebas
    (`name`, `unit` default "pcs"), sehingga saat PR dijadikan PO barisnya
    kehilangan `material_id` dan satuan tidak pernah dikonversi. Sekarang:

      · `material_id` OPSIONAL — bila diisi, kode/nama/satuan dasar diambil dari
        master dan qty dikonversi ke satuan dasar (INV-UOM-2).
      · `uom` = satuan beli yang diminta pemohon (mis. "ktn"). `qty` tetap
        angka yang diketik pemohon dalam satuan itu; `qty_base` hasil konversi.
      · `estimated_price` = harga per satuan `uom`; `estimated_price_base`
        harga per satuan dasar (INV-UOM-1).
    """
    raw_items = list(raw_items or [])
    ids = [i.get("material_id") for i in raw_items if i.get("material_id")]
    mats = await db.rahaza_materials.find(
        {"id": {"$in": list(set(ids))}}, {"_id": 0}).to_list(len(ids) + 5) if ids else []
    mmap = {m["id"]: m for m in mats}

    out = []
    for i in raw_items:
        mid = i.get("material_id") or None
        mat = mmap.get(mid) if mid else None
        if mid and not mat:
            raise HTTPException(400, f"Material {mid} tidak ditemukan di master.")

        name = (i.get("name") or (mat or {}).get("name") or "").strip()
        if not name:
            continue
        base = _uom.base_uom_of(mat) if mat else (
            _bom_uom.norm_unit(i.get("uom") or i.get("unit")) or "pcs")
        uom_in = _bom_uom.norm_unit(i.get("uom") or i.get("unit") or base) or base
        if mat:
            try:
                factor, source = _bom_uom.factor_to_base(mat, uom_in)
            except _uom.UomError as e:
                raise HTTPException(400, f"{mat.get('code') or mid}: {e}")
        else:
            factor, source = 1.0, "freeform"

        qty = float(i.get("qty") or 1)
        price = float(i.get("estimated_price") or 0)
        qty_base = round(qty * factor, 4)
        price_base = round(price / factor, 6) if factor else price
        out.append({
            "id": i.get("id") or _uid(),
            "material_id": mid,
            "material_code": (mat or {}).get("code") or i.get("material_code") or "",
            "name": name,
            "specification": i.get("specification", ""),
            "qty": round(qty, 6),
            "unit": uom_in,          # kompatibilitas lama (dulu teks bebas)
            "uom": uom_in,
            "uom_factor": round(float(factor), 8),
            "uom_source": source,
            "base_uom": base,
            "qty_base": qty_base,
            "estimated_price": round(price, 4),
            "estimated_price_base": price_base,
            "total_price": round(qty * price, 2),
            "suggested_supplier_id": i.get("suggested_supplier_id") or None,
            "notes": i.get("notes", ""),
        })
    return out


async def build_pr_doc(db, user: dict, body: dict, *, origin: str = "",
                       origin_week: str = "") -> dict:
    """Susun dokumen PR (BELUM disimpan) — SATU definisi untuk semua jalur.

    2026-08-23 (sesi #33) — dipakai `POST /requests` (diketik manual) **dan**
    Daftar Belanja Mingguan (`core/shopping_list` → `/api/rahaza/shopping-list/
    create-pr`). Dulu jalur kedua tidak ada; kalau ia menyusun dokumennya sendiri,
    satuan/harga-per-satuan-dasar/penomoran bisa menyimpang dari PR manual tanpa
    ada yang tahu. `origin` + `origin_week` = jejak asal usul (dipakai layar
    riwayat belanja mingguan & penjaga anti dobel belanja).
    """
    body = body or {}
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "Judul permintaan wajib diisi.")
    items = await _norm_pr_items(db, body.get("items", []))
    if not items:
        raise HTTPException(400, "Minimal 1 item harus diisi.")

    total_est = sum(float(i["total_price"]) for i in items)
    pr_number = await _gen_pr_number(db, (body.get("request_number") or "").strip())
    doc = {
        "id": _uid(),
        "request_number": pr_number,
        "title": title,
        "description": (body.get("description") or "").strip(),
        "items": items,
        "total_estimated": round(total_est, 2),
        "justification": (body.get("justification") or "").strip(),
        "priority": body.get("priority", "medium"),  # low | medium | high | urgent
        "request_type": body.get("request_type", "asset"),  # asset | consumable | service | other
        "department": (body.get("department") or user.get("department", "")).strip(),
        "needed_by": body.get("needed_by") or None,
        "suggested_supplier_id": body.get("suggested_supplier_id") or None,
        "requested_by": user["id"],
        "requested_by_name": user.get("name", ""),
        "status": "draft",
        "approval_steps": [],
        # Rantai persetujuan baru dibekukan saat submit (nilai PR masih bisa
        # berubah selama draft), jadi di sini masih kosong.
        "approval_chain": [],
        "current_approver_stage": None,
        "current_approver_role": None,
        "submitted_at": None,
        "approved_at": None,
        "rejected_at": None,
        "rejection_reason": None,
        "linked_asset_ids": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    if origin:
        doc["origin"] = origin
        doc["origin_week"] = origin_week
    return doc


@router.post("/requests")
async def create_request(request: Request):
    user = await require_auth(request)
    db = get_db()
    doc = await build_pr_doc(db, user, await request.json())
    await db.dewi_procurement_requests.insert_one(doc)
    return _ser(doc)


@router.get("/requests/{req_id}")
async def get_request(req_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    user = await _with_department(db, user)
    cfg = await _chain_config(db)
    out = _ser(req)
    out.update(_eval_approval(req, user, _pr_chain(req, cfg)))
    return out


@router.put("/requests/{req_id}")
async def update_request(req_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] != "draft":
        raise HTTPException(400, "Hanya request berstatus draft yang bisa diubah.")
    if req["requested_by"] != user["id"] and user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Tidak diizinkan.")
    body = await request.json()
    update = {}
    if "title" in body:
        update["title"] = body["title"]
    if "description" in body:
        update["description"] = body["description"]
    if "justification" in body:
        update["justification"] = body["justification"]
    if "priority" in body:
        update["priority"] = body["priority"]
    if "department" in body:
        update["department"] = body["department"]
    if "items" in body:
        items = await _norm_pr_items(db, body["items"])
        if not items:
            raise HTTPException(400, "Minimal 1 item harus diisi.")
        update["items"] = items
        update["total_estimated"] = round(sum(float(i["total_price"]) for i in items), 2)
    if "needed_by" in body:
        update["needed_by"] = body["needed_by"] or None
    if "suggested_supplier_id" in body:
        update["suggested_supplier_id"] = body["suggested_supplier_id"] or None
    if "request_type" in body:
        update["request_type"] = body["request_type"]
    if update:
        update["updated_at"] = _now()
        await db.dewi_procurement_requests.update_one({"id": req_id}, {"$set": update})
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════════════
# MESIN PERSETUJUAN — DIPINDAH ke `core/pr_approval.py` (2026-08-07)
# ═════════════════════════════════════════════════════════════════════════════
# Alasan: laporan owner "purchase request di aksesoris & gudang harusnya
# tersambung ke procurement". Request Pembelian Aksesoris (`acc_purchase_requests`)
# sekarang memakai aturan yang SAMA, jadi mesinnya tidak boleh tinggal di satu
# router. Daftar peran / aturan tahap yang ditulis dua kali adalah akar bug
# 2026-08-06 (inbox) dan 2026-08-07 (tombol UI) — jangan diulang.
#
# Nama-nama lama di-ekspor ulang di bawah supaya konsumen yang sudah ada
# (routes/approval_badge.py, scripts/poc_approval_chain.py) tidak perlu diubah.
from core.pr_approval import (  # noqa: E402
    DEPT_APPROVER_ROLES, FINAL_APPROVER_ROLES, FINANCE_APPROVER_ROLES,
    PENDING_STATUSES, STAGE_DEPT, STAGE_FINAL, STAGE_FINANCE, STAGE_LABELS,
    STAGE_PERMS, STAGE_ROLE_LABELS, STAGE_ROLES, STAGE_TO_STATUS,
    STATUS_TO_STAGE, SUPER_APPROVER_ROLES,
    approved_actor_ids as _approved_actor_ids,
    chain_config as _chain_config,
    compute_chain as _compute_chain,
    doc_chain as _pr_chain,
    eval_approval as _eval_approval,
    next_stage_after as _next_stage_after,
    stage_role_ok as _stage_role_ok,
    status_after_stage as _status_after_stage,
    with_department as _with_department,
)
from core.pr_approval import notify_requester as _notify_requester_bell  # noqa: E402
from core.pr_approval import notify_stage_approvers as _notify_stage_bell  # noqa: E402


async def _notify_stage_approvers(db, pr: dict, stage: str, chain: list):
    await _notify_stage_bell(db, pr, stage, chain, module_id="proc-requests",
                             number=pr.get("request_number", ""),
                             title=pr.get("title", ""),
                             kind_label="Permintaan Pengadaan")


async def _notify_requester(db, pr: dict, *, title: str, body: str, severity: str = "info"):
    await _notify_requester_bell(db, pr, title=title, body=body, severity=severity,
                                 module_id="proc-requests",
                                 number=pr.get("request_number", ""))


# ─── Workflow Actions ─────────────────────────────────────────────────────

@router.post("/requests/{req_id}/submit")
async def submit_request(req_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] != "draft":
        raise HTTPException(400, "Hanya request draft yang bisa disubmit.")
    if req["requested_by"] != user["id"] and (user.get("role") or "").lower() not in SUPER_APPROVER_ROLES:
        raise HTTPException(403, "Tidak diizinkan.")

    # Rantai persetujuan DIBEKUKAN di sini — bukan dihitung ulang setiap kali
    # dibaca. Kalau owner mengubah ambang nilai besok, PR yang sudah berjalan
    # tidak boleh tiba-tiba berpindah jalur atau kehilangan tahap yang sudah
    # disetujui (jejak audit harus tetap masuk akal).
    cfg = await _chain_config(db)
    chain = _compute_chain(req.get("total_estimated"), cfg)

    step = {
        "id": _uid(),
        "step": "submit",
        "stage": None,
        "actor_id": user["id"],
        "actor_name": user.get("name", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "submitted",
        "action_label": "Diajukan",
        "comment": "",
        "timestamp": _now().isoformat(),
    }
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "submitted", "submitted_at": _now(),
                  "approval_chain": chain,
                  "approval_thresholds": dict(cfg),
                  "current_approver_stage": STAGE_DEPT,
                  # Field lama menyimpan "dept_head" (peran yang tidak ada di app
                  # ini). Sekarang berisi KUNCI TAHAP yang sah supaya konsumen
                  # lama tidak menunjuk peran hantu.
                  "current_approver_role": STAGE_DEPT,
                  "updated_at": _now()},
         "$push": {"approval_steps": step}}
    )
    pr_after = {**req, "status": "submitted", "approval_chain": chain}
    await _notify_stage_approvers(db, pr_after, STAGE_DEPT, chain)
    return {"ok": True, "new_status": "submitted", "approval_chain": chain,
            "stage": STAGE_DEPT, "stage_label": STAGE_LABELS[STAGE_DEPT],
            "total_stages": len(chain)}


@router.post("/requests/{req_id}/approve")
async def approve_request(req_id: str, request: Request):
    """Setujui tahap persetujuan yang sedang aktif.

    Gerbangnya adalah `_eval_approval` (SSOT) — tahap, peran, larangan
    self-approval, larangan dua tahap oleh orang yang sama, dan batas departemen
    ditegakkan di satu tempat yang SAMA dengan yang dipakai inbox & tombol UI.
    admin/owner boleh menembus, tapi penembusannya dicatat.
    """
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] not in PENDING_STATUSES:
        raise HTTPException(400, f"Status '{req['status']}' tidak bisa diapprove.")

    cfg = await _chain_config(db)
    chain = _pr_chain(req, cfg)
    ev = _eval_approval(req, await _with_department(db, user), chain)
    if not ev["can_approve"]:
        raise HTTPException(403, ev["blocked_reason"]
                            or "Akses ditolak: Anda tidak berhak menyetujui permintaan ini.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — body opsional
        body = {}
    comment = (body.get("comment") or "").strip()

    stage = ev["stage"]
    next_status = _status_after_stage(chain, stage)
    next_stage = _next_stage_after(chain, stage)
    action_label = f"Disetujui — {STAGE_LABELS.get(stage, stage)}"
    if ev["is_override"]:
        action_label += " (override admin)"

    step = {
        "id": _uid(),
        "step": req["status"],          # status SEBELUM approve (kompatibilitas riwayat lama)
        "stage": stage,
        "actor_id": user["id"],
        "actor_name": user.get("name", "") or user.get("email", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "approved",
        "action_label": action_label,
        "comment": comment,
        "override": bool(ev["is_override"]),
        "override_reasons": list(ev["override_reasons"]),
        "timestamp": _now().isoformat(),
    }
    update_fields = {
        "status": next_status,
        "approval_chain": chain,
        "current_approver_stage": next_stage,
        "current_approver_role": next_stage,
        "updated_at": _now(),
    }
    if next_status == "approved":
        update_fields["approved_at"] = _now()
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": update_fields, "$push": {"approval_steps": step}}
    )
    # Notifikasi ke Communication Hub (best-effort)
    pr_after = {**req, **update_fields}
    await _notify_procurement_event(
        db,
        pr_after,
        actor=user,
        action=("final_approved" if next_status == "approved" else "approved"),
        new_status=next_status,
        comment=comment,
    )
    # Bel notifikasi: approver TAHAP BERIKUTNYA, atau pembuat PR bila sudah tuntas.
    if next_stage:
        await _notify_stage_approvers(db, pr_after, next_stage, chain)
    else:
        await _notify_requester(
            db, pr_after, severity="success",
            title="Permintaan Pengadaan Anda disetujui penuh",
            body=(f"{req.get('request_number', '')} — {req.get('title', '')}\n"
                  "Semua tahap persetujuan selesai. Langkah berikutnya: "
                  "terbitkan Purchase Order ke supplier."))
    return {"ok": True, "new_status": next_status, "stage_approved": stage,
            "stage_label": STAGE_LABELS.get(stage, ""),
            "next_stage": next_stage,
            "next_stage_label": STAGE_LABELS.get(next_stage, "") if next_stage else "",
            "override": bool(ev["is_override"]),
            "override_reasons": list(ev["override_reasons"]),
            "approval_chain": chain, "total_stages": len(chain)}


@router.post("/requests/{req_id}/reject")
async def reject_request(req_id: str, request: Request):
    """Tolak permintaan. Gerbang & pencatatan override sama dengan `/approve`."""
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] not in PENDING_STATUSES:
        raise HTTPException(400, "Tidak bisa ditolak pada status ini.")

    cfg = await _chain_config(db)
    chain = _pr_chain(req, cfg)
    ev = _eval_approval(req, await _with_department(db, user), chain)
    if not ev["can_reject"]:
        raise HTTPException(403, ev["blocked_reason"]
                            or "Akses ditolak: Anda tidak berhak menolak permintaan ini.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    reason = (body.get("reason") or body.get("comment") or "").strip()
    if not reason:
        # Dulu alasan opsional ⇒ PR ditolak tanpa penjelasan dan pemohon tidak
        # tahu apa yang harus diperbaiki.
        raise HTTPException(400, "Alasan penolakan wajib diisi agar pemohon tahu "
                                 "apa yang harus diperbaiki.")
    action_label = f"Ditolak — {STAGE_LABELS.get(ev['stage'], ev['stage'] or '')}"
    if ev["is_override"]:
        action_label += " (override admin)"
    step = {
        "id": _uid(),
        "step": req["status"],
        "stage": ev["stage"],
        "actor_id": user["id"],
        "actor_name": user.get("name", "") or user.get("email", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "rejected",
        "action_label": action_label,
        "comment": reason,
        "override": bool(ev["is_override"]),
        "override_reasons": list(ev["override_reasons"]),
        "timestamp": _now().isoformat(),
    }
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "rejected", "rejected_at": _now(), "rejection_reason": reason,
                  "current_approver_stage": None, "current_approver_role": None,
                  "updated_at": _now()},
         "$push": {"approval_steps": step}}
    )
    # Notifikasi ke Communication Hub (best-effort)
    pr_after = {**req, "status": "rejected", "rejection_reason": reason}
    await _notify_procurement_event(
        db,
        pr_after,
        actor=user,
        action="rejected",
        new_status="rejected",
        comment=reason,
    )
    await _notify_requester(
        db, pr_after, severity="warning",
        title="Permintaan Pengadaan Anda ditolak",
        body=(f"{req.get('request_number', '')} — {req.get('title', '')}\n"
              f"Tahap: {STAGE_LABELS.get(ev['stage'], '-')}\n"
              f"Alasan: {reason}"))
    return {"ok": True, "new_status": "rejected", "override": bool(ev["is_override"])}



@router.post("/requests/{req_id}/cancel")
async def cancel_request(req_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] not in ("draft", "submitted"):
        raise HTTPException(400, "Hanya request draft/submitted yang bisa dibatalkan.")
    if req["requested_by"] != user["id"] and user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Tidak diizinkan.")
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}}
    )
    return {"ok": True}


@router.post("/requests/{req_id}/complete")
async def complete_request(req_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req["status"] not in ("approved", "in_procurement"):
        raise HTTPException(400, "Request harus berstatus approved atau in_procurement.")
    body = await request.json()
    linked_asset_ids = body.get("linked_asset_ids", [])
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "completed", "linked_asset_ids": linked_asset_ids, "updated_at": _now()}}
    )
    return {"ok": True}


@router.get("/inbox")
async def get_approval_inbox(
    request: Request,
    scope: str = Query("relevant", description="relevant | all | mine"),
    department: Optional[str] = Query(None),
):
    """Kotak persetujuan GABUNGAN: semua permintaan pembelian yang menunggu
    KEPUTUSAN SAYA — Permintaan Pengadaan **dan** Request Pembelian Aksesoris.

    2026-08-07 (laporan owner "purchase request aksesoris/gudang harusnya
    tersambung ke procurement"): `acc_purchase_requests` dulu punya alur
    persetujuan sendiri TANPA RBAC (siapa pun yang login bisa menyetujui, bahkan
    pembuatnya) dan tidak pernah muncul di sini. Sekarang keduanya memakai satu
    mesin `core/pr_approval.py`, jadi pekerjaan pembelian tidak lagi tersebar di
    dua inbox. Setiap item membawa `kind` ("pr"/"acc_pr") dan `api_base` supaya
    UI tahu ke endpoint mana aksi disetujui/ditolak dikirim.

    scope:
      relevant (bawaan) — hanya yang benar-benar bisa saya setujui sekarang
      mine              — permintaan saya sendiri yang sedang menunggu persetujuan
      all               — semua PR pending (admin/owner saja; selain itu jatuh ke relevant)
    """
    user = await require_auth(request)
    db = get_db()
    is_admin = (user.get("role") or "").lower() in SUPER_APPROVER_ROLES

    if scope == "relevant" or (scope == "all" and not is_admin):
        from core.pr_approval import pending_for_user
        items = await pending_for_user(db, user)
        if department and is_admin:
            items = [i for i in items if i.get("department") == department]
        return items

    query = {"status": {"$in": list(PENDING_STATUSES)}}
    if scope == "mine":
        query["requested_by"] = user["id"]
    if department and is_admin:
        query["department"] = department

    items = await db.dewi_procurement_requests.find(
        query, {"_id": 0}
    ).sort("submitted_at", 1).to_list(500)

    cfg = await _chain_config(db)
    result = []
    _u = await _with_department(db, user)
    for i in items:
        ev = _eval_approval(i, _u, _pr_chain(i, cfg))
        out = _ser(i)
        out.update(ev)
        out.update({"kind": "pr", "kind_label": "Pengadaan",
                    "api_base": "/api/procurement/requests",
                    "module_id": "proc-requests"})
        result.append(out)

    if scope == "mine":
        # Request Aksesoris milik saya juga harus bisa dilacak di satu tempat.
        from core.pr_approval import acc_material_map, normalize_acc_pr
        accs = await db.acc_purchase_requests.find(
            {"status": "Submitted", "requested_by": user["id"]}, {"_id": 0}
        ).to_list(500)
        cfgc = cfg
        mats = await acc_material_map(db, accs)
        for d in accs:
            chain = _pr_chain(d, cfgc)
            ev = _eval_approval(d, _u, chain,
                                stage=d.get("current_approver_stage") or STAGE_DEPT)
            out = _ser(normalize_acc_pr(d, mats))
            out.update(ev)
            result.append(out)
    return result


@router.get("/requests/{req_id}/timeline")
async def get_request_timeline(req_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    cfg = await _chain_config(db)
    ev = _eval_approval(req, user, _pr_chain(req, cfg))
    return {"steps": req.get("approval_steps", []), "current_status": req["status"],
            "chain": ev["chain"], "approval_chain": ev["approval_chain"],
            "total_stages": ev["total_stages"], "stage": ev["stage"],
            "stage_label": ev["stage_label"],
            "next_approver_label": ev["next_approver_label"]}


@router.delete("/requests/{req_id}")
async def delete_request(req_id: str, request: Request):
    """Hapus permintaan.

    Dibuat 2026-08-07: `scripts/verify_pr_inbox_roles.py` memanggil endpoint ini
    untuk membersihkan PR uji, tetapi endpoint-nya TIDAK PERNAH ADA (404 ditelan
    karena best-effort) — itulah sebabnya PR uji `UJI INBOX — kancing plastik`
    menumpuk di data demo. Aturan:
      · pemohon boleh menghapus PR-nya sendiri selama masih `draft`;
      · admin/owner boleh menghapus PR apa pun yang BELUM punya PO terkait
        (PR yang sudah menghasilkan PO tidak boleh hilang dari jejak audit).
    """
    user = await require_auth(request)
    db = get_db()
    req = await db.dewi_procurement_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    is_admin = (user.get("role") or "").lower() in SUPER_APPROVER_ROLES
    if not is_admin:
        if req.get("requested_by") != user.get("id"):
            raise HTTPException(403, "Hanya pemohon atau admin yang boleh menghapus permintaan ini.")
        if req.get("status") != "draft":
            raise HTTPException(400, "Hanya permintaan berstatus draft yang bisa dihapus. "
                                     "Gunakan Batalkan untuk permintaan yang sudah diajukan.")
    elif req.get("linked_po_id") or req.get("linked_po_number"):
        raise HTTPException(400, "Permintaan ini sudah menghasilkan Purchase Order "
                                 f"({req.get('linked_po_number')}) — tidak boleh dihapus.")
    await db.dewi_procurement_requests.delete_one({"id": req_id})
    logger.info("[procurement] PR %s dihapus oleh %s (%s)",
                req.get("request_number"), user.get("email"), user.get("role"))
    return {"ok": True, "deleted": req.get("request_number")}


# ─── Create PO from Approved PR ──────────────────────────────────────────────

async def _gen_po_number_proc(db) -> str:
    from datetime import date as _date
    prefix = f"PO-{_date.today().strftime('%Y%m%d')}-"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1 -> dup/E11000; po_number is unique-indexed)
    return await gen_prefixed_number(db, "rahaza_purchase_orders", "po_number", prefix, 3)


@router.post("/requests/{req_id}/create-po")
async def create_po_from_pr(req_id: str, request: Request):
    """Buat Purchase Order (PO) dari PR yang sudah Approved.

    2026-08-06 (Portal Pengadaan) — versi lama membuang `material_id`, tidak
    mengenal Master Supplier, dan tidak mengonversi satuan. Akibatnya PO hasil PR
    tidak bisa masuk stok kanonik saat GR (item tanpa `material_id` dilewati oleh
    `warehouse.py`) dan harganya bisa salah kali/bagi. Sekarang PR→PO membawa:
    `material_id`, satuan beli + faktor, harga per satuan dasar, dan `supplier_id`.

    Body:
        supplier_id            (str, disarankan — Master Supplier)
        vendor_name            (str, dipakai bila supplier_id kosong)
        vendor_contact / vendor_address (str, optional — override)
        expected_delivery_date (str YYYY-MM-DD, optional)
        notes                  (str, optional)
        items_override         (list, optional: [{item_id, uom, qty, unit_cost}])
    """
    user = await require_auth(request)
    db = get_db()

    pr = await db.dewi_procurement_requests.find_one({"id": req_id})
    if not pr:
        raise HTTPException(404, "PR tidak ditemukan.")
    if pr["status"] != "approved":
        raise HTTPException(400, f"PR harus berstatus 'approved' untuk dibuat PO. Status saat ini: {pr['status']}")
    if pr.get("linked_po_id"):
        raise HTTPException(400, f"PR ini sudah memiliki PO terhubung: {pr.get('linked_po_number', pr['linked_po_id'])}")

    body = await request.json()

    # Import di dalam fungsi: hindari siklus impor antar modul route.
    from routes.rahaza_po import (
        _norm_po_items as _po_items, _resolve_supplier as _po_supplier,
        _gen_po_number as _po_number, _enrich_po as _po_enrich,
    )

    sup_fields = await _po_supplier(db, body)
    if not sup_fields.get("supplier_id") and not sup_fields.get("vendor_name"):
        raise HTTPException(400, "supplier_id (Master Supplier) atau vendor_name wajib diisi.")

    override = {}
    for ov in (body.get("items_override") or []):
        if isinstance(ov, dict) and ov.get("item_id"):
            override[ov["item_id"]] = ov

    from datetime import date as _date
    raw_items = []
    for it in (pr.get("items") or []):
        ov = override.get(it.get("id")) or {}
        raw_items.append({
            "material_id": it.get("material_id") or None,
            "description": it.get("name", ""),
            "specification": it.get("specification", ""),
            "uom": ov.get("uom") or it.get("uom") or it.get("unit") or "pcs",
            "qty_input": float(ov.get("qty") if ov.get("qty") not in (None, "")
                               else it.get("qty", 1)),
            "unit_cost_input": float(ov.get("unit_cost") if ov.get("unit_cost") not in (None, "")
                                     else it.get("estimated_price", 0)),
            "notes": it.get("notes", ""),
        })
    po_items = await _po_items(db, raw_items)
    if not po_items:
        raise HTTPException(400, "PR tidak punya item yang bisa dijadikan PO.")

    po_number = await _po_number(db)
    po_total = round(sum(float(i["qty_ordered"]) * float(i["unit_cost"])
                         for i in po_items), 2)
    pr_total = round(float(pr.get("total_estimated") or 0), 2)
    # ── LUBANG YANG DITUTUP 2026-08-07 ──────────────────────────────────────
    # `items_override` boleh mengubah qty DAN unit_cost tanpa batas, sehingga PR
    # Rp 800.000 yang sudah disetujui bisa diterbitkan menjadi PO Rp 800.000.000
    # ke supplier — uang yang dikomitmenkan jauh melebihi yang pernah disetujui.
    # Sekarang selisihnya DICATAT di dokumen; `core.pr_approval.po_chain()`
    # memakai penanda ini untuk MEMAKSA rantai persetujuan PENUH (bukan 1 tahap),
    # dan kotak persetujuan menampilkan peringatannya ke approver.
    # Toleransi 0,5% mengikuti ambang varians 3-Way Match (pembulatan satuan).
    exceeds = po_total > pr_total * 1.005 if pr_total > 0 else po_total > 0
    po_doc = {
        "id": _uid(),
        "po_number": po_number,
        "from_pr_id": pr["id"],
        "from_pr_number": pr.get("request_number", ""),
        **sup_fields,
        "po_date": _date.today().isoformat(),
        "expected_delivery_date": body.get("expected_delivery_date") or pr.get("needed_by") or None,
        "items": po_items,
        "total_value": po_total,
        "status": "draft",
        "notes": (body.get("notes") or "").strip() or f"Dibuat dari PR {pr.get('request_number','')}",
        # Jejak perbandingan nilai: dipakai memaksa rantai persetujuan penuh
        # dan menampilkan peringatan ke approver di kotak persetujuan.
        "pr_approved_value": pr_total,
        "exceeds_pr_value": bool(exceeds),
        "approval_flow_key": "value_based",
        "approval_steps": [],
        "approval_chain": [],
        "current_approver_stage": None,
        "requested_by": user["id"],
        # CATATAN SENGAJA: `department` TIDAK diisi untuk PO. Aturan departemen di
        # `eval_approval` hanya berlaku bila dokumen DAN user punya departemen;
        # kalau PO mewarisi departemen PR (mis. "Gudang"), maka `admin_pengadaan`
        # (departemen Pengadaan) justru TERBLOKIR menyetujui PO pengadaan.
        # Departemen asal disimpan hanya untuk INFORMASI.
        "source_department": (pr.get("department") or "").strip(),
        "approvals": [],
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_purchase_orders.insert_one(po_doc)

    # Update PR: set in_procurement + link
    await db.dewi_procurement_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "in_procurement",
            "linked_po_id": po_doc["id"],
            "linked_po_number": po_number,
            "updated_at": _now(),
        }}
    )

    out = {k: v for k, v in po_doc.items() if k != "_id"}
    await _po_enrich(db, out)
    return _ser(out)



# ─── Supporting Data: Request Types ─────────────────────────────────────────
# Extended request_type list (Phase 5B)
PROCUREMENT_REQUEST_TYPES = [
    {'value': 'asset',        'label': 'Aset Tetap',          'description': 'Pembelian aset tetap (mesin, peralatan, furnitur, elektronik)'},
    {'value': 'consumable',   'label': 'Barang Habis Pakai',  'description': 'Bahan habis pakai (ATK, bahan baku minor, supplies)'},
    {'value': 'service',      'label': 'Jasa',                'description': 'Pengadaan jasa atau tenaga ahli'},
    {'value': 'subscription', 'label': 'Langganan / SaaS',    'description': 'Langganan software, SaaS, atau layanan berulang'},
    {'value': 'maintenance',  'label': 'Kontrak Maintenance',  'description': 'Kontrak maintenance/servis peralatan atau fasilitas'},
    {'value': 'rental',       'label': 'Sewa Alat/Fasilitas', 'description': 'Sewa alat, kendaraan, atau fasilitas operasional'},
    {'value': 'project',      'label': 'Berbasis Proyek',     'description': 'Pengadaan untuk kebutuhan proyek tertentu'},
    {'value': 'other',        'label': 'Lainnya',             'description': 'Jenis pengadaan lainnya yang tidak termasuk kategori di atas'},
]


@router.get('/request-types')
async def get_request_types(request: Request):
    """
    Daftar jenis pengadaan (request_type) yang tersedia.
    Digunakan untuk dropdown di form buat PR.
    RBAC read-guard (BUG-AUTH-1): butuh akses portal finance/assets/management.
    """
    await require_portal(request, "finance", "assets", "management")
    return {'items': PROCUREMENT_REQUEST_TYPES}