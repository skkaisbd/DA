#!/usr/bin/env python3
"""
archive_legacy_cmt_jobs.py — FASE 22 (keputusan owner: **arsipkan**, jangan hapus).

MASALAH:
  `dewi_cmt_jobs` menyimpan 4 job CMT warisan yang TIDAK menunjuk PO mana pun
  (`po_id` kosong). Job seperti ini tidak bisa ditelusuri ke pesanan, tapi tetap
  ikut menaikkan KPI Portal CMT ("job aktif", "pcs dalam proses", "overdue") —
  angka yang menyesatkan dan tak bisa ditindaklanjuti.

KEPUTUSAN: ARSIPKAN.
  · ditandai `archived=True` + alasan + waktu → DISEMBUNYIKAN dari layar & KPI
  · dokumennya TETAP di database (jejak historis, tetap bisa diekspor)
  · idempoten; `--restore` membatalkan pengarsipan

Pakai:
    python3 scripts/archive_legacy_cmt_jobs.py            # arsipkan
    python3 scripts/archive_legacy_cmt_jobs.py --dry-run  # laporan saja
    python3 scripts/archive_legacy_cmt_jobs.py --restore  # buka arsip
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle  # noqa: E402

G, Y, C, B, X = "\033[92m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
REASON = ("Job CMT warisan tanpa PO — tidak bisa ditelusuri ke pesanan. "
          "Diarsipkan (disembunyikan dari layar & KPI), dokumen tetap disimpan.")


def main() -> int:
    dry = "--dry-run" in sys.argv
    restore = "--restore" in sys.argv
    db = db_handle()

    if restore:
        r = db.dewi_cmt_jobs.update_many(
            {"archived": True},
            {"$unset": {"archived": "", "archived_at": "", "archived_reason": ""}})
        print(f"{G}arsip dibuka: {r.modified_count} job{X}")
        return 0

    q = {"po_id": {"$in": [None, ""]}, "archived": {"$ne": True}}
    rows = list(db.dewi_cmt_jobs.find(q, {"_id": 0, "id": 1, "job_number": 1,
                                          "status": 1, "cmt_partner_id": 1, "qty_total": 1}))
    print(f"{B}{C}ARSIP JOB CMT LEGACY TANPA PO — kandidat: {len(rows)}{X}")
    for r in rows:
        print(f"  · {r.get('job_number') or r['id'][:12]} status={r.get('status')} "
              f"qty={r.get('qty_total')} partner={str(r.get('cmt_partner_id'))[:12]}")
    if dry:
        print(f"{Y}dry-run — tidak ada yang diubah{X}")
        return 0
    if rows:
        db.dewi_cmt_jobs.update_many(q, {"$set": {
            "archived": True,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_reason": REASON,
        }})
    total_arch = db.dewi_cmt_jobs.count_documents({"archived": True})
    print(f"{G}{B}selesai — {len(rows)} job diarsipkan (total arsip: {total_arch}); "
          f"tidak ada dokumen yang dihapus{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
