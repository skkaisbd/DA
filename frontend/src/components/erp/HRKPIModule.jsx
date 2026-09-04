import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Target, Users, ClipboardList, BarChart3, Settings, Plus, RefreshCw,
  ChevronDown, ChevronRight, CheckCircle2, Clock, AlertCircle, Edit2,
  Trash2, Eye, Send, FileText, TrendingUp, Award, UserCheck, X,
  BookOpen, Save, Loader2, Download, Star, Flag, Activity, Trophy,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, BarChart, Bar, Cell,
} from 'recharts';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import KPIGamificationTab from './KPIGamificationTab';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;
const kpi = (path, opts = {}) => fetch(`${API}/api/dewi/kpi${path}`, opts);

const GRADE_CFG = {
  A: { color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border-emerald-400 dark:border-emerald-500/30', label: 'Sangat Baik', raise: '10%' },
  B: { color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300 border-blue-400 dark:border-blue-500/30', label: 'Baik', raise: '7%' },
  C: { color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-400 dark:border-amber-500/30', label: 'Cukup', raise: '-' },
  D: { color: 'bg-orange-100 dark:bg-orange-500/20 text-orange-600 dark:text-orange-300 border-orange-400 dark:border-orange-500/30', label: 'Kurang', raise: '-' },
  E: { color: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300 border-red-400 dark:border-red-500/30', label: 'Sangat Kurang', raise: '-' },
};

const STATUS_CFG = {
  draft: { color: 'bg-muted dark:bg-slate-500/20 text-foreground/70', label: 'Draft' },
  open: { color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300', label: 'Buka' },
  closed: { color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300', label: 'Ditutup' },
  finalized: { color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300', label: 'Final' },
};

const EVAL_TYPE_CFG = {
  self: { label: 'Self-Assessment', color: 'text-indigo-600 dark:text-indigo-400', weight: '20%' },
  peer: { label: 'Peer Review', color: 'text-sky-600 dark:text-sky-400', weight: '20%' },
  supervisor_to_staff: { label: 'Supervisor → Staff', color: 'text-amber-700 dark:text-amber-400', weight: '35%' },
  staff_to_supervisor: { label: 'Staff → Supervisor', color: 'text-violet-600 dark:text-violet-400', weight: '25%' },
};

const fmtScore = (n) => (n === null || n === undefined) ? '—' : Number(n).toFixed(1);
const fmtPct = (n) => (n === null || n === undefined) ? '—' : `${Number(n).toFixed(1)}%`;

function GradeBadge({ grade }) {
  if (!grade) return <span className="text-muted-foreground text-xs">—</span>;
  const cfg = GRADE_CFG[grade] || {};
  return <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${cfg.color}`}>{grade}</span>;
}

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.draft;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>{cfg.label}</span>;
}

function ScoreBar({ score, max = 100, color = 'bg-indigo-500' }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  return (
    <div className="w-full bg-foreground/5 rounded-full h-1.5 overflow-hidden">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function HRKPIModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [tab, setTab] = useState('periods');

  const [periods, setPeriods] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selectedPeriod, setSelectedPeriod] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [reportData, setReportData] = useState(null);
  const [performData, setPerformData] = useState([]);
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkScores, setBulkScores] = useState({});
  const [bulkSaving, setBulkSaving] = useState(false);
  const [fairnessData, setFairnessData] = useState(null);
  const [fairnessLoading, setFairnessLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);

  const loadFairness = useCallback(async (pid) => {
    if (!pid) return;
    setFairnessLoading(true);
    try {
      const r = await kpi(`/fairness/${pid}`, { headers });
      const d = await r.json();
      setFairnessData(d);
    } catch (e) { console.error(e); }
    finally { setFairnessLoading(false); }
  }, [headers]);

  const handleBulkSave = async () => {
    if (!selectedPeriod) return;
    const entries = Object.entries(bulkScores).filter(([, v]) => v.perform_score !== '' && v.perform_score !== null && v.perform_score !== undefined);
    if (!entries.length) { toast.error('Tidak ada nilai yang diinput'); return; }
    setBulkSaving(true);
    try {
      const payload = entries.map(([employee_id, v]) => ({
        employee_id,
        perform_score: parseFloat(v.perform_score) || 0,
        notes: v.notes || '',
      }));
      const r = await kpi(`/perform/${selectedPeriod.period_id}/bulk`, {
        method: 'POST', headers, body: JSON.stringify({ scores: payload }),
      });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal simpan'); return; }
      toast.success(`${d.saved} nilai perform disimpan, ${d.skipped} dilewati`);
      setBulkScores({});
      loadPerform(selectedPeriod.period_id);
    } catch (e) { toast.error('Gagal menyimpan'); }
    finally { setBulkSaving(false); }
  };

  // Trend & Goals state
  const [trendEmployeeId, setTrendEmployeeId] = useState('');
  const [trendData, setTrendData] = useState(null);
  const [companyTrend, setCompanyTrend] = useState(null);
  const [goals, setGoals] = useState([]);
  const [goalsPeriodId, setGoalsPeriodId] = useState('');
  const [goalsEmployeeId, setGoalsEmployeeId] = useState('');
  const [goalDialog, setGoalDialog] = useState(null);
  const [kpiStats, setKpiStats] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);
  const [goalsLoading, setGoalsLoading] = useState(false);

  // Dialogs
  const [periodDialog, setPeriodDialog] = useState(null);
  const [questionDialog, setQuestionDialog] = useState(null);
  const [performDialog, setPerformDialog] = useState(null);
  const [resultDialog, setResultDialog] = useState(null);

  const loadPeriods = useCallback(async () => {
    try {
      const r = await kpi('/periods', { headers });
      const d = await r.json();
      setPeriods(d.periods || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadQuestions = useCallback(async () => {
    try {
      const r = await kpi('/questions', { headers });
      const d = await r.json();
      setQuestions(d.questions || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadEmployees = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers });
      const d = await r.json();
      setEmployees(Array.isArray(d) ? d : (d.items || d.rows || d.employees || []));
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadProgress = useCallback(async (pid) => {
    if (!pid) return;
    try {
      const r = await kpi(`/monitor/${pid}`, { headers });
      const d = await r.json();
      setProgressData(d);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadReport = useCallback(async (pid) => {
    if (!pid) return;
    try {
      const r = await kpi(`/reports/summary/${pid}`, { headers });
      const d = await r.json();
      setReportData(d);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadPerform = useCallback(async (pid) => {
    if (!pid) return;
    try {
      const r = await kpi(`/perform/${pid}`, { headers });
      const d = await r.json();
      setPerformData(d.perform_scores || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadTrend = useCallback(async (empId) => {
    if (!empId) return;
    setTrendLoading(true);
    try {
      const r = await kpi(`/trend/${empId}`, { headers });
      const d = await r.json();
      setTrendData(d);
    } catch (e) { console.error(e); }
    finally { setTrendLoading(false); }
  }, [headers]);

  const loadCompanyTrend = useCallback(async () => {
    try {
      const r = await kpi('/trend', { headers });
      const d = await r.json();
      setCompanyTrend(d);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadGoals = useCallback(async (pid, empId) => {
    setGoalsLoading(true);
    try {
      const params = new URLSearchParams();
      if (pid) params.set('period_id', pid);
      if (empId) params.set('employee_id', empId);
      const r = await kpi(`/goals?${params}`, { headers });
      const d = await r.json();
      setGoals(d.goals || []);
    } catch (e) { console.error(e); }
    finally { setGoalsLoading(false); }
  }, [headers]);

  const loadKpiStats = useCallback(async () => {
    try {
      const r = await kpi('/stats', { headers });
      const d = await r.json();
      setKpiStats(d);
    } catch (e) { console.error(e); }
  }, [headers]);

  useEffect(() => {
    loadPeriods();
    loadEmployees();
    loadKpiStats();
  }, [loadPeriods, loadEmployees, loadKpiStats]);

  useEffect(() => {
    if (tab === 'questions') loadQuestions();
    if (tab === 'perform' && selectedPeriod) loadPerform(selectedPeriod.period_id);
    if (tab === 'monitor' && selectedPeriod) loadProgress(selectedPeriod.period_id);
    if (tab === 'reports' && selectedPeriod) { loadReport(selectedPeriod.period_id); }
    if (tab === 'trend') { loadCompanyTrend(); if (trendEmployeeId) loadTrend(trendEmployeeId); }
    if (tab === 'goals') { loadGoals(goalsPeriodId, goalsEmployeeId); }
  }, [tab, selectedPeriod, loadQuestions, loadProgress, loadReport, loadPerform, loadCompanyTrend, loadTrend, trendEmployeeId, loadGoals, goalsPeriodId, goalsEmployeeId, loadKpiStats]);

  const handleSeedDefaults = async () => {
    const r = await kpi('/questions/seed-defaults', { method: 'POST', headers });
    const d = await r.json();
    toast(d.message || 'Selesai');
    loadQuestions();
  };

  const handleSavePeriod = async (form) => {
    const isEdit = !!form.period_id;
    const url = isEdit ? `/periods/${form.period_id}` : '/periods';
    const method = isEdit ? 'PUT' : 'POST';
    const r = await kpi(url, { method, headers, body: JSON.stringify(form) });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal menyimpan periode'); return; }
    toast.success(isEdit ? 'Periode diupdate' : 'Periode dibuat');
    setPeriodDialog(null);
    loadPeriods();
  };

  const handleChangeStatus = async (period, newStatus) => {
    const r = await kpi(`/periods/${period.period_id}`, {
      method: 'PUT', headers, body: JSON.stringify({ status: newStatus }),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal ubah status'); return; }
    toast.success(`Status diubah ke "${STATUS_CFG[newStatus]?.label}"`);
    loadPeriods();
    if (selectedPeriod?.period_id === period.period_id) {
      setSelectedPeriod(d.period);
    }
  };

  const handleDeletePeriod = async (period) => {
    if (!window.confirm(`Hapus periode "${period.name}"?`)) return;
    const r = await kpi(`/periods/${period.period_id}`, { method: 'DELETE', headers });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal hapus'); return; }
    toast.success('Periode dihapus');
    loadPeriods();
    if (selectedPeriod?.period_id === period.period_id) setSelectedPeriod(null);
  };

  const handleSaveQuestion = async (form) => {
    const isEdit = !!form.question_id;
    const url = isEdit ? `/questions/${form.question_id}` : '/questions';
    const method = isEdit ? 'PUT' : 'POST';
    const r = await kpi(url, { method, headers, body: JSON.stringify(form) });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success(isEdit ? 'Pertanyaan diupdate' : 'Pertanyaan ditambahkan');
    setQuestionDialog(null);
    loadQuestions();
  };

  const handleDeleteQuestion = async (qid) => {
    if (!window.confirm('Nonaktifkan pertanyaan ini?')) return;
    await kpi(`/questions/${qid}`, { method: 'DELETE', headers });
    toast.success('Pertanyaan dinonaktifkan');
    loadQuestions();
  };

  const handleSavePerform = async (form) => {
    const r = await kpi(`/perform/${form.period_id}/${form.employee_id}`, {
      method: 'PUT', headers, body: JSON.stringify(form),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
    toast.success('Nilai Perform disimpan');
    setPerformDialog(null);
    loadPerform(form.period_id);
  };

  const handleCalculate = async () => {
    if (!selectedPeriod) return;
    setCalculating(true);
    try {
      const r = await kpi(`/results/${selectedPeriod.period_id}/calculate`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal kalkulasi'); return; }
      toast.success(`KPI dihitung untuk ${d.calculated} karyawan`);
      loadReport(selectedPeriod.period_id);
    } finally {
      setCalculating(false);
    }
  };

  const handlePublish = async (force = false) => {
    if (!selectedPeriod) return;
    if (!force && !window.confirm('Publish hasil KPI? Karyawan akan bisa melihat hasilnya.')) return;
    const r = await kpi(`/results/${selectedPeriod.period_id}/publish`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ force }),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal publish'); return; }
    // Completion warning
    if (d.warning) {
      if (window.confirm(
        `${d.message}\n\nLanjutkan publish dengan data yang ada?`
      )) {
        return handlePublish(true);
      }
      return;
    }
    const raiseMsg = d.raise_proposals
      ? ` | ${d.raise_proposals.created} usulan kenaikan gaji otomatis dibuat`
      : '';
    toast.success(`${d.published} hasil KPI dipublish (${d.completion_pct}% lengkap)${raiseMsg}`, {
      description: d.raise_proposals?.created > 0
        ? 'Buka HR → Penggajian → Kenaikan Gaji untuk approve usulan kenaikan.'
        : undefined,
      duration: 6000,
    });
    loadPeriods();
    loadReport(selectedPeriod.period_id);
    loadKpiStats();
  };

  // Sprint 42 — Generate raise proposals from this KPI period (Grade A/B → 10%/7%)
  const [generatingRaise, setGeneratingRaise] = useState(false);
  const handleGenerateRaiseProposals = async () => {
    if (!selectedPeriod) return;
    if (!window.confirm(
      `Generate usulan kenaikan gaji untuk semua karyawan dengan Grade A (10%) atau B (7%) di periode ini?\n\n` +
      `Usulan akan masuk workflow dual approval: Atasan → HR.\n` +
      `Karyawan yang sudah punya usulan aktif untuk periode ini akan di-skip.`
    )) return;

    setGeneratingRaise(true);
    try {
      const API_URL = process.env.REACT_APP_BACKEND_URL;
      const r = await fetch(
        `${API_URL}/api/rahaza/salary-adjustments/generate-from-kpi/${selectedPeriod.period_id}`,
        { method: 'POST', headers }
      );
      const d = await r.json();
      if (!r.ok) {
        toast.error(d.detail || 'Gagal generate usulan');
        return;
      }
      toast.success(
        `${d.message || `Berhasil ${d.created} usulan, ${d.skipped} di-skip`}`,
        {
          description: `Buka menu HR → Penggajian → Kenaikan Gaji untuk approve.`,
          duration: 5000,
        }
      );
    } catch (e) {
      toast.error(e.message || 'Gagal generate');
    } finally {
      setGeneratingRaise(false);
    }
  };

  const empOptions = employees.map(e => ({ value: e.id, label: `${e.employee_code} — ${e.name}` }));

  // RC-UI-03: client-side pagination (10/page) for KPI periods & goals lists
  const periodsPg = useClientPagination(periods, 10);
  const goalsPg   = useClientPagination(goals, 10);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Target className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
            KPI Bulanan Operasional
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Evaluasi operasional per periode (bulanan) · Perform 60% · Attitude 20% · Absensi 20% · Untuk review tahunan, gunakan menu <strong>Annual Review</strong>.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { loadPeriods(); loadEmployees(); }}>
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-8 w-full">
          <TabsTrigger value="periods" className="flex items-center gap-1.5 text-xs">
            <FileText className="w-3.5 h-3.5" /> Periode
          </TabsTrigger>
          <TabsTrigger value="questions" className="flex items-center gap-1.5 text-xs">
            <BookOpen className="w-3.5 h-3.5" /> Bank Soal
          </TabsTrigger>
          <TabsTrigger value="perform" className="flex items-center gap-1.5 text-xs">
            <TrendingUp className="w-3.5 h-3.5" /> Nilai Perform
          </TabsTrigger>
          <TabsTrigger value="monitor" className="flex items-center gap-1.5 text-xs">
            <UserCheck className="w-3.5 h-3.5" /> Progress
          </TabsTrigger>
          <TabsTrigger value="reports" className="flex items-center gap-1.5 text-xs">
            <BarChart3 className="w-3.5 h-3.5" /> Laporan
          </TabsTrigger>
          <TabsTrigger value="trend" className="flex items-center gap-1.5 text-xs">
            <Activity className="w-3.5 h-3.5" /> Tren KPI
          </TabsTrigger>
          <TabsTrigger value="goals" className="flex items-center gap-1.5 text-xs">
            <Flag className="w-3.5 h-3.5" /> Goals
          </TabsTrigger>
          <TabsTrigger value="gamifikasi" className="flex items-center gap-1.5 text-xs">
            <Trophy className="w-3.5 h-3.5" /> Gamifikasi
          </TabsTrigger>
        </TabsList>

        {/* ── TAB 1: PERIODE ─────────────────────────────────── */}
        <TabsContent value="periods" className="space-y-4 mt-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-muted-foreground">{periods.length} periode terdaftar</p>
            <Button size="sm" onClick={() => setPeriodDialog({ participant_employee_ids: [], supervisor_assignments: [] })}>
              <Plus className="w-4 h-4 mr-1" /> Buat Periode
            </Button>
          </div>

          <div className="space-y-3">
            {periodsPg.paged.map(p => (
              <div
                key={p.period_id}
                className={`rounded-xl border p-4 cursor-pointer transition-all ${selectedPeriod?.period_id === p.period_id ? 'border-indigo-500/50 bg-indigo-100 dark:bg-indigo-500/5' : 'border-foreground/10 bg-foreground/5 hover:border-foreground/20'}`}
                onClick={() => setSelectedPeriod(p)}
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">{p.name}</span>
                      <StatusBadge status={p.status} />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {p.period_from && p.period_to ? `${p.period_from} s.d. ${p.period_to}` : 'Tanggal belum diatur'}
                      {' · '}{p.working_days} hari kerja
                      {' · '}{p.participant_count || 0} karyawan
                    </div>
                  </div>
                  <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                    {p.status === 'draft' && (
                      <Button size="sm" variant="outline" className="text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30 h-7 text-xs"
                        onClick={() => handleChangeStatus(p, 'open')}>
                        Buka Form
                      </Button>
                    )}
                    {p.status === 'open' && (
                      <Button size="sm" variant="outline" className="text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-500/30 h-7 text-xs"
                        onClick={() => handleChangeStatus(p, 'closed')}>
                        Tutup Form
                      </Button>
                    )}
                    {p.status === 'closed' && (
                      <Button size="sm" variant="outline" className="text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-500/30 h-7 text-xs"
                        onClick={() => { setSelectedPeriod(p); setTab('reports'); setTimeout(() => handlePublish(), 100); }}>
                        <Send className="w-3 h-3 mr-1" /> Publish Hasil
                      </Button>
                    )}
                    <Button size="icon" variant="ghost" className="h-7 w-7"
                      onClick={() => setPeriodDialog(p)}>
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>
                    {p.status === 'draft' && (
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400"
                        onClick={() => handleDeletePeriod(p)}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {periods.length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                <Target className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p>Belum ada periode KPI</p>
                <Button size="sm" className="mt-3" onClick={() => setPeriodDialog({})}>
                  Buat Periode Pertama
                </Button>
              </div>
            )}
            {periodsPg.total > 0 && <PaginationLite page={periodsPg.page} totalPages={periodsPg.totalPages} total={periodsPg.total} pageSize={periodsPg.pageSize} onPageChange={periodsPg.setPage} />}
          </div>
        </TabsContent>

        {/* ── TAB 2: BANK SOAL ─────────────────────────────────── */}
        <TabsContent value="questions" className="space-y-4 mt-4">
          <div className="flex justify-between items-center flex-wrap gap-2">
            <p className="text-sm text-muted-foreground">{questions.length} pertanyaan aktif</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleSeedDefaults}>
                <BookOpen className="w-4 h-4 mr-1" /> Seed Default DA
              </Button>
              <Button size="sm" onClick={() => setQuestionDialog({ eval_type: 'self', category_weight: 0.10 })}>
                <Plus className="w-4 h-4 mr-1" /> Tambah Soal
              </Button>
            </div>
          </div>

          {Object.entries(EVAL_TYPE_CFG).map(([type, cfg]) => {
            const typeQs = questions.filter(q => q.eval_type === type);
            if (!typeQs.length) return null;
            return (
              <div key={type} className="rounded-xl border border-foreground/10 bg-foreground/5 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-foreground/10">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-semibold ${cfg.color}`}>{cfg.label}</span>
                    <span className="text-xs text-muted-foreground">Bobot {cfg.weight}</span>
                    <span className="text-xs bg-foreground/10 px-2 py-0.5 rounded-full">{typeQs.length} soal</span>
                  </div>
                </div>
                <div className="divide-y divide-white/5">
                  {typeQs.map((q, i) => (
                    <div key={q.question_id} className="flex items-start justify-between px-4 py-3 group">
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        <span className="text-xs text-muted-foreground mt-0.5 shrink-0">{i + 1}.</span>
                        <div className="min-w-0">
                          <div className="text-xs text-foreground/80 leading-relaxed">{q.question_text}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            Kategori: <span className="text-foreground/60">{q.category}</span>
                            {' · '}Bobot: {(q.category_weight * 100).toFixed(0)}%
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 shrink-0 ml-2">
                        <Button size="icon" variant="ghost" className="h-6 w-6"
                          onClick={() => setQuestionDialog(q)}>
                          <Edit2 className="w-3 h-3" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-6 w-6 text-red-700 dark:text-red-400"
                          onClick={() => handleDeleteQuestion(q.question_id)}>
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
          {questions.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <BookOpen className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="mb-3">Bank soal kosong</p>
              <Button size="sm" onClick={handleSeedDefaults}>Seed Pertanyaan Default DA</Button>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 3: NILAI PERFORM ─────────────────────────────── */}
        <TabsContent value="perform" className="space-y-4 mt-4">
          {!selectedPeriod ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>Pilih periode terlebih dahulu di tab Periode</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="font-medium text-foreground">{selectedPeriod.name}</p>
                  <p className="text-xs text-muted-foreground">{performData.length} karyawan sudah diinput</p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={bulkMode ? 'default' : 'outline'}
                    className={bulkMode ? 'bg-indigo-600 hover:bg-indigo-700' : ''}
                    onClick={() => { setBulkMode(!bulkMode); setBulkScores({}); }}
                  >
                    <ClipboardList className="w-4 h-4 mr-1" />
                    {bulkMode ? 'Kembali ke Normal' : 'Mode Bulk Input'}
                  </Button>
                  {!bulkMode && (
                    <Button size="sm" onClick={() => setPerformDialog({
                      period_id: selectedPeriod.period_id,
                      items: [{ label: 'KPI Utama', target: 100, actual: 0, score: 0, weight: 1 }],
                    })}>
                      <Plus className="w-4 h-4 mr-1" /> Input Nilai
                    </Button>
                  )}
                  {bulkMode && (
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700"
                      onClick={handleBulkSave} disabled={bulkSaving || !Object.keys(bulkScores).length}>
                      {bulkSaving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
                      Simpan Semua ({Object.keys(bulkScores).length})
                    </Button>
                  )}
                </div>
              </div>

              {/* Bulk mode info banner */}
              {bulkMode && (
                <div className="rounded-lg border border-indigo-400 dark:border-indigo-500/30 bg-indigo-100 dark:bg-indigo-500/5 px-4 py-2.5 text-xs text-indigo-600 dark:text-indigo-300 flex items-center gap-2">
                  <ClipboardList className="w-4 h-4 shrink-0" />
                  <span>
                    <strong>Mode Bulk Input:</strong> Ketik langsung nilai perform (0–100) di kolom input. Klik "Simpan Semua" untuk menyimpan semua sekaligus.
                    Nilai kosong tidak akan tersimpan.
                  </span>
                </div>
              )}

              {/* Participants table */}
              {selectedPeriod.participant_employee_ids?.length > 0 && (
                <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                        <th className="text-left px-4 py-3">Karyawan</th>
                        <th className="text-center px-4 py-3">Nilai Perform</th>
                        {bulkMode && <th className="text-center px-4 py-3 text-indigo-600 dark:text-indigo-300">Input Baru</th>}
                        <th className="text-left px-4 py-3">{bulkMode ? 'Catatan Baru' : 'Catatan'}</th>
                        {!bulkMode && <th className="px-4 py-3"></th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {selectedPeriod.participant_employee_ids.map(empId => {
                        const emp = employees.find(e => e.id === empId);
                        const perf = performData.find(p => p.employee_id === empId);
                        const bulkVal = bulkScores[empId] || {};
                        const hasBulkInput = bulkVal.perform_score !== undefined && bulkVal.perform_score !== '';
                        return (
                          <tr key={empId} className={`hover:bg-foreground/5 transition-colors ${hasBulkInput ? 'bg-indigo-100 dark:bg-indigo-500/5' : ''}`}>
                            <td className="px-4 py-3">
                              <div className="font-medium">{emp?.name || 'Karyawan'}</div>
                              <div className="text-xs text-muted-foreground">{emp?.employee_code || empId.slice(0, 8)}</div>
                            </td>
                            <td className="px-4 py-3 text-center">
                              {perf ? (
                                <span className="font-bold text-indigo-600 dark:text-indigo-400">{fmtScore(perf.perform_score)}</span>
                              ) : (
                                <span className="text-muted-foreground text-xs">Belum diinput</span>
                              )}
                            </td>
                            {bulkMode && (
                              <td className="px-4 py-2 text-center">
                                <input
                                  type="number"
                                  min={0} max={100} step={0.5}
                                  placeholder={perf?.perform_score?.toFixed(1) || '0–100'}
                                  value={bulkVal.perform_score ?? ''}
                                  onChange={e => setBulkScores(prev => ({
                                    ...prev,
                                    [empId]: { ...prev[empId], perform_score: e.target.value }
                                  }))}
                                  className="w-20 text-center rounded border border-foreground/10 bg-foreground/5 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none"
                                />
                              </td>
                            )}
                            <td className="px-4 py-3 text-xs text-muted-foreground">
                              {bulkMode ? (
                                <input
                                  type="text"
                                  placeholder="Catatan..."
                                  value={bulkVal.notes ?? ''}
                                  onChange={e => setBulkScores(prev => ({
                                    ...prev,
                                    [empId]: { ...prev[empId], notes: e.target.value }
                                  }))}
                                  className="w-full rounded border border-foreground/10 bg-foreground/5 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none"
                                />
                              ) : (
                                perf?.notes || '—'
                              )}
                            </td>
                            {!bulkMode && (
                              <td className="px-4 py-3">
                                <Button size="sm" variant="outline" className="h-7 text-xs"
                                  onClick={() => setPerformDialog({
                                    period_id: selectedPeriod.period_id,
                                    employee_id: empId,
                                    employee_name: emp?.name,
                                    perform_score: perf?.perform_score || 0,
                                    items: perf?.items || [{ label: 'KPI Utama', target: 100, actual: 0, score: 0, weight: 1 }],
                                    notes: perf?.notes || '',
                                  })}>
                                  {perf ? <><Edit2 className="w-3 h-3 mr-1" />Edit</> : <><Plus className="w-3 h-3 mr-1" />Input</>}
                                </Button>
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 4: MONITOR PROGRESS ───────────────────────────── */}
        <TabsContent value="monitor" className="space-y-4 mt-4">
          {!selectedPeriod ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>Pilih periode terlebih dahulu di tab Periode</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <p className="font-medium">{selectedPeriod.name} — Progress Pengisian</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => loadProgress(selectedPeriod.period_id)}>
                    <RefreshCw className="w-4 h-4 mr-1" /> Refresh
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className={fairnessData ? (
                      fairnessData.overall_severity === 'error' ? 'border-red-500/50 text-red-700 dark:text-red-400' :
                      fairnessData.overall_severity === 'warning' ? 'border-amber-500/50 text-amber-700 dark:text-amber-400' :
                      'border-emerald-500/50 text-emerald-600 dark:text-emerald-400'
                    ) : 'border-foreground/20'}
                    onClick={() => loadFairness(selectedPeriod.period_id)}
                    disabled={fairnessLoading}
                  >
                    {fairnessLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}
                    Cek Fairness
                    {fairnessData && (
                      <span className={`ml-1 text-xs font-bold ${
                        fairnessData.overall_severity === 'error' ? 'text-red-700 dark:text-red-400' :
                        fairnessData.overall_severity === 'warning' ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}>
                        {fairnessData.overall_severity === 'error' ? `${fairnessData.errors_count}E` :
                         fairnessData.overall_severity === 'warning' ? `${fairnessData.warnings_count}W` : '✓'}
                      </span>
                    )}
                  </Button>
                </div>
              </div>

              {/* Fairness panel */}
              {fairnessData && (
                <div className={`rounded-xl border p-4 space-y-3 ${
                  fairnessData.overall_severity === 'error' ? 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5' :
                  fairnessData.overall_severity === 'warning' ? 'border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5' :
                  'border-emerald-400 dark:border-emerald-500/30 bg-emerald-100 dark:bg-emerald-500/5'
                }`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-medium text-sm flex items-center gap-2">
                        {fairnessData.overall_severity === 'ok'
                          ? <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          : fairnessData.overall_severity === 'warning'
                          ? <AlertCircle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
                          : <AlertCircle className="w-4 h-4 text-red-700 dark:text-red-400" />}
                        Hasil Peer Review Fairness Check
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">{fairnessData.summary}</p>
                    </div>
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setFairnessData(null)}>
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>

                  {fairnessData.issues?.length > 0 ? (
                    <div className="space-y-2">
                      {fairnessData.issues.map(item => (
                        <div key={item.employee_id} className="rounded-lg border border-foreground/10 bg-foreground/5 p-3">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-medium text-sm">
                              {item.employee_name}
                              <span className="text-xs text-muted-foreground ml-2">{item.employee_code}</span>
                            </span>
                            <span className={`text-xs font-bold ${
                              item.severity === 'error' ? 'text-red-700 dark:text-red-400' :
                              item.severity === 'warning' ? 'text-amber-700 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'
                            }`}>
                              {item.reviewer_count} reviewer(s)
                            </span>
                          </div>
                          <div className="space-y-1">
                            {item.issues.map((iss, i) => (
                              <div key={i} className={`flex items-start gap-2 text-xs rounded px-2 py-1 ${
                                iss.severity === 'error' ? 'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-300' : 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300'
                              }`}>
                                <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                                <span>{iss.message}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-3 text-emerald-600 dark:text-emerald-400 text-sm">
                      ✅ Semua {fairnessData.total_participants} karyawan lulus fairness check — tidak ada masalah ditemukan.
                    </div>
                  )}
                </div>
              )}

              {progressData?.progress && (
                <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                        <th className="text-left px-4 py-3">Karyawan</th>
                        <th className="text-center px-4 py-3">Self</th>
                        <th className="text-center px-4 py-3">Peer</th>
                        <th className="text-center px-4 py-3">Staff→Sup</th>
                        <th className="text-center px-4 py-3">Sup Review</th>
                        <th className="text-center px-4 py-3">Perform</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {progressData.progress.map(p => (
                        <tr key={p.employee_id} className="hover:bg-foreground/5">
                          <td className="px-4 py-3">
                            <div className="font-medium">{p.employee_name}</div>
                            <div className="text-xs text-muted-foreground">{p.employee_code} · {p.department}</div>
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.self_done ? <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mx-auto" /> : <Clock className="w-4 h-4 text-amber-400/60 mx-auto" />}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={p.peer_done === p.peer_total && p.peer_total > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}>
                              {p.peer_done}/{p.peer_total}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.staff_to_sup_done ? <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mx-auto" /> : <Clock className="w-4 h-4 text-amber-400/60 mx-auto" />}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.supervisor_reviewed ? <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mx-auto" /> : <Clock className="w-4 h-4 text-amber-400/60 mx-auto" />}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.perform_input ? (
                              <span className="text-indigo-600 dark:text-indigo-400 font-medium">{fmtScore(p.perform_score)}</span>
                            ) : (
                              <AlertCircle className="w-4 h-4 text-red-400/60 mx-auto" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 5: LAPORAN & FINALISASI ────────────────────────── */}
        <TabsContent value="reports" className="space-y-4 mt-4">
          {!selectedPeriod ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>Pilih periode terlebih dahulu di tab Periode</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <p className="font-medium">{selectedPeriod.name}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => loadReport(selectedPeriod.period_id)}>
                    <RefreshCw className="w-4 h-4 mr-1" /> Refresh
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleCalculate} disabled={calculating}>
                    {calculating ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <BarChart3 className="w-4 h-4 mr-1" />}
                    Hitung KPI
                  </Button>
                  {selectedPeriod.status === 'closed' && (
                    <Button size="sm" onClick={handlePublish} className="bg-emerald-600 hover:bg-emerald-700">
                      <Send className="w-4 h-4 mr-1" /> Publish Hasil
                    </Button>
                  )}
                  {selectedPeriod.status === 'finalized' && (
                    <Button
                      size="sm"
                      onClick={handleGenerateRaiseProposals}
                      disabled={generatingRaise}
                      className="bg-indigo-600 hover:bg-indigo-700"
                      data-testid="kpi-generate-raise-btn"
                    >
                      {generatingRaise ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Award className="w-4 h-4 mr-1" />}
                      Generate Kenaikan Gaji
                    </Button>
                  )}
                </div>
              </div>

              {reportData && reportData.finalized_count > 0 && (
                <>
                  {/* Summary cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                      { label: 'Rata-rata KPI', value: fmtPct(reportData.summary.avg_kpi), color: 'text-indigo-600 dark:text-indigo-400' },
                      { label: 'Rata-rata Perform', value: fmtPct(reportData.summary.avg_perform), color: 'text-blue-600 dark:text-blue-400' },
                      { label: 'Rata-rata Attitude', value: fmtPct(reportData.summary.avg_attitude), color: 'text-violet-600 dark:text-violet-400' },
                      { label: 'Rata-rata Absensi', value: fmtPct(reportData.summary.avg_absensi), color: 'text-emerald-600 dark:text-emerald-400' },
                    ].map(card => (
                      <div key={card.label} className="rounded-xl border border-foreground/10 bg-foreground/5 p-3 text-center">
                        <div className={`text-xl font-bold ${card.color}`}>{card.value}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{card.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Grade distribution */}
                  <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                    <p className="text-sm font-medium mb-3">Distribusi Grade</p>
                    <div className="flex gap-3 flex-wrap">
                      {Object.entries(reportData.summary.grade_distribution).map(([g, cnt]) => (
                        <div key={g} className="flex items-center gap-2">
                          <GradeBadge grade={g} />
                          <span className="text-sm font-bold">{cnt}</span>
                          <span className="text-xs text-muted-foreground">({GRADE_CFG[g]?.label})</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Detail table */}
                  <div className="rounded-xl border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-foreground/10 text-xs text-muted-foreground">
                          <th className="text-left px-4 py-3">Karyawan</th>
                          <th className="text-center px-4 py-3">Perform</th>
                          <th className="text-center px-4 py-3">Attitude</th>
                          <th className="text-center px-4 py-3">Absensi</th>
                          <th className="text-center px-4 py-3">KPI Final</th>
                          <th className="text-center px-4 py-3">Grade</th>
                          <th className="text-center px-4 py-3">Status</th>
                          <th className="text-center px-4 py-3">PDF</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {reportData.details.map(r => (
                          <tr key={r.employee_id} className="hover:bg-foreground/5 cursor-pointer"
                            onClick={() => setResultDialog(r)}>
                            <td className="px-4 py-3">
                              <div className="font-medium">{r.employee_name}</div>
                              <div className="text-xs text-muted-foreground">{r.employee_code}</div>
                            </td>
                            <td className="px-4 py-3 text-center font-medium">{fmtScore(r.perform_score)}</td>
                            <td className="px-4 py-3 text-center font-medium">{fmtScore(r.attitude_score)}</td>
                            <td className="px-4 py-3 text-center font-medium">{fmtScore(r.absensi_score)}</td>
                            <td className="px-4 py-3 text-center">
                              <span className="font-bold text-indigo-600 dark:text-indigo-400">{fmtScore(r.kpi_final)}</span>
                            </td>
                            <td className="px-4 py-3 text-center"><GradeBadge grade={r.grade} /></td>
                            <td className="px-4 py-3 text-center">
                              <span className={`text-xs ${r.publish_status === 'published' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}`}>
                                {r.publish_status === 'published' ? 'Published' : 'Draft'}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-7 w-7"
                                title="Export PDF"
                                onClick={e => {
                                  e.stopPropagation();
                                  window.open(`${API}/api/dewi/kpi/results/${selectedPeriod.period_id}/${r.employee_id}/pdf?token=${token}`, '_blank');
                                }}
                              >
                                <Download className="w-3.5 h-3.5 text-muted-foreground" />
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              {(!reportData || reportData.finalized_count === 0) && (
                <div className="text-center py-12 text-muted-foreground">
                  <BarChart3 className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>Hasil KPI belum dihitung</p>
                  <p className="text-xs mt-1">Klik "Hitung KPI" untuk kalkulasi otomatis</p>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── TAB 6: TREN KPI ──────────────────────────────────────── */}
        <TabsContent value="trend" className="space-y-4 mt-4">
          <div className="flex flex-wrap items-center gap-3 justify-between">
            <p className="font-medium text-sm">Tren KPI Historis</p>
            <div className="flex gap-2">
              <SmartNativeSelect
                className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
                value={trendEmployeeId}
                onChange={e => { setTrendEmployeeId(e.target.value); if (e.target.value) loadTrend(e.target.value); }}
              >
                <option value="">-- Pilih Karyawan --</option>
                {employees.map(e => (
                  <option key={e.id} value={e.id}>{e.employee_code} — {e.name}</option>
                ))}
              </SmartNativeSelect>
              <Button size="sm" variant="outline" onClick={() => { loadCompanyTrend(); if (trendEmployeeId) loadTrend(trendEmployeeId); }}>
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Company-wide trend */}
          {companyTrend?.trend && companyTrend.trend.length > 0 && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-xs text-muted-foreground mb-3 font-medium">📊 Rata-rata KPI Perusahaan ({companyTrend.trend.length} Periode Terakhir)</p>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={companyTrend.trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="period_name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                    labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
                    formatter={(v, name) => [`${Number(v).toFixed(1)}`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="company_avg" stroke="#6366f1" strokeWidth={2} dot={{ r: 4 }} name="Avg KPI" />
                </LineChart>
              </ResponsiveContainer>

              {/* Grade distribution chart */}
              <p className="text-xs text-muted-foreground mt-4 mb-2 font-medium">Distribusi Grade per Periode</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={companyTrend.trend} barSize={12}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="period_name" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="grade_distribution.A" fill="#10b981" name="Grade A" stackId="a" />
                  <Bar dataKey="grade_distribution.B" fill="#3b82f6" name="Grade B" stackId="a" />
                  <Bar dataKey="grade_distribution.C" fill="#f59e0b" name="Grade C" stackId="a" />
                  <Bar dataKey="grade_distribution.D" fill="#f97316" name="Grade D" stackId="a" />
                  <Bar dataKey="grade_distribution.E" fill="#ef4444" name="Grade E" stackId="a" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Individual employee trend */}
          {trendEmployeeId && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
              <p className="text-xs text-muted-foreground mb-3 font-medium">
                📈 Tren Individual — {employees.find(e => e.id === trendEmployeeId)?.name || trendEmployeeId}
                {trendData?.department && <span className="ml-2 text-indigo-600 dark:text-indigo-400">({trendData.department})</span>}
              </p>
              {trendLoading && <div className="py-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-indigo-600 dark:text-indigo-400" /></div>}
              {!trendLoading && trendData?.trend && trendData.trend.length > 0 && (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={trendData.trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="period_name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                      <Tooltip
                        contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                        formatter={(v, name) => [v !== null ? `${Number(v).toFixed(1)}` : '—', name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="kpi_final" stroke="#6366f1" strokeWidth={2} dot={{ r: 4 }} name="KPI Final" connectNulls />
                      <Line type="monotone" dataKey="perform_score" stroke="#3b82f6" strokeWidth={1.5} dot={{ r: 3 }} name="Perform" connectNulls strokeDasharray="4 2" />
                      <Line type="monotone" dataKey="attitude_score" stroke="#8b5cf6" strokeWidth={1.5} dot={{ r: 3 }} name="Attitude" connectNulls strokeDasharray="4 2" />
                      <Line type="monotone" dataKey="dept_avg" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Dept Avg" strokeDasharray="6 3" />
                    </LineChart>
                  </ResponsiveContainer>
                  {/* Data table */}
                  <div className="mt-3 rounded-lg border overflow-hidden border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-foreground/10 text-muted-foreground bg-foreground/5">
                          <th className="text-left px-3 py-2">Periode</th>
                          <th className="text-center px-3 py-2">KPI Final</th>
                          <th className="text-center px-3 py-2">Perform</th>
                          <th className="text-center px-3 py-2">Attitude</th>
                          <th className="text-center px-3 py-2">Absensi</th>
                          <th className="text-center px-3 py-2">Grade</th>
                          <th className="text-center px-3 py-2">Dept Avg</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {trendData.trend.map(row => (
                          <tr key={row.period_id} className="hover:bg-foreground/5">
                            <td className="px-3 py-2 font-medium">{row.period_name}</td>
                            <td className="px-3 py-2 text-center font-bold text-indigo-600 dark:text-indigo-400">{fmtScore(row.kpi_final)}</td>
                            <td className="px-3 py-2 text-center">{fmtScore(row.perform_score)}</td>
                            <td className="px-3 py-2 text-center">{fmtScore(row.attitude_score)}</td>
                            <td className="px-3 py-2 text-center">{fmtScore(row.absensi_score)}</td>
                            <td className="px-3 py-2 text-center"><GradeBadge grade={row.grade} /></td>
                            <td className="px-3 py-2 text-center text-amber-700 dark:text-amber-400">{fmtScore(row.dept_avg)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {!trendLoading && (!trendData?.trend || trendData.trend.length === 0) && (
                <p className="text-center py-8 text-muted-foreground text-sm">Belum ada data KPI untuk karyawan ini.</p>
              )}
            </div>
          )}

          {!trendEmployeeId && !companyTrend?.trend?.length && (
            <div className="text-center py-16 text-muted-foreground">
              <Activity className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Pilih karyawan untuk melihat tren KPI individual</p>
              <p className="text-xs mt-1">Atau tunggu data perusahaan termuat</p>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 7: GOALS ─────────────────────────────────────────── */}
        <TabsContent value="goals" className="space-y-4 mt-4">
          <div className="flex flex-wrap items-center gap-3 justify-between">
            <p className="font-medium text-sm flex items-center gap-2"><Flag className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> Goal Setting & Progress Tracking</p>
            <div className="flex gap-2 flex-wrap">
              <SmartNativeSelect
                className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
                value={goalsPeriodId}
                onChange={e => { setGoalsPeriodId(e.target.value); loadGoals(e.target.value, goalsEmployeeId); }}
              >
                <option value="">-- Semua Periode --</option>
                {periods.map(p => <option key={p.period_id} value={p.period_id}>{p.name}</option>)}
              </SmartNativeSelect>
              <SmartNativeSelect
                className="text-xs rounded border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-foreground"
                value={goalsEmployeeId}
                onChange={e => { setGoalsEmployeeId(e.target.value); loadGoals(goalsPeriodId, e.target.value); }}
              >
                <option value="">-- Semua Karyawan --</option>
                {employees.map(e => <option key={e.id} value={e.id}>{e.employee_code} — {e.name}</option>)}
              </SmartNativeSelect>
              <Button size="sm" onClick={() => setGoalDialog({ period_id: goalsPeriodId, employee_id: goalsEmployeeId })}
                className="bg-emerald-600 hover:bg-emerald-700">
                <Plus className="w-4 h-4 mr-1" /> Tambah Goal
              </Button>
            </div>
          </div>

          {goalsLoading && <div className="py-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-emerald-600 dark:text-emerald-400" /></div>}

          {!goalsLoading && goals.length > 0 && (
            <div className="space-y-3">
              {goalsPg.paged.map(goal => {
                const pct = goal.progress_pct || 0;
                const statusCfg = {
                  achieved: { color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500', label: '✅ Tercapai' },
                  on_track: { color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-500', label: '🔵 On Track' },
                  at_risk: { color: 'text-amber-700 dark:text-amber-400', bg: 'bg-amber-500', label: '⚠️ At Risk' },
                  missed: { color: 'text-red-700 dark:text-red-400', bg: 'bg-red-500', label: '❌ Missed' },
                }[goal.status] || { color: 'text-muted-foreground', bg: 'bg-muted', label: '—' };

                return (
                  <div key={goal.goal_id} className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="font-medium text-sm">{goal.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {goal.employee_name} · {goal.period_name}
                          {goal.description && <span> · {goal.description}</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className={`text-xs font-medium ${statusCfg.color}`}>{statusCfg.label}</span>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setGoalDialog(goal)}>
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7"
                          onClick={async () => {
                            if (!window.confirm('Hapus goal ini?')) return;
                            await kpi(`/goals/${goal.goal_id}`, { method: 'DELETE', headers });
                            toast.success('Goal dihapus');
                            loadGoals(goalsPeriodId, goalsEmployeeId);
                          }}>
                          <Trash2 className="w-3.5 h-3.5 text-red-700 dark:text-red-400" />
                        </Button>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-muted-foreground">Progress</span>
                          <span className="font-medium">{goal.actual_value} / {goal.target_value} {goal.unit}</span>
                        </div>
                        <div className="w-full bg-foreground/10 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${statusCfg.bg}`}
                            style={{ width: `${Math.min(100, pct)}%` }}
                          />
                        </div>
                        <div className="text-right text-xs mt-1 font-bold">{pct.toFixed(1)}%</div>
                      </div>
                    </div>
                  </div>
                );
              })}
              {goalsPg.total > 0 && <PaginationLite page={goalsPg.page} totalPages={goalsPg.totalPages} total={goalsPg.total} pageSize={goalsPg.pageSize} onPageChange={goalsPg.setPage} />}
            </div>
          )}

          {!goalsLoading && goals.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Flag className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Belum ada goals untuk filter yang dipilih</p>
              <p className="text-xs mt-1">Klik "Tambah Goal" untuk mulai membuat goals karyawan</p>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 8: GAMIFIKASI ─────────────────────────────────── */}
        <TabsContent value="gamifikasi" className="mt-4">
          <div className="mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <Trophy className="w-5 h-5 text-yellow-500" /> Gamifikasi KPI
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              Leaderboard, badge, dan achievement system untuk memotivasi karyawan
            </p>
          </div>
          <KPIGamificationTab token={token} periods={periods} isHR={true} />
        </TabsContent>
      </Tabs>

      {/* ── PERIOD DIALOG ────────────────────────────────────────── */}
      {periodDialog !== null && (
        <PeriodDialog
          initial={periodDialog}
          employees={employees}
          headers={headers}
          onSave={handleSavePeriod}
          onClose={() => setPeriodDialog(null)}
        />
      )}

      {/* ── QUESTION DIALOG ──────────────────────────────────────── */}
      {questionDialog !== null && (
        <QuestionDialog
          initial={questionDialog}
          onSave={handleSaveQuestion}
          onClose={() => setQuestionDialog(null)}
        />
      )}

      {/* ── PERFORM DIALOG ───────────────────────────────────────── */}
      {performDialog !== null && (
        <PerformDialog
          initial={performDialog}
          employees={employees}
          onSave={handleSavePerform}
          onClose={() => setPerformDialog(null)}
        />
      )}

      {/* ── RESULT DETAIL DIALOG ─────────────────────────────────── */}
      {resultDialog !== null && (
        <ResultDetailDialog
          result={resultDialog}
          onClose={() => setResultDialog(null)}
        />
      )}

      {/* ── GOAL DIALOG ──────────────────────────────────────────── */}
      {goalDialog !== null && (
        <GoalDialog
          initial={goalDialog}
          periods={periods}
          employees={employees}
          headers={headers}
          onSave={async (form) => {
            const isEdit = !!form.goal_id;
            const r = await kpi(
              isEdit ? `/goals/${form.goal_id}` : '/goals',
              { method: isEdit ? 'PUT' : 'POST', headers, body: JSON.stringify(form) }
            );
            const d = await r.json();
            if (!r.ok) { toast.error(d.detail || 'Gagal menyimpan goal'); return; }
            toast.success(isEdit ? 'Goal diupdate' : 'Goal berhasil dibuat');
            setGoalDialog(null);
            loadGoals(goalsPeriodId, goalsEmployeeId);
          }}
          onClose={() => setGoalDialog(null)}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════

function PeriodDialog({ initial, employees, headers, onSave, onClose }) {
  const [form, setForm] = useState({
    name: '', period_from: '', period_to: '', working_days: 26,
    notes: '', participant_employee_ids: [], supervisor_assignments: [],
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  const toggleEmployee = (empId) => {
    setForm(f => ({
      ...f,
      participant_employee_ids: f.participant_employee_ids.includes(empId)
        ? f.participant_employee_ids.filter(id => id !== empId)
        : [...f.participant_employee_ids, empId],
    }));
  };

  const selectAll = () => setForm(f => ({ ...f, participant_employee_ids: employees.map(e => e.id) }));
  const clearAll = () => setForm(f => ({ ...f, participant_employee_ids: [] }));

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{form.period_id ? 'Edit Periode' : 'Buat Periode KPI'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label>Nama Periode <span className="text-red-700 dark:text-red-400">*</span></Label>
            <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="KPI Januari 2026" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Tanggal Mulai</Label>
              <Input type="date" value={form.period_from}
                onChange={e => setForm(f => ({ ...f, period_from: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Tanggal Selesai</Label>
              <Input type="date" value={form.period_to}
                onChange={e => setForm(f => ({ ...f, period_to: e.target.value }))} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Jumlah Hari Kerja</Label>
            <Input type="number" value={form.working_days} min={1} max={31}
              onChange={e => setForm(f => ({ ...f, working_days: parseInt(e.target.value) || 26 }))} />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Peserta ({form.participant_employee_ids.length} dipilih)</Label>
              <div className="flex gap-2">
                <button type="button" onClick={selectAll}
                  className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">Pilih Semua</button>
                <span className="text-muted-foreground text-xs">·</span>
                <button type="button" onClick={clearAll}
                  className="text-xs text-red-700 dark:text-red-400 hover:underline">Kosongkan</button>
              </div>
            </div>
            <div className="rounded-lg border border-foreground/10 max-h-48 overflow-y-auto divide-y divide-white/5">
              {employees.map(emp => (
                <label key={emp.id} className="flex items-center gap-3 px-3 py-2 hover:bg-foreground/5 cursor-pointer">
                  <input type="checkbox"
                    checked={form.participant_employee_ids.includes(emp.id)}
                    onChange={() => toggleEmployee(emp.id)}
                    className="rounded"
                  />
                  <span className="text-sm">{emp.employee_code} — {emp.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">{emp.job_title}</span>
                </label>
              ))}
              {employees.length === 0 && (
                <p className="text-xs text-muted-foreground px-3 py-4 text-center">
                  Belum ada data karyawan
                </p>
              )}
            </div>
          </div>

          <div className="space-y-1">
            <Label>Catatan</Label>
            <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Catatan optional..." rows={2} />
          </div>

          {/* Supervisor Assignments */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Penugasan Supervisor ({form.supervisor_assignments.length} grup)</Label>
              <button type="button"
                onClick={() => setForm(f => ({
                  ...f,
                  supervisor_assignments: [
                    ...f.supervisor_assignments,
                    { supervisor_employee_id: '', employee_ids: [] }
                  ]
                }))}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                + Tambah Supervisor
              </button>
            </div>
            {form.supervisor_assignments.length === 0 && (
              <p className="text-xs text-muted-foreground">Tidak ada supervisor assignment — staff→supervisor form tidak akan muncul.</p>
            )}
            {form.supervisor_assignments.map((sa, i) => (
              <div key={i} className="rounded-lg border border-foreground/10 bg-foreground/5 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">Supervisor {i + 1}</span>
                  <button type="button"
                    onClick={() => setForm(f => ({ ...f, supervisor_assignments: f.supervisor_assignments.filter((_, idx) => idx !== i) }))}
                    className="text-xs text-red-700 dark:text-red-400 hover:underline">Hapus</button>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Supervisor</Label>
                  <SmartNativeSelect
                    value={sa.supervisor_employee_id}
                    onChange={e => setForm(f => ({
                      ...f,
                      supervisor_assignments: f.supervisor_assignments.map((s, idx) =>
                        idx === i ? { ...s, supervisor_employee_id: e.target.value } : s
                      )
                    }))}
                    className="w-full h-8 px-2 rounded border border-foreground/10 bg-foreground/5 text-xs"
                  >
                    <option value="">-- Pilih Supervisor --</option>
                    {employees.map(e => (
                      <option key={e.id} value={e.id}>{`${e.employee_code} — ${e.name}`}</option>
                    ))}
                  </SmartNativeSelect>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Bawahan (pilih dari peserta)</Label>
                  <div className="rounded border border-foreground/10 max-h-32 overflow-y-auto divide-y divide-white/5">
                    {employees.filter(e => form.participant_employee_ids.includes(e.id) && e.id !== sa.supervisor_employee_id).map(emp => (
                      <label key={emp.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-foreground/5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={sa.employee_ids.includes(emp.id)}
                          onChange={e => {
                            const newIds = e.target.checked
                              ? [...sa.employee_ids, emp.id]
                              : sa.employee_ids.filter(id => id !== emp.id);
                            setForm(f => ({
                              ...f,
                              supervisor_assignments: f.supervisor_assignments.map((s, idx) =>
                                idx === i ? { ...s, employee_ids: newIds } : s
                              )
                            }));
                          }}
                          className="rounded"
                        />
                        <span className="text-xs">{emp.employee_code} — {emp.name}</span>
                      </label>
                    ))}
                    {employees.filter(e => form.participant_employee_ids.includes(e.id) && e.id !== sa.supervisor_employee_id).length === 0 && (
                      <p className="text-xs text-muted-foreground px-2 py-2">Tambahkan peserta terlebih dahulu</p>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{sa.employee_ids.length} bawahan dipilih</p>
                </div>
              </div>
            ))}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function QuestionDialog({ initial, onSave, onClose }) {
  const [form, setForm] = useState({
    eval_type: 'self', category: '', category_weight: 0.10,
    question_text: '', order: 99,
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{form.question_id ? 'Edit Pertanyaan' : 'Tambah Pertanyaan'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label>Tipe Evaluasi</Label>
            <Select value={form.eval_type} onValueChange={v => setForm(f => ({ ...f, eval_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(EVAL_TYPE_CFG).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v.label} ({v.weight})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Kategori</Label>
              <Input value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="misal: Tanggung Jawab" required />
            </div>
            <div className="space-y-1">
              <Label>Bobot Kategori (0-1)</Label>
              <Input type="number" value={form.category_weight} step={0.05} min={0.01} max={1}
                onChange={e => setForm(f => ({ ...f, category_weight: parseFloat(e.target.value) || 0.10 }))} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Teks Pertanyaan</Label>
            <Textarea value={form.question_text}
              onChange={e => setForm(f => ({ ...f, question_text: e.target.value }))}
              placeholder="Tuliskan pertanyaan..." rows={3} required />
          </div>
          <div className="space-y-1">
            <Label>Urutan</Label>
            <Input type="number" value={form.order} min={1}
              onChange={e => setForm(f => ({ ...f, order: parseInt(e.target.value) || 99 }))} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PerformDialog({ initial, employees, onSave, onClose }) {
  const [form, setForm] = useState({
    period_id: '', employee_id: '', employee_name: '',
    items: [{ label: 'KPI Utama', target: 100, actual: 0, score: 0, weight: 1 }],
    notes: '',
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const totalWeight = form.items.reduce((sum, it) => sum + (parseFloat(it.weight) || 0), 0);
  const weightedScore = totalWeight > 0
    ? form.items.reduce((sum, it) => sum + (parseFloat(it.score) || 0) * (parseFloat(it.weight) || 0), 0) / totalWeight
    : 0;

  const addItem = () => setForm(f => ({
    ...f,
    items: [...f.items, { label: 'KPI Baru', target: 100, actual: 0, score: 0, weight: 1 }],
  }));
  const removeItem = (i) => setForm(f => ({ ...f, items: f.items.filter((_, idx) => idx !== i) }));
  const updateItem = (i, key, val) => setForm(f => ({
    ...f,
    items: f.items.map((it, idx) => idx === i ? { ...it, [key]: val } : it),
  }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave({ ...form, perform_score: Math.round(weightedScore * 10) / 10 });
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Input Nilai Perform</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!form.employee_id && (
            <div className="space-y-1">
              <Label>Karyawan</Label>
              <Select value={form.employee_id}
                onValueChange={v => {
                  const emp = employees.find(e => e.id === v);
                  setForm(f => ({ ...f, employee_id: v, employee_name: emp?.name || '' }));
                }}>
                <SelectTrigger><SelectValue placeholder="Pilih karyawan" /></SelectTrigger>
                <SelectContent>
                  {employees.map(e => (
                    <SelectItem key={e.id} value={e.id}>{e.employee_code} — {e.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {form.employee_name && (
            <div className="rounded-lg bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-300 dark:border-indigo-500/20 px-3 py-2 text-sm">
              Karyawan: <span className="font-semibold text-indigo-600 dark:text-indigo-300">{form.employee_name}</span>
            </div>
          )}

          {/* KPI Items */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Item KPI ({form.items.length} item)</Label>
              <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={addItem}>
                <Plus className="w-3 h-3 mr-1" /> Tambah Item
              </Button>
            </div>
            <div className="space-y-2">
              {form.items.map((item, i) => (
                <div key={i} className="rounded-lg border border-foreground/10 bg-foreground/5 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <Input value={item.label} onChange={e => updateItem(i, 'label', e.target.value)}
                      placeholder="Nama KPI" className="h-7 text-xs flex-1 mr-2" />
                    <Button type="button" size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400 shrink-0"
                      onClick={() => removeItem(i)}>
                      <X className="w-3 h-3" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <Label className="text-xs">Skor (0-100)</Label>
                      <Input type="number" value={item.score} min={0} max={100}
                        onChange={e => updateItem(i, 'score', parseFloat(e.target.value) || 0)}
                        className="h-7 text-xs" />
                    </div>
                    <div>
                      <Label className="text-xs">Bobot</Label>
                      <Input type="number" value={item.weight} min={0.1} step={0.1}
                        onChange={e => updateItem(i, 'weight', parseFloat(e.target.value) || 1)}
                        className="h-7 text-xs" />
                    </div>
                    <div>
                      <Label className="text-xs">Catatan</Label>
                      <Input value={item.notes || ''} onChange={e => updateItem(i, 'notes', e.target.value)}
                        placeholder="opsional" className="h-7 text-xs" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Calculated score preview */}
          <div className="rounded-xl bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-300 dark:border-indigo-500/20 px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-indigo-600 dark:text-indigo-300">Nilai Perform Terhitung:</span>
            <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">{weightedScore.toFixed(1)}</span>
          </div>

          <div className="space-y-1">
            <Label>Catatan Supervisor</Label>
            <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Catatan evaluasi..." rows={2} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving || !form.employee_id}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResultDetailDialog({ result, onClose }) {
  const g = GRADE_CFG[result.grade] || {};
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Detail KPI — {result.employee_name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* Final score */}
          <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4 text-center">
            <div className="text-5xl font-bold text-indigo-600 dark:text-indigo-400 mb-1">{fmtScore(result.kpi_final)}</div>
            <div className="text-sm text-muted-foreground">KPI Final (dari 100)</div>
            {result.grade && (
              <div className={`inline-flex items-center gap-2 mt-2 px-3 py-1 rounded-full text-sm font-semibold border ${g.color}`}>
                <Award className="w-4 h-4" />
                Grade {result.grade} — {g.label}
              </div>
            )}
          </div>

          {/* Component breakdown */}
          <div className="space-y-3">
            {[
              { label: 'Perform (60%)', score: result.perform_score, color: 'bg-blue-500' },
              { label: 'Attitude (20%)', score: result.attitude_score, color: 'bg-violet-500' },
              { label: 'Absensi (20%)', score: result.absensi_score, color: 'bg-emerald-500' },
            ].map(c => (
              <div key={c.label} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{c.label}</span>
                  <span className="font-medium">{fmtScore(c.score)}</span>
                </div>
                <ScoreBar score={c.score || 0} color={c.color} />
              </div>
            ))}
          </div>

          {/* Absensi detail */}
          {result.absensi_detail && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-3">
              <p className="text-xs font-medium mb-2 text-muted-foreground">Detail Absensi</p>
              <div className="grid grid-cols-3 gap-2 text-xs">
                {Object.entries(result.absensi_detail.breakdown || {}).map(([k, v]) => (
                  v > 0 && <div key={k} className="flex justify-between">
                    <span className="capitalize text-muted-foreground">{k}</span>
                    <span className="font-medium">{v}</span>
                  </div>
                ))}
                <div className="flex justify-between col-span-3 pt-1 border-t border-foreground/10 mt-1">
                  <span className="text-muted-foreground">Hari Tidak Hadir</span>
                  <span className="font-medium">{result.absensi_detail.absent_days || 0} / {result.absensi_detail.working_days}</span>
                </div>
              </div>
            </div>
          )}

          {/* Status and recommendations */}
          {result.status_kpi && (
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Status</span>
                <span className="font-medium">{result.status_kpi}</span>
              </div>
              {result.raise_pct > 0 && (
                <div className="flex justify-between text-sm mt-1">
                  <span className="text-muted-foreground">Kenaikan Gaji</span>
                  <span className="font-medium text-emerald-600 dark:text-emerald-400">{result.raise_pct}%</span>
                </div>
              )}
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


// ─── GOAL DIALOG ──────────────────────────────────────────────────────────────
function GoalDialog({ initial, periods, employees, headers, onSave, onClose }) {
  const [form, setForm] = useState({
    period_id: '',
    employee_id: '',
    title: '',
    description: '',
    target_value: 100,
    unit: '',
    actual_value: 0,
    notes: '',
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const progress = form.target_value > 0
    ? Math.min(100, Math.round((form.actual_value / form.target_value) * 100))
    : 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Flag className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            {form.goal_id ? 'Edit Goal' : 'Tambah Goal'}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Periode</Label>
              <SmartNativeSelect
                className="w-full text-xs rounded border border-foreground/10 bg-foreground/5 px-2 py-1.5 text-foreground"
                value={form.period_id}
                onChange={e => setForm(f => ({ ...f, period_id: e.target.value }))}
                required
              >
                <option value="">-- Pilih Periode --</option>
                {periods.map(p => <option key={p.period_id} value={p.period_id}>{p.name}</option>)}
              </SmartNativeSelect>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Karyawan</Label>
              <SmartNativeSelect
                className="w-full text-xs rounded border border-foreground/10 bg-foreground/5 px-2 py-1.5 text-foreground"
                value={form.employee_id}
                onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}
                required
              >
                <option value="">-- Pilih Karyawan --</option>
                {employees.map(e => <option key={e.id} value={e.id}>{e.employee_code} — {e.name}</option>)}
              </SmartNativeSelect>
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Judul Goal</Label>
            <Input
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="contoh: Produksi 1000 pcs per bulan"
              required
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Deskripsi (opsional)</Label>
            <Textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Penjelasan lebih lanjut tentang goal ini..."
              rows={2}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Target</Label>
              <Input
                type="number"
                value={form.target_value}
                min={0}
                step={0.1}
                onChange={e => setForm(f => ({ ...f, target_value: parseFloat(e.target.value) || 0 }))}
                required
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Aktual</Label>
              <Input
                type="number"
                value={form.actual_value}
                min={0}
                step={0.1}
                onChange={e => setForm(f => ({ ...f, actual_value: parseFloat(e.target.value) || 0 }))}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Satuan</Label>
              <Input
                value={form.unit}
                onChange={e => setForm(f => ({ ...f, unit: e.target.value }))}
                placeholder="pcs, %, dll"
              />
            </div>
          </div>

          {/* Progress preview */}
          <div className="rounded-lg border border-foreground/10 bg-foreground/5 p-3">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-muted-foreground">Progress Preview</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">{progress}%</span>
            </div>
            <div className="w-full bg-foreground/10 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${
                  progress >= 100 ? 'bg-emerald-500' :
                  progress >= 70 ? 'bg-blue-500' :
                  progress >= 40 ? 'bg-amber-500' : 'bg-red-500'
                }`}
                style={{ width: `${Math.min(100, progress)}%` }}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Catatan</Label>
            <Textarea
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="Catatan tambahan..."
              rows={2}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Batal</Button>
            <Button type="submit" disabled={saving} className="bg-emerald-600 hover:bg-emerald-700">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
