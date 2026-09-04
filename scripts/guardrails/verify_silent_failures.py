#!/usr/bin/env python3
"""INV-SILENT-01 — KEGAGALAN DIAM-DIAM di jalur STOK & UANG.

KELAS BUG YANG DIJAGA
---------------------
`except Exception: pass` pada jalur stok/uang berarti sebuah mutasi bisa GAGAL
tanpa error, tanpa log, dan tanpa ada yang tahu — lalu angkanya salah selamanya.
Ini persis kriteria gate repo ini: *"kalau pemeriksaan ini hilang, apakah UANG,
DATA, KEAMANAN, atau ALUR PRODUK bisa rusak tanpa ada yang tahu?"*

BUKTI NYATA (2026-08-07) — kenapa ini bukan aturan gaya kode:
  · `core/quarantine.py` menelan kegagalan `stock_service.release()` SEBELUM
    barang karantina dipindah/dibuang. Karena `issue()` menjaga qty **FISIK**
    (bukan qty tersedia), disposisi tetap jalan dan
    `available_quantity = qty - reserved` menjadi **NEGATIF** — tanpa satu pun
    jejak. Stok "tersedia" negatif merusak semua keputusan sesudahnya.
  · `core/stock_service.py` menelan kegagalan ROLLBACK reservasi ⇒ stok
    ter-reserve SELAMANYA (barang ada, tapi tak pernah bisa dipakai lagi).
  · `core/accessory_stock.py` & `core/quarantine.py` menelan kegagalan resolusi
    zona kanonik ⇒ stok satu material diam-diam TERBELAH ke dua id lokasi.
  · Empat titik `ensure_subledger_for_entity` (bank, pelanggan, channel, impor)
    ditelan ⇒ entitas uang tanpa akun Buku Besar; ketahuan jauh kemudian saat
    neraca tidak seimbang.

ATURAN
------
Di berkas jalur STOK/UANG (daftar `MONEY_STOCK_PATHS`), sebuah
`except ...:` yang badannya HANYA `pass` = PELANGGARAN.

Cara yang benar (pilih salah satu):
  1. `logger.error(...)` / `logger.warning(...)` lalu lanjut — bila memang
     non-fatal, TAPI jejaknya wajib ada;
  2. `raise` / `raise ... from e` — bila melanjutkan akan merusak angka;
  3. bila benar-benar kejadian NORMAL (mis. body request opsional), tulis
     `# noqa: BLE001` DENGAN alasan yang jelas — itu diterima gate ini.

Usage:
    cd /app && python scripts/guardrails/verify_silent_failures.py
    cd /app && python scripts/guardrails/verify_silent_failures.py --report-only
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BE = ROOT / "backend"
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
REPORT_ONLY = "--report-only" in sys.argv

# Berkas yang MENYENTUH stok atau uang. Sengaja daftar EKSPLISIT, bukan seluruh
# repo: gate ini harus menjaga yang mahal, bukan menjadi polisi gaya kode.
MONEY_STOCK_PATHS = [
    "core/stock_service.py",
    "core/stock_reconcile.py",
    "core/stock_schema.py",
    "core/accessory_stock.py",
    "core/accessory_valuation.py",
    "core/accessory_issue.py",
    "core/quarantine.py",
    "core/location_resolver.py",
    "core/production_qty_ledger.py",
    "core/short_shipment.py",
    "core/pr_approval.py",
    "routes/rahaza_finance.py",
    "routes/rahaza_journals.py",
    "routes/rahaza_posting.py",
    "routes/rahaza_orders.py",
    "routes/rahaza_po.py",
    "routes/rahaza_ap_from_gr.py",
    "routes/coa_auto.py",
    "routes/marketing_accounts.py",
    "routes/data_transfer.py",
    "routes/production_maklon_bridge.py",
    "routes/warehouse.py",
    "routes/dewi_accessories_purchase.py",
    "routes/dewi_accessories_stock.py",
    "routes/dewi_procurement.py",
]

EXCEPT_RE = re.compile(r"^(\s*)except\b[^\n]*:\s*(#.*)?$")


def scan(path: Path) -> list:
    """Kembalikan [(baris, indent, potongan)] untuk except yang badannya hanya `pass`."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        m = EXCEPT_RE.match(ln)
        if not m:
            continue
        indent, trailing = m.group(1), (m.group(2) or "")
        # `# noqa: BLE001` + alasan = keputusan sadar yang sudah didokumentasikan.
        if "noqa" in trailing.lower():
            continue
        # Kumpulkan badan blok except (baris ber-indent lebih dalam / komentar).
        body = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                continue
            cur = len(nxt) - len(nxt.lstrip())
            if cur <= len(indent):
                break
            body.append(nxt.strip())
        if not body:
            continue
        # Komentar diabaikan saat menilai; kalau SEMUA statement-nya `pass` → senyap.
        stmts = [b for b in body if not b.startswith("#")]
        has_noqa_comment = any("noqa" in b.lower() for b in body if b.startswith("#"))
        if stmts and all(s == "pass" for s in stmts) and not has_noqa_comment:
            out.append((i + 1, ln.strip()))
    return out


def main() -> int:
    print(f"{C}{B}\n{'=' * 74}\n  INV-SILENT-01 — kegagalan diam-diam di jalur STOK & UANG\n{'=' * 74}{X}")
    checked, offenders = 0, []
    for rel in MONEY_STOCK_PATHS:
        p = BE / rel
        if not p.exists():
            continue
        checked += 1
        for line_no, snippet in scan(p):
            offenders.append(f"{rel}:{line_no}  →  {snippet}")

    print(f"\n  {checked} berkas jalur stok/uang diperiksa — {len(offenders)} temuan")
    if offenders:
        print(f"\n  {R}{B}PELANGGARAN — kegagalan ditelan tanpa jejak:{X}")
        for o in offenders:
            print(f"    · {o}")
        print(f"\n  {Y}Perbaiki dengan: logger.error/warning(...) lalu lanjut, ATAU `raise`,{X}")
        print(f"  {Y}ATAU `# noqa: BLE001` beserta alasan bila memang kejadian normal.{X}")
        if REPORT_ONLY:
            print(f"\n  {Y}(--report-only: tidak mem-blok){X}")
            return 0
        print(f"\n  {R}{B}INV-SILENT-01 MERAH{X}\n")
        return 1
    print(f"\n  {G}{B}INV-SILENT-01 HIJAU — tidak ada kegagalan senyap di jalur stok/uang.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
