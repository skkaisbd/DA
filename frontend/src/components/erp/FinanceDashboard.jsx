import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { motion } from 'framer-motion';
import {
  BarChart3, HandCoins, PieChart, Calculator, BookCheck, Scale, Wallet, FolderTree,
  FileText, FileSpreadsheet, Award, Banknote, Store, Landmark, ArrowRightLeft, Hourglass,
  Brain, Receipt, ShieldAlert, Book, Package,
} from 'lucide-react';

// Akses cepat — grup & urutannya SAMA dengan section sidebar Keuangan (portalNav.js,
// IA v3 2026-09-02) supaya pemakai tidak menemukan dua peta untuk satu portal.
const QUICK_LINKS = [
  { id: 'fin-recap',            label: 'Rekap Keuangan',   desc: 'Ringkasan keuangan & analisis margin.',        icon: BarChart3,      group: 'laporan' },
  { id: 'fin-reports-hub',      label: 'Laporan Keuangan', desc: 'Neraca saldo, buku besar, L/R, neraca, arus kas.', icon: FileSpreadsheet, group: 'laporan' },
  { id: 'fin-executive-report', label: 'Laporan Eksekutif', desc: 'Ringkasan manajemen untuk pemilik.',         icon: Award,          group: 'laporan' },

  { id: 'fin-marketplace-settlement', label: 'Pencairan Marketplace', desc: 'Uang masuk dari Shopee/TikTok & potongannya.', icon: Banknote, group: 'penerimaan' },
  { id: 'fin-ar-360',                 label: 'Aging Piutang',         desc: 'Umur piutang & statement pelanggan.',        icon: Scale,    group: 'penerimaan' },
  { id: 'fin-channel-gl',             label: 'Peta Akun Channel',     desc: 'Akun pendapatan per channel penjualan.',      icon: Store,    group: 'penerimaan' },

  { id: 'fin-cash',          label: 'Kas & Bank',        desc: 'Saldo akun kas/bank & pergerakan.',       icon: Landmark,       group: 'kas' },
  { id: 'fin-petty-cash',    label: 'Kas Kecil',         desc: 'Pengeluaran kecil harian & pengisian.',   icon: Wallet,         group: 'kas' },
  { id: 'fin-bank-transfer', label: 'Transfer Bank',     desc: 'Pindah dana antar rekening.',             icon: ArrowRightLeft, group: 'kas' },
  { id: 'fin-bank-recon',    label: 'Rekonsiliasi Bank', desc: 'Cocokkan mutasi bank dengan buku.',        icon: Hourglass,      group: 'kas' },
  { id: 'fin-ai-cashflow',   label: 'Prediksi Kas',      desc: 'Perkiraan arus kas ke depan.',            icon: Brain,          group: 'kas' },

  { id: 'fin-expenses',         label: 'Pengeluaran & Klaim',          desc: 'Pengeluaran umum & pencairan klaim karyawan.', icon: Receipt,   group: 'pengeluaran' },
  { id: 'fin-kasbon',           label: 'Kasbon & Pinjaman',            desc: 'Kasbon karyawan & cicilannya.',              icon: HandCoins, group: 'pengeluaran' },
  { id: 'fin-settlement-queue', label: 'Penyelesaian Perjalanan Dinas', desc: 'Selesaikan uang muka perjalanan dinas.',     icon: FileText,  group: 'pengeluaran' },

  { id: 'fin-journal-hub',           label: 'Jurnal',                       desc: 'Jurnal umum & daftar jurnal.',              icon: BookCheck,   group: 'akuntansi' },
  { id: 'fin-acctg-adjust-hub',      label: 'Penyesuaian Akhir Periode',    desc: 'Akrual, depresiasi, hapus buku, pelepasan aset.', icon: Calculator, group: 'akuntansi' },
  { id: 'fin-approval',              label: 'Persetujuan Perubahan Invoice', desc: 'Setujui perubahan invoice AR/AP.',          icon: ShieldAlert, group: 'akuntansi' },
  { id: 'fin-accounting-master-hub', label: 'Master Akuntansi',             desc: 'Bagan akun, profil posting, periode.',       icon: FolderTree,  group: 'akuntansi' },

  { id: 'fin-budget',       label: 'Anggaran',       desc: 'Rencana vs realisasi anggaran.',        icon: PieChart,   group: 'perencanaan' },
  { id: 'fin-cost-centers', label: 'Pusat Biaya',    desc: 'Alokasi biaya per pusat biaya.',        icon: Book,       group: 'perencanaan' },
  { id: 'fin-hpp',          label: 'HPP',            desc: 'Harga pokok per Work Order.',           icon: Calculator, group: 'perencanaan' },
  { id: 'fin-hpp-produk',   label: 'HPP per Potong', desc: 'Harga pokok per produk/potong.',        icon: Calculator, group: 'perencanaan' },
  { id: 'fin-fixed-assets', label: 'Aset Tetap',     desc: 'Daftar aset & penyusutannya.',          icon: Package,    group: 'perencanaan' },
];

const GROUP_META = {
  laporan:     { label: 'Ringkasan & Laporan',     desc: 'Output — angka yang dibaca pemilik.' },
  penerimaan:  { label: 'Penjualan & Penerimaan',  desc: 'Uang masuk dari penjualan & pelanggan.' },
  kas:         { label: 'Kas & Bank',              desc: 'Uang di tangan — saldo, transfer, rekonsiliasi.' },
  pengeluaran: { label: 'Pengeluaran & Karyawan',  desc: 'Uang keluar ke karyawan & operasional.' },
  akuntansi:   { label: 'Akuntansi',               desc: 'Pencatatan — jurnal, penyesuaian, master.' },
  perencanaan: { label: 'Anggaran, Biaya & Aset',  desc: 'Perencanaan — anggaran, HPP, aset.' },
};

export default function FinanceDashboard({ onNavigate }) {
  const groups = Object.keys(GROUP_META);

  return (
    <div className="space-y-6" data-testid="finance-dashboard">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Portal Keuangan</h1>
        <p className="text-muted-foreground text-sm mt-1">Diurutkan menurut alur uang: laporan → uang masuk → kas & bank → uang keluar → pencatatan → perencanaan.</p>
      </div>

      <GlassPanel className="p-4 flex items-center gap-3">
        <BarChart3 className="w-5 h-5 text-primary" />
        <div>
          <p className="text-sm font-medium text-foreground">Modul keuangan tersedia</p>
          <p className="text-xs text-muted-foreground">Gunakan navigasi sidebar atau akses cepat di bawah untuk mengakses modul.</p>
        </div>
      </GlassPanel>

      {groups.map((groupId) => {
        const meta = GROUP_META[groupId];
        const items = QUICK_LINKS.filter(l => l.group === groupId);
        return (
          <section key={groupId} aria-labelledby={`fin-group-${groupId}`}>
            <div className="mb-3 flex items-baseline gap-2">
              <h2 id={`fin-group-${groupId}`} className="text-sm font-semibold text-foreground/80 uppercase tracking-wider">{meta.label}</h2>
              <span className="text-xs text-foreground/40">· {meta.desc}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 auto-rows-fr">
              {items.map((link, idx) => {
                const Icon = link.icon;
                return (
                  <motion.div
                    key={link.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: idx * 0.04 }}
                    className="h-full"
                  >
                    <GlassCard
                      className="p-5 h-full min-h-[150px] flex flex-col cursor-pointer group"
                      onClick={() => onNavigate && onNavigate(link.id)}
                      data-testid={`fin-link-${link.id}`}
                    >
                      <div className="w-10 h-10 rounded-xl bg-primary/15 border border-primary/25 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                        <Icon className="w-5 h-5 text-primary" />
                      </div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{link.label}</h3>
                      <p className="text-xs text-muted-foreground leading-relaxed flex-1">{link.desc}</p>
                    </GlassCard>
                  </motion.div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
