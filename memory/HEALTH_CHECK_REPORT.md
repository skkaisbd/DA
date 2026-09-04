# HEALTH CHECK REPORT — snapshot 2026-07-25 (akhir sesi FASE 6.6 + FASE 8)

## Layanan
```
backend      RUNNING   /api/health → {status:ok, db:connected}
frontend     RUNNING   STATIC BUNDLE (node static_server.js) → HTTP 200
mongodb      RUNNING   182 koleksi (+1 baru: rahaza_material_cost_history dibuat saat ada valuasi)
```
- Frontend build: `yarn build` = **Compiled successfully**, 0 warning.
- Lint FE (`npx eslint`, file sesi ini): **0 error** (sisa warning = pola lama `no-unused-vars` di moduleRegistry).
- ruff (file baru sesi ini): **0 issue**. Sisa issue di `core/helpers.py`, `core/location_resolver.py`,
  `core/accessory_stock.py` = baseline lama, BUKAN regresi.

## Login (rate limit 10 req/60 detik per IP — login sekali, reuse token)
| Akun | Hasil |
|---|---|
| `admin@garment.com` / `Admin@123` | 200 |
| `hr@ · finance@ · spv@ · gudang@ · maklon@ dewiaditya.id` / `Dewi@123` | 200 semua |
| `packing@dewiaditya.id` / `Dewi@123` (tim_packing) | tersedia untuk uji negatif scrap |

## Baseline data (setelah semua artefak uji dibersihkan)
- `rahaza_material_stock`: **5 baris, semuanya Skema A (kanonik)** — `/api/wms/stock-schema/health` → `healthy: true`,
  total on-hand 11.550.
- Aksesoris: 3 item (`ACC-LBL-01` Rp350 × 4.000 · `ACC-BTN-12` Rp200 × 5.000 · `ACC-DA-LBL` Rp500 × 1.800) —
  nilai persediaan **Rp 3.300.000**, `unvalued_items` 0.
- `rahaza_costing_settings.GLOBAL`: `default_material_cost_per_kg` = `default_yarn_cost_per_kg` = 0.
- 0 artefak `QA66-*` / `QA8-*` / `QAUI-*` / `TEST-F6*` tersisa (termasuk 1 `rahaza_grn_inspections` yatim
  yang dihapus manual; `scripts/cleanup_test_f6.py` belum mencakupnya).

## Skrip verifikasi (semua isolated + self-clean)
| Skrip | Hasil |
|---|---|
| `scripts/verify_fase66.py` | **48 PASS / 0 FAIL** (rekonsiliasi skema A/B/C + alias field) |
| `scripts/verify_fase8.py` | **48 PASS / 0 FAIL** (valuasi HPP aksesoris + jurnal) |
| `scripts/verify_acc123.py` | **62 PASS / 0 FAIL** (regresi FASE 7) |
| `scripts/verify_phase6_quarantine.py` | **48 PASS / 0 FAIL** (regresi karantina; jalankan `cleanup_test_f6.py --apply` setelahnya) |
| `scripts/verify_fase8plus.py` | **24 PASS / 0 FAIL** (alarm "belum dinilai" + rapor valuasi Excel/PDF) |
| `scripts/verify_fase9_legacy_drop.py` | **24 PASS / 0 FAIL** (siklus penuh alat drop koleksi legacy) |
| `testing_agent_v3` | iteration_169 (100%/0 critical) + iteration_170 (backend 100%/0 critical) |

## Verifikasi UI manual (Playwright, oleh main agent)
Rekonsiliasi dari UI (Pratinjau → konfirmasi → Terapkan → banner sehat → Rollback) · Set HPP (100→250) ·
validasi Scrap tanpa alasan (pesan merah inline, modal tetap terbuka) · Scrap 5 pcs (nilai Rp 1.250 + JE nyata) ·
Terima 95 @400 (HPP 250→325 rata-rata bergerak + JE) · kartu stok bernilai + riwayat HPP · form master material
menyimpan Komposisi · BOM matriks "Bahan /pcs" + "1 bahan · 1 aksesoris" · HPP settings simpan/reload ·
14 modul Portal Gudang + 6 tab hub Stok & Akurasi = 0 crash, 0 "Pilih Portal", 0 page error.

## Catatan
- `wh-dashboard` BUKAN module id yang valid — id benar `warehouse-dashboard` (hash tak dikenal mendarat di
  "Pilih Portal", perilaku existing).
- Koleksi legacy kandidat drop TIDAK ADA di DB preview ⇒ `drop_legacy_collections_guided.py --audit` no-op
  (gunanya di DB produksi user).

## Artefak testing agent yang HARUS dibersihkan manual (2026-07-25)
`testing_agent_v3` iteration_170 melaporkan `data_changes: None` tetapi meninggalkan 3 material `ZZTEST-*`,
3 baris `rahaza_material_stock`, 6 dokumen `notifications`, 2 JE + 4 baris jurnal. Sudah dibersihkan; DB
kembali ke baseline (Rp 3.300.000 · 5 baris stok Skema A · 0 notifikasi `stock`).
**Aturan praktis: SELALU verifikasi DB sendiri setelah memanggil testing agent.**
