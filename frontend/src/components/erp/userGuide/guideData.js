/**
 * Structured data untuk Panduan Penggunaan PT Rahaza ERP.
 * Dipakai oleh UserGuideContent.jsx (rich-visual renderer).
 *
 * Struktur:
 *  - PORTAL_META: warna, icon, role per portal
 *  - GUIDE_SECTIONS: array section utama (overview, per-portal, scenarios, tips)
 *  - SCENARIOS: array test-scenario dengan prerequisite, langkah, expected result
 */

import {
  BookOpen, BarChart3, Workflow, Warehouse, DollarSign, UserCog, UserCircle,
  Package, ClipboardList, FileText, Calendar, Users, Settings, Activity,
  AlertTriangle, CheckCircle2, Clock, Lightbulb, Zap, Wrench, ShieldAlert,
  PackageCheck, Truck, Receipt, BookMarked, Layers, Target, ScrollText,
  HelpCircle, Sparkles, Boxes, Factory, ListChecks, Gauge,
  // Session 28 — LiveHost
  Radio, Play, GraduationCap, Bell, Trophy, Mic2,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────
 * Portal Meta — warna & ikon per portal (konsisten di seluruh aplikasi)
 * ───────────────────────────────────────────────────────── */
export const PORTAL_META = {
  manajemen: {
    name: 'Manajemen',
    short: 'MGT',
    icon: BarChart3,
    role: 'Direktur, Manager Produksi/Keuangan/HR',
    color: 'sky',
    classes: {
      text: 'text-sky-500',
      bg: 'bg-sky-100 dark:bg-sky-500/10',
      border: 'border-sky-400 dark:border-sky-500/30',
      ring: 'ring-sky-500/20',
      dot: 'bg-sky-500',
    },
  },
  produksi: {
    name: 'Produksi',
    short: 'PRD',
    icon: Factory,
    role: 'Supervisor, PPIC, Operator',
    color: 'emerald',
    classes: {
      text: 'text-emerald-500',
      bg: 'bg-emerald-100 dark:bg-emerald-500/10',
      border: 'border-emerald-400 dark:border-emerald-500/30',
      ring: 'ring-emerald-500/20',
      dot: 'bg-emerald-500',
    },
  },
  gudang: {
    name: 'Gudang',
    short: 'WHS',
    icon: Warehouse,
    role: 'Kepala Gudang, Staff Gudang',
    color: 'amber',
    classes: {
      text: 'text-amber-500',
      bg: 'bg-amber-100 dark:bg-amber-500/10',
      border: 'border-amber-400 dark:border-amber-500/30',
      ring: 'ring-amber-500/20',
      dot: 'bg-amber-500',
    },
  },
  pengadaan: {
    name: 'Pengadaan',
    short: 'PRC',
    icon: Receipt,
    role: 'Staf & Manajer Pengadaan, Keuangan, Kepala Gudang',
    color: 'indigo',
    classes: {
      text: 'text-indigo-500',
      bg: 'bg-indigo-100 dark:bg-indigo-500/10',
      border: 'border-indigo-400 dark:border-indigo-500/30',
      ring: 'ring-indigo-500/20',
      dot: 'bg-indigo-500',
    },
  },
  keuangan: {
    name: 'Keuangan',
    short: 'FIN',
    icon: DollarSign,
    role: 'Finance Staff, Accounting',
    color: 'violet',
    classes: {
      text: 'text-violet-500',
      bg: 'bg-violet-100 dark:bg-violet-500/10',
      border: 'border-violet-400 dark:border-violet-500/30',
      ring: 'ring-violet-500/20',
      dot: 'bg-violet-500',
    },
  },
  sdm: {
    name: 'SDM',
    short: 'HR',
    icon: UserCog,
    role: 'HR Staff',
    color: 'rose',
    classes: {
      text: 'text-rose-500',
      bg: 'bg-rose-100 dark:bg-rose-500/10',
      border: 'border-rose-400 dark:border-rose-500/30',
      ring: 'ring-rose-500/20',
      dot: 'bg-rose-500',
    },
  },
  qc: {
    name: 'QC',
    short: 'QC',
    icon: ShieldAlert,
    role: 'QC Inspector',
    color: 'fuchsia',
    classes: {
      text: 'text-fuchsia-500',
      bg: 'bg-fuchsia-100 dark:bg-fuchsia-500/10',
      border: 'border-fuchsia-400 dark:border-fuchsia-500/30',
      ring: 'ring-fuchsia-500/20',
      dot: 'bg-fuchsia-500',
    },
  },
  shift: {
    name: 'Shift',
    short: 'SHF',
    icon: Clock,
    role: 'Supervisor Shift',
    color: 'cyan',
    classes: {
      text: 'text-cyan-500',
      bg: 'bg-cyan-100 dark:bg-cyan-500/10',
      border: 'border-cyan-400 dark:border-cyan-500/30',
      ring: 'ring-cyan-500/20',
      dot: 'bg-cyan-500',
    },
  },
  saya: {
    name: 'Portal Saya',
    short: 'ME',
    icon: UserCircle,
    role: 'Semua karyawan',
    color: 'pink',
    classes: {
      text: 'text-pink-500',
      bg: 'bg-pink-100 dark:bg-pink-500/10',
      border: 'border-pink-400 dark:border-pink-500/30',
      ring: 'ring-pink-500/20',
      dot: 'bg-pink-500',
    },
  },
  livehost: {
    name: 'LiveHost',
    short: 'LIV',
    icon: Radio,
    role: 'Admin Marketing, Supervisor LiveHost, Host',
    color: 'teal',
    classes: {
      text: 'text-teal-500',
      bg: 'bg-teal-100 dark:bg-teal-500/10',
      border: 'border-teal-400 dark:border-teal-500/30',
      ring: 'ring-teal-500/20',
      dot: 'bg-teal-500',
    },
  },
};

/* ─────────────────────────────────────────────────────────
 * Difficulty levels untuk skenario
 * ───────────────────────────────────────────────────────── */
export const DIFFICULTY = {
  pemula: { label: 'Pemula', classes: 'bg-green-100 dark:bg-green-500/15 text-green-600 border-green-400 dark:border-green-500/30' },
  menengah: { label: 'Menengah', classes: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 border-amber-400 dark:border-amber-500/30' },
  lanjut: { label: 'Lanjut', classes: 'bg-red-100 dark:bg-red-500/15 text-red-600 border-red-400 dark:border-red-500/30' },
};

/* ─────────────────────────────────────────────────────────
 * Section "Overview" — pengenalan sistem
 * ───────────────────────────────────────────────────────── */
export const OVERVIEW = {
  id: 'overview',
  title: 'Selamat Datang',
  icon: BookOpen,
  intro:
    'PT Rahaza ERP adalah platform terpadu untuk mengelola seluruh operasional pabrik garment rajut — dari perencanaan produksi, gudang, keuangan, hingga SDM.',
  highlights: [
    { icon: Zap, title: 'Real-time', desc: 'Data produksi & stok ter-update otomatis' },
    { icon: ListChecks, title: 'Terintegrasi', desc: '5 portal saling terhubung tanpa duplikasi data' },
    { icon: ShieldAlert, title: 'Audit Trail', desc: 'Setiap perubahan tercatat (siapa, kapan, apa)' },
    { icon: Sparkles, title: 'AI Assistant', desc: 'Chatbot bantuan & ringkasan laporan otomatis' },
  ],
  loginSteps: [
    { icon: 'login', text: 'Masuk dengan email & password yang diberikan admin' },
    { icon: 'select', text: 'Pilih Portal yang sesuai dengan peran Anda' },
    { icon: 'navigate', text: 'Menu utama berada di sidebar kiri portal' },
    { icon: 'switch', text: 'Klik nama portal di kiri-atas untuk berpindah portal' },
  ],
};

/* ─────────────────────────────────────────────────────────
 * Per-Portal Detail — daftar menu & deskripsi visual
 * ───────────────────────────────────────────────────────── */
export const PORTALS_GUIDE = [
  {
    id: 'p-manajemen',
    portalKey: 'manajemen',
    title: 'Portal Manajemen',
    summary: 'Pusat kendali eksekutif: dashboard KPI, master data produk/customer, order buyer, analitik.',
    menus: [
      {
        icon: BarChart3, title: 'Dashboard Eksekutif',
        path: 'Dashboard › Dashboard Eksekutif',
        description: 'Tampilan KPI utama untuk direktur & manager.',
        bullets: [
          'KPI: WO aktif, WO selesai bulan ini, OEE rata-rata, total karyawan',
          'Production Trend Chart 30 hari terakhir',
          'Top Issues — masalah produksi yang paling sering muncul',
        ],
        tips: 'Refresh otomatis tiap 5 menit. Cocok ditampilkan di TV ruang manajemen.',
      },
      {
        icon: Layers, title: 'Style Master (Model Produk)',
        path: 'Master Data › Model Produk',
        description: 'Katalog desain yang pernah/akan diproduksi.',
        bullets: [
          'Kode & nama, kategori, berat bahan per pcs, ukuran bundle',
          'Upload foto desain (otomatis muncul di LKP PDF)',
          'BOM — daftar material per model',
        ],
        warn: 'Pastikan foto desain ter-upload sebelum produksi mulai.',
      },
      {
        icon: ClipboardList, title: 'Order Management',
        path: 'Order › Order Produksi',
        description: 'Buat & pantau order dari buyer/customer.',
        bullets: [
          'Pilih buyer, model, qty, ukuran, tanggal kirim',
          'Status: Draft → Confirmed → In Production → Shipped',
          'Generate Work Order otomatis per batch',
        ],
      },
      {
        icon: BookMarked, title: 'Panduan Penggunaan ERP',
        path: 'Bantuan › Panduan',
        description: 'Manual lengkap (halaman ini).',
        bullets: ['Search semua menu & fitur', '8 skenario test step-by-step', 'Tips & FAQ'],
      },
    ],
  },
  {
    id: 'p-produksi',
    portalKey: 'produksi',
    title: 'Portal Produksi',
    summary: 'Hati pabrik: WO, LKP, APS Gantt, Line Assignment, OEE, Rework, Shift Handover.',
    menus: [
      {
        icon: ClipboardList, title: 'Work Order (WO)',
        path: 'Eksekusi › Work Order',
        description: 'Surat perintah kerja yang menggerakkan lantai produksi.',
        bullets: [
          'Status: Draft → Released → In Progress → Completed/Cancelled',
          'Release WO → otomatis reserve material sesuai BOM',
          'Cetak LKP Massal — status LKP semua WO aktif',
        ],
        warn: 'Pastikan stok BOM sudah cukup sebelum Release. Kalau kurang, sistem tampilkan warning.',
      },
      {
        icon: FileText, title: 'LKP (Lembar Kerja Produksi)',
        path: 'Eksekusi › Work Order › [WO] › LKP',
        description: 'Dokumen instruksi kerja per WO — SOP, BOM, QC, packing.',
        bullets: [
          '5-step wizard: Tech Pack → SOP → QC → Packing → Notes',
          'Upload Foto QC/defect/progres (max 3 per LKP)',
          'Foto otomatis muncul di Section L PDF',
          'Versioning — setiap revisi buat versi baru',
        ],
        tips: 'Download PDF selalu generate ulang dengan foto terbaru.',
      },
      {
        icon: Calendar, title: 'APS Gantt — Penjadwalan Otomatis',
        path: 'Monitoring › Penjadwalan APS',
        description: 'Visualisasi jadwal WO per lini.',
        bullets: [
          'Auto-Schedule — sistem optimalkan urutan WO',
          'Kolom merah = hari libur (dari Kalender Produksi)',
          'Tab Line Balance — keseimbangan beban per lini',
        ],
      },
      {
        icon: Users, title: 'Assign Lini Hari Ini',
        path: 'Eksekusi › Assign Lini Hari Ini',
        description: 'Tentukan karyawan & mesin per lini & shift.',
        bullets: [
          'Copy dari Kemarin — 1 klik isi otomatis',
          'Auto-Assign dari Template tersimpan',
        ],
      },
      {
        icon: PackageCheck, title: 'Bulk Material Issue (Bulk MI)',
        path: 'Eksekusi › Bulk Material Issue',
        description: 'Keluarkan material ke lantai produksi banyak WO sekaligus.',
        bullets: [
          'Default tampil WO "in_progress" — bisa filter ke "released"',
          'Pilih WO → review BOM → konfirmasi → stok terkurangi',
        ],
        warn: 'Cek stok material cukup sebelum issue.',
      },
      {
        icon: Clock, title: 'Shift Handover',
        path: 'Eksekusi › Shift Handover',
        description: 'Serah terima shift dengan checklist & PDF.',
        bullets: [
          '5 checklist standar (target, quality, downtime, material, K3)',
          'Catat issues (tipe + priority) & pending tasks',
          'Sign-Off oleh supervisor shift berikutnya',
          'Download End-of-Shift PDF',
        ],
      },
      {
        icon: Boxes, title: 'Reservasi Material',
        path: 'Eksekusi › Reservasi Material',
        description: 'Stok yang sudah di-booking untuk WO tertentu.',
        bullets: [
          'Tab Per WO / Per Material',
          'Auto-reservasi saat WO di-release',
          'Stok Tersedia = Stok Total - Reserved',
        ],
      },
      {
        icon: Calendar, title: 'Kalender Produksi',
        path: 'Master Data › Kalender Produksi',
        description: 'Hari libur & pengecualian untuk APS.',
        bullets: [
          'Seed Libur Nasional 2026 (1-klik 20 hari)',
          'Tipe entri: Libur (merah), Pengecualian (kuning), Catatan (biru)',
          'Kalkulator hari kerja per periode',
        ],
      },
      {
        icon: Gauge, title: 'OEE Dashboard',
        path: 'Monitoring › OEE',
        description: 'Overall Equipment Effectiveness per lini & mesin.',
        bullets: [
          'OEE = Availability × Performance × Quality',
          'Drill-down per lini & mesin',
          'Downtime events (mesin breakdown, dll)',
        ],
      },
      {
        icon: AlertTriangle, title: 'Papan Rework',
        path: 'Eksekusi › Papan Rework',
        description: 'Manajemen item yang gagal QC & perlu rework.',
        bullets: [
          'Buat Rework: WO, qty, jenis defect, assign operator',
          'Kode defect terstandardisasi',
          'Closed-loop tracking — sampai pcs pass kembali',
        ],
      },
    ],
  },
  {
    id: 'p-gudang',
    portalKey: 'gudang',
    title: 'Portal Gudang',
    summary: 'Kelola material, inventori, penerimaan barang, opname stok, multi-zona. (Pembelian/PO kini di Portal Pengadaan.)',
    menus: [
      {
        icon: Package, title: 'Master Material',
        path: 'Master Data › Material',
        description: 'Daftar semua material (bahan, aksesoris, produk jadi).',
        bullets: ['Kategori: Bahan / Aksesoris / Produk Jadi', 'Min stock indicator (low-stock badge)'],
      },
      {
        icon: Boxes, title: 'Inventori',
        path: 'Inventori › Stok',
        description: 'Stok real-time per material & lokasi.',
        bullets: [
          'FIFO valuation',
          'Movement log lengkap (in/out/adjust)',
          'Filter per gedung/zona/rak',
        ],
      },
      {
        icon: Truck, title: 'Penerimaan Barang (GR)',
        path: 'Penerimaan Barang',
        description: 'Konfirmasi penerimaan barang dari PO. (PO-nya dibuat di Portal Pengadaan.)',
        bullets: [
          'No GR atomic counter (GR-00001 dst)',
          'Saat status = received → auto-sync ke material_stock',
          'Material picker dari master material',
        ],
      },
      {
        icon: ListChecks, title: 'Stockopname',
        path: 'Inventori › Opname',
        description: 'Stock taking dengan adjustment otomatis ke GL.',
        bullets: [
          'Input fisik vs sistem',
          'Selisih → otomatis posting jurnal ke akuntansi',
          'Audit trail per record',
        ],
      },
      {
        icon: AlertTriangle, title: 'Low Stock Indicators',
        path: 'Inventori › Low Stock',
        description: 'Material di bawah minimum.',
        bullets: ['Threshold konfigurabel (angka tetap atau %)', 'Badge merah/kuning'],
      },
    ],
  },
  {
    // 2026-08-06 — section BARU: portal ini lahir dari pemisahan procurement
    // dari Gudang/Keuangan/Aksesoris. Tanpa entri di sini, "Panduan Penggunaan"
    // tidak pernah menyebut portal yang justru paling sering dipakai pembeli.
    id: 'p-pengadaan',
    portalKey: 'pengadaan',
    title: 'Portal Pengadaan',
    summary: 'Satu pintu untuk membeli: master supplier, permintaan (PR), purchase order, rekonsiliasi 3 arah, faktur supplier, dan analisis belanja.',
    menus: [
      {
        icon: Gauge, title: 'Dashboard Pengadaan',
        path: 'Ringkasan & Master › Dashboard Pengadaan',
        description: 'Antrean kerja harian pembeli + peringatan PO telat/jatuh tempo.',
        bullets: [
          'KPI: PR menunggu, PO berjalan, penerimaan, hutang supplier',
          'Funnel P2P: PR → PO → Penerimaan → Faktur',
          'Peringatan PO tanpa Master Supplier (data lama)',
        ],
      },
      {
        icon: Boxes, title: 'Master Supplier',
        path: 'Ringkasan & Master › Master Supplier',
        description: 'Sumber tunggal data supplier + daftar harga per satuan beli.',
        bullets: [
          'Kode SUP-xxxx otomatis; nama dijaga unik (anti duplikat)',
          'Kontak, rekening, NPWP, termin bayar, lead time, kategori',
          'Migrasi Data Lama: nama teks bebas di PO/GRN lama → master',
        ],
        tips: 'Isi daftar harga supaya harga PO terisi otomatis saat memilih material.',
      },
      {
        icon: ClipboardList, title: 'Permintaan Pengadaan (PR)',
        path: 'Permintaan & Pesanan › Permintaan Pengadaan',
        description: 'Divisi mengajukan kebutuhan; melewati rantai persetujuan lalu jadi PO.',
        bullets: [
          'Item bisa ditautkan ke material master + satuan beli',
          'Kotak masuk persetujuan hanya menampilkan antrean Anda',
          'PR disetujui → tombol Buat PO',
        ],
      },
      {
        icon: Receipt, title: 'Purchase Order (PO)',
        path: 'Permintaan & Pesanan › Purchase Order',
        description: 'Pesanan resmi ke supplier dengan satuan beli berjenjang.',
        bullets: [
          'Supplier dipilih dari master (bukan teks bebas)',
          'Input karton/bungkus → sistem simpan konversi ke satuan dasar',
          'Status: Draf → Disetujui → Diterima Sebagian → Diterima Penuh',
        ],
        tips: 'Barang datang dicatat di Portal Gudang → Penerimaan Barang; qty diterima muncul kembali di PO.',
      },
      {
        icon: ListChecks, title: 'Rekonsiliasi PO (3 Arah)',
        path: 'Rekonsiliasi & Faktur › Rekonsiliasi PO',
        description: 'Bandingkan dipesan ↔ diterima ↔ difaktur dalam satuan dasar.',
        bullets: [
          'Menandai kurang/lebih kirim & faktur kelebihan',
          'Toleransi selisih dapat diatur',
          'Detail per PO: daftar penerimaan & faktur yang menempel',
        ],
      },
      {
        icon: FileText, title: 'Faktur Supplier',
        path: 'Rekonsiliasi & Faktur › Faktur Supplier',
        description: 'Buat hutang (AP) dari barang yang SUDAH diterima.',
        bullets: [
          'Nilai memakai qty NET (dikurangi tolakan QC) & harga satuan dasar',
          'Nomor faktur supplier ditolak bila dobel',
          'Diteruskan ke Keuangan untuk penjadwalan pembayaran',
        ],
      },
      {
        icon: BarChart3, title: 'Penilaian Supplier & Analisis Belanja',
        path: 'Ringkasan & Master › Penilaian Supplier / Analisis Belanja',
        description: 'Evaluasi supplier & arah belanja berbasis data nyata.',
        bullets: [
          'Penilaian dikelompokkan per Master Supplier (ejaan nama tak memecah nilai)',
          'Tingkat terima QC, tingkat cacat, ketepatan waktu kirim, grade A–D',
          'Belanja per supplier/kategori/material + tren bulanan',
        ],
      },
    ],
  },
  {
    id: 'p-keuangan',
    portalKey: 'keuangan',
    title: 'Portal Keuangan',
    summary: 'Akuntansi penuh: CoA, jurnal, payroll, laporan keuangan.',
    menus: [
      {
        icon: BookMarked, title: 'Chart of Accounts (CoA)',
        path: 'Master › CoA',
        description: 'Daftar akun akuntansi.',
        bullets: ['Hierarchy multi-level', 'Tipe: Asset/Liability/Equity/Revenue/Expense'],
      },
      {
        icon: ScrollText, title: 'Jurnal Umum',
        path: 'Akuntansi › Jurnal',
        description: 'Posting jurnal manual & otomatis.',
        bullets: [
          'Auto-post dari opname adjustment & payroll',
          'Filter per periode/akun',
          'Posting / Reverse',
        ],
      },
      {
        icon: DollarSign, title: 'Payroll Run',
        path: 'Payroll › Periode',
        description: 'Pemrosesan gaji bulanan.',
        bullets: [
          'Multi-skema: borongan pcs/jam, mingguan, bulanan',
          'Tombol "Periksa Sekarang" — validasi anomali absensi',
          'Generate slip gaji + posting jurnal',
        ],
        tips: 'Validasi attendance bersifat warning (bukan block).',
      },
      {
        icon: FileText, title: 'Laporan Keuangan',
        path: 'Laporan › Finance',
        description: 'Laporan standar.',
        bullets: ['Neraca, Laba-Rugi, Cash Flow Direct', 'Export Excel/PDF'],
      },
    ],
  },
  {
    id: 'p-sdm',
    portalKey: 'sdm',
    title: 'Portal SDM',
    summary: 'Kelola karyawan, absensi, izin, payroll profile, laporan HR.',
    menus: [
      {
        icon: Users, title: 'Master Karyawan',
        path: 'SDM › Karyawan',
        description: 'Daftar karyawan & profil.',
        bullets: [
          'Data identitas, departemen, lini, shift',
          'Payroll profile (skema gaji, base rate)',
          'Linking user → employee untuk Portal Saya',
        ],
      },
      {
        icon: Activity, title: 'Absensi',
        path: 'SDM › Absensi',
        description: 'Catat kehadiran harian.',
        bullets: [
          'Check-in / check-out',
          'Lembur (overtime)',
          'Auto-fill dari approved leave',
        ],
      },
      {
        icon: ListChecks, title: 'Izin & Cuti',
        path: 'SDM › Izin/Cuti',
        description: 'Request & approval cuti.',
        bullets: ['Saldo cuti per karyawan', 'Approval flow', 'Auto-fill ke attendance'],
      },
      {
        icon: BarChart3, title: 'Laporan HR',
        path: 'SDM › Laporan',
        description: 'Laporan attendance, lembur, payroll, turnover.',
        bullets: [
          'Filter: department, location, shift',
          'Format: table + charts',
          'Export Excel + PDF',
        ],
      },
    ],
  },
  {
    id: 'p-saya',
    portalKey: 'saya',
    title: 'Portal Saya',
    summary: 'Self-service untuk semua karyawan: kehadiran & slip gaji pribadi.',
    menus: [
      {
        icon: UserCircle, title: 'Profil Saya',
        path: 'Saya › Profil',
        description: 'Data pribadi & status karyawan.',
        bullets: ['Departemen, lini, shift', 'Saldo cuti'],
      },
      {
        icon: Activity, title: 'Kehadiran Saya',
        path: 'Saya › Absensi',
        description: 'Riwayat kehadiran pribadi.',
        bullets: ['Per bulan', 'Statistik kehadiran/lembur'],
      },
      {
        icon: Receipt, title: 'Slip Gaji Saya',
        path: 'Saya › Slip Gaji',
        description: 'Download slip gaji per periode.',
        bullets: ['Detail komponen gaji', 'Download PDF'],
      },
    ],
  },
  {
    id: 'p-livehost',
    portalKey: 'livehost',
    title: 'LiveHost Management',
    summary:
      'Modul end-to-end untuk live streaming: jadwal shift, script library, training, performance tracking, dan auto-sync payment ke Finance.',
    sopDownload: {
      label: 'Download SOP LiveHost (PDF)',
      endpoint: '/api/marketing/livehost/sop/download',
      filename: 'SOP_LiveHost.pdf',
    },
    menus: [
      {
        icon: Users, title: 'Live Hosts',
        path: 'Marketing › KOL & Creator › LiveHost Management › Live Hosts',
        description: 'Master data semua host: nama, kontak, employment type, rate, language skills, expertise.',
        bullets: [
          'CRUD host & password awal',
          'Assign 1+ platform account',
          'Atur shift preferences & language',
        ],
        tips: 'Email host harus unik karena dipakai untuk login ke /livehost portal.',
      },
      {
        icon: Calendar, title: 'Shift Management',
        path: 'LiveHost Management › Shift Management',
        description: 'Jadwalkan shift live: pilih host, account, tanggal, jenis shift, jam.',
        bullets: [
          '4 jenis shift: morning / afternoon / evening / night',
          'Validasi konflik waktu otomatis',
          'Host langsung dapat notifikasi real-time saat shift dibuat',
        ],
        warn: 'Pastikan host status = active dan platform account aktif sebelum buat shift.',
      },
      {
        icon: Calendar, title: 'Calendar View',
        path: 'LiveHost Management › Calendar View',
        description: 'Visualisasi kalender mingguan/bulanan semua shift, sortable per host atau account.',
        bullets: ['Drag-to-explore', 'Filter per host / account'],
      },
      {
        icon: FileText, title: 'Script Library',
        path: 'LiveHost Management › Script Library',
        description: 'Kumpulan script untuk live: opening, product intro, promotion, closing.',
        bullets: [
          'Global vs account-specific script',
          'Multi-bahasa (Indonesia / English / Mixed)',
          'Host browse via portal & filter per kategori',
        ],
      },
      {
        icon: GraduationCap, title: 'Training',
        path: 'LiveHost Management › Training',
        description: 'Modul training (video / pdf / quiz) dengan tracking progress per host.',
        bullets: [
          'Training wajib harus selesai sebelum shift produksi',
          'Expiry & re-certification otomatis',
          'Host self-complete untuk non-quiz, admin record score untuk quiz',
        ],
      },
      {
        icon: BarChart3, title: 'Analytics',
        path: 'LiveHost Management › Analytics',
        description: 'Performance dashboard per host & shift analysis.',
        bullets: [
          'Total shifts, hours, revenue, AOV per host',
          'Best shift time/day',
          'Top performer leaderboard',
        ],
      },
      {
        icon: DollarSign, title: 'Payment',
        path: 'LiveHost Management › Payment',
        description: 'Kalkulasi pembayaran (base + bonus − penalty) & auto-sync ke Finance/Payroll.',
        bullets: [
          'Sync membuat entry di payroll_entries (status pending_approval)',
          'Idempoten: shift yang sudah synced tidak akan diproses ulang',
          'Host dapat notifikasi saat payment sudah masuk ke Finance',
        ],
        warn: 'Approval final tetap dilakukan oleh tim Finance di Portal Keuangan.',
      },
      {
        icon: Radio, title: 'LiveHost Portal (Host)',
        path: 'URL: /livehost (standalone)',
        description: 'Portal mobile-first untuk host: login, clock-in/out, baca script, kerjakan training, lihat notifikasi real-time.',
        bullets: [
          '5 tab: Shift, Script, Training, Notif, Profile',
          'Real-time notifications via SSE',
          'Self-complete training non-quiz',
        ],
        tips: 'Portal dirancang mobile-first; buka di HP untuk pengalaman terbaik.',
      },
      {
        icon: Bell, title: 'Real-Time Notifications',
        path: 'Otomatis via SSE',
        description: 'Server-Sent Events stream untuk host: shift assigned, training assigned, payment synced.',
        bullets: [
          'Koneksi otomatis saat host login',
          'Fallback polling tersedia jika SSE tidak available',
          'Mark read / mark-all-read di portal',
        ],
      },
    ],
  },
];

/* ─────────────────────────────────────────────────────────
 * 8 Skenario Test — dengan PRE-REQUISITE eksplisit
 * Format step: { portal: 'produksi', icon: ?, title: 'Buat Order',
 *               detail: '...', menu: 'Order > Buat Order' }
 * ───────────────────────────────────────────────────────── */
export const SCENARIOS = [
  {
    id: 's1',
    code: 'S1',
    title: 'Order Baru → Produksi → QC Pass → Selesai',
    description:
      'Alur happy-path produksi normal: dari order masuk hingga semua qty pass QC dan WO ditutup.',
    difficulty: 'pemula',
    estimatedTime: '~3-5 hari kalender (proses real); ~15 menit (input sistem)',
    personas: ['manajemen', 'produksi'],
    prerequisites: [
      'Master Customer & Buyer sudah terdaftar di Portal Manajemen',
      'Master Model "Sweater Klasik V-Neck" sudah ada (foto desain ter-upload)',
      'BOM model lengkap (bahan & aksesoris dengan qty per pcs)',
      'SOP per proses sudah dibuat (rajut, linking, sewing, steam, qc, packing)',
      'Stok bahan utama & aksesoris cukup untuk 200 pcs',
      'Lini & mesin sudah aktif, karyawan operator sudah terdaftar',
    ],
    steps: [
      { portal: 'manajemen', title: 'Buat Order', menu: 'Order › Buat Order',
        detail: 'Pilih buyer, model "Sweater Klasik V-Neck", qty 200, size M, delivery 30 Jun.' },
      { portal: 'produksi', title: 'Generate WO', menu: 'Order detail › Generate WO',
        detail: 'WO otomatis terbuat dengan status Draft.' },
      { portal: 'produksi', title: 'Review & Release WO', menu: 'WO detail › Release',
        detail: 'Cek BOM lengkap → klik Release → status Released, material auto-reserved.' },
      { portal: 'produksi', title: 'Buat LKP', menu: 'WO detail › Buat LKP',
        detail: '5-step wizard isi instruksi → Generate PDF → bagikan ke operator.' },
      { portal: 'produksi', title: 'Assign Lini', menu: 'Eksekusi › Assign Lini Hari Ini',
        detail: 'Pilih tanggal → assign operator ke Line A.' },
      { portal: 'produksi', title: 'Issue Material', menu: 'Eksekusi › Bulk MI',
        detail: 'Pilih WO → konfirmasi → material keluar dari gudang.' },
      { portal: 'produksi', title: 'Update Progress', menu: 'WO detail',
        detail: 'Operator/supervisor isi qty_produced harian.' },
      { portal: 'qc', title: 'QC Inspeksi', menu: 'QC › Inspect',
        detail: '200 pcs lulus QC → qty_passed_qc = 200.' },
      { portal: 'produksi', title: 'WO Complete', menu: 'WO detail',
        detail: 'Ubah status WO → Completed.' },
      { portal: 'shift', title: 'Shift Handover', menu: 'Eksekusi › Shift Handover',
        detail: 'Buat handover akhir shift, checklist OK, download PDF.' },
    ],
    expectedResults: [
      'WO status: Completed',
      'LKP PDF tersimpan & bisa dicetak ulang',
      'Stok material berkurang sesuai BOM',
      'Shift Handover ter-sign-off, PDF bisa di-download',
    ],
  },
  {
    id: 's2',
    code: 'S2',
    title: 'Ada Defect — Tidak Lulus QC → Rework',
    description: '200 pcs diproduksi, 30 pcs cacat (jahitan lepas), harus rework.',
    difficulty: 'menengah',
    estimatedTime: '+1-2 hari ekstra (untuk rework)',
    personas: ['produksi', 'qc'],
    prerequisites: [
      'Skenario S1 langkah 1-7 sudah dijalankan (WO sudah produksi 200 pcs)',
      'Kode defect sudah terdaftar di master (mis: jaitan-lepas, lubang, salah-warna)',
      'Operator rework sudah ditentukan',
      'LKP sudah ada untuk WO terkait (untuk upload foto evidence)',
    ],
    steps: [
      { portal: 'qc', title: 'QC Check', menu: 'QC › Inspect',
        detail: '170 lulus, 30 defect (kode: jaitan-lepas).' },
      { portal: 'produksi', title: 'Update WO', menu: 'WO detail',
        detail: 'qty_passed_qc = 170, qty_rework = 30.' },
      { portal: 'produksi', title: 'Tambah Rework', menu: 'Eksekusi › Papan Rework',
        detail: 'Isi WO, qty 30, jenis defect, assign operator rework.' },
      { portal: 'produksi', title: 'Upload Foto Defect', menu: 'LKP detail › Upload Foto',
        detail: 'Caption "Defect: jahitan lepas area bahu", tipe defect_evidence.' },
      { portal: 'produksi', title: 'Rework Selesai', menu: 'Papan Rework',
        detail: '28 pcs sukses rework, 2 pcs reject total.' },
      { portal: 'produksi', title: 'Update Final', menu: 'WO detail',
        detail: 'qty_passed_qc = 198, qty_reject = 2.' },
      { portal: 'shift', title: 'Catat di Handover', menu: 'Shift Handover',
        detail: 'Issues: tipe "kualitas", deskripsi & priority "medium".' },
      { portal: 'produksi', title: 'Download LKP PDF', menu: 'LKP › Download',
        detail: 'Section L menampilkan foto defect.' },
    ],
    expectedResults: [
      'Papan Rework terdokumentasi',
      'Foto defect muncul di LKP PDF Section L',
      'Shift handover mencatat masalah kualitas',
      'Net output: 198 pcs (bukan 200)',
    ],
  },
  {
    id: 's3',
    code: 'S3',
    title: 'Material Kurang — Produksi Tertunda',
    description: 'Stok bahan tidak cukup saat WO di-release. Sistem kasih warning.',
    difficulty: 'menengah',
    estimatedTime: '~1-3 hari (tunggu PO datang)',
    personas: ['produksi', 'gudang'],
    prerequisites: [
      'WO Draft sudah ada dengan BOM yang komplit',
      'Master supplier sudah terdaftar',
      'Threshold low stock sudah dikonfigurasi per material',
      'Stok bahan YRN-W-002 di bawah kebutuhan WO (intentional shortage)',
    ],
    steps: [
      { portal: 'produksi', title: 'Release WO', menu: 'WO › Release',
        detail: 'Sistem auto-reserve material.' },
      { portal: 'produksi', title: 'Cek Warning', menu: 'API response',
        detail: '"material_reservation.warnings: Stok YRN-W-002 tidak cukup: butuh 45kg, tersedia 30kg".' },
      { portal: 'gudang', title: 'Lihat Low Stock', menu: 'Inventori › Bahan',
        detail: 'Badge merah pada YRN-W-002.' },
      { portal: 'pengadaan', title: 'Buat PO', menu: 'Permintaan & Pesanan › Purchase Order',
        detail: 'Order ke supplier YRN-W-002 qty 100kg (supplier dipilih dari Master Supplier).' },
      { portal: 'shift', title: 'Catat Issue', menu: 'Shift Handover',
        detail: 'Tipe "material", priority "high", deskripsi shortage + status PO.' },
      { portal: 'gudang', title: 'Receiving', menu: 'Penerimaan Barang',
        detail: 'Konfirmasi terima 100kg → stok bertambah otomatis.' },
      { portal: 'produksi', title: 'Lanjutkan Produksi', menu: 'Bulk MI',
        detail: 'Issue material → produksi berjalan.' },
    ],
    expectedResults: [
      'Warning muncul saat release WO',
      'Low stock badge terlihat di modul material',
      'PO terdokumentasi & ter-receive',
      'Shift handover mencatat masalah material',
    ],
  },
  {
    id: 's4',
    code: 'S4',
    title: 'Mesin Breakdown — OEE Turun',
    description: 'Mesin Rajut M-001 breakdown 3 jam di Line A, OEE hari ini turun.',
    difficulty: 'menengah',
    estimatedTime: '~3 jam (event); ~10 menit (input sistem)',
    personas: ['produksi'],
    prerequisites: [
      'Mesin M-001 terdaftar di Master Mesin & assigned ke Line A',
      'WO aktif sedang berjalan di Line A',
      'Reason code downtime sudah ada (mesin-rusak, listrik, dll)',
      'OEE Dashboard sudah ada baseline data minggu ini',
    ],
    steps: [
      { portal: 'produksi', title: 'Operator Lapor', menu: '—',
        detail: 'Mesin M-001 mati jam 09:00.' },
      { portal: 'shift', title: 'Buat Shift Handover (mid-shift)', menu: 'Shift Handover',
        detail: 'Checklist downtime ✓, issue tipe "mesin" priority "high", task "Hubungi teknisi".' },
      { portal: 'produksi', title: 'Lihat OEE', menu: 'Monitoring › OEE',
        detail: 'Line A OEE turun → drill-down → downtime events terlihat.' },
      { portal: 'produksi', title: 'Mesin Diperbaiki', menu: '—',
        detail: 'Jam 12:00 (downtime 3 jam dari 8 jam = Availability 62.5%).' },
      { portal: 'shift', title: 'Sign-Off Handover', menu: 'Shift Handover',
        detail: 'Notes "M-001 sudah ok jam 12:00".' },
      { portal: 'shift', title: 'Download PDF', menu: 'Shift Handover › PDF',
        detail: 'End-of-Shift report tergenerate.' },
    ],
    expectedResults: [
      'OEE Line A turun (availability < 100%)',
      'Downtime terdokumentasi di shift handover & OEE dashboard',
      'Sign-off dengan catatan perbaikan',
      'PDF report lengkap',
    ],
  },
  {
    id: 's5',
    code: 'S5',
    title: 'Shift Malam — Serah Terima Lengkap',
    description: 'Shift 1 (07:00-15:00) selesai, serah terima ke Shift 2 (15:00-23:00).',
    difficulty: 'pemula',
    estimatedTime: '~15 menit',
    personas: ['shift'],
    prerequisites: [
      'Master Shift sudah terdaftar (S1, S2, S3 dengan jam masing-masing)',
      'Supervisor Shift 1 & Shift 2 sudah login',
      'WO aktif dengan progress data shift 1',
    ],
    steps: [
      { portal: 'shift', title: 'Buat Handover Shift 1', menu: 'Shift Handover › Baru',
        detail: 'Pilih Shift 1, isi catatan, checklist 5 item, issues, pending tasks.' },
      { portal: 'shift', title: 'Shift 2 Lihat Handover', menu: 'Shift Handover › Tab Hari Ini',
        detail: '—' },
      { portal: 'shift', title: 'Sign Off', menu: 'Card › Sign Off',
        detail: 'Notes "Diterima, siap dilanjutkan".' },
      { portal: 'shift', title: 'Download PDF', menu: 'Detail › PDF',
        detail: 'Arsip dokumen serah terima.' },
    ],
    expectedResults: [
      'Handover terdaftar dengan status "Signed Off"',
      'Badge "Signed Off" hijau di kartu',
      'PDF lengkap dengan blok tanda tangan kedua supervisor',
    ],
  },
  {
    id: 's6',
    code: 'S6',
    title: 'Hari Libur — APS Skip Otomatis',
    description: '1 Mei (Hari Buruh) — pabrik libur. APS perlu tahu ini.',
    difficulty: 'pemula',
    estimatedTime: '~5 menit',
    personas: ['produksi', 'manajemen'],
    prerequisites: [
      'User punya akses ke Kalender Produksi (admin/produksi)',
      'Tahun berjalan belum di-seed libur nasional',
    ],
    steps: [
      { portal: 'produksi', title: 'Seed Libur Nasional', menu: 'Master Data › Kalender Produksi',
        detail: 'Klik "Seed Libur Nasional 2026" → 20 hari otomatis masuk.' },
      { portal: 'produksi', title: 'Cek APS Gantt', menu: 'Monitoring › APS',
        detail: 'Tanggal 1 Mei berwarna merah, tooltip "Hari Buruh Internasional".' },
      { portal: 'produksi', title: 'Auto-Schedule', menu: 'APS › Auto-Schedule',
        detail: 'Sistem skip tanggal merah otomatis.' },
      { portal: 'produksi', title: 'Cek Kalkulator', menu: 'Kalender › Kalkulator Hari Kerja',
        detail: 'Mei 2026 = 20 hari kerja.' },
    ],
    expectedResults: [
      'Hari libur merah di APS Gantt',
      'Auto-schedule skip hari libur',
      'Kalkulator hari kerja akurat',
    ],
  },
  {
    id: 's7',
    code: 'S7',
    title: 'New Buyer — Full Flow dari Nol',
    description: 'Buyer baru dari Korea pesan 500 pcs cardigan, model belum pernah diproduksi.',
    difficulty: 'lanjut',
    estimatedTime: '~1-2 minggu (real); ~1 jam (setup sistem)',
    personas: ['manajemen', 'produksi', 'gudang'],
    prerequisites: [
      'Akses admin/manager untuk membuat master data baru',
      'Foto sample dari buyer sudah ada (untuk LKP)',
      'Spesifikasi tech-pack model dari buyer',
      'Daftar material yang dibutuhkan (bahan, aksesoris)',
    ],
    steps: [
      { portal: 'manajemen', title: 'Tambah Customer', menu: 'Master › Customer',
        detail: 'Profil buyer baru "K-Fashion Ltd".' },
      { portal: 'manajemen', title: 'Tambah Model', menu: 'Master Data › Model Produk',
        detail: 'Model "Cardigan Korea 2026", upload foto desain.' },
      { portal: 'produksi', title: 'Buat BOM', menu: 'BOM › Tambah',
        detail: 'Input kebutuhan material per pcs.' },
      { portal: 'produksi', title: 'Buat SOP', menu: 'SOP › Tambah',
        detail: 'Input langkah kerja + SAM + target pcs/jam.' },
      { portal: 'manajemen', title: 'Buat Order', menu: 'Order › Buat',
        detail: 'K-Fashion 500 pcs Cardigan, delivery 15 Juli.' },
      { portal: 'produksi', title: 'Auto-Schedule', menu: 'APS › Auto-Schedule',
        detail: 'Sistem bagi ke beberapa lini.' },
      { portal: 'produksi', title: 'Generate WO', menu: 'Order › Generate',
        detail: '3 WO: Line A 200, Line B 150, Line C 150.' },
      { portal: 'pengadaan', title: 'Cek Material & PO', menu: 'Purchase Order',
        detail: 'Buat PO jika stok kurang.' },
      { portal: 'produksi', title: 'Release Semua WO', menu: 'WO › Release',
        detail: 'Material auto-reserve.' },
      { portal: 'produksi', title: 'Buat LKP per WO', menu: 'LKP › Buat',
        detail: 'Upload foto sample buyer.' },
      { portal: 'produksi', title: 'Lanjut S1', menu: '—',
        detail: 'Lanjutkan dengan flow Skenario 1 (produksi normal).' },
    ],
    expectedResults: [
      'Master data model & SOP tersedia sebelum produksi',
      'APS bisa schedule semua 3 WO sekaligus',
      'LKP berisi foto sample buyer',
    ],
  },
  {
    id: 's8',
    code: 'S8',
    title: 'Lembur & Payroll Akhir Bulan',
    description: 'Ada lembur di akhir bulan, payroll harus akurat.',
    difficulty: 'menengah',
    estimatedTime: '~1-2 jam (review + run payroll)',
    personas: ['sdm', 'keuangan'],
    prerequisites: [
      'Master karyawan + payroll profile lengkap (skema, base rate)',
      'Cutoff payroll bulan berjalan sudah ditentukan',
      'Data attendance bulan ini sudah lengkap (termasuk lembur)',
      'CoA Payroll-related sudah ter-set up',
    ],
    steps: [
      { portal: 'sdm', title: 'Input Lembur', menu: 'SDM › Absensi',
        detail: 'Input jam lembur per karyawan.' },
      { portal: 'sdm', title: 'Export Review', menu: 'Absensi › Export',
        detail: 'Excel data attendance untuk validasi.' },
      { portal: 'keuangan', title: 'Validasi Payroll', menu: 'Payroll › Periksa Sekarang',
        detail: 'Sistem cek anomali (lembur > 3 jam tanpa approval, dll).' },
      { portal: 'keuangan', title: 'Selesaikan Warning', menu: '—',
        detail: 'Approve / koreksi anomali.' },
      { portal: 'keuangan', title: 'Proses Payroll', menu: 'Payroll › Run',
        detail: 'Hitung gaji + lembur + tunjangan - potongan.' },
      { portal: 'keuangan', title: 'Cetak Slip', menu: 'Payroll › Slip',
        detail: 'Generate slip semua karyawan.' },
      { portal: 'sdm', title: 'Laporan Lembur', menu: 'SDM › Laporan',
        detail: 'Export Excel → kirim manajemen.' },
    ],
    expectedResults: [
      'Lembur terhitung otomatis',
      'Warning anomali absensi terdeteksi sebelum payroll',
      'Slip gaji akurat',
      'Laporan lembur ter-export',
    ],
  },
];

/* ─────────────────────────────────────────────────────────
 * Tips, FAQ & Troubleshooting
 * ───────────────────────────────────────────────────────── */
export const TIPS = {
  daily: [
    { icon: 'production', title: 'Produksi', items: [
      'Selalu Release WO sebelum issue material — sistem otomatis reserve',
      'Upload foto LKP segera setelah QC — foto muncul di PDF download berikutnya',
      'Buat Shift Handover di akhir setiap shift — bukan hanya saat ada masalah',
      'Pakai "Copy dari Kemarin" untuk Assign Lini — hemat waktu',
    ]},
    { icon: 'warehouse', title: 'Gudang', items: [
      'Receiving harus sertakan material_id — agar stok ter-update otomatis',
      'Cek low-stock dashboard tiap pagi — antisipasi shortage',
      'Lakukan opname rutin (mingguan/bulanan) — data tetap akurat',
    ]},
    { icon: 'finance', title: 'Keuangan', items: [
      'Jalankan validasi attendance sebelum Run Payroll',
      'Review jurnal otomatis (opname, payroll) sebelum tutup buku',
    ]},
  ],
  faq: [
    { q: 'Mengapa foto LKP belum muncul di PDF?',
      a: 'Foto muncul setelah download ulang. Sistem otomatis re-generate PDF kalau ada upload baru (pdf_stale=True).' },
    { q: 'Bagaimana cara reset password?',
      a: 'Hubungi admin sistem. Admin bisa reset via SDM › Karyawan › User Account.' },
    { q: 'WO tidak bisa di-release, kenapa?',
      a: 'Cek apakah BOM komplit & stok material cukup. Sistem block release kalau material kurang (kecuali force).' },
    { q: 'OEE saya 0, kenapa?',
      a: 'OEE perlu data baseline (target produksi, downtime events). Pastikan SOP punya target & lini punya assignment hari ini.' },
    { q: 'Apakah bisa rollback jurnal?',
      a: 'Ya, lewat Akuntansi › Jurnal › klik jurnal → Reverse. Akan buat jurnal balik (kontra).' },
  ],
  troubleshoot: [
    { issue: 'PDF LKP gagal di-download',
      sol: 'Cek koneksi internet. Klik "Regenerate" di detail LKP. Kalau masih error, lihat log audit di tab Audit.' },
    { issue: 'Stok minus setelah issue',
      sol: 'Pasti ada bug data. Stop issue, lakukan opname segera, lalu adjustment ke GL.' },
    { issue: 'Auto-schedule APS tidak skip libur',
      sol: 'Pastikan Kalender Produksi sudah seed libur nasional + tahun berjalan ada di range.' },
  ],
};
