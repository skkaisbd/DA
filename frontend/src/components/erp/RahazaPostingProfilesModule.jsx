import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { RefreshCw, Save, Sparkles, Settings2, BookOpen, AlertCircle, CheckCircle2 } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';
import ImportExportToolbar from './ImportExportToolbar';

const EVENT_LABELS = {
  ar_invoice: 'AR Invoice — Dr Piutang / Cr Penjualan (+PPN Keluaran)',
  ar_payment: 'AR Payment — Dr Kas / Cr Piutang',
  ap_invoice: 'AP Invoice — Dr Beban/Inventory / Cr Hutang (+PPN Masukan)',
  ap_payment: 'AP Payment — Dr Hutang / Cr Kas',
  expense: 'Expense — Dr Beban / Cr Kas',
  payroll_finalize: 'Payroll Finalize — Dr Gaji Expense / Cr Hutang Gaji (+PPh21 +BPJS)',
  inventory_receive: 'Material Receive — Dr Inventory RM / Cr AP Clearing',
  inventory_issue: 'Material Issue — Dr WIP / Cr Inventory RM',
  inventory_adjust: 'Material Adjust — Dr/Cr Inventory vs Adj Expense',
  cogs_shipment: 'COGS Shipment — Dr COGS / Cr FG Inventory',
};

const ROLE_LABELS = {
  debit_ar: 'Akun Piutang (Dr)',
  credit_revenue: 'Akun Pendapatan (Cr)',
  credit_tax_output: 'Akun PPN Keluaran (Cr)',
  debit_cash_default: 'Akun Kas Default (Dr)',
  credit_cash_default: 'Akun Kas Default (Cr)',
  credit_ar: 'Akun Piutang (Cr)',
  debit_expense_default: 'Akun Beban Default (Dr)',
  debit_inventory_rm: 'Akun Inventory RM (Dr)',
  debit_tax_input: 'Akun PPN Masukan (Dr)',
  credit_ap: 'Akun Hutang (Cr)',
  debit_ap: 'Akun Hutang (Dr)',
  debit_salary_expense: 'Beban Gaji (Dr)',
  credit_salary_payable: 'Hutang Gaji (Cr)',
  credit_tax_pph21: 'Hutang PPh 21 (Cr)',
  credit_bpjs_payable: 'Hutang BPJS (Cr)',
  credit_ap_clearing: 'Hutang Usaha/Clearing (Cr)',
  debit_wip: 'Persediaan WIP (Dr)',
  credit_inventory_rm: 'Inventory RM (Cr)',
  inventory_rm: 'Inventory RM',
  adjustment_expense: 'Adjustment Expense',
  debit_cogs_material: 'COGS Material (Dr)',
  debit_cogs_labor: 'COGS Labor (Dr)',
  debit_cogs_overhead: 'COGS Overhead (Dr)',
  credit_fg_inventory: 'FG Inventory (Cr)',
};

export default function RahazaPostingProfilesModule({ token }) {
  const [profiles, setProfiles] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [edits, setEdits] = useState({}); // { event_type: { role: code, ... } }

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [rp, ra] = await Promise.all([
        fetch('/api/rahaza/posting-profiles', { headers }),
        fetch('/api/rahaza/coa/accounts?active_only=true', { headers }),
      ]);
      if (!rp.ok) { setError(`Gagal memuat posting profiles (HTTP ${rp.status})`); return; }
      if (!ra.ok) { setError(`Gagal memuat CoA (HTTP ${ra.status})`); return; }
      setProfiles(await rp.json());
      setAccounts(await ra.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const seedDefaults = async () => {
    setError(''); setInfo('');
    const r = await fetch('/api/rahaza/posting-profiles/seed', { method: 'POST', headers });
    if (!r.ok) { setError(`Seed gagal (HTTP ${r.status})`); return; }
    const d = await r.json();
    setInfo(`Seed OK: ${d.inserted} baru, ${d.skipped} sudah ada.`);
    fetchData();
  };

  const saveProfile = async (event_type) => {
    setSaving(event_type); setError(''); setInfo('');
    const original = profiles.find(p => p.event_type === event_type) || {};
    const merged = { ...(original.mapping || {}), ...(edits[event_type] || {}) };
    // strip empty codes
    const clean = {};
    Object.entries(merged).forEach(([k, v]) => { if ((v || '').trim()) clean[k] = v.trim(); });
    const r = await fetch(`/api/rahaza/posting-profiles/${event_type}`, {
      method: 'PUT', headers, body: JSON.stringify({ mapping: clean }),
    });
    setSaving('');
    if (!r.ok) {
      const t = await r.text();
      try { const j = JSON.parse(t); setError(`Gagal simpan ${event_type}: ${j.detail || t}`); }
      catch { setError(`Gagal simpan ${event_type}: ${t}`); }
      return;
    }
    setInfo(`Profile “${event_type}” disimpan.`);
    setEdits(e => ({ ...e, [event_type]: undefined }));
    fetchData();
  };

  const handleEdit = (event_type, role, code) => {
    setEdits(e => ({ ...e, [event_type]: { ...(e[event_type] || {}), [role]: code } }));
  };

  const getValue = (event_type, role, fallback) => {
    const ed = edits[event_type] || {};
    return Object.prototype.hasOwnProperty.call(ed, role) ? ed[role] : (fallback || '');
  };

  const leafAccounts = accounts.filter(a => !a.is_group);

  return (
    <div className="space-y-5" data-testid="posting-profiles-page">
      <PageHeader
        icon={Settings2}
        eyebrow="Accounting Core · F2"
        title="Posting Profiles"
        subtitle="Mapping default akun CoA untuk auto-posting jurnal saat transaksi dijalankan (AR/AP/Expense/Payroll/Inventory)."
        actions={
          <>
            <ImportExportToolbar collectionKey="posting_profiles" label="Posting Profiles" onImported={fetchData} />
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="pp-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button variant="ghost" onClick={seedDefaults} className="h-9 border border-[var(--glass-border)]" data-testid="pp-seed"><Sparkles className="w-3.5 h-3.5 mr-1.5" />Seed Default</Button>
          </>
        }
      />

      {error && (
        <GlassCard className="p-3 border-[hsl(var(--destructive))]">
          <div className="flex items-center gap-2 text-sm text-[hsl(var(--destructive))]">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        </GlassCard>
      )}
      {info && (
        <GlassCard className="p-3">
          <div className="flex items-center gap-2 text-sm text-emerald-300">
            <CheckCircle2 className="w-4 h-4" /> {info}
          </div>
        </GlassCard>
      )}

      {loading ? (
        <GlassCard className="p-16 text-center text-muted-foreground">Memuat…</GlassCard>
      ) : profiles.length === 0 ? (
        <GlassCard className="p-12 text-center">
          <BookOpen className="w-10 h-10 mx-auto mb-2 opacity-40" />
          <p className="text-muted-foreground mb-4">Belum ada posting profiles. Jalankan Seed Default untuk memulai.</p>
          <Button onClick={seedDefaults} data-testid="pp-seed-empty"><Sparkles className="w-3.5 h-3.5 mr-1.5" />Seed Default</Button>
        </GlassCard>
      ) : (
        <div className="space-y-4">
          {profiles.map(p => {
            const mapping = p.mapping || {};
            const roles = Object.keys(mapping);
            const hasEdits = !!edits[p.event_type];
            return (
              <GlassCard key={p.event_type} className="p-5" data-testid={`pp-card-${p.event_type}`}>
                <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
                  <div>
                    <h3 className="font-semibold text-foreground uppercase tracking-wide text-sm">{p.event_type}</h3>
                    <p className="text-xs text-muted-foreground mt-1">{EVENT_LABELS[p.event_type] || p.description}</p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => saveProfile(p.event_type)}
                    disabled={!hasEdits || saving === p.event_type}
                    data-testid={`pp-save-${p.event_type}`}
                    className="h-8"
                  >
                    <Save className="w-3.5 h-3.5 mr-1.5" />
                    {saving === p.event_type ? 'Menyimpan…' : 'Simpan'}
                  </Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {roles.map(role => (
                    <div key={role} data-testid={`pp-row-${p.event_type}-${role}`}>
                      <label className="text-[10px] uppercase text-muted-foreground font-semibold">{ROLE_LABELS[role] || role}</label>
                      <SmartNativeSelect
                        value={getValue(p.event_type, role, mapping[role])}
                        onChange={e => handleEdit(p.event_type, role, e.target.value)}
                        className="w-full h-9 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-sm text-foreground backdrop-blur-sm focus:outline-none focus:border-[hsl(var(--primary))]"
                        data-testid={`pp-select-${p.event_type}-${role}`}
                      >
                        <option value="">— Tidak dipetakan —</option>
                        {leafAccounts.map(a => (
                          <option key={a.code} value={a.code}>{`${a.code} — ${a.name}`}</option>
                        ))}
                      </SmartNativeSelect>
                    </div>
                  ))}
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
