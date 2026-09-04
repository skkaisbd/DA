import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, FileText, Download, BookOpen } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';

const fmt = (n) => Number(n || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });
const todayISO = () => new Date().toISOString().slice(0, 10);

export default function RahazaGeneralLedgerModule({ token }) {
  const [accounts, setAccounts] = useState([]);
  const [code, setCode] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [from, setFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); });
  const [to, setTo] = useState(todayISO());
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => {
    fetch('/api/rahaza/coa/accounts', { headers })
      .then(r => r.ok ? r.json() : [])
      .then(list => { setAccounts(list.filter(a => !a.is_group)); if (list.length > 0) setCode(list.find(a => !a.is_group)?.code || ''); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const fetchGL = useCallback(async () => {
    if (!code) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ account_code: code, from, to });
      const r = await fetch(`/api/rahaza/finance/reports/general-ledger?${params}`, { headers });
      if (r.ok) setData(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, from, to, token]);
  useEffect(() => { fetchGL(); }, [fetchGL]);

  const exportCSV = () => {
    if (!data?.lines) return;
    const rows = data.lines.map(l => [l.date, l.je_number, l.description, l.source, l.debit, l.credit, l.balance]);
    const csv = [
      ['Tanggal', 'Jurnal', 'Deskripsi', 'Sumber', 'Debit', 'Credit', 'Saldo'],
      ...rows,
    ].map(r => r.map(c => typeof c === 'string' && c.includes(',') ? `"${c}"` : c).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `gl-${code}-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const acc = data?.account;
  const totalDebit = (data?.lines || []).reduce((s, l) => s + (l.debit || 0), 0);
  const totalCredit = (data?.lines || []).reduce((s, l) => s + (l.credit || 0), 0);

  return (
    <div className="space-y-5" data-testid="rahaza-gl-page">
      <PageHeader
        icon={BookOpen}
        eyebrow="Portal Finance · Laporan"
        title="Buku Besar (General Ledger)"
        subtitle="Detail semua transaksi per akun dengan saldo berjalan. Pilih akun dan range tanggal."
        actions={
          <>
            <Button variant="ghost" onClick={fetchGL} className="h-9 border border-[var(--glass-border)]" data-testid="gl-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={exportCSV} className="h-9 border border-[var(--glass-border)]" disabled={!data?.lines?.length} data-testid="gl-export"><Download className="w-3.5 h-3.5 mr-1.5" />Export CSV</Button>
          </>
        }
      />

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <label className="text-[10px] uppercase text-muted-foreground font-semibold block mb-1">Akun</label>
            <SmartNativeSelect
              value={code}
              onChange={e => setCode(e.target.value)}
              className="h-9 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-sm text-foreground min-w-[260px]"
              data-testid="gl-account"
            >
              <option value="">— Pilih akun —</option>
              {accounts.map(a => <option key={a.code} value={a.code}>{`${a.code} · ${a.name}`}</option>)}
            </SmartNativeSelect>
          </div>
          <div>
            <label className="text-[10px] uppercase text-muted-foreground font-semibold block mb-1">Dari</label>
            <GlassInput type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-9 w-40" data-testid="gl-from" />
          </div>
          <div>
            <label className="text-[10px] uppercase text-muted-foreground font-semibold block mb-1">Sampai</label>
            <GlassInput type="date" value={to} onChange={e => setTo(e.target.value)} className="h-9 w-40" data-testid="gl-to" />
          </div>
        </div>
      </GlassCard>

      {acc && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile label="Akun" value={acc.name} testId="gl-kpi-acc" />
          <StatTile label="Saldo Awal" value={fmt(data.opening_balance)} testId="gl-kpi-open" />
          <StatTile label="Total Debit / Credit" value={`${fmt(totalDebit)} / ${fmt(totalCredit)}`} testId="gl-kpi-mv" />
          <StatTile label="Saldo Akhir" value={fmt(data.end_balance)} accent="primary" testId="gl-kpi-end" />
        </div>
      )}

      <GlassCard className="p-0 overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-muted-foreground">Memuat…</div>
        ) : !data || !data.lines?.length ? (
          <div className="py-16 text-center text-muted-foreground">
            <FileText className="w-10 h-10 mx-auto mb-2 opacity-40" />
            {code ? 'Tidak ada transaksi di periode ini.' : 'Pilih akun untuk melihat buku besar.'}
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-sm">
                <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="py-2 px-2">Tanggal</th>
                  <th className="py-2 px-2">No. Jurnal</th>
                  <th className="py-2 px-2">Deskripsi</th>
                  <th className="py-2 px-2">Sumber</th>
                  <th className="py-2 px-2 text-right">Debit</th>
                  <th className="py-2 px-2 text-right">Credit</th>
                  <th className="py-2 px-2 text-right">Saldo</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-[var(--glass-border)] text-xs font-semibold bg-foreground/5">
                  <td colSpan={6} className="py-1.5 px-2">Saldo Awal</td>
                  <td className="py-1.5 px-2 text-right font-mono">{fmt(data.opening_balance)}</td>
                </tr>
                {data.lines.map((l, i) => (
                  <tr key={i} className="border-b border-[var(--glass-border)] hover:bg-foreground/5">
                    <td className="py-1.5 px-2 text-xs">{l.date}</td>
                    <td className="py-1.5 px-2 font-mono text-xs">{l.je_number}</td>
                    <td className="py-1.5 px-2 text-xs">{l.description || '-'}</td>
                    <td className="py-1.5 px-2 text-[10px] uppercase text-muted-foreground">{l.source}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs text-emerald-300">{l.debit ? fmt(l.debit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs text-sky-300">{l.credit ? fmt(l.credit) : ''}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-xs font-semibold">{fmt(l.balance)}</td>
                  </tr>
                ))}
                <tr className="font-semibold bg-[var(--card-surface)] border-t-2 border-[var(--glass-border)]">
                  <td colSpan={4} className="py-2 px-2 text-right text-xs uppercase">TOTAL MUTASI</td>
                  <td className="py-2 px-2 text-right font-mono text-xs">{fmt(totalDebit)}</td>
                  <td className="py-2 px-2 text-right font-mono text-xs">{fmt(totalCredit)}</td>
                  <td className="py-2 px-2 text-right font-mono text-xs">{fmt(data.end_balance)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
