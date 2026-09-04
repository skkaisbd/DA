# MAPPING AS-IS vs TO-BE — Adopsi Flow Produksi SOMMERVILLE (disesuaikan Produksi vs Maklon)
> Pendekatan KERAS: hapus mesin produksi rahaza multi-stage yang cacat (D1–D5), adopsi flow
> progress SOMMERVILLE yang lurus, pisahkan logic Produksi vs Maklon. Fokus fase-1:
> PO → progress → yield/output → fulfillment PO → shipment (SKIP multi-stage lini).

## TABEL A — DATA MODEL (AS-IS → TO-BE)
| Konsep | AS-IS (sekarang) | Masalah | TO-BE (seharusnya) |
|---|---|---|---|
| Mesin produksi | `rahaza_work_orders` (satu koleksi, flag `source` internal/maklon) + `production_*` (orphan) | D1 dua mesin; D2 WO terpadu rapuh | **PISAH per portal**: Produksi pakai `production_*` (SOMMERVILLE); Maklon pakai `dewi_maklon_*` — tidak ada lagi WO terpadu ber-flag |
| Production order | `rahaza_work_orders` (+source) | crash maklon (qty) | Produksi: `production_pos`+`po_items`; Maklon: `dewi_maklon_pos` |
| Progress | multi-proses `rahaza_processes` per stage | kompleks, rapuh | `production_progress` (produced_qty, defect_qty) — single-stage |
| Yield/output | tersebar per proses | tak ada angka yield bersih | `produced_qty − defect_qty` = good; yield% = good/produced |
| Fulfillment | stage-qty rahaza | tak jelas | `qty_shipped` vs `ordered_qty` (+ over/under) |
| Shipment | `wh_cmt_dispatches`/fulfillment terpisah | ambigu owner | Produksi→`buyer_shipments` (ke customer/fulfillment); Maklon→dispatch klien (surat jalan) |
| Variance | `production_variances` (rahaza post-gl) | ok, dipertahankan | `production_variances` (over/under) + bridge GL menyusul |
| Master produk | `rahaza_models` dibuat 5 tempat | D3 multi-origin | Single-source: **RnD→BOM→`rahaza_models`+`rahaza_boms`**; produksi WAJIB rujuk model+BOM |
| Master maklon | campur (snapshot di WO terpadu) | D2/D4 | `dewi_maklon_buyer_catalog`/snapshot (spek KLIEN) — terpisah total |
| CMT/vendor | `vendor_shipments`+`dewi_cmt_*` dipakai internal & maklon tanpa owner | D4 | Beri field OWNER eksplisit (`business_type`: internal|maklon) pada dispatch/vendor record |

## TABEL B — FLOW PRODUKSI (AS-IS → TO-BE)
| Langkah | AS-IS (rahaza multi-stage) | TO-BE (SOMMERVILLE progress, disesuaikan) |
|---|---|---|
| 1. Order | WO dari order (source internal/maklon) di 1 koleksi | Produksi: PO internal (dari demand marketing/toko/manual); Maklon: PO klien |
| 2. Material | material issue rahaza / CMT | Produksi: issue dari Gudang (milik DA); Maklon: terima material KLIEN |
| 3. Eksekusi | Cutting→Sewing→Finishing→QC→Packing (stage terpisah, line assign, OEE/andon) — SKIP | **Single progress**: catat produced_qty & defect (bisa oleh operator internal / CMT vendor) |
| 4. Yield | tersebar | good = produced−defect; yield% ditampilkan |
| 5. Fulfillment | stage-qty | qty_shipped vs ordered; over/under = variance |
| 6. Shipment | dispatch campur | Produksi→buyer/customer (FG ke Gudang→fulfillment); Maklon→klien (surat jalan) |
| 7. Finance | WIP GL rahaza | Produksi: inventory→COGS→AR jual; Maklon: AR jasa (CMT rate) — bridge menyusul |

## TABEL C — PERBEDAAN LOGIC PRODUKSI vs MAKLON (di TO-BE)
| Aspek | PRODUKSI (internal) | MAKLON |
|---|---|---|
| Pemicu PO | demand internal (marketing/toko/manual) | PO dari KLIEN |
| Master produk | `rahaza_models` (dari RnD→BOM) | snapshot spek KLIEN (`dewi_maklon_buyer_catalog`) |
| Pemilik material | DA (dari Gudang) | KLIEN |
| Costing | HPP penuh (bahan+CMT+OH) → inventory | HPP JASA (tanpa bahan) → CMT rate/pcs |
| Tujuan shipment | customer/marketplace (via Gudang→fulfillment) | KLIEN (surat jalan, bukan inventory DA) |
| Finance | inventory→COGS→AR penjualan | AR jasa ke klien + DP + termin |
| Katalog | terhubung Katalog Marketing (harga+akun toko) | TIDAK ada katalog marketing |
| RnD | WAJIB (asal master produk) | TIDAK terkait RnD |

## TABEL D — YANG DIHAPUS (pendekatan keras)
| Defect | Hapus apa | Ganti dengan |
|---|---|---|
| D1 | Mesin `rahaza_work_orders` sbg mesin produksi + endpoint gandanya | `production_*` (Produksi) + `dewi_maklon_*` (Maklon) |
| D2 | Skema WO terpadu ber-flag `source` | Dua jalur terpisah, tak ada shared-WO |
| D3 | 4 jalur pembuat `rahaza_models` non-RnD (admin/seed/production/setup) | Single-source: hanya via RnD→BOM |
| D4 | CMT/vendor tanpa owner | Tambah `business_type` owner di record CMT/vendor |
| D5 | 20 redirect `prod-*`, 9 `_archive`, 7 `*_backup`, modul multi-stage yg di-skip | UI Produksi baru berbasis flow SOMMERVILLE |

## CATATAN KEPUTUSAN (untuk plan)
- Fase-1 fokus: PO→progress→yield→fulfillment→shipment (single-stage). Multi-stage di-SKIP.
- Downstream (Gudang/Finance) "sudah cukup benar" → bridge menyusul (fase berikut).
- Maklon TETAP terpisah; jangan digabung ke mesin Produksi.
- Backend `production_*` SUDAH ADA di DA → adopsi UI + penyesuaian logic, bukan bikin dari nol.
