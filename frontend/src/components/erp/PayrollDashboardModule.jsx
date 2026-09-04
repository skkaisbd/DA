/**
 * PayrollDashboardModule — Phase 3 P1
 *
 * Dashboard otomasi payroll:
 * - KPI snapshot (runs, disbursed, coverage)
 * - Alerts (missing profiles, stale drafts)
 * - Manual trigger dengan date range
 * - Attendance sync preview
 * - Run history timeline
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  DollarSign, Users, AlertTriangle, CheckCircle2,
  RefreshCw, Play, Calendar, Clock, XCircle,
  ChevronRight, Info, Zap, BarChart3,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '../ui/dialog';
import { useToast } from '../../hooks/use-toast';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL || '';
const FMT_IDR = v => `Rp ${(+v || 0).toLocaleString('id-ID')}`;

const STATUS_CFG = {
  draft:     { color: 'text-amber-700 dark:text-amber-400',   bg: 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30',   label: 'Draft' },
  finalized: { color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30', label: 'Final' },
  paid:      { color: 'text-blue-600 dark:text-blue-400',    bg: 'bg-blue-100 dark:bg-blue-500/10 border-blue-400 dark:border-blue-500/30',       label: 'Paid' },
  void:      { color: 'text-muted-foreground dark:text-zinc-500',    bg: 'bg-muted-foreground/30 border-border/30',       label: 'Void' },
};

const SEVERITY_CFG = {
  warning: { color: 'text-amber-700 dark:text-amber-400', bg: 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30', Icon: AlertTriangle },
  info:    { color: 'text-blue-600 dark:text-blue-400',  bg: 'bg-blue-100 dark:bg-blue-500/10 border-blue-400 dark:border-blue-500/30',   Icon: Info },
  error:   { color: 'text-red-700 dark:text-red-400',   bg: 'bg-red-100 dark:bg-red-500/10 border-red-400 dark:border-red-500/30',     Icon: XCircle },
};

export default function PayrollDashboardModule({ user, headers }) {
  const [dashboard, setDashboard] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  // Trigger modal
  const [showTrigger, setShowTrigger] = useState(false);
  const [triggerForm, setTriggerForm] = useState({
    period_from: '',
    period_to: '',
    notes: 'Auto-triggered via Payroll Dashboard',
  });
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState(null);

  const { toast } = useToast();
  const authH = useMemo(() => headers || {}, [headers]);

  // Auto-fill period_from/to to current month
  useEffect(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
    setTriggerForm(f => ({
      ...f,
      period_from: `${y}-${m}-01`,
      period_to: `${y}-${m}-${lastDay}`,
    }));
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, alertRes, histRes] = await Promise.all([
        axios.get(`${API}/api/payroll/automation/dashboard`, { headers: authH }),
        axios.get(`${API}/api/payroll/automation/alerts`, { headers: authH }),
        axios.get(`${API}/api/payroll/automation/history`, { headers: authH, params: { limit: 12 } }),
      ]);
      setDashboard(dashRes.data);
      setAlerts(alertRes.data?.data || []);
      setHistory(histRes.data?.data || []);
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal load data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [authH, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleTrigger = async () => {
    if (!triggerForm.period_from || !triggerForm.period_to) {
      toast({ title: 'Error', description: 'Periode harus diisi', variant: 'destructive' });
      return;
    }
    setTriggering(true);
    setTriggerResult(null);
    try {
      const res = await axios.post(`${API}/api/payroll/automation/trigger`, triggerForm, { headers: authH });
      setTriggerResult(res.data);
      toast({ title: 'Berhasil', description: `Payroll run ${res.data.run_number || ''} dibuat.` });
      fetchAll();
    } catch (e) {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Gagal trigger', variant: 'destructive' });
    } finally {
      setTriggering(false);
    }
  };

  const d = dashboard || {};
  const runSummary = d.run_summary || {};
  const coverage = d.employee_profile_coverage || {};
  const schedule = d.automation_schedule || {};

  const { page, setPage, totalPages, total, paged } = useClientPagination(history, 10);
  return (
    <div className="p-4 md:p-6 space-y-6 text-foreground">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <DollarSign className="text-emerald-600 dark:text-emerald-400" /> Payroll Automation Dashboard
          </h2>
          <p className="text-sm text-muted-foreground/60 dark:text-zinc-400 mt-1">Monitor dan kelola siklus penggajian otomatis</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => setShowTrigger(true)}
            className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
            data-testid="btn-trigger-payroll"
          >
            <Play className="w-4 h-4 mr-1" /> Jalankan Payroll
          </Button>
          <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}
            className="border-border text-foreground/80 hover:bg-muted" data-testid="btn-refresh-payroll">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a, i) => {
            const cfg = SEVERITY_CFG[a.severity] || SEVERITY_CFG.info;
            return (
              <div key={i} className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${cfg.bg}`}>
                <cfg.Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cfg.color}`} />
                <div>
                  <p className={`text-sm font-medium ${cfg.color}`}>{a.message}</p>
                  <p className="text-xs text-muted-foreground/60 dark:text-zinc-400 mt-0.5">{a.action}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Disbursed YTD</div>
            <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
              {loading ? '…' : FMT_IDR(d.total_disbursed_ytd)}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500">tahun ini</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Draft Runs</div>
            <div className="text-xl font-bold text-amber-700 dark:text-amber-400">
              {loading ? '…' : (runSummary.draft?.count ?? 0)}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500">
              {FMT_IDR(runSummary.draft?.total_net_rp)} pending
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Finalized</div>
            <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
              {loading ? '…' : (runSummary.finalized?.count ?? 0)}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500">
              {FMT_IDR(runSummary.finalized?.total_net_rp)}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1">Profile Coverage</div>
            <div className="text-xl font-bold text-foreground">
              {loading ? '…' : `${coverage.coverage_pct ?? 0}%`}
            </div>
            <div className="text-xs text-muted-foreground/60 dark:text-zinc-500">
              {coverage.with_payroll_profile ?? 0}/{coverage.total_active_employees ?? 0} karyawan aktif
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Latest Run + Schedule */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Latest Run */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80">Run Terakhir</CardTitle>
          </CardHeader>
          <CardContent>
            {!d.latest_run ? (
              <p className="text-muted-foreground/60 dark:text-zinc-500 text-sm">Belum ada payroll run</p>
            ) : (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60 dark:text-zinc-400">Run #:</span>
                  <span className="font-mono text-foreground">{d.latest_run.run_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60 dark:text-zinc-400">Periode:</span>
                  <span className="text-foreground">{d.latest_run.period?.from} s/d {d.latest_run.period?.to}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60 dark:text-zinc-400">Status:</span>
                  <span className={STATUS_CFG[d.latest_run.status]?.color || 'text-foreground/80'}>
                    {STATUS_CFG[d.latest_run.status]?.label || d.latest_run.status}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60 dark:text-zinc-400">Karyawan:</span>
                  <span className="text-foreground">{d.latest_run.employee_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground/60 dark:text-zinc-400">Net Pay:</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium">{FMT_IDR(d.latest_run.total_net_pay)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Schedule Config */}
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-blue-600 dark:text-blue-400" /> Jadwal Auto-Run
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground/60 dark:text-zinc-400">Status:</span>
                <Badge variant="outline" className={schedule.enabled ? 'text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30' : 'text-muted-foreground/60 dark:text-zinc-500 border-border'}>
                  {schedule.enabled ? 'Aktif' : 'Non-aktif'}
                </Badge>
              </div>
              {schedule.enabled && (
                <>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">Trigger tanggal:</span>
                    <span className="text-foreground">{schedule.run_day_of_month || '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground/60 dark:text-zinc-400">Auto-finalize:</span>
                    <span className="text-foreground">{schedule.auto_finalize ? 'Ya' : 'Tidak'}</span>
                  </div>
                </>
              )}
              {!schedule.enabled && (
                <p className="text-xs text-muted-foreground/60">Konfigurasi jadwal di Settings untuk aktifkan auto-run bulanan.</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Run History */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-foreground/80 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-purple-600 dark:text-purple-400" /> Riwayat Payroll Run (12 terakhir)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {history.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground/60 dark:text-zinc-500 text-sm">
              Belum ada riwayat run
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground/60 dark:text-zinc-400">
                    <th className="text-left px-4 py-2">Run #</th>
                    <th className="text-left px-4 py-2">Periode</th>
                    <th className="text-left px-4 py-2">Status</th>
                    <th className="text-right px-4 py-2">Karyawan</th>
                    <th className="text-right px-4 py-2">Net Pay</th>
                    <th className="text-right px-4 py-2">Dibuat</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map(r => {
                    const sc = STATUS_CFG[r.status] || STATUS_CFG.draft;
                    return (
                      <tr key={r.id} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="px-4 py-2 font-mono text-xs text-foreground/80">{r.run_number}</td>
                        <td className="px-4 py-2 text-muted-foreground/60 dark:text-zinc-400 text-xs">
                          {r.period?.from} s/d {r.period?.to}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded border ${sc.bg} ${sc.color}`}>{sc.label}</span>
                        </td>
                        <td className="px-4 py-2 text-right text-muted-foreground/60 dark:text-zinc-400">{r.employee_count || '—'}</td>
                        <td className="px-4 py-2 text-right text-emerald-600 dark:text-emerald-400">{FMT_IDR(r.total_net_pay)}</td>
                        <td className="px-4 py-2 text-right text-muted-foreground/60 dark:text-zinc-500 text-xs">
                          {r.created_at ? new Date(r.created_at).toLocaleDateString('id-ID') : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Trigger Modal */}
      <Dialog open={showTrigger} onOpenChange={setShowTrigger}>
        <DialogContent className="bg-card border-border max-w-md">
          <DialogHeader>
            <DialogTitle className="text-foreground">Jalankan Payroll Run</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {triggerResult ? (
              <div className={`rounded-lg p-4 border ${
                triggerResult.status === 'created'
                  ? 'bg-emerald-100 dark:bg-emerald-500/10 border-emerald-400 dark:border-emerald-500/30'
                  : 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30'
              }`}>
                <p className={`font-medium text-sm mb-2 ${
                  triggerResult.status === 'created' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'
                }`}>
                  {triggerResult.status === 'created' ? '✅ Run berhasil dibuat!' : '⚠ Run sudah ada'}
                </p>
                <div className="text-xs text-foreground/80 space-y-1">
                  <div>Run #: <span className="font-mono">{triggerResult.run_number || triggerResult.run?.run_number || '—'}</span></div>
                  <div>Karyawan: <span className="text-foreground">{triggerResult.employee_count || '—'}</span></div>
                  {triggerResult.next_step && <p className="text-muted-foreground/60 dark:text-zinc-400 mt-1">{triggerResult.next_step}</p>}
                </div>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Periode Dari</label>
                    <Input
                      type="date"
                      value={triggerForm.period_from}
                      onChange={e => setTriggerForm(f => ({ ...f, period_from: e.target.value }))}
                      className="bg-muted border-border text-sm"
                      data-testid="input-period-from"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Periode Sampai</label>
                    <Input
                      type="date"
                      value={triggerForm.period_to}
                      onChange={e => setTriggerForm(f => ({ ...f, period_to: e.target.value }))}
                      className="bg-muted border-border text-sm"
                      data-testid="input-period-to"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground/60 dark:text-zinc-400 mb-1 block">Catatan</label>
                  <Input
                    value={triggerForm.notes}
                    onChange={e => setTriggerForm(f => ({ ...f, notes: e.target.value }))}
                    className="bg-muted border-border text-sm"
                    placeholder="Catatan optional"
                  />
                </div>
              </>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setShowTrigger(false); setTriggerResult(null); }}>Tutup</Button>
              {!triggerResult && (
                <Button
                  onClick={handleTrigger}
                  disabled={triggering}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid="btn-confirm-trigger"
                >
                  {triggering ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Play className="w-4 h-4 mr-1" />}
                  Jalankan
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
