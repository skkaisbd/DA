import { useState, useEffect, useCallback } from 'react';
import { Plus, RefreshCw, Edit2, Trash2, FileText, RotateCcw } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;

export default function AccrualsModule({ token }) {
  const [accruals, setAccruals] = useState([]);
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ type: '', period: '' });
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAccruals = useCallback(async () => {
    setLoading(true);
    try {
      let url = '/api/rahaza/finance/accruals';
      const params = [];
      if (filter.type) params.push(`type=${filter.type}`);
      if (filter.period) params.push(`period=${filter.period}`);
      if (params.length) url += '?' + params.join('&');
      const r = await fetch(url, { headers });
      if (r.ok) setAccruals(await r.json());
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat data akrual', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filter]);

  useEffect(() => { fetchAccruals(); }, [fetchAccruals]);

  const save = async (body) => {
    try {
      const url = body.id ? `/api/rahaza/finance/accruals/${body.id}` : '/api/rahaza/finance/accruals';
      const method = body.id ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
      if (r.ok) {
        toast({ title: 'Sukses', description: `Akrual berhasil ${body.id ? 'diupdate' : 'dibuat'}` });
        setEditing(null);
        fetchAccruals();
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal menyimpan', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal menyimpan akrual', variant: 'destructive' });
    }
  };

  const del = async (id) => {
    if (!window.confirm('Hapus entry akrual ini?')) return;
    try {
      const r = await fetch(`/api/rahaza/finance/accruals/${id}`, { method: 'DELETE', headers });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Akrual berhasil dihapus' });
        fetchAccruals();
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal menghapus', variant: 'destructive' });
    }
  };

  const reverse = async (id) => {
    if (!window.confirm('Reverse entry akrual ini?')) return;
    try {
      const r = await fetch(`/api/rahaza/finance/accruals/${id}/reverse`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reversal_date: new Date().toISOString().split('T')[0] })
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Akrual berhasil di-reverse' });
        fetchAccruals();
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal reverse akrual', variant: 'destructive' });
    }
  };

  const totalIncome = accruals.filter(a => a.type === 'income' && a.status === 'active').reduce((s, a) => s + (Number(a.amount) || 0), 0);
  const totalExpense = accruals.filter(a => a.type === 'expense' && a.status === 'active').reduce((s, a) => s + (Number(a.amount) || 0), 0);

  const { page, setPage, totalPages, total, paged } = useClientPagination(accruals, 10);
  return (
    <div className="space-y-5" data-testid="accruals-page">
      <PageHeader
        icon={FileText}
        eyebrow="Portal Finance · Accounting"
        title="Pencatatan Akrual"
        subtitle="Catat pendapatan & beban yang sudah terjadi tapi belum tercatat di periode berjalan."
        actions={
          <>
            <Button variant="ghost" onClick={fetchAccruals} className="h-9 border border-[var(--glass-border)]" data-testid="accrual-refresh">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Muat Ulang
            </Button>
            <Button onClick={() => setEditing({ period: '', type: 'expense', description: '', amount: 0, account_id: '' })} className="h-9" data-testid="accrual-add">
              <Plus className="w-3.5 h-3.5 mr-1.5" />Tambah Akrual
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <StatTile label="Total Akrual Pendapatan" value={fmt(totalIncome)} accent="success" />
        <StatTile label="Total Akrual Beban" value={fmt(totalExpense)} accent="destructive" />
      </div>
      <GlassCard className="p-4">
        <div className="flex gap-3 mb-4">
          <input
            type="month"
            value={filter.period}
            onChange={e => setFilter(f => ({ ...f, period: e.target.value }))}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
            placeholder="Filter Periode"
            data-testid="accrual-filter-period"
          />
          <select
            value={filter.type}
            onChange={e => setFilter(f => ({ ...f, type: e.target.value }))}
            className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
            data-testid="accrual-filter-type"
          >
            <option value="">Semua Tipe</option>
            <option value="income">Pendapatan</option>
            <option value="expense">Beban</option>
          </select>
        </div>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : accruals.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">Belum ada data akrual. Tekan "Tambah Akrual".</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="accrual-table">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <th className="pb-2">Periode</th>
                  <th className="pb-2">Tipe</th>
                  <th className="pb-2">Deskripsi</th>
                  <th className="pb-2 text-right">Jumlah</th>
                  <th className="pb-2">Status</th>
                  <th className="pb-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(a => (
                  <tr key={a.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-border)]/30" data-testid={`accrual-row-${a.id}`}>
                    <td className="py-3">{a.period}</td>
                    <td className="py-3">
                      <span className={`px-2 py-1 rounded text-xs ${a.type === 'income' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
                        {a.type === 'income' ? 'Pendapatan' : 'Beban'}
                      </span>
                    </td>
                    <td className="py-3">{a.description}</td>
                    <td className="py-3 text-right font-mono">{fmt(a.amount)}</td>
                    <td className="py-3">
                      <span className={`px-2 py-1 rounded text-xs ${a.status === 'active' ? 'bg-blue-500/20 text-blue-300' : 'bg-muted/20 text-muted-foreground'}`}>
                        {a.status === 'active' ? 'Aktif' : 'Reversed'}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex gap-1 justify-end">
                        {a.status === 'active' && (
                          <>
                            <button onClick={() => setEditing({ ...a })} className="text-primary hover:bg-primary/10 rounded p-1" data-testid={`accrual-edit-${a.id}`}>
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => reverse(a.id)} className="text-yellow-300 hover:bg-yellow-400/10 rounded p-1" data-testid={`accrual-reverse-${a.id}`}>
                              <RotateCcw className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => del(a.id)} className="text-red-300 hover:bg-red-400/10 rounded p-1" data-testid={`accrual-delete-${a.id}`}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        )}
      </GlassCard>
      {editing && <AccrualEditor value={editing} onClose={() => setEditing(null)} onSave={save} />}
    </div>
  );
}

function AccrualEditor({ value, onClose, onSave }) {
  const [s, setS] = useState(value);
  const upd = (k, v) => setS(x => ({ ...x, [k]: v }));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="accrual-editor">
        <h2 className="text-xl font-bold text-foreground mb-4">{s.id ? 'Edit' : 'Tambah'} Akrual</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs uppercase text-muted-foreground">Periode (YYYY-MM)</label>
            <input
              type="month"
              value={s.period}
              onChange={e => upd('period', e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="accrual-period"
            />
          </div>
          <div>
            <label className="text-xs uppercase text-muted-foreground">Tipe</label>
            <select
              value={s.type}
              onChange={e => upd('type', e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              data-testid="accrual-type"
            >
              <option value="income">Pendapatan</option>
              <option value="expense">Beban</option>
            </select>
          </div>
          <div>
            <label className="text-xs uppercase text-muted-foreground">Deskripsi</label>
            <textarea
              value={s.description}
              onChange={e => upd('description', e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
              rows={3}
              data-testid="accrual-description"
            />
          </div>
          <div>
            <label className="text-xs uppercase text-muted-foreground">Jumlah (Rp)</label>
            <GlassInput
              type="number"
              min={0}
              value={s.amount || 0}
              onChange={e => upd('amount', Number(e.target.value))}
              data-testid="accrual-amount"
            />
          </div>
          <div>
            <label className="text-xs uppercase text-muted-foreground">Account ID (COA) - Opsional</label>
            <GlassInput
              value={s.account_id || ''}
              onChange={e => upd('account_id', e.target.value)}
              placeholder="UUID akun COA"
              data-testid="accrual-account-id"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-6 justify-end">
          <Button variant="ghost" onClick={onClose} className="border border-[var(--glass-border)]" data-testid="accrual-cancel">
            Batal
          </Button>
          <Button onClick={() => onSave(s)} data-testid="accrual-save">
            Simpan
          </Button>
        </div>
      </GlassCard>
    </div>
  );
}
