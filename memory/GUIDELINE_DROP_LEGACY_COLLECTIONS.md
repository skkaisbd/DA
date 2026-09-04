# PANDUAN DROP KOLEKSI LEGACY (FASE 8.8 / persiapan FASE 9)

> Dibuat: 2026-07-25 (sesi FASE 6.6 + FASE 8, environment dari repo `hanababama/da`)
> Alat: `backend/migrations/drop_legacy_collections_guided.py`
> Aturan induk: `AGENT_DEVELOPMENT_RULES.md` §5.3 Migration Protocol

## 0. PRINSIP (JANGAN DILANGGAR)

1. **Tidak ada drop langsung.** Selalu: `--audit` → `--dry-run` → **arsip** → `--execute` → verifikasi → (opsional) `--rollback`.
2. **Arsip dulu, hapus kemudian.** Skrip menyalin SELURUH dokumen ke koleksi arsip
   `legacy_archive_<nama>_<timestamp>` sebelum `drop()`. Tanpa arsip = tanpa jalan pulang.
3. **Nol konsumen adalah SYARAT, bukan asumsi.** Sebuah koleksi hanya boleh di-drop jika:
   - tidak ada endpoint/route yang membacanya (grep kode, bukan ingatan), DAN
   - tidak ada modul frontend yang memanggil endpoint tersebut, DAN
   - indeks-nya sudah dihapus dari `server.py::startup_event` (kalau tidak, koleksi akan **lahir kembali** setiap restart).
4. **Backup database dulu** (`scripts/backup.sh`) untuk drop di database produksi user.
5. **Satu grup per sesi.** Jangan gabung beberapa grup dalam satu eksekusi — kalau ada masalah,
   sulit tahu penyebabnya.
6. **Diamkan 1 minggu.** Setelah route legacy dimatikan, tunggu 1 minggu (monitoring) baru drop koleksinya.

## 1. CARA PAKAI

```bash
cd /app/backend

# 1) Lihat peta: koleksi apa saja, berapa dokumen, mana yang tak lagi dirujuk kode
python3 migrations/drop_legacy_collections_guided.py --audit

# 2) Pratinjau satu grup (tidak menulis apa pun)
python3 migrations/drop_legacy_collections_guided.py --group opname_v1 --dry-run

# 3) Eksekusi (arsip -> drop -> jurnal)
python3 migrations/drop_legacy_collections_guided.py --group opname_v1 --execute

# 4) Bila ada yang tak beres
python3 migrations/drop_legacy_collections_guided.py --logs
python3 migrations/drop_legacy_collections_guided.py --rollback <log_id>

# 5) Setelah yakin (mis. >1 bulan), bersihkan arsip
python3 migrations/drop_legacy_collections_guided.py --purge-archives --older-than-days 30
```

## 1.b HASIL EKSEKUSI & PEMBUKTIAN (2026-07-25)
- Alat ini **sudah dibuktikan bekerja** oleh `scripts/verify_fase9_legacy_drop.py` = **24 PASS / 0 FAIL**:
  data legacy tiruan disuntik lalu diuji siklus penuh — audit → dry-run (tidak menulis) → arsip
  (jumlah dokumen diverifikasi SEBELUM drop) → drop → jurnal → `--logs` → **rollback pulih 100%** →
  rollback kedua ditolak → drop ulang → pengaman grup BELUM SIAP → `--purge-archives` → regresi SSOT.
- Eksekusi nyata `--group opname_v1 --execute` di database preview: **no-op** (kedua koleksi tidak ada).
  Di DB produksi user, jalankan urutan yang sama; `server.py` TIDAK punya `create_index` untuk kedua
  koleksi itu, jadi tidak ada risiko koleksi "lahir kembali" setelah restart.

## 2. GRUP KANDIDAT & STATUS

| Grup | Koleksi | Pengganti (SSOT) | Status kesiapan |
|---|---|---|---|
| `opname_v1` | `wh_opname_sessions`, `wh_opname_items` | `wh_opname_sessions2` (Opname3 scan-driven) | **SIAP** — route GEN2 sudah dihapus di FASE 5; tidak ada konsumen |
| `warehouse_ledger` | `warehouse_stock`, `warehouse_movements`, `warehouse_putaway`, `warehouse_opname`, `warehouse_locations` | `rahaza_material_stock` + `rahaza_stock_ledger` + `wh_zones` | **SIAP** — sudah ditangani skrip khusus `migrate_drop_warehouse_ledger_legacy.py` (FASE F/F+). Grup ini hanya jaring pengaman |
| `accessory_legacy` | `acc_loans`, `acc_internal_requests` | `dewi_asset_loans` (ACC-3) + `dewi_accessory_requests` (TD-009) | **SIAP** (sejak FASE 10, 2026-07-25) — seluruh prasyarat §3 tuntas & terverifikasi `verify_fase10_accessory_legacy.py` 44/44 |
| `accessory_master_legacy` | `accessories`, `accessory_requests` | `rahaza_materials` (type=accessory) | **SUDAH DI-DROP** (Session #11.16 Phase A). Terdaftar agar audit tidak bingung bila muncul lagi |

> Di database **preview** (hasil seed baru) hampir semua koleksi di atas **tidak ada** ⇒ skrip no-op.
> Yang perlu perhatian adalah database **produksi user** yang sudah lama berjalan.

## 3. PRASYARAT GRUP `accessory_legacy` — ✅ SELESAI (FASE 10, 2026-07-25)

`acc_loans` (peminjaman aksesoris lama):
- [x] `POST /api/acc/loans` sudah **410 Gone** (ACC-3) — tidak ada pinjaman baru.
- [x] Semua pinjaman berstatus `Active` ditutup otomatis lewat
      `backend/migrations/close_legacy_acc_loans.py` (idempoten, `--dry-run`/`--execute`/`--rollback`;
      stok aksesoris dikembalikan saat penutupan, jejak `closed_by='migration_fase10'`).
- [x] Tab **Peminjaman (deprecated)** DILEPAS dari `AccessoryModule.jsx` (`acc-tab-pinjam` sudah tidak ada).
      Domain peminjaman sepenuhnya di `#asset-loans`.
- [x] `GET /api/acc/loans` & `PUT /api/acc/loans/{id}/return` juga **410** (sebelumnya masih hidup) —
      auth tetap dicek lebih dulu sehingga tanpa token balasannya 401.
- [x] Tidak ada `create_index` untuk `acc_loans` di `server.py::startup_event` (diverifikasi grep = 0).

`acc_internal_requests` (permintaan internal aksesoris lama):
- [x] SSOT = `dewi_accessory_requests` (`request_type='internal_issuance'`), dipakai dashboard & inbox.
- [x] Endpoint legacy `GET/POST /api/acc/internal-requests` + `PUT /api/acc/internal-requests/{id}`
      diubah menjadi **410**; file lama dipindah ke `backend/routes/_archive/dewi_accessories_full_backup.py`.
- [x] **Pemotongan stok** — satu-satunya alasan endpoint legacy masih dipakai — diangkat ke
      `backend/core/accessory_issue.py` (`check_availability` + `issue_accessory`) lalu dipakai
      `POST /api/dewi/accessory-requests/{id}/deliver`. Validasi SEMUA baris dulu (tidak ada
      pengeluaran separuh jalan), idempoten (deliver kedua → 400), stok kurang → 400 "stok tidak cukup".
- [x] `_enrich_movement` di 6 modul berhenti membaca koleksi legacy (baca `dewi_accessory_requests`
      & `dewi_asset_loans`).
- [x] KPI dashboard `active_loans` diganti `ready_to_deliver`; `pending_requests` membaca SSOT.
- [x] Tidak ada `create_index` untuk `acc_internal_requests` di `server.py::startup_event`.

**Bukti:** `python3 scripts/verify_fase10_accessory_legacy.py` = **44 PASS / 0 FAIL** ·
`python3 backend/migrations/drop_legacy_collections_guided.py --audit` → grup `accessory_legacy` **[SIAP]**.
Di DB preview kedua koleksi memang tidak ada ⇒ `--execute` = no-op; nilainya ada di DB produksi user.

## 4. CHECKLIST EKSEKUSI (copy saat mengerjakan)

```
[ ] backup database (scripts/backup.sh) — WAJIB utk DB produksi
[ ] --audit disimpan sebagai bukti sebelum (jumlah dokumen per koleksi)
[ ] grep konsumen = 0 (backend routes + frontend fetch)
[ ] indeks koleksi sudah dihapus dari server.py::startup_event
[ ] --dry-run: jumlah dokumen sesuai audit
[ ] --execute: arsip terbentuk (legacy_archive_*) + koleksi hilang
[ ] restart backend → koleksi TIDAK lahir kembali (kalau lahir: masih ada create_index)
[ ] smoke test layar terkait (Opname, Aksesoris, Gudang) — tidak ada 500
[ ] testing_agent_v3 regresi
[ ] catat di memory/CHANGELOG.md + plan.md
```

## 5. ALIAS FIELD LEGACY (`yarn_*`) — ✅ SUDAH DIHENTIKAN (FASE 11, 2026-07-25)

> **STATUS: SELESAI.** Alias legacy **tidak ditulis lagi** dan kunci `yarn_*` sudah dihapus dari DB
> preview. Bagian di bawah dipertahankan sebagai catatan sejarah + panduan untuk DB produksi Anda.
>
> ### Apa yang berubah
> | | Sebelum FASE 11 | Sesudah |
> |---|---|---|
> | Menulis (`mirror()`) | kanonik **+ alias** | **kanonik saja** (`WRITE_ALIASES = {}`) |
> | Response API (`with_aliases()`) | membawa dua-duanya | **kanonik saja**, kunci legacy dibuang |
> | Membaca (`read_field()`) | kanonik → legacy | **tetap** kanonik → legacy (jaring pengaman dok lama) |
> | Menerima input dari klien | kanonik atau legacy | **tetap** kanonik atau legacy (kompatibilitas) |
>
> ### Cara menjalankan di DB PRODUKSI Anda (urut, idempoten)
> ```bash
> cd /app/backend
> python3 migrations/migrate_rename_yarn_fields.py --discover      # lihat koleksi yang masih punya kunci legacy
> python3 migrations/migrate_rename_yarn_fields.py --execute       # backfill: pastikan kanoniknya ADA
> python3 migrations/migrate_rename_yarn_fields.py --drop-legacy   # dry-run
> python3 migrations/migrate_rename_yarn_fields.py --drop-legacy --yes   # eksekusi
> ```
> `--drop-legacy` punya **palang pengaman**: menolak jalan bila masih ada dokumen yang HANYA punya
> kunci legacy (mencegah kehilangan data). Hasil di preview: 6 kunci dihapus, `--discover` bersih.
>
> ### Cara MEMBALIK bila integrasi eksternal Anda ternyata masih mencari `yarn_*`
> Isi ulang `WRITE_ALIASES` di `backend/core/material_fields.py` dengan isi `LEGACY_READ_ALIASES`
> (dan `WRITE_ALIASES` di `frontend/src/lib/materialFields.js`). **Tidak perlu menyentuh satu pun
> file route** — semua penulisan sudah terpusat.
>
> ### Bukti
> `scripts/verify_fase11.py` BAGIAN 5a/5b (17 assertion) + `scripts/verify_fase66.py` §B (kontrak baru,
> 56 PASS) — termasuk assertion "DB tidak menyimpan kunci `yarn_*` lagi".

---

### (Sejarah) FASE 6.6-B — kenapa alias itu ada

FASE 6.6-B mengganti nama field internal ke bentuk netral, TAPI alias legacy tetap ditulis:

| Kanonik | Alias legacy (masih ditulis) |
|---|---|
| `composition` | `yarn_type` |
| `material_kg_per_pcs` | `yarn_kg_per_pcs` |
| `default_material_cost_per_kg` | `default_yarn_cost_per_kg` |
| `total_material_kg_per_pcs` | `total_yarn_kg_per_pcs` |
| `total_material_kg` | `total_yarn_kg` |
| `bulk_line_count` | `yarn_count` |

Syarat menghapus alias (fase terpisah) — **SEMUA SUDAH DIPENUHI di FASE 11**:
1. ✅ `grep -rn "yarn_" backend/ frontend/src/` → sisa kemunculan hanya **nama variabel lokal**,
   komentar, kunci sub-dokumen BOM legacy (`yarn_materials` — konsep BERBEDA), dan skrip migrasi.
   Tidak ada route yang menulis/membaca field `yarn_*` secara langsung; semua lewat
   `material_fields.mirror()` / `read_field()` / `with_aliases()`.
2. ⚠️ **Belum bisa diverifikasi oleh agent** — integrasi/ekspor eksternal milik user. Mitigasinya:
   endpoint **tetap MENERIMA** nama legacy sebagai input, dan `read_field()` **tetap** punya fallback
   baca. Yang berubah hanya: nama legacy tidak lagi DITULIS dan tidak lagi muncul di response.
3. ✅ `migrate_rename_yarn_fields.py` melaporkan **0 dokumen** perlu backfill → aman untuk `--drop-legacy`.

## 6. CATATAN JUJUR

- Skrip ini **tidak** menghapus indeks di `server.py` — itu perubahan kode, harus dilakukan manual
  (dan memang harus, supaya ada jejak di git).
- Rollback memulihkan **dokumen**, bukan indeks. Setelah rollback, jalankan restart backend agar
  indeks dibuat ulang oleh `startup_event` (bila baris indeksnya masih ada).
- Koleksi arsip ikut menambah ukuran database. Purge setelah periode aman.
