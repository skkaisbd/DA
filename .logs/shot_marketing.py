#!/usr/bin/env python3
"""Ambil tangkapan layar Portal Marketing untuk MENGUKUR keluhan pemilik
("cards belum terdesain: lupa background, sebagian abu-abu") — bukan menebak.

Selain gambar, skrip ini juga MENGUKUR: untuk setiap kartu terlihat, warna
latar efektifnya dibaca dari browser. Kartu yang latarnya `transparent` /
`rgba(0,0,0,0)` adalah kartu yang "lupa diberi background" — dan itu tidak bisa
dilihat dari kode saja karena kelas Tailwind bisa tertimpa.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://da37-cmt-bridge.preview.emergentagent.com"
OUT = Path("/app/.logs/shots")
OUT.mkdir(parents=True, exist_ok=True)

MODULES = sys.argv[1:] or [
    "marketing-product-launches",
    "marketing-ai-hub",
    "marketing-kol-hub",
    "marketing-live-hub",
    "marketing-reports",
    "marketing-health",
]

PROBE = """
() => {
  const out = [];
  const cards = document.querySelectorAll(
    '[class*="rounded-xl"],[class*="rounded-lg"],[data-slot="card"]');
  let i = 0;
  for (const el of cards) {
    const r = el.getBoundingClientRect();
    if (r.width < 160 || r.height < 60) continue;         // bukan kartu
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    const transparent = bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent';
    const hasBorder = parseFloat(cs.borderTopWidth) > 0;
    const hasShadow = cs.boxShadow && cs.boxShadow !== 'none';
    out.push({
      i: i++,
      cls: (el.className || '').toString().slice(0, 150),
      bg, transparent, hasBorder, hasShadow,
      w: Math.round(r.width), h: Math.round(r.height),
      text: (el.innerText || '').trim().slice(0, 48).replace(/\\n/g, ' | '),
    });
    if (i > 60) break;
  }
  return out;
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.set_default_timeout(60000)
    pg.goto(URL, wait_until="domcontentloaded")
    pg.wait_for_timeout(4000)
    pg.fill("input[type='email']", "admin@garment.com")
    pg.fill("input[type='password']", "Admin@123")
    pg.click("button[type='submit']")
    pg.wait_for_timeout(9000)
    print("login OK")

    report = {}
    for mod in MODULES:
        try:
            pg.evaluate(f"window.location.hash='{mod}'")
            pg.wait_for_timeout(1200)
            pg.reload(wait_until="domcontentloaded")
            pg.wait_for_timeout(7000)
            pg.screenshot(path=str(OUT / f"{mod}.png"), full_page=False)
            cards = pg.evaluate(PROBE)
            bad = [c for c in cards if c["transparent"]
                   and not c["hasBorder"] and not c["hasShadow"]]
            report[mod] = {"cards": len(cards), "tanpa_background": len(bad),
                           "contoh": bad[:5]}
            print(f"{mod:34s} kartu={len(cards):3d} tanpa_background={len(bad):3d}")
        except Exception as e:  # noqa: BLE001
            print(f"{mod:34s} GAGAL: {e}")
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    b.close()
print(f"\nsimpan di {OUT}")
