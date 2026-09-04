"""
core/cmt_receipt_status.py — SSOT STATUS PENERIMAAN FG DARI CMT.

FASE 4 (UX, permintaan owner): penerimaan barang jadi dari CMT dulu memakai
3 langkah persetujuan (`Draft` → `Submitted` → `Approved`) + halaman dalam
terpisah, padahal pekerjaannya SATU: hitung fisik lalu selesai.

Sekarang hanya ada:
    on_qc         — sedang dihitung/di-QC (bisa diedit)
    completed_qc  — selesai QC (stok & tagihan sudah terbentuk, terkunci)
    cancelled     — dibatalkan (salah input)

Status LAMA tetap bisa dibaca (data historis) lewat `canon_status()` supaya tidak
ada dokumen yang hilang dari layar. Modul ini dipakai bersama oleh
`routes/dewi_cmt_packing.py` (penulis) dan konsumen lain (`dewi_cmt_permak.py`,
`buyer_shipment.py`) supaya tidak ada dua definisi status yang menyimpang —
pelajaran audit 2026-07-31: gerbang status yang disalin selalu tertinggal.
"""
from __future__ import annotations

ST_QC = "on_qc"
ST_DONE = "completed_qc"
ST_CANCELLED = "cancelled"

LEGACY_STATUS = {
    "draft": ST_QC,
    "submitted": ST_QC,
    "on_qc": ST_QC,
    "approved": ST_DONE,
    "completed_qc": ST_DONE,
    "rejected": ST_CANCELLED,
    "cancelled": ST_CANCELLED,
}

STATUS_LABEL = {
    ST_QC: "Sedang QC",
    ST_DONE: "Selesai QC",
    ST_CANCELLED: "Dibatalkan",
}


def canon_status(raw) -> str:
    """Normalisasi status penerimaan (baru & historis) ke status kanonik."""
    return LEGACY_STATUS.get(str(raw or "").strip().lower(), ST_QC)


def is_done(raw) -> bool:
    return canon_status(raw) == ST_DONE


def with_canon_status(doc: dict | None) -> dict | None:
    """Sisipkan status kanonik + label; status asli disimpan di `status_raw`."""
    if not doc:
        return doc
    raw = doc.get("status")
    canon = canon_status(raw)
    doc["status_raw"] = raw
    doc["status"] = canon
    doc["status_label"] = STATUS_LABEL.get(canon, canon)
    return doc


def canon_status_filter(requested: str) -> dict:
    """Filter Mongo yang menerima status kanonik MAUPUN legacy (semua kapitalisasi)."""
    canon = canon_status(requested)
    olds = [k for k, v in LEGACY_STATUS.items() if v == canon]
    variants = set()
    for o in olds:
        variants.update({o, o.capitalize(), o.upper()})
    return {"$in": sorted(variants)}
