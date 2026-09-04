"""
pdf_document_settings.py — Pengaturan PDF per jenis surat/dokumen (KEP item#3 / P1d).

Melengkapi framework `operations_pdf_configs` (pemilihan kolom tabel) dengan:
  - Cakupan SEMUA jenis surat (payslip, surat jalan, invoice maklon, dll — lih. SUPPORTED_PDF_DOCS).
  - Konfigurasi branding per dokumen (tampilkan logo, header/footer override).
  - Konfigurasi BLOK TANDA TANGAN: label + sumber nama (custom / dari field data mis. nama karyawan).

Endpoints (prefix /api/pdf-doc-settings):
  GET  /doc-types                 → katalog jenis dokumen + field tanda tangan yang tersedia
  GET  /{doc_type}                → pengaturan (mengembalikan default bila belum di-set)
  PUT  /{doc_type}                → simpan/replace pengaturan
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity, check_role
from utils.pdf_common import (
    SUPPORTED_PDF_DOCS, DEFAULT_DOC_SETTINGS, get_doc_settings, doc_types_catalog, _now,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pdf-doc-settings", tags=["pdf-doc-settings"])

VALID_NAME_SOURCES = {"custom", "field", "blank", "user"}


@router.get("/doc-types")
async def list_doc_types(request: Request):
    """Katalog semua jenis surat + field tanda tangan yang bisa dipakai."""
    await require_auth(request)
    return {"doc_types": doc_types_catalog()}


@router.get("/{doc_type}")
async def get_settings(doc_type: str, request: Request):
    await require_auth(request)
    if doc_type not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_type}' tidak dikenal.")
    db = get_db()
    return await get_doc_settings(db, doc_type)


@router.put("/{doc_type}")
async def save_settings(doc_type: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Hanya admin yang dapat mengubah pengaturan PDF.')
    if doc_type not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_type}' tidak dikenal.")
    db = get_db()
    body = await request.json()

    # validasi signatures
    sigs = body.get("signatures")
    clean_sigs = None
    if sigs is not None:
        if not isinstance(sigs, list):
            raise HTTPException(400, "signatures harus berupa array.")
        allowed_fields = {f["key"] for f in SUPPORTED_PDF_DOCS[doc_type].get("available_fields", [])}
        clean_sigs = []
        for s in sigs:
            src = s.get("name_source", "blank")
            if src not in VALID_NAME_SOURCES:
                raise HTTPException(400, f"name_source '{src}' tidak valid.")
            if src == "field" and s.get("field_key") and s["field_key"] not in allowed_fields:
                raise HTTPException(400, f"field_key '{s.get('field_key')}' tidak tersedia utk {doc_type}.")
            clean_sigs.append({
                "key": s.get("key", ""),
                "label": (s.get("label") or "").strip()[:60],
                "name_source": src,
                "custom_name": (s.get("custom_name") or "").strip()[:80],
                "field_key": s.get("field_key", ""),
                "role_label": (s.get("role_label") or "").strip()[:60],
            })

    patch = {"doc_type": doc_type, "updated_at": _now(), "updated_by": user.get("name", "")}
    for k in ("show_logo", "show_signatures", "header_line1", "header_line2", "footer_text"):
        if k in body:
            patch[k] = body[k]
    if clean_sigs is not None:
        patch["signatures"] = clean_sigs

    await db.pdf_document_settings.update_one(
        {"doc_type": doc_type}, {"$set": patch}, upsert=True
    )
    await log_activity(user['id'], user.get('name', ''), 'update', 'pdf_doc_settings',
                       f"Updated PDF settings for {doc_type}")
    return await get_doc_settings(db, doc_type)
