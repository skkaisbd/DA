#!/usr/bin/env bash
# Seed demo produksi LENGKAP (idempoten) — 1 perintah untuk seluruh rantai:
#   RnD -> Produksi Internal -> Gudang/WMS (Surat Jalan Internal BOM) ->
#   Maklon/CMT -> Vendor Portal -> Finance (AR + Invoice) + dokumen PDF.
#
# Urutan penting: produksi/maklon dulu (buat model/BOM/job), lalu RnD+WMS
# (RnD styles + Surat Jalan Internal 'Isi dari BOM' butuh job internal).
#
# Jalankan: bash /app/scripts/seed_demo_all.sh
set -e
cd /app/backend
echo "==================================================================="
echo " SEED DEMO PRODUKSI + MAKLON (internal, maklon, vendor, finance, PDF)"
echo "==================================================================="
python3 /app/tests/seed_demo_produksi_maklon.py
echo ""
echo "==================================================================="
echo " SEED DEMO RnD + WMS SURAT JALAN INTERNAL (BOM-driven / P4)"
echo "==================================================================="
python3 /app/tests/seed_demo_rnd_wms.py
echo ""
echo "==================================================================="
echo " SEED DEMO TAGIHAN CMT (pintu Invoice Produksi — PO internal ke CMT)"
echo "==================================================================="
python3 /app/scripts/seed_demo_cmt_billing_internal.py
echo ""
echo "==================================================================="
echo " MASTER VARIAN INTERNAL (PO Produksi internal butuh Warna × Size)"
echo "==================================================================="
python3 /app/scripts/seed_internal_variants.py
echo ""
echo "==================================================================="
echo " UNIFIKASI MASTER VENDOR CMT + MIGRASI PO MAKLON YATIM → SSOT PO"
echo "==================================================================="
python3 /app/scripts/migrate_unify_cmt_vendor_master.py
python3 /app/scripts/migrate_orphan_maklon_pos.py
echo ""
echo "==================================================================="
echo " DEMO PERMAK/REJECT MAKLON + ALUR QC PENERIMAAN CMT (on_qc → selesai)"
echo "==================================================================="
python3 /app/scripts/seed_maklon_permak_demo.py
python3 /app/scripts/seed_cmt_qc_flow_demo.py
echo ""
echo "==================================================================="
echo " DEMO SURAT JALAN BUYER GABUNGAN (2 PO 1 surat jalan — keluhan #6)"
echo "==================================================================="
python3 /app/scripts/seed_consolidated_buyer_shipment_demo.py
echo ""
echo "==================================================================="
echo " AUDIT RELASI: referensi vendor yatim + buku kuantitas (jaring pengaman)"
echo "==================================================================="
python3 /app/scripts/repair_orphan_vendor_refs.py
python3 /app/scripts/recompute_qty_ledger.py
# 2026-08-05 — seeder demo membuat dokumen dispatch ke buyer LANGSUNG di DB
# (tanpa melewati pipeline yang mengurangi stok FG), sehingga INV-18 selalu
# MERAH di container baru. Langkah ini menutupnya: stok FG hasil produksi
# ditambahkan bila belum tercatat, lalu mutasi keluar dijalankan.
# `--topup-fg` HANYA untuk data demo (lihat docstring skripnya).
python3 /app/scripts/repair_selisih_ssot.py --apply --topup-fg
echo ""
echo "==================================================================="
echo " SEED DEMO SELESAI — semua portal terisi data."
echo "  Login admin       : admin@garment.com / Admin@123"
echo "  Vendor CMT (JMC)  : cmtvendor@dewiaditya.id / Dewi@123"
echo "  Vendor CMT (RPK)  : cmtvendor2@dewiaditya.id / Dewi@123"
echo "  Klien maklon      : klienmaklon@dewiaditya.id / Dewi@123"
echo "==================================================================="
