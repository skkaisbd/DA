import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  TrendingUp, Plus, RefreshCw, CheckCircle2, XCircle, Clock, AlertCircle,
  UserCheck, Banknote, Filter, Search, Eye, Loader2, Wand2, ChevronRight,
  FileText, Award, Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const fetchAPI = (path, opts = {}, token) =>
  fetch(`${API}/api/rahaza${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(opts.headers || {}),
    },
  });

// Status configuration
const STATUS_CFG = {
  pending_manager: {
    label: 'Menunggu Atasan',
    color: 'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400 dark:border-amber-500/30',
    icon: Clock,
  },
  pending_hr: {
    label: 'Menunggu HR',
    color: 'bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400 dark:border-blue-500/30',
    icon: Clock,
  },
  approved: {
    label: 'Disetujui',
    color: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400 dark:border-emerald-500/30',
    icon: CheckCircle2,
  },
  rejected: {
    label: 'Ditolak',
    color: 'bg-rose-100 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400 dark:border-rose-500/30',
    icon: XCircle,
  },
  cancelled: {
    label: 'Dibatalkan',
    color: 'bg-muted dark:bg-slate-500/15 text-foreground dark:text-foreground/70 border-border dark:border-slate-500/30',
    icon: XCircle,
  },
};

const TYPE_LABELS = {
  kpi_raise: 'KPI Auto-Raise',
  performance_raise: 'Performance Raise',
  promotion: 'Promosi',
  annual_increment: 'Kenaikan Tahunan',
  manual: 'Manual HR',
};

const fmtCurrency = (n) => {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n);
};

const fmtDate = (d) => {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
};

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.cancelled;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${cfg.color}`}
      data-testid={`adj-status-badge-${status}`}
    >
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, suffix, color, testId }) {
  return (
    <Card className="border-border/50" data-testid={testId}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
            <p className="text-2xl font-bold tabular-nums">
              {value}
              {suffix && <span className="text-base font-normal text-muted-foreground ml-1">{suffix}</span>}
            </p>
          </div>
          <div className={`p-2 rounded-lg ${color}`}>
            <Icon className="w-5 h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function RahazaSalaryAdjustmentModule({ token, user }) {
  const [adjustments, setAdjustments] = useState([]);
  const [stats, setStats] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [payrollProfiles, setPayrollProfiles] = useState({});
  const [kpiPeriods, setKpiPeriods] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [search, setSearch] = useState('');

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [actionDialog, setActionDialog] = useState(null); // { type: 'approve_manager' | 'approve_hr' | 'reject' | 'cancel', adj }

  const userRole = useMemo(() => (user?.role || '').toLowerCase(), [user]);
  const isHR = ['superadmin', 'admin', 'owner', 'hr'].includes(userRole);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [adjRes, statsRes, empsRes, periodsRes] = await Promise.all([
        fetchAPI('/salary-adjustments', {}, token),
        fetchAPI('/salary-adjustments/stats/summary', {}, token),
        fetchAPI('/employees?limit=500', {}, token),
        fetch(`${API}/api/dewi/kpi/periods`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const adjs = adjRes.ok ? await adjRes.json() : [];
      const st = statsRes.ok ? await statsRes.json() : null;
      const emps = empsRes.ok ? await empsRes.json() : [];
      const periods = periodsRes.ok ? await periodsRes.json() : [];

      setAdjustments(Array.isArray(adjs) ? adjs : []);
      setStats(st);
      setEmployees(Array.isArray(emps) ? emps : []);
      setKpiPeriods(Array.isArray(periods) ? periods.filter(p => p.status === 'finalized') : []);
    } catch (e) {
      toast.error('Gagal memuat data: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Filtered list
  const filtered = useMemo(() => {
    return adjustments.filter((a) => {
      if (filterStatus !== 'all' && a.status !== filterStatus) return false;
      if (filterType !== 'all' && a.adjustment_type !== filterType) return false;
      if (search) {
        const s = search.toLowerCase();
        const text = `${a.employee_name || ''} ${a.employee_code || ''} ${a.department || ''} ${a.reason || ''}`.toLowerCase();
        if (!text.includes(s)) return false;
      }
      return true;
    });
  }, [adjustments, filterStatus, filterType, search]);

  return (
    <div className="space-y-5 p-4 md:p-6" data-testid="salary-adjustment-module">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="salary-adjustment-title">
            <TrendingUp className="w-6 h-6 text-primary" />
            Penyesuaian Gaji (Raise) — Dual Approval
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Workflow kenaikan gaji dengan persetujuan <strong>Atasan + HR</strong>. Auto-generate dari KPI Grade A/B atau buat manual.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            disabled={loading}
            data-testid="adj-refresh-btn"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            Refresh
          </Button>
          {isHR && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setGenerateOpen(true)}
                data-testid="adj-generate-from-kpi-btn"
              >
                <Wand2 className="w-4 h-4 mr-2" />
                Generate dari KPI
              </Button>
              <Button
                size="sm"
                onClick={() => setCreateOpen(true)}
                data-testid="adj-create-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Buat Usulan Manual
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="adj-stats-grid">
          <StatCard
            icon={Clock}
            label="Menunggu Atasan"
            value={stats.pending_manager}
            color="bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400"
            testId="stat-pending-manager"
          />
          <StatCard
            icon={Clock}
            label="Menunggu HR"
            value={stats.pending_hr}
            color="bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400"
            testId="stat-pending-hr"
          />
          <StatCard
            icon={CheckCircle2}
            label="Disetujui"
            value={stats.approved}
            color="bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            testId="stat-approved"
          />
          <StatCard
            icon={XCircle}
            label="Ditolak"
            value={stats.rejected}
            color="bg-rose-100 dark:bg-rose-500/15 text-rose-600 dark:text-rose-400"
            testId="stat-rejected"
          />
          <StatCard
            icon={Award}
            label="Rata² Raise"
            value={(stats.avg_raise_pct || 0).toFixed(1)}
            suffix="%"
            color="bg-indigo-100 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-400"
            testId="stat-avg-raise"
          />
        </div>
      )}

      {/* Filters */}
      <Card className="border-border/50">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-[200px]">
              <Search className="w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Cari nama, kode, atau alasan..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="max-w-md"
                data-testid="adj-search-input"
              />
            </div>
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="w-[180px]" data-testid="adj-filter-status">
                <SelectValue placeholder="Filter Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                <SelectItem value="pending_manager">Menunggu Atasan</SelectItem>
                <SelectItem value="pending_hr">Menunggu HR</SelectItem>
                <SelectItem value="approved">Disetujui</SelectItem>
                <SelectItem value="rejected">Ditolak</SelectItem>
                <SelectItem value="cancelled">Dibatalkan</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-[180px]" data-testid="adj-filter-type">
                <SelectValue placeholder="Filter Tipe" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Tipe</SelectItem>
                {Object.entries(TYPE_LABELS).map(([v, l]) => (
                  <SelectItem key={v} value={v}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* List Table */}
      <Card className="border-border/50">
        <CardHeader className="border-b">
          <CardTitle className="text-base flex items-center justify-between">
            <span>Daftar Usulan Kenaikan Gaji</span>
            <Badge variant="secondary" className="text-xs">
              {filtered.length} / {adjustments.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-12 text-center text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              Memuat data…
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground" data-testid="adj-empty-state">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="font-medium">Belum ada usulan kenaikan gaji</p>
              <p className="text-xs mt-1">
                {isHR
                  ? 'Klik "Buat Usulan Manual" atau "Generate dari KPI" untuk memulai.'
                  : 'Belum ada usulan yang menunggu approval Anda.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 border-b">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-medium">Karyawan</th>
                    <th className="px-3 py-2 font-medium">Tipe</th>
                    <th className="px-3 py-2 font-medium">Atasan</th>
                    <th className="px-3 py-2 font-medium text-right">Gaji Saat Ini</th>
                    <th className="px-3 py-2 font-medium text-right">Gaji Usulan</th>
                    <th className="px-3 py-2 font-medium text-right">Kenaikan</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Tgl</th>
                    <th className="px-3 py-2 font-medium text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <tr
                      key={a.id}
                      className="border-b last:border-b-0 hover:bg-muted/30 transition-colors"
                      data-testid={`adj-row-${a.id}`}
                    >
                      <td className="px-3 py-2.5">
                        <div className="font-medium">{a.employee_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {a.employee_code} · {a.department || '—'}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge variant="outline" className="text-xs">
                          {TYPE_LABELS[a.adjustment_type] || a.adjustment_type}
                        </Badge>
                        {a.kpi_grade && (
                          <Badge variant="secondary" className="text-xs ml-1">
                            Grade {a.kpi_grade}
                          </Badge>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs">
                        {a.manager_name ? (
                          <span className="inline-flex items-center gap-1">
                            <UserCheck className="w-3 h-3" />
                            {a.manager_name}
                          </span>
                        ) : (
                          <span className="text-muted-foreground italic">Tidak ada</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-xs">{fmtCurrency(a.current_base)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-xs font-semibold">{fmtCurrency(a.proposed_base)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-xs text-emerald-600 dark:text-emerald-400 font-semibold">
                        +{(a.raise_pct || 0).toFixed(1)}%
                      </td>
                      <td className="px-3 py-2.5">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{fmtDate(a.created_at)}</td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            onClick={() => {
                              setActionDialog({ type: 'view', adj: a });
                              setDetailOpen(true);
                            }}
                            title="Lihat detail"
                            data-testid={`adj-view-${a.id}`}
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          {a.status === 'pending_manager' && (
                            <Button
                              size="sm"
                              variant="default"
                              className="h-7 text-xs"
                              onClick={() => setActionDialog({ type: 'approve_manager', adj: a })}
                              data-testid={`adj-approve-mgr-${a.id}`}
                            >
                              Setujui Atasan
                            </Button>
                          )}
                          {(a.status === 'pending_hr' || (a.status === 'pending_manager' && isHR)) && isHR && (
                            <Button
                              size="sm"
                              variant="default"
                              className="h-7 text-xs"
                              onClick={() => setActionDialog({ type: 'approve_hr', adj: a })}
                              data-testid={`adj-approve-hr-${a.id}`}
                            >
                              Setujui HR
                            </Button>
                          )}
                          {['pending_manager', 'pending_hr'].includes(a.status) && (
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950"
                              onClick={() => setActionDialog({ type: 'reject', adj: a })}
                              data-testid={`adj-reject-${a.id}`}
                            >
                              Tolak
                            </Button>
                          )}
                          {isHR && ['pending_manager', 'pending_hr'].includes(a.status) && (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-7 w-7 text-muted-foreground hover:text-rose-600"
                              onClick={() => setActionDialog({ type: 'cancel', adj: a })}
                              title="Batalkan"
                              data-testid={`adj-cancel-${a.id}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Manual Dialog */}
      <CreateManualDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        token={token}
        employees={employees}
        onSuccess={() => {
          setCreateOpen(false);
          loadData();
        }}
      />

      {/* Generate from KPI Dialog */}
      <GenerateFromKPIDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        token={token}
        kpiPeriods={kpiPeriods}
        onSuccess={() => {
          setGenerateOpen(false);
          loadData();
        }}
      />

      {/* Action Dialog (approve / reject / cancel) */}
      <ActionDialog
        action={actionDialog}
        token={token}
        onClose={() => setActionDialog(null)}
        onSuccess={() => {
          setActionDialog(null);
          loadData();
        }}
      />

      {/* Detail Dialog */}
      <DetailDialog
        open={detailOpen && actionDialog?.type === 'view'}
        adj={actionDialog?.adj}
        onClose={() => {
          setDetailOpen(false);
          setActionDialog(null);
        }}
      />
    </div>
  );
}

// ─── Create Manual Dialog ────────────────────────────────────────────────────
function CreateManualDialog({ open, onClose, token, employees, onSuccess }) {
  const [employeeId, setEmployeeId] = useState('');
  const [proposedBase, setProposedBase] = useState('');
  const [adjType, setAdjType] = useState('manual');
  const [reason, setReason] = useState('');
  const [effectiveDate, setEffectiveDate] = useState('');
  const [currentBase, setCurrentBase] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const selectedEmp = employees.find((e) => e.id === employeeId);

  // Fetch current payroll profile for selected employee
  useEffect(() => {
    if (!employeeId) {
      setCurrentBase(0);
      return;
    }
    fetchAPI(`/payroll-profiles?employee_id=${employeeId}`, {}, token)
      .then((r) => (r.ok ? r.json() : []))
      .then((profiles) => {
        const active = profiles.find((p) => p.active) || profiles[0];
        setCurrentBase(active?.base_rate || 0);
      })
      .catch(() => setCurrentBase(0));
  }, [employeeId, token]);

  const reset = () => {
    setEmployeeId('');
    setProposedBase('');
    setAdjType('manual');
    setReason('');
    setEffectiveDate('');
    setCurrentBase(0);
  };

  const handleSubmit = async () => {
    if (!employeeId) {
      toast.error('Pilih karyawan');
      return;
    }
    const proposed = parseFloat(proposedBase);
    if (!proposed || proposed <= currentBase) {
      toast.error(`Gaji usulan harus lebih besar dari gaji saat ini (${fmtCurrency(currentBase)})`);
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetchAPI(
        '/salary-adjustments',
        {
          method: 'POST',
          body: JSON.stringify({
            employee_id: employeeId,
            proposed_base: proposed,
            adjustment_type: adjType,
            reason: reason || 'Manual adjustment by HR',
            effective_date: effectiveDate || null,
          }),
        },
        token
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal membuat usulan');

      const noManager = !data.manager_id;
      toast.success(
        noManager
          ? 'Usulan dibuat. Karyawan belum punya atasan, langsung menunggu HR.'
          : 'Usulan dibuat. Menunggu approval atasan.'
      );
      reset();
      onSuccess();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-lg" data-testid="create-adj-dialog">
        <DialogHeader>
          <DialogTitle>Buat Usulan Kenaikan Gaji (Manual)</DialogTitle>
          <DialogDescription>
            Usulan akan masuk workflow dual approval: Atasan → HR
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <Label htmlFor="emp-select">Karyawan *</Label>
            <Select value={employeeId} onValueChange={setEmployeeId}>
              <SelectTrigger id="emp-select" data-testid="create-adj-employee-select">
                <SelectValue placeholder="Pilih karyawan…" />
              </SelectTrigger>
              <SelectContent className="max-h-[300px]">
                {employees
                  .filter((e) => e.active !== false)
                  .map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.employee_code} — {e.name} {e.manager_name ? `(Atasan: ${e.manager_name})` : '(Tanpa Atasan)'}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            {selectedEmp && !selectedEmp.manager_id && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                Karyawan belum punya atasan. Usulan akan langsung menunggu approval HR.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Gaji Saat Ini</Label>
              <Input
                value={fmtCurrency(currentBase)}
                readOnly
                className="bg-muted"
                data-testid="create-adj-current-base"
              />
            </div>
            <div>
              <Label htmlFor="proposed-base">Gaji Usulan (Rp) *</Label>
              <Input
                id="proposed-base"
                type="number"
                value={proposedBase}
                onChange={(e) => setProposedBase(e.target.value)}
                placeholder="contoh: 5500000"
                data-testid="create-adj-proposed-base"
              />
              {proposedBase && currentBase > 0 && parseFloat(proposedBase) > currentBase && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                  +{(((parseFloat(proposedBase) - currentBase) / currentBase) * 100).toFixed(1)}% (
                  {fmtCurrency(parseFloat(proposedBase) - currentBase)})
                </p>
              )}
            </div>
          </div>

          <div>
            <Label htmlFor="adj-type">Tipe Penyesuaian</Label>
            <Select value={adjType} onValueChange={setAdjType}>
              <SelectTrigger id="adj-type" data-testid="create-adj-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TYPE_LABELS).map(([v, l]) => (
                  <SelectItem key={v} value={v}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="effective-date">Tgl Efektif (Opsional)</Label>
            <Input
              id="effective-date"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              data-testid="create-adj-effective-date"
            />
          </div>

          <div>
            <Label htmlFor="reason">Alasan</Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Misal: Promosi, kinerja menonjol, dll."
              rows={3}
              data-testid="create-adj-reason"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting} data-testid="create-adj-cancel-btn">
            Batal
          </Button>
          <Button onClick={handleSubmit} disabled={submitting} data-testid="create-adj-submit-btn">
            {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Buat Usulan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Generate from KPI Dialog ────────────────────────────────────────────────
function GenerateFromKPIDialog({ open, onClose, token, kpiPeriods, onSuccess }) {
  const [periodId, setPeriodId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const handleGenerate = async () => {
    if (!periodId) {
      toast.error('Pilih periode KPI dulu');
      return;
    }
    setSubmitting(true);
    setResult(null);
    try {
      const res = await fetchAPI(
        `/salary-adjustments/generate-from-kpi/${periodId}`,
        { method: 'POST' },
        token
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal generate');
      setResult(data);
      toast.success(data.message || `Berhasil generate ${data.created} usulan`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setPeriodId('');
    setResult(null);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-lg" data-testid="generate-kpi-dialog">
        <DialogHeader>
          <DialogTitle>Generate Usulan Kenaikan dari KPI</DialogTitle>
          <DialogDescription>
            Membuat usulan kenaikan gaji untuk semua karyawan dengan KPI Grade A (10%) atau B (7%) pada periode terpilih.
            Karyawan yang sudah punya usulan aktif untuk periode ini akan di-skip.
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="space-y-3">
            <div>
              <Label htmlFor="kpi-period">Periode KPI (yang sudah final)</Label>
              <Select value={periodId} onValueChange={setPeriodId}>
                <SelectTrigger id="kpi-period" data-testid="generate-period-select">
                  <SelectValue placeholder="Pilih periode KPI…" />
                </SelectTrigger>
                <SelectContent>
                  {kpiPeriods.length === 0 ? (
                    <SelectItem value="__empty__" disabled>
                      Belum ada periode KPI yang final/published
                    </SelectItem>
                  ) : (
                    kpiPeriods.map((p) => (
                      <SelectItem key={p.period_id} value={p.period_id}>
                        {p.period_label} ({p.month}/{p.year})
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
            {kpiPeriods.length === 0 && (
              <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 rounded p-3 text-xs text-amber-700 dark:text-amber-300 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <div>
                  Belum ada periode KPI yang sudah dipublish/final. Silakan buka modul KPI dan publish dulu hasil periode yang
                  ingin di-generate.
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-400 dark:border-emerald-500/30 rounded p-3 text-sm">
              <div className="font-semibold flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                Selesai
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  Berhasil dibuat: <strong>{result.created}</strong>
                </div>
                <div>
                  Di-skip: <strong>{result.skipped}</strong>
                </div>
              </div>
              {result.skipped_reasons && Object.values(result.skipped_reasons).some((v) => v > 0) && (
                <div className="mt-2 pt-2 border-t border-emerald-400 dark:border-emerald-500/30 text-xs space-y-0.5">
                  <div className="font-medium">Detail skip:</div>
                  {result.skipped_reasons.duplicate_active > 0 && (
                    <div>• Sudah ada usulan aktif: {result.skipped_reasons.duplicate_active}</div>
                  )}
                  {result.skipped_reasons.no_payroll_profile > 0 && (
                    <div>• Tidak punya payroll profile: {result.skipped_reasons.no_payroll_profile}</div>
                  )}
                  {result.skipped_reasons.employee_not_found > 0 && (
                    <div>• Karyawan tidak ditemukan: {result.skipped_reasons.employee_not_found}</div>
                  )}
                  {result.skipped_reasons.raise_pct_zero > 0 && (
                    <div>• Grade tidak eligible: {result.skipped_reasons.raise_pct_zero}</div>
                  )}
                </div>
              )}
            </div>
            {result.created_items && result.created_items.length > 0 && (
              <div className="max-h-48 overflow-y-auto border rounded">
                <table className="w-full text-xs">
                  <thead className="bg-muted">
                    <tr>
                      <th className="text-left px-2 py-1">Karyawan</th>
                      <th className="text-right px-2 py-1">Raise %</th>
                      <th className="text-left px-2 py-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.created_items.map((c) => (
                      <tr key={c.id} className="border-t">
                        <td className="px-2 py-1">{c.employee_name}</td>
                        <td className="px-2 py-1 text-right text-emerald-600 dark:text-emerald-400 font-semibold">
                          +{c.raise_pct.toFixed(0)}%
                        </td>
                        <td className="px-2 py-1">
                          <StatusBadge status={c.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {!result ? (
            <>
              <Button variant="outline" onClick={onClose} disabled={submitting}>
                Batal
              </Button>
              <Button
                onClick={handleGenerate}
                disabled={submitting || !periodId}
                data-testid="generate-submit-btn"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                <Wand2 className="w-4 h-4 mr-2" />
                Generate Sekarang
              </Button>
            </>
          ) : (
            <Button onClick={onSuccess} data-testid="generate-close-btn">
              <CheckCircle2 className="w-4 h-4 mr-2" />
              Tutup & Refresh
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Action Dialog (Approve / Reject / Cancel) ───────────────────────────────
function ActionDialog({ action, token, onClose, onSuccess }) {
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setNotes('');
  }, [action]);

  if (!action || action.type === 'view') return null;

  const { type, adj } = action;

  const config = {
    approve_manager: {
      title: 'Setujui Sebagai Atasan',
      description: 'Anda akan menyetujui usulan ini sebagai atasan. Setelah disetujui akan diteruskan ke HR untuk approval final.',
      endpoint: `/salary-adjustments/${adj.id}/approve-manager`,
      bodyKey: 'notes',
      submitLabel: 'Setujui',
      variant: 'default',
      icon: CheckCircle2,
      iconColor: 'text-emerald-600',
    },
    approve_hr: {
      title: 'Setujui Sebagai HR (Final)',
      description: `Setelah disetujui HR, gaji ${adj.employee_name} akan otomatis diupdate menjadi ${fmtCurrency(adj.proposed_base)} di payroll profile.`,
      endpoint: `/salary-adjustments/${adj.id}/approve-hr`,
      bodyKey: 'notes',
      submitLabel: 'Setujui & Apply',
      variant: 'default',
      icon: Banknote,
      iconColor: 'text-emerald-600',
    },
    reject: {
      title: 'Tolak Usulan',
      description: 'Anda akan menolak usulan kenaikan gaji ini. Mohon berikan alasan penolakan.',
      endpoint: `/salary-adjustments/${adj.id}/reject`,
      bodyKey: 'reason',
      submitLabel: 'Tolak',
      variant: 'destructive',
      icon: XCircle,
      iconColor: 'text-rose-600',
      requireNotes: true,
    },
    cancel: {
      title: 'Batalkan Usulan',
      description: 'Usulan akan dibatalkan dan tidak bisa di-approve lagi.',
      endpoint: `/salary-adjustments/${adj.id}`,
      method: 'DELETE',
      submitLabel: 'Batalkan',
      variant: 'destructive',
      icon: Trash2,
      iconColor: 'text-rose-600',
    },
  }[type];

  const handleSubmit = async () => {
    if (config.requireNotes && !notes.trim()) {
      toast.error('Mohon isi alasan');
      return;
    }
    setSubmitting(true);
    try {
      const opts = { method: config.method || 'POST' };
      if (config.bodyKey) {
        opts.body = JSON.stringify({ [config.bodyKey]: notes });
      }
      const res = await fetchAPI(config.endpoint, opts, token);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal');
      toast.success(data.message || 'Berhasil');
      onSuccess();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const Icon = config.icon;

  return (
    <Dialog open={!!action} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="action-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className={`w-5 h-5 ${config.iconColor}`} />
            {config.title}
          </DialogTitle>
          <DialogDescription>{config.description}</DialogDescription>
        </DialogHeader>

        {/* Summary card */}
        <div className="bg-muted rounded p-3 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Karyawan</span>
            <span className="font-medium">
              {adj.employee_name} ({adj.employee_code})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Gaji saat ini</span>
            <span className="tabular-nums">{fmtCurrency(adj.current_base)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Gaji usulan</span>
            <span className="tabular-nums font-semibold">{fmtCurrency(adj.proposed_base)}</span>
          </div>
          <div className="flex justify-between text-emerald-600 dark:text-emerald-400 font-semibold">
            <span>Kenaikan</span>
            <span>+{(adj.raise_pct || 0).toFixed(1)}%</span>
          </div>
        </div>

        {config.bodyKey && (
          <div>
            <Label htmlFor="action-notes">
              {type === 'reject' ? 'Alasan Penolakan *' : 'Catatan (Opsional)'}
            </Label>
            <Textarea
              id="action-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder={type === 'reject' ? 'Alasan penolakan…' : 'Catatan…'}
              data-testid="action-notes-input"
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Batal
          </Button>
          <Button variant={config.variant} onClick={handleSubmit} disabled={submitting} data-testid="action-submit-btn">
            {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            {config.submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Detail Dialog ───────────────────────────────────────────────────────────
function DetailDialog({ open, adj, onClose }) {
  if (!adj) return null;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Detail Usulan Kenaikan Gaji
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <DetailRow label="Karyawan" value={`${adj.employee_name} (${adj.employee_code})`} />
            <DetailRow label="Departemen" value={adj.department || '—'} />
            <DetailRow label="Tipe" value={TYPE_LABELS[adj.adjustment_type] || adj.adjustment_type} />
            <DetailRow label="Status" value={<StatusBadge status={adj.status} />} />
            <DetailRow label="Atasan (Manager)" value={adj.manager_name || '—'} />
            {adj.kpi_grade && <DetailRow label="KPI Grade" value={`${adj.kpi_grade} (skor: ${adj.kpi_final_score?.toFixed(1)})`} />}
          </div>
          <div className="border-t pt-3 grid grid-cols-3 gap-3">
            <DetailRow label="Gaji Saat Ini" value={fmtCurrency(adj.current_base)} />
            <DetailRow label="Gaji Usulan" value={fmtCurrency(adj.proposed_base)} />
            <DetailRow label="Kenaikan" value={`+${(adj.raise_pct || 0).toFixed(1)}% (${fmtCurrency(adj.raise_amount)})`} />
          </div>
          <div className="border-t pt-3">
            <DetailRow label="Alasan" value={adj.reason || '—'} />
          </div>
          <div className="border-t pt-3 text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Dibuat oleh</span>
              <span>
                {adj.created_by_name || '—'} · {fmtDate(adj.created_at)}
              </span>
            </div>
            {adj.manager_approved_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Disetujui Atasan</span>
                <span>
                  {adj.manager_approved_by_name} · {fmtDate(adj.manager_approved_at)}
                  {adj.manager_notes && <span className="block italic text-muted-foreground">"{adj.manager_notes}"</span>}
                </span>
              </div>
            )}
            {adj.hr_approved_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Disetujui HR</span>
                <span>
                  {adj.hr_approved_by_name} · {fmtDate(adj.hr_approved_at)}
                  {adj.hr_notes && <span className="block italic text-muted-foreground">"{adj.hr_notes}"</span>}
                </span>
              </div>
            )}
            {adj.applied_at && (
              <div className="flex justify-between text-emerald-600 dark:text-emerald-400">
                <span>Applied ke Payroll</span>
                <span>{fmtDate(adj.applied_at)}</span>
              </div>
            )}
            {adj.rejected_at && (
              <div className="flex justify-between text-rose-600 dark:text-rose-400">
                <span>Ditolak oleh {adj.rejected_by_role}</span>
                <span>
                  {adj.rejected_by_name} · {fmtDate(adj.rejected_at)}
                  {adj.rejection_reason && (
                    <span className="block italic">"{adj.rejection_reason}"</span>
                  )}
                </span>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={onClose} data-testid="detail-close-btn">
            Tutup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailRow({ label, value }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-sm font-medium mt-0.5">{value}</div>
    </div>
  );
}
