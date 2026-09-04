"""core/material_issue_engine.py — SATU MESIN "KELUARKAN MATERIAL DARI GUDANG".

MENGAPA MODUL INI ADA (FASE H-1, 2026-08-15)
--------------------------------------------
Keluhan pemilik: *"kirim material ke cmt — bahan dikirimkan dan berkurang, tidak
perlu ada ketik ketik lagi, otomatis terbuat dan langsung berkurang saja,
begitupun aksesoris dan lainnya."*

Yang DIUKUR sebelum modul ini dibuat:
  · `POST /api/vendor-shipments` ("Kirim Material CMT") HANYA menulis
    `vendor_shipments` + `vendor_shipment_items`. Baris itemnya adalah **PO ITEM
    GARMEN** (`sku`, `size`, `color`, `qty_sent`) — tidak ada satu pun baris
    kain/aksesoris. Tidak ada mutasi `rahaza_material_stock`, tidak ada
    `rahaza_material_issues`, tidak ada jurnal.
    ⇒ kain & aksesoris keluar gudang ke CMT TANPA JEJAK; stok tidak pernah turun.
  · Layar "Pengeluaran Material" (`RahazaMaterialIssueModule`) tidak punya jalur
    CREATE sama sekali — hanya bisa meng-approve dokumen yang tidak pernah ada.
  · Satu-satunya pembuat MI dari UI memakai endpoint maklon yang sudah ditandai
    `deprecated=True`.

KEPUTUSAN DESAIN
----------------
1. TIDAK membuat mekanisme potong stok BARU. `issue_material_issue()` di bawah
   adalah inti `POST /material-issues/{id}/approve` yang DIEKSTRAK, sehingga
   "mengeluarkan material" punya SATU definisi: validasi stok per lokasi →
   `core.stock_service.issue()` (atomik, anti-race) → catat movement → posting GL
   `post_inventory_issue`. Kalau rumusnya berubah, dua-duanya ikut berubah.
   (Pelajaran Fase E: dua definisi untuk satu pertanyaan = angka bercabang.)
2. Kebutuhan material dihitung dari BOM aktif per (model, size) × qty dikirim,
   memakai konversi satuan SSOT `core.bom_uom` supaya "gram" tidak diperlakukan
   sebagai "kg".
3. Lokasi TIDAK diketik pemakai. Untuk setiap material dipilih lokasi dengan
   stok tersedia TERBANYAK — itu yang membuat alurnya "tanpa ketik-ketik".
4. Stok kurang ⇒ pengiriman DITOLAK dengan pesan yang menyebut angkanya
   (keputusan pemilik: jangan diteruskan menjadi stok minus).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MaterialShortage(Exception):
    """Stok material tidak cukup — pengiriman harus DITOLAK, bukan diteruskan."""

    def __init__(self, shortages: list):
        self.shortages = shortages
        lines = "; ".join(
            f"{s['material_code']} butuh {s['required']:g} {s.get('unit', '')} "
            f"tersedia {s['available']:g}" for s in shortages)
        super().__init__(f"Stok material tidak cukup: {lines}")


class BomMissing(Exception):
    """BOM tidak bisa dipakai — jangan menebak isi kiriman material."""


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 1. INTI PENGELUARAN (dipakai approve MI DAN kirim material ke CMT)
# ═════════════════════════════════════════════════════════════════════════════
async def issue_material_issue(db, mi: dict, user: dict, *, loc_overrides: dict | None = None,
                               ref_type: str | None = None) -> dict:
    """Keluarkan seluruh baris MI dari gudang. SATU definisi untuk semua pemanggil.

    Mengembalikan dict berisi dokumen MI terbaru + hasil posting GL.
    Melempar `MaterialShortage` bila ada baris yang stoknya kurang (TIDAK ADA
    baris yang dipotong bila salah satu kurang — semua atau tidak sama sekali).
    """
    from core import stock_service
    from routes.rahaza_inventory_shared import _enrich_mi, _log_movement, _now
    from routes.rahaza_posting import post_inventory_issue

    loc_overrides = loc_overrides or {}
    raw_items = list(mi.get("items") or [])
    default_ref = ref_type or ("wo_issue" if mi.get("work_order_id") else "manual_issue")

    # ── (a) kumpulkan pasangan (material, lokasi) lalu baca stoknya sekali ──
    pairs = set()
    for it in raw_items:
        loc = loc_overrides.get(it["material_id"]) or it.get("location_id")
        if loc and _f(it.get("qty_required")) > 0:
            pairs.add((it["material_id"], loc))
    stock_map = {}
    if pairs:
        mids = list({p[0] for p in pairs})
        locs = list({p[1] for p in pairs})
        async for s in db.rahaza_material_stock.find(
                {"material_id": {"$in": mids}, "location_id": {"$in": locs}}):
            stock_map[(s.get("material_id"), s.get("location_id"))] = s

    # ── (b) rencana + deteksi kekurangan SEBELUM memotong apa pun ──────────
    plan, shortages, no_loc = [], [], []
    mat_meta = {}
    async for m in db.rahaza_materials.find(
            {"id": {"$in": [i["material_id"] for i in raw_items]}},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1}):
        mat_meta[m["id"]] = m
    for it in raw_items:
        loc = loc_overrides.get(it["material_id"]) or it.get("location_id")
        qty = _f(it.get("qty_required"))
        if qty <= 0:
            continue
        meta = mat_meta.get(it["material_id"], {})
        if not loc:
            no_loc.append(meta.get("code") or it["material_id"])
            continue
        avail = _f((stock_map.get((it["material_id"], loc)) or {}).get("qty"))
        if avail + 1e-9 < qty:
            shortages.append({
                "material_id": it["material_id"],
                "material_code": meta.get("code") or it["material_id"],
                "material_name": meta.get("name") or "",
                "unit": meta.get("unit") or "",
                "required": round(qty, 4), "available": round(avail, 4),
                "location_id": loc,
            })
        plan.append({"material_id": it["material_id"], "location_id": loc,
                     "qty": qty, "item_id": it["id"]})
    if no_loc:
        raise BomMissing(
            "Material berikut tidak punya lokasi stok sama sekali di gudang: "
            + ", ".join(no_loc)
            + ". Catat penerimaan/opname dulu sebelum mengirim ke CMT.")
    if shortages:
        raise MaterialShortage(shortages)

    # ── (c) potong stok (atomik per baris) ────────────────────────────────
    race_failures = []
    for p in plan:
        try:
            await stock_service.issue(
                p["material_id"], p["location_id"], p["qty"],
                ref={"source": "material_issue", "mi_number": mi.get("mi_number"),
                     "item_id": p.get("item_id"), "ref_type": default_ref,
                     "ref_id": mi["id"]},
                actor={"id": str(user.get("id") or ""), "email": user.get("email", "")},
                db=db,
            )
        except stock_service.InsufficientStock:
            race_failures.append({"material_id": p["material_id"],
                                  "location_id": p["location_id"],
                                  "required": p["qty"]})
            continue
        await _log_movement(
            db, user, type="issue", material_id=p["material_id"], qty=p["qty"],
            from_location_id=p["location_id"], to_location_id=None,
            ref_type=default_ref, ref_id=mi["id"],
            notes=f"MI {mi.get('mi_number', '')}")
    if race_failures:
        raise MaterialShortage([{
            "material_id": f["material_id"],
            "material_code": (mat_meta.get(f["material_id"]) or {}).get("code", "?"),
            "material_name": "", "unit": "",
            "required": f["required"], "available": 0.0,
            "location_id": f["location_id"],
        } for f in race_failures])

    # ── (d) tutup dokumen + posting GL ────────────────────────────────────
    new_items = [{**it, "qty_issued": _f(it.get("qty_required")),
                  "location_id": loc_overrides.get(it["material_id"]) or it.get("location_id")}
                 for it in raw_items]
    await db.rahaza_material_issues.update_one(
        {"id": mi["id"]},
        {"$set": {"items": new_items, "status": "issued", "issued_at": _now(),
                  "issued_by": user.get("id"), "updated_at": _now()}})
    out = await db.rahaza_material_issues.find_one({"id": mi["id"]}, {"_id": 0})
    await _enrich_mi(db, out)
    posting = None
    try:
        posting = await post_inventory_issue(db, out, user)
    except Exception as e:  # noqa: BLE001
        logger.exception("posting jurnal pengeluaran material gagal (MI %s)",
                         mi.get("mi_number"))
        posting = {"ok": False, "error": str(e)}
    fresh = await db.rahaza_material_issues.find_one({"id": mi["id"]}, {"_id": 0})
    await _enrich_mi(db, fresh)
    fresh["_posting_result"] = posting
    return fresh


# ═════════════════════════════════════════════════════════════════════════════
# 2. KEBUTUHAN MATERIAL DARI BOM (per PO item × qty dikirim)
# ═════════════════════════════════════════════════════════════════════════════
async def _active_bom(db, model_id: str, size_id: str, color: str = ""):
    """Resolusi BOM aktif — memakai SSOT yang sama dengan MI dari job internal
    (`production_internal_adapter._active_bom`): BOM spesifik-warna → BOM umum →
    BOM apa pun untuk model+size. Sengaja TIDAK menulis resolusi sendiri supaya
    "BOM mana yang dipakai" punya satu jawaban di seluruh sistem."""
    from routes.production_internal_adapter import _active_bom as _resolve
    return await _resolve(db, model_id, size_id, color)


async def bom_need_for_lines(db, lines: list) -> tuple[dict, list, int]:
    """Hitung kebutuhan material dari BOM.

    `lines` = [{po_item_id, qty}] — qty dalam pcs garmen.
    Return (need_by_code, catatan[]) di mana need_by_code[code] = {name, unit,
    type, qty}.
    """
    from core import bom_uom
    from routes.rahaza_bom import _is_kglike

    poi_ids = [ln["po_item_id"] for ln in lines if ln.get("po_item_id")]
    po_items = {}
    if poi_ids:
        async for p in db.po_items.find({"id": {"$in": poi_ids}}, {"_id": 0}):
            po_items[p["id"]] = p

    need, notes, total_pcs = {}, [], 0
    for ln in lines:
        pi = po_items.get(ln.get("po_item_id")) or {}
        qty = int(_f(ln.get("qty")))
        if qty <= 0:
            continue
        total_pcs += qty
        model_id, size_id = pi.get("model_id"), pi.get("size_id")
        label = pi.get("sku") or pi.get("product_name") or ln.get("po_item_id")
        if not model_id or not size_id:
            notes.append(f"{label}: PO item belum tertaut model/ukuran master "
                         f"(model_id/size_id kosong) — BOM tidak bisa dibaca")
            continue
        bom = await _active_bom(db, model_id, size_id, pi.get("color") or "")
        if not bom:
            notes.append(f"{label}: tidak ada BOM aktif untuk model/ukuran ini")
            continue
        bom_mats, uom_warn = await bom_uom.ensure_uom(db, bom)
        for w in uom_warn:
            if w not in notes:
                notes.append(w)
        for m in bom_mats:
            code = (m.get("code") or "").strip().upper()
            if not code:
                continue
            base_unit = bom_uom.base_unit_of(m)
            is_kg = _is_kglike({**m, "unit": base_unit})
            e = need.setdefault(code, {
                "name": m.get("name") or code,
                "unit": base_unit or ("kg" if is_kg else "pcs"),
                "type": "yarn" if is_kg else "accessory",
                "qty": 0.0,
            })
            e["qty"] += bom_uom.qty_base_of(m) * qty
    return need, notes, total_pcs


async def best_location_for(db, material_id: str, qty_needed: float):
    """Lokasi dengan stok tersedia TERBANYAK — supaya pemakai tidak perlu memilih."""
    best, best_qty = None, -1.0
    async for s in db.rahaza_material_stock.find(
            {"material_id": material_id}, {"_id": 0, "location_id": 1, "qty": 1}):
        q = _f(s.get("qty"))
        if q > best_qty:
            best, best_qty = s.get("location_id"), q
    return best, max(0.0, best_qty)


# ═════════════════════════════════════════════════════════════════════════════
# 3. KIRIM MATERIAL KE CMT ⇒ MI OTOMATIS + STOK BERKURANG
# ═════════════════════════════════════════════════════════════════════════════
async def issue_for_vendor_shipment(db, shipment: dict, ship_items: list,
                                    user: dict) -> dict:
    """Terbitkan Material Issue OTOMATIS untuk satu surat jalan material ke CMT.

    Idempoten: bila surat jalan ini sudah punya MI, dokumen itu yang dikembalikan.
    """
    from routes.rahaza_inventory_shared import _uid, _gen_mi_number, _now

    existing = await db.rahaza_material_issues.find_one(
        {"vendor_shipment_id": shipment["id"], "status": {"$ne": "rejected"}}, {"_id": 0})
    if existing:
        return {"ok": True, "already": True, "mi": existing}

    lines = [{"po_item_id": it.get("po_item_id"), "qty": it.get("qty_sent")}
             for it in ship_items if it.get("po_item_id")]
    need, notes, total_pcs = await bom_need_for_lines(db, lines)
    if not need:
        raise BomMissing(
            "Kebutuhan material tidak bisa dihitung dari BOM, jadi tidak ada yang "
            "dikeluarkan dari gudang. Penyebab: "
            + ("; ".join(notes) if notes else "BOM kosong")
            + ". Lengkapi BOM model/ukuran di Master Produk lalu kirim ulang.")

    # ── resolve master material by code (JANGAN membuat master baru di sini:
    #    material yang tidak ada di master berarti BOM menunjuk barang yang tidak
    #    pernah masuk gudang — itu harus terlihat, bukan ditambal diam-diam) ──
    codes = list(need.keys())
    mats = {}
    async for m in db.rahaza_materials.find(
            {"code": {"$in": codes}, "active": True}, {"_id": 0}):
        mats[m["code"]] = m
    unknown = [c for c in codes if c not in mats]
    if unknown:
        raise BomMissing(
            "Material pada BOM belum ada di Master Item gudang: "
            + ", ".join(unknown)
            + ". Daftarkan materialnya (atau perbaiki kode di BOM) sebelum "
              "mengirim material ke CMT.")

    items, auto_loc, no_stock = [], {}, []
    for code, e in need.items():
        mat = mats[code]
        loc, avail = await best_location_for(db, mat["id"], e["qty"])
        if not loc:
            no_stock.append(f"{code} ({e['qty']:g} {e['unit']})")
            continue
        auto_loc[mat["id"]] = loc
        items.append({
            "id": _uid(), "material_id": mat["id"],
            "qty_required": round(e["qty"], 4),
            "qty_issued": 0, "location_id": loc, "notes": "",
        })
    if no_stock:
        raise BomMissing(
            "Material berikut belum punya baris stok di gudang mana pun: "
            + ", ".join(no_stock)
            + ". Catat penerimaan barang atau opname dulu.")

    mi = {
        "id": _uid(),
        "mi_number": await _gen_mi_number(db),
        "work_order_id": None,
        "wo_number_snapshot": "",
        "job_id": None,
        "vendor_shipment_id": shipment["id"],
        "vendor_shipment_number": shipment.get("shipment_number", ""),
        "vendor_id": shipment.get("vendor_id", ""),
        "vendor_name": shipment.get("vendor_name", ""),
        "production_po_id": shipment.get("po_id"),
        "po_number_snapshot": shipment.get("po_number", ""),
        "qty_wo_pcs": total_pcs,
        "items": items,
        "status": "pending_approval",
        "source": "vendor_shipment",
        "notes": ("Otomatis dari Kirim Material CMT "
                  f"{shipment.get('shipment_number', '')} (FASE H-1)"
                  + (f" · catatan BOM: {'; '.join(notes)}" if notes else "")),
        "bom_notes": notes,
        "created_by": user.get("id"), "created_by_name": user.get("name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_material_issues.insert_one(dict(mi))
    fresh = await issue_material_issue(db, mi, user, loc_overrides=auto_loc,
                                       ref_type="cmt_material_issue")
    await db.vendor_shipments.update_one(
        {"id": shipment["id"]},
        {"$set": {"material_issue_id": mi["id"],
                  "material_issue_number": mi["mi_number"]}})
    return {"ok": True, "already": False, "mi": fresh,
            "mi_number": mi["mi_number"], "bom_notes": notes,
            "total_pcs": total_pcs, "material_lines": len(items)}
