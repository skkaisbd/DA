"""
CV. Dewi Aditya — Laporan Maklon (dulu "Phase 7 Reporting").

DITULIS ULANG 2026-08-06 — SUMBER DATA DIPINDAH KE SSOT
------------------------------------------------------
Versi lama membaca koleksi yang **sudah tidak ditulisi siapa pun**:
`dewi_cmt_progress_reports` (0 dokumen), `dewi_cmt_delivery_orders` (0),
`dewi_maklon_dispatches` (0), dan `dewi_cmt_jobs` (job legacy yang diarsipkan).
Akibatnya seluruh Laporan Maklon tampil kosong walau produksi berjalan.

SSOT yang dipakai sekarang (semua lewat `services/mgmt_analytics.py`):
  PO maklon        : `production_pos` (business_type != internal) + `po_items`
  Pelaksanaan      : `production_jobs` + `production_job_items`
  Buku kuantitas   : `core/production_qty_ledger.ledger_view()`
  Progres harian   : `production_progress`
  Penerimaan CMT   : `cmt_receipts` (+ `cmt_receipt_lines`)
  Kirim ke CMT     : `vendor_shipments`
  Kirim ke buyer   : `buyer_shipments` + `buyer_shipment_items`
  Komersial/klien  : `dewi_maklon_pos` (+ `dewi_maklon_invoices`, `rahaza_ar_invoices`)
  Penjualan online : `marketing_orders`  (tetap — datanya nyata)
  Penyesuaian stok : `rahaza_stock_ledger` (op=adjust)

Bentuk respons DIPERTAHANKAN agar `Phase7ReportingModule.jsx` tidak rusak;
setiap respons kini menambah `sources` (jejak koleksi + jumlah dokumen) supaya
angka bisa ditelusuri.

Endpoints (prefix /api/dewi/reports):
  GET /daily?date=YYYY-MM-DD[&domain=]
  GET /monthly?year=&month=[&domain=]
  GET /po/{po_id}
  GET /actual-vs-target?period=YYYY-MM[&domain=]
  GET /production-trend?days=30[&domain=]
  GET /export/daily.csv?date=
  GET /export/monthly.csv?year=&month=
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from typing import Optional, Dict
from datetime import datetime, date, timedelta
import logging
import csv
import io

from database import get_db
from auth import require_auth, serialize_doc
from services.mgmt_analytics import (
    MAX_DOCS, as_iso_date, buyer_dispatch_map, domain_label, domain_scope,
    f as _f, i as _i, norm_domain,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/reports", tags=["dewi-reports"])


def _today_str() -> str:
    return date.today().isoformat()


def _date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _dom(request: Optional[Request], default: str = "maklon") -> str:
    """Laporan ini milik Portal Maklon → default domain maklon, tapi bisa dialihkan."""
    if request is None:
        return default
    return norm_domain(request.query_params.get("domain") or default)


async def _receipts_of(db, po_ids: list) -> list:
    if not po_ids:
        return []
    return await db.cmt_receipts.find(
        {"po_id": {"$in": po_ids}},
        {"_id": 0, "id": 1, "po_id": 1, "po_number": 1, "receipt_code": 1, "receipt_date": 1,
         "status": 1, "cmt_vendor_id": 1, "cmt_name": 1, "total_actual": 1,
         "total_rejected": 1, "total_qty_short": 1, "total_claimed_by_cmt": 1},
    ).to_list(MAX_DOCS)


def _vendor_bucket(store: dict, vid: str, name: str) -> dict:
    return store.setdefault(vid or "internal", {
        "cmt_partner_id": vid or "internal",
        "cmt_name": name or "Produksi Internal",
        "qty_processed": 0, "qty_passed": 0, "qty_failed": 0,
        "_refs": set(), "_days": set(),
    })


# ── DAILY REPORT ───────────────────────────────────────────────────────────────
@router.get("/daily")
async def daily_report(
    request: Request = None,
    report_date: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD; default hari ini"),
    user: dict = Depends(require_auth),
):
    """Laporan harian dari SSOT: produksi/penerimaan, kirim, fulfillment, penyesuaian stok."""
    db = get_db()
    target = report_date or _today_str()
    try:
        datetime.strptime(target, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Format tanggal harus YYYY-MM-DD")
    domain = _dom(request)
    sc = await domain_scope(db, domain)

    by_vendor: Dict[str, dict] = {}
    by_step: Dict[str, int] = {}

    # 1a. Penerimaan dari CMT pada tanggal itu = "diproses/lolos/gagal" versi nyata
    receipts = await _receipts_of(db, sc["po_ids"])
    receipts_today = [r for r in receipts if as_iso_date(r.get("receipt_date")) == target]
    for r in receipts_today:
        actual = _i(r.get("total_actual"))
        reject = _i(r.get("total_rejected"))
        b = _vendor_bucket(by_vendor, r.get("cmt_vendor_id"), r.get("cmt_name"))
        b["qty_processed"] += actual
        b["qty_passed"] += max(0, actual - reject)
        b["qty_failed"] += reject
        b["_refs"].add(r.get("po_number") or r.get("po_id"))
        by_step["Penerimaan dari CMT"] = by_step.get("Penerimaan dari CMT", 0) + actual

    # 1b. Catatan progres produksi (dipakai job internal maupun job maklon internal)
    prog = await db.production_progress.find(
        {"job_id": {"$in": sc["job_ids"]}},
        {"_id": 0, "job_id": 1, "completed_quantity": 1, "progress_date": 1},
    ).to_list(MAX_DOCS) if sc["job_ids"] else []
    prog_today = [p for p in prog if as_iso_date(p.get("progress_date")) == target]
    for p in prog_today:
        job = sc["job_by_id"].get(p.get("job_id")) or {}
        qty = _i(p.get("completed_quantity"))
        b = _vendor_bucket(by_vendor, job.get("vendor_id"), job.get("vendor_name"))
        b["qty_processed"] += qty
        b["qty_passed"] += qty
        b["_refs"].add(job.get("job_number") or job.get("po_number"))
        by_step["Progres produksi"] = by_step.get("Progres produksi", 0) + qty

    production_vendors = []
    for v in by_vendor.values():
        refs = v.pop("_refs")
        v.pop("_days", None)
        production_vendors.append({**v, "jobs_count": len([x for x in refs if x])})

    total_processed = sum(v["qty_processed"] for v in production_vendors)
    total_passed = sum(v["qty_passed"] for v in production_vendors)
    total_failed = sum(v["qty_failed"] for v in production_vendors)

    # 2. Pengiriman: keluar = surat jalan ke CMT · masuk = penerimaan dari CMT
    vships = await db.vendor_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}},
        {"_id": 0, "shipment_date": 1, "created_at": 1, "status": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    do_issued = sum(1 for s in vships
                    if as_iso_date(s.get("shipment_date") or s.get("created_at")) == target)
    do_received = len(receipts_today)

    # 3. Fulfillment penjualan online (data nyata: marketing_orders)
    fulfillment_dispatched = 0
    fulfillment_total_qty = 0
    try:
        async for o in db.marketing_orders.find({"fulfillment_status": "dispatched"}):
            if as_iso_date(o.get("dispatched_at")) == target:
                fulfillment_dispatched += 1
                fulfillment_total_qty += sum(
                    _i(it.get("qty_allocated", it.get("quantity", 0)))
                    for it in (o.get("fulfillment_items") or o.get("items") or []))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[laporan-harian] fulfillment gagal dihitung: {e}")

    # 4. Penyesuaian stok hari itu — pembaca kanonik (buku besar stok)
    adj_count = 0
    try:
        start = datetime.fromisoformat(f"{target}T00:00:00")
        end = start + timedelta(days=1)
        adj_count = await db.rahaza_stock_ledger.count_documents(
            {"op": "adjust", "created_at": {"$gte": start, "$lt": end}})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[laporan-harian] penyesuaian stok gagal dihitung: {e}")

    # 5. Kirim ke buyer pada hari itu
    dispatch = await buyer_dispatch_map(db, sc["po_ids"])
    buyer_qty_today = 0
    bs = await db.buyer_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "id": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    if bs:
        bsi = await db.buyer_shipment_items.find(
            {"shipment_id": {"$in": [b["id"] for b in bs]}},
            {"_id": 0, "qty_shipped": 1, "dispatch_date": 1},
        ).to_list(MAX_DOCS)
        buyer_qty_today = sum(_i(x.get("qty_shipped")) for x in bsi
                              if as_iso_date(x.get("dispatch_date")) == target)

    return {
        "date": target,
        "domain": domain,
        "domain_label": domain_label(domain),
        "production": {
            "total_processed": total_processed,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate_pct": round(total_passed / total_processed * 100, 1) if total_processed else 0,
            "by_vendor": production_vendors,
            "by_step": [{"step": k, "qty": v} for k, v in by_step.items()],
        },
        "delivery_orders": {
            "issued": do_issued,          # surat jalan ke CMT
            "received": do_received,       # penerimaan dari CMT
        },
        "buyer_delivery": {
            "qty_today": buyer_qty_today,
            "po_with_dispatch": len(dispatch),
        },
        "fulfillment": {
            "dispatched_orders": fulfillment_dispatched,
            "dispatched_qty": fulfillment_total_qty,
        },
        "stock_adjustments": adj_count,
        "sources": [
            {"collection": "production_pos", "count": len(sc["pos"]), "note": f"PO domain {domain}"},
            {"collection": "cmt_receipts", "count": len(receipts), "note": f"{len(receipts_today)} pada tanggal ini"},
            {"collection": "production_progress", "count": len(prog), "note": f"{len(prog_today)} pada tanggal ini"},
            {"collection": "vendor_shipments", "count": len(vships), "note": "surat jalan ke CMT"},
            {"collection": "rahaza_stock_ledger", "count": adj_count, "note": "penyesuaian stok"},
        ],
    }


# ── MONTHLY REPORT ─────────────────────────────────────────────────────────────
@router.get("/monthly")
async def monthly_report(
    request: Request = None,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    user: dict = Depends(require_auth),
):
    """Laporan bulanan agregat per vendor CMT & per klien maklon — dari SSOT."""
    db = get_db()
    month_str = f"{year:04d}-{month:02d}"
    domain = _dom(request)
    sc = await domain_scope(db, domain)

    by_vendor: Dict[str, dict] = {}
    receipts = await _receipts_of(db, sc["po_ids"])
    for r in receipts:
        d = as_iso_date(r.get("receipt_date"))
        if not d.startswith(month_str):
            continue
        actual = _i(r.get("total_actual"))
        reject = _i(r.get("total_rejected"))
        b = _vendor_bucket(by_vendor, r.get("cmt_vendor_id"), r.get("cmt_name"))
        b["qty_processed"] += actual
        b["qty_passed"] += max(0, actual - reject)
        b["qty_failed"] += reject
        b["_refs"].add(r.get("po_number") or r.get("po_id"))
        b["_days"].add(d)

    prog = await db.production_progress.find(
        {"job_id": {"$in": sc["job_ids"]}},
        {"_id": 0, "job_id": 1, "completed_quantity": 1, "progress_date": 1},
    ).to_list(MAX_DOCS) if sc["job_ids"] else []
    for p in prog:
        d = as_iso_date(p.get("progress_date"))
        if not d.startswith(month_str):
            continue
        job = sc["job_by_id"].get(p.get("job_id")) or {}
        qty = _i(p.get("completed_quantity"))
        b = _vendor_bucket(by_vendor, job.get("vendor_id"), job.get("vendor_name"))
        b["qty_processed"] += qty
        b["qty_passed"] += qty
        b["_refs"].add(job.get("job_number") or job.get("po_number"))
        b["_days"].add(d)

    production_by_vendor = []
    for v in by_vendor.values():
        refs = v.pop("_refs")
        days = v.pop("_days")
        proc = v["qty_processed"]
        production_by_vendor.append({
            "cmt_partner_id": v["cmt_partner_id"],
            "cmt_name": v["cmt_name"],
            "total_processed": proc,
            "total_passed": v["qty_passed"],
            "total_failed": v["qty_failed"],
            "pass_rate_pct": round(v["qty_passed"] / proc * 100, 1) if proc else 0,
            "active_days": len(days),
            "jobs_count": len([x for x in refs if x]),
        })

    # Klien maklon — mirror komersial (data nyata)
    pipe_maklon = [
        {"$match": {"po_date": {"$regex": f"^{month_str}"}}},
        {"$group": {
            "_id": {"client_id": "$client_id", "client_name": "$client_name"},
            "po_count": {"$sum": 1},
            "total_qty": {"$sum": "$total_qty"},
            "total_value": {"$sum": "$total_value"},
            "amount_paid": {"$sum": "$amount_paid"},
        }},
    ]
    maklon_result = await db.dewi_maklon_pos.aggregate(pipe_maklon).to_list(MAX_DOCS)
    maklon_by_client = [{
        "client_id": r["_id"].get("client_id"),
        "client_name": r["_id"].get("client_name", "Tanpa nama"),
        "po_count": r["po_count"],
        "total_qty": _i(r.get("total_qty")),
        "total_value": _f(r.get("total_value")),
        "amount_paid": _f(r.get("amount_paid")),
        "outstanding": _f(r.get("total_value")) - _f(r.get("amount_paid")),
    } for r in maklon_result]

    vships = await db.vendor_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}},
        {"_id": 0, "shipment_date": 1, "created_at": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    do_issued = sum(1 for s in vships if as_iso_date(
        s.get("shipment_date") or s.get("created_at")).startswith(month_str))
    do_received = sum(1 for r in receipts
                      if as_iso_date(r.get("receipt_date")).startswith(month_str))

    total_processed = sum(v["total_processed"] for v in production_by_vendor)
    total_passed = sum(v["total_passed"] for v in production_by_vendor)
    total_failed = sum(v["total_failed"] for v in production_by_vendor)

    return {
        "period": month_str,
        "domain": domain,
        "domain_label": domain_label(domain),
        "summary": {
            "total_processed": total_processed,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate_pct": round(total_passed / total_processed * 100, 1) if total_processed else 0,
            "vendor_count": len(production_by_vendor),
            "maklon_po_count": sum(m["po_count"] for m in maklon_by_client),
            "maklon_total_value": sum(m["total_value"] for m in maklon_by_client),
            "do_issued": do_issued,
            "do_received": do_received,
        },
        "production_by_vendor": production_by_vendor,
        "maklon_by_client": maklon_by_client,
        "sources": [
            {"collection": "cmt_receipts", "count": len(receipts), "note": "penerimaan dari CMT"},
            {"collection": "production_progress", "count": len(prog), "note": "progres produksi"},
            {"collection": "dewi_maklon_pos", "count": len(maklon_result), "note": "klien & nilai order"},
            {"collection": "vendor_shipments", "count": len(vships), "note": "surat jalan ke CMT"},
        ],
    }


# ── PER-PO REPORT ──────────────────────────────────────────────────────────────
@router.get("/po/{po_id}")
async def po_report(po_id: str, user: dict = Depends(require_auth)):
    """Detail satu PO maklon: buku kuantitas, pengiriman, AR/GL.

    `po_id` boleh id `dewi_maklon_pos` MAUPUN id `production_pos` (SSOT) — dulu
    hanya menerima id mirror sehingga sering 404 dari layar yang memakai PO SSOT.
    """
    db = get_db()
    mk = await db.dewi_maklon_pos.find_one({"id": po_id}, {"_id": 0})
    prod_po = None
    if mk:
        pid = mk.get("production_po_id")
        if pid:
            prod_po = await db.production_pos.find_one({"id": pid}, {"_id": 0})
        if not prod_po and mk.get("po_number"):
            prod_po = await db.production_pos.find_one({"po_number": mk["po_number"]}, {"_id": 0})
    else:
        prod_po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
        if prod_po:
            mk = await db.dewi_maklon_pos.find_one(
                {"$or": [{"production_po_id": prod_po["id"]},
                         {"po_number": prod_po.get("po_number")}]}, {"_id": 0})
    if not mk and not prod_po:
        raise HTTPException(404, f"PO {po_id} tidak ditemukan")

    header = mk or prod_po
    items = []
    ledger = {k: 0 for k in ("produced", "accepted", "reject", "rework_open", "short_open")}
    target_qty = _i((mk or {}).get("total_qty"))
    dispatch_rows = []
    qty_dispatched_total = 0
    jobs_out = []

    if prod_po:
        from core.production_qty_ledger import po_ledger_totals
        po_items = await db.po_items.find({"po_id": prod_po["id"]}, {"_id": 0}).to_list(MAX_DOCS)
        totals = await po_ledger_totals(db, prod_po["id"])
        t = totals.get("totals") or {}
        ledger = {
            "produced": _i(t.get("produced")), "accepted": _i(t.get("accepted")),
            "reject": _i(t.get("reject")), "rework_open": _i(t.get("rework_open")),
            "short_open": _i(t.get("short_open")),
        }
        target_qty = _i(t.get("ordered")) or sum(_i(x.get("qty")) for x in po_items) or target_qty
        items = [{
            "sku": x.get("sku"), "product_name": x.get("product_name"),
            "size": x.get("size"), "color": x.get("color"), "qty": _i(x.get("qty")),
        } for x in po_items]

        jobs = await db.production_jobs.find(
            {"po_id": prod_po["id"]}, {"_id": 0, "id": 1, "job_number": 1, "status": 1,
                                       "vendor_name": 1, "deadline": 1},
        ).to_list(MAX_DOCS)
        jobs_out = serialize_doc(jobs)

        ships = await db.buyer_shipments.find(
            {"po_id": prod_po["id"]}, {"_id": 0}).to_list(MAX_DOCS)
        sid = [s["id"] for s in ships]
        bsi = await db.buyer_shipment_items.find(
            {"shipment_id": {"$in": sid}}, {"_id": 0},
        ).to_list(MAX_DOCS) if sid else []
        by_ship: dict = {}
        for x in bsi:
            by_ship.setdefault(x.get("shipment_id"), []).append(x)
        for s in ships:
            rows = by_ship.get(s["id"], [])
            qty = sum(_i(x.get("qty_shipped")) for x in rows)
            qty_dispatched_total += qty
            dispatch_rows.append({
                "id": s.get("id"),
                "dispatch_number": s.get("shipment_number"),
                "dispatch_date": max([as_iso_date(x.get("dispatch_date")) for x in rows] or [""])
                                 or as_iso_date(s.get("created_at")),
                "qty": qty,
                "status": s.get("ship_status") or "-",
                "destination": s.get("customer_name") or "-",
            })
        dispatch_rows.sort(key=lambda r: r["dispatch_date"], reverse=True)

    ar = None
    if (mk or {}).get("ar_invoice_id"):
        ar = await db.rahaza_ar_invoices.find_one({"id": mk["ar_invoice_id"]}, {"_id": 0})
        if not ar:
            ar = await db.dewi_maklon_invoices.find_one({"id": mk["ar_invoice_id"]}, {"_id": 0})

    return {
        "po": serialize_doc(header),
        "production_po": serialize_doc(prod_po) if prod_po else None,
        "items": items,
        "jobs": jobs_out,
        "progress": {
            "target_qty": target_qty,
            "qty_produced": ledger["produced"],
            "qty_accepted": ledger["accepted"],
            "qty_reject": ledger["reject"],
            "qty_rework_open": ledger["rework_open"],
            "qty_short_open": ledger["short_open"],
            "qty_dispatched": qty_dispatched_total,
            "qty_remaining": max(0, target_qty - qty_dispatched_total),
            "production_pct": round(ledger["produced"] / target_qty * 100, 1) if target_qty else 0,
            "dispatch_pct": round(qty_dispatched_total / target_qty * 100, 1) if target_qty else 0,
        },
        "dispatches": dispatch_rows,
        "finance": {
            "ar_invoice_id": (mk or {}).get("ar_invoice_id"),
            "ar_invoice_number": (mk or {}).get("ar_invoice_number") or (ar or {}).get("invoice_number"),
            "payment_status": (mk or {}).get("payment_status", "unpaid"),
            "advance_payment": _f((mk or {}).get("advance_payment")),
            "amount_paid": _f((mk or {}).get("amount_paid")),
            "outstanding": _f((mk or {}).get("total_value")) - _f((mk or {}).get("amount_paid")),
            "gl_posted": bool((mk or {}).get("gl_posted_at")),
            "gl_je_id": (mk or {}).get("gl_je_id"),
        },
        "sources": [
            {"collection": "production_pos", "count": 1 if prod_po else 0, "note": "PO SSOT"},
            {"collection": "po_items", "count": len(items), "note": "item PO"},
            {"collection": "production_job_items", "count": len(jobs_out), "note": "buku kuantitas"},
            {"collection": "buyer_shipments", "count": len(dispatch_rows), "note": "kirim ke buyer"},
            {"collection": "dewi_maklon_pos", "count": 1 if mk else 0, "note": "komersial maklon"},
        ],
    }


# ── ACTUAL VS TARGET ───────────────────────────────────────────────────────────
@router.get("/actual-vs-target")
async def actual_vs_target(
    request: Request = None,
    period: str = Query(..., description="Format YYYY-MM untuk monthly"),
    user: dict = Depends(require_auth),
):
    """Realisasi vs target per job produksi & per PO — dari SSOT."""
    db = get_db()
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Format period harus YYYY-MM")
    domain = _dom(request)
    sc = await domain_scope(db, domain)
    per_job = sc["ledger_per_job"]

    cmt_comparison = []
    for j in sc["jobs"]:
        created = as_iso_date(j.get("created_at"))
        deadline = as_iso_date(j.get("deadline") or j.get("delivery_deadline"))
        if not (created.startswith(period) or deadline.startswith(period)):
            continue
        led = per_job.get(j["id"]) or {}
        target = _i(led.get("ordered"))
        actual = _i(led.get("produced"))
        po = sc["po_by_id"].get(j.get("po_id")) or {}
        cmt_comparison.append({
            "job_id": j.get("id"),
            "job_code": j.get("job_number"),
            "product_name": po.get("po_number") or "-",
            "cmt_partner_id": j.get("vendor_id"),
            "cmt_name": j.get("vendor_name") or "Produksi Internal",
            "target": target,
            "actual": actual,
            "accepted": _i(led.get("accepted")),
            "reject": _i(led.get("reject")),
            "variance": actual - target,
            "achievement_pct": round(actual / target * 100, 1) if target else 0,
            "status": j.get("status"),
            "deadline_date": deadline,
        })

    dispatch = await buyer_dispatch_map(db, sc["po_ids"])
    maklon_comparison = []
    for p in sc["pos"]:
        po_date = as_iso_date(p.get("po_date") or p.get("created_at"))
        if not po_date.startswith(period):
            continue
        target = sum(_i(x.get("qty")) for x in sc["items_by_po"].get(p["id"], []))
        actual = (dispatch.get(p["id"]) or {}).get("qty", 0)
        maklon_comparison.append({
            "po_id": p.get("id"),
            "po_number": p.get("po_number"),
            "client_name": p.get("customer_name") or "-",
            "target_qty": target,
            "dispatched_qty": actual,
            "remaining_qty": max(0, target - actual),
            "achievement_pct": round(actual / target * 100, 1) if target else 0,
            "status": p.get("status"),
            "deadline": as_iso_date(p.get("deadline") or p.get("delivery_deadline")),
        })

    return {
        "period": period,
        "domain": domain,
        "domain_label": domain_label(domain),
        "cmt_jobs": cmt_comparison,
        "maklon_pos": maklon_comparison,
        "summary": {
            "cmt_job_count": len(cmt_comparison),
            "cmt_total_target": sum(c["target"] for c in cmt_comparison),
            "cmt_total_actual": sum(c["actual"] for c in cmt_comparison),
            "maklon_po_count": len(maklon_comparison),
            "maklon_total_target": sum(m["target_qty"] for m in maklon_comparison),
            "maklon_total_dispatched": sum(m["dispatched_qty"] for m in maklon_comparison),
        },
        "sources": [
            {"collection": "production_jobs", "count": len(sc["jobs"]), "note": "target & realisasi job"},
            {"collection": "production_pos", "count": len(sc["pos"]), "note": "PO domain"},
            {"collection": "buyer_shipments", "count": len(dispatch), "note": "realisasi kirim"},
        ],
    }


# ── PRODUCTION TREND ───────────────────────────────────────────────────────────
@router.get("/production-trend")
async def production_trend(
    request: Request = None,
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(require_auth),
):
    """Tren produksi N hari terakhir (untuk chart) — dari SSOT."""
    db = get_db()
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    domain = _dom(request)
    sc = await domain_scope(db, domain)

    trend_map = {d.isoformat(): {"date": d.isoformat(), "total_processed": 0,
                                 "total_passed": 0, "total_failed": 0, "dispatched_qty": 0}
                 for d in _date_range(start_date, end_date)}

    receipts = await _receipts_of(db, sc["po_ids"])
    for r in receipts:
        d = as_iso_date(r.get("receipt_date"))
        row = trend_map.get(d)
        if not row:
            continue
        actual = _i(r.get("total_actual"))
        reject = _i(r.get("total_rejected"))
        row["total_processed"] += actual
        row["total_passed"] += max(0, actual - reject)
        row["total_failed"] += reject

    prog = await db.production_progress.find(
        {"job_id": {"$in": sc["job_ids"]}},
        {"_id": 0, "completed_quantity": 1, "progress_date": 1},
    ).to_list(MAX_DOCS) if sc["job_ids"] else []
    for p in prog:
        row = trend_map.get(as_iso_date(p.get("progress_date")))
        if row:
            q = _i(p.get("completed_quantity"))
            row["total_processed"] += q
            row["total_passed"] += q

    if sc["po_ids"]:
        bs = await db.buyer_shipments.find(
            {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "id": 1}).to_list(MAX_DOCS)
        if bs:
            bsi = await db.buyer_shipment_items.find(
                {"shipment_id": {"$in": [b["id"] for b in bs]}},
                {"_id": 0, "qty_shipped": 1, "dispatch_date": 1},
            ).to_list(MAX_DOCS)
            for x in bsi:
                row = trend_map.get(as_iso_date(x.get("dispatch_date")))
                if row:
                    row["dispatched_qty"] += _i(x.get("qty_shipped"))

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "domain": domain,
        "domain_label": domain_label(domain),
        "trend": list(trend_map.values()),
        "sources": [
            {"collection": "cmt_receipts", "count": len(receipts), "note": "penerimaan dari CMT"},
            {"collection": "production_progress", "count": len(prog), "note": "progres produksi"},
        ],
    }


# ── CSV EXPORT ─────────────────────────────────────────────────────────────────
@router.get("/export/daily.csv")
async def export_daily_csv(
    request: Request = None,
    report_date: Optional[str] = Query(None, alias="date"),
    user: dict = Depends(require_auth),
):
    data = await daily_report(request=request, report_date=report_date, user=user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Laporan Harian Produksi"])
    w.writerow(["Tanggal", data["date"]])
    w.writerow(["Domain", data["domain_label"]])
    w.writerow([])
    w.writerow(["RINGKASAN PRODUKSI"])
    w.writerow(["Total Diproses", data["production"]["total_processed"]])
    w.writerow(["Total Lolos QC", data["production"]["total_passed"]])
    w.writerow(["Total Gagal QC", data["production"]["total_failed"]])
    w.writerow(["Pass Rate (%)", data["production"]["pass_rate_pct"]])
    w.writerow([])
    w.writerow(["PER VENDOR"])
    w.writerow(["Vendor", "Diproses", "Lolos", "Gagal", "Jumlah PO/Job"])
    for v in data["production"]["by_vendor"]:
        w.writerow([v["cmt_name"], v["qty_processed"], v["qty_passed"], v["qty_failed"], v["jobs_count"]])
    w.writerow([])
    w.writerow(["PER SUMBER"])
    w.writerow(["Sumber", "Qty"])
    for s in data["production"]["by_step"]:
        w.writerow([s["step"], s["qty"]])
    w.writerow([])
    w.writerow(["PENGIRIMAN"])
    w.writerow(["Surat Jalan ke CMT", data["delivery_orders"]["issued"]])
    w.writerow(["Penerimaan dari CMT", data["delivery_orders"]["received"]])
    w.writerow(["Qty Kirim ke Buyer", data["buyer_delivery"]["qty_today"]])
    w.writerow([])
    w.writerow(["FULFILLMENT ONLINE"])
    w.writerow(["Order Dikirim", data["fulfillment"]["dispatched_orders"]])
    w.writerow(["Qty Dikirim", data["fulfillment"]["dispatched_qty"]])
    w.writerow([])
    w.writerow(["JEJAK SUMBER DATA"])
    w.writerow(["Koleksi", "Jumlah", "Catatan"])
    for s in data["sources"]:
        w.writerow([s["collection"], s["count"], s["note"]])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="laporan-harian-{data["date"]}.csv"'})


@router.get("/export/monthly.csv")
async def export_monthly_csv(
    request: Request = None,
    year: int = Query(...),
    month: int = Query(...),
    user: dict = Depends(require_auth),
):
    data = await monthly_report(request=request, year=year, month=month, user=user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Laporan Bulanan — {data['period']}"])
    w.writerow(["Domain", data["domain_label"]])
    w.writerow([])
    w.writerow(["RINGKASAN"])
    for k, v in data["summary"].items():
        w.writerow([k, v])
    w.writerow([])
    w.writerow(["PRODUKSI PER VENDOR"])
    w.writerow(["Vendor", "Diproses", "Lolos", "Gagal", "Pass Rate %", "Hari Aktif", "PO/Job"])
    for v in data["production_by_vendor"]:
        w.writerow([v["cmt_name"], v["total_processed"], v["total_passed"], v["total_failed"],
                    v["pass_rate_pct"], v["active_days"], v["jobs_count"]])
    w.writerow([])
    w.writerow(["MAKLON PER KLIEN"])
    w.writerow(["Klien", "Jumlah PO", "Total Qty", "Nilai Order", "Terbayar", "Sisa"])
    for m in data["maklon_by_client"]:
        w.writerow([m["client_name"], m["po_count"], m["total_qty"], m["total_value"],
                    m["amount_paid"], m["outstanding"]])
    w.writerow([])
    w.writerow(["JEJAK SUMBER DATA"])
    for s in data["sources"]:
        w.writerow([s["collection"], s["count"], s["note"]])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="laporan-bulanan-{data["period"]}.csv"'})
