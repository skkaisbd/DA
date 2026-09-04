# QA Bug Register — Modul `prod-orders` (Order Produksi)

<!-- Dokumen QA internal. TIDAK ditampilkan sebagai materi training.
     Materi training (bebas-bug) ada di: ../produksi/prod-orders.md
     Standar: 01_DEEP_STANDARD_v3.md — bug WAJIB dipisah dari dokumen training. -->

> **Tujuan file ini:** menyimpan seluruh temuan QA (bug/observasi) untuk modul `prod-orders`
> beserta bukti, perbaikan, dan verifikasi — **terpisah** dari dokumen training agar materi
> pelatihan pengguna tetap bersih (hanya menampilkan perilaku yang benar).
>
> **Modul:** `prod-orders` · **Komponen induk:** `frontend/src/components/erp/RahazaOrdersModule.jsx`
> **Status keseluruhan:** ✅ **SEMUA TEMUAN SELESAI + DIVERIFIKASI** (per 2026-07-07)
> **Kondisi DB setelah uji:** bersih (self-cleanup skrip).

---

## 1. Ringkasan Temuan

| ID | Severity | Judul singkat | Status | Verifikasi |
|----|----------|---------------|--------|------------|
| BUG-003 | **High** | Stage Tracking 404 untuk order Rahaza | ✅ FIXED | UI iter 66 + skrip TC-25/26/27 |
| BUG-001 | Medium | API menerima order tanpa item | ✅ FIXED | skrip TC-03 + UI iter 66 |
| BUG-002 | Medium | Qty non-numerik → HTTP 500 | ✅ FIXED | skrip TC-30/30b |
| OBS-004 | Low | Auto-confirm (Generate WO) tak tercatat audit | ✅ FIXED | UI iter 67 + skrip TC-34 |
| OBS-005 | Low | Tombol tutup drawer Riwayat terhalang overlay | ✅ FIXED | UI iter 68 |
| OBS-007 | Low | `order_date`/`due_date` tidak divalidasi format | ✅ FIXED | skrip TC-31 |
| OBS-008 | Low | Kondisi render status mati `production_complete` | ✅ FIXED | UI iter 67 |
| OBS-006 | Low | Tombol mutasi tampil ke role tanpa izin | ✅ BY-DESIGN (enhancement) | terverifikasi TC-32/33 |

**Total:** 8 temuan (1 High, 2 Medium, 5 Low). 7 di-fix, 1 (OBS-006) diklasifikasikan by-design (backend menolak 403 → aman) dengan catatan enhancement UI gating.

---

## 2. Detail Temuan (Expected vs Actual + Perbaikan + Bukti)

### BUG-003 — Stage Tracking 404 untuk order Rahaza  · Severity: High
- **Repro:** buat order via modul `prod-orders` (tersimpan di koleksi `rahaza_orders`) → transisi ke `in_production` → buka Detail → panel Stage Tracking memanggil `GET /api/production-pos/{id}/stage-summary`.
- **Expected:** panel tampil, `qty_ordered` sesuai item order.
- **Actual (sebelum fix):** HTTP 404 — endpoint hanya membaca koleksi `production_pos`, sedangkan order Rahaza ada di `rahaza_orders`.
- **Perbaikan:** `stage-summary` & `stage-qty` diberi **fallback** ke koleksi `rahaza_orders`; `qty_ordered` diambil dari item order.
- **File:** `backend/routes/production_po.py` (`stage-summary` `:579`, `stage-qty` `:527`).
- **Verifikasi:** UI `testing_agent_v3` iter 66 (Stage panel tampil tanpa 404, input sukses, progress 0→37%) + skrip TC-25/26/27.

### BUG-001 — API menerima order tanpa item  · Severity: Medium
- **Repro:** `POST /api/rahaza/orders {is_internal:true, items:[]}`.
- **Expected:** HTTP 400 dengan pesan minimal 1 item.
- **Actual (sebelum fix):** HTTP 200 (order kosong tersimpan).
- **Perbaikan:** guard `400` di **create & update** bila tidak ada item valid → `"Minimal 1 item pesanan (Model + Size + Qty > 0)."`
- **File:** `backend/routes/rahaza_orders.py` (`POST /orders` `:179`, `PUT /orders/{oid}` `:253`).
- **Verifikasi:** skrip TC-03 + UI iter 66.

### BUG-002 — Qty non-numerik → HTTP 500  · Severity: Medium
- **Repro:** `POST /api/rahaza/orders {items:[{model,size,qty:"abc"}]}`.
- **Expected:** HTTP 400 (bukan 500) — item invalid di-skip; bila semua invalid → 400.
- **Actual (sebelum fix):** HTTP 500 (crash saat cast qty).
- **Perbaikan:** parsing qty dengan `try/except` → item non-numerik di-skip.
- **File:** `backend/routes/rahaza_orders.py` (parsing item pada `POST /orders`).
- **Verifikasi:** skrip TC-30 (semua invalid → 400) & TC-30b (campur → simpan yang valid). Catatan: API-only (tak dapat dipicu dari UI karena input UI bertipe number).

### OBS-004 — Auto-confirm (Generate WO) tak tercatat audit  · Severity: Low
- **Repro:** order draft → `POST /generate-work-orders` → order otomatis `confirmed`, tetapi audit tidak mencatat `status_change`.
- **Expected:** audit `status_change` (auto) tercatat.
- **Perbaikan:** tambah `log_audit(status_change)` di jalur auto-confirm.
- **File:** `backend/routes/rahaza_work_orders.py` (`generate-work-orders` `:605`).
- **Verifikasi:** UI iter 67 + skrip TC-34.

### OBS-005 — Tombol tutup drawer Riwayat terhalang overlay  · Severity: Low
- **Repro:** Detail → Riwayat → klik tombol tutup (`audit-drawer-close`) → klik pertama kadang tidak menutup (overlay Radix menangkap pointer).
- **Expected:** tertutup pada klik pertama; Esc & backdrop juga menutup.
- **Perbaikan:** drawer `z-[70]` + `pointer-events-auto`.
- **File:** `frontend/src/components/erp/AuditHistoryDrawer.jsx`.
- **Verifikasi:** UI iter 68 (regresi iter 67 sudah diselesaikan).

### OBS-007 — `order_date`/`due_date` tidak divalidasi format  · Severity: Low
- **Repro:** `POST /api/rahaza/orders {due_date:"BUKAN-TANGGAL", ...}`.
- **Expected:** HTTP 400 `"due_date harus berformat tanggal YYYY-MM-DD."`
- **Perbaikan:** validasi `date.fromisoformat` di create & update.
- **File:** `backend/routes/rahaza_orders.py`.
- **Verifikasi:** skrip TC-31.

### OBS-008 — Kondisi render status mati `production_complete`  · Severity: Low
- **Repro:** kondisi render panel Stage Tracking mengacu status `production_complete` yang tidak ada di state machine order.
- **Expected:** kondisi render hanya memakai status valid.
- **Perbaikan:** hapus `production_complete` dari kondisi render.
- **File:** `frontend/src/components/erp/RahazaOrdersModule.jsx`.
- **Verifikasi:** UI iter 67.

### OBS-006 — Tombol mutasi tampil ke role tanpa izin  · Severity: Low · **BY-DESIGN**
- **Repro:** login `supervisor_produksi` → tombol Generate WO/Ubah Status tetap tampil; klik → backend `403`.
- **Analisis:** backend **sudah** menolak (403) sehingga **aman secara data**. Frontend belum menyembunyikan tombol.
- **Keputusan:** **by-design** untuk saat ini; dicatat sebagai **enhancement backlog** (UI gating). Bukan defect fungsional.
- **Verifikasi:** TC-32 (403 saat mutasi) & TC-33 (200 saat baca).

---

## 3. Bukti Uji (artefak)
- **Skrip backend:** `/app/tests/pilot_prod_orders_test_v2.py` — **39/39 PASS** (idempoten, self-cleanup).
- **Report UI `testing_agent_v3`:** `/app/test_reports/iteration_66.json`, `_67.json`, `_68.json`.
- **Kredensial uji:** `memory/test_credentials.md` (admin `admin@garment.com` / `Admin@123`).
- **Kondisi DB setelah uji:** bersih (orders=0, models=0, customers=0, sizes=5 seed).

## 4. Changelog Perbaikan (kode)
| Tanggal | Perubahan | File |
|---|---|---|
| 2026-07-07 | BUG-003: stage endpoints dukung order Rahaza (fallback koleksi) | `backend/routes/production_po.py` |
| 2026-07-07 | BUG-001: guard min 1 item (create & update) | `backend/routes/rahaza_orders.py` |
| 2026-07-07 | BUG-002: parsing qty aman (skip non-numerik) | `backend/routes/rahaza_orders.py` |
| 2026-07-07 | OBS-004: audit pada auto-confirm generate WO | `backend/routes/rahaza_work_orders.py` |
| 2026-07-07 | OBS-005: z-index + pointer-events drawer Riwayat | `frontend/src/components/erp/AuditHistoryDrawer.jsx` |
| 2026-07-07 | OBS-007: validasi format tanggal | `backend/routes/rahaza_orders.py` |
| 2026-07-07 | OBS-008: hapus status mati `production_complete` | `frontend/src/components/erp/RahazaOrdersModule.jsx` |

## 5. Residual / Catatan
- Isi Export CSV diverifikasi "berisi data order" (belum divalidasi per kolom baris-per-baris) — residual minor, bukan defect.
- Uji beban konkuren tidak dilakukan (di luar cakupan fungsional).
