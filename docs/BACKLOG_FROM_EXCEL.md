# Backlog — Data Excel yang Belum Terakomodasi

Dihasilkan otomatis oleh `scripts/seed_da_master_from_excel.py`.

1. Sheet 'Memo' (rincian per-rol: 12 rol, berat tertulis vs pengecekan, lebar 135cm) BELUM diimpor — perlu keputusan owner: dijadikan dokumen roll fisik (wh_fabric_rolls) untuk kain yang mana?

2. SPEK PRODUK (55 SKU) tersimpan sebagai `spec` di master model (bahan + aksesoris + qty/pcs). BELUM diubah jadi BOM resmi (rahaza_boms) karena nama aksesoris di Excel adalah teks bebas (mis. 'Kancing 18L') dan harus dipetakan manual ke kode master aksesoris (A1, A47, …) + ke size. Perlu keputusan owner: buat layar pemetaan nama→kode, atau isi BOM manual?

3. Dashboard Marketing: sheet DAILY ACTIVITY, KPI TIM, CAMPAIGN, ADS, BUDGET IKLAN, PENCAIRAN MARKETPLACE, RETUR, REVIEW NEGATIF, KOL & ENDORSEMENT, PENGIRIMAN SAMPEL, KOMPETITOR, MEETING berisi TRANSAKSI/aktivitas harian — sengaja TIDAK diimpor sesuai keputusan owner (mulai bersih). Bila nanti ingin dipakai sebagai baseline historis, perlu konfirmasi.

