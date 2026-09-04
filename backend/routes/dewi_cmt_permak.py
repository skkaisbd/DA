"""
routes/dewi_cmt_permak.py — CMT Permak / Rework (perbaikan barang cacat).

Domain: setelah FG dari CMT di-inspeksi di DA (`cmt_receipt_lines.reject_qty`), barang cacat
bisa dikirim ke PERMAK (rework). Permak yang **open/in_progress** mengurangi FG (barang belum
siap kirim). Hasil:
  - `selesai_berhasil` → sebagian/seluruh qty jadi bagus (qty_fixed) sisanya buang (qty_scrap)
  - `gagal_buang`      → seluruh qty dibuang (scrap)

Collection: `dewi_cmt_permak`
  id, permak_number (PMK/YYYY/MM/NNNN), po_id, po_number, po_item_id,
  sku, product_name, size, color, serial_number,
  source ('reject'|'good'), source_receipt_id, source_receipt_line_id,
  qty, qty_fixed, qty_scrap,
  vendor_permak, reason, notes, photos[],
  status ('open'|'in_progress'|'selesai_berhasil'|'gagal_buang'),
  status_history[], created_at, created_by, updated_at, updated_by

Prefix: /api/dewi/cmt-permak
Reconcile: services/maklon_progress.py membaca collection ini utk menghitung FG kanonik.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.production_rbac import PROD_ADMIN_ROLES, PROD_VENDOR_ROLES, is_vendor, vendor_identity
from routes.shared import can_act

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dewi/cmt-permak", tags=["dewi-cmt-permak"])

ACTIVE = ("open", "in_progress")
SUCCESS = "selesai_berhasil"
SCRAP = "gagal_buang"
ALL_STATUS = ("open", "in_progress", SUCCESS, SCRAP)
TERMINAL = (SUCCESS, SCRAP)
TRANSITIONS = {
    "open": {"in_progress", SUCCESS, SCRAP},
    "in_progress": {SUCCESS, SCRAP},
    SUCCESS: set(),
    SCRAP: set(),
}

# Jenis permak (S4: retur ke penjahit vs permak sendiri)
PERMAK_TYPES = ("permak_sendiri", "retur_ke_cmt")
# Taksonomi masalah (informational; UI bebas menambah via free-text bila perlu)
PROBLEM_TYPES = ("jahitan", "noda", "ukuran", "bahan", "aksesoris", "lainnya")


def _now():
    return datetime.now(timezone.utc)


def _id():
    return str(uuid.uuid4())


def _iv(v, default=0) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


async def _next_permak_no(db, requested: str = "") -> str:
    """Nomor permak — SATU PINTU kebijakan penomoran (SESI #27, batch-3 Fase G)."""
    from core.doc_number_policy import issue_number
    return await issue_number(db, "dewi_cmt_permak.permak_number", requested=requested)


def _require_admin(user: dict):
    # 2026-08-06 — gerbang izin terpusat (routes.shared.can_act, fallback aman).
    if not can_act(user, "cmt.permak.manage", "cmt.approve", "production.manage",
                   legacy_roles=PROD_ADMIN_ROLES):
        raise HTTPException(403, "Akses ditolak: butuh izin kelola permak (cmt.permak.manage).")


def _require_admin_or_vendor(user: dict):
    """Vendor CMT WAJIB bisa MELIHAT permak/rework miliknya (cacat PMK-2)."""
    if is_vendor(user):
        return
    if can_act(user, "cmt.view", "cmt.permak.manage", "production.manage",
               legacy_roles=PROD_ADMIN_ROLES):
        return
    raise HTTPException(403, "Akses ditolak: butuh izin melihat permak (cmt.view).")


# ─── Models ──────────────────────────────────────────────────────────────────
class PermakCreate(BaseModel):
    po_id: str = Field(..., min_length=1)
    po_item_id: str = Field(..., min_length=1)
    qty: int = Field(..., gt=0)
    source: str = "reject"          # 'reject' | 'good'
    permak_type: str = "permak_sendiri"   # 'permak_sendiri' | 'retur_ke_cmt'
    problem_type: str = ""          # jahitan|noda|ukuran|bahan|aksesoris|lainnya (free-text ok)
    # FASE 14 — `ge=0` WAJIB: tanpa batas ini `cost_per_pcs: -50000` diterima
    # HTTP 200 dan tersimpan, membuat `total_cost` NEGATIF (dibuktikan:
    # cost_per_pcs=-50000 × qty 2 → total_cost=-100000) ⇒ ongkos permak negatif
    # masuk pembukuan. Bukti & cara uji ulang: scripts/probe_numeric_bounds.py
    cost_per_pcs: float = Field(0.0, ge=0)   # ongkos permak per pcs
    return_deadline: Optional[str] = None  # YYYY-MM-DD, target selesai/kembali
    source_receipt_id: Optional[str] = None
    source_receipt_line_id: Optional[str] = None
    vendor_permak: str = ""
    reason: str = ""
    notes: str = ""
    photos: List[str] = []
    # SESI #27 — nomor ketikan staf (HANYA dipakai bila kebijakan = MANUAL).
    permak_number: Optional[str] = ""


class FromReceiptLine(BaseModel):
    receipt_line_id: str = Field(..., min_length=1)
    # `gt=0` menyamakan penolakan di level model dengan guard handler
    # ("qty harus > 0") — deklaratif, muncul di OpenAPI, tidak bergantung urutan kode.
    qty: Optional[int] = Field(default=None, gt=0)   # default = sisa reject yang belum dipermak
    permak_type: str = "permak_sendiri"
    problem_type: str = ""
    cost_per_pcs: float = Field(0.0, ge=0)   # FASE 14 — lihat PermakCreate.cost_per_pcs
    return_deadline: Optional[str] = None
    vendor_permak: str = ""
    reason: str = ""
    notes: str = ""
    photos: List[str] = []
    # SESI #27 — nomor ketikan staf (HANYA dipakai bila kebijakan = MANUAL).
    permak_number: Optional[str] = ""


class PermakUpdate(BaseModel):
    qty: Optional[int] = Field(default=None, gt=0)
    permak_type: Optional[str] = None
    problem_type: Optional[str] = None
    # FASE 14 — dibuktikan bisa menyimpan -12345 (total_cost jadi -24690) lewat
    # PUT /api/dewi/cmt-permak/{id}. Endpoint UPDATE sama berbahayanya dgn CREATE.
    cost_per_pcs: Optional[float] = Field(default=None, ge=0)
    return_deadline: Optional[str] = None
    vendor_permak: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    photos: Optional[List[str]] = None


class StatusChange(BaseModel):
    status: str = Field(..., min_length=1)
    # `ge=0` menyamakan penolakan di level model dengan guard handler
    # ("qty_fixed/qty_scrap tidak boleh negatif"). 0 tetap sah (semua scrap / semua fixed).
    qty_fixed: Optional[int] = Field(default=None, ge=0)
    qty_scrap: Optional[int] = Field(default=None, ge=0)
    note: str = ""


# ─── Helpers ───────────────────────────────────────────────────────────────
async def _enrich_from_po_item(db, po_id: str, po_item_id: str) -> dict:
    """Ambil metadata SKU dari po_items + header PO untuk memperkaya dokumen permak."""
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan")
    item = await db.po_items.find_one({"id": po_item_id, "po_id": po_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Item PO tidak ditemukan pada PO ini")
    return {
        "po_number": po.get("po_number", ""),
        "sku": item.get("sku", ""),
        "product_name": item.get("product_name", ""),
        "size": item.get("size", ""),
        "color": item.get("color", ""),
        "serial_number": item.get("serial_number", ""),
    }


async def _permaked_qty_for_line(db, receipt_line_id: str, exclude_id: str = None) -> int:
    q = {"source_receipt_line_id": receipt_line_id}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    docs = await db.dewi_cmt_permak.find(q, {"_id": 0, "qty": 1}).to_list(None)
    return sum(_iv(d.get("qty")) for d in docs)


def _compute_h3_flag(doc: dict, grace_days: int) -> dict:
    """Tambah field turunan read-only: days_to_deadline, overdue, h3_flag.
    h3_flag=True bila belum selesai & sudah melewati return_deadline + grace (mis. H+3)."""
    rd = doc.get("return_deadline")
    out = {"days_to_deadline": None, "overdue": False, "h3_flag": False}
    if rd and doc.get("status") not in TERMINAL:
        try:
            d = datetime.strptime(str(rd)[:10], "%Y-%m-%d").date()
            today = _now().date()
            delta = (d - today).days
            out["days_to_deadline"] = delta
            out["overdue"] = delta < 0
            out["h3_flag"] = (today - d).days > grace_days
        except (ValueError, TypeError) as e:
            # 2026-08-07 — DULU `pass` tanpa jejak. Akibatnya PERMAK yang tanggal
            # batas kembalinya rusak TIDAK PERNAH ditandai `overdue`/`h3_flag`,
            # sehingga barang yang sudah lewat H+3 di vendor tampak "masih aman"
            # dan tidak pernah masuk daftar kejar. Sekarang dicatat + ditandai.
            out["deadline_invalid"] = True
            logger.warning(
                "[permak] `return_deadline` permak %s tidak bisa dibaca (%r) — permak ini "
                "TIDAK ikut ditandai terlambat/H+3, jadi bisa luput dari daftar kejar. "
                "Perbaiki tanggalnya: %s", doc.get("id"), rd, e)
    return out


async def _enrich(db, doc: dict) -> dict:
    """Tambah field turunan read-only (h3_flag/overdue) berdasar grace config."""
    try:
        cfg = await db.dewi_system_config.find_one(
            {"key": "maklon_permak_return_grace_days"}, {"_id": 0, "value": 1})
        grace = int(cfg["value"]) if cfg and cfg.get("value") is not None else 3
    except Exception:
        # F13 — konfigurasi tenggang (grace) menentukan kapan permak dianggap
        # OVERDUE. Diam-diam memakai 3 hari berarti layar bisa menuduh/mengampuni
        # vendor dengan aturan yang bukan pilihan owner. Non-blocking, tapi
        # dicatat supaya salah-tuduh punya jejak.
        logger.warning(
            "[cmt-permak] config 'maklon_permak_return_grace_days' tidak terbaca — "
            "memakai tenggang cadangan 3 hari untuk doc=%s", doc.get("id"),
            exc_info=True)
        grace = 3
    doc.update(_compute_h3_flag(doc, grace))
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 — PIPELINE REWORK TERTUTUP (perbaikan cacat PMK-2 & PMK-3)
# ─────────────────────────────────────────────────────────────────────────────
# CACAT LAMA (terbukti oleh scripts/audit_e2e_produksi_maklon_cmt.py):
#   • Permak tidak punya `vendor_id` → tidak bisa ditampilkan/di-scope ke vendor CMT,
#     jadi "retur ke CMT" tidak pernah memicu pekerjaan apa pun di sisi vendor.
#   • `status=selesai_berhasil` HANYA menulis dokumen permak: stok FG tidak
#     bertambah, qty diterima PO tidak naik, reject tidak berkurang.
# PERBAIKAN:
#   • Permak menyimpan vendor_id/vendor_name (dari penerimaan atau PO).
#   • `retur_ke_cmt` membuat SURAT JALAN REWORK (`vendor_shipments`,
#     shipment_type='REWORK', parent_shipment_id = SJ asal) sehingga barang muncul
#     di Portal Vendor → vendor inspeksi → JOB ANAK otomatis (mekanisme yang sudah
#     terbukti dipakai ADDITIONAL/REPLACEMENT) → vendor kerjakan → deklarasi kirim
#     balik → penerimaan CMT baru menambah qty diterima. Pipeline yang BENAR.
#   • `permak_sendiri` selesai → karantina dilepas ke gudang FG (stok +) dan buku
#     kuantitas job item diperbarui (accepted +, rework_open −).
async def _resolve_vendor_for_permak(db, po_id: str, receipt_id: str | None) -> dict:
    """vendor CMT pemilik barang reject: dari penerimaan → PO → SJ material."""
    if receipt_id:
        r = await db.cmt_receipts.find_one({"id": receipt_id},
                                           {"_id": 0, "cmt_vendor_id": 1, "cmt_name": 1})
        if r and r.get("cmt_vendor_id"):
            return {"vendor_id": r["cmt_vendor_id"], "vendor_name": r.get("cmt_name", "")}
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0, "vendor_id": 1, "vendor_name": 1})
    if po and po.get("vendor_id"):
        return {"vendor_id": po["vendor_id"], "vendor_name": po.get("vendor_name", "")}
    return {"vendor_id": "", "vendor_name": ""}


async def _create_rework_shipment(db, permak: dict, actor: dict) -> dict:
    """Kirim barang reject BALIK ke vendor CMT lewat pipeline surat jalan resmi."""
    from core.helpers import new_id, now
    from utils.counters import gen_prefixed_number as _gen

    vendor_id = permak.get("vendor_id")
    if not vendor_id:
        return {"ok": False, "error": "vendor CMT tidak diketahui — SJ rework tidak dibuat"}

    # SJ asal (untuk parent_shipment_id → job anak otomatis)
    parent_ship_id = None
    ji_rows = await db.production_job_items.find(
        {"po_item_id": permak.get("po_item_id")}, {"_id": 0}).sort("created_at", -1).to_list(5)
    if ji_rows:
        job = await db.production_jobs.find_one({"id": ji_rows[0].get("job_id")},
                                                {"_id": 0, "vendor_shipment_id": 1})
        parent_ship_id = (job or {}).get("vendor_shipment_id")

    sj_no = await _gen(db, "vendor_shipments", "shipment_number", "SJ-RWK-", 5)
    ship_id = new_id()
    ship = {
        "id": ship_id, "shipment_number": sj_no,
        "delivery_note_number": "",
        "vendor_id": vendor_id, "vendor_name": permak.get("vendor_name", ""),
        "po_id": permak.get("po_id"), "po_number": permak.get("po_number", ""),
        "shipment_date": now(),
        "shipment_type": "REWORK",
        "parent_shipment_id": parent_ship_id,
        "business_type": "maklon",
        "status": "Sent", "inspection_status": "Pending",
        "rework_permak_id": permak.get("id"),
        "rework_permak_number": permak.get("permak_number"),
        "notes": f"Rework/permak {permak.get('permak_number')} — {permak.get('reason', '')}",
        "created_by": actor.get("name", ""), "created_at": now(), "updated_at": now(),
    }
    await db.vendor_shipments.insert_one(ship)
    await db.vendor_shipment_items.insert_one({
        "id": new_id(), "shipment_id": ship_id, "shipment_number": sj_no,
        "po_id": permak.get("po_id"), "po_number": permak.get("po_number", ""),
        "po_item_id": permak.get("po_item_id"),
        "source_po_item_id": permak.get("po_item_id"),
        "product_name": permak.get("product_name", ""),
        "serial_number": permak.get("serial_number", ""),
        "sku": permak.get("sku", ""), "size": permak.get("size", ""),
        "color": permak.get("color", ""),
        "qty_sent": _iv(permak.get("qty")),
        "is_rework": True, "rework_permak_id": permak.get("id"),
        "created_at": now(),
    })

    # barang fisik keluar dari karantina DA → kembali ke vendor
    quarantine_note = None
    if permak.get("source_receipt_line_id"):
        try:
            from core import quarantine as qmod
            q_item = await db.wh_quarantine_items.find_one(
                {"source.receipt_line_id": permak["source_receipt_line_id"], "status": "open"},
                {"_id": 0})
            if q_item:
                await qmod.quarantine_out(
                    db, item=q_item, action="return_supplier",
                    qty=min(_iv(permak.get("qty")), _iv(q_item.get("remaining_qty"))),
                    actor=actor,
                    notes=f"Retur rework ke CMT via {sj_no}")
                quarantine_note = "keluar karantina → dikirim balik ke vendor"
        except Exception as e:  # noqa: BLE001
            logger.exception("quarantine return_supplier gagal untuk permak %s", permak.get("id"))
            quarantine_note = f"karantina gagal: {e}"

    await db.dewi_cmt_permak.update_one(
        {"id": permak["id"]},
        {"$set": {"rework_shipment_id": ship_id, "rework_shipment_number": sj_no,
                  "status": "in_progress", "updated_at": _now()}})
    return {"ok": True, "shipment_id": ship_id, "shipment_number": sj_no,
            "parent_shipment_id": parent_ship_id, "quarantine": quarantine_note}


# ─── Endpoints ───────────────────────────────────────────────────────────────
@router.get("")
async def list_permak(
    request: Request,
    po_id: Optional[str] = None,
    po_item_id: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    user = await require_auth(request)
    _require_admin_or_vendor(user)
    db = get_db()
    query: dict = {}
    # Vendor CMT hanya melihat rework/permak yang menjadi tanggung jawabnya.
    if is_vendor(user):
        vid = vendor_identity(user)
        if not vid:
            raise HTTPException(403, "Akun vendor belum terhubung ke master vendor CMT.")
        query["vendor_id"] = vid
    if po_id:
        query["po_id"] = po_id
    if po_item_id:
        query["po_item_id"] = po_item_id
    if status:
        query["status"] = status
    if source:
        query["source"] = source
    if q:
        query["$or"] = [
            {"permak_number": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
            {"product_name": {"$regex": q, "$options": "i"}},
            {"po_number": {"$regex": q, "$options": "i"}},
        ]
    total = await db.dewi_cmt_permak.count_documents(query)
    skip = (page - 1) * limit
    docs = await db.dewi_cmt_permak.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for d in docs:
        await _enrich(db, d)
    return {
        "items": serialize_doc(docs),
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
        },
    }


@router.get("/summary")
async def permak_summary(request: Request, po_id: Optional[str] = None):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    match: dict = {}
    if po_id:
        match["po_id"] = po_id
    docs = await db.dewi_cmt_permak.find(match, {"_id": 0}).to_list(None)
    _cfg = await db.dewi_system_config.find_one(
        {"key": "maklon_permak_return_grace_days"}, {"_id": 0, "value": 1})
    grace = int(_cfg["value"]) if _cfg and _cfg.get("value") is not None else 3
    summary = {
        "total_records": len(docs),
        "open": 0, "in_progress": 0, "selesai_berhasil": 0, "gagal_buang": 0,
        "qty_open": 0, "qty_in_progress": 0, "qty_fixed": 0, "qty_scrap": 0,
        "qty_total": 0,
        "total_cost": 0.0,
        "permak_sendiri": 0, "retur_ke_cmt": 0,
        "h3_alert": 0,
        "distinct_pos": len({d.get("po_id") for d in docs if d.get("po_id")}),
    }
    for d in docs:
        st = d.get("status", "open")
        qty = _iv(d.get("qty"))
        summary["qty_total"] += qty
        summary["total_cost"] += float(d.get("total_cost") or 0)
        pt = d.get("permak_type", "permak_sendiri")
        if pt in summary:
            summary[pt] += 1
        if st in summary:
            summary[st] += 1
        if st == "open":
            summary["qty_open"] += qty
        elif st == "in_progress":
            summary["qty_in_progress"] += qty
        elif st == SUCCESS:
            summary["qty_fixed"] += _iv(d.get("qty_fixed"))
            summary["qty_scrap"] += _iv(d.get("qty_scrap"))
        elif st == SCRAP:
            summary["qty_scrap"] += qty
        # H+N alert (belum selesai & lewat return_deadline + grace)
        flags = _compute_h3_flag(d, grace)
        if flags["h3_flag"]:
            summary["h3_alert"] += 1
    summary["total_cost"] = round(summary["total_cost"], 2)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 2026-06 — PERMAK "REJECT QC" WAJIB TERTAUT BARIS PENERIMAAN (cacat wiring)
# ─────────────────────────────────────────────────────────────────────────────
# Layar "Buat Permak Baru" hanya menanyakan PO + item + qty, jadi dokumennya
# tersimpan TANPA `source_receipt_line_id`. Akibatnya begitu permak dinyatakan
# BERHASIL, `core.production_qty_ledger.apply_rework_outcome()`:
#   · TIDAK menaikkan `cmt_receipt_lines.qty_reworked_ok` ⇒ kapasitas kirim ke
#     buyer tidak pernah bertambah (barang yang sudah bagus mustahil dikirim);
#   · TIDAK menemukan item KARANTINA-nya ⇒ stok FG tidak bertambah
#     (`stock_released: 0`), jadi pagar stok menolak pengiriman berikutnya.
# Dibuktikan `scripts/_repro_5bug_produksi_maklon.py` (BUG 1), dijaga INV-F27.
#
# Penautan sekarang dikerjakan BACKEND: qty permak dipetakan ke baris penerimaan
# yang masih punya sisa reject, FIFO, boleh melintasi beberapa baris. SATU baris
# penerimaan = SATU dokumen permak (dokumen kembar), supaya SEMUA pembaca lama
# (`_permaked_qty_for_line`, antrean reject, karantina, packing) tetap benar
# tanpa perlu mengerti soal alokasi.
async def _reject_allocations(db, po_item_id: str, qty: int) -> tuple:
    """(alokasi, total sisa reject yang belum dipermak) untuk satu po_item.

    Hanya baris dari penerimaan yang SUDAH selesai QC yang dihitung — gerbang
    yang sama dengan `/from-receipt-line`.
    """
    from core.cmt_receipt_status import is_done as _receipt_done
    lines = await db.cmt_receipt_lines.find(
        {"po_item_id": po_item_id, "reject_qty": {"$gt": 0}}, {"_id": 0}
    ).sort("created_at", 1).to_list(None)
    rec_ids = list({ln.get("receipt_id") for ln in lines if ln.get("receipt_id")})
    receipts = await db.cmt_receipts.find(
        {"id": {"$in": rec_ids}}, {"_id": 0, "id": 1, "status": 1}
    ).to_list(None) if rec_ids else []
    done = {r["id"] for r in receipts if _receipt_done(r.get("status"))}
    allocations, left, sisa = [], _iv(qty), 0
    for ln in lines:
        if ln.get("receipt_id") not in done:
            continue
        remaining = _iv(ln.get("reject_qty")) - await _permaked_qty_for_line(db, ln["id"])
        if remaining <= 0:
            continue
        sisa += remaining
        if left <= 0:
            continue
        take = min(left, remaining)
        allocations.append({"receipt_id": ln.get("receipt_id"),
                            "receipt_line_id": ln["id"], "qty": take})
        left -= take
    return allocations, sisa


@router.post("")
async def create_permak(data: PermakCreate, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    if data.source not in ("reject", "good"):
        raise HTTPException(422, "source harus 'reject' atau 'good'")
    if data.permak_type not in PERMAK_TYPES:
        raise HTTPException(422, f"permak_type harus salah satu {PERMAK_TYPES}")
    meta = await _enrich_from_po_item(db, data.po_id, data.po_item_id)

    # ── Tautkan ke baris penerimaan (sumber reject) ──────────────────────────
    allocations = []
    if data.source_receipt_line_id:
        line = await db.cmt_receipt_lines.find_one(
            {"id": data.source_receipt_line_id}, {"_id": 0}
        )
        if line:
            reject_qty = _iv(line.get("reject_qty"))
            already = await _permaked_qty_for_line(db, data.source_receipt_line_id)
            if already + data.qty > reject_qty:
                raise HTTPException(
                    400,
                    f"Qty permak melebihi sisa reject. reject={reject_qty}, sudah dipermak={already}, diminta={data.qty}",
                )
        allocations = [{"receipt_id": data.source_receipt_id or (line or {}).get("receipt_id"),
                        "receipt_line_id": data.source_receipt_line_id, "qty": data.qty}]
    elif data.source == "reject":
        allocations, sisa = await _reject_allocations(db, data.po_item_id, data.qty)
        if sum(a["qty"] for a in allocations) < data.qty:
            raise HTTPException(
                400,
                f"Qty permak {data.qty} pcs melebihi sisa reject yang belum dipermak "
                f"({sisa} pcs) untuk item ini. Turunkan qty, atau catat reject-nya "
                f"dulu di 'Terima FG dari CMT' dan selesaikan QC-nya — tanpa baris "
                f"penerimaan, hasil permak tidak bisa menambah stok FG maupun sisa "
                f"kirim ke buyer.")
    if not allocations:
        # sumber 'good' (barang bagus dipermak): tidak ada baris reject yang ditaut
        allocations = [{"receipt_id": data.source_receipt_id,
                        "receipt_line_id": data.source_receipt_line_id,
                        "qty": data.qty}]

    docs, reworks = [], []
    # SESI #27 — satu pengajuan bisa terpecah menjadi BEBERAPA dokumen permak (satu
    # per baris reject). Satu nomor ketikan mustahil dipakai untuk semuanya, jadi
    # mode MANUAL + pecahan > 1 DITOLAK dengan jalan keluarnya disebut — daripada
    # diam-diam memberi nomor ketikan ke dokumen pertama dan nomor otomatis ke
    # sisanya (arsip jadi campur dua kebijakan tanpa ada yang tahu).
    nomor_diminta = (data.permak_number or "").strip()
    if nomor_diminta and len(allocations) > 1:
        raise HTTPException(400, (
            f"Pengajuan ini akan melahirkan {len(allocations)} dokumen permak (satu per "
            "baris reject), sehingga satu nomor ketikan tidak bisa dipakai untuk "
            "semuanya. Pecah menjadi beberapa pengajuan, atau ubah penomoran Permak ke "
            "OTOMATIS di Administrasi Sistem → Penomoran Dokumen."))
    for alloc in allocations:
        now = _now()
        vendor = await _resolve_vendor_for_permak(db, data.po_id, alloc.get("receipt_id"))
        qty_alloc = _iv(alloc.get("qty"))
        doc = {
            "id": _id(),
            "permak_number": await _next_permak_no(db, nomor_diminta),
            "po_id": data.po_id,
            "po_number": meta["po_number"],
            "po_item_id": data.po_item_id,
            "sku": meta["sku"],
            "product_name": meta["product_name"],
            "size": meta["size"],
            "color": meta["color"],
            "serial_number": meta["serial_number"],
            # FASE 2: tautan vendor CMT — tanpa ini rework tidak bisa dilihat/dikerjakan vendor
            "vendor_id": vendor["vendor_id"],
            "vendor_name": vendor["vendor_name"],
            "source": data.source,
            "permak_type": data.permak_type,
            "problem_type": data.problem_type,
            "cost_per_pcs": float(data.cost_per_pcs or 0),
            "total_cost": round(float(data.cost_per_pcs or 0) * qty_alloc, 2),
            "return_deadline": data.return_deadline,
            "source_receipt_id": alloc.get("receipt_id"),
            "source_receipt_line_id": alloc.get("receipt_line_id"),
            # jejak: penautan otomatis oleh server (bukan pilihan layar)
            "source_link_auto": bool(alloc.get("receipt_line_id")) and not data.source_receipt_line_id,
            "qty": qty_alloc,
            "qty_fixed": 0,
            "qty_scrap": 0,
            "vendor_permak": data.vendor_permak,
            "reason": data.reason,
            "notes": data.notes,
            "photos": data.photos or [],
            "status": "open",
            "status_history": [{
                "status": "open", "at": now.isoformat(),
                "by": user.get("name", user["id"]), "note": "Permak dibuat",
            }],
            "created_at": now,
            "created_by": user.get("name", user["id"]),
            "updated_at": now,
            "updated_by": user.get("name", user["id"]),
        }
        await db.dewi_cmt_permak.insert_one(doc)

        # ── FASE 2: retur ke CMT → langsung buat SJ REWORK supaya vendor bisa mengerjakan ──
        if data.permak_type == "retur_ke_cmt":
            rework = await _create_rework_shipment(db, doc, user)
            reworks.append(rework)
            if rework.get("ok"):
                doc["rework_shipment_id"] = rework["shipment_id"]
                doc["rework_shipment_number"] = rework["shipment_number"]
                doc["status"] = "in_progress"
        docs.append(doc)

    primary = docs[0]
    await log_activity(user["id"], user.get("name", ""), "create", "cmt-permak",
                       f"Permak {primary['permak_number']} qty {data.qty} ({meta['sku']})"
                       + (f" — dipecah {len(docs)} dokumen sesuai baris penerimaan"
                          if len(docs) > 1 else ""))
    out = serialize_doc({k: v for k, v in primary.items() if k != "_id"})
    out["allocations"] = allocations
    if len(docs) > 1:
        out["siblings"] = serialize_doc([{k: v for k, v in d.items() if k != "_id"}
                                         for d in docs[1:]])
        out["split_note"] = (
            f"Qty {data.qty} pcs berasal dari {len(docs)} baris penerimaan, jadi "
            f"dibuat {len(docs)} dokumen permak agar stok & sisa kirim tetap "
            f"terlacak per penerimaan.")
    if reworks:
        out["rework"] = reworks[0]
        if len(reworks) > 1:
            out["reworks"] = reworks
    return out


@router.post("/from-receipt-line")
async def create_from_receipt_line(data: FromReceiptLine, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    line = await db.cmt_receipt_lines.find_one({"id": data.receipt_line_id}, {"_id": 0})
    if not line:
        raise HTTPException(404, "Receipt line tidak ditemukan")
    receipt = await db.cmt_receipts.find_one({"id": line.get("receipt_id")}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Receipt induk tidak ditemukan")
    # FASE 4: gerbang status memakai SSOT `core/cmt_receipt_status` (menerima
    # `completed_qc` BARU maupun `Approved` historis). Dulu hard-coded "Approved"
    # sehingga setelah status disederhanakan, membuat permak selalu 400.
    from core.cmt_receipt_status import is_done as _receipt_done
    if not _receipt_done(receipt.get("status")):
        raise HTTPException(
            400, "Hanya baris dari penerimaan yang sudah SELESAI QC bisa dipermak/di-rework")

    reject_qty = _iv(line.get("reject_qty"))
    if reject_qty <= 0:
        raise HTTPException(400, "Line ini tidak punya qty reject untuk dipermak")
    already = await _permaked_qty_for_line(db, data.receipt_line_id)
    remaining = reject_qty - already
    if remaining <= 0:
        raise HTTPException(400, f"Semua qty reject ({reject_qty}) sudah dikirim ke permak")

    qty = data.qty if data.qty is not None else remaining
    if qty <= 0:
        raise HTTPException(422, "qty harus > 0")
    if qty > remaining:
        raise HTTPException(400, f"Qty melebihi sisa reject ({remaining})")

    po_id = receipt.get("po_id", "")
    po_item_id = line.get("po_item_id", "")
    if not po_id or not po_item_id:
        raise HTTPException(400, "Receipt line tidak punya po_id/po_item_id — tidak bisa dilacak")

    payload = PermakCreate(
        po_id=po_id,
        po_item_id=po_item_id,
        qty=qty,
        source="reject",
        permak_type=data.permak_type,
        problem_type=data.problem_type,
        cost_per_pcs=data.cost_per_pcs,
        return_deadline=data.return_deadline,
        source_receipt_id=receipt.get("id"),
        source_receipt_line_id=data.receipt_line_id,
        vendor_permak=data.vendor_permak,
        reason=data.reason or line.get("reject_reason", ""),
        notes=data.notes,
        photos=data.photos or line.get("photos", []) or [],
        permak_number=(data.permak_number or ""),
    )
    return await create_permak(payload, request)


@router.get("/{permak_id}")
async def get_permak(permak_id: str, request: Request):
    user = await require_auth(request)
    _require_admin_or_vendor(user)
    db = get_db()
    doc = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Permak tidak ditemukan")
    if is_vendor(user) and doc.get("vendor_id") != vendor_identity(user):
        raise HTTPException(403, "Rework ini bukan milik vendor Anda")
    await _enrich(db, doc)
    return serialize_doc(doc)


@router.put("/{permak_id}")
async def update_permak(permak_id: str, data: PermakUpdate, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    doc = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Permak tidak ditemukan")
    if doc.get("status") in TERMINAL:
        raise HTTPException(400, "Permak sudah selesai/dibuang — tidak bisa diubah")

    updates = {}
    if data.qty is not None:
        # jaga guard sisa reject bila terhubung ke line
        if doc.get("source_receipt_line_id"):
            line = await db.cmt_receipt_lines.find_one({"id": doc["source_receipt_line_id"]}, {"_id": 0})
            if line:
                reject_qty = _iv(line.get("reject_qty"))
                already = await _permaked_qty_for_line(db, doc["source_receipt_line_id"], exclude_id=permak_id)
                if already + data.qty > reject_qty:
                    raise HTTPException(400, f"Qty melebihi sisa reject ({reject_qty - already})")
        updates["qty"] = data.qty
    if data.permak_type is not None:
        if data.permak_type not in PERMAK_TYPES:
            raise HTTPException(422, f"permak_type harus salah satu {PERMAK_TYPES}")
        updates["permak_type"] = data.permak_type
    if data.problem_type is not None:
        updates["problem_type"] = data.problem_type
    if data.cost_per_pcs is not None:
        updates["cost_per_pcs"] = float(data.cost_per_pcs)
    if data.return_deadline is not None:
        updates["return_deadline"] = data.return_deadline
    if data.vendor_permak is not None:
        updates["vendor_permak"] = data.vendor_permak
    if data.reason is not None:
        updates["reason"] = data.reason
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.photos is not None:
        updates["photos"] = data.photos
    if not updates:
        return serialize_doc(doc)
    # Recompute total_cost bila qty / cost_per_pcs berubah
    new_qty = updates.get("qty", _iv(doc.get("qty")))
    new_cost = updates.get("cost_per_pcs", float(doc.get("cost_per_pcs") or 0))
    updates["total_cost"] = round(float(new_cost) * int(new_qty), 2)
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("name", user["id"])
    await db.dewi_cmt_permak.update_one({"id": permak_id}, {"$set": updates})
    out = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    await _enrich(db, out)
    return serialize_doc(out)


@router.post("/{permak_id}/status")
async def change_status(permak_id: str, data: StatusChange, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    doc = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Permak tidak ditemukan")

    cur = doc.get("status", "open")
    new = data.status
    if new not in ALL_STATUS:
        raise HTTPException(422, f"Status tidak valid. Pilihan: {', '.join(ALL_STATUS)}")
    if new == cur:
        raise HTTPException(400, f"Status sudah '{cur}'")
    if new not in TRANSITIONS.get(cur, set()):
        raise HTTPException(400, f"Transisi '{cur}' → '{new}' tidak diizinkan")

    qty = _iv(doc.get("qty"))
    updates = {"status": new, "updated_at": _now(), "updated_by": user.get("name", user["id"])}

    if new == SUCCESS:
        qf = data.qty_fixed if data.qty_fixed is not None else (qty - _iv(data.qty_scrap))
        qs = data.qty_scrap if data.qty_scrap is not None else (qty - qf)
        qf, qs = _iv(qf), _iv(qs)
        if qf < 0 or qs < 0:
            raise HTTPException(422, "qty_fixed/qty_scrap tidak boleh negatif")
        if qf + qs != qty:
            raise HTTPException(400, f"qty_fixed + qty_scrap harus = qty ({qty}). Diterima {qf}+{qs}")
        updates["qty_fixed"] = qf
        updates["qty_scrap"] = qs
    elif new == SCRAP:
        updates["qty_fixed"] = 0
        updates["qty_scrap"] = qty

    hist = doc.get("status_history", [])
    hist.append({
        "status": new, "at": _now().isoformat(),
        "by": user.get("name", user["id"]),
        "note": data.note or f"Status → {new}",
    })
    updates["status_history"] = hist

    await db.dewi_cmt_permak.update_one({"id": permak_id}, {"$set": updates})

    # ─── FASE 2 — EFEK NYATA (perbaikan cacat PMK-3) ─────────────────────────
    # Dulu: perubahan status HANYA menulis dokumen permak. Stok tidak berubah,
    # qty diterima PO tidak naik, reject tidak berkurang ⇒ lingkaran
    # "100 produced → 10 reject → diperbaiki → 100 diterima" tidak pernah tertutup.
    effect = None
    if new in TERMINAL:
        try:
            from core import production_qty_ledger as qty_ledger
            fresh = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
            effect = await qty_ledger.apply_rework_outcome(
                db, fresh,
                qty_fixed=_iv(updates.get("qty_fixed")),
                qty_scrap=_iv(updates.get("qty_scrap")),
                actor=user)
        except Exception as e:  # noqa: BLE001
            logger.exception("apply_rework_outcome gagal untuk permak %s", permak_id)
            effect = {"ok": False, "error": str(e)}

    await log_activity(user["id"], user.get("name", ""), "status", "cmt-permak",
                       f"Permak {doc.get('permak_number')} → {new}")
    out = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    res = serialize_doc(out)
    if effect is not None:
        res["effect"] = serialize_doc(effect)
    return res


@router.delete("/{permak_id}")
async def delete_permak(permak_id: str, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    doc = await db.dewi_cmt_permak.find_one({"id": permak_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Permak tidak ditemukan")
    if doc.get("status") != "open":
        raise HTTPException(400, "Hanya permak berstatus 'open' yang bisa dihapus")
    await db.dewi_cmt_permak.delete_one({"id": permak_id})
    await log_activity(user["id"], user.get("name", ""), "delete", "cmt-permak",
                       f"Permak {doc.get('permak_number')} dihapus")
    return {"ok": True, "deleted": permak_id}
