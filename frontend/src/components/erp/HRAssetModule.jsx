import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Plus, Edit2, Trash2, RefreshCw, Search, Tag,
  UserCheck, ArrowLeftRight, Printer, CheckCircle2, Clock,
  AlertCircle, X, Save, Loader2, QrCode, Filter, Download,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { EmptyState } from './EmptyState';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const asset = (path, opts = {}) => fetch(`${API}/api/dewi/assets${path}`, { cache: 'no-store', ...opts });

const CATEGORIES = ['Laptop/PC','Seragam','Helm/APD','ID Card','Kendaraan','Peralatan','Furnitur','Handphone','Kunci/Akses','Lainnya'];
const CONDITIONS = ['Baik', 'Rusak', 'Hilang'];
const STATUSES   = ['Available', 'Assigned', 'Maintenance', 'Disposed'];

const STATUS_CFG = {
  Available:   { color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300', label: 'Tersedia' },
  Assigned:    { color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300',       label: 'Dipinjam' },
  Maintenance: { color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300',     label: 'Perbaikan' },
  Disposed:    { color: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300',         label: 'Dibuang' },
};

const COND_CFG = {
  Baik:   { color: 'text-emerald-600 dark:text-emerald-400', icon: CheckCircle2 },
  Rusak:  { color: 'text-amber-700 dark:text-amber-400',   icon: AlertCircle  },
  Hilang: { color: 'text-red-700 dark:text-red-400',     icon: X            },
};

const fmtRp = (n) => n ? formatRupiah(n) : '—';

function StatusBadge({ status }) {
  const c = STATUS_CFG[status] || STATUS_CFG.Available;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.color}`}>{c.label}</span>;
}

function CondBadge({ cond }) {
  const c = COND_CFG[cond] || COND_CFG.Baik;
  const Icon = c.icon;
  return <span className={`text-xs flex items-center gap-1 ${c.color}`}><Icon className="w-3 h-3" />{cond}</span>;
}

export default function HRAssetModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [tab, setTab] = useState('assets');

  const [assets, setAssets] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [empSearch, setEmpSearch] = useState('');
  const [selectedEmp, setSelectedEmp] = useState(null);
  const [empAssets, setEmpAssets] = useState([]);
  const [loading, setLoading] = useState(false);

  // Dialogs
  const [assetDialog, setAssetDialog] = useState(null);
  const [assignDialog, setAssignDialog] = useState(null);  // {asset, mode: assign|return}

  const loadAssets = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (filterCat) params.set('category', filterCat);
      if (filterStatus) params.set('status', filterStatus);
      const r = await asset(`?${params}`, { headers });
      const d = await r.json();
      setAssets(d.assets || []);
    } catch (e) {
      if (!e?.message?.includes('already read')) console.error('loadAssets:', e);
    }
  }, [headers, search, filterCat, filterStatus]);

  const loadAssignments = useCallback(async () => {
    try {
      const r = await asset('/assignments?status=active', { headers });
      const d = await r.json();
      setAssignments(d.assignments || []);
    } catch (e) {
      if (!e?.message?.includes('already read')) console.error('loadAssignments:', e);
    }
  }, [headers]);

  const loadEmployees = useCallback(async () => {
    try {
      // FASE 20 — dulu '/api/rahaza/master/employees' (404 senyap). Endpoint yang
      // benar membalas {total, items:[...]} ⇒ `items` wajib dibaca.
      const r = await fetch(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers, cache: 'no-store' });
      const d = await r.json();
      setEmployees(Array.isArray(d) ? d : d.items || d.rows || d.employees || []);
    } catch (e) {
      if (!e?.message?.includes('already read')) console.error('loadEmployees:', e);
    }
  }, [headers]);

  const loadEmpAssets = useCallback(async (empId) => {
    if (!empId) return;
    try {
      const r = await asset(`/employee/${empId}`, { headers });
      const d = await r.json();
      setEmpAssets(d.assignments || []);
    } catch (e) {
      if (!e?.message?.includes('already read')) console.error('loadEmpAssets:', e);
    }
  }, [headers]);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams();
        if (search) params.set('search', search);
        if (filterCat) params.set('category', filterCat);
        if (filterStatus) params.set('status', filterStatus);
        const r = await asset(`?${params}`, { headers, cache: 'no-store' });
        const d = await r.json();
        setAssets(d.assets || []);
      } catch (e) {
        if (!e?.message?.includes('already read')) console.error('loadAssets:', e);
      }
    })();
  }, [headers, search, filterCat, filterStatus]);

  useEffect(() => {
    if (tab !== 'assignments') return;
    (async () => {
      try {
        const r = await asset('/assignments?status=active', { headers, cache: 'no-store' });
        const d = await r.json();
        setAssignments(d.assignments || []);
      } catch (e) {
        if (!e?.message?.includes('already read')) console.error('loadAssignments:', e);
      }
    })();
  }, [tab, headers]);

  useEffect(() => {
    (async () => {
      try {
        // FASE 20 — jalur KEDUA yang memuat karyawan di file ini (selain
        // loadEmployees di atas); dulu juga menembak endpoint yang tak ada.
        const r = await fetch(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers, cache: 'no-store' });
        const d = await r.json();
        setEmployees(Array.isArray(d) ? d : d.items || d.rows || d.employees || []);
      } catch (e) {
        if (!e?.message?.includes('already read')) console.error('loadEmployees:', e);
      }
    })();
  }, [headers]);

  useEffect(() => {
    if (!selectedEmp) return;
    (async () => {
      try {
        const r = await asset(`/employee/${selectedEmp.id}`, { headers, cache: 'no-store' });
        const d = await r.json();
        setEmpAssets(d.assignments || []);
      } catch (e) {
        if (!e?.message?.includes('already read')) console.error('loadEmpAssets:', e);
      }
    })();
  }, [selectedEmp, headers]);

  const handleSaveAsset = async (form) => {
    const isEdit = !!form.asset_id;
    const url = isEdit ? `/${form.asset_id}` : '';
    const method = isEdit ? 'PUT' : 'POST';
    const r = await asset(url, { method, headers, body: JSON.stringify(form) });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success(isEdit ? 'Aset diupdate' : 'Aset ditambahkan');
    setAssetDialog(null);
    loadAssets();
  };

  const handleDeleteAsset = async (assetId) => {
    if (!window.confirm('Hapus aset ini?')) return;
    const r = await asset(`/${assetId}`, { method: 'DELETE', headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal hapus'); return; }
    toast.success('Aset dihapus');
    loadAssets();
  };

  const handleAssign = async (form) => {
    const r = await asset(`/${form.asset_id}/assign`, { method: 'POST', headers, body: JSON.stringify(form) });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success(`Aset ditugaskan ke ${form.employee_name}`);
    setAssignDialog(null);
    loadAssets();
    loadAssignments();
    if (selectedEmp) loadEmpAssets(selectedEmp.id);
  };

  const handleReturn = async (form) => {
    const r = await asset(`/${form.asset_id}/return`, { method: 'POST', headers, body: JSON.stringify(form) });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success('Aset dikembalikan');
    setAssignDialog(null);
    loadAssets();
    loadAssignments();
    if (selectedEmp) loadEmpAssets(selectedEmp.id);
  };

  const handlePrintLabel = (a) => {
    const url = `${API}/api/dewi/assets/${a.asset_id}/label`;
    window.open(`${url}?token=${token}`, '_blank');
  };

  const handlePrintBulk = () => {
    const params = filterCat ? `?category=${encodeURIComponent(filterCat)}` : '';
    window.open(`${API}/api/dewi/assets/labels/bulk${params}`, '_blank');
  };

  const filteredEmps = employees.filter(e =>
    empSearch ? (e.name.toLowerCase().includes(empSearch.toLowerCase()) ||
      e.employee_code.toLowerCase().includes(empSearch.toLowerCase())) : true
  );

  const { page, setPage, totalPages, total, paged } = useClientPagination(assets, 10);
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Package className="w-6 h-6 text-indigo-600 dark:text-indigo-400" /> Aset Karyawan
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Tracking aset perusahaan · {assets.length} aset terdaftar</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { loadAssets(); loadAssignments(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setAssetDialog({})}>
            <Plus className="w-4 h-4 mr-1" /> Tambah Aset
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-3 w-full max-w-md">
          <TabsTrigger value="assets" className="text-xs">Daftar Aset</TabsTrigger>
          <TabsTrigger value="assignments" className="text-xs">Penugasan Aktif</TabsTrigger>
          <TabsTrigger value="by_employee" className="text-xs">Per Karyawan</TabsTrigger>
        </TabsList>

        {/* ── TAB 1: DAFTAR ASET ─────────────────────────────── */}
        <TabsContent value="assets" className="space-y-4 mt-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Cari nama / kode / S/N..." className="pl-9 h-9" />
            </div>
            <Select value={filterCat || 'all'} onValueChange={v => setFilterCat(v === 'all' ? '' : v)}>
              <SelectTrigger className="w-40 h-9"><SelectValue placeholder="Semua Kategori" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Kategori</SelectItem>
                {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filterStatus || 'all'} onValueChange={v => setFilterStatus(v === 'all' ? '' : v)}>
              <SelectTrigger className="w-36 h-9"><SelectValue placeholder="Semua Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                {STATUSES.map(s => <SelectItem key={s} value={s}>{STATUS_CFG[s]?.label || s}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={handlePrintBulk} title="Cetak semua label">
              <Printer className="w-4 h-4 mr-1" /> Cetak Semua Label
            </Button>
          </div>

          {/* Asset table */}
          <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-3">Kode / Nama</th>
                  <th className="text-left px-4 py-3">Kategori</th>
                  <th className="text-left px-4 py-3">Kondisi</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="text-left px-4 py-3">Dipinjam Oleh</th>
                  <th className="text-left px-4 py-3">Harga Beli</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {paged.map(a => (
                  <tr key={a.asset_id} className="hover:bg-foreground/5 group">
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.asset_name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{a.asset_code}</div>
                      {a.serial_number && <div className="text-xs text-muted-foreground">S/N: {a.serial_number}</div>}
                    </td>
                    <td className="px-4 py-3 text-sm">{a.category}</td>
                    <td className="px-4 py-3"><CondBadge cond={a.condition} /></td>
                    <td className="px-4 py-3"><StatusBadge status={a.status} /></td>
                    <td className="px-4 py-3 text-sm">
                      {a.current_assignment
                        ? <div>
                            <div className="font-medium">{a.current_assignment.employee_name}</div>
                            <div className="text-xs text-muted-foreground">{a.current_assignment.assigned_date}</div>
                          </div>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3 text-sm">{fmtRp(a.purchase_price)}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100">
                        <Button size="icon" variant="ghost" className="h-7 w-7" title="Cetak Label"
                          onClick={() => handlePrintLabel(a)} data-testid={`print-label-${a.asset_id}`}>
                          <QrCode className="w-3.5 h-3.5" />
                        </Button>
                        {a.status === 'Available' && (
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-blue-600 dark:text-blue-400" title="Tugaskan"
                            onClick={() => setAssignDialog({ asset: a, mode: 'assign' })}
                            data-testid={`assign-asset-${a.asset_id}`}>
                            <UserCheck className="w-3.5 h-3.5" />
                          </Button>
                        )}
                        {a.status === 'Assigned' && (
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-700 dark:text-amber-400" title="Kembalikan"
                            onClick={() => setAssignDialog({ asset: a, mode: 'return' })}
                            data-testid={`return-asset-${a.asset_id}`}>
                            <ArrowLeftRight className="w-3.5 h-3.5" />
                          </Button>
                        )}
                        <Button size="icon" variant="ghost" className="h-7 w-7" title="Edit"
                          onClick={() => setAssetDialog(a)}>
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400" title="Hapus"
                          onClick={() => handleDeleteAsset(a.asset_id)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {assets.length === 0 && (
                  <tr><td colSpan={7}>
                    <EmptyState icon={Package} title="Belum ada aset terdaftar" description="Tambahkan aset pertama untuk mulai melacak inventaris aset karyawan." action={{ label: 'Tambah Aset', onClick: () => setAssetDialog({}) }} />
                  </td></tr>
                )}
              </tbody>
            </table>
            <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
          </div>
        </TabsContent>

        {/* ── TAB 2: PENUGASAN AKTIF ─────────────────────────── */}
        <TabsContent value="assignments" className="space-y-4 mt-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{assignments.length} aset sedang dipinjam</p>
          </div>
          <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                  <th className="text-left px-4 py-3">Aset</th>
                  <th className="text-left px-4 py-3">Karyawan</th>
                  <th className="text-left px-4 py-3">Tgl Pinjam</th>
                  <th className="text-left px-4 py-3">Tgl Kembali</th>
                  <th className="text-left px-4 py-3">Catatan</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {assignments.map(a => (
                  <tr key={a.assignment_id} className="hover:bg-foreground/5">
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.asset_name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{a.asset_code}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.employee_name}</div>
                      <div className="text-xs text-muted-foreground">{a.employee_code}</div>
                    </td>
                    <td className="px-4 py-3 text-xs">{a.assigned_date}</td>
                    <td className="px-4 py-3 text-xs">
                      {a.expected_return_date
                        ? <span className={new Date(a.expected_return_date) < new Date() ? 'text-red-700 dark:text-red-400' : 'text-muted-foreground'}>
                            {a.expected_return_date}
                          </span>
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{a.notes || '—'}</td>
                    <td className="px-4 py-3">
                      <Button size="sm" variant="outline" className="h-7 text-xs text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-500/30"
                        onClick={() => {
                          const ast = assets.find(x => x.asset_id === a.asset_id) || { asset_id: a.asset_id, asset_name: a.asset_name };
                          setAssignDialog({ asset: ast, mode: 'return' });
                        }}
                        data-testid={`return-assign-${a.assignment_id}`}>
                        <ArrowLeftRight className="w-3 h-3 mr-1" /> Kembalikan
                      </Button>
                    </td>
                  </tr>
                ))}
                {assignments.length === 0 && (
                  <tr><td colSpan={6}>
                    <EmptyState icon={ArrowLeftRight} title="Tidak ada penugasan aktif" description="Tidak ada aset yang sedang dipinjam karyawan saat ini." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </TabsContent>

        {/* ── TAB 3: PER KARYAWAN ────────────────────────────── */}
        <TabsContent value="by_employee" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Employee selector */}
            <div className="space-y-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input value={empSearch} onChange={e => setEmpSearch(e.target.value)}
                  placeholder="Cari karyawan..." className="pl-9 h-9" />
              </div>
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 max-h-80 overflow-y-auto divide-y divide-white/5">
                {filteredEmps.slice(0, 30).map(e => (
                  <button key={e.id}
                    className={`w-full text-left px-3 py-2.5 text-sm hover:bg-foreground/10 transition-colors ${selectedEmp?.id === e.id ? 'bg-indigo-100 dark:bg-indigo-500/10 border-l-2 border-indigo-400' : ''}`}
                    onClick={() => setSelectedEmp(e)}>
                    <div className="font-medium">{e.name}</div>
                    <div className="text-xs text-muted-foreground">{e.employee_code} · {e.job_title}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Employee assets */}
            <div className="md:col-span-2 space-y-3">
              {selectedEmp ? (
                <>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold">{selectedEmp.name}</p>
                      <p className="text-xs text-muted-foreground">{selectedEmp.employee_code} · {selectedEmp.job_title}</p>
                    </div>
                    <span className="text-sm text-muted-foreground">{empAssets.filter(a => a.status === 'active').length} aktif</span>
                  </div>
                  {empAssets.length > 0 ? (
                    <div className="space-y-2">
                      {empAssets.map(a => (
                        <div key={a.assignment_id}
                          className={`rounded-xl border p-3 flex items-center justify-between ${a.status === 'active' ? 'border-indigo-400 dark:border-indigo-500/30 bg-indigo-100 dark:bg-indigo-500/5' : 'border-foreground/10 bg-foreground/5 opacity-60'}`}>
                          <div>
                            <div className="font-medium text-sm">{a.asset_name}</div>
                            <div className="text-xs text-muted-foreground">
                              {a.asset_code} · {a.status === 'active' ? `Dipinjam: ${a.assigned_date}` : `Dikembalikan: ${a.return_date}`}
                            </div>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${a.status === 'active' ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300' : 'bg-muted dark:bg-slate-500/20 text-foreground/70'}`}>
                            {a.status === 'active' ? 'Aktif' : 'Kembali'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState icon={Package} title="Tidak ada aset dipinjam" description="Karyawan ini belum meminjam aset apapun." />
                  )}
                </>
              ) : (
                <EmptyState icon={UserCheck} title="Pilih karyawan" description="Klik nama karyawan di sebelah kiri untuk melihat aset yang dipinjam." />
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── DIALOG: ADD/EDIT ASSET ─────────────────────────── */}
      {assetDialog !== null && (
        <AssetFormDialog initial={assetDialog} employees={employees} onSave={handleSaveAsset} onClose={() => setAssetDialog(null)} />
      )}

      {/* ── DIALOG: ASSIGN / RETURN ──────────────────────────── */}
      {assignDialog !== null && (
        <AssignDialog
          data={assignDialog}
          employees={employees}
          onAssign={handleAssign}
          onReturn={handleReturn}
          onClose={() => setAssignDialog(null)}
        />
      )}
    </div>
  );
}

function AssetFormDialog({ initial, onSave, onClose }) {
  const [form, setForm] = useState({
    asset_code: '', asset_name: '', category: 'Lainnya', serial_number: '',
    purchase_date: '', purchase_price: 0, condition: 'Baik', notes: '',
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{form.asset_id ? 'Edit Aset' : 'Tambah Aset'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Kode Aset</Label>
              <Input value={form.asset_code} onChange={e => setForm(f => ({ ...f, asset_code: e.target.value.toUpperCase() }))}
                placeholder="Contoh: AST-001" />
            </div>
            <div className="space-y-1">
              <Label>Nama Aset <span className="text-red-700 dark:text-red-400">*</span></Label>
              <Input value={form.asset_name} onChange={e => setForm(f => ({ ...f, asset_name: e.target.value }))}
                placeholder="Laptop Lenovo X1" required />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Kategori</Label>
              <Select value={form.category} onValueChange={v => setForm(f => ({ ...f, category: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Kondisi</Label>
              <Select value={form.condition} onValueChange={v => setForm(f => ({ ...f, condition: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{CONDITIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label>Serial Number</Label>
            <Input value={form.serial_number} onChange={e => setForm(f => ({ ...f, serial_number: e.target.value }))}
              placeholder="SN-XXXXXXXX" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Tgl Beli</Label>
              <Input type="date" value={form.purchase_date} onChange={e => setForm(f => ({ ...f, purchase_date: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Harga Beli (Rp)</Label>
              <Input type="number" value={form.purchase_price} min={0}
                onChange={e => setForm(f => ({ ...f, purchase_price: parseFloat(e.target.value) || 0 }))} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Catatan</Label>
            <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} rows={2} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />} Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AssignDialog({ data, employees, onAssign, onReturn, onClose }) {
  const { asset, mode } = data;
  const [form, setForm] = useState({
    asset_id: asset.asset_id,
    employee_id: '',
    employee_name: '',
    assigned_date: new Date().toISOString().split('T')[0],
    expected_return_date: '',
    return_date: new Date().toISOString().split('T')[0],
    condition: 'Baik',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    if (mode === 'assign') await onAssign(form);
    else await onReturn(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{mode === 'assign' ? 'Tugaskan Aset' : 'Kembalikan Aset'}</DialogTitle>
        </DialogHeader>
        <div className="rounded-xl bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-300 dark:border-indigo-500/20 px-3 py-2 mb-2">
          <div className="font-medium text-sm">{asset.asset_name}</div>
          <div className="text-xs text-muted-foreground">{asset.asset_code}</div>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'assign' ? (
            <>
              <div className="space-y-1">
                <Label>Pilih Karyawan <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Select value={form.employee_id} onValueChange={v => {
                  const emp = employees.find(e => e.id === v);
                  setForm(f => ({ ...f, employee_id: v, employee_name: emp?.name || '' }));
                }}>
                  <SelectTrigger><SelectValue placeholder="Pilih karyawan..." /></SelectTrigger>
                  <SelectContent>
                    {employees.map(e => <SelectItem key={e.id} value={e.id}>{e.employee_code} — {e.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Tgl Pinjam</Label>
                  <Input type="date" value={form.assigned_date}
                    onChange={e => setForm(f => ({ ...f, assigned_date: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <Label>Tgl Kembali (opsional)</Label>
                  <Input type="date" value={form.expected_return_date}
                    onChange={e => setForm(f => ({ ...f, expected_return_date: e.target.value }))} />
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Tgl Kembali</Label>
                  <Input type="date" value={form.return_date}
                    onChange={e => setForm(f => ({ ...f, return_date: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <Label>Kondisi</Label>
                  <Select value={form.condition} onValueChange={v => setForm(f => ({ ...f, condition: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{CONDITIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}
          <div className="space-y-1">
            <Label>Catatan</Label>
            <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Opsional..." />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving || (mode === 'assign' && !form.employee_id)}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> :
                mode === 'assign' ? <UserCheck className="w-4 h-4 mr-1" /> : <ArrowLeftRight className="w-4 h-4 mr-1" />}
              {mode === 'assign' ? 'Tugaskan' : 'Kembalikan'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

