"""dewi_rnd — shared router instance + helper utilities.
Di-import oleh semua sub-modul dewi_rnd_*.py.
"""
from fastapi import APIRouter
from datetime import datetime, timezone
import re
import uuid

router = APIRouter(prefix="/api/dewi/rnd", tags=["RnD"])


def now_utc():
    return datetime.now(timezone.utc)


def sid():
    return str(uuid.uuid4())


def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ── Resolusi baris material RnD → master (2026-08-02) ────────────────────────
# Baris BOM/costing RnD memakai nama kunci berbeda tergantung layarnya: Tech Pack
# menulis `material` (nama), Sample Costing menulis `name`, importer menulis
# `material_code`. Tanpa tautan ke master `rahaza_materials`, satuan baris TIDAK
# bisa dikonversi (core.bom_uom butuh `uoms` / gramasi / lebar dari master).

def line_code(line: dict) -> str:
    ln = line or {}
    return str(ln.get('material_code') or ln.get('code') or '').strip().upper()


def line_name(line: dict) -> str:
    ln = line or {}
    return str(ln.get('material_name') or ln.get('name') or ln.get('material') or '').strip()


def _exact_ci(value: str) -> dict:
    return {'$regex': f'^{re.escape(value)}$', '$options': 'i'}


async def resolve_master_material(db, line: dict):
    """Master `rahaza_materials` untuk sebuah baris: id → kode → nama (case-insensitive)."""
    ln = line or {}
    mid = ln.get('material_id') or ln.get('linked_material_id')
    if mid:
        doc = await db.rahaza_materials.find_one({'id': mid}, {'_id': 0})
        if doc:
            return doc
    code = line_code(ln)
    if code:
        doc = await db.rahaza_materials.find_one({'code': code}, {'_id': 0})
        if doc:
            return doc
    name = line_name(ln)
    if name:
        doc = await db.rahaza_materials.find_one(
            {'name': _exact_ci(name), 'type': {'$ne': 'fg'}}, {'_id': 0})
        if doc:
            return doc
    return None


async def resolve_rnd_material(db, line: dict):
    """Dokumen Riset Material (`dewi_rnd_materials`): kode → nama (case-insensitive)."""
    ln = line or {}
    code = line_code(ln)
    if code:
        doc = await db.dewi_rnd_materials.find_one({'material_code': code}, {'_id': 0})
        if doc:
            return doc
    name = line_name(ln)
    if name:
        doc = await db.dewi_rnd_materials.find_one({'material_name': _exact_ci(name)}, {'_id': 0})
        if doc:
            return doc
    return None
