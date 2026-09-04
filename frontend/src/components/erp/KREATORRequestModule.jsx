import { useState, useEffect, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Users, Plus, Trash2, Eye, Search, CheckCircle2, XCircle,
  Send, Truck, Clock, Radio, Video, Sparkles
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from './docnum/DocNumberField';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_CONF = {
  draft:            { label: 'Draft',         cls: 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',     Icon: Clock },
  submitted:        { label: 'Tunggu RnD',    cls: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30', Icon: Send },
  approved_by_rnd:  { label: 'Disetujui RnD', cls: 'bg-sky-100 dark:bg-sky-500/15 text-sky-500 border-sky-400 dark:border-sky-500/30',       Icon: CheckCircle2 },
  sample_ready:     { label: 'Sample Siap',   cls: 'bg-violet-100 dark:bg-violet-500/15 text-violet-500 border-violet-400 dark:border-violet-500/30', Icon: Sparkles },
  delivered:        { label: 'Dikirim',       cls: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border-emerald-400 dark:border-emerald-500/30', Icon: Truck },
  rejected:         { label: 'Ditolak',       cls: 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30',       Icon: XCircle },
  cancelled:        { label: 'Batal',         cls: 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',     Icon: XCircle },
};

const KREATOR_TYPE_CONF = {
  live_streaming: { label: 'Live Streaming', cls: 'bg-fuchsia-100 dark:bg-fuchsia-500/15 text-fuchsia-500 border-fuchsia-400 dark:border-fuchsia-500/30', Icon: Radio },
  tiktok_video:   { label: 'TikTok Video',   cls: 'bg-teal-100 dark:bg-teal-500/15 text-teal-500 border-teal-400 dark:border-teal-500/30', Icon: Video },
};

const emptyForm = {
  kreator_name: '',
  kreator_handle: '',
  kreator_type: 'live_streaming',
  product_concept: '',
  reference_links: [],
  target_segment: '',
  sample_qty: 1,
  sample_colors: '',
  sample_sizes: '',
  deadline: '',
  notes: '',
};

export default function KREATORRequestModule({ token, currentUser, user, moduleId }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  // RC-IA T-3: scope per portal (lightweight). Derived from module-id:
  //   • marketing-kreator-requests = Marketing (buat & lacak request KREATOR)
  //   • rnd-kreator-requests       = RnD (antrian review & approve; default filter 'submitted')
  const scope = moduleId === 'rnd-kreator-requests' ? 'rnd' : 'marketing';
  const isRndScope = scope === 'rnd';
  const actor = currentUser || user;
  const roleIsRnd = (actor?.role || '').toLowerCase().includes('rnd')
    || ['superadmin', 'admin', 'manager', 'owner'].includes((actor?.role || '').toLowerCase());
  // Aksi approve/tolak RnD tampil pada scope RnD (portal sudah role-guarded) atau untuk role RnD-capable.
  const isRnd = isRndScope || roleIsRnd;

  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState(isRndScope ? 'submitted' : ''); // RnD: fokus antrian "Tunggu RnD"
  const [filterType, setFilterType] = useState('');
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [actionModal, setActionModal] = useState(null); // { id, type, notes }
  // SESI #27 — kebijakan penomoran Permintaan Kreator (Otomatis/Manual) milik owner.
  const numPolicy = useDocNumberPolicy('dewi_kreator_requests.request_code',
                                       localStorage.getItem('erp_token'));
  const [reqCode, setReqCode] = useState('');
  const [delId, setDelId] = useState(null);

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStatus) qs.set('status', filterStatus);
      if (filterType) qs.set('kreator_type', filterType);
      if (search) qs.set('search', search);
      const res = await fetch(`${API}/api/dewi/kreator-requests?${qs}`, { headers: h });
      setRequests(await res.json());
    } catch { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/stats/summary`, { headers: h });
      if (res.ok) setStats(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchRequests(); }, [filterStatus, filterType]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fetchStats(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openNew = () => {
    setForm({ ...emptyForm });
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (r) => {
    setForm({
      kreator_name: r.kreator_name || '',
      kreator_handle: r.kreator_handle || '',
      kreator_type: r.kreator_type || 'live_streaming',
      product_concept: r.product_concept || '',
      reference_links: r.reference_links || [],
      target_segment: r.target_segment || '',
      sample_qty: r.sample_qty || 1,
      sample_colors: (r.sample_colors || []).join(', '),
      sample_sizes: (r.sample_sizes || []).join(', '),
      deadline: r.deadline || '',
      notes: r.notes || '',
    });
    setEditing(r.id);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.kreator_name?.trim()) return toast.error('Nama kreator wajib diisi');
    if (!form.product_concept?.trim()) return toast.error('Konsep produk wajib diisi');
    const payload = {
      ...form,
      sample_colors: form.sample_colors ? String(form.sample_colors).split(',').map(s => s.trim()).filter(Boolean) : [],
      sample_sizes:  form.sample_sizes  ? String(form.sample_sizes).split(',').map(s => s.trim()).filter(Boolean)  : [],
      sample_qty: Number(form.sample_qty) || 1,
    };
    try {
      const url = editing ? `${API}/api/dewi/kreator-requests/${editing}` : `${API}/api/dewi/kreator-requests`;
      const method = editing ? 'PUT' : 'POST';
      const body = editing ? payload
        : { ...payload, ...docNumberPayload(numPolicy, 'request_code', reqCode) };
      const res = await fetch(url, { method, headers: h, body: JSON.stringify(body) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal menyimpan');
      }
      toast.success(editing ? 'Request diperbarui' : 'Request kreator dibuat');
      setShowForm(false);
      fetchRequests();
      fetchStats();
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan');
    }
  };

  const handleSubmit = async (id) => {
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${id}/submit`, { method: 'POST', headers: h });
      if (!res.ok) throw new Error();
      toast.success('Request dikirim ke RnD untuk approval');
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal submit request'); }
  };

  const handleApprove = async () => {
    if (!actionModal) return;
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${actionModal.id}/approve-by-rnd`, {
        method: 'POST', headers: h, body: JSON.stringify({ notes: actionModal.notes || '' }),
      });
      if (!res.ok) throw new Error();
      toast.success('Request disetujui RnD');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal approve'); }
  };

  const handleReject = async () => {
    if (!actionModal) return;
    if (!actionModal.notes?.trim()) return toast.error('Alasan reject wajib diisi');
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${actionModal.id}/reject`, {
        method: 'POST', headers: h, body: JSON.stringify({ reason: actionModal.notes }),
      });
      if (!res.ok) throw new Error();
      toast.success('Request ditolak');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal reject'); }
  };

  const handleMarkSampleReady = async (id) => {
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${id}/mark-sample-ready`, { method: 'POST', headers: h });
      if (!res.ok) throw new Error();
      toast.success('Sample ditandai siap');
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal update status'); }
  };

  const handleMarkDelivered = async () => {
    if (!actionModal) return;
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${actionModal.id}/mark-delivered`, {
        method: 'POST', headers: h,
        body: JSON.stringify({
          delivery_method: actionModal.delivery_method || '',
          tracking_number: actionModal.tracking_number || '',
        }),
      });
      if (!res.ok) throw new Error();
      toast.success('Sample ditandai dikirim');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal update delivery'); }
  };

  const handleDelete = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/kreator-requests/${delId}`, { method: 'DELETE', headers: h });
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
      || (r.kreator_name || '').toLowerCase().includes(q)
      || (r.product_concept || '').toLowerCase().includes(q);
  }), [requests, search]);

  const formatDate = (iso) => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="p-6 space-y-5" data-testid="kreator-request-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Users className="w-5 h-5 text-fuchsia-500" /> {isRndScope ? 'Approve Kreator Request' : 'KREATOR Request Management'}
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            {isRndScope
              ? 'Antrian review & persetujuan request produk dari KREATOR. Setujui / tolak lalu tandai sample siap — koordinasi RnD ↔ Marketing.'
              : 'Permintaan produk dari KREATOR (Live Streaming & TikTok Video) — koordinasi Marketing ↔ RnD'}
          </p>
        </div>
        {!isRndScope && (
          <Button onClick={openNew} className="gap-2" data-testid="kreator-req-add-btn">
            <Plus className="w-4 h-4" /> Request Baru
          </Button>
        )}
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="kreator-req-stats">
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50">Total Request</div>
            <div className="text-2xl font-bold text-foreground mt-1">{stats.total}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Radio className="w-3 h-3" /> Live Streaming</div>
            <div className="text-2xl font-bold text-fuchsia-500 mt-1" data-testid="stats-live-streaming">{stats.live_streaming}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Video className="w-3 h-3" /> TikTok Video</div>
            <div className="text-2xl font-bold text-teal-500 mt-1" data-testid="stats-tiktok-video">{stats.tiktok_video}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Send className="w-3 h-3" /> Tunggu RnD</div>
            <div className="text-2xl font-bold text-amber-700 dark:text-amber-500 mt-1">{stats.pending_rnd_approval}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Sparkles className="w-3 h-3" /> Siap Kirim</div>
            <div className="text-2xl font-bold text-violet-500 mt-1">{stats.ready_to_deliver}</div>
          </GlassCard>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchRequests()}
            placeholder="Cari kode / kreator / konsep..." className="pl-9"
            data-testid="kreator-req-search-input" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          data-testid="kreator-req-filter-type"
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[150px]">
          <option value="">Semua Tipe</option>
          <option value="live_streaming">Live Streaming</option>
          <option value="tiktok_video">TikTok Video</option>
        </select>
        <SmartNativeSelect value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          data-testid="kreator-req-filter-status"
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[150px]">
          <option value="">Semua Status</option>
          {Object.entries(STATUS_CONF).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </SmartNativeSelect>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-fuchsia-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Users className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">
            {isRndScope ? 'Tidak ada request menunggu persetujuan. Ubah filter status untuk melihat request lain.' : 'Belum ada request kreator.'}
          </p>
          {!isRndScope && (
            <Button variant="outline" className="mt-3" onClick={openNew}>+ Buat Request Pertama</Button>
          )}
        </GlassCard>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode', 'Kreator', 'Tipe', 'Konsep Produk', 'Qty', 'Status', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map(r => {
                const sc = STATUS_CONF[r.status] || STATUS_CONF.draft;
                const tc = KREATOR_TYPE_CONF[r.kreator_type] || KREATOR_TYPE_CONF.live_streaming;
                const SIcon = sc.Icon;
                const TIcon = tc.Icon;
                return (
                  <tr key={r.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-foreground">{r.request_code}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{r.kreator_name}</div>
                      {r.kreator_handle && <div className="text-xs text-foreground/40">@{r.kreator_handle}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${tc.cls}`}>
                        <TIcon className="w-3 h-3" /> {tc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate text-foreground/80" title={r.product_concept}>
                      {r.product_concept}
                    </td>
                    <td className="px-4 py-3 text-foreground/70 text-xs">
                      {r.sample_qty} pcs
                      {(r.sample_colors || []).length > 0 && <div className="text-foreground/40">{r.sample_colors.join(', ')}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>
                        <SIcon className="w-3 h-3" /> {sc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        <Button variant="ghost" size="sm" onClick={() => setDetail(r)}
                          className="h-7 w-7 p-0" data-testid={`kreator-req-detail-${r.id}`}>
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        {r.status === 'draft' && (
                          <>
                            <Button variant="ghost" size="sm"
                              onClick={() => handleSubmit(r.id)}
                              className="h-7 px-2 text-xs text-sky-600 dark:text-sky-400 hover:bg-sky-100 dark:bg-sky-500/10"
                              data-testid={`kreator-req-submit-${r.id}`}>
                              <Send className="w-3.5 h-3.5 mr-1" /> Submit
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => openEdit(r)}
                              className="h-7 w-7 p-0"
                              data-testid={`kreator-req-edit-${r.id}`}>
                              <Sparkles className="w-3.5 h-3.5" />
                            </Button>
                          </>
                        )}
                        {r.status === 'submitted' && isRnd && (
                          <>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: r.id, type: 'approve', notes: '' })}
                              className="h-7 px-2 text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10"
                              data-testid={`kreator-req-approve-${r.id}`}>
                              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Setujui
                            </Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: r.id, type: 'reject', notes: '' })}
                              className="h-7 px-2 text-xs text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                              data-testid={`kreator-req-reject-${r.id}`}>
                              <XCircle className="w-3.5 h-3.5 mr-1" /> Tolak
                            </Button>
                          </>
                        )}
                        {r.status === 'approved_by_rnd' && (
                          <Button variant="ghost" size="sm"
                            onClick={() => handleMarkSampleReady(r.id)}
                            className="h-7 px-2 text-xs text-violet-600 dark:text-violet-400 hover:bg-violet-100 dark:bg-violet-500/10"
                            data-testid={`kreator-req-sample-ready-${r.id}`}>
                            <Sparkles className="w-3.5 h-3.5 mr-1" /> Sample Siap
                          </Button>
                        )}
                        {r.status === 'sample_ready' && (
                          <Button variant="ghost" size="sm"
                            onClick={() => setActionModal({ id: r.id, type: 'deliver', notes: '', delivery_method: '', tracking_number: '' })}
                            className="h-7 px-2 text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10"
                            data-testid={`kreator-req-deliver-${r.id}`}>
                            <Truck className="w-3.5 h-3.5 mr-1" /> Kirim
                          </Button>
                        )}
                        {(r.status === 'draft' || r.status === 'rejected' || r.status === 'cancelled') && (
                          <Button variant="ghost" size="sm" onClick={() => setDelId(r.id)}
                            className="h-7 w-7 p-0 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                            data-testid={`kreator-req-delete-${r.id}`}>
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
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* Create/Edit Form Modal */}
      {showForm && (
        <Modal onClose={() => setShowForm(false)}
          title={editing ? 'Edit Request KREATOR' : 'Buat Request KREATOR Baru'} size="lg">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Nama Kreator <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Input className="mt-1" value={form.kreator_name}
                  onChange={e => f('kreator_name', e.target.value)}
                  placeholder="Contoh: Tasya Farasya"
                  data-testid="kreator-form-name" />
              </div>
              <div>
                <Label>Handle/Username</Label>
                <Input className="mt-1" value={form.kreator_handle}
                  onChange={e => f('kreator_handle', e.target.value)}
                  placeholder="tasyafarasya" />
              </div>
            </div>
            <div>
              <Label>Tipe Kreator <span className="text-red-700 dark:text-red-400">*</span></Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {Object.entries(KREATOR_TYPE_CONF).map(([k, v]) => {
                  const Icon = v.Icon;
                  return (
                    <button key={k} type="button"
                      onClick={() => f('kreator_type', k)}
                      data-testid={`kreator-form-type-${k}`}
                      className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border transition-all ${
                        form.kreator_type === k
                          ? `${v.cls} border-current`
                          : 'border-foreground/10 hover:border-foreground/20 text-foreground/60'
                      }`}>
                      <Icon className="w-4 h-4" />
                      <span className="text-sm font-medium">{v.label}</span>
                    </button>
                  );
                })}
              </div>
              <p className="text-xs text-foreground/40 mt-1">
                Live Streaming: butuh 1 pcs per warna best-seller · TikTok Video: 1 pcs random color
              </p>
            </div>
            <div>
              <Label>Konsep Produk <span className="text-red-700 dark:text-red-400">*</span></Label>
              <textarea value={form.product_concept}
                onChange={e => f('product_concept', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-24 resize-none"
                placeholder="Deskripsi produk yang diminta kreator..."
                data-testid="kreator-form-concept" />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label>Qty Sample</Label>
                <Input className="mt-1" type="number" min="1" value={form.sample_qty}
                  onChange={e => f('sample_qty', e.target.value)}
                  data-testid="kreator-form-qty" />
              </div>
              <div>
                <Label>Warna (pisah koma)</Label>
                <Input className="mt-1" value={form.sample_colors}
                  onChange={e => f('sample_colors', e.target.value)}
                  placeholder="merah, hitam, krem" />
              </div>
              <div>
                <Label>Ukuran (pisah koma)</Label>
                <Input className="mt-1" value={form.sample_sizes}
                  onChange={e => f('sample_sizes', e.target.value)}
                  placeholder="M, L, XL" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Target Segmen</Label>
                <Input className="mt-1" value={form.target_segment}
                  onChange={e => f('target_segment', e.target.value)}
                  placeholder="Mahasiswa, ibu-ibu, dll." />
              </div>
              <div>
                <Label>Deadline</Label>
                <Input className="mt-1" type="date" value={form.deadline}
                  onChange={e => f('deadline', e.target.value)} />
              </div>
            </div>
            <div>
              <Label>Catatan</Label>
              <textarea value={form.notes}
                onChange={e => f('notes', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none"
                placeholder="Catatan tambahan untuk RnD..." />
            </div>

            {!editing && (
              <DocNumberField
                policy={numPolicy} value={reqCode} onChange={setReqCode}
                testId="kreator-docnum" label="Nomor Permintaan Kreator" />
            )}
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
            <Button onClick={handleSave} data-testid="kreator-form-save-btn">
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
                <div className="text-xs text-foreground/50">Kreator</div>
                <div className="font-medium">{detail.kreator_name}</div>
                {detail.kreator_handle && <div className="text-xs text-foreground/40">@{detail.kreator_handle}</div>}
              </div>
              <div>
                <div className="text-xs text-foreground/50">Tipe</div>
                <div>{KREATOR_TYPE_CONF[detail.kreator_type]?.label || detail.kreator_type}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Qty Sample</div>
                <div>{detail.sample_qty} pcs</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Warna / Ukuran</div>
                <div>{(detail.sample_colors || []).join(', ') || '—'} · {(detail.sample_sizes || []).join(', ') || '—'}</div>
              </div>
              <div className="col-span-2">
                <div className="text-xs text-foreground/50">Konsep Produk</div>
                <div className="mt-1 px-3 py-2 rounded-lg bg-foreground/5">{detail.product_concept}</div>
              </div>
              {detail.target_segment && (
                <div className="col-span-2">
                  <div className="text-xs text-foreground/50">Target Segmen</div>
                  <div>{detail.target_segment}</div>
                </div>
              )}
              {detail.deadline && (
                <div>
                  <div className="text-xs text-foreground/50">Deadline</div>
                  <div>{formatDate(detail.deadline)}</div>
                </div>
              )}
              <div>
                <div className="text-xs text-foreground/50">Status</div>
                <div>{STATUS_CONF[detail.status]?.label || detail.status}</div>
              </div>
              {detail.style_code && (
                <div className="col-span-2">
                  <div className="text-xs text-foreground/50">Style Linked</div>
                  <div className="font-mono">{detail.style_code} — {detail.style_name}</div>
                </div>
              )}
            </div>
            {detail.notes && (
              <div>
                <div className="text-xs text-foreground/50">Catatan</div>
                <div className="mt-1 px-3 py-2 rounded-lg bg-foreground/5">{detail.notes}</div>
              </div>
            )}
            {detail.approved_by && (
              <div className="text-xs text-foreground/50">
                Disetujui oleh <strong>{detail.approved_by}</strong> pada {formatDate(detail.approved_at)}
              </div>
            )}
            {detail.delivered_by && (
              <div className="text-xs text-foreground/50">
                Dikirim oleh <strong>{detail.delivered_by}</strong> pada {formatDate(detail.delivered_at)}
                {detail.delivery_method && ` · ${detail.delivery_method}`}
                {detail.tracking_number && ` · Resi: ${detail.tracking_number}`}
              </div>
            )}
            {detail.rejection_reason && (
              <div className="px-3 py-2 rounded-lg bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 text-red-700 dark:text-red-400">
                Alasan reject: {detail.rejection_reason}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Action Modal (Approve / Reject / Deliver) */}
      {actionModal && (
        <Modal onClose={() => setActionModal(null)}
          title={
            actionModal.type === 'approve' ? 'Setujui Request (RnD)' :
            actionModal.type === 'reject'  ? 'Tolak Request' :
            'Catat Pengiriman Sample'
          }>
          {actionModal.type === 'deliver' ? (
            <div className="space-y-3">
              <div>
                <Label>Metode Pengiriman</Label>
                <select value={actionModal.delivery_method || ''}
                  onChange={e => setActionModal(p => ({ ...p, delivery_method: e.target.value }))}
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground"
                  data-testid="kreator-deliver-method">
                  <option value="">— Pilih —</option>
                  <option value="courier">Kurir (JNE/JNT/SiCepat)</option>
                  <option value="pickup">Pickup Langsung</option>
                  <option value="mail">POS / Mail</option>
                </select>
              </div>
              <div>
                <Label>Nomor Resi (opsional)</Label>
                <Input className="mt-1" value={actionModal.tracking_number || ''}
                  onChange={e => setActionModal(p => ({ ...p, tracking_number: e.target.value }))}
                  placeholder="JNE12345..."
                  data-testid="kreator-deliver-tracking" />
              </div>
            </div>
          ) : (
            <>
              <p className="text-sm text-foreground/60 mb-3">
                {actionModal.type === 'approve'
                  ? 'Catatan approval (opsional):'
                  : 'Tuliskan alasan penolakan:'}
              </p>
              <textarea value={actionModal.notes || ''}
                onChange={e => setActionModal(p => ({ ...p, notes: e.target.value }))}
                className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-24 resize-none"
                placeholder={actionModal.type === 'reject' ? 'Alasan reject...' : 'Catatan...'}
                data-testid="kreator-action-notes" />
            </>
          )}
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="outline" onClick={() => setActionModal(null)}>Batal</Button>
            <Button
              onClick={
                actionModal.type === 'approve' ? handleApprove :
                actionModal.type === 'reject'  ? handleReject :
                handleMarkDelivered
              }
              className={actionModal.type === 'reject' ? 'bg-red-600 hover:bg-red-700 text-foreground' : ''}
              data-testid="kreator-confirm-action-btn">
              {actionModal.type === 'approve' ? 'Setujui'
                : actionModal.type === 'reject' ? 'Tolak'
                : 'Catat Kirim'}
            </Button>
          </div>
        </Modal>
      )}

      {!!delId && (
        <ConfirmDialog title="Hapus Request?"
          message="Request kreator akan dihapus permanen."
          onConfirm={handleDelete} onCancel={() => setDelId(null)} />
      )}
    </div>
  );
}
