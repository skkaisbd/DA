"""core/cmt_delivery_note.py — SSOT Surat Jalan CMT → DA (W5, permintaan pemilik 2026-08-20).

KENAPA BERKAS INI ADA
---------------------
Pemilik minta surat jalan untuk barang jadi yang dikirim vendor CMT ke DA, dengan
tombol cetaknya di layar **Produksi → Terima FG dari CMT**. Sumber angkanya adalah
BARIS PENERIMAAN yang dipilih (`cmt_receipts` + `cmt_receipt_lines`) — qty & identitas
barangnya sudah pasti di dokumen itu.

Dua hal yang TIDAK boleh dikerjakan di dalam generator PDF, karena keduanya adalah
keputusan data (dan generator PDF bukan tempat menyimpan kebenaran):

1. **Nomor surat jalan.** Nomornya lahir sekali per penerimaan lalu DIPAKAI ULANG
   pada cetakan berikutnya — kalau tidak, satu penerimaan bisa punya banyak nomor
   surat jalan dan arsip fisik tidak bisa dicocokkan. Nomornya lewat satu-satunya
   generator race-safe `utils.counters.gen_prefixed_number` sehingga formatnya bisa
   diatur pemilik di Administrasi Sistem → Penomoran Dokumen.

2. **Nomor seri barang.** `cmt_receipt_lines` TIDAK menyimpan `serial_number`; serial
   hidup di `po_items` (nomor invoice/seri PO) dan `buyer_shipment_items`. Resolusinya
   ditulis satu kali di sini supaya layar lain yang butuh surat jalan yang sama tidak
   menyusun serial dengan aturan sendiri.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from utils.counters import gen_prefixed_number

COLLECTION = "cmt_delivery_notes"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_number(db, receipt: dict, actor: dict | None = None) -> dict:
    """Dokumen surat jalan untuk satu penerimaan CMT — IDEMPOTEN per penerimaan.

    Cetak pertama membuat nomornya; cetak berikutnya memakai nomor yang SAMA dan
    hanya menambah jejak cetak (siapa & kapan).
    """
    rid = receipt.get("id")
    who = (actor or {}).get("name") or (actor or {}).get("email") or ""
    existing = await db[COLLECTION].find_one({"receipt_id": rid}, {"_id": 0})
    if existing:
        await db[COLLECTION].update_one(
            {"id": existing["id"]},
            {"$set": {"last_printed_at": _now(), "last_printed_by": who},
             "$inc": {"print_count": 1}})
        existing["print_count"] = int(existing.get("print_count") or 0) + 1
        existing["last_printed_at"] = _now()
        existing["last_printed_by"] = who
        return existing

    now = datetime.now(timezone.utc)
    number = await gen_prefixed_number(
        db, COLLECTION, "dn_number", f"SJ-CMT/{now:%Y}/{now:%m}/", 4)
    doc = {
        "id": str(uuid.uuid4()),
        "dn_number": number,
        "receipt_id": rid,
        "receipt_code": receipt.get("receipt_code", ""),
        "po_id": receipt.get("po_id", ""),
        "po_number": receipt.get("po_number", ""),
        "cmt_vendor_id": receipt.get("cmt_vendor_id", ""),
        "cmt_name": receipt.get("cmt_name", ""),
        "business_type": receipt.get("business_type", ""),
        "vendor_delivery_note": receipt.get("delivery_note", ""),
        "receipt_date": receipt.get("receipt_date", ""),
        "print_count": 1,
        "first_printed_at": _now(),
        "last_printed_at": _now(),
        "last_printed_by": who,
        "created_at": _now(),
        "created_by": who,
    }
    await db[COLLECTION].insert_one(dict(doc))
    return doc


async def build_lines(db, receipt_id: str) -> list[dict]:
    """Baris surat jalan: qty kirim (klaim CMT) · qty lolos QC · reject + serial."""
    lines = await db.cmt_receipt_lines.find(
        {"receipt_id": receipt_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    if not lines:
        return []

    po_item_ids = [ln.get("po_item_id") for ln in lines if ln.get("po_item_id")]
    bsi_ids = [ln.get("source_buyer_shipment_item_id") for ln in lines
               if ln.get("source_buyer_shipment_item_id")]
    po_map, bsi_map = {}, {}
    if po_item_ids:
        for d in await db.po_items.find(
                {"id": {"$in": po_item_ids}},
                {"_id": 0, "id": 1, "serial_number": 1, "sku": 1,
                 "product_name": 1, "size": 1, "color": 1}).to_list(1000):
            po_map[d["id"]] = d
    if bsi_ids:
        for d in await db.buyer_shipment_items.find(
                {"id": {"$in": bsi_ids}},
                {"_id": 0, "id": 1, "serial_number": 1, "sku": 1,
                 "product_name": 1, "size": 1, "color": 1}).to_list(1000):
            bsi_map[d["id"]] = d

    out = []
    for ln in lines:
        src = po_map.get(ln.get("po_item_id")) or {}
        alt = bsi_map.get(ln.get("source_buyer_shipment_item_id")) or {}

        def pick(field, line_field=None):
            return (str(ln.get(line_field or field) or "").strip()
                    or str(src.get(field) or "").strip()
                    or str(alt.get(field) or "").strip())

        qty_sent = ln.get("qty_claimed_by_cmt")
        if qty_sent in (None, ""):
            qty_sent = ln.get("qty_shipped_by_cmt") or 0
        out.append({
            "serial": pick("serial_number"),
            "sku": pick("sku", "sku_code"),
            "product": pick("product_name"),
            "size": pick("size"),
            "color": pick("color"),
            "qty_sent": float(qty_sent or 0),
            "qty_received": float(ln.get("qty_actual") or 0),
            "qty_reject": float(ln.get("reject_qty") or 0),
            "notes": (str(ln.get("notes") or "").strip()
                      or str(ln.get("reject_reason") or "").strip()),
        })
    return out
