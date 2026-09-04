import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Calculator, Plus, Trash2, Pencil, X, AlertTriangle } from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import { formatRupiah } from '@/lib/format';
import RnDUnitSelect, { UOM_STATUS } from './RnDUnitSelect';

const API = process.env.REACT_APP_BACKEND_URL || '';
const fmt = (n) => n != null ? formatRupiah(n) : '—';

const emptyAcc = { name: '', material_id: '', qty: 0, unit: 'm', unit_cost: 0 };

const emptyForm = {
  sample_code: '', style_id: '', style_name: '',
  fabric_items: [{ name: 'Main Fabric', material_id: '', qty: 1, unit: 'm', unit_cost: 0 }],
  trim_items: [],
  labor_cost: 0,
  overhead_cost: 0,
  notes: '',
};

/** Baris hasil hitung server: qty asli → qty pada satuan harga → biaya. */
function LineHint({ row }) {
  if (!row) return null;
  const st = UOM_STATUS[row.uom_status] || {};
  const warn = st.warn || row.price_source === 'unresolved';
  return (
    <div className={`col-span-full -mt-1 mb-1 text-[11px] leading-snug ${warn ? 'text-red-600 dark:text-red-400' : 'text-foreground/50'}`}
      data-testid="costing-line-hint">
      {warn && <AlertTriangle className="inline w-3 h-3 mr-1 -mt-0.5" />}
      {row.qty} {row.unit} → <b>{row.qty_priced}</b> {row.price_unit} × {fmt(row.price_per_unit)} = <b>{fmt(row.total_cost)}</b>
      {row.uom_note ? ` · ${row.uom_note}` : (st.label ? ` · ${st.label}` : '')}
      {row.price_source === 'unresolved' && ' · harga belum ada, isi harga atau lengkapi Riset Material'}
    </div>
  );
}

export default function RnDCostingTab({ token }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const [costings, setCostings] = useState([]);
  const [styles,   setStyles]   = useState([]);
  const [samples,  setSamples]  = useState([]);
  const [matOpts,  setMatOpts]  = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing,  setEditing]  = useState(null);
  const [form,     setForm]     = useState({ ...emptyForm });
  const [calc,     setCalc]     = useState(null);   // hasil hitung server (sadar satuan)
  const [delId,    setDelId]    = useState(null);
  const [expanded, setExpanded] = useState(null);

  const f = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const fetchCostings = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/sample-costing`, { headers: h });
      if (res.ok) setCostings(await res.json());
    } catch { toast.error('Gagal memuat costing'); }
    finally { setLoading(false); }
  };

  const fetchRef = async (path, setter) => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/${path}`, { headers: h });
      if (res.ok) {
        const data = await res.json();
        setter(Array.isArray(data) ? data : (data.items || []));
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchCostings();
    fetchRef('styles', setStyles);
    fetchRef('sample-requests', setSamples);
    fetchRef('material-options', setMatOpts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Pratinjau biaya dari SERVER (satuan dikonversi di sana) ────────────────
  const fetchCalc = useCallback(async (payload) => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/sample-costing/preview`, {
        method: 'POST', headers: h, body: JSON.stringify(payload),
      });
      if (res.ok) setCalc(await res.json());
    } catch { /* ignore */ }
  }, [token]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!showForm) return;
    const t = setTimeout(() => fetchCalc({
      fabric_items: form.fabric_items, trim_items: form.trim_items,
      labor_cost: form.labor_cost, overhead_cost: form.overhead_cost,
    }), 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.fabric_items, form.trim_items, form.labor_cost, form.overhead_cost, showForm, fetchCalc]);

  const setRow = (key, i, k, v) => {
    const items = [...(form[key] || [])];
    let row = { ...items[i], [k]: ['qty', 'unit_cost'].includes(k) ? Number(v) : v };
    if (k === 'material_id') {
      const m = matOpts.find(o => o.material_id === v);
      if (m) row = { ...row, name: m.name, unit: row.unit || m.base_unit };
    }
    items[i] = row;
    f(key, items);
  };
  const addRow = (key, seed) => f(key, [...(form[key] || []), { ...emptyAcc, ...seed }]);
  const removeRow = (key, i) => f(key, (form[key] || []).filter((_, j) => j !== i));

  const setStyleField = sid => {
    const sel = styles.find(s => s.id === sid);
    setForm(p => ({ ...p, style_id: sid, style_name: sel?.style_name || '' }));
  };

  const setSampleField = sc => {
    const sel = samples.find(s => s.sample_code === sc);
    if (sel) setForm(p => ({ ...p, sample_code: sc, sample_request_id: sel.id, style_id: sel.style_id || p.style_id, style_name: sel.style_name || p.style_name }));
    else f('sample_code', sc);
  };

  const openEdit = rec => {
    setForm({
      sample_code: rec.sample_code || '',
      sample_request_id: rec.sample_request_id || '',
      style_id: rec.style_id || '',
      style_name: rec.style_name || '',
      fabric_items: rec.fabric_items?.length ? rec.fabric_items : [{ ...emptyAcc }],
      trim_items: rec.trim_items || [],
      labor_cost: rec.labor_cost || 0,
      overhead_cost: rec.overhead_cost || 0,
      notes: rec.notes || '',
    });
    setCalc(null);
    setEditing(rec.id);
    setShowForm(true);
  };

  const openNew = () => {
    setEditing(null);
    setForm({ ...emptyForm });
    setCalc(null);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.sample_code && !form.sample_request_id) {
      toast.error('Pilih kode sample dulu');
      return;
    }
    try {
      const method = editing ? 'PUT' : 'POST';
      const url = editing
        ? `${API}/api/dewi/rnd/sample-costing/${editing}`
        : `${API}/api/dewi/rnd/sample-costing`;
      const res = await fetch(url, { method, headers: h, body: JSON.stringify(form) });
      const data = await res.json().catch(() => null);
      if (!res.ok) { toast.error(data?.detail || 'Gagal menyimpan costing'); return; }
      toast.success(editing ? 'Costing diperbarui' : 'Costing ditambahkan');
      if (data?.uom_warnings?.length) {
        toast.warning(`Satuan perlu dibereskan: ${data.uom_warnings.slice(0, 2).join(' | ')}`);
      }
      setShowForm(false);
      setEditing(null);
      setForm({ ...emptyForm });
      fetchCostings();
    } catch { toast.error('Gagal menyimpan costing'); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/rnd/sample-costing/${delId}`, { method: 'DELETE', headers: h });
      toast.success('Costing dihapus');
      setDelId(null);
      fetchCostings();
    } catch { toast.error('Gagal menghapus'); }
  };

  const rowsOf = (key) => (calc?.[key] || []);

  const renderRows = (key, testPrefix) => (form[key] || []).map((it, i) => (
    <div key={i} className="grid grid-cols-[1fr_150px_70px_92px_96px_28px] gap-2 mb-2">
      <Input value={it.name} onChange={e => setRow(key, i, 'name', e.target.value)}
        placeholder="Nama bahan" className="text-sm" data-testid={`${testPrefix}-name-${i}`} />
      <SmartNativeSelect value={it.material_id || ''}
        onChange={e => setRow(key, i, 'material_id', e.target.value)}
        data-testid={`${testPrefix}-master-${i}`}
        className="w-full text-sm">
        <option value="">Tautkan master…</option>
        {matOpts.map(m => (
          <option key={m.material_id} value={m.material_id}>{m.code} — {m.name} ({m.base_unit})</option>
        ))}
      </SmartNativeSelect>
      <Input type="number" value={it.qty} onChange={e => setRow(key, i, 'qty', e.target.value)}
        placeholder="Qty" className="text-sm" data-testid={`${testPrefix}-qty-${i}`} />
      <RnDUnitSelect value={it.unit} onChange={e => setRow(key, i, 'unit', e.target.value)}
        testId={`${testPrefix}-unit-${i}`} />
      <Input type="number" value={it.unit_cost} onChange={e => setRow(key, i, 'unit_cost', e.target.value)}
        placeholder="Harga" className="text-sm" data-testid={`${testPrefix}-price-${i}`} />
      <Button variant="ghost" size="sm" onClick={() => removeRow(key, i)}
        className="h-9 w-7 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:bg-red-500/10">
        <X className="w-3.5 h-3.5" /></Button>
      <LineHint row={rowsOf(key)[i]} />
    </div>
  ));

  return (
    <div className="p-6 space-y-5" data-testid="rnd-costing-tab">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Calculator className="w-5 h-5 text-violet-500" /> Sample Costing
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            Rincian biaya per sample — qty dikonversi otomatis ke satuan harga material
          </p>
        </div>
        <Button onClick={openNew} className="gap-2" data-testid="create-costing-btn">
          <Plus className="w-4 h-4" /> Tambah Costing
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : costings.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Calculator className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada data costing.</p>
          <Button variant="outline" className="mt-3" onClick={openNew}>+ Tambah Costing Pertama</Button>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {costings.map(c => (
            <GlassCard key={c.id} className="p-4" data-testid={`costing-card-${c.id}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm font-semibold text-foreground">{c.sample_code || '—'}</span>
                    {c.style_name && <span className="text-xs text-foreground/50">{c.style_name}</span>}
                    {c.uom_warnings?.length > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> {c.uom_warnings.length} satuan bermasalah
                      </span>
                    )}
                  </div>
                  <div className="flex gap-6 mt-2 text-sm">
                    <span className="text-foreground/60">Material: <strong className="text-foreground">{fmt(c.total_material_cost)}</strong></span>
                    <span className="text-foreground/60">Tenaga: <strong className="text-foreground">{fmt(c.labor_cost)}</strong></span>
                    <span className="text-foreground/60">Overhead: <strong className="text-foreground">{fmt(c.overhead_cost)}</strong></span>
                    <span className="text-violet-600 dark:text-violet-400">Total: <strong>{fmt(c.total_cost)}</strong></span>
                  </div>
                </div>
                <div className="flex gap-1 ml-4">
                  <Button variant="ghost" size="sm" onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                    className="h-7 px-2 text-xs text-foreground/50" data-testid={`costing-detail-${c.id}`}>
                    {expanded === c.id ? 'Tutup' : 'Rincian'}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openEdit(c)}
                    className="h-7 w-7 p-0" data-testid={`costing-edit-${c.id}`}><Pencil className="w-3.5 h-3.5" /></Button>
                  <Button variant="ghost" size="sm" onClick={() => setDelId(c.id)}
                    className="h-7 w-7 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:bg-red-500/10">
                    <Trash2 className="w-3.5 h-3.5" /></Button>
                </div>
              </div>
              {expanded === c.id && (
                <div className="mt-4 space-y-3 border-t border-foreground/10 pt-4">
                  {[['fabric_items', 'Bahan Kain'], ['trim_items', 'Aksesoris / Trim']].map(([key, label]) => (
                    c[key]?.length > 0 && (
                      <div key={key}>
                        <div className="text-xs font-semibold text-foreground/50 uppercase tracking-wider mb-2">{label}</div>
                        {c[key].map((it, i) => {
                          const st = UOM_STATUS[it.uom_status] || {};
                          return (
                            <div key={i} className="flex justify-between text-xs py-1 gap-3">
                              <span className="text-foreground/70">
                                {it.name}
                                {st.warn && <span className="text-red-600 dark:text-red-400 ml-1">({st.label})</span>}
                              </span>
                              <span className="text-foreground/70 text-right">
                                {it.qty} {it.unit}
                                {it.qty_priced != null && it.price_unit && it.unit !== it.price_unit &&
                                  <> → {it.qty_priced} {it.price_unit}</>}
                                {' '}× {fmt(it.price_per_unit ?? it.unit_cost)} = <strong>{fmt(it.total_cost ?? (it.qty * it.unit_cost))}</strong>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )
                  ))}
                  {c.uom_warnings?.length > 0 && (
                    <ul className="text-xs text-red-600 dark:text-red-400 list-disc pl-4 space-y-0.5">
                      {c.uom_warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  )}
                  {c.notes && <p className="text-xs text-foreground/40 italic">{c.notes}</p>}
                </div>
              )}
            </GlassCard>
          ))}
        </div>
      )}

      {/* Form Modal */}
      <Modal open={showForm} onClose={() => setShowForm(false)}
        title={editing ? 'Edit Sample Costing' : 'Tambah Sample Costing'} size="lg">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Kode Sample</Label>
              <SmartNativeSelect value={form.sample_code}
                onChange={e => setSampleField(e.target.value)}
                data-testid="costing-sample-select"
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                <option value="">-- Pilih Kode Sample --</option>
                {samples.map(s => <option key={s.id} value={s.sample_code}>{s.sample_code} — {s.style_name}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <Label>Style</Label>
              <SmartNativeSelect value={form.style_id} onChange={e => setStyleField(e.target.value)}
                data-testid="costing-style-select"
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                <option value="">-- Pilih Style --</option>
                {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
              </SmartNativeSelect>
            </div>
          </div>

          <div className="text-[11px] text-foreground/50 bg-foreground/5 rounded-md px-3 py-2">
            Tautkan baris ke <b>master material</b> agar satuannya bisa dikonversi (mis. gram→kg, lusin→pcs,
            meter↔kg untuk kain lewat gramasi &amp; lebar). Kolom Harga boleh dikosongkan — sistem memakai harga
            Riset Material / master material.
          </div>

          {/* Fabric items */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Bahan Kain</Label>
              <Button type="button" variant="outline" size="sm" onClick={() => addRow('fabric_items', { unit: 'm' })}
                className="h-7 text-xs gap-1" data-testid="add-fabric-row">
                <Plus className="w-3 h-3" /> Tambah Bahan
              </Button>
            </div>
            {renderRows('fabric_items', 'fabric')}
          </div>

          {/* Trim items */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Aksesoris / Trim</Label>
              <Button type="button" variant="outline" size="sm" onClick={() => addRow('trim_items', { name: 'Label', unit: 'pcs' })}
                className="h-7 text-xs gap-1" data-testid="add-trim-row">
                <Plus className="w-3 h-3" /> Tambah Aksesoris
              </Button>
            </div>
            {renderRows('trim_items', 'trim')}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Ongkos Jahit (Rp)</Label>
              <Input className="mt-1" type="number" value={form.labor_cost}
                onChange={e => f('labor_cost', Number(e.target.value))} data-testid="costing-labor-input" />
            </div>
            <div>
              <Label>Overhead (Rp)</Label>
              <Input className="mt-1" type="number" value={form.overhead_cost}
                onChange={e => f('overhead_cost', Number(e.target.value))} data-testid="costing-overhead-input" />
            </div>
          </div>

          {/* Total dari server */}
          <div className="bg-violet-500/8 border border-violet-300 dark:border-violet-500/20 rounded-lg p-3 space-y-1"
            data-testid="costing-total-panel">
            <div className="flex items-center justify-between">
              <span className="text-sm text-foreground/70">Biaya Material (setelah konversi satuan)</span>
              <span className="text-sm font-semibold text-foreground">{fmt(calc?.total_material_cost ?? 0)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-foreground/70">Total Estimasi</span>
              <span className="text-lg font-bold text-violet-600 dark:text-violet-400" data-testid="costing-total-value">
                {fmt(calc?.total_cost ?? 0)}
              </span>
            </div>
            {calc?.uom_warnings?.length > 0 && (
              <ul className="text-[11px] text-red-600 dark:text-red-400 list-disc pl-4 pt-1 space-y-0.5"
                data-testid="costing-uom-warnings">
                {calc.uom_warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>

          <div>
            <Label>Catatan</Label>
            <textarea value={form.notes} onChange={e => f('notes', e.target.value)}
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none" />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button onClick={handleSave} data-testid="save-costing-btn">Simpan</Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus Costing?"
          message="Data costing akan dihapus permanen."
        />
      )}
    </div>
  );
}
