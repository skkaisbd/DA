import { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, Edit2, Trash2, Building2, PieChart } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

export default function RahazaCostCentersModule({ token }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/rahaza/cost-centers', { headers });
      if (r.ok) setRows(await r.json());
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  useEffect(() => { fetchRows(); }, [fetchRows]);

  const save = async (body) => {
    setError('');
    const url = body.id ? `/api/rahaza/cost-centers/${body.id}` : '/api/rahaza/cost-centers';
    const method = body.id ? 'PUT' : 'POST';
    const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
    if (!r.ok) setError(`Gagal simpan (HTTP ${r.status})`); else { setEditing(null); fetchRows(); }
  };
  const del = async (id) => {
    if (!window.confirm('Nonaktifkan cost center ini?')) return;
    const r = await fetch(`/api/rahaza/cost-centers/${id}`, { method: 'DELETE', headers });
    if (r.ok) fetchRows();
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(rows, 10);
  return (
    <div className="space-y-5" data-testid="rahaza-cost-centers-page">
      <PageHeader
        icon={PieChart}
        eyebrow="Portal Keuangan · CV. Dewi Aditya"
        title="Cost Centers"
        subtitle="Master cost center untuk alokasi biaya & overhead ke HPP."
        actions={
          <>
            <Button variant="ghost" onClick={fetchRows} className="h-9 border border-[var(--glass-border)]"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang</Button>
            <Button onClick={() => setEditing({ code: '', name: '', category: 'umum', overhead_rate_per_pcs: 0 })} className="h-9" data-testid="cc-add"><Plus className="w-3.5 h-3.5 mr-1.5" />Tambah</Button>
          </>
        }
      />
      {error && <div className="bg-red-400/10 border border-red-300/20 rounded-lg p-3 text-sm text-red-300">{error}</div>}
      {loading ? <div className="flex items-center justify-center h-48"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div> : (
        <GlassCard className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)]"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-3">Kode</th><th className="px-3 py-3">Nama</th><th className="px-3 py-3">Kategori</th><th className="px-3 py-3 text-right">Overhead/pcs</th><th className="px-3 py-3 text-right">Aksi</th></tr></thead>
            <tbody>
              {rows.length === 0 ? <tr><td colSpan={5} className="text-center py-12 text-muted-foreground">Belum ada cost center.</td></tr> : paged.map(r => (
                <tr key={r.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]" data-testid={`cc-row-${r.code}`}>
                  <td className="px-4 py-2 font-mono text-xs text-foreground">{r.code}</td>
                  <td className="px-3 py-2 text-foreground">{r.name}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{r.category}</td>
                  <td className="px-3 py-2 text-right font-mono text-foreground">Rp {Number(r.overhead_rate_per_pcs || 0).toLocaleString('id-ID')}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => setEditing({ ...r })} className="text-xs text-primary hover:underline mr-3"><Edit2 className="w-3 h-3 inline" /></button>
                    <button onClick={() => del(r.id)} className="text-xs text-red-300 hover:underline"><Trash2 className="w-3 h-3 inline" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </GlassCard>
      )}
      {editing && <CCEditor value={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function CCEditor({ value, onClose, onSave }) {
  const [s, setS] = useState(value);
  const upd = (k, v) => setS(x => ({ ...x, [k]: v }));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-md w-full" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-foreground mb-4">{s.id ? 'Edit' : 'Tambah'} Cost Center</h2>
        <div className="space-y-3">
          <div><label className="text-xs uppercase text-muted-foreground">Kode</label><GlassInput value={s.code} onChange={e => upd('code', e.target.value.toUpperCase())} disabled={!!s.id} data-testid="cc-code" /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Nama</label><GlassInput value={s.name} onChange={e => upd('name', e.target.value)} data-testid="cc-name" /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Kategori</label><GlassInput value={s.category} onChange={e => upd('category', e.target.value)} placeholder="produksi | gudang | umum | ..." /></div>
          <div><label className="text-xs uppercase text-muted-foreground">Overhead Rate per Pcs (Rp)</label><GlassInput type="number" min={0} step={100} value={s.overhead_rate_per_pcs || 0} onChange={e => upd('overhead_rate_per_pcs', Number(e.target.value))} data-testid="cc-overhead" /></div>
        </div>
        <div className="flex gap-2 mt-6 justify-end">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]">Batal</Button>
          <Button onClick={() => onSave(s)} data-testid="cc-save">Simpan</Button>
        </div>
      </GlassCard>
    </div>
  );
}
