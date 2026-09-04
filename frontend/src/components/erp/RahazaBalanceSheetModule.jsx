import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Scale, Download, FileBarChart, CheckCircle2, AlertTriangle } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import { Skeleton } from '@/components/ui/skeleton';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const todayISO = () => new Date().toISOString().slice(0, 10);

function AccountList({ title, accounts, total, testId, tone }) {
  const toneClass = tone === 'asset' ? 'text-sky-300' : tone === 'liab' ? 'text-amber-300' : 'text-emerald-300';
  return (
    <GlassCard className="p-0 overflow-hidden" data-testid={testId}>
      <div className="px-5 py-3 border-b border-[var(--glass-border)] bg-[var(--card-surface)]/40 flex items-center justify-between">
        <h3 className="font-semibold text-sm uppercase tracking-wider">{title}</h3>
        <span className={`font-mono text-sm font-bold ${toneClass}`}>{fmt(total)}</span>
      </div>
      {accounts.length === 0 ? (
        <div className="px-5 py-4 text-xs text-muted-foreground">Tidak ada saldo.</div>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {accounts.map(a => (
              <tr key={a.code} className="border-b border-[var(--glass-border)] last:border-0" data-testid={`${testId}-row-${a.code}`}>
                <td className="py-2 px-5 font-mono text-xs text-muted-foreground w-28">{a.code}</td>
                <td className="py-2 px-2 text-sm">
                  {a.name}
                  {a.computed && <span className="ml-2 text-[10px] uppercase text-muted-foreground">(auto P&L)</span>}
                </td>
                <td className="py-2 px-5 text-right font-mono text-sm">{fmt(a.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </GlassCard>
  );
}

export default function RahazaBalanceSheetModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [asOf, setAsOf] = useState(todayISO());
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await fetch(`/api/rahaza/finance/reports/balance-sheet?as_of=${asOf}`, { headers });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, asOf]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = () => {
    if (!data) return;
    const lines = [['Group', 'Code', 'Name', 'Amount']];
    (data.assets.accounts || []).forEach(a => lines.push(['Assets', a.code, a.name, a.amount]));
    lines.push(['Assets TOTAL', '', '', data.assets.total]);
    (data.liabilities.accounts || []).forEach(a => lines.push(['Liabilities', a.code, a.name, a.amount]));
    lines.push(['Liabilities TOTAL', '', '', data.liabilities.total]);
    (data.equity.accounts || []).forEach(a => lines.push(['Equity', a.code, a.name, a.amount]));
    lines.push(['Equity TOTAL', '', '', data.equity.total]);
    const csv = lines.map(r => r.map(c => (typeof c === 'string' && c.includes(',')) ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `balance-sheet-${asOf}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const t = data?.totals || {};

  return (
    <div className="space-y-5" data-testid="bs-page">
      <PageHeader
        icon={Scale}
        eyebrow="Accounting Core · F2"
        title="Balance Sheet (Neraca)"
        subtitle="Posisi keuangan per tanggal tertentu. Aset = Liabilitas + Ekuitas (termasuk Laba/Rugi tahun berjalan)."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="bs-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} disabled={!data} className="h-9 border border-[var(--glass-border)]" data-testid="bs-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs text-muted-foreground">Per Tanggal</span>
          <GlassInput type="date" value={asOf} onChange={e => setAsOf(e.target.value)} className="h-8 w-40" data-testid="bs-as-of" />
          {data && (
            <div className={`ml-auto flex items-center gap-2 text-xs font-semibold ${data.balanced ? 'text-emerald-300' : 'text-rose-300'}`} data-testid="bs-balanced">
              {data.balanced ? <><CheckCircle2 className="w-4 h-4" /> Balanced (Aset = Liab + Ekuitas)</> : <><AlertTriangle className="w-4 h-4" /> UNBALANCED! Diff = {fmt(t.diff)}</>}
            </div>
          )}
        </div>
      </GlassCard>

      {error && (
        <GlassCard className="p-3 text-sm text-[hsl(var(--destructive))]" data-testid="bs-error">{error}</GlassCard>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Total Aset" value={fmt(t.assets)} accent="primary" testId="bs-kpi-assets" />
        <StatTile label="Total Liabilitas" value={fmt(t.liabilities)} testId="bs-kpi-liab" />
        <StatTile label="Total Ekuitas" value={fmt(t.equity)} accent="success" testId="bs-kpi-equity" />
        <StatTile label={t.current_earnings >= 0 ? 'Laba YTD' : 'Rugi YTD'} value={fmt(t.current_earnings)} accent={t.current_earnings >= 0 ? 'success' : 'danger'} testId="bs-kpi-earnings" />
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-64 rounded-xl" />
          <div className="space-y-4">
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
        </div>
      ) : !data ? (
        <EmptyState icon={FileBarChart} title="Tidak ada data" description="Laporan Balance Sheet akan muncul setelah ada transaksi di periode ini." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AccountList title="ASET" accounts={data.assets.accounts || []} total={data.assets.total} testId="bs-assets" tone="asset" />
          <div className="space-y-4">
            <AccountList title="LIABILITAS" accounts={data.liabilities.accounts || []} total={data.liabilities.total} testId="bs-liab" tone="liab" />
            <AccountList title="EKUITAS" accounts={data.equity.accounts || []} total={data.equity.total} testId="bs-equity" tone="equity" />
            <GlassCard className="p-4 border-2">
              <div className="flex items-center justify-between">
                <span className="text-sm uppercase tracking-wider font-bold">Total Liab + Ekuitas</span>
                <span className="font-mono text-base font-bold">{fmt(t.liab_plus_equity)}</span>
              </div>
            </GlassCard>
          </div>
        </div>
      )}
    </div>
  );
}
