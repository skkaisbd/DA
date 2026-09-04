import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Plus, Edit2, Trash2, X, Upload, Camera, FileText, Video, Image as ImageIcon,
  ArrowUp, ArrowDown, Link2, ListChecks, BookOpen, Info, Wand2, AlertTriangle,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { DataTable } from './DataTableV2';
import { PageHeader } from './moduleAtoms';
import ImportExportToolbar from './ImportExportToolbar';
import { toast } from 'sonner';
import { readField, readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

// F3 — kategori TIDAK LAGI hardcode. Dulu daftar ini hidup di 4 tempat berbeda
// dengan isi berbeda (Master Produk · Buyer Catalog Maklon · AI Quote · seeder),
// dan servernya menerima teks apa pun di luar daftar. Sekarang satu master:
// GET /api/rahaza/product-categories.
const DEFAULT_FORM = {
  code: '', name: '', category_id: '', material_kg_per_pcs: 0, bundle_size: 30,
  description: '', base_hpp: 0, retail_price: 0, weight_gram: 0,
};
const MAX_PHOTOS = 8;

const IMAGE_FALLBACK = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24' fill='none' stroke='%23cbd5e1' stroke-width='1.5'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Ccircle cx='8.5' cy='8.5' r='1.5'/%3E%3Cpath d='M21 15l-5-5L5 21'/%3E%3C/svg%3E`;

const fileUrl = (path, token) => `/api/files/${path}?auth=${encodeURIComponent(token)}`;

const rupiah = (v) => {
  const n = Number(v || 0);
  if (!n) return '—';
  return `Rp ${n.toLocaleString('id-ID')}`;
};

const HPP_SOURCE_LABEL = {
  // 2026-08-23 — sumber baru & DIDAHULUKAN: HPP lahir dari BOM × harga pembelian
  // + upah CMT/cutting (layar "HPP per Potong"), bukan ketikan master.
  bom: { text: 'BOM + pembelian', cls: 'bg-emerald-500/10 border-emerald-400/40 text-emerald-700 dark:text-emerald-300' },
  rnd: { text: 'dari R&D', cls: 'bg-blue-500/10 border-blue-400/40 text-blue-700 dark:text-blue-300' },
  manual: { text: 'manual', cls: 'bg-amber-500/10 border-amber-400/40 text-amber-700 dark:text-amber-300' },
  none: { text: 'belum ada', cls: 'bg-red-500/10 border-red-400/40 text-red-700 dark:text-red-300' },
};

function HppCell({ row }) {
  const src = HPP_SOURCE_LABEL[row?.hpp_source] || HPP_SOURCE_LABEL.none;
  const val = Number(row?.hpp || 0);
  return (
    <div className="flex flex-col gap-0.5" data-testid={`model-hpp-${row?.code}`}>
      <span className={val ? 'text-foreground font-medium' : 'text-muted-foreground'}>{rupiah(val)}</span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border w-fit ${src.cls}`}>{src.text}</span>
    </div>
  );
}

function ytId(url) {
  const m = String(url || '').match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([\w-]{11})/);
  return m ? m[1] : null;
}

function ImageThumb({ path, token, onDelete, large = false }) {
  const url = useMemo(() => fileUrl(path, token), [path, token]);
  const sz = large ? 'w-24 h-24' : 'w-12 h-12';
  return (
    <div className={`relative group ${sz} rounded-lg overflow-hidden border border-[var(--glass-border)] bg-[var(--glass-bg)]`}>
      <img src={url} alt="model" className="w-full h-full object-cover"
        onError={(e) => { e.target.src = IMAGE_FALLBACK; e.target.style.objectFit = 'contain'; e.target.style.padding = '6px'; }} />
      {onDelete && (
        <button onClick={onDelete}
          className="absolute top-0.5 right-0.5 p-1 rounded-full bg-red-500/90 text-white opacity-0 group-hover:opacity-100 transition-opacity"
          data-testid="model-image-delete" title="Hapus foto">
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PANDUAN PRODUKSI DIALOG — Foto Produk + SOP langkah + Video/Referensi
// ════════════════════════════════════════════════════════════════════════════
function PanduanProduksiDialog({ model, token, onClose, onUpdated }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [tab, setTab] = useState('foto');
  const [paths, setPaths] = useState(model.image_paths || []);
  const [steps, setSteps] = useState(() =>
    (model.sop_steps || []).map((s) => ({
      id: s.id || crypto.randomUUID(), title: s.title || '', description: s.description || '', image_path: s.image_path || '',
    }))
  );
  const [videos, setVideos] = useState(() => (model.reference_videos || []).map((v) => ({ url: v.url || '', title: v.title || '' })));
  const [refImages, setRefImages] = useState(() => (model.reference_images || []).map((v) => ({ url: v.url || '', caption: v.caption || '' })));
  const [uploading, setUploading] = useState(false);
  const [stepUploading, setStepUploading] = useState(null);
  const [saving, setSaving] = useState(false);

  // ── Foto Produk ────────────────────────────────────────────────────────────
  const handleUploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (paths.length >= MAX_PHOTOS) { toast.error(`Maksimal ${MAX_PHOTOS} foto per model`); return; }
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch(`/api/rahaza/models/${model.id}/images`, { method: 'POST', headers, body: fd });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Upload gagal'); return; }
      const data = await r.json();
      setPaths(data.image_paths || []);
      toast.success('Foto diupload');
      onUpdated && onUpdated();
    } finally { setUploading(false); e.target.value = ''; }
  };

  const handleDeletePhoto = async (path) => {
    if (!window.confirm('Hapus foto ini?')) return;
    const r = await fetch(`/api/rahaza/models/${model.id}/images`, {
      method: 'DELETE', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ storage_path: path }),
    });
    if (r.ok) { const data = await r.json(); setPaths(data.image_paths || []); toast.success('Foto dihapus'); onUpdated && onUpdated(); }
    else toast.error('Gagal menghapus foto');
  };

  // ── SOP langkah ──────────────────────────────────────────────────────────────
  const addStep = () => setSteps((s) => [...s, { id: crypto.randomUUID(), title: '', description: '', image_path: '' }]);
  const removeStep = (idx) => setSteps((s) => s.filter((_, i) => i !== idx));
  const updateStep = (idx, patch) => setSteps((s) => s.map((st, i) => (i === idx ? { ...st, ...patch } : st)));
  const moveStep = (idx, dir) => setSteps((s) => {
    const j = idx + dir; if (j < 0 || j >= s.length) return s;
    const c = [...s]; [c[idx], c[j]] = [c[j], c[idx]]; return c;
  });

  const uploadStepPhoto = async (idx, file) => {
    if (!file) return;
    setStepUploading(idx);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch(`/api/rahaza/models/${model.id}/sop-image`, { method: 'POST', headers, body: fd });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Upload gagal'); return; }
      const data = await r.json();
      updateStep(idx, { image_path: data.storage_path });
      toast.success('Foto langkah diupload');
    } finally { setStepUploading(null); }
  };

  // ── Video & Referensi ─────────────────────────────────────────────────────────
  const addVideo = () => setVideos((v) => [...v, { url: '', title: '' }]);
  const removeVideo = (idx) => setVideos((v) => v.filter((_, i) => i !== idx));
  const updateVideo = (idx, patch) => setVideos((v) => v.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const addRefImage = () => setRefImages((v) => [...v, { url: '', caption: '' }]);
  const removeRefImage = (idx) => setRefImages((v) => v.filter((_, i) => i !== idx));
  const updateRefImage = (idx, patch) => setRefImages((v) => v.map((it, i) => (i === idx ? { ...it, ...patch } : it)));

  const saveSop = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/rahaza/models/${model.id}/sop`, {
        method: 'PUT', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ sop_steps: steps, reference_videos: videos, reference_images: refImages }),
      });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Gagal menyimpan'); return; }
      toast.success('Panduan Produksi tersimpan');
      onUpdated && onUpdated();
      onClose();
    } finally { setSaving(false); }
  };

  const TabBtn = ({ id, icon: Icon, label, count }) => (
    <button onClick={() => setTab(id)}
      className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors ${
        tab === id ? 'bg-primary/10 border-primary/40 text-foreground' : 'border-[var(--glass-border)] text-muted-foreground hover:bg-[var(--glass-bg-hover)]'}`}
      data-testid={`panduan-tab-${id}`}>
      <Icon className="w-4 h-4" /> {label}
      {count != null && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-foreground/10">{count}</span>}
    </button>
  );

  return (
    <Modal onClose={onClose} title={`Panduan Produksi · ${model.code} — ${model.name}`} size="lg">
      <div className="space-y-4" data-testid="panduan-produksi-dialog">
        <div className="flex items-center gap-2 flex-wrap">
          <TabBtn id="foto" icon={Camera} label="Foto Produk" count={paths.length} />
          <TabBtn id="sop" icon={ListChecks} label="SOP Produksi" count={steps.length} />
          <TabBtn id="video" icon={Video} label="Video & Referensi" count={videos.length + refImages.length} />
        </div>

        {/* ── FOTO ── */}
        {tab === 'foto' && (
          <div className="space-y-3" data-testid="panduan-foto-tab">
            <p className="text-sm text-muted-foreground">
              Upload sampai <b>{MAX_PHOTOS} foto jadi / referensi</b> (max 5MB). Tampil di LKP & Portal Vendor CMT.
            </p>
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-3">
              {paths.map((p) => <ImageThumb key={p} path={p} token={token} large onDelete={() => handleDeletePhoto(p)} />)}
              {paths.length < MAX_PHOTOS && (
                <label className="w-24 h-24 rounded-lg border-2 border-dashed border-[var(--glass-border)] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-primary hover:bg-[var(--glass-bg-hover)] transition-colors"
                  data-testid="model-image-upload-label">
                  {uploading ? <span className="text-xs text-muted-foreground">Uploading...</span> : (<>
                    <Upload className="w-5 h-5 text-muted-foreground" />
                    <span className="text-[10px] text-muted-foreground">Tambah foto</span>
                  </>)}
                  <input type="file" accept="image/*" className="hidden" disabled={uploading} onChange={handleUploadPhoto} data-testid="model-image-upload-input" />
                </label>
              )}
            </div>
            <div className="text-xs text-muted-foreground">{paths.length}/{MAX_PHOTOS} foto · JPG, PNG, WebP. (Tersimpan otomatis)</div>
          </div>
        )}

        {/* ── SOP ── */}
        {tab === 'sop' && (
          <div className="space-y-3" data-testid="panduan-sop-tab">
            <p className="text-sm text-muted-foreground">
              Tata cara pembuatan model — langkah berurutan. Vendor CMT membaca ini untuk tahu cara produksi.
            </p>
            <div className="space-y-3 max-h-[45vh] overflow-y-auto pr-1">
              {steps.map((st, idx) => (
                <div key={st.id} className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3" data-testid={`sop-step-${idx}`}>
                  <div className="flex items-start gap-3">
                    <div className="flex flex-col items-center gap-1 pt-1">
                      <span className="w-6 h-6 rounded-full bg-primary/15 text-primary text-xs font-bold flex items-center justify-center">{idx + 1}</span>
                      <button onClick={() => moveStep(idx, -1)} disabled={idx === 0} className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" title="Naik"><ArrowUp className="w-3.5 h-3.5" /></button>
                      <button onClick={() => moveStep(idx, 1)} disabled={idx === steps.length - 1} className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" title="Turun"><ArrowDown className="w-3.5 h-3.5" /></button>
                    </div>
                    <div className="flex-1 space-y-2">
                      <GlassInput value={st.title} onChange={(e) => updateStep(idx, { title: e.target.value })}
                        placeholder="Judul langkah (cth: Potong kain sesuai pola)" data-testid={`sop-step-${idx}-title`} />
                      <textarea value={st.description} onChange={(e) => updateStep(idx, { description: e.target.value })}
                        placeholder="Deskripsi / instruksi detail..." rows={2}
                        className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm text-foreground resize-y"
                        data-testid={`sop-step-${idx}-desc`} />
                      <div className="flex items-center gap-3">
                        {st.image_path ? (
                          <div className="relative group">
                            <img src={fileUrl(st.image_path, token)} alt="step" className="w-20 h-20 rounded-lg object-cover border border-[var(--glass-border)]"
                              onError={(e) => { e.target.src = IMAGE_FALLBACK; }} />
                            <button onClick={() => updateStep(idx, { image_path: '' })}
                              className="absolute -top-1.5 -right-1.5 p-1 rounded-full bg-red-500/90 text-white" title="Hapus foto langkah"><X className="w-3 h-3" /></button>
                          </div>
                        ) : (
                          <label className="w-20 h-20 rounded-lg border-2 border-dashed border-[var(--glass-border)] flex flex-col items-center justify-center gap-1 cursor-pointer hover:border-primary text-muted-foreground"
                            data-testid={`sop-step-${idx}-photo-label`}>
                            {stepUploading === idx ? <span className="text-[9px]">...</span> : (<><ImageIcon className="w-4 h-4" /><span className="text-[9px]">Foto</span></>)}
                            <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadStepPhoto(idx, e.target.files?.[0])} />
                          </label>
                        )}
                        <button onClick={() => removeStep(idx)} className="ml-auto flex items-center gap-1 text-xs text-red-400 hover:text-red-300" data-testid={`sop-step-${idx}-remove`}>
                          <Trash2 className="w-3.5 h-3.5" /> Hapus langkah
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {steps.length === 0 && (
                <div className="text-center py-6 text-sm text-muted-foreground border border-dashed border-[var(--glass-border)] rounded-lg">
                  Belum ada langkah. Klik "Tambah Langkah".
                </div>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={addStep} data-testid="sop-add-step-btn"><Plus className="w-4 h-4 mr-1" /> Tambah Langkah</Button>
          </div>
        )}

        {/* ── VIDEO & REFERENSI ── */}
        {tab === 'video' && (
          <div className="space-y-5" data-testid="panduan-video-tab">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Video className="w-4 h-4 text-primary" /> Referensi Video</span>
                <Button variant="outline" size="sm" onClick={addVideo} data-testid="ref-add-video-btn"><Plus className="w-4 h-4 mr-1" /> Video</Button>
              </div>
              <div className="space-y-2">
                {videos.map((v, idx) => {
                  const yid = ytId(v.url);
                  return (
                    <div key={idx} className="flex items-center gap-3 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2" data-testid={`ref-video-${idx}`}>
                      {yid ? <img src={`https://img.youtube.com/vi/${yid}/default.jpg`} alt="yt" className="w-16 h-12 rounded object-cover" />
                           : <div className="w-16 h-12 rounded bg-foreground/10 flex items-center justify-center"><Video className="w-5 h-5 text-muted-foreground" /></div>}
                      <div className="flex-1 space-y-1">
                        <GlassInput value={v.title} onChange={(e) => updateVideo(idx, { title: e.target.value })} placeholder="Judul video" data-testid={`ref-video-${idx}-title`} />
                        <GlassInput value={v.url} onChange={(e) => updateVideo(idx, { url: e.target.value })} placeholder="https://youtu.be/... atau link Drive" data-testid={`ref-video-${idx}-url`} />
                      </div>
                      <button onClick={() => removeVideo(idx)} className="p-1.5 text-red-400 hover:text-red-300" data-testid={`ref-video-${idx}-remove`}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  );
                })}
                {videos.length === 0 && <div className="text-xs text-muted-foreground py-2">Belum ada video referensi.</div>}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Link2 className="w-4 h-4 text-primary" /> Gambar Referensi (link)</span>
                <Button variant="outline" size="sm" onClick={addRefImage} data-testid="ref-add-image-btn"><Plus className="w-4 h-4 mr-1" /> Gambar</Button>
              </div>
              <div className="space-y-2">
                {refImages.map((v, idx) => (
                  <div key={idx} className="flex items-center gap-3 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2" data-testid={`ref-image-${idx}`}>
                    <img src={v.url || IMAGE_FALLBACK} alt="ref" className="w-14 h-14 rounded object-cover bg-foreground/5" onError={(e) => { e.target.src = IMAGE_FALLBACK; e.target.style.objectFit = 'contain'; e.target.style.padding = '4px'; }} />
                    <div className="flex-1 space-y-1">
                      <GlassInput value={v.caption} onChange={(e) => updateRefImage(idx, { caption: e.target.value })} placeholder="Keterangan" data-testid={`ref-image-${idx}-caption`} />
                      <GlassInput value={v.url} onChange={(e) => updateRefImage(idx, { url: e.target.value })} placeholder="https://.../gambar.jpg" data-testid={`ref-image-${idx}-url`} />
                    </div>
                    <button onClick={() => removeRefImage(idx)} className="p-1.5 text-red-400 hover:text-red-300" data-testid={`ref-image-${idx}-remove`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                {refImages.length === 0 && <div className="text-xs text-muted-foreground py-2">Belum ada gambar referensi.</div>}
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-[var(--glass-border)]">
          <Button variant="ghost" onClick={onClose} data-testid="panduan-close">Tutup</Button>
          <Button onClick={saveSop} disabled={saving} data-testid="panduan-save">
            {saving ? 'Menyimpan...' : 'Simpan Panduan (SOP + Video)'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function RahazaModelsModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [catFilter, setCatFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [autoCode, setAutoCode] = useState(true);
  const [saving, setSaving] = useState(false);
  const [panduanModel, setPanduanModel] = useState(null);
  const [techpackModel, setTechpackModel] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const [rm, rc] = await Promise.all([
        fetch('/api/rahaza/models', { headers }),
        fetch('/api/rahaza/product-categories', { headers }),
      ]);
      if (rm.ok) setRows(await rm.json());
      if (rc.ok) {
        const d = await rc.json();
        setCategories(d.categories || []);
      }
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const visibleRows = useMemo(
    () => (catFilter ? rows.filter((r) => r.category_id === catFilter) : rows),
    [rows, catFilter],
  );

  const noCategoryCount = useMemo(
    () => rows.filter((r) => !r.category_id && r.active !== false).length,
    [rows],
  );

  const selectedCat = useMemo(
    () => categories.find((c) => c.id === form.category_id) || null,
    [categories, form.category_id],
  );

  const openCreate = () => {
    setEditing(null);
    setForm({ ...DEFAULT_FORM, category_id: categories[0]?.id || '' });
    setAutoCode(true);
    setModalOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row);
    setForm({
      code: row.code || '', name: row.name || '', category_id: row.category_id || '',
      material_kg_per_pcs: readNumber(row, FIELD.materialKgPerPcs), bundle_size: row.bundle_size || 30,
      description: row.description || '',
      base_hpp: Number(row.base_hpp || 0), retail_price: Number(row.retail_price || 0),
      weight_gram: Number(row.weight_gram || 0),
    });
    setAutoCode(false);
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name) { toast.error('Nama model wajib diisi'); return; }
    if (!form.category_id) { toast.error('Kategori wajib dipilih'); return; }
    if (!editing && !autoCode && !form.code) { toast.error('Kode wajib diisi (atau aktifkan kode otomatis)'); return; }
    setSaving(true);
    try {
      const url = editing ? `/api/rahaza/models/${editing.id}` : '/api/rahaza/models';
      const method = editing ? 'PUT' : 'POST';
      const payload = { ...form };
      if (!editing && autoCode) delete payload.code;   // K-1A: server yang membuat kode
      const r = await fetch(url, { method, headers, body: JSON.stringify(payload) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { toast.error(d.detail || `HTTP ${r.status}`); return; }
      if (editing) {
        const p = d.propagated || {};
        const extra = (p.fg || p.catalog_items)
          ? ` · ikut disegarkan: ${p.fg || 0} barang jadi, ${p.catalog_items || 0} item katalog`
          : '';
        toast.success(`Model diperbarui${extra}`);
      } else {
        toast.success(`Model dibuat · kode ${d.code || ''}`);
      }
      setModalOpen(false);
      fetchRows();
    } finally { setSaving(false); }
  };

  const handleDelete = async (row) => {
    if (!window.confirm(
      `Nonaktifkan model ${row.code}?\n\nItem katalog marketing yang menawarkan produk ini akan ikut dinonaktifkan `
      + `supaya barang yang sudah dihentikan tidak bisa dijual.`)) return;
    const r = await fetch(`/api/rahaza/models/${row.id}`, { method: 'DELETE', headers });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      const n = d.affected_count || 0;
      toast.success(n ? `Model dinonaktifkan · ${n} item katalog ikut dinonaktifkan` : 'Model dinonaktifkan');
      fetchRows();
    } else toast.error(d.detail || 'Gagal menonaktifkan');
  };

  const columns = [
    { key: 'code', label: 'Kode', sortable: true, render: (row) => <span className="font-mono text-xs">{row.code}</span> },
    { key: 'name', label: 'Nama Model', sortable: true },
    {
      key: 'category_name', label: 'Kategori', sortable: true,
      render: (row) => {
        if (!row.category_id) {
          return (
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border bg-amber-500/10 border-amber-400/40 text-amber-700 dark:text-amber-300"
              title="Kategori belum dipilih — tidak ditebak oleh sistem" data-testid={`model-nocat-${row.code}`}>
              <AlertTriangle className="w-3 h-3" /> belum dipilih
            </span>
          );
        }
        return (
          <span className="inline-flex items-center gap-1.5" data-testid={`model-cat-${row.code}`}>
            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/30">
              {row.category_code || '—'}
            </span>
            <span className="text-sm">{row.category_name || row.category}</span>
          </span>
        );
      },
    },
    { key: 'hpp', label: 'HPP', sortable: true, render: (row) => <HppCell row={row} /> },
    {
      key: 'retail_price', label: 'Harga Jual Resmi', sortable: true,
      render: (row) => (
        <span className={Number(row.retail_price || 0) ? 'text-foreground' : 'text-muted-foreground'}
          data-testid={`model-retail-${row.code}`}>
          {rupiah(row.retail_price)}
        </span>
      ),
    },
    {
      key: 'weight_gram', label: 'Berat', sortable: true,
      render: (row) => (
        <span className={Number(row.weight_gram || 0) ? 'text-foreground' : 'text-muted-foreground'}
          data-testid={`model-weight-${row.code}`}>
          {Number(row.weight_gram || 0) ? `${Number(row.weight_gram)} g` : '—'}
        </span>
      ),
    },
    {
      key: 'image_paths', label: 'Foto',
      render: (row) => {
        const arr = Array.isArray(row?.image_paths) ? row.image_paths : [];
        return (
          <div className="flex items-center gap-1.5" data-testid={`model-images-${row.code}`}>
            {arr.slice(0, 3).map((p) => <ImageThumb key={p} path={p} token={token} />)}
            {arr.length > 3 && <span className="text-[10px] text-muted-foreground">+{arr.length - 3}</span>}
          </div>
        );
      },
    },
    {
      key: 'sop_steps', label: 'Panduan',
      render: (row) => {
        const nSop = (row?.sop_steps || []).length;
        const nVid = (row?.reference_videos || []).length;
        return (
          <button
            onClick={(e) => { e.stopPropagation(); setPanduanModel(row); }}
            className="px-2 py-1 rounded text-xs border border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] flex items-center gap-1 text-muted-foreground hover:text-foreground"
            data-testid={`model-panduan-${row.code}`} title="Panduan Produksi (SOP + Foto + Video)">
            <BookOpen className="w-3.5 h-3.5" />
            <span>{nSop} SOP · {nVid} video</span>
          </button>
        );
      },
    },
    {
      key: 'techpack', label: 'Tech Pack',
      render: (row) => {
        const tp = row?.techpack;
        if (!tp) return <span className="text-xs text-muted-foreground">—</span>;
        return (
          <button onClick={(e) => { e.stopPropagation(); setTechpackModel(row); }}
            className="px-2 py-1 rounded text-xs border border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] flex items-center gap-1 text-muted-foreground hover:text-foreground"
            data-testid={`model-techpack-${row.code}`} title="Ringkasan spesifikasi dari R&D (read-only)">
            <FileText className="w-3.5 h-3.5" />
            <span>v{tp.version ?? '?'} · {(tp.bom_items || []).length} bahan</span>
          </button>
        );
      },
    },
    { key: 'material_kg_per_pcs', label: 'Bahan utama/pcs (kg)', render: (row) => { const v = readNumber(row, FIELD.materialKgPerPcs); return v ? Number(v).toFixed(3) : '-'; } },
    { key: 'bundle_size', label: 'Bundle', render: (row, v) => `${v || 30} pcs` },
    {
      key: 'actions', label: 'Aksi',
      render: (row) => (
        <div className="flex items-center gap-1">
          <button onClick={(e) => { e.stopPropagation(); openEdit(row); }}
            className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" title="Edit" data-testid={`model-edit-${row.code}`}>
            <Edit2 className="w-3.5 h-3.5" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); handleDelete(row); }}
            className="p-1.5 rounded hover:bg-red-100 dark:bg-red-500/20 text-muted-foreground hover:text-red-700 dark:text-red-400" title="Nonaktifkan" data-testid={`model-deactivate-${row.code}`}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4" data-testid="rahaza-models-module">
      <PageHeader
        title="Model Produk (Internal)"
        subtitle="Master model produksi: kategori, HPP, harga jual resmi, berat, + Panduan Produksi (SOP, foto, video) yang dibaca Vendor CMT."
        actions={
          <>
            <select value={catFilter} onChange={(e) => setCatFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm text-foreground"
              data-testid="model-filter-category">
              <option value="">Semua kategori</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.sku_prefix} · {c.name}</option>)}
            </select>
            <ImportExportToolbar collectionKey="models" label="Model Produk" onImported={fetchRows} />
            <Button onClick={openCreate} className="gap-1.5" data-testid="model-create-btn">
              <Plus className="w-4 h-4" /> Tambah Model
            </Button>
          </>
        }
      />

      {noCategoryCount > 0 && (
        <div className="flex items-start gap-2 text-[12px] text-amber-800 dark:text-amber-200 bg-amber-500/10 border border-amber-400/40 rounded-lg p-3"
          data-testid="model-nocat-banner">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            <b>{noCategoryCount} produk belum punya kategori.</b> Sistem <b>tidak menebak</b> —
            grouping & filter katalog marketing baru bisa dipercaya setelah kategorinya dipilih.
            Buka Edit pada baris bertanda “belum dipilih”.
          </span>
        </div>
      )}

      <GlassCard>
        <DataTable tableId="rahaza-models" columns={columns} rows={visibleRows} loading={loading}
          emptyTitle="Belum ada model" emptyDescription="Model internal idealnya lahir dari R&D. Klik Tambah Model untuk input manual." rowKey="id" />
      </GlassCard>

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? `Edit Model · ${editing.code}` : 'Tambah Model Baru'} size="md">
          <div className="space-y-3" data-testid="model-form">
            {!editing && (
              <div className="flex items-start gap-2 text-[11px] text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-400/30 rounded-lg p-2" data-testid="model-rnd-hint">
                <Info className="w-4 h-4 shrink-0 mt-0.5" />
                <span><b>Disarankan lewat R&D:</b> produk internal idealnya lahir dari modul R&D (publish style → otomatis jadi master + bawa foto desain). Input manual ini untuk kasus khusus.</span>
              </div>
            )}
            <div>
              <label className="text-xs text-muted-foreground">Nama Model <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Contoh: Vest Rajut Formal" data-testid="model-form-name" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Kategori <span className="text-red-700 dark:text-red-400">*</span></label>
              <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-sm text-foreground" data-testid="model-form-category">
                <option value="">— pilih kategori —</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.sku_prefix})</option>)}
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">
                Dipakai untuk filter & grouping katalog marketing. Daftar ini diambil dari tab <b>Kategori</b>.
              </p>
            </div>

            {/* ── Kode produk: otomatis dari prefix kategori (K-1A) ── */}
            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-muted-foreground">Kode Produk</label>
                {!editing && (
                  <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none">
                    <input type="checkbox" checked={autoCode} onChange={(e) => setAutoCode(e.target.checked)}
                      data-testid="model-form-autocode" />
                    Buat otomatis
                  </label>
                )}
              </div>
              {!editing && autoCode ? (
                <div className="flex items-center gap-2 text-sm text-foreground" data-testid="model-form-code-auto">
                  <Wand2 className="w-4 h-4 text-primary" />
                  <span className="font-mono">
                    {selectedCat ? `${selectedCat.sku_prefix}-0001` : '(pilih kategori dulu)'}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    — nomor urut berikutnya dibuat server; SKU varian menjadi{' '}
                    <span className="font-mono">{selectedCat ? `${selectedCat.sku_prefix}-0001-NVY-M` : '…'}</span>
                  </span>
                </div>
              ) : (
                <GlassInput value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                  placeholder="Contoh: VST-0001" data-testid="model-form-code" />
              )}
            </div>

            {/* ── HPP · Harga Jual · Berat (F5 — menutup P1 & P4) ── */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">HPP dasar (Rp)</label>
                <GlassInput type="number" min="0" value={form.base_hpp}
                  onChange={(e) => setForm({ ...form, base_hpp: e.target.value })} data-testid="model-form-base-hpp" />
                <p className="text-[10px] text-muted-foreground mt-1">Dipakai bila belum ada HPP dari R&D.</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Harga jual resmi (Rp)</label>
                <GlassInput type="number" min="0" value={form.retail_price}
                  onChange={(e) => setForm({ ...form, retail_price: e.target.value })} data-testid="model-form-retail-price" />
                <p className="text-[10px] text-muted-foreground mt-1">Jadi nilai awal harga di katalog.</p>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Berat satuan (gram)</label>
                <GlassInput type="number" min="0" value={form.weight_gram}
                  onChange={(e) => setForm({ ...form, weight_gram: e.target.value })} data-testid="model-form-weight-gram" />
                <p className="text-[10px] text-muted-foreground mt-1">Dipakai hitung biaya kirim.</p>
              </div>
            </div>

            {editing && (
              <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 text-[11px] space-y-1"
                data-testid="model-form-hpp-info">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">HPP berlaku:</span>
                  <span className="font-medium text-foreground">{rupiah(editing.hpp)}</span>
                  <span className={`px-1.5 py-0.5 rounded-full border ${(HPP_SOURCE_LABEL[editing.hpp_source] || HPP_SOURCE_LABEL.none).cls}`}>
                    {(HPP_SOURCE_LABEL[editing.hpp_source] || HPP_SOURCE_LABEL.none).text}
                  </span>
                  {editing.hpp_updated_at && (
                    <span className="text-muted-foreground">
                      diperbarui {String(editing.hpp_updated_at).slice(0, 10)}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground">
                  Perubahan kategori / berat / harga di sini <b>otomatis turun</b> ke Barang Jadi (FG)
                  dan item katalog marketing yang tertaut.
                </p>
                {/* 2026-08-23 — HPP produk tidak lagi perlu diketik: layar "HPP per
                    Potong" menghitungnya dari BOM × harga pembelian + upah CMT/cutting. */}
                <button type="button"
                  onClick={() => (typeof onNavigate === 'function'
                    ? onNavigate('fin-hpp-produk')
                    : (window.location.hash = 'fin-hpp-produk'))}
                  className="text-[hsl(var(--primary))] underline"
                  data-testid="model-goto-hpp-potong">
                  Hitung HPP dari BOM &amp; harga pembelian (HPP per Potong) →
                </button>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Ukuran Bundle (pcs)</label>
                <GlassInput type="number" value={form.bundle_size}
                  onChange={(e) => setForm({ ...form, bundle_size: parseInt(e.target.value) || 30 })} data-testid="model-form-bundle-size" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Bahan utama/pcs (kg)</label>
                <GlassInput type="number" step="0.001" value={form.material_kg_per_pcs}
                  onChange={(e) => setForm({ ...form, material_kg_per_pcs: e.target.value })} data-testid="model-form-material-kg" />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Deskripsi</label>
              <GlassInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Opsional" data-testid="model-form-description" />
            </div>
            {editing && (
              <p className="text-[11px] text-muted-foreground bg-[var(--glass-bg)] p-2 rounded border border-[var(--glass-border)]">
                💡 <b>Panduan Produksi</b> (SOP, foto jadi, video) dikelola lewat tombol <BookOpen className="inline w-3 h-3" /> di kolom Panduan pada tabel.
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
              <Button variant="ghost" onClick={() => setModalOpen(false)} data-testid="model-form-cancel">Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="model-form-save">{saving ? 'Menyimpan...' : 'Simpan'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {panduanModel && (
        <PanduanProduksiDialog model={panduanModel} token={token} onClose={() => setPanduanModel(null)} onUpdated={fetchRows} />
      )}

      {techpackModel && (
        <Modal onClose={() => setTechpackModel(null)}
          title={`Tech Pack (R&D) · ${techpackModel.code} — ${techpackModel.name}`} size="md">
          <div className="space-y-3 text-sm" data-testid="model-techpack-dialog">
            <p className="text-[11px] text-muted-foreground">
              Ringkasan spesifikasi hasil promosi dari R&D — <b>hanya baca</b>. Sumber kebenarannya
              tetap Tech Pack di modul R&D.
            </p>
            {(() => {
              const tp = techpackModel.techpack || {};
              const rowsTp = [
                ['Versi', tp.version ?? '—'],
                ['Rentang size', tp.size_range || '—'],
                ['Base size', tp.base_size || '—'],
                ['Jenis jahitan', tp.stitch_type || '—'],
                ['Kelonggaran jahit', tp.seam_allowance_mm != null ? `${tp.seam_allowance_mm} mm` : '—'],
                ['Jumlah bahan (BOM)', (tp.bom_items || []).length],
                ['Jumlah ukuran diukur', (tp.measurements || []).length],
              ];
              return (
                <div className="rounded-lg border border-[var(--glass-border)] overflow-hidden">
                  {rowsTp.map(([k, v], i) => (
                    <div key={k} className={`flex items-center justify-between px-3 py-2 ${i % 2 ? 'bg-[var(--glass-bg)]' : ''}`}>
                      <span className="text-muted-foreground text-xs">{k}</span>
                      <span className="text-foreground">{String(v)}</span>
                    </div>
                  ))}
                  {tp.construction_notes && (
                    <div className="px-3 py-2 border-t border-[var(--glass-border)]">
                      <div className="text-muted-foreground text-xs mb-1">Catatan konstruksi</div>
                      <pre className="whitespace-pre-wrap text-xs text-foreground font-sans">{tp.construction_notes}</pre>
                    </div>
                  )}
                </div>
              );
            })()}
            <div className="flex justify-end pt-2 border-t border-[var(--glass-border)]">
              <Button variant="ghost" onClick={() => setTechpackModel(null)} data-testid="model-techpack-close">Tutup</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
