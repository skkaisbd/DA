# QA / Bug Register — `flow-manajemen-approval-multilevel`

> Berkas ini memisahkan catatan QA/observasi dari materi training (sesuai standar v4).
> Materi training (`docs/user-guide/manajemen/flow-manajemen-approval-multilevel.md`) tetap bebas tag bug.

## Ringkasan Verifikasi

- **POC backend**: `tests/flow_manajemen_approval_multilevel_test.py` → **ALL PASS** (20 skenario, exit 0), self-cleanup (DB pristine).
- **Audit testid**: `scripts/docgen/audit_testids.py --module-id approval-multilevel` → **LULUS 0 FAIL** (15 testid statik unik).
- **Validator dokumen**: `scripts/docgen/validate_flow.py --flow-id flow-manajemen-approval-multilevel` → **LULUS 10/10** (0 WARN, 0 FAIL; 810 baris; rubrik 97/100).

## Observasi (LOW — non-blocking)

### AML-OBSERVASI-1 · Code smell: blok terduplikasi di `process_action`
- **Lokasi**: `backend/services/approval_chain_service.py`, fungsi `process_action` (± baris 302–389).
- **Deskripsi**: Badan logika transisi (set status level saat ini → hitung status baru → `update_one`) tampak **terduplikasi dua kali** dalam satu fungsi.
- **Dampak**: **Benign / tidak merusak happy-path.** Blok kedua membaca ulang `doc["current_level"]` in-memory yang **tidak berubah** (hanya variabel lokal yang diubah pada blok pertama), sehingga menghasilkan transisi **identik** dan tidak menyebabkan lompatan level. Diverifikasi via POC: approve tepat maju **satu** level; reject cascade benar; final approve → `approved`. Efek satu-satunya adalah **dua kali penulisan DB** (redundan).
- **Rekomendasi**: Refactor menghapus blok kedua (single update) pada sesi backend terpisah, dengan re-run POC sebagai regression gate. Bukan blocker untuk penandaan Done dokumen.

### AML-OBSERVASI-2 · Pengerasan RBAC pada layer aksi
- **Lokasi**: `backend/routes/approval_multilevel.py` — endpoint `approve`/`reject`.
- **Deskripsi**: Endpoint aksi memvalidasi **autentikasi + status** (guardrail state) namun tidak melakukan **hard-block peran** di layer aksi. Gating peran diterapkan di lapisan **inbox** (`GET /api/approvals/pending` memfilter berdasar `levels[current_level].role`); `superadmin`/`owner` berperan sebagai override.
- **Dampak**: Untuk operasi normal (user menindak dari inbox mereka), perilaku sudah benar. Namun panggilan API langsung oleh user terautentikasi yang bukan approver level tersebut secara teknis tidak diblok di layer aksi.
- **Rekomendasi**: Tambahkan verifikasi peran di layer aksi (mencocokkan peran user dengan `levels[current_level].role`, selain superadmin/owner). Ditandai untuk pengerasan lanjutan; tidak memengaruhi happy-path yang didokumentasikan.

## Perbaikan yang Dilakukan pada Sesi Ini

- **Testability**: Menambahkan **15 `data-testid`** pada `MultiLevelApprovalModule.jsx` (tabs, filter, refresh, seed, kartu request + aksi approve/reject/note/view/open-module, dan modal detail). Tidak mengubah perilaku fungsional; hanya menambah selector stabil untuk E2E.

## Cleanup / State DB

- `tests/...` menghapus seluruh `approval_requests` fixture (ref_code prefix `E2E-APPROVAL`) + chain `type=e2e_test`.
- **Chain default** hasil seed idempoten (`seed-missing-chains`) **dipertahankan** sebagai baseline aplikasi (UI memerlukan chain agar berfungsi). Ini analog dengan data seed produksi lain dan bukan fixture E2E.
- Verifikasi pasca-run: `approval_requests` total = 0; `approval_chains` total = 11 (tanpa `e2e_test`).
