# ✅ SELESAI — DIKERJAKAN & DIVERIFIKASI 2026-08-01

> **Dokumen ini sudah DIEKSEKUSI.** Semua gap A–G diimplementasi sesuai keputusan owner 2026-08-01
> (lihat §8-JAWABAN di bawah). Bukti: `tests/scenario_selisih_ssot.py` **43/43**,
> `tests/backend_test_selisih_edge_cases.py` **12/12**, `bash scripts/gate.sh` **13/13 HIJAU**,
> `python3 scripts/verify_produksi_maklon_invariants.py --audit-only` **INV-13…INV-18 hijau**,
> `scripts/recompute_qty_ledger.py --dry-run` bersih, dan UI diverifikasi langsung di browser.
> Ringkasan lengkap: entri teratas `memory/CHANGELOG.md` + bagian SESI AKTIF (2026-08-01) di `plan.md`.
>
> **§8-JAWABAN (keputusan owner):** (1) selisih CMT→DA bukan klaim otomatis — dokumen dikoreksi ke qty
> yang diterima DA, sisa kirim vendor naik lagi untuk dikirim ulang; (2) selisih buyer sama, keputusan
> finance (tanggungan CMT/DA) hanya saat PO ditutup; (3) koreksi sepihak Admin DA + notifikasi vendor,
> TANPA sanggahan; (4) TANPA batas waktu — selisih tetap `open` sampai diselesaikan.
>
> **Untuk data lama / hasil restore:** `python3 scripts/repair_selisih_ssot.py --dry-run` lalu `--apply`.

---

# HANDOFF — SELISIH KIRIM CMT→DA & DA→BUYER (Portal Produksi · Maklon · Vendor CMT)

> **Dibuat 2026-07-31** sesudah penelusuran empiris penuh (bukan baca kode saja).
> **Untuk agent berikutnya: BACA FILE INI SAMPAI HABIS SEBELUM MENYENTUH KODE.**
> Semua penelusuran sudah dilakukan dan hasilnya ada di sini — **JANGAN menelusuri ulang**
> (owner sudah kehilangan 2 sesi karena penelusuran berulang; itu tidak boleh terjadi lagi).
> Yang tersisa untuk Anda: **implementasi + verifikasi**, bukan investigasi.

---

## 0. TL;DR — apa yang harus dikerjakan

| # | Gap | Ringkas | Prioritas | Status |
|---|---|---|---|---|
| **A** | Selisih kirim tidak punya identitas | `declared 100 − lolos 90 − reject 0 = 10` hanya angka turunan; tidak ada field, tidak ada tampilan, tidak ada kewajiban vendor | **P0** | BELUM |
| **B** | Edit hasil QC setelah selesai diterima diam-diam | `PUT /api/prod/cmt-receipts/{id}/lines/{lid}` balas **200** setelah QC selesai, tapi buku kuantitas & stok TIDAK ikut → angka bercabang | **P0 (bug)** | BELUM |
| **C** | Tidak ada fitur koreksi penerimaan | Satu-satunya jalan konsisten = buat penerimaan tambahan, tapi `qty_declared` jadi dobel (110 dari 100) | **P0** | BELUM |
| **D** | PDF Surat Jalan gabungan tidak menyebut PO | Header PDF `No PO` KOSONG untuk SJ gabungan; tabel item tanpa kolom No. PO | P1 | BELUM |
| **E** | Stok FG tidak berkurang saat kirim ke buyer | Kirim 100 pcs → stok FG tetap 100; tidak ada mutasi keluar sama sekali | **P0 (bug)** | BELUM |
| **F** | Selisih buyer tidak membuka kapasitas kirim ulang | Pagar memakai `qty_shipped` dispatch sebelumnya, bukan `qty_received` (padahal komentar kode menjanjikan sebaliknya) | **P0 (bug)** | BELUM |
| **G** | Selisih buyer tanpa tindak lanjut | Hanya laporan; `close-short` manual & DITOLAK bila PO sudah `Completed` (status final) | P1 | BELUM |

Ada satu keputusan kebijakan yang **masih menunggu owner** → §8.

---

## 1. ATURAN BISNIS OWNER (ditegaskan owner 2026-07-31) — INI SUMBER KEBENARANNYA

Owner menegaskan **dua kasus yang selama ini dicampur oleh sistem**:

### Kasus 1 — REJECT (barang SAMPAI, tapi cacat)
Vendor kirim 100, DA terima 100 fisik, 10 di antaranya cacat → minta dikerjakan ulang.
* **Produksi vendor tetap 100** (barangnya nyata ada, sudah dijahit). Ini sudah benar di sistem.
* 10 pcs masuk **karantina QC**, lalu masuk siklus permak (permak sendiri / retur ke CMT).
* **Sistem sudah menangani ini dengan benar** — lihat bukti §4 Kasus B.

### Kasus 2 — SELISIH KIRIM (barang TIDAK SAMPAI) ← **YANG SALAH DIPAHAMI SESI LALU**
Vendor **mengklaim** kirim 100, tapi yang benar-benar diterima DA hanya 90. Kata owner:

> "bisa saja vendor klaim mereka kirim 100 namun aktual yang diterima itu 90, terus kalau seperti
> ini maka pengirimannya harus diulang jadi bukan 100 harus 90 … vendor harus menemukan di mana
> 10 barang ini apakah lupa terkirim, hilang, dll dan harus ada penyelesaiannya, namun dokumen
> data apa yang dikirimkan harus sesuai"

Artinya, aturan yang WAJIB dipenuhi sistem:
1. **Dokumen = kenyataan.** Deklarasi/surat jalan vendor harus **DIKOREKSI menjadi 90**, bukan
   dibiarkan tercatat 100 dengan "selisih 10" yang menggantung.
2. **10 pcs tetap KEWAJIBAN VENDOR** — statusnya "belum terkirim / harus dicari", bukan hilang dari
   sistem. Sisa kirim vendor untuk item itu **naik lagi 10 pcs**.
3. **Harus ada penyelesaian yang tercatat**: barang ditemukan → dikirim ulang (deklarasi baru), atau
   dinyatakan hilang → dokumen penyelesaian/klaim (nilai & pihak yang menanggung).
4. **Progress "terkirim ke DA" = 90**, BUKAN 100. (Yang tetap 100 hanya `produced_qty` pada
   **Kasus 1/reject** — jangan dipakai untuk membenarkan Kasus 2.)

> ⚠️ **Kesalahan sesi lalu (jangan diulang):** menyamakan Kasus 2 dengan Kasus 1 dan menyimpulkan
> "progress tetap 100 itu sudah benar". Untuk Kasus 2 itu SALAH menurut aturan owner di atas.

---

## 2. MENGHIDUPKAN ENVIRONMENT (± 3 menit, langkah pasti — jangan bereksperimen)

```bash
# 1. Repo → /app (JANGAN timpa .env platform)
cd /tmp && rm -rf da && git clone --depth 1 <repo-url> da && \
rsync -a --exclude='.env' --exclude='.git' --exclude='node_modules' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='.emergent' \
      --exclude='.bootstrap_cache' /tmp/da/ /app/

# 2. Bootstrap (env + deps + build FE + restart + seed idempoten + verifikasi login)
EMERGENT_LLM_KEY=sk-emergent-XXXX bash /app/scripts/bootstrap.sh

# 3. Data: restore snapshot backup (kalau owner mengirim file .zip backup)
#    Lewat portal: Administrasi Sistem → Backup Data → Upload ZIP → Restore
#    Lewat API:
TOKEN=$(curl -s -X POST localhost:8001/api/auth/login -H 'Content-Type: application/json' \
        -d '{"email":"admin@garment.com","password":"Admin@123"}' | jq -r .token)
curl -s -X POST localhost:8001/api/admin/backup/upload-file -H "Authorization: Bearer $TOKEN" \
     -F "file=@/path/backup.zip"          # → balas backup_id
curl -s -X POST localhost:8001/api/admin/backup/restore -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"backup_id":"<id>","confirm":true}'
```

**Kredensial:** `admin@garment.com / Admin@123` · role `{hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123`
· vendor CMT `cmtvendor@dewiaditya.id / Dewi@123` · klien maklon `klienmaklon@dewiaditya.id / Dewi@123`.
Rate-limit login 10/60 detik → **login sekali, pakai ulang token**.

**Frontend memakai BUNDLE STATIK** (`frontend/static_server.js`), bukan dev-server. Setelah mengubah
`frontend/src` **WAJIB**: `bash /app/scripts/rebuild_frontend.sh` (± 30 detik) — kalau tidak, perubahan
Anda tidak akan terlihat di preview dan Anda akan mengira kodenya tidak jalan.

**Navigasi modul di UI:** login → `window.location.hash='<module-id>'` → reload.
Modul penting: `mgmt-backup-restore`, `maklon-po` (→ `maklon-pos-engine`), `buyer-shipments`,
`cmt-receive`, `cmt-permak`, `wh-stock-schema`.

---

## 3. PETA KODE — di mana semuanya (file:line, sudah diverifikasi 2026-07-31)

### Rantai alur (CMT → DA → Buyer)
| Tahap | Endpoint | File |
|---|---|---|
| Vendor deklarasi kirim ke DA | `POST /api/buyer-shipments` (`receiver_type='da'`, dipaksa untuk vendor) | `routes/buyer_shipment.py:530` · gate `:47` |
| Auto-buat penerimaan DA dari deklarasi | helper `_auto_create_cmt_receipt_from_shipment` | `routes/buyer_shipment.py:214` |
| Penerimaan FG dari CMT (header) | `POST /api/prod/cmt-receipts` | `routes/dewi_cmt_packing.py:271` |
| Tambah baris penerimaan | `POST /api/prod/cmt-receipts/{id}/lines` | `routes/dewi_cmt_packing.py:~430` |
| **Edit baris (BUG: tanpa gerbang status)** | `PUT /api/prod/cmt-receipts/{id}/lines/{lid}` | `routes/dewi_cmt_packing.py:466` |
| Selesaikan QC (satu-satunya aksi final) | `POST /api/prod/cmt-receipts/{id}/complete-qc` (+alias `/approve`) | `routes/dewi_cmt_packing.py:533` → `_finish_receipt:557` |
| Validasi `lolos+reject ≤ dideklarasi` | — | `routes/dewi_cmt_packing.py:576-586` |
| Stok FG masuk (lolos QC) | `qty_ledger.post_fg_accepted` | `core/production_qty_ledger.py:242` |
| Buku kuantitas + karantina reject | `qty_ledger.apply_receipt_result` (idempoten via `qty_ledger_applied_at`) | `core/production_qty_ledger.py:149` |
| Antrean reject | `GET /api/prod/cmt-reject-queue` → `qty_ledger.reject_queue` | `dewi_cmt_packing.py:387` · `production_qty_ledger.py:378` |
| Permak / rework | `POST /api/dewi/cmt-permak/from-receipt-line` · `POST /api/dewi/cmt-permak/{id}/status` | `routes/dewi_cmt_permak.py:497` · `:622` |
| Hasil rework → buku kuantitas | `qty_ledger.apply_rework_outcome` | `core/production_qty_ledger.py:261` |
| SJ ke buyer (bisa GABUNGAN multi-PO) | `POST /api/buyer-shipments` (`receiver_type='buyer'` + `source_receipt_ids[]`) | `routes/buyer_shipment.py:530` |
| **Pagar qty vs penerimaan (BUG F ada di sini)** | `_validate_source_receipts_cap` | `routes/buyer_shipment.py:70` (perhitungan `:124-160`) |
| Force-edit qty dikirim (ada audit trail) | `PUT /api/buyer-shipment-items/{id}` | `routes/buyer_shipment.py:791` |
| Catat qty diterima buyer | `PUT /api/buyer-shipment-items/{id}/received` | `routes/buyer_shipment.py:862` |
| Laporan Kirim vs Diterima | `GET /api/buyer-receipt-variance` | `routes/buyer_shipment.py:927` |
| Auto-close PO saat penuh | `try_auto_close_po_on_full` | `routes/production_maklon_bridge.py:~480` |
| Tutup-kurang + nota kredit/AR | `POST /api/production-pos/{id}/close-short` → `finalize_ar_on_short_close` | `routes/production_pos.py:559` · `production_maklon_bridge.py:519` |
| Ringkasan/fulfillment PO | `GET .../fulfillment` `:1244` · `.../quantity-summary` `:1276` | `routes/production_pos.py` |
| PDF Surat Jalan buyer (**GAP D**) | `GET /api/export-pdf?type=buyer-shipment&id=…` | `routes/operations_pdf.py:488-545` |
| Quick Complete (alat demo, HATI-HATI) | `POST /api/production-pos/{id}/quick-complete` | `routes/production_pos.py:936` (step 7 **selalu** set `Completed`, `:1189`) |

### SSOT buku kuantitas — WAJIB dibaca sebelum mengubah angka apa pun
`core/production_qty_ledger.py` (429 baris). Field di `production_job_items`:
`ordered_qty · available_qty · produced_qty · qty_declared · qty_accepted · qty_reject ·
qty_rework_open · qty_repaired · qty_scrap`. Invarian yang dijaga:
`produced ≥ accepted + reject` · `reject = rework_open + repaired + scrap + undecided` ·
`accepted = Σ qty_actual + Σ permak_sendiri.qty_fixed`.
**Semua mutasi HARUS lewat modul ini** (jangan `$inc` manual di route).

### Frontend
| Layar | File |
|---|---|
| Surat Jalan Buyer (DA) — gabungan, expand per PO, input qty diterima, cetak PDF | `frontend/src/components/erp/engine/BuyerShipmentModule.jsx` (received modal `:302-320`, `downloadPDF:334`) |
| Deklarasi vendor kirim ke DA (+PDF sisi klien) | `engine/VendorBuyerShipments.jsx` (`downloadPDF:132`) |
| Portal Vendor — job & kolom Lolos QC/Reject/Rework | `engine/VendorProductionJobs.jsx` (`:223-250`, `:457-485`) |
| Bar progres multi-status | `engine/ProgressBreakdownBar.jsx` |
| Penerimaan FG dari CMT / QC | `components/erp/CMTMonitorModule.jsx`, `CMTPermakModule.jsx`, `CMTLifecycleModule.jsx` |
| Registry modul → nama modul UI | `components/erp/moduleRegistry.js` |

### Alat verifikasi yang SUDAH ADA (jangan bikin baru)
| Alat | Gunanya |
|---|---|
| `bash scripts/gate.sh` | 13 gerbang (lint, kontrak FE-BE, RBAC, dsb.) |
| `python3 scripts/verify_produksi_maklon_invariants.py` | 16 invarian; **INV-13/14/15** di `:505-571` (vendor yatim · buku kuantitas vs dokumen · SJ rework yatim) |
| `python3 scripts/recompute_qty_ledger.py --dry-run` | **Bangun ulang buku kuantitas dari dokumen sumber**; PAKAI INI sebagai mesin fitur koreksi (§7 rancangan) |
| `python3 scripts/repair_orphan_vendor_refs.py` | rapikan referensi vendor yatim |
| `python3 tests/scenario_owner_questions.py` | **Reproduksi 3 pertanyaan owner** (selisih+reject+rework, 5 PO→SJ gabungan 500, selisih buyer) |
| `python3 tests/scenario_q3_natural.py` | Alur ALAMI (tanpa Quick Complete) → close-short + AR |
| `python3 tests/verify_backup_restore_fix.py` | Regresi fitur backup/restore (15 cek) |

---

## 4. HASIL UJI EMPIRIS 2026-07-31 (angka nyata — jangan diuji ulang, cukup dibaca)

### Kasus A+B — vendor kirim 100 A + 100 B; DA terima 90 A; B 100 dgn 10 reject
PO uji `UJI-Q1-193006`, vendor "CV Jahit Mitra CMT".

| SKU | pesan | produksi vendor | dideklarasi | lolos QC | reject | rework | selisih |
|---|---|---|---|---|---|---|---|
| A | 100 | 100 | 100 | 90 | 0 | 0 | **10** |
| B | 100 | 100 | 100 | 90 | 10 | 10 | 0 |

* Stok: A `+90 @ ZNA-FG`. B `90 @ ZNA-FG` + **10 @ karantina QC**; setelah permak *retur ke CMT*
  dibuat, sistem menerbitkan **Surat Jalan REWORK `SJ-RWK-00001`** (tersimpan di dokumen permak:
  `rework_shipment_id`/`rework_shipment_number` — **bukan** di `buyer_shipments`) dan mengeluarkan
  10 pcs dari karantina. `rework_open` tetap 10 sampai vendor mengirim balik.
* `GET /production-pos/{id}/quantity-summary` → `declared 200 · accepted 180 · reject 10 ·
  reject_open 10 · reject_rate 5%` — **tidak ada** angka "selisih kirim".
* **Kasus B (reject) = SUDAH BENAR.** **Kasus A (selisih) = melanggar aturan owner §1.**

### Koreksi salah hitung (owner: "harus jadi 90, dan 10 pcs dicari vendor")
* `PUT …/lines/{lid}` `{"qty_actual":100}` pada penerimaan yang **sudah selesai QC** → **HTTP 200**,
  baris jadi 100, tetapi **buku kuantitas tetap 90 dan stok tetap 90** → data bercabang, tanpa
  peringatan. Tidak ada endpoint `reopen`/`undo`/`koreksi` (sudah dicari: TIDAK ADA).
* Penerimaan tambahan 10 pcs → `accepted 100`, stok 100 ✓ **tetapi** `qty_declared` jadi **110**.
* `qty_shipped_by_cmt` (angka klaim vendor) **TIDAK ADA di whitelist** `update_line`
  (`dewi_cmt_packing.py:472-479`) → **dokumen klaim vendor tidak bisa dikoreksi lewat API**.
  Yang bisa dikoreksi hanya deklarasi vendor di `buyer_shipment_items.qty_shipped` lewat
  `PUT /api/buyer-shipment-items/{id}` (`:791`, wajib `reason`, ada `edit_history`) — **tapi
  koreksi itu TIDAK menular ke `cmt_receipt_lines.qty_shipped_by_cmt`** yang sudah tercetak.
  ⇒ Inilah mata rantai yang harus disambung untuk memenuhi aturan owner.

### Kasus C — 5 PO × 100 pcs, tiap PO 5× kirim @20, lalu 1 SJ gabungan
* 25 penerimaan selesai QC → tiap PO `accepted 100/100`.
* Satu SJ: `SJ-BYR-202607-0001` · `consolidated=true` · `po_ids: 5` · 5 baris · **500 pcs** ✓
* `GET /api/buyer-receipt-variance` memecah per PO (5 baris) ✓
* Over-ship +1 pcs → **400** "Maksimal kirim: 0 pcs" ✓
* **GAP D:** header dokumen `po_number = ''` (kosong) & `po_id = None` untuk SJ gabungan; PDF
  (`operations_pdf.py:499-528`) mencetak `('No PO', bs.po_number)` → kosong, dan kolom tabelnya
  `No · Serial · Product · SKU · Size · Color · Ordered · Total Shipped · Remaining` → **tanpa No. PO**.

### Kasus D — buyer menerima 95 dari 100 (jalur ALAMI, PO tidak di-Quick-Complete)
* `PUT …/received {"qty_received":95}` → `variance 5`, ada `received_history` + log aktivitas ✓
* `fulfillment` → `ordered 100 · shipped 100 · received 95 · qty_short 5 · is_full false`; PO tetap
  `In Production` (tidak auto-close) ✓
* `close-short {"closed_reason":"buyer_material_shortage","confirm":true}` → PO `Closed Short`,
  `finance: {credit_note_created:false, ar_adjusted_to_received:true, ar_status:"draft"}` →
  **invoice AR draft otomatis diturunkan ke qty diterima** ✓ (nota kredit hanya dibuat bila AR
  sudah issued — `production_maklon_bridge.py:519-575`)
* **GAP E (bukti):** stok FG SKU uji **tetap 100 pcs** setelah 100 pcs dikirim ke buyer.
  `rahaza_stock_ledger` hanya berisi `add … source=cmt_receipt`; `rahaza_fg_movements` hanya `IN`.
  Tidak ada `stock_service.issue` untuk dispatch buyer di seluruh backend (sudah di-grep).
  Untuk `business_type='maklon'` jurnal COGS juga **di-skip** (`buyer_shipment.py:743-755`).
* **GAP F (bukti):** kirim ulang 5 pcs → **400** "melebihi qty terima dari CMT (100) minus yg sudah
  didispatch (100)". Pagar `_validate_source_receipts_cap` memakai `qty_shipped` dispatch sebelumnya
  (`:135-138`), padahal pagar kedua (produced-cap, `:652-654`) menyebut "cap based on ACTUAL RECEIVED
  … so shortfalls re-open capacity". **Dua pagar, dua definisi → yang ketat menang → mustahil kirim ulang.**
* **GAP G (bukti):** `close-short` pada PO berstatus `Completed` → **400 "PO sudah berstatus
  'Completed'"**; dan transisi keluar dari `Completed` juga ditolak ("status final"). Tidak ada
  koleksi klaim/dispute di DB (sudah dicek), tidak ada penyesuaian stok/progress otomatis.

---

## 5. YANG SUDAH TERBUKTI BENAR (jangan dibongkar lagi)
1. Reject → karantina → permak (sendiri/retur CMT) → SJ-RWK → buku kuantitas. ✓
2. `produced_qty` tidak turun karena reject. ✓ (hanya untuk Kasus 1!)
3. Surat jalan buyer **gabungan multi-PO** (data & UI). ✓
4. Pagar over-ship terhadap qty lolos QC. ✓
5. Pencatatan qty diterima buyer + riwayat + alasan + laporan selisih per PO. ✓
6. `close-short` → status `Closed Short` + AR draft disesuaikan / nota kredit bila AR issued. ✓
7. Idempotensi `apply_receipt_result` (`qty_ledger_applied_at`). ✓

---

## 6. JEBAKAN YANG SUDAH MEMAKAN WAKTU (hindari!)
1. **`quick-complete` selalu menutup PO** (`Completed`, status FINAL, tidak bisa keluar) → jangan
   pakai untuk menyiapkan data uji yang masih butuh dispatch/close-short. Pakai jalur alami seperti
   `tests/scenario_q3_natural.py` (PO → vendor-shipment → Received → inspeksi → job → progress).
2. **Frontend statik** → wajib `rebuild_frontend.sh` setelah ubah `src` (lihat §2).
3. **Limit file mongod = 1024** di container ini → backup/restore DB besar bisa membuat mongod
   **abort** (`WT_PANIC: Too many open files`). Sudah ada penjaga otomatis
   (`backend/utils/mongod_fdlimit.py`, dipasang di startup + APScheduler 5 menit + sebelum
   backup/restore) + `scripts/ensure_mongod_fdlimit.sh`. Cek: `python3 backend/utils/mongod_fdlimit.py --print`.
4. **Uji yang mengubah data**: SELALU `POST /api/admin/backup/create` dulu, lalu setelah uji
   `POST /api/admin/backup/restore {backup_id, confirm:true}`. Terbukti bersih (0 sisa data uji).
5. **Rate-limit login** 10/60s → satu token dipakai ulang.
6. `SJ-RWK` ada di dokumen **permak**, bukan `buyer_shipments` (sesi lalu salah cari di sini).
7. `qty_shipped_by_cmt` tidak bisa diubah lewat API (whitelist) — jangan buang waktu mencari caranya.
8. Dua sistem "vendor": `vendor_jobs`/`vendor_progress_reports` (portal vendor generik,
   `routes/vendor_portal.py`) **vs** `production_jobs`/`production_job_items` (mesin produksi,
   dipakai Portal Vendor CMT `engine/VendorProductionJobs.jsx`). Untuk selisih/QC pakai yang **kedua**.

---

## 7. RANCANGAN PERBAIKAN YANG DIUSULKAN (siap dieksekusi)

### P0-1 · GAP A+C — "SELISIH KIRIM" jadi warga kelas satu (memenuhi aturan owner §1)
**Backend**
* Tambah field buku kuantitas di `production_job_items`: `qty_short_open` (belum sampai, masih
  kewajiban vendor) dan `qty_short_resolved` + alasan penyelesaian. Tambahkan ke `LEDGER_FIELDS`
  dan `ledger_view()` (`core/production_qty_ledger.py:37,103`).
* Di `apply_receipt_result` (`:149`): hitung `short = declared − accepted − reject`; bila `> 0`
  → `qty_short_open += short` **dan** kembalikan sisa kirim vendor (jangan menaikkan `qty_declared`
  untuk barang yang tidak sampai). Rekomendasi konkret: **`qty_declared` hanya boleh berisi barang
  yang benar-benar sampai** (`accepted + reject`), sedangkan klaim vendor disimpan terpisah sebagai
  `qty_claimed_by_vendor` supaya dua angka tidak saling menimpa.
* Endpoint baru `POST /api/prod/cmt-receipts/{id}/lines/{lid}/koreksi-deklarasi`
  → set `qty_shipped_by_cmt` ke angka nyata (90), **rambatkan** ke
  `buyer_shipment_items.qty_shipped` deklarasi vendor terkait (`source_buyer_shipment_item_id`)
  memakai mekanisme audit yang sudah ada (`buyer_shipment.py:791` style: `reason` wajib +
  `edit_history`), lalu jalankan ulang perhitungan (§ pakai `scripts/recompute_qty_ledger.py`
  sebagai fungsi, jangan tulis rumus baru).
* Endpoint penyelesaian selisih `POST /api/prod/short-shipments/{id}/resolve` dengan pilihan:
  `ditemukan_dikirim_ulang` (buka kembali sisa kirim vendor) · `hilang_tanggungan_vendor`
  (klaim/potong tagihan CMT) · `hilang_tanggungan_da` (beban DA). ⚠️ **Butuh keputusan owner §8.**
* Invarian baru untuk `scripts/verify_produksi_maklon_invariants.py`:
  * **INV-16**: `qty_claimed_by_vendor = accepted + reject + qty_short_open + qty_short_resolved`
  * **INV-17**: tidak ada baris penerimaan SELESAI QC dengan `declared > accepted + reject` yang
    tidak punya catatan selisih (open atau resolved).
**Frontend**
* Kolom **"Belum sampai"** + tombol **"Koreksi deklarasi"** di layar penerimaan FG dari CMT.
* Portal Vendor (`engine/VendorProductionJobs.jsx`): kolom **"Belum sampai / harus dicari"** +
  banner kewajiban vendor; sisa kirim harus naik lagi setelah koreksi.
* Kartu KPI + alarm bila `qty_short_open > 0` (dashboard produksi & PO-360).
**Kriteria terima:** skenario owner (kirim 100, terima 90) menghasilkan: dokumen deklarasi 90,
`qty_short_open` 10, sisa kirim vendor 10, tidak ada angka bercabang, INV-16/17 hijau,
`recompute_qty_ledger.py --dry-run` bersih.

### P0-2 · GAP B — tutup lubang edit setelah QC selesai
* `dewi_cmt_packing.py:466 update_line` → tolak (**409**) bila status penerimaan sudah `ST_DONE`,
  dengan pesan yang mengarahkan ke fitur koreksi resmi.
* Fitur koreksi resmi (`POST …/lines/{lid}/koreksi-hasil-qc`): balik stok FG selisihnya lewat
  `core/stock_service` (bukan tulis mentah), perbarui buku kuantitas via recompute, tulis
  `koreksi_history` + log aktivitas, dan **idempoten**.
* Uji regresi: `tests/scenario_owner_questions.py` bagian Q1-b harus berubah dari "DATA TIDAK
  SINKRON" menjadi "ditolak 409 + koreksi resmi konsisten".

### P0-3 · GAP E — stok FG harus berkurang saat kirim ke buyer
* Di `create_buyer_shipment` (`buyer_shipment.py:530`) untuk `receiver_type='buyer'`: keluarkan
  stok FG per baris lewat `core/stock_service.issue` (lokasi FG dari
  `qty_ledger.resolve_fg_location_id`), catat `rahaza_fg_movements` `OUT` + ref surat jalan,
  **idempoten per `dispatch_seq`** (pola sama seperti COGS posting).
* Perlakuan koreksi/force-edit & pembatalan SJ harus membalik mutasi (jangan sampai stok minus).
* Alat perbaikan data lama: `scripts/repair_fg_stock_from_buyer_shipments.py --dry-run` →
  hitung stok FG seharusnya (`Σ accepted − Σ dikirim ke buyer + Σ retur`), laporkan & betulkan.
* Invarian **INV-18**: untuk setiap SKU FG, `stok_fisik = Σ accepted − Σ qty_shipped_buyer
  + Σ retur_buyer − Σ scrap` (toleransi 0).

### P0-4 · GAP F — kapasitas kirim ulang harus mengikuti qty DITERIMA
* `_validate_source_receipts_cap` (`:124-160`): ganti `dispatched_by_key` supaya memakai
  **qty efektif diterima** (`qty_received` bila diisi, else `qty_shipped`) — samakan dengan
  definisi pagar produced-cap (`:652-654`) agar hanya ada SATU definisi.
* Uji: setelah buyer terima 95 dari 100, kirim ulang 5 pcs harus **berhasil**; kirim 6 pcs ditolak.

### P1-5 · GAP D — PDF Surat Jalan gabungan
* `operations_pdf.py:488-545`: tambah kolom **No. PO** di tabel item; header menampilkan **daftar
  semua PO** (`bs.po_ids` → nomor PO) saat `consolidated`; tambah **subtotal per PO** + total besar.
* Uji: PDF SJ gabungan 5 PO memuat 5 nomor PO & subtotal masing-masing (ekstrak teks PDF).

### P1-6 · GAP G — selisih buyer wajib punya tindak lanjut
* Izinkan penyesuaian pasca-`Completed`: tambah transisi `Completed → Closed Short` (atau endpoint
  `POST /production-pos/{id}/adjust-short` khusus) — sekarang `Completed` final sehingga selisih yang
  ketahuan belakangan mentok.
* Saat `qty_received < qty_shipped`: otomatis buat **catatan selisih buyer** (dokumen sendiri:
  nomor, PO, item, qty, alasan, status penyelesaian) + notifikasi ke Admin & Finance; tautkan ke
  nota kredit/AR bila diputuskan menjadi pengurang tagihan.

---

## 8. KEPUTUSAN OWNER YANG MASIH DITUNGGU (tanyakan SEBELUM mengoding P0-1 & P1-6)
1. **Selisih kirim CMT→DA (barang tidak sampai)** ditanggung siapa secara default:
   (a) klaim/potong tagihan vendor CMT · (b) beban DA (hilang di jalan) · (c) pilih manual per kejadian?
2. **Selisih terima buyer (DA→buyer)**: (a) klaim ke vendor CMT · (b) beban DA · (c) manual?
3. Apakah **koreksi deklarasi** boleh dilakukan sepihak oleh Admin DA, atau perlu **persetujuan
   vendor** di portal vendor (dua pihak sepakat) sebelum angka resmi berubah?
4. Batas waktu penyelesaian selisih (mis. 7 hari) sebelum otomatis jadi klaim?

---

## 9. DEFINITION OF DONE sesi berikutnya
- [ ] P0-1 … P0-4 selesai + invarian INV-16/17/18 ditambahkan dan **hijau**
- [ ] `python3 tests/scenario_owner_questions.py` → semua "TEMUAN" untuk Q1/Q3 hilang
- [ ] `python3 tests/scenario_q3_natural.py` → kirim ulang 5 pcs berhasil; stok FG turun 100→0
- [ ] `bash scripts/gate.sh` 13/13 · `verify_produksi_maklon_invariants.py` semua hijau ·
      `recompute_qty_ledger.py --dry-run` bersih
- [ ] UI diverifikasi di browser (bukan hanya API) untuk: koreksi deklarasi, kolom "belum sampai",
      PDF SJ gabungan, kirim ulang selisih
- [ ] `memory/CHANGELOG.md`, `memory/BUG_REGISTRY.md`, `plan.md` diperbarui + file ini ditandai SELESAI
- [ ] Snapshot backup dibuat sebelum uji & DB dipulihkan sesudahnya (0 sisa data `UJI-`)

---

## 10. CATATAN PROSES UNTUK AGENT BERIKUTNYA (owner sudah 2× kehilangan waktu)
* **Jangan menelusuri ulang** apa pun yang sudah tertulis di sini. Kalau ragu, buka file:line yang
  sudah dicantumkan — bukan `grep` dari nol.
* **Jangan mengklaim "sudah fixed" tanpa bukti angka** dari skrip/DB/browser. Owner menguji ulang.
* **Jangan mencampur Kasus 1 (reject) dengan Kasus 2 (selisih kirim)** — itu akar kesalahpahaman
  sesi ini.
* Balas owner **dalam Bahasa Indonesia**, ringkas, dengan angka.
