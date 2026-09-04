# HANDOFF — LANJUTKAN ANALISIS (Adopsi Produksi SOMMERVILLE -> DA)
> Untuk agent/sesi berikutnya.
> **UPDATE (sesi lanjutan): ANALISIS E1–E9 LENGKAP.** Baca `PRODUKSI_E1-E9_RECAP.md` dulu (indeks + semua
> decision points terkumpul), lalu detail per-bagian E1..E9. Keputusan user baru sudah dikunci di
> `SOMMERVILLE_ADOPTION_PLAN.md` (#5 UI tetap DA, #6 finance tetap DA, #7 scope adopsi, #8 strategi 2GB).
> BELUM eksekusi kode sampai user beri lampu hijau + putuskan decision points terbuka (RECAP §3).
> Tujuan handoff (historis): lanjutkan FULL ANALISIS dgn metode & gaya SAMA, lalu finalkan PLAN.

## A. KONTEKS SINGKAT
- DA = ERP garment CV. Dewi Aditya (React+FastAPI+Mongo). DA adalah FORK dari SOMMERVILLE.
- User FRUSTRASI dgn Portal Produksi (rahaza_*) yg buggy tak selesai; pilih pendekatan KERAS:
  adopsi flow SOMMERVILLE + hapus yang cacat.
- User minta: Maklon = IDENTIK SOMMERVILLE (field+collection persis); Produksi internal = base sama
  + disesuaikan utk integrasi. Fokus fase-1: PO->progress->yield->fulfillment->shipment (skip multi-stage).
- MODE: masih DISKUSI/ANALISIS. Output tiap langkah = tabel AS-IS vs TO-BE + peta integrasi + penjelasan use-case.
  User TIDAK mau asumsi — semua harus GROUNDED ke kode (file:line/koleksi/endpoint) + verifikasi live.

## B. STATUS ENVIRONMENT (sudah siap)
- App JALAN STABIL (no loop). Backend healthy, FE = STATIC BUNDLE.
- ATURAN ENV (WAJIB): JANGAN `craco start`/`yarn start:dev` (loop 5 menit -> pod restart).
  FE dilayani `node static_server.js`. Setelah ubah frontend/src: `bash /app/scripts/rebuild_frontend.sh`.
  Backend hot-reload normal. backend/.env WAJIB ada JWT_SECRET. EMERGENT_LLM_KEY sudah di-set.
- Kredensial: admin@garment.com / Admin@123 ; {hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123.
- SOMMERVILLE reference clone ada di /tmp/sommerville (git shallow). Backend monolit server.py 6267 baris,
  153 endpoint @api.*, FE ~55 komponen flat + App.js state-based (bukan portal shell).

## C. YANG SUDAH DIANALISIS (DONE) — baca dokumen ini
1. SOMMERVILLE_ADOPTION_ANALYSIS.md — DA=fork SOMMERVILLE; peta integrasi; mesin WO terpadu.
2. PRODUKSI_LOGIC_DEFECTS.md — D1..D5 grounded (dual engine, WO terpadu crash, master multi-origin,
   CMT tanpa owner, dead code).
3. PRODUKSI_MAPPING_ASIS_TOBE.md — Tabel A/B/C/D AS-IS vs TO-BE + yang dihapus.
4. PRODUKSI_TOBE_ECOSYSTEM_MAP.md — peta menyeluruh + tabel edge integrasi (RnD/Master/Katalog/
   Aksesoris/Gudang/Finance/HR/Aset/Kolaborasi) + koreksi peminjaman=aset.
5. SOMMERVILLE_ADOPTION_PLAN.md — plan (living doc).

## D. FAKTA KUNCI (jangan diulang risetnya)
- Endpoint & koleksi produksi DA == SOMMERVILLE (production_pos/jobs/progress/variances/returns/
  buyer_shipments/vendor_shipments/material_requests/po_accessories). Backend production_*.py DA MASIH ADA
  tapi UI-nya diarsip; UI produksi sekarang pakai rahaza_* (buggy).
- Master produk internal: RnD(dewi_rnd_styles+sample_req) -> tentukan BOM -> rahaza_models+rahaza_boms+
  rahaza_model_process_sop+rahaza_sizes. Katalog Marketing (marketing_catalogs/_items) = master + harga jual
  + plot akun toko (marketing_accounts/comm_channels). MAKLON TERPISAH (dewi_maklon_buyer_catalog/snapshot).
- Vendor CMT dipakai internal(overload) & maklon(subcontract): vendor_shipments/dewi_cmt_*/wh_cmt_dispatches/
  role cmt_vendor. Beri owner business_type di TO-BE.
- po_items SOMMERVILLE punya selling_price_snapshot + cmt_price_snapshot (2 harga).

## E. SISA ANALISIS (LANJUTKAN — urut prioritas)
1. **FIELD INVENTORY LENGKAP SOMMERVILLE** per collection (metode: grep insert dict di server.py,
   contoh sudah utk production_pos/po_items). Ekstrak: production_jobs, production_job_items,
   production_progress, buyer_shipments(+items+dispatches), vendor_shipments(+items),
   vendor_material_inspections(+items), material_requests, production_variances, production_returns(+items),
   po_accessories, accessory_*, invoices, payments. -> jadi kamus field acuan Maklon (identik) + Produksi.
2. **Flow QC & Retur** detail (produksi & maklon): inspection, defect, production_returns, buyer variance.
3. **Bridge FINANCE**: bagaimana production/variance -> GL (DA sudah punya production-variances/{vid}/post-gl);
   AR jual (internal) vs AR jasa (maklon); posting profiles yang relevan.
4. **Flow GUDANG** detail: material issue/return, FG receiving, opname, surat jalan, CMT dispatch.
5. **Marketing**: catalog <-> demand (marketing_orders/dewi_toko_orders) <-> fulfillment FG. Plot akun toko.
6. **HR**: operator assignment, piece-rate payroll dari output produksi, shift, KPI.
7. **ASET**: mesin=aset -> depresiasi; PEMINJAMAN ASET (menu di Aksesoris).
8. **RBAC**: role SOMMERVILLE (vendor/buyer/admin/superadmin) vs role DA (portal-based+cmt_vendor+custom).
   Petakan siapa boleh apa di flow baru.
9. **AKSESORIS**: BOM(accessory_materials) -> request -> issue ke produksi; purchase request; opname.

## F. METODE (ikuti gaya yang sudah jalan)
- Tiap bagian: (1) grounded ke kode (grep/view file:line, cek koleksi, probe endpoint live dgn token admin),
  (2) buat tabel AS-IS vs TO-BE, (3) peta integrasi + penjelasan use-case, (4) simpan ke /app/memory,
  (5) MINTA VALIDASI user sebelum lanjut. JANGAN asumsi; kalau ragu -> verifikasi kode dulu, bukan tanya.
- Probe live: TOKEN=$(login admin) lalu curl endpoint. Prefix maklon = /api/dewi/maklon; produksi rahaza = /api/rahaza/*.
- Update SOMMERVILLE_ADOPTION_PLAN.md tiap ada keputusan baru.

## G. JANGAN
- Jangan eksekusi/ubah kode produksi sebelum user setuju (masih fase analisis).
- Jangan `craco start`. Jangan timpa .env (JWT_SECRET/MONGO_URL/REACT_APP_BACKEND_URL).
- Jangan gabung Maklon ke mesin Produksi (harus tetap pisah).
- Jangan warisi bug SOMMERVILLE (lihat PRODUCTION_FLOW_AUDIT.md di /tmp/sommerville).
