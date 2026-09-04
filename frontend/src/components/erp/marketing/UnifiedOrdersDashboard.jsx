import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShoppingBag, Package, Truck, CheckCircle2, XCircle, RotateCcw,
  Search, Filter, RefreshCw, ChevronRight, ChevronDown, List,
  TrendingUp, DollarSign, AlertCircle, AlertTriangle, Download, Loader2, X, ClipboardList
} from 'lucide-react';
import OnwardCTA from '../OnwardCTA';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import { MarketingAccountSelect } from './pickers/MarketingPickers';
// F10 (sesi #10) — angka yang benar di layar tidak ada gunanya kalau tidak bisa
// dibawa ke rapat. Satu pembuat CSV untuk semua layar daftar (lib/csv.js).
import ExportCsvButton from '@/components/ui/export-csv-button';


const API = process.env.REACT_APP_BACKEND_URL;

// ── Constants ──
const STATUS_CONFIG = {
  new:       { label: 'Baru',      color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',      icon: ShoppingBag,   dot: 'bg-blue-500'   },
  packed:    { label: 'Dikemas',   color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',  icon: Package,       dot: 'bg-amber-500'  },
  shipped:   { label: 'Dikirim',   color: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300', icon: Truck,        dot: 'bg-indigo-500' },
  delivered: { label: 'Terkirim', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2, dot: 'bg-emerald-500' },
  cancelled: { label: 'Batal',    color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',         icon: XCircle,       dot: 'bg-red-500'    },
  returned:  { label: 'Retur',    color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300', icon: RotateCcw,    dot: 'bg-orange-500' },
};

const PLATFORM_ICONS = { shopee: '🛒', tiktok: '🎵', tokopedia: '🟢', default: '🚧' };

function fmt(n) { return new Intl.NumberFormat('id-ID').format(n || 0); }
function fmtRp(n) { return `Rp ${fmt(n)}`; }
function fmtDate(d) {
  if (!d) return '-';
  return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.new;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${c.color}`}>
      <Icon size={11} />{c.label}
    </span>
  );
}

function PlatformBadge({ platform }) {
  const icon = PLATFORM_ICONS[platform] || PLATFORM_ICONS.default;
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-muted font-medium capitalize">
      {icon} {platform}
    </span>
  );
}

// ── Order Detail Drawer ──
function OrderDetailDrawer({ order, open, onClose, onStatusChange }) {
  const [updating, setUpdating] = useState(false);
  const [newStatus, setNewStatus] = useState('');
  const [note, setNote] = useState('');
  const { toast } = useToast();

  if (!order) return null;

  const validNextStatuses = {
    new: ['packed', 'cancelled'],
    packed: ['shipped', 'cancelled'],
    shipped: ['delivered', 'returned'],
    delivered: ['returned'],
    cancelled: [],
    returned: [],
  };

  const handleStatusUpdate = async () => {
    if (!newStatus) return;
    setUpdating(true);
    try {
      const res = await axios.patch(`${API}/api/marketing/orders/${order.id}/status`,
        { status: newStatus, note },
        { headers: { Authorization: `Bearer ${localStorage.getItem('erp_token')}` } }
      );
      const freed = Number(res?.data?.reservation_released || 0);
      toast({
        title: `Status diubah ke ${STATUS_CONFIG[newStatus]?.label || newStatus}`,
        description: freed > 0
          ? `Reservasi stok ${freed.toLocaleString('id-ID')} pcs dilepas kembali ke stok jual.`
          : undefined,
      });
      onStatusChange();
      onClose();
    } catch (e) {
      // F10 — alasan penolakan WAJIB sampai ke layar. Backend sekarang menolak
      // transisi berbahaya (mis. menghidupkan order yang sudah dibatalkan, yang
      // akan menjual stok yang sama dua kali) dengan penjelasan lengkap; pesan
      // generik "Gagal update status" membuat staf mengira sistemnya rusak.
      toast({
        title: 'Status tidak bisa diubah',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally {
      setUpdating(false);
    }
  };

  const nexts = validNextStatuses[order.status] || [];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingBag size={16} />
            {order.order_id}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {/* Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Status</span>
            <StatusBadge status={order.status} />
          </div>
          {/* Order Info */}
          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Info Pesanan</p>
            {[
              { label: 'Platform', value: <PlatformBadge platform={order.platform} /> },
              { label: 'Akun',     value: order.account_name },
              { label: 'Produk',   value: order.product_name },
              { label: 'Variasi',  value: order.variation },
              { label: 'SKU',      value: <span className="font-mono text-xs">{order.sku_id}</span> },
              { label: 'Qty',      value: order.quantity },
              { label: 'Harga',    value: fmtRp(order.price_final) },
              { label: 'Diskon',   value: order.discount_seller > 0 ? fmtRp(order.discount_seller) : '-' },
              { label: 'Ongkir',   value: fmtRp(order.shipping_cost) },
              { label: 'Total',    value: <strong>{fmtRp(order.total_payment)}</strong> },
              { label: 'Metode',   value: order.payment_method },
            ].map(r => (
              <div key={r.label} className="flex justify-between text-sm">
                <span className="text-muted-foreground w-24 flex-shrink-0">{r.label}</span>
                <span className="text-right flex-1">{r.value}</span>
              </div>
            ))}
          </div>
          {/* Shipping Info */}
          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Info Pengiriman</p>
            {[
              { label: 'Penerima',  value: order.customer_name },
              { label: 'Kota',      value: order.city },
              { label: 'Kurir',     value: order.courier },
              { label: 'Resi',      value: order.tracking_number || '-' },
              { label: 'Pesan',     value: order.order_date ? fmtDate(order.order_date) : '-' },
              { label: 'Dikemas',   value: order.packed_date ? fmtDate(order.packed_date) : '-' },
              { label: 'Dikirim',   value: order.shipped_date ? fmtDate(order.shipped_date) : '-' },
              { label: 'Terkirim',  value: order.delivered_date ? fmtDate(order.delivered_date) : '-' },
            ].map(r => (
              <div key={r.label} className="flex justify-between text-sm">
                <span className="text-muted-foreground w-24 flex-shrink-0">{r.label}</span>
                <span className="text-right flex-1">{r.value}</span>
              </div>
            ))}
          </div>
          {/* Update Status */}
          {nexts.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Update Status</p>
              <Select value={newStatus} onValueChange={setNewStatus}>
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Pilih status baru..." />
                </SelectTrigger>
                <SelectContent>
                  {nexts.map(s => (
                    <SelectItem key={s} value={s}>{STATUS_CONFIG[s]?.label || s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input placeholder="Catatan (opsional)" value={note} onChange={e => setNote(e.target.value)} className="h-9 text-sm" />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Tutup</Button>
          {nexts.length > 0 && (
            <Button onClick={handleStatusUpdate} disabled={!newStatus || updating}>
              {updating && <Loader2 size={13} className="mr-1 animate-spin" />}
              Simpan
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Picking List Modal ──
// BUG (ditemukan lewat lint, 2026-08-14): komponen ini dulu memakai
// `accountFilter` yang HANYA ADA di komponen induk ⇒ `ReferenceError` begitu
// modal dibuka (layar putih). Tidak pernah terlihat sebagai galat build karena
// JavaScript baru mengeluh saat baris itu benar-benar dijalankan. Sekarang
// lingkup toko DIKIRIM sebagai prop — jadi daftar picking mengikuti toko yang
// sedang dipilih di layar, bukan diam-diam semua toko.
function PickingListModal({ open, onClose, token, accountFilter = '' }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [platform, setPlatform] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { statuses: 'new,packed' };
      if (accountFilter) params.account_id = accountFilter;
      if (platform) params.platform = platform;
      const res = await axios.get(`${API}/api/marketing/orders/picking-list`, {
        params,
        headers: {
          // Kunci token yang benar untuk app ini adalah `erp_token`
          // (lihat `lib/apiFetch.js`); `auth_token` tidak pernah ada ⇒ tanpa
          // prop `token`, permintaan ini akan 401 tanpa penjelasan.
          Authorization: `Bearer ${token || localStorage.getItem('erp_token') || ''}`,
        },
      });
      setData(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [platform, token, accountFilter]);

  useEffect(() => { if (open) load(); }, [open, load]);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardList size={16} /> Picking List
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Select value={platform || 'all'} onValueChange={v => setPlatform(v === 'all' ? '' : v)}>
              <SelectTrigger className="w-[140px] h-8 text-xs">
                <SelectValue placeholder="Semua Platform" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Platform</SelectItem>
                <SelectItem value="shopee">🛒 Shopee</SelectItem>
                <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" className="h-8" onClick={load}>
              <RefreshCw size={12} className="mr-1" /> Refresh
            </Button>
            {data && (
              <span className="text-xs text-muted-foreground ml-auto">
                {data.total_items} SKU | {data.total_orders} order
              </span>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto border rounded-lg">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="animate-spin" size={20} />
              </div>
            ) : !data || data.picking_list.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
                Tidak ada order untuk dikemas
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-muted/50 sticky top-0">
                  <tr>
                    {['SKU', 'Variasi', 'Produk', 'Total Qty', 'Order'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-semibold text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.picking_list.map((item, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="px-3 py-2 font-mono font-semibold">{item.sku_id}</td>
                      <td className="px-3 py-2 text-muted-foreground">{item.variation}</td>
                      <td className="px-3 py-2 max-w-[180px] truncate" title={item.product_name}>{item.product_name}</td>
                      <td className="px-3 py-2">
                        <span className="font-bold text-base text-primary">{item.total_qty}</span>
                        <span className="text-muted-foreground ml-1">pcs</span>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{item.order_count} order</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ──
export default function UnifiedOrdersDashboard({ token, onNavigate }) {
  const { toast } = useToast();
  const [summary, setSummary] = useState(null);
  const [orders, setOrders] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [page, setPage] = useState(1);

  // UI state
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showPickingList, setShowPickingList] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkStatus, setBulkStatus] = useState('');
  const [bulkDialog, setBulkDialog] = useState(false);
  // F10 — hasil bulk per-order (order mana yang GAGAL & kenapa). Sebelum ini
  // jalur bulk selalu melapor sukses, jadi order yang tidak berubah tidak pernah
  // terlihat oleh staf.
  const [bulkResult, setBulkResult] = useState(null);

  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };
  const searchRef = useRef(null);
  const debounceRef = useRef(null);

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await axios.get(`${API}/api/marketing/orders/summary`, { headers: authH });
      setSummary(res.data);
    } finally { setSummaryLoading(false); }
  }, [token]); // eslint-disable-line

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 25 };
      // F14 — filter per TOKO memakai `account_id` (SSOT), bukan mencocokkan nama.
      // Sebelum ini 60/60 order tidak punya `account_id` sehingga pemilih akun di
      // layar ini selalu mengembalikan daftar kosong.
      if (accountFilter)  params.account_id = accountFilter;
      if (statusFilter)   params.status   = statusFilter;
      if (platformFilter) params.platform = platformFilter;
      if (search)         params.search   = search;
      const res = await axios.get(`${API}/api/marketing/orders`, { params, headers: authH });
      setOrders(res.data.orders || []);
      setPagination(res.data.pagination);
    } finally { setLoading(false); }
  }, [page, statusFilter, platformFilter, accountFilter, search, token]); // eslint-disable-line

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setPage(1), 400);
  };

  const handleBulkStatus = async () => {
    if (!bulkStatus || selectedIds.size === 0) return;
    try {
      const res = await axios.post(`${API}/api/marketing/orders/bulk-status`,
        { order_ids: Array.from(selectedIds), status: bulkStatus },
        { headers: authH }
      );
      // F10 — backend sekarang melapor per-order. Kegagalan TIDAK boleh ditelan:
      // dulu jalur ini selalu bilang "N order diupdate" walau tidak ada yang
      // berubah, dan (lebih buruk) membatalkan order TANPA melepas reservasi
      // stoknya. Sekarang staf melihat berapa yang berhasil, berapa yang tidak,
      // alasannya, dan berapa stok yang dilepas kembali.
      const d = res.data || {};
      const done = d.updated_count ?? selectedIds.size;
      const failed = d.failed_count || 0;
      const freed = Number(d.reservation_released || 0);
      setBulkResult(failed ? { failed: d.failed || [], done, status: bulkStatus } : null);
      toast({
        title: `${done} order diubah ke ${STATUS_CONFIG[bulkStatus]?.label}`
          + (failed ? ` · ${failed} gagal` : ''),
        description: freed > 0
          ? `Reservasi stok ${freed.toLocaleString('id-ID')} pcs dilepas kembali ke stok jual.`
          : (failed ? (d.failed || [])[0]?.reason : undefined),
        variant: failed ? 'destructive' : undefined,
      });
      setSelectedIds(new Set()); setBulkStatus('');
      fetchOrders(); fetchSummary();
    } catch (e) {
      toast({
        title: 'Bulk update gagal',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    }
    setBulkDialog(false);
  };

  // KPI Cards data
  const kpis = [
    { label: 'Total Order',   value: fmt(summary?.total_orders),        sub: `${fmt(summary?.by_platform?.shopee?.count || 0)} Shopee + ${fmt(summary?.by_platform?.tiktok?.count || 0)} TikTok`,           icon: ShoppingBag, color: 'text-indigo-600',  bg: 'bg-indigo-50 dark:bg-indigo-900/20' },
    { label: 'Perlu Tindakan', value: fmt(summary?.need_action),          sub: `${fmt(summary?.by_status?.new || 0)} Baru + ${fmt(summary?.by_status?.packed || 0)} Dikemas`,                             icon: AlertCircle, color: 'text-amber-600',   bg: 'bg-amber-50 dark:bg-amber-900/20' },
    { label: 'Total Revenue', value: fmtRp(summary?.total_revenue),      sub: `Hari ini: ${fmtRp(summary?.today?.revenue)}`,                                                                              icon: DollarSign,  color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-900/20' },
    { label: 'Minggu Ini',    value: fmt(summary?.this_week?.orders),    sub: fmtRp(summary?.this_week?.revenue),                                                                                         icon: TrendingUp,  color: 'text-blue-600',    bg: 'bg-blue-50 dark:bg-blue-900/20' },
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="orders-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard Order</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Manajemen pesanan dari semua platform marketplace</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchSummary(); fetchOrders(); }}>
            <RefreshCw size={13} className="mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setShowPickingList(true)} data-testid="btn-picking-list">
            <ClipboardList size={13} className="mr-1" /> Picking List
          </Button>
        </div>
      </div>

      {/* RC-FLOW-UX-CORE — onward CTA: continue the order flow into Warehouse (cross-portal) + after-sales (Alur 7/8) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Lanjutkan Alur Order"
        className="mb-6"
        actions={[
          { module: 'fulfillment', label: 'Proses Fulfillment di Gudang', icon: Truck, primary: true, hint: 'Order → FG Out (Portal Gudang)' },
          { module: 'marketing-complaints', label: 'Komplain Pelanggan', icon: AlertCircle, hint: 'Kelola komplain terkait order (Alur 7)' },
          { module: 'marketing-returns', label: 'Retur & Refund', icon: RotateCcw, hint: 'Proses retur/refund order (Alur 8)' },
        ]}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => (
          <div key={k.label} className={`rounded-xl border p-4 ${k.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              <k.icon size={15} className={k.color} />
            </div>
            <p className={`text-2xl font-bold tabular-nums ${k.color}`}>{summaryLoading ? '...' : (k.value || '0')}</p>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{summaryLoading ? '' : k.sub}</p>
          </div>
        ))}
      </div>

      {/* Status Mini Bar */}
      {summary && (
        <div className="flex flex-wrap gap-2 mb-5">
          {Object.entries(STATUS_CONFIG).map(([s, cfg]) => {
            const count = summary.by_status?.[s] || 0;
            if (!count) return null;
            return (
              <button
                key={s}
                onClick={() => { setStatusFilter(statusFilter === s ? '' : s); setPage(1); }}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                  statusFilter === s ? 'border-primary ring-1 ring-primary' : 'border-border hover:border-primary/50'
                } ${cfg.color}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                {cfg.label} <span className="font-bold">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Table Card */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-1">
              <div className="relative flex-1 max-w-xs">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Cari order ID, produk, pembeli..."
                  className="pl-9 h-9 text-sm"
                  value={search}
                  onChange={handleSearchChange}
                  data-testid="search-orders"
                />
              </div>
              <div className="w-52">
                <MarketingAccountSelect token={token} value={accountFilter}
                  onChange={(v) => { setAccountFilter(v); setPage(1); }} label=""
                  includeAll allLabel="Semua Toko" required={false}
                  testId="orders-filter-account" />
              </div>
              <Select value={platformFilter || 'all'} onValueChange={v => { setPlatformFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[140px] h-9 text-xs">
                  <SelectValue placeholder="Platform" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Platform</SelectItem>
                  <SelectItem value="shopee">🛒 Shopee</SelectItem>
                  <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                  <SelectItem value="tokopedia">🟢 Tokopedia</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* Unduh yang TERLIHAT (halaman & filter yang sedang aktif) */}
            <ExportCsvButton
              filename="pesanan-marketplace"
              testId="orders-export-csv"
              note={pagination && pagination.total > orders.length
                ? `halaman ini saja dari ${pagination.total} pesanan` : 'semua yang cocok filter'}
              head={['Order ID', 'Platform', 'Toko', 'Produk', 'Variasi', 'SKU', 'Qty',
                'Total (Rp)', 'Pembeli', 'Kota', 'Status', 'Tgl Pesan']}
              rows={orders.map((o) => [o.order_id, o.platform, o.account_name || '',
                o.product_name, o.variation, o.sku_id, o.quantity, o.total_payment,
                o.customer_name, o.city, o.status,
                o.order_date ? String(o.order_date).slice(0, 10) : ''])}
            />
            {/* Bulk Actions */}
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{selectedIds.size} dipilih</span>
                <Select value={bulkStatus} onValueChange={setBulkStatus}>
                  <SelectTrigger className="w-[130px] h-8 text-xs">
                    <SelectValue placeholder="Ubah status" />
                  </SelectTrigger>
                  <SelectContent>
                    {['packed', 'shipped', 'delivered', 'cancelled'].map(s => (
                      <SelectItem key={s} value={s}>{STATUS_CONFIG[s]?.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button size="sm" variant="outline" className="h-8" onClick={() => bulkStatus && setBulkDialog(true)} disabled={!bulkStatus}>
                  Terapkan
                </Button>
                <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setSelectedIds(new Set())}>
                  <X size={13} />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="animate-spin text-muted-foreground" size={24} />
            </div>
          ) : orders.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <ShoppingBag size={32} className="opacity-30 mb-2" />
              <p className="text-sm">Tidak ada order ditemukan</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="px-3 py-2 text-left w-8">
                      <input type="checkbox"
                        checked={selectedIds.size === orders.length && orders.length > 0}
                        onChange={e => setSelectedIds(e.target.checked ? new Set(orders.map(o => o.id)) : new Set())}
                        className="rounded"
                      />
                    </th>
                    {['Order ID', 'Platform', 'Produk', 'Qty', 'Total', 'Pembeli', 'Status', 'Tgl Pesan', ''].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {orders.map(order => (
                    <tr key={order.id}
                      className="hover:bg-muted/30 transition-colors group"
                      data-testid={`order-row-${order.id}`}
                    >
                      <td className="px-3 py-2">
                        <input type="checkbox"
                          checked={selectedIds.has(order.id)}
                          onChange={e => {
                            const next = new Set(selectedIds);
                            e.target.checked ? next.add(order.id) : next.delete(order.id);
                            setSelectedIds(next);
                          }}
                          className="rounded"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-xs font-semibold">{order.order_id}</td>
                      <td className="px-3 py-2"><PlatformBadge platform={order.platform} /></td>
                      <td className="px-3 py-2">
                        <div className="max-w-[180px]">
                          <p className="truncate text-sm font-medium" title={order.product_name}>{order.product_name}</p>
                          <p className="text-xs text-muted-foreground">{order.variation} • {order.sku_id}</p>
                        </div>
                      </td>
                      <td className="px-3 py-2 tabular-nums text-center">{order.quantity}</td>
                      <td className="px-3 py-2 tabular-nums whitespace-nowrap">{fmtRp(order.total_payment)}</td>
                      <td className="px-3 py-2">
                        <div>
                          <p className="text-sm">{order.customer_name}</p>
                          <p className="text-xs text-muted-foreground">{order.city}</p>
                        </div>
                      </td>
                      <td className="px-3 py-2"><StatusBadge status={order.status} /></td>
                      <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {order.order_date ? new Date(order.order_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) : '-'}
                      </td>
                      <td className="px-3 py-2">
                        <Button size="sm" variant="ghost" className="h-7 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => setSelectedOrder(order)}
                          data-testid={`btn-order-detail-${order.id}`}
                        >
                          <ChevronRight size={14} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* Pagination */}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <span className="text-xs text-muted-foreground">{pagination.total} order</span>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" className="h-7" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Sebelumnya</Button>
                <span className="text-xs">{page} / {pagination.total_pages}</span>
                <Button size="sm" variant="outline" className="h-7" disabled={page >= pagination.total_pages} onClick={() => setPage(p => p + 1)}>Berikutnya</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Order Detail Drawer */}
      <OrderDetailDrawer
        order={selectedOrder}
        open={!!selectedOrder}
        onClose={() => setSelectedOrder(null)}
        onStatusChange={() => { fetchOrders(); fetchSummary(); }}
      />

      {/* Picking List Modal */}
      <PickingListModal
        open={showPickingList}
        onClose={() => setShowPickingList(false)}
        token={token}
        accountFilter={accountFilter}
      />

      {/* Bulk Update Confirmation */}
      <AlertDialog open={bulkDialog} onOpenChange={setBulkDialog}>
        <AlertDialogContent data-testid="bulk-status-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Update {selectedIds.size} Order?</AlertDialogTitle>
            <AlertDialogDescription>
              Status akan diubah ke <strong>{STATUS_CONFIG[bulkStatus]?.label}</strong> untuk {selectedIds.size} order yang dipilih.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {/* F10 — konsekuensi STOK ditulis di depan, bukan disimpan di kode.
              Membatalkan order melepas reservasinya: barangnya kembali bisa
              dijual, dan order itu TIDAK bisa dihidupkan lagi. */}
          {(bulkStatus === 'cancelled' || bulkStatus === 'returned') && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-400/40 bg-amber-500/10 p-3 text-[12px] text-amber-800 dark:text-amber-200"
              data-testid="bulk-cancel-stock-note">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <b>Reservasi stok akan dilepas.</b> Stok yang tadinya ditahan untuk order
                ini kembali menjadi stok jual. Order yang sudah dibatalkan/diretur
                <b> tidak bisa dihidupkan lagi</b> — bila pembeli memesan ulang, buat order baru.
              </div>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkStatus} data-testid="bulk-status-confirm">Terapkan</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* F10 — laporan kegagalan per-order (mis. order yang sudah batal tidak bisa
          dihidupkan). Dulu kegagalan seperti ini tidak pernah sampai ke layar. */}
      <AlertDialog open={!!bulkResult} onOpenChange={(o) => !o && setBulkResult(null)}>
        <AlertDialogContent data-testid="bulk-status-result">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {bulkResult?.done || 0} berhasil · {bulkResult?.failed?.length || 0} tidak bisa diubah
            </AlertDialogTitle>
            <AlertDialogDescription>
              Order berikut tidak diubah. Alasannya ditulis apa adanya supaya bisa ditindaklanjuti.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {(bulkResult?.failed || []).map((f) => (
              <div key={f.order_id}
                className="rounded-md border border-border bg-muted/40 p-2 text-[12px]">
                <div className="font-mono text-[11px] text-foreground">
                  {f.order_ref || f.order_id}
                </div>
                <div className="text-muted-foreground">{f.reason}</div>
              </div>
            ))}
          </div>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setBulkResult(null)}>Mengerti</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
