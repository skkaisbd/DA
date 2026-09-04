# 🗂️ IA RESTRUCTURE PROPOSAL — Usulan Perombakan Struktur Menu (RC-IA-01)
> **UPDATE Session #26 — user MENYETUJUI rekomendasi 1a/2a/3a/4a → DIEKSEKUSI & TERVERIFIKASI:**
> - **CUTI (1a)**: notif in-app "Cuti Disetujui + Sisa saldo" ke karyawan (backend `rahaza_leave.approve_leave`). E2E OK. Struktur pintu cuti tetap (1 request `portal-cuti` + 1 approve `hr-leave`; `leave-header` = header, `portal-workspace` = launcher).
> - **EXPENSE (2a)**: banner "Inbox bersama SDM & Keuangan" di 2 modul dual-surface (fin-expenses vs fin-expense-settlement = beda fungsi, by-design).
> - **OPNAME (3a)**: `wh-accessory-ops` (Gudang) → redirect ke Portal Aksesoris (`accessories-master-stock`), relabel "Aksesoris (Portal Aksesoris)"; opname MATERIAL tetap `wms-stock-hub` (2 domain resmi terpisah).
> - **PAYSLIP (4a)**: `portal-payslip` sumber tunggal; kartu/quick-action dashboard sudah nge-link ke sana (terverifikasi).
>
> Deliverable BAGIAN 8 `SSOT_MASTER_REPAIR_PLAN_PART5.md`. **Status awal: MENUNGGU PERSETUJUAN USER** (kecuali bug jelas kelas 8.1 yang sudah diperbaiki: portal Aset).
> Basis bukti: ekstraksi `portalNav.js` + `moduleRegistry.js` + deteksi otomatis 8.1 (2026-07-02).

---

## BAGIAN 1 — HASIL DETEKSI "≥2 MENU → KOMPONEN SAMA" (semua portal)

| Komponen | Menu | Vonis | Tindakan |
|---|---|---|---|
| `AssetManagementPortal` | asset-dashboard / asset-list / asset-procurement | ❌ DUPLIKAT (pindah menu tak berubah) | ✅ **SUDAH FIX** (defaultTab per menu, testing agent 9/9 PASS) |
| `ProcessExecutionModule` | prod-exec-cutting/sewing/finishing/qc/rework/packing | ✅ SAH | Terdiferensiasi via prop `moduleId` → processCode berbeda per menu |
| `EmployeeExpenseApprovalModule` | hr-expense-approval + fin-expense-settlement | ✅ SAH (dual entry-point disengaja, ada komentar kode) | Opsional: samakan label agar user paham ini layar sama |
| `EmployeeTravelSettlementModule` | hr-travel-settlement + fin-settlement-queue | ✅ SAH (idem) | idem |
| `KREATORRequestModule` | marketing-kreator-requests + rnd-kreator-requests | ✅ SAH (inbox lintas-portal) | — |
| `AccessoryRequestInbox` | warehouse-accessory-requests + rnd-accessory-requests + accessories-inbox | ✅ SAH (inbox lintas-portal) | Lihat usulan W-3 (kurangi di warehouse) |
| `makeModuleWithTab` group (accessories-*) | 5 menu portal Accessories | ✅ SAH | Sudah ber-tab berbeda |

**Kesimpulan**: duplikat rusak tersisa = **0**.

---

## BAGIAN 2 — MATRIKS PORTAL WAREHOUSE (22 menu, 3 seksi) + IRISAN

### 2.1 Peta sekarang (menu → komponen → urusan)
| Seksi | Menu | Komponen | Urusan inti |
|---|---|---|---|
| INVENTORI | warehouse-dashboard | WarehouseDashboard | ringkasan |
| INVENTORI | wh-master | WarehouseMasterHub | master material+FG |
| INVENTORI | **wh-stock** | RahazaStockModule | **stok & pergerakan** (rahaza_material_stock/movements) |
| INVENTORI | wh-material-issue | RahazaMaterialIssueModule | pengeluaran material |
| INVENTORI | **unified-inventory** | UnifiedInventoryModule | **viewer stok gabungan** (wms/stock/unified) |
| OPERASIONAL | wh-purchase-orders → wh-receiving → wh-putaway | PO/GRN/PutAway | inbound |
| OPERASIONAL | wh-supplier-scorecard | SupplierScorecard | kualitas vendor (inbound) |
| OPERASIONAL | fulfillment · wh-picklist | Fulfillment/PickList | outbound |
| OPERASIONAL | **wh-inventory-adjustments** | InventoryScrapModule | **penyesuaian/scrap stok** |
| OPERASIONAL | wh-bin | LocationsModule | lokasi/bin |
| OPERASIONAL | wh-accessory-ops · warehouse-accessory-requests | AccessoryModule/Inbox | aksesoris (ada portal sendiri!) |
| OPERASIONAL | wh-returns · warehouse-smart | Returns/Smart | retur · alert/reorder |
| GARMENT WMS | wms (scanner) · wms-fabric-rolls | WMSModule/FabricRolls | tools |
| GARMENT WMS | wms-delivery-notes · wms-cmt-dispatches | DN/CMT Dispatch | outbound dokumen |
| GARMENT WMS | **wms-opname-enhanced** | WMSOpnameEnhanced | **stock opname (SSOT opname2)** |

### 2.2 IRISAN TERIDENTIFIKASI (kasus yang Anda laporkan — TERKONFIRMASI)
**Rumpun "STOK & AKURASI" terpencar di 3 seksi berbeda:**
`unified-inventory` (INVENTORI) · `wh-stock` (INVENTORI) · `wh-inventory-adjustments` (OPERASIONAL) · `wms-opname-enhanced` (GARMENT WMS) — empat-empatnya mengurus stok yang sama (`rahaza_material_stock`/unified) dari sudut berbeda → user bingung pintu mana yang benar.

### 2.3 USULAN `RC-IA-warehouse-1` (pilih satu)
- **Opsi A (REKOMENDASI)** — buat hub `wms-stock-hub` 4 tab: *Viewer Stok (unified)* · *Stok & Pergerakan* · *Opname* · *Penyesuaian*; letakkan di seksi INVENTORI; 4 id lama → redirect+tab (pola hub yang sudah terbukti). 4 menu hilang → 1 pintu.
- **Opsi B** — tanpa hub: buat seksi baru **"STOK & AKURASI"** berisi 4 menu itu berurutan (viewer → pergerakan → opname → penyesuaian); seksi lama dirapikan.
- **Opsi C** — biarkan (tidak direkomendasikan).

### 2.4 Usulan tambahan warehouse (independen, pilih per item)
- **W-2 Re-grup 3 seksi → 5 seksi alur bisnis**: `MASTER & STOK` (master, stock-hub) · `INBOUND` (PO→GRN→Put-Away→Scorecard) · `OUTBOUND` (Fulfillment→Picklist→Surat Jalan→Dispatch CMT) · `AKURASI & ALERT` (opname/adjust bila Opsi B, smart-alert, returns) · `TOOLS` (Scanner, Fabric Roll, Bin). Label "GARMENT WMS (ADVANCED)" DIHAPUS (tidak bermakna bagi user — inilah akar kebingungan "advanced vs operasional").
- **W-3 Aksesoris**: portal Accessories sudah lengkap → di warehouse sisakan SATU menu "Aksesoris" (redirect ke portal accessories ATAU 1 hub 2 tab Transaksi+Inbox). Menghapus dobel pintu.
- **W-4 Scanner**: `wms` (WMSModule scanner) vs Universal Scan portal — biarkan (scanner gudang ≠ universal scan), hanya ganti label jadi "Scanner Gudang" agar jelas.

---

## BAGIAN 3 — QUICK-SCAN PORTAL LAIN (temuan ringan)
| Portal | Temuan | Usulan |
|---|---|---|
| HR ↔ Finance | 2 layar dual-surface (expense, travel) label beda | Samakan label + tambah keterangan "(Inbox bersama HR/Finance)" — kosmetik |
| Marketing ↔ RnD | kreator-requests & accessory-inbox lintas portal | Biarkan (disengaja); pastikan label identik |
| Production | prod-exec-* 6 menu 1 komponen | SAH (per-proses); tidak diubah |
| Semua portal | Sisa audit menyeluruh per-portal (matriks spt 2.1) | Dikerjakan bertahap saat RC-UI-02 render review (efisien: sekali jalan) |

---

## BAGIAN 4 — KEPUTUSAN YANG DIMINTA DARI ANDA
1. `RC-IA-warehouse-1`: **A** (hub 4 tab — rekomendasi) / B (seksi) / C (biarkan)?
2. `W-2` re-grup 5 seksi alur bisnis: ya / tidak?
3. `W-3` aksesoris warehouse → 1 pintu: ya / tidak?
4. `W-4` rename label scanner: ya / tidak?
5. Kosmetik label dual-surface HR↔Finance: ya / tidak?

> Setelah Anda jawab, eksekusi mengikuti pola hub yang sudah terbukti (redirect id lama + deep-link tab + verifikasi testing agent). Tanpa persetujuan, nav TIDAK diubah.

---

## BAGIAN 5 — TEMUAN SAPU LEVEL-TAB WAREHOUSE (Session #21, bukti grep endpoint per modul)

> Hasil eksekusi Deteksi #3 (PART5 §9.1) pada 9 modul warehouse. Ini CACAT NYATA baru, di luar opname (yang sudah fixed):

### RC-IA-warehouse-2 🔴 — Menu inbound RESMI justru pakai endpoint LEGACY
- **Bukti**: `ReceivingModule` (menu "Penerimaan Barang GRN") → `api/wms/legacy/receiving|locations`; `PutAwayModule` → `api/wms/legacy/putaway|stock|locations`; `LocationsModule` (menu "Lokasi/Bin") → `api/wms/legacy/locations`.
- Sementara **tab "Receiving/Scan" DI DALAM WMS Scanner** pakai jalur non-legacy (`api/wms/...` → SSOT wh_grn/wh_putaway).
- **Cacat**: dual-door TERBALIK — pintu bertanda resmi memakai jalur legacy; data GRN/putaway bisa berbeda antara dua pintu (pola persis kasus opname).
- **Instruksi fix eksplisit**: (1) buka `backend/routes/wms_*.py`, petakan `wms/legacy/receiving|putaway|locations` → koleksi apa vs `wms/grn|putaway|positions` (SSOT wh_grn(8)/wh_putaway(5)/wh_positions(36) per registry Part 3); (2) repoint 3 modul FE ke endpoint SSOT + peta field; (3) hapus/deprecate tab Receiving & Posisi di WMSModule ATAU menu — SATU pintu saja (usul: menu tetap, tab scanner jadi pengarah spt opname); (4) verifikasi testing agent: GRN dibuat dari menu muncul juga di scanner-view & stok naik di unified.

### RC-IA-warehouse-3 🔴 — TIGA pintu "penyesuaian stok" dengan TIGA endpoint berbeda
- **Bukti**: `InventoryScrapModule` (menu Penyesuaian) → `rahaza/material-adjust`; `UnifiedInventoryModule` → `wms/stock/unified/adjust`; `RahazaStockModule` (Stok & Pergerakan) → `rahaza/material-adjust|transfer|receive`.
- **Cacat**: user bisa menyesuaikan stok dari 3 tempat; wajib STOP-VERIFY apakah ketiga endpoint menulis ke koleksi/ledger sama (`rahaza_material_stock`+movements) — bila tidak, ini bug integritas stok.
- **Instruksi fix**: (1) grep backend ketiga endpoint → tulis tabel tulis-ke-koleksi; (2) tetapkan SATU jalur adjust resmi (usul: `wms/stock/unified/adjust` bila menulis stock+movement lengkap); (3) dua pintu lain → hapus tombol adjust + pengarah; (4) uji: adjust 1 item → stok & movement konsisten di ketiga tampilan.

### RC-IA-warehouse-4 🟠 — Duplikasi VIEW stok (bukan tulis)
- `RahazaStockModule` vs `UnifiedInventoryModule` menampilkan stok dari sumber beda (`rahaza/material-stock` vs `wms/stock/unified`). Digabung dalam usulan `wms-stock-hub` (Bagian 2.3 Opsi A) — putuskan bersama keputusan #1.

> Status: BELUM dieksekusi (butuh persetujuan + sesi eksekusi). Domain lain (produksi/finance/HR/marketing) belum disapu level-tab — kerjakan dengan perintah §9.1 yang sama.

---

## BAGIAN 6 — HASIL SAPU LEVEL-TAB 7 PORTAL LAIN (Session #22, otomatis §9.1)

### 6.1 Temuan utama
1. **TIDAK ADA endpoint `legacy/*`** di luar warehouse ✅ (masalah legacy terisolasi di RC-IA-warehouse-2).
2. **TIDAK ADA dual-door rusak baru level baca** — irisan endpoint yang terdeteksi bersifat wajar (modul per-proses membaca `work-orders`/`execution` yang sama; accessories = 1 komponen ber-tab; finance memakai keluarga `rahaza/finance` bersama).
3. **🔴 TEMUAN OVERWHELM (akar keluhan user)** — jumlah menu per portal jauh melampaui ambang sehat (target ≤7/seksi):
   | Portal | Jumlah menu | Vonis |
   |---|---|---|
   | HR | **43** | overload berat — wajib re-grup/hub |
   | Finance | **40** | overload berat |
   | Production | **39** | overload berat |
   | Toko/Marketing | 25 | sedang |
   | Warehouse | 22 | sedang (sudah ada usulan Bagian 2) |
   | Maklon 15 · RnD 12 · Accessories 8 | wajar |
4. **Kandidat konsolidasi hub baru** (dari pola endpoint sama → layar serumpun):
   - `prod-exec-*` 6 menu → 1 menu "Eksekusi Proses" ber-tab (komponen sudah satu!) — hemat 5 menu.
   - HR `api/hr/expenses` 5 menu (claims/approval/travel/settlement/per-diem) → 1 hub "Expense & Perjalanan" 5 tab.
   - HR attendance 4 menu (attendance/approval/auto/admin) → 1 hub "Absensi" 4 tab.
   - Finance `fin-asset-*`+accruals+bad-debt (5 menu jurnal-otomatis) → 1 hub "Penyesuaian Akuntansi".
   - RnD 6 menu `dewi/rnd` (patterns/variants/techpack/revisions/analytics/dashboard) → pertimbangkan 2 hub.

### 6.2 Langkah lanjut EKSPLISIT (belum dieksekusi)
1. Verifikasi WRITE-level RC-IA-warehouse-3 (tiga endpoint adjust → koleksi mana) — perintah: `grep -n "material-adjust\|unified/adjust" backend/routes/*.py` lalu baca handler & catat koleksi tulis.
2. Eksekusi konsolidasi 6.1.4 SETELAH user menyetujui (pola hub terbukti, redirect id lama).
3. Ulangi sapu ini untuk portal management/self/collaboration (di-skip karena kecil) — perintah sama §9.1.

---

# BAGIAN 7 — AUDIT LEVEL-TAB (§9.1) — Session #24


> ## ✅ RESOLVED 2026-07-21 — T-1..T-5 di §7.2 di bawah BUKAN LAGI "PERLU-KEPUTUSAN".
> Semua sudah **diputuskan & dieksekusi** (lihat **§8.1** di dokumen ini) dan **diverifikasi kode/logika** pada 2026-07-21:
> T-1 by-design (koleksi `wh_opname_sessions2` dipartisi `domain`, bukan split-brain, stok→SSOT `rahaza_material_stock`);
> T-2/T-3 scope-per-`moduleId` terpasang (+fix bug laten approve RnD); T-4 cross-link; T-5 label disambiguation.
> Kolom "vonis" bertuliskan PERLU-KEPUTUSAN di tabel §7.2 = teks historis pra-keputusan.

> Metode: `/tmp/tab_audit.py` — parse `moduleRegistry.js` → id→file (lazy/static/makeModuleWithTab), filter HANYA id yang jadi menu di `portalNav.js`, ekstrak label tab (`TabsTrigger`, `{id/key,label}`, `{label,Component}` hub) + endpoint per file, kelompokkan per fitur-kata-kunci (opname/adjustment/receiving/PO/QC/attendance/expense/payroll/leave/journal/dst.), vonis DUPLIKAT bila 1 fitur = tab fungsional di ≥2 modul beda.

## 7.1 Sifat temuan (JUJUR): sebagian besar collision = FALSE POSITIVE
Deteksi heuristik ini menandai banyak "kandidat", tapi setelah verifikasi manual per-file, mayoritas BUKAN duplikat fungsional:
- **Launcher/dashboard kartu-pintasan** (bukan tab fungsional): `FinanceDashboard.jsx` (93 LOC, daftar kartu `{id:'fin-journal-entry',label:'Jurnal Umum'…}` yang me-link ke modul lain — BUKAN mengimplementasi jurnal), `PortalSayaDashboard`, `mgmt-reports` (ReportsModule = selector jenis laporan: "NO INVOICE/NO PO/QTY QC PASS"). → collision karena label kartu, bukan duplikasi fitur.
- **Keyword collision**: `salary_adjustment` (HR) ↔ stock `adjustment`; `Executive Summary` ↔ 'leave' (izin) — bukan fitur sama.
- **Unified inbox by-design**: `hr-inbox` (`/api/hr/inbox`) = SATU inbox agregat approval (cuti/lembur/absensi/gaji) — sengaja beririsan dgn modul domain (quick-approve vs detail). Pola sah, bukan bug.
- **Double-count dalam hub yang sama** (tab hub dihitung 2× oleh 2 regex) — artefak skrip, bukan duplikat nyata.

## 7.2 KANDIDAT NYATA (perlu KEPUTUSAN USER — TIDAK dieksekusi otomatis, sesuai §8.3)
| # | Fitur | Lokasi A | Lokasi B | Analisis | Vonis |
|---|---|---|---|---|---|
| T-1 | **Stok Opname** | `wms-stock-hub` tab "Opname Stok" → `WMSOpnameEnhancedModule` (`/api/wms/opname2/*`, SSOT `wh_opname_sessions2`) | `wh-accessory-ops` (AccessoryModule) tab "Stok Opname" → `/api/acc/opname/*` | DUA sistem opname untuk DUA domain stok berbeda (material/fabric vs aksesoris). Mungkin SAH (aksesoris = domain stok terpisah `rahaza_materials type=accessory`) ATAU split-brain dgn opname2. | **PERLU-KEPUTUSAN**: satukan opname aksesoris ke opname2 (filter domain) ATAU dokumentasikan sbg domain terpisah resmi. Butuh cek backend koleksi tulis `/api/acc/opname`. |
| T-2 | **AccessoryRequestInbox** (§8.1 menu-level) | `warehouse-accessory-requests` (Portal Gudang) | `rnd-accessory-requests` (Portal RnD) + `accessories-inbox` (Portal Aksesoris) | 3 menu → komponen SAMA tanpa prop pembeda ({token} saja). Dikomentari "alias" (lintas-portal by-design). Pindah antar-3-menu = tampilan identik (pola bug §8.1). | **PERLU-KEPUTUSAN**: (a) tambah prop `scope` (filter per-portal: gudang=fulfill, rnd=self-monitor) ATAU (b) sisakan 1 + redirect 2 lainnya. |
| T-3 | **KREATORRequestModule** (§8.1 menu-level) | `marketing-kreator-requests` (Marketing) | `rnd-kreator-requests` (RnD, alias) | 2 menu → komponen sama tanpa pembeda ({token,currentUser}). Alias lintas-portal by-design. | **PERLU-KEPUTUSAN**: sama spt T-2 (scope prop atau redirect). |
| T-4 | **Approval Absensi** | `hr-inbox` (unified `/api/hr/inbox`, quick-approve) | `hr-attendance-hub` tab "Approval Absen" (`RahazaAttendanceApprovalModule`, detail) | Dua PINTU approve absensi (agregat vs detail). Pola unified-inbox umum & sah, tapi tumpang tindih fungsi approve. | **CATATAN (bukan bug)**: pertahankan; opsional tambah link silang inbox↔detail. |
| T-5 | **Self-service (payslip/cuti/absen)** | `portal-dashboard`/`portal-cuti` (PortalSaya*) | `portal-workspace` (WorkspaceHub tab "Kehadiran & Payslip"/"Slip Gaji Saya"/"Cuti & Izin Saya") | Dua portal self-service beririsan (Portal Saya vs Workspace). | **PERLU-KEPUTUSAN**: klarifikasi peran 2 portal self-service — gabung atau bedakan tegas. |

## 7.3 Kesimpulan §9.1
- Deteksi level-TAB SELESAI (skrip `/tmp/tab_audit.py`, regenerasi kapan pun). **0 duplikat fungsional wajib-fix ditemukan** yang belum ter-cover; 5 kandidat di 7.2 = semua **PERLU-KEPUTUSAN USER** (menyentuh IA lintas-portal/backend SSOT — dilarang eksekusi tanpa persetujuan per §8.3).
- Duplikat tab akut yang dulu ada ("Stok Opname" di WMS Scanner) SUDAH difix sesi lalu (RC-IA-warehouse-0). Tidak ada regresi tab-dobel baru.


---

# BAGIAN 8 — KEPUTUSAN USER & EKSEKUSI (Session #28)

> Env: repo di-clone dari `github.com/bikinakumarah/da` → /app (env preserved: `MONGO_URL`/`REACT_APP_BACKEND_URL` TIDAK diubah; +`JWT_SECRET`(gen)+`EMERGENT_LLM_KEY` di backend/.env). deps pip -r requirements.txt + `yarn install`. Seed startup OK (superadmin `admin@garment.com`/`Admin@123`, COA 274, posting profiles 33). services RUNNING; health 200; login 200; frontend `compiled successfully`.

## 8.1 Keputusan terhadap 5 kandidat §7.2 (T-1..T-5)
| # | Keputusan user | Eksekusi Session #28 | Status |
|---|---|---|---|
| **T-1 — Stok Opname** | **B — dokumentasikan sbg domain terpisah resmi, TANPA ubah backend** | Opname aksesoris (`/api/acc/opname/*`, `AccessoryModule` tab "Stok Opname") = **domain stok Aksesoris resmi & terpisah** dari opname Material/Kain (`/api/wms/opname2/*`, SSOT `wh_opname_sessions2`). Bukan split-brain. Tidak ada perubahan backend. (Catatan domain sudah ada di StokOpnameTab sejak Session #26 3a.) | ✅ Doc-only |
| **T-2 — AccessoryRequestInbox** | **A — prop `scope` (RnD = read-only monitor)** | `AccessoryRequestInbox` sekarang membaca `moduleId`: `rnd-accessory-requests` = **mode PANTAU (read-only monitor)** — default filter `request_type=rnd_sample` + semua status, banner "Mode pantau (read-only)", **sembunyikan** baris filter-tipe & seluruh tombol aksi fulfillment (Siapkan/Kirim/Tolak/Hapus). `warehouse-accessory-requests` & `accessories-inbox` = inbox fulfillment penuh (tak berubah). | ✅ Kode |
| **T-3 — KREATORRequestModule** | **A — prop `scope` ringan (marketing vs rnd default-filter + label)** | `KREATORRequestModule` membaca `moduleId`: `rnd-kreator-requests` = **scope RnD** (label "Approve Kreator Request", default filter status `submitted`/Tunggu RnD, tombol "Request Baru" & empty-state-create disembunyikan, aksi Setujui/Tolak aktif via scope). `marketing-kreator-requests` = scope Marketing (buat & lacak, default semua status). **Bonus fix latent bug**: `isRnd` dulu bergantung prop `currentUser` yang **tak pernah** dioper App.js (App.js mengoper `user`/`moduleId`) → tombol approve/tolak RnD **tak pernah muncul**; kini benar via scope+fallback role. | ✅ Kode |
| **T-4 — Approval Absensi** | **pertahankan by-design (+ link silang opsional)** | Kedua pintu dipertahankan. `hr-inbox` (`HRApprovalInboxModule`) mendapat **cross-link opsional** ke `hr-attendance-hub`: tombol header "Attendance Hub →" + note kontekstual saat tab "Absensi" aktif; keduanya `onNavigate('hr-attendance-hub', { tab: 'approval' })`. | ✅ Kode |
| **T-5 — Self-service / label "Workspace"** | **by-design, perjelas label** | 3 label "Workspace" yang ambigu dibedakan tegas: `portal-workspace` "My Workspace" → **"Ruang Kerja Saya"** (catatan/tugas/pengingat/kalender/tautan pribadi); `collab-workspace` "My Workspace (Spreadsheet)" → **"Workspace Spreadsheet"**; `prod-workspace-master` "Master Workspace" → **"Master Lokasi Kerja"** (lokasi fisik). Header komponen (`WorkspaceHub`, `WorkspacePortal`) ikut diperjelas. Portal Saya (self-service payslip/cuti/absen) tetap sumber tunggal self-service — tak lagi bertabrakan makna dgn "Workspace". | ✅ Label |

> **Kontrak prop**: `moduleId={currentModule}` sudah dioper App.js ke **setiap** `ModuleComponent` (App.js ~baris 600) & modul yang sama dipetakan ke >1 module-id di `moduleRegistry.js` (alias lintas-portal). Jadi wiring `scope`-per-module-id **tidak butuh perubahan registry/App.js** — cukup baca `moduleId` di modul (pola T-2/T-3).

## 8.2 Bug ditemukan & diperbaiki (blocker kompilasi)
- **`AccessoryRequestInbox.jsx`**: edit parsial sesi sebelumnya menyisakan `{!isRndMonitor && (` **tanpa penutup `)}`** (JSX expression tak tertutup) → **Babel gagal parse (`Unexpected token, expected ","` di baris type-filter)** → seluruh build gagal kompilasi. **Fix**: tambah penutup `)}` setelah baris filter-tipe + rapikan pembungkus aksi. Kini `compiled successfully`.

## 8.3 §9.1 AUDIT LEVEL-TAB — Produksi / Finance / HR / Marketing(Toko) (baru, Session #28)
> Sisa portal yang belum disapu level-tab (§7.3 / BAGIAN 5 baris "Domain lain … belum disapu") kini DIJALANKAN. Skrip regenerable: **`/app/scripts/tab_audit.py`** (versi refinasi: hanya hitung TAB fungsional nyata — `TabsTrigger` + array hub `{key,label,Component}`; klasifikasi kandidat hanya dari LABEL tab, endpoint = konteks). Dump: `/app/docs/tab_audit_session28_result.json`.

Menu terpindai: Produksi 35 · Finance 36 · HR 30 · Marketing/Toko 25 (semua ter-resolve ke file).

**Kandidat (fitur = tab fungsional di ≥2 modul):**
| Fitur | Modul A | Modul B | Vonis |
|---|---|---|---|
| **attendance** | `hr-attendance-hub` (Manual/Otomatis/Approval Absen) | `hr-inbox` (tab Absensi) | = **T-4** (sudah diputuskan by-design + cross-link, DONE). |
| **payroll** | `hr-admin` (tab "Struktur Gaji" = master) | `hr-inbox` (tab "Gaji" = antrian approval `salary_adjustment`) | **by-design** — master config vs approval inbox (pola unified-inbox, sama seperti T-4). Bukan duplikat implementasi. |
| **asset** | `fin-acctg-adjust-hub` (Depresiasi/Pelepasan Aset — akuntansi aset tetap, GL) | `hr-assets` (Daftar/Penugasan Aset ke karyawan — inventaris HR) | **DOMAIN BERBEDA** — aset tetap keuangan (nilai buku/penyusutan) vs penugasan aset fisik ke karyawan. Bukan duplikat. |
| **live** | `marketing-live-hub` (Live Sessions / LiveHost Mgmt — operasional) | `marketing-sales` (tab "🎥 Live Revenue" — analitik pendapatan) | **by-design** — kelola operasi live vs pelaporan pendapatan dari live. Tujuan beda. |

**Kesimpulan §9.1 (4 portal):** **0 duplikat fungsional wajib-fix.** 1 kandidat = T-4 (sudah ditangani); 3 sisanya = by-design/domain terpisah (tak butuh keputusan tambahan). Konsisten dgn §7.3. Audit ini **read-only** (tidak mengeksekusi perubahan IA/backend, sesuai §8.3).
