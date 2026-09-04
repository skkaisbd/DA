import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Edit2, Trash2, Package, Scale, Gem, Archive, AlertTriangle, Search } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import PaginationBar from './PaginationBar';
import ImportExportToolbar from './ImportExportToolbar';
import { CATEGORY_OPTIONS, categoryToStoredType, typeToCategory, isKgLike } from '@/lib/itemTaxonomy';
import UomEditor from './UomEditor';
import { resolveUoms, sanitizeUoms, purchaseUomOf, issueUomOf, displayUomOf, MATERIAL_UNITS } from '@/lib/uom';
import { readField, readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

// Tampilan per 3 kategori bisnis (Bahan/Aksesoris/Produk Jadi). Semua tipe legacy
// dipetakan ke kategori yang sama agar label konsisten.
const TYPE_META = {
  yarn:        { label: 'Bahan',       icon: Scale,   color: 'text-amber-600 dark:text-amber-300',     bg: 'bg-amber-400/10',   border: 'border-amber-300/20' },
  fabric:      { label: 'Bahan',       icon: Scale,   color: 'text-amber-600 dark:text-amber-300',     bg: 'bg-amber-400/10',   border: 'border-amber-300/20' },
  kain:        { label: 'Bahan',       icon: Scale,   color: 'text-amber-600 dark:text-amber-300',     bg: 'bg-amber-400/10',   border: 'border-amber-300/20' },
  interlining: { label: 'Bahan',       icon: Scale,   color: 'text-amber-600 dark:text-amber-300',     bg: 'bg-amber-400/10',   border: 'border-amber-300/20' },
  accessory:   { label: 'Aksesoris',   icon: Gem,     color: 'text-primary',                           bg: 'bg-primary/10',     border: 'border-primary/25' },
  packaging:   { label: 'Aksesoris',   icon: Gem,     color: 'text-primary',                           bg: 'bg-primary/10',     border: 'border-primary/25' },
  fg:          { label: 'Produk Jadi', icon: Archive, color: 'text-emerald-600 dark:text-emerald-300', bg: 'bg-emerald-400/10', border: 'border-emerald-300/20' },
  other:       { label: 'Lainnya',     icon: Package, color: 'text-muted-foreground',                  bg: 'bg-muted/20',       border: 'border-border' },
};

export default function RahazaMaterialsModule({ token }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [filterType, setFilterType] = useState('');
  const [filterLowStock, setFilterLowStock] = useState(false);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState({
    code: '', name: '', type: 'fabric', unit: 'kg', category: '', category_name: '', composition: '', color: '', notes: '',
    min_stock: 0, min_stock_qty: '', min_stock_percentage: '', reorder_point: '', active: true,
    unit_cost: 0,
    // Satuan berjenjang (SSOT: lib/uom.js). `pack_*` tetap ada sebagai cermin
    // supaya dokumen lama & konsumen lama tidak pecah (INV-UOM-4).
    uoms: [], purchase_uom: '', issue_uom: '', display_uom: '',
    pack_unit: 'pack', pack_size: 1, display_in_packs: false,
  });
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  // Pagination
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState(null);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchRows = useCallback(async (targetPage = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: targetPage, limit: 50 });
      if (filterType) params.set('type', filterType);
      else params.set('exclude_type', 'fg'); // tab "Bahan & Aksesoris" tidak menampilkan Produk Jadi (FG punya tab sendiri)
      if (filterLowStock) params.set('low_stock', 'true');
      if (search) params.set('search', search);
      const r = await fetch(`/api/rahaza/materials?${params}`, { headers });
      if (r.ok) {
        const data = await r.json();
        if (data && data.items && data.pagination) {
          setRows(data.items);
          setPagination(data.pagination);
        } else {
          setRows(Array.isArray(data) ? data : []);
          setPagination(null);
        }
      }
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterType, filterLowStock, search]);

  useEffect(() => { setPage(1); fetchRows(1); }, [filterType, filterLowStock, search]); // eslint-disable-line
  useEffect(() => { fetchRows(page); }, [page]); // eslint-disable-line
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/rahaza/material-categories', { headers });
        if (r.ok) setCategories(await r.json());
      } catch { /* ignore */ }
    })();
  }, []); // eslint-disable-line

  const openCreate = () => {
    setEditing(null);
    setForm({ code: '', name: '', type: 'fabric', unit: 'kg', category: '', category_name: '', composition: '', color: '', notes: '', min_stock: 0, min_stock_qty: '', min_stock_percentage: '', reorder_point: '', active: true, unit_cost: 0, gsm: '', width_cm: '', uoms: [], purchase_uom: '', issue_uom: '', display_uom: '', pack_unit: 'pack', pack_size: 1, display_in_packs: false });
    setFormError(''); setModalOpen(true);
  };
  const openEdit = (r) => {
    setEditing(r);
    setForm({ ...r, composition: readField(r, FIELD.composition), min_stock_qty: r.min_stock_qty || '', min_stock_percentage: r.min_stock_percentage || '', reorder_point: r.reorder_point || '', unit_cost: r.unit_cost || 0,
      gsm: r.gsm ?? '', width_cm: r.width_cm ?? '',
      uoms: resolveUoms(r), purchase_uom: purchaseUomOf(r), issue_uom: issueUomOf(r), display_uom: displayUomOf(r),
      pack_unit: r.pack_unit || 'pack', pack_size: r.pack_size || 1, display_in_packs: r.display_in_packs || false });
    setFormError(''); setModalOpen(true);
  };
  const save = async () => {
    setSaving(true); setFormError('');
    try {
      if (!form.code || !form.name) throw new Error('Kode & nama wajib diisi.');
      const url = editing ? `/api/rahaza/materials/${editing.id}` : '/api/rahaza/materials';
      const method = editing ? 'PUT' : 'POST';
      const payload = {
        ...form,
        min_stock: Number(form.min_stock) || 0,
        min_stock_qty: form.min_stock_qty !== '' ? Number(form.min_stock_qty) : null,
        min_stock_percentage: form.min_stock_percentage !== '' ? Number(form.min_stock_percentage) : null,
        reorder_point: form.reorder_point !== '' ? Number(form.reorder_point) : 0,
        // Harga hanya dikirim saat MEMBUAT (harga awal). Saat mengedit, harga
        // tidak boleh datang dari layar master — ia lahir dari harga pembelian.
        ...(editing ? {} : { unit_cost: Number(form.unit_cost) || 0 }),
        gsm: form.gsm !== '' && form.gsm != null ? Number(form.gsm) : null,
        width_cm: form.width_cm !== '' && form.width_cm != null ? Number(form.width_cm) : null,
        // Satuan: kirim daftar UOM yang sudah dibersihkan. Backend (core/uom)
        // memvalidasi ulang dan menulis cermin pack_unit/pack_size sendiri.
        uoms: sanitizeUoms(form.uoms, form.unit),
      };
      if (editing) delete payload.unit_cost;   // harga tidak diedit dari master
      const res = await fetch(url, { method, headers, body: JSON.stringify(payload) });      if (!res.ok) {
        const STATUS_MSG = { 400: 'Data tidak valid.', 403: 'Tidak ada akses.', 409: 'Kode sudah terpakai.' };
        throw new Error(STATUS_MSG[res.status] || `Gagal simpan (HTTP ${res.status})`);
      }
      setModalOpen(false); fetchRows();
    } catch (e) { setFormError(e.message); }
    finally { setSaving(false); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Nonaktifkan material ${r.code}?`)) return;
    await fetch(`/api/rahaza/materials/${r.id}`, { method: 'DELETE', headers });
    fetchRows();
  };

  const lowStockCount = rows.filter(r => r.is_low_stock || r.below_min).length;

  if (loading) return (<div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>);

  return (
    <div className="space-y-5" data-testid="rahaza-materials-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Master Material</h1>
          <p className="text-muted-foreground text-sm mt-1">Bahan, aksesoris, dan produk jadi. Dipakai di Stock, Material Issue, dan WO.</p>
        </div>
        <div className="flex items-center gap-2">
          <ImportExportToolbar collectionKey="materials" label="Bahan / Material" onImported={fetchRows} />
          <Button onClick={openCreate} data-testid="mat-add-btn"><Plus className="w-4 h-4 mr-1.5" /> Material Baru</Button>
        </div>
      </div>

      {/* Sprint 3.4: Low Stock Alert Banner */}
      {lowStockCount > 0 && (
        <div className="flex items-center gap-2 bg-amber-400/10 border border-amber-300/20 rounded-lg px-4 py-2.5" data-testid="mat-low-stock-banner">
          <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0" />
          <span className="text-sm text-amber-300 font-medium">{lowStockCount} material di bawah ambang minimum stok.</span>
          <button onClick={() => setFilterLowStock(true)} className="text-xs text-amber-300 underline ml-auto">Lihat semua</button>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <GlassInput value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari kode/nama..." className="pl-8 h-9 text-sm" data-testid="mat-search" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="mat-filter-type">
          <option value="">Semua (Bahan &amp; Aksesoris)</option>
          <option value="bahan">Bahan</option>
          <option value="aksesoris">Aksesoris</option>
        </select>
        <button
          onClick={() => setFilterLowStock(!filterLowStock)}
          className={`h-9 px-3 rounded-lg border text-sm flex items-center gap-1.5 transition-colors ${filterLowStock ? 'bg-amber-400/15 border-amber-300/30 text-amber-300' : 'border-[var(--glass-border)] text-muted-foreground hover:text-foreground'}`}
          data-testid="mat-filter-low-stock">
          <AlertTriangle className="w-3.5 h-3.5" /> Low Stock {filterLowStock && `(aktif)`}
        </button>
      </div>

      <GlassCard className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-3">Kode</th>
                <th className="px-4 py-3">Nama</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Unit</th>
                <th className="px-4 py-3">Min Stok</th>
                <th className="px-4 py-3">Warna/Jenis</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">
                  {filterLowStock ? 'Tidak ada material low stock.' : 'Belum ada material. Klik "Material Baru" untuk menambah.'}
                </td></tr>
              ) : rows.map(r => {
                const meta = TYPE_META[r.type] || {};
                const Icon = meta.icon || Package;
                const isLow = r.is_low_stock || r.below_min;
                return (
                  <tr key={r.id} className={`border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] ${!r.active ? 'opacity-50' : ''} ${isLow ? 'bg-amber-400/4' : ''}`} data-testid={`mat-row-${r.code}`}>
                    <td className="px-4 py-3 font-mono text-xs text-foreground">
                      {r.code}
                      {isLow && <AlertTriangle className="w-3 h-3 text-amber-300 inline ml-1.5" title={r.low_stock_reason || 'Low Stock'} data-testid={`mat-low-badge-${r.code}`} />}
                    </td>
                    <td className="px-4 py-3 text-foreground">{r.name}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${meta.bg} ${meta.border} border ${meta.color}`}>
                        <Icon className="w-3 h-3" /> {meta.label || r.type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{r.unit}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {r.min_stock_qty ? <span className="font-mono">{r.min_stock_qty} {r.unit}</span> : (r.min_stock ? r.min_stock : '—')}
                      {r.min_stock_percentage ? <span className="ml-1 text-[10px] text-primary/70">({r.min_stock_percentage}%)</span> : null}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">{r.color || readField(r, FIELD.composition) || '—'}</td>
                    <td className="px-4 py-3">{r.active ? <span className="text-emerald-600 dark:text-emerald-300 text-xs font-medium">Aktif</span> : <span className="text-muted-foreground text-xs">Non-aktif</span>}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button onClick={() => openEdit(r)} className="p-1.5 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground" title="Edit" data-testid={`mat-edit-${r.code}`}><Edit2 className="w-3.5 h-3.5" /></button>
                        {r.active && <button onClick={() => remove(r)} className="p-1.5 rounded hover:bg-red-400/10 text-muted-foreground hover:text-red-400" title="Nonaktifkan"><Trash2 className="w-3.5 h-3.5" /></button>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        {pagination && pagination.total_pages > 1 && (
          <div className="px-4 py-3 border-t border-border">
            <PaginationBar pagination={pagination} onPageChange={setPage} />
          </div>
        )}
      </GlassCard>

      {modalOpen && (
        <Modal onClose={() => setModalOpen(false)} title={editing ? `Edit ${editing.code}` : 'Material Baru'} size="md">
          <div className="space-y-3" data-testid="mat-form">
            {formError && <div className="bg-red-400/10 border border-red-300/20 rounded-lg p-3 text-sm text-red-300">{formError}</div>}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Kode <span className="text-red-400">*</span></label>
                <GlassInput value={form.code} onChange={e => setForm({...form, code: e.target.value.toUpperCase()})} placeholder="BHN-KTN30S" data-testid="mat-field-code" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Jenis <span className="text-red-400">*</span></label>
                <select value={typeToCategory(form.type)} onChange={e => { const st = categoryToStoredType(e.target.value); setForm({...form, type: st, unit: isKgLike(st) ? 'kg' : 'pcs'}); }} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="mat-field-type">
                  {CATEGORY_OPTIONS.filter(o => o.value !== 'fg').map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Kategori Material</label>
              <SmartNativeSelect
                value={form.category}
                onChange={e => {
                  const cat = categories.find(c => c.code === e.target.value);
                  setForm({...form, category: e.target.value, category_name: cat ? cat.name : ''});
                }}
                className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="mat-field-category">
                <option value="">— Pilih Kategori —</option>
                {categories.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Nama <span className="text-red-400">*</span></label>
              <GlassInput value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="Kain Katun 30s" data-testid="mat-field-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Unit</label>
                <SmartNativeSelect value={form.unit} onChange={e => setForm({...form, unit: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground">
                  {MATERIAL_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Min Stok (Legacy)</label>
                <GlassInput type="number" step="0.1" value={form.min_stock} onChange={e => setForm({...form, min_stock: e.target.value})} />
              </div>
            </div>

            {/* HARGA SATUAN (HPP) — sejak 2026-08-21 harganya LAHIR DARI PEMBELIAN
                (PO → Penerimaan Barang, rata-rata bergerak), bukan ketikan master.
                Saat membuat barang baru masih boleh diisi sebagai HARGA AWAL karena
                belum ada pembeliannya. */}
            {editing ? (
              <div className="border border-[var(--glass-border)] rounded-lg p-3 space-y-1" data-testid="mat-cost-derived">
                <p className="text-xs font-semibold text-foreground/70 uppercase">Harga Satuan / HPP</p>
                <p className="text-lg font-bold text-foreground tabular-nums" data-testid="mat-cost-value">
                  Rp {Number(form.unit_cost || 0).toLocaleString('id-ID')}
                  <span className="text-xs font-normal text-muted-foreground"> / {form.unit}</span>
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Sumber: <strong>{
                    form.cost_method === 'wac' ? 'rata-rata pembelian (PO → penerimaan)'
                      : form.cost_method === 'manual' ? 'koreksi manual (Valuasi HPP)'
                        : form.cost_method === 'opening' ? 'harga awal saat barang didaftarkan'
                          : 'belum ada pembelian bernilai'
                  }</strong>
                  {form.last_receipt_unit_cost > 0 && (
                    <> · harga beli terakhir Rp {Number(form.last_receipt_unit_cost).toLocaleString('id-ID')}</>
                  )}
                </p>
                <p className="text-[11px] text-amber-600 dark:text-amber-300">
                  Harga tidak diketik di sini. Ia terbentuk otomatis dari harga pembelian di PO saat
                  barang diterima. Koreksi manual (bila salah harga) lewat <strong>Valuasi HPP</strong>
                  agar ada jejak audit.
                </p>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Harga Awal (Rp) — opsional</label>
                <GlassInput type="number" step="1" min="0" value={form.unit_cost}
                  onChange={e => setForm({...form, unit_cost: e.target.value})}
                  placeholder="Cth: 25000" data-testid="mat-field-unit-cost" />
                <p className="text-[11px] text-muted-foreground mt-1">
                  Hanya untuk barang yang sudah ada di gudang sebelum sistem ini. Setelah ada
                  pembelian (PO → penerimaan), harga <strong>otomatis mengikuti harga beli</strong>.
                </p>
              </div>
            )}

            {/* 2026-08-02 · Kain: gramasi & lebar → konversi meter ⇄ kg */}
            {['fabric', 'kain', 'yarn', 'interlining'].includes(form.type) && (
              <div className="border border-primary/20 bg-primary/5 rounded-lg p-3 space-y-2">
                <p className="text-xs font-semibold text-primary uppercase">Data Kain — Konversi Meter ⇄ Kg</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-foreground/70 mb-1">Gramasi / GSM (g/m²)</label>
                    <GlassInput type="number" step="1" min="0" value={form.gsm ?? ''}
                      onChange={e => setForm({ ...form, gsm: e.target.value })}
                      placeholder="Cth: 240" data-testid="mat-field-gsm" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-foreground/70 mb-1">Lebar Kain (cm)</label>
                    <GlassInput type="number" step="0.5" min="0" value={form.width_cm ?? ''}
                      onChange={e => setForm({ ...form, width_cm: e.target.value })}
                      placeholder="Cth: 160" data-testid="mat-field-width" />
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground" data-testid="mat-fabric-conv-hint">
                  {Number(form.gsm) > 0 && Number(form.width_cm) > 0 ? (
                    <>1 meter ≈ <strong>{((Number(form.gsm) * (Number(form.width_cm) / 100)) / 1000).toFixed(4)} kg</strong>
                      {' '}· 1 kg ≈ <strong>{(1 / ((Number(form.gsm) * (Number(form.width_cm) / 100)) / 1000)).toFixed(3)} meter</strong>
                      {' '}— dipakai BOM, RnD/HPP &amp; costing untuk mengubah meter ke kg.</>
                  ) : (
                    <>Isi keduanya agar sistem bisa mengubah pemakaian <strong>meter</strong> menjadi <strong>kg</strong> (kain dibeli per kg).</>
                  )}
                </p>
              </div>
            )}

            {/* Satuan & kemasan berjenjang (maks 3 tingkat) — SSOT lib/uom.js */}
            <UomEditor
              baseUnit={form.unit}
              uoms={form.uoms}
              purchaseUom={form.purchase_uom}
              issueUom={form.issue_uom}
              displayUom={form.display_uom}
              resetKey={editing?.id || 'new'}
              materialId={editing?.id || null}
              token={token}
              onRebased={() => { setModalOpen(false); fetchRows(); }}
              onChange={patch => setForm(f => ({ ...f, ...patch }))}
            />

            {/* Sprint 3.4: Configurable Low Stock Threshold */}
            <div className="border border-amber-300/20 bg-amber-400/5 rounded-lg p-3 space-y-2">
              <p className="text-xs font-semibold text-amber-300 uppercase">Konfigurasi Ambang Low Stock</p>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-foreground/70 mb-1">Min Qty Tetap ({form.unit})</label>
                  <GlassInput type="number" step="0.01" min="0" value={form.min_stock_qty} onChange={e => setForm({...form, min_stock_qty: e.target.value})} placeholder="Cth: 50" data-testid="mat-field-min-qty" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground/70 mb-1">Titik Pesan Ulang ({form.unit})</label>
                  <GlassInput type="number" step="0.01" min="0" value={form.reorder_point} onChange={e => setForm({...form, reorder_point: e.target.value})} placeholder="Cth: 80" data-testid="mat-field-reorder-point" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-foreground/70 mb-1">Min % dari Max Hist</label>
                  <GlassInput type="number" step="1" min="0" max="100" value={form.min_stock_percentage} onChange={e => setForm({...form, min_stock_percentage: e.target.value})} placeholder="Cth: 20" data-testid="mat-field-min-pct" />
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">
                <strong>Min Qty</strong> = stok kritis (di bawah ini → alert merah). <strong>Titik pesan ulang</strong> = saatnya
                order lagi (alert kuning). Untuk mengisi banyak material sekaligus beserta usulannya,
                pakai tab <strong>Ambang Stok</strong>.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Jenis/Komposisi</label>
                <GlassInput value={form.composition || ''} onChange={e => setForm({...form, composition: e.target.value})} placeholder="Acrylic 100%" data-testid="mat-field-composition" />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Warna</label>
                <GlassInput value={form.color} onChange={e => setForm({...form, color: e.target.value})} placeholder="Navy" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Catatan</label>
              <GlassInput value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} placeholder="Opsional" />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setModalOpen(false)} disabled={saving}>Batal</Button>
              <Button onClick={save} disabled={saving} data-testid="mat-save-btn">{saving ? 'Menyimpan...' : 'Simpan'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
