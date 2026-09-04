
import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend } from 'recharts';
import { TrendingUp, TrendingDown, RefreshCw, DollarSign, ArrowUpCircle, ArrowDownCircle, BarChart2 } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from './EmptyState';
import { formatRupiah } from '@/lib/format';

const FILTER_OPTIONS = [
  { label: 'Hari Ini', value: 'today' },
  { label: '7 Hari', value: '7d' },
  { label: '28 Hari', value: '28d' },
  { label: 'Bulan Ini', value: 'month' },
  { label: 'Semua', value: 'all' },
  { label: 'Custom', value: 'custom' },
];

function getDateRange(filter) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (filter === 'today') return { date_from: today.toISOString().split('T')[0], date_to: today.toISOString().split('T')[0] };
  if (filter === '7d') { const d = new Date(today); d.setDate(d.getDate() - 7); return { date_from: d.toISOString().split('T')[0], date_to: today.toISOString().split('T')[0] }; }
  if (filter === '28d') { const d = new Date(today); d.setDate(d.getDate() - 28); return { date_from: d.toISOString().split('T')[0], date_to: today.toISOString().split('T')[0] }; }
  if (filter === 'month') { const d = new Date(now.getFullYear(), now.getMonth(), 1); return { date_from: d.toISOString().split('T')[0], date_to: today.toISOString().split('T')[0] }; }
  return {};
}

const fmt = formatRupiah;
const fmtShort = (v) => {
  const n = Number(v || 0);
  if (n >= 1000000000) return `${(n / 1000000000).toFixed(1)}M`;
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}jt`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return n.toLocaleString('id-ID');
};

export default function FinancialRecapModule({ token }) {
  const [recap, setRecap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');

  const fetchRecap = useCallback(async () => {
    setLoading(true);
    try {
      const range = filter === 'custom' ? { date_from: customFrom, date_to: customTo } : getDateRange(filter);
      const params = new URLSearchParams();
      if (range.date_from) params.set('date_from', range.date_from);
      if (range.date_to) params.set('date_to', range.date_to);
      const res = await fetch(`/api/financial-recap?${params.toString()}`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      setRecap(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [token, filter, customFrom, customTo]);

  useEffect(() => { fetchRecap(); }, [fetchRecap]);

  if (loading) return (
    <div className="space-y-4 p-2" data-testid="finance-recap-skeleton">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton className="h-52 rounded-xl" />
        <Skeleton className="h-52 rounded-xl" />
      </div>
    </div>
  );

  const r = recap || {};
  const grossMarginPct = r.gross_margin_pct || 0;
  const monthlyTrend = r.monthly_trend || [];
  const garmentSummary = r.garment_summary || [];

  const KPI_CARDS = [
    { label: 'Total Nilai Penjualan', value: fmt(r.total_sales_value), sub: `${r.total_buyer_invoices || 0} buyer invoice`, icon: <TrendingUp className="w-5 h-5" />, bg: 'bg-gradient-to-br from-emerald-500 to-emerald-600', text: 'text-emerald-500' },
    { label: 'Total Biaya Vendor', value: fmt(r.total_vendor_cost), sub: `${r.total_vendor_invoices || 0} vendor invoice`, icon: <TrendingDown className="w-5 h-5" />, bg: 'bg-gradient-to-br from-amber-500 to-amber-600', text: 'text-amber-700 dark:text-amber-500' },
    { label: 'Cash In (Dari Customer)', value: fmt(r.total_cash_in), sub: 'Total pembayaran diterima', icon: <ArrowDownCircle className="w-5 h-5" />, bg: 'bg-gradient-to-br from-blue-500 to-blue-600', text: 'text-primary' },
    { label: 'Cash Out (Ke Vendor)', value: fmt(r.total_cash_out), sub: 'Total pembayaran dikeluarkan', icon: <ArrowUpCircle className="w-5 h-5" />, bg: 'bg-gradient-to-br from-red-500 to-red-600', text: 'text-red-700 dark:text-red-500' },
    { label: 'Piutang Outstanding (AR)', value: fmt(r.accounts_receivable_outstanding), sub: 'Belum diterima dari buyer', icon: <DollarSign className="w-5 h-5" />, bg: 'bg-gradient-to-br from-purple-500 to-purple-600', text: 'text-purple-500' },
    { label: 'Hutang Outstanding (AP)', value: fmt(r.accounts_payable_outstanding), sub: 'Belum dibayar ke vendor', icon: <DollarSign className="w-5 h-5" />, bg: 'bg-gradient-to-br from-rose-500 to-rose-600', text: 'text-rose-500' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Rekap Keuangan</h1>
          <p className="text-muted-foreground text-sm mt-1">Ringkasan finansial produksi — Revenue, Cost, Cashflow, AP/AR</p>
        </div>
        <button onClick={fetchRecap} className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg text-sm hover:bg-[var(--glass-bg)]">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Date Filter */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border p-4 shadow-sm">
        <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">Filter Periode</p>
        <div className="flex flex-wrap gap-2 items-center">
          {FILTER_OPTIONS.map(opt => (
            <button key={opt.value} onClick={() => setFilter(opt.value)}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${filter === opt.value ? 'bg-primary text-foreground border-blue-600' : 'border-border text-muted-foreground hover:bg-[var(--glass-bg)]'}`}>
              {opt.label}
            </button>
          ))}
          {filter === 'custom' && (
            <div className="flex items-center gap-2 ml-2">
              <input type="date" value={customFrom} onChange={e => setCustomFrom(e.target.value)}
                className="border border-border rounded-lg px-3 py-1.5 text-sm" />
              <span className="text-muted-foreground text-sm">s/d</span>
              <input type="date" value={customTo} onChange={e => setCustomTo(e.target.value)}
                className="border border-border rounded-lg px-3 py-1.5 text-sm" />
              <button onClick={fetchRecap} className="px-3 py-1.5 bg-primary text-foreground rounded-lg text-sm">Terapkan</button>
            </div>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {KPI_CARDS.map(card => (
          <div key={card.label} className="bg-[var(--card-surface)] rounded-xl border border-border p-4 shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs text-muted-foreground">{card.label}</p>
              <span className={card.text}>{card.icon}</span>
            </div>
            <p className="text-xl font-bold text-foreground mt-1">{card.value}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Gross Margin Highlight */}
      <div className={`rounded-xl p-5 border ${r.gross_margin >= 0 ? 'bg-gradient-to-r from-emerald-50 to-blue-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">Est. Gross Margin</p>
            <p className={`text-3xl font-bold mt-1 ${r.gross_margin >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmt(r.gross_margin)}</p>
            <p className="text-sm text-muted-foreground mt-1">Nilai Penjualan − Biaya Vendor</p>
          </div>
          <div className={`text-center px-6 py-4 rounded-xl ${r.gross_margin >= 0 ? 'bg-emerald-100' : 'bg-red-100'}`}>
            <p className="text-xs text-muted-foreground">Margin %</p>
            <p className={`text-3xl font-bold ${r.gross_margin >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{grossMarginPct}%</p>
            <p className={`text-xs mt-0.5 ${r.gross_margin >= 0 ? 'text-emerald-600' : 'text-red-700 dark:text-red-500'}`}>{r.gross_margin >= 0 ? 'Profitable' : 'Loss'}</p>
          </div>
        </div>
        {/* Cash Flow Summary */}
        <div className="mt-4 grid grid-cols-4 gap-3">
          <div className="bg-[var(--card-surface)]/70 rounded-lg p-3">
            <p className="text-xs text-muted-foreground">Cash In</p>
            <p className="font-bold text-emerald-700">{fmt(r.total_cash_in)}</p>
          </div>
          <div className="bg-[var(--card-surface)]/70 rounded-lg p-3">
            <p className="text-xs text-muted-foreground">Cash Out</p>
            <p className="font-bold text-red-600">{fmt(r.total_cash_out)}</p>
          </div>
          <div className="bg-[var(--card-surface)]/70 rounded-lg p-3">
            <p className="text-xs text-muted-foreground">Net Cash Flow</p>
            <p className={`font-bold ${(r.total_cash_in - r.total_cash_out) >= 0 ? 'text-primary' : 'text-red-600'}`}>
              {fmt(r.total_cash_in - r.total_cash_out)}
            </p>
          </div>
          <div className="bg-[var(--card-surface)]/70 rounded-lg p-3">
            <p className="text-xs text-muted-foreground">Invoice Adjustments</p>
            <p className={`font-bold ${(r.total_adjustments || 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
              {(r.total_adjustments || 0) >= 0 ? '+' : ''}{fmt(r.total_adjustments || 0)}
            </p>
          </div>
        </div>
      </div>

      {/* Charts */}
      {monthlyTrend.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Sales vs Cost trend */}
          <div className="bg-[var(--card-surface)] rounded-xl border border-border p-5 shadow-sm">
            <h3 className="font-semibold text-foreground mb-1 text-sm">Tren Penjualan vs Biaya Vendor</h3>
            <p className="text-xs text-muted-foreground mb-4">6 bulan terakhir</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={monthlyTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 9 }} tickFormatter={fmtShort} />
                <Tooltip formatter={(v, n) => [fmt(v), n === 'sales' ? 'Penjualan' : n === 'cost' ? 'Biaya Vendor' : 'Margin']} />
                <Legend formatter={(v) => v === 'sales' ? 'Penjualan' : v === 'cost' ? 'Biaya Vendor' : 'Margin'} />
                <Bar dataKey="sales" fill="#10b981" name="sales" radius={[4, 4, 0, 0]} />
                <Bar dataKey="cost" fill="#f59e0b" name="cost" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Cash Flow trend */}
          <div className="bg-[var(--card-surface)] rounded-xl border border-border p-5 shadow-sm">
            <h3 className="font-semibold text-foreground mb-1 text-sm">Tren Cashflow</h3>
            <p className="text-xs text-muted-foreground mb-4">Cash In vs Cash Out per bulan</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={monthlyTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 9 }} tickFormatter={fmtShort} />
                <Tooltip formatter={(v, n) => [fmt(v), n === 'cash_in' ? 'Cash In' : n === 'cash_out' ? 'Cash Out' : 'Margin']} />
                <Legend formatter={(v) => v === 'cash_in' ? 'Cash In' : v === 'cash_out' ? 'Cash Out' : 'Margin'} />
                <Line type="monotone" dataKey="cash_in" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} name="cash_in" />
                <Line type="monotone" dataKey="cash_out" stroke="#ef4444" strokeWidth={2} dot={{ r: 4 }} name="cash_out" />
                <Line type="monotone" dataKey="margin" stroke="#10b981" strokeWidth={2} strokeDasharray="4 4" dot={{ r: 3 }} name="margin" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* AP/AR Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[var(--card-surface)] rounded-xl border border-amber-200 p-4 shadow-sm">
          <h3 className="font-semibold text-amber-700 mb-3 flex items-center gap-2">
            <ArrowUpCircle className="w-4 h-4" /> Accounts Payable (Hutang Vendor)
          </h3>
          <div className="space-y-2">
            {garmentSummary.length === 0 ? (
              <p className="text-sm text-muted-foreground">Tidak ada data</p>
            ) : garmentSummary.slice(0, 5).map((g, i) => (
              <div key={i} className="flex justify-between items-center">
                <span className="text-sm text-foreground">{g.garment_name}</span>
                <div className="text-right">
                  <p className="text-sm font-bold">{fmt(g.total_invoiced)}</p>
                  <p className={`text-xs ${g.outstanding > 0 ? 'text-red-700 dark:text-red-500' : 'text-emerald-500'}`}>
                    Sisa: {fmt(g.outstanding)}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-amber-100">
            <div className="flex justify-between">
              <span className="text-sm font-semibold text-amber-700">Total Outstanding AP</span>
              <span className="font-bold text-red-600">{fmt(r.accounts_payable_outstanding)}</span>
            </div>
          </div>
        </div>

        <div className="bg-[var(--card-surface)] rounded-xl border border-primary/20 p-4 shadow-sm">
          <h3 className="font-semibold text-primary mb-3 flex items-center gap-2">
            <ArrowDownCircle className="w-4 h-4" /> Accounts Receivable (Piutang Customer)
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center bg-primary/10 rounded-lg p-3">
              <div>
                <p className="text-sm font-semibold text-primary">Total Piutang</p>
                <p className="text-xs text-primary">{r.total_buyer_invoices || 0} buyer invoice</p>
              </div>
              <p className="text-lg font-bold text-primary">{fmt(r.total_sales_value)}</p>
            </div>
            <div className="flex justify-between items-center bg-emerald-50 rounded-lg p-3">
              <div>
                <p className="text-sm font-semibold text-emerald-700">Sudah Diterima</p>
                <p className="text-xs text-emerald-500">Total Cash In dari buyer</p>
              </div>
              <p className="text-lg font-bold text-emerald-700">{fmt(r.total_cash_in)}</p>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-blue-100">
            <div className="flex justify-between">
              <span className="text-sm font-semibold text-primary">Total Outstanding AR</span>
              <span className="font-bold text-red-600">{fmt(r.accounts_receivable_outstanding)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
