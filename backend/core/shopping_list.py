"""core/shopping_list.py — SSOT **DAFTAR BELANJA MINGGUAN** (sesi #33).

═══════════════════════════════════════════════════════════════════════════════
MASALAH YANG DISELESAIKAN (terukur 2026-08-23, data hidup)
═══════════════════════════════════════════════════════════════════════════════
Sampai sesi #32 tidak ada satu pun layar/endpoint yang menjawab pertanyaan
pemilik: **"minggu ini saya harus belanja apa, berapa banyak, dan kira-kira
berapa uangnya?"**. Yang ada:
  · `GET /api/warehouse/smart-reorder` — hanya mengusulkan TITIK PESAN ULANG
    (angka ambang), bukan "beli berapa".
  · `GET /api/rahaza/materials/reorder-alerts` — hanya bilang "kurang n",
    tanpa satuan beli, tanpa harga, tanpa jembatan ke Permintaan Pengadaan ⇒
    hasilnya harus DIKETIK ULANG manual sebagai PR.

Keputusan pemilik sesi #33: basis kebutuhan **HANYA ambang minimum / titik pesan
ulang** (bukan BOM/kebutuhan produksi). Maka satu-satunya definisi "perlu beli"
di berkas ini datang dari SSOT `core/stock_thresholds` — tidak ada rumus kedua.

ATURAN JUJUR YANG DITEGAKKAN DI SINI
  1. Stok SELALU dibaca kanonik (`core/stock_service.onhand_map`) — semua lokasi,
     semua skema baris.
  2. Qty beli dibulatkan **KE ATAS** ke satuan BELI (`core/uom.purchase_uom_of`
     + `core/bom_uom.factor_to_base`) — memesan 11,67 lusin tidak mungkin.
  3. MOQ supplier NYATA (`rahaza_supplier_price_lists`) menaikkan qty, dan
     ALASANNYA disebut di baris itu.
  4. Harga: harga supplier aktif TERMURAH bila ada, kalau tidak ada memakai HPP
     rata-rata bergerak hasil pembelian (`unit_cost`). Sumbernya SELALU disebut.
     Barang tanpa harga ⇒ `value_status='unvalued'` dan **tidak** diam-diam
     menambah Rp0 ke total.
  5. Barang yang **belum punya ambang** tidak bisa dinilai butuh/tidak ⇒ tidak
     diusulkan, TETAPI dihitung dan DIKATAKAN (dengan jalan keluarnya).
  6. ANTI DOBEL BELANJA: barang yang sudah punya PR/PO terbuka di minggu ISO ini
     ditandai + tidak dihitung sebagai "perlu dibeli".
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from core import bom_uom as _bom_uom
from core import stock_service, stock_thresholds
from core import uom as _uom

MASTER = "rahaza_materials"
PRICE_LIST = "rahaza_supplier_price_lists"
PR_COLL = "dewi_procurement_requests"
PO_COLL = "rahaza_purchase_orders"

PR_DEAD = ("rejected", "cancelled", "canceled", "closed")
PO_DEAD = ("rejected", "cancelled", "canceled", "closed", "completed")
ORIGIN = "weekly_shopping_list"


def _f(v) -> float:
    try:
        if v in (None, ""):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _now():
    return datetime.now(timezone.utc)


def week_window(ref: datetime | None = None) -> dict:
    """Minggu ISO (Senin 00:00 → Minggu 23:59) tempat tanggal `ref` berada."""
    ref = ref or _now()
    start = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0,
                                                          microsecond=0)
    end = start + timedelta(days=7) - timedelta(microseconds=1)
    iso = ref.isocalendar()
    return {
        "iso": f"{iso[0]}-W{int(iso[1]):02d}",
        "year": int(iso[0]),
        "week": int(iso[1]),
        "start": start,
        "end": end,
        "label": f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}",
    }


def _ceil_to_uom(qty_base: float, factor: float) -> float:
    """Bulatkan KE ATAS ke satuan beli. Toleransi 1e-6 agar 144/12 tidak jadi 13."""
    if factor <= 0:
        return round(qty_base, 4)
    return float(math.ceil(round(qty_base / factor, 6) - 1e-9))


async def _price_index(db, material_ids: list) -> dict:
    """Harga supplier aktif TERMURAH per material (per satuan dasar) + MOQ."""
    ids = [m for m in (material_ids or []) if m]
    if not ids:
        return {}
    rows = await db[PRICE_LIST].find(
        {"material_id": {"$in": ids}, "is_active": True}, {"_id": 0}).to_list(5000)
    sup_ids = list({r.get("supplier_id") for r in rows if r.get("supplier_id")})
    sup_names = {}
    if sup_ids:
        for s in await db.rahaza_suppliers.find(
                {"id": {"$in": sup_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(sup_ids) + 5):
            sup_names[s["id"]] = s.get("name") or ""
    best: dict = {}
    for r in rows:
        mid = r.get("material_id")
        pb = _f(r.get("price_base"))
        if pb <= 0:
            continue
        cur = best.get(mid)
        if cur and _f(cur.get("price_base")) <= pb:
            continue
        best[mid] = {
            "supplier_id": r.get("supplier_id"),
            "name": sup_names.get(r.get("supplier_id")) or r.get("supplier_name") or "",
            "price": round(_f(r.get("price")), 4),
            "price_base": round(pb, 6),
            "uom": r.get("uom") or "",
            "moq": round(_f(r.get("moq")), 4),
            "moq_base": round(_f(r.get("moq_base")), 4),
            "lead_time_days": int(_f(r.get("lead_time_days")) or 0),
            "valid_from": r.get("valid_from"),
        }
    return best


async def _open_orders(db, material_ids: list, since: datetime) -> dict:
    """PR/PO terbuka minggu ini per material — dasar ANTI DOBEL BELANJA."""
    ids = set(m for m in (material_ids or []) if m)
    if not ids:
        return {}
    out: dict = {}
    prs = await db[PR_COLL].find(
        {"created_at": {"$gte": since}, "status": {"$nin": list(PR_DEAD)},
         "items.material_id": {"$in": list(ids)}}, {"_id": 0}).to_list(2000)
    for pr in prs:
        for it in (pr.get("items") or []):
            mid = it.get("material_id")
            if mid in ids and mid not in out:
                out[mid] = {
                    "type": "pr", "id": pr.get("id"), "number": pr.get("request_number") or "",
                    "status": pr.get("status") or "", "created_at": pr.get("created_at"),
                    "qty": round(_f(it.get("qty")), 4), "uom": it.get("uom") or "",
                    "origin": pr.get("origin") or "",
                    "label": f"PR {pr.get('request_number') or ''} ({pr.get('status') or ''})",
                }
    pos = await db[PO_COLL].find(
        {"created_at": {"$gte": since}, "status": {"$nin": list(PO_DEAD)},
         "items.material_id": {"$in": list(ids)}}, {"_id": 0}).to_list(2000)
    for po in pos:
        for it in (po.get("items") or []):
            mid = it.get("material_id")
            if mid in ids and mid not in out:
                out[mid] = {
                    "type": "po", "id": po.get("id"), "number": po.get("po_number") or "",
                    "status": po.get("status") or "", "created_at": po.get("created_at"),
                    "qty": round(_f(it.get("qty_ordered")), 4), "uom": it.get("uom") or "",
                    "origin": "",
                    "label": f"PO {po.get('po_number') or ''} ({po.get('status') or ''})",
                }
    return out


async def weekly(db, *, types: list | None = None, search: str = "",
                 include_requested: bool = True, limit: int = 5000,
                 ref: datetime | None = None) -> dict:
    """Daftar belanja minggu ini — satu baris per barang yang menyentuh ambang."""
    wk = week_window(ref)
    q: dict = {"active": True}
    if types:
        q["type"] = {"$in": types}
    if (search or "").strip():
        import re
        pat = re.compile(re.escape(search.strip()), re.IGNORECASE)
        q["$or"] = [{"code": pat}, {"name": pat}]
    mats = await db[MASTER].find(q, {"_id": 0}).sort([("type", 1), ("code", 1)]).to_list(limit)
    ids = [m["id"] for m in mats if m.get("id")]
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}

    need_ids, staged = [], []
    with_threshold = 0
    for m in mats:
        th = stock_thresholds.resolve_threshold(m)
        if th["has_threshold"]:
            with_threshold += 1
        qty = round(_f(onhand.get(m.get("id"), 0)), 4)
        status = stock_thresholds.status_of(qty, th)
        if not th["has_threshold"] or status not in ("low", "critical"):
            continue
        shortage = round(max(0.0, th["alert_at"] - qty), 4)
        if shortage <= 0:
            continue
        staged.append((m, th, qty, status, shortage))
        need_ids.append(m["id"])

    prices = await _price_index(db, need_ids)
    open_orders = await _open_orders(db, need_ids, wk["start"])

    rows = []
    for m, th, qty, status, shortage in staged:
        mid = m["id"]
        base = _uom.base_uom_of(m)
        p_uom = _uom.purchase_uom_of(m) or base
        try:
            factor, f_source = _bom_uom.factor_to_base(m, p_uom)
        except Exception:  # noqa: BLE001 — satuan beli rusak tidak boleh mematikan layar
            factor, f_source, p_uom = 1.0, "base", base
        factor = float(factor) or 1.0

        sup = prices.get(mid)
        notes = []
        qty_target = shortage
        moq_base = _f((sup or {}).get("moq_base"))
        if moq_base > qty_target:
            qty_target = moq_base
            notes.append(f"dinaikkan ke MOQ supplier {moq_base:g} {base}")
        qty_buy = _ceil_to_uom(qty_target, factor)
        qty_buy_base = round(qty_buy * factor, 4)
        if factor != 1 and qty_buy_base > round(qty_target, 4) + 1e-6:
            notes.append(f"dibulatkan ke atas ke satuan beli {p_uom} (1 {p_uom} = {factor:g} {base})")

        unit_cost = _f(m.get("unit_cost"))
        if sup and _f(sup.get("price_base")) > 0:
            price_base, price_source = _f(sup["price_base"]), "supplier_price_list"
        elif unit_cost > 0:
            price_base, price_source = unit_cost, "moving_average"
        else:
            price_base, price_source = 0.0, "none"
        valued = price_base > 0
        est_total = round(qty_buy_base * price_base, 2) if valued else 0.0
        order = open_orders.get(mid)

        row = {
            "material_id": mid,
            "code": m.get("code") or "",
            "name": m.get("name") or "",
            "type": m.get("type") or "",
            "category_name": m.get("category_name") or "",
            "unit": m.get("unit") or base,
            "base_uom": base,
            "purchase_uom": p_uom,
            "purchase_factor": round(factor, 6),
            "purchase_factor_source": f_source,
            "onhand": qty,
            "min_qty": th["min_qty"],
            "reorder_point": th["reorder_point"],
            "alert_at": th["alert_at"],
            "threshold_source": th["threshold_source"],
            "threshold_basis": m.get("threshold_basis") or "",
            "threshold_basis_note": m.get("threshold_basis_note") or "",
            "stock_status": status,
            "shortage": shortage,
            "qty_buy": qty_buy,
            "qty_buy_base": qty_buy_base,
            "qty_note": " · ".join(notes),
            "unit_cost": round(unit_cost, 4),
            "price_base": round(price_base, 6),
            "price_per_purchase_uom": round(price_base * factor, 4),
            "price_source": price_source,
            "price_note": (
                f"harga supplier {(sup or {}).get('name') or ''} "
                f"{_f((sup or {}).get('price')):,.2f}/{(sup or {}).get('uom') or base}"
                if price_source == "supplier_price_list" else
                ("HPP rata-rata bergerak hasil pembelian" if price_source == "moving_average"
                 else "belum ada harga — isi lewat penerimaan pembelian atau koreksi HPP")),
            "est_total": est_total,
            "valued": valued,
            "value_status": "valued" if valued else "unvalued",
            "supplier": sup,
            "pr": order,
            "already_requested": bool(order),
        }
        if include_requested or not order:
            rows.append(row)

    rows.sort(key=lambda r: (r["already_requested"], not r["valued"], -r["est_total"],
                             -r["shortage"]))
    pending = [r for r in rows if not r["already_requested"]]
    without_threshold = len(mats) - with_threshold
    summary = {
        "week": wk["iso"],
        "week_label": wk["label"],
        "total_materials": len(mats),
        "with_threshold": with_threshold,
        "without_threshold": without_threshold,
        "without_threshold_note": (
            f"{without_threshold} dari {len(mats)} barang belum punya ambang minimum, jadi "
            f"sistem tidak bisa menilai barang itu perlu dibeli atau tidak — daftar ini BELUM "
            f"lengkap. Isi ambangnya massal di Master Item → tab Ambang Stok."
            if without_threshold else
            "Semua barang aktif sudah punya ambang minimum — daftar ini lengkap."),
        "rows": len(rows),
        "need_buy": len(pending),
        "est_total_value": round(sum(r["est_total"] for r in pending if r["valued"]), 2),
        "unvalued_count": sum(1 for r in pending if not r["valued"]),
        "unvalued_note": ("Barang tanpa harga TIDAK dihitung ke perkiraan total — harganya "
                          "lahir dari penerimaan pembelian, bukan ketikan."),
        "already_requested_count": sum(1 for r in rows if r["already_requested"]),
        "critical": sum(1 for r in pending if r["stock_status"] == "critical"),
        "with_supplier": sum(1 for r in pending if r.get("supplier")),
    }
    return {"week": {**wk, "start": wk["start"], "end": wk["end"]}, "rows": rows,
            "summary": summary}


async def build_pr_items(db, material_ids: list, *, ref: datetime | None = None) -> dict:
    """Siapkan baris PR dari daftar mingguan (angka SAMA dengan yang dilihat pemilik)."""
    ids = [str(m) for m in (material_ids or []) if m]
    if not ids:
        return {"items": [], "skipped": [], "rows": [], "week": week_window(ref)}
    data = await weekly(db, limit=20000, ref=ref)
    by_id = {r["material_id"]: r for r in data["rows"]}
    items, skipped, used = [], [], []
    for mid in ids:
        r = by_id.get(mid)
        if not r:
            skipped.append({"material_id": mid,
                            "reason": "tidak ada di daftar belanja minggu ini (stok sudah cukup, "
                                      "ambangnya belum diisi, atau barangnya tidak aktif)"})
            continue
        if r["already_requested"]:
            skipped.append({"material_id": mid, "code": r["code"],
                            "reason": f"sudah ada {(r.get('pr') or {}).get('label') or 'permintaan'} "
                                      f"minggu ini — anti dobel belanja"})
            continue
        items.append({
            "material_id": mid,
            "name": r["name"],
            "qty": r["qty_buy"],
            "uom": r["purchase_uom"],
            "estimated_price": r["price_per_purchase_uom"],
            "suggested_supplier_id": (r.get("supplier") or {}).get("supplier_id"),
            "notes": (f"stok {r['onhand']:g} {r['base_uom']} di bawah ambang "
                      f"{r['alert_at']:g} ⇒ kurang {r['shortage']:g}"
                      + (f" · {r['qty_note']}" if r["qty_note"] else "")
                      + f" · harga: {r['price_note']}"),
        })
        used.append(r)
    return {"items": items, "skipped": skipped, "rows": used, "week": data["week"]}


async def created_history(db, *, limit: int = 100) -> dict:
    """PR yang LAHIR dari layar Daftar Belanja Mingguan (jejak, bukan tebakan)."""
    rows = await db[PR_COLL].find({"origin": ORIGIN}, {"_id": 0}).sort(
        "created_at", -1).to_list(max(1, min(limit, 500)))
    out = []
    for pr in rows:
        out.append({
            "id": pr.get("id"), "number": pr.get("request_number") or "",
            "status": pr.get("status") or "", "week": pr.get("origin_week") or "",
            "created_at": pr.get("created_at"), "title": pr.get("title") or "",
            "lines": len(pr.get("items") or []),
            "total_estimated": round(_f(pr.get("total_estimated")), 2),
            "requested_by_name": pr.get("requested_by_name") or "",
            "materials": [{"material_id": i.get("material_id"), "code": i.get("material_code"),
                           "name": i.get("name"), "qty": _f(i.get("qty")),
                           "uom": i.get("uom")} for i in (pr.get("items") or [])],
        })
    return {"items": out, "total": len(out),
            "summary": {"requests": len(out),
                        "total_value": round(sum(r["total_estimated"] for r in out), 2)}}
