# CLEANUP MASTER PLAN — DA53 ERP
**Dokumen sintesis komprehensif untuk pembersihan/de-duplikasi (semua yang belum dikerjakan)**
Sifat: **READ-ONLY analysis** — belum ada perubahan kode dalam dokumen ini. Tanggal: sesi optimalisasi lanjutan.

---

## 0. Cara Baca Dokumen Ini

Setiap kandidat dinilai dengan **5 dimensi verifikasi silang** (multi-metode) agar akurat & aman:

| Dim | Nama | Pertanyaan |
|---|---|---|
| **D1** | Data | Berapa dokumen? (0 = kosong) |
| **D2** | Kode backend | Siapa menulis/membaca? **Coupling** = berapa file berbeda menyentuhnya |
| **D3** | Frontend | Modul/menu mana? Tampil di sidebar? |
| **D4** | Linkage/FK | Apakah id-nya direferensikan koleksi/kode lain? (risiko RC-6 memutus relasi) |
| **D5** | Semantik | Duplikat sejati atau pemisahan domain yang sah? |

### Tier Keamanan (hasil kombinasi dimensi)
- 🟢 **T1 — AMAN SEKARANG**: kosong/junk, tanpa reader nyata, tanpa modul, coupling ≤1, tanpa FK. Drop/redirect tanpa risiko.
- 🟡 **T2 — BUTUH MIGRASI**: ada data (kecil), duplikat sejati. Perlu skrip migrasi idempoten + verifikasi.
- 🟠 **T3 — DEDUP MENU (frontend)**: risiko data rendah, cukup redirect/gabung-tab, TAPI wajib pastikan kanonik menutup fungsi sumber.
- 🔴 **T4 — RISIKO TINGGI / TUNDA**: coupling tinggi, dual-active, atau bug laten. Perlu kerja per-klaster hati-hati.
- ⚪ **KEEP**: dorman tapi terpasang di alur aktif → **JANGAN sentuh** (keputusan user: "semua modul dipakai").

**Prinsip eksekusi (wajib):** *bekukan → (migrasi bila ada data) → re-point/redirect → verifikasi (data+render) → arsip.* Simpan `makeRedirect` untuk deep-link. Rollback = kembalikan 1 baris / restore koleksi.

---

## 1. Yang SUDAH Dikerjakan (baseline)
- ✅ **O1.2** De-dup CMT (frontend): 5 menu CMT dihapus dari sidebar Produksi + redirect ke `vendor-admin`/`wms-cmt-dispatches`/`wms-delivery-notes`. Terverifikasi (testing agent 95%, tanpa regresi).
- ✅ **O1.3** Drop junk mati: `rahaza_kpi_results` (30), `dewi_tasks` (10) + nonaktif seed. Kanonik `da_kpi_results` (25) utuh.
- ✅ **Session #12 Phase A** Linting: Ruff backend 52→0, ESLint frontend 13→0 (refactor React hooks: useMemo auth headers + functional setState PettyCash). Verified: build 0 warning, health 200, render OK.
- ✅ **W3 (Tier 1)** Drop 3 koleksi 100% dead: `rahaza_onboarding_checklists` (1, seed-only; kanonik `dewi_onboarding_checklists`), `accessory_inspections` (0), `accessory_defects` (0). Nonaktif seed + hapus index scaffolding server.py. DB 256→253, tidak di-recreate setelah restart. Testing agent iteration_26: Backend 100% (20/20), 0 regresi.

---

## 2. 🟢 TIER 1 — ✅ SELESAI (W3)

Semua lolos multi-metode: kosong/junk, **tanpa reader nyata, tanpa modul sidebar, coupling ≤1, tanpa FK**. Pola identik dengan O1.3 yang sudah terbukti aman. **DIEKSEKUSI di Session #12 (W3).**

| Koleksi | D1 docs | D2 coupling | D3 modul | Aksi | Kanonik | Status |
|---|---|---|---|---|---|---|
| `rahaza_onboarding_checklists` | 1 (seed-only) | 1 (seed) | — | Nonaktif seed + drop | `dewi_onboarding_checklists` | ✅ DONE |
| `accessory_inspections` | 0 | 1 (server.py index; route NOOP) | — | Hapus index + drop | (subsistem mati) | ✅ DONE |
| `accessory_defects` | 0 | 1 (server.py index; route NOOP) | — | Hapus index + drop | (subsistem mati) | ✅ DONE |

**Rollback:** koleksi kosong/junk — restore trivial. **DoD:** ✅ backend health 200, tidak ada modul error, koleksi tidak di-recreate.

---

## 3. 🟡 TIER 2 — BUTUH MIGRASI DATA (medium, hati-hati)

### T2.1 — Kasbon Legacy → Kasbon Baru ✅ SELESAI (Session #12, Phase D)
- **D1:** `rahaza_employee_loans` = **3 dok** (ada data). Kanonik `dewi_kasbon_requests` + `dewi_kasbon_installments`, aktif.
- **D2:** coupling 2 (`rahaza_employee_loans.py` + seed). `rahaza_posting.py` memakai `loan_id`. **VERIFIED GL-SAFE:** `rahaza_journal_entries` = 0 referensi ke 3 loan → murni seed tanpa histori GL.
- **D3:** menu `hr-employee-loans` ("Pinjaman Karyawan (Legacy)").
- **D4:** **0 referensi FK eksternal** ke 3 loan id.
- **D5:** Konsolidasi sah — `dewi_kasbon.py` (BARU) SUPERSET, mendukung `type: pinjaman` + GL.
- **DIEKSEKUSI:**
  1. ✅ Skrip idempoten `backend/migrations/t2_1_migrate_employee_loans_to_kasbon.py` (backup JSON + marker `migrated_from_loan_id`) → 3 record → `dewi_kasbon_requests` (type=pinjaman, status=disbursed).
  2. ✅ Redirect menu `hr-employee-loans` → `makeRedirect('hr-kasbon')`; menu Legacy dihapus dari sidebar; import di-comment. Koleksi legacy **diarsip (TIDAK di-drop)**.
  3. ✅ **BUG FIX** `GET /api/dewi/kasbon/stats` 500 (seed `created_at` datetime di-slice string) → helper `_ym()` robust. Kini 200, outstanding Rp 26.166.668.
- **Verifikasi:** testing_agent iteration_28 Backend 100% (53/53), 0 bug; UI: 3 pinjaman tampil + kartu outstanding benar.
- **Rollback:** hapus dokumen `dewi_kasbon_requests` dengan `{"migrated_from":"rahaza_employee_loans"}` + restore backup + kembalikan baris menu.

---

## 4. 🟠 TIER 3 — DEDUP MENU FRONTEND (redirect / gabung-tab)

Risiko data rendah, tapi **wajib verifikasi kanonik menutup fungsi sumber** sebelum eksekusi.

> **Update Session #12 (W4):** Verifikasi coverage sudah dijalankan untuk T3.1/T3.2/T3.7/T3.8. **Hanya T3.1 yang benar-benar duplikat** dan sudah dieksekusi. T3.2/T3.7/T3.8 ternyata BUKAN duplikat (lihat kolom Status) → JANGAN digabung/hapus.

| # | Duplikat | Kanonik | Status / Catatan verifikasi |
|---|---|---|---|
| T3.1 | `wh-opname` (Stok Opname) | `wms-opname-enhanced` (RESMI) | ✅ **DONE (W4)**. `wh-opname`→`/api/wms/legacy/opname` (DEPRECATED); RESMI→`/api/wms/opname2` SSOT (superset). Menu dihapus + `makeRedirect`. testing_agent iteration_27 100%. |
| T3.2 | `unified-approval-hub` vs `hr-inbox` + `approval-multilevel` | ~~hub~~ | ❌ **SKIP — BUKAN duplikat**. Hub = agregator dashboard yang `onNavigate()` ke `hr-inbox`/`approval-multilevel` untuk aksi approve/reject. Hapus modul = rusak hub. |
| T3.3 | `fin-journal-entry` + `fin-journal-list` | 1 modul 2 tab | Konsolidasi komponen (belum) |
| T3.4 | Marketing AI 4× (`ai-insights`,`advanced-ai`,`ai-content`,`ai-image`) | 1 "AI Marketing" hub (tab) | Konsolidasi komponen (belum) |
| T3.5 | HR AI 5× (`hr-ai-insights`,`attrition`,`skill-gap`,`coaching`,`ai-actions`) | 1 "AI HR" hub (tab) | Konsolidasi komponen (belum) |
| T3.6 | Marketing Live 3× (`live`,`live-analytics`,`livehost`) | 1 "Live" hub (tab) | Konsolidasi komponen (belum) |
| T3.7 | `marketing-kreator-requests` vs `rnd-kreator-requests` | ~~1 approval~~ | ❌ **SKIP — BUKAN duplikat**. Dua id → komponen SAMA `KREATORRequestModule` untuk 2 audiens portal (RnD approve + Marketing kelola). Sudah optimal. |
| T3.8 | `maklon-notifications` dobel (Maklon + Marketing) | ~~1 lokasi~~ | ❌ **SKIP — cross-portal reuse** `NotificationCenterModule`. Hapus dari Marketing berisiko hilang akses notif Marketing. |
| T3.9 | RnD `rnd-hpp` vs `rnd-costing` | gabung tab | Konsolidasi komponen (belum) |

**Rollback:** semua reversibel (baris menu / makeRedirect). **DoD:** kanonik render + fungsi sumber tercakup + testing agent.
**Catatan W4:** scan otomatis konfirmasi **0 menu id kembar intra-portal** — struktur menu app sudah cukup bersih; sisa T3.3–T3.6/T3.9 adalah *konsolidasi komponen* (bukan duplikat murni), butuh effort lebih & keputusan produk.

---

## 5. 🔴 TIER 4 — RISIKO TINGGI / TUNDA (perlu kerja per-klaster)

| Klaster | Kenapa berisiko (bukti) | Rencana aman |
|---|---|---|
| **Arsip backend CMT** `dewi_cmt_*` | Coupling 4–8; dibaca `dewi_phase7_reports.py` + `dewi_cmt_seed.py`. Frontend SUDAH redirect. | Arsip route bertahap: bekukan endpoint → pastikan phase7-reports tetap jalan (empty) → pindah file ke `_archive` → verifikasi startup |
| **Shift dual-active** `hr_shifts`(7) vs `rahaza_shifts`(4) | `rahaza_shifts` coupling **10** (aps_scheduler + attendance + assignments). `hr_shifts` terisolasi (coupling 1) | Verdict: `rahaza_shifts` = kanonik operasional. Migrasi 7 `hr_shifts` → `rahaza_shifts` + redirect 2 menu HR shift. Uji absensi/penjadwalan menyeluruh |
| **`dewi_notifications`** (5, **write-only**) | Ditulis employee_expense/travel routes, **tak ada pembaca** → notifikasi dibuat tapi tak ditampilkan (bug laten) | Bukan dedup murni; arahkan penulisan ke `notifications` (kanonik, 59) → perbaikan fungsional |
| **Seed onboarding routing** | Seed menulis ke `rahaza_onboarding_checklists` (T1 drop), padahal modul baca `dewi_onboarding_checklists` (kosong) | Setelah T1: arahkan seed ke koleksi kanonik agar modul `hr-onboarding` berisi data (feature-fix terpisah) |

---

## 6. ⚪ KEEP — JANGAN Sentuh (dorman tapi terpasang di alur aktif)

Multi-metode membuktikan koleksi ini **kosong TAPI ter-coupling erat** → menghapus = berbahaya. Sesuai keputusan Anda "semua modul dipakai".

| Koleksi/Modul | Bukti KEEP |
|---|---|
| `production_pos` / `po_items` / `production_jobs` / `production_job_items` | Coupling **17/11/10/11** — dirujuk operations_*, dashboard, reports, production.py. Subsistem produksi dorman. |
| `rahaza_boms` | Coupling 7; dipakai modul aktif `prod-assignments`,`prod-bulk-mi` (BOM embedded di model) |
| `dewi_maklon_bom` / `dewi_maklon_hpp` | Terpasang di alur `dewi_maklon_pos` / `po_360` / billing |
| `dewi_rnd_hpp` + subsistem `dewi_rnd_*` | Modul RnD (dipakai per keputusan Anda) |
| **Aset**: `da_assets` (Portal Aset + `hr-assets` via `/api/dewi/assets`) & Finance `rahaza_fixed_assets`(15) | **KOREKSI analisis awal**: da_assets = koleksi modul aset (dorman, bukan duplikat hapus). Finance fixed-assets = domain akuntansi terpisah (sah) |
| `dewi_cmt_partners`, `dewi_cmt_component_requests` | Kosong tapi ter-wire; frontend sudah redirect. Backend biar diarsip di T4 |
| Marketing catalog/livehost, LMS, Toko flashsale | Modul dorman (dipakai per keputusan Anda) |

---

## 7. ⚪ BUKAN Duplikat (pemisahan domain sah — JANGAN gabung)
- **Portal Saya** (payslip/kpi/cuti/training/kasbon "Saya") = cermin self-service HR (beda audiens).
- **Laporan akuntansi standar**: COA, Neraca Saldo, Buku Besar, Laba Rugi, Neraca, Arus Kas, AR/AP Aging, Budget.
- **Sample** di maklon/rnd/marketing; **Return** marketing (after-sales) vs warehouse (fisik).
- **Expense**: `employee_*` (dinas/per-diem) vs `rahaza_expense*` (klaim) — fragmentasi kompleks, perlu kajian bisnis, **jangan buru-buru**.

---

## 8. Urutan Gelombang yang Disarankan (aman → berisiko)

| Gel | Isi | Risiko | Uji |
|---|---|---|---|
| **W3** | T1 (drop 3 junk: onboarding-checklists, accessory-inspections/defects) | Sangat rendah | health + smoke |
| **W4** | T3 dedup menu paling jelas (T3.1 opname, T3.2 approval, T3.7 kreator, T3.8 notif-menu) | Rendah | testing agent (nav/redirect) |
| **W5** | T2 kasbon (migrasi 3 record + GL) | Sedang | test kasbon + GL |
| **W6** | T3 konsolidasi komponen (AI hub, live hub, journal tabs, rnd hpp) | Sedang | testing agent |
| **W7** | T4 arsip backend CMT | Sedang-tinggi | regression penuh |
| **W8** | T4 shift dual-active (migrasi + attendance) | Tinggi | regression penuh HR/produksi |
| **W9** | Feature-fix: dewi_notifications routing, seed onboarding routing | Sedang | uji fungsional |

---

## 9. Risk Register & Catatan Jujur
1. **"Kosong ≠ mati"** terbukti berkali-kali (production_pos coupling 17, rahaza_boms coupling 7). Keputusan hapus **wajib** lolos D2 (coupling) + D3 (modul) + D4 (FK), bukan hanya D1 (docs).
2. **Manfaat visual** terbesar ada di T3/T4 (dedup menu). T1 murni kebersihan data backend (nilai kecil, risiko ~0).
3. **Dasar data** = snapshot DB saat ini + konfirmasi bisnis Anda. Bukan dari analitik pemakaian produksi nyata.
4. Setiap gelombang **berdiri sendiri & reversibel**; boleh berhenti kapan saja.

---
*Disintesis dari: FORENSIC_MASTER_REPORT.md + analisis manual mendalam Produksi/Maklon + komparasi SOMMERVILLE + Forensic Scanner v2 (5 dimensi) + deteksi linkage FK. Semua read-only.*
