/**
 * CMTLifecycleModule — Vendor-centric Cross-Module Dashboard for CMT (Cut-Make-Trim)
 * Phase 29 — Cross-Module Vendor View
 *
 * Two views:
 *  A) Vendor List — picker with KPIs per vendor + system summary strip
 *  B) Vendor Detail — 6 tabs: Overview, Jobs, Material Issued, Receipts, Payments, Performance
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Building2, RefreshCw, Search, ChevronRight, ArrowLeft, Package, Truck,
  TrendingUp, AlertTriangle, CheckCircle2, Clock, DollarSign, Banknote,
  BarChart3, Activity, Calendar, MapPin, Phone, FileText, Briefcase,
  Users, Layers, ShieldCheck, Target, Zap, AlertCircle, FileSearch,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader } from './moduleAtoms';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ───────────────────────────────────────────────────────────────
const fmtRp = (v) => (v === null || v === undefined || v === '') ? '—' : formatRupiah(v);
function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return v; }
}
function fmtDateTime(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return v; }
}
function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  return `${Number(v).toFixed(1)}%`;
}

const STATUS_META = {
  active:    { label: 'Aktif',     color: 'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/15 border-green-400 dark:border-green-400/30' },
  inactive:  { label: 'Nonaktif',  color: 'text-muted-foreground bg-muted dark:bg-slate-500/15 border-border dark:border-slate-400/30' },
  assigned:  { label: 'Ditugaskan',     color: 'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/15 border-blue-400 dark:border-blue-400/30' },
  in_sewing: { label: 'Sedang Dijahit', color: 'text-violet-600 dark:text-violet-300 bg-violet-100 dark:bg-violet-500/15 border-violet-400 dark:border-violet-400/30' },
  sewing:    { label: 'Sedang Dijahit', color: 'text-violet-600 dark:text-violet-300 bg-violet-100 dark:bg-violet-500/15 border-violet-400 dark:border-violet-400/30' },
  in_progress: { label: 'Berjalan',     color: 'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/15 border-blue-400 dark:border-blue-400/30' },
  qc:        { label: 'QC',         color: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/15 border-amber-400 dark:border-amber-400/30' },
  completed: { label: 'Selesai',    color: 'text-emerald-600 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-500/15 border-emerald-400 dark:border-emerald-400/30' },
  cancelled: { label: 'Dibatalkan', color: 'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/15 border-red-400 dark:border-red-400/30' },
  draft:     { label: 'Draft',      color: 'text-foreground/70 bg-muted dark:bg-slate-500/15 border-border dark:border-slate-400/30' },
  approved:  { label: 'Disetujui',  color: 'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/15 border-blue-400 dark:border-blue-400/30' },
  paid:      { label: 'Dibayar',    color: 'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/15 border-green-400 dark:border-green-400/30' },
  submitted: { label: 'Submit',     color: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/15 border-amber-400 dark:border-amber-400/30' },
  pending_approval: { label: 'Menunggu Approval', color: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/15 border-amber-400 dark:border-amber-400/30' },
  in_review: { label: 'Direview',   color: 'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/15 border-blue-400 dark:border-blue-400/30' },
};

function StatusBadge({ status, fallbackLabel }) {
  const m = STATUS_META[status] || { label: fallbackLabel || status || '—', color: 'text-foreground/70 bg-foreground/10 border-foreground/20' };
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.color}`}>
      {m.label}
    </span>
  );
}

// ─── KPI Cells ─────────────────────────────────────────────────────────────
function KPICell({ label, value, icon: Icon, tone = 'slate', sub }) {
  const toneMap = {
    slate:   'text-foreground/70',
    green:   'text-green-600 dark:text-green-300',
    amber:   'text-amber-600 dark:text-amber-300',
    red:     'text-red-600 dark:text-red-300',
    violet:  'text-violet-600 dark:text-violet-300',
    blue:    'text-blue-600 dark:text-blue-300',
    emerald: 'text-emerald-600 dark:text-emerald-300',
    cyan:    'text-cyan-600 dark:text-cyan-300',
  };
  return (
    <div className="p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] transition">
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`text-lg font-bold ${toneMap[tone]} leading-tight`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground/60 mt-0.5">{sub}</div>}
    </div>
  );
}

function MiniProgressBar({ pct, gradient = 'from-violet-500 to-green-500' }) {
  const safe = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="h-1.5 rounded-full bg-foreground/10 overflow-hidden">
      <motion.div
        className={`h-full bg-gradient-to-r ${gradient}`}
        initial={{ width: 0 }}
        animate={{ width: `${safe}%` }}
        transition={{ duration: 0.5 }}
      />
    </div>
  );
}

// ─── Vendor List View ─────────────────────────────────────────────────────
function VendorListView({ headers, onPick }) {
  const [vendors, setVendors] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${API}/api/dewi/cmt/lifecycle?status=${statusFilter}`, { headers }),
        fetch(`${API}/api/dewi/cmt/lifecycle/summary`, { headers }),
      ]);
      if (r1.ok) { const d = await r1.json(); setVendors(d.items || []); }
      if (r2.ok) setSummary(await r2.json());
    } catch (e) {
      toast.error('Gagal memuat data: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [headers, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (!search) return vendors;
    const q = search.toLowerCase();
    return vendors.filter(v =>
      (v.name || '').toLowerCase().includes(q) ||
      (v.code || '').toLowerCase().includes(q) ||
      (v.address || '').toLowerCase().includes(q)
    );
  }, [vendors, search]);

  const s = summary || {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="CMT Lifecycle Dashboard"
        subtitle="Vendor-centric cross-module view — Jobs, Material, Progress, Receipts, Payments dalam 1 layar per vendor CMT."
        icon={Briefcase}
        actions={
          <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="cmt-lc-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        }
      />

      {/* System-wide Summary */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <KPICell label="Total Vendor" value={fmtNum(s.total_vendors)} icon={Building2} tone="slate" sub={`${s.active_vendors} aktif`} />
          <KPICell label="Active Jobs" value={fmtNum(s.total_active_jobs)} icon={Activity} tone="violet" />
          <KPICell label="Pcs in Process" value={fmtNum(s.total_pcs_in_process)} icon={Package} tone="blue" />
          <KPICell label="Overdue Jobs" value={fmtNum(s.total_overdue_jobs)} icon={AlertCircle} tone="red" />
          <KPICell label="Pcs 30 Hari" value={fmtNum(s.pcs_completed_30d)} icon={TrendingUp} tone="green" />
          <KPICell label="Receipts Pending" value={fmtNum(s.receipts_pending_qc)} icon={ShieldCheck} tone="amber" />
          <KPICell label="Material Dispatched" value={fmtNum(s.active_dispatches)} icon={Truck} tone="cyan" />
          <KPICell label="Jobs Selesai" value={fmtNum(s.total_completed_jobs)} icon={CheckCircle2} tone="emerald" />
          <KPICell label="Total Ditagih" value={fmtRp(s.total_billed)} icon={FileText} tone="blue" />
          <KPICell label="Total Dibayar" value={fmtRp(s.total_paid)} icon={Banknote} tone="green" />
          <KPICell label="Outstanding" value={fmtRp(s.total_outstanding)} icon={DollarSign} tone="red" />
          <KPICell label="Pending Payments" value={`${fmtNum(s.pending_payments_count)} (${fmtRp(s.pending_payments_amount)})`} icon={Clock} tone="amber" />
        </div>
      )}

      {/* Filter & Search */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center bg-foreground/5 border border-foreground/10 rounded-md px-3 min-w-[260px] flex-1">
            <Search className="w-4 h-4 text-muted-foreground/60" />
            <Input
              placeholder="Cari nama vendor / kode / alamat..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-0 focus-visible:ring-0 text-sm"
              data-testid="cmt-lc-search"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-44 bg-foreground/5 border-foreground/10 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              <SelectItem value="active">Hanya Aktif</SelectItem>
              <SelectItem value="inactive">Nonaktif</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Vendor Cards Grid */}
        {loading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground">Memuat vendors...</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-muted-foreground/60 gap-2">
            <Briefcase className="w-12 h-12 opacity-30" />
            <p className="text-sm">Tidak ada vendor CMT ditemukan</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map(v => (
              <VendorCard key={v.partner_id} vendor={v} onClick={() => onPick(v)} />
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function VendorCard({ vendor, onClick }) {
  const completedPct = vendor.jobs_total > 0
    ? Math.round((vendor.jobs_completed / vendor.jobs_total) * 100)
    : 0;
  return (
    <motion.button
      data-testid={`cmt-lc-vendor-${vendor.partner_id}`}
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      onClick={onClick}
      className="text-left p-4 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:border-violet-400 dark:border-violet-400/30 hover:bg-foreground/[0.06] transition group"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-violet-600 dark:text-violet-300">{vendor.code}</span>
            <StatusBadge status={vendor.status} />
          </div>
          <h4 className="text-sm font-bold text-foreground mt-0.5 truncate" title={vendor.name}>{vendor.name}</h4>
          <p className="text-[10px] text-muted-foreground/60 mt-0.5 flex items-center gap-1">
            <MapPin className="w-3 h-3" /> <span className="truncate">{vendor.address || '—'}</span>
          </p>
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground/50 group-hover:text-violet-600 dark:text-violet-400 transition" />
      </div>

      {/* Mini KPIs */}
      <div className="grid grid-cols-3 gap-2 mt-3">
        <div className="text-center p-1.5 rounded bg-violet-100 dark:bg-violet-500/10 border border-violet-400/15">
          <div className="text-[10px] text-violet-300/80 uppercase tracking-wider">Active</div>
          <div className="text-base font-bold text-violet-600 dark:text-violet-300">{fmtNum(vendor.jobs_active)}</div>
        </div>
        <div className="text-center p-1.5 rounded bg-blue-100 dark:bg-blue-500/10 border border-blue-400/15">
          <div className="text-[10px] text-blue-300/80 uppercase tracking-wider">Pcs</div>
          <div className="text-base font-bold text-blue-600 dark:text-blue-300">{fmtNum(vendor.pcs_in_process)}</div>
        </div>
        <div className="text-center p-1.5 rounded bg-red-100 dark:bg-red-500/10 border border-red-400/15">
          <div className="text-[10px] text-red-300/80 uppercase tracking-wider">Overdue</div>
          <div className="text-base font-bold text-red-600 dark:text-red-300">{fmtNum(vendor.jobs_overdue)}</div>
        </div>
      </div>

      {/* Performance bar */}
      <div className="mt-3">
        <div className="flex items-center justify-between text-[10px] mb-1">
          <span className="text-muted-foreground">Rate per pcs</span>
          <span className="text-emerald-600 dark:text-emerald-300 font-semibold">{fmtRp(vendor.rate_per_pcs)}</span>
        </div>
        <div className="flex items-center justify-between text-[10px] mt-1">
          <span className="text-muted-foreground">Outstanding</span>
          <span className={vendor.outstanding > 0 ? 'text-amber-600 dark:text-amber-300' : 'text-green-600 dark:text-green-300'}>{fmtRp(vendor.outstanding)}</span>
        </div>
        {vendor.on_time_pct !== null && (
          <div className="flex items-center justify-between text-[10px] mt-1">
            <span className="text-muted-foreground">On-Time</span>
            <span className="text-violet-600 dark:text-violet-300 font-semibold">{fmtPct(vendor.on_time_pct)}</span>
          </div>
        )}
      </div>
    </motion.button>
  );
}

// ─── Vendor Detail View ────────────────────────────────────────────────────
function VendorDetailView({ vendorId, headers, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('overview');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/dewi/cmt/lifecycle/${vendorId}`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat detail vendor');
        onBack();
        return;
      }
      setData(await r.json());
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [vendorId, headers, onBack]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data) {
    return (
      <GlassCard className="p-12 text-center text-muted-foreground">
        <RefreshCw className="w-8 h-8 mx-auto mb-3 animate-spin text-violet-600 dark:text-violet-400" />
        Memuat detail vendor CMT...
      </GlassCard>
    );
  }

  const k = data.kpis || {};
  const partner = data.partner || {};

  const tabs = [
    { value: 'overview',  label: 'Overview',           icon: BarChart3 },
    { value: 'jobs',      label: 'Jobs',               icon: Briefcase },
    { value: 'material',  label: 'Material Issued',    icon: Truck },
    { value: 'progress',  label: 'Progress',           icon: Activity },
    { value: 'receipts',  label: 'Receipts (QC)',      icon: ShieldCheck },
    { value: 'payments',  label: 'Payments',           icon: Banknote },
    { value: 'performance', label: 'Performance',      icon: TrendingUp },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <GlassCard className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack} data-testid="cmt-lc-back" className="text-foreground/70 hover:text-foreground">
              <ArrowLeft className="w-4 h-4 mr-1" /> Kembali ke Daftar
            </Button>
            <div className="border-l border-foreground/10 pl-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-violet-600 dark:text-violet-300">{partner.code}</span>
                <h2 className="text-lg font-bold text-foreground">{partner.name}</h2>
                <StatusBadge status={partner.status} />
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-3 flex-wrap">
                {partner.address && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {partner.address}</span>}
                {(partner.contact_phone || partner.phone) && (
                  <span className="flex items-center gap-1"><Phone className="w-3 h-3" /> {partner.contact_phone || partner.phone}</span>
                )}
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-300">
                  <DollarSign className="w-3 h-3" /> {fmtRp(k.rate_per_pcs)} per pcs
                </span>
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="cmt-lc-detail-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </GlassCard>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICell label="Active Jobs"        value={fmtNum(k.jobs_active)}     icon={Activity}    tone="violet" />
        <KPICell label="Pcs in Process"     value={fmtNum(k.pcs_in_process)}  icon={Package}     tone="blue" />
        <KPICell label="Overdue"            value={fmtNum(k.jobs_overdue)}    icon={AlertCircle} tone="red" />
        <KPICell label="Completed YTD"      value={fmtNum(k.pcs_completed_ytd)} icon={CheckCircle2} tone="green" />
        <KPICell label="Pcs Last 30d"       value={fmtNum(k.pcs_last_30)}     icon={TrendingUp}  tone="emerald" />
        <KPICell label="On-Time Rate"       value={fmtPct(k.on_time_pct)}     icon={Target}      tone="violet" sub={`${k.on_time_completed}/${k.on_time_completed + k.late_completed}`} />
        <KPICell label="Defect Rate"        value={fmtPct(k.defect_rate_pct)} icon={ShieldCheck} tone="amber" />
        <KPICell label="Material Dispatched" value={fmtNum(k.dispatches_active)} icon={Truck}    tone="cyan" sub={`${k.dispatches_total} total`} />
        <KPICell label="Receipts Pending"   value={fmtNum(k.receipts_pending_qc)} icon={FileSearch} tone="amber" sub={`${k.receipts_total} total`} />
        <KPICell label="Total Billed"       value={fmtRp(k.total_billed)}     icon={FileText}    tone="blue" />
        <KPICell label="Paid"               value={fmtRp(k.total_paid)}       icon={Banknote}    tone="green" />
        <KPICell label="Outstanding"        value={fmtRp(k.outstanding)}      icon={DollarSign}  tone="red" sub={`${k.pending_payments_count} pending`} />
      </div>

      {/* Tabs */}
      <GlassCard className="p-4">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-foreground/5 grid grid-cols-4 md:grid-cols-7 gap-1 h-auto p-1">
            {tabs.map(t => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                data-testid={`cmt-lc-tab-${t.value}`}
                className="data-[state=active]:bg-violet-600 data-[state=active]:text-foreground text-xs flex items-center gap-1.5"
              >
                <t.icon className="w-3.5 h-3.5" /> {t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <div className="mt-5">
            <AnimatePresence mode="wait">
              <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                {tab === 'overview' && <OverviewTab data={data} />}
                {tab === 'jobs' && <JobsTab data={data} />}
                {tab === 'material' && <MaterialTab data={data} />}
                {tab === 'progress' && <ProgressTab data={data} />}
                {tab === 'receipts' && <ReceiptsTab data={data} />}
                {tab === 'payments' && <PaymentsTab data={data} />}
                {tab === 'performance' && <PerformanceTab data={data} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </Tabs>
      </GlassCard>
    </div>
  );
}

// ─── Tab Panels ────────────────────────────────────────────────────────────
function OverviewTab({ data }) {
  const overdue = data.overdue_jobs || [];
  const recentJobs = (data.jobs || []).slice(0, 5);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-300" /> Overdue Jobs ({overdue.length})
        </h4>
        {overdue.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground/60 gap-1">
            <CheckCircle2 className="w-8 h-8 opacity-30" />
            <p className="text-xs">Tidak ada job yang overdue 🎉</p>
          </div>
        ) : (
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {overdue.slice(0, 10).map(j => (
              <div key={j.id} className="p-2 rounded bg-red-100 dark:bg-red-500/10 border border-red-300 dark:border-red-400/20 flex items-center justify-between">
                <div>
                  <span className="text-xs font-mono text-red-600 dark:text-red-300">{j.job_code}</span>
                  <div className="text-[10px] text-muted-foreground">{j.product_name || '—'}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-red-600 dark:text-red-300 font-bold">{j.late_days || 0} hari telat</div>
                  <div className="text-[10px] text-muted-foreground/60">Deadline: {fmtDate(j.deadline_date)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Job Terbaru
        </h4>
        {recentJobs.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 italic">Belum ada job.</p>
        ) : (
          <div className="space-y-1.5">
            {recentJobs.map(j => (
              <div key={j.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08] flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-violet-600 dark:text-violet-300">{j.job_code}</span>
                    <StatusBadge status={j.status} />
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{j.product_name || '—'} · {fmtNum(j.qty_total || j.qty)} pcs</div>
                </div>
                <div className="text-[10px] text-muted-foreground/60">{fmtDate(j.deadline_date)}</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function JobsTab({ data }) {
  const jobs = data.jobs || [];
  const { page, setPage, totalPages, total, paged } = useClientPagination(jobs, 10);
  if (jobs.length === 0) {
    return <p className="text-xs text-muted-foreground/60 italic text-center py-8">Belum ada job untuk vendor ini.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b border-foreground/10">
            <th className="text-left py-2 px-2">Job Code</th>
            <th className="text-left py-2 px-2">Produk</th>
            <th className="text-right py-2 px-2">Qty</th>
            <th className="text-right py-2 px-2">Processed</th>
            <th className="text-right py-2 px-2">Rate</th>
            <th className="text-left py-2 px-2">Deadline</th>
            <th className="text-left py-2 px-2">Status</th>
            <th className="text-left py-2 px-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {paged.map(j => {
            const qty = j.qty_total || j.qty || 0;
            const processed = j.qty_processed || j.qty_received || 0;
            const pct = qty > 0 ? Math.round((processed / qty) * 100) : 0;
            return (
              <tr key={j.id} className={`border-b border-foreground/5 hover:bg-foreground/[0.03] ${j.is_overdue ? 'bg-red-100 dark:bg-red-500/5' : ''}`}>
                <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{j.job_code}</td>
                <td className="py-2 px-2 text-foreground">{j.product_name || '—'}</td>
                <td className="py-2 px-2 text-right text-foreground">{fmtNum(qty)}</td>
                <td className="py-2 px-2 text-right">
                  <div className="flex items-center gap-2 justify-end">
                    <div className="w-16">
                      <MiniProgressBar pct={pct} />
                    </div>
                    <span className="text-blue-600 dark:text-blue-300 w-10 text-right">{fmtNum(processed)}</span>
                  </div>
                </td>
                <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300">{fmtRp(j.rate_per_pcs)}</td>
                <td className="py-2 px-2">
                  <span className={j.is_overdue ? 'text-red-600 dark:text-red-300 font-bold' : ''}>{fmtDate(j.deadline_date)}</span>
                  {j.is_overdue && <div className="text-[10px] text-red-600 dark:text-red-300">{j.late_days} hari telat</div>}
                  {!j.is_overdue && j.days_to_deadline !== undefined && (
                    <div className="text-[10px] text-muted-foreground/60">{j.days_to_deadline} hari lagi</div>
                  )}
                </td>
                <td className="py-2 px-2"><StatusBadge status={j.status} /></td>
                <td className="py-2 px-2 text-muted-foreground italic truncate max-w-[180px]" title={j.notes}>{j.notes || '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
    </div>
  );
}

function MaterialTab({ data }) {
  const dispatches = data.dispatches || [];
  const dos = data.delivery_orders || [];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Truck className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> WMS Dispatches ({dispatches.length})
        </h4>
        {dispatches.length === 0 ? <p className="text-xs text-muted-foreground/60 italic">Belum ada dispatch.</p> : (
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {dispatches.map(d => (
              <div key={d.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-cyan-600 dark:text-cyan-300">{d.dispatch_number || d.id.slice(0, 8)}</span>
                  <StatusBadge status={d.status} />
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">{fmtDateTime(d.created_at)}</div>
                <div className="text-[10px] text-foreground/70 mt-0.5">{(d.items || []).length} jenis material</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <FileText className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Delivery Orders ({dos.length})
        </h4>
        {dos.length === 0 ? <p className="text-xs text-muted-foreground/60 italic">Belum ada DO.</p> : (
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {dos.map(d => (
              <div key={d.id} className="p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-violet-600 dark:text-violet-300">{d.do_number || d.do_code || d.id.slice(0, 8)}</span>
                  <StatusBadge status={d.status} />
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">{fmtDateTime(d.created_at)}</div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function ProgressTab({ data }) {
  const progress = data.progress_reports || [];
  if (progress.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-muted-foreground/60 gap-2">
        <Activity className="w-10 h-10 opacity-30" />
        <p className="text-sm">Belum ada laporan progress harian.</p>
      </div>
    );
  }
  return (
    <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
      {progress.map(p => (
        <div key={p.id} className="p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] border-l-4 border-l-violet-400/40">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <div className="text-xs font-mono text-violet-600 dark:text-violet-300">{fmtDate(p.date)}</div>
              <div className="text-sm text-foreground mt-0.5">{p.job_code || '—'} · {p.process_step || ''}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-emerald-600 dark:text-emerald-300">{fmtNum(p.qty_done || p.output_qty || 0)} pcs</div>
              {p.defect_qty > 0 && <div className="text-[10px] text-red-600 dark:text-red-300">{fmtNum(p.defect_qty)} defect</div>}
            </div>
          </div>
          {p.notes && <p className="text-xs text-muted-foreground italic mt-1">{p.notes}</p>}
        </div>
      ))}
    </div>
  );
}

function ReceiptsTab({ data }) {
  const receipts = data.receipts || [];
  if (receipts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-muted-foreground/60 gap-2">
        <ShieldCheck className="w-10 h-10 opacity-30" />
        <p className="text-sm">Belum ada receipt dari vendor.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b border-foreground/10">
            <th className="text-left py-2 px-2">Receipt #</th>
            <th className="text-left py-2 px-2">Job</th>
            <th className="text-left py-2 px-2">Tanggal</th>
            <th className="text-right py-2 px-2">Qty Diterima</th>
            <th className="text-right py-2 px-2">Defect</th>
            <th className="text-left py-2 px-2">Status</th>
            <th className="text-left py-2 px-2">QC Notes</th>
          </tr>
        </thead>
        <tbody>
          {receipts.map(r => (
            <tr key={r.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
              <td className="py-2 px-2 font-mono text-cyan-600 dark:text-cyan-300">{r.receipt_number || r.id.slice(0, 8)}</td>
              <td className="py-2 px-2 text-violet-600 dark:text-violet-300">{r.job_code || '—'}</td>
              <td className="py-2 px-2 text-foreground/70">{fmtDate(r.receipt_date || r.created_at)}</td>
              <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300">{fmtNum(r.qty_received || r.qty || 0)}</td>
              <td className="py-2 px-2 text-right text-red-600 dark:text-red-300">{fmtNum(r.defect_qty || 0)}</td>
              <td className="py-2 px-2"><StatusBadge status={r.status} /></td>
              <td className="py-2 px-2 text-muted-foreground italic truncate max-w-[180px]" title={r.qc_notes || r.notes}>{r.qc_notes || r.notes || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PaymentsTab({ data }) {
  const payments = data.payments || [];
  if (payments.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-muted-foreground/60 gap-2">
        <Banknote className="w-10 h-10 opacity-30" />
        <p className="text-sm">Belum ada payment record.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b border-foreground/10">
            <th className="text-left py-2 px-2">Payment #</th>
            <th className="text-left py-2 px-2">Periode</th>
            <th className="text-right py-2 px-2">Qty</th>
            <th className="text-right py-2 px-2">Gross</th>
            <th className="text-right py-2 px-2">Penalty</th>
            <th className="text-right py-2 px-2">Net Amount</th>
            <th className="text-left py-2 px-2">Status</th>
            <th className="text-left py-2 px-2">Tgl Bayar</th>
          </tr>
        </thead>
        <tbody>
          {payments.map(p => (
            <tr key={p.id} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
              <td className="py-2 px-2 font-mono text-emerald-600 dark:text-emerald-300">{p.payment_number || p.id.slice(0, 8)}</td>
              <td className="py-2 px-2 text-foreground/70">{p.period || `${fmtDate(p.period_start)} - ${fmtDate(p.period_end)}`}</td>
              <td className="py-2 px-2 text-right text-foreground">{fmtNum(p.total_qty || 0)}</td>
              <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtRp(p.gross_amount)}</td>
              <td className="py-2 px-2 text-right text-red-600 dark:text-red-300">{fmtRp(p.penalty_amount)}</td>
              <td className="py-2 px-2 text-right text-emerald-600 dark:text-emerald-300 font-bold">{fmtRp(p.net_amount)}</td>
              <td className="py-2 px-2"><StatusBadge status={p.status} /></td>
              <td className="py-2 px-2 text-muted-foreground">{p.paid_at ? fmtDate(p.paid_at) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PerformanceTab({ data }) {
  const k = data.kpis || {};
  const series = data.monthly_series || [];
  const maxPcs = Math.max(1, ...series.map(s => s.pcs));
  return (
    <div className="space-y-4">
      {/* Score Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <ScoreCard label="On-Time Delivery" value={k.on_time_pct} unit="%" 
                   icon={Target}
                   target={90}
                   tone={k.on_time_pct >= 90 ? 'green' : k.on_time_pct >= 75 ? 'amber' : 'red'} />
        <ScoreCard label="Defect Rate" value={k.defect_rate_pct} unit="%" 
                   icon={ShieldCheck}
                   target={3}
                   reverse
                   tone={(k.defect_rate_pct || 0) <= 3 ? 'green' : (k.defect_rate_pct || 0) <= 5 ? 'amber' : 'red'} />
        <ScoreCard label="Throughput 30d" value={k.pcs_last_30} unit=" pcs" 
                   icon={Zap}
                   tone="violet" />
      </div>

      {/* Monthly Throughput Chart */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> Throughput Bulanan (6 bulan terakhir)
        </h4>
        {series.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 italic">Belum cukup data untuk visualisasi.</p>
        ) : (
          <div className="space-y-2">
            {series.map(s => {
              const pct = (s.pcs / maxPcs) * 100;
              return (
                <div key={s.month} className="flex items-center gap-3">
                  <span className="text-xs text-foreground/70 w-16">{s.month}</span>
                  <div className="flex-1 h-6 rounded bg-foreground/5 overflow-hidden relative">
                    <motion.div
                      className="absolute inset-y-0 left-0 bg-gradient-to-r from-violet-500/40 to-emerald-500/40 border-r border-emerald-400 dark:border-emerald-400/30"
                      initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6 }}
                    />
                    <span className="absolute inset-0 flex items-center px-2 text-xs text-foreground font-mono">
                      {fmtNum(s.pcs)} pcs · {s.jobs} jobs
                      {s.defects > 0 && <span className="ml-2 text-red-600 dark:text-red-300">· {s.defects} defects</span>}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>

      {/* Performance Insights */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Ringkasan Performa
        </h4>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <RowKV label="Jobs Selesai (Lifetime)" value={fmtNum(k.jobs_completed)} />
          <RowKV label="Jobs Aktif" value={fmtNum(k.jobs_active)} />
          <RowKV label="Jobs Dibatalkan" value={fmtNum(k.jobs_cancelled)} />
          <RowKV label="Throughput YTD" value={`${fmtNum(k.pcs_completed_ytd)} pcs`} />
          <RowKV label="Throughput 30d" value={`${fmtNum(k.pcs_last_30)} pcs`} />
          <RowKV label="Throughput 90d" value={`${fmtNum(k.pcs_last_90)} pcs`} />
          <RowKV label="On-Time Completed" value={fmtNum(k.on_time_completed)} />
          <RowKV label="Late Completed" value={fmtNum(k.late_completed)} />
          <RowKV label="Progress Reports (30d)" value={fmtNum(k.progress_reports_30d)} />
          <RowKV label="Rate per Pcs" value={fmtRp(k.rate_per_pcs)} />
          <RowKV label="Penalty per Day" value={fmtRp(k.penalty_per_day)} />
        </div>
      </GlassCard>
    </div>
  );
}

function ScoreCard({ label, value, unit, icon: Icon, tone, target, reverse }) {
  const toneMap = {
    green: 'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/10',
    amber: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/10',
    red:   'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/10',
    violet: 'text-violet-600 dark:text-violet-300 bg-violet-100 dark:bg-violet-500/10',
  };
  const klass = toneMap[tone] || 'text-foreground/70 bg-foreground/5';
  const numericV = value === null || value === undefined ? null : Number(value);
  return (
    <GlassCard className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        {Icon && <Icon className="w-3.5 h-3.5" />} {label}
      </div>
      <div className={`text-3xl font-bold ${klass.split(' ')[0]}`}>
        {numericV === null ? '—' : `${numericV}${unit}`}
      </div>
      {target !== undefined && (
        <div className="text-[10px] text-muted-foreground/60 mt-1">
          Target {reverse ? '≤' : '≥'} {target}{unit}
        </div>
      )}
    </GlassCard>
  );
}

function RowKV({ label, value }) {
  return (
    <div className="flex justify-between p-2 rounded bg-foreground/[0.03] border border-foreground/[0.08]">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground font-semibold">{value}</span>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────
export default function CMTLifecycleModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [selectedVendorId, setSelectedVendorId] = useState(null);

  if (selectedVendorId) {
    return <VendorDetailView vendorId={selectedVendorId} headers={headers} onBack={() => setSelectedVendorId(null)} />;
  }
  return <VendorListView headers={headers} onPick={(v) => setSelectedVendorId(v.partner_id)} />;
}

