import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  Target, Plus, Loader2, TrendingUp, AlertTriangle, CheckCircle2, Award,
  BarChart3, Building2, Trash2, Edit, Save, X, ChevronRight
} from 'lucide-react';

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const PRIORITY_COLOR = {
  critical: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400 border-red-400 dark:border-red-500/30',
  high: 'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-400 dark:border-orange-500/30',
  medium: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-400 dark:border-amber-500/30',
  low: 'bg-muted dark:bg-slate-500/15 text-muted-foreground dark:text-muted-foreground border-border dark:border-slate-500/30',
};

const HEALTH_COLOR = {
  on_track: 'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30',
  at_risk: 'bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-400 dark:border-amber-500/30',
  off_track: 'bg-red-100 dark:bg-red-500/15 text-red-600 dark:text-red-400 border-red-400 dark:border-red-500/30',
  completed: 'bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-400 dark:border-blue-500/30',
};

const HEALTH_LABEL = {
  on_track: 'On Track',
  at_risk: 'At Risk',
  off_track: 'Off Track',
  completed: 'Completed',
};

const METRIC_TYPES = [
  { value: 'number', label: 'Number' },
  { value: 'percentage', label: 'Percentage (%)' },
  { value: 'currency', label: 'Currency (Rp)' },
  { value: 'binary', label: 'Binary (done/not)' },
];

function formatMetricValue(val, type) {
  if (val == null) return '—';
  if (type === 'currency') return `Rp ${Number(val).toLocaleString('id-ID')}`;
  if (type === 'percentage') return `${Number(val).toFixed(1)}%`;
  return Number(val).toLocaleString('id-ID');
}

export default function OKRTrackerModule({ token }) {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [period, setPeriod] = useState('');
  const [periods, setPeriods] = useState([]);
  const [objectives, setObjectives] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);

  // create-objective dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    title: '',
    description: '',
    period: '',
    department: '',
    owner_name: '',
    priority: 'medium',
    key_results: [{ title: '', metric_type: 'number', target_value: 100, current_value: 0, unit: '' }],
  });

  // detail dialog
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [editingKRId, setEditingKRId] = useState(null);
  const [krEdit, setKrEdit] = useState({ current_value: 0 });

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );
  const BASE = process.env.REACT_APP_BACKEND_URL;

  const fetchPeriods = useCallback(async () => {
    try {
      const r = await fetch(`${BASE}/api/management/okr/periods`, { headers });
      const data = await r.json();
      const arr = data?.data || [];
      setPeriods(arr);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers]);

  const fetchDashboard = useCallback(async () => {
    try {
      const q = period ? `?period=${encodeURIComponent(period)}` : '';
      const r = await fetch(`${BASE}/api/management/okr/dashboard${q}`, { headers });
      const data = await r.json();
      setDashboard(data?.data || null);
    } catch (e) {
      console.error(e);
      toast.error('Gagal memuat dashboard');
    }
  }, [BASE, headers, period]);

  const fetchObjectives = useCallback(async () => {
    try {
      const q = period ? `?period=${encodeURIComponent(period)}` : '';
      const r = await fetch(`${BASE}/api/management/okr/objectives${q}`, { headers });
      const data = await r.json();
      setObjectives(data?.data || []);
    } catch (e) {
      console.error(e);
    }
  }, [BASE, headers, period]);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchPeriods(), fetchDashboard(), fetchObjectives()]).finally(() => setLoading(false));
  }, [fetchPeriods, fetchDashboard, fetchObjectives]);

  // ───────────────────── Handlers ─────────────────────
  const addKRRow = () => {
    setForm((f) => ({
      ...f,
      key_results: [...f.key_results, { title: '', metric_type: 'number', target_value: 100, current_value: 0, unit: '' }],
    }));
  };

  const updateKR = (i, key, val) => {
    setForm((f) => {
      const krs = [...f.key_results];
      krs[i] = { ...krs[i], [key]: val };
      return { ...f, key_results: krs };
    });
  };

  const removeKR = (i) => {
    setForm((f) => ({ ...f, key_results: f.key_results.filter((_, idx) => idx !== i) }));
  };

  const handleCreate = async () => {
    if (!form.title?.trim()) {
      toast.error('Title objective wajib diisi');
      return;
    }
    if (!form.period?.trim()) {
      toast.error('Period wajib diisi (mis. 2026-Q1)');
      return;
    }
    if (!form.key_results.length || form.key_results.some((kr) => !kr.title?.trim())) {
      toast.error('Tambahkan minimal 1 Key Result dengan judul');
      return;
    }
    try {
      const r = await fetch(`${BASE}/api/management/okr/objectives`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          ...form,
          key_results: form.key_results.map((kr) => ({
            ...kr,
            target_value: Number(kr.target_value) || 0,
            current_value: Number(kr.current_value) || 0,
          })),
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const created = await r.json();
      const newPeriod = created?.data?.period || form.period;
      toast.success('Objective berhasil dibuat');
      setCreateOpen(false);
      setForm({
        title: '',
        description: '',
        period: '',
        department: '',
        owner_name: '',
        priority: 'medium',
        key_results: [{ title: '', metric_type: 'number', target_value: 100, current_value: 0, unit: '' }],
      });
      // Selaraskan filter periode ke objective yang baru dibuat agar langsung tampil di list.
      // Bila periode berubah, useEffect memuat ulang otomatis; panggilan langsung menutup kasus periode sama.
      setPeriod(newPeriod);
      fetchPeriods();
      fetchObjectives();
      fetchDashboard();
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  const openDetail = async (obj) => {
    try {
      const r = await fetch(`${BASE}/api/management/okr/objectives/${obj.id}`, { headers });
      const data = await r.json();
      setDetail(data?.data || obj);
      setDetailOpen(true);
    } catch (e) {
      console.error(e);
      setDetail(obj);
      setDetailOpen(true);
    }
  };

  const beginEditKR = (kr) => {
    setEditingKRId(kr.id);
    setKrEdit({ current_value: kr.current_value, notes: kr.notes || '' });
  };

  const saveKR = async (kr) => {
    try {
      const r = await fetch(`${BASE}/api/management/okr/key-results/${kr.id}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({
          current_value: Number(krEdit.current_value) || 0,
          notes: krEdit.notes,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Key Result diperbarui');
      setEditingKRId(null);
      openDetail(detail);
      fetchObjectives();
      fetchDashboard();
    } catch (e) {
      toast.error(`Gagal update: ${e.message}`);
    }
  };

  const archiveObjective = async (id) => {
    if (!confirm('Archive objective ini?')) return;
    try {
      const r = await fetch(`${BASE}/api/management/okr/objectives/${id}`, { method: 'DELETE', headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Objective di-archive');
      setDetailOpen(false);
      fetchObjectives();
      fetchDashboard();
    } catch (e) {
      toast.error(`Gagal: ${e.message}`);
    }
  };

  // ───────────────────── Render ─────────────────────
  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Target className="w-6 h-6 text-indigo-500" /> Strategic OKR Tracker
          </h1>
          <p className="text-sm text-muted-foreground">
            Track Objectives & Key Results strategis (kuartalan / tahunan) lengkap dengan progress & health.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={period || '__all__'} onValueChange={(v) => setPeriod(v === '__all__' ? '' : v)}>
            <SelectTrigger data-testid="okr-period-filter" className="w-40">
              <SelectValue placeholder="Semua periode" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua periode</SelectItem>
              {periods.map((p) => (
                <SelectItem key={p} value={p}>{p}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button data-testid="okr-create-btn"><Plus className="w-4 h-4 mr-1" /> Objective Baru</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Buat Objective + Key Results</DialogTitle></DialogHeader>
              <div className="space-y-3 py-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>Title Objective *</Label>
                    <Input data-testid="okr-form-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Mis. Tingkatkan revenue 20% Q1 2026" />
                  </div>
                  <div>
                    <Label>Period * (e.g. 2026-Q1)</Label>
                    <Input data-testid="okr-form-period" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} placeholder="2026-Q1" />
                  </div>
                </div>
                <div>
                  <Label>Description</Label>
                  <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="Penjelasan dan konteks objective..." />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <Label>Department</Label>
                    <Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} placeholder="Marketing" />
                  </div>
                  <div>
                    <Label>Owner</Label>
                    <Input value={form.owner_name} onChange={(e) => setForm({ ...form, owner_name: e.target.value })} placeholder="Nama PIC" />
                  </div>
                  <div>
                    <Label>Priority</Label>
                    <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {PRIORITY_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="border-t border-[var(--glass-border)] pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <Label className="text-sm font-semibold">Key Results ({form.key_results.length})</Label>
                    <Button type="button" size="sm" variant="outline" onClick={addKRRow}>
                      <Plus className="w-3.5 h-3.5 mr-1" /> Tambah KR
                    </Button>
                  </div>
                  {form.key_results.map((kr, i) => (
                    <div key={i} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] mb-2">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-xs font-medium text-muted-foreground">KR #{i + 1}</span>
                        {form.key_results.length > 1 && (
                          <button type="button" onClick={() => removeKR(i)} className="text-xs text-red-700 dark:text-red-500 hover:underline">Hapus</button>
                        )}
                      </div>
                      <Input className="mb-2" data-testid={`okr-form-kr-title-${i}`} value={kr.title} onChange={(e) => updateKR(i, 'title', e.target.value)} placeholder="Judul KR (mis. Revenue Rp 500jt/bulan)" />
                      <div className="grid grid-cols-4 gap-2">
                        <div>
                          <Label className="text-[11px]">Metric</Label>
                          <Select value={kr.metric_type} onValueChange={(v) => updateKR(i, 'metric_type', v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {METRIC_TYPES.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label className="text-[11px]">Target</Label>
                          <Input type="number" value={kr.target_value} onChange={(e) => updateKR(i, 'target_value', e.target.value)} />
                        </div>
                        <div>
                          <Label className="text-[11px]">Current</Label>
                          <Input type="number" value={kr.current_value} onChange={(e) => updateKR(i, 'current_value', e.target.value)} />
                        </div>
                        <div>
                          <Label className="text-[11px]">Unit</Label>
                          <Input value={kr.unit || ''} onChange={(e) => updateKR(i, 'unit', e.target.value)} placeholder="%, IDR, pcs" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setCreateOpen(false)}>Batal</Button>
                <Button data-testid="okr-save-btn" onClick={handleCreate}>Simpan</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-2 w-full md:w-[360px]">
          <TabsTrigger value="dashboard" data-testid="okr-tab-dashboard"><BarChart3 className="w-4 h-4 mr-1.5" /> Dashboard</TabsTrigger>
          <TabsTrigger value="objectives" data-testid="okr-tab-objectives"><Target className="w-4 h-4 mr-1.5" /> Objectives</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-4 space-y-4">
          {loading || !dashboard ? (
            <GlassCard className="p-6 text-center text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Memuat...</GlassCard>
          ) : dashboard.total_objectives === 0 ? (
            <GlassCard className="p-12 text-center">
              <Target className="w-12 h-12 text-muted-foreground mx-auto mb-2 opacity-50" />
              <h3 className="font-semibold text-foreground">Belum ada Objective</h3>
              <p className="text-sm text-muted-foreground mb-4">Buat objective pertama untuk mulai tracking.</p>
              <Button onClick={() => setCreateOpen(true)}><Plus className="w-4 h-4 mr-1" /> Buat Objective</Button>
            </GlassCard>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <StatCard label="Total" value={dashboard.total_objectives} icon={Target} color="indigo" />
                <StatCard label="On Track" value={dashboard.on_track} icon={CheckCircle2} color="emerald" />
                <StatCard label="At Risk" value={dashboard.at_risk} icon={AlertTriangle} color="amber" />
                <StatCard label="Off Track" value={dashboard.off_track} icon={TrendingUp} color="red" />
                <StatCard label="Avg Progress" value={`${dashboard.average_progress}%`} icon={Award} color="blue" />
              </div>

              {dashboard.by_department?.length > 0 && (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><Building2 className="w-4 h-4 text-indigo-500" /> Breakdown per Department</h3>
                  <div className="space-y-2">
                    {dashboard.by_department.map((d, i) => (
                      <div key={i} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium">{d.department}</span>
                          <span className="text-xs text-muted-foreground">{d.total} objective · {d.critical_count} critical</span>
                        </div>
                        <Progress value={d.average_progress} className="h-1.5" />
                        <div className="text-[11px] text-muted-foreground mt-0.5">Avg progress {d.average_progress}%</div>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}

              {dashboard.top_objectives?.length > 0 && (
                <GlassCard className="p-6">
                  <h3 className="text-base font-semibold mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-emerald-500" /> Top Objectives</h3>
                  <div className="space-y-2">
                    {dashboard.top_objectives.map((o) => (
                      <ObjectiveRow key={o.id} obj={o} onClick={() => openDetail(o)} />
                    ))}
                  </div>
                </GlassCard>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="objectives" className="mt-4">
          {objectives.length === 0 ? (
            <GlassCard className="p-10 text-center text-sm text-muted-foreground">Belum ada objective</GlassCard>
          ) : (
            <div className="space-y-2">
              {objectives.map((o) => (
                <ObjectiveRow key={o.id} obj={o} onClick={() => openDetail(o)} detailed />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 pr-8">
                  <Target className="w-5 h-5 text-indigo-500" /> {detail.title}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{detail.period}</Badge>
                  {detail.department && <Badge variant="outline">{detail.department}</Badge>}
                  {detail.priority && <Badge className={PRIORITY_COLOR[detail.priority]} variant="outline">{detail.priority}</Badge>}
                  {detail.health && <Badge className={HEALTH_COLOR[detail.health]} variant="outline">{HEALTH_LABEL[detail.health] || detail.health}</Badge>}
                </div>
                {detail.description && <p className="text-sm text-muted-foreground">{detail.description}</p>}
                {detail.owner_name && <p className="text-xs text-muted-foreground">Owner: {detail.owner_name}</p>}
                <div className="p-3 rounded-lg bg-gradient-to-br from-indigo-500/10 to-violet-500/10 border border-indigo-300 dark:border-indigo-500/20">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold">Overall Progress</span>
                    <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400">{detail.progress?.toFixed(1) ?? 0}%</span>
                  </div>
                  <Progress value={detail.progress || 0} className="h-2" />
                </div>

                <div>
                  <h4 className="text-sm font-semibold mb-2">Key Results ({(detail.key_results || []).length})</h4>
                  <div className="space-y-2">
                    {(detail.key_results || []).map((kr) => {
                      const progress = kr.target_value > 0 ? Math.min(100, (kr.current_value / kr.target_value) * 100) : (kr.current_value > 0 ? 100 : 0);
                      const editing = editingKRId === kr.id;
                      return (
                        <div key={kr.id} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                          <div className="flex items-start justify-between mb-1">
                            <span className="text-sm font-medium flex-1 pr-2">{kr.title}</span>
                            {!editing ? (
                              <button onClick={() => beginEditKR(kr)} className="text-xs text-indigo-500 hover:underline flex items-center gap-1" data-testid={`okr-edit-kr-${kr.id}`}>
                                <Edit className="w-3 h-3" /> Update
                              </button>
                            ) : (
                              <div className="flex items-center gap-2">
                                <button onClick={() => setEditingKRId(null)} className="text-xs text-red-700 dark:text-red-500 hover:underline"><X className="w-3 h-3" /></button>
                                <button onClick={() => saveKR(kr)} className="text-xs text-emerald-500 hover:underline flex items-center gap-1"><Save className="w-3 h-3" /> Simpan</button>
                              </div>
                            )}
                          </div>
                          {!editing ? (
                            <>
                              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                                <span>{formatMetricValue(kr.current_value, kr.metric_type)} / {formatMetricValue(kr.target_value, kr.metric_type)}{kr.unit && kr.metric_type !== 'currency' && kr.metric_type !== 'percentage' ? ` ${kr.unit}` : ''}</span>
                                <span>{progress.toFixed(0)}%</span>
                              </div>
                              <Progress value={progress} className="h-1.5" />
                            </>
                          ) : (
                            <div className="grid grid-cols-2 gap-2 mt-1">
                              <div>
                                <Label className="text-[11px]">Current Value</Label>
                                <Input type="number" value={krEdit.current_value} onChange={(e) => setKrEdit({ ...krEdit, current_value: e.target.value })} />
                              </div>
                              <div>
                                <Label className="text-[11px]">Notes</Label>
                                <Input value={krEdit.notes || ''} onChange={(e) => setKrEdit({ ...krEdit, notes: e.target.value })} placeholder="opsional" />
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="destructive" size="sm" onClick={() => archiveObjective(detail.id)}><Trash2 className="w-3.5 h-3.5 mr-1" /> Archive</Button>
                <Button variant="outline" onClick={() => setDetailOpen(false)}>Tutup</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }) {
  const map = {
    blue: 'from-blue-500/10 to-cyan-500/10 border-blue-300 dark:border-blue-500/20 text-blue-600 dark:text-blue-400',
    emerald: 'from-emerald-500/10 to-teal-500/10 border-emerald-300 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    amber: 'from-amber-500/10 to-orange-500/10 border-amber-300 dark:border-amber-500/20 text-amber-600 dark:text-amber-400',
    red: 'from-red-500/10 to-rose-500/10 border-red-300 dark:border-red-500/20 text-red-600 dark:text-red-400',
    indigo: 'from-indigo-500/10 to-violet-500/10 border-indigo-300 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
  };
  return (
    <div className={`p-3 rounded-xl bg-gradient-to-br border ${map[color] || map.blue}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-70" />}
      </div>
      <div className="font-bold text-foreground text-2xl">{value}</div>
    </div>
  );
}

function ObjectiveRow({ obj, onClick, detailed = false }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      data-testid={`okr-obj-row-${obj.id}`}
      className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:border-indigo-500/40 cursor-pointer transition"
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 flex-1 pr-2">
          <span className="font-medium text-sm text-foreground">{obj.title}</span>
          {obj.priority && <Badge className={PRIORITY_COLOR[obj.priority]} variant="outline">{obj.priority}</Badge>}
          {obj.health && <Badge className={HEALTH_COLOR[obj.health]} variant="outline">{HEALTH_LABEL[obj.health] || obj.health}</Badge>}
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground" />
      </div>
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground mb-1">
        <span>{obj.period}</span>
        {obj.department && <span>· {obj.department}</span>}
        {obj.owner_name && <span>· {obj.owner_name}</span>}
        {typeof obj.key_results_count === 'number' && <span>· {obj.key_results_count} KR</span>}
      </div>
      <div className="flex items-center gap-2">
        <Progress value={obj.progress || 0} className="h-1.5 flex-1" />
        <span className="text-xs font-medium text-foreground">{(obj.progress ?? 0).toFixed(0)}%</span>
      </div>
      {detailed && obj.description && (
        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{obj.description}</p>
      )}
    </div>
  );
}
