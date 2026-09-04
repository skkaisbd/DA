import {
  ClipboardList, ClipboardSignature, Boxes, Hammer, UserCheck, Zap, ClipboardPen,
  Package, Activity, BarChart4, Siren, AlertTriangle, Gauge, LayoutGrid,
  CalendarClock, FileText, Calendar, ListChecks, Filter, Search, Plus, Edit, Trash2,
  Download, Upload, Printer, Eye, RefreshCw, CheckCircle2, X as XIcon,
  Sparkles, BookOpen,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────
 * Help Content Per Modul (Portal Produksi)
 *
 * Struktur:
 * { moduleId: {
 *     title, icon, screenshot (path public), purpose, whoUses,
 *     buttons: [{label, icon, action, when}],
 *     tips: [string], warnings: [string], relatedScenarios: ['s1', 's2'],
 *     tour: [{selector, title, content, position}]
 *   }
 * }
 * ───────────────────────────────────────────────────────── */

export const MODULE_HELP = {
  /* ╔══════════════ RINGKASAN ══════════════╗ */

  'production-dashboard': {
    title: 'Dashboard Produksi',
    icon: Gauge,
    screenshot: '/guide/screenshots/production-dashboard.png',
    purpose:
      'Dashboard pusat kontrol produksi dengan KPI real-time: WO aktif, output harian, OEE, alert. Cocok untuk supervisor & manager memantau performa lini.',
    whoUses: 'Supervisor, Manager Produksi, PPIC',
    sections: [
      'KPI Cards (atas) — angka utama hari ini',
      'Throughput Chart — grafik output 7-30 hari',
      'Status WO breakdown — distribusi status work order',
      'Top Issues — masalah yang paling sering muncul',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Filter, action: 'Ganti rentang waktu data (Hari Ini / 7 Hari / 30 Hari)', when: 'Saat ingin lihat tren historis' },
      { label: 'Refresh', icon: RefreshCw, action: 'Muat ulang data dashboard', when: 'Manual update; auto-refresh 5 menit' },
    ],
    tips: [
      'Refresh otomatis tiap 5 menit, tidak perlu reload manual',
      'Klik KPI card untuk drill-down ke modul terkait',
      'OEE rendah? Cek Dashboard OEE untuk lihat breakdown',
    ],
    relatedScenarios: ['s1', 's4'],
  },

  'prod-line-board': {
    title: 'Papan Lini Produksi',
    icon: LayoutGrid,
    screenshot: '/guide/screenshots/prod-line-board.png',
    purpose:
      'Papan visual real-time per lini — siapa yang bekerja, mesin apa yang aktif, progres output vs target. Ideal sebagai monitor di lantai produksi.',
    whoUses: 'Supervisor, Operator',
    sections: [
      'Per Lini Card — info lini, operator, mesin, target vs actual',
      'Color-coded status — hijau on-track, kuning at-risk, merah behind',
      'Auto-refresh setiap 30 detik',
    ],
    buttons: [
      { label: 'Filter Lini', icon: Filter, action: 'Tampilkan hanya lini tertentu (mis: hanya lini saya)', when: 'Saat fokus 1-2 lini' },
      { label: 'Mode TV', icon: Eye, action: 'Mode fullscreen untuk monitor TV di pabrik', when: 'Pasang di shop floor' },
    ],
    tips: [
      'Buka di tab terpisah dengan mode TV untuk monitoring lantai',
      'Card merah → segera intervensi (briefing operator atau cek mesin)',
    ],
    relatedScenarios: ['s4'],
  },

  'prod-aps-gantt': {
    title: 'Penjadwalan APS (Gantt)',
    icon: CalendarClock,
    screenshot: '/guide/screenshots/prod-aps-gantt.png',
    purpose:
      'Advanced Planning & Scheduling visualisasi Gantt — semua WO terjadwal per lini per hari. AI auto-schedule berdasarkan due date & kapasitas.',
    whoUses: 'PPIC, Supervisor',
    sections: [
      'Timeline horizontal (hari) × Lini (vertikal)',
      'WO sebagai bar berwarna — panjang = durasi, warna = priority',
      'Kolom merah = hari libur (dari Kalender Produksi)',
      'Tab Line Balance — keseimbangan beban antar lini',
    ],
    buttons: [
      { label: 'Auto-Schedule', icon: Zap, action: 'AI optimalkan urutan WO berdasarkan due-date + kapasitas + libur', when: 'Setelah generate WO baru atau saat ada perubahan kapasitas' },
      { label: 'Filter Lini/Status', icon: Filter, action: 'Tampilkan WO tertentu saja', when: 'Saat lihat WO urgent saja' },
      { label: 'Refresh', icon: RefreshCw, action: 'Muat ulang jadwal terbaru', when: 'Setelah update WO manual' },
    ],
    tips: [
      'Sebelum auto-schedule, pastikan Kalender Produksi sudah seed libur',
      'Drag bar WO untuk reschedule manual (override AI)',
      'Hover bar → tooltip detail WO',
    ],
    warnings: [
      'Auto-schedule akan replace jadwal yang sudah ada — backup dulu kalau perlu',
    ],
    relatedScenarios: ['s6', 's7'],
  },

  /* ╔══════════════ EKSEKUSI ══════════════╗ */

  'prod-orders': {
    title: 'Order Produksi',
    icon: ClipboardList,
    screenshot: '/guide/screenshots/prod-orders.png',
    purpose:
      'Daftar order dari customer/buyer. Setiap order bisa di-generate menjadi multiple Work Orders untuk produksi.',
    whoUses: 'Manager Produksi, PPIC, Sales',
    sections: [
      'Tabel order dengan kolom: kode, customer, model, qty, due date, status',
      'Filter status: Draft / Confirmed / In Production / Shipped',
      'Detail Order menampilkan: WO terkait, progress %',
    ],
    buttons: [
      { label: 'Buat Order', icon: Plus, action: 'Tambah order baru: pilih customer, model, qty, size, delivery date', when: 'Customer kasih PO baru' },
      { label: 'Generate WO', icon: Zap, action: 'Otomatis buat Work Order(s) dari order — bisa 1 WO atau dipecah per lini', when: 'Order sudah confirmed & siap produksi' },
      { label: 'Edit', icon: Edit, action: 'Ubah qty/due-date sebelum WO dibuat', when: 'Order belum di-generate WO' },
      { label: 'Lihat Detail', icon: Eye, action: 'Buka detail order + daftar WO terkait', when: 'Cek progress order' },
    ],
    tips: [
      'Order harus Confirmed sebelum bisa Generate WO',
      'Setelah WO dibuat, qty order tidak bisa diubah lagi',
      'Pastikan model & customer sudah ada di master data',
    ],
    relatedScenarios: ['s1', 's7'],
  },

  'prod-work-orders': {
    title: 'Work Order',
    icon: ClipboardSignature,
    screenshot: '/guide/screenshots/prod-work-orders.png',
    purpose:
      'Surat perintah kerja yang menggerakkan lantai produksi. Setiap WO punya BOM, target qty, lini, due-date. Inti operasional produksi.',
    whoUses: 'Supervisor, PPIC, Operator',
    sections: [
      'Tabel WO dengan filter status, lini, due-date',
      'Detail WO: BOM, progress, LKP, riwayat, audit',
      'Aksi cepat: Release, Bulk Print LKP',
    ],
    buttons: [
      { label: 'Buat WO Manual', icon: Plus, action: 'Tambah WO langsung tanpa lewat order', when: 'Internal stock production atau sample' },
      { label: 'Release WO', icon: CheckCircle2, action: 'Status Draft → Released. Otomatis reserve material sesuai BOM', when: 'Material cukup & lini siap' },
      { label: 'Buat LKP', icon: FileText, action: 'Generate Lembar Kerja Produksi (instruksi kerja)', when: 'Setelah WO Released, sebelum produksi' },
      { label: 'Cetak LKP Massal', icon: Printer, action: 'Lihat status LKP semua WO aktif & cetak massal', when: 'Awal hari atau awal shift' },
      { label: 'Filter & Search', icon: Search, action: 'Cari WO berdasarkan kode, model, status', when: 'Database besar' },
    ],
    tips: [
      'Saat Release: sistem auto-reserve material — pastikan stok cukup',
      'Status WO tidak bisa skip (harus Draft → Released → In Progress → Completed)',
      'LKP wajib ada sebelum operator mulai kerja',
    ],
    warnings: [
      'Material kurang saat Release → muncul warning, tapi WO tetap Released. Cek warnings di response.',
      'Cancelled WO tidak bisa dilanjutkan — harus buat WO baru',
    ],
    relatedScenarios: ['s1', 's2', 's3'],
    tour: [
      { selector: '[data-testid="rahaza-work-orders-page"]', title: 'Halaman Work Order', content: 'Ini adalah pusat kontrol semua WO. Dari sini Anda bisa buat, release, dan kelola lifecycle WO.', position: 'bottom' },
      { selector: '[data-testid="wo-add-btn"]', title: 'Buat WO Manual', content: 'Klik untuk membuat WO baru manual (di luar yang di-generate dari Order). Cocok untuk produksi internal/sample.', position: 'bottom' },
      { selector: '[data-testid="bulk-lkp-btn"]', title: 'Cetak LKP Massal', content: 'Lihat & cetak LKP semua WO aktif sekaligus. Ideal di awal hari/shift.', position: 'bottom' },
      { selector: 'table', title: 'Tabel WO', content: 'Daftar semua WO. Klik baris untuk lihat detail (BOM, progress, LKP, riwayat). Filter & sort tersedia di header tabel.', position: 'top' },
    ],
  },

  'prod-bundles': {
    title: 'Penelusuran Bundle',
    icon: Boxes,
    screenshot: '/guide/screenshots/prod-bundles.png',
    purpose:
      'Track bundle (kumpulan pcs sejenis) dari proses ke proses — dari rajut sampai packing. Genealogy untuk traceability.',
    whoUses: 'Supervisor, QC',
    sections: [
      'Tabel bundle: kode, WO, model, qty, current process, status',
      'Detail bundle: timeline event (rajut → linking → washing → QC → pack)',
      'QR Code per bundle (scan dari mesin scanner)',
    ],
    buttons: [
      { label: 'Scan Bundle', icon: Search, action: 'Buka kamera/scanner, scan QR bundle untuk update status', when: 'Bundle pindah proses' },
      { label: 'Detail Bundle', icon: Eye, action: 'Lihat seluruh riwayat bundle (created, moved, QC, etc.)', when: 'Investigasi defect / customer complain' },
    ],
    tips: [
      'QR scanner butuh kamera — pakai HP/tablet di lantai',
      'Kalau bundle hilang status, scan ulang',
    ],
    relatedScenarios: ['s2'],
  },

  'prod-rework-board': {
    title: 'Papan Rework',
    icon: Hammer,
    screenshot: '/guide/screenshots/prod-rework-board.png',
    purpose:
      'Manajemen item yang gagal QC dan perlu rework. Closed-loop tracking sampai pcs lulus QC kembali.',
    whoUses: 'Supervisor QC, Operator Rework',
    sections: [
      'Tabel rework: WO, qty, defect code, status, assigned operator',
      'Status: Open → In Progress → Re-QC → Pass / Reject',
      'Defect code terstandardisasi (jaitan-lepas, lubang, salah-warna, dll)',
    ],
    buttons: [
      { label: 'Tambah Rework', icon: Plus, action: 'Daftarkan pcs defect untuk rework', when: 'QC fail di-detect' },
      { label: 'Update Status', icon: Edit, action: 'Pindahkan status (mulai rework / re-QC / pass)', when: 'Operator selesai rework' },
      { label: 'Filter', icon: Filter, action: 'Filter per status, per operator, per WO', when: 'Banyak rework aktif' },
    ],
    tips: [
      'Pakai defect code dari master, jangan free text',
      'Rework yang gagal 2x → reject (tidak bisa rework selamanya)',
      'Foto evidence wajib untuk defect besar',
    ],
    relatedScenarios: ['s2'],
  },

  'prod-assignments': {
    title: 'Assign Lini Hari Ini',
    icon: UserCheck,
    screenshot: '/guide/screenshots/prod-assignments.png',
    purpose:
      'Tentukan karyawan & mesin per lini & shift hari ini. Kunci agar Operator View tahu siapa kerja di mana.',
    whoUses: 'Supervisor, Leader Lini',
    sections: [
      'Pilih tanggal & lini',
      'Form assignment: shift, operator, mesin, proses',
      'Bulk action: Copy dari Kemarin / Auto-Assign Template',
    ],
    buttons: [
      { label: 'Copy dari Kemarin', icon: RefreshCw, action: '1-klik salin assignment dari hari sebelumnya', when: 'Hari rutin tanpa banyak perubahan' },
      { label: 'Auto-Assign Template', icon: Zap, action: 'Pakai template tersimpan (mis: "shift pagi standar")', when: 'Sudah punya pola assignment' },
      { label: 'Tambah Assignment', icon: Plus, action: 'Manual assign karyawan ke lini+shift+mesin', when: 'Custom atau ada karyawan baru' },
    ],
    tips: [
      'Lakukan SETIAP hari — kalau lupa, Operator View akan kosong',
      'Karyawan absent? Sistem akan suggest pengganti',
      'Simpan pola sering pakai sebagai Template',
    ],
    relatedScenarios: ['s1', 's5'],
  },

  'prod-bulk-mi': {
    title: 'Bulk Material Issue',
    icon: Zap,
    screenshot: '/guide/screenshots/prod-bulk-mi.png',
    purpose:
      'Keluarkan material ke lantai produksi untuk banyak WO sekaligus dalam 1 transaksi. Hemat waktu vs MI per WO.',
    whoUses: 'Staff Gudang, Supervisor',
    sections: [
      'Filter WO (default: in_progress)',
      'Pilih WO yang akan di-issue (checkbox)',
      'Preview material aggregate (BOM × qty per WO)',
      'Konfirmasi → stok terkurangi & pergerakan tercatat',
    ],
    buttons: [
      { label: 'Filter Status WO', icon: Filter, action: 'Switch ke "released" atau "in_progress"', when: 'Issue WO yang baru di-release' },
      { label: 'Pilih Semua', icon: CheckCircle2, action: 'Centang semua WO sekaligus', when: 'Issue rutin awal hari' },
      { label: 'Preview', icon: Eye, action: 'Lihat material aggregate yang akan di-issue', when: 'Sebelum konfirmasi' },
      { label: 'Konfirmasi Issue', icon: Zap, action: 'Eksekusi issue — stok terkurangi & pergerakan tercatat', when: 'Setelah preview cocok' },
    ],
    tips: [
      'Cek stok cukup sebelum issue (badge merah = kurang)',
      'Issue tidak bisa di-undo — buat reverse manual via Adjustment',
      'Bulk MI hari ini idealnya pagi sebelum produksi mulai',
    ],
    warnings: [
      'Stok minus akan diizinkan tapi muncul warning. Lakukan opname segera.',
    ],
    relatedScenarios: ['s1', 's3'],
    tour: [
      { selector: '[data-testid="bulk-mi-page"]', title: 'Halaman Bulk Material Issue', content: 'Keluarkan material untuk banyak WO sekaligus dalam 1 transaksi. Hemat waktu dibandingkan MI 1-by-1.', position: 'bottom' },
      { selector: '[data-testid="bmi-preview-btn"]', title: 'Tombol Preview', content: 'Lihat agregat material yang akan di-issue (BOM × qty per WO yang dipilih). Wajib preview sebelum konfirmasi.', position: 'top' },
    ],
  },

  'prod-shift-handover': {
    title: 'Shift Handover',
    icon: ClipboardPen,
    screenshot: '/guide/screenshots/prod-shift-handover.png',
    purpose:
      'Serah terima shift dengan checklist standar, log issues, pending tasks, dan PDF report. Wajib di akhir setiap shift.',
    whoUses: 'Supervisor Shift',
    sections: [
      'Tab "Hari Ini" / "Riwayat" — handover aktif vs lama',
      '5 Checklist standar: target, quality, downtime, material, K3',
      'Issues + priority (low/medium/high/critical)',
      'Pending tasks untuk shift berikutnya',
      'Sign-off oleh shift penerima',
    ],
    buttons: [
      { label: 'Buat Handover Baru', icon: Plus, action: 'Pilih shift & tanggal, isi checklist, issues, tasks', when: 'Akhir shift' },
      { label: 'Sign Off', icon: CheckCircle2, action: 'Supervisor shift berikutnya konfirmasi diterima', when: 'Awal shift baru' },
      { label: 'Download PDF', icon: Download, action: 'Generate End-of-Shift PDF report (lengkap dengan tanda tangan)', when: 'Arsip atau kirim manajemen' },
      { label: 'Edit', icon: Edit, action: 'Ubah handover (selama belum sign-off)', when: 'Ada koreksi' },
    ],
    tips: [
      'Buat handover SETIAP shift — bukan hanya saat ada masalah',
      'Issues priority "high/critical" → escalate ke manager',
      'Sign-off = konfirmasi shift baru terima info',
    ],
    relatedScenarios: ['s4', 's5'],
    tour: [
      { selector: '[data-testid="shift-handover-page"]', title: 'Halaman Shift Handover', content: 'Manajemen serah terima shift dengan checklist standar, log issues, & PDF report.', position: 'bottom' },
      { selector: '[data-testid="new-handover-btn"]', title: 'Buat Handover Baru', content: 'Klik untuk mulai handover akhir shift. Pilih shift, isi checklist 5 item, issues, dan pending tasks.', position: 'bottom' },
    ],
  },

  'prod-material-reservation': {
    title: 'Reservasi Material',
    icon: Package,
    screenshot: '/guide/screenshots/prod-material-reservation.png',
    purpose:
      'Stok yang sudah di-booking (reserved) untuk WO tertentu. Auto-reserve saat WO di-Release. Manual reserve juga bisa.',
    whoUses: 'Supervisor, PPIC, Staff Gudang',
    sections: [
      'Tab "Per Work Order" — reservasi per WO',
      'Tab "Per Material" — overview stok dengan availability bar',
      'Status: reserved / partial-issued / fully-issued / released',
    ],
    buttons: [
      { label: 'Buat Reservasi', icon: Plus, action: 'Manual reserve material untuk WO (kalau auto-reserve gagal)', when: 'Special case atau material non-BOM' },
      { label: 'Release Reservasi', icon: XIcon, action: 'Lepas reservasi → stok kembali available', when: 'WO cancelled atau qty di-revisi' },
      { label: 'Filter Status', icon: Filter, action: 'Filter per WO, per material, per status', when: 'Banyak reservasi aktif' },
    ],
    tips: [
      'Stok Tersedia = Stok Total - Reserved',
      'Auto-reserve hanya jalan saat Release WO',
      'Cek tab Per Material untuk lihat material kritis',
    ],
    relatedScenarios: ['s3'],
    tour: [
      { selector: '[data-testid="material-reservation-page"]', title: 'Halaman Reservasi Material', content: 'Stok yang sudah di-booking untuk WO tertentu. Auto-reserve saat WO Release.', position: 'bottom' },
      { selector: '[data-testid="new-reservation-btn"]', title: 'Buat Reservasi Manual', content: 'Untuk kasus khusus dimana auto-reserve tidak cukup. Pilih WO + material + qty.', position: 'bottom' },
    ],
  },

  /* ╔══════════════ MONITORING ══════════════╗ */

  'prod-oee': {
    title: 'Dashboard OEE',
    icon: Activity,
    screenshot: '/guide/screenshots/prod-oee.png',
    purpose:
      'Overall Equipment Effectiveness per lini & mesin. Formula: OEE = Availability × Performance × Quality. World-class target ≥ 85%.',
    whoUses: 'Manager Produksi, Supervisor',
    sections: [
      'KPI utama: OEE keseluruhan + 3 komponen (A, P, Q)',
      'Drill-down per lini & per mesin',
      'Downtime events (mesin breakdown, dll) — feed Availability',
      'Trend chart 7-30 hari',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Filter, action: 'Hari Ini / 7 Hari / 30 Hari', when: 'Lihat tren' },
      { label: 'Drill-down Lini', icon: Eye, action: 'Klik lini → detail downtime events', when: 'Investigasi OEE rendah' },
    ],
    tips: [
      'Availability rendah → mesin sering breakdown / changeover lama',
      'Performance rendah → operator slow / target tidak realistis',
      'Quality rendah → defect tinggi (cek Pareto Defect)',
    ],
    warnings: [
      'OEE 0% biasanya karena: tidak ada assignment hari ini, atau SOP belum punya target',
    ],
    relatedScenarios: ['s4'],
  },

  'prod-line-balance': {
    title: 'Line Balancing',
    icon: BarChart4,
    screenshot: '/guide/screenshots/prod-line-balance.png',
    purpose:
      'Analisis keseimbangan beban antar stasiun kerja dalam 1 lini. Identifikasi bottleneck & sub-utilized.',
    whoUses: 'Industrial Engineer, Supervisor, PPIC',
    sections: [
      'Bar chart per stasiun: cycle time vs target',
      'SAM (Standard Allowed Minute) per proses',
      'Efficiency factor & balance loss %',
    ],
    buttons: [
      { label: 'Pilih Lini & WO', icon: Filter, action: 'Analisis lini tertentu untuk WO tertentu', when: 'Setup lini baru atau model baru' },
    ],
    tips: [
      'Bottleneck (paling tinggi) = batasi output lini',
      'Operator stasiun under-utilized bisa dialihkan',
      'Re-balance saat model baru atau qty besar',
    ],
  },

  'prod-rework-analytics': {
    title: 'Analitik Rework',
    icon: BarChart4,
    screenshot: '/guide/screenshots/prod-rework-analytics.png',
    purpose:
      'Statistik rework — Pareto defect (top defects), trend per minggu, breakdown per operator/lini/model.',
    whoUses: 'Manager QC, Manager Produksi',
    sections: [
      'Pareto chart top defect codes (80/20 rule)',
      'Trend rework rate 30 hari',
      'Breakdown: per operator, per lini, per model, per shift',
    ],
    buttons: [
      { label: 'Filter Periode', icon: Filter, action: 'Range tanggal analisis', when: 'Review weekly/monthly' },
    ],
    tips: [
      'Top 3 defect = fokus improvement (Pareto principle)',
      'Operator dengan rework rate tinggi → training',
      'Lini dengan rework tinggi → cek mesin & standardisasi proses',
    ],
  },

  'prod-alert-settings': {
    title: 'Pengaturan Alert',
    icon: Siren,
    screenshot: '/guide/screenshots/prod-alert-settings.png',
    purpose:
      'Konfigurasi rule alert otomatis (low stock, WO behind, OEE drop, dll). Alert akan muncul di NotificationBell + Andon.',
    whoUses: 'Admin, Manager Produksi',
    sections: [
      'Daftar rule alert aktif',
      'Form: rule name, trigger condition, threshold, severity, channel',
      'Test alert (kirim test ke channel)',
    ],
    buttons: [
      { label: 'Tambah Rule', icon: Plus, action: 'Buat rule baru: kondisi + threshold + channel', when: 'Setup awal atau policy baru' },
      { label: 'Toggle Aktif', icon: CheckCircle2, action: 'Enable/disable rule tanpa hapus', when: 'Maintenance atau temp off' },
      { label: 'Hapus Rule', icon: Trash2, action: 'Hapus rule permanent', when: 'Rule sudah obsolete' },
    ],
    tips: [
      'Mulai dengan severity "low" untuk rule baru — naikkan kalau perlu',
      'Threshold terlalu sensitif = alert spam, abai oleh user',
      'Test rule sebelum activate',
    ],
  },

  'prod-andon-board': {
    title: 'Papan Andon',
    icon: AlertTriangle,
    screenshot: '/guide/screenshots/prod-andon-board.png',
    purpose:
      'Papan visual alert real-time per lini. Warna mengikuti severity. Operator bisa raise andon (bantuan) dari Operator View.',
    whoUses: 'Supervisor, Operator',
    sections: [
      'Grid per lini dengan status: Normal / Warning / Stop',
      'Active andons + durasi (escalation timer)',
      'Resolve andon dengan catatan tindakan',
    ],
    buttons: [
      { label: 'Resolve Andon', icon: CheckCircle2, action: 'Tutup andon + isi tindakan yang dilakukan', when: 'Masalah sudah ditangani' },
      { label: 'Mode TV', icon: Eye, action: 'Fullscreen untuk monitor di shop floor', when: 'Pasang di pabrik' },
    ],
    tips: [
      'Andon "stop" = lini berhenti — prioritas no.1',
      'Resolve dengan catatan — feed ke analytics root cause',
      'Idealnya pasang TV di shop floor dengan mode TV',
    ],
    relatedScenarios: ['s4'],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * EKSEKUSI PROSES — Eksekusi per stasiun kerja
   * ════════════════════════════════════════════════════════════════ */

  'prod-exec-rajut': {
    title: 'Eksekusi Proses — Rajut',
    icon: ClipboardList,
    purpose: 'Halaman pencatatan output produksi di stasiun Rajut. Operator merekam jumlah pcs yang selesai dirajut per bundle/kloter, lengkap dengan jam, operator, dan mesin.',
    whoUses: 'Operator Rajut, Supervisor Lini',
    sections: [
      'Filter WO aktif — pilih Work Order yang sedang berjalan',
      'Form Input Output — masukkan qty selesai, operator, mesin',
      'Riwayat Event Hari Ini — log semua pencatatan shift ini',
    ],
    buttons: [
      { label: 'Catat Output', icon: Plus, action: 'Simpan pencatatan output proses rajut', when: 'Setiap selesai satu kloter/bundle' },
      { label: 'Lihat Riwayat', icon: Eye, action: 'Tampilkan log WIP event hari ini', when: 'Verifikasi data sebelum laporan' },
    ],
    tips: [
      'Alur produksi: Rajut (1) → Linking (2) → Sewing (3) → Steam (4) → QC (5) → Packing (6)',
      'Catat output setiap kali ada kloter selesai, bukan menunggu akhir shift',
      'Pilih operator yang benar agar data produktivitas akurat',
    ],
    warnings: [
      'QC dilakukan SETELAH Steam — pastikan urutan proses benar',
      'Jangan catat qty melebihi target WO untuk menghindari error',
    ],
    relatedScenarios: ['s1'],
  },

  'prod-exec-linking': {
    title: 'Eksekusi Proses — Linking',
    icon: ClipboardList,
    purpose: 'Halaman pencatatan output di stasiun Linking. Setelah proses rajut selesai, bagian-bagian kain dijahit/disambungkan di stasiun linking ini.',
    whoUses: 'Operator Linking, Supervisor Lini',
    sections: [
      'Filter WO aktif — pilih Work Order yang sedang berjalan',
      'Form Input Output — masukkan qty linking, operator',
      'Riwayat Event — log pencatatan shift ini',
    ],
    buttons: [
      { label: 'Catat Output', icon: Plus, action: 'Simpan pencatatan output proses linking', when: 'Setiap selesai satu kloter' },
    ],
    tips: [
      'Linking adalah proses menyambungkan bagian badan, lengan, dan kerah hasil rajut',
      'Pastikan qty linking tidak melebihi qty rajut yang masuk',
      'Alur: Rajut → Linking → Sewing → Steam → QC → Packing',
    ],
    relatedScenarios: ['s1'],
  },

  'prod-exec-sewing': {
    title: 'Eksekusi Proses — Sewing',
    icon: ClipboardList,
    purpose: 'Pencatatan output di stasiun Sewing (jahit). Meliputi pemasangan label, penyelesaian jahitan, dan pengecekan kerapian sebelum masuk ke proses steam.',
    whoUses: 'Operator Sewing, Supervisor Lini',
    sections: [
      'Filter WO aktif — pilih Work Order',
      'Form Input Output — qty sewing selesai',
      'Riwayat Event — log pencatatan hari ini',
    ],
    buttons: [
      { label: 'Catat Output', icon: Plus, action: 'Simpan pencatatan output proses sewing', when: 'Setiap kloter selesai dijahit' },
    ],
    tips: [
      'Setelah sewing, barang menuju STEAM bukan langsung QC',
      'Pastikan label sudah terpasang sebelum menuju steam',
      'Alur: Rajut → Linking → Sewing → Steam → QC → Packing',
    ],
    relatedScenarios: ['s1'],
  },

  'prod-exec-steam': {
    title: 'Eksekusi Proses — Steam',
    icon: ClipboardList,
    purpose: 'Pencatatan output di stasiun Steam. Proses steam (uap panas) dilakukan setelah sewing untuk merapikan garmen sebelum pemeriksaan QC. Ini adalah proses ke-4 dalam alur produksi.',
    whoUses: 'Operator Steam, Supervisor Lini',
    sections: [
      'Filter WO aktif — pilih Work Order',
      'Form Input Output — qty steam selesai',
      'Riwayat Event — log pencatatan hari ini',
    ],
    buttons: [
      { label: 'Catat Output', icon: Plus, action: 'Simpan pencatatan output proses steam', when: 'Setiap kloter selesai di-steam' },
    ],
    tips: [
      'Steam adalah proses ke-4: Sewing → STEAM → QC → Packing',
      'QC hanya boleh dilakukan SETELAH steam — garmen harus sudah rapi',
      'Steam meratakan jahitan dan membentuk garmen sesuai standar',
    ],
    warnings: [
      'PENTING: QC dilakukan setelah Steam. Jangan kirim ke QC sebelum steam selesai.',
    ],
    relatedScenarios: ['s1'],
  },

  'prod-exec-qc': {
    title: 'Eksekusi Proses — QC (Quality Control)',
    icon: ClipboardList,
    purpose: 'Pencatatan hasil pemeriksaan Quality Control. Setelah steam, setiap garmen diperiksa oleh QC Inspector untuk memastikan kualitas sesuai standar sebelum dilakukan packing.',
    whoUses: 'QC Inspector, Supervisor QC',
    sections: [
      'Filter WO aktif — pilih Work Order',
      'Form QC — qty lulus, qty gagal, kode defect',
      'Riwayat Inspeksi — log hasil QC hari ini',
    ],
    buttons: [
      { label: 'Catat Hasil QC', icon: CheckCircle2, action: 'Simpan hasil pemeriksaan QC (pass/fail + defect)', when: 'Setelah memeriksa satu kloter garmen' },
    ],
    tips: [
      'QC adalah proses ke-5: Sewing → Steam → QC → Packing',
      'Barang yang gagal QC masuk ke proses Rework, bukan langsung packing',
      'Catat kode defect spesifik untuk analisis pareto kualitas',
      'Alur: Rajut → Linking → Sewing → Steam → QC → Packing',
    ],
    warnings: [
      'Garmen HARUS sudah melalui proses Steam sebelum QC',
      'Barang gagal QC wajib dicatat dengan kode defect — data ini masuk ke analitik kualitas',
    ],
    relatedScenarios: ['s1', 's2'],
  },

  'prod-exec-packing': {
    title: 'Eksekusi Proses — Packing',
    icon: ClipboardList,
    purpose: 'Pencatatan output di stasiun Packing. Proses akhir produksi — garmen yang telah lulus QC dikemas sesuai spesifikasi buyer sebelum dikirim.',
    whoUses: 'Operator Packing, Supervisor Lini',
    sections: [
      'Filter WO aktif — pilih Work Order',
      'Form Input Output — qty packing selesai',
      'Riwayat Event — log pencatatan hari ini',
    ],
    buttons: [
      { label: 'Catat Output', icon: Plus, action: 'Simpan pencatatan output packing', when: 'Setiap kloter selesai dikemas' },
    ],
    tips: [
      'Packing adalah proses ke-6 dan TERAKHIR dalam alur produksi',
      'Hanya garmen yang LULUS QC boleh masuk ke packing',
      'Setelah packing selesai, WO bisa ditutup dan siap pengiriman',
    ],
    warnings: [
      'Pastikan qty packing tidak melebihi qty yang lulus QC',
    ],
    relatedScenarios: ['s1'],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL MANAJEMEN
   * ════════════════════════════════════════════════════════════════ */

  'management-dashboard': {
    title: 'Dashboard Eksekutif',
    icon: Gauge,
    purpose: 'Ringkasan kinerja bisnis PT Rahaza secara menyeluruh — produksi, keuangan, SDM, dan gudang dalam satu halaman. Dirancang untuk monitoring level manajemen.',
    whoUses: 'Direktur, Manager, Manajemen Senior',
    sections: [
      'KPI Bisnis — total pesanan, nilai produksi, omzet bulan ini',
      'Status Produksi — WO aktif, output hari ini, OEE',
      'Keuangan Singkat — piutang vs hutang, arus kas',
      'SDM Ringkas — kehadiran hari ini, status payroll',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Filter, action: 'Ganti rentang waktu tampilan dashboard', when: 'Analisis tren mingguan/bulanan' },
      { label: 'Refresh', icon: RefreshCw, action: 'Perbarui data real-time', when: 'Update manual data terkini' },
    ],
    tips: [
      'Dashboard diperbarui otomatis setiap 5 menit',
      'Klik kartu KPI untuk drill-down ke modul detail',
      'Gunakan filter periode untuk melihat tren historis',
    ],
    relatedScenarios: ['s1'],
  },

  'mgmt-overview': {
    title: 'Ikhtisar Manajemen',
    icon: LayoutGrid,
    purpose: 'Ringkasan operasional harian dari seluruh portal — produksi, gudang, keuangan, SDM. Satu halaman untuk monitoring cepat semua aspek bisnis.',
    whoUses: 'Manager Operasional, Direktur',
    sections: [
      'Ringkasan Produksi — WO aktif, output target vs aktual',
      'Ringkasan Gudang — stok kritis, PO pending',
      'Ringkasan Keuangan — invoice jatuh tempo, pembayaran pending',
      'Ringkasan SDM — kehadiran, lembur, cuti pending',
    ],
    tips: [
      'Gunakan halaman ini sebagai titik awal monitoring harian',
      'Klik "Lihat Detail" pada setiap seksi untuk masuk ke modul terkait',
    ],
    relatedScenarios: ['s1'],
  },

  'mgmt-products': {
    title: 'Data Produk (Legacy)',
    icon: Package,
    purpose: 'Manajemen katalog produk — kode SKU, nama produk, kategori, harga CMT, dan harga jual. Digunakan untuk referensi master data produk yang dijual ke buyer.',
    whoUses: 'Admin, Manager Produk, PPIC',
    sections: [
      'Daftar Produk — semua produk aktif dengan kode & harga',
      'Form Tambah/Edit — isi data produk baru atau update existing',
    ],
    buttons: [
      { label: 'Tambah Produk', icon: Plus, action: 'Buat produk/SKU baru', when: 'Ada model garmen baru yang akan diproduksi' },
      { label: 'Edit', icon: Edit, action: 'Update informasi produk', when: 'Ada perubahan harga atau spesifikasi' },
      { label: 'Hapus', icon: Trash2, action: 'Nonaktifkan produk', when: 'Produk sudah tidak diproduksi' },
    ],
    tips: [
      'Untuk master data produk Rahaza yang lebih lengkap, gunakan menu "Model Produk" di Portal Produksi',
      'Kode produk harus unik — digunakan sebagai referensi di PO dan laporan',
      'Harga CMT = biaya makloon per pcs ke vendor',
    ],
  },

  'mgmt-customers': {
    title: 'Data Pembeli (Buyer)',
    icon: UserCheck,
    purpose: 'Manajemen data buyer/pelanggan yang memesan garmen. Berisi informasi kontak, alamat, dan histori pesanan buyer.',
    whoUses: 'Admin, Sales, Manager',
    sections: [
      'Daftar Buyer — semua pembeli aktif',
      'Detail Buyer — kontak, alamat, histori pesanan',
      'Form Tambah/Edit — data buyer baru',
    ],
    buttons: [
      { label: 'Tambah Buyer', icon: Plus, action: 'Daftarkan pembeli/buyer baru', when: 'Ada pelanggan baru yang memesan' },
      { label: 'Edit', icon: Edit, action: 'Update data kontak atau alamat buyer', when: 'Ada perubahan informasi buyer' },
    ],
    tips: [
      'Lengkapi data kontak buyer untuk kemudahan komunikasi pengiriman',
      'Untuk pelanggan di sistem Rahaza, gunakan "Pelanggan Rahaza" di bawah',
    ],
  },

  'mgmt-reports': {
    title: 'Laporan Bisnis',
    icon: BarChart4,
    purpose: 'Laporan komprehensif bisnis garmen — produksi, progres WO, keuangan, pengiriman, rework, dan material. Semua data terintegrasi dari sistem Rahaza.',
    whoUses: 'Manager, Direktur, Akuntan',
    sections: [
      'Laporan Produksi — rekap pesanan, WO, output per model',
      'Laporan Progres — progress WO per proses per tanggal',
      'Laporan Keuangan — invoice AR, pembayaran, outstanding',
      'Laporan Pengiriman — pengiriman ke buyer',
      'Laporan Rework — defect dan rework per model',
      'Material Issue — pengeluaran material dari gudang',
    ],
    buttons: [
      { label: 'Filter Tanggal', icon: Filter, action: 'Filter laporan berdasarkan periode', when: 'Laporan bulanan/mingguan' },
      { label: 'Export Excel', icon: Download, action: 'Unduh laporan dalam format Excel (.xlsx)', when: 'Untuk distribusi atau analisis lanjutan' },
      { label: 'Terapkan Filter', icon: Search, action: 'Terapkan filter yang dipilih', when: 'Setelah mengisi kriteria filter' },
    ],
    tips: [
      'Klik tab laporan di kiri untuk ganti jenis laporan',
      'Filter tanggal sangat membantu mempersempit data',
      'Export Excel untuk laporan ke manajemen atau klien',
    ],
    relatedScenarios: ['s1'],
  },

  'mgmt-users': {
    title: 'Manajemen Pengguna',
    icon: UserCheck,
    purpose: 'Kelola akun pengguna sistem ERP — tambah pengguna baru, ubah password, atur peran, dan nonaktifkan akun. Admin saja yang boleh mengakses modul ini.',
    whoUses: 'Administrator Sistem',
    sections: [
      'Daftar Pengguna — semua akun aktif dan nonaktif',
      'Form Tambah/Edit — data akun pengguna',
      'Assign Peran — hubungkan pengguna ke peran akses',
    ],
    buttons: [
      { label: 'Tambah Pengguna', icon: Plus, action: 'Buat akun pengguna baru', when: 'Ada karyawan baru yang perlu akses ERP' },
      { label: 'Edit', icon: Edit, action: 'Perbarui data atau reset password', when: 'Ada perubahan info atau password terlupakan' },
      { label: 'Nonaktifkan', icon: Trash2, action: 'Nonaktifkan akun tanpa menghapus data', when: 'Karyawan resign atau pindah bagian' },
    ],
    tips: [
      'Gunakan prinsip "least privilege" — berikan akses minimal sesuai kebutuhan pekerjaan',
      'Nonaktifkan akun karyawan yang resign segera',
      'Admin bisa reset password dari halaman ini tanpa tahu password lama',
    ],
    warnings: [
      'Jangan bagikan akun — setiap pengguna harus punya akun sendiri',
      'Penghapusan akun permanen tidak bisa dibatalkan — gunakan "Nonaktifkan" sebagai gantinya',
    ],
  },

  'mgmt-roles': {
    title: 'Peran & Hak Akses',
    icon: ClipboardList,
    purpose: 'SATU tempat untuk mengatur akses: portal yang boleh dibuka, menu yang disembunyikan, dan izin aksi/approval per peran.',
    whoUses: 'Administrator Sistem (Super Admin)',
    sections: [
      'Daftar Peran (kiri) — cari peran, lihat jumlah pengguna / portal / izin',
      '1. Identitas Peran — nama & keterangan, plus "Salin pengaturan dari peran lain"',
      '2. Portal yang Boleh Dibuka — kosong berarti memakai aturan bawaan sistem',
      '3. Hak Akses — pilih cepat per modul: Tidak ada / Lihat saja / Penuh',
      '4. Sembunyikan Menu Tertentu — opsional, untuk kasus khusus',
      '5. Riwayat Perubahan — siapa mengubah akses peran ini dan kapan',
    ],
    buttons: [
      { label: 'Tambah Peran', icon: Plus, action: 'Buat peran baru, lalu atur portal & izinnya di panel kanan', when: 'Ada jabatan baru yang butuh akses berbeda' },
      { label: 'Simpan', icon: Edit, action: 'Simpan identitas + portal + menu + izin dalam satu langkah', when: 'Muncul label "Belum disimpan"' },
    ],
    tips: [
      'Buat peran sesuai jabatan nyata: Operator, Supervisor, QC Inspector, dll.',
      'Setelah membuat peran, assign ke pengguna di tab Pengguna',
      'Pakai Preset (Lihat saja / Operator / Approver / Penuh) supaya tidak perlu mencentang satu-satu',
      'Tombol "Bandingkan" berguna saat audit: lihat selisih izin antar dua peran',
    ],
    warnings: [
      'Selama daftar izin sebuah peran masih KOSONG, sistem memakai aturan bawaan lama. Begitu satu izin dicentang, peran itu hanya boleh melakukan apa yang tercentang.',
    ],
  },

  'mgmt-activity': {
    title: 'Log Aktivitas',
    icon: Activity,
    purpose: 'Rekam jejak semua aktivitas pengguna di sistem — siapa mengubah apa dan kapan. Berguna untuk audit trail dan investigasi insiden.',
    whoUses: 'Administrator, Auditor, Manager',
    sections: [
      'Daftar Log — semua aktivitas terurut dari terbaru',
      'Filter User — saring log berdasarkan pengguna',
      'Filter Action — saring berdasarkan jenis aksi (create/update/delete)',
      'Filter Tanggal — saring berdasarkan periode',
    ],
    buttons: [
      { label: 'Terapkan Filter', icon: Filter, action: 'Terapkan kriteria filter yang dipilih', when: 'Mencari aktivitas spesifik' },
      { label: 'Export', icon: Download, action: 'Unduh log aktivitas ke Excel', when: 'Untuk keperluan audit' },
    ],
    tips: [
      'Log tidak bisa dihapus atau diubah — ini adalah catatan permanen',
      'Gunakan kombinasi filter user + tanggal untuk investigasi yang efisien',
      'IP Address dicatat untuk setiap aktivitas — berguna jika ada akses mencurigakan',
    ],
  },

  'mgmt-company': {
    title: 'Pengaturan Perusahaan',
    icon: FileText,
    purpose: 'Konfigurasi informasi perusahaan — nama, alamat, logo, NPWP, nomor telepon. Data ini muncul di header dokumen PDF seperti invoice dan LKP.',
    whoUses: 'Administrator, Owner',
    sections: [
      'Informasi Dasar — nama, alamat, telepon, email',
      'Identitas Pajak — NPWP, PKP status',
      'Logo Perusahaan — upload logo untuk dokumen PDF',
    ],
    buttons: [
      { label: 'Simpan Pengaturan', icon: Edit, action: 'Simpan perubahan data perusahaan', when: 'Setelah mengisi atau update data' },
      { label: 'Upload Logo', icon: Upload, action: 'Unggah logo perusahaan (JPG/PNG)', when: 'Setup awal atau ganti logo' },
    ],
    tips: [
      'Logo ukuran 200x80px ideal untuk dokumen PDF',
      'Data NPWP wajib diisi jika perusahaan PKP untuk keperluan faktur pajak',
      'Perubahan data perusahaan langsung terlihat di semua dokumen PDF yang dicetak',
    ],
  },

  'mgmt-pdf': {
    title: 'Konfigurasi PDF',
    icon: Printer,
    purpose: 'Pengaturan tampilan dokumen PDF yang dihasilkan sistem — LKP, invoice, slip gaji, laporan. Atur header, footer, warna, dan informasi tambahan.',
    whoUses: 'Administrator, Manager',
    sections: [
      'Template PDF — pilih dan atur template',
      'Header/Footer — konfigurasi informasi di atas dan bawah dokumen',
      'Warna & Font — sesuaikan branding perusahaan',
    ],
    tips: [
      'Perubahan konfigurasi berlaku untuk semua cetak PDF setelahnya',
      'Preview PDF tersedia sebelum menyimpan perubahan',
    ],
  },

  'mgmt-help': {
    title: 'Panduan Penggunaan',
    icon: BookOpen,
    purpose: 'Panduan lengkap cara menggunakan seluruh modul ERP PT Rahaza. Berisi skenario step-by-step, persona pengguna, tips, dan diagram alur proses.',
    whoUses: 'Semua Pengguna',
    sections: [
      'Skenario Alur — langkah detail proses bisnis dari awal ke akhir',
      'Persona Pengguna — siapa menggunakan apa',
      'Diagram Alur — visualisasi alur produksi dan material',
      'FAQ — pertanyaan umum dan jawaban',
    ],
    tips: [
      'Gunakan tombol "?" di setiap halaman untuk bantuan kontekstual modul tersebut',
      'Skenario S1 (Order Baru) adalah panduan paling lengkap untuk operator baru',
      'Diagram alur menjelaskan koneksi antar modul secara visual',
    ],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL GUDANG
   * ════════════════════════════════════════════════════════════════ */

  'warehouse-dashboard': {
    title: 'Dashboard Gudang',
    icon: Gauge,
    purpose: 'Pusat monitoring gudang — stok kritis, PO pending, penerimaan hari ini, aktivitas putaway, dan pergerakan material. Untuk supervisor dan staf gudang.',
    whoUses: 'Kepala Gudang, Supervisor Gudang',
    sections: [
      'KPI Gudang — total item, stok kritis, PO pending',
      'Grafik Pergerakan — keluar-masuk material per periode',
      'Stok Menipis — daftar material dengan stok di bawah minimum',
      'PO Belum Terima — purchase order yang belum datang',
    ],
    buttons: [
      { label: 'Refresh', icon: RefreshCw, action: 'Perbarui data dashboard', when: 'Cek status terkini' },
    ],
    tips: [
      'Perhatikan "Stok Kritis" — material dengan stok <10% dari minimum reorder',
      'Dashboard diupdate real-time saat ada transaksi gudang baru',
    ],
    relatedScenarios: ['s3'],
  },

  'wh-receiving': {
    title: 'Penerimaan Barang (GR)',
    icon: Package,
    purpose: 'Proses penerimaan material dari supplier ke gudang. Verifikasi kesesuaian barang datang dengan Purchase Order, lalu buat Goods Receipt untuk update stok.',
    whoUses: 'Staf Gudang, Kepala Gudang',
    sections: [
      'PO Pending — daftar PO yang menunggu penerimaan',
      'Form GR — isi qty terima, kondisi barang, tanggal terima',
      'Riwayat Penerimaan — semua GR yang sudah diproses',
    ],
    buttons: [
      { label: 'Terima Barang', icon: CheckCircle2, action: 'Buat Goods Receipt dari PO yang ada', when: 'Barang dari supplier sudah tiba' },
      { label: 'Catat Penerimaan Parsial', icon: Package, action: 'Terima sebagian qty dari total PO', when: 'Supplier kirim bertahap' },
    ],
    tips: [
      'Selalu cocokkan fisik barang dengan dokumen PO sebelum konfirmasi terima',
      'Catat kondisi barang — kalau ada kerusakan, foto dan catat sebelum terima',
      'Setelah GR, stok otomatis bertambah di sistem',
    ],
    warnings: [
      'Jangan terima barang tanpa PO — buat PO terlebih dahulu jika belum ada',
      'Penerimaan parsial boleh, tapi pastikan catatan qty akurat',
    ],
    relatedScenarios: ['s3'],
  },

  'wh-putaway': {
    title: 'Putaway (Penempatan Barang)',
    icon: Boxes,
    purpose: 'Tempatkan material yang baru diterima ke lokasi bin yang tepat di gudang. Sistem mencatat lokasi setiap material untuk kemudahan pencarian stok.',
    whoUses: 'Staf Gudang',
    sections: [
      'Material Pending Putaway — item yang sudah diterima tapi belum di-putaway',
      'Form Putaway — pilih lokasi bin dan konfirmasi penempatan',
      'Riwayat — semua putaway yang sudah dilakukan',
    ],
    buttons: [
      { label: 'Putaway', icon: Boxes, action: 'Konfirmasi penempatan material ke bin tertentu', when: 'Setelah penerimaan GR selesai' },
    ],
    tips: [
      'Kelompokkan material sejenis dalam satu zona untuk efisiensi pencarian',
      'Cantumkan lokasi bin di label fisik material untuk mempermudah picking',
      'Putaway yang akurat = stock opname yang lebih cepat dan akurat',
    ],
    relatedScenarios: ['s3'],
  },

  'wh-opname': {
    title: 'Stock Opname',
    icon: ClipboardList,
    purpose: 'Proses penghitungan fisik stok gudang untuk rekonsiliasi dengan data sistem. Hitung stok aktual, bandingkan dengan sistem, dan selesaikan selisih.',
    whoUses: 'Kepala Gudang, Staf Gudang, Akuntansi',
    sections: [
      'Buat Sesi Opname — mulai sesi penghitungan baru',
      'Input Hitungan Fisik — isi qty aktual per material',
      'Rekonsiliasi — lihat selisih fisik vs sistem',
      'Finalize & Post ke Akuntansi — selesaikan opname dan buat jurnal penyesuaian',
    ],
    buttons: [
      { label: 'Mulai Opname', icon: ClipboardList, action: 'Buat sesi opname baru', when: 'Jadwal opname periodik (bulanan/triwulan)' },
      { label: 'Input Hitungan', icon: Edit, action: 'Masukkan qty hasil hitung fisik', when: 'Saat tim menghitung di gudang' },
      { label: 'Finalize', icon: CheckCircle2, action: 'Selesaikan opname dan posting ke GL', when: 'Semua item sudah dihitung dan diverifikasi' },
      { label: 'Export Excel', icon: Download, action: 'Unduh data opname ke Excel', when: 'Dokumentasi atau analisis lanjutan' },
    ],
    tips: [
      'Lakukan opname saat gudang tidak ada aktivitas (malam/weekend)',
      'Libatkan dua orang untuk hitung dan catat — mengurangi error',
      'Selisih kecil (<1%) umumnya masih dalam toleransi',
      'Hasil opname otomatis masuk ke jurnal penyesuaian stok di akuntansi',
    ],
    warnings: [
      'Sesi opname yang sudah difinalize tidak bisa dibatalkan',
      'Pastikan semua transaksi gudang hari opname sudah tercatat sebelum mulai',
    ],
    relatedScenarios: ['s3'],
  },

  'wh-bin': {
    title: 'Lokasi & Bin Gudang',
    icon: Boxes,
    purpose: 'Kelola struktur lokasi gudang — gedung, zona, rak, dan bin. Setiap material bisa dilacak sampai level bin untuk akurasi stok.',
    whoUses: 'Kepala Gudang, Admin',
    sections: [
      'Pohon Lokasi — hierarki Gedung → Zona → Rak → Bin',
      'Form Tambah/Edit — buat lokasi baru',
      'Kapasitas — atur kapasitas maksimal per bin',
    ],
    buttons: [
      { label: 'Tambah Lokasi', icon: Plus, action: 'Buat lokasi gudang baru (gedung/zona/rak/bin)', when: 'Ekspansi gudang atau reorganisasi' },
      { label: 'Edit', icon: Edit, action: 'Ubah nama atau kapasitas lokasi', when: 'Ada perubahan layout gudang' },
    ],
    tips: [
      'Gunakan penamaan yang logis: GD-A-R01-B01 (Gedung A, Rak 1, Bin 1)',
      'Bin dengan kapasitas yang tepat membantu mencegah overloading',
    ],
  },

  'wh-accessory': {
    title: 'Aksesori & Komponen',
    icon: Package,
    purpose: 'Manajemen stok aksesori garmen — kancing, resleting, label, benang, dan komponen lainnya yang dibutuhkan untuk produksi.',
    whoUses: 'Staf Gudang, PPIC',
    sections: [
      'Daftar Aksesori — semua item aksesori dengan stok',
      'Tambah/Edit — pendaftaran aksesori baru',
      'Riwayat Keluar-Masuk — pergerakan aksesori',
    ],
    buttons: [
      { label: 'Tambah Aksesori', icon: Plus, action: 'Daftarkan aksesori baru ke sistem', when: 'Ada jenis aksesori baru' },
      { label: 'Sesuaikan Stok', icon: Edit, action: 'Koreksi stok manual', when: 'Penyesuaian setelah hitung fisik' },
    ],
    tips: [
      'Atur minimum stok untuk setiap aksesori agar mendapat alert sebelum habis',
      'Pergerakan aksesori tercatat saat proses Material Issue ke produksi',
    ],
  },

  'wh-purchase-orders': {
    title: 'Purchase Order (PO)',
    icon: FileText,
    purpose: 'Kelola pembelian material dari supplier — buat PO baru, tracking status pengiriman, dan integrasi dengan penerimaan barang.',
    whoUses: 'Purchasing, Kepala Gudang',
    sections: [
      'Daftar PO — semua PO dengan status (draft/sent/partial/done)',
      'Form Buat PO — detail item, qty, harga, tanggal kirim',
      'Tracking Status — persentase penerimaan per PO',
    ],
    buttons: [
      { label: 'Buat PO', icon: Plus, action: 'Buat Purchase Order baru ke supplier', when: 'Stok material menipis atau ada kebutuhan baru' },
      { label: 'Kirim ke Supplier', icon: Upload, action: 'Tandai PO sebagai sudah dikirim ke supplier', when: 'PO sudah dikonfirmasi dan dikirim' },
      { label: 'Terima Barang', icon: Package, action: 'Arahkan ke modul Penerimaan untuk proses GR', when: 'Barang dari supplier datang' },
      { label: 'Cetak PO', icon: Printer, action: 'Cetak atau download PO sebagai PDF', when: 'Kirim ke supplier atau arsip' },
    ],
    tips: [
      'Buat PO sebelum barang datang — staf gudang akan matching barang dengan PO saat terima',
      'PO dengan status "Partial" berarti barang sudah sebagian datang',
      'Integrasikan dengan modul AP untuk pembayaran ke supplier',
    ],
    warnings: [
      'PO yang sudah ada penerimaan sebagian tidak bisa dibatalkan',
      'Cek kredit limit supplier sebelum PO besar',
    ],
    relatedScenarios: ['s3'],
  },

  'wh-materials': {
    title: 'Master Material',
    icon: Package,
    purpose: 'Kelola katalog item produksi — Bahan, Aksesoris, dan Produk Jadi. Setiap item memiliki kode, satuan, minimum stok, dan lead time.',
    whoUses: 'Admin, Kepala Gudang, PPIC',
    sections: [
      'Daftar Material — semua material terdaftar',
      'Form Tambah/Edit — data material baru',
      'Minimum Stok — atur reorder point',
    ],
    buttons: [
      { label: 'Tambah Material', icon: Plus, action: 'Daftarkan material baru ke sistem', when: 'Ada bahan baku baru' },
      { label: 'Edit', icon: Edit, action: 'Update spesifikasi atau harga material', when: 'Ada perubahan dari supplier' },
    ],
    tips: [
      'Atur minimum stok (reorder point) untuk mendapat notifikasi stok kritis',
      'Kode material harus unik dan konsisten — gunakan kode yang mudah diingat',
      'Lead time penting untuk perencanaan pembelian',
    ],
  },

  'wh-stock': {
    title: 'Stok Material',
    icon: Boxes,
    purpose: 'Lihat posisi stok semua material secara real-time — qty tersedia, qty reserved untuk produksi, dan qty dalam transit. Termasuk fitur filter dan export.',
    whoUses: 'Kepala Gudang, PPIC, Supervisor Produksi',
    sections: [
      'Daftar Stok — semua material dengan qty current',
      'Filter — cari berdasarkan kode, nama, atau lokasi',
      'Detail — lihat detail per material termasuk lokasi bin',
    ],
    buttons: [
      { label: 'Export Excel', icon: Download, action: 'Unduh laporan stok ke Excel', when: 'Laporan stok mingguan/bulanan' },
      { label: 'Refresh', icon: RefreshCw, action: 'Perbarui tampilan stok', when: 'Cek stok terkini setelah transaksi' },
    ],
    tips: [
      'Qty "Reserved" = sudah dicadangkan untuk WO aktif, belum keluar fisik',
      'Qty "On Hand" = stok tersedia untuk digunakan',
      'Filter "Stok Kritis" untuk fokus pada material yang perlu restock segera',
    ],
  },

  'wh-material-issue': {
    title: 'Permintaan Material (MI)',
    icon: Package,
    purpose: 'Proses pengeluaran material dari gudang ke lini produksi berdasarkan Work Order. Setiap MI harus disetujui supervisor sebelum material dikeluarkan.',
    whoUses: 'PPIC, Supervisor Produksi, Kepala Gudang',
    sections: [
      'Daftar MI — semua permintaan material',
      'Form Buat MI — pilih WO, material, dan qty yang dibutuhkan',
      'Approval Flow — status pending/approved/issued',
    ],
    buttons: [
      { label: 'Buat MI', icon: Plus, action: 'Buat permintaan material baru untuk WO', when: 'WO sudah release dan perlu material' },
      { label: 'Setujui', icon: CheckCircle2, action: 'Setujui permintaan material (supervisor)', when: 'Verifikasi kebutuhan dan stok mencukupi' },
      { label: 'Issue (Keluarkan)', icon: Package, action: 'Keluarkan material dari gudang secara fisik', when: 'Setelah disetujui, material bisa diambil' },
    ],
    tips: [
      'Gunakan Bulk MI Generator di Portal Produksi untuk MI massal dari BOM',
      'Material yang sudah diissue otomatis mengurangi stok gudang',
      'Catat no. WO di setiap MI untuk traceability',
    ],
    warnings: [
      'MI yang sudah diissue tidak bisa dibatalkan — hati-hati sebelum konfirmasi',
    ],
    relatedScenarios: ['s1', 's3'],
  },

  'wh-material-reservation': {
    title: 'Reservasi Material',
    icon: Boxes,
    purpose: 'Reservasi material untuk WO mendatang — material "dipesan" di gudang sebelum diissue secara fisik. Memastikan ketersediaan material untuk produksi yang sudah direncanakan.',
    whoUses: 'PPIC, Supervisor Produksi',
    sections: [
      'Daftar Reservasi — material yang sudah direservasi per WO',
      'Form Reservasi — pilih WO dan material yang akan direservasi',
    ],
    buttons: [
      { label: 'Buat Reservasi', icon: Plus, action: 'Reservasi material untuk WO tertentu', when: 'WO sudah di-release dan material perlu disiapkan' },
      { label: 'Batalkan Reservasi', icon: XIcon, action: 'Batalkan reservasi jika WO dibatalkan', when: 'WO tidak jadi dilaksanakan' },
    ],
    tips: [
      'Reservasi mengurangi qty "Available" tapi stok fisik belum keluar',
      'Gunakan reservasi untuk perencanaan produksi jangka pendek (1-2 minggu)',
    ],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL KEUANGAN
   * ════════════════════════════════════════════════════════════════ */

  'finance-dashboard': {
    title: 'Dashboard Keuangan',
    icon: Gauge,
    purpose: 'Ringkasan posisi keuangan PT Rahaza — kas, piutang, hutang, P&L bulan ini, dan arus kas. Untuk monitoring keuangan level manajer.',
    whoUses: 'Manajer Keuangan, Direktur, Akuntan',
    sections: [
      'KPI Keuangan — kas, piutang, hutang',
      'P&L Singkat — pendapatan vs beban bulan ini',
      'Arus Kas — ringkasan cash flow',
      'Invoice Jatuh Tempo — AR yang perlu ditagih',
    ],
    tips: [
      'Monitor rasio piutang/hutang secara berkala',
      'Dashboard diperbarui real-time saat ada posting jurnal',
    ],
  },

  // Session #11.17: Legacy fin-ar, fin-ap, fin-invoices, fin-manual-invoice, fin-payments
  // REMOVED from help data. Use SSOT modules instead:
  //   - fin-ar-invoices (AR Invoices)
  //   - fin-ar-360 (AR 360° Aging + Statement)
  //   - fin-ap-aging (AP Aging)
  //   - maklon-billing (Maklon Invoices)

  'fin-approval': {
    title: 'Persetujuan Keuangan',
    icon: CheckCircle2,
    purpose: 'Kelola alur persetujuan (approval) untuk transaksi keuangan — pembayaran besar, jurnal manual, atau invoice dengan nilai di atas batas tertentu.',
    whoUses: 'Manajer Keuangan, Direktur',
    sections: [
      'Pending Approval — transaksi menunggu persetujuan',
      'Riwayat — transaksi yang sudah disetujui atau ditolak',
    ],
    buttons: [
      { label: 'Setujui', icon: CheckCircle2, action: 'Setujui transaksi keuangan', when: 'Setelah review dan verifikasi' },
      { label: 'Tolak', icon: XIcon, action: 'Tolak transaksi dengan catatan alasan', when: 'Ada ketidaksesuaian data' },
    ],
    tips: [
      'Review dokumen pendukung sebelum menyetujui transaksi besar',
      'Transaksi yang ditolak dikembalikan ke pembuat untuk koreksi',
    ],
  },

  // Session #11.17: 'fin-payments' help entry REMOVED — payment workflows now flow
  // through fin-ar-invoices (AR receipts) + fin-ap-aging (AP payments).

  'fin-recap': {
    title: 'Rekap Keuangan',
    icon: BarChart4,
    purpose: 'Ringkasan keuangan periodik — total revenue, total beban, margin, dan perbandingan antar periode. Dashboard keuangan yang lebih detail dari dashboard utama.',
    whoUses: 'Manajer Keuangan, Direktur',
    sections: [
      'Rekap Periode — pilih bulan/kuartal/tahun',
      'Komparasi — bandingkan dua periode',
      'Breakdown — detail per kategori revenue/beban',
    ],
    buttons: [
      { label: 'Export Excel', icon: Download, action: 'Unduh rekap ke Excel', when: 'Laporan bulanan untuk manajemen' },
    ],
    tips: [
      'Bandingkan bulan ini vs bulan lalu untuk identifikasi tren',
      'Margin kotor < 20% perlu investigasi biaya produksi',
    ],
  },

  'fin-cost-centers': {
    title: 'Pusat Biaya',
    icon: FileText,
    purpose: 'Kelola pusat biaya (cost center) untuk alokasi biaya produksi, overhead, dan SDM ke departemen yang tepat. Mendukung pelaporan keuangan per departemen.',
    whoUses: 'Akuntan, Manajer Keuangan',
    sections: [
      'Daftar Cost Center — semua pusat biaya aktif',
      'Form Tambah/Edit — buat pusat biaya baru',
    ],
    buttons: [
      { label: 'Tambah Cost Center', icon: Plus, action: 'Buat pusat biaya baru', when: 'Ada departemen baru atau kebutuhan pelaporan baru' },
    ],
    tips: [
      'Standar cost center: Produksi, Gudang, Administrasi, Marketing, SDM',
      'Cost center digunakan saat input jurnal manual untuk alokasi biaya',
    ],
  },

  'fin-ar-invoices': {
    title: 'Invoice AR (Piutang)',
    icon: FileText,
    purpose: 'Kelola invoice piutang ke pelanggan dalam sistem Rahaza. Berbeda dengan Invoice Penjualan umum — ini khusus untuk sistem AR Rahaza yang terintegrasi dengan pengiriman.',
    whoUses: 'Akuntan, Manajer Keuangan',
    sections: [
      'Daftar Invoice AR — semua invoice dengan status pembayaran',
      'Buat Invoice AR — dari pengiriman yang sudah selesai',
      'Cetak/Download PDF',
    ],
    buttons: [
      { label: 'Buat Invoice AR', icon: Plus, action: 'Buat invoice berdasarkan shipment ke pelanggan', when: 'Setelah pengiriman ke pelanggan selesai' },
      { label: 'Catat Pembayaran', icon: CheckCircle2, action: 'Input pembayaran masuk dari pelanggan', when: 'Pelanggan sudah bayar' },
      { label: 'Cetak PDF', icon: Printer, action: 'Download invoice sebagai PDF', when: 'Kirim ke pelanggan' },
    ],
    tips: [
      'Semua nominal dalam format Rp. dengan pemisah ribuan titik',
      'Invoice yang jatuh tempo muncul di dashboard dengan highlight merah',
    ],
  },

  'fin-cash': {
    title: 'Kas & Rekening Bank',
    icon: FileText,
    purpose: 'Kelola akun kas dan rekening bank perusahaan — saldo terkini, mutasi, dan rekonsiliasi bank.',
    whoUses: 'Akuntan, Kasir, Manajer Keuangan',
    sections: [
      'Daftar Akun Kas/Bank — saldo per akun',
      'Mutasi — riwayat keluar-masuk per akun',
      'Rekonsiliasi — cocokkan dengan laporan bank',
    ],
    buttons: [
      { label: 'Tambah Akun', icon: Plus, action: 'Daftarkan rekening bank baru', when: 'Ada rekening baru yang dibuka' },
      { label: 'Input Mutasi', icon: Edit, action: 'Catat transaksi kas/bank manual', when: 'Ada transaksi yang tidak auto-generate' },
    ],
    tips: [
      'Rekonsiliasi bank bulanan wajib — cocokkan buku besar dengan rekening koran',
      'Akun kas kecil (petty cash) sebaiknya punya akun terpisah',
    ],
  },

  'fin-expenses': {
    title: 'Beban & Biaya Operasional',
    icon: FileText,
    purpose: 'Catat dan kelola pengeluaran operasional perusahaan — listrik, air, telepon, pemeliharaan, supplies kantor, dan biaya lain-lain.',
    whoUses: 'Akuntan, Admin Keuangan',
    sections: [
      'Daftar Beban — semua pengeluaran per periode',
      'Input Beban — catat beban baru',
      'Analisis — beban per kategori',
    ],
    buttons: [
      { label: 'Catat Beban', icon: Plus, action: 'Input beban baru dengan kategori dan akun', when: 'Ada pengeluaran yang perlu dicatat' },
      { label: 'Upload Bukti', icon: Upload, action: 'Lampirkan kwitansi/invoice pendukung', when: 'Dokumentasi pengeluaran' },
    ],
    tips: [
      'Kategorisasi beban yang konsisten memudahkan analisis pengeluaran',
      'Upload bukti transaksi untuk keperluan audit',
    ],
  },

  'fin-hpp': {
    title: 'HPP (Harga Pokok Produksi)',
    icon: BarChart4,
    purpose: 'Kalkulasi dan analisis Harga Pokok Produksi per model garmen. Meliputi biaya bahan baku, biaya tenaga kerja langsung, dan biaya overhead pabrik.',
    whoUses: 'Akuntan Biaya, Manajer Keuangan, PPIC',
    sections: [
      'HPP per Model — biaya per pcs per model garmen',
      'Komponen Biaya — breakdown material, tenaga kerja, overhead',
      'Analisis Margin — bandingkan HPP vs harga jual',
    ],
    tips: [
      'HPP dihitung otomatis berdasarkan BOM + actual material issue + biaya tenaga kerja',
      'Margin < 20% perlu review harga jual atau efisiensi produksi',
      'Update HPP setiap ada perubahan harga bahan baku',
    ],
  },

  'fin-coa': {
    title: 'Bagan Akun (Chart of Accounts)',
    icon: FileText,
    purpose: 'Kelola struktur akun akuntansi perusahaan. COA adalah tulang punggung sistem akuntansi — setiap transaksi di-posting ke akun yang tepat.',
    whoUses: 'Akuntan Senior, Manajer Keuangan',
    sections: [
      'Daftar Akun — semua akun aktif dengan kode',
      'Hierarki — akun header dan sub-akun',
      'Form Tambah/Edit — buat atau ubah akun',
    ],
    buttons: [
      { label: 'Tambah Akun', icon: Plus, action: 'Buat akun baru dalam COA', when: 'Ada kebutuhan pencatatan baru yang belum ada akunnya' },
      { label: 'Edit', icon: Edit, action: 'Ubah nama atau tipe akun', when: 'Penyesuaian COA' },
    ],
    tips: [
      'Struktur COA standar: 1xxx Aset, 2xxx Kewajiban, 3xxx Modal, 4xxx Pendapatan, 5xxx Beban',
      'Jangan hapus akun yang sudah punya transaksi — nonaktifkan saja',
      'Konsultasikan dengan akuntan senior sebelum mengubah struktur COA',
    ],
    warnings: [
      'Perubahan COA berdampak pada seluruh laporan keuangan',
    ],
  },

  'fin-journal-entry': {
    title: 'Jurnal Entri Manual',
    icon: ClipboardPen,
    purpose: 'Input jurnal akuntansi manual untuk transaksi yang tidak di-generate otomatis — koreksi, penyesuaian akhir periode, depresiasi, dan alokasi biaya.',
    whoUses: 'Akuntan, Manajer Keuangan',
    sections: [
      'Form Jurnal — debit/kredit per akun',
      'Validasi — sistem cek balance debit=kredit',
      'Posting — jurnal diposting ke General Ledger',
    ],
    buttons: [
      { label: 'Tambah Baris', icon: Plus, action: 'Tambah baris debit/kredit dalam jurnal', when: 'Membuat jurnal dengan banyak akun' },
      { label: 'Posting', icon: CheckCircle2, action: 'Post jurnal ke General Ledger', when: 'Jurnal sudah benar dan siap diposting' },
    ],
    tips: [
      'Debit harus sama dengan Kredit — sistem akan menolak jurnal tidak balance',
      'Sertakan keterangan yang jelas — berguna untuk audit trail',
      'Jurnal yang sudah diposting tidak bisa dihapus — buat jurnal koreksi jika salah',
    ],
    warnings: [
      'JANGAN posting jurnal yang belum diverifikasi — konsultasikan dengan akuntan senior',
      'Jurnal yang diposting mengubah saldo akun secara permanen',
    ],
  },

  'fin-trial-balance': {
    title: 'Neraca Saldo (Trial Balance)',
    icon: BarChart4,
    purpose: 'Laporan neraca saldo — saldo semua akun per tanggal tertentu. Verifikasi bahwa total debit = total kredit sebelum menyusun laporan keuangan.',
    whoUses: 'Akuntan, Manajer Keuangan',
    sections: [
      'Neraca Saldo — semua akun dengan saldo debit/kredit',
      'Filter Periode — pilih tanggal/bulan',
      'Export — download ke Excel',
    ],
    tips: [
      'Cek trial balance bulanan sebelum tutup buku',
      'Total Debit harus sama dengan Total Kredit — jika tidak sama ada kesalahan jurnal',
      'Gunakan sebagai dasar menyusun laporan L/R dan Neraca',
    ],
  },

  'fin-general-ledger': {
    title: 'Buku Besar (General Ledger)',
    icon: FileText,
    purpose: 'Lihat rincian semua transaksi per akun — mutasi debit/kredit, referensi jurnal, dan saldo berjalan. Buku besar adalah catatan akuntansi terlengkap.',
    whoUses: 'Akuntan, Manajer Keuangan, Auditor',
    sections: [
      'Pilih Akun — filter buku besar per akun',
      'Rincian Transaksi — semua entri dengan tanggal, keterangan, debit/kredit',
      'Saldo Berjalan — saldo kumulatif setiap transaksi',
    ],
    buttons: [
      { label: 'Filter Periode', icon: Filter, action: 'Filter transaksi berdasarkan tanggal', when: 'Review transaksi periode tertentu' },
      { label: 'Export Excel', icon: Download, action: 'Download buku besar ke Excel', when: 'Audit atau rekonsiliasi' },
    ],
    tips: [
      'Gunakan untuk menelusuri "dari mana" saldo akun berasal',
      'Klik referensi jurnal untuk lihat dokumen asal transaksi',
    ],
  },

  'fin-periods': {
    title: 'Periode Akuntansi',
    icon: Calendar,
    purpose: 'Kelola periode akuntansi (bulan/tahun fiskal) — buka, tutup, dan lock periode. Periode yang dikunci mencegah posting transaksi mundur.',
    whoUses: 'Manajer Keuangan, Akuntan Senior',
    sections: [
      'Daftar Periode — semua periode dengan status (open/closed/locked)',
      'Buka/Tutup Periode — ubah status periode',
    ],
    buttons: [
      { label: 'Tutup Periode', icon: CheckCircle2, action: 'Tutup periode bulan yang sudah selesai', when: 'Setelah semua jurnal bulan tersebut selesai' },
      { label: 'Buka Kembali', icon: RefreshCw, action: 'Buka kembali periode yang sudah ditutup', when: 'Ada koreksi yang perlu diposting di periode lama' },
    ],
    warnings: [
      'Periode yang dikunci (locked) tidak bisa dibuka kembali — gunakan dengan hati-hati',
      'Tutup periode hanya setelah semua rekonsiliasi selesai',
    ],
  },

  'fin-posting-profiles': {
    title: 'Profil Posting Akuntansi',
    icon: FileText,
    purpose: 'Konfigurasi auto-posting — akun GL mana yang di-debit/kredit otomatis saat ada transaksi tertentu (penjualan, pembelian, payroll, dll).',
    whoUses: 'Akuntan Senior, Manajer Keuangan',
    sections: [
      'Profil per Tipe Transaksi — konfigurasi per jenis transaksi',
      'Akun Debit/Kredit — atur akun yang digunakan',
    ],
    tips: [
      'Setup posting profile di awal implementasi sistem',
      'Konsultasikan dengan akuntan/auditor untuk standar akuntansi yang tepat',
    ],
    warnings: [
      'Perubahan posting profile berdampak pada semua transaksi setelahnya',
    ],
  },

  'fin-pnl': {
    title: 'Laporan Laba Rugi (P&L)',
    icon: BarChart4,
    purpose: 'Laporan Laba Rugi periodik — pendapatan, beban produksi, beban operasional, dan laba bersih. Dasar pengambilan keputusan manajemen.',
    whoUses: 'Manajer Keuangan, Direktur',
    sections: [
      'Pendapatan — total penjualan per periode',
      'HPP — harga pokok penjualan',
      'Laba Kotor — pendapatan dikurangi HPP',
      'Beban Operasional — biaya non-produksi',
      'Laba Bersih — hasil akhir',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Filter, action: 'Ganti periode laporan L/R', when: 'Analisis bulanan, triwulan, atau tahunan' },
      { label: 'Export Excel', icon: Download, action: 'Download laporan L/R ke Excel', when: 'Laporan untuk direksi atau investor' },
    ],
    tips: [
      'Bandingkan dua periode untuk analisis tren profitabilitas',
      'Margin kotor < 20% perlu audit biaya produksi',
      'Format nilai dalam Rp. dengan pemisah ribuan',
    ],
  },

  'fin-balance-sheet': {
    title: 'Neraca (Balance Sheet)',
    icon: BarChart4,
    purpose: 'Laporan posisi keuangan perusahaan — aset, kewajiban, dan ekuitas per tanggal tertentu. Total Aset harus sama dengan Total Kewajiban + Ekuitas.',
    whoUses: 'Manajer Keuangan, Direktur, Auditor',
    sections: [
      'Aset — aset lancar dan tidak lancar',
      'Kewajiban — hutang jangka pendek dan panjang',
      'Ekuitas — modal dan laba ditahan',
    ],
    buttons: [
      { label: 'Pilih Tanggal', icon: Calendar, action: 'Lihat posisi neraca per tanggal tertentu', when: 'Laporan akhir bulan/tahun' },
      { label: 'Export Excel', icon: Download, action: 'Download neraca ke Excel', when: 'Laporan resmi' },
    ],
    tips: [
      'Neraca dibuat per tanggal spesifik (bukan periode)',
      'Aset = Kewajiban + Ekuitas — jika tidak balance, cek jurnal terakhir',
    ],
  },

  'fin-journal-list': {
    title: 'Daftar Jurnal',
    icon: FileText,
    purpose: 'Lihat semua jurnal yang telah diposting — manual maupun otomatis dari transaksi sistem. Untuk audit trail dan review akuntansi.',
    whoUses: 'Akuntan, Auditor',
    sections: [
      'Daftar Jurnal — semua jurnal terurut tanggal',
      'Detail Jurnal — lihat baris debit/kredit per jurnal',
      'Filter — cari jurnal berdasarkan akun, tanggal, atau referensi',
    ],
    buttons: [
      { label: 'Filter', icon: Filter, action: 'Filter jurnal berdasarkan kriteria', when: 'Mencari jurnal tertentu' },
      { label: 'Export', icon: Download, action: 'Export daftar jurnal ke Excel', when: 'Audit atau rekonsiliasi' },
    ],
    tips: [
      'Jurnal otomatis dibuat oleh sistem saat ada transaksi (sales, purchase, payroll)',
      'Gunakan pencarian referensi untuk menemukan jurnal dari dokumen tertentu',
    ],
  },

  'fin-ap-aging': {
    title: 'Aging Hutang (AP Aging)',
    icon: BarChart4,
    purpose: 'Analisis umur hutang ke supplier — klasifikasikan hutang berdasarkan usia (0-30, 31-60, 61-90, >90 hari) untuk prioritas pembayaran.',
    whoUses: 'Akuntan, Manajer Keuangan',
    sections: [
      'Aging Summary — total hutang per bucket umur',
      'Detail per Supplier — hutang per supplier dengan tanggal jatuh tempo',
    ],
    tips: [
      'Prioritaskan pembayaran hutang yang sudah >30 hari untuk hindari denda',
      'Hutang >60 hari bisa mempengaruhi hubungan dengan supplier',
    ],
  },

  'fin-cash-flow': {
    title: 'Arus Kas (Cash Flow)',
    icon: BarChart4,
    purpose: 'Laporan arus kas — dari mana uang masuk dan ke mana uang keluar. Dibagi menjadi tiga aktivitas: operasi, investasi, dan pendanaan.',
    whoUses: 'Manajer Keuangan, Direktur',
    sections: [
      'Arus Kas Operasi — dari aktivitas bisnis sehari-hari',
      'Arus Kas Investasi — pembelian/penjualan aset',
      'Arus Kas Pendanaan — modal, dividen, pinjaman',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Filter, action: 'Ganti periode laporan arus kas', when: 'Analisis bulanan' },
      { label: 'Export Excel', icon: Download, action: 'Download laporan arus kas', when: 'Laporan resmi' },
    ],
    tips: [
      'Arus kas operasi negatif berturut-turut = tanda bahaya likuiditas',
      'Monitor arus kas mingguan untuk pastikan ada cukup kas untuk operasi',
    ],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL SDM (HR)
   * ════════════════════════════════════════════════════════════════ */

  'hr-dashboard': {
    title: 'Dashboard SDM',
    icon: Gauge,
    purpose: 'Ringkasan data sumber daya manusia — total karyawan, kehadiran hari ini, cuti pending, status payroll, dan indikator HR lainnya.',
    whoUses: 'Manajer SDM, Direktur',
    sections: [
      'KPI SDM — total karyawan, hadir hari ini, absensi',
      'Status Cuti — cuti pending persetujuan',
      'Payroll — status penggajian bulan ini',
      'Tren Kehadiran — grafik kehadiran 30 hari',
    ],
    tips: [
      'Monitor tingkat kehadiran harian untuk deteksi masalah lebih awal',
      'Cuti pending >5 hari perlu segera diproses',
    ],
  },

  'hr-employees': {
    title: 'Data Karyawan',
    icon: UserCheck,
    purpose: 'Kelola data master karyawan — biodata, jabatan, departemen, tanggal masuk, gaji pokok, dan status karyawan.',
    whoUses: 'HRD, Admin SDM',
    sections: [
      'Daftar Karyawan — semua karyawan aktif dan tidak aktif',
      'Form Tambah/Edit — data lengkap karyawan',
      'Detail Karyawan — riwayat jabatan, dokumen',
    ],
    buttons: [
      { label: 'Tambah Karyawan', icon: Plus, action: 'Daftarkan karyawan baru ke sistem', when: 'Ada karyawan baru bergabung' },
      { label: 'Edit', icon: Edit, action: 'Update data karyawan', when: 'Ada perubahan jabatan, gaji, atau informasi lain' },
      { label: 'Non-aktifkan', icon: XIcon, action: 'Tandai karyawan resign/pensiun', when: 'Karyawan berhenti bekerja' },
    ],
    tips: [
      'Data karyawan terintegrasi dengan modul Absensi, Payroll, dan Cuti',
      'Pastikan NPK (Nomor Pokok Karyawan) unik untuk setiap karyawan',
      'Upload dokumen kontrak kerja untuk arsip digital',
    ],
  },

  'hr-attendance': {
    title: 'Absensi & Kehadiran',
    icon: CalendarClock,
    purpose: 'Kelola data kehadiran karyawan — rekam absen masuk/keluar, hitung jam kerja, lembur, dan ketidakhadiran. Data ini otomatis masuk ke perhitungan payroll.',
    whoUses: 'HRD, Supervisor, Admin SDM',
    sections: [
      'Rekap Absensi — kehadiran per karyawan per periode',
      'Input Absensi Manual — koreksi data absensi',
      'Laporan Ketidakhadiran — summary absen, izin, sakit',
    ],
    buttons: [
      { label: 'Input Absensi', icon: Plus, action: 'Catat kehadiran manual atau koreksi data', when: 'Koreksi data mesin absensi atau input manual' },
      { label: 'Export Rekap', icon: Download, action: 'Unduh rekap absensi ke Excel', when: 'Laporan absensi bulanan' },
    ],
    tips: [
      'Data absensi terintegrasi langsung dengan perhitungan payroll',
      'Karyawan absen tanpa keterangan otomatis dipotong gajinya sesuai profil payroll',
      'Lembur harus diinput agar terhitung di slip gaji',
    ],
  },

  'hr-payroll-profiles': {
    title: 'Profil Penggajian',
    icon: FileText,
    purpose: 'Konfigurasi komponen gaji per karyawan atau grup karyawan — gaji pokok, tunjangan tetap, tunjangan tidak tetap, BPJS, pajak PPh 21, dan potongan lainnya.',
    whoUses: 'HRD, Manajer SDM',
    sections: [
      'Daftar Profil — semua template profil gaji',
      'Komponen Gaji — Gaji Pokok, Tunjangan Makan, Transport, dll.',
      'Potongan — BPJS Ketenagakerjaan, BPJS Kesehatan, PPh 21',
    ],
    buttons: [
      { label: 'Buat Profil', icon: Plus, action: 'Buat template profil gaji baru', when: 'Ada jabatan/grup baru dengan struktur gaji berbeda' },
      { label: 'Edit', icon: Edit, action: 'Update komponen gaji dalam profil', when: 'Ada penyesuaian upah minimum atau kebijakan gaji' },
    ],
    tips: [
      'Format semua nilai gaji dalam Rp. (Rupiah) — contoh: Rp 3.500.000',
      'Profil bisa di-assign ke banyak karyawan dengan struktur gaji sama',
      'BPJS Ketenagakerjaan: JHT 5.7% (3.7% pemberi kerja + 2% karyawan)',
      'Pastikan sesuai UMK/UMR yang berlaku di daerah',
    ],
  },

  'hr-payroll-run': {
    title: 'Proses Penggajian (Payroll Run)',
    icon: FileText,
    purpose: 'Hitung dan proses penggajian bulanan semua karyawan — buat slip gaji, finalize, dan generate jurnal akuntansi otomatis. Proses utama penggajian bulanan.',
    whoUses: 'HRD, Manajer SDM, Akuntan',
    sections: [
      'Buat Payroll Run — pilih periode bulan dan karyawan',
      'Review Slip Gaji — verifikasi perhitungan sebelum finalize',
      'Finalize — konfirmasi dan kunci data payroll bulan ini',
      'Cetak/Export Slip — download slip gaji per karyawan',
    ],
    buttons: [
      { label: 'Buat Payroll Run', icon: Plus, action: 'Mulai proses penggajian bulan baru', when: 'Akhir bulan, setelah data absensi final' },
      { label: 'Finalize', icon: CheckCircle2, action: 'Kunci data payroll — tidak bisa diubah lagi', when: 'Semua slip sudah diverifikasi dan benar' },
      { label: 'Cetak Slip Gaji', icon: Printer, action: 'Download slip gaji PDF per karyawan', when: 'Distribusikan ke karyawan' },
      { label: 'Export Excel', icon: Download, action: 'Export rekap payroll ke Excel', when: 'Laporan ke direktur atau akuntan' },
    ],
    tips: [
      'Semua nominal dalam format Rp. (Rupiah) — Rp 5.200.000',
      'Buat payroll run hanya setelah data absensi bulan tersebut sudah final',
      'Review minimal 3 slip sampel sebelum finalize untuk cek perhitungan',
      'Setelah finalize, sistem otomatis generate jurnal ke akuntansi',
    ],
    warnings: [
      'Payroll Run yang sudah di-finalize tidak bisa diubah — buat run baru untuk koreksi',
      'JANGAN finalize sebelum semua data absensi dan lembur lengkap',
    ],
  },

  'hr-leave': {
    title: 'Manajemen Cuti & Izin',
    icon: Calendar,
    purpose: 'Proses pengajuan dan persetujuan cuti/izin karyawan — cuti tahunan, sakit, keperluan keluarga, dsb. Integrasi dengan absensi dan payroll.',
    whoUses: 'Karyawan (pengajuan), HRD, Supervisor (persetujuan)',
    sections: [
      'Pengajuan Cuti — form pengajuan dari karyawan',
      'Pending Approval — cuti yang menunggu persetujuan',
      'Saldo Cuti — sisa cuti per karyawan',
      'Kalender Cuti — jadwal cuti tim',
    ],
    buttons: [
      { label: 'Ajukan Cuti', icon: Plus, action: 'Buat pengajuan cuti baru', when: 'Karyawan ingin ambil cuti' },
      { label: 'Setujui', icon: CheckCircle2, action: 'Setujui permohonan cuti', when: 'Supervisor/HRD menyetujui' },
      { label: 'Tolak', icon: XIcon, action: 'Tolak permohonan dengan alasan', when: 'Tidak bisa diizinkan karena kebutuhan produksi' },
    ],
    tips: [
      'Cuti tahunan: 12 hari/tahun (standar UU Ketenagakerjaan Indonesia)',
      'Cuti yang disetujui otomatis masuk ke kalender tim dan data absensi',
      'Saldo cuti dikurangi otomatis setelah cuti selesai',
    ],
  },

  'hr-reports': {
    title: 'Laporan SDM',
    icon: BarChart4,
    purpose: 'Laporan komprehensif data SDM — headcount, turnover, absensi, produktivitas per karyawan, dan analisis tenaga kerja.',
    whoUses: 'Manajer SDM, Direktur',
    sections: [
      'Laporan Headcount — jumlah karyawan per departemen',
      'Laporan Absensi — rekap kehadiran per periode',
      'Laporan Turnover — karyawan masuk dan keluar',
      'Laporan Produktivitas — output per karyawan/operator',
      'Laporan Payroll Summary — total penggajian per periode',
    ],
    buttons: [
      { label: 'Filter Periode', icon: Filter, action: 'Pilih periode laporan', when: 'Laporan bulanan/triwulan' },
      { label: 'Export Excel', icon: Download, action: 'Download laporan ke Excel', when: 'Laporan untuk manajemen' },
    ],
    tips: [
      'Semua nilai gaji/upah dalam format Rp. (Rupiah)',
      'Laporan produktivitas terintegrasi dengan data output produksi per operator',
      'Gunakan laporan turnover untuk analisis retensi karyawan',
    ],
  },

  'hr-ai-insights': {
    title: 'AI Insights SDM',
    icon: Sparkles,
    purpose: 'Analitik SDM berbasis AI — identifikasi pola absensi, prediksi risiko turnover, dan rekomendasi tindakan SDM berdasarkan data historis.',
    whoUses: 'Manajer SDM, Direktur',
    sections: [
      'Ringkasan AI — insight otomatis dari data SDM',
      'Pola Absensi — identifikasi karyawan dengan absensi tinggi',
      'Rekomendasi — tindakan yang disarankan AI',
    ],
    tips: [
      'AI insights diperbarui setiap hari berdasarkan data terbaru',
      'Gunakan sebagai input untuk rapat evaluasi SDM bulanan',
    ],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL SAYA (SELF-SERVICE)
   * ════════════════════════════════════════════════════════════════ */

  'self-dashboard': {
    title: 'Portal Saya (Self-Service)',
    icon: UserCheck,
    purpose: 'Portal mandiri karyawan — lihat slip gaji, cek saldo dan histori cuti, rekap absensi pribadi, WO yang ditugaskan, dan pengumuman perusahaan.',
    whoUses: 'Semua Karyawan',
    sections: [
      'Slip Gaji — lihat dan download slip gaji bulanan',
      'Cuti — saldo cuti, histori cuti, ajukan cuti baru',
      'Absensi — rekap kehadiran pribadi bulan ini',
      'Work Order — WO/LKP yang ditugaskan ke saya',
      'Pengumuman — info dari manajemen/HRD',
    ],
    buttons: [
      { label: 'Ajukan Cuti', icon: Plus, action: 'Buat pengajuan cuti atau izin', when: 'Ingin ambil cuti' },
      { label: 'Download Slip Gaji', icon: Download, action: 'Download slip gaji bulan ini sebagai PDF', when: 'Keperluan KPR, BPJS, atau arsip pribadi' },
    ],
    tips: [
      'Slip gaji hanya tersedia setelah HRD menyelesaikan payroll bulan tersebut',
      'Ajukan cuti minimal 3 hari sebelum tanggal mulai (kecuali sakit)',
      'Hubungi HRD jika data absensi tidak sesuai',
    ],
  },

  /* ╔══════════════════════════════════════════════════════════════
   * PORTAL PRODUKSI — ANALITIK & KEPUTUSAN
   * ════════════════════════════════════════════════════════════════ */

  'prod-defect-codes': {
    title: 'Kode Defect Kualitas',
    icon: AlertTriangle,
    purpose: 'Kelola kode defect standar untuk pencatatan hasil QC. Kode defect yang terdefinisi dengan baik memungkinkan analisis Pareto kualitas yang akurat.',
    whoUses: 'QC Inspector, Manajer QC, PPIC',
    sections: [
      'Daftar Kode Defect — semua kode defect aktif',
      'Form Tambah/Edit — buat kode defect baru',
      'Frekuensi — berapa kali kode ini muncul',
    ],
    buttons: [
      { label: 'Tambah Kode', icon: Plus, action: 'Buat kode defect baru', when: 'Ada jenis cacat baru yang perlu dikategorikan' },
      { label: 'Edit', icon: Edit, action: 'Update deskripsi kode defect', when: 'Penyempurnaan definisi' },
    ],
    tips: [
      'Kode defect yang spesifik = analisis kualitas yang lebih baik',
      'Standarisasi nama kode dengan semua QC inspector sebelum digunakan',
    ],
  },

  'prod-pareto': {
    title: 'Analisis Pareto Defect',
    icon: BarChart4,
    purpose: 'Analisis Pareto (80-20) untuk identifikasi jenis defect yang paling sering terjadi. Fokuskan perbaikan pada 20% jenis defect yang menyebabkan 80% masalah kualitas.',
    whoUses: 'Manajer QC, PPIC, Supervisor Produksi',
    sections: [
      'Grafik Pareto — bar chart + cumulative line',
      'Tabel Defect — rank dari paling sering ke jarang',
      'Filter — filter per model, periode, lini',
    ],
    buttons: [
      { label: 'Filter', icon: Filter, action: 'Filter data berdasarkan model/periode/lini', when: 'Analisis per model atau period tertentu' },
      { label: 'Export', icon: Download, action: 'Download grafik dan data', when: 'Presentasi atau laporan kualitas' },
    ],
    tips: [
      'Fokus tindakan perbaikan pada defect yang ada di 20% pertama (kiri grafik)',
      'Bandingkan Pareto bulan ini vs bulan lalu untuk lihat efek perbaikan',
    ],
    relatedScenarios: ['s2'],
  },

  'prod-fpy': {
    title: 'FPY — First Pass Yield',
    icon: BarChart4,
    purpose: 'Analisis First Pass Yield (FPY) — persentase garmen yang lulus QC tanpa perlu rework. FPY tinggi = kualitas produksi yang baik.',
    whoUses: 'Manajer QC, PPIC, Supervisor Produksi',
    sections: [
      'FPY Keseluruhan — rata-rata FPY seluruh WO',
      'FPY per Model — breakdown per jenis garmen',
      'FPY per Lini — perbandingan per lini produksi',
      'Tren FPY — grafik perkembangan waktu',
    ],
    tips: [
      'FPY target minimal 95% untuk produksi garmen rajut',
      'FPY rendah per lini → investigasi mesin, operator, atau material',
      'Bandingkan FPY model baru vs model lama untuk evaluasi kompleksitas',
    ],
    relatedScenarios: ['s2'],
  },

  'prod-downtime': {
    title: 'Analisis Downtime',
    icon: Siren,
    purpose: 'Monitor dan analisis downtime mesin/lini produksi — kapan terjadi, berapa lama, penyebab, dan dampak terhadap OEE dan output.',
    whoUses: 'Supervisor Produksi, Maintenance, PPIC',
    sections: [
      'Rekap Downtime — total downtime per periode',
      'Breakdown per Sebab — kategori penyebab downtime',
      'Tren — grafik downtime harian/mingguan',
      'Impact OEE — dampak downtime terhadap OEE',
    ],
    tips: [
      'Catat penyebab downtime spesifik (bukan hanya "mesin rusak")',
      'Downtime >2 jam/hari per lini perlu tindakan maintenance segera',
      'Preventive maintenance yang baik mengurangi downtime tidak terencana',
    ],
    relatedScenarios: ['s4'],
  },

  'prod-backlog': {
    title: 'Analisis Backlog',
    icon: ListChecks,
    purpose: 'Monitor backlog produksi — pesanan yang belum selesai, WO yang terlambat, dan proyeksi penyelesaian. Alat perencanaan kapasitas.',
    whoUses: 'PPIC, Supervisor Produksi, Manajer',
    sections: [
      'Daftar Backlog — WO yang terlambat atau berisiko',
      'Analisis Keterlambatan — berapa hari terlambat per WO',
      'Proyeksi — kapan backlog bisa diselesaikan',
    ],
    tips: [
      'Review backlog setiap Senin pagi untuk prioritas minggu ini',
      'WO terlambat >5 hari perlu eskalasi ke manajemen',
    ],
    relatedScenarios: ['s1'],
  },

  'prod-ai-insights': {
    title: 'AI Insights Produksi',
    icon: Sparkles,
    purpose: 'Analitik berbasis AI untuk produksi — identifikasi bottleneck, prediksi keterlambatan WO, analisis root cause masalah, dan rekomendasi optimasi.',
    whoUses: 'PPIC, Supervisor Produksi, Manajer',
    sections: [
      'Ringkasan Harian — insight otomatis hari ini',
      'Analisis Root Cause — penyebab masalah terkini',
      'Prediksi — WO yang berisiko terlambat',
      'Chatbot AI — tanya jawab bebas tentang data produksi',
    ],
    tips: [
      'Gunakan chatbot untuk query cepat: "Berapa output lini A hari ini?"',
      'AI insights diperbarui setiap jam berdasarkan data WIP terbaru',
      'Rekomendasi AI perlu divalidasi oleh supervisor sebelum diterapkan',
    ],
    relatedScenarios: ['s1', 's4'],
  },

  'prod-production-calendar': {
    title: 'Kalender Produksi',
    icon: Calendar,
    purpose: 'Jadwal produksi visual dalam tampilan kalender — lihat WO per lini per hari, hari libur, dan kapasitas tersisa. Alat perencanaan produksi visual.',
    whoUses: 'PPIC, Supervisor Produksi',
    sections: [
      'Kalender Bulanan — WO terjadwal per lini',
      'Hari Libur — tandai hari libur nasional dan pabrik',
      'Kapasitas — visualisasi utilisasi per hari',
    ],
    buttons: [
      { label: 'Tandai Libur', icon: Calendar, action: 'Tambahkan hari libur ke kalender produksi', when: 'Ada hari libur nasional atau pabrik' },
    ],
    tips: [
      'Kalender produksi terintegrasi dengan APS Gantt untuk penjadwalan detail',
      'Hari merah = libur, abu = kapasitas penuh',
    ],
  },

  'prod-aql-calculator': {
    title: 'Kalkulator AQL (Acceptance Quality Limit)',
    icon: ClipboardList,
    purpose: 'Hitung ukuran sampel QC berdasarkan standar AQL internasional. Tentukan berapa pcs yang perlu diperiksa dari satu lot untuk keputusan terima/tolak.',
    whoUses: 'QC Inspector, Manajer QC',
    sections: [
      'Input Lot Size — jumlah total pcs dalam lot',
      'Pilih AQL Level — 0.65, 1.0, 1.5, 2.5, 4.0',
      'Hasil — ukuran sampel + batas akseptabel/tolak',
    ],
    tips: [
      'AQL 1.5 adalah standar umum garmen export',
      'Semakin kecil AQL, semakin ketat standar kualitas — perlu sampel lebih banyak',
      'Gunakan Inspection Level II untuk kondisi normal',
    ],
  },

  'prod-locations': {
    title: 'Gedung & Zona Produksi',
    icon: Boxes,
    purpose: 'Master data lokasi produksi — gedung, lantai, zona, dan area kerja. Digunakan untuk assignment lini produksi dan tracking posisi mesin/bundle.',
    whoUses: 'Admin, Supervisor Produksi',
    sections: [
      'Pohon Lokasi — hierarki gedung ke zona',
      'Form Tambah/Edit — buat lokasi baru',
    ],
    tips: [
      'Penamaan yang sistematis memudahkan koordinasi antar shift',
      'Lokasi digunakan di modul lini produksi dan shift handover',
    ],
  },

  'prod-processes': {
    title: 'Proses Produksi',
    icon: Activity,
    purpose: 'Master data proses produksi beserta urutan alurnya. Alur standar: Rajut (1) → Linking (2) → Sewing (3) → Steam (4) → QC (5) → Packing (6) → Rework (R).',
    whoUses: 'Admin, PPIC, Manajer Produksi',
    sections: [
      'Daftar Proses — semua proses dengan urutan',
      'Form Tambah/Edit — buat atau ubah proses',
    ],
    tips: [
      'URUTAN PROSES PENTING: Steam (4) harus sebelum QC (5)',
      'Proses Rework adalah proses samping — garmen gagal QC kembali ke Rework lalu QC ulang',
      'Jangan ubah urutan proses tanpa konsultasi dengan PPIC',
    ],
    warnings: [
      'QC dilakukan SETELAH Steam — garmen harus sudah di-steam sebelum pemeriksaan',
    ],
  },

  'prod-shifts': {
    title: 'Shift Kerja',
    icon: CalendarClock,
    purpose: 'Kelola jadwal shift kerja — jam mulai, jam selesai, istirahat. Data shift digunakan untuk kalkulasi kapasitas produksi dan OEE.',
    whoUses: 'Admin, Supervisor Produksi',
    sections: [
      'Daftar Shift — semua shift yang tersedia',
      'Form Tambah/Edit — buat atau ubah shift',
    ],
    tips: [
      'Durasi shift yang akurat penting untuk kalkulasi OEE yang benar',
      'Istirahat di-exclude dari waktu produksi (tidak masuk hitung OEE)',
    ],
  },

  'prod-machines': {
    title: 'Mesin Rajut',
    icon: Zap,
    purpose: 'Master data mesin rajut — jenis, spesifikasi, nomor mesin, kapasitas. Data mesin digunakan untuk assignment operator dan tracking downtime.',
    whoUses: 'Admin, Supervisor Produksi, Maintenance',
    sections: [
      'Daftar Mesin — semua mesin dengan status',
      'Spesifikasi — jenis rajut, gauge, kapasitas',
      'Status Mesin — aktif, maintenance, rusak',
    ],
    buttons: [
      { label: 'Tambah Mesin', icon: Plus, action: 'Daftarkan mesin baru', when: 'Ada penambahan mesin baru' },
      { label: 'Update Status', icon: Edit, action: 'Ubah status mesin (aktif/maintenance/rusak)', when: 'Ada perubahan kondisi mesin' },
    ],
    tips: [
      'Update status mesin segera saat masuk maintenance untuk akurasi OEE',
      'Mesin "rusak" tidak dihitung dalam kapasitas produksi',
    ],
  },

  'prod-lines': {
    title: 'Lini Produksi',
    icon: Activity,
    purpose: 'Master data lini produksi — nama lini, kapasitas, supervisor penanggung jawab, dan stasiun kerja yang ada. Lini adalah unit produksi terkecil.',
    whoUses: 'Admin, PPIC, Supervisor',
    sections: [
      'Daftar Lini — semua lini dengan kapasitas',
      'Form Tambah/Edit — buat lini baru',
    ],
    tips: [
      'Kapasitas lini digunakan untuk perencanaan WO dan APS Gantt',
      'Setiap lini butuh supervisor yang assigned',
    ],
  },

  'prod-models': {
    title: 'Model Produk',
    icon: Package,
    purpose: 'Master data model garmen yang diproduksi — kode model, nama, kategori, spesifikasi teknis, dan gambar teknik. Dasar untuk BOM dan SOP.',
    whoUses: 'PPIC, Admin, Desainer',
    sections: [
      'Daftar Model — semua model aktif',
      'Detail Model — spesifikasi lengkap',
      'Upload Gambar Teknis — tech pack garmen',
    ],
    buttons: [
      { label: 'Tambah Model', icon: Plus, action: 'Daftarkan model garmen baru', when: 'Ada desain baru yang akan diproduksi' },
      { label: 'Edit', icon: Edit, action: 'Update spesifikasi model', when: 'Ada revisi desain' },
    ],
    tips: [
      'Kode model harus unik dan deskriptif',
      'Lengkapi BOM setelah buat model baru untuk bisa generate material issue otomatis',
    ],
  },

  'prod-sizes': {
    title: 'Ukuran (Size)',
    icon: Activity,
    purpose: 'Master data ukuran garmen — S, M, L, XL, dll. dengan dimensi dan spesifikasi. Ukuran digunakan di WO, BOM, dan bundle.',
    whoUses: 'Admin, PPIC',
    sections: [
      'Daftar Ukuran — semua ukuran yang tersedia',
      'Urutan — urutan tampil di dokumen',
    ],
    buttons: [
      { label: 'Tambah Ukuran', icon: Plus, action: 'Daftarkan ukuran baru', when: 'Ada request ukuran khusus dari buyer' },
    ],
    tips: [
      'Urutkan ukuran dari kecil ke besar untuk konsistensi dokumen',
    ],
  },

  'prod-bom': {
    title: 'BOM (Bill of Materials)',
    icon: ListChecks,
    purpose: 'Daftar kebutuhan material untuk setiap model garmen per pcs. BOM digunakan untuk kalkulasi kebutuhan material saat WO dibuat dan untuk Material Issue.',
    whoUses: 'PPIC, Admin, R&D',
    sections: [
      'BOM per Model — daftar material dan qty per pcs',
      'Form BOM — tambah/edit komponen material',
      'Kalkulasi — proyeksi kebutuhan untuk qty WO tertentu',
    ],
    buttons: [
      { label: 'Tambah Komponen', icon: Plus, action: 'Tambah material ke BOM model ini', when: 'Ada material baru dalam komposisi garmen' },
      { label: 'Edit Qty', icon: Edit, action: 'Update kebutuhan qty per pcs', when: 'Ada perubahan formula/komposisi' },
    ],
    tips: [
      'BOM harus akurat untuk MI yang tepat — kelebihan material = waste, kekurangan = produksi terhenti',
      'Update BOM jika ada perubahan desain atau supplier material',
    ],
    warnings: [
      'BOM yang salah menyebabkan shortage atau overstock material',
    ],
  },

  'prod-sop': {
    title: 'SOP Produksi',
    icon: FileText,
    purpose: 'Standar Operasional Prosedur per proses per model — instruksi kerja detail, parameter mesin, dan standar kualitas yang harus diikuti operator.',
    whoUses: 'Supervisor, Operator, QC, Training',
    sections: [
      'SOP per Proses — pilih proses (rajut/linking/steam/dll)',
      'SOP per Model — spesifik untuk model tertentu',
      'Versi SOP — histori perubahan',
    ],
    buttons: [
      { label: 'Buat SOP', icon: Plus, action: 'Tulis SOP baru untuk proses/model', when: 'Ada proses baru atau model baru' },
      { label: 'Update', icon: Edit, action: 'Revisi SOP yang sudah ada', when: 'Ada penyempurnaan prosedur' },
    ],
    tips: [
      'SOP harus dipahami oleh operator sebelum mulai produksi',
      'Lampirkan foto atau gambar untuk SOP yang kompleks',
      'Versi kontrol SOP penting — jangan hapus SOP lama, buat versi baru',
    ],
  },

  'prod-shipments': {
    title: 'Pengiriman Produk',
    icon: Package,
    purpose: 'Kelola pengiriman garmen jadi ke buyer — buat dokumen pengiriman, track status, dan catat nomor resi. Terintegrasi dengan invoice AR.',
    whoUses: 'Staf Pengiriman, Admin',
    sections: [
      'Daftar Pengiriman — semua shipment dengan status',
      'Buat Pengiriman — pilih WO/order yang siap kirim',
      'Dokumen Pengiriman — surat jalan, packing list',
    ],
    buttons: [
      { label: 'Buat Pengiriman', icon: Plus, action: 'Buat dokumen pengiriman baru', when: 'Garmen sudah selesai packing dan siap kirim' },
      { label: 'Update Status', icon: Edit, action: 'Update status pengiriman (in transit/delivered)', when: 'Update dari kurir/ekspedisi' },
      { label: 'Cetak Surat Jalan', icon: Printer, action: 'Print dokumen surat jalan', when: 'Diperlukan untuk pengiriman fisik' },
    ],
    tips: [
      'Buat pengiriman hanya dari WO yang sudah 100% selesai packing',
      'Simpan nomor resi untuk tracking dan bukti pengiriman',
    ],
  },

  /* ═══════════════════════════════════════════════════════════════════════
   * PORTAL PENGADAAN (2026-08-06)
   * Sembilan pintu di portal baru sebelumnya tersebar di Gudang/Keuangan/
   * Aksesoris dan HANYA `wh-purchase-orders` yang punya panduan. Akibatnya
   * pengguna membuka portal baru tanpa penjelasan apa pun. Ditulis lengkap
   * di sini supaya tombol "Panduan" di setiap modul pengadaan berisi.
   * ═══════════════════════════════════════════════════════════════════════ */
  'proc-dashboard': {
    title: 'Dashboard Pengadaan',
    icon: Gauge,
    purpose: 'Satu layar untuk melihat seluruh siklus beli barang: permintaan (PR) menunggu, PO terbuka, barang belum datang, faktur belum dibayar, dan peringatan PO telat.',
    whoUses: 'Staf & Manajer Pengadaan, Kepala Gudang, Keuangan',
    sections: [
      'Kartu KPI — PR menunggu, PO terbuka, nilai belanja bulan ini, faktur jatuh tempo',
      'Funnel P2P — PR → PO → Penerimaan → Faktur dalam satu alur',
      'Peringatan — PO melewati tanggal kirim, PO tanpa Master Supplier, faktur jatuh tempo',
    ],
    buttons: [
      { label: 'Muat Ulang', icon: RefreshCw, action: 'Ambil angka terbaru dari server', when: 'Setelah membuat PR/PO baru' },
      { label: 'Klik kartu KPI', icon: Eye, action: 'Melompat ke modul terkait dengan filter yang sesuai', when: 'Ingin menindaklanjuti angka yang terlihat' },
    ],
    tips: [
      'Mulai hari kerja dari sini: kartu "PR menunggu persetujuan" adalah antrean kerja Anda',
      'Peringatan "PO tanpa Master Supplier" menandai data lama — rapikan lewat Master Supplier → Migrasi',
    ],
    warnings: [
      'Angka dihitung dari data nyata (PR/PO/GR/AP). Kalau nol semua, memang belum ada transaksi pada periode itu',
    ],
  },

  'proc-suppliers': {
    title: 'Master Supplier',
    icon: Boxes,
    purpose: 'Sumber tunggal data supplier: kode, NPWP, kontak, rekening, termin bayar, kategori, lead time, dan daftar harga per satuan beli. Menggantikan pengisian nama supplier sebagai teks bebas.',
    whoUses: 'Staf & Manajer Pengadaan, Keuangan',
    sections: [
      'Daftar Supplier — cari, filter kategori/status, aktif & nonaktif',
      'Form Supplier — identitas, kontak, bank, termin, kategori, lead time',
      'Daftar Harga — harga per material per satuan beli + MOQ + masa berlaku',
      'Migrasi Data Lama — ubah nama supplier teks bebas di PO/GRN lama menjadi master',
    ],
    buttons: [
      { label: 'Tambah Supplier', icon: Plus, action: 'Daftarkan supplier baru (kode SUP-xxxx dibuat otomatis)', when: 'Ada supplier baru yang akan ditransaksikan' },
      { label: 'Daftar Harga', icon: ListChecks, action: 'Kelola harga per material & satuan beli supplier tersebut', when: 'Supplier mengirim price list baru' },
      { label: 'Migrasi Data Lama', icon: Upload, action: 'Pratinjau lalu jalankan pembuatan master dari nama supplier lama + isi supplier_id', when: 'Sekali saat mulai memakai portal ini' },
      { label: 'Nonaktifkan / Aktifkan', icon: XIcon, action: 'Menyembunyikan supplier dari pilihan PO tanpa menghapus riwayat', when: 'Supplier berhenti dipakai' },
    ],
    tips: [
      'Isi daftar harga: harga PO akan terisi otomatis saat memilih material + supplier',
      'Satu supplier boleh punya beberapa kategori (kain, aksesoris, jasa) — dipakai untuk filter dan analisis belanja',
      'Nama supplier dijaga unik (tanpa peduli besar-kecil huruf & spasi ganda) sehingga tidak muncul dua kartu untuk satu perusahaan',
    ],
    warnings: [
      'Supplier yang sudah dipakai PO tidak bisa dihapus — nonaktifkan saja agar riwayat & penilaian tetap utuh',
      'Migrasi hanya membuat data yang belum ada (idempoten): menjalankannya dua kali tidak menduplikasi',
    ],
  },

  'proc-requests': {
    title: 'Permintaan Pengadaan (PR)',
    icon: ClipboardList,
    purpose: 'Divisi mengajukan kebutuhan barang/jasa, melewati rantai persetujuan, lalu diterbitkan menjadi Purchase Order. Item PR bisa ditautkan ke material master beserta satuan belinya.',
    whoUses: 'Semua divisi (pengaju), Dept Head & Manajer (penyetuju), Pengadaan (penerbit PO)',
    sections: [
      'Kotak Masuk Persetujuan — hanya PR yang menunggu tanda tangan Anda',
      'Daftar PR — filter status, departemen, prioritas',
      'Form PR — item (material master atau bebas), satuan beli, estimasi harga, alasan',
    ],
    buttons: [
      { label: 'Buat PR', icon: Plus, action: 'Ajukan permintaan pengadaan baru', when: 'Ada kebutuhan barang/jasa yang harus dibeli' },
      { label: 'Setujui / Tolak', icon: CheckCircle2, action: 'Memproses PR di antrean Anda beserta catatan', when: 'PR masuk ke kotak masuk persetujuan Anda' },
      { label: 'Buat PO', icon: FileText, action: 'Terbitkan Purchase Order dari PR yang sudah disetujui', when: 'PR berstatus Disetujui' },
    ],
    tips: [
      'Pilih material dari master bila ada — satuan, harga, dan stok jadi ikut terbawa ke PO',
      'Estimasi harga otomatis diusulkan dari daftar harga supplier saat material dipilih',
      'Item jasa / non-material tetap bisa diisi bebas (misal "biaya kirim")',
    ],
    warnings: [
      'PR yang sudah diterbitkan menjadi PO tidak bisa diubah — buat PR baru bila kebutuhan berubah',
    ],
    relatedScenarios: ['s3'],
  },

  'proc-purchase-orders': {
    title: 'Purchase Order (PO)',
    icon: FileText,
    purpose: 'Pesanan resmi ke supplier: pilih supplier dari master, input qty & harga dalam SATUAN BELI (mis. karton), sistem menyimpan hasil konversi ke satuan dasar untuk stok & jurnal.',
    whoUses: 'Staf & Manajer Pengadaan',
    sections: [
      'Daftar PO — filter status/tanggal/supplier + halaman (pagination)',
      'Form PO — supplier master, item material atau bebas, satuan beli, harga, tanggal kirim',
      'Detail PO — riwayat penerimaan, sisa qty, nilai, cetak PDF/Excel',
    ],
    buttons: [
      { label: 'Buat PO', icon: Plus, action: 'Terbitkan PO baru ke supplier', when: 'PR disetujui atau stok perlu diisi' },
      { label: 'Ajukan / Setujui', icon: CheckCircle2, action: 'Alirkan PO melalui persetujuan sebelum dikirim ke supplier', when: 'Isi PO sudah final' },
      { label: 'Kirim ke Supplier', icon: Upload, action: 'Tandai PO terkirim (mengunci perubahan isi)', when: 'PO sudah disetujui' },
      { label: 'Cetak / Unduh', icon: Printer, action: 'PDF & Excel PO memakai satuan beli supplier', when: 'Dikirim ke supplier atau diarsipkan' },
    ],
    tips: [
      'Harga terisi otomatis dari daftar harga supplier; tetap bisa ditimpa manual',
      'Kolom bantuan di bawah baris menunjukkan hasil konversi: mis. 10 ktn = 1.440 pcs',
      'Barang datang? Catat di Portal Gudang → Penerimaan Barang; qty diterima akan muncul di PO ini',
    ],
    warnings: [
      'PO yang sudah ada penerimaan sebagian tidak bisa dibatalkan',
      'Ganti satuan beli setelah harga diisi akan menghitung ulang nilai baris — periksa total sebelum simpan',
    ],
    relatedScenarios: ['s3'],
  },

  'proc-accessory-pr': {
    title: 'Request Aksesoris (Pembelian)',
    icon: Sparkles,
    purpose: 'Permintaan pembelian aksesoris (kancing, label, hangtag, kemasan) dari divisi aksesoris — pintunya dipindah ke Pengadaan karena semua pembelian kini satu tempat.',
    whoUses: 'Admin Aksesoris, Staf Pengadaan',
    sections: [
      'Daftar Request — status pengajuan pembelian aksesoris',
      'Form Request — item aksesoris, qty, kebutuhan tanggal, alasan',
    ],
    buttons: [
      { label: 'Buat Request', icon: Plus, action: 'Ajukan pembelian aksesoris', when: 'Stok aksesoris menipis atau ada order baru' },
      { label: 'Proses', icon: CheckCircle2, action: 'Tindak lanjuti menjadi PO ke supplier', when: 'Request disetujui' },
    ],
    tips: [
      'Stok & peminjaman aksesoris tetap dikelola di Portal Aksesoris — di sini khusus PEMBELIAN',
    ],
  },

  'proc-3way-match': {
    title: 'Rekonsiliasi 3-Arah (PO ↔ Penerimaan ↔ Faktur)',
    icon: ListChecks,
    purpose: 'Membandingkan qty & nilai yang DIPESAN, DITERIMA, dan DIFAKTUR dalam satuan dasar, sehingga selisih (kurang/lebih kirim, faktur kelebihan) terlihat sebelum dibayar.',
    whoUses: 'Pengadaan, Keuangan, Auditor internal',
    sections: [
      'KPI — jumlah PO cocok, menunggu, selisih, kelebihan/kekurangan',
      'Tabel per PO — ordered vs received vs invoiced + status kecocokan',
      'Detail per PO — daftar penerimaan & faktur yang menempel pada PO',
    ],
    buttons: [
      { label: 'Buka Detail', icon: Eye, action: 'Lihat rincian penerimaan & faktur satu PO', when: 'Ada tanda selisih pada baris PO' },
      { label: 'Filter', icon: Filter, action: 'Saring per status kecocokan / supplier / periode', when: 'Menelusuri kasus tertentu' },
    ],
    tips: [
      'Semua angka sudah dalam satuan dasar walau PO dibuat dalam karton — jadi bisa dibandingkan apa adanya',
      'Toleransi selisih kecil dapat diatur; di luar toleransi ditandai untuk ditindak',
    ],
    warnings: [
      'Jangan setujui pembayaran saat status masih "selisih" tanpa penjelasan dari supplier/gudang',
    ],
  },

  'proc-ap-invoices': {
    title: 'Faktur Supplier',
    icon: ClipboardSignature,
    purpose: 'Membuat tagihan hutang (AP) dari barang yang SUDAH diterima, lalu meneruskannya ke Keuangan untuk dibayar — mencegah membayar barang yang belum datang.',
    whoUses: 'Pengadaan, Keuangan (AP)',
    sections: [
      'Penerimaan Siap Difakturkan — GR yang belum punya faktur',
      'Daftar Faktur — status draft/terkirim/dibayar',
      'Form Faktur — nomor faktur supplier, tanggal, jatuh tempo, PPN',
    ],
    buttons: [
      { label: 'Buat Faktur dari Penerimaan', icon: Plus, action: 'Menghasilkan faktur AP memakai qty NET & harga satuan dasar', when: 'Faktur fisik dari supplier sudah diterima' },
      { label: 'Teruskan ke Keuangan', icon: Upload, action: 'Kirim faktur untuk dijadwalkan pembayarannya', when: 'Faktur sudah dicek terhadap rekonsiliasi 3-arah' },
    ],
    tips: [
      'Selalu cek Rekonsiliasi 3-Arah lebih dulu — nilai faktur mengikuti qty yang benar-benar diterima',
      'Qty NET = diterima dikurangi yang ditolak QC, jadi barang cacat tidak ikut terbayar',
    ],
    warnings: [
      'Nomor faktur supplier tidak boleh dobel — sistem menolak duplikat agar tidak terjadi bayar dua kali',
    ],
  },

  'proc-scorecard': {
    title: 'Penilaian Supplier',
    icon: BarChart4,
    purpose: 'Menilai supplier dari data nyata: ketepatan kirim, tingkat penerimaan QC, dan nilai belanja — dikelompokkan per Master Supplier sehingga perbedaan ejaan nama tidak memecah nilai.',
    whoUses: 'Manajer Pengadaan, Manajemen',
    sections: [
      'Tabel Penilaian — accept rate, grade, jumlah penerimaan, nilai belanja',
      'Detail Supplier — riwayat PO & inspeksi QC pembentuk nilai',
    ],
    buttons: [
      { label: 'Ubah Periode', icon: CalendarClock, action: 'Hitung ulang penilaian untuk rentang hari tertentu', when: 'Evaluasi bulanan/kuartalan' },
      { label: 'Buka Detail', icon: Eye, action: 'Melihat data pembentuk nilai satu supplier', when: 'Sebelum keputusan lanjut/stop kerja sama' },
    ],
    tips: [
      'Grade A–D dihitung dari accept rate; gunakan bersama ketepatan waktu kirim, bukan salah satu saja',
      'Baris "belum tertaut master" menandakan data lama — jalankan migrasi di Master Supplier agar nilainya menyatu',
    ],
  },

  'proc-analytics': {
    title: 'Analisis Belanja',
    icon: Activity,
    purpose: 'Menjawab "uang pengadaan habis ke mana": per supplier, per kategori, per material, dan trennya tiap bulan.',
    whoUses: 'Manajer Pengadaan, Keuangan, Manajemen',
    sections: [
      'Ringkasan — total belanja, jumlah PO, rata-rata nilai per PO',
      'Tren Bulanan — grafik nilai belanja per bulan',
      'Peringkat — supplier, kategori, dan material terbesar',
    ],
    buttons: [
      { label: 'Pilih Periode', icon: Calendar, action: 'Ganti rentang analisis (3/6/12/24 bulan)', when: 'Menyusun laporan atau negosiasi harga' },
      { label: 'Muat Ulang', icon: RefreshCw, action: 'Hitung ulang dari data PO terbaru', when: 'Setelah menerbitkan PO baru' },
    ],
    tips: [
      'Kategori "Item Bebas / Jasa" berisi baris PO tanpa material master — kalau porsinya besar, pertimbangkan dibuatkan master',
      'Pakai peringkat supplier bersama Penilaian Supplier: belanja besar + grade rendah = risiko yang harus ditindak',
    ],
  },

};

/* ─────────────────────────────────────────────────────────
 * Helper: get help by moduleId
 * ───────────────────────────────────────────────────────── */
export function getModuleHelp(moduleId) {
  return MODULE_HELP[moduleId] || null;
}

/* ─────────────────────────────────────────────────────────
 * Daftar moduleId yang punya diagram (selain screenshot biasa)
 * ───────────────────────────────────────────────────────── */
export const MODULES_WITH_DIAGRAM = {
  'prod-work-orders': 'wo-flow',
  'prod-oee': 'oee-formula',
  'prod-material-reservation': 'material-flow',
  'prod-bulk-mi': 'material-flow',
};
