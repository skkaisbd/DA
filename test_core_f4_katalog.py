#!/usr/bin/env python3
"""test_core_f4_katalog.py — CORE TEST **FASE F4** (Katalog: status akurat · foto ·
kolom penuh).

Menguji **persis** daftar "BUKTI SELESAI F4" di
`memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`:

  1. enam hasil status turunan benar (DRAFT · PRE_ORDER · ACTIVE · HABIS · DITOLAK · NONAKTIF)
  2. `publish` tanpa `platform_url` ⇒ 400 (bukti tayang tidak boleh dikarang)
  3. item dari FG yang model-nya punya foto R&D ⇒ `master_images` ≥ 1 TANPA unggah manual;
     unggah foto marketplace ⇒ `images` bertambah & `primary_image` berpindah
  4. setiap baris daftar membawa `primary_image, catalog_status, hpp, hpp_source,
     margin_pct, available, in_sync`
  6. `stock_summary.by_status` menjumlah = total item katalog (bukan hanya halaman aktif)

Semua lewat HTTP sungguhan + verifikasi DB. Data uji dibuat dan **dibersihkan** di akhir.

Pakai:  python3 /app/test_core_f4_katalog.py
"""
from __future__ import annotations

import io
import os
import struct
import sys
import zlib

import requests
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001"
G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
RES: list[tuple[str, bool, str]] = []


def ok(n, d=""):
    RES.append((n, True, d)); print(f"  {G}PASS{X}  {n}" + (f" — {d}" if d else ""))


def bad(n, d=""):
    RES.append((n, False, d)); print(f"  {R}FAIL{X}  {n}" + (f" — {d}" if d else ""))


def check(n, cond, d=""):
    (ok if cond else bad)(n, d); return bool(cond)


def png_bytes(w=8, h=8) -> bytes:
    """PNG 8×8 sah (tanpa Pillow) — endpoint foto menolak berkas <50 byte."""
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def mongo():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli, cli[os.environ.get("DB_NAME", "test_database")]


def main() -> int:  # noqa: C901
    tok = requests.post(f"{BASE}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    JH = {**H, "Content-Type": "application/json"}
    CAT = f"{BASE}/api/marketing/catalogs"
    cli, db = mongo()

    accs = requests.get(f"{BASE}/api/marketing/accounts", headers=H, timeout=60).json()
    accs = accs.get("accounts", accs) if isinstance(accs, dict) else accs
    by_code = {a.get("account_code"): a for a in accs}
    acc = by_code.get("TOKPED-DA")
    if not check("prasyarat: toko uji (Tokopedia) ada", bool(acc), f"{len(accs)} toko"):
        return 1

    # ── master produk: cari model dengan varian berstok & varian tanpa stok ─────
    mp = requests.get(f"{CAT}/master-products", headers=H, timeout=120).json()
    prods = mp.get("products") or []
    with_stock = next((p for p in prods
                       if any(v["sellable_stock"] > 0 for v in p["variants"])), None)
    no_stock = next((p for p in prods
                     if p["variants"] and all(v["sellable_stock"] <= 0 for v in p["variants"])),
                    None)
    if not check("prasyarat: master produk berstok & tanpa stok ada",
                 bool(with_stock and no_stock),
                 f"{len(prods)} produk"):
        return 1
    fg_in = next(v for v in with_stock["variants"] if v["sellable_stock"] > 0)
    fg_out = no_stock["variants"][0]

    catalog_id = None
    created_items: list[str] = []
    try:
        # ══════════════════════════════════════════════════════════════════════
        print(f"\n{Y}[A] FOTO MASTER IKUT TERBAWA (bukti #3){X}")
        # ══════════════════════════════════════════════════════════════════════
        # foto R&D dipasang di master lewat endpoint resmi (bukan tulis langsung)
        rm = requests.put(f"{BASE}/api/rahaza/models/{with_stock['model_id']}",
                          headers=JH, timeout=60,
                          json={"image_paths": ["/api/uploads/rnd/f4-demo-1.jpg",
                                               "/api/uploads/rnd/f4-demo-2.jpg"]})
        check("A1 foto R&D dipasang di master produk", rm.status_code == 200,
              f"{rm.status_code} {rm.text[:120]}")

        c = requests.post(CAT, headers=JH, timeout=60, json={
            "account_id": acc["id"], "name": "Katalog UJI F4", "platform": acc.get("platform")})
        if not check("A2 katalog uji dibuat", c.status_code in (200, 201),
                     f"{c.status_code} {c.text[:140]}"):
            return 1
        cbody = c.json()
        catalog_id = (cbody.get("catalog") or cbody).get("id")

        r = requests.post(f"{CAT}/{catalog_id}/items/from-fg", headers=JH, timeout=60,
                          json={"fg_material_id": fg_in["fg_material_id"], "price": 0})
        if not check("A3 item dibuat dari FG master", r.status_code in (200, 201),
                     f"{r.status_code} {r.text[:160]}"):
            return 1
        item = r.json()["item"]
        item_id = item["id"]
        created_items.append(item_id)
        check("A4 master_images ≥1 TANPA unggah manual",
              len(item.get("master_images") or []) >= 1,
              f"{len(item.get('master_images') or [])} foto master · "
              f"{(item.get('master_images') or [{}])[0].get('from')}")
        check("A5 item baru lahir DRAFT (belum ada bukti tayang)",
              item.get("catalog_status") == "DRAFT" if "catalog_status" in item
              else True, str(item.get("catalog_status")))

        # ══════════════════════════════════════════════════════════════════════
        print(f"\n{Y}[B] ENAM STATUS TURUNAN + PAGAR BUKTI TAYANG (bukti #1 & #2){X}")
        # ══════════════════════════════════════════════════════════════════════
        def status_of(iid: str) -> str:
            lst = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120).json()
            row = next((x for x in lst["items"] if x["id"] == iid), {})
            return row.get("catalog_status", "?")

        check("B1 DRAFT — belum tayang", status_of(item_id) == "DRAFT", status_of(item_id))

        p = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/publish",
                          headers=JH, json={"platform_url": ""}, timeout=60)
        check("B2 publish TANPA url ⇒ 400", p.status_code == 400,
              f"{p.status_code} {str(p.json().get('detail'))[:90]}")

        p = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/publish",
                          headers=JH, json={"platform_url": "sudah tayang"}, timeout=60)
        check("B3 publish dengan url ngawur ⇒ 400 (bukan dianggap tayang)",
              p.status_code == 400, f"{p.status_code}")

        p = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/publish", headers=JH,
                          timeout=60,
                          json={"platform_url": "https://tokopedia.com/da/uji-f4"})
        check("B4 publish dengan url sah ⇒ 200", p.status_code == 200,
              f"{p.status_code} {p.text[:110]}")
        check("B5 ACTIVE — tayang & stok jual > 0", status_of(item_id) == "ACTIVE",
              f"{status_of(item_id)} · stok {fg_in['sellable_stock']:g}")

        p = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/preorder", headers=JH,
                          json={"is_preorder": True, "note": "batch Agustus"}, timeout=60)
        check("B6 PRE_ORDER — pre-order menang atas stok",
              p.status_code == 200 and status_of(item_id) == "PRE_ORDER",
              f"{p.status_code} · {status_of(item_id)}")
        requests.post(f"{CAT}/{catalog_id}/items/{item_id}/preorder", headers=JH,
                      json={"is_preorder": False}, timeout=60)

        # HABIS memakai varian yang stok jualnya 0 (data demo sengaja menyisakannya)
        r2 = requests.post(f"{CAT}/{catalog_id}/items/from-fg", headers=JH, timeout=60,
                           json={"fg_material_id": fg_out["fg_material_id"], "price": 0})
        item2 = r2.json().get("item", {})
        item2_id = item2.get("id")
        if item2_id:
            created_items.append(item2_id)
        requests.post(f"{CAT}/{catalog_id}/items/{item2_id}/publish", headers=JH,
                      json={"platform_url": "https://tokopedia.com/da/uji-f4-habis"},
                      timeout=60)
        check("B7 HABIS — tayang tetapi stok jual 0",
              status_of(item2_id) == "HABIS",
              f"{status_of(item2_id)} · stok {fg_out['sellable_stock']:g}")

        rj = requests.post(f"{CAT}/{catalog_id}/items/{item2_id}/reject", headers=JH,
                           json={"reason": ""}, timeout=60)
        check("B8 reject TANPA alasan ⇒ 400", rj.status_code == 400, f"{rj.status_code}")
        rj = requests.post(f"{CAT}/{catalog_id}/items/{item2_id}/reject", headers=JH,
                           json={"reason": "Foto tidak sesuai pedoman platform"}, timeout=60)
        check("B9 DITOLAK + alasannya tercatat",
              rj.status_code == 200 and status_of(item2_id) == "DITOLAK",
              str(rj.json().get("item", {}).get("catalog_status_reason"))[:80])

        ar = requests.post(f"{CAT}/{catalog_id}/items/{item2_id}/archive", headers=JH,
                           json={"reason": "stop dijual"}, timeout=60)
        check("B10 NONAKTIF — diarsipkan (tidak dihapus)",
              ar.status_code == 200 and status_of(item2_id) == "NONAKTIF",
              f"{ar.status_code} · {status_of(item2_id)}")
        rs = requests.post(f"{CAT}/{catalog_id}/items/{item2_id}/restore", headers=JH,
                           json={"reason": "dijual lagi"}, timeout=60)
        check("B11 restore ⇒ DRAFT (wajib ditayangkan ulang dengan bukti)",
              rs.status_code == 200 and status_of(item2_id) == "DRAFT",
              status_of(item2_id))

        doc = db.marketing_catalog_items.find_one({"id": item2_id}, {"_id": 0})
        hist = doc.get("status_history") or []
        check("B12 jejak perubahan penayangan tersimpan", len(hist) >= 4,
              f"{len(hist)} langkah: " + " → ".join(h.get("action", "") for h in hist[:6]))

        # ══════════════════════════════════════════════════════════════════════
        print(f"\n{Y}[C] FOTO MARKETPLACE & FOTO UTAMA (bukti #3 lanjutan){X}")
        # ══════════════════════════════════════════════════════════════════════
        lst = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120).json()
        row = next(x for x in lst["items"] if x["id"] == item_id)
        check("C1 primary_image jatuh ke FOTO MASTER saat belum ada foto marketplace",
              (row.get("primary_image") or "").startswith("/api/uploads/rnd/"),
              str(row.get("primary_image")))

        up1 = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/photos", headers=H,
                            timeout=60,
                            files={"file": ("mp1.png", io.BytesIO(png_bytes()), "image/png")})
        up2 = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/photos", headers=H,
                            timeout=60,
                            files={"file": ("mp2.png", io.BytesIO(png_bytes()), "image/png")})
        check("C2 unggah 2 foto marketplace ⇒ 200",
              up1.status_code == 200 and up2.status_code == 200,
              f"{up1.status_code}/{up2.status_code}")
        lst = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120).json()
        row = next(x for x in lst["items"] if x["id"] == item_id)
        check("C3 primary_image BERPINDAH ke foto marketplace",
              (row.get("primary_image") or "").startswith("/api/uploads/products/"),
              str(row.get("primary_image"))[:70])
        check("C4 image_count = foto marketplace + foto master",
              row.get("image_count") == len(row.get("images") or []) + len(row.get("master_images") or []),
              f"{row.get('image_count')} (mp={len(row.get('images') or [])} "
              f"master={len(row.get('master_images') or [])})")

        imgs = list(row.get("images") or [])
        ro = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/photos/reorder",
                           headers=JH, json={"urls": [imgs[1], imgs[0]]}, timeout=60)
        check("C5 urutan foto bisa diubah ⇒ foto utama ikut berubah",
              ro.status_code == 200 and ro.json().get("primary_image") == imgs[1],
              f"{ro.status_code} · {str(ro.json().get('primary_image'))[-24:]}")
        ro_bad = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/photos/reorder",
                               headers=JH, json={"urls": ["/tidak/ada.png"]}, timeout=60)
        check("C6 urutan foto berisi url asing ⇒ 400", ro_bad.status_code == 400,
              f"{ro_bad.status_code}")

        rf = requests.post(f"{CAT}/{catalog_id}/items/{item_id}/refresh-from-master",
                           headers=JH, timeout=60)
        check("C7 refresh-from-master menyegarkan foto master",
              rf.status_code == 200
              and len(rf.json().get("item", {}).get("master_images") or []) >= 1,
              f"{rf.status_code} · {len(rf.json().get('item', {}).get('master_images') or [])} foto")

        # ══════════════════════════════════════════════════════════════════════
        print(f"\n{Y}[D] KONTRAK BARIS & RINGKAS PER STATUS (bukti #4 & #6){X}")
        # ══════════════════════════════════════════════════════════════════════
        lst = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120).json()
        row = next(x for x in lst["items"] if x["id"] == item_id)
        need = ["primary_image", "catalog_status", "catalog_status_reason", "publish_state",
                "hpp", "hpp_source", "margin", "margin_pct", "available", "in_sync",
                "retail_price_master", "price_delta_vs_master", "image_count",
                "stock_live_status", "needs_attention", "category_name", "weight_gram",
                "sku", "name"]
        miss = [f for f in need if f not in row]
        check("D1 setiap baris membawa 19 kolom wajib layar", not miss,
              "lengkap" if not miss else f"HILANG: {', '.join(miss)}")

        summ = lst["stock_summary"]
        by = summ.get("by_status") or {}
        check("D2 by_status ada & menjumlah = total item katalog",
              sum(by.values()) == lst["total"],
              f"{by} · total {lst['total']}")
        check("D3 status_options dikirim untuk dropdown layar",
              len(lst.get("status_options") or []) == 6,
              str([o["value"] for o in lst.get("status_options", [])]))

        f_draft = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120,
                               params={"catalog_status": "DRAFT"}).json()
        check("D4 filter catalog_status=DRAFT hanya mengembalikan DRAFT",
              all(x["catalog_status"] == "DRAFT" for x in f_draft["items"]),
              f"{f_draft['total']} baris")
        f_bad = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=60,
                             params={"catalog_status": "NGAWUR"})
        check("D5 status ngawur ⇒ 400 (bukan diam-diam kosong)",
              f_bad.status_code == 400, f"{f_bad.status_code}")
        f_photo = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120,
                               params={"has_photo": "true"}).json()
        check("D6 filter has_photo bekerja",
              all(x["image_count"] > 0 for x in f_photo["items"]) and f_photo["total"] >= 1,
              f"{f_photo['total']} baris berfoto")
        f_sort = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120,
                              params={"sort": "margin", "order": "desc"}).json()
        margins = [x["margin"] for x in f_sort["items"]]
        check("D7 urutan bisa dipilih (marjin turun)", margins == sorted(margins, reverse=True),
              str(margins[:4]))
        f_ps = requests.get(f"{CAT}/{catalog_id}/items", headers=H, timeout=120,
                            params={"publish_state": "published"}).json()
        check("D8 filter publish_state bekerja",
              all(x["publish_state"] == "published" for x in f_ps["items"]),
              f"{f_ps['total']} tayang")

        bt = requests.post(f"{CAT}/{catalog_id}/items/bulk-transition", headers=JH,
                           timeout=60,
                           json={"item_ids": created_items, "action": "archive",
                                 "reason": "uji massal"})
        check("D9 aksi massal (arsipkan 2 item) ⇒ 200 & keduanya NONAKTIF",
              bt.status_code == 200 and bt.json().get("changed") == len(created_items),
              f"{bt.status_code} · {bt.json().get('message')}")
        bp = requests.post(f"{CAT}/{catalog_id}/items/bulk-transition", headers=JH,
                           timeout=60,
                           json={"item_ids": created_items, "action": "publish"})
        check("D10 aksi massal 'publish' DITOLAK 400 (URL harus per item)",
              bp.status_code == 400, f"{bp.status_code}")

    finally:
        print(f"\n  {Y}(bersih-bersih){X}")
        for iid in created_items:
            d = requests.delete(f"{CAT}/{catalog_id}/items/{iid}", headers=H, timeout=60)
            print(f"    hapus item {iid[:8]}: {d.status_code}")
        if catalog_id:
            d = requests.delete(f"{CAT}/{catalog_id}", headers=H, timeout=60)
            print(f"    hapus katalog uji: {d.status_code}")
        # foto master demo dilepas kembali dari master produk
        requests.put(f"{BASE}/api/rahaza/models/{with_stock['model_id']}",
                     headers=JH, json={"image_paths": []}, timeout=60)
        cli.close()

    print("\n" + "=" * 90)
    tot = len(RES); fail = sum(1 for _, o, _ in RES if not o)
    print(f"RINGKAS F4: {tot - fail}/{tot} PASS"
          + (f" · {R}{fail} GAGAL{X}" if fail else f" {G}(status turunan · foto master · kolom penuh){X}"))
    print("=" * 90)
    for n, o, d in RES:
        if not o:
            print(f"  {R}·{X} {n} — {d}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
