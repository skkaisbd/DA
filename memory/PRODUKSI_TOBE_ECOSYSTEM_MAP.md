# PETA EKOSISTEM TO-BE (MENYELURUH) — Produksi/Maklon + semua portal
> Versi TO-BE: Produksi & Maklon PISAH (tanpa WO terpadu), flow progress SOMMERVILLE.
> Fokus fase-1: PO→progress→yield→fulfillment→shipment. Penjelasan per-edge = use-case.

## DIAGRAM
```
                     ┌───────────────────────────────────────────────┐
                     │  RnD  (dewi_rnd_styles + dewi_rnd_sample_req)   │
                     │  desain → sample → APPROVE → TENTUKAN BOM       │
                     │  (HANYA jalur INTERNAL; maklon TIDAK lewat RnD) │
                     └───────────────┬─────────────────────────────────┘
                                     ▼
             ┌───────────────────────────────────────────────────────┐
             │  MASTER PRODUK INTERNAL                                 │
             │  rahaza_models + rahaza_boms + rahaza_sizes + SOP       │
             │  BOM = KAIN + AKSESORIS + urutan proses                 │
             └───┬───────────────────────────────────┬────────────────┘
      (BOM sebut │ kebutuhan aksesoris)               │
                 ▼                                    ▼
   ┌──────────────────────────┐          ┌───────────────────────────────┐
   │ PORTAL AKSESORIS          │          │ KATALOG MARKETING              │
   │ master stok · opname ·    │          │ marketing_catalogs/_items      │
   │ request internal · pinjam │          │ = master + HARGA JUAL + plot   │
   │ · purchase request        │          │   akun toko (Shopee/TikTok/..) │
   │ → SUPLAI aksesoris ke      │          └──────────┬─────────────────────┘
   │   PRODUKSI & RnD sampling │                     │ dijual online → DEMAND
   └───────────┬──────────────┘                     │
     issue/pinjam aksesoris    │                     │
                 └──────────────┼─────────────────────┤
                                ▼                     ▼
   ┌──────────────────────────────────┐   ┌──────────────────────────────────┐
   │ PRODUKSI INTERNAL (TO-BE)         │   │ MAKLON (TO-BE — TERPISAH)         │
   │ production_pos → production_jobs  │   │ dewi_maklon_pos → progress →      │
   │ → progress(produced,defect) →     │   │ yield → dispatch klien            │
   │ yield → fulfillment → shipment    │   │ produk = SNAPSHOT spek KLIEN      │
   │ material: dari GUDANG (milik DA)  │   │ material: dari KLIEN              │
   └──────┬──────────────┬─────────────┘   └───────────────┬───────────────────┘
          │              │ (outsource jahit)                │ (subcontract sebagian)
          │              ▼                                  ▼
          │      🔶 VENDOR CMT  (business_type = internal | maklon  ← OWNER EKSPLISIT)
          │      vendor_shipments / dewi_cmt_* / wh_cmt_dispatches / role cmt_vendor
          ▼                                                 ▼
   FG → GUDANG (rahaza_fg_inventory)               FG → DISPATCH ke KLIEN (surat jalan)
   → Fulfillment → kirim ke CUSTOMER               (BUKAN inventory DA)
   → MARKETING catat penjualan                     → FINANCE: AR JASA (CMT rate) + DP + termin
   → FINANCE: inventory → COGS → AR penjualan

CROSS-CUTTING (menopang keduanya):
  GUDANG    : simpan material+aksesoris+FG; issue/return; opname; surat jalan
  FINANCE   : costing/HPP; GL; AR/AP; depresiasi; posting profiles
  HR + PORTAL SAYA : operator/skill; absensi/shift; payroll piece-rate; self-service (slip/cuti/kpi)
  MANAJEMEN ASET   : mesin & alat produksi = ASET → depresiasi ke Finance
  KOLABORASI       : chat/spreadsheet lintas divisi (bukan data produksi)
```

## TABEL EDGE INTEGRASI (dari → ke : arti / use-case)
| Dari → Ke | Yang mengalir | Arti / Use-case | Koleksi kunci |
|---|---|---|---|
| RnD → Master Produk Internal | style+sample approved + BOM | RnD RISET produk baru; begitu di-approve & BOM fix → LAHIR artikel siap produksi | dewi_rnd_styles, rahaza_models, rahaza_boms |
| Master Produk → Katalog Marketing | artikel + harga jual + akun | Produk yang MAU DIJUAL online dipasang harga & diplot ke akun toko | marketing_catalogs/_items, marketing_accounts |
| Katalog → Produksi Internal | order online = DEMAND | Barang laku → butuh diproduksi → jadi PO produksi internal | marketing_orders, dewi_toko_orders → production_pos |
| BOM → Aksesoris | daftar aksesoris dibutuhkan | BOM sebut kancing/label/ritsleting dsb → produksi minta ke divisi Aksesoris | rahaza_boms(accessory_materials), accessory_requests |
| Aksesoris → Produksi | aksesoris di-issue/pinjam | Divisi Aksesoris keluarkan stok aksesoris utk WO; kurang → auto request/PR | accessories, accessory_shipments, po_accessories |
| Aksesoris → RnD | aksesoris utk sampling | RnD butuh aksesoris utk bikin sample | rnd-accessory-requests |
| Aksesoris → Finance/P2P | purchase request | Stok aksesoris menipis → PR → pengadaan | accessory purchase → rahaza_purchase_orders |
| Gudang → Produksi Internal | material kain (milik DA) | Produksi internal ambil bahan dari stok DA | rahaza_material_stock/issues |
| KLIEN → Maklon | PO + material klien | Klien kirim spek+material; DA hanya jasa CMT | dewi_maklon_pos, snapshot |
| Produksi/Maklon → Vendor CMT | material+cutting ke vendor | Outsource jahit (internal saat overload / maklon subcontract). OWNER eksplisit | vendor_shipments, dewi_cmt_* |
| Produksi Internal → Gudang FG | barang jadi masuk stok | FG milik DA disimpan utk dijual | rahaza_fg_inventory |
| Gudang FG → Marketing | fulfillment penjualan | Order online dipenuhi dari stok FG → dikirim ke customer | fulfillment, marketing_orders |
| Maklon → Klien | dispatch surat jalan | Barang jadi (milik klien) dikirim balik ke klien | dewi_maklon_dispatches |
| Produksi Internal → Finance | inventory→COGS→AR jual | Nilai persediaan → HPP saat terjual → piutang penjualan | rahaza_journal_*, rahaza_ar_invoices |
| Maklon → Finance | AR jasa + DP | Tagih fee CMT ke klien (bukan jual barang) | rahaza_ar_invoices/dewi_maklon_invoices |
| Produksi → HR/Portal Saya | operator, output | Ambil operator dari HR; output → KPI; upah piece-rate | rahaza_employees, payroll |
| Mesin produksi → Manajemen Aset | mesin=aset | Mesin jahit/cutting = aset → depresiasi | rahaza_fixed_assets |

## PORTAL YANG BUKAN BAGIAN FLOW PRODUKSI (untuk kejelasan)
- Portal Saya = self-service HR (slip/cuti/kpi) — turunan HR, bukan produksi.
- Kolaborasi = komunikasi/spreadsheet lintas tim — cross-cutting.
- Manajemen Aset = terkait produksi HANYA via mesin=aset→depresiasi Finance.

## KOREKSI (dari user)
- Menu "Peminjaman" di Portal Aksesoris = peminjaman **ASET/alat** (bukan aksesoris habis-pakai).
  Jadi jalur "pinjam" bukan konsumsi aksesoris produksi — itu domain Manajemen Aset.
- Aksesoris habis-pakai (kancing/label/ritsleting) TETAP di-issue ke produksi via BOM→request.
