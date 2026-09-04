# FLOW_UX_AUDIT.md — Audit UX 10 Alur Bisnis Kritis (PART5 §9.2)

> **✅ UPDATE Session #29c — DE-DUP PINTU MENU (keputusan user 1a/2a/3b/4a) DIEKSEKUSI & TERVERIFIKASI:**
> Temuan: mayoritas "pintu duplikat" ternyata = header seksi / quick-link WorkspaceHub / pembagian domain sah — bukan duplikasi berbahaya; akar masalah = LABEL ambigu.
> - **3b Expense (Keuangan):** 2 pintu (`fin-expenses` + `fin-expense-settlement`) → digabung jadi 1 hub ber-tab `FinanceExpenseHub` (tab "Pengeluaran (Umum)" + "Klaim Karyawan (Disbursement)"). Menu sidebar tinggal 1 pintu "Pengeluaran & Klaim". Deep-link lama `fin-expense-settlement` → `makeRedirect('fin-expenses','settlement')` (buka tab settlement). Verified: testing agent iter#54 = 100% hub+deep-link.
> - **2a Opname:** `accessories-opname` → "Stok Opname (Aksesoris)" (bedakan dari opname material `wms-stock-hub`). Keduanya tetap (2 domain sah).
> - **4a Cuti:** header SDM "🏖️ Cuti & Izin" → "🏖️ Manajemen Cuti (SDM)"; `hr-leave` "Izin & Cuti" → "Kelola & Persetujuan Cuti" (bedakan dari self-service `portal-cuti`). Quick-link WorkspaceHub dibiarkan (berguna, bukan re-implementasi).
> - **1a Payslip:** `hr-payroll-run` "Penggajian & Slip" → "Penggajian (Payroll Run)" (bedakan dari self-service `portal-payslip` "Slip Gaji Saya").
> Semua relabel + hub terverifikasi render via screenshot. CATATAN: testing agent iter#54 melaporkan "portal switching broken (CRITICAL)" — ini **FALSE POSITIVE** (agent tak kembali ke portal selector dulu); switching portal terbukti normal via screenshot manual (Aksesoris & SDM keduanya berpindah benar).

> Session #24. Metode: analisis-kode navigasi (`portal-shell/portalNav.js` 13 portal / 221 menu + deteksi onward-CTA via `grep window.location.hash`) + perilaku write-flow yang SUDAH diverifikasi backend (testing agent iter#37 = 95.2% LULUS) + render modul terverifikasi (iter#38 = 100%). Diagram "aktual vs ideal" + kartu RC-FLOW-UX per cacat.
>
> **Skala dampak:** 🔴 BLOCKER (alur tak selesai / user tersesat) · 🟠 CONFUSING (bisa selesai tapi butuh tebak / lompat portal tak jelas) · 🟡 COSMETIC (poles).
>
> **TEMUAN LINTAS-ALUR #1 (paling berdampak):** dari seluruh modul ERP, **hanya 2 file** yang memakai navigasi onward (`window.location.hash=`). Artinya **halaman hasil hampir tak pernah menyediakan tombol "lanjut ke langkah berikут"** — setelah menyelesaikan langkah N, user harus TAHU sendiri & mencari langkah N+1 di sidebar. Ini akar mayoritas gesekan di bawah.
>
> **TEMUAN LINTAS-ALUR #2:** modul TIDAK menerima prop `onNavigate` (hanya `{token, currentUser}`), sehingga tak bisa menautkan langkah antar-modul tanpa `window.location.hash`. **Fix fondasi (RC-FLOW-UX-CORE):** teruskan `onNavigate(moduleId)` ke setiap modul via registry/PortalShell → memungkinkan CTA onward di semua kartu di bawah.

---

## Ringkasan verdict per alur
| # | Alur | Portal tersentuh | Lompat portal | Verdict |
|---|---|---|---|---|
| 1 | PO → GRN → Put-Away → Stok | Gudang | 0 | 🟠 (3 menu terpisah, tanpa CTA onward) |
| 2 | Opname → Adjustment | Gudang (+Aksesoris terpisah) | 0–1 | 🟠 (split domain material vs aksesoris) |
| 3 | WO → Cutting → Bundle → Jahit→Packing → QC → FG | Produksi → Gudang | 1 | 🟠 (langkah awal terpisah; eksekusi sudah 1 hub) |
| 4 | FG → Surat Jalan / Dispatch CMT | Gudang | 0 | 🟢/🟠 (2 pintu berbeda tujuan; ok, kurang CTA) |
| 5 | Order Toko → Fulfillment | Marketing → Gudang | 1 | 🟠 (lompat portal, tanpa CTA) |
| 6 | Expense Claim → Approve → Disburse → GL | SDM → Keuangan | 1 | 🟠 (segregasi tugas wajar; pintu Finance ganda) |
| 7 | Payroll Run → Slip | SDM | 0 | 🟢 (satu hub) |
| 8 | Cuti: request → approve → saldo | Portal Saya → SDM | 1 | 🔴/🟠 (pintu cuti GANDA di 2 portal + duplikat) |
| 9 | AR Invoice → Post GL → Payment | Keuangan | 0 | 🟢 (satu modul lifecycle) |
| 10 | Maklon PO → progress → invoice | Maklon | 0 | 🟢/🟠 (satu portal; CTA onward kurang) |
| 11 | Retur pelanggan → refund → koreksi stok | Toko → Gudang (+Keuangan) | 1–2 | 🔴/🟠 (2 sistem retur PARALEL & terputus; tanpa jembatan) |

**Positif (dari sesi lalu):** banyak alur SUDAH dikonsolidasi ke hub (prod-exec-hub, hr-expense-hub, wms-stock-hub, fin-journal-hub, ARLifecycle) → dalam-hub sudah pakai tab (langkah tersambung). Masalah tersisa ada di SAMBUNGAN antar-menu/antar-portal.

---

## ALUR 1 — PO → GRN → Put-Away → Stok  🟠
**Aktual:** Gudang › `wh-purchase-orders` (buat PO) → *[user pindah menu sendiri]* → Gudang › `wh-receiving` (GRN terima) → *[pindah menu]* → Gudang › `wh-putaway` → *[pindah menu]* → cek stok di `wms-stock-hub`/`wh-stock-viewer`.
**Ideal:** dari PO yang sudah "diterima sebagian", tombol **"Buat GRN"**; dari GRN selesai, tombol **"Put-Away sekarang"**; dari put-away, tombol **"Lihat Stok"**.
- **RC-FLOW-UX-1a** 🟠 — Tidak ada CTA onward antar 3 menu. Lokasi: `PurchaseOrderModule`, `wh-receiving` module, `wh-putaway` module. Fix: pada halaman detail PO status=received tampilkan tombol `onNavigate('wh-receiving', {po_id})`; pada GRN sukses toast + tombol `onNavigate('wh-putaway')`. Dampak: hemat 3 hunt-menu.
- **RC-FLOW-UX-1b** 🟡 — Terminologi campur "GRN" vs "Penerimaan Barang" vs "Receiving". Fix: samakan label ke "Penerimaan (GRN)".

## ALUR 2 — Opname → Adjustment  🟠
**Aktual:** Gudang › `wms-stock-hub` tab "Opname Stok" (`/api/wms/opname2`) → tab "Penyesuaian" (adjustment). **TAPI** aksesoris punya pintu terpisah: Aksesoris › `accessories-opname` (`/api/acc/opname`).
- **RC-FLOW-UX-2a** 🟠 (=§9.1 T-1) — Dua sistem opname (material vs aksesoris) di 2 portal. **PERLU-KEPUTUSAN**: satukan ke opname2 dgn filter domain, atau dokumentasikan resmi sbg 2 domain. Dampak: user aksesoris & user gudang bingung "opname yang mana".
- **Positif:** dalam `wms-stock-hub`, opname→adjustment sudah 1 hub bertab (tersambung). 🟢

## ALUR 3 — WO → Cutting → Bundle → Jahit→Packing → QC → FG  🟠
**Aktual:** Produksi › `prod-orders` (Order Produksi) → `prod-work-orders` (WO) → `prod-cutting` (Cutting Hub) → `prod-bundles` (Bundle) → `prod-exec-hub` (Jahit→Packing→QC, **sudah 1 hub bertab** 🟢) → hasil FG masuk ke Gudang › fulfillment/stock.
- **RC-FLOW-UX-3a** 🟠 — 4 menu awal (order/WO/cutting/bundle) terpisah tanpa CTA onward. Setelah buat WO (verified 200), tak ada tombol "Mulai Cutting". Fix: CTA `onNavigate('prod-cutting', {wo_id})` di halaman WO baru; kartu WO cantumkan tahap berjalan + tombol lanjut.
- **RC-FLOW-UX-3b** 🟠 — Transisi Produksi→Gudang (FG) tak eksplisit; user tak tahu FG sudah masuk stok. Fix: pada QC-pass di prod-exec-hub, toast "FG X pcs masuk stok" + link ke stok.
- **Positif:** eksekusi jahit→packing→QC sudah satu hub. 🟢

## ALUR 4 — FG → Surat Jalan Customer / Dispatch CMT  🟢/🟠
**Aktual:** Gudang › `wms-delivery-notes` (Surat Jalan Customer) DAN `wms-cmt-dispatches` (Dispatch ke CMT) — dua tujuan berbeda (customer vs vendor CMT), keduanya di Gudang. Create+issue **verified 200** (iter#37).
- **RC-FLOW-UX-4a** 🟡 — Dua menu mirip ("Surat Jalan" vs "Dispatch CMT") berdekatan; label sudah membedakan tujuan → wajar. Fix opsional: sub-judul penjelas ("ke Customer" / "ke Vendor CMT").

## ALUR 5 — Order Toko → Fulfillment  🟠
**Aktual:** Marketing › `marketing-orders` (Unified Orders) → **LOMPAT PORTAL** → Gudang › `fulfillment` (Order → FG Out).
- **RC-FLOW-UX-5a** 🟠 — Lompat Marketing→Gudang tanpa jembatan. User marketing tak tahu order-nya harus diproses di portal Gudang. Fix: di `marketing-orders` status=paid, tampilkan status fulfillment (read-only) + (jika role gudang) CTA `onNavigate('fulfillment')`; sebaliknya `fulfillment` tampilkan asal order.

## ALUR 6 — Expense Claim → Approve → Disburse → GL  🟠
**Aktual:** SDM › `hr-expense-hub` (karyawan buat+submit) → **LOMPAT** → Keuangan › `fin-expenses`/`fin-expense-settlement` (Finance approve+disburse → auto JE GL). Disburse **verified 200 utk role accounting** (FIX RC-FLOW-expense-1 sesi ini).
- **RC-FLOW-UX-6a** 🟠 — Pintu expense GANDA di Keuangan: `fin-expenses` (Pengeluaran) + `fin-expense-settlement` (Klaim Karyawan Disbursement) + hub di SDM. Fix: perjelas peran tiap pintu / gabung disbursement ke satu tempat. **PERLU-KEPUTUSAN**.
- **RC-FLOW-UX-6b** 🟡 — Lompat SDM→Keuangan wajar (segregasi tugas), tapi karyawan tak dpt notifikasi in-app saat klaim disburse. Fix: pastikan notif "klaim dibayar" muncul di Portal Saya (notif submit sudah verified).

## ALUR 7 — Payroll Run → Slip  🟢
**Aktual:** SDM › `hr-payroll-run` (create run → sync absensi → finalize → slip). Satu tempat, tersambung.
- **RC-FLOW-UX-7a** 🟡 — Slip karyawan muncul di 3 tempat (`portal-payslip`, `portal-workspace`, `portal-dashboard`) → lihat Alur 8/§9.1 T-5. Payroll-run sendiri OK.

## ALUR 8 — Cuti: request → approve → saldo  🔴/🟠
**Aktual:** Portal Saya › `portal-cuti` (Cuti & Lembur) ATAU `portal-workspace` tab "Cuti" (request) → **LOMPAT** → SDM › `hr-leave` (approve) & `hr-leave-balances` (saldo). **TAPI** SDM punya DUA pintu cuti: `leave-header` (🏖️ Cuti & Izin) + `hr-leave` (Izin & Cuti); self-service juga ganda (`portal-cuti` vs `portal-workspace`).
- **RC-FLOW-UX-8a** 🔴 (=§9.1 T-5) — **Pintu cuti duplikat**: SDM 2 pintu + Portal Saya 2 pintu. User bingung request/approve di mana. Fix: sisakan 1 pintu request (Portal Saya) + 1 pintu approve (SDM), redirect sisanya. **PERLU-KEPUTUSAN** (menyentuh IA).
- **RC-FLOW-UX-8b** 🟠 — Setelah approve, saldo (`hr-leave-balances`) update (verified balance.used naik iter#37) tapi user tak dpt CTA/notif. Fix: notif "cuti disetujui, saldo tersisa X".

## ALUR 9 — AR Invoice → Post GL → Payment  🟢
**Aktual:** Keuangan › `fin-ar-invoices` (ARLifecycle: create→post-to-gl→payment, JE+cash-movement). **Full flow verified 200** (iter#37). Satu modul lifecycle, tersambung.
- **RC-FLOW-UX-9a** 🟡 — CTA onward antar tahap ada di dalam lifecycle (baik). Poles: badge status jelas (draft/posted/paid).

## ALUR 10 — Maklon PO → progress → invoice  🟢/🟠
**Aktual:** Maklon › `maklon-po` (buat PO) + `maklon-po-360` (360° view progress) → invoice. Satu portal.
- **RC-FLOW-UX-10a** 🟠 — Progress & invoice terpisah dari PO create; `maklon-po-360` bagus utk lihat menyeluruh tapi jalur create→invoice kurang CTA. Fix: dari PO-360 tombol "Buat Invoice" saat progress=selesai.

## ALUR 11 — Retur Pelanggan → Refund → Koreksi Stok  🔴/🟠
**Aktual (berdasarkan kode):** ada **DUA sistem retur PARALEL** yang jalan sendiri-sendiri, tanpa jembatan:

**Jalur A — sisi Marketing/Toko (finansial):**
Toko › `marketing-after-sales` (hub 3-tab: Komplain / Returns & Refunds / Log Penyelesaian) → koleksi `marketing_returns`. Lifecycle endpoint `/api/marketing/returns/*`:
`create` → `approve` → `complete` → `create-credit-note` (auto-post GL reversing **Dr Revenue / Cr AR**, koleksi `rahaza_credit_notes`).  **File:** `backend/routes/marketing_returns_routes.py`. **Tidak menyentuh stok sama sekali** (verified: endpoint `complete_return` hanya update status + `updated_at`, tak ada `fg_inventory`/`fg_movements`/`stock_movement`).

**Jalur B — sisi Gudang (fisik):**
Gudang › `wh-returns` (Retur & Refund, seksi OUTBOUND) → koleksi terpisah. Lifecycle endpoint `/api/wh/returns/*`:
`create` → `receive` → `inspect` → `resolve` (aksi: **Restock ke Gudang** / Reshipment / Appeal Platform / Dispose / Donasi). Saat `resolve = Restock`, sistem `$inc: total_qty` ke `rahaza_fg_inventory` + tulis `rahaza_fg_movements {movement_type:'IN', source:'return_restock'}`.  **File:** `backend/routes/dewi_wh_returns.py` (baris 300–360). **Tidak membuat credit note / jurnal refund.**

**Legacy/deep-link paralel (menambah kebingungan pintu):** `marketing-complaints`, `marketing-returns` (standalone lama, sekarang dibungkus hub), `toko-cs`/`toko-returns` (TokoCSReturnsModule — memanggil endpoint marketing yang sama). Semua ada di `moduleRegistry.js` (baris 902–962).

**Ideal:** satu retur pelanggan seharusnya:  
`Toko: buat retur (referensi order)` → `Toko: approve` → **CTA "Kirim ke Gudang: Terima Barang Fisik"** (buat `wh_return` link back ke `marketing_return_id`) → `Gudang: receive → inspect → resolve(Restock)` (stok naik) → **CTA "Terbitkan Credit Note & Refund"** kembali ke Toko/Keuangan (`create-credit-note` → GL reversing → jika perlu, cash-payment) → CTA "Lihat Jurnal" ke `fin-journal-hub`. Satu retur, satu ID master, dua eksekusi (fisik+finansial) tersambung.

### Cacat teridentifikasi
- **RC-FLOW-UX-11a** 🔴 **BLOCKER-DATA** — Dua sistem retur berjalan tanpa saling mengenal (`marketing_returns` vs `dewi_wh_returns` = 2 koleksi berbeda, tak ada FK/back-ref). Konsekuensi: (i) retur diselesaikan di Marketing (credit-note terbit, GL ter-post) **stok FG TIDAK bertambah** — jurnal ≠ realita gudang; (ii) retur di-restock di Gudang **tanpa credit note / GL** — kas/piutang tetap salah. **Fix wajib:** sinkronisasi 2-arah — saat `marketing_returns.approve`, auto-buat `wh_return` stub (link `source_return_id`) dengan status `pending`; saat `wh_returns.resolve(Restock)`, callback ke `marketing_returns` untuk unlock/auto-trigger `create-credit-note`. **PERLU-KEPUTUSAN sistemik** (menyentuh skema backend). Alternatif jangka pendek (non-destruktif): tambahkan field `wh_return_id` opsional di `marketing_returns` + tombol manual "Buat Retur Fisik di Gudang".

- **RC-FLOW-UX-11b** 🟠 — Tak ada CTA onward antar hub. Setelah `marketing-after-sales` approve retur, tak ada tombol "Terima Barang di Gudang" → user gudang tak tahu ada retur masuk. Sebaliknya, setelah `wh-returns` resolve, tak ada tombol "Terbitkan Credit Note". **Fix (fondasi sudah siap via RC-FLOW-UX-CORE):**
  - Di `ReturnsRefundsModule.jsx` (tab "Returns & Refunds" di dalam `MarketingAfterSalesHub`): setelah status → `approved`, render `<OnwardCTA onNavigate={onNavigate} actions={[{module:'wh-returns', label:'Terima Barang Fisik di Gudang', icon:PackagePlus}, {module:'marketing-after-sales', params:{tab:'returns'}, label:'Terbitkan Credit Note', hint:'setelah barang diterima', icon:FileText}]} />`.
  - Di `WHReturnsModule.jsx` setelah `resolve=Restock` sukses: `<OnwardCTA … actions={[{module:'marketing-after-sales', params:{tab:'returns'}, label:'Terbitkan Credit Note & Refund'}, {module:'wms-stock-hub', params:{tab:'stock'}, label:'Cek Stok FG'}]} />`.
  - Cross-portal Toko→Gudang otomatis oleh `handleNavigate` (sudah terbukti Alur 5).

- **RC-FLOW-UX-11c** 🔴 **BLOCKER-STOK** — `POST /api/marketing/returns/{id}/complete` menutup retur tanpa restock. Bila user Marketing salah pakai jalur A saja (tanpa Gudang), FG hilang secara akuntansi jual (revenue di-reverse) tetapi tidak muncul kembali di `fg_inventory`. **Fix opsi 1 (backend):** tolak `complete` bila tak ada `wh_return_id` terkait (kecuali `disposition='dispose'`/`refund_only`). **Opsi 2 (UX):** pada tab "Returns & Refunds", tampilkan warning-banner "Barang belum diterima Gudang" bila `status=approved` > 24 jam. **PERLU-KEPUTUSAN.**

- **RC-FLOW-UX-11d** 🟠 — **Pintu retur GANDA di sidebar:** Marketing punya `marketing-after-sales` (Komplain+Retur) + legacy deep-link `marketing-returns` + `marketing-complaints` + `toko-cs`/`toko-returns` (TokoCSReturnsModule) yang **memanggil endpoint yang sama** = 4–5 pintu untuk fitur identik. Gudang punya `wh-returns` (beda sistem). Fix (sejalan Session #29c de-dup): sisakan **1 pintu Marketing = `marketing-after-sales`** (sudah hub 3-tab); redirect deep-link lama pakai `makeRedirect('marketing-after-sales', 'returns' | 'complaints')`; retire `toko-cs`/`toko-returns` (atau redirect). Tandai `wh-returns` sebagai "Retur Fisik (Gudang)" agar label bedakan tujuan. **PERLU-KEPUTUSAN** (menyentuh IA).

- **RC-FLOW-UX-11e** 🟡 — Terminologi bercampur: "Retur", "Return", "Refund", "Credit Note", "Restock" muncul acak di label modul & tombol. Fix: standar Bahasa — "Retur (Pengembalian Barang)" untuk fisik, "Refund (Pengembalian Dana)" untuk finansial, "Nota Kredit" untuk dokumen akunting; hindari campur EN/ID di 1 layar.

- **RC-FLOW-UX-11f** 🟡 — Log Penyelesaian di `MarketingAfterSalesHub` (tab-3) **hanya baca dari `marketing_complaints` + `marketing_returns`** — retur yang di-restock via `wh-returns` tak muncul di log. Fix: perluas `ResolutionLogTab` merge tambahan `GET /api/wh/returns?status=Resolved` (setelah RC-FLOW-UX-11a diputuskan).

### Status backend (yang terbukti dari kode)
- ✅ `marketing_returns` lifecycle + auto-credit-note + GL reversing berfungsi (verified via handler `create_credit_note` → `rahaza_posting.post_credit_note`).
- ✅ `wh_returns` restock update `fg_inventory` + movement log berfungsi (verified `resolve_return` handler baris 322–345).
- 🔴 **Tak ada handler yang menautkan keduanya.** Ini bukan bug endpoint tunggal — ini **gap arsitektur** (2 domain data ter-decouple).

### Catatan RBAC
- Marketing side: `require_auth` generik (tanpa role-check di kode saat ini) — bila ingin segregasi (mis. hanya `marketing_manager` boleh approve, hanya `accounting` boleh `create-credit-note`), tambahkan role guard mengikuti pola RC-FLOW-expense-1/production-1 (cek role string hardcode; `role_permissions` collection masih kosong per handoff Session #24).
- Gudang side: sama, `require_auth` saja. Konsisten dengan modul warehouse lain.

---

## Usulan REDESAIN (bold, opsional — butuh persetujuan user, §8.3)
1. **RC-FLOW-UX-CORE (fondasi):** teruskan `onNavigate(moduleId, params)` ke SEMUA modul (via registry render + PortalShell). Tanpa ini, CTA onward mustahil rapi. **Prioritas #1** — membuka semua fix "🟠 tanpa CTA" di atas.
2. **"Process Cockpit" per rantai:** untuk 3 rantai lintas-langkah (Procure-to-Stock #1, Make (#3), Order-to-Cash #5+#9), sediakan 1 halaman stepper (breadcrumb tahap + status + tombol lanjut) alih-alih mengandalkan sidebar. Mengurangi hunt-menu & lompat-portal.
3. **De-duplikasi pintu (butuh keputusan):** Cuti (Alur 8), Expense (Alur 6), Opname (Alur 2), Self-service payslip (Alur 7/8), **Retur & Komplain (Alur 11)** — sisakan 1 pintu/fungsi + redirect (target §8.3: ≤7 menu per seksi, 1 pintu per fitur).
4. **Sinkronisasi 2-domain untuk retur (Alur 11):** hubungkan `marketing_returns` ↔ `wh_returns` (1 retur pelanggan = 1 master + 2 eksekusi tersambung: fisik & finansial). Tanpa ini, RC-FLOW-UX-11a/11c/11f tak bisa ditutup — hanya bisa mitigasi via CTA (RC-FLOW-UX-11b).

## Kesimpulan §9.2
- 10 alur bisnis kritis + 1 alur after-sales (retur/refund) SELESAI diaudit. **Backend untuk 10 alur inti LULUS (iter#37)** — tak ada alur yang "putus" secara teknis. Alur 11 (retur/refund) menambah **1 blocker-arsitektur baru** (RC-FLOW-UX-11a: 2 sistem retur paralel tanpa jembatan) + **1 blocker-stok** (RC-FLOW-UX-11c: `complete` marketing-return tanpa auto-restock).
- Gesekan umum bersifat **UX-navigasi**: (a) minim CTA onward (akar #1), (b) beberapa lompat-portal tanpa jembatan (Toko↔Gudang↔Keuangan), (c) pintu duplikat (cuti/expense/opname/payslip **+ retur/komplain**).
- **1 blocker teknis (RC-FLOW-UX-11a/11c)** + 1 blocker-UX (RC-FLOW-UX-8a pintu cuti ganda) + ~11 confusing (🟠) + poles (🟡). Semua fix diusulkan **non-destruktif**; perubahan skema data / IA portal ditandai **PERLU-KEPUTUSAN** (tidak dieksekusi tanpa persetujuan, sesuai §8.3).

---

## STATUS UPDATE — RC-FLOW-UX-11 (Alur After-Sales/Retur) DIEKSEKUSI ✅ (Session #26)

**Keputusan user 8 Jul 2026:** 11a=B (link manual) · 11c=B (soft warning) · 11d=A (konsolidasi ketat). Semua diimplementasikan & tested (deep_testing_backend_v2 iter#55 = 9/9 PASS).

**Yang berubah (backend):**
- **`backend/routes/marketing_returns_routes.py`**:
  - Endpoint baru `POST /api/marketing/returns/{id}/create-wh-return` (idempoten, status-guard `approved`/`completed`): buat entry `wh_returns` dengan `source_marketing_return_id` link back; simpan `wh_return_id`/`wh_return_code`/`wh_return_status='Pending'` di `marketing_returns`.
  - `complete_return` upgrade: response menyertakan field `warning` non-null bila tak ada `wh_return_id` dan `disposition` ∉ {`dispose`,`refund_only`,`donation`} (soft-guard, bukan hard-block).
- **`backend/routes/dewi_wh_returns.py`**:
  - `resolve_return` upgrade: bila `source_marketing_return_id` ada, callback `marketing_returns.update` set `wh_return_status='Resolved'`, `wh_action_taken`, `wh_restock_qty`, `wh_resolved_at` (non-blocking; gagal callback tak batalkan resolve).

**Yang berubah (frontend):**
- **`marketing/ReturnsRefundsModule.jsx`**: tombol **"Buat Retur Fisik di Gudang"** di detail-modal saat `status=approved` & belum ada `wh_return_id`; setelah link ada, tampil badge `wh_return_code` + tombol **"Buka di Gudang →"** (cross-portal Toko→Gudang via `onNavigate`); banner ⚠️ "Barang belum diterima Gudang" muncul otomatis bila `approved > 24 jam` tanpa `wh_return_id` (RC-FLOW-UX-11c).
- **`WHReturnsModule.jsx`**: di blok "Resolusi" (status Resolved) tampilkan referensi retur Toko asal; bila `source_marketing_return_id` ada, render `<OnwardCTA>` dgn 2 tombol: **"Terbitkan Credit Note & Refund"** (cross-portal Gudang→Toko ke `marketing-after-sales` tab `returns`) + **"Cek Stok FG"** (ke `wms-stock-hub` tab `stock`).
- **`moduleRegistry.js`** (RC-FLOW-UX-11d): 4 pintu legacy → `makeRedirect` ke `marketing-after-sales`:
  - `marketing-complaints` → `hub_tab_marketing-after-sales=complaints`
  - `marketing-returns` → `hub_tab_marketing-after-sales=returns`
  - `toko-cs` → `hub_tab_marketing-after-sales=complaints`
  - `toko-returns` → `hub_tab_marketing-after-sales=returns`
- **`App.js` `LEGACY_MODULE_TO_PORTAL`**: 4 id di atas dipetakan ke portal `toko` supaya deep-link hash lama tetap resolve portal.
- **`MarketingAfterSalesHub.jsx`**: baca `sessionStorage.hub_tab_marketing-after-sales` untuk initial tab (dukung deep-link dari `makeRedirect`); forward `onNavigate` ke child (`ComplaintsManagementModule`, `ReturnsRefundsModule`).
- **`portal-shell/portalNav.js`**: `wh-returns` label dari "Retur & Refund" → **"Retur Fisik (Gudang)"** (bedakan tujuan dari retur finansial di `marketing-after-sales`).

**Sisa (belum dieksekusi):**
- ~~**RC-FLOW-UX-11e** (poles terminologi)~~ ✅ **SELESAI Session #26 lanjutan**: standar Bahasa diterapkan — "Refund & Nota Kredit" (Toko/Marketing), "Retur Fisik & Restock (Gudang)" (WH), tombol "Selesaikan & Terbitkan Nota Kredit", header hub "Komplain & Retur/Refund". Konsisten EN/ID di tiap layar.
- ~~**RC-FLOW-UX-11f** (Log Penyelesaian merge `wh_returns` Resolved)~~ ✅ **SELESAI Session #26 lanjutan**: `ResolutionLogTab` sekarang fetch `GET /api/wh/returns?status=Resolved` + merge (dedup via `marketing_returns.wh_return_id` set). Item type baru `wh_return` dgn badge hijau "Retur Fisik". Non-blocker sebelumnya kini tertutup.
- **11a langkah lanjutan** (opsi A "auto-sync 2-arah") — dipending sesuai keputusan user (11a=B); dapat di-upgrade kapan pun bila 24-jam soft-guard terbukti kurang.

---

## STATUS UPDATE — RC-FLOW-UX-CORE SELESAI ✅ (Session #25, testing iter#40 = 100%)

**Fondasi `onNavigate` sudah TERPASANG & ROBUST untuk SEMUA modul:**
- `onNavigate(moduleId, params)` sudah di-pass App.js ke SETIAP `ModuleComponent` (branch PortalShell & collaboration) dan diteruskan lewat hub (`WMSStockHub`/dll → `HubTabs` `{...rest}` → tab component). Jadi semua modul (termasuk tab hub) menerimanya.
- **App.js `handleNavigate` di-upgrade** jadi navigasi onward penuh:
  1. **Cross-portal switch** — bila modul target ada di portal lain yang boleh diakses (`findPortalForModule` + `canAccessPortal`), `selectedPortal` ikut pindah + `localStorage.erp_portal` di-set → sidebar/top-nav konsisten (Marketing→Gudang, SDM→Keuangan, dst).
  2. **Hub-tab deep target** — `onNavigate(hubId, { tab: '<key>' })` set `sessionStorage.hub_tab_<hubId>` (kontrak `HubTabs`) untuk buka tab spesifik.
  3. Guard modul invalid, forward `deepLinkParams`, scroll-to-top.
- **Komponen reusable baru**: `components/erp/OnwardCTA.jsx` — bar "Langkah Berikutnya" konsisten (dual-theme, ikon+panah). API: `<OnwardCTA onNavigate={onNavigate} title actions={[{module,label,params?,icon?,primary?,hint?,testId?}]} />`.
- **CTA onward ter-pasang & TERVERIFIKASI**:
  - Alur 5 (CROSS-PORTAL): `marketing-orders` (UnifiedOrdersDashboard, portal Toko) → **"Proses Fulfillment di Gudang"** → `fulfillment` (portal Gudang). Terbukti portal pindah + FulfillmentModule render.
  - Alur 10: `maklon-po-360` (POPickerView) → **"Invoice & Billing"** → `maklon-billing` (same-portal Maklon).
  - Alur 1 (SUDAH ADA): `wh-purchase-orders` (PurchaseOrderModule) → buat GR → `onNavigate('wh-receiving', {receipt_id,...})`. Regresi OK.

**Cara menambah CTA onward baru (untuk agent berikutnya):**
1. Pastikan modul menerima prop `onNavigate` (top-level modul otomatis dapat; sub-komponen: teruskan prop-nya).
2. `import OnwardCTA from './OnwardCTA'` (atau `../OnwardCTA`).
3. Render setelah header/hasil: `<OnwardCTA onNavigate={onNavigate} title="…" actions={[{ module:'<id>', label:'…', icon: SomeIcon, primary:true }]} />`.
4. Cross-portal otomatis ditangani `handleNavigate` — cukup beri `module` id target yang valid di `MODULE_REGISTRY`.

**Kandidat CTA onward berikutnya (incremental, belum dipasang):** Alur 3 (WO → `prod-cutting`), Alur 6 (payroll → jurnal `fin-journal-*`), Alur 2 (GRN → `wh-putaway` → `wh-stock-hub`), **Alur 11** (marketing-after-sales `approved` → `wh-returns` receive **[cross-portal Toko→Gudang]**; `wh-returns` `resolve=Restock` → `marketing-after-sales` `create-credit-note` **[cross-portal Gudang→Toko]** — lihat RC-FLOW-UX-11b), Alur 9 (RnD sample approved → `rnd-techpack`/`maklon-po`). Semua tinggal pakai `<OnwardCTA/>` — fondasi sudah siap.

**Catatan khusus Alur 11 (retur/refund):** CTA onward memecahkan RC-FLOW-UX-11b saja. **RC-FLOW-UX-11a (2 sistem retur paralel) & 11c (complete tanpa restock) TIDAK bisa diselesaikan hanya dengan CTA** — butuh keputusan sistemik (skema data + backend handler). Rekomendasi urutan: (1) pasang CTA dulu untuk menutup gap navigasi (murah, non-destruktif); (2) minta keputusan user untuk sinkronisasi 2-arah `marketing_returns ↔ wh_returns`; (3) baru eksekusi RC-FLOW-UX-11a/11c/11d bila disetujui.

**Catatan non-kritis (pre-existing, di luar scope):** warning React DOM nesting `<span> cannot be a child of <option>` di WarehouseDashboard (console-only, tak pengaruh fungsi).
