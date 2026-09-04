# BUG REGISTER (Global) — DA37 ERP Dokumentasi & QA

<!-- Sumber kebenaran bug lintas modul. Bug TIDAK ditampilkan di dokumen training.
     Setiap modul punya file QA sendiri: docs/user-guide/_qa/<moduleId>_bugs.md -->

> **Kebijakan (v3):** Dokumen training di `docs/user-guide/<portal>/<moduleId>.md` **WAJIB bebas bug**.
> Semua temuan bug/observasi dicatat **di sini** (ringkasan lintas modul) + di file QA per modul.
> Validator `scripts/docgen/validate_module.py` akan **menolak** dokumen training yang masih
> memuat tag `BUG-`/`OBS-` atau section bug.

**Legenda status:** ✅ FIXED · 🔧 IN-PROGRESS · 🕒 OPEN · 🧭 BY-DESIGN (enhancement)
**Severity:** High (blokir fungsi/500/data salah) · Medium (fungsi jalan tapi keliru minor) · Low (kosmetik/UX)

---

## Ringkasan per Modul
| Modul | File QA | #Temuan | High | Med | Low | Status |
|---|---|---|---|---|---|---|
| `prod-orders` | [prod-orders_bugs.md](prod-orders_bugs.md) | 8 | 1 | 2 | 5 | ✅ semua selesai/diklasifikasi |
| `prod-work-orders` | [prod-work-orders_bugs.md](prod-work-orders_bugs.md) | 1 (+1 obs) | 0 | 1 | 0 | ✅ fixed + diverifikasi |
| `prod-bundles` | [prod-bundles_bugs.md](prod-bundles_bugs.md) | 1 (+2 obs) | 0 | 0 | 1 | ✅ fixed + diverifikasi |
| `production-dashboard` | [production-dashboard_bugs.md](production-dashboard_bugs.md) | 1 (+3 obs) | 0 | 0 | 1 | ✅ fixed + diverifikasi |
| `flow-produksi-inti` (alur) | [flow-produksi-inti_bugs.md](flow-produksi-inti_bugs.md) | 0 (+2 obs) | 0 | 0 | 0 | ✅ CLEAN — 18/18 uji + audit statis 0 FAIL |
| `flow-maklon-inti` (alur) | [flow-maklon-inti_bugs.md](flow-maklon-inti_bugs.md) | 2 (+1 obs) | 0 | 1 | 1 | ✅ fixed + diverifikasi — 17/17 uji + E2E 8/8 + audit 0 FAIL |
| `flow-gudang-inbound` (alur) | [flow-gudang-inbound_bugs.md](flow-gudang-inbound_bugs.md) | 0 (+2 obs) | 0 | 0 | 0 | ✅ CLEAN — 16/16 uji + audit 0 FAIL |
| `flow-keuangan-kas-bank` (alur) | [flow-keuangan-kas-bank_bugs.md](flow-keuangan-kas-bank_bugs.md) | 1 (+3 obs) | 1 | 0 | 0 | ✅ fixed + diverifikasi — POC 30/30 + validator 10/10 + DB pristine |
| `flow-maklon-client-portal` (alur) | [flow-maklon-client-portal_bugs.md](flow-maklon-client-portal_bugs.md) | 0 (+6 obs) | 0 | 0 | 0 | ✅ CLEAN — POC 29/29 + validator 10/10 + DB pristine (SEED utuh) |
| `flow-sdm-kpi-okr` (alur) | [flow-sdm-kpi-okr_bugs.md](flow-sdm-kpi-okr_bugs.md) | 0 (+6 obs) | 0 | 0 | 0 | ✅ CLEAN — POC 30/30 + validator 10/10 + DB pristine (SEED utuh) |

---

## Log Bug Global
| BUG-ID | Modul | Severity | Status | Ringkas |
|---|---|---|---|---|
| BUG-003 | prod-orders | High | ✅ FIXED | Stage Tracking 404 untuk order Rahaza → fallback koleksi `rahaza_orders` |
| BUG-001 | prod-orders | Medium | ✅ FIXED | API buat/edit order menerima items kosong → guard 400 |
| BUG-002 | prod-orders | Medium | ✅ FIXED | Qty non-numerik → 500 → item di-skip (400 bila semua invalid). API-only |
| OBS-004 | prod-orders | Low | ✅ FIXED | Auto-confirm (Generate WO) tidak menulis audit |
| OBS-005 | prod-orders | Low | ✅ FIXED | Tombol tutup Audit drawer tertutup overlay z-index/pointer-events |
| OBS-006 | prod-orders | Low | 🧭 BY-DESIGN | Tombol mutasi tampil ke role tanpa izin (backend tetap 403) |
| OBS-007 | prod-orders | Low | ✅ FIXED | `order_date`/`due_date` tidak divalidasi format |
| OBS-008 | prod-orders | Low | ✅ FIXED | Status mati `production_complete` di kondisi render Stage panel |
| WO-BUG-001 | prod-work-orders | Medium | ✅ FIXED | Cetak LKP Massal melewatkan WO `in_production` (typo `in_progress`) di `lkp-bulk-today` |
| BDL-BUG-001 | prod-bundles | Low | ✅ FIXED | `<Modal>` tidak meneruskan `data-testid` → modal detail bundle tak bisa ditarget test (fix: forward ke `DialogPrimitive.Content`) |
| PD-BUG-001 | production-dashboard | Low | ✅ FIXED | Duplikat `data-testid="production-dashboard"` (hub + Overview) → selector ambigu (fix: Overview → `production-dashboard-overview`) |
| MKL-TID-001 | flow-maklon-inti (maklon-po) | Medium | ✅ FIXED | `MaklonPOModule.jsx` hanya 2 `data-testid` statis → kontrol jalur utama (Buat PO/Konfirmasi/Dispatch/Post-AR/Simpan/field item) tak bisa ditarget test. Fix: tambah test-id happy-path (non-breaking); esbuild OK + audit 0 FAIL |
| MKL-UX-001 | flow-maklon-inti (maklon-po) | Low | ✅ FIXED | Tab default daftar PO = `active` → PO baru (Draft) tak langsung terlihat (temuan E2E). Fix: default tab → `all` (Semua) |
| CUT-TID-001 | flow-produksi-cutting (prod-cutting) | Low | ✅ FIXED | `CuttingProcessModule.jsx` minim `data-testid` pada elemen request/batch → jalur happy-path (buat request/approve/reject/buat batch/status cut_done + field form) tak bisa ditarget test. Fix: tambah test-id non-breaking (`cutting-tab-*`, `cutting-create-*-btn`, `cutreq-*`, `cutbatch-*`, `cutting-req-approve/reject/makebatch-{id}`, `cutting-batch-cutdone/assign-{id}`); esbuild OK + audit 0 FAIL + E2E it_82 |
| AP-INFO-001 | flow-keuangan-ap (fin-3way-match) | Info | ✅ NOTED | Bill AP dapat dibuat manual (`/ap-invoices`) atau via 3-way match dari GR (`/ap-invoices/from-gr`); pembayaran tanpa `account_id` tak mengubah saldo kas. Backend POC ALL PASS (auto-JE send+payment) |
| JE-INFO-001 | flow-keuangan-jurnal (fin-journal-hub) | Info | ✅ NOTED | Report `general-ledger` butuh query `account_code`; jurnal dapat langsung post saat create. Backend POC ALL PASS (guard seimbang + laporan) |
| MWO-INFO-001 | flow-produksi-material-wo (wh-material-issue) | Info | ✅ NOTED | Auto-JE issue (Dr WIP/Cr Persediaan) best-effort — bernilai 0 bila material tanpa `unit_cost`; stok RM diisi via inbound/seed (tak ada API stock-in langsung). Backend POC ALL PASS (posting_ok=true saat unit_cost ada) |
| RC-FLOW-kasbank-1 | flow-keuangan-kas-bank (fin-petty-cash, fin-bank-transfer) | **High** | ✅ FIXED | `FINANCE_ROLES` tak menyertakan role Finance kanonik `accounting`/`staff_keuangan` → staf Keuangan (`finance@dewiaditya.id`) DITOLAK **403** saat buat/replenish/close dana kas kecil & buat/void transfer bank. Fix: tambah `accounting`,`staff_keuangan`,`finance_manager` ke `FINANCE_ROLES` di `rahaza_petty_cash.py` & `rahaza_bank_transfers.py`. Verifikasi: create fund & transfer → 200 (TC-11/TC-12 PASS) |
| KB-INFO-001 | flow-keuangan-kas-bank (fin-bank-recon) | Info | ✅ NOTED | Endpoint bank-recon hanya `require_auth` (tanpa role-gate approver); auto-match menulis flag `is_matched` ADDITIVE ke JE (tidak ubah akuntansi). Backend POC ALL PASS (30 assertions, auto-match 2/2, DB pristine) |

---

## Cara pakai (untuk agent/QA)
1. Saat menemukan bug selama dokumentasi/uji sebuah modul → catat di `_qa/<moduleId>_bugs.md` + tambahkan baris di **Log Bug Global** ini.
2. Bug **High** → fix langsung → verifikasi via `testing_agent_v3` → set status ✅ FIXED.
3. Bug Med/Low → catat; fix bila diminta owner.
4. **Jangan** menuliskan tag bug di dokumen training — validator akan gagal.

## Toolchain Guardrail (v4 — Flow-centric)
> Validator dokumen hanya memeriksa **teks markdown**. Untuk mencegah regresi testabilitas DOM,
> mutu kode divalidasi terpisah oleh:
- `scripts/docgen/validate_flow.py` — gerbang dokumen alur (anti-halusinasi + cakupan endpoint
  happy-path + kedalaman ≥ 800 baris + bukti uji). Longgar pada cakupan test-id 100%, ketat pada mutu inti.
- `scripts/docgen/audit_testids.py` — **auditor statis** `data-testid` React: mendeteksi duplikat
  lintas-file (pola PD-BUG-001), duplikat dalam-file, prop tak diteruskan (pola BDL-BUG-001), dan
  elemen interaktif tanpa test-id. Jalankan sebelum uji E2E:
  `python3 scripts/docgen/audit_testids.py --module-id <id...>`.
- **E2E UI (`testing_agent_v3`)** tetap wajib untuk memastikan alur benar-benar jalan di browser.
