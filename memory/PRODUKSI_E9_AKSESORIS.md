# E9 — AKSESORIS : BOM → Request → Issue + Purchase + Opname (AS-IS vs TO-BE)
> Handoff §E9. GROUNDED: `rahaza_bom.py`, `dewi_accessories_requests.py`, `dewi_accessories_purchase.py`,
> `dewi_accessories_opname.py`, `dewi_accessories_stock.py`. STATUS: **ANALISIS SELESAI → ACC-1/2/3 SUDAH DIEKSEKUSI**.

> ## ✅ STATUS EKSEKUSI (2026-07-25) — ACC-1, ACC-2, ACC-3 SEMUA SELESAI & TERUJI
> Ketiga *decision point* di §4 bawah ini **bukan lagi rencana** — sudah diimplementasi, diuji
> (`scripts/verify_acc123.py` = 62 PASS/0 FAIL; `testing_agent_v3` iteration_167 backend 100%), dan
> diverifikasi di UI. Ringkas hasilnya:
> - **ACC-1 → dipilih Opsi A (otomatis).** Saat PO internal dibuat, BOM di-explode jadi `po_accessories`
>   yang **membawa `accessory_id`**. Endpoint `GET /api/production-pos/{po}/accessory-requirements`
>   (kebutuhan vs stok vs kekurangan) + tombol **Buat Permintaan** → SSOT `dewi_accessory_requests`
>   (`request_type='internal_issuance'`, `status='submitted'`, `source='po_bom_explode'`, anti-dobel).
> - **ACC-2 → `material_id` WAJIB untuk baris ASESORIS** (baris kain/benang tetap boleh lepas demi kompat
>   data lama). Auto-link by `code`; ditolak 400 + sebut nomor baris bila tidak dikenal. Endpoint audit
>   `GET /api/rahaza/boms/link-health` + perbaikan massal `POST /api/rahaza/boms/relink-materials`
>   (RBAC ketat: Admin/Owner + Produksi/RnD). UI: banner kesehatan + kolom "Taut" per baris BOM.
> - **ACC-3 → peminjaman PINDAH ke domain ASET** (`/api/assets/loans*`, modul `#asset-loans`).
>   1 pinjaman = 1 unit aset ber-nomor; kondisi kembali menentukan status aset (baik→aktif,
>   rusak→pemeliharaan + catatan maintenance otomatis, hilang→hilang). Menu lama dilepas dari nav
>   Portal Aksesoris; deep-link `#accessories-loans` tetap hidup + banner deprecation; **`POST /api/acc/loans`
>   ditutup (410)** supaya tidak ada lagi pinjaman baru yang salah domain & mengurangi stok aksesoris,
>   sementara `GET` + `PUT .../return` tetap hidup untuk menutup data historis.
>
> Detail eksekusi & bukti: `plan.md` §FASE 7 · `memory/CHANGELOG.md` (2026-07-25).

## 0. TEMUAN INTI
- **Aksesoris = bagian INVENTORY TERPADU** `rahaza_material_stock` (inventory_category `accessory`),
  BUKAN koleksi terpisah → SSOT konsisten (bagus, sejalan RC-IA).
- **BOM SUDAH memuat aksesoris**: `rahaza_bom.py` field `accessory_materials: [{name, code, qty, unit,
  notes, material_id?}]` (`:20,302`), + kalkulasi kebutuhan aksesoris (BOM × qty, `:407-409`).
- **Opname aksesoris = TERPADU** dengan gudang: SSOT `wh_opname_sessions2` (`dewi_accessories_opname.py:3`).
- **Peminjaman = domain ASET** (koreksi user; lihat E7), BUKAN konsumsi aksesoris.

## 1. AKSESORIS — AS-IS (grounded)
| Flow | Route / Endpoint | Collection | State / Efek |
|---|---|---|---|
| Master + stok | `dewi_accessories_stock.py`, `dewi_accessories_items.py` | `rahaza_materials`(kategori accessory) + `rahaza_material_stock` | stok per lokasi (min/max stock) |
| BOM (kebutuhan/pcs) | `rahaza_bom.py` `accessory_materials[]` | `rahaza_boms` | explode: qty aksesoris = qty_per × order_qty (`:407`) |
| **Request → Issue ke produksi** | `dewi_accessories_requests.py` `/internal-requests` | request docs + `rahaza_material_stock` | Pending → **issued** (`issued_by`), deduct stok (`_add_stock` `:82`) |
| Purchase (beli) | `dewi_accessories_purchase.py` `/purchase-requests` | purchase request docs | Draft → Submitted → Approved / Rejected |
| Opname | `dewi_accessories_opname.py` | **`wh_opname_sessions2`** (terpadu) | count → variance → adjust (audit) |
| Peminjaman (mislokasi) | `dewi_accessories_loans.py` | (lihat E7) | → seharusnya ASET/alat |

### Catatan link BOM→request
- BOM punya `material_id?` **opsional** pada tiap aksesoris → kopling ke master **belum wajib** (longgar).
- `/internal-requests` sekarang cenderung **manual** (belum ada bukti auto-generate dari BOM saat PO dibuat).

## 2. PEMETAAN ke SOMMERVILLE
| SOMMERVILLE | DA (padanan) |
|---|---|
| `po_accessories` (kebutuhan aksesoris per PO) | hasil explode `rahaza_boms.accessory_materials` × qty PO |
| `material_requests` REQ-ACC (aksesoris kurang saat inspeksi) | `dewi_accessories_requests` internal-request / additional |
| stok aksesoris (di vendor) | `rahaza_material_stock` (category accessory, ownership cv_da/maklon_client) |

## 3. TO-BE — Aksesoris dalam ekosistem
| Edge | PRODUKSI INTERNAL | MAKLON |
|---|---|---|
| Kebutuhan aksesoris | saat **production_pos** dibuat → explode BOM `accessory_materials` → buat `po_accessories`/requirement | `po_accessories` (SOMMERVILLE) dari spesifikasi klien |
| Issue ke produksi | issue dari `rahaza_material_stock` (cv_da) → deduct + (opsional) GL | material klien: aksesoris milik klien (ownership maklon_client) |
| Kurang saat inspeksi | `material_requests` REQ-ACC (SOMMERVILLE) → beli/replenish | idem |
| Purchase | `/purchase-requests` → terima (GRN) → stock-in unified | idem |
| Opname | `wh_opname_sessions2` (tetap terpadu) | opname material klien terpisah (ownership) |
| Peminjaman | **pindah ke Aset** (E7) | N/A |

## 4. DECISION POINTS
### ⚠️ ACC-1 (PERLU KEPUTUSAN) — auto BOM→requirement saat PO
- **Opsi A** — otomatis: saat `production_pos` internal dibuat, explode BOM → generate `po_accessories` +
  draft issue. (mengurangi kerja manual; sejalan rantai RnD→BOM→produksi)
- **Opsi B** — manual: user buat `/internal-requests` sendiri (status quo).
- **Rekomendasi A** (konsisten dgn keberadaan explode `:407`), dgn tombol konfirmasi issue.
### ACC-2 — perkuat kopling `material_id`
Wajibkan `material_id` pada tiap aksesoris BOM (bukan opsional) supaya requirement→issue nyambung ke stok
riil (hindari drift nama/kode). [rek: ya, LOW effort]
### ACC-3 — relokasi peminjaman → Aset (lihat E7 AST-3)

## 5. INVARIAN
- Issue aksesoris ≤ available stok (unified).
- Opname = SSOT `wh_opname_sessions2` (satu pintu; jangan buat opname aksesoris terpisah — RC-IA).
- Aksesoris habis-pakai = jalur BOM→request→issue; **peminjaman ≠ konsumsi** (domain aset).

---
*E9 selesai. ANALISIS E1–E9 LENGKAP. Lanjut: finalisasi rangkuman + decision points.*
