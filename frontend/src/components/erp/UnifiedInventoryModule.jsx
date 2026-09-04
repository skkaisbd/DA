/**
 * Unified Inventory Viewer — Phase 2 Enhancement
 * View WIP & FG inventory dengan filter category & ownership
 * 
 * Features:
 * - Filter by inventory_category (wip_internal, fg_internal)
 * - Filter by ownership (cv_da, maklon clients)
 * - Search by material_id/name
 * - View material movements
 * - Export to CSV
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Search, RefreshCw, Filter, Download, Eye,
  TrendingUp, TrendingDown, AlertCircle, Settings, Plus, Minus,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(d) { 
  if (!d) return '-';
  return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
}

const CATEGORY_COLORS = {
  wip_internal: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-400/30',
  fg_internal: 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border-green-400 dark:border-green-400/30',
  raw_material: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-400/30',
  maklon_wip: 'bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-400 dark:border-violet-400/30',
  maklon_fg: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-400/30',
};

// ─── MATERIAL MOVEMENTS DIALOG ─────────────────────────────────────────────────
function MaterialMovementsDialog({ material, onClose, headers }) {
  const [loading, setLoading] = useState(false);
  const [movements, setMovements] = useState([]);

  useEffect(() => {
    const fetchMovements = async () => {
      setLoading(true);
      try {
        const r = await fetch(
          `${API}/api/rahaza/material-movements?material_id=${material.material_id}&limit=20`,
          { headers }
        );
        if (r.ok) {
          const data = await r.json();
          setMovements(data.movements || data || []);
        }
      } catch (e) {
        console.error('Failed to fetch movements', e);
      } finally {
        setLoading(false);
      }
    };
    fetchMovements();
  }, [material.material_id, headers]);

  return (
    <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto bg-card border-foreground/10">
      <DialogHeader>
        <DialogTitle>Material Movements — {material.material_name}</DialogTitle>
      </DialogHeader>

      <div className="space-y-3">
        <div className="bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20 rounded-lg p-3 text-sm">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div><span className="text-muted-foreground">Kode Barang:</span> <span className="text-foreground font-mono">{material.material_code || material.sku || '—'}</span></div>
            <div><span className="text-muted-foreground">Kategori:</span> <span className="text-foreground">{material.category_name || material.inventory_category}</span></div>
            <div><span className="text-muted-foreground">Current Qty:</span> <span className="text-foreground font-mono">{fmtNum(material.quantity)} {material.unit}</span></div>
            <div><span className="text-muted-foreground">Available:</span> <span className="text-green-600 dark:text-green-300 font-mono">{fmtNum(material.available_quantity)} {material.unit}</span></div>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading movements...</div>
        ) : movements.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground/60">Tidak ada movement history</div>
        ) : (
          <div className="space-y-2">
            {movements.map((mov, idx) => (
              <div key={idx} className="bg-foreground/5 rounded-lg p-3 border border-foreground/10">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge className={mov.movement_type === 'IN' ? 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-300' : 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300'}>
                      {mov.movement_type === 'IN' ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
                      {mov.movement_type}
                    </Badge>
                    <span className="text-sm text-foreground font-mono">
                      {mov.movement_type === 'IN' ? '+' : ''}{fmtNum(mov.quantity)} {mov.unit || material.unit}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">{fmtDate(mov.created_at)}</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  <div>Source: <span className="text-foreground/70">{mov.source_module || '-'}</span></div>
                  {mov.notes && <div className="mt-1 text-muted-foreground/60">{mov.notes}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DialogContent>
  );
}

// ─── STOCK ADJUSTMENT DIALOG ───────────────────────────────────────────────────
function StockAdjustmentDialog({ material, onClose, headers, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [adjustmentType, setAdjustmentType] = useState('opname_increase');
  const [qtyDelta, setQtyDelta] = useState('');
  const [reason, setReason] = useState('');
  const [referenceNo, setReferenceNo] = useState('');

  const handleSubmit = async () => {
    if (!qtyDelta || isNaN(Number(qtyDelta)) || Number(qtyDelta) === 0) {
      toast.error('Qty delta harus angka non-zero');
      return;
    }
    if (!reason || reason.trim().length < 3) {
      toast.error('Alasan minimal 3 karakter');
      return;
    }

    // Determine sign based on adjustment_type
    let signedDelta = Number(qtyDelta);
    if (['opname_decrease', 'damage'].includes(adjustmentType)) {
      signedDelta = -Math.abs(signedDelta);
    } else if (adjustmentType === 'opname_increase') {
      signedDelta = Math.abs(signedDelta);
    }
    // correction: as-entered (allow negative directly)

    setLoading(true);
    try {
      const r = await fetch(`${API}/api/wms/stock/unified/adjust`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          material_id: material.material_id,
          adjustment_type: adjustmentType,
          qty_delta: signedDelta,
          reason: reason.trim(),
          reference_no: referenceNo.trim() || null,
        })
      });
      if (r.ok) {
        const data = await r.json();
        toast.success(`Adjustment berhasil. Qty: ${fmtNum(data.qty_before)} → ${fmtNum(data.qty_after)}`);
        if (onSuccess) onSuccess();
        onClose();
      } else {
        const err = await r.json().catch(() => ({}));
        toast.error(err.detail || 'Gagal melakukan adjustment');
      }
    } catch (e) {
      toast.error('Network error saat adjustment');
    } finally {
      setLoading(false);
    }
  };

  return (
    <DialogContent className="max-w-md bg-card border-foreground/10" data-testid="stock-adjustment-dialog">
      <DialogHeader>
        <DialogTitle>Stock Adjustment / Opname</DialogTitle>
        <DialogDescription className="text-muted-foreground">
          {material.material_name} ({material.material_code || material.sku || '—'})
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 pt-2">
        <div className="bg-blue-100 dark:bg-blue-500/10 border border-blue-300 dark:border-blue-400/20 rounded-lg p-3 text-sm">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-muted-foreground">Current Qty:</span>{' '}
              <span className="text-foreground font-mono">{fmtNum(material.quantity)} {material.unit}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Available:</span>{' '}
              <span className="text-green-600 dark:text-green-300 font-mono">{fmtNum(material.available_quantity)} {material.unit}</span>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-foreground/70">Tipe Adjustment</Label>
          <Select value={adjustmentType} onValueChange={setAdjustmentType}>
            <SelectTrigger data-testid="adjustment-type-select" className="bg-foreground/5 border-foreground/10">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="opname_increase">Opname — Kelebihan (+)</SelectItem>
              <SelectItem value="opname_decrease">Opname — Kurang (−)</SelectItem>
              <SelectItem value="damage">Damage / Rusak (−)</SelectItem>
              <SelectItem value="correction">Koreksi Manual (± sesuai input)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-foreground/70">
            Qty {adjustmentType === 'correction' ? '(boleh negatif)' : '(akan otomatis ditambah/kurang sesuai tipe)'}
          </Label>
          <Input
            data-testid="adjustment-qty-input"
            type="number"
            step="0.01"
            value={qtyDelta}
            onChange={e => setQtyDelta(e.target.value)}
            placeholder={adjustmentType === 'correction' ? 'e.g. -5 atau 10' : 'e.g. 5'}
            className="bg-foreground/5 border-foreground/10 font-mono"
          />
          {qtyDelta && !isNaN(Number(qtyDelta)) && (
            <div className="text-xs text-muted-foreground">
              Preview: {fmtNum(material.quantity)} → {' '}
              <span className="text-amber-600 dark:text-amber-300 font-mono">
                {fmtNum(
                  Number(material.quantity || 0) +
                  (adjustmentType === 'opname_decrease' || adjustmentType === 'damage'
                    ? -Math.abs(Number(qtyDelta))
                    : adjustmentType === 'opname_increase'
                      ? Math.abs(Number(qtyDelta))
                      : Number(qtyDelta))
                )} {material.unit}
              </span>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-foreground/70">No. Referensi (Optional)</Label>
          <Input
            data-testid="adjustment-reference-input"
            value={referenceNo}
            onChange={e => setReferenceNo(e.target.value)}
            placeholder="No. Berita Acara / Dokumen"
            className="bg-foreground/5 border-foreground/10"
          />
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-foreground/70">Alasan / Keterangan *</Label>
          <Textarea
            data-testid="adjustment-reason-input"
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Jelaskan alasan adjustment ini..."
            rows={3}
            className="bg-foreground/5 border-foreground/10"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button
            data-testid="adjustment-cancel-btn"
            variant="outline"
            onClick={onClose}
            disabled={loading}
            className="border-foreground/10"
          >
            Batal
          </Button>
          <Button
            data-testid="adjustment-submit-btn"
            onClick={handleSubmit}
            disabled={loading}
            className="bg-gradient-to-r from-amber-500 to-orange-500 text-foreground"
          >
            {loading ? 'Memproses...' : 'Submit Adjustment'}
          </Button>
        </div>
      </div>
    </DialogContent>
  );
}

// ─── MAIN MODULE ───────────────────────────────────────────────────────────────
export default function UnifiedInventoryModule({ token }) {
  const headers = useMemo(() => ({ 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }), [token]);

  const [loading, setLoading] = useState(false);
  const [inventory, setInventory] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [ownershipFilter, setOwnershipFilter] = useState('all');
  const [movementsDialog, setMovementsDialog] = useState(null);
  const [adjustmentDialog, setAdjustmentDialog] = useState(null);
  // W1 (sesi #29, permintaan pemilik) — identitas barang, bukan UUID.
  // Pemilik: "material id seharusnya tidak perlu ada di table ini".
  // Kolom KODE + kategori/warna/opsi dipakai; filternya dibangun dari `facets`
  // yang dikirim backend (nilai yang benar-benar ada), dan saklar "stok 0"
  // menampilkan barang master yang belum punya baris stok — inilah sebab layar ini
  // tampak "tidak sinkron" dengan Master Item Produk Jadi (26 baris vs 321 barang).
  const [prodCategoryFilter, setProdCategoryFilter] = useState('all');
  const [colorFilter, setColorFilter] = useState('all');
  const [optionFilter, setOptionFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [includeZero, setIncludeZero] = useState(false);
  const [facets, setFacets] = useState({ categories: [], colors: [], options: [] });
  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [pagination, setPagination] = useState({ total: 0, total_pages: 0, has_next: false, has_prev: false });

  const fetchInventory = useCallback(async () => {
    setLoading(true);
    try {
      // Build query
      let query = `page=${page}&limit=${pageSize}&`;
      if (categoryFilter !== 'all') {
        query += `inventory_category=${categoryFilter}&`;
      }
      if (ownershipFilter !== 'all') {
        query += `ownership=${ownershipFilter}&`;
      }
      if (searchQuery) {
        query += `search=${encodeURIComponent(searchQuery)}&`;
      }
      // W1 — filter identitas barang + saklar stok 0
      if (typeFilter !== 'all')          query += `material_type=${typeFilter}&`;
      if (prodCategoryFilter !== 'all')  query += `category=${encodeURIComponent(prodCategoryFilter)}&`;
      if (colorFilter !== 'all')         query += `color=${encodeURIComponent(colorFilter)}&`;
      if (optionFilter !== 'all')        query += `option=${encodeURIComponent(optionFilter)}&`;
      if (includeZero)                   query += 'include_zero=1&';

      const r = await fetch(`${API}/api/wms/stock/unified?${query}`, { headers });
      if (r.ok) {
        const data = await r.json();
        setInventory(data.items || []);
        if (data.facets) setFacets(data.facets);
        setPagination({
          total: data.total || 0,
          total_pages: data.total_pages || 0,
          has_next: data.has_next || false,
          has_prev: data.has_prev || false,
        });
      }
    } catch (e) {
      toast.error('Gagal memuat inventory');
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, ownershipFilter, searchQuery, page, pageSize, headers,
      typeFilter, prodCategoryFilter, colorFilter, optionFilter, includeZero]);

  useEffect(() => {
    const timer = setTimeout(fetchInventory, 300);
    return () => clearTimeout(timer);
  }, [fetchInventory]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [categoryFilter, ownershipFilter, searchQuery, pageSize, typeFilter,
      prodCategoryFilter, colorFilter, optionFilter, includeZero]);

  const stats = useMemo(() => {
    const totalQty = inventory.reduce((s, i) => s + (i.quantity || 0), 0);
    const availableQty = inventory.reduce((s, i) => s + (i.available_quantity || 0), 0);
    const reservedQty = inventory.reduce((s, i) => s + (i.reserved_quantity || 0), 0);
    const lowStock = inventory.filter(i => (i.available_quantity || 0) < (i.reorder_point || 10)).length;
    return { totalItems: pagination.total || inventory.length, totalQty, availableQty, reservedQty, lowStock };
  }, [inventory, pagination.total]);

  const handleExport = async () => {
    try {
      // Fetch ALL data (across all pages) for CSV export
      let query = `page=1&limit=500&`;
      if (categoryFilter !== 'all') query += `inventory_category=${categoryFilter}&`;
      if (ownershipFilter !== 'all') query += `ownership=${ownershipFilter}&`;
      if (searchQuery) query += `search=${encodeURIComponent(searchQuery)}&`;
      if (typeFilter !== 'all')         query += `material_type=${typeFilter}&`;
      if (prodCategoryFilter !== 'all') query += `category=${encodeURIComponent(prodCategoryFilter)}&`;
      if (colorFilter !== 'all')        query += `color=${encodeURIComponent(colorFilter)}&`;
      if (optionFilter !== 'all')       query += `option=${encodeURIComponent(optionFilter)}&`;
      if (includeZero)                  query += 'include_zero=1&';

      const r = await fetch(`${API}/api/wms/stock/unified?${query}`, { headers });
      if (!r.ok) {
        toast.error('Gagal mengambil data export');
        return;
      }
      const data = await r.json();
      const allItems = data.items || [];

      // W1 — ekspor memakai KODE barang, bukan UUID `material_id`, dan membawa
      // kategori/warna/opsi/ukuran. Kolom id sengaja TIDAK diikutkan (pemilik:
      // "material id seharusnya tidak perlu ada di table ini" — termasuk di ekspor).
      const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
      const csv = [
        ['Kode Barang', 'Nama Barang', 'Kategori', 'Warna', 'Opsi', 'Ukuran',
         'Jenis Stok', 'Kepemilikan', 'Qty', 'Tersedia', 'Reserved', 'Satuan', 'Lokasi'].join(','),
        ...allItems.map(i => [
          q(i.material_code || i.sku),
          q(i.material_name),
          q(i.category_name),
          q(i.color_name),
          q(i.option_name),
          q(i.size_code),
          q(i.inventory_category),
          q(i.ownership),
          i.quantity,
          i.available_quantity,
          i.reserved_quantity,
          q(i.unit),
          q(i.location_code ? `${i.location_code}${i.location_name ? ' · ' + i.location_name : ''}` : (i.location || 'belum ada baris stok')),
        ].join(','))
      ].join('\n');

      const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `stok-barang-${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      toast.success(`${allItems.length} item di-export ke CSV`);
    } catch (e) {
      toast.error('Gagal export CSV');
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center">
              <Package className="w-5 h-5 text-foreground" />
            </div>
            Unified Inventory Viewer
          </h1>
          <p className="text-sm text-muted-foreground mt-1">WIP & FG Internal Inventory Management</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={fetchInventory} variant="outline" size="sm" className="border-foreground/10">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button onClick={handleExport} variant="outline" size="sm" className="border-foreground/10">
            <Download className="w-4 h-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* RC-IA-warehouse-3: viewer read-only. Adjustment RESMI dilakukan di tab "Penyesuaian" (jalur rahaza/material-adjust + posting GL, per-lokasi). */}
      <div className="flex items-start gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs text-blue-700 dark:text-blue-300" data-testid="unified-viewer-readonly-note">
        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>Tampilan ini <strong>read-only</strong>. Untuk menyesuaikan stok gunakan tab <strong>“Penyesuaian (Adjustment)”</strong> — jalur resmi yang mencatat pergerakan per-lokasi &amp; posting jurnal (GL).</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-5 gap-4">
        {[
          { label: 'Total Items', value: stats.totalItems, color: 'text-foreground' },
          { label: 'Total Qty', value: fmtNum(stats.totalQty), color: 'text-blue-600 dark:text-blue-300' },
          { label: 'Available', value: fmtNum(stats.availableQty), color: 'text-green-600 dark:text-green-300' },
          { label: 'Reserved', value: fmtNum(stats.reservedQty), color: 'text-amber-600 dark:text-amber-300' },
          { label: 'Low Stock', value: stats.lowStock, color: stats.lowStock > 0 ? 'text-red-600 dark:text-red-300' : 'text-muted-foreground' },
        ].map(s => (
          <GlassCard key={s.label} className="p-4">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Filters */}
      <GlassCard className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Search className="w-3 h-3" /> Cari
            </div>
            <Input 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Kode barang, nama, warna, lokasi..."
              className="bg-foreground/5 border-foreground/10"
              data-testid="inv-search"
            />
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Filter className="w-3 h-3" /> Kategori Produk
            </div>
            <Select value={prodCategoryFilter} onValueChange={setProdCategoryFilter}>
              <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="inv-filter-category">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Kategori</SelectItem>
                {(facets.categories || []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Filter className="w-3 h-3" /> Warna
            </div>
            <Select value={colorFilter} onValueChange={setColorFilter}>
              <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="inv-filter-color">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Warna</SelectItem>
                {(facets.colors || []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Filter className="w-3 h-3" /> Opsi Varian
            </div>
            <Select value={optionFilter} onValueChange={setOptionFilter}>
              <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="inv-filter-option">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Opsi</SelectItem>
                {(facets.options || []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Filter className="w-3 h-3" /> Jenis Barang
            </div>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="inv-filter-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Jenis</SelectItem>
                <SelectItem value="fg">Produk Jadi (FG)</SelectItem>
                <SelectItem value="fabric">Kain</SelectItem>
                <SelectItem value="accessory">Aksesoris</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
              <Filter className="w-3 h-3" /> Kepemilikan
            </div>
            <Select value={ownershipFilter} onValueChange={setOwnershipFilter}>
              <SelectTrigger className="bg-foreground/5 border-foreground/10" data-testid="inv-filter-ownership">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Ownership</SelectItem>
                <SelectItem value="cv_da">CV. Dewi Aditya</SelectItem>
                <SelectItem value="maklon">Maklon Clients</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        {/* W1 — saklar "tampilkan juga yang stoknya 0" */}
        <div className="flex items-center justify-between gap-3 mt-4 pt-3 border-t border-foreground/10 flex-wrap">
          <label className="flex items-center gap-2 text-xs text-foreground/80 cursor-pointer select-none"
            title="Barang master yang belum punya baris stok ikut ditampilkan dengan qty 0 — supaya daftar bisa disamakan dengan Master Item Produk Jadi.">
            <input type="checkbox" checked={includeZero}
              onChange={e => setIncludeZero(e.target.checked)}
              className="h-3.5 w-3.5 accent-[hsl(var(--primary))] cursor-pointer"
              data-testid="inv-show-zero-toggle" />
            Tampilkan juga barang yang stoknya 0 (samakan dengan Master Item)
          </label>
          {(prodCategoryFilter !== 'all' || colorFilter !== 'all' || optionFilter !== 'all'
            || typeFilter !== 'all' || searchQuery) && (
            <Button variant="ghost" size="sm" className="h-7 text-xs"
              onClick={() => { setProdCategoryFilter('all'); setColorFilter('all'); setOptionFilter('all'); setTypeFilter('all'); setSearchQuery(''); }}
              data-testid="inv-clear-filters">
              Bersihkan filter
            </Button>
          )}
        </div>
      </GlassCard>

      {/* Inventory Table */}
      <GlassCard className="p-6">
        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Memuat inventory...</div>
        ) : inventory.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground/60">
            <Package className="w-12 h-12 mx-auto opacity-20 mb-3" />
            <p>Tidak ada inventory untuk filter ini</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10">
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Kode Barang</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Nama Barang</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Kategori</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Warna · Ukuran</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Opsi</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Jenis Stok</th>
                  <th className="text-right py-3 px-2 text-xs font-semibold text-muted-foreground">Quantity</th>
                  <th className="text-right py-3 px-2 text-xs font-semibold text-muted-foreground">Available</th>
                  <th className="text-right py-3 px-2 text-xs font-semibold text-muted-foreground">Reserved</th>
                  <th className="text-left py-3 px-2 text-xs font-semibold text-muted-foreground">Lokasi</th>
                  <th className="text-center py-3 px-2 text-xs font-semibold text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((item, idx) => {
                  const isLowStock = (item.available_quantity || 0) < (item.reorder_point || 10);
                  return (
                    <tr key={`${item.id || item.material_id || 'row'}-${item.inventory_category || ''}-${item.ownership || ''}-${item.location || ''}-${idx}`} className="border-b border-foreground/5 hover:bg-foreground/5 transition" data-testid={`inv-row-${item.material_code || item.material_id}`}>
                      <td className="py-3 px-2 text-foreground font-mono text-xs">{item.material_code || item.sku || '—'}</td>
                      <td className="py-3 px-2 text-foreground">{item.material_name}</td>
                      <td className="py-3 px-2 text-foreground/80 text-xs">{item.category_name || '—'}</td>
                      <td className="py-3 px-2 text-foreground/80 text-xs">
                        {item.color_name || '—'}
                        {item.size_code ? <span className="text-muted-foreground"> · {item.size_code}</span> : null}
                      </td>
                      <td className="py-3 px-2 text-foreground/70 text-xs">{item.option_name || '—'}</td>
                      <td className="py-3 px-2">
                        <Badge className={`text-[10px] ${CATEGORY_COLORS[item.inventory_category] || 'bg-muted dark:bg-slate-500/15 text-foreground/70'}`}>
                          {item.inventory_category}
                        </Badge>
                      </td>
                      <td className="py-3 px-2 text-right text-foreground font-mono">{fmtNum(item.quantity)} {item.unit}</td>
                      <td className="py-3 px-2 text-right">
                        <span className={`font-mono ${isLowStock ? 'text-red-600 dark:text-red-300' : 'text-green-600 dark:text-green-300'}`}>
                          {fmtNum(item.available_quantity)} {item.unit}
                        </span>
                        {isLowStock && <AlertCircle className="w-3 h-3 inline ml-1 text-red-700 dark:text-red-400" />}
                      </td>
                      <td className="py-3 px-2 text-right text-amber-600 dark:text-amber-300 font-mono">{fmtNum(item.reserved_quantity || 0)}</td>
                      <td className="py-3 px-2 text-muted-foreground text-xs">
                        {item.no_stock_row
                          ? <span className="italic text-foreground/40">belum ada baris stok</span>
                          : (item.location_code
                              ? `${item.location_code}${item.location_name ? ' · ' + item.location_name : ''}`
                              : (item.location || '-'))}
                      </td>
                      <td className="py-3 px-2 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            data-testid={`view-movements-${item.material_id}`}
                            size="sm"
                            variant="ghost"
                            onClick={() => setMovementsDialog(item)}
                            className="h-7 px-2 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-600 dark:text-blue-300"
                          >
                            <Eye className="w-3 h-3 mr-1" />
                            Log
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Controls */}
        {pagination.total_pages > 0 && (
          <div className="flex items-center justify-between pt-4 mt-4 border-t border-foreground/10" data-testid="inventory-pagination">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                Menampilkan{' '}
                <span className="text-foreground font-mono">
                  {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, pagination.total)}
                </span>{' '}
                dari{' '}
                <span className="text-foreground font-mono">{fmtNum(pagination.total)}</span>{' '}
                item
              </span>
              <div className="flex items-center gap-2">
                <span>Per halaman:</span>
                <Select value={String(pageSize)} onValueChange={v => setPageSize(parseInt(v))}>
                  <SelectTrigger data-testid="page-size-select" className="bg-foreground/5 border-foreground/10 h-7 w-20 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                    <SelectItem value="200">200</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Button
                data-testid="page-first"
                size="sm"
                variant="ghost"
                onClick={() => setPage(1)}
                disabled={!pagination.has_prev}
                className="h-7 w-7 p-0"
              >
                <ChevronsLeft className="w-4 h-4" />
              </Button>
              <Button
                data-testid="page-prev"
                size="sm"
                variant="ghost"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={!pagination.has_prev}
                className="h-7 w-7 p-0"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="px-3 text-xs text-foreground/70 font-mono">
                Halaman <span className="text-foreground">{page}</span> dari{' '}
                <span className="text-foreground">{pagination.total_pages}</span>
              </span>
              <Button
                data-testid="page-next"
                size="sm"
                variant="ghost"
                onClick={() => setPage(p => p + 1)}
                disabled={!pagination.has_next}
                className="h-7 w-7 p-0"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
              <Button
                data-testid="page-last"
                size="sm"
                variant="ghost"
                onClick={() => setPage(pagination.total_pages)}
                disabled={!pagination.has_next}
                className="h-7 w-7 p-0"
              >
                <ChevronsRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </GlassCard>

      {/* Movements Dialog */}
      {movementsDialog && (
        <Dialog open={!!movementsDialog} onOpenChange={() => setMovementsDialog(null)}>
          <MaterialMovementsDialog 
            material={movementsDialog}
            headers={headers}
            onClose={() => setMovementsDialog(null)}
          />
        </Dialog>
      )}

      {/* Adjustment Dialog */}
      {adjustmentDialog && (
        <Dialog open={!!adjustmentDialog} onOpenChange={() => setAdjustmentDialog(null)}>
          <StockAdjustmentDialog
            material={adjustmentDialog}
            headers={headers}
            onClose={() => setAdjustmentDialog(null)}
            onSuccess={fetchInventory}
          />
        </Dialog>
      )}
    </div>
  );
}
