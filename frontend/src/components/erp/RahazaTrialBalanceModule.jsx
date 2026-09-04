import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Scale, Download, FileBarChart, Search } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile, EmptyState } from './moduleAtoms';
import { Skeleton } from '@/components/ui/skeleton';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const todayISO = () => new Date().toISOString().slice(0, 10);

export default function RahazaTrialBalanceModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [from, setFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); });
  const [to, setTo] = useState(todayISO());
  const [showZero, setShowZero] = useState(false);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ from, to, show_zero: showZero ? 'true' : 'false' });
      const r = await fetch(`/api/rahaza/finance/reports/trial-balance?${params}`, { headers });
      if (r.ok) setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, from, to, showZero]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const exportCSV = () => {
    if (!data?.rows) return;
    const rows = data.rows.map(r => [r.code, r.name, r.type, r.opening_debit, r.opening_credit, r.period_debit, r.period_credit, r.end_debit, r.end_credit]);
    const csv = [
      ['Kode', 'Nama', 'Tipe', 'Opening Debit', 'Opening Credit', 'Period Debit', 'Period Credit', 'End Debit', 'End Credit'],
      ...rows,
    ].map(r => r.map(c => typeof c === 'string' && c.includes(',') ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `trial-balance-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const filtered = (data?.rows || []).filter(r => {
    if (typeFilter && r.type !== typeFilter) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return r.code.toLowerCase().includes(s) || r.name.toLowerCase().includes(s);
  });

  return (
    <div className="space-y-5" data-testid="rahaza-tb-page">
      <PageHeader
        icon={Scale}
        eyebrow="Portal Finance · Laporan"
        title="Trial Balance (Neraca Saldo)"
        subtitle="Laporan saldo semua akun untuk verifikasi double-entry. Debit harus sama dengan Credit."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="tb-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} className="h-9 border border-[var(--glass-border)]" disabled={!data?.rows?.length} data-testid="tb-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dari</span>
            <GlassInput type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 w-36" data-testid="tb-from" />
            <span className="text-xs text-muted-foreground">s/d</span>
            <GlassInput type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 w-36" data-testid="tb-to" />
          </div>
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="h-8 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-xs text-foreground"
            data-testid="tb-type"
          >
            <option value="">Semua Tipe</option>
            <option value="ASSET">Aset</option>
            <option value="LIABILITY">Liabilitas</option>
            <option value="EQUITY">Ekuitas</option>
            <option value="REVENUE">Pendapatan</option>
            <option value="COGS">HPP</option>
            <option value="EXPENSE">Beban</option>
          </select>
          <label className="inline-flex items-center gap-2 text-xs text-foreground/80">
            <input type="checkbox" checked={showZero} onChange={e => setShowZero(e.target.checked)} data-testid="tb-show-zero" />
            Tampilkan akun saldo 0
          </label>
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <GlassInput value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari akun…" className="pl-8 h-8" data-testid="tb-search" />
          </div>
        </div>
      </GlassCard>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Period Debit" value={fmt(data?.totals?.period_debit)} testId="tb-kpi-pd" />
        <StatTile label="Period Credit" value={fmt(data?.totals?.period_credit)} testId="tb-kpi-pc" />
        <StatTile label="Ending Debit" value={fmt(data?.totals?.end_debit)} accent="primary" testId="tb-kpi-ed" />
        <StatTile
          label={data?.balanced ? 'Ending Credit (Balanced ✓)' : 'Ending Credit (UNBALANCED!)'}
          value={fmt(data?.totals?.end_credit)}
          accent={data?.balanced ? 'success' : 'danger'}
          testId="tb-kpi-ec"
        />
      </div>

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-lg" />)}</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground">
            <FileBarChart className="w-10 h-10 mx-auto mb-2 opacity-40" />
            Tidak ada data. Coba ubah periode atau centang “Tampilkan akun saldo 0”.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-sm">
                <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="py-2 px-2">Kode</th>
                  <th className="py-2 px-2">Akun</th>
                  <th className="py-2 px-2">Tipe</th>
                  <th className="py-2 px-2 text-right">Saldo Awal (Dr)</th>
                  <th className="py-2 px-2 text-right">Saldo Awal (Cr)</th>
                  <th className="py-2 px-2 text-right">Mutasi Debit</th>
                  <th className="py-2 px-2 text-right">Mutasi Credit</th>
                  <th className="py-2 px-2 text-right">Saldo Akhir (Dr)</th>
                  <th className="py-2 px-2 text-right">Saldo Akhir (Cr)</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.code} className="border-b border-[var(--glass-border)] hover:bg-foreground/5" data-testid={`tb-row-${r.code}`}>
                    <td className="py-1.5 px-2 font-mono text-xs">{r.code}</td>
                    <td className="py-1.5 px-2">{r.name}</td>
                    <td className="py-1.5 px-2 text-[10px] uppercase text-muted-foreground">{r.type}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs">{r.opening_debit ? fmt(r.opening_debit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs">{r.opening_credit ? fmt(r.opening_credit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs text-emerald-300">{r.period_debit ? fmt(r.period_debit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs text-sky-300">{r.period_credit ? fmt(r.period_credit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs font-semibold">{r.end_debit ? fmt(r.end_debit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs font-semibold">{r.end_credit ? fmt(r.end_credit) : ''}</td>
                  </tr>
                ))}
                {data?.totals && (
                  <tr className="font-semibold bg-[var(--card-surface)] border-t-2 border-[var(--glass-border)]">
                    <td colSpan={3} className="py-2 px-2 text-right text-xs uppercase">TOTAL</td>
                    <td className="py-2 px-2 text-right font-mono text-xs">{fmt(data.totals.opening_debit)}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs">{fmt(data.totals.opening_credit)}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs text-emerald-300">{fmt(data.totals.period_debit)}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs text-sky-300">{fmt(data.totals.period_credit)}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs">{fmt(data.totals.end_debit)}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs">{fmt(data.totals.end_credit)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
