# QA / Bug Register — Flow QC / Rework (`flow-produksi-qc-rework`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN — happy-path (output → qc pass/fail → papan rework out/fail → packing) terverifikasi via `tests/flow_produksi_qc_rework_test.py`.
- **Guardrail terverifikasi:**
  - `quick-output` pada proses QC ditolak (400) → QC wajib via `qc-event`.
  - `qc-event` tanpa `qty_pass`/`qty_fail` (>0) ditolak (400).
  - `rework-event` dengan `qty_out + qty_fail > qty_in` ditolak (400).
- **DB pristine:** skrip melakukan hard-cleanup `rahaza_wip_events` (fixture line) + fixture line.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| QCR-01 | LOW | `flow-summary` menghitung `rework = out("REWORK")` dengan `event_type="output"`, sedangkan event rework bertipe `rework_pass`/`rework_fail`. Akibatnya throughput REWORK pada summary = 0 dan `wip_rework` = `qc_fail` (belum dikurangi yang sudah diproses). Tidak memblok alur inti; qc_pass/qc_fail & throughput PACKING tetap akurat. | NOTED |
| QCR-02 | LOW | `ProcessExecutionModule.jsx`: tombol **Refresh** board dan tombol **Batal** modal belum memiliki `data-testid`. Ditambahkan `board-refresh-btn` & `quick-cancel-btn` untuk testabilitas E2E. | FIXED |
| QCR-03 | INFO | Auditor statis `audit_testids.py --file ... --strict` menandai beberapa elemen interaktif (parser terpotong oleh arrow `=>` di `onClick`) padahal `data-testid` sudah ada (mis. `quick-input-*`, `wo-select`, `qty-chip-*`). False-positive parser; audit gate `--module-id prod-exec-hub` LULUS 0 FAIL. | NOTED |
| QCR-04 | INFO | `rework-event` meng-auto-create proses `REWORK` bila belum ada di master data (order_seq 99, is_rework=true). By design. | NOTED |
| QCR-05 | INFO | `quick-output`/`qc-event`/`rework-event` menerima input **tanpa assignment** (model/size/WO = null). By design untuk fleksibilitas lantai. | NOTED |

## Bukti Uji
- `python3 tests/flow_produksi_qc_rework_test.py` → **QC/REWORK FLOW ALL PASS**
  (output→qc pass=80/fail=20→rework in=20/out=15/fail=5→packing=95; flow-summary qc_pass=80 qc_fail=20 packing=95; 3 guardrail 400; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-produksi-qc-rework` → **LULUS 10/10**.
- `python3 scripts/docgen/audit_testids.py --module-id prod-exec-hub` → **LULUS (0 FAIL)**.
- **E2E UI (Playwright, prod-exec-hub):** login → Portal Produksi → Eksekusi Proses → tab QC submit 80/20 → tab Rework submit 20/15/5 → tab Packing submit 95. Semua sukses; board memperbarui breakdown (Pass/Fail, Lolos/Scrap, Output) dan tabel Event Terbaru. **Tidak ada logout** saat perpindahan tab.

## Catatan E2E (agent-to-agent)
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| QCR-06 | INFO | Iterasi testing agent (it_83) melaporkan "session redirect ke login" saat pindah tab setelah submit QC. Diverifikasi ulang manual via Playwright: perpindahan tab HubTabs murni state internal (`data-testid=hub-tab-*`, tanpa reload), token di localStorage TTL 24 jam. Alur QC→Rework→Packing terbukti mulus tanpa logout. Laporan tersebut adalah **false-alarm** akibat navigasi via reload/URL yang mendarat di halaman "Pilih Portal" (bukan login). | NOT-A-BUG |
