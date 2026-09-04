import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, RefreshCw, Receipt, CreditCard, BookOpen } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { DataTable } from './DataTableV2';
import OnwardCTA from './OnwardCTA';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function RahazaExpensesModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [centers, setCenters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [e, c, a] = await Promise.all([
        fetch('/api/rahaza/expenses', { headers }).then(r => r.json()),
        fetch('/api/rahaza/cost-centers', { headers }).then(r => r.json()),
        fetch('/api/rahaza/cash-accounts', { headers }).then(r => r.json()),
      ]);
      setRows(Array.isArray(e) ? e : []); setCenters(Array.isArray(c) ? c : []); setAccounts(Array.isArray(a) ? a : []);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  useEffect(() => { fetchAll(); }, [fetchAll]);

  const create = async (body) => {
    const r = await fetch('/api/rahaza/expenses', { method: 'POST', headers, body: JSON.stringify(body) });
    if (r.ok) { setCreating(false); fetchAll(); }
  };

  const total = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);

  // Kategori unik untuk filter dropdown
  const categoryOptions = useMemo(() => {
    const set = new Set();
    rows.forEach(r => { if (r.category) set.add(r.category); });
    return [...set].sort().map(c => ({ value: c, label: c }));
  }, [rows]);

  return (
    <div className="space-y-5" data-testid="rahaza-expenses-page">
      <PageHeader
        icon={CreditCard}
        eyebrow="Portal Keuangan · CV. Dewi Aditya"
        title="Expenses"
        subtitle="Input biaya operasional dengan tagging cost center untuk analisa HPP."
        actions={
          <>
            <Button variant="ghost" onClick={fetchAll} className="h-9 border border-[var(--glass-border)]"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button onClick={() => setCreating(true)} className="h-9" data-testid="exp-add"><Plus className="w-3.5 h-3.5 mr-1.5" />Tambah</Button>
          </>
        }
      />
      <StatTile label="Total Expense (tampilan saat ini)" value={fmt(total)} accent="danger" />
      <DataTable
        tableId="expenses"
        loading={loading}
        rows={rows}
        searchFields={['date', 'category', 'description', 'cost_center_code', 'cost_center_name']}
        filters={[
          { key: 'category', label: 'Kategori', type: 'select', options: categoryOptions },
          { key: 'cost_center_id', label: 'Cost Center', type: 'select',
            options: centers.map(c => ({ value: c.id, label: `${c.code} · ${c.name}` })) },
          { key: 'date', label: 'Tanggal', type: 'date-range' },
        ]}
        columns={[
          { key: 'date', label: 'Tanggal', sortable: true,
            render: (r, v) => <span className="text-xs">{v}</span> },
          { key: 'category', label: 'Kategori', sortable: true,
            render: (r, v) => <span className="text-xs">{v}</span> },
          { key: 'description', label: 'Deskripsi', sortable: true },
          { key: 'cost_center_code', label: 'Cost Center',
            render: (r) => <span className="text-[11px] text-foreground/60">{r.cost_center_code || '—'} {r.cost_center_name && `· ${r.cost_center_name}`}</span> },
          { key: 'amount', label: 'Jumlah', align: 'right', sortable: true,
            render: (r) => <span className="font-mono text-[hsl(var(--destructive))]">{fmt(r.amount)}</span> },
        ]}
        emptyTitle="Belum ada expense"
        emptyDescription='Klik "Tambah" untuk input biaya operasional.'
        emptyIcon={CreditCard}
        exportFilename={`expenses-${new Date().toISOString().slice(0,10)}.csv`}
      />
      <OnwardCTA
        onNavigate={onNavigate}
        title="Setelah Catat Biaya"
        actions={[
          { module: 'fin-journal-hub', label: 'Lihat Jurnal (GL)', icon: BookOpen, primary: true, hint: 'Cek jurnal akuntansi yang terbentuk dari biaya' },
          { module: 'fin-expense-settlement', label: 'Settlement Klaim', icon: CreditCard, hint: 'Proses pencairan klaim biaya karyawan' },
        ]}
      />
      {creating && <ExpEditor centers={centers} accounts={accounts} onClose={() => setCreating(false)} onSave={create} />}
    </div>
  );
}

function ExpEditor({ centers, accounts, onClose, onSave }) {
  const today = new Date().toISOString().split('T')[0];
  const [s, setS] = useState({ date: today, category: 'operasional', description: '', amount: 0, cost_center_id: '', account_id: '', notes: '' });
  const upd = (k, v) => setS(x => ({ ...x, [k]: v }));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-md w-full" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-foreground mb-4">Tambah Expense</h2>
        <div className="space-y-3">
          <div><label className="text-xs uppercase text-muted-foreground">Tanggal</label><GlassInput type="date" value={s.date} onChange={e => upd('date', e.target.value)} /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Kategori</label><GlassInput value={s.category} onChange={e => upd('category', e.target.value)} placeholder="operasional | sewa | listrik | ..." /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Deskripsi</label><GlassInput value={s.description} onChange={e => upd('description', e.target.value)} data-testid="exp-desc" /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Jumlah</label><GlassInput type="number" min={0} step="1000" value={s.amount} onChange={e => upd('amount', Number(e.target.value))} data-testid="exp-amount" /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Cost Center</label><SmartNativeSelect value={s.cost_center_id} onChange={e => upd('cost_center_id', e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"><option value="">— Tanpa —</option>{centers.map(c => <option key={c.id} value={c.id}>{`${c.code} · ${c.name}`}</option>)}</SmartNativeSelect></div>
          <div><label className="text-xs uppercase text-muted-foreground">Bayar dari Rekening (opsional)</label><SmartNativeSelect value={s.account_id} onChange={e => upd('account_id', e.target.value)} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"><option value="">— Tidak link —</option>{accounts.map(a => <option key={a.id} value={a.id}>{`${a.code} · ${a.name}`}</option>)}</SmartNativeSelect></div>
        </div>
        <div className="flex gap-2 mt-6 justify-end"><Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button><Button onClick={() => onSave(s)} data-testid="exp-save">Simpan</Button></div>
      </GlassCard>
    </div>
  );
}
