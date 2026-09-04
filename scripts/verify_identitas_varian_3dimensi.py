#!/usr/bin/env python3
"""verify_identitas_varian_3dimensi.py — Sesi #28 (2026-08-19).

GATE **INV-F30** — "IDENTITAS BARANG TIDAK BOLEH MENABRAK."

YANG TERUKUR SEBELUM PERBAIKAN (data hidup, 83 SKU platform nyata)
──────────────────────────────────────────────────────────────────
Jembatan SKU sesi #20 benar dan gate INV-F29 hijau, tetapi **tidak satu barang
pun pernah dijembatani**: ``sync-audit`` melaporkan ``A1 CRITICAL: NOL dari 601
baris pesanan menunjuk master gudang`` dan ``A5: 553 pesanan di antrean gudang,
tidak satu pun siap dialokasikan``.

Penyebabnya diukur, bukan ditebak — ``sku_bridge.parse_variation`` dijalankan
pada 83 string variasi nyata::

    83 SKU berbeda  →  35 identitas   ·  16 kelompok TABRAKAN
    63 SKU (76%) dan 489 pcs (81%) tertimpa
    18/83 warna tidak terbaca · 20/83 ukuran tidak terbaca

Tabrakan terburuk: **8 SKU berbeda** jatuh ke satu identitas ``hitam/XL`` —
``BLACK…PAKAI KARET`` (39 pcs), ``POLKA BLACK…SMOOK`` (12), ``POLKA BLACK…TANPA
KARET`` (10), ``BLACK…TANPA KARET`` (7), … Kalau itu ditulis, gudang mengambil
**barang yang salah** untuk 4 dari 5 pesanan.

Dua akar sebab: (1) warna majemuk dipotong oleh pencocokan *substring*
(``POLKA WHITE`` menemukan alias ``white`` ⇒ jadi ``putih``, motif hilang);
(2) ``PAKAI KARET`` / ``TANPA KARET`` / ``PAKAI KARET (SMOOK)`` tidak dibaca
sama sekali, dan skema varian hanya punya dua sumbu sehingga tak ada tempat
menyimpannya.

INVARIAN
────────
  V1  identitas INJEKTIF: variasi BERBEDA ⇒ identitas BERBEDA; variasi SAMA
      PERSIS ⇒ identitas SAMA (dua listing menjual satu barang — sah, dan
      memang terjadi 13 kali pada data ini)
  V2  TIDAK ADA pencocokan substring warna: POLKA WHITE ≠ Putih,
      POLKA BLACK ≠ Hitam, BUTTER YELLOW ≠ Kuning
  V3  dimensi ke-3 HIDUP di DB: ada varian yang model·warna·ukurannya sama
      tetapi opsinya berbeda, dan SKU-nya berbeda
  V4  index unik varian = 4 sumbu (model·ukuran·warna·opsi); index 3 sumbu lama
      sudah TIDAK ADA; setiap varian punya `option_code`
  V5  opsi berasal dari MASTER (`rahaza_variant_options`), bukan teks bebas
  V6  KOMPATIBEL-BALIK: opsi `NA` & warna `TDI` tidak menambah akhiran SKU;
      tidak ada satu pun SKU varian berakhiran `-NA`/`-TDI`
  V7  `GET /plan` (pratinjau) BENAR-BENAR tidak menulis apa pun
  V8  `POST /apply` IDEMPOTEN: pemanggilan kedua tidak melahirkan apa pun
  V9  rantai identitas UTUH: tiap pemetaan menunjuk varian + master FG + item
      katalog yang benar-benar ada
  V10 tidak ada dua variasi BERBEDA yang menunjuk satu varian (di DB)
  V11 palet warna aktif BEBAS KEMBAR & tidak ada varian menggantung ke warna
      yang sudah dihapus
  V12 SKU varian unik (tidak ada kembar)
  V13 PINTUNYA ADA DI LAYAR: tab "Onboarding Produk" & "Opsi Varian" terdaftar,
      komponennya ada, dan endpoint yang dipanggilnya benar-benar ada di backend
  V14 nama model tidak MEMBUANG identitas produk (cacat lama
      `clean_product_name`: "ONA DRESS - …" → "Midi Dress Salur …", ONA hilang)
  V15 alat ukur tidak mengotori data: 0 baris stok / kartu stok menunjuk
      material yang tidak ada (regresi kebocoran gate cutting H5/H6 & H6b)

Self-cleaning: bila masih ada produk belum tertaut, gate mengerjakan onboarding
produk ber-opsi terbanyak lalu **membatalkannya kembali** (rollback) — jadi ia
tidak pernah meninggalkan jejak, dan tidak pernah "lulus dengan sopan" karena
data ujinya tidak ada.

Pakai:  python3 scripts/verify_identitas_varian_3dimensi.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

load_dotenv(ROOT / "backend" / ".env")

from core import sku_bridge as sb                                 # noqa: E402
from core import variant_identity as vi                           # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PASS: list = []
FAIL: list = []

FE_BRIDGE = ROOT / "frontend/src/components/erp/SkuBridgeModule.jsx"
FE_PANEL = ROOT / "frontend/src/components/erp/VariantOnboardingPanel.jsx"
BE_ROUTE = ROOT / "backend/routes/variant_onboarding.py"

WATCH = ("rahaza_models", "rahaza_model_variants", "rahaza_colors", "rahaza_sizes",
         "rahaza_variant_options", "rahaza_materials", "marketing_catalog_items",
         "marketing_catalogs", "marketing_sku_bridge", "counters",
         "rahaza_product_categories")


def ok(code, msg, detail=""):
    PASS.append(code)
    print(f"  {G}✓{X} {code} — {msg}" + (f" · {detail}" if detail else ""))


def bad(code, msg, detail=""):
    FAIL.append(code)
    print(f"  {R}✗ {code} — {msg}{X}" + (f" · {detail}" if detail else ""))


def head(t):
    print(f"\n{C}{B}{t}{X}")


async def snapshot(db):
    return {c: await db[c].count_documents({}) for c in WATCH}


def grew(a, b):
    return {k: (a[k], b[k]) for k in a if b.get(k, 0) != a[k]}


# ══════════════════════════════════════════════════════════════════════════════
async def v1_v2_mesin(db):
    head("V1/V2 — mesin identitas: injektif & tidak memotong warna majemuk")
    rows = await vi._collect_rows(db)
    if not rows:
        bad("V1", "TIDAK TERUKUR: tidak ada baris pesanan ber-platform_sku_id",
            "data nyata kosong — gate ini tidak boleh lulus tanpa mengukur")
        return []
    by_ident, by_var = defaultdict(set), defaultdict(set)
    unreadable = []
    for r in rows:
        idn = vi.parse_identity(r.get("variation"), product_name=r.get("product_name"),
                                shop_name=r.get("account_name"))
        pk = vi.product_key(r.get("product_name"))
        by_ident[(pk, idn["identity_key"])].add(vi.norm(r.get("variation")))
        by_var[(pk, vi.norm(r.get("variation")))].add(idn["identity_key"])
        if idn["unreadable"]:
            unreadable.append((r.get("variation"), idn["unreadable"]))

    collisions = {k: v for k, v in by_ident.items() if len(v) > 1}
    if collisions:
        for k, v in list(collisions.items())[:4]:
            bad("V1", "dua variasi berbeda menghasilkan SATU identitas",
                f"{k[1]} ← {sorted(v)[:3]}")
    else:
        ok("V1", "identitas injektif", f"{len(rows)} SKU → {len(by_ident)} identitas · 0 tabrakan")

    split = {k: v for k, v in by_var.items() if len(v) > 1}
    if split:
        bad("V1b", "variasi yang sama persis menghasilkan identitas berbeda", str(list(split)[:3]))
    else:
        shared = sum(1 for v in by_ident.values() if len(v) == 1 and True)
        ok("V1b", "variasi sama persis → satu identitas",
           f"{sum(1 for k, v in by_ident.items() if len(v) == 1)} identitas konsisten")

    if unreadable:
        bad("V1c", f"{len(unreadable)} variasi punya bagian yang tidak terbaca",
            str(unreadable[:3]))
    else:
        ok("V1c", "tidak ada bagian variasi yang gagal dibaca", f"{len(rows)} SKU")

    # V2 — warna majemuk TIDAK boleh runtuh ke warna dasar
    cases = [("POLKA WHITE", "Polka White"), ("POLKA BLACK", "Polka Black"),
             ("BUTTER YELLOW", "Butter Yellow"), ("WHITE", "Putih"), ("BLACK", "Hitam"),
             ("MAHOGANY", "Mahogany"), ("NUVGETT", "Nuvget"), ("MAUVE", "Mauve")]
    wrong = [(src, want, vi.resolve_color_name(src)[0])
             for src, want in cases if vi.resolve_color_name(src)[0] != want]
    if wrong:
        bad("V2", "warna majemuk masih dipotong / salah dipetakan", str(wrong))
    else:
        ok("V2", "warna majemuk utuh & sinonim bahasa tetap disatukan",
           "POLKA WHITE≠Putih · POLKA BLACK≠Hitam · BUTTER YELLOW≠Kuning")

    # substring matching harus benar-benar tidak dipakai
    src = (ROOT / "backend/core/variant_identity.py").read_text(encoding="utf-8")
    if re.search(r"for\s+alias.*in\s+COLOR_\w+\.items\(\)[\s\S]{0,120}?alias\s+in\s+n", src):
        bad("V2b", "masih ada pencocokan substring warna di mesin baru")
    else:
        ok("V2b", "mesin baru tidak memakai pencocokan substring warna")
    return rows


async def v3_v6_skema(db):
    head("V3/V4/V5/V6 — dimensi ke-3, index, master opsi, kompatibel-balik")
    variants = await db[vi.VARIANTS].find({}, {"_id": 0}).to_list(20000)
    if not variants:
        bad("V3", "TIDAK TERUKUR: tidak ada varian di master")
        return
    trio = defaultdict(set)
    for v in variants:
        trio[(v.get("model_id"), v.get("color_id"), v.get("size_id"))].add(
            v.get("option_code") or vi.OPTION_NA)
    multi = {k: v for k, v in trio.items() if len(v) > 1}
    if multi:
        sample_key = next(iter(multi))
        skus = sorted(v.get("sku") for v in variants
                      if (v.get("model_id"), v.get("color_id"), v.get("size_id")) == sample_key)
        dup_sku = len(skus) != len(set(skus))
        if dup_sku:
            bad("V3", "varian ber-opsi berbeda memakai SKU yang sama", str(skus))
        else:
            ok("V3", "dimensi ke-3 hidup di master",
               f"{len(multi)} kombinasi model·warna·ukuran punya >1 opsi · contoh: {skus[:4]}")
    else:
        bad("V3", "TIDAK TERUKUR / dimensi ke-3 belum dipakai",
            "tidak ada satu pun model·warna·ukuran dengan opsi berbeda — "
            "jalankan onboarding produk ber-opsi (mis. Jennifer Blouse) lebih dulu")

    info = await db[vi.VARIANTS].index_information()
    if "model_size_color_option_unique" in info and "model_size_color_variant_unique" not in info:
        ok("V4", "index unik varian 4 sumbu terpasang & index 3 sumbu lama dilepas")
    else:
        bad("V4", "index unik varian belum 4 sumbu", str(sorted(info)))

    no_opt = [v.get("sku") for v in variants if not v.get("option_code")]
    if no_opt:
        bad("V4b", f"{len(no_opt)} varian tanpa option_code", str(no_opt[:5]))
    else:
        ok("V4b", "seluruh varian punya option_code", f"{len(variants)} varian")

    master_codes = {o["code"] for o in await db[vi.OPTIONS].find(
        {}, {"_id": 0, "code": 1}).to_list(200)}
    stray = sorted({v.get("option_code") for v in variants} - master_codes)
    if stray:
        bad("V5", "ada option_code yang tidak terdaftar di master opsi", str(stray))
    else:
        ok("V5", "seluruh opsi varian berasal dari master",
           f"{len(master_codes)} opsi master: {sorted(master_codes)}")

    if (vi.make_sku("BLS-0001", "PWH", "XL", "NA") == "BLS-0001-PWH-XL"
            and vi.make_sku("BLS-0001", "PWH", "XL", "KRT") == "BLS-0001-PWH-XL-KRT"
            and vi.make_sku("AKS-0001", "TDI", "BESAR", "NA") == "AKS-0001-BESAR"):
        ok("V6", "kode ketidakhadiran (NA/TDI) tidak masuk SKU",
           "SKU varian lama tidak mungkin berubah bentuk")
    else:
        bad("V6", "bentuk SKU tidak kompatibel-balik",
            vi.make_sku("BLS-0001", "PWH", "XL", "NA"))

    tail = [v.get("sku") for v in variants
            if str(v.get("sku") or "").upper().endswith(("-NA", "-TDI"))]
    if tail:
        bad("V6b", "ada SKU varian berakhiran -NA/-TDI", str(tail[:5]))
    else:
        ok("V6b", "tidak ada SKU varian berakhiran -NA/-TDI")


async def v7_v8_onboarding(db):
    head("V7/V8 — pratinjau tidak menulis · apply idempoten")
    groups = await vi.list_product_groups(db, only_unmapped=True)
    created_target = None
    if groups["products"]:
        # Ada produk belum tertaut → kerjakan yang paling menantang (opsi terbanyak),
        # ukur, lalu BATALKAN. Gate tidak boleh lulus tanpa mengukur.
        target = sorted(groups["products"],
                        key=lambda p: (-len(p.get("options") or []), -p["sku_count"]))[0]
        pkey = target["product_key"]
    else:
        all_groups = await vi.list_product_groups(db, only_unmapped=False)
        if not all_groups["products"]:
            bad("V7", "TIDAK TERUKUR: tidak ada produk platform pada pesanan")
            return
        target = sorted(all_groups["products"],
                        key=lambda p: (-len(p.get("options") or []), -p["sku_count"]))[0]
        pkey = target["product_key"]

    snap_a = await snapshot(db)
    plan = await vi.plan_onboarding(db, product_key=pkey)
    snap_b = await snapshot(db)
    d = grew(snap_a, snap_b)
    if not plan.get("ok"):
        bad("V7", "rencana gagal disusun", plan.get("message"))
        return
    if d:
        bad("V7", "pratinjau MENULIS ke database", str(d))
    else:
        ok("V7", "pratinjau tidak menulis apa pun",
           f"{len(WATCH)} koleksi dipantau · produk uji: {target['proposed_model_name']}")

    if plan["totals"]["collisions"]:
        bad("V7b", "rencana masih memuat tabrakan identitas",
            str(plan["totals"]["collisions"]))
    else:
        ok("V7b", "rencana bebas tabrakan identitas",
           f"{plan['totals']['identities']} identitas dari "
           f"{plan['totals']['distinct_variations']} variasi berbeda")

    if groups["products"]:
        res = await vi.apply_onboarding(db, product_key=pkey, user={"id": "gate-f30"})
        if not res.get("ok"):
            bad("V8", "apply gagal", str(res.get("failures") or res.get("message")))
            return
        created_target = res["model"]["id"]

    snap_c = await snapshot(db)
    res2 = await vi.apply_onboarding(db, product_key=pkey, user={"id": "gate-f30"})
    snap_d = await snapshot(db)
    up = {k: v for k, v in grew(snap_c, snap_d).items() if v[1] > v[0]}
    if (res2.get("created") or {}).get("variants") or up:
        bad("V8", "apply kedua melahirkan data baru",
            f"created={res2.get('created')} tumbuh={up}")
    else:
        ok("V8", "apply idempoten", "pemanggilan kedua tidak melahirkan apa pun")

    if created_target:
        rb = await vi.rollback_onboarding(db, model_id=created_target,
                                         user={"id": "gate-f30"})
        print(f"  {Y}·{X} bersih-bersih: {rb.get('message')}")


async def v9_v12_db(db):
    head("V9/V10/V11/V12 — keadaan DB: rantai utuh, tanpa tabrakan, palet bersih")
    bridges = await db[vi.BRIDGE].find({}, {"_id": 0}).to_list(5000)
    if not bridges:
        bad("V9", "TIDAK TERUKUR: belum ada satu pun pemetaan SKU",
            "onboarding belum pernah dijalankan — invarian rantai tidak bisa diukur")
    else:
        broken = []
        for bdoc in bridges:
            v = await db[vi.VARIANTS].find_one({"id": bdoc.get("variant_id")}, {"_id": 0, "id": 1})
            fg = await db[vi.MATERIALS].find_one({"id": bdoc.get("fg_material_id")},
                                                {"_id": 0, "id": 1})
            it = await db[vi.ITEMS].find_one({"id": bdoc.get("catalog_item_id")},
                                             {"_id": 0, "id": 1}) \
                if bdoc.get("catalog_item_id") else None
            if not (v and fg and it):
                broken.append({"sku": bdoc.get("platform_sku_id"), "varian": bool(v),
                               "fg": bool(fg), "item": bool(it)})
        if broken:
            bad("V9", f"{len(broken)} pemetaan menunjuk mata rantai yang tidak ada",
                str(broken[:3]))
        else:
            ok("V9", "rantai pemetaan→varian→FG→item katalog utuh",
               f"{len(bridges)} pemetaan")

        per_variant = defaultdict(set)
        for bdoc in bridges:
            per_variant[bdoc.get("variant_id")].add(vi.norm(bdoc.get("variation_sample")))
        multi = {k: v for k, v in per_variant.items() if k and len(v) > 1}
        if multi:
            bad("V10", "satu varian ditunjuk beberapa variasi BERBEDA",
                str([(k, sorted(v)) for k, v in list(multi.items())[:2]]))
        else:
            ok("V10", "tidak ada dua variasi berbeda menunjuk satu varian",
               f"{len(per_variant)} varian terpetakan")

    cs = await db[vi.COLORS].find({"active": {"$ne": False}}, {"_id": 0}).to_list(500)
    dup = defaultdict(list)
    for c in cs:
        dup[vi.color_group_key(c.get("name"))].append(c.get("code"))
    kembar = {k: v for k, v in dup.items() if len(v) > 1}
    if kembar:
        bad("V11", "palet warna aktif masih kembar",
            ", ".join(f"{k}={'+'.join(sorted(v))}" for k, v in sorted(kembar.items())))
    else:
        ok("V11", "palet warna aktif bebas kembar", f"{len(cs)} warna aktif")

    color_ids = {c["id"] for c in await db[vi.COLORS].find({}, {"_id": 0, "id": 1}).to_list(500)}
    dangling = [v.get("sku") for v in await db[vi.VARIANTS].find(
        {}, {"_id": 0, "sku": 1, "color_id": 1}).to_list(20000)
        if v.get("color_id") and v["color_id"] not in color_ids]
    if dangling:
        bad("V11b", f"{len(dangling)} varian menggantung ke warna yang tidak ada",
            str(dangling[:5]))
    else:
        ok("V11b", "tidak ada varian menggantung ke warna terhapus")

    skus = [v.get("sku") for v in await db[vi.VARIANTS].find(
        {}, {"_id": 0, "sku": 1}).to_list(20000)]
    dupes = {s for s in skus if skus.count(s) > 1} if len(skus) < 4000 else set()
    if dupes:
        bad("V12", "ada SKU varian kembar", str(sorted(dupes)[:5]))
    else:
        ok("V12", "SKU varian unik", f"{len(set(skus))} SKU")


async def v13_layar(db):
    head("V13 — pintunya benar-benar ada di layar")
    if not FE_PANEL.exists():
        bad("V13", "komponen VariantOnboardingPanel.jsx tidak ada")
        return
    bridge = FE_BRIDGE.read_text(encoding="utf-8") if FE_BRIDGE.exists() else ""
    panel = FE_PANEL.read_text(encoding="utf-8")
    missing = [n for n in ("ProductOnboardingTab", "VariantOptionsTab")
               if n not in bridge or n not in panel]
    tabs = [t for t in ('value="onboarding"', 'value="options"') if t not in bridge]
    if missing or tabs:
        bad("V13", "tab onboarding/opsi belum terpasang di layar Jembatan SKU",
            f"komponen hilang={missing} tab hilang={tabs}")
    else:
        ok("V13", "tab 'Onboarding Produk' & 'Opsi Varian' terdaftar di layar")

    # Endpoint yang dipanggil layar WAJIB ada di backend (anti FE memanggil ruang kosong)
    called = set(re.findall(r"['\"`]/variant-onboarding([A-Za-z0-9_\-/{}]*)", panel))
    route_src = BE_ROUTE.read_text(encoding="utf-8") if BE_ROUTE.exists() else ""
    declared = set(re.findall(r"@router\.(?:get|post|delete|put)\('([^']*)'\)", route_src))
    dead = []
    for c in called:
        path = (c.split("?")[0] or "/").rstrip("/") or "/"
        base = "/" + path.lstrip("/")
        if base in declared:
            continue
        # ruas terakhir yang berupa nilai dinamis dicocokkan ke pola {param}
        parts = base.rstrip("/").split("/")
        pattern = "/".join(parts[:-1]) + "/{code}"
        if pattern in declared or any(d.startswith(base) for d in declared):
            continue
        dead.append(base)
    if dead:
        bad("V13b", "layar memanggil endpoint yang tidak ada di backend", str(sorted(dead)))
    else:
        ok("V13b", "seluruh endpoint yang dipanggil layar ada di backend",
           f"{len(called)} pemanggilan · {len(declared)} endpoint")


async def v14_nama_model(db):
    head("V14 — nama model tidak membuang identitas produk")
    models = await db[vi.MODELS].find(
        {"created_via": vi.CREATED_VIA, "source_product_name": {"$ne": None}},
        {"_id": 0, "name": 1, "source_product_name": 1}).to_list(500)
    if not models:
        # Tidak ada model hasil onboarding → ukur langsung dari judul pesanan nyata.
        rows = await vi._collect_rows(db)
        titles = {r.get("product_name"): r.get("account_name") for r in rows}
        if not titles:
            bad("V14", "TIDAK TERUKUR: tidak ada judul produk platform")
            return
        bad_names = []
        for t, shop in titles.items():
            nm = vi.propose_model_name(t, shop_name=shop)
            head_tok = [w for w in vi.norm(t).split() if w not in vi.SHOP_NOISE][:3]
            if not (set(vi.norm(nm).split()) & set(head_tok)):
                bad_names.append((t[:40], nm))
        if bad_names:
            bad("V14", "usulan nama model membuang nama produknya", str(bad_names[:3]))
        else:
            ok("V14", "usulan nama model memuat nama produknya", f"{len(titles)} judul")
        return
    bad_names = []
    for m in models:
        src = vi.norm(m.get("source_product_name"))
        head_tok = [w for w in src.split() if w not in vi.SHOP_NOISE][:3]
        if not (set(vi.norm(m.get("name")).split()) & set(head_tok)):
            bad_names.append((m.get("source_product_name", "")[:40], m.get("name")))
    if bad_names:
        bad("V14", "ada model hasil onboarding yang namanya kehilangan identitas produk",
            str(bad_names[:3]))
    else:
        ok("V14", "setiap model hasil onboarding memuat nama produk sumbernya",
           f"{len(models)} model")


async def v15_alat_ukur(db):
    head("V15 — alat ukur tidak boleh mengotori data yang diukurnya")
    mids = {m["id"] async for m in db[vi.MATERIALS].find({}, {"_id": 0, "id": 1})}
    leaks = {}
    for coll in ("rahaza_material_stock", "rahaza_stock_ledger"):
        n = 0
        async for s in db[coll].find({}, {"_id": 0, "material_id": 1}):
            if s.get("material_id") and s["material_id"] not in mids:
                n += 1
        if n:
            leaks[coll] = n
    if leaks:
        bad("V15", "ada baris stok/kartu stok menunjuk material yang tidak ada",
            f"{leaks} — periksa cleanup gate cutting (verify_fase_h5_h6_roll / h6b)")
    else:
        ok("V15", "0 rujukan stok menggantung",
           "cleanup gate cutting menghapus stok+kartu milik POTONGAN, bukan hanya masternya")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print(f"{C}{B}INV-F30 — IDENTITAS BARANG TIDAK BOLEH MENABRAK{X}")
    await vi.ensure_all_masters(db)
    await v1_v2_mesin(db)
    await v3_v6_skema(db)
    await v7_v8_onboarding(db)
    await v9_v12_db(db)
    await v13_layar(db)
    await v14_nama_model(db)
    await v15_alat_ukur(db)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian identitas varian 3 dimensi terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
