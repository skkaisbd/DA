"""data/pdf_doc_registry.py — SATU katalog jenis dokumen PDF (SESI #19).

MENGAPA BERKAS INI ADA
----------------------
Sebelum sesi #19 katalog dokumen PDF tersebar di DUA tempat yang tidak saling tahu:

  1. `utils/pdf_common.SUPPORTED_PDF_DOCS` — 7 jenis SURAT (slip gaji, surat jalan,
     invoice maklon, SPP, …) beserta blok tanda tangannya. Dipakai layar
     "PDF: Surat & TTD" (`pdf_document_settings`).
  2. `routes/operations_pdf_configs.PDF_COLUMN_DEFINITIONS` — 13 jenis LAPORAN
     beserta daftar kolom tabelnya. Dipakai layar "PDF: Kolom Tabel"
     (`pdf_export_configs`).

Tiga jenis (`production-po`, `vendor-shipment`, `buyer-shipment-dispatch`) hidup di
KEDUA daftar dengan label berbeda, dan pemilik harus membuka DUA layar dengan UI/UX
berbeda untuk mengatur SATU dokumen yang sama — itulah keluhan pemilik:
"cek ada dua halaman berbeda ui ux-nya jelas".

Berkas ini menyatukan keduanya menjadi satu katalog: label, grup, orientasi halaman,
kolom tabel, field yang boleh dipakai sebagai nama penandatangan, blok tanda tangan
bawaan, dan CONTOH data untuk pratinjau. Ia adalah lapisan DATA (tanpa impor modul
lain di dalam backend) supaya tidak pernah terjadi impor berputar:

    data/pdf_doc_registry.py   ← tidak mengimpor apa pun dari backend
        ↑                ↑
    core/pdf_template.py   utils/pdf_common.py
        ↑                        ↑
    routes/pdf_templates.py   semua generator PDF
"""
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════════
# KOLOM TABEL PER JENIS DOKUMEN
# ═══════════════════════════════════════════════════════════════════════════════
# `required: True` = kolom yang menjadi tulang punggung dokumen (nomor urut, qty).
# Kolom wajib boleh DIPINDAH urutannya, tetapi tidak boleh disembunyikan: total dan
# penomoran baris dihitung dari kolom itu, dan dokumen tanpa qty bukan dokumen.
PDF_COLUMN_DEFINITIONS: dict[str, list[dict]] = {
    # ── SURAT / DOKUMEN OPERASIONAL ──────────────────────────────────────────
    'delivery-note': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'material_code', 'label': 'Kode Material'},
        {'key': 'description', 'label': 'Uraian Barang'},
        {'key': 'roll_no', 'label': 'No. Roll'},
        {'key': 'qty', 'label': 'Qty', 'required': True},
        {'key': 'unit', 'label': 'Satuan'},
        {'key': 'remarks', 'label': 'Keterangan'},
    ],
    'delivery-note-recap': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'sj_number', 'label': 'No. Surat Jalan'},
        {'key': 'source', 'label': 'Sumber'},
        {'key': 'type', 'label': 'Jenis'},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'destination', 'label': 'Tujuan'},
        {'key': 'reference', 'label': 'Acuan'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'lines', 'label': 'Baris'},
        {'key': 'qty', 'label': 'Total Qty', 'required': True},
    ],
    'payslip': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'component', 'label': 'Komponen'},
        {'key': 'type', 'label': 'Jenis'},
        {'key': 'note', 'label': 'Keterangan'},
        {'key': 'amount', 'label': 'Jumlah (Rp)', 'required': True},
    ],
    'invoice-maklon': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'description', 'label': 'Uraian'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'qty', 'label': 'Qty', 'required': True},
        {'key': 'unit', 'label': 'Satuan'},
        {'key': 'price', 'label': 'Harga Satuan'},
        {'key': 'amount', 'label': 'Jumlah'},
    ],
    'picklist': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'position_barcode', 'label': 'Barcode Posisi'},
        {'key': 'location', 'label': 'Lokasi'},
        {'key': 'material_code', 'label': 'Kode Material'},
        {'key': 'material_name', 'label': 'Nama Material'},
        {'key': 'qty', 'label': 'Qty Ambil', 'required': True},
        {'key': 'unit', 'label': 'Satuan'},
        {'key': 'checkbox', 'label': 'Pick'},
    ],
    'production-guide': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'step', 'label': 'Tahap'},
        {'key': 'description', 'label': 'Instruksi'},
        {'key': 'standard', 'label': 'Standar Mutu'},
    ],
    # ── LAPORAN & DOKUMEN PRODUKSI (dipindah dari operations_pdf_configs) ────
    'production-po': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Nama Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'qty', 'label': 'Qty', 'required': True},
        {'key': 'price', 'label': 'Harga Jual'},
        {'key': 'cmt', 'label': 'Harga CMT'},
    ],
    'vendor-shipment': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'po', 'label': 'No. PO'},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Nama Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'qty_sent', 'label': 'Qty Dikirim', 'required': True},
    ],
    'buyer-shipment-dispatch': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Nama Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'ordered', 'label': 'Qty Order'},
        {'key': 'this_dispatch', 'label': 'Kirim Ini', 'required': True},
        {'key': 'cumul_shipped', 'label': 'Kumulatif Terkirim'},
        {'key': 'remaining', 'label': 'Sisa'},
    ],
    # ── SURAT JALAN CMT → DA (W5, permintaan pemilik 2026-08-20) ─────────────
    # Satu penerimaan FG = satu surat jalan. Kolom hasil QC (`qty_received`,
    # `qty_reject`) DIDAFTARKAN sebagai PILIHAN supaya satu dokumen bisa dicetak
    # "sebelum QC" (hanya qty kirim) maupun "setelah QC" (kirim + lolos + reject)
    # tanpa membuat dua jenis dokumen yang bisa saling menyimpang.
    'cmt-delivery-note': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'product', 'label': 'Nama Produk'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'qty_sent', 'label': 'Qty Kirim', 'required': True},
        {'key': 'qty_received', 'label': 'Qty Terima (Lolos QC)'},
        {'key': 'qty_reject', 'label': 'Qty Reject'},
        {'key': 'notes', 'label': 'Keterangan'},
    ],
    'production-report': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'po', 'label': 'No. PO'},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Nama Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'qty', 'label': 'Qty'},
        {'key': 'price', 'label': 'Harga'},
        {'key': 'cmt', 'label': 'CMT'},
        {'key': 'vendor', 'label': 'Vendor'},
        {'key': 'produced', 'label': 'Diproduksi'},
        {'key': 'shipped', 'label': 'Dikirim'},
    ],
    'report-production': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'tanggal', 'label': 'Tanggal'},
        {'key': 'no_po', 'label': 'No PO'},
        {'key': 'no_seri', 'label': 'Serial'},
        {'key': 'nama_produk', 'label': 'Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'warna', 'label': 'Warna'},
        {'key': 'output_qty', 'label': 'Qty'},
        {'key': 'harga', 'label': 'Harga'},
        {'key': 'hpp', 'label': 'HPP/CMT'},
        {'key': 'garment', 'label': 'Vendor'},
        {'key': 'po_status', 'label': 'Status'},
    ],
    'report-progress': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'job_number', 'label': 'Job'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'serial_number', 'label': 'Serial'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'product_name', 'label': 'Produk'},
        {'key': 'qty_progress', 'label': 'Qty'},
        {'key': 'notes', 'label': 'Catatan'},
        {'key': 'recorded_by', 'label': 'Dicatat oleh'},
    ],
    'report-financial': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'invoice_number', 'label': 'No. Invoice'},
        {'key': 'category', 'label': 'Kategori'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'vendor_or_buyer', 'label': 'Vendor/Buyer'},
        {'key': 'amount', 'label': 'Nilai'},
        {'key': 'paid', 'label': 'Dibayar'},
        {'key': 'remaining', 'label': 'Sisa'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'date', 'label': 'Tanggal'},
    ],
    'report-shipment': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'direction', 'label': 'Arah'},
        {'key': 'shipment_number', 'label': 'No. Kiriman'},
        {'key': 'shipment_type', 'label': 'Jenis'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'inspection', 'label': 'Inspeksi'},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'items', 'label': 'Item'},
    ],
    'report-defect': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'product_name', 'label': 'Produk'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'defect_qty', 'label': 'Qty Defect'},
        {'key': 'defect_type', 'label': 'Tipe'},
        {'key': 'description', 'label': 'Deskripsi'},
        {'key': 'status', 'label': 'Status'},
    ],
    'report-return': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'return_number', 'label': 'No. Retur'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'customer_name', 'label': 'Customer'},
        {'key': 'return_date', 'label': 'Tanggal'},
        {'key': 'total_qty', 'label': 'Total Qty'},
        {'key': 'item_count', 'label': 'Item'},
        {'key': 'reason', 'label': 'Alasan'},
        {'key': 'status', 'label': 'Status'},
    ],
    'report-missing-material': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'request_number', 'label': 'No. Permintaan'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'reason', 'label': 'Alasan'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'child_shipment', 'label': 'Kiriman Anak'},
        {'key': 'date', 'label': 'Tanggal'},
    ],
    'report-replacement': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'request_number', 'label': 'No. Permintaan'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'reason', 'label': 'Alasan'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'child_shipment', 'label': 'Kiriman Anak'},
        {'key': 'date', 'label': 'Tanggal'},
    ],
    'report-accessory': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'shipment_number', 'label': 'No. Kiriman'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'accessory_name', 'label': 'Aksesoris'},
        {'key': 'accessory_code', 'label': 'Kode'},
        {'key': 'qty_sent', 'label': 'Qty'},
        {'key': 'unit', 'label': 'Satuan'},
        {'key': 'status', 'label': 'Status'},
    ],
}


# Bobot lebar kolom BAWAAN (relatif). Dipakai bila pemilik belum menyetel lebar
# sendiri di editor. Ditulis di sini supaya tabel bawaan sudah proporsional —
# tanpa ini semua kolom rata dan kolom "Uraian" melipat jadi tiga baris sementara
# kolom "Satuan" kelebaran (terlihat di pratinjau pertama sesi #19).
DEFAULT_COLUMN_WEIGHTS: dict[str, dict] = {'delivery-note': {'no': 0.6, 'material_code': 1.2, 'description': 3.0, 'roll_no': 1.4, 'qty': 0.8, 'unit': 0.7, 'remarks': 1.6},
    'delivery-note-recap': {'no': 0.6, 'sj_number': 1.8, 'source': 0.9, 'type': 1.2, 'date': 0.9, 'destination': 2.0, 'reference': 1.5, 'status': 1.0, 'lines': 0.6, 'qty': 0.9},
    'payslip': {'no': 0.6, 'component': 2.4, 'type': 1.0, 'note': 2.2, 'amount': 1.3},
    'invoice-maklon': {'no': 0.6, 'description': 3.0, 'sku': 1.2, 'qty': 0.7, 'unit': 0.7, 'price': 1.3, 'amount': 1.4},
    'picklist': {'no': 0.6, 'position_barcode': 1.5, 'location': 1.4, 'material_code': 1.3, 'material_name': 2.8, 'qty': 0.8, 'unit': 0.7, 'checkbox': 0.7},
    'production-guide': {'no': 0.6, 'step': 1.0, 'description': 3.4, 'standard': 2.0},
    'production-po': {'no': 0.6, 'serial': 1.4, 'product': 2.6, 'sku': 1.4, 'size': 0.7, 'color': 1.0, 'qty': 0.8, 'price': 1.3, 'cmt': 1.3},
    'vendor-shipment': {'no': 0.6, 'po': 1.4, 'serial': 1.4, 'product': 2.6, 'sku': 1.4, 'size': 0.7, 'color': 1.0, 'qty_sent': 1.0},
    'buyer-shipment-dispatch': {'no': 0.6, 'serial': 1.4, 'product': 2.4, 'sku': 1.3, 'size': 0.7, 'color': 1.0, 'ordered': 0.9, 'this_dispatch': 1.0, 'cumul_shipped': 1.2, 'remaining': 0.9},
    'cmt-delivery-note': {'no': 0.5, 'serial': 1.3, 'sku': 1.4, 'product': 2.6, 'size': 0.7,
                          'color': 1.0, 'qty_sent': 1.0, 'qty_received': 1.2,
                          'qty_reject': 0.9, 'notes': 1.8}}


def weights_of(doc_key: str) -> dict:
    """Bobot lebar bawaan per kolom untuk satu jenis dokumen (kosong = rata)."""
    return dict(DEFAULT_COLUMN_WEIGHTS.get(doc_key, {}))


# ═══════════════════════════════════════════════════════════════════════════════
# JENIS SURAT + BLOK TANDA TANGAN
# ═══════════════════════════════════════════════════════════════════════════════
# Struktur satu blok tanda tangan (permintaan pemilik, sesi #19):
#     ATAS   = `subject`  → judul blok yang bisa diganti ("Penerima", "Pengirim", …)
#     TENGAH = ruang kosong untuk tanda tangan basah
#     BAWAH  = `nama`     → dari `custom_name`, dari field data (`field_key`),
#                            atau DIKOSONGKAN (garis titik-titik) agar ditulis tangan
#     `note` = keterangan kecil di bawah nama (jabatan/pihak)
#
# `name_source`: 'custom' | 'field' | 'blank'
SUPPORTED_PDF_DOCS: dict[str, dict] = {
    "payslip": {
        "label": "Slip Gaji (Payslip)",
        "group": "SDM & Penggajian",
        "page": "portrait",
        "title": "SLIP GAJI KARYAWAN",
        "available_fields": [
            {"key": "employee_name", "label": "Nama Karyawan"},
            {"key": "employee_code", "label": "Kode/ID Karyawan"},
            {"key": "run_number", "label": "No. Run Payroll"},
            {"key": "approved_by", "label": "Disetujui oleh (run)"},
        ],
        "default_signatures": [
            {"subject": "Disetujui oleh", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "HRD / Finance"},
            {"subject": "Diterima oleh", "name_source": "field", "custom_name": "",
             "field_key": "employee_name", "note": "Karyawan"},
        ],
    },
    "delivery-note": {
        "label": "Surat Jalan Gudang",
        "group": "Gudang & Logistik",
        "page": "portrait",
        "title": "SURAT JALAN",
        "available_fields": [
            {"key": "issued_by", "label": "Diterbitkan oleh"},
            {"key": "recipient_name", "label": "Nama Penerima (tujuan)"},
            {"key": "driver_name", "label": "Nama Sopir"},
            {"key": "sj_number", "label": "No. Surat Jalan"},
        ],
        "default_signatures": [
            {"subject": "Pengirim", "name_source": "field", "custom_name": "",
             "field_key": "issued_by", "note": "Gudang"},
            {"subject": "Pengangkut / Sopir", "name_source": "blank", "custom_name": "",
             "field_key": "driver_name", "note": "Ekspedisi"},
            {"subject": "Penerima", "name_source": "blank", "custom_name": "",
             "field_key": "recipient_name", "note": "Penerima"},
        ],
    },
    "delivery-note-recap": {
        "label": "Rekap Surat Jalan (Lintas Sumber)",
        "group": "Gudang & Logistik",
        "page": "landscape",
        "title": "REKAP SURAT JALAN",
        "available_fields": [
            {"key": "printed_by", "label": "Dicetak oleh"},
        ],
        "default_signatures": [
            {"subject": "Dibuat oleh", "name_source": "field", "custom_name": "",
             "field_key": "printed_by", "note": "Admin Gudang"},
            {"subject": "Diperiksa oleh", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Supervisor"},
        ],
    },
    "picklist": {
        "label": "Pick List Gudang",
        "group": "Gudang & Logistik",
        "page": "portrait",
        "title": "PICK LIST",
        "available_fields": [
            {"key": "assignee_name", "label": "Nama Operator (picker)"},
            {"key": "ref_number", "label": "No. Pick List"},
        ],
        "default_signatures": [
            {"subject": "Picker", "name_source": "field", "custom_name": "",
             "field_key": "assignee_name", "note": "Nama & TTD"},
            {"subject": "Checker", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Nama & TTD"},
            {"subject": "Diterima oleh", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Nama & TTD"},
        ],
    },
    "invoice-maklon": {
        "label": "Invoice Maklon",
        "group": "Keuangan",
        "page": "portrait",
        "title": "INVOICE",
        "available_fields": [
            {"key": "client_name", "label": "Nama Klien"},
            {"key": "invoice_number", "label": "No. Invoice"},
        ],
        "default_signatures": [
            {"subject": "Hormat kami", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "Finance"},
        ],
    },
    "vendor-shipment": {
        "label": "Surat Jalan Vendor (Kirim Material)",
        "group": "Produksi",
        "page": "portrait",
        "title": "SURAT JALAN MATERIAL",
        "available_fields": [
            {"key": "vendor_name", "label": "Nama Vendor"},
            {"key": "shipment_number", "label": "No. Pengiriman"},
        ],
        "default_signatures": [
            {"subject": "Pengirim", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "Produksi"},
            {"subject": "Penerima", "name_source": "field", "custom_name": "",
             "field_key": "vendor_name", "note": "Vendor"},
        ],
    },
    "buyer-shipment-dispatch": {
        "label": "Surat Jalan Buyer (Dispatch)",
        "group": "Produksi",
        "page": "portrait",
        "title": "SURAT JALAN PENGIRIMAN",
        "available_fields": [
            {"key": "buyer_name", "label": "Nama Buyer"},
            {"key": "shipment_number", "label": "No. Pengiriman"},
        ],
        "default_signatures": [
            {"subject": "Pengirim", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "Produksi"},
            {"subject": "Penerima", "name_source": "field", "custom_name": "",
             "field_key": "buyer_name", "note": "Buyer"},
        ],
    },
    "cmt-delivery-note": {
        "label": "Surat Jalan CMT → DA (Terima FG)",
        "group": "Produksi",
        "page": "landscape",
        "title": "SURAT JALAN — PENGIRIMAN BARANG JADI DARI CMT KE DA",
        "available_fields": [
            {"key": "cmt_name", "label": "Nama Vendor CMT"},
            {"key": "dn_number", "label": "No. Surat Jalan"},
            {"key": "receipt_code", "label": "No. Penerimaan FG"},
            {"key": "po_number", "label": "No. PO"},
        ],
        "default_signatures": [
            {"subject": "Pengirim", "name_source": "field", "custom_name": "",
             "field_key": "cmt_name", "note": "Vendor CMT"},
            {"subject": "Pemeriksa QC", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "QC DA"},
            {"subject": "Penerima", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Gudang DA"},
        ],
    },
    "production-po": {
        "label": "Surat Perintah Produksi (SPP)",
        "group": "Produksi",
        "page": "landscape",
        "title": "SURAT PERINTAH PRODUKSI (SPP)",
        "available_fields": [
            {"key": "vendor_name", "label": "Nama Vendor/CMT"},
            {"key": "po_number", "label": "No. PO"},
        ],
        "default_signatures": [
            {"subject": "Dibuat oleh", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "PPIC / Produksi"},
            {"subject": "Disetujui oleh", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "Manajer Produksi"},
            {"subject": "Pelaksana", "name_source": "field", "custom_name": "",
             "field_key": "vendor_name", "note": "Vendor/CMT"},
        ],
    },
    "production-guide": {
        "label": "Panduan Produk & Proses (SOP)",
        "group": "Produksi",
        "page": "portrait",
        "title": "PANDUAN PRODUK & PROSES PRODUKSI",
        "available_fields": [
            {"key": "vendor_name", "label": "Nama Vendor/CMT"},
            {"key": "shipment_number", "label": "No. Pengiriman"},
        ],
        "default_signatures": [
            {"subject": "Disiapkan oleh", "name_source": "custom", "custom_name": "",
             "field_key": "", "note": "PPIC / RnD"},
            {"subject": "Diterima & dipahami oleh", "name_source": "field",
             "custom_name": "", "field_key": "vendor_name", "note": "Vendor/CMT"},
        ],
    },
    "production-report": {
        "label": "Laporan Produksi Lengkap",
        "group": "Laporan",
        "page": "landscape",
        "title": "LAPORAN PRODUKSI",
        "available_fields": [{"key": "printed_by", "label": "Dicetak oleh"}],
        "default_signatures": [
            {"subject": "Dibuat oleh", "name_source": "field", "custom_name": "",
             "field_key": "printed_by", "note": "Admin"},
            {"subject": "Disetujui oleh", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Manajer"},
        ],
    },
}

# Laporan-laporan (report-*) memakai pola tanda tangan & judul yang sama; didaftarkan
# secara terprogram supaya tidak ada 9 blok teks kembar yang bisa saling menyimpang.
_REPORT_LABELS = {
    "report-production": "Laporan: Produksi",
    "report-progress": "Laporan: Progres",
    "report-financial": "Laporan: Keuangan",
    "report-shipment": "Laporan: Pengiriman",
    "report-defect": "Laporan: Defect",
    "report-return": "Laporan: Retur",
    "report-missing-material": "Laporan: Material Kurang",
    "report-replacement": "Laporan: Barang Pengganti",
    "report-accessory": "Laporan: Aksesoris",
}
for _k, _label in _REPORT_LABELS.items():
    SUPPORTED_PDF_DOCS[_k] = {
        "label": _label,
        "group": "Laporan",
        "page": "landscape",
        "title": _label.replace("Laporan: ", "LAPORAN ").upper(),
        "available_fields": [{"key": "printed_by", "label": "Dicetak oleh"}],
        "default_signatures": [
            {"subject": "Dibuat oleh", "name_source": "field", "custom_name": "",
             "field_key": "printed_by", "note": "Admin"},
            {"subject": "Disetujui oleh", "name_source": "blank", "custom_name": "",
             "field_key": "", "note": "Manajer"},
        ],
    }


DEFAULT_DOC_SETTINGS = {
    "show_logo": True,
    "show_signatures": True,
    "header_line1": "",   # kosong = pakai company_name dari profil perusahaan
    "header_line2": "",   # kosong = pakai alamat/tagline
    "footer_text": "",
}

GROUP_ORDER = ["Gudang & Logistik", "Produksi", "Keuangan", "SDM & Penggajian", "Laporan"]


# ── KOLOM YANG BENAR-BENAR DITEGAKKAN GENERATOR ───────────────────────────────
# SESI #19 — daftar ini bukan hiasan: layar editor MENYEMBUNYIKAN penyunting kolom
# untuk jenis yang generatornya masih memakai daftar kolom bawaan kode. Menampilkan
# penyunting kolom yang tidak berlaku sama buruknya dengan setelan penomoran yang
# tidak ditegakkan (sesi #18): pemilik mengira sudah mengubah sesuatu, padahal tidak.
# Penjaga INV-F26/P9 memeriksa bahwa setiap kunci di sini BENAR-BENAR melewati
# `tpl_table_parts`/`apply_columns` di jalur cetaknya.
COLUMNS_ENFORCED: dict[str, str] = {
    "delivery-note": "backend/routes/wms_delivery_notes.py",
    "delivery-note-recap": "backend/routes/wms_delivery_notes.py",
    "picklist": "backend/routes/wms_picklist.py",
    "invoice-maklon": "backend/utils/invoice_pdf.py",
    "production-po": "backend/routes/operations_pdf.py",
    "vendor-shipment": "backend/routes/operations_pdf.py",
    "buyer-shipment-dispatch": "backend/routes/operations_pdf.py",
    "cmt-delivery-note": "backend/routes/operations_pdf.py",
    "production-report": "backend/routes/operations_pdf.py",
    "report-production": "backend/routes/operations_pdf.py",
    "report-progress": "backend/routes/operations_pdf.py",
    "report-financial": "backend/routes/operations_pdf.py",
    "report-shipment": "backend/routes/operations_pdf.py",
    "report-defect": "backend/routes/operations_pdf.py",
    "report-return": "backend/routes/operations_pdf.py",
    "report-missing-material": "backend/routes/operations_pdf.py",
    "report-replacement": "backend/routes/operations_pdf.py",
    "report-accessory": "backend/routes/operations_pdf.py",
}

# Alasan jujur untuk jenis yang kolomnya BELUM bisa diatur (ditampilkan di layar).
COLUMNS_NOT_ENFORCED_REASON: dict[str, str] = {
    "payslip": ("Slip gaji memakai tata letak A5 khusus (kotak pendapatan/potongan, "
                "blok gaji bersih, watermark RAHASIA) yang tidak berbentuk satu tabel "
                "kolom. Kop, tanda tangan, dan footer-nya TETAP mengikuti template."),
    "production-guide": ("Panduan produksi berisi bagian naratif + foto per model, "
                         "bukan satu tabel kolom. Kop, tanda tangan, dan footer-nya "
                         "TETAP mengikuti template."),
}


def columns_enforced(doc_key: str) -> bool:
    return doc_key in COLUMNS_ENFORCED


def columns_note(doc_key: str) -> str:
    return COLUMNS_NOT_ENFORCED_REASON.get(doc_key, "")


def doc_keys() -> list[str]:
    return list(SUPPORTED_PDF_DOCS.keys())


def spec(doc_key: str) -> dict:
    return SUPPORTED_PDF_DOCS.get(doc_key, {})


def columns_of(doc_key: str) -> list[dict]:
    """Kolom bawaan satu jenis dokumen (list kosong = dokumen tanpa tabel diatur)."""
    return [dict(c) for c in PDF_COLUMN_DEFINITIONS.get(doc_key, [])]


def required_keys(doc_key: str) -> list[str]:
    return [c["key"] for c in PDF_COLUMN_DEFINITIONS.get(doc_key, []) if c.get("required")]


def page_of(doc_key: str) -> str:
    return spec(doc_key).get("page", "portrait")


def default_signatures(doc_key: str) -> list[dict]:
    return [dict(s) for s in spec(doc_key).get("default_signatures", [])]


# ── CONTOH DATA UNTUK PRATINJAU ───────────────────────────────────────────────
# Pratinjau HARUS memakai data contoh, bukan dokumen sungguhan: pemilik sedang
# menyetel template, bukan membuka arsip — dan pratinjau tidak boleh bergantung
# pada ada/tidaknya dokumen nyata (di basis data baru, dokumennya belum ada).
_SAMPLE_VALUES = {
    "no": lambda i: str(i),
    "qty": lambda i: f"{i * 12}",
    "qty_sent": lambda i: f"{i * 12}",
    "qty_received": lambda i: f"{i * 12 - 1}",
    "qty_reject": lambda i: "1",
    "qty_to_pick": lambda i: f"{i * 12}",
    "qty_progress": lambda i: f"{i * 12}",
    "output_qty": lambda i: f"{i * 12}",
    "total_qty": lambda i: f"{i * 24}",
    "this_dispatch": lambda i: f"{i * 6}",
    "cumul_shipped": lambda i: f"{i * 10}",
    "ordered": lambda i: f"{i * 20}",
    "remaining": lambda i: f"{i * 4}",
    "defect_qty": lambda i: str(i),
    "item_count": lambda i: str(i + 1),
    "items": lambda i: str(i + 1),
    "lines": lambda i: str(i + 1),
    "sku": lambda i: f"SKU-{1000 + i}",
    "serial": lambda i: f"SN-{2026}{i:04d}",
    "no_seri": lambda i: f"SN-{2026}{i:04d}",
    "serial_number": lambda i: f"SN-{2026}{i:04d}",
    "product": lambda i: "Kaos Katun Combed 30s Lengan Pendek",
    "nama_produk": lambda i: "Kaos Katun Combed 30s Lengan Pendek",
    "product_name": lambda i: "Kaos Katun Combed 30s Lengan Pendek",
    "description": lambda i: "Kain katun combed 30s warna navy",
    "material_name": lambda i: "Kain Katun Combed 30s",
    "component": lambda i: ["Gaji Pokok", "Tunjangan Makan", "Lembur", "BPJS (potongan)"][(i - 1) % 4],
    "type": lambda i: "Pendapatan" if i % 4 else "Potongan",
    "amount": lambda i: f"{i * 1250000:,}".replace(",", "."),
    "price": lambda i: f"{i * 25000:,}".replace(",", "."),
    "harga": lambda i: f"{i * 25000:,}".replace(",", "."),
    "cmt": lambda i: f"{i * 8000:,}".replace(",", "."),
    "hpp": lambda i: f"{i * 8000:,}".replace(",", "."),
    "paid": lambda i: f"{i * 1000000:,}".replace(",", "."),
    "size": lambda i: ["S", "M", "L", "XL"][(i - 1) % 4],
    "color": lambda i: ["Navy", "Hitam", "Putih", "Maroon"][(i - 1) % 4],
    "warna": lambda i: ["Navy", "Hitam", "Putih", "Maroon"][(i - 1) % 4],
    "unit": lambda i: "pcs",
    "material_code": lambda i: f"MAT-{100 + i}",
    "accessory_code": lambda i: f"ACC-{100 + i}",
    "accessory_name": lambda i: "Label Woven",
    "roll_no": lambda i: f"RL-202608-{i:04d}",
    "position_barcode": lambda i: f"A1-Z{i}-R0{i}",
    "location": lambda i: f"GD1/Z{i}/RAK-0{i}",
    "checkbox": lambda i: "( )",
    "remarks": lambda i: "-",
    "notes": lambda i: "-",
    "note": lambda i: "-",
    "reason": lambda i: "Kurang kirim",
    "status": lambda i: ["Draft", "Dikirim", "Diterima", "Selesai"][(i - 1) % 4],
    "po_status": lambda i: "Berjalan",
    "date": lambda i: f"{i:02d}/08/2026",
    "tanggal": lambda i: f"{i:02d}/08/2026",
    "return_date": lambda i: f"{i:02d}/08/2026",
    "po": lambda i: f"PO-INT-202608-000{i}",
    "po_number": lambda i: f"PO-INT-202608-000{i}",
    "no_po": lambda i: f"PO-INT-202608-000{i}",
    "job_number": lambda i: f"JOB-000{i}",
    "invoice_number": lambda i: f"INV-MKL-2026-000{i}",
    "request_number": lambda i: f"REQ-202608-000{i}",
    "return_number": lambda i: f"RET-202608-000{i}",
    "shipment_number": lambda i: f"SHP-202608-000{i}",
    "sj_number": lambda i: f"SJ-INTERNAL/2026/08/000{i}",
    "vendor": lambda i: "CV Jahit Mitra CMT",
    "vendor_name": lambda i: "CV Jahit Mitra CMT",
    "garment": lambda i: "CV Jahit Mitra CMT",
    "customer_name": lambda i: "PT Aruna Activewear",
    "vendor_or_buyer": lambda i: "PT Aruna Activewear",
    "buyer_name": lambda i: "PT Aruna Activewear",
    "destination": lambda i: "Gudang Lantai 2",
    "source": lambda i: "Gudang",
    "reference": lambda i: f"PO-INT-202608-000{i}",
    "recorded_by": lambda i: "Admin Gudang",
    "printed_by": lambda i: "Admin Gudang",
    "child_shipment": lambda i: "-",
    "direction": lambda i: "Keluar",
    "shipment_type": lambda i: "Normal",
    "inspection": lambda i: "Lulus",
    "category": lambda i: "Piutang",
    "defect_type": lambda i: "Jahitan",
    "produced": lambda i: f"{i * 12}",
    "shipped": lambda i: f"{i * 10}",
    "step": lambda i: f"Tahap {i}",
    "standard": lambda i: "Toleransi ±1 cm",
}


def sample_value(key: str, i: int) -> str:
    fn = _SAMPLE_VALUES.get(key)
    if fn:
        return str(fn(i))
    return f"Contoh {i}"


def sample_rows(doc_key: str, keys: list[str], n: int = 4) -> list[list[str]]:
    """Baris contoh untuk pratinjau — nilainya mengikuti ARTI kolomnya."""
    return [[sample_value(k, i) for k in keys] for i in range(1, n + 1)]


def sample_info(doc_key: str) -> list[tuple]:
    """Pasangan info (label, nilai) contoh di bawah kop surat."""
    sp = spec(doc_key)
    base = [
        ("Nomor Dokumen", sample_value("sj_number" if "delivery" in doc_key else "po_number", 1)),
        ("Tanggal", "17/08/2026"),
    ]
    if doc_key == "payslip":
        base = [("Nama Karyawan", "Siti Rahayu"), ("Kode Karyawan", "EMP-0142"),
                ("Periode", "Agustus 2026"), ("Jabatan", "Operator Jahit")]
    elif doc_key == "picklist":
        base = [("No. Pick List", "PL-202608-0007"), ("Operator", "Budi Santoso"),
                ("Sumber", "PO-INT-202608-0001"), ("Total", "4 item · 120 pcs")]
    elif doc_key == "invoice-maklon":
        base = [("No. Invoice", "INV-MKL-2026-0007"), ("Klien", "PT Aruna Activewear"),
                ("Tanggal", "17/08/2026"), ("Jatuh Tempo", "31/08/2026")]
    elif doc_key in ("delivery-note", "vendor-shipment", "buyer-shipment-dispatch"):
        base = [("No. Surat Jalan", sample_value("sj_number", 1)), ("Tanggal", "17/08/2026"),
                ("Tujuan", "CV Jahit Mitra CMT"), ("No. Kendaraan", "B 9021 XYZ")]
    elif doc_key == "production-po":
        base = [("No. PO", "PO-INT-202608-0001"), ("Customer", "PT Aruna Activewear"),
                ("Vendor/CMT", "CV Jahit Mitra CMT"), ("Deadline", "31/08/2026")]
    return base + ([("Jenis Dokumen", sp.get("label", doc_key))] if sp.get("label") else [])


def sample_context(doc_key: str) -> dict:
    """Konteks contoh untuk nama penandatangan (name_source='field')."""
    return {
        "employee_name": "Siti Rahayu", "employee_code": "EMP-0142",
        "run_number": "PAY-202608-0001", "approved_by": "Dewi Aditya",
        "issued_by": "Admin Gudang", "recipient_name": "CV Jahit Mitra CMT",
        "driver_name": "Budi Santoso", "sj_number": sample_value("sj_number", 1),
        "client_name": "PT Aruna Activewear", "invoice_number": "INV-MKL-2026-0007",
        "vendor_name": "CV Jahit Mitra CMT", "buyer_name": "PT Aruna Activewear",
        "shipment_number": "SHP-202608-0001", "po_number": "PO-INT-202608-0001",
        "assignee_name": "Budi Santoso", "ref_number": "PL-202608-0007",
        "printed_by": "Admin Gudang",
    }


def catalog() -> list[dict]:
    """Katalog lengkap untuk layar editor: label, grup, kolom, field TTD, TTD bawaan."""
    out = []
    for key, sp in SUPPORTED_PDF_DOCS.items():
        out.append({
            "doc_key": key,
            "label": sp.get("label", key),
            "group": sp.get("group", "Lainnya"),
            "page": sp.get("page", "portrait"),
            "title": sp.get("title", sp.get("label", key)),
            "columns": columns_of(key),
            "required_keys": required_keys(key),
            "columns_enforced": columns_enforced(key),
            "columns_note": columns_note(key),
            "available_fields": sp.get("available_fields", []),
            "default_signatures": default_signatures(key),
        })
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    out.sort(key=lambda d: (order.get(d["group"], 99), d["label"]))
    return out


def doc_types_catalog() -> list:
    """Bentuk LAMA katalog (dipakai `/api/pdf-doc-settings/doc-types`).

    Dipertahankan supaya layar/skrip lama tidak pecah saat layar baru dirilis;
    isinya diturunkan dari katalog yang sama (bukan salinan kedua).
    """
    return [
        {
            "doc_type": key,
            "label": sp.get("label", key),
            "group": sp.get("group", "Lainnya"),
            "available_fields": sp.get("available_fields", []),
            "default_signatures": [
                {"key": s.get("key", ""), "label": s.get("subject", ""),
                 "name_source": s.get("name_source", "blank"),
                 "custom_name": s.get("custom_name", ""),
                 "field_key": s.get("field_key", ""),
                 "role_label": s.get("note", "")}
                for s in sp.get("default_signatures", [])
            ],
        }
        for key, sp in SUPPORTED_PDF_DOCS.items()
    ]
