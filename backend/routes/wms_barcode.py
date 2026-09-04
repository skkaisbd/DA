"""FASE H-3 (2026-08-16) — MENU "BUAT BARCODE": satu pintu cetak label.

Keadaan sebelum berkas ini (diukur, bukan dugaan):
  · `POST /api/wms/materials/labels/batch-pdf` & `POST /api/wms/fg/labels/batch-pdf`
    sudah ada berbulan-bulan dengan **0 pemanggil di seluruh frontend** ⇒ dari sudut
    pandang pemakai, barcode bahan & barang jadi TIDAK BISA dicetak.
  · Keduanya hanya bisa 1 label per item — padahal pekerjaan gudang selalu
    "cetak 50 lembar untuk satu artikel".
  · Jalur FG membaca `rahaza_fg_matrix` yang di basis data ini **KOSONG (0 dokumen)**,
    sementara barang jadi yang nyata hidup di `rahaza_materials` (`type='fg'`, 332
    dokumen, lahir otomatis dari varian master). Artinya tombol cetak FG akan
    SELALU menjawab 404 "tidak ditemukan" — cacat yang mustahil terlihat dari
    daftar endpoint, karena endpoint-nya sendiri "ada".

Aturan yang dipegang endpoint ini:
  1. **Nilai barcode = kode master.** Tidak ada field untuk mengetik kode bebas.
     Barcode yang kodenya dikarang akan discan menjadi item yang tidak ada di
     sistem — dan barang fisiknya sudah tertempel label itu (aturan F14).
  2. **Sumber "otomatis dari produksi" wajib menyebut yang TIDAK ketemu di master.**
     Baris PO yang SKU-nya belum punya varian master dilaporkan
     `master_linked: false` beserta alasannya, bukan dibuang diam-diam dan bukan
     dicetak seolah-olah sah.
  3. **Batas label per cetak** (`MAX_LABELS`) supaya satu klik tidak melahirkan
     PDF ribuan halaman yang menggantung browser.
  4. **Riwayat cetak dicatat** (`wh_barcode_print_jobs`): "siapa mencetak label
     apa, berapa lembar, kapan" adalah satu-satunya cara menjawab pertanyaan
     "kenapa ada dua label dengan kode sama di gudang".
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import log_activity, require_auth, serialize_doc
from core import label_render as lr
from database import get_db
from utils.counters import gen_prefixed_number

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/barcode", tags=["wms-barcode"])

MAX_LABELS = 500          # total lembar per satu PDF
MAX_COPIES_PER_ROW = 200
KINDS = ("material", "fg")
MASTER_LIMIT = 20000


def _now():
    return datetime.now(timezone.utc)


def _kind_filter(kind: str) -> dict:
    return {"type": "fg"} if kind == "fg" else {"type": {"$ne": "fg"}}


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(400, f"kind harus salah satu dari {KINDS}")
    return kind


def _slim(m: dict) -> dict:
    return {
        "id": m.get("id"), "code": m.get("code") or m.get("sku"),
        "name": m.get("name"), "unit": lr.unit_of(m), "type": m.get("type"),
        "category": m.get("category") or "", "color": m.get("color_name") or m.get("color") or "",
        "size": m.get("size_code") or m.get("size") or "",
        "model_code": m.get("model_code") or "", "is_cut_panel": bool(m.get("is_cut_panel")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Pemilih item dari MASTER
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/items")
async def barcode_items(
    request: Request,
    kind: str = Query("material"),
    q: str = Query("", max_length=120),
    limit: int = Query(60, ge=1, le=300),
):
    """Daftar item master untuk dipilih. Barcode HANYA boleh dari master ini."""
    await require_auth(request)
    _check_kind(kind)
    db = get_db()
    flt = {"active": {"$ne": False}, **_kind_filter(kind)}
    if q.strip():
        rx = re.escape(q.strip())
        flt["$or"] = [{"code": {"$regex": rx, "$options": "i"}},
                      {"name": {"$regex": rx, "$options": "i"}},
                      {"sku": {"$regex": rx, "$options": "i"}}]
    total = await db.rahaza_materials.count_documents(flt)
    rows = await db.rahaza_materials.find(flt, {"_id": 0}).sort("code", 1).limit(limit).to_list(limit)
    return {"kind": kind, "total": total, "returned": len(rows),
            "items": [_slim(m) for m in rows]}


# ══════════════════════════════════════════════════════════════════════════════
# 2. Sumber OTOMATIS: dari PO produksi
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/production-options")
async def production_options(request: Request, limit: int = Query(30, ge=1, le=100)):
    """PO produksi terbaru + jumlah pcs — untuk mode 'otomatis dari produksi'."""
    await require_auth(request)
    db = get_db()
    pos = await db.production_pos.find(
        {}, {"_id": 0, "id": 1, "po_number": 1, "business_type": 1, "status": 1,
             "customer_name": 1, "buyer_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    ids = [p["id"] for p in pos]
    agg = {}
    if ids:
        async for it in db.po_items.find({"po_id": {"$in": ids}},
                                         {"_id": 0, "po_id": 1, "qty": 1}):
            e = agg.setdefault(it["po_id"], {"items": 0, "qty": 0})
            e["items"] += 1
            e["qty"] += int(it.get("qty") or 0)
    for p in pos:
        e = agg.get(p["id"], {"items": 0, "qty": 0})
        p["item_count"] = e["items"]
        p["total_qty"] = e["qty"]
    return serialize_doc(pos)


async def _resolve_fg_master(db, item: dict) -> Optional[dict]:
    """SKU PO → varian FG master. Tiga percobaan, dari paling pasti ke paling longgar.

    Kenapa tidak cukup mencocokkan SKU: SKU pada `po_items` demo internal berbunyi
    `DA-TS01-ALLSIZE` (tanpa kode warna) sementara varian master bernama
    `DA-TS01-HTM-ALLSIZE`. Mencocokkan hanya lewat SKU akan melaporkan "tidak ada
    di master" untuk barang yang jelas ADA — dan orang akan berhenti percaya
    penandanya.
    """
    sku = (item.get("sku") or "").strip()
    if sku:
        m = await db.rahaza_materials.find_one(
            {"type": "fg", "$or": [{"code": sku}, {"sku": sku}]}, {"_id": 0})
        if m:
            return m
    model_id, size_id = item.get("model_id"), item.get("size_id")
    color = (item.get("color") or "").strip().lower()
    if model_id and size_id:
        cands = await db.rahaza_materials.find(
            {"type": "fg", "model_id": model_id, "size_id": size_id}, {"_id": 0}
        ).to_list(200)
        if cands:
            if color:
                for c in cands:
                    names = {str(c.get(k) or "").strip().lower()
                             for k in ("color", "color_name", "color_code")}
                    if color in names:
                        return c
            elif len(cands) == 1:
                return cands[0]
    if model_id and (item.get("size") or "").strip():
        size = item["size"].strip().upper()
        cands = await db.rahaza_materials.find(
            {"type": "fg", "model_id": model_id, "size_code": size}, {"_id": 0}
        ).to_list(200)
        for c in cands:
            names = {str(c.get(k) or "").strip().lower()
                     for k in ("color", "color_name", "color_code")}
            if not color or color in names:
                return c
    return None


@router.get("/from-production")
async def from_production(request: Request, po_id: str = Query(..., min_length=1)):
    """Baris label yang MENGIKUTI produksi: artikel + jumlah dari PO."""
    await require_auth(request)
    db = get_db()
    po = await db.production_pos.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO produksi tidak ditemukan")
    items = await db.po_items.find({"po_id": po_id}, {"_id": 0}).to_list(MASTER_LIMIT)
    rows, unlinked = [], 0
    for it in items:
        fg = await _resolve_fg_master(db, it)
        if fg:
            rows.append({
                "material_id": fg.get("id"), "code": fg.get("code") or fg.get("sku"),
                "name": fg.get("name"), "size": fg.get("size_code") or it.get("size") or "",
                "color": fg.get("color_name") or fg.get("color") or it.get("color") or "",
                "copies": int(it.get("qty") or 0), "master_linked": True,
                "po_sku": it.get("sku") or "",
            })
        else:
            unlinked += 1
            rows.append({
                "material_id": None, "code": it.get("sku") or "",
                "name": it.get("product_name") or "", "size": it.get("size") or "",
                "color": it.get("color") or "", "copies": int(it.get("qty") or 0),
                "master_linked": False, "po_sku": it.get("sku") or "",
                "reason": "SKU ini belum punya varian di master Barang Jadi — "
                          "buat variannya dulu di Master Produk, jangan cetak label "
                          "dengan kode yang tidak dikenal sistem.",
            })
    return {"po_id": po_id, "po_number": po.get("po_number"),
            "business_type": po.get("business_type"), "kind": "fg",
            "rows": rows, "unlinked_count": unlinked,
            "total_copies": sum(r["copies"] for r in rows)}


# ══════════════════════════════════════════════════════════════════════════════
# 3. Cetak batch (1 PDF gabungan) + riwayat
# ══════════════════════════════════════════════════════════════════════════════

class BarcodeRow(BaseModel):
    id: Optional[str] = None
    code: Optional[str] = None
    copies: int = 1


class BarcodeBatchIn(BaseModel):
    kind: str = "material"
    rows: List[BarcodeRow] = []
    include_stock: bool = True
    source: str = "manual"           # manual | produksi
    po_id: Optional[str] = None
    note: str = ""


async def _attach_stock(db, mats: List[dict]):
    ids = [m["id"] for m in mats if m.get("id")]
    if not ids:
        return
    per = {}
    async for s in db.rahaza_material_stock.find(
            {"material_id": {"$in": ids}},
            {"_id": 0, "material_id": 1, "qty": 1, "location_id": 1}):
        per.setdefault(s["material_id"], []).append(s)
    loc_ids = list({s.get("location_id") for rows in per.values()
                    for s in rows if s.get("location_id")})
    loc_map = {}
    if loc_ids:
        async for loc in db.rahaza_locations.find({"id": {"$in": loc_ids}},
                                                  {"_id": 0, "id": 1, "code": 1, "name": 1}):
            loc_map[loc["id"]] = loc.get("code") or loc.get("name") or "-"
        async for pos in db.wh_positions.find({"id": {"$in": loc_ids}},
                                              {"_id": 0, "id": 1, "label": 1, "barcode": 1}):
            loc_map.setdefault(pos["id"], pos.get("label") or pos.get("barcode") or "-")
    for m in mats:
        rows = per.get(m.get("id")) or []
        if not rows:
            continue
        m["stock_qty"] = sum(float(s.get("qty") or 0) for s in rows)
        main = next((s.get("location_id") for s in rows
                     if float(s.get("qty") or 0) > 0 and s.get("location_id")), None)
        m["location"] = loc_map.get(main, "-")


@router.post("/batch-pdf")
async def barcode_batch_pdf(data: BarcodeBatchIn, request: Request):
    user = await require_auth(request)
    kind = _check_kind(data.kind)
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label (reportlab/barcode) tidak tersedia")
    if not data.rows:
        raise HTTPException(400, "Belum ada item yang dipilih untuk dicetak.")

    total = 0
    for r in data.rows:
        if r.copies < 1 or r.copies > MAX_COPIES_PER_ROW:
            raise HTTPException(400, f"Jumlah label per item harus 1–{MAX_COPIES_PER_ROW}.")
        total += r.copies
    if total > MAX_LABELS:
        raise HTTPException(400, f"Total {total} label melebihi batas {MAX_LABELS} lembar "
                                 f"per cetak. Pecah menjadi beberapa kali cetak.")

    db = get_db()
    ids = [r.id for r in data.rows if r.id]
    codes = [r.code for r in data.rows if r.code]
    found = await db.rahaza_materials.find(
        {"$or": [{"id": {"$in": ids}}, {"code": {"$in": codes}}, {"sku": {"$in": codes}}]},
        {"_id": 0}).to_list(MASTER_LIMIT)
    by_id = {m["id"]: m for m in found if m.get("id")}
    by_code = {}
    for m in found:
        for key in (m.get("code"), m.get("sku")):
            if key:
                by_code.setdefault(key, m)

    docs, missing, wrong_kind = [], [], []
    resolved_rows = []
    for r in data.rows:
        mat = by_id.get(r.id) if r.id else None
        if not mat and r.code:
            mat = by_code.get(r.code)
        if not mat:
            missing.append(r.code or r.id or "?")
            continue
        is_fg = mat.get("type") == "fg"
        if (kind == "fg") != is_fg:
            wrong_kind.append(mat.get("code"))
            continue
        docs.extend([mat] * r.copies)
        resolved_rows.append({"material_id": mat.get("id"), "code": mat.get("code"),
                              "name": mat.get("name"), "copies": r.copies})
    if missing:
        raise HTTPException(400, "Kode berikut tidak ada di master, jadi labelnya tidak "
                                 "dicetak (barcode harus bisa discan menjadi item yang "
                                 f"benar-benar ada): {', '.join(map(str, missing[:10]))}")
    if wrong_kind:
        raise HTTPException(400, f"Item {', '.join(map(str, wrong_kind[:10]))} bukan jenis "
                                 f"'{kind}'. Pindah ke tab yang sesuai.")

    if kind == "material" and data.include_stock:
        await _attach_stock(db, list({m["id"]: m for m in docs}.values()))

    pdf = lr.grid_labels_pdf(kind, docs, include_stock=data.include_stock,
                             title=f"Barcode {kind} ({len(docs)} label)")

    job = {
        "id": __import__("uuid").uuid4().hex,
        "job_number": await gen_prefixed_number(
            db, "wh_barcode_print_jobs", "job_number",
            f"BC-{_now().strftime('%Y%m%d')}-", 3),
        "kind": kind, "source": data.source if data.source in ("manual", "produksi") else "manual",
        "po_id": data.po_id, "note": (data.note or "")[:500],
        "rows": resolved_rows, "item_count": len(resolved_rows), "total_labels": len(docs),
        "include_stock": bool(data.include_stock),
        "created_at": _now(), "created_by": user.get("id"),
        "created_by_name": user.get("name") or user.get("email") or "",
    }
    await db.wh_barcode_print_jobs.insert_one(dict(job))
    await log_activity(user.get("id"), user.get("name", ""), "print",
                       "wms.barcode", job["job_number"])

    fname = f"barcode-{kind}-{job['job_number']}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{fname}"',
        "X-Barcode-Job": job["job_number"], "X-Barcode-Labels": str(len(docs)),
    })


@router.get("/history")
async def barcode_history(request: Request, limit: int = Query(30, ge=1, le=200),
                          kind: str = Query("")):
    await require_auth(request)
    db = get_db()
    flt = {}
    if kind:
        flt["kind"] = _check_kind(kind)
    rows = await db.wh_barcode_print_jobs.find(flt, {"_id": 0}).sort(
        "created_at", -1).limit(limit).to_list(limit)
    return serialize_doc(rows)
