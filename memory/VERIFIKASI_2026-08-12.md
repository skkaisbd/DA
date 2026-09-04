# VERIFIKASI 2026-08-12 — Apa yang BENAR-BENAR rusak, apa yang SUDAH beres

**Sifat dokumen:** buku bukti. Setiap baris di sini punya (a) berkas + nomor baris, atau
(b) angka yang bisa dihitung ulang dengan satu perintah. Tidak ada opini.

**Kenapa dokumen ini ada:** rencana lama (`memory/RENCANA_EKSEKUSI_MARKETING_2026-08-11.md`)
berisi pekerjaan yang **sudah dikerjakan** (mis. "3 rumus qty katalog" sudah disatukan).
Kalau agent AI mengeksekusinya apa adanya, ia akan **mengulang** pekerjaan dan/atau
menimpa perbaikan yang sudah benar — persis keluhan owner: *"duplikasi duplikasi"*.
Dokumen ini memisahkan **MASIH RUSAK** dari **SUDAH BERES** sebelum satu baris kode ditulis.

---

## 0. Lingkungan pembuktian (bisa diulang)

| Hal | Nilai |
|---|---|
| Repo | `github.com/jejahahabsasda/DA` → disalin ke `/app` |
| Database | `test_database`, **di-restore** dari `backups/auto_20260810_190000` (mongorestore --gzip --drop) |
| Bootstrap | `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh --skip-deps` → backend healthy, 6 akun login HTTP 200 |
| Berkas nyata | `samples/TikTok_UntukDikirim_2026-07-19.xlsx` — 1 sheet `OrderSKUList`, **65 kolom**, 603 baris (baris 1 header, **baris 2 = deskripsi kolom**, 601 baris data) |
| Skala sistem | **2.277** endpoint (`routes/`), **326** endpoint marketing, **386** koleksi disebut kode, **192** koleksi ada di DB, **284 + 40** modul UI |
| Data marketing di DB | **0 dokumen** untuk semua koleksi marketing (kecuali 3 akun DEMO) ⇒ semua cacat di bawah dibuktikan dari **KODE + berkas nyata**, bukan dari isi DB |

### Harness (READ-ONLY) yang dipakai
| Skrip | Fungsi |
|---|---|
| `scripts/_forensic_ssot_v3.py` **(baru)** | matriks akses koleksi (siapa nulis/baca, file:line), koleksi "kubur"/"selalu kosong", pulau 1-berkas, duplikasi konsep, jenis impor → koleksi → pembaca. Output `memory/FORENSIC_SSOT_V3.json` |
| `scripts/_audit_ui_tables_v2.py` **(baru)** | audit UI sadar-`GlassCard`: kartu-saja, jumlah kolom tabel, ada/tidak pengalih tampilan. Output `memory/AUDIT_UI_TABLES_V2.json` |
| `scripts/_prove_import_orders_result.py` | jalankan `build_rows()` produksi pada berkas nyata |
| `scripts/_analyze_seller_center_export.py` | bongkar 65 kolom + matematika dobel |
| `scripts/_prove_sales_cycle.py` | siklus target/omzet/anggaran (8 pemeriksaan keterhubungan) |
| `scripts/_prove_catalog_master_gaps.py` | ⚠️ **STALE — JANGAN DIPERCAYA** (lihat §3) |

---

## 1. ANGKA BERKAS NYATA (dasar semua gate di rencana eksekusi)

```
baris data                        601      pesanan unik                     559
baris per pesanan (maks)            4      (Order ID, SKU ID) ganda           0   ← items[] aman
total pcs                         603      SKU ID unik                       83   → 8 nama produk induk

Σ SKU Subtotal After Discount   Rp 59.783.811   ← OMZET PRODUK (dasar Target, default)
Σ Order Amount (per pesanan 1×)  Rp 62.805.113   ← yang dibayar pembeli (termasuk ongkir)
Σ SKU Subtotal Before Discount  Rp 109.179.000
Σ SKU Seller Discount            Rp 48.020.983   ← 80,3% dari omzet produk; biaya promosi TERBESAR
Σ SKU Platform Discount           Rp 1.374.206
Σ Shipping Fee After Disc (1×)    Rp 1.744.000

Order Channel   LIVE  Rp 42.364.407 (70,9%, 389 pesanan) · Videos Rp 9.590.333 (16,0%, 96)
                Product cards Rp 7.829.071 (13,1%, 78)
Creator Handle  32 unik · iori.oliviara Rp 26.942.611 (45,1%) · vivin.ir1994 Rp 10.936.791 (18,3%)
                · tanpa kreator Rp 7.979.170 (13,3%)
Normal or Pre-order   Pre-order 514 baris · Normal 87 baris
Status                'Perlu dikirim' 601 · Substatus: Menunggu pengambilan 597 / pengiriman 4
Kurir                 J&T Express 596 · JNE Express Standard ID 1 · kosong 4
Warehouse Name        'Outfit Boutique' 601   ← cocok dgn COA 4-122 "Penjualan – TikTok Outfit Boutique"
Waktu                 Created 601 · Paid 108 · RTS 597 · Shipped 0 · Delivered 0 · Cancelled 0
Format tanggal        'DD/MM/YYYY HH:MM:SS' (teks)
```

---

## 2. MASIH RUSAK — cacat terverifikasi (D01–D21)

> Kolom **Fase** merujuk `memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`.

| ID | Cacat (terbukti) | Bukti | Dampak terukur | Fase |
|---|---|---|---|---|
| **D01** | Impor `sales_daily` menulis dokumen **RATA** (`revenue`, `orders`, `aov` di akar), sedangkan input manual menulis **BERSARANG** (`metrics{}`, `fulfillment{}`, `customer_satisfaction{}`, `live_metrics{}`) | penulis impor: `routes/marketing_data_import.py::_finish` cabang `st.key == "sales_daily"` (hanya menghitung `aov`, tidak membungkus); penulis manual: `routes/marketing_sales.py:59-95` | Target baca `metrics.revenue` (`routes/marketing_targets.py:158-159`) ⇒ **Rp 0**; Dashboard **HTTP 500**; Health Score **15 vs 89** untuk angka yang sama | **F0** |
| **D02** | Dashboard mengindeks langsung `sale["metrics"]`, `sale["account_id"]` (tanpa `.get`) | `routes/marketing_dashboard.py:62,63,66,72` | satu dokumen cacat ⇒ **seluruh layar mati** (500), bukan satu angka kosong | **F0** |
| **D03** | Indeks `marketing_sales_data(account_id,date,revenue_type)` **TIDAK unique** | `backend/server.py:842-845` (`name="sales_account_date_type"`, tanpa `unique=True`) | rekap harian bisa dobel ⇒ omzet bulanan bisa terhitung 2× tanpa galat | **F0** |
| **D04** | Jenis impor `orders` **tidak bisa membaca ekspor TikTok nyata** | `scripts/_prove_import_orders_result.py` pada berkas nyata | **601/601 baris DITOLAK**, omzet tercatat **Rp 0** dari Rp 59.783.811; **55/65 kolom dibuang**; baris ke-2 (deskripsi) masuk sebagai "pesanan" palsu; dedupe `(account_id, order_id)` akan **menelan 42 baris SKU** dari 36 pesanan multi-SKU | **F1** |
| **D05** | Sales Performance: `total_revenue = $sum:'$total_payment'` **per baris**, `total_orders = $sum:1`, filter memakai **`account_name` (teks)** hasil terjemahan dari `account_id` | `routes/marketing_sales_performance_routes.py:64-88` | pada berkas nyata **+16,8% = Rp 10.572.124** dobel; ganti nama toko ⇒ riwayat lama hilang **tanpa galat** | **F1/F2** |
| **D06** | Mesin impor AI lama **masih hidup & terdaftar**, menyimpan tebakan AI apa adanya ke koleksi yang tidak pernah dibaca | `routes/universal_import.py:766-778` → `discount_campaign` → `marketing_discount_campaigns`, `sample_shipping` → `marketing_sample_shipments`, jenis tak dikenal → `marketing_import_<apa pun>`; **`sales_data` tidak ada di peta** ⇒ rekap penjualan jatuh ke `marketing_import_sales_data` (**0 pembaca**). Commit `doc = {..., **committed_data}` (baris 787-800) **tanpa** `scope.stamp_account()` (tidak ada `account_id`) dan **tanpa dedupe** (`insert_one` polos ⇒ commit 2× = data dobel). UI: tab "Sesi AI (lama)" (`ImportCenterModule.jsx:40-56`) | data "berhasil diimpor" lalu **tidak muncul di mana pun**; filter per toko kosong; nama kolom Excel jadi nama field DB | **F0.6 (HAPUS TOTAL)** |
| **D07** | **EMPAT** mesin impor hidup bersamaan; dua di antaranya **berbagi ruang URL yang sama**: `/api/marketing/import/*` (universal_import, AI) · `/api/marketing/import/upload`+`/import/{upload_id}` (marketing_import.py, khusus sales) · `/api/marketing/data-import` (unified tanpa AI, **yang benar**) · `SmartImportModule.jsx` (UI zombie, lihat D23) | `server.py:1613-1614` memuat komentar pengembang sebelumnya: *"universal_import_router MUST be registered BEFORE marketing_import_router to prevent /api/marketing/import/sessions being matched as /{upload_id}"* — artinya `GET /import/sessions` bisa tertangkap sebagai `GET /import/{upload_id}` dengan `upload_id="sessions"` | kebenaran aplikasi bergantung pada **urutan baris `include_router`**: merapikan urutan impor = satu layar mati tanpa galat yang jelas | **F0.6 (HAPUS TOTAL)** |
| **D08** | Anggaran & Iklan = **PULAU**: `marketing_budgets`, `marketing_spend_entries` hanya disentuh `routes/marketing_budget.py`; `marketing_ads_data` hanya `routes/marketing_ads_routes.py` | `memory/FORENSIC_SSOT_V3.json` → `single_file_islands` | 8/8 pemeriksaan keterhubungan target⇄anggaran⇄pesanan⇄jurnal = **TIDAK** (`_prove_sales_cycle.py` S4); realisasi `ads` diketik manual padahal datanya ada | **F5** |
| **D09** | Biaya promosi TERBESAR tidak masuk Anggaran | `SKU Seller Discount` ada di ekspor; kategori `diskon` diisi manual (`routes/marketing_budget.py:167-178`) | **Rp 48.020.983 / 2 minggu** tidak tercatat otomatis | **F5** |
| **D10** | Target/Anggaran/Omzet: **tanpa RBAC**, **tanpa kunci periode**, **tanpa riwayat nilai lama** | `routes/marketing_targets.py:35` & `routes/marketing_budget.py:222` hanya `require_auth`; tidak ada koleksi lock | siapa pun yang login bisa menimpa target bulan lalu; nilai lama hilang tanpa jejak | **F5/F6** |
| **D11** | `pic_id` / `assigned_staff` **ada di data tapi tidak pernah ditegakkan**; role "Supervisor Marketing" di-seed sebagai `pic_toko`; tidak ada role `spv_marketing`/`staff_marketing`/`content_creator`/`host_live` | 0 lokasi kode menggabungkan user→lingkup toko (grep `pic_id` + `user`); `backend/auth.py:225-255` daftar role; `memory/SEED_CREDENTIALS.md` | setiap staf melihat & bisa mengubah **semua** toko | **F6** |
| **D12** | Katalog **tidak punya status penayangan**: hanya `is_active` (bool) + `stock_status` (`in_stock`/`low_stock`/`out_of_stock`) | `routes/marketing_catalog_items.py:646-664`, `core/catalog_stock.py:326` | tidak bisa membedakan DRAFT / PRE-ORDER / ACTIVE / HABIS / ARSIP — padahal **514 dari 601** baris ekspor nyata berstatus *Pre-order* | **F4** |
| **D13** | Rantai **FOTO** putus di FG→katalog | unggah RnD: `routes/dewi_rnd_styles.py:582` → `design_images`; dibawa ke master: `dewi_rnd_styles.py:481` (`rahaza_models.image_paths`); **`rahaza_materials` (FG) tidak punya field foto**; `POST /items/from-fg` (`marketing_catalog_items.py:640`) menyalin 40+ field **tanpa** foto; `refresh-from-master` (`:852`) juga tidak menyalin foto | item katalog dari master **selalu lahir tanpa foto**, padahal fotonya sudah ada di master RnD | **F4** |
| **D14** | **DUA layar katalog** untuk data yang sama, kemampuan berbeda | `CatalogManagementModule.jsx` (1.817 baris, tabel 20 kolom, **0 dukungan foto**) vs `TokoProductCatalogModule.jsx` (690 baris, **kartu-saja**, 0 tabel, foto ADA) | staf melihat dua kebenaran; perbaikan harus dikerjakan 2× | **F4** |
| **D15** | Rencana konten **tanpa pemilik, tanpa link video terbit, tanpa KPI** | `routes/marketing_content_calendar_routes.py:127-138` — field: account, platform, date, content_type, title, description, cta, post_time, reference_link, status | laporan performa content creator **mustahil dibuat** | **F7** |
| **D16** | **Tidak ada laporan mingguan** | `routes/marketing_reports.py` hanya `/daily`, `/monthly`, `/monthly/export-pdf` | rapat mingguan tidak punya sumber angka | **F8** |
| **D17** | Cakupan KPI e-commerce tipis | `core/marketing_import_schema.py` SALES = 20 field | **tidak ada**: buyers, unit dipesan/dibayar, UV, PV, product clicks, CTR, ATC, cart→order, order→paid, pembeli baru vs lama, pecahan sumber trafik, GPM, impresi, durasi tonton, PCU, metrik video, kreator aktif, SPS, waktu proses | **F8** |
| **D18** | **Tidak ada impor Pencairan/Settlement** ⇒ uang REAL tidak pernah masuk Finance dari marketplace | 0 hasil grep `settlement/pencairan` di `routes/marketing_*`; jalur lama Marketing→AR sengaja dimatikan (`components/erp/MarketingARBridgeModule.jsx`) | omzet marketing dipakai sebagai angka performa, **tidak ada** jalur uang cair ke jurnal | **F9** |
| **D19** | UI memaksa kartu untuk data banyak | `memory/AUDIT_UI_TABLES_V2.json`: **95/240** modul kartu-saja. Yang paling menyakitkan: `TokoOrdersModule.jsx` (1.055 baris, kartu-saja, 36 field), `TokoProductCatalogModule.jsx`, `SampleDeliveryModule.jsx`, `DailyReportModule.jsx`. Tabel tipis: `KOLCreatorModule` 2 kolom, `UnifiedOrdersDashboard` 3 kolom, `AdsPerformance`/`SalesPerformance`/`LiveSession` 1 kolom. **Hanya 7** modul punya pengalih tampilan | daftar panjang tidak bisa dibaca/di-sort/di-ekspor | **F4/F8/F10** |
| **D20** | Lubang data terukur | `FORENSIC_SSOT_V3.json`: **13** koleksi ditulis-tak-pernah-dibaca · **28** dibaca-tak-pernah-ditulis (mis. `marketing_kol_campaigns` dibaca `routes/dewi_executive_report.py:247` ⇒ laporan eksekutif selalu 0) · **156** pulau 1-berkas · **10** pasangan koleksi konsep-sama (`marketing_budgets`↔`rahaza_budgets`, `marketing_orders`↔`rahaza_orders`, `payroll_runs`↔`rahaza_payroll_runs`, …) | angka nol yang salah ikut dibawa ke rapat | **F0/F10** |
| **D21** | `marketing_orders` tidak punya indeks unik `(account_id, order_id)`; `order_id` hanya indeks biasa; **tidak ada** indeks `account_id` | `routes/marketing_orders_routes.py:186-194` | impor ulang bisa menggandakan pesanan; filter per toko lambat | **F1** |
| **D22** | Master toko **tidak tertaut ke Finance** | `marketing_platform_accounts` (dokumen nyata) = `account_code, account_name, username, platform, group, status, pic_id, assigned_staff, health_score, credentials, import_config` — **tidak ada** `coa_*` | COA sudah punya akun per toko (`4-111`…`4-131`) tapi **tidak pernah dipakai**; DB hanya berisi 3 toko DEMO, bukan 9 toko nyata | **F0/F9** |
| **D23** | **Mesin impor KE-EMPAT yang bahkan tidak bisa dibuka** | `frontend/src/components/erp/SmartImportModule.jsx` di-`lazy()` di `moduleRegistry.js:384` **tetapi tidak pernah dipetakan ke id modul mana pun** ⇒ tidak ada menu/deeplink yang bisa membukanya. Ia memanggil `/api/marketing/import/upload|analyze|preview|execute|rollback` + `/api/marketing/import-templates` | kode mati yang tetap dibaca agent berikutnya sebagai "fitur" ⇒ sumber kebingungan & duplikasi berulang | **F0.6 (hapus)** |
| **D24** | Job pembersih unggahan **tidak pernah membersihkan apa pun** | `backend/utils/scheduler.py::job_cleanup_old_marketing_uploads` menunjuk `/app/uploads/marketing` — folder itu **tidak ada**; yang nyata `/app/uploads/marketing-data-import` (jalur benar) & `/app/uploads/marketing-imports` (mesin lama) | disk terus terisi berkas impor; log hanya menulis "not found, skipping" sehingga terlihat sehat | **F0.6(e)** |

---

## 3. SUDAH BERES — JANGAN DIKERJAKAN ULANG (anti-duplikasi)

> Ini yang membuat rencana lama berbahaya bila dieksekusi mentah.

| Klaim lama | Keadaan SEBENARNYA hari ini | Bukti |
|---|---|---|
| "Stok katalog punya **3 rumus** berbeda (M1)" | **SUDAH SATU RUMUS.** `core/catalog_stock.py` (K-6a/K-7a) adalah SSOT; ketiga pintu memanggilnya | `core/catalog_stock.py:1-30` (docstring keputusan), `marketing_catalog_items.py:588` (`_cstock.sellable_stock`), `marketing_catalog_stock.py:309` (`_cstock.item_sellable`) |
| "Item baru lahir stok 0 (M2)" | **SUDAH DIPERBAIKI** — `from-fg` memakai `sellable_stock()` | `marketing_catalog_items.py:586-590` |
| "`sync-from-wms` abaikan `reserved` (M3), baca `qty` mentah (M4), lewati `variant_sku` (M5)" | **SUDAH DIPERBAIKI** — semua lewat SSOT + `read_qty()`/`read_reserved()` | `core/catalog_stock.py:33` (impor `core.stock_schema`), `marketing_catalog_stock.py:275-315` |
| "Tidak ada penyegar dari master (M7)" | **ADA** `POST /{catalog_id}/refresh-from-master` + `refresh-hpp` (satu item & seluruh katalog) | `marketing_catalog_items.py:806,827,852` |
| "`from-fg` tidak cek produk non-aktif (M8)" | **SUDAH DICEK** (400 bila FG/model non-aktif) | `marketing_catalog_items.py:560-578` |
| "Order tidak menyimpan tautan master (M9)" | **SUDAH** — `catalog_item_id`, `fg_material_id`, `variant_id`, `model_id`, `master_link_source` | `marketing_orders_routes.py:723-731` |
| "Marketing menulis AR/jurnal Finance" | **SUDAH DIMATIKAN** (Keputusan #1) | `components/erp/MarketingARBridgeModule.jsx` (modul sengaja dinonaktifkan) |
| "Dokumen marketing tanpa `account_id`" | **SSOT lingkup toko SUDAH ADA** dan dipakai importir unified (`scope.stamp_account`) | `core/marketing_account_scope.py`, `marketing_data_import.py:911-915` |
| "Impor harus menebak jenis data dengan AI" | **SUDAH ADA jalur tanpa AI** dengan 16 jenis tertulis + template + pratinjau + rollback, dan **sudah jadi tab utama** | `core/marketing_import_schema.py` (`SOURCE_TYPES`), `routes/marketing_data_import.py`, `components/erp/ImportCenterModule.jsx:37` |
| "Rincian produk sesi live tidak ada" | **ADA** jenis `live_session_products` + pagar anti-dobel-hitung | `marketing_import_schema.py:313`, `marketing_data_import.py:874-887` |
| "Katalog tidak melaporkan item bermasalah" | **ADA** `attention=unlinked|stale|all`, `in_sync`, `available` live, `margin`, `price_delta_vs_master` — dihitung untuk **seluruh** katalog | `marketing_catalog_items.py:932-1060` |

### ⚠️ Peringatan alat lama
`scripts/_prove_catalog_master_gaps.py` **memberi label terbalik & basi**: ia melaporkan
`M4/M5/M6/M7/M8/M9` sebagai "TIDAK TERBUKTI" sambil mencetak bukti bahwa cacatnya ADA,
dan melaporkan `M1/M2` "TERBUKTI" padahal endpoint-nya sudah memakai SSOT (skrip
menghitung ulang rumus LAMA secara inline, bukan memanggil endpoint). **Jangan pakai
skrip itu sebagai gate.** Gate yang sah: `scripts/_forensic_ssot_v3.py` +
`scripts/gate_marketing_ssot.py` (dibuat di F0).

---

## 4. TIDAK BISA DIVERIFIKASI SEKARANG (harus diukur ulang setelah ada data nyata)

| Hal | Kenapa | Kapan bisa diukur |
|---|---|---|
| "field dibaca tapi tidak ada di dokumen" per koleksi | 18 koleksi marketing **kosong** ⇒ `scripts/audit_marketing_field_reads.py` melaporkan *tak ternilai* | setelah F1 (impor nyata masuk) — jalankan ulang, wajib **0 pasti_cacat** |
| integritas rujukan (`account_id`, `catalog_item_id`, `creator_id`) | idem | setelah F1/F4 — `scripts/audit_marketing_integrity.py` wajib **0 rujukan cacat** |
| Kolom laporan **Pencairan/Settlement** TikTok & Shopee | **berkas contoh belum ada** | **BLOKIR-DATA F9** — owner mengirim 1 contoh per platform |
| Kolom ekspor **KPI/funnel** (Shopee "Data Toko", TikTok "Analisis") | berkas contoh belum ada | **BLOKIR-DATA F8** — kalau tidak ada, jalur form input mingguan tetap dibangun (keputusan owner: siapkan keduanya) |
| Ekspor B/C (Dikirim/Selesai, Batal/Retur) | belum ada contoh; berkas A punya `Shipped/Delivered/Cancelled Time` **kosong 100%** | **BLOKIR-DATA F3** (bisa mulai dengan asumsi kolom identik dgn A — dinyatakan eksplisit di F3) |
