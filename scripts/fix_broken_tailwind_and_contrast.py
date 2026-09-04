#!/usr/bin/env python3
"""fix_broken_tailwind_and_contrast.py — perbaiki DUA cacat tampilan terukur.

Dijalankan SEKALI (idempoten). Disimpan di repo sebagai bukti apa yang diubah
dan mengapa — bukan sebagai alat yang perlu dijalankan rutin.

(1) KELAS TAILWIND RUSAK — sisa find/replace massal yang gagal
    (`bg-white/60` → `bg-foreground/[0.06]0`). Kelas dengan angka nyasar
    sesudah `]` tidak menghasilkan CSS apa pun ⇒ elemen benar-benar tanpa latar.
    Setiap pemetaan di bawah MENGEMBALIKAN MAKSUD ASLINYA, bukan menebak warna:
    nilai `white/NN` diterjemahkan ke padanan yang sadar-tema (`background/NN`,
    `border-border`, `foreground/NN`) sesuai KONTEKS elemennya.

    Perkecualian yang disengaja: `UniversalScanPortal.jsx` memakai panel
    `bg-zinc-900` yang SELALU gelap (bukan mengikuti tema), jadi di sana
    `border-white/10` memang jawaban yang benar — menggantinya dengan
    `border-border` akan membuat garisnya hilang di panel gelap.

(2) ABU-ABU DI ATAS ABU-ABU — `text-muted-foreground/50|60|70` pada elemen
    ber-latar `bg-muted`. Rasio kontrasnya 1.9–2.6 (lantai 3.0). Modifikator
    opasitas di sini tidak pernah menolong: `muted-foreground` memang sudah
    warna redup; menurunkannya lagi hanya mencampurnya ke latar. Perbaikannya
    membuang modifikatornya (rasio naik ke ± 4.3 terang / 4.9 gelap).
    HANYA baris yang benar-benar ber-`bg-muted` yang disentuh.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("/app/frontend/src")

# ── (1) pemetaan kelas rusak → maksud aslinya, sadar-tema ────────────────────
GLOBAL_MAP = {
    "bg-foreground/[0.06]0":     "bg-background/60",   # was bg-white/60
    "bg-foreground/[0.08]0":     "bg-background/80",   # was bg-white/80
    "bg-foreground/[0.03]0":     "bg-background/70",   # was bg-white/30
    "bg-foreground/[0.01]0":     "bg-background/60",   # was bg-white/10
    "border-foreground/[0.02]0": "border-border",      # was border-white/20
    "border-foreground/[0.03]0": "border-foreground/30",
    "border-foreground/[0.04]0": "border-foreground/40",
    "border-foreground/[0.01]0": "border-border",      # was border-white/10
}
# Panel yang SELALU gelap (`bg-zinc-900`) — `border-border` akan hilang di sana.
FILE_OVERRIDE = {
    "scanner/UniversalScanPortal.jsx": {
        "border-foreground/[0.01]0": "border-white/10",
    },
    # Kartu panduan: ubin ikon di atas gradien; `dark:` versinya perlu lebih
    # redup daripada versi terang, jadi tidak boleh disamakan.
    "userGuide/UserGuideContent.jsx": {
        "dark:bg-foreground/[0.01]0": "dark:bg-foreground/10",
        "bg-foreground/[0.01]0":      "bg-background/70",
    },
}

FADED_RE = re.compile(r"\btext-muted-foreground/(?:50|60|70|80)\b")
MUTED_BG_RE = re.compile(r"\bbg-muted(?:/\d+)?\b")

# ── (3) JARING PENGAMAN PALSU: `localStorage.getItem('auth_token')` ──────────
# Diukur: `auth_token` TIDAK PERNAH ditulis di mana pun (`setItem('auth_token')`
# = 0 kemunculan). Kunci yang benar adalah `erp_token` (lihat `lib/apiFetch.js`
# dan `App.js:598`). Jadi 30 baris `token || localStorage.getItem('auth_token')`
# bukan cadangan — ia SELALU menghasilkan `Bearer null` begitu prop `token`
# kosong, dan layarnya memberi tahu pemakai "gagal memuat" tanpa sebab.
# Cadangan yang tidak mungkin bekerja lebih buruk daripada tidak ada cadangan:
# ia membuat orang berhenti mencurigai token sebagai penyebab.
FAKE_TOKEN_FALLBACK = "localStorage.getItem('auth_token')"
REAL_TOKEN_FALLBACK = "localStorage.getItem('erp_token')"


def main() -> int:
    apply = "--execute" in sys.argv
    files = [f for f in SRC.rglob("*.jsx") if "/ui/" not in str(f)]
    files += list(SRC.rglob("*.js"))

    n_broken = n_faded = n_files = n_token = 0
    for f in files:
        src = f.read_text(errors="ignore")
        orig = src
        rel = str(f.relative_to(SRC / "components" / "erp")) \
            if (SRC / "components" / "erp") in f.parents else str(f.relative_to(SRC))

        # (1) kelas rusak — override per berkas lebih dulu (lebih spesifik)
        ov = next((v for k, v in FILE_OVERRIDE.items() if rel.endswith(k)), {})
        for bad, good in ov.items():
            if bad in src:
                n_broken += src.count(bad)
                src = src.replace(bad, good)
        for bad, good in GLOBAL_MAP.items():
            if bad in src:
                n_broken += src.count(bad)
                src = src.replace(bad, good)

        # (2) kontras — hanya pada baris yang MEMANG ber-latar muted
        out_lines = []
        for ln in src.splitlines(keepends=True):
            if MUTED_BG_RE.search(ln) and FADED_RE.search(ln):
                n_faded += len(FADED_RE.findall(ln))
                ln = FADED_RE.sub("text-muted-foreground", ln)
            out_lines.append(ln)
        src = "".join(out_lines)

        # (3) jaring pengaman token yang tidak mungkin bekerja
        if FAKE_TOKEN_FALLBACK in src:
            n_token += src.count(FAKE_TOKEN_FALLBACK)
            src = src.replace(FAKE_TOKEN_FALLBACK, REAL_TOKEN_FALLBACK)

        if src != orig:
            n_files += 1
            if apply:
                f.write_text(src)

    print(f"{'DITERAPKAN' if apply else 'LAPORAN SAJA'}: "
          f"{n_broken} kelas rusak · {n_faded} kontras rendah · "
          f"{n_token} token palsu · {n_files} berkas")
    if not apply:
        print("jalankan dengan --execute untuk menerapkan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
