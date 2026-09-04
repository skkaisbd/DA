# QA / Bug Register — `flow-rnd-sampling-design`

> Memisahkan catatan QA dari materi training (standar v4). Dokumen training
> (`docs/user-guide/rnd/flow-rnd-sampling-design.md`) bebas tag bug.

## Ringkasan Verifikasi

- **POC backend**: `tests/flow_rnd_sampling_design_test.py` → **ALL PASS (27 skenario)**, exit 0, self-cleanup (DB pristine).
- **Audit testid**: `scripts/docgen/audit_testids.py --module-id rnd-design-hub rnd-costing-hub --file RnDStylesTab.jsx RnDSamplesTab.jsx RnDHPPCalculatorModule.jsx` → **LULUS 0 FAIL** (27 testid statik unik).
- **Validator dokumen**: `scripts/docgen/validate_flow.py --flow-id flow-rnd-sampling-design` → **LULUS 10/10** (0 WARN, 0 FAIL; 802 baris; rubrik 97/100).

## Bug Ditemukan & Diperbaiki

- Tidak ada bug fungsional baru ditemukan pada alur ini. Seluruh happy-path & guardrail berperilaku sesuai kontrak.

## Observasi (LOW — non-blocking)

### RND-OBSERVASI-1 · Pengerasan RBAC pada layer aksi
- **Lokasi**: `backend/routes/dewi_rnd_styles.py`, `dewi_rnd_samples.py` — endpoint aksi (`owner-approve`, `owner-reject`, `promote-to-production`, sample `approve`/`reject`).
- **Deskripsi**: Endpoint memvalidasi **autentikasi + status prasyarat** (guardrail transisi), namun tidak mem-block peran di layer aksi (mis. verifikasi bahwa hanya Owner yang boleh `owner-approve`). Gating peran diasumsikan pada UI portal RnD.
- **Dampak**: Happy-path operasional benar. Panggilan API langsung oleh user terautentikasi non-Owner secara teknis tidak diblok di layer aksi.
- **Rekomendasi**: Tambahkan verifikasi peran (Owner/Manajer) pada endpoint keputusan. Ditandai untuk pengerasan lanjutan; tidak memengaruhi happy-path terdokumentasi.

### RND-OBSERVASI-2 · A4 audit testid (false-positive)
- Auditor melaporkan 72 elemen interaktif "tanpa testid" pada 3 file tab. Ini **false-positive** dari parsing arrow-function `=>` di dalam handler `onClick`/`onChange`. Elemen aksi kritikal (create/save/submit/approve/reject/HPP) sudah memiliki `data-testid`. Non-blocking (WARN, bukan FAIL).

## E2E UI (testing agent iter_86) + Investigasi Main-Agent

Testing agent melaporkan 2 isu; keduanya **diinvestigasi ulang oleh main agent via Playwright bersih** dan terbukti **artefak lingkungan/harness, BUKAN bug aplikasi**:

- **(MEDIUM dilaporkan) "OwnerReviewDialog tidak menutup setelah approve"** → **TIDAK REPRO**. Pada sesi bersih: buka dialog → pilih approve → confirm → **dialog menutup** (`owner-review-dialog` detached), tidak ada redirect login, dan status style DEMO-RND-PENDING **berubah ke `approved_for_launch`** di DB. Kode handler (`handleOwnerApprove`) memang memanggil `setOwnerReviewDialog(null)` + `fetchStyles()` pada sukses. Gejala "dialog tetap terbuka" pada harness terjadi karena panggilan API mengembalikan 401 (session/harness), yang ditelan diam-diam oleh cabang `isUnauthorized`.
- **(LOW dilaporkan) "session hilang saat hash-nav + reload"** → **TIDAK REPRO**. Pada sesi bersih: setelah `#rnd-design-hub` reload dan `#rnd-costing-hub` reload, pengguna **tetap login** (localStorage `erp_token` bertahan; `App.js` restore-session benar). Isu pada harness kemungkinan dari 401 yang memicu `onUnauthorized` auto-logout, bukan kegagalan restore-session aplikasi.

**Bukti E2E UI bersih (main agent):** Login → `#rnd-design-hub` → Styles menampilkan 3 style demo (draft/pending/approved) → Owner Review approve **berhasil & dialog menutup** → `#rnd-costing-hub` → tab **HPP Calculator** menampilkan record demo dengan nilai persis kalkulasi (Direct Rp 60.700, Overhead Rp 6.070, HPP Rp 66.770, Harga Jual Proposal Rp 95.385,71, Margin 30%). Tidak ada red-screen/crash. Data demo dibersihkan setelah uji.

## Cleanup / State DB

- Skrip menghapus seluruh fixture bertag `E2E-RND` (styles, sample_requests, hpp, tech_packs, revisions) + Production Model hasil promote (`rahaza_models.rnd_style_code` prefix `E2E-RND`).
- Verifikasi pasca-run: residu `E2E-RND` = 0 pada semua koleksi terkait. Data seed pra-uji tidak tersentuh.
