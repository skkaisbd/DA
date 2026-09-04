# MAKLON REVAMP PLAN (2026-07-21) — IA restructure + Qty-progress multi-state + Permak (M1)

Sumber kebutuhan: user ingin Portal Maklon terstruktur sesuai flow, deprecate menu redundant,
pindahkan setting ke sistem, dan **logika qty-progress benar** (rework/permak mengurangi FG).
Wajib: cek semua integrasi (termasuk portal eksternal) supaya tak ada relasi putus/mismatch.

## AUDIT INTEGRASI (temuan)
- Nav ids yang dipindah/urut ulang: **0 referensi luar** kecuali `vendor-portal` (1 ref di HelpGuide) → aman.
- Portal eksternal **/vendor-cmt** (role `cmt_vendor`) render `erp/engine/VendorPortalApp` — BUKAN modul admin `VendorPortalModule`. → Deprecate `vendor-portal` dari nav admin AMAN.
- Portal eksternal **/klien-maklon** (role `klien_maklon`) konsumsi `GET /api/maklon-client/pos` (progress_pct) + `/api/dewi/client-portal/*`. → Perubahan progress WAJIB backward-compatible (pertahankan `progress_pct`, tambah breakdown).
- Vendor submit progress: `POST /api/vendor-portal/my-jobs/{job_id}/progress`. Return material: `POST /api/wms/cmt-dispatches/{id}/return-line`.
- Sumber qty PARALEL (risiko mismatch): `vendor_jobs`, `production_job_items.produced_qty` (dipakai `production_maklon_bridge` → `dewi_maklon_pos.items[].qty_produced` → progress lama), `cmt_receipt_lines` (qty_actual/reject_qty, punya `po_item_id`), `wh_cmt_dispatches`, `buyer_shipment_items.qty_shipped`.
- Progress lama: `progress_pct = Σqty_produced / Σqty_ordered` (biner). `qty_produced` dari production_job_items, TIDAK mencerminkan cmt_receipts → **mismatch nyata**.
- Config tujuan pindah: Manajemen portal → section `ADMINISTRASI SISTEM` (`mgmt-system-hub`).

## MODEL QTY-PROGRESS BARU (canonical, dihitung dari SSOT)
Per item PO (per seri/SKU):
- `qty_ordered`  = po_items.qty
- `qty_sent_cmt` = Σ wh_cmt_dispatches (SSOT dispatch) untuk po_item
- `qty_returned` = Σ cmt_receipt_lines(approved).qty_shipped_by_cmt (fisik balik)
- `qty_accepted` = Σ cmt_receipt_lines(approved).qty_actual (lolos QC)
- `qty_reject_qc`= Σ cmt_receipt_lines(approved).reject_qty (cacat saat QC)
- `qty_rework_open` = Σ dewi_cmt_permak(open/dikirim) untuk po_item
- `qty_rework_fixed`= Σ permak(selesai_berhasil)
- `qty_scrap`   = Σ permak(gagal→buang) + sisa reject_qc yang tak dipermak
- `qty_dispatched` = Σ buyer_shipment_items.qty_shipped
- **qty_good (Barang Jadi)** = qty_accepted + qty_rework_fixed − qty_rework_open  (rework mengurangi FG)
- **qty_good_ready** = qty_good − qty_dispatched
Invariant: qty_returned = qty_accepted + qty_reject_qc ; rework diambil dari pool cacat/good.
Backward compat: tetap kirim `progress_pct` (= qty_dispatched/qty_ordered *100) + object `breakdown`.

## EKSEKUSI BERTAHAP
### PHASE 1 — IA restructure (frontend nav, low-risk)
1. portalNav.js `maklon`: MASTER DATA (+vendor-admin) · PRODUKSI MAKLON (urut flow + cmt-permak) · MONITORING PROGRESS (dashboard, tracking, prod-work-orders, variance) · KEUANGAN & ANALITIK. Hapus section PENGATURAN + item vendor-portal.
2. Pindah `maklon-config` & `maklon-notifications` ke Manajemen → ADMINISTRASI SISTEM.
3. Fix ref `vendor-portal` di HelpGuide.
4. Registrasi id `cmt-permak` di moduleRegistry (placeholder dulu).
5. Rebuild + smoke nav.

### PHASE 2 — Backend: progress canonical + Permak
6. `services/maklon_progress.py` compute_po_progress() (reconcile SSOT).
7. `routes/dewi_cmt_permak.py` CRUD+status+summary+from-receipt-line; register di server.py.
8. Wire canonical progress ke po_360, maklon_client_tracking (jaga progress_pct), tracking.
9. testing_agent backend (permak + invariant + client portal tetap jalan).

### PHASE 3 — Frontend: Permak UI + progress multi-state
10. CMTPermakModule.jsx (KPI+tabel+dialog+status+from-receipt).
11. Tracking & PO-360: bar breakdown multi-state.
12. Tombol "Kirim ke Permak" di da-cmt-receive line.
13. Rebuild + testing_agent UI.

Status: PHASE 1 ✅ · PHASE 2 ✅ · PHASE 3 ✅ — SELESAI (semua fase diverifikasi E2E).

## PROGRESS LOG (continuation session 2026-07-21)
- Repo di-clone ke /app. env fix: JWT_SECRET + EMERGENT_LLM_KEY. frontend start → craco dev.
- Login admin: admin@garment.com / Admin@123 (lihat test_credentials.md).
- PHASE 1 ✅: portalNav maklon sudah restrukturisasi (MASTER DATA +vendor-admin; PRODUKSI MAKLON urut-flow + cmt-permak; MONITORING PROGRESS; KEUANGAN). maklon-config/notifications → Manajemen ADMINISTRASI SISTEM. HelpGuide ref vendor-portal = dead code (_archive, tak di-import) → no-op. cmt-permak diregistrasi di moduleRegistry (Phase 3).
- PHASE 2 ✅ backend:
  · services/maklon_progress.py — compute_po_progress()/compute_pos_batch() (SSOT reconcile, FG multi-state).
  · routes/dewi_cmt_permak.py — CRUD+status machine (open→in_progress→selesai_berhasil/gagal_buang)+summary+from-receipt-line. Registered server.py.
  · maklon_client_tracking.py — /pos & /pos/{id}/tracking + breakdown (progress_pct/delivery_pct DIJAGA) + endpoint baru /pos/{id}/progress.
  · dewi_maklon_po_360.py — tambah field progress_breakdown.
  · Core test /app/tests/test_core_maklon_progress.py = 36/36 pass. testing_agent backend = 20/20 pass, 0 bug.
- FG formula final: qty_good = qty_accepted + Σ(fixed|source=reject) − Σ(qty|source=good,WIP) − Σ(scrap|source=good). Invariant returned==accepted+reject.
- PHASE 3 (frontend, in progress):
  · engine/ProgressBreakdownBar.jsx (bar multi-state reusable).
  · CMTPermakModule.jsx (KPI+tabel+create dialog+status dialog) + registrasi cmt-permak.
  · DAReceiveFromCMTModule.jsx — tombol "Kirim ke Permak" pada line reject (receipt Approved) + dialog.
  · MaklonPO360Module.jsx + MaklonProductionTracking.jsx — render ProgressBreakdownBar (canonical).
  · Demo data: scripts/seed_maklon_permak_demo.py (PO-MKL-DEMO-001, tag _demo). Clean: --clean.
- CATATAN DEPLOY: frontend package.json "start" diubah ke craco dev (untuk hot-reload). Untuk produksi/preview-stable pakai "start:prod" (node static_server.js) — kembalikan bila perlu.
