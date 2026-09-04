"""core.marketing_live_products — **SSOT rincian produk per sesi live**.

CACAT YANG DISELESAIKAN BERKAS INI
---------------------------------
`GET /api/marketing/live/analytics/product-performance` sudah ada sejak lama dan
meng-`$unwind` field `products` pada `marketing_live_sessions`. Masalahnya:
**tidak ada satu pun jalan untuk mengisi field itu** — CRUD sesi live (F16) tidak
menerimanya, impor tidak menerimanya, seed tidak menulisnya. Jadi endpoint itu
selalu membalas daftar kosong, dan pertanyaan yang paling sering diajukan pemilik
toko sesudah live — *"tadi barang mana yang paling laku?"* — tidak bisa dijawab
oleh aplikasi, padahal jawabannya menentukan apa yang dibawakan di sesi besok dan
berapa yang harus disiapkan gudang.

Cacat kedua di endpoint yang sama: parameter `account_id` **diterima tetapi tidak
pernah dipakai** di `$match`. Layar mengirim filter toko, server mengabaikannya,
dan angka toko A tercampur toko B **tanpa satu pun error** — bentuk kesalahan
yang paling berbahaya karena terlihat meyakinkan.

KEPUTUSAN PENYIMPANAN
---------------------
Rincian produk disimpan sebagai **koleksi sendiri** (`marketing_live_session_products`),
satu dokumen = satu produk pada satu sesi. Bukan array di dalam dokumen sesi.
Alasannya konkret:

* mesin impor tanpa AI (F17) menulis **baris**, dan rollback-nya menghapus baris
  berdasarkan `_import_session_id`; array di dalam dokumen lain tidak bisa
  di-rollback dengan mekanisme yang sudah terbukti itu;
* analitik butuh `$group` per produk lintas sesi — dengan koleksi sendiri cukup
  satu indeks, tanpa `$unwind` seluruh koleksi sesi;
* satu baris bisa punya jejak audit sendiri (siapa mengisi, dari impor mana).

Yang TIDAK berubah: sesi live tetap pemilik angka totalnya (`revenue`, `orders`).
Rincian produk adalah **penjabaran** dari total itu, dan berkas ini yang menjaga
keduanya tidak saling membantah (lihat :func:`reconcile`).

ATURAN YANG DITEGAKKAN DI SINI (bukan di layar)
-----------------------------------------------
1. **Produk WAJIB item katalog milik toko sesi itu.** Rincian sesi toko A yang
   menunjuk produk toko B akan merusak dua laporan sekaligus tanpa terlihat.
2. **Satu produk hanya boleh muncul sekali per sesi.** Kalau boleh dobel, "produk
   terlaris" jadi hasil penjumlahan baris yang sama dua kali.
3. **Rincian tidak boleh melebihi omzet sesi** (toleransi 2% untuk pembulatan
   ongkir/diskon platform). Kalau dibiarkan, omzet live dihitung dua kali:
   sekali di total sesi, sekali di rincian.
4. **Omzet tanpa unit terjual ditolak.** `units_sold = 0` sah (produk dibawakan
   tapi tidak ada yang beli — justru informasi penting), tetapi `revenue > 0`
   dengan `0` unit adalah salah input.
5. **Lingkup toko diwarisi dari sesi**, tidak diterima dari layar. Dengan begitu
   lingkup baris rincian tidak mungkin berbeda dari sesinya.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

COLLECTION = "marketing_live_session_products"
SESSIONS = "marketing_live_sessions"
CATALOG_ITEMS = "marketing_catalog_items"

# Toleransi over-alokasi omzet: pembulatan ongkir/diskon platform pada laporan
# marketplace sering membuat jumlah rincian berbeda beberapa rupiah dari total
# sesi. 2% cukup untuk itu, dan masih jauh di bawah "satu produk kelebihan".
OVER_TOLERANCE = 0.02

# Field yang boleh ditulis oleh layar/impor (sisanya turunan).
INPUT_FIELDS = ("catalog_item_id", "units_sold", "revenue", "orders", "notes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def to_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def rp(v: Any) -> str:
    """Rupiah gaya Indonesia. Dipakai di PESAN — sebelumnya dipakai
    `f"{x:,.0f}".replace(",", ".")` di tempat pemakaian, dan penggantian global
    itu ikut mengubah koma pada kalimatnya ("Isi unit terjualnya, atau…" menjadi
    "Isi unit terjualnya. atau…"). Angka diformat di satu tempat saja.
    """
    return "Rp " + f"{int(round(num(v))):,}".replace(",", ".")


def pct(v: Any) -> str:
    """Persen dengan pembulatan yang SAMA di semua tempat.

    Cacat yang ditutup: satu angka cakupan tampil TIGA versi di satu dialog —
    kolom tabel "69.5%", baris rekonsiliasi "69%" (dihitung ulang di JS), dan
    pesan server "70%" (`:.0f` atas nilai 69.5). Layar yang membantah dirinya
    sendiri membuat orang memilih angka yang paling enak dilihat. Sekarang satu
    format: satu desimal, tanpa ".0" yang menggantung.
    """
    f = round(num(v), 1)
    return f"{int(f)}%" if float(f).is_integer() else f"{f}%"


def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


async def ensure_indexes(db) -> None:
    """Indeks + jaminan "satu produk sekali per sesi" di level basis data.

    Aturan yang hanya dijaga di kode akan bocor lewat impor, skrip, atau endpoint
    baru yang lupa memanggilnya. Indeks unik menutup semuanya sekaligus.
    """
    try:
        await db[COLLECTION].create_index("id", unique=True)
        await db[COLLECTION].create_index("session_id")
        await db[COLLECTION].create_index("account_id")
        await db[COLLECTION].create_index("session_date")
        await db[COLLECTION].create_index("catalog_item_id")
        await db[COLLECTION].create_index(
            [("session_id", 1), ("catalog_item_id", 1)],
            unique=True, name="uniq_session_item")
    except Exception:  # pragma: no cover — indeks sudah ada / balapan startup
        logger.debug("index rincian produk live sudah ada", exc_info=True)


# ── item katalog ─────────────────────────────────────────────────────────────
async def resolve_item(db, *, account_id: str, catalog_item_id: Optional[str] = None,
                       sku: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Cari item katalog dan PASTIKAN miliknya toko sesi.

    Menerima `catalog_item_id` (dari layar) atau `sku`/`name` (dari berkas impor,
    yang tidak pernah membawa id internal kita).
    """
    from core import marketing_account_scope as scope

    item = None
    if catalog_item_id:
        item = await db[CATALOG_ITEMS].find_one({"id": catalog_item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, f"Item katalog '{catalog_item_id}' tidak ditemukan")
    elif sku or name:
        cat_ids = [c["id"] for c in await db.marketing_catalogs.find(
            {"account_id": account_id}, {"_id": 0, "id": 1}).to_list(500)]
        q: Dict[str, Any] = {"catalog_id": {"$in": cat_ids}} if cat_ids else {"catalog_id": "__none__"}
        if sku:
            item = await db[CATALOG_ITEMS].find_one({**q, "sku": sku}, {"_id": 0})
            if not item:  # cocokkan longgar (spasi/besar-kecil huruf)
                for cand in await db[CATALOG_ITEMS].find(q, {"_id": 0}).to_list(5000):
                    if scope.norm(cand.get("sku")) == scope.norm(sku):
                        item = cand
                        break
        if item is None and name:
            for cand in await db[CATALOG_ITEMS].find(q, {"_id": 0}).to_list(5000):
                if scope.norm(cand.get("name")) == scope.norm(name):
                    item = cand
                    break
        if not item:
            raise HTTPException(
                404, f"SKU/produk '{sku or name}' tidak ada di katalog toko ini. "
                     f"Tambahkan dulu di Manajemen Katalog, atau perbaiki SKU-nya — "
                     f"rincian yang tidak tertaut master tidak bisa dipakai laporan.")
    else:
        raise HTTPException(400, "Produk wajib: pilih item dari katalog toko.")

    if account_id and item.get("account_id") and item["account_id"] != account_id:
        raise HTTPException(
            400, f"Produk '{item.get('name')}' bukan milik toko sesi ini. "
                 f"Pilih produk dari katalog toko yang membawakan sesinya.")
    return item


# ── satu baris rincian ───────────────────────────────────────────────────────
def build_line(session: dict, item: dict, data: dict, *, user_email: str = "system",
               line_id: Optional[str] = None) -> dict:
    """Bentuk dokumen rincian. Semua angka turunan dihitung di sini, sekali."""
    units = to_int(data.get("units_sold"), 0)
    revenue = round(num(data.get("revenue"), 0.0), 2)
    orders = to_int(data.get("orders"), 0)
    if units < 0 or revenue < 0 or orders < 0:
        raise HTTPException(400, "Unit terjual, omzet, dan jumlah order tidak boleh negatif")
    if units == 0 and revenue > 0:
        raise HTTPException(
            400, f"Produk '{item.get('name')}': omzet {rp(revenue)} tapi 0 unit "
                 f"terjual. Isi unit terjualnya, atau nolkan omzetnya.")

    hpp = num(item.get("hpp"), 0.0)
    doc = {
        "id": line_id or str(uuid.uuid4()),
        "session_id": session.get("id"),
        "session_date": session.get("session_date"),
        "session_title": session.get("title", ""),
        # lingkup toko DIWARISI dari sesi — tidak diterima dari layar
        "account_id": session.get("account_id"),
        "account_name": session.get("account_name", ""),
        "platform": session.get("platform", ""),
        "host_id": session.get("host_id"),
        "host_name": session.get("host_name", ""),
        # produk dari MASTER
        "catalog_item_id": item.get("id"),
        "sku": item.get("sku", ""),
        "product_name": item.get("name", ""),
        "category": item.get("category", ""),
        "hpp": hpp,
        "harga_jual_master": num(item.get("harga_jual") or item.get("price"), 0.0),
        # angka yang diisi manusia
        "units_sold": units,
        "revenue": revenue,
        "orders": orders,
        "notes": (data.get("notes") or "")[:500],
        # angka turunan (tidak boleh diketik — supaya tidak ada dua versi)
        "price_avg": round(revenue / units, 2) if units else 0.0,
        "hpp_total": round(hpp * units, 2),
        "gross_margin": round(revenue - hpp * units, 2),
        "gross_margin_pct": (round((revenue - hpp * units) / revenue * 100, 2)
                             if revenue else 0.0),
        "updated_at": _now(),
        "updated_by": user_email,
    }
    return doc


# ── rekonsiliasi terhadap total sesi ────────────────────────────────────────
def reconcile(session: dict, lines: List[dict]) -> dict:
    """Bandingkan rincian dengan total sesi, dan katakan apa artinya.

    Dipakai layar DAN endpoint. Tidak ada angka "coverage" versi kedua di JS.
    """
    total_revenue = round(sum(num(l.get("revenue")) for l in lines), 2)
    total_units = sum(to_int(l.get("units_sold")) for l in lines)
    total_orders = sum(to_int(l.get("orders")) for l in lines)
    s_revenue = round(num(session.get("revenue") or session.get("gmv")), 2)
    s_orders = to_int(session.get("orders") or session.get("total_orders"))
    s_units = to_int(session.get("units_sold"))

    over = bool(s_revenue > 0 and total_revenue > s_revenue * (1 + OVER_TOLERANCE))
    unallocated = round(max(s_revenue - total_revenue, 0.0), 2)
    coverage = round(total_revenue / s_revenue * 100, 1) if s_revenue else 0.0

    if not lines:
        status, message = "kosong", (
            "Sesi ini belum punya rincian produk. Tambahkan produk yang laku supaya "
            "laporan 'Produk Terlaris saat Live' bisa menjawab barang mana yang "
            "harus dibawakan lagi.")
    elif over:
        status, message = "melebihi", (
            f"Rincian produk {rp(total_revenue)} MELEBIHI omzet sesi "
            f"{rp(s_revenue)}. Salah satunya keliru — perbaiki angka produk, "
            f"atau samakan total sesi dengan rincian.")
    elif s_revenue <= 0:
        status, message = "sesi_tanpa_omzet", (
            f"Rincian produk terisi {rp(total_revenue)}, tetapi omzet sesi masih "
            f"Rp 0. Tekan 'Samakan total sesi' supaya kartu KPI live tidak melaporkan "
            f"nol di atas rincian yang jelas ada isinya.")
    elif unallocated <= max(s_revenue * OVER_TOLERANCE, 1):
        status, message = "lengkap", (
            f"Rincian sudah menjelaskan seluruh omzet sesi ({pct(coverage)}).")
    else:
        status, message = "sebagian", (
            f"Rincian menjelaskan {pct(coverage)} omzet sesi; "
            f"{rp(unallocated)} belum terinci per produk.")

    return {
        "lines_count": len(lines),
        "total_units": total_units,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "session_revenue": s_revenue,
        "session_orders": s_orders,
        "session_units_sold": s_units,
        "unallocated_revenue": unallocated,
        "coverage_pct": coverage,
        "over_allocated": over,
        "units_over_session": bool(s_units > 0 and total_units > s_units),
        "status": status,
        "message": message,
    }


def assert_not_over_allocated(session: dict, lines: List[dict]) -> dict:
    """Tolak keras over-alokasi. Omzet yang dihitung dua kali adalah uang palsu."""
    rec = reconcile(session, lines)
    if rec["over_allocated"]:
        raise HTTPException(400, rec["message"])
    return rec


# ── baca ─────────────────────────────────────────────────────────────────────
async def list_lines(db, session_id: str) -> List[dict]:
    return await db[COLLECTION].find({"session_id": session_id}, {"_id": 0}).sort(
        "revenue", -1).to_list(500)


async def summary_for_sessions(db, session_ids: List[str]) -> Dict[str, dict]:
    """Ringkasan rincian untuk BANYAK sesi dalam satu agregasi (dipakai tabel).

    Tanpa ini, tabel 20 baris akan memanggil 20 kueri — dan yang pertama kali
    dikorbankan orang saat itu terjadi adalah kolomnya, bukan kuerinya.
    """
    if not session_ids:
        return {}
    rows = await db[COLLECTION].aggregate([
        {"$match": {"session_id": {"$in": session_ids}}},
        {"$group": {
            "_id": "$session_id",
            "lines_count": {"$sum": 1},
            "total_units": {"$sum": {"$ifNull": ["$units_sold", 0]}},
            "total_revenue": {"$sum": {"$ifNull": ["$revenue", 0]}},
            "total_orders": {"$sum": {"$ifNull": ["$orders", 0]}},
        }},
    ]).to_list(len(session_ids) + 10)
    return {r["_id"]: {k: v for k, v in r.items() if k != "_id"} for r in rows}


# ── tulis ────────────────────────────────────────────────────────────────────
async def add_line(db, session: dict, data: dict, *, user_email: str = "system") -> dict:
    item = await resolve_item(db, account_id=session.get("account_id"),
                              catalog_item_id=data.get("catalog_item_id"),
                              sku=data.get("sku"), name=data.get("product_name"))
    existing = await db[COLLECTION].find_one(
        {"session_id": session["id"], "catalog_item_id": item["id"]}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(
            400, f"Produk '{item.get('name')}' sudah ada pada sesi ini. Ubah baris "
                 f"yang sudah ada — kalau dobel, 'produk terlaris' menghitungnya dua kali.")
    doc = build_line(session, item, data, user_email=user_email)
    doc["created_at"] = _now()
    doc["created_by"] = user_email
    lines = await list_lines(db, session["id"])
    assert_not_over_allocated(session, lines + [doc])
    await db[COLLECTION].insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_line(db, session: dict, line_id: str, data: dict, *,
                      user_email: str = "system") -> dict:
    cur = await db[COLLECTION].find_one({"id": line_id, "session_id": session["id"]},
                                        {"_id": 0})
    if not cur:
        raise HTTPException(404, "Baris rincian produk tidak ditemukan pada sesi ini")
    merged = {**{k: cur.get(k) for k in INPUT_FIELDS},
              **{k: v for k, v in data.items() if v is not None}}
    item = await resolve_item(db, account_id=session.get("account_id"),
                              catalog_item_id=merged.get("catalog_item_id"))
    if item["id"] != cur.get("catalog_item_id"):
        clash = await db[COLLECTION].find_one(
            {"session_id": session["id"], "catalog_item_id": item["id"],
             "id": {"$ne": line_id}}, {"_id": 0, "id": 1})
        if clash:
            raise HTTPException(400, f"Produk '{item.get('name')}' sudah ada pada sesi ini.")
    doc = build_line(session, item, merged, user_email=user_email, line_id=line_id)
    doc["created_at"] = cur.get("created_at")
    doc["created_by"] = cur.get("created_by")
    if cur.get("_import_session_id"):
        doc["_import_session_id"] = cur["_import_session_id"]
    others = [l for l in await list_lines(db, session["id"]) if l["id"] != line_id]
    assert_not_over_allocated(session, others + [doc])
    await db[COLLECTION].replace_one({"id": line_id}, dict(doc))
    return doc


async def delete_line(db, session_id: str, line_id: str) -> None:
    res = await db[COLLECTION].delete_one({"id": line_id, "session_id": session_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Baris rincian produk tidak ditemukan pada sesi ini")


async def replace_lines(db, session: dict, rows: List[dict], *,
                        user_email: str = "system") -> List[dict]:
    """Ganti SELURUH rincian sesi (dipakai satu-tombol-simpan di dialog).

    Divalidasi lengkap dulu, baru ditulis — supaya kegagalan di baris ke-5 tidak
    meninggalkan sesi dengan 4 baris tersimpan dan 1 hilang.
    """
    docs: List[dict] = []
    seen: set = set()
    for i, row in enumerate(rows or []):
        item = await resolve_item(db, account_id=session.get("account_id"),
                                  catalog_item_id=row.get("catalog_item_id"),
                                  sku=row.get("sku"), name=row.get("product_name"))
        if item["id"] in seen:
            raise HTTPException(
                400, f"Produk '{item.get('name')}' ditulis dua kali pada baris rincian. "
                     f"Gabungkan jadi satu baris.")
        seen.add(item["id"])
        d = build_line(session, item, row, user_email=user_email,
                       line_id=row.get("id") or None)
        d["created_at"] = _now()
        d["created_by"] = user_email
        docs.append(d)
    assert_not_over_allocated(session, docs)
    await db[COLLECTION].delete_many({"session_id": session["id"]})
    if docs:
        await db[COLLECTION].insert_many([dict(d) for d in docs])
        for d in docs:
            d.pop("_id", None)
    return docs


# ── data demo ────────────────────────────────────────────────────────────────
# Pelajaran F14 yang jangan diulang: data demo yang dilihat staf pertama kali
# IKUT MENGAJARKAN bentuk data. Kalau 18 sesi live demo tidak punya satu pun
# rincian produk, layar "Produk Terlaris saat Live" tampak rusak di DB baru dan
# fiturnya dianggap tidak jalan. Karena itu sesi demo diberi rincian yang
# KONSISTEN: hanya memakai item katalog toko sesi itu, dan jumlahnya SELALU di
# bawah omzet sesi (tidak pernah melanggar aturan yang baru saja ditegakkan).
_DEMO_CHECKED = False


async def seed_demo_products(db) -> int:
    """Isi rincian produk untuk sesi live DEMO saja (`_seed_origin`)."""
    global _DEMO_CHECKED
    if _DEMO_CHECKED:
        return 0
    _DEMO_CHECKED = True
    if await db[COLLECTION].count_documents({}) > 0:
        return 0
    sessions = await db[SESSIONS].find({"_seed_origin": True}, {"_id": 0}).to_list(500)
    if not sessions:
        return 0

    import random

    items_cache: Dict[str, List[dict]] = {}
    docs: List[dict] = []
    for s in sessions:
        aid = s.get("account_id")
        if not aid:
            continue
        if aid not in items_cache:
            cat_ids = [c["id"] for c in await db.marketing_catalogs.find(
                {"account_id": aid}, {"_id": 0, "id": 1}).to_list(50)]
            items_cache[aid] = await db[CATALOG_ITEMS].find(
                {"catalog_id": {"$in": cat_ids}} if cat_ids else {"catalog_id": "__none__"},
                {"_id": 0}).to_list(100)
        items = items_cache[aid]
        if not items:
            continue
        rnd = random.Random(str(s.get("id")))
        s_rev = num(s.get("revenue"))
        if s_rev <= 0:
            continue
        picked = rnd.sample(items, min(len(items), rnd.randint(2, 4)))
        # rincian selalu MENJELASKAN SEBAGIAN omzet (55–95%), tidak pernah melebihi
        budget = s_rev * rnd.uniform(0.55, 0.95)
        weights = [rnd.uniform(0.6, 1.8) for _ in picked]
        wsum = sum(weights) or 1
        for item, w in zip(picked, weights):
            # dibulatkan ke rupiah penuh — nilai berkoma pada uang rupiah membuat
            # data demo terlihat seperti hasil salah hitung.
            part = float(round(budget * w / wsum))
            price = num(item.get("harga_jual") or item.get("price")) or 1
            units = max(1, int(round(part / price)))
            d = build_line(s, item, {"units_sold": units, "revenue": part,
                                    "orders": max(1, int(units * 0.8))},
                           user_email="seed")
            d["created_at"] = s.get("created_at") or _now()
            d["created_by"] = "seed"
            d["_seed_origin"] = True
            docs.append(d)
    if docs:
        await ensure_indexes(db)
        await db[COLLECTION].insert_many([dict(x) for x in docs])
        logger.info("[seed] %d baris rincian produk sesi live demo", len(docs))
    return len(docs)


async def delete_for_session(db, session_id: str) -> int:
    """Cascade: sesi dihapus ⇒ rincian ikut. Baris yatim = laporan hantu."""
    res = await db[COLLECTION].delete_many({"session_id": session_id})
    return res.deleted_count


async def sync_session_totals(db, session: dict, *, user_email: str = "system") -> dict:
    """Samakan total sesi dengan rincian — AKSI EKSPLISIT, bukan otomatis.

    Kalau total sesi diam-diam ditimpa setiap kali rincian berubah, angka dari
    laporan resmi marketplace (yang seharusnya jadi acuan) akan hilang tanpa
    jejak. Karena itu ini tombol, bukan efek samping.
    """
    from core import marketing_live_fields as _LF

    lines = await list_lines(db, session["id"])
    if not lines:
        raise HTTPException(400, "Belum ada rincian produk untuk disamakan")
    rec = reconcile(session, lines)
    upd = {
        "revenue": rec["total_revenue"],
        "units_sold": rec["total_units"],
        "products_featured": rec["lines_count"],
        "updated_at": _now(),
        "updated_by": user_email,
        "revenue_source": "rincian_produk",
    }
    if rec["total_orders"] > 0:
        upd["orders"] = rec["total_orders"]
    merged = {**session, **upd}
    _LF.compute_derived(merged)
    for k in ("engagement_rate", "conversion_rate", "aov"):
        upd[k] = merged[k]
    await db[SESSIONS].update_one({"id": session["id"]}, {"$set": upd})
    after = await db[SESSIONS].find_one({"id": session["id"]}, {"_id": 0})
    return {"before": {"revenue": num(session.get("revenue")),
                       "orders": to_int(session.get("orders")),
                       "units_sold": to_int(session.get("units_sold"))},
            "after": {"revenue": num(after.get("revenue")),
                      "orders": to_int(after.get("orders")),
                      "units_sold": to_int(after.get("units_sold"))},
            "session": serialize(after),
            "reconciliation": reconcile(after, lines)}
