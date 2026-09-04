#!/usr/bin/env python3
"""AUDIT UI (READ-ONLY) — daftar mana yang hanya CARD, mana yang sudah TABEL,
dan mana yang sudah punya pengalih tampilan (viewMode).

Tidak mengubah berkas apa pun.
Jalankan: cd /app && python3 scripts/_audit_marketing_ui_views.py
"""
from __future__ import annotations

import os
import re

ROOTS = [
    "frontend/src/components/erp/marketing",
    "frontend/src/components/erp",
]
INTEREST = re.compile(r"(Module|Dashboard|Page|Tab)\.jsx$")
MARKETING_HINT = re.compile(r"marketing|kol|livehost|catalog|toko|order|sales|ads|discount|"
                            r"review|complaint|sample|launch|content|budget|target", re.I)


def scan(path):
    src = open(path, encoding="utf-8", errors="ignore").read()
    has_table = bool(re.search(r"<(Table|table)[\s>]", src))
    card_grid = len(re.findall(r"grid\s+grid-cols-\d|grid-cols-\d.*gap-", src))
    map_cards = len(re.findall(r"\.map\((\w+)\s*=>\s*\(?\s*<Card", src))
    view_toggle = bool(re.search(r"viewMode|view_mode|ToggleGroup|LayoutGrid", src))
    rows = len(re.findall(r"<TableRow", src))
    api = sorted(set(re.findall(r"['\"`]/api/([a-z0-9\-_/]+)", src)))[:3]
    return {
        "table": has_table, "rows": rows, "card_grid": card_grid,
        "map_cards": map_cards, "toggle": view_toggle,
        "lines": src.count("\n") + 1, "api": api,
    }


def main():
    seen = set()
    files = []
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for f in sorted(os.listdir(root)):
            p = os.path.join(root, f)
            if not os.path.isfile(p) or not f.endswith(".jsx"):
                continue
            if not INTEREST.search(f):
                continue
            if root.endswith("/erp") and not MARKETING_HINT.search(f):
                continue
            if f in seen:
                continue
            seen.add(f)
            files.append(p)

    print("=" * 118)
    print("AUDIT TAMPILAN DAFTAR — modul Marketing / Katalog / Order")
    print("=" * 118)
    print(f"{'berkas':<44} {'baris':>6} {'TABEL':>6} {'TableRow':>9} "
          f"{'kartu.map':>10} {'grid':>5} {'pengalih':>9}  masalah")
    print("-" * 118)
    only_card, has_both, table_only = [], [], []
    for p in files:
        r = scan(p)
        name = os.path.basename(p)
        problem = ""
        if r["map_cards"] > 0 and not r["table"]:
            problem = "HANYA KARTU — sulit dibaca kalau data banyak"
            only_card.append(name)
        elif r["map_cards"] > 0 and r["table"] and not r["toggle"]:
            problem = "kartu + tabel, tanpa pengalih"
            has_both.append(name)
        elif r["table"] and r["map_cards"] == 0:
            table_only.append(name)
        print(f"{name:<44} {r['lines']:>6} {str(r['table']):>6} {r['rows']:>9} "
              f"{r['map_cards']:>10} {r['card_grid']:>5} {str(r['toggle']):>9}  {problem}")

    print("-" * 118)
    print(f"HANYA KARTU (perlu 2 tipe tampilan)   : {len(only_card)}")
    for n in only_card:
        print(f"    - {n}")
    print(f"KARTU + TABEL tanpa pengalih          : {len(has_both)}")
    for n in has_both:
        print(f"    - {n}")
    print(f"sudah TABEL saja                      : {len(table_only)}")
    print("\nPola pengalih yang SUDAH ADA di repo (boleh dicontoh, jangan bikin baru):")
    for p in ["frontend/src/components/erp/marketing/ProductLaunchModule.jsx",
              "frontend/src/components/erp/engine/BuyerShipmentModule.jsx",
              "frontend/src/components/erp/EmployeeExpenseModule.jsx"]:
        if os.path.exists(p):
            src = open(p, encoding="utf-8", errors="ignore").read()
            m = re.findall(r"viewMode[^\n]{0,70}", src)[:2]
            print(f"    {os.path.basename(p)}: {m}")
    print("    komponen tersedia: components/ui/toggle-group.jsx")


if __name__ == "__main__":
    main()
