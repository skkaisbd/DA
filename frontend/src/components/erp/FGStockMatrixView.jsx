import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Grid3X3, Layers, Package, RefreshCw, Search, X, MinusCircle,
  Lock, CheckCircle2, AlertCircle, ChevronDown, ChevronRight,
  Activity, ArrowUpCircle, ArrowDownCircle, Calendar, Tag, Sparkles,
} from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';

// Color palette for visual color mapping in cells
const COLOR_DOT = {
  BLACK:  'bg-card ring-border',
  WHITE:  'bg-white ring-border',
  GRAY:   'bg-muted ring-border',
  NAVY:   'bg-blue-900 ring-blue-700',
  BLUE:   'bg-blue-500 ring-blue-400',
  RED:    'bg-red-500 ring-red-400',
  GREEN:  'bg-emerald-500 ring-emerald-400',
  YELLOW: 'bg-amber-400 ring-amber-300',
  PURPLE: 'bg-purple-500 ring-purple-400',
  PINK:   'bg-pink-400 ring-pink-300',
  BROWN:  'bg-amber-800 ring-amber-700',
  ORANGE: 'bg-orange-500 ring-orange-400',
};

function colorDotClass(color) {
  return COLOR_DOT[(color || '').toUpperCase()] || 'bg-gradient-to-br from-zinc-400 to-zinc-600 ring-border';
}

/**
 * FG Stock Matrix viewer — pivots inventory by Model × Color (rows) × Size (columns).
 * Interactive: cell click opens detail panel with allocate/issue actions.
 */
export default function FGStockMatrixView({ token, onCellAction }) {
  const { toast } = useToast();
  const [matrix, setMatrix] = useState({ summary: {}, size_order: [], models: [] });
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterModel, setFilterModel] = useState('all');
  const [onlyWithStock, setOnlyWithStock] = useState(true);
  const [collapsedModels, setCollapsedModels] = useState({});
  const [detailCell, setDetailCell] = useState(null); // { material_id, code, ... }
  const [actionMode, setActionMode] = useState(null); // 'allocate' | 'issue' | null
  const [actionQty, setActionQty] = useState('');
  const [actionRef, setActionRef] = useState('');
  const [actionNotes, setActionNotes] = useState('');
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [detailData, setDetailData] = useState(null);

  const h = useMemo(() => ({
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }), [token]);

  const fetchMatrix = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (onlyWithStock) params.set('only_with_stock', 'true');
      if (filterModel && filterModel !== 'all') params.set('model', filterModel);

      const [mRes, modelsRes] = await Promise.all([
        fetch(`/api/rahaza/fg-matrix?${params}`, { headers: h }),
        fetch('/api/rahaza/fg-matrix/models', { headers: h }),
      ]);
      if (mRes.ok) {
        const data = await mRes.json();
        setMatrix(data);
      }
      if (modelsRes.ok) setModels(await modelsRes.json());
    } catch (e) {
      toast({ title: 'Gagal memuat matrix', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [h, onlyWithStock, filterModel, toast]);

  useEffect(() => { fetchMatrix(); }, [fetchMatrix]);

  const fetchCellDetail = useCallback(async (materialId) => {
    try {
      const res = await fetch(`/api/rahaza/fg-matrix/cell-detail/${materialId}`, { headers: h });
      if (res.ok) setDetailData(await res.json());
    } catch (e) {
      console.error(e);
    }
  }, [h]);

  const openCell = (cell, modelKey) => {
    setDetailCell({ ...cell, model_key: modelKey });
    setActionMode(null);
    setActionQty('');
    setActionRef('');
    setActionNotes('');
    setDetailData(null);
    if (cell.material_id) fetchCellDetail(cell.material_id);
  };

  const closeDetail = () => {
    setDetailCell(null);
    setActionMode(null);
  };

  const handleAllocate = async () => {
    if (!detailCell?.material_id) return;
    const qty = parseInt(actionQty, 10);
    if (!qty || qty <= 0) return toast({ title: 'Qty harus > 0', variant: 'destructive' });
    if (qty > detailCell.available) return toast({ title: `Maksimal: ${detailCell.available} pcs`, variant: 'destructive' });

    setActionSubmitting(true);
    try {
      const res = await fetch('/api/rahaza/fg-matrix/allocate', {
        method: 'POST',
        headers: h,
        body: JSON.stringify({
          material_id: detailCell.material_id,
          qty,
          reference_type: 'manual',
          reference_label: actionRef || `Allocation for ${detailCell.code}`,
          notes: actionNotes,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Allocate failed');
      toast({ title: `✅ Direservasi ${qty} pcs — ${data.reservation_no}` });
      setActionMode(null);
      setActionQty('');
      setActionRef('');
      setActionNotes('');
      fetchMatrix();
      fetchCellDetail(detailCell.material_id);
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    } finally {
      setActionSubmitting(false);
    }
  };

  const handleRelease = async (reservationId) => {
    try {
      const res = await fetch(`/api/rahaza/fg-matrix/release/${reservationId}`, {
        method: 'POST', headers: h,
      });
      if (!res.ok) throw new Error('Release failed');
      toast({ title: '✅ Reservasi dilepas' });
      fetchMatrix();
      if (detailCell?.material_id) fetchCellDetail(detailCell.material_id);
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    }
  };

  const handleSeedDemo = async () => {
    try {
      const res = await fetch('/api/rahaza/fg-matrix/seed-demo', { method: 'POST', headers: h });
      const data = await res.json();
      if (data.status === 'seeded') {
        toast({ title: `✅ Demo data seeded: ${data.materials_inserted} SKUs` });
      } else {
        toast({ title: 'Demo data sudah ada' });
      }
      fetchMatrix();
    } catch (e) {
      toast({ title: e.message, variant: 'destructive' });
    }
  };

  const toggleModel = (key) => setCollapsedModels(s => ({ ...s, [key]: !s[key] }));

  const filteredModels = useMemo(() => {
    if (!search) return matrix.models;
    const q = search.toLowerCase();
    return matrix.models.filter(m =>
      m.model_key.toLowerCase().includes(q) ||
      m.colors.some(c => c.toLowerCase().includes(q)) ||
      Object.values(m.cells).some(row =>
        Object.values(row).some(cell => (cell.code || '').toLowerCase().includes(q) || (cell.name || '').toLowerCase().includes(q))
      )
    );
  }, [matrix.models, search]);

  // Heatmap intensity helper — returns Tailwind classes based on qty
  const cellIntensity = (qty, max) => {
    if (qty <= 0) return 'bg-card/40 text-muted-foreground/40 border-border/30';
    const ratio = max > 0 ? qty / max : 0;
    if (ratio < 0.25) return 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-500/30';
    if (ratio < 0.5)  return 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-200 border-emerald-500/40';
    if (ratio < 0.75) return 'bg-emerald-500/30 text-emerald-100 border-emerald-400/50';
    return 'bg-emerald-500/40 text-foreground border-emerald-400/60';
  };

  return (
    <div className="space-y-4" data-testid="fg-matrix-view">
      {/* Toolbar */}
      <GlassPanel className="p-3 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <GlassInput
            placeholder="Cari model / warna / SKU…"
            className="pl-8 h-8 text-sm"
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="fg-matrix-search"
          />
        </div>
        <Select value={filterModel} onValueChange={setFilterModel}>
          <SelectTrigger className="w-40 h-8 text-xs" data-testid="fg-matrix-model-filter">
            <SelectValue placeholder="Semua model" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua model</SelectItem>
            {models.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={onlyWithStock}
            onChange={e => setOnlyWithStock(e.target.checked)}
            className="accent-primary"
            data-testid="fg-matrix-stock-toggle"
          />
          Hanya yang ada stok
        </label>
        <Button size="sm" variant="ghost" onClick={fetchMatrix} className="gap-1.5 text-xs ml-auto">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
        {matrix.models.length === 0 && (
          <Button size="sm" variant="outline" onClick={handleSeedDemo} className="gap-1.5 text-xs" data-testid="fg-matrix-seed-btn">
            <Sparkles className="w-3.5 h-3.5" />
            Seed Demo
          </Button>
        )}
      </GlassPanel>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total Model</div>
          <div className="text-xl font-bold text-foreground">{matrix.summary?.total_models || 0}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total SKU</div>
          <div className="text-xl font-bold text-foreground">{matrix.summary?.total_skus || 0}</div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Total Qty</div>
          <div className="text-xl font-bold text-primary">
            {Number(matrix.summary?.total_qty || 0).toLocaleString('id-ID')}
            <span className="text-xs text-muted-foreground ml-1">pcs</span>
          </div>
        </GlassPanel>
        <GlassPanel className="p-3 text-center">
          <div className="text-[10px] text-muted-foreground uppercase mb-1">Size Range</div>
          <div className="text-xl font-bold text-foreground">
            {(matrix.size_order || []).slice(0, 6).filter(s => s.length <= 4).join(' · ') || '—'}
          </div>
        </GlassPanel>
      </div>

      {/* Loading / Empty states */}
      {loading && (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      )}
      {!loading && filteredModels.length === 0 && (
        <GlassCard className="p-12 text-center" hover={false}>
          <Package className="w-12 h-12 mx-auto text-muted-foreground/30 mb-3" />
          <p className="text-sm text-muted-foreground mb-1">
            {matrix.models.length === 0 ? 'Belum ada data FG.' : 'Tidak ada model yang cocok dengan filter.'}
          </p>
          {matrix.models.length === 0 && (
            <p className="text-xs text-muted-foreground/60">
              Klik tombol <span className="font-semibold">Seed Demo</span> untuk melihat tampilan matrix dengan data contoh.
            </p>
          )}
        </GlassCard>
      )}

      {/* Matrix rendered per model */}
      {!loading && filteredModels.map(model => {
        const isCollapsed = collapsedModels[model.model_key];
        // Compute max qty within this model's cells for heatmap intensity
        let maxQty = 0;
        Object.values(model.cells).forEach(row => Object.values(row).forEach(c => { if (c.qty > maxQty) maxQty = c.qty; }));

        return (
          <GlassCard key={model.model_key} className="p-0 overflow-hidden" data-testid={`fg-matrix-model-${model.model_key}`}>
            {/* Header */}
            <button
              type="button"
              onClick={() => toggleModel(model.model_key)}
              className="w-full px-4 py-3 flex items-center gap-3 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors text-left"
            >
              {isCollapsed ? <ChevronRight className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
              <Layers className="w-4 h-4 text-primary" />
              <div className="flex-1">
                <div className="font-semibold text-foreground text-sm flex items-center gap-2">
                  {model.model_key}
                  <Badge variant="outline" className="text-[10px] text-muted-foreground border-[var(--glass-border)]">
                    {model.sku_count} SKU
                  </Badge>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {model.colors.length} warna × {model.sizes.length} size — total{' '}
                  <span className="text-primary font-bold">{model.total_qty.toLocaleString('id-ID')}</span>{' '}
                  <span className="text-muted-foreground/70">pcs</span>
                  {model.total_available !== model.total_qty && (
                    <span className="ml-2 text-amber-700 dark:text-amber-400">({model.total_available} tersedia)</span>
                  )}
                </div>
              </div>
              <div className="hidden md:flex items-center gap-1">
                {model.colors.slice(0, 5).map(c => (
                  <div key={c} className={`w-3 h-3 rounded-full ring-1 ${colorDotClass(c)}`} title={c} />
                ))}
                {model.colors.length > 5 && (
                  <span className="text-[10px] text-muted-foreground ml-1">+{model.colors.length - 5}</span>
                )}
              </div>
            </button>

            {/* Matrix Grid */}
            {!isCollapsed && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[11px] text-muted-foreground bg-[var(--glass-bg)]/50">
                      <th className="px-3 py-2 text-left font-medium sticky left-0 bg-[var(--glass-bg)] z-10 min-w-[140px]">
                        <span className="flex items-center gap-1.5">
                          <Tag className="w-3 h-3" /> Warna \ Size
                        </span>
                      </th>
                      {model.sizes.map(size => (
                        <th key={size} className="px-2 py-2 text-center font-mono font-semibold text-foreground min-w-[80px]">
                          {size}
                        </th>
                      ))}
                      <th className="px-3 py-2 text-right font-medium text-foreground/80">
                        Subtotal
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.colors.map(color => {
                      const row = model.cells[color] || {};
                      const subtotal = Object.values(row).reduce((a, c) => a + (c.qty || 0), 0);
                      return (
                        <tr key={color} className="border-t border-[var(--glass-border)]">
                          <td className="px-3 py-2 sticky left-0 bg-[var(--bg)]/95 backdrop-blur-sm z-10">
                            <div className="flex items-center gap-2">
                              <div className={`w-3.5 h-3.5 rounded-full ring-1 ring-offset-1 ring-offset-transparent ${colorDotClass(color)}`} />
                              <span className="text-xs font-medium text-foreground">{color}</span>
                            </div>
                          </td>
                          {model.sizes.map(size => {
                            const cell = row[size];
                            if (!cell) {
                              return (
                                <td key={size} className="px-2 py-2 text-center">
                                  <span className="inline-block w-full text-[11px] text-muted-foreground/30">—</span>
                                </td>
                              );
                            }
                            const cls = cellIntensity(cell.qty, maxQty);
                            return (
                              <td key={size} className="px-1.5 py-1.5 text-center">
                                <button
                                  type="button"
                                  onClick={() => openCell(cell, model.model_key)}
                                  className={`w-full px-2 py-1.5 rounded-md border ${cls} transition-all hover:scale-[1.03] hover:brightness-110 active:scale-[0.98] cursor-pointer`}
                                  data-testid={`fg-matrix-cell-${cell.code}`}
                                  title={`${cell.code}\n${cell.name}\nQty: ${cell.qty} | Reserved: ${cell.reserved} | Available: ${cell.available}`}
                                >
                                  <div className="text-sm font-bold leading-tight">{cell.qty}</div>
                                  {cell.reserved > 0 && (
                                    <div className="text-[9px] mt-0.5 opacity-80 flex items-center justify-center gap-0.5">
                                      <Lock className="w-2 h-2" />
                                      {cell.reserved}
                                    </div>
                                  )}
                                </button>
                              </td>
                            );
                          })}
                          <td className="px-3 py-2 text-right font-bold text-primary">
                            {subtotal.toLocaleString('id-ID')}
                          </td>
                        </tr>
                      );
                    })}
                    {/* Per-size totals row */}
                    <tr className="border-t-2 border-[var(--glass-border)] bg-[var(--glass-bg)]/30">
                      <td className="px-3 py-2 sticky left-0 bg-[var(--glass-bg)] z-10 text-xs font-semibold text-muted-foreground">
                        Total per Size
                      </td>
                      {model.sizes.map(size => {
                        const total = model.colors.reduce((a, c) => a + (model.cells[c]?.[size]?.qty || 0), 0);
                        return (
                          <td key={size} className="px-2 py-2 text-center text-xs font-bold text-foreground/90">
                            {total.toLocaleString('id-ID')}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2 text-right font-bold text-primary text-base">
                        {model.total_qty.toLocaleString('id-ID')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>
        );
      })}

      {/* Cell Detail Modal/Sheet */}
      {detailCell && (
        <div className="fixed inset-0 bg-foreground/50 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-0 md:p-4" onClick={closeDetail}>
          <div
            className="bg-[var(--glass-bg)] backdrop-blur-xl border border-[var(--glass-border)] rounded-t-2xl md:rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}
            data-testid="fg-matrix-cell-modal"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-[var(--glass-border)] flex items-start gap-3">
              <div className="flex-1">
                <div className="text-xs text-muted-foreground mb-1">{detailCell.model_key}</div>
                <div className="text-lg font-bold text-foreground">{detailCell.code}</div>
                <div className="text-sm text-muted-foreground">{detailCell.name}</div>
              </div>
              <button onClick={closeDetail} className="text-muted-foreground hover:text-foreground p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3 px-5 py-4 border-b border-[var(--glass-border)]">
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground uppercase">On Hand</div>
                <div className="text-xl font-bold text-foreground">{detailCell.qty}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground uppercase flex items-center justify-center gap-0.5">
                  <Lock className="w-2.5 h-2.5" /> Reserved
                </div>
                <div className="text-xl font-bold text-amber-700 dark:text-amber-400">{detailCell.reserved}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-muted-foreground uppercase">Available</div>
                <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{detailCell.available}</div>
              </div>
            </div>

            {/* Action area */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {actionMode === 'allocate' ? (
                <div className="space-y-3" data-testid="fg-matrix-allocate-form">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <Lock className="w-4 h-4 text-amber-700 dark:text-amber-400" /> Reservasi Stok
                    </h4>
                    <button onClick={() => setActionMode(null)} className="text-xs text-muted-foreground hover:text-foreground">
                      Batal
                    </button>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Qty</label>
                    <GlassInput
                      type="number" min="1" max={detailCell.available}
                      value={actionQty}
                      onChange={e => setActionQty(e.target.value)}
                      placeholder={`Max ${detailCell.available} pcs`}
                      data-testid="fg-matrix-allocate-qty"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Untuk (Reference)</label>
                    <GlassInput
                      value={actionRef}
                      onChange={e => setActionRef(e.target.value)}
                      placeholder="Contoh: PO-2026-001 / Customer XYZ"
                      data-testid="fg-matrix-allocate-ref"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Catatan</label>
                    <GlassInput
                      value={actionNotes}
                      onChange={e => setActionNotes(e.target.value)}
                      placeholder="Catatan tambahan…"
                    />
                  </div>
                  <Button
                    onClick={handleAllocate}
                    disabled={actionSubmitting || !actionQty || parseInt(actionQty, 10) <= 0 || parseInt(actionQty, 10) > detailCell.available}
                    className="w-full bg-amber-500 hover:bg-amber-600 gap-2"
                    data-testid="fg-matrix-allocate-submit"
                  >
                    {actionSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                    Konfirmasi Reservasi
                  </Button>
                </div>
              ) : (
                <>
                  {/* Action buttons */}
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      onClick={() => setActionMode('allocate')}
                      disabled={detailCell.available <= 0}
                      variant="outline"
                      className="gap-1.5 text-xs border-amber-400 dark:border-amber-400/30 text-amber-600 dark:text-amber-300 hover:bg-amber-50 dark:bg-amber-400/10"
                      data-testid="fg-matrix-btn-allocate"
                    >
                      <Lock className="w-3.5 h-3.5" /> Reservasi
                    </Button>
                    <Button
                      onClick={() => {
                        closeDetail();
                        onCellAction?.('issue', detailCell);
                      }}
                      disabled={detailCell.available <= 0}
                      variant="outline"
                      className="gap-1.5 text-xs border-rose-400 dark:border-rose-400/30 text-rose-600 dark:text-rose-300 hover:bg-rose-50 dark:bg-rose-400/10"
                      data-testid="fg-matrix-btn-issue"
                    >
                      <MinusCircle className="w-3.5 h-3.5" /> Keluarkan Stok
                    </Button>
                  </div>

                  {detailData && (
                    <>
                      {/* Stock by location */}
                      {detailData.stocks_by_location?.length > 0 && (
                        <div>
                          <div className="text-xs font-semibold text-muted-foreground uppercase mb-2 flex items-center gap-1.5">
                            <Package className="w-3 h-3" /> Stok per Lokasi
                          </div>
                          <div className="space-y-1">
                            {detailData.stocks_by_location.map((s, idx) => (
                              <div key={idx} className="flex items-center justify-between text-xs px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                                <span className="text-foreground">{s.location_name || s.location_id || 'Default'}</span>
                                <span className="font-mono text-primary font-bold">{s.qty} pcs</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Active reservations */}
                      {detailData.active_reservations?.length > 0 && (
                        <div>
                          <div className="text-xs font-semibold text-muted-foreground uppercase mb-2 flex items-center gap-1.5">
                            <Lock className="w-3 h-3" /> Reservasi Aktif
                          </div>
                          <div className="space-y-1">
                            {detailData.active_reservations.map(r => (
                              <div key={r.id} className="flex items-center gap-2 text-xs px-3 py-2 rounded-md bg-amber-50 dark:bg-amber-400/5 border border-amber-300 dark:border-amber-400/20">
                                <div className="flex-1 min-w-0">
                                  <div className="font-medium text-foreground truncate">{r.reservation_no}</div>
                                  <div className="text-muted-foreground truncate">{r.reference_label || '—'}</div>
                                </div>
                                <div className="font-mono text-amber-600 dark:text-amber-300 font-bold whitespace-nowrap">{r.qty} pcs</div>
                                <button
                                  onClick={() => handleRelease(r.id)}
                                  className="text-[10px] text-rose-600 dark:text-rose-300 hover:text-rose-200 underline whitespace-nowrap"
                                  data-testid={`fg-matrix-release-${r.reservation_no}`}
                                >
                                  Release
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Recent movements */}
                      {detailData.recent_movements?.length > 0 && (
                        <div>
                          <div className="text-xs font-semibold text-muted-foreground uppercase mb-2 flex items-center gap-1.5">
                            <Activity className="w-3 h-3" /> Pergerakan Terakhir
                          </div>
                          <div className="space-y-1">
                            {detailData.recent_movements.slice(0, 5).map(mv => (
                              <div key={mv.id} className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                                {mv.direction === 'in' ? (
                                  <ArrowDownCircle className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                                ) : (
                                  <ArrowUpCircle className="w-3 h-3 text-rose-600 dark:text-rose-400" />
                                )}
                                <span className="flex-1 truncate text-muted-foreground">
                                  {mv.notes || mv.reason_label || mv.source || '—'}
                                </span>
                                <span className={`font-mono font-bold ${mv.direction === 'in' ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                                  {mv.direction === 'in' ? '+' : '-'}{mv.qty}
                                </span>
                                <span className="text-muted-foreground/70 text-[10px] whitespace-nowrap">
                                  {new Date(mv.timestamp).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' })}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { FGStockMatrixView };
