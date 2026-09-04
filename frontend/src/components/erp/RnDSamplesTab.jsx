import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Plus, CheckCircle, XCircle, Clock, Send, Search,
  FlaskConical, Pencil, Trash2, Filter, Package, FileStack, Factory
} from 'lucide-react';
import { toast } from '../ui/sonner';
import { apiFetch, ApiError } from '@/lib/apiFetch';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import OnwardCTA from './OnwardCTA';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const STATUS_CONF = {
  draft:     { label: 'Draft',     cls: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',     Icon: Clock },
  submitted: { label: 'Diajukan', cls: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30',  Icon: Send },
  approved:  { label: 'Disetujui',cls: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-500 border-emerald-400 dark:border-emerald-500/30', Icon: CheckCircle },
  rejected:  { label: 'Ditolak',  cls: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30',         Icon: XCircle },
};

const PRIORITY_CLS = {
  high:   'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border-red-500/25',
  normal: 'bg-sky-100 dark:bg-sky-500/15 text-sky-500 border-sky-500/25',
  low:    'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border/25',
};

const emptyForm = {
  style_id: '', quantity: 1, priority: 'normal', sample_pic: '', due_date: '', notes: '',
};

export default function RnDSamplesTab({ token, onNavigate }) {
  const [samples,  setSamples]  = useState([]);
  const [styles,   setStyles]   = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [filterStatus, setFilterStatus] = useState('');
  const [search,   setSearch]   = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form,     setForm]     = useState({ ...emptyForm });
  // Approve / Reject modal
  const [actionModal, setActionModal] = useState(null); // { id, type: 'approve'|'reject', notes: '' }
  const [delId,    setDelId]    = useState(null);

  // Session 27 — Accessory Request Modal (GAP-R3)
  const [accReqModal, setAccReqModal] = useState(null); // { sample: {...}, items: [...], urgent, needed_by_date, notes }
  // SESI #27 — kebijakan penomoran Permintaan Aksesoris. TIPE=REQ-AKS (sampel R&D).
  const accNumPolicy = useDocNumberPolicy('dewi_accessory_requests.request_code',
                                          localStorage.getItem('erp_token'),
                                          { TIPE: 'REQ-AKS' });
  const [accReqCode, setAccReqCode] = useState('');

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const fetchSamples = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStatus) qs.set('status', filterStatus);
      if (search) qs.set('search', search);
      const data = await apiFetch(`/dewi/rnd/sample-requests${qs.toString() ? '?' + qs : ''}`);
      setSamples(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error('Gagal memuat sample');
    } finally { setLoading(false); }
  };

  const fetchStyles = async () => {
    try {
      const data = await apiFetch('/dewi/rnd/styles');
      setStyles(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchSamples(); }, [filterStatus]);
  useEffect(() => { fetchStyles(); }, []);

  const handleCreate = async () => {
    if (!form.style_id) return toast.error('Pilih style terlebih dahulu');
    try {
      await apiFetch('/dewi/rnd/sample-requests', { method: 'POST', body: form });
      toast.success('Sample request berhasil dibuat');
      setShowForm(false);
      setForm({ ...emptyForm });
      fetchSamples();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error('Gagal membuat sample');
    }
  };

  const handleSubmit = async (id) => {
    try {
      await apiFetch(`/dewi/rnd/sample-requests/${id}/submit`, { method: 'POST' });
      toast.success('Sample berhasil di-submit');
      fetchSamples();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error('Gagal submit sample');
    }
  };

  const handleAction = async () => {
    if (!actionModal) return;
    const { id, type, notes } = actionModal;
    if (type === 'reject' && !notes.trim()) return toast.error('Alasan reject wajib diisi');
    try {
      await apiFetch(`/dewi/rnd/sample-requests/${id}/${type}`, {
        method: 'POST', body: { notes },
      });
      toast.success(type === 'approve' ? 'Sample disetujui' : 'Sample ditolak');
      setActionModal(null);
      fetchSamples();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(`Gagal ${type} sample`);
    }
  };

  const handleDelete = async () => {
    try {
      await apiFetch(`/dewi/rnd/sample-requests/${delId}`, { method: 'DELETE' });
      toast.success('Sample dihapus');
      setDelId(null);
      fetchSamples();
    } catch { toast.error('Gagal menghapus'); }
  };

  // ── Session 27 — GAP-R3 Accessory Request Handlers ────────────────────────
  const openAccReq = (sample) => {
    setAccReqModal({
      sample,
      items: [{ material_code: '', material_name: '', qty: 1, unit: 'pcs', notes: '' }],
      urgent: false,
      needed_by_date: '',
      notes: '',
      submitting: false,
    });
  };

  const updateAccReqItem = (idx, field, value) => {
    setAccReqModal(prev => {
      if (!prev) return prev;
      const items = [...prev.items];
      items[idx] = { ...items[idx], [field]: value };
      return { ...prev, items };
    });
  };

  const addAccReqItemRow = () => {
    setAccReqModal(prev => prev ? ({ ...prev, items: [...prev.items, { material_code: '', material_name: '', qty: 1, unit: 'pcs', notes: '' }] }) : prev);
  };

  const removeAccReqItemRow = (idx) => {
    setAccReqModal(prev => {
      if (!prev) return prev;
      if (prev.items.length <= 1) return prev;
      return { ...prev, items: prev.items.filter((_, i) => i !== idx) };
    });
  };

  const handleSubmitAccReq = async () => {
    if (!accReqModal) return;
    const validItems = accReqModal.items.filter(it => (it.material_name || it.material_code) && Number(it.qty) > 0);
    if (validItems.length === 0) {
      toast.error('Minimal 1 item dengan nama/kode dan qty > 0');
      return;
    }
    try {
      setAccReqModal(p => ({ ...p, submitting: true }));
      const payload = {
        sample_request_id: accReqModal.sample.id,
        style_id: accReqModal.sample.style_id,
        style_code: accReqModal.sample.style_code,
        style_name: accReqModal.sample.style_name,
        items: validItems,
        urgent: !!accReqModal.urgent,
        needed_by_date: accReqModal.needed_by_date || '',
        notes: accReqModal.notes || '',
        status: 'submitted',  // langsung submit ke Admin Aksesoris
        ...docNumberPayload(accNumPolicy, 'request_code', accReqCode),
      };
      const res = await apiFetch('/dewi/accessory-requests', { method: 'POST', body: payload });
      // Submit transition (optional — backend default is 'draft' if status missing; we send 'submitted')
      // Actually we passed status='submitted' so the row is created directly in submitted state; skip /submit call to keep simple.
      toast.success(`Request aksesoris ${res.request_code} terkirim`);
      setAccReqModal(null);
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) {
        toast.error(e?.body?.detail || 'Gagal membuat request aksesoris');
      } else if (!(e instanceof ApiError)) {
        toast.error('Gagal membuat request aksesoris');
      }
      setAccReqModal(p => p ? ({ ...p, submitting: false }) : p);
    }
  };

  const filtered = samples.filter(s => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (s.sample_code || '').toLowerCase().includes(q)
      || (s.style_name || '').toLowerCase().includes(q)
      || (s.style_code || '').toLowerCase().includes(q);
  });

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="p-6 space-y-5" data-testid="rnd-samples-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-violet-500" /> Sample Requests
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">Kelola permintaan sample produk</p>
        </div>
        <Button onClick={() => { setShowForm(true); }} className="gap-2" data-testid="create-sample-btn">
          <Plus className="w-4 h-4" /> Request Sample Baru
        </Button>
      </div>

      {/* RC-FLOW-UX Alur 9 — Sample disetujui → Tech Pack / PO Maklon */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Setelah Sample Disetujui"
        actions={[
          { module: 'rnd-techpack', label: 'Buat Tech Pack', icon: FileStack, primary: true, hint: 'Susun tech pack dari sample yang disetujui' },
          { module: 'maklon-po', label: 'Buat PO Maklon', icon: Factory, hint: 'Order produksi maklon berdasarkan sample' },
        ]}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchSamples()}
            placeholder="Cari kode / style..." className="pl-9" />
        </div>
        <div className="flex gap-2 flex-wrap">
          {['', 'draft', 'submitted', 'approved', 'rejected'].map(s => (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                filterStatus === s
                  ? 'bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400 border-violet-500/40'
                  : 'bg-foreground/5 text-foreground/50 border-foreground/10 hover:border-foreground/20'
              }`}>
              {s === '' ? 'Semua' : STATUS_CONF[s]?.label || s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <FlaskConical className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada sample request.</p>
          <Button variant="outline" className="mt-3" onClick={() => setShowForm(true)}>+ Buat Request Pertama</Button>
        </GlassCard>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode Sample', 'Style', 'Qty', 'PIC / Pembuat', 'Prioritas', 'Due Date', 'Status', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map(s => {
                const sc = STATUS_CONF[s.status] || STATUS_CONF.draft;
                const Icon = sc.Icon;
                return (
                  <tr key={s.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-foreground">{s.sample_code}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{s.style_name}</div>
                      <div className="text-xs text-foreground/40">{s.style_code}</div>
                    </td>
                    <td className="px-4 py-3 text-foreground/70">{s.quantity} pcs</td>
                    <td className="px-4 py-3 text-foreground/70 text-xs" data-testid={`sample-pic-${s.id}`}>
                      {s.sample_pic || <span className="text-foreground/40">belum ditentukan</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${PRIORITY_CLS[s.priority] || PRIORITY_CLS.normal}`}>
                        {s.priority === 'high' ? 'Tinggi' : s.priority === 'low' ? 'Rendah' : 'Normal'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground/60 text-xs">
                      {s.due_date ? new Date(s.due_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>
                        <Icon className="w-3 h-3" /> {sc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        {s.status === 'draft' && (
                          <Button variant="ghost" size="sm"
                            onClick={() => handleSubmit(s.id)}
                            className="h-7 px-2 text-xs text-sky-600 dark:text-sky-400 hover:text-sky-600 dark:text-sky-300 hover:bg-sky-100 dark:bg-sky-500/10"
                            data-testid={`submit-sample-${s.id}`}>
                            <Send className="w-3.5 h-3.5 mr-1" /> Submit
                          </Button>
                        )}
                        {s.status === 'submitted' && (
                          <>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: s.id, type: 'approve', notes: '' })}
                              className="h-7 px-2 text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10"
                              data-testid={`approve-sample-${s.id}`}>
                              <CheckCircle className="w-3.5 h-3.5 mr-1" /> Setujui
                            </Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: s.id, type: 'reject', notes: '' })}
                              className="h-7 px-2 text-xs text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                              data-testid={`reject-sample-${s.id}`}>
                              <XCircle className="w-3.5 h-3.5 mr-1" /> Tolak
                            </Button>
                          </>
                        )}
                        {(s.status === 'submitted' || s.status === 'approved') && (
                          <Button variant="ghost" size="sm"
                            onClick={() => openAccReq(s)}
                            className="h-7 px-2 text-xs text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:bg-amber-500/10"
                            title="Request Aksesoris ke Admin Aksesoris"
                            data-testid={`req-acc-sample-${s.id}`}>
                            <Package className="w-3.5 h-3.5 mr-1" /> Aksesoris
                          </Button>
                        )}
                        <Button variant="ghost" size="sm" onClick={() => setDelId(s.id)}
                          className="h-7 w-7 p-0 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10">
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* Create Form Modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)} title="Request Sample Baru">
        <div className="space-y-4">
          <div>
            <Label>Style <span className="text-red-700 dark:text-red-400">*</span></Label>
            <SmartNativeSelect value={form.style_id} onChange={e => f('style_id', e.target.value)}
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
              <option value="">-- Pilih Style --</option>
              {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Quantity (pcs)</Label>
              <Input className="mt-1" type="number" min="1" value={form.quantity}
                onChange={e => f('quantity', parseInt(e.target.value))} />
            </div>
            <div>
              <Label>Prioritas</Label>
              <select value={form.priority} onChange={e => f('priority', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                <option value="low">Rendah</option>
                <option value="normal">Normal</option>
                <option value="high">Tinggi</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>PIC / Pembuat Sample</Label>
              <Input className="mt-1" value={form.sample_pic}
                onChange={e => f('sample_pic', e.target.value)}
                placeholder="Nama penjahit / tim sample"
                data-testid="sample-pic-input" />
            </div>
            <div>
              <Label>Target Selesai</Label>
              <Input className="mt-1" type="date" value={form.due_date}
                onChange={e => f('due_date', e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Catatan</Label>
            <textarea value={form.notes} onChange={e => f('notes', e.target.value)}
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-20 resize-none"
              placeholder="Spesifikasi khusus, referensi, dll..." />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button onClick={handleCreate} data-testid="save-sample-btn">Buat Request</Button>
        </div>
      </Modal>

      {/* Approve / Reject Modal */}
      <Modal
        open={!!actionModal}
        onClose={() => setActionModal(null)}
        title={actionModal?.type === 'approve' ? 'Setujui Sample Request' : 'Tolak Sample Request'}
      >
        <p className="text-sm text-foreground/60 mb-4">
          {actionModal?.type === 'approve'
            ? 'Tambahkan catatan approval (opsional):'
            : 'Tuliskan alasan penolakan:'}
        </p>
        <textarea
          value={actionModal?.notes || ''}
          onChange={e => setActionModal(a => ({ ...a, notes: e.target.value }))}
          className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-24 resize-none"
          placeholder={actionModal?.type === 'reject' ? 'Alasan penolakan wajib diisi...' : 'Catatan opsional...'}
          data-testid="action-notes-input"
        />
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="outline" onClick={() => setActionModal(null)}>Batal</Button>
          <Button
            onClick={handleAction}
            className={actionModal?.type === 'reject' ? 'bg-red-600 hover:bg-red-700 text-foreground' : ''}
            data-testid="confirm-action-btn"
          >
            {actionModal?.type === 'approve' ? 'Setujui' : 'Tolak Sample'}
          </Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus Sample Request?"
          message="Sample request ini akan dihapus permanen."
        />
      )}

      {/* ── Session 27 — GAP-R3 Accessory Request Modal ──────────────────── */}
      {accReqModal && (
        <Modal open={!!accReqModal} onClose={() => setAccReqModal(null)}
          title={`Request Aksesoris — ${accReqModal.sample.sample_code}`} size="xl">
          <div className="space-y-4">
            <div className="px-4 py-3 rounded-lg bg-amber-100 dark:bg-amber-500/5 border border-amber-300 dark:border-amber-500/20">
              <div className="text-xs text-foreground/60">Style</div>
              <div className="font-medium text-foreground">{accReqModal.sample.style_code} — {accReqModal.sample.style_name}</div>
              <div className="text-xs text-foreground/50 mt-1">Sample qty: {accReqModal.sample.quantity} pcs</div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Daftar Aksesoris</Label>
                <Button type="button" variant="outline" size="sm" onClick={addAccReqItemRow}
                  data-testid="acc-req-add-row" className="gap-1.5">
                  <Plus className="w-3.5 h-3.5" /> Tambah Baris
                </Button>
              </div>
              <div className="space-y-2">
                {accReqModal.items.map((it, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-start" data-testid={`acc-req-row-${idx}`}>
                    <Input className="col-span-3" placeholder="Kode (opsional)"
                      value={it.material_code}
                      onChange={e => updateAccReqItem(idx, 'material_code', e.target.value)} />
                    <Input className="col-span-4" placeholder="Nama aksesoris *"
                      value={it.material_name}
                      onChange={e => updateAccReqItem(idx, 'material_name', e.target.value)} />
                    <Input className="col-span-2" type="number" min="0" step="0.1" placeholder="Qty"
                      value={it.qty}
                      onChange={e => updateAccReqItem(idx, 'qty', e.target.value)} />
                    <select className="col-span-2 border border-input bg-background rounded-md px-2 py-2 text-sm text-foreground"
                      value={it.unit}
                      onChange={e => updateAccReqItem(idx, 'unit', e.target.value)}>
                      <option value="pcs">pcs</option>
                      <option value="meter">meter</option>
                      <option value="kg">kg</option>
                      <option value="roll">roll</option>
                      <option value="set">set</option>
                      <option value="lusin">lusin</option>
                    </select>
                    <button type="button" onClick={() => removeAccReqItemRow(idx)}
                      disabled={accReqModal.items.length <= 1}
                      className="col-span-1 h-9 rounded-md border border-red-400 dark:border-red-500/30 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                      data-testid={`acc-req-remove-row-${idx}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Butuh Sebelum (tanggal)</Label>
                <Input type="date" className="mt-1" value={accReqModal.needed_by_date}
                  onChange={e => setAccReqModal(p => ({ ...p, needed_by_date: e.target.value }))}
                  data-testid="acc-req-needed-by-date" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer text-sm" data-testid="acc-req-urgent-label">
                  <input type="checkbox" checked={!!accReqModal.urgent}
                    onChange={e => setAccReqModal(p => ({ ...p, urgent: e.target.checked }))}
                    className="w-4 h-4 accent-amber-500"
                    data-testid="acc-req-urgent-checkbox" />
                  <span className="text-foreground/70">Tandai Urgent</span>
                </label>
              </div>
            </div>

            <div>
              <Label>Catatan</Label>
              <textarea className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-20 resize-none"
                placeholder="Spesifikasi warna, ukuran khusus, dll..."
                value={accReqModal.notes}
                onChange={e => setAccReqModal(p => ({ ...p, notes: e.target.value }))}
                data-testid="acc-req-notes" />
            </div>

            <DocNumberField
              policy={accNumPolicy} value={accReqCode} onChange={setAccReqCode}
              testId="acc-req-docnum" label="Nomor Permintaan Aksesoris" />
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <Button variant="outline" onClick={() => setAccReqModal(null)} disabled={accReqModal.submitting}>Batal</Button>
            <Button onClick={handleSubmitAccReq} disabled={accReqModal.submitting}
              data-testid="acc-req-submit-btn" className="gap-2">
              {accReqModal.submitting && <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-current" />}
              Kirim Request
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
