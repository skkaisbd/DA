import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Package, ArrowDown, ArrowRightLeft, AlertTriangle, Scale, Gem, Archive, Clock, MapPin, TriangleAlert, Plus, Minus, RefreshCw } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import Modal from './Modal';
import { DataTable } from './DataTableV2';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { toast } from 'sonner';
import { typeToCategory } from '@/lib/itemTaxonomy';

// Tampilan per 3 kategori bisnis (Bahan/Aksesoris/Produk Jadi).
const CAT_ICON = { bahan: Scale, aksesoris: Gem, fg: Archive };
const CAT_LABEL = { bahan: 'Bahan', aksesoris: 'Aksesoris', fg: 'Produk Jadi' };
const CAT_COLOR = { bahan: 'text-amber-600 dark:text-amber-300', aksesoris: 'text-primary', fg: 'text-emerald-600 dark:text-emerald-300' };

// W1 (sesi #29) — pilihan filter dibangun dari nilai yang BENAR-BENAR ADA di data.
// Daftar hardcode akan menyesatkan (mis. warna yang tidak dipakai satu pun barang),
// dan menghitungnya dari string SKU akan salah — sumbernya master barang.
function uniqOptions(rows, field) {
  const seen = new Set();
  (rows || []).forEach(r => {
    const v = (r?.[field] || '').trim();
    if (v) seen.add(v);
  });
  return [...seen].sort((a, b) => a.localeCompare(b)).map(v => ({ value: v, label: v }));
}

// U7: Check if expiry date is within 30 days
function expiryWarning(expiry_date) {  if (!expiry_date) return null;
  const days = Math.floor((new Date(expiry_date) - new Date()) / 86400000);
  if (days < 0) return { label: 'Kedaluwarsa', cls: 'text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-400/10' };
  if (days <= 30) return { label: `${days}h lagi`, cls: 'text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-400/10' };
  return null;
}

/** Inline Quick Adjust Popover — ±qty tanpa buka modal penuh */
function QuickAdjustPopover({ row, token, onDone }) {
  const [open, setOpen] = useState(false);
  const [delta, setDelta] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const qty = Number(delta);
    if (!qty || qty === 0) { toast.error('Delta qty tidak boleh 0.'); return; }
    setSaving(true);
    try {
      const r = await fetch('/api/rahaza/material-adjust', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          material_id: row.material_id,
          location_id: row.location_id,
          qty_delta: qty,
          notes: notes || (qty > 0 ? 'Quick adjust +' : 'Quick adjust -'),
        }),
      });
      if (r.ok) {
        toast.success(`Stok ${row.material_code} berhasil diupdate ${qty > 0 ? '+' : ''}${qty} ${row.unit}.`);
        setOpen(false); setDelta(''); setNotes('');
        onDone();
      } else {
        const d = await r.json().catch(() => ({}));
        toast.error(d.detail || `Gagal adjust (HTTP ${r.status})`);
      }
    } finally { setSaving(false); }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="h-7 px-2 rounded border border-[var(--glass-border)] bg-[var(--glass-bg)] text-foreground/60 hover:text-primary hover:border-primary/30 hover:bg-primary/8 transition-colors text-xs font-semibold flex items-center gap-1 whitespace-nowrap"
          data-testid={`stock-adjust-btn-${row.material_code}`}
          title="Quick adjust stok ±"
        >
          <Plus className="w-3 h-3" />/<Minus className="w-3 h-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-3" align="end">
        <p className="text-xs font-semibold text-foreground mb-2">Adjust Stok</p>
        <p className="text-[10px] text-muted-foreground mb-2">{row.material_code} · {row.location_code} · Stok: <span className="font-mono font-semibold text-foreground">{Number(row.qty).toFixed(2)} {row.unit}</span></p>
        <div className="space-y-2">
          <div>
            <label className="text-[10px] text-muted-foreground uppercase mb-1 block">Delta Qty (+/-)</label>
            <GlassInput
              type="number"
              step="0.001"
              placeholder="+10 atau -5"
              value={delta}
              onChange={e => setDelta(e.target.value)}
              className="h-8 text-xs font-mono"
              autoFocus
              data-testid={`stock-adjust-delta-${row.material_code}`}
            />
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground uppercase mb-1 block">Catatan</label>
            <GlassInput
              placeholder="Alasan (opsional)"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              className="h-8 text-xs"
              data-testid={`stock-adjust-notes-${row.material_code}`}
            />
          </div>
          <div className="flex gap-1.5 pt-1">
            <button
              onClick={() => { setOpen(false); setDelta(''); setNotes(''); }}
              className="flex-1 h-7 text-xs rounded border border-[var(--glass-border)] text-muted-foreground hover:text-foreground"
            >Batal</button>
            <button
              onClick={submit}
              disabled={saving || !delta}
              className="flex-1 h-7 text-xs rounded border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors font-semibold disabled:opacity-50"
              data-testid={`stock-adjust-submit-${row.material_code}`}
            >
              {saving ? <RefreshCw className="w-3 h-3 animate-spin mx-auto" /> : 'Simpan'}
            </button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default function RahazaStockModule({ token }) {
  const [stocks, setStocks] = useState([]);
  const [summary, setSummary] = useState(null);
  const [movements, setMovements] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [locations, setLocations] = useState([]);
  const [reorderAlerts, setReorderAlerts] = useState([]);
  const [filterLocation, setFilterLocation] = useState('');  // U5
  // W1 (sesi #29) — saklar "tampilkan juga yang stoknya 0". Layar ini menampilkan
  // BARIS STOK, dan hanya ±26 dari 321 barang jadi punya baris stok ⇒ daftarnya
  // tampak "tidak sinkron" dengan Master Item Produk Jadi. Dengan saklar ini
  // barang master yang belum pernah punya stok ikut tampil (qty 0).
  const [showZero, setShowZero] = useState(false);
  const [loading, setLoading] = useState(true);
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [receiveForm, setReceiveForm] = useState({ material_id: '', location_id: '', qty: '', notes: '' });
  const [transferForm, setTransferForm] = useState({ material_id: '', from_location_id: '', to_location_id: '', qty: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [stkRes, sumRes, mvRes, reorderRes] = await Promise.all([
        fetch(`/api/rahaza/material-stock${showZero ? '?include_zero=1' : ''}`, { headers }).then(r => r.ok ? r.json() : []),
        fetch('/api/rahaza/material-stock/summary', { headers }).then(r => r.ok ? r.json() : null),
        fetch('/api/rahaza/material-movements?limit=30', { headers }).then(r => r.ok ? r.json() : []),
        fetch('/api/rahaza/materials/reorder-alerts', { headers }).then(r => r.ok ? r.json() : []),
      ]);
      // Ensure each stock row has a stable unique key (id may be missing in some seed rows).
      const normalizedStocks = (Array.isArray(stkRes) ? stkRes : []).map((s, i) => ({
        ...s,
        _key: s.id || `${s.material_id || 'm'}-${s.location_id || 'l'}-${i}`,
      }));
      setStocks(normalizedStocks); setSummary(sumRes); setMovements(mvRes); setReorderAlerts(reorderRes);
    } finally { setLoading(false); }
  }, [token, showZero]);

  useEffect(() => {
    const h = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch('/api/rahaza/materials', { headers: h }).then(r => r.ok ? r.json() : []),
      // FASE C: sumber lokasi = daftar STORAGE terpadu (zona kanonik wh_* + legacy storage
      // yang belum termigrasi). Zona produksi (cutting/sewing/qc/packing) TIDAK muncul.
      fetch('/api/rahaza/storage-locations', { headers: h }).then(r => r.ok ? r.json() : []),
    ]).then(([m, l]) => { setMaterials((m || []).filter(x => x.active)); setLocations(Array.isArray(l) ? l : []); });
  }, [token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Fase C: filter lokasi = lokasi yang benar-benar punya stok. Nama/kode diambil dari
  // baris stok (sudah di-resolve backend lintas skema: rahaza_locations LAMA + wh_* BARU),
  // fallback ke daftar storage. Form receive/transfer/adjust pakai daftar storage terpadu.
  const locById = Object.fromEntries(locations.map(l => [l.id, l]));
  const stockLocMeta = {};
  stocks.forEach(s => {
    if (s.location_id && !stockLocMeta[s.location_id]) {
      stockLocMeta[s.location_id] = {
        code: s.location_code || locById[s.location_id]?.code || String(s.location_id).slice(0, 12),
        name: s.location_name || locById[s.location_id]?.name || '',
      };
    }
  });
  const stockFilterLocations = Object.entries(stockLocMeta)
    .map(([id, meta]) => ({ id, ...meta }))
    .sort((a, b) => a.code.localeCompare(b.code));

  const openReceive = () => { setReceiveForm({ material_id: '', location_id: '', qty: '', notes: '' }); setFormError(''); setReceiveOpen(true); };
  const openTransfer = () => { setTransferForm({ material_id: '', from_location_id: '', to_location_id: '', qty: '', notes: '' }); setFormError(''); setTransferOpen(true); };

  const doReceive = async () => {
    setSaving(true); setFormError('');
    try {
      if (!receiveForm.material_id || !receiveForm.location_id || !(Number(receiveForm.qty) > 0)) throw new Error('Pilih material, lokasi, dan isi qty > 0.');
      const r = await fetch('/api/rahaza/material-receive', { method: 'POST', headers, body: JSON.stringify({ ...receiveForm, qty: Number(receiveForm.qty) }) });
      if (!r.ok) {
        const STATUS_MSG = { 400: 'Data tidak valid.', 403: 'Tidak ada akses.', 404: 'Material/Lokasi tidak ditemukan.' };
        throw new Error(STATUS_MSG[r.status] || `Gagal simpan (HTTP ${r.status})`);
      }
      setReceiveOpen(false); fetchAll();
    } catch (e) { setFormError(e.message); }
    finally { setSaving(false); }
  };

  const doTransfer = async () => {
    setSaving(true); setFormError('');
    try {
      if (!transferForm.material_id || !transferForm.from_location_id || !transferForm.to_location_id) throw new Error('Lengkapi material & kedua lokasi.');
      if (transferForm.from_location_id === transferForm.to_location_id) throw new Error('Lokasi asal dan tujuan tidak boleh sama.');
      if (!(Number(transferForm.qty) > 0)) throw new Error('Qty harus > 0.');
      const r = await fetch('/api/rahaza/material-transfer', { method: 'POST', headers, body: JSON.stringify({ ...transferForm, qty: Number(transferForm.qty) }) });
      if (!r.ok) {
        const STATUS_MSG = { 400: 'Data tidak valid / stok kurang.', 403: 'Tidak ada akses.' };
        throw new Error(STATUS_MSG[r.status] || `Gagal transfer (HTTP ${r.status})`);
      }
      setTransferOpen(false); fetchAll();
    } catch (e) { setFormError(e.message); }
    finally { setSaving(false); }
  };

  if (loading) return (<div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" /></div>);

  return (
    <div className="space-y-5" data-testid="rahaza-stock-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Stok Material</h1>
          <p className="text-muted-foreground text-sm mt-1">Stok bahan, aksesoris, dan produk jadi per Gedung / Zona. Transfer A↔B dan penerimaan dicatat di ledger.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={openTransfer} className="border border-[var(--glass-border)]" data-testid="stock-transfer-btn"><ArrowRightLeft className="w-4 h-4 mr-1.5" /> Transfer A↔B</Button>
          <Button onClick={openReceive} data-testid="stock-receive-btn"><ArrowDown className="w-4 h-4 mr-1.5" /> Penerimaan</Button>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {['bahan', 'aksesoris', 'fg'].map(t => {
            const Icon = CAT_ICON[t] || Package;
            const s = summary.by_category?.[t] || {};
            return (
              <GlassPanel key={t} className="p-3" data-testid={`stock-summary-${t}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Icon className={`w-4 h-4 ${CAT_COLOR[t]}`} />
                  <span className="text-xs font-semibold text-muted-foreground uppercase">{CAT_LABEL[t]}</span>
                </div>
                <div className="text-xl font-bold text-foreground">{Number(s.total_qty || 0).toFixed(t === 'bahan' ? 2 : 0)}</div>
                <div className="text-[10px] text-muted-foreground">{s.row_count || 0} baris stok</div>
              </GlassPanel>
            );
          })}
          <GlassPanel className={`p-3 ${summary.low_stock_count > 0 ? 'border-amber-400 dark:border-amber-300/30' : ''}`}>
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className={`w-4 h-4 ${summary.low_stock_count > 0 ? 'text-amber-600 dark:text-amber-300' : 'text-foreground/30'}`} />
              <span className="text-xs font-semibold text-muted-foreground uppercase">Low Stock</span>
            </div>
            <div className={`text-xl font-bold ${summary.low_stock_count > 0 ? 'text-amber-600 dark:text-amber-300' : 'text-foreground'}`}>{summary.low_stock_count}</div>
            <div className="text-[10px] text-muted-foreground">material di bawah min</div>
          </GlassPanel>
        </div>
      )}

      {/* U8 — Reorder Alert Banner */}
      {reorderAlerts.length > 0 && (
        <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20 rounded-xl p-3 flex items-start gap-2" data-testid="reorder-alert-banner">
          <TriangleAlert size={15} className="text-amber-700 dark:text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="text-sm font-semibold text-amber-600 dark:text-amber-300">{reorderAlerts.length} material perlu reorder</span>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {reorderAlerts.map(a => (
                <span key={a.id} className="text-[10px] bg-amber-100 dark:bg-amber-500/20 text-amber-200 px-2 py-0.5 rounded-full border border-amber-300 dark:border-amber-400/20">
                  {a.code} — butuh {a.shortage} {a.unit}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* U5 — Location filter bar + W1 saklar "tampilkan stok 0" */}
      <div className="flex items-center gap-2 flex-wrap">
        <MapPin size={14} className="text-foreground/40 flex-shrink-0" />
        <span className="text-xs text-foreground/40">Filter lokasi:</span>
        <button
          onClick={() => setFilterLocation('')}
          className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${filterLocation === '' ? 'bg-foreground/[0.15] border-foreground/30 text-foreground' : 'bg-foreground/5 border-foreground/10 text-foreground/50 hover:bg-foreground/10'}`}
        >
          Semua
        </button>
        {stockFilterLocations.map(l => (
          <button
            key={l.id}
            onClick={() => setFilterLocation(filterLocation === l.id ? '' : l.id)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${filterLocation === l.id ? 'bg-cyan-100 dark:bg-cyan-500/25 border-cyan-400/40 text-cyan-600 dark:text-cyan-300' : 'bg-foreground/5 border-foreground/10 text-foreground/50 hover:bg-foreground/10'}`}
            data-testid={`stock-loc-filter-${l.code}`}
            title={l.name || l.code}
          >
            {l.code}
          </button>
        ))}
        {stockFilterLocations.length === 0 && (
          <span className="text-xs text-foreground/30 italic">belum ada stok berlokasi</span>
        )}
        <label
          className="ml-auto flex items-center gap-2 text-xs text-foreground/70 cursor-pointer select-none"
          title="Barang master yang belum punya baris stok ikut ditampilkan dengan qty 0 — supaya daftar bisa disamakan dengan Master Item Produk Jadi."
        >
          <input
            type="checkbox"
            checked={showZero}
            onChange={e => setShowZero(e.target.checked)}
            className="h-3.5 w-3.5 accent-[hsl(var(--primary))] cursor-pointer"
            data-testid="stock-show-zero-toggle"
          />
          Tampilkan juga yang stoknya 0
          {showZero && (
            <span className="text-[10px] text-foreground/50" data-testid="stock-zero-count">
              ({stocks.filter(s => s.no_stock_row).length} barang belum punya stok)
            </span>
          )}
        </label>
      </div>

      {/* Stock table — DataTable v2 */}
      <DataTable
        tableId="stock"
        loading={loading}
        rowKey="_key"
        rows={filterLocation ? stocks.filter(s => s.location_id === filterLocation) : stocks}
        searchFields={['material_code', 'material_name', 'location_code', 'location_name',
                       'category_name', 'color_name', 'option_name', 'size_code']}
        filters={[
          { key: 'material_type', label: 'Jenis', type: 'select',
            accessor: (r) => typeToCategory(r.material_type),
            options: [
              { value: 'bahan', label: 'Bahan' },
              { value: 'aksesoris', label: 'Aksesoris' },
              { value: 'fg', label: 'Produk Jadi' },
            ] },
          // W1 — filter identitas barang. Pilihannya dibangun dari data yang benar-benar
          // ada (bukan daftar hardcode) supaya tidak ada opsi kosong yang menyesatkan.
          { key: 'category_name', label: 'Kategori', type: 'select',
            accessor: (r) => r.category_name || '—',
            options: uniqOptions(stocks, 'category_name') },
          { key: 'color_name', label: 'Warna', type: 'select',
            accessor: (r) => r.color_name || '—',
            options: uniqOptions(stocks, 'color_name') },
          { key: 'option_name', label: 'Opsi', type: 'select',
            accessor: (r) => r.option_name || '—',
            options: uniqOptions(stocks, 'option_name') },
          { key: 'status', label: 'Status', type: 'select',
            accessor: (r) => r.below_min ? 'low' : 'ok',
            options: [
              { value: 'ok', label: 'OK' },
              { value: 'low', label: 'Low Stock' },
            ] },
        ]}
        columns={[
          { key: 'material_code', label: 'Barang', sortable: true,
            render: (r) => (
              <div>
                <div className="font-mono text-xs">{r.material_code}</div>
                <div className="text-[11px] text-foreground/60">{r.material_name}</div>
              </div>
            ) },
          { key: 'category_name', label: 'Kategori', sortable: true,
            accessor: (r) => r.category_name || '',
            render: (r) => <span className="text-foreground/80 text-xs">{r.category_name || '—'}</span> },
          { key: 'color_name', label: 'Warna', sortable: true,
            accessor: (r) => r.color_name || '',
            render: (r) => (
              <span className="text-foreground/80 text-xs">
                {r.color_name || '—'}
                {r.size_code ? <span className="text-foreground/40"> · {r.size_code}</span> : null}
              </span>
            ) },
          { key: 'option_name', label: 'Opsi', sortable: true,
            accessor: (r) => r.option_name || '',
            render: (r) => <span className="text-foreground/70 text-xs">{r.option_name || '—'}</span> },
          { key: 'material_type', label: 'Jenis', sortable: true,
            render: (r) => <span className={`text-xs ${CAT_COLOR[typeToCategory(r.material_type)]}`}>{CAT_LABEL[typeToCategory(r.material_type)]}</span> },
          { key: 'location', label: 'Lokasi', sortable: true,
            accessor: (r) => r.location_code ? `${r.location_code} · ${r.location_name || ''}` : '',
            render: (r) => r.location_code
              ? <span className="text-foreground/70">{r.location_code} · {r.location_name}</span>
              : <span className="text-foreground/40 italic text-xs">belum ada baris stok</span> },
          { key: 'qty', label: 'Qty', align: 'right', sortable: true,
            render: (r) => <span className="font-mono font-semibold">{Number(r.qty).toFixed(r.unit === 'kg' ? 3 : 2)} <span className="text-foreground/60 text-xs">{r.unit}</span></span> },
          { key: 'min_stock', label: 'Min Stok', align: 'right', sortable: true,
            render: (r) => <span className="text-foreground/60">{r.min_stock_qty || r.min_stock || '—'}</span> },
          { key: 'status', label: 'Status',
            accessor: (r) => r.below_min ? 'low' : 'ok',
            render: (r) => r.below_min
              ? <span className="text-[hsl(var(--warning))] text-xs font-medium">Low</span>
              : <span className="text-[hsl(var(--success))] text-xs font-medium">OK</span> },
          { key: '_adjust', label: 'Adjust', align: 'right',
            render: (r) => (
              // Baris tanpa lokasi (belum punya baris stok) tidak bisa di-adjust:
              // penyesuaian WAJIB menyebut lokasi. Pakai "Penerimaan" untuk memulai.
              r.location_id
                ? <QuickAdjustPopover row={r} token={token} onDone={fetchAll} />
                : <span className="text-[10px] text-foreground/40">pakai Penerimaan</span>
            ) },
        ]}
        emptyTitle="Belum ada stok"
        emptyDescription='Mulai dari "Penerimaan" untuk menambah stok ke lokasi.'
        emptyIcon={Package}
        exportFilename={`material-stock-${new Date().toISOString().slice(0,10)}.csv`}
      />

      {/* Movements ledger */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="px-4 py-2 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">Movement Ledger (30 terakhir)</span>
        </div>
        <div className="overflow-x-auto max-h-80">
          <table className="w-full text-xs">
            <thead className="bg-[var(--glass-bg)] sticky top-0">
              <tr className="text-left text-[10px] text-muted-foreground">
                <th className="px-3 py-2">Waktu</th>
                <th className="px-3 py-2">Tipe</th>
                <th className="px-3 py-2">Material</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2">Dari</th>
                <th className="px-3 py-2">Ke</th>
                <th className="px-3 py-2">Ref</th>
              </tr>
            </thead>
            <tbody>
              {movements.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-6 text-muted-foreground">Belum ada movement.</td></tr>
              ) : movements.map((m, idx) => (
                <tr key={m.id || `mv-${idx}`} className="border-t border-[var(--glass-border)]">
                  <td className="px-3 py-1.5 text-muted-foreground whitespace-nowrap">{new Date(m.timestamp).toLocaleString('id-ID', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                  <td className="px-3 py-1.5">
                    {m.type === 'receive'  && <span className="text-emerald-600 dark:text-emerald-300">Receive</span>}
                    {m.type === 'issue'    && <span className="text-red-600 dark:text-red-300">Issue</span>}
                    {m.type === 'transfer' && <span className="text-primary">Transfer</span>}
                    {m.type === 'adjust'   && <span className="text-amber-600 dark:text-amber-300">Adjust</span>}
                  </td>
                  <td className="px-3 py-1.5 text-foreground">{m.material_code}</td>
                  <td className="px-3 py-1.5 text-right font-mono font-semibold text-foreground">{Number(m.qty).toFixed(3)} {m.unit || ''}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{m.from_location_name || '—'}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{m.to_location_name || '—'}</td>
                  <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[160px]">{m.notes || m.ref_type || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Receive modal */}
      {receiveOpen && (
        <Modal onClose={() => setReceiveOpen(false)} title="Penerimaan Material" size="md">
          <div className="space-y-3" data-testid="receive-form">
            {formError && <div className="bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-300/20 rounded-lg p-3 text-sm text-red-600 dark:text-red-300">{formError}</div>}
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Material <span className="text-red-700 dark:text-red-400">*</span></label>
              <SmartNativeSelect value={receiveForm.material_id} onChange={e => setReceiveForm({...receiveForm, material_id: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="receive-material">
                <option value="">— Pilih —</option>
                {materials.map(m => <option key={m.id} value={m.id}>{`${m.code} · ${m.name} (${m.unit})`}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Lokasi Tujuan <span className="text-red-700 dark:text-red-400">*</span></label>
              <SmartNativeSelect value={receiveForm.location_id} onChange={e => setReceiveForm({...receiveForm, location_id: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="receive-location">
                <option value="">— Pilih —</option>
                {locations.map(l => <option key={l.id} value={l.id}>{`${l.code} · ${l.name}`}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Qty <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput type="number" step="0.001" value={receiveForm.qty} onChange={e => setReceiveForm({...receiveForm, qty: e.target.value})} placeholder="0" data-testid="receive-qty" />
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Catatan</label>
              <GlassInput value={receiveForm.notes} onChange={e => setReceiveForm({...receiveForm, notes: e.target.value})} placeholder="No. surat jalan, supplier, dsb" />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setReceiveOpen(false)} disabled={saving}>Batal</Button>
              <Button onClick={doReceive} disabled={saving} data-testid="receive-submit">{saving ? 'Menyimpan...' : 'Simpan Penerimaan'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Transfer modal */}
      {transferOpen && (
        <Modal onClose={() => setTransferOpen(false)} title="Transfer Antar Gudang" size="md">
          <div className="space-y-3" data-testid="transfer-form">
            {formError && <div className="bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-300/20 rounded-lg p-3 text-sm text-red-600 dark:text-red-300">{formError}</div>}
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Material <span className="text-red-700 dark:text-red-400">*</span></label>
              <SmartNativeSelect value={transferForm.material_id} onChange={e => setTransferForm({...transferForm, material_id: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="transfer-material">
                <option value="">— Pilih —</option>
                {materials.map(m => <option key={m.id} value={m.id}>{`${m.code} · ${m.name} (${m.unit})`}</option>)}
              </SmartNativeSelect>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Dari Lokasi <span className="text-red-700 dark:text-red-400">*</span></label>
                <SmartNativeSelect value={transferForm.from_location_id} onChange={e => setTransferForm({...transferForm, from_location_id: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="transfer-from">
                  <option value="">—</option>
                  {locations.map(l => <option key={l.id} value={l.id}>{l.code}</option>)}
                </SmartNativeSelect>
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground/70 mb-1">Ke Lokasi <span className="text-red-700 dark:text-red-400">*</span></label>
                <SmartNativeSelect value={transferForm.to_location_id} onChange={e => setTransferForm({...transferForm, to_location_id: e.target.value})} className="w-full h-10 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground" data-testid="transfer-to">
                  <option value="">—</option>
                  {locations.map(l => <option key={l.id} value={l.id}>{l.code}</option>)}
                </SmartNativeSelect>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Qty <span className="text-red-700 dark:text-red-400">*</span></label>
              <GlassInput type="number" step="0.001" value={transferForm.qty} onChange={e => setTransferForm({...transferForm, qty: e.target.value})} placeholder="0" data-testid="transfer-qty" />
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground/70 mb-1">Catatan</label>
              <GlassInput value={transferForm.notes} onChange={e => setTransferForm({...transferForm, notes: e.target.value})} placeholder="Opsional" />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setTransferOpen(false)} disabled={saving}>Batal</Button>
              <Button onClick={doTransfer} disabled={saving} data-testid="transfer-submit">{saving ? 'Menyimpan...' : 'Konfirmasi Transfer'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
