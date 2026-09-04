"""
Return & Refund — Portal Gudang (Blueprint §3.7)

Dua tipe return:
  Tipe 1 — paket kembali dari ekspedisi  (expedition_return)
  Tipe 2 — customer request refund       (customer_refund)

Workflow:
  Pending → Received (unboxing) → Inspected (cek kondisi & penyebab) → Resolved

Collections: wh_returns

Endpoints:
  GET    /api/wh/returns              — list (filter: type, status, search)
  GET    /api/wh/returns/summary      — stats dashboard
  POST   /api/wh/returns              — buat record return baru
  GET    /api/wh/returns/{id}         — detail
  PUT    /api/wh/returns/{id}         — update info dasar
  POST   /api/wh/returns/{id}/receive — terima fisik (unboxing notes, foto notes)
  POST   /api/wh/returns/{id}/inspect — hasil inspeksi (kondisi, penyebab, rekomendasi)
  POST   /api/wh/returns/{id}/resolve — resolusi akhir (restock/reshipment/appeal/dispose)
  DELETE /api/wh/returns/{id}         — hapus (hanya Pending)
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import uuid
import re
from datetime import datetime, timezone

from database import get_db
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc
from core import returns_bridge as _rb
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wh", tags=["wh-returns"])

# ── helpers ──────────────────────────────────────────────────────────────────
def _id():  return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()

RETURN_TYPES   = ["expedition_return", "customer_refund"]
CONDITIONS     = ["Baik", "Rusak", "Rusak Ringan", "Rusak Berat", "Tidak Layak Jual"]
CAUSES         = ["Kesalahan Gudang", "Kesalahan Customer", "Kesalahan Ekspedisi", "Lainnya"]
# W4 (sesi #29) — "Karantina (Rusak)" DITAMBAH sebagai aksi resmi: barang rusak
# tetap harus tercatat fisiknya, tetapi TIDAK boleh menambah stok jual.
ACTIONS        = ["Restock ke Gudang", "Karantina (Rusak)", "Reshipment",
                  "Appeal Platform", "Dibuang / Dispose", "Donasi"]
STATUS_FLOW    = ["Pending", "Received", "Inspected", "Resolved", "Cancelled"]

CHANNELS = ["Shopee", "Tokopedia", "TikTok Shop", "Lazada", "Instagram", "WhatsApp", "Lainnya"]


async def _next_code(db, requested: str = "") -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    """SESI #19 — SATU PINTU kebijakan penomoran (Otomatis/Manual)."""
    from core.doc_number_policy import issue_number
    return await issue_number(db, "wh_returns.return_code", requested=requested)


# ═══════════════════════════════════════════════════════════════
# LIST & SUMMARY
# ═══════════════════════════════════════════════════════════════

@router.get("/returns/summary")
async def get_summary(request: Request):
    await require_auth(request)
    db = get_db()

    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    by_status = {r["_id"]: r["count"] for r in await db.wh_returns.aggregate(pipeline).to_list(500)}

    by_type = [{"$group": {"_id": "$return_type", "count": {"$sum": 1}}}]
    type_counts = {r["_id"]: r["count"] for r in await db.wh_returns.aggregate(by_type).to_list(500)}

    total = await db.wh_returns.count_documents({})
    pending = by_status.get("Pending", 0)
    received = by_status.get("Received", 0)
    inspected = by_status.get("Inspected", 0)
    resolved = by_status.get("Resolved", 0)

    # Items needing action today: Pending + Received + Inspected
    action_needed = pending + received + inspected

    return {
        "total": total,
        "pending": pending,
        "received": received,
        "inspected": inspected,
        "resolved": resolved,
        "action_needed": action_needed,
        "expedition_returns": type_counts.get("expedition_return", 0),
        "customer_refunds": type_counts.get("customer_refund", 0),
    }


@router.get("/returns")
async def list_returns(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get("return_type"):
        query["return_type"] = sp["return_type"]
    if sp.get("status"):
        query["status"] = sp["status"]
    # W4 — filter asal & status tautan master (dipakai layar untuk memisahkan
    # retur dari Marketing dan menyorot yang belum tertaut master barang).
    if sp.get("source") == "marketing":
        query["source_marketing_return_id"] = {"$nin": [None, ""]}
    elif sp.get("source") == "manual":
        query["source_marketing_return_id"] = {"$in": [None, ""]}
    if sp.get("link_status"):
        if sp["link_status"] == "needs_link":
            query["link_status"] = {"$nin": [None, "", _rb.LINK_OK]}
        else:
            query["link_status"] = sp["link_status"]
    if sp.get("restocked") in ("1", "true", "yes"):
        query["restocked"] = True
    elif sp.get("restocked") in ("0", "false", "no"):
        query["restocked"] = {"$ne": True}
    if sp.get("search"):
        rx = re.compile(re.escape(sp["search"]), re.IGNORECASE)
        query["$or"] = [{"return_code": rx}, {"order_number": rx},
                         {"customer_name": rx}, {"resi_number": rx}]
    docs = await db.wh_returns.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(500)
    return serialize_doc(docs)


# ══════════════════════════════════════════════════════════════════════════════
# W4 (sesi #29) — JEMBATAN RETUR MARKETING → GUDANG
# Rute STATIS ini WAJIB berada SEBELUM `/returns/{return_id}` (FastAPI mencocokkan
# rute berurutan; kalau di bawah, 'marketing-gap' akan dibaca sebagai id retur).
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/returns/marketing-gap")
async def marketing_gap(request: Request):
    """Berapa retur pembeli di Marketing yang BELUM punya pekerjaan fisik di sini.

    Angka inilah yang dulu tidak pernah terlihat siapa pun: `marketing_returns`
    berisi 30 retur nyata sementara `wh_returns` 0 dokumen.
    """
    await require_auth(request)
    db = get_db()
    q = {"status": {"$nin": list(_rb.SKIP_STATUSES)}}
    total = await db.marketing_returns.count_documents(q)
    linked_ids = await db.wh_returns.distinct("source_marketing_return_id")
    linked_ids = [x for x in linked_ids if x]
    pending = await db.marketing_returns.count_documents(
        {**q, "id": {"$nin": linked_ids}})
    return {
        "marketing_returns_total": total,
        "already_bridged": len(linked_ids),
        "pending_bridge": pending,
        "wh_returns_total": await db.wh_returns.count_documents({}),
        "from_marketing": await db.wh_returns.count_documents(
            {"source_marketing_return_id": {"$nin": [None, ""]}}),
        "restocked": await db.wh_returns.count_documents({"restocked": True}),
        "needs_link": await db.wh_returns.count_documents(
            {"link_status": {"$nin": [None, "", _rb.LINK_OK]}}),
    }


@router.post("/returns/sync-marketing")
async def sync_from_marketing(request: Request):
    """Tarik retur pembeli dari Marketing ke antrean Retur Fisik (idempoten).

    Body opsional: {dry_run: bool, auto_restock: bool, condition: 'Baik'|'Rusak'}
    """
    user = await require_auth(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    res = await _rb.sync_all(
        db, actor=user,
        dry_run=bool(body.get("dry_run")),
        auto_restock=body.get("auto_restock", True) is not False,
        condition=body.get("condition"),
        limit=int(body.get("limit") or 500))
    return {"success": True, "data": res}


# ═══════════════════════════════════════════════════════════════
# CREATE & GET
# ═══════════════════════════════════════════════════════════════

@router.post("/returns")
async def create_return(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    rt = body.get("return_type", "expedition_return")
    if rt not in RETURN_TYPES:
        raise HTTPException(400, f"return_type harus salah satu dari: {RETURN_TYPES}")
    if not body.get("order_number") and not body.get("resi_number"):
        raise HTTPException(400, "order_number atau resi_number wajib diisi")

    code = await _next_code(db, (body.get("return_code") or "").strip())
    # ── W4 (sesi #29) — TAUTKAN KE MASTER BARANG SAAT DICATAT ────────────────
    # Retur yang dicatat manual gudang DULU hanya menyimpan `sku_code` sebagai
    # teks bebas, jadi restock-nya mustahil menemukan barangnya (dan itulah salah
    # satu sebab menu ini terasa "usang"). Sekarang layar mengirim `material_id`
    # dari master FG (gate INV-F14); `sku_code` tetap diterima sebagai cadangan
    # dan dicocokkan ke master — bukan ditebak.
    ident = {"material_id": None, "material_code": (body.get("sku_code") or "").strip(),
             "material_name": body.get("product_name", ""), "unit": "pcs",
             "link_status": _rb.LINK_NONE,
             "reason": "Barang retur belum dipilih dari master produk jadi."}
    mid = (body.get("material_id") or body.get("fg_material_id") or "").strip()
    mat = None
    if mid:
        mat = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0})
        if not mat:
            raise HTTPException(400, f"Master barang '{mid}' tidak ditemukan")
    elif ident["material_code"]:
        mat = await db.rahaza_materials.find_one(
            {"$or": [{"code": ident["material_code"]}, {"sku": ident["material_code"]}]},
            {"_id": 0})
    if mat:
        ident = {
            "material_id": mat["id"],
            "material_code": mat.get("code") or mat.get("sku") or "",
            "material_name": mat.get("name") or body.get("product_name", ""),
            "unit": mat.get("unit") or "pcs",
            "category_name": mat.get("category_name") or mat.get("category") or "",
            "color_name": mat.get("color_name") or mat.get("color") or "",
            "option_name": mat.get("option_name") or "",
            "variant_id": mat.get("variant_id"),
            "link_status": _rb.LINK_OK,
            "reason": "",
        }
    doc = {
        "id": _id(),
        "return_code": code,
        "return_type": rt,
        # Order info
        "order_number": body.get("order_number", ""),
        "resi_number": body.get("resi_number", ""),
        "channel": body.get("channel", ""),
        "customer_name": body.get("customer_name", ""),
        "customer_contact": body.get("customer_contact", ""),
        "sku_code": ident.get("material_code") or body.get("sku_code", ""),
        "product_name": ident.get("material_name") or body.get("product_name", ""),
        "qty": int(body.get("qty", 1)),
        "order_value": float(body.get("order_value", 0)),
        "initial_reason": body.get("initial_reason", ""),  # alasan awal customer/ekspedisi
        "notes": body.get("notes", ""),
        # Tautan master barang (kunci agar restock bisa tepat sasaran)
        "material_id": ident.get("material_id"),
        "fg_material_id": ident.get("material_id"),
        "variant_id": ident.get("variant_id"),
        "material_unit": ident.get("unit") or "pcs",
        "material_category": ident.get("category_name") or "",
        "material_color": ident.get("color_name") or "",
        "material_option": ident.get("option_name") or "",
        "link_status": ident.get("link_status"),
        "link_reason": ident.get("reason") or "",
        "link_source": "manual_master_pick" if ident.get("material_id") else "",
        "source": "manual",
        # Workflow
        "status": "Pending",
        "timeline": [
            {"status": "Pending", "at": _now(), "by": user["name"],
             "note": "Return dibuat"}
        ],
        # Receive step
        "received_at": "", "received_by": "",
        "unboxing_condition_notes": "",   # catatan kondisi saat unboxing
        "unboxing_photo_notes": "",       # kode foto/link bukti
        "package_condition": "",          # kondisi kemasan luar
        # Inspect step
        "inspected_at": "", "inspected_by": "",
        "item_condition": "",             # Baik / Rusak / Rusak Ringan / Rusak Berat / Tidak Layak Jual
        "return_cause": "",               # Kesalahan Gudang / Customer / Ekspedisi / Lainnya
        "cause_detail": "",
        "recommended_action": "",
        # Resolve step
        "resolved_at": "", "resolved_by": "",
        "action_taken": "",               # Restock / Karantina / Reshipment / Appeal / Dispose
        "action_notes": "",
        "reshipment_resi": "",            # jika reshipment
        "appeal_status": "",              # jika appeal: Pending / Success / Fail
        "restock_qty": 0,                 # jika restock
        "restocked": False,
        "restock_location_id": None, "restock_location_code": "",
        "restock_condition": "", "stock_effect": "",
        # Meta
        "created_by": user["name"], "created_at": _now(), "updated_at": _now()
    }
    await db.wh_returns.insert_one(doc)
    return JSONResponse(serialize_doc(doc), status_code=201)


@router.get("/returns/{return_id}")
async def get_return(return_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    return serialize_doc(doc)


@router.put("/returns/{return_id}")
async def update_return(return_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    upd = {k: v for k, v in body.items()
           if k not in ("_id", "id", "return_code", "status", "timeline", "created_at", "created_by")}
    upd["updated_at"] = _now()
    await db.wh_returns.update_one({"id": return_id}, {"$set": upd})
    result = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    return serialize_doc(result)


@router.delete("/returns/{return_id}")
async def delete_return(return_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc.get("status") != "Pending":
        raise HTTPException(400, "Hanya return berstatus Pending yang bisa dihapus")
    await db.wh_returns.delete_one({"id": return_id})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# WORKFLOW STEPS
# ═══════════════════════════════════════════════════════════════

@router.post("/returns/{return_id}/receive")
async def receive_return(return_id: str, request: Request):
    """
    Step 1: Tim Packing terima fisik barang.
    Input: unboxing_condition_notes, unboxing_photo_notes, package_condition
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc["status"] != "Pending":
        raise HTTPException(400, f"Status saat ini '{doc['status']}' — harus Pending untuk di-receive")

    timeline_entry = {
        "status": "Received", "at": _now(), "by": user["name"],
        "note": body.get("unboxing_condition_notes", "Barang diterima dari ekspedisi")
    }
    upd = {
        "status": "Received",
        "received_at": _now(), "received_by": user["name"],
        "unboxing_condition_notes": body.get("unboxing_condition_notes", ""),
        "unboxing_photo_notes": body.get("unboxing_photo_notes", ""),
        "package_condition": body.get("package_condition", ""),
        "updated_at": _now()
    }
    await db.wh_returns.update_one({"id": return_id}, {
        "$set": upd, "$push": {"timeline": timeline_entry}
    })
    result = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    return serialize_doc(result)


@router.post("/returns/{return_id}/inspect")
async def inspect_return(return_id: str, request: Request):
    """
    Step 2: Inspeksi kondisi item dan tentukan penyebab return.
    Input: item_condition, return_cause, cause_detail, recommended_action
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc["status"] != "Received":
        raise HTTPException(400, f"Status saat ini '{doc['status']}' — harus Received untuk di-inspect")

    condition = body.get("item_condition", "")
    cause = body.get("return_cause", "")
    recommended = body.get("recommended_action", "")

    # Auto-recommend action berdasarkan penyebab
    if not recommended:
        if cause == "Kesalahan Gudang":
            recommended = "Reshipment"
        elif cause == "Kesalahan Customer":
            recommended = "Appeal Platform"
        elif cause == "Kesalahan Ekspedisi":
            recommended = "Reshipment"
        else:
            recommended = "Restock ke Gudang"

    timeline_entry = {
        "status": "Inspected", "at": _now(), "by": user["name"],
        "note": f"Kondisi: {condition} | Penyebab: {cause} | Rekomendasi: {recommended}"
    }
    upd = {
        "status": "Inspected",
        "inspected_at": _now(), "inspected_by": user["name"],
        "item_condition": condition,
        "return_cause": cause,
        "cause_detail": body.get("cause_detail", ""),
        "recommended_action": recommended,
        "updated_at": _now()
    }
    await db.wh_returns.update_one({"id": return_id}, {
        "$set": upd, "$push": {"timeline": timeline_entry}
    })
    result = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    return serialize_doc(result)


@router.post("/returns/{return_id}/resolve")
async def resolve_return(return_id: str, request: Request):
    """
    Step 3: Eksekusi tindakan akhir.
    - Restock ke Gudang     → stok NYATA bertambah lewat `core/stock_service`
                              (satu pintu) + baris ledger; lokasi ditentukan
                              kondisi barang (Baik → ZNA-FG, Rusak → karantina)
    - Karantina (Rusak)     → stok masuk ZNA-KARANTINA (tidak boleh dijual)
    - Reshipment            → input resi baru
    - Appeal Platform       → update appeal_status
    - Dibuang / Dispose     → catat alasan
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc["status"] != "Inspected":
        raise HTTPException(400, f"Status saat ini '{doc['status']}' — harus Inspected untuk di-resolve")

    action = body.get("action_taken", doc.get("recommended_action", ""))
    if not action:
        raise HTTPException(400, "action_taken wajib diisi")

    restock_qty = int(body.get("restock_qty", doc.get("qty", 1)) or 0)

    # ── W4 (sesi #29) — RESTOCK LEWAT SATU PINTU STOK ─────────────────────────
    # SEBELUM ini blok inilah yang membuat pemilik merasa menu ini "usang":
    # ia menulis ke `rahaza_fg_inventory` (koleksi MATI, 0 dokumen) dan mencari
    # item lewat `sku_code` yang oleh jembatan lama selalu dikirim KOSONG ⇒ 100%
    # tidak pernah menemukan apa pun ⇒ menekan "Restock ke Gudang" TIDAK PERNAH
    # menambah stok dan tidak meninggalkan satu baris ledger pun.
    # Sekarang: `core/returns_bridge.restock` → `core/stock_service.add` (alias
    # skema & available_quantity terjaga, ledger tertulis, idempoten).
    restock_result = None
    restock_error = None
    if action in (_rb.ACTION_RESTOCK, _rb.ACTION_QUARANTINE):
        cond = _rb.normalize_condition(
            body.get("item_condition") or doc.get("item_condition"))
        if action == _rb.ACTION_QUARANTINE:
            cond = _rb.COND_DAMAGED
        try:
            restock_result = await _rb.restock(
                db, doc, condition=cond, qty=restock_qty, actor=user,
                note=body.get("action_notes", ""))
            doc = await db.wh_returns.find_one({"id": return_id})
        except _rb.ReturnBridgeError as e:
            # Barang fisik SUDAH di gudang: jangan batalkan resolusinya, tetapi
            # jangan pula berpura-pura stok bertambah. Alasannya disimpan supaya
            # bisa ditindak (petakan SKU / pilih produk) lalu di-restock ulang.
            restock_error = str(e)
            logger.error("[retur-gudang] restock %s gagal: %s", return_id, e)

    timeline_entry = {
        "status": "Resolved", "at": _now(), "by": user["name"],
        "note": f"Aksi: {action} | {body.get('action_notes', '')}"
    }
    upd = {
        "status": "Resolved",
        "resolved_at": _now(), "resolved_by": user["name"],
        "action_taken": action,
        "action_notes": body.get("action_notes", ""),
        "reshipment_resi": body.get("reshipment_resi", ""),
        "appeal_status": body.get("appeal_status", ""),
        "restock_qty": (restock_result or {}).get("qty", doc.get("restock_qty", 0))
        if restock_result else doc.get("restock_qty", 0),
        "restock_error": restock_error or "",
        "updated_at": _now()
    }
    await db.wh_returns.update_one({"id": return_id}, {
        "$set": upd, "$push": {"timeline": timeline_entry}
    })

    # RC-FLOW-UX-11a (opsi B): callback ke marketing_returns bila retur ini
    # berasal dari retur Toko (link `source_marketing_return_id`). Update
    # `wh_return_status='Resolved'` supaya UI Marketing tahu barang sudah masuk
    # kembali & tombol "Terbitkan Credit Note" bisa jalan aman.
    src_mkt_id = doc.get("source_marketing_return_id")
    if src_mkt_id:
        # 2026-08-07 — DULU `except Exception: pass` dengan komentar
        # "Non-blocking: jangan gagalkan resolve karena callback marketing gagal".
        # Keputusan non-blocking-nya BENAR (barang sudah fisik masuk gudang; membatalkan
        # resolve akan lebih merusak). Yang salah: kegagalannya tak berjejak. Padahal
        # justru sinkronisasi INILAH yang membuka tombol "Terbitkan Credit Note" di
        # Marketing. Kalau gagal diam-diam, retur pelanggan MENGGANTUNG: barang sudah
        # diterima, uang/credit note tidak pernah terbit, dan tidak ada satu pun layar
        # yang menunjukkan kenapa. Sekarang: dicatat ERROR + DITANDAI di dokumen retur
        # gudang supaya bisa ditindak (lihat `mkt_sync_ok`).
        try:
            _fresh = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
            # W4 — balikan LENGKAP (status, kondisi, qty, lokasi, efek stok) lewat
            # SSOT `returns_bridge._stamp_marketing` supaya layar Toko bisa
            # menjelaskan "masuk stok jual" vs "ditahan karantina".
            await _rb._stamp_marketing(db, src_mkt_id, _fresh or {})
            await db.marketing_returns.update_one(
                {"id": src_mkt_id},
                {"$set": {
                    "wh_return_status": "Resolved",
                    "wh_action_taken": action,
                    "wh_resolved_at": _now(),
                    "updated_at": _now(),
                }}
            )
            await db.wh_returns.update_one(
                {"id": return_id},
                {"$set": {"mkt_sync_ok": True, "mkt_sync_error": "", "mkt_sync_at": _now()}})
        except Exception as e:  # noqa: BLE001
            logger.error(
                "[retur-gudang] GAGAL menyinkronkan retur %s ke Marketing (%s) — tombol "
                "'Terbitkan Credit Note' TIDAK akan aktif dan retur pelanggan menggantung. "
                "Perlu tindakan manual: %s", return_id, src_mkt_id, e)
            await db.wh_returns.update_one(
                {"id": return_id},
                {"$set": {"mkt_sync_ok": False, "mkt_sync_error": str(e)[:300],
                          "mkt_sync_at": _now()}})

    result = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    out = serialize_doc(result)
    if isinstance(out, dict):
        out["restock_result"] = {
            "restocked": bool((restock_result or {}).get("restocked")),
            "already": bool((restock_result or {}).get("already")),
            "qty": (restock_result or {}).get("qty", 0),
            "location_code": ((restock_result or {}).get("location") or {}).get("code", ""),
            "stock_effect": (restock_result or {}).get("stock_effect", ""),
            "message": (restock_result or {}).get("message", "") or restock_error or "",
            "error": restock_error or "",
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# W4 (sesi #29) — AKSI CEPAT: satu klik "Terima & Restock"
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/returns/{return_id}/quick-restock")
async def quick_restock(return_id: str, request: Request):
    """Terima + inspeksi + selesaikan + tambah stok dalam SATU klik.

    Alur 3 langkah (Pending→Received→Inspected→Resolved) tetap ditulis di timeline
    supaya jejak auditnya sama lengkap, tetapi petugas gudang tidak perlu membuka
    tiga formulir untuk satu barang retur yang jelas kondisinya.

    Body: {condition: 'Baik'|'Rusak', qty: int, note: str}
      · Baik  → stok masuk ZNA-FG (ikut stok jual)
      · Rusak → stok masuk ZNA-KARANTINA (TIDAK dijual)
    """
    user = await require_auth(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    doc = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc.get("status") == "Cancelled":
        raise HTTPException(400, "Return sudah dibatalkan")
    if doc.get("restocked"):
        raise HTTPException(400, (
            f"Stok retur ini sudah ditambahkan sebelumnya "
            f"({doc.get('restock_qty', 0)} pcs → {doc.get('restock_location_code') or '-'}). "
            "Tidak digandakan."))
    if not (doc.get("material_id") or doc.get("fg_material_id")):
        raise HTTPException(400, (
            "Retur ini belum tertaut master barang jadi, jadi stok tidak bisa "
            "ditambah. " + (doc.get("link_reason") or
                            "Pilih produknya dari katalog di retur Marketing, atau "
                            "petakan SKU-nya lewat Jembatan SKU.")))

    try:
        res = await _rb.auto_process(
            db, return_id,
            condition=body.get("condition") or doc.get("item_condition") or _rb.COND_GOOD,
            qty=body.get("qty"),
            actor=user,
            note=body.get("note", ""))
    except _rb.ReturnBridgeError as e:
        raise HTTPException(400, str(e))

    return {
        "success": True,
        "restocked": bool(res.get("restocked")),
        "already": bool(res.get("already")),
        "qty": res.get("qty", 0),
        "condition": res.get("condition", ""),
        "location_code": (res.get("location") or {}).get("code", ""),
        "location_name": (res.get("location") or {}).get("name", ""),
        "stock_effect": res.get("stock_effect", ""),
        "onhand_after": res.get("onhand_after", 0),
        "message": res.get("message", ""),
        "data": serialize_doc(res.get("wh_return") or {}),
    }


@router.post("/returns/{return_id}/relink")
async def relink_return(return_id: str, request: Request):
    """Coba tautkan ulang retur ke master barang (setelah SKU dipetakan/produk dipilih).

    Dipakai untuk baris ber-`link_status` != 'linked': daripada memaksa petugas
    membuat retur baru, identitasnya dihitung ulang dari retur Marketing asalnya.
    """
    await require_auth(request)
    db = get_db()
    doc = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    src = doc.get("source_marketing_return_id")
    if not src:
        raise HTTPException(400, "Retur ini bukan dari Marketing — tidak ada sumber untuk ditautkan ulang")
    mkt = await db.marketing_returns.find_one({"id": src}, {"_id": 0})
    if not mkt:
        raise HTTPException(404, "Retur Marketing asal sudah tidak ada")
    ident = await _rb.resolve_identity(db, mkt)
    await db.wh_returns.update_one({"id": return_id}, {"$set": {
        "material_id": ident.get("material_id"),
        "fg_material_id": ident.get("material_id"),
        "variant_id": ident.get("variant_id"),
        "catalog_item_id": ident.get("catalog_item_id"),
        "sku_code": ident.get("material_code") or doc.get("sku_code", ""),
        "product_name": ident.get("material_name") or doc.get("product_name", ""),
        "material_unit": ident.get("unit") or "pcs",
        "material_category": ident.get("category_name") or "",
        "material_color": ident.get("color_name") or "",
        "material_option": ident.get("option_name") or "",
        "link_status": ident.get("link_status"),
        "link_reason": ident.get("reason") or "",
        "link_source": ident.get("source") or "",
        "link_candidates": ident.get("candidates") or [],
        "updated_at": _now(),
    }})
    fresh = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    return {"success": True, "link_status": ident.get("link_status"),
            "reason": ident.get("reason", ""), "data": serialize_doc(fresh)}


@router.post("/returns/{return_id}/cancel")
async def cancel_return(return_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = await db.wh_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan")
    if doc["status"] in ("Resolved", "Cancelled"):
        raise HTTPException(400, "Return sudah selesai atau dibatalkan")
    timeline_entry = {
        "status": "Cancelled", "at": _now(), "by": user["name"],
        "note": body.get("reason", "Dibatalkan")
    }
    await db.wh_returns.update_one({"id": return_id}, {
        "$set": {"status": "Cancelled", "updated_at": _now()},
        "$push": {"timeline": timeline_entry}
    })
    result = await db.wh_returns.find_one({"id": return_id}, {"_id": 0})
    return serialize_doc(result)
