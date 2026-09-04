"""acc_baseline — SSOT TUNGGAL angka baseline data demo AKSESORIS.

═══════════════════════════════════════════════════════════════════════════════
KENAPA FILE INI ADA (FASE 13, 2026-07-26) — "Rp 9.667.750" itu RESIDU QA
═══════════════════════════════════════════════════════════════════════════════
Selama beberapa sesi, dokumen serah-terima menyatakan baseline demo aksesoris
WAJIB bernilai **Rp 9.667.750 / qty 32.220** dengan `ACC-BTN-12 = 5.020`.
Angka itu TIDAK REPRODUCIBLE: environment yang baru di-bootstrap menghasilkan
**Rp 9.663.750 / qty 32.200** dengan `ACC-BTN-12 = 5.000`.

Pelacakan seluruh penulis stok membuktikan tidak ada seeder yang pernah menulis
lebih dari 5.000 untuk `ACC-BTN-12`:
  * `backend/scripts/link_demo_bom_materials.py` → 5000
  * `backend/routes/rahaza_setup.py`             → angka 6 itu qty BARIS BOM, bukan stok
  * `backend/routes/maklon_seed.py`              → tidak menyentuh ACC-BTN-12

Selisih 20 pcs berasal dari `scripts/verify_phase_g_acc_opname.py` yang setiap
run meng-APPROVE opname pada material demo (+5 pcs `ACC-BTN-12`, -3 pcs
`ACC-LBL-01`) tanpa memulihkannya: 5.000 + 4 run × 5 = **5.020**. Residu itu lalu
dipatok sebagai "baseline sah" di `cleanup_fase10_qa.py`, sehingga alat cleanup
malah MENYUNTIKKAN persediaan fiktif (menulis 5.020 padahal seeder cuma 5.000).

Sejak FASE 13 kebocorannya sudah ditutup di penulisnya, dan angka baseline
dikembalikan ke yang REPRODUCIBLE DARI SEEDER. Semua total di bawah DIHITUNG
dari `STOCK_BASELINE` × `COST_BASELINE` (bukan angka ajaib yang diketik ulang),
supaya tidak mungkin lagi menyimpang antar berkas.

DIPAKAI OLEH
  * `scripts/cleanup_fase10_qa.py`   — deteksi & pemulihan drift
  * `tests/backend_test_fase12.py`   — assert preservasi baseline
  * `scripts/verify_fase13.py`       — sentinel drift

CARA PAKAI
    import sys; sys.path.insert(0, "/app/scripts/lib")
    from acc_baseline import STOCK_BASELINE, COST_BASELINE, TOTAL_VALUE, TOTAL_QTY
"""
from __future__ import annotations

# `__ACC__` = zona penyimpanan AKSESORIS kanonik, di-resolve saat runtime lewat
# `core.accessory_stock.get_accessory_location_id()`. JANGAN mematok id lokasi
# apa pun di sini: FASE 12 memindahkan stok dari lokasi pseudo `GDG-UTAMA-DEMO`
# ke zona kanonik, dan baseline yang mematok lokasi lama akan MEMBATALKAN
# rekonsiliasi itu saat `--apply`.
ACC_ZONE = "__ACC__"

# Hasil seed demo yang SAH & reproducible: kode → {lokasi: qty}
STOCK_BASELINE: dict[str, dict[str, float]] = {
    # 5.000 dari `link_demo_bom_materials.py` — BUKAN 5.020 (lihat catatan di atas)
    "ACC-BTN-12": {ACC_ZONE: 5000.0},
    "ACC-LBL-01": {ACC_ZONE: 4000.0},
    "ACC-DA-LBL": {ACC_ZONE: 1800.0},
    # 7 item dari `scripts/seed_acc_valuation_baseline.py`
    "DEMO-ACC-BTN-15L": {ACC_ZONE: 6800.0},   # 5.000 + 3.000 diterima − 1.200 dipakai
    "DEMO-ACC-LBL-WVN": {ACC_ZONE: 3950.0},   # 4.000 − 50 rusak
    "DEMO-ACC-ZIP-20": {ACC_ZONE: 1200.0},
    "DEMO-ACC-THR-40S": {ACC_ZONE: 150.0},
    "DEMO-ACC-HTG-KRT": {ACC_ZONE: 6000.0},
    "DEMO-ACC-ELS-25": {ACC_ZONE: 800.0},     # sengaja HPP 0 → memicu alarm "belum dinilai"
    "DEMO-ACC-SNP-BTN": {ACC_ZONE: 2500.0},   # sengaja HPP 0 → memicu alarm "belum dinilai"
}

# HPP (unit_cost) hasil seed. Dua item sengaja 0 supaya alarm "belum dinilai" hidup.
COST_BASELINE: dict[str, float] = {
    "ACC-BTN-12": 200.0,
    "ACC-LBL-01": 350.0,
    "ACC-DA-LBL": 500.0,
    "DEMO-ACC-BTN-15L": 159.375,   # rata-rata bergerak: (5.000×150 + 3.000×175) / 8.000
    "DEMO-ACC-LBL-WVN": 300.0,
    "DEMO-ACC-ZIP-20": 1250.0,
    "DEMO-ACC-THR-40S": 8500.0,
    "DEMO-ACC-HTG-KRT": 220.0,
    "DEMO-ACC-ELS-25": 0.0,
    "DEMO-ACC-SNP-BTN": 0.0,
}

# Nilai bersih `rahaza_costing_settings` sesudah seed. `overhead_rate_per_pcs`
# memang 1.000; SEMUA fallback harga HARUS 0 — kalau tidak nol, hampir pasti
# residu skrip verify (12345/77 dari fase12, 88000 dari fase66, 4321 dari fase11).
COSTING_SETTINGS_BASELINE: dict[str, float] = {
    "overhead_rate_per_pcs": 1000.0,
    "default_material_cost_per_kg": 0.0,
    "default_accessory_cost_per_unit": 0.0,
    "labor_rate_fallback_per_pcs": 0.0,
}


def _qty(code: str) -> float:
    return sum(STOCK_BASELINE[code].values())


# ── Total DITURUNKAN dari tabel di atas (bukan angka yang diketik ulang) ──────
TOTAL_ITEMS: int = len(STOCK_BASELINE)
TOTAL_QTY: float = sum(_qty(c) for c in STOCK_BASELINE)
TOTAL_VALUE: float = sum(_qty(c) * COST_BASELINE[c] for c in STOCK_BASELINE)
VALUED_ITEMS: int = sum(1 for c in STOCK_BASELINE if COST_BASELINE[c] > 0)
UNVALUED_ITEMS: int = TOTAL_ITEMS - VALUED_ITEMS
UNVALUED_QTY: float = sum(_qty(c) for c in STOCK_BASELINE if COST_BASELINE[c] <= 0)

# Jaring pengaman: kalau seseorang mengubah tabel di atas tanpa sadar, angka
# turunan ikut berubah dan uji baseline akan langsung merah — itu memang tujuannya.
# Nilai referensi environment segar (bootstrap.sh) per 2026-07-26:
#   TOTAL_ITEMS=10 · TOTAL_QTY=32.200 · TOTAL_VALUE=9.663.750
#   VALUED_ITEMS=8 · UNVALUED_ITEMS=2 · UNVALUED_QTY=3.300
assert TOTAL_ITEMS == 10, TOTAL_ITEMS
assert TOTAL_QTY == 32200.0, TOTAL_QTY
assert TOTAL_VALUE == 9663750.0, TOTAL_VALUE
assert (VALUED_ITEMS, UNVALUED_ITEMS) == (8, 2), (VALUED_ITEMS, UNVALUED_ITEMS)
assert UNVALUED_QTY == 3300.0, UNVALUED_QTY


def resolved_stock_baseline(acc_location_id: str) -> dict[str, dict[str, float]]:
    """`STOCK_BASELINE` dengan placeholder `__ACC__` diganti id lokasi nyata."""
    return {
        code: {(acc_location_id if loc == ACC_ZONE else loc): qty
               for loc, qty in plan.items()}
        for code, plan in STOCK_BASELINE.items()
    }


if __name__ == "__main__":   # `python3 scripts/lib/acc_baseline.py` → cetak ringkasan
    print("=== SSOT BASELINE AKSESORIS DEMO (diturunkan dari tabel) ===")
    for code in STOCK_BASELINE:
        print(f"  {code:<20} qty {_qty(code):>9,.0f} × HPP {COST_BASELINE[code]:>10,.3f}"
              f" = {_qty(code) * COST_BASELINE[code]:>13,.0f}")
    print(f"  {'TOTAL':<20} qty {TOTAL_QTY:>9,.0f}"
          f" {'':>21} = {TOTAL_VALUE:>13,.0f}")
    print(f"  item bernilai {VALUED_ITEMS} · belum dinilai {UNVALUED_ITEMS}"
          f" (qty {UNVALUED_QTY:,.0f})")
