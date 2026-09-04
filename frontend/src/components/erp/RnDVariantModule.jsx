import { useState, useEffect, useCallback, Fragment } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Layers, Plus, Trash2, Pencil, Search, X, Palette, Ruler,
  AlertTriangle, Wrench, CheckCircle2, Save,
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_OPTS = [
  { value: 'active',   label: 'Aktif' },
  { value: 'draft',    label: 'Draft' },
  { value: 'archived', label: 'Arsip' },
];

const STATUS_COLOR = {
  active:   'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 border-emerald-400 dark:border-emerald-500/30',
  draft:    'bg-amber-100 dark:bg-amber-500/20 text-amber-600 border-amber-400 dark:border-amber-500/30',
  archived: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-500 border-border dark:border-zinc-500/30',
};

const NEW_COLOR = '__new__';

/** Hex untuk swatch. Dokumen lama menyimpan HEX di `color_code`; dokumen baru
 *  memakai `color_hex` (dan `color_code` berisi KODE master, mis. NVY). */
const swatchOf = (v) => {
  const hx = String(v?.color_hex || '').trim();
  if (hx.startsWith('#')) return hx;
  const legacy = String(v?.color_code || '').trim();
  return legacy.startsWith('#') ? legacy : '#9CA3AF';
};

/** KODE master warna dari sebuah varian (kosong bila masih hex/legacy). */
const codeOf = (v) => {
  const c = String(v?.color_code || '').trim();
  return c.startsWith('#') ? '' : c.toUpperCase();
};

/** Baris ukuran sebuah varian → selalu list objek.
 *  Importir Excel menulis `sizes` sebagai daftar STRING (`['S','M','L']`),
 *  sedangkan modal Varian menulis daftar objek `{size, sku, qty_plan}`.
 *  Tanpa normalisasi ini, varian hasil impor tidak menampilkan chip ukuran
 *  sama sekali (dan modal Edit-nya kehilangan daftar ukurannya). */
const sizeRows = (v) => ((v?.sizes) || []).map(s =>
  typeof s === 'string' ? { size: s, sku: '', qty_plan: 0 } : (s || {})
).filter(s => s.size);

const canonicalSku = (styleCode, colorCode, size) =>
  [styleCode, colorCode, size].map(s => String(s || '').trim().toUpperCase())
    .filter(Boolean).join('-');

async function readErr(res, fallback) {
  try {
    const data = await res.json();
    return data?.detail || data?.message || fallback;
  } catch { return fallback; }
}

export default function RnDVariantModule({ token }) {
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };

  const [variants, setVariants] = useState([]);
  const [styles, setStyles]     = useState([]);
  const [colorOpts, setColorOpts] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [search, setSearch]     = useState('');
  const [filterStyle, setFilterStyle] = useState('');
  const [delId, setDelId]       = useState(null);

  // ── SKU audit (bug §2.5.1 — SKU R&D terbalik dari SSOT) ──
  const [audit, setAudit]       = useState(null);
  const [showAudit, setShowAudit] = useState(false);
  const [fixing, setFixing]     = useState('');

  // ── Modal state ──
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing]   = useState(null);   // variant id saat edit
  const [styleId, setStyleId]   = useState('');
  const [styleCode, setStyleCode] = useState('');
  const [styleName, setStyleName] = useState('');
  const [colorRows, setColorRows] = useState([]);   // [{key, color_id, code, name, hex, isNew, draft:{name,code,hex}}]
  const [sizes, setSizes]       = useState([]);     // ['XS','S',...]
  const [sizeMap, setSizeMap]   = useState([]);     // [{size,size_id,matched}]
  const [sizeSource, setSizeSource] = useState('default');
  const [sizeDirty, setSizeDirty]   = useState(false);
  const [matrix, setMatrix]     = useState({});     // {colorKey: {size: {sku, qty_plan}}}
  const [status, setStatus]     = useState('active');
  const [notes, setNotes]       = useState('');
  const [saving, setSaving]     = useState(false);

  // ─────────────────────────── loaders ───────────────────────────
  const loadVariants = useCallback(async () => {
    setLoading(true);
    try {
      const url = filterStyle
        ? `${API}/api/dewi/rnd/variants?style_id=${filterStyle}`
        : `${API}/api/dewi/rnd/variants`;
      const res = await fetch(url, { headers: h });
      const data = await res.json();
      setVariants(Array.isArray(data) ? data : []);
    } catch { toast.error('Gagal memuat varian'); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStyle, token]);

  const loadStyles = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles`, { headers: h });
      const data = await res.json();
      setStyles(Array.isArray(data) ? data : (data.items || []));
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadColors = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/color-options`, { headers: h });
      if (res.ok) setColorOpts(await res.json());
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadAudit = useCallback(async () => {
    try {
      const qs = filterStyle ? `?style_id=${filterStyle}` : '';
      const res = await fetch(`${API}/api/dewi/rnd/variants/sku-audit${qs}`, { headers: h });
      if (res.ok) setAudit(await res.json());
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStyle, token]);

  useEffect(() => { loadVariants(); loadAudit(); }, [loadVariants, loadAudit]);
  useEffect(() => { loadStyles(); loadColors(); }, [loadStyles, loadColors]);

  const loadSizeList = async (sid) => {
    if (!sid) { setSizes([]); setSizeMap([]); setSizeSource('default'); return []; }
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles/${sid}/size-list`, { headers: h });
      if (!res.ok) return [];
      const d = await res.json();
      setSizes(d.size_list || []);
      setSizeMap(d.size_map || []);
      setSizeSource(d.source || 'default');
      setSizeDirty(false);
      return d.size_list || [];
    } catch { return []; }
  };

  // ─────────────────────────── modal open ───────────────────────────
  const resetModal = () => {
    setColorRows([]); setMatrix({}); setStatus('active'); setNotes('');
    setSizes([]); setSizeMap([]); setSizeDirty(false); setSaving(false);
  };

  const openNew = async () => {
    const sel = styles.find(s => s.id === filterStyle);
    resetModal();
    setEditing(null);
    setStyleId(sel?.id || '');
    setStyleCode(sel?.style_code || '');
    setStyleName(sel?.style_name || '');
    setShowForm(true);
    if (sel?.id) await loadSizeList(sel.id);
    setColorRows([blankColorRow()]);
  };

  const openEdit = async (v) => {
    resetModal();
    setEditing(v.id);
    setStyleId(v.style_id || '');
    setStyleCode(v.style_code || '');
    setStyleName(v.style_name || '');
    setStatus(v.status || 'active');
    setNotes(v.notes || '');
    setShowForm(true);

    const list = await loadSizeList(v.style_id);
    const rows = sizeRows(v);
    const rowSizes = rows.map(s => s.size);
    const merged = rowSizes.length ? rowSizes : list;
    setSizes(merged);

    const key = v.color_id || codeOf(v) || 'legacy';
    setColorRows([{
      key,
      color_id: v.color_id || '',
      code: codeOf(v),
      name: v.color || '',
      hex: swatchOf(v),
      isNew: false,
      draft: { name: '', code: '', hex: '#4F46E5' },
    }]);
    const cell = {};
    rows.forEach(s => {
      cell[s.size] = { sku: s.sku || '', qty_plan: Number(s.qty_plan || 0) };
    });
    setMatrix({ [key]: cell });
  };

  const blankColorRow = () => ({
    key: `row-${Math.random().toString(36).slice(2, 9)}`,
    color_id: '', code: '', name: '', hex: '#9CA3AF',
    isNew: false, draft: { name: '', code: '', hex: '#4F46E5' },
  });

  const onStyleChange = async (sid) => {
    const sel = styles.find(s => s.id === sid);
    setStyleId(sid);
    setStyleCode(sel?.style_code || '');
    setStyleName(sel?.style_name || '');
    if (sid) await loadSizeList(sid);
  };

  // ─────────────────────────── color rows ───────────────────────────
  const addColorRow = () => setColorRows(rows => [...rows, blankColorRow()]);

  const removeColorRow = (key) => {
    setColorRows(rows => rows.filter(r => r.key !== key));
    setMatrix(m => { const n = { ...m }; delete n[key]; return n; });
  };

  const pickColor = (key, value) => {
    if (value === NEW_COLOR) {
      setColorRows(rows => rows.map(r => r.key === key
        ? { ...r, isNew: true, color_id: '', code: '', name: '' } : r));
      return;
    }
    const opt = colorOpts.find(c => c.color_id === value);
    if (!opt) return;
    if (colorRows.some(r => r.key !== key && r.color_id === opt.color_id)) {
      toast.error(`Warna "${opt.name}" sudah ada di daftar. Satu warna cukup satu baris.`);
      return;
    }
    const oldKey = key;
    setColorRows(rows => rows.map(r => r.key === key
      ? { ...r, isNew: false, color_id: opt.color_id, code: opt.code, name: opt.name, hex: opt.hex }
      : r));
    // SKU lama (dari warna sebelumnya) tidak boleh nyangkut
    setMatrix(m => ({ ...m, [oldKey]: {} }));
  };

  const setDraft = (key, field, val) =>
    setColorRows(rows => rows.map(r => r.key === key
      ? { ...r, draft: { ...r.draft, [field]: val } } : r));

  const saveNewColor = async (row) => {
    const name = (row.draft.name || '').trim();
    if (!name) return toast.error('Isi nama warna baru');
    try {
      const res = await fetch(`${API}/api/dewi/rnd/color-options`, {
        method: 'POST', headers: h,
        body: JSON.stringify({ name, code: (row.draft.code || '').trim(), hex: row.draft.hex }),
      });
      if (!res.ok) return toast.error(await readErr(res, 'Gagal menambah warna ke master'));
      const created = await res.json();
      setColorOpts(prev => [...prev, created]);
      setColorRows(rows => rows.map(r => r.key === row.key
        ? { ...r, isNew: false, color_id: created.color_id, code: created.code,
            name: created.name, hex: created.hex }
        : r));
      toast.success(`Warna "${created.name}" (${created.code}) ditambahkan ke master & terpilih`);
    } catch { toast.error('Gagal menambah warna ke master'); }
  };

  // ─────────────────────────── sizes ───────────────────────────
  const addSize = () => { setSizes(s => [...s, '']); setSizeDirty(true); };

  const renameSize = (idx, val) => {
    const old = sizes[idx];
    setSizes(prev => prev.map((s, i) => (i === idx ? val : s)));
    setSizeDirty(true);
    if (old && old !== val) {
      setMatrix(m => {
        const n = {};
        Object.entries(m).forEach(([ck, cell]) => {
          const c2 = { ...cell };
          if (Object.prototype.hasOwnProperty.call(c2, old)) {
            c2[val] = c2[old];
            delete c2[old];
          }
          n[ck] = c2;
        });
        return n;
      });
    }
  };

  const removeSize = (idx) => {
    const gone = sizes[idx];
    setSizes(prev => prev.filter((_, i) => i !== idx));
    setSizeDirty(true);
    setMatrix(m => {
      const n = {};
      Object.entries(m).forEach(([ck, cell]) => {
        const c2 = { ...cell }; delete c2[gone]; n[ck] = c2;
      });
      return n;
    });
  };

  const persistSizeList = async (silent = false) => {
    const clean = sizes.map(s => String(s || '').trim()).filter(Boolean);
    if (!styleId) { if (!silent) toast.error('Pilih style dulu'); return false; }
    if (clean.length === 0) { if (!silent) toast.error('Daftar ukuran tidak boleh kosong'); return false; }
    try {
      const res = await fetch(`${API}/api/dewi/rnd/styles/${styleId}/size-list`, {
        method: 'PUT', headers: h, body: JSON.stringify({ size_list: clean }),
      });
      if (!res.ok) { if (!silent) toast.error(await readErr(res, 'Gagal menyimpan daftar ukuran')); return false; }
      const d = await res.json();
      setSizes(d.size_list || clean);
      setSizeMap(d.size_map || []);
      setSizeSource(d.source || 'style');
      setSizeDirty(false);
      if (!silent) {
        toast.success(`Daftar ukuran style ${styleCode} disimpan (${(d.size_list || []).length} ukuran)`);
        if ((d.unmatched || []).length) {
          toast.warning(`Belum dipadankan ke master produksi: ${d.unmatched.join(', ')}`);
        }
      }
      return true;
    } catch { if (!silent) toast.error('Gagal menyimpan daftar ukuran'); return false; }
  };

  // ─────────────────────────── matrix cells ───────────────────────────
  const cellVal = (ck, size, field) => {
    const v = matrix[ck]?.[size];
    if (!v) return field === 'qty_plan' ? 0 : '';
    return v[field] ?? (field === 'qty_plan' ? 0 : '');
  };

  const setCell = (ck, size, field, val) => setMatrix(m => ({
    ...m,
    [ck]: { ...(m[ck] || {}), [size]: {
      ...(m[ck]?.[size] || { sku: '', qty_plan: 0 }),
      [field]: field === 'qty_plan' ? Number(val || 0) : val,
    } },
  }));

  const autoGenSKU = () => {
    const ready = colorRows.filter(r => r.code || r.name);
    if (!styleCode) return toast.error('Pilih style dulu (kode style dipakai di SKU)');
    if (ready.length === 0) return toast.error('Pilih minimal satu warna dulu');
    const clean = sizes.map(s => String(s || '').trim()).filter(Boolean);
    setMatrix(m => {
      const n = { ...m };
      ready.forEach(r => {
        const ck = r.key;
        n[ck] = { ...(n[ck] || {}) };
        clean.forEach(sz => {
          const prev = n[ck][sz] || { sku: '', qty_plan: 0 };
          n[ck][sz] = { ...prev, sku: canonicalSku(styleCode, r.code || r.name, sz) };
        });
      });
      return n;
    });
    toast.success('SKU di-generate mengikuti SSOT: {STYLE}-{KODE WARNA}-{UKURAN}');
  };

  // ─────────────────────────── save ───────────────────────────
  const handleSave = async () => {
    if (!styleId) return toast.error('Pilih style terlebih dahulu');
    const cleanSizes = sizes.map(s => String(s || '').trim()).filter(Boolean);
    if (cleanSizes.length === 0) return toast.error('Tambahkan minimal satu ukuran');

    const chosen = colorRows.filter(r => r.color_id || r.name);
    if (chosen.length === 0) return toast.error('Tambahkan minimal satu warna');
    const pending = colorRows.find(r => r.isNew && !r.color_id);
    if (pending) return toast.error('Ada warna baru yang belum disimpan ke master — klik "Simpan ke Master"');

    setSaving(true);
    try {
      if (sizeDirty) await persistSizeList(true);

      if (editing) {
        const r = chosen[0];
        const body = {
          style_id: styleId, style_code: styleCode, style_name: styleName,
          color_id: r.color_id || undefined, color: r.name, color_code: r.code,
          color_hex: r.hex, status, notes,
          sizes: cleanSizes.map(sz => ({
            size: sz,
            sku: cellVal(r.key, sz, 'sku') || canonicalSku(styleCode, r.code || r.name, sz),
            qty_plan: Number(cellVal(r.key, sz, 'qty_plan') || 0),
          })),
        };
        const res = await fetch(`${API}/api/dewi/rnd/variants/${editing}`, {
          method: 'PUT', headers: h, body: JSON.stringify(body),
        });
        if (!res.ok) { toast.error(await readErr(res, 'Gagal memperbarui varian')); return; }
        toast.success('Varian diperbarui');
      } else {
        const mtx = {};
        chosen.forEach(r => {
          const id = r.color_id || r.code;
          mtx[id] = {};
          cleanSizes.forEach(sz => {
            mtx[id][sz] = {
              sku: cellVal(r.key, sz, 'sku') || '',
              qty_plan: Number(cellVal(r.key, sz, 'qty_plan') || 0),
            };
          });
        });
        const body = {
          style_id: styleId, style_code: styleCode, style_name: styleName,
          colors: chosen.map(r => ({ color_id: r.color_id, code: r.code, name: r.name, hex: r.hex })),
          sizes: cleanSizes, matrix: mtx, status, notes,
        };
        const res = await fetch(`${API}/api/dewi/rnd/variants/bulk`, {
          method: 'POST', headers: h, body: JSON.stringify(body),
        });
        if (!res.ok) { toast.error(await readErr(res, 'Gagal menyimpan varian'), { duration: 7000 }); return; }
        const out = await res.json();
        toast.success(`${out.created_count} varian dibuat (${chosen.length} warna × ${cleanSizes.length} ukuran)`);
      }
      setShowForm(false);
      loadVariants();
      loadAudit();
    } catch { toast.error('Gagal menyimpan varian'); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/rnd/variants/${delId}`, { method: 'DELETE', headers: h });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal menghapus')); return; }
      toast.success('Varian dihapus');
      setDelId(null);
      loadVariants(); loadAudit();
    } catch { toast.error('Gagal menghapus'); }
  };

  const fixSku = async (vid) => {
    setFixing(vid);
    try {
      const res = await fetch(`${API}/api/dewi/rnd/variants/${vid}/fix-sku`, { method: 'POST', headers: h });
      if (!res.ok) { toast.error(await readErr(res, 'Gagal memperbaiki SKU')); return; }
      const out = await res.json();
      toast.success(`${out.changed_count} SKU diperbaiki mengikuti SSOT`);
      loadVariants(); loadAudit();
    } catch { toast.error('Gagal memperbaiki SKU'); }
    finally { setFixing(''); }
  };

  const filtered = variants.filter(v => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (v.color || '').toLowerCase().includes(q)
      || (v.color_code || '').toLowerCase().includes(q)
      || (v.style_code || '').toLowerCase().includes(q)
      || (v.style_name || '').toLowerCase().includes(q);
  });

  const unmatchedSizes = new Set((sizeMap || []).filter(m => !m.matched).map(m => m.size));
  const activeColors = colorRows.filter(r => r.color_id || r.name);
  const cleanSizesView = sizes;

  return (
    <div className="p-6" data-testid="rnd-variant-module">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-violet-500" /> Varian Produk
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            Banyak warna sekaligus (dari master warna) × ukuran bebas per style — SKU mengikuti SSOT
          </p>
        </div>
        <Button onClick={openNew} className="gap-2" data-testid="rnd-variant-add-btn">
          <Plus className="w-4 h-4" /> Tambah Varian
        </Button>
      </div>

      {/* SKU tidak sesuai SSOT */}
      {audit && (audit.drift_variants > 0 || audit.colors_not_in_master > 0) && (
        <GlassCard className="p-4 mb-5 border-amber-400 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10"
          data-testid="rnd-sku-audit-banner">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                  {audit.drift_rows} SKU tidak sesuai SSOT
                  {audit.colors_not_in_master > 0 && ` · ${audit.colors_not_in_master} varian warnanya belum ada di master`}
                </div>
                <div className="text-xs text-amber-700/80 dark:text-amber-300/80 mt-0.5">
                  Aturan SSOT: <span className="font-mono">{audit.convention}</span>. SKU lama tidak diubah
                  otomatis — perbaiki per baris supaya Anda yang memutuskan.
                </div>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowAudit(v => !v)}
              className="h-8 text-xs" data-testid="rnd-sku-audit-toggle">
              {showAudit ? 'Sembunyikan' : `Lihat ${audit.items.length} varian`}
            </Button>
          </div>

          {showAudit && (
            <div className="mt-4 space-y-3" data-testid="rnd-sku-audit-panel">
              {audit.items.map(it => (
                <div key={it.variant_id} className="rounded-lg border border-amber-300 dark:border-amber-500/30 bg-background/70 p-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded border border-foreground/20"
                        style={{ backgroundColor: it.color_hex }} />
                      <span className="text-sm font-medium text-foreground">{it.color || '(tanpa nama)'}</span>
                      {it.color_in_master ? (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{it.color_code}</span>
                      ) : (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-500/40">
                          belum ada di master warna
                        </span>
                      )}
                      <span className="text-xs text-foreground/50">{it.style_code}</span>
                    </div>
                    <Button size="sm" variant="outline" disabled={fixing === it.variant_id}
                      onClick={() => fixSku(it.variant_id)} className="h-7 text-xs gap-1"
                      data-testid={`rnd-sku-fix-${it.variant_id}`}>
                      <Wrench className="w-3 h-3" /> {fixing === it.variant_id ? 'Memperbaiki…' : 'Perbaiki SKU'}
                    </Button>
                  </div>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-foreground/40">
                          <th className="text-left px-2 py-1 font-medium">Ukuran</th>
                          <th className="text-left px-2 py-1 font-medium">SKU sekarang</th>
                          <th className="text-left px-2 py-1 font-medium">SKU seharusnya (SSOT)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {it.rows.filter(r => !r.ok).map((r, i) => (
                          <tr key={i} className="border-t border-foreground/5">
                            <td className="px-2 py-1 font-semibold text-foreground">{r.size}</td>
                            <td className="px-2 py-1 font-mono text-red-600 dark:text-red-400 line-through">{r.sku_now || '—'}</td>
                            <td className="px-2 py-1 font-mono text-emerald-600 dark:text-emerald-400">{r.sku_canonical || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari warna / kode / style..." className="pl-9" data-testid="rnd-variant-search" />
        </div>
        <SmartNativeSelect value={filterStyle} onChange={e => setFilterStyle(e.target.value)}
          data-testid="rnd-variant-filter-style"
          className="border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground min-w-[200px]">
          <option value="">Semua Style</option>
          {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
        </SmartNativeSelect>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex justify-center h-32 items-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-violet-500" />
        </div>
      ) : filtered.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <Layers className="w-10 h-10 text-foreground/20 mx-auto mb-3" />
          <p className="text-foreground/50 text-sm">Belum ada varian produk.</p>
          <Button variant="outline" className="mt-3" onClick={openNew}>+ Tambah Varian Pertama</Button>
        </GlassCard>
      ) : (
        <div className="space-y-4">
          {filtered.map(v => (
            <GlassCard key={v.id} className="p-4" data-testid={`rnd-variant-card-${v.id}`}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg border border-foreground/20 shadow-sm flex-shrink-0"
                    style={{ backgroundColor: swatchOf(v) }} />
                  <div>
                    <div className="font-semibold text-foreground flex items-center gap-2">
                      {v.color}
                      {codeOf(v) && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                          {codeOf(v)}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-foreground/50">{v.style_code} — {v.style_name}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLOR[v.status] || ''}`}>
                    {STATUS_OPTS.find(s => s.value === v.status)?.label || v.status}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => openEdit(v)}
                    className="h-8 w-8 p-0" data-testid={`rnd-variant-edit-${v.id}`}>
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setDelId(v.id)}
                    className="h-8 w-8 p-0 text-red-700 dark:text-red-500 hover:bg-red-100 dark:hover:bg-red-500/10"
                    data-testid={`rnd-variant-del-${v.id}`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              {sizeRows(v).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {sizeRows(v).map((s, i) => (
                    <div key={i} className="text-xs bg-foreground/5 border border-foreground/10 rounded-lg px-2.5 py-1.5">
                      <span className="font-bold text-foreground">{s.size}</span>
                      {s.qty_plan > 0 && <span className="text-foreground/50 ml-1">× {s.qty_plan} pcs</span>}
                      {s.sku
                        ? <div className="text-foreground/40 font-mono mt-0.5">{s.sku}</div>
                        : <div className="text-amber-600 dark:text-amber-400 mt-0.5">SKU belum dibuat</div>}
                    </div>
                  ))}
                </div>
              )}
              {v.notes && <p className="text-xs text-foreground/40 mt-2">{v.notes}</p>}
            </GlassCard>
          ))}
        </div>
      )}

      {/* ───────────────────────── Form Modal ───────────────────────── */}
      <Modal open={showForm} onClose={() => setShowForm(false)}
        title={editing ? 'Edit Varian' : 'Tambah Varian (bisa banyak warna sekaligus)'} size="3xl">
        <div className="space-y-5">
          <div>
            <Label>Style Produk <span className="text-red-700 dark:text-red-400">*</span></Label>
            <SmartNativeSelect value={styleId} onChange={e => onStyleChange(e.target.value)}
              data-testid="rnd-variant-style-select"
              className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
              <option value="">-- Pilih Style --</option>
              {styles.map(s => <option key={s.id} value={s.id}>{s.style_code} — {s.style_name}</option>)}
            </SmartNativeSelect>
          </div>

          {/* ── WARNA (multi) ── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="flex items-center gap-1">
                <Palette className="w-4 h-4" /> Warna
                {!editing && <span className="text-xs font-normal text-foreground/50">(bisa lebih dari satu)</span>}
              </Label>
              {!editing && (
                <Button type="button" variant="outline" size="sm" onClick={addColorRow}
                  className="h-7 text-xs gap-1" data-testid="rnd-variant-add-color">
                  <Plus className="w-3 h-3" /> Tambah Warna
                </Button>
              )}
            </div>

            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] divide-y divide-foreground/5">
              {colorRows.length === 0 && (
                <div className="p-4 text-center text-sm text-foreground/40">
                  Belum ada warna. Klik "Tambah Warna".
                </div>
              )}
              {colorRows.map((r, idx) => (
                <div key={r.key} className="p-3" data-testid={`rnd-variant-color-row-${idx}`}>
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-7 rounded-md border border-foreground/20 flex-shrink-0 shadow-sm"
                      style={{ backgroundColor: r.hex }} />
                    <SmartNativeSelect
                      value={r.isNew ? NEW_COLOR : (r.color_id || '')}
                      onChange={e => pickColor(r.key, e.target.value)}
                      data-testid={`rnd-variant-color-select-${idx}`}
                      className="flex-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                      <option value="">-- Pilih warna dari master --</option>
                      {colorOpts.map(c => (
                        <option key={c.color_id} value={c.color_id}>{`${c.name} (${c.code})`}</option>
                      ))}
                      <option value={NEW_COLOR}>+ Warna baru…</option>
                    </SmartNativeSelect>
                    {r.code && (
                      <span className="text-[11px] font-mono px-2 py-1 rounded bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300">
                        {r.code}
                      </span>
                    )}
                    {!editing && (
                      <Button variant="ghost" size="sm" onClick={() => removeColorRow(r.key)}
                        className="h-8 w-8 p-0 text-red-700 dark:text-red-500"
                        data-testid={`rnd-variant-del-color-${idx}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>

                  {r.isNew && (
                    <div className="mt-2 ml-9 grid grid-cols-[1fr_110px_44px_auto] gap-2 items-center">
                      <Input value={r.draft.name} onChange={e => setDraft(r.key, 'name', e.target.value)}
                        placeholder="Nama warna baru (mis. Navy Blue)" className="h-9 text-sm"
                        data-testid={`rnd-variant-new-color-name-${idx}`} />
                      <Input value={r.draft.code} onChange={e => setDraft(r.key, 'code', e.target.value.toUpperCase())}
                        placeholder="KODE" className="h-9 text-sm font-mono"
                        data-testid={`rnd-variant-new-color-code-${idx}`} />
                      <input type="color" value={r.draft.hex}
                        onChange={e => setDraft(r.key, 'hex', e.target.value)}
                        className="w-11 h-9 rounded border border-input cursor-pointer bg-background" />
                      <Button type="button" size="sm" onClick={() => saveNewColor(r)}
                        className="h-9 text-xs gap-1" data-testid={`rnd-variant-save-color-${idx}`}>
                        <Save className="w-3 h-3" /> Simpan ke Master
                      </Button>
                      <p className="col-span-4 text-[11px] text-foreground/50">
                        Kode dipakai di SKU (mis. NVY). Warna ini ditulis ke master warna yang sama
                        dengan produksi &amp; gudang — tidak perlu pindah menu.
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* ── UKURAN & SKU (matriks warna × ukuran) ── */}
          <div>
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
              <Label className="flex items-center gap-1">
                <Ruler className="w-4 h-4" /> Ukuran &amp; SKU
                <span className="text-xs font-normal text-foreground/50">
                  {sizeSource === 'default' ? '(daftar bawaan — simpan untuk jadikan milik style ini)' : `(daftar style ${styleCode})`}
                </span>
              </Label>
              <div className="flex gap-2 flex-wrap">
                <Button type="button" variant="outline" size="sm" onClick={addSize}
                  className="h-7 text-xs gap-1" data-testid="rnd-variant-add-size">
                  <Plus className="w-3 h-3" /> Tambah Ukuran
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => persistSizeList(false)}
                  disabled={!styleId} className="h-7 text-xs gap-1" data-testid="rnd-variant-save-sizes">
                  <Save className="w-3 h-3" /> Simpan Daftar Ukuran{sizeDirty ? ' *' : ''}
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={autoGenSKU}
                  className="h-7 text-xs" data-testid="rnd-variant-autogen-sku">
                  Auto-generate SKU
                </Button>
              </div>
            </div>

            {sizeDirty && (
              <div className="text-[11px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/30 rounded-md px-2 py-1.5 mb-2">
                Daftar ukuran berubah — akan ikut tersimpan ke style saat Anda menekan Simpan.
              </div>
            )}

            <div className="overflow-x-auto rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
              <table className="w-full text-sm" data-testid="rnd-variant-matrix">
                <thead className="bg-foreground/5">
                  <tr>
                    <th rowSpan="2" className="text-left px-3 py-2 text-xs text-foreground/50 w-56 align-bottom">Ukuran</th>
                    {activeColors.map(r => (
                      <th key={r.key} colSpan="2" className="text-center px-2 py-1.5 text-xs text-foreground/60 border-l border-foreground/10">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="w-3 h-3 rounded-sm border border-foreground/20" style={{ backgroundColor: r.hex }} />
                          {r.name || '(warna)'}{r.code ? ` · ${r.code}` : ''}
                        </span>
                      </th>
                    ))}
                    <th rowSpan="2" className="w-9" />
                  </tr>
                  <tr>
                    {activeColors.map(r => (
                      <Fragment key={`hdr-${r.key}`}>
                        <th className="text-left px-2 py-1 text-[10px] text-foreground/40 border-l border-foreground/10">SKU</th>
                        <th className="text-right px-2 py-1 text-[10px] text-foreground/40 w-20">Qty</th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cleanSizesView.length === 0 && (
                    <tr><td colSpan={2 + activeColors.length * 2} className="px-3 py-6 text-center text-sm text-foreground/40">
                      Belum ada ukuran. Klik "Tambah Ukuran" — bebas, boleh "All Size" atau "28/30".
                    </td></tr>
                  )}
                  {cleanSizesView.map((sz, i) => (
                    <tr key={i} className="border-t border-foreground/5">
                      <td className="px-3 py-1.5">
                        <div className="flex items-center gap-1.5">
                          <Input value={sz} onChange={e => renameSize(i, e.target.value)}
                            placeholder="Ukuran" className="h-7 text-xs font-semibold min-w-[72px]"
                            data-testid={`rnd-variant-size-input-${i}`} />
                          {unmatchedSizes.has(sz) && (
                            <span title="Belum ada di master ukuran produksi — nanti perlu dipadankan manual saat masuk PO produksi"
                              className="text-[9px] px-1 py-0.5 rounded bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-500/40 whitespace-nowrap">
                              belum dipadankan
                            </span>
                          )}
                        </div>
                      </td>
                      {activeColors.map(r => (
                        <Fragment key={`${r.key}-${i}`}>
                          <td className="px-2 py-1.5 border-l border-foreground/10">
                            <Input value={cellVal(r.key, sz, 'sku')}
                              onChange={e => setCell(r.key, sz, 'sku', e.target.value)}
                              placeholder={canonicalSku(styleCode, r.code || r.name, sz) || 'SKU'}
                              className="h-7 text-xs font-mono"
                              data-testid={`rnd-variant-sku-${i}-${r.code || r.key}`} />
                          </td>
                          <td className="px-2 py-1.5">
                            <Input type="number" min="0" value={cellVal(r.key, sz, 'qty_plan')}
                              onChange={e => setCell(r.key, sz, 'qty_plan', e.target.value)}
                              className="h-7 text-xs text-right"
                              data-testid={`rnd-variant-qty-${i}-${r.code || r.key}`} />
                          </td>
                        </Fragment>
                      ))}
                      <td className="px-1 py-1.5">
                        <Button variant="ghost" size="sm" onClick={() => removeSize(i)}
                          className="h-7 w-7 p-0 text-red-700 dark:text-red-500"
                          data-testid={`rnd-variant-del-size-${i}`}>
                          <X className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!editing && activeColors.length > 0 && cleanSizesView.length > 0 && (
              <p className="text-[11px] text-foreground/50 mt-2 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                Simpan akan membuat <b className="text-foreground">{activeColors.length} varian</b>
                {' '}(satu per warna), masing-masing dengan {cleanSizesView.length} ukuran.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Status</Label>
              <select value={status} onChange={e => setStatus(e.target.value)}
                data-testid="rnd-variant-status"
                className="w-full mt-1 border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground">
                {STATUS_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <Label>Catatan</Label>
              <Input className="mt-1" value={notes} onChange={e => setNotes(e.target.value)}
                data-testid="rnd-variant-notes" />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="outline" onClick={() => setShowForm(false)}>Batal</Button>
          <Button onClick={handleSave} disabled={saving} data-testid="rnd-variant-save-btn">
            {saving ? 'Menyimpan…' : (editing ? 'Simpan' : `Simpan ${activeColors.length || ''} Varian`)}
          </Button>
        </div>
      </Modal>

      {delId && (
        <ConfirmDialog
          onConfirm={handleDelete}
          onCancel={() => setDelId(null)}
          title="Hapus Varian?"
          message="Data varian akan dihapus permanen."
        />
      )}
    </div>
  );
}
