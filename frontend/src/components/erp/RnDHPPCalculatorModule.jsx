import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Calculator, Plus, Trash2, Pencil, RefreshCw, TrendingUp, PackageOpen,
  Scissors, Settings2, Save, X, Wand2, AlertTriangle, Layers, Database,
  PenLine, CheckCircle2, History,
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL || '';

const fmt = (n) => (n != null && n !== '' ? formatRupiah(n) : '—');

const emptyAcc = { name: '', unit_cost: 0, qty: 1 };

/** F4 — sumber biaya PER BARIS. Menggantikan saklar global `use_bom`
 *  (semua-atau-tidak) yang membuat master + custom MUSTAHIL dicampur. */
const SOURCES = [
  { value: 'master',   label: 'Master',   Icon: Database, hint: 'Harga dari master material (rahaza_materials)' },
  { value: 'techpack', label: 'Techpack', Icon: Layers,   hint: 'Dari BOM Tech Pack terbaru style ini' },
  { value: 'manual',   label: 'Manual',   Icon: PenLine,  hint: 'Custom field — nama & harga sendiri' },
];

const SOURCE_CLS = {
  master:   'bg-sky-100 dark:bg-sky-500/20 text-sky-700 dark:text-sky-300 border-sky-300 dark:border-sky-500/40',
  techpack: 'bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-500/40',
  manual:   'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40',
};

const emptyForm = {
  hpp_code: '', style_id: '', style_code: '', style_name: '',
  fabric_usage_per_pcs: 0,
  fabric_price_per_meter: 0,
  fabric_source: 'manual', fabric_size: '',
  accessories_cost: [{ name: 'Label / Tag', unit_cost: 500, qty: 1 }],
  cost_lines: [],
  cmt_cost_per_pcs: 0, cmt_cost_source: 'manual', cmt_cost_ref: '',
  cutting_cost_per_pcs: 0,
  packaging_cost_per_pcs: 0,
  overhead_pct: 10,
  margin_pct: 30,
  use_bom: false,
  notes: '', status: 'draft',
};

const PREVIEW_INIT = {
  fabric_cost: 0, accessories_total: 0, material_cost: 0, cmt_cost: 0, cutting_cost: 0,
  packaging_cost: 0, direct_cost: 0, overhead_value: 0,
  hpp_total: 0, selling_price_proposal: 0,
  margin_pct: 30, overhead_pct: 10,
};

let lineSeq = 0;
const newLineId = () => `l_${Date.now().toString(36)}_${lineSeq++}`;

async function readErr(res, fallback) {
  try { const d = await res.json(); return d?.detail || fallback; } catch { return fallback; }
}

export default function RnDHPPCalculatorModule({ token }) {
  const hdr = useMemo(() => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }), [token]);
  const [records, setRecords]   = useState([]);
  const [styles,  setStyles]    = useState([]);
  const [matOpts, setMatOpts]   = useState([]);
  const [cmtOpts, setCmtOpts]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing,  setEditing]  = useState(null);
  const [form,     setForm]     = useState({ ...emptyForm });
  const [preview,  setPreview]  = useState(PREVIEW_INIT);
  const [prevLoading, setPrevLoading] = useState(false);
  const [prevError, setPrevError] = useState('');
  const [computed, setComputed] = useState([]);   // cost_lines hasil hitungan server
  const [delId,    setDelId]    = useState(null);
  const [stale,    setStale]    = useState(null);
  const [saving,   setSaving]   = useState(false);

  const f = (name, val) => setForm(prev => ({ ...prev, [name]: val }));

  // ── estimasi kain dari techpack (mode lama, tetap dipertahankan) ──
  const [fabricEst, setFabricEst] = useState(null);
  const [fabricEstLoading, setFabricEstLoading] = useState(false);

  const hybrid = (form.cost_lines || []).length > 0;

  // ─────────────────────────── loaders ───────────────────────────
  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator`, { headers: hdr });
      const d = await res.json();
      setRecords(Array.isArray(d) ? d : []);
    } catch { toast.error('Gagal memuat HPP'); }
    finally { setLoading(false); }
  }, [hdr]);

  const loadStyles = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles`, { headers: hdr });
      const data = await res.json();
      setStyles(Array.isArray(data) ? data : (data.items || []));
    } catch { /* ignore */ }
  }, [hdr]);

  const loadMatOpts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/material-options`, { headers: hdr });
      if (res.ok) setMatOpts(await res.json());
    } catch { /* ignore */ }
  }, [hdr]);

  const loadCmtOpts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator/cmt-suggestions`, { headers: hdr });
      if (res.ok) setCmtOpts(await res.json());
    } catch { /* ignore */ }
  }, [hdr]);

  useEffect(() => { loadRecords(); loadStyles(); loadMatOpts(); loadCmtOpts(); },
    [loadRecords, loadStyles, loadMatOpts, loadCmtOpts]);

  // ─────────────────────────── live preview ───────────────────────────
  const fetchPreview = useCallback(async (formData) => {
    setPrevLoading(true);
    try {
      const useLines = (formData.cost_lines || []).length > 0;
      const endpoint = useLines
        ? 'preview'
        : (formData.use_bom ? 'compute-from-bom' : 'preview');
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator/${endpoint}`, {
        method: 'POST', headers: hdr, body: JSON.stringify(formData),
      });
      if (res.ok) {
        const data = await res.json();
        setPreview(data);
        setPrevError('');
        setComputed(useLines ? (data.cost_lines || []) : (data.material_breakdown || []));
      } else {
        setPrevError(await readErr(res, 'Gagal menghitung'));
      }
    } catch { setPrevError('Gagal menghubungi server'); }
    finally { setPrevLoading(false); }
  }, [hdr]);

  useEffect(() => {
    if (!showForm) return;
    const t = setTimeout(() => fetchPreview(form), 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    form.fabric_usage_per_pcs, form.fabric_price_per_meter,
    form.accessories_cost, form.cost_lines, form.cmt_cost_per_pcs,
    form.cutting_cost_per_pcs, form.packaging_cost_per_pcs,
    form.overhead_pct, form.margin_pct, form.use_bom, form.style_id,
    showForm, fetchPreview,
  ]);

  // ─────────────────────────── open / edit ───────────────────────────
  const openNew = () => {
    setForm({ ...emptyForm, hpp_code: `HPP-${Date.now().toString(36).toUpperCase()}` });
    setPreview(PREVIEW_INIT); setComputed([]); setStale(null); setPrevError('');
    setEditing(null); setShowForm(true);
  };

  const openEdit = async (rec) => {
    setForm({
      hpp_code: rec.hpp_code || '',
      style_id: rec.style_id || '',
      style_code: rec.style_code || '',
      style_name: rec.style_name || '',
      fabric_usage_per_pcs: rec.fabric_usage_per_pcs || 0,
      fabric_price_per_meter: rec.fabric_price_per_meter || 0,
      fabric_source: rec.fabric_source || 'manual',
      fabric_size: rec.fabric_size || '',
      accessories_cost: rec.accessories_cost?.length ? rec.accessories_cost : [{ ...emptyAcc }],
      // dokumen lama dibaca sebagai cost_lines oleh backend (legacy mapping)
      cost_lines: (rec.cost_lines || []).map(l => ({ ...l, line_id: l.line_id || newLineId() })),
      cmt_cost_per_pcs: rec.cmt_cost_per_pcs || 0,
      cmt_cost_source: rec.cmt_cost_source || 'manual',
      cmt_cost_ref: rec.cmt_cost_ref || '',
      cutting_cost_per_pcs: rec.cutting_cost_per_pcs || 0,
      packaging_cost_per_pcs: rec.packaging_cost_per_pcs || 0,
      overhead_pct: rec.overhead_pct ?? 10,
      margin_pct: rec.margin_pct ?? 30,
      use_bom: !!rec.use_bom,
      notes: rec.notes || '',
      status: rec.status || 'draft',
    });
    setComputed(rec.cost_lines || rec.bom_breakdown || []);
    setPreview({
      fabric_cost: rec.fabric_cost, accessories_total: rec.accessories_total,
      material_cost: rec.material_cost,
      cmt_cost: rec.cmt_cost, cutting_cost: rec.cutting_cost,
      packaging_cost: rec.packaging_cost, direct_cost: rec.direct_cost,
      overhead_value: rec.overhead_value, hpp_total: rec.hpp_total,
      selling_price_proposal: rec.selling_price_proposal,
      margin_pct: rec.margin_pct, overhead_pct: rec.overhead_pct,
    });
    setPrevError(''); setEditing(rec.id); setShowForm(true);
    checkStale(rec.id);
  };

  const checkStale = async (id) => {
    setStale(null);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator/${id}/stale-check`, { headers: hdr });
      if (res.ok) setStale(await res.json());
    } catch { /* ignore */ }
  };

  const setStyleField = (styleId) => {
    const sel = styles.find(s => s.id === styleId);
    setForm(prev => ({ ...prev, style_id: styleId, style_code: sel?.style_code || '', style_name: sel?.style_name || '' }));
    setFabricEst(null);
  };

  // ─────────────────────────── cost lines ───────────────────────────
  const setLine = (i, patch) => setForm(prev => {
    const lines = [...(prev.cost_lines || [])];
    lines[i] = { ...lines[i], ...patch };
    return { ...prev, cost_lines: lines };
  });

  const removeLine = (i) => setForm(prev => ({
    ...prev, cost_lines: (prev.cost_lines || []).filter((_, j) => j !== i),
  }));

  const addManualLine = () => setForm(prev => ({
    ...prev,
    cost_lines: [...(prev.cost_lines || []), {
      line_id: newLineId(), label: '', source: 'manual',
      qty: 1, unit: 'pcs', unit_cost_used: 0, override: false, override_reason: '',
    }],
  }));

  const addMasterLine = () => setForm(prev => ({
    ...prev,
    cost_lines: [...(prev.cost_lines || []), {
      line_id: newLineId(), label: '', source: 'master', material_id: '',
      qty: 1, unit: '', unit_cost_used: 0, override: false, override_reason: '',
    }],
  }));

  const pullFromTechpack = async () => {
    if (!form.style_id) return toast.error('Pilih Style dulu untuk menarik BOM Tech Pack');
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp-calculator/cost-lines/from-techpack`, {
        method: 'POST', headers: hdr, body: JSON.stringify({ style_id: form.style_id }),
      });
      if (!res.ok) return toast.error(await readErr(res, 'Gagal menarik BOM Tech Pack'), { duration: 7000 });
      const d = await res.json();
      const incoming = (d.cost_lines || []).map(l => ({ ...l, line_id: l.line_id || newLineId() }));
      setForm(prev => ({ ...prev, cost_lines: [...(prev.cost_lines || []), ...incoming] }));
      toast.success(`${incoming.length} baris BOM Tech Pack ditambahkan (sumber: Techpack)`);
      if (d.unlinked_count > 0) {
        toast.warning(`${d.unlinked_count} baris tidak tertaut master — harganya Rp0. Tautkan materialnya di Tech Pack, atau ubah sumbernya jadi Manual.`, { duration: 9000 });
      }
    } catch { toast.error('Gagal menarik BOM Tech Pack'); }
  };

  const applyMasterPrices = () => {
    // buang override → semua baris master/techpack kembali ke harga master terbaru
    setForm(prev => ({
      ...prev,
      cost_lines: (prev.cost_lines || []).map(l => l.source === 'manual'
        ? l : { ...l, override: false, override_reason: '', unit_cost_used: 0 }),
    }));
    toast.success('Semua baris master dikembalikan ke harga master terbaru');
  };

  const setAcc = (idx, field, val) => {
    const acc = [...form.accessories_cost];
    acc[idx] = { ...acc[idx], [field]: ['unit_cost', 'qty'].includes(field) ? Number(val) : val };
    f('accessories_cost', acc);
  };
  const addAcc = () => f('accessories_cost', [...form.accessories_cost, { ...emptyAcc }]);
  const removeAcc = (idx) => f('accessories_cost', form.accessories_cost.filter((_, i) => i !== idx));

  const loadFabricEstimate = async () => {
    if (!form.style_id) { toast.error('Pilih Style dulu untuk menghitung kain dari techpack'); return; }
    setFabricEstLoading(true);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/hpp/fabric-estimate?style_id=${form.style_id}`, { headers: hdr });
      const data = await res.json();
      if (!res.ok) { toast.error(data?.detail || 'Techpack belum ada untuk style ini'); setFabricEst(null); return; }
      if (!data.sizes || data.sizes.length === 0) { toast.error('Techpack belum punya data Penggunaan Bahan'); setFabricEst(null); return; }
      setFabricEst(data);
      if (data.has_unresolved_price) toast.warning('Sebagian harga kain belum diset di Riset Material (dianggap Rp0).');
      else toast.success('Estimasi kain dimuat dari techpack');
    } catch { toast.error('Gagal memuat estimasi kain'); }
    finally { setFabricEstLoading(false); }
  };

  const applyFabricSize = (sz) => {
    setForm(prev => ({ ...prev,
      fabric_usage_per_pcs: sz.meters_per_pcs,
      fabric_price_per_meter: sz.weighted_price_per_meter,
      fabric_source: 'techpack', fabric_size: sz.size,
    }));
    toast.success(`Kain size ${sz.size} diterapkan`);
  };

  // ─────────────────────────── save / delete ───────────────────────────
  const handleSave = async (statusOverride) => {
    if (!form.hpp_code) return toast.error('Isi kode HPP');
    const bad = (form.cost_lines || []).find(l =>
      l.override && l.source !== 'manual' && !String(l.override_reason || '').trim());
    if (bad) return toast.error(`Baris "${bad.label || 'tanpa nama'}": harga master ditimpa tapi alasannya belum diisi.`, { duration: 7000 });

    setSaving(true);
    const payload = { ...form, ...(statusOverride ? { status: statusOverride } : {}) };
    try {
      const method = editing ? 'PUT' : 'POST';
      const url = editing
        ? `${API}/api/dewi/rnd/hpp-calculator/${editing}`
        : `${API}/api/dewi/rnd/hpp-calculator`;
      const res = await fetch(url, { method, headers: hdr, body: JSON.stringify(payload) });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal menyimpan HPP'), { duration: 8000 }); return; }
      toast.success(editing ? 'HPP diperbarui' : 'HPP disimpan');
      setShowForm(false);
      loadRecords();
    } catch { toast.error('Gagal menyimpan HPP'); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/rnd/hpp-calculator/${delId}`, { method: 'DELETE', headers: hdr });
      toast.success('HPP dihapus');
      setDelId(null);
      loadRecords();
    } catch { toast.error('Gagal menghapus'); }
  };

  const computedById = useMemo(() => {
    const m = {};
    (computed || []).forEach(l => { if (l.line_id) m[l.line_id] = l; });
    return m;
  }, [computed]);

  const linesTotal = useMemo(
    () => (computed || []).reduce((a, l) => a + Number(l.line_cost || 0), 0),
    [computed]);

  const staleIds = useMemo(
    () => new Set(((stale?.stale_lines) || []).map(l => l.line_id)), [stale]);

  const sourceMix = (rec) => {
    const set = new Set((rec.cost_lines || []).map(l => l.source));
    return [...set];
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(records, 10);

  /** HPP yang baris bersumber-masternya sudah tidak sesuai harga master sekarang. */
  const staleRecords = useMemo(
    () => (records || []).filter(r => (r.stale_count || 0) > 0), [records]);

  return (
    <div className="p-6" data-testid="rnd-hpp-module">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Calculator className="w-5 h-5 text-violet-500" /> HPP Calculator
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            Biaya material bersumber <b>per baris</b> — Master, Techpack, dan Manual bisa bercampur
          </p>
        </div>
        <Button onClick={openNew} className="gap-2" data-testid="rnd-hpp-add-btn">
          <Plus className="w-4 h-4" /> Hitung HPP Baru
        </Button>
      </div>

      {/* Peringatan harga master basi — di DAFTAR, bukan hanya di dalam form.
          Sebelumnya `stale-check` hanya jalan saat modal Edit dibuka, jadi HPP
          yang harganya sudah basi tidak kelihatan sampai dibuka satu per satu. */}
      {staleRecords.length > 0 && (
        <GlassCard className="p-4 mb-5 border-amber-400 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10"
          data-testid="rnd-hpp-stale-list-banner">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                {staleRecords.length} HPP memakai harga master yang sudah berubah
              </div>
              <div className="text-xs text-amber-700/80 dark:text-amber-300/80 mt-0.5">
                Angka yang tersimpan <b>tidak diubah otomatis</b> — HPP lama tetap apa adanya.
                Buka HPP-nya lalu <b>Simpan</b> ulang bila ingin memakai harga master terbaru.
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {staleRecords.map(r => (
                  <button key={r.id} type="button" onClick={() => openEdit(r)}
                    className="text-[11px] font-mono px-2 py-1 rounded-md bg-background/70
                      border border-amber-300 dark:border-amber-500/40 text-amber-900 dark:text-amber-100
                      hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors"
                    data-testid={`rnd-hpp-stale-jump-${r.id}`}>
                    {r.hpp_code} · {r.stale_count} baris
                  </button>
                ))}
              </div>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Saved records */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : records.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Calculator className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada kalkulasi HPP.</p>
          <Button variant="outline" className="mt-3" onClick={openNew}>+ Hitung HPP Pertama</Button>
        </GlassCard>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode HPP', 'Style', 'Sumber Biaya', 'Harga Master', 'Direct Cost', 'Overhead', 'HPP/pcs', 'Harga Jual Proposal', 'Margin', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map(rec => (
                <tr key={rec.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                  <td className="px-4 py-3 font-mono text-xs text-foreground/70">{rec.hpp_code}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{rec.style_code || '—'}</div>
                    <div className="text-xs text-foreground/50">{rec.style_name}</div>
                  </td>
                  <td className="px-4 py-3" data-testid={`rnd-hpp-sources-${rec.id}`}>
                    <div className="flex flex-wrap gap-1">
                      {sourceMix(rec).length === 0 ? (
                        <span className="text-xs text-foreground/40">manual</span>
                      ) : sourceMix(rec).map(s => (
                        <span key={s} className={`text-[10px] px-1.5 py-0.5 rounded border ${SOURCE_CLS[s] || ''}`}>
                          {SOURCES.find(x => x.value === s)?.label || s}
                        </span>
                      ))}
                      {rec.cost_lines_legacy && (rec.cost_lines || []).length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border border-foreground/20 text-foreground/50" title="Dokumen lama — dibaca dari use_bom, angkanya tidak diubah">
                          dokumen lama
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3" data-testid={`rnd-hpp-stale-cell-${rec.id}`}>
                    {(rec.stale_count || 0) > 0 ? (
                      <button type="button" onClick={() => openEdit(rec)}
                        title={
                          `Harga master sudah berubah sejak HPP ini dihitung:\n` +
                          (rec.stale_lines || []).map(l =>
                            `· ${l.label || l.material_code || 'baris'}: ${fmt(l.unit_cost_snapshot)} → ${fmt(l.unit_cost_now)} (${l.direction})`
                          ).join('\n') +
                          `\n\nAngka HPP tersimpan TIDAK diubah otomatis. Buka lalu Simpan ulang untuk memakai harga baru.`
                        }
                        className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md
                          bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-200
                          border border-amber-400 dark:border-amber-500/50
                          hover:bg-amber-200 dark:hover:bg-amber-500/30 transition-colors"
                        data-testid={`rnd-hpp-stale-badge-${rec.id}`}>
                        <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                        {rec.stale_count} harga berubah
                      </button>
                    ) : (rec.stale_checked_lines || 0) > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400"
                        title={`${rec.stale_checked_lines} baris bersumber master — semuanya masih sesuai harga master sekarang`}
                        data-testid={`rnd-hpp-stale-ok-${rec.id}`}>
                        <CheckCircle2 className="w-3 h-3 flex-shrink-0" /> sesuai master
                      </span>
                    ) : (
                      <span className="text-[11px] text-foreground/30"
                        title="Tidak ada baris bersumber master untuk dibandingkan (semua manual / dokumen lama)">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground/70">{fmt(rec.direct_cost)}</td>
                  <td className="px-4 py-3 text-foreground/70">{fmt(rec.overhead_value)}</td>
                  <td className="px-4 py-3 font-semibold text-foreground">{fmt(rec.hpp_total)}</td>
                  <td className="px-4 py-3 font-bold text-emerald-600 dark:text-emerald-400">{fmt(rec.selling_price_proposal)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">
                      {rec.margin_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(rec)}
                        className="h-7 w-7 p-0" data-testid={`rnd-hpp-edit-${rec.id}`}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setDelId(rec.id)}
                        className="h-7 w-7 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:hover:bg-red-500/10"
                        data-testid={`rnd-hpp-del-${rec.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* ───────────────────── HPP Form Modal ───────────────────── */}
      <Modal open={showForm} onClose={() => setShowForm(false)}
        title={editing ? 'Edit HPP' : 'Hitung HPP Baru'} size="3xl">
        <div className="space-y-5">
          {/* Baris atas: identitas — lebar penuh */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <Label>Kode HPP <span className="text-red-700 dark:text-red-400">*</span></Label>
                <Input className="mt-1 font-mono" value={form.hpp_code}
                  onChange={e => f('hpp_code', e.target.value)} data-testid="hpp-code-input" />
              </div>
              <div>
                <Label>Style (Opsional)</Label>
                <SmartNativeSelect value={form.style_id} onChange={e => setStyleField(e.target.value)}
                  data-testid="hpp-style-select"
                  className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                  <option value="">-- Pilih Style --</option>
                  {styles.map(s => <option key={s.id} value={s.id}>{`${s.style_code} — ${s.style_name}`}</option>)}
                </SmartNativeSelect>
              </div>
          </div>

          {/* ── F4: Biaya material — sumber PER BARIS (LEBAR PENUH: tabelnya lebar) ── */}
          <GlassCard className="p-4" data-testid="hpp-cost-lines-card">
              <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <PackageOpen className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                    Biaya Material — Sumber per Baris
                  </h3>
                  <p className="text-[11px] text-foreground/50 mt-0.5">
                    Master + Techpack + Manual boleh bercampur. Total = jumlah SEMUA baris.
                  </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button type="button" variant="outline" size="sm" onClick={pullFromTechpack}
                    className="h-7 text-xs gap-1" data-testid="hpp-pull-techpack">
                    <Wand2 className="w-3 h-3" /> Tarik dari Techpack BOM
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={addMasterLine}
                    className="h-7 text-xs gap-1" data-testid="hpp-add-master-line">
                    <Database className="w-3 h-3" /> Baris Master
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={addManualLine}
                    className="h-7 text-xs gap-1" data-testid="hpp-add-manual-line">
                    <PenLine className="w-3 h-3" /> Baris Manual
                  </Button>
                </div>
              </div>

              {prevError && (
                <div className="mb-3 text-[11px] text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-500/10 border border-red-300 dark:border-red-500/40 rounded-md px-2 py-1.5 flex items-start gap-1"
                  data-testid="hpp-preview-error">
                  <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" /> <span>{prevError}</span>
                </div>
              )}

              {stale && stale.stale_count > 0 && (
                <div className="mb-3 rounded-md border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 px-3 py-2"
                  data-testid="hpp-stale-banner">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="text-[11px] text-amber-800 dark:text-amber-200 flex items-start gap-1">
                      <History className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      <span><b>{stale.stale_count} baris</b> memakai harga master yang sudah berubah.
                        Angka tersimpan tidak diubah otomatis — perbarui bila setuju.</span>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={applyMasterPrices}
                      className="h-7 text-xs" data-testid="hpp-refresh-master-prices">
                      Pakai harga master terbaru
                    </Button>
                  </div>
                  <ul className="mt-1.5 text-[11px] text-amber-800/90 dark:text-amber-200/90 space-y-0.5">
                    {stale.stale_lines.slice(0, 4).map(l => (
                      <li key={l.line_id} className="font-mono">
                        {l.label}: {fmt(l.unit_cost_snapshot)} → {fmt(l.unit_cost_now)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {!hybrid ? (
                <div className="text-center py-6">
                  <p className="text-xs text-foreground/50 mb-3">
                    Belum ada baris biaya. Mode lama (kain + aksesoris manual di bawah) masih dipakai —
                    tambahkan baris di atas untuk memakai mode hybrid.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto" data-testid="hpp-cost-lines-table">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-foreground/10 text-foreground/40">
                        <th className="text-left px-1.5 py-1.5 font-medium min-w-[130px]">Baris biaya</th>
                        <th className="text-left px-1.5 py-1.5 font-medium w-[110px]">Sumber</th>
                        <th className="text-left px-1.5 py-1.5 font-medium min-w-[150px]">Referensi</th>
                        <th className="text-right px-1.5 py-1.5 font-medium w-16">Qty</th>
                        <th className="text-left px-1.5 py-1.5 font-medium w-20">Satuan</th>
                        <th className="text-right px-1.5 py-1.5 font-medium w-24">Harga master</th>
                        <th className="text-right px-1.5 py-1.5 font-medium w-28">Harga dipakai</th>
                        <th className="text-right px-1.5 py-1.5 font-medium w-24">Biaya</th>
                        <th className="w-7" />
                      </tr>
                    </thead>
                    <tbody>
                      {(form.cost_lines || []).map((l, i) => {
                        const c = computedById[l.line_id] || {};
                        const isManual = l.source === 'manual';
                        const unlinked = !isManual && c.master_linked === false;
                        const isStale = staleIds.has(l.line_id);
                        return (
                          <tr key={l.line_id} className={`border-b border-foreground/5 align-top ${unlinked ? 'bg-red-50 dark:bg-red-500/[0.07]' : ''}`}
                            data-testid={`hpp-line-${i}`}>
                            <td className="px-1.5 py-1.5">
                              <Input value={l.label || ''} onChange={e => setLine(i, { label: e.target.value })}
                                placeholder="Nama baris" className="h-7 text-xs"
                                data-testid={`hpp-line-label-${i}`} />
                            </td>
                            <td className="px-1.5 py-1.5">
                              <SmartNativeSelect value={l.source} searchable={false}
                                onChange={e => setLine(i, { source: e.target.value,
                                  ...(e.target.value === 'manual' ? { material_id: '', override: false, override_reason: '' } : {}) })}
                                data-testid={`hpp-line-source-${i}`} className="w-full text-xs">
                                {SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                              </SmartNativeSelect>
                            </td>
                            <td className="px-1.5 py-1.5">
                              {isManual ? (
                                <span className="text-foreground/30">— custom field —</span>
                              ) : (
                                <>
                                  <SmartNativeSelect value={l.material_id || ''}
                                    onChange={e => {
                                      const opt = matOpts.find(m => m.material_id === e.target.value);
                                      setLine(i, { material_id: e.target.value,
                                        material_code: opt?.code || '',
                                        material_name: opt?.name || '',
                                        label: l.label || opt?.name || '',
                                        unit: l.unit || opt?.base_unit || '' });
                                    }}
                                    data-testid={`hpp-line-material-${i}`} className="w-full text-xs">
                                    <option value="">⚠ Pilih master material…</option>
                                    {matOpts.map(m => <option key={m.material_id} value={m.material_id}>{`${m.code} — ${m.name} (${m.base_unit})`}</option>)}
                                  </SmartNativeSelect>
                                  {unlinked && (
                                    <div className="mt-1 text-[10px] text-red-700 dark:text-red-300 flex items-start gap-1"
                                      data-testid={`hpp-line-unlinked-${i}`}>
                                      <AlertTriangle className="w-2.5 h-2.5 mt-0.5 flex-shrink-0" />
                                      <span>Tanpa master: harga &amp; konversi satuan tidak dihitung.</span>
                                    </div>
                                  )}
                                </>
                              )}
                            </td>
                            <td className="px-1.5 py-1.5">
                              <Input type="number" step="0.01" value={l.qty ?? 1}
                                onChange={e => setLine(i, { qty: Number(e.target.value) })}
                                className="h-7 text-xs text-right" data-testid={`hpp-line-qty-${i}`} />
                            </td>
                            <td className="px-1.5 py-1.5">
                              <Input value={l.unit || ''} onChange={e => setLine(i, { unit: e.target.value })}
                                placeholder="pcs" className="h-7 text-xs" data-testid={`hpp-line-unit-${i}`} />
                            </td>
                            <td className="px-1.5 py-1.5 text-right">
                              {isManual ? <span className="text-foreground/30">—</span> : (
                                <span className={isStale ? 'text-amber-700 dark:text-amber-300 font-medium' : 'text-foreground/60'}>
                                  {fmt(c.unit_cost_master)}
                                  {isStale && <AlertTriangle className="inline w-2.5 h-2.5 ml-0.5 -mt-0.5" />}
                                </span>
                              )}
                            </td>
                            <td className="px-1.5 py-1.5">
                              {isManual || l.override ? (
                                <Input type="number" value={l.unit_cost_used ?? 0}
                                  onChange={e => setLine(i, { unit_cost_used: Number(e.target.value) })}
                                  className="h-7 text-xs text-right" data-testid={`hpp-line-price-${i}`} />
                              ) : (
                                <div className="text-right text-foreground font-medium py-1">{fmt(c.unit_cost_used)}</div>
                              )}
                              {!isManual && (
                                <label className="mt-1 flex items-center gap-1 text-[10px] text-foreground/60 cursor-pointer">
                                  <input type="checkbox" checked={!!l.override}
                                    onChange={e => setLine(i, { override: e.target.checked,
                                      unit_cost_used: e.target.checked ? (c.unit_cost_master || 0) : 0,
                                      ...(e.target.checked ? {} : { override_reason: '' }) })}
                                    data-testid={`hpp-line-override-${i}`} />
                                  timpa harga
                                </label>
                              )}
                              {!isManual && l.override && (
                                <Input value={l.override_reason || ''}
                                  onChange={e => setLine(i, { override_reason: e.target.value })}
                                  placeholder="Alasan (WAJIB)"
                                  className={`h-7 text-[10px] mt-1 ${String(l.override_reason || '').trim() ? '' : 'border-red-400 dark:border-red-500'}`}
                                  data-testid={`hpp-line-reason-${i}`} />
                              )}
                            </td>
                            <td className="px-1.5 py-1.5 text-right font-semibold text-foreground"
                              data-testid={`hpp-line-cost-${i}`}>{fmt(c.line_cost)}</td>
                            <td className="px-0 py-1.5">
                              <Button variant="ghost" size="sm" onClick={() => removeLine(i)}
                                className="h-7 w-7 p-0 text-red-700 dark:text-red-500"
                                data-testid={`hpp-line-del-${i}`}>
                                <X className="w-3 h-3" />
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                      <tr>
                        <td colSpan="7" className="px-1.5 py-2 text-right text-foreground/60">
                          Total biaya material ({(form.cost_lines || []).length} baris)
                        </td>
                        <td className="px-1.5 py-2 text-right font-bold text-violet-600 dark:text-violet-400"
                          data-testid="hpp-cost-lines-total">{fmt(linesTotal)}</td>
                        <td />
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
          </GlassCard>

          {/* Sisanya: kiri input, kanan ringkasan yang menempel */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
            {/* Mode lama — hanya ditampilkan bila belum ada cost_lines */}
            {!hybrid && (
              <>
                <GlassCard className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <PackageOpen className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Bahan Kain (mode lama)
                      {form.fabric_source === 'techpack' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                          dari Techpack{form.fabric_size ? ` · ${form.fabric_size}` : ''}
                        </span>
                      )}
                    </h3>
                    <Button type="button" variant="outline" size="sm" onClick={loadFabricEstimate}
                      disabled={fabricEstLoading} className="h-7 text-xs gap-1" data-testid="hpp-fabric-from-techpack">
                      <Wand2 className="w-3 h-3" /> {fabricEstLoading ? 'Memuat...' : 'Hitung dari Techpack'}
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs">Pemakaian kain/pcs (meter)</Label>
                      <Input className="mt-1" type="number" step="0.01" value={form.fabric_usage_per_pcs}
                        onChange={e => { f('fabric_usage_per_pcs', Number(e.target.value)); f('fabric_source', 'manual'); }} />
                    </div>
                    <div>
                      <Label className="text-xs">Harga kain/meter (Rp)</Label>
                      <Input className="mt-1" type="number" value={form.fabric_price_per_meter}
                        onChange={e => { f('fabric_price_per_meter', Number(e.target.value)); f('fabric_source', 'manual'); }} />
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-foreground/50">
                    Biaya kain = {form.fabric_usage_per_pcs} m × Rp {Number(form.fabric_price_per_meter).toLocaleString('id-ID')} = <strong className="text-foreground">{fmt(form.fabric_usage_per_pcs * form.fabric_price_per_meter)}</strong>
                  </div>

                  {fabricEst && fabricEst.sizes?.length > 0 && (
                    <div className="mt-3 border-t border-foreground/10 pt-3" data-testid="hpp-fabric-estimate-panel">
                      <div className="text-xs font-medium text-foreground/60 mb-2">
                        Estimasi techpack <b>{fabricEst.style_code}</b> — klik size untuk pakai:
                        {fabricEst.has_unresolved_price && <span className="text-amber-600 ml-1">(sebagian harga Rp0 — set di Riset Material)</span>}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {fabricEst.sizes.map(sz => (
                          <button key={sz.size} type="button" onClick={() => applyFabricSize(sz)}
                            className={`text-xs px-2 py-1 rounded-md border transition-colors ${form.fabric_size === sz.size && form.fabric_source === 'techpack'
                              ? 'bg-violet-100 dark:bg-violet-500/20 border-violet-400 text-violet-700 dark:text-violet-300'
                              : 'bg-background border-border text-foreground/70 hover:border-violet-400'}`}>
                            <b>{sz.size}</b>: {sz.meters_per_pcs}m × Rp{Number(sz.weighted_price_per_meter).toLocaleString('id-ID')} = {fmt(sz.fabric_cost_per_pcs)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </GlassCard>

                <GlassCard className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <PenLine className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Aksesoris (mode lama)
                    </h3>
                    <Button type="button" variant="outline" size="sm" onClick={addAcc} className="h-7 text-xs gap-1">
                      <Plus className="w-3 h-3" /> Tambah
                    </Button>
                  </div>
                  {form.accessories_cost.map((acc, i) => (
                    <div key={i} className="grid grid-cols-[1fr_110px_70px_32px] gap-2 mb-2">
                      <Input value={acc.name} onChange={e => setAcc(i, 'name', e.target.value)}
                        placeholder="Nama item" className="text-sm" />
                      <Input type="number" value={acc.unit_cost}
                        onChange={e => setAcc(i, 'unit_cost', e.target.value)}
                        placeholder="Harga/unit" className="text-sm" />
                      <Input type="number" value={acc.qty} min="1"
                        onChange={e => setAcc(i, 'qty', e.target.value)}
                        placeholder="Qty" className="text-sm" />
                      <Button variant="ghost" size="sm" onClick={() => removeAcc(i)}
                        className="h-9 w-8 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:hover:bg-red-500/10">
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                </GlassCard>
              </>
            )}

            {/* Biaya Proses */}
            <GlassCard className="p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <Scissors className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Biaya Proses /pcs
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Ongkos CMT (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.cmt_cost_per_pcs}
                    onChange={e => setForm(p => ({ ...p, cmt_cost_per_pcs: Number(e.target.value), cmt_cost_source: 'manual', cmt_cost_ref: '' }))}
                    data-testid="hpp-cmt-input" />
                  {cmtOpts.length > 0 && (
                    <SmartNativeSelect value={form.cmt_cost_ref || ''}
                      onChange={e => {
                        const opt = cmtOpts.find(o => o.catalog_id === e.target.value);
                        if (!opt) return;
                        setForm(p => ({ ...p, cmt_cost_per_pcs: opt.cmt_price,
                          cmt_cost_source: 'catalog', cmt_cost_ref: opt.catalog_id }));
                        toast.success(`Ongkos CMT dari master katalog ${opt.code}: ${formatRupiah(opt.cmt_price)}`);
                      }}
                      data-testid="hpp-cmt-catalog" className="w-full mt-1 text-xs">
                      <option value="">Ambil dari master katalog buyer…</option>
                      {cmtOpts.map(o => (
                        <option key={o.catalog_id} value={o.catalog_id}>{`${o.code} — ${o.name} · ${formatRupiah(o.cmt_price)}`}</option>
                      ))}
                    </SmartNativeSelect>
                  )}
                  {form.cmt_cost_source === 'catalog' && (
                    <div className="mt-1 text-[10px] text-sky-700 dark:text-sky-300 flex items-center gap-1">
                      <CheckCircle2 className="w-2.5 h-2.5" /> dari master katalog buyer
                    </div>
                  )}
                </div>
                <div>
                  <Label className="text-xs">Biaya Cutting (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.cutting_cost_per_pcs}
                    onChange={e => f('cutting_cost_per_pcs', Number(e.target.value))} />
                </div>
                <div>
                  <Label className="text-xs">Packaging/pcs (Rp)</Label>
                  <Input className="mt-1" type="number" value={form.packaging_cost_per_pcs}
                    onChange={e => f('packaging_cost_per_pcs', Number(e.target.value))} />
                </div>
              </div>
            </GlassCard>

            {/* Overhead & Margin */}
            <GlassCard className="p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <Settings2 className="w-4 h-4 text-violet-600 dark:text-violet-400" /> Overhead & Target Margin
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Overhead (%)</Label>
                  <Input className="mt-1" type="number" step="0.5" value={form.overhead_pct}
                    onChange={e => f('overhead_pct', Number(e.target.value))} />
                  <div className="text-xs text-foreground/40 mt-1">dari total direct cost</div>
                </div>
                <div>
                  <Label className="text-xs">Target Margin (%)</Label>
                  <Input className="mt-1" type="number" step="0.5" value={form.margin_pct}
                    onChange={e => f('margin_pct', Number(e.target.value))} />
                  <div className="text-xs text-foreground/40 mt-1">dari harga jual</div>
                </div>
              </div>
            </GlassCard>

            <div>
              <Label>Catatan</Label>
              <textarea value={form.notes} onChange={e => f('notes', e.target.value)}
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-16 resize-none" />
            </div>
          </div>

          {/* Right: Live Preview */}
          <div className="lg:col-span-2">
            <div className="sticky top-0">
              <GlassCard className="p-5 border-violet-300 dark:border-violet-500/20 bg-gradient-to-br from-violet-500/5 to-purple-500/5">
                <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-violet-500" />
                  Hasil Kalkulasi
                  {prevLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-foreground/40" />}
                </h3>

                <div className="space-y-2.5 text-sm">
                  {hybrid ? (
                    <div className="flex items-center justify-between">
                      <span className="text-foreground/60">Biaya Material ({(form.cost_lines || []).length} baris)</span>
                      <span className="font-mono text-foreground" data-testid="hpp-preview-material">{fmt(preview.material_cost)}</span>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-foreground/60">Biaya Kain</span>
                        <span className="font-mono text-foreground">{fmt(preview.fabric_cost)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-foreground/60">Biaya Aksesoris</span>
                        <span className="font-mono text-foreground">{fmt(preview.accessories_total)}</span>
                      </div>
                    </>
                  )}
                  {[
                    { label: 'Ongkos CMT',    val: preview.cmt_cost },
                    { label: 'Biaya Cutting', val: preview.cutting_cost },
                    { label: 'Packaging',     val: preview.packaging_cost },
                  ].map(row => (
                    <div key={row.label} className="flex items-center justify-between">
                      <span className="text-foreground/60">{row.label}</span>
                      <span className="font-mono text-foreground">{fmt(row.val)}</span>
                    </div>
                  ))}

                  <div className="border-t border-foreground/10 pt-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-foreground/70 font-medium">Direct Cost</span>
                      <span className="font-mono font-semibold text-foreground">{fmt(preview.direct_cost)}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-foreground/60">Overhead ({preview.overhead_pct}%)</span>
                      <span className="font-mono text-foreground/70">{fmt(preview.overhead_value)}</span>
                    </div>
                  </div>

                  <div className="border-t border-violet-400 dark:border-violet-500/30 pt-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">HPP / pcs</span>
                      <span className="font-mono font-bold text-foreground text-base" data-testid="hpp-preview-total">{fmt(preview.hpp_total)}</span>
                    </div>
                  </div>

                  <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-500/25 rounded-xl p-3 mt-3">
                    <div className="text-xs text-emerald-700/80 dark:text-emerald-400/70 mb-1">Harga Jual Proposal</div>
                    <div className="text-xl font-bold text-emerald-700 dark:text-emerald-400">{fmt(preview.selling_price_proposal)}</div>
                    <div className="text-xs text-emerald-700/70 dark:text-emerald-400/60 mt-1">Margin {preview.margin_pct}% dari harga jual</div>
                  </div>

                  {hybrid && (
                    <div className="text-[11px] text-foreground/50 pt-1">
                      Sumber baris:{' '}
                      {[...new Set((form.cost_lines || []).map(l => l.source))].map(s => (
                        <span key={s} className={`ml-1 px-1.5 py-0.5 rounded border ${SOURCE_CLS[s] || ''}`}>
                          {SOURCES.find(x => x.value === s)?.label || s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </GlassCard>
            </div>
          </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button variant="outline" disabled={saving} onClick={() => handleSave('draft')} className="gap-2">
            <Save className="w-4 h-4" /> Simpan Draft
          </Button>
          <Button onClick={() => handleSave('approved')} disabled={saving} className="gap-2" data-testid="rnd-hpp-save-btn">
            <CheckCircle2 className="w-4 h-4" /> {saving ? 'Menyimpan…' : 'Simpan & Setujui'}
          </Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus HPP?"
          message="Data kalkulasi HPP akan dihapus permanen."
        />
      )}
    </div>
  );
}
