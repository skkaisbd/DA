/**
 * ARLifecycleModule — AR 360° Dashboard
 * Phase 30 — Order-to-Cash (OTC) Completion
 *
 * Three views:
 *  A) Dashboard — system KPIs + bucket totals + top debtors
 *  B) Aging Matrix — per-customer aging table (drillable)
 *  C) Customer Statement — detail view with running balance for one customer
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Scale, RefreshCw, Search, ChevronRight, ArrowLeft, FileText, DollarSign,
  Calendar, Clock, AlertTriangle, AlertCircle, CheckCircle2, TrendingUp,
  TrendingDown, Users, Phone, Building2, Banknote, Receipt, FileSpreadsheet,
  BarChart3, Filter, Printer, ExternalLink,} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { PageHeader, EmptyState } from './moduleAtoms';
import { Skeleton } from '@/components/ui/skeleton';
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
function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  return `${Number(v).toFixed(1)}%`;
}

const BUCKET_LABELS = {
  current: { label: 'Current',        color: 'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/15 border-green-400 dark:border-green-400/30' },
  '1_30':  { label: '1-30 hari',      color: 'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/15 border-blue-400 dark:border-blue-400/30' },
  '31_60': { label: '31-60 hari',     color: 'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/15 border-amber-400 dark:border-amber-400/30' },
  '61_90': { label: '61-90 hari',     color: 'text-orange-600 dark:text-orange-300 bg-orange-100 dark:bg-orange-500/15 border-orange-400 dark:border-orange-400/30' },
  '90_plus': { label: '> 90 hari',    color: 'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/15 border-red-400 dark:border-red-400/30' },
};

function BucketBadge({ bucket }) {
  const m = BUCKET_LABELS[bucket] || BUCKET_LABELS.current;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${m.color}`}>
      {m.label}
    </span>
  );
}

// ─── KPI ─────────────────────────────────────────────────────────────────
function KPICell({ label, value, sub, icon: Icon, tone = 'slate' }) {
  const toneMap = {
    slate:   'text-foreground/70',
    green:   'text-green-600 dark:text-green-300',
    amber:   'text-amber-600 dark:text-amber-300',
    red:     'text-red-600 dark:text-red-300',
    violet:  'text-violet-600 dark:text-violet-300',
    blue:    'text-blue-600 dark:text-blue-300',
    emerald: 'text-emerald-600 dark:text-emerald-300',
    orange:  'text-orange-600 dark:text-orange-300',
  };
  return (
    <div className="p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08]">
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      <div className={`text-lg font-bold ${toneMap[tone]} leading-tight`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

// ─── Customer Statement View ────────────────────────────────────────────
function CustomerStatementView({ customerId, headers, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      const r = await fetch(`${API}/api/rahaza/ar-360/customer/${customerId}/statement?${params}`, { headers });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        toast.error(e.detail || 'Gagal memuat statement');
        return;
      }
      setData(await r.json());
    } catch (e) {
      toast.error('Network error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [customerId, headers, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data) {
    return (
      <div className="space-y-4 p-2" data-testid="ar360-statement-skeleton">
        <Skeleton className="h-20 rounded-xl" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  const cust = data.customer || {};
  const txs = data.transactions || [];
  const aging = data.aging_snapshot || {};
  const totalAging = data.aging_total || 0;

  return (
    <div className="space-y-5">
      {/* Header */}
      <GlassCard className="p-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack} data-testid="ar360-back" className="text-foreground/70 hover:text-foreground">
              <ArrowLeft className="w-4 h-4 mr-1" /> Kembali
            </Button>
            <div className="border-l border-foreground/10 pl-4">
              <div className="flex items-center gap-2 flex-wrap">
                <Building2 className="w-4 h-4 text-violet-600 dark:text-violet-300" />
                <h3 className="text-lg font-bold text-foreground">{cust.name}</h3>
                {cust.code && <span className="text-xs font-mono text-violet-600 dark:text-violet-300">{cust.code}</span>}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-3 flex-wrap">
                {cust.address && <span>{cust.address}</span>}
                {(cust.phone || cust.contact_phone) && (
                  <span className="flex items-center gap-1"><Phone className="w-3 h-3" /> {cust.phone || cust.contact_phone}</span>
                )}
                {cust.payment_terms && <span>Terms: {cust.payment_terms}</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.print()}
              className="border-foreground/10 text-foreground/70 hover:text-foreground"
              data-testid="ar360-print"
            >
              <Printer className="w-3.5 h-3.5 mr-1" /> Print
            </Button>
            <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="text-muted-foreground hover:text-foreground">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </GlassCard>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPICell label="Total Ditagih" value={fmtRp(data.total_billed)} icon={FileText} tone="blue" sub={`${data.total_invoices} invoice`} />
        <KPICell label="Total Dibayar" value={fmtRp(data.total_paid)} icon={Banknote} tone="green" sub={`${data.total_payments} pembayaran`} />
        <KPICell label="Outstanding Balance" value={fmtRp(data.closing_balance)} icon={DollarSign} tone={data.closing_balance > 0 ? 'red' : 'green'} />
        <KPICell label="Open Aging" value={fmtRp(totalAging)} icon={Clock} tone="amber" />
      </div>

      {/* Aging Snapshot */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-amber-600 dark:text-amber-300" /> Aging Snapshot
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <AgingBucket label="Current"    value={aging.current}    total={totalAging} tone="green" />
          <AgingBucket label="1-30 hari"  value={aging['1_30']}    total={totalAging} tone="blue" />
          <AgingBucket label="31-60 hari" value={aging['31_60']}   total={totalAging} tone="amber" />
          <AgingBucket label="61-90 hari" value={aging['61_90']}   total={totalAging} tone="orange" />
          <AgingBucket label="> 90 hari"  value={aging['90_plus']} total={totalAging} tone="red" />
        </div>
      </GlassCard>

      {/* Date Filter */}
      <GlassCard className="p-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Filter className="w-3 h-3" /> Periode:
          </span>
          <div className="flex items-center gap-1">
            <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="bg-foreground/5 border-foreground/10 text-xs w-36 h-8" data-testid="ar360-date-from" />
            <span className="text-muted-foreground text-xs">→</span>
            <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="bg-foreground/5 border-foreground/10 text-xs w-36 h-8" data-testid="ar360-date-to" />
          </div>
          {(dateFrom || dateTo) && (
            <Button size="sm" variant="ghost" onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-muted-foreground text-xs h-7">
              Reset
            </Button>
          )}
        </div>
      </GlassCard>

      {/* Transactions Table with Running Balance */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <Receipt className="w-4 h-4 text-violet-600 dark:text-violet-300" /> Riwayat Transaksi ({txs.length})
        </h4>
        {txs.length === 0 ? (
          <EmptyState icon={Receipt} title="Belum ada transaksi" description="Transaksi untuk customer ini akan tampil di sini." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b border-foreground/10">
                  <th className="text-left py-2 px-2">Tanggal</th>
                  <th className="text-left py-2 px-2">Jenis</th>
                  <th className="text-left py-2 px-2">Referensi</th>
                  <th className="text-left py-2 px-2">Deskripsi</th>
                  <th className="text-right py-2 px-2">Debit</th>
                  <th className="text-right py-2 px-2">Kredit</th>
                  <th className="text-right py-2 px-2">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {txs.map((t, idx) => {
                  const isInvoice = t.type === 'invoice';
                  return (
                    <motion.tr
                      key={idx}
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                      transition={{ delay: idx * 0.01 }}
                      className="border-b border-foreground/5 hover:bg-foreground/[0.03]"
                    >
                      <td className="py-2 px-2 text-foreground/70">{fmtDate(t.date)}</td>
                      <td className="py-2 px-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${isInvoice ? 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 border border-blue-400 dark:border-blue-400/30' : 'bg-green-100 dark:bg-green-500/15 text-green-600 dark:text-green-300 border border-green-400 dark:border-green-400/30'}`}>
                          {isInvoice ? 'INVOICE' : 'PAYMENT'}
                        </span>
                      </td>
                      <td className="py-2 px-2 font-mono text-violet-600 dark:text-violet-300">{t.reference}</td>
                      <td className="py-2 px-2 text-foreground/70">{t.description}</td>
                      <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300 font-semibold">
                        {t.debit > 0 ? fmtRp(t.debit) : '—'}
                      </td>
                      <td className="py-2 px-2 text-right text-green-600 dark:text-green-300 font-semibold">
                        {t.credit > 0 ? fmtRp(t.credit) : '—'}
                      </td>
                      <td className={`py-2 px-2 text-right font-bold ${t.balance_after > 0 ? 'text-amber-600 dark:text-amber-300' : 'text-green-600 dark:text-green-300'}`}>
                        {fmtRp(t.balance_after)}
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-violet-400/40">
                  <td colSpan="4" className="py-2 px-2 text-xs text-foreground font-bold">Saldo Akhir</td>
                  <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300 font-bold">{fmtRp(data.total_billed)}</td>
                  <td className="py-2 px-2 text-right text-green-600 dark:text-green-300 font-bold">{fmtRp(data.total_paid)}</td>
                  <td className={`py-2 px-2 text-right text-base font-bold ${data.closing_balance > 0 ? 'text-amber-600 dark:text-amber-300' : 'text-green-600 dark:text-green-300'}`}>
                    {fmtRp(data.closing_balance)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}

function AgingBucket({ label, value = 0, total = 0, tone }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const toneMap = {
    green:  'text-green-600 dark:text-green-300 bg-green-100 dark:bg-green-500/10 border-green-300 dark:border-green-400/20',
    blue:   'text-blue-600 dark:text-blue-300 bg-blue-100 dark:bg-blue-500/10 border-blue-300 dark:border-blue-400/20',
    amber:  'text-amber-600 dark:text-amber-300 bg-amber-100 dark:bg-amber-500/10 border-amber-300 dark:border-amber-400/20',
    orange: 'text-orange-600 dark:text-orange-300 bg-orange-100 dark:bg-orange-500/10 border-orange-300 dark:border-orange-400/20',
    red:    'text-red-600 dark:text-red-300 bg-red-100 dark:bg-red-500/10 border-red-300 dark:border-red-400/20',
  };
  const klass = toneMap[tone] || toneMap.blue;
  return (
    <div className={`p-3 rounded-lg border ${klass}`}>
      <div className="text-[10px] uppercase tracking-wider">{label}</div>
      <div className="text-base font-bold mt-1">{fmtRp(value)}</div>
      <div className="text-[10px] text-muted-foreground mt-0.5">{pct}%</div>
    </div>
  );
}

// ─── Dashboard / Aging Matrix View ──────────────────────────────────────
function DashboardView({ headers, onPickCustomer }) {
  const [dashboard, setDashboard] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('overview');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${API}/api/rahaza/ar-360/dashboard?top_n=20`, { headers }),
        fetch(`${API}/api/rahaza/ar-360/aging`, { headers }),
      ]);
      if (r1.ok) setDashboard(await r1.json());
      if (r2.ok) setMatrix(await r2.json());
    } catch (e) {
      toast.error('Gagal memuat: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const matrixRows = useMemo(() => {
    if (!matrix?.rows) return [];
    if (!search) return matrix.rows;
    const q = search.toLowerCase();
    return matrix.rows.filter(r =>
      (r.customer_name || '').toLowerCase().includes(q) ||
      (r.customer_code || '').toLowerCase().includes(q)
    );
  }, [matrix, search]);

  const k = dashboard?.kpis || {};
  const buckets = dashboard?.buckets || {};
  const bucketCounts = dashboard?.bucket_counts || {};
  const totalBucket = Object.values(buckets).reduce((s, v) => s + (Number(v) || 0), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AR 360° Dashboard"
        subtitle="Aging Bucket, Customer Statement, dan Top Debtors — pusat manajemen piutang."
        icon={Scale}
        actions={
          <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="text-muted-foreground hover:text-foreground" data-testid="ar360-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        }
      />

      {/* Top KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KPICell label="Total Outstanding" value={fmtRp(k.total_outstanding)} icon={DollarSign} tone="red" />
        <KPICell label="Overdue Amount" value={fmtRp(k.total_overdue_amount)} icon={AlertCircle} tone="red" sub={`${fmtPct(k.overdue_pct_of_outstanding)} dari total`} />
        <KPICell label="Open Invoices" value={fmtNum(k.count_open_invoices)} icon={FileText} tone="blue" sub={`${k.count_overdue_invoices || 0} overdue`} />
        <KPICell label="Avg Days Overdue" value={`${k.avg_days_overdue || 0} hari`} icon={Clock} tone="amber" />
        <KPICell label="Unique Debtors" value={fmtNum(k.total_unique_debtors)} icon={Users} tone="violet" />
        <KPICell label="DSO Estimate" value={k.dso_estimate_days ? `${k.dso_estimate_days} hari` : '—'} icon={TrendingUp} tone="emerald" sub={`Collected 30d: ${fmtRp(k.cash_collected_30d)}`} />
      </div>

      {/* Bucket Overview */}
      <GlassCard className="p-4">
        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-600 dark:text-cyan-300" /> Distribusi Aging
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(BUCKET_LABELS).map(([key, m]) => {
            const val = buckets[key] || 0;
            const cnt = bucketCounts[key] || 0;
            const pct = totalBucket > 0 ? (val / totalBucket) * 100 : 0;
            return (
              <div key={key} className={`p-3 rounded-lg border ${m.color.replace('text-', 'border-').replace('/30', '/20')}`}>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.label}</div>
                <div className={`text-lg font-bold ${m.color.split(' ')[0]} mt-1`}>{fmtRp(val)}</div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-[10px] text-muted-foreground">{cnt} invoice</span>
                  <span className="text-[10px] font-semibold text-foreground/70">{pct.toFixed(0)}%</span>
                </div>
                <div className="h-1 rounded-full bg-foreground/10 mt-1.5 overflow-hidden">
                  <motion.div
                    className={`h-full ${m.color.split(' ')[1]}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.6 }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </GlassCard>

      {/* Tabs */}
      <GlassCard className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-foreground/5 h-auto p-1">
              <TabsTrigger value="overview" data-testid="ar360-tab-overview">
                <TrendingUp className="w-3 h-3 mr-1" /> Top Debtors
              </TabsTrigger>
              <TabsTrigger value="matrix" data-testid="ar360-tab-matrix">
                <FileSpreadsheet className="w-3 h-3 mr-1" /> Aging Matrix
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center bg-foreground/5 border border-foreground/10 rounded-md px-3 min-w-[240px]">
            <Search className="w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Cari nama / kode customer..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent border-0 focus-visible:ring-0 text-sm"
              data-testid="ar360-search"
            />
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15 }}>
            {tab === 'overview' && (
              <TopDebtorsView debtors={dashboard?.top_debtors || []} search={search} onPickCustomer={onPickCustomer} />
            )}
            {tab === 'matrix' && (
              <AgingMatrixView rows={matrixRows} totals={matrix?.totals || {}} onPickCustomer={onPickCustomer} />
            )}
          </motion.div>
        </AnimatePresence>
      </GlassCard>
    </div>
  );
}

function TopDebtorsView({ debtors, search, onPickCustomer }) {
  const filtered = useMemo(() => {
    if (!search) return debtors;
    const q = search.toLowerCase();
    return debtors.filter(d =>
      (d.customer_name || '').toLowerCase().includes(q) ||
      (d.customer_code || '').toLowerCase().includes(q)
    );
  }, [debtors, search]);

  if (filtered.length === 0) {
    return (
      <EmptyState
        icon={search ? Search : Users}
        title={search ? 'Tidak ada customer yang cocok' : 'Tidak ada debtor yang outstanding 🎉'}
        description={search ? 'Coba ubah kata kunci pencarian.' : 'Semua piutang sudah lunas!'}
      />
    );
  }

  return (
    <div className="space-y-2">
      {filtered.map((d, idx) => (
        <motion.button
          key={d.customer_id}
          data-testid={`ar360-debtor-${d.customer_id}`}
          initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.02 }}
          onClick={() => onPickCustomer(d)}
          className="w-full text-left p-3 rounded-lg bg-foreground/[0.03] border border-foreground/[0.08] hover:bg-foreground/[0.06] hover:border-violet-400 dark:border-violet-400/30 transition group"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className="w-8 h-8 rounded-full bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center text-violet-600 dark:text-violet-300 font-bold text-sm flex-shrink-0">
                {idx + 1}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-foreground truncate">{d.customer_name}</span>
                  {d.customer_code && <span className="text-[10px] font-mono text-violet-600 dark:text-violet-300">{d.customer_code}</span>}
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-3 flex-wrap">
                  <span>{d.invoice_count} invoice</span>
                  {d.oldest_days_overdue > 0 && (
                    <span className="text-amber-600 dark:text-amber-300">Terlama: {d.oldest_days_overdue} hari overdue</span>
                  )}
                </div>
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-base font-bold text-red-600 dark:text-red-300">{fmtRp(d.outstanding)}</div>
              {d.overdue_amount > 0 && (
                <div className="text-[10px] text-amber-600 dark:text-amber-300">Overdue: {fmtRp(d.overdue_amount)}</div>
              )}
            </div>
            <ChevronRight className="w-4 h-4 text-foreground/15 group-hover:text-violet-600 dark:text-violet-400 transition flex-shrink-0" />
          </div>
        </motion.button>
      ))}
    </div>
  );
}

function AgingMatrixView({ rows, totals, onPickCustomer }) {
  if (rows.length === 0) {
    return (
      <EmptyState icon={FileSpreadsheet} title="Tidak ada data aging" description="Data aging piutang akan muncul di sini setelah ada invoice." />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b border-foreground/10">
            <th className="text-left py-2 px-2">Customer</th>
            <th className="text-right py-2 px-2">Current</th>
            <th className="text-right py-2 px-2">1-30 hari</th>
            <th className="text-right py-2 px-2">31-60 hari</th>
            <th className="text-right py-2 px-2">61-90 hari</th>
            <th className="text-right py-2 px-2">&gt; 90 hari</th>
            <th className="text-right py-2 px-2 border-l border-foreground/10">Total</th>
            <th className="text-center py-2 px-2">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <motion.tr
              key={r.customer_id}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="border-b border-foreground/5 hover:bg-foreground/[0.03]"
            >
              <td className="py-2 px-2">
                <div className="flex items-center gap-2">
                  <span className="text-foreground font-semibold truncate max-w-[200px]" title={r.customer_name}>{r.customer_name}</span>
                  {r.customer_code && <span className="text-[10px] font-mono text-violet-600 dark:text-violet-300">{r.customer_code}</span>}
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {r.count} inv · oldest {r.oldest_days_overdue}d
                </div>
              </td>
              <td className="py-2 px-2 text-right">{r.current > 0 ? <span className="text-green-600 dark:text-green-300">{fmtRp(r.current)}</span> : <span className="text-foreground/15">—</span>}</td>
              <td className="py-2 px-2 text-right">{r['1_30'] > 0 ? <span className="text-blue-600 dark:text-blue-300">{fmtRp(r['1_30'])}</span> : <span className="text-foreground/15">—</span>}</td>
              <td className="py-2 px-2 text-right">{r['31_60'] > 0 ? <span className="text-amber-600 dark:text-amber-300">{fmtRp(r['31_60'])}</span> : <span className="text-foreground/15">—</span>}</td>
              <td className="py-2 px-2 text-right">{r['61_90'] > 0 ? <span className="text-orange-600 dark:text-orange-300">{fmtRp(r['61_90'])}</span> : <span className="text-foreground/15">—</span>}</td>
              <td className="py-2 px-2 text-right">{r['90_plus'] > 0 ? <span className="text-red-600 dark:text-red-300 font-bold">{fmtRp(r['90_plus'])}</span> : <span className="text-foreground/15">—</span>}</td>
              <td className="py-2 px-2 text-right border-l border-foreground/10">
                <span className="text-foreground font-bold">{fmtRp(r.total)}</span>
              </td>
              <td className="py-2 px-2 text-center">
                <Button
                  size="sm"
                  variant="outline"
                  className="border-violet-400 dark:border-violet-400/30 text-violet-600 dark:text-violet-300 hover:bg-violet-100 dark:bg-violet-500/10 text-[10px] h-7 px-2"
                  data-testid={`ar360-matrix-statement-${r.customer_id}`}
                  onClick={() => onPickCustomer(r)}
                >
                  <ExternalLink className="w-3 h-3 mr-1" /> Statement
                </Button>
              </td>
            </motion.tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-violet-400/40 font-bold">
            <td className="py-2 px-2 text-foreground">TOTAL ({totals.count || 0} invoice)</td>
            <td className="py-2 px-2 text-right text-green-600 dark:text-green-300">{fmtRp(totals.current)}</td>
            <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-300">{fmtRp(totals['1_30'])}</td>
            <td className="py-2 px-2 text-right text-amber-600 dark:text-amber-300">{fmtRp(totals['31_60'])}</td>
            <td className="py-2 px-2 text-right text-orange-600 dark:text-orange-300">{fmtRp(totals['61_90'])}</td>
            <td className="py-2 px-2 text-right text-red-600 dark:text-red-300">{fmtRp(totals['90_plus'])}</td>
            <td className="py-2 px-2 text-right text-base text-foreground border-l border-foreground/10">{fmtRp(totals.total)}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────
export default function ARLifecycleModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);

  if (selectedCustomerId) {
    return (
      <CustomerStatementView
        customerId={selectedCustomerId}
        headers={headers}
        onBack={() => setSelectedCustomerId(null)}
      />
    );
  }
  return <DashboardView headers={headers} onPickCustomer={(d) => setSelectedCustomerId(d.customer_id)} />;
}

