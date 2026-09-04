"""
pdf_common.py — Fondasi bersama untuk semua PDF surat/dokumen (branding + tanda tangan).

SESI #19 — berkas ini kini JEMBATAN TIPIS, bukan sumber kebenaran:
  · katalog jenis dokumen & kolom  → `data/pdf_doc_registry.py`
  · template (kop/kolom/tanda tangan/footer) → `core/pdf_template.py` (koleksi `pdf_templates`)
Sebelumnya katalog surat ada di sini dan katalog kolom ada di
`routes/operations_pdf_configs.py`; dua daftar untuk satu dokumen membuat pemilik
harus mengatur satu surat di DUA layar dengan UI berbeda (keluhan pemilik sesi #18).

Nama-nama lama (`SUPPORTED_PDF_DOCS`, `DEFAULT_DOC_SETTINGS`, `get_company_profile`,
`get_doc_settings`, `resolve_signature_name`, `doc_types_catalog`) DIPERTAHANKAN
karena dipakai belasan generator PDF — yang berubah hanya dari mana isinya datang.
"""
from datetime import datetime, timezone

from core import pdf_template as _tpl
from data.pdf_doc_registry import (DEFAULT_DOC_SETTINGS, PDF_COLUMN_DEFINITIONS,
                                   SUPPORTED_PDF_DOCS, doc_types_catalog)

__all__ = [
    "SUPPORTED_PDF_DOCS", "DEFAULT_DOC_SETTINGS", "PDF_COLUMN_DEFINITIONS",
    "doc_types_catalog", "get_company_profile", "get_doc_settings",
    "resolve_signature_name", "_now",
]


def _now():
    return datetime.now(timezone.utc)


async def get_company_profile(db) -> dict:
    """Profil perusahaan ternormalisasi (satu pembaca: core.pdf_template)."""
    return await _tpl.company_profile(db)


async def get_doc_settings(db, doc_type: str) -> dict:
    """Pengaturan PDF efektif utk satu jenis dokumen — DARI TEMPLATE (sesi #19).

    Bentuk kembaliannya tetap sama seperti sebelumnya (`show_logo`, `header_line1`,
    `signatures[...]`) DITAMBAH `_template` (template lengkap). Generator lama
    otomatis ikut menghormati template pemilik; generator yang sudah dipindah
    memakai `_template` untuk fitur baru (logo, urutan kolom, blok TTD > 3).
    """
    if doc_type not in SUPPORTED_PDF_DOCS:
        # Jenis yang belum terdaftar tetap dapat bawaan aman (dulu juga begitu),
        # supaya dokumen baru tidak pernah gagal cetak hanya karena belum didaftarkan.
        out = dict(DEFAULT_DOC_SETTINGS)
        out.update({"doc_type": doc_type, "label": doc_type, "signatures": []})
        return out
    return await _tpl.legacy_doc_settings(db, doc_type)


def resolve_signature_name(sig: dict, context: dict) -> str:
    """Nama penandatangan dari konfigurasi + konteks dokumen.

    name_source: 'custom' → custom_name; 'field' → context[field_key]; lainnya → ''.
    """
    return _tpl.resolve_name(sig, context)
