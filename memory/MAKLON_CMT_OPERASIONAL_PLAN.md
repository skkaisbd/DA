# MAKLON CMT OPERASIONAL PLAN (2026-07-21)
## Menutup gap Excel "Sistem DewiAditya" vs Portal Maklon — TANPA duplikat / percabangan / konflik SSOT

> Prinsip wajib (dari user): **tidak boleh ada duplikat/percabangan data, tidak boleh SSOT tidak jelas,
> tidak boleh false-logic, tetap user-friendly.**
> Strategi: **99% fitur = (a) tambah FIELD ke koleksi SSOT yang sudah ada, atau (b) endpoint READ-ONLY
> agregasi di atas SSOT. TIDAK membuat koleksi "kebenaran" baru** (kecuali `dewi_cmt_permak` yang sudah ada).

---

## BAGIAN A — PETA SSOT SEBENARNYA (hasil audit kode terkini)

### A.1 Rantai SSOT MAKLON (kontrak keras — acuan semua fitur baru)
```
production_pos / po_items / po_accessories        (owner: production_pos.py)          ← PO buyer (business_type='maklon')
   → vendor_shipments / vendor_shipment_items      (owner: vendor_shipment.py)         ← DA kirim POTONGAN+aksesoris ke CMT
        + accessory_shipment_items
        + vendor_material_inspections(_items)        (owner: vendor_shipment.py)         ← inspeksi terima di CMT
   → material_requests                              (owner: vendor_shipment.py/exceptions.py) ← KOMPONEN KURANG (kain)
   → production_jobs / production_job_items          (owner: vendor_shipment.py + production_execution.py) ← job produksi (produced_qty)
        + production_progress                        (owner: production_execution.py)    ← ledger progress harian
   → cmt_receipts / cmt_receipt_lines                (owner: dewi_cmt_packing.py)        ← SETORAN CMT→DA + QC (qty_actual/reject_qty)  [SATU-SATUNYA titik QC FG]
   → dewi_cmt_permak                                 (owner: dewi_cmt_permak.py)         ← PERMAK (sudah dibuat M1 dasar; rework kurangi FG)
   → buyer_shipments / buyer_shipment_items          (owner: buyer_shipment.py)          ← DA kirim balik ke buyer/mitra
komponen kurang (aksesoris): dewi_cmt_component_requests (owner: dewi_cmt_component_requests.py) ← SSOT tunggal, bersih
finance mirror (READ-ONLY dari sisi kita): dewi_maklon_pos + dewi_maklon_finance (owner: production_maklon_bridge.py)
```

### A.2 Koleksi PARALEL / MATI (sumber split-brain) — hasil audit writer
| Konsep | LIVE SSOT | Paralel/mati | Status | Keputusan |
|---|---|---|---|---|
| Master CMT partner | `vendor_partners` (vendor_portal.py, nav `vendor-admin`) | `dewi_cmt_partners` (hanya `_archive/*` + `dewi_demo_seed`) | **MATI (arsip)** | SSOT=`vendor_partners`. Stop tulis `dewi_cmt_partners` (bersihkan demo seed). |
| Job & progress | `production_jobs`/`production_job_items`/`production_progress` (PO-linked) | `vendor_jobs`/`vendor_progress_reports` (vendor_portal.py, portal eksternal, **standalone, TIDAK PO-linked**); `dewi_cmt_jobs`/`dewi_cmt_progress` (`_archive` = mati) | `vendor_jobs`=**LIVE tapi terpisah** | SSOT progress PO=`production_jobs`. `vendor_jobs`=portal eksternal (bukan sumber KPI PO). Lihat B.2. |
| Kirim material DA→CMT | `vendor_shipments` (nav maklon `prod-shipments-vendor`) | `wh_cmt_dispatches` (wms_cmt_dispatches.py, nav **PRODUKSI** `wms-cmt-dispatches`; satuan meter, wo-keyed) | keduanya LIVE, **beda portal** | SSOT MAKLON=`vendor_shipments`+`cmt_receipts`. `wh_cmt_dispatches`=domain WMS/Produksi-internal. Lihat B.3. |

### A.3 Kontradiksi dokumen yang HARUS ditegaskan
- `GUIDELINE_CMT_FLOW.md §4.2`: **"SSOT DA→CMT = `vendor_shipments`"**.
- `server.py` komentar O1.1/O1.2 (+redirect `cmt-progress`/`do-management`/`prod-cmt-packing` → `wms-cmt-dispatches`): **"SSOT dispatch = `wh_cmt_dispatches`"**.
- FAKTA relasi: `cmt_receipt_lines.job_item_id → production_job_items` dan `.po_item_id → po_items`.
  Artinya rantai FG maklon **nyambung ke `production_jobs`/`vendor_shipments`, BUKAN ke `wh_cmt_dispatches`**.
  → **Keputusan (rekomendasi): untuk PORTAL MAKLON, SSOT rantai = `vendor_shipments`→`production_jobs`→`cmt_receipts`.**
  `wh_cmt_dispatches` diperlakukan sebagai jalur WMS/Produksi-internal (di luar KPI operasional maklon),
  dikonsolidasikan belakangan (Fase 5, prioritas rendah).

---

## BAGIAN B — RESOLUSI 3 RISIKO SPLIT-BRAIN (fondasi, Fase 0)

**B.1 Master CMT** → Tegaskan `vendor_partners` = SSOT. Aksi: (1) hentikan seed `dewi_cmt_partners` untuk konteks maklon;
(2) tandai `dewi_cmt_partners`/`dewi_cmt_jobs`/`dewi_cmt_progress` sebagai DEPRECATED di INVARIANTS.md.

**B.2 vendor_jobs vs production_jobs** (paling krusial):
- MASALAH: portal CMT eksternal (`/vendor-cmt`, role `cmt_vendor`) memakai `vendor_jobs` (dibuat manual admin, progress vendor masuk `vendor_progress_reports`). Ini **tidak** mengalir ke `production_jobs`/`po_items` → progress PO tak tahu laporan vendor.
- REKOMENDASI (opsi B2-A, default): **Semua KPI operasional maklon (progress, kejar, dashboard) baca HANYA rantai SSOT (`production_jobs`+`cmt_receipts`).** `vendor_jobs` tetap sebagai self-service vendor (informasi), TIDAK dijadikan sumber angka PO. Hindari double-count.
- OPSIONAL lanjutan (opsi B2-B, bila diinginkan nanti): buat **bridge SATU ARAH** `vendor_progress_reports → production_progress` (map by `wo_id`/`po_item`), read-only, idempotent, sehingga laporan vendor memperkaya progress PO. Tidak wajib untuk fase awal.

**B.3 vendor_shipments vs wh_cmt_dispatches** → Portal Maklon pakai `vendor_shipments`+`cmt_receipts`.
Tidak menyentuh `wh_cmt_dispatches` di fitur maklon. Konsolidasi penuh = Fase 5 (rendah).

> Fase 0 = dokumentasi keputusan + guard (bukan migrasi data besar). Nol risiko ke data live.

---

## BAGIAN C — PEMETAAN GAP → PERLUASAN SSOT (desain anti-duplikat)

| Gap | Cara implement (NO new truth) | Koleksi/endpoint |
|---|---|---|
| **M1 PERMAK** (sudah dasar) | **EXTEND** `dewi_cmt_permak`: `permak_type`('permak_sendiri'\|'retur_ke_cmt'), `problem_type`, `cost_per_pcs`, `total_cost`(computed), `return_deadline`, `h3_flag`(computed) | koleksi ada; tambah field + UI |
| **S4 Retur ke penjahit** | = `dewi_cmt_permak` dengan `permak_type='retur_ke_cmt'` (bukan koleksi baru) | subset M1 |
| **S2 QC % lolos per setoran** | **READ-ONLY**: `pass_rate = Σqty_actual/Σqty_shipped_by_cmt` per `cmt_receipts`. Tambah field turunan di response + endpoint ringkас | `cmt_receipts` (SSOT QC per K5) |
| **S3 KEJAR CMT** (aging/buffer/H+5) | **READ-ONLY service** `services/cmt_kejar.py` agregasi `production_jobs`+`vendor_shipments`+`cmt_receipts`: umur hari, outstanding(dispatched−returned), bucket (on-track/mendekati/TELAT) vs `target_cmt_date` | endpoint baru, 0 koleksi baru |
| **S1 POTONGAN MASUK** (batch-SKU+seri+cek-seri) | **EXTEND** `vendor_shipments`/`vendor_shipment_items` (sudah ada po_item/sku/size/color/serial/qty_sent/shipment_type). Tambah **endpoint "cek seri"** (deteksi serial dobel) + tampilan batch | `vendor_shipments` |
| **S5 REKAP AKSESORIS** | **READ-ONLY**: agregasi `po_accessories` + `dewi_maklon_bom_templates.qty_per_pcs × po_items.qty`, group harian/bulanan/PO | endpoint baru |
| **M2 DASHBOARD OWNER CMT** | **READ-ONLY** gabungan semua SSOT (potongan masuk, disetor, sisa di CMT, TELAT, ongkos jahit terhitung, komponen kurang belum diterima, biaya permak) | endpoint agregasi |
| **M3 KAPASITAS CMT** | **EXTEND** `vendor_partners`: `capacity_pcs`, `capacity_note`. Load vs kapasitas = read-only compute | `vendor_partners` |
| **M4 DUAL-DEADLINE / buffer** | Sudah ada `production_pos.delivery_deadline`(=Deadline Mitra) & `deadline`(=internal). Tambah `buffer_days` + computed `target_cmt_date = delivery_deadline − buffer_days`. Formalkan makna | `production_pos`/`production_jobs` (field ada + 1 field) |
| **M5 "KALI SETOR" / sisa berjalan** | **READ-ONLY**: kali_setor = count `cmt_receipts`(Approved) per PO/job; sisa = dispatched−returned | masuk service kejar/progress |

**Kesimpulan desain:** koleksi kebenaran BARU = **0**. Semua = tambah field additive + service read-only.
→ memenuhi: tanpa duplikat, tanpa percabangan, tanpa konflik SSOT, tanpa false-logic (angka selalu dihitung dari 1 sumber).

---

## BAGIAN D — RENCANA EKSEKUSI BERTAHAP (tested per fase)

### FASE 0 — Fondasi SSOT (dok + guard, low-risk) [WAJIB pertama]
- Tulis keputusan B.1/B.2/B.3 ke `INVARIANTS.md` (+deprecate note `dewi_cmt_*`).
- Bersihkan `dewi_demo_seed` agar tidak menulis `dewi_cmt_partners`/`dewi_cmt_jobs` (cegah confusion).
- Tambah `target_cmt_date`/`buffer_days` semantik (M4 fondasi) — field + default.
- ✅ Test: pastikan flow lama (vendor-admin, tracking, client portal) tetap jalan.

### FASE 1 — [PRIORITAS TINGGI-1] Kualitas harian: M1 lengkap + S4 + S2
- Backend: extend `dewi_cmt_permak` (permak_type/problem_type/cost/return_deadline/h3) + endpoint QC pass-rate per receipt.
- Frontend: lengkapi `CMTPermakModule` (tipe retur-vs-sendiri, ongkos, deadline+H+3 badge); tampil % lolos di `da-cmt-receive`.
- ✅ testing_agent (permak enrich + invariant + pass-rate).

### FASE 2 — [PRIORITAS TINGGI-2] Kontrol telat: S3 KEJAR + M4 + M2 Dashboard Owner + M5
- Backend: `services/cmt_kejar.py` (aging/bucket/kali-setor) + endpoint; endpoint Dashboard Owner.
- Frontend: modul/tab "Kejar CMT" (tabel aging + filter TELAT/mendekati) + "Dashboard Owner CMT" (KPI). Badge dual-deadline.
- ✅ testing_agent (aging math, bucket, dashboard KPI vs SSOT).

### FASE 3 — [MENENGAH] Intake benar: S1 POTONGAN MASUK + cek-seri (+ M5 detail) ✅ SELESAI
- Backend: `services/cmt_intake.py` + `routes/cmt_intake.py` (prefix `/api/dewi/cmt-intake`):
  - `GET /cek-seri` deteksi serial DOBEL antar `po_items` (normalisasi case/spasi) — READ-ONLY.
  - `GET /serial-lookup` cek 1 seri (dipakai peringatan live saat BUAT ORDER, non-block).
  - `GET /batches` view per-batch POTONGAN MASUK atas `vendor_shipments`.
  - **KONFIRMASI USER**: seri = `po_items.serial_number` yang SUDAH ADA (input saat buat order & mewaris ke shipment). TIDAK ada field seri baru. 100% read-only.
- Frontend: tab "Potongan Masuk" + "Cek Seri" di `CMTMonitorModule`; peringatan live seri dobel di `ProductionPOModule` (item form).
- ✅ testing_agent 21/21 (iteration_142).

### FASE 4 — [MENENGAH] Belanja: S5 REKAP AKSESORIS + M3 KAPASITAS ✅ SELESAI
- Backend: `services/cmt_belanja.py` + `routes/cmt_belanja.py` (prefix `/api/dewi/cmt-belanja`):
  - `GET /rekap-aksesoris` = `po_accessories` + turunan BOM (`qty_per_pcs × po_items.qty`), breakdown per aksesoris/PO/bulan + material non-aksesoris. READ-ONLY.
  - `GET /kapasitas` = beban (outstanding di CMT via `services.cmt_kejar`) vs `vendor_partners.capacity_pcs`.
  - Field additif `capacity_pcs`/`capacity_note` di `vendor_partners` lewat owner-nya (`vendor_portal.py` PartnerIn/create/update, non-destruktif).
  - FIX: `cascade_delete_po` kini ikut hapus `po_accessories` (idempotency seed).
- Frontend: tab "Rekap Aksesoris" + "Kapasitas CMT" di `CMTMonitorModule`; input Kapasitas di `VendorAccountsAdminModule` (vendor-admin).
- ✅ testing_agent 23/23 (iteration_143).

### FASE 5 — [RENDAH] Konsolidasi struktural ✅ SELESAI (pemisahan permanen ditegaskan)
- Backend: `services/cmt_recon.py` + `routes/cmt_recon.py` (`GET /api/dewi/cmt-recon/dispatch`):
  - Rekonsiliasi READ-ONLY dua domain: `vendor_shipments`(maklon/pcs, SSOT KPI) vs `wh_cmt_dispatches`(WMS/meter, bukan KPI).
  - Deteksi tumpang-tindih (split-brain): dispatch WMS yang WO-nya nyambung ke PO maklon → verdict `overlap_detected`; jika bersih → `separated_clean`.
- Frontend: tab "Rekonsiliasi" di `CMTMonitorModule` (verdict + 2 kartu domain + catatan).
- **KEPUTUSAN**: pemisahan PERMANEN ditegaskan (MCS-04). Bridge `vendor_progress_reports → production_progress` (B2-B) **SENGAJA TIDAK dibuat** (opsi B2-A) untuk cegah double-count.
- ✅ testing_agent (iteration_144).

---

## KEPUTUSAN YANG MENUNGGU KONFIRMASI USER
1. Prioritas urutan fase (default: 1→2→3→4, lalu 5). — user pilih (mis. "1e" = semua berurutan).
2. SSOT vendor_jobs: **opsi B2-A (default, KPI baca SSOT saja)** atau B2-B (tambah bridge). 
3. Tafsir alur seller→DA→CMT→seller: dikonfirmasi benar (cocok dgn rantai SSOT).
4. Label field: hybrid — **judul UI pakai istilah Excel** (POTONGAN MASUK, SETORAN, KEJAR, PERMAK, PUSEAN),
   **field DB pakai istilah sistem** (agar konsisten kode). 

Status: **Fase 0–5 SELESAI & lolos testing_agent.** Semua = agregasi read-only + field additif; koleksi kebenaran baru = 0. Endpoint baru: `/api/dewi/cmt-intake/*`, `/api/dewi/cmt-belanja/*`, `/api/dewi/cmt-recon/dispatch`. UI: `CMTMonitorModule` (7 tab) + peringatan seri dobel di `ProductionPOModule` + kapasitas di `VendorAccountsAdminModule`.
