"""core.returns_bridge — SESI #29 (W4, permintaan pemilik).

**JEMBATAN SATU-ARAH: retur pembeli (Marketing) → Retur Fisik (Gudang) → STOK.**

═══════════════════════════════════════════════════════════════════════════════
MASALAH YANG DIUKUR SEBELUM MODUL INI ADA (2026-08-19, DB preview)
═══════════════════════════════════════════════════════════════════════════════
  · `marketing_returns`      = **30 dokumen** (retur pembeli NYATA)
  · `wh_returns`             = **0 dokumen**  ⇒ layar "Retur Fisik" gudang KOSONG
                               SELAMANYA
  · `production_returns`     = 0, `production_return_items` = 0
  · Jembatan yang ada (`POST /api/marketing/returns/{id}/create-wh-return`):
      - harus DIKLIK MANUAL dan hanya boleh saat approved/completed,
      - mengirim `sku_code=""` dan memaksa `qty=1` ⇒ gudang tidak tahu barang
        apa yang kembali, jadi restock mustahil tepat.
  · Restock di `POST /api/wh/returns/{id}/resolve` menulis ke
    `rahaza_fg_inventory` — koleksi **MATI (0 dokumen)** — dan BUKAN lewat
    `core/stock_service`. Artinya: walau petugas menekan "Restock ke Gudang",
    **stok nyata tidak pernah bertambah** dan tidak ada satu baris ledger pun.

KEPUTUSAN PEMILIK (2026-08-19)
------------------------------
  1. Retur yang dibuat di Marketing **OTOMATIS** memunculkan pekerjaan di Gudang
     (tanpa klik manual) dan **OTOMATIS restock**.
  2. Ada **pilihan kondisi barang**:
       · **Baik**  → stok masuk zona jual `ZNA-FG`  → ikut terhitung stok jual.
       · **Rusak** → stok masuk `ZNA-KARANTINA`     → TIDAK terhitung stok jual
         (K-6a `core/catalog_stock.blocked_location_ids` sudah mengecualikan
         setiap lokasi ber-kode KARANTINA), jadi barang rusak TIDAK BISA terjual.

PRINSIP MODUL INI (sama seperti `core/sku_bridge`)
-------------------------------------------------
  * **SATU PINTU stok**: setiap penambahan stok memakai `core/stock_service.add`
    ⇒ alias skema (`qty`/`total_qty`/`quantity`) & `available_quantity` konsisten
    dan setiap mutasi punya baris `rahaza_stock_ledger`.
  * **IDEMPOTEN**: satu retur Marketing hanya boleh melahirkan SATU `wh_returns`
    (kunci `source_marketing_return_id`) dan hanya boleh menambah stok SEKALI
    (penjaga atomik `restocked`). Menekan tombol dua kali tidak menggandakan stok.
  * **TIDAK MENEBAK**: identitas barang diambil dari master (item katalog atau
    baris pesanan yang sudah tertaut SKU Bridge). Bila pesanan multi-baris dan
    tidak ada penunjuk pasti, retur tetap MUNCUL di gudang tetapi ditandai
    `needs_manual_resolution` dan stok TIDAK disentuh — lebih baik pekerjaan
    terlihat lalu diperbaiki manusia daripada stok bertambah pada barang salah.
  * **BERJEJAK**: timeline `wh_returns` mencatat langkah otomatis, dan retur
    Marketing menerima balikan (`wh_return_id/code/status`, `wh_stock_effect`).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from core import stock_service
from utils.counters import gen_prefixed_number

logger = logging.getLogger(__name__)

WH = "wh_returns"
MKT = "marketing_returns"

# ── kosakata kondisi barang ──────────────────────────────────────────────────
COND_GOOD = "Baik"
COND_DAMAGED = "Rusak"
CONDITIONS = (COND_GOOD, COND_DAMAGED, "Rusak Ringan", "Rusak Berat", "Tidak Layak Jual")
_GOOD_ALIASES = {"baik", "good", "bagus", "layak jual", "ok", "normal", "mulus"}

# Lokasi tujuan restock (kode master `rahaza_locations`).
LOC_SELLABLE = "ZNA-FG"          # Area Produk Jadi — ikut stok jual
LOC_QUARANTINE = "ZNA-KARANTINA"  # Area Karantina QC — DIKECUALIKAN dari stok jual

# Status tautan identitas barang retur.
LINK_OK = "linked"
LINK_AMBIGUOUS = "needs_manual_resolution"
LINK_NONE = "no_master_link"

ACTION_RESTOCK = "Restock ke Gudang"
ACTION_QUARANTINE = "Karantina (Rusak)"


class ReturnBridgeError(Exception):
    """Kegagalan yang harus terlihat (mis. lokasi master tidak ada)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


def _actor_name(actor) -> str:
    a = actor or {}
    return a.get("name") or a.get("full_name") or a.get("email") or "sistem"


def _int(v, default: int = 0) -> int:
    try:
        n = int(float(v))
        return n
    except (TypeError, ValueError):
        return default


# ═════════════════════════════════════════════════════════════════════════════
# KONDISI & LOKASI
# ═════════════════════════════════════════════════════════════════════════════
def normalize_condition(raw) -> str:
    """Samakan ejaan kondisi. Apa pun yang bukan 'Baik' dianggap RUSAK.

    Sengaja konservatif: kalau kondisi tidak terbaca, barang TIDAK dianggap layak
    jual — lebih aman menahan barang di karantina daripada menjual barang rusak.
    """
    s = str(raw or "").strip()
    if not s:
        return COND_GOOD
    if s.lower() in _GOOD_ALIASES:
        return COND_GOOD
    for c in CONDITIONS:
        if s.lower() == c.lower():
            return c
    return COND_DAMAGED


def is_sellable_condition(cond) -> bool:
    return normalize_condition(cond) == COND_GOOD


async def resolve_location(db, condition) -> dict:
    """Lokasi tujuan stok retur menurut kondisi barang."""
    sellable = is_sellable_condition(condition)
    code = LOC_SELLABLE if sellable else LOC_QUARANTINE
    loc = await db.rahaza_locations.find_one({"code": code}, {"_id": 0})
    if not loc:
        raise ReturnBridgeError(
            f"Lokasi master '{code}' tidak ada di Struktur Gudang. Buat lokasi itu "
            "dulu — stok retur tidak boleh disimpan tanpa lokasi.")
    return {
        "id": loc["id"],
        "code": loc.get("code") or code,
        "name": loc.get("name") or code,
        "sellable": sellable,
    }


# ═════════════════════════════════════════════════════════════════════════════
# IDENTITAS BARANG (tanpa menebak)
# ═════════════════════════════════════════════════════════════════════════════
async def _material_snapshot(db, material_id: str) -> dict:
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        return {}
    return {
        "material_id": mat["id"],
        "material_code": mat.get("code") or mat.get("sku") or "",
        "material_name": mat.get("name") or "",
        "unit": mat.get("unit") or "pcs",
        "material_type": mat.get("type") or "fg",
        "category_name": mat.get("category_name") or mat.get("category") or "",
        "color_name": mat.get("color_name") or mat.get("color") or "",
        "option_name": mat.get("option_name") or "",
        "variant_id": mat.get("variant_id"),
    }


async def _from_catalog_item(db, catalog_item_id: str) -> dict | None:
    it = await db.marketing_catalog_items.find_one({"id": catalog_item_id}, {"_id": 0})
    if not it:
        return None
    mid = it.get("fg_material_id") or it.get("material_id")
    if not mid:
        return None
    snap = await _material_snapshot(db, mid)
    if not snap:
        return None
    snap["catalog_item_id"] = it["id"]
    snap["source"] = "catalog_item"
    return snap


async def resolve_identity(db, ret: dict) -> dict:
    """Tentukan barang & jumlah yang kembali. Hasil:

        {link_status, material_id, material_code, material_name, unit, qty,
         variant_id, catalog_item_id, source, reason, candidates[]}

    Urutan sumber (dari paling pasti):
      1. `catalog_item_id` pada retur (dipilih pemakai dari katalog toko)
      2. `sku` pada retur → item katalog / master material ber-kode sama
      3. `order_id` → `marketing_orders.items[]` yang sudah tertaut SKU Bridge
         · 1 baris tertaut          → dipakai
         · >1 baris & nama produk retur cocok TEPAT SATU baris → dipakai
         · sisanya                  → `needs_manual_resolution` + kandidat
    """
    out = {
        "link_status": LINK_NONE,
        "material_id": None,
        "material_code": "",
        "material_name": "",
        "unit": "pcs",
        "qty": max(1, _int(ret.get("qty") or ret.get("qty_return"), 1)),
        "variant_id": None,
        "catalog_item_id": ret.get("catalog_item_id"),
        "source": "",
        "reason": "",
        "candidates": [],
    }

    # 1) item katalog yang dipilih pemakai
    if ret.get("catalog_item_id"):
        snap = await _from_catalog_item(db, ret["catalog_item_id"])
        if snap:
            out.update(snap)
            out["link_status"] = LINK_OK
            return out
        out["reason"] = ("Item katalog retur ini belum tertaut ke master barang jadi "
                         "(FG). Petakan dulu lewat Jembatan SKU.")

    # 2) SKU pada retur
    sku = (ret.get("sku") or "").strip()
    if sku:
        it = await db.marketing_catalog_items.find_one({"sku": sku}, {"_id": 0})
        if it:
            snap = await _from_catalog_item(db, it["id"])
            if snap:
                out.update(snap)
                out["link_status"] = LINK_OK
                out["source"] = "catalog_sku"
                return out
        mat = await db.rahaza_materials.find_one(
            {"$or": [{"code": sku}, {"sku": sku}], "type": "fg"}, {"_id": 0})
        if mat:
            out.update(await _material_snapshot(db, mat["id"]))
            out["link_status"] = LINK_OK
            out["source"] = "material_code"
            return out

    # 3) lewat pesanan (hasil SKU Bridge sesi #28)
    order_id = (ret.get("order_id") or "").strip()
    if order_id:
        order = await db.marketing_orders.find_one({"order_id": order_id}, {"_id": 0})
        if not order:
            out["reason"] = (f"Pesanan {order_id} tidak ada di data pesanan Marketing, "
                             "jadi barangnya tidak bisa dipastikan.")
            return out
        items = order.get("items") or []
        linked = [i for i in items if i.get("fg_material_id")]
        if not linked:
            out["reason"] = (f"Pesanan {order_id} belum tertaut master barang "
                             "(Jembatan SKU). Petakan SKU-nya dulu.")
            return out
        chosen = None
        if len(linked) == 1:
            chosen = linked[0]
            src = "order_item"
        else:
            want = (ret.get("product") or "").strip().lower()
            hits = [i for i in linked
                    if want and want in str(i.get("product_name_raw") or "").lower()]
            if len(hits) == 1:
                chosen = hits[0]
                src = "order_item_name_match"
            else:
                out["link_status"] = LINK_AMBIGUOUS
                out["reason"] = (
                    f"Pesanan {order_id} punya {len(linked)} baris barang. Retur harus "
                    "menunjuk SATU produk — pilih produknya dari katalog pada retur ini "
                    "supaya stok tidak bertambah pada barang yang salah.")
                out["candidates"] = [{
                    "catalog_item_id": i.get("catalog_item_id"),
                    "fg_material_id": i.get("fg_material_id"),
                    "product_name": i.get("product_name_raw") or "",
                    "variation": i.get("variation_raw") or "",
                    "quantity": _int(i.get("quantity"), 1),
                } for i in linked]
                return out
        snap = await _material_snapshot(db, chosen["fg_material_id"])
        if not snap:
            out["reason"] = ("Baris pesanan menunjuk master barang yang sudah tidak ada "
                             f"({chosen.get('fg_material_id')}).")
            return out
        out.update(snap)
        out["catalog_item_id"] = chosen.get("catalog_item_id") or out.get("catalog_item_id")
        out["variant_id"] = chosen.get("variant_id") or snap.get("variant_id")
        if not (ret.get("qty") or ret.get("qty_return")):
            out["qty"] = max(1, _int(chosen.get("quantity"), 1))
        out["link_status"] = LINK_OK
        out["source"] = src
        return out

    if not out["reason"]:
        out["reason"] = ("Retur ini tidak menyebut produk maupun nomor pesanan, jadi "
                         "barang yang kembali tidak bisa dipastikan.")
    return out


# ═════════════════════════════════════════════════════════════════════════════
# MEMBUAT PEKERJAAN DI GUDANG (idempoten)
# ═════════════════════════════════════════════════════════════════════════════
async def _next_code(db) -> str:
    """Nomor retur gudang. Selalu OTOMATIS (dokumen ini lahir dari sistem, bukan
    diketik pemakai), tetapi FORMATNYA sama dengan yang dipakai layar manual —
    dibaca dari kebijakan penomoran pemilik (`doc_number_configs`) supaya arsip
    retur tidak berisi dua pola nomor yang berbeda."""
    key = "wh_returns.return_code"
    try:
        from core import doc_number_policy as _dnp
        from utils.counters import render_format
        pol = await _dnp.policy(db, key)
        prefix, width = render_format(pol["format"], ctx={})
    except Exception as e:  # noqa: BLE001 — jangan sampai retur gagal karena format
        logger.warning("[retur-jembatan] format nomor retur tidak terbaca (%s) — "
                       "pakai pola cadangan RET-YYYYMMDD-###", e)
        prefix, width = f"RET-{_now():%Y%m%d}-", 3
    return await gen_prefixed_number(db, WH, "return_code", prefix, width,
                                     config_key=key)


async def ensure_wh_return(db, ret: dict, *, actor=None, condition=None,
                           auto_restock: bool = True) -> dict:
    """Pastikan retur Marketing punya SATU pekerjaan Retur Fisik di Gudang.

    Return: {created, restocked, wh_return, identity, message}
    """
    actor = actor or {}
    cond = normalize_condition(condition if condition is not None
                               else ret.get("item_condition") or ret.get("goods_condition"))

    # ── idempoten: sudah pernah dijembatani? ──────────────────────────────────
    existing = None
    if ret.get("wh_return_id"):
        existing = await db[WH].find_one({"id": ret["wh_return_id"]}, {"_id": 0})
    if not existing:
        existing = await db[WH].find_one({"source_marketing_return_id": ret["id"]}, {"_id": 0})
    if existing:
        res = {"created": False, "restocked": False, "wh_return": existing,
               "identity": None, "message": f"Sudah terhubung ke {existing.get('return_code')}"}
        if auto_restock and not existing.get("restocked") \
                and existing.get("link_status") == LINK_OK:
            done = await auto_process(db, existing["id"], condition=cond, actor=actor)
            res["restocked"] = bool(done.get("restocked"))
            res["wh_return"] = done.get("wh_return") or existing
            res["message"] = done.get("message") or res["message"]
        await _stamp_marketing(db, ret["id"], res["wh_return"])
        return res

    ident = await resolve_identity(db, ret)
    code = await _next_code(db)
    actor_name = _actor_name(actor)
    reason_txt = " — ".join([x for x in [ret.get("reason_label"), ret.get("reason_detail")] if x])

    doc = {
        "id": _uid(),
        "return_code": code,
        "return_type": "customer_refund",
        # ── info pesanan (dipetakan dari retur Marketing) ─────────────────────
        "order_number": ret.get("order_id", ""),
        "resi_number": "",
        "channel": ret.get("platform", ""),
        "customer_name": ret.get("customer_name") or ret.get("account_name") or "Pembeli Marketplace",
        "customer_contact": "",
        "sku_code": ident.get("material_code") or (ret.get("sku") or ""),
        "product_name": ident.get("material_name") or ret.get("product") or "",
        "qty": max(1, _int(ident.get("qty"), 1)),
        "order_value": float(ret.get("price") or 0),
        "initial_reason": reason_txt,
        "notes": (f"Otomatis dari retur Toko/Marketing #{ret['id']}. "
                  f"Refund: Rp {float(ret.get('refund_amount') or 0):,.0f}. "
                  f"{ret.get('notes') or ''}").strip(),
        # ── tautan master barang (kunci agar restock tidak buta) ──────────────
        "material_id": ident.get("material_id"),
        "fg_material_id": ident.get("material_id"),
        "variant_id": ident.get("variant_id"),
        "catalog_item_id": ident.get("catalog_item_id"),
        "material_unit": ident.get("unit") or "pcs",
        "material_category": ident.get("category_name") or "",
        "material_color": ident.get("color_name") or "",
        "material_option": ident.get("option_name") or "",
        "link_status": ident.get("link_status"),
        "link_reason": ident.get("reason") or "",
        "link_source": ident.get("source") or "",
        "link_candidates": ident.get("candidates") or [],
        # ── asal (jembatan satu arah) ─────────────────────────────────────────
        "source": "marketing_return",
        "source_marketing_return_id": ret["id"],
        "source_marketing_order_id": ret.get("order_id"),
        "source_account_name": ret.get("account_name") or "",
        # ── alur kerja ────────────────────────────────────────────────────────
        "status": "Pending",
        "timeline": [{
            "status": "Pending", "at": _now_iso(), "by": actor_name,
            "note": (f"Dibuat otomatis dari retur Marketing (pesanan "
                     f"{ret.get('order_id') or '-'})"),
        }],
        "received_at": "", "received_by": "",
        "unboxing_condition_notes": "", "unboxing_photo_notes": "", "package_condition": "",
        "inspected_at": "", "inspected_by": "",
        "item_condition": "", "return_cause": "", "cause_detail": "", "recommended_action": "",
        "resolved_at": "", "resolved_by": "",
        "action_taken": "", "action_notes": "",
        "reshipment_resi": "", "appeal_status": "", "restock_qty": 0,
        "restocked": False,
        "restock_location_id": None, "restock_location_code": "",
        "restock_condition": "", "stock_effect": "",
        # ── meta ──────────────────────────────────────────────────────────────
        "created_by": actor_name, "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db[WH].insert_one(doc)
    doc.pop("_id", None)

    out = {"created": True, "restocked": False, "wh_return": doc, "identity": ident,
           "message": f"Retur fisik {code} dibuat di Gudang"}

    if auto_restock and ident.get("link_status") == LINK_OK:
        done = await auto_process(db, doc["id"], condition=cond, actor=actor)
        out["restocked"] = bool(done.get("restocked"))
        out["wh_return"] = done.get("wh_return") or doc
        out["message"] = done.get("message") or out["message"]
    elif auto_restock:
        out["message"] = (f"Retur fisik {code} dibuat, TAPI stok belum ditambah: "
                          f"{ident.get('reason') or 'barang belum tertaut master'}")

    await _stamp_marketing(db, ret["id"], out["wh_return"])
    return out


async def _stamp_marketing(db, marketing_return_id: str, wh: dict) -> None:
    """Tulis balikan ke retur Marketing supaya layar Toko tahu keadaan fisiknya."""
    wh = wh or {}
    try:
        await db[MKT].update_one({"id": marketing_return_id}, {"$set": {
            "wh_return_id": wh.get("id"),
            "wh_return_code": wh.get("return_code", ""),
            "wh_return_status": wh.get("status", "Pending"),
            "wh_link_status": wh.get("link_status", ""),
            "wh_link_reason": wh.get("link_reason", ""),
            "wh_restock_qty": wh.get("restock_qty", 0),
            "wh_restocked": bool(wh.get("restocked")),
            "wh_stock_effect": wh.get("stock_effect", ""),
            "wh_restock_location_code": wh.get("restock_location_code", ""),
            "wh_item_condition": wh.get("item_condition", ""),
            "wh_sync_ok": True,
            "wh_sync_error": "",
            "wh_sync_at": _now(),
            "updated_at": _now(),
        }})
    except Exception as e:  # noqa: BLE001
        # Jangan gagalkan pekerjaan fisik gudang karena balikan ke Marketing gagal,
        # TAPI jangan diam: kalau ini gagal, layar Toko akan menyangka retur belum
        # ditangani padahal stok sudah bertambah.
        logger.error("[retur-jembatan] gagal menandai retur Marketing %s: %s",
                     marketing_return_id, e)


# ═════════════════════════════════════════════════════════════════════════════
# RESTOCK (satu pintu `core/stock_service`)
# ═════════════════════════════════════════════════════════════════════════════
async def restock(db, wh_ret: dict, *, condition=None, qty=None, actor=None,
                  note: str = "") -> dict:
    """Tambah stok barang retur. IDEMPOTEN & guarded.

    · Penjaga atomik `restocked` dipasang SEBELUM stok ditambah supaya klik ganda
      / dua proses paralel tidak pernah menambah stok dua kali.
    · Barang Baik → `ZNA-FG` (ikut stok jual). Barang Rusak → `ZNA-KARANTINA`
      (dikecualikan dari stok jual oleh K-6a) ⇒ barang rusak tidak bisa terjual.
    """
    actor = actor or {}
    mid = wh_ret.get("material_id") or wh_ret.get("fg_material_id")
    if not mid:
        raise ReturnBridgeError(
            "Retur ini belum tertaut master barang jadi, jadi stok tidak bisa "
            "ditambah. Pilih produknya dari katalog di retur Marketing, atau "
            "petakan SKU-nya lewat Jembatan SKU.")
    cond = normalize_condition(condition if condition is not None
                               else wh_ret.get("item_condition"))
    n = max(1, _int(qty if qty is not None else wh_ret.get("qty"), 1))
    loc = await resolve_location(db, cond)

    # ── penjaga idempotensi (atomik) ──────────────────────────────────────────
    claim = await db[WH].update_one(
        {"id": wh_ret["id"], "restocked": {"$ne": True}},
        {"$set": {"restocked": True, "restock_claimed_at": _now_iso()}})
    if claim.matched_count == 0:
        cur = await db[WH].find_one({"id": wh_ret["id"]}, {"_id": 0})
        return {"restocked": False, "already": True, "wh_return": cur,
                "message": "Stok retur ini sudah pernah ditambahkan (tidak digandakan)."}

    snap = await _material_snapshot(db, mid)
    try:
        row = await stock_service.add(
            mid, loc["id"], n,
            meta={
                "material_code": snap.get("material_code", ""),
                "material_name": snap.get("material_name", ""),
                "material_type": snap.get("material_type", "fg"),
                "unit": snap.get("unit", "pcs"),
                "category_name": snap.get("category_name", ""),
                "location_code": loc["code"],
                "inventory_category": "finished_goods",
                "ownership": "own",
            },
            ref={
                "type": "wh_return_restock",
                "ref_id": wh_ret["id"],
                "ref_no": wh_ret.get("return_code", ""),
                "marketing_return_id": wh_ret.get("source_marketing_return_id"),
                "order_number": wh_ret.get("order_number", ""),
                "condition": cond,
            },
            actor={"id": actor.get("id"), "name": _actor_name(actor)},
            db=db,
        )
    except Exception as e:
        # Batalkan klaim supaya retur bisa dicoba lagi setelah masalahnya beres —
        # kalau flag dibiarkan menyala, barang fisik ada tapi stoknya tak pernah
        # bisa dimasukkan lagi oleh siapa pun.
        await db[WH].update_one({"id": wh_ret["id"]},
                                {"$set": {"restocked": False},
                                 "$unset": {"restock_claimed_at": ""}})
        logger.error("[retur-jembatan] restock GAGAL untuk %s: %s",
                     wh_ret.get("return_code"), e)
        raise

    effect = "sellable" if loc["sellable"] else "quarantine"
    patch = {
        "restock_qty": n,
        "restock_at": _now_iso(),
        "restock_by": _actor_name(actor),
        "restock_location_id": loc["id"],
        "restock_location_code": loc["code"],
        "restock_location_name": loc["name"],
        "restock_condition": cond,
        "stock_effect": effect,
        "material_id": mid,
        "fg_material_id": mid,
        "sku_code": wh_ret.get("sku_code") or snap.get("material_code", ""),
        "product_name": wh_ret.get("product_name") or snap.get("material_name", ""),
        "updated_at": _now_iso(),
    }
    await db[WH].update_one({"id": wh_ret["id"]}, {"$set": patch, "$push": {"timeline": {
        "status": wh_ret.get("status", "Resolved"), "at": _now_iso(),
        "by": _actor_name(actor),
        "note": (f"Stok +{n} {snap.get('unit', 'pcs')} {snap.get('material_code', '')} "
                 f"→ {loc['name']} ({loc['code']}) · kondisi {cond} · "
                 f"{'ikut stok jual' if loc['sellable'] else 'TIDAK dijual (karantina)'}"
                 + (f" · {note}" if note else "")),
    }}})

    await refresh_catalog_cache(db, mid)
    fresh = await db[WH].find_one({"id": wh_ret["id"]}, {"_id": 0})
    return {
        "restocked": True,
        "already": False,
        "qty": n,
        "condition": cond,
        "location": loc,
        "stock_effect": effect,
        "onhand_after": float((row or {}).get("qty") or 0),
        "wh_return": fresh,
        "message": (f"Stok +{n} → {loc['name']} ({loc['code']}) · kondisi {cond}"
                    + ("" if loc["sellable"] else " · tidak dijual (karantina)")),
    }


async def refresh_catalog_cache(db, material_id: str) -> int:
    """Segarkan cache stok jual item katalog yang memakai material ini (K-7a).

    Stok jual dihitung LIVE saat katalog dibaca, tetapi cache-nya dipakai untuk
    daftar & lencana "stok rendah". Kalau tidak disegarkan, layar Toko masih
    menunjukkan angka lama sesaat setelah retur masuk.
    """
    try:
        from core import catalog_stock as _cs
        items = await db.marketing_catalog_items.find(
            {"$or": [{"fg_material_id": material_id}, {"material_id": material_id}]},
            {"_id": 0}).to_list(200)
        blocked = await _cs.blocked_location_ids(db)
        n = 0
        for it in items:
            await _cs.sync_item_cache(db, it, blocked_locs=blocked)
            n += 1
        return n
    except Exception as e:  # noqa: BLE001
        logger.error("[retur-jembatan] gagal menyegarkan cache stok katalog %s: %s",
                     material_id, e)
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# PROSES OTOMATIS: terima → inspeksi → selesai + restock
# ═════════════════════════════════════════════════════════════════════════════
async def auto_process(db, wh_return_id: str, *, condition=None, qty=None,
                       actor=None, note: str = "") -> dict:
    """Jalankan seluruh alur fisik sekaligus (keputusan pemilik: otomatis).

    Timeline tetap ditulis langkah-per-langkah (Received → Inspected → Resolved)
    supaya jejak auditnya sama lengkap dengan proses manual, dan petugas gudang
    tetap bisa membaca apa yang terjadi.
    """
    actor = actor or {}
    who = _actor_name(actor)
    doc = await db[WH].find_one({"id": wh_return_id}, {"_id": 0})
    if not doc:
        raise ReturnBridgeError(f"Retur fisik {wh_return_id} tidak ditemukan")
    if doc.get("restocked"):
        return {"restocked": False, "already": True, "wh_return": doc,
                "message": "Stok retur ini sudah pernah ditambahkan (tidak digandakan)."}

    cond = normalize_condition(condition if condition is not None
                               else doc.get("item_condition"))
    n = max(1, _int(qty if qty is not None else doc.get("qty"), 1))
    sellable = is_sellable_condition(cond)
    action = ACTION_RESTOCK if sellable else ACTION_QUARANTINE

    steps = [
        {"status": "Received", "at": _now_iso(), "by": who,
         "note": "Barang retur diterima gudang (otomatis dari Marketing)"},
        {"status": "Inspected", "at": _now_iso(), "by": who,
         "note": f"Kondisi: {cond} · Rekomendasi: {action}"},
        {"status": "Resolved", "at": _now_iso(), "by": who,
         "note": f"Aksi: {action}" + (f" · {note}" if note else "")},
    ]
    await db[WH].update_one({"id": wh_return_id}, {
        "$set": {
            "status": "Resolved",
            "received_at": _now_iso(), "received_by": who,
            "unboxing_condition_notes": "Diterima otomatis dari retur Marketing",
            "package_condition": "",
            "inspected_at": _now_iso(), "inspected_by": who,
            "item_condition": cond,
            "return_cause": doc.get("return_cause") or "Kesalahan Customer",
            "cause_detail": doc.get("initial_reason") or "",
            "recommended_action": action,
            "resolved_at": _now_iso(), "resolved_by": who,
            "action_taken": action,
            "action_notes": note or "Diproses otomatis oleh jembatan retur Marketing → Gudang",
            "auto_processed": True,
            "updated_at": _now_iso(),
        },
        "$push": {"timeline": {"$each": steps}},
    })

    fresh = await db[WH].find_one({"id": wh_return_id}, {"_id": 0})
    res = await restock(db, fresh, condition=cond, qty=n, actor=actor, note=note)
    if res.get("wh_return") and doc.get("source_marketing_return_id"):
        await _stamp_marketing(db, doc["source_marketing_return_id"], res["wh_return"])
    return res


# ═════════════════════════════════════════════════════════════════════════════
# BACKFILL: tarik retur Marketing yang belum pernah dijembatani
# ═════════════════════════════════════════════════════════════════════════════
SKIP_STATUSES = {"rejected", "cancelled"}


async def sync_all(db, *, actor=None, dry_run: bool = False,
                   auto_restock: bool = True, condition=None,
                   limit: int = 500) -> dict:
    """Jembatani SEMUA retur Marketing yang belum punya pekerjaan gudang.

    Retur berstatus `rejected`/`cancelled` DILEWATI: barangnya memang tidak
    kembali, jadi menambah stok untuknya akan berbohong.
    """
    q = {"status": {"$nin": list(SKIP_STATUSES)}}
    rets = await db[MKT].find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    out = {"scanned": len(rets), "created": 0, "already": 0, "restocked": 0,
           "skipped": 0, "failed": 0, "dry_run": bool(dry_run), "details": []}
    for r in rets:
        wh_exists = await db[WH].find_one({"source_marketing_return_id": r["id"]},
                                          {"_id": 0, "id": 1, "return_code": 1,
                                           "restocked": 1})
        if wh_exists and not dry_run:
            out["already"] += 1
            continue
        if dry_run:
            ident = await resolve_identity(db, r)
            out["details"].append({
                "marketing_return_id": r["id"], "order_id": r.get("order_id"),
                "product": r.get("product"), "link_status": ident["link_status"],
                "material_code": ident.get("material_code"), "qty": ident.get("qty"),
                "reason": ident.get("reason"),
                "already": bool(wh_exists),
            })
            if wh_exists:
                out["already"] += 1
            elif ident["link_status"] == LINK_OK:
                out["created"] += 1
            else:
                out["skipped"] += 1
            continue
        try:
            res = await ensure_wh_return(db, r, actor=actor, condition=condition,
                                        auto_restock=auto_restock)
            if res.get("created"):
                out["created"] += 1
            else:
                out["already"] += 1
            if res.get("restocked"):
                out["restocked"] += 1
            wh = res.get("wh_return") or {}
            if wh.get("link_status") != LINK_OK:
                out["skipped"] += 1
            out["details"].append({
                "marketing_return_id": r["id"], "order_id": r.get("order_id"),
                "wh_return_code": wh.get("return_code"),
                "link_status": wh.get("link_status"),
                "restocked": bool(wh.get("restocked")),
                "stock_effect": wh.get("stock_effect", ""),
                "message": res.get("message", ""),
            })
        except Exception as e:  # noqa: BLE001
            out["failed"] += 1
            out["details"].append({"marketing_return_id": r["id"], "error": str(e)[:300]})
            logger.error("[retur-jembatan] gagal menjembatani retur %s: %s", r["id"], e)
    return out
