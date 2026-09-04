"""
services/cmt_recon.py — READ-ONLY Rekonsiliasi Dispatch (Fase 5 / Konsolidasi).

Tujuan: MENEGASKAN PEMISAHAN PERMANEN dua domain dispatch (INVARIANTS MCS-04) dan
mendeteksi bila terjadi tumpang-tindih (split-brain) agar bisa ditangani manusia.

Dua domain TERPISAH:
  1) MAKLON (pcs/potongan)  = `vendor_shipments`/`vendor_shipment_items` (DA→CMT), ber-serial,
     di-key ke `production_pos` (business_type=maklon). Ini SSOT KPI maklon.
  2) WMS/INTERNAL (meter/roll) = `wh_cmt_dispatches` (dispatch kain ke CMT), di-key ke Work Order.
     TIDAK memberi makan KPI maklon.

Modul ini TIDAK menulis & TIDAK menggabung data. Hanya membaca + memberi verdict.
"""
from typing import Dict, List, Any


def _f(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _int(v) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return int(_f(v))


async def dispatch_reconciliation(db) -> Dict[str, Any]:
    # ── A) Domain MAKLON: vendor_shipments (pcs) ───────────────────────────────
    maklon_pos = await db.production_pos.find(
        {"business_type": "maklon"}, {"_id": 0, "id": 1, "po_number": 1}
    ).to_list(2000)
    maklon_po_ids = {p["id"] for p in maklon_pos}
    po_number_by_id = {p["id"]: p.get("po_number", "") for p in maklon_pos}

    vshipments = await db.vendor_shipments.find(
        {"$or": [{"business_type": "maklon"}, {"po_id": {"$in": list(maklon_po_ids)}}]},
        {"_id": 0, "id": 1, "po_id": 1, "vendor_id": 1, "vendor_name": 1},
    ).to_list(2000)
    vs_ids = [s["id"] for s in vshipments]
    vs_items = []
    if vs_ids:
        vs_items = await db.vendor_shipment_items.find(
            {"shipment_id": {"$in": vs_ids}}, {"_id": 0, "qty_sent": 1}
        ).to_list(10000)
    maklon_domain = {
        "collection": "vendor_shipments",
        "unit": "pcs",
        "shipment_count": len(vshipments),
        "total_pcs_sent": sum(_int(i.get("qty_sent")) for i in vs_items),
        "distinct_po": len({s.get("po_id") for s in vshipments if s.get("po_id")}),
        "distinct_vendor": len({s.get("vendor_id") for s in vshipments if s.get("vendor_id")}),
    }

    # ── B) Domain WMS/INTERNAL: wh_cmt_dispatches (meter) ──────────────────────
    dispatches = await db.wh_cmt_dispatches.find({}, {"_id": 0}).to_list(3000)
    total_meter = 0.0
    for d in dispatches:
        for ln in (d.get("lines") or []):
            total_meter += _f(ln.get("qty"))
    wms_domain = {
        "collection": "wh_cmt_dispatches",
        "unit": "meter",
        "dispatch_count": len(dispatches),
        "total_meter_dispatched": round(total_meter, 2),
        "distinct_wo": len({d.get("wo_id") for d in dispatches if d.get("wo_id")}),
        "distinct_cmt_name": len({(d.get("cmt_name") or "").strip().lower() for d in dispatches if d.get("cmt_name")}),
    }

    # ── C) Deteksi TUMPANG-TINDIH (potensi split-brain) ────────────────────────
    # wh_cmt_dispatches.wo_id → work order/production_job → po_id; jika PO=maklon → overlap.
    overlaps: List[Dict[str, Any]] = []
    wo_ids = [d.get("wo_id") for d in dispatches if d.get("wo_id")]
    wo_to_po: Dict[str, str] = {}
    if wo_ids:
        for coll in ("work_orders", "production_jobs"):
            wos = await db[coll].find(
                {"id": {"$in": wo_ids}}, {"_id": 0, "id": 1, "po_id": 1, "wo_number": 1}
            ).to_list(3000)
            for w in wos:
                if w.get("po_id"):
                    wo_to_po[w["id"]] = w["po_id"]
    for d in dispatches:
        po_id = wo_to_po.get(d.get("wo_id"))
        if po_id and po_id in maklon_po_ids:
            overlaps.append({
                "po_id": po_id,
                "po_number": po_number_by_id.get(po_id, ""),
                "dispatch_no": d.get("dispatch_no", ""),
                "wo_number": d.get("wo_number", ""),
                "cmt_name": d.get("cmt_name", ""),
                "meter": round(sum(_f(ln.get("qty")) for ln in (d.get("lines") or [])), 2),
            })

    # info: nama CMT di WMS yang cocok dengan master vendor_partners (bukan overlap keras)
    partners = await db.vendor_partners.find({}, {"_id": 0, "name": 1}).to_list(500)
    partner_names = {(p.get("name") or "").strip().lower() for p in partners if p.get("name")}
    cmt_name_matches = sorted({
        (d.get("cmt_name") or "").strip() for d in dispatches
        if (d.get("cmt_name") or "").strip().lower() in partner_names
    })

    clean = len(overlaps) == 0
    return {
        "verdict": "separated_clean" if clean else "overlap_detected",
        "verdict_label": (
            "Terpisah bersih — tidak ada tumpang-tindih antar sistem dispatch."
            if clean else
            f"Terdeteksi {len(overlaps)} tumpang-tindih PO maklon di kedua sistem — perlu ditinjau."
        ),
        "maklon_domain": maklon_domain,
        "wms_domain": wms_domain,
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "cmt_name_matches": cmt_name_matches,
        "notes": [
            "Domain MAKLON (pcs) & WMS (meter) sengaja DIPISAH permanen (INVARIANTS MCS-04).",
            "KPI maklon HANYA membaca vendor_shipments/cmt_receipts — tidak dari wh_cmt_dispatches.",
            "Bridge vendor_progress_reports → production_progress SENGAJA TIDAK dibuat (opsi B2-A) untuk mencegah double-count.",
        ],
    }
