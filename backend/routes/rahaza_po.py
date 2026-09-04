"""
PT Rahaza — Sprint 2.1: Purchase Order (PO) Module

Endpoints (prefix /api/rahaza):
  - GET  /purchase-orders?status=&vendor=&date_from=&date_to=
  - GET  /purchase-orders/{po_id}
  - POST /purchase-orders            → create draft PO
  - PUT  /purchase-orders/{po_id}    → update draft PO
  - POST /purchase-orders/{po_id}/submit     → submit for approval
  - POST /purchase-orders/{po_id}/approve    → approve PO (single-step default)
  - POST /purchase-orders/{po_id}/reject     → reject PO
  - POST /purchase-orders/{po_id}/cancel     → cancel PO (before received)
  - DELETE /purchase-orders/{po_id}          → delete draft PO

Status flow:
  draft → pending_approval → approved → (partially_received | fully_received)
  draft → rejected (bisa re-submit)
  any → cancelled

Sprint 2.1 Goal:
  - Receiving (GR) wajib referensi ke PO valid untuk 3-way matching
  - Approval workflow configurable (default: single-step manager approval)
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.counters import next_counter, gen_prefixed_number
from core.doc_number_policy import issue_number
from core import uom as _uom          # SSOT konversi satuan (INV-UOM-1/2)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain
import uuid
import logging
import math
from datetime import datetime, timezone, date
from typing import Optional
import re

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-po"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


PO_STATUSES = ["draft", "pending_approval", "approved", "partially_received", "fully_received", "rejected", "cancelled"]


async def _require_admin(request: Request):
    """Boleh MENGELOLA PO (buat / ubah / ajukan / batalkan / buat GR).

    BUG 2026-08-07: daftar peran di sini ditulis sendiri —
    ("superadmin", "admin", "owner", "manager") — dan dari empat itu HANYA
    `superadmin` yang benar-benar ada di aplikasi ini. Akibatnya `admin_pengadaan`,
    `manager_pengadaan`, `purchasing`, dan `admin_gudang` TIDAK BISA membuat atau
    mengajukan PO sama sekali, padahal pintu "Purchase Order" tampil di menu
    Portal Pengadaan mereka. Sekarang memakai gerbang SSOT `routes.shared`.
    """
    from routes.shared import PORTAL_ACCESS, require_perm
    return await require_perm(
        request, 'purchasing.manage', 'proc.po.manage', 'warehouse.manage',
        legacy_roles=('manager_pengadaan', 'admin_pengadaan', 'purchasing',
                      'admin_gudang', 'manager', 'dept_head',
                      'owner', 'admin', 'superadmin')
        + tuple(PORTAL_ACCESS.get('procurement', ())),
        message='Akses ditolak: butuh izin mengelola Purchase Order.')


# ═══════════════════════════════════════════════════════════════════════════
# PERSETUJUAN PO — memakai mesin YANG SAMA dengan Permintaan Pengadaan
# (core/pr_approval.py). Menutup lubang yang DIBUKTIKAN 2026-08-07:
#
#   · `_require_approver` lama memakai daftar peran karangan sendiri
#     ("superadmin","owner","manager","production_manager","warehouse_manager");
#     hanya `superadmin` yang benar-benar ada ⇒ `direktur@` (approver TERTINGGI),
#     `finance@`, dan `gudang@` semuanya 403. Persetujuan PO MATI di praktik.
#   · TIDAK ADA larangan menyetujui PO sendiri: `admin@garment.com` terbukti
#     bisa submit LALU approve PO yang SAMA — komitmen uang ke supplier
#     sendirian, tanpa mata kedua.
#   · Satu tahap saja, tidak mengikuti nilai, tanpa notifikasi, tanpa jejak
#     audit per tahap, dan PO tidak pernah muncul di kotak persetujuan.
#   · Penolakan boleh tanpa alasan (frontend malah mengisi otomatis
#     "Tidak ada alasan"), jadi pemohon tidak pernah tahu apa yang salah.
# ═══════════════════════════════════════════════════════════════════════════

async def _po_ctx(db, po_id: str, user: dict):
    """PO + rantai + hak persetujuan user atasnya (SSOT)."""
    from core.pr_approval import (
        PO_STAGE_LABELS, PO_STAGE_ROLE_LABELS, PO_STAGE_ROLES, STAGE_DEPT,
        chain_config, eval_approval, po_chain, with_department,
    )
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    cfg = await chain_config(db)
    chain = po_chain(po, cfg)
    stage = po.get("current_approver_stage") if po.get("status") == "pending_approval" else None
    if po.get("status") == "pending_approval" and not stage:
        stage = STAGE_DEPT
    u = await with_department(db, user)
    ev = eval_approval(po, u, chain, stage=stage, roles_map=PO_STAGE_ROLES,
                       labels=PO_STAGE_LABELS, role_labels=PO_STAGE_ROLE_LABELS)
    return po, chain, ev, cfg


async def _po_flags(db, user, pos: list):
    """Tempelkan flag izin SERVER ke daftar/detail PO.

    Frontend DILARANG menebak dari status/peran — sampai 2026-08-07 tabel PO
    merender tombol Setujui/Tolak untuk SIAPA PUN yang login (hanya digating
    `po.status === 'pending_approval'`), lalu backend membalas 403. Itu membuat
    tombol yang tampak bisa dipakai tapi selalu gagal.
    """
    from core.pr_approval import (
        PO_STAGE_LABELS, PO_STAGE_ROLE_LABELS, PO_STAGE_ROLES, STAGE_DEPT,
        chain_config, eval_approval, po_chain, with_department,
    )
    cfg = await chain_config(db)
    u = await with_department(db, user)
    role = (u.get("role") or "").lower()
    for po in pos:
        chain = po_chain(po, cfg)
        stage = po.get("current_approver_stage") if po.get("status") == "pending_approval" else None
        if po.get("status") == "pending_approval" and not stage:
            stage = STAGE_DEPT
        po.update(eval_approval(po, u, chain, stage=stage, roles_map=PO_STAGE_ROLES,
                                labels=PO_STAGE_LABELS,
                                role_labels=PO_STAGE_ROLE_LABELS))
        po["can_submit"] = po.get("status") in ("draft", "rejected")
        po["is_creator"] = bool(u.get("id")) and po.get("created_by") == u.get("id")
        po["kind"] = "po"
        po["kind_label"] = "Purchase Order"
        po["api_base"] = "/api/rahaza/purchase-orders"
        po["stage_labels_source"] = "server"
        if role in ("superadmin", "admin", "owner"):
            po["can_submit"] = po.get("status") in ("draft", "rejected")
    return pos


PO_DOCNUM_KEY = "rahaza_purchase_orders.po_number"


async def _gen_po_number(db, requested: str = "", *, sistem: bool = False) -> str:
    """Nomor PO: SATU PINTU kebijakan penomoran (SESI #19).

    `sistem=True` dipakai jalur yang LAHIR TANPA MANUSIA (PO massal per vendor dari
    satu permintaan): tidak ada layar tempat nomor bisa diketik, jadi jalur itu tetap
    otomatis meskipun owner menyetel MANUAL — dan itu dicatat di `catatan` registry,
    bukan disembunyikan.
    """
    if sistem:
        today = date.today().strftime("%Y%m%d")
        return await gen_prefixed_number(db, "rahaza_purchase_orders", "po_number",
                                         f"PO-{today}-", 3, config_key=PO_DOCNUM_KEY)
    return await issue_number(db, PO_DOCNUM_KEY, requested=requested)


async def _enrich_po(db, po):
    """Enrich PO dengan data master LENGKAP: material, supplier, dan satuan.

    2026-08-06 (Portal Pengadaan) — versi lama HANYA membaca `rahaza_materials`
    sehingga:
      · item free-form hasil PR→PO (tanpa `material_id`) tampil tanpa nama/satuan
        (kolom kosong di UI — keluhan "tidak lengkap mengambil collection"),
      · `unit` selalu ditimpa satuan DASAR material sehingga satuan beli
        (karton/bungkus) yang dipilih pembeli hilang dari tampilan,
      · nama/kode supplier tidak pernah diresolusi dari master.
    Versi ini menambal ketiganya sekaligus dan tetap kompatibel ke belakang.
    """
    if not po:
        return po

    items = po.get("items") or []

    # ── Master material (SSOT) ──────────────────────────────────────────────
    m_ids = list({it["material_id"] for it in items if it.get("material_id")})
    mats = await db.rahaza_materials.find(
        {"id": {"$in": m_ids}}, {"_id": 0}).to_list(len(m_ids) + 5) if m_ids else []
    m_map = {m["id"]: m for m in mats}

    # ── Master supplier (SSOT) ─────────────────────────────────────────────
    sup = None
    if po.get("supplier_id"):
        sup = await db.rahaza_suppliers.find_one(
            {"id": po["supplier_id"]},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "phone": 1, "email": 1,
             "address": 1, "npwp": 1, "payment_terms": 1, "payment_term_days": 1,
             "currency": 1, "lead_time_days": 1, "is_active": 1, "bank_accounts": 1},
        )
    if not sup and (po.get("vendor_name") or "").strip():
        # PO lama (pra-master): resolusi lewat nama ternormalisasi supaya UI tetap
        # bisa menampilkan kode supplier tanpa harus migrasi dulu.
        try:
            from routes.procurement_suppliers import name_key as _nk
            sup = await db.rahaza_suppliers.find_one(
                {"name_key": _nk(po["vendor_name"])},
                {"_id": 0, "id": 1, "code": 1, "name": 1, "phone": 1, "email": 1,
                 "address": 1, "npwp": 1, "payment_terms": 1, "payment_term_days": 1,
                 "currency": 1, "lead_time_days": 1, "is_active": 1, "bank_accounts": 1},
            )
        except Exception:
            sup = None
    po["supplier"] = sup or None
    po["supplier_code"] = (sup or {}).get("code") or po.get("supplier_code")
    po["supplier_name"] = (sup or {}).get("name") or po.get("vendor_name") or ""
    po["supplier_linked"] = bool(sup)
    po["payment_terms"] = po.get("payment_terms") or (sup or {}).get("payment_terms")
    po["currency"] = po.get("currency") or (sup or {}).get("currency") or "IDR"

    for it in items:
        m = m_map.get(it.get("material_id")) or {}
        base = _uom.base_uom_of(m) if m else (it.get("base_uom") or "")
        it["material_code"] = m.get("code") or it.get("material_code") or ""
        it["material_name"] = (m.get("name") or it.get("material_name")
                               or it.get("description") or "")
        it["material_type"] = m.get("type") or it.get("material_type") or ""
        it["material_linked"] = bool(m)
        it["base_uom"] = base or it.get("base_uom") or ""
        # `unit` (lama) = satuan DASAR; satuan beli ada di `uom`
        it["unit"] = base or it.get("unit") or ""
        it["uom"] = it.get("uom") or base or it.get("unit") or ""
        it["uom_factor"] = float(it.get("uom_factor") or 1)
        qty_base = float(it.get("qty_ordered") or 0)
        f = it["uom_factor"] or 1
        if it.get("qty_input") in (None, ""):
            it["qty_input"] = round(qty_base / f, 6) if f else qty_base
        if it.get("unit_cost_input") in (None, ""):
            it["unit_cost_input"] = round(float(it.get("unit_cost") or 0) * f, 4)
        it["qty_received_input"] = round(float(it.get("qty_received") or 0) / f, 6) if f else 0.0
        it["qty_remaining"] = max(0.0, round(qty_base - float(it.get("qty_received") or 0), 4))
        it["subtotal"] = round(qty_base * float(it.get("unit_cost") or 0), 2)
        if m:
            it["stock_unit_cost"] = float(m.get("unit_cost") or 0)
        # Label satuan siap tampil: "10 ktn (1.440 pcs)"
        if it["uom"] and base and it["uom"] != base and f != 1:
            it["qty_label"] = (f"{it['qty_input']:g} {it['uom']} "
                               f"({qty_base:g} {base})")
        else:
            it["qty_label"] = f"{qty_base:g} {base or it['uom']}"

    return po


async def _norm_po_items(db, raw_items):
    """Normalisasi + validasi item PO **dengan konversi satuan SSOT**.

    Kontrak baru (mendukung satuan beli berjenjang):
      Input  : {material_id?, description?, uom, qty_input|qty_ordered,
                unit_cost_input|unit_cost, notes}
      Disimpan:
        qty_input, unit_cost_input, uom, uom_factor   → apa yang pembeli lihat/cetak
        qty_ordered  = qty_input × uom_factor          → SATUAN DASAR (INV-UOM-2)
        unit_cost    = unit_cost_input ÷ uom_factor    → per SATUAN DASAR (INV-UOM-1)

    Item tanpa `material_id` (free-form dari PR: jasa, sewa, aset) TETAP diterima
    — sebelumnya dibuang diam-diam oleh `if not mid: continue` sehingga PO hasil
    PR bisa kehilangan barisnya.
    """
    raw_items = raw_items or []
    ids = [it.get("material_id") for it in raw_items if it.get("material_id")]
    mats = await db.rahaza_materials.find(
        {"id": {"$in": list(set(ids))}}, {"_id": 0}).to_list(len(ids) + 5) if ids else []
    m_map = {m["id"]: m for m in mats}

    cleaned = []
    for it in raw_items:
        mid = it.get("material_id") or None
        mat = m_map.get(mid) if mid else None
        if mid and not mat:
            raise HTTPException(400, f"Material ID tidak ditemukan: {mid}")

        desc = (it.get("description") or it.get("name") or "").strip()
        if not mid and not desc:
            continue  # baris kosong

        base = _uom.base_uom_of(mat) if mat else (
            _bom_uom.norm_unit(it.get("uom") or it.get("unit")) or "pcs")
        uom_in = _bom_uom.norm_unit(it.get("uom") or it.get("unit") or base) or base

        # Faktor konversi ke satuan dasar
        if mat:
            try:
                factor, source = _bom_uom.factor_to_base(mat, uom_in)
            except _uom.UomError as e:
                raise HTTPException(
                    400, f"{mat.get('code') or mid}: {e}")
        else:
            # free-form: satuan bebas, tidak ada master → faktor 1 (satuan = dasar)
            factor, source = 1.0, "freeform"

        # qty: utamakan qty_input (satuan beli); fallback qty_ordered (satuan dasar)
        if it.get("qty_input") not in (None, ""):
            qty_input = float(it.get("qty_input") or 0)
            qty_base = qty_input * factor
        else:
            qty_base = float(it.get("qty_ordered") or 0)
            qty_input = qty_base / factor if factor else qty_base
        if qty_base <= 0:
            continue

        # harga: utamakan unit_cost_input (per satuan beli)
        if it.get("unit_cost_input") not in (None, ""):
            cost_input = float(it.get("unit_cost_input") or 0)
            cost_base = cost_input / factor if factor else cost_input
        else:
            cost_base = float(it.get("unit_cost") or 0)
            cost_input = cost_base * factor
        if cost_base < 0:
            raise HTTPException(400, "Harga tidak boleh negatif.")

        cleaned.append({
            "id": it.get("id") or _uid(),
            "material_id": mid,
            "description": desc or (mat or {}).get("name") or "",
            "specification": (it.get("specification") or "").strip(),
            # tampilan / cetak (satuan beli)
            "uom": uom_in,
            "uom_factor": round(float(factor), 8),
            "uom_source": source,
            "qty_input": round(qty_input, 6),
            "unit_cost_input": round(cost_input, 4),
            # perhitungan (satuan dasar) — INV-UOM-1 & INV-UOM-2
            "base_uom": base,
            "qty_ordered": round(qty_base, 4),
            "qty_received": round(float(it.get("qty_received") or 0), 4),
            "unit_cost": round(cost_base, 6),
            "subtotal": round(qty_base * cost_base, 2),
            "notes": it.get("notes") or "",
        })
    return cleaned


async def _resolve_supplier(db, body: dict, *, current: dict | None = None) -> dict:
    """Resolusi supplier PO dari master (SSOT).

    Menerima `supplier_id` (disarankan) ATAU `vendor_name` (kompatibilitas lama).
    Bila hanya nama dikirim dan namanya cocok dengan master (name_key) → ditautkan
    otomatis. Bila tidak cocok, PO tetap bisa dibuat (tidak memblokir alur lama)
    tetapi ditandai `supplier_linked=False` agar bisa dibersihkan lewat migrasi.
    """
    from routes.procurement_suppliers import name_key as _nk
    cur = current or {}
    sid = (body.get("supplier_id") if "supplier_id" in body else cur.get("supplier_id")) or ""
    sid = str(sid).strip()
    sup = None
    if sid:
        sup = await db.rahaza_suppliers.find_one({"id": sid}, {"_id": 0})
        if not sup:
            raise HTTPException(400, f"Supplier {sid} tidak ditemukan di master.")
        if sup.get("is_active") is False:
            raise HTTPException(400, f"Supplier {sup.get('name')} sudah tidak aktif.")
    else:
        nm = (body.get("vendor_name") if "vendor_name" in body else cur.get("vendor_name")) or ""
        nm = str(nm).strip()
        if nm:
            sup = await db.rahaza_suppliers.find_one({"name_key": _nk(nm)}, {"_id": 0})

    if sup:
        primary_bank = next((b for b in (sup.get("bank_accounts") or [])
                             if b.get("is_primary")), None) or \
            (sup.get("bank_accounts") or [None])[0]
        primary_contact = next((c for c in (sup.get("contacts") or [])
                                if c.get("is_primary")), None) or \
            (sup.get("contacts") or [None])[0]
        return {
            "supplier_id": sup["id"],
            "supplier_code": sup.get("code"),
            "vendor_name": sup.get("name") or "",
            "vendor_contact": (body.get("vendor_contact")
                               or (primary_contact or {}).get("phone")
                               or sup.get("phone") or ""),
            "vendor_address": (body.get("vendor_address") or sup.get("address") or ""),
            "vendor_npwp": sup.get("npwp") or "",
            "payment_terms": sup.get("payment_terms") or "net30",
            "payment_term_days": int(sup.get("payment_term_days") or 30),
            "currency": sup.get("currency") or "IDR",
            "supplier_bank": primary_bank or None,
        }

    nm = (body.get("vendor_name") if "vendor_name" in body else cur.get("vendor_name")) or ""
    return {
        "supplier_id": None,
        "supplier_code": None,
        "vendor_name": str(nm).strip(),
        "vendor_contact": body.get("vendor_contact") or cur.get("vendor_contact") or "",
        "vendor_address": body.get("vendor_address") or cur.get("vendor_address") or "",
        "payment_terms": body.get("payment_terms") or cur.get("payment_terms") or "net30",
        "currency": body.get("currency") or cur.get("currency") or "IDR",
    }


# ── PO CRUD ────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders")
async def list_pos(
    request: Request,
    status: Optional[str] = None,
    vendor: Optional[str] = None,
    supplier_id: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    paginate: bool = Query(False, description="true → bentuk {items, pagination}"),
):
    user = await require_auth(request)
    db = get_db()
    q = {}
    if status:
        if status not in PO_STATUSES:
            raise HTTPException(400, f"Status harus salah satu: {PO_STATUSES}")
        q["status"] = status
    if supplier_id:
        q["supplier_id"] = supplier_id
    if vendor:
        q["vendor_name"] = {"$regex": re.escape(vendor), "$options": "i"}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"po_number": rx}, {"vendor_name": rx}, {"supplier_code": rx},
                    {"from_pr_number": rx}]
    if date_from:
        q["po_date"] = q.get("po_date", {})
        q["po_date"]["$gte"] = date_from
    if date_to:
        q["po_date"] = q.get("po_date", {})
        q["po_date"]["$lte"] = date_to

    total = await db.rahaza_purchase_orders.count_documents(q)
    cur = db.rahaza_purchase_orders.find(q, {"_id": 0}).sort("created_at", -1)
    if paginate:
        cur = cur.skip((page - 1) * limit).limit(limit)
        rows = await cur.to_list(limit)
    else:
        rows = await cur.to_list(500)

    for po in rows:
        await _enrich_po(db, po)
        po["item_count"] = len(po.get("items") or [])
        po["total_value"] = round(sum(float(i.get("qty_ordered") or 0) * float(i.get("unit_cost") or 0) for i in (po.get("items") or [])), 2)
        po["total_received"] = round(sum(float(i.get("qty_received") or 0) for i in (po.get("items") or [])), 4)
        po["received_pct"] = round(
            (po["total_received"] / sum(float(i.get("qty_ordered") or 0)
                                        for i in (po.get("items") or [])) * 100), 2
        ) if sum(float(i.get("qty_ordered") or 0) for i in (po.get("items") or [])) else 0.0

    # Flag izin dari SERVER (SSOT). Tabel PO dulu merender Setujui/Tolak untuk
    # SIAPA PUN yang login lalu backend membalas 403 — tombol yang tampak bisa
    # dipakai tapi selalu gagal.
    await _po_flags(db, user, rows)
    if paginate:
        return serialize_doc({
            "items": rows,
            "pagination": {"page": page, "page_size": limit, "total": total,
                           "total_pages": max(1, math.ceil(total / limit))},
        })
    return serialize_doc(rows)


@router.get("/purchase-orders/{po_id}")
async def get_po(po_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    await _enrich_po(db, po)
    # Flag izin dari SERVER (SSOT) supaya UI tidak menebak dari status/peran.
    from auth import require_auth as _ra
    await _po_flags(db, await _ra(request), [po])
    return serialize_doc(po)


@router.post("/purchase-orders")
async def create_po(request: Request):
    """Buat PO draft.

    Body:
      supplier_id            (str, disarankan — pilih dari Master Supplier)
      vendor_name            (str, kompatibilitas lama; dipakai bila supplier_id kosong)
      po_date, expected_delivery_date, notes
      items: [{material_id?, description?, uom, qty_input, unit_cost_input, notes}]
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()

    sup_fields = await _resolve_supplier(db, body)
    if not sup_fields.get("supplier_id") and not sup_fields.get("vendor_name"):
        raise HTTPException(400, "supplier_id (Master Supplier) atau vendor_name wajib diisi.")

    items = await _norm_po_items(db, body.get("items"))
    if not items:
        raise HTTPException(400, "Minimal 1 item (material master atau item bebas).")

    total_value = round(sum(float(i["qty_ordered"]) * float(i["unit_cost"]) for i in items), 2)

    doc = {
        "id": _uid(),
        "po_number": await _gen_po_number(db, (body.get("po_number") or "").strip()),
        **sup_fields,
        "po_date": body.get("po_date") or date.today().isoformat(),
        "expected_delivery_date": body.get("expected_delivery_date") or None,
        "items": items,
        "total_value": total_value,
        "status": "draft",
        "notes": body.get("notes") or "",
        "approval_flow_key": body.get("approval_flow_key") or "single_step",  # configurable
        "approvals": [],  # list of {user_id, user_name, approved_at, step}
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_purchase_orders.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.po", doc["po_number"])
    await _enrich_po(db, doc)
    return serialize_doc(doc)


@router.put("/purchase-orders/{po_id}")
async def update_po(po_id: str, request: Request):
    """Update draft PO."""
    user = await _require_admin(request)
    db = get_db()
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    if po.get("status") not in ("draft", "rejected"):
        raise HTTPException(400, f"Hanya PO Draft/Rejected yang bisa diedit. Status saat ini: {po.get('status')}")
    
    body = await request.json()
    upd = {"updated_at": _now()}

    if "supplier_id" in body or "vendor_name" in body:
        upd.update(await _resolve_supplier(db, body, current=po))
    if "vendor_contact" in body:
        upd["vendor_contact"] = body["vendor_contact"]
    if "vendor_address" in body:
        upd["vendor_address"] = body["vendor_address"]
    if "po_date" in body:
        upd["po_date"] = body["po_date"]
    if "expected_delivery_date" in body:
        upd["expected_delivery_date"] = body["expected_delivery_date"]
    if "notes" in body:
        upd["notes"] = body["notes"]
    if "items" in body:
        items = await _norm_po_items(db, body["items"])
        if not items:
            raise HTTPException(400, "Minimal 1 item (material master atau item bebas).")
        upd["items"] = items
        upd["total_value"] = round(
            sum(float(i["qty_ordered"]) * float(i["unit_cost"]) for i in items), 2)
    
    await db.rahaza_purchase_orders.update_one({"id": po_id}, {"$set": upd})
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.po", po["po_number"])
    out = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    await _enrich_po(db, out)
    return serialize_doc(out)


@router.delete("/purchase-orders/{po_id}")
async def delete_po(po_id: str, request: Request):
    """Delete draft PO."""
    user = await _require_admin(request)
    db = get_db()
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    if po.get("status") not in ("draft", "rejected"):
        raise HTTPException(400, "Hanya PO Draft/Rejected yang bisa dihapus.")
    
    await db.rahaza_purchase_orders.delete_one({"id": po_id})
    await log_activity(user["id"], user.get("name", ""), "delete", "rahaza.po", po["po_number"])
    return {"status": "deleted"}


# ── PO Approval Workflow ───────────────────────────────────────────────────────

@router.post("/purchase-orders/{po_id}/submit")
async def submit_po(po_id: str, request: Request):
    """Ajukan PO untuk persetujuan (draft → pending_approval).

    Rantai tahapnya DIBEKUKAN di sini berdasarkan nilai PO + ambang yang diatur
    owner, jadi mengubah ambang tidak menggeser PO yang sudah berjalan.
    """
    from core.pr_approval import (
        PO_STAGE_LABELS, PO_STAGE_ROLE_LABELS, PO_STAGE_ROLES, STAGE_DEPT,
        chain_config, notify_stage_approvers, po_chain,
    )
    user = await _require_admin(request)
    db = get_db()
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    if po.get("status") not in ("draft", "rejected"):
        raise HTTPException(400, f"Hanya PO Draft/Rejected yang bisa diajukan. Status: {po.get('status')}")

    cfg = await chain_config(db)
    # Rantai dihitung dari dokumen TANPA `approval_chain` lama supaya pengajuan
    # ulang setelah ditolak memakai nilai terbaru.
    chain = po_chain({k: v for k, v in po.items() if k != "approval_chain"}, cfg)
    step = {
        "id": _uid(), "step": "submit", "stage": None,
        "actor_id": user["id"],
        "actor_name": user.get("name", "") or user.get("email", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "submitted", "action_label": "Diajukan", "comment": "",
        "timestamp": _now().isoformat(),
    }
    await db.rahaza_purchase_orders.update_one(
        {"id": po_id},
        {"$set": {
            "status": "pending_approval",
            "submitted_at": _now(),
            "submitted_by": user["id"],
            # WAJIB untuk pemisahan wewenang: mesin persetujuan memakai
            # `requested_by` untuk menolak "pembuat menyetujui sendiri".
            "requested_by": po.get("created_by") or user["id"],
            "approval_chain": chain,
            "approval_thresholds": dict(cfg),
            "current_approver_stage": STAGE_DEPT,
            "approval_steps": [step],
            "rejected_reason": None,
            "updated_at": _now(),
        }}
    )
    after = {**po, "status": "pending_approval", "approval_chain": chain}
    await notify_stage_approvers(
        db, after, STAGE_DEPT, chain, module_id="proc-purchase-orders",
        number=po.get("po_number", ""),
        title=f"PO ke {po.get('vendor_name') or 'supplier'}",
        kind_label="Purchase Order", roles_map=PO_STAGE_ROLES,
        labels=PO_STAGE_LABELS, value_field="total_value")
    await log_activity(user["id"], user.get("name", ""), "submit", "rahaza.po", po["po_number"])
    out = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    await _enrich_po(db, out)
    await _po_flags(db, user, [out])
    out["stage_label"] = PO_STAGE_LABELS.get(STAGE_DEPT, "")
    out["next_approver_label"] = PO_STAGE_ROLE_LABELS.get(STAGE_DEPT, "")
    out["total_stages"] = len(chain)
    return serialize_doc(out)


@router.post("/purchase-orders/{po_id}/approve")
async def approve_po(po_id: str, request: Request):
    """Setujui SATU TAHAP persetujuan PO.

    Gerbangnya `core.pr_approval.eval_approval` (SSOT): peran tahap, larangan
    menyetujui PO sendiri, larangan satu orang menyetujui dua tahap, dan
    override admin yang TERCATAT.
    """
    from core.pr_approval import (
        PO_STAGE_LABELS, PO_STAGE_ROLES, next_stage_after, notify_requester,
        notify_stage_approvers,
    )
    user = await require_auth(request)
    db = get_db()
    po, chain, ev, _cfg = await _po_ctx(db, po_id, user)
    if po.get("status") != "pending_approval":
        raise HTTPException(400, f"Hanya PO Menunggu Persetujuan yang bisa disetujui. Status: {po.get('status')}")
    if not ev["can_approve"]:
        raise HTTPException(403, ev["blocked_reason"]
                            or "Akses ditolak: Anda tidak berhak menyetujui PO ini.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    comment = (body.get("comment") or body.get("notes") or "").strip()

    stage = ev["stage"]
    nxt = next_stage_after(chain, stage)
    label = f"Disetujui — {PO_STAGE_LABELS.get(stage, stage)}"
    if ev["is_override"]:
        label += " (override admin)"
    step = {
        "id": _uid(), "step": stage, "stage": stage,
        "actor_id": user["id"],
        "actor_name": user.get("name", "") or user.get("email", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "approved", "action_label": label, "comment": comment,
        "override": bool(ev["is_override"]),
        "override_reasons": list(ev["override_reasons"]),
        "timestamp": _now().isoformat(),
    }
    upd = {"current_approver_stage": nxt, "approval_chain": chain, "updated_at": _now()}
    if not nxt:
        upd.update({"status": "approved", "approved_at": _now(),
                    "approved_by": user["id"]})
    await db.rahaza_purchase_orders.update_one(
        {"id": po_id}, {"$set": upd, "$push": {"approval_steps": step,
                                               "approvals": {
                                                   "user_id": user["id"],
                                                   "user_name": user.get("name", ""),
                                                   "approved_at": _now(),
                                                   "step": stage}}})
    after = {**po, **upd}
    if nxt:
        await notify_stage_approvers(
            db, after, nxt, chain, module_id="proc-purchase-orders",
            number=po.get("po_number", ""),
            title=f"PO ke {po.get('vendor_name') or 'supplier'}",
            kind_label="Purchase Order", roles_map=PO_STAGE_ROLES,
            labels=PO_STAGE_LABELS, value_field="total_value")
    else:
        await notify_requester(
            db, after, severity="success", module_id="proc-purchase-orders",
            number=po.get("po_number", ""),
            title="Purchase Order Anda disetujui penuh",
            body=(f"{po.get('po_number', '')} — {po.get('vendor_name', '')}\n"
                  "Semua tahap persetujuan selesai. Langkah berikutnya: "
                  "kirim ke supplier & catat penerimaan barang."))
    await log_activity(user["id"], user.get("name", ""),
                       f"approve:{stage}", "rahaza.po", po["po_number"])
    out = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    await _enrich_po(db, out)
    await _po_flags(db, user, [out])
    out["stage_approved"] = stage
    out["next_stage"] = nxt
    out["next_stage_label"] = PO_STAGE_LABELS.get(nxt, "") if nxt else ""
    out["override"] = bool(ev["is_override"])
    return serialize_doc(out)


@router.get("/purchase-orders/{po_id}/timeline")
async def po_timeline(po_id: str, request: Request):
    """Jejak audit persetujuan PO: siapa, tahap apa, kapan, komentar, override."""
    user = await require_auth(request)
    db = get_db()
    po, _chain, ev, _cfg = await _po_ctx(db, po_id, user)
    return serialize_doc({
        "steps": po.get("approval_steps", []),
        "current_status": po.get("status"),
        "chain": ev["chain"], "approval_chain": ev["approval_chain"],
        "total_stages": ev["total_stages"], "stage": ev["stage"],
        "stage_label": ev["stage_label"],
        "next_approver_label": ev["next_approver_label"],
    })


@router.post("/purchase-orders/{po_id}/reject")
async def reject_po(po_id: str, request: Request):
    """Tolak PO (pending_approval → rejected). ALASAN WAJIB."""
    from core.pr_approval import PO_STAGE_LABELS, notify_requester
    user = await require_auth(request)
    db = get_db()
    po, _chain, ev, _cfg = await _po_ctx(db, po_id, user)
    if po.get("status") != "pending_approval":
        raise HTTPException(400, f"Hanya PO Menunggu Persetujuan yang bisa ditolak. Status: {po.get('status')}")
    if not ev["can_reject"]:
        raise HTTPException(403, ev["blocked_reason"]
                            or "Akses ditolak: Anda tidak berhak menolak PO ini.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    reason = (body.get("reason") or body.get("comment") or "").strip()
    if not reason:
        raise HTTPException(400, "Alasan penolakan wajib diisi agar pembuat PO tahu "
                                 "apa yang harus diperbaiki.")
    label = f"Ditolak — {PO_STAGE_LABELS.get(ev['stage'], ev['stage'] or '')}"
    if ev["is_override"]:
        label += " (override admin)"
    step = {
        "id": _uid(), "step": ev["stage"], "stage": ev["stage"],
        "actor_id": user["id"],
        "actor_name": user.get("name", "") or user.get("email", ""),
        "actor_role": (user.get("role") or "").lower(),
        "action": "rejected", "action_label": label, "comment": reason,
        "override": bool(ev["is_override"]),
        "override_reasons": list(ev["override_reasons"]),
        "timestamp": _now().isoformat(),
    }
    await db.rahaza_purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"status": "rejected", "rejected_at": _now(),
                  "rejected_by": user["id"], "rejected_reason": reason,
                  "current_approver_stage": None, "updated_at": _now()},
         "$push": {"approval_steps": step}})
    await notify_requester(
        db, {**po, "status": "rejected"}, severity="warning",
        module_id="proc-purchase-orders", number=po.get("po_number", ""),
        title="Purchase Order Anda ditolak",
        body=(f"{po.get('po_number', '')} — {po.get('vendor_name', '')}\n"
              f"Tahap: {PO_STAGE_LABELS.get(ev['stage'], '-')}\nAlasan: {reason}"))
    await log_activity(user["id"], user.get("name", ""), f"reject:{reason}", "rahaza.po", po["po_number"])
    out = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    await _enrich_po(db, out)
    await _po_flags(db, user, [out])
    return serialize_doc(out)


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_po(po_id: str, request: Request):
    """Cancel PO (any status except fully_received → cancelled)."""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()
    reason = body.get("reason") or "Tidak ada alasan"
    
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    if po.get("status") == "fully_received":
        raise HTTPException(400, "PO yang sudah fully received tidak bisa di-cancel.")
    if po.get("status") == "cancelled":
        raise HTTPException(400, "PO sudah dibatalkan.")
    
    await db.rahaza_purchase_orders.update_one(
        {"id": po_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": _now(),
                "cancelled_by": user["id"],
                "cancelled_reason": reason,
                "updated_at": _now(),
            }
        }
    )
    await log_activity(user["id"], user.get("name", ""), f"cancel:{reason}", "rahaza.po", po["po_number"])
    out = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    await _enrich_po(db, out)
    return serialize_doc(out)


# ── Update PO received qty (called from warehouse GR) ────────────────────────

async def update_po_received_qty(db, po_id: str, items_received: list):
    """
    Called by warehouse.py saat GR received.
    items_received: [{"material_id": "...", "qty": ...}, ...]
    
    Update qty_received per item dan status PO.
    """
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        log.warning(f"PO {po_id} tidak ditemukan untuk update received qty")
        return
    
    # Build maps: by po_item_id (preferred) and material_id (fallback).
    # PR-derived POs have free-form items without material_id, so po_item_id
    # is the reliable linkage between GR lines and PO lines.
    received_by_item = {}
    received_by_mid = {}
    for r in items_received:
        qty = float(r.get("qty") or 0)
        if qty <= 0:
            continue
        pid = r.get("po_item_id")
        mid = r.get("material_id")
        if pid:
            received_by_item[pid] = received_by_item.get(pid, 0) + qty
        if mid:
            received_by_mid[mid] = received_by_mid.get(mid, 0) + qty

    # Update PO items
    updated_items = []
    total_ordered = 0
    total_received = 0
    for it in (po.get("items") or []):
        pid = it.get("id")
        mid = it.get("material_id")
        qty_ordered = float(it.get("qty_ordered") or 0)
        current_received = float(it.get("qty_received") or 0)
        if pid and pid in received_by_item:
            add = received_by_item[pid]
        elif mid and mid in received_by_mid:
            add = received_by_mid[mid]
        else:
            add = 0
        new_received = current_received + add

        updated_items.append({
            **it,
            "qty_received": round(new_received, 4),
        })
        total_ordered += qty_ordered
        total_received += new_received
    
    # Determine new status
    new_status = po.get("status")
    if po.get("status") in ("approved", "partially_received"):
        if total_received >= total_ordered:
            new_status = "fully_received"
        elif total_received > 0:
            new_status = "partially_received"
    
    await db.rahaza_purchase_orders.update_one(
        {"id": po_id},
        {
            "$set": {
                "items": updated_items,
                "status": new_status,
                "updated_at": _now(),
            }
        }
    )
    log.info(f"PO {po.get('po_number')} updated: received {total_received}/{total_ordered}, status: {new_status}")


# ── PO → GR helpers (P1.C: Create GR from PO + audit trail) ──────────────────

async def compute_po_remaining(db, po_id: str) -> dict:
    """Compute remaining qty per material_id for a PO. Returns:
        {
            "po": {...},
            "items_remaining": [
                {
                    "po_item_id": str, "material_id": str, "material_name": str,
                    "unit": str, "qty_ordered": float, "qty_received": float,
                    "qty_remaining": float
                },
                ...
            ],
            "total_remaining": float
        }
    """
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return {"po": None, "items_remaining": [], "total_remaining": 0.0}
    await _enrich_po(db, po)

    items_out = []
    total = 0.0
    for it in (po.get("items") or []):
        qty_ordered = float(it.get("qty_ordered") or 0)
        qty_received = float(it.get("qty_received") or 0)
        qty_remaining = max(0.0, round(qty_ordered - qty_received, 4))
        factor = float(it.get("uom_factor") or 1) or 1
        items_out.append({
            "po_item_id": it.get("id"),
            "material_id": it.get("material_id"),
            "material_code": it.get("material_code"),
            "material_name": it.get("material_name") or it.get("description"),
            "material_type": it.get("material_type"),
            "description": it.get("description") or "",
            "unit": it.get("base_uom") or it.get("unit"),
            "base_uom": it.get("base_uom") or it.get("unit"),
            # satuan beli + faktor supaya penerimaan bisa menampilkan/menerima
            # dalam kemasan yang sama seperti saat dipesan
            "uom": it.get("uom") or it.get("base_uom") or it.get("unit"),
            "uom_factor": factor,
            "qty_ordered": round(qty_ordered, 4),
            "qty_received": round(qty_received, 4),
            "qty_remaining": qty_remaining,
            "qty_ordered_input": round(qty_ordered / factor, 6),
            "qty_remaining_input": round(qty_remaining / factor, 6),
            "unit_cost": float(it.get("unit_cost") or 0),
            "unit_cost_input": float(it.get("unit_cost_input")
                                     or float(it.get("unit_cost") or 0) * factor),
            "notes": it.get("notes") or "",
        })
        total += qty_remaining
    return {"po": po, "items_remaining": items_out, "total_remaining": round(total, 4)}


@router.get("/purchase-orders/{po_id}/remaining")
async def get_po_remaining(po_id: str, request: Request):
    """P1.C: GET remaining qty per item untuk PO (untuk pre-fill GR di frontend)."""
    await require_auth(request)
    db = get_db()
    res = await compute_po_remaining(db, po_id)
    if not res["po"]:
        raise HTTPException(404, "PO tidak ditemukan.")
    return serialize_doc({
        "po_id": res["po"]["id"],
        "po_number": res["po"]["po_number"],
        "vendor_name": res["po"]["vendor_name"],
        "status": res["po"]["status"],
        "items_remaining": res["items_remaining"],
        "total_remaining": res["total_remaining"],
    })


@router.post("/purchase-orders/{po_id}/create-gr")
async def create_gr_from_po(po_id: str, request: Request):
    """P1.C: Create Goods Receipt (GR) draft dari PO.

    Workflow:
      - Validasi PO status ∈ {approved, partially_received}
      - Hitung remaining qty per item
      - Skip item yang fully received
      - Buat GR draft di warehouse_receiving dengan:
        * po_id, po_number, supplier_name = vendor_name
        * items[*].expected_qty = qty_remaining
        * items[*].material_id, material_name terisi
        * enforce_po_qty = True (default; mencegah over-receive)
      - Mengembalikan GR doc.

    Body (optional):
      - location_id, location_name: lokasi penerimaan default
      - notes: catatan tambahan
      - items_override: [{po_item_id, qty}] - jika hanya ingin partial GR
    """
    user = await _require_admin(request)
    db = get_db()
    body = await request.json() if (await request.body()) else {}

    res = await compute_po_remaining(db, po_id)
    po = res["po"]
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")
    if po.get("status") not in ("approved", "partially_received"):
        raise HTTPException(
            400,
            f"Hanya PO Approved/Partially Received yang bisa dibuatkan GR. Status saat ini: {po.get('status')}",
        )
    if res["total_remaining"] <= 0:
        raise HTTPException(400, "Tidak ada qty tersisa untuk diterima.")

    # Build override map (material_id -> qty) if provided
    override_map: dict = {}
    if isinstance(body.get("items_override"), list):
        for ov in body["items_override"]:
            po_item_id = ov.get("po_item_id")
            try:
                q = float(ov.get("qty") or 0)
            except Exception:
                q = 0.0
            if po_item_id and q > 0:
                override_map[po_item_id] = q

    # Build GR items from PO remaining (skip 0)
    gr_items = []
    for ir in res["items_remaining"]:
        if ir["qty_remaining"] <= 0:
            continue
        expected = ir["qty_remaining"]
        if override_map and ir["po_item_id"] in override_map:
            expected = min(override_map[ir["po_item_id"]], ir["qty_remaining"])
        if expected <= 0:
            continue
        gr_items.append({
            "id": _uid(),
            "po_item_id": ir["po_item_id"],
            "product_name": ir["material_name"] or ir["material_code"] or ir.get("description") or "Unknown",
            "sku": ir["material_code"] or "",
            "material_id": ir["material_id"],
            "material_name": ir["material_name"] or ir["material_code"] or ir.get("description") or "Unknown",
            "expected_qty": float(expected),
            "received_qty": 0.0,
            "rejected_qty": 0.0,
            # `unit` = satuan DASAR (angka di atas selalu satuan dasar, INV-UOM-2)
            "unit": ir["base_uom"] or ir["unit"] or "pcs",
            "base_uom": ir["base_uom"] or ir["unit"] or "pcs",
            # satuan beli PO + faktornya → gudang bisa menerima per kemasan
            "po_uom": ir.get("uom") or ir["base_uom"] or "pcs",
            "uom_factor": float(ir.get("uom_factor") or 1),
            "expected_qty_input": round(float(expected) / (float(ir.get("uom_factor") or 1) or 1), 6),
            "unit_cost": float(ir["unit_cost"] or 0),
            "unit_cost_input": float(ir.get("unit_cost_input") or ir["unit_cost"] or 0),
            "inspection_status": "pending",
            "inspection_notes": "",
        })
    if not gr_items:
        raise HTTPException(400, "Tidak ada item yang bisa dibuatkan GR (semua sudah fully received).")

    # Nomor GR — race-safe & formatnya bisa diatur owner
    # (kunci `warehouse_receiving.receipt_number`)
    receipt_number = await gen_prefixed_number(db, "warehouse_receiving", "receipt_number",
                                               "GR-", 5)

    location_id = body.get("location_id", "")
    location_name = body.get("location_name", "")
    receipt = {
        "id": _uid(),
        "receipt_number": receipt_number,
        "source_type": "supplier",
        "source_ref": po.get("po_number") or "",
        "supplier_name": po.get("vendor_name") or "",
        "supplier_id": po.get("supplier_id") or None,
        "supplier_code": po.get("supplier_code") or None,
        "location_id": location_id,
        "location_name": location_name,
        "status": "draft",
        "items": gr_items,
        "notes": body.get("notes") or f"Auto-created from PO {po.get('po_number')}",
        "received_by": user["name"],
        "received_by_id": user["id"],
        # PO linkage
        "po_id": po["id"],
        "po_number": po.get("po_number"),
        # P1.C: enforce_po_qty default true → anti over-receive
        "enforce_po_qty": True,
        # Audit
        "created_from": "po",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.warehouse_receiving.insert_one(receipt)
    await log_activity(
        user["id"], user.get("name", ""),
        "create_from_po", "warehouse_receiving",
        f"Created GR {receipt_number} from PO {po.get('po_number')} ({len(gr_items)} items, {round(sum(i['expected_qty'] for i in gr_items),2)} total qty)",
    )
    return serialize_doc(receipt)


@router.get("/purchase-orders/{po_id}/grs")
async def list_grs_for_po(po_id: str, request: Request):
    """P1.C: List semua GR yang terkait ke PO (untuk audit trail di PO detail)."""
    await require_auth(request)
    db = get_db()
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0, "po_number": 1, "id": 1})
    if not po:
        raise HTTPException(404, "PO tidak ditemukan.")

    grs = await db.warehouse_receiving.find(
        {"po_id": po_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)

    # Compute summary per GR
    summary = []
    for gr in grs:
        items = gr.get("items") or []
        total_expected = sum(float(i.get("expected_qty") or 0) for i in items)
        total_received = sum(float(i.get("received_qty") or 0) for i in items)
        total_rejected = sum(float(i.get("rejected_qty") or 0) for i in items)
        summary.append({
            "id": gr["id"],
            "receipt_number": gr.get("receipt_number"),
            "status": gr.get("status"),
            "created_at": gr.get("created_at"),
            "received_by": gr.get("received_by"),
            "location_name": gr.get("location_name"),
            "items_count": len(items),
            "total_expected": round(total_expected, 4),
            "total_received": round(total_received, 4),
            "total_rejected": round(total_rejected, 4),
            "total_net": round(total_received - total_rejected, 4),
            "enforce_po_qty": gr.get("enforce_po_qty", False),
        })
    return serialize_doc(summary)


# ─── BULK CSV IMPORT ────────────────────────────────────────────────────────────

@router.post("/purchase-orders/bulk-import")
async def bulk_import_po_csv(request: Request):
    """
    Import multiple PO items from CSV.
    Body: {supplier_id?, vendor_name, rows: [{material_code, qty_ordered, unit_cost, uom?}], ...}
    Baris CSV boleh memakai satuan beli (`uom`) — dikonversi ke satuan dasar
    memakai SSOT `core/uom.py` + `core/bom_uom.py` (INV-UOM-1/2).
    Returns: list of created POs grouped by vendor.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    rows = body.get("rows", [])
    if not rows:
        raise HTTPException(400, "CSV kosong atau tidak ada baris valid.")

    # Batch prefetch all referenced materials by code (single $in query)
    mat_codes_csv = list({(row.get("material_code") or "").strip().upper()
                           for row in rows if (row.get("material_code") or "").strip()})
    mat_by_code: dict = {}
    if mat_codes_csv:
        async for m in db.rahaza_materials.find(
            {"code": {"$in": mat_codes_csv}, "active": True}, {"_id": 0}
        ):
            mat_by_code[m["code"]] = m

    # Group rows by vendor_name (allow per-row vendor override, default to body-level)
    default_vendor = (body.get("vendor_name") or "").strip()
    groups: dict = {}
    errors = []
    for i, row in enumerate(rows):
        vendor = (row.get("vendor_name") or default_vendor).strip()
        if not vendor:
            errors.append(f"Row {i+1}: vendor_name wajib.")
            continue
        mat_code = (row.get("material_code") or "").strip().upper()
        if not mat_code:
            errors.append(f"Row {i+1}: material_code wajib.")
            continue
        try:
            qty = float(row.get("qty_ordered") or row.get("qty_input") or 0)
            price = float(row.get("unit_cost") or row.get("unit_cost_input") or 0)
        except (ValueError, TypeError):
            errors.append(f"Row {i+1}: qty_ordered/unit_cost harus angka.")
            continue
        if qty <= 0:
            errors.append(f"Row {i+1}: qty_ordered harus > 0.")
            continue
        mat = mat_by_code.get(mat_code)
        if not mat:
            errors.append(f"Row {i+1}: material '{mat_code}' tidak ditemukan.")
            continue
        groups.setdefault(vendor, []).append({
            "material_id": mat["id"],
            "uom": row.get("uom") or row.get("unit") or _uom.base_uom_of(mat),
            "qty_input": qty,
            "unit_cost_input": price,
            "notes": row.get("notes") or "",
        })

    if errors and not groups:
        raise HTTPException(422, {"errors": errors})

    created = []
    for vendor, raw_items in groups.items():
        try:
            items = await _norm_po_items(db, raw_items)
        except HTTPException as e:
            errors.append(f"{vendor}: {e.detail}")
            continue
        if not items:
            continue
        sup_fields = await _resolve_supplier(
            db, {"supplier_id": body.get("supplier_id"), "vendor_name": vendor,
                 "vendor_contact": body.get("vendor_contact"),
                 "vendor_address": body.get("vendor_address")})
        doc = {
            "id": _uid(),
            "po_number": await _gen_po_number(db, sistem=True),
            **sup_fields,
            "po_date": body.get("po_date") or date.today().isoformat(),
            "expected_delivery_date": body.get("expected_delivery_date") or None,
            "items": items,
            "status": "draft",
            "approvals": [],
            "approval_flow_key": "single_step",
            "notes": f"[Bulk Import] {body.get('notes') or ''}".strip(),
            "total_value": round(sum(float(it["qty_ordered"]) * float(it["unit_cost"])
                                     for it in items), 2),
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.rahaza_purchase_orders.insert_one(doc)
        created.append(serialize_doc(doc))

    return {"ok": True, "created": len(created), "purchase_orders": created, "row_errors": errors}

