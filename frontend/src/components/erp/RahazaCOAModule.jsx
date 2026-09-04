import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, RefreshCw, Edit2, Trash2, BookOpen, Sparkles, Search, FolderTree } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';
import { TypeBadge, CoaTreeView } from './RahazaCOATreeNode';
import ImportExportToolbar from './ImportExportToolbar';

const TYPES = ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'COGS', 'EXPENSE', 'OTHER_INCOME', 'OTHER_EXPENSE'];

function AccountEditor({ initial, onSave, onClose, accounts }) {
  const [form, setForm] = useState(initial || { code: '', name: '', type: 'ASSET', parent_code: '', is_group: false, flags: {} });
  const handle = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const groupAccounts = accounts.filter(a => a.is_group);
  return (
    <GlassCard className="p-5" data-testid="coa-editor">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-foreground">{form.id ? 'Edit Akun' : 'Tambah Akun Baru'}</h3>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground" data-testid="coa-editor-close">×</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Kode Akun *</label>
          <GlassInput value={form.code} onChange={e => handle('code', e.target.value)} disabled={!!form.id} placeholder="1-1101" data-testid="coa-input-code" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Nama *</label>
          <GlassInput value={form.name} onChange={e => handle('name', e.target.value)} placeholder="Kas Kecil" data-testid="coa-input-name" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Tipe *</label>
          <select
            value={form.type}
            onChange={e => handle('type', e.target.value)}
            disabled={!!form.id}
            className="w-full h-9 rounded-[var(--radius-sm)] bg-[var(--card-surface)] border border-[var(--glass-border)] px-2 text-sm text-foreground backdrop-blur-sm"
            data-testid="coa-input-type"
          >
            {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase text-muted-foreground font-semibold">Parent Code</label>
          <SmartNativeSelect
            value={form.parent_code || ''}
            onChange={e => handle('parent_code', e.target.value)}
            className="h-9 text-sm"
            data-testid="coa-input-parent"
          >
            <option value="">— Tidak ada parent —</option>
            {groupAccounts.map(a => <option key={a.code} value={a.code}>{`${a.code} ${a.name}`}</option>)}
          </SmartNativeSelect>
        </div>
        <div className="md:col-span-2">
          <label className="inline-flex items-center gap-2 text-sm text-foreground/80">
            <input type="checkbox" checked={!!form.is_group} onChange={e => handle('is_group', e.target.checked)} data-testid="coa-input-isgroup" />
            Akun Group (header / non-postable)
          </label>
          <p className="text-[11px] text-muted-foreground mt-1">Akun group hanya sebagai header hierarchy, tidak bisa menerima jurnal.</p>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="ghost" onClick={onClose} className="h-9 border border-[var(--glass-border)]" data-testid="coa-editor-cancel">Batal</Button>
        <Button onClick={() => onSave(form)} className="h-9" data-testid="coa-editor-save">Simpan</Button>
      </div>
    </GlassCard>
  );
}

function FlatAccountRow({ acc, onEdit, onDelete }) {
  return (
    <tr className="border-b border-[var(--glass-border)] hover:bg-foreground/5">
      <td className="py-2 px-2 font-mono text-xs">{acc.code}</td>
      <td className="py-2 px-2">
        {acc.name}
        {acc.is_group && <span className="text-[9px] text-muted-foreground italic ml-1">(group)</span>}
      </td>
      <td className="py-2 px-2"><TypeBadge type={acc.type} /></td>
      <td className="py-2 px-2 font-mono text-xs text-muted-foreground">{acc.parent_code || '-'}</td>
      <td className="py-2 px-2 text-xs">{acc.normal_balance}</td>
      <td className="py-2 px-2">
        <span className="text-[10px] text-muted-foreground font-mono">
          {Object.keys(acc.flags || {}).join(', ') || '-'}
        </span>
      </td>
      <td className="py-2 px-2 text-right">
        <button
          onClick={() => onEdit(acc)}
          className="text-primary hover:bg-primary/10 rounded p-1 mr-1"
          data-testid={`coa-row-edit-${acc.code}`}
        >
          <Edit2 className="w-3 h-3" />
        </button>
        <button
          onClick={() => onDelete(acc)}
          className="text-red-300 hover:bg-red-400/10 rounded p-1"
          data-testid={`coa-row-delete-${acc.code}`}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </td>
    </tr>
  );
}

function FlatAccountsTable({ accounts, onEdit, onDelete }) {
  if (accounts.length === 0) {
    return <div className="py-6 text-center text-muted-foreground text-xs">Tidak ada akun cocok pencarian.</div>;
  }
  return (
    <div className="max-h-[600px] overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-[var(--card-surface)] backdrop-blur-sm">
          <tr className="text-left text-[10px] uppercase text-muted-foreground border-b border-[var(--glass-border)]">
            <th className="py-2 px-2">Kode</th>
            <th className="py-2 px-2">Nama</th>
            <th className="py-2 px-2">Tipe</th>
            <th className="py-2 px-2">Parent</th>
            <th className="py-2 px-2">Normal</th>
            <th className="py-2 px-2">Flags</th>
            <th className="py-2 px-2 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map(acc => (
            <FlatAccountRow key={acc.code} acc={acc} onEdit={onEdit} onDelete={onDelete} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TreeView({ tree, onEdit, onDelete }) {
  return <CoaTreeView tree={tree} onEdit={onEdit} onDelete={onDelete} />;
}

export default function RahazaCOAModule({ token }) {
  const [tree, setTree] = useState([]);
  const [flat, setFlat] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [view, setView] = useState('tree');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [t, l] = await Promise.all([
        fetch('/api/rahaza/coa/tree', { headers }).then(r => r.ok ? r.json() : []),
        fetch('/api/rahaza/coa/accounts', { headers }).then(r => r.ok ? r.json() : []),
      ]);
      setTree(t);
      setFlat(l);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  useEffect(() => { fetchData(); }, [fetchData]);

  const doSeed = async () => {
    if (!window.confirm('Seed template CoA garment manufacturing (PSAK)? Akan skip akun yang sudah ada.')) return;
    const r = await fetch('/api/rahaza/coa/seed', { method: 'POST', headers });
    if (r.ok) {
      const j = await r.json();
      alert(`Seed selesai. Inserted: ${j.inserted}, Skipped: ${j.skipped}`);
      fetchData();
    } else {
      const err = await r.json();
      alert('Gagal: ' + (err.detail || 'error'));
    }
  };

  const save = async (body) => {
    const isNew = !body.id;
    const url = isNew ? '/api/rahaza/coa/accounts' : `/api/rahaza/coa/accounts/${body.id}`;
    const method = isNew ? 'POST' : 'PUT';
    const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
    if (r.ok) { setEditing(null); fetchData(); }
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const del = async (acc) => {
    if (!window.confirm(`Hapus/nonaktifkan akun ${acc.code} ${acc.name}?`)) return;
    const r = await fetch(`/api/rahaza/coa/accounts/${acc.id}`, { method: 'DELETE', headers });
    if (r.ok) fetchData();
    else { const e = await r.json(); alert(e.detail || 'Error'); }
  };

  const filtered = flat.filter(a => {
    if (!search) return true;
    const s = search.toLowerCase();
    return a.code.toLowerCase().includes(s) || a.name.toLowerCase().includes(s);
  });

  return (
    <div className="space-y-5" data-testid="rahaza-coa-page">
      <PageHeader
        icon={BookOpen}
        eyebrow="Portal Finance · Accounting Core"
        title="Chart of Accounts (CoA)"
        subtitle="Struktur akun akuntansi PSAK/SAK-ETAP untuk manufaktur garment. Digunakan sebagai pondasi semua jurnal dan laporan keuangan."
        actions={
          <>
            <ImportExportToolbar collectionKey="coa_accounts" label="Chart of Accounts" onImported={fetchData} />
            <Button variant="ghost" onClick={fetchData} className="h-9 border border-[var(--glass-border)]" data-testid="coa-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
            </Button>
            {flat.length === 0 && (
              <Button variant="ghost" onClick={doSeed} className="h-9 border border-[var(--glass-border)] text-violet-300" data-testid="coa-seed">
                <Sparkles className="w-3.5 h-3.5 mr-1.5" />Seed Template PSAK
              </Button>
            )}
            <Button onClick={() => setEditing({ code: '', name: '', type: 'ASSET', parent_code: '', is_group: false })} className="h-9" data-testid="coa-add">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Tambah Akun
            </Button>
          </>
        }
      />

      {editing && <AccountEditor initial={editing} onSave={save} onClose={() => setEditing(null)} accounts={flat} />}

      <GlassCard className="p-4">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <GlassInput
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Cari kode atau nama akun…"
              className="pl-8"
              data-testid="coa-search"
            />
          </div>
          <div className="flex gap-1 rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-[var(--card-surface)] p-0.5">
            <button
              onClick={() => setView('tree')}
              className={view === 'tree' ? 'px-3 py-1 text-xs rounded bg-primary/20 text-primary' : 'px-3 py-1 text-xs rounded text-muted-foreground'}
              data-testid="coa-view-tree"
            >
              <FolderTree className="w-3 h-3 inline mr-1" />Tree
            </button>
            <button
              onClick={() => setView('flat')}
              className={view === 'flat' ? 'px-3 py-1 text-xs rounded bg-primary/20 text-primary' : 'px-3 py-1 text-xs rounded text-muted-foreground'}
              data-testid="coa-view-flat"
            >
              Flat
            </button>
          </div>
          <div className="text-xs text-muted-foreground">
            Total: <span className="font-semibold text-foreground">{flat.length}</span> akun
          </div>
        </div>

        {loading && <div className="py-12 text-center text-muted-foreground">Memuat…</div>}

        {!loading && flat.length === 0 && (
          <div className="py-12 text-center space-y-3">
            <div className="text-muted-foreground">CoA belum ada. Klik "Seed Template PSAK" untuk memulai.</div>
            <Button onClick={doSeed} data-testid="coa-seed-empty">
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />Seed Template PSAK Garment
            </Button>
          </div>
        )}

        {!loading && flat.length > 0 && view === 'tree' && !search && (
          <TreeView tree={tree} onEdit={setEditing} onDelete={del} />
        )}

        {!loading && flat.length > 0 && (view === 'flat' || search) && (
          <FlatAccountsTable accounts={filtered} onEdit={setEditing} onDelete={del} />
        )}
      </GlassCard>
    </div>
  );
}
