"""Dashboard Produksi — agregator satu panggilan yang mengikuti ALUR NYATA pabrik.

Kenyataan 2026 (dikonfirmasi owner): jahit dikerjakan vendor CMT di luar dan
Cutting sudah punya portal sendiri. Karena itu dashboard TIDAK lagi memakai
WIP per proses internal (Cutting→Sewing→Finishing→QC→Packing) yang sudah mati —
angkanya selalu nol dan menyesatkan.

Rantai yang benar:
    Rencana (PO) → Cutting → Di Vendor CMT → Terima & QC → Permak → Serah Terima FG

Satu endpoint dipakai dua portal:
    business_type=internal → Portal Produksi   (serah terima ke inventori sendiri)
    business_type=maklon   → Portal Maklon     (dispatch ke buyer)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import require_auth
from database import get_db

router = APIRouter(prefix="/api/prod", tags=["production-dashboard"])

PLANNING_STATUSES = ["Draft", "Confirmed"]
ACTIVE_STATUSES = ["Draft", "Confirmed", "Distributed", "In Production",
                   "Production Complete", "Variance Review", "Return Review",
                   "Ready to Close"]
CLOSED_STATUSES = ["Closed", "Completed", "Closed Short"]
CUT_ACTIVE = ["draft", "in_progress"]


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


async def _po_scope(db, business_type: str) -> tuple[list, dict]:
    """PO aktif untuk tipe bisnis ini + peta id→dokumen."""
    q = ({"business_type": "internal"} if business_type == "internal"
         else {"business_type": {"$ne": "internal"}})
    pos = await db.production_pos.find(q, {"_id": 0}).to_list(3000)
    return pos, {p["id"]: p for p in pos}


@router.get("/dashboard")
async def production_dashboard(
    business_type: str = Query("internal", pattern="^(internal|maklon)$"),
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(require_auth),
):
    db = get_db()
    since = (date.today() - timedelta(days=days)).isoformat()
    pos, po_map = await _po_scope(db, business_type)
    po_ids = list(po_map.keys())

    # ── PO: hitung per status + qty dari po_items ────────────────────────────
    items = await db.po_items.find({"po_id": {"$in": po_ids}},
                                   {"_id": 0, "po_id": 1, "id": 1, "qty": 1}).to_list(20000)
    qty_by_po: dict[str, int] = {}
    item_ids: list[str] = []
    for it in items:
        qty_by_po[it["po_id"]] = qty_by_po.get(it["po_id"], 0) + _i(it.get("qty"))
        item_ids.append(it["id"])

    by_status: dict[str, dict] = {}
    for p in pos:
        st = p.get("status") or "Draft"
        row = by_status.setdefault(st, {"status": st, "count": 0, "qty": 0})
        row["count"] += 1
        row["qty"] += qty_by_po.get(p["id"], 0)
    po_status = sorted(by_status.values(), key=lambda r: -r["count"])

    aktif = [p for p in pos if p.get("status") in ACTIVE_STATUSES]
    qty_aktif = sum(qty_by_po.get(p["id"], 0) for p in aktif)
    qty_rencana = sum(qty_by_po.get(p["id"], 0) for p in pos if p.get("status") in PLANNING_STATUSES)

    # ── Cutting (portal sendiri, dipakai kedua tipe bisnis) ──────────────────
    cut_rows = await db.cutting_orders.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1},
                    "planned": {"$sum": "$planned_output_qty"},
                    "produced": {"$sum": "$produced_qty"},
                    "consumed": {"$sum": "$consumed_input_qty"},
                    "waste": {"$sum": "$waste_qty"}}},
    ]).to_list(20)
    cut_by_status = {r["_id"]: r for r in cut_rows}
    cut_consumed = sum(_f(r.get("consumed")) for r in cut_rows)
    cut_produced = sum(_f(r.get("produced")) for r in cut_rows)
    cutting = {
        "draft": _i(cut_by_status.get("draft", {}).get("n")),
        "in_progress": _i(cut_by_status.get("in_progress", {}).get("n")),
        "completed": _i(cut_by_status.get("completed", {}).get("n")),
        "qty_dalam_proses": round(sum(_f(cut_by_status.get(s, {}).get("planned")) for s in CUT_ACTIVE)),
        "qty_potongan_jadi": round(cut_produced),
        "kain_terpakai": round(cut_consumed, 2),
        "waste": round(sum(_f(r.get("waste")) for r in cut_rows), 2),
        "rendemen": round(cut_produced / cut_consumed, 3) if cut_consumed > 0 else 0.0,
        "panel_aktif": await db.rahaza_materials.count_documents({"is_cut_panel": True, "active": True}),
    }

    # ── Di vendor CMT: dikirim vs sudah kembali ──────────────────────────────
    vs = await db.vendor_shipments.find({"po_id": {"$in": po_ids}},
                                        {"_id": 0, "id": 1, "status": 1, "vendor_name": 1,
                                         "po_id": 1, "shipment_date": 1}).to_list(5000)
    vs_ids = [s["id"] for s in vs]
    vsi = await db.vendor_shipment_items.aggregate([
        {"$match": {"shipment_id": {"$in": vs_ids}}},
        {"$group": {"_id": "$shipment_id", "sent": {"$sum": "$qty_sent"}}},
    ]).to_list(5000) if vs_ids else []
    sent_by_ship = {r["_id"]: _i(r["sent"]) for r in vsi}

    per_vendor: dict[str, dict] = {}
    qty_terkirim = qty_kembali = 0
    for s in vs:
        q = sent_by_ship.get(s["id"], 0)
        v = per_vendor.setdefault(s.get("vendor_name") or "(tanpa nama)",
                                  {"vendor": s.get("vendor_name") or "(tanpa nama)",
                                   "kirim": 0, "qty_kirim": 0, "qty_kembali": 0})
        v["kirim"] += 1
        v["qty_kirim"] += q
        qty_terkirim += q
        if s.get("status") == "Received":
            v["qty_kembali"] += q
            qty_kembali += q
    for v in per_vendor.values():
        v["outstanding"] = v["qty_kirim"] - v["qty_kembali"]
    vendor = {
        "pengiriman": len(vs),
        "qty_terkirim": qty_terkirim,
        "qty_kembali": qty_kembali,
        "outstanding": qty_terkirim - qty_kembali,
        "per_vendor": sorted(per_vendor.values(), key=lambda v: -v["outstanding"])[:8],
    }

    # ── Terima FG dari CMT + mutu ────────────────────────────────────────────
    rq = {"business_type": "internal"} if business_type == "internal" else {"business_type": {"$ne": "internal"}}
    receipts = await db.cmt_receipts.find(rq, {"_id": 0, "id": 1, "status": 1, "total_actual": 1,
                                               "total_rejected": 1, "approved_at": 1,
                                               "receipt_date": 1, "cmt_name": 1}).to_list(5000)
    today_iso = date.today().isoformat()
    qc = {"draft": 0, "submitted": 0, "approved": 0, "rejected": 0,
          "qty_diterima": 0, "qty_ditolak": 0, "pcs_hari_ini": 0,
          "menunggu_qty": 0, "vendor_aktif": len({r.get("cmt_name") for r in receipts if r.get("cmt_name")})}
    for r in receipts:
        st = (r.get("status") or "Draft").lower()
        qc[st] = qc.get(st, 0) + 1
        ok, rej = _i(r.get("total_actual")), _i(r.get("total_rejected"))
        if st == "approved":
            qc["qty_diterima"] += ok
            qc["qty_ditolak"] += rej
            if str(r.get("approved_at") or "")[:10] == today_iso:
                qc["pcs_hari_ini"] += ok
        elif st in ("draft", "submitted"):
            qc["menunggu_qty"] += ok
    total_periksa = qc["qty_diterima"] + qc["qty_ditolak"]
    qc["tingkat_cacat"] = round(qc["qty_ditolak"] / total_periksa * 100, 2) if total_periksa else 0.0

    # ── Permak / perbaikan ───────────────────────────────────────────────────
    permak_rows = await db.dewi_cmt_permak.aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}, "qty": {"$sum": "$qty"}}},
    ]).to_list(20)
    permak = {"terbuka": 0, "selesai": 0, "qty_terbuka": 0}
    for r in permak_rows:
        st = str(r["_id"] or "").lower()
        if st in ("done", "completed", "selesai", "closed"):
            permak["selesai"] += _i(r["n"])
        else:
            permak["terbuka"] += _i(r["n"])
            permak["qty_terbuka"] += _i(r.get("qty"))

    # ── Serah terima FG / dispatch ke buyer ──────────────────────────────────
    bs = await db.buyer_shipments.find({"po_id": {"$in": po_ids}},
                                       {"_id": 0, "id": 1, "shipment_date": 1}).to_list(5000)
    bs_ids = [s["id"] for s in bs]
    bsi = await db.buyer_shipment_items.aggregate([
        {"$match": {"shipment_id": {"$in": bs_ids}}},
        {"$group": {"_id": None, "qty": {"$sum": "$qty_shipped"}}},
    ]).to_list(1) if bs_ids else []
    recent_ids = [s["id"] for s in bs if str(s.get("shipment_date") or "")[:10] >= since]
    bsi_recent = await db.buyer_shipment_items.aggregate([
        {"$match": {"shipment_id": {"$in": recent_ids}}},
        {"$group": {"_id": None, "qty": {"$sum": "$qty_shipped"}}},
    ]).to_list(1) if recent_ids else []
    handover = {
        "pengiriman": len(bs),
        "qty_total": _i(bsi[0]["qty"]) if bsi else 0,
        "qty_periode": _i(bsi_recent[0]["qty"]) if bsi_recent else 0,
        "label": "Serah Terima FG" if business_type == "internal" else "Dispatch ke Buyer",
    }

    # ── Rantai tahap (untuk visual alur) ─────────────────────────────────────
    pipeline = [
        {"stage": "rencana", "label": "Rencana PO", "qty": qty_rencana,
         "count": sum(1 for p in pos if p.get("status") in PLANNING_STATUSES),
         "module": "prod-pos-internal" if business_type == "internal" else "maklon-pos-engine"},
        {"stage": "cutting", "label": "Cutting", "qty": cutting["qty_dalam_proses"],
         "count": cutting["draft"] + cutting["in_progress"], "module": "cutting-orders"},
        {"stage": "vendor", "label": "Di Vendor CMT", "qty": vendor["outstanding"],
         "count": len(per_vendor), "module": "prod-shipments-vendor"},
        {"stage": "qc", "label": "Terima & QC", "qty": qc["menunggu_qty"],
         "count": qc["draft"] + qc["submitted"], "module": "da-cmt-receive"},
        {"stage": "permak", "label": "Permak", "qty": permak["qty_terbuka"],
         "count": permak["terbuka"], "module": "cmt-permak"},
        {"stage": "kirim", "label": handover["label"], "qty": handover["qty_periode"],
         "count": len(recent_ids),
         "module": "prod-shipments-buyer"},
    ]

    # ── PO tertahan paling lama (bukan bottleneck proses, tapi bottleneck alur) ──
    now = datetime.now(timezone.utc)
    aging = []
    for p in aktif:
        raw = p.get("updated_at") or p.get("created_at")
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            umur = (now - ts).days
        except (TypeError, ValueError):
            umur = 0
        aging.append({"po_id": p["id"], "po_number": p.get("po_number"),
                      "status": p.get("status"), "qty": qty_by_po.get(p["id"], 0),
                      "hari_diam": umur,
                      "deadline": str(p.get("deadline") or "")[:10] or None,
                      "customer": p.get("customer_name") or p.get("vendor_name") or ""})
    aging.sort(key=lambda r: -r["hari_diam"])

    return {
        "business_type": business_type,
        "periode_hari": days,
        "ringkasan": {
            "po_aktif": len(aktif),
            "qty_aktif": qty_aktif,
            "po_selesai": sum(1 for p in pos if p.get("status") in CLOSED_STATUSES),
            "di_vendor": vendor["outstanding"],
            "menunggu_qc": qc["menunggu_qty"],
            "tingkat_cacat": qc["tingkat_cacat"],
            "keluar_periode": handover["qty_periode"],
        },
        "pipeline": pipeline,
        "po_status": po_status,
        "cutting": cutting,
        "vendor": vendor,
        "qc": qc,
        "permak": permak,
        "handover": handover,
        "aging": aging[:8],
        "updated_at": now.isoformat(),
    }
