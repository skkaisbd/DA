/**
 * ProductionControlTowerModule — Daily Operations Production Dashboard
 * Phase 28 — P2 Workflow Consolidation #3
 *
 * Single dashboard for Production Manager / Supervisor:
 *  - KPI strip: Active WOs, Today's output, On Track / At Risk / Overdue counts
 *  - Progress bars: overall + maklon
 *  - Critical alerts: Overdue + At-Risk WO lists
 *  - Maklon PO progress cards
 *  - WO status breakdown chart
 *  - Upcoming deadline table
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Factory, RefreshCw, AlertTriangle, CheckCircle2, Clock, Package, Truck,
  Activity, TrendingUp, Calendar, Users, Bell, AlertCircle, ChevronRight,
  Layers, Zap, Target, BarChart3,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { PageHeader } from './moduleAtoms';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Helpers ───────────────────────────────────────────────────────────────
function fmtNum(v) { return Number(v || 0).toLocaleString('id-ID'); }
function fmtDate(v) {
  if (!v) return '—';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return v;
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return v; }
}

const RISK_META = {
  on_track:  { label: 'On Track',  color: 'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/15 border-green-400 dark:border-green-400/30', icon: CheckCircle2 },
  at_risk:   { label: 'At Risk',   color: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/15 border-amber-400 dark:border-amber-400/30', icon: AlertTriangle },
  overdue:   { label: 'OVERDUE',   color: 'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/15 border-red-400 dark:border-red-400/30',       icon: AlertCircle },
  unknown:   { label: 'No DL',     color: 'text-foreground/70 bg-muted dark:bg-slate-500/15 border-border dark:border-slate-400/30', icon: Clock },
  completed: { label: 'Completed', color: 'text-emerald-600 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-500/15 border-emerald-400 dark:border-emerald-400/30', icon: CheckCircle2 },
};

function RiskBadge({ risk }) {
  const m = RISK_META[risk] || RISK_META.unknown;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.color}`}>
      <Icon className="w-3 h-3" /> {m.label}
    </span>
  );
}

// ─── KPI Cards ─────────────────────────────────────────────────────────────
function KPICell({ label, value, icon: Icon, tone = 'slate', big = false }) {
  const toneMap = {
    slate:   'text-foreground/70 bg-foreground/[0.03]',
    green:   'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/10',
    amber:   'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/10',
    red:     'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/10',
    violet:  'text-violet-600 dark:text-violet-300 bg-violet-100 dark:bg-violet-500/10',
    blue:    'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/10',
    emerald: 'text-emerald-600 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-500/10',
  };
  const klass = toneMap[tone] || toneMap.slate;
  return (
    <div className={`p-3 rounded-lg border border-foreground/[0.08] ${klass}`}>
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`${big ? 'text-2xl' : 'text-xl'} font-bold ${klass.split(' ')[0]}`}>{value}</div>
    </div>
  );
}

// ─── Progress Bar ──────────────────────────────────────────────────────────
function ProgressBar({ pct, gradient = 'from-violet-500 to-green-500' }) {
  const safePct = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="h-2 rounded-full bg-foreground/10 overflow-hidden">
      <motion.div
        className={`h-full rounded-full bg-gradient-to-r ${gradient}`}
        initial={{ width: 0 }}
        animate={{ width: `${safePct}%` }}
        transition={{ duration: 0.6 }}
      />
    </div>
  );
}

// ─── WO Row Card ──────────────────────────────────────────────────────────
function WORowCard({ wo, onClick }) {
  const dl = wo.deadline ? fmtDate(wo.deadline) : '—';
  const dayLabel = wo.days_to_deadline === null
    ? ''
    : wo.days_to_deadline < 0
      ? `${Math.abs(wo.days_to_deadline)} hari terlewat`
      : wo.days_to_deadline === 0
        ? 'Hari ini'
        : `${wo.days_to_deadline} hari lagi`;

  return (
    <motion.button
      data-testid={`pct-wo-row-${wo.id}`}
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      onClick={() => onClick?.(wo)}
      className="w-full text-left p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30 transition group"
    >
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-mono font-bold text-foreground truncate max-w-[280px]" title={wo.wo_number}>{wo.wo_number}</span>
            <RiskBadge risk={wo.risk_status} />
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70">{wo.status}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5 flex-wrap">
            <span>{wo.artikel || wo.product_name_snapshot || '—'}</span>
            {wo.color && <span>· {wo.color}/{wo.size}</span>}
            {wo.client_name && <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {wo.client_name}</span>}
            <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {dl} {dayLabel && <span className={wo.days_to_deadline < 0 ? 'text-red-600 dark:text-red-300 ml-1' : wo.days_to_deadline <= 5 ? 'text-amber-600 dark:text-amber-300 ml-1' : ''}>({dayLabel})</span>}</span>
          </div>
        </div>
        <div className="text-right min-w-[140px]">
          <div className="text-xs text-muted-foreground">{fmtNum(wo.qty_produced || 0)} / {fmtNum(wo.qty || 0)} pcs</div>
          <div className="flex items-center gap-2 mt-0.5">
            <div className="flex-1">
              <ProgressBar pct={wo.progress_pct} />
            </div>
            <span className="text-xs font-semibold text-foreground w-10 text-right">{wo.progress_pct}%</span>
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground/50 group-hover:text-violet-600 dark:text-violet-400 transition" />
      </div>
    </motion.button>
  );
}

// ─── Maklon PO Progress Card ──────────────────────────────────────────────
function MaklonPOCard({ po, onClick }) {
  const dl = po.deadline ? fmtDate(po.deadline) : '—';
  return (
    <motion.button
      data-testid={`pct-makpo-${po.id}`}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      onClick={() => onClick?.(po)}
      className="w-full text-left p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:border-violet-400 dark:border-violet-400/30 transition group"
    >
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono font-bold text-foreground">{po.po_number}</span>
            <RiskBadge risk={po.risk_status} />
          </div>
          <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
            <Users className="w-3 h-3" /> {po.client_name}
            <span>·</span>
            <Calendar className="w-3 h-3" /> {dl}
            {po.days_to_deadline !== null && po.days_to_deadline !== undefined && (
              <span className={po.days_to_deadline < 0 ? 'text-red-600 dark:text-red-300' : po.days_to_deadline <= 5 ? 'text-amber-600 dark:text-amber-300' : 'text-muted-foreground/60'}>
                ({po.days_to_deadline < 0 ? `${Math.abs(po.days_to_deadline)} hari terlewat` : `${po.days_to_deadline} hari lagi`})
              </span>
            )}
          </div>
        </div>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/70 capitalize">{po.status}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <ProgressBar pct={po.progress_pct} />
        </div>
        <div className="text-right">
          <div className="text-xs font-bold text-foreground">{po.progress_pct}%</div>
          <div className="text-[10px] text-muted-foreground">{fmtNum(po.qty_produced)} / {fmtNum(po.total_qty)}</div>
        </div>
      </div>
    </motion.button>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────
export default function ProductionControlTowerModule({ token, onNavigate }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [woTab, setWoTab] = useState('overdue');
  const [autoRefresh, setAutoRefresh] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/prod/control-tower?days_window=7`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat data');
        return;
      }
      setData(await r.json());
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh every 30s when enabled
  useEffect(() => {
    if (!autoRefresh) return undefined;
    const id = setInterval(() => fetchData(), 30000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchData]);

  const handleWOClick = (wo) => {
    if (wo.maklon_po_id && onNavigate) {
      onNavigate('maklon-po-360', { po_id: wo.maklon_po_id });
    } else if (onNavigate) {
      // WO di Pusat Kendali = job produksi internal → buka daftar Production Jobs
      onNavigate('prod-work-orders', { job_id: wo.id, po_id: wo.po_id, search: wo.wo_number });
    } else {
      toast.info(`WO ${wo.wo_number} — drill-down belum tersedia`);
    }
  };

  const handlePOClick = (po) => {
    if (onNavigate) onNavigate('maklon-po-360', { po_id: po.id });
  };

  if (loading && !data) {
    return (
      <GlassCard className="p-12 text-center text-muted-foreground">
        <RefreshCw className="w-8 h-8 mx-auto mb-3 animate-spin text-violet-600 dark:text-violet-400" />
        Memuat Production Control Tower…
      </GlassCard>
    );
  }

  if (!data) {
    return (
      <GlassCard className="p-8 text-center text-muted-foreground">
        <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-700 dark:text-red-400" />
        Gagal memuat data.
        <Button onClick={fetchData} variant="outline" className="mt-3 border-foreground/10">Coba Lagi</Button>
      </GlassCard>
    );
  }

  const k = data.kpis || {};
  const woTabData = woTab === 'overdue' ? (data.overdue_wos || [])
    : woTab === 'at_risk' ? (data.at_risk_wos || [])
    : (data.all_active_wos || []);
  const woEmptyLabel = woTab === 'overdue' ? 'WO yang overdue' : woTab === 'at_risk' ? 'WO yang at-risk' : 'WO aktif';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Production Control Tower"
        subtitle="Daily operations dashboard untuk Production Manager — semua KPI, alerts, dan progress dalam satu layar."
        icon={Factory}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant={autoRefresh ? 'default' : 'outline'}
              size="sm"
              onClick={() => setAutoRefresh(v => !v)}
              data-testid="pct-auto-refresh"
              className={autoRefresh ? 'bg-green-600 hover:bg-green-500 text-foreground' : 'border-foreground/10 text-foreground/70'}
            >
              <Zap className="w-3.5 h-3.5 mr-1.5" /> {autoRefresh ? 'Live' : 'Manual'}
            </Button>
            <Button variant="ghost" size="sm" onClick={fetchData} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="pct-refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        }
      />

      {/* KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <KPICell label="Active WOs" value={fmtNum(k.active_wos)} icon={Activity} tone="violet" big />
        <KPICell label="Completed Today" value={fmtNum(k.today_completed_wos)} icon={CheckCircle2} tone="green" big />
        <KPICell label="On Track" value={fmtNum(k.on_track)} icon={CheckCircle2} tone="green" />
        <KPICell label="At Risk" value={fmtNum(k.at_risk)} icon={AlertTriangle} tone="amber" />
        <KPICell label="OVERDUE" value={fmtNum(k.overdue)} icon={AlertCircle} tone="red" big />
        <KPICell label="Tanpa Deadline" value={fmtNum(k.unknown_deadline)} icon={Clock} tone="slate" />
        <KPICell label="CMT Pending QC" value={fmtNum(k.cmt_pending_review)} icon={Truck} tone="blue" />
      </div>

      {/* Deep-link Bar: Open Full View buttons to dedicated modules (FORENSIC_09 #7 spec) */}
      <GlassCard className="p-3" data-testid="pct-deeplink-bar">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <p className="text-[11px] text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5" />
            Buka Tampilan Lengkap
          </p>
          <div className="flex items-center flex-wrap gap-2">
            <Button
              variant="outline" size="sm"
              className="h-7 text-xs border-violet-400 dark:border-violet-400/30 text-violet-600 dark:text-violet-300 hover:bg-violet-100 dark:bg-violet-500/10"
              onClick={() => onNavigate && onNavigate('prod-line-board')}
              data-testid="pct-link-line-board"
            >
              <Activity className="w-3 h-3 mr-1" /> Live Line Board
            </Button>
            <Button
              variant="outline" size="sm"
              className="h-7 text-xs border-red-400 dark:border-red-400/30 text-red-600 dark:text-red-300 hover:bg-red-100 dark:bg-red-500/10"
              onClick={() => onNavigate && onNavigate('prod-andon-board')}
              data-testid="pct-link-andon-board"
            >
              <Bell className="w-3 h-3 mr-1" /> Andon Alerts
            </Button>
            <Button
              variant="outline" size="sm"
              className="h-7 text-xs border-blue-400 dark:border-blue-400/30 text-blue-600 dark:text-blue-300 hover:bg-blue-100 dark:bg-blue-500/10"
              onClick={() => onNavigate && onNavigate('prod-shift-handover')}
              data-testid="pct-link-shift-handover"
            >
              <Users className="w-3 h-3 mr-1" /> Shift Handover
            </Button>
            <Button
              variant="outline" size="sm"
              className="h-7 text-xs border-amber-400 dark:border-amber-400/30 text-amber-600 dark:text-amber-300 hover:bg-amber-100 dark:bg-amber-500/10"
              onClick={() => onNavigate && onNavigate('prod-backlog')}
              data-testid="pct-link-backlog"
            >
              <TrendingUp className="w-3 h-3 mr-1" /> Backlog &amp; Forecast
            </Button>
          </div>
        </div>
      </GlassCard>

      {/* Output snapshot */}
      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Target className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Output Snapshot
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {k.window_completed_wos || 0} WO completed in last {k.window_days || 7} days · {fmtNum(k.bundles_pending_print)} bundles pending print
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-right">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Target Total</div>
              <div className="text-lg font-bold text-foreground">{fmtNum(k.total_target_qty)} pcs</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Diproduksi</div>
              <div className="text-lg font-bold text-green-600 dark:text-green-300">{fmtNum(k.total_produced_qty)} pcs</div>
            </div>
            <div className="text-right min-w-[80px]">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Progress</div>
              <div className="text-lg font-bold text-violet-600 dark:text-violet-300">{k.overall_progress_pct || 0}%</div>
            </div>
          </div>
        </div>
        <ProgressBar pct={k.overall_progress_pct} gradient="from-violet-500 via-blue-500 to-green-500" />
        <div className="flex justify-between text-[10px] text-muted-foreground/60 mt-1">
          <span>0</span>
          <span>{fmtNum(k.total_target_qty)} pcs</span>
        </div>
      </GlassCard>

      {/* Critical Alerts Section */}
      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Bell className="w-4 h-4 text-red-600 dark:text-red-300" /> Critical Alerts
            {(k.overdue + k.at_risk) > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 border border-red-400 dark:border-red-400/30">
                {fmtNum(k.overdue + k.at_risk)} aktif
              </span>
            )}
          </h3>
        </div>
        <Tabs value={woTab} onValueChange={setWoTab}>
          <TabsList className="bg-foreground/5 mb-3">
            <TabsTrigger value="overdue" data-testid="pct-tab-overdue" className="data-[state=active]:bg-red-600 data-[state=active]:text-foreground">
              <AlertCircle className="w-3 h-3 mr-1" /> Overdue ({k.overdue || 0})
            </TabsTrigger>
            <TabsTrigger value="at_risk" data-testid="pct-tab-at-risk" className="data-[state=active]:bg-amber-600 data-[state=active]:text-foreground">
              <AlertTriangle className="w-3 h-3 mr-1" /> At Risk ({k.at_risk || 0})
            </TabsTrigger>
            <TabsTrigger value="all" data-testid="pct-tab-all" className="data-[state=active]:bg-violet-600 data-[state=active]:text-foreground">
              <Activity className="w-3 h-3 mr-1" /> Semua WO ({k.active_wos || 0})
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {woTabData.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground/60 gap-2">
            <CheckCircle2 className="w-10 h-10 opacity-30" />
            <p className="text-sm">Tidak ada {woEmptyLabel}</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
            {woTabData.map(wo => (
              <WORowCard key={wo.id} wo={wo} onClick={handleWOClick} />
            ))}
          </div>
        )}
      </GlassCard>

      {/* Maklon Progress */}
      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Package className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Maklon PO Progress ({k.maklon_active_pos || 0} aktif)
          </h3>
          <div className="flex items-center gap-3 text-xs">
            <span className="text-muted-foreground">Target {fmtNum(k.maklon_target_qty)} pcs</span>
            <span>·</span>
            <span className="text-green-600 dark:text-green-300">{fmtNum(k.maklon_produced_qty)} produced</span>
            <span>·</span>
            <span className="text-violet-600 dark:text-violet-300 font-bold">{k.maklon_progress_pct || 0}%</span>
          </div>
        </div>
        {(data.maklon_progress || []).length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground/60 gap-2">
            <Package className="w-10 h-10 opacity-30" />
            <p className="text-sm">Belum ada PO Maklon yang aktif</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(data.maklon_progress || []).map(po => (
              <MaklonPOCard key={po.id} po={po} onClick={handlePOClick} />
            ))}
          </div>
        )}
      </GlassCard>

      {/* WO Status Breakdown */}
      <GlassCard className="p-5">
        <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> WO Status Breakdown
        </h3>
        {Object.keys(data.wo_status_breakdown || {}).length === 0 ? (
          <p className="text-xs text-muted-foreground/60 italic">Belum ada WO aktif.</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(data.wo_status_breakdown || {})
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => {
                const pct = k.active_wos > 0 ? (count / k.active_wos) * 100 : 0;
                return (
                  <div key={status} className="flex items-center gap-3">
                    <span className="text-xs text-foreground/70 w-32 truncate capitalize">{status.replace(/_/g, ' ')}</span>
                    <div className="flex-1 h-6 rounded bg-foreground/5 overflow-hidden relative">
                      <motion.div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-violet-500/40 to-violet-500/20 border-r border-violet-400 dark:border-violet-400/30"
                        initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }}
                      />
                      <span className="absolute inset-0 flex items-center px-2 text-xs text-foreground font-mono">
                        {count} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </GlassCard>

      {/* Upcoming Deadlines */}
      {(data.upcoming_deadlines || []).length > 0 && (
        <GlassCard className="p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Calendar className="w-4 h-4 text-amber-600 dark:text-amber-300" /> Deadline Dekat (≤14 hari)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(data.upcoming_deadlines || []).map(po => (
              <MaklonPOCard key={po.id} po={po} onClick={handlePOClick} />
            ))}
          </div>
        </GlassCard>
      )}

      <div className="text-[10px] text-muted-foreground/60 text-right">
        Last update: {new Date(data.as_of).toLocaleString('id-ID')} {autoRefresh && '· auto-refresh setiap 30s'}
      </div>
    </div>
  );
}
