# PLAN — Adopsi Flow Produksi SOMMERVILLE ke DA
> STATUS: ANALISIS BERJALAN (BELUM eksekusi kode). Plan ini PROGRESS KECIL — baru mencakup
> flow PRODUKSI. Analisis penuh (semua flow) DILANJUTKAN. Lihat SOMMERVILLE_ANALYSIS_HANDOFF.md.
> Update terakhir: sesi analisis awal (setup DA+SOMMERVILLE selesai, app jalan stabil).

## 0. TUJUAN & PRINSIP
- **MAKLON = IDENTIK SOMMERVILLE**: seluruh fitur produksi + FIELD + COLLECTION persis sama.
  Ini jadi implementasi acuan/referensi. Penambahan menyusul saat user test langsung.
- **PRODUKSI INTERNAL = base SAMA** (field/struktur sama biar konsisten & user mudah paham)
  TAPI DISESUAIKAN agar integrasi portal lain jalan (RnD/Gudang/Marketing/Finance/Aksesoris).
- **Pendekatan KERAS**: HAPUS mesin rahaza multi-stage yang cacat + dead code (D1–D5), bukan tambal.
- **Fokus fase-1 flow**: PO -> progress -> yield/output -> fulfillment PO -> shipment.
  SKIP dulu multi-stage lini (cutting/sewing/finishing/QC/packing terpisah, OEE/andon, line balance).

## 1. KEPUTUSAN TERKUNCI (locked)
1. Maklon adopsi COLLECTION + FIELD SOMMERVILLE apa adanya (production_pos, po_items,
   production_jobs, production_progress, buyer_shipments, vendor_shipments, production_variances,
   production_returns, material_requests, po_accessories, dst).
2. Produksi internal pakai STRUKTUR/FIELD sama + lapisan integrasi.
3. Produksi & Maklon DIPISAH — TIDAK ADA lagi work order terpadu ber-flag `source`.
4. Master produk internal SINGLE-SOURCE: RnD -> tentukan BOM -> rahaza_models + rahaza_boms.
   Maklon = snapshot spek KLIEN (tak lewat RnD/katalog marketing).
5. Vendor CMT diberi OWNER eksplisit (business_type: internal|maklon) — perbaiki D4.
6. HAPUS: mesin produksi rahaza multi-stage + endpoint ganda (D1) + dead code (D5).
7. KOREKSI domain: menu "Peminjaman" Aksesoris = ASET/alat (bukan aksesoris).
8. **UI = TETAP SISTEM DA** (keputusan user, sesi ini). Pertahankan portal shell + `moduleRegistry.js`
   + `portalNav.js` + Shadcn. **TIDAK** mengadopsi UI flat SOMMERVILLE. Yang diadopsi dari SOMMERVILLE
   HANYA **fitur + business-logic flow (backend)**; UI-nya dirender ulang / dipakai ulang komponen DA
   yang sudah ada (buat/ubah modul yang plug ke portal shell).
9. **FINANCE = TETAP DA** (keputusan user, sesi ini). **JANGAN clone flow finance SOMMERVILLE**
   (`invoices`/`payments` monolit). DA sudah punya engine finance matang (`rahaza_posting.py`,
   38 posting profiles). → Maklon finance TETAP `dewi_maklon_finance` (AR jasa/DP/AP CMT) = **FIN-2 = Opsi B (LOCKED)**.
   Produksi internal tetap pakai engine finance DA (adapter costing re-key ke `production_jobs`, BUKAN finance SOMMERVILLE).
10. **SCOPE ADOPSI (LOCKED — arahan user, sesi ini). Adopsi dari SOMMERVILLE HANYA:**
    (a) **Logic produksi / flow bisnis**, (b) **master data produksi**, (c) **tracking**, (d) **portal VENDOR (CMT)**.
    **JANGAN adopsi**: finance, **system admin/settings**, **manajemen akun/user/auth/role SOMMERVILLE**,
    UI shell SOMMERVILLE, buyer-portal terpisah, dan modul lain yang tak relevan → semua itu **PAKAI DA**.
    (Detail tabel di §1b.)
11. **KEPUTUSAN DECISION POINTS (LOCKED — user, sesi ini):**
    - **FIN-1 = A**: costing penuh WIP→FG→COGS, **adapter re-key ke `production_jobs`** (bukan rahaza WO).
    - **HR-1 = CAMPURAN** (borongan + bulanan) → **WAJIB pertahankan capture output per-operator/proses**
      (piece-rate tetap; rahaza multi-stage boleh dibuang TAPI output log per-operator dipertahankan).
    - **GDG-2 = A** (`draft-from-job`), **GDG-1 = YA** (owner `business_type` CMT dispatch).
    - **QC-1 = B** (pertahankan `dewi_maklon_qc_checks`), **QC-2 = BUANG** (Pareto/FPY per-line dihapus),
      **RET-1 = A** (after-sales R3), **MKT-1 = B** (onward CTA), **MKT-2/ACC-2 = YA**, **ACC-1 = A** (auto explode BOM),
      **RBAC-1 = B** (role-string hardcode DA; remap saat port).
    - Aset (AST-1/2/3) = **prio rendah** (tunda). Desain adapter → `PRODUKSI_E10_ADAPTER_MIGRASI.md`.

## 1b. SCOPE ADOPSI — ADOPT vs SKIP (LOCKED)
### ✅ ADOPT (SOMMERVILLE → DA, backend logic + rendered di UI DA)
| Kategori | Item SOMMERVILLE | Target DA |
|---|---|---|
| (a) Logic/flow produksi | endpoint+collection: production-pos, po-items, po-accessories, vendor-shipments(+items), vendor-material-inspections(+items), material-requests, production-jobs(+items), production-progress, production-variances, production-returns(+items), buyer-shipments(+items), material-defect-reports | Portal Produksi (internal) & Portal Maklon (identik) |
| (b) Master data produksi | products, product-variants, garments (vendor CMT) | internal → `rahaza_models`/variants (RnD→BOM); maklon → snapshot; garments → `cmt_vendor` |
| (c) Tracking | serial tracking, progress tracking, shipment tracking (remaining-to-ship, dispatch_seq, over/under, child jobs) | fitur tracking di modul produksi/maklon DA |
| (d) Portal VENDOR (CMT) | VendorDashboard, VendorReceiving, VendorMaterialInspection, VendorMaterialRequests, VendorProductionJobs, VendorProgress, VendorBuyerShipments/ShipmentModule, VendorDefectReports, VendorVarianceReport, VendorSerialTracking, VendorReminderInbox | Portal `cmt_vendor` DA (role+`cmt_vendor_id` sudah ada) — **UI komponen DA**, bukan `VendorPortalApp.jsx` SOMMERVILLE |

### ❌ SKIP (JANGAN adopsi — pakai punya DA)
| Kategori | Item SOMMERVILLE (skip) | Alasan / ganti |
|---|---|---|
| Finance | invoices, payments, AccountsPayable/ReceivableModule | DA `rahaza_posting` + `dewi_maklon_finance` (FIN-2 locked) |
| System admin/settings | company-settings, CompanySettingsModule, data-management | DA punya `company_settings` + settings sendiri |
| Akun/User/Auth/Role | /auth, /users, /roles, /permissions, UserManagement/RoleManagement/BulkAddUser | DA `auth.py` + RBAC portal-based (E8) TETAP |
| UI shell | VendorPortalApp/BuyerPortalApp/App.js state-based, UI flat | DA portal shell + moduleRegistry (decision #8) |
| Buyer portal | Buyer* modules sebagai portal terpisah | internal: "buyer"=customer via Marketing; maklon: `klien_maklon` view — TIDAK port portal buyer |
| Infra lain | websocket/reminder/smart-import SOMMERVILLE (jika ada) | pakai padanan DA bila perlu |

## 2. REFERENSI FIELD SOMMERVILLE (grounded — SAMPEL, lengkap di analisis lanjut)
- **production_pos**: id, po_number, customer_name, buyer_id, vendor_id, vendor_name,
  po_date, deadline, delivery_deadline, status, notes, created_by, created_at, updated_at
  (close: close_reason, close_notes, closed_by, closed_at)
- **po_items**: id, po_id, po_number, product_id, product_name, variant_id, size, color, sku,
  qty, serial_number, selling_price_snapshot, cmt_price_snapshot, created_at
  (CATATAN: sudah bawa 2 harga -> selling utk internal, cmt utk maklon)
- BELUM diekstrak (TODO analisis): production_jobs, production_job_items, production_progress,
  buyer_shipments(+items+dispatches), vendor_shipments(+items), vendor_material_inspections,
  material_requests, production_variances, production_returns(+items), po_accessories,
  accessory_* , invoices, payments.

## 3. FASE EKSEKUSI (DRAFT — final setelah analisis penuh)
> **Prinsip baru (sesi ini): BACKEND-FIRST, UI-LAST.** Karena UI = TETAP DA (hanya reuse komponen) &
> container 1 CPU/2GB (rebuild FE mahal), semua adopsi dikerjakan di backend + POC test dulu; sentuhan
> frontend dibatch & di-build sekali; **UI testing HANYA di AKHIR** (lihat §7).
- **Fase 0 — Persiapan**: freeze versi SOMMERVILLE acuan; ekstrak FIELD INVENTORY LENGKAP
  tiap collection (✅ E1 selesai); petakan endpoint SOMMERVILLE (153) yang dipakai flow progress.
- **Fase 1 — ANALISIS PENUH (SEDANG BERJALAN)**: selesaikan mapping SEMUA flow (E1–E9). Output
  tiap bagian = tabel AS-IS vs TO-BE (✅ E1–E6 selesai; sisa E7–E9).
- **Fase 2 — MAKLON (fitur+flow) identik**: port BE **business logic** SOMMERVILLE ke Portal Maklon,
  field/collection persis. **UI: reuse komponen DA** (BUKAN port FE SOMMERVILLE). **Finance: TIDAK di-clone**
  (pakai `dewi_maklon_finance`). Bawa daftar bug SOMMERVILLE (C-1..M-3) → fix saat port, jangan warisi.
- **Fase 3 — PRODUKSI internal**: base flow sama + adapter integrasi (RnD master, Gudang material,
  Marketing demand/catalog, **Finance DA** GL, Aksesoris). UI = modul DA (portal shell).
- **Fase 4 — HAPUS D1–D5**: setelah TO-BE tervalidasi (rahaza multi-stage engine + dead code).
- **Fase 5 — BRIDGES + TEST**: bridge Finance(DA)/Gudang/HR; **backend test via POC script per-flow
  (tanpa build FE)**; **UI E2E testing_agent DIJALANKAN TERAKHIR** setelah 1× build final.

## 7. STRATEGI DEV DI BATAS 1 CPU / 2 GB (WAJIB — biar development smooth)
> Sumber kendala: FE = static bundle (lihat `memory/PREVIEW_STABLE_MODE.md`). `yarn build` makan
> beberapa menit @1 core (nice-19, heap 1024MB, minify+sourcemap OFF), **tak ada hot reload**;
> `craco start` DILARANG (loop 5 mnt → pod restart). Backend hot-reload murah.
**Aturan kerja (untuk semua fase eksekusi):**
1. **Backend dulu, frontend belakangan.** Semua logic adopsi = backend (endpoint + collection + guard).
   Backend uvicorn `--reload` → perubahan instan, TANPA build.
2. **Validasi backend pakai POC script** (`tests/flow_*_test.py`) via `python3` — TANPA menyentuh FE.
   Ini menggantikan "cek di UI" selama development (murah, cepat, deterministik).
3. **Batch perubahan frontend.** Jangan `rebuild_frontend.sh` tiap edit kecil. Kumpulkan SEMUA edit
   `frontend/src` satu feature, lalu **build SEKALI** di akhir batch. Preview tetap layani build lama.
4. **UI testing di AKHIR saja** (arahan user). `testing_agent_v3` untuk FE dijalankan **satu kali**
   setelah build final tiap fase besar — bukan per-perubahan. Skip drag&drop/kamera/voice.
5. **Reuse komponen DA, minim dependency baru.** Jangan `yarn add` library besar (menaikkan ukuran
   bundle + waktu/memori build → risiko OOM). UI dari komponen/pola yang sudah ada.
6. **Jaga heap < cap.** Build heap 1024MB + backend + mongo harus < 2GB (cek `fe_build.log`; jika OOM,
   turunkan heap / tutup proses lain saat build). Build selalu `nice -n 19`.
7. **Rebuild command tunggal:** `bash /app/scripts/rebuild_frontend.sh` (build low-prio → reload static server).
8. **Jangan ubah** `.env` kritikal (JWT_SECRET/MONGO_URL/REACT_APP_BACKEND_URL) & jangan `craco start`.

## 8. STANCE UI (LOCKED — arahan user)
- **Pertahankan UI DA**: `App.js` portal shell, `PortalSelector`, `moduleRegistry.js`, `portalNav.js`, Shadcn.
- Flow SOMMERVILLE dirender via **modul DA baru/diubah** yang plug ke portal shell + registry + onward CTA.
- **Tidak** ada port `VendorPortalApp`/`BuyerPortalApp`/App.js state-based SOMMERVILLE.
- Kandidat penempatan: modul Produksi baru (PO→progress→yield→shipment) menggantikan modul rahaza multi-stage
  di Portal Produksi; Maklon pakai modul Maklon DA yang sudah ada + tambah flow yang kurang.

## 4. RISIKO & MITIGASI
- Adopsi bug SOMMERVILLE -> mitigasi: daftar bug audit dibawa & difix saat port + verifikasi testing_agent.
- Tabrakan collection generik (users/roles/products/garments/company_settings/attachments) ->
  JANGAN timpa buta; rekonsiliasi ke auth/portal DA.
- Master produk fork (products SOMMERVILLE vs rahaza_models) -> Produksi internal WAJIB rujuk rahaza_models.
- ENV: JANGAN `craco start` (loop). FE = static bundle; setelah ubah src: `bash /app/scripts/rebuild_frontend.sh`.

## 5. YANG BELUM DIANALISIS (lanjut — lihat handoff)
Gudang detail · QC/retur · Finance GL bridge · Marketing catalog/demand/fulfillment · HR piece-rate ·
Aset + peminjaman aset · RBAC role mapping (vendor/buyer/cmt_vendor vs portal DA) · field inventory lengkap.

## 6. DOKUMEN TERKAIT (memory)
- SOMMERVILLE_ADOPTION_ANALYSIS.md (analisa lineage + integrasi)
- PRODUKSI_LOGIC_DEFECTS.md (D1-D5 grounded)
- PRODUKSI_MAPPING_ASIS_TOBE.md (tabel AS-IS vs TO-BE)
- PRODUKSI_TOBE_ECOSYSTEM_MAP.md (peta menyeluruh + edge integrasi)
- SOMMERVILLE_ANALYSIS_HANDOFF.md (cara & sisa analisis)
