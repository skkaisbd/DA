/**
 * ⚠️ LAYAR PENSIUN (SESI #19, 2026-08-18) — JANGAN DIPASANG LAGI KE MENU.
 *
 * Digantikan `erp/pdf/PdfTemplateStudio.jsx` ("PDF & Kop Surat"): satu layar untuk
 * kop surat (logo & identitas PT), kolom tabel (tampil/urutan/tambah), blok tanda
 * tangan, footer, PLUS pratinjau PDF di sampingnya. Keluhan pemilik yang membuat
 * layar ini dipensiunkan: "cek ada dua halaman berbeda ui ux-nya jelas" —
 * berkas ini adalah salah satu dari dua halaman itu.
 *
 * Berkas TIDAK dihapus supaya riwayat & pola lamanya bisa dibaca, tetapi tidak
 * dirujuk `moduleRegistry.js` maupun hub mana pun. Penjaga INV-F26 (P1) akan MERAH
 * bila berkas ini dipasang kembali sebagai tab/menu.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  FileDown, Plus, Trash2, Star, Check, X, Settings, Eye, Download,
  ChevronDown, ChevronRight, Save, Edit2, LayoutGrid, List, Info
} from 'lucide-react';

const PDF_TYPE_LABELS = {
  'production-po': 'SPP (Surat Perintah Produksi)',
  'vendor-shipment': 'Surat Jalan Material',
  'buyer-shipment-dispatch': 'Surat Jalan Buyer (Dispatch)',
  'production-report': 'Laporan Produksi Lengkap',
  'report-production': 'Report: Produksi',
  'report-progress': 'Report: Progres',
  'report-financial': 'Report: Keuangan',
  'report-shipment': 'Report: Pengiriman',
  'report-defect': 'Report: Defect',
  'report-return': 'Report: Retur',
  'report-missing-material': 'Report: Material Hilang',
  'report-replacement': 'Report: Pengganti',
  'report-accessory': 'Report: Aksesoris',
};

const PDF_TYPE_GROUPS = {
  'Documents': ['production-po', 'vendor-shipment', 'buyer-shipment-dispatch', 'production-report'],
  'Reports': ['report-production', 'report-progress', 'report-financial', 'report-shipment', 'report-defect', 'report-return', 'report-missing-material', 'report-replacement', 'report-accessory'],
};

export default function PDFConfigModule({ token }) {
  const [configs, setConfigs] = useState([]);
  const [columns, setColumns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editConfig, setEditConfig] = useState(null);
  const [formName, setFormName] = useState('');
  const [formColumns, setFormColumns] = useState([]);
  const [formDefault, setFormDefault] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState({ Documents: true, Reports: true });
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchConfigs = useCallback(async () => {
    try {
      const res = await fetch('/api/pdf-export-configs', { headers });
      const data = await res.json();
      setConfigs(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch PDF configs:', e);
    }
  }, [headers]);

  const fetchColumns = useCallback(async (type) => {
    if (!type) { setColumns([]); return; }
    try {
      const res = await fetch(`/api/pdf-export-columns?type=${type}`, { headers });
      const data = await res.json();
      setColumns(data.columns || []);
    } catch (e) {
      setColumns([]);
    }
  }, [headers]);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  const openCreateModal = (type) => {
    setSelectedType(type);
    setEditConfig(null);
    setFormName('');
    setFormDefault(false);
    setFormColumns([]);
    fetchColumns(type).then(() => setShowModal(true));
  };

  const openEditModal = (cfg) => {
    setSelectedType(cfg.pdf_type);
    setEditConfig(cfg);
    setFormName(cfg.name);
    setFormDefault(cfg.is_default || false);
    setFormColumns(cfg.columns || []);
    fetchColumns(cfg.pdf_type).then(() => setShowModal(true));
  };

  useEffect(() => {
    if (showModal && selectedType) {
      fetchColumns(selectedType);
    }
  }, [selectedType, showModal, fetchColumns]);

  useEffect(() => {
    // When columns load and creating new, select all
    if (columns.length > 0 && !editConfig && formColumns.length === 0) {
      setFormColumns(columns.map(c => c.key));
    }
  }, [columns, editConfig, formColumns.length]);

  const toggleColumn = (key) => {
    const required = columns.filter(c => c.required).map(c => c.key);
    if (required.includes(key)) return; // Can't uncheck required
    setFormColumns(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const selectAll = () => setFormColumns(columns.map(c => c.key));
  const deselectOptional = () => setFormColumns(columns.filter(c => c.required).map(c => c.key));

  const handleSave = async () => {
    if (!formName.trim()) { alert('Nama preset harus diisi'); return; }
    if (formColumns.length === 0) { alert('Pilih minimal 1 kolom'); return; }
    setSaving(true);
    try {
      const body = { pdf_type: selectedType, name: formName, columns: formColumns, is_default: formDefault };
      let res;
      if (editConfig) {
        res = await fetch(`/api/pdf-export-configs/${editConfig.id}`, { method: 'PUT', headers, body: JSON.stringify(body) });
      } else {
        res = await fetch('/api/pdf-export-configs', { method: 'POST', headers, body: JSON.stringify(body) });
      }
      if (res.ok) {
        setShowModal(false);
        fetchConfigs();
      } else {
        const err = await res.json();
        alert('Error: ' + (err.detail || JSON.stringify(err)));
      }
    } catch (e) {
      alert('Error: ' + e.message);
    }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus preset PDF ini?')) return;
    try {
      await fetch(`/api/pdf-export-configs/${id}`, { method: 'DELETE', headers });
      fetchConfigs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  const handleSetDefault = async (cfg) => {
    try {
      await fetch(`/api/pdf-export-configs/${cfg.id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ is_default: !cfg.is_default })
      });
      fetchConfigs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  const handleTestExport = async (type) => {
    setTestResult(null);
    try {
      const defaultConfig = configs.find(c => c.pdf_type === type && c.is_default);
      let url = `/api/export-pdf?type=${type}`;
      if (defaultConfig) url += `&config_id=${defaultConfig.id}`;
      // For document types that need an ID, just test without ID to see error handling
      const res = await fetch(url, { headers });
      if (res.ok) {
        const blob = await res.blob();
        const burl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = burl;
        a.download = `test_${type}.pdf`;
        a.click();
        URL.revokeObjectURL(burl);
        setTestResult({ type, ok: true, msg: 'PDF downloaded successfully' });
      } else {
        const err = await res.json().catch(() => ({}));
        setTestResult({ type, ok: false, msg: err.detail || `HTTP ${res.status}` });
      }
    } catch (e) {
      setTestResult({ type, ok: false, msg: e.message });
    }
  };

  const getConfigsForType = (type) => configs.filter(c => c.pdf_type === type);
  const getDefaultForType = (type) => configs.find(c => c.pdf_type === type && c.is_default);

  const toggleGroup = (group) => {
    setExpandedGroups(prev => ({ ...prev, [group]: !prev[group] }));
  };

  return (
    <div className="space-y-6" data-testid="pdf-config-module">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-3" data-testid="pdf-config-title">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Settings className="w-6 h-6 text-primary" />
            </div>
            Konfigurasi Export PDF
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Atur kolom yang ditampilkan pada setiap jenis dokumen PDF. Preset default akan digunakan otomatis saat export.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground bg-[var(--glass-bg)] rounded-lg px-3 py-2">
          <Info className="w-4 h-4" />
          <span>{configs.length} preset tersimpan</span>
        </div>
      </div>

      {/* PDF Types Grid */}
      {Object.entries(PDF_TYPE_GROUPS).map(([group, types]) => (
        <div key={group} className="bg-[var(--card-surface)] rounded-xl border border-border overflow-hidden shadow-sm">
          <button
            onClick={() => toggleGroup(group)}
            className="w-full flex items-center justify-between px-5 py-3.5 bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors"
            data-testid={`group-toggle-${group.toLowerCase()}`}
          >
            <div className="flex items-center gap-3">
              {expandedGroups[group] ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
              <span className="text-sm font-semibold text-foreground uppercase tracking-wide">{group}</span>
              <span className="text-xs bg-secondary text-muted-foreground rounded-full px-2 py-0.5">{types.length}</span>
            </div>
          </button>
          {expandedGroups[group] && (
            <div className="divide-y divide-border">
              {types.map(type => {
                const typeConfigs = getConfigsForType(type);
                const defaultCfg = getDefaultForType(type);
                return (
                  <div key={type} className="px-5 py-4 hover:bg-[var(--glass-bg)]/50 transition-colors" data-testid={`pdf-type-row-${type}`}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <FileDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                          <span className="text-sm font-medium text-foreground">{PDF_TYPE_LABELS[type] || type}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          {defaultCfg ? (
                            <span className="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5">
                              <Star className="w-3 h-3 fill-current" />
                              Default: {defaultCfg.name} ({defaultCfg.columns?.length} kolom)
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">Semua kolom (default sistem)</span>
                          )}
                          {typeConfigs.length > 0 && (
                            <span className="text-xs text-muted-foreground">
                              {typeConfigs.length} preset
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          onClick={() => handleTestExport(type)}
                          className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                          title="Test Export PDF"
                          data-testid={`test-export-${type}`}
                        >
                          <Download className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openCreateModal(type)}
                          className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary bg-primary/10 hover:bg-primary/15 rounded-lg px-3 py-1.5 transition-colors"
                          data-testid={`create-preset-${type}`}
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Buat Preset
                        </button>
                      </div>
                    </div>
                    {/* Show existing presets */}
                    {typeConfigs.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {typeConfigs.map(cfg => (
                          <div key={cfg.id} className="flex items-center justify-between bg-[var(--card-surface)] border border-border rounded-lg px-3 py-2" data-testid={`preset-card-${cfg.id}`}>
                            <div className="flex items-center gap-3 min-w-0">
                              <button
                                onClick={() => handleSetDefault(cfg)}
                                className={`p-1 rounded-md transition-colors ${cfg.is_default ? 'text-amber-700 dark:text-amber-500 bg-amber-50' : 'text-muted-foreground hover:text-amber-700 dark:text-amber-400 hover:bg-amber-50'}`}
                                title={cfg.is_default ? 'Remove as default' : 'Set as default'}
                                data-testid={`toggle-default-${cfg.id}`}
                              >
                                <Star className={`w-4 h-4 ${cfg.is_default ? 'fill-current' : ''}`} />
                              </button>
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-foreground truncate">{cfg.name}</p>
                                <p className="text-xs text-muted-foreground">{cfg.columns?.length || 0} kolom dipilih</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1">
                              <button onClick={() => openEditModal(cfg)} className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-colors" title="Edit" data-testid={`edit-preset-${cfg.id}`}>
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                              <button onClick={() => handleDelete(cfg.id)} className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Delete" data-testid={`delete-preset-${cfg.id}`}>
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}

      {/* Test Result Toast */}
      {testResult && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border ${
          testResult.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'
        }`} data-testid="test-result-toast">
          {testResult.ok ? <Check className="w-5 h-5 text-emerald-500" /> : <X className="w-5 h-5 text-red-700 dark:text-red-500" />}
          <div>
            <p className="text-sm font-medium">{testResult.ok ? 'Export Berhasil' : 'Export Gagal'}</p>
            <p className="text-xs opacity-80">{testResult.msg}</p>
          </div>
          <button onClick={() => setTestResult(null)} className="p-1 hover:bg-black/5 rounded"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay-bg)] backdrop-blur-sm" data-testid="preset-modal-backdrop">
          <div className="bg-[var(--card-surface)] rounded-2xl shadow-[0_12px_40px_rgba(0,0,0,0.25)] w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden flex flex-col" data-testid="preset-modal">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-foreground" data-testid="modal-title">
                  {editConfig ? 'Edit Preset' : 'Buat Preset Baru'}
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">{PDF_TYPE_LABELS[selectedType] || selectedType}</p>
              </div>
              <button onClick={() => setShowModal(false)} className="p-1.5 hover:bg-[var(--glass-bg-hover)] rounded-lg transition-colors" data-testid="modal-close">
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
              {/* Name field */}
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Nama Preset</label>
                <input
                  type="text"
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  placeholder="e.g., Ringkasan, Lengkap, Custom Client A"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-ring focus:border-primary/30 outline-none"
                  data-testid="preset-name-input"
                />
              </div>

              {/* Default toggle */}
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setFormDefault(!formDefault)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formDefault ? 'bg-primary' : 'bg-secondary'}`}
                  data-testid="preset-default-toggle"
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-[var(--card-surface)] transition-transform shadow ${formDefault ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
                <span className="text-sm text-muted-foreground">Set sebagai default untuk tipe ini</span>
              </div>

              {/* Column Selector */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-foreground">Pilih Kolom</label>
                  <div className="flex gap-2">
                    <button onClick={selectAll} className="text-xs text-primary hover:brightness-110" data-testid="select-all-columns">Pilih Semua</button>
                    <span className="text-muted-foreground">|</span>
                    <button onClick={deselectOptional} className="text-xs text-muted-foreground hover:text-foreground" data-testid="deselect-optional">Hanya Wajib</button>
                  </div>
                </div>
                <div className="bg-[var(--glass-bg)] rounded-lg border border-border p-3">
                  <div className="grid grid-cols-2 gap-2" data-testid="column-grid">
                    {columns.map(col => {
                      const isSelected = formColumns.includes(col.key);
                      const isRequired = col.required;
                      return (
                        <button
                          key={col.key}
                          onClick={() => toggleColumn(col.key)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-left transition-all text-sm ${
                            isSelected
                              ? 'bg-primary/10 border-primary/25 text-blue-800'
                              : 'bg-[var(--card-surface)] border-border text-muted-foreground hover:border-border'
                          } ${isRequired ? 'ring-1 ring-amber-200' : ''}`}
                          data-testid={`column-${col.key}`}
                        >
                          <div className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 ${
                            isSelected ? 'bg-primary text-foreground' : 'border border-border'
                          }`}>
                            {isSelected && <Check className="w-3 h-3" />}
                          </div>
                          <span className="truncate">{col.label}</span>
                          {isRequired && <span className="text-xs text-amber-700 dark:text-amber-500 flex-shrink-0">*</span>}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                    <span className="text-amber-700 dark:text-amber-500">*</span> Kolom wajib tidak dapat dihilangkan
                  </p>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{formColumns.length} dari {columns.length} kolom dipilih</p>
              </div>

              {/* Preview */}
              <div>
                <label className="text-sm font-medium text-foreground mb-1 block">Preview Kolom</label>
                <div className="bg-muted rounded-lg p-3 overflow-x-auto">
                  <div className="flex gap-1">
                    {formColumns.map(key => {
                      const col = columns.find(c => c.key === key);
                      return (
                        <span key={key} className="px-2 py-1 bg-muted-foreground/30 text-foreground text-xs rounded whitespace-nowrap">
                          {col?.label || key}
                        </span>
                      );
                    })}
                    {formColumns.length === 0 && <span className="text-xs text-muted-foreground">Belum ada kolom dipilih</span>}
                  </div>
                </div>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-border flex items-center justify-end gap-3 bg-[var(--glass-bg)]">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground rounded-lg transition-colors"
                data-testid="modal-cancel"
              >
                Batal
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-foreground text-sm font-medium rounded-lg hover:brightness-110 disabled:opacity-50 transition-colors"
                data-testid="modal-save"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Menyimpan...' : editConfig ? 'Simpan Perubahan' : 'Simpan Preset'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
