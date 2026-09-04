import { useState, useEffect } from 'react';
import { GlassCard } from '@/components/ui/glass';
import {
  Plus, Search, Pencil, Trash2, X, Check, Eye, Layers,
  Send, Clock, CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronUp, MessageSquare,
  ImagePlus, Loader2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || '';
import { toast } from '../ui/sonner';
import { apiFetch, ApiError } from '@/lib/apiFetch';
import RnDStyleDetailPage from './RnDStyleDetailPage';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const STATUS_BADGE = {
  draft:                 { label: 'Draft',                color: '#94a3b8', bg: '#94a3b820' },
  active:                { label: 'Active',               color: '#10b981', bg: '#10b98120' },
  pending_owner_review:  { label: 'Menunggu Review Owner',color: '#f59e0b', bg: '#f59e0b20' },
  approved_for_launch:   { label: 'Disetujui Owner',      color: '#3b82f6', bg: '#3b82f620' },
  archived:              { label: 'Archived',             color: '#6b7280', bg: '#6b728020' },
};

// Status keputusan — hanya boleh berpindah lewat tombol Ajukan/Setujui/Tolak
// (backend juga menolak perubahannya lewat PUT /styles/{id}).
const LIFECYCLE_STATUSES = ['pending_owner_review', 'approved_for_launch'];

function StatusBadge({ status }) {
  const s = STATUS_BADGE[status] || STATUS_BADGE.draft;
  return (
    <span
      className="inline-block px-2 py-1 rounded-full text-xs font-medium"
      style={{ backgroundColor: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

function ReviewHistoryPanel({ style }) {
  if (!style.owner_review_result) return null;
  const approved = style.owner_review_result === 'approved';
  return (
    <div
      className={`mt-2 px-3 py-2 rounded-lg text-xs flex items-start gap-2 ${
        approved ? 'bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20' : 'bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-400/20'
      }`}
    >
      {approved ? (
        <CheckCircle2 className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
      ) : (
        <XCircle className="w-3.5 h-3.5 text-red-700 dark:text-red-400 mt-0.5 shrink-0" />
      )}
      <div>
        <span className={`font-semibold ${approved ? 'text-blue-600 dark:text-blue-300' : 'text-red-600 dark:text-red-300'}`}>
          {approved ? 'Disetujui' : 'Ditolak'} oleh {style.owner_reviewed_by}
        </span>
        {style.owner_review_notes && (
          <p className="text-foreground/60 mt-0.5">{style.owner_review_notes}</p>
        )}
      </div>
    </div>
  );
}

export default function RnDStylesTab({ token, user }) {
  const [styles, setStyles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailStyleId, setDetailStyleId] = useState(null);
  const [submitReviewDialog, setSubmitReviewDialog] = useState(null);
  const [ownerReviewDialog, setOwnerReviewDialog] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [showPendingInbox, setShowPendingInbox] = useState(false);

  const [form, setForm] = useState({
    style_code: '', style_name: '', category: '',
    buyer: '', fabric_type: '', season: '', description: '', status: 'draft',
  });

  // Foto desain (unggah di form Tambah/Edit Style → galeri approval manajemen)
  const [photos, setPhotos] = useState([]);            // foto yang sudah tersimpan
  const [pendingPhotos, setPendingPhotos] = useState([]); // dipilih saat mode Tambah
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  // Detect if current user is owner/superadmin
  const isOwner = user && (user.role === 'superadmin' || user.role === 'owner' || user.role === 'admin');

  useEffect(() => {
    fetchStyles();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, filterStatus]);

  useEffect(() => {
    if (isOwner) fetchPendingCount();
  }, [isOwner]);

  const fetchStyles = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (filterStatus) params.set('status', filterStatus);
      const qs = params.toString();
      const data = await apiFetch(`/dewi/rnd/styles${qs ? '?' + qs : ''}`);
      setStyles(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal memuat data style');
    } finally {
      setLoading(false);
    }
  };

  const fetchPendingCount = async () => {
    try {
      const data = await apiFetch('/dewi/rnd/styles/pending-review');
      setPendingCount(Array.isArray(data) ? data.length : 0);
    } catch {}
  };

  const openCreate = () => {
    setEditing(null);
    setForm({ style_code: '', style_name: '', category: '', buyer: '', fabric_type: '', season: '', description: '', status: 'draft' });
    setPhotos([]);
    setPendingPhotos([]);
    setShowForm(true);
  };

  const openEdit = (style) => {
    setEditing(style);
    setPhotos(Array.isArray(style.design_images) ? style.design_images.filter((p) => p && p.url) : []);
    setPendingPhotos([]);
    setForm({
      style_code: style.style_code || '', style_name: style.style_name || '',
      category: style.category || '', buyer: style.buyer || '',
      fabric_type: style.fabric_type || '', season: style.season || '',
      description: style.description || '', status: style.status || 'draft',
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.style_code.trim() || !form.style_name.trim()) {
      toast.error('Kode style dan nama style wajib diisi');
      return;
    }
    try {
      if (editing) {
        await apiFetch(`/dewi/rnd/styles/${editing.id}`, { method: 'PUT', body: form });
        toast.success('Style berhasil diupdate');
      } else {
        const created = await apiFetch('/dewi/rnd/styles', { method: 'POST', body: form });
        if (pendingPhotos.length && created?.id) {
          for (const file of pendingPhotos) await uploadPhoto(created.id, file);
        }
        toast.success(pendingPhotos.length
          ? `Style dibuat + ${pendingPhotos.length} foto desain diunggah`
          : 'Style berhasil dibuat');
      }
      setShowForm(false);
      setPendingPhotos([]);
      fetchStyles();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal menyimpan style');
    }
  };

  const uploadPhoto = (styleId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiFetch(`/dewi/rnd/styles/${styleId}/images`, { method: 'POST', formData: fd });
  };

  const handlePhotoInput = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = '';
    if (!files.length) return;
    const tooBig = files.find((f) => f.size > 10 * 1024 * 1024);
    if (tooBig) { toast.error(`${tooBig.name} lebih dari 10MB`); return; }
    if (!editing) { setPendingPhotos((p) => [...p, ...files]); return; }
    setUploadingPhoto(true);
    try {
      for (const file of files) {
        const entry = await uploadPhoto(editing.id, file);
        setPhotos((p) => [...p, entry]);
      }
      toast.success('Foto desain diunggah');
      fetchStyles();
    } catch (err) {
      toast.error(err.userMessage || err.detail || 'Gagal mengunggah foto');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handlePhotoDelete = async (imgId) => {
    try {
      await apiFetch(`/dewi/rnd/styles/${editing.id}/images/${imgId}`, { method: 'DELETE' });
      setPhotos((p) => p.filter((x) => x.id !== imgId));
      toast.success('Foto desain dihapus');
      fetchStyles();
    } catch (err) {
      toast.error(err.userMessage || 'Gagal menghapus foto');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Yakin ingin menghapus style ini?')) return;
    try {
      await apiFetch(`/dewi/rnd/styles/${id}`, { method: 'DELETE' });
      toast.success('Style berhasil dihapus');
      fetchStyles();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal menghapus style');
    }
  };

  // GAP-R2: Submit for Owner Review
  const handleSubmitForReview = async (styleId, notes) => {
    try {
      await apiFetch(`/dewi/rnd/styles/${styleId}/submit-for-review`, { method: 'POST', body: { notes } });
      toast.success('Style berhasil diajukan untuk review Owner');
      setSubmitReviewDialog(null);
      fetchStyles();
      if (isOwner) fetchPendingCount();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal mengajukan review');
    }
  };

  // GAP-R2: Owner Approve
  const handleOwnerApprove = async (styleId, notes) => {
    try {
      await apiFetch(`/dewi/rnd/styles/${styleId}/owner-approve`, { method: 'POST', body: { notes } });
      toast.success('Style berhasil disetujui');
      setOwnerReviewDialog(null);
      fetchStyles();
      if (isOwner) fetchPendingCount();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal menyetujui style');
    }
  };

  // GAP-R2: Owner Reject
  const handleOwnerReject = async (styleId, notes) => {
    if (!notes.trim()) { toast.error('Catatan penolakan wajib diisi'); return; }
    try {
      await apiFetch(`/dewi/rnd/styles/${styleId}/owner-reject`, { method: 'POST', body: { notes } });
      toast.success('Style ditolak dan dikembalikan ke Draft');
      setOwnerReviewDialog(null);
      fetchStyles();
      if (isOwner) fetchPendingCount();
    } catch (e) {
      if (e instanceof ApiError && !e.isUnauthorized) toast.error(e.userMessage || 'Gagal menolak style');
    }
  };

  const { page: stylesPage, setPage: setStylesPage, totalPages: stylesTotalPages, total: stylesTotal, paged: pagedStyles } = useClientPagination(styles, 10);


  return (
    <div className="space-y-4" data-testid="rnd-styles-tab">
      {/* Owner Pending Review Inbox Banner */}
      {isOwner && pendingCount > 0 && (
        <div className="rounded-xl border border-amber-400 dark:border-amber-400/30 bg-amber-100 dark:bg-amber-500/10 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              <span className="text-sm font-semibold text-amber-600 dark:text-amber-300">
                {pendingCount} style menunggu review Owner Anda
              </span>
            </div>
            <button
              onClick={() => { setShowPendingInbox(!showPendingInbox); if (!showPendingInbox) setFilterStatus('pending_owner_review'); else setFilterStatus(''); }}
              className="text-xs text-amber-600 dark:text-amber-300 hover:text-amber-200 flex items-center gap-1"
              data-testid="view-pending-review-btn"
            >
              {showPendingInbox ? (<><ChevronUp className="w-3.5 h-3.5" /> Sembunyikan</>) : (<><ChevronDown className="w-3.5 h-3.5" /> Lihat Semua</>)}
            </button>
          </div>
        </div>
      )}

      {/* Search + Filter + Create */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Cari style..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          data-testid="filter-status-select"
        >
          <option value="">Semua Status</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="pending_owner_review">Menunggu Review</option>
          <option value="approved_for_launch">Disetujui Owner</option>
          <option value="archived">Archived</option>
        </select>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:opacity-90 transition-opacity"
          data-testid="create-style-btn"
        >
          <Plus className="w-4 h-4" />
          Tambah Style
        </button>
      </div>

      {/* Styles Table */}
      <GlassCard>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left p-3 text-sm font-semibold">Kode</th>
                <th className="text-left p-3 text-sm font-semibold">Nama Style</th>
                <th className="text-left p-3 text-sm font-semibold">Kategori</th>
                <th className="text-left p-3 text-sm font-semibold">Buyer</th>
                <th className="text-left p-3 text-sm font-semibold">Season</th>
                <th className="text-left p-3 text-sm font-semibold">Varian</th>
                <th className="text-left p-3 text-sm font-semibold">Status</th>
                <th className="text-right p-3 text-sm font-semibold">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="8" className="text-center p-8 text-muted-foreground">Memuat...</td></tr>
              ) : styles.length === 0 ? (
                <tr><td colSpan="8" className="text-center p-8 text-muted-foreground">Belum ada data style</td></tr>
              ) : (
                pagedStyles.map((style) => {
                  const variantCount = (style.variants || []).length;
                  const canSubmitReview = (style.status === 'draft' || style.status === 'active');
                  const pendingReview = style.status === 'pending_owner_review';

                  return (
                    <tr key={style.id} className="border-b hover:bg-accent/50 transition-colors">
                      <td className="p-3">
                        <span className="font-mono text-sm font-semibold">{style.style_code}</span>
                      </td>
                      <td className="p-3">
                        <div>{style.style_name}</div>
                        {/* Riwayat keputusan owner: siapa memutuskan + alasan lengkap.
                            (Sebelum 2026-08-07 komponen ReviewHistoryPanel ini menganggur
                            dan barisnya hanya memotong alasan sampai 40 karakter tanpa
                            menyebut pemutusnya.) */}
                        <ReviewHistoryPanel style={style} />
                        {pendingReview && style.submitted_for_review_by && (
                          <div className="mt-1 text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Diajukan oleh {style.submitted_for_review_by}
                          </div>
                        )}
                      </td>
                      <td className="p-3 text-sm text-muted-foreground">{style.category || '-'}</td>
                      <td className="p-3 text-sm text-muted-foreground">{style.buyer || '-'}</td>
                      <td className="p-3 text-sm text-muted-foreground">{style.season || '-'}</td>
                      <td className="p-3">
                        {variantCount > 0 ? (
                          <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-500/20">
                            <Layers className="w-3 h-3 text-violet-500" />
                            <span className="text-xs font-semibold text-violet-500">{variantCount}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="p-3">
                        <StatusBadge status={style.status} />
                      </td>
                      <td className="p-3">
                        <div className="flex items-center justify-end gap-1">
                          {/* Owner: Approve/Reject when pending review */}
                          {isOwner && pendingReview && (
                            <button
                              onClick={() => setOwnerReviewDialog(style)}
                              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300 hover:bg-amber-500/30 transition-colors"
                              title="Review Desain"
                              data-testid={`owner-review-style-${style.id}`}
                            >
                              <MessageSquare className="w-3 h-3" />
                              Review
                            </button>
                          )}
                          {/* RnD: Submit for review */}
                          {canSubmitReview && (
                            <button
                              onClick={() => setSubmitReviewDialog(style)}
                              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-300 hover:bg-violet-500/30 transition-colors"
                              title="Ajukan ke Owner"
                              data-testid={`submit-review-${style.id}`}
                            >
                              <Send className="w-3 h-3" />
                              Ajukan
                            </button>
                          )}
                          <button
                            onClick={() => setDetailStyleId(style.id)}
                            className="p-1.5 hover:bg-accent rounded transition-colors"
                            title="Lihat Detail"
                            data-testid={`detail-style-${style.id}`}
                          >
                            <Eye className="w-4 h-4 text-violet-500" />
                          </button>
                          <button
                            onClick={() => openEdit(style)}
                            className="p-1.5 hover:bg-accent rounded transition-colors"
                            title="Edit"
                            data-testid={`edit-style-${style.id}`}
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(style.id)}
                            className="p-1.5 hover:bg-destructive/10 text-destructive rounded transition-colors"
                            title="Hapus"
                            data-testid={`delete-style-${style.id}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {!loading && styles.length > 0 && (
          <PaginationLite page={stylesPage} totalPages={stylesTotalPages} total={stylesTotal} onPageChange={setStylesPage} className="px-3" />
        )}
      </GlassCard>

      {/* ── Create/Edit Style Modal ── */}
      {showForm && (
        <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50 p-4">
          <GlassCard className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold">{editing ? 'Edit Style' : 'Tambah Style Baru'}</h2>
                <button onClick={() => setShowForm(false)} className="p-1 hover:bg-accent rounded transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1.5">Kode Style <span className="text-destructive">*</span></label>
                  <input type="text" value={form.style_code} onChange={(e) => setForm({ ...form, style_code: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="ST-001" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Nama Style <span className="text-destructive">*</span></label>
                  <input type="text" value={form.style_name} onChange={(e) => setForm({ ...form, style_name: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="Basic Tee Premium" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Kategori</label>
                  <input type="text" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="T-Shirt" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Buyer</label>
                  <input type="text" value={form.buyer} onChange={(e) => setForm({ ...form, buyer: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="Zara" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Fabric Type</label>
                  <input type="text" value={form.fabric_type} onChange={(e) => setForm({ ...form, fabric_type: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="Cotton Combed 30s" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Season</label>
                  <input type="text" value={form.season} onChange={(e) => setForm({ ...form, season: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="Spring 2024" />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium mb-1.5">Deskripsi</label>
                  <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary" rows="3" placeholder="Classic crew neck t-shirt..." />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1.5">Status</label>
                  {LIFECYCLE_STATUSES.includes(form.status) ? (
                    /* Status keputusan (menunggu review / disetujui owner) TIDAK boleh
                       diubah dari form edit — dulu select-nya menampilkan "Draft" secara
                       keliru sehingga status review bisa terhapus tanpa sengaja. */
                    <div className="rounded-lg border bg-muted/40 px-3 py-2" data-testid="style-status-locked">
                      <StatusBadge status={form.status} />
                      <p className="mt-1.5 text-[11px] text-muted-foreground">
                        Diatur lewat tombol <b>Ajukan Review</b> / <b>Setujui</b> / <b>Tolak</b> agar
                        keputusan tercatat beserta pemutus &amp; alasannya.
                      </p>
                    </div>
                  ) : (
                    <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                      className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      data-testid="style-status-select">
                      <option value="draft">Draft</option>
                      <option value="active">Active</option>
                      <option value="archived">Archived</option>
                    </select>
                  )}
                </div>
              </div>

              {/* ── Foto / Sketsa Desain ── */}
              <div className="rounded-lg border p-4 space-y-3" data-testid="style-photos-section">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div>
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <ImagePlus className="w-4 h-4 text-violet-500" /> Foto / Sketsa Desain
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Tampil di galeri approval manajemen &amp; ikut tersimpan pada riwayat revisi. Maks 10MB per foto.
                    </p>
                  </div>
                  <label
                    className="flex items-center gap-2 px-3 py-2 border rounded-lg text-sm font-medium cursor-pointer hover:bg-accent transition-colors"
                    data-testid="style-photo-upload-label"
                  >
                    {uploadingPhoto ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImagePlus className="w-4 h-4" />}
                    {uploadingPhoto ? 'Mengunggah...' : 'Pilih Foto'}
                    <input type="file" accept="image/*" multiple hidden disabled={uploadingPhoto}
                      onChange={handlePhotoInput} data-testid="style-photo-input" />
                  </label>
                </div>

                {photos.length === 0 && pendingPhotos.length === 0 ? (
                  <p className="text-xs text-muted-foreground" data-testid="style-photo-empty">
                    Belum ada foto desain.
                  </p>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="style-photo-grid">
                    {photos.map((p) => (
                      <div key={p.id} className="relative rounded-lg border overflow-hidden group">
                        <img
                          src={`${API}${p.url}${(p.url || '').includes('?') ? '&' : '?'}auth=${encodeURIComponent(token || '')}`}
                          alt={p.caption || 'Foto desain'} className="h-24 w-full object-cover" loading="lazy"
                        />
                        <button onClick={() => handlePhotoDelete(p.id)} data-testid={`style-photo-delete-${p.id}`}
                          className="absolute top-1 right-1 p-1 rounded bg-background/90 text-destructive md:opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Hapus foto">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <p className="truncate px-2 py-1 text-[10px] text-muted-foreground">{p.caption || '—'}</p>
                      </div>
                    ))}
                    {pendingPhotos.map((f, i) => (
                      <div key={`pending-${i}`} className="relative rounded-lg border border-dashed overflow-hidden">
                        <img src={URL.createObjectURL(f)} alt={f.name} className="h-24 w-full object-cover" />
                        <button onClick={() => setPendingPhotos((p) => p.filter((_, idx) => idx !== i))}
                          data-testid={`style-photo-pending-remove-${i}`}
                          className="absolute top-1 right-1 p-1 rounded bg-background/90 text-destructive" title="Batalkan">
                          <X className="w-3.5 h-3.5" />
                        </button>
                        <p className="truncate px-2 py-1 text-[10px] text-amber-600 dark:text-amber-400">
                          Akan diunggah: {f.name}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t">
                <button onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg font-medium hover:bg-accent transition-colors">Batal</button>
                <button onClick={handleSave} className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:opacity-90 transition-opacity" data-testid="save-style-btn">
                  <Check className="w-4 h-4" /> Simpan
                </button>
              </div>
            </div>
          </GlassCard>
        </div>
      )}

      {/* ── Submit for Review Dialog ── */}
      {submitReviewDialog && (
        <SubmitForReviewDialog
          style={submitReviewDialog}
          onClose={() => setSubmitReviewDialog(null)}
          onSubmit={handleSubmitForReview}
        />
      )}

      {/* ── Owner Review Dialog ── */}
      {ownerReviewDialog && (
        <OwnerReviewDialog
          style={ownerReviewDialog}
          onClose={() => setOwnerReviewDialog(null)}
          onApprove={handleOwnerApprove}
          onReject={handleOwnerReject}
        />
      )}

      {/* ── Style Detail ── */}
      {detailStyleId && (
        <RnDStyleDetailPage
          token={token}
          styleId={detailStyleId}
          onClose={() => setDetailStyleId(null)}
        />
      )}
    </div>
  );
}

// ─── Sub-Components ────────────────────────────────────────────────────────────

function SubmitForReviewDialog({ style, onClose, onSubmit }) {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    await onSubmit(style.id, notes);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-foreground/50 flex items-center justify-center z-50 p-4" data-testid="submit-review-dialog">
      <GlassCard className="w-full max-w-md">
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-violet-100 dark:bg-violet-500/20 flex items-center justify-center">
              <Send className="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <div>
              <h3 className="font-bold text-lg">Ajukan ke Owner</h3>
              <p className="text-sm text-muted-foreground">{style.style_code} — {style.style_name}</p>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-violet-100 dark:bg-violet-500/10 border border-violet-300 dark:border-violet-400/20 text-sm text-violet-600 dark:text-violet-300">
            Style ini akan dikirim ke Owner untuk review dan persetujuan sebelum dilanjutkan ke produksi.
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Catatan untuk Owner (opsional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              rows="3"
              placeholder="Contoh: Style ini siap untuk review, sample sudah disiapkan..."
              data-testid="review-notes-input"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button onClick={onClose} className="px-4 py-2 border rounded-lg font-medium hover:bg-accent transition-colors">Batal</button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-foreground rounded-lg font-medium hover:bg-violet-700 transition-colors disabled:opacity-50"
              data-testid="confirm-submit-review-btn"
            >
              <Send className="w-4 h-4" />
              {saving ? 'Mengajukan...' : 'Ajukan Review'}
            </button>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

function OwnerReviewDialog({ style, onClose, onApprove, onReject }) {
  const [notes, setNotes] = useState('');
  const [action, setAction] = useState(null); // 'approve' | 'reject'
  const [saving, setSaving] = useState(false);

  const handleAction = async () => {
    if (action === 'reject' && !notes.trim()) { toast.error('Catatan penolakan wajib diisi'); return; }
    setSaving(true);
    if (action === 'approve') await onApprove(style.id, notes);
    else await onReject(style.id, notes);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-foreground/50 flex items-center justify-center z-50 p-4" data-testid="owner-review-dialog">
      <GlassCard className="w-full max-w-lg">
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-amber-700 dark:text-amber-400" />
              </div>
              <div>
                <h3 className="font-bold text-lg">Review Desain Style</h3>
                <p className="text-sm text-muted-foreground">{style.style_code} — {style.style_name}</p>
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 hover:bg-accent rounded"><X className="w-4 h-4" /></button>
          </div>

          {/* Style info */}
          <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-foreground/[0.04] border border-foreground/[0.08] text-sm">
            <InfoItem label="Kategori" value={style.category} />
            <InfoItem label="Buyer" value={style.buyer} />
            <InfoItem label="Fabric Type" value={style.fabric_type} />
            <InfoItem label="Season" value={style.season} />
            {style.description && (
              <div className="col-span-2">
                <span className="text-foreground/50 text-xs">Deskripsi:</span>
                <p className="text-foreground/80 mt-0.5">{style.description}</p>
              </div>
            )}
          </div>

          {/* Submission info */}
          {style.submitted_for_review_by && (
            <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-300">
              <Clock className="w-3.5 h-3.5" />
              Diajukan oleh <strong>{style.submitted_for_review_by}</strong>
              {style.review_notes && <span className="text-foreground/60">— {style.review_notes}</span>}
            </div>
          )}

          {/* Action selector */}
          <div>
            <p className="text-sm font-medium mb-2">Keputusan Owner:</p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setAction('approve')}
                className={`p-3 rounded-xl border-2 transition-all flex items-center gap-2 justify-center ${
                  action === 'approve'
                    ? 'border-green-400 bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300'
                    : 'border-foreground/10 bg-foreground/[0.04] text-foreground/60 hover:border-green-400/40'
                }`}
                data-testid="owner-approve-option"
              >
                <CheckCircle2 className="w-4 h-4" />
                Setujui Desain
              </button>
              <button
                onClick={() => setAction('reject')}
                className={`p-3 rounded-xl border-2 transition-all flex items-center gap-2 justify-center ${
                  action === 'reject'
                    ? 'border-red-400 bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-300'
                    : 'border-foreground/10 bg-foreground/[0.04] text-foreground/60 hover:border-red-400/40'
                }`}
                data-testid="owner-reject-option"
              >
                <XCircle className="w-4 h-4" />
                Tolak Desain
              </button>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium mb-1.5">
              {action === 'reject' ? 'Catatan Penolakan *' : 'Catatan (opsional)'}
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              rows="3"
              placeholder={action === 'reject' ? 'Jelaskan alasan penolakan...' : 'Catatan tambahan...'}
              data-testid="owner-review-notes-input"
            />
          </div>

          <div className="flex items-center justify-end gap-3">
            <button onClick={onClose} className="px-4 py-2 border rounded-lg font-medium hover:bg-accent transition-colors">Batal</button>
            <button
              onClick={handleAction}
              disabled={!action || saving}
              className={`flex items-center gap-2 px-5 py-2 rounded-lg font-medium transition-colors disabled:opacity-40 text-foreground ${
                action === 'approve' ? 'bg-green-600 hover:bg-green-700' :
                action === 'reject' ? 'bg-red-600 hover:bg-red-700' :
                'bg-primary'
              }`}
              data-testid="confirm-owner-review-btn"
            >
              {action === 'approve' ? <CheckCircle2 className="w-4 h-4" /> : action === 'reject' ? <XCircle className="w-4 h-4" /> : null}
              {saving ? 'Memproses...' : action === 'approve' ? 'Setujui' : action === 'reject' ? 'Tolak' : 'Pilih Keputusan'}
            </button>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

function InfoItem({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-xs text-foreground/50">{label}</span>
      <p className="text-sm text-foreground/80">{value}</p>
    </div>
  );
}
