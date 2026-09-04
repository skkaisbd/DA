"""
CV. Dewi Aditya / PT Rahaza — WMS Pick-List Generator (Phase 7.9)

Given outbound movements (shipment FG or material issue RM), generate an
optimized pick list:
  - Find positions where the requested material is stored
  - Sort by building → zone → rack → shelf → slot (efficient picking route)
  - Provide ordered PDF for floor workers

Endpoints (prefix /api/wms/picklist):
  GET  /source/{source_type}/{source_id}  → generate pick list from a source
  GET  /{picklist_id}                     → fetch saved pick list
  POST /                                   → create a pick list from explicit items
  GET  /{picklist_id}/pdf                  → printable PDF
  GET  /                                   → list all pick lists
  POST /{picklist_id}/complete            → mark pick list as completed
"""
# ruff: noqa: F401
import uuid
import io
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/wms/picklist", tags=["wms-picklist"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(d):
    if not d:
        return None
    d = dict(d)
    d.pop("_id", None)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


async def _build_picklist_items(db, items: List[dict]) -> List[dict]:
    """
    Given list of {material_id, material_code, material_name, qty, unit},
    find all positions that store each material, distribute qty FIFO,
    and return ordered pick items sorted by location.
    """
    pick_items = []
    for item in items:
        material_id = item.get("material_id")
        needed = float(item.get("qty") or 0)
        if needed <= 0 or not material_id:
            continue

        # Find positions with this material, sorted by location
        positions = await db.wh_positions.find(
            {"material_id": material_id, "qty": {"$gt": 0}},
            {"_id": 0}
        ).to_list(500)

        # Sort by building→zone→rack→shelf→slot using barcode
        positions.sort(key=lambda p: (
            p.get("building_code", ""),
            p.get("zone_code", ""),
            p.get("rack_code", ""),
            p.get("shelf_number", 0),
            p.get("slot_number", 0),
            p.get("barcode", ""),
        ))

        # Allocate qty across positions (greedy, take what's available)
        remaining = needed
        for pos in positions:
            avail = float(pos.get("qty") or 0)
            if avail <= 0:
                continue
            take = min(avail, remaining)
            pick_items.append({
                "pick_item_id": _uid(),
                "material_id": material_id,
                "material_code": item.get("material_code", pos.get("material_code", "")),
                "material_name": item.get("material_name", pos.get("material_name", "")),
                "position_id": pos.get("id"),
                "position_barcode": pos.get("barcode", ""),
                "building_code": pos.get("building_code", ""),
                "zone_code": pos.get("zone_code", ""),
                "rack_code": pos.get("rack_code", ""),
                "shelf_number": pos.get("shelf_number"),
                "slot_number": pos.get("slot_number"),
                "qty_to_pick": round(take, 3),
                "available_qty": round(avail, 3),
                "unit": item.get("unit", pos.get("unit", "pcs")),
                "status": "pending",  # pending | picked | short
                "picked_qty": 0,
                "lot_number": pos.get("lot_number", ""),
            })
            remaining -= take
            if remaining <= 0.001:
                break

        # If still short, add a "short" entry
        if remaining > 0.001:
            pick_items.append({
                "pick_item_id": _uid(),
                "material_id": material_id,
                "material_code": item.get("material_code", ""),
                "material_name": item.get("material_name", ""),
                "position_id": None,
                "position_barcode": "",
                "building_code": "",
                "zone_code": "",
                "rack_code": "",
                "qty_to_pick": round(remaining, 3),
                "available_qty": 0,
                "unit": item.get("unit", "pcs"),
                "status": "short",
                "picked_qty": 0,
                "note": "Stok tidak mencukupi — butuh restock.",
            })

    return pick_items


@router.get("")
async def list_picklists(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    await require_auth(request)
    db = get_db()
    filt: dict = {}
    if status:
        filt["status"] = status
    docs = await db.wh_picklists.find(filt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"ok": True, "picklists": [_s(d) for d in docs]}


@router.post("")
async def create_picklist(request: Request):
    """Create pick list from explicit items [{material_id, qty, unit, ...}]."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    items = body.get("items") or []
    if not items:
        raise HTTPException(400, "items wajib diisi.")

    pick_items = await _build_picklist_items(db, items)

    doc = {
        "picklist_id": _uid(),
        "ref_number": f"PL-{_now().strftime('%Y%m%d-%H%M%S')}",
        "source_type": body.get("source_type") or "manual",
        "source_id": body.get("source_id") or "",
        "source_ref": body.get("source_ref") or "",
        "items": pick_items,
        "total_items": len(pick_items),
        "total_qty": sum(i["qty_to_pick"] for i in pick_items),
        "status": "pending",  # pending | in_progress | completed
        "notes": body.get("notes") or "",
        "assignee_id": body.get("assignee_id") or "",
        "assignee_name": body.get("assignee_name") or "",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    await db.wh_picklists.insert_one(doc)
    return {"ok": True, "picklist": _s(doc)}


@router.get("/source/{source_type}/{source_id}")
async def generate_from_source(source_type: str, source_id: str, request: Request):
    """
    Generate (preview) pick list from a source without saving.
    source_type: shipment | material_issue
    """
    await require_auth(request)
    db = get_db()

    items_to_pick: List[dict] = []
    ref = ""

    if source_type == "shipment":
        ship = await db.rahaza_shipments.find_one({"id": source_id}, {"_id": 0})
        if not ship:
            raise HTTPException(404, "Shipment tidak ditemukan.")
        ref = ship.get("shipment_number") or source_id[:8]
        for line in (ship.get("items") or ship.get("lines") or []):
            items_to_pick.append({
                "material_id": line.get("material_id") or line.get("fg_id") or line.get("model_id"),
                "material_code": line.get("material_code") or line.get("fg_code") or line.get("model_code"),
                "material_name": line.get("material_name") or line.get("model_name") or "",
                "qty": float(line.get("qty") or line.get("qty_shipped") or 0),
                "unit": line.get("unit") or "pcs",
            })
    elif source_type == "material_issue":
        mi = await db.rahaza_material_issues.find_one({"id": source_id}, {"_id": 0})
        if not mi:
            mi = await db.dewi_material_issues.find_one({"id": source_id}, {"_id": 0})
        if not mi:
            raise HTTPException(404, "Material issue tidak ditemukan.")
        ref = mi.get("mi_number") or mi.get("issue_number") or source_id[:8]
        for line in (mi.get("items") or mi.get("lines") or []):
            items_to_pick.append({
                "material_id": line.get("material_id"),
                "material_code": line.get("material_code"),
                "material_name": line.get("material_name") or "",
                "qty": float(line.get("qty") or 0),
                "unit": line.get("unit") or "pcs",
            })
    elif source_type == "pending_movement":
        mv = await db.wh_pending_movements.find_one({"id": source_id}, {"_id": 0})
        if not mv:
            raise HTTPException(404, "Pending movement tidak ditemukan.")
        if mv.get("type") not in ("outbound_fg", "outbound_rm"):
            raise HTTPException(400, "Hanya movement outbound yang bisa di-picklist.")
        ref = mv.get("ref_number") or source_id[:8]
        items_to_pick.append({
            "material_id": mv.get("material_id"),
            "material_code": mv.get("material_code"),
            "material_name": mv.get("material_name") or "",
            "qty": float(mv.get("expected_qty") or 0),
            "unit": mv.get("unit") or "pcs",
        })
    else:
        raise HTTPException(400, f"source_type tidak didukung: {source_type}")

    if not items_to_pick:
        raise HTTPException(400, "Tidak ada item untuk dipick.")

    pick_items = await _build_picklist_items(db, items_to_pick)
    return {
        "ok": True,
        "preview": True,
        "source_type": source_type,
        "source_id": source_id,
        "source_ref": ref,
        "items": pick_items,
        "total_items": len(pick_items),
        "total_qty": sum(i["qty_to_pick"] for i in pick_items),
        "short_items": sum(1 for i in pick_items if i.get("status") == "short"),
    }


@router.get("/{picklist_id}")
async def get_picklist(picklist_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.wh_picklists.find_one({"picklist_id": picklist_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pick list tidak ditemukan.")
    return {"ok": True, "picklist": _s(doc)}


@router.put("/{picklist_id}/item/{pick_item_id}/pick")
async def mark_item_picked(picklist_id: str, pick_item_id: str, request: Request):
    """Mark one pick item as picked (or partially picked)."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    picked_qty = float(body.get("picked_qty") or 0)

    doc = await db.wh_picklists.find_one({"picklist_id": picklist_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pick list tidak ditemukan.")

    items = doc.get("items") or []
    found = False
    for it in items:
        if it.get("pick_item_id") == pick_item_id:
            it["picked_qty"] = picked_qty
            it["status"] = "picked" if picked_qty >= it.get("qty_to_pick", 0) else ("partial" if picked_qty > 0 else "pending")
            it["picked_by"] = user.get("name", "")
            it["picked_at"] = _now().isoformat()
            found = True
            break
    if not found:
        raise HTTPException(404, "Pick item tidak ditemukan.")

    # Update overall status
    all_picked = all(i.get("status") == "picked" for i in items if i.get("status") != "short")
    any_picked = any(i.get("status") in ("picked", "partial") for i in items)
    new_status = "completed" if all_picked else ("in_progress" if any_picked else "pending")

    await db.wh_picklists.update_one(
        {"picklist_id": picklist_id},
        {"$set": {
            "items": items,
            "status": new_status,
            "updated_at": _now(),
            "completed_at": _now() if new_status == "completed" else None,
        }}
    )
    return {"ok": True, "status": new_status}


@router.post("/{picklist_id}/complete")
async def complete_picklist(picklist_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.wh_picklists.update_one(
        {"picklist_id": picklist_id},
        {"$set": {"status": "completed", "completed_at": _now(), "completed_by": user["id"], "updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Pick list tidak ditemukan.")
    return {"ok": True}


@router.delete("/{picklist_id}")
async def delete_picklist(picklist_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.wh_picklists.delete_one({"picklist_id": picklist_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Pick list tidak ditemukan.")
    return {"ok": True}


@router.get("/{picklist_id}/pdf")
async def picklist_pdf(picklist_id: str, request: Request):
    """Pick List cetak — SESI #19: memakai TEMPLATE PDF pemilik.

    Yang terukur sebelum ini: Pick List sama sekali TIDAK punya kop surat (nama PT
    pun tidak ada, padahal kertas ini dibawa keluar rak dan sering ikut ke tangan
    ekspedisi), blok tanda tangannya dipaku tiga ("Picker/Checker/Delivered to")
    tanpa bisa diubah, dan lebar kolomnya milimeter tetap: 174 mm dari 186 mm lebar
    konten ⇒ tabel tidak penuh halaman.

    Sekarang kop, kolom (tampil/urutan/lebar/kolom tambahan), blok tanda tangan, dan
    footer datang dari layar "PDF & Kop Surat" — dengan generator tabel yang sama
    (`_pdf_data_table`) yang dijaga penjaga anti-tumpang-tindih INV-F17.
    """
    await require_auth(request)
    db = get_db()
    doc = await db.wh_picklists.find_one({"picklist_id": picklist_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pick list tidak ditemukan.")

    try:
        from core.pdf_template import (footer_flowables, header_flowables,
                                       signature_flowables)
        from routes.operations_pdf_helpers import (CONTENT_W_PORTRAIT, _build_pdf,
                                                   _pdf_data_table, tpl_table_parts)
        from utils.pdf_common import get_company_profile
    except ImportError:
        raise HTTPException(500, "reportlab belum terinstall.")

    items = doc.get("items") or []
    created_raw = doc.get("created_at") or ""
    created_str = (created_raw.isoformat() if isinstance(created_raw, datetime)
                   else str(created_raw))

    all_keys = ['no', 'position_barcode', 'location', 'material_code', 'material_name',
                'qty', 'unit', 'checkbox']
    all_headers = ['No', 'Barcode Posisi', 'Lokasi', 'Kode Material', 'Nama Material',
                   'Qty Ambil', 'Satuan', 'Pick']
    rows = []
    for i, it in enumerate(items, 1):
        kurang = it.get("status") == "short"
        lokasi = "—" if kurang else (
            f"{it.get('building_code','')}/{it.get('zone_code','')}/{it.get('rack_code','')}")
        rows.append([
            i, it.get("position_barcode") or "—", lokasi,
            it.get("material_code", ""), it.get("material_name", ""),
            f"{it.get('qty_to_pick', 0)}" + (" (kurang)" if kurang else ""),
            it.get("unit", ""), "(   )",
        ])

    headers, rows2, keys, weights, right_cols, doc_settings = await tpl_table_parts(
        db, 'picklist', all_keys, all_headers, rows, numeric_keys=('qty',))

    profile = await get_company_profile(db)
    tpl = (doc_settings or {}).get('_template') or {}
    elements = header_flowables(
        tpl.get('header'), profile, 'PICK LIST',
        info_pairs=[
            ('No. Pick List', doc.get('ref_number', '')),
            ('Dibuat', created_str[:19].replace('T', ' ')),
            ('Sumber', f"{doc.get('source_type','-')} · {doc.get('source_ref','-')}"),
            ('Operator', doc.get('assignee_name') or '—'),
            ('Total', f"{len(items)} item · {doc.get('total_qty', 0)} pcs"),
            ('Status', doc.get('status', '-')),
        ], avail=CONTENT_W_PORTRAIT)

    if headers:
        elements.append(_pdf_data_table(headers, rows2, weights=weights,
                                        right_cols=right_cols, style=tpl.get('table')))

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        "<i>Ambil item berurutan sesuai daftar untuk rute terpendek. "
        "Scan barcode posisi saat mengambil item.</i>",
        ParagraphStyle("plNote", fontSize=8, leading=10.5)))

    elements.extend(signature_flowables(
        tpl.get('signatures'),
        {"assignee_name": doc.get('assignee_name') or '',
         "ref_number": doc.get('ref_number', '')},
        avail=CONTENT_W_PORTRAIT))
    elements.extend(footer_flowables(tpl.get('footer'), profile))

    buf = _build_pdf(io.BytesIO(), elements)
    ref_number = doc.get("ref_number", "PL")
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="picklist_{ref_number}.pdf"'})
