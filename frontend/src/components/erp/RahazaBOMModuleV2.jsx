import { useState, useEffect, useCallback } from 'react';
import { Plus, Edit2, X, Copy, Package, Scale, Save, FileText, Search, Layers, Link2, Unlink, Wrench } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { InlineMaterialPicker } from './bom/InlineMaterialPicker';
import { VersionRail } from './bom/VersionRail';
import { RequirementsPreviewCard } from './bom/RequirementsPreviewCard';
import { typeToCategory, categoryToStoredType, isKgLike } from '@/lib/itemTaxonomy';
import { readField, readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

/* ─── PT Rahaza · BOM Multi-Version (Phase 7A Fase 1 — unified materials[]) ─────
   - Satu daftar materials[] generik (bukan lagi yarn/accessory terpisah)
   - Tiap baris: pilih dari master + kategori + qty + unit + tipe
   - Matrix view, multi-version (create/edit/activate), preview kebutuhan, copy-to-sizes
────────────────────────────────────────────────────────────────────────────── */

const UNIT_OPTIONS = ['kg', 'gram', 'm', 'yard', 'pcs', 'lusin', 'set', 'pair', 'rol', 'karton', 'pak'];
// 3 kategori bisnis; komponen BOM hanya Bahan & Aksesoris (FG bukan komponen).
const TYPE_OPTIONS = [
  { value: 'bahan', label: 'Bahan' },
  { value: 'aksesoris', label: 'Aksesoris' },
];
const KGLIKE_TYPES = new Set(['yarn', 'fabric', 'kain', 'benang', 'interlining']);

const blankMaterial = () => ({
  material_id: null, code: '', name: '',
  material_type: 'fabric', category: '', category_name: '',
  qty: '', unit: 'kg', notes: '',
});

const materialsFromVersion = (v) => (v?.materials || []).map(m => ({
  material_id: m.material_id || null,
  code: m.code || '',
  name: m.name || '',
  material_type: m.material_type || 'other',
  category: m.category || '',
  category_name: m.category_name || '',
  qty: String(m.qty ?? ''),
  unit: m.unit || 'pcs',
  notes: m.notes || '',
}));

const selCls = 'w-full h-9 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground';

// ACC-2 — baris BOM bertipe aksesoris WAJIB tertaut ke master material
// (memory/PRODUKSI_E9_AKSESORIS.md §ACC-2). Tanpa `material_id`, kebutuhan
// aksesoris tidak bisa dipotong dari stok yang benar & nama/kode gampang drift.
const ACC_TYPES = new Set(['accessory', 'aksesoris', 'packaging', 'kemasan']);
const isAccessoryLine = (m) => ACC_TYPES.has(String(m?.material_type || '').toLowerCase());

export default function RahazaBOMModuleV2({ token }) {
  const [models, setModels] = useState([]);
  const [sizes, setSizes]   = useState([]);
  const [categories, setCategories] = useState([]);
  const [matrix, setMatrix] = useState(null);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [selectedSizeId, setSelectedSizeId] = useState('');
  const [loading, setLoading] = useState(false);

  const [activeTab, setActiveTab] = useState('matrix');

  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const [editor, setEditor] = useState(null); // { mode:'edit'|'create', versionId?, form }
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [isDirty, setIsDirty] = useState(false);

  const [copyModal, setCopyModal] = useState(null);

  // ACC-2 — kesehatan kopling BOM ↔ master material
  const [linkHealth, setLinkHealth] = useState(null);
  const [relinking, setRelinking] = useState(false);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const loadLinkHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/rahaza/boms/link-health', { headers: { Authorization: `Bearer ${token}` } });
      setLinkHealth(res.ok ? await res.json() : null);
    } catch { /* noop */ }
  }, [token]);

  const runRelink = async () => {
    setRelinking(true);
    try {
      const res = await fetch('/api/rahaza/boms/relink-materials', {
        method: 'POST', headers, body: JSON.stringify({ dry_run: false }),
      });
      if (!res.ok) throw new Error(`Gagal relink (HTTP ${res.status})`);
      const d = await res.json();
      toast.success(`${d.lines_linked} baris berhasil ditautkan ke master` +
        (d.lines_still_unlinked ? ` · ${d.lines_still_unlinked} baris masih perlu diperbaiki manual` : ''));
      loadLinkHealth();
      loadMatrix();
    } catch (err) {
      toast.error(err.message || 'Gagal menautkan otomatis');
    } finally { setRelinking(false); }
  };

  const loadBase = useCallback(async () => {
    const h = { Authorization: `Bearer ${token}` };
    const [mRes, sRes, cRes] = await Promise.all([
      fetch('/api/rahaza/models', { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/sizes',  { headers: h }).then(r => r.ok ? r.json() : []),
      fetch('/api/rahaza/material-categories', { headers: h }).then(r => r.ok ? r.json() : []),
    ]);
    const activeModels = (mRes || []).filter(m => m.active);
    setModels(activeModels);
    setSizes((sRes || []).filter(s => s.active));
    setCategories(cRes || []);
    const storedModel = localStorage.getItem('bom_selected_model');
    if (storedModel && activeModels.find(m => m.id === storedModel)) {
      setSelectedModelId(storedModel);
    } else if (!selectedModelId && activeModels.length) {
      setSelectedModelId(activeModels[0].id);
    }
  }, [token, selectedModelId]);

  const loadMatrix = useCallback(async () => {
    if (!selectedModelId) { setMatrix(null); return; }
    setLoading(true);
    try {
      const res = await fetch(`/api/rahaza/models/${selectedModelId}/bom`, { headers });
      setMatrix(res.ok ? await res.json() : null);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModelId, token]);

  const loadVersions = useCallback(async () => {
    if (!selectedModelId || !selectedSizeId) {
      setVersions([]); setSelectedVersion(null); return;
    }
    setVersionsLoading(true);
    try {
      const res = await fetch(
        `/api/rahaza/boms/versions?model_id=${selectedModelId}&size_id=${selectedSizeId}`,
        { headers }
      );
      if (res.ok) {
        const data = await res.json();
        setVersions(data || []);
        const active = (data || []).find(v => v.is_active);
        if (active) setSelectedVersion(active);
        else if ((data || []).length > 0) setSelectedVersion(data[0]);
        else setSelectedVersion(null);
      } else {
        setVersions([]); setSelectedVersion(null);
      }
    } finally {
      setVersionsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModelId, selectedSizeId, token]);

  useEffect(() => { loadBase(); }, [loadBase]);
  useEffect(() => { loadMatrix(); }, [loadMatrix]);
  useEffect(() => { loadLinkHealth(); }, [loadLinkHealth]);
  useEffect(() => { loadVersions(); }, [loadVersions]);
  useEffect(() => {
    if (selectedModelId) localStorage.setItem('bom_selected_model', selectedModelId);
  }, [selectedModelId]);

  const openEditorForSize = (sizeId) => {
    setSelectedSizeId(sizeId);
    setEditor(null);
    setActiveTab('editor');
  };

  const startCreateVersion = () => {
    const template = selectedVersion ? {
      color: selectedVersion.color || '',
      materials: materialsFromVersion(selectedVersion),
      notes: '',
    } : {
      color: '',
      materials: [blankMaterial()],
      notes: '',
    };
    if (!template.materials.length) template.materials = [blankMaterial()];
    setEditor({ mode: 'create', form: template });
    setIsDirty(false);
    setFormError('');
  };

  const startEditVersion = () => {
    if (!selectedVersion) { toast.error('Pilih versi untuk diedit'); return; }
    setEditor({
      mode: 'edit',
      versionId: selectedVersion.id,
      form: {
        color: selectedVersion.color || '',
        materials: materialsFromVersion(selectedVersion),
        notes: selectedVersion.notes || '',
      },
    });
    setIsDirty(false);
    setFormError('');
  };

  // ── Unified material row handlers ──────────────────────────────────────────
  const updateMaterial = (idx, patch) => {
    setEditor(e => ({
      ...e,
      form: { ...e.form, materials: e.form.materials.map((m, i) => i === idx ? { ...m, ...patch } : m) },
    }));
    setIsDirty(true);
  };

  const addMaterial = () => {
    setEditor(e => ({ ...e, form: { ...e.form, materials: [...e.form.materials, blankMaterial()] } }));
    setIsDirty(true);
  };

  const removeMaterial = (idx) => {
    setEditor(e => ({ ...e, form: { ...e.form, materials: e.form.materials.filter((_, i) => i !== idx) } }));
    setIsDirty(true);
  };

  const selectMaterialFromMaster = (idx, mat) => {
    updateMaterial(idx, {
      material_id: mat.id,
      code: mat.code || '',
      name: mat.name || '',
      material_type: mat.type || 'other',
      category: mat.category || '',
      category_name: mat.category_name || '',
      unit: mat.unit || 'pcs',
    });
    toast.success(`Material ${mat.code} dipilih`);
  };

  const onCategoryChange = (idx, code) => {
    const cat = categories.find(c => c.code === code);
    updateMaterial(idx, { category: code, category_name: cat ? cat.name : '' });
  };

  const saveBOM = async () => {
    if (!editor || !selectedModelId || !selectedSizeId) return;
    setSaving(true);
    setFormError('');
    try {
      const materials = editor.form.materials
        .filter(m => m.name && Number(m.qty) > 0)
        .map(m => ({
          material_id: m.material_id || null,
          code: (m.code || '').toUpperCase(),
          name: m.name,
          material_type: m.material_type || '',
          category: m.category || '',
          category_name: m.category_name || '',
          qty: Number(m.qty),
          unit: m.unit || 'pcs',
          notes: m.notes || '',
        }));

      if (materials.length === 0) {
        throw new Error('Tambahkan minimal 1 material (dengan nama & qty > 0).');
      }

      // ACC-2 — cegah baris aksesoris "lepas" dari master SEBELUM kirim ke server,
      // supaya user langsung tahu baris mana yang harus dipilih dari master.
      const looseAcc = materials
        .map((m, i) => ({ ...m, _row: i + 1 }))
        .filter(m => isAccessoryLine(m) && !m.material_id);
      if (looseAcc.length) {
        throw new Error(
          `Baris aksesoris wajib dipilih dari master material (klik ikon 🔍 di kolom pertama). ` +
          `Belum tertaut: ${looseAcc.map(m => `baris ${m._row} "${m.name}"`).join(', ')}.`
        );
      }

      const payload = {
        model_id: selectedModelId,
        size_id: selectedSizeId,
        color: editor.form.color || '',
        materials,
        notes: editor.form.notes || '',
      };

      let res;
      if (editor.mode === 'edit' && editor.versionId) {
        res = await fetch(`/api/rahaza/boms/${editor.versionId}`, {
          method: 'PUT', headers, body: JSON.stringify(payload),
        });
      } else {
        res = await fetch('/api/rahaza/boms', {
          method: 'POST', headers, body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || `Gagal menyimpan (HTTP ${res.status})`);
      }

      toast.success(editor.mode === 'edit' ? 'Perubahan berhasil disimpan' : 'Versi baru berhasil dibuat');
      setEditor(null);
      setIsDirty(false);
      loadMatrix();
      loadVersions();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleActivateVersion = async (versionId) => {
    try {
      const res = await fetch(`/api/rahaza/boms/${versionId}/activate`, { method: 'POST', headers });
      if (!res.ok) throw new Error('Gagal mengaktifkan versi');
      toast.success('Versi berhasil diaktifkan');
      loadMatrix();
      loadVersions();
    } catch (err) {
      toast.error(err.message || 'Gagal mengaktifkan versi');
    }
  };

  const handleSelectVersion = (versionId) => {
    const version = versions.find(v => v.id === versionId);
    if (version) setSelectedVersion(version);
  };

  const openCopy = (row) => {
    if (!row.bom_id) return;
    setCopyModal({ bom_id: row.bom_id, source_size_code: row.size_code, target_ids: [], overwrite: false });
  };

  const runCopy = async () => {
    if (!copyModal) return;
    if (!copyModal.target_ids.length) { toast.error('Pilih minimal 1 size target.'); return; }
    try {
      const res = await fetch(`/api/rahaza/boms/${copyModal.bom_id}/copy-to-sizes`, {
        method: 'POST', headers,
        body: JSON.stringify({ target_size_ids: copyModal.target_ids, overwrite: copyModal.overwrite }),
      });
      if (!res.ok) throw new Error(`Gagal copy (HTTP ${res.status})`);
      const data = await res.json();
      setCopyModal(null);
      loadMatrix();
      toast.success(`Copy selesai. Dibuat: ${data.created.length} · Overwrite: ${data.overwritten.length} · Dilewati: ${data.skipped.length}`);
    } catch (err) {
      toast.error(err.message || 'Gagal copy BOM');
    }
  };

  const selectedModel = matrix?.model;
  const selectedSize = sizes.find(s => s.id === selectedSizeId);
  const activeVersion = versions.find(v => v.is_active);
  const viewerMaterials = selectedVersion?.materials || [];

  return (
    <div className="space-y-5" data-testid="rahaza-bom-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Bill of Materials (BOM)</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Konfigurasi BOM multi-version dengan daftar material terunifikasi & preview kebutuhan
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={selectedModelId}
            onValueChange={val => { setSelectedModelId(val); setSelectedSizeId(''); setEditor(null); setActiveTab('matrix'); }}
            data-testid="bom-model-selector"
          >
            <SelectTrigger className="w-[240px]">
              <SelectValue placeholder="— Pilih Model —" />
            </SelectTrigger>
            <SelectContent>
              {models.map(m => (
                <SelectItem key={m.id} value={m.id}>{m.code} · {m.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* ACC-2 — kesehatan kopling BOM ↔ master material.
          Banner SELALU tampil bila data kesehatan sudah dimuat: kondisi BURUK
          (amber, ada baris lepas) maupun SEHAT (emerald). Sebelumnya banner
          hilang total saat sehat sehingga user tak pernah dapat konfirmasi
          bahwa rantai BOM→kebutuhan→stok memang utuh. */}
      {linkHealth && (linkHealth.unlinked_lines > 0 ? (
        <div className="rounded-xl border border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 px-4 py-3"
          data-testid="bom-link-health-banner">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="text-sm text-amber-900 dark:text-amber-200">
              <strong>{linkHealth.unlinked_lines} baris BOM belum tertaut ke master material</strong>
              {linkHealth.unlinked_accessory_lines > 0 && (
                <> — termasuk <strong>{linkHealth.unlinked_accessory_lines} baris aksesoris</strong></>
              )}.
              <div className="text-xs mt-1 opacity-90">
                Baris yang tidak tertaut membuat kebutuhan material tidak bisa dipotong dari stok yang benar
                (nama/kode gampang beda dengan master). Perbaikan otomatis akan menautkan baris yang
                <strong> kodenya cocok</strong> dengan master; sisanya perlu dipilih manual di editor.
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={runRelink} disabled={relinking}
              data-testid="bom-relink-btn">
              <Wrench className="w-3.5 h-3.5 mr-1" />
              {relinking ? 'Menautkan...' : 'Perbaiki Otomatis'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-emerald-400 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 px-4 py-3"
          data-testid="bom-link-health-banner">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-emerald-900 dark:text-emerald-200">
              <strong>Kopling BOM sehat</strong> — {linkHealth.total_lines} baris material
              {' '}({linkHealth.accessory_lines} aksesoris) di {linkHealth.total_boms} BOM sudah tertaut ke master material.
              <div className="text-xs mt-1 opacity-90">
                Rantai BOM → kebutuhan material → stok tersambung, jadi kebutuhan tiap PO bisa
                dibandingkan dengan stok nyata.
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={runRelink} disabled={relinking}
              data-testid="bom-relink-btn">
              <Wrench className="w-3.5 h-3.5 mr-1" />
              {relinking ? 'Memeriksa...' : 'Periksa Ulang'}
            </Button>
          </div>
        </div>
      ))}

      {!selectedModelId ? (
        <GlassCard className="p-12 text-center text-muted-foreground">
          <Package className="w-10 h-10 mx-auto mb-3 text-foreground/30" />
          Pilih model terlebih dahulu untuk mulai mengisi BOM.
        </GlassCard>
      ) : (        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList>
            <TabsTrigger value="matrix" data-testid="bom-tab-matrix">Matriks BOM</TabsTrigger>
            <TabsTrigger value="editor" disabled={!selectedSizeId} data-testid="bom-tab-editor">
              Editor {selectedSize ? `· ${selectedSize.code}` : ''}
            </TabsTrigger>
            <TabsTrigger value="preview" disabled={!selectedVersion} data-testid="bom-tab-preview">
              Preview Kebutuhan
            </TabsTrigger>
          </TabsList>

          {/* Matrix Tab */}
          <TabsContent value="matrix" className="space-y-4">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
              </div>
            ) : !matrix ? (
              <GlassCard className="p-6 text-center text-muted-foreground">
                Tidak dapat memuat data BOM.
              </GlassCard>
            ) : (
              <GlassCard className="p-0 overflow-hidden">
                <div className="px-4 py-3 border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
                  <div className="flex items-center gap-2 text-sm">
                    <Package className="w-4 h-4 text-primary" />
                    <span className="font-semibold text-foreground">{selectedModel?.code}</span>
                    <span className="text-muted-foreground">· {selectedModel?.name}</span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Size</TableHead>
                        <TableHead>Versi Aktif</TableHead>
                        <TableHead><Scale className="w-3 h-3 inline mr-1" /> Bahan /pcs</TableHead>
                        <TableHead>Material</TableHead>
                        <TableHead>Terakhir Update</TableHead>
                        <TableHead className="text-right">Aksi</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(matrix.matrix || []).map(row => (
                        <TableRow
                          key={row.size_id}
                          className="hover:bg-[var(--glass-bg-hover)]"
                          data-testid={`bom-row-${row.size_code}`}
                        >
                          <TableCell className="font-semibold text-foreground">{row.size_code}</TableCell>
                          <TableCell>
                            {row.bom_id ? (
                              <Badge variant="default" className="text-[10px]">v{row.version}</Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">Belum ada</span>
                            )}
                          </TableCell>
                          <TableCell className="font-mono text-foreground">
                            {readNumber(row, FIELD.totalMaterialKgPerPcs) ? readNumber(row, FIELD.totalMaterialKgPerPcs).toFixed(3) : '—'} kg
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            {row.material_count || 0} material
                            {row.material_count ? ` (${readNumber(row, FIELD.bulkLineCount)} bahan · ${row.accessory_count} aksesoris)` : ''}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            {row.updated_at ? new Date(row.updated_at).toLocaleDateString('id-ID') : '—'}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="inline-flex items-center gap-1">
                              <Button
                                variant="ghost" size="sm" className="h-8 px-2"
                                onClick={() => openEditorForSize(row.size_id)}
                                data-testid={`bom-open-${row.size_code}`}
                              >
                                {row.bom_id ? <Edit2 className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                              </Button>
                              {row.bom_id && (
                                <Button
                                  variant="ghost" size="sm" className="h-8 px-2"
                                  onClick={() => openCopy(row)}
                                  data-testid={`bom-copy-${row.size_code}`}
                                >
                                  <Copy className="w-3.5 h-3.5" />
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </GlassCard>
            )}
          </TabsContent>

          {/* Editor Tab */}
          <TabsContent value="editor" className="space-y-4">
            {!selectedSizeId ? (
              <GlassCard className="p-12 text-center text-muted-foreground">
                Pilih size dari matriks untuk mulai edit BOM
              </GlassCard>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                <div className="lg:col-span-8 space-y-4">
                  {editor ? (
                    <GlassCard className="p-5 space-y-5" data-testid="bom-editor-form">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-semibold text-foreground">
                            {editor.mode === 'edit' ? 'Edit Versi' : 'Buat Versi Baru'}
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            {selectedModel?.code} · {selectedSize?.code}
                            {editor.mode === 'edit' && selectedVersion ? ` · v${selectedVersion.version}` : ''}
                          </p>
                        </div>
                        {isDirty && (
                          <Badge variant="outline" className="text-warning border-warning">Belum disimpan</Badge>
                        )}
                      </div>

                      {formError && (
                        <div
                          data-testid="bom-form-error"
                          className="bg-red-100 dark:bg-red-500/10 border border-red-400 dark:border-red-500/30 rounded-lg p-3 text-sm text-red-800 dark:text-red-300"
                        >
                          {formError}
                        </div>
                      )}

                      {/* Unified Materials */}
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <Layers className="w-4 h-4 text-primary" />
                            <span className="text-sm font-semibold text-foreground">Daftar Material</span>
                            <span className="text-xs text-muted-foreground">qty per pcs</span>
                          </div>
                          <Button variant="outline" size="sm" onClick={addMaterial} data-testid="bom-add-material-btn">
                            <Plus className="w-4 h-4 mr-1" /> Tambah Material
                          </Button>
                        </div>
                        <div className="border border-[var(--glass-border)] rounded-lg overflow-x-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-[36px]"></TableHead>
                                <TableHead className="min-w-[180px]">Nama</TableHead>
                                <TableHead className="min-w-[120px]">Kode</TableHead>
                                <TableHead className="min-w-[150px]">Kategori</TableHead>
                                <TableHead className="min-w-[120px]">Tipe</TableHead>
                                <TableHead className="w-24">Qty</TableHead>
                                <TableHead className="w-28">Unit</TableHead>
                                <TableHead className="w-10"></TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {editor.form.materials.map((m, idx) => (
                                <TableRow key={idx}>
                                  <TableCell>
                                    <div className="flex items-center gap-1">
                                      <InlineMaterialPicker
                                        token={token}
                                        categories={categories}
                                        onSelect={mat => selectMaterialFromMaster(idx, mat)}
                                      >
                                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Pilih dari master">
                                          <Search className="w-3.5 h-3.5" />
                                        </Button>
                                      </InlineMaterialPicker>
                                      {/* ACC-2 — indikator kopling ke master material */}
                                      {m.material_id ? (
                                        <span title="Tertaut ke master material" data-testid={`bom-mat-${idx}-linked`}>
                                          <Link2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                        </span>
                                      ) : (
                                        <span
                                          title={isAccessoryLine(m)
                                            ? 'WAJIB: baris aksesoris harus dipilih dari master material'
                                            : 'Belum tertaut ke master material (disarankan pilih dari master)'}
                                          data-testid={`bom-mat-${idx}-unlinked`}
                                        >
                                          <Unlink className={`w-3.5 h-3.5 ${isAccessoryLine(m)
                                            ? 'text-red-600 dark:text-red-400'
                                            : 'text-amber-600 dark:text-amber-400'}`} />
                                        </span>
                                      )}
                                    </div>
                                  </TableCell>
                                  <TableCell>
                                    <GlassInput
                                      value={m.name}
                                      onChange={e => updateMaterial(idx, { name: e.target.value })}
                                      placeholder="Kain Katun 30s"
                                      data-testid={`bom-mat-${idx}-name`}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <GlassInput
                                      value={m.code}
                                      onChange={e => updateMaterial(idx, { code: e.target.value.toUpperCase() })}
                                      placeholder="YRN-ACR28"
                                      data-testid={`bom-mat-${idx}-code`}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <select
                                      className={selCls}
                                      value={m.category || ''}
                                      onChange={e => onCategoryChange(idx, e.target.value)}
                                      data-testid={`bom-mat-${idx}-category`}
                                    >
                                      <option value="">— Kategori —</option>
                                      {categories.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
                                    </select>
                                  </TableCell>
                                  <TableCell>
                                    <select
                                      className={selCls}
                                      value={typeToCategory(m.material_type)}
                                      onChange={e => {
                                        const st = categoryToStoredType(e.target.value);
                                        const patch = { material_type: st };
                                        if (isKgLike(st) && !KGLIKE_TYPES.has(m.material_type)) patch.unit = 'kg';
                                        updateMaterial(idx, patch);
                                      }}
                                      data-testid={`bom-mat-${idx}-type`}
                                    >
                                      {TYPE_OPTIONS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                                    </select>
                                  </TableCell>
                                  <TableCell>
                                    <GlassInput
                                      type="number"
                                      step="0.001"
                                      value={m.qty}
                                      onChange={e => updateMaterial(idx, { qty: e.target.value })}
                                      placeholder="0.300"
                                      data-testid={`bom-mat-${idx}-qty`}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <select
                                      className={selCls}
                                      value={m.unit || 'pcs'}
                                      onChange={e => updateMaterial(idx, { unit: e.target.value })}
                                      data-testid={`bom-mat-${idx}-unit`}
                                    >
                                      {UNIT_OPTIONS.map(u => <option key={u} value={u}>{u}</option>)}
                                    </select>
                                  </TableCell>
                                  <TableCell>
                                    <Button
                                      variant="ghost" size="sm"
                                      className="h-7 w-7 p-0 hover:bg-red-400/10 hover:text-red-400"
                                      onClick={() => removeMaterial(idx)}
                                      data-testid={`bom-mat-${idx}-remove`}
                                    >
                                      <X className="w-4 h-4" />
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              ))}
                              {editor.form.materials.length === 0 && (
                                <TableRow>
                                  <TableCell colSpan={8} className="text-center py-6 text-xs text-muted-foreground">
                                    Belum ada material. Klik "Tambah Material" untuk mulai.
                                  </TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      {/* Notes */}
                      <div>
                        <label className="block text-xs font-medium text-foreground/70 mb-1">
                          Catatan BOM (opsional)
                        </label>
                        <GlassInput
                          value={editor.form.notes}
                          onChange={e => { setEditor(ed => ({ ...ed, form: { ...ed.form, notes: e.target.value } })); setIsDirty(true); }}
                          placeholder="cth: sample awal, revisi #2, dsb"
                          data-testid="bom-notes-input"
                        />
                      </div>

                      {/* Actions */}
                      <div className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--glass-border)]">
                        <Button
                          variant="ghost"
                          onClick={() => {
                            if (isDirty && !window.confirm('Ada perubahan belum disimpan. Batalkan?')) return;
                            setEditor(null); setIsDirty(false); setFormError('');
                          }}
                          disabled={saving}
                        >
                          Batal
                        </Button>
                        <Button onClick={saveBOM} disabled={saving} data-testid="bom-save-btn">
                          <Save className="w-4 h-4 mr-2" />
                          {saving ? 'Menyimpan...' : (editor.mode === 'edit' ? 'Simpan Perubahan' : 'Simpan Versi Baru')}
                        </Button>
                      </div>
                    </GlassCard>
                  ) : (
                    // Version Viewer
                    <GlassCard className="p-5">
                      {selectedVersion ? (
                        <div className="space-y-4">
                          <div className="flex items-center justify-between">
                            <div>
                              <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                                <FileText className="w-5 h-5 text-primary" />
                                BOM v{selectedVersion.version}
                                {selectedVersion.is_active && (<Badge variant="default" className="ml-2">Aktif</Badge>)}
                              </h3>
                              <p className="text-sm text-muted-foreground mt-1">
                                {selectedModel?.code} · {selectedSize?.code}
                                {' · '}{selectedVersion.material_count || viewerMaterials.length} material
                                {readNumber(selectedVersion, FIELD.totalMaterialKgPerPcs) ? ` · ${readNumber(selectedVersion, FIELD.totalMaterialKgPerPcs).toFixed(3)} kg/pcs` : ''}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button variant="outline" size="sm" onClick={startCreateVersion} data-testid="bom-create-new-version-btn">
                                <Plus className="w-4 h-4 mr-2" /> Versi Baru
                              </Button>
                              <Button variant="default" size="sm" onClick={startEditVersion} data-testid="bom-edit-version-btn">
                                <Edit2 className="w-4 h-4 mr-2" /> Edit
                              </Button>
                            </div>
                          </div>

                          {viewerMaterials.length > 0 ? (
                            <div>
                              <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                                <Layers className="w-4 h-4 text-primary" />
                                Material ({viewerMaterials.length})
                              </h4>
                              <div className="border border-[var(--glass-border)] rounded-lg overflow-x-auto">
                                <Table data-testid="bom-viewer-materials-table">
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead className="w-10" title="Tertaut ke master material?">Taut</TableHead>
                                      <TableHead>Kode</TableHead>
                                      <TableHead>Nama</TableHead>
                                      <TableHead>Kategori</TableHead>
                                      <TableHead>Tipe</TableHead>
                                      <TableHead className="text-right">Qty</TableHead>
                                      <TableHead>Unit</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {viewerMaterials.map((m, idx) => (
                                      <TableRow key={idx} data-testid={`bom-viewer-row-${idx}`}>
                                        {/* ACC-2 — status kopling ke master material terlihat TANPA
                                            harus masuk mode Edit (baris lepas = rantai stok putus). */}
                                        <TableCell>
                                          {m.material_id ? (
                                            <span title="Tertaut ke master material"
                                              data-testid={`bom-viewer-mat-${idx}-linked`}>
                                              <Link2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                            </span>
                                          ) : (
                                            <span
                                              title={isAccessoryLine(m)
                                                ? 'WAJIB: baris aksesoris harus dipilih dari master material'
                                                : 'Belum tertaut ke master material (disarankan pilih dari master)'}
                                              data-testid={`bom-viewer-mat-${idx}-unlinked`}>
                                              <Unlink className={`w-3.5 h-3.5 ${isAccessoryLine(m)
                                                ? 'text-red-600 dark:text-red-400'
                                                : 'text-amber-600 dark:text-amber-400'}`} />
                                            </span>
                                          )}
                                        </TableCell>
                                        <TableCell className="font-mono text-xs">{m.code || '—'}</TableCell>
                                        <TableCell>{m.name}</TableCell>
                                        <TableCell className="text-xs text-muted-foreground">{m.category_name || '—'}</TableCell>
                                        <TableCell className="text-xs text-muted-foreground">
                                          {(TYPE_OPTIONS.find(t => t.value === m.material_type) || {}).label || m.material_type}
                                        </TableCell>
                                        <TableCell className="text-right font-mono">{m.qty}</TableCell>
                                        <TableCell className="text-xs">{m.unit}</TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            </div>
                          ) : (
                            <div className="text-center py-6 text-sm text-muted-foreground">
                              Versi ini belum memiliki material. Klik "Edit" untuk menambah.
                            </div>
                          )}

                          {selectedVersion.notes && (
                            <div className="p-3 bg-[var(--glass-bg)] rounded-lg border border-[var(--glass-border)]">
                              <div className="text-xs font-medium text-muted-foreground mb-1">Catatan</div>
                              <div className="text-sm text-foreground">{selectedVersion.notes}</div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-center py-12 text-muted-foreground">
                          <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
                          <p>Belum ada versi BOM untuk size ini</p>
                          <Button
                            variant="outline" size="sm" className="mt-4"
                            onClick={() => { setEditor({ mode: 'create', form: { color: '', materials: [blankMaterial()], notes: '' } }); setIsDirty(false); setFormError(''); }}
                            data-testid="bom-create-first-version-btn"
                          >
                            <Plus className="w-4 h-4 mr-2" /> Buat Versi Pertama
                          </Button>
                        </div>
                      )}
                    </GlassCard>
                  )}
                </div>

                {/* Version Rail */}
                <div className="lg:col-span-4">
                  <VersionRail
                    versions={versions}
                    activeVersionId={activeVersion?.id}
                    selectedVersionId={selectedVersion?.id}
                    onSelectVersion={handleSelectVersion}
                    onCreateVersion={startCreateVersion}
                    onActivateVersion={handleActivateVersion}
                    loading={versionsLoading}
                  />
                </div>
              </div>
            )}
          </TabsContent>

          {/* Preview Tab */}
          <TabsContent value="preview">
            {selectedVersion ? (
              <RequirementsPreviewCard bom={selectedVersion} token={token} />
            ) : (
              <GlassCard className="p-12 text-center text-muted-foreground">
                Pilih versi BOM untuk melihat preview kebutuhan material
              </GlassCard>
            )}
          </TabsContent>
        </Tabs>
      )}

      {/* Copy Modal */}
      {copyModal && (
        <Dialog open={!!copyModal} onOpenChange={() => setCopyModal(null)}>
          <DialogContent className="sm:max-w-[600px]" data-testid="bom-copy-modal">
            <DialogHeader>
              <DialogTitle>Copy BOM dari Size {copyModal.source_size_code}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <p className="text-sm text-muted-foreground">
                Pilih size tujuan. Material akan disalin sesuai versi aktif.
              </p>
              <div className="grid grid-cols-4 gap-2">
                {(matrix?.matrix || [])
                  .filter(r => r.size_code !== copyModal.source_size_code)
                  .map(r => {
                    const checked = copyModal.target_ids.includes(r.size_id);
                    return (
                      <label
                        key={r.size_id}
                        className={`border border-[var(--glass-border)] rounded-lg px-3 py-2 cursor-pointer text-sm flex items-center gap-2 transition-colors ${
                          checked ? 'bg-primary/10 border-primary/40 text-foreground'
                                  : 'bg-[var(--glass-bg)] text-foreground/70 hover:bg-[var(--glass-bg-hover)]'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={e =>
                            setCopyModal(c => ({
                              ...c,
                              target_ids: e.target.checked
                                ? [...c.target_ids, r.size_id]
                                : c.target_ids.filter(x => x !== r.size_id),
                            }))
                          }
                          data-testid={`bom-copy-target-${r.size_code}`}
                        />
                        <span className="font-mono">{r.size_code}</span>
                        {r.bom_id && <span className="text-[10px] text-amber-300">(ada)</span>}
                      </label>
                    );
                  })}
              </div>
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={copyModal.overwrite}
                  onChange={e => setCopyModal(c => ({ ...c, overwrite: e.target.checked }))}
                  data-testid="bom-copy-overwrite"
                />
                Overwrite BOM yang sudah ada
              </label>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setCopyModal(null)}>Batal</Button>
              <Button onClick={runCopy} data-testid="bom-copy-run-btn">Copy</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
