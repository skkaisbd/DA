"""
PT Rahaza ERP — SOP Inline (Phase 18D)

Master SOP per model×process.
Admin bisa buat/edit/hapus SOP + upload lampiran (gambar, PDF).
Operator bisa baca via GET /by-context.

Data model (collection `rahaza_model_process_sop`):
  id, model_id, model_code, process_id, process_code,
  title, content_markdown, attachments[], version,
  active, created_at, updated_at

Endpoints:
  GET  /api/rahaza/sop               — list all SOPs (auth)
  POST /api/rahaza/sop               — create SOP (admin)
  GET  /api/rahaza/sop/by-context    — get active SOP by model+process (auth)
  GET  /api/rahaza/sop/{id}          — get single SOP (auth)
  PUT  /api/rahaza/sop/{id}          — update SOP (admin)
  DELETE /api/rahaza/sop/{id}        — soft-delete SOP (admin)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/sop", tags=["SOP"])


def _ser(doc: dict) -> dict:
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


async def _require_admin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in ("admin", "superadmin", "owner", "manager_production"):
        raise HTTPException(403, "Butuh role Admin / Manager Produksi untuk mengelola SOP")
    return user


async def _enrich_sop(db, sop: dict) -> dict:
    """Enrich SOP with model and process names."""
    model_id = sop.get("model_id")
    process_id = sop.get("process_id")
    if model_id and not sop.get("model_code"):
        m = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0, "code": 1, "name": 1})
        if m:
            sop["model_code"] = m.get("code", "")
            sop["model_name"] = m.get("name", "")
    if process_id and not sop.get("process_code"):
        p = await db.rahaza_processes.find_one({"id": process_id}, {"_id": 0, "code": 1, "name": 1})
        if p:
            sop["process_code"] = p.get("code", "")
            sop["process_name"] = p.get("name", "")
    return sop


@router.get("")
async def list_sops(
    request: Request,
    model_id: str = None,
    process_id: str = None,
    active_only: bool = False,
):
    """List all SOPs with optional filters."""
    await require_auth(request)
    db = get_db()
    query = {}
    if model_id:
        query["model_id"] = model_id
    if process_id:
        query["process_id"] = process_id
    if active_only:
        query["active"] = True
    sops = await db.rahaza_model_process_sop.find(query, {"_id": 0}).sort("model_code", 1).to_list(500)
    enriched = []
    for s in sops:
        s = await _enrich_sop(db, _ser(s))
        enriched.append(s)
    return {"sops": enriched, "total": len(enriched)}


@router.get("/by-context")
async def get_sop_by_context(
    request: Request,
    model_id: str = None,
    process_id: str = None,
):
    """Get active SOP for a specific model+process context."""
    await require_auth(request)
    if not model_id or not process_id:
        raise HTTPException(400, "Butuh model_id dan process_id")
    db = get_db()
    sop = await db.rahaza_model_process_sop.find_one(
        {"model_id": model_id, "process_id": process_id, "active": True},
        {"_id": 0},
    )
    if not sop:
        return {"sop": None, "found": False}
    sop = await _enrich_sop(db, _ser(sop))
    return {"sop": sop, "found": True}


@router.get("/{sop_id}")
async def get_sop(sop_id: str, request: Request):
    """Get a single SOP by ID."""
    await require_auth(request)
    db = get_db()
    sop = await db.rahaza_model_process_sop.find_one({"id": sop_id}, {"_id": 0})
    if not sop:
        raise HTTPException(404, "SOP tidak ditemukan")
    sop = await _enrich_sop(db, _ser(sop))
    return sop


@router.post("")
async def create_sop(request: Request):
    """Create a new SOP."""
    user = await _require_admin(request)
    body = await request.json()
    db = get_db()

    model_id = body.get("model_id") or ""
    process_id = body.get("process_id") or ""
    if not model_id or not process_id:
        raise HTTPException(400, "model_id dan process_id wajib diisi")

    # Check for duplicates
    existing = await db.rahaza_model_process_sop.find_one(
        {"model_id": model_id, "process_id": process_id, "active": True}, {"_id": 0, "id": 1}
    )
    if existing:
        raise HTTPException(409, f"SOP aktif untuk model+proses ini sudah ada (id={existing['id']}). Update yang ada atau deaktivasi dulu.")

    # Enrich with codes/names
    model_code, model_name = "", ""
    m = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0, "code": 1, "name": 1})
    if m:
        model_code = m.get("code", "")
        model_name = m.get("name", "")

    process_code, process_name = "", ""
    p = await db.rahaza_processes.find_one({"id": process_id}, {"_id": 0, "code": 1, "name": 1})
    if p:
        process_code = p.get("code", "")
        process_name = p.get("name", "")

    now = datetime.now(timezone.utc)
    sop = {
        "id": str(uuid.uuid4()),
        "model_id": model_id,
        "model_code": model_code,
        "model_name": model_name,
        "process_id": process_id,
        "process_code": process_code,
        "process_name": process_name,
        "title": (body.get("title") or f"SOP {model_code} · {process_code}").strip()[:200],
        "content_markdown": (body.get("content_markdown") or "").strip(),
        "sam_minutes": float(body["sam_minutes"]) if body.get("sam_minutes") not in (None, "") else None,
        "target_pcs_per_operator": int(body["target_pcs_per_operator"]) if body.get("target_pcs_per_operator") not in (None, "") else None,
        "attachments": body.get("attachments") or [],  # list of {name, url, type}
        "version": 1,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "created_by": user.get("name") or "",
    }
    await db.rahaza_model_process_sop.insert_one(sop)
    sop.pop("_id", None)
    logger.info(f"[sop] created id={sop['id']} model={model_code} process={process_code}")
    return _ser(sop)


@router.put("/{sop_id}")
async def update_sop(sop_id: str, request: Request):
    """Update an existing SOP."""
    await _require_admin(request)
    body = await request.json()
    db = get_db()
    sop = await db.rahaza_model_process_sop.find_one({"id": sop_id}, {"_id": 0})
    if not sop:
        raise HTTPException(404, "SOP tidak ditemukan")

    update = {"updated_at": datetime.now(timezone.utc)}
    if "title" in body:
        update["title"] = str(body["title"]).strip()[:200]
    if "content_markdown" in body:
        update["content_markdown"] = str(body["content_markdown"]).strip()
    if "sam_minutes" in body:
        update["sam_minutes"] = float(body["sam_minutes"]) if body.get("sam_minutes") not in (None, "") else None
    if "target_pcs_per_operator" in body:
        update["target_pcs_per_operator"] = int(body["target_pcs_per_operator"]) if body.get("target_pcs_per_operator") not in (None, "") else None
    if "attachments" in body:
        update["attachments"] = body["attachments"] or []
    if "active" in body:
        update["active"] = bool(body["active"])
    if update.get("active") != sop.get("active") or any(k in update for k in ["title", "content_markdown"]):
        update["version"] = sop.get("version", 1) + 1

    await db.rahaza_model_process_sop.update_one({"id": sop_id}, {"$set": update})
    updated_sop = await db.rahaza_model_process_sop.find_one({"id": sop_id}, {"_id": 0})
    return _ser(updated_sop)


@router.delete("/{sop_id}")
async def delete_sop(sop_id: str, request: Request):
    """Soft-delete (deactivate) SOP."""
    await _require_admin(request)
    db = get_db()
    sop = await db.rahaza_model_process_sop.find_one({"id": sop_id}, {"_id": 0})
    if not sop:
        raise HTTPException(404, "SOP tidak ditemukan")
    await db.rahaza_model_process_sop.update_one(
        {"id": sop_id},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"message": "SOP dinonaktifkan"}
