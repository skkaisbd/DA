# SELESAI — Perbaikan UI Tabel & Warna Tombol (light mode)

Status: **DONE** (2026-07-27). Diverifikasi `testing_agent_v3` iterasi 4:
0 bug kritis, 0 bug UI, 1 temuan LOW (sudah diperbaiki juga).

## Akar masalah (terkonfirmasi)
1. **Pembungkus tabel bukan kartu** — banyak modul memakai `bg-foreground/5`
   yang di light mode ≈ 5% hitam di atas latar terang, jadi kartu "hilang".
2. **Tombol memakai warna mentah** (`bg-blue-500`) + `text-foreground`
   (near-black di atas warna pekat) — sisa refactor massal terdahulu.
3. **Kartu KPI pastel** tidak punya permukaan kartu standar.
4. **Teks pucat** (`text-emerald-300`, `text-foreground/40`, dst.) kontras < 3:1.

## Yang dikerjakan

### 1. Komponen baru
`frontend/src/components/ui/data-card.jsx`
- `DataCard`, `DataCardHeader`, `DataTableShell`, `StatCard`, `EmptyRow`
- Semua memakai token: `--card-surface`, `--glass-border`, `--shadow-card`,
  `hsl(var(--primary))`, `--radius-*`.

### 2. Baseline CSS global light-mode
`frontend/src/index.css` — blok baru ditulis **di luar `@layer`** supaya menang
atas utility Tailwind pada specificity sama. Semua di-scope `html.light`
(dark & classic tidak tersentuh):

| # | Isi |
|---|-----|
| 1 | `:is(div,section,form,td):has(> table)` → kartu putih + hairline + radius + shadow, plus aturan anti bingkai-ganda |
| 2 | Isi tabel: header ber-tint, divider baris, zebra, hover, `tfoot`, sticky head |
| 3 | Utility teks opasitas rendah (`text-foreground/30..70`, `text-muted-foreground/30..70`) → `--muted-foreground` |
| 6 | Blok pastel KPI (`bg-*-50` + `rounded-*`) diberi hairline + shadow |
| 7 | `bg-foreground/5` & `/10` dipertegas |
| 8 | Border input/select selalu terlihat |
| 9 | Idiom dark-mode bocor: `bg-black/5..30` (non-overlay), `bg-white/5..10`, `divide-white/*` |
| BUTTON-BASELINE | Tombol `bg-{blue,indigo,sky,violet,purple}-{500..800}` → `hsl(var(--primary))` + `--primary-foreground`; tombol semantik dipaksa teks putih; bug `text-foreground` di atas latar pekat |
| TEXT-BASELINE | Teks shade 200/300/400 pada 22 keluarga warna → shade 600/700 yang terbaca |

**PENTING:** selector memakai **exact word match** `[class~="bg-blue-500"]`,
BUKAN substring `[class*="bg-blue-5"]`. Substring sempat membuat
`hover:bg-blue-50` (tombol ikon edit/hapus) berlatar penuh dan ikonnya hilang.

### 3. Script
- `scripts/gen_light_button_css.py` — generator idempotent untuk blok
  BUTTON-BASELINE & TEXT-BASELINE (ditandai marker `@@LIGHT-*-BASELINE:START/END@@`).
  Jalankan ulang kalau perlu menambah keluarga warna.
- `scripts/codemod_table_wrappers.py` — mengganti pembungkus tabel bergaya
  `bg-foreground/5` ke token `--card-surface`. Sudah dijalankan:
  **37 titik di 24 file**. Aman diulang (idempotent, `--dry` tersedia).

### 4. Modul yang disentuh langsung
- `HRShiftManagementModule.jsx` — KPI memakai `StatCard`.
- `RahazaMaterialsModule.jsx` — status `Aktif` memakai `text-emerald-600 dark:text-emerald-300`.
- 24 file lain lewat codemod.

## Cara verifikasi ulang
```bash
bash /app/scripts/rebuild_frontend.sh          # ±2 menit (build statis, tanpa hot reload)
python3 /app/scripts/guardrails/check_nav_map.py   # harus HIJAU
```
Halaman referensi: `#hr-employees`, `#hr-shift-management`, `#wh-master`,
`#accessories-master-stock`, `#mgmt-access-hub`, `#cutting-orders`,
`#fin-recap`, `#marketing-accounts`, `#maklon-clients`, `#asset-management`,
`#wms-fabric-rolls`.

Ganti tema untuk cek regresi:
`localStorage.setItem('rahaza-theme','dark'|'classic'|'light')` **lalu
`page.reload()`** — mengganti hash saja tidak memicu reload.

## Catatan
- Light mode SUDAH default; `--card-surface: #FFFFFF` solid.
- Frontend = build statis, tidak ada hot reload.
- DB berisi master data saja; transaksi sengaja kosong → banyak halaman
  menampilkan empty state, itu bukan bug.
