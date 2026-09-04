import { ShoppingBag, Users, Star, Package, ChevronRight, AlertTriangle, CheckCircle2, TrendingUp, Zap } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { motion } from 'framer-motion';

const STATS = [
  { label: 'Pesanan Masuk Hari Ini', value: '0', icon: ShoppingBag, accent: 'text-pink-600 dark:text-pink-400',   bg: 'bg-pink-100 dark:bg-pink-500/10',   border: 'border-pink-300 dark:border-pink-400/20' },
  { label: 'KOL / Kreator Aktif',   value: '0', icon: Star,        accent: 'text-amber-700 dark:text-amber-400',  bg: 'bg-amber-100 dark:bg-amber-500/10',  border: 'border-amber-300 dark:border-amber-400/20' },
  { label: 'Sample Dalam Proses',   value: '0', icon: Package,     accent: 'text-blue-600 dark:text-blue-400',   bg: 'bg-blue-100 dark:bg-blue-500/10',   border: 'border-blue-300 dark:border-blue-400/20' },
  { label: 'Return Pending',        value: '0', icon: TrendingUp,  accent: 'text-red-700 dark:text-red-400',    bg: 'bg-red-100 dark:bg-red-500/10',    border: 'border-red-300 dark:border-red-400/20' },
];

const QUICK_ACTIONS = [
  { label: 'Input Pesanan Marketplace',   icon: ShoppingBag,  color: 'text-pink-600 dark:text-pink-400' },
  { label: 'Tambah/Kelola Kreator KOL',  icon: Star,         color: 'text-amber-700 dark:text-amber-400' },
  { label: 'Request Sample ke Kreator',  icon: Package,      color: 'text-blue-600 dark:text-blue-400' },
  { label: 'Setting Flashsale Produk',   icon: Zap,          color: 'text-green-700 dark:text-green-400' },
];

export default function TokoDashboard() {
  return (
    <div className="p-6 space-y-6" data-testid="toko-dashboard">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-pink-100 dark:bg-pink-500/15 border border-pink-400/25 flex items-center justify-center">
            <ShoppingBag className="w-5 h-5 text-pink-600 dark:text-pink-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Dashboard Toko Online</h1>
            <p className="text-sm text-foreground/50">Marketplace, KOL Management & Customer Service — CV. Dewi Aditya</p>
          </div>
        </div>
      </motion.div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {STATS.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 * i }}>
            <GlassCard hover className={`p-5 border ${s.border}`}>
              <div className={`w-9 h-9 rounded-lg ${s.bg} border ${s.border} flex items-center justify-center mb-3`}>
                <s.icon className={`w-4.5 h-4.5 ${s.accent}`} />
              </div>
              <div className="text-2xl font-bold text-foreground">{s.value}</div>
              <div className="text-xs text-foreground/50 mt-0.5">{s.label}</div>
            </GlassCard>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Quick Actions */}
        <GlassCard hover={false} className="p-5">
          <h3 className="text-sm font-semibold text-foreground/80 mb-4">Aksi Cepat</h3>
          <div className="space-y-2">
            {QUICK_ACTIONS.map(a => (
              <button key={a.label} className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-foreground/5 transition-colors text-left group">
                <div className="w-8 h-8 rounded-lg bg-foreground/5 flex items-center justify-center shrink-0">
                  <a.icon className={`w-4 h-4 ${a.color}`} />
                </div>
                <span className="text-sm text-foreground/70 group-hover:text-foreground flex-1">{a.label}</span>
                <ChevronRight className="w-3.5 h-3.5 text-foreground/30 group-hover:text-foreground/60" />
              </button>
            ))}
          </div>
        </GlassCard>

        {/* Status Modul */}
        <GlassCard hover={false} className="p-5">
          <h3 className="text-sm font-semibold text-foreground/80 mb-4">Status Pengembangan Modul</h3>
          <div className="space-y-3">
            {[
              { name: 'Manajemen Pesanan Marketplace', status: 'Dalam Pengembangan', ready: false },
              { name: 'KOL & Kreator Management',     status: 'Dalam Pengembangan', ready: false },
              { name: 'Sample Tracking & Pengiriman', status: 'Dalam Pengembangan', ready: false },
              { name: 'Flashsale & Price Management', status: 'Dalam Pengembangan', ready: false },
              { name: 'Return & Refund Management',   status: 'Dalam Pengembangan', ready: false },
              { name: 'Integrasi Marketplace API',    status: 'Direncanakan (Fase 5)', ready: false },
            ].map(m => (
              <div key={m.name} className="flex items-center gap-3">
                {m.ready
                  ? <CheckCircle2 className="w-4 h-4 text-green-700 dark:text-green-400 shrink-0" />
                  : <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0" />}
                <div className="flex-1">
                  <div className="text-sm text-foreground/80">{m.name}</div>
                  <div className="text-xs text-foreground/40">{m.status}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 p-3 rounded-xl bg-pink-500/8 border border-pink-300 dark:border-pink-400/20">
            <p className="text-xs text-foreground/50">
              Portal Toko Online sedang dalam pengembangan (Fase 4). Integrasi marketplace API (Shopee/Tokopedia) tersedia di Fase 5.
            </p>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
