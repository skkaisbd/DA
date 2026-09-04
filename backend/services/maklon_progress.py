"""
services/maklon_progress.py — Canonical multi-state qty-progress for Maklon PO.

WHY: Progress lama (`progress_pct = Σ production_job_items.produced_qty / Σ po_items.qty`)
tidak mencerminkan penerimaan aktual dari CMT (`cmt_receipt_lines`), permak/rework, maupun
dispatch ke buyer → sering mismatch. Service ini menghitung SATU sumber kebenaran (SSOT)
per PO item lalu meng-agregat ke PO.

SSOT yang dibaca (semua ber-`po_item_id` = `po_items.id`):
- po_items                      → qty_ordered
- production_job_items          → qty_produced   (dipertahankan utk backward-compat progress_pct)
- cmt_receipt_lines (receipt Approved) → qty_returned_cmt / qty_accepted / qty_reject_qc
- dewi_cmt_permak               → rework open/fixed/scrap (mengurangi FG)
- buyer_shipment_items          → qty_dispatched / qty_received_buyer

Model FG (Barang Jadi) — rework MENGURANGI FG saat masih open, dan scrap permanen:
  qty_good = qty_accepted
             + Σ(fixed  | source=reject)     # reject direpair → jadi good baru
             - Σ(qty    | source=good, WIP)   # good ditarik utk permak (belum kembali)
             - Σ(scrap  | source=good)        # good hilang permanen
  qty_good_ready = qty_good - qty_dispatched

Backward-compat: caller tetap boleh pakai `progress_pct` (produced-based, tak berubah).
"""
from typing import Dict, List, Any, Optional, Iterable
from core.cmt_receipt_status import (ST_DONE as _RC_DONE,
                                    canon_status_filter as _rc_filter)

# Status permak
PERMAK_ACTIVE = ("open", "in_progress")
PERMAK_SUCCESS = "selesai_berhasil"
PERMAK_SCRAP = "gagal_buang"
PERMAK_ALL_STATUSES = ("open", "in_progress", PERMAK_SUCCESS, PERMAK_SCRAP)


def _int(v) -> int:
    try:
        if v is None:
            return 0
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0


def _pct(part: int, whole: int) -> float:
    return round((part / whole) * 100, 1) if whole > 0 else 0.0


async def _approved_receipt_ids(db, po_id: str) -> List[str]:
    docs = await db.cmt_receipts.find(
        {"po_id": po_id, "status": _rc_filter(_RC_DONE)}, {"_id": 0, "id": 1}
    ).to_list(None)
    return [d["id"] for d in docs if d.get("id")]


def _blank_item_state() -> Dict[str, int]:
    return {
        "qty_ordered": 0,
        "qty_produced": 0,
        "qty_returned_cmt": 0,
        "qty_accepted": 0,
        "qty_reject_qc": 0,
        "qty_rework_open": 0,
        "qty_rework_fixed": 0,
        "qty_scrap": 0,
        "qty_dispatched": 0,
        "qty_received_buyer": 0,
        # good accounting deltas (internal, source-aware)
        "_good_delta": 0,
    }


def _finalize_item(state: Dict[str, int]) -> Dict[str, Any]:
    """Compute derived good/ready + pct for a single item state dict."""
    accepted = state["qty_accepted"]
    good = accepted + state["_good_delta"]
    good = max(0, good)
    dispatched = state["qty_dispatched"]
    good_ready = max(0, good - dispatched)
    ordered = state["qty_ordered"]
    out = {k: v for k, v in state.items() if not k.startswith("_")}
    out["qty_good"] = good
    out["qty_good_ready"] = good_ready
    out["qty_outstanding"] = max(0, ordered - dispatched)
    out["progress_pct"] = _pct(state["qty_produced"], ordered)      # backward-compat (produced)
    out["delivery_pct"] = _pct(state["qty_received_buyer"], ordered)
    out["good_pct"] = _pct(good, ordered)
    out["dispatch_pct"] = _pct(dispatched, ordered)
    return out


def _apply_permak(state: Dict[str, int], p: Dict[str, Any]) -> None:
    """Fold one permak record into an item state (source-aware FG accounting)."""
    status = p.get("status", "open")
    source = p.get("source", "reject")
    qty = _int(p.get("qty"))
    qty_fixed = _int(p.get("qty_fixed"))
    qty_scrap = _int(p.get("qty_scrap"))

    if status in PERMAK_ACTIVE:
        state["qty_rework_open"] += qty
        if source == "good":
            state["_good_delta"] -= qty            # good ditarik keluar (WIP)
        # source=reject saat WIP: belum good, tak ada delta
    elif status == PERMAK_SUCCESS:
        state["qty_rework_fixed"] += qty_fixed
        state["qty_scrap"] += qty_scrap
        if source == "good":
            state["_good_delta"] -= qty_scrap      # good hilang sebesar scrap; fixed kembali (net 0)
        else:  # reject
            state["_good_delta"] += qty_fixed      # reject direpair → good baru
    elif status == PERMAK_SCRAP:
        # semua qty dibuang
        state["qty_scrap"] += qty
        if source == "good":
            state["_good_delta"] -= qty


async def compute_po_progress(db, po_id: str) -> Optional[Dict[str, Any]]:
    """Full canonical progress for one maklon PO (SSOT: production_pos + po_items).

    Returns None kalau PO tidak ada di `production_pos` (mis. PO legacy dunia-B murni).
    """
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return None

    items = await db.po_items.find({"po_id": po_id}, {"_id": 0}).sort("created_at", 1).to_list(None)
    item_ids = [i["id"] for i in items]

    # Init per-item states
    states: Dict[str, Dict[str, int]] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    for it in items:
        iid = it["id"]
        st = _blank_item_state()
        st["qty_ordered"] = _int(it.get("qty"))
        states[iid] = st
        meta[iid] = {
            "po_item_id": iid,
            "sku": it.get("sku", ""),
            "product_name": it.get("product_name", ""),
            "size": it.get("size", ""),
            "color": it.get("color", ""),
            "serial_number": it.get("serial_number", ""),
            "unit_price": it.get("unit_price", 0),
        }

    if item_ids:
        # produced (legacy source)
        prod_agg = await db.production_job_items.aggregate([
            {"$match": {"po_item_id": {"$in": item_ids}}},
            {"$group": {"_id": "$po_item_id", "q": {"$sum": "$produced_qty"}}},
        ]).to_list(None)
        for a in prod_agg:
            if a["_id"] in states:
                states[a["_id"]]["qty_produced"] = _int(a["q"])

        # cmt_receipt_lines — only from Approved receipts
        approved_ids = await _approved_receipt_ids(db, po_id)
        if approved_ids:
            lines = await db.cmt_receipt_lines.find(
                {"receipt_id": {"$in": approved_ids}, "po_item_id": {"$in": item_ids}},
                {"_id": 0},
            ).to_list(None)
            for ln in lines:
                iid = ln.get("po_item_id")
                if iid not in states:
                    continue
                st = states[iid]
                st["qty_returned_cmt"] += _int(ln.get("qty_shipped_by_cmt"))
                st["qty_accepted"] += _int(ln.get("qty_actual"))
                st["qty_reject_qc"] += _int(ln.get("reject_qty"))

        # permak / rework
        permaks = await db.dewi_cmt_permak.find(
            {"po_item_id": {"$in": item_ids}}, {"_id": 0}
        ).to_list(None)
        for p in permaks:
            iid = p.get("po_item_id")
            if iid in states:
                _apply_permak(states[iid], p)

        # buyer shipment (dispatch DA→buyer)
        ship_agg = await db.buyer_shipment_items.aggregate([
            {"$match": {"po_item_id": {"$in": item_ids}}},
            {"$group": {
                "_id": "$po_item_id",
                "shipped": {"$sum": "$qty_shipped"},
                "recv": {"$sum": {"$ifNull": ["$qty_received", "$qty_shipped"]}},
            }},
        ]).to_list(None)
        for a in ship_agg:
            if a["_id"] in states:
                states[a["_id"]]["qty_dispatched"] = _int(a["shipped"])
                states[a["_id"]]["qty_received_buyer"] = _int(a["recv"])

    # Finalize items + totals
    item_out: List[Dict[str, Any]] = []
    totals = _blank_item_state()
    good_total = 0
    good_ready_total = 0
    for iid in item_ids:
        fin = _finalize_item(states[iid])
        merged = {**meta[iid], **fin}
        item_out.append(merged)
        for k in totals:
            if k in fin:
                totals[k] += fin[k]
        good_total += fin["qty_good"]
        good_ready_total += fin["qty_good_ready"]

    ordered = totals["qty_ordered"]
    breakdown = {k: v for k, v in totals.items() if not k.startswith("_")}
    breakdown["qty_good"] = good_total
    breakdown["qty_good_ready"] = good_ready_total
    breakdown["qty_outstanding"] = max(0, ordered - totals["qty_dispatched"])

    result = {
        "po_id": po_id,
        "po_number": po.get("po_number", ""),
        "business_type": po.get("business_type", ""),
        "status": po.get("status", ""),
        "buyer_id": po.get("buyer_id", ""),
        "customer_name": po.get("customer_name", ""),
        # ── Backward-compat scalars (jangan dihapus) ────────────────────────
        "total_ordered": ordered,
        "total_produced": totals["qty_produced"],
        "total_dispatched": totals["qty_dispatched"],
        "total_received": totals["qty_received_buyer"],
        "progress_pct": _pct(totals["qty_produced"], ordered),
        "delivery_pct": _pct(totals["qty_received_buyer"], ordered),
        # ── Canonical multi-state ───────────────────────────────────────────
        "good_pct": _pct(good_total, ordered),
        "dispatch_pct": _pct(totals["qty_dispatched"], ordered),
        "breakdown": breakdown,
        "items": item_out,
    }
    return result


def summarize_breakdown(progress: Dict[str, Any]) -> Dict[str, Any]:
    """Compact summary (untuk list views) dari hasil compute_po_progress."""
    b = progress.get("breakdown", {})
    return {
        "po_id": progress.get("po_id"),
        "po_number": progress.get("po_number"),
        "status": progress.get("status"),
        "progress_pct": progress.get("progress_pct", 0),
        "delivery_pct": progress.get("delivery_pct", 0),
        "good_pct": progress.get("good_pct", 0),
        "dispatch_pct": progress.get("dispatch_pct", 0),
        "breakdown": b,
    }


async def compute_pos_batch(db, po_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Compute canonical breakdown untuk banyak PO (dipakai list views).

    Mengembalikan {po_id: summary} agar list `/pos` bisa tampilkan breakdown ringkas
    tanpa N+1 round-trip berat. Perhitungan tetap reuse compute_po_progress per PO
    (aggregations sudah ter-index), cukup untuk skala 200 PO list.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for pid in po_ids:
        prog = await compute_po_progress(db, pid)
        if prog is not None:
            out[pid] = summarize_breakdown(prog)
    return out
