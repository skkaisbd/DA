/**
 * AccessoriesReports — Portal Aksesoris MVP
 * Session #11.21 — Simple 3-tab report view
 *
 * Tabs: Pemakaian | Stock Level | Biaya
 * Uses existing /api/acc/* endpoints where available,
 * shows EmptyState placeholder for endpoints not yet built.
 */

import { useState, useEffect, useCallback } from 'react';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  BarChart3, Package, TrendingDown, DollarSign,
  RefreshCw, Download, Calendar, AlertCircle
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || '';

function fmtDate(iso) {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return iso?.slice(0, 10) || '-'; }
}

function fmtNum(n) { return Number(n || 0).toLocaleString('id-ID'); }

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse bg-foreground/5 rounded-lg ${className}`} />;
}

function EmptyPlaceholder({ title = 'Data Belum Tersedia', desc = '' }) {
  return (
    <div className="text-center py-16">
      <AlertCircle className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
      <p className="font-medium text-foreground/70">{title}</p>
      {desc && <p className="text-sm text-muted-foreground mt-1">{desc}</p>}
    </div>
  );
}

// ── Stock Level Report (uses existing /api/acc/items) ────────────────────
function StockLevelTab({ token }) {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');
  const [search, setSearch]   = useState('');
  const [filter, setFilter]   = useState('all');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/acc/items`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const filtered = items.filter(i => {
    const matchSearch = !search ||
      i.name?.toLowerCase().includes(search.toLowerCase()) ||
      i.code?.toLowerCase().includes(search.toLowerCase());
    const matchFilter =
      filter === 'all' ? true :
      filter === 'low'  ? (i.stock_qty ?? 0) <= (i.min_stock ?? 0) && (i.stock_qty ?? 0) > 0 :
      filter === 'out'  ? (i.stock_qty ?? 0) <= 0 :
      true;
    return matchSearch && matchFilter;
  });

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="space-y-4" data-testid="acc-reports-stock">
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          placeholder="Cari nama / kode..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg border border-foreground/10 bg-foreground/5 text-sm focus:outline-none focus:ring-1 focus:ring-[hsl(var(--primary)/0.5)]"
        />
        <select
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="px-3 py-2 rounded-lg border border-foreground/10 bg-foreground/5 text-sm focus:outline-none"
        >
          <option value="all">Semua Status</option>
          <option value="low">Stok Rendah</option>
          <option value="out">Stok Habis</option>
        </select>
      </div>

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

      {loading ? (
        <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : filtered.length === 0 ? (
        <EmptyPlaceholder title="Tidak ada item aksesoris" desc="Tambahkan item di menu Master & Stok." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-foreground/[0.03]">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Kode</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Nama Item</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Kategori</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Stok Saat Ini</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Min. Stok</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {paged.map(item => {
                const qty = item.stock_qty ?? 0;
                const min = item.min_stock ?? 0;
                const status = qty <= 0 ? 'Habis' : (min > 0 && qty <= min) ? 'Rendah' : 'Aman';
                const statusCls = qty <= 0
                  ? 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10'
                  : (min > 0 && qty <= min)
                  ? 'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10'
                  : 'text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/10';
                return (
                  <tr key={item.id} className="hover:bg-foreground/[0.03] transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{item.code || '-'}</td>
                    <td className="px-4 py-3 font-medium">{item.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{item.category || '-'}</td>
                    <td className="px-4 py-3 text-right font-semibold">{fmtNum(qty)} {item.unit}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{fmtNum(min)}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusCls}`}>{status}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          <div className="px-4 py-3 border-t border-foreground/10 text-xs text-muted-foreground">
            {filtered.length} item ditampilkan dari {items.length} total
          </div>
        </div>
      )}
    </div>
  );
}

// ── Placeholder tabs ─────────────────────────────────────────────────────
function UsageTab() {
  return (
    <EmptyPlaceholder
      title="Laporan Pemakaian — Coming Soon"
      desc="Fitur ini akan menampilkan rekap pemakaian aksesoris per periode, divisi, dan item. Akan tersedia di pembaruan berikutnya."
    />
  );
}

function CostTab() {
  return (
    <EmptyPlaceholder
      title="Analisis Biaya — Coming Soon"
      desc="Fitur ini akan menampilkan analisis biaya aksesoris termasuk HPP per unit produksi. Akan tersedia di pembaruan berikutnya."
    />
  );
}

// ── Main Component ─────────────────────────────────────────────────────────
const TABS = [
  { id: 'stock',  label: 'Stock Level',  icon: Package },
  { id: 'usage',  label: 'Pemakaian',    icon: TrendingDown },
  { id: 'cost',   label: 'Biaya',        icon: DollarSign },
];

export default function AccessoriesReports({ token }) {
  const [tab, setTab] = useState('stock');

  return (
    <div className="space-y-5" data-testid="accessories-reports">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Laporan Aksesoris</h2>
          <p className="text-muted-foreground text-sm mt-1">Laporan stock level, pemakaian, dan analisis biaya aksesoris</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-foreground/5 border border-foreground/10 rounded-xl w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              tab === t.id
                ? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))] shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-foreground/5'
            }`}
            data-testid={`acc-reports-tab-${t.id}`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="bg-foreground/[0.02] border border-foreground/10 rounded-xl p-5">
        {tab === 'stock' && <StockLevelTab token={token} />}
        {tab === 'usage' && <UsageTab />}
        {tab === 'cost' && <CostTab />}
      </div>
    </div>
  );
}
