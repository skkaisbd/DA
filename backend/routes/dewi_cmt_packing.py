"""
CMT Packing & Stok Opname — Blueprint §2.7

Alur utama:
  1. CMT kirim barang → Tim Packing buat 'CMT Receipt'
  2. Tim Packing hitung fisik per SKU / warna / ukuran
  3. Admin Produksi verifikasi & approve → stock tercatat sebagai FG
  4. Barang lolos QC → tampil di Display Rak

Collections:
  cmt_receipts       — Header penerimaan dari CMT
  cmt_receipt_lines  — Baris detail per SKU/variant

Endpoints:
  GET    /api/prod/cmt-receipts                   — list (filter status, cmt_name)
  POST   /api/prod/cmt-receipts                   — buat penerimaan baru
  GET    /api/prod/cmt-receipts/{id}              — detail + lines
  PUT    /api/prod/cmt-receipts/{id}              — update header
  POST   /api/prod/cmt-receipts/{id}/lines        — tambah baris
  PUT    /api/prod/cmt-receipts/{id}/lines/{lid}  — update qty fisik sebuah baris
  DELETE /api/prod/cmt-receipts/{id}/lines/{lid}  — hapus baris
  POST   /api/prod/cmt-receipts/{id}/submit       — submit ke Admin (Pending→Submitted)
  POST   /api/prod/cmt-receipts/{id}/approve      — Admin approve → update FG stock
  POST   /api/prod/cmt-receipts/{id}/reject       — Admin reject
  GET    /api/prod/display-rak                    — tampilkan FG per kode/nama (approved+in_stock)
  GET    /api/prod/cmt-receipts/summary           — stats dashboard
"""
# ruff: noqa: E741

from fastapi import APIRouter, HTTPException, Request, Depends
from routes.production_rbac import deny_external_dep
from fastapi.responses import JSONResponse
import uuid
import re
import logging
from datetime import datetime, timezone

from database import get_db
from core import production_qty_ledger as qty_ledger
from utils.counters import gen_prefixed_number
from utils.variant_ssot import resolve_variant, ensure_fg_material
from auth import require_auth, serialize_doc, check_role, log_activity

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FASE 4 (UX) — STATUS PENERIMAAN FG DARI CMT: CUKUP DUA
# ─────────────────────────────────────────────────────────────────────────────
# Definisi SSOT-nya ada di `core/cmt_receipt_status.py` supaya konsumen lain
# (permak, buyer shipment) memakai gerbang yang SAMA — bukan salinan yang
# tertinggal (pelajaran audit: gerbang status yang disalin selalu menyimpang).
from core.cmt_receipt_status import (  # noqa: E402
    ST_QC, ST_DONE, ST_CANCELLED, STATUS_LABEL,
    canon_status as _canon_status,
    with_canon_status as _with_canon_status,
    canon_status_filter as _canon_status_filter,
)


async def _ensure_fg_for_cmt_line(db, ln: dict, doc: dict, user: dict) -> dict:
    """SSOT resolver for a CMT receipt line → returns the REAL FG material doc.

    Priority:
      1. Resolve master variant by SKU → ensure_fg_material (code == SKU, id = UUID).
      2. Existing FG material with code == SKU (case-insensitive).
      3. Create a minimal FG material (type='fg', code=SKU) so stock links to a real master.

    Guarantees the received FG becomes usable stock visible in FG Inventory / FG Matrix,
    instead of an orphaned `FG-{sku}` row disconnected from the SSOT master.
    """
    sku = (ln.get("sku_code") or "").strip()
    product_name = ln.get("product_name", "")
    color = ln.get("color", "")
    size = ln.get("size", "")
    if not sku:
        return None
    # 1) master variant → ensure FG
    try:
        variant = await resolve_variant(db, sku=sku)
        if variant:
            return await ensure_fg_material(db, variant, user=user)
    except Exception:
        logger.exception("CMT approve: gagal resolve/ensure FG dari variant untuk sku %s", sku)
    # 2) existing FG material by code
    fg = await db.rahaza_materials.find_one(
        {"type": "fg", "code": {"$regex": f"^{re.escape(sku)}$", "$options": "i"}}, {"_id": 0})
    if fg:
        return fg
    # 3) create minimal FG master
    fg = {
        "id": _id(), "code": sku, "sku": sku,
        "name": f"{product_name} {color} {size}".strip() or sku,
        "type": "fg", "unit": "pcs", "active": True,
        "color": color, "size_code": size,
        "min_stock_qty": 0,
        "notes": f"Auto-created dari CMT receipt {doc.get('receipt_code')}",
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_materials.insert_one(dict(fg))
    return fg

router = APIRouter(prefix="/api/prod", tags=["cmt-packing"], dependencies=[Depends(deny_external_dep)])
def _id():  return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()


async def _seq(db, collection: str, prefix: str, field: str = "code") -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1 -> dup under concurrency)
    return await gen_prefixed_number(db, collection, field, f"{prefix}-", 5)


async def _recalc_receipt_totals(db, receipt_id: str):
    """Hitung ulang total header dari baris-barisnya.

    FASE IA-C (2026-07-26) — BUG NYATA: dulu hanya `update_line` (PUT) yang menghitung
    ulang header, sedangkan `add_line` (POST) tidak. Akibatnya penerimaan yang dibuat
    dengan cara normal (buat header → tambah baris berisi qty) meninggalkan
    `total_shipped_by_cmt = 0`, dan saat approve
    `production_maklon_bridge.mature_ap_from_cmt_receipt` membandingkan
    `total_shipped_by_cmt (0) != qty_actual + reject` → SETIAP tagihan CMT ditandai
    `variance_flagged=True` (alarm palsu "kiriman tidak cocok" pada 100% tagihan).
    """
    lines = await db.cmt_receipt_lines.find({"receipt_id": receipt_id}).to_list(500)

    def _n(ln, *keys):
        for k in keys:
            v = ln.get(k)
            if v not in (None, ""):
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return 0
        return 0

    await db.cmt_receipts.update_one({"id": receipt_id}, {"$set": {
        "total_actual": sum(int(ln.get("qty_actual", 0) or 0) for ln in lines),
        "total_rejected": sum(int(ln.get("reject_qty", 0) or 0) for ln in lines),
        "total_shipped_by_cmt": sum(int(ln.get("qty_shipped_by_cmt", 0) or 0) for ln in lines),
        # SELISIH KIRIM (aturan owner): klaim vendor vs yang benar-benar sampai
        "total_claimed_by_cmt": sum(_n(ln, "qty_claimed_by_cmt", "qty_shipped_by_cmt")
                                    for ln in lines),
        "total_qty_short": sum(int(ln.get("qty_short", 0) or 0) for ln in lines),
        "updated_at": _now(),
    }})


# ═══════════════════════════════════════════════════════
# DASHBOARD SUMMARY
# ═══════════════════════════════════════════════════════

@router.get("/cmt-receipts/summary")
async def receipt_summary(request: Request):
    await require_auth(request)
    db = get_db()
    total = await db.cmt_receipts.count_documents({})
    on_qc = await db.cmt_receipts.count_documents({"status": _canon_status_filter(ST_QC)})
    done = await db.cmt_receipts.count_documents({"status": _canon_status_filter(ST_DONE)})
    cancelled = await db.cmt_receipts.count_documents({"status": _canon_status_filter(ST_CANCELLED)})

    # Total pcs diterima hari ini (selesai QC)
    today = _now()[:10]
    pipeline = [
        {"$match": {"status": _canon_status_filter(ST_DONE),
                    "$or": [{"qc_completed_at": {"$gte": today}},
                            {"approved_at": {"$gte": today}}]}},
        {"$lookup": {"from": "cmt_receipt_lines", "localField": "id",
                     "foreignField": "receipt_id", "as": "lines"}},
        {"$unwind": {"path": "$lines", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": None,
                    "total_pcs": {"$sum": "$lines.qty_actual"},
                    "total_reject": {"$sum": "$lines.reject_qty"}}}
    ]
    res = await db.cmt_receipts.aggregate(pipeline).to_list(1)
    pcs_today = (res[0].get("total_pcs") or 0) if res else 0
    reject_today = (res[0].get("total_reject") or 0) if res else 0

    # FASE 22 — TOTAL KUMULATIF (semua status, bukan hanya hari ini).
    # Kartu KPI di UI dulu menghitung dari daftar TAB AKTIF, jadi saat tab
    # "Sedang QC" terbuka kartunya menunjukkan "Lolos QC 0 / Reject 0"
    # sementara panel Antrean Reject di layar yang sama berkata 30 pcs reject —
    # dua angka yang saling membantah. Sekarang angkanya datang dari sini.
    pipeline_all = [
        {"$match": {"status": _canon_status_filter(ST_DONE)}},
        {"$lookup": {"from": "cmt_receipt_lines", "localField": "id",
                     "foreignField": "receipt_id", "as": "lines"}},
        {"$unwind": {"path": "$lines", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": None,
                    "total_pcs": {"$sum": "$lines.qty_actual"},
                    "total_reject": {"$sum": "$lines.reject_qty"}}}
    ]
    res_all = await db.cmt_receipts.aggregate(pipeline_all).to_list(1)
    pcs_total = (res_all[0].get("total_pcs") or 0) if res_all else 0
    reject_total = (res_all[0].get("total_reject") or 0) if res_all else 0

    # baris yang belum dihitung pada penerimaan yang masih QC (angka kerja nyata)
    qc_ids = [d["id"] for d in await db.cmt_receipts.find(
        {"status": _canon_status_filter(ST_QC)}, {"_id": 0, "id": 1}).to_list(1000)]
    uncounted_lines = await db.cmt_receipt_lines.count_documents(
        {"receipt_id": {"$in": qc_ids}, "qty_actual": None}) if qc_ids else 0

    # Reject yang belum diputuskan (antrean kerja nyata, bukan angka mati)
    try:
        pending_reject = await qty_ledger.reject_queue(db, only_open=True, limit=500)
    except Exception:
        logger.exception("reject_queue gagal")
        pending_reject = []

    cmt_names = await db.cmt_receipts.distinct(
        "cmt_name", {"status": {"$nin": ["Rejected", "cancelled", "Cancelled"]}})

    return {
        "total": total,
        "on_qc": on_qc, "completed_qc": done, "cancelled": cancelled,
        # kompatibilitas nama lama supaya kartu FE lama tidak kosong
        "pending": on_qc, "submitted": on_qc, "approved": done, "rejected": cancelled,
        "pcs_approved_today": pcs_today,
        "pcs_reject_today": reject_today,
        "pcs_accepted_total": pcs_total,
        "pcs_reject_total": reject_total,
        "uncounted_lines": uncounted_lines,
        "reject_pending_decision": sum(r["qty_undecided"] for r in pending_reject),
        "reject_pending_lines": len(pending_reject),
        "active_cmt_count": len(cmt_names)
    }


# ═══════════════════════════════════════════════════════
# CMT RECEIPTS CRUD
# ═══════════════════════════════════════════════════════

@router.get("/cmt-receipts")
async def list_receipts(request: Request):
    """SATU tabel penerimaan FG dari CMT (FASE 4): semua angka yang dibutuhkan
    ada di baris daftar ini — tidak perlu masuk halaman dalam untuk melihat/isi."""
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get("status") and sp["status"] != "all":
        query["status"] = _canon_status_filter(sp["status"])
    if sp.get("cmt_name"):
        query["cmt_name"] = re.compile(re.escape(sp["cmt_name"]), re.IGNORECASE)
    if sp.get("wo_number"):
        query["wo_number"] = re.compile(re.escape(sp["wo_number"]), re.IGNORECASE)
    if sp.get("po_id"):
        query["po_id"] = sp["po_id"]
    docs = await db.cmt_receipts.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    ids = [d["id"] for d in docs]
    all_lines = await db.cmt_receipt_lines.find(
        {"receipt_id": {"$in": ids}}, {"_id": 0}).to_list(None) if ids else []
    by_receipt: dict = {}
    for ln in all_lines:
        by_receipt.setdefault(ln.get("receipt_id"), []).append(ln)
    # permak per baris (untuk kolom "reject belum diputuskan")
    line_ids = [ln["id"] for ln in all_lines]
    permaks = await db.dewi_cmt_permak.find(
        {"source_receipt_line_id": {"$in": line_ids}}, {"_id": 0}).to_list(None) if line_ids else []
    permak_qty: dict = {}
    for p in permaks:
        k = p.get("source_receipt_line_id")
        permak_qty[k] = permak_qty.get(k, 0) + int(p.get("qty") or 0)

    # ── keputusan owner 3a: deklarasi kirim CMT→DA bisa DIINPUT STAF DA ───────
    # Layar "Terima FG dari CMT" adalah gerbang UANG (qty_actual di sini yang
    # mematangkan tagihan CMT). Kalau deklarasi asalnya diketik staf — bukan
    # vendor — itu harus terlihat DI SINI juga, bukan cuma di monitoring.
    _ship_ids = [d.get("related_shipment_id") for d in docs if d.get("related_shipment_id")]
    _decl: dict = {}
    if _ship_ids:
        for s in await db.buyer_shipments.find(
                {"id": {"$in": _ship_ids}},
                {"_id": 0, "id": 1, "entered_by_staff": 1, "entered_by": 1,
                 "entered_by_role": 1}).to_list(None):
            _decl[s["id"]] = s

    for d in docs:
        _s = _decl.get(d.get("related_shipment_id")) or {}
        d["declaration_entered_by_staff"] = _s.get("entered_by_staff") is True
        d["declaration_entered_by"] = _s.get("entered_by", "")
        d["declaration_entered_by_role"] = _s.get("entered_by_role", "")
        _with_canon_status(d)
        lines = by_receipt.get(d["id"], [])
        d["lines"] = serialize_doc(lines)          # FASE 4: baris ikut di daftar
        d["line_count"] = len(lines)
        d["total_qty_expected"] = sum(int(ln.get("qty_expected") or 0) for ln in lines)
        d["total_qty_actual"] = sum(int(ln.get("qty_actual") or 0) for ln in lines
                                    if ln.get("qty_actual") is not None)
        _shipped = sum(int(ln.get("qty_shipped_by_cmt") or 0) for ln in lines)
        _reject = sum(int(ln.get("reject_qty") or 0) for ln in lines)
        _base = _shipped if _shipped > 0 else d["total_qty_actual"] + _reject
        d["total_qty_reject"] = _reject
        d["total_shipped_by_cmt"] = _shipped
        # ── SELISIH KIRIM: klaim vendor & qty yang BELUM SAMPAI (kewajiban vendor) ──
        d["total_claimed_by_cmt"] = sum(
            int(ln.get("qty_claimed_by_cmt") or ln.get("qty_shipped_by_cmt") or 0)
            for ln in lines)
        d["total_qty_short"] = sum(int(ln.get("qty_short") or 0) for ln in lines)
        d["total_qty_short_open"] = sum(
            max(0, int(ln.get("qty_short") or 0) - int(ln.get("qty_short_resolved") or 0))
            for ln in lines if (ln.get("short_status") or "") == "open")
        d["total_reject_undecided"] = sum(
            max(0, int(ln.get("reject_qty") or 0) - permak_qty.get(ln["id"], 0)) for ln in lines)
        d["uncounted_lines"] = sum(1 for ln in lines if ln.get("qty_actual") is None)
        d["pass_rate"] = round(d["total_qty_actual"] / _base * 100, 1) if _base > 0 else 0.0
        d["reject_rate"] = round(_reject / _base * 100, 1) if _base > 0 else 0.0
        d["can_complete_qc"] = (d["status"] == ST_QC and len(lines) > 0
                                and d["uncounted_lines"] == 0)
    return serialize_doc(docs)


@router.post("/cmt-receipts")
async def create_receipt(request: Request):
    """Create a new CMT Receipt (header only, or with auto-populated lines if
    `related_shipment_id` is provided — Phase B linkage to buyer_shipments
    doc where receiver_type='da'). Idempotent by `related_shipment_id`."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    # ─── PHASE B — Idempotent link to a CMT declaration shipment ──────────
    related_shipment_id = body.get('related_shipment_id') or body.get('cmt_shipment_id') or ''
    if related_shipment_id:
        existing = await db.cmt_receipts.find_one(
            {'related_shipment_id': related_shipment_id}, {'_id': 0}
        )
        if existing:
            return serialize_doc(existing)

    if not body.get("cmt_name"):
        # If linked to a buyer_shipment, derive cmt_name from it.
        if related_shipment_id:
            ship = await db.buyer_shipments.find_one({'id': related_shipment_id})
            if ship:
                body["cmt_name"] = ship.get('vendor_name', '') or body.get('cmt_name', '')
        if not body.get("cmt_name"):
            raise HTTPException(400, "cmt_name wajib diisi")

    # FASE G (sesi #18) — nomor penerimaan FG menghormati mode Otomatis/Manual yang
    # disetel System Admin (Penomoran Dokumen). Dulu selalu otomatis, jadi togglenya
    # tidak berpengaruh apa pun untuk dokumen ini.
    from core.doc_number_policy import issue_number
    code = await issue_number(db, "cmt_receipts.receipt_code",
                              requested=(body.get("receipt_code") or ""))
    now_ts = _now()
    doc = {
        "id": _id(), "receipt_code": code,
        "cmt_name": body["cmt_name"],
        "cmt_vendor_id": body.get("cmt_vendor_id", ""),
        "wo_number": body.get("wo_number", ""),
        "wo_id": body.get("wo_id", ""),
        "po_id": body.get("po_id", ""),
        "po_number": body.get("po_number", ""),
        "business_type": body.get("business_type", "internal"),
        "receipt_date": body.get("receipt_date", now_ts[:10]),
        "delivery_note": body.get("delivery_note", ""),
        "notes": body.get("notes", ""),
        "status": ST_QC,
        "submitted_at": "", "submitted_by": "",
        "approved_at": "", "approved_by": "",
        "reject_reason": "",
        # ─── PHASE B fields ────────────────────────────────────────────────
        "related_shipment_id": related_shipment_id,
        "total_shipped_by_cmt": 0,
        "total_actual": 0,
        "total_rejected": 0,
        "variance_reason": "",
        "defect_photos": body.get("defect_photos", []),
        # ────────────────────────────────────────────────────────────────────
        "created_by": user["name"], "created_at": now_ts, "updated_at": now_ts
    }
    await db.cmt_receipts.insert_one(doc)

    # If linked to a shipment, auto-populate lines from buyer_shipment_items.
    if related_shipment_id:
        try:
            ship_items = await db.buyer_shipment_items.find(
                {'shipment_id': related_shipment_id}, {'_id': 0}
            ).to_list(None)
            total_shipped = 0
            for it in ship_items:
                qty = int(it.get('qty_shipped', 0) or 0)
                if qty <= 0:
                    continue
                total_shipped += qty
                await db.cmt_receipt_lines.insert_one({
                    'id': _id(),
                    'receipt_id': doc['id'],
                    'sku_code': it.get('sku', ''),
                    'product_name': it.get('product_name', ''),
                    'color': it.get('color', ''),
                    'size': it.get('size', ''),
                    'qty_expected': qty,
                    'qty_shipped_by_cmt': qty,
                    'qty_claimed_by_cmt': qty,
                    'qty_short': 0, 'qty_short_resolved': 0, 'short_status': '',
                    'qty_actual': None,
                    'reject_qty': 0,
                    'reject_reason': '',
                    'photos': [],
                    'source_buyer_shipment_item_id': it.get('id'),
                    'po_item_id': it.get('po_item_id'),
                    'job_item_id': it.get('job_item_id'),
                    'notes': '',
                    'created_at': now_ts,
                })
            if total_shipped:
                await db.cmt_receipts.update_one(
                    {'id': doc['id']},
                    {'$set': {'total_shipped_by_cmt': total_shipped, 'updated_at': _now()}}
                )
                doc['total_shipped_by_cmt'] = total_shipped
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Phase B: gagal auto-populate cmt_receipt_lines untuk shipment %s',
                related_shipment_id
            )

    return JSONResponse(serialize_doc(doc), status_code=201)


@router.get("/cmt-receipts/{receipt_id}")
async def get_receipt(receipt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    _with_canon_status(doc)
    doc["lines"] = await db.cmt_receipt_lines.find({"receipt_id": receipt_id}, {"_id": 0}).to_list(500)
    return serialize_doc(doc)


@router.get("/cmt-reject-queue")
async def cmt_reject_queue(request: Request):
    """ANTREAN REJECT — supaya reject tidak pernah hilang dari layar (FASE 1).

    Menampilkan tiap baris penerimaan yang punya reject beserta sisa qty yang
    BELUM diputuskan (belum dijadikan permak sendiri / retur ke CMT / dibuang).
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    rows = await qty_ledger.reject_queue(
        db, po_id=sp.get("po_id"), vendor_id=sp.get("vendor_id"),
        only_open=(sp.get("only_open", "1") not in ("0", "false", "False")))
    return {"items": serialize_doc(rows), "total": len(rows),
            "total_qty_undecided": sum(r["qty_undecided"] for r in rows)}


@router.put("/cmt-receipts/{receipt_id}")
async def update_receipt(receipt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.cmt_receipts.find_one({"id": receipt_id})
    if not doc:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    if _canon_status(doc.get("status")) != ST_QC:
        raise HTTPException(400, "Hanya penerimaan yang masih 'Sedang QC' bisa diedit")
    # Phase B: added variance_reason + defect_photos to allowed fields.
    allowed = {k: v for k, v in body.items()
               if k in ("cmt_name", "wo_number", "wo_id", "receipt_date",
                        "delivery_note", "notes", "variance_reason", "defect_photos",
                        "po_id", "po_number")}
    allowed["updated_at"] = _now()
    await db.cmt_receipts.update_one({"id": receipt_id}, {"$set": allowed})
    result = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    return serialize_doc(result)


# ═══════════════════════════════════════════════════════
# LINES (per-SKU detail)
# ═══════════════════════════════════════════════════════

@router.post("/cmt-receipts/{receipt_id}/lines")
async def add_line(receipt_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    receipt = await db.cmt_receipts.find_one({"id": receipt_id})
    if not receipt:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    if _canon_status(receipt.get("status")) != ST_QC:
        raise HTTPException(400, "Tidak bisa tambah baris — QC sudah selesai/dibatalkan")
    body = await request.json()
    if not body.get("product_name") and not body.get("sku_code"):
        raise HTTPException(400, "product_name atau sku_code wajib diisi")
    line = {
        "id": _id(), "receipt_id": receipt_id,
        "sku_code": body.get("sku_code", ""),
        "product_name": body.get("product_name", ""),
        "color": body.get("color", ""),
        "size": body.get("size", ""),
        "qty_expected": int(body.get("qty_expected", 0)),
        "qty_actual": body.get("qty_actual"),
        # ─── PHASE B fields ────────────────────────────────────────────────
        "qty_shipped_by_cmt": int(body.get("qty_shipped_by_cmt", 0) or 0),
        # SELISIH KIRIM: klaim vendor disimpan terpisah dari dokumen resmi
        "qty_claimed_by_cmt": int(body.get("qty_claimed_by_cmt",
                                           body.get("qty_shipped_by_cmt", 0)) or 0),
        "qty_short": 0, "qty_short_resolved": 0, "short_status": "",
        "reject_qty": int(body.get("reject_qty", 0) or 0),
        "reject_reason": body.get("reject_reason", ""),
        "photos": body.get("photos", []),
        "source_buyer_shipment_item_id": body.get("source_buyer_shipment_item_id", ""),
        "po_item_id": body.get("po_item_id", ""),
        "job_item_id": body.get("job_item_id", ""),
        # ────────────────────────────────────────────────────────────────────
        "notes": body.get("notes", ""),
        "created_at": _now()
    }
    await db.cmt_receipt_lines.insert_one(line)
    await _recalc_receipt_totals(db, receipt_id)
    return JSONResponse(serialize_doc(line), status_code=201)


@router.put("/cmt-receipts/{receipt_id}/lines/{line_id}")
async def update_line(receipt_id: str, line_id: str, request: Request):
    """Isi/ubah angka QC sebuah baris — HANYA selama penerimaan masih `on_qc`.

    BUG P0 YANG DITUTUP (audit 2026-07-31, GAP B): endpoint ini dulu membalas 200
    walau QC SUDAH SELESAI, sementara buku kuantitas & stok TIDAK ikut berubah →
    angka bercabang tanpa peringatan (baris 100, buku 90, stok 90). Sekarang
    ditolak 409 dan pengguna diarahkan ke fitur KOREKSI RESMI yang konsisten:
      · POST …/lines/{lid}/koreksi-hasil-qc   (qty lolos/reject salah input)
      · POST …/lines/{lid}/koreksi-deklarasi  (klaim vendor salah tulis)
    """
    await require_auth(request)
    db = get_db()
    body = await request.json()
    receipt = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    st = _canon_status(receipt.get("status"))
    if st == ST_DONE:
        raise HTTPException(
            409,
            "QC penerimaan ini SUDAH SELESAI — angka tidak boleh diubah langsung karena "
            "stok FG, karantina, dan buku kuantitas sudah terbentuk. Pakai fitur koreksi "
            "resmi: 'Koreksi hasil QC' (qty lolos/reject) atau 'Koreksi deklarasi' "
            "(klaim vendor) supaya stok & buku kuantitas ikut dikoreksi beserta jejak audit.")
    if st == ST_CANCELLED:
        raise HTTPException(409, "Penerimaan sudah dibatalkan — tidak bisa diubah.")
    # Phase B: whitelist mutable fields explicitly. reject_qty/reject_reason/photos/
    # qty_actual are the DA-fill fields; qty_shipped_by_cmt is fixed after creation.
    allowed_keys = {
        'sku_code', 'product_name', 'color', 'size',
        'qty_expected', 'qty_actual', 'notes',
        'reject_qty', 'reject_reason', 'photos',
        'po_item_id', 'job_item_id',
    }
    update = {k: v for k, v in body.items() if k in allowed_keys}
    # Coerce numeric fields
    for nk in ('qty_expected', 'qty_actual', 'reject_qty'):
        if nk in update and update[nk] is not None:
            try:
                update[nk] = int(update[nk])
            except (TypeError, ValueError):
                raise HTTPException(400, f'{nk} harus angka')
    update['updated_at'] = _now()
    await db.cmt_receipt_lines.update_one({"id": line_id, "receipt_id": receipt_id}, {"$set": update})
    # Total header dihitung ulang lewat SATU helper (SSOT) — lihat _recalc_receipt_totals.
    await _recalc_receipt_totals(db, receipt_id)
    result = await db.cmt_receipt_lines.find_one({"id": line_id}, {"_id": 0})
    return serialize_doc(result)


@router.delete("/cmt-receipts/{receipt_id}/lines/{line_id}")
async def delete_line(receipt_id: str, line_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await db.cmt_receipt_lines.delete_one({"id": line_id, "receipt_id": receipt_id})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# KOREKSI RESMI (P0-1 · P0-2) — SATU-SATUNYA jalan mengubah angka yang SUDAH final
# ═══════════════════════════════════════════════════════════════════════════
# Aturan owner: "dokumen data apa yang dikirimkan harus sesuai".
#   · koreksi-hasil-qc   → qty lolos / reject salah input → stok FG & buku kuantitas
#                          ikut dikoreksi (bukan tulis mentah), ada jejak audit.
#   · koreksi-deklarasi  → klaim vendor salah tulis → dokumen deklarasi + selisih
#                          disesuaikan; vendor DAPAT NOTIFIKASI (bukan sanggahan).

async def _line_or_404(db, receipt_id: str, line_id: str):
    receipt = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    line = await db.cmt_receipt_lines.find_one({"id": line_id, "receipt_id": receipt_id}, {"_id": 0})
    if not line:
        raise HTTPException(404, "Baris penerimaan tidak ditemukan")
    return receipt, line


async def _after_correction(db, receipt_id: str, line: dict, user: dict,
                            claimed: int, arrived: int, reason: str) -> dict:
    """Segarkan dokumen selisih + buku kuantitas dari DOKUMEN SUMBER (satu rumus)."""
    from core import short_shipment as shortmod
    receipt = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    ji = await qty_ledger.resolve_job_item_for_line(db, line)
    short_doc = await shortmod.record_cmt_short(
        db, receipt=receipt, line=line, claimed=claimed, arrived=arrived,
        job_item=ji, actor=user, reason=reason)
    short_qty = max(0, int(claimed) - int(arrived))
    await db.cmt_receipt_lines.update_one({"id": line["id"]}, {"$set": {
        "qty_claimed_by_cmt": int(claimed),
        "qty_shipped_by_cmt": int(arrived) if _canon_status(receipt.get("status")) == ST_DONE
        else int(claimed),
        "qty_short": short_qty,
        "short_status": "open" if short_qty > 0 else "",
        "updated_at": _now()}})
    await _recalc_receipt_totals(db, receipt_id)
    resync = None
    if line.get("po_item_id"):
        resync = await qty_ledger.resync_from_documents(
            db, po_item_id=line["po_item_id"],
            prefer_job_item_id=(ji or {}).get("id", ""))
    return {"short": serialize_doc(short_doc) if short_doc else None,
            "ledger_resync": serialize_doc(resync) if resync else None}


@router.post("/cmt-receipts/{receipt_id}/lines/{line_id}/koreksi-hasil-qc")
async def koreksi_hasil_qc(receipt_id: str, line_id: str, request: Request):
    """KOREKSI RESMI hasil QC sebuah baris SETELAH penerimaan selesai QC.

    Efek (semuanya, atau ditolak):
      1. stok FG dikoreksi sebesar selisihnya lewat SSOT stok (`core/stock_service`);
      2. baris penerimaan diperbarui + `koreksi_history` (jejak audit) + log aktivitas;
      3. dokumen selisih kirim disegarkan (dibuat / diperbarui / dibatalkan);
      4. buku kuantitas dihitung ULANG dari dokumen sumber (satu rumus, idempoten).
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    receipt, line = await _line_or_404(db, receipt_id, line_id)
    if _canon_status(receipt.get("status")) != ST_DONE:
        raise HTTPException(
            400, "Penerimaan masih 'Sedang QC' — cukup ubah angkanya langsung "
                 "(PUT baris), koreksi resmi hanya untuk penerimaan yang sudah selesai QC.")
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Alasan koreksi wajib diisi (jejak audit).")
    old_actual = int(line.get("qty_actual") or 0)
    old_reject = int(line.get("reject_qty") or 0)
    try:
        new_actual = int(body.get("qty_actual", old_actual) or 0)
        new_reject = int(body.get("reject_qty", old_reject) or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "qty_actual / reject_qty harus angka")
    if new_actual < 0 or new_reject < 0:
        raise HTTPException(400, "qty tidak boleh negatif")
    claimed = int(line.get("qty_claimed_by_cmt") or line.get("qty_shipped_by_cmt") or 0)
    if claimed and (new_actual + new_reject) > claimed:
        raise HTTPException(
            400, f"lolos ({new_actual}) + reject ({new_reject}) melebihi klaim vendor "
                 f"({claimed}). Bila klaim vendor yang salah, pakai 'Koreksi deklarasi'.")
    if new_actual == old_actual and new_reject == old_reject:
        raise HTTPException(400, "Tidak ada perubahan angka.")
    if new_reject != old_reject:
        # reject sudah menjadi barang karantina (dan mungkin sudah dipermak/diretur):
        # mengubahnya butuh pembongkaran karantina → belum didukung, tolak jelas.
        handled = await db.dewi_cmt_permak.count_documents({"source_receipt_line_id": line_id})
        if handled:
            raise HTTPException(
                409, "Reject baris ini sudah diproses permak/retur ke CMT — angka reject "
                     "tidak bisa dikoreksi. Selesaikan dulu dokumen permaknya.")
        raise HTTPException(
            409, "Koreksi qty REJECT belum didukung karena barang reject sudah masuk "
                 "karantina QC. Batalkan/selesaikan dokumen karantina & permak terlebih "
                 "dahulu, atau koreksi hanya qty LOLOS.")

    delta = new_actual - old_actual
    stock_note = None
    fg_material_id = line.get("fg_material_id") or ""
    if delta != 0:
        mat = await qty_ledger.resolve_fg_material(
            db, material_id=fg_material_id, sku=line.get("sku_code", ""))
        if not mat:
            raise HTTPException(400, "Master FG baris ini tidak ditemukan — stok tidak bisa dikoreksi.")
        ref = {"source": "cmt_receipt_koreksi", "receipt_id": receipt_id,
               "receipt_code": receipt.get("receipt_code"), "receipt_line_id": line_id,
               "po_id": receipt.get("po_id"), "po_number": receipt.get("po_number"),
               "reason": reason}
        try:
            if delta > 0:
                posted = await qty_ledger.post_fg_accepted(
                    db, material_id=mat["id"], qty=delta, ref=ref, actor=user,
                    meta={"material_code": mat.get("code", ""), "material_name": mat.get("name", ""),
                          "unit": "pcs", "type": "finished_goods"})
                loc = posted["location_id"]
                mv = "IN"
            else:
                await qty_ledger.issue_fg(db, material_id=mat["id"], qty=-delta,
                                          sku=line.get("sku_code", ""), ref=ref, actor=user)
                loc = await qty_ledger.resolve_fg_location_id(db)
                mv = "OUT"
        except qty_ledger.FGStockShortfall as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("koreksi stok FG gagal (line %s)", line_id)
            raise HTTPException(500, f"Koreksi stok FG gagal: {e}")
        await db.rahaza_fg_movements.insert_one({
            "id": _id(), "sku_code": line.get("sku_code", ""), "movement_type": mv,
            "qty": abs(delta), "source": "cmt_receipt_koreksi", "ref_id": receipt_id,
            "ref_number": receipt.get("receipt_code"), "material_id": mat["id"],
            "location_id": loc,
            "notes": f"Koreksi hasil QC {old_actual} → {new_actual} pcs. Alasan: {reason}",
            "created_by": user["name"], "created_at": _now()})
        stock_note = {"delta": delta, "movement": mv}

    entry = {"field": "qty_actual", "old": old_actual, "new": new_actual,
             "reject_old": old_reject, "reject_new": new_reject, "reason": reason,
             "by": user["name"], "by_id": user["id"], "at": _now(),
             "stock": stock_note}
    await db.cmt_receipt_lines.update_one({"id": line_id}, {
        "$set": {"qty_actual": new_actual, "reject_qty": new_reject, "updated_at": _now()},
        "$push": {"koreksi_history": entry}})
    line = await db.cmt_receipt_lines.find_one({"id": line_id}, {"_id": 0})
    extra = await _after_correction(db, receipt_id, line, user, claimed,
                                   new_actual + new_reject, reason)
    # Angka dokumen (yang benar-benar sampai) berubah → vendor diberi tahu.
    try:
        from core import short_shipment as _sm
        await _sm.notify_declaration_correction(
            db, receipt=receipt, line=line, old_value=old_actual + old_reject,
            new_value=new_actual + new_reject, reason=reason, actor=user,
            field="qty diterima DA")
    except Exception:  # noqa: BLE001
        logger.exception("notifikasi koreksi hasil QC gagal (line %s)", line_id)
    await log_activity(user["id"], user["name"], "Koreksi Hasil QC", "Terima FG dari CMT",
                       f"{receipt.get('receipt_code')} · {line.get('sku_code')}: lolos "
                       f"{old_actual} → {new_actual} pcs. Alasan: {reason}")
    return {"success": True, "line": serialize_doc(line), "stock": stock_note, **extra}


@router.post("/cmt-receipts/{receipt_id}/lines/{line_id}/koreksi-deklarasi")
async def koreksi_deklarasi(receipt_id: str, line_id: str, request: Request):
    """KOREKSI KLAIM VENDOR (`qty_claimed_by_cmt`) + rambatkan ke dokumen deklarasi.

    Dipakai bila angka KLAIM vendor yang salah tulis (mis. tertulis 100 padahal
    vendor memang hanya mengirim 90 → selisih seharusnya 0). Boleh dilakukan
    sepihak oleh Admin DA (keputusan owner) — vendor DIBERI NOTIFIKASI + label jelas.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    receipt, line = await _line_or_404(db, receipt_id, line_id)
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Alasan koreksi wajib diisi (jejak audit).")
    try:
        new_claim = int(body.get("qty_claimed", body.get("qty_claimed_by_cmt")))
    except (TypeError, ValueError):
        raise HTTPException(400, "qty_claimed wajib angka")
    if new_claim < 0:
        raise HTTPException(400, "qty_claimed tidak boleh negatif")
    arrived = int(line.get("qty_actual") or 0) + int(line.get("reject_qty") or 0)
    is_done = _canon_status(receipt.get("status")) == ST_DONE
    if is_done and new_claim < arrived:
        raise HTTPException(
            400, f"Klaim ({new_claim}) tidak boleh lebih kecil dari yang sudah tercatat "
                 f"sampai ({arrived} pcs). Koreksi hasil QC dulu bila angka itu yang salah.")
    old_claim = int(line.get("qty_claimed_by_cmt") or line.get("qty_shipped_by_cmt") or 0)
    entry = {"field": "qty_claimed_by_cmt", "old": old_claim, "new": new_claim,
             "reason": reason, "by": user["name"], "by_id": user["id"], "at": _now()}
    await db.cmt_receipt_lines.update_one({"id": line_id}, {
        "$set": {"qty_claimed_by_cmt": new_claim,
                 "qty_shipped_by_cmt": arrived if is_done else new_claim,
                 "updated_at": _now()},
        "$push": {"koreksi_history": entry}})
    from core import short_shipment as shortmod
    await shortmod._propagate_declaration_correction(
        db, line=line, arrived=arrived if is_done else new_claim, claimed=new_claim, actor=user)
    line = await db.cmt_receipt_lines.find_one({"id": line_id}, {"_id": 0})
    extra = {}
    if is_done:
        extra = await _after_correction(db, receipt_id, line, user, new_claim, arrived, reason)
    # Vendor WAJIB diberi tahu (keputusan owner: koreksi sepihak + notifikasi jelas)
    try:
        await shortmod.notify_declaration_correction(
            db, receipt=receipt, line=line, old_value=old_claim, new_value=new_claim,
            reason=reason, actor=user, field="klaim kirim")
    except Exception:  # noqa: BLE001
        logger.exception("notifikasi koreksi deklarasi gagal (line %s)", line_id)
    await log_activity(user["id"], user["name"], "Koreksi Deklarasi CMT", "Terima FG dari CMT",
                       f"{receipt.get('receipt_code')} · {line.get('sku_code')}: klaim vendor "
                       f"{old_claim} → {new_claim} pcs. Alasan: {reason}")
    return {"success": True, "line": serialize_doc(line), **extra}


# ═══════════════════════════════════════════════════════════════════════════
# SELISIH KIRIM CMT → DA (dokumen kelas satu, TANPA batas waktu otomatis)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/short-shipments")
async def list_short_shipments(request: Request):
    """Daftar selisih kirim vendor CMT → DA (barang belum sampai).

    `?status=open|resolved|cancelled|all` · `?po_id=` · `?vendor_id=`
    Vendor CMT hanya melihat selisihnya sendiri.
    """
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    from core import short_shipment as shortmod
    from routes.production_rbac import is_vendor, vendor_identity
    vendor_id = sp.get("vendor_id") or ""
    if is_vendor(user):
        vendor_id = vendor_identity(user) or "__none__"
    else:
        # Portal CMT Override — staf DA melihat selisih vendor yang diwakilinya.
        from core.cmt_override import resolve_override
        _ov = await resolve_override(request, user, db)
        if _ov:
            vendor_id = _ov['vendor_id']
    out = await shortmod.list_cmt_shorts(
        db, status=(sp.get("status") or "open"), po_id=sp.get("po_id") or "",
        vendor_id=vendor_id)
    return serialize_doc(out)


@router.post("/short-shipments/{short_id}/resolve")
async def resolve_short_shipment(short_id: str, request: Request):
    """Selesaikan selisih kirim: dikirim ulang / hilang (tanggungan vendor atau DA) /
    salah input. Keputusan MANUAL per kejadian (keputusan owner) — tidak ada
    pemotongan tagihan otomatis; Finance memprosesnya di modul tagihan CMT."""
    user = await require_auth(request)
    db = get_db()
    if not check_role(user, ["admin", "admin_maklon", "admin_produksi",
                            "supervisor_produksi", "owner", "manager", "finance"]):
        raise HTTPException(403, "Hanya Admin/Finance yang boleh menyelesaikan selisih kirim")
    body = await request.json()
    from core import short_shipment as shortmod
    try:
        doc = await shortmod.resolve_cmt_short_manual(
            db, short_id, resolution=(body.get("resolution") or "").strip(),
            notes=(body.get("notes") or "").strip(), actor=user)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if doc and doc.get("po_item_id"):
        await qty_ledger.resync_from_documents(db, po_item_id=doc["po_item_id"],
                                               prefer_job_item_id=doc.get("job_item_id", ""))
    await log_activity(user["id"], user["name"], "Selesaikan Selisih Kirim", "Terima FG dari CMT",
                       f"{(doc or {}).get('short_number')} · {(doc or {}).get('sku')} "
                       f"{(doc or {}).get('qty_short')} pcs → {body.get('resolution')}")
    return {"success": True, "short": serialize_doc(doc)}



# ═══════════════════════════════════════════════════════
# WORKFLOW
# ═══════════════════════════════════════════════════════

@router.post("/cmt-receipts/{receipt_id}/submit")
async def submit_receipt(receipt_id: str, request: Request):
    """DEPRECATED (FASE 4 UX) — dulu: Draft → Submitted → Approved (3 langkah + halaman
    terpisah). Sekarang penerimaan hanya punya 2 status: `on_qc` → `completed_qc`.
    Endpoint ini dipertahankan supaya klien lama tidak pecah: ia hanya memastikan
    penerimaan masih `on_qc` dan mengembalikan dokumennya (tidak mengubah status).
    """
    await require_auth(request)
    db = get_db()
    doc = await db.cmt_receipts.find_one({"id": receipt_id})
    if not doc:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    if _canon_status(doc.get("status")) == ST_DONE:
        raise HTTPException(400, "Penerimaan sudah selesai QC")
    lines = await db.cmt_receipt_lines.find({"receipt_id": receipt_id}).to_list(500)
    if not lines:
        raise HTTPException(400, "Tambahkan minimal 1 item sebelum menyelesaikan QC")
    counted = [ln for ln in lines if ln.get("qty_actual") is not None]
    if not counted:
        raise HTTPException(400, "Hitung qty fisik minimal 1 item")
    await db.cmt_receipts.update_one({"id": receipt_id}, {"$set": {
        "status": ST_QC, "updated_at": _now()}})
    result = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    return serialize_doc(_with_canon_status(result))


@router.post("/cmt-receipts/{receipt_id}/complete-qc")
async def complete_qc(receipt_id: str, request: Request):
    """SATU-SATUNYA aksi penyelesaian penerimaan FG dari CMT (FASE 1+4).

    Menggantikan rangkaian submit → approve. Efek (semuanya, atau ditolak):
      1. Validasi tiap baris sudah dihitung (`qty_actual` terisi) dan
         qty_actual + reject_qty tidak melebihi qty yang dideklarasikan vendor.
      2. Stok FG += Σ qty_actual  → lewat SSOT stok (`core/stock_service`,
         punya `location_id` kanonik + ledger mutasi).  BUG LAMA: dulu ditulis
         mentah ke `rahaza_material_stock` dengan `location: "gudang_fg"` tanpa
         `location_id` ⇒ stok hantu di luar SSOT.
      3. Reject → KARANTINA + buku kuantitas job item (`qty_reject`,
         `qty_rework_open`). Produksi vendor (`produced_qty`) TIDAK dikurangi.
      4. AP vendor CMT dimatangkan (qty lolos × rate) — idempoten.
    """
    return await _finish_receipt(receipt_id, request)


@router.post("/cmt-receipts/{receipt_id}/approve")
async def approve_receipt(receipt_id: str, request: Request):
    """Alias kompatibilitas untuk `complete-qc` (klien/FE lama)."""
    return await _finish_receipt(receipt_id, request)


async def _finish_receipt(receipt_id: str, request: Request):
    from routes.shared import require_perm
    user = await require_perm(
        request, 'cmt.approve', 'cmt.manage', 'production.approve',
        legacy_roles=('admin_maklon', 'supervisor_produksi', 'admin_produksi',
                      'manager_produksi', 'admin_gudang', 'manager',
                      'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menyelesaikan/menyetujui QC penerimaan CMT.')
    db = get_db()
    doc = await db.cmt_receipts.find_one({"id": receipt_id})
    if not doc:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    if _canon_status(doc.get("status")) == ST_DONE:
        raise HTTPException(400, "Penerimaan ini sudah selesai QC")
    if _canon_status(doc.get("status")) == ST_CANCELLED:
        raise HTTPException(400, "Penerimaan dibatalkan — tidak bisa diselesaikan")
    lines = await db.cmt_receipt_lines.find({"receipt_id": receipt_id}).to_list(500)
    if not lines:
        raise HTTPException(400, "Tambahkan minimal 1 item sebelum menyelesaikan QC")

    # ── Validasi angka (gerbang tunggal) ──
    belum = [ln.get("sku_code") or ln.get("product_name") or ln["id"]
             for ln in lines if ln.get("qty_actual") is None]
    if belum:
        raise HTTPException(400, "Qty fisik belum dihitung untuk: " + ", ".join(map(str, belum[:5])))
    for ln in lines:
        qa = int(ln.get("qty_actual") or 0)
        rj = int(ln.get("reject_qty") or 0)
        declared = int(ln.get("qty_shipped_by_cmt") or 0)
        if qa < 0 or rj < 0:
            raise HTTPException(400, "qty_actual/reject_qty tidak boleh negatif")
        if declared and (qa + rj) > declared:
            raise HTTPException(
                400,
                f"{ln.get('sku_code') or 'item'}: lolos ({qa}) + reject ({rj}) = {qa + rj} "
                f"melebihi yang dikirim vendor ({declared}). Perbaiki angkanya.")

    # ── 1. Stok FG untuk qty lolos QC — lewat SSOT stok ──
    stock_result = []
    for ln in lines:
        qty = int(ln.get("qty_actual") or 0)
        if qty <= 0:
            continue
        sku = (ln.get("sku_code") or "").strip()
        fg = await _ensure_fg_for_cmt_line(db, ln, doc, user)
        if not fg:
            raise HTTPException(
                400,
                f"Baris {sku or ln['id']} tidak punya SKU/master FG — tidak bisa masuk stok. "
                "Lengkapi SKU baris penerimaan atau varian PO-nya.")
        material_id = fg["id"]
        # simpan tautan material di baris supaya karantina & audit bisa memakainya
        await db.cmt_receipt_lines.update_one(
            {"id": ln["id"]}, {"$set": {"fg_material_id": material_id,
                                        "fg_material_code": fg.get("code", sku)}})
        ln["fg_material_id"] = material_id
        try:
            posted = await qty_ledger.post_fg_accepted(
                db, material_id=material_id, qty=qty,
                ref={"source": "cmt_receipt", "receipt_id": receipt_id,
                     "receipt_code": doc.get("receipt_code"),
                     "po_id": doc.get("po_id"), "po_number": doc.get("po_number"),
                     "vendor_id": doc.get("cmt_vendor_id"), "vendor_name": doc.get("cmt_name")},
                actor=user,
                meta={"material_code": fg.get("code", sku),
                      "material_name": fg.get("name", ""),
                      "unit": "pcs", "type": "finished_goods"})
        except Exception as e:  # noqa: BLE001
            logger.exception("post stok FG gagal (receipt %s line %s)", receipt_id, ln["id"])
            raise HTTPException(500, f"Gagal menambah stok FG: {e}")
        stock_result.append({"sku": fg.get("code", sku), "qty": qty,
                             "location_id": posted["location_id"]})
        await db.rahaza_fg_movements.insert_one({
            "id": _id(), "sku_code": sku,
            "movement_type": "IN", "qty": qty,
            "source": "cmt_receipt", "ref_id": receipt_id,
            "ref_number": doc.get("receipt_code"),
            "material_id": material_id,
            "location_id": posted["location_id"],
            "notes": f"Terima dari CMT {doc.get('cmt_name')} — lolos QC",
            "created_by": user["name"], "created_at": _now()})

    # ── 2. Status selesai QC ──
    await db.cmt_receipts.update_one({"id": receipt_id}, {"$set": {
        "status": ST_DONE,
        "qc_completed_at": _now(), "qc_completed_by": user["name"],
        # kompatibilitas kolom lama
        "approved_at": _now(), "approved_by": user["name"],
        "submitted_at": doc.get("submitted_at") or _now(),
        "submitted_by": doc.get("submitted_by") or user["name"],
        "updated_at": _now()}})

    # ── 3. Buku kuantitas job item + karantina reject (FASE 1) ──
    fresh = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    ledger_result = None
    try:
        ledger_result = await qty_ledger.apply_receipt_result(db, fresh, lines, actor=user)
    except Exception as e:  # noqa: BLE001
        logger.exception("propagasi buku kuantitas gagal (receipt %s)", receipt_id)
        ledger_result = {"applied": False, "errors": [str(e)]}

    # ── 4. AP vendor CMT (idempoten) ──
    ap_result = None
    try:
        from routes.production_maklon_bridge import mature_ap_from_cmt_receipt
        ap_result = await mature_ap_from_cmt_receipt(db, receipt_id, user)
    except Exception:
        logger.exception('gagal mature AP dari cmt_receipt %s', receipt_id)

    # ── 5. Segarkan total header SETELAH buku kuantitas menulis qty_short /
    # qty_claimed_by_cmt ke baris (kalau tidak, `total_qty_short` di header
    # tertinggal 0 walau barisnya punya selisih → dua angka lagi).
    await _recalc_receipt_totals(db, receipt_id)

    result = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    out = serialize_doc(_with_canon_status(result))
    out['stock_posted'] = stock_result
    out['qty_ledger'] = serialize_doc(ledger_result) if ledger_result else None
    if ap_result is not None:
        out['ap_mature'] = serialize_doc(ap_result)
    return out


@router.post("/cmt-receipts/{receipt_id}/reject")
async def reject_receipt(receipt_id: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'cmt.approve', 'cmt.manage', 'production.approve',
        legacy_roles=('admin_maklon', 'supervisor_produksi', 'admin_produksi',
                      'manager_produksi', 'admin_gudang', 'manager',
                      'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menolak penerimaan CMT.')
    db = get_db()
    body = await request.json()
    doc = await db.cmt_receipts.find_one({"id": receipt_id})
    if not doc:
        raise HTTPException(404, "Penerimaan tidak ditemukan")
    if _canon_status(doc.get("status")) != ST_QC:
        raise HTTPException(400, "Tidak bisa dibatalkan — QC sudah selesai")
    await db.cmt_receipts.update_one({"id": receipt_id}, {"$set": {
        "status": ST_CANCELLED,
        "reject_reason": body.get("reason", ""),
        "updated_at": _now()
    }})
    result = await db.cmt_receipts.find_one({"id": receipt_id}, {"_id": 0})
    return serialize_doc(result)


# ═══════════════════════════════════════════════════════
# DISPLAY RAK
# ═══════════════════════════════════════════════════════

@router.get("/display-rak")
async def display_rak(request: Request):
    """
    Tampilkan semua item FG yang sudah approved dari CMT.
    Grouped by sku_code → aggregated qty.
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    # Ambil semua approved receipts
    receipts_q = {"status": "Approved"}
    if sp.get("cmt_name"):
        receipts_q["cmt_name"] = re.compile(re.escape(sp["cmt_name"]), re.IGNORECASE)
    receipt_ids = await db.cmt_receipts.distinct("id", receipts_q)
    if not receipt_ids:
        return []
    # Aggregate lines
    lines_q = {"receipt_id": {"$in": receipt_ids}, "qty_actual": {"$gt": 0}}
    if sp.get("search"):
        rx = re.compile(re.escape(sp["search"]), re.IGNORECASE)
        lines_q["$or"] = [{"sku_code": rx}, {"product_name": rx}]
    pipeline = [
        {"$match": lines_q},
        {"$group": {
            "_id": {"sku_code": "$sku_code", "product_name": "$product_name",
                    "color": "$color", "size": "$size"},
            "total_qty": {"$sum": "$qty_actual"},
            "last_received": {"$max": "$created_at"}
        }},
        {"$sort": {"_id.product_name": 1, "_id.color": 1, "_id.size": 1}}
    ]
    res = await db.cmt_receipt_lines.aggregate(pipeline).to_list(500)
    out = []
    for r in res:
        g = r["_id"]
        out.append({
            "sku_code": g.get("sku_code", ""),
            "product_name": g.get("product_name", ""),
            "color": g.get("color", ""),
            "size": g.get("size", ""),
            "total_qty": r["total_qty"],
            "last_received": r.get("last_received", "")
        })
    return serialize_doc(out)


# ═══════════════════════════════════════════════════════
# PRODUCTION DASHBOARD — Material per Lokasi
# ═══════════════════════════════════════════════════════

@router.get("/material-summary-by-location")
async def material_summary_by_location(request: Request):
    """
    Material issue stats grouped by location (for production dashboard multi-warehouse filter).
    Returns per-location: pending_issues, approved_issues, total_qty_issued.
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    loc_id = sp.get("location_id")

    # Get all material issues
    mis_q = {}
    if loc_id:
        # Filter by location: find pending movements from that location
        pending_ids = await db.wh_pending_movements.distinct(
            "source_id",
            {"type": "outbound_rm", "source_type": "rahaza_material_issue", "building_id": loc_id}
        )
        # Also match by location_id in MI items (fallback)
        mi_direct = await db.rahaza_material_issues.distinct("id", {"items.location_id": loc_id})
        all_ids = list(set((pending_ids or []) + (mi_direct or [])))
        mis_q["id"] = {"$in": all_ids or ["__none__"]}

    mis = await db.rahaza_material_issues.find(mis_q, {"_id": 0, "id": 1, "status": 1, "work_order_id": 1, "created_at": 1}).to_list(500)

    status_counts = {}
    for mi in mis:
        st = mi.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Locations list
    locations = await db.rahaza_locations.find({"active": True}, {"_id": 0}).to_list(500)

    return {
        "location_id": loc_id,
        "total_mis": len(mis),
        "by_status": status_counts,
        "locations": locations
    }
