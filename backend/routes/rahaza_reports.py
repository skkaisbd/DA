from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from datetime import timedelta, datetime
from routes.shared import get_pagination_params, paginated_response
from core import stock_service
# SATU tempat agregasi SSOT — dipakai juga oleh routes/dewi_phase7_reports.py
# supaya tidak lahir sumber kebenaran kedua (lihat services/mgmt_analytics.py).
from services.mgmt_analytics import (
    MAX_DOCS, as_iso_date as _as_iso_date, buyer_dispatch_map, domain_label, domain_scope,
    f as _f, i as _i, in_period as _in_period, norm_domain, po_buckets,
    resolve_period, today as _today,
)

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-reports"])


def _norm_domain(v):
    return norm_domain(v)


def _domain_label(d):
    return domain_label(d)


def _period(request: Request, default_days: int = 30):
    sp = request.query_params
    return resolve_period(sp.get("date_from"), sp.get("date_to"), default_days)


def _po_buckets(pos):
    return po_buckets(pos)


# ═════════════════════════════════════════════════════════════════════════════
# RINGKASAN BISNIS
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/management/overview")
async def overview(request: Request):
    """KPI Ringkasan Bisnis dari SSOT, dipisah per domain, dengan jejak sumber."""
    await require_auth(request)
    db = get_db()
    domain = _norm_domain(request.query_params.get("domain"))
    start, end = _period(request, default_days=30)
    sc = await domain_scope(db, domain)

    qty_ordered = sum(_i(it.get("qty")) for it in sc["items"])
    buckets = _po_buckets(sc["pos"])

    jobs_active = sum(1 for j in sc["jobs"]
                      if (j.get("status") or "").lower() not in ("completed", "closed", "cancelled"))
    jobs_done = sum(1 for j in sc["jobs"]
                    if (j.get("status") or "").lower() in ("completed", "closed"))

    # Output pada periode — internal: catatan progres; maklon: penerimaan dari CMT.
    progress_rows = await db.production_progress.find(
        {"job_id": {"$in": sc["job_ids"]}}, {"_id": 0, "job_id": 1, "completed_quantity": 1,
                                             "progress_date": 1},
    ).to_list(MAX_DOCS) if sc["job_ids"] else []
    output_progress = sum(_i(r.get("completed_quantity")) for r in progress_rows
                          if _in_period(r.get("progress_date"), start, end))

    receipts = await db.cmt_receipts.find(
        {"po_id": {"$in": sc["po_ids"]}},
        {"_id": 0, "id": 1, "po_id": 1, "receipt_date": 1, "status": 1,
         "total_actual": 1, "total_rejected": 1, "total_qty_short": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    receipts_period = [r for r in receipts if _in_period(r.get("receipt_date"), start, end)]
    qty_received = sum(_i(r.get("total_actual")) for r in receipts_period)

    # Pengiriman
    vendor_ship = await db.vendor_shipments.count_documents(
        {"po_id": {"$in": sc["po_ids"]}}) if sc["po_ids"] else 0
    buyer_ship_docs = await db.buyer_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "id": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    bs_ids = [b["id"] for b in buyer_ship_docs]
    bs_items = await db.buyer_shipment_items.find(
        {"shipment_id": {"$in": bs_ids}}, {"_id": 0, "qty_shipped": 1, "dispatch_date": 1},
    ).to_list(MAX_DOCS) if bs_ids else []
    qty_to_buyer = sum(_i(x.get("qty_shipped")) for x in bs_items)

    # Keuangan — AR adalah SSOT GL. Domain: invoice bertaut PO maklon = maklon.
    ar_q = {}
    if domain == "maklon":
        ar_q = {"linked_maklon_po_id": {"$nin": [None, ""]}}
    elif domain == "internal":
        ar_q = {"$or": [{"linked_maklon_po_id": {"$in": [None, ""]}},
                        {"linked_maklon_po_id": {"$exists": False}}]}
    ar_rows = await db.rahaza_ar_invoices.find(
        ar_q, {"_id": 0, "total_amount": 1, "amount_paid": 1, "amount_due": 1,
               "status": 1, "invoice_date": 1, "due_date": 1},
    ).to_list(MAX_DOCS)
    ar_invoiced = sum(_f(r.get("total_amount")) for r in ar_rows)
    ar_paid = sum(_f(r.get("amount_paid")) for r in ar_rows)
    ar_outstanding = sum(
        _f(r.get("amount_due")) if r.get("amount_due") is not None
        else _f(r.get("total_amount")) - _f(r.get("amount_paid"))
        for r in ar_rows
        if (r.get("status") or "").lower() not in ("paid", "cancelled", "void"))
    today_iso = _today().isoformat()
    ar_overdue = sum(
        1 for r in ar_rows
        if (r.get("status") or "").lower() not in ("paid", "cancelled", "void")
        and _as_iso_date(r.get("due_date")) and _as_iso_date(r.get("due_date")) < today_iso)

    mk_inv_count = 0
    mk_inv_value = 0.0
    if domain in ("maklon", "all"):
        mk_inv = await db.dewi_maklon_invoices.find(
            {}, {"_id": 0, "total_amount": 1}).to_list(MAX_DOCS)
        mk_inv_count = len(mk_inv)
        mk_inv_value = sum(_f(r.get("total_amount")) for r in mk_inv)

    # Gudang — pembaca kanonik stok (bukan koleksi legacy).
    mats = await db.rahaza_materials.find(
        {"active": {"$ne": False}},
        {"_id": 0, "id": 1, "min_stock": 1, "min_stock_qty": 1},
    ).to_list(MAX_DOCS)
    onhand = await stock_service.onhand_map(db=db)
    low_count = 0
    for m in mats:
        minv = m.get("min_stock_qty")
        if minv in (None, ""):
            minv = m.get("min_stock")
        minv = _f(minv)
        if minv > 0 and _f(onhand.get(m["id"])) < minv:
            low_count += 1

    # SDM
    emp_active = await db.rahaza_employees.count_documents({"active": True})
    att = await db.rahaza_attendance_events.aggregate([
        {"$match": {"date": today_iso}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(200)
    att_summary = {(a["_id"] or "lain"): a["count"] for a in att}

    lg = sc["ledger"]
    produced = lg["produced"]
    accepted = lg["accepted"]
    reject = lg["reject"]

    return {
        "domain": domain,
        "domain_label": _domain_label(domain),
        "date_from": start,
        "date_to": end,
        "orders": {**buckets, "qty_ordered": qty_ordered},
        "production": {
            "jobs_total": len(sc["jobs"]),
            "jobs_active": jobs_active,
            "jobs_done": jobs_done,
            "qty_produced": produced,
            "qty_accepted": accepted,
            "qty_reject": reject,
            "qty_rework_open": lg["rework_open"],
            "qty_short_open": lg["short_open"],
            "reject_rate_pct": round(reject / produced * 100, 1) if produced else 0.0,
            "accept_rate_pct": round(accepted / produced * 100, 1) if produced else 0.0,
            "output_period": output_progress + qty_received,
            "output_progress_period": output_progress,
            "output_received_period": qty_received,
            "fulfilment_pct": round(accepted / qty_ordered * 100, 1) if qty_ordered else 0.0,
        },
        "delivery": {
            "vendor_shipments": vendor_ship,
            "buyer_shipments": len(buyer_ship_docs),
            "qty_shipped_to_buyer": qty_to_buyer,
            "cmt_receipts": len(receipts),
            "cmt_receipts_period": len(receipts_period),
        },
        "finance": {
            "ar_invoices": len(ar_rows),
            "ar_invoiced": round(ar_invoiced),
            "ar_paid": round(ar_paid),
            "ar_outstanding": round(ar_outstanding),
            "ar_overdue_count": ar_overdue,
            "maklon_invoices": mk_inv_count,
            "maklon_invoiced_value": round(mk_inv_value),
        },
        "warehouse": {
            "materials_tracked": len(mats),
            "low_stock_materials": low_count,
        },
        "hr": {
            "employees_active": emp_active,
            "attendance_today": att_summary,
        },
        "sources": [
            {"collection": "production_pos", "count": len(sc["pos"]), "note": f"PO domain {domain}"},
            {"collection": "po_items", "count": len(sc["items"]), "note": "item PO (qty pesan)"},
            {"collection": "production_jobs", "count": len(sc["jobs"]), "note": "pelaksanaan"},
            {"collection": "production_job_items", "count": len(sc["job_items"]),
             "note": "buku kuantitas (ledger_view)"},
            {"collection": "production_progress", "count": len(progress_rows),
             "note": "progres internal pada periode"},
            {"collection": "cmt_receipts", "count": len(receipts), "note": "penerimaan dari CMT"},
            {"collection": "buyer_shipments", "count": len(buyer_ship_docs), "note": "kirim ke buyer"},
            {"collection": "rahaza_ar_invoices", "count": len(ar_rows), "note": "AR (SSOT GL)"},
            {"collection": "rahaza_materials", "count": len(mats), "note": "master material aktif"},
        ],
    }


@router.get("/management/daily-output")
async def daily_output(request: Request, days: int = Query(7, ge=1, le=365)):
    """Output per hari. Internal = catatan progres · Maklon = penerimaan dari CMT."""
    await require_auth(request)
    db = get_db()
    domain = _norm_domain(request.query_params.get("domain"))
    sp = request.query_params
    if sp.get("date_from") and sp.get("date_to"):
        start, end = _period(request)
    else:
        today = _today()
        start = (today - timedelta(days=days - 1)).isoformat()
        end = today.isoformat()
    sd = datetime.fromisoformat(start).date()
    ed = datetime.fromisoformat(end).date()
    span = max(1, (ed - sd).days + 1)
    if span > 365:
        raise HTTPException(400, "Rentang maksimal 365 hari.")
    dates = [(sd + timedelta(days=i)).isoformat() for i in range(span)]
    timeline = {d: {"date": d, "total": 0, "internal": 0, "maklon": 0} for d in dates}

    sc = await domain_scope(db, domain)
    job_domain = {j["id"]: (j.get("business_type") or "internal") for j in sc["jobs"]}

    prog = await db.production_progress.find(
        {"job_id": {"$in": sc["job_ids"]}},
        {"_id": 0, "job_id": 1, "completed_quantity": 1, "progress_date": 1},
    ).to_list(MAX_DOCS) if sc["job_ids"] else []
    for r in prog:
        d = _as_iso_date(r.get("progress_date"))
        if d in timeline:
            q = _i(r.get("completed_quantity"))
            timeline[d]["total"] += q
            key = "internal" if job_domain.get(r.get("job_id")) == "internal" else "maklon"
            timeline[d][key] += q

    rec = await db.cmt_receipts.find(
        {"po_id": {"$in": sc["po_ids"]}},
        {"_id": 0, "receipt_date": 1, "total_actual": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    for r in rec:
        d = _as_iso_date(r.get("receipt_date"))
        if d in timeline:
            q = _i(r.get("total_actual"))
            timeline[d]["total"] += q
            timeline[d]["maklon"] += q

    return {
        "domain": domain, "domain_label": _domain_label(domain),
        "days": span, "date_from": start, "date_to": end,
        "timeline": list(timeline.values()),
        "sources": [
            {"collection": "production_progress", "count": len(prog), "note": "progres internal"},
            {"collection": "cmt_receipts", "count": len(rec), "note": "penerimaan maklon"},
        ],
    }


@router.get("/management/top-models")
async def top_models(request: Request, limit: int = Query(10, ge=1, le=200)):
    """Produk teratas: qty dipesan (po_items) vs qty diterima (buku kuantitas)."""
    await require_auth(request)
    db = get_db()
    domain = _norm_domain(request.query_params.get("domain"))
    sc = await domain_scope(db, domain)
    per_item = sc["ledger_per_item"]
    agg: dict = {}
    for it in sc["items"]:
        key = it.get("sku") or it.get("product_name") or it.get("id")
        row = agg.setdefault(key, {
            "sku": it.get("sku") or "-", "name": it.get("product_name") or "-",
            "qty": 0, "accepted": 0, "orders": 0,
        })
        row["qty"] += _i(it.get("qty"))
        row["orders"] += 1
        led = per_item.get(it["id"])
        if led:
            row["accepted"] += led["accepted"]
    out = sorted(agg.values(), key=lambda r: -r["qty"])[:limit]
    for r in out:
        r["code"] = r["sku"]
        r["progress_pct"] = round(r["accepted"] / r["qty"] * 100, 1) if r["qty"] else 0.0
    return {"domain": domain, "domain_label": _domain_label(domain), "items": out,
            "sources": [{"collection": "po_items", "count": len(sc["items"]),
                         "note": "qty pesan per SKU"}]}


@router.get("/management/top-customers")
async def top_customers(request: Request, limit: int = Query(10, ge=1, le=200)):
    """Pelanggan/klien teratas berdasarkan qty PO (+ nilai order untuk maklon)."""
    await require_auth(request)
    db = get_db()
    domain = _norm_domain(request.query_params.get("domain"))
    sc = await domain_scope(db, domain)

    # Nilai komersial maklon ada di mirror `dewi_maklon_pos` (total_value).
    value_by_po: dict = {}
    if domain in ("maklon", "all"):
        async for m in db.dewi_maklon_pos.find(
                {}, {"_id": 0, "production_po_id": 1, "po_number": 1, "total_value": 1,
                     "client_name": 1}):
            if m.get("production_po_id"):
                value_by_po[m["production_po_id"]] = m
            if m.get("po_number"):
                value_by_po.setdefault(f"num:{m['po_number']}", m)

    agg: dict = {}
    for p in sc["pos"]:
        mk = value_by_po.get(p["id"]) or value_by_po.get(f"num:{p.get('po_number')}") or {}
        name = p.get("customer_name") or mk.get("client_name") or "(tanpa nama)"
        row = agg.setdefault(name, {"name": name, "orders": 0, "total_qty": 0, "total_value": 0.0})
        row["orders"] += 1
        row["total_qty"] += sum(_i(it.get("qty")) for it in sc["items_by_po"].get(p["id"], []))
        row["total_value"] += _f(mk.get("total_value"))
    out = sorted(agg.values(), key=lambda r: -r["total_qty"])[:limit]
    for r in out:
        r["total_value"] = round(r["total_value"])
    return {"domain": domain, "domain_label": _domain_label(domain), "items": out,
            "sources": [
                {"collection": "production_pos", "count": len(sc["pos"]), "note": "PO per pelanggan"},
                {"collection": "dewi_maklon_pos", "count": len(value_by_po),
                 "note": "nilai order maklon"},
            ]}


@router.get("/management/on-time-delivery")
async def on_time_delivery(request: Request, days: int = Query(90, ge=1, le=3650)):
    """Ketepatan kirim: tanggal dispatch terakhir ke buyer vs deadline PO."""
    await require_auth(request)
    db = get_db()
    domain = _norm_domain(request.query_params.get("domain"))
    sc = await domain_scope(db, domain)
    since = (_today() - timedelta(days=days)).isoformat()

    ships = await db.buyer_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "id": 1, "po_id": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    ship_po = {s["id"]: s.get("po_id") for s in ships}
    items = await db.buyer_shipment_items.find(
        {"shipment_id": {"$in": list(ship_po.keys())}},
        {"_id": 0, "shipment_id": 1, "dispatch_date": 1, "qty_shipped": 1},
    ).to_list(MAX_DOCS) if ship_po else []

    last_dispatch: dict = {}
    for it in items:
        d = _as_iso_date(it.get("dispatch_date"))
        if not d or d < since:
            continue
        po_id = ship_po.get(it.get("shipment_id"))
        if not po_id:
            continue
        if d > last_dispatch.get(po_id, ""):
            last_dispatch[po_id] = d

    total = 0
    on_time = 0
    late_rows = []
    for po_id, d in last_dispatch.items():
        po = sc["po_by_id"].get(po_id) or {}
        due = _as_iso_date(po.get("deadline") or po.get("delivery_deadline"))
        if not due:
            continue  # tanpa deadline → tidak bisa dinilai (jangan dipaksa)
        total += 1
        if d <= due:
            on_time += 1
        else:
            late_rows.append({"po_number": po.get("po_number"), "deadline": due, "dispatch": d})
    rate = (on_time / total * 100) if total else 0.0
    return {
        "domain": domain, "domain_label": _domain_label(domain), "days": days,
        "total_po": total, "on_time": on_time, "late": total - on_time,
        "rate_pct": round(rate, 1),
        "measurable_note": "Hanya PO yang punya deadline DAN sudah dikirim ke buyer yang dinilai.",
        "late_examples": late_rows[:5],
        "sources": [
            {"collection": "buyer_shipments", "count": len(ships), "note": "pengiriman ke buyer"},
            {"collection": "buyer_shipment_items", "count": len(items), "note": "tanggal dispatch"},
        ],
    }


@router.get("/management/payroll-summary")
async def payroll_summary(request: Request):
    await require_auth(request)
    db = get_db()
    latest = await db.rahaza_payroll_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return {"latest_run": serialize_doc(latest) if latest else None}


# ═════════════════════════════════════════════════════════════════════════════
# LAPORAN TABEL (dipakai ReportsModule — "Laporan Umum")
# ═════════════════════════════════════════════════════════════════════════════
REPORT_TYPES = ("production", "progress", "financial", "shipment", "rework",
                "material-issue", "per-po")


@router.get("/reports/{report_type}")
async def get_rahaza_report(report_type: str, request: Request):
    """Laporan tabel dari SSOT.

    Query: domain=internal|maklon|all · date_from · date_to · page · limit
    Tanpa `page`/`limit` → array (kompatibel pemakai lama).
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    domain = _norm_domain(sp.get("domain"))
    date_from = sp.get("date_from") or ""
    date_to = sp.get("date_to") or ""
    use_pagination = "page" in sp or "limit" in sp
    page = limit = skip = 0
    if use_pagination:
        page, limit, skip = get_pagination_params(request, default_limit=50)

    def in_range(v) -> bool:
        d = _as_iso_date(v)
        if date_from and (not d or d < date_from):
            return False
        if date_to and (not d or d > date_to):
            return False
        return True

    def out(rows: list):
        rows = serialize_doc(rows)
        if use_pagination:
            return paginated_response(rows[skip:skip + limit], len(rows), page, limit)
        return rows

    if report_type not in REPORT_TYPES:
        raise HTTPException(404, f"Jenis laporan '{report_type}' tidak dikenal. "
                                 f"Pilihan: {', '.join(REPORT_TYPES)}")

    sc = await domain_scope(db, domain)
    per_item = sc["ledger_per_item"]

    # ── PRODUKSI: PO + item + buku kuantitas ────────────────────────────────
    if report_type == "production":
        rows = []
        for p in sc["pos"]:
            if not in_range(p.get("po_date") or p.get("created_at")):
                continue
            for it in sc["items_by_po"].get(p["id"], []):
                led = per_item.get(it["id"]) or {}
                qty = _i(it.get("qty"))
                acc = _i(led.get("accepted"))
                rows.append({
                    "tanggal": _as_iso_date(p.get("po_date") or p.get("created_at")),
                    "no_po": p.get("po_number", ""),
                    "domain": "Internal" if (p.get("business_type") == "internal") else "Maklon",
                    "pelanggan": p.get("customer_name", "") or "-",
                    "vendor": p.get("vendor_name", "") or "-",
                    "sku": it.get("sku", "") or "-",
                    "produk": it.get("product_name", "") or "-",
                    "ukuran": it.get("size", "") or "-",
                    "warna": it.get("color", "") or "-",
                    "qty_pesan": qty,
                    "qty_produksi": _i(led.get("produced")),
                    "qty_diterima": acc,
                    "qty_reject": _i(led.get("reject")),
                    "pct_selesai": round(acc / qty * 100, 1) if qty else 0.0,
                    "status_po": p.get("status", ""),
                    "deadline": _as_iso_date(p.get("deadline") or p.get("delivery_deadline")),
                })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── PROGRES: catatan progres produksi internal ──────────────────────────
    if report_type == "progress":
        prog = await db.production_progress.find(
            {"job_id": {"$in": sc["job_ids"]}}, {"_id": 0},
        ).to_list(MAX_DOCS) if sc["job_ids"] else []
        rows = []
        for r in prog:
            if not in_range(r.get("progress_date")):
                continue
            job = sc["job_by_id"].get(r.get("job_id")) or {}
            po = sc["po_by_id"].get(job.get("po_id")) or {}
            rows.append({
                "tanggal": _as_iso_date(r.get("progress_date")),
                "no_job": job.get("job_number", "") or "-",
                "no_po": job.get("po_number", "") or po.get("po_number", "") or "-",
                "pelanggan": po.get("customer_name", "") or "-",
                "pelaksana": job.get("vendor_name", "") or "Produksi Internal",
                "sku": r.get("sku", "") or "-",
                "produk": r.get("product_name", "") or "-",
                "ukuran": r.get("size", "") or "-",
                "warna": r.get("color", "") or "-",
                "qty": _i(r.get("completed_quantity")),
                "dicatat_oleh": r.get("recorded_by", "") or "-",
                "catatan": r.get("notes", "") or "",
            })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── KEUANGAN: AR invoice (SSOT GL) ──────────────────────────────────────
    if report_type == "financial":
        ar_q = {}
        if domain == "maklon":
            ar_q = {"linked_maklon_po_id": {"$nin": [None, ""]}}
        elif domain == "internal":
            ar_q = {"$or": [{"linked_maklon_po_id": {"$in": [None, ""]}},
                            {"linked_maklon_po_id": {"$exists": False}}]}
        invs = await db.rahaza_ar_invoices.find(ar_q, {"_id": 0}).to_list(MAX_DOCS)
        rows = []
        for inv in invs:
            if not in_range(inv.get("invoice_date")):
                continue
            total = _f(inv.get("total_amount"))
            paid = _f(inv.get("amount_paid"))
            rows.append({
                "tanggal": _as_iso_date(inv.get("invoice_date")),
                "no_invoice": inv.get("invoice_number", ""),
                "pelanggan": inv.get("customer_name", "") or "-",
                "no_po_maklon": inv.get("linked_maklon_po_number", "") or "-",
                "subtotal": _f(inv.get("subtotal")),
                "pajak": _f(inv.get("tax_amount")),
                "total": total,
                "terbayar": paid,
                "sisa": _f(inv.get("amount_due")) if inv.get("amount_due") is not None else total - paid,
                "status": inv.get("status", ""),
                "jatuh_tempo": _as_iso_date(inv.get("due_date")),
                "sumber": inv.get("source_module", "") or "-",
            })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── PENGIRIMAN: surat jalan ke buyer ────────────────────────────────────
    if report_type == "shipment":
        ships = await db.buyer_shipments.find(
            {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0},
        ).to_list(MAX_DOCS) if sc["po_ids"] else []
        sid = [s["id"] for s in ships]
        items = await db.buyer_shipment_items.find(
            {"shipment_id": {"$in": sid}}, {"_id": 0},
        ).to_list(MAX_DOCS) if sid else []
        by_ship: dict = {}
        for it in items:
            by_ship.setdefault(it.get("shipment_id"), []).append(it)
        rows = []
        for s in ships:
            sit = by_ship.get(s["id"], [])
            dispatch = max([_as_iso_date(x.get("dispatch_date")) for x in sit] or [""])
            tanggal = dispatch or _as_iso_date(s.get("created_at"))
            if not in_range(tanggal):
                continue
            po = sc["po_by_id"].get(s.get("po_id")) or {}
            rows.append({
                "tanggal": tanggal,
                "no_pengiriman": s.get("shipment_number", ""),
                "no_po": s.get("po_number", "") or po.get("po_number", "") or "-",
                "pelanggan": s.get("customer_name", "") or po.get("customer_name", "") or "-",
                "vendor": s.get("vendor_name", "") or "-",
                "baris": len(sit),
                "qty": sum(_i(x.get("qty_shipped")) for x in sit),
                "qty_fg_keluar": sum(_i(x.get("fg_issued_qty")) for x in sit),
                "status": s.get("ship_status", "") or "-",
                "catatan": s.get("notes", "") or "",
            })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── REWORK / QC GAGAL: baris penerimaan CMT yang direject ───────────────
    if report_type == "rework":
        receipts = await db.cmt_receipts.find(
            {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0},
        ).to_list(MAX_DOCS) if sc["po_ids"] else []
        rid = [r["id"] for r in receipts]
        rec_by_id = {r["id"]: r for r in receipts}
        lines = await db.cmt_receipt_lines.find(
            {"receipt_id": {"$in": rid}}, {"_id": 0},
        ).to_list(MAX_DOCS) if rid else []
        permaks = await db.dewi_cmt_permak.find({}, {"_id": 0}).to_list(MAX_DOCS)
        permak_by_item: dict = {}
        for pk in permaks:
            key = pk.get("job_item_id") or pk.get("po_item_id")
            if key:
                permak_by_item.setdefault(key, []).append(pk)
        rows = []
        for ln in lines:
            if _i(ln.get("reject_qty")) <= 0:
                continue
            rec = rec_by_id.get(ln.get("receipt_id")) or {}
            tanggal = _as_iso_date(rec.get("receipt_date") or rec.get("created_at"))
            if not in_range(tanggal):
                continue
            pk = (permak_by_item.get(ln.get("job_item_id"))
                  or permak_by_item.get(ln.get("po_item_id")) or [])
            rows.append({
                "tanggal": tanggal,
                "no_penerimaan": rec.get("receipt_code", "") or "-",
                "no_po": rec.get("po_number", "") or "-",
                "vendor_cmt": rec.get("cmt_name", "") or "-",
                "sku": ln.get("sku_code", "") or "-",
                "produk": ln.get("product_name", "") or "-",
                "ukuran": ln.get("size", "") or "-",
                "warna": ln.get("color", "") or "-",
                "qty_diterima": _i(ln.get("qty_actual")),
                "qty_reject": _i(ln.get("reject_qty")),
                "alasan_reject": ln.get("reject_reason", "") or "-",
                "tindak_lanjut": (pk[0].get("permak_number") if pk else "belum diputuskan"),
                "status_permak": (pk[0].get("status") if pk else "-"),
                "status_penerimaan": rec.get("status", "") or "-",
            })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── PERMINTAAN MATERIAL ─────────────────────────────────────────────────
    if report_type == "material-issue":
        mi_q = {}
        if domain != "all" and sc["po_ids"]:
            mi_q = {"production_po_id": {"$in": sc["po_ids"]}}
        mis = await db.rahaza_material_issues.find(mi_q, {"_id": 0}).to_list(MAX_DOCS)
        rows = []
        for mi in mis:
            tanggal = _as_iso_date(mi.get("issued_at") or mi.get("created_at"))
            if not in_range(tanggal):
                continue
            po = sc["po_by_id"].get(mi.get("production_po_id")) or {}
            its = mi.get("items") or []
            if not its:
                its = [{}]
            for it in its:
                rows.append({
                    "tanggal": tanggal,
                    "no_mi": mi.get("mi_number", "") or "-",
                    "no_po": mi.get("po_number_snapshot", "") or po.get("po_number", "") or "-",
                    "no_job": mi.get("job_number_snapshot", "") or "-",
                    "material": it.get("material_name") or it.get("material_code") or "-",
                    "qty_diminta": _f(it.get("qty_required") or it.get("qty_requested")),
                    "qty_dikeluarkan": _f(it.get("qty_issued")),
                    "satuan": it.get("unit") or it.get("input_uom") or "-",
                    "status": mi.get("status", "") or "-",
                    "dibuat_oleh": mi.get("created_by_name", "") or "-",
                    "catatan": mi.get("notes", "") or "",
                })
        rows.sort(key=lambda r: r["tanggal"], reverse=True)
        return out(rows)

    # ── PER PO: satu baris per PO + buku kuantitas + status hilir ───────────
    # (dulu FE mengirim array kosong ⇒ laporan ini SELALU kosong)
    receipts = await db.cmt_receipts.find(
        {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "po_id": 1, "total_actual": 1,
                                           "total_rejected": 1, "status": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    rec_by_po: dict = {}
    for r in receipts:
        rec_by_po.setdefault(r.get("po_id"), []).append(r)
    ships = await db.buyer_shipments.find(
        {"po_id": {"$in": sc["po_ids"]}}, {"_id": 0, "id": 1, "po_id": 1},
    ).to_list(MAX_DOCS) if sc["po_ids"] else []
    ship_po = {s["id"]: s.get("po_id") for s in ships}
    bs_items = await db.buyer_shipment_items.find(
        {"shipment_id": {"$in": list(ship_po.keys())}},
        {"_id": 0, "shipment_id": 1, "qty_shipped": 1},
    ).to_list(MAX_DOCS) if ship_po else []
    shipped_by_po: dict = {}
    for it in bs_items:
        po_id = ship_po.get(it.get("shipment_id"))
        if po_id:
            shipped_by_po[po_id] = shipped_by_po.get(po_id, 0) + _i(it.get("qty_shipped"))
    jobs_by_po: dict = {}
    for j in sc["jobs"]:
        jobs_by_po.setdefault(j.get("po_id"), []).append(j)
    mk_value: dict = {}
    async for m in db.dewi_maklon_pos.find({}, {"_id": 0, "production_po_id": 1, "po_number": 1,
                                                "total_value": 1, "payment_status": 1}):
        if m.get("production_po_id"):
            mk_value[m["production_po_id"]] = m
        if m.get("po_number"):
            mk_value.setdefault(f"num:{m['po_number']}", m)

    rows = []
    for p in sc["pos"]:
        tanggal = _as_iso_date(p.get("po_date") or p.get("created_at"))
        if not in_range(tanggal):
            continue
        its = sc["items_by_po"].get(p["id"], [])
        qty = sum(_i(it.get("qty")) for it in its)
        agg = {k: 0 for k in ("produced", "accepted", "reject", "rework_open", "short_open")}
        for it in its:
            led = per_item.get(it["id"])
            if led:
                for k in agg:
                    agg[k] += _i(led.get(k))
        mk = mk_value.get(p["id"]) or mk_value.get(f"num:{p.get('po_number')}") or {}
        rows.append({
            "tanggal": tanggal,
            "no_po": p.get("po_number", ""),
            "domain": "Internal" if (p.get("business_type") == "internal") else "Maklon",
            "pelanggan": p.get("customer_name", "") or "-",
            "status_po": p.get("status", ""),
            "deadline": _as_iso_date(p.get("deadline") or p.get("delivery_deadline")),
            "baris_item": len(its),
            "qty_pesan": qty,
            "qty_produksi": agg["produced"],
            "qty_diterima": agg["accepted"],
            "qty_reject": agg["reject"],
            "qty_rework_terbuka": agg["rework_open"],
            "qty_selisih_kirim": agg["short_open"],
            "qty_kirim_buyer": shipped_by_po.get(p["id"], 0),
            "jumlah_job": len(jobs_by_po.get(p["id"], [])),
            "jumlah_penerimaan": len(rec_by_po.get(p["id"], [])),
            "pct_selesai": round(agg["accepted"] / qty * 100, 1) if qty else 0.0,
            "nilai_order": _f(mk.get("total_value")),
            "status_bayar": mk.get("payment_status", "") or "-",
        })
    rows.sort(key=lambda r: r["tanggal"], reverse=True)
    return out(rows)


# ═════════════════════════════════════════════════════════════════════════════
# PUSAT LAPORAN (Reports Hub) — data penting tiap portal, dipilih per kategori
#
# Dulu "Pusat Laporan" hanya katalog tautan statis: owner bilang "saya malah
# tidak mengerti menu ini, yang ada malah direct ke portal lain". Sekarang tiap
# kategori mengembalikan KPI + tabel data NYATA dari SSOT, dan tautan modul
# hanya sebagai tindak lanjut (bukan satu-satunya isi).
#
# Kontrak generik supaya UI bisa merender apa saja tanpa hardcode:
#   { category, label, description, kpis[], tables[], sources[] }
# ═════════════════════════════════════════════════════════════════════════════
HUB_CATEGORIES = [
    {"id": "eksekutif", "label": "Eksekutif", "portal": "management",
     "description": "Ringkasan lintas divisi: PO, output, piutang, dan risiko keterlambatan."},
    {"id": "produksi_internal", "label": "Produksi Internal DA", "portal": "production",
     "description": "Job produksi sendiri: target, realisasi, reject, dan progres harian."},
    {"id": "maklon", "label": "Maklon", "portal": "maklon",
     "description": "Order klien maklon: nilai order, pembayaran, penerimaan dari CMT."},
    {"id": "gudang", "label": "Gudang", "portal": "warehouse",
     "description": "Stok material, material di bawah minimum, dan pengeluaran ke produksi."},
    {"id": "keuangan", "label": "Keuangan", "portal": "finance",
     "description": "Invoice AR, piutang belum tertagih, dan tagihan jatuh tempo."},
    {"id": "sdm", "label": "SDM / HRIS", "portal": "hr",
     "description": "Karyawan aktif, kehadiran hari ini, dan jam kerja."},
    {"id": "rnd", "label": "RnD & Desain", "portal": "rnd",
     "description": "Style dalam pengembangan dan yang menunggu keputusan manajemen."},
    {"id": "marketing", "label": "Marketing / Toko", "portal": "toko",
     "description": "Order online: omzet, status pengiriman, dan produk terlaris."},
]


def _kpi(label, value, fmt="number", sub="", tone="primary"):
    return {"label": label, "value": value, "format": fmt, "sub": sub, "tone": tone}


def _table(tid, title, subtitle, columns, rows, module_id="", module_label="", empty_hint=""):
    return {"id": tid, "title": title, "subtitle": subtitle, "columns": columns,
            "rows": rows, "module_id": module_id, "module_label": module_label,
            "empty_hint": empty_hint}


@router.get("/reports-hub/categories")
async def reports_hub_categories(request: Request):
    await require_auth(request)
    return {"items": HUB_CATEGORIES}


@router.get("/reports-hub/summary")
async def reports_hub_summary(request: Request):
    """Data penting satu kategori/portal: KPI + tabel relevan, semuanya dari SSOT."""
    await require_auth(request)
    db = get_db()
    cat = (request.query_params.get("category") or "eksekutif").strip().lower()
    meta = next((c for c in HUB_CATEGORIES if c["id"] == cat), None)
    if not meta:
        raise HTTPException(404, f"Kategori '{cat}' tidak dikenal. "
                                 f"Pilihan: {', '.join(c['id'] for c in HUB_CATEGORIES)}")
    start, end = _period(request, default_days=30)
    today_iso = _today().isoformat()
    kpis: list = []
    tables: list = []
    sources: list = []

    # ── EKSEKUTIF ──────────────────────────────────────────────────────────
    if cat == "eksekutif":
        sc = await domain_scope(db, "all")
        lg = sc["ledger"]
        qty_ordered = sum(_i(x.get("qty")) for x in sc["items"])
        buckets = po_buckets(sc["pos"])
        dispatch = await buyer_dispatch_map(db, sc["po_ids"])
        ar = await db.rahaza_ar_invoices.find(
            {}, {"_id": 0, "invoice_number": 1, "customer_name": 1, "total_amount": 1,
                 "amount_paid": 1, "amount_due": 1, "status": 1, "due_date": 1},
        ).to_list(MAX_DOCS)
        outstanding = sum(
            _f(r.get("amount_due")) if r.get("amount_due") is not None
            else _f(r.get("total_amount")) - _f(r.get("amount_paid"))
            for r in ar if (r.get("status") or "").lower() not in ("paid", "cancelled", "void"))
        kpis = [
            _kpi("PO Berjalan", buckets["running"], "number",
                 f"dari {buckets['total']} PO", "primary"),
            _kpi("Qty Dipesan", qty_ordered, "number", "pcs di seluruh PO", "info"),
            _kpi("Sudah Diterima", lg["accepted"], "number",
                 f"dari {lg['produced']} pcs diproduksi", "success"),
            _kpi("Reject Terbuka", lg["reject"], "number",
                 f"{lg['rework_open']} pcs menunggu permak", "warning"),
            _kpi("Kirim ke Buyer", sum(v["qty"] for v in dispatch.values()), "number",
                 f"{len(dispatch)} PO sudah dikirim", "info"),
            _kpi("Piutang Belum Tertagih", round(outstanding), "currency",
                 f"{len(ar)} invoice", "danger" if outstanding else "success"),
        ]
        # PO berisiko: deadline lewat / dekat tapi belum selesai
        risk = []
        for p in sc["pos"]:
            st = (p.get("status") or "").lower()
            if st in ("closed", "completed", "cancelled", "draft"):
                continue
            due = _as_iso_date(p.get("deadline") or p.get("delivery_deadline"))
            if not due:
                continue
            its = sc["items_by_po"].get(p["id"], [])
            qty = sum(_i(x.get("qty")) for x in its)
            acc = sum(_i((sc["ledger_per_item"].get(x["id"]) or {}).get("accepted")) for x in its)
            sisa_hari = (datetime.fromisoformat(due).date() - _today()).days
            if sisa_hari > 14:
                continue
            risk.append({
                "no_po": p.get("po_number"), "pelanggan": p.get("customer_name") or "-",
                "domain": "Internal" if p.get("business_type") == "internal" else "Maklon",
                "deadline": due, "sisa_hari": sisa_hari,
                "qty_pesan": qty, "qty_diterima": acc,
                "kurang": max(0, qty - acc), "status": p.get("status"),
            })
        risk.sort(key=lambda r: r["sisa_hari"])
        tables.append(_table(
            "po-risiko", "PO Perlu Perhatian",
            "Deadline lewat atau kurang dari 14 hari, tapi barang belum lengkap diterima",
            [{"key": "no_po", "label": "NO PO"}, {"key": "domain", "label": "DOMAIN"},
             {"key": "pelanggan", "label": "PELANGGAN"},
             {"key": "deadline", "label": "DEADLINE", "format": "date"},
             {"key": "sisa_hari", "label": "SISA HARI", "format": "number"},
             {"key": "qty_pesan", "label": "PESAN", "format": "number"},
             {"key": "qty_diterima", "label": "DITERIMA", "format": "number"},
             {"key": "kurang", "label": "KURANG", "format": "number"},
             {"key": "status", "label": "STATUS"}],
            risk[:10], "prod-monitoring", "Buka Tracking Produksi",
            "Tidak ada PO yang mendekati atau melewati deadline. "
            "PO tanpa deadline tidak ikut dinilai."))
        outstanding_rows = sorted(
            [{"no_invoice": r.get("invoice_number"), "pelanggan": r.get("customer_name") or "-",
              "total": _f(r.get("total_amount")), "terbayar": _f(r.get("amount_paid")),
              "sisa": (_f(r.get("amount_due")) if r.get("amount_due") is not None
                       else _f(r.get("total_amount")) - _f(r.get("amount_paid"))),
              "jatuh_tempo": _as_iso_date(r.get("due_date")), "status": r.get("status")}
             for r in ar if (r.get("status") or "").lower() not in ("paid", "cancelled", "void")],
            key=lambda r: -r["sisa"])
        tables.append(_table(
            "ar-outstanding", "Piutang Terbesar", "Invoice yang belum lunas",
            [{"key": "no_invoice", "label": "NO INVOICE"}, {"key": "pelanggan", "label": "PELANGGAN"},
             {"key": "total", "label": "TOTAL", "format": "currency"},
             {"key": "terbayar", "label": "TERBAYAR", "format": "currency"},
             {"key": "sisa", "label": "SISA", "format": "currency"},
             {"key": "jatuh_tempo", "label": "JATUH TEMPO", "format": "date"},
             {"key": "status", "label": "STATUS"}],
            outstanding_rows[:10], "fin-ar-360", "Buka Piutang (AR)",
            "Semua invoice sudah lunas."))
        sources = [
            {"collection": "production_pos", "count": len(sc["pos"]), "note": "PO semua domain"},
            {"collection": "production_job_items", "count": len(sc["job_items"]), "note": "buku kuantitas"},
            {"collection": "rahaza_ar_invoices", "count": len(ar), "note": "piutang"},
        ]

    # ── PRODUKSI INTERNAL / MAKLON ─────────────────────────────────────────
    elif cat in ("produksi_internal", "maklon"):
        domain = "internal" if cat == "produksi_internal" else "maklon"
        sc = await domain_scope(db, domain)
        lg = sc["ledger"]
        per_job = sc["ledger_per_job"]
        qty_ordered = sum(_i(x.get("qty")) for x in sc["items"])
        buckets = po_buckets(sc["pos"])
        jobs_active = sum(1 for j in sc["jobs"]
                          if (j.get("status") or "").lower() not in ("completed", "closed", "cancelled"))
        receipts = await db.cmt_receipts.find(
            {"po_id": {"$in": sc["po_ids"]}},
            {"_id": 0, "receipt_code": 1, "po_number": 1, "cmt_name": 1, "receipt_date": 1,
             "status": 1, "total_actual": 1, "total_rejected": 1, "total_qty_short": 1},
        ).to_list(MAX_DOCS) if sc["po_ids"] else []
        dispatch = await buyer_dispatch_map(db, sc["po_ids"])

        kpis = [
            _kpi("PO Berjalan", buckets["running"], "number", f"dari {buckets['total']} PO", "primary"),
            _kpi("Job Aktif", jobs_active, "number", f"dari {len(sc['jobs'])} job", "info"),
            _kpi("Qty Dipesan", qty_ordered, "number", "pcs", "info"),
            _kpi("Diproduksi", lg["produced"], "number", f"{lg['accepted']} diterima", "success"),
            _kpi("Reject", lg["reject"], "number",
                 f"{round(lg['reject'] / lg['produced'] * 100, 1) if lg['produced'] else 0}% dari produksi",
                 "warning"),
            _kpi("Kirim ke Buyer", sum(v["qty"] for v in dispatch.values()), "number",
                 f"{len(dispatch)} PO", "info"),
        ]
        job_rows = []
        for j in sc["jobs"]:
            led = per_job.get(j["id"]) or {}
            ordered = _i(led.get("ordered"))
            produced = _i(led.get("produced"))
            job_rows.append({
                "no_job": j.get("job_number"), "no_po": j.get("po_number"),
                "pelaksana": j.get("vendor_name") or "Produksi Internal",
                "status": j.get("status"),
                "target": ordered, "produksi": produced,
                "diterima": _i(led.get("accepted")), "reject": _i(led.get("reject")),
                "pct": round(produced / ordered * 100, 1) if ordered else 0.0,
                "deadline": _as_iso_date(j.get("deadline") or j.get("delivery_deadline")),
            })
        job_rows.sort(key=lambda r: (r["status"] or "", -r["pct"]))
        tables.append(_table(
            "job-list", "Job Produksi", "Target vs realisasi per job (buku kuantitas SSOT)",
            [{"key": "no_job", "label": "NO JOB"}, {"key": "no_po", "label": "NO PO"},
             {"key": "pelaksana", "label": "PELAKSANA"}, {"key": "status", "label": "STATUS"},
             {"key": "target", "label": "TARGET", "format": "number"},
             {"key": "produksi", "label": "PRODUKSI", "format": "number"},
             {"key": "diterima", "label": "DITERIMA", "format": "number"},
             {"key": "reject", "label": "REJECT", "format": "number"},
             {"key": "pct", "label": "%", "format": "number"},
             {"key": "deadline", "label": "DEADLINE", "format": "date"}],
            job_rows[:10], "prod-monitoring", "Buka Tracking Produksi",
            "Belum ada job. Job terbentuk setelah PO dikonfirmasi lalu didistribusi "
            "ke pelaksana (internal atau vendor CMT)."))
        rec_rows = sorted([{
            "no_penerimaan": r.get("receipt_code"), "no_po": r.get("po_number"),
            "vendor": r.get("cmt_name") or "-",
            "tanggal": _as_iso_date(r.get("receipt_date")),
            "diterima": _i(r.get("total_actual")), "reject": _i(r.get("total_rejected")),
            "selisih_kirim": _i(r.get("total_qty_short")), "status": r.get("status"),
        } for r in receipts], key=lambda r: r["tanggal"], reverse=True)
        tables.append(_table(
            "penerimaan", "Penerimaan Barang dari Pelaksana",
            "Hasil QC saat barang masuk kembali ke DA",
            [{"key": "no_penerimaan", "label": "NO PENERIMAAN"}, {"key": "no_po", "label": "NO PO"},
             {"key": "vendor", "label": "PELAKSANA"},
             {"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "diterima", "label": "DITERIMA", "format": "number"},
             {"key": "reject", "label": "REJECT", "format": "number"},
             {"key": "selisih_kirim", "label": "SELISIH KIRIM", "format": "number"},
             {"key": "status", "label": "STATUS"}],
            rec_rows[:10], "da-cmt-receive", "Buka Terima FG dari CMT",
            "Belum ada penerimaan barang untuk domain ini."))
        sources = [
            {"collection": "production_pos", "count": len(sc["pos"]), "note": f"PO {domain}"},
            {"collection": "production_jobs", "count": len(sc["jobs"]), "note": "pelaksanaan"},
            {"collection": "cmt_receipts", "count": len(receipts), "note": "penerimaan"},
        ]

    # ── GUDANG ─────────────────────────────────────────────────────────────
    elif cat == "gudang":
        mats = await db.rahaza_materials.find(
            {"active": {"$ne": False}},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1,
             "min_stock": 1, "min_stock_qty": 1},
        ).to_list(MAX_DOCS)
        onhand = await stock_service.onhand_map(db=db)
        low_rows = []
        for m in mats:
            minv = m.get("min_stock_qty")
            if minv in (None, ""):
                minv = m.get("min_stock")
            minv = _f(minv)
            cur = _f(onhand.get(m["id"]))
            if minv > 0 and cur < minv:
                low_rows.append({"kode": m.get("code"), "material": m.get("name"),
                                 "jenis": m.get("type") or "-", "satuan": m.get("unit") or "-",
                                 "stok": cur, "minimum": minv, "kurang": round(minv - cur, 2)})
        low_rows.sort(key=lambda r: -r["kurang"])
        bins_used = await db.wh_positions.count_documents({"qty": {"$gt": 0}})
        bins_total = await db.wh_positions.count_documents({})
        mis = await db.rahaza_material_issues.find({}, {"_id": 0}).to_list(MAX_DOCS)
        mi_rows = sorted([{
            "no_mi": m.get("mi_number"), "no_po": m.get("po_number_snapshot") or "-",
            "no_job": m.get("job_number_snapshot") or "-",
            "tanggal": _as_iso_date(m.get("issued_at") or m.get("created_at")),
            "baris": len(m.get("items") or []),
            "status": m.get("status") or "-",
            "dibuat_oleh": m.get("created_by_name") or "-",
        } for m in mis], key=lambda r: r["tanggal"], reverse=True)
        stock_value = sum(_f(onhand.get(m["id"])) for m in mats)
        kpis = [
            _kpi("Material Aktif", len(mats), "number", "master material", "primary"),
            _kpi("Di Bawah Minimum", len(low_rows), "number", "perlu restock",
                 "danger" if low_rows else "success"),
            _kpi("Total Kuantitas Stok", round(stock_value, 2), "number",
                 "gabungan semua satuan dasar", "info"),
            _kpi("Bin Terpakai", bins_used, "number", f"dari {bins_total} bin", "info"),
            _kpi("Pengeluaran Material", len(mis), "number", "dokumen MI", "info"),
        ]
        tables.append(_table(
            "low-stock", "Material di Bawah Stok Minimum", "Diurutkan dari kekurangan terbesar",
            [{"key": "kode", "label": "KODE"}, {"key": "material", "label": "MATERIAL"},
             {"key": "jenis", "label": "JENIS"},
             {"key": "stok", "label": "STOK", "format": "number"},
             {"key": "minimum", "label": "MINIMUM", "format": "number"},
             {"key": "kurang", "label": "KURANG", "format": "number"},
             {"key": "satuan", "label": "SATUAN"}],
            low_rows[:10], "wh-materials", "Buka Master Material",
            "Semua material di atas stok minimum. Material tanpa nilai minimum "
            "tidak ikut dinilai."))
        tables.append(_table(
            "material-issue", "Pengeluaran Material Terbaru", "Material yang keluar ke job produksi",
            [{"key": "no_mi", "label": "NO MI"}, {"key": "no_po", "label": "NO PO"},
             {"key": "no_job", "label": "NO JOB"},
             {"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "baris", "label": "BARIS", "format": "number"},
             {"key": "status", "label": "STATUS"}, {"key": "dibuat_oleh", "label": "DIBUAT OLEH"}],
            mi_rows[:10], "wh-material-issue", "Buka Pengeluaran Material",
            "Belum ada pengeluaran material."))
        sources = [
            {"collection": "rahaza_materials", "count": len(mats), "note": "master aktif"},
            {"collection": "rahaza_material_stock", "count": len(onhand), "note": "stok on-hand"},
            {"collection": "wh_positions", "count": bins_total, "note": "bin gudang"},
            {"collection": "rahaza_material_issues", "count": len(mis), "note": "pengeluaran"},
        ]

    # ── KEUANGAN ───────────────────────────────────────────────────────────
    elif cat == "keuangan":
        ar = await db.rahaza_ar_invoices.find({}, {"_id": 0}).to_list(MAX_DOCS)
        mk_inv = await db.dewi_maklon_invoices.find({}, {"_id": 0}).to_list(MAX_DOCS)
        invoiced = sum(_f(r.get("total_amount")) for r in ar)
        paid = sum(_f(r.get("amount_paid")) for r in ar)
        open_rows = [r for r in ar if (r.get("status") or "").lower() not in ("paid", "cancelled", "void")]
        outstanding = sum(
            _f(r.get("amount_due")) if r.get("amount_due") is not None
            else _f(r.get("total_amount")) - _f(r.get("amount_paid")) for r in open_rows)
        overdue = [r for r in open_rows
                   if _as_iso_date(r.get("due_date")) and _as_iso_date(r.get("due_date")) < today_iso]
        kpis = [
            _kpi("Total Ditagihkan", round(invoiced), "currency", f"{len(ar)} invoice AR", "primary"),
            _kpi("Sudah Dibayar", round(paid), "currency",
                 f"{round(paid / invoiced * 100, 1) if invoiced else 0}% tertagih", "success"),
            _kpi("Belum Tertagih", round(outstanding), "currency",
                 f"{len(open_rows)} invoice terbuka", "warning"),
            _kpi("Jatuh Tempo", len(overdue), "number", "invoice lewat tanggal", 
                 "danger" if overdue else "success"),
            _kpi("Tagihan Maklon", round(sum(_f(r.get("total_amount")) for r in mk_inv)), "currency",
                 f"{len(mk_inv)} dokumen (modul maklon)", "info"),
        ]
        tables.append(_table(
            "ar", "Invoice AR", "Semua invoice piutang, terbaru di atas",
            [{"key": "no_invoice", "label": "NO INVOICE"}, {"key": "pelanggan", "label": "PELANGGAN"},
             {"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "total", "label": "TOTAL", "format": "currency"},
             {"key": "terbayar", "label": "TERBAYAR", "format": "currency"},
             {"key": "sisa", "label": "SISA", "format": "currency"},
             {"key": "jatuh_tempo", "label": "JATUH TEMPO", "format": "date"},
             {"key": "status", "label": "STATUS"}],
            sorted([{
                "no_invoice": r.get("invoice_number"), "pelanggan": r.get("customer_name") or "-",
                "tanggal": _as_iso_date(r.get("invoice_date")),
                "total": _f(r.get("total_amount")), "terbayar": _f(r.get("amount_paid")),
                "sisa": (_f(r.get("amount_due")) if r.get("amount_due") is not None
                         else _f(r.get("total_amount")) - _f(r.get("amount_paid"))),
                "jatuh_tempo": _as_iso_date(r.get("due_date")), "status": r.get("status"),
            } for r in ar], key=lambda r: r["tanggal"], reverse=True)[:10],
            "fin-ar-360", "Buka Piutang (AR)", "Belum ada invoice AR."))
        tables.append(_table(
            "maklon-inv", "Tagihan Maklon", "Dokumen tagihan dari modul maklon",
            [{"key": "no_invoice", "label": "NO"}, {"key": "klien", "label": "KLIEN"},
             {"key": "no_order", "label": "NO ORDER"},
             {"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "total", "label": "TOTAL", "format": "currency"},
             {"key": "terbayar", "label": "TERBAYAR", "format": "currency"},
             {"key": "status", "label": "STATUS"}],
            sorted([{
                "no_invoice": r.get("invoice_number") or r.get("invoice_code"),
                "klien": r.get("client_name") or "-", "no_order": r.get("order_code") or "-",
                "tanggal": _as_iso_date(r.get("invoice_date")),
                "total": _f(r.get("total_amount")), "terbayar": _f(r.get("amount_paid")),
                "status": r.get("status"),
            } for r in mk_inv], key=lambda r: r["tanggal"], reverse=True)[:10],
            "maklon-billing", "Buka Penagihan Maklon", "Belum ada tagihan maklon."))
        sources = [
            {"collection": "rahaza_ar_invoices", "count": len(ar), "note": "SSOT piutang"},
            {"collection": "dewi_maklon_invoices", "count": len(mk_inv), "note": "tagihan maklon"},
        ]

    # ── SDM ────────────────────────────────────────────────────────────────
    elif cat == "sdm":
        emps = await db.rahaza_employees.find({}, {"_id": 0}).to_list(MAX_DOCS)
        active = [e for e in emps if e.get("active")]
        att_today = await db.rahaza_attendance_events.find(
            {"date": today_iso}, {"_id": 0}).to_list(MAX_DOCS)
        att_period = await db.rahaza_attendance_events.find(
            {"date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(MAX_DOCS)
        hours = sum(_f(a.get("hours_worked")) for a in att_period)
        overtime = sum(_f(a.get("overtime_hours")) for a in att_period)
        by_status: dict = {}
        for a in att_today:
            k = a.get("status") or "lain"
            by_status[k] = by_status.get(k, 0) + 1
        emp_name = {e["id"]: e.get("name") for e in emps}
        kpis = [
            _kpi("Karyawan Aktif", len(active), "number", f"dari {len(emps)} terdaftar", "primary"),
            _kpi("Hadir Hari Ini", sum(by_status.values()), "number",
                 " · ".join(f"{k}: {v}" for k, v in by_status.items()) or "belum ada absensi", "info"),
            _kpi("Jam Kerja Periode", round(hours, 1), "number", f"{start} → {end}", "success"),
            _kpi("Jam Lembur", round(overtime, 1), "number", "pada periode yang sama", "warning"),
        ]
        tables.append(_table(
            "absen", "Absensi Periode", "Catatan kehadiran pada periode terpilih",
            [{"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "karyawan", "label": "KARYAWAN"}, {"key": "status", "label": "STATUS"},
             {"key": "masuk", "label": "MASUK"}, {"key": "keluar", "label": "KELUAR"},
             {"key": "jam", "label": "JAM KERJA", "format": "number"},
             {"key": "lembur", "label": "LEMBUR", "format": "number"}],
            sorted([{
                "tanggal": a.get("date"), "karyawan": emp_name.get(a.get("employee_id")) or "-",
                "status": a.get("status") or "-",
                "masuk": str(a.get("clock_in") or "-")[:16], "keluar": str(a.get("clock_out") or "-")[:16],
                "jam": _f(a.get("hours_worked")), "lembur": _f(a.get("overtime_hours")),
            } for a in att_period], key=lambda r: r["tanggal"] or "", reverse=True)[:10],
            "hr-attendance", "Buka Absensi", "Belum ada catatan absensi pada periode ini."))
        tables.append(_table(
            "karyawan", "Karyawan Aktif", "Master karyawan",
            [{"key": "kode", "label": "KODE"}, {"key": "nama", "label": "NAMA"},
             {"key": "peran", "label": "PERAN"},
             {"key": "gabung", "label": "TANGGAL GABUNG", "format": "date"}],
            [{"kode": e.get("employee_code"), "nama": e.get("name"),
              "peran": e.get("role_hint") or "-", "gabung": _as_iso_date(e.get("join_date"))}
             for e in active][:10],
            "hr-employees", "Buka Data Karyawan", "Belum ada karyawan aktif."))
        sources = [
            {"collection": "rahaza_employees", "count": len(emps), "note": "master karyawan"},
            {"collection": "rahaza_attendance_events", "count": len(att_period), "note": "absensi periode"},
        ]

    # ── RND ────────────────────────────────────────────────────────────────
    elif cat == "rnd":
        styles = await db.dewi_rnd_styles.find({}, {"_id": 0}).to_list(MAX_DOCS)
        samples = await db.dewi_rnd_sample_requests.find({}, {"_id": 0}).to_list(MAX_DOCS)
        by_status: dict = {}
        for s_ in styles:
            k = (s_.get("status") or "draft")
            by_status[k] = by_status.get(k, 0) + 1
        pending = [s_ for s_ in styles if (s_.get("status") or "") == "pending_owner_review"]
        promoted = [s_ for s_ in styles if s_.get("promoted_to_model_id")]
        kpis = [
            _kpi("Total Style", len(styles), "number",
                 " · ".join(f"{k}: {v}" for k, v in by_status.items()) or "-", "primary"),
            _kpi("Menunggu Keputusan", len(pending), "number", "butuh review manajemen",
                 "warning" if pending else "success"),
            _kpi("Naik ke Produksi", len(promoted), "number", "sudah jadi model produksi", "success"),
            _kpi("Permintaan Sample", len(samples), "number", "seluruh status", "info"),
        ]
        tables.append(_table(
            "style", "Style RnD", "Status pengembangan desain",
            [{"key": "kode", "label": "KODE"}, {"key": "nama", "label": "NAMA STYLE"},
             {"key": "jenis", "label": "JENIS"}, {"key": "klien", "label": "KLIEN/BUYER"},
             {"key": "status", "label": "STATUS"},
             {"key": "dibuat", "label": "DIBUAT", "format": "date"}],
            sorted([{
                "kode": s_.get("style_code"), "nama": s_.get("style_name"),
                "jenis": s_.get("rnd_type") or "-",
                "klien": s_.get("client_name") or s_.get("buyer") or "-",
                "status": s_.get("status") or "draft",
                "dibuat": _as_iso_date(s_.get("created_at")),
            } for s_ in styles], key=lambda r: r["dibuat"], reverse=True)[:10],
            "rnd-styles", "Buka Style RnD", "Belum ada style RnD."))
        sources = [
            {"collection": "dewi_rnd_styles", "count": len(styles), "note": "style desain"},
            {"collection": "dewi_rnd_sample_requests", "count": len(samples), "note": "permintaan sample"},
        ]

    # ── MARKETING ──────────────────────────────────────────────────────────
    else:
        orders = await db.marketing_orders.find({}, {"_id": 0}).to_list(MAX_DOCS)
        in_period_rows = [o for o in orders
                          if _in_period(o.get("order_date") or o.get("created_at"), start, end)]
        revenue = sum(_f(o.get("revenue") or o.get("price_final")) for o in in_period_rows)
        qty = sum(_i(o.get("quantity")) for o in in_period_rows)
        by_status: dict = {}
        for o in in_period_rows:
            k = o.get("fulfillment_status") or "belum diproses"
            by_status[k] = by_status.get(k, 0) + 1
        by_product: dict = {}
        for o in in_period_rows:
            k = o.get("product_name") or "-"
            row = by_product.setdefault(k, {"produk": k, "qty": 0, "omzet": 0.0, "order": 0})
            row["qty"] += _i(o.get("quantity"))
            row["omzet"] += _f(o.get("revenue") or o.get("price_final"))
            row["order"] += 1
        kpis = [
            _kpi("Order Periode", len(in_period_rows), "number", f"{start} → {end}", "primary"),
            _kpi("Omzet Periode", round(revenue), "currency", f"{qty} pcs terjual", "success"),
            _kpi("Total Order", len(orders), "number", "seluruh riwayat", "info"),
            _kpi("Status Pengiriman", len(by_status), "number",
                 " · ".join(f"{k}: {v}" for k, v in by_status.items()) or "-", "info"),
        ]
        tables.append(_table(
            "top-produk", "Produk Terlaris", "Berdasarkan omzet pada periode terpilih",
            [{"key": "produk", "label": "PRODUK"}, {"key": "order", "label": "ORDER", "format": "number"},
             {"key": "qty", "label": "QTY", "format": "number"},
             {"key": "omzet", "label": "OMZET", "format": "currency"}],
            sorted(by_product.values(), key=lambda r: -r["omzet"])[:10],
            "marketing-catalog", "Buka Katalog", "Belum ada order pada periode ini."))
        tables.append(_table(
            "order-terbaru", "Order Terbaru", "Order online paling baru",
            [{"key": "tanggal", "label": "TANGGAL", "format": "date"},
             {"key": "no_order", "label": "NO ORDER"}, {"key": "platform", "label": "PLATFORM"},
             {"key": "pelanggan", "label": "PELANGGAN"}, {"key": "produk", "label": "PRODUK"},
             {"key": "qty", "label": "QTY", "format": "number"},
             {"key": "omzet", "label": "OMZET", "format": "currency"},
             {"key": "status", "label": "STATUS"}],
            sorted([{
                "tanggal": _as_iso_date(o.get("order_date") or o.get("created_at")),
                "no_order": o.get("order_id") or "-", "platform": o.get("platform") or "-",
                "pelanggan": o.get("customer_name") or "-", "produk": o.get("product_name") or "-",
                "qty": _i(o.get("quantity")),
                "omzet": _f(o.get("revenue") or o.get("price_final")),
                "status": o.get("fulfillment_status") or "belum diproses",
            } for o in orders], key=lambda r: r["tanggal"], reverse=True)[:10],
            "marketing-orders", "Buka Order Marketing", "Belum ada order online."))
        sources = [{"collection": "marketing_orders", "count": len(orders), "note": "order online"}]

    return {
        "category": meta["id"], "label": meta["label"], "portal": meta["portal"],
        "description": meta["description"],
        "date_from": start, "date_to": end,
        "kpis": kpis, "tables": tables, "sources": sources,
    }


# ═════════════════════════════════════════════════════════════════════════════
# PERINGATAN OTOMATIS UNTUK MANAJEMEN
# Permintaan owner: "kirim notifikasi ke manajemen saat ada PO mendekati deadline
# atau piutang jatuh tempo". Logika di services/management_alerts.py (dipakai
# scheduler harian 07:00 juga), di sini hanya pintu untuk melihat & memicu manual.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/management/alerts")
async def management_alerts_preview(request: Request):
    """Pratinjau peringatan (tidak menulis notifikasi).

    Tanpa `warn_days`, ambang diambil dari konfigurasi owner (PO & AR terpisah).
    """
    await require_auth(request)
    from services.management_alerts import scan_management_alerts
    warn = request.query_params.get("warn_days")
    warn_days = None
    if warn not in (None, ""):
        try:
            warn_days = int(warn)
        except (TypeError, ValueError):
            raise HTTPException(400, "warn_days harus angka.")
        if not 0 <= warn_days <= 60:
            raise HTTPException(400, "warn_days harus 0..60.")
    return await scan_management_alerts(get_db(), warn_days=warn_days, dry_run=True)


# Ambang peringatan yang bisa diatur owner (2026-08-07)
@router.get("/management/alert-config")
async def get_management_alert_config(request: Request):
    """Ambang aktif: berapa hari sebelum tenggat PO / jatuh tempo piutang diperingatkan."""
    await require_auth(request)
    from services.management_alerts import get_alert_config
    return await get_alert_config(get_db())


@router.put("/management/alert-config")
async def put_management_alert_config(request: Request):
    """Simpan ambang peringatan (dipakai penjadwal harian 07:00 & layar pratinjau)."""
    from routes.shared import require_perm
    user = await require_perm(request, "report.view", "dashboard.view",
                              legacy_roles=("manager", "owner", "accounting", "manager_keuangan",
                                            "admin_produksi", "supervisor_produksi", "admin_maklon"),
                              message="Akses ditolak: butuh izin melihat laporan manajemen.")
    from services.management_alerts import save_alert_config
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    try:
        return await save_alert_config(get_db(), body, user if isinstance(user, dict) else None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/management/alerts/scan")
async def management_alerts_scan(request: Request):
    """Jalankan pemindaian & kirim notifikasi sekarang (idempoten per hari)."""
    from routes.shared import require_perm
    await require_perm(request, "report.view", "dashboard.view",
                       legacy_roles=("manager", "owner", "accounting", "manager_keuangan",
                                     "admin_produksi", "supervisor_produksi", "admin_maklon"),
                       message="Akses ditolak: butuh izin melihat laporan manajemen.")
    from services.management_alerts import scan_management_alerts
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    warn_days = body.get("warn_days")
    if warn_days not in (None, ""):
        try:
            warn_days = int(warn_days)
        except (TypeError, ValueError):
            raise HTTPException(400, "warn_days harus angka.")
    else:
        warn_days = None
    return await scan_management_alerts(get_db(), warn_days=warn_days, dry_run=False)