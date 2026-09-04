#!/usr/bin/env python3
"""
gen_light_button_css.py
=======================
Menghasilkan ulang blok CSS "TOMBOL / KONTRAS" di frontend/src/index.css.

Kenapa perlu script:
  Selector substring (`[class*="bg-blue-5"]`) ternyata ikut mengenai
  `hover:bg-blue-50` sehingga tombol ikon jadi berlatar penuh. Solusinya
  memakai exact word match `[class~="bg-blue-500"]`, tapi kombinasinya
  ratusan baris — jadi digenerate.

Idempotent: blok lama (di antara marker) selalu ditulis ulang.
"""
from pathlib import Path

CSS = Path("/app/frontend/src/index.css")

START = "/* @@LIGHT-BUTTON-BASELINE:START@@ */"
END = "/* @@LIGHT-BUTTON-BASELINE:END@@ */"

# Warna yang dipetakan ke token brand (--primary)
BRAND = ["blue", "indigo", "sky", "violet", "purple"]
BRAND_SHADES = [500, 600, 700, 800]

# Warna semantik: hue dipertahankan, teks dipaksa putih agar kontras aman
SEMANTIC = {
    "emerald": [500, 600, 700],
    "green": [500, 600, 700],
    "teal": [500, 600, 700],
    "cyan": [600, 700],
    "amber": [600, 700],
    "yellow": [600, 700],
    "orange": [500, 600, 700],
    "red": [500, 600, 700],
    "rose": [500, 600, 700],
    "pink": [500, 600, 700],
    "fuchsia": [500, 600, 700],
    "slate": [600, 700, 800, 900],
    "gray": [600, 700, 800, 900],
    "zinc": [600, 700, 800, 900],
    "neutral": [600, 700, 800, 900],
    "stone": [600, 700, 800, 900],
}

INTERACTIVE = 'button, a, [role="button"], [type="button"], [type="submit"]'


def sel_list(pairs, prefix=""):
    """[class~="<prefix>bg-<fam>-<shade>"] untuk tiap pasangan."""
    return [f'[class~="{prefix}bg-{fam}-{shade}"]' for fam, shade in pairs]


def brand_pairs():
    return [(f, s) for f in BRAND for s in BRAND_SHADES]


def semantic_pairs():
    return [(f, s) for f, shades in SEMANTIC.items() for s in shades]


def join(sels, indent="  "):
    return (",\n" + indent).join(sels)


def build():
    b_base = join(sel_list(brand_pairs()))
    b_hover = join(sel_list(brand_pairs(), prefix="hover:"))
    s_base = join(sel_list(semantic_pairs()))

    out = []
    out.append(START)
    out.append("""
/* ───────────────────────────────────────────────────────────────────────────
   TOMBOL — warna mentah dipetakan ke token brand (light mode)
   Exact word match (`class~=`) supaya varian seperti `hover:bg-blue-50`
   ATAU `bg-blue-500/20` TIDAK ikut terkena.
   Hanya elemen interaktif; titik status / chart / badge tetap semantik.
   ─────────────────────────────────────────────────────────────────────────── */""")

    # 1. Tombol brand — background & teks
    out.append(f"""html.light :is({INTERACTIVE}):is(
  {b_base}
) {{
  background-color: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
  border-color: hsl(var(--primary));
}}""")

    out.append(f"""html.light :is({INTERACTIVE}):is(
  {b_base}
) :is(svg, span, p, strong, small) {{
  color: hsl(var(--primary-foreground));
}}""")

    # 2. Hover pada tombol brand
    out.append(f"""html.light :is({INTERACTIVE}):is(
  {b_hover}
):hover {{
  background-color: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
  filter: brightness(1.08);
}}""")

    # 3. Tombol semantik — teks putih
    out.append(f"""html.light :is({INTERACTIVE}):is(
  {s_base}
) {{
  color: #FFFFFF;
}}
html.light :is({INTERACTIVE}):is(
  {s_base}
) :is(svg, span, p, strong, small) {{
  color: #FFFFFF;
}}""")

    # 4. Bug kontras: .text-foreground di atas latar pekat (element apa pun)
    all_base = join(sel_list(brand_pairs() + semantic_pairs()))
    out.append(f"""
/* Bug kontras dari refactor massal terdahulu: `text-foreground` (near-black)
   dipakai di atas latar pekat. Di light mode dipaksa putih. */
html.light .text-foreground:is(
  {all_base}
) {{
  color: #FFFFFF;
}}
html.light .text-foreground:is(
  {all_base}
) :is(svg, span, p) {{
  color: #FFFFFF;
}}""")

    out.append(END)
    return "\n".join(out) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# Remap warna TEKS pucat (shade 200/300/400) → shade gelap yang terbaca
# di atas permukaan putih. Nilai diambil dari palet Tailwind resmi.
# ═══════════════════════════════════════════════════════════════════════════
TEXT_START = "/* @@LIGHT-TEXT-BASELINE:START@@ */"
TEXT_END = "/* @@LIGHT-TEXT-BASELINE:END@@ */"

READABLE = {
    "slate": "#475569",
    "gray": "#4B5563",
    "zinc": "#52525B",
    "neutral": "#525252",
    "stone": "#57534E",
    "red": "#DC2626",
    "orange": "#C2410C",
    "amber": "#B45309",
    "yellow": "#A16207",
    "lime": "#4D7C0F",
    "green": "#15803D",
    "emerald": "#047857",
    "teal": "#0F766E",
    "cyan": "#0E7490",
    "sky": "#0369A1",
    "blue": "#2563EB",
    "indigo": "#4F46E5",
    "violet": "#7C3AED",
    "purple": "#9333EA",
    "fuchsia": "#C026D3",
    "pink": "#DB2777",
    "rose": "#E11D48",
}
PALE_SHADES = [200, 300, 400]

# Permukaan gelap tempat teks pucat justru BENAR — dikecualikan.
DARK_SURFACES = ", ".join(
    f'[class~="bg-{fam}-{sh}"]'
    for fam in ("slate", "gray", "zinc", "neutral", "stone")
    for sh in (800, 900, 950)
) + ', [class~="bg-black"]'


def build_text_block():
    lines = [TEXT_START]
    lines.append("""
/* ───────────────────────────────────────────────────────────────────────────
   TEKS PUCAT → SHADE TERBACA (light mode)
   `text-emerald-300`, `text-blue-400`, dst. adalah warna untuk latar gelap.
   Di atas kartu putih kontrasnya < 3:1. Di light mode dipetakan ke shade
   600/700 dari keluarga warna yang sama sehingga sinyal semantiknya tetap.
   ─────────────────────────────────────────────────────────────────────────── */""")
    for fam, hexv in READABLE.items():
        sels = ",\n".join(f"html.light .text-{fam}-{sh}" for sh in PALE_SHADES)
        lines.append(f"{sels} {{\n  color: {hexv};\n}}")

    pale_sels = ", ".join(
        f".text-{fam}-{sh}" for fam in READABLE for sh in PALE_SHADES
    )
    lines.append(f"""
/* Penyeimbang — di dalam permukaan gelap, teks pucat tetap dipertahankan */
html.light :is({DARK_SURFACES}) :is({pale_sels}) {{
  color: inherit;
}}""")
    lines.append(TEXT_END)
    return "\n".join(lines) + "\n"


def replace_block(src, start, end, block):
    if start in src and end in src:
        head = src.split(start)[0]
        tail = src.split(end, 1)[1]
        return head + block + tail
    return src.rstrip() + "\n\n" + block


def main():
    src = CSS.read_text()
    src = replace_block(src, START, END, build())
    src = replace_block(src, TEXT_START, TEXT_END, build_text_block())
    CSS.write_text(src)
    print("[gen] blok CSS tombol + teks light-mode ditulis")


if __name__ == "__main__":
    main()
