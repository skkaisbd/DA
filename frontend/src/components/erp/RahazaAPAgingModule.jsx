import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, CreditCard, Download, FileBarChart } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 0 });

const BUCKETS = [
  { key: 'current', label: 'Belum Jatuh Tempo', tone: 'text-emerald-300' },
  { key: '1_30', label: '1–30 hari', tone: 'text-sky-300' },
  { key: '31_60', label: '31–60 hari', tone: 'text-amber-300' },
  { key: '61_90', label: '61–90 hari', tone: 'text-orange-300' },
  { key: '90_plus', label: '>90 hari', tone: 'text-rose-300' },
];

export default function RahazaAPAgingModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await fetch('/api/rahaza/ap-aging', { headers });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = () => {
    if (!data?.details) return;
    const rows = data.details.map(r => [
      r.invoice_number, r.vendor_name, r.issue_date, r.due_date,
      r.days_overdue, r.total, r.paid_amount, r.balance, r.status,
    ]);
    const csv = [
      ['Invoice', 'Vendor', 'Issue Date', 'Due Date', 'Days Overdue', 'Total', 'Paid', 'Balance', 'Status'],
      ...rows,
    ].map(r => r.map(c => (typeof c === 'string' && c.includes(',')) ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ap-aging-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5" data-testid="ap-aging-page">
      <PageHeader
        icon={CreditCard}
        eyebrow="Accounting Core · F2"
        title="AP Aging (Umur Hutang)"
        subtitle="Bucket umur hutang usaha berdasarkan tanggal jatuh tempo. Status sent / partial_paid ikut dihitung."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="apa-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} disabled={!data?.details?.length} className="h-9 border border-[var(--glass-border)]" data-testid="apa-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      {error && <GlassCard className="p-3 text-sm text-[hsl(var(--destructive))]" data-testid="apa-error">{error}</GlassCard>}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {BUCKETS.map(b => (
          <StatTile
            key={b.key}
            label={b.label}
            value={fmt(data?.buckets?.[b.key])}
            accent={b.key === 'current' ? 'success' : b.key === '90_plus' ? 'danger' : 'primary'}
            testId={`apa-kpi-${b.key}`}
          />
        ))}
      </div>
      <GlassCard className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm uppercase tracking-wider font-semibold text-muted-foreground">Total Outstanding</span>
          <span className="font-mono text-xl font-bold text-amber-300" data-testid="apa-total">{fmt(data?.total)}</span>
        </div>
      </GlassCard>

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
          </div>
        ) : !data?.details?.length ? (
          <EmptyState
            icon={FileBarChart}
            title="Tidak ada hutang outstanding"
            description="Semua pembayaran ke supplier sudah lunas atau belum ada transaksi AP."
            data-testid="apa-empty"
          />
        ) : (
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-sm">
                <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="py-2 px-3">Invoice</th>
                  <th className="py-2 px-3">Vendor</th>
                  <th className="py-2 px-3">Issue</th>
                  <th className="py-2 px-3">Due Date</th>
                  <th className="py-2 px-3 text-right">Days Overdue</th>
                  <th className="py-2 px-3 text-right">Total</th>
                  <th className="py-2 px-3 text-right">Paid</th>
                  <th className="py-2 px-3 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {data.details.map(r => {
                  const od = r.days_overdue || 0;
                  const tone = od <= 0 ? 'text-emerald-300' : od <= 30 ? 'text-sky-300' : od <= 60 ? 'text-amber-300' : od <= 90 ? 'text-orange-300' : 'text-rose-300';
                  return (
                    <tr key={r.id} className="border-b border-[var(--glass-border)] hover:bg-foreground/5" data-testid={`apa-row-${r.invoice_number}`}>
                      <td className="py-2 px-3 font-mono text-xs">{r.invoice_number}</td>
                      <td className="py-2 px-3">{r.vendor_name}</td>
                      <td className="py-2 px-3 text-xs">{r.issue_date}</td>
                      <td className="py-2 px-3 text-xs">{r.due_date}</td>
                      <td className={`py-2 px-3 text-right font-mono text-xs ${tone}`}>{od}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs">{fmt(r.total)}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs">{fmt(r.paid_amount)}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs text-amber-300 font-semibold">{fmt(r.balance)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
