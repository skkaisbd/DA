import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  AlertTriangle, Search, RefreshCw, Save, Wand2, CheckCircle2, Info, Eraser,
  ShoppingCart, Layers, ChevronDown, ChevronRight,
} from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

const STATUS_META = {
  critical:     { label: 'Kritis',        cls: 'bg-red-400/10 text-red-500 border-red-300/25' },
  low:          { label: 'Perlu pesan',   cls: 'bg-amber-400/10 text-amber-500 border-amber-300/25' },
  ok:           { label: 'Aman',          cls: 'bg-emerald-400/10 text-emerald-600 border-emerald-300/25' },
  no_threshold: { label: 'Belum diambang', cls: 'bg-muted/30 text-muted-foreground border-border' },
};

const num = (v) => (v === '' || v == null ? 0 : Number(v) || 0);
const fmt = (v) => Number(v || 0).toLocaleString('id-ID', { maximumFractionDigits: 2 });

// Empat DASAR pengisian massal. Semuanya punya pijakan nyata; tidak ada yang menebak.
const MODES = [
  {
    key: 'purchase_lot',
    label: 'Dari lot pembelian',
    hint: 'rata-rata satu kali beli dari penerimaan nyata 12 bulan terakhir \u00d7 pengali',
    param: { key: 'lot_multiplier', label: 'Pengali lot', def: '0.5', step: '0.1', suffix: '\u00d7' },
  },
  {
    key: 'usage_30d',
    label: 'Dari pemakaian 30 hari',
    hint: 'pakai per hari \u00d7 masa tunggu pembelian \u2014 hanya untuk barang yang pernah dipakai',
    param: null,
  },
  {
    key: 'percent_onhand',
    label: 'Persen stok sekarang',
    hint: 'stok sekarang dianggap normal; ambang = sebagian dari stok itu',
    param: { key: 'percent', label: 'Persen', def: '20', step: '1', suffix: '%' },
  },
  {
    key: 'fixed',
    label: 'Angka yang saya tentukan',
    hint: 'satu angka untuk seluruh seleksi \u2014 cocok per jenis / per kategori',
    param: null,
  },
];

/**
 * Ambang Stok \u2014 layar tempat pemilik MENGISI ambang minimum & titik pesan ulang.
 *
 * Sesi #29 (W3) membuat layar ini karena alert stok tidak pernah berbunyi: 333
 * dari 333 material tidak punya ambang. Sesi #33 menutup lubang yang tersisa:
 * usulan lama HANYA lahir dari pemakaian 30 hari, dan terukur di data nyata
 * hanya **5 dari 335 material** yang punya pemakaian \u21d2 tombol "Pakai semua
 * usulan" secara struktural cuma bisa mengisi 5 baris, 330 sisanya harus
 * diketik satu per satu. Sekarang ada EMPAT dasar pengisian massal, semuanya
 * bisa dipratinjau lebih dulu, bisa dikosongkan lagi, dan DASARNYA disimpan
 * bersama siapa & kapan supaya tidak ada angka anonim.
 */
export default function StockThresholdsModule({ token, onNavigate }) {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [edits, setEdits] = useState({});           // material_id -> {min_stock_qty, reorder_point}
  const [filterType, setFilterType] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(() => new Set());
  const [bulkOpen, setBulkOpen] = useState(true);
  const [mode, setMode] = useState('purchase_lot');
  const [params, setParams] = useState({ lot_multiplier: '0.5', percent: '20',
    min_stock_qty: '', reorder_point: '' });
  const [preview, setPreview] = useState(null);
  const [busyBulk, setBusyBulk] = useState(false);

  const headers = useMemo(() => ({
    Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
    'Content-Type': 'application/json',
  }), [token]);

  const goto = useCallback((moduleId) => {
    if (onNavigate) { onNavigate(moduleId); return; }
    if (window.location.hash === `#${moduleId}`) window.location.hash = '';
    window.location.hash = `#${moduleId}`;
  }, [onNavigate]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ status: filterStatus, limit: 1000 });
      if (filterType) p.set('type', filterType);
      if (search.trim()) p.set('search', search.trim());
      const r = await fetch(`/api/rahaza/stock-thresholds?${p}`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setRows(d.items || []);
      setSummary(d.summary || null);
      setEdits({});
      setSelected(new Set());
    } catch (e) {
      toast.error(`Gagal memuat ambang stok: ${e.message}`);
    } finally { setLoading(false); }
  }, [headers, filterType, filterStatus, search]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const setEdit = (id, field, value) => setEdits(prev => ({
    ...prev, [id]: { ...(prev[id] || {}), [field]: value },
  }));

  const valueOf = (r, field) => {
    const e = edits[r.material_id];
    if (e && e[field] !== undefined) return e[field];
    return r[field] ? String(r[field]) : '';
  };

  const applySuggestion = (r) => {
    const s = r.suggestion || {};
    if (s.no_usage_data) {
      toast.error(`${r.code} belum ada pemakaian 30 hari terakhir — pakai dasar "Dari lot pembelian" pada panel Isi Massal.`);
      return;
    }
    setEdits(prev => ({
      ...prev,
      [r.material_id]: {
        min_stock_qty: String(s.suggested_min_stock),
        reorder_point: String(s.suggested_reorder_point),
      },
    }));
  };

  const applyAllSuggestions = () => {
    const next = { ...edits };
    let n = 0;
    let skipped = 0;
    rows.forEach(r => {
      const s = r.suggestion || {};
      if (s.no_usage_data || !s.suggested_min_stock) { skipped += 1; return; }
      next[r.material_id] = {
        min_stock_qty: String(s.suggested_min_stock),
        reorder_point: String(s.suggested_reorder_point),
      };
      n += 1;
    });
    setEdits(next);
    if (n) {
      toast.success(`${n} usulan disiapkan — klik Simpan untuk menerapkan.`
        + (skipped ? ` ${skipped} barang tidak punya pemakaian 30 hari; pakai panel Isi Ambang Massal (dasar "Dari lot pembelian") untuk barang-barang itu.` : ''));
    } else {
      toast.error(`Tidak ada barang dengan pemakaian nyata di daftar ini (${skipped} barang dilewati) — `
        + 'pakai panel Isi Ambang Massal dengan dasar "Dari lot pembelian" atau "Persen stok sekarang".');
    }
  };

  const dirtyItems = useMemo(() => Object.entries(edits).map(([material_id, v]) => ({
    material_id,
    min_stock_qty: num(v.min_stock_qty),
    reorder_point: num(v.reorder_point),
  })).filter(it => {
    const r = rows.find(x => x.material_id === it.material_id);
    if (!r) return false;
    return num(r.min_stock_qty) !== it.min_stock_qty || num(r.reorder_point) !== it.reorder_point;
  }), [edits, rows]);

  const save = async () => {
    if (!dirtyItems.length) return;
    setSaving(true);
    try {
      const r = await fetch('/api/rahaza/stock-thresholds/bulk', {
        method: 'POST', headers, body: JSON.stringify({ items: dirtyItems }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`${d.updated} ambang stok disimpan — alert langsung aktif.`);
      fetchRows();
    } catch (e) {
      toast.error(`Gagal menyimpan: ${e.message}`);
    } finally { setSaving(false); }
  };

  // ── ISI MASSAL ────────────────────────────────────────────────────────────
  const scope = useMemo(() => {
    if (selected.size) return { material_ids: Array.from(selected) };
    return {
      type: filterType || undefined,
      search: search.trim() || undefined,
      status: filterStatus !== 'all' ? filterStatus : undefined,
    };
  }, [selected, filterType, search, filterStatus]);

  const scopeLabel = selected.size
    ? `${selected.size} baris tercentang`
    : `semua hasil filter (${rows.length} baris)`;

  const activeMode = MODES.find(m => m.key === mode) || MODES[0];

  const bulkBody = useCallback((dry) => {
    const p = {};
    if (mode === 'percent_onhand') p.percent = num(params.percent);
    if (mode === 'purchase_lot') p.lot_multiplier = num(params.lot_multiplier);
    if (mode === 'fixed') {
      p.min_stock_qty = num(params.min_stock_qty);
      p.reorder_point = num(params.reorder_point);
    }
    return { mode, dry_run: dry, params: p, scope };
  }, [mode, params, scope]);

  const runBulk = async (dry) => {
    if (mode === 'fixed' && num(params.min_stock_qty) <= 0 && num(params.reorder_point) <= 0) {
      toast.error('Isi minimal salah satu: minimum stok atau titik pesan ulang.');
      return;
    }
    setBusyBulk(true);
    try {
      const r = await fetch('/api/rahaza/stock-thresholds/bulk-fill', {
        method: 'POST', headers, body: JSON.stringify(bulkBody(dry)),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setPreview(d);
      if (dry) {
        toast.success(d.eligible
          ? `Pratinjau: ${d.eligible} barang akan diisi (${d.skipped_count} dilewati). Belum ada yang ditulis.`
          : `Tidak ada barang yang bisa diisi dengan dasar ini — ${d.skipped_count} dilewati beserta alasannya.`);
      } else {
        toast.success(`${d.applied} ambang terisi dengan dasar "${d.basis_label}" — alert langsung aktif.`);
        fetchRows();
      }
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    } finally { setBusyBulk(false); }
  };

  const clearSelected = async () => {
    if (!selected.size) {
      toast.error('Centang dulu baris yang ambangnya mau dikosongkan.');
      return;
    }
    if (!window.confirm(`Kosongkan ambang ${selected.size} barang? Alert untuk barang itu akan berhenti berbunyi.`)) return;
    setBusyBulk(true);
    try {
      const r = await fetch('/api/rahaza/stock-thresholds/bulk-clear', {
        method: 'POST', headers, body: JSON.stringify({ material_ids: Array.from(selected) }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      toast.success(`${d.cleared} ambang dikosongkan.`);
      setPreview(null);
      fetchRows();
    } catch (e) {
      toast.error(`Gagal mengosongkan: ${e.message}`);
    } finally { setBusyBulk(false); }
  };

  const toggle = (id) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleAll = () => setSelected(prev =>
    prev.size === rows.length ? new Set() : new Set(rows.map(r => r.material_id)));

  return (
    <div className="space-y-4" data-testid="stock-thresholds-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-bold text-foreground">Ambang Stok — Minimum &amp; Titik Pesan Ulang</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Alert stok &amp; Daftar Belanja Mingguan hanya bekerja untuk barang yang ambangnya sudah
            diisi. Setiap ambang menyimpan DASARNYA, siapa yang mengisi, dan kapan.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={fetchRows} disabled={loading} data-testid="threshold-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
          </Button>
          <Button variant="outline" onClick={() => goto('wh-shopping-list')}
            data-testid="threshold-goto-shopping">
            <ShoppingCart className="w-4 h-4 mr-1.5" /> Daftar Belanja Mingguan
          </Button>
          <Button variant="outline" onClick={applyAllSuggestions} data-testid="threshold-apply-all">
            <Wand2 className="w-4 h-4 mr-1.5" /> Pakai semua usulan
          </Button>
          <Button onClick={save} disabled={saving || !dirtyItems.length} data-testid="threshold-save">
            <Save className="w-4 h-4 mr-1.5" /> {saving ? 'Menyimpan…' : `Simpan${dirtyItems.length ? ` (${dirtyItems.length})` : ''}`}
          </Button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="threshold-summary">
          {[
            { k: 'with_threshold', label: 'Sudah punya ambang', v: summary.with_threshold, tone: 'text-emerald-600 dark:text-emerald-300' },
            { k: 'missing_threshold', label: 'Belum diisi', v: summary.missing_threshold, tone: 'text-amber-600 dark:text-amber-300' },
            { k: 'critical', label: 'Stok kritis', v: summary.critical, tone: 'text-red-500' },
            { k: 'low', label: 'Perlu pesan ulang', v: summary.low, tone: 'text-amber-500' },
          ].map(c => (
            <GlassCard key={c.k} className="p-3">
              <div className={`text-2xl font-bold ${c.tone}`} data-testid={`threshold-stat-${c.k}`}>{c.v}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{c.label} · dari {summary.total_materials} material</div>
            </GlassCard>
          ))}
        </div>
      )}

      {summary && summary.with_threshold === 0 && (
        <div className="flex items-start gap-2 bg-amber-400/10 border border-amber-300/25 rounded-lg px-4 py-3" data-testid="threshold-empty-warning">
          <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-600 dark:text-amber-300">
            <strong>Belum ada satu pun ambang stok yang diisi</strong> — itulah sebabnya menu
            Alert &amp; Reorder selalu kosong dan Daftar Belanja Mingguan kosong. Pakai panel
            <em> Isi Ambang Massal</em> di bawah: mulai dari <em>lot pembelian</em> (paling banyak
            barang yang tercakup), lalu sesuaikan yang perlu.
          </div>
        </div>
      )}

      {/* ── PANEL ISI MASSAL ───────────────────────────────────────────────── */}
      <GlassCard className="p-0 overflow-hidden" data-testid="threshold-bulk-panel">
        <button onClick={() => setBulkOpen(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--glass-bg-hover)] transition-colors"
          data-testid="threshold-bulk-toggle">
          <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Layers className="w-4 h-4 text-primary" /> Isi Ambang Massal
            <Badge variant="secondary" className="text-[10px]">{scopeLabel}</Badge>
          </span>
          {bulkOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground" />
            : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
        </button>

        {bulkOpen && (
          <div className="px-4 pb-4 space-y-3 border-t border-[var(--glass-border)] pt-3">
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
              {MODES.map(m => (
                <button key={m.key} onClick={() => { setMode(m.key); setPreview(null); }}
                  className={`text-left rounded-lg border px-3 py-2 transition-colors ${
                    mode === m.key
                      ? 'border-primary bg-primary/10'
                      : 'border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]'}`}
                  data-testid={`threshold-mode-${m.key}`}>
                  <div className={`text-sm font-medium ${mode === m.key ? 'text-primary' : 'text-foreground'}`}>{m.label}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{m.hint}</div>
                </button>
              ))}
            </div>

            <div className="flex items-end gap-3 flex-wrap">
              {activeMode.param && (
                <div>
                  <label className="text-xs text-muted-foreground">{activeMode.param.label}</label>
                  <div className="flex items-center gap-1 mt-1">
                    <GlassInput type="number" step={activeMode.param.step} min="0"
                      value={params[activeMode.param.key]}
                      onChange={e => setParams(p => ({ ...p, [activeMode.param.key]: e.target.value }))}
                      className="h-9 w-24 text-sm" data-testid={`threshold-param-${activeMode.param.key}`} />
                    <span className="text-xs text-muted-foreground">{activeMode.param.suffix}</span>
                  </div>
                </div>
              )}
              {mode === 'fixed' && (
                <>
                  <div>
                    <label className="text-xs text-muted-foreground">Minimum stok</label>
                    <GlassInput type="number" step="0.01" min="0" value={params.min_stock_qty}
                      onChange={e => setParams(p => ({ ...p, min_stock_qty: e.target.value }))}
                      placeholder="0" className="h-9 w-28 text-sm mt-1"
                      data-testid="threshold-param-min" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Titik pesan ulang</label>
                    <GlassInput type="number" step="0.01" min="0" value={params.reorder_point}
                      onChange={e => setParams(p => ({ ...p, reorder_point: e.target.value }))}
                      placeholder="0" className="h-9 w-28 text-sm mt-1"
                      data-testid="threshold-param-rp" />
                  </div>
                </>
              )}
              <Button variant="outline" onClick={() => runBulk(true)} disabled={busyBulk}
                data-testid="threshold-bulk-preview">
                <Wand2 className="w-4 h-4 mr-1.5" /> Pratinjau
              </Button>
              <Button onClick={() => runBulk(false)} disabled={busyBulk}
                data-testid="threshold-bulk-apply">
                Terapkan ke {scopeLabel}
              </Button>
              <Button variant="ghost" onClick={clearSelected} disabled={busyBulk || !selected.size}
                data-testid="threshold-bulk-clear">
                <Eraser className="w-4 h-4 mr-1.5" /> Kosongkan terpilih
              </Button>
            </div>

            <div className="text-xs text-muted-foreground">
              Centang baris untuk membatasi ke barang tertentu; tanpa centang, penerapan mengikuti
              filter di bawah. Pratinjau tidak menulis apa pun.
            </div>

            {preview && (
              <div className="rounded-lg border border-[var(--glass-border)] overflow-hidden"
                data-testid="threshold-preview">
                <div className="px-3 py-2 bg-[var(--glass-bg)] text-xs flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="text-foreground font-semibold">
                    {preview.dry_run ? 'Pratinjau' : 'Diterapkan'} · dasar {preview.basis_label}
                  </span>
                  <span className="text-muted-foreground">diperiksa {preview.scanned} barang</span>
                  <span className="text-emerald-600 dark:text-emerald-300"
                    data-testid="threshold-preview-eligible">
                    {preview.dry_run ? `${preview.eligible} akan diisi` : `${preview.applied} terisi`}
                  </span>
                  {preview.skipped_count > 0 && (
                    <span className="text-amber-600 dark:text-amber-300"
                      data-testid="threshold-preview-skipped">
                      {preview.skipped_count} dilewati
                    </span>
                  )}
                </div>
                {!!(preview.preview || []).length && (
                  <div className="overflow-x-auto max-h-56">
                    <table className="w-full text-xs">
                      <thead className="bg-[var(--glass-bg)] sticky top-0">
                        <tr className="text-left text-muted-foreground">
                          <th className="px-3 py-2">Kode</th>
                          <th className="px-3 py-2 text-right">Stok</th>
                          <th className="px-3 py-2 text-right">Min sekarang</th>
                          <th className="px-3 py-2 text-right">Min baru</th>
                          <th className="px-3 py-2 text-right">Pesan ulang baru</th>
                          <th className="px-3 py-2">Dasar angkanya</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.preview.slice(0, 30).map(p => (
                          <tr key={p.material_id} className="border-t border-[var(--glass-border)]"
                            data-testid={`threshold-preview-row-${p.code}`}>
                            <td className="px-3 py-1.5 font-mono text-foreground">{p.code}</td>
                            <td className="px-3 py-1.5 text-right font-mono text-foreground">{fmt(p.onhand)} {p.unit}</td>
                            <td className="px-3 py-1.5 text-right font-mono text-muted-foreground">{fmt(p.current_min)}</td>
                            <td className="px-3 py-1.5 text-right font-mono font-semibold text-foreground">{fmt(p.min_stock_qty)}</td>
                            <td className="px-3 py-1.5 text-right font-mono text-foreground">{fmt(p.reorder_point)}</td>
                            <td className="px-3 py-1.5 text-muted-foreground">{p.basis_note}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {preview.preview.length > 30 && (
                      <div className="px-3 py-1.5 text-[10px] text-muted-foreground">
                        …dan {preview.preview.length - 30} baris lain (semua akan ikut diterapkan)
                      </div>
                    )}
                  </div>
                )}
                {!!(preview.skipped || []).length && (
                  <div className="px-3 py-2 text-[11px] text-muted-foreground border-t border-[var(--glass-border)]">
                    <strong className="text-amber-600 dark:text-amber-300">Dilewati:</strong>{' '}
                    {preview.skipped.slice(0, 4).map(s => `${s.code} (${s.reason})`).join(' · ')}
                    {preview.skipped.length > 4 && ` · dan ${preview.skipped.length - 4} lainnya`}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <GlassInput value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari kode / nama material…" className="pl-8 h-9 text-sm"
            data-testid="threshold-search" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="threshold-filter-type">
          <option value="">Semua jenis</option>
          <option value="bahan">Bahan</option>
          <option value="aksesoris">Aksesoris</option>
          <option value="fg">Produk Jadi</option>
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
          data-testid="threshold-filter-status">
          <option value="all">Semua status</option>
          <option value="missing">Belum ada ambang</option>
          <option value="set">Sudah ada ambang</option>
          <option value="low">Sedang rendah / kritis</option>
        </select>
        {!!rows.length && (
          <Button variant="outline" size="sm" onClick={toggleAll} data-testid="threshold-select-all">
            {selected.size === rows.length ? 'Batalkan semua' : `Centang semua (${rows.length})`}
          </Button>
        )}
      </div>

      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="threshold-table">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-3 py-3 w-8"></th>
                <th className="px-3 py-3">Kode</th>
                <th className="px-3 py-3">Nama</th>
                <th className="px-3 py-3 text-right">Stok</th>
                <th className="px-3 py-3 text-right">Min Stok</th>
                <th className="px-3 py-3 text-right">Titik Pesan Ulang</th>
                <th className="px-3 py-3">Dasar</th>
                <th className="px-3 py-3">Usulan (pemakaian nyata)</th>
                <th className="px-3 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} className="text-center py-12 text-muted-foreground">Memuat…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={9} className="text-center py-12 text-muted-foreground">Tidak ada material pada filter ini.</td></tr>
              ) : rows.map(r => {
                const s = r.suggestion || {};
                const meta = STATUS_META[r.status] || STATUS_META.no_threshold;
                const dirty = !!edits[r.material_id];
                const isSel = selected.has(r.material_id);
                return (
                  <tr key={r.material_id}
                    className={`border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] ${dirty ? 'bg-primary/5' : ''} ${isSel ? 'bg-primary/[0.07]' : ''}`}
                    data-testid={`threshold-row-${r.code}`}>
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={isSel} onChange={() => toggle(r.material_id)}
                        data-testid={`threshold-check-${r.code}`} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">{r.code}</td>
                    <td className="px-3 py-2 text-foreground">
                      {r.name}
                      <span className="block text-[10px] text-muted-foreground">{r.type} · {r.unit}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-foreground whitespace-nowrap">
                      {fmt(r.onhand)} {r.unit}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <GlassInput type="number" step="0.01" min="0" value={valueOf(r, 'min_stock_qty')}
                        onChange={e => setEdit(r.material_id, 'min_stock_qty', e.target.value)}
                        placeholder="0" className="h-8 w-24 text-right text-xs"
                        data-testid={`threshold-min-${r.code}`} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <GlassInput type="number" step="0.01" min="0" value={valueOf(r, 'reorder_point')}
                        onChange={e => setEdit(r.material_id, 'reorder_point', e.target.value)}
                        placeholder="0" className="h-8 w-24 text-right text-xs"
                        data-testid={`threshold-rp-${r.code}`} />
                    </td>
                    <td className="px-3 py-2 text-xs" data-testid={`threshold-basis-${r.code}`}>
                      {r.threshold_basis ? (
                        <>
                          <Badge variant="secondary" className="text-[10px]">
                            {(MODES.find(m => m.key === r.threshold_basis) || {}).label || r.threshold_basis}
                          </Badge>
                          <span className="block text-[10px] text-muted-foreground mt-0.5 line-clamp-2"
                            title={r.threshold_basis_note}>
                            {r.threshold_basis_note}
                          </span>
                          {r.threshold_set_by && (
                            <span className="block text-[10px] text-muted-foreground">
                              oleh {r.threshold_set_by} · {String(r.threshold_set_at).slice(0, 10)}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">
                          {r.has_threshold ? 'diisi sebelum jejak dasar dicatat' : 'belum diisi'}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {s.no_usage_data ? (
                        <span className="text-muted-foreground inline-flex items-center gap-1">
                          <Info className="w-3 h-3" /> belum ada pemakaian 30 hari
                        </span>
                      ) : (
                        <button onClick={() => applySuggestion(r)}
                          className="text-primary hover:underline text-left"
                          data-testid={`threshold-use-suggestion-${r.code}`}>
                          min <strong>{s.suggested_min_stock}</strong> · pesan ulang <strong>{s.suggested_reorder_point}</strong>
                          <span className="block text-[10px] text-muted-foreground">
                            pakai {s.avg_daily_consumption}/hari × {s.lead_time_days} hari · {s.movements_30d} transaksi — klik untuk pakai
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${meta.cls}`}
                        data-testid={`threshold-status-${r.code}`}>
                        {r.status === 'ok' ? <CheckCircle2 className="w-3 h-3" /> : r.status === 'no_threshold' ? null : <AlertTriangle className="w-3 h-3" />}
                        {meta.label}
                      </span>
                      {r.shortage > 0 && (
                        <span className="block text-[10px] text-muted-foreground mt-0.5">kurang {fmt(r.shortage)} {r.unit}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
