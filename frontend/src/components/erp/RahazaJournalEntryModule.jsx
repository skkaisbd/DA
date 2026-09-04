import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, RefreshCw, Trash2, BookCheck, FileText, X, Check, Ban, Search } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { IconButton } from './IconButton';
import { formatRupiah } from '@/lib/format';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const fmt = formatRupiah;
const todayISO = () => new Date().toISOString().slice(0, 10);

const STATUS_COLORS = {
  draft: 'text-amber-300 bg-amber-400/10 border-amber-400/25',
  posted: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/25',
  voided: 'text-red-300 bg-red-400/10 border-red-400/25',
};

function StatusBadge({ status }) {
  const cls = STATUS_COLORS[status] || 'text-foreground/70 bg-foreground/5 border-foreground/10';
  return <span className={`text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded border ${cls}`}>{status}</span>;
}

function JournalEditor({ accounts, onSave, onClose, token }) {
  const [form, setForm] = useState({
    date: todayISO(),
    memo: '',
    je_number: '',
    post: false,
    lines: [
      { account_code: '', debit: 0, credit: 0, description: '' },
      { account_code: '', debit: 0, credit: 0, description: '' },
    ],
  });
  // SESI #19 — kebijakan penomoran Jurnal Umum (Otomatis/Manual) dari Administrasi
  // Sistem → Penomoran Dokumen. Jurnal hasil posting otomatis dokumen lain tetap
  // bernomor otomatis; yang diatur di sini adalah jurnal yang diketik orang.
  const numPolicy = useDocNumberPolicy('rahaza_journal_entries.je_number', token);
  const handle = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setLine = (i, k, v) => setForm(f => ({ ...f, lines: f.lines.map((ln, idx) => idx === i ? { ...ln, [k]: v } : ln) }));
  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, { account_code: '', debit: 0, credit: 0, description: '' }] }));
  const removeLine = (i) => setForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));

  const totalD = form.lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalC = form.lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = totalD === totalC && totalD > 0;
  const nomorSiap = numPolicy?.mode !== 'manual' || !!form.je_number.trim();

  const submit = (asDraft) => {
    const body = {
      date: form.date,
      memo: form.memo,
      post: !asDraft,
      ...docNumberPayload(numPolicy, 'je_number', form.je_number),
      lines: form.lines.filter(l => l.account_code).map(l => ({
        account_code: l.account_code,
        debit: Number(l.debit) || 0,
        credit: Number(l.credit) || 0,
        description: l.description || '',
      })),
    };
    onSave(body);
  };

  const postableAccounts = accounts.filter(a => !a.is_group);

  return (
    <GlassCard className="p-5" data-testid="je-editor">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-foreground">Jurnal Baru</h3>
        <IconButton label="Tutup editor" onClick={onClose} className="text-muted-foreground hover:text-foreground p-1" data-testid="je-editor-close"><X className="w-4 h-4" /></IconButton>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div>
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Tanggal *</label>
          <GlassInput type="date" value={form.date} onChange={e => handle('date', e.target.value)} data-testid="je-input-date" />
        </div>
        <div className="md:col-span-2">
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Memo / Deskripsi</label>
          <GlassInput value={form.memo} onChange={e => handle('memo', e.target.value)} placeholder="Mis. Setoran modal awal" data-testid="je-input-memo" />
        </div>
        <div className="md:col-span-3">
          <DocNumberField
            policy={numPolicy}
            value={form.je_number}
            onChange={v => handle('je_number', v)}
            label="Nomor Jurnal"
            testId="je-number"
          />
        </div>
      </div>

      <div className="mb-2">
        <label className="text-[10px] uppercase text-muted-foreground font-semibold">Baris Jurnal (minimal 2, debit=credit)</label>
      </div>
      <div className="space-y-2 mb-4">
        {form.lines.map((ln, i) => (
          <div key={i} className="grid grid-cols-12 gap-2 items-start">
            <div className="col-span-5">
              <SmartNativeSelect
                value={ln.account_code}
                onChange={e => setLine(i, 'account_code', e.target.value)}
                className="w-full h-9 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-sm text-foreground backdrop-blur-sm"
                data-testid={`je-line-${i}-account`}
              >
                <option value="">— Pilih akun —</option>
                {postableAccounts.map(a => <option key={a.code} value={a.code}>{`${a.code} · ${a.name}`}</option>)}
              </SmartNativeSelect>
            </div>
            <div className="col-span-2">
              <GlassInput type="number" value={ln.debit} onChange={e => { setLine(i, 'debit', e.target.value); if (Number(e.target.value) > 0) setLine(i, 'credit', 0); }} placeholder="Debit" data-testid={`je-line-${i}-debit`} />
            </div>
            <div className="col-span-2">
              <GlassInput type="number" value={ln.credit} onChange={e => { setLine(i, 'credit', e.target.value); if (Number(e.target.value) > 0) setLine(i, 'debit', 0); }} placeholder="Credit" data-testid={`je-line-${i}-credit`} />
            </div>
            <div className="col-span-2">
              <GlassInput value={ln.description} onChange={e => setLine(i, 'description', e.target.value)} placeholder="Uraian" data-testid={`je-line-${i}-desc`} />
            </div>
            <div className="col-span-1 flex items-center justify-center">
              {form.lines.length > 2 && (
                <button onClick={() => removeLine(i)} className="text-red-300 hover:bg-red-400/10 rounded p-1.5" data-testid={`je-line-${i}-remove`}><Trash2 className="w-3.5 h-3.5" /></button>
              )}
            </div>
          </div>
        ))}
      </div>
      <Button variant="ghost" onClick={addLine} className="h-8 text-xs border border-dashed border-[var(--glass-border)]" data-testid="je-add-line"><Plus className="w-3 h-3 mr-1" />Tambah Baris</Button>

      <div className="mt-5 flex items-center justify-between flex-wrap gap-3 pt-4 border-t border-[var(--glass-border)]">
        <div className="flex gap-4 text-sm">
          <div><span className="text-muted-foreground text-xs">Total Debit: </span><span className="font-mono font-semibold">{fmt(totalD)}</span></div>
          <div><span className="text-muted-foreground text-xs">Total Credit: </span><span className="font-mono font-semibold">{fmt(totalC)}</span></div>
          <div className={`font-semibold ${balanced ? 'text-emerald-300' : 'text-red-300'}`} data-testid="je-balanced-indicator">
            {balanced ? 'Seimbang ✓' : 'Tidak Seimbang (Δ ' + fmt(Math.abs(totalD - totalC)) + ')'}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="h-9 border border-[var(--glass-border)]" data-testid="je-editor-cancel">Batal</Button>
          <Button variant="ghost" onClick={() => submit(true)} className="h-9 border border-[var(--glass-border)]" disabled={!balanced || !nomorSiap} data-testid="je-save-draft">Simpan Draft</Button>
          <Button onClick={() => submit(false)} className="h-9" disabled={!balanced || !nomorSiap} data-testid="je-save-post">Simpan & Post</Button>
        </div>
      </div>
    </GlassCard>
  );
}

function JournalDetail({ je, onPost, onVoid, onDelete, onClose }) {
  return (
    <GlassCard className="p-5" data-testid="je-detail">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-foreground font-mono">{je.je_number}</h3>
          <div className="text-xs text-muted-foreground mt-0.5">{je.date} · {je.memo || '—'}</div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={je.status} />
          <IconButton label="Tutup detail jurnal" onClick={onClose} className="text-muted-foreground hover:text-foreground p-1" data-testid="je-detail-close"><X className="w-4 h-4" /></IconButton>
        </div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
            <th className="py-2 pr-2">Akun</th>
            <th className="py-2 pr-2">Deskripsi</th>
            <th className="py-2 pr-2 text-right">Debit</th>
            <th className="py-2 pr-2 text-right">Credit</th>
          </tr>
        </thead>
        <tbody>
          {je.lines.map(ln => (
            <tr key={ln.line_id} className="border-b border-[var(--glass-border)]">
              <td className="py-2 pr-2"><span className="font-mono text-xs text-muted-foreground">{ln.account_code}</span> {ln.account_name}</td>
              <td className="py-2 pr-2 text-xs text-foreground/70">{ln.description || '-'}</td>
              <td className="py-2 pr-2 text-right font-mono text-xs">{ln.debit ? fmt(ln.debit) : ''}</td>
              <td className="py-2 pr-2 text-right font-mono text-xs">{ln.credit ? fmt(ln.credit) : ''}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td colSpan={2} className="py-2 pr-2 text-right text-xs">TOTAL</td>
            <td className="py-2 pr-2 text-right font-mono">{fmt(je.total_debit)}</td>
            <td className="py-2 pr-2 text-right font-mono">{fmt(je.total_credit)}</td>
          </tr>
        </tbody>
      </table>
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-[var(--glass-border)]">
        <div className="text-[11px] text-muted-foreground">
          Dibuat oleh <span className="text-foreground/80">{je.created_by_name || '-'}</span> · Sumber: {je.source_module}
          {je.voided_at && <span className="ml-2 text-red-300">· Voided</span>}
        </div>
        <div className="flex gap-2">
          {je.status === 'draft' && (
            <>
              <Button variant="ghost" onClick={() => onDelete(je)} className="h-8 text-xs border border-red-400/25 text-red-300" data-testid="je-delete"><Trash2 className="w-3 h-3 mr-1" />Hapus Draft</Button>
              <Button onClick={() => onPost(je)} className="h-8 text-xs" data-testid="je-post"><Check className="w-3 h-3 mr-1" />Post Jurnal</Button>
            </>
          )}
          {je.status === 'posted' && (
            <Button variant="ghost" onClick={() => onVoid(je)} className="h-8 text-xs border border-red-400/25 text-red-300" data-testid="je-void"><Ban className="w-3 h-3 mr-1" />Void</Button>
          )}
        </div>
      </div>
    </GlassCard>
  );
}

export default function RahazaJournalEntryModule({ token }) {
  const [journals, setJournals] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterFrom, setFilterFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); });
  const [filterTo, setFilterTo] = useState(todayISO());
  const [search, setSearch] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ from: filterFrom, to: filterTo, limit: '500' });
      if (filterStatus) params.set('status', filterStatus);
      const [j, a] = await Promise.all([
        fetch(`/api/rahaza/journals?${params}`, { headers }).then(r => r.ok ? r.json() : []),
        fetch('/api/rahaza/coa/accounts', { headers }).then(r => r.ok ? r.json() : []),
      ]);
      setJournals(j); setAccounts(a);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterFrom, filterTo, filterStatus]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const save = async (body) => {
    const r = await fetch('/api/rahaza/journals', { method: 'POST', headers, body: JSON.stringify(body) });
    if (r.ok) { setEditing(null); fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const postJE = async (je) => {
    if (!window.confirm(`Post jurnal ${je.je_number}? Setelah di-post, hanya bisa di-void.`)) return;
    const r = await fetch(`/api/rahaza/journals/${je.id}/post`, { method: 'POST', headers });
    if (r.ok) { setDetailId(null); fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const voidJE = async (je) => {
    const reason = window.prompt(`Alasan void jurnal ${je.je_number}?`);
    if (reason === null) return;
    const r = await fetch(`/api/rahaza/journals/${je.id}/void`, { method: 'POST', headers, body: JSON.stringify({ reason }) });
    if (r.ok) { setDetailId(null); fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const delDraft = async (je) => {
    if (!window.confirm(`Hapus draft ${je.je_number}?`)) return;
    const r = await fetch(`/api/rahaza/journals/${je.id}`, { method: 'DELETE', headers });
    if (r.ok) { setDetailId(null); fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const filtered = journals.filter(j => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (j.je_number || '').toLowerCase().includes(s) || (j.memo || '').toLowerCase().includes(s);
  });

  const detailJE = detailId ? journals.find(j => j.id === detailId) : null;
  const kpi = {
    total: journals.length,
    posted: journals.filter(j => j.status === 'posted').length,
    draft: journals.filter(j => j.status === 'draft').length,
    voided: journals.filter(j => j.status === 'voided').length,
  };

  return (
    <div className="space-y-5" data-testid="rahaza-je-page">
      <PageHeader
        icon={BookCheck}
        eyebrow="Portal Finance · Accounting Core"
        title="Jurnal Umum (Manual Journal Entry)"
        subtitle="Buat jurnal manual dengan double-entry. Validasi otomatis: total debit = total credit, akun harus leaf (non-group), dan periode tidak dikunci."
        actions={
          <>
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="je-refresh"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button onClick={() => setEditing({})} className="h-9" disabled={accounts.length === 0} data-testid="je-add"><Plus className="w-3.5 h-3.5 mr-1.5" />Jurnal Baru</Button>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Total Jurnal" value={kpi.total} testId="je-kpi-total" />
        <StatTile label="Posted" value={kpi.posted} accent="success" testId="je-kpi-posted" />
        <StatTile label="Draft" value={kpi.draft} accent="warning" testId="je-kpi-draft" />
        <StatTile label="Voided" value={kpi.voided} accent="danger" testId="je-kpi-voided" />
      </div>

      {editing && <JournalEditor accounts={accounts} onSave={save} onClose={() => setEditing(null)} token={token} />}
      {detailJE && <JournalDetail je={detailJE} onPost={postJE} onVoid={voidJE} onDelete={delDraft} onClose={() => setDetailId(null)} />}

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dari</span>
            <GlassInput type="date" value={filterFrom} onChange={e => setFilterFrom(e.target.value)} className="h-8 w-36" data-testid="je-filter-from" />
            <span className="text-xs text-muted-foreground">s/d</span>
            <GlassInput type="date" value={filterTo} onChange={e => setFilterTo(e.target.value)} className="h-8 w-36" data-testid="je-filter-to" />
          </div>
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            className="h-8 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-xs text-foreground"
            data-testid="je-filter-status"
          >
            <option value="">Semua Status</option>
            <option value="draft">Draft</option>
            <option value="posted">Posted</option>
            <option value="voided">Voided</option>
          </select>
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <GlassInput value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari nomor jurnal / memo…" className="pl-8 h-8" data-testid="je-search" />
          </div>
        </div>
        {loading ? (
          <div className="py-12 text-center text-muted-foreground">Memuat…</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            <FileText className="w-10 h-10 mx-auto mb-2 opacity-40" />
            Belum ada jurnal di periode ini.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
                <th className="py-2 px-2">No. Jurnal</th>
                <th className="py-2 px-2">Tanggal</th>
                <th className="py-2 px-2">Memo</th>
                <th className="py-2 px-2">Sumber</th>
                <th className="py-2 px-2">Status</th>
                <th className="py-2 px-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(j => (
                <tr
                  key={j.id}
                  onClick={() => setDetailId(j.id)}
                  className="border-b border-[var(--glass-border)] hover:bg-foreground/5 cursor-pointer"
                  data-testid={`je-row-${j.je_number}`}
                >
                  <td className="py-2 px-2 font-mono text-xs">{j.je_number}</td>
                  <td className="py-2 px-2 text-xs">{j.date}</td>
                  <td className="py-2 px-2 text-xs">{j.memo || '-'}</td>
                  <td className="py-2 px-2"><span className="text-[10px] uppercase text-muted-foreground">{j.source_module}</span></td>
                  <td className="py-2 px-2"><StatusBadge status={j.status} /></td>
                  <td className="py-2 px-2 text-right font-mono text-xs">{fmt(j.total_debit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
