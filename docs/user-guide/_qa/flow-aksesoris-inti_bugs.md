# QA / Bug Register — Flow Aksesoris Inti (`flow-aksesoris-inti`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN untuk happy-path — PR→Stok→Request Internal→Opname terverifikasi via `tests/flow_aksesoris_inti_test.py`.
- **Posting terverifikasi:**
  - PR `Received` → `rahaza_material_stock` (ZNA-AKSESORIS) += 50 + movement `receive`.
  - Receive +20 → 70; Issue −10 → 60 (guard stok ≥ 0).
  - Opname count 57 (system 60, selisih −3) → `complete` posting adjustment → stok 57 + movement `adjust` (reference_type `opname`).
- **Guardrail terverifikasi (4):**
  - Issue melebihi stok ditolak (400).
  - Allocate request non-`submitted` ditolak (400).
  - Start opname kedua saat masih ada sesi aktif ditolak (400).
  - Count pada sesi opname `Completed` ditolak (400).
- **DB pristine:** hard-cleanup master + PR + request + sesi opname + stok + movement.

## Temuan / Observasi
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| AKS-01 | LOW | `GET /api/acc/stock/movements` memfilter `{domain:'accessory'}` (`routes/dewi_accessories_stock.py`), sedangkan helper `_log_movement` menulis dokumen `rahaza_material_movements` **tanpa** field `domain`. Akibatnya list movement via API mengembalikan kosong walau audit tercatat di DB. Endpoint tetap `200` (tidak crash). Verifikasi audit pada POC dilakukan langsung ke koleksi (`reference_type='opname'`). Rekomendasi: set `domain:'accessory'` saat insert di `_log_movement`, atau longgarkan filter query. | NOTED (tidak memblokir happy-path) |
| AKS-02 | INFO | Request internal via tab `AccessoryModule` memakai endpoint legacy `/api/acc/internal-requests`, sementara SSOT kanonik + Inbox Approval memakai `/api/dewi/accessory-requests` (`request_type='internal_issuance'`). Dokumen alur mengajarkan jalur SSOT. Migrasi: `backend/migrations/migrate_acc_requests_consolidation.py`. | NOTED |
| AKS-03 | INFO | Request internal SSOT (`allocate`/`deliver`) **tidak** mengurangi stok (workflow-only); pengurangan fisik dilakukan lewat `issue` stok. Ini by design pada versi saat ini (hook allocate→issue direncanakan terpisah). | NOTED |
| AKS-04 | INFO | `start` opname men-snapshot SELURUH aksesoris aktif (`type='accessory'`), bukan per-rak. Untuk gudang aksesoris besar, snapshot bisa banyak baris; count bersifat per item. By design. | NOTED |
| AKS-05 | INFO | POC mengisolasi data via master fixture berkode unik `E2E-ACC-XXXXXX`; pre-clean membatalkan sesi opname aksesoris `open` lama agar guard sesi-aktif tidak salah blokir. Tidak menyentuh data nyata bermakna. | NOTED |

## Bukti Uji
- `python3 tests/flow_aksesoris_inti_test.py` → **ALUR AKSESORIS INTI ALL PASS**
  (20 assertion PASS: item→PR(Draft→Received +50)→receive 70→issue 60→guard 400→request internal draft→delivered→opname start→count 57→complete stok 57→guard 400; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-aksesoris-inti` → **LULUS 10/10**.
- Grounding endpoint diverifikasi memakai `scripts/docgen/validate_flow.py` (F3: seluruh `/api` ter-*grounded* ke `all_backend_paths`).

## Catatan (agent-to-agent)
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| AKS-06 | INFO | Lingkungan continuation: `backend/.env` sebelumnya tidak memuat `JWT_SECRET` sehingga backend gagal start (`RuntimeError`). Ditambahkan `JWT_SECRET` + `pip install -r requirements.txt` (openpyxl dll). Kredensial uji: `admin@garment.com` / `Admin@123` (lihat `memory/test_credentials.md`). | RESOLVED |
