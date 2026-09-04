"""core/fg_cost_layers.py — **SSOT HPP BATCH (FIFO) barang jadi**.

KENAPA MODUL INI ADA (diukur 2026-08-23)
----------------------------------------
Sebelum modul ini, HPP barang jadi hanya punya SATU angka per SKU
(`rahaza_materials.hpp`) yang ditulis kalkulator (`core/product_costing`) dari
BOM + tarif upah. Akibat nyata:

* **Biaya jahit batch tidak pernah masuk.** `po_items.cmt_price_snapshot`
  (upah jahit/pcs) selalu 0 untuk SPK produksi internal — tidak ada pintu
  inputnya (`routes/production_internal_adapter.py`). Jadi HPP hanya bahan.
* **Permak tidak pernah masuk.** `dewi_cmt_permak.total_cost` (ongkos perbaikan)
  hidup sendiri; HPP barang yang dipermak sama dengan yang tidak.
* **Satu angka tidak bisa menjawab "batch mana".** Kain naik harga ⇒ HPP batch
  baru berbeda dari batch lama yang MASIH ada di gudang. Satu angka memaksa
  memilih salah satu, dan siapa pun yang melihat margin tidak tahu yang mana.

Modul ini menyimpan **lapisan biaya per batch** (FIFO) untuk tiap SKU barang jadi:

    lapisan = { material_id (FG), qty_in, qty_remaining, unit_cost,
                rincian{bahan, jahit, permak, internal, overhead},
                batch{po_id, po_number, receipt_id, job_item_id}, created_at }

Lapisan LAHIR saat barang jadi lolos QC dan masuk gudang FG (satu pintu:
`core.production_qty_ledger.post_fg_accepted`), dan DIPAKAI (FIFO: yang tertua
dulu) saat barang jadi keluar untuk dijual/dikirim.

ANGKA YANG DIPAKAI LAYAR (keputusan pemilik 2026-08-23)
-------------------------------------------------------
* `hpp_fifo_avg` — **rata-rata tertimbang lapisan yang MASIH ada stoknya**. Ini
  angka yang dipakai Katalog Marketing untuk margin, karena inilah biaya barang
  yang benar-benar bisa dijual hari ini.
* `hpp_last_batch` — biaya batch terakhir masuk (untuk melihat tren).
* Kalau BELUM ada lapisan sama sekali, modul ini **tidak mengarang**: ia
  mengembalikan `source='none'` dan layar wajib menampilkan HPP kalkulator
  (BOM) beserta keterangan bahwa itu perkiraan, bukan biaya nyata.

ATURAN JUJUR
------------
1. Lapisan tidak pernah dihapus; yang habis hanya `qty_remaining=0` (jejak audit).
2. `unit_cost` selalu menyimpan RINCIAN + `source` tiap komponennya; komponen
   yang tidak diketahui ditulis 0 **dan** dicatat di `gaps[]` — tidak pernah
   ditebak.
3. FIFO keluar memakai `qty_remaining` lapisan tertua; kalau stok lapisan kurang
   dari qty keluar, sisanya dicatat `uncosted_qty` (bukan dipaksa memakai
   lapisan terakhir), supaya "barang keluar tanpa biaya" TERLIHAT.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

LAYERS = "fg_cost_layers"
CONSUMPTIONS = "fg_cost_consumptions"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _f(v, d: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(d)
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _r(v, nd: int = 2) -> float:
    return round(_f(v), nd)


# ══════════════════════════════════════════════════════════════════════════════
# MENGHITUNG BIAYA SATU BATCH
# ══════════════════════════════════════════════════════════════════════════════
async def compute_batch_unit_cost(db, *, po_item: dict, qty: int) -> dict:
    """Biaya per pcs satu batch = bahan (BOM) + upah jahit (SPK) + permak + internal.

    Semua komponen menyebut ASALNYA. Komponen yang belum ada tidak ditebak.
    """
    from core import product_costing as pc

    out = {
        "material_cost": 0.0, "material_source": "none",
        "sewing_cost": 0.0, "sewing_source": "none",
        "permak_cost": 0.0, "permak_source": "none",
        "internal_labor_cost": 0.0, "internal_labor_source": "none",
        "overhead_cost": 0.0,
        "unit_cost": 0.0, "gaps": [],
    }
    model_id = (po_item or {}).get("model_id") or ""
    size_id = (po_item or {}).get("size_id") or ""

    # ── bahan: BOM × harga master (SSOT core/product_costing) ────────────────
    if model_id and size_id:
        try:
            mc = await pc.compute_material_cost(db, model_id, size_id)
            if mc.get("bom_id"):
                out["material_cost"] = _r(mc.get("material_cost"))
                out["material_source"] = "bom"
                if mc.get("unvalued_count"):
                    out["gaps"].append(
                        f"{mc['unvalued_count']} bahan belum punya harga — biaya bahan batch ini "
                        f"lebih rendah dari kenyataan")
            else:
                out["gaps"].append("BOM model/ukuran ini belum ada — biaya bahan batch belum bisa dihitung")
        except Exception:  # noqa: BLE001
            logger.exception("compute_material_cost gagal (model=%s size=%s)", model_id, size_id)
            out["gaps"].append("biaya bahan gagal dihitung — periksa BOM & satuan bahan")
    else:
        out["gaps"].append("item SPK tidak menunjuk model/ukuran — biaya bahan tidak bisa dihitung")

    # ── upah jahit: DIINPUT di SPK (po_items.cmt_price_snapshot) ─────────────
    rate = _f((po_item or {}).get("cmt_price_snapshot"))
    if rate > 0:
        out["sewing_cost"] = _r(rate)
        out["sewing_source"] = "spk"
    else:
        out["gaps"].append("biaya jahit/pcs SPK ini belum diisi — isi di layar Biaya Jahit SPK")

    # ── permak: ongkos perbaikan item ini, dibagi qty batch ─────────────────
    pid = (po_item or {}).get("id")
    if pid and qty > 0:
        rows = await db.dewi_cmt_permak.find(
            {"po_item_id": pid}, {"_id": 0, "total_cost": 1, "cost_per_pcs": 1, "qty": 1}
        ).to_list(500)
        total = sum(_f(r.get("total_cost")) or _f(r.get("cost_per_pcs")) * _f(r.get("qty")) for r in rows)
        if total > 0:
            out["permak_cost"] = _r(total / qty)
            out["permak_source"] = f"permak ({len(rows)} dokumen, dibagi {qty} pcs batch)"

    # ── upah internal (cutting dll) + overhead: dari kalkulator model ────────
    if model_id:
        try:
            model = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
            if model:
                st = await pc.get_settings(db)
                ov = await pc.get_override(db, model_id)
                lab = await pc.resolve_internal_labor(db, model, override=ov, settings=st)
                if _f(lab.get("rate")) > 0:
                    out["internal_labor_cost"] = _r(lab["rate"])
                    out["internal_labor_source"] = lab.get("source") or "none"
                if st.get("include_overhead_in_product_hpp"):
                    out["overhead_cost"] = _r(st.get("overhead_rate_per_pcs"))
        except Exception:  # noqa: BLE001
            logger.exception("resolve_internal_labor gagal (model=%s)", model_id)

    out["unit_cost"] = _r(out["material_cost"] + out["sewing_cost"] + out["permak_cost"]
                          + out["internal_labor_cost"] + out["overhead_cost"])
    return out


# ══════════════════════════════════════════════════════════════════════════════
# LAPISAN MASUK
# ══════════════════════════════════════════════════════════════════════════════
async def push_layer(db, *, material_id: str, qty: int, po_item: dict | None = None,
                     ref: dict | None = None, actor: dict | None = None,
                     unit_cost: float | None = None,
                     breakdown: dict | None = None) -> dict:
    """Catat satu lapisan biaya batch untuk SKU barang jadi `material_id`."""
    qty = int(_f(qty))
    if not material_id or qty <= 0:
        return {}
    if unit_cost is None:
        calc = await compute_batch_unit_cost(db, po_item=po_item or {}, qty=qty)
        unit_cost = calc["unit_cost"]
        breakdown = calc
    doc = {
        "id": _uid(),
        "material_id": material_id,
        "sku": (po_item or {}).get("sku") or "",
        "model_id": (po_item or {}).get("model_id") or "",
        "size_id": (po_item or {}).get("size_id") or "",
        "qty_in": qty,
        "qty_remaining": qty,
        "unit_cost": _r(unit_cost),
        "total_cost": _r(_f(unit_cost) * qty),
        "breakdown": {k: v for k, v in (breakdown or {}).items() if k != "gaps"},
        "gaps": (breakdown or {}).get("gaps") or [],
        "batch": {
            "po_id": (po_item or {}).get("po_id") or (ref or {}).get("po_id") or "",
            "po_number": (po_item or {}).get("po_number") or (ref or {}).get("po_number") or "",
            "po_item_id": (po_item or {}).get("id") or "",
            "receipt_id": (ref or {}).get("receipt_id") or "",
            "receipt_code": (ref or {}).get("receipt_code") or "",
            "source": (ref or {}).get("type") or "production",
        },
        "created_at": _now(),
        "created_by": (actor or {}).get("name") or (actor or {}).get("email") or "system",
    }
    await db[LAYERS].insert_one(doc)
    await refresh_master_hpp(db, material_id)
    doc.pop("_id", None)
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# LAPISAN KELUAR (FIFO)
# ══════════════════════════════════════════════════════════════════════════════
async def consume_fifo(db, *, material_id: str, qty: int, ref: dict | None = None,
                       actor: dict | None = None) -> dict:
    """Ambil biaya dari lapisan tertua. Sisa yang tidak tertutup lapisan DILAPORKAN."""
    qty = int(_f(qty))
    out = {"material_id": material_id, "qty": qty, "cogs": 0.0,
           "layers_used": [], "uncosted_qty": 0}
    if not material_id or qty <= 0:
        return out
    left = qty
    layers = await db[LAYERS].find(
        {"material_id": material_id, "qty_remaining": {"$gt": 0}},
        {"_id": 0}).sort("created_at", 1).to_list(500)
    for ly in layers:
        if left <= 0:
            break
        take = min(left, int(_f(ly.get("qty_remaining"))))
        if take <= 0:
            continue
        await db[LAYERS].update_one({"id": ly["id"]},
                                    {"$inc": {"qty_remaining": -take},
                                     "$set": {"updated_at": _now()}})
        cost = _r(_f(ly.get("unit_cost")) * take)
        out["cogs"] = _r(out["cogs"] + cost)
        out["layers_used"].append({"layer_id": ly["id"], "qty": take,
                                   "unit_cost": _r(ly.get("unit_cost")),
                                   "total": cost,
                                   "po_number": (ly.get("batch") or {}).get("po_number") or ""})
        left -= take
    out["uncosted_qty"] = max(0, left)
    if out["layers_used"] or out["uncosted_qty"]:
        await db[CONSUMPTIONS].insert_one({
            "id": _uid(), "material_id": material_id, "qty": qty,
            "cogs": out["cogs"], "uncosted_qty": out["uncosted_qty"],
            "layers_used": out["layers_used"], "ref": ref or {},
            "actor": (actor or {}).get("name") or "system", "created_at": _now(),
        })
    await refresh_master_hpp(db, material_id)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ANGKA YANG DIBACA LAYAR
# ══════════════════════════════════════════════════════════════════════════════
async def hpp_snapshot(db, material_id: str) -> dict:
    """HPP batch untuk satu SKU FG: rata-rata lapisan sisa + batch terakhir."""
    res = {"material_id": material_id, "source": "none",
           "hpp_fifo_avg": 0.0, "hpp_last_batch": 0.0, "qty_on_layers": 0,
           "layer_count": 0, "open_layer_count": 0, "layers": [], "gaps": []}
    rows = await db[LAYERS].find({"material_id": material_id}, {"_id": 0}
                                 ).sort("created_at", -1).to_list(200)
    if not rows:
        return res
    res["layer_count"] = len(rows)
    res["hpp_last_batch"] = _r(rows[0].get("unit_cost"))
    open_rows = [r for r in rows if _f(r.get("qty_remaining")) > 0]
    res["open_layer_count"] = len(open_rows)
    qty = sum(_f(r.get("qty_remaining")) for r in open_rows)
    res["qty_on_layers"] = int(qty)
    if qty > 0:
        res["hpp_fifo_avg"] = _r(
            sum(_f(r.get("unit_cost")) * _f(r.get("qty_remaining")) for r in open_rows) / qty)
        res["source"] = "fifo_remaining"
    else:
        # semua lapisan habis — angka terakhir yang PERNAH nyata tetap berguna,
        # tetapi harus MENGAKU bahwa stoknya nol.
        res["hpp_fifo_avg"] = res["hpp_last_batch"]
        res["source"] = "fifo_last_batch_no_stock"
    res["layers"] = [{
        "id": r["id"], "qty_in": r.get("qty_in"), "qty_remaining": r.get("qty_remaining"),
        "unit_cost": _r(r.get("unit_cost")), "breakdown": r.get("breakdown") or {},
        "batch": r.get("batch") or {}, "gaps": r.get("gaps") or [],
        "created_at": (r.get("created_at").isoformat()
                       if isinstance(r.get("created_at"), datetime) else r.get("created_at")),
    } for r in rows[:50]]
    all_gaps = []
    for r in open_rows:
        for g in (r.get("gaps") or []):
            if g not in all_gaps:
                all_gaps.append(g)
    res["gaps"] = all_gaps
    return res


async def hpp_map(db, material_ids: list[str]) -> dict:
    """Versi massal (dipakai daftar katalog/stok) — {material_id: {avg,last,qty}}."""
    ids = [m for m in (material_ids or []) if m]
    if not ids:
        return {}
    rows = await db[LAYERS].find({"material_id": {"$in": ids}}, {"_id": 0}).to_list(5000)
    acc: dict = {}
    for r in rows:
        mid = r["material_id"]
        slot = acc.setdefault(mid, {"qty": 0.0, "value": 0.0, "last": 0.0,
                                    "last_at": None, "layers": 0})
        slot["layers"] += 1
        rem = _f(r.get("qty_remaining"))
        if rem > 0:
            slot["qty"] += rem
            slot["value"] += rem * _f(r.get("unit_cost"))
        at = r.get("created_at")
        if slot["last_at"] is None or (at and at > slot["last_at"]):
            slot["last_at"] = at
            slot["last"] = _f(r.get("unit_cost"))
    out = {}
    for mid, s in acc.items():
        avg = (s["value"] / s["qty"]) if s["qty"] > 0 else s["last"]
        out[mid] = {
            "hpp_fifo_avg": _r(avg), "hpp_last_batch": _r(s["last"]),
            "qty_on_layers": int(s["qty"]), "layer_count": s["layers"],
            "source": "fifo_remaining" if s["qty"] > 0 else "fifo_last_batch_no_stock",
        }
    return out


async def refresh_master_hpp(db, material_id: str) -> dict:
    """Tuliskan HPP FIFO ke master FG + item katalog marketing (satu pintu).

    Master tetap SSOT untuk layar mana pun yang membaca `hpp`; kolom tambahan
    `hpp_fifo_avg` / `hpp_last_batch` menyimpan asal angkanya supaya tidak ada
    yang harus menebak apa arti `hpp`.
    """
    snap = await hpp_snapshot(db, material_id)
    if snap["source"] == "none":
        return snap
    await db.rahaza_materials.update_one(
        {"id": material_id},
        {"$set": {"hpp": snap["hpp_fifo_avg"], "hpp_source": "fifo_batch",
                  "hpp_fifo_avg": snap["hpp_fifo_avg"],
                  "hpp_last_batch": snap["hpp_last_batch"],
                  "hpp_layer_qty": snap["qty_on_layers"],
                  "hpp_updated_at": _now()}})
    mat = await db.rahaza_materials.find_one({"id": material_id},
                                             {"_id": 0, "code": 1, "id": 1})
    if mat:
        await db.marketing_catalog_items.update_many(
            {"$or": [{"fg_product_id": material_id},
                     {"sku": mat.get("code")}]},
            {"$set": {"hpp": snap["hpp_fifo_avg"], "hpp_source": "fifo_batch",
                      "hpp_fifo_avg": snap["hpp_fifo_avg"],
                      "hpp_last_batch": snap["hpp_last_batch"],
                      "hpp_updated_at": _now()}})
    return snap
