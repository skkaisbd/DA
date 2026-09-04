#!/usr/bin/env python3
"""2026_08_12_catalog_master_images.py — F4: isi field baru pada item katalog LAMA.

KENAPA MIGRASI INI ADA
----------------------
F4 menambahkan tiga hal pada `marketing_catalog_items`:

  1. `master_images[]`  — foto MASTER produk (dari `rahaza_models.image_paths`).
     Item lama dibuat sebelum penyalinan ini ada, jadi foto R&D-nya tidak pernah
     terbawa: katalog tampak "tanpa foto" padahal fotonya sudah ada sejak R&D.

  2. `publish_state`    — keputusan tayang/tidak. Item lama tidak punya field ini.
     Menganggap semuanya 'draft' akan menyatakan produk yang JELAS sudah tayang
     (punya `platform_url`) sebagai belum tayang, dan sebaliknya menganggap semuanya
     'published' berarti MENGARANG bukti tayang. Aturan yang dipakai — dan ditulis
     sekali ke dokumen supaya tidak ditebak berulang kali:
         ada `platform_url` ⇒ 'published' (+ `publish_state_inferred=True`)
         tidak ada          ⇒ 'draft'
     `publish_state_inferred` membuat layar bisa jujur: nilai itu **kesimpulan
     sistem**, bukan keputusan manusia.

  3. `catalog_status`    — cache status turunan (rumus tunggal `core/catalog_status.py`)
     supaya filter & ringkasan per status tidak harus menghitung ulang seluruh
     katalog setiap kali.

Sifat: **idempoten** & **tidak menimpa keputusan manusia** (item yang sudah punya
`publish_state` sah tidak disentuh).

Pakai:
    python3 backend/migrations/2026_08_12_catalog_master_images.py            # dry-run
    python3 backend/migrations/2026_08_12_catalog_master_images.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "/app/backend")

from core import catalog_status as cstatus   # noqa: E402
from core import catalog_stock as cstock     # noqa: E402
from core import product_master as pm        # noqa: E402
from database import get_db                  # noqa: E402

G, Y, R, X = "\033[92m", "\033[93m", "\033[91m", "\033[0m"


async def main(apply: bool) -> int:
    db = get_db()
    items = await db.marketing_catalog_items.find({}, {"_id": 0}).to_list(20000)
    if not items:
        print(f"{Y}0 item katalog — tidak ada yang perlu dimigrasi.{X}")
        return 0

    models = {m["id"]: m for m in await db.rahaza_models.find(
        {}, {"_id": 0}).to_list(5000)}
    blocked = await cstock.blocked_location_ids(db)

    n_img = n_state = n_status = 0
    by_status: dict = cstatus.empty_by_status()
    samples: list = []

    for it in items:
        patch: dict = {}

        # 1) foto master
        model = models.get(it.get("model_id") or "") or {}
        imgs = pm.master_images(model) if model else []
        if imgs and (it.get("master_images") or []) != imgs:
            patch["master_images"] = imgs
            n_img += 1
        elif "master_images" not in it:
            patch["master_images"] = imgs      # tulis [] supaya field-nya selalu ada

        # 2) publish_state (tidak pernah menimpa nilai sah yang sudah ada)
        cur = str(it.get("publish_state") or "").strip().lower()
        if cur not in cstatus.PUBLISH_STATES:
            inferred = cstatus.publish_state_of(it)
            patch["publish_state"] = inferred
            patch["publish_state_inferred"] = True
            if inferred == "published" and not it.get("published_at"):
                patch["published_at"] = it.get("updated_at") or it.get("created_at")
            n_state += 1
        patch.setdefault("is_preorder", bool(it.get("is_preorder") or False))
        patch.setdefault("rejected_reason", it.get("rejected_reason") or "")

        # 3) cache status (dihitung dengan stok jual SEBENARNYA)
        merged = {**it, **patch}
        res = await cstock.item_sellable(db, merged, blocked_locs=blocked)
        available = res["available"] if res.get("link_type") != "none" else None
        st = cstatus.cache_patch(merged, available)
        if it.get("catalog_status") != st["catalog_status"]:
            n_status += 1
        patch.update(st)
        by_status[st["catalog_status"]] += 1

        if len(samples) < 8:
            samples.append((it.get("sku") or it.get("id"), patch["catalog_status"],
                            len(patch.get("master_images", it.get("master_images") or [])),
                            patch.get("publish_state", cur)))

        if apply:
            await db.marketing_catalog_items.update_one({"id": it["id"]}, {"$set": patch})

    mode = f"{G}APPLY{X}" if apply else f"{Y}DRY-RUN{X}"
    print(f"\n{'=' * 78}\nF4 migrasi item katalog — mode: {mode}\n{'=' * 78}")
    print(f"  item diperiksa            : {len(items)}")
    print(f"  foto master diisi/segarkan: {n_img}")
    print(f"  publish_state disimpulkan : {n_state}")
    print(f"  cache status diperbarui   : {n_status}")
    print(f"  sebaran status            : "
          + " · ".join(f"{k}={v}" for k, v in by_status.items() if v))
    print("  contoh:")
    for sku, st, ni, ps in samples:
        print(f"    {sku:<24} {st:<10} foto_master={ni} publish={ps}")
    if not apply:
        print(f"\n  {Y}DRY-RUN — tidak ada yang diubah. Jalankan ulang dengan --apply.{X}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.apply)))
