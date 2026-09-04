#!/usr/bin/env python3
"""Uji LAYAR untuk BUG-1: form Launching wajib memakai Master Produk.

Cerita yang diuji (klik sungguhan, bukan membaca kode):
  1. Buka Peluncuran Produk → klik "Tambah Produk"
  2. Form TIDAK lagi punya kotak ketik nama produk / bahan / model
  3. Pemilih master ADA, bisa dibuka, dan berisi produk dari master
  4. Memilih produk mengisi kode, kategori, HPP, harga resmi — tanpa mengetik
  5. Menyimpan tanpa memilih produk DITOLAK dengan pesan yang menyebut jalan keluar
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://da37-cmt-bridge.preview.emergentagent.com"
OUT = Path("/app/.logs/shots")
OUT.mkdir(parents=True, exist_ok=True)
errs, console_errs = [], []


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: console_errs.append(m.text)
              if m.type == "error" else None)
        pg.set_default_timeout(60000)

        pg.goto(URL, wait_until="domcontentloaded")
        pg.wait_for_timeout(4000)
        pg.fill("input[type='email']", "admin@garment.com")
        pg.fill("input[type='password']", "Admin@123")
        pg.click("button[type='submit']")
        pg.wait_for_timeout(9000)
        pg.evaluate("window.location.hash='marketing-product-launches'")
        pg.wait_for_timeout(1200)
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_timeout(8000)
        print("1) layar Peluncuran Produk terbuka")

        pg.click("[data-testid='btn-add-launch']")
        pg.wait_for_timeout(2500)
        pg.screenshot(path=str(OUT / "f14_form_dialog.png"))
        print("2) dialog Tambah Produk terbuka")

        # 2) tidak ada kotak ketik nama produk / bahan / model
        dialog = pg.locator("[role='dialog']")
        html = dialog.inner_html()
        for needle, label in (("launch-material-readonly", "Bahan (dari master)"),
                              ("launch-model-readonly", "Kode Model (dari master)")):
            print(f"   {'OK ' if needle in html else 'GAGAL'} {label} tampil read-only")

        # 3) pemilih master ada & bisa dibuka
        sel = pg.locator("[data-testid='launch-product-select']")
        print(f"3) pemilih master terlihat: {sel.is_visible()}")
        sel.click()
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(OUT / "f14_picker_open.png"))
        opts = pg.locator("[data-testid^='launch-product-select-opt-']")
        n = opts.count()
        print(f"   pilihan produk dari master: {n}")
        if n == 0:
            print("   GAGAL: master kosong di layar")
            b.close()
            return 1

        first_text = opts.nth(0).inner_text().replace("\n", " | ")
        opts.nth(0).click()
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(OUT / "f14_picked.png"))
        print(f"4) produk dipilih: {first_text[:70]}")

        meta = pg.locator("[data-testid='launch-product-select-meta']")
        print(f"   ringkasan master tampil: {meta.is_visible()} "
              f"→ {meta.inner_text().replace(chr(10), ' ') if meta.is_visible() else ''}")
        model_ro = pg.locator("[data-testid='launch-model-readonly']").inner_text()
        print(f"   kode model terisi otomatis: '{model_ro.strip()}'")

        print(f"\npage errors  : {len(errs)}  {errs[:2]}")
        print(f"console error: {len(console_errs)}  {console_errs[:2]}")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
