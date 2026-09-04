import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Star, Plus, Pencil, Trash2, Sparkles, RefreshCw, CheckCircle2, AlertCircle,
  Filter, X, Loader2, MessageSquare, ThumbsUp, ThumbsDown, Table2, LayoutGrid
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
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './ActiveAccountBar';
import axios from 'axios';
import { CatalogItemSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS = { shopee: '🛍️', tiktok: '🎵', tokopedia: '🟢', instagram: '📷' };
// F10 (2026-08-13) — layar ulasan dulu KARTU-SAJA. Ulasan dibaca untuk MENCARI POLA
// ("produk mana yang dikeluhkan", "berapa yang belum dibalas"), dan pola hanya
// terlihat kalau barisnya sejajar. Kolom "Balasan" sengaja menyebut **belum dibalas**
// secara terbuka — ulasan bintang 1 yang tak terbalas adalah biaya yang tak terlihat.
const REVIEWS_VIEW_KEY = 'marketing_reviews_view';
// F10 (sesi #10) — daftar yang tidak bisa diunduh memaksa staf menyalin ulang
// dengan tangan (sumber salah-ketik). Satu pembuat CSV: `lib/csv.js`.
import ExportCsvButton from '@/components/ui/export-csv-button';

const REVIEW_HEADS = ['Tanggal', 'Rating', 'Platform', 'Order ID', 'Toko', 'Produk',
  'Isi ulasan', 'Kategori', 'Status', 'Balasan', 'Aksi'];
const fmtDate = (v) => {
  if (!v) return '—';
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s.slice(0, 10) : d.toISOString().slice(0, 10);
};
const STATUS_CONFIG = {
  pending:  { label: 'Menunggu', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300', icon: AlertCircle },
  reviewed: { label: 'Direspon',  color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
};

function StarRating({ rating, size = 14 }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map(i => (
        <Star key={i} size={size} className={i <= rating ? 'fill-amber-400 text-amber-700 dark:text-amber-400' : 'text-foreground/80 dark:text-gray-600'} />
      ))}
    </div>
  );
}

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
  date: '', order_id: '', platform: 'shopee', rating: 5, product: '',
  category: 'tanpa_keterangan', review_text: '', screenshot_url: '', response_text: ''
};

export default function RatingReviewModule({ token }) {
  const { toast } = useToast();
  const authH = useMemo(() => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const { accounts: masterAccounts, byId: accountById } = useMarketingAccounts(token);
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const [summary, setSummary] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [categories, setCategories] = useState([]);
  const [platforms, setPlatforms] = useState([]);

  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState('');

  const [filterStatus, setFilterStatus] = useState('');
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterRating, setFilterRating] = useState(0);
  const [filterCategory, setFilterCategory] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formLoading, setFormLoading] = useState(false);

  const [showDetail, setShowDetail] = useState(null);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(REVIEWS_VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  const [responseText, setResponseText] = useState('');
  const [respondLoading, setRespondLoading] = useState(false);

  const fetchMeta = useCallback(async () => {
    try {
      const [catRes, platRes] = await Promise.all([
        axios.get(`${API}/api/marketing/reviews/categories`, { headers: authH }),
        axios.get(`${API}/api/marketing/reviews/platforms`, { headers: authH })
      ]);
      setCategories(catRes.data.categories || []);
      setPlatforms(platRes.data.platforms || []);
    } catch (e) {
      console.error('Meta fetch error:', e);
    }
  }, [authH]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/marketing/reviews/summary`, { headers: authH });
      setSummary(res.data.data || {});
    } catch (e) {
      console.error('Summary fetch error:', e);
    }
  }, [authH]);

  const fetchReviews = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = { page, page_size: 20 };
      if (filterStatus) params.status = filterStatus;
      if (filterPlatform) params.platform = filterPlatform;
      if (filterRating > 0) params.rating = filterRating;
      if (filterCategory) params.category = filterCategory;
      if (searchQuery) params.search = searchQuery;
      if (activeAccount?.id) params.account_id = activeAccount.id;

      const res = await axios.get(`${API}/api/marketing/reviews`, { headers: authH, params });
      setReviews(res.data.data || []);
      setPagination(res.data.pagination || {});
    } catch (e) {
      console.error('Reviews fetch error:', e);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authH, filterStatus, filterPlatform, filterRating, filterCategory, searchQuery, activeAccount]);

  useEffect(() => {
    fetchMeta();
    fetchSummary();
  }, [fetchMeta, fetchSummary]);

  useEffect(() => {
    fetchReviews(currentPage);
  }, [fetchReviews, currentPage]);

  useEffect(() => {
    try { localStorage.setItem(REVIEWS_VIEW_KEY, view); } catch { /* penyimpanan diblokir */ }
  }, [view]);

  const openForm = (review = null) => {
    if (review) {
      setEditTarget(review);
      setForm({
        account_id: review.account_id || '',
        account_name: review.account_name || '',
        date: review.date,
        order_id: review.order_id,
        platform: review.platform,
        rating: review.rating,
        product: review.product,
        category: review.category,
        review_text: review.review_text,
        screenshot_url: review.screenshot_url || '',
        response_text: review.response_text || ''
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
    if (!form.order_id || !(form.catalog_item_id || form.product) || !form.review_text) {
      toast({ title: 'Error', description: 'Order ID, Produk, dan Review wajib diisi', variant: 'destructive' });
      return;
    }
    try {
      setFormLoading(true);
      if (editTarget) {
        await axios.put(`${API}/api/marketing/reviews/${editTarget.id}`, form, { headers: authH });
        toast({ title: 'Berhasil', description: 'Review diperbarui' });
      } else {
        await axios.post(`${API}/api/marketing/reviews`, form, { headers: authH });
        toast({ title: 'Berhasil', description: 'Review ditambahkan' });
      }
      closeForm();
      fetchReviews(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus review ini?')) return;
    try {
      await axios.delete(`${API}/api/marketing/reviews/${id}`, { headers: authH });
      toast({ title: 'Berhasil', description: 'Review dihapus' });
      fetchReviews(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const handleAICategorize = async (reviewId) => {
    try {
      setAiLoading(reviewId);
      const res = await axios.post(`${API}/api/marketing/reviews/${reviewId}/ai-categorize`, {}, { headers: authH });
      toast({ title: 'AI Sukses', description: `Kategori: ${res.data.result?.category || 'N/A'}` });
      fetchReviews(currentPage);
    } catch (e) {
      toast({ title: 'AI Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setAiLoading('');
    }
  };

  const handleRespond = async () => {
    if (!responseText) {
      toast({ title: 'Error', description: 'Response text wajib diisi', variant: 'destructive' });
      return;
    }
    try {
      setRespondLoading(true);
      await axios.post(`${API}/api/marketing/reviews/${showDetail.id}/respond`, { response_text: responseText }, { headers: authH });
      toast({ title: 'Berhasil', description: 'Response terkirim' });
      setShowDetail(null);
      setResponseText('');
      fetchReviews(currentPage);
      fetchSummary();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || e.message, variant: 'destructive' });
    } finally {
      setRespondLoading(false);
    }
  };

  const clearFilters = () => {
    setFilterStatus('');
    setFilterPlatform('');
    setFilterRating(0);
    setFilterCategory('');
    setSearchQuery('');
    setCurrentPage(1);
  };

  const s = summary || {};
  const activeFilters = [filterStatus, filterPlatform, filterRating > 0, filterCategory, searchQuery].filter(Boolean).length;

  return (
    <div className="space-y-6" data-testid="rating-review-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Rating & Review Management</h1>
          <p className="text-sm text-muted-foreground mt-1">Kelola review produk dari berbagai platform</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => fetchReviews(currentPage)} variant="outline" size="sm">
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
          <Button onClick={() => openForm()} size="sm">
            <Plus size={14} className="mr-1" />Tambah Review
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <ActiveAccountBar accounts={masterAccounts} activeAccount={activeAccount} onAccountChange={acc => { setActiveAccount(acc); setCurrentPage(1); }} hint="Filter review by akun:" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard label="Total Review" value={s.total || 0} color="text-blue-600" bg="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950/30 dark:to-blue-900/30" icon={Star} />
        <KPICard label="Rating Rendah" value={s.low_rating || 0} sub="(1-2 bintang)" color="text-red-600" bg="bg-gradient-to-br from-red-50 to-red-100 dark:from-red-950/30 dark:to-red-900/30" icon={ThumbsDown} />
        <KPICard label="Rata-rata Rating" value={s.avg_rating || 0} color="text-amber-600" bg="bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-950/30 dark:to-amber-900/30" icon={Star} />
        <KPICard label="Menunggu" value={s.pending || 0} color="text-orange-600" bg="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-950/30 dark:to-orange-900/30" icon={AlertCircle} />
        <KPICard label="Direspon" value={s.reviewed || 0} color="text-emerald-600" bg="bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-950/30 dark:to-emerald-900/30" icon={CheckCircle2} />
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
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Status</SelectItem>
                <SelectItem value="pending">Menunggu</SelectItem>
                <SelectItem value="reviewed">Direspon</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterPlatform} onValueChange={setFilterPlatform}>
              <SelectTrigger>
                <SelectValue placeholder="Platform" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Platform</SelectItem>
                {platforms.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={filterRating.toString()} onValueChange={v => setFilterRating(parseInt(v))}>
              <SelectTrigger>
                <SelectValue placeholder="Rating" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">Semua Rating</SelectItem>
                <SelectItem value="1">1 Bintang</SelectItem>
                <SelectItem value="2">2 Bintang</SelectItem>
                <SelectItem value="3">3 Bintang</SelectItem>
                <SelectItem value="4">4 Bintang</SelectItem>
                <SelectItem value="5">5 Bintang</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterCategory} onValueChange={setFilterCategory}>
              <SelectTrigger>
                <SelectValue placeholder="Kategori" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Semua Kategori</SelectItem>
                {categories.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
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
            <CardTitle>Daftar Review ({pagination?.total || 0})</CardTitle>
            <div className="flex rounded-md border border-border overflow-hidden">
              <button type="button" onClick={() => setView('table')} data-testid="reviews-view-table"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <Table2 size={12} /> Tabel
              </button>
              <button type="button" onClick={() => setView('grid')} data-testid="reviews-view-grid"
                className={`px-2.5 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                  ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
                <LayoutGrid size={12} /> Kartu
              </button>
            </div>
            <ExportCsvButton
              filename="rating-ulasan-toko"
              testId="reviews-export-csv"
              head={['Tanggal', 'Rating', 'Platform', 'Order ID', 'Toko', 'Produk',
                'Isi ulasan', 'Kategori', 'Status', 'Balasan']}
              rows={(reviews || []).map((r) => [fmtDate(r.date || r.created_at), r.rating,
                r.platform, r.order_id, r.account_name, r.product, r.review_text,
                r.category_label, r.status, r.response_text])}
            />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin" size={24} /></div>
          ) : reviews.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">Tidak ada review</div>
          ) : view === 'table' ? (
            <div className="rounded-lg border border-border overflow-x-auto">
              <table className="w-full text-xs" data-testid="reviews-table">
                <thead className="bg-muted/60">
                  <tr>{REVIEW_HEADS.map((h) => (
                    <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {reviews.map(r => (
                    <tr key={r.id} className="hover:bg-muted/30" data-testid={`reviews-row-${r.id}`}>
                      <td className="px-2.5 py-2 whitespace-nowrap">{fmtDate(r.date || r.created_at)}</td>
                      <td className="px-2.5 py-2"><StarRating rating={r.rating} size={12} /></td>
                      <td className="px-2.5 py-2 whitespace-nowrap">{PLATFORM_ICONS[r.platform]} {r.platform || '—'}</td>
                      <td className="px-2.5 py-2 font-mono text-[11px]">{r.order_id || '—'}</td>
                      <td className="px-2.5 py-2">{r.account_name || '—'}</td>
                      <td className="px-2.5 py-2 max-w-[200px] truncate" title={r.product}>{r.product || '—'}</td>
                      <td className="px-2.5 py-2 max-w-[280px] truncate" title={r.review_text}>
                        {r.review_text || '—'}
                      </td>
                      <td className="px-2.5 py-2">{r.category_label || '—'}</td>
                      <td className="px-2.5 py-2">
                        {r.status ? (
                          <Badge className={STATUS_CONFIG[r.status]?.color}>
                            {STATUS_CONFIG[r.status]?.label || r.status}
                          </Badge>
                        ) : '—'}
                      </td>
                      <td className="px-2.5 py-2 max-w-[220px] truncate" title={r.response_text}>
                        {r.response_text || <span className="text-amber-600">belum dibalas</span>}
                      </td>
                      <td className="px-2.5 py-2 whitespace-nowrap text-right">
                        <Button onClick={() => setShowDetail(r)} variant="ghost" size="sm"
                          data-testid={`reviews-detail-${r.id}`}><MessageSquare size={14} /></Button>
                        {aiLoading === r.id ? <Loader2 className="animate-spin inline" size={14} /> : (
                          <Button onClick={() => handleAICategorize(r.id)} variant="ghost" size="sm"
                            title="AI Kategorisasi"><Sparkles size={14} /></Button>
                        )}
                        <Button onClick={() => openForm(r)} variant="ghost" size="sm"><Pencil size={14} /></Button>
                        <Button onClick={() => handleDelete(r.id)} variant="ghost" size="sm"><Trash2 size={14} /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="space-y-3" data-testid="reviews-grid">
              {reviews.map(r => (
                <div key={r.id} className="border rounded-lg p-4 space-y-2 hover:bg-muted/30 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <StarRating rating={r.rating} size={16} />
                        <span className="text-xs text-muted-foreground">{PLATFORM_ICONS[r.platform]} {r.platform}</span>
                        <Badge variant="outline" className="text-xs">{r.order_id}</Badge>
                        <span className="text-xs font-medium">{r.product}</span>
                        {r.status && <Badge className={STATUS_CONFIG[r.status]?.color}>{STATUS_CONFIG[r.status]?.label}</Badge>}
                      </div>
                      <p className="text-sm">{r.review_text}</p>
                      {r.category_label && (
                        <Badge variant="secondary" className="text-xs">{r.category_label}</Badge>
                      )}
                      {r.response_text && (
                        <div className="mt-2 p-2 bg-muted rounded-md">
                          <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                            <MessageSquare size={12} />Response:
                          </p>
                          <p className="text-sm">{r.response_text}</p>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      <Button onClick={() => setShowDetail(r)} variant="ghost" size="sm">
                        <MessageSquare size={14} />
                      </Button>
                      {aiLoading === r.id ? (
                        <Loader2 className="animate-spin" size={14} />
                      ) : (
                        <Button onClick={() => handleAICategorize(r.id)} variant="ghost" size="sm" title="AI Kategorisasi">
                          <Sparkles size={14} />
                        </Button>
                      )}
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
            <DialogTitle>{editTarget ? 'Edit Review' : 'Tambah Review'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Akun / Toko Marketplace *</Label>
              <Select value={form.account_id || ''} onValueChange={handleAccountChange}>
                <SelectTrigger data-testid="review-account-select">
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
                <Label>Rating</Label>
                <Select value={form.rating.toString()} onValueChange={v => setForm({ ...form, rating: parseInt(v) })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[1, 2, 3, 4, 5].map(r => <SelectItem key={r} value={r.toString()}>{r} Bintang</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Kategori</Label>
                <Select value={form.category} onValueChange={v => setForm({ ...form, category: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {categories.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
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
                testId="review-item-select" />
            </div>
            <div className="space-y-2">
              <Label>Review Text *</Label>
              <Textarea value={form.review_text} onChange={e => setForm({ ...form, review_text: e.target.value })} rows={3} placeholder="Isi review..." />
            </div>
            <div className="space-y-2">
              <Label>Response (Opsional)</Label>
              <Textarea value={form.response_text} onChange={e => setForm({ ...form, response_text: e.target.value })} rows={3} placeholder="Response..." />
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

      {/* Detail + Respond Dialog */}
      <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Detail Review</DialogTitle>
          </DialogHeader>
          {showDetail && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <StarRating rating={showDetail.rating} size={18} />
                  <span className="text-sm text-muted-foreground">{PLATFORM_ICONS[showDetail.platform]} {showDetail.platform}</span>
                </div>
                <p className="text-sm"><strong>Order:</strong> {showDetail.order_id}</p>
                <p className="text-sm"><strong>Produk:</strong> {showDetail.product}</p>
                <p className="text-sm"><strong>Review:</strong> {showDetail.review_text}</p>
                {showDetail.response_text && (
                  <div className="p-3 bg-muted rounded-md">
                    <p className="text-xs text-muted-foreground mb-1">Response:</p>
                    <p className="text-sm">{showDetail.response_text}</p>
                  </div>
                )}
              </div>
              {showDetail.status === 'pending' && (
                <div className="space-y-2">
                  <Label>Kirim Response</Label>
                  <Textarea value={responseText} onChange={e => setResponseText(e.target.value)} rows={3} placeholder="Tulis response..." />
                  <Button onClick={handleRespond} disabled={respondLoading} className="w-full">
                    {respondLoading && <Loader2 className="animate-spin mr-1" size={14} />}
                    Kirim Response
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
