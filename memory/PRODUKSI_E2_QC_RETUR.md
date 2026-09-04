# E2 — FLOW QC & RETUR (Produksi & Maklon) : AS-IS vs TO-BE
> Handoff §E2. GROUNDED ke kode DA (`/app/backend/routes/*`) + SOMMERVILLE (`/tmp/sommerville/backend/server.py`).
> STATUS: ANALISIS (belum eksekusi). Fokus: QC & Retur SISI PRODUKSI/MAKLON.
> (Retur PELANGGAN/after-sales `marketing_returns`↔`wh_returns` sudah didokumentasikan Sesi #86 —
> di sini hanya disebut sbagai batas domain.)

## 0. TEMUAN INTI — ADA 5 SISTEM QC PARALEL + 3 SISTEM RETUR PARALEL (bukti D1/D5)
Grep `db.*qc*/defect/receipt/return` menemukan sistem QC & retur tumpang tindih:
- QC: `rahaza_qc_events`, `qc_inspections`, `rahaza_grn_inspections`, `dewi_maklon_qc_checks`,
  `cmt_receipts`(+lines) + (SOMMERVILLE) `vendor_material_inspections`+`material_defect_reports`.
- Retur: `production_returns`(+items), `production_material_returns`, `marketing_returns`/`wh_returns`
  /`dewi_returns`/`dewi_toko_returns`.

---

## 1. QC — AS-IS (5 sistem, grounded)
| # | Sistem / Route | Prefix | Collection | Model QC | Domain | Verdict |
|---|---|---|---|---|---|---|
| Q1 | `rahaza_qc_v2.py` | `/api/rahaza` | `rahaza_qc_events`, `rahaza_defect_codes` | **bundle-based multi-stage** (bundle_id, line_id, shift_id; checked/pass/fail qty; defect_code_ids[]; defect_details[]) + Pareto/FPY | Produksi internal (rahaza) | `verdict` pass\|fail (`rahaza_qc_v2.py:144-171`) |
| Q2 | `qc.py` | `/api/qc` | `qc_inspections`, `qc_defect_types` | inspeksi generik + rework-by-operator + dashboard | generik/produksi | inspection status |
| Q3 | `rahaza_grn_qc.py` | `/api/rahaza/grn-qc` | `rahaza_grn_inspections` | **AQL** incoming material + supplier scorecard | **GUDANG** (GRN material masuk) | reject-categories (`:66-150`) |
| Q4 | `dewi_maklon_qc.py` | `/api/dewi/maklon/qc` | `dewi_maklon_qc_checks` | per-stage per-order; qty_inspected/passed/rejected/rework; reject_rate_pct; alert threshold | **MAKLON** | result pass\|reject\|rework (`:96-132`) |
| Q5 | `dewi_cmt_packing.py` | `/api/prod` | `cmt_receipts`, `cmt_receipt_lines` | QC saat **terima FG dari CMT** (qty_actual per line) → approve = post FG | Produksi/Maklon (CMT) | status Draft→Submitted→Approved/Rejected (`:251-332`) |
| Q6 | (SOMMERVILLE) `server.py` | `/api` | `vendor_material_inspections`(+items), `material_defect_reports` | inspeksi material MASUK (received/missing) + defect saat produksi (defect_qty → potong kapasitas I-1) | **acuan TO-BE** | inspection Submitted; defect Reported |

### Detail Q4 (Maklon) — `dewi_maklon_qc_checks`
Field: order_id, order_code, client_name, **stage** (QC_STAGES), **result** (pass/reject/rework),
qty_inspected, qty_passed, qty_rejected, qty_rework, reject_rate_pct, inspector_name,
alert_triggered, alert_threshold_pct, inspected_at, created_by. Guard: `_assert_qty_consistency`.

### Detail Q5 (CMT FG receipt) — `cmt_receipts` approve
`approve_receipt` (`:251-332`): status harus 'Submitted' → per line `qty_actual` di-post ke
**`rahaza_material_stock`** (ownership `cv_da`, inventory_category `fg_internal`, material_id `FG-<sku>`)
+ audit `rahaza_fg_movements` (movement_type IN, source `cmt_receipt`). Status → 'Approved'.

### Detail Q6 (SOMMERVILLE — acuan)
- **Incoming**: `vendor_material_inspections` + items (received_qty/missing_qty) → `available_qty` job_item.
- **Selama produksi**: `material_defect_reports` (defect_qty) → **kurangi kapasitas** (Invariant I-1:
  produced ≤ available − Σdefect; `server.py:1887-1902`).
- **Tidak ada "QC pass/fail per bundle"** — QC direpresentasikan lewat defect + variance.

## 2. QC — TO-BE (disesuaikan Produksi vs Maklon)
| Aspek | PRODUKSI INTERNAL (TO-BE) | MAKLON (TO-BE) |
|---|---|---|
| Model dasar | **SOMMERVILLE**: inspeksi material masuk + `material_defect_reports` + variance | **IDENTIK SOMMERVILLE** (keputusan terkunci) |
| QC incoming material | dari **Gudang** (bukan vendor kirim) → adaptasi `vendor_material_inspections` jadi "material issue inspection" [bridge E4] | material milik **KLIEN** → `vendor_material_inspections` apa adanya |
| QC selama produksi | `material_defect_reports` (defect_qty potong kapasitas) — **BUANG** `rahaza_qc_events` bundle multi-stage (D1/D5) | sama (SOMMERVILLE) |
| GRN AQL (Q3) | **TETAP** di Gudang (incoming material dari supplier) — bukan bagian mesin produksi | N/A (material klien) |
| CMT FG receipt (Q5) | **TETAP** sebagai jalur FG-in Gudang (bridge Produksi↔Gudang), owner `business_type` | dispatch balik ke klien (bukan FG inventory DA) |

### ⚠️ DECISION POINT QC-1 (PERLU KEPUTUSAN USER)
Maklon sekarang punya QC sendiri (`dewi_maklon_qc_checks`, Q4) yang **stage-based + reject_rate + alert**
— lebih kaya dari model SOMMERVILLE (defect-report). "Maklon identik SOMMERVILLE" berarti:
- **Opsi A** — ganti Q4 dgn model SOMMERVILLE (defect_reports + variance). KEHILANGAN fitur stage/reject-rate/alert.
- **Opsi B** — pertahankan Q4 (lebih baik) sebagai "ekstensi DA di atas Maklon", hanya port struktur PO/job/shipment SOMMERVILLE. (rekomendasi: B — jangan buang fitur yang lebih baik.)

### ⚠️ DECISION POINT QC-2
`rahaza_qc_events` (Q1, bundle multi-stage) dipakai UI Produksi sekarang (ProcessExecutionModule).
Menghapusnya (sesuai D1/D5) = kehilangan Pareto/FPY per-line. TO-BE single-stage tak punya per-line QC.
Tanya: apakah Pareto/FPY per-line MASIH dibutuhkan (Opsi: simpan sebagai analitik opsional) atau boleh dibuang?

---

## 3. RETUR — AS-IS (3 sistem, grounded)
| # | Sistem / Route | Collection | Arti | State | Domain |
|---|---|---|---|---|---|
| R1 | `production_returns.py` (SOMMERVILLE) | `production_returns`(+items) | **BUYER retur FG cacat** ke Admin utk perbaikan | RTN-xxxx: 'Repair Needed' → repair flow (`repaired_qty`) | Produksi (buyer=customer) |
| R2 | `production_material_returns.py` | `production_material_returns` | **Retur SISA MATERIAL** dari lantai produksi → Gudang | draft → submitted → approved → **received** (`:109-135`,`:184-314`) | Produksi↔Gudang |
| R3 | `marketing_returns_routes.py` + `dewi_wh_returns.py` (Sesi #86) | `marketing_returns`, `wh_returns`, `credit_notes` | **Retur PELANGGAN online** → refund + restock | approved→create-wh-return→receive→inspect→resolve→complete→credit-note | Marketing↔Gudang↔Finance |
| (R4) | `dewi_returns.py`, `dewi_toko_returns` | `dewi_toko_returns` | retur toko (legacy, sebagian redirect ke R3) | — | Toko (legacy) |

### Overlap / kebingungan retur
- **R1 vs R3**: dua-duanya "customer/buyer return FG". R1 (SOMMERVILLE) = untuk model outsource-vendor
  (buyer terima dari vendor). R3 (Sesi #86) = retur pelanggan online shop (marketplace). **Tumpang tindih
  makna** utk Produksi internal (siapa "buyer"? customer marketplace = R3).
- **R2** beda domain (material sisa, bukan FG cacat) → jelas milik Gudang. Tetap.

## 4. RETUR — TO-BE
| Konsep | PRODUKSI INTERNAL | MAKLON |
|---|---|---|
| Retur FG cacat dari pelanggan | pakai **R3** (marketing after-sales, sudah jadi & tested Sesi #86) — BUKAN R1 | N/A (barang milik klien; klaim klien = proses maklon terpisah) |
| Retur material sisa ke gudang | **R2** (tetap) | material klien: retur ke klien (bukan R2) |
| R1 `production_returns` (SOMMERVILLE) | **status: opsional** — hanya relevan bila DA benar-benar jalankan model "kirim ke buyer/reseller B2B". Kalau tidak → JANGAN aktifkan (island). | tak dipakai |

### ⚠️ DECISION POINT RET-1 (PERLU KEPUTUSAN USER)
Untuk Produksi internal, retur pelanggan sudah ditangani R3 (marketing after-sales). Apakah:
- **Opsi A** — R1 `production_returns` SOMMERVILLE TIDAK diaktifkan utk internal (hanya port utk Maklon-B2B jika perlu). (rekomendasi A)
- **Opsi B** — aktifkan R1 sebagai jalur retur B2B/reseller terpisah dari retur online R3.

---

## 5. INVARIAN QC/RETUR yang WAJIB dijaga (dari PRODUCTION_FLOW_AUDIT.md)
- **I-1** produced ≤ available − Σdefect (defect_report memotong kapasitas).
- **I-3** Σreturn ≤ Σshipped − Σalready_returned (retur buyer).
- **I-4** return_qty ≥ 1.
- Maklon Q4: `qty_inspected = qty_passed + qty_rejected + qty_rework` (`_assert_qty_consistency`).
- CMT Q5: approve hanya dari status 'Submitted'; `qty_actual` > 0 → FG-in.

## 6. YANG DIHAPUS (pendekatan keras, sinkron D1/D5)
| Buang | Alasan | Ganti |
|---|---|---|
| `rahaza_qc_events` bundle multi-stage (Q1) sbg jalur QC WAJIB produksi | D1/D5 kompleks-rapuh | defect_reports SOMMERVILLE (+ opsional analitik Pareto bila QC-2=simpan) |
| Duplikasi retur R1 utk internal | overlap R3 | R3 marketing after-sales |

## 7. RINGKAS KEPUTUSAN yang perlu user (dibawa ke akhir analisis)
- **QC-1**: Maklon QC → Opsi A (ganti SOMMERVILLE) atau B (pertahankan `dewi_maklon_qc_checks`)? [rek: B]
- **QC-2**: Buang Pareto/FPY per-line (rahaza_qc_events) atau simpan sbagai analitik? 
- **RET-1**: `production_returns` SOMMERVILLE utk internal → aktifkan (B) atau island/skip (A)? [rek: A]

---
*E2 selesai. Lanjut E3 (Bridge Finance).*
