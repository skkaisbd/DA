"""
WMS — Surat Jalan / Delivery Note (P0-WH-2)
CV. Dewi Aditya — Dokumen pengiriman legal

Tipe:
  SJ-CMT      : kirim kain + aksesoris ke CMT (link ke WO)
  SJ-MAKLON   : kirim barang jadi ke klien maklon
  SJ-SUPPLIER : retur kain/material ke supplier
  SJ-INTERNAL : transfer antar gedung/lokasi internal
  SJ-ONLINE   : pengiriman online shop (batch resi)

Collection: wh_delivery_notes
  id, sj_number (SJ/2026/05/0001), sj_type, status (draft|issued|received|cancelled),
  recipient_name, recipient_address, recipient_phone,
  shipper_name, vehicle_no, notes,
  issued_at, received_at, cancelled_at,
  lines: [{line_no, description, qty, unit, remarks}]
  created_at, created_by, updated_at, updated_by

Endpoints (prefix /api/wms/delivery-notes):
  GET    /                    list + filter
  POST   /                    create draft SJ
  GET    /sources             FASE H-7: SATU daftar surat jalan LINTAS SUMBER (read-only)
  GET    /sources/recap-pdf   FASE H-7: cetak rekap daftar lintas sumber (landscape)
  GET    /{sj_id}             detail
  PUT    /{sj_id}             update draft
  DELETE /{sj_id}             delete draft
  POST   /{sj_id}/issue       issue (dari draft → issued, generate PDF)
  POST   /{sj_id}/receive     mark as received (buyer scan/acknowledge)
  POST   /{sj_id}/cancel      cancel
  GET    /{sj_id}/pdf         download PDF

FASE H-7 (2026-08-16) — MENGAPA ADA LAPISAN AGREGASI
----------------------------------------------------
Terukur sebelum perbaikan: layar "Surat Jalan" di Portal Gudang HANYA membaca
`wh_delivery_notes` (2 dokumen, keduanya DEMO), sementara surat jalan yang benar-benar
dipakai operasional hidup di DUA koleksi lain — `vendor_shipments` (kirim material ke CMT)
dan `buyer_shipments` + `buyer_shipment_items` (dispatch bertahap ke buyer) — masing-masing
dengan PDF-nya sendiri di `operations_pdf.py`. Akibatnya orang gudang yang ditanya "surat
jalan apa saja yang keluar minggu ini?" harus membuka TIGA layar di DUA portal berbeda, dan
layar yang namanya paling mirip pertanyaan itu justru yang isinya paling sedikit.

Keputusan pemilik (2026-08-16): **satukan jadi satu daftar cetak**. `wh_delivery_notes`
TIDAK dipensiunkan (dia satu-satunya tempat surat jalan internal/manual bisa dibuat), tetapi
layar Surat Jalan sekarang punya satu daftar READ-ONLY lintas sumber: tiap baris menunjuk
dokumen aslinya dan mencetak PDF resminya (tidak ada generator PDF kedua — nomor & isi
dokumen tetap milik sumbernya masing-masing).
"""
# ruff: noqa: F401
import io
import logging
import uuid
from datetime import datetime, timezone

from auth import require_auth, serialize_doc, verify_token_str
from core.doc_number_policy import issue_number
from database import get_db
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from utils.counters import gen_prefixed_number
from utils.pdf_common import (
    get_company_profile,
    get_doc_settings,
    resolve_signature_name,
)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/delivery-notes", tags=["wms-delivery-notes"])

SJ_TYPES = ["SJ-CMT", "SJ-MAKLON", "SJ-SUPPLIER", "SJ-INTERNAL", "SJ-ONLINE"]
SJ_STATUSES = ["draft", "issued", "received", "cancelled"]
# SESI #19 — kunci kebijakan penomoran (registry `data/doc_number_registry.py`).
SJ_DOCNUM_KEY = "wh_delivery_notes.sj_number"


def _now(): return datetime.now(timezone.utc)
def _id(): return str(uuid.uuid4())


class SJLine(BaseModel):
    description: str = Field(..., min_length=1)
    qty: float = Field(..., gt=0)
    unit: str = "pcs"
    remarks: str = ""
    roll_no: str = ""  # optional link to fabric roll
    material_code: str = ""


class SJIn(BaseModel):
    sj_type: str
    # SESI #19 — kolom nomor hanya dipakai bila kebijakan penomoran Surat Jalan Gudang
    # disetel MANUAL. Pada mode OTOMATIS, mengirim nomor DITOLAK (bukan diabaikan
    # diam-diam) oleh `core.doc_number_policy.issue_number`.
    sj_number: str = ""
    recipient_name: str = Field(..., min_length=1)
    recipient_address: str = ""
    recipient_phone: str = ""
    shipper_name: str = ""
    vehicle_no: str = ""
    notes: str = ""
    reference_type: str = ""   # wo, maklon_order, po
    reference_id: str = ""
    reference_no: str = ""
    lines: list[SJLine] = []


class IssueIn(BaseModel):
    shipper_name: str = ""
    vehicle_no: str = ""
    notes: str = ""


class ReceiveIn(BaseModel):
    received_by: str = ""
    notes: str = ""


class CancelIn(BaseModel):
    reason: str = ""


async def _next_sj_number(db, sj_type: str) -> str:
    """Nomor SJ OTOMATIS — dipakai jalur yang tidak punya manusia di layarnya.

    Satu-satunya pemakai sekarang: `routes/wms_cmt_dispatches.py::execute_dispatch`
    (SJ-CMT lahir sendiri saat dispatch dieksekusi). Surat jalan yang DIBUAT ORANG
    lewat `create_sj` memakai `issue_number` supaya kebijakan Otomatis/Manual owner
    benar-benar berlaku — lihat catatan di `data/doc_number_registry.py`.
    """
    prefix = f"{sj_type}/{_now().strftime('%Y/%m')}/"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1 -> dup/E11000)
    return await gen_prefixed_number(db, "wh_delivery_notes", "sj_number", prefix, 4,
                                     ctx={"TIPE": sj_type}, config_key=SJ_DOCNUM_KEY)


@router.get("")
async def list_sj(
    request: Request,
    sj_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if sj_type:
        q["sj_type"] = sj_type
    if status:
        q["status"] = status
    if search:
        q["$or"] = [
            {"sj_number": {"$regex": search, "$options": "i"}},
            {"recipient_name": {"$regex": search, "$options": "i"}},
            {"reference_no": {"$regex": search, "$options": "i"}},
        ]
    total = await db.wh_delivery_notes.count_documents(q)
    skip = (page - 1) * limit
    items = await db.wh_delivery_notes.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": [serialize_doc(i) for i in items],
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
            "has_next": (skip + limit) < total,
            "has_prev": page > 1,
        }
    }


@router.post("")
async def create_sj(data: SJIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    if data.sj_type not in SJ_TYPES:
        raise HTTPException(400, f"sj_type harus salah satu dari {SJ_TYPES}")
    sj_id = _id()
    now = _now()
    # SESI #19 — SATU PINTU penomoran: menghormati mode Otomatis/Manual yang disetel
    # owner di Administrasi Sistem → Penomoran Dokumen (dulu selalu otomatis, sehingga
    # setelan MANUAL tersimpan tetapi tidak pernah berlaku).
    sj_number = await issue_number(db, SJ_DOCNUM_KEY, ctx={"TIPE": data.sj_type},
                                   requested=data.sj_number)
    lines = [{"line_no": i + 1, **line.dict()} for i, line in enumerate(data.lines)]
    doc = {
        "id": sj_id,
        "sj_number": sj_number,
        "sj_type": data.sj_type,
        "status": "draft",
        "recipient_name": data.recipient_name,
        "recipient_address": data.recipient_address,
        "recipient_phone": data.recipient_phone,
        "shipper_name": data.shipper_name,
        "vehicle_no": data.vehicle_no,
        "notes": data.notes,
        "reference_type": data.reference_type,
        "reference_id": data.reference_id,
        "reference_no": data.reference_no,
        "lines": lines,
        "issued_at": None, "received_at": None, "cancelled_at": None,
        "created_at": now,
        "created_by": user.get("name", user["id"]),
        "updated_at": now,
        "updated_by": user.get("name", user["id"]),
    }
    await db.wh_delivery_notes.insert_one(doc)
    out = await db.wh_delivery_notes.find_one({"id": sj_id}, {"_id": 0})
    return {"ok": True, "sj": serialize_doc(out)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE H-7 — SATU DAFTAR SURAT JALAN LINTAS SUMBER (READ-ONLY)
# ═══════════════════════════════════════════════════════════════════════════════
# Lapisan ini TIDAK menulis apa pun dan TIDAK membuat nomor baru. Ia menormalkan tiga
# koleksi yang masing-masing sudah punya dokumen resminya sendiri:
#   · `wh_delivery_notes`   → surat jalan internal/manual gudang (punya PDF sendiri)
#   · `vendor_shipments`    → kirim material ke CMT      (PDF: type=vendor-shipment)
#   · `buyer_shipment_items`→ dispatch bertahap ke buyer  (PDF: type=buyer-shipment-dispatch,
#                             satu baris = satu pengiriman fisik, bukan satu PO)
# Kenapa dispatch buyer dipecah per `dispatch_seq`: itulah dokumen yang benar-benar dibawa
# kurir. Menggabungnya per shipment akan menyembunyikan pengiriman ke-2 dan ke-3.

SOURCE_META = {
    "gudang": {"label": "Gudang (internal/manual)", "module": "wms-delivery-notes"},
    "vendor": {"label": "Kirim Material ke CMT", "module": "prod-shipments-vendor"},
    "buyer": {"label": "Dispatch ke Buyer", "module": "prod-shipments-buyer"},
}


def _iso(v) -> str:
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v or "")


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _hit(row: dict, q: str) -> bool:
    if not q:
        return True
    ql = q.lower()
    return any(ql in str(row.get(k) or "").lower()
               for k in ("number", "recipient", "reference", "doc_type", "source_label"))


def _in_range(row: dict, date_from: str, date_to: str) -> bool:
    """Baris masuk rentang tanggal? Dokumen TANPA tanggal hanya lolos bila rentangnya
    memang tidak diisi — jangan pernah menghitungnya sebagai "di dalam rentang"."""
    d = (row.get("date") or "")[:10]
    if not d:
        return not (date_from or date_to)
    return (not date_from or d >= date_from) and (not date_to or d <= date_to)


async def _rows_gudang(db) -> list[dict]:
    out = []
    async for sj in db.wh_delivery_notes.find({}, {"_id": 0}):
        lines = sj.get("lines") or []
        out.append({
            "source": "gudang", "source_label": SOURCE_META["gudang"]["label"],
            "module": SOURCE_META["gudang"]["module"],
            "key": f"gudang:{sj.get('id')}",
            "id": sj.get("id"),
            "number": sj.get("sj_number") or "",
            "doc_type": sj.get("sj_type") or "SJ",
            "date": _iso(sj.get("issued_at") or sj.get("created_at")),
            "recipient": sj.get("recipient_name") or "",
            "reference": sj.get("reference_no") or "",
            "status": sj.get("status") or "draft",
            "lines": len(lines),
            "qty": round(sum(_f(x.get("qty")) for x in lines), 3),
            "pdf_url": f"/api/wms/delivery-notes/{sj.get('id')}/pdf",
            "pdf_alt_url": "",
            "pdf_alt_label": "",
            "vehicle_no": sj.get("vehicle_no") or "",
        })
    return out


async def _rows_vendor(db) -> list[dict]:
    agg = {}
    async for it in db.vendor_shipment_items.find(
            {}, {"_id": 0, "shipment_id": 1, "qty_sent": 1}):
        a = agg.setdefault(it.get("shipment_id"), {"n": 0, "qty": 0.0})
        a["n"] += 1
        a["qty"] += _f(it.get("qty_sent"))
    out = []
    async for s in db.vendor_shipments.find({}, {"_id": 0}):
        a = agg.get(s.get("id"), {"n": 0, "qty": 0.0})
        out.append({
            "source": "vendor", "source_label": SOURCE_META["vendor"]["label"],
            "module": SOURCE_META["vendor"]["module"],
            "key": f"vendor:{s.get('id')}",
            "id": s.get("id"),
            "number": s.get("delivery_note_number") or s.get("shipment_number") or "",
            "doc_type": f"SJ-CMT · {s.get('shipment_type') or 'NORMAL'}",
            "date": _iso(s.get("shipment_date") or s.get("created_at")),
            "recipient": s.get("vendor_name") or "",
            "reference": s.get("po_number") or "",
            "status": s.get("status") or "",
            "lines": a["n"],
            "qty": round(a["qty"], 3),
            "pdf_url": f"/api/export-pdf?type=vendor-shipment&id={s.get('id')}",
            "pdf_alt_url": "",
            "pdf_alt_label": "",
            "vehicle_no": s.get("vehicle_no") or "",
        })
    return out


async def _rows_buyer(db) -> list[dict]:
    heads = {}
    async for b in db.buyer_shipments.find({}, {"_id": 0}):
        heads[b.get("id")] = b
    agg = {}
    async for it in db.buyer_shipment_items.find(
            {}, {"_id": 0, "shipment_id": 1, "dispatch_seq": 1, "dispatch_date": 1,
                 "qty_shipped": 1}):
        seq = int(it.get("dispatch_seq") or 1)
        k = (it.get("shipment_id"), seq)
        a = agg.setdefault(k, {"n": 0, "qty": 0.0, "date": it.get("dispatch_date")})
        a["n"] += 1
        a["qty"] += _f(it.get("qty_shipped"))
        if not a["date"]:
            a["date"] = it.get("dispatch_date")
    out = []
    for (sid, seq), a in agg.items():
        b = heads.get(sid) or {}
        base = b.get("shipment_number") or sid or ""
        out.append({
            "source": "buyer", "source_label": SOURCE_META["buyer"]["label"],
            "module": SOURCE_META["buyer"]["module"],
            "key": f"buyer:{sid}:{seq}",
            "id": sid,
            "sub_seq": seq,
            "number": f"{base}#{seq}",
            "doc_type": f"SJ-BUYER · kirim ke-{seq}",
            "date": _iso(a["date"] or b.get("last_dispatch") or b.get("created_at")),
            "recipient": b.get("customer_name") or b.get("vendor_name") or "",
            "reference": b.get("po_number") or "",
            "status": b.get("ship_status") or "",
            "lines": a["n"],
            "qty": round(a["qty"], 3),
            "pdf_url": (f"/api/export-pdf?type=buyer-shipment-dispatch"
                        f"&shipment_id={sid}&dispatch_seq={seq}"),
            # Dokumen kumulatif (seluruh pengiriman PO ini) — dipakai saat buyer minta rekap.
            "pdf_alt_url": f"/api/export-pdf?type=buyer-shipment&id={sid}",
            "pdf_alt_label": "PDF kumulatif",
            "vehicle_no": "",
        })
    return out


async def _unified_rows(db, *, source: str = "", q: str = "",
                        date_from: str = "", date_to: str = "") -> list[dict]:
    rows: list[dict] = []
    if source in ("", "all", "gudang"):
        rows += await _rows_gudang(db)
    if source in ("", "all", "vendor"):
        rows += await _rows_vendor(db)
    if source in ("", "all", "buyer"):
        rows += await _rows_buyer(db)
    rows = [r for r in rows if _hit(r, q) and _in_range(r, date_from, date_to)]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("number") or ""), reverse=True)
    return rows


@router.get("/sources")
async def list_sj_all_sources(
    request: Request,
    source: str = Query("", description="all|gudang|vendor|buyer"),
    q: str = Query("", description="cari nomor / tujuan / acuan"),
    date_from: str = Query("", description="YYYY-MM-DD"),
    date_to: str = Query("", description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=2000),
):
    """SATU daftar surat jalan lintas sumber — read-only, tanpa nomor baru (H-7)."""
    await require_auth(request)
    db = get_db()
    rows = await _unified_rows(db, source=source, q=q, date_from=date_from, date_to=date_to)
    counts = {"gudang": 0, "vendor": 0, "buyer": 0}
    for r in rows:
        counts[r["source"]] = counts.get(r["source"], 0) + 1
    return serialize_doc({
        "items": rows[:limit],
        "total": len(rows),
        "by_source": counts,
        "total_qty": round(sum(_f(r.get("qty")) for r in rows), 3),
        "sources": [{"key": k, **v} for k, v in SOURCE_META.items()],
    })


@router.get("/sources/recap-pdf")
async def recap_pdf_all_sources(
    request: Request,
    source: str = Query(""),
    q: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    token: str = Query("", description="dipakai bila diunduh lewat window.open"),
):
    """Cetak REKAP daftar surat jalan lintas sumber (bukan pengganti surat jalannya).

    Memakai helper `_pdf_data_table` (auto-wrap + lebar proporsional penuh halaman) sesuai
    keputusan Fase F1/F2 — tabel hardcode adalah sebab dokumen lama tumpang tindih.
    """
    if token:
        # Diunduh lewat window.open (tidak bisa mengirim header) — token di query string.
        if not verify_token_str(token):
            raise HTTPException(401, "Token tidak sah / kedaluwarsa.")
    else:
        await require_auth(request)
    db = get_db()
    rows = await _unified_rows(db, source=source, q=q, date_from=date_from, date_to=date_to)

    from routes.operations_pdf_helpers import (
        CONTENT_W_LANDSCAPE,
        _build_pdf,
        _pdf_data_table,
        _pdf_footer_branded,
        _pdf_header_branded,
    )
    profile = await get_company_profile(db)
    doc_settings = await get_doc_settings(db, "delivery-note-recap")
    periode = (f"{date_from or '…'} s/d {date_to or '…'}"
               if (date_from or date_to) else "semua tanggal")
    elements: list = []
    _pdf_header_branded(
        elements, profile, doc_settings, "REKAP SURAT JALAN — SEMUA SUMBER",
        info_pairs=[
            ("Periode", periode),
            ("Sumber", SOURCE_META.get(source, {}).get("label", "Semua sumber")),
            ("Kata kunci", q or "-"),
            ("Jumlah dokumen", str(len(rows))),
        ],
        avail=CONTENT_W_LANDSCAPE)
    # SESI #19 — susunan kolom rekap mengikuti TEMPLATE PDF pemilik (tampil/urutan/
    # lebar), sama seperti dokumen lain. Baris TOTAL dibangun PER KUNCI, bukan per
    # indeks tetap: begitu kolom diurutkan ulang, total per indeks akan mendarat di
    # kolom yang salah (cacat yang sama sudah pernah terjadi di surat jalan buyer).
    from routes.operations_pdf_helpers import tpl_table_parts
    all_keys = ["no", "sj_number", "source", "type", "date", "destination",
                "reference", "status", "lines", "qty"]
    all_headers = ["No", "No. Surat Jalan", "Sumber", "Jenis", "Tanggal", "Tujuan",
                   "Acuan (PO/Ref)", "Status", "Baris", "Total Qty"]
    data = []
    for i, r in enumerate(rows, 1):
        data.append([i, r["number"], r["source_label"], r["doc_type"],
                     (r.get("date") or "")[:10], r["recipient"], r["reference"] or "-",
                     r["status"], r["lines"], f"{_f(r.get('qty')):,.2f}"])
    headers, data, keys, weights, right_cols, doc_settings = await tpl_table_parts(
        db, "delivery-note-recap", all_keys, all_headers, data,
        numeric_keys=("no", "lines", "qty"))
    if not rows:
        data = [["-" if k == "no" else ("tidak ada surat jalan pada filter ini"
                                        if k == "sj_number" else "") for k in keys]]
    else:
        total_by_key = {
            "sj_number": f"TOTAL {len(rows)} dokumen",
            "lines": str(sum(int(r.get("lines") or 0) for r in rows)),
            "qty": f"{sum(_f(r.get('qty')) for r in rows):,.2f}",
        }
        data.append([total_by_key.get(k, "") for k in keys])
    elements.append(_pdf_data_table(
        headers, data, weights=weights, right_cols=right_cols,
        total_row=bool(rows), page="landscape",
        style=(doc_settings.get("_template") or {}).get("table")))
    _pdf_footer_branded(elements, profile, doc_settings)
    buf = io.BytesIO()
    _build_pdf(buf, elements, page="landscape")
    fname = f"rekap-surat-jalan-{(date_from or 'semua')}-{(date_to or 'tanggal')}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{sj_id}")
async def get_sj(sj_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"$or": [{"id": sj_id}, {"sj_number": sj_id}]}, {"_id": 0})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    return serialize_doc(sj)


@router.put("/{sj_id}")
async def update_sj(sj_id: str, data: dict, request: Request):
    user = await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"id": sj_id})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if sj["status"] != "draft":
        raise HTTPException(400, "Hanya draft Surat Jalan yang dapat diupdate")
    allowed = {"recipient_name", "recipient_address", "recipient_phone", "shipper_name",
               "vehicle_no", "notes", "lines", "reference_type", "reference_id", "reference_no"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if "lines" in updates:
        updates["lines"] = [{"line_no": i + 1, **ln} for i, ln in enumerate(updates["lines"])]
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("name", user["id"])
    await db.wh_delivery_notes.update_one({"id": sj_id}, {"$set": updates})
    out = await db.wh_delivery_notes.find_one({"id": sj_id}, {"_id": 0})
    return {"ok": True, "sj": serialize_doc(out)}


@router.post("/{sj_id}/issue")
async def issue_sj(sj_id: str, data: IssueIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"id": sj_id})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if sj["status"] != "draft":
        raise HTTPException(400, "Hanya draft yang dapat di-issue")
    if not sj.get("lines"):
        raise HTTPException(400, "Surat Jalan harus memiliki minimal 1 item")
    updates = {
        "status": "issued",
        "issued_at": _now(),
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }
    if data.shipper_name:
        updates["shipper_name"] = data.shipper_name
    if data.vehicle_no:
        updates["vehicle_no"] = data.vehicle_no
    if data.notes:
        updates["notes"] = (sj.get("notes", "") + " " + data.notes).strip()
    await db.wh_delivery_notes.update_one({"id": sj_id}, {"$set": updates})

    # WS-E: SJ-INTERNAL → buat PENDING OUTBOUND_RM (best-effort resolve material_code).
    # Stok BELUM turun; gudang wajib Scan-Out di WMS. Baris yang tak ter-resolve → dokumen saja.
    pendings = []
    if sj.get("sj_type") == "SJ-INTERNAL":
        try:
            from routes.wms_receiving import helper_create_pending_outbound_rm
            for ln in sj.get("lines", []):
                code = (ln.get("material_code") or "").strip()
                if not code:
                    continue
                mat = await db.rahaza_materials.find_one({"code": code}, {"_id": 0})
                if not mat:
                    continue  # tak ter-resolve → tak sentuh stok
                pending = await helper_create_pending_outbound_rm(
                    db,
                    material_id=mat.get("id"),
                    material_code=code,
                    material_name=mat.get("name", ln.get("description", "")),
                    qty=float(ln.get("qty", 0) or 0),
                    unit=ln.get("unit", "pcs"),
                    source_type="delivery_note",
                    source_id=sj_id,
                    source_ref=sj.get("sj_number", ""),
                    notes=f"SJ Internal {sj.get('sj_number','')} — Scan-Out diperlukan",
                    created_by=user.get("email", user.get("name", "system")),
                )
                pendings.append({"pending_id": pending.get("id"), "ref_number": pending.get("ref_number"),
                                 "material_name": mat.get("name", ""), "qty": ln.get("qty", 0)})
            if pendings:
                await db.wh_delivery_notes.update_one(
                    {"id": sj_id},
                    {"$set": {"wms_pending_refs": [p["ref_number"] for p in pendings]}}
                )
        except Exception as e:  # noqa: BLE001 — pembuatan pending WMS adalah LANGKAH
            # TAMBAHAN: surat jalan sudah tersimpan, jadi kegagalan helper (mis. gedung
            # belum dipetakan) tidak boleh menggagalkan penerbitan SJ. Dicatat sebagai
            # warning supaya tetap terlihat, bukan ditelan.
            log.warning(f"Gagal buat pending outbound_rm SJ-INTERNAL {sj_id}: {e}")

    out = await db.wh_delivery_notes.find_one({"id": sj_id}, {"_id": 0})
    return {"ok": True, "sj": serialize_doc(out), "wms_pending": pendings,
            "scan_out_required": bool(pendings)}


@router.post("/{sj_id}/receive")
async def receive_sj(sj_id: str, data: ReceiveIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"id": sj_id})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if sj["status"] != "issued":
        raise HTTPException(400, "Hanya Surat Jalan issued yang dapat dikonfirmasi diterima")
    await db.wh_delivery_notes.update_one({"id": sj_id}, {"$set": {
        "status": "received",
        "received_at": _now(),
        "received_by": data.received_by or user.get("name", user["id"]),
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    out = await db.wh_delivery_notes.find_one({"id": sj_id}, {"_id": 0})
    return {"ok": True, "sj": serialize_doc(out)}


@router.post("/{sj_id}/cancel")
async def cancel_sj(sj_id: str, data: CancelIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"id": sj_id})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if sj["status"] == "received":
        raise HTTPException(400, "Surat Jalan yang sudah diterima tidak dapat dibatalkan")
    await db.wh_delivery_notes.update_one({"id": sj_id}, {"$set": {
        "status": "cancelled",
        "cancelled_at": _now(),
        "cancel_reason": data.reason,
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    return {"ok": True}


@router.delete("/{sj_id}")
async def delete_sj(sj_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one({"id": sj_id})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if sj["status"] not in ("draft", "cancelled"):
        raise HTTPException(400, "Hanya draft/cancelled yang dapat dihapus")
    await db.wh_delivery_notes.delete_one({"id": sj_id})
    return {"ok": True}


@router.get("/{sj_id}/pdf")
async def sj_pdf(
    sj_id: str,
    request: Request,
    token: str | None = None,
):
    """Surat Jalan cetak — SESI #19: DITULIS ULANG memakai TEMPLATE PDF pemilik.

    Keluhan pemilik: "header surat sangat buruk sekali". Yang terukur pada versi
    lama: kop digambar tangan dengan `canvas.drawString` pada koordinat milimeter
    tetap (nama PT 9 pt, alamat DIPOTONG 70 karakter, tanpa telepon/NPWP, tanpa
    LOGO sama sekali), tabelnya memakai 5 posisi X tetap sehingga uraian barang
    dipotong 60 karakter dan tidak pernah melipat, dan blok tanda tangan dipaksa
    maksimal 3 (`sig_defs[:3]`) dengan posisi X manual — blok ke-4 hilang tanpa pesan.

    Versi ini memakai fondasi yang sama dengan dokumen lain (platypus + template):
    kop bisa berlogo, kolom tabel bisa diatur & diurutkan, teks melipat rapi tanpa
    tumpang tindih (dijaga INV-F17), dan jumlah blok tanda tangan mengikuti setelan.
    """
    if token:
        user = verify_token_str(token)
        if not user:
            raise HTTPException(401, "Invalid token")
    else:
        user = await require_auth(request)
    db = get_db()
    sj = await db.wh_delivery_notes.find_one(
        {"$or": [{"id": sj_id}, {"sj_number": sj_id}]}, {"_id": 0})
    if not sj:
        raise HTTPException(404, "Surat Jalan tidak ditemukan")
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab tidak tersedia")

    from core.pdf_template import (footer_flowables, header_flowables,
                                   signature_flowables)
    from routes.operations_pdf_helpers import (CONTENT_W_PORTRAIT, _build_pdf,
                                               _pdf_data_table, tpl_table_parts)

    SJ_TYPE_LABELS = {
        "SJ-CMT": "Pengiriman ke CMT",
        "SJ-MAKLON": "Pengiriman ke Klien Maklon",
        "SJ-SUPPLIER": "Retur ke Supplier",
        "SJ-INTERNAL": "Transfer Internal",
        "SJ-ONLINE": "Pengiriman Online Shop",
    }
    issued_at = sj.get("issued_at") or sj.get("created_at")
    if hasattr(issued_at, "strftime"):
        tanggal = issued_at.strftime("%d/%m/%Y")
    else:
        tanggal = str(issued_at or "")[:10]

    all_keys = ['no', 'material_code', 'description', 'roll_no', 'qty', 'unit', 'remarks']
    all_headers = ['No', 'Kode Material', 'Uraian Barang', 'No. Roll', 'Qty', 'Satuan',
                   'Keterangan']
    rows = []
    for line in sj.get("lines", []):
        rows.append([
            line.get("line_no", ""), line.get("material_code", ""),
            line.get("description", ""), line.get("roll_no", ""),
            f"{float(line.get('qty', 0) or 0):,.2f}".replace(",", "."),
            line.get("unit", ""), line.get("remarks", ""),
        ])

    headers, rows2, keys, weights, right_cols, doc_settings = await tpl_table_parts(
        db, 'delivery-note', all_keys, all_headers, rows, numeric_keys=('qty',))
    tpl = (doc_settings or {}).get('_template') or {}
    profile = await get_company_profile(db)

    info = [
        ("No. Surat Jalan", sj.get("sj_number", "")),
        ("Tanggal", tanggal),
        ("Jenis", SJ_TYPE_LABELS.get(sj.get("sj_type", ""), sj.get("sj_type", ""))),
        ("Status", sj.get("status", "")),
        ("Kepada", sj.get("recipient_name", "")),
        ("Alamat", sj.get("recipient_address", "")),
    ]
    if sj.get("recipient_phone"):
        info.append(("Telepon", sj["recipient_phone"]))
    if sj.get("reference_no"):
        info.append((f"Acuan ({(sj.get('reference_type') or '-').upper()})",
                     sj["reference_no"]))
    info.append(("No. Kendaraan", sj.get("vehicle_no") or "-"))
    info.append(("Pengirim", sj.get("shipper_name") or "-"))

    elements = header_flowables(tpl.get('header'), profile, "SURAT JALAN",
                                info_pairs=info, avail=CONTENT_W_PORTRAIT)
    if headers:
        elements.append(_pdf_data_table(headers, rows2, weights=weights,
                                        right_cols=right_cols, style=tpl.get('table')))

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer
    if sj.get("notes"):
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph(
            f"<b>Catatan:</b> {str(sj['notes'])[:300]}",
            ParagraphStyle("sjNote", fontSize=8, leading=10.5)))

    elements.extend(signature_flowables(tpl.get('signatures'), {
        "issued_by": sj.get("shipper_name") or sj.get("created_by", ""),
        "recipient_name": sj.get("recipient_name", ""),
        "driver_name": sj.get("driver_name") or sj.get("shipper_name", ""),
        "sj_number": sj.get("sj_number", ""),
    }, avail=CONTENT_W_PORTRAIT))
    elements.extend(footer_flowables(tpl.get('footer'), profile))

    buf = _build_pdf(io.BytesIO(), elements)
    filename = f"surat-jalan-{sj.get('sj_number', sj_id).replace('/', '-')}.pdf"
    preview = request.query_params.get("preview") in ("1", "true", "yes")
    disposition = "inline" if preview else "attachment"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
