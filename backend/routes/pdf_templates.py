"""routes/pdf_templates.py — API layar SATU PINTU "PDF & Kop Surat" (SESI #19).

Menggantikan DUA layar lama yang UI/UX-nya berbeda:
  · `/api/pdf-export-columns` + `/api/pdf-export-configs`  (kolom tabel)
  · `/api/pdf-doc-settings/*`                              (kop, logo, tanda tangan)
Keduanya tetap hidup sebagai warisan/arsip, tetapi SUMBER KEBENARAN yang dipakai
generator PDF sekarang adalah koleksi `pdf_templates` (lihat `core/pdf_template.py`).

Endpoint (prefix /api/pdf-templates):
  GET    /catalog          katalog jenis dokumen + kolom + field tanda tangan
  GET    /global           template GLOBAL (kop/tanda tangan/footer bawaan semua dokumen)
  PUT    /global           simpan template global
  POST   /preview          PDF PRATINJAU dari template yang sedang diedit (data contoh)
  GET    /{doc_key}        template satu jenis dokumen (+ bendera override)
  PUT    /{doc_key}        simpan template satu jenis dokumen
  DELETE /{doc_key}        hapus override → kembali mengikuti global + bawaan

Urutan rute SENGAJA spesifik-dulu (`/catalog`, `/global`, `/preview`) sebelum
`/{doc_key}`: FastAPI mencocokkan berurutan, dan rute parameter yang didahulukan
akan menelan permintaan `/catalog` sebagai doc_key bernama "catalog".
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from auth import require_auth
from core import pdf_template as tpl
from data.pdf_doc_registry import SUPPORTED_PDF_DOCS, catalog
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pdf-templates", tags=["pdf-templates"])


async def _require_manage(request: Request) -> dict:
    """Izin kelola template PDF.

    Memakai gerbang izin terpusat supaya owner bisa memberi izin ini ke peran
    non-admin dari layar "Peran & Hak Akses" (pola yang sama dengan Penomoran
    Dokumen), bukan mengunci mati ke role 'admin'.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "pdf.manage", "settings.manage",
        legacy_roles=("superadmin", "owner", "admin"),
        message="Akses ditolak: butuh izin kelola template PDF (pdf.manage).",
    )


def _label(user: dict) -> str:
    return str((user or {}).get("email") or (user or {}).get("name") or (user or {}).get("id") or "")


@router.get("/catalog")
async def get_catalog(request: Request):
    """Katalog jenis dokumen untuk editor (label, grup, kolom, field TTD)."""
    await require_auth(request)
    return {"docs": catalog(),
            "header_layouts": list(tpl.HEADER_LAYOUTS),
            "name_sources": list(tpl.NAME_SOURCES),
            "max_signature_blocks": tpl.MAX_SIGNATURE_BLOCKS,
            "max_extra_columns": tpl.MAX_EXTRA_COLUMNS,
            "max_logo_kb": tpl.MAX_LOGO_BYTES // 1024}


@router.get("/global")
async def get_global_template(request: Request):
    await require_auth(request)
    db = get_db()
    out = await tpl.get_global(db)
    out["company_profile"] = await tpl.company_profile(db)
    return out


@router.put("/global")
async def put_global_template(request: Request):
    user = await _require_manage(request)
    db = get_db()
    body = await request.json()
    try:
        return await tpl.save(db, "", body, _label(user))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/preview")
async def preview(request: Request):
    """PDF pratinjau — data CONTOH, template belum perlu disimpan.

    Dipakai penampil di SAMPING editor (permintaan pemilik: "ada preview/viewer di
    samping editor supaya user langsung mengecek hasilnya tanpa mengunduh").

    `?format=png` mengembalikan GAMBAR halaman pertama. Alasannya bukan hiasan:
    penampil PDF bawaan browser tidak selalu ada (mode kios, browser tertanam,
    beberapa Android WebView) dan iframe-nya tampil KOSONG tanpa pesan apa pun —
    pemilik akan menyimpulkan pratinjaunya rusak. Gambar dirender dari PDF yang
    SAMA (pymupdf), jadi tetap WYSIWYG, bukan tiruan HTML.
    """
    await require_auth(request)
    db = get_db()
    body = await request.json()
    doc_key = str(body.get("doc_key") or "").strip()
    if doc_key not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_key}' tidak dikenal.")
    template = body.get("template") or None
    if template:
        # Validasi RINGAN untuk pratinjau: logo rusak/kelebihan ukuran ditolak dengan
        # pesan yang sama seperti saat menyimpan, bukan menghasilkan PDF tanpa logo
        # secara diam-diam (pemilik akan mengira logonya tidak didukung).
        try:
            hdr = template.get("header") or {}
            if hdr.get("logo_data"):
                tpl.validate_logo(hdr["logo_data"])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    try:
        buf = await tpl.build_preview(db, doc_key, template)
    except Exception as e:  # noqa: BLE001
        logger.exception("[pdf-template] pratinjau gagal untuk %s", doc_key)
        raise HTTPException(500, f"Pratinjau gagal dibuat: {e}") from e

    if (request.query_params.get("format") or "").lower() == "png":
        try:
            import io as _io

            import pymupdf
            doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
            pix = doc[0].get_pixmap(dpi=110)
            png = _io.BytesIO(pix.tobytes("png"))
            png.seek(0)
            return StreamingResponse(
                png, media_type="image/png",
                headers={"Cache-Control": "no-store",
                         "X-Pdf-Pages": str(doc.page_count)})
        except Exception as e:  # noqa: BLE001
            # Gagal merender gambar TIDAK boleh menghilangkan pratinjau: kembalikan
            # PDF-nya (penampil browser masih mungkin bekerja) dan catat sebabnya.
            logger.warning("[pdf-template] render PNG gagal, kembali ke PDF: %s", e)
            buf.seek(0)

    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="pratinjau-{doc_key}.pdf"',
                 "Cache-Control": "no-store"})


@router.get("/{doc_key}")
async def get_doc_template(doc_key: str, request: Request):
    await require_auth(request)
    if doc_key not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_key}' tidak dikenal.")
    db = get_db()
    out = await tpl.get_doc(db, doc_key)
    out["effective"] = await tpl.resolve(db, doc_key)
    return out


@router.put("/{doc_key}")
async def put_doc_template(doc_key: str, request: Request):
    user = await _require_manage(request)
    if doc_key not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_key}' tidak dikenal.")
    db = get_db()
    body = await request.json()
    try:
        return await tpl.save(db, doc_key, body, _label(user))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{doc_key}")
async def reset_doc_template(doc_key: str, request: Request):
    await _require_manage(request)
    if doc_key not in SUPPORTED_PDF_DOCS:
        raise HTTPException(404, f"Jenis dokumen '{doc_key}' tidak dikenal.")
    db = get_db()
    return await tpl.reset(db, doc_key)
