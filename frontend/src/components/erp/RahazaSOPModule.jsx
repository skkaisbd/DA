import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { BookOpen, Plus, Edit, Trash2, CheckCircle, XCircle, AlertTriangle, Search, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GlassCard, GlassInput, GlassPanel } from '@/components/ui/glass';
import Modal from './Modal';
import { toast } from 'sonner';

/* ─── RahazaSOPModule — Admin SOP Management (Phase 18D) ─────────────────────
   Admin interface for creating and managing SOPs per model×process.
 ───────────────────────────────────────────────────────────────────────── */

const EMPTY_FORM = {
  model_id: '',
  process_id: '',
  title: '',
  content_markdown: '',
  sam_minutes: '',
  target_pcs_per_operator: '',
  attachments: [],
  active: true,
};

export default function RahazaSOPModule({ token }) {
  const [sops, setSops] = useState([]);
  const [models, setModels] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [filterModel, setFilterModel] = useState('');
  const [filterProcess, setFilterProcess] = useState('');
  const [modal, setModal] = useState(null); // null | 'create' | 'edit'
  const [editItem, setEditItem] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const loadSops = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterModel) params.set('model_id', filterModel);
      if (filterProcess) params.set('process_id', filterProcess);
      const r = await fetch(`/api/rahaza/sop?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) {
        const data = await r.json();
        setSops(data.sops || []);
      }
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterModel, filterProcess]);

  const loadMasters = useCallback(async () => {
    const [mr, pr] = await Promise.all([
      fetch('/api/rahaza/models?active=true', { headers: { Authorization: `Bearer ${token}` } }),
      fetch('/api/rahaza/processes', { headers: { Authorization: `Bearer ${token}` } }),
    ]);
    if (mr.ok) setModels(await mr.json());
    if (pr.ok) setProcesses(await pr.json());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { loadSops(); }, [loadSops]);
  useEffect(() => { loadMasters(); }, [loadMasters]);

  const openCreate = () => { setForm(EMPTY_FORM); setEditItem(null); setModal('create'); };
  const openEdit = (sop) => { setForm({ ...sop, sam_minutes: sop.sam_minutes ?? '', target_pcs_per_operator: sop.target_pcs_per_operator ?? '', attachments: sop.attachments || [] }); setEditItem(sop); setModal('edit'); };
  const closeModal = () => { setModal(null); setEditItem(null); };

  const handleSave = async () => {
    if (!form.model_id || !form.process_id) {
      toast.error('Model dan proses wajib dipilih');
      return;
    }
    setSaving(true);
    try {
      const url = modal === 'edit' ? `/api/rahaza/sop/${editItem.id}` : '/api/rahaza/sop';
      const method = modal === 'edit' ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers, body: JSON.stringify(form) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      toast.success(modal === 'edit' ? 'SOP diperbarui' : 'SOP dibuat');
      closeModal();
      loadSops();
    } catch (e) { toast.error(e.message); } finally { setSaving(false); }
  };

  const handleDelete = async (sop) => {
    if (!window.confirm(`Nonaktifkan SOP "${sop.title}"?`)) return;
    setDeleting(sop.id);
    try {
      const r = await fetch(`/api/rahaza/sop/${sop.id}`, { method: 'DELETE', headers });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
      toast.success('SOP dinonaktifkan');
      loadSops();
    } catch (e) { toast.error(e.message); } finally { setDeleting(null); }
  };

  const filtered = sops.filter(s => {
    if (!searchQ) return true;
    const q = searchQ.toLowerCase();
    return (
      s.title?.toLowerCase().includes(q) ||
      s.model_code?.toLowerCase().includes(q) ||
      s.process_code?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6" data-testid="sop-module">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-[hsl(var(--primary))]" />
            SOP Produksi
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Instruksi kerja per Model × Proses · Tersedia di OperatorView
          </p>
        </div>
        <Button onClick={openCreate} className="gap-2" data-testid="sop-add-btn">
          <Plus className="w-4 h-4" /> Tambah SOP
        </Button>
      </div>

      {/* Filters */}
      <GlassPanel className="p-3 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <GlassInput
            className="pl-8 h-9"
            placeholder="Cari model, proses, judul..."
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
            data-testid="sop-search"
          />
        </div>
        <SmartNativeSelect
          value={filterModel}
          onChange={e => setFilterModel(e.target.value)}
          className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="sop-filter-model"
        >
          <option value="">Semua Model</option>
          {models.map(m => <option key={m.id} value={m.id}>{`${m.code} — ${m.name}`}</option>)}
        </SmartNativeSelect>
        <SmartNativeSelect
          value={filterProcess}
          onChange={e => setFilterProcess(e.target.value)}
          className="h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="sop-filter-process"
        >
          <option value="">Semua Proses</option>
          {processes.map(p => <option key={p.id} value={p.id}>{`${p.code} — ${p.name}`}</option>)}
        </SmartNativeSelect>
      </GlassPanel>

      {/* SOP list */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-8 text-center">
          <BookOpen className="w-10 h-10 mx-auto mb-3 text-foreground/20" />
          <p className="text-sm font-medium text-foreground">Belum ada SOP</p>
          <p className="text-xs text-muted-foreground mt-1">Tambah instruksi kerja untuk operator.</p>
          <Button onClick={openCreate} className="mt-4 gap-2">
            <Plus className="w-4 h-4" /> Tambah SOP Pertama
          </Button>
        </GlassCard>
      ) : (
        <div className="grid gap-3">
          {filtered.map(sop => (
            <GlassCard key={sop.id} className="p-4" data-testid={`sop-card-${sop.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 flex items-center justify-center flex-shrink-0">
                    <BookOpen className="w-4.5 h-4.5 text-[hsl(var(--primary))]" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-foreground">{sop.title}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                      <span>v{sop.version}</span>
                      {sop.sam_minutes && <span className="text-primary font-mono">SAM: {sop.sam_minutes}m</span>}
                      {sop.target_pcs_per_operator && <span className="text-emerald-300 font-mono">{sop.target_pcs_per_operator} pcs/op</span>}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {sop.model_code} · {sop.process_code}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border ${
                        sop.active
                          ? 'bg-emerald-400/10 text-emerald-300 border-emerald-400/25'
                          : 'bg-foreground/5 text-muted-foreground border-foreground/15'
                      }`}>
                        {sop.active ? <CheckCircle className="w-2.5 h-2.5" /> : <XCircle className="w-2.5 h-2.5" />}
                        {sop.active ? 'Aktif' : 'Nonaktif'}
                      </span>
                      <span className="text-[10px] text-muted-foreground">v{sop.version}</span>
                      {(sop.attachments || []).length > 0 && (
                        <span className="text-[10px] text-muted-foreground">
                          {sop.attachments.length} lampiran
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <Button
                    variant="ghost" size="sm"
                    onClick={() => openEdit(sop)}
                    className="h-8 w-8 px-0"
                    title="Edit SOP"
                    data-testid={`sop-edit-btn-${sop.id}`}
                  >
                    <Edit className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    variant="ghost" size="sm"
                    onClick={() => handleDelete(sop)}
                    disabled={deleting === sop.id}
                    className="h-8 w-8 px-0 text-red-400 hover:bg-red-400/10"
                    title="Nonaktifkan SOP"
                    data-testid={`sop-delete-btn-${sop.id}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              {sop.content_markdown && (
                <div className="mt-2 text-xs text-muted-foreground bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-lg px-3 py-2 line-clamp-2">
                  {sop.content_markdown}
                </div>
              )}
            </GlassCard>
          ))}
        </div>
      )}

      {/* Create/Edit modal */}
      {modal && (
        <Modal onClose={closeModal} title={modal === 'create' ? 'Tambah SOP Baru' : 'Edit SOP'} size="lg">
          <div className="space-y-4" data-testid="sop-form-modal">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Model <span className="text-red-400">*</span></label>
                <SmartNativeSelect
                  value={form.model_id}
                  onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="sop-form-model"
                  disabled={modal === 'edit'}
                >
                  <option value="">Pilih model...</option>
                  {models.map(m => <option key={m.id} value={m.id}>{`${m.code} — ${m.name}`}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Proses <span className="text-red-400">*</span></label>
                <SmartNativeSelect
                  value={form.process_id}
                  onChange={e => setForm(f => ({ ...f, process_id: e.target.value }))}
                  className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="sop-form-process"
                  disabled={modal === 'edit'}
                >
                  <option value="">Pilih proses...</option>
                  {processes.map(p => <option key={p.id} value={p.id}>{`${p.code} — ${p.name}`}</option>)}
                </SmartNativeSelect>
              </div>
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">Judul SOP</label>
              <GlassInput
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                placeholder="Contoh: SOP Rajut Model X — Proses Linking"
                data-testid="sop-form-title"
              />
            </div>

            {/* Sprint 22 / SAM Fields */}
            <div className="grid grid-cols-2 gap-3 bg-primary/5 border border-primary/15 rounded-lg p-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">SAM (Standard Allowed Minutes)</label>
                <GlassInput
                  type="number" step="0.01" min="0"
                  value={form.sam_minutes}
                  onChange={e => setForm(f => ({ ...f, sam_minutes: e.target.value }))}
                  placeholder="Cth: 2.5"
                  data-testid="sop-form-sam"
                />
                <p className="text-[10px] text-muted-foreground mt-0.5">Menit per unit. Dipakai Line Balancing.</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Target Pcs per Operator</label>
                <GlassInput
                  type="number" step="1" min="0"
                  value={form.target_pcs_per_operator}
                  onChange={e => setForm(f => ({ ...f, target_pcs_per_operator: e.target.value }))}
                  placeholder="Cth: 200"
                  data-testid="sop-form-target-pcs"
                />
                <p className="text-[10px] text-muted-foreground mt-0.5">Override fallback 400 pcs/hari.</p>
              </div>
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">
                Instruksi Kerja (Markdown)
              </label>
              <textarea
                className="w-full min-h-[200px] px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground placeholder:text-foreground/40 focus:outline-none focus:ring-1 focus:ring-[hsl(var(--ring))] resize-y font-mono"
                placeholder="## Langkah-Langkah\n\n1. Persiapkan bahan...\n2. Atur mesin...\n\n## Catatan Keselamatan\n\n- Gunakan APD sesuai ketentuan"
                value={form.content_markdown}
                onChange={e => setForm(f => ({ ...f, content_markdown: e.target.value }))}
                data-testid="sop-form-content"
              />
              <p className="text-[10px] text-muted-foreground mt-1">Mendukung format Markdown: **tebal**, *miring*, ## heading, - daftar, 1. nomor</p>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="sop-active"
                checked={form.active}
                onChange={e => setForm(f => ({ ...f, active: e.target.checked }))}
                className="w-4 h-4"
                data-testid="sop-form-active"
              />
              <label htmlFor="sop-active" className="text-sm text-foreground">SOP Aktif</label>
            </div>

            <div className="flex gap-3">
              <Button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 h-10"
                data-testid="sop-form-save-btn"
              >
                {saving ? 'Menyimpan...' : modal === 'edit' ? 'Simpan Perubahan' : 'Buat SOP'}
              </Button>
              <Button variant="ghost" onClick={closeModal} className="h-10 px-4">
                Batal
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
