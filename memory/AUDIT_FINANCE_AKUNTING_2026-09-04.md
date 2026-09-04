# AUDIT PORTAL FINANCE & AKUNTING — 2026-09-04 (iter 107)

> Status: **TEMUAN SAJA — belum ada perbaikan dieksekusi** (arahan owner).
> Metode: baca kode (`routes/rahaza_posting.py`, `rahaza_fin_reports.py`, `rahaza_finance.py`, `rahaza_posting_profiles`, `coa_auto.py`, `dewi_maklon_finance.py`, `dewi_maklon_billing.py`, `production_maklon_bridge.py`, `marketing_settlements.py`, `rahaza_payroll_runs.py`, `dewi_bank_reconciliation.py`, `rahaza_bank_recon.py`, `rahaza_petty_cash.py`, `dewi_kasbon.py`, `employee_*`, `cascade_delete.py`, `core/fg_cost_layers.py`) **+ uji nyata di DB seed** dengan 2 skrip read/write-terkontrol (data uji dibersihkan):
> - `backend/scripts/audit_finance_integrity.py` — pemindai integritas GL/COA/subledger (read-only, boleh dijalankan kapan saja).
> - `backend/scripts/audit_finance_live.py` — transaksi uji AR/AP/maklon/jurnal manual + laporan, lalu cleanup.
>
> Kondisi DB saat audit: 8 JE (semua `posted`, semua seimbang, cermin `rahaza_journal_lines` konsisten), 275 akun COA, 0 periode, 0 cash account, `rahaza_customers` kosong.

## Ringkasan eksekutif
Mesin jurnal inti (`_create_posted_je`) **sehat**: validasi seimbang, akun ada/aktif/non-header, idempoten per `(source_module, source_ref)`, cermin baris hanya untuk `posted`, void menghapus cermin. Neraca Saldo seimbang. **Namun sambungan antar-modul dan peta akun tidak aman**: ada 6 temuan CRITICAL & 9 HIGH yang membuat Neraca tidak seimbang, saldo subledger tidak pernah nol, HPP dobel, pendapatan/piutang maklon tidak sampai ke GL, dan AP dari GR membebani "Listrik & Air Kantor".

| Severity | Jumlah |
|---|---|
| CRITICAL | 6 |
| HIGH | 10 |
| MED | 9 |
| LOW | 5 |

---

## A. CRITICAL

### C-01 Subledger AR/AP dibuka di akun anak, ditutup di akun kontrol → saldo subledger tak pernah nol
- **Bukti (uji T1):** AR invoice pelanggan (Auto-COA aktif) → JE `Dr 1-1301-AUDIT "Piutang Pelanggan — AUDIT Customer" 222.000`. Pembayaran → JE `Cr 1-1301 "Piutang Usaha — Dagang" 100.000`.
- **Kode:** `post_ar_invoice` memakai `resolve_subledger_account(customer/channel)`; `post_ar_payment`, `post_credit_note`, `post_bad_debt_writeoff` memakai `mapping.credit_ar` (kontrol) tanpa resolusi subledger. Hal yang sama di AP: `post_ap_invoice` → subledger supplier/CMT (`2-1100-CMT-001`), `post_ap_payment` → `mapping.debit_ap` kontrol `2-1100`.
- **Dampak:** akun anak pelanggan/vendor membengkak selamanya, akun kontrol bersaldo **negatif**; statement pelanggan/vendor dari GL salah; rekonsiliasi subledger vs GL mustahil.
- **Rekomendasi:** semua sisi kredit/debit AR-AP (payment, CN, write-off, retur) wajib memakai akun yang **sama dengan JE penerbitan** (simpan `ar_account_code`/`ap_account_code` di dokumen invoice saat issue, pakai itu di semua posting berikutnya).

### C-02 AP dari Goods Receipt dibebankan ke "6-2200 Listrik & Air Kantor" + AP tercatat dobel dgn jurnal penerimaan bahan
- **Kode:** `rahaza_ap_from_gr.create_ap_from_gr` tidak mengisi `gl_debit_code` → `post_ap_invoice` memakai `mapping.debit_expense_default = 6-2200` (= **Listrik & Air Kantor** di COA ter-seed). Sementara penerimaan stok (`post_inventory_receive`, 6 JE di DB) sudah `Dr 1-1401 Persediaan / Cr 2-1100 Hutang Usaha`.
- **Dampak:** setiap invoice supplier bahan/aksesori: (1) beban listrik naik sebesar nilai bahan, (2) Hutang Usaha dicatat **dua kali** (GR + invoice), (3) persediaan benar tapi L/R & neraca salah. GL AP saat ini 6.523.125 vs subledger AP 0 (`subledger_vs_gl`).
- **Rekomendasi:** AP-dari-GR harus `Dr 2-1100 (AP clearing/GRNI) / Cr AP vendor`, atau ubah `inventory_receive` mengkredit akun **GRNI** terpisah (mis. 2-1150 "Hutang Belum Ditagih") yang dibersihkan oleh AP invoice. Bug 6-2200 sudah pernah ditemukan utk CMT (komentar FASE IA-C) tapi tidak diperbaiki untuk `ap_invoice` umum.

### C-03 Biaya jahit CMT dibukukan DUA KALI (AP CMT → 5-231 COGS, lalu lagi lewat lapisan FG → 5-2000 COGS saat dispatch) & FG/WIP tidak pernah dikapitalisasi
- **Kode:** `post_cmt_ap_invoice` → `Dr 5-231 Biaya Vendor CMT – Jahit` langsung (beban periode). `core/fg_cost_layers` memasukkan `cmt_price_snapshot` sebagai `sewing_cost` lapisan batch → `post_cogs_on_buyer_dispatch` → `Dr 5-2000 HPP Tenaga Kerja / Cr 1-1404 FG` untuk nilai yang sama. Tidak ada satu pun jurnal `Dr WIP/FG` untuk upah jahit & overhead (`grep 1-330` hanya di MI).
- **Dampak:** HPP tenaga kerja **2×**; akun `1-1404 Persediaan FG` bersaldo **negatif** sebesar porsi jahit+overhead karena FG masuk hanya senilai material MI (`post_wip_to_fg_on_job_complete`) tapi keluar senilai material+jahit+overhead.
- **Rekomendasi:** pilih satu model: (a) *absorption* — AP CMT `Dr 1-330 WIP`, job complete `Dr FG / Cr WIP` senilai bahan+jahit+overhead, dispatch `Dr COGS / Cr FG`; atau (b) *period cost* — hapus komponen jahit/overhead dari jurnal COGS dispatch (tetap di lapisan biaya utk analitik).

### C-04 Neraca TIDAK seimbang: tipe akun `CURRENT_ASSET` & `OTHER` tidak dikenali laporan
- **Bukti (uji T4):** jurnal `Dr 1-1320 Piutang Pinjaman Karyawan / Cr 1-1201` 500.000 → `balance-sheet.balanced=false`, `diff=-500.000`, `1-1320` tidak muncul di aset; Neraca Saldo tetap seimbang (memakai semua akun).
- **Kode:** `rahaza_fin_reports.balance_sheet` hanya mengelompokkan `ASSET|LIABILITY|EQUITY|REVENUE|COGS|EXPENSE|OTHER_INCOME|OTHER_EXPENSE`; COA memuat `1-1320` bertipe `CURRENT_ASSET` (dipakai profil `employee_loan_*`) dan grup `7-0000` bertipe `OTHER`.
- **Rekomendasi:** normalisasi tipe COA (`CURRENT_ASSET→ASSET`), tambahkan validasi tipe pada `POST/PUT coa`, dan laporan menolak/menandai tipe tak dikenal.

### C-05 Profil `asset_disposal` menunjuk akun yang salah total
- **Data (`rahaza_posting_profiles`):** `credit_fixed_asset = 1-1501` (= **PPN Masukan**), `debit_accum_depr = 1-1502` (= **PPh 22/23 Dibayar Dimuka**). Profil `asset_acquisition` benar (`1-2500 Inventaris`, `1-2501 Akum. Penyusutan`).
- **Dampak:** penjualan aset mengurangi PPN Masukan & PPh dibayar dimuka, aset tetap & akumulasi tidak pernah keluar dari neraca. Fallback hard-code di `post_depreciation` juga salah (`6-3100` = Tunjangan & Bonus, `1-1502`).
- **Rekomendasi:** perbaiki seed profil + hapus semua fallback kode akun hard-code di `rahaza_posting.py` (ganti dengan error "mapping belum lengkap").

### C-06 Pendapatan, piutang & penerimaan kas Maklon tidak sampai ke GL
- **Bukti (uji T3):** `POST /dewi/maklon/invoices/generate` → AR `issued` 799.200 tapi **0 JE**; `POST /dewi/maklon/payments` 100.000 → **0 JE**, tidak ada `rahaza_cash_movements`. Satu-satunya pintu GL adalah manual `POST /api/dewi/maklon/finance/pos/{id}/post-ar` yang (a) boleh dipanggil saat AR masih **draft** (nilai = qty *order*, bukan yang diterima), (b) tanggal JE = `po_date` bukan tanggal invoice, (c) bila invoice di-generate setelahnya, JE **tidak disesuaikan** (tidak ada void/re-post), (d) langsung menyetel AR `issued` melewati alur generate.
- **Dampak:** L/R & AR GL tidak memuat bisnis maklon; kas bank tidak bertambah saat klien bayar; `gl_posted_at` yang dipakai `cancel_invoice` sebagai gerbang tidak pernah terisi lewat alur normal.
- **Rekomendasi:** `_generate_from_engine_ar` → panggil `post_maklon_ar_invoice` (tanggal = issue_date, nilai = AR final); `record_payment` → `post_ar_payment` + `rahaza_cash_movements`; `cancel` → `void_ar_invoice_posting`; tolak `post-ar` bila AR masih draft.

---

## B. HIGH

### H-01 Dua kamus status & dua skema field di `rahaza_ar_invoices` → Aging Finance buta terhadap AR Maklon
- Rahaza: `status ∈ {draft,sent,partial_paid,paid,overdue}`, field `total/paid_amount/balance`. Maklon (`production_maklon_bridge`, `dewi_maklon_billing`): `status ∈ {draft,issued,partial_paid,paid,cancelled}`, field `total_amount/amount_paid/amount_due`.
- **Bukti:** `GET /rahaza/ar-aging` total 122.000 (hanya AR uji), `GET /dewi/maklon/reports/aging` 699.200 (hanya maklon). `write-off-bad-debt` mensyaratkan `sent/overdue` → AR maklon tak bisa di-write-off. `post_ar_invoice` membaca `invoice.total` → utk dokumen maklon nilainya 0 (baris AR di-skip → "Jurnal harus minimal 2 baris").
- **Rekomendasi:** satu skema kanonik (`total_amount/amount_paid/amount_due`, `issued`), migrasi data, dan satu laporan aging.

### H-02 Payroll finalize tidak memisahkan PPh21/BPJS → liabilitas pajak & BPJS di GL selalu 0 lalu negatif saat dibayar
- `rahaza_payroll_runs` menyimpan `total_gross/total_deductions/total_net` saja; `post_payroll_run` membaca `run.total_pph21` & `run.total_bpjs_employee` (tidak ada) → seluruh potongan masuk `Cr 2-1200 Hutang Gaji "Other Deductions"`. Endpoint bayar BPJS/PPh21 kemudian `Dr 2-1500` / `Dr 2-1301` → kedua akun **debit (negatif)**, 2-1200 lebih saji.
- Tambahan: kondisi `total_net + pph21 + bpjs + other_ded == total_gross` memakai kesetaraan float → bila gagal, JE tak seimbang → posting **gagal diam-diam** (`post_error`). Potongan kasbon juga masuk 2-1200, sementara `employee_loan_repayment_payroll` mengkredit 1-1320 dari 2-1200 → bergantung urutan pemanggilan.
- **Rekomendasi:** agregasi `deductions[]` per `type` (pph21/bpjs_*/kasbon/lainnya) di run, posting per komponen ke akun liabilitas masing-masing, toleransi 0,01.

### H-03 CMT payment (AP vendor CMT) tidak punya alur bayar → AP CMT tidak pernah dilunasi di GL
- `dewi_cmt_payments` hanya ditulis oleh bridge (`draft`) dan `post-ap`; tidak ada endpoint approve/pay/void; dashboard vendor menghitung `status=='paid'` yang tak pernah terjadi. Tidak ada `Dr AP / Cr Bank` untuk CMT.

### H-04 Dua keluarga kode akun (3-digit legacy `1-110/1-120/1-131/1-210/1-220/2-110/2-120/2-130/1-310..` vs 4-digit `1-1201/1-1301/1-1401/2-1100/2-1200/2-1400`) untuk konsep yang sama, dan profil posting mencampurnya
- `ar_payment.debit_cash_default = 1-110 Kas Kecil` (penerimaan piutang default ke kas kecil); `maklon_advance_payment.debit_cash_default = 1-131`; kasbon (`dewi_kasbon`) memakai `1-120 Kasbon Karyawan` & `2-120 Hutang Gaji Karyawan` (kunci mapping `debit_loan_receivable/credit_cash` **tidak cocok** dgn profil `employee_loan_disbursement` yang berkunci `debit_employee_loan_receivable` → selalu fallback), sedangkan `rahaza_employee_loans` memakai `1-1320` & `2-1200`. AR maklon → `1-1301 Piutang Dagang` (ada `1-210 Piutang Usaha – Maklon` yang menganggur); pendapatan maklon → `4-1100 Penjualan Garment`; PPN keluaran ada `2-130` **dan** `2-1400`; persediaan ada `1-310/1-320/1-340/1-350` **dan** `1-1401/1-1402/1-1404`.
- **Dampak:** saldo satu konsep terpecah di 2–3 akun; neraca terbaca ganda; owner memilih akun yang tak pernah terisi.
- **Rekomendasi:** putuskan satu skema; nonaktifkan (bukan hapus) akun legacy; skrip migrasi jurnal; mapping profil diselaraskan.

### H-05 Kas/Bank: cash account & bank subledger tidak sinkron dgn akun yang dipakai modul lain
- Auto-COA bank membuat `1-1200-<CODE>` (uji: `1-1200-AUDIT-BANK-2`) dan **menimpa** `gl_account_code` yang diberikan (1-1201). Namun `marketing_settlements` (`COA.cash=1-1201`), bank recon adjustment (`1-1201` hard-code), payroll payment default `1-1201`, petty cash replenish `1-1201`, kasbon `1-131` — semua melewati cash account. `rahaza_cash_accounts.balance` di-`$inc` manual di beberapa endpoint (AR/AP payment, expense, recon) tapi tidak oleh settlement/payroll/petty cash → saldo kartu kas ≠ GL ≠ mutasi.
- **Rekomendasi:** semua posting kas wajib lewat `cash_account_id` → `gl_account_code`; saldo kas dihitung dari GL, bukan field `balance`.

### H-06 Rekonsiliasi bank: sisi GL selalu kosong & auto-match menyentuh JE non-bank
- `get_session` memfilter `rahaza_journal_entries` dgn `account_type in [kas,bank,cash,bank_account]` — field itu **tidak ada** di dokumen JE (ada di baris sebagai `ASSET`) → daftar GL kosong. `auto_match` mencocokkan **semua** JE posted periode itu tanpa filter akun bank, lalu menulis `is_matched`/`match_score` ke dokumen JE (mencemari SSOT jurnal). Adjustment recon selalu ke `1-1201` apa pun bank sesinya.

### H-07 Fulfillment PO internal: COGS dibukukan saat dispatch, pendapatan tidak pernah
- `buyer_shipment` dispatch → `post_cogs_on_buyer_dispatch` (Dr COGS/Cr FG) tetapi tidak ada AR/pendapatan untuk PO internal (pembuat AR: `rahaza_finance` manual, `rahaza_shipments` legacy tidak dipakai). Pendapatan online shop hanya lahir dari `marketing_settlements` (cash basis, **draft**), beda periode dgn COGS.
- **Dampak:** laba kotor per periode salah (biaya di bulan kirim, pendapatan di bulan pencairan, atau tidak sama sekali utk buyer B2B).

### H-08 Kontrol periode hanya berlaku bila dokumen periode ada
- **Bukti (T5):** jurnal tertanggal `2019-01-15` diterima (`rahaza_periods` kosong). `_ensure_period_open` hanya menolak status `closed/locked` dari periode yang **terdaftar**; tidak ada `ensure-year` otomatis, tidak ada batas tanggal masa depan.

### H-09 Jurnal maklon `post-ar` idempoten per AR id tetapi tidak reaktif terhadap perubahan nilai (lihat C-06c) & `cancel_invoice` bergantung `gl_posted_at` yang tidak diisi jalur normal → invoice yang sudah masuk GL lewat `post-ar` manual lalu di-*generate*/cancel meninggalkan JE yatim.

### H-10 Retur/credit note & diskon salah akun
- `post_ar_invoice` diskon → fallback `6-1100` (= **Biaya Iklan & Promosi**), padahal ada `4-1300 Diskon Penjualan`. `post_credit_note` → `Dr 4-1100 / Cr 1-1301` (kontrol, lihat C-01) dan tidak memakai `4-1200 Retur Penjualan`; PPN pada CN tidak dibalik. `post_bad_debt_writeoff` fallback `6-2600` (= **Asuransi**).

---

## C. MED

- **M-01** Nilai persediaan untuk jurnal MI/adjust/scrap = `rahaza_materials.unit_cost` (harga master saat ini), bukan biaya lapisan/rata-rata saat transaksi → HPP bahan bergeser saat harga master diubah; `post_inventory_receive` juga fallback ke unit_cost master.
- **M-02** `post_cogs_shipment` (legacy `rahaza_shipments`) masih di-import `fulfillment.py`/`rahaza_shipments.py` dan memakai snapshot HPP per WO — dua mesin COGS paralel dgn `post_cogs_on_buyer_dispatch`.
- **M-03** `cmt_ap_invoice.debit_cmt_expense_maklon = 7-120` bertipe **EXPENSE** di grup 7 "Pendapatan & Beban Lain-lain" → biaya proyek maklon masuk "Beban Operasional", bukan HPP maklon; laba kotor maklon (yang baru dihitung di mirror `gross_margin`) tidak konsisten dgn L/R.
- **M-04** Penalti keterlambatan CMT dikredit ke `4-920 Pendapatan di Luar Usaha` (pendapatan) alih-alih mengurangi biaya CMT; total AP dikurangi penalti tapi `dewi_cmt_payments.net_amount` tidak diperbarui saat penalti diubah.
- **M-05** Pencairan marketplace: `platform_fee` ke `4-141` (kontra-pendapatan) vs `ads` ke `6-1100` (beban) — kebijakan campur; `other` ke `7-4000` untuk **dua arah** (subsidi ongkir kredit & potongan lain debit) → saling menetralkan di satu akun. JE dibuat `draft` dan tidak ada notifikasi ke Finance utk approve → potensi menumpuk tak terposting.
- **M-06** `post_expense`, `employee_expense_claims`, `petty_cash` default kredit `1-110 Kas Kecil` bila bank tidak dipilih → klaim karyawan yang ditransfer bank tercatat keluar dari kas kecil.
- **M-07** Aging AR rahaza menghitung `overdue` dari `due_date` tapi status `overdue` hanya diset oleh proses lain (tidak ada cron) → invoice `sent` lewat jatuh tempo tetap "current" di sebagian layar; maklon `_recalc_invoice` menyetel `overdue` hanya saat dipanggil (bayar/cancel).
- **M-08** `trial_balance` saldo awal: cabang `normal_balance=CREDIT` menghitung `opening_debit/credit` identik dgn cabang DEBIT (kode duplikat) — benar secara angka tapi menandakan penanganan akun kontra (`1-211`, `1-521..`, `3-400`, `4-140/141/230`, `5-130/260` bertipe ≠ normal_balance) tidak pernah dirancang; 11 akun `type_normal_mismatch`.
- **M-09** Neraca "Laba Tahun Berjalan" = akumulasi **sejak awal data** (tanpa closing entry/laba ditahan), sedangkan L/R default YTD → tahun kedua angkanya tidak sebanding; tidak ada proses tutup tahun (`3-xxx Laba Ditahan`).

## D. LOW

- **L-01** `_gen_je_number` dua implementasi (`rahaza_posting` vs `rahaza_journals`) dgn prefix sama `JE-YYYYMMDD-` — counter berbeda dapat menghasilkan nomor tabrakan (unique index?) — perlu dicek indeks `je_number`.
- **L-02** `post_production_variance` & `post_asset_acquisition` tidak `return result` (fungsi berakhir tanpa return → pemanggil menerima `None`, log "N/A").
- **L-03** Kode akun hard-code tersebar (>40 tempat): `rahaza_posting.py`, `marketing_settlements.COA`, `employee_travel_settlements.GL_*`, `rahaza_payroll_runs` (`2-1500`, `2-1301`, `1-1201`), `dewi_kasbon`. Semua harus lewat posting profile.
- **L-04** `rahaza_customers` kosong di seed sementara klien maklon ada di `dewi_maklon_clients` & buyer PO di master lain → AR manual Finance tidak bisa memilih pelanggan yang sama dgn Produksi/Maklon (dua master pelanggan).
- **L-05** `cascade_delete` PO menghapus AR `draft` saja (benar), tetapi mirror `dewi_maklon_pos` ikut dihapus walau AR `issued/paid` masih ada → AR yatim tanpa PO (`linked_maklon_po_id` menggantung).

---

## E. Yang terbukti AMAN (tidak perlu tindakan)
- `_create_posted_je`: seimbang (0 JE tak seimbang), akun divalidasi, header ditolak, baris nol dilewati, idempoten, cermin hanya untuk `posted` (draft settlement tidak mencemari TB), void menghapus cermin.
- Neraca Saldo (TB) seimbang; agregasi GL/TB/L/R konsisten dari `rahaza_journal_lines`.
- Iter 106: AR maklon ↔ cermin invoice satu id/nomor; payment propagasi `amount_paid/amount_due`; cancel mengembalikan AR draft; cancel invoice yang sudah dibayar ditolak (400).
- Auto-COA membuat akun anak postable dgn tipe/normal balance warisan parent, kode unik, jejak `flags.subledger_*`.
- RBAC finance: `deny_external_dep` di router maklon finance/billing; klien & vendor 403 (iter 105).

## F. Urutan perbaikan yang disarankan (bila disetujui)
1. **C-01 + C-06** — satu akun AR/AP per dokumen untuk semua posting; generate/payment/cancel maklon → GL otomatis. (dampak terbesar, risiko kecil)
2. **C-02** — GRNI clearing untuk penerimaan bahan & AP-dari-GR; `debit_expense_default` diganti ke akun beban umum yang benar.
3. **C-04 + H-04 + C-05** — bersihkan COA (tipe, akun ganda, profil disposal), hapus fallback hard-code.
4. **C-03** — putuskan model kapitalisasi jahit/overhead; sesuaikan WIP→FG & COGS.
5. **H-01** — unifikasi skema/status AR + satu aging.
6. **H-02, H-03, H-05, H-06** — payroll komponen, alur bayar CMT, kas lewat cash account, recon bank.
7. **H-07, H-08, M-xx** — pendapatan PO internal, periode wajib, closing tahunan.

Setiap langkah wajib disertai: migrasi data JE lama (void+re-post per `source_ref`), pengujian `audit_finance_integrity.py` (0 temuan) dan `balance-sheet.balanced=true`.
