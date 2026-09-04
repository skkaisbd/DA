# ruff: noqa: F401
"""
operations_pdf_configs.py — PDF Export Configuration Management (WARISAN)
Endpoints: /api/pdf-export-columns, /api/pdf-export-configs (CRUD)

Refactored: Session #11.19 Phase 3.2.6 (split from operations_export.py 1277 LOC)

SESI #19 — layar barunya adalah "PDF & Kop Surat" (`/api/pdf-templates`) dan
sumber kebenaran kolom pindah ke `data/pdf_doc_registry.py`. Endpoint di berkas ini
DIPERTAHANKAN karena masih dipakai skrip/uji lama dan sebagai arsip konfigurasi
kolom bernama; definisi kolomnya kini DIIMPOR dari registry supaya tidak ada dua
daftar kolom yang bisa berbeda pendapat tentang dokumen yang sama.
"""
import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from datetime import datetime, timezone

from data.pdf_doc_registry import PDF_COLUMN_DEFINITIONS  # noqa: F401  (SSOT kolom)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operations-pdf-configs"])



@router.get("/pdf-export-columns")
async def get_pdf_export_columns(request: Request):
    """Get available columns for a PDF type."""
    await require_auth(request)
    pdf_type = request.query_params.get('type', '')
    if pdf_type in PDF_COLUMN_DEFINITIONS:
        return {'pdf_type': pdf_type, 'columns': PDF_COLUMN_DEFINITIONS[pdf_type]}
    return {'pdf_type': pdf_type, 'columns': [], 'available_types': list(PDF_COLUMN_DEFINITIONS.keys())}


@router.get("/pdf-export-configs")
async def list_pdf_export_configs(request: Request):
    """List all PDF export configurations."""
    await require_auth(request)
    db = get_db()
    pdf_type = request.query_params.get('type')
    query = {}
    if pdf_type:
        query['pdf_type'] = pdf_type
    configs = await db.pdf_export_configs.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    return serialize_doc(configs)


@router.get("/pdf-export-configs/{config_id}")
async def get_pdf_export_config(config_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await db.pdf_export_configs.find_one({'id': config_id}, {'_id': 0})
    if not cfg:
        raise HTTPException(404, 'Config not found')
    return serialize_doc(cfg)


@router.post("/pdf-export-configs")
async def create_pdf_export_config(request: Request):
    """Create a new PDF export config."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    pdf_type = body.get('pdf_type', '')
    name = body.get('name', '')
    columns = body.get('columns', [])
    is_default = body.get('is_default', False)
    if not pdf_type or not name:
        raise HTTPException(400, 'pdf_type and name required')
    if not columns:
        raise HTTPException(400, 'columns array required')
    # Ensure required columns are included
    if pdf_type in PDF_COLUMN_DEFINITIONS:
        required = [c['key'] for c in PDF_COLUMN_DEFINITIONS[pdf_type] if c.get('required')]
        provided = set(columns)
        if not all(r in provided for r in required):
            raise HTTPException(400, f'Required columns missing: {required}')
    # If setting as default, unset previous defaults
    if is_default:
        await db.pdf_export_configs.update_many({'pdf_type': pdf_type, 'is_default': True},
                                                 {'$set': {'is_default': False}})
    new_cfg = {'id': str(uuid.uuid4()), 'pdf_type': pdf_type, 'name': name, 'columns': columns,
               'is_default': is_default, 'created_by': user.get('name', ''),
               'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)}
    await db.pdf_export_configs.insert_one(new_cfg)
    await log_activity(user['id'], user.get('name', ''), 'create', 'pdf_export_config', f"Created config {name}")
    return serialize_doc({k: v for k, v in new_cfg.items() if k != '_id'})


@router.put("/pdf-export-configs/{config_id}")
async def update_pdf_export_config(config_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    existing = await db.pdf_export_configs.find_one({'id': config_id})
    if not existing:
        raise HTTPException(404, 'Config not found')
    update = {'updated_at': datetime.now(timezone.utc)}
    if 'name' in body:
        update['name'] = body['name']
    if 'columns' in body:
        columns = body['columns']
        # Validate required columns
        pdf_type = existing.get('pdf_type', '')
        if pdf_type in PDF_COLUMN_DEFINITIONS:
            required = [c['key'] for c in PDF_COLUMN_DEFINITIONS[pdf_type] if c.get('required')]
            provided = set(columns)
            if not all(r in provided for r in required):
                raise HTTPException(400, f'Required columns missing: {required}')
        update['columns'] = columns
    if 'is_default' in body:
        if body['is_default']:
            await db.pdf_export_configs.update_many({'pdf_type': existing['pdf_type'], 'is_default': True},
                                                     {'$set': {'is_default': False}})
        update['is_default'] = body['is_default']
    await db.pdf_export_configs.update_one({'id': config_id}, {'$set': update})
    await log_activity(user['id'], user.get('name', ''), 'update', 'pdf_export_config',
                       f"Updated config {existing.get('name', config_id)}")
    return serialize_doc(await db.pdf_export_configs.find_one({'id': config_id}, {'_id': 0}))


@router.delete("/pdf-export-configs/{config_id}")
async def delete_pdf_export_config(config_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    existing = await db.pdf_export_configs.find_one({'id': config_id})
    if not existing:
        raise HTTPException(404, 'Config not found')
    await db.pdf_export_configs.delete_one({'id': config_id})
    await log_activity(user['id'], user.get('name', ''), 'delete', 'pdf_export_config',
                       f"Deleted config {existing.get('name', config_id)}")
    return {'success': True}
