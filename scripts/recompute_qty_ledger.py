#!/usr/bin/env python3
"""
recompute_qty_ledger.py — FASE 22. Bangun ULANG buku kuantitas job item
(`qty_declared / qty_accepted / qty_reject / qty_rework_open / qty_repaired /
qty_scrap`) dari DOKUMEN SUMBER, lalu laporkan/betulkan selisihnya.

KENAPA PERLU:
  Buku kuantitas ditulis secara INKREMENTAL (`$inc`) saat penerimaan CMT
  diselesaikan dan saat permak ditutup. Kalau dokumen penerimaan/permak dihapus
  (mis. data demo dibersihkan) atau ditulis dua kali, angkanya jadi menggantung —
  gejalanya di UI: "Lolos QC 190" padahal "Diproduksi 145" (accepted > produced),
  angka yang mustahil dan langsung merusak kepercayaan pada laporan.

SUMBER KEBENARAN (urutan hitung):
  declared = Σ baris penerimaan SELESAI QC (qty_shipped_by_cmt, atau actual+reject)
  reject   = Σ reject_qty baris tsb
  repaired = Σ qty_fixed permak `permak_sendiri` berstatus terminal berhasil
  scrap    = Σ qty_scrap permak terminal (kedua tipe)
  accepted = Σ qty_actual + repaired
  rework_open = reject − Σ terminal(qty_fixed + qty_scrap)      (≥ 0)

Pakai:
    python3 scripts/recompute_qty_ledger.py --dry-run   # hanya laporan
    python3 scripts/recompute_qty_ledger.py             # perbaiki
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, "/app/backend")
from gr_common import db_handle  # noqa: E402
from core.cmt_receipt_status import is_done as receipt_done  # noqa: E402

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
FIELDS = ("qty_declared", "qty_accepted", "qty_reject",
          "qty_rework_open", "qty_repaired", "qty_scrap",
          # SELISIH KIRIM (aturan owner 2026-08-01): dokumen = kenyataan.
          # `qty_declared` = yang BENAR-BENAR sampai; klaim vendor dipisah.
          "qty_claimed_by_vendor", "qty_short_open", "qty_short_resolved")
TERMINAL_OK = "selesai_berhasil"
TERMINAL_BAD = "gagal_buang"


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def audit_ledger(db, apply: bool = False, verbose: bool = True) -> list[dict]:
    """Bandingkan buku kuantitas dengan dokumen sumber, PER `po_item`.

    Kenapa per `po_item` dan bukan per job item: satu `po_item` bisa punya
    BEBERAPA job item (mis. job anak hasil rework `retur_ke_cmt`), dan engine
    menaruh mutasi pada job item "terbaru pada saat itu" — urutan historis yang
    tidak bisa direkonstruksi. Yang HARUS benar adalah TOTAL per po_item:
    itulah angka yang dibaca ringkasan PO, monitoring, penutupan PO, dan portal
    vendor. Perbaikan otomatis hanya dilakukan bila po_item punya SATU job item
    (kalau lebih, hanya dilaporkan supaya tidak menghapus jejak rework).

    Return: daftar temuan `{po_item_id, sku, job_items, diff:{field: (cur, target)}}`.
    """
    done_receipt_ids = {r["id"] for r in db.cmt_receipts.find({}, {"_id": 0, "id": 1, "status": 1})
                        if receipt_done(r.get("status"))}
    lines = list(db.cmt_receipt_lines.find({}, {"_id": 0}))
    permaks = list(db.dewi_cmt_permak.find({}, {"_id": 0}))
    job_items = list(db.production_job_items.find({}, {"_id": 0}))
    shorts = list(db.cmt_short_shipments.find({}, {"_id": 0})) \
        if "cmt_short_shipments" in db.list_collection_names() else []

    ji_to_poi = {ji["id"]: ji.get("po_item_id") for ji in job_items}
    # kelompokkan job item per po_item (job item tanpa po_item_id → kelompok sendiri)
    groups: dict[str, list] = {}
    for ji in job_items:
        key = ji.get("po_item_id") or f"__ji__{ji['id']}"
        groups.setdefault(key, []).append(ji)

    # baris penerimaan per kelompok
    rows_by_group: dict[str, list] = {}
    for ln in lines:
        if ln.get("receipt_id") not in done_receipt_ids:
            continue
        poi = ln.get("po_item_id") or ji_to_poi.get(ln.get("job_item_id") or "")
        key = poi or (f"__ji__{ln['job_item_id']}" if ln.get("job_item_id") else None)
        if key:
            rows_by_group.setdefault(key, []).append(ln)

    perm_by_poi: dict[str, list] = {}
    for p in permaks:
        if p.get("po_item_id"):
            perm_by_poi.setdefault(p["po_item_id"], []).append(p)

    short_by_poi: dict[str, list] = {}
    for s in shorts:
        key = s.get("po_item_id") or (f"__ji__{s['job_item_id']}" if s.get("job_item_id") else None)
        if key:
            short_by_poi.setdefault(key, []).append(s)

    findings: list[dict] = []
    for key, jis in groups.items():
        rows = rows_by_group.get(key, [])
        # SELISIH KIRIM: dokumen resmi = qty yang BENAR-BENAR sampai (actual+reject);
        # klaim vendor (`qty_claimed_by_cmt`) disimpan terpisah.
        arrived = sum(_i(ln.get("qty_actual")) + _i(ln.get("reject_qty")) for ln in rows)
        declared = arrived
        claimed = sum(_i(ln.get("qty_claimed_by_cmt")) or _i(ln.get("qty_shipped_by_cmt"))
                      or (_i(ln.get("qty_actual")) + _i(ln.get("reject_qty"))) for ln in rows)
        accepted_base = sum(_i(ln.get("qty_actual")) for ln in rows)
        reject = sum(_i(ln.get("reject_qty")) for ln in rows)
        srows = short_by_poi.get(key, [])
        short_open = sum(max(0, _i(s.get("qty_short")) - _i(s.get("qty_resolved")))
                         for s in srows if s.get("status") == "open")
        short_resolved = sum(_i(s.get("qty_resolved")) for s in srows
                             if s.get("status") != "cancelled")

        repaired = scrap = closed = 0
        for p in perm_by_poi.get(key, []):
            if str(p.get("status") or "") not in (TERMINAL_OK, TERMINAL_BAD):
                continue
            qf, qs = _i(p.get("qty_fixed")), _i(p.get("qty_scrap"))
            closed += qf + qs
            scrap += qs
            if p.get("permak_type") != "retur_ke_cmt":
                repaired += qf
        target = {
            "qty_declared": declared,
            "qty_accepted": accepted_base + repaired,
            "qty_reject": reject,
            "qty_rework_open": max(0, reject - closed),
            "qty_repaired": repaired,
            "qty_scrap": scrap,
            "qty_claimed_by_vendor": claimed,
            "qty_short_open": short_open,
            "qty_short_resolved": short_resolved,
        }
        cur = {f: sum(_i(ji.get(f)) for ji in jis) for f in FIELDS}
        if cur == target:
            continue
        if not rows and all(v == 0 for v in cur.values()):
            continue
        diff = {f: (cur[f], target[f]) for f in FIELDS if cur[f] != target[f]}
        sku = next((ji.get("sku") for ji in jis if ji.get("sku")), None)
        findings.append({"po_item_id": key, "sku": sku,
                         "job_items": len(jis), "diff": diff})
        if verbose:
            pretty = {k: f"{v[0]}→{v[1]}" for k, v in diff.items()}
            note = "" if len(jis) == 1 else f"  {Y}(dilaporkan saja: {len(jis)} job item){X}"
            print(f"  {Y}{sku or key[:14]}{X} {pretty}{note}")
        if apply and len(jis) == 1:
            db.production_job_items.update_one({"id": jis[0]["id"]}, {"$set": target})
    return findings


def main() -> int:
    dry = "--dry-run" in sys.argv
    db = db_handle()
    total_items = db.production_job_items.count_documents({})
    print(f"{B}{C}REKALKULASI BUKU KUANTITAS — {total_items} job item{X}")
    findings = audit_ledger(db, apply=not dry)
    print(f"\n{B}ringkas:{X} diperiksa={total_items} "
          f"{'perlu perbaikan=' + str(len(findings)) + ' (dry-run)' if dry else 'diperbaiki=' + str(len(findings))}")
    if not findings:
        print(f"{G}{B}HIJAU — buku kuantitas konsisten dengan dokumen sumber{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
