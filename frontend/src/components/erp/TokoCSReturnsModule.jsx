import { useState, useEffect, useCallback, useMemo } from 'react';
import { MessageSquare, RotateCcw, Plus, Trash2, Search, Star, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { PageHeader } from './moduleAtoms';

// ── Constants (mapped to marketing_* SSOT shape) ────────────────────────────
const PLATFORM_OPTIONS = [
  { value: 'shopee', label: 'Shopee' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'tokopedia', label: 'Tokopedia' },
  { value: 'instagram', label: 'Instagram' },
];

const RETURN_REASONS = [
  { value: 'produk_tidak_sesuai', label: 'Produk Tidak Sesuai Deskripsi' },
  { value: 'ukuran_salah', label: 'Ukuran Salah/Tidak Sesuai' },
  { value: 'produk_cacat', label: 'Produk Cacat/Rusak' },
  { value: 'warna_berbeda', label: 'Warna Berbeda dari Gambar' },
  { value: 'tidak_sesuai_ekspektasi', label: 'Tidak Sesuai Ekspektasi' },
  { value: 'salah_pesan', label: 'Salah Pesan' },
  { value: 'terlambat_sampai', label: 'Terlambat Sampai' },
  { value: 'rusak_saat_pengiriman', label: 'Rusak Saat Pengiriman' },
  { value: 'lainnya', label: 'Lainnya' },
];

const COURIERS = ['jnt', 'spx', 'sicepat', 'jne', 'anteraja', 'ninja', 'grab', 'gojek'];

const RETURN_STATUS_COLORS = {
  pending: 'bg-blue-500/15 text-blue-300 border-blue-400/25',
  approved: 'bg-amber-500/15 text-amber-300 border-amber-400/25',
  rejected: 'bg-red-500/15 text-red-300 border-red-400/25',
  completed: 'bg-green-500/15 text-green-300 border-green-400/25',
  cancelled: 'bg-foreground/10 text-foreground/50 border-foreground/15',
};

const RETURN_STATUS_LABELS = {
  pending: 'Menunggu',
  approved: 'Disetujui',
  rejected: 'Ditolak',
  completed: 'Selesai',
  cancelled: 'Dibatalkan',
};

const REFUND_TYPE_LABELS = {
  full_refund: 'Refund Penuh',
  partial_refund: 'Refund Sebagian',
  exchange: 'Tukar (Reship)',
  no_refund: 'Tanpa Refund',
};

const REFUND_TYPE_COLORS = {
  full_refund: 'bg-red-500/15 text-red-300',
  partial_refund: 'bg-amber-500/15 text-amber-300',
  exchange: 'bg-blue-500/15 text-blue-300',
  no_refund: 'bg-foreground/10 text-foreground/50',
};

const REVIEW_STATUS_LABELS = {
  pending: 'Belum Dibaca',
  reviewed: 'Sudah Direspons',
};

const REVIEW_STATUS_COLORS = {
  pending: 'bg-blue-500/15 text-blue-300 border-blue-400/25',
  reviewed: 'bg-green-500/15 text-green-300 border-green-400/25',
};

const todayIso = () => new Date().toISOString().slice(0, 10);
const fmtDate = (d) => (d ? new Date(d).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' }) : '-');
const fmtRupiah = (n) => new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(n || 0));

export default function TokoCSReturnsModule({ token, defaultTab = 'cs' }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [returnsSummary, setReturnsSummary] = useState(null);
  const [reviewsSummary, setReviewsSummary] = useState(null);

  // Returns
  const [returns, setReturns] = useState([]);
  const [returnsLoading, setReturnsLoading] = useState(false);
  const [returnSearch, setReturnSearch] = useState('');
  const [returnReasonFilter, setReturnReasonFilter] = useState('all');
  const [returnStatusFilter, setReturnStatusFilter] = useState('all');
  const [returnDialog, setReturnDialog] = useState(null);
  const [savingReturn, setSavingReturn] = useState(false);
  const [decisionDialog, setDecisionDialog] = useState(null);
  const [decision, setDecision] = useState({ action: 'approve', refund_type: 'full_refund', notes: '' });

  // Reviews
  const [reviews, setReviews] = useState([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [reviewDialog, setReviewDialog] = useState(null);
  const [responseText, setResponseText] = useState('');
  const [respondingId, setRespondingId] = useState(null);
  const [ratingFilter, setRatingFilter] = useState('all');
  const [reviewStatusFilter, setReviewStatusFilter] = useState('all');

  const emptyReturn = {
    date: todayIso(),
    order_id: '',
    platform: 'shopee',
    product: '',
    price: 0,
    reason: 'produk_tidak_sesuai',
    reason_detail: '',
    courier: 'jnt',
    refund_type: 'full_refund',
    notes: '',
  };
  const emptyReview = {
    date: todayIso(),
    order_id: '',
    platform: 'shopee',
    product: '',
    rating: 5,
    review_text: '',
    category: 'kualitas_produk',
  };

  const loadReturns = useCallback(async () => {
    setReturnsLoading(true);
    try {
      const params = new URLSearchParams();
      if (returnReasonFilter !== 'all') params.set('reason', returnReasonFilter);
      if (returnStatusFilter !== 'all') params.set('status', returnStatusFilter);
      if (returnSearch) params.set('search', returnSearch);
      params.set('page_size', '50');
      const [rReturns, rSummary] = await Promise.all([
        fetch(`/api/marketing/returns?${params}`, { headers }),
        fetch('/api/marketing/returns/summary', { headers }),
      ]);
      if (rReturns.ok) {
        const j = await rReturns.json();
        setReturns(j.data || []);
      }
      if (rSummary.ok) {
        const j = await rSummary.json();
        setReturnsSummary(j.data || null);
      }
    } finally {
      setReturnsLoading(false);
    }
  }, [headers, returnReasonFilter, returnStatusFilter, returnSearch]);

  const loadReviews = useCallback(async () => {
    setReviewsLoading(true);
    try {
      const params = new URLSearchParams();
      if (reviewStatusFilter !== 'all') params.set('status', reviewStatusFilter);
      if (ratingFilter !== 'all') params.set('rating', ratingFilter);
      params.set('page_size', '50');
      const [r, rSum] = await Promise.all([
        fetch(`/api/marketing/reviews?${params}`, { headers }),
        fetch('/api/marketing/reviews/summary', { headers }),
      ]);
      if (r.ok) {
        const j = await r.json();
        setReviews(j.data || []);
      }
      if (rSum.ok) {
        const j = await rSum.json();
        setReviewsSummary(j.data || null);
      }
    } finally {
      setReviewsLoading(false);
    }
  }, [headers, reviewStatusFilter, ratingFilter]);

  useEffect(() => { loadReturns(); }, [loadReturns]);
  useEffect(() => { if (activeTab === 'cs') loadReviews(); }, [activeTab, loadReviews]);

  const saveReturn = async () => {
    if (!returnDialog?.order_id || !returnDialog?.product || !returnDialog?.reason_detail) {
      toast.error('Order ID, Produk, dan Detail alasan wajib diisi');
      return;
    }
    setSavingReturn(true);
    try {
      const { id, ...body } = { ...returnDialog, price: Number(returnDialog.price) };
      const url = id ? `/api/marketing/returns/${id}` : '/api/marketing/returns';
      const r = await fetch(url, { method: id ? 'PUT' : 'POST', headers, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      toast.success(id ? 'Return diperbarui' : `Return ${d.data?.id?.slice(0, 8) || ''} dibuat`);
      setReturnDialog(null);
      loadReturns();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSavingReturn(false);
    }
  };

  const makeDecision = async () => {
    if (!decision.notes.trim()) {
      toast.error('Catatan keputusan wajib diisi');
      return;
    }
    try {
      if (decision.action === 'approve') {
        // 1) Approve
        const r1 = await fetch(`/api/marketing/returns/${decisionDialog.id}/approve`, { method: 'POST', headers });
        if (!r1.ok) {
          const d = await r1.json();
          throw new Error(d.detail || 'Gagal approve');
        }
        // 2) Set refund_type + notes via PUT
        await fetch(`/api/marketing/returns/${decisionDialog.id}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify({ refund_type: decision.refund_type, notes: decision.notes }),
        });
        toast.success(`Disetujui — ${REFUND_TYPE_LABELS[decision.refund_type]}`);
      } else if (decision.action === 'reject') {
        const r1 = await fetch(`/api/marketing/returns/${decisionDialog.id}/reject`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ notes: decision.notes }),
        });
        if (!r1.ok) {
          const d = await r1.json();
          throw new Error(d.detail || 'Gagal reject');
        }
        toast.success('Return ditolak');
      } else if (decision.action === 'complete') {
        const r1 = await fetch(`/api/marketing/returns/${decisionDialog.id}/complete`, { method: 'POST', headers });
        if (!r1.ok) {
          const d = await r1.json();
          throw new Error(d.detail || 'Gagal complete');
        }
        toast.success('Return diselesaikan');
      }
      setDecisionDialog(null);
      loadReturns();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const deleteReturn = async (ret) => {
    if (!window.confirm(`Hapus return ${ret.id?.slice(0, 8)}?`)) return;
    const r = await fetch(`/api/marketing/returns/${ret.id}`, { method: 'DELETE', headers });
    if (!r.ok) {
      const d = await r.json();
      toast.error(d.detail || 'Gagal');
      return;
    }
    toast.success('Dihapus');
    loadReturns();
  };

  const respondReview = async (reviewId) => {
    if (!responseText.trim()) {
      toast.error('Isi teks respons');
      return;
    }
    setRespondingId(reviewId);
    try {
      const r = await fetch(`/api/marketing/reviews/${reviewId}/respond`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ response_text: responseText }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success('Respons disimpan');
      setReviewDialog(null);
      setResponseText('');
      loadReviews();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setRespondingId(null);
    }
  };

  const deleteReview = async (rev) => {
    if (!window.confirm('Hapus review ini?')) return;
    const r = await fetch(`/api/marketing/reviews/${rev.id}`, { method: 'DELETE', headers });
    if (r.ok) {
      toast.success('Dihapus');
      loadReviews();
    } else {
      toast.error('Gagal');
    }
  };

  const addReview = async () => {
    if (!reviewDialog?.review_text || !reviewDialog?.order_id || !reviewDialog?.product) {
      toast.error('Order ID, Produk dan Teks review wajib diisi');
      return;
    }
    const r = await fetch('/api/marketing/reviews', {
      method: 'POST',
      headers,
      body: JSON.stringify(reviewDialog),
    });
    const d = await r.json();
    if (!r.ok) {
      toast.error(d.detail || 'Gagal');
      return;
    }
    toast.success('Review dicatat');
    setReviewDialog(null);
    loadReviews();
  };

  const StarRating = ({ rating }) => (
    <span className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={`w-3 h-3 ${i <= rating ? 'fill-amber-400 text-amber-400' : 'text-foreground/20'}`} />
      ))}
    </span>
  );

  return (
    <div className="p-6 space-y-6" data-testid="toko-cs-module">
      <PageHeader
        title="Customer Service"
        description="Kelola ulasan pelanggan, kasus return, dan keputusan refund (marketing SSOT)"
        icon={MessageSquare}
      />

      {/* Summary Cards */}
      {returnsSummary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <GlassCard className="p-3 text-center" data-testid="card-returns-pending">
            <div className="text-2xl font-bold text-blue-400">{returnsSummary.pending || 0}</div>
            <div className="text-xs text-foreground/55">Return Pending</div>
          </GlassCard>
          <GlassCard className="p-3 text-center" data-testid="card-returns-approved">
            <div className="text-2xl font-bold text-amber-400">{returnsSummary.approved || 0}</div>
            <div className="text-xs text-foreground/55">Disetujui</div>
          </GlassCard>
          <GlassCard className="p-3 text-center" data-testid="card-returns-completed">
            <div className="text-2xl font-bold text-green-400">{returnsSummary.completed || 0}</div>
            <div className="text-xs text-foreground/55">Selesai</div>
          </GlassCard>
          <GlassCard className="p-3 text-center" data-testid="card-returns-refund-amount">
            <div className="text-lg font-bold text-red-400">{fmtRupiah(returnsSummary.total_refund || 0)}</div>
            <div className="text-xs text-foreground/55">Total Refund</div>
          </GlassCard>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="cs" data-testid="tab-cs">Ulasan & CS</TabsTrigger>
          <TabsTrigger value="returns" data-testid="tab-returns">Return & Refund</TabsTrigger>
        </TabsList>

        {/* CS / REVIEWS TAB */}
        <TabsContent value="cs" className="space-y-4">
          {/* Review summary inline (if available) */}
          {reviewsSummary && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="reviews-summary">
              <GlassCard className="p-3 text-center">
                <div className="text-2xl font-bold text-blue-400">{reviewsSummary.pending || 0}</div>
                <div className="text-xs text-foreground/55">Belum Dibaca</div>
              </GlassCard>
              <GlassCard className="p-3 text-center">
                <div className="text-2xl font-bold text-amber-400">{reviewsSummary.avg_rating || 0}⭐</div>
                <div className="text-xs text-foreground/55">Rating Rata-rata</div>
              </GlassCard>
              <GlassCard className="p-3 text-center">
                <div className="text-2xl font-bold text-red-400">{reviewsSummary.low_rating || 0}</div>
                <div className="text-xs text-foreground/55">Rating Rendah (1-2⭐)</div>
              </GlassCard>
              <GlassCard className="p-3 text-center">
                <div className="text-2xl font-bold text-green-400">{reviewsSummary.reviewed || 0}</div>
                <div className="text-xs text-foreground/55">Sudah Direspons</div>
              </GlassCard>
            </div>
          )}

          <div className="flex gap-2 flex-wrap">
            <div className="flex gap-1">
              {['all', '1', '2', '3'].map((r) => (
                <button
                  key={r}
                  onClick={() => setRatingFilter(r)}
                  className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                    ratingFilter === r ? 'bg-red-500/15 border-red-400/30 text-red-300' : 'border-foreground/15 text-foreground/60'
                  }`}
                  data-testid={`filter-rating-${r}`}
                >
                  {r === 'all' ? 'Semua Rating' : `${r}⭐`}
                </button>
              ))}
            </div>
            <Select value={reviewStatusFilter} onValueChange={setReviewStatusFilter}>
              <SelectTrigger className="w-36" data-testid="filter-review-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                <SelectItem value="pending">Belum Dibaca</SelectItem>
                <SelectItem value="reviewed">Sudah Direspons</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" onClick={() => setReviewDialog({ ...emptyReview })} className="gap-1 ml-auto" data-testid="btn-add-review">
              <Plus className="w-3.5 h-3.5" /> Catat Review
            </Button>
          </div>

          {reviewsLoading ? (
            <div className="text-center py-8 text-foreground/40">Memuat...</div>
          ) : reviews.length === 0 ? (
            <GlassCard className="p-10 text-center">
              <MessageSquare className="w-10 h-10 mx-auto mb-3 text-foreground/25" />
              <p className="text-foreground/50 text-sm">Belum ada ulasan pelanggan</p>
            </GlassCard>
          ) : (
            <div className="space-y-2">
              {reviews.map((rev) => (
                <GlassCard key={rev.id} className="p-4" data-testid={`review-row-${rev.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <StarRating rating={rev.rating} />
                        <span className="text-sm font-medium">{rev.product || 'Produk tidak diketahui'}</span>
                        <span className="text-xs text-foreground/40 capitalize">{rev.platform}</span>
                        {rev.order_id && <span className="text-xs font-mono text-foreground/50">#{rev.order_id}</span>}
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${REVIEW_STATUS_COLORS[rev.status] || 'bg-foreground/10 text-foreground/50 border-foreground/15'}`}>
                          {REVIEW_STATUS_LABELS[rev.status] || rev.status}
                        </span>
                      </div>
                      <p className="text-sm text-foreground/70 mt-1.5">{rev.review_text}</p>
                      {rev.response_text && (
                        <div className="mt-2 p-2 rounded-lg bg-primary/5 border border-primary/15">
                          <p className="text-xs text-primary/80">
                            <span className="font-medium">Respons:</span> {rev.response_text}
                          </p>
                        </div>
                      )}
                      <div className="text-xs text-foreground/35 mt-1">
                        {fmtDate(rev.date || rev.created_at)} {rev.category_label ? `• ${rev.category_label}` : ''}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {rev.status !== 'reviewed' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs h-7"
                          onClick={() => { setReviewDialog({ ...rev, _action: 'respond' }); setResponseText(''); }}
                          data-testid={`btn-respond-${rev.id}`}
                        >
                          Respons
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs h-7 text-red-400"
                        onClick={() => deleteReview(rev)}
                        data-testid={`btn-delete-review-${rev.id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </TabsContent>

        {/* RETURNS TAB */}
        <TabsContent value="returns" className="space-y-4">
          <div className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-40">
              <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-foreground/40" />
              <Input
                placeholder="Cari order / produk / alasan..."
                value={returnSearch}
                onChange={(e) => setReturnSearch(e.target.value)}
                className="pl-8"
                data-testid="input-return-search"
              />
            </div>
            <Select value={returnReasonFilter} onValueChange={setReturnReasonFilter}>
              <SelectTrigger className="w-44" data-testid="filter-return-reason"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Alasan</SelectItem>
                {RETURN_REASONS.map((r) => (
                  <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={returnStatusFilter} onValueChange={setReturnStatusFilter}>
              <SelectTrigger className="w-36" data-testid="filter-return-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                {Object.entries(RETURN_STATUS_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" onClick={() => setReturnDialog({ ...emptyReturn })} className="gap-1" data-testid="btn-add-return">
              <Plus className="w-3.5 h-3.5" /> Kasus Baru
            </Button>
          </div>

          {returnsLoading ? (
            <div className="text-center py-8 text-foreground/40">Memuat...</div>
          ) : returns.length === 0 ? (
            <GlassCard className="p-10 text-center">
              <RotateCcw className="w-10 h-10 mx-auto mb-3 text-foreground/25" />
              <p className="text-foreground/50 text-sm">Belum ada kasus return/refund</p>
            </GlassCard>
          ) : (
            <div className="space-y-2">
              {returns.map((ret) => (
                <GlassCard key={ret.id} className="p-4" data-testid={`return-row-${ret.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-foreground/50">#{ret.id?.slice(0, 8)}</span>
                        <span className="font-medium text-sm">{ret.product || '-'}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full border ${RETURN_STATUS_COLORS[ret.status] || ''}`}>
                          {RETURN_STATUS_LABELS[ret.status] || ret.status}
                        </span>
                        <span className="text-xs text-foreground/50 capitalize">{ret.platform}</span>
                        {ret.refund_type && ret.refund_type !== 'no_refund' && (
                          <span className={`text-xs px-2 py-0.5 rounded ${REFUND_TYPE_COLORS[ret.refund_type] || ''}`}>
                            {REFUND_TYPE_LABELS[ret.refund_type] || ret.refund_type}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-foreground/65 mt-1">
                        <span className="text-foreground/40">{ret.reason_label || ret.reason}:</span> {ret.reason_detail}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-foreground/40 mt-0.5 flex-wrap">
                        {ret.order_id && <span>Order: <span className="font-mono">{ret.order_id}</span></span>}
                        {ret.price > 0 && <span>Harga: {fmtRupiah(ret.price)}</span>}
                        {ret.refund_amount > 0 && <span className="text-red-300">Refund: {fmtRupiah(ret.refund_amount)}</span>}
                        {ret.courier && <span className="uppercase">{ret.courier}</span>}
                      </div>
                      <div className="text-xs text-foreground/35 mt-0.5">{fmtDate(ret.date || ret.created_at)}</div>
                      {ret.notes && (
                        <div className="mt-1.5 p-1.5 rounded bg-foreground/5 text-xs text-foreground/55">
                          <span className="font-medium">Catatan:</span> {ret.notes}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {ret.status === 'pending' && (
                        <Button
                          size="sm"
                          className="text-xs h-7"
                          onClick={() => { setDecisionDialog(ret); setDecision({ action: 'approve', refund_type: 'full_refund', notes: '' }); }}
                          data-testid={`btn-decision-${ret.id}`}
                        >
                          Putuskan
                        </Button>
                      )}
                      {ret.status === 'approved' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs h-7"
                          onClick={() => { setDecisionDialog(ret); setDecision({ action: 'complete', refund_type: ret.refund_type || 'full_refund', notes: '' }); }}
                          data-testid={`btn-complete-${ret.id}`}
                        >
                          <CheckCircle className="w-3 h-3 mr-1" /> Selesaikan
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs h-7 text-red-400"
                        onClick={() => deleteReturn(ret)}
                        data-testid={`btn-delete-return-${ret.id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Add Review Dialog */}
      {reviewDialog && !reviewDialog._action && (
        <Dialog open={!!reviewDialog} onOpenChange={() => setReviewDialog(null)}>
          <DialogContent className="max-w-md" data-testid="dialog-add-review">
            <DialogHeader><DialogTitle>Catat Review</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Platform</Label>
                  <Select value={reviewDialog.platform} onValueChange={(v) => setReviewDialog((d) => ({ ...d, platform: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PLATFORM_OPTIONS.map((p) => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Rating</Label>
                  <Select value={String(reviewDialog.rating)} onValueChange={(v) => setReviewDialog((d) => ({ ...d, rating: Number(v) }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <SelectItem key={n} value={String(n)}>{n} ⭐</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">No. Order *</Label>
                  <Input
                    className="mt-1"
                    value={reviewDialog.order_id}
                    onChange={(e) => setReviewDialog((d) => ({ ...d, order_id: e.target.value }))}
                    data-testid="input-review-order-id"
                  />
                </div>
                <div>
                  <Label className="text-xs">Tanggal</Label>
                  <Input
                    type="date"
                    className="mt-1"
                    value={reviewDialog.date}
                    onChange={(e) => setReviewDialog((d) => ({ ...d, date: e.target.value }))}
                  />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Nama Produk *</Label>
                  <Input
                    className="mt-1"
                    value={reviewDialog.product}
                    onChange={(e) => setReviewDialog((d) => ({ ...d, product: e.target.value }))}
                    data-testid="input-review-product"
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs">Teks Review *</Label>
                <Textarea
                  className="mt-1"
                  rows={3}
                  value={reviewDialog.review_text}
                  onChange={(e) => setReviewDialog((d) => ({ ...d, review_text: e.target.value }))}
                  data-testid="input-review-text"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReviewDialog(null)}>Batal</Button>
              <Button onClick={addReview} data-testid="btn-save-review">Simpan</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Respond Review Dialog */}
      {reviewDialog?._action === 'respond' && (
        <Dialog open={!!reviewDialog} onOpenChange={() => setReviewDialog(null)}>
          <DialogContent className="max-w-md" data-testid="dialog-respond-review">
            <DialogHeader><DialogTitle>Respons Review</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
              <div className="p-3 rounded-lg bg-foreground/5 border border-foreground/10">
                <div className="flex items-center gap-2 mb-1">
                  <StarRating rating={reviewDialog.rating} />
                  <span className="text-sm font-medium">{reviewDialog.product}</span>
                </div>
                <p className="text-sm text-foreground/60">{reviewDialog.review_text}</p>
              </div>
              <div>
                <Label className="text-xs">Template Respons</Label>
                <div className="flex flex-wrap gap-1 mt-1 mb-2">
                  {[
                    'Terima kasih atas ulasannya! Kami akan terus meningkatkan kualitas.',
                    'Mohon maaf atas pengalaman yang kurang baik. Tim kami akan segera membantu.',
                    'Terima kasih sudah berbelanja. Semoga puas dengan produk kami!',
                  ].map((t, i) => (
                    <button
                      key={i}
                      className="text-xs px-2 py-1 rounded border border-foreground/15 hover:border-primary/30 text-foreground/60"
                      onClick={() => setResponseText(t)}
                    >
                      Template {i + 1}
                    </button>
                  ))}
                </div>
                <Textarea
                  className="mt-1"
                  rows={3}
                  placeholder="Tulis respons Anda..."
                  value={responseText}
                  onChange={(e) => setResponseText(e.target.value)}
                  data-testid="input-response-text"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReviewDialog(null)}>Batal</Button>
              <Button
                onClick={() => respondReview(reviewDialog.id)}
                disabled={!!respondingId || !responseText.trim()}
                data-testid="btn-send-response"
              >
                {respondingId ? 'Mengirim...' : 'Kirim Respons'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Return New/Edit Dialog */}
      {returnDialog && (
        <Dialog open={!!returnDialog} onOpenChange={() => setReturnDialog(null)}>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="dialog-return">
            <DialogHeader><DialogTitle>{returnDialog.id ? 'Edit Return' : 'Kasus Return Baru'}</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Platform</Label>
                  <Select value={returnDialog.platform} onValueChange={(v) => setReturnDialog((d) => ({ ...d, platform: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PLATFORM_OPTIONS.map((p) => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Kurir</Label>
                  <Select value={returnDialog.courier} onValueChange={(v) => setReturnDialog((d) => ({ ...d, courier: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {COURIERS.map((c) => (
                        <SelectItem key={c} value={c}><span className="uppercase">{c}</span></SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">No. Order *</Label>
                  <Input
                    className="mt-1"
                    value={returnDialog.order_id}
                    onChange={(e) => setReturnDialog((d) => ({ ...d, order_id: e.target.value }))}
                    data-testid="input-return-order-id"
                  />
                </div>
                <div>
                  <Label className="text-xs">Tanggal</Label>
                  <Input
                    type="date"
                    className="mt-1"
                    value={returnDialog.date}
                    onChange={(e) => setReturnDialog((d) => ({ ...d, date: e.target.value }))}
                  />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Produk *</Label>
                  <Input
                    className="mt-1"
                    value={returnDialog.product}
                    onChange={(e) => setReturnDialog((d) => ({ ...d, product: e.target.value }))}
                    data-testid="input-return-product"
                  />
                </div>
                <div>
                  <Label className="text-xs">Harga (Rp)</Label>
                  <Input
                    type="number"
                    className="mt-1"
                    min={0}
                    value={returnDialog.price}
                    onChange={(e) => setReturnDialog((d) => ({ ...d, price: e.target.value }))}
                    data-testid="input-return-price"
                  />
                </div>
                <div>
                  <Label className="text-xs">Tipe Refund</Label>
                  <Select value={returnDialog.refund_type} onValueChange={(v) => setReturnDialog((d) => ({ ...d, refund_type: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(REFUND_TYPE_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label className="text-xs">Alasan Return</Label>
                <Select value={returnDialog.reason} onValueChange={(v) => setReturnDialog((d) => ({ ...d, reason: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {RETURN_REASONS.map((r) => (
                      <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Detail Alasan *</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={returnDialog.reason_detail}
                  onChange={(e) => setReturnDialog((d) => ({ ...d, reason_detail: e.target.value }))}
                  data-testid="input-return-detail"
                />
              </div>
              <div>
                <Label className="text-xs">Catatan</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={returnDialog.notes}
                  onChange={(e) => setReturnDialog((d) => ({ ...d, notes: e.target.value }))}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReturnDialog(null)}>Batal</Button>
              <Button onClick={saveReturn} disabled={savingReturn} data-testid="btn-save-return">
                {savingReturn ? 'Menyimpan...' : 'Simpan'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Decision Dialog */}
      {decisionDialog && (
        <Dialog open={!!decisionDialog} onOpenChange={() => setDecisionDialog(null)}>
          <DialogContent className="max-w-md" data-testid="dialog-decision">
            <DialogHeader>
              <DialogTitle>
                {decision.action === 'complete' ? 'Selesaikan Return' : 'Putuskan Kasus Return'}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div className="p-3 rounded-lg bg-foreground/5 border border-foreground/10 text-sm">
                <div className="font-medium">{decisionDialog.product}</div>
                <div className="text-foreground/60 text-xs mt-0.5">{decisionDialog.reason_detail}</div>
                {decisionDialog.order_id && (
                  <div className="text-foreground/40 text-xs mt-0.5">Order: <span className="font-mono">{decisionDialog.order_id}</span></div>
                )}
              </div>

              {decision.action !== 'complete' && (
                <div>
                  <Label className="text-xs">Aksi</Label>
                  <Select value={decision.action} onValueChange={(v) => setDecision((d) => ({ ...d, action: v }))}>
                    <SelectTrigger className="mt-1" data-testid="select-decision-action"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="approve">Setujui Return</SelectItem>
                      <SelectItem value="reject">Tolak Return</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {decision.action === 'approve' && (
                <div>
                  <Label className="text-xs">Tipe Refund</Label>
                  <Select value={decision.refund_type} onValueChange={(v) => setDecision((d) => ({ ...d, refund_type: v }))}>
                    <SelectTrigger className="mt-1" data-testid="select-refund-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="full_refund">Refund Penuh</SelectItem>
                      <SelectItem value="partial_refund">Refund Sebagian (70%)</SelectItem>
                      <SelectItem value="exchange">Tukar/Kirim Ulang</SelectItem>
                      <SelectItem value="no_refund">Tanpa Refund</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div>
                <Label className="text-xs">Catatan {decision.action !== 'complete' ? '*' : ''}</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={decision.notes}
                  onChange={(e) => setDecision((d) => ({ ...d, notes: e.target.value }))}
                  data-testid="input-decision-notes"
                  placeholder={decision.action === 'complete' ? 'Opsional' : 'Wajib diisi...'}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDecisionDialog(null)}>Batal</Button>
              <Button
                onClick={makeDecision}
                disabled={decision.action !== 'complete' && !decision.notes.trim()}
                data-testid="btn-confirm-decision"
                className={decision.action === 'reject' ? 'bg-red-500 hover:bg-red-600' : ''}
              >
                {decision.action === 'approve' && <CheckCircle className="w-3.5 h-3.5 mr-1" />}
                {decision.action === 'reject' && <XCircle className="w-3.5 h-3.5 mr-1" />}
                {decision.action === 'complete' && <CheckCircle className="w-3.5 h-3.5 mr-1" />}
                Konfirmasi
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
