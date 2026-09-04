import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Target, Users, ClipboardCheck, Plus, RefreshCw, Calendar, TrendingUp,
  Award, CheckCircle2, Clock, Edit2, Star,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { PageHeader, StatTile } from './moduleAtoms';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const CYCLE_STATUS_COLORS = {
  draft: 'bg-foreground/10 text-foreground/60 border-foreground/15',
  active: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25',
  closed: 'bg-blue-500/15 text-blue-300 border-blue-400/25',
};
const ASSIGNMENT_STATUS_COLORS = {
  assigned: 'bg-blue-500/15 text-blue-300',
  in_progress: 'bg-amber-500/15 text-amber-300',
  review: 'bg-purple-500/15 text-purple-300',
  completed: 'bg-emerald-500/15 text-emerald-300',
};
const REVIEW_STATUS_COLORS = {
  draft: 'bg-foreground/10 text-foreground/60',
  self_submitted: 'bg-blue-500/15 text-blue-300',
  manager_review: 'bg-amber-500/15 text-amber-300',
  finalized: 'bg-emerald-500/15 text-emerald-300',
};
const CATEGORY_LABELS = {
  sales: 'Sales', quality: 'Kualitas', attendance: 'Kehadiran',
  teamwork: 'Kerja Sama', innovation: 'Inovasi',
  productivity: 'Produktivitas', leadership: 'Kepemimpinan',
};

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';
const fmtScore = (n) => (n || 0).toFixed(2);

export default function HRPerformanceModule({ token, defaultTab = 'cycles' }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [activeTab, setActiveTab] = useState(defaultTab);

  const [summary, setSummary] = useState(null);
  const [cycles, setCycles] = useState([]);
  const [kpis, setKpis] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(false);

  // KPI Monthly Trend for review reference
  const [kpiTrend, setKpiTrend] = useState(null);
  const [kpiTrendLoading, setKpiTrendLoading] = useState(false);
  const [kpiDialog, setKpiDialog] = useState(null);
  // BUG-FIX 2026-07-25: state ini TIDAK PERNAH dideklarasikan padahal dipakai di
  // 12+ tempat (dialog "Siklus Baru"). Akibatnya render komponen langsung
  // ReferenceError: cycleDialog is not defined ⇒ modul HR Performance blank/crash.
  const [cycleDialog, setCycleDialog] = useState(null);
  const [reviewDialog, setReviewDialog] = useState(null);
  const [reviewActor, setReviewActor] = useState('self');
  const [reviewScores, setReviewScores] = useState([]);
  const [reviewOverallNotes, setReviewOverallNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c, k, a, r] = await Promise.all([
        fetch(`${API_BASE}/api/dewi/hris/performance/summary`, { headers }),
        fetch(`${API_BASE}/api/dewi/hris/performance/cycles`, { headers }),
        fetch(`${API_BASE}/api/dewi/hris/performance/kpis`, { headers }),
        fetch(`${API_BASE}/api/dewi/hris/performance/assignments`, { headers }),
        fetch(`${API_BASE}/api/dewi/hris/performance/reviews`, { headers }),
      ]);
      if (s.ok) setSummary(await s.json());
      if (c.ok) setCycles(await c.json());
      if (k.ok) setKpis(await k.json());
      if (a.ok) setAssignments(await a.json());
      if (r.ok) setReviews(await r.json());
    } catch (e) {
      toast.error('Gagal memuat data performance');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // ── Cycle save ──
  const saveCycle = async () => {
    if (!cycleDialog?.cycle_code || !cycleDialog?.name) { toast.error('Code & nama wajib diisi'); return; }
    setSubmitting(true);
    try {
      const r = await fetch(`${API_BASE}/api/dewi/hris/performance/cycles`, {
        method: 'POST', headers, body: JSON.stringify(cycleDialog),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success('Cycle berhasil dibuat');
      setCycleDialog(null);
      loadAll();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ── KPI save ──
  const saveKpi = async () => {
    if (!kpiDialog?.kpi_code || !kpiDialog?.name) { toast.error('Code & nama wajib diisi'); return; }
    setSubmitting(true);
    try {
      const r = await fetch(`${API_BASE}/api/dewi/hris/performance/kpis`, {
        method: 'POST', headers, body: JSON.stringify(kpiDialog),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal');
      toast.success('KPI template berhasil dibuat');
      setKpiDialog(null);
      loadAll();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ── Review open ──
  const openReviewDialog = async (review, actor = 'self') => {
    const assignment = assignments.find(a => a.id === review.assignment_id);
    const kpis = assignment?.kpis || [];
    const existingScores = actor === 'self' ? (review.self_scores || []) : (review.manager_scores || []);
    const existingNotes = actor === 'self' ? (review.self_overall_notes || '') : (review.manager_overall_notes || '');
    const scores = kpis.map(k => {
      const existing = existingScores.find(s => s.kpi_id === k.kpi_id);
      return {
        kpi_id: k.kpi_id,
        kpi_name: k.kpi_name,
        target_value: k.target_value,
        target_operator: k.target_operator,
        measurement: k.measurement,
        weight: k.weight,
        actual_value: existing?.actual_value ?? 0,
        rating: existing?.rating ?? 3,
        notes: existing?.notes ?? '',
      };
    });
    setReviewDialog({ ...review, _assignment: assignment });
    setReviewActor(actor);
    setReviewScores(scores);
    setReviewOverallNotes(existingNotes);
    setKpiTrend(null);

    // Fetch KPI monthly trend for this employee
    const empId = review.employee_id || assignment?.employee_id;
    if (empId) {
      setKpiTrendLoading(true);
      try {
        const r = await fetch(`${API_BASE}/api/dewi/kpi/trend/${empId}?limit=12`, { headers });
        if (r.ok) setKpiTrend(await r.json());
      } catch { /* noop */ }
      finally { setKpiTrendLoading(false); }
    }
  };

  const submitReview = async () => {
    if (!reviewDialog) return;
    setSubmitting(true);
    try {
      const payload = {
        actor: reviewActor,
        scores: reviewScores.map(s => ({
          kpi_id: s.kpi_id,
          actual_value: Number(s.actual_value) || 0,
          rating: Number(s.rating),
          notes: s.notes || '',
        })),
        overall_notes: reviewOverallNotes,
      };
      const r = await fetch(`${API_BASE}/api/dewi/hris/performance/reviews/${reviewDialog.id}/submit`, {
        method: 'PUT', headers, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal submit');

      // P2.1: Show raise proposal notification
      if (d.raise_proposal_created) {
        toast.success(
          `Review berhasil! Score: ${d.final_score?.toFixed(1)}/5.0`,
          {
            description: `🎉 Usulan kenaikan gaji ${d.raise_pct}% otomatis dibuat — perlu approval HR/Manager.`,
            duration: 7000,
          }
        );
      } else {
        toast.success(`Review ${reviewActor === 'self' ? 'karyawan' : 'manager'} berhasil di-submit`);
      }
      setReviewDialog(null);
      loadAll();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const runSeed = async () => {
    setSubmitting(true);
    try {
      const r = await fetch(`${API_BASE}/api/dewi/hris/performance/seed-demo`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal seed');
      toast.success(`Seed OK — +${d.counts.cycles} cycles, +${d.counts.kpis} KPIs, +${d.counts.assignments} assignments, +${d.counts.reviews} reviews`);
      loadAll();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="hr-performance-module">
      <PageHeader
        icon={Target}
        eyebrow="HRIS · Annual Review (Tahunan)"
        title="Penilaian Kinerja Tahunan"
        subtitle="Siklus review tahunan/semesteran — untuk evaluasi KPI/OKR strategis. Untuk KPI operasional bulanan, gunakan menu 'KPI Bulanan' di sidebar."
        testId="hr-performance-header"
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={runSeed} disabled={submitting} data-testid="perf-seed-btn">
              <RefreshCw className="mr-2 h-4 w-4" /> Seed Demo
            </Button>
            <Button variant="outline" size="sm" onClick={loadAll} disabled={loading} data-testid="perf-refresh-btn">
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>
        }
      />

      {/* Summary Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4" data-testid="perf-summary-tiles">
        <StatTile label="Cycle Aktif" value={summary?.active_cycle?.cycle_code || '—'}
                  suffix={summary?.active_cycle?.name} accent="primary" testId="tile-active-cycle" />
        <StatTile label="Total Assignments" value={summary?.total_assignments || 0}
                  suffix={`${summary?.completed_assignments || 0} completed`} testId="tile-assignments" />
        <StatTile label="Reviews Finalized" value={summary?.finalized_reviews || 0}
                  suffix={`dari ${summary?.total_reviews || 0} total`} accent="success" testId="tile-finalized" />
        <StatTile label="Rata-rata Skor" value={fmtScore(summary?.avg_final_score)}
                  suffix="skala 1-5" accent="warning" testId="tile-avg-score" />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full max-w-2xl grid-cols-3" data-testid="perf-tabs">
          <TabsTrigger value="cycles" data-testid="tab-cycles">
            <Calendar className="mr-2 h-4 w-4" /> Cycles
          </TabsTrigger>
          <TabsTrigger value="kpis" data-testid="tab-kpis">
            <Award className="mr-2 h-4 w-4" /> KPI & Assignments
          </TabsTrigger>
          <TabsTrigger value="reviews" data-testid="tab-reviews">
            <ClipboardCheck className="mr-2 h-4 w-4" /> Reviews
          </TabsTrigger>
        </TabsList>

        {/* ── TAB: CYCLES ── */}
        <TabsContent value="cycles" className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-foreground/60">{cycles.length} siklus penilaian</div>
            <Button size="sm" onClick={() => setCycleDialog({
              cycle_code: '', name: '', period_type: 'quarterly',
              start_date: '', end_date: '', status: 'draft', notes: '',
            })} data-testid="btn-create-cycle">
              <Plus className="mr-2 h-4 w-4" /> Cycle Baru
            </Button>
          </div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {cycles.map(c => (
              <GlassCard key={c.id} className="p-4 space-y-2" data-testid={`cycle-card-${c.cycle_code}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-semibold text-sm">{c.cycle_code}</div>
                    <div className="text-xs text-foreground/60">{c.name}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-md border ${CYCLE_STATUS_COLORS[c.status]}`}>
                    {c.status}
                  </span>
                </div>
                <div className="text-xs text-foreground/50">
                  {fmtDate(c.start_date)} → {fmtDate(c.end_date)}
                </div>
                <div className="text-xs text-foreground/50">
                  Type: <span className="text-foreground/80">{c.period_type}</span>
                </div>
              </GlassCard>
            ))}
            {cycles.length === 0 && !loading && (
              <div className="col-span-full text-center py-8 text-foreground/60 text-sm" data-testid="cycles-empty">
                Belum ada cycle. Klik "Seed Demo" atau "Cycle Baru".
              </div>
            )}
          </div>
        </TabsContent>

        {/* ── TAB: KPI & ASSIGNMENTS ── */}
        <TabsContent value="kpis" className="space-y-6">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Template KPI ({kpis.length})</h3>
              <Button size="sm" variant="outline" onClick={() => setKpiDialog({
                kpi_code: '', name: '', category: 'productivity',
                description: '', measurement: '', target_value: 0,
                target_operator: '>=', weight_default: 20, is_active: true,
              })} data-testid="btn-create-kpi">
                <Plus className="mr-2 h-4 w-4" /> KPI Baru
              </Button>
            </div>
            <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3" data-testid="kpi-list">
              {kpis.map(k => (
                <GlassCard key={k.id} className="p-3 text-sm space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-xs text-foreground/70">{k.kpi_code}</span>
                    <span className="text-[10px] uppercase tracking-wide text-foreground/50 bg-foreground/5 px-2 py-0.5 rounded">
                      {CATEGORY_LABELS[k.category] || k.category}
                    </span>
                  </div>
                  <div className="font-semibold">{k.name}</div>
                  <div className="text-xs text-foreground/60">
                    Target: {k.target_operator} {k.target_value} {k.measurement}
                  </div>
                  <div className="text-xs text-foreground/50">Weight default: {k.weight_default}%</div>
                </GlassCard>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold mb-3">Assignments ({assignments.length})</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="assignment-table">
                <thead className="text-xs text-foreground/60 border-b border-foreground/10">
                  <tr>
                    <th className="text-left py-2 px-2">Karyawan</th>
                    <th className="text-left py-2 px-2">Cycle</th>
                    <th className="text-left py-2 px-2">Departemen</th>
                    <th className="text-left py-2 px-2">KPIs</th>
                    <th className="text-left py-2 px-2">Progress</th>
                    <th className="text-left py-2 px-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {assignments.map(a => (
                    <tr key={a.id} className="border-b border-foreground/5 hover:bg-foreground/5"
                        data-testid={`assignment-row-${a.employee_nik}`}>
                      <td className="py-2 px-2">
                        <div className="font-medium">{a.employee_name}</div>
                        <div className="text-xs text-foreground/50">{a.position}</div>
                      </td>
                      <td className="py-2 px-2 text-xs">{a.cycle_code}</td>
                      <td className="py-2 px-2 text-xs">{a.department}</td>
                      <td className="py-2 px-2 text-xs">
                        {(a.kpis || []).length} KPIs · weight {a.total_weight}%
                      </td>
                      <td className="py-2 px-2">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 bg-foreground/10 rounded-full overflow-hidden">
                            <div className="h-full bg-primary" style={{ width: `${a.progress_pct}%` }} />
                          </div>
                          <span className="text-xs text-foreground/60">{a.progress_pct}%</span>
                        </div>
                      </td>
                      <td className="py-2 px-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${ASSIGNMENT_STATUS_COLORS[a.status]}`}>
                          {a.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {assignments.length === 0 && (
                    <tr><td colSpan={6} className="text-center py-6 text-foreground/50 text-sm">
                      Belum ada assignment.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </TabsContent>

        {/* ── TAB: REVIEWS ── */}
        <TabsContent value="reviews" className="space-y-4">
          <div className="text-sm text-foreground/60">{reviews.length} review pada sistem</div>
          <div className="grid gap-3 md:grid-cols-2">
            {reviews.map(r => (
              <GlassCard key={r.id} className="p-4 space-y-2" data-testid={`review-card-${r.employee_nik}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-semibold text-sm">{r.employee_name}</div>
                    <div className="text-xs text-foreground/50">{r.department} · {r.cycle_code}</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ${REVIEW_STATUS_COLORS[r.status]}`}>
                    {r.status}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs">
                  <div className="flex items-center gap-1.5">
                    <Users className="h-3 w-3 text-foreground/50" />
                    <span>Self: {r.self_submitted_at ? <CheckCircle2 className="inline h-3 w-3 text-emerald-400" /> : <Clock className="inline h-3 w-3 text-foreground/40" />}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Award className="h-3 w-3 text-foreground/50" />
                    <span>Manager: {r.manager_submitted_at ? <CheckCircle2 className="inline h-3 w-3 text-emerald-400" /> : <Clock className="inline h-3 w-3 text-foreground/40" />}</span>
                  </div>
                </div>

                {r.final_score > 0 && (
                  <div className="flex items-center gap-2 pt-1">
                    <TrendingUp className="h-4 w-4 text-amber-300" />
                    <span className="text-sm font-semibold">Final Score: {fmtScore(r.final_score)}</span>
                    <div className="flex gap-0.5 ml-2">
                      {[1, 2, 3, 4, 5].map(n => (
                        <Star key={n} className={`h-3 w-3 ${n <= Math.round(r.final_score) ? 'fill-amber-400 text-amber-400' : 'text-foreground/20'}`} />
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  <Button size="sm" variant="outline" className="text-xs h-7"
                          onClick={() => openReviewDialog(r, 'self')}
                          disabled={r.status === 'finalized'}
                          data-testid={`btn-review-self-${r.employee_nik}`}>
                    <Edit2 className="mr-1 h-3 w-3" /> Self Review
                  </Button>
                  <Button size="sm" variant="outline" className="text-xs h-7"
                          onClick={() => openReviewDialog(r, 'manager')}
                          disabled={r.status === 'finalized' || r.status === 'draft'}
                          data-testid={`btn-review-mgr-${r.employee_nik}`}>
                    <ClipboardCheck className="mr-1 h-3 w-3" /> Manager Review
                  </Button>
                </div>
              </GlassCard>
            ))}
            {reviews.length === 0 && !loading && (
              <div className="col-span-full text-center py-8 text-foreground/60 text-sm">
                Belum ada review.
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* ─── Dialog Cycle ─── */}
      <Dialog open={!!cycleDialog} onOpenChange={(o) => !o && setCycleDialog(null)}>
        <DialogContent className="max-w-md" data-testid="cycle-dialog">
          <DialogHeader><DialogTitle>Cycle Penilaian Baru</DialogTitle></DialogHeader>
          {cycleDialog && (
            <div className="space-y-3">
              <div>
                <Label>Code *</Label>
                <Input value={cycleDialog.cycle_code} placeholder="Q3-2026"
                       onChange={(e) => setCycleDialog({ ...cycleDialog, cycle_code: e.target.value })}
                       data-testid="input-cycle-code" />
              </div>
              <div>
                <Label>Nama *</Label>
                <Input value={cycleDialog.name} placeholder="Quarter 3 — 2026"
                       onChange={(e) => setCycleDialog({ ...cycleDialog, name: e.target.value })}
                       data-testid="input-cycle-name" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tipe</Label>
                  <Select value={cycleDialog.period_type} onValueChange={(v) => setCycleDialog({ ...cycleDialog, period_type: v })}>
                    <SelectTrigger data-testid="select-cycle-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="quarterly">Quarterly</SelectItem>
                      <SelectItem value="half_year">Half Year</SelectItem>
                      <SelectItem value="yearly">Yearly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Status</Label>
                  <Select value={cycleDialog.status} onValueChange={(v) => setCycleDialog({ ...cycleDialog, status: v })}>
                    <SelectTrigger data-testid="select-cycle-status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="draft">Draft</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="closed">Closed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Start Date *</Label>
                  <Input type="date" value={cycleDialog.start_date}
                         onChange={(e) => setCycleDialog({ ...cycleDialog, start_date: e.target.value })}
                         data-testid="input-cycle-start" />
                </div>
                <div>
                  <Label>End Date *</Label>
                  <Input type="date" value={cycleDialog.end_date}
                         onChange={(e) => setCycleDialog({ ...cycleDialog, end_date: e.target.value })}
                         data-testid="input-cycle-end" />
                </div>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea value={cycleDialog.notes || ''} rows={2}
                          onChange={(e) => setCycleDialog({ ...cycleDialog, notes: e.target.value })} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCycleDialog(null)}>Batal</Button>
            <Button onClick={saveCycle} disabled={submitting} data-testid="btn-save-cycle">
              {submitting ? 'Menyimpan...' : 'Simpan'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── Dialog KPI ─── */}
      <Dialog open={!!kpiDialog} onOpenChange={(o) => !o && setKpiDialog(null)}>
        <DialogContent className="max-w-md" data-testid="kpi-dialog">
          <DialogHeader><DialogTitle>KPI Template Baru</DialogTitle></DialogHeader>
          {kpiDialog && (
            <div className="space-y-3">
              <div>
                <Label>Code *</Label>
                <Input value={kpiDialog.kpi_code}
                       onChange={(e) => setKpiDialog({ ...kpiDialog, kpi_code: e.target.value })}
                       data-testid="input-kpi-code" />
              </div>
              <div>
                <Label>Nama *</Label>
                <Input value={kpiDialog.name}
                       onChange={(e) => setKpiDialog({ ...kpiDialog, name: e.target.value })}
                       data-testid="input-kpi-name" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Kategori</Label>
                  <Select value={kpiDialog.category} onValueChange={(v) => setKpiDialog({ ...kpiDialog, category: v })}>
                    <SelectTrigger data-testid="select-kpi-category"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Weight Default (%)</Label>
                  <Input type="number" min={0} max={100} value={kpiDialog.weight_default}
                         onChange={(e) => setKpiDialog({ ...kpiDialog, weight_default: Number(e.target.value) })} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label>Operator</Label>
                  <Select value={kpiDialog.target_operator} onValueChange={(v) => setKpiDialog({ ...kpiDialog, target_operator: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value=">=">{'\u2265'}</SelectItem>
                      <SelectItem value="<=">{'\u2264'}</SelectItem>
                      <SelectItem value="=">=</SelectItem>
                      <SelectItem value=">">{'>'}</SelectItem>
                      <SelectItem value="<">{'<'}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Target</Label>
                  <Input type="number" value={kpiDialog.target_value}
                         onChange={(e) => setKpiDialog({ ...kpiDialog, target_value: Number(e.target.value) })} />
                </div>
                <div>
                  <Label>Unit</Label>
                  <Input value={kpiDialog.measurement} placeholder="%"
                         onChange={(e) => setKpiDialog({ ...kpiDialog, measurement: e.target.value })} />
                </div>
              </div>
              <div>
                <Label>Deskripsi</Label>
                <Textarea rows={2} value={kpiDialog.description || ''}
                          onChange={(e) => setKpiDialog({ ...kpiDialog, description: e.target.value })} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setKpiDialog(null)}>Batal</Button>
            <Button onClick={saveKpi} disabled={submitting} data-testid="btn-save-kpi">
              {submitting ? 'Menyimpan...' : 'Simpan'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── Dialog Review Submit ─── */}
      <Dialog open={!!reviewDialog} onOpenChange={(o) => !o && setReviewDialog(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="review-dialog">
          <DialogHeader>
            <DialogTitle>
              {reviewActor === 'self' ? 'Self Review' : 'Manager Review'} — {reviewDialog?.employee_name}
            </DialogTitle>
          </DialogHeader>
          {reviewDialog && (
            <div className="space-y-4">
              <div className="text-xs text-foreground/60">
                Cycle: <span className="text-foreground/80">{reviewDialog.cycle_code}</span> ·
                Dept: <span className="text-foreground/80">{reviewDialog.department}</span>
              </div>

              {/* ── KPI Monthly Trend Reference Panel ── */}
              {(kpiTrendLoading || (kpiTrend?.trend?.length > 0)) && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3" data-testid="kpi-trend-panel">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" /> KPI Bulanan — Referensi
                    </p>
                    {kpiTrend?.trend?.filter(t => t.kpi_final != null).length > 0 && (() => {
                      const scores = kpiTrend.trend.filter(t => t.kpi_final != null).map(t => t.kpi_final);
                      const avg = (scores.reduce((a,b) => a+b, 0) / scores.length).toFixed(2);
                      return (
                        <span className="text-xs font-bold text-amber-400">
                          Avg {avg}/100 ({scores.length} bln)
                        </span>
                      );
                    })()}
                  </div>
                  {kpiTrendLoading ? (
                    <p className="text-xs text-foreground/50">Memuat data KPI...</p>
                  ) : (
                    <div className="flex gap-1.5 flex-wrap">
                      {kpiTrend.trend.map((t, i) => {
                        const score = t.kpi_final;
                        const color = score == null ? 'bg-muted/30 text-muted-foreground'
                          : score >= 85 ? 'bg-emerald-500/20 text-emerald-400'
                          : score >= 70 ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-red-500/20 text-red-400';
                        return (
                          <div key={i} className={`text-center rounded px-2 py-1 text-[10px] font-medium ${color}`}
                            title={t.period_name}>
                            <div className="font-mono">{t.period_name?.slice(-6) || `M${t.month}`}</div>
                            <div className="font-bold">{score != null ? score.toFixed(0) : '—'}</div>
                            {t.grade && <div className="text-[9px]">{t.grade}</div>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {reviewScores.length === 0 && (
                <div className="text-sm text-foreground/60 text-center py-4">
                  Assignment belum memiliki KPI. Tidak bisa review.
                </div>
              )}

              {reviewScores.map((s, idx) => (
                <GlassCard key={s.kpi_id} className="p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-sm">{s.kpi_name}</div>
                    <div className="text-xs text-foreground/60">Weight: {s.weight}%</div>
                  </div>
                  <div className="text-xs text-foreground/60">
                    Target: {s.target_operator} {s.target_value} {s.measurement}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-xs">Actual Value</Label>
                      <Input type="number" value={s.actual_value}
                             onChange={(e) => setReviewScores(reviewScores.map((rs, i) => i === idx ? { ...rs, actual_value: e.target.value } : rs))}
                             data-testid={`input-actual-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-xs">Rating (1-5)</Label>
                      <Select value={String(s.rating)}
                              onValueChange={(v) => setReviewScores(reviewScores.map((rs, i) => i === idx ? { ...rs, rating: Number(v) } : rs))}>
                        <SelectTrigger data-testid={`select-rating-${idx}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {[1, 2, 3, 4, 5].map(n => (
                            <SelectItem key={n} value={String(n)}>{n} {n === 5 ? '- Excellent' : n === 4 ? '- Good' : n === 3 ? '- Average' : n === 2 ? '- Below' : '- Poor'}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Textarea value={s.notes || ''} placeholder="Catatan..." rows={1}
                            onChange={(e) => setReviewScores(reviewScores.map((rs, i) => i === idx ? { ...rs, notes: e.target.value } : rs))} />
                </GlassCard>
              ))}

              <div>
                <Label>Overall Notes</Label>
                <Textarea value={reviewOverallNotes} rows={2}
                          onChange={(e) => setReviewOverallNotes(e.target.value)}
                          placeholder="Catatan keseluruhan review..." />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewDialog(null)}>Batal</Button>
            <Button onClick={submitReview} disabled={submitting || reviewScores.length === 0} data-testid="btn-submit-review">
              {submitting ? 'Submitting...' : `Submit ${reviewActor === 'self' ? 'Self' : 'Manager'} Review`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
