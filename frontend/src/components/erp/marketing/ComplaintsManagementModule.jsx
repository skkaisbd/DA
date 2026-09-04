import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  AlertTriangle, Clock, CheckCircle2, XCircle,
  Search, RefreshCw, Loader2, ChevronRight, Bot, Cpu,
  MessageSquare, AlertCircle, TrendingDown, Inbox, RotateCcw
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
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import { ActiveAccountBar } from './ActiveAccountBar';
import { useMarketingAccounts } from '@/hooks/useMarketingAccounts';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

// ── Constants ──
const SLA_CONFIG = {
  on_time:  { label: 'On Time',   color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', dot: 'bg-emerald-500' },
  at_risk:  { label: 'At Risk',   color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',        dot: 'bg-amber-500' },
  overdue:  { label: 'Overdue',   color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',                dot: 'bg-red-500' },
  resolved: { label: 'Selesai',   color: 'bg-muted text-muted-foreground dark:bg-gray-800/50 dark:text-gray-400',            dot: 'bg-muted' },
};

const STATUS_CONFIG = {
  open:        { label: 'Terbuka',     color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',           icon: AlertTriangle },
  in_progress: { label: 'Diproses',   color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',       icon: Clock },
  resolved:    { label: 'Selesai',    color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300', icon: CheckCircle2 },
  closed:      { label: 'Ditutup',    color: 'bg-muted text-muted-foreground dark:bg-gray-800/50 dark:text-gray-400',        icon: XCircle },
};

const SEVERITY_CONFIG = {
  critical: { label: 'Kritis',   color: 'text-red-600',    bg: 'bg-red-600' },
  high:     { label: 'Tinggi',   color: 'text-orange-600', bg: 'bg-orange-500' },
  medium:   { label: 'Sedang',   color: 'text-amber-600',  bg: 'bg-amber-500' },
  low:      { label: 'Rendah',   color: 'text-muted-foreground',   bg: 'bg-muted' },
};

const CATEGORY_LABELS = {
  missing_item:         '📦 Produk Kurang',
  wrong_item:           '❌ Produk Salah',
  quality_defect:       '🔧 Cacat/Rusak',
  size_mismatch:        '📏 Ukuran Salah',
  late_delivery:        '⏰ Lambat',
  packaging_damage:     '🗡️ Kemasan Rusak',
  seller_unresponsive:  '🔇 Tidak Responsif',
  description_mismatch: '📝 Tidak Sesuai',
  other:                '❓ Lainnya',
};

const PLATFORM_ICONS = { shopee: '🛒', tiktok: '🎵', tokopedia: '🟢' };

function fmtDate(d) {
  if (!d) return '-';
  return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function SLABadge({ sla_status, sla_due_at }) {
  const cfg = SLA_CONFIG[sla_status] || SLA_CONFIG.on_time;
  const due = sla_due_at ? new Date(sla_due_at) : null;
  const hoursLeft = due ? (due - Date.now()) / 3600000 : null;
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
        {cfg.label}
      </span>
      {hoursLeft !== null && sla_status !== 'resolved' && (
        <span className="text-[11px] text-muted-foreground">
          {hoursLeft < 0
            ? `${Math.abs(Math.round(hoursLeft))}j overdue`
            : `${Math.round(hoursLeft)}j tersisa`
          }
        </span>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <Icon size={11} />{cfg.label}
    </span>
  );
}

// ── Complaint Detail Modal ──
function ComplaintDetailModal({ complaint, open, onClose, onUpdate, token }) {
  const { toast } = useToast();
  const [newStatus, setNewStatus] = useState('');
  const [noteText, setNoteText] = useState('');
  const [updating, setUpdating] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [detail, setDetail] = useState(null);

  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };

  useEffect(() => {
    if (open && complaint) {
      setDetail(complaint);
      setNewStatus('');
      setNoteText('');
    }
  }, [open, complaint]);

  const handleStatusUpdate = async () => {
    if (!newStatus) return;
    setUpdating(true);
    try {
      await axios.patch(`${API}/api/marketing/complaints/${detail.id}/status`,
        { status: newStatus, note: noteText || undefined },
        { headers: authH }
      );
      toast({ title: `Status diubah ke ${STATUS_CONFIG[newStatus]?.label}` });
      onUpdate();
      onClose();
    } catch (e) {
      toast({ title: 'Gagal update', variant: 'destructive' });
    } finally { setUpdating(false); }
  };

  const handleAddNote = async () => {
    if (!noteText.trim()) return;
    setUpdating(true);
    try {
      await axios.post(`${API}/api/marketing/complaints/${detail.id}/notes`,
        { text: noteText },
        { headers: authH }
      );
      toast({ title: 'Catatan ditambahkan' });
      // Reload complaint
      const res = await axios.get(`${API}/api/marketing/complaints/${detail.id}`, { headers: authH });
      setDetail(res.data);
      setNoteText('');
    } catch (e) {
      toast({ title: 'Gagal tambah catatan', variant: 'destructive' });
    } finally { setUpdating(false); }
  };

  const handleAiClassify = async () => {
    setAiLoading(true);
    try {
      const res = await axios.post(`${API}/api/marketing/complaints/${detail.id}/ai-classify`,
        {}, { headers: authH });
      const r = res.data.result;
      toast({ title: `AI: ${CATEGORY_LABELS[r.category] || r.category} (${((r.confidence||0)*100).toFixed(0)}% konfiden)` });
      setDetail(prev => ({
        ...prev,
        category: r.category,
        category_label: r.category,
        severity: r.severity,
        response_template: r.response_template || prev.response_template
      }));
    } catch (e) {
      toast({ title: 'AI gagal', description: e.response?.data?.detail, variant: 'destructive' });
    } finally { setAiLoading(false); }
  };

  if (!detail) return null;

  const nexts = { open: ['in_progress', 'resolved', 'closed'], in_progress: ['resolved', 'closed'], resolved: ['closed'], closed: [] };
  const nextStatuses = nexts[detail.status] || [];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-500" />
            {detail.complaint_number}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* Header Info */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <StatusBadge status={detail.status} />
                <SLABadge sla_status={detail.sla_status} sla_due_at={detail.sla_due_at} />
                <Badge variant="outline" className="text-xs">
                  {PLATFORM_ICONS[detail.platform]} {detail.platform}
                </Badge>
                {detail.severity && (
                  <span className={`text-xs font-semibold ${SEVERITY_CONFIG[detail.severity]?.color}`}>
                    {SEVERITY_CONFIG[detail.severity]?.label}
                  </span>
                )}
              </div>
              <p className="text-sm font-medium">{CATEGORY_LABELS[detail.category] || detail.category_label || detail.category}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{detail.account_name} • {fmtDate(detail.complaint_date)}</p>
            </div>
            <Button size="sm" variant="outline" className="flex-shrink-0" onClick={handleAiClassify} disabled={aiLoading}>
              {aiLoading ? <Loader2 size={12} className="mr-1 animate-spin" /> : <Bot size={12} className="mr-1" />}
              AI Classify
            </Button>
          </div>

          {/* Complaint Text */}
          <div className="rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-900/10 p-3">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1">💬 Keluhan Pelanggan:</p>
            <p className="text-sm">{detail.complaint_text}</p>
            <p className="text-xs text-muted-foreground mt-1">— {detail.customer_name} • {detail.product_name}</p>
          </div>

          {/* Response Template */}
          {detail.response_template && (
            <div className="rounded-lg border bg-muted/20 p-3">
              <p className="text-xs font-semibold text-muted-foreground mb-1">📝 Template Respons AI:</p>
              <p className="text-sm italic text-muted-foreground">{detail.response_template}</p>
            </div>
          )}

          {/* Orders */}
          {(detail.orders || []).length > 0 && (
            <div className="rounded-lg border bg-muted/20 p-3">
              <p className="text-xs font-semibold text-muted-foreground mb-2">Pesanan Terkait:</p>
              {detail.orders.map((o, i) => (
                <div key={i} className="flex justify-between text-xs py-0.5">
                  <span className="font-mono">{o.order_id}</span>
                  <span>{o.qty} pcs • {o.courier}</span>
                </div>
              ))}
            </div>
          )}

          {/* Notes Timeline */}
          {(detail.notes || []).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground">Catatan Internal:</p>
              {detail.notes.map((n, i) => (
                <div key={i} className="rounded-lg border-l-2 border-primary/30 bg-muted/20 pl-3 pr-2 py-2">
                  <p className="text-xs text-muted-foreground">{n.author} • {new Date(n.added_at).toLocaleString('id-ID', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })}</p>
                  <p className="text-sm mt-0.5">{n.text}</p>
                </div>
              ))}
            </div>
          )}

          {/* Add Note */}
          <div className="space-y-2">
            <Textarea
              placeholder="Tambah catatan internal..."
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              className="text-sm resize-none h-20"
              data-testid="note-textarea"
            />
            <Button size="sm" variant="outline" onClick={handleAddNote} disabled={!noteText.trim() || updating}>
              <MessageSquare size={12} className="mr-1" /> Tambah Catatan
            </Button>
          </div>

          {/* Update Status */}
          {nextStatuses.length > 0 && (
            <div className="border-t pt-4 space-y-3">
              <p className="text-sm font-medium">Update Status Komplain</p>
              <div className="flex items-center gap-3">
                <Select value={newStatus} onValueChange={setNewStatus}>
                  <SelectTrigger className="flex-1 h-9 text-sm">
                    <SelectValue placeholder="Pilih status baru..." />
                  </SelectTrigger>
                  <SelectContent>
                    {nextStatuses.map(s => (
                      <SelectItem key={s} value={s}>{STATUS_CONFIG[s]?.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={handleStatusUpdate} disabled={!newStatus || updating} className="flex-shrink-0">
                  {updating && <Loader2 size={12} className="mr-1 animate-spin" />}
                  Simpan
                </Button>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Component ──
export default function ComplaintsManagementModule({ token, onNavigate }) {
  const { toast } = useToast();
  const { activeAccount, setActiveAccount } = useActiveMarketingAccount();
  const { accounts: masterAccounts } = useMarketingAccounts(token);
  const [summary, setSummary] = useState(null);
  const [complaints, setComplaints] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [slaFilter, setSlaFilter] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [page, setPage] = useState(1);

  // UI
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const debounceRef = useRef(null);
  const authH = { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await axios.get(`${API}/api/marketing/complaints/summary`, { headers: authH });
      setSummary(res.data);
    } finally { setSummaryLoading(false); }
  }, [token]); // eslint-disable-line

  const fetchComplaints = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: 25 };
      if (statusFilter)         params.status     = statusFilter;
      if (slaFilter)            params.sla_status = slaFilter;
      if (catFilter)            params.category   = catFilter;
      if (platformFilter)       params.platform   = platformFilter;
      if (search)               params.search     = search;
      if (activeAccount?.id)    params.account_id = activeAccount.id;
      const res = await axios.get(`${API}/api/marketing/complaints`, { params, headers: authH });
      setComplaints(res.data.complaints || []);
      setPagination(res.data.pagination);
    } finally { setLoading(false); }
  }, [page, statusFilter, slaFilter, catFilter, platformFilter, search, activeAccount, token]); // eslint-disable-line

  useEffect(() => { fetchSummary(); }, [fetchSummary]);
  useEffect(() => { fetchComplaints(); }, [fetchComplaints]);

  const handleSearchChange = (e) => {
    setSearch(e.target.value);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setPage(1), 400);
  };

  // KPI Cards
  const kpis = [
    { label: 'Total Komplain',  value: summary?.total,        sub: `${summary?.by_status?.open || 0} terbuka`,                    color: 'text-indigo-600', bg: 'bg-indigo-50 dark:bg-indigo-900/20', icon: Inbox },
    { label: 'Overdue (SLA)',   value: summary?.overdue,       sub: `${summary?.at_risk || 0} at risk`,                           color: 'text-red-600',    bg: 'bg-red-50 dark:bg-red-900/20',     icon: AlertCircle },
    { label: 'Resolve Rate',    value: `${summary?.resolve_rate || 0}%`, sub: `${summary?.resolved || 0} terselesaikan`,           color: 'text-emerald-600',bg: 'bg-emerald-50 dark:bg-emerald-900/20', icon: CheckCircle2 },
    { label: 'Sedang Diproses', value: summary?.by_status?.in_progress || 0, sub: `${summary?.by_sla?.at_risk || 0} perlu segera`, color: 'text-amber-600',  bg: 'bg-amber-50 dark:bg-amber-900/20', icon: Clock },
  ];

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="complaints-dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Manajemen Komplain</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Keluhan pelanggan dengan SLA tracking dan klasifikasi AI</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { fetchSummary(); fetchComplaints(); }}>
          <RefreshCw size={13} className="mr-1" /> Refresh
        </Button>
      </div>

      {/* RC-FLOW-UX — onward CTA: komplain → retur/refund (Alur 7→8) */}
      <OnwardCTA
        onNavigate={onNavigate}
        title="Tindak Lanjut Komplain"
        className="mb-5"
        actions={[
          { module: 'marketing-returns', label: 'Proses Retur & Refund', icon: RotateCcw, primary: true, hint: 'Komplain berujung retur/refund' },
        ]}
      />

      {/* Active Account Bar */}
      <div className="mb-4">
        <ActiveAccountBar accounts={masterAccounts} activeAccount={activeAccount} onAccountChange={acc => { setActiveAccount(acc); setPage(1); }} hint="Filter komplain by akun:" />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {kpis.map(k => (
          <div key={k.label} className={`rounded-xl border p-4 ${k.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              <k.icon size={15} className={k.color} />
            </div>
            <p className={`text-3xl font-bold tabular-nums ${k.color}`}>{summaryLoading ? '...' : (k.value ?? '0')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{summaryLoading ? '' : k.sub}</p>
          </div>
        ))}
      </div>

      {/* SLA Status Bar */}
      {summary?.by_sla && (
        <div className="flex flex-wrap gap-2 mb-5">
          {Object.entries(SLA_CONFIG).map(([key, cfg]) => {
            const count = summary.by_sla[key] || 0;
            if (!count) return null;
            return (
              <button
                key={key}
                onClick={() => { setSlaFilter(slaFilter === key ? '' : key); setPage(1); }}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                  slaFilter === key ? 'border-primary ring-1 ring-primary' : 'border-border hover:border-primary/50'
                } ${cfg.color}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                {cfg.label} <span className="font-bold">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Cari nomor, keluhan, produk..."
                className="pl-9 h-9 text-sm"
                value={search}
                onChange={handleSearchChange}
                data-testid="search-complaints"
              />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Select value={statusFilter || 'all'} onValueChange={v => { setStatusFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[130px] h-9 text-xs">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Status</SelectItem>
                  {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={catFilter || 'all'} onValueChange={v => { setCatFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[150px] h-9 text-xs">
                  <SelectValue placeholder="Kategori" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Kategori</SelectItem>
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={platformFilter || 'all'} onValueChange={v => { setPlatformFilter(v === 'all' ? '' : v); setPage(1); }}>
                <SelectTrigger className="w-[130px] h-9 text-xs">
                  <SelectValue placeholder="Platform" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Platform</SelectItem>
                  <SelectItem value="shopee">🛒 Shopee</SelectItem>
                  <SelectItem value="tiktok">🎵 TikTok</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 className="animate-spin text-muted-foreground" size={24} />
            </div>
          ) : complaints.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
              <CheckCircle2 size={32} className="opacity-30 mb-2" />
              <p className="text-sm">Tidak ada komplain ditemukan</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    {['No. Komplain', 'Platform', 'Kategori', 'Pelanggan / Produk', 'Tanggal', 'Status', 'SLA', ''].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {complaints.map(c => (
                    <tr key={c.id}
                      className="hover:bg-muted/30 transition-colors group"
                      data-testid={`complaint-row-${c.id}`}
                    >
                      <td className="px-3 py-2 font-mono text-xs font-semibold">{c.complaint_number}</td>
                      <td className="px-3 py-2 text-xs">
                        {PLATFORM_ICONS[c.platform]} <span className="capitalize">{c.platform}</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs">{CATEGORY_LABELS[c.category] || c.category}</span>
                      </td>
                      <td className="px-3 py-2">
                        <p className="font-medium text-xs">{c.customer_name}</p>
                        <p className="text-xs text-muted-foreground truncate max-w-[160px]" title={c.product_name}>{c.product_name}</p>
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {c.complaint_date ? new Date(c.complaint_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: '2-digit' }) : '-'}
                      </td>
                      <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                      <td className="px-3 py-2">
                        <SLABadge sla_status={c.sla_status} sla_due_at={c.sla_due_at} />
                      </td>
                      <td className="px-3 py-2">
                        <Button size="sm" variant="ghost" className="h-7 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => setSelectedComplaint(c)}
                          data-testid={`btn-complaint-detail-${c.id}`}
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
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <span className="text-xs text-muted-foreground">{pagination.total} komplain</span>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" className="h-7" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Sebelumnya</Button>
                <span className="text-xs">{page} / {pagination.total_pages}</span>
                <Button size="sm" variant="outline" className="h-7" disabled={page >= pagination.total_pages} onClick={() => setPage(p => p + 1)}>Berikutnya</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detail Modal */}
      <ComplaintDetailModal
        complaint={selectedComplaint}
        open={!!selectedComplaint}
        onClose={() => setSelectedComplaint(null)}
        onUpdate={() => { fetchComplaints(); fetchSummary(); }}
        token={token}
      />
    </div>
  );
}
