# WS A–H — EXECUTION PLAN (code-grounded, verified against /app)

> Basis: user's MASTER DEV PLAN (konsolidasi + verifikasi ulang plan.md Repo B `assnasnsd/da`).
> Aturan sesi ini (dari user): **verifikasi kode dulu (file:line) sebelum klaim**, jangan action-bias,
> **JANGAN bilang "aman/selesai" sebelum menelusuri konsumen kode**. Item yang butuh **keputusan bisnis
> user → SKIP dulu**; kerjakan yang tidak butuh keputusan. Frontend berubah → `bash /app/scripts/rebuild_frontend.sh`.

---

## A. PAPAN VERIFIKASI (sesi ini, dibuka & dibaca langsung di kode /app)

| ID | Klaim | Verdict | Bukti kode (file:line) | Koreksi vs dokumen |
|----|-------|---------|------------------------|--------------------|
| **P0/H-C2** | `ProductionProgressModule` ("Input Progress") pakai model legacy `work_orders`, menu LIVE, koleksi kosong | ✅ CODE-VERIFIED (runtime penuh butuh demo data) | FE `engine/ProductionProgressModule.jsx:18,27,45,66,77` (`apiGet('/work-orders')`, `work_order_id`). Menu LIVE: `portalNav.js:162` `prod-progress` + `moduleRegistry.js:616` (14+ menu `prod-exec-*` redirect ke sini). Penulis `work_orders` HANYA `production_execution.py:629` (POST /work-orders) — **tidak ada FE yang memanggilnya**. Engine hidup pakai `production_jobs`. Runtime: `GET /api/work-orders`→200 `[]` | **Repo B H2 SALAH** ("orphan, no frontend points to /api/work-orders"). Faktanya menu LIVE & jadi kanonik. MASTER PLAN (C2) benar. |
| **B3** | RnD dashboard hitung status `'review'` yang tak pernah ditulis → widget basi 0 | ✅ VERIFIED | Backend `dewi_rnd_design.py:20` count `{'status':'review'}`. Status yang DITULIS di `dewi_rnd_styles.py`: `draft(76,291)`, `pending_owner_review(159)`, `approved_for_launch(197)`, `active(243)`, `promoted(260)` → `'review'` NIHIL. FE `RnDPortalDashboard.jsx:160` tampilkan `kpi.review_styles` | — |
| **G1** | Promote RnD→Master tak bawa foto | ✅ VERIFIED | `dewi_rnd_styles.py:234-248` `model_doc` tanpa `image_paths`; style punya `design_images` (`:83`); `rahaza_models` pakai `image_paths` (`rahaza_production.py:156,185,195,210-223`) | — |
| A5 | Split-brain `rahaza_material_stock` (`qty` vs `quantity`) + band-aid | 🟡 BELUM re-verifikasi sesi ini (di-skip, butuh GO + backup) | (dokumen mengutip `wms_receiving.py:433`, `dewi_cmt_packing.py:278-314`, `unified_inventory.py:119,199,214-227`) | verifikasi ulang saat GO |
| G4 | COA double-seed → 11 duplikat | 🟡 BELUM re-verifikasi sesi ini (di-skip, sentuh Finance) | (dokumen mengutip `rahaza_coa.py:50,346,579,592-623`) | verifikasi ulang saat GO |
| G6 | `post_wip_to_fg_on_wo_complete` orphan | 🟡 coupled ke keputusan WO (skip) | (dokumen: `rahaza_posting.py:900`, caller hanya `_archive/...`) | verifikasi saat GO |

---

## B. FASE EKSEKUSI (dependency-aware)

### ✅ WAVE 1 — SAFE / DECISION-FREE (dieksekusi sesi ini)
1. **Fix B3** — RnD dashboard hitung status nyata (backend `dewi_rnd_design.py` + FE `RnDPortalDashboard.jsx`). Risiko: rendah (isolated, read-only stats).
2. **Fix G1** — map `design_images[] → rahaza_models.image_paths[]` saat promote (`dewi_rnd_styles.py`). Risiko: rendah (aditif, tanpa schema change).

### ⏸️ WAVE 2 — SKIP dulu (butuh keputusan user / risiko tinggi / butuh demo data)
- **P0 / H-C2** — migrasi `ProductionProgressModule` `work_orders` → job-item model. *Bukan keputusan bisnis*, tapi: (a) rewrite modul produksi LIVE, (b) **butuh demo data `production_jobs` untuk uji end-to-end** (DB sekarang kosong per pilihan user "no demo seed"). → tunggu GO + izin seed data uji.
- **A5** split-brain `rahaza_material_stock` — risiko sedang-tinggi (banyak reader), **WAJIB backup + testing_agent**. Tunggu GO.
- **G4** merge COA duplikat — sentuh Finance/journal. Tunggu GO.
- **G6 + H-C1/C2 cleanup** — arsip posting WO orphan + redirect `prod-orders` + buang residu `work_orders`. Coupled ke keputusan WO. Tunggu GO.
- **WS-C (AI wrapper + Claude)** — butuh keputusan **key/model** (Emergent Universal vs ANTHROPIC langsung; ID model). Tunggu keputusan.
- **WS-B (ReportsHub + Executive AI + gear admin)** — fitur baru; Executive AI gated ke keputusan key.
- **WS-D (Smart Import redesign)** — kualitas tergantung structured-output model (WS-C).
- **WS-E / A3 / A6 (wiring outbound scan-out)** — overlap A5.
- **H-C3 (Maklon PO)** & **H-C4 (Dispatch)** — **keputusan bisnis** (opsi 1/2/3 & A/C). Tunggu.
- **WS-F build memory** — informational (P3).

---

## C. DECISION GATES (menunggu jawaban user; item ini TIDAK dikerjakan sampai dijawab)
- [ ] **GO-P0**: izin migrasi `ProductionProgressModule` ke job-item + izin seed data uji produksi minimal untuk verifikasi?
- [ ] **GO-A5**: izin kanonisasi skema `rahaza_material_stock` (dual-write→migrasi reader→hapus fallback) + backup?
- [ ] **GO-G4**: izin merge COA duplikat (canonical + migrasi JE + soft-deprecate)?
- [ ] **AI key/model**: Emergent Universal Key (Claude via wrapper) atau ANTHROPIC_API_KEY langsung? ID model final?
- [ ] **H-C3** Maklon PO: opsi 1 (konsolidasi) / 2 (read-only, rekomendasi) / 3?
- [ ] **H-C4** Dispatch: opsi A (SSOT engine) / C (quick-win, rekomendasi) / B?

---

## D. LOG EKSEKUSI
### WAVE 1 — SELESAI & TERUJI (9/9 E2E, real API+DB, data uji dibersihkan)
- **Fix B3** (`dewi_rnd_design.py`): `review_styles` kini hitung `status='pending_owner_review'`; tambah `approved_styles` (`approved_for_launch`) & `promoted_styles`.
  - ⚠️ **Koreksi saat uji (disiplin verifikasi):** promote **TIDAK** menulis `status='promoted'` ke DB (itu hanya nilai di response JSON `dewi_rnd_styles.py:260`). Sinyal promoted yang benar = field **`promoted_to_model_id != None`**. Metrik diperbaiki → kalau tidak, widget `promoted` akan **selalu 0** (mengulang bug kelas yang sama dgn `'review'`).
  - FE `RnDPortalDashboard.jsx:160`: label "Style Review" → **"Menunggu Review"** (butuh rebuild static).
- **Fix G1** (`dewi_rnd_styles.py` promote): `model_doc['image_paths'] = list(style.design_images or [])` → foto RnD ikut ke Master Data.
- Uji: `tests/verify_b3_g1.py` → **9/9 PASS** (dashboard keys, pending count, approved count, promoted-via-promoted_to_model_id, image_paths mapping). Data uji (style+model) dihapus otomatis → DB tetap bersih.
- Sisa: rebuild frontend static untuk label B3 (sedang berjalan).

### WAVE 2 — P0 (WS-H C2) SELESAI & TERVALIDASI (UI + API live)
- **Rewrite** `frontend/src/components/erp/engine/ProductionProgressModule.jsx`: dari model legacy `work_orders` (GET /work-orders — koleksi tak pernah diisi flow hidup) → model job-item hidup, meniru `VendorProgress.jsx` tetapi **di-scope internal** (`GET /production-jobs?business_type=internal` → `/production-job-items?job_id=` → `POST /production-progress {job_item_id}`).
- Dibuang fitur mati modul lama: riwayat progres via GET `/production-progress?work_order_id=` (tak relevan job-item) + edit/hapus progres via **PUT/DELETE /production-progress/{id}** yang **TIDAK ADA di backend** (verified: hanya GET+POST). Menghindari tombol 404.
- Bukti target model diverifikasi: backend `production_execution.py` POST `/production-progress` punya jalur `job_item_id` (defect cap I-1, gate material-issue internal GDG-2, opsi operator/proses payroll HR-1, auto-complete + posting WIP→FG AD-3). GET `/production-jobs` untuk user internal TIDAK di-scope vendor (lihat vendor auto-scope di `is_vendor`).
- **Validasi (real data via seed engine asli `tests/seed_demo_produksi_maklon.py`):** Portal Produksi → Input Progress kini menampilkan JOB-PO-INT-DEMO-2 (In Progress 60%), item DA-TS01-L (Tersedia 200/Diproduksi 120/Sisa 80). POST progress +20 → `produced_qty` 120→140 (HTTP 201, gate GDG-2 lolos). Screenshot live OK, tanpa red screen.
- ⚠️ **Catatan koreksi vs Repo B:** klaim Repo B H2 ("/api/work-orders orphan, tak ada FE") **SALAH** — `prod-progress` menu LIVE (14+ menu redirect ke sini). MASTER PLAN (C2) benar.
- ⚠️ **DB tidak lagi kosong:** demo data produksi+maklon di-seed untuk uji P0 (perlu `production_jobs` internal). Bisa dibersihkan kapan saja (seed idempoten; hapus po-*-demo-*). Sisa referensi `/work-orders` di bundle = tombol "Generate WO" `RahazaOrdersModule.jsx` (item H-C1, terpisah, butuh keputusan).

### WAVE 2 — P0: testing_agent + follow-up (SELESAI)
- testing_agent (iteration_101): P0 **VERIFIED** (tabel tak kosong, save 201), B3 **VERIFIED** ("Menunggu Review" render), regresi Vendor Portal **PASSED**, backend 9/9. G1 di-skip agent (tak ada style di seed) — sudah kubuktikan 9/9 di `verify_b3_g1.py`.
- 1 catatan LOW ("modal tak buka klik pertama") → **root cause = selektor test ambigu** (ada 3 teks "Input Progress": menu sidebar, recents, tombol baris). **BUKAN bug modal**. Ditambah `data-testid` (`prod-progress-job-select`, `open-progress-btn`, `progress-qty-input`, `save-progress-btn`) → modal terkonfirmasi terbuka penuh + form render (screenshot live). Save juga terbukti (produced_qty naik).

## E. STATUS SAAT INI (checkpoint untuk user)
Selesai & teruji live: **B3, G1, P0**. Semua item non-keputusan yang aman sudah dieksekusi.
Sisa backlog **butuh keputusan / high-risk (WAJIB GO + backup)** — lihat bagian C. Menunggu arahan user.
