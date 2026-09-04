"""
Portal Pengadaan — Dashboard Ringkasan (SSOT lintas koleksi)

Menjawab keluhan "tidak lengkap dalam mengambil collection datanya": dashboard
ini membaca SEMUA koleksi yang membentuk siklus pengadaan (P2P), bukan satu:

  dewi_procurement_requests        → Permintaan Pengadaan (PR)
  rahaza_purchase_orders           → Purchase Order (PO)
  warehouse_receiving              → Penerimaan Barang (GR)
  rahaza_grn_inspections           → Inspeksi QC penerimaan
  rahaza_ap_invoices               → Invoice hutang supplier (AP)
  rahaza_suppliers                 → Master supplier
  rahaza_supplier_price_lists      → Daftar harga supplier
  acc_purchase_requests            → Request Pembelian Aksesoris (divisi)

Endpoint:
  GET /api/procurement/overview        — kartu KPI + antrean kerja + peringatan
  GET /api/procurement/pipeline        — funnel PR → PO → GR → AP
  GET /api/procurement/spend-analysis  — belanja per supplier / kategori / bulan
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import serialize_doc
from core.pr_approval import ACC_PR_COLLECTION, ACC_PR_OPEN_STATUSES
from database import get_db
# 2026-08-06 (BUG-RBAC-PROC-1): dashboard pengadaan dulu memakai `require_auth`
# (cukup login) sehingga angka belanja, hutang supplier, dan daftar PO/PR bisa
# dibaca semua pegawai. Kini butuh AKSES PORTAL Pengadaan lewat penjaga SSOT.
from routes.shared import require_portal

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/procurement", tags=["procurement-dashboard"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


OPEN_PO_STATUS = ["approved", "partially_received"]
PENDING_PR_STATUS = ["submitted", "dept_approved", "finance_approved"]


async def _count(db, coll: str, q: dict) -> int:
    try:
        return await db[coll].count_documents(q)
    except Exception:
        log.warning("count gagal untuk %s", coll, exc_info=True)
        return 0


@router.get("/overview")
async def procurement_overview(request: Request):
    """Kartu KPI + antrean kerja + peringatan untuk Portal Pengadaan."""
    user = await require_portal(request, "procurement", allow_perms=("purchasing.view", "purchasing.manage"))
    db = get_db()
    today = date.today()
    month_start = today.replace(day=1).isoformat()

    # ── PR ──────────────────────────────────────────────────────────────────
    pr_total = await _count(db, "dewi_procurement_requests", {})
    pr_pending = await _count(db, "dewi_procurement_requests",
                              {"status": {"$in": PENDING_PR_STATUS}})
    pr_approved = await _count(db, "dewi_procurement_requests", {"status": "approved"})
    pr_mine = await _count(db, "dewi_procurement_requests", {"requested_by": user["id"]})

    # ── PO ──────────────────────────────────────────────────────────────────
    po_draft = await _count(db, "rahaza_purchase_orders", {"status": "draft"})
    po_pending = await _count(db, "rahaza_purchase_orders", {"status": "pending_approval"})
    po_open = await _count(db, "rahaza_purchase_orders", {"status": {"$in": OPEN_PO_STATUS}})
    po_done = await _count(db, "rahaza_purchase_orders", {"status": "fully_received"})

    po_value_agg = await db.rahaza_purchase_orders.aggregate([
        {"$match": {"status": {"$nin": ["cancelled", "rejected", "draft"]},
                    "po_date": {"$gte": month_start}}},
        {"$group": {"_id": None, "value": {"$sum": "$total_value"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    po_value_month = round((po_value_agg[0]["value"] if po_value_agg else 0) or 0, 2)

    open_value_agg = await db.rahaza_purchase_orders.aggregate([
        {"$match": {"status": {"$in": OPEN_PO_STATUS}}},
        {"$group": {"_id": None, "value": {"$sum": "$total_value"}}},
    ]).to_list(1)
    open_po_value = round((open_value_agg[0]["value"] if open_value_agg else 0) or 0, 2)

    # ── GR & QC ─────────────────────────────────────────────────────────────
    gr_draft = await _count(db, "warehouse_receiving", {"status": "draft"})
    gr_received = await _count(db, "warehouse_receiving",
                               {"status": {"$in": ["received", "completed"]}})
    qc_pending = await _count(db, "warehouse_receiving",
                              {"status": {"$in": ["received", "completed"]},
                               "$or": [{"inspection_id": {"$exists": False}},
                                       {"inspection_id": None}]})

    # ── AP ──────────────────────────────────────────────────────────────────
    ap_unpaid = await _count(db, "rahaza_ap_invoices",
                             {"status": {"$in": ["draft", "posted", "approved", "unpaid",
                                                 "partially_paid"]}})
    ap_agg = await db.rahaza_ap_invoices.aggregate([
        {"$match": {"status": {"$nin": ["paid", "cancelled", "void"]}}},
        {"$group": {"_id": None, "value": {"$sum": "$total_amount"}}},
    ]).to_list(1)
    ap_outstanding = round((ap_agg[0]["value"] if ap_agg else 0) or 0, 2)

    # ── Supplier ────────────────────────────────────────────────────────────
    sup_total = await _count(db, "rahaza_suppliers", {})
    sup_active = await _count(db, "rahaza_suppliers", {"is_active": {"$ne": False}})
    price_rows = await _count(db, "rahaza_supplier_price_lists", {"is_active": True})

    # ── PR aksesoris (divisi) ───────────────────────────────────────────────
    # BUG 2026-08-07 (lanjutan laporan owner "PR aksesoris harusnya tersambung ke
    # procurement"): kartu ini SELALU 0 karena dua sebab yang saling menutupi:
    #   1. koleksi yang dibaca (`dewi_accessories_purchase_requests` dan
    #      `dewi_acc_purchase_requests`) TIDAK PERNAH ADA. Koleksi sebenarnya
    #      adalah `acc_purchase_requests` (lihat routes/dewi_accessories_purchase.py
    #      yang menulis lewat `db.acc_purchase_requests`);
    #   2. filter statusnya huruf kecil (`draft`/`submitted`), sedangkan Request
    #      Aksesoris memakai status BERKAPITAL (`Draft`/`Submitted`/`Approved`).
    # Jadi walau namanya dibetulkan tanpa membetulkan kapitalisasi, angka
    # "menunggu proses" tetap 0. Keduanya dibetulkan sekaligus di sini.
    # `ACC_PR_COLLECTION` = SSOT nama koleksi supaya tidak ada tebakan nama lagi.
    acc_pr = await _count(db, ACC_PR_COLLECTION, {})
    # "Menunggu proses" = belum menjadi pesanan/penerimaan dan belum ditolak.
    acc_pr_pending = await _count(db, ACC_PR_COLLECTION,
                                  {"status": {"$in": ACC_PR_OPEN_STATUSES}})
    # Yang benar-benar menunggu KEPUTUSAN approver (dipakai antrean kerja).
    acc_pr_awaiting_approval = await _count(db, ACC_PR_COLLECTION,
                                            {"status": "Submitted"})

    # ── Peringatan: PO jatuh tempo & PO tanpa supplier master ───────────────
    soon = (today + timedelta(days=7)).isoformat()
    late_pos = await db.rahaza_purchase_orders.find(
        {"status": {"$in": OPEN_PO_STATUS}, "expected_delivery_date": {"$ne": None,
                                                                      "$lt": today.isoformat()}},
        {"_id": 0, "id": 1, "po_number": 1, "vendor_name": 1, "supplier_code": 1,
         "expected_delivery_date": 1, "total_value": 1, "status": 1},
    ).sort("expected_delivery_date", 1).limit(20).to_list(20)
    due_soon = await db.rahaza_purchase_orders.find(
        {"status": {"$in": OPEN_PO_STATUS},
         "expected_delivery_date": {"$gte": today.isoformat(), "$lte": soon}},
        {"_id": 0, "id": 1, "po_number": 1, "vendor_name": 1, "supplier_code": 1,
         "expected_delivery_date": 1, "total_value": 1, "status": 1},
    ).sort("expected_delivery_date", 1).limit(20).to_list(20)
    po_no_supplier = await _count(db, "rahaza_purchase_orders",
                                  {"$or": [{"supplier_id": {"$exists": False}},
                                           {"supplier_id": None}, {"supplier_id": ""}]})

    # ── Aktivitas terbaru (gabungan PR + PO) ────────────────────────────────
    recent_prs = await db.dewi_procurement_requests.find(
        {}, {"_id": 0, "id": 1, "request_number": 1, "title": 1, "status": 1,
             "total_estimated": 1, "created_at": 1, "requested_by_name": 1},
    ).sort("created_at", -1).limit(5).to_list(5)
    recent_pos = await db.rahaza_purchase_orders.find(
        {}, {"_id": 0, "id": 1, "po_number": 1, "vendor_name": 1, "status": 1,
             "total_value": 1, "created_at": 1, "po_date": 1},
    ).sort("created_at", -1).limit(5).to_list(5)

    return serialize_doc({
        "kpi": {
            "pr_total": pr_total, "pr_pending": pr_pending, "pr_approved": pr_approved,
            "pr_mine": pr_mine,
            "po_draft": po_draft, "po_pending_approval": po_pending, "po_open": po_open,
            "po_completed": po_done,
            "po_value_this_month": po_value_month, "open_po_value": open_po_value,
            "gr_draft": gr_draft, "gr_received": gr_received, "qc_pending": qc_pending,
            "ap_unpaid": ap_unpaid, "ap_outstanding": ap_outstanding,
            "suppliers_total": sup_total, "suppliers_active": sup_active,
            "price_list_rows": price_rows,
            "accessory_pr_total": acc_pr, "accessory_pr_pending": acc_pr_pending,
            "accessory_pr_awaiting_approval": acc_pr_awaiting_approval,
        },
        "alerts": {
            "po_overdue": late_pos,
            "po_due_soon": due_soon,
            "po_without_supplier_master": po_no_supplier,
        },
        "recent": {"requests": recent_prs, "purchase_orders": recent_pos},
        "generated_at": _now(),
    })


@router.get("/pipeline")
async def procurement_pipeline(request: Request, days: int = Query(90, ge=7, le=730)):
    """Funnel P2P: PR → PO → GR → AP dalam N hari terakhir."""
    await require_portal(request, "procurement", allow_perms=("purchasing.view", "purchasing.manage"))
    db = get_db()
    since_iso = (date.today() - timedelta(days=days)).isoformat()
    since_dt = _now() - timedelta(days=days)

    pr_by_status = await db.dewi_procurement_requests.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1},
                    "value": {"$sum": "$total_estimated"}}},
    ]).to_list(50)
    po_by_status = await db.rahaza_purchase_orders.aggregate([
        {"$match": {"po_date": {"$gte": since_iso}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}, "value": {"$sum": "$total_value"}}},
    ]).to_list(50)
    gr_by_status = await db.warehouse_receiving.aggregate([
        {"$match": {"created_at": {"$gte": since_dt}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]).to_list(50)
    ap_by_status = await db.rahaza_ap_invoices.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}, "value": {"$sum": "$total_amount"}}},
    ]).to_list(50)

    def fmt(rows):
        return [{"status": r["_id"] or "unknown", "count": r["n"],
                 "value": round(r.get("value") or 0, 2)} for r in rows]

    return serialize_doc({
        "period_days": days,
        "requests": fmt(pr_by_status),
        "purchase_orders": fmt(po_by_status),
        "goods_receipts": fmt(gr_by_status),
        "ap_invoices": fmt(ap_by_status),
    })


@router.get("/spend-analysis")
async def spend_analysis(request: Request, months: int = Query(6, ge=1, le=24),
                         supplier_id: Optional[str] = None):
    """Analisis belanja: per supplier, per kategori material, per bulan."""
    await require_portal(request, "procurement", allow_perms=("purchasing.view", "purchasing.manage"))
    db = get_db()
    start = (date.today().replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    q: dict = {"po_date": {"$gte": start.isoformat()},
               "status": {"$nin": ["cancelled", "rejected", "draft"]}}
    if supplier_id:
        q["supplier_id"] = supplier_id

    pos = await db.rahaza_purchase_orders.find(
        q, {"_id": 0, "po_number": 1, "po_date": 1, "supplier_id": 1, "vendor_name": 1,
            "supplier_code": 1, "items": 1, "total_value": 1, "status": 1}).to_list(3000)

    mat_ids = list({it.get("material_id") for p in pos for it in (p.get("items") or [])
                    if it.get("material_id")})
    mats = await db.rahaza_materials.find(
        {"id": {"$in": mat_ids}}, {"_id": 0, "id": 1, "type": 1, "category": 1,
                                   "code": 1, "name": 1}).to_list(len(mat_ids) + 5) \
        if mat_ids else []
    mmap = {m["id"]: m for m in mats}

    by_supplier: dict = {}
    by_category: dict = {}
    by_month: dict = {}
    by_material: dict = {}
    for p in pos:
        key = p.get("supplier_id") or f"name::{p.get('vendor_name') or '-'}"
        s = by_supplier.setdefault(key, {
            "supplier_id": p.get("supplier_id"), "supplier_code": p.get("supplier_code"),
            "supplier_name": p.get("vendor_name") or "-", "po_count": 0, "value": 0.0})
        s["po_count"] += 1
        s["value"] += float(p.get("total_value") or 0)

        mo = str(p.get("po_date") or "")[:7]
        m = by_month.setdefault(mo, {"month": mo, "po_count": 0, "value": 0.0})
        m["po_count"] += 1
        m["value"] += float(p.get("total_value") or 0)

        for it in (p.get("items") or []):
            amount = float(it.get("qty_ordered") or 0) * float(it.get("unit_cost") or 0)
            mat = mmap.get(it.get("material_id")) or {}
            cat = mat.get("type") or ("free_form" if not it.get("material_id") else "other")
            c = by_category.setdefault(cat, {"category": cat, "value": 0.0, "lines": 0})
            c["value"] += amount
            c["lines"] += 1
            mk = it.get("material_id") or f"desc::{it.get('description') or '-'}"
            mm = by_material.setdefault(mk, {
                "material_id": it.get("material_id"),
                "material_code": mat.get("code") or it.get("material_code") or "",
                "material_name": (mat.get("name") or it.get("description")
                                  or it.get("material_name") or "-"),
                "qty_base": 0.0, "value": 0.0, "base_uom": it.get("base_uom") or ""})
            mm["qty_base"] += float(it.get("qty_ordered") or 0)
            mm["value"] += amount

    def rnd(rows, key="value"):
        out = list(rows)
        for r in out:
            r[key] = round(r[key], 2)
            if "qty_base" in r:
                r["qty_base"] = round(r["qty_base"], 4)
        out.sort(key=lambda r: -r[key])
        return out

    return serialize_doc({
        "months": months,
        "total_value": round(sum(float(p.get("total_value") or 0) for p in pos), 2),
        "po_count": len(pos),
        "by_supplier": rnd(by_supplier.values())[:50],
        "by_category": rnd(by_category.values()),
        "by_month": sorted(by_month.values(), key=lambda r: r["month"]),
        "top_materials": rnd(by_material.values())[:25],
    })
