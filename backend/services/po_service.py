"""
po_service.py — Procure-to-Pay (P2P) Service Layer
CV. Dewi Aditya — P1.C Procure-to-Pay Completion

Fungsi:
- get_po_with_grn_status(db, po_id) → enriched PO dict
- get_available_grs_for_invoice(db, vendor_id) → list[gr]
- link_grn_to_po(db, grn_id, po_id) → updated grn
- compute_3way_match(db, po_id) → {status, po, grn, ap_invoice, discrepancies}
- get_p2p_summary(db) → summary dict
"""
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_po_with_grn_status(db: AsyncIOMotorDatabase, po_id: str) -> Optional[dict]:
    """
    Ambil PO beserta status penerimaan barang (GRN) dan invoice yang terkait.
    """
    po = await db.rahaza_purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return None

    # Find linked GRNs
    grns = await db.rahaza_grn_inspections.find({"po_id": po_id}, {"_id": 0}).to_list(50)
    # Find linked AP invoice
    ap = await db.rahaza_ap_invoices.find_one({"po_id": po_id}, {"_id": 0, "id": 1, "status": 1, "total_amount": 1})

    total_ordered = sum(float(it.get("qty_ordered") or it.get("qty") or 0) for it in (po.get("items") or []))
    total_received = sum(
        float(it.get("qty_accepted") or it.get("qty_received") or 0)
        for gr in grns
        for it in (gr.get("items") or [])
    )

    receive_pct = round((total_received / total_ordered * 100) if total_ordered else 0, 1)
    grn_status = "fully_received" if receive_pct >= 99 else ("partially_received" if receive_pct > 0 else "pending")

    return {
        **po,
        "grns": grns,
        "grn_count": len(grns),
        "grn_status": grn_status,
        "total_ordered": total_ordered,
        "total_received": total_received,
        "receive_pct": receive_pct,
        "ap_invoice": ap,
        "p2p_complete": grn_status == "fully_received" and ap is not None,
    }


async def compute_3way_match(
    db: AsyncIOMotorDatabase,
    po_id: str,
) -> dict:
    """
    Hitung 3-way match untuk satu PO.
    Bandingkan: PO qty & amount vs GRN qty & amount vs AP Invoice amount.
    """
    enriched = await get_po_with_grn_status(db, po_id)
    if not enriched:
        return {"status": "not_found", "po_id": po_id}

    po_total = float(enriched.get("total_amount") or enriched.get("total") or 0)
    grn_total = sum(
        float(gr.get("total_accepted_amount") or gr.get("total_value") or 0)
        for gr in enriched.get("grns", [])
    )
    ap_total  = float((enriched.get("ap_invoice") or {}).get("total_amount") or 0)

    discrepancies = []
    if abs(po_total - grn_total) > 1:       # tolerance Rp 1
        discrepancies.append({"type": "qty",  "desc": f"PO {po_total:,.0f} vs GRN {grn_total:,.0f}"})
    if ap_total and abs(grn_total - ap_total) > 1:
        discrepancies.append({"type": "invoice", "desc": f"GRN {grn_total:,.0f} vs Invoice {ap_total:,.0f}"})

    status = "matched" if not discrepancies else "discrepancy"
    if not enriched.get("grns"):
        status = "pending_grn"
    if not enriched.get("ap_invoice"):
        status = "pending_invoice" if enriched.get("grns") else "pending_grn"

    return {
        "po_id": po_id,
        "status": status,
        "po_total": po_total,
        "grn_total": grn_total,
        "ap_total": ap_total,
        "discrepancies": discrepancies,
        "grn_count": enriched["grn_count"],
        "receive_pct": enriched["receive_pct"],
        "grn_status": enriched["grn_status"],
        "ap_invoice": enriched.get("ap_invoice"),
    }


async def get_p2p_summary(db: AsyncIOMotorDatabase) -> dict:
    """Ringkasan status P2P pipeline."""
    total_pos    = await db.rahaza_purchase_orders.count_documents({})
    open_pos     = await db.rahaza_purchase_orders.count_documents({"status": {"$in": ["approved", "partially_received"]}})
    pending_grn  = await db.rahaza_purchase_orders.count_documents({"status": "approved", "grn_status": "pending"})
    grns         = await db.rahaza_grn_inspections.count_documents({})
    open_invoices= await db.rahaza_ap_invoices.count_documents({"status": {"$in": ["draft", "pending"]}})
    return {
        "total_pos": total_pos,
        "open_pos": open_pos,
        "pending_grn": pending_grn,
        "total_grns": grns,
        "open_ap_invoices": open_invoices,
    }
