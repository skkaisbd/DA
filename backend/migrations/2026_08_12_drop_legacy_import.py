#!/usr/bin/env python3
"""2026_08_12_drop_legacy_import.py — F0.6(d): buang sisa 2 mesin impor lama.

KEPUTUSAN OWNER (2026-08-12): *"hapus total berkas + rutenya"* dan
*"tidak apa apa mulai saja, abaikan data lama"*. Berkas kode sudah dihapus
(`routes/universal_import.py`, `routes/marketing_import.py`,
`routes/universal_import_indexes.py`, 3 berkas UI). Skrip ini membersihkan
sisanya di database & disk supaya tidak ada lagi yang \"kelihatan seperti fitur\".

KOLEKSI YANG DIBUANG (semuanya milik mesin lama):
  marketing_import_sessions      sesi impor AI lama
  marketing_import_uploads       unggahan mesin impor sales lama
  marketing_import_templates     template mesin lama (diganti marketing_data_import_formats di F1)
  marketing_import_history        riwayat mesin impor sales lama
  marketing_import_*             koleksi KARANGAN dari jenis data yang tidak dikenal
                                 (mis. `marketing_import_sales_data` — 0 pembaca)
  marketing_discount_campaigns   TUJUAN SALAH; yang benar `marketing_discounts`
  marketing_sample_shipments     TUJUAN SALAH; yang benar `marketing_samples`

FOLDER DISK: /app/uploads/marketing-imports  (milik mesin lama)
             /app/uploads/marketing-data-import  ← JALUR RESMI, TIDAK DISENTUH

Pakai:
    python3 backend/migrations/2026_08_12_drop_legacy_import.py            # dry-run
    python3 backend/migrations/2026_08_12_drop_legacy_import.py --apply    # eksekusi
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

from database import get_db  # noqa: E402

EXPLICIT = [
    "marketing_import_sessions",
    "marketing_import_uploads",
    "marketing_import_templates",
    "marketing_import_history",
    "marketing_discount_campaigns",
    "marketing_sample_shipments",
]
PREFIX_INVENTED = "marketing_import_"     # koleksi karangan `marketing_import_<jenis>`
KEEP = {"marketing_import_engine", "marketing_import_schema"}   # nama modul, bukan koleksi
LEGACY_UPLOAD_DIR = Path("/app/uploads/marketing-imports")
OFFICIAL_UPLOAD_DIR = Path("/app/uploads/marketing-data-import")


async def main(apply: bool) -> int:
    db = get_db()
    names = set(await db.list_collection_names())

    targets = []
    for n in sorted(names):
        if n in EXPLICIT or (n.startswith(PREFIX_INVENTED) and n not in KEEP):
            targets.append(n)

    print("=" * 78)
    print(f"F0.6(d) buang sisa mesin impor lama — mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 78)
    if not targets:
        print("  (tidak ada koleksi legacy di database ini — bersih)")
    total = 0
    for n in targets:
        c = await db[n].count_documents({})
        total += c
        print(f"  {'DROP' if apply else 'akan di-drop':>14s}  {n:36s} {c:6d} dokumen")
        if apply:
            await db[n].drop()

    print(f"\n  total dokumen terdampak: {total}")

    # ── disk ──────────────────────────────────────────────────────────────────
    if LEGACY_UPLOAD_DIR.exists():
        n_files = sum(1 for _ in LEGACY_UPLOAD_DIR.rglob("*") if _.is_file())
        print(f"\n  folder legacy {LEGACY_UPLOAD_DIR} — {n_files} berkas "
              f"{'DIHAPUS' if apply else 'akan dihapus'}")
        if apply:
            shutil.rmtree(LEGACY_UPLOAD_DIR, ignore_errors=True)
    else:
        print(f"\n  folder legacy {LEGACY_UPLOAD_DIR} — tidak ada")

    OFFICIAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  folder resmi  {OFFICIAL_UPLOAD_DIR} — dipertahankan "
          f"({sum(1 for _ in OFFICIAL_UPLOAD_DIR.rglob('*') if _.is_file())} berkas)")

    if not apply:
        print("\n  DRY-RUN: tidak ada yang diubah. Jalankan ulang dengan --apply.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="benar-benar men-drop")
    a = ap.parse_args()
    os.chdir("/app/backend")
    raise SystemExit(asyncio.run(main(a.apply)))
