"""
services/cmt_intake.py — READ-ONLY agregasi "INTAKE BENAR" (Fase 3 / S1 POTONGAN MASUK + cek-seri).

Kontrak SSOT (INVARIANTS MCS-01/05):
- Sumber seri (SN) TUNGGAL = `po_items.serial_number` (diinput saat BUAT ORDER, ProductionPOModule).
  Seri ini MEWARIS otomatis ke `production_job_items`/`vendor_shipment_items`/`buyer_shipment_items`
  (bukan duplikat — hanya diturunkan). Maka deteksi DOBEL cukup dilihat di titik asal `po_items`.
- Potongan masuk (DA→CMT) = `vendor_shipments`/`vendor_shipment_items` (qty_sent) + inspeksi.

MODUL INI TIDAK MENULIS APA PUN & TIDAK MEMBUAT FIELD/KOLEKSI BARU.
Semua = agregasi read-only di atas rantai SSOT yang sudah ada.
"""
from typing import Dict, List, Any, Optional


def _int(v) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0


def _norm(s: Any) -> str:
    """Normalisasi seri untuk pembanding dobel: trim + upper + rapatkan spasi."""
    return " ".join(str(s or "").strip().upper().split())


# ─── Scope PO ────────────────────────────────────────────────────────────────
async def _po_map(db, scope: str = "maklon") -> Dict[str, Dict[str, Any]]:
    """Peta {po_id: po} sesuai scope ('maklon' | 'all')."""
    q: Dict[str, Any] = {}
    if scope == "maklon":
        q["business_type"] = "maklon"
    pos = await db.production_pos.find(
        q, {"_id": 0, "id": 1, "po_number": 1, "customer_name": 1,
            "status": 1, "business_type": 1}
    ).to_list(2000)
    return {p["id"]: p for p in pos}


# ─── CEK-SERI: deteksi seri dobel lintas po_items ─────────────────────────────
async def cek_seri(db, scope: str = "maklon") -> Dict[str, Any]:
    """Deteksi serial number yang dipakai di >1 baris PO (po_items) → potensi dobel.

    READ-ONLY. Sumber = po_items.serial_number (SSOT seri). Tidak ada field baru.
    """
    pom = await _po_map(db, scope)
    po_ids = list(pom.keys())
    q: Dict[str, Any] = {"serial_number": {"$nin": [None, ""]}}
    if scope == "maklon":
        q["po_id"] = {"$in": po_ids}

    items = await db.po_items.find(
        q, {"_id": 0, "id": 1, "po_id": 1, "po_number": 1, "serial_number": 1,
            "sku": 1, "size": 1, "color": 1, "qty": 1, "product_name": 1}
    ).to_list(5000)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    total_with_serial = 0
    for it in items:
        raw = it.get("serial_number") or ""
        if not str(raw).strip():
            continue
        total_with_serial += 1
        po = pom.get(it.get("po_id"), {})
        usage = {
            "po_item_id": it.get("id"),
            "po_id": it.get("po_id"),
            "po_number": it.get("po_number") or po.get("po_number", ""),
            "customer_name": po.get("customer_name", ""),
            "po_status": po.get("status", ""),
            "business_type": po.get("business_type", ""),
            "serial_raw": raw,
            "sku": it.get("sku", ""),
            "size": it.get("size", ""),
            "color": it.get("color", ""),
            "qty": _int(it.get("qty")),
            "product_name": it.get("product_name", ""),
        }
        groups.setdefault(_norm(raw), []).append(usage)

    duplicates = []
    for norm_serial, usages in groups.items():
        if len(usages) > 1:
            duplicates.append({
                "serial": norm_serial,
                "count": len(usages),
                # tandai jika hanya beda kapital/spasi (variasi penulisan)
                "raw_variants": sorted({u["serial_raw"] for u in usages}),
                "has_case_variant": len({u["serial_raw"] for u in usages}) > 1,
                "usages": sorted(usages, key=lambda u: (u["po_number"], u["sku"])),
            })
    duplicates.sort(key=lambda d: (-d["count"], d["serial"]))

    return {
        "scope": scope,
        "total_serials": len(groups),
        "total_items_with_serial": total_with_serial,
        "duplicate_count": len(duplicates),
        "duplicate_item_count": sum(d["count"] for d in duplicates),
        "duplicates": duplicates,
    }


# ─── SERIAL LOOKUP: cek 1 seri (untuk peringatan live saat BUAT ORDER) ─────────
async def serial_lookup(
    db, serial: str, exclude_po_id: Optional[str] = None,
    exclude_item_id: Optional[str] = None, scope: str = "all",
) -> Dict[str, Any]:
    """Cek apakah 1 serial sudah dipakai di po_items lain (global secara default).

    Dipakai form BUAT ORDER untuk peringatan (TIDAK block). READ-ONLY.
    """
    norm = _norm(serial)
    result = {"serial": serial, "normalized": norm, "exists": False, "usages": []}
    if not norm:
        return result

    q: Dict[str, Any] = {"serial_number": {"$nin": [None, ""]}}
    if scope == "maklon":
        pom = await _po_map(db, "maklon")
        q["po_id"] = {"$in": list(pom.keys())}
    else:
        pom = None

    items = await db.po_items.find(
        q, {"_id": 0, "id": 1, "po_id": 1, "po_number": 1, "serial_number": 1,
            "sku": 1, "size": 1, "color": 1, "qty": 1}
    ).to_list(5000)

    usages = []
    for it in items:
        if _norm(it.get("serial_number")) != norm:
            continue
        if exclude_item_id and it.get("id") == exclude_item_id:
            continue
        if exclude_po_id and it.get("po_id") == exclude_po_id:
            continue
        po = None
        if pom is not None:
            po = pom.get(it.get("po_id"))
        else:
            po = await db.production_pos.find_one(
                {"id": it.get("po_id")},
                {"_id": 0, "customer_name": 1, "status": 1, "business_type": 1},
            )
        po = po or {}
        usages.append({
            "po_item_id": it.get("id"),
            "po_id": it.get("po_id"),
            "po_number": it.get("po_number", ""),
            "customer_name": po.get("customer_name", ""),
            "po_status": po.get("status", ""),
            "business_type": po.get("business_type", ""),
            "serial_raw": it.get("serial_number", ""),
            "sku": it.get("sku", ""),
            "size": it.get("size", ""),
            "color": it.get("color", ""),
            "qty": _int(it.get("qty")),
        })
    result["exists"] = len(usages) > 0
    result["usages"] = usages
    return result


# ─── POTONGAN MASUK: batch view atas vendor_shipments ─────────────────────────
async def intake_batches(
    db, po_id: Optional[str] = None, only_open: bool = True, scope: str = "maklon",
) -> Dict[str, Any]:
    """View per-batch "POTONGAN MASUK" (DA→CMT) dari `vendor_shipments`.

    READ-ONLY. Setiap batch = 1 vendor_shipment; itemnya = vendor_shipment_items
    (sku/size/color/serial/qty_sent) + status inspeksi (received/missing).
    """
    pom = await _po_map(db, scope)
    q: Dict[str, Any] = {}
    if po_id:
        q["po_id"] = po_id
    elif scope == "maklon":
        # batasi ke shipment yang PO-nya maklon (business_type shipment kadang kosong utk data lama)
        q["$or"] = [{"business_type": "maklon"}, {"po_id": {"$in": list(pom.keys())}}]

    shipments = await db.vendor_shipments.find(
        q, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)

    # buang PO yang bukan scope (kalau data lama tak ber-business_type)
    if scope == "maklon" and not po_id:
        shipments = [s for s in shipments if s.get("po_id") in pom or s.get("business_type") == "maklon"]

    ship_ids = [s["id"] for s in shipments]
    items_by_ship: Dict[str, List[Dict[str, Any]]] = {}
    if ship_ids:
        vsi = await db.vendor_shipment_items.find(
            {"shipment_id": {"$in": ship_ids}}, {"_id": 0}
        ).to_list(5000)
        # inspeksi per shipment_item (received/missing)
        vsi_ids = [v["id"] for v in vsi]
        insp_by_vsi: Dict[str, Dict[str, Any]] = {}
        if vsi_ids:
            insp_items = await db.vendor_material_inspection_items.find(
                {"shipment_item_id": {"$in": vsi_ids}}, {"_id": 0}
            ).to_list(5000)
            for ii in insp_items:
                insp_by_vsi[ii["shipment_item_id"]] = ii
        for v in vsi:
            ii = insp_by_vsi.get(v["id"], {})
            items_by_ship.setdefault(v["shipment_id"], []).append({
                "vsi_id": v.get("id"),
                "po_item_id": v.get("po_item_id"),
                "product_name": v.get("product_name", ""),
                "sku": v.get("sku", ""),
                "size": v.get("size", ""),
                "color": v.get("color", ""),
                "serial_number": v.get("serial_number", ""),
                "qty_sent": _int(v.get("qty_sent")),
                "received_qty": _int(ii.get("received_qty")) if ii else None,
                "missing_qty": _int(ii.get("missing_qty")) if ii else None,
                "inspected": bool(ii),
            })

    batches = []
    for s in shipments:
        items = items_by_ship.get(s["id"], [])
        total_sent = sum(i["qty_sent"] for i in items)
        total_received = sum((i["received_qty"] or 0) for i in items if i["received_qty"] is not None)
        total_missing = sum((i["missing_qty"] or 0) for i in items if i["missing_qty"] is not None)
        any_inspected = any(i["inspected"] for i in items)
        batches.append({
            "shipment_id": s.get("id"),
            "shipment_number": s.get("shipment_number", ""),
            "delivery_note_number": s.get("delivery_note_number", ""),
            "po_id": s.get("po_id"),
            "po_number": s.get("po_number", ""),
            "customer_name": pom.get(s.get("po_id"), {}).get("customer_name", ""),
            "vendor_name": s.get("vendor_name", ""),
            "shipment_date": s.get("shipment_date"),
            "shipment_type": s.get("shipment_type", "NORMAL"),
            "status": s.get("status", ""),
            "inspection_status": s.get("inspection_status", "" if not any_inspected else "Inspected"),
            "item_count": len(items),
            "total_sent": total_sent,
            "total_received": total_received if any_inspected else None,
            "total_missing": total_missing if any_inspected else None,
            "items": items,
        })

    return {
        "scope": scope,
        "po_id": po_id,
        "count": len(batches),
        "total_sent": sum(b["total_sent"] for b in batches),
        "batches": batches,
    }
