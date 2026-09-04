import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, Calendar, Clock, BookOpen, CheckSquare, Bell, User, AlertCircle, Banknote, Target } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n || 0);
}

function fmtShort(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}jt`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}rb`;
  return String(n || 0);
}

function StatCard({ icon: Icon, title, value, sub, color = 'blue', badge, onClick }) {
  const colorMap = {
    blue:   { bg: 'bg-blue-50 dark:bg-blue-950', icon: 'text-blue-600 dark:text-blue-400', border: 'border-blue-100 dark:border-blue-800' },
    green:  { bg: 'bg-green-50 dark:bg-green-950', icon: 'text-green-600 dark:text-green-400', border: 'border-green-100 dark:border-green-800' },
    purple: { bg: 'bg-purple-50 dark:bg-purple-950', icon: 'text-purple-600 dark:text-purple-400', border: 'border-purple-100 dark:border-purple-800' },
    amber:  { bg: 'bg-amber-50 dark:bg-amber-950', icon: 'text-amber-600 dark:text-amber-400', border: 'border-amber-100 dark:border-amber-800' },
    red:    { bg: 'bg-red-50 dark:bg-red-950', icon: 'text-red-600 dark:text-red-400', border: 'border-red-100 dark:border-red-800' },
    indigo: { bg: 'bg-indigo-50 dark:bg-indigo-950', icon: 'text-indigo-600 dark:text-indigo-400', border: 'border-indigo-100 dark:border-indigo-800' },
  };
  const c = colorMap[color] || colorMap.blue;
  return (
    <Card
      className={`transition-shadow ${onClick ? 'cursor-pointer hover:shadow-md active:scale-[0.98]' : 'hover:shadow-md'} transition-all duration-150`}
      onClick={onClick}
    >
      <CardContent className="pt-4 pb-4 px-4">
        <div className="flex items-start justify-between mb-2">
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${c.bg} ${c.border}`}>
            <Icon className={`w-4.5 h-4.5 ${c.icon}`} />
          </div>
          {badge && <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5">{badge}</Badge>}
        </div>
        {/* Mobile: compact value + title */}
        <p className="text-xl sm:text-2xl font-bold leading-tight">{value}</p>
        <p className="text-xs sm:text-sm font-medium text-foreground mt-0.5 leading-snug">{title}</p>
        {sub && <p className="text-[10px] sm:text-xs text-muted-foreground mt-1 leading-snug">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function PortalSayaDashboard({ user, headers, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/api/portal/dashboard`, { headers });
      setData(d);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
    </div>
  );

  if (!data) return (
    <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
      <AlertCircle className="w-10 h-10 mb-2 opacity-30" />
      <p className="text-sm">Gagal memuat dashboard. Coba refresh.</p>
    </div>
  );

  const mainLeave = data.leave_balance?.[0];
  const att = data.absensi_bulan_ini || {};
  const training = data.training_stats || {};
  const kpi = data.kpi_score;
  const todos = data.todos || {};

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-5xl mx-auto pb-20 md:pb-6">
      {/* ─── Header / Greeting ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <User className="w-5 h-5 sm:w-6 sm:h-6 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-lg sm:text-xl font-bold truncate">Selamat Datang, {user?.name?.split(' ')[0] || 'Karyawan'}!</h1>
          <p className="text-xs sm:text-sm text-muted-foreground truncate">
            {data.job_title || user?.role}{data.employee_code ? ` · ${data.employee_code}` : ''}
          </p>
        </div>
        {!data.is_linked && (
          <Badge variant="outline" className="shrink-0 text-amber-600 border-amber-300 bg-amber-50 text-[10px] sm:text-xs">
            <AlertCircle className="w-3 h-3 mr-1" />
            <span className="hidden sm:inline">Belum Terhubung ke Data Karyawan</span>
            <span className="sm:hidden">Belum Terhubung</span>
          </Badge>
        )}
      </div>

      {/* ─── Stat Grid ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <StatCard
          icon={Calendar}
          title="Sisa Cuti"
          value={mainLeave ? `${mainLeave.remaining} hari` : '-'}
          sub={mainLeave ? `Terpakai ${mainLeave.used}/${mainLeave.quota}` : 'Belum ada data'}
          color="green"
          badge={data.pending_leave > 0 ? `${data.pending_leave}` : undefined}
          onClick={() => onNavigate?.('portal-cuti')}
        />
        <StatCard
          icon={Banknote}
          title="Take Home Pay"
          value={data.last_payslip ? fmtShort(data.last_payslip.net_pay) : '-'}
          sub={data.last_payslip ? `${data.last_payslip.period}` : 'Belum ada payslip'}
          color="blue"
          onClick={() => onNavigate?.('portal-payslip')}
        />
        <StatCard
          icon={Clock}
          title="Hadir Bulan Ini"
          value={att.hadir ?? '-'}
          sub={`I:${att.izin ?? 0} · S:${att.sakit ?? 0} · α:${att.alfa ?? 0}`}
          color="indigo"
          onClick={() => onNavigate?.('self-dashboard')}
        />
        <StatCard
          icon={BookOpen}
          title="Training"
          value={`${training.completed ?? 0}/${training.enrolled ?? 0}`}
          sub={`${training.pct ?? 0}% selesai`}
          color="purple"
          onClick={() => onNavigate?.('portal-training')}
        />
        {kpi && (
          <StatCard
            icon={Target}
            title="Skor KPI"
            value={kpi.score}
            sub={`Grade ${kpi.grade} · ${kpi.period}`}
            color="green"
            onClick={() => onNavigate?.('kpi-portal')}
          />
        )}
        <StatCard
          icon={CheckSquare}
          title="Todo Saya"
          value={`${todos.done ?? 0}/${todos.total ?? 0}`}
          sub={todos.overdue > 0 ? `${todos.overdue} overdue` : 'Semua selesai'}
          color={todos.overdue > 0 ? 'red' : 'blue'}
          badge={todos.overdue > 0 ? `${todos.overdue}!` : undefined}
        />
        {data.upcoming_reminders?.length > 0 && (
          <StatCard
            icon={Bell}
            title="Reminder"
            value={data.upcoming_reminders.length}
            sub={data.upcoming_reminders[0]?.title || ''}
            color="amber"
          />
        )}
      </div>

      {/* ─── Leave balance detail ─────────────────────────────────────────────── */}
      {data.leave_balance?.length > 1 && (
        <Card>
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-semibold">Saldo Cuti Tahun Ini</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
              {data.leave_balance.map((lb, i) => (
                <div key={i} className="bg-muted/50 rounded-lg p-2.5 sm:p-3">
                  <p className="text-[10px] sm:text-xs text-muted-foreground truncate">{lb.type_name}</p>
                  <div className="flex items-end gap-1 mt-1">
                    <span className="text-lg sm:text-xl font-bold text-primary">{lb.remaining}</span>
                    <span className="text-[10px] text-muted-foreground mb-0.5">/ {lb.quota} hari</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5 mt-1.5">
                    <div
                      className="bg-primary h-1.5 rounded-full transition-all"
                      style={{ width: `${lb.quota ? Math.min(100, lb.used / lb.quota * 100) : 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ─── Upcoming Reminders ────────────────────────────────────────────── */}
      {data.upcoming_reminders?.length > 0 && (
        <Card>
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Bell className="w-4 h-4 text-amber-500" /> Reminder Mendatang
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            {data.upcoming_reminders.slice(0, 5).map((r, i) => (
              <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900">
                <div className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs sm:text-sm font-medium truncate">{r.title}</p>
                  <p className="text-[10px] text-muted-foreground">{r.remind_at?.slice(0, 16).replace('T', ' ')}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* ─── Quick Actions (Mobile-focused) ───────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2 px-4 pt-4">
          <CardTitle className="text-sm font-semibold">Aksi Cepat</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {[
              { id: 'portal-cuti',      label: 'Ajukan Cuti',   icon: Calendar, color: 'text-green-600' },
              { id: 'portal-payslip',   label: 'Slip Gaji',     icon: Banknote, color: 'text-blue-600' },
              { id: 'kpi-portal',       label: 'KPI Saya',      icon: Target, color: 'text-emerald-600' },
              { id: 'portal-training',  label: 'Training',      icon: BookOpen, color: 'text-purple-600' },
              { id: 'portal-notifikasi', label: 'Notifikasi',   icon: Bell, color: 'text-amber-600' },
              { id: 'portal-profile',   label: 'Profil Saya',  icon: TrendingUp, color: 'text-indigo-600' },
            ].map(({ id, label, icon: Icon, color }) => (
              <button
                key={id}
                onClick={() => onNavigate?.(id)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-muted/50 hover:bg-muted/80 active:scale-95 transition-all duration-150 touch-manipulation"
                data-testid={`quick-action-${id}`}
              >
                <Icon className={`w-5 h-5 ${color}`} />
                <span className="text-[10px] text-center text-foreground/70 leading-tight">{label}</span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
