import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, TrendingUp, Download, FileBarChart, ChevronRight } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import { Skeleton } from '@/components/ui/skeleton';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const todayISO = () => new Date().toISOString().slice(0, 10);
const startOfYear = () => { const d = new Date(); d.setMonth(0, 1); return d.toISOString().slice(0, 10); };

function Section({ label, total, accounts, testId, tone }) {
  const [open, setOpen] = useState(false);
  const toneClass = tone === 'revenue' ? 'text-emerald-300' : tone === 'expense' ? 'text-rose-300' : 'text-foreground';
  return (
    <GlassCard className="p-0 overflow-hidden" data-testid={testId}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-foreground/5 transition-colors"
        data-testid={`${testId}-toggle`}
      >
        <div className="flex items-center gap-3">
          <ChevronRight className={`w-4 h-4 transition-transform ${open ? 'rotate-90' : ''}`} />
          <span className="font-semibold text-sm text-foreground uppercase tracking-wider">{label}</span>
        </div>
        <span className={`font-mono font-semibold ${toneClass}`}>{fmt(total)}</span>
      </button>
      {open && (
        <div className="border-t border-[var(--glass-border)] bg-[var(--card-surface)]/40">
          {accounts.filter(a => a.amount !== 0).length === 0 ? (
            <div className="px-5 py-3 text-xs text-muted-foreground">Tidak ada saldo di periode ini.</div>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {accounts.filter(a => a.amount !== 0).map(a => (
                  <tr key={a.code} className="border-b border-[var(--glass-border)] last:border-0">
                    <td className="py-2 px-5 font-mono text-xs text-muted-foreground w-28">{a.code}</td>
                    <td className="py-2 px-2 text-sm">{a.name}</td>
                    <td className="py-2 px-5 text-right font-mono text-sm">{fmt(a.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </GlassCard>
  );
}

export default function RahazaPnLModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [from, setFrom] = useState(startOfYear());
  const [to, setTo] = useState(todayISO());
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ from, to });
      const r = await fetch(`/api/rahaza/finance/reports/profit-loss?${params}`, { headers });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, from, to]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = () => {
    if (!data) return;
    const lines = [['Group', 'Code', 'Name', 'Amount']];
    Object.entries(data.groups || {}).forEach(([key, g]) => {
      (g.accounts || []).forEach(a => {
        lines.push([g.label, a.code, a.name, a.amount]);
      });
      lines.push([`${g.label} — TOTAL`, '', '', g.total]);
    });
    Object.entries(data.totals || {}).forEach(([k, v]) => lines.push(['TOTALS', k, '', v]));
    const csv = lines.map(r => r.map(c => (typeof c === 'string' && c.includes(',')) ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `profit-loss-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const t = data?.totals || {};

  return (
    <div className="space-y-5" data-testid="pnl-page">
      <PageHeader
        icon={TrendingUp}
        eyebrow="Accounting Core · F2"
        title="Profit & Loss (Laba Rugi)"
        subtitle="Laporan laba rugi periodik: Pendapatan − HPP − Beban = Laba Bersih."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="pnl-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} disabled={!data} className="h-9 border border-[var(--glass-border)]" data-testid="pnl-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs text-muted-foreground">Dari</span>
          <GlassInput type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 w-36" data-testid="pnl-from" />
          <span className="text-xs text-muted-foreground">s/d</span>
          <GlassInput type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 w-36" data-testid="pnl-to" />
        </div>
      </GlassCard>

      {error && (
        <GlassCard className="p-3 text-sm text-[hsl(var(--destructive))]" data-testid="pnl-error">{error}</GlassCard>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Pendapatan" value={fmt(t.revenue)} accent="success" testId="pnl-kpi-revenue" />
        <StatTile label="HPP" value={fmt(t.cogs)} testId="pnl-kpi-cogs" />
        <StatTile label="Gross Profit" value={fmt(t.gross_profit)} accent="primary" testId="pnl-kpi-gross" />
        <StatTile label={t.net_income >= 0 ? 'Laba Bersih' : 'Rugi Bersih'} value={fmt(t.net_income)} accent={t.net_income >= 0 ? 'success' : 'danger'} testId="pnl-kpi-net" />
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 rounded-xl" />
          <Skeleton className="h-16 rounded-xl" />
          <Skeleton className="h-16 rounded-xl" />
          <Skeleton className="h-16 rounded-xl" />
        </div>
      ) : !data ? (
        <EmptyState icon={FileBarChart} title="Tidak ada data" description="Laporan laba rugi akan muncul setelah ada transaksi di periode ini." />
      ) : (
        <div className="space-y-3">
          <Section label={data.groups.revenue.label} total={data.groups.revenue.total} accounts={data.groups.revenue.accounts} testId="pnl-sec-revenue" tone="revenue" />
          <Section label={data.groups.cogs.label} total={data.groups.cogs.total} accounts={data.groups.cogs.accounts} testId="pnl-sec-cogs" tone="expense" />
          <GlassCard className="p-4 bg-[var(--card-surface)]/60">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Gross Profit</span>
              <span className="font-mono text-base font-bold">{fmt(t.gross_profit)}</span>
            </div>
          </GlassCard>
          <Section label={data.groups.expense.label} total={data.groups.expense.total} accounts={data.groups.expense.accounts} testId="pnl-sec-expense" tone="expense" />
          <GlassCard className="p-4 bg-[var(--card-surface)]/60">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Operating Income</span>
              <span className={`font-mono text-base font-bold ${t.operating_income >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{fmt(t.operating_income)}</span>
            </div>
          </GlassCard>
          <Section label={data.groups.other_income.label} total={data.groups.other_income.total} accounts={data.groups.other_income.accounts} testId="pnl-sec-other-income" tone="revenue" />
          <Section label={data.groups.other_expense.label} total={data.groups.other_expense.total} accounts={data.groups.other_expense.accounts} testId="pnl-sec-other-expense" tone="expense" />
          <GlassCard className="p-5 border-2" data-testid="pnl-net-summary">
            <div className="flex items-center justify-between">
              <span className="text-sm uppercase tracking-wider font-bold">{t.net_income >= 0 ? 'LABA BERSIH' : 'RUGI BERSIH'}</span>
              <span className={`font-mono text-xl font-bold ${t.net_income >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{fmt(t.net_income)}</span>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
