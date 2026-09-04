# E7 — ASET : Mesin=Aset → Depresiasi + Peminjaman (AS-IS vs TO-BE)
> Handoff §E7. GROUNDED: `routes/asset/*.py`, `rahaza_fixed_assets.py`, `rahaza_posting.py`,
> `dewi_accessories_loans.py`, `rahaza_machines` (seed). STATUS: ANALISIS.
> Catatan: Aset = **PERIFER** terhadap adopsi SOMMERVILLE (SOMMERVILLE tak punya modul aset).
> Yang relevan: (a) mesin produksi = aset → depresiasi ke Finance DA; (b) koreksi domain "Peminjaman".

## 0. TEMUAN INTI
1. **DUA sistem aset** (mirip pola D1): `dewi_assets` (Portal Manajemen Aset, `/api/assets`) vs
   `rahaza_fixed_assets` (dipakai `rahaza_posting` utk GL acquisition/depresiasi/disposal). Perlu rekonsiliasi.
2. **Mesin ≠ Aset (GAP)**: `rahaza_machines` (13×) TIDAK ter-link ke aset → depresiasi mesin produksi
   tidak otomatis. (tak ada ref machine↔asset di kode).
3. **"Peminjaman" salah-domain**: `dewi_accessories_loans.py` mengimplementasi pinjam **item aksesoris**
   dari stok aksesoris — padahal (koreksi user) "Peminjaman" seharusnya **pinjam ASET/alat** (domain Aset),
   bukan konsumsi aksesoris.

## 1. ASET — AS-IS (grounded)
| Sistem | Collection | Route | Fungsi | GL |
|---|---|---|---|---|
| Portal Aset (Flow 6 ✅) | `dewi_assets`, `dewi_asset_categories`, `dewi_asset_depreciation` | `asset/*` (`/api/assets`) | register (+jurnal beli 1500/1100), 7 kategori, depresiasi per+batch (6200/1590), assign/unassign/maintenance, disposal, transfer, predictive maintenance, scan label | ya (via assets_core + posting) |
| Fixed assets (finance) | `rahaza_fixed_assets` (22×) | `rahaza_fixed_assets.py` + `rahaza_posting.post_asset_acquisition/post_depreciation/post_asset_disposal` (`:1050,1094,1405`) | akuisisi/depresiasi/disposal → GL | ya |
> Overlap: keduanya "fixed asset + depresiasi + GL". Perlu tentukan SSOT (kemungkinan `dewi_assets`
> = UI portal, `rahaza_fixed_assets` = jalur GL lama). **AST-1**.

## 2. MESIN PRODUKSI — AS-IS
- `rahaza_machines` (13×) = master mesin (jahit/cutting) dipakai lini produksi (rahaza multi-stage / OEE).
- **Tidak** ter-registrasi sebagai aset → tak ada depresiasi otomatis mesin. GAP integrasi Produksi↔Aset↔Finance.

## 3. PEMINJAMAN — AS-IS vs koreksi user
- `dewi_accessories_loans.py` (`/loans`): pinjam **item dari stok aksesoris** (borrower_name, items,
  movement `related_loan_id`), berada di **Portal Aksesoris**.
- **Koreksi user (ecosystem map)**: "Peminjaman" = pinjam **ASET/alat** (gunting, mesin portabel, dsb) →
  domain **Manajemen Aset**, BUKAN konsumsi aksesoris habis-pakai. Aksesoris habis-pakai (kancing/label/
  ritsleting) TETAP lewat jalur BOM→request→issue (E9).
- → **Mismatch domain**: implementasi sekarang meminjamkan aksesoris, semestinya meminjamkan aset/alat.

## 4. TO-BE
| Edge | TO-BE | Catatan |
|---|---|---|
| Mesin → Aset | daftarkan `rahaza_machines` sebagai `dewi_assets` (kategori "Mesin Produksi") | aktifkan depresiasi mesin → Finance DA |
| Aset → Finance | depresiasi/akuisisi/disposal → GL DA (sudah ada) | tetap DA (bukan SOMMERVILLE) |
| Peminjaman | pindah ke domain **Aset/alat** (loan aset), pisahkan dari stok aksesoris | selaras koreksi user |
| Adopsi SOMMERVILLE | **TIDAK menyentuh aset** (SOMMERVILLE tak punya) | aset tetap DA apa adanya |

## 5. DECISION POINTS
### ⚠️ AST-1 — rekonsiliasi 2 sistem aset
`dewi_assets` (portal) vs `rahaza_fixed_assets` (GL lama). Pilih SSOT tunggal (rek: `dewi_assets` + pastikan
posting GL lewat satu jalur). [PERLU KEPUTUSAN — tapi bisa DITUNDA; tak memblokir adopsi produksi]
### ⚠️ AST-2 — mesin=aset bridge
Registrasi `rahaza_machines` → `dewi_assets` untuk depresiasi. [rek: ya, tapi PRIORITAS RENDAH — periferal]
### ⚠️ AST-3 — relokasi "Peminjaman"
Pindahkan peminjaman alat/aset ke Portal Aset; keluarkan dari Aksesoris. [rek: ya; selaras koreksi user]

## 6. RINGKAS
Aset = periferal, tetap DA, tidak terpengaruh clone SOMMERVILLE. Semua item AST-1..AST-3 = **PRIORITAS
RENDAH / bisa ditunda** setelah inti Produksi/Maklon beres. Tidak memblokir Fase 2/3.

---
*E7 selesai. Lanjut E8 (RBAC).*
