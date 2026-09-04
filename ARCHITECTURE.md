# ARCHITECTURE.md — Cross-Domain SSOT Reference (CV. Dewi Aditya ERP)

> **Tujuan:** "build memory" lintas-domain agar sesi/agent berikutnya cepat paham
> **SSOT (Single Source of Truth)** tiap domain, siapa penulisnya, dan alur data antar-domain.
> **Grounded:** nama koleksi diverifikasi ke DB live (177 koleksi) pada 2026-07-21.
> **Jangan duplikat** `memory/GUIDELINE_CMT_FLOW.md` (detail Produksi/Maklon/CMT-flow ada di sana —
> dokumen itu **prioritas lebih tinggi** bila ada konflik). File ini = peta ringkas + pointer.
>
> Presedensi bukti: **runtime > kode nyata > dokumen**. Kalau menemukan diskrepansi,
> catat di CHANGELOG, jangan patch kode agar cocok dokumen.

---

## 1. Domain Registry (SSOT per domain)

| Domain | SSOT collections (writer) | Owner file(s) | Catatan |
|---|---|---|---|
| **Produksi (Internal)** | `production_pos`, `production_job_items`, `production_jobs`, `production_progress` | `routes/production_pos.py`, `routes/production_execution.py` | Cutting: `dewi_cutting_requests`, `dewi_cutting_batches`. |
| **Maklon** | `dewi_maklon_pos` (header+items[]), `dewi_maklon_dispatches`, `dewi_maklon_material_receive`, `dewi_maklon_qc_checks`, `dewi_maklon_invoices`, `dewi_maklon_payments`, `dewi_maklon_advance_payments` | `routes/dewi_maklon_pos.py`, `routes/dewi_maklon_finance.py`, `routes/dewi_maklon_billing.py` | Buyer catalog: `dewi_maklon_buyer_catalog`. HPP: `dewi_maklon_hpp`. |
| **Vendor CMT (portal)** | `vendor_partners`, `vendor_jobs`, `vendor_progress_reports` | `routes/vendor_portal.py` | Admin CRUD penuh (partner/akun/job). Akun login = `users` role `cmt_vendor` (link `cmt_vendor_id`). |
| **CMT-flow (DA↔Vendor)** | `dewi_cmt_partners`, `dewi_cmt_jobs`, `dewi_cmt_deliveries`, `dewi_cmt_delivery_orders`, `dewi_cmt_payments`, `dewi_cmt_component_requests` | `routes/dewi_cmt_*.py` | **Detail lengkap → `memory/GUIDELINE_CMT_FLOW.md`.** |
| **Finance / Rahaza Posting** | `rahaza_journal_entries`, `rahaza_journal_lines`, `rahaza_coa_accounts`, `rahaza_posting_profiles`, `rahaza_hpp_snapshots`, `rahaza_periods` | `routes/rahaza_posting.py`, `routes/rahaza_posting_profiles.py`, `routes/rahaza_coa.py`, `routes/rahaza_hpp.py` | Semua posting **idempotent** via `(source_module, source_ref)`. JE header+lines terpisah (link `je_id`). |
| **Marketing / Toko / After-sales** | `marketing_orders`, `marketing_returns`, `marketing_complaints`, `credit_notes`, `marketing_catalogs`/`marketing_catalog_items`, `marketing_kol_creators` | `routes/marketing_*.py` | **Toko lama (`dewi_toko_*`) DEPRECATED** — cutover Phase C → `/api/marketing/*` SSOT. |
| **HR / Payroll** | `rahaza_payroll_runs`, `rahaza_payroll_profiles`, `rahaza_salary_grades`, `rahaza_salary_adjustments`, `rahaza_attendance_events`, `da_payroll_allowances` | `routes/rahaza_hr_seed.py`, `routes/dewi_hris_*.py`, payroll routes | ⚠️ `payroll_entries` = koleksi hantu (Session #17) — jangan tulis ke sana. |
| **Master Produk** | `rahaza_models`, `rahaza_model_variants`, `rahaza_colors`, `rahaza_sizes`, `rahaza_materials` | `routes/rahaza_master.py`, `routes/rahaza_materials.py` | Aksesoris = `rahaza_materials` filter `type='accessory'` (`/api/acc/items/*`). |

---

## 2. Cross-domain data flows (posting bridges)

| # | Trigger | Aksi | JE / SSOT | source_module |
|---|---|---|---|---|
| F1 | Job **Internal** `Completed` (via `production-progress`) | WIP → Barang Jadi | `rahaza_journal_entries` Dr FG `1-1404` / Cr WIP `1-330` | `wip_to_fg_on_wo_complete` (profile), fungsi aktif `post_wip_to_fg_on_job_complete` |
| F2 | **DP Maklon** dari klien | Dr Bank `1-131` / Cr Uang Muka `2-140` | balanced, posted | `maklon_advance_payment` |
| F3 | Maklon **AR Invoice** (PO confirmed) | Dr Piutang / Cr Pendapatan Maklon / Cr PPN | balanced | `maklon_ar_invoice` |
| F4 | **CMT AP Invoice** (bayar vendor) | Dr Biaya CMT / Cr Hutang Vendor | balanced | `cmt_ap_invoice` |
| F5 | (Guideline) CMT Receipt/Buyer Shipment | Mature AP/AR → finance | lihat `GUIDELINE_CMT_FLOW.md` | — |

**Aturan posting (WAJIB):**
- Akun target **harus postable leaf** (`is_group=false`). Jangan pernah post ke header/group.
- Idempotency via `_find_existing_je(db, source_module, source_ref)` sebelum `_create_posted_je`.
- Profil akun di `rahaza_posting_profiles` (auto-seed startup dari `DEFAULT_PROFILES`).
  Endpoint disarankan **validasi postability + fallback ke default postable** (contoh: `dewi_maklon_finance.record_advance_payment._postable`).

---

## 3. Bridge modules

- `routes/production_maklon_bridge.py` — jembatan `production_pos` ↔ `dewi_maklon_pos` ↔ `dewi_maklon_finance`.
- `routes/production_internal_adapter.py` — event job Internal (`on_job_completed_internal`) → HPP snapshot + posting `post_wip_to_fg_on_job_complete`.
- `routes/rahaza_posting.py` — semua helper posting finance (`_create_posted_je`, `_find_existing_je`, `_void_je_by_source`).

---

## 4. Anti-duplikat glossary (mudah tertukar)

| Sering keliru | SSOT sebenarnya | Status yang lain |
|---|---|---|
| `production_pos` vs `dewi_maklon_pos` | keduanya SSOT untuk domainnya | dihubungkan via bridge, bukan mirror buta |
| `production_jobs` vs `dewi_cmt_jobs` vs `vendor_jobs` | `production_jobs` (internal), `dewi_cmt_jobs` (CMT-flow), `vendor_jobs` (portal vendor) | domain berbeda, jangan digabung |
| `dewi_toko_*` | **DEPRECATED** → `marketing_*` | cutover Phase C |
| `payroll_entries` | koleksi hantu (0 reader) | jangan tulis (Session #17) |
| `2-140` (Uang Muka Diterima – Maklon, postable) | benar untuk DP Maklon | `2-1300` = "Hutang Pajak" **non-postable header**, JANGAN dipakai |
| Aksesoris koleksi terpisah | `rahaza_materials` `type='accessory'` | tidak ada koleksi `accessories` sendiri |

---

## 5. Konvensi teknis

- **Currency/number**: locale ID (`.`=ribuan, `,`=desimal). Parse: `utils/money.py`
  (`parse_id_number`, `parse_id_int`, `format_idr`); frontend: `src/lib/format.js`
  (`formatRupiah`, `formatNumber`, `parseIDNumber`/`parseRupiah`).
- **Auth**: JWT bearer; `require_auth` + `check_role`. Role Finance kanonik = `accounting`
  (bukan `finance`) — cek daftar role di endpoint bila menambah role.
- **API prefix** `/api`; posting idempotent; koleksi baru = additive.
- **Serialisasi**: `serialize_doc` (drop `_id`, konversi datetime → ISO) sebelum return.

---

## 6. Pointer dokumen

- `memory/GUIDELINE_CMT_FLOW.md` — **master** Produksi/Maklon/CMT-flow (prioritas tertinggi).
- `memory/PREVIEW_STABLE_MODE.md` — kendala env pod (frontend static bundle, WAJIB baca).
- `BACKLOG_PLAN.md` — backlog item + acceptance criteria.
- `memory/CHANGELOG.md` — riwayat perubahan per sesi.
- `memory/INVARIANTS.md`, `memory/BUG_REGISTRY.md` — invariant & registri bug.
