"""document_number_configs.py — Configurable document numbering (Phase D).

Admin-configurable FORMAT for auto-generated document numbers (starting with the
CMT→DA and DA→Buyer surat jalan). Backed by `utils.doc_numbering` + the atomic
`counters` SSOT. Format tokens documented in utils/doc_numbering.py.

Endpoints (prefix /api/document-number-configs):
  GET  /                  -> list all known doc types (default merged with saved) + live preview
  GET  /{doc_type}        -> single effective config + preview
  PUT  /{doc_type}        -> save/replace config (admin only)
  POST /{doc_type}/preview-> render an example number for a candidate format (no counter change)
"""
import logging
from fastapi import APIRouter, Request, HTTPException

from database import get_db
from auth import require_auth, check_role, log_activity
from core.helpers import now
from utils.doc_numbering import (
    DEFAULT_CONFIGS, SEQ_RESETS, get_number_config, preview_number,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/document-number-configs", tags=["document-number-configs"])

# Doc types exposed in the admin UI (extensible). Buyer shipments first.
KNOWN_DOC_TYPES = ['buyer_shipment_buyer', 'buyer_shipment_da']

_ADMIN_ROLES = ['admin', 'superadmin', 'owner']


async def _effective(db, doc_type: str, context=None):
    cfg = await get_number_config(db, doc_type)
    cfg['preview'] = preview_number(cfg, context=context or _sample_ctx(doc_type))
    return cfg


def _sample_ctx(doc_type: str) -> dict:
    return {'po_number': 'PO-MK-0001', 'buyer': 'PT Buyer Jaya'}


@router.get("")
async def list_configs(request: Request):
    await require_auth(request)
    db = get_db()
    out = []
    for dt in KNOWN_DOC_TYPES:
        out.append(await _effective(db, dt))
    return {"doc_types": out, "tokens": [
        "{PREFIX}", "{YYYY}", "{YY}", "{MM}", "{DD}", "{SEQ}", "{SEQ5}", "{PO}", "{BUYER}",
    ], "seq_resets": list(SEQ_RESETS)}


@router.get("/{doc_type}")
async def get_config(doc_type: str, request: Request):
    await require_auth(request)
    db = get_db()
    return await _effective(db, doc_type)


@router.put("/{doc_type}")
async def save_config(doc_type: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, _ADMIN_ROLES):
        raise HTTPException(403, 'Hanya admin yang dapat mengubah format nomor dokumen.')
    db = get_db()
    body = await request.json()

    fmt = str(body.get('format') or '').strip()
    if not fmt:
        raise HTTPException(400, 'format wajib diisi.')
    seq_reset = body.get('seq_reset', 'yearly')
    if seq_reset not in SEQ_RESETS:
        raise HTTPException(400, f"seq_reset harus salah satu dari {list(SEQ_RESETS)}.")
    try:
        seq_width = max(1, min(10, int(body.get('seq_width') or 4)))
    except (TypeError, ValueError):
        raise HTTPException(400, 'seq_width harus angka 1-10.')

    patch = {
        'label': (body.get('label') or DEFAULT_CONFIGS.get(doc_type, {}).get('label') or doc_type),
        'format': fmt,
        'prefix': (body.get('prefix') or ''),
        'seq_width': seq_width,
        'seq_reset': seq_reset,
        'enabled': bool(body.get('enabled', True)),
        'updated_at': now(),
        'updated_by': user.get('name', ''),
    }
    await db.document_number_configs.update_one(
        {'_id': doc_type}, {'$set': patch}, upsert=True)
    await log_activity(user['id'], user.get('name', ''), 'update', 'document_number_config',
                       f"Format nomor '{doc_type}' -> {fmt}")
    return await _effective(db, doc_type)


@router.post("/{doc_type}/preview")
async def preview_config(doc_type: str, request: Request):
    """Render an example number for a candidate format WITHOUT changing the counter."""
    await require_auth(request)
    body = await request.json()
    # Build an ad-hoc config from the candidate body (fallback to saved/default).
    db = get_db()
    cfg = await get_number_config(db, doc_type)
    for k in ('format', 'prefix', 'seq_width', 'seq_reset'):
        if body.get(k) is not None:
            cfg[k] = body[k]
    # normalize via a fresh pass (guarantees SEQ token, clamps width)
    from utils.doc_numbering import _base_config  # local import to avoid cycle noise
    if not str(cfg.get('format') or '').strip():
        cfg['format'] = _base_config(doc_type)['format']
    ctx = body.get('context') or _sample_ctx(doc_type)
    try:
        sample = preview_number(cfg, context=ctx, sample_seq=int(body.get('sample_seq', 7)))
    except Exception as e:
        raise HTTPException(400, f'Format tidak valid: {e}')
    return {'preview': sample, 'format': cfg.get('format')}
