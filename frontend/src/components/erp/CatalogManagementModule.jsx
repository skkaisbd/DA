/**
 * CatalogManagementModule — Marketing Portal Phase 5
 * Manajemen katalog produk per akun platform + stock sync.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import {
  Package, Plus, RefreshCw, Search, Edit2, Trash2, AlertTriangle,
  CheckCircle2, AlertCircle, ChevronRight, ChevronLeft, TrendingDown,
  ShoppingBag, Layers, BarChart3, Save, Loader2, X, History,
  ArrowRightLeft, Download, Upload, Tag, Star, Eye, Coins, PackagePlus,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { FGProductPickerDialog } from './FGProductPickerDialog';
// 2026-08-12 — "Isi dari Master Produk" (banyak toko sekaligus) hidup sebagai TAB di
// sini, bukan sebagai pintu menu terpisah: staf yang membuka Manajemen Katalog dan
// menemukan katalog kosong harus bisa mengisinya DI TEMPAT, bukan mencari menu lain.
import CatalogFromMasterModule from './marketing/CatalogFromMasterModule';
import CatalogItemsView from './marketing/CatalogItemsView';
import { formatRupiah } from '@/lib/format';
import { readField, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const cat = (path, opts = {}) => fetch(`${API}/api/marketing/catalogs${path}`, opts);

const PLATFORMS = ['Shopee', 'TikTok Shop', 'Tokopedia', 'Lazada', 'Blibli', 'Instagram', 'Website', 'Lainnya'];

const STOCK_STATUS_CFG = {
  in_stock:     { label: 'Tersedia', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-300 dark:border-emerald-500/20', badge: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300' },
  low_stock:    { label: 'Stok Rendah', color: 'text-amber-700 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-500/20', badge: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300' },
  out_of_stock: { label: 'Habis', color: 'text-red-700 dark:text-red-400', bg: 'bg-red-100 dark:bg-red-500/10 border-red-300 dark:border-red-500/20', badge: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300' },
};

// ─── Main Component ───────────────────────────────────────────────────────────

export default function CatalogManagementModule({ token, moduleId, initialTab }) {
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  // Tab awal: deep-link `marketing-catalog-from-master` mendarat di tab "Isi dari
  // Master". Dipilih dari `moduleId` (dikirim App.js) — BUKAN dari sessionStorage
  // yang harus ditulis modul lain lebih dulu; urutan mount itu terbukti tidak bisa
  // diandalkan dan membuat deep-link mendarat di tab pertama.
  const [tab, setTab] = useState(() => {
    const TABS = ['catalogs', 'items', 'stock', 'history', 'from-master'];
    if (initialTab && TABS.includes(initialTab)) return initialTab;
    if (moduleId === 'marketing-catalog-from-master') return 'from-master';
    try {
      const saved = sessionStorage.getItem('hub_tab_marketing-catalog');
      if (saved && TABS.includes(saved)) {
        sessionStorage.removeItem('hub_tab_marketing-catalog');
        return saved;
      }
    } catch (e) { /* sessionStorage tidak tersedia */ }
    return 'catalogs';
  });
  const [accounts, setAccounts] = useState([]);
  const [catalogs, setCatalogs] = useState([]);
  const [selectedCatalog, setSelectedCatalog] = useState(null);
  const [items, setItems] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterAccount, setFilterAccount] = useState('');

  // Dialogs
  const [catalogDialog, setCatalogDialog] = useState(null);
  const [itemDialog, setItemDialog] = useState(null);
  const [stockDialog, setStockDialog] = useState(null);
  const [bulkStockDialog, setBulkStockDialog] = useState(false);
  const [bulkStockData, setBulkStockData] = useState({});

  const [syncing, setSyncing] = useState(false);
  const [refreshingHpp, setRefreshingHpp] = useState(false);
  const [refreshingMaster, setRefreshingMaster] = useState(false);
  // F6 — kategori dari MASTER (bukan teks bebas). Dipakai filter + form item.
  const [productCategories, setProductCategories] = useState([]);
  const [filterCategoryId, setFilterCategoryId] = useState('');
  // F11 — "Perlu Perhatian": saring item bermasalah (belum tertaut master / stok
  // basi). WAJIB dikerjakan server: item bermasalah bisa ada di halaman ke-2
  // (paginasi 10/hal), jadi banner yang mengatakan "1 item belum tertaut" dulu
  // memberi tahu ada masalah TANPA satu pun cara menemukannya.
  const [filterAttention, setFilterAttention] = useState('');
  const [stockSummary, setStockSummary] = useState({ stale: 0, unlinked: 0, attention: 0 });
  // F4 — saringan penayangan/status/foto/urutan. SEMUA dikerjakan SERVER: statusnya
  // turunan (dihitung dari publish_state + stok jual), jadi menyaringnya di layar
  // hanya akan benar untuk baris yang kebetulan sedang tampil.
  const [f4, setF4] = useState({
    catalogStatus: [], publishState: '', hasPhoto: '', sort: 'name', order: 'asc',
  });
  const [statusOptions, setStatusOptions] = useState([]);
  const [seeding, setSeeding] = useState(false);

  // ── Load functions ────────────────────────────────────────────────

  const loadProductCategories = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/rahaza/product-categories`, { headers });
      const d = await r.json();
      setProductCategories(d.categories || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadAccounts = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/marketing/accounts?status=active`, { headers });
      const d = await r.json();
      setAccounts(d.accounts || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadCatalogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterAccount) params.set('account_id', filterAccount);
      const r = await cat(`?${params}`, { headers });
      const d = await r.json();
      setCatalogs(d.catalogs || []);
    } catch (e) { toast.error('Gagal memuat katalog'); }
    finally { setLoading(false); }
  }, [headers, filterAccount]);

  const loadItems = useCallback(async (cid, search = '', status = '', categoryId = '',
                                       attention = '', f4opts = null) => {
    if (!cid) return;
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (status) params.set('status', status);
      if (categoryId) params.set('category_id', categoryId);
      // F11 — filter item bermasalah dikerjakan SERVER supaya bekerja lintas halaman
      if (attention) params.set('attention', attention);
      // F4 — status penayangan / foto / urutan juga dikerjakan server
      const o = f4opts || {};
      if ((o.catalogStatus || []).length) params.set('catalog_status', o.catalogStatus.join(','));
      if (o.publishState) params.set('publish_state', o.publishState);
      if (o.hasPhoto) params.set('has_photo', o.hasPhoto);
      if (o.sort) params.set('sort', o.sort);
      if (o.order) params.set('order', o.order);
      // Ambil cukup banyak baris supaya paginasi 10/hal di layar tidak memotong
      // katalog besar (bawaan server 100 dulu menyembunyikan item ke-101 dst.)
      params.set('limit', '500');
      const r = await cat(`/${cid}/items?${params}`, { headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal memuat item katalog'); return; }
      setItems(d.items || []);
      setStatusOptions(d.status_options || []);
      setStockSummary(d.stock_summary || { stale: 0, unlinked: 0, attention: 0 });
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadDashboard = useCallback(async () => {
    try {
      const r = await cat('/stock-dashboard', { headers });
      const d = await r.json();
      setDashboard(d);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadHistory = useCallback(async (cid) => {
    if (!cid) return;
    try {
      const r = await cat(`/${cid}/stock-history?limit=30`, { headers });
      const d = await r.json();
      setHistory(d.history || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  useEffect(() => {
    loadAccounts();
    loadDashboard();
    loadProductCategories();
  }, [loadAccounts, loadDashboard, loadProductCategories]);

  useEffect(() => {
    if (tab === 'catalogs' || tab === 'items') loadCatalogs();
    if (tab === 'stock') loadDashboard();
  }, [tab, loadCatalogs, loadDashboard]);

  useEffect(() => {
    if (selectedCatalog) {
      loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention, f4);
      if (tab === 'history') loadHistory(selectedCatalog.id);
    }
  }, [selectedCatalog, searchQ, filterStatus, filterCategoryId, filterAttention, f4,
      tab, loadItems, loadHistory]);

  // ── Handlers ─────────────────────────────────────────────────────

  const handleSaveCatalog = async (form) => {
    const isEdit = !!form.id;
    const r = await cat(
      isEdit ? `/${form.id}` : '',
      { method: isEdit ? 'PUT' : 'POST', headers, body: JSON.stringify(form) }
    );
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal simpan'); return; }
    toast.success(isEdit ? 'Katalog diupdate' : 'Katalog dibuat!');
    setCatalogDialog(null);
    loadCatalogs();
  };

  const handleDeleteCatalog = async (catalog) => {
    if (!window.confirm(`Hapus katalog "${catalog.name}" dan semua itemnya?`)) return;
    const r = await cat(`/${catalog.id}`, { method: 'DELETE', headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal hapus'); return; }
    toast.success(d.message || 'Katalog dihapus');
    if (selectedCatalog?.id === catalog.id) setSelectedCatalog(null);
    loadCatalogs();
  };

  const handleSaveItem = async (form) => {
    if (!selectedCatalog) return;
    const isEdit = !!form.id;

    // Two-mode payload: from-fg vs manual
    if (!isEdit && form._mode === 'from_fg' && form.fg_material_id) {
      // Create from FG master
      const payload = {
        fg_material_id: form.fg_material_id,
        price: parseFloat(form.harga_jual ?? form.price) || 0,
        original_price: parseFloat(form.harga_coret ?? form.original_price) || 0,
        platform_price: parseFloat(form.platform_price) || 0,
        harga_jual: parseFloat(form.harga_jual ?? form.price) || 0,
        harga_coret: parseFloat(form.harga_coret ?? form.original_price) || 0,
        harga_original: parseFloat(form.harga_original) || 0,
        platform_url: form.platform_url || '',
        stock_alert_threshold: parseFloat(form.stock_alert_threshold) || 10,
        tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
        description_override: form.description || '',
      };
      const r = await cat(`/${selectedCatalog.id}/items/from-fg`, {
        method: 'POST', headers, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal simpan item dari FG'); return; }
      toast.success(d.message || 'Item berhasil ditambahkan dari FG');
    } else {
      // Manual entry (edit existing or new manual)
      const payload = {
        ...form,
        tags: typeof form.tags === 'string'
          ? form.tags.split(',').map(t => t.trim()).filter(Boolean)
          : (form.tags || []),
        price: parseFloat(form.harga_jual ?? form.price) || 0,
        original_price: parseFloat(form.harga_coret ?? form.original_price) || 0,
        platform_price: parseFloat(form.platform_price) || 0,
        harga_jual: parseFloat(form.harga_jual ?? form.price) || 0,
        harga_coret: parseFloat(form.harga_coret ?? form.original_price) || 0,
        harga_original: parseFloat(form.harga_original) || 0,
        stock_quantity: parseFloat(form.stock_quantity) || 0,
        stock_alert_threshold: parseFloat(form.stock_alert_threshold) || 10,
        weight_gram: parseFloat(form.weight_gram) || 0,
      };
      // hpp bersifat read-only (dari RnD) — jangan kirim dari form manual
      delete payload.hpp;
      delete payload._mode;
      delete payload.fg_preview;
      // ── F6/T3 — kategori TIDAK lagi dikirim sebagai teks bebas ──────────────
      // Server memang sudah membuang `category`, jadi mengirimnya hanya membuat
      // staf percaya isian itu tersimpan. Yang dikirim sekarang `category_id`
      // (tervalidasi), dan HANYA untuk item yang belum tertaut master — item
      // tertaut kategorinya milik Master Produk (server balas 400 kalau dipaksa).
      const _linkedToMaster = !!(form.fg_material_id || form.material_id || form.variant_id);
      delete payload.category;
      delete payload.fg_material_id;
      if (_linkedToMaster || !form.category_id) {
        delete payload.category_id;
      }
      const r = await cat(
        isEdit ? `/${selectedCatalog.id}/items/${form.id}` : `/${selectedCatalog.id}/items`,
        { method: isEdit ? 'PUT' : 'POST', headers, body: JSON.stringify(payload) }
      );
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal simpan item'); return; }
      toast.success(isEdit ? 'Item diupdate' : 'Item ditambahkan!');
    }
    setItemDialog(null);
    loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
    loadCatalogs();
  };

  const handleDeleteItem = async (item) => {
    if (!window.confirm(`Hapus item "${item.name}"?`)) return;
    const r = await cat(`/${selectedCatalog.id}/items/${item.id}`, { method: 'DELETE', headers });
    if (!r.ok) { toast.error('Gagal hapus item'); return; }
    toast.success('Item dihapus');
    loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
    loadCatalogs();
  };

  const handleUpdateStock = async (form) => {
    const r = await cat(`/${selectedCatalog.id}/items/${form.id}/stock`, {
      method: 'PUT', headers, body: JSON.stringify({ stock_quantity: form.stock_quantity, notes: form.notes }),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal update stok'); return; }
    toast.success(`Stok diupdate: ${d.old_stock} → ${d.new_stock}`);
    setStockDialog(null);
    loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
    loadCatalogs();
    loadHistory(selectedCatalog.id);
  };

  const handleBulkStockSave = async () => {
    if (!selectedCatalog) return;
    const updates = Object.entries(bulkStockData)
      .filter(([, v]) => v.qty !== '' && v.qty !== undefined)
      .map(([item_id, v]) => ({ item_id, stock_quantity: parseFloat(v.qty) || 0, notes: v.notes || '' }));
    if (!updates.length) { toast.error('Tidak ada data yang diinput'); return; }
    const r = await cat(`/${selectedCatalog.id}/bulk-stock-update`, {
      method: 'POST', headers, body: JSON.stringify({ updates }),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal bulk update'); return; }
    toast.success(`${d.saved} item stok diperbarui`);
    setBulkStockDialog(false);
    setBulkStockData({});
    loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
    loadCatalogs();
    loadHistory(selectedCatalog.id);
  };

  const handleWmsSync = async () => {
    if (!selectedCatalog) return;
    setSyncing(true);
    try {
      const r = await cat(`/${selectedCatalog.id}/sync-from-wms`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal sync'); return; }
      toast.success(d.message);
      loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
      loadCatalogs();
    } finally { setSyncing(false); }
  };

  const handleSeedDemo = async () => {
    setSeeding(true);
    try {
      const r = await cat('/seed-demo', { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal seed'); return; }
      toast.success(d.message);
      loadCatalogs();
      loadDashboard();
      loadAccounts();
    } finally { setSeeding(false); }
  };

  // Tarik-ulang HPP dari RnD (Model/FG) — SEMUA item katalog (bulk)
  const handleRefreshHppBulk = async () => {
    if (!selectedCatalog) return;
    setRefreshingHpp(true);
    try {
      const r = await cat(`/${selectedCatalog.id}/refresh-hpp`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal refresh HPP'); return; }
      const skipped = d.skipped_no_source || 0;
      toast.success(
        `HPP diperbarui: ${d.updated} item${skipped ? ` · ${skipped} item tanpa sumber RnD dilewati` : ''}`
      );
      loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
    } catch (e) {
      toast.error('Gagal refresh HPP');
    } finally { setRefreshingHpp(false); }
  };

  // Tarik-ulang HPP dari RnD (Model/FG) — satu item

  // F8/M7 — Segarkan field TAMPILAN item katalog dari MASTER (nama, kategori,
  // berat, info varian, HPP, harga resmi) + stoknya. Menutup "salinan tanpa
  // penyegar": dulu field-field ini disalin SEKALI saat item dibuat dan tidak
  // pernah diperbarui, jadi kategori/berat di katalog basi selamanya.
  const handleRefreshFromMaster = async () => {
    if (!selectedCatalog) return;
    setRefreshingMaster(true);
    try {
      const r = await cat(`/${selectedCatalog.id}/refresh-from-master`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal menyegarkan dari master'); return; }
      toast.success(d.message || `${d.updated} item disegarkan dari master`);
      loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId, filterAttention);
      loadCatalogs();
    } catch (e) {
      toast.error('Gagal menyegarkan dari master');
    } finally { setRefreshingMaster(false); }
  };

  // Fase 3b — Sinkron stok item Toko dari FG (by SKU varian / material). Auto-override.

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            Manajemen Katalog Produk
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Phase 5 — Catalog Management + Stock Sync
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={handleSeedDemo} disabled={seeding}>
            {seeding ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Package className="w-4 h-4 mr-1" />}
            Seed Demo Data
          </Button>
          <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => setCatalogDialog({})}>
            <Plus className="w-4 h-4 mr-1" /> Buat Katalog
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Total Item', value: dashboard.summary?.total_items || 0, icon: Package, color: 'text-blue-600 dark:text-blue-400' },
            { label: 'Tersedia', value: dashboard.summary?.in_stock || 0, icon: CheckCircle2, color: 'text-emerald-600 dark:text-emerald-400' },
            { label: 'Stok Rendah', value: dashboard.summary?.low_stock || 0, icon: AlertTriangle, color: 'text-amber-700 dark:text-amber-400' },
            { label: 'Habis', value: dashboard.summary?.out_of_stock || 0, icon: AlertCircle, color: 'text-red-700 dark:text-red-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="rounded-xl border border-foreground/10 bg-foreground/5 p-3 flex items-center gap-3">
              <Icon className={`w-8 h-8 ${color} shrink-0`} />
              <div>
                <div className="text-xl font-bold">{value}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-5 w-full">
          <TabsTrigger value="catalogs" className="flex items-center gap-1.5 text-xs" data-testid="catalog-tab-catalogs">
            <Layers className="w-3.5 h-3.5" /> Katalog
          </TabsTrigger>
          <TabsTrigger value="items" className="flex items-center gap-1.5 text-xs" disabled={!selectedCatalog} data-testid="catalog-tab-items">
            <ShoppingBag className="w-3.5 h-3.5" /> Item {selectedCatalog && <Badge variant="secondary" className="ml-1 text-xs px-1">{selectedCatalog.item_count}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="from-master" className="flex items-center gap-1.5 text-xs" data-testid="catalog-tab-from-master">
            <PackagePlus className="w-3.5 h-3.5" /> Isi dari Master
          </TabsTrigger>
          <TabsTrigger value="stock" className="flex items-center gap-1.5 text-xs" data-testid="catalog-tab-stock">
            <BarChart3 className="w-3.5 h-3.5" /> Stok Dashboard
          </TabsTrigger>
          <TabsTrigger value="history" className="flex items-center gap-1.5 text-xs" disabled={!selectedCatalog} data-testid="catalog-tab-history">
            <History className="w-3.5 h-3.5" /> Riwayat
          </TabsTrigger>
        </TabsList>

        {/* ── TAB 1: CATALOGS ── */}
        <TabsContent value="catalogs" className="space-y-4 mt-4">
          <div className="flex flex-wrap gap-2 items-center justify-between">
            <SmartNativeSelect
              className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
              value={filterAccount}
              onChange={e => setFilterAccount(e.target.value)}
            >
              <option value="">Semua Akun</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.platform} — {a.name}</option>)}
            </SmartNativeSelect>
            <Button size="sm" variant="outline" onClick={loadCatalogs} disabled={loading}>
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>

          {loading && (
            <div className="text-center py-12"><Loader2 className="w-8 h-8 animate-spin mx-auto text-indigo-600 dark:text-indigo-400" /></div>
          )}

          {!loading && catalogs.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Layers className="w-12 h-12 mx-auto mb-3 opacity-20" />
              <p className="text-sm">Belum ada katalog</p>
              <p className="text-xs mt-1">Klik "Buat Katalog" atau "Seed Demo Data" untuk memulai</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {catalogs.map(catalog => (
              <CatalogCard
                key={catalog.id}
                catalog={catalog}
                isSelected={selectedCatalog?.id === catalog.id}
                onSelect={() => { setSelectedCatalog(catalog); setTab('items'); }}
                onEdit={() => setCatalogDialog(catalog)}
                onDelete={() => handleDeleteCatalog(catalog)}
              />
            ))}
          </div>
        </TabsContent>

        {/* ── TAB 2: ITEMS ── */}
        <TabsContent value="items" className="space-y-4 mt-4">
          {selectedCatalog && (
            <>
              {/* Catalog breadcrumb */}
              <div className="flex items-center gap-2 flex-wrap justify-between">
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setTab('catalogs')}>
                    <ChevronLeft className="w-4 h-4 mr-1" /> Katalog
                  </Button>
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  <span className="font-medium text-sm">{selectedCatalog.name}</span>
                  <PlatformBadge platform={selectedCatalog.platform} />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setBulkStockDialog(true)}>
                    <ArrowRightLeft className="w-4 h-4 mr-1" /> Bulk Stok
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleWmsSync} disabled={syncing}
                    title="Sinkron stok semua item dari WMS/Finished Goods (via material & varian/SKU)"
                    data-testid="catalog-sync-wms">
                    {syncing ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />}
                    Sinkron Stok FG
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleRefreshHppBulk} disabled={refreshingHpp}
                    title="Tarik-ulang HPP semua item dari master (R&D / HPP dasar manual)" data-testid="catalog-refresh-hpp-bulk">
                    {refreshingHpp ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Coins className="w-4 h-4 mr-1 text-amber-600 dark:text-amber-400" />}
                    Refresh HPP
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleRefreshFromMaster} disabled={refreshingMaster}
                    title="Segarkan nama, kategori, berat, info varian, HPP & harga resmi dari Master Produk"
                    data-testid="catalog-refresh-from-master">
                    {refreshingMaster ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1 text-indigo-600 dark:text-indigo-400" />}
                    Segarkan dari Master
                  </Button>
                  <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700" onClick={() => setItemDialog({})}>
                    <Plus className="w-4 h-4 mr-1" /> Tambah Item
                  </Button>
                </div>
              </div>

              {/* Filters */}
              <div className="flex gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[180px]">
                  <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="pl-8 h-8 text-xs"
                    placeholder="Cari nama, SKU, tag..."
                    value={searchQ}
                    onChange={e => setSearchQ(e.target.value)}
                  />
                </div>
                <select
                  className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
                  value={filterStatus}
                  onChange={e => setFilterStatus(e.target.value)}
                >
                  <option value="">Semua Status</option>
                  <option value="in_stock">Tersedia</option>
                  <option value="low_stock">Stok Rendah</option>
                  <option value="out_of_stock">Habis</option>
                </select>
                <select
                  className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
                  value={filterCategoryId}
                  onChange={e => setFilterCategoryId(e.target.value)}
                  title="Kategori dari Master Produk (bukan teks bebas)"
                  data-testid="catalog-filter-category"
                >
                  <option value="">Semua Kategori</option>
                  {productCategories.map(c => (
                    <option key={c.id} value={c.id}>{c.sku_prefix} · {c.name}</option>
                  ))}
                </select>
              </div>

              {/* F11 — chip "Perlu Perhatian". Ada di samping filter lain supaya
                  item bermasalah bisa ditemukan TANPA menebak halaman. Chip hanya
                  tampil kalau memang ada masalah — layar bersih tidak perlu
                  dihiasi tombol yang selalu kosong. */}
              {(stockSummary.attention > 0 || filterAttention) && (
                <div className="flex flex-wrap items-center gap-2" data-testid="catalog-attention-chips">
                  <span className="text-[11px] text-muted-foreground">Tampilkan:</span>
                  {[
                    { key: '', label: 'Semua Item', count: null, testid: 'chip-all' },
                    { key: 'all', label: 'Perlu Perhatian', count: stockSummary.attention || 0, testid: 'chip-attention' },
                    { key: 'unlinked', label: 'Belum tertaut master', count: stockSummary.unlinked || 0, testid: 'chip-unlinked' },
                    { key: 'stale', label: 'Stok basi', count: stockSummary.stale || 0, testid: 'chip-stale' },
                  ].filter(c => c.key === '' || c.key === 'all' || c.count > 0 || filterAttention === c.key)
                    .map(c => {
                      const active = filterAttention === c.key;
                      return (
                        <button
                          key={c.key || 'all-items'}
                          type="button"
                          onClick={() => setFilterAttention(c.key)}
                          data-testid={`catalog-attention-${c.testid}`}
                          className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${
                            active
                              ? 'bg-amber-500/20 border-amber-400/60 text-amber-800 dark:text-amber-200 font-semibold'
                              : 'bg-foreground/5 border-foreground/10 text-muted-foreground hover:text-foreground hover:border-foreground/25'
                          }`}
                        >
                          {c.label}
                          {c.count !== null && <span className="ml-1 opacity-80">({c.count})</span>}
                        </button>
                      );
                    })}
                  {filterAttention && (
                    <span className="text-[11px] text-amber-700 dark:text-amber-300"
                      data-testid="catalog-attention-active-note">
                      menampilkan {items.length} item bermasalah dari {stockSummary.scanned ?? '—'} item katalog
                    </span>
                  )}
                </div>
              )}

              {/* K-7a — peringatan cache stok basi / item belum tertaut master.
                  F11: BISA DIKLIK. Sebelumnya banner ini memberi tahu ada masalah
                  tanpa satu pun cara menemukannya (item bermasalah bisa di halaman
                  ke-2), sehingga peringatannya praktis jadi hiasan. */}
              {(stockSummary.stale > 0 || stockSummary.unlinked > 0) && (
                <div className="flex items-start gap-2 text-[12px] rounded-lg p-3 border bg-amber-500/10 border-amber-400/40 text-amber-800 dark:text-amber-200"
                  data-testid="catalog-stock-warning">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    {stockSummary.stale > 0 && (
                      <div>
                        <button type="button" onClick={() => setFilterAttention('stale')}
                          className="underline decoration-dotted underline-offset-2 font-bold hover:opacity-80"
                          data-testid="catalog-warning-stale-link"
                          title="Klik untuk menyaring hanya item yang stoknya basi">
                          {stockSummary.stale} item stoknya basi
                        </button>
                        {' '}— angka simpanan berbeda dari stok jual sebenarnya. Kolom “Stok”
                        sudah menampilkan angka <b>LIVE</b>; klik <b>Sinkron Stok FG</b> untuk
                        merapikan angka simpanannya.
                      </div>
                    )}
                    {stockSummary.unlinked > 0 && (
                      <div>
                        <button type="button" onClick={() => setFilterAttention('unlinked')}
                          className="underline decoration-dotted underline-offset-2 font-bold hover:opacity-80"
                          data-testid="catalog-warning-unlinked-link"
                          title="Klik untuk menyaring hanya item yang belum tertaut ke Master Produk">
                          {stockSummary.unlinked} item belum tertaut ke master
                        </button>
                        {' '}— stoknya tidak bisa dihitung otomatis dan tidak bisa dijual lewat
                        alur order. Tautkan varian/FG-nya.
                      </div>
                    )}
                    {stockSummary.counts_truncated && (
                      <div className="text-[11px] opacity-80">
                        Catatan jujur: katalog ini lebih dari {stockSummary.scanned} item, jadi
                        hitungan di atas hanya mencakup {stockSummary.scanned} item pertama.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* F4.4 — TABEL 20 KOLOM + KARTU, aksi penayangan, kelola foto.
                  Tabel lama hanya 5 kolom (Produk/Harga/Stok/Status/Aksi) dan
                  "Status" di situ artinya STOK — sehingga pertanyaan marketing
                  ("mana yang belum tayang? ditolak kenapa? marjinnya berapa?")
                  tidak bisa dijawab walau datanya SUDAH dikirim endpoint. */}
              <CatalogItemsView
                catalog={selectedCatalog}
                token={token}
                items={items}
                stockSummary={stockSummary}
                statusOptions={statusOptions}
                filters={f4}
                onFilterChange={(patch) => setF4((s) => ({ ...s, ...patch }))}
                onEdit={(it) => setItemDialog(it)}
                onDelete={(it) => handleDeleteItem(it)}
                onReload={() => {
                  loadItems(selectedCatalog.id, searchQ, filterStatus, filterCategoryId,
                            filterAttention, f4);
                  loadCatalogs();
                }}
              />
            </>
          )}
        </TabsContent>

        {/* ── TAB 3: STOCK DASHBOARD ── */}
        <TabsContent value="stock" className="space-y-4 mt-4">
          <div className="flex items-center justify-between">
            <p className="font-medium text-sm">Dashboard Stok Multi-Katalog</p>
            <Button size="sm" variant="outline" onClick={loadDashboard}>
              <RefreshCw className="w-4 h-4 mr-1" /> Refresh
            </Button>
          </div>

          {dashboard && (
            <>
              {/* Health bar */}
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">Kesehatan Stok Keseluruhan</span>
                  <span className={`text-xl font-bold ${
                    (dashboard.summary?.health_pct || 0) >= 80 ? 'text-emerald-600 dark:text-emerald-400' :
                    (dashboard.summary?.health_pct || 0) >= 60 ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400'
                  }`}>
                    {dashboard.summary?.health_pct || 0}%
                  </span>
                </div>
                <div className="w-full bg-foreground/10 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-3 rounded-full transition-all ${
                      (dashboard.summary?.health_pct || 0) >= 80 ? 'bg-emerald-500' :
                      (dashboard.summary?.health_pct || 0) >= 60 ? 'bg-amber-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${dashboard.summary?.health_pct || 0}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {dashboard.summary?.in_stock || 0} dari {dashboard.summary?.total_items || 0} item tersedia
                  {dashboard.last_sync && <span> · Sync terakhir: {new Date(dashboard.last_sync.synced_at).toLocaleString('id-ID')}</span>}
                </p>
              </div>

              {/* Per platform */}
              {dashboard.platform_breakdown?.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2 font-medium">Breakdown per Platform</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {dashboard.platform_breakdown.map(p => (
                      <div key={p.platform} className="rounded-lg border border-foreground/10 bg-foreground/5 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium text-sm">{p.platform}</span>
                          <span className="text-xs text-muted-foreground">{p.total} item</span>
                        </div>
                        <div className="flex gap-2 text-xs">
                          <span className="text-emerald-600 dark:text-emerald-400">{p.in_stock || 0} ✓</span>
                          <span className="text-amber-700 dark:text-amber-400">{p.low_stock || 0} ⚠</span>
                          <span className="text-red-700 dark:text-red-400">{p.out_of_stock || 0} ✗</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Low stock alert list */}
              {dashboard.low_stock_items?.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2 font-medium flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400" />
                    Item Perlu Restock ({dashboard.low_stock_items.length})
                  </p>
                  <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                          <th className="text-left px-4 py-2">Produk</th>
                          <th className="text-left px-4 py-2">Platform</th>
                          <th className="text-center px-4 py-2">Stok</th>
                          <th className="text-center px-4 py-2">Min</th>
                          <th className="text-center px-4 py-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {dashboard.low_stock_items.map(item => {
                          const cfg = STOCK_STATUS_CFG[item.stock_status] || STOCK_STATUS_CFG.low_stock;
                          return (
                            <tr key={item.id} className="hover:bg-foreground/5">
                              <td className="px-4 py-2">
                                <div className="font-medium text-xs">{item.name}</div>
                                <div className="text-xs text-muted-foreground">{item.sku}</div>
                              </td>
                              <td className="px-4 py-2 text-xs">{item.platform}</td>
                              <td className="px-4 py-2 text-center">
                                <span className={`font-bold ${cfg.color}`}>{item.stock_quantity}</span>
                              </td>
                              <td className="px-4 py-2 text-center text-xs text-muted-foreground">
                                {item.stock_alert_threshold}
                              </td>
                              <td className="px-4 py-2 text-center">
                                <span className={`text-xs px-1.5 py-0.5 rounded-full border ${cfg.badge} ${cfg.bg}`}>
                                  {cfg.label}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {(!dashboard.low_stock_items || dashboard.low_stock_items.length === 0) && (
                <div className="text-center py-10 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-10 h-10 mx-auto mb-2 opacity-60" />
                  <p className="text-sm">Semua item stok aman 🎉</p>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 4: HISTORY ── */}
        <TabsContent value="history" className="space-y-4 mt-4">
          {selectedCatalog && (
            <>
              <div className="flex items-center justify-between">
                <p className="font-medium text-sm">Riwayat Stok — {selectedCatalog.name}</p>
                <Button size="sm" variant="outline" onClick={() => loadHistory(selectedCatalog.id)}>
                  <RefreshCw className="w-4 h-4 mr-1" /> Refresh
                </Button>
              </div>
              {history.length === 0 && (
                <div className="text-center py-12 text-muted-foreground">
                  <History className="w-10 h-10 mx-auto mb-3 opacity-20" />
                  <p className="text-sm">Belum ada riwayat sinkronisasi</p>
                </div>
              )}
              {history.length > 0 && (
                <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                        <th className="text-left px-4 py-3">Produk</th>
                        <th className="text-center px-4 py-3">Sebelum</th>
                        <th className="text-center px-4 py-3">Delta</th>
                        <th className="text-center px-4 py-3">Sesudah</th>
                        <th className="text-left px-4 py-3">Tipe</th>
                        <th className="text-left px-4 py-3">Waktu</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {history.map(log => (
                        <tr key={log.id} className="hover:bg-foreground/5">
                          <td className="px-4 py-2">
                            <div className="font-medium text-xs">{log.name}</div>
                            <div className="text-xs text-muted-foreground">{log.sku}</div>
                          </td>
                          <td className="px-4 py-2 text-center text-xs">{log.old_stock}</td>
                          <td className="px-4 py-2 text-center">
                            <span className={`text-xs font-bold ${log.delta > 0 ? 'text-emerald-600 dark:text-emerald-400' : log.delta < 0 ? 'text-red-700 dark:text-red-400' : 'text-muted-foreground'}`}>
                              {log.delta > 0 ? '+' : ''}{log.delta}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-center text-xs font-medium">{log.new_stock}</td>
                          <td className="px-4 py-2 text-xs">
                            <span className="px-1.5 py-0.5 rounded bg-foreground/10 text-muted-foreground capitalize">
                              {log.sync_type?.replace('_', ' ')}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-xs text-muted-foreground">
                            {new Date(log.synced_at).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 5: ISI DARI MASTER PRODUK ──────────────────────────────────
            Jalur lama hanya bisa menambah SATU varian ke SATU katalog per aksi;
            untuk 9 toko × puluhan varian itu ratusan klik, dan yang benar-benar
            terjadi bukan "staf sabar" melainkan katalog dibiarkan KOSONG —
            sehingga item pesanan hasil impor tidak bisa ditautkan ke master dan
            marjin per pesanan tidak bisa dihitung sama sekali. */}
        <TabsContent value="from-master" className="mt-4">
          {tab === 'from-master' && (
            <CatalogFromMasterModule
              token={token}
              onAssigned={() => { loadCatalogs(); loadDashboard(); }}
            />
          )}
        </TabsContent>
      </Tabs>

      {/* ── DIALOGS ── */}
      {catalogDialog !== null && (
        <CatalogDialog
          initial={catalogDialog}
          accounts={accounts}
          onSave={handleSaveCatalog}
          onClose={() => setCatalogDialog(null)}
        />
      )}

      {itemDialog !== null && selectedCatalog && (
        <ItemDialog
          initial={itemDialog}
          catalog={selectedCatalog}
          token={token}
          productCategories={productCategories}
          onSave={handleSaveItem}
          onClose={() => setItemDialog(null)}
        />
      )}

      {stockDialog !== null && (
        <StockUpdateDialog
          item={stockDialog}
          onSave={handleUpdateStock}
          onClose={() => setStockDialog(null)}
        />
      )}

      {bulkStockDialog && selectedCatalog && (
        <BulkStockDialog
          items={items}
          data={bulkStockData}
          onChange={setBulkStockData}
          onSave={handleBulkStockSave}
          onClose={() => { setBulkStockDialog(false); setBulkStockData({}); }}
        />
      )}
    </div>
  );
}

// ─── Catalog Card ─────────────────────────────────────────────────────────────

function CatalogCard({ catalog, isSelected, onSelect, onEdit, onDelete }) {
  const totalItems = catalog.item_count || 0;
  const lowStock = catalog.low_stock_count || 0;
  const outStock = catalog.out_of_stock_count || 0;
  const health = totalItems > 0
    ? Math.round((totalItems - lowStock - outStock) / totalItems * 100)
    : 100;

  return (
    <div className={`rounded-xl border p-4 space-y-3 cursor-pointer transition-all ${
      isSelected
        ? 'border-indigo-500/50 bg-indigo-100 dark:bg-indigo-500/10'
        : 'border-foreground/10 bg-foreground/5 hover:border-foreground/20 hover:bg-foreground/[0.08]'
    }`} onClick={onSelect}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <p className="font-semibold text-sm">{catalog.name}</p>
            {!catalog.is_active && <Badge variant="outline" className="text-xs">Nonaktif</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <PlatformBadge platform={catalog.platform} />
            <span className="text-xs text-muted-foreground">{catalog.account_name}</span>
          </div>
          {catalog.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{catalog.description}</p>
          )}
        </div>
        <div className="flex gap-1 ml-2">
          <button className="p-1 hover:bg-foreground/10 rounded" onClick={e => { e.stopPropagation(); onEdit(); }}>
            <Edit2 className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button className="p-1 hover:bg-foreground/10 rounded" onClick={e => { e.stopPropagation(); onDelete(); }}>
            <Trash2 className="w-3.5 h-3.5 text-red-700 dark:text-red-400" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-foreground/5 px-2 py-1.5">
          <div className="font-bold text-sm">{totalItems}</div>
          <div className="text-xs text-muted-foreground">Item</div>
        </div>
        <div className="rounded-lg bg-amber-100 dark:bg-amber-500/10 px-2 py-1.5">
          <div className="font-bold text-sm text-amber-700 dark:text-amber-400">{lowStock}</div>
          <div className="text-xs text-muted-foreground">Rendah</div>
        </div>
        <div className="rounded-lg bg-red-100 dark:bg-red-500/10 px-2 py-1.5">
          <div className="font-bold text-sm text-red-700 dark:text-red-400">{outStock}</div>
          <div className="text-xs text-muted-foreground">Habis</div>
        </div>
      </div>

      {/* Health bar */}
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-muted-foreground">Kesehatan Stok</span>
          <span className={health >= 80 ? 'text-emerald-600 dark:text-emerald-400' : health >= 60 ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400'}>
            {health}%
          </span>
        </div>
        <div className="w-full bg-foreground/10 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full ${health >= 80 ? 'bg-emerald-500' : health >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
            style={{ width: `${health}%` }}
          />
        </div>
      </div>

      <Button size="sm" variant="outline" className="w-full text-xs" onClick={onSelect}>
        <Eye className="w-3.5 h-3.5 mr-1" /> Lihat Item
      </Button>
    </div>
  );
}

// ─── Platform Badge ───────────────────────────────────────────────────────────

function PlatformBadge({ platform }) {
  const cfg = {
    'Shopee': 'bg-orange-100 dark:bg-orange-500/20 text-orange-600 dark:text-orange-300 border-orange-400 dark:border-orange-500/30',
    'TikTok Shop': 'bg-pink-100 dark:bg-pink-500/20 text-pink-600 dark:text-pink-300 border-pink-400 dark:border-pink-500/30',
    'Tokopedia': 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-300 border-green-400 dark:border-green-500/30',
    'Lazada': 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-500/30',
    'Blibli': 'bg-blue-600/20 text-blue-200 border-blue-600/30',
  }[platform] || 'bg-foreground/10 text-muted-foreground border-foreground/10';
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded-full border ${cfg}`}>{platform}</span>
  );
}

// ─── Catalog Dialog ───────────────────────────────────────────────────────────

function CatalogDialog({ initial, accounts, onSave, onClose }) {
  const [form, setForm] = useState({ is_active: true, name: '', description: '', account_id: '', platform: '', ...initial });
  const [saving, setSaving] = useState(false);

  // Auto-fill platform from account
  useEffect(() => {
    if (form.account_id) {
      const acc = accounts.find(a => a.id === form.account_id);
      if (acc) setForm(f => ({ ...f, platform: acc.platform }));
    }
  }, [form.account_id, accounts]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            {form.id ? 'Edit Katalog' : 'Buat Katalog Baru'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label className="text-xs">Akun Platform *</Label>
            <SmartNativeSelect
              className="w-full text-sm rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
              value={form.account_id}
              onChange={e => setForm(f => ({ ...f, account_id: e.target.value }))}
              required
            >
              <option value="">-- Pilih Akun --</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.platform} — {a.name}</option>)}
            </SmartNativeSelect>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Nama Katalog *</Label>
            <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="mis. Katalog Produk Utama" required />
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Deskripsi</Label>
            <Textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={2} />
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" id="is_active" checked={form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
            <Label htmlFor="is_active" className="text-xs cursor-pointer">Aktif</Label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving} className="bg-indigo-600 hover:bg-indigo-700">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Item Dialog ──────────────────────────────────────────────────────────────

function ItemDialog({ initial, catalog, token, productCategories = [], onSave, onClose }) {
  const isEdit = !!initial.id;
  // Mode: 'from_fg' (default for new) | 'manual' (legacy / for editing existing)
  const [mode, setMode] = useState(isEdit ? 'manual' : 'from_fg');
  const [fgPickerOpen, setFgPickerOpen] = useState(false);
  const [fgPreview, setFgPreview] = useState(null);

  const [form, setForm] = useState({
    is_active: true, sku: '', name: '', description: '', price: 0,
    original_price: 0, platform_price: 0, stock_quantity: 0, stock_alert_threshold: 10,
    material_id: '', fg_material_id: '', platform_url: '', weight_gram: 0,
    category: '', variant_info: '', variant_id: '',
    ...initial,
    // Kompat: item lama mungkin hanya punya price/original_price.
    // CATATAN 2026-07-25: default `harga_jual/harga_coret/harga_original/hpp/tags: 0|''`
    // yang dulu ditulis DI ATAS `...initial` dihapus karena SELALU ditimpa baris di
    // bawah ini (duplikat kunci objek → lint error, dan menyesatkan pembaca).
    harga_jual: initial.harga_jual ?? initial.price ?? 0,
    harga_coret: initial.harga_coret ?? initial.original_price ?? 0,
    harga_original: initial.harga_original ?? 0,
    hpp: initial.hpp ?? 0,
    category_id: initial.category_id ?? '',
    tags: Array.isArray(initial.tags) ? initial.tags.join(', ') : (initial.tags || ''),
  });
  const [saving, setSaving] = useState(false);

  // F6 — kategori item katalog MILIK MASTER PRODUK.
  // Item yang tertaut master (dibuat dari FG / punya varian) kategorinya turun
  // otomatis dan TIDAK boleh diubah di sini; server pun menolaknya. Item manual
  // lama boleh memilih kategori, tetapi HANYA dari master (bukan teks bebas):
  // dulu teks bebas yang tidak cocok master diam-diam hilang saat disimpan.
  const linkedToMaster = !!(form.fg_material_id || form.material_id || form.variant_id)
    || mode === 'from_fg';
  const masterCategoryLabel = [initial.category_code, initial.category_name || initial.category]
    .filter(Boolean).join(' · ');

  // Fase 3b: daftar varian produksi internal (rahaza_model_variants) utk penautan stok Toko<->FG
  const [prodVariants, setProdVariants] = useState([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${API}/api/rahaza/variants`, { headers: { Authorization: `Bearer ${token}` } });
        if (r.ok && !cancelled) {
          const data = await r.json();
          setProdVariants(Array.isArray(data) ? data : (data.variants || data.items || []));
        }
      } catch (_e) { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // If editing item that came from FG, show its FG preview
  useEffect(() => {
    if (isEdit && (initial.fg_material_id || initial.source === 'from_fg')) {
      setFgPreview({
        id: initial.fg_material_id || initial.material_id,
        code: initial.fg_code || initial.sku,
        name: initial.fg_name || initial.name,
        color: initial.fg_color || '',
        unit: initial.unit || 'pcs',
        stock_qty: initial.stock_quantity,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFGSelect = (fg) => {
    setFgPreview(fg);
    setForm(f => ({
      ...f,
      fg_material_id: fg.id,
      sku: (fg.code || '').toUpperCase(),
      name: fg.name || '',
      category: fg.category || fg.subtype || '',
      variant_info: [
        fg.color ? `Warna: ${fg.color}` : null,
        readField(fg, FIELD.composition) ? `Material: ${readField(fg, FIELD.composition)}` : null,
      ].filter(Boolean).join(' | '),
      stock_quantity: fg.stock_qty || 0,
      weight_gram: fg.weight_gram || 0,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (mode === 'from_fg' && !form.fg_material_id) {
      toast.error('Pilih produk dari Master FG dulu');
      return;
    }
    setSaving(true);
    try {
      await onSave({ ...form, _mode: mode });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="catalog-item-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingBag className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            {isEdit ? 'Edit Item' : 'Tambah Item Baru'}
            <span className="text-xs text-muted-foreground font-normal">— {catalog.name}</span>
          </DialogTitle>
        </DialogHeader>

        {/* Mode switcher — hide on edit (mode locked to manual) */}
        {!isEdit && (
          <div className="flex gap-2 p-1 bg-muted/50 rounded-md">
            <button
              type="button"
              onClick={() => setMode('from_fg')}
              className={`flex-1 px-3 py-2 rounded text-sm font-medium transition-colors ${
                mode === 'from_fg'
                  ? 'bg-indigo-600 text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              data-testid="mode-from-fg"
            >
              📦 Dari Master FG (Recommended)
            </button>
            <button
              type="button"
              onClick={() => setMode('manual')}
              className={`flex-1 px-3 py-2 rounded text-sm font-medium transition-colors ${
                mode === 'manual'
                  ? 'bg-indigo-600 text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              data-testid="mode-manual"
            >
              ✏️ Manual (Legacy)
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          {/* FG Mode: Show FG picker */}
          {mode === 'from_fg' && (
            <div className="space-y-2">
              <Label className="text-xs">Produk Master FG *</Label>
              {fgPreview ? (
                <div className="p-3 rounded-md border-2 border-indigo-400 dark:border-indigo-500/30 bg-indigo-100 dark:bg-indigo-500/5 space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm">{fgPreview.name}</div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <code className="px-1.5 py-0.5 bg-muted rounded font-mono">{fgPreview.code}</code>
                        {fgPreview.color && <span>{fgPreview.color}</span>}
                        <span>Stok master: <b>{fgPreview.stock_qty || 0}</b></span>
                      </div>
                    </div>
                    {!isEdit && (
                      <Button type="button" size="sm" variant="ghost" onClick={() => setFgPickerOpen(true)}>
                        Ganti
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full justify-start border-dashed h-auto py-3"
                  onClick={() => setFgPickerOpen(true)}
                  data-testid="open-fg-picker"
                >
                  <Search className="w-4 h-4 mr-2" />
                  Pilih dari Master FG (Finished Goods)...
                </Button>
              )}
              <p className="text-[11px] text-muted-foreground">
                💡 Pilih produk dari Inventory FG agar SKU, nama, dan stock tersinkronisasi otomatis.
              </p>
            </div>
          )}

          {/* Manual fields — disabled when FG mode aktif dan belum pilih FG; editable saat manual mode */}
          {(mode === 'manual' || fgPreview) && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">SKU * {mode === 'from_fg' && <span className="text-muted-foreground">(auto dari FG)</span>}</Label>
                  <Input
                    value={form.sku}
                    onChange={e => setForm(f => ({ ...f, sku: e.target.value }))}
                    placeholder="SKU-001"
                    required
                    readOnly={mode === 'from_fg'}
                    className={mode === 'from_fg' ? 'bg-muted/30' : ''}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Kategori</Label>
                  {linkedToMaster ? (
                    <>
                      <div className="flex items-center gap-2 h-9 px-3 rounded-md border border-input bg-muted/30 text-sm text-foreground"
                        data-testid="item-category-readonly">
                        {(initial.category_code || form.category_code) && (
                          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300">
                            {initial.category_code || form.category_code}
                          </span>
                        )}
                        <span className={masterCategoryLabel || form.category ? '' : 'text-muted-foreground'}>
                          {initial.category_name || form.category_name || form.category
                            || 'otomatis dari Master Produk'}
                        </span>
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        Mengikuti Master Produk — ubah kategorinya di Master Produk,
                        lalu klik “Segarkan dari Master”.
                      </p>
                    </>
                  ) : (
                    <>
                      <select
                        className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm text-foreground"
                        value={form.category_id || ''}
                        onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))}
                        data-testid="item-category-select"
                      >
                        <option value="">— pilih kategori —</option>
                        {productCategories.map(c => (
                          <option key={c.id} value={c.id}>{c.sku_prefix} · {c.name}</option>
                        ))}
                      </select>
                      <p className="text-[10px] text-muted-foreground">
                        Dari Master Kategori Produk (bukan teks bebas) supaya
                        pengelompokan katalog bisa dipercaya.
                      </p>
                    </>
                  )}
                </div>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Nama Produk * {mode === 'from_fg' && <span className="text-muted-foreground">(auto dari FG)</span>}</Label>
                <Input
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Nama lengkap produk"
                  required
                  readOnly={mode === 'from_fg'}
                  className={mode === 'from_fg' ? 'bg-muted/30' : ''}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Varian {mode === 'from_fg' && <span className="text-muted-foreground">(auto dari FG)</span>}</Label>
                <Input
                  value={form.variant_info}
                  onChange={e => setForm(f => ({ ...f, variant_info: e.target.value }))}
                  placeholder="mis. Warna: Hitam, Putih | Size: S, M, L"
                  readOnly={mode === 'from_fg'}
                  className={mode === 'from_fg' ? 'bg-muted/30' : ''}
                />
              </div>

              {mode === 'manual' && (
                <div className="space-y-1">
                  <Label className="text-xs">Tautkan Varian Produksi (opsional)</Label>
                  <Select
                    value={form.variant_id || 'none'}
                    onValueChange={(val) => {
                      if (val === 'none') { setForm(f => ({ ...f, variant_id: '' })); return; }
                      const v = prodVariants.find(x => x.id === val);
                      setForm(f => ({
                        ...f,
                        variant_id: val,
                        sku: (f.sku && f.sku.trim()) ? f.sku : (v?.sku || ''),
                        variant_info: f.variant_info || (v ? `Warna: ${v.color_name}, Size: ${v.size_code}` : ''),
                      }));
                    }}
                  >
                    <SelectTrigger data-testid="catalog-variant-selector">
                      <SelectValue placeholder="— Tidak ditautkan —" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">— Tidak ditautkan —</SelectItem>
                      {prodVariants.map(v => (
                        <SelectItem key={v.id} value={v.id}>{v.sku} · {v.color_name} {v.size_code}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">Tautkan ke SKU varian produksi internal agar stok Toko ↔ FG selaras.</p>
                </div>
              )}

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Harga Jual (Rp) *</Label>
                  <Input type="number" min={0} value={form.harga_jual}
                    data-testid="catalog-input-harga-jual"
                    onChange={e => setForm(f => ({ ...f, harga_jual: e.target.value, price: e.target.value }))} required />
                  <p className="text-[10px] text-muted-foreground">Harga final ke customer</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Harga Coret (Rp)</Label>
                  <Input type="number" min={0} value={form.harga_coret}
                    data-testid="catalog-input-harga-coret"
                    onChange={e => setForm(f => ({ ...f, harga_coret: e.target.value, original_price: e.target.value }))} />
                  <p className="text-[10px] text-muted-foreground">Dicoret utk promo (≥ jual)</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Harga Original / List (Rp)</Label>
                  <Input type="number" min={0} value={form.harga_original}
                    data-testid="catalog-input-harga-original"
                    onChange={e => setForm(f => ({ ...f, harga_original: e.target.value }))} />
                  <p className="text-[10px] text-muted-foreground">Harga normal / list resmi</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Harga Platform (Rp)</Label>
                  <Input type="number" min={0} value={form.platform_price} onChange={e => setForm(f => ({ ...f, platform_price: e.target.value }))} />
                  <p className="text-[10px] text-muted-foreground">Harga tertera di marketplace</p>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs flex items-center gap-1">HPP (Rp) <span className="text-muted-foreground">— dari RnD</span></Label>
                  <Input type="number" value={form.hpp || 0} readOnly disabled
                    data-testid="catalog-input-hpp"
                    className="bg-muted/40 cursor-not-allowed" />
                  <p className="text-[10px] text-muted-foreground">
                    Biaya pokok (internal), otomatis dari RnD. Tidak tampil ke customer.
                  </p>
                </div>
              </div>

              {/* Stock fields — only show in manual mode (FG mode auto-syncs from master) */}
              {mode === 'manual' && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Stok Awal</Label>
                    <Input type="number" min={0} value={form.stock_quantity} onChange={e => setForm(f => ({ ...f, stock_quantity: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Alert Min Stok</Label>
                    <Input type="number" min={0} value={form.stock_alert_threshold} onChange={e => setForm(f => ({ ...f, stock_alert_threshold: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Berat (gram)</Label>
                    <Input type="number" min={0} value={form.weight_gram} onChange={e => setForm(f => ({ ...f, weight_gram: e.target.value }))} />
                  </div>
                </div>
              )}
              {mode === 'from_fg' && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Alert Min Stok</Label>
                    <Input type="number" min={0} value={form.stock_alert_threshold} onChange={e => setForm(f => ({ ...f, stock_alert_threshold: e.target.value }))} />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Stok (auto)</Label>
                    <Input type="number" value={form.stock_quantity} readOnly className="bg-muted/30" />
                  </div>
                </div>
              )}

              <div className="space-y-1">
                <Label className="text-xs">URL Platform (opsional)</Label>
                <Input value={form.platform_url} onChange={e => setForm(f => ({ ...f, platform_url: e.target.value }))} placeholder="https://shopee.co.id/..." />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Tags (pisahkan dengan koma)</Label>
                <Input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} placeholder="fashion, wanita, summer, bestseller" />
              </div>

              {mode === 'manual' && (
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="item_active" checked={form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
                  <Label htmlFor="item_active" className="text-xs cursor-pointer">Item Aktif</Label>
                </div>
              )}
            </>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button
              type="submit"
              disabled={saving || (mode === 'from_fg' && !form.fg_material_id)}
              className="bg-indigo-600 hover:bg-indigo-700"
              data-testid="save-item-btn"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>

        {/* FG Picker Dialog */}
        <FGProductPickerDialog
          open={fgPickerOpen}
          onOpenChange={setFgPickerOpen}
          onSelect={handleFGSelect}
          token={token}
          title="Pilih Produk dari Master FG"
          description={`Pilih produk Finished Goods untuk ditambahkan ke katalog "${catalog.name}".`}
        />
      </DialogContent>
    </Dialog>
  );
}

// ─── Stock Update Dialog ──────────────────────────────────────────────────────

function StockUpdateDialog({ item, onSave, onClose }) {
  const [qty, setQty] = useState(item.stock_quantity || 0);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const delta = qty - (item.stock_quantity || 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave({ ...item, stock_quantity: parseFloat(qty) || 0, notes });
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <ArrowRightLeft className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            Update Stok — {item.name}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 px-4 py-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">SKU</span>
              <span>{item.sku}</span>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-muted-foreground">Stok Saat Ini</span>
              <span className="font-bold">{item.stock_quantity}</span>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-muted-foreground">Min Alert</span>
              <span>{item.stock_alert_threshold}</span>
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Stok Baru</Label>
            <Input
              type="number" min={0} step={1}
              value={qty}
              onChange={e => setQty(e.target.value)}
              autoFocus
              required
            />
            {delta !== 0 && (
              <p className={`text-xs ${delta > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                {delta > 0 ? `+${delta}` : delta} dari stok saat ini
              </p>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Catatan</Label>
            <Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="mis. Restock dari gudang, Koreksi opname..." />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving} className="bg-blue-600 hover:bg-blue-700">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Update Stok
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Bulk Stock Dialog ────────────────────────────────────────────────────────

function BulkStockDialog({ items, data, onChange, onSave, onClose }) {
  const editCount = Object.values(data).filter(v => v.qty !== '' && v.qty !== undefined).length;

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            Bulk Update Stok ({editCount} item diubah)
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Isi stok baru untuk item yang ingin diupdate. Kosongkan jika tidak ingin mengubah.
          </p>
          <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-foreground/10 text-xs text-muted-foreground bg-foreground/5">
                  <th className="text-left px-4 py-2">Produk / SKU</th>
                  <th className="text-center px-4 py-2">Stok Saat Ini</th>
                  <th className="text-center px-4 py-2 text-blue-600 dark:text-blue-300">Stok Baru</th>
                  <th className="text-left px-4 py-2">Catatan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {items.map(item => {
                  const d = data[item.id] || {};
                  const hasInput = d.qty !== '' && d.qty !== undefined;
                  return (
                    <tr key={item.id} className={hasInput ? 'bg-blue-100 dark:bg-blue-500/5' : 'hover:bg-foreground/5'}>
                      <td className="px-4 py-2">
                        <div className="text-xs font-medium">{item.name}</div>
                        <div className="text-xs text-muted-foreground">{item.sku}</div>
                      </td>
                      <td className="px-4 py-2 text-center text-sm font-bold">{item.stock_quantity}</td>
                      <td className="px-4 py-2 text-center">
                        <input
                          type="number" min={0} step={1}
                          placeholder="—"
                          value={d.qty ?? ''}
                          onChange={e => onChange(prev => ({
                            ...prev,
                            [item.id]: { ...prev[item.id], qty: e.target.value }
                          }))}
                          className="w-20 text-center rounded border border-foreground/10 bg-foreground/5 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          type="text"
                          placeholder="Catatan..."
                          value={d.notes ?? ''}
                          onChange={e => onChange(prev => ({
                            ...prev,
                            [item.id]: { ...prev[item.id], notes: e.target.value }
                          }))}
                          className="w-full rounded border border-foreground/10 bg-foreground/5 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={onSave} disabled={!editCount}>
            <Save className="w-4 h-4 mr-1" /> Simpan {editCount > 0 ? `(${editCount})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
