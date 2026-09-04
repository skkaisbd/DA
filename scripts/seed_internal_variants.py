#!/usr/bin/env python3
"""
seed_internal_variants.py — FASE 8: master VARIAN internal supaya PO Produksi
internal BISA dibuat.

MASALAH (audit 2026-07-31, cacat CRIT VAR-1):
  `frontend/.../engine/ProductionPOModule.jsx` MEWAJIBKAN setiap item PO internal
  memilih Varian (Warna · Size) dari `rahaza_model_variants`. Tetapi di DB:
      rahaza_colors         = 0 dokumen
      rahaza_model_variants = 0 dokumen
  ⇒ dropdown varian selalu kosong ⇒ **PO Produksi internal tidak mungkin dibuat**
  (validasi FE menolak: "pilih Varian ... dari master data terlebih dahulu").
  Endpoint untuk membuatnya sudah ada (`POST /api/rahaza/colors`,
  `POST /api/rahaza/models/{id}/variants/generate`) — yang hilang cuma DATANYA.

Skrip ini (idempoten) memakai ENDPOINT resmi (bukan tulis mentah ke Mongo) supaya
SKU dibangun oleh SSOT `utils/variant_ssot.build_variant_sku`:
  1. Pastikan warna dasar ada (Hitam/Putih/Navy/Abu/Merah/Krem).
  2. Untuk setiap model aktif tanpa varian → generate matriks warna × size aktif.

Pakai:
    python3 scripts/seed_internal_variants.py
    python3 scripts/seed_internal_variants.py --colors "Hitam,Putih" --model DA-TS01
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

DEFAULT_COLORS = [
    ("Hitam", "BLK", "#111111"),
    ("Putih", "WHT", "#FFFFFF"),
    ("Navy", "NVY", "#1F3A93"),
    ("Abu", "GRY", "#8E8E93"),
    ("Merah", "RED", "#D0021B"),
    ("Krem", "CRM", "#EFE3C8"),
]


_COLOR_ALIAS = {"abuabu": "abu", "greyabu": "abu"}


def _norm_color_name(name: str) -> str:
    """Nama warna yang bisa dibandingkan: 'Abu-abu' dan 'Abu' warna yang SAMA."""
    s = "".join(ch for ch in (name or "").lower() if ch.isalnum())
    return _COLOR_ALIAS.get(s, s)


def login():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                            "password": os.environ.get("ADMIN_PASS", "Admin@123")}, timeout=25)
    if r.status_code == 429:
        time.sleep(12)
        return login()
    r.raise_for_status()
    return r.json()["token"]


def main():
    only_model = None
    if "--model" in sys.argv:
        only_model = sys.argv[sys.argv.index("--model") + 1]
    colors = DEFAULT_COLORS
    if "--colors" in sys.argv:
        names = [n.strip() for n in sys.argv[sys.argv.index("--colors") + 1].split(",") if n.strip()]
        colors = [(n, n[:3].upper(), "#CCCCCC") for n in names]

    tok = login()
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    print(f"{B}{C}SEED MASTER VARIAN INTERNAL{X}")

    # 1) warna
    existing = requests.get(f"{BASE}/api/rahaza/colors", headers=H, timeout=30).json()
    existing = existing.get("colors", existing) if isinstance(existing, dict) else existing
    have = {(c.get("code") or "").upper() for c in (existing or [])}
    # SESI #38 — penyemai ini dulu menyaring HANYA lewat KODE, sehingga "Hitam"
    # (BLK) tetap dibuat walau master palet sudah punya "Hitam" (HTM). Akibatnya
    # palet warna aktif kembar (INV-F30/V11 MERAH) dan tiap model melahirkan dua
    # kelompok varian yang secara fisik warnanya sama. Sekarang NAMA yang
    # menentukan: satu warna nyata = satu baris master.
    have_names = {_norm_color_name(c.get("name")) for c in (existing or [])}
    created_colors = 0
    for name, code, hexv in colors:
        if code in have or _norm_color_name(name) in have_names:
            continue
        r = requests.post(f"{BASE}/api/rahaza/colors", headers=H,
                          json={"name": name, "code": code, "hex": hexv}, timeout=30)
        if r.status_code in (200, 201):
            created_colors += 1
        elif r.status_code != 409:
            print(f"  {Y}warna {code} gagal: HTTP {r.status_code} {r.text[:120]}{X}")
    allc = requests.get(f"{BASE}/api/rahaza/colors", headers=H, timeout=30).json()
    allc = allc.get("colors", allc) if isinstance(allc, dict) else allc
    print(f"  warna: {len(allc)} total (+{created_colors} baru)")
    color_ids = [c["id"] for c in allc if c.get("active") is not False]
    if not color_ids:
        print(f"  {R}tidak ada warna aktif — abort{X}")
        return 1

    # 2) varian per model
    models = requests.get(f"{BASE}/api/rahaza/models", headers=H, timeout=30).json()
    models = models.get("models", models) if isinstance(models, dict) else models
    total_created = 0
    for m in models or []:
        if only_model and m.get("code") != only_model and m.get("id") != only_model:
            continue
        cur = requests.get(f"{BASE}/api/rahaza/models/{m['id']}/variants", headers=H, timeout=30).json()
        curv = cur.get("variants", cur) if isinstance(cur, dict) else cur
        if curv:
            print(f"  · {m.get('code')}: sudah punya {len(curv)} varian — skip")
            continue
        r = requests.post(f"{BASE}/api/rahaza/models/{m['id']}/variants/generate", headers=H,
                          json={"color_ids": color_ids}, timeout=90)
        if r.status_code in (200, 201):
            d = r.json()
            n = len(d.get("created") or []) if isinstance(d, dict) else 0
            total_created += n
            print(f"  · {m.get('code')}: {G}{n} varian dibuat{X}")
        else:
            print(f"  · {m.get('code')}: {R}gagal HTTP {r.status_code}{X} {r.text[:160]}")

    print(f"\n  {G}selesai{X} — total varian baru: {total_created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
