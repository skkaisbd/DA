#!/usr/bin/env python3
"""
POC / FORENSIK — SINKRONISASI DATA LINTAS PORTAL (Sesi #20)
===========================================================
Keluhan pemilik (verbatim):
  "list barang dari marketing untuk dikirimkan oleh tim gudang tidak ada yang sama,
   saya cek dari id-nya antara gudang dan di marketing tidak sinkron ... cek stock
   opname sinkronisasi dengan masterdatanya apakah salah atau tidak dan semua data
   yang seharusnya tersinkronisasi dengan table data lain"

Skrip ini TIDAK menebak. Ia MENGUKUR dari data yang hidup di MongoDB:

  A. Marketing → Gudang : apakah baris pesanan marketing menunjuk barang gudang?
  B. Katalog  → FG      : apakah item katalog jual tertaut ke master FG?
  C. Varian   → FG      : apakah varian model internal punya master FG + stok?
  D. Opname   → Master  : apakah stock opname memakai id master yang sah?
  E. Integritas rujukan : semua foreign-key lintas koleksi (dangling reference)

Jalankan:  python3 /app/tests/poc_sync_forensic.py
Keluaran :  ringkasan di layar + /app/.logs/sync_forensic.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

C_RED, C_GRN, C_YEL, C_CYN, C_RST, C_BLD = (
    "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[0m", "\033[1m",
)

FINDINGS = []


def head(t):
    print(f"\n{C_BLD}{'=' * 78}\n{t}\n{'=' * 78}{C_RST}")


def sub(t):
    print(f"\n{C_CYN}--- {t} ---{C_RST}")


def ok(t):
    print(f"  {C_GRN}✓{C_RST} {t}")


def bad(t, sev="HIGH"):
    print(f"  {C_RED}✗ [{sev}]{C_RST} {t}")
    FINDINGS.append({"severity": sev, "text": t})


def warn(t):
    print(f"  {C_YEL}!{C_RST} {t}")
    FINDINGS.append({"severity": "MED", "text": t})


def pct(a, b):
    return 0.0 if not b else round(100.0 * a / b, 1)


db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
REPORT = {}


# ══════════════════════════════════════════════════════════════════════════════
# A. MARKETING → GUDANG  (keluhan utama pemilik)
# ══════════════════════════════════════════════════════════════════════════════
def audit_a_marketing_to_warehouse():
    head("A. MARKETING → GUDANG — 'list barang untuk dikirim gudang tidak ada yang sama'")

    orders = list(db.marketing_orders.find({}, {"_id": 0}))
    n_ord = len(orders)
    print(f"  Total pesanan marketing : {n_ord}")

    lines = 0
    linked_lines = 0
    linked_pcs = 0
    total_pcs = 0
    link_sources = Counter()
    orders_fully = 0
    orders_partial = 0
    orders_none = 0
    unmapped_psid = defaultdict(lambda: {"pcs": 0, "orders": 0, "name": "", "variation": ""})

    for o in orders:
        its = o.get("items") or []
        if not its:
            # pesanan lama tanpa items[] — tautan tingkat-order
            has = bool(o.get("fg_material_id"))
            (orders_fully if has else orders_none).__class__  # noop
            if has:
                orders_fully += 1
            else:
                orders_none += 1
            continue
        n_ok = 0
        for it in its:
            lines += 1
            q = float(it.get("quantity") or it.get("qty") or 0)
            total_pcs += q
            src = it.get("master_link_source") or "unlinked"
            link_sources[src] += 1
            if it.get("fg_material_id"):
                linked_lines += 1
                linked_pcs += q
                n_ok += 1
            else:
                psid = str(it.get("platform_sku_id") or "").strip() or "(kosong)"
                e = unmapped_psid[psid]
                e["pcs"] += q
                e["orders"] += 1
                e["name"] = e["name"] or (it.get("product_name_raw") or "")
                e["variation"] = e["variation"] or (it.get("variation_raw") or "")
        if n_ok == len(its):
            orders_fully += 1
        elif n_ok:
            orders_partial += 1
        else:
            orders_none += 1

    sub("A1 · Tautan baris pesanan → master FG gudang (fg_material_id)")
    print(f"  Baris pesanan           : {lines}")
    print(f"  Baris TERTAUT ke FG     : {linked_lines} ({pct(linked_lines, lines)}%)")
    print(f"  Pcs TERTAUT             : {linked_pcs:.0f} / {total_pcs:.0f} ({pct(linked_pcs, total_pcs)}%)")
    print(f"  Sumber tautan           : {dict(link_sources)}")
    if lines and linked_lines == 0:
        bad(f"NOL dari {lines} baris pesanan marketing tertaut ke master gudang. "
            f"Tim gudang MUSTAHIL mencocokkan barang dari id — persis keluhan pemilik.", "CRITICAL")
    elif pct(linked_lines, lines) < 90:
        bad(f"Hanya {pct(linked_lines, lines)}% baris pesanan tertaut ke master gudang "
            f"({lines - linked_lines} baris tanpa id barang).", "HIGH")
    else:
        ok(f"{pct(linked_lines, lines)}% baris pesanan tertaut.")

    sub("A2 · Pesanan siap-kirim di antrean gudang (fulfillment)")
    FSTAT = ["pending_fulfillment", "allocated", "picking", "packed_ready", "awaiting_scanout"]
    queue = [o for o in orders if o.get("fulfillment_status") in FSTAT]
    print(f"  Pesanan di antrean gudang : {len(queue)}")
    fs = Counter(o.get("fulfillment_status") or "(tidak diisi)" for o in orders)
    print(f"  Sebaran fulfillment_status: {dict(fs)}")
    ready_to_ship = [o for o in orders if str(o.get("status_raw") or "").lower().startswith("perlu dikirim")
                     or o.get("status") in ("paid", "packed", "to_ship")]
    print(f"  Pesanan berstatus perlu dikirim/paid : {len(ready_to_ship)}")
    if ready_to_ship and not queue:
        bad(f"{len(ready_to_ship)} pesanan perlu dikirim tetapi antrean gudang KOSONG "
            f"(fulfillment_status tidak pernah diisi) — gudang tidak melihat pekerjaannya.", "CRITICAL")

    sub("A3 · SKU platform yang tidak dikenal master (biang ketidaksinkronan)")
    tops = sorted(unmapped_psid.items(), key=lambda kv: -kv[1]["pcs"])
    print(f"  Jumlah SKU platform TANPA tautan master : {len(tops)}")
    for psid, e in tops[:8]:
        nm = (e["name"] or "")[:56]
        print(f"    · {psid:22s} {e['pcs']:5.0f} pcs · {e['orders']:3d} pesanan · {nm}")
    if tops:
        bad(f"{len(tops)} SKU platform dipesan pembeli tetapi tidak dikenal master "
            f"(marketing memakai platform_sku_id numerik, gudang memakai UUID/kode FG).", "CRITICAL")

    sub("A4 · Jembatan pemetaan yang tersedia (platform_sku_ids di item katalog)")
    items = list(db.marketing_catalog_items.find({}, {"_id": 0}))
    with_map = [i for i in items if i.get("platform_sku_ids")]
    n_map = sum(len(i.get("platform_sku_ids") or []) for i in items)
    print(f"  Item katalog                     : {len(items)}")
    print(f"  Item katalog punya platform_sku_ids: {len(with_map)}")
    print(f"  Total SKU platform terpeta        : {n_map}")
    if items and not with_map:
        bad("Tabel jembatan `marketing_catalog_items.platform_sku_ids` KOSONG — "
            "pemetaan SKU platform→master belum pernah terjadi.", "CRITICAL")

    # apakah pemetaan hanya bisa lewat sesi impor?
    sess = db.marketing_data_import_sessions.count_documents({})
    print(f"  Sesi impor tersimpan             : {sess}")
    if tops and sess == 0:
        bad("Satu-satunya pintu pemetaan SKU adalah `/import/sessions/{id}/sku-map` "
            "(butuh sesi impor). Sesi 0 ⇒ SKU tak-tertaut TIDAK BISA dipetakan sama sekali.",
            "CRITICAL")
    elif tops:
        warn("Pemetaan SKU hanya tersedia di dalam sesi impor (per-sesi). Tidak ada layar "
             "master pemetaan SKU yang berdiri sendiri ⇒ SKU dari sesi yang sudah dihapus "
             "mustahil dipetakan.")

    REPORT["A_marketing_to_warehouse"] = {
        "orders": n_ord, "lines": lines, "linked_lines": linked_lines,
        "linked_pct": pct(linked_lines, lines), "pcs_total": total_pcs,
        "pcs_linked": linked_pcs, "link_sources": dict(link_sources),
        "orders_fully_linked": orders_fully, "orders_partial": orders_partial,
        "orders_unlinked": orders_none, "unmapped_platform_skus": len(tops),
        "fulfillment_queue": len(queue), "ready_to_ship": len(ready_to_ship),
        "catalog_items": len(items), "catalog_items_with_map": len(with_map),
        "import_sessions": sess,
        "top_unmapped": [{"platform_sku_id": k, **v} for k, v in tops[:25]],
    }


# ══════════════════════════════════════════════════════════════════════════════
# B. KATALOG JUAL → MASTER FG
# ══════════════════════════════════════════════════════════════════════════════
def audit_b_catalog_to_fg():
    head("B. KATALOG MARKETING → MASTER FG GUDANG")

    items = list(db.marketing_catalog_items.find({}, {"_id": 0}))
    mats = {m["id"]: m for m in db.rahaza_materials.find({}, {"_id": 0})}
    fg_by_code = {}
    for m in mats.values():
        for k in (m.get("code"), m.get("sku")):
            if k:
                fg_by_code[str(k).upper()] = m

    no_link, dangling, resolvable_by_sku, linked = [], [], [], []
    for i in items:
        mid = i.get("fg_material_id") or i.get("material_id")
        if mid:
            if mid in mats:
                linked.append(i)
            else:
                dangling.append(i)
        else:
            vsku = (i.get("variant_sku") or i.get("sku") or "").strip().upper()
            if vsku and vsku in fg_by_code:
                resolvable_by_sku.append(i)
            else:
                no_link.append(i)

    sub("B1 · Tautan item katalog → FG")
    print(f"  Item katalog             : {len(items)}")
    print(f"  Tertaut & FG ADA         : {len(linked)}")
    print(f"  Tertaut tapi FG HILANG   : {len(dangling)}  (dangling reference)")
    print(f"  Belum tertaut, SKU cocok : {len(resolvable_by_sku)}  (bisa diperbaiki otomatis)")
    print(f"  Belum tertaut & SKU asing: {len(no_link)}")
    if dangling:
        bad(f"{len(dangling)} item katalog menunjuk fg_material_id yang TIDAK ADA di "
            f"rahaza_materials — stok yang ditampilkan ke marketing pasti salah.", "HIGH")
    if no_link:
        bad(f"{len(no_link)} item katalog tanpa tautan master FG ⇒ stoknya tidak bisa dihitung.", "HIGH")
    if resolvable_by_sku:
        warn(f"{len(resolvable_by_sku)} item katalog bisa ditautkan otomatis lewat SKU tetapi "
             f"fg_material_id-nya dibiarkan kosong.")
    if items and not dangling and not no_link and not resolvable_by_sku:
        ok("Semua item katalog tertaut ke master FG yang sah.")

    sub("B2 · Cache stok katalog vs stok hidup gudang")
    stock_rows = defaultdict(list)
    for s in db.rahaza_material_stock.find({}, {"_id": 0}):
        stock_rows[s.get("material_id")].append(s)

    def read_qty(s):
        for k in ("qty", "total_qty", "quantity", "on_hand", "onhand"):
            if s.get(k) is not None:
                try:
                    return float(s[k] or 0)
                except (TypeError, ValueError):
                    pass
        return 0.0

    def read_res(s):
        for k in ("reserved_qty", "reserved", "qty_reserved"):
            if s.get(k) is not None:
                try:
                    return float(s[k] or 0)
                except (TypeError, ValueError):
                    pass
        return 0.0

    drift = []
    for i in linked:
        mid = i.get("fg_material_id") or i.get("material_id")
        rows = stock_rows.get(mid, [])
        live = max(0.0, sum(read_qty(r) for r in rows) - sum(read_res(r) for r in rows))
        cache = float(i.get("stock_quantity") or 0)
        if abs(live - cache) > 0.001:
            drift.append({"item": i.get("name", "")[:44], "sku": i.get("sku", ""),
                          "cache": cache, "live": live})
    print(f"  Item dibandingkan        : {len(linked)}")
    print(f"  Cache stok MELENCENG     : {len(drift)}")
    for d in drift[:8]:
        print(f"    · {d['sku']:22s} cache={d['cache']:8.1f}  hidup={d['live']:8.1f}  {d['item']}")
    if drift:
        bad(f"{len(drift)} item katalog memamerkan stok yang berbeda dari gudang "
            f"(risiko overselling / kehilangan penjualan).", "HIGH")
    elif linked:
        ok("Cache stok katalog sama dengan stok hidup gudang.")

    sub("B3 · Item katalog tanpa baris stok sama sekali")
    nostock = [i for i in linked if not stock_rows.get(i.get("fg_material_id") or i.get("material_id"))]
    print(f"  Item tertaut tanpa baris stok : {len(nostock)}")
    if nostock:
        warn(f"{len(nostock)} item katalog tertaut FG tetapi FG itu belum punya baris stok "
             f"di gudang (dijual tanpa barang).")

    REPORT["B_catalog_to_fg"] = {
        "items": len(items), "linked": len(linked), "dangling": len(dangling),
        "resolvable_by_sku": len(resolvable_by_sku), "no_link": len(no_link),
        "stock_cache_drift": len(drift), "linked_without_stock_rows": len(nostock),
        "drift_sample": drift[:15],
    }


# ══════════════════════════════════════════════════════════════════════════════
# C. VARIAN MODEL INTERNAL → FG
# ══════════════════════════════════════════════════════════════════════════════
def audit_c_variants_to_fg():
    head("C. VARIAN MODEL INTERNAL → MASTER FG (Phase 3: variant_id → stok Toko/FG)")

    variants = list(db.rahaza_model_variants.find({}, {"_id": 0}))
    mats = list(db.rahaza_materials.find({}, {"_id": 0}))
    fg = [m for m in mats if (m.get("type") or "").lower() == "fg"]
    fg_by_code = {}
    for m in fg:
        for k in (m.get("code"), m.get("sku")):
            if k:
                fg_by_code[str(k).upper()] = m
    fg_by_variant = {m["variant_id"]: m for m in fg if m.get("variant_id")}

    with_fg_id, with_fg_sku, orphan = [], [], []
    for v in variants:
        if v.get("id") in fg_by_variant:
            with_fg_id.append(v)
        elif (v.get("sku") or "").strip().upper() in fg_by_code:
            with_fg_sku.append(v)
        else:
            orphan.append(v)

    sub("C1 · Varian → FG")
    print(f"  Varian model internal      : {len(variants)}")
    print(f"  Master FG (type=fg)        : {len(fg)}  / total material {len(mats)}")
    print(f"  Varian punya FG via variant_id : {len(with_fg_id)}")
    print(f"  Varian punya FG via SKU        : {len(with_fg_sku)}")
    print(f"  Varian TANPA master FG         : {len(orphan)} ({pct(len(orphan), len(variants))}%)")
    if orphan:
        bad(f"{len(orphan)} varian ({pct(len(orphan), len(variants))}%) belum punya master FG ⇒ "
            f"mustahil dijual/dikirim karena gudang tidak punya barangnya.", "HIGH")
    for v in orphan[:6]:
        print(f"    · {str(v.get('sku','')):24s} {str(v.get('color',''))[:12]:12s} {v.get('size','')}")

    sub("C2 · FG tanpa varian (arah sebaliknya)")
    fg_orphan = [m for m in fg if not m.get("variant_id")]
    print(f"  FG tanpa variant_id        : {len(fg_orphan)} / {len(fg)}")
    if fg_orphan:
        warn(f"{len(fg_orphan)} master FG tidak menunjuk varian mana pun — "
             f"jejak balik ke master produk hilang.")

    sub("C3 · Varian yang punya FG tetapi FG-nya tanpa stok")
    stock_ids = {s.get("material_id") for s in db.rahaza_material_stock.find({}, {"material_id": 1})}
    have = [v for v in variants if v.get("id") in fg_by_variant]
    nostock = [v for v in have if fg_by_variant[v["id"]]["id"] not in stock_ids]
    print(f"  Varian ber-FG tanpa baris stok : {len(nostock)} / {len(have)}")

    REPORT["C_variants_to_fg"] = {
        "variants": len(variants), "fg_materials": len(fg), "materials_total": len(mats),
        "with_fg_by_variant_id": len(with_fg_id), "with_fg_by_sku": len(with_fg_sku),
        "orphan_variants": len(orphan), "fg_without_variant": len(fg_orphan),
        "variants_with_fg_no_stock": len(nostock),
    }


# ══════════════════════════════════════════════════════════════════════════════
# D. STOCK OPNAME → MASTER DATA
# ══════════════════════════════════════════════════════════════════════════════
def audit_d_opname_vs_master():
    head("D. STOCK OPNAME → MASTER DATA")

    # temukan koleksi opname apa pun yang dipakai
    cand = [c for c in db.list_collection_names()
            if re.search(r"opname|stock_count|stock_take|cycle_count", c, re.I)]
    counts = {c: db[c].count_documents({}) for c in cand}
    print(f"  Koleksi opname terdeteksi : {counts or '(tidak ada)'}")

    mats = {m["id"] for m in db.rahaza_materials.find({}, {"id": 1})}
    locs = {l["id"] for l in db.rahaza_locations.find({}, {"id": 1})}
    stock_keys = set()
    stock_by_mat = defaultdict(float)

    def read_qty(s):
        for k in ("qty", "total_qty", "quantity", "on_hand", "onhand"):
            if s.get(k) is not None:
                try:
                    return float(s[k] or 0)
                except (TypeError, ValueError):
                    pass
        return 0.0

    for s in db.rahaza_material_stock.find({}, {"_id": 0}):
        stock_keys.add((s.get("material_id"), s.get("location_id")))
        stock_by_mat[s.get("material_id")] += read_qty(s)

    total_items = 0
    bad_mat = 0
    bad_loc = 0
    sessions = 0
    samples = []
    for c, n in counts.items():
        if not n:
            continue
        for d in db[c].find({}, {"_id": 0}):
            sessions += 1
            lines = d.get("items") or d.get("lines") or d.get("counts") or []
            if isinstance(lines, list) and lines:
                for ln in lines:
                    if not isinstance(ln, dict):
                        continue
                    total_items += 1
                    mid = ln.get("material_id") or ln.get("item_id")
                    lid = ln.get("location_id") or ln.get("bin_id") or ln.get("position_id")
                    if mid and mid not in mats:
                        bad_mat += 1
                        if len(samples) < 8:
                            samples.append({"coll": c, "material_id": mid, "reason": "material tidak ada di master"})
                    if lid and lid not in locs and len(samples) < 8:
                        bad_loc += 1
            else:
                mid = d.get("material_id")
                if mid:
                    total_items += 1
                    if mid not in mats:
                        bad_mat += 1

    sub("D1 · Rujukan opname ke master")
    print(f"  Dokumen/sesi opname   : {sessions}")
    print(f"  Baris hitung          : {total_items}")
    print(f"  material_id tak dikenal: {bad_mat}")
    print(f"  location_id tak dikenal: {bad_loc}")
    if bad_mat:
        bad(f"{bad_mat} baris opname memakai material_id yang tidak ada di master.", "HIGH")
    if sessions == 0:
        warn("Belum ada satu pun sesi stock opname — sinkronisasi opname↔master belum "
             "bisa dibuktikan dengan data nyata (perlu 1 sesi uji).")
    else:
        ok("Rujukan opname ke master terperiksa.")

    sub("D2 · Skema stok ganda (sumber salah-hitung klasik)")
    schema = Counter()
    for s in db.rahaza_material_stock.find({}, {"_id": 0}):
        keys = tuple(sorted(k for k in ("qty", "total_qty", "quantity") if s.get(k) is not None))
        schema[keys or ("(tidak ada field qty)",)] += 1
    print(f"  Sebaran field kuantitas: { {'+'.join(k): v for k, v in schema.items()} }")
    if len(schema) > 1:
        warn(f"Koleksi stok memakai {len(schema)} skema kuantitas berbeda — pembacaan mentah "
             f"(bukan lewat core.stock_schema) akan salah hitung.")

    sub("D3 · Baris stok menunjuk master/lokasi yang hilang")
    dang_m = [s for s in db.rahaza_material_stock.find({}, {"_id": 0})
              if s.get("material_id") and s["material_id"] not in mats]
    dang_l = [s for s in db.rahaza_material_stock.find({}, {"_id": 0})
              if s.get("location_id") and s["location_id"] not in locs]
    print(f"  Baris stok material hilang : {len(dang_m)}")
    print(f"  Baris stok lokasi hilang   : {len(dang_l)}")
    if dang_m:
        bad(f"{len(dang_m)} baris stok menunjuk material yang tidak ada di master.", "HIGH")
    if dang_l:
        bad(f"{len(dang_l)} baris stok menunjuk lokasi yang tidak ada di master lokasi.", "HIGH")

    REPORT["D_opname_vs_master"] = {
        "opname_collections": counts, "sessions": sessions, "lines": total_items,
        "unknown_material_id": bad_mat, "unknown_location_id": bad_loc,
        "stock_qty_schemas": len(schema),
        "stock_dangling_material": len(dang_m), "stock_dangling_location": len(dang_l),
        "samples": samples,
    }


# ══════════════════════════════════════════════════════════════════════════════
# E. INTEGRITAS RUJUKAN LINTAS KOLEKSI
# ══════════════════════════════════════════════════════════════════════════════
FK_RULES = [
    # (koleksi, field, koleksi_tujuan, field_tujuan, catatan)
    ("marketing_catalog_items", "catalog_id", "marketing_catalogs", "id", "item → katalog"),
    ("marketing_catalog_items", "account_id", "marketing_platform_accounts", "id", "item → toko"),
    ("marketing_catalog_items", "fg_material_id", "rahaza_materials", "id", "item → FG"),
    ("marketing_catalog_items", "variant_id", "rahaza_model_variants", "id", "item → varian"),
    ("marketing_catalog_items", "model_id", "rahaza_models", "id", "item → model"),
    ("marketing_orders", "account_id", "marketing_platform_accounts", "id", "pesanan → toko"),
    ("rahaza_material_stock", "material_id", "rahaza_materials", "id", "stok → material"),
    ("rahaza_material_stock", "location_id", "rahaza_locations", "id", "stok → lokasi"),
    ("rahaza_model_variants", "model_id", "rahaza_models", "id", "varian → model"),
    ("rahaza_materials", "variant_id", "rahaza_model_variants", "id", "FG → varian"),
    ("rahaza_materials", "model_id", "rahaza_models", "id", "FG → model"),
    ("rahaza_stock_ledger", "material_id", "rahaza_materials", "id", "kartu stok → material"),
    ("rahaza_material_movements", "material_id", "rahaza_materials", "id", "mutasi → material"),
    ("rahaza_material_issues", "material_id", "rahaza_materials", "id", "pengeluaran → material"),
    ("po_items", "material_id", "rahaza_materials", "id", "baris PO → material"),
    ("production_job_items", "material_id", "rahaza_materials", "id", "job → material"),
    ("marketing_sales_data", "account_id", "marketing_platform_accounts", "id", "penjualan → toko"),
    ("marketing_budgets", "account_id", "marketing_platform_accounts", "id", "anggaran → toko"),
    ("marketing_account_targets", "account_id", "marketing_platform_accounts", "id", "target → toko"),
    ("wh_delivery_notes", "account_id", "marketing_platform_accounts", "id", "surat jalan → toko"),
]


def audit_e_referential_integrity():
    head("E. INTEGRITAS RUJUKAN LINTAS KOLEKSI (dangling foreign key)")
    cache = {}
    rows = []
    for coll, field, target, tfield, note in FK_RULES:
        if coll not in db.list_collection_names():
            continue
        n = db[coll].count_documents({})
        if not n:
            continue
        if target not in cache:
            cache[target] = {d[tfield] for d in db[target].find({}, {tfield: 1}) if d.get(tfield)}
        ids = cache[target]
        filled = 0
        dang = 0
        for d in db[coll].find({}, {field: 1, "_id": 0}):
            v = d.get(field)
            if not v or not isinstance(v, str):
                continue
            filled += 1
            if v not in ids:
                dang += 1
        rows.append({"coll": coll, "field": field, "target": target, "docs": n,
                     "filled": filled, "dangling": dang, "note": note})

    print(f"  {'KOLEKSI.FIELD':52s} {'DOK':>5s} {'ISI':>5s} {'RUSAK':>6s}")
    for r in sorted(rows, key=lambda x: -x["dangling"]):
        key = f"{r['coll']}.{r['field']}"
        mark = f"{C_RED}" if r["dangling"] else f"{C_GRN}"
        print(f"  {mark}{key:52s}{C_RST} {r['docs']:5d} {r['filled']:5d} {r['dangling']:6d}")
    broken = [r for r in rows if r["dangling"]]
    if broken:
        for r in broken:
            bad(f"{r['coll']}.{r['field']} → {r['target']}: {r['dangling']} rujukan rusak ({r['note']}).",
                "HIGH")
    else:
        ok("Tidak ada rujukan rusak pada aturan yang diperiksa.")

    # field tautan yang KOSONG padahal wajib
    sub("E2 · Field tautan yang dibiarkan kosong (bukan rusak, tetapi tidak pernah diisi)")
    empties = [r for r in rows if r["docs"] and r["filled"] == 0]
    for r in empties:
        warn(f"{r['coll']}.{r['field']} kosong di SELURUH {r['docs']} dokumen ({r['note']}).")
    if not empties:
        ok("Semua field tautan terisi di setidaknya sebagian dokumen.")

    REPORT["E_referential_integrity"] = {"rules": rows, "broken": len(broken), "empty_links": len(empties)}


def main():
    head("FORENSIK SINKRONISASI DATA — CV. DEWI ADITYA ERP")
    print(f"  DB: {os.environ.get('DB_NAME')}  ·  koleksi: {len(db.list_collection_names())}")
    audit_a_marketing_to_warehouse()
    audit_b_catalog_to_fg()
    audit_c_variants_to_fg()
    audit_d_opname_vs_master()
    audit_e_referential_integrity()

    head("RINGKASAN TEMUAN")
    sev = Counter(f["severity"] for f in FINDINGS)
    print(f"  CRITICAL={sev.get('CRITICAL',0)}  HIGH={sev.get('HIGH',0)}  MED={sev.get('MED',0)}")
    for f in FINDINGS:
        c = C_RED if f["severity"] in ("CRITICAL", "HIGH") else C_YEL
        print(f"  {c}[{f['severity']:8s}]{C_RST} {f['text']}")

    os.makedirs("/app/.logs", exist_ok=True)
    with open("/app/.logs/sync_forensic.json", "w") as fh:
        json.dump({"report": REPORT, "findings": FINDINGS}, fh, indent=2, default=str)
    print(f"\n  → /app/.logs/sync_forensic.json")
    return 1 if sev.get("CRITICAL") or sev.get("HIGH") else 0


if __name__ == "__main__":
    sys.exit(main())
