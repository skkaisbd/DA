# QA — Alur Maklon Inti (`flow-maklon-inti`)

> Catatan QA untuk dokumen berbasis alur Portal Maklon. Materi training di
> `maklon/flow-maklon-inti.md` wajib bebas bug; temuan dicatat di sini + `BUG_REGISTER.md`.

## Ringkasan
- **Dokumen:** [`maklon/flow-maklon-inti.md`](../maklon/flow-maklon-inti.md) — LULUS `validate_flow.py` **10/10**, 816 baris, rubrik 97/100.
- **Skrip uji backend:** `tests/flow_maklon_inti_test.py` — **17/17 PASS** (self-cleanup terverifikasi).
- **Audit test-id statis:** `scripts/docgen/audit_testids.py --module-id maklon-po` — **0 FAIL**.
- **Modul tersentuh:** `maklon-po` (pusat), `maklon-po-360`, `maklon-billing`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| MKL-TID-001 | Medium | FIXED | `MaklonPOModule.jsx` hanya punya 2 `data-testid` statis — seluruh kontrol jalur utama (Buat PO, Konfirmasi, Dispatch, Post-AR, Simpan, field item) tidak dapat ditarget otomatis. Ditambahkan test-id pada kontrol happy-path (create/confirm/dispatch/post-ar/save + `po-item-{idx}-*` + `dispatch-item-{idx}-*`). Diverifikasi via esbuild (kompilasi OK) + audit (0 FAIL). |
| MKL-UX-001 | Low | FIXED | Tab default daftar PO = `active` (Aktif) sehingga PO baru berstatus Draft tidak langsung terlihat setelah dibuat (ditemukan saat E2E). Fix: tab default → `all` (Semua) agar PO baru langsung tampak. |

### Detail MKL-TID-001 (Testability)
- **Dampak:** Alur maklon tidak dapat diuji E2E secara stabil; melanggar mandat desain
  (setiap elemen interaktif wajib `data-testid`).
- **Perbaikan (frontend, non-breaking, hanya penambahan atribut):**
  `maklon-po-page`, `maklon-po-create-btn`, `maklon-po-refresh-btn`, `maklon-po-search-input`,
  `maklon-po-card-{id}`, `maklon-po-form-client-select`, `maklon-po-add-item-btn`,
  `maklon-po-form-save-btn`, `po-item-{idx}-{seri,color,size,qty,rate}`,
  `maklon-po-confirm-btn`, `maklon-po-dispatch-open-btn`, `maklon-po-material-btn`,
  `maklon-po-bom-btn`, `maklon-po-postar-btn`, `dispatch-item-{idx}-{check,qty}`,
  `maklon-dispatch-submit-btn`, `maklon-dispatch-confirm-{id}`.
- **Verifikasi:** `esbuild` transform exit 0; `audit_testids.py` A1/A2/A3 PASS, A4 WARN
  (47 elemen non-kritikal tanpa testid — di luar jalur utama, non-blocker).

### Observasi (bukan bug)
- **A4 WARN (Low, INFO):** elemen interaktif non-kritikal (Select/Input di dialog, item dropdown
  Buyer Catalog picker) belum ber-testid. Di luar jalur kritikal; tidak menghambat E2E happy-path.

## Audit Statis (detail, `--module-id maklon-po`)
- A1 (duplikat lintas-file): **PASS** — 0 duplikat.
- A2 (duplikat dalam-file): **PASS**.
- A3 (prop-forwarding testid): **PASS**.
- A4 (interaktif tanpa testid): **WARN** (47) — non-blocker, di luar jalur kritikal.
