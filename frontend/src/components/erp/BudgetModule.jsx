import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Plus, Edit2, Trash2, CheckCircle, Lock, Unlock, Upload,
  BarChart2, TrendingUp, TrendingDown, Minus, RefreshCw,
  ChevronDown, ChevronRight, FileText, Download, Eye, AlertTriangle
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import PaginationBar from './PaginationBar';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const STATUS_MAP = {
  draft:    { label: 'Draft',    color: 'bg-secondary text-muted-foreground' },
  approved: { label: 'Approved', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  locked:   { label: 'Terkunci', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
};

const MONTHS = [
  '01','02','03','04','05','06','07','08','09','10','11','12'
];

export default function BudgetModule({ token }) {
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const [view, setView] = useState('list'); // 'list' | 'detail' | 'variance'
  const [budgets, setBudgets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [items, setItems] = useState([]);
  const [variance, setVariance] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState(null);
  const [page, setPage] = useState(1);
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [filterStatus, setFilterStatus] = useState('');

  // Modals
  const [modalBudget, setModalBudget] = useState(false);
  const [modalItem, setModalItem] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [costCenters, setCostCenters] = useState([]);
  const [coa, setCoa] = useState([]);

  // Forms
  const [budgetForm, setBudgetForm] = useState({ name: '', year: new Date().getFullYear(), period_type: 'monthly', cost_center_id: '', department: '', notes: '' });
  const [itemForm, setItemForm] = useState({ account_id: '', month: '', amount_budgeted: '', notes: '' });

  const fetchBudgets = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: p, limit: 20, year: filterYear });
      if (filterStatus) params.set('status', filterStatus);
      const r = await fetch(`/api/rahaza/finance/budgets?${params}`, { headers });
      const data = await r.json();
      if (data.items && data.pagination) {
        setBudgets(data.items); setPagination(data.pagination);
      } else {
        setBudgets(Array.isArray(data) ? data : []);
        setPagination(null);
      }
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterYear, filterStatus]);

  useEffect(() => { setPage(1); fetchBudgets(1); }, [filterYear, filterStatus]); // eslint-disable-line
  useEffect(() => { fetchBudgets(page); }, [page]); // eslint-disable-line

  const fetchMeta = async () => {
    const [ccRes, coaRes] = await Promise.all([
      fetch('/api/rahaza/cost-centers', { headers }),
      fetch('/api/rahaza/coa/accounts?active_only=false', { headers }),
    ]);
    if (ccRes.ok) setCostCenters(await ccRes.json());
    if (coaRes.ok) setCoa(await coaRes.json());
  };

  const openDetail = async (budget) => {
    setSelected(budget);
    setView('detail');
    await fetchItems(budget.id);
    await fetchMeta();
  };

  const fetchItems = async (bid) => {
    const r = await fetch(`/api/rahaza/finance/budgets/${bid}/items`, { headers });
    if (r.ok) setItems(await r.json());
  };

  const fetchVariance = async (bid) => {
    setLoading(true);
    const r = await fetch(`/api/rahaza/finance/budgets/${bid}/variance`, { headers });
    if (r.ok) {
      setVariance(await r.json());
      setView('variance');
    }
    setLoading(false);
  };

  const createBudget = async () => {
    const r = await fetch('/api/rahaza/finance/budgets', {
      method: 'POST', headers, body: JSON.stringify(budgetForm),
    });
    if (r.ok) {
      toast.success('Budget berhasil dibuat');
      setModalBudget(false);
      fetchBudgets(1);
      setBudgetForm({ name: '', year: new Date().getFullYear(), period_type: 'monthly', cost_center_id: '', department: '', notes: '' });
    } else {
      const e = await r.json();
      toast.error(e.detail || 'Gagal membuat budget');
    }
  };

  const deleteBudget = async (bid) => {
    if (!window.confirm('Hapus budget ini?')) return;
    const r = await fetch(`/api/rahaza/finance/budgets/${bid}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Budget dihapus'); fetchBudgets(page); }
    else { const e = await r.json(); toast.error(e.detail || 'Gagal hapus'); }
  };

  const changeStatus = async (bid, action) => {
    const r = await fetch(`/api/rahaza/finance/budgets/${bid}/${action}`, { method: 'POST', headers });
    if (r.ok) {
      toast.success(`Budget berhasil di-${action}`);
      const updated = await fetch(`/api/rahaza/finance/budgets/${bid}`, { headers });
      if (updated.ok) setSelected(await updated.json());
      fetchBudgets(page);
    } else {
      const e = await r.json(); toast.error(e.detail || 'Gagal');
    }
  };

  const addItem = async () => {
    if (!selected) return;
    const r = await fetch(`/api/rahaza/finance/budgets/${selected.id}/items`, {
      method: 'POST', headers,
      body: JSON.stringify({
        ...itemForm,
        amount_budgeted: parseFloat(itemForm.amount_budgeted) || 0,
      }),
    });
    if (r.ok) {
      toast.success('Item berhasil ditambahkan');
      setModalItem(false);
      setItemForm({ account_id: '', month: '', amount_budgeted: '', notes: '' });
      await fetchItems(selected.id);
      const upd = await fetch(`/api/rahaza/finance/budgets/${selected.id}`, { headers });
      if (upd.ok) setSelected(await upd.json());
    } else {
      const e = await r.json(); toast.error(e.detail || 'Gagal');
    }
  };

  const deleteItem = async (iid) => {
    if (!selected) return;
    const r = await fetch(`/api/rahaza/finance/budgets/${selected.id}/items/${iid}`, { method: 'DELETE', headers });
    if (r.ok) { toast.success('Item dihapus'); await fetchItems(selected.id); }
    else { const e = await r.json(); toast.error(e.detail || 'Gagal'); }
  };

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file || !selected) return;
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`/api/rahaza/finance/budgets/${selected.id}/import-excel`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    });
    if (r.ok) {
      const res = await r.json();
      toast.success(`Import berhasil: ${res.imported} item. Dilewati: ${res.skipped?.length || 0}`);
      await fetchItems(selected.id);
    } else { const err = await r.json(); toast.error(err.detail || 'Gagal import'); }
    setImportOpen(false);
    e.target.value = '';
  };

  // ── Group items by month for the detail view
  const itemsByMonth = items.reduce((acc, it) => {
    const m = it.month || '?';
    if (!acc[m]) acc[m] = [];
    acc[m].push(it);
    return acc;
  }, {});

  const fmtRp = formatRupiah;

  if (view === 'variance' && variance) {
    const { budget: vb, rows: vrows, summary } = variance;
    return (
      <div className="space-y-5" data-testid="budget-variance-page">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => { setView('detail'); }}>&larr; Kembali ke Detail</Button>
          <h2 className="text-lg font-semibold">Variance Report — {vb?.name}</h2>
        </div>
        {/* Summary cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Total Budget', value: fmtRp(summary.total_budgeted), icon: <BarChart2 className="w-4 h-4" />, color: 'text-blue-500' },
            { label: 'Total Aktual', value: fmtRp(summary.total_actual), icon: <TrendingUp className="w-4 h-4" />, color: 'text-emerald-500' },
            { label: 'Variance', value: fmtRp(summary.total_variance), icon: summary.total_variance >= 0 ? <TrendingDown className="w-4 h-4" /> : <TrendingUp className="w-4 h-4" />, color: summary.total_variance >= 0 ? 'text-emerald-500' : 'text-red-700 dark:text-red-500' },
            { label: '% Variance', value: `${summary.total_variance_pct}%`, icon: <Minus className="w-4 h-4" />, color: 'text-muted-foreground' },
          ].map(c => (
            <GlassCard key={c.label} className="p-4">
              <div className={`flex items-center gap-1.5 text-xs text-muted-foreground mb-1 ${c.color}`}>{c.icon} {c.label}</div>
              <div className="text-sm font-semibold text-foreground">{c.value}</div>
            </GlassCard>
          ))}
        </div>
        {/* Variance table */}
        <GlassCard className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)] text-xs uppercase text-muted-foreground">
              <tr>{['Bulan','Akun','Budget','Aktual','Variance','%','Status'].map(h => <th key={h} className="px-3 py-2.5 text-left whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-border">
              {vrows.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-muted-foreground">Tidak ada data</td></tr>}
              {vrows.map((r, i) => (
                <tr key={i} className="hover:bg-[var(--glass-bg)]">
                  <td className="px-3 py-2">{r.month}</td>
                  <td className="px-3 py-2">{r.account_code} <span className="text-muted-foreground">{r.account_name}</span></td>
                  <td className="px-3 py-2 text-right">{fmtRp(r.amount_budgeted)}</td>
                  <td className="px-3 py-2 text-right">{fmtRp(r.amount_actual)}</td>
                  <td className={`px-3 py-2 text-right font-medium ${r.variance < 0 ? 'text-red-700 dark:text-red-500' : 'text-emerald-500'}`}>{fmtRp(r.variance)}</td>
                  <td className={`px-3 py-2 text-right ${r.variance < 0 ? 'text-red-700 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>{r.variance_pct}%</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                      r.status === 'over' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                      r.status === 'under' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' :
                      'bg-secondary text-muted-foreground'
                    }`}>{r.status === 'over' ? 'Over Budget' : r.status === 'under' ? 'Under Budget' : 'On Target'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      </div>
    );
  }

  if (view === 'detail' && selected) {
    const st = STATUS_MAP[selected.status] || STATUS_MAP.draft;
    return (
      <div className="space-y-5" data-testid="budget-detail-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setView('list')}>&larr; Daftar Budget</Button>
            <div>
              <h2 className="text-lg font-semibold">{selected.name}</h2>
              <span className={`px-2 py-0.5 rounded-full text-xs ${st.color}`}>{st.label}</span>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            {selected.status === 'draft' && <Button size="sm" onClick={() => changeStatus(selected.id, 'approve')} className="bg-blue-600 hover:bg-blue-700 text-foreground"><CheckCircle className="w-3.5 h-3.5 mr-1" />Approve</Button>}
            {selected.status === 'approved' && <Button size="sm" onClick={() => changeStatus(selected.id, 'lock')} className="bg-green-600 hover:bg-green-700 text-foreground"><Lock className="w-3.5 h-3.5 mr-1" />Lock</Button>}
            {(selected.status === 'approved' || selected.status === 'locked') && <Button size="sm" variant="outline" onClick={() => changeStatus(selected.id, 'reopen')}><Unlock className="w-3.5 h-3.5 mr-1" />Reopen</Button>}
            {selected.status !== 'locked' && <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}><Upload className="w-3.5 h-3.5 mr-1" />Import Excel</Button>}
            {selected.status !== 'locked' && <Button size="sm" onClick={() => setModalItem(true)}><Plus className="w-3.5 h-3.5 mr-1" />Tambah Item</Button>}
            <Button size="sm" variant="outline" onClick={() => fetchVariance(selected.id)} disabled={loading}><BarChart2 className="w-3.5 h-3.5 mr-1" />Variance</Button>
          </div>
        </div>

        {/* Budget header info */}
        <GlassCard className="p-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div><span className="text-muted-foreground">Tahun:</span> <strong>{selected.year}</strong></div>
            <div><span className="text-muted-foreground">Tipe:</span> {selected.period_type}</div>
            <div><span className="text-muted-foreground">Departemen:</span> {selected.department || '-'}</div>
            <div><span className="text-muted-foreground">Total Budget:</span> <strong className="text-emerald-500">{fmtRp(selected.total_budgeted)}</strong></div>
          </div>
        </GlassCard>

        {/* Items grouped by month */}
        {Object.keys(itemsByMonth).sort().map(month => (
          <GlassCard key={month}>
            <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
              <h3 className="font-medium text-sm">{month}</h3>
              <span className="text-xs text-muted-foreground">{fmtRp(itemsByMonth[month].reduce((s, i) => s + Number(i.amount_budgeted || 0), 0))}</span>
            </div>
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground uppercase">
                <tr><th className="px-3 py-2 text-left">Akun</th><th className="px-3 py-2 text-right">Budget</th><th className="px-3 py-2 text-left">Catatan</th><th className="px-3 py-2 w-10"></th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {itemsByMonth[month].map(it => (
                  <tr key={it.id} className="hover:bg-[var(--glass-bg)]">
                    <td className="px-3 py-2">{it.account_code} <span className="text-muted-foreground">{it.account_name}</span></td>
                    <td className="px-3 py-2 text-right font-medium">{fmtRp(it.amount_budgeted)}</td>
                    <td className="px-3 py-2 text-muted-foreground">{it.notes || '-'}</td>
                    <td className="px-3 py-2">
                      {selected.status !== 'locked' && (
                        <button onClick={() => deleteItem(it.id)} className="text-red-700 dark:text-red-400 hover:text-red-600 p-1 rounded"><Trash2 className="w-3.5 h-3.5" /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassCard>
        ))}
        {items.length === 0 && <div className="text-center py-10 text-muted-foreground">Belum ada item. Tambah manual atau import Excel.</div>}

        {/* Import file input hidden */}
        {importOpen && <input type="file" accept=".xlsx,.xls" className="hidden" id="import-budget" onChange={handleImport} />}
        {importOpen && document.getElementById('import-budget') && (() => { document.getElementById('import-budget').click(); setImportOpen(false); return null; })()}

        {/* Add Item Modal */}
        {modalItem && (
          <Modal title="Tambah Item Budget" onClose={() => setModalItem(false)} size="sm">
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Akun (COA) *</label>
                <SmartNativeSelect value={itemForm.account_id} onChange={e => setItemForm(f => ({...f, account_id: e.target.value}))}
                  className="w-full border border-border rounded-md px-2.5 py-1.5 text-sm bg-[var(--card-surface)]">
                  <option value="">-- Pilih Akun --</option>
                  {coa.map(a => <option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Bulan (YYYY-MM) *</label>
                <select value={itemForm.month} onChange={e => setItemForm(f => ({...f, month: e.target.value}))}
                  className="w-full border border-border rounded-md px-2.5 py-1.5 text-sm bg-[var(--card-surface)]">
                  <option value="">-- Pilih Bulan --</option>
                  {MONTHS.map(m => <option key={m} value={`${budgetForm.year || selected.year}-${m}`}>{selected.year}-{m}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Jumlah Budget (Rp) *</label>
                <GlassInput type="number" placeholder="0" value={itemForm.amount_budgeted} onChange={e => setItemForm(f => ({...f, amount_budgeted: e.target.value}))} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Catatan</label>
                <GlassInput placeholder="Opsional" value={itemForm.notes} onChange={e => setItemForm(f => ({...f, notes: e.target.value}))} />
              </div>
              <div className="flex gap-2 pt-1">
                <Button onClick={addItem} className="flex-1">Simpan</Button>
                <Button variant="outline" onClick={() => setModalItem(false)} className="flex-1">Batal</Button>
              </div>
            </div>
          </Modal>
        )}
      </div>
    );
  }

  // ── LIST VIEW
  return (
    <div className="space-y-5" data-testid="budget-list-page">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold">Anggaran (Budget)</h2>
          <p className="text-xs text-muted-foreground">Kelola budget per tahun, departemen, dan pusat biaya</p>
        </div>
        <Button onClick={() => { setModalBudget(true); fetchMeta(); }} data-testid="btn-new-budget">
          <Plus className="w-4 h-4 mr-1.5" /> Buat Budget Baru
        </Button>
      </div>

      {/* Filters */}
      <GlassCard className="p-3">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Tahun:</span>
            <SmartNativeSelect value={filterYear} onChange={e => setFilterYear(+e.target.value)}
              className="border border-border rounded px-2 py-1 text-sm bg-[var(--card-surface)]">
              {[2023,2024,2025,2026,2027].map(y => <option key={y} value={y}>{y}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Status:</span>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
              className="border border-border rounded px-2 py-1 text-sm bg-[var(--card-surface)]">
              <option value="">Semua</option>
              <option value="draft">Draft</option>
              <option value="approved">Approved</option>
              <option value="locked">Terkunci</option>
            </select>
          </div>
          <Button size="sm" variant="ghost" onClick={() => fetchBudgets(1)} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </GlassCard>

      {/* Table */}
      <GlassCard className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--glass-bg)] text-xs uppercase text-muted-foreground">
            <tr>
              {['Nama Budget','Tahun','Tipe','Departemen','Total Budget','Status','Aksi'].map(h => (
                <th key={h} className="px-3 py-3 text-left whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading && <tr><td colSpan={7} className="text-center py-8"><RefreshCw className="w-5 h-5 animate-spin mx-auto text-muted-foreground" /></td></tr>}
            {!loading && budgets.length === 0 && <tr><td colSpan={7} className="text-center py-8 text-muted-foreground">Belum ada budget. Buat yang pertama!</td></tr>}
            {!loading && budgets.map(b => {
              const st = STATUS_MAP[b.status] || STATUS_MAP.draft;
              return (
                <tr key={b.id} className="hover:bg-[var(--glass-bg)]">
                  <td className="px-3 py-2.5 font-medium">{b.name}</td>
                  <td className="px-3 py-2.5">{b.year}</td>
                  <td className="px-3 py-2.5 capitalize">{b.period_type}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.department || '-'}</td>
                  <td className="px-3 py-2.5 font-medium text-emerald-600 dark:text-emerald-400">{fmtRp(b.total_budgeted)}</td>
                  <td className="px-3 py-2.5"><span className={`px-2 py-0.5 rounded-full text-xs ${st.color}`}>{st.label}</span></td>
                  <td className="px-3 py-2.5">
                    <div className="flex gap-1.5">
                      <button onClick={() => openDetail(b)} className="p-1 rounded hover:bg-primary/10" title="Detail"><Eye className="w-3.5 h-3.5 text-primary" /></button>
                      {b.status === 'draft' && <button onClick={() => deleteBudget(b.id)} className="p-1 rounded hover:bg-red-100" title="Hapus"><Trash2 className="w-3.5 h-3.5 text-red-700 dark:text-red-400" /></button>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {pagination && pagination.total_pages > 1 && (
          <div className="px-4 py-3 border-t border-border">
            <PaginationBar pagination={pagination} onPageChange={setPage} />
          </div>
        )}
      </GlassCard>

      {/* Create Budget Modal */}
      {modalBudget && (
        <Modal title="Buat Budget Baru" onClose={() => setModalBudget(false)} size="sm">
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Nama Budget *</label>
              <GlassInput placeholder="mis. Anggaran Operasional 2026" value={budgetForm.name} onChange={e => setBudgetForm(f => ({...f, name: e.target.value}))} data-testid="budget-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Tahun *</label>
                <GlassInput type="number" value={budgetForm.year} onChange={e => setBudgetForm(f => ({...f, year: +e.target.value}))} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Tipe Periode</label>
                <select value={budgetForm.period_type} onChange={e => setBudgetForm(f => ({...f, period_type: e.target.value}))}
                  className="w-full border border-border rounded px-2.5 py-1.5 text-sm bg-[var(--card-surface)]">
                  <option value="monthly">Bulanan</option>
                  <option value="quarterly">Kuartalan</option>
                  <option value="annual">Tahunan</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Departemen</label>
              <GlassInput placeholder="mis. Produksi, Keuangan" value={budgetForm.department} onChange={e => setBudgetForm(f => ({...f, department: e.target.value}))} />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Pusat Biaya</label>
              <SmartNativeSelect value={budgetForm.cost_center_id} onChange={e => setBudgetForm(f => ({...f, cost_center_id: e.target.value}))}
                className="w-full border border-border rounded px-2.5 py-1.5 text-sm bg-[var(--card-surface)]">
                <option value="">-- Pilih (opsional) --</option>
                {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Catatan</label>
              <GlassInput placeholder="Opsional" value={budgetForm.notes} onChange={e => setBudgetForm(f => ({...f, notes: e.target.value}))} />
            </div>
            <div className="flex gap-2 pt-1">
              <Button onClick={createBudget} className="flex-1" data-testid="btn-submit-budget">Buat Budget</Button>
              <Button variant="outline" onClick={() => setModalBudget(false)} className="flex-1">Batal</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
