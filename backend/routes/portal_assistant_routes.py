"""Asisten ERP CV. Dewi Aditya — endpoint sadar-portal.

Prinsip: jawab dari basis pengetahuan statis lebih dulu (gratis & instan).
AI (Claude) hanya dipanggil bila basis pengetahuan tidak yakin DAN kunci
`ANTHROPIC_API_KEY` tersedia. Tanpa kunci, asisten tetap berguna penuh.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth
from database import get_db
from services import portal_assistant as kb

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["assistant"])

ASSISTANT_NAME = "Asisten ERP CV. Dewi Aditya"
COLL = "assistant_chat_history"

SYSTEM_PROMPT = (
    "Kamu adalah Asisten ERP CV. Dewi Aditya, sebuah perusahaan garmen di Indonesia. "
    "Tugasmu menjelaskan CARA KERJA SISTEM ERP ini kepada karyawan: alur pekerjaan, "
    "arti istilah, dan letak fitur. Jawab dalam Bahasa Indonesia yang sederhana, "
    "singkat (maksimal 6 kalimat atau 6 langkah bernomor), dan langsung ke inti. "
    "HANYA gunakan informasi dari KONTEKS SISTEM di bawah. Bila konteks tidak memuat "
    "jawabannya, katakan terus terang bahwa kamu belum punya informasinya dan sarankan "
    "menghubungi admin sistem. JANGAN mengarang nama modul, angka, atau menu."
)


def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/context")
async def context(request: Request, portal: Optional[str] = None):
    """Identitas asisten + ringkasan portal aktif + saran pertanyaan."""
    await require_auth(request)
    doc = kb.load_kb(portal) if portal else None
    fallback = kb.load_kb(kb.GENERAL) or {}
    src = doc or fallback
    return {
        "assistant_name": ASSISTANT_NAME,
        "portal": portal if doc else None,
        "portal_label": src.get("label", "Umum"),
        "ringkasan": src.get("ringkasan", ""),
        "saran": src.get("saran", []),
        "total_fitur": len(src.get("fitur", [])),
        "kb_available": bool(doc),
    }


@router.post("/ask")
async def ask(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    question = (body.get("question") or body.get("message") or "").strip()
    portal = (body.get("portal") or "").strip() or None
    module = (body.get("module") or "").strip() or None
    session_id = body.get("session_id") or f"asst-{user['id'][:8]}-{date.today().isoformat()}"
    if not question:
        raise HTTPException(400, "Pertanyaan wajib diisi.")

    res = kb.answer(question, portal)
    source = res["source"]

    if source == "none":
        ai_reply, ai_err = await _try_ai(db, question, portal, module, session_id, user)
        if ai_reply:
            res = {"source": "ai", "kind": "ai", "portal": portal, "reply": ai_reply,
                   "confidence": "sedang", "related": res.get("related", [])}
            source = "ai"
        else:
            label = (kb.load_kb(portal) or kb.load_kb(kb.GENERAL) or {}).get("label", "portal ini")
            res["reply"] = (
                f"Maaf, saya belum punya penjelasan untuk pertanyaan itu di {label}."
                + (f"\n\n({ai_err})" if ai_err else "")
                + "\n\nCoba pertanyaan lain, atau hubungi admin sistem."
            )

    now = _now_iso()
    await db[COLL].insert_many([
        {"id": _uid(), "session_id": session_id, "user_id": user["id"], "role": "user",
         "content": question, "portal": portal, "module": module, "created_at": now},
        {"id": _uid(), "session_id": session_id, "user_id": user["id"], "role": "assistant",
         "content": res["reply"], "portal": portal, "module": module,
         "source": source, "created_at": now},
    ])

    return {"ok": True, "session_id": session_id, "reply": res["reply"],
            "source": source, "confidence": res.get("confidence"),
            "related": res.get("related", []), "created_at": now}


async def _try_ai(db, question, portal, module, session_id, user):
    """Panggil Claude hanya bila basis pengetahuan gagal. Return (reply, error_note)."""
    from services.ai import call_claude, LLMUnavailable
    ctx = kb.ai_context(portal)
    where = f"Pengguna sedang membuka portal '{portal or 'tidak diketahui'}'" + (
        f", modul '{module}'." if module else ".")
    try:
        reply = await call_claude(
            system_message=f"{SYSTEM_PROMPT}\n\nKONTEKS SISTEM:\n{ctx}",
            user_message=f"{where}\n\nPertanyaan: {question}",
            session_tag="assistant-erp",
            db=db,
            tier="light",
        )
        return (reply or "").strip(), None
    except LLMUnavailable:
        return None, "Bantuan AI belum aktif — kunci Claude belum dipasang admin."
    except HTTPException as e:
        log.warning("assistant AI gagal: %s", e.detail)
        return None, "Bantuan AI sedang tidak tersedia."
    except Exception as e:  # pragma: no cover
        log.exception("assistant AI error")
        return None, "Bantuan AI sedang tidak tersedia."


@router.get("/history")
async def history(request: Request, session_id: Optional[str] = None,
                  limit: int = Query(100, ge=1, le=500)):
    user = await require_auth(request)
    db = get_db()
    if not session_id:
        session_id = f"asst-{user['id'][:8]}-{date.today().isoformat()}"
    rows = await db[COLL].find(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0},
    ).sort("created_at", 1).to_list(limit)
    return {"session_id": session_id, "messages": rows}


@router.delete("/history")
async def clear_history(request: Request, session_id: str):
    user = await require_auth(request)
    db = get_db()
    r = await db[COLL].delete_many({"session_id": session_id, "user_id": user["id"]})
    return {"ok": True, "deleted": r.deleted_count}
