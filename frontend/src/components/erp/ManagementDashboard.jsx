/**
 * Dashboard Eksekutif — CV. Dewi Aditya ERP
 * Ringkasan performa operasional lintas departemen dengan KPI real-time.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from 'recharts';
import {
  TrendingUp, Package, Factory, Banknote, AlertTriangle, Clock, Truck, Users,
  Calendar, UserCheck, Zap, Activity, TrendingDown,
} from 'lucide-react';
import {
  StatCard, ChartCard, GlassTooltip, HeroCrystalCard, CHART_PALETTE,
} from './dashboardAtoms';
import NextActionWidget from './NextActionWidget';
import { PeriodPicker } from './PeriodPicker';

const fmtNum = (v) => Number(v || 0).toLocaleString('id-ID');
const fmtShortIDR = (n) => {
  const v = Number(n || 0);
  if (v >= 1e9) return `Rp ${(v / 1e9).toFixed(1)}M`;
  if (v >= 1e6) return `Rp ${(v / 1e6).toFixed(1)}jt`;
  if (v >= 1e3) return `Rp ${(v / 1e3).toFixed(0)}rb`;
  return `Rp ${v.toLocaleString('id-ID')}`;
};

// AR Aging bar chart
function ARAgingBar({ data }) {
  if (!data) return null;
  const items = [
    { label: 'Belum JT', key: 'current', color: '#22c55e' },
    { label: '1-30 hr',  key: 'd30',    color: '#eab308' },
    { label: '31-60 hr', key: 'd60',    color: '#f97316' },
    { label: '61-90 hr', key: 'd90',    color: '#ef4444' },
    { label: '>90 hr',   key: 'd90plus',color: '#7f1d1d' },
  ];
  const total = items.reduce((s, i) => s + (data[i.key] || 0), 0);
  if (total === 0) return <p className="text-xs text-muted-foreground text-center py-4">Tidak ada piutang outstanding</p>;
  return (
    <div className="space-y-2">
      {items.map(({ label, key, color }) => {
        const val = data[key] || 0;
        const pct = total > 0 ? Math.round(val / total * 100) : 0;
        if (val === 0) return null;
        return (
          <div key={key} className="flex items-center gap-2 text-xs">
            <div className="w-16 text-muted-foreground shrink-0">{label}</div>
            <div className="flex-1 bg-muted/40 rounded-full h-3 overflow-hidden">
              <div className="h-3 rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
            </div>
            <div className="w-20 text-right font-medium tabular-nums">{fmtShortIDR(val)}</div>
            <div className="w-9 text-right text-muted-foreground">{pct}%</div>
          </div>
        );
      })}
      <div className="flex justify-between text-xs text-muted-foreground pt-1 border-t">
        <span>Total AR</span>
        <span className="font-semibold text-foreground">{fmtShortIDR(total)}</span>
      </div>
    </div>
  );
}

export default function ManagementDashboard({ token, onNavigate, onModuleChange }) {
  const [metrics, setMetrics] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState({ preset: '30d', from: null, to: null, compare: false });
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Task 2.4/Dashboard 13→12: unified navigate helper (supports both onNavigate and onModuleChange)
  const drill = (moduleId) => () => {
    if (onModuleChange) onModuleChange(moduleId);
    else if (onNavigate) onNavigate(moduleId);
  };

  const fetchData = useCallback(async () => {
    try {
      const [mRes, aRes] = await Promise.all([
        fetch('/api/dashboard', { headers }),
        fetch('/api/dashboard/analytics', { headers }),
      ]);
      if (mRes.ok) setMetrics(await mRes.json());
      if (aRes.ok) setAnalytics(await aRes.json());
    } catch (e) { /* ignore */ }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return (
    <div className="space-y-5">
      <div className="h-32 rounded-[var(--radius-xl)] bg-[var(--card-surface)] border border-[var(--glass-border)] animate-pulse" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[...Array(8)].map((_, i) => <div key={i} className="h-28 rounded-[var(--radius-lg)] bg-[var(--card-surface)] border border-[var(--glass-border)] animate-pulse" />)}
      </div>
    </div>
  );

  const weeklyTP = analytics?.weeklyThroughput || [];
  const woStatusData = (metrics?.woStatus || []).map(s => ({ name: s._id || 'Unknown', value: s.count }));
  const today = new Date().toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  return (
    <div className="space-y-5" data-testid="management-dashboard">
      <HeroCrystalCard
        testId="mgmt-dashboard-hero"
        eyebrow="Portal Management"
        title="Dashboard Eksekutif"
        description={`CV. Dewi Aditya ERP — ${today}. Ringkasan performa operasional lintas departemen.`}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <PeriodPicker value={period} onChange={setPeriod} compareEnabled={true} testId="mgmt-dashboard-period" />
            {(onModuleChange || onNavigate) && (
              <button
                onClick={drill('ai-business-dashboard')()}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-purple-600/80 hover:bg-purple-600 text-foreground rounded-lg shadow-sm transition-colors"
                title="Buka AI Business Intelligence"
              >
                🤖 AI Business
              </button>
            )}
          </div>
        }
      />

      <NextActionWidget
        token={token}
        portal="management"
        onNavigate={(moduleId) => onNavigate && onNavigate(moduleId)}
        onOpenSetupWizard={() => { onNavigate && onNavigate('production-dashboard'); }}
        maxCards={5}
      />

      {/* ── TODAY'S REAL-TIME KPIs ── */}
      <div className="rounded-xl border bg-gradient-to-r from-primary/5 to-blue-500/5 p-4">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          KPI Hari Ini · Real-time
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Revenue Today */}
          <div className="space-y-0.5" data-testid="kpi-revenue-today">
            <p className="text-xs text-muted-foreground">Revenue Hari Ini</p>
            <p className="text-lg font-bold text-primary">{fmtShortIDR(metrics?.revenueToday)}</p>
            <p className="text-xs text-muted-foreground">MTD: {fmtShortIDR(metrics?.revenueMTD)}</p>
          </div>
          {/* Revenue YTD */}
          <div className="space-y-0.5" data-testid="kpi-revenue-ytd">
            <p className="text-xs text-muted-foreground">Revenue YTD</p>
            <p className="text-lg font-bold text-emerald-600">{fmtShortIDR(metrics?.revenueYTD)}</p>
            <p className="text-xs text-muted-foreground">Tahun {new Date().getFullYear()}</p>
          </div>
          {/* Attendance Today */}
          <div className="space-y-0.5" data-testid="kpi-attendance">
            <p className="text-xs text-muted-foreground">Kehadiran Hari Ini</p>
            <p className="text-lg font-bold text-blue-600">
              {metrics?.attendanceTodayPct ?? '—'}%
            </p>
            <p className="text-xs text-muted-foreground">
              {metrics?.attendanceTodayCount ?? 0} / {metrics?.activeEmployees ?? 0} karyawan
            </p>
          </div>
          {/* OEE */}
          <div className="space-y-0.5" data-testid="kpi-oee">
            <p className="text-xs text-muted-foreground">OEE Rata-rata (7 hari)</p>
            <p className={`text-lg font-bold ${
              metrics?.avgOEE == null ? 'text-muted-foreground' :
              metrics.avgOEE >= 85 ? 'text-emerald-600' :
              metrics.avgOEE >= 65 ? 'text-amber-600' : 'text-red-600'
            }`}>
              {metrics?.avgOEE != null ? `${metrics.avgOEE}%` : '—'}
            </p>
            <p className="text-xs text-muted-foreground">
              {metrics?.avgOEE == null ? 'Belum ada data OEE' :
               metrics.avgOEE >= 85 ? 'World-class (≥85%)' :
               metrics.avgOEE >= 65 ? 'Perlu ditingkatkan' : 'Kritis — perhatian'}
            </p>
          </div>
        </div>
      </div>

      {/* ── KPI Row 1 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 auto-rows-fr">
        <StatCard testId="mgmt-kpi-orders" icon={Package} label="Total Order"
          value={fmtNum(metrics?.totalPOs)} sub={`${metrics?.activePOs || 0} aktif`}
          accent="primary"
          trend={metrics?.delayedPOs > 0 ? { value: -metrics.delayedPOs, suffix: ' terlambat', label: 'dari jadwal' } : null}
          onClick={drill('prod-orders')}
        />
        <StatCard testId="mgmt-kpi-jobs" icon={Factory} label="Job Aktif"
          value={fmtNum(metrics?.activeJobs)} sub="Job produksi berjalan" accent="info"
          onClick={drill('prod-work-orders')} />
        <StatCard testId="mgmt-kpi-ontime" icon={Clock} label="On-Time Rate"
          value={`${metrics?.onTimeRate || 0}%`} sub="Order tepat waktu"
          accent={metrics?.onTimeRate >= 80 ? 'success' : 'warning'}
          trend={{ value: metrics?.onTimeRate >= 80 ? 5 : -5, label: metrics?.onTimeRate >= 80 ? 'Baik' : 'Perlu perhatian' }}
          onClick={drill('prod-orders')}
        />
        <StatCard testId="mgmt-kpi-revenue" icon={Banknote} label="Total Revenue"
          value={fmtShortIDR(metrics?.totalRevenue)} sub={`Margin: ${fmtShortIDR(metrics?.grossMargin)}`}
          accent="mint"
          onClick={drill('fin-ar-invoices')} />
      </div>

      {/* ── KPI Row 2 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 auto-rows-fr">
        <StatCard testId="mgmt-kpi-employees" icon={Users} label="Karyawan Aktif"
          value={fmtNum(metrics?.activeEmployees)} sub={`${metrics?.attendanceTodayPct ?? 0}% hadir hari ini`}
          accent="info"
          onClick={drill('hr-employees')} />
        <StatCard testId="mgmt-kpi-ar" icon={TrendingUp} label="Outstanding AR"
          value={fmtShortIDR(metrics?.outstandingAR)} sub="Piutang belum bayar" accent="primary"
          onClick={drill('fin-ar-invoices')} />
        <StatCard testId="mgmt-kpi-ap" icon={AlertTriangle} label="Outstanding AP"
          value={fmtShortIDR(metrics?.outstandingAP)} sub="Hutang belum bayar"
          accent={metrics?.outstandingAP > 0 ? 'warning' : 'success'}
          onClick={drill('fin-ap-aging')} />
        <StatCard testId="mgmt-kpi-shipments" icon={Truck} label="Shipment Tertunda"
          value={fmtNum(metrics?.pendingShipments)} sub="Material belum diterima"
          accent={metrics?.pendingShipments > 0 ? 'warning' : 'success'}
          onClick={drill('wh-stock')} />
      </div>

      {/* ── AR Aging + WO Status ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="AR Aging" subtitle="Distribusi piutang berdasarkan hari keterlambatan" data-testid="chart-ar-aging">
          <ARAgingBar data={metrics?.arAging} />
        </ChartCard>

        <ChartCard title="Status Job Produksi" subtitle="Distribusi WO per status">
          {woStatusData.length > 0 ? (
            <>
              <div style={{ width: '100%', height: 140 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={woStatusData} cx="50%" cy="50%" innerRadius={40} outerRadius={62} paddingAngle={3} dataKey="value" strokeWidth={0}>
                      {woStatusData.map((_, i) => <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />)}
                    </Pie>
                    <Tooltip content={<GlassTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-1.5 mt-2">
                {woStatusData.map((e, i) => (
                  <div key={e.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: CHART_PALETTE[i % CHART_PALETTE.length] }} />
                      <span className="text-foreground/60 capitalize">{e.name}</span>
                    </div>
                    <span className="font-semibold tabular-nums">{e.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-40 text-foreground/40 text-xs">Belum ada data</div>
          )}
        </ChartCard>
      </div>

      {/* ── Charts ── */}
      <ChartCard title="Throughput Produksi (Mingguan)" subtitle="Total output per minggu">
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer>
            <BarChart data={weeklyTP} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 4" stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} stroke="var(--chart-grid)" />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} stroke="var(--chart-grid)" width={40} />
              <Tooltip content={<GlassTooltip formatter={(v) => `${fmtNum(v)} pcs`} />} cursor={{ fill: 'var(--glass-bg-hover)' }} />
              <Bar dataKey="qty" name="Produksi" fill={CHART_PALETTE[0]} radius={[6, 6, 0, 0]} maxBarSize={44} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* Production trend 6 month */}
      <ChartCard title="Tren Produksi 6 Bulan" subtitle="Perbandingan jumlah PO dan output produksi">
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer>
            <AreaChart data={metrics?.monthlyData || []} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="mgmtProd" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CHART_PALETTE[0]} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={CHART_PALETTE[0]} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 4" stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} stroke="var(--chart-grid)" />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} stroke="var(--chart-grid)" width={40} />
              <Tooltip content={<GlassTooltip />} cursor={{ fill: 'var(--glass-bg-hover)' }} />
              <Bar dataKey="pos" name="PO" fill={CHART_PALETTE[1]} radius={[3, 3, 0, 0]} maxBarSize={28} />
              <Area type="monotone" dataKey="production" name="Produksi" stroke={CHART_PALETTE[0]} strokeWidth={2.5} fill="url(#mgmtProd)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    </div>
  );
}
