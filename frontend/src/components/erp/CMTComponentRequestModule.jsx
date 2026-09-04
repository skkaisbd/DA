import { useState, useEffect, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Scissors, Plus, Trash2, Eye, Search, CheckCircle2, XCircle,
  Truck, Clock, AlertTriangle, PackageOpen, Layers, Send
} from 'lucide-react';
import { toast } from '../ui/sonner';
import MasterProductSelect from './pickers/MasterProductSelect';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_CONF = {
  pending:   { label: 'Pending',   cls: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30',     Icon: Clock },
  cutting:   { label: 'Diproses',  cls: 'bg-sky-100 dark:bg-sky-500/15 text-sky-500 border-sky-400 dark:border-sky-500/30',          Icon: Scissors },
  ready:     { label: 'Siap Kirim',cls: 'bg-violet-100 dark:bg-violet-500/15 text-violet-500 border-violet-400 dark:border-violet-500/30', Icon: PackageOpen },
  delivered: { label: 'Terkirim',  cls: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border-emerald-400 dark:border-emerald-500/30', Icon: Truck },
  rejected:  { label: 'Ditolak',   cls: 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30',          Icon: XCircle },
  cancelled: { label: 'Batal',     cls: 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',       Icon: XCircle },
};

const TYPE_CONF = {
  component: { label: 'Komponen', cls: 'bg-sky-100 dark:bg-sky-500/15 text-sky-500 border-sky-400 dark:border-sky-500/30' },
  accessory: { label: 'Aksesoris', cls: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30' },
};

const NEXT_STATUS = {
  pending:  { value: 'cutting',   label: 'Mulai Proses', cls: 'text-sky-600 dark:text-sky-400 hover:bg-sky-100 dark:bg-sky-500/10', Icon: Scissors },
  cutting:  { value: 'ready',     label: 'Tandai Siap',  cls: 'text-violet-600 dark:text-violet-400 hover:bg-violet-100 dark:bg-violet-500/10', Icon: PackageOpen },
  ready:    { value: 'delivered', label: 'Tandai Kirim', cls: 'text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10', Icon: Truck },
};

const emptyItem = () => ({ component_type: '', size: '', color: '', qty: 1, unit: 'pcs', notes: '' });

const emptyForm = {
  request_type: 'component',
  cmt_partner_name: '',
  cmt_partner_id: '',
  work_order_code: '',
  work_order_id: '',
  // F14b — identitas produk dari MASTER (`rahaza_models`), bukan ketikan.
  model_id: '',
  model_code: '',
  product_name: '',
  items: [emptyItem()],
  urgent: false,
  needed_by_date: '',
  notes: '',
};

export default function CMTComponentRequestModule({ token }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };

  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [actionModal, setActionModal] = useState(null); // { id, target_status, notes, delivery_order_number }
  const [delId, setDelId] = useState(null);
  // SESI #27 — kebijakan penomoran (Otomatis/Manual). `TIPE` ikut jenis request supaya
  // pratinjau nomornya nomor yang BENAR-BENAR akan lahir, bukan contoh.
  const numPolicy = useDocNumberPolicy(
    'dewi_cmt_component_requests.request_code', token,
    { TIPE: form.request_type === 'accessory' ? 'REQ-AKS-CMT' : 'REQ-CMP' });
  const [reqCode, setReqCode] = useState('');

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const updateItem = (idx, field, val) => {
    setForm(p => {
      const items = [...p.items];
      items[idx] = { ...items[idx], [field]: val };
      return { ...p, items };
    });
  };

  const addItemRow = () => setForm(p => ({ ...p, items: [...p.items, emptyItem()] }));
  const removeItemRow = (idx) => setForm(p => p.items.length > 1 ? ({ ...p, items: p.items.filter((_, i) => i !== idx) }) : p);

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStatus) qs.set('status', filterStatus);
      if (filterType) qs.set('request_type', filterType);
      if (search) qs.set('search', search);
      const res = await fetch(`${API}/api/dewi/cmt-component-requests?${qs}`, { headers: h });
      setRequests(await res.json());
    } catch { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/cmt-component-requests/stats/summary`, { headers: h });
      if (res.ok) setStats(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchRequests(); }, [filterStatus, filterType]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fetchStats(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openNew = () => {
    setForm({ ...emptyForm, items: [emptyItem()] });
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (r) => {
    setForm({
      request_type: r.request_type || 'component',
      cmt_partner_name: r.cmt_partner_name || '',
      cmt_partner_id: r.cmt_partner_id || '',
      work_order_code: r.work_order_code || '',
      work_order_id: r.work_order_id || '',
      model_id: r.model_id || '',
      model_code: r.model_code || '',
      product_name: r.product_name || '',
      items: (r.items && r.items.length > 0) ? r.items : [emptyItem()],
      urgent: !!r.urgent,
      needed_by_date: r.needed_by_date || '',
      notes: r.notes || '',
    });
    setEditing(r.id);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.cmt_partner_name?.trim()) return toast.error('Nama CMT partner wajib diisi');
    const validItems = form.items.filter(it => it.component_type?.trim() && Number(it.qty) > 0);
    if (validItems.length === 0) return toast.error('Minimal 1 item komponen valid');

    const payload = {
      ...form,
      items: validItems.map(it => ({
        component_type: it.component_type,
        size: it.size || '',
        color: it.color || '',
        qty: Number(it.qty) || 0,
        unit: it.unit || 'pcs',
        notes: it.notes || '',
      })),
    };
    try {
      const url = editing ? `${API}/api/dewi/cmt-component-requests/${editing}` : `${API}/api/dewi/cmt-component-requests`;
      const method = editing ? 'PUT' : 'POST';
      const body = editing ? payload
        : { ...payload, ...docNumberPayload(numPolicy, 'request_code', reqCode) };
      const res = await fetch(url, { method, headers: h, body: JSON.stringify(body) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal menyimpan');
      }
      toast.success(editing ? 'Request diperbarui' : 'Request CMT dibuat');
      setShowForm(false);
      fetchRequests();
      fetchStats();
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan');
    }
  };

  const handleSetStatus = async () => {
    if (!actionModal) return;
    const { id, target_status, notes, delivery_order_number, reason } = actionModal;
    try {
      const body = { status: target_status };
      if (target_status === 'delivered' && delivery_order_number) {
        body.delivery_order_number = delivery_order_number;
      }
      if (target_status === 'rejected') {
        if (!reason?.trim()) return toast.error('Alasan reject wajib diisi');
        body.reason = reason;
      }
      if (notes) body.notes = notes;

      const res = await fetch(`${API}/api/dewi/cmt-component-requests/${id}/set-status`, {
        method: 'POST', headers: h, body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal');
      }
      toast.success(`Status diubah ke ${STATUS_CONF[target_status]?.label || target_status}`);
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch (e) {
      toast.error(e.message || 'Gagal update status');
    }
  };

  const handleDelete = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/cmt-component-requests/${delId}`, { method: 'DELETE', headers: h });
      if (!res.ok) throw new Error();
      toast.success('Request dihapus');
      setDelId(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal menghapus'); }
  };

  const filtered = useMemo(() => requests.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.request_code || '').toLowerCase().includes(q)
      || (r.cmt_partner_name || '').toLowerCase().includes(q)
      || (r.work_order_code || '').toLowerCase().includes(q)
      || (r.product_name || '').toLowerCase().includes(q);
  }), [requests, search]);

  const formatDate = (iso) => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  };

  return (
    <div className="p-6 space-y-5" data-testid="cmt-component-request-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Scissors className="w-5 h-5 text-sky-500" /> CMT Kekurangan Komponen
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            Permintaan komponen/aksesoris dari CMT partner ke Admin Packing & SPV Cutting
          </p>
        </div>
        <Button onClick={openNew} className="gap-2" data-testid="cmt-req-add-btn">
          <Plus className="w-4 h-4" /> Request Baru
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3" data-testid="cmt-req-stats">
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50">Total</div>
            <div className="text-2xl font-bold text-foreground mt-1">{stats.total}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Clock className="w-3 h-3" /> Pending</div>
            <div className="text-2xl font-bold text-amber-700 dark:text-amber-500 mt-1">{stats.pending}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Scissors className="w-3 h-3" /> Diproses</div>
            <div className="text-2xl font-bold text-sky-500 mt-1">{stats.cutting}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><PackageOpen className="w-3 h-3" /> Siap</div>
            <div className="text-2xl font-bold text-violet-500 mt-1">{stats.ready}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Truck className="w-3 h-3" /> Terkirim</div>
            <div className="text-2xl font-bold text-emerald-500 mt-1">{stats.delivered}</div>
          </GlassCard>
          <GlassCard className="p-3 border-red-400 dark:border-red-500/30">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><AlertTriangle className="w-3 h-3 text-red-700 dark:text-red-500" /> Urgent</div>
            <div className="text-2xl font-bold text-red-700 dark:text-red-500 mt-1" data-testid="cmt-req-stats-urgent">{stats.urgent_pending}</div>
          </GlassCard>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchRequests()}
            placeholder="Cari kode / CMT / WO / produk..." className="pl-9"
            data-testid="cmt-req-search-input" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          data-testid="cmt-req-filter-type"
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[150px]">
          <option value="">Semua Tipe</option>
          <option value="component">Komponen</option>
          <option value="accessory">Aksesoris</option>
        </select>
        <SmartNativeSelect value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          data-testid="cmt-req-filter-status"
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[150px]">
          <option value="">Semua Status</option>
          {Object.entries(STATUS_CONF).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </SmartNativeSelect>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-sky-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Scissors className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada request komponen.</p>
          <Button variant="outline" className="mt-3" onClick={openNew}>+ Buat Request Pertama</Button>
        </GlassCard>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode', 'CMT/WO', 'Tipe', 'Items', 'Butuh Tgl', 'Status', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => {
                const sc = STATUS_CONF[r.status] || STATUS_CONF.pending;
                const tc = TYPE_CONF[r.request_type] || TYPE_CONF.component;
                const SIcon = sc.Icon;
                const next = NEXT_STATUS[r.status];
                return (
                  <tr key={r.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs font-semibold text-foreground">{r.request_code}</div>
                      {r.urgent && (
                        <span className="inline-flex items-center gap-1 text-[10px] mt-0.5 px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border border-red-400 dark:border-red-500/30">
                          <AlertTriangle className="w-2.5 h-2.5" /> URGENT
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground text-sm">{r.cmt_partner_name || '—'}</div>
                      <div className="text-xs text-foreground/40 font-mono">{r.work_order_code || ''}</div>
                      {r.product_name && <div className="text-xs text-foreground/50">{r.product_name}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${tc.cls}`}>
                        {tc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground/70 text-xs">
                      {(r.items || []).length} item
                      {(r.items || []).length > 0 && (
                        <div className="text-foreground/40 max-w-[180px] truncate" title={(r.items || []).map(i => i.component_type).join(', ')}>
                          {(r.items || []).map(i => i.component_type).filter(Boolean).slice(0, 3).join(', ')}
                          {(r.items || []).length > 3 && '...'}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground/60 text-xs">{r.needed_by_date ? formatDate(r.needed_by_date) : '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>
                        <SIcon className="w-3 h-3" /> {sc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        <Button variant="ghost" size="sm" onClick={() => setDetail(r)}
                          className="h-7 w-7 p-0" data-testid={`cmt-req-detail-${r.id}`}>
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        {next && (
                          <Button variant="ghost" size="sm"
                            onClick={() => setActionModal({
                              id: r.id, target_status: next.value, notes: '',
                              delivery_order_number: '',
                            })}
                            className={`h-7 px-2 text-xs ${next.cls}`}
                            data-testid={`cmt-req-${r.id}-to-${next.value}`}>
                            <next.Icon className="w-3.5 h-3.5 mr-1" /> {next.label}
                          </Button>
                        )}
                        {(r.status === 'pending' || r.status === 'cutting') && (
                          <Button variant="ghost" size="sm"
                            onClick={() => setActionModal({
                              id: r.id, target_status: 'rejected', reason: '',
                            })}
                            className="h-7 px-2 text-xs text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                            data-testid={`cmt-req-${r.id}-to-rejected`}>
                            <XCircle className="w-3.5 h-3.5 mr-1" /> Tolak
                          </Button>
                        )}
                        {r.status === 'pending' && (
                          <Button variant="ghost" size="sm" onClick={() => openEdit(r)}
                            className="h-7 w-7 p-0"
                            data-testid={`cmt-req-edit-${r.id}`}>
                            <Layers className="w-3.5 h-3.5" />
                          </Button>
                        )}
                        {(r.status === 'pending' || r.status === 'rejected' || r.status === 'cancelled') && (
                          <Button variant="ghost" size="sm" onClick={() => setDelId(r.id)}
                            className="h-7 w-7 p-0 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                            data-testid={`cmt-req-delete-${r.id}`}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Form Modal */}
      {showForm && (
        <Modal onClose={() => setShowForm(false)}
          title={editing ? 'Edit Request CMT' : 'Buat Request Komponen CMT'} size="xl">
          <div className="space-y-4">
            <div>
              <Label>Tipe Request</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {Object.entries(TYPE_CONF).map(([k, v]) => (
                  <button key={k} type="button"
                    onClick={() => f('request_type', k)}
                    data-testid={`cmt-form-type-${k}`}
                    className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg border transition-all text-sm font-medium ${
                      form.request_type === k
                        ? `${v.cls} border-current`
                        : 'border-foreground/10 hover:border-foreground/20 text-foreground/60'
                    }`}>
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>CMT Partner <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Input className="mt-1" value={form.cmt_partner_name}
                  onChange={e => f('cmt_partner_name', e.target.value)}
                  placeholder="Nama CMT partner / vendor"
                  data-testid="cmt-form-partner" />
              </div>
              <div>
                <Label>Work Order</Label>
                <Input className="mt-1" value={form.work_order_code}
                  onChange={e => f('work_order_code', e.target.value)}
                  placeholder="WO-2024-001"
                  data-testid="cmt-form-wo" />
              </div>
            </div>
            <div>
              {/* F14b — produk yang komponennya diminta ke vendor CMT adalah
                  produk DA yang ada di master. Dulu diketik bebas ⇒ satu
                  permintaan menyebut "Kemeja Pria Lengan Panjang", permintaan
                  berikutnya "Kemeja Pria LP", dan rekap komponen per produk
                  memecahnya jadi dua produk berbeda. */}
              <MasterProductSelect
                token={token}
                value={form.model_id}
                label="Produk (dari Master Produk)"
                required={false}
                testId="cmt-product-select"
                onChange={(m) => setForm(p => ({
                  ...p,
                  model_id: m?.model_id || '',
                  model_code: m?.code || '',
                  product_name: m?.name || '',
                }))}
                helpText="Kosongkan hanya kalau permintaan ini memang belum menempel pada satu produk master."
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>{form.request_type === 'accessory' ? 'Daftar Aksesoris' : 'Daftar Komponen'}</Label>
                <Button type="button" variant="outline" size="sm" onClick={addItemRow}
                  className="gap-1.5" data-testid="cmt-form-add-row">
                  <Plus className="w-3.5 h-3.5" /> Tambah Baris
                </Button>
              </div>
              <div className="space-y-2">
                {form.items.map((it, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-start" data-testid={`cmt-form-row-${idx}`}>
                    <Input className="col-span-3"
                      placeholder={form.request_type === 'accessory' ? 'Kancing/Resleting/Label *' : 'Lengan/Kerah/Saku/Lining *'}
                      value={it.component_type}
                      onChange={e => updateItem(idx, 'component_type', e.target.value)}
                      data-testid={`cmt-form-row-${idx}-type`} />
                    <Input className="col-span-2" placeholder="Size (S/M/L)"
                      value={it.size} onChange={e => updateItem(idx, 'size', e.target.value)} />
                    <Input className="col-span-2" placeholder="Warna"
                      value={it.color} onChange={e => updateItem(idx, 'color', e.target.value)} />
                    <Input className="col-span-2" type="number" min="0" placeholder="Qty"
                      value={it.qty} onChange={e => updateItem(idx, 'qty', e.target.value)} />
                    <select className="col-span-2 border border-input bg-background rounded-md px-2 py-2 text-sm text-foreground"
                      value={it.unit} onChange={e => updateItem(idx, 'unit', e.target.value)}>
                      <option value="pcs">pcs</option>
                      <option value="set">set</option>
                      <option value="meter">meter</option>
                      <option value="lusin">lusin</option>
                    </select>
                    <button type="button" onClick={() => removeItemRow(idx)}
                      disabled={form.items.length <= 1}
                      className="col-span-1 h-9 rounded-md border border-red-400 dark:border-red-500/30 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10 disabled:opacity-30 flex items-center justify-center"
                      data-testid={`cmt-form-row-${idx}-remove`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Butuh Sebelum</Label>
                <Input className="mt-1" type="date" value={form.needed_by_date}
                  onChange={e => f('needed_by_date', e.target.value)}
                  data-testid="cmt-form-needed-by" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <input type="checkbox" checked={!!form.urgent}
                    onChange={e => f('urgent', e.target.checked)}
                    className="w-4 h-4 accent-amber-500"
                    data-testid="cmt-form-urgent" />
                  <span className="text-foreground/70">Tandai Urgent</span>
                </label>
              </div>
            </div>
            <div>
              <Label>Catatan</Label>
              <textarea value={form.notes}
                onChange={e => f('notes', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none"
                placeholder="Detail spesifikasi, instruksi khusus..." />
            </div>

            {!editing && (
              <DocNumberField
                policy={numPolicy} value={reqCode} onChange={setReqCode}
                testId="cmt-req-docnum" label="Nomor Permintaan" />
            )}
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
            <Button onClick={handleSave} data-testid="cmt-form-save-btn">
              {editing ? 'Update' : 'Buat Request'}
            </Button>
          </div>
        </Modal>
      )}

      {/* Detail Modal */}
      {detail && (
        <Modal onClose={() => setDetail(null)} title={`Detail: ${detail.request_code}`} size="lg">
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-foreground/50">CMT Partner</div>
                <div className="font-medium">{detail.cmt_partner_name || '—'}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Work Order</div>
                <div className="font-mono">{detail.work_order_code || '—'}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Produk</div>
                <div>{detail.product_name || '—'}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Tipe Request</div>
                <div>{TYPE_CONF[detail.request_type]?.label || detail.request_type}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Status</div>
                <div>{STATUS_CONF[detail.status]?.label || detail.status}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Butuh Sebelum</div>
                <div>{detail.needed_by_date ? formatDate(detail.needed_by_date) : '—'}</div>
              </div>
            </div>
            <div>
              <Label>Items ({(detail.items || []).length})</Label>
              <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                <table className="w-full text-xs">
                  <thead className="bg-foreground/5">
                    <tr>
                      {['Komponen', 'Size', 'Warna', 'Qty', 'Unit', 'Catatan'].map(h => (
                        <th key={h} className="text-left px-3 py-2 text-foreground/50">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.items || []).map((it, idx) => (
                      <tr key={idx} className="border-t border-foreground/5">
                        <td className="px-3 py-2 font-medium">{it.component_type}</td>
                        <td className="px-3 py-2">{it.size || '—'}</td>
                        <td className="px-3 py-2">{it.color || '—'}</td>
                        <td className="px-3 py-2">{it.qty}</td>
                        <td className="px-3 py-2">{it.unit}</td>
                        <td className="px-3 py-2 text-foreground/60">{it.notes || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {detail.notes && (
              <div>
                <div className="text-xs text-foreground/50">Catatan</div>
                <div className="mt-1 px-3 py-2 rounded-lg bg-foreground/5">{detail.notes}</div>
              </div>
            )}
            <div className="space-y-1 text-xs text-foreground/50">
              <div>Dibuat: <strong>{detail.requester_name}</strong> · {formatDate(detail.created_at)}</div>
              {detail.cutting_started_at && (
                <div>Diproses: <strong>{detail.cutting_started_by}</strong> · {formatDate(detail.cutting_started_at)}</div>
              )}
              {detail.ready_at && (
                <div>Siap: <strong>{detail.ready_by}</strong> · {formatDate(detail.ready_at)}</div>
              )}
              {detail.delivered_at && (
                <div>
                  Terkirim: <strong>{detail.delivered_by}</strong> · {formatDate(detail.delivered_at)}
                  {detail.delivery_order_number && ` · DO: ${detail.delivery_order_number}`}
                </div>
              )}
            </div>
            {detail.rejection_reason && (
              <div className="px-3 py-2 rounded-lg bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 text-red-700 dark:text-red-400">
                Alasan reject: {detail.rejection_reason}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Action Modal */}
      {actionModal && (
        <Modal onClose={() => setActionModal(null)}
          title={
            actionModal.target_status === 'cutting'   ? 'Mulai Proses Cutting' :
            actionModal.target_status === 'ready'     ? 'Tandai Komponen Siap' :
            actionModal.target_status === 'delivered' ? 'Catat Pengiriman' :
            actionModal.target_status === 'rejected'  ? 'Tolak Request' :
            'Update Status'
          }>
          {actionModal.target_status === 'delivered' ? (
            <div className="space-y-3">
              <div>
                <Label>Nomor Delivery Order</Label>
                <Input className="mt-1" value={actionModal.delivery_order_number || ''}
                  onChange={e => setActionModal(p => ({ ...p, delivery_order_number: e.target.value }))}
                  placeholder="DO-CMT-2024-001"
                  data-testid="cmt-action-do-number" />
              </div>
              <div>
                <Label>Catatan (opsional)</Label>
                <textarea value={actionModal.notes || ''}
                  onChange={e => setActionModal(p => ({ ...p, notes: e.target.value }))}
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-20 resize-none"
                  placeholder="Diserahkan ke CMT via courier..." />
              </div>
            </div>
          ) : actionModal.target_status === 'rejected' ? (
            <>
              <p className="text-sm text-foreground/60 mb-3">Tuliskan alasan penolakan:</p>
              <textarea value={actionModal.reason || ''}
                onChange={e => setActionModal(p => ({ ...p, reason: e.target.value }))}
                className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-24 resize-none"
                placeholder="Stok kosong, di luar spesifikasi, dll..."
                data-testid="cmt-action-reject-reason" />
            </>
          ) : (
            <>
              <p className="text-sm text-foreground/60 mb-3">Catatan (opsional):</p>
              <textarea value={actionModal.notes || ''}
                onChange={e => setActionModal(p => ({ ...p, notes: e.target.value }))}
                className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-20 resize-none"
                placeholder="Catatan internal..." />
            </>
          )}
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="outline" onClick={() => setActionModal(null)}>Batal</Button>
            <Button onClick={handleSetStatus}
              className={actionModal.target_status === 'rejected' ? 'bg-red-600 hover:bg-red-700 text-foreground' : ''}
              data-testid="cmt-action-confirm-btn">
              {actionModal.target_status === 'cutting' ? 'Mulai Proses'
                : actionModal.target_status === 'ready' ? 'Tandai Siap'
                : actionModal.target_status === 'delivered' ? 'Catat Kirim'
                : actionModal.target_status === 'rejected' ? 'Tolak'
                : 'Update'}
            </Button>
          </div>
        </Modal>
      )}

      {!!delId && (
        <ConfirmDialog title="Hapus Request?"
          message="Request komponen akan dihapus permanen."
          onConfirm={handleDelete} onCancel={() => setDelId(null)} />
      )}
    </div>
  );
}
