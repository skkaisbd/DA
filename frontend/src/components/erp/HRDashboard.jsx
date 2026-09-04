import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import {
  Users, CalendarCheck, AlertTriangle, Banknote, TrendingUp,
  Clock, UserCheck, UserX, Coffee, Plane, Sun, HelpCircle, RefreshCw
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { IconButton } from './IconButton';
import { EmptyState } from './EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRupiah } from '@/lib/format';

const fmtCurrency = formatRupiah;
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';

const STATUS_COLOR = { hadir: '#10b981', izin: '#f59e0b', sakit: '#3b82f6', alfa: '#ef4444', cuti: '#8b5cf6', libur: '#64748b' };
const STATUS_ICON  = { hadir: UserCheck, izin: Coffee, sakit: HelpCircle, alfa: UserX, cuti: Plane, libur: Sun };
const STATUS_LABEL = { hadir: 'Hadir', izin: 'Izin', sakit: 'Sakit', alfa: 'Alfa', cuti: 'Cuti', libur: 'Libur' };

function KpiTile({ icon: Icon, label, value, sub, color, accent }) {
  return (
    <GlassCard hover={false} className="p-5 flex items-start gap-4">
      <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0`} style={{ background: `${color}20`, border: `1px solid ${color}35` }}>
        <Icon className="w-6 h-6" style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
        <p className="text-2xl font-bold text-foreground leading-none">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </div>
    </GlassCard>
  );
}

function AttBreakdownBar({ data, total }) {
  const keys = ['hadir', 'izin', 'sakit', 'alfa', 'cuti', 'libur'];
  return (
    <div className="space-y-2">
      {keys.map(k => {
        const val = data[k] || 0;
        const pct = total > 0 ? Math.round((val / total) * 100) : 0;
        const Icon = STATUS_ICON[k] || HelpCircle;
        return (
          <div key={k} className="flex items-center gap-3">
            <div className="flex items-center gap-2 w-24 shrink-0">
              <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: STATUS_COLOR[k] }} />
              <span className="text-xs text-muted-foreground">{STATUS_LABEL[k]}</span>
            </div>
            <div className="flex-1 h-2 rounded-full bg-[var(--glass-border)] overflow-hidden">
              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: STATUS_COLOR[k] }} />
            </div>
            <span className="text-xs font-mono font-medium text-foreground w-7 text-right">{val}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function HRDashboard({ token }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const fetchDashboard = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/rahaza/hr/dashboard`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  if (loading) return (
    <div className="space-y-4 p-2" data-testid="hr-dashboard-skeleton">
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Skeleton className="col-span-2 h-52 rounded-xl" />
        <Skeleton className="h-52 rounded-xl" />
      </div>
      <Skeleton className="h-40 rounded-xl" />
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <AlertTriangle className="w-10 h-10 text-amber-400" />
      <p className="text-sm text-muted-foreground">Gagal memuat dashboard: {error}</p>
      <button onClick={fetchDashboard} className="text-xs text-primary hover:brightness-110">Coba lagi</button>
    </div>
  );

  const att = data?.attendance_today || {};
  const total = data?.total_employees || 0;
  const run   = data?.latest_payroll_run;

  return (
    <div className="space-y-6" data-testid="hr-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard SDM</h1>
          <p className="text-muted-foreground text-sm">
            {new Date().toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <IconButton label="Refresh dashboard" onClick={fetchDashboard} data-testid="hr-dashboard-refresh">
          <RefreshCw className="w-4 h-4 text-muted-foreground" />
        </IconButton>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          icon={Users} label="Total Karyawan Aktif"
          value={total}
          sub="karyawan terdaftar"
          color="#6366f1"
        />
        <KpiTile
          icon={UserCheck} label="Hadir Hari Ini"
          value={att.hadir || 0}
          sub={`${att.attendance_rate || 0}% attendance rate`}
          color="#10b981"
        />
        <KpiTile
          icon={HelpCircle} label="Belum Absen"
          value={att.not_recorded || 0}
          sub="dari total karyawan aktif"
          color="#f59e0b"
        />
        <KpiTile
          icon={AlertTriangle} label="Alfa (7 hari)"
          value={data?.alfa_last_7d || 0}
          sub="hari kerja tidak hadir"
          color="#ef4444"
        />
      </div>

      {/* Main content: Attendance breakdown + Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Attendance Today breakdown */}
        <GlassCard hover={false} className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <CalendarCheck className="w-4 h-4 text-primary" /> Kehadiran Hari Ini
            </h2>
            <span className="text-xs text-muted-foreground">{att.recorded || 0} / {total} dicatat</span>
          </div>
          <AttBreakdownBar data={att} total={total} />
          {att.not_recorded > 0 && (
            <p className="mt-3 text-xs text-amber-400 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              {att.not_recorded} karyawan belum dicatat kehadirannya hari ini
            </p>
          )}
        </GlassCard>

        {/* Trend 7 hari */}
        <GlassCard hover={false} className="p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-primary" /> Tren Kehadiran (7 Hari)
          </h2>
          {(data?.attendance_trend || []).length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={data.attendance_trend} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
                  tickFormatter={d => d ? d.slice(5) : ''} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }} />
                <Tooltip
                  contentStyle={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: '12px', fontSize: 12 }}
                  labelStyle={{ color: 'var(--muted-foreground)' }}
                />
                <Bar dataKey="hadir" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center">
              <p className="text-sm text-muted-foreground">Belum ada data absensi 7 hari terakhir</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Payroll Run Terbaru */}
      {run && (
        <GlassCard hover={false} className="p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Banknote className="w-4 h-4 text-primary" /> Payroll Run Terbaru
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Periode</p>
              <p className="text-sm font-medium text-foreground">
                {fmtDate(run.period_from)} — {fmtDate(run.period_to)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                run.status === 'finalized' ? 'bg-emerald-400/15 text-emerald-400 border border-emerald-400/20'
                : 'bg-amber-400/15 text-amber-400 border border-amber-400/20'
              }`}>{run.status}</span>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Total Payout</p>
              <p className="text-sm font-bold text-foreground">{fmtCurrency(run.total_net ?? run.total_payout)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Jumlah Karyawan</p>
              <p className="text-sm font-medium text-foreground">{run.total_employees ?? run.employee_count ?? '-'}</p>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Recent Attendance */}
      {(data?.recent_attendance || []).length > 0 && (
        <GlassCard hover={false} className="p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-primary" /> Kehadiran Terbaru
          </h2>
          <div className="space-y-2">
            {data.recent_attendance.map((r, i) => {
              const Icon = STATUS_ICON[r.status] || HelpCircle;
              return (
                <div key={i} className="flex items-center justify-between py-2 border-b border-[var(--glass-border)] last:border-0">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${STATUS_COLOR[r.status] || '#64748b'}18` }}>
                      <Icon className="w-4 h-4" style={{ color: STATUS_COLOR[r.status] || '#64748b' }} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{r.employee_name}</p>
                      <p className="text-xs text-muted-foreground">{r.date}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-medium" style={{ color: STATUS_COLOR[r.status] || '#64748b' }}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                    {r.hours_worked > 0 && (
                      <p className="text-xs text-muted-foreground">{r.hours_worked}j</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}

      {/* Dept breakdown */}
      {(data?.dept_breakdown || []).length > 0 && (
        <GlassCard hover={false} className="p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" /> Sebaran Karyawan per Jabatan
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {data.dept_breakdown.map((d, i) => (
              <div key={i} className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                <p className="text-xl font-bold text-foreground">{d.count}</p>
                <p className="text-xs text-muted-foreground truncate">{d.dept || 'Lainnya'}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
