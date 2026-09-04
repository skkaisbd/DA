import { useState, useEffect, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Package, Inbox, CheckCircle2, Truck, XCircle, Clock,
  AlertTriangle, Search, Eye, Trash2, FileText
} from 'lucide-react';
import { toast } from '../ui/sonner';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL || '';

const STATUS_CONF = {
  draft:     { label: 'Draft',     cls: 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',     Icon: Clock },
  submitted: { label: 'Menunggu',  cls: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-500 border-amber-400 dark:border-amber-500/30',  Icon: Inbox },
  allocated: { label: 'Disiapkan', cls: 'bg-sky-100 dark:bg-sky-500/15 text-sky-500 border-sky-400 dark:border-sky-500/30',        Icon: Package },
  delivered: { label: 'Terkirim',  cls: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-500 border-emerald-400 dark:border-emerald-500/30', Icon: CheckCircle2 },
  rejected:  { label: 'Ditolak',   cls: 'bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border-red-400 dark:border-red-500/30',        Icon: XCircle },
  cancelled: { label: 'Batal',     cls: 'bg-muted dark:bg-zinc-500/15 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',     Icon: XCircle },
};

// P3 TD-009 (Session #11.10): request_type discriminator labels
const TYPE_CONF = {
  rnd_sample:         { label: 'RnD Sample',      cls: 'bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-300 border-violet-400 dark:border-violet-500/30' },
  internal_issuance:  { label: 'Internal',        cls: 'bg-cyan-100 dark:bg-cyan-500/15 text-cyan-600 dark:text-cyan-300 border-cyan-400 dark:border-cyan-500/30' },
  vendor_additional:  { label: 'Vendor Add',      cls: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-500/30' },
  vendor_replacement: { label: 'Vendor Replace',  cls: 'bg-fuchsia-100 dark:bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-300 border-fuchsia-400 dark:border-fuchsia-500/30' },
};

export default function AccessoryRequestInbox({ token, moduleId }) {
  // RC-IA T-2: scope per portal. RnD (rnd-accessory-requests) = PANTAU request sample (read-only monitor);
  // Gudang/Aksesoris = inbox fulfillment penuh (allocate/deliver/reject).
  const isRndMonitor = moduleId === 'rnd-accessory-requests';
  const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState(isRndMonitor ? '' : 'submitted'); // RnD: semua status sample; lainnya: inbox
  const [filterType, setFilterType] = useState(isRndMonitor ? 'rnd_sample' : ''); // RnD: fokus rnd_sample; lainnya: semua tipe
  const [search, setSearch] = useState('');
  const [urgentOnly, setUrgentOnly] = useState(false);
  const [detail, setDetail] = useState(null);
  const [actionModal, setActionModal] = useState(null); // { id, type, notes }
  const [delId, setDelId] = useState(null);

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (filterStatus) qs.set('status', filterStatus);
      if (filterType)   qs.set('request_type', filterType);
      if (urgentOnly) qs.set('urgent_only', 'true');
      if (search) qs.set('search', search);
      const res = await fetch(`${API}/api/dewi/accessory-requests?${qs}`, { headers: h });
      const data = await res.json();
      setRequests(Array.isArray(data) ? data : []);
    } catch { toast.error('Gagal memuat data request'); }
    finally { setLoading(false); }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API}/api/dewi/accessory-requests/stats/summary`, { headers: h });
      if (res.ok) setStats(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchRequests(); }, [filterStatus, filterType, urgentOnly]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fetchStats(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAllocate = async () => {
    if (!actionModal) return;
    try {
      await fetch(`${API}/api/dewi/accessory-requests/${actionModal.id}/allocate`, {
        method: 'POST', headers: h, body: JSON.stringify({ notes: actionModal.notes || '' }),
      });
      toast.success('Request dialokasikan');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal mengalokasikan'); }
  };

  const handleDeliver = async () => {
    if (!actionModal) return;
    try {
      await fetch(`${API}/api/dewi/accessory-requests/${actionModal.id}/deliver`, {
        method: 'POST', headers: h, body: JSON.stringify({ notes: actionModal.notes || '' }),
      });
      toast.success('Request ditandai sudah diterima');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal update status'); }
  };

  const handleReject = async () => {
    if (!actionModal) return;
    if (!actionModal.notes?.trim()) {
      toast.error('Alasan reject wajib diisi');
      return;
    }
    try {
      await fetch(`${API}/api/dewi/accessory-requests/${actionModal.id}/reject`, {
        method: 'POST', headers: h, body: JSON.stringify({ reason: actionModal.notes }),
      });
      toast.success('Request ditolak');
      setActionModal(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal reject'); }
  };

  const handleDelete = async () => {
    try {
      await fetch(`${API}/api/dewi/accessory-requests/${delId}`, { method: 'DELETE', headers: h });
      toast.success('Request dihapus');
      setDelId(null);
      fetchRequests();
      fetchStats();
    } catch { toast.error('Gagal menghapus'); }
  };

  const filtered = useMemo(() => requests.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (r.request_code || '').toLowerCase().includes(q)
      || (r.style_code || '').toLowerCase().includes(q)
      || (r.style_name || '').toLowerCase().includes(q)
      || (r.requester_name || '').toLowerCase().includes(q);
  }), [requests, search]);

  const formatDate = (iso) => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="p-6 space-y-5" data-testid="accessory-request-inbox">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Inbox className="w-5 h-5 text-amber-700 dark:text-amber-500" /> {isRndMonitor ? 'Pantau Request Sample (RnD)' : 'Inbox Request Aksesoris'}
            <span className="px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-[11px] font-medium border border-emerald-400 dark:border-emerald-500/30">SSOT</span>
          </h1>
          <p className="text-sm text-foreground/50 mt-0.5">
            {isRndMonitor
              ? 'Pantau status permintaan sample RnD (read-only). Alokasi & pengiriman dilakukan oleh Gudang/Portal Aksesoris.'
              : <>Semua permintaan aksesoris (RnD sample, internal issuance, vendor add/replace) — backed by <span className="font-mono text-amber-300/80">dewi_accessory_requests</span></>}
          </p>
        </div>
      </div>

      {isRndMonitor && (
        <div className="flex items-start gap-2 rounded-lg border border-sky-400/40 bg-sky-50 dark:bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:text-sky-300" data-testid="acc-req-rnd-monitor-banner">
          <Eye className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>Mode <b>pantau (read-only)</b> — halaman yang sama dengan inbox Gudang/Aksesoris, difilter ke request <b>RnD Sample</b>. Aksi alokasi/kirim/tolak hanya tersedia di Portal Gudang/Aksesoris.</span>
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="acc-req-stats">
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50">Total</div>
            <div className="text-2xl font-bold text-foreground mt-1">{stats.total}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Inbox className="w-3 h-3" /> Menunggu</div>
            <div className="text-2xl font-bold text-amber-700 dark:text-amber-500 mt-1" data-testid="acc-req-stats-submitted">{stats.submitted}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><Package className="w-3 h-3" /> Disiapkan</div>
            <div className="text-2xl font-bold text-sky-500 mt-1">{stats.allocated}</div>
          </GlassCard>
          <GlassCard className="p-3">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Terkirim</div>
            <div className="text-2xl font-bold text-emerald-500 mt-1">{stats.delivered}</div>
          </GlassCard>
          <GlassCard className="p-3 border-red-400 dark:border-red-500/30">
            <div className="text-xs text-foreground/50 flex items-center gap-1"><AlertTriangle className="w-3 h-3 text-red-700 dark:text-red-500" /> Urgent</div>
            <div className="text-2xl font-bold text-red-700 dark:text-red-500 mt-1" data-testid="acc-req-stats-urgent">{stats.urgent_pending}</div>
          </GlassCard>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground/40" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && fetchRequests()}
            placeholder="Cari kode / style / requester / divisi..." className="pl-9"
            data-testid="acc-req-search-input" />
        </div>
        <div className="flex gap-2 flex-wrap">
          {[
            { v: '', label: 'Semua' },
            { v: 'submitted', label: 'Menunggu' },
            { v: 'allocated', label: 'Disiapkan' },
            { v: 'delivered', label: 'Terkirim' },
            { v: 'rejected', label: 'Ditolak' },
          ].map(opt => (
            <button key={opt.v} onClick={() => setFilterStatus(opt.v)}
              data-testid={`acc-req-filter-${opt.v || 'all'}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                filterStatus === opt.v
                  ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-500 border-amber-500/40'
                  : 'bg-foreground/5 text-foreground/50 border-foreground/10 hover:border-foreground/20'
              }`}>
              {opt.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs cursor-pointer" data-testid="acc-req-urgent-only-label">
          <input type="checkbox" checked={urgentOnly} onChange={e => setUrgentOnly(e.target.checked)}
            className="w-4 h-4 accent-red-500" data-testid="acc-req-urgent-only-checkbox" />
          <span className="text-foreground/70">Urgent saja</span>
        </label>
      </div>

      {/* P3 TD-009 — Request Type Filter (disembunyikan di mode pantau RnD yang terkunci ke rnd_sample) */}
      {!isRndMonitor && (
      <div className="flex flex-wrap gap-2 items-center" data-testid="acc-req-type-filter-row">
        <span className="text-xs text-foreground/40 uppercase tracking-wider">Tipe:</span>
        {[
          { v: '',                   label: 'Semua' },
          { v: 'rnd_sample',         label: 'RnD Sample' },
          { v: 'internal_issuance',  label: 'Internal' },
          { v: 'vendor_additional',  label: 'Vendor Add' },
          { v: 'vendor_replacement', label: 'Vendor Replace' },
        ].map(opt => (
          <button key={opt.v} onClick={() => setFilterType(opt.v)}
            data-testid={`acc-req-type-${opt.v || 'all'}`}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium border transition-all ${
              filterType === opt.v
                ? 'bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-300 border-violet-500/40'
                : 'bg-foreground/5 text-foreground/50 border-foreground/10 hover:border-foreground/20'
            }`}>
            {opt.label}
            {stats?.by_request_type && opt.v && (
              <span className="ml-1.5 opacity-60">({stats.by_request_type[opt.v] || 0})</span>
            )}
          </button>
        ))}
      </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-white/5">
              {Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  {[...Array(9)].map((__, j) => (
                    <td key={j} className="px-4 py-3"><Skeleton className="h-4" /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="Tidak ada request aksesoris"
          description="Request yang masuk akan muncul di sini. Ubah filter untuk melihat request dengan status berbeda."
          data-testid="inbox-empty"
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
          <table className="w-full text-sm">
            <thead className="bg-foreground/5 border-b border-foreground/10">
              <tr>
                {['Kode', 'Tipe', 'Style / Konteks', 'Items', 'Butuh Tgl', 'Status', 'Requester', 'Tgl Buat', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-foreground/50 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map(r => {
                const sc = STATUS_CONF[r.status] || STATUS_CONF.draft;
                const tc = TYPE_CONF[r.request_type] || TYPE_CONF.rnd_sample;
                const Icon = sc.Icon;
                return (
                  <tr key={r.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03] last:border-0">
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs font-semibold text-foreground">{r.request_code}</div>
                      {r.urgent && (
                        <span className="inline-flex items-center gap-1 text-[10px] mt-0.5 px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border border-red-400 dark:border-red-500/30">
                          <AlertTriangle className="w-2.5 h-2.5" /> URGENT
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center text-[11px] px-2 py-0.5 rounded-md border ${tc.cls}`}
                            data-testid={`acc-req-type-badge-${r.id}`}>
                        {tc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {/* Conditional context per request_type */}
                      {r.request_type === 'internal_issuance' ? (
                        <>
                          <div className="font-medium text-foreground text-sm">{r.divisi || '—'}</div>
                          <div className="text-xs text-foreground/40 truncate max-w-[180px]">{r.purpose || ''}</div>
                        </>
                      ) : r.request_type === 'vendor_additional' || r.request_type === 'vendor_replacement' ? (
                        <>
                          <div className="font-medium text-foreground text-sm font-mono">{r.po_number || '—'}</div>
                          <div className="text-xs text-foreground/40 truncate max-w-[180px]">Vendor: {r.vendor_id || '—'}</div>
                        </>
                      ) : (
                        <>
                          <div className="font-medium text-foreground text-sm">{r.style_code || '—'}</div>
                          <div className="text-xs text-foreground/40">{r.style_name || ''}</div>
                        </>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground/70 text-xs">{(r.items || []).length} item</td>
                    <td className="px-4 py-3 text-foreground/60 text-xs">{r.needed_by_date ? formatDate(r.needed_by_date) : '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${sc.cls}`}>
                        <Icon className="w-3 h-3" /> {sc.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground/60 text-xs">{r.requester_name || '—'}</td>
                    <td className="px-4 py-3 text-foreground/50 text-xs">{formatDate(r.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setDetail(r)}
                          className="h-7 w-7 p-0 text-foreground/60 hover:text-foreground"
                          data-testid={`acc-req-detail-${r.id}`}>
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        {/* RC-IA T-2: fulfillment actions hidden in RnD read-only monitor scope */}
                        {!isRndMonitor && (
                        <>
                        {r.status === 'submitted' && (
                          <>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: r.id, type: 'allocate', notes: '' })}
                              className="h-7 px-2 text-xs text-sky-600 dark:text-sky-400 hover:bg-sky-100 dark:bg-sky-500/10"
                              data-testid={`acc-req-allocate-${r.id}`}>
                              <Package className="w-3.5 h-3.5 mr-1" /> Siapkan
                            </Button>
                            <Button variant="ghost" size="sm"
                              onClick={() => setActionModal({ id: r.id, type: 'reject', notes: '' })}
                              className="h-7 px-2 text-xs text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                              data-testid={`acc-req-reject-${r.id}`}>
                              <XCircle className="w-3.5 h-3.5 mr-1" /> Tolak
                            </Button>
                          </>
                        )}
                        {r.status === 'allocated' && (
                          <Button variant="ghost" size="sm"
                            onClick={() => setActionModal({ id: r.id, type: 'deliver', notes: '' })}
                            className="h-7 px-2 text-xs text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:bg-emerald-500/10"
                            data-testid={`acc-req-deliver-${r.id}`}>
                            <Truck className="w-3.5 h-3.5 mr-1" /> Tandai Kirim
                          </Button>
                        )}
                        {(r.status === 'draft' || r.status === 'rejected' || r.status === 'cancelled') && (
                          <Button variant="ghost" size="sm" onClick={() => setDelId(r.id)}
                            className="h-7 w-7 p-0 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10"
                            data-testid={`acc-req-delete-${r.id}`}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                        </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* Detail Modal */}
      {detail && (
        <Modal onClose={() => setDetail(null)} title={`Detail: ${detail.request_code}`} size="lg">
          <div className="space-y-4">
            {/* Type badge + context info */}
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center text-xs px-2.5 py-1 rounded-md border ${(TYPE_CONF[detail.request_type] || TYPE_CONF.rnd_sample).cls}`}>
                {(TYPE_CONF[detail.request_type] || TYPE_CONF.rnd_sample).label}
              </span>
              <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border ${(STATUS_CONF[detail.status] || STATUS_CONF.draft).cls}`}>
                {(STATUS_CONF[detail.status] || STATUS_CONF.draft).label}
              </span>
              {detail.urgent && (
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-500 border border-red-400 dark:border-red-500/30">
                  <AlertTriangle className="w-3 h-3" /> URGENT
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              {/* Type-specific fields */}
              {detail.request_type === 'internal_issuance' ? (
                <>
                  <div>
                    <div className="text-xs text-foreground/50">Divisi</div>
                    <div className="font-medium">{detail.divisi || '—'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-foreground/50">Tujuan / Purpose</div>
                    <div className="text-sm">{detail.purpose || '—'}</div>
                  </div>
                </>
              ) : detail.request_type === 'vendor_additional' || detail.request_type === 'vendor_replacement' ? (
                <>
                  <div>
                    <div className="text-xs text-foreground/50">Vendor ID</div>
                    <div className="font-mono text-xs">{detail.vendor_id || '—'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-foreground/50">PO Number</div>
                    <div className="font-mono text-xs">{detail.po_number || '—'}</div>
                  </div>
                  {detail.original_shipment_id && (
                    <div>
                      <div className="text-xs text-foreground/50">Original Shipment</div>
                      <div className="font-mono text-xs">{detail.original_shipment_id}</div>
                    </div>
                  )}
                  {detail.child_shipment_number && (
                    <div>
                      <div className="text-xs text-foreground/50">Child Shipment</div>
                      <div className="font-mono text-xs text-emerald-600 dark:text-emerald-300">{detail.child_shipment_number}</div>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div>
                    <div className="text-xs text-foreground/50">Style</div>
                    <div className="font-medium">{detail.style_code} — {detail.style_name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-foreground/50">Sample Request ID</div>
                    <div className="font-mono text-xs">{detail.sample_request_id || '—'}</div>
                  </div>
                </>
              )}
              <div>
                <div className="text-xs text-foreground/50">Requester</div>
                <div>{detail.requester_name || '—'}</div>
              </div>
              <div>
                <div className="text-xs text-foreground/50">Butuh Tanggal</div>
                <div>{detail.needed_by_date ? formatDate(detail.needed_by_date) : '—'}</div>
              </div>
            </div>
            <div>
              <Label>Item Aksesoris</Label>
              <div className="mt-2 overflow-x-auto rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                <table className="w-full text-xs">
                  <thead className="bg-foreground/5">
                    <tr>
                      {['Kode', 'Nama', 'Qty', 'Unit', 'Catatan'].map(h => (
                        <th key={h} className="text-left px-3 py-2 text-foreground/50">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(detail.items || []).map((it, idx) => (
                      <tr key={idx} className="border-t border-foreground/5">
                        <td className="px-3 py-2 font-mono">{it.material_code || '—'}</td>
                        <td className="px-3 py-2">{it.material_name}</td>
                        <td className="px-3 py-2">{it.qty}</td>
                        <td className="px-3 py-2">{it.unit}</td>
                        <td className="px-3 py-2 text-foreground/60">{it.notes || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {detail.notes && (
              <div>
                <Label>Catatan</Label>
                <div className="mt-1 px-3 py-2 rounded-lg bg-foreground/5 text-sm text-foreground/80">{detail.notes}</div>
              </div>
            )}
            {detail.allocated_by && (
              <div className="text-xs text-foreground/50">
                Disiapkan oleh <strong>{detail.allocated_by}</strong> pada {formatDate(detail.allocated_at)}
              </div>
            )}
            {detail.delivered_by && (
              <div className="text-xs text-foreground/50">
                Dikirim oleh <strong>{detail.delivered_by}</strong> pada {formatDate(detail.delivered_at)}
              </div>
            )}
            {detail.rejection_reason && (
              <div className="px-3 py-2 rounded-lg bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-500/20 text-sm text-red-700 dark:text-red-400">
                Alasan reject: {detail.rejection_reason}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Action Modal */}
      {actionModal && (
        <Modal onClose={() => setActionModal(null)}
          title={
            actionModal.type === 'allocate' ? 'Siapkan Aksesoris' :
            actionModal.type === 'deliver' ? 'Tandai Sudah Diterima' :
            'Tolak Request'
          }>
          <p className="text-sm text-foreground/60 mb-3">
            {actionModal.type === 'reject'
              ? 'Tuliskan alasan penolakan:'
              : 'Catatan tambahan (opsional):'}
          </p>
          <textarea value={actionModal.notes}
            onChange={e => setActionModal(p => ({ ...p, notes: e.target.value }))}
            className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm text-foreground h-24 resize-none"
            placeholder={actionModal.type === 'reject' ? 'Stok kosong / di luar standar...' : 'Sudah disiapkan di rak A-3...'}
            data-testid="acc-req-action-notes" />
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="outline" onClick={() => setActionModal(null)}>Batal</Button>
            <Button
              onClick={actionModal.type === 'allocate' ? handleAllocate
                : actionModal.type === 'deliver' ? handleDeliver
                : handleReject}
              className={actionModal.type === 'reject' ? 'bg-red-600 hover:bg-red-700 text-foreground' : ''}
              data-testid="acc-req-confirm-action-btn">
              {actionModal.type === 'allocate' ? 'Siapkan'
                : actionModal.type === 'deliver' ? 'Tandai Kirim'
                : 'Tolak'}
            </Button>
          </div>
        </Modal>
      )}

      {!!delId && (
        <ConfirmDialog title="Hapus Request?"
          message="Request aksesoris akan dihapus permanen."
          onConfirm={handleDelete} onCancel={() => setDelId(null)} />
      )}
    </div>
  );
}
