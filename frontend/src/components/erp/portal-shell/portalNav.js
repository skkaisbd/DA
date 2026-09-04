/**
 * Portal Navigation Configuration — PortalShell.jsx companion
 *
 * Pure data + helper functions (no React imports). Contains:
 *   - PORTAL_LABEL: portal id -> display label
 *   - PORTAL_NAV:   portal id -> { title, sections: [...] }
 *   - sectionContainsModule, sectionFlatItems, findModuleLabel, formatSectionLabel
 *
 * IMPORTANT: `findModuleLabel` is RE-EXPORTED by `PortalShell.jsx` for backward
 * compatibility (it is referenced via `import { findModuleLabel } from '../erp/PortalShell'`
 * in legacy code). Do not rename.
 *
 * IA v2 (Round-2 redesign — 2026-07-05):
 *   - Prinsip: MECE (tak ada section beranggota 1), functional cohesion (1 section = 1 flow),
 *     information scent (label = prediktor isi), Miller's Law (≤ ~7 item/section).
 *   - Badge dekoratif (RESMI/HUB/BARU/AI/BETA/VENDOR/Phase) DIHAPUS — noise & cepat basi.
 *   - Item `isHeader` dekoratif DIHAPUS (grouping ditangani section/group).
 *   - Label = frasa benda, Bahasa Indonesia, akronim industri dipertahankan (PO/AR/AP/GRN/HPP/COA/GL/KPI/SOP).
 *   - TIDAK ADA moduleId dihapus (deep-link lama aman via moduleRegistry.js) — hanya di-reorder/rename/merge.
 *   - Kontrak divalidasi gate: scripts/guardrails/check_nav_map.py (INV-NAV-01).
 *
 * IA v2.1 (Pilot konsolidasi + normalisasi nama — 2026-07-06):
 *   - PILOT: Portal PRODUKSI (35→22 pintu) & KEUANGAN (35→25 pintu). Fitur tidak dihapus —
 *     modul digabung jadi TAB dalam Hub (pola hubs/HubTabs.jsx). moduleId lama tetap di registry.
 *   - Hub baru: prod-analytics-hub, prod-monitoring-hub, prod-master-process-hub,
 *     prod-master-product-hub, fin-reports-hub, fin-accounting-master-hub.
 *   - Aturan nama (disetujui owner): akronim DIPERTAHANKAN, TANPA tanda kurung, maksimal 2 kata,
 *     ganti istilah tidak lumrah (PO 360°/3-Way Match/Control Tower/Smart Import/AR Bridge, dst).
 *   - Diverifikasi: check_nav_map.py HIJAU + testing_agent_v3 iter_62 (6/6 hub, 29/29 tab, deep-link 4/4).
 *   - ROLLOUT PENUH (2026-07-06, iter_63): pola diterapkan ke 10 portal sisa. Total 213→176 pintu (−37),
 *     12 hub total. Hub tambahan: mgmt-access-hub, mgmt-system-hub, hr-payroll-hub, hr-shift-hub,
 *     hr-leave-hub, marketing-kol-hub. Nama: 0 tanda kurung, semua ≤2 kata (kecuali 'Onboarding' & akronim).
 */

import {
  // Dashboards
  LayoutDashboard, Gauge, LineChart, Warehouse, UserCog,
  // Management / Admin
  TrendingUp, FileSpreadsheet, Shirt, Users,
  KeyRound, History, Building2, FileCog, BookOpen, UserPlus, GraduationCap, Palette,
  // Production operational
  LayoutGrid, ClipboardList, ClipboardSignature, Boxes,
  Hammer, Activity, Siren, AlertTriangle, Truck, Tv2, Zap,
  ClipboardPen, Package, CalendarDays,
  // Production process stages
  Link2, Scissors, ClipboardCheck, Droplets, PackageOpen, RotateCcw, Paintbrush,
  // Production master
  Workflow, Timer, Wrench, Factory, HardHat, Ruler, BookMarked,
  // Warehouse
  Archive, PackageMinus, PackagePlus, ArrowRightLeft, MapPin, Sparkles, Lock, Award, Send,
  // Finance — Accounting Core
  FolderTree, BookCheck, Scale, Book, CalendarRange, Settings2,
  FileText, Hourglass, Wallet,
  // Finance — Operasional (Session #11.17: Files/CreditCard/FilePlus removed — unused after legacy finance cleanup)
  ReceiptText, Landmark, Receipt, PieChart, Calculator, HandCoins,
  Banknote, BarChart3, Shield, ShieldAlert, ShieldCheck,
  // HR
  Clock, Contact, Calendar, Briefcase,
  // AI & Self
  Brain, Target, UserCircle, CheckSquare, Settings,
  // New portals (Maklon + Toko)
  Star, MessageSquare, ShoppingCart, Bell, Store, Barcode,
  // Phase 5 — Catalog + Marketing (Week 4-7)
  Layers, ShoppingBag, AlertCircle, HeartPulse, Video,
  // Phase 3 Week 8-10 — Content Calendar, Discounts, Product Launch
  Tag, Rocket,
  // Phase 3 Week 13 — Fitur Internal
  ThumbsUp, PackageSearch,
  // Session 12 — AI Content Tools & KOL Leaderboard
  Trophy, Image as ImageIcon,
  // Session 15 — HR AI & Portal Saya Extensions
  FileSearch, TrendingDown, Lightbulb, FileText as FileTextIcon, MessageSquare as MessageSquareIcon,
  // Session 26 — Portal RnD icons
  FlaskConical, Beaker,
  // Session 28 — LiveHost Management icon
  Radio,
  // Session 29 (Phase 26) — HR Approval Inbox icon
  Inbox,
  // Employee Expense Management (EEM)
  CreditCard, Plane, Database,
  // Penomoran Dokumen & SKU
  Hash,
} from 'lucide-react';

// Portal labels shown as badge next to brand (top-left). Click brand to go back to selector.
export const PORTAL_LABEL = {
  management: 'Manajemen',
  sysadmin:    'Administrasi Sistem',
  production:  'Produksi',
  cutting:     'Cutting',
  warehouse:   'Gudang',
  procurement: 'Pengadaan',
  accessories: 'Aksesoris',
  finance:     'Keuangan',
  hr:          'SDM / HRIS',
  maklon:      'Maklon',
  toko:        'Marketing',
  rnd:         'RnD & Desain',
  self:        'Portal Saya',
  collaboration: 'Portal Kolaborasi',
  assets:      'Manajemen Aset',
};

// ── CV. Dewi Aditya · Portal-specific navigation (IA v2) ─────────────────
// Rules:
//   - Bahasa Indonesia untuk label menu (istilah teknis/akronim industri dipertahankan).
//   - Setiap ikon UNIK per portal agar mudah dibedakan (UX audit).
//   - Tidak ada moduleId duplikat DALAM satu portal (lintas-portal boleh — shortcut).
//   - Sections mendukung dua mode:
//       { items: [...] }  — list datar (default)
//       { groups: [{label, items}, ...] }  — dikelompokkan dengan sub-header di sidebar
export const PORTAL_NAV = {
  management: {
    title: 'Manajemen',
    sections: [
      {
        label: 'RINGKASAN EKSEKUTIF',
        items: [
          { id: 'management-dashboard',  label: 'Dashboard Eksekutif', icon: LayoutDashboard },
          { id: 'mgmt-overview',         label: 'Ringkasan Bisnis',    icon: TrendingUp },
          { id: 'reports-hub',           label: 'Pusat Laporan',       icon: FileSpreadsheet },
          { id: 'phase7-reports',        label: 'Laporan Maklon',      icon: BarChart3 },
          { id: 'mgmt-reports',          label: 'Laporan Umum',        icon: FileSpreadsheet },
          { id: 'rnd-dashboard',         label: 'Ringkasan RnD',       icon: FlaskConical },
        ],
      },
      {
        label: 'STRATEGI & APPROVAL',
        items: [
          { id: 'unified-approval-hub',  label: 'Pusat Approval',  icon: Layers },
          { id: 'mgmt-marketing-cycle',  label: 'Siklus Marketing', icon: Target },
          { id: 'mgmt-marketing-change-log', label: 'Jejak Marketing', icon: History },
          { id: 'mgmt-okr',              label: 'OKR Tracker',     icon: Target },
          { id: 'mgmt-tools',            label: 'Digest Mingguan', icon: BarChart3 },
          { id: 'ai-usage-monitor',      label: 'Monitor AI',      icon: Activity },
        ],
      },
    ],
  },

  // ── PORTAL ADMINISTRASI SISTEM ─────────────────────────────────────────────
  // IA v4 (FASE IA-2, keputusan owner): section "ADMINISTRASI SISTEM" DILEPAS dari
  // Portal Manajemen. Alasan: Portal Manajemen = ruang EKSEKUTIF (angka bisnis,
  // strategi, approval); kontrol akses / konfigurasi / backup adalah pekerjaan IT
  // yang beda audiens, beda frekuensi pakai, dan beda risiko. Mencampurnya membuat
  // eksekutif harus melewati menu berbahaya, dan admin IT harus menembus dashboard.
  // Akses dibatasi super_admin + admin (portalAccess.js & backend routes/shared.py).
  //   - `mgmt-backup-restore` DINAIKKAN jadi pintu sendiri (dulu id mati: ada di
  //     registry, tidak ada di menu manapun) dan tab "Backup" DIBUANG dari
  //     ManagementSystemHub supaya tidak jadi satu isi dua pintu (guard NAV-DUPTAB).
  sysadmin: {
    title: 'Administrasi Sistem',
    sections: [
      {
        label: 'AKSES & AUDIT',
        items: [
          { id: 'mgmt-access-hub', label: 'Kontrol Akses', icon: Shield },
          { id: 'sys-rbac-audit', label: 'Audit Approval & Notifikasi', icon: ShieldCheck },
          { id: 'mgmt-activity',   label: 'Log Aktivitas', icon: History },
          { id: 'sys-notif-config', label: 'Aturan Notifikasi', icon: Bell },
        ],
      },
      {
        label: 'SISTEM & DATA',
        items: [
          { id: 'mgmt-system-hub',      label: 'Pengaturan Sistem',  icon: Database },
          // Sesi #20 — pemilik bisa mengukur sendiri kesehatan tautan antar tabel
          // (dulu hanya bisa lewat skrip forensik di komputer pengembang).
          { id: 'sync-audit',           label: 'Sinkronisasi Data',  icon: ShieldCheck },
          { id: 'mgmt-backup-restore',  label: 'Backup Data',        icon: Archive },
          { id: 'sys-doc-numbering',    label: 'Penomoran Dokumen',  icon: Hash },
          { id: 'maklon-config',        label: 'Konfigurasi Maklon', icon: Settings2 },
          { id: 'maklon-notifications', label: 'Notifikasi Maklon',  icon: Bell },
          { id: 'mgmt-help',            label: 'Panduan Sistem',     icon: BookOpen },
        ],
      },
    ],
  },

  // ── PORTAL PRODUKSI ────────────────────────────────────────────────────────
  // IA v3 (FASE IA-1, 2026-07-26) — keputusan owner: Portal Produksi & Maklon punya
  // ALUR YANG SAMA (dua-duanya dilempar ke CMT). Bedanya hanya: DA tidak mengirim ke
  // buyer eksternal karena buyer-nya DA sendiri ⇒ langkah itu = SERAH TERIMA FG ke
  // inventory DA. Maka struktur + nama menu DI-MIRROR dari Portal Maklon, kata
  // "Maklon" → "Internal", supaya user tidak perlu belajar dua peta menu.
  //   - datar 2 tingkat (TANPA `groups`) seperti Maklon — dulu Produksi 3 tingkat
  //     dengan 12 pintu menumpuk di satu section.
  //   - DEPRECATED dari menu (moduleId TETAP di registry ⇒ deep-link lama aman):
  //       prod-progress        "Input Progress"  — progres masuk dari CMT/Portal Vendor
  //       prod-shift-handover  "Operan Shift"    — tidak relevan lagi
  //       prod-material-returns "Retur Material" — duplikasi (material diurus di Kirim Material CMT)
  //       hr-ai-hub            "AI Actions"      — isinya hub AI SDM, bukan produksi
  //   - Data internal & maklon DIPISAH di modul yang dipakai bersama
  //     (business_type=internal): Production Jobs, Tracking Produksi, Laporan Variance,
  //     Kirim Material CMT, Serah Terima FG, Tutup PO, Invoice.
  //   Rincian & bukti: docs/PROPOSAL_IA_PRODUKSI.md
  production: {
    title: 'Produksi',
    sections: [
      {
        label: 'MASTER DATA',
        items: [
          { id: 'prod-master-product-hub', label: 'Master Produk', icon: Shirt },
          { id: 'prod-master-process-hub', label: 'Master Proses', icon: Workflow },
          { id: 'vendor-admin',            label: 'Vendor CMT',    icon: Building2 },
          // Ditaruh PERSIS di sebelah master "Vendor CMT" dan di section PERTAMA
          // (yang tampil apa adanya saat portal dibuka), sama seperti di Portal
          // Maklon. Alasan: sidebar hanya menampilkan pintu SECTION AKTIF, jadi
          // saat pintu ini duduk di section kedua ia tidak terlihat sampai orang
          // menebak harus mengklik pil section dulu — temuan uji 2026-08-08.
          // Kewenangannya LEBIH SEMPIT daripada portalnya (keputusan owner 2b):
          // mengisi atas nama vendor CMT berdampak langsung ke TAGIHAN CMT.
          // Daftar role WAJIB sama dengan backend core/cmt_override.OVERRIDE_ROLES.
          { id: 'cmt-override-portal',     label: 'Input Vendor CMT', icon: UserCog,
            roles: ['admin', 'superadmin', 'admin_produksi', 'supervisor_produksi', 'ppic'] },
        ],
      },
      {
        label: 'PRODUKSI INTERNAL',
        items: [
          { id: 'prod-pos-internal',      label: 'PO Internal',         icon: ClipboardSignature },
          { id: 'prod-shipments-vendor',  label: 'Kirim Material CMT',  icon: Scissors },
          // FASE H-2 (2026-08-16, keputusan owner): pembuat Pengeluaran Material =
          // admin gudang DAN supervisor produksi. Supervisor produksi tidak punya
          // akses Portal Gudang (PORTAL_ACCESS), jadi tanpa pintu di sini
          // kewenangan barunya tidak bisa dipakai dari layar mana pun. Duplikat
          // LINTAS-portal memang diizinkan aturan IA (shortcut yang disengaja) —
          // isinya modul yang SAMA, bukan salinan kedua.
          { id: 'wh-material-issue',      label: 'Pengeluaran Material', icon: PackageMinus },
          { id: 'da-cmt-receive',         label: 'Terima FG dari CMT',  icon: Truck },
          { id: 'cmt-permak',             label: 'Permak / Perbaikan',  icon: Wrench },
          { id: 'prod-shipments-buyer',   label: 'Serah Terima FG',     icon: PackageOpen },
          { id: 'po-closure',             label: 'Tutup PO',            icon: Lock },
        ],
      },
      {
        label: 'MONITORING PROGRESS',
        items: [
          { id: 'production-dashboard', label: 'Dashboard Produksi', icon: Gauge },
          { id: 'prod-control-tower',   label: 'Pusat Kendali',      icon: Factory },
          { id: 'prod-monitoring',      label: 'Tracking Produksi',  icon: Activity },
          { id: 'prod-work-orders',     label: 'Production Jobs',    icon: Boxes },
          { id: 'prod-variance',        label: 'Laporan Variance',   icon: Target },
        ],
      },
      {
        label: 'KEUANGAN & ANALITIK',
        items: [
          { id: 'prod-cmt-billing',            label: 'Invoice',            icon: Banknote },
          // sesi #34 — pintu input biaya jahit per SKU/pcs di SPK (dulu selalu 0
          // untuk SPK internal) + viewer HPP batch FIFO.
          { id: 'prod-sewing-cost',            label: 'Biaya Jahit',        icon: Scissors },
          { id: 'fin-hpp',                     label: 'HPP Produksi',       icon: Calculator },
          { id: 'fin-hpp-produk',              label: 'HPP per Potong',     icon: Calculator },
          { id: 'prod-material-requirements',  label: 'Kebutuhan Material', icon: ClipboardPen },
          { id: 'prod-analytics-hub',          label: 'Analitik Produksi',  icon: BarChart3 },
          { id: 'prod-ai-insights',            label: 'Estimasi AI',        icon: Sparkles },
          { id: 'prod-predictive-maintenance', label: 'Perawatan Mesin',    icon: Wrench },
        ],
      },
    ],
  },

  // ── PORTAL CUTTING ─────────────────────────────────────────────────────────
  // FASE IA-4 (permintaan owner): portal baru. Cutting = mengubah ROLL KAIN
  // menjadi KAIN POLA (potongan). Potongan tetap berstatus MATERIAL — dia yang
  // jadi BOM job produksi internal dan dikirim ke CMT. Karena itu portal ini
  // menempel erat ke Gudang: input diambil dari master material + stok gudang,
  // output ditulis balik sebagai item master + stok gudang (SSOT sama).
  cutting: {
    title: 'Cutting',
    sections: [
      {
        label: 'CUTTING',
        items: [
          { id: 'cutting-dashboard', label: 'Dashboard Cutting', icon: Gauge },
          { id: 'cutting-orders',    label: 'Order Cutting',     icon: Scissors },
          { id: 'cutting-panels',    label: 'Master Potongan',   icon: PackageOpen },
        ],
      },
    ],
  },

  // ── PORTAL PENGADAAN ───────────────────────────────────────────────────────
  // 2026-08-06 (permintaan owner): procurement DILEPAS dari Portal Gudang,
  // Keuangan, dan Aksesoris menjadi portal sendiri. Alasan yang terbukti dari
  // kode, bukan asumsi:
  //   · Pembelian tersebar di 3 portal (Gudang: PO + Penilaian Supplier;
  //     Keuangan: Permintaan Pengadaan + Rekonsiliasi PO; Aksesoris: Purchase
  //     Request) sehingga satu pekerjaan (beli barang) memaksa pindah portal.
  //   · Tidak ada Master Supplier: `rahaza_po.py` menerima `vendor_name` TEKS
  //     BEBAS ⇒ penilaian supplier terpecah oleh perbedaan ejaan.
  //   · PO/PR belum memakai SSOT satuan (`core/uom.py`) padahal penerimaan &
  //     opname sudah ⇒ selisih qty/nilai persediaan.
  // Semua itu diperbaiki bersama portal ini. Pintu lama TETAP resolve
  // (App.js LEGACY_MODULE_TO_PORTAL) supaya bookmark/notifikasi tidak mati.
  procurement: {
    title: 'Pengadaan',
    sections: [
      {
        label: 'RINGKASAN & MASTER',
        items: [
          { id: 'proc-dashboard', label: 'Dashboard Pengadaan', icon: LayoutDashboard },
          { id: 'proc-suppliers', label: 'Master Supplier',      icon: Building2 },
          { id: 'proc-scorecard', label: 'Penilaian Supplier',   icon: Award },
          { id: 'proc-analytics', label: 'Analisis Belanja',     icon: BarChart3 },
        ],
      },
      {
        label: 'PERMINTAAN & PESANAN',
        items: [
          // SESI #33 — pintu yang sama dengan portal Gudang (shortcut): usul beli
          // mingguan dari ambang stok, sekali klik menjadi PR di layar berikutnya.
          { id: 'wh-shopping-list',     label: 'Belanja Mingguan',     icon: PackagePlus },
          { id: 'proc-requests',        label: 'Permintaan Pengadaan', icon: ShoppingCart },
          { id: 'proc-purchase-orders', label: 'Purchase Order',       icon: FileText },
          { id: 'proc-accessory-pr',    label: 'Request Aksesoris',    icon: PackageSearch },
        ],
      },
      {
        label: 'REKONSILIASI & FAKTUR',
        items: [
          { id: 'proc-3way-match',  label: 'Rekonsiliasi PO', icon: Scale },
          { id: 'proc-ap-invoices', label: 'Faktur Supplier', icon: ReceiptText },
        ],
      },
    ],
  },

  warehouse: {
    title: 'Gudang',
    sections: [
      {
        label: 'INVENTORI & STOK',
        items: [
          { id: 'warehouse-dashboard', label: 'Dashboard Gudang',   icon: Warehouse },
          { id: 'wh-master',           label: 'Master Item',        icon: Boxes },
          { id: 'wms-stock-hub',       label: 'Stok & Akurasi',     icon: Archive },
          { id: 'warehouse-smart',     label: 'Alert & Reorder',    icon: AlertTriangle },
          // SESI #33 — dua pintu baru. 'Belanja Mingguan' menjawab "minggu ini
          // beli apa?" (dari ambang stok → PR Pengadaan), 'Riwayat Harga'
          // menjawab "kenapa HPP saya berubah?" (dari pembelian & hasil cutting).
          { id: 'wh-shopping-list',    label: 'Belanja Mingguan',   icon: ShoppingCart },
          { id: 'wh-cost-history',     label: 'Riwayat Harga',      icon: History },
        ],
      },
      {
        // 2026-08-06: `wh-purchase-orders` (Purchase Order) & `wh-supplier-scorecard`
        // (Penilaian Supplier) DIPINDAH ke Portal Pengadaan — keduanya pekerjaan
        // PEMBELIAN, bukan pekerjaan gudang. Gudang tetap memegang penerimaan
        // fisik, penyimpanan, dan karantina QC.
        //
        // FASE H-9 (2026-08-16): 'Roll Kain' DIPINDAH ke sini dari section alat.
        // Alasan: roll kain LAHIR dari penerimaan kain dan MATI di Cutting — dia
        // bagian rantai inbound, bukan "alat". (Catatan jujur: penerimaan kain
        // BELUM otomatis membuat/mengurangi roll — itu H-5, masih backlog. Yang
        // dipindah sekarang baru tempat pintunya supaya urutan kerjanya benar.)
        label: 'INBOUND — PENERIMAAN',
        items: [
          { id: 'wh-receiving',          label: 'Penerimaan Barang', icon: PackagePlus },
          { id: 'wms-fabric-rolls',      label: 'Roll Kain',         icon: Package },
          { id: 'wh-putaway',            label: 'Penyimpanan',       icon: ArrowRightLeft },
          { id: 'wh-quarantine',         label: 'Karantina QC',      icon: ShieldAlert },
        ],
      },
      {
        // IA v4: 'Pengeluaran Material' DIPINDAH ke sini dari "INVENTORI & STOK".
        // Alasan (terbukti dari kode, bukan asumsi): rahaza_material_issues adalah
        // arus KELUAR gudang menuju PRODUKSI — dokumennya dibuat otomatis dari BOM
        // job produksi internal (production_internal_adapter.py `draft-from-job`),
        // lalu approve → potong stok + posting jurnal (rahaza_posting.post_inventory_issue).
        // Jadi tempatnya bersama outbound lain, bukan di laci "stok".
        //
        // FASE H-4 (2026-08-16): pintu 'Kirim CMT' (`wms-cmt-dispatches`) DILEPAS
        // dari sidebar Gudang atas izin owner. Diukur sebelum dilepas:
        // `wh_cmt_dispatches` = 0 dokumen dan pekerjaan nyatanya sudah berjalan di
        // Portal Produksi/Maklon → 'Kirim Material CMT' (`prod-shipments-vendor`,
        // koleksi `vendor_shipments`), yang sejak Fase H-1 juga menerbitkan
        // Pengeluaran Material + memotong stok. Dua pintu untuk satu pekerjaan
        // membuat orang mengisi di layar yang stoknya tidak pernah bergerak.
        // moduleId-nya TIDAK dihapus dari moduleRegistry ⇒ deep-link lama tetap hidup.
        label: 'OUTBOUND — PENGIRIMAN',
        items: [
          { id: 'wh-material-issue',  label: 'Pengeluaran Material', icon: PackageMinus },
          { id: 'fulfillment',        label: 'Fulfillment',   icon: Send },
          // Sesi #20 — gudang butuh pintu yang sama: kalau antrean Fulfillment
          // menyebut "belum tertaut master", inilah tempat memperbaikinya.
          { id: 'sku-bridge',         label: 'Jembatan SKU',  icon: Link2 },
          { id: 'wh-picklist',        label: 'Pick List',     icon: ClipboardList },
          { id: 'wms-delivery-notes', label: 'Surat Jalan',   icon: FileText },
          { id: 'wh-returns',         label: 'Retur Fisik',   icon: RotateCcw },
        ],
      },
      {
        // FASE H-3 (2026-08-16): pintu BARU 'Buat Barcode'. Endpoint label bahan
        // (`/api/wms/materials/labels/batch-pdf`) & barang jadi
        // (`/api/wms/fg/labels/batch-pdf`) sudah ada berbulan-bulan dengan NOL
        // pemanggil UI ⇒ barcode gudang praktis tidak bisa dicetak siapa pun.
        //
        // FASE H-4 (2026-08-16): pintu 'Scan Gudang' (`wh-scan`) DILEPAS atas izin
        // owner. Diukur: layar itu membaca antrean `wh_pending_movements` = 0
        // dokumen, dan endpoint pengisi antreannya
        // (`/api/wms/pending/create-from-production|create-from-shipment`) TIDAK
        // punya satu pun pemanggil di seluruh repo ⇒ layar permanen kosong.
        // Scan tetap hidup MELEKAT pada prosesnya (Penerimaan, Penyimpanan,
        // Opname, Pengeluaran Material) — bukan sebagai menu tersendiri.
        label: 'ALAT & AKSESORIS',
        items: [
          { id: 'wh-barcode',                   label: 'Buat Barcode',      icon: Barcode },
          { id: 'wh-structure',                 label: 'Struktur Gudang',   icon: Building2 },
          { id: 'wh-units',                     label: 'Satuan & Konversi', icon: Scale },
          { id: 'wh-audit',                     label: 'Audit Trail',       icon: History },
          // 2026-08-19 (sesi #28, permintaan pemilik) — 'Operasi Aksesoris'
          // (`wh-accessory-ops`) dan 'Inbox Aksesoris'
          // (`warehouse-accessory-requests`) DIHAPUS dari Portal Gudang: keduanya
          // hanya melempar pemakai ke Portal Aksesoris, jadi ia menambah dua pintu
          // yang isinya bukan milik portal ini. Modulnya TIDAK dihapus dari
          // registry — pintu aslinya tetap ada di Portal Aksesoris.
        ],
      },
    ],
  },

  // ── PORTAL AKSESORIS ───────────────────────────────────────────────────────
  // IA v4 (FASE IA-2, keputusan owner): 3 section (Dashboard&Laporan, Inventori,
  // Request&Pengadaan) DIGABUNG jadi SATU section. Alasan: portalnya kecil (7 pintu)
  // dan 5 di antaranya sebenarnya hanya TAB di dalam AccessoryModule — memecahnya
  // jadi 3 laci membuat user memindai 3 kali untuk 7 pilihan. Tidak ada pintu
  // dihapus; fungsionalitas identik.
  accessories: {
    title: 'Aksesoris',
    sections: [
      {
        label: 'AKSESORIS',
        items: [
          { id: 'accessories-dashboard',        label: 'Dashboard',        icon: LayoutDashboard },
          { id: 'accessories-master-stock',     label: 'Master Aksesoris', icon: Package },
          { id: 'accessories-opname',           label: 'Stok Opname',      icon: ClipboardCheck },
          { id: 'accessories-internal-request', label: 'Request Internal', icon: ArrowRightLeft },
          { id: 'accessories-inbox',            label: 'Inbox Approval',   icon: Inbox },
          // ACC-3: "Peminjaman" (dulu id 'accessories-loans') DIPINDAH ke Manajemen Aset.
          // Peminjaman = domain ASET (unit fisik yang harus kembali), BUKAN konsumsi
          // aksesoris. Id lama tetap resolve via App.js LEGACY_MODULE_TO_PORTAL.
          // 2026-08-06: 'accessories-purchase' (Purchase Request) DIPINDAH ke
          // Portal Pengadaan (`proc-accessory-pr`) — pembelian = domain pengadaan.
          { id: 'accessories-reports',          label: 'Laporan',          icon: BarChart3 },
        ],
      },
    ],
  },

  // ── PORTAL KEUANGAN ────────────────────────────────────────────────────────
  // IA v4 (FASE IA-2). Masalah IA lama (diakui owner: "paling berantakan"):
  //   · "PIUTANG AR" cuma 2 pintu dan salah satunya (Channel GL) sebenarnya
  //     pemetaan akun, bukan piutang.
  //   · "KAS & PEMBAYARAN" menumpuk 8 pintu campur: kas, bank, prediksi AI,
  //     pengeluaran, kasbon, settlement — tiga urusan berbeda dalam satu laci.
  //   · "LAPORAN & BIAYA" mencampur LAPORAN (output) dengan MASTER/PERENCANAAN
  //     (pusat biaya, HPP, anggaran, aset tetap) — beda arah kerja.
  // Prinsip baru: urutkan menurut SIKLUS UANG, bukan menurut nama modul —
  //   Ringkasan → Piutang (uang masuk) → Hutang/Pengadaan (uang keluar terikat) →
  //   Kas/Bank & Biaya (eksekusi uang) → Akuntansi (pencatatan) → Perencanaan.
  // TIDAK ADA pintu dihapus/ditambah (24 pintu tetap 24) — murni relokasi menu.
  // 2026-09-02 — IA v3 Keuangan (keputusan pemilik): section lama "PENJUALAN &
  // PIUTANG" (2 pintu, Channel GL = peta akun, bukan piutang) dan "KAS, BANK &
  // BIAYA" (8 pintu campur: bank, pencairan, klaim, kasbon, dinas) dibubarkan.
  // Prinsip: satu section = satu arah uang. Uang MASUK (penjualan/penerimaan),
  // uang di TANGAN (kas & bank), uang KELUAR ke orang (pengeluaran & karyawan),
  // PENCATATAN (akuntansi), PERENCANAAN (anggaran/biaya/aset), OUTPUT (laporan).
  // Tidak ada pintu dihapus; hanya relokasi + 4 label diperjelas.
  finance: {
    title: 'Keuangan',
    sections: [
      {
        label: 'RINGKASAN & LAPORAN',
        items: [
          { id: 'finance-dashboard',    label: 'Dashboard Keuangan', icon: LineChart },
          { id: 'fin-recap',            label: 'Rekap Keuangan',     icon: BarChart3 },
          { id: 'fin-reports-hub',      label: 'Laporan Keuangan',   icon: FileSpreadsheet },
          { id: 'fin-executive-report', label: 'Laporan Eksekutif',  icon: Award },
        ],
      },
      {
        label: 'PENJUALAN & PENERIMAAN',
        items: [
          { id: 'fin-marketplace-settlement', label: 'Pencairan Marketplace', icon: Banknote },
          { id: 'fin-ar-360',                 label: 'Aging Piutang',         icon: Scale },
          { id: 'fin-channel-gl',             label: 'Peta Akun Channel',     icon: Store },
        ],
      },
      {
        label: 'KAS & BANK',
        items: [
          { id: 'fin-cash',          label: 'Kas & Bank',        icon: Landmark },
          { id: 'fin-petty-cash',    label: 'Kas Kecil',         icon: Wallet },
          { id: 'fin-bank-transfer', label: 'Transfer Bank',     icon: ArrowRightLeft },
          { id: 'fin-bank-recon',    label: 'Rekonsiliasi Bank', icon: Hourglass },
          { id: 'fin-ai-cashflow',   label: 'Prediksi Kas',      icon: Brain },
        ],
      },
      {
        label: 'PENGELUARAN & KARYAWAN',
        items: [
          { id: 'fin-expenses',         label: 'Pengeluaran & Klaim',          icon: Receipt },
          { id: 'fin-kasbon',           label: 'Kasbon & Pinjaman',            icon: HandCoins },
          { id: 'fin-settlement-queue', label: 'Penyelesaian Perjalanan Dinas', icon: FileText },
        ],
      },
      {
        label: 'AKUNTANSI',
        items: [
          { id: 'fin-journal-hub',           label: 'Jurnal',                       icon: BookCheck },
          { id: 'fin-acctg-adjust-hub',      label: 'Penyesuaian Akhir Periode',    icon: Calculator },
          { id: 'fin-approval',              label: 'Persetujuan Perubahan Invoice', icon: ShieldAlert },
          { id: 'fin-accounting-master-hub', label: 'Master Akuntansi',             icon: FolderTree },
        ],
      },
      {
        label: 'ANGGARAN, BIAYA & ASET',
        items: [
          { id: 'fin-budget',       label: 'Anggaran',       icon: PieChart },
          { id: 'fin-cost-centers', label: 'Pusat Biaya',    icon: Book },
          { id: 'fin-hpp',          label: 'HPP',            icon: Calculator },
          { id: 'fin-hpp-produk',   label: 'HPP per Potong', icon: Calculator },
          { id: 'fin-fixed-assets', label: 'Aset Tetap',     icon: Package },
        ],
      },
    ],
  },

  // ── PORTAL SDM / HRIS ──────────────────────────────────────────────────────
  // IA v4 (FASE IA-2, keputusan owner): 5 section lama (Dashboard&Approval,
  // Karyawan&Organisasi, Rekrutmen&Pengembangan, Kehadiran-Shift-Cuti,
  // Penggajian&Klaim) DIRINGKAS jadi 3 section utama sesuai permintaan owner:
  //   1. MANAJEMEN KARYAWAN  — semua yang menempel pada ORANG-nya (data diri,
  //      absen, cuti, gaji, kasbon, klaim, aset yang dipegang).
  //   2. MANAJEMEN ORGANISASI — semua yang menempel pada STRUKTUR & PENGISIANNYA
  //      (bagan organisasi, shift, rekrutmen, onboarding, pengumuman, pengaturan).
  //   3. ANALITIK & LAPORAN  — dashboard, laporan, kinerja, pembelajaran, AI,
  //      dan inbox/approval (bersifat pengawasan lintas karyawan).
  // TIDAK ADA pintu dihapus/ditambah/diganti komponen — murni relokasi menu
  // (24 pintu tetap 24). Semua id lama tetap resolve (deep-link aman).
  hr: {
    title: 'SDM',
    sections: [
      {
        label: 'MANAJEMEN KARYAWAN',
        items: [
          { id: 'hr-employees',           label: 'Data Karyawan',    icon: Users },
          { id: 'hr-attendance-hub',      label: 'Absensi',          icon: Clock },
          { id: 'hr-attendance-sessions', label: 'Istirahat & Izin', icon: Timer },
          { id: 'hr-leave-hub',           label: 'Cuti & Lembur',    icon: CalendarDays },
          { id: 'hr-payroll-hub',         label: 'Penggajian',       icon: Banknote },
          { id: 'hr-kasbon',              label: 'Kasbon',           icon: Wallet },
          { id: 'hr-expense-hub',         label: 'Klaim Dinas',      icon: Plane },
          { id: 'hr-assets',              label: 'Aset Karyawan',    icon: Package },
        ],
      },
      {
        label: 'MANAJEMEN ORGANISASI',
        items: [
          { id: 'hr-org-chart',        label: 'Struktur Organisasi', icon: LayoutGrid },
          { id: 'hr-shift-hub',        label: 'Shift',               icon: Calendar },
          { id: 'hr-recruitment',      label: 'Rekrutmen & ATS',     icon: FileText },
          { id: 'hr-resume-screening', label: 'Screening CV',        icon: FileSearch },
          { id: 'hr-onboarding',       label: 'Onboarding',          icon: ClipboardCheck },
          { id: 'hr-job-board',        label: 'Job Board',           icon: Briefcase },
          { id: 'hr-announcements',    label: 'Papan Pengumuman',    icon: Bell },
          { id: 'hr-admin',            label: 'Pengaturan SDM',      icon: Settings },
        ],
      },
      {
        label: 'ANALITIK & LAPORAN',
        items: [
          { id: 'hr-dashboard',         label: 'Dashboard SDM',       icon: UserCog },
          { id: 'hr-reports',           label: 'Laporan SDM',         icon: BarChart3 },
          { id: 'hr-performance-hub',   label: 'Manajemen Kinerja',   icon: Target },
          { id: 'hr-lms',               label: 'Pembelajaran',        icon: GraduationCap },
          { id: 'hr-ai-hub',            label: 'AI SDM',              icon: Brain },
          { id: 'unified-approval-hub', label: 'Pusat Approval',      icon: Layers },
          { id: 'hr-inbox',             label: 'Inbox SDM',           icon: Inbox },
          { id: 'approval-multilevel',  label: 'Approval Bertingkat', icon: CheckSquare },
        ],
      },
    ],
  },

  rnd: {
    title: 'RnD & Desain',
    sections: [
      {
        label: 'DESAIN & SAMPLING',
        items: [
          { id: 'rnd-dashboard',          label: 'Dashboard RnD',   icon: LayoutDashboard },
          { id: 'rnd-design-hub',         label: 'Style & Desain',  icon: Palette },
          // sesi #34 — hasil final RnD sebagai KATALOG (foto, HPP batch, status sync)
          { id: 'rnd-product-viewer',     label: 'Produk Final',    icon: Boxes },
          { id: 'rnd-samples',            label: 'Sample Request',  icon: FlaskConical },
          { id: 'rnd-accessory-requests', label: 'Request Aksesoris', icon: Package },
          { id: 'rnd-materials',          label: 'Riset Material',  icon: Beaker },
        ],
      },
      {
        label: 'COSTING & ANALITIK',
        items: [
          { id: 'rnd-costing-hub',      label: 'Costing & HPP', icon: Calculator },
          { id: 'rnd-analytics',        label: 'RnD Analytics', icon: BarChart3 },
          { id: 'rnd-kreator-requests', label: 'Approval Kreator', icon: Users },
        ],
      },
    ],
  },

  self: {
    title: 'Portal Saya',
    sections: [
      {
        label: 'PROFIL & KEHADIRAN',
        items: [
          { id: 'portal-dashboard',  label: 'Dashboard',    icon: LayoutDashboard },
          { id: 'portal-profile',    label: 'Profil',       icon: UserCircle },
          { id: 'portal-absen',      label: 'Absen Saya',   icon: Clock },
          { id: 'self-dashboard',    label: 'Kehadiran',    icon: Clock },
          { id: 'portal-cuti',       label: 'Cuti & Lembur', icon: Calendar },
          { id: 'portal-notifikasi', label: 'Notifikasi',   icon: Bell },
        ],
      },
      {
        label: 'KOMPENSASI & KINERJA',
        items: [
          { id: 'portal-payslip',       label: 'Slip Gaji',     icon: Banknote },
          { id: 'portal-kasbon',        label: 'Kasbon',        icon: Wallet },
          { id: 'kpi-portal',           label: 'KPI',           icon: Target },
          { id: 'portal-annual-review', label: 'Annual Review', icon: Trophy },
        ],
      },
      {
        label: 'PENGEMBANGAN & DOKUMEN',
        items: [
          { id: 'portal-training',      label: 'Training',     icon: BookOpen },
          { id: 'portal-peer-feedback', label: 'Peer Feedback', icon: MessageSquareIcon },
          { id: 'portal-career-coach',  label: 'Career Coach', icon: Brain },
          { id: 'portal-workspace',     label: 'Ruang Kerja',  icon: Star },
          { id: 'portal-documents',     label: 'Dokumen',      icon: FileTextIcon },
        ],
      },
    ],
  },

  maklon: {
    title: 'Maklon',
    sections: [
      {
        label: 'MASTER DATA',
        items: [
          { id: 'maklon-clients',       label: 'Data Klien',       icon: Users },
          { id: 'maklon-buyer-catalog', label: 'Katalog Buyer',    icon: BookOpen },
          { id: 'vendor-admin',         label: 'Vendor CMT',       icon: Building2 },
          { id: 'cmt-override-portal',  label: 'Input Vendor CMT', icon: UserCog,
            roles: ['admin', 'superadmin', 'admin_produksi', 'supervisor_produksi', 'ppic'] },
        ],
      },
      {
        label: 'PRODUKSI MAKLON',
        items: [
          { id: 'maklon-pos-engine',      label: 'PO Maklon',            icon: ClipboardSignature },
          { id: 'maklon-po-360',          label: 'Detail PO',            icon: Layers },
          { id: 'maklon-samples',         label: 'Kelola Sampel',        icon: ClipboardCheck },
          { id: 'prod-shipments-vendor',  label: 'Kirim Material CMT',   icon: Scissors },
          { id: 'da-cmt-receive',         label: 'Terima FG dari CMT',   icon: Truck },
          { id: 'cmt-permak',             label: 'Permak / Perbaikan',   icon: Wrench },
          { id: 'prod-shipments-buyer',   label: 'Dispatch ke Buyer',    icon: Link2 },
          { id: 'po-closure',             label: 'Tutup PO',             icon: Lock },
        ],
      },
      {
        label: 'MONITORING PROGRESS',
        items: [
          { id: 'maklon-dashboard',     label: 'Dashboard Maklon',   icon: Gauge },
          { id: 'maklon-alur-produksi', label: 'Alur Produksi',      icon: Factory },
          { id: 'cmt-monitor',          label: 'Monitoring CMT',     icon: Siren },
          { id: 'maklon-tracking',      label: 'Tracking Produksi',  icon: Activity },
          // 2026-08-08 — pintu monitoring yang DIKELOMPOKKAN PER VENDOR CMT
          // (engine/ProductionMonitoringModule) sebelumnya HANYA punya pintu di
          // Portal Produksi, dan komponen itu memilih domain dari portalnya:
          // di Produksi = 'internal'. Akibatnya vendor CMT MAKLON tidak pernah
          // terlihat di layar itu — termasuk badge "diinput staf DA" yang justru
          // paling relevan untuk vendor CMT. Pintu ini membukanya untuk domain maklon.
          { id: 'prod-monitoring',      label: 'Tracking Vendor',    icon: TrendingUp },
          { id: 'prod-work-orders',     label: 'Production Jobs',    icon: Boxes },
          // FASE IA-3 (wiring putus): modul & endpoint "Komponen Kurang"
          // (CMTComponentRequestModule + /api/dewi/cmt-component-requests) SUDAH ADA
          // dan dipakai di Excel operasional owner (sheet "KOMPONEN KURANG"), tapi
          // TIDAK punya pintu di menu manapun ⇒ fitur tak terjangkau user.
          { id: 'cmt-component-requests', label: 'Komponen Kurang',  icon: PackageSearch },
          { id: 'prod-variance-report', label: 'Laporan Variance',   icon: Target },
        ],
      },
      {
        label: 'KEUANGAN & ANALITIK',
        items: [
          { id: 'maklon-billing',  label: 'Invoice',     icon: Banknote },
          { id: 'maklon-hpp',      label: 'HPP Jahit',   icon: Target },
          { id: 'maklon-ai-quote', label: 'Estimasi AI', icon: Sparkles },
        ],
      },
    ],
  },

  toko: {
    title: 'Marketing',
    sections: [
      {
        // FASE D (2026-08-16) — pintu Dashboard Marketing AKHIRNYA ada.
        // `toko-dashboard` sudah lama menjadi modul bawaan Portal Marketing
        // (App.js: PORTAL_DEFAULT_MODULE.toko), tetapi TIDAK tercantum di satu pun
        // sidebar ⇒ begitu pemakai membuka menu lain, tidak ada jalan kembali ke
        // dashboardnya selain memuat ulang portal. Itulah keluhan "dashboard
        // marketing hilang dari menu".
        label: 'RINGKASAN & LAPORAN',
        items: [
          { id: 'toko-dashboard',   label: 'Dashboard Marketing', icon: LayoutDashboard },
          { id: 'marketing-reports', label: 'Laporan Marketing',  icon: BarChart3 },
        ],
      },
      {
        label: 'PENJUALAN MULTI-CHANNEL',
        items: [
          { id: 'marketing-accounts',  label: 'Kelola Akun',       icon: Store },
          { id: 'marketing-account-review', label: 'Koreksi Data Toko', icon: ClipboardCheck },
          { id: 'marketing-sales',     label: 'Input Sales',       icon: TrendingUp },
          { id: 'marketing-import',    label: 'Impor Data',        icon: FileSpreadsheet },
          { id: 'marketing-orders',    label: 'Order Terpadu',     icon: ShoppingBag },
          { id: 'marketing-fulfillment', label: 'Monitoring Kirim', icon: Truck },
          { id: 'marketing-catalog',   label: 'Manajemen Katalog', icon: Layers },
          // Sesi #20 — pintu yang menyamakan identitas barang marketing ⇄ gudang.
          // Diletakkan di sini (bukan di laci "pengaturan") karena pekerjaannya
          // melekat pada arus pesanan: SKU yang belum tertaut = pesanan yang tidak
          // bisa dikirim gudang.
          { id: 'sku-bridge',          label: 'Jembatan SKU',      icon: Link2 },
        ],
      },
      {
        // sesi #34 — UANG yang benar-benar cair dari marketplace. Dipisah dari
        // section penjualan karena isinya bukan arus pesanan melainkan arus kas,
        // dan karena section penjualan sudah 8 pintu (batas INV-NAV-01).
        label: 'UANG TOKO: ANGGARAN & PENCAIRAN',
        items: [
          { id: 'marketing-targets',     label: 'Target & Budget', icon: Target },
          { id: 'marketing-settlements', label: 'Pencairan Toko',  icon: Banknote },
        ],
      },
      {
        label: 'KONTEN, KAMPANYE & KREATOR',
        items: [
          { id: 'marketing-content-calendar', label: 'Kalender Konten',   icon: Calendar },
          { id: 'marketing-discounts',        label: 'Kampanye Diskon',   icon: Tag },
          { id: 'marketing-product-launches', label: 'Peluncuran Produk', icon: Rocket },
          { id: 'marketing-kol-hub',          label: 'KOL & Kreator',     icon: Star },
        ],
      },
      {
        label: 'ANALITIK, LIVE & AI',
        items: [
          { id: 'marketing-health',    label: 'Kesehatan Akun',    icon: HeartPulse },
          { id: 'marketing-live-hub',  label: 'Live Selling',      icon: Video },
          { id: 'marketing-ai-hub',    label: 'AI Marketing',      icon: Sparkles },
          { id: 'marketing-scheduler', label: 'Penjadwal Otomasi', icon: Timer },
          { id: 'marketing-change-log', label: 'Jejak Perubahan', icon: History },
        ],
      },
      {
        label: 'AFTER-SALES & PENGATURAN',
        items: [
          { id: 'marketing-after-sales',          label: 'Komplain & Retur', icon: AlertCircle },
          { id: 'marketing-reviews',              label: 'Rating & Ulasan',  icon: ThumbsUp },
          { id: 'marketing-samples',              label: 'Kirim Sample',     icon: PackageSearch },
          { id: 'marketing-task-hub',             label: 'Manajemen Tugas',  icon: ClipboardCheck },
          { id: 'marketing-integration-settings', label: 'Integrasi API',    icon: Settings },
          { id: 'marketing-webhooks',             label: 'Monitor Webhook',  icon: Zap },
          { id: 'maklon-notifications',           label: 'Notifikasi',       icon: Bell },
        ],
      },
    ],
  },

  collaboration: {
    title: 'Portal Kolaborasi',
    sections: [
      {
        label: 'KOLABORASI',
        items: [
          { id: 'collaboration',    label: 'Portal Kolaborasi', icon: MessageSquare },
          { id: 'collab-workspace', label: 'Spreadsheet',       icon: FileText },
        ],
      },
    ],
  },

  // ── PORTAL MANAJEMEN ASET ──────────────────────────────────────────────────
  // IA v4 (FASE IA-2, keputusan owner): sidebar DIHAPUS. Buktinya: keempat pintu
  // lama (asset-dashboard / asset-list / asset-procurement / asset-loans) me-render
  // KOMPONEN YANG SAMA (AssetManagementPortal) dan hanya berbeda `defaultTab` —
  // jadi "navigasi" sidebar sebenarnya cuma memindahkan tab di dalam halaman.
  // Dua lapis navigasi untuk satu halaman = beban kognitif tanpa manfaat.
  //   ⇒ portal ini kini SATU pintu (`asset-management`) dengan `singleDoor: true`.
  //     PortalShell menyembunyikan sidebar + pill section untuk portal ber-flag ini
  //     (dijaga guard NAV-SOLO). Navigasi internal 100% lewat tab modul.
  //   ⇒ id lama TETAP di moduleRegistry (deep-link `#asset-list` dsb. tetap membuka
  //     tab yang benar).
  assets: {
    title: 'Manajemen Aset',
    singleDoor: true,
    sections: [
      {
        label: 'MANAJEMEN ASET',
        items: [
          { id: 'asset-management', label: 'Manajemen Aset', icon: Boxes },
        ],
      },
    ],
  },
};

// ─── Helpers ────────────────────────────────────────────────────────────────

// Helper: apakah section mengandung moduleId (support items & groups)
export function sectionContainsModule(section, moduleId) {
  if (!section) return false;
  if (section.items?.some((i) => i.id === moduleId)) return true;
  if (section.groups?.some((g) => g.items?.some((i) => i.id === moduleId))) return true;
  return false;
}

// Helper: flatten section → list of items (menggabungkan groups)
export function sectionFlatItems(section) {
  if (!section) return [];
  if (section.items?.length) return section.items;
  if (section.groups?.length) return section.groups.flatMap((g) => g.items || []);
  return [];
}

// Helper: cari label menu berdasarkan currentModule (untuk topbar title)
export function findModuleLabel(portal, moduleId) {
  const nav = PORTAL_NAV[portal];
  if (!nav) return moduleId;
  for (const sec of nav.sections) {
    const all = sectionFlatItems(sec);
    const found = all.find((it) => it.id === moduleId);
    if (found) return found.label;
  }
  return moduleId;
}

// ── helper: tampilkan label section lebih enak dibaca (ALL CAPS → Title Case),
// preserve akronim di dalam tanda kurung DAN daftar akronim terkenal ──
const KNOWN_ACRONYMS = new Set([
  'HPP', 'AR', 'AP', 'SOP', 'BOM', 'OEE', 'QC', 'APS', 'KPI', 'ERP', 'TV', 'HR', 'WO',
  'GRN', 'COA', 'GL', 'PR', 'PO', 'AI', 'CMT', 'AQL', 'FPY', 'P2P', 'TB',
]);

export function formatSectionLabel(label) {
  if (!label) return '';
  return label
    .split(' ')
    .map((w) => {
      if (!w) return '';
      // preserve acronyms within parens, e.g. (AR), (AP), (HPP), (F1)
      if (/^\(.+\)$/.test(w)) return w.toUpperCase();
      // preserve known acronyms (case-insensitive match)
      if (KNOWN_ACRONYMS.has(w.toUpperCase())) return w.toUpperCase();
      // everything else → Title Case (first letter upper, rest lower)
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    })
    .join(' ');
}
