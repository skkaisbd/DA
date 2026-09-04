import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Edit2, Trash2, CheckCircle2, XCircle } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import ImportExportToolbar from './ImportExportToolbar';
import { Button } from '@/components/ui/button';
import { GlassInput } from '@/components/ui/glass';

// Reusable master-data CRUD page.
// Props:
//   title       : judul halaman
//   description : subtitle
//   endpoint    : '/api/rahaza/locations' etc.
//   token       : auth token
//   columns     : [{ key, label, render?, showInForm? }]
//   fields      : [{ key, label, type: 'text'|'select'|'number'|'readonly', options?:[{value,label}], required?, help? }]
//   defaultItem : initial form state
//   testIdPrefix
//   canEdit     : boolean (default true)
export default function MasterDataCRUD({
  title, description, endpoint, token,
  columns = [], fields = [], defaultItem = {},
  testIdPrefix = 'md',
  canEdit = true,
  ieKey = null,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(defaultItem);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(endpoint, { headers });
      if (res.ok) {
        const d = await res.json();
        // Unwrap paginated responses ({items|rows|data|results:[...]}) → always store an array.
        setRows(Array.isArray(d) ? d : (d?.items || d?.rows || d?.data || d?.results || []));
      }
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, token]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openCreate = () => { setEditing(null); setForm(defaultItem); setError(''); setModalOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    const f = { ...defaultItem };
    fields.forEach(fld => { f[fld.key] = row[fld.key] ?? defaultItem[fld.key] ?? ''; });
    setForm(f);
    setError('');
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true); setError('');
    try {
      const url = editing ? `${endpoint}/${editing.id}` : endpoint;
      const method = editing ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers, body: JSON.stringify(form) });
      if (!res.ok) {
        // Status-based friendly message (body stream may be consumed by
        // third-party scripts like analytics wrappers — don't rely on it).
        const STATUS_MSG = {
          400: 'Data tidak valid. Periksa kembali isian form.',
          401: 'Sesi berakhir. Silakan login ulang.',
          403: 'Anda tidak punya akses untuk aksi ini.',
          404: 'Data tidak ditemukan.',
          409: `Kode "${form.code || form.employee_code || ''}" sudah terpakai. Gunakan kode lain.`,
          422: 'Format data tidak sesuai.',
          500: 'Server error. Coba lagi beberapa saat.',
        };
        let msg = STATUS_MSG[res.status] || `Gagal menyimpan (HTTP ${res.status})`;
        // Try to read body for more detail (may fail if intercepted)
        try {
          const clone = res.clone();
          const data = await clone.json();
          if (data && typeof data.detail === 'string') msg = data.detail;
          else if (data && Array.isArray(data.detail) && data.detail[0]?.msg) msg = data.detail.map(d => d.msg).join(', ');
        } catch (_) { /* body unreadable — keep status-based msg */ }
        throw new Error(msg);
      }
      setModalOpen(false);
      await fetchRows();
    } catch (err) { setError(err.message || 'Terjadi kesalahan tidak terduga'); }
    finally { setSaving(false); }
  };

  const handleDeactivate = async (row) => {
    if (!window.confirm(`Nonaktifkan "${row.name || row.code}"?`)) return;
    await fetch(`${endpoint}/${row.id}`, { method: 'DELETE', headers });
    fetchRows();
  };

  const activeCol = {
    key: 'active', label: 'Status',
    render: (v) => v
      ? <span className="inline-flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 className="w-3.5 h-3.5" /> Aktif</span>
      : <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><XCircle className="w-3.5 h-3.5" /> Nonaktif</span>,
  };

  const actionsCol = canEdit ? {
    key: '_actions', label: 'Aksi',
    render: (_, row) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" data-testid={`${testIdPrefix}-edit-${row.id}`}><Edit2 className="w-3.5 h-3.5" /></button>
        {row.active && (
          <button onClick={() => handleDeactivate(row)} className="p-1.5 rounded hover:bg-red-400/10 text-muted-foreground hover:text-red-400" data-testid={`${testIdPrefix}-deactivate-${row.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
        )}
      </div>
    ),
  } : null;

  const fullColumns = [...columns, activeCol, ...(actionsCol ? [actionsCol] : [])];

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
    </div>
  );

  return (
    <div className="space-y-6" data-testid={`${testIdPrefix}-page`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{title}</h1>
          {description && <p className="text-muted-foreground text-sm mt-1">{description}</p>}
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            {ieKey && <ImportExportToolbar collectionKey={ieKey} label={title} onImported={fetchRows} />}
            <Button onClick={openCreate} data-testid={`${testIdPrefix}-add-btn`}>
              <Plus className="w-4 h-4 mr-1.5" /> Tambah
            </Button>
          </div>
        )}
        {!canEdit && ieKey && (
          <ImportExportToolbar collectionKey={ieKey} label={title} onImported={fetchRows} />
        )}
      </div>

      <DataTable
        columns={fullColumns}
        data={rows}
        searchKeys={columns.map(c => c.key)}
      />

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? `Edit ${title}` : `Tambah ${title}`}>
          <div className="space-y-4" data-testid={`${testIdPrefix}-form`}>
            {error && <div className="bg-red-400/10 border border-red-300/20 rounded-lg p-3 text-sm text-red-300" data-testid={`${testIdPrefix}-error`}>{error}</div>}
            {fields.filter(f => !(editing && f.createOnly) && !(f.editOnly && !editing)).map(fld => (
              <div key={fld.key}>
                <label className="block text-sm font-medium text-foreground/70 mb-1.5">
                  {fld.label} {fld.required && <span className="text-red-400">*</span>}
                </label>
                {fld.type === 'select' ? (
                  <SmartNativeSelect
                    value={form[fld.key] ?? ''}
                    onChange={e => setForm({ ...form, [fld.key]: e.target.value })}
                    className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    data-testid={`${testIdPrefix}-field-${fld.key}`}
                  >
                    <option value="">— Pilih —</option>
                    {(fld.options || []).map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </SmartNativeSelect>
                ) : fld.type === 'number' ? (
                  <GlassInput
                    type="number"
                    value={form[fld.key] ?? ''}
                    onChange={e => setForm({ ...form, [fld.key]: e.target.value === '' ? '' : Number(e.target.value) })}
                    placeholder={fld.placeholder || ''}
                    data-testid={`${testIdPrefix}-field-${fld.key}`}
                  />
                ) : (
                  <GlassInput
                    type={fld.type === 'time' ? 'time' : 'text'}
                    value={form[fld.key] ?? ''}
                    onChange={e => setForm({ ...form, [fld.key]: e.target.value })}
                    placeholder={fld.placeholder || ''}
                    disabled={fld.type === 'readonly'}
                    data-testid={`${testIdPrefix}-field-${fld.key}`}
                  />
                )}
                {fld.help && <p className="text-xs text-muted-foreground mt-1">{fld.help}</p>}
              </div>
            ))}
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
              <Button onClick={handleSave} disabled={saving} data-testid={`${testIdPrefix}-save-btn`}>
                {saving ? 'Menyimpan...' : 'Simpan'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
