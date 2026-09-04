# AUDIT FORENSIK — PRODUKSI · MAKLON · CMT/VENDOR · FINANCE · GUDANG
**Tanggal:** 2026-07-31 · **Metode:** peta AST collection R/W + inspeksi dokumen nyata + **uji alur end-to-end lewat HTTP** (bukan cek HTTP 200)
**Alat (bisa dijalankan ulang):**
- `python3 scripts/audit_maklon_production_ssot.py --json` → peta penulis/pembaca per collection
- `python3 scripts/audit_e2e_produksi_maklon_cmt.py` → 20 temuan berbukti angka, bersih-bersih otomatis (`docs/AUDIT_E2E_FINDINGS.json`)

---

## 0. Kesimpulan satu paragraf

Sistem ini punya **dua mesin PO yang berdiri sendiri** (`production_pos` vs `dewi_maklon_pos`), **tiga model pekerjaan vendor** (`production_jobs`, `vendor_jobs`, `dewi_cmt_jobs`), dan **dua master vendor CMT** (`vendor_partners` vs `dewi_cmt_partners`). Portal Maklon menulis PO **asli** ke collection yang secara arsitektur adalah **mirror**, sehingga PO tersebut tidak bisa masuk alur produksi sama sekali — tetapi tetap menampilkan status "in_production/completed". Di ujung lain, **informasi reject tidak punya rumah**: `production_job_items` tidak punya field reject, sehingga 10 pcs reject dari 100 pcs hanya hidup sebagai angka di baris penerimaan, tidak pernah kembali ke PO, ke portal vendor, ke karantina, maupun ke pipeline permak. Permak yang diselesaikan **tidak berefek apa pun**. Inilah sebabnya sistem terasa "berantakan": tiap layar benar secara teknis (HTTP 200) tetapi **angka antar layar tidak pernah bertemu**.

---

## 1. PETA SSOT — AS IS (yang benar-benar ada di kode & data)

### 1.1 Purchase Order — DUA mesin
| | `production_pos` + `po_items` | `dewi_maklon_pos` (items embedded) |
|---|---|---|
| Penulis | `production_pos.py`, `production_execution.py`, `production_internal_adapter.py`, `production_maklon_bridge.py`, `vendor_shipment.py`, `maklon_seed.py` | `dewi_maklon_pos.py`, `dewi_maklon_billing.py`, `dewi_maklon_finance.py`, `production_maklon_bridge.py`, `maklon_seed.py` |
| UI | Portal Produksi → `engine/ProductionPOModule.jsx` | Portal Maklon → `MaklonPOModule.jsx` |
| Varian | **ADA** picker varian (maklon: `buyer_catalog.variants[]`; internal: `rahaza_model_variants`) + WAJIB | **TIDAK ADA** — `color`/`size` free-text (`MaklonPOModule.jsx:106-111`) |
| Bisa masuk produksi | Ya (SJ material → inspeksi → job → progress) | **Tidak** |
| Peran arsitektural sebenarnya | **SSOT** | **MIRROR** (`mirror_of:'production_pos'`, `production_po_id`) — dibuat oleh `production_maklon_bridge.py:104-150` |

**Data nyata:** 11 dokumen `dewi_maklon_pos` → **1 mirror sah**, **10 PO asli yatim** (tanpa `production_pos`), **7 di antaranya berstatus `in_production` / `completed` / `invoiced`** padahal NOL job, NOL kirim material, NOL penerimaan.

### 1.2 Pekerjaan vendor — TIGA model
| Model | Collection | Penulis | Isi nyata | Dipakai UI |
|---|---|---|---|---|
| Engine (benar) | `production_jobs` + `production_job_items` + `production_progress` | `production_execution.py` | 3 / 4 / 4 | `engine/VendorPortalApp.jsx` (portal vendor saat login `cmt_vendor`), `engine/VendorProgress.jsx` |
| Portal vendor lama | `vendor_jobs` + `vendor_progress_reports` | `vendor_portal.py` | **0 / 0** | `VendorPortalModule.jsx` (module id `vendor-portal`) |
| Lifecycle CMT | `dewi_cmt_jobs` + `dewi_cmt_progress` | seed saja | 4 / **collection tidak ada** | `CMTLifecycleModule.jsx` via `/api/dewi/cmt/lifecycle` |

- `vendor_progress_reports` **punya `qty_reject`** — satu-satunya tempat reject per hari — tapi collection-nya mati dan tidak pernah menyentuh PO/dispatch/tagihan.
- `dewi_cmt_jobs` **tidak punya `po_id`/`po_number`/`vendor_id`** (field-nya: `cmt_partner_id`, `cutting_batch_id`, `batch_code`, `qc_pass_qty`, `qc_reject_qty`) → pekerjaan CMT tidak bisa dilacak ke PO mana pun.

### 1.3 Master vendor CMT — DUA, tidak beririsan
`vendor_partners` (1 dok: `mk-vendor-demo-1`) ⟂ `dewi_cmt_partners` (4 dok: CMT Pak Heru/Bu Warsini/Mas Joko/Bu Sri) — **irisan id = 0**.
Akibat nyata: `dewi_cmt_payments.cmt_partner_id` menyimpan id dari **dua master berbeda** (dokumen baru `mk-vendor-demo-1` dari `vendor_partners`, dokumen lama id `dewi_cmt_partners`) ⇒ pengelompokan tagihan per CMT di Portal CMT salah. Skema jumlah juga campur: `net_amount` (baru) vs `total_amount` (lama).

### 1.4 Alur FG dari CMT & dispatch buyer (yang SUDAH benar strukturnya)
```
vendor: POST /api/buyer-shipments (receiver_type='da')      ← deklarasi kirim ke DA
      → auto draft cmt_receipts (TERBUKTI JALAN)
DA    : PUT  /api/prod/cmt-receipts/{id}/lines/{lid}         ← qty_actual 90, reject_qty 10
      → POST submit → POST approve
      → stok FG += 90 (rahaza_material_stock, TERBUKTI, delta tepat 90)
      → AP CMT dewi_cmt_payments: total_pcs 90, total_rejected 10, net_amount 1.620.000 (TERBUKTI BENAR)
DA    : POST /api/buyer-shipments (receiver_type='buyer', source_receipt_ids=[...])  ← TERBUKTI JALAN
```
Jadi **rangka alurnya benar** dan `dispatch ke buyer` **memang seharusnya** bersumber dari penerimaan (`cmt_receipts`) — bukan salah konsep. Yang salah adalah **UX-nya** (3 status + halaman terpisah), **reject tidak diteruskan**, dan **konsolidasi multi-PO belum pernah menghasilkan dokumen** + dokumen lama tidak punya field konsolidasi.

### 1.5 Permintaan material/komponen ke CMT — LIMA permukaan
| Permukaan | Collection | Isi | Menunjuk PO? | Menunjuk vendor? | Dari inspeksi? |
|---|---|---|---|---|---|
| "Komponen Kurang" | `dewi_cmt_component_requests` | 0 | ? (kosong) | ? | tidak |
| "Kirim Material ke CMT" (WMS) | `wh_cmt_dispatches` | **collection tidak ada** | — | — | — |
| Permintaan material vendor (auto dari inspeksi aksesoris kurang) | `material_requests` | **collection tidak ada** | ya (kode) | ya | ya |
| "Permintaan Tambahan" | `vendor_shipments` `shipment_type='ADDITIONAL'` | 1 | ya | ya | tidak |
| Retur material | `production_material_returns` | **collection tidak ada** | — | — | — |

Inspeksi material vendor (`vendor_material_inspections`, 1 dok) **tidak pernah** tertaut ke permintaan komponen mana pun.

### 1.6 Collection "hantu" di domain ini (dibaca/ditulis kode, tidak ada di DB)
`cmt_receipts`*, `cmt_receipt_lines`* (\*terbentuk saat alur dijalankan), `dewi_cmt_permak`*, `dewi_cmt_progress`, `dewi_maklon_material_issues`, `dewi_maklon_credit_notes`, `material_defect_reports`, `material_requests`, `production_returns`, `production_return_items`, `production_variances`, `product_variants`, `products`, `garments`, `buyers`, `rahaza_work_orders` (0 dok, **8 pembaca**), `rahaza_fg_movements`, `wh_cmt_dispatches`, `wh_pending_movements`, `rahaza_bundles`, `cmt_receipt`-terkait lain. Total 44 nama collection di domain ini tidak ada di DB.

---

## 2. REGISTER CACAT (semua berbukti angka — `docs/AUDIT_E2E_FINDINGS.json`)

| Kode | Sev | Cacat | Bukti | Keluhan user |
|---|---|---|---|---|
| **SSOT-1** | CRIT | Portal Maklon membuat PO **asli** di collection **mirror** → PO tidak bisa produksi | PO baru `mirror_of=null`, `production_pos` tidak ada | #1,#2 |
| **ORPH-1** | CRIT | 10 PO maklon yatim; 7 berstatus produksi/selesai → **progres palsu** | daftar PO `MKL-2026-001..010` | #2 |
| **SSOT-1b** | CRIT | `POST /api/vendor-shipments` **menerima `po_id` yang tidak ada** (HTTP 201) → surat jalan yatim, `po_number` kosong | http=201 | (baru) |
| **TRK-1** | CRIT | Tracking produksi mengelompokkan `production_jobs` per vendor → PO maklon portal **tidak mungkin muncul** | PO baru tidak ada di `/api/production-tracking` | #2 |
| **CMT-1** | CRIT | Dua model job vendor; `vendor_jobs`/`vendor_progress_reports` = 0 tapi modul UI-nya masih hidup → progress vendor di modul itu **tidak berefek** | 0 vs 3 job | #3,#5,#7 |
| **CMT-2** | CRIT | `dewi_cmt_jobs` tanpa `po_id` → Portal CMT tidak bisa dilacak ke PO | 4/4 tanpa po | #3 |
| **VAR-1** | CRIT | `rahaza_model_variants` **kosong** → PO Produksi **internal** tidak bisa dibuat (UI mewajibkan varian) | 2 model, 0 varian | #1 (produksi) |
| **INV-2** | CRIT | `production_job_items` **tidak punya field reject** → "produced 100, reject 10" tidak punya rumah | field list job item | #5 |
| **RJT-1** | CRIT | 10 pcs reject **hilang**: tidak ke karantina, tidak jadi permak, tidak jadi klaim vendor | karantina 0, permak 0 | #5 |
| **PMK-2** | CRIT | Permak **tidak terlihat sisi vendor** di endpoint mana pun → tidak ada trigger kerja ulang | 3 endpoint diperiksa | #6 |
| **PMK-3** | CRIT | Permak `selesai_berhasil` 10 pcs → **stok FG tidak naik, accepted PO tidak naik, reject tidak turun** | stok 270→270 | #5,#6 |
| **MK-2** | HIGH | PO Maklon tidak menyimpan FK varian (hanya teks) → SKU/FG tidak bisa ditautkan master | item tersimpan tanpa `maklon_variant_id` | #1 |
| **CMT-3** | HIGH | Dua master vendor CMT tidak beririsan | irisan id 0 | #3 |
| **FIN-3** | HIGH | `dewi_cmt_payments.cmt_partner_id` campur id dua master; jumlah campur `net_amount`/`total_amount` | `mk-vendor-demo-1` tidak ada di `dewi_cmt_partners` | integrasi finance |
| **INV-3** | HIGH | `quantity-summary` PO tanpa angka reject → tutup PO tidak menampilkan reject | respons tanpa "reject" | #5 |
| **CONS-3** | HIGH | Dokumen `buyer_shipments` lama tanpa field konsolidasi (`po_ids`,`consolidated`,`parent_shipment_id`,`child_shipment_ids`) | contoh `SJ-BYR-MK-DEMO-2` | #6 |
| **MAT-1** | HIGH | 5 permukaan permintaan material/komponen, 3 collection-nya bahkan tidak ada | tabel §1.5 | #3 |
| **MAT-3** | HIGH | Inspeksi vendor tidak pernah membentuk permintaan komponen | 2 inspeksi, 0 tertaut | #3 |
| **FLD-1** | MED | `po_items.qty` vs pembaca `qty_ordered` | `qty=100`, `qty_ordered=null` | kolom kosong |
| **CONS-2** | MED | Belum pernah ada SJ gabungan | 0 dokumen | #6 |

### Yang TERBUKTI SUDAH BENAR (jangan dirusak saat perbaikan)
- Auto-draft `cmt_receipts` dari deklarasi kirim vendor.
- Stok FG bertambah **tepat** sebesar qty lolos QC (delta 90 dari 100 dikirim).
- AP CMT = qty lolos × rate, dengan `total_rejected` tercatat, idempoten per receipt.
- Dispatch DA→buyer dengan cap terhadap `source_receipt_ids` Approved.
- Guard over-ship SJ material ke vendor (ordered − already_sent).
- GL seimbang (Dr = Cr).

---

## 3. ARSITEKTUR TARGET (TO BE) — keputusan SSOT

1. **PO**: `production_pos` + `po_items` = **satu-satunya SSOT** untuk internal & maklon.
   `dewi_maklon_pos` = **mirror read-only** untuk finance/AR + portal klien. `POST /api/dewi/maklon/pos` **tidak boleh** lagi membuat PO asli.
   Form PO Maklon dipasangkan **picker varian** (`buyer_catalog.variants[]`) dan menyimpan `maklon_variant_id` + `sku`.
2. **Job vendor**: `production_jobs` + `production_job_items` = SSOT.
   `vendor_jobs`/`vendor_progress_reports` + `VendorPortalModule.jsx` **dipensiunkan** (modul lama dilepas dari registry, endpoint ditandai deprecated).
   `dewi_cmt_jobs` diberi `po_id`/`vendor_id` (migrasi) atau Portal CMT dialihkan membaca `production_jobs`.
3. **Master vendor CMT**: `vendor_partners` = SSOT; `dewi_cmt_partners` dimigrasi/di-alias.
4. **Buku kuantitas per job item** (SSOT angka produksi):
   `qty_ordered` · `qty_available` · **`qty_produced`** (tak pernah turun) · **`qty_accepted`** · **`qty_reject`** · **`qty_rework_open`** · **`qty_scrap`**
   Invarian: `qty_produced = qty_accepted + qty_reject_open + qty_scrap + qty_rework_open`.
5. **Pipeline reject** (menutup lingkaran):
   `approve penerimaan` → untuk tiap `reject_qty>0`: buat **rework** otomatis (`permak_type` `permak_sendiri` | `retur_ke_cmt`) + `qty_reject` di job item.
   `rework selesai_berhasil` → stok FG += `qty_fixed`, `qty_accepted` += `qty_fixed`, `qty_reject` -= `qty_fixed`.
   `retur_ke_cmt` → muncul sebagai **pekerjaan ulang di portal vendor** (job anak ber-`shipment_type='REWORK'`), dan saat vendor kirim balik → penerimaan baru.
   `gagal_buang` → `qty_scrap`, biaya diakui, PO bisa ditutup short dengan jejak jelas.
6. **Terima FG dari CMT — UX disederhanakan**: satu tabel, status **`on_qc` → `completed_qc`**, penghitungan qty di baris yang bisa di-inline-edit (tanpa halaman dalam terpisah, tanpa Draft/Submitted/Approved).
7. **Permintaan material/komponen**: satu alur `cmt_material_requests` (rename/unifikasi `dewi_cmt_component_requests`) wajib `po_id` + `vendor_id` + `inspection_id`, dibuat otomatis dari inspeksi kurang/rusak; "Permintaan Tambahan" = `vendor_shipments ADDITIONAL` yang **memenuhi** request tersebut.
8. **Konsolidasi SJ buyer**: backfill field konsolidasi ke semua dokumen; detail SJ mengembalikan `po_ids[]` + `child_shipments[]` + itemnya.
9. **Validasi FK wajib** di seluruh domain: `po_id`, `po_item_id`, `vendor_id`, `job_item_id`, `receipt_id` → 400 bila tidak ada.

---

## 4. URUTAN PERBAIKAN (fase, tiap fase diverifikasi testing agent)

| Fase | Isi | Kenapa duluan |
|---|---|---|
| **F1** | Buku kuantitas job item (`qty_produced/accepted/reject/rework_open/scrap`) + propagasi reject saat approve penerimaan + `quantity-summary`/`fulfillment` memuat reject + karantina/rework otomatis | Ini yang membuat ANGKA benar; semua layar lain ikut benar |
| **F2** | Pipeline permak/rework tertutup: efek stok + accepted, job REWORK ke portal vendor, retur ke CMT | Melengkapi F1 |
| **F3** | SSOT PO: Portal Maklon menulis ke `production_pos` + picker varian; blokir pembuatan PO asli di mirror; migrasi 10 PO yatim; validasi FK | Menghentikan sumber data sampah baru |
| **F4** | Terima FG dari CMT: satu tabel, status `on_qc`/`completed_qc`, inline edit; hapus halaman dalam | Keluhan UX #5 |
| **F5** | Unifikasi permintaan material/komponen + auto dari inspeksi | Keluhan #3 |
| **F6** | Konsolidasi SJ buyer + child shipment + backfill | Keluhan #6 |
| **F7** | Pensiunkan portal vendor lama + satukan master vendor CMT + Portal CMT menunjuk PO | Keluhan #3, integrasi |
| **F8** | Varian internal (`rahaza_model_variants`) bisa dibuat dari UI + seed | Keluhan #1 sisi produksi |
| **F9** | Perbaikan UI: kartu/tabel yang memotong isi (overflow), lebar kolom, tabel detail bisa di-scroll | Keluhan #4 |
| **F10** | Guardrail baru: `scripts/verify_produksi_maklon_invariants.py` masuk `gate.sh` supaya cacat ini tidak bisa kembali | Anti-regresi |
