"""core.marketing_daily_rollup — REKAP HARIAN **TURUNAN** dari pesanan toko (F2).

KENAPA BERKAS INI ADA
---------------------
Sebelum F2 ada **dua dunia omzet** yang tidak pernah bertemu:

1. `marketing_orders` — pesanan hasil impor Seller Center (angka nyata, per pesanan).
2. `marketing_sales_data` — rekap harian yang **DIKETIK** staf.

Target, Dashboard, Anggaran, dan Laporan semuanya membaca dunia (2), sedangkan
pesanan yang benar-benar terjadi ada di dunia (1). Akibatnya, satu toko bisa
menunjukkan tiga angka omzet berbeda di tiga layar untuk hari yang sama — dan
tidak ada satu pun galat yang muncul.

Berkas ini membuat dunia (2) **diturunkan** dari dunia (1): angka omzet & jumlah
pesanan tidak lagi diketik, tapi dihitung dari pesanan. Entri manual untuk grup
`metrics` ditolak (409) kecuali SPV memakai jalur **override** yang tercatat.

ATURAN YANG TIDAK BOLEH DILANGGAR
---------------------------------
* **Idempoten.** Menjalankan ulang untuk tanggal yang sama tidak boleh mengubah
  hasil atau menambah dokumen (kunci alami `(account_id, date, revenue_type)`).
* **Hanya menyentuh yang memang turunan.** `$set` dilakukan per-field pada grup
  `metrics`, `traffic`, dan sebagian `fulfillment`. Grup `funnel`, `buyers_mix`,
  `customer_satisfaction`, `live_metrics`, `content_metrics` adalah milik sumber
  lain (F7/F8, entri manual) dan **tidak pernah ditimpa**.
* **Tidak meninggalkan angka nyangkut.** Bila tidak ada lagi pesanan pada hari itu
  dan dokumennya memang turunan, dokumen itu **dihapus** (bukan dibiarkan 0),
  supaya rollback impor benar-benar mengembalikan keadaan.
* **Override SPV dihormati.** Dokumen `source='manual_override'` tidak ditimpa
  kecuali dipanggil dengan `force=True` (tombol "Hitung Ulang (paksa)").
* **Zona waktu.** `order_date` disimpan sebagai jam dinding platform (WIB).
  Pengelompokan hari memakai bagian tanggalnya apa adanya — inilah yang membuat
  angka rekap sama dengan yang dilihat staf di Seller Center.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from core import marketing_sales_shape as _shape

logger = logging.getLogger(__name__)

ORDERS = "marketing_orders"
DAILY = "marketing_sales_data"
ACCOUNTS = "marketing_platform_accounts"

REVENUE_TYPE = "total"
# Status yang TIDAK dihitung sebagai omzet (uangnya tidak pernah ada).
EXCLUDED_FOR_REVENUE = ("cancelled",)
# Status yang dianggap sudah berjalan sampai kirim (dasar fulfillment_rate).
FULFILLED_STATUSES = ("shipped", "delivered", "completed")
# Kanal trafik yang dikenali rekap harian (SSOT §3 grup `traffic`).
TRAFFIC_KEYS = ("live", "video", "ads", "affiliate", "campaign", "organic",
                "product_card", "search", "other")
# Field `fulfillment` yang MEMANG turunan dari pesanan (sisanya milik F8).
DERIVED_FULFILLMENT_KEYS = ("cancelled_orders", "cancelled_value", "returned_orders",
                            "returned_value", "returned_revenue_product",
                            "returned_units", "cancellation_rate", "return_rate",
                            "fulfillment_rate")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def order_date_key(value: Any) -> Optional[str]:
    """Tanggal (YYYY-MM-DD) satu pesanan — dasar pengelompokan rekap harian."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return None


def _day_bounds(date: str) -> Tuple[datetime, datetime]:
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d, d + timedelta(days=1)


# ══════════════════════════════════════════════════════════════════════════════
# PEMBACA DEFENSIF UANG PESANAN — SATU definisi untuk SEMUA pembaca
# ══════════════════════════════════════════════════════════════════════════════
# KENAPA ADA (temuan 2026-08-13, saat menguji marjin F5):
# `marketing_orders` menampung DUA bentuk dokumen yang lahir dari dua pintu:
#   · impor Seller Center (F1) → `revenue_product`, `order_amount`,
#     `items[].quantity`, `items[].sku_subtotal_after_discount`;
#   · pembuatan MANUAL lewat layar Order Terpadu → `total_payment`, `revenue`,
#     `items[].qty`, `items[].price` — TANPA satu pun nama kanonik di atas.
# Akibat terukur: setiap pesanan yang diinput staf lewat layar menyumbang
# **Rp 0** ke rekap harian, ke siklus F5, dan ke marjin — tanpa satu pun galat.
# Pintu manualnya sudah diperbaiki agar menulis nama kanonik, tetapi dokumen LAMA
# tetap ada di DB, jadi pembacanya harus tetap defensif (pola F0.3).
def order_revenue_product(o: dict) -> float:
    """Omzet PRODUK satu pesanan (tanpa ongkir), apa pun bentuk dokumennya."""
    for k in ("revenue_product",):
        if o.get(k) is not None:
            return _num(o.get(k))
    items = o.get("items") or []
    if items:
        return round(sum(item_revenue(it) for it in items), 2)
    # dokumen manual paling lama: hanya harga × jumlah
    return round(_num(o.get("price_final")) * _int(o.get("quantity")), 2)


def order_amount_of(o: dict) -> float:
    """Yang DIBAYAR pembeli (termasuk ongkir)."""
    for k in ("order_amount", "total_payment"):
        if o.get(k) is not None:
            return _num(o.get(k))
    return round(order_revenue_product(o) + _num(o.get("shipping_cost")), 2)


def order_revenue_gross(o: dict) -> float:
    """Omzet sebelum diskon penjual (harga coret)."""
    for k in ("revenue_gross",):
        if o.get(k) is not None:
            return _num(o.get(k))
    items = o.get("items") or []
    if items:
        tot = 0.0
        for it in items:
            before = it.get("sku_subtotal_before_discount")
            tot += (_num(before) if before is not None
                    else _num(it.get("price_original") or it.get("price")) * item_qty(it))
        return round(tot, 2)
    return round(_num(o.get("price_original") or o.get("price_final"))
                 * _int(o.get("quantity")), 2)


def order_seller_discount(o: dict) -> float:
    """Diskon yang ditanggung PENJUAL (biaya nyata, dasar realisasi anggaran)."""
    for k in ("seller_discount_total", "discount_seller"):
        if o.get(k) is not None:
            return _num(o.get(k))
    items = o.get("items") or []
    return round(sum(_num(it.get("sku_seller_discount")) for it in items), 2)


def item_qty(it: dict) -> int:
    """Jumlah unit satu baris item (impor: `quantity`, manual: `qty`)."""
    for k in ("quantity", "qty", "qty_ordered"):
        if it.get(k) is not None:
            return _int(it.get(k))
    return 0


def item_revenue(it: dict) -> float:
    """Omzet satu baris item SESUDAH diskon (impor & manual)."""
    for k in ("sku_subtotal_after_discount", "subtotal", "amount"):
        if it.get(k) is not None:
            return _num(it.get(k))
    return round(_num(it.get("price")) * item_qty(it), 2)



# ══════════════════════════════════════════════════════════════════════════════
# HITUNG SATU HARI
# ══════════════════════════════════════════════════════════════════════════════
def summarize_orders(orders: List[dict]) -> dict:
    """Ringkas daftar pesanan satu hari → angka datar untuk `build_daily_doc`."""
    live_ok = [o for o in orders if (o.get("status") or "") not in EXCLUDED_FOR_REVENUE]
    cancelled = [o for o in orders if (o.get("status") or "") == "cancelled"]
    returned = [o for o in orders if (o.get("status") or "") == "returned"]
    fulfilled = [o for o in orders if (o.get("status") or "") in FULFILLED_STATUSES]

    rev_product = sum(order_revenue_product(o) for o in live_ok)
    rev_order = sum(order_amount_of(o) for o in live_ok)
    gross = sum(order_revenue_gross(o) for o in live_ok)
    disc_seller = sum(order_seller_discount(o) for o in live_ok)
    disc_platform = sum(_num(o.get("platform_discount_total")) for o in live_ok)
    units = sum(_int(o.get("quantity")) or sum(item_qty(it) for it in (o.get("items") or []))
                for o in live_ok)
    buyers: Set[str] = {
        str(o.get("buyer_username") or o.get("customer_phone") or o.get("customer_name") or "").strip().lower()
        for o in live_ok}
    buyers.discard("")

    traffic = {k: 0.0 for k in TRAFFIC_KEYS}
    for o in live_ok:
        ch = (o.get("order_channel") or "other").strip().lower()
        if ch not in traffic:
            ch = "other"
        traffic[ch] += order_revenue_product(o)
    traffic = {k: round(v, 2) for k, v in traffic.items()}

    total_orders = len(orders)
    # SESI #9 — nilai retur pada KEDUA basis uang, dihitung oleh SATU kalkulator
    # (`core.marketing_returns`). Impor lokal: `marketing_returns` memakai pembaca
    # uang dari berkas ini, jadi impor tingkat-modul akan melingkar.
    from core import marketing_returns as _ret
    rsplit = _ret.split_from_orders(orders)
    fulfillment = {
        "cancelled_orders": len(cancelled),
        "cancelled_value": round(sum(order_amount_of(o) for o in cancelled), 2),
        "returned_orders": len(returned),
        "returned_value": round(sum(order_amount_of(o) for o in returned), 2),
        # BARU: dasar "omzet setelah retur" untuk toko berbasis omzet produk.
        "returned_revenue_product": rsplit["returned_revenue_product"],
        "returned_units": rsplit["returned_units"],
        "cancellation_rate": round(len(cancelled) / total_orders * 100, 2) if total_orders else 0.0,
        "return_rate": round(len(returned) / total_orders * 100, 2) if total_orders else 0.0,
        "fulfillment_rate": round(len(fulfilled) / total_orders * 100, 2) if total_orders else 0.0,
    }

    return {
        "revenue_product": round(rev_product, 2),
        "revenue_order_amount": round(rev_order, 2),
        "gross_before_discount": round(gross, 2),
        "seller_discount": round(disc_seller, 2),
        "platform_discount": round(disc_platform, 2),
        "orders": len(live_ok),
        "units": units,
        "buyers": len(buyers),
        "traffic": traffic,
        "fulfillment": fulfillment,
    }


async def recompute_daily(db, account_id: str, date: str, *,
                          force: bool = False, actor: str = "system") -> dict:
    """Hitung ulang rekap harian SATU tanggal dari `marketing_orders`. Idempoten.

    → ``{account_id, date, action, orders, revenue_product, skipped_reason?}``
    ``action`` ∈ ``upserted`` · ``deleted`` · ``skipped_override`` · ``noop``
    """
    date = _shape.norm_date(date)
    account = await db[ACCOUNTS].find_one({"id": account_id}, {"_id": 0})
    if not account:
        # Toko sudah tidak ada ⇒ rekap TURUNAN miliknya tidak punya dasar apa pun.
        # Dulu dokumennya dibiarkan, dan yang tertinggal adalah rekap ber-akun
        # YATIM: ia ikut dijumlah di laporan gabungan, tidak bisa dibuka dari layar
        # mana pun (tokonya tidak ada di pemilih), dan membuat gate lingkup toko
        # merah tanpa penyebab yang bisa ditelusuri. Hanya dokumen turunan yang
        # dihapus — entri manual/override tetap disimpan sebagai bukti sejarah.
        existing = await db[DAILY].find_one(
            {"account_id": account_id, "date": date, "revenue_type": REVENUE_TYPE},
            {"_id": 0, "source": 1})
        if existing and (existing.get("source") in _shape.DERIVED_SOURCES):
            await db[DAILY].delete_one({"account_id": account_id, "date": date,
                                        "revenue_type": REVENUE_TYPE})
            logger.info("[rollup] rekap turunan %s %s dihapus: tokonya sudah tidak ada",
                        account_id, date)
            return {"account_id": account_id, "date": date, "action": "deleted_orphan",
                    "orders": 0, "skipped_reason": "toko tidak ada"}
        return {"account_id": account_id, "date": date, "action": "noop",
                "skipped_reason": "toko tidak ada"}

    start, end = _day_bounds(date)
    orders = await db[ORDERS].find({
        "account_id": account_id,
        "$or": [
            {"order_date": {"$gte": start, "$lt": end}},
            {"order_date": {"$gte": date, "$lt": date + "\uffff"}},   # dokumen lama: string
        ],
    }, {"_id": 0}).to_list(20000)
    # jaring pengaman: buang pesanan yang tanggalnya bukan hari ini
    orders = [o for o in orders if order_date_key(o.get("order_date")) == date]

    existing = await db[DAILY].find_one(
        {"account_id": account_id, "date": date, "revenue_type": REVENUE_TYPE}, {"_id": 0})
    src = (existing or {}).get("source")

    if existing and src == _shape.SOURCE_MANUAL_OVERRIDE and not force:
        return {"account_id": account_id, "date": date, "action": "skipped_override",
                "orders": len(orders),
                "skipped_reason": "angka hari ini di-override SPV; pakai Hitung Ulang (paksa)"}

    if not orders:
        # Tidak ada pesanan: dokumen turunan HARUS hilang supaya angka tidak nyangkut
        # sesudah rollback impor / pembatalan pesanan.
        if existing and (src in (_shape.SOURCE_ORDERS_AUTO,)
                         or (force and src == _shape.SOURCE_MANUAL_OVERRIDE)):
            await db[DAILY].delete_one({"account_id": account_id, "date": date,
                                        "revenue_type": REVENUE_TYPE})
            return {"account_id": account_id, "date": date, "action": "deleted", "orders": 0}
        return {"account_id": account_id, "date": date, "action": "noop", "orders": 0}

    flat = summarize_orders(orders)
    doc = _shape.build_daily_doc(
        account=account, date=date, revenue_type=REVENUE_TYPE, flat=flat,
        source=_shape.SOURCE_ORDERS_AUTO,
    )

    now = _now()
    # Pembacaan grup WAJIB lewat pembaca kanonik (gate G6): mengindeks
    # `doc["metrics"]` langsung adalah pola yang dulu melahirkan HTTP 500.
    metrics = _shape.read_metrics(doc)
    traffic = _shape.read_group(doc, "traffic")
    fulfillment = _shape.read_group(doc, "fulfillment")
    satisfaction = _shape.read_group(doc, "customer_satisfaction")
    set_fields: Dict[str, Any] = {
        "metrics": metrics,
        "revenue_basis": doc.get("revenue_basis"),
        "source": _shape.SOURCE_ORDERS_AUTO,
        "locked_source": True,
        "unit_pct_scale": "0-100",
        "shape_version": doc.get("shape_version", 2),
        "account_code": account.get("account_code", ""),
        "account_name": account.get("account_name", ""),
        "platform": account.get("platform", ""),
        "rollup_orders_count": len(orders),
        "rollup_at": now,
        "rollup_by": actor,
        "updated_at": now,
    }
    # traffic & sebagian fulfillment: per-field, supaya angka dari sumber lain
    # (KPI mingguan F8, entri manual) tidak ikut terhapus.
    for k, v in traffic.items():
        set_fields[f"traffic.{k}"] = v
    for k in DERIVED_FULFILLMENT_KEYS:
        if k in fulfillment:
            set_fields[f"fulfillment.{k}"] = fulfillment[k]
    # jejak override sebelumnya dihapus saat kembali menjadi turunan
    unset_fields = {"override_reason": "", "override_by": "", "override_at": ""}

    await db[DAILY].update_one(
        {"account_id": account_id, "date": date, "revenue_type": REVENUE_TYPE},
        {
            "$set": set_fields,
            "$unset": unset_fields,
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "date": date,
                "revenue_type": REVENUE_TYPE,
                "funnel": {},
                "buyers_mix": {},
                "customer_satisfaction": satisfaction,
                "live_metrics": {},
                "content_metrics": {},
                "created_at": now,
                "created_by": actor,
            },
        },
        upsert=True,
    )
    return {"account_id": account_id, "date": date, "action": "upserted",
            "orders": len(orders), "revenue_product": flat["revenue_product"]}


async def recompute_range(db, account_id: str, date_from: str, date_to: str, *,
                          force: bool = False, actor: str = "system") -> dict:
    """Hitung ulang rentang tanggal (inklusif)."""
    d0 = datetime.strptime(_shape.norm_date(date_from), "%Y-%m-%d")
    d1 = datetime.strptime(_shape.norm_date(date_to), "%Y-%m-%d")
    if d1 < d0:
        d0, d1 = d1, d0
    results: List[dict] = []
    cur = d0
    while cur <= d1:
        results.append(await recompute_daily(
            db, account_id, cur.date().isoformat(), force=force, actor=actor))
        cur += timedelta(days=1)
    return _summary(results)


async def recompute_for_orders(db, order_ids: Iterable[str], *,
                               force: bool = False, actor: str = "system") -> dict:
    """Hitung ulang HANYA (toko, tanggal) yang tersentuh daftar pesanan ini."""
    ids = [i for i in (order_ids or []) if i]
    if not ids:
        return _summary([])
    pairs: Set[Tuple[str, str]] = set()
    CHUNK = 1000
    for n in range(0, len(ids), CHUNK):
        docs = await db[ORDERS].find(
            {"id": {"$in": ids[n:n + CHUNK]}},
            {"_id": 0, "account_id": 1, "order_date": 1}).to_list(CHUNK)
        for d in docs:
            key = order_date_key(d.get("order_date"))
            if d.get("account_id") and key:
                pairs.add((d["account_id"], key))
    return await recompute_pairs(db, pairs, force=force, actor=actor)


async def recompute_pairs(db, pairs: Iterable[Tuple[str, str]], *,
                          force: bool = False, actor: str = "system") -> dict:
    """Hitung ulang daftar (account_id, date) — dipakai hook rollback/ubah status."""
    results = []
    for account_id, date in sorted(set(pairs)):
        results.append(await recompute_daily(db, account_id, date, force=force, actor=actor))
    return _summary(results)


def _summary(results: List[dict]) -> dict:
    return {
        "dates": len(results),
        "upserted": sum(1 for r in results if r.get("action") == "upserted"),
        "deleted": sum(1 for r in results if r.get("action") == "deleted"),
        "skipped_override": sum(1 for r in results if r.get("action") == "skipped_override"),
        "orders": sum(r.get("orders") or 0 for r in results),
        "revenue_product": round(sum(r.get("revenue_product") or 0 for r in results), 2),
        "details": results[:200],
    }


async def pairs_from_orders(db, query: dict) -> Set[Tuple[str, str]]:
    """(account_id, date) dari sebuah kueri pesanan — dipakai SEBELUM menghapus."""
    out: Set[Tuple[str, str]] = set()
    docs = await db[ORDERS].find(query, {"_id": 0, "account_id": 1, "order_date": 1}
                                 ).to_list(20000)
    for d in docs:
        key = order_date_key(d.get("order_date"))
        if d.get("account_id") and key:
            out.add((d["account_id"], key))
    return out
