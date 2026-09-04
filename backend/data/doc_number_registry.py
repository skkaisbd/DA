"""Katalog jenis dokumen yang nomornya BISA dikonfigurasi owner.

Sumber kebenaran daftar ini = pemetaan `scripts/map_document_numbers.py`
(semua pemanggilan `utils.counters.gen_prefixed_number`). Menambah entri di
sini TIDAK membuat generator baru — hanya memberi label & format bawaan untuk
layar konfigurasi. Kunci = "<koleksi>.<field>".

Token yang tersedia untuk SEMUA jenis:
    {YYYY} {YY} {MM} {DD}  → tanggal pembuatan dokumen
    {SEQ:n}                → nomor urut, n = jumlah digit (WAJIB, harus di akhir)
Token khusus per jenis ada di kolom `tokens`.
"""

DOC_NUMBER_REGISTRY = [
    # ── GUDANG ────────────────────────────────────────────────────────────────
    # FASE H-5 (2026-08-16) — entri BARU 'Roll Kain'. Nomor roll dulu WAJIB
    # DIKETIK (`RollIn.roll_no`), padahal roll adalah barang fisik yang datang
    # belasan sekaligus: nomor ketikan membuat dua gulungan bisa bernomor sama dan
    # tidak ada yang bisa membuktikan gulungan mana yang dipotong. Mode `auto`
    # menjadi bawaan — roll lahir dari penerimaan barang, bukan dari ketikan.
    {"key": "wh_fabric_rolls.roll_no", "label": "Roll Kain", "group": "Gudang",
     "auto_only": True,
     "alasan_otomatis": 'Nomor gulungan lahir dari rincian roll pada PENERIMAAN kain '
                        '(Fase H-5) — satu penerimaan melahirkan belasan gulungan '
                        'sekaligus, jadi nomornya tidak diketik orang. Formatnya tetap '
                        'bisa diatur.',
     "default_format": "RL-{YYYY}{MM}-{SEQ:4}", "tokens": [], "default_mode": "auto",
     "catatan": "Dibuat otomatis saat penerimaan kain (rincian roll per gulungan). "
                "SESI #27: dulu ditandai 'ditegakkan' padahal TIDAK ADA satu pun layar "
                "yang bisa mengetik nomor roll — bila owner memilih MANUAL, penerimaan "
                "kain justru GAGAL meminta nomor yang tak punya kolom di form."},
    # SESI #19 (2026-08-17) — Surat Jalan Gudang DITEGAKKAN. Nomor SJ gudang selama
    # ini 100% otomatis dan kolom nomornya tidak pernah ada di form, sehingga owner
    # yang memindah setelan ke MANUAL tidak melihat perubahan apa pun.
    # `default_mode: auto` menjaga perilaku hari ini APA ADANYA.
    # PENTING: surat jalan yang LAHIR TANPA MANUSIA tetap bernomor otomatis, yaitu
    # SJ-CMT yang dibuat `routes/wms_cmt_dispatches.py::execute_dispatch` — tidak ada
    # orang di layar itu yang bisa mengetik nomor, jadi mode MANUAL tidak berlaku
    # untuknya (formatnya tetap mengikuti setelan ini).
    {"key": "wh_delivery_notes.sj_number", "label": "Surat Jalan Gudang", "group": "Gudang",
     "policy_enforced": True,
     "default_format": "{TIPE}/{YYYY}/{MM}/{SEQ:4}", "tokens": ["TIPE"],
     "default_mode": "auto",
     "catatan": "TIPE = jenis surat jalan (SJ-CMT, SJ-MAKLON, SJ-SUPPLIER, SJ-INTERNAL, "
                "SJ-ONLINE). Mode MANUAL berlaku untuk surat jalan yang dibuat orang di "
                "layar Gudang; SJ-CMT yang lahir otomatis dari Kirim Material ke CMT tetap "
                "bernomor otomatis."},
    {"key": "wh_cmt_dispatches.dispatch_no", "label": "Pengiriman ke CMT", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir otomatis saat pengiriman ke CMT dieksekusi — tidak ada layar tempat nomor ini bisa diketik.',
     "default_format": "CMD/{YYYY}/{MM}/{SEQ:4}", "tokens": []},
    {"key": "wh_returns.return_code", "label": "Retur Gudang", "group": "Gudang",
     "policy_enforced": True, "default_mode": "auto",
     "default_format": "WH-RET-{SEQ:5}", "tokens": []},
    {"key": "wh_opname_sessions2.session_no", "label": "Sesi Opname (Aksesoris)", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir saat sesi opname aksesoris dimulai.',
     "default_format": "OPNAME-{SEQ:4}", "tokens": []},
    {"key": "wh_opname3_sessions.session_no", "label": "Sesi Opname (Gudang)", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir saat sesi opname gudang dimulai.',
     "default_format": "OPN-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "rahaza_grn_inspections.inspection_no", "label": "Inspeksi Penerimaan", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir otomatis saat barang masuk diperiksa (QC penerimaan).',
     "default_format": "INS-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "rahaza_material_issues.mi_number", "label": "Pengeluaran Material", "group": "Gudang",
     "policy_enforced": True, "default_mode": "auto",
     "default_format": "MI-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "warehouse_receiving.receipt_number", "label": "Penerimaan Barang (GR)", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir otomatis saat PO pembelian diterima gudang.',
     "default_format": "GR-{SEQ:5}", "tokens": [],
     "catatan": "Dibuat otomatis saat PO pembelian diterima di gudang."},
    {"key": "rahaza_fg_issues.issue_number", "label": "Pengeluaran Barang Jadi", "group": "Gudang",
     "policy_enforced": True,
     "default_format": "FGI-{YYYY}{MM}{DD}-{SEQ:4}", "tokens": []},
    {"key": "rahaza_fg_reservations.reservation_no", "label": "Reservasi Barang Jadi", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Lahir saat barang jadi dipesan dari matriks FG.',
     "default_format": "RES-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "rahaza_shipments.shipment_number", "label": "Pengiriman", "group": "Gudang",
     "auto_only": True, "alasan_otomatis": 'Koleksi warisan (SSOT surat jalan pindah ke Gudang) — tidak ada layar penulisnya.',
     "default_format": "SHP-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},

    # ── PENGADAAN ─────────────────────────────────────────────────────────────
    # SESI #19 (2026-08-17) — PR Pengadaan DITEGAKKAN (permintaan owner).
    {"key": "dewi_procurement_requests.request_number", "label": "Permintaan Pengadaan (PR)", "group": "Pengadaan",
     "policy_enforced": True,
     "default_format": "PR-{YYYY}{MM}-{SEQ:4}", "tokens": [], "default_mode": "auto",
     "catatan": "Mode MANUAL: nomor PR diketik pemohon tetapi wajib mengikuti pola ini."},
    {"key": "rahaza_purchase_orders.po_number", "label": "Purchase Order (PO)", "group": "Pengadaan",
     "policy_enforced": True, "default_mode": "auto",
     "default_format": "PO-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "acc_purchase_requests.pr_number", "label": "Permintaan Beli Aksesoris", "group": "Pengadaan",
     "policy_enforced": True,
     "default_format": "ACC-PR-{SEQ:4}", "tokens": []},

    # ── PRODUKSI & MAKLON ─────────────────────────────────────────────────────
    # FASE G (2026-08-16) — DUA entri di bawah BARU. Nomor PO produksi (sumber
    # nomor SPP) selama ini 100% diketik tangan: `create_po_internal()` menolak
    # permintaan tanpa `po_number` dan menyimpan apa pun yang dikirim. Isinya
    # sekarang bercampur bebas (`PO-INT-DEMO-1`, `PO-MK-DEMO-1`, `PO-MKL-GAB-A`).
    # `default_mode: manual` menjaga perilaku hari ini APA ADANYA — yang berubah
    # hanyalah nomor manual wajib mengikuti polanya, dan owner boleh memindah ke
    # OTOMATIS kapan pun dari layar Penomoran Dokumen.
    # Satu koleksi+field menampung dua jenis dokumen (internal vs maklon) ⇒ kunci
    # kedua memakai override `collection`/`field` seperti pola invoice AR.
    {"key": "production_pos.po_number", "label": "PO Produksi Internal (SPP)", "group": "Produksi",
     "policy_enforced": True,
     "default_format": "PO-INT-{YYYY}{MM}-{SEQ:4}", "tokens": [], "default_mode": "manual",
     "catatan": "Dipakai juga sebagai nomor SPP. Mode manual = nomor diketik tetapi "
                "wajib mengikuti pola ini."},
    {"key": "production_pos.po_number_maklon", "label": "PO Maklon (Produksi)", "group": "Maklon",
     "policy_enforced": True,
     "default_format": "PO-MKL-{YYYY}{MM}-{SEQ:4}", "tokens": [], "default_mode": "auto",
     "collection": "production_pos", "field": "po_number",
     "catatan": "PO maklon yang tersimpan di koleksi PO produksi (SSOT satu penulis). "
                "Bawaan OTOMATIS (iter 106) — nomor lahir dari sistem; ubah ke manual bila perlu."},
    {"key": "cutting_orders.number", "label": "Order Cutting", "group": "Produksi",
     "auto_only": True, "alasan_otomatis": 'Lahir dari perintah produksi (SPP) saat cutting direncanakan.',
     "default_format": "CUT-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "dewi_cmt_permak.permak_number", "label": "Permak / Perbaikan", "group": "Produksi",
     "policy_enforced": True,
     "default_format": "PMK/{YYYY}/{MM}/{SEQ:4}", "tokens": [],
     "catatan": "Mode MANUAL hanya untuk permak yang melahirkan SATU dokumen; "
                "satu pengajuan yang terpecah ke beberapa baris reject ditolak dengan "
                "alasannya (satu nomor tidak bisa dipakai banyak dokumen)."},
    {"key": "cmt_receipts.receipt_code", "label": "Penerimaan FG dari CMT", "group": "Produksi",
     "policy_enforced": True,
     "default_format": "CMT-RCV-{SEQ:5}", "tokens": []},
    # W5 (2026-08-20) — surat jalan CMT → DA. Nomor LAHIR saat surat jalannya
    # dicetak dari baris penerimaan FG (satu penerimaan = satu nomor, dipakai lagi
    # pada cetakan berikutnya), jadi tidak ada form yang bisa mengetiknya.
    {"key": "cmt_delivery_notes.dn_number", "label": "Surat Jalan CMT → DA",
     "group": "Produksi", "auto_only": True,
     "alasan_otomatis": 'Nomor lahir saat surat jalan dicetak dari baris "Terima FG dari '
                        'CMT" — satu penerimaan memakai satu nomor selamanya, jadi tidak '
                        'ada layar yang mengetiknya.',
     "default_format": "SJ-CMT/{YYYY}/{MM}/{SEQ:4}", "tokens": []},
    # SESI #27 — "Retur Material Produksi" (`production_material_returns.ref_no`) DIHAPUS
    # dari katalog: menu `prod-material-returns` sudah DI-DEPRECATE pemilik (duplikasi —
    # material diurus di "Kirim Material CMT", lihat catatan portalNav.js), tidak ada satu
    # pun layar yang membuatnya, dan koleksinya kosong. Menawarkan setelan Otomatis/Manual
    # untuk dokumen yang tak bisa dibuat siapa pun = setelan yang berbohong. Jalur
    # tulisnya masih ada di kode dan tercatat sebagai PENGECUALIAN BERALASAN pada gate
    # INV-F25 (G12) supaya tidak hilang dari radar.
    {"key": "production_returns.return_number", "label": "Retur Produksi (barang dari buyer)",
     "group": "Produksi", "policy_enforced": True,
     "default_format": "RTN-{SEQ:4}", "tokens": [],
     "catatan": "Retur barang jadi dari buyer (layar Produksi → Retur). BERBEDA dari "
                "retur material ke gudang."},
    {"key": "production_jobs.job_number", "label": "Job Produksi", "group": "Produksi",
     "auto_only": True,
     "alasan_otomatis": 'Job lahir dari perintah produksi/WO; job turunan memakai nomor '
                        'induk + akhiran, jadi nomornya tidak boleh diketik.',
     "default_format": "JOB-{SEQ:4}", "tokens": []},
    {"key": "dewi_cmt_component_requests.request_code", "label": "Permintaan Komponen Kurang",
     "group": "Produksi", "policy_enforced": True,
     "default_format": "{TIPE}-{YY}{MM}{DD}-{SEQ:3}", "tokens": ["TIPE"],
     "catatan": "TIPE = REQ-CMP (komponen) atau REQ-AKS-CMT (aksesoris dari CMT) — "
                "dua jenis permintaan, dua seri nomor, satu kebijakan."},
    {"key": "dewi_maklon_samples.sample_code", "label": "Sampel Maklon", "group": "Maklon",
     "policy_enforced": True,
     "default_format": "SMP-{ORDER}-{SEQ:2}", "tokens": ["ORDER"],
     "catatan": "ORDER = kode order/PO klien, supaya satu seri per order "
                "(SMP-<ORDER>-01, -02, …). Format lama di katalog ini "
                "(SMP-{YYYY}{MM}-…) tidak pernah dipakai kode — diperbaiki sesi #27."},
    {"key": "dewi_maklon_credit_notes.credit_note_number", "label": "Nota Kredit Maklon", "group": "Maklon",
     "auto_only": True, "alasan_otomatis": 'Dibuat sistem oleh jembatan produksi–maklon.',
     "default_format": "CN-MKL-{SEQ:5}", "tokens": []},
    {"key": "dewi_cmt_payments.payment_code", "label": "Pembayaran CMT", "group": "Maklon",
     "auto_only": True, "alasan_otomatis": 'Dibuat sistem oleh jembatan produksi–maklon.',
     "default_format": "PAY-CMT-{SEQ:5}", "tokens": []},
    # ── tahap 2 (2026-08-05): 11 penghasil nomor manual dipusatkan ────────────
    {"key": "dewi_maklon_pos.po_number", "label": "PO Maklon", "group": "Maklon",
     "auto_only": True,
     "alasan_otomatis": 'PO maklon dibuat di Portal Produksi (koleksi `production_pos`, '
                        'jenis "PO Maklon (Produksi)") lalu DICERMINKAN ke sini — '
                        'nomornya lahir di sana, tidak diketik di layar ini.',
     "default_format": "MKL-{KLIEN}-{YYYY}-{SEQ:4}", "tokens": ["KLIEN"],
     "catatan": "KLIEN = kode klien maklon (mis. ARN). SESI #27: tidak ada layar aktif "
                "yang membuat PO lewat koleksi ini (yang lama sudah diarsipkan), jadi "
                "menawarkan mode MANUAL di sini akan menjadi setelan tanpa kolom."},
    {"key": "dewi_maklon_dispatches.dispatch_number", "label": "Pengiriman Maklon ke Klien",
     "auto_only": True, "alasan_otomatis": 'Lahir dari alur pengiriman PO maklon.',
     "group": "Maklon", "default_format": "DISP-{KLIEN}-{YYYY}{MM}{DD}-{SEQ:3}",
     "tokens": ["KLIEN"]},
    {"key": "dewi_maklon_invoices.invoice_number", "label": "Invoice Maklon (manual)",
     "policy_enforced": True,
     "group": "Maklon", "default_format": "{PREFIX}-{YYYY}-{SEQ:4}", "tokens": ["PREFIX"],
     "catatan": "PREFIX mengikuti Pengaturan Sistem 'maklon_invoice_prefix' (bawaan INV-MKL)."},
    {"key": "dewi_maklon.ar_invoice_number", "label": "Invoice Maklon otomatis (AR)",
     "auto_only": True, "alasan_otomatis": 'Dibuat sistem saat PO maklon dikonfirmasi.',
     "group": "Maklon", "default_format": "INV-MKL-{YYYY}-{SEQ:4}", "tokens": [],
     "collection": "rahaza_ar_invoices", "field": "invoice_number",
     "catatan": "Dibuat otomatis saat PO Maklon dikonfirmasi. Tersimpan di koleksi "
                "invoice piutang, terpisah dari nomor AR Finance."},
    {"key": "vendor_jobs.job_number", "label": "Job Vendor (Portal Vendor)", "group": "Maklon",
     "auto_only": True, "alasan_otomatis": 'Lahir saat pekerjaan dibagikan ke portal vendor.',
     "default_format": "VJ-{SEQ:5}", "tokens": []},

    # ── KEUANGAN ──────────────────────────────────────────────────────────────
    # SESI #19 (2026-08-17) — Jurnal Umum DITEGAKKAN (permintaan owner).
    # Satu buku besar = satu urutan nomor, jadi TIDAK dibuat kunci kedua untuk jurnal
    # otomatis: dua format berbeda pada satu field justru merusak urutan arsipnya.
    {"key": "rahaza_journal_entries.je_number", "label": "Jurnal Umum (JE)", "group": "Keuangan",
     "policy_enforced": True,
     "default_format": "JE-{YYYY}{MM}{DD}-{SEQ:4}", "tokens": [], "default_mode": "auto",
     "catatan": "Mode MANUAL berlaku untuk Jurnal Umum yang diketik orang di layar Keuangan. "
                "Jurnal yang lahir otomatis dari posting dokumen lain (penjualan, penggajian, "
                "penerimaan barang) tetap bernomor otomatis — tidak ada yang mengetiknya."},
    {"key": "rahaza_ar_invoices.invoice_number", "label": "Invoice Piutang (AR)", "group": "Keuangan",
     "policy_enforced": True,
     "default_format": "AR-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "rahaza_credit_notes.cn_number", "label": "Nota Kredit", "group": "Keuangan",
     "auto_only": True, "alasan_otomatis": 'Dibuat sistem saat retur penjualan disetujui.',
     "default_format": "CN-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "rahaza_bank_transfers.ref_number", "label": "Transfer Bank", "group": "Keuangan",
     "policy_enforced": True,
     "catatan": "Nomor dokumen transfer internal (bukan nomor referensi bank).",
     "default_format": "BT-{YYYY}{MM}{DD}-{SEQ:4}", "tokens": []},
    {"key": "rahaza_fixed_assets.code", "label": "Aset Tetap", "group": "Keuangan",
     "policy_enforced": True,
     "default_format": "FA-{SEQ:5}", "tokens": [],
     "catatan": "Field dokumennya `code` (bukan `asset_code`). Aset yang lahir dari "
                "kapitalisasi penerimaan barang tetap bernomor otomatis."},
    {"key": "rahaza_orders.order_number", "label": "Order Penjualan", "group": "Keuangan",
     "auto_only": True,
     "alasan_otomatis": 'Layar "Order Penjualan" lama DINONAKTIFKAN dari UI (menu '
                        '`prod-orders` diarahkan ke PO Internal); order yang hidup dibuat '
                        'sebagai PO Produksi Internal (SPP). Endpoint lamanya masih ada '
                        'untuk dibaca modul lain, tetapi tidak ada layar yang mengetik '
                        'nomornya.',
     "default_format": "ORD-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "rahaza_ap_invoices.invoice_number", "label": "Invoice Hutang (AP dari GR)",
     "auto_only": True, "alasan_otomatis": 'Hutang dibuat sistem dari penerimaan barang (GR), bukan diketik.',
     "group": "Keuangan", "default_format": "AP-{YY}{MM}-{SEQ:4}", "tokens": []},

    # ── SDM ───────────────────────────────────────────────────────────────────
    {"key": "rahaza_payroll_runs.run_number", "label": "Run Penggajian", "group": "SDM",
     "auto_only": True, "alasan_otomatis": 'Lahir saat run penggajian dibuat sistem.',
     "default_format": "PAY-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    # SESI #18 (2026-08-17) — satu koleksi `dewi_kasbon_requests` menampung DUA jenis
    # pengajuan (kasbon & pinjaman) dengan awalan berbeda (KSB / PIN), jadi masing-masing
    # punya kunci sendiri memakai override `collection`/`field` (pola yang sama dengan
    # PO Maklon). Tanpa kunci kedua, memindah "Kasbon" ke MANUAL akan ikut memaksa
    # pengajuan PINJAMAN diketik manual — dua dokumen berbeda dipaksa satu kebijakan.
    {"key": "dewi_kasbon_requests.request_number", "label": "Pengajuan Kasbon", "group": "SDM",
     "policy_enforced": True,
     "default_format": "KSB-{YYYY}{MM}-{SEQ:5}", "tokens": [],
     "catatan": "Hanya untuk jenis pengajuan KASBON. Pinjaman karyawan punya kuncinya sendiri."},
    {"key": "dewi_kasbon_requests.request_number_pinjaman",
     "label": "Pengajuan Pinjaman Karyawan", "group": "SDM",
     "policy_enforced": True,
     "default_format": "PIN-{YYYY}{MM}-{SEQ:5}", "tokens": [],
     "collection": "dewi_kasbon_requests", "field": "request_number",
     "catatan": "Pinjaman (cicilan >1) yang tersimpan di koleksi pengajuan kasbon."},
    # SESI #27 — "Pinjaman Karyawan" versi LEGACY (`rahaza_employee_loans.loan_number`)
    # DIHAPUS dari katalog ini. Alasannya bukan kosmetik: koleksinya sudah diarsipkan
    # (0 dokumen) oleh migrasi T2.1, menunya diarahkan ke `hr-kasbon`, layarnya dilepas
    # dari registry, dan sejak sesi ini endpoint penulisnya menjawab HTTP 410. Selama
    # entri ini ada di katalog, owner bisa memilih Otomatis/Manual untuk dokumen yang
    # TIDAK BISA dibuat siapa pun — setelan yang berbohong, yang justru dilawan Fase G.
    # Pinjaman karyawan yang HIDUP = "Pengajuan Pinjaman Karyawan"
    # (`dewi_kasbon_requests.request_number_pinjaman`, sudah ditegakkan sejak sesi #18).
    {"key": "dewi_assets.asset_number", "label": "Aset Inventaris", "group": "SDM",
     "policy_enforced": True,
     "default_format": "AST-{KATEGORI}-{YYYY}-{SEQ:4}", "tokens": ["KATEGORI"],
     "catatan": "KATEGORI = kode kategori aset (mis. IT, KND). Format lama di katalog "
                "ini (AST-{YYYY}-…) tidak pernah dipakai kode — diperbaiki sesi #27. "
                "Impor massal tetap bernomor otomatis."},
    {"key": "rahaza_expense_claims.claim_number", "label": "Klaim Biaya Karyawan", "group": "SDM",
     "policy_enforced": True,
     "default_format": "EC-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "employee_travel_requests.trip_number", "label": "Permohonan Perjalanan Dinas",
     "policy_enforced": True,
     "group": "SDM", "default_format": "TR-{YYYY}{MM}-{SEQ:4}", "tokens": []},
    {"key": "employee_travel_settlements.settlement_number", "label": "Penyelesaian Perjalanan Dinas",
     "policy_enforced": True,
     "group": "SDM", "default_format": "TS-{YYYY}{MM}-{SEQ:4}", "tokens": []},

    # ── LAIN-LAIN ─────────────────────────────────────────────────────────────
    {"key": "dewi_accessory_requests.request_code", "label": "Permintaan Aksesoris", "group": "Aksesoris",
     "policy_enforced": True,
     "default_format": "{TIPE}-{YY}{MM}{DD}-{SEQ:3}", "tokens": ["TIPE"],
     "catatan": "TIPE mengikuti jenis permintaan: REQ-AKS (sampel R&D) · INT-REQ "
                "(pengeluaran internal) · ACC-ADD (tambahan vendor) · ACC-RPL "
                "(pengganti vendor)."},
    {"key": "dewi_kreator_requests.request_code", "label": "Permintaan Kreator", "group": "Marketing",
     "policy_enforced": True,
     "default_format": "REQ-KR-{YY}{MM}{DD}-{SEQ:3}", "tokens": []},
    {"key": "wh_barcode_print_jobs.job_number", "label": "Job Cetak Barcode", "group": "Gudang",
     "auto_only": True,
     "alasan_otomatis": 'Antrean cetak label dibuat sistem saat tombol cetak ditekan — '
                        'bukan dokumen yang diarsipkan.',
     "default_format": "BPJ-{YYYY}{MM}{DD}-{SEQ:3}", "tokens": []},

    # ── SKU / KODE MASTER ─────────────────────────────────────────────────────
    {"key": "rahaza_suppliers.code", "label": "Kode Supplier", "group": "SKU / Kode Master",
     "pending_enforce": True,
     "default_format": "SUP-{SEQ:4}", "tokens": [],
     "catatan": "Form supplier sudah menerima kode ketikan (dengan pemeriksaan kembar), "
                "tetapi belum lewat satu pintu kebijakan penomoran."},
    {"key": "rahaza_materials.code", "label": "SKU Aksesoris Baru", "group": "SKU / Kode Master",
     "auto_only": True, "alasan_otomatis": 'Kode master aksesoris dibuat sistem saat master baru disimpan.',
     "default_format": "ACC-{SEQ:4}", "tokens": []},
    {"key": "rahaza_materials.cut_panel_code", "label": "SKU Potongan (Cutting)", "group": "SKU / Kode Master",
     "auto_only": True, "alasan_otomatis": 'Kode potongan lahir dari proses cutting (tanpa nomor urut).',
     "default_format": "CUT-{STYLE}-{WARNA}-{SIZE}", "tokens": ["STYLE", "WARNA", "SIZE"],
     "sequenced": False,
     "catatan": "Kode potongan hasil cutting. Tanpa nomor urut — kombinasi style/warna/ukuran sudah unik."},
]

REGISTRY_BY_KEY = {e["key"]: e for e in DOC_NUMBER_REGISTRY}
GROUPS = sorted({e["group"] for e in DOC_NUMBER_REGISTRY})


def target_of(entry: dict) -> tuple:
    """(koleksi, field) NYATA tempat nomor disimpan.

    Umumnya diturunkan dari `key` ("<koleksi>.<field>"), tetapi entri boleh
    menimpanya lewat `collection`/`field` bila satu koleksi menampung dua jenis
    nomor (mis. invoice AR Finance vs invoice maklon otomatis).
    """
    coll, fld = entry["key"].rsplit(".", 1)
    return entry.get("collection") or coll, entry.get("field") or fld
