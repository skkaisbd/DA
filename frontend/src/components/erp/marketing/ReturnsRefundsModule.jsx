import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RotateCcw, Plus, Pencil, Trash2, RefreshCw, CheckCircle2, Clock, XCircle,
  AlertCircle, Filter, X, Loader2, ThumbsUp, ThumbsDown, Warehouse, PackageCheck, FileText,
  Table2, LayoutGrid
} from 'lucide-react';
import OnwardCTA from '../OnwardCTA';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { useMarketingAccounts, getPlatformIcon } from '@/hooks/useMarketingAccounts';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './ActiveAccountBar';
import axios from 'axios';
import { CatalogItemSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { shopee: '🛍️', tiktok: '🎵', tokopedia: '🟢', instagram: '📷' };
// F10 (2026-08-13) — layar retur dulu KARTU-SAJA. Retur adalah baris UANG (nilai
// refund, alasan, hasil banding): tanpa tabel, staf tidak bisa membandingkan 20
// baris untuk mencari pola alasan retur, dan itu justru satu-satunya gunanya
// mencatat retur. Tampilan Kartu dipertahankan untuk layar sempit/HP.
const RETURNS_VIEW_KEY = 'marketing_returns_view';
const RETURN_HEADS = ['Tanggal', 'Platform', 'Order ID', 'Toko', 'Produk', 'Harga',
  'Alasan', 'Rincian alasan', 'Refund', 'Status', 'Hasil banding', 'Catatan', 'Aksi'];
const fmtDate = (v) => {
  if (!v) return '—';
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s.slice(0, 10) : d.toISOString().slice(0, 10);
};
const STATUS_CONFIG = {
  pending:   { label: 'Menunggu', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: Clock },
  approved:  { label: 'Disetujui', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', icon: ThumbsUp },
  completed: { label: 'Selesai', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
  rejected:  { label: 'Ditolak', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', icon: ThumbsDown },
};

function KPICard({ label, value, sub, color, bg, icon: Icon }) {
  return (
    <Card className={`${bg} border-0`}>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-background/60 dark:bg-black/20`}>
          <Icon size={20} className={color} />
        </div>
        <div>
          <p className="text-xl font-bold leading-tight">{value}</p>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

const EMPTY_FORM = {
  catalog_item_id: '', sku: '',
  account_id: '', account_name: '',
  date: '', order_id: '', platform: 'shopee', product: '', price: 0,
  // W4 (sesi #29) — KONDISI & JUMLAH barang yang kembali. Dua kolom inilah yang
  // membuat retur langsung menggerakkan stok gudang tanpa menebak:
  //   Baik  → masuk Area Produk Jadi (ikut stok jual)
  //   Rusak → masuk Area Karantina (TIDAK dijual)
  item_condition: 'Baik', qty: 1,
  reason: 'ukuran_salah', reason_detail: '', courier: 'jnt', refund_type: 'full_refund', notes: ''
};

export default function ReturnsRefundsModule({ token, onNavigate }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const { accounts: masterAccounts, byId: accountById } = useMarketingAccounts(token);
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const [summary, setSummary] = useState(null);
  const [returns, setReturns] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [reasons, setReasons] = useState([]);

  const [loading, setLoading] = useState(true);

  const [filterStatus, setFilterStatus] = useState('');
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterReason, setFilterReason] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formLoading, setFormLoading] = useState(false);

  const [showDetail, setShowDetail] = useState(null);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(RETURNS_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  const [actionLoading, setActionLoading] = useState('');

  const fetchReasons = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/returns/reasons`, { headers: authH });
      setReasons(res.data.reasons || []);
    } catch (e) {
      console.error('Reasons fetch error:', e);
    }
  }, [authH]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/returns/summary`, { headers: authH });
      setSummary(res.data.data || {});
    } catch (e) {
      console.error('Summary fetch error:', e);
    }
  }, [authH]);

  const fetchReturns = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = { page, page_size: 20 };
      if (filterStatus) params.status = filterStatus;
      if (filterPlatform) params.platform = filterPlatform;
      if (filterReason) params.reason = filterReason;
      if (searchQuery) params.search = searchQuery;
      if (activeAccount?.id) params.account_id = activeAccount.id;

      const res = await axios.get(`${API}/api/marketing/returns`, { headers: authH, params });
      setReturns(res.data.data || []);
      setPagination(res.data.pagination || {});
    } catch (e) {
      console.error('Returns fetch error:', e);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authH, filterStatus, filterPlatform, filterReason, searchQuery, activeAccount]);

  useEffect(() => {
    fetchReasons();
    fetchSummary();
  }, [fetchReasons, fetchSummary]);

  useEffect(() => {
    fetchReturns(currentPage);
  }, [fetchReturns, currentPage]);

  useEffect(() => {
    try { localStorage.setItem(RETURNS_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const openForm = (ret = null) => {
    if (ret) {
      setEditTarget(ret);
      setForm({
        account_id: ret.account_id || '',
        account_name: ret.account_name || '',
        date: ret.date,
        order_id: ret.order_id,
        platform: ret.platform,
        product: ret.product,
        price: ret.price,
        item_condition: ret.item_condition || 'Baik',
        qty: ret.qty || 1,
        reason: ret.reason,
        reason_detail: ret.reason_detail,
        courier: ret.courier,
        refund_type: ret.refund_type,
        notes: ret.notes || ''
      });
    } else {
      setEditTarget(null);
      setForm({ ...EMPTY_FORM, date: new Date().toISOString().split('T')[0] });
    }
    setShowForm(true);
  };

  // When account_id changes, auto-fill account_name & platform from master
  const handleAccountChange = (accountId) => {
    const acc = accountById[accountId];
    setForm(f => ({
      ...f,
      account_id: accountId,
      account_name: acc?.account_name || acc?.name || '',
      platform: acc?.platform || f.platform,
    }));
  };

  const closeForm = () => {
    setShowForm(false);
    setEditTarget(null);
    setForm(EMPTY_FORM);
  };

  const handleSave = async () => {
    if (!form.account_id) {
      toast({ title: 'Error', description: 'Wajib pilih Akun / Toko', variant: 'destructive' });
      return;
    }
    if (!form.order_id || !(form.catalog_item_id || form.product) || !form.reason_detail) {
      toast({ title: 'Error', description: 'Order ID, Produk, dan Alasan Detail wajib diisi', variant: 'destructive' });
      return;
    }
    try {
      setFormLoading(true);
      if (editTarget) {
        await axios.put(`${API}/api/marketing/returns/${editTarget.id}`, form, { headers: authH });
        toast({ title: 'Berhasil', description: 'Return diperbarui' });
      } else {
        const res = await axios.post(`${API}/api/marketing/returns`, form, { headers: authH });
        // W4 — beri tahu APA YANG TERJADI PADA STOK, bukan cuma "tersimpan".
        const wh = res?.data?.warehouse || {};
        const desc = wh.wh_return_code
          ? `Retur tersimpan. Retur fisik ${wh.wh_return_code} otomatis dibuat di Gudang`
            + (wh.restocked
              ? ` · ${wh.stock_effect === 'sellable'
                  ? `stok jual bertambah (${wh.location})`
                  : `barang ditahan di karantina (${wh.location})`}`
              : ' · stok BELUM bertambah (perlu dipilih produknya di Gudang)')
          : 'Retur tersimpan (pekerjaan gudang belum terbuat — cek menu Gudang › Retur Fisik)';
        toast({ title: 'Berhasil', description: desc });
      }
      closeForm();
      fetchReturns(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus return ini?')) return;
    try {
      await axios.delete(`${API}/api/marketing/returns/${id}`, { headers: authH });
      toast({ title: 'Berhasil', description: 'Return dihapus' });
      fetchReturns(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const handleApprove = async (id) => {
    try {
      setActionLoading(id);
      await axios.post(`${API}/api/marketing/returns/${id}/approve`, {}, { headers: authH });
      toast({ title: 'Berhasil', description: 'Return disetujui' });
      fetchReturns(currentPage);
      fetchSummary();
      setShowDetail(null);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const handleReject = async (id, notes) => {
    try {
      setActionLoading(id);
      await axios.post(`${API}/api/marketing/returns/${id}/reject`, { notes }, { headers: authH });
      toast({ title: 'Berhasil', description: 'Return ditolak' });
      fetchReturns(currentPage);
      fetchSummary();
      setShowDetail(null);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const handleComplete = async (id) => {
    try {
      setActionLoading(id);
      const res = await axios.post(`${API}/api/marketing/returns/${id}/complete`, {}, { headers: authH });
      const warning = res?.data?.warning;
      if (warning) {
        toast({ title: 'Diselesaikan (dengan peringatan)', description: warning, variant: 'default' });
      } else {
        toast({ title: 'Berhasil', description: 'Return diselesaikan' });
      }
      fetchReturns(currentPage);
      fetchSummary();
      setShowDetail(null);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  // RC-FLOW-UX-11a (opsi B): tombol manual "Buat Retur Fisik di Gudang" untuk
  // menghubungkan marketing_returns → wh_returns. Idempoten (backend cek back-ref).
  const handleCreateWhReturn = async (id) => {
    try {
      setActionLoading(id);
      const res = await axios.post(
        `${API}/api/marketing/returns/${id}/create-wh-return`,
        {},
        { headers: authH }
      );
      const code = res?.data?.wh_return_code || res?.data?.data?.return_code;
      const already = res?.data?.already_exists;
      const restocked = res?.data?.restocked;
      const effect = res?.data?.stock_effect;
      toast({
        title: already ? 'Sudah terhubung' : 'Berhasil',
        description: (already
          ? `Retur ini sudah punya entry Gudang ${code || ''}`
          : `Retur fisik dibuat di Gudang: ${code}.`)
          + (restocked
            ? ` Stok sudah diperbarui (${effect === 'sellable' ? 'masuk stok jual' : 'ditahan di karantina'}).`
            : ` ${res?.data?.message || 'Stok belum bertambah — buka menu Gudang › Retur Fisik.'}`),
      });
      // refresh list & detail
      const refreshed = await axios.get(`${API}/api/marketing/returns/${id}`, { headers: authH });
      if (refreshed?.data?.data) setShowDetail(refreshed.data.data);
      fetchReturns(currentPage);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const clearFilters = () => {
    setFilterStatus('');
    setFilterPlatform('');
    setFilterReason('');
    setSearchQuery('');
    setCurrentPage(1);
  };

  const s = summary || {};
  const activeFilters = [filterStatus, filterPlatform, filterReason, searchQuery].filter(Boolean).length;

  return (
    <div className="space-y-6" data-testid="returns-refunds-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Refund & Nota Kredit</h1>
          <p className="text-sm text-muted-foreground mt-1">Kelola pengembalian dana dan nota kredit — sisi Toko/Marketing</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => fetchReturns(currentPage)} variant="outline" size="sm">
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button onClick={() => openForm()} size="sm">
            <Plus size={14} className="mr-1" />Buat Refund
          </Button>
        </div>
      </div>

      {/* RC-FLOW-UX — onward CTA: retur/refund → terima barang retur fisik di Gudang (cross-portal, Alur 8) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Tindak Lanjut Retur"
        actions={[
          { module: 'wh-returns', label: 'Terima Retur Fisik di Gudang', icon: Warehouse, primary: true, hint: 'Barang retur masuk kembali ke Gudang' },
        ]}
      />

      {/* KPI Cards */}
      <ActiveAccountBar accounts={masterAccounts} activeAccount={activeAccount} onAccountChange={acc => { setActiveAccount(acc); setCurrentPage(1); }} hint="Filter returns by akun:" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard label="Total Return" value={s.total || 0} color="text-blue-600" bg="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950/30 dark:to-blue-900/30" icon={RotateCcw} />
        <KPICard label="Menunggu" value={s.pending || 0} color="text-orange-600" bg="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-950/30 dark:to-orange-900/30" icon={Clock} />
        <KPICard label="Disetujui" value={s.approved || 0} color="text-blue-600" bg="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950/30 dark:to-blue-900/30" icon={ThumbsUp} />
        <KPICard label="Selesai" value={s.completed || 0} color="text-emerald-600" bg="bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-950/30 dark:to-emerald-900/30" icon={CheckCircle2} />
        <KPICard label="Total Refund" value={`Rp ${(s.total_refund || 0).toLocaleString('id-ID')}`} color="text-purple-600" bg="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-950/30 dark:to-purple-900/30" icon={RotateCcw} />
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Filter size={16} />Filter
              {activeFilters > 0 && (
                <Badge variant="secondary" className="ml-1">{activeFilters}</Badge>
              )}
            </CardTitle>
            {activeFilters > 0 && (
              <Button onClick={clearFilters} variant="ghost" size="sm">
                <X size={14} className="mr-1" />Clear
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Status</SelectItem>
                <SelectItem value="pending">Menunggu</SelectItem>
                <SelectItem value="approved">Disetujui</SelectItem>
                <SelectItem value="completed">Selesai</SelectItem>
                <SelectItem value="rejected">Ditolak</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterPlatform} onValueChange={setFilterPlatform}>
              <SelectTrigger>
                <SelectValue placeholder="Platform" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Platform</SelectItem>
                <SelectItem value="shopee">Shopee</SelectItem>
                <SelectItem value="tiktok">TikTok</SelectItem>
                <SelectItem value="tokopedia">Tokopedia</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterReason} onValueChange={setFilterReason}>
              <SelectTrigger>
                <SelectValue placeholder="Alasan" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Alasan</SelectItem>
                {reasons.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Input
              placeholder="Cari order/produk..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>Daftar Return ({pagination?.total || 0})</CardTitle>
            <div className="flex rounded-md border border-border overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="returns-view-table"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <Table2 size={12} /> Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="returns-view-grid"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <LayoutGrid size={12} /> Kartu
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin" size={24} /></div>
          ) : returns.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">Tidak ada return</div>
          ) : view === 'table' ? (
            <div className="rounded-lg border border-border overflow-x-auto">
              <table className="w-full text-xs" data-testid="returns-table">
                <thead className="bg-muted/60">
                  <tr>{RETURN_HEADS.map((h) => (
                    <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {returns.map(r => (
                    <tr key={r.id} className="hover:bg-muted/30" data-testid={`returns-row-${r.id}`}>
                      <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(r.date || r.created_at)}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap">
                        {PLATFORM_ICONS[r.platform]} {r.platform || '—'}
                      </td>
                      <td className="px-2.5 py-2 font-mono text-[11px]">{r.order_id || '—'}</td>
                      <td className="px-2.5 py-2">{r.account_name || '—'}</td>
                      <td className="px-2.5 py-2 max-w-[220px] truncate" title={r.product}>{r.product || '—'}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap">Rp {(r.price || 0).toLocaleString('id-ID')}</td>
                      <td className="px-2.5 py-2">{r.reason_label || r.reason || '—'}</td>
                      <td className="px-2.5 py-2 max-w-[200px] truncate" title={r.reason_detail}>
                        {r.reason_detail || '—'}
                      </td>
                      <td className="px-2.5 py-2 whitespace-nowrap font-semibold">
                        Rp {(r.refund_amount || 0).toLocaleString('id-ID')}
                      </td>
                      <td className="px-2.5 py-2">
                        {r.status ? (
                          <Badge className={STATUS_CONFIG[r.status]?.color}>
                            {STATUS_CONFIG[r.status]?.label || r.status}
                          </Badge>
                        ) : '—'}
                      </td>
                      <td className="px-2.5 py-2">{r.appeal_result || '—'}</td>
                      <td className="px-2.5 py-2 max-w-[160px] truncate" title={r.notes}>{r.notes || '—'}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap text-right">
                        <Button onClick={() => setShowDetail(r)} variant="ghost" size="sm"
                          data-testid={`returns-detail-${r.id}`}>Detail</Button>
                        <Button onClick={() => openForm(r)} variant="ghost" size="sm"><Pencil size={14} /></Button>
                        <Button onClick={() => handleDelete(r.id)} variant="ghost" size="sm"><Trash2 size={14} /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="space-y-3" data-testid="returns-grid">
              {returns.map(r => (
                <div key={r.id} className="border rounded-lg p-4 space-y-2 hover:bg-muted/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-muted-foreground">{PLATFORM_ICONS[r.platform]} {r.platform}</span>
                        <Badge variant="outline" className="text-xs">{r.order_id}</Badge>
                        <span className="text-xs font-medium">{r.product}</span>
                        <span className="text-xs text-muted-foreground">Rp {(r.price || 0).toLocaleString('id-ID')}</span>
                        {r.status && <Badge className={STATUS_CONFIG[r.status]?.color}>{STATUS_CONFIG[r.status]?.label}</Badge>}
                      </div>
                      <p className="text-sm"><strong>Alasan:</strong> {r.reason_label} - {r.reason_detail}</p>
                      {r.notes && <p className="text-xs text-muted-foreground">Catatan: {r.notes}</p>}
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>Refund: Rp {(r.refund_amount || 0).toLocaleString('id-ID')}</span>
                        <span>•</span>
                        <span>{r.appeal_result}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <Button onClick={() => setShowDetail(r)} variant="ghost" size="sm">
                        Detail
                      </Button>
                      <Button onClick={() => openForm(r)} variant="ghost" size="sm">
                        <Pencil size={14} />
                      </Button>
                      <Button onClick={() => handleDelete(r.id)} variant="ghost" size="sm">
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-muted-foreground">
                Halaman {pagination.page} dari {pagination.total_pages}
              </p>
              <div className="flex gap-1">
                <Button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  variant="outline"
                  size="sm"
                >
                  Prev
                </Button>
                <Button
                  onClick={() => setCurrentPage(p => Math.min(pagination.total_pages, p + 1))}
                  disabled={currentPage === pagination.total_pages}
                  variant="outline"
                  size="sm"
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Form Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editTarget ? 'Edit Return' : 'Tambah Return'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Akun / Toko Marketplace *</Label>
              <Select value={form.account_id || ''} onValueChange={handleAccountChange}>
                <SelectTrigger data-testid="return-account-select">
                  <SelectValue placeholder={masterAccounts.length === 0 ? 'Belum ada akun — buat di Manage Accounts' : 'Pilih akun...'} />
                </SelectTrigger>
                <SelectContent>
                  {masterAccounts.length === 0 && (
                    <SelectItem value="empty" disabled>Belum ada akun aktif</SelectItem>
                  )}
                  {masterAccounts.map(acc => (
                    <SelectItem key={acc.id} value={acc.id}>
                      {getPlatformIcon(acc.platform)} {acc.account_name} <span className="text-xs text-muted-foreground ml-1">({acc.platform})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {form.account_id && (
                <p className="text-xs text-muted-foreground">
                  Platform: <strong>{form.platform}</strong> (otomatis dari akun)
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tanggal</Label>
                <Input type="date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Order ID *</Label>
                <Input value={form.order_id} onChange={e => setForm({ ...form, order_id: e.target.value })} placeholder="ORD-123456" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Harga</Label>
                <Input type="number" value={form.price} onChange={e => setForm({ ...form, price: parseFloat(e.target.value) })} />
              </div>
              <div className="space-y-2">
                <Label>Tipe Refund</Label>
                <Select value={form.refund_type} onValueChange={v => setForm({ ...form, refund_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="full_refund">Full Refund</SelectItem>
                    <SelectItem value="partial_refund">Partial Refund</SelectItem>
                    <SelectItem value="exchange">Exchange</SelectItem>
                    <SelectItem value="no_refund">No Refund</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Produk *</Label>
              {/* F15 — produk DIPILIH dari katalog toko. Sebelum ini teks bebas:
                  "Gamis Daluna Basic" dan "Gamis Daluna basic" jadi dua produk di
                  laporan, sehingga "produk mana yang paling banyak diretur / paling
                  buruk ulasannya" tidak bisa dijawab. */}
              <CatalogItemSelect
                token={token} accountId={form.account_id} label=""
                value={form.catalog_item_id || ''}
                onChange={(item) => setForm({
                  ...form,
                  catalog_item_id: item?.id || '',
                  product: item?.name || '',
                  sku: item?.sku || '',
                })}
                testId="return-item-select" />
            </div>
            {/* ── W4 (sesi #29) — KONDISI & JUMLAH BARANG YANG KEMBALI ─────────
                Retur yang dibuat di sini LANGSUNG membuat pekerjaan Retur Fisik di
                Gudang dan langsung menggerakkan stok. Kondisi menentukan lokasinya:
                Baik → stok jual, Rusak → karantina (tidak boleh dijual). */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Kondisi Barang *</Label>
                <Select value={form.item_condition || 'Baik'} onValueChange={v => setForm({ ...form, item_condition: v })}>
                  <SelectTrigger data-testid="return-condition-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Baik">Baik — masuk stok jual</SelectItem>
                    <SelectItem value="Rusak">Rusak — ditahan di karantina</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Qty Barang Kembali *</Label>
                <Input type="number" min={1} value={form.qty || 1}
                  onChange={e => setForm({ ...form, qty: Math.max(1, parseInt(e.target.value || '1', 10)) })}
                  data-testid="return-qty-input" />
              </div>
            </div>
            <div className="rounded-md border border-sky-300 bg-sky-50 dark:bg-sky-950/30 dark:border-sky-800 px-3 py-2 text-xs text-sky-900 dark:text-sky-200 flex items-start gap-2">
              <Warehouse size={14} className="mt-0.5 shrink-0" />
              <span>
                Setelah disimpan, <strong>Retur Fisik di Gudang dibuat otomatis</strong> dan stok
                langsung disesuaikan: kondisi <strong>Baik</strong> masuk Area Produk Jadi (ikut stok jual),
                kondisi <strong>Rusak</strong> masuk Area Karantina (tidak dijual).
              </span>
            </div>
            <div className="space-y-2">
              <Label>Alasan</Label>
              <Select value={form.reason} onValueChange={v => setForm({ ...form, reason: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {reasons.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Alasan Detail *</Label>
              <Textarea value={form.reason_detail} onChange={e => setForm({ ...form, reason_detail: e.target.value })} rows={2} placeholder="Detail alasan return..." />
            </div>
            <div className="space-y-2">
              <Label>Catatan</Label>
              <Textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} placeholder="Catatan..." />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={closeForm} variant="outline" disabled={formLoading}>Batal</Button>
            <Button onClick={handleSave} disabled={formLoading}>
              {formLoading && <Loader2 className="animate-spin mr-1" size={14} />}
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Detail Refund</DialogTitle>
          </DialogHeader>
          {showDetail && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <p className="text-sm"><strong>Order:</strong> {showDetail.order_id}</p>
                <p className="text-sm"><strong>Produk:</strong> {showDetail.product}</p>
                <p className="text-sm"><strong>Harga:</strong> Rp {(showDetail.price || 0).toLocaleString('id-ID')}</p>
                <p className="text-sm"><strong>Alasan:</strong> {showDetail.reason_label}</p>
                <p className="text-sm"><strong>Detail:</strong> {showDetail.reason_detail}</p>
                <p className="text-sm"><strong>Refund:</strong> Rp {(showDetail.refund_amount || 0).toLocaleString('id-ID')}</p>
                <p className="text-sm"><strong>Status:</strong> <Badge className={STATUS_CONFIG[showDetail.status]?.color}>{STATUS_CONFIG[showDetail.status]?.label}</Badge></p>
                {showDetail.wh_return_code && (
                  <p className="text-sm"><strong>Retur Fisik (Gudang):</strong> <Badge variant="outline">{showDetail.wh_return_code}</Badge> <span className="text-xs text-muted-foreground ml-1">status: {showDetail.wh_return_status || 'Pending'}</span></p>
                )}
                {/* W4 — apa yang terjadi pada STOK, dinyatakan terang-terangan. */}
                {showDetail.wh_return_id && (
                  <div className="text-sm" data-testid="mkt-ret-stock-effect">
                    <strong>Efek stok:</strong>{' '}
                    {showDetail.wh_restocked ? (
                      <Badge className={showDetail.wh_stock_effect === 'sellable'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'}>
                        {showDetail.wh_stock_effect === 'sellable'
                          ? `+${showDetail.wh_restock_qty || 0} stok jual (${showDetail.wh_restock_location_code || 'ZNA-FG'})`
                          : `+${showDetail.wh_restock_qty || 0} karantina (${showDetail.wh_restock_location_code || 'ZNA-KARANTINA'})`}
                      </Badge>
                    ) : (
                      <Badge variant="outline">belum masuk stok</Badge>
                    )}
                    {showDetail.wh_link_status && showDetail.wh_link_status !== 'linked' && (
                      <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">{showDetail.wh_link_reason}</p>
                    )}
                  </div>
                )}
                {showDetail.credit_note_number && (
                  <p className="text-sm"><strong>Credit Note:</strong> <Badge variant="outline">{showDetail.credit_note_number}</Badge></p>
                )}
              </div>

              {/* RC-FLOW-UX-11c (opsi B, soft-warning): retur approved > 24 jam & belum ada wh_return_id */}
              {showDetail.status === 'approved' && !showDetail.wh_return_id && (() => {
                const upd = new Date(showDetail.updated_at || showDetail.date || 0).getTime();
                const hours = (Date.now() - upd) / 36e5;
                if (hours < 24) return null;
                return (
                  <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 px-3 py-2 text-sm">
                    <AlertCircle size={16} className="text-amber-600 mt-0.5 shrink-0" />
                    <div className="text-amber-900 dark:text-amber-200">
                      <strong className="block mb-0.5">Barang belum diterima Gudang</strong>
                      <span className="text-xs">
                        Retur disetujui {Math.floor(hours)} jam lalu, tapi belum ada entry Retur Fisik di Gudang. Stok FG tidak akan otomatis bertambah. Klik <em>Buat Retur Fisik di Gudang</em> untuk melanjutkan.
                      </span>
                    </div>
                  </div>
                );
              })()}

              {/* W4 — retur LAMA (dibuat sebelum jembatan otomatis) bisa ditarik ke
                  Gudang dari sini, apa pun statusnya selain ditolak/dibatalkan.
                  Dulu tombol ini hanya muncul saat 'approved', sehingga retur
                  'pending'/'completed' tidak punya jalan sama sekali ke gudang. */}
              {!showDetail.wh_return_id && !['rejected', 'cancelled'].includes(showDetail.status) && (
                <Button
                  onClick={() => handleCreateWhReturn(showDetail.id)}
                  disabled={actionLoading === showDetail.id}
                  variant="outline"
                  className="w-full"
                  data-testid="btn-create-wh-return"
                >
                  {actionLoading === showDetail.id
                    ? <Loader2 className="animate-spin mr-1" size={14} />
                    : <Warehouse size={14} className="mr-1" />}
                  Kirim ke Gudang &amp; Masukkan Stok
                </Button>
              )}

              {showDetail.status === 'pending' && (
                <div className="flex gap-2">
                  <Button onClick={() => handleApprove(showDetail.id)} disabled={actionLoading === showDetail.id} className="flex-1">
                    {actionLoading === showDetail.id && <Loader2 className="animate-spin mr-1" size={14} />}
                    <ThumbsUp size={14} className="mr-1" />Setujui
                  </Button>
                  <Button onClick={() => handleReject(showDetail.id, 'Tidak memenuhi syarat')} disabled={actionLoading === showDetail.id} variant="destructive" className="flex-1">
                    {actionLoading === showDetail.id && <Loader2 className="animate-spin mr-1" size={14} />}
                    <ThumbsDown size={14} className="mr-1" />Tolak
                  </Button>
                </div>
              )}
              {showDetail.status === 'approved' && (
                <div className="flex flex-col gap-2">
                  {showDetail.wh_return_id && (
                    <div className="rounded-md border border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-800 px-3 py-2 text-sm text-emerald-900 dark:text-emerald-200 flex items-center gap-2">
                      <CheckCircle2 size={14} className="text-emerald-600" />
                      Terhubung ke Gudang: <strong>{showDetail.wh_return_code}</strong>
                      {onNavigate && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto h-7 px-2 text-xs"
                          onClick={() => onNavigate('wh-returns', { return_id: showDetail.wh_return_id })}
                          data-testid="btn-open-wh-return"
                        >
                          Buka di Gudang →
                        </Button>
                      )}
                    </div>
                  )}
                  <Button onClick={() => handleComplete(showDetail.id)} disabled={actionLoading === showDetail.id} className="w-full">
                    {actionLoading === showDetail.id && <Loader2 className="animate-spin mr-1" size={14} />}
                    <CheckCircle2 size={14} className="mr-1" />Selesaikan & Terbitkan Nota Kredit
                  </Button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
