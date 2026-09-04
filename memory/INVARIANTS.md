# INVARIANTS.md — SSOT Invarian CV. Dewi Aditya ERP

> Diadaptasi dari metodologi Rahaza-Travel. Setiap invarian punya verifier otomatis di
> `/app/scripts/`. Jalankan `bash scripts/gate.sh`. Perbarui file ini saat menemukan
> invarian baru. **"Selesai" hanya sah bila gate HIJAU (lihat `GATE_RECEIPT.md`).**

## Cara baca
- **FAIL** = pelanggaran keras (blok klaim selesai).
- **WARN** = anomali/semantic-smell (didokumentasikan, non-blok).
- **SKIP** = tak dapat diuji sekarang (backend/auth mati) — **bukan** PASS.

---

## A. Finance / General Ledger — `verify_data_integrity.py`
| ID | Invarian | Koleksi | Sifat |
|---|---|---|---|
| INV-GL-1 | Tiap jurnal seimbang: `total_debit == total_credit == Σ lines.debit/credit` | `rahaza_journal_entries` | FAIL |
| INV-GL-2 | Trial-balance global: Σ debit posted == Σ credit posted | idem | FAIL |
| INV-GL-3 | `line.account_code` ada di CoA aktif | `rahaza_coa_accounts` | FAIL |
| INV-JL-1 | `rahaza_journal_lines.je_id` menunjuk entry yang ada (no orphan) | `rahaza_journal_lines` | WARN |

## B. Accounts Receivable / Payable
| ID | Invarian | Sifat |
|---|---|---|
| INV-AR-1 | AR `balance ∈ [0, total]` (tak minus, tak lebihi total) | FAIL |
| INV-REF-1b | `ar_payments` menunjuk `ar_invoices` yang ada | WARN |
| INV-AP-1 | AP `amount >= 0` | FAIL |

## C. Maklon (RC-7 basis pajak — KALIBRASI PENTING)
| ID | Invarian | Sifat |
|---|---|---|
| INV-MKL-1 | `amount_paid` (tax-incl) <= total invoice tax-inclusive | FAIL |
| INV-MKL-2 | Smell: `amount_paid` (tax-incl) vs `total_value` (pra-pajak) tercampur dalam 1 dok | WARN |

> Catatan: `amount_paid` di `dewi_maklon_pos` SUDAH termasuk PPN 11% (= total `dewi_maklon_invoices`),
> sedangkan `total_value` PRA-pajak. Jangan bandingkan mentah (menghasilkan "overpay" palsu).

## D. Inventory / WMS
| ID | Invarian | Sifat |
|---|---|---|
| INV-STK-1 | Stok tak negatif (`material_stock.qty`, `materials.current_stock`) | FAIL |
| INV-REF-1a | `material_stock.material_id` ada di `materials` | WARN |

## E. Penomoran dokumen (RC-5)
| ID | Invarian | Sifat |
|---|---|---|
| INV-CNT-1 | Nomor dok unik: `je_number, wo_number, ap_number, invoice_number, po_number` | FAIL |
| CC1 | N create paralel → semua 200 nomor UNIK / clean-4xx, **tak ada 5xx** | FAIL |

## F. HR / Cuti
| ID | Invarian | Sifat |
|---|---|---|
| INV-LEAVE-1 | `used ∈ [0, allocated+adjustments]` (tak minus, tak over-consume) | FAIL |

## G. Produksi
| ID | Invarian | Sifat |
|---|---|---|
| INV-WO-1 | `completed_qty ∈ [0, target]` | FAIL |

## H. Numeric bounds
| ID | Invarian | Sifat |
|---|---|---|
| INV-NUM-1 | Uang/qty tak negatif di koleksi finansial kunci | FAIL |

## I. State-machine — `verify_state_machine.py`
| ID | Invarian | Sifat |
|---|---|---|
| SM1 | Post jurnal non-draft ditolak (400) | FAIL |
| SM2 | Void jurnal voided ditolak (400) — idempotent, no double reversal | FAIL |
| SM3 | Delete jurnal non-draft ditolak (400) | FAIL |
| SM4 | Jurnal tak-seimbang ditolak (400) | FAIL |

## J. Adversarial — `verify_adversarial_5xx.py`
| ID | Invarian | Sifat |
|---|---|---|
| INV-5XX-01 | Input hostile (non-numerik, tipe salah, string raksasa, dst) → 4xx, **bukan 5xx** | FAIL |

## K. Kontrak FE↔BE — `preflight/verify_fe_be_contract.py`  (INV-CONTRACT-01)
| ID | Invarian | Sifat |
|---|---|---|
| CONTRACT-A | Tidak ada duplicate route `(METHOD, path)` (FastAPI pakai definisi TERAKHIR → handler pertama mati diam-diam) | HIGH (blok) |
| CONTRACT-B | Setiap panggilan API FE `${API}/api/...` cocok dgn route backend (OpenAPI SSOT) | WARN (triase) |
| CONTRACT-C | Route backend yang tak dipanggil FE (orphan / hidden) | INFO |

## L. Auth coverage — `guardrails/verify_auth_coverage.py`  (INV-AUTH-01)
| ID | Invarian | Sifat |
|---|---|---|
| AUTH-01 | Tiap endpoint menegakkan auth (langsung/`Depends`/helper `_require_*`/`require_*_auth`/verifikasi token), kecuali `PUBLIC_ALLOWLIST` (login/register/health/webhook/public) | mutation=HIGH, GET=MED |

## M. RBAC / kebocoran akses — `guardrails/verify_rbac_idor.py`  (INV-RBAC-01)  ★RUNTIME ★BLOCKING (gate.sh)
| ID | Invarian | Sifat |
|---|---|---|
| RBAC-UNAUTH | GET parameterless tanpa token → 401/403 (bukan 200) | sensitif=HIGH (BLOK), lain=MED (advisory) |
| RBAC-XROLE | Role rendah (mis. `operator`) menembak endpoint portal lain (jurnal/AR/AP/payroll/COA) → **403**, bukan 200 (eskalasi privilege) | HIGH (BLOK) |

> Ditegakkan di kode via `shared.require_portal(request, *portal_ids)` (SSOT `check_portal_access`)
> dan `require_portal_dep()` sebagai router-level dependency pada router finance/HR
> (rahaza_journals, rahaza_finance, rahaza_coa, rahaza_payroll_runs) + auth pada `/api/financial-recap`.
> SUPER_ROLES otomatis lolos; izin eksplisit (`*`, `<portal>.view/manage`) dihormati.

## N. Anti-pola statik — `guardrails/verify_static_antipatterns.py`  (INV-STATIC-01)
| ID | Invarian | Sifat |
|---|---|---|
| SA-RC5 | Tak ada `count_documents()+1` untuk penomoran; pakai `utils.counters.gen_prefixed_number` (atomic). Koleksi unique-indexed=HIGH (500 E11000), lain=MED (nomor dup) | HIGH/MED |
| SA-5XX | Koersi numerik input klien harus di-guard try/except→400 (bukan 500) | MED |
| SA-TZ / SA-EXC | datetime naive & `except:` telanjang | LOW |

## O. Integritas navigasi — `guardrails/check_nav_map.py`  (INV-NAV-01)  ★STATIC ★BLOCKING (gate.sh)
| ID | Invarian | Sifat |
|---|---|---|
| NAV-SINGLE | Tak ada section beranggota 1 item (langgar MECE/cohesion) | HIGH (BLOK) |
| NAV-EMPTY | Tak ada section 0 item | HIGH (BLOK) |
| NAV-GHOST | Tiap moduleId menu ADA di `MODULE_REGISTRY` (kecuali `isHeader`) | HIGH (BLOK) |
| NAV-DUP | Tak ada moduleId duplikat DALAM satu portal (lintas-portal boleh) | HIGH (BLOK) |
| NAV-DEPTH | Kedalaman IA ≤ 4 (Portal→Section→Group→Item) | MED |
> SSOT struktur IA: `memory/IA_BLUEPRINT.md`. Self-test-proven (inject→MERAH→revert→HIJAU).

## P. Batas numerik schema — `guardrails/verify_numeric_bounds.py`  (INV-NUM-01)  ★STATIC ★ADVISORY| ID | Invarian | Sifat |
|---|---|---|
| NUM-UNBOUND | Field uang/kuantitas di Pydantic model wajib `ge=`/`gt=` (tolak negatif/absurd) | MED (report-only; baseline 134 field → backlog fix) |

## U. Satuan material (multi-UOM) — `guardrails/verify_uom_integrity.py`  (INV-UOM-01)  ★RUNTIME ★BLOCKING
| ID | Invarian | Sifat |
|---|---|---|
| INV-UOM-1 | `rahaza_materials.unit_cost` **selalu** harga per **satuan dasar**. Satuan lain hanya alat bantu entri; hasil konversinya yang disimpan. `cost_uom` tidak boleh persist ≠ satuan dasar. | FAIL |
| INV-UOM-2 | Semua qty di `rahaza_material_stock`, `rahaza_stock_ledger`, `rahaza_material_movements` **selalu** dalam satuan dasar | FAIL |
| INV-UOM-3 | `uoms` valid: tepat 1 satuan dasar berfaktor 1, kode unik, tiap faktor > 0, maks 3 satuan (dasar + 2 tingkat kemasan), induk ada di daftar | FAIL |
| INV-UOM-4 | `unit` (lama) == `base_uom` (baru); cermin `pack_unit`/`pack_size` konsisten dengan `uoms` | FAIL |
| INV-UOM-5 | Mengedit daftar `uoms` **tidak boleh** mengubah angka stok yang sudah ada. Perubahan satuan dasar hanya lewat aksi "Ubah Satuan Dasar" ber-audit | FAIL |
| INV-UOM-6 | `factor` selalu relatif ke **satuan dasar**, bukan ke induknya | FAIL |

> **Kenapa INV-UOM-1 mengikat:** 5 modul hilir — `dewi_rnd_hpp`, `rahaza_hpp`,
> `rahaza_material_requirements`, `production_internal_adapter`, `rahaza_posting` —
> memakai rumus `amount = qty × unit_cost` dan mengasumsikan keduanya satuan dasar.
> Mengubah makna `unit_cost` merusak HPP RnD, HPP produksi, MRP, dan posting GL sekaligus.
>
> SSOT konversi: `backend/core/uom.py` ⇄ `frontend/src/lib/uom.js` (wajib sinkron).
> Rancangan: `docs/RANCANGAN_MULTI_UOM.md` · Audit: `docs/AUDIT_KONVERSI_SATUAN.md`
> Peta dampak: `docs/MAP_UOM_IMPACT.md` (132 file BE, 64 FE, 52 titik tulis stok).
> Self-test-proven: 5 kelas pelanggaran sintetis terbukti MERAH lalu HIJAU setelah revert.

## Q. Cross-entity referensial — `guardrails/verify_cross_entity.py`  (INV-CROSS-01)  ★RUNTIME ★ADVISORY
| ID | Invarian | Sifat |
|---|---|---|
| CROSS-ORPHAN | Child FK (journal_line→entry/COA, AR→customer, WO→order, issue→WO, maklon PO→client) tak yatim | HIGH (report-only; skip aman bila field-name beda) |

## R. Kualitas kerja / effort statik — `guardrails/verify_effort_quality.py`  (INV-QUALITY-01)  ★STATIC ★ADVISORY
| ID | Invarian | Sifat |
|---|---|---|
| QUAL-NOTIMPL | Tak ada `NotImplementedError` di router | HIGH |
| QUAL-SWALLOW | Tak ada `except…: pass` (telan error senyap) | MED |
| QUAL-SECRET/FEURL/MONGO | Tak ada rahasia/URL backend/mongo:// hardcoded | HIGH |
> Melengkapi `meta/effort_gate.py` (git-diff). Lihat `ANTI_UNDERDELIVERY_PROTOCOL.md`.

## S. Meta guardrail-registry — `guardrails/verify_guardrail_registry.py`  (INV-META-01)  ★STATIC
| ID | Invarian | Sifat |
|---|---|---|
| META-UNWIRED | Tiap guardrail `verify_*/check_*` WAJIB dirujuk `gate.sh` (cegah perlindungan mati diam-diam / "HIJAU-PALSU") | HIGH (report-only) |

## T. Health — `health_check.py`  (HEALTH-01)  ★RUNTIME ★BLOCKING
| ID | Invarian | Sifat |
|---|---|---|
| HEALTH-DOWN/AUTH/5XX | `/api/health` 2xx, login admin OK, endpoint inti tak 5xx | CRIT/HIGH (BLOK) |

## META. Efektivitas gate & kualitas AI
| ID | Invarian | Sifat |
|---|---|---|
| MUT-01 (`meta/mutation_test.py`) | Setiap korupsi invarian yang disuntik HARUS `KILLED` gate integrity (SURVIVED=blind spot) | FAIL |
| EFFORT-01 (`meta/effort_gate.py`) | Klaim "selesai" wajib punya bukti: receipt HIJAU+baru, tanpa TODO/mock/stub, mutation SURVIVED=0 | lensa BLOK |

---

## MAKLON-CMT-SSOT — Keputusan SSOT Operasional CMT (Maklon CMT Operasional Plan, Fase 0)
> Kontrak keras untuk pekerjaan operasional CMT baru (KEJAR, Dashboard Owner, Potongan Masuk, Rekap Aksesoris, Kapasitas).
> Tujuan: cegah duplikat/percabangan/split-brain. **Semua fitur baru WAJIB membaca rantai SSOT ini, bukan koleksi paralel.**

| ID | Invarian / Keputusan | Sifat |
|---|---|---|
| MCS-01 | Rantai SSOT Maklon = `production_pos`/`po_items` → `vendor_shipments`/`vendor_shipment_items`(+`vendor_material_inspections`) → `production_jobs`/`production_job_items`/`production_progress` → `cmt_receipts`/`cmt_receipt_lines` → `dewi_cmt_permak` → `buyer_shipments`/`buyer_shipment_items`. Komponen-kurang aksesoris = `dewi_cmt_component_requests`. | FAIL bila fitur maklon baru menulis truth di luar rantai ini |
| MCS-02 | Master CMT partner SSOT = `vendor_partners` (owner `vendor_portal.py`, nav `vendor-admin`). `dewi_cmt_partners`/`dewi_cmt_jobs`/`dewi_cmt_progress` = **LEGACY/ARSIP** (hanya `_archive/*` + `dewi_demo_seed`), jangan tulis dari kode baru. | WARN (deprecate) |
| MCS-03 | Progress/qty PO dihitung HANYA dari rantai SSOT (mis. `production_job_items.produced_qty`, `cmt_receipt_lines`, `dewi_cmt_permak`, `buyer_shipment_items`). `vendor_jobs`/`vendor_progress_reports` (portal CMT eksternal) **BUKAN sumber angka PO** (opsi B2-A) — hindari double-count. | FAIL bila KPI PO baca `vendor_jobs` |
| MCS-04 | Untuk PORTAL MAKLON, dispatch DA→CMT = `vendor_shipments`+`cmt_receipts`. `wh_cmt_dispatches` (wms_cmt_dispatches.py) = domain WMS/Produksi-internal, **tidak** dipakai KPI maklon (konsolidasi = Fase 5). | WARN |
| MCS-05 | Semua metrik operasional (kejar/dashboard/rekap/kapasitas) = **READ-ONLY agregasi** di atas SSOT + config (`dewi_system_config`: `maklon_cmt_buffer_days`, `maklon_cmt_late_grace_days`, `maklon_permak_return_grace_days`). **0 koleksi kebenaran baru.** | FAIL bila muncul koleksi truth baru |
| MCS-06 | Target CMT = `delivery_deadline − maklon_cmt_buffer_days` (computed, tidak disimpan). Deadline Mitra/Buyer = `production_pos.delivery_deadline`. Deadline internal = `production_pos.deadline`. | FAIL bila ada field target_cmt tersimpan ganda |
| MCS-07 | **Nomor seri (SN) SSOT tunggal = `po_items.serial_number`** (input saat BUAT ORDER, mewaris otomatis ke `production_job_items`/`vendor_shipment_items`/`buyer_shipment_items`). Cek-seri (`/api/dewi/cmt-intake/*`) = READ-ONLY deteksi dobel; **DILARANG** membuat field/koleksi seri baru. | FAIL bila ada field seri baru selain warisan `serial_number` |
| MCS-08 | Kapasitas CMT = field additif `vendor_partners.capacity_pcs`/`capacity_note` (owner `vendor_portal.py`). Rekap aksesoris & kapasitas (`/api/dewi/cmt-belanja/*`) = READ-ONLY (`po_accessories` + BOM×qty; beban via `services.cmt_kejar`). | FAIL bila kapasitas/rekap disimpan sebagai truth baru |
| MCS-09 | **Fase 5 = pemisahan PERMANEN ditegaskan.** `vendor_shipments`(maklon/pcs) & `wh_cmt_dispatches`(WMS/meter) tetap TERPISAH; `/api/dewi/cmt-recon/dispatch` hanya READ-ONLY monitor + deteksi overlap. Bridge `vendor_progress_reports → production_progress` (B2-B) **SENGAJA TIDAK dibuat** (opsi B2-A). | FAIL bila ada penggabungan/bridge yang double-count |

## Gap yang BELUM ter-invarian (TODO — lihat GAP_ANALYSIS §8)
- ~~Cross-entity double-allocation (referensial yatim)~~ → **kini tercakup** oleh INV-CROSS-01 (`verify_cross_entity.py`, advisory). Ekstensi double-allocation stok FG/operator/mesin masih backlog.
- Reservation-lock statik.
- Lintas-periode payroll (no double-count).
- ~~RBAC-guard statik~~ → **kini tercakup RUNTIME & BLOCKING** oleh INV-RBAC-01 (`verify_rbac_idor.py`, terpasang di `gate.sh`). **BUG-RBAC-1 SUDAH DITUTUP** — read-guard ditegakkan di kode via `require_portal`/`require_portal_dep` (lihat ENGINEERING_GUARDRAILS §12).

## INV-F30 — IDENTITAS BARANG TIDAK BOLEH MENABRAK (2026-08-19, sesi #28)
`scripts/verify_identitas_varian_3dimensi.py` · 23 invarian · dijalankan oleh `gate.sh`.

Kenapa ada: mesin identitas lama menabrakkan **83 SKU platform nyata menjadi 35 identitas**
(16 kelompok tabrakan, 63 SKU / 489 pcs tertimpa). Delapan SKU berbeda jatuh ke satu `hitam/XL`
karena (1) warna majemuk dipotong pencocokan *substring* (`POLKA WHITE` → `putih`) dan
(2) `PAKAI/TANPA KARET` tidak dibaca sama sekali. Kalau itu ditulis, **gudang mengambil barang yang
salah untuk 4 dari 5 pesanan**.

- **V1** identitas INJEKTIF: variasi berbeda ⇒ identitas berbeda; variasi sama persis ⇒ identitas sama
- **V2** tidak ada pencocokan substring warna (POLKA WHITE ≠ Putih, BUTTER YELLOW ≠ Kuning)
- **V3** dimensi ke-3 hidup di DB: ada model·warna·ukuran dengan opsi berbeda & SKU berbeda
- **V4** index unik varian = 4 sumbu; index 3 sumbu lama dilepas; semua varian punya `option_code`
- **V5** opsi berasal dari master `rahaza_variant_options`, bukan teks bebas
- **V6** KOMPATIBEL-BALIK: kode ketidakhadiran (`NA` opsi, `TDI` warna) tidak masuk SKU ⇒ SKU 330
  varian lama mustahil berubah; tidak ada SKU berakhiran `-NA`/`-TDI`
- **V7** pratinjau onboarding tidak menulis apa pun (11 koleksi dipantau, termasuk `counters`)
- **V8** apply idempoten
- **V9** rantai pemetaan → varian → master FG → item katalog utuh
- **V10** tidak ada dua variasi berbeda menunjuk satu varian
- **V11** palet warna aktif bebas kembar & tidak ada varian menggantung ke warna terhapus
- **V12** SKU varian unik
- **V13** pintunya ADA di layar (tab Onboarding Produk & Opsi Varian) **dan** setiap endpoint yang
  dipanggil layar benar-benar ada di backend
- **V14** nama model tidak membuang identitas produk (cacat lama `clean_product_name`)
- **V15** alat ukur tidak mengotori: 0 baris stok / kartu stok menunjuk material yang tidak ada

Sifat: bila masih ada produk belum tertaut, gate MENGERJAKAN onboarding produk ber-opsi terbanyak
lalu MEMBATALKANNYA kembali — ia tidak pernah lulus hanya karena data ujinya tidak ada.

## INV-F31 — RETUR PEMBELI HARUS SAMPAI KE GUDANG DAN KEMBALI KE STOK (2026-08-19, sesi #29)
`scripts/verify_jembatan_retur_marketing_gudang.py` · 15 invarian · dijalankan oleh `gate.sh`.

Kenapa ada (diukur, bukan ditebak): `marketing_returns` = **30 dokumen retur pembeli NYATA**
sementara `wh_returns` = **0** ⇒ layar **Retur Fisik** gudang kosong SELAMANYA. Jembatan yang ada
harus diklik manual, hanya untuk status approved/completed, dan mengirim `sku_code=""` + `qty=1`.
Lebih buruk: tombol **"Restock ke Gudang"** menulis ke `rahaza_fg_inventory` — koleksi **MATI (0
dokumen)** — memakai `sku_code` yang selalu kosong ⇒ **stok nyata tidak pernah bertambah** dan 0
baris ledger. Barang retur senilai jutaan rupiah hilang dari pembukuan stok tanpa satu pun error.

- **R1** pintunya ADA di layar (`wh-returns` di registry + sidebar Gudang) — pemilik minta fitur ini
  DIHIDUPKAN, bukan dihapus
- **R1b** layar Gudang punya: tombol *Tarik Retur dari Marketing*, aksi cepat *Terima & Restock*,
  pemilih kondisi Baik/Rusak, spanduk angka jembatan, dan pemilih barang dari MASTER (INV-F14)
- **R1c** layar Marketing menanyakan kondisi & jumlah barang, lalu MENYATAKAN efek stoknya
- **R2** 0 penulisan ke koleksi stok mati (`rahaza_fg_inventory`/`rahaza_fg_movements`)
- **R2b** restock melewati `core/returns_bridge` → `core/stock_service` (satu pintu + ledger)
- **R2c** retur Marketing memicu jembatan saat DIBUAT (otomatis, bukan hanya tombol manual)
- **R3** DATA NYATA: 0 retur pembeli (selain ditolak/dibatalkan) tanpa pekerjaan Retur Fisik
- **R4** kondisi **Baik** ⇒ `wh_returns` lahir otomatis + stok bertambah di `ZNA-FG` + 1 baris
  `rahaza_stock_ledger` ber-`ref.ref_id` (aturan INV-F30 V15)
- **R5** kondisi **Rusak** ⇒ stok masuk `ZNA-KARANTINA` dan **stok JUAL tidak bertambah** (K-6a)
- **R6/R6b** IDEMPOTEN: menjembatani ulang & restock kedua tidak menggandakan dokumen/stok
  (penjaga atomik `restocked` dipasang SEBELUM stok ditambah)
- **R7** TIDAK MENEBAK: pesanan multi-baris tanpa penunjuk produk ⇒ pekerjaan tetap MUNCUL,
  ditandai `needs_manual_resolution`, stok TIDAK disentuh
- **R8** rantai balik jujur: retur Marketing menerima kode/status/qty/efek stok gudang
- **R9** 0 rujukan menggantung (material & retur Marketing asal benar-benar ada)
- **R10** alat ukur bersih: seluruh artefak uji dihapus & stok kembali persis (INV-F30 V15)

Sifat: gate MEMBUAT retur uji (Baik & Rusak + kasus ambigu) pada data hidup, mengukur stok
sebelum/sesudah, lalu MENGEMBALIKAN semuanya — ia tidak bisa lulus tanpa mengukur.

## INV-F32 — TABEL STOK TERBACA & KOLOM CETAK BISA DIPILIH (2026-08-19/20, sesi #29)
`scripts/verify_tabel_stok_dan_ekspor_kolom.py` · 11 invarian · dijalankan oleh `gate.sh`.

Kenapa ada (terukur): (a) layar **Stok & Akurasi** tab pertama menampilkan **UUID `material_id`
sebagai kolom PERTAMA** dan mengekspornya ke CSV, tanpa kolom Kategori/Warna/Opsi padahal ketiganya
sudah tersimpan di master; layarnya menampilkan **26 BARIS STOK untuk 321 barang jadi** ⇒ tampak
"tidak sinkron" dengan Master Item. (b) kolom **Serial No** sudah ada di katalog kolom PDF tetapi
tidak ada pintu memilihnya saat mencetak — dan memakai konfigurasi kolom pada laporan produksi
justru **menggagalkan cetakan (500 "list index out of range")** karena kolom difilter DUA KALI
(`_filter_columns` inline + `tpl_table_parts`).

- **T1** API stok mengirim identitas dari MASTER: kode·kategori·warna·opsi·ukuran
- **T2** `include_zero=1` menampilkan barang master tanpa baris stok (qty 0, `no_stock_row`)
- **T3** Viewer Unified diperkaya master + mengirim `facets` (pilihan filter dari data nyata)
- **T4** filter kategori/warna/opsi BENAR-BENAR menyaring (0 baris salah warna)
- **T5** UUID `material_id` tidak lagi ditampilkan/diekspor; CSV memakai **Kode Barang**
- **T6** kolom+filter+saklar "tampilkan stok 0" ada di KEDUA layar stok
- **T7** kolom Serial tersedia sebagai pilihan untuk dokumen produksi & maklon
- **T8** `?cols=` benar-benar mengubah PDF jadi (diukur dari teks PDF: kolom tak dicentang HILANG,
  yang dicentang TETAP)
- **T9** kolom WAJIB tetap tercetak walau tidak dicentang; kunci karangan diabaikan (bukan 500)
- **T10** pintunya ADA di layar: `PdfColumnPicker` di Laporan Produksi & SPP Produksi/Maklon
- **T11** 0 penyaringan kolom ganda di generator PDF (akar 500 lama)

Sifat: gate hanya MEMBACA (GET) — tidak menulis dokumen apa pun, jadi tidak bisa mengotori data.

## INV-F36 — HPP PER POTONG LAHIR DARI PEMBELIAN + BOM MENGISI RENCANA CUTTING (2026-08-23, sesi #31)
`scripts/verify_hpp_potong_dan_bom_cutting.py` · 12 invarian · self-cleaning · dijalankan `gate.sh`.

Kenapa ada (terukur): sesi #30 membuat harga **BAHAN** lahir dari pembelian, tetapi HPP **PRODUK
JADI** belum pernah lahir dari angka itu — `rahaza_materials` type='fg' = **321 dokumen, semuanya
`hpp: 0` & `hpp_source: 'none'`**, dan satu-satunya sumber HPP model adalah kalkulator R&D atau
**KETIKAN** `base_hpp`. Akibatnya kolom HPP & margin di Katalog Marketing ada tapi selalu 0/"belum
ada", jadi margin tidak bisa diketahui sebelum harga jual ditetapkan. Selain itu rencana pemakaian
kain pada Order Cutting masih **DITEBAK manual** walau BOM per model+size sudah menyimpan kebutuhan
per pcs.

- **C1** biaya bahan/pcs = Σ(qty BOM dalam satuan DASAR × `unit_cost`) — 150 cm = 1,5 m;
  0,5 lusin = 6 pcs; harga HANYA dari master hasil pembelian (modul tidak pernah menulis harga bahan)
- **C2** bahan tanpa harga TIDAK dihitung 0 diam-diam ⇒ `gaps.material_unvalued` + baris
  berstatus `unvalued` + `computable=false`
- **C3** upah cutting/internal punya rantai sumber yang DILAPORKAN (`owner` → `wip_actual` →
  `settings_process_rates` → `settings_fallback`); proses jahit/CMT dikecualikan (anti dobel hitung)
- **C4** upah CMT kosong = kekurangan + kandidat tarif NYATA (partner CMT / job CMT) ditawarkan
- **C5** upah yang dikunci pemilik dipakai & sumbernya `owner` (dengan siapa & kapan)
- **C6** overhead **OPSIONAL**: default MATI (keputusan pemilik), bisa dihidupkan per permintaan
- **C7** margin & usulan harga jual benar (margin ATAS harga jual); margin TIDAK ditampilkan bila
  HPP belum diketahui (`margin_known=false`) — mencegah "margin 100%" palsu atas biaya 0
- **C8** TERAPKAN menulis HPP ke master (`rahaza_models.hpp_bom`) + FG **per ukuran**
  (`rahaza_materials.hpp`, `hpp_source='bom'`) + item katalog Marketing; **idempoten** + snapshot
  audit di `product_cost_snapshots`
- **C9** `core/product_master.resolve_hpp` urutannya **bom → rnd → manual → none**; model tanpa
  `hpp_bom` angkanya TIDAK berubah
- **C10** BOM mengisi rencana cutting: kebutuhan/pcs & total dalam satuan kain, aksesoris ikut,
  kain di luar BOM (`input_not_in_bom`) & ukuran tanpa BOM (`bom_missing`) DIKATAKAN
- **C11** LAYAR ada: menu **HPP per Potong** (`fin-hpp-produk`) terdaftar + 9 testid kunci; kartu
  **Kebutuhan menurut BOM** + tombol **Pakai angka BOM** ada di dialog Order Cutting
- **C12** alat ukur bersih: artefak uji dihapus, setelan costing dipulihkan, total stok kembali persis

Sifat: gate MEMBELI bahan sungguhan (PO → approve → GR → terima) supaya harga benar-benar lahir dari
pembelian, lalu mengembalikan seluruh jejaknya.

## INV-F37 — NILAI POTONGAN LAHIR SAAT DIPOTONG & TIDAK ADA POTONGAN YATIM (2026-08-23, sesi #32)
`scripts/verify_potongan_nilai_dan_yatim.py` · 12 invarian · self-cleaning · dijalankan `gate.sh`.

Kenapa ada (terukur): pemilik menemukan sendiri lewat mongosh bahwa **(a)** harga/HPP master
potongan **= 0** dan **(b)** master potongan menjadi **yatim** (order cutting / kain sumbernya sudah
tidak ada). Pengukuran menemukan dua sebab yang berbeda. Untuk (a): `complete` order cutting
menghitung nilai memakai harga kain yang **di-snapshot saat order dibuat** — pada satu order uji
tercatat **Rp600.000** padahal nilai kain yang benar-benar keluar **Rp641.379,31** ⇒ **Rp41.379
hilang tanpa jejak**. Untuk (b): sumbernya bukan alur produk melainkan **ALAT UKUR** — gate INV-F24
menghapus master potongan dengan **REGEX KODE** (`^(VFH6B-|CUT-GATE-F24)`), sementara sejak sesi #30
kode potongan diturunkan dari NAMA MODEL (`CUT-JEPIT-JEDAI-…`) ⇒ regex tak pernah cocok ⇒ satu master
sampah **menumpuk setiap kali gate dijalankan**.

- **C1** statik: `add_progress` memanggil `cut_panel_value.apply_progress_value` (nilai berpindah
  saat barang bergerak, dan stok potongan dibaca **SEBELUM** `stock_service.add`)
- **C2** statik: `complete` memakai Σ nilai progres (`order_value_totals`) dan **TIDAK** menimpa HPP
  master tanpa syarat (order lama bermaster 0 diisi sekali, sumber `cutting_complete_backfill`)
- **C3** statik: `cancel` & `delete` memanggil penjaga `cut_panel_health.remove_if_unused`
- **C4** statik: LAYAR Master Potongan punya kolom nilai + kartu potongan yatim + tombol bersihkan
  (tidak ada fitur backend tanpa pintu di layar)
- **C5** runtime: progres #1 ⇒ HPP potongan = nilai kain keluar / pcs jadi
- **C6** runtime: progres #2 dengan harga kain yang sudah berubah ⇒ **RATA-RATA BERGERAK**, angka
  lama tidak ditimpa
- **C7** runtime: kekekalan nilai — Σ nilai kain yang keluar == nilai stok potongan yang masuk
- **C8** runtime: kain belum bernilai ⇒ potongan `value_status='unvalued'` + alasan & jalan keluarnya
  DIKATAKAN (bukan diam-diam Rp0) + notifikasi ke Admin Gudang
- **C9** runtime: `cancel` membuang master potongan yang belum pernah bergerak
- **C10** runtime: potongan yatim TERDETEKSI (`order_missing`/`source_missing`/`source_inactive`/
  `source_unknown`), bisa dibersihkan, dan **IDEMPOTEN**
- **C11** runtime: potongan yatim yang **MASIH BERSTOK** tidak dihapus dan alasannya disebut
  (supaya stok tidak menjadi hantu)
- **C12** **KEADAAN AKHIR**: **0 potongan yatim** di database sesudah seluruh uji dijalankan —
  dijalankan SESUDAH bersih-bersih, persis pola C14 INV-F24. Ini penjaga terhadap **alat ukur yang
  bocor**: kebocoran mana pun (gate, POC, seed) langsung MERAH.

Sifat: gate MEMBELI kain sungguhan (PO → approve → GR → terima) supaya harga lahir dari pembelian,
memotongnya dua kali dengan harga berbeda, lalu mengembalikan seluruh jejaknya.


---

## INV-F39 (2026-08-23, sesi #34) — BIAYA JAHIT → HPP BATCH → MARKETING · IMPOR PINTAR · PORTAL KREATOR · GAJI HOST BULANAN
Penjaga: `scripts/verify_biaya_jahit_hpp_batch_impor_pintar.py` (23 invarian, self-cleaning).

**Kenapa ada:** lima cacat yang DIUKUR, bukan diduga. (1) `po_items.cmt_price_snapshot` dibaca tiga
tempat (monitoring CMT, tagihan CMT, kalkulator HPP) tetapi SPK internal **selalu menulis 0** dan
tidak ada layar yang bisa mengisinya ⇒ HPP = biaya bahan saja, margin marketing terlihat lebih bagus
dari kenyataan. (2) Portal kreator membaca koleksi katalog **kosong** dan kreator demo lahir tanpa
kredensial ⇒ pemilik tidak bisa login sama sekali. (3) 22 jenis impor dipilih manual tanpa petunjuk
⇒ berkas pesanan bisa masuk sebagai penjualan harian **tanpa ada yang tahu**. (4) Upah live host
per-sesi (jam × tarif + 10% omzet − denda) melahirkan gaji **di luar payroll HR** ⇒ satu orang
dibayar di dua buku. (5) Periode anggaran 7 hari membuat `budget/summary` **500** dan layar
menampilkan **Rp 0 tanpa pesan apa pun**.

- **A1–A4** biaya jahit: layar punya daftar SPK; tarif tersimpan di **`po_items.cmt_price_snapshot`**
  (SSOT lama, bukan koleksi baru) dengan jejak pengisi; **total baris = tarif × qty** (staf mengetik
  tarif per SKU per pcs, sistem yang mengalikan); HPP/pcs memuat ongkos jahit itu
- **B1–B2** HPP batch: `hpp_fifo_avg` == **rata-rata TERTIMBANG lapisan yang masih bersisa**
  (bukan batch terakhir, bukan rata-rata seluruh riwayat); setiap lapisan menyimpan **rincian**
  (bahan/jahit/permak/internal) **dan** `gaps[]` — komponen yang belum diketahui tidak pernah ditebak
- **C1–C3** portal kreator: kreator ber-akun bisa **login**; katalog terisi dari SSOT
  `marketing_catalog_items`; **TIDAK ADA** field ber-nama `hpp*`/`margin`/`cost` yang terkirim
  (daftar PUTIH field, bukan daftar hitam — daftar hitam pasti bocor saat ada field biaya baru);
  semua item punya nama produk terbaca (kalau tidak, request barang gagal 500)
- **D1–D4** impor pintar: platform terbaca dari **sidik kolom** berkas ASLI pemilik; salah pilih
  jenis **DILAPORKAN** beserta bukti jumlah kolom; ≥5 baris mentah tersedia untuk viewer tabel;
  jenis yang benar memetakan ≥30 kolom dengan kolom wajib lengkap
- **E1–E2** live host: **0 shift** bersaldo `total_pay > 0`; basis biaya anggaran =
  `livehost_monthly_salary` (dibaca dari `rahaza_payroll_profiles`, SSOT payroll HR)
- **F1–F2** periode anggaran: setelan terbaca (default **7 hari**); `budget/summary` **HTTP 200**
  untuk periode 7 hari **DAN** bulanan — dua-duanya, karena mode bulanan tidak boleh mati
- **G1–G3** insentif kreator: tracker pcs (diinput staf marketing) menghitung per-pcs + bonus target;
  **tutup periode ⇒ hitungan 0** (entri hari ini milik periode yang ditutup, tidak dibayar dua kali);
  entri periode lama **tetap tersimpan** sebagai bukti bayar
- **H1–H2** viewer RnD: produk final terlihat sebagai katalog dengan status sync katalog marketing;
  setiap produk yang belum lengkap **menyebut kekurangannya** (BOM/katalog/biaya jahit/foto)

## INV-F44 (2026-08-26, sesi #38) — JURNAL COGS MEMAKAI BIAYA BATCH YANG BENAR-BENAR KELUAR
Penjaga: `scripts/verify_cogs_fifo_jurnal.py` (11 invarian, self-cleaning & stok-netral).
Regresi tambahan: `backend/tests/test_iter96_cogs_fifo_journal.py` (13 uji, pytest).

**Kenapa ada:** sesi #34 memasang FIFO keluar — `core.production_qty_ledger.issue_fg` memakan
lapisan biaya tertua dan menuliskan hasilnya ke baris pengiriman (`fg_cogs`, `fg_cogs_layers`,
`fg_cogs_uncosted_qty`). Tetapi `routes.rahaza_posting.post_cogs_on_buyer_dispatch` **tidak pernah
membacanya**: jurnal COGS tetap memakai snapshot HPP per SPK. Jadi satu pengiriman punya DUA angka
biaya — gudang mencatat biaya batch NYATA, buku besar mencatat PERKIRAAN — dan laba per pengiriman
selalu salah **tanpa satu pun galat**. Ini persis pola yang paling mahal di repo ini: dua kebenaran
untuk satu angka rupiah.

- **J1** dasar biaya = `fifo_batch` bila lapisan batch ada, dan nilai jurnalnya **sama persis**
  dengan Σ `fg_cogs` baris pengiriman (bukan mendekati)
- **J2** nilainya dipecah ke akun **BAHAN · UPAH · OVERHEAD** menurut `breakdown` lapisan
  (upah = jahit + permak + upah internal); Σ komponen == total
- **J3** jurnal seimbang & kredit persediaan FG == total COGS
- **J4** memo jurnal **menyebut dasar biayanya** — pembaca laba harus tahu angkanya nyata
  (`biaya batch FIFO`) atau perkiraan (`perkiraan HPP SPK`)
- **J5** idempoten per dispatch (`cogs_job:{shipment}:seq{n}`) — tidak pernah dua jurnal
- **J6** qty yang keluar **tanpa** lapisan biaya DILAPORKAN (`uncosted_qty` + `note`), bukan
  ditutup dengan memaksa memakai lapisan terakhir
- **J6b** SJ **CAMPURAN** (1 baris berbiaya + 1 baris yang keluar TANPA lapisan sama sekali):
  baris yang gratis total tetap disebut. Lubang nyata yang ditemukan penguji sesi #38 — kekurangan
  harus dijumlahkan **sebelum** baris tanpa lapisan dilewati
- **J7** jalan mundur: tanpa lapisan sama sekali, snapshot HPP SPK tetap dipakai dan dasarnya
  disebut `hpp_snapshot` (impor lama tidak putus)
- **J8** tanpa lapisan **dan** tanpa snapshot ⇒ **tidak ada jurnal karangan** (`ok=False`,
  sebabnya disebut)
- **J9** alat ukur tidak meninggalkan sampah (jurnal, baris cermin, lapisan, SJ, stok)
- **J10** rantai **pintu nyata**: lapisan batch masuk (`fg_cost_layers.push_layer`) → stok masuk
  (`core.stock_service.add`) → dikirim (`routes.buyer_shipment._issue_fg_for_dispatch`) → jurnal
  memakai angka itu

⚠️ **Jangan** menambahkan sumber biaya COGS ketiga. Kalau butuh dasar baru, ia harus lewat
`_fifo_cogs_for_dispatch` dan **menyebut namanya** di `basis`.

## INV-F45 (2026-08-26, sesi #40) — IMPOR PINTAR PUNYA PINTU DI LAYAR · PENCAIRAN VOID TIDAK MENGUNCI
Penjaga: `scripts/verify_impor_pintar_pintu_layar.py` (27 invarian, membersihkan artefaknya sendiri).

**Kenapa ada:** audit sesi #40 menemukan DUA fitur yang tercatat "selesai" tetapi tidak pernah bisa
dipakai — bukan karena error, melainkan karena tidak ada pintunya di layar:
1. Langkah 1 layar **Impor Data** menyaring daftar jenis per KELOMPOK
   (`group_key === groupKey`), tetapi **tidak ada satu pun tempat yang mengisi `groupKey`** —
   pemilih 6 kelompok (sesi #37) tidak pernah dirender. Layar menjawab **"0 dari 22 jenis data"**
   saat dibuka; satu-satunya jalan adalah menebak kata kunci pencarian.
2. **Deteksi otomatis** (`POST /api/marketing/data-import/detect`, sesi #34 butir B) hidup dan
   benar di backend, tetapi **tidak dipanggil satu berkas frontend pun**. Fitur tanpa pintu =
   fitur yang tidak ada.
3. Bonus temuan yang ikut dikunci: pencairan marketplace yang jurnalnya sudah **di-void** tetap
   terkunci. Pesan penolakannya menyuruh "void jurnalnya dulu di Portal Finance", padahal
   pemeriksanya hanya melihat ADA/TIDAK `je_id` ⇒ jalan buntu: pencairan salah-input tidak bisa
   diperbaiki maupun dihapus selamanya.

- **F45-1..5** layar memanggil `/source-groups` & `/detect`, `setGroupKey` benar-benar dipakai,
  6 `data-testid` kunci ada, dan tidak ada state yang mati (`groups`, `detectRes`, `showDeprecated`)
- **F45-6..8** kontrak backend: ≥5 kelompok & ≥10 jenis · **tidak ada jenis tanpa kelompok** ·
  **tidak ada kelompok kosong** (kartu yang diklik selalu berisi — akar bug "layar kosong")
- **F45-9,10** deteksi atas berkas ASLI pemilik mengusulkan jenis yang benar **beserta buktinya**
  (kolom cocok, kolom wajib, skor)
- **F45-11** berkas 46 kolom **0 baris** dilaporkan `row_count=0` ⇒ layar memperingatkan SEBELUM
  unggah, bukan menolaknya di langkah berikutnya
- **F45-12..15** selama jurnal pencairan HIDUP: hapus & ubah ditolak **400**
- **F45-16..19** sesudah jurnal **void**: angka bisa diperbaiki (tautan `je_id` DILEPAS,
  `can.edit` hidup lagi) dan pencairannya bisa dihapus
- **F45-20** alat ukur tidak meninggalkan jurnal/pencairan uji

⚠️ **Aturan yang lahir dari sini:** state React yang dideklarasikan tetapi tidak pernah dipakai
(`setX` tanpa pemanggil) pada layar bisnis **bukan sekadar lint** — itu tanda fitur yang hilang saat
berkas dipulihkan/di-refactor. Jalankan `npx eslint src/components/erp/marketing` sesudah menyentuh
layar marketing.
