# VERIFIKASI KECACATAN LOGIKA — REAL SYSTEM (Portal Produksi & overlap)
> Analisis forensik existing DA (bukan SOMMERVILLE). Output → bahan PLAN untuk diluruskan.
> Semua temuan grounded: file:line / koleksi / endpoint / data live.

## D1 — DUAL MESIN PRODUKSI (akar kebingungan)
DA punya DUA model produksi paralel, dua-duanya HIDUP di backend:
- `production_*` (warisan SOMMERVILLE): production_pos/jobs/progress/variances/returns/
  buyer_shipments. Endpoint LIVE (routes/production_*.py) TAPI UI-nya diarsip
  (components/erp/_archive/, sisa POStageTrackingPanel).
- `rahaza_*` (bikinan DA): rahaza_work_orders + multi-stage (cutting/CMT/QC/packing).
  Inilah yang dipakai UI Produksi sekarang (portalNav: prod-orders→RahazaOrders,
  prod-work-orders→RahazaWorkOrders).
BUKTI: kedua set koleksi dipakai 11–16 file. DAMPAK: dua "sumber kebenaran" utk satu
konsep production order → kebingungan, seed mubazir, logika kontradiktif.

## D2 — WO TERPADU (flag `source`) RAPUH → CRASH LATEN
`rahaza_work_orders` = satu koleksi utk internal DAN maklon via field `source`.
- routes/rahaza_work_orders.py `_enrich_wo()`: cabang maklon (L267-272) TIDAK pernah
  set `qty`; jalur `with_progress=True` (detail L366, progress L477) hitung
  `progress_pct = completed/qty` → UnboundLocalError/500 utk SETIAP WO source=maklon.
- Data live: 25/25 WO ter-seed TANPA field `source` (semua "(none)"→default internal).
  Jalur maklon-WO TAK PERNAH di-seed/diuji → bug laten tak kelihatan.
DAMPAK: buka/progress work order maklon = 500. Desain internal+maklon satu koleksi =
pabrik bug.

## D3 — MASTER DATA BUKAN SINGLE-SOURCE (RnD bukan satu-satunya asal)
Konsep bisnis (benar): RnD → tentukan BOM → lahir master produk internal
(rahaza_models+rahaza_boms) → Katalog Marketing (marketing_catalogs/_items = +harga jual
+plot ke akun toko). Maklon TERPISAH (dewi_maklon_buyer_catalog/snapshot; spek dari klien).
Realita kode: `rahaza_models` dibuat/diubah dari 5 tempat: dewi_rnd_styles(RnD),
rahaza_admin_helpers, rahaza_demo_seed, rahaza_production, rahaza_setup → produk bisa
lahir TANPA lewat RnD/BOM → `bom_snapshot` kosong → enrich WO hasil 0 material.
DAMPAK: master vs katalog vs maklon rawan tercampur; BOM tak konsisten.

## D4 — LAPISAN CMT/VENDOR MENUMPANG INTERNAL & MAKLON (kepemilikan ambigu)
`wh_cmt_dispatches`, `dewi_cmt_lifecycle`, `vendor_shipments` dirujuk BAIK internal
(production_seed_full) MAUPUN maklon (dewi_maklon_finance) + role cmt_vendor.
Tak ada pemilik jelas: satu CMT dispatch itu overflow produksi internal atau subcontract
maklon? Koleksi sama, semantik beda. DAMPAK: kepemilikan material (DA vs klien) tak bisa
diturunkan bersih dari record CMT → risiko salah hitung stok/finance.

## D5 — DEAD/REDIRECT CODE MASIF DI PRODUKSI (kebingungan + hazard)
moduleRegistry: 81 makeRedirect (20 prod-*), 9 komponen _archive, 7 route *_backup.
UI produksi SOMMERVILLE lama diarsip tapi endpoint backend dipertahankan; prod-cmt/
prod-cmt-packing redirect ke vendor-admin/wms; maklon-cmt juga redirect.
DAMPAK: sulit tahu mana yang "real" → agent/orang menyentuh jalur mati → "halusinasi".

## RINGKAS AKAR MASALAH
Overlap = (a) dua mesin produksi (D1), (b) internal+maklon dalam satu WO (D2),
(c) master data multi-origin (D3), (d) CMT/vendor tanpa owner (D4), (e) dead code (D5).
Arah pelurusan (kandidat, untuk PLAN): pisahkan mesin per domain, master data single-source
(RnD→model→katalog), CMT/vendor beri owner eksplisit, buang dead code, adopsi flow progress
SOMMERVILLE yang lurus utk menggantikan multi-stage rahaza yang rapuh.
