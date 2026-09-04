# QA / Catatan Bug — Alur Manajemen Aset (`flow-manajemen-aset`)

> Materi training (`docs/user-guide/aset/flow-manajemen-aset.md`) sengaja **bebas** tag bug.
> Seluruh observasi & tindak lanjut dicatat **di sini** (terpisah dari materi pelatihan).

Tanggal: 2026-07 · Status flow: **Done** (POC ALL PASS + audit testid LULUS + E2E UI PASS + 1 FIX + validator 10/10).

---

## AST-FIX-001 — [MEDIUM][FIXED] AssetDetailDrawer tidak menyegarkan data setelah mutasi

- **Komponen:** `frontend/src/components/erp/asset/drawers/AssetDetailDrawer.jsx`.
- **Gejala (ditemukan testing_agent_v3 iteration_86, frontend 90%):** Setelah memposting depresiasi
  atau menugaskan aset, drawer detail menampilkan NBV, akumulasi depresiasi, dan status penugasan
  yang **basi** (stale) sampai drawer ditutup lalu dibuka kembali. Dashboard menampilkan nilai benar.
- **Root cause:** Drawer merender langsung dari prop `asset` (objek list item dari parent). Setelah
  mutasi, parent memuat ulang daftar tetapi objek yang dipegang drawer tidak ikut diperbarui; drawer
  juga tidak me-`fetch` detail terbaru (`GET /api/assets/{id}`).
- **Fix:** Menambah state lokal `detail` yang disinkronkan dengan prop dan diperbarui via helper
  `reloadDetail()` (`GET /api/assets/{id}` + `GET /api/assets/{id}/assignments`) yang dipanggil
  **setelah setiap mutasi**: depresiasi (`postDepr`), penugasan (`assignAsset`), pengembalian
  (`unassign`), dan pemeliharaan (`addMaintenance`). `postDepr` tidak lagi menutup drawer sehingga
  pengguna melihat pembaruan langsung. Ditambah `data-testid`: `assign-user-id`, `assign-user-name`,
  `assign-submit-btn`, `unassign-asset-btn`.
- **Verifikasi (testing_agent_v3 iteration_87, frontend 100%):** NBV `12.000.000 → 11.762.500`,
  akumulasi `0 → 237.500`, status “Sedang Ditugaskan” muncul live, unassign mengembalikan form —
  semuanya tanpa menutup drawer. 0 error konsol.

---

## AST-OBS-002 — [LOW] Input `type="month"` & periode masa depan (2097)

- Pada uji E2E awal, testing agent kesulitan mengetik periode masa depan (`2097-01`) ke kontrol
  native `<input type="month">`; input default ke bulan berjalan. Depresiasi tetap berjalan untuk
  bulan yang dipilih.
- **Analisis:** perilaku kontrol native browser + harness pengetikan, bukan cacat backend. Untuk
  penggunaan nyata (bulan berjalan / dekat), input berfungsi normal.
- **Status:** diterima (LOW). Tidak ada perubahan kode diperlukan.

---

## AST-OBS-003 — [INFO] Grounding `/api/assets` & supplementary manifest

- **Isu tooling:** `scripts/docgen/extract_module.py` membangun `all_backend_paths` dengan memindai
  dekorator `@router.<method>` per file. Sub-paket aset (`backend/routes/asset/*.py`) memakai
  **router yang diimpor** dari `_helpers.py` (`router = APIRouter(prefix="/api/assets")`), sehingga
  pemindai tidak dapat me-resolve prefix lintas-file. Akibatnya endpoint `/api/assets` (bare) absen
  dari manifest lama → gagal F3.
- **Tindakan:** Menambahkan **supplementary manifest**
  `docs/user-guide/_manifests/asset-management.manifest.json` berisi **37 endpoint `/api/assets/*`
  nyata** (di-generate dari source + diverifikasi via `curl` live). Ini melengkapi
  `all_backend_paths` yang di-union oleh `validate_flow.py` sehingga grounding F3 akurat (bukan
  melonggarkan aturan — endpoint benar-benar ada).
- **Status:** INFO. Endpoint terverifikasi nyata (dashboard/categories/depreciate/assign live 200).

---

## AST-OBS-004 — [INFO] Modul Komplain-style: kategori & jurnal adalah master/otomatis

- Kategori aset (7 default) di-seed otomatis (`_ensure_default_categories`) saat modul dibuka/registrasi
  pertama — ini master data, bukan residu uji.
- Jurnal pembelian & depresiasi dibuat **otomatis berstatus draft** di `rahaza_journal_entries`
  (`source_module=asset_management`).
- **Status:** by-design (INFO).

---

## Cleanup DB

Fixture uji (POC self-cleanup + pembersihan pasca E2E) dihapus dari koleksi:
`dewi_assets`, `dewi_asset_depreciation`, `dewi_asset_assignments`, `dewi_asset_maintenance`,
`dewi_asset_categories`, dan `rahaza_journal_entries` (`source_module=asset_management`,
`source_ref` = nomor aset uji). Pola yang dibersihkan: nama aset berawalan `E2E-AST`/`E2E FIX`/`E2E TEST`.
DB dikonfirmasi **pristine** (koleksi aset kembali kosong seperti kondisi awal, 0 residu).
