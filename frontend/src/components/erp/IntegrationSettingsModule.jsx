import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Key, Plus, Trash2, TestTube2, CheckCircle, XCircle,
  Eye, EyeOff, RefreshCw, Save, Brain, Bell, HardDrive, Mail, Settings2, AlertTriangle
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const CATEGORY_META = {
  ai: { label: 'AI & LLM', icon: Brain, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-950/30' },
  notification: { label: 'Notifikasi', icon: Bell, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-950/30' },
  storage: { label: 'Penyimpanan', icon: HardDrive, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-950/30' },
  email: { label: 'Email', icon: Mail, color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-950/30' },
  custom: { label: 'Kustom', icon: Settings2, color: 'text-foreground/60', bg: 'bg-[var(--glass-bg)]' },
};

export default function IntegrationSettingsModule({ token, userRole }) {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [editKey, setEditKey] = useState(null); // key_name being edited
  const [form, setForm] = useState({ key_name: '', value: '', description: '', category: 'ai' });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState({});
  const [testResults, setTestResults] = useState({});
  const [showValues, setShowValues] = useState({});
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const canEdit = ['superadmin', 'admin'].includes(userRole);
  const canDelete = userRole === 'superadmin';

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/rahaza/integration-settings', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.ok) setKeys(data.data || []);
      else setError(data.detail || 'Gagal memuat pengaturan.');
    } catch (e) {
      setError('Gagal terhubung ke server.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.key_name || !form.value) {
      setError('Nama kunci dan nilai wajib diisi.');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const res = await fetch('/api/rahaza/integration-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (data.ok) {
        setSuccess(data.message || 'Berhasil disimpan.');
        setAddOpen(false);
        setEditKey(null);
        setForm({ key_name: '', value: '', description: '', category: 'ai' });
        fetchKeys();
        setTimeout(() => setSuccess(''), 4000);
      } else {
        setError(data.detail || 'Gagal menyimpan.');
      }
    } catch (e) {
      setError('Gagal terhubung ke server.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (keyName) => {
    if (!window.confirm(`Hapus kunci ${keyName}? Sistem akan fallback ke environment variable.`)) return;
    try {
      const res = await fetch(`/api/rahaza/integration-settings/${keyName}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.ok) {
        setSuccess(data.message);
        fetchKeys();
        setTimeout(() => setSuccess(''), 4000);
      } else {
        setError(data.detail || 'Gagal menghapus.');
      }
    } catch (e) {
      setError('Gagal terhubung ke server.');
    }
  };

  const handleTest = async (keyName) => {
    setTesting(t => ({ ...t, [keyName]: true }));
    try {
      const res = await fetch(`/api/rahaza/integration-settings/test/${keyName}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setTestResults(r => ({ ...r, [keyName]: data }));
    } catch (e) {
      setTestResults(r => ({ ...r, [keyName]: { ok: false, message: 'Gagal menghubungi server.' } }));
    } finally {
      setTesting(t => ({ ...t, [keyName]: false }));
    }
  };

  const openEdit = (key) => {
    setEditKey(key.key_name);
    setForm({
      key_name: key.key_name,
      value: '',
      description: key.description || '',
      category: key.category || 'ai',
    });
    setAddOpen(true);
  };

  const openAdd = () => {
    setEditKey(null);
    setForm({ key_name: '', value: '', description: '', category: 'ai' });
    setAddOpen(true);
  };

  // Group keys by category
  const grouped = {};
  keys.forEach(k => {
    const cat = k.category || 'custom';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(k);
  });

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Integrasi & API Keys</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Kelola kunci API dan konfigurasi integrasi layanan eksternal. Kunci disimpan di database terenkripsi.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={fetchKeys} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {canEdit && (
            <Button size="sm" onClick={openAdd} className="bg-primary text-foreground">
              <Plus className="w-4 h-4 mr-1.5" /> Tambah Kunci
            </Button>
          )}
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-lg px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
          <CheckCircle className="w-4 h-4 shrink-0" /> {success}
        </div>
      )}

      {/* Info banner */}
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-3">
        <div className="flex items-start gap-2">
          <Key className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
          <div className="text-sm text-blue-700 dark:text-blue-300">
            <p className="font-medium">Prioritas penggunaan kunci:</p>
            <p className="text-xs mt-1 text-blue-600 dark:text-blue-400">
              1. Nilai yang dikonfigurasi di sini (database) — diutamakan<br />
              2. Environment variable (.env) — fallback otomatis jika tidak ada di database
            </p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([cat, catKeys]) => {
            const meta = CATEGORY_META[cat] || CATEGORY_META.custom;
            const CatIcon = meta.icon;
            return (
              <div key={cat} className="bg-[var(--card-surface)] rounded-xl border border-border shadow-sm">
                <div className={`flex items-center gap-2 px-5 py-3 border-b border-border ${meta.bg} rounded-t-xl`}>
                  <CatIcon className={`w-4 h-4 ${meta.color}`} />
                  <h3 className="font-semibold text-sm text-foreground">{meta.label}</h3>
                  <span className="text-xs text-muted-foreground ml-auto">{catKeys.length} kunci</span>
                </div>
                <div className="divide-y divide-border">
                  {catKeys.map(key => (
                    <div key={key.key_name} className="px-5 py-4" data-testid={`key-row-${key.key_name}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-sm font-semibold text-foreground">{key.key_name}</span>
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                              key.is_configured
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400'
                                : 'bg-[var(--glass-bg)] text-muted-foreground'
                            }`}>
                              {key.is_configured ? <CheckCircle className="w-2.5 h-2.5" /> : <XCircle className="w-2.5 h-2.5" />}
                              {key.is_configured ? `Dikonfigurasi (${key.source})` : 'Belum dikonfigurasi'}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{key.description}</p>
                          {key.is_configured && (
                            <div className="flex items-center gap-2 mt-2">
                              <code className="text-xs font-mono bg-[var(--glass-bg)] px-2 py-0.5 rounded border border-border">
                                {showValues[key.key_name] ? '(nilai tersembunyi — klik ikon mata untuk reveal)' : key.masked_value || '(env)'}
                              </code>
                              {key.updated_at && (
                                <span className="text-[10px] text-muted-foreground">
                                  Diperbarui: {new Date(key.updated_at).toLocaleDateString('id-ID')}
                                  {key.updated_by && ` oleh ${key.updated_by}`}
                                </span>
                              )}
                            </div>
                          )}
                          {testResults[key.key_name] && (
                            <div className={`flex items-center gap-1.5 mt-2 text-xs ${
                              testResults[key.key_name].ok ? 'text-emerald-600' : 'text-red-600'
                            }`}>
                              {testResults[key.key_name].ok
                                ? <CheckCircle className="w-3.5 h-3.5" />
                                : <XCircle className="w-3.5 h-3.5" />}
                              {testResults[key.key_name].message}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => handleTest(key.key_name)}
                            disabled={testing[key.key_name]}
                            title="Uji kunci"
                            data-testid={`test-key-${key.key_name}`}
                          >
                            <TestTube2 className={`w-3.5 h-3.5 ${testing[key.key_name] ? 'animate-pulse' : ''}`} />
                          </Button>
                          {canEdit && (
                            <Button
                              variant="ghost" size="sm"
                              onClick={() => openEdit(key)}
                              title="Edit kunci"
                              data-testid={`edit-key-${key.key_name}`}
                            >
                              <Key className="w-3.5 h-3.5" />
                            </Button>
                          )}
                          {canDelete && key.source === 'db' && (
                            <Button
                              variant="ghost" size="sm"
                              onClick={() => handleDelete(key.key_name)}
                              className="text-red-700 dark:text-red-500 hover:text-red-600"
                              title="Hapus dari DB"
                              data-testid={`delete-key-${key.key_name}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add/Edit Modal */}
      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-border shadow-2xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold text-foreground mb-4">
              {editKey ? `Edit Kunci: ${editKey}` : 'Tambah Kunci API'}
            </h2>
            <form onSubmit={handleSave} className="space-y-4">
              {!editKey && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">Nama Kunci *</label>
                  <input
                    type="text"
                    required
                    className="w-full border border-border rounded-lg px-3 py-2.5 text-sm font-mono uppercase"
                    placeholder="CONTOH_API_KEY"
                    value={form.key_name}
                    onChange={e => setForm(f => ({ ...f, key_name: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') }))}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Hanya huruf kapital, angka, dan underscore.</p>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {editKey ? 'Nilai Baru *' : 'Nilai *'}
                </label>
                <div className="relative">
                  <input
                    type={showValues['_form'] ? 'text' : 'password'}
                    required
                    className="w-full border border-border rounded-lg px-3 py-2.5 text-sm font-mono pr-10"
                    placeholder={editKey ? 'Masukkan nilai baru untuk mengganti...' : 'Masukkan nilai kunci...'}
                    value={form.value}
                    onChange={e => setForm(f => ({ ...f, value: e.target.value }))}
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    onClick={() => setShowValues(s => ({ ...s, _form: !s._form }))}
                  >
                    {showValues['_form'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Deskripsi (opsional)</label>
                <input
                  type="text"
                  className="w-full border border-border rounded-lg px-3 py-2.5 text-sm"
                  placeholder="Keterangan penggunaan kunci ini..."
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Kategori</label>
                <SmartNativeSelect
                  className="w-full border border-border rounded-lg px-3 py-2.5 text-sm bg-[var(--card-surface)]"
                  value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                >
                  {Object.entries(CATEGORY_META).map(([val, meta]) => (
                    <option key={val} value={val}>{meta.label}</option>
                  ))}
                </SmartNativeSelect>
              </div>
              {error && (
                <p className="text-sm text-red-600">{error}</p>
              )}
              <div className="flex gap-2 pt-2">
                <Button type="submit" disabled={saving} className="flex-1 bg-primary text-foreground">
                  <Save className="w-4 h-4 mr-1.5" />
                  {saving ? 'Menyimpan...' : 'Simpan'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => { setAddOpen(false); setEditKey(null); setError(''); }}
                >
                  Batal
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
