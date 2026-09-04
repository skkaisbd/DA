# RECAP — ANALISIS ADOPSI SOMMERVILLE E1–E9 (LENGKAP)
> Ringkasan analisis Produksi/Maklon (mode ANALISIS, belum eksekusi). Dibuat sesi lanjutan.
> Baca berurut: E1→E9. Semua GROUNDED ke kode DA + SOMMERVILLE (`/tmp/sommerville`).

## 1. DAFTAR DOKUMEN ANALISIS
| # | Dokumen | Isi |
|---|---|---|
| E1 | `PRODUKSI_E1_FIELD_INVENTORY_SOMMERVILLE.md` | Field inventory 19 collection SOMMERVILLE + invarian I-1..I-5 + bug C-1..M-3 + delta DA |
| E2 | `PRODUKSI_E2_QC_RETUR.md` | 5 sistem QC + 3 sistem retur (AS-IS) → TO-BE + QC-1/QC-2/RET-1 |
| E3 | `PRODUKSI_E3_BRIDGE_FINANCE.md` | Bridge GL produksi/maklon; risiko rahaza-anchor; FIN-1 open, FIN-2 LOCKED=B |
| E4 | `PRODUKSI_E4_GUDANG.md` | SSOT `rahaza_material_stock`; issue/return/FG/opname/SJ/CMT dispatch; D4 fix; GDG-1/2 |
| E5 | `PRODUKSI_E5_MARKETING.md` | Catalog(by SKU)↔demand↔fulfillment; GAP demand→produksi; MKT-1/2 |
| E6 | `PRODUKSI_E6_HR.md` | Payroll monthly/daily/pcs; piece-rate anchor `rahaza_wip_events`; HR-1/2 |
| E7 | `PRODUKSI_E7_ASET.md` | 2 sistem aset; mesin≠aset (gap); peminjaman salah-domain; AST-1/2/3 (prio rendah) |
| E8 | `PRODUKSI_E8_RBAC.md` | Role SOMMERVILLE(4) vs DA(21+5); `role_permissions` kosong; RBAC-1/2 |
| E9 | `PRODUKSI_E9_AKSESORIS.md` | Aksesoris di unified stock; BOM `accessory_materials`; opname terpadu; ACC-1/2/3 |
| E10 | `PRODUKSI_E10_ADAPTER_MIGRASI.md` | **Desain adapter** re-anchor rahaza WO→`production_jobs` (FIN-1=A, HR-1=campuran, GDG-2=A); KEEP/REPURPOSE/DELETE |
| E11 | `PRODUKSI_E11_VENDOR_PORTAL_ENDPOINTS.md` | **Scoping port portal Vendor/CMT**: 14 komponen SOMMERVILLE → DA (ADA/PARSIAL/GAP) |
| Plan | `SOMMERVILLE_ADOPTION_PLAN.md` | Keputusan terkunci #1–#11 + SCOPE §1b + FASE + §7 strategi 2GB + §8 UI stance |

## 2. KEPUTUSAN TERKUNCI (dari user)
1. DA = fork SOMMERVILLE; adopsi flow progress SOMMERVILLE (lurus), buang rahaza multi-stage (D1–D5).
2. **Maklon = identik SOMMERVILLE** (field+collection persis); **Produksi internal = base sama + adapter integrasi**.
3. **Produksi & Maklon DIPISAH** (tak ada WO terpadu ber-flag `source`).
4. Master single-source: RnD→BOM→`rahaza_models` (internal); snapshot (maklon); garments→`cmt_vendor`.
5. **UI = TETAP DA** (portal shell + moduleRegistry). Hanya port fitur+logic; render pakai komponen DA.
6. **FINANCE = TETAP DA** (`rahaza_posting` + `dewi_maklon_finance`); **jangan clone finance SOMMERVILLE**.
7. **SCOPE ADOPSI** = HANYA (a) logic/flow produksi, (b) master data produksi, (c) tracking, (d) **portal VENDOR/CMT**.
   **SKIP**: finance, system admin/settings, akun/user/auth/role SOMMERVILLE, UI shell, buyer-portal, infra lain.
8. **STRATEGI DEV 2GB**: backend-first, POC script utk validasi (tanpa build), batch FE, **UI testing di AKHIR**.

## 3. DECISION POINTS — STATUS (✅ diputuskan user sesi ini)
| ID | Topik | KEPUTUSAN (final) |
|---|---|---|
| **QC-1** | QC Maklon | ✅ **B** — pertahankan `dewi_maklon_qc_checks` (jangan diganti SOMMERVILLE) |
| **QC-2** | Pareto/FPY per-line (`rahaza_qc_events`) | ✅ **BUANG** (tidak disimpan) |
| **RET-1** | Retur pelanggan internal | ✅ **A** — pakai after-sales R3; `production_returns` SOMMERVILLE TIDAK diaktifkan |
| **FIN-1** | Costing produksi internal | ✅ **A** — costing penuh WIP→FG→COGS, **adapter re-key ke `production_jobs`** |
| ~~FIN-2~~ | Finance Maklon | ✅ **LOCKED=B** — tetap `dewi_maklon_finance` (tak clone finance SOMMERVILLE) |
| **GDG-1** | Owner CMT dispatch/SJ (fix D4) | ✅ **YA** — tambah `business_type` (internal/maklon) |
| **GDG-2** | Anchor material issue produksi | ✅ **A** — `draft-from-job` (selaras FIN-1) |
| **MKT-1** | Jembatan demand→produksi | ✅ **B** — onward CTA "Buat PO Produksi" (bukan auto-PO) |
| **MKT-2** | Katalog `model_id` FK | ✅ **YA** |
| **HR-1** | Skema upah operator internal | ✅ **CAMPURAN** (borongan + bulanan) → **WAJIB pertahankan capture output per-operator** (piece-rate tetap ada) |
| **AST-1/2/3** | Aset (rekonsiliasi/mesin/peminjaman) | ⏸️ **PRIO RENDAH** (tunda pasca inti) |
| **RBAC-1** | Model izin | ✅ **B** — role-string hardcode DA (SOMMERVILLE auth di-skip); remap allowed_roles saat port |
| **ACC-1** | Auto BOM→requirement saat PO | ✅ **A** — otomatis explode saat `production_pos` |
| **ACC-2** | Wajibkan `material_id` di BOM aksesoris | ✅ **YA** |

> **Konsekuensi kunci (HR-1=CAMPURAN + FIN-1=A):** rahaza multi-stage BOLEH dibuang, TAPI perlu tetap
> menyimpan **capture output per-operator/proses** (untuk borongan) + **HPP snapshot per production_jobs**
> (untuk WIP→FG→COGS). Desain adapter ini dianalisis di **`PRODUKSI_E10_ADAPTER_MIGRASI.md`**.

## 4. RISIKO TERTINGGI (integrasi) — ringkas
- **F-1 (HIGH)**: hapus `rahaza_work_orders` memutus WIP→FG→COGS (finance) & piece-rate (HR) & material-issue
  (gudang) yang di-anchor ke sana. → butuh adapter re-key ke `production_jobs` (FIN-1/GDG-2/HR-1 saling terkait).
- **GAP demand→produksi (MKT-1)**: order online belum otomatis jadi PO produksi.
- **D4 (GDG-1)**: owner internal/maklon di CMT dispatch masih ditebak dari WO flag.

## 5. LANGKAH BERIKUTNYA
Analisis E1–E9 **LENGKAP** + **semua decision point sudah diputuskan user** (§3). Karena kluster
**FIN-1=A + HR-1=CAMPURAN + GDG-2=A** menuntut ADAPTER (re-key costing/piece-rate/material-issue dari
`rahaza_work_orders` → `production_jobs`), langkah lanjut = **analisis desain adapter & migrasi**
(`PRODUKSI_E10_ADAPTER_MIGRASI.md`) + **peta endpoint portal Vendor** (`PRODUKSI_E11_VENDOR_PORTAL_ENDPOINTS.md`)
SEBELUM eksekusi. Eksekusi Fase 2 (Maklon) menunggu lampu hijau user (user: "update dokumen dulu & lanjut analisis").
