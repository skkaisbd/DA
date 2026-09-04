import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, BookCheck, Download, Search } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const todayISO = () => new Date().toISOString().slice(0, 10);
const startOfMonth = () => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); };

const SOURCE_OPTIONS = [
  { value: '', label: 'Semua Sumber' },
  { value: 'manual', label: 'Manual JE' },
  { value: 'ar_invoice', label: 'AR Invoice' },
  { value: 'ar_payment', label: 'AR Payment' },
  { value: 'ap_invoice', label: 'AP Invoice' },
  { value: 'ap_payment', label: 'AP Payment' },
  { value: 'expense', label: 'Expense' },
  { value: 'payroll_finalize', label: 'Payroll' },
  { value: 'inventory_receive', label: 'Inventory Receive' },
  { value: 'inventory_issue', label: 'Inventory Issue' },
  { value: 'inventory_adjust', label: 'Inventory Adjust' },
  { value: 'cogs_shipment', label: 'COGS Shipment' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'Semua Status' },
  { value: 'draft', label: 'Draft' },
  { value: 'posted', label: 'Posted' },
  { value: 'voided', label: 'Voided' },
];

function StatusPill({ status }) {
  const map = {
    draft: 'bg-foreground/10 text-muted-foreground',
    posted: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
    voided: 'bg-rose-500/20 text-rose-300 border border-rose-500/40',
  };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold ${map[status] || ''}`}>{status}</span>;
}

export default function RahazaJournalListModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [from, setFrom] = useState(startOfMonth());
  const [to, setTo] = useState(todayISO());
  const [source, setSource] = useState('');
  const [status, setStatus] = useState('');
  const [accountCode, setAccountCode] = useState('');
  const [search, setSearch] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ from, to });
      if (source) params.set('source', source);
      if (status) params.set('status', status);
      if (accountCode) params.set('account_code', accountCode);
      const r = await fetch(`/api/rahaza/finance/reports/journal-list?${params}`, { headers });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, from, to, source, status, accountCode]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const openDetail = async (je_id) => {
    const r = await fetch(`/api/rahaza/journals/${je_id}`, { headers });
    if (!r.ok) return;
    setSelected(await r.json());
  };

  const exportCSV = () => {
    if (!data?.rows) return;
    const rows = data.rows.map(r => [r.je_number, r.date, r.status, r.source_module, r.source_ref || '', r.memo, r.total_debit, r.total_credit]);
    const csv = [
      ['JE Number', 'Date', 'Status', 'Source', 'Ref', 'Memo', 'Debit', 'Credit'],
      ...rows,
    ].map(r => r.map(c => (typeof c === 'string' && c.includes(',')) ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `journal-list-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const filtered = (data?.rows || []).filter(r => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (r.je_number || '').toLowerCase().includes(s) || (r.memo || '').toLowerCase().includes(s) || (r.source_ref || '').toLowerCase().includes(s);
  });
  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);

  return (
    <div className="space-y-5" data-testid="jl-page">
      <PageHeader
        icon={BookCheck}
        eyebrow="Accounting Core · F2"
        title="Journal List (Audit Trail)"
        subtitle="Daftar semua jurnal (manual + auto-posting) dengan filter sumber, akun, dan periode."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="jl-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} disabled={!filtered.length} className="h-9 border border-[var(--glass-border)]" data-testid="jl-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dari</span>
            <GlassInput type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 w-36" data-testid="jl-from" />
            <span className="text-xs text-muted-foreground">s/d</span>
            <GlassInput type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 w-36" data-testid="jl-to" />
          </div>
          <select value={source} onChange={e => setSource(e.target.value)} className="h-8 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-xs text-foreground" data-testid="jl-source">
            {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={status} onChange={e => setStatus(e.target.value)} className="h-8 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-xs text-foreground" data-testid="jl-status">
            {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <GlassInput value={accountCode} onChange={e => setAccountCode(e.target.value.trim())} placeholder="Kode Akun (opsional)" className="h-8 w-40" data-testid="jl-account" />
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <GlassInput value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari JE/memo/ref…" className="pl-8 h-8" data-testid="jl-search" />
          </div>
        </div>
      </GlassCard>

      {error && <GlassCard className="p-3 text-sm text-[hsl(var(--destructive))]" data-testid="jl-error">{error}</GlassCard>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Jumlah JE" value={data?.count || 0} testId="jl-kpi-count" />
        <StatTile label="Total Debit" value={fmt(data?.total_debit)} testId="jl-kpi-debit" />
        <StatTile label="Total Credit" value={fmt(data?.total_credit)} testId="jl-kpi-credit" />
        <StatTile label="Balanced" value={(data?.total_debit || 0) === (data?.total_credit || 0) ? 'Yes' : 'No'} accent={(data?.total_debit || 0) === (data?.total_credit || 0) ? 'success' : 'danger'} testId="jl-kpi-balanced" />
      </div>

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-muted-foreground">Memuat…</div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground">Tidak ada jurnal di filter ini.</div>
        ) : (
          <>
          <div className="overflow-x-auto max-h-[640px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-sm">
                <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="py-2 px-3">JE Number</th>
                  <th className="py-2 px-3">Tanggal</th>
                  <th className="py-2 px-3">Sumber</th>
                  <th className="py-2 px-3">Memo</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3 text-right">Debit</th>
                  <th className="py-2 px-3 text-right">Credit</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(r => (
                  <tr key={r.id} onClick={() => openDetail(r.id)} className="border-b border-[var(--glass-border)] hover:bg-foreground/5 cursor-pointer" data-testid={`jl-row-${r.je_number}`}>
                    <td className="py-2 px-3 font-mono text-xs">{r.je_number}</td>
                    <td className="py-2 px-3">{r.date}</td>
                    <td className="py-2 px-3 text-xs uppercase text-muted-foreground">{r.source_module || 'manual'}</td>
                    <td className="py-2 px-3 text-xs">{r.memo}</td>
                    <td className="py-2 px-3"><StatusPill status={r.status} /></td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-emerald-300">{fmt(r.total_debit)}</td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-sky-300">{fmt(r.total_credit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-3" />
          </>
        )}
      </GlassCard>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <GlassCard className="p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()} data-testid="jl-detail">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-bold text-foreground">{selected.je_number}</h3>
                <p className="text-xs text-muted-foreground">{selected.date} · {selected.source_module || 'manual'} · <StatusPill status={selected.status} /></p>
              </div>
              <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground" data-testid="jl-detail-close">×</button>
            </div>
            <p className="text-sm text-muted-foreground mb-4">{selected.memo}</p>
            {selected.source_ref && <p className="text-xs text-muted-foreground mb-4">Ref: <span className="font-mono">{selected.source_ref}</span></p>}
            <table className="w-full text-sm border border-[var(--glass-border)] rounded overflow-hidden">
              <thead className="bg-[var(--card-surface)]">
                <tr className="text-left text-[10px] uppercase text-muted-foreground">
                  <th className="py-2 px-3">Akun</th>
                  <th className="py-2 px-3">Deskripsi</th>
                  <th className="py-2 px-3 text-right">Debit</th>
                  <th className="py-2 px-3 text-right">Credit</th>
                </tr>
              </thead>
              <tbody>
                {(selected.lines || []).map(ln => (
                  <tr key={ln.line_id} className="border-t border-[var(--glass-border)]">
                    <td className="py-2 px-3"><span className="font-mono text-xs">{ln.account_code}</span> — {ln.account_name}</td>
                    <td className="py-2 px-3 text-xs">{ln.description}</td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-emerald-300">{ln.debit ? fmt(ln.debit) : ''}</td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-sky-300">{ln.credit ? fmt(ln.credit) : ''}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-[var(--card-surface)] font-semibold">
                  <td colSpan={2} className="py-2 px-3 text-xs uppercase">TOTAL</td>
                  <td className="py-2 px-3 text-right font-mono text-xs">{fmt(selected.total_debit)}</td>
                  <td className="py-2 px-3 text-right font-mono text-xs">{fmt(selected.total_credit)}</td>
                </tr>
              </tfoot>
            </table>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
