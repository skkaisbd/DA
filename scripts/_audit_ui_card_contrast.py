#!/usr/bin/env python3
"""_audit_ui_card_contrast.py — UKUR dua cacat tampilan yang DILAPORKAN PEMILIK:
kartu yang "lupa diberi background", dan teks/badge yang "masih abu-abu".

═══════════════════════════════════════════════════════════════════════════════
KENAPA ALAT INI ADA
═══════════════════════════════════════════════════════════════════════════════
Laporan pemilik (2026-08-14): *"beberapa page di portal marketing cardsnya masih
belum terdesign dengan baik seperti lupa di kasih background cardsnya, lalu ada
beberapa yang masih abu abu itu perbaiki."*

Dua keluhan itu ternyata punya sebab yang BISA DIUKUR — bukan selera:

── (1) KELAS TAILWIND RUSAK ⇒ TIDAK ADA CSS SAMA SEKALI ────────────────────────
Ditemukan pola `bg-foreground/[0.06]0`, `border-foreground/[0.01]0`, dst. Angka
nyasar sesudah `]` membuat kelasnya TIDAK DIKENAL Tailwind, jadi ia tidak
menghasilkan satu baris CSS pun. Elemennya benar-benar tanpa latar — persis
"lupa dikasih background".

Sebabnya bukan kelalaian satu orang, melainkan **find/replace massal yang
gagal**: `bg-white/60` → (ganti `white/6` jadi `foreground/[0.06]`) →
`bg-foreground/[0.06]0`. Pola yang sama menjelaskan `[0.01]0` (dari `/10`),
`[0.02]0` (`/20`), `[0.03]0` (`/30`), `[0.04]0` (`/40`), `[0.08]0` (`/80`).
Kelas rusak TIDAK PERNAH menjadi galat build maupun lint — Tailwind hanya
mengabaikannya. Itulah kenapa ia bisa hidup berbulan-bulan.

── (2) ABU-ABU DI ATAS ABU-ABU ⇒ TIDAK TERBACA ────────────────────────────────
Pola `bg-muted text-muted-foreground/50`. Dengan tema terang produk ini
(`--muted: 240 20% 94%`, `--muted-foreground: 226 16% 44%`):
  · opasitas penuh  → rasio kontras ± 4.3  (memadai untuk teks tebal kecil)
  · opasitas 50%    → warna teks BERCAMPUR ke latar (L ± 69%) → rasio ± 1.9
    — jauh di bawah ambang 3.0 mana pun. Badge status jadi bayangan abu-abu.
Modifikator opasitas pada teks di atas latar `muted` selalu memperburuk kontras;
tidak ada kasus di mana ia menolong.

Alat ini MENGUKUR keduanya (bukan menilai selera warna), lalu melaporkannya per
berkas supaya bisa diperbaiki dan dijaga.

Pakai:  python3 /app/scripts/_audit_ui_card_contrast.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path("/app/frontend/src")
OUT = Path("/app/memory/AUDIT_UI_CARD_CONTRAST.json")
G, R, Y, X, B, C = ("\033[92m", "\033[91m", "\033[93m", "\033[0m",
                    "\033[1m", "\033[96m")

# (1) Kelas dengan angka NYASAR sesudah kurung siku arbitrary-value.
#     `bg-foreground/[0.06]0`  → RUSAK      (tidak menghasilkan CSS)
#     `bg-foreground/[0.15]`   → sah        (opasitas 15%)
BROKEN_RE = re.compile(r"[\w-]+/\[[0-9.]+\]\d+")

# (2) Teks ber-opasitas di atas latar `muted` — abu-abu di atas abu-abu.
#     Dicari dalam SATU string className supaya konteksnya pasti sama elemen.
MUTED_BG_RE = re.compile(r"\bbg-muted(?:/\d+)?\b")
FADED_TEXT_RE = re.compile(r"\btext-(muted-foreground|foreground)/(\d{1,3})\b")

# Nilai tema NYATA produk ini (frontend/src/index.css). Dipakai untuk MENGHITUNG
# kontras, bukan menebak ambang. Versi pertama alat ini memakai ambang kasar
# "opasitas < 100 = cacat" dan itu MENUDUH SALAH: `text-foreground/80` di atas
# `bg-muted` rasionya 8.6 — sangat terbaca. Penjaga yang salah tuduh akan
# berhenti dipercaya, jadi angkanya dihitung.
THEMES = {
    # nama: (L latar muted %, L muted-foreground %, L foreground %)
    "terang": (94.0, 44.0, 10.0),
    "gelap":  (14.0, 68.0, 97.0),
}
# WCAG AA untuk teks besar/tebal = 3.0. Badge status memakai teks kecil TEBAL,
# jadi 3.0 dipakai sebagai LANTAI (bukan target). Di bawah itu bukan soal
# selera lagi — tulisannya memang menghilang ke latarnya.
CONTRAST_FLOOR = 3.0

# (3) KELAS TAILWIND YANG DIRAKIT SAAT BERJALAN.
#     `className={`bg-${color}-500/5 …`}` — Tailwind menghasilkan CSS dengan
#     MEMBACA TEKS berkas sumber; ia tidak menjalankan JavaScript. Kelas itu
#     tidak pernah dibuat, dan elemennya tampil TANPA latar.
#
#     Yang membuatnya sulit ditemukan: kadang kelasnya KEBETULAN ada karena
#     berkas LAIN memakainya secara harfiah. Terukur pada `main.*.css` SEBELUM
#     perbaikan: `bg-violet-500/5` ADA (dipakai berkas lain) tetapi
#     `bg-teal-500/5`, `border-teal-500/20`, `border-teal-500/25` TIDAK ADA ⇒
#     pada komponen KPI yang SAMA, kartu "violet" terlihat benar sementara
#     kartu "teal" ("Perlu Diserahkan" di Dashboard Aksesoris) tampil polos.
#     Itulah bentuk paling membingungkan dari keluhan "lupa dikasih background".
#     Perbaikannya: `lib/tone.js` — nama warna boleh dinamis, KELASNYA harfiah.
DYNAMIC_CLASS_RE = re.compile(
    r"className=\{`[^`]*\b(?:bg|text|border|from|via|to|ring|fill|stroke)-\$\{")


def _lum_from_l(l_pct: float) -> float:
    """Luminансi relatif perkiraan dari komponen L (HSL) — cukup untuk MEMBANDINGKAN.

    Warna di sini semuanya abu-abu/berjenuh rendah, jadi L (HSL) ≈ terang
    persepsi; pendekatan sRGB linear di bawah sudah memadai untuk memutuskan
    "terbaca / tidak", dan sengaja dibuat sederhana supaya bisa diperiksa orang.
    """
    c = max(0.0, min(1.0, l_pct / 100.0))
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _ratio(l1: float, l2: float) -> float:
    a, b = _lum_from_l(l1), _lum_from_l(l2)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def contrast_on_muted(token: str, opacity: int) -> float:
    """Rasio kontras TERBURUK di antara tema terang & gelap."""
    worst = 99.0
    for bg_l, mutedfg_l, fg_l in THEMES.values():
        text_l = mutedfg_l if token == "muted-foreground" else fg_l
        # Opasitas = pencampuran ke latar.
        eff = (opacity / 100.0) * text_l + (1 - opacity / 100.0) * bg_l
        worst = min(worst, _ratio(eff, bg_l))
    return worst


def scan(path: Path) -> tuple[list, list, list]:
    try:
        src = path.read_text(errors="ignore")
    except Exception:  # noqa: BLE001
        return [], [], []
    lines = src.splitlines()

    broken = []
    for i, ln in enumerate(lines, 1):
        for m in BROKEN_RE.finditer(ln):
            broken.append({"file": str(path.relative_to(SRC)), "line": i,
                           "cls": m.group(0), "snippet": ln.strip()[:120]})

    faded = []
    for i, ln in enumerate(lines, 1):
        if not MUTED_BG_RE.search(ln):
            continue
        for m in FADED_TEXT_RE.finditer(ln):
            token, op = m.group(1), int(m.group(2))
            ratio = contrast_on_muted(token, op)
            if ratio < CONTRAST_FLOOR:
                faded.append({"file": str(path.relative_to(SRC)), "line": i,
                              "cls": m.group(0), "opacity": op,
                              "contrast": round(ratio, 2),
                              "snippet": ln.strip()[:120]})

    dynamic = []
    for i, ln in enumerate(lines, 1):
        # Baris komentar dikecualikan: berkas `lib/tone.js` MENJELASKAN pola ini
        # sebagai contoh yang salah; menuduhnya akan membuat penjaga ini
        # bertengkar dengan dokumentasinya sendiri.
        st = ln.lstrip()
        if st.startswith(("//", "*", "/*")):
            continue
        if DYNAMIC_CLASS_RE.search(ln):
            dynamic.append({"file": str(path.relative_to(SRC)), "line": i,
                            "snippet": ln.strip()[:140]})
    return broken, faded, dynamic


def main() -> int:
    files = [f for f in SRC.rglob("*.jsx") if "/ui/" not in str(f)]
    files += list(SRC.rglob("*.js"))
    all_broken, all_faded, all_dyn = [], [], []
    for f in files:
        b, d, y = scan(f)
        all_broken.extend(b)
        all_faded.extend(d)
        all_dyn.extend(y)

    rep = {
        "scanned_files": len(files),
        "broken_classes": all_broken,
        "faded_on_muted": all_faded,
        "dynamic_classes": all_dyn,
        "total_broken": len(all_broken),
        "total_faded": len(all_faded),
        "total_dynamic": len(all_dyn),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False))

    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0

    print(f"{B}══ AUDIT TAMPILAN — kartu tanpa latar & abu-abu di atas abu-abu ══{X}")
    print(f"  berkas dipindai: {len(files)}")
    print(f"\n{B}(1) Kelas Tailwind RUSAK (tidak menghasilkan CSS){X}  "
          f"{R if all_broken else G}{len(all_broken)}{X}")
    byf: dict = {}
    for h in all_broken:
        byf.setdefault(h["file"], []).append(h)
    for fn, hs in sorted(byf.items(), key=lambda kv: -len(kv[1])):
        print(f"  {Y}{len(hs):2d}{X}  {fn}")
        for h in hs[:4]:
            print(f"        {C}L{h['line']:<5d}{X} {h['cls']}")

    print(f"\n{B}(2) Teks di atas latar `muted` dengan kontras < {CONTRAST_FLOOR}{X}  "
          f"{R if all_faded else G}{len(all_faded)}{X}")
    byf2: dict = {}
    for h in all_faded:
        byf2.setdefault(h["file"], []).append(h)
    for fn, hs in sorted(byf2.items(), key=lambda kv: -len(kv[1]))[:25]:
        print(f"  {Y}{len(hs):2d}{X}  {fn}")
        for h in hs[:3]:
            print(f"        {C}L{h['line']:<5d}{X} {h['cls']:28s} rasio {h['contrast']}")

    print(f"\n{B}(3) Kelas Tailwind DIRAKIT saat berjalan (tidak pernah dibuat){X}  "
          f"{R if all_dyn else G}{len(all_dyn)}{X}")
    byf3: dict = {}
    for h in all_dyn:
        byf3.setdefault(h["file"], []).append(h)
    for fn, hs in sorted(byf3.items(), key=lambda kv: -len(kv[1])):
        print(f"  {Y}{len(hs):2d}{X}  {fn}")
        for h in hs[:3]:
            print(f"        {C}L{h['line']:<5d}{X} {h['snippet'][:90]}")

    print(f"\n  laporan: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
