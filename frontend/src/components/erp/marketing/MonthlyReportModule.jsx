/**
 * MonthlyReportModule — Laporan Bulanan PIC Portal Marketing
 * Target vs actual per akun, task completion, sales input rate.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart3, RefreshCw, TrendingUp,
  ChevronLeft, ChevronRight, Loader2, Target, ClipboardList,
  CheckCircle2, AlertTriangle, FileDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { AccountBadge } from './AccountBadge';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const MONTH_NAMES = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
const fmtRp = formatRupiah;
const fmtCompact = (n) => {
  if (!n) return 'Rp 0';
  if (n >= 1e9) return `Rp ${(n/1e9).toFixed(1)}M`;
  if (n >= 1e6) return `Rp ${(n/1e6).toFixed(1)}jt`;
  if (n >= 1e3) return `Rp ${(n/1e3).toFixed(0)}rb`;
  return `Rp ${n}`;
};
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(n || 0);

const STATUS_CONFIG = {
  on_track:  { label: 'On Track', cls: 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 border-emerald-400 dark:border-emerald-500/30', bar: 'bg-emerald-500' },
  warning:   { label: 'Warning',  cls: 'bg-amber-100 dark:bg-amber-500/10  text-amber-600  border-amber-400 dark:border-amber-500/30',  bar: 'bg-amber-500'  },
  behind:    { label: 'Behind',   cls: 'bg-red-100 dark:bg-red-500/10    text-red-600    border-red-400 dark:border-red-500/30',    bar: 'bg-red-500'    },
  no_target: { label: '—',        cls: 'bg-muted/30 text-muted-foreground',                      bar: 'bg-muted'      },
};

function AchievementCell({ actual, target, pct, status, fmt = fmtCompact }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.no_target;
  return (
    <div className="text-right">
      <div className="text-sm font-semibold">{fmt(actual)}</div>
      {target != null && target > 0 ? (
        <>
          <div className="text-[10px] text-muted-foreground">/ {fmt(target)}</div>
          <div className="h-1 bg-muted rounded-full mt-0.5 overflow-hidden w-20 ml-auto">
            <div className={`h-full ${cfg.bar} transition-all`} style={{ width: `${Math.min(pct || 0, 100)}%` }} />
          </div>
          <Badge variant="outline" className={`text-[10px] mt-1 ${cfg.cls}`}>{pct}%</Badge>
        </>
      ) : (
        <Badge variant="outline" className="text-[10px] text-muted-foreground">Belum set</Badge>
      )}
    </div>
  );
}

function SummaryKpi({ label, value, sub, icon: Icon, color }) {
  return (
    <GlassPanel className="p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon size={14} className={color || 'text-primary'} />}
      </div>
      <p className={`text-xl font-bold ${color || ''}`}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </GlassPanel>
  );
}

export default function MonthlyReportModule({ token }) {
  const now = new Date();
  const [year, setYear]     = useState(now.getFullYear());
  const [month, setMonth]   = useState(now.getMonth() + 1);
  const [report, setReport] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [exporting, setExporting] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  const authH = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/reports/monthly?year=${year}&month=${month}`, { headers: authH });
      if (!res.ok) throw new Error('Gagal memuat laporan');
      setReport(await res.json());
    } catch (e) { toast.error(e.message); }
    finally { setLoading(false); }
  }, [year, month, token]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  const handleExportPDF = async () => {
    setExporting(true);
    try {
      const res = await fetch(
        `${API}/api/marketing/reports/monthly/export-pdf?year=${year}&month=${month}`,
        { headers: authH }
      );
      if (!res.ok) throw new Error('Gagal generate PDF');
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `laporan-marketing-${MONTH_NAMES[month-1].toLowerCase()}-${year}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF berhasil didownload');
    } catch (e) { toast.error(e.message); }
    finally { setExporting(false); }
  };

  const s = report?.summary || {};

  return (
    <div className="space-y-5 p-4 lg:p-6" data-testid="monthly-report-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 size={22} className="text-primary" /> Laporan Bulanan
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Target vs aktual per akun — {MONTH_NAMES[month - 1]} {year}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prevMonth}><ChevronLeft size={14} /></Button>
          <span className="font-semibold text-sm min-w-[130px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <Button variant="outline" size="sm" onClick={nextMonth}><ChevronRight size={14} /></Button>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleExportPDF}
            disabled={exporting || loading}
            data-testid="export-pdf-btn"
            className="gap-1.5"
          >
            {exporting
              ? <Loader2 size={13} className="animate-spin" />
              : <FileDown size={13} />
            }
            Export PDF
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 size={28} className="animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <SummaryKpi label="Total Akun" value={s.total_accounts || 0} icon={Target} />
            <SummaryKpi label="Revenue Actual" value={fmtCompact(s.rev_actual)}
              sub={s.rev_target > 0 ? `Target: ${fmtCompact(s.rev_target)}` : 'Belum ada target'}
              icon={TrendingUp} color={s.rev_pct >= 90 ? 'text-emerald-600' : s.rev_pct >= 70 ? 'text-amber-600' : s.rev_actual > 0 ? 'text-red-600' : ''} />
            <SummaryKpi label="Pencapaian Revenue"
              value={s.rev_pct != null ? `${s.rev_pct}%` : '—'}
              sub={s.rev_pct >= 90 ? 'On Track ✅' : s.rev_pct >= 70 ? 'Perlu usaha' : s.rev_pct != null ? 'Jauh dari target' : 'Set target dulu'}
              icon={s.rev_pct >= 90 ? CheckCircle2 : s.rev_pct >= 70 ? TrendingUp : AlertTriangle}
              color={s.rev_pct >= 90 ? 'text-emerald-600' : s.rev_pct >= 70 ? 'text-amber-600' : s.rev_pct != null ? 'text-red-600' : 'text-muted-foreground'} />
            <SummaryKpi label="Orders Actual" value={fmtNum(s.ord_actual)}
              sub={s.ord_target > 0 ? `Target: ${fmtNum(s.ord_target)}` : '—'} icon={BarChart3} />
            <SummaryKpi label="Task Completion"
              value={s.task_completion != null ? `${s.task_completion}%` : '—'}
              icon={ClipboardList}
              color={s.task_completion >= 80 ? 'text-emerald-600' : s.task_completion >= 60 ? 'text-amber-600' : 'text-red-600'} />
            <SummaryKpi label="Sales Input Rate"
              value={s.avg_sales_input_rate != null ? `${s.avg_sales_input_rate}%` : '—'}
              sub="rata-rata per akun"
              icon={CheckCircle2}
              color={s.avg_sales_input_rate >= 80 ? 'text-emerald-600' : 'text-amber-600'} />
          </div>

          {/* Per Account Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Detail per Akun</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {!report?.accounts?.length ? (
                <div className="py-10 text-center text-muted-foreground text-sm">Belum ada akun aktif</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="monthly-report-table">
                    <thead>
                      <tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                        <th className="px-4 py-2.5 text-left">Akun</th>
                        <th className="px-4 py-2.5 text-right">Revenue</th>
                        <th className="px-4 py-2.5 text-right">Orders</th>
                        <th className="px-4 py-2.5 text-right">Sales Input</th>
                        <th className="px-4 py-2.5 text-right">Task</th>
                        <th className="px-4 py-2.5 text-right">Health</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {report.accounts.map(row => (
                      <React.Fragment key={row.account_id}>
                          <tr
                            key={row.account_id}
                            className="hover:bg-muted/20 cursor-pointer"
                            data-testid={`monthly-row-${row.account_code}`}
                            onClick={() => setExpandedRow(expandedRow === row.account_id ? null : row.account_id)}
                          >
                            <td className="px-4 py-3">
                              <AccountBadge account={row} size="sm" />
                            </td>
                            <td className="px-4 py-3">
                              <AchievementCell
                                actual={row.actual.revenue}
                                target={row.target.revenue}
                                pct={row.achievement.revenue_pct}
                                status={row.achievement.revenue_status}
                                fmt={fmtCompact}
                              />
                            </td>
                            <td className="px-4 py-3">
                              <AchievementCell
                                actual={row.actual.orders}
                                target={row.target.orders}
                                pct={row.achievement.orders_pct}
                                status={row.achievement.orders_status}
                                fmt={fmtNum}
                              />
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="text-sm font-semibold">{row.actual.sales_days} hari</div>
                              <div className={`text-xs ${row.actual.input_rate >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                                {row.actual.input_rate}% input rate
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="text-sm font-semibold">{row.task_stats.done}/{row.task_stats.total}</div>
                              {row.task_stats.completion_rate != null && (
                                <div className={`text-xs ${row.task_stats.completion_rate >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>
                                  {row.task_stats.completion_rate}%
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={`text-sm font-bold ${row.health_score >= 80 ? 'text-emerald-600' : row.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                                {row.health_score ?? 'N/A'}
                              </span>
                            </td>
                          </tr>
                          {/* Expanded: daily chart mini */}
                          {expandedRow === row.account_id && row.daily_chart?.length > 0 && (
                            <tr key={`${row.account_id}-detail`}>
                              <td colSpan={6} className="px-4 py-3 bg-muted/10 border-b">
                                <p className="text-xs text-muted-foreground mb-2">Revenue harian — {row.account_name}</p>
                                <div className="flex items-end gap-1 h-12">
                                  {row.daily_chart.map((d, i) => {
                                    const max = Math.max(...row.daily_chart.map(x => x.revenue), 1);
                                    const h = Math.round((d.revenue / max) * 100);
                                    return (
                                      <div key={i} className="flex flex-col items-center gap-0.5 flex-1 min-w-[4px]">
                                        <div
                                          className="w-full rounded-t bg-primary/60"
                                          style={{ height: `${h}%`, minHeight: d.revenue > 0 ? '2px' : '0' }}
                                          title={`${d.date}: ${fmtRp(d.revenue)}`}
                                        />
                                      </div>
                                    );
                                  })}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
