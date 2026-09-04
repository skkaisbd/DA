# QA — Alur Produksi Inti (`flow-produksi-inti`)

> Catatan QA untuk dokumen berbasis alur. Materi training di
> `produksi/flow-produksi-inti.md` **wajib bebas bug**; temuan dicatat di sini + di
> `BUG_REGISTER.md`.

## Ringkasan
- **Dokumen:** [`produksi/flow-produksi-inti.md`](../produksi/flow-produksi-inti.md) — LULUS `validate_flow.py` **10/10**, 885 baris, rubrik 97/100.
- **Skrip uji backend:** `tests/flow_alur_produksi_inti_test.py` — **18/18 PASS** (self-cleanup terverifikasi).
- **Audit test-id statis:** `scripts/docgen/audit_testids.py` — **0 FAIL** (tidak ada duplikat testid lintas-file pada modul alur).
- **Modul tersentuh:** `prod-wizard`, `prod-work-orders`, `prod-simple-input`.

## Temuan
| ID | Severity | Status | Ringkas |
|---|---|---|---|
| — | — | ✅ CLEAN | Tidak ada bug fungsional/testabilitas baru pada alur inti. |

### Observasi (bukan bug)
- **OBS-FLOW-001 (Low, ✅ INFO):** `data-testid="production-wizard-step-preview"` muncul 3× di
  `ProductionWizardModule.jsx` (baris 233/244/252), tetapi ketiganya berada pada cabang
  *early-return* yang **saling eksklusif** (loading / kosong / normal). Hanya satu yang
  ter-render pada satu waktu → selektor tetap unik & stabil. **By-design, bukan bug.**
- **OBS-FLOW-002 (Low, ✅ INFO):** Auditor A4 menandai sejumlah elemen interaktif tanpa
  `data-testid` (mayoritas di `RahazaWorkOrdersModule.jsx`/`DataTableV2.jsx`). Semua **di luar
  jalur kritikal** (kontrol tabel/paginasi generik). Selektor jalur utama sudah lengkap.

## Audit Statis (detail)
- A1 (duplikat lintas-file): **PASS** — 0 duplikat.
- A2 (duplikat dalam-file): **WARN** — 1 (OBS-FLOW-001, by-design).
- A3 (prop-forwarding testid): **PASS**.
- A4 (interaktif tanpa testid): **WARN** — non-blocker, di luar jalur kritikal.
