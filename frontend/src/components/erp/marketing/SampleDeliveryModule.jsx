import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Package, Plus, Pencil, Trash2, RefreshCw, CheckCircle2, Clock, Truck,
  AlertCircle, Filter, X, Loader2, Video, TrendingUp, Table2, LayoutGrid
} from 'lucide-react';
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
import axios from 'axios';
import {
  MarketingAccountSelect, MarketingCreatorSelect, CatalogItemSelect,
} from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { tiktok: '🎵', instagram: '📷', shopee: '🛍️', tokopedia: '🟢' };
// F10 (2026-08-13) — layar ini KARTU-SAJA padahal isinya BIAYA yang mudah menguap:
// sample dikirim ke kreator (HPP + ongkir) dan sering tidak pernah ditagih hasilnya.
// Kolom "Umur (hari)" & "Video" sengaja ditampilkan terbuka: sample berumur 30 hari
// tanpa link video adalah kerugian yang selama ini tidak pernah terlihat di layar.
const SAMPLE_VIEW_KEY = 'marketing_sample_view';
// F10 (sesi #10) — daftar yang tidak bisa diunduh memaksa staf menyalin ulang
// dengan tangan (sumber salah-ketik). Satu pembuat CSV: `lib/csv.js`.
import ExportCsvButton from '@/components/ui/export-csv-button';

const SAMPLE_HEADS = ['Tanggal', 'Toko', 'Kreator', 'Produk', 'SKU', 'Qty', 'HPP',
  'Total HPP', 'Ongkir', 'Kurir', 'Resi', 'Status kirim', 'Progress', 'Video',
  'Umur (hari)', 'Aksi'];
const fmtDate = (v) => {
  if (!v) return '—';
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s.slice(0, 10) : d.toISOString().slice(0, 10);
};
const ageDays = (v) => {
  if (!v) return '—';
  const d = new Date(String(v).slice(0, 10));
  if (Number.isNaN(d.getTime())) return '—';
  return Math.max(0, Math.round((Date.now() - d.getTime()) / 86400000));
};
const SHIPMENT_STATUS_CONFIG = {
  pending:   { label: 'Menunggu', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: Clock },
  shipped:   { label: 'Dikirim', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', icon: Truck },
  delivered: { label: 'Terkirim', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
};

const PROGRESS_STATUS_CONFIG = {
  open:        { label: 'Open', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  follow_up:   { label: 'Follow Up', color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' },
  sold:        { label: 'Terjual', color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' },
  no_response: { label: 'No Response', color: 'bg-muted text-foreground dark:bg-gray-900/30 dark:text-gray-300' },
  closed:      { label: 'Closed', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' },
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
  account_id: '', account_name: '',
  date: '', username: '', sample_type: 'video', platform: 'tiktok', product: '',
  size: 'M', color: '', quantity: 1, hpp: 0, ongkir: 0, courier: 'jnt', video_link: '', notes: ''
};

export default function SampleDeliveryModule({ token }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const { accounts: masterAccounts, byId: accountById } = useMarketingAccounts(token);
  const [summary, setSummary] = useState(null);
  const [samples, setSamples] = useState([]);
  const [pagination, setPagination] = useState(null);

  const [loading, setLoading] = useState(true);

  const [filterShipmentStatus, setFilterShipmentStatus] = useState('');
  const [filterProgress, setFilterProgress] = useState('');
  const [filterPlatform, setFilterPlatform] = useState('');
  // F14 — filter per TOKO. Sebelum ini `marketing_samples` bahkan tidak punya
  // `account_id`, jadi pertanyaan "berapa biaya sample toko X" tidak terjawab.
  const [filterAccountId, setFilterAccountId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formLoading, setFormLoading] = useState(false);

  // Opsi ukuran & warna mengikuti item katalog yang dipilih (bukan teks bebas).
  const [sizeOptions, setSizeOptions] = useState([]);
  const [colorOptions, setColorOptions] = useState([]);

  const [showDetail, setShowDetail] = useState(null);
  const [progressUpdate, setProgressUpdate] = useState({ progress: '', sales_update: '' });
  const [actionLoading, setActionLoading] = useState('');
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(SAMPLE_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  useEffect(() => {
    try { localStorage.setItem(SAMPLE_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/samples/summary`, {
        headers: authH,
        params: filterAccountId ? { account_id: filterAccountId } : {},
      });
      setSummary(res.data.data || {});
    } catch (e) {
      console.error('Summary fetch error:', e);
    }
  }, [authH, filterAccountId]);

  const fetchSamples = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = { page, page_size: 20 };
      if (filterShipmentStatus) params.shipment_status = filterShipmentStatus;
      if (filterProgress) params.progress = filterProgress;
      if (filterPlatform) params.platform = filterPlatform;
      if (filterAccountId) params.account_id = filterAccountId;
      if (searchQuery) params.search = searchQuery;

      const res = await axios.get(`${API}/api/marketing/samples`, { headers: authH, params });
      setSamples(res.data.data || []);
      setPagination(res.data.pagination || {});
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [authH, toast, filterShipmentStatus, filterProgress, filterPlatform, filterAccountId, searchQuery]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  useEffect(() => {
    fetchSamples(currentPage);
  }, [fetchSamples, currentPage]);

  const openForm = (sample = null) => {
    if (sample) {
      setEditTarget(sample);
      setForm({
        account_id: sample.account_id || '',
        account_name: sample.account_name || '',
        date: sample.date,
        username: sample.username,
        sample_type: sample.sample_type,
        platform: sample.platform,
        product: sample.product,
        size: sample.size,
        color: sample.color,
        quantity: sample.quantity,
        hpp: sample.hpp,
        ongkir: sample.ongkir,
        courier: sample.courier,
        video_link: sample.video_link || '',
        notes: sample.notes || ''
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
    // F14/F15 — toko, kreator, dan produk katalog WAJIB dipilih dari master.
    // Dulu `username`/`product`/`size`/`color`/`hpp` semuanya teks/angka ketikan:
    // satu kreator bisa pecah jadi beberapa baris laporan hanya karena beda ejaan,
    // dan HPP yang salah ketik langsung menjadi biaya sample yang salah.
    if (!form.account_id) {
      toast({ title: 'Toko belum dipilih', description: 'Sample harus menempel pada satu toko.', variant: 'destructive' });
      return;
    }
    if (!form.creator_id) {
      toast({ title: 'Kreator belum dipilih', description: 'Pilih kreator dari daftar yang di-assign ke toko ini.', variant: 'destructive' });
      return;
    }
    if (!form.catalog_item_id && !form.product) {
      toast({ title: 'Produk belum dipilih', description: 'Pilih produk dari katalog toko.', variant: 'destructive' });
      return;
    }
    try {
      setFormLoading(true);
      if (editTarget) {
        await axios.put(`${API}/api/marketing/samples/${editTarget.id}`, form, { headers: authH });
        toast({ title: 'Berhasil', description: 'Sample diperbarui' });
      } else {
        await axios.post(`${API}/api/marketing/samples`, form, { headers: authH });
        toast({ title: 'Berhasil', description: 'Sample ditambahkan' });
      }
      closeForm();
      fetchSamples(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus sample ini?')) return;
    try {
      await axios.delete(`${API}/api/marketing/samples/${id}`, { headers: authH });
      toast({ title: 'Berhasil', description: 'Sample dihapus' });
      fetchSamples(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const handleShip = async (id) => {
    try {
      setActionLoading(id);
      await axios.post(`${API}/api/marketing/samples/${id}/ship`, {}, { headers: authH });
      toast({ title: 'Berhasil', description: 'Sample ditandai dikirim' });
      fetchSamples(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const handleDeliver = async (id) => {
    try {
      setActionLoading(id);
      await axios.post(`${API}/api/marketing/samples/${id}/deliver`, {}, { headers: authH });
      toast({ title: 'Berhasil', description: 'Sample ditandai terkirim' });
      fetchSamples(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const handleUpdateProgress = async () => {
    if (!progressUpdate.progress) {
      toast({ title: 'Error', description: 'Status progress wajib dipilih', variant: 'destructive' });
      return;
    }
    try {
      setActionLoading(showDetail.id);
      await axios.post(`${API}/api/marketing/samples/${showDetail.id}/update-progress`, progressUpdate, { headers: authH });
      toast({ title: 'Berhasil', description: 'Progress diupdate' });
      setShowDetail(null);
      setProgressUpdate({ progress: '', sales_update: '' });
      fetchSamples(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setActionLoading('');
    }
  };

  const clearFilters = () => {
    setFilterShipmentStatus('');
    setFilterProgress('');
    setFilterPlatform('');
    setSearchQuery('');
    setCurrentPage(1);
  };

  const s = summary || {};
  const activeFilters = [filterShipmentStatus, filterProgress, filterPlatform, filterAccountId, searchQuery].filter(Boolean).length;

  return (
    <div className="space-y-6" data-testid="sample-delivery-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Database Pengiriman Sample</h1>
          <p className="text-sm text-muted-foreground mt-1">Tracking pengiriman sample ke reseller/KOL</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => fetchSamples(currentPage)} variant="outline" size="sm">
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button onClick={() => openForm()} size="sm">
            <Plus size={14} className="mr-1" />Tambah Sample
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        <KPICard label="Total Sample" value={s.total || 0} color="text-blue-600" bg="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950/30 dark:to-blue-900/30" icon={Package} />
        <KPICard label="Pending" value={s.pending || 0} color="text-orange-600" bg="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-950/30 dark:to-orange-900/30" icon={Clock} />
        <KPICard label="Dikirim" value={s.shipped || 0} color="text-blue-600" bg="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950/30 dark:to-blue-900/30" icon={Truck} />
        <KPICard label="Terkirim" value={s.delivered || 0} color="text-emerald-600" bg="bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-950/30 dark:to-emerald-900/30" icon={CheckCircle2} />
        <KPICard label="Terjual" value={s.sold || 0} color="text-green-600" bg="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-950/30 dark:to-green-900/30" icon={TrendingUp} />
        <KPICard label="Total Investasi" value={`Rp ${(s.total_investment || 0).toLocaleString('id-ID')}`} color="text-purple-600" bg="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-950/30 dark:to-purple-900/30" icon={Package} />
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
            <Select value={filterShipmentStatus} onValueChange={setFilterShipmentStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Status Kirim" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Status</SelectItem>
                <SelectItem value="pending">Menunggu</SelectItem>
                <SelectItem value="shipped">Dikirim</SelectItem>
                <SelectItem value="delivered">Terkirim</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterProgress} onValueChange={setFilterProgress}>
              <SelectTrigger>
                <SelectValue placeholder="Progress" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Progress</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="follow_up">Follow Up</SelectItem>
                <SelectItem value="sold">Terjual</SelectItem>
                <SelectItem value="no_response">No Response</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
            {/* F14 — filter per TOKO. `marketing_samples` dulu tidak punya
                `account_id` sama sekali, jadi biaya sample per toko mustahil dihitung. */}
            <MarketingAccountSelect token={token} value={filterAccountId}
              onChange={(v) => { setFilterAccountId(v); setCurrentPage(1); }}
              label="" includeAll allLabel="Semua Toko" required={false}
              testId="sample-filter-account" />
            <Select value={filterPlatform} onValueChange={setFilterPlatform}>
              <SelectTrigger>
                <SelectValue placeholder="Platform" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Platform</SelectItem>
                <SelectItem value="tiktok">TikTok</SelectItem>
                <SelectItem value="instagram">Instagram</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Cari username/produk..."
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
            <CardTitle>Daftar Sample ({pagination?.total || 0})</CardTitle>
            <div className="flex rounded-md border border-border overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="sample-view-table"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <Table2 size={12} /> Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="sample-view-grid"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <LayoutGrid size={12} /> Kartu
              </button>
            </div>
            <ExportCsvButton
              filename="kirim-sample-kreator"
              testId="sample-export-csv"
              head={['Tanggal', 'Toko', 'Platform', 'Kreator', 'Jenis', 'Produk', 'SKU',
                'Warna', 'Ukuran', 'Qty', 'HPP', 'Total HPP', 'Ongkir', 'Kurir', 'Resi',
                'Status kirim', 'Progress', 'Link video']}
              rows={(samples || []).map((s) => [fmtDate(s.date || s.created_at),
                s.account_name, s.platform, s.username, s.sample_type_label || s.sample_type,
                s.product, s.sku, s.color, s.size, s.quantity, s.hpp, s.total_hpp,
                s.ongkir, s.courier, s.tracking_number, s.shipment_status, s.progress,
                s.video_link])}
            />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin" size={24} /></div>
          ) : samples.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">Tidak ada sample</div>
          ) : view === 'table' ? (
            <div className="rounded-lg border border-border overflow-x-auto">
              <table className="w-full text-xs" data-testid="sample-table">
                <thead className="bg-muted/60">
                  <tr>{SAMPLE_HEADS.map((h) => (
                    <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {samples.map(s => (
                    <tr key={s.id} className="hover:bg-muted/30" data-testid={`sample-row-${s.id}`}>
                      <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(s.date || s.created_at)}</td>
                      <td className="px-2.5 py-2">{s.account_name || '—'}</td>
                      <td className="px-2.5 py-2">
                        <div className="font-medium text-foreground">{s.username || '—'}</div>
                        <div className="text-[10px] text-muted-foreground">
                          {PLATFORM_ICONS[s.platform]} {s.sample_type_label || s.sample_type || ''}
                        </div>
                      </td>
                      <td className="px-2.5 py-2 max-w-[200px] truncate" title={s.product}>
                        {s.product || '—'}
                        {s.size || s.color ? (
                          <span className="text-[10px] text-muted-foreground"> · {s.size} {s.color}</span>
                        ) : null}
                      </td>
                      <td className="px-2.5 py-2 font-mono text-[11px]">{s.sku || '—'}</td>
                      <td className="px-2.5 py-2">{s.quantity || 0}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap">Rp {(s.hpp || 0).toLocaleString('id-ID')}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap font-semibold">
                        Rp {(s.total_hpp || 0).toLocaleString('id-ID')}
                      </td>
                      <td className="px-2.5 py-2 whitespace-nowrap">Rp {(s.ongkir || 0).toLocaleString('id-ID')}</td>
                      <td className="px-2.5 py-2">{s.courier || '—'}</td>
                      <td className="px-2.5 py-2 font-mono text-[11px]">{s.tracking_number || '—'}</td>
                      <td className="px-2.5 py-2">
                        {s.shipment_status ? (
                          <Badge className={SHIPMENT_STATUS_CONFIG[s.shipment_status]?.color}>
                            {SHIPMENT_STATUS_CONFIG[s.shipment_status]?.label || s.shipment_status}
                          </Badge>
                        ) : '—'}
                      </td>
                      <td className="px-2.5 py-2">
                        {s.progress ? (
                          <Badge className={PROGRESS_STATUS_CONFIG[s.progress]?.color}>
                            {PROGRESS_STATUS_CONFIG[s.progress]?.label || s.progress}
                          </Badge>
                        ) : '—'}
                      </td>
                      <td className="px-2.5 py-2">
                        {s.video_link ? (
                          <a href={s.video_link} target="_blank" rel="noopener noreferrer"
                            className="text-blue-600 hover:underline inline-flex items-center gap-1">
                            <Video size={11} />Video
                          </a>
                        ) : <span className="text-amber-600">belum ada</span>}
                      </td>
                      <td className="px-2.5 py-2 whitespace-nowrap">{ageDays(s.date || s.created_at)}</td>
                      <td className="px-2.5 py-2 whitespace-nowrap text-right">
                        {s.shipment_status === 'pending' && (
                          <Button onClick={() => handleShip(s.id)} disabled={actionLoading === s.id}
                            variant="ghost" size="sm" title="Tandai Dikirim">
                            {actionLoading === s.id ? <Loader2 className="animate-spin" size={14} /> : <Truck size={14} />}
                          </Button>
                        )}
                        {s.shipment_status === 'shipped' && (
                          <Button onClick={() => handleDeliver(s.id)} disabled={actionLoading === s.id}
                            variant="ghost" size="sm" title="Tandai Terkirim">
                            {actionLoading === s.id ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} />}
                          </Button>
                        )}
                        <Button onClick={() => { setShowDetail(s); setProgressUpdate({ progress: s.progress, sales_update: s.sales_update }); }}
                          variant="ghost" size="sm" title="Update Progress"><TrendingUp size={14} /></Button>
                        <Button onClick={() => openForm(s)} variant="ghost" size="sm"><Pencil size={14} /></Button>
                        <Button onClick={() => handleDelete(s.id)} variant="ghost" size="sm"><Trash2 size={14} /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="space-y-3" data-testid="sample-grid">
              {samples.map(s => (
                <div key={s.id} className="border rounded-lg p-4 space-y-2 hover:bg-muted/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-medium">{s.username}</span>
                        <span className="text-xs text-muted-foreground">{PLATFORM_ICONS[s.platform]} {s.sample_type_label}</span>
                        <span className="text-xs">{s.product}</span>
                        <Badge variant="outline" className="text-xs">{s.size} - {s.color}</Badge>
                        {s.shipment_status && <Badge className={SHIPMENT_STATUS_CONFIG[s.shipment_status]?.color}>{SHIPMENT_STATUS_CONFIG[s.shipment_status]?.label}</Badge>}
                        {s.progress && <Badge className={PROGRESS_STATUS_CONFIG[s.progress]?.color}>{PROGRESS_STATUS_CONFIG[s.progress]?.label}</Badge>}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>Qty: {s.quantity}</span>
                        <span>•</span>
                        <span>HPP: Rp {(s.total_hpp || 0).toLocaleString('id-ID')}</span>
                        <span>•</span>
                        <span>Ongkir: Rp {(s.ongkir || 0).toLocaleString('id-ID')}</span>
                      </div>
                      {s.sales_update && <p className="text-sm"><strong>Update:</strong> {s.sales_update}</p>}
                      {s.video_link && (
                        <a href={s.video_link} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                          <Video size={12} />Lihat Video
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      {s.shipment_status === 'pending' && (
                        <Button onClick={() => handleShip(s.id)} disabled={actionLoading === s.id} variant="ghost" size="sm" title="Tandai Dikirim">
                          {actionLoading === s.id ? <Loader2 className="animate-spin" size={14} /> : <Truck size={14} />}
                        </Button>
                      )}
                      {s.shipment_status === 'shipped' && (
                        <Button onClick={() => handleDeliver(s.id)} disabled={actionLoading === s.id} variant="ghost" size="sm" title="Tandai Terkirim">
                          {actionLoading === s.id ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} />}
                        </Button>
                      )}
                      <Button onClick={() => { setShowDetail(s); setProgressUpdate({ progress: s.progress, sales_update: s.sales_update }); }} variant="ghost" size="sm" title="Update Progress">
                        <TrendingUp size={14} />
                      </Button>
                      <Button onClick={() => openForm(s)} variant="ghost" size="sm">
                        <Pencil size={14} />
                      </Button>
                      <Button onClick={() => handleDelete(s.id)} variant="ghost" size="sm">
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
            <DialogTitle>{editTarget ? 'Edit Sample' : 'Tambah Sample'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Akun / Toko Marketplace (untuk track origin) *</Label>
              <Select value={form.account_id || ''} onValueChange={handleAccountChange}>
                <SelectTrigger data-testid="sample-account-select">
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
                <Label>Username KOL *</Label>
                {/* F15 — kreator dipilih dari master yang DI-ASSIGN ke toko ini.
                    `username` menjadi TURUNAN (diisi server), bukan diketik. */}
                <MarketingCreatorSelect
                  token={token} accountId={form.account_id} label=""
                  value={form.creator_id || ''}
                  onChange={(v) => setForm({ ...form, creator_id: v })}
                  testId="sample-creator-select" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Tipe</Label>
                <Select value={form.sample_type} onValueChange={v => setForm({ ...form, sample_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="live">Live Streaming</SelectItem>
                    <SelectItem value="video">Video Review</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Platform</Label>
                <Select value={form.platform} onValueChange={v => setForm({ ...form, platform: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tiktok">TikTok</SelectItem>
                    <SelectItem value="instagram">Instagram</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Kurir</Label>
                <Select value={form.courier} onValueChange={v => setForm({ ...form, courier: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="jnt">JNT</SelectItem>
                    <SelectItem value="spx">SPX</SelectItem>
                    <SelectItem value="sicepat">SiCepat</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Produk *</Label>
              {/* F15 — produk dipilih dari KATALOG toko; SKU, HPP, ukuran & warna
                  ikut master sehingga tidak perlu diketik ulang. */}
              <CatalogItemSelect
                token={token} accountId={form.account_id} label=""
                value={form.catalog_item_id || ''}
                onChange={(item) => { setSizeOptions(item?.sizes || []); setColorOptions(item?.colors || []); setForm({
                  ...form,
                  catalog_item_id: item?.id || '',
                  product: item?.name || '',
                  sku: item?.sku || '',
                  hpp: item?.hpp || 0,
                  size: (item?.sizes && item.sizes[0]) || form.size,
                  color: (item?.colors && item.colors[0]) || form.color,
                }); }}
                testId="sample-item-select" />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Size</Label>
                <Select value={form.size || ''} onValueChange={v => setForm({ ...form, size: v })}>
                  <SelectTrigger data-testid="sample-size-select"><SelectValue placeholder="Ukuran" /></SelectTrigger>
                  <SelectContent>
                    {(sizeOptions.length ? sizeOptions : ['All Size']).map(s => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Warna</Label>
                <Select value={form.color || ''} onValueChange={v => setForm({ ...form, color: v })}>
                  <SelectTrigger data-testid="sample-color-select"><SelectValue placeholder="Warna" /></SelectTrigger>
                  <SelectContent>
                    {(colorOptions.length ? colorOptions : ['-']).map(c => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Qty</Label>
                <Input type="number" value={form.quantity} onChange={e => setForm({ ...form, quantity: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>HPP (per pcs)</Label>
                <Input type="number" value={form.hpp} disabled={!!form.catalog_item_id}
                  onChange={e => setForm({ ...form, hpp: parseFloat(e.target.value) })}
                  data-testid="sample-hpp" />
                {form.catalog_item_id && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    HPP diambil dari katalog — ubah di Manajemen Katalog bila salah.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label>Ongkir</Label>
                <Input type="number" value={form.ongkir} onChange={e => setForm({ ...form, ongkir: parseFloat(e.target.value) })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Video Link</Label>
              <Input value={form.video_link} onChange={e => setForm({ ...form, video_link: e.target.value })} placeholder="https://vt.tiktok.com/..." />
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

      {/* Update Progress Dialog */}
      <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Update Progress</DialogTitle>
          </DialogHeader>
          {showDetail && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <p className="text-sm"><strong>Username:</strong> {showDetail.username}</p>
                <p className="text-sm"><strong>Produk:</strong> {showDetail.product}</p>
              </div>
              <div className="space-y-2">
                <Label>Status Progress</Label>
                <Select value={progressUpdate.progress} onValueChange={v => setProgressUpdate({ ...progressUpdate, progress: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="follow_up">Follow Up</SelectItem>
                    <SelectItem value="sold">Terjual</SelectItem>
                    <SelectItem value="no_response">No Response</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Update Penjualan</Label>
                <Textarea value={progressUpdate.sales_update} onChange={e => setProgressUpdate({ ...progressUpdate, sales_update: e.target.value })} rows={3} placeholder="Contoh: Terjual 5 pcs..." />
              </div>
              <Button onClick={handleUpdateProgress} disabled={actionLoading === showDetail.id} className="w-full">
                {actionLoading === showDetail.id && <Loader2 className="animate-spin mr-1" size={14} />}
                Update Progress
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
