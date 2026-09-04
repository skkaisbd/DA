# HANDOFF — Penghapusan Fisik `rahaza_shipments` (Proyek Terpisah)

> Bahasa: Indonesia. Dibuat sesi #2 (lanjutan). Status: **BELUM DIKERJAKAN — rencana/blueprint saja.**
> Tujuan dokumen: memberi agent/dev berikutnya panduan LENGKAP + akurat untuk menghapus subsistem
> customer-shipping legacy `rahaza_shipments` dengan aman, termasuk apa yang berubah & bagaimana logikanya.

---

## 0. TL;DR (Ringkasan Eksekutif)

- `rahaza_shipments` adalah **subsistem Surat Jalan customer legacy hasil port "PT Rahaza"** (domain: `rahaza_orders` → `rahaza_work_orders` → `rahaza_shipments`).
- Sudah **DEPRECATED** (lihat notice di `routes/rahaza_shipments.py` baris 48–68). Penggantinya (SSOT) = **WMS Delivery Notes** → koleksi `wh_delivery_notes`, router `/api/wms/delivery-notes/*` (`routes/wms_delivery_notes.py`).
- **Seluruh domain ini DORMAN/KOSONG** di deployment saat ini:
  - `rahaza_shipments = 0`, `rahaza_orders = 0`, `rahaza_work_orders = 0`, `rahaza_customers = 0`, `rahaza_hpp_snapshots = 0`, `wh_delivery_notes = 0`.
  - Konsekuensi: penghapusan ≈ **buang dead code + referensi mati**, BUKAN migrasi data live. Risiko turun drastis, TAPI tetap butuh pengujian menyeluruh karena beberapa modul masih meng-import fungsi/menyediakan opsi UI.
- **JANGAN sentuh `rahaza_models` / `rahaza_boms` / `rahaza_sizes` / `rahaza_materials`** — koleksi ini DIPAKAI master produk internal (BOM/HPP produksi). `rahaza_models` punya 1 doc (demo). Domain "master produk internal" ≠ domain "customer-shipping".
- `customer-statement` **SUDAH dimigrasi** ke engine AR (`routes/rahaza_finance.py`, `GET /api/rahaza/customer-statement/{id}`), path lama tinggal alias tipis. Ini bukan lagi bagian dari pekerjaan.

---

## 1. Peta Arsitektur: Lama vs Baru

### 1a. Subsistem LAMA (yang akan dihapus)
```
rahaza_orders ──▶ rahaza_work_orders ──▶ rahaza_shipments (Surat Jalan customer)
                                              │  status: draft → dispatched → delivered / cancelled
                                              │  ON dispatch:
                                              │   1) auto AR invoice draft → rahaza_ar_invoices
                                              │   2) post COGS JE (rahaza_posting.post_cogs_shipment)
                                              │   3) pending OUTBOUND FG (wms_receiving.helper_create_pending_outbound_fg)
                                              │   4) notifikasi
                                              └─ PDF Surat Jalan A5 (reportlab manual)
Router: /api/rahaza/shipments/*  (routes/rahaza_shipments.py, prefix baris 46)
```

### 1b. Subsistem BARU (SSOT pengganti)
```
wh_delivery_notes (routes/wms_delivery_notes.py, prefix /api/wms/delivery-notes)
  sj_type: SJ-CMT | SJ-MAKLON | SJ-SUPPLIER | SJ-INTERNAL | SJ-ONLINE
  status:  draft → issued → received → cancelled
  endpoints: GET / , POST / , GET/PUT/DELETE /{id}, POST /{id}/issue, /receive, /cancel, GET /{id}/pdf
  PDF: pakai utils/pdf_common (branding/tanda tangan terpadu) ✅
```
Selain itu, alur produksi/maklon modern memakai:
- `buyer_shipments` (dispatch barang jadi ke buyer) — `routes/buyer_shipment.py`
- `vendor_shipments` (kirim material ke vendor CMT) — `routes/vendor_shipment.py`
- `wh_pending_movements` (outbound RM/FG) sebagai **sumber Pick List modern**
- AR: `dewi_maklon_invoices` (maklon) + `rahaza_ar_invoices` (AR engine `rahaza_finance.py`)

---

## 2. Inventaris LENGKAP Dependency `rahaza_shipments` (WAJIB dibereskan)

### A. Backend — MEMBACA/MENULIS koleksi `rahaza_shipments`
| # | File | Baris (approx) | Peran | Aksi yang diperlukan |
|---|------|-----|-------|----------------------|
| A1 | `routes/rahaza_shipments.py` | seluruh file (647 baris) | Router + CRUD + lifecycle + PDF + AR auto-draft | Hapus/arsipkan file & unmount di server.py |
| A2 | `routes/wms_picklist.py` | 188–200 | `source_type == "shipment"` → `db.rahaza_shipments.find_one` | Hapus cabang "shipment"; andalkan `pending_movement` (sudah ada, baris 216–229) |
| A3 | `routes/rahaza_reports.py` | 445–468 | `report_type == "shipment"` baca `rahaza_shipments` | Hapus cabang, ATAU repoint ke `wh_delivery_notes`/`buyer_shipments` |
| A4 | `routes/rahaza_posting.py` | 830–894 (`post_cogs_shipment`) + `_save_source_posting_result(..., "rahaza_shipments", ...)` | Posting COGS JE saat dispatch | Fungsi hanya dipanggil DARI rahaza_shipments. Hapus pemanggilan; fungsi boleh diarsip/disimpan bila mau dipakai engine baru |
| A5 | `routes/rahaza_admin_shared.py` | ~50 (registry koleksi) | Daftar koleksi rahaza (reset/backup) | Hapus entri `"rahaza_shipments"` |
| A6 | `routes/dashboard_routes.py` | 94,164,320 (komentar) | Referensi dorman (komentar saja) | Bersihkan komentar; pastikan tak ada query aktif |
| A7 | `routes/wms_receiving.py` | ~125 (komentar "Called from rahaza_shipments dispatch") + fungsi `helper_create_pending_outbound_fg` | Fungsi DIPANGGIL oleh rahaza_shipments, bukan sebaliknya | Biarkan fungsi (dipakai engine lain juga); cukup hilangkan pemanggil |
| A8 | `server.py` | 1108 (`from routes.rahaza_shipments import router...`), 1201 (`app.include_router(...)`), 858–862 (create_index koleksi) | Mount router + index | Hapus import, include_router, dan create_index |

### B. Backend — logika INTERNAL router yang perlu diputuskan (dipindah / dibuang)
Terletak di `routes/rahaza_shipments.py`:
- `POST /{sid}/status` (baris 263–398): transisi status + **4 efek samping on-dispatch**:
  1. `_create_ar_invoice_from_shipment` (426–482) → auto AR draft ke `rahaza_ar_invoices`.
  2. `post_cogs_shipment` (via rahaza_posting).
  3. `helper_create_pending_outbound_fg` (via wms_receiving) → buat pending OUTBOUND FG untuk scan-out.
  4. `publish_notification`.
- `POST /{sid}/post-cogs` (401–414): retry COGS manual.
- `GET /{sid}/pdf` + `_build_surat_jalan_pdf` (486–636): PDF A5 (versi lama, TIDAK pakai pdf_common). **Engine baru sudah punya PDF pakai pdf_common → tak perlu diporting.**
- `GET /customer-statement/{id}` (639+): **SUDAH dimigrasi** → tinggal alias.

### C. Frontend — memanggil `/api/rahaza/shipments`
| # | File | Baris | Peran | Aksi |
|---|------|-------|-------|------|
| C1 | `components/erp/WMSPickListModule.jsx` | 248 (`fetch('/api/rahaza/shipments?limit=50')`), 237 (`sourceType='shipment'`), 281, 294 (`<SelectItem value="shipment">`), 300–306 | Dropdown sumber Pick List "Shipment (FG Outbound)" | Hapus opsi "shipment"; ganti default `sourceType` ke `material_issue` atau `pending_movement`; hapus fetch shipments |
| C2 | `components/erp/RahazaARInvoicesModule.jsx` | 417 | customer-statement | **SUDAH** diarahkan ke `/api/rahaza/customer-statement/{id}` (selesai) |
| C3 | `components/erp/RahazaShipmentsModule.jsx` | file utuh | Modul UI lama | **SUDAH diarsip**: `moduleRegistry.js` 173–174 (di-comment), `prod-shipments` → redirect `wms-delivery-notes` (baris 709). Bisa hapus fisik file bila mau |

---

## 3. Detail Logika yang Berubah (per fitur)

### 3.1 Pick List Source: "shipment" → "pending_movement"
- **Sekarang**: `wms_picklist.generate_from_source(source_type="shipment", source_id)` baca `rahaza_shipments.items` untuk membuat daftar pick FG.
- **Modern**: sumber outbound FG/RM = `wh_pending_movements` (type `outbound_fg`/`outbound_rm`). Cabang `pending_movement` SUDAH ADA di `wms_picklist.py` (216–229).
- **Perubahan**: hapus cabang `shipment`. Di UI (`WMSPickListModule.jsx`) hapus `SelectItem value="shipment"` dan tambahkan opsi `pending_movement` bila belum ada di UI (endpoint sudah mendukung). Pending outbound FG dihasilkan oleh alur dispatch engine baru (lihat 3.4).

### 3.2 Laporan Shipment
- **Sekarang**: `rahaza_reports report_type="shipment"` baca `rahaza_shipments` (hasil kosong).
- **Modern**: laporan pengiriman customer = query ke `wh_delivery_notes` (semua sj_type) dan/atau `buyer_shipments` (dispatch ke buyer). 
- **Perubahan**: repoint query ke `wh_delivery_notes` (map field: `sj_number`, `sj_type`, `recipient_name`, `status`, `issued_at`, `lines[].qty`). Jika laporan ini tak dipakai UI, cukup hapus cabangnya.

### 3.3 COGS Posting on Dispatch
- **Sekarang**: `post_cogs_shipment` hitung COGS dari `rahaza_hpp_snapshots` per WO (Dr COGS material/labor/overhead, Cr FG Inventory), dipanggil saat status→dispatched.
- **Modern**: COGS untuk alur produksi/maklon di-handle finance maklon/produksi (`dewi_maklon_finance`, `rahaza_posting` untuk WO-completion `post_wip_to_fg_on_wo_complete`). Domain Rahaza dorman → posting ini tak pernah jalan.
- **Perubahan/keputusan**: karena dorman, cukup **lepas pemanggilan** dari router yang dihapus. Bila engine baru (`wh_delivery_notes` SJ-MAKLON issue) ingin auto-COGS, buat trigger baru di endpoint `POST /{sj_id}/issue` yang memanggil posting berbasis HPP snapshot maklon/produksi (pekerjaan opsional, bukan wajib untuk removal).

### 3.4 Pending OUTBOUND FG (scan-out gudang)
- **Sekarang**: rahaza_shipments dispatch memanggil `helper_create_pending_outbound_fg(source_type="shipment", ...)` → `wh_pending_movements`.
- **Modern**: alur dispatch engine baru harus yang membuat pending outbound. **CEK**: apakah `buyer_shipment` dispatch dan/atau `wh_delivery_notes` issue sudah membuat `wh_pending_movements`? Jika BELUM, tambahkan pemanggilan `helper_create_pending_outbound_fg(source_type="delivery_note" / "buyer_shipment", ...)` di endpoint issue/dispatch engine baru — supaya Pick List (3.1) tetap punya sumber outbound.
- Ini **titik integrasi paling penting** agar rantai dispatch→pending→picklist→scan-out tidak putus.

### 3.5 Auto AR Invoice on Dispatch
- **Sekarang**: dispatch → `_create_ar_invoice_from_shipment` → draft `rahaza_ar_invoices` (subtotal = Σ qty×unit_price).
- **Modern**: AR maklon = `dewi_maklon_invoices` (via modul billing maklon, sudah ada tombol Cetak PDF). AR channel/umum = `rahaza_ar_invoices` (via AR engine `rahaza_finance.py POST /ar-invoices`).
- **Perubahan/keputusan**: fitur "auto-draft AR saat kirim" bersifat opsional. Bila diinginkan pada engine baru, implement di `wh_delivery_notes POST /{sj_id}/issue` (untuk SJ-MAKLON/SJ-ONLINE) memanggil pembuatan invoice draft yang relevan. Untuk sekadar removal, cukup buang fungsi ini.

### 3.6 PDF Surat Jalan
- **Sekarang**: `_build_surat_jalan_pdf` (reportlab manual, A5, TANPA pdf_common).
- **Modern**: `wh_delivery_notes GET /{sj_id}/pdf` sudah pakai `utils/pdf_common` (branding + tanda tangan terpadu). **Tidak perlu porting** — engine baru lebih baik.

### 3.7 Customer Statement — SELESAI
- Sudah pindah ke `rahaza_finance.py`. Alias lama di `rahaza_shipments.py` bisa ikut terhapus saat file di-unmount (frontend sudah pakai path baru).

---

## 4. Rencana Eksekusi Bertahap (urutan AMAN)

> Prinsip: putuskan SEMUA consumer dulu, baru unmount router, terakhir hapus file/koleksi.

**FASE 0 — Persiapan & verifikasi kondisi**
- Konfirmasi ulang di DB target (staging & prod): `rahaza_shipments.count == 0`, `rahaza_orders == 0`, `rahaza_work_orders == 0`. Jika TIDAK 0 di prod → STOP, butuh script migrasi data ke `wh_delivery_notes` (lihat Fase 5).

**FASE 1 — Integrasi engine baru (agar rantai tak putus)**
- Pastikan alur dispatch baru (`buyer_shipment` dispatch dan/atau `wh_delivery_notes` issue) membuat `wh_pending_movements` outbound (3.4). Tambahkan bila belum.
- (Opsional) Implement auto-AR & auto-COGS di engine baru bila fitur itu ingin dipertahankan (3.3, 3.5).

**FASE 2 — Lepaskan consumer FRONTEND**
- `WMSPickListModule.jsx`: hapus opsi "shipment", set default source ke `material_issue`/`pending_movement`, hapus fetch `/api/rahaza/shipments`. (C1)
- Hapus fisik `RahazaShipmentsModule.jsx` (opsional, sudah diarsip). (C3)
- Rebuild frontend (`/app/scripts/rebuild_frontend.sh`).

**FASE 3 — Lepaskan consumer BACKEND**
- `wms_picklist.py`: hapus cabang `source_type=="shipment"`. (A2)
- `rahaza_reports.py`: hapus/relink cabang `report_type=="shipment"`. (A3)
- `rahaza_posting.py`: hapus pemanggilan `_save_source_posting_result(..., "rahaza_shipments", ...)` yang khusus shipment; putuskan nasib `post_cogs_shipment`. (A4)
- `rahaza_admin_shared.py`: hapus entri `"rahaza_shipments"`. (A5)
- `dashboard_routes.py`: bersihkan komentar. (A6)

**FASE 4 — Unmount & hapus router**
- `server.py`: hapus baris import (1108), `app.include_router(rahaza_shipments_router)` (1201), dan `create_index` koleksi (858–862). (A8)
- Hapus/arsipkan `routes/rahaza_shipments.py`. Karena alias `customer-statement` ada di sini, **pastikan** frontend sudah pakai path baru (SUDAH) sebelum menghapus.
- Restart backend, cek `tail -n 100 /var/log/supervisor/backend.*.log` untuk ImportError.

**FASE 5 — (HANYA bila prod TIDAK kosong) Migrasi data**
- Script `scripts/migrate_shipping_consolidation.py` **DISEBUT di notice TAPI TIDAK ADA** di repo (`/app/scripts/` tidak memuatnya). Harus DIBUAT:
  - Baca tiap `rahaza_shipments` → buat `wh_delivery_notes` (map: `shipment_number`→`sj_number` atau generate baru; `customer_name_snapshot`→`recipient_name`; `customer_address_snapshot`→`recipient_address`; `items[]`→`lines[]` {description=model+size, qty, unit=pcs}; `status` draft→draft, dispatched→issued, delivered→received, cancelled→cancelled; `sj_type` default SJ-MAKLON/SJ-ONLINE sesuai konteks).
  - Sediakan mode `--dry-run` (hitung & log tanpa tulis) dan mode eksekusi (idempoten: skip jika `sj_number` sudah ada / simpan `legacy_shipment_id`).
  - Setelah migrasi & verifikasi, drop koleksi `rahaza_shipments`.

**FASE 6 — Hapus koleksi**
- Bila 0 doc (kasus saat ini): `db.rahaza_shipments.drop()` aman langsung.

---

## 5. Checklist Pengujian Menyeluruh (WAJIB sebelum selesai)

Backend (curl/testing_agent):
- [ ] `GET /api/wms/picklist/source/pending_movement/{id}` bekerja; opsi "shipment" hilang tak menimbulkan error.
- [ ] `POST /api/wms/picklist` (buat pick list dari sumber modern) sukses.
- [ ] Laporan produksi/keuangan yang dulu punya report shipment tidak 500 (cabang dihapus/relink).
- [ ] `GET /api/rahaza/customer-statement/{id}` & alias lama tetap OK (backward-compat) — atau alias sengaja dihapus & frontend tetap jalan.
- [ ] `GET /api/wms/delivery-notes` + create/issue/receive/pdf jalan (engine baru).
- [ ] Alur dispatch baru → membuat `wh_pending_movements` → muncul sebagai sumber Pick List (rantai utuh).
- [ ] Tidak ada ImportError saat backend start (server.py bersih).
- [ ] REGRESI: buyer_shipments & vendor_shipments (filter business_type) tetap jalan; PDF SPP/vendor/buyer/invoice-maklon valid; portal vendor ter-scope; akses admin maklon OK.

Frontend (screenshot/testing_agent):
- [ ] WMS Pick List: dropdown sumber tampil benar tanpa "Shipment (FG Outbound)"; generate & simpan pick list sukses.
- [ ] Modul AR Invoices: tombol statement customer tetap bekerja.
- [ ] Tidak ada menu/route yang error 404/blank akibat modul shipments lama.

Rebuild wajib: `/app/scripts/rebuild_frontend.sh` (frontend = static bundle, TANPA hot reload).

---

## 6. Rollback Plan
- Semua perubahan bersifat penghapusan referensi. Simpan diff/commit terpisah per fase.
- Bila error: kembalikan `server.py` (import + include_router + index) dan file `routes/rahaza_shipments.py` dari VCS → subsistem lama aktif lagi (idempoten karena koleksi kosong).
- Alias `customer-statement` lama sengaja dipertahankan sebagai jaring pengaman; jangan dihapus sebelum yakin tak ada pemanggil eksternal.

---

## 7. Estimasi & Risiko
- **Effort**: ~0.5–1 hari (kondisi dorman/kosong). Bertambah bila prod punya data → +script migrasi + verifikasi.
- **Risiko**: MENENGAH-RENDAH. Titik paling rawan = rantai **dispatch → pending outbound → pick list** (Fase 1/3.4). Jika lupa, gudang kehilangan sumber Pick List untuk barang keluar.
- **Yang TIDAK boleh disentuh**: `rahaza_models`, `rahaza_boms`, `rahaza_sizes`, `rahaza_materials` (master produk internal + BOM/HPP produksi), `rahaza_ar_invoices` & `rahaza_customers` (AR engine masih dipakai), `rahaza_finance.py`.

---

## 8. Referensi File Cepat
- Router lama: `/app/backend/routes/rahaza_shipments.py`
- Engine baru: `/app/backend/routes/wms_delivery_notes.py`
- Pick list: `/app/backend/routes/wms_picklist.py` (baris 176–235)
- Reports: `/app/backend/routes/rahaza_reports.py` (445–486)
- Posting COGS: `/app/backend/routes/rahaza_posting.py` (830–894)
- Registry koleksi: `/app/backend/routes/rahaza_admin_shared.py` (~50)
- Mount: `/app/backend/server.py` (1108, 1201, 858–862)
- FE pick list: `/app/frontend/src/components/erp/WMSPickListModule.jsx` (237–306)
- FE AR: `/app/frontend/src/components/erp/RahazaARInvoicesModule.jsx` (417)
- FE modul lama (arsip): `/app/frontend/src/components/erp/RahazaShipmentsModule.jsx`, `moduleRegistry.js` (173–174, 709)
