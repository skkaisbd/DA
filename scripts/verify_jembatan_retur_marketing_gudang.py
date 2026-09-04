#!/usr/bin/env python3
"""verify_jembatan_retur_marketing_gudang.py — SESI #29 (permintaan pemilik W4).

GATE **INV-F31** — "RETUR PEMBELI HARUS SAMPAI KE GUDANG DAN KEMBALI KE STOK."

═══════════════════════════════════════════════════════════════════════════════
YANG TERUKUR SEBELUM PERBAIKAN (2026-08-19, DB preview — bukan dugaan)
═══════════════════════════════════════════════════════════════════════════════
Keluhan pemilik: menu **Retur Fisik** & **Restock Gudang** "tidak terkoneksi ke
portal marketing". Diukur:

  · `marketing_returns` = **30 dokumen** (retur pembeli nyata)
  · `wh_returns`        = **0 dokumen**   ⇒ antrean gudang KOSONG SELAMANYA
  · `production_returns`/`production_return_items` = 0
  · Jembatan yang ada harus DIKLIK MANUAL, hanya untuk status approved/completed,
    dan mengirim `sku_code=""` + `qty=1` ⇒ gudang tidak tahu barang apa yang
    kembali, jadi restock mustahil tepat.
  · `POST /api/wh/returns/{id}/resolve` "Restock ke Gudang" menulis ke
    `rahaza_fg_inventory` — koleksi **MATI (0 dokumen)** — dan bukan lewat
    `core/stock_service` ⇒ **stok nyata tidak pernah bertambah**, 0 baris ledger.

INVARIAN YANG DIJAGA GATE INI
-----------------------------
  R1  PINTUNYA ADA di layar: modul `wh-returns` terdaftar & muncul di sidebar
      Gudang; tombol "Tarik Retur dari Marketing" + aksi "Terima & Restock"
      (dengan pilihan kondisi) benar-benar ada di berkas layar; layar Marketing
      punya pemilih kondisi Baik/Rusak. (Pemilik: JANGAN pernah dimatikan.)
  R2  TIDAK ADA JALUR STOK MATI: `routes/dewi_wh_returns.py` tidak lagi menulis
      `rahaza_fg_inventory`/`rahaza_fg_movements`; restock melewati SSOT
      `core/returns_bridge` → `core/stock_service`; route Marketing memanggil
      jembatan saat retur DIBUAT (otomatis, bukan tombol manual saja).
  R3  DATA NYATA tersambung: 0 retur pembeli (selain ditolak/dibatalkan) yang
      belum punya pekerjaan Retur Fisik di gudang.
  R4  Retur baru kondisi **Baik** ⇒ `wh_returns` otomatis lahir, stok BERTAMBAH
      di `ZNA-FG` lewat `stock_service` (ada baris `rahaza_stock_ledger` dengan
      `ref.ref_id` = id retur gudang, sesuai aturan INV-F30 V15).
  R5  Kondisi **Rusak** ⇒ stok masuk `ZNA-KARANTINA` dan **stok JUAL tidak
      bertambah** (K-6a `core/catalog_stock`) ⇒ barang rusak tidak bisa terjual.
  R6  IDEMPOTEN: menjembatani/menekan restock dua kali TIDAK menggandakan
      dokumen maupun stok.
  R7  TIDAK MENEBAK: pesanan multi-baris tanpa penunjuk produk ⇒ retur tetap
      MUNCUL di gudang, ditandai `needs_manual_resolution`, dan stok TIDAK
      disentuh.
  R8  Rantai balik jujur: retur Marketing menerima `wh_return_code`, status,
      qty & efek stok (stok jual vs karantina).
  R9  0 rujukan menggantung: setiap `wh_returns.material_id` ada di
      `rahaza_materials`; setiap `source_marketing_return_id` ada di
      `marketing_returns`.
  R10 ALAT UKUR TIDAK MENGOTORI: seluruh artefak uji dihapus & stok dikembalikan
      persis (jumlah dokumen + total stok + jumlah kartu stok sama seperti
      sebelum gate) — aturan INV-F30 V15.

Pakai:  python3 scripts/verify_jembatan_retur_marketing_gudang.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

load_dotenv(ROOT / "backend" / ".env")

from core import returns_bridge as rb                             # noqa: E402
from core import catalog_stock as cs                              # noqa: E402
from core import stock_service                                    # noqa: E402
from core.stock_schema import read_qty                            # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list = []
FAIL: list = []

FE_WH = ROOT / "frontend/src/components/erp/WHReturnsModule.jsx"
FE_MKT = ROOT / "frontend/src/components/erp/marketing/ReturnsRefundsModule.jsx"
FE_REG = ROOT / "frontend/src/components/erp/moduleRegistry.js"
FE_NAV = ROOT / "frontend/src/components/erp/portal-shell/portalNav.js"
BE_WH = ROOT / "backend/routes/dewi_wh_returns.py"
BE_MKT = ROOT / "backend/routes/marketing_returns_routes.py"
BE_BRIDGE = ROOT / "backend/core/returns_bridge.py"

TAG = "UJI-F31"
WATCH = ("wh_returns", "marketing_returns", "rahaza_material_stock",
         "rahaza_stock_ledger", "rahaza_materials", "marketing_catalog_items",
         "counters")


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


def _now():
    return datetime.now(timezone.utc)


async def snapshot(db):
    counts = {c: await db[c].count_documents({}) for c in WATCH}
    rows = await db.rahaza_material_stock.find({}, {"_id": 0}).to_list(20000)
    counts["_total_qty"] = round(sum(read_qty(r) for r in rows), 4)
    return counts


# ═════════════════════════════════════════════════════════════════════════════
async def r1_layar():
    head("R1 — pintunya ADA di layar (pemilik: jangan pernah dimatikan)")
    reg = FE_REG.read_text(encoding="utf-8")
    nav = FE_NAV.read_text(encoding="utf-8")
    wh = FE_WH.read_text(encoding="utf-8")
    mkt = FE_MKT.read_text(encoding="utf-8")

    miss = []
    if "'wh-returns'" not in reg:
        miss.append("moduleRegistry tidak memuat wh-returns")
    if "'wh-returns'" not in nav:
        miss.append("sidebar portal tidak memuat wh-returns")
    if miss:
        bad("R1", "menu Retur Fisik hilang dari layar", "; ".join(miss))
    else:
        ok("R1", "modul & menu Retur Fisik terdaftar", "moduleRegistry + portalNav")

    need_wh = {
        "btn-pull-marketing": "tombol Tarik Retur dari Marketing",
        "quick-restock-": "aksi cepat Terima & Restock di baris tabel",
        "quick-condition": "pemilih kondisi Baik/Rusak saat restock",
        "confirm-quick-restock-btn": "tombol konfirmasi masuk stok",
        "mkt-bridge-banner": "spanduk angka jembatan Marketing→Gudang",
        "ret-material-select": "pemilih barang dari MASTER (INV-F14)",
    }
    hilang = [v for k, v in need_wh.items() if k not in wh]
    if hilang:
        bad("R1b", "layar Gudang belum menyediakan jalannya", "; ".join(hilang))
    else:
        ok("R1b", "layar Gudang punya tombol tarik, aksi cepat, pemilih kondisi & master",
           f"{len(need_wh)} penanda uji ditemukan")

    need_mkt = {"return-condition-select": "pemilih kondisi barang (Baik/Rusak)",
                "return-qty-input": "jumlah barang kembali",
                "mkt-ret-stock-effect": "penjelasan efek stok"}
    hilang2 = [v for k, v in need_mkt.items() if k not in mkt]
    if hilang2:
        bad("R1c", "layar Marketing belum menanyakan kondisi barang", "; ".join(hilang2))
    else:
        ok("R1c", "layar Marketing menanyakan kondisi & jumlah, lalu menyatakan efek stok")


async def r2_kode():
    head("R2 — tidak ada jalur stok mati; stok hanya lewat satu pintu")
    src_wh = BE_WH.read_text(encoding="utf-8")
    src_mkt = BE_MKT.read_text(encoding="utf-8")
    src_bridge = BE_BRIDGE.read_text(encoding="utf-8")

    dead = [c for c in ("rahaza_fg_inventory", "rahaza_fg_movements")
            if f"db.{c}" in src_wh]
    if dead:
        bad("R2", "route retur gudang masih menulis koleksi stok MATI", ", ".join(dead))
    else:
        ok("R2", "koleksi stok mati tidak dipakai lagi di route retur gudang",
           "rahaza_fg_inventory / rahaza_fg_movements")

    if "returns_bridge" not in src_wh or "_rb.restock" not in src_wh:
        bad("R2b", "resolve retur gudang tidak memakai SSOT jembatan retur")
    elif "stock_service" not in src_bridge:
        bad("R2b", "jembatan retur tidak memakai core/stock_service")
    else:
        ok("R2b", "restock retur melewati core/returns_bridge → core/stock_service",
           "alias skema & available_quantity terjaga + ledger tertulis")

    if "ensure_wh_return" not in src_mkt:
        bad("R2c", "membuat retur di Marketing tidak memicu jembatan ke Gudang")
    else:
        ok("R2c", "retur Marketing memicu jembatan otomatis saat DIBUAT",
           "bukan hanya tombol manual")


async def r3_data_nyata(db):
    head("R3 — data NYATA tersambung (bukan hanya kodenya benar)")
    q = {"status": {"$nin": list(rb.SKIP_STATUSES)}}
    total = await db.marketing_returns.count_documents(q)
    linked = [x for x in await db.wh_returns.distinct("source_marketing_return_id") if x]
    pending = await db.marketing_returns.count_documents({**q, "id": {"$nin": linked}})
    wh_total = await db.wh_returns.count_documents({})
    restocked = await db.wh_returns.count_documents({"restocked": True})
    if total == 0:
        bad("R3", "TIDAK TERUKUR: tidak ada retur pembeli di data")
        return
    if pending > 0:
        bad("R3", f"{pending} dari {total} retur pembeli belum punya pekerjaan Retur Fisik",
            "tekan 'Tarik Retur dari Marketing' / POST /api/wh/returns/sync-marketing")
    else:
        ok("R3", f"{total}/{total} retur pembeli sudah punya pekerjaan Retur Fisik",
           f"wh_returns={wh_total} · sudah masuk stok={restocked}")


# ═════════════════════════════════════════════════════════════════════════════
async def _pilih_material(db):
    """Material FG yang punya item katalog (supaya efek stok jual bisa diukur)."""
    it = await db.marketing_catalog_items.find_one(
        {"fg_material_id": {"$nin": [None, ""]}}, {"_id": 0})
    if not it:
        return None, None
    mat = await db.rahaza_materials.find_one({"id": it["fg_material_id"]}, {"_id": 0})
    return mat, it


async def _buat_retur_uji(db, *, condition, qty, catalog_item_id=None, order_id=None,
                          product=""):
    doc = {
        "id": f"{TAG}-{uuid.uuid4()}",
        "date": _now().date().isoformat(),
        "order_id": order_id or f"{TAG}-ORDER",
        "catalog_item_id": catalog_item_id,
        "product": product or f"{TAG} produk",
        "price": 100000.0,
        "qty": qty,
        "item_condition": condition,
        "reason": "produk_cacat", "reason_label": "Produk Cacat/Rusak",
        "reason_detail": f"{TAG} uji otomatis", "courier": "jnt",
        "status": "pending", "refund_type": "full_refund", "refund_amount": 100000.0,
        "notes": TAG, "created_by": TAG,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.marketing_returns.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def r4_r8_fungsional(db, ctx):
    head("R4/R5/R6/R7/R8 — uji fungsional pada data hidup (self-cleaning)")
    mat, item = await _pilih_material(db)
    if not mat:
        bad("R4", "TIDAK TERUKUR: tidak ada material FG bertaut item katalog")
        return
    mid = mat["id"]
    ctx["material_id"] = mid
    onhand0 = await stock_service.get_onhand(mid, db=db)
    jual0 = (await cs.sellable_stock(db, mid))["onhand"]

    # ── R4: kondisi BAIK → stok jual bertambah di ZNA-FG ─────────────────────
    ret_baik = await _buat_retur_uji(db, condition="Baik", qty=2,
                                     catalog_item_id=item["id"])
    ctx["mkt_ids"].append(ret_baik["id"])
    res = await rb.ensure_wh_return(db, ret_baik, actor={"name": TAG},
                                    condition="Baik", auto_restock=True)
    wh = res.get("wh_return") or {}
    ctx["wh_ids"].append(wh.get("id"))
    onhand1 = await stock_service.get_onhand(mid, db=db)
    jual1 = (await cs.sellable_stock(db, mid))["onhand"]
    ledger = await db.rahaza_stock_ledger.count_documents(
        {"ref.ref_id": wh.get("id"), "op": "add"})
    if (res.get("created") and wh.get("restocked")
            and wh.get("restock_location_code") == rb.LOC_SELLABLE
            and round(onhand1 - onhand0, 4) == 2 and round(jual1 - jual0, 4) == 2
            and ledger == 1):
        ok("R4", "retur kondisi Baik otomatis lahir di gudang & MENAMBAH stok jual",
           f"{wh.get('return_code')} · on-hand {onhand0}→{onhand1} · "
           f"stok jual {jual0}→{jual1} · 1 baris ledger (ref.ref_id)")
    else:
        bad("R4", "retur kondisi Baik tidak menambah stok sebagaimana mestinya",
            f"created={res.get('created')} restocked={wh.get('restocked')} "
            f"lokasi={wh.get('restock_location_code')} onhand={onhand0}→{onhand1} "
            f"jual={jual0}→{jual1} ledger={ledger}")

    # ── R8: rantai balik ke Marketing ────────────────────────────────────────
    mkt = await db.marketing_returns.find_one({"id": ret_baik["id"]}, {"_id": 0})
    if (mkt and mkt.get("wh_return_code") and mkt.get("wh_restocked") is True
            and mkt.get("wh_stock_effect") == "sellable"
            and int(mkt.get("wh_restock_qty") or 0) == 2):
        ok("R8", "retur Marketing menerima balikan jujur dari gudang",
           f"{mkt['wh_return_code']} · efek={mkt['wh_stock_effect']} · qty={mkt['wh_restock_qty']}")
    else:
        bad("R8", "layar Marketing tidak tahu apa yang terjadi pada barangnya",
            str({k: (mkt or {}).get(k) for k in
                 ("wh_return_code", "wh_restocked", "wh_stock_effect", "wh_restock_qty")}))

    # ── R6: idempoten ────────────────────────────────────────────────────────
    mkt_refresh = await db.marketing_returns.find_one({"id": ret_baik["id"]}, {"_id": 0})
    res2 = await rb.ensure_wh_return(db, mkt_refresh, actor={"name": TAG},
                                     condition="Baik", auto_restock=True)
    n_wh = await db.wh_returns.count_documents(
        {"source_marketing_return_id": ret_baik["id"]})
    onhand2 = await stock_service.get_onhand(mid, db=db)
    if not res2.get("created") and n_wh == 1 and onhand2 == onhand1:
        ok("R6", "menjembatani ulang TIDAK menggandakan dokumen maupun stok",
           f"wh_returns={n_wh} · on-hand tetap {onhand2}")
    else:
        bad("R6", "jembatan tidak idempoten",
            f"created={res2.get('created')} dokumen={n_wh} onhand={onhand1}→{onhand2}")

    # restock manual kedua juga harus ditolak
    wh_now = await db.wh_returns.find_one({"id": wh.get("id")}, {"_id": 0})
    res3 = await rb.restock(db, wh_now, condition="Baik", qty=2, actor={"name": TAG})
    onhand3 = await stock_service.get_onhand(mid, db=db)
    if res3.get("already") and onhand3 == onhand1:
        ok("R6b", "restock kedua ditolak penjaga atomik", f"on-hand tetap {onhand3}")
    else:
        bad("R6b", "restock bisa dijalankan dua kali (stok menggelembung)",
            f"{res3.get('message')} · onhand={onhand1}→{onhand3}")

    # ── R5: kondisi RUSAK → karantina, stok jual TIDAK bertambah ─────────────
    jual_before = (await cs.sellable_stock(db, mid))["onhand"]
    ret_rusak = await _buat_retur_uji(db, condition="Rusak", qty=3,
                                      catalog_item_id=item["id"])
    ctx["mkt_ids"].append(ret_rusak["id"])
    res4 = await rb.ensure_wh_return(db, ret_rusak, actor={"name": TAG},
                                     condition="Rusak", auto_restock=True)
    wh4 = res4.get("wh_return") or {}
    ctx["wh_ids"].append(wh4.get("id"))
    sell_after = await cs.sellable_stock(db, mid)
    onhand4 = await stock_service.get_onhand(mid, db=db)
    if (wh4.get("restocked") and wh4.get("restock_location_code") == rb.LOC_QUARANTINE
            and wh4.get("stock_effect") == "quarantine"
            and round(onhand4 - onhand3, 4) == 3
            and round(sell_after["onhand"] - jual_before, 4) == 0
            and sell_after["excluded_onhand"] >= 3):
        ok("R5", "barang RUSAK masuk karantina & TIDAK bisa dijual",
           f"{wh4.get('return_code')} · on-hand {onhand3}→{onhand4} · "
           f"stok jual tetap {sell_after['onhand']} · dikecualikan "
           f"{sell_after['excluded_onhand']}")
    else:
        bad("R5", "barang rusak tidak ditahan sebagaimana mestinya",
            f"lokasi={wh4.get('restock_location_code')} efek={wh4.get('stock_effect')} "
            f"onhand={onhand3}→{onhand4} jual={jual_before}→{sell_after['onhand']}")

    # ── R7: pesanan multi-baris tanpa penunjuk → tidak menebak ───────────────
    multi = None
    async for o in db.marketing_orders.find(
            {"items.1": {"$exists": True}},
            {"_id": 0, "order_id": 1, "items": 1}):
        if len([i for i in (o.get("items") or []) if i.get("fg_material_id")]) > 1:
            multi = o
            break
    if not multi:
        ok("R7", "TIDAK BERLAKU: tidak ada pesanan multi-baris tertaut di data",
           "aturan tetap dijaga oleh core/returns_bridge.resolve_identity")
    else:
        onhand5 = await stock_service.get_onhand(mid, db=db)
        ret_amb = await _buat_retur_uji(db, condition="Baik", qty=1,
                                        order_id=multi["order_id"],
                                        product=f"{TAG} tidak jelas produknya")
        ctx["mkt_ids"].append(ret_amb["id"])
        res5 = await rb.ensure_wh_return(db, ret_amb, actor={"name": TAG},
                                        condition="Baik", auto_restock=True)
        wh5 = res5.get("wh_return") or {}
        ctx["wh_ids"].append(wh5.get("id"))
        onhand6 = await stock_service.get_onhand(mid, db=db)
        total_stock = await snapshot(db)
        if (wh5.get("link_status") == rb.LINK_AMBIGUOUS and not wh5.get("restocked")
                and wh5.get("link_reason") and onhand6 == onhand5):
            ok("R7", "pesanan multi-baris: pekerjaan MUNCUL tapi stok tidak ditebak",
               f"{wh5.get('return_code')} · {wh5['link_status']} · "
               f"kandidat={len(wh5.get('link_candidates') or [])}")
        else:
            bad("R7", "jembatan MENEBAK barang pada pesanan multi-baris",
                f"link={wh5.get('link_status')} restocked={wh5.get('restocked')} "
                f"onhand={onhand5}→{onhand6} total={total_stock['_total_qty']}")


async def r9_gantung(db):
    head("R9 — 0 rujukan menggantung")
    mids = {m["id"] async for m in db.rahaza_materials.find({}, {"_id": 0, "id": 1})}
    bad_mat, bad_src = [], []
    async for w in db.wh_returns.find({}, {"_id": 0, "id": 1, "return_code": 1,
                                           "material_id": 1,
                                           "source_marketing_return_id": 1}):
        if w.get("material_id") and w["material_id"] not in mids:
            bad_mat.append(w.get("return_code"))
        src = w.get("source_marketing_return_id")
        if src and not await db.marketing_returns.find_one({"id": src}, {"_id": 1}):
            bad_src.append(w.get("return_code"))
    if bad_mat or bad_src:
        bad("R9", "ada retur gudang menunjuk data yang tidak ada",
            f"material hilang: {bad_mat[:3]} · retur Marketing hilang: {bad_src[:3]}")
    else:
        ok("R9", "setiap retur gudang menunjuk master & retur Marketing yang benar-benar ada")


async def cleanup(db, ctx):
    """Kembalikan SEMUA yang disentuh gate (INV-F30 V15)."""
    for wid in [x for x in ctx["wh_ids"] if x]:
        w = await db.wh_returns.find_one({"id": wid}, {"_id": 0})
        if w and w.get("restocked") and w.get("material_id") and w.get("restock_qty"):
            try:
                await stock_service.issue(
                    w["material_id"], w.get("restock_location_id"),
                    float(w["restock_qty"]),
                    ref={"type": "uji_f31_cleanup", "ref_id": wid},
                    actor={"name": TAG}, db=db)
            except Exception as e:  # noqa: BLE001
                print(f"  {Y}! cleanup: gagal mengembalikan stok {wid}: {e}{X}")
        await db.rahaza_stock_ledger.delete_many({"ref.ref_id": wid})
        await db.wh_returns.delete_one({"id": wid})
    for mkt_id in ctx["mkt_ids"]:
        await db.marketing_returns.delete_one({"id": mkt_id})
    await db.marketing_returns.delete_many({"id": {"$regex": f"^{TAG}"}})
    await db.wh_returns.delete_many({"created_by": TAG})
    # baris stok yang lahir dari uji (karantina) & tersisa kosong → hapus
    async for r in db.rahaza_material_stock.find(
            {"material_id": ctx.get("material_id"), "qty": 0}, {"_id": 0}):
        if r.get("location_code") == rb.LOC_QUARANTINE:
            await db.rahaza_material_stock.delete_one({"id": r["id"]})
    # segarkan kembali cache stok katalog supaya angkanya tidak tertinggal
    if ctx.get("material_id"):
        await rb.refresh_catalog_cache(db, ctx["material_id"])


async def r10_alat_ukur(db, snap0):
    head("R10 — alat ukur tidak boleh mengotori data yang diukurnya")
    snap1 = await snapshot(db)
    beda = {k: (snap0[k], snap1[k]) for k in snap0
            if k != "counters" and snap1.get(k) != snap0[k]}
    if beda:
        bad("R10", "gate meninggalkan jejak di data", str(beda))
    else:
        ok("R10", "seluruh artefak uji dihapus & stok kembali persis",
           f"total stok {snap1['_total_qty']} · wh_returns {snap1['wh_returns']} · "
           f"kartu stok {snap1['rahaza_stock_ledger']}")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print(f"{C}{B}INV-F31 — RETUR PEMBELI HARUS SAMPAI KE GUDANG DAN KEMBALI KE STOK{X}")
    snap0 = await snapshot(db)
    ctx = {"wh_ids": [], "mkt_ids": [], "material_id": None}
    try:
        await r1_layar()
        await r2_kode()
        await r3_data_nyata(db)
        await r4_r8_fungsional(db, ctx)
        await r9_gantung(db)
    finally:
        await cleanup(db, ctx)
    await r10_alat_ukur(db, snap0)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian jembatan retur terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
