import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Target, Sparkles, AlertTriangle, Loader2, Award, TrendingUp, Calendar, Lightbulb } from 'lucide-react';
import { IconButton } from '../IconButton';

const FOCUS_OPTIONS = [
  { value: 'performance', label: 'Peningkatan Kinerja' },
  { value: 'leadership', label: 'Kepemimpinan' },
  { value: 'technical', label: 'Skill Teknis' },
  { value: 'communication', label: 'Komunikasi' },
  { value: 'time_management', label: 'Manajemen Waktu' },
  { value: 'overall', label: 'Keseluruhan' },
];

export default function HRCoachingModule({ token }) {
  const [employees, setEmployees] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [result, setResult] = useState(null);
  const [formData, setFormData] = useState({ focus: 'overall', goals: '' });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/employees/list`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setEmployees(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat karyawan: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/coaching/history`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setHistory(data?.data || []);
    } catch (e) {
      console.error('History fetch failed:', e);
    }
  }, [headers]);

  useEffect(() => {
    fetchEmployees();
    fetchHistory();
  }, [fetchEmployees, fetchHistory]);

  const handleGenerate = async () => {
    if (!selectedEmployee) {
      toast.error('Pilih karyawan terlebih dahulu');
      return;
    }
    setGenerating(true);
    setResult(null);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/coaching/${selectedEmployee}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(formData),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data?.data);
      toast.success('Coaching plan berhasil dibuat!', { icon: <Sparkles className="w-4 h-4" /> });
      fetchHistory();
    } catch (e) {
      toast.error(`Gagal membuat coaching plan: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6 p-6" data-testid="hr-coaching-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
            <Target className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Performance Coaching AI</h1>
            <p className="text-sm text-muted-foreground">Rencana coaching personal berbasis AI untuk pengembangan karyawan</p>
          </div>
        </div>
        <IconButton icon={Sparkles} onClick={fetchEmployees} disabled={loading} tooltip="Refresh" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form Panel */}
        <GlassCard className="p-6 space-y-4">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-emerald-500" />
            <h2 className="text-lg font-semibold text-foreground">Pilih Karyawan & Fokus Coaching</h2>
          </div>

          <div className="space-y-4">
            <div>
              <Label>Karyawan</Label>
              <Select value={selectedEmployee || ''} onValueChange={setSelectedEmployee}>
                <SelectTrigger>
                  <SelectValue placeholder="Pilih karyawan..." />
                </SelectTrigger>
                <SelectContent>
                  {employees.map(e => (
                    <SelectItem key={e.id || e.employee_code} value={e.id || e.employee_code}>
                      {e.name} - {e.department || 'N/A'} ({e.job_title || 'N/A'})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Fokus Coaching</Label>
              <Select value={formData.focus} onValueChange={v => setFormData({ ...formData, focus: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FOCUS_OPTIONS.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Tujuan Spesifik (Opsional)</Label>
              <Textarea
                placeholder="Misal: Meningkatkan produktivitas 20% dalam 3 bulan, Mengurangi error QC..."
                value={formData.goals}
                onChange={e => setFormData({ ...formData, goals: e.target.value })}
                rows={3}
              />
            </div>

            <Button onClick={handleGenerate} disabled={generating || !selectedEmployee} className="w-full">
              {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Membuat Plan...</> : <><Sparkles className="w-4 h-4 mr-2" /> Generate Coaching Plan</>}
            </Button>
          </div>
        </GlassCard>

        {/* Result Panel */}
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Award className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-foreground">Coaching Plan</h2>
          </div>

          {result ? (
            <div className="space-y-4 max-h-[600px] overflow-y-auto">
              {/* Title */}
              {result.plan?.coaching_title && (
                <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-300 dark:border-emerald-500/20">
                  <h3 className="text-lg font-bold text-foreground">{result.plan.coaching_title}</h3>
                  {result.employee && (
                    <p className="text-xs text-muted-foreground mt-1">{result.employee.name} • {result.employee.job_title} • {result.employee.department}</p>
                  )}
                </div>
              )}

              {/* Summary */}
              {result.plan?.employee_summary && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-amber-500" /> Ringkasan Situasi
                  </h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">{result.plan.employee_summary}</p>
                </div>
              )}

              {/* Development Areas */}
              {result.plan?.key_development_areas && result.plan.key_development_areas.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Area Pengembangan Kunci</h4>
                  <div className="flex flex-wrap gap-2">
                    {result.plan.key_development_areas.map((area, i) => (
                      <Badge key={i} variant="outline" className="text-xs">{area}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* SMART Goals */}
              {result.plan?.smart_goals && result.plan.smart_goals.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <Target className="w-4 h-4 text-blue-500" /> SMART Goals
                  </h4>
                  <div className="space-y-2">
                    {result.plan.smart_goals.map((sg, i) => (
                      <div key={i} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                        <p className="text-xs font-medium text-foreground mb-1">{sg.goal}</p>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>⏱️ {sg.timeline}</span>
                          <span>📊 {sg.measurement}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Weekly Actions */}
              {result.plan?.weekly_actions && result.plan.weekly_actions.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-indigo-500" /> Aksi Mingguan
                  </h4>
                  <ul className="space-y-1">
                    {result.plan.weekly_actions.map((wa, i) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                        <span className="text-indigo-500 font-bold mt-0.5">W{i + 1}.</span>{wa}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Recommended Trainings */}
              {result.plan?.recommended_trainings && result.plan.recommended_trainings.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2">Rekomendasi Training</h4>
                  <div className="flex flex-wrap gap-2">
                    {result.plan.recommended_trainings.map((rt, i) => (
                      <Badge key={i} variant="secondary" className="text-xs">{rt}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Manager Support */}
              {result.plan?.manager_support && (
                <div className="p-3 rounded-lg bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20">
                  <h4 className="text-xs font-semibold text-foreground mb-1">Dukungan Manager</h4>
                  <p className="text-xs text-muted-foreground">{result.plan.manager_support}</p>
                </div>
              )}

              {/* Milestones */}
              {result.plan?.milestones && result.plan.milestones.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-green-500" /> Milestones
                  </h4>
                  <div className="space-y-2">
                    {result.plan.milestones.map((ms, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <Badge className="shrink-0">Bulan {ms.month}</Badge>
                        <p className="text-xs text-muted-foreground">{ms.target}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Motivational Message */}
              {result.plan?.motivational_message && (
                <div className="p-4 rounded-lg bg-gradient-to-br from-blue-500/10 to-indigo-500/10 border border-blue-300 dark:border-blue-500/20">
                  <p className="text-xs text-foreground italic leading-relaxed">"{result.plan.motivational_message}"</p>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <Target className="w-12 h-12 text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">Pilih karyawan dan klik "Generate Coaching Plan" untuk membuat rencana coaching personal</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* History */}
      <GlassCard className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <Calendar className="w-5 h-5 text-indigo-500" />
          <h2 className="text-lg font-semibold text-foreground">Riwayat Coaching Plans</h2>
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">Belum ada riwayat coaching plan</p>
        ) : (
          <div className="space-y-2">
            {history.slice(0, 10).map((h, i) => (
              <Dialog key={i}>
                <DialogTrigger asChild>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)] transition-colors cursor-pointer">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{h.employee_name}</p>
                      <p className="text-xs text-muted-foreground">Fokus: {h.focus} • {new Date(h.generated_at).toLocaleDateString('id-ID')}</p>
                    </div>
                    <Badge variant="outline">Lihat Plan</Badge>
                  </div>
                </DialogTrigger>
                <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>{h.plan?.coaching_title || 'Coaching Plan'}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4">
                    {h.plan?.employee_summary && <p className="text-sm text-muted-foreground">{h.plan.employee_summary}</p>}
                    {h.plan?.smart_goals && (
                      <div>
                        <h4 className="text-sm font-semibold mb-2">Goals</h4>
                        <ul className="space-y-1">
                          {h.plan.smart_goals.map((g, j) => (
                            <li key={j} className="text-xs">• {g.goal}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </DialogContent>
              </Dialog>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
