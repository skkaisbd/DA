import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Wallet, Download, Droplet, TrendingUp, ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import { Skeleton } from '@/components/ui/skeleton';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 });
const todayISO = () => new Date().toISOString().slice(0, 10);
const startOfMonth = () => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); };

function ActivityGroup({ label, items, total, testId, tone }) {
  const toneClass = total >= 0 ? 'text-emerald-300' : 'text-rose-300';
  const headerBar = tone === 'operating' ? 'bg-sky-500/10 border-sky-500/30' : tone === 'investing' ? 'bg-purple-500/10 border-purple-500/30' : 'bg-amber-500/10 border-amber-500/30';
  return (
    <GlassCard className="p-0 overflow-hidden" data-testid={testId}>
      <div className={`px-5 py-3 border-b border-[var(--glass-border)] ${headerBar} flex items-center justify-between`}>
        <h3 className="font-semibold text-sm uppercase tracking-wider">{label}</h3>
        <span className={`font-mono text-base font-bold ${toneClass}`}>{fmt(total)}</span>
      </div>
      {items.length === 0 ? (
        <div className="px-5 py-4 text-xs text-muted-foreground">Tidak ada aktivitas di periode ini.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
              <th className="py-2 px-5 text-left">Kategori</th>
              <th className="py-2 px-3 text-right">Masuk</th>
              <th className="py-2 px-3 text-right">Keluar</th>
              <th className="py-2 px-5 text-right">Net</th>
            </tr>
          </thead>
          <tbody>
            {items.map(r => (
              <tr key={r.category} className="border-b border-[var(--glass-border)] last:border-0" data-testid={`${testId}-row-${r.category}`}>
                <td className="py-2 px-5 text-sm">{r.label} <span className="text-[10px] text-muted-foreground">({r.count})</span></td>
                <td className="py-2 px-3 text-right font-mono text-xs text-emerald-300">{r.inflow > 0 ? fmt(r.inflow) : ''}</td>
                <td className="py-2 px-3 text-right font-mono text-xs text-rose-300">{r.outflow > 0 ? fmt(r.outflow) : ''}</td>
                <td className={`py-2 px-5 text-right font-mono text-sm ${r.net >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{fmt(r.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </GlassCard>
  );
}

export default function RahazaCashFlowModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [from, setFrom] = useState(startOfMonth());
  const [to, setTo] = useState(todayISO());
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ from, to });
      const r = await fetch(`/api/rahaza/finance/reports/cash-flow?${params}`, { headers });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, from, to]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = () => {
    if (!data) return;
    const lines = [['Activity', 'Category', 'Inflow', 'Outflow', 'Net', 'Count']];
    Object.entries(data.activities || {}).forEach(([key, act]) => {
      (act.items || []).forEach(r => lines.push([act.label, r.label, r.inflow, r.outflow, r.net, r.count]));
      lines.push([`${act.label} TOTAL`, '', '', '', act.total, '']);
    });
    lines.push(['Net Change', '', '', '', data.totals.net_change_in_cash, '']);
    lines.push(['Opening Cash', '', '', '', data.totals.opening_cash, '']);
    lines.push(['Closing Cash', '', '', '', data.totals.closing_cash, '']);
    const csv = lines.map(r => r.map(c => (typeof c === 'string' && c.includes(',')) ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `cash-flow-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const t = data?.totals || {};

  return (
    <div className="space-y-5" data-testid="cf-page">
      <PageHeader
        icon={Wallet}
        eyebrow="Accounting Core · F3"
        title="Laporan Arus Kas"
        subtitle="Cash Flow Statement — metode direct dari ledger pergerakan kas. Grouping: Operasi / Investasi / Pendanaan."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="cf-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} disabled={!data} className="h-9 border border-[var(--glass-border)]" data-testid="cf-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs text-muted-foreground">Dari</span>
          <GlassInput type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 w-36" data-testid="cf-from" />
          <span className="text-xs text-muted-foreground">s/d</span>
          <GlassInput type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 w-36" data-testid="cf-to" />
        </div>
      </GlassCard>

      {error && <GlassCard className="p-3 text-sm text-[hsl(var(--destructive))]" data-testid="cf-error">{error}</GlassCard>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile label="Kas Awal" value={fmt(t.opening_cash)} testId="cf-kpi-open" />
        <StatTile label="Operasi" value={fmt(t.operating)} accent={t.operating >= 0 ? 'success' : 'danger'} testId="cf-kpi-operating" />
        <StatTile label="Investasi" value={fmt(t.investing)} testId="cf-kpi-investing" />
        <StatTile label="Pendanaan" value={fmt(t.financing)} testId="cf-kpi-financing" />
        <StatTile label="Kas Akhir" value={fmt(t.closing_cash)} accent="primary" testId="cf-kpi-closing" />
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-48 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
        </div>
      ) : !data ? (
        <EmptyState icon={Wallet} title="Tidak ada data cash flow" description="Laporan arus kas akan muncul setelah ada transaksi kas di periode ini." />
      ) : (
        <div className="space-y-4">
          <ActivityGroup label={data.activities.operating.label} items={data.activities.operating.items} total={data.activities.operating.total} testId="cf-operating" tone="operating" />
          <ActivityGroup label={data.activities.investing.label} items={data.activities.investing.items} total={data.activities.investing.total} testId="cf-investing" tone="investing" />
          <ActivityGroup label={data.activities.financing.label} items={data.activities.financing.items} total={data.activities.financing.total} testId="cf-financing" tone="financing" />

          <GlassCard className="p-5 border-2" data-testid="cf-summary">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Droplet className="w-4 h-4 text-sky-300" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Kas Awal Periode</span>
              </div>
              <span className="font-mono text-base">{fmt(t.opening_cash)}</span>
            </div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                {t.net_change_in_cash >= 0 ? <ArrowUpCircle className="w-4 h-4 text-emerald-300" /> : <ArrowDownCircle className="w-4 h-4 text-rose-300" />}
                <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Perubahan Bersih Kas</span>
              </div>
              <span className={`font-mono text-base font-bold ${t.net_change_in_cash >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{fmt(t.net_change_in_cash)}</span>
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-[var(--glass-border)]">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-[hsl(var(--primary))]" />
                <span className="text-sm uppercase tracking-wider font-bold">Kas Akhir Periode</span>
              </div>
              <span className="font-mono text-xl font-bold">{fmt(t.closing_cash)}</span>
            </div>
          </GlassCard>

          {data.cash_accounts?.length > 0 && (
            <GlassCard className="p-0 overflow-hidden" data-testid="cf-accounts">
              <div className="px-5 py-3 border-b border-[var(--glass-border)] bg-[var(--card-surface)]/40">
                <h3 className="font-semibold text-sm uppercase tracking-wider">Saldo Rekening Kas/Bank (Current)</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                    <th className="py-2 px-5 text-left">Kode</th>
                    <th className="py-2 px-3 text-left">Nama</th>
                    <th className="py-2 px-3 text-left">Tipe</th>
                    <th className="py-2 px-5 text-right">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {data.cash_accounts.map(a => (
                    <tr key={a.id} className="border-b border-[var(--glass-border)] last:border-0">
                      <td className="py-2 px-5 font-mono text-xs">{a.code}</td>
                      <td className="py-2 px-3">{a.name}</td>
                      <td className="py-2 px-3 text-xs uppercase text-muted-foreground">{a.type}</td>
                      <td className="py-2 px-5 text-right font-mono text-sm">{fmt(a.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </GlassCard>
          )}
        </div>
      )}
    </div>
  );
}
