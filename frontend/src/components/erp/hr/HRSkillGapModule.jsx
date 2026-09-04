import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import {
  Target, Plus, Loader2, AlertTriangle, TrendingUp, Building2, Users, User,
  GraduationCap, BarChart3, History, Sparkles, ChevronRight, Award
} from 'lucide-react';

const CATEGORY_OPTIONS = [
  { value: 'technical', label: 'Technical' },
  { value: 'soft', label: 'Soft Skills' },
  { value: 'domain', label: 'Domain' },
];

const PRIORITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const PRIORITY_COLOR = {
  critical: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400 border-red-400 dark:border-red-500/30',
  high: 'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-400 dark:border-orange-500/30',
  medium: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-400 dark:border-amber-500/30',
  low: 'bg-muted dark:bg-slate-500/15 text-muted-foreground dark:text-muted-foreground border-border dark:border-slate-500/30',
};

const SEVERITY_COLOR = {
  High: 'text-red-600 dark:text-red-400',
  Medium: 'text-amber-600 dark:text-amber-400',
  Low: 'text-emerald-600 dark:text-emerald-400',
};

export default function HRSkillGapModule({ token }) {
  const [activeTab, setActiveTab] = useState('analysis');
  const [requirements, setRequirements] = useState([]);
  const [analyses, setAnalyses] = useState([]);
  const [departments, setDepartments] = useState([]);

  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [currentResult, setCurrentResult] = useState(null);

  // analysis form
  const [analysisLevel, setAnalysisLevel] = useState('department');
  const [targetDept, setTargetDept] = useState('');

  // requirement form (Dialog state)
  const [reqDialogOpen, setReqDialogOpen] = useState(false);
  const [reqForm, setReqForm] = useState({
    skill_name: '',
    category: 'technical',
    required_level: 3,
    priority: 'high',
    for_role: '',
    for_department: '',
  });

  // detail dialog
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState(null);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const BASE = process.env.REACT_APP_BACKEND_URL;

  // ───────────────────────────── Fetchers ──────────────────────────────
  const fetchRequirements = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/hr/skill-gap/requirements`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setRequirements(data?.data || []);
    } catch (e) {
      console.error('fetchRequirements:', e);
      toast.error(`Gagal memuat skill requirements: ${e.message}`);
    }
  }, [BASE, headers]);

  const fetchAnalyses = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/hr/skill-gap/analyses?limit=20`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setAnalyses(data?.data || []);
    } catch (e) {
      console.error('fetchAnalyses:', e);
    }
  }, [BASE, headers]);

  const fetchDepartments = useCallback(async () => {
    try {
      // Use dedicated skill-gap endpoint (avoids dependency on hr/ai employees list bug)
      const r = await fetch(`${BASE}/api/hr/skill-gap/departments`, { headers });
      if (!r.ok) return;
      const data = await r.json();
      const arr = (data?.data || []).filter(Boolean).sort();
      setDepartments(arr);
      if (arr.length && !targetDept) setTargetDept(arr[0]);
    } catch (e) {
      console.error('fetchDepartments:', e);
    }
  }, [BASE, headers, targetDept]);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchRequirements(), fetchAnalyses(), fetchDepartments()]).finally(() =>
      setLoading(false)
    );
  }, [fetchRequirements, fetchAnalyses, fetchDepartments]);

  // ───────────────────────── Create requirement ─────────────────────────
  const handleCreateRequirement = async () => {
    if (!reqForm.skill_name?.trim()) {
      toast.error('Nama skill wajib diisi');
      return;
    }
    if (!reqForm.for_role && !reqForm.for_department) {
      toast.error('Isi minimal salah satu: Role atau Department');
      return;
    }
    try {
      const body = {
        skill_name: reqForm.skill_name.trim(),
        category: reqForm.category,
        required_level: Number(reqForm.required_level) || 1,
        priority: reqForm.priority,
        for_role: reqForm.for_role?.trim() || null,
        for_department: reqForm.for_department?.trim() || null,
      };
      const r = await fetch(`${BASE}/api/hr/skill-gap/requirements`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Skill requirement berhasil disimpan');
      setReqDialogOpen(false);
      setReqForm({
        skill_name: '',
        category: 'technical',
        required_level: 3,
        priority: 'high',
        for_role: '',
        for_department: '',
      });
      fetchRequirements();
    } catch (e) {
      toast.error(`Gagal menyimpan: ${e.message}`);
    }
  };

  // ───────────────────────── Run analysis ─────────────────────────
  const handleAnalyze = async () => {
    if (analysisLevel === 'department' && !targetDept) {
      toast.error('Pilih departemen dahulu');
      return;
    }
    setAnalyzing(true);
    setCurrentResult(null);
    try {
      const endpoint =
        analysisLevel === 'department'
          ? `${BASE}/api/hr/skill-gap/analyze/department`
          : analysisLevel === 'company'
          ? `${BASE}/api/hr/skill-gap/analyze/company`
          : `${BASE}/api/hr/skill-gap/analyze/individual`;

      const body = {
        level: analysisLevel,
        target_id: analysisLevel === 'department' ? targetDept : null,
        include_recommendations: true,
      };
      const r = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(body) });
      if (!r.ok) {
        let msg = `HTTP ${r.status}`;
        try {
          const j = await r.json();
          msg = j.detail || msg;
        } catch {
          /* noop */
        }
        throw new Error(msg);
      }
      const data = await r.json();
      setCurrentResult(data?.data);
      toast.success('Analisis selesai', { icon: <Sparkles className="w-4 h-4" /> });
      fetchAnalyses();
    } catch (e) {
      toast.error(`Analisis gagal: ${e.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  // ───────────────────────── Detail viewer ─────────────────────────
  const openDetail = (a) => {
    setDetailData(a);
    setDetailOpen(true);
  };

  // ───────────────────────── Render helpers ─────────────────────────
  const renderRequirementsTab = () => (
    <GlassCard className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Target className="w-4 h-4 text-blue-500" />
            Skill Requirements ({requirements.length})
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Definisikan kebutuhan skill per role atau departemen
          </p>
        </div>
        <Dialog open={reqDialogOpen} onOpenChange={setReqDialogOpen}>
          <DialogTrigger asChild>
            <Button data-testid="skill-gap-add-requirement-btn" size="sm">
              <Plus className="w-4 h-4 mr-1" /> Tambah Requirement
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Tambah Skill Requirement</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div>
                <Label>Nama Skill *</Label>
                <Input
                  data-testid="skill-gap-req-name"
                  placeholder="Mis. Python, Adobe Illustrator, Cutting Operator"
                  value={reqForm.skill_name}
                  onChange={(e) => setReqForm({ ...reqForm, skill_name: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Kategori</Label>
                  <Select
                    value={reqForm.category}
                    onValueChange={(v) => setReqForm({ ...reqForm, category: v })}
                  >
                    <SelectTrigger data-testid="skill-gap-req-category">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORY_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Level Dibutuhkan (1-5)</Label>
                  <Input
                    data-testid="skill-gap-req-level"
                    type="number"
                    min={1}
                    max={5}
                    value={reqForm.required_level}
                    onChange={(e) =>
                      setReqForm({ ...reqForm, required_level: Number(e.target.value) })
                    }
                  />
                </div>
              </div>
              <div>
                <Label>Prioritas</Label>
                <Select
                  value={reqForm.priority}
                  onValueChange={(v) => setReqForm({ ...reqForm, priority: v })}
                >
                  <SelectTrigger data-testid="skill-gap-req-priority">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITY_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Untuk Role (opsional)</Label>
                <Input
                  data-testid="skill-gap-req-role"
                  placeholder="Mis. Operator Cutting"
                  value={reqForm.for_role}
                  onChange={(e) => setReqForm({ ...reqForm, for_role: e.target.value })}
                />
              </div>
              <div>
                <Label>Untuk Departemen (opsional)</Label>
                <Select
                  value={reqForm.for_department || '__none__'}
                  onValueChange={(v) =>
                    setReqForm({ ...reqForm, for_department: v === '__none__' ? '' : v })
                  }
                >
                  <SelectTrigger data-testid="skill-gap-req-dept">
                    <SelectValue placeholder="Pilih departemen..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">— Tidak spesifik —</SelectItem>
                    {departments.map((d) => (
                      <SelectItem key={d} value={d}>
                        {d}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Tip: isi minimal salah satu Role atau Departemen.
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReqDialogOpen(false)}>
                Batal
              </Button>
              <Button data-testid="skill-gap-req-save" onClick={handleCreateRequirement}>
                Simpan
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {requirements.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          Belum ada skill requirement. Klik <span className="font-medium">Tambah Requirement</span>{' '}
          untuk mulai.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground border-b border-[var(--glass-border)]">
              <tr>
                <th className="text-left py-2 px-2">Skill</th>
                <th className="text-left py-2 px-2">Kategori</th>
                <th className="text-left py-2 px-2">Level</th>
                <th className="text-left py-2 px-2">Prioritas</th>
                <th className="text-left py-2 px-2">Role</th>
                <th className="text-left py-2 px-2">Department</th>
              </tr>
            </thead>
            <tbody>
              {requirements.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-[var(--glass-border)] hover:bg-[var(--glass)]"
                >
                  <td className="py-2 px-2 font-medium">{r.skill_name}</td>
                  <td className="py-2 px-2 text-muted-foreground">{r.category}</td>
                  <td className="py-2 px-2">
                    <Badge variant="outline">Lv {r.required_level}/5</Badge>
                  </td>
                  <td className="py-2 px-2">
                    <Badge className={PRIORITY_COLOR[r.priority] || ''} variant="outline">
                      {r.priority}
                    </Badge>
                  </td>
                  <td className="py-2 px-2 text-muted-foreground">{r.for_role || '—'}</td>
                  <td className="py-2 px-2 text-muted-foreground">{r.for_department || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
  );

  const renderAnalysisTab = () => (
    <>
      <GlassCard className="p-6 mb-4">
        <h3 className="text-base font-semibold text-foreground flex items-center gap-2 mb-3">
          <BarChart3 className="w-4 h-4 text-emerald-500" /> Jalankan Analisis Baru
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div>
            <Label>Level Analisis</Label>
            <Select value={analysisLevel} onValueChange={setAnalysisLevel}>
              <SelectTrigger data-testid="skill-gap-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="individual">
                  <span className="flex items-center gap-2">
                    <User className="w-3.5 h-3.5" /> Individu (Diri Sendiri)
                  </span>
                </SelectItem>
                <SelectItem value="department">
                  <span className="flex items-center gap-2">
                    <Users className="w-3.5 h-3.5" /> Departemen
                  </span>
                </SelectItem>
                <SelectItem value="company">
                  <span className="flex items-center gap-2">
                    <Building2 className="w-3.5 h-3.5" /> Company-wide
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {analysisLevel === 'department' && (
            <div>
              <Label>Departemen</Label>
              <Select value={targetDept} onValueChange={setTargetDept}>
                <SelectTrigger data-testid="skill-gap-dept">
                  <SelectValue placeholder="Pilih departemen" />
                </SelectTrigger>
                <SelectContent>
                  {departments.map((d) => (
                    <SelectItem key={d} value={d}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex items-end">
            <Button
              data-testid="skill-gap-run-analyze"
              onClick={handleAnalyze}
              disabled={analyzing}
              className="w-full"
            >
              {analyzing ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Menganalisis...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 mr-2" /> Analisis Sekarang
                </>
              )}
            </Button>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground">
          Analisis akan membandingkan skill aktual karyawan dengan{' '}
          <span className="font-medium">Skill Requirements</span> yang sudah didefinisikan, lalu
          menghasilkan rekomendasi training & hiring.
        </p>
      </GlassCard>

      {currentResult && (
        <GlassCard className="p-6">
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2 mb-4">
            <Award className="w-4 h-4 text-amber-500" /> Hasil Analisis
          </h3>
          {renderResultBody(currentResult)}
        </GlassCard>
      )}
    </>
  );

  const renderResultBody = (data) => {
    if (!data) return null;

    // INDIVIDUAL
    if (data.level === 'individual' || data.employee_id) {
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <StatCard label="Total Gap" value={data.total_gaps ?? 0} icon={AlertTriangle} color="amber" />
            <StatCard label="Critical Gap" value={data.critical_gaps ?? 0} icon={TrendingUp} color="red" />
            <StatCard label="Karyawan" value={data.employee_name || '—'} icon={User} color="blue" small />
          </div>

          {data.gaps?.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Skill Gaps</h4>
              <div className="space-y-2">
                {data.gaps.map((g, i) => (
                  <GapRow key={i} gap={g} variant="individual" />
                ))}
              </div>
            </div>
          )}

          {data.recommendations?.length > 0 && renderRecommendations(data.recommendations)}
        </div>
      );
    }

    // DEPARTMENT
    if (data.level === 'department' || data.department) {
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <StatCard label="Department" value={data.department} icon={Building2} color="indigo" small />
            <StatCard label="Karyawan" value={data.total_employees ?? 0} icon={Users} color="blue" />
            <StatCard label="Total Gap" value={data.total_gaps ?? 0} icon={AlertTriangle} color="amber" />
            <StatCard label="Critical Gap" value={data.critical_gaps ?? 0} icon={TrendingUp} color="red" />
          </div>

          {data.gaps?.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Skill Gaps by Department</h4>
              <div className="space-y-2">
                {data.gaps.map((g, i) => (
                  <GapRow key={i} gap={g} variant="department" />
                ))}
              </div>
            </div>
          )}

          {data.recommendations?.length > 0 && renderRecommendations(data.recommendations)}
        </div>
      );
    }

    // COMPANY
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <StatCard label="Total Karyawan" value={data.total_employees ?? 0} icon={Users} color="blue" />
          <StatCard label="Departemen" value={data.total_departments ?? 0} icon={Building2} color="indigo" />
          <StatCard
            label="Departemen dgn Requirement"
            value={data.department_breakdown?.length ?? 0}
            icon={Target}
            color="emerald"
          />
        </div>

        {data.department_breakdown?.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold mb-2">Breakdown per Department</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground border-b border-[var(--glass-border)]">
                  <tr>
                    <th className="text-left py-2 px-2">Department</th>
                    <th className="text-right py-2 px-2">Karyawan</th>
                    <th className="text-right py-2 px-2">Skill Req.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.department_breakdown.map((d, i) => (
                    <tr key={i} className="border-b border-[var(--glass-border)]">
                      <td className="py-2 px-2 font-medium">{d.department}</td>
                      <td className="py-2 px-2 text-right">{d.employee_count}</td>
                      <td className="py-2 px-2 text-right">{d.skill_requirements}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {data.recommendations?.length > 0 && renderRecommendations(data.recommendations)}
      </div>
    );
  };

  const renderRecommendations = (recs) => (
    <div>
      <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
        <GraduationCap className="w-4 h-4 text-emerald-500" /> Rekomendasi
      </h4>
      <div className="space-y-2">
        {recs.map((rec, i) => (
          <div
            key={i}
            className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]"
          >
            <div className="flex items-center justify-between mb-1">
              <div className="text-sm font-medium text-foreground">{rec.title}</div>
              {rec.priority && (
                <Badge className={PRIORITY_COLOR[rec.priority] || ''} variant="outline">
                  {rec.priority}
                </Badge>
              )}
            </div>
            {rec.description && (
              <p className="text-xs text-muted-foreground mb-2">{rec.description}</p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {(rec.skills || rec.skills_addressed || rec.skills_needed || []).map((s, j) => (
                <Badge key={j} variant="secondary" className="text-[11px]">
                  {s}
                </Badge>
              ))}
            </div>
            {(rec.estimated_cost || rec.estimated_budget || rec.timeline || rec.estimated_duration) && (
              <div className="mt-2 text-[11px] text-muted-foreground flex flex-wrap gap-3">
                {(rec.estimated_cost || rec.estimated_budget) && (
                  <span>💰 {rec.estimated_cost || rec.estimated_budget}</span>
                )}
                {(rec.timeline || rec.estimated_duration) && (
                  <span>⏱️ {rec.timeline || rec.estimated_duration}</span>
                )}
              </div>
            )}
            {rec.suggested_actions?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {rec.suggested_actions.map((a, k) => (
                  <li key={k} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                    <ChevronRight className="w-3 h-3 mt-0.5 text-emerald-500" />
                    {a}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );

  const renderHistoryTab = () => (
    <GlassCard className="p-6">
      <h3 className="text-base font-semibold text-foreground flex items-center gap-2 mb-4">
        <History className="w-4 h-4 text-indigo-500" /> Riwayat Analisis ({analyses.length})
      </h3>
      {analyses.length === 0 ? (
        <div className="py-10 text-center text-sm text-muted-foreground">
          Belum ada analisis. Jalankan analisis baru di tab <span className="font-medium">Analisis</span>.
        </div>
      ) : (
        <div className="space-y-2">
          {analyses.map((a, i) => (
            <div
              key={a.id || i}
              role="button"
              tabIndex={0}
              data-testid={`skill-gap-history-${i}`}
              onClick={() => openDetail(a)}
              onKeyDown={(e) => e.key === 'Enter' && openDetail(a)}
              className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:border-emerald-500/40 cursor-pointer transition"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-foreground capitalize flex items-center gap-2">
                    {a.level === 'individual' && <User className="w-3.5 h-3.5 text-blue-500" />}
                    {a.level === 'department' && <Users className="w-3.5 h-3.5 text-emerald-500" />}
                    {a.level === 'company' && <Building2 className="w-3.5 h-3.5 text-indigo-500" />}
                    {a.level || '—'}{' '}
                    {a.department && (
                      <span className="text-xs text-muted-foreground">• {a.department}</span>
                    )}
                    {a.employee_name && (
                      <span className="text-xs text-muted-foreground">• {a.employee_name}</span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {a.analyzed_at ? new Date(a.analyzed_at).toLocaleString('id-ID') : '—'}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {typeof a.gap_count === 'number' && (
                    <Badge variant="outline">{a.gap_count} gap</Badge>
                  )}
                  {typeof a.critical_gaps === 'number' && (
                    <Badge className={PRIORITY_COLOR.critical} variant="outline">
                      {a.critical_gaps} critical
                    </Badge>
                  )}
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );

  // ─────────────────────────── Layout ───────────────────────────
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Target className="w-6 h-6 text-emerald-500" /> Skill Gap Analysis
        </h1>
        <p className="text-sm text-muted-foreground">
          Identifikasi kesenjangan skill di level individu, departemen, atau perusahaan — lengkap dengan rekomendasi training & hiring.
        </p>
      </div>

      {loading ? (
        <GlassCard className="p-6 flex items-center justify-center text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin mr-2" /> Memuat data...
        </GlassCard>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid grid-cols-3 w-full md:w-[480px]">
            <TabsTrigger value="analysis" data-testid="skill-gap-tab-analysis">
              <BarChart3 className="w-4 h-4 mr-1.5" /> Analisis
            </TabsTrigger>
            <TabsTrigger value="requirements" data-testid="skill-gap-tab-requirements">
              <Target className="w-4 h-4 mr-1.5" /> Requirements
            </TabsTrigger>
            <TabsTrigger value="history" data-testid="skill-gap-tab-history">
              <History className="w-4 h-4 mr-1.5" /> Riwayat
            </TabsTrigger>
          </TabsList>

          <TabsContent value="analysis" className="mt-4">
            {renderAnalysisTab()}
          </TabsContent>
          <TabsContent value="requirements" className="mt-4">
            {renderRequirementsTab()}
          </TabsContent>
          <TabsContent value="history" className="mt-4">
            {renderHistoryTab()}
          </TabsContent>
        </Tabs>
      )}

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detail Analisis Skill Gap</DialogTitle>
          </DialogHeader>
          {detailData && (
            <div className="text-xs text-muted-foreground mb-2">
              {detailData.analyzed_at
                ? new Date(detailData.analyzed_at).toLocaleString('id-ID')
                : ''}
            </div>
          )}
          {renderResultBody(detailData)}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ───────────────────────── Sub-components ─────────────────────────
function StatCard({ label, value, icon: Icon, color = 'blue', small = false }) {
  const colorMap = {
    blue: 'from-blue-500/10 to-cyan-500/10 border-blue-300 dark:border-blue-500/20 text-blue-600 dark:text-blue-400',
    emerald: 'from-emerald-500/10 to-teal-500/10 border-emerald-300 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    amber: 'from-amber-500/10 to-orange-500/10 border-amber-300 dark:border-amber-500/20 text-amber-600 dark:text-amber-400',
    red: 'from-red-500/10 to-rose-500/10 border-red-300 dark:border-red-500/20 text-red-600 dark:text-red-400',
    indigo: 'from-indigo-500/10 to-violet-500/10 border-indigo-300 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
  };
  return (
    <div className={`p-3 rounded-xl bg-gradient-to-br border ${colorMap[color] || colorMap.blue}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-70" />}
      </div>
      <div className={`font-bold text-foreground ${small ? 'text-base' : 'text-2xl'}`}>{value}</div>
    </div>
  );
}

function GapRow({ gap, variant }) {
  const pct = variant === 'department'
    ? Number(gap.coverage_percentage || 0)
    : gap.required_level
    ? Math.round(((gap.current_level || 0) / gap.required_level) * 100)
    : 0;

  return (
    <div className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground text-sm">{gap.skill_name}</span>
          <Badge variant="outline" className="text-[10px]">{gap.category}</Badge>
          <Badge className={PRIORITY_COLOR[gap.priority] || ''} variant="outline">
            {gap.priority}
          </Badge>
          {gap.gap_severity && (
            <span className={`text-[11px] font-medium ${SEVERITY_COLOR[gap.gap_severity] || ''}`}>
              · {gap.gap_severity}
            </span>
          )}
        </div>
        {variant === 'individual' ? (
          <span className="text-xs text-muted-foreground">
            Lv {gap.current_level}/{gap.required_level}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">
            {gap.employees_with_gap} karyawan gap · avg {gap.average_level}/{gap.required_level}
          </span>
        )}
      </div>
      <Progress value={pct} className="h-1.5" />
      <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1">
        <span>
          {variant === 'department' ? `${pct}% coverage` : `${pct}% achieved`}
        </span>
        {variant === 'individual' && gap.gap_percentage != null && (
          <span>Gap {gap.gap_percentage}%</span>
        )}
      </div>
    </div>
  );
}
