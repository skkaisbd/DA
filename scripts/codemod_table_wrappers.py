#!/usr/bin/env python3
"""
codemod_table_wrappers.py
=========================
Mengganti pembungkus tabel yang memakai latar transparan (`bg-foreground/5`,
`bg-foreground/[0.03]`, dst.) menjadi token permukaan kartu resmi.

Hanya menyentuh <div> yang BENAR-BENAR membungkus <table> pada baris berikutnya,
sehingga panel subtle non-tabel tidak ikut berubah.

Jalankan:  python3 /app/scripts/codemod_table_wrappers.py [--dry]
"""
import re
import sys
from pathlib import Path

ROOT = Path("/app/frontend/src/components")
DRY = "--dry" in sys.argv

CARD = "border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]"

# pola className pembungkus yang latarnya transparan
FAINT = re.compile(
    r'border-foreground/\[?0?\.?\d*\]?|bg-foreground/\[?0?\.?\d*\]?|bg-foreground/\d+'
)

# baris <div className="..."> yang diikuti (dalam 2 baris) oleh <table
DIV_RE = re.compile(r'^(\s*)<div className="([^"]*)">\s*$')

changed_files = 0
changed_spots = 0

for path in sorted(ROOT.rglob("*.jsx")):
    lines = path.read_text().splitlines(keepends=True)
    out = list(lines)
    touched = False

    for i, line in enumerate(lines):
        m = DIV_RE.match(line.rstrip("\n"))
        if not m:
            continue
        # cek apakah <table muncul di 1-2 baris berikutnya
        lookahead = "".join(lines[i + 1: i + 3])
        if "<table" not in lookahead:
            continue
        indent, cls = m.group(1), m.group(2)
        if "card-surface" in cls:
            continue
        tokens = cls.split()
        has_faint = any(
            t.startswith("bg-foreground/") or t.startswith("border-foreground/")
            for t in tokens
        )
        if not has_faint:
            continue
        # buang token faint, sisipkan token kartu
        kept = [
            t for t in tokens
            if not (t.startswith("bg-foreground/") or t.startswith("border-foreground/"))
        ]
        if "border" not in kept:
            kept.insert(0, "border")
        if not any(t.startswith("rounded") for t in kept):
            kept.insert(0, "rounded-xl")
        new_cls = " ".join(kept + CARD.split())
        out[i] = f'{indent}<div className="{new_cls}">\n'
        touched = True
        changed_spots += 1

    if touched:
        changed_files += 1
        if not DRY:
            path.write_text("".join(out))
        print(f"  [patch] {path.relative_to(ROOT)}")

print(f"\n{'(dry-run) ' if DRY else ''}{changed_spots} pembungkus tabel di {changed_files} file diperbarui.")
