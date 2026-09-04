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
import { FileSearch, Sparkles, AlertTriangle, CheckCircle, XCircle, Loader2, TrendingUp, Award } from 'lucide-react';
import { IconButton } from '../IconButton';

const RECOMMENDATION_COLOR = {
  'Strongly Recommended': '#10b981',
  'Recommended': '#3b82f6',
  'Consider': '#f59e0b',
  'Not Recommended': '#ef4444',
};

const MATCH_BADGE = {
  yes: { label: 'Match', color: '#10b981' },
  partial: { label: 'Partial', color: '#f59e0b' },
  no: { label: 'No Match', color: '#ef4444' },
};

export default function HRResumeScreeningModule({ token }) {
  const [candidates, setCandidates] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [screening, setScreening] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [result, setResult] = useState(null);
  const [formData, setFormData] = useState({ job_requirements: '', focus_areas: [] });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/employees/list`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setCandidates(data?.data || []);
    } catch (e) {
      toast.error(`Gagal memuat kandidat: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/resume-screen/history`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setHistory(data?.data || []);
    } catch (e) {
      console.error('History fetch failed:', e);
    }
  }, [headers]);

  useEffect(() => {
    fetchCandidates();
    fetchHistory();
  }, [fetchCandidates, fetchHistory]);

  const handleScreen = async () => {
    if (!selectedCandidate) {
      toast.error('Pilih kandidat terlebih dahulu');
      return;
    }
    setScreening(true);
    setResult(null);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/hr/ai/resume-screen/${selectedCandidate}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(formData),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data?.data);
      toast.success('Screening selesai!', { icon: <Sparkles className="w-4 h-4" /> });
      fetchHistory();
    } catch (e) {
      toast.error(`Screening gagal: ${e.message}`);
    } finally {
      setScreening(false);
    }
  };

  const recColor = result?.analysis?.recommendation ? RECOMMENDATION_COLOR[result.analysis.recommendation] : '#64748b';

  return (
    <div className="space-y-6 p-6" data-testid="hr-resume-screening">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <FileSearch className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">AI Resume Screening</h1>
            <p className="text-sm text-muted-foreground">Analisis CV kandidat dengan AI untuk penilaian objektif</p>
          </div>
        </div>
        <IconButton icon={Sparkles} onClick={fetchCandidates} disabled={loading} tooltip="Refresh" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form Panel */}
        <GlassCard className="p-6 space-y-4">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-blue-500" />
            <h2 className="text-lg font-semibold text-foreground">Pilih Kandidat & Kriteria</h2>
          </div>

          <div className="space-y-4">
            <div>
              <Label>Kandidat</Label>
              <Select value={selectedCandidate || ''} onValueChange={setSelectedCandidate}>
                <SelectTrigger>
                  <SelectValue placeholder="Pilih kandidat..." />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map(c => (
                    <SelectItem key={c.id || c.employee_code} value={c.id || c.employee_code}>
                      {c.name} - {c.department || 'N/A'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Persyaratan Tambahan (Opsional)</Label>
              <Textarea
                placeholder="Misal: Minimal 3 tahun pengalaman di garment manufacturing..."
                value={formData.job_requirements}
                onChange={e => setFormData({ ...formData, job_requirements: e.target.value })}
                rows={3}
              />
            </div>

            <div>
              <Label>Area Fokus</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {['skills', 'experience', 'education', 'communication'].map(area => (
                  <Badge
                    key={area}
                    variant={formData.focus_areas.includes(area) ? 'default' : 'outline'}
                    className="cursor-pointer"
                    onClick={() => {
                      const newAreas = formData.focus_areas.includes(area)
                        ? formData.focus_areas.filter(a => a !== area)
                        : [...formData.focus_areas, area];
                      setFormData({ ...formData, focus_areas: newAreas });
                    }}
                  >
                    {area}
                  </Badge>
                ))}
              </div>
            </div>

            <Button onClick={handleScreen} disabled={screening || !selectedCandidate} className="w-full">
              {screening ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Menganalisis...</> : <><Sparkles className="w-4 h-4 mr-2" /> Mulai Screening</>}
            </Button>
          </div>
        </GlassCard>

        {/* Result Panel */}
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Award className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-foreground">Hasil Analisis</h2>
          </div>

          {result ? (
            <div className="space-y-4">
              {/* Overall Score */}
              <div className="text-center p-4 rounded-xl" style={{ background: `${recColor}15`, border: `1px solid ${recColor}35` }}>
                <div className="text-4xl font-bold" style={{ color: recColor }}>{result.analysis.overall_score || 0}</div>
                <div className="text-xs text-muted-foreground mt-1">Skor Keseluruhan</div>
                <Badge className="mt-2" style={{ background: recColor }}>{result.analysis.recommendation}</Badge>
              </div>

              {/* Strengths */}
              {result.analysis.strengths && result.analysis.strengths.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-500" /> Kekuatan
                  </h3>
                  <ul className="space-y-1">
                    {result.analysis.strengths.map((s, i) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                        <span className="text-green-500 mt-0.5">•</span>{s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Weaknesses */}
              {result.analysis.weaknesses && result.analysis.weaknesses.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                    <XCircle className="w-4 h-4 text-amber-500" /> Area Pengembangan
                  </h3>
                  <ul className="space-y-1">
                    {result.analysis.weaknesses.map((w, i) => (
                      <li key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                        <span className="text-amber-500 mt-0.5">•</span>{w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Skill Match */}
              {result.analysis.skill_match && result.analysis.skill_match.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-foreground mb-2">Kesesuaian Skill</h3>
                  <div className="space-y-1">
                    {result.analysis.skill_match.map((sm, i) => {
                      const badge = MATCH_BADGE[sm.match] || MATCH_BADGE.no;
                      return (
                        <div key={i} className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">{sm.skill}</span>
                          <Badge variant="outline" style={{ borderColor: badge.color, color: badge.color }}>{badge.label}</Badge>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Summary */}
              {result.analysis.summary && (
                <div className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                  <p className="text-xs text-muted-foreground leading-relaxed">{result.analysis.summary}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <FileSearch className="w-12 h-12 text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">Pilih kandidat dan klik "Mulai Screening" untuk melihat hasil analisis AI</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* History */}
      <GlassCard className="p-6">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-indigo-500" />
          <h2 className="text-lg font-semibold text-foreground">Riwayat Screening</h2>
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">Belum ada riwayat screening</p>
        ) : (
          <div className="space-y-2">
            {history.slice(0, 10).map((h, i) => {
              const hRec = h.analysis?.recommendation;
              const hColor = hRec ? RECOMMENDATION_COLOR[hRec] : '#64748b';
              return (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)] transition-colors">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{h.candidate_name}</p>
                    <p className="text-xs text-muted-foreground">{h.position} • {new Date(h.generated_at).toLocaleDateString('id-ID')}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-lg font-bold" style={{ color: hColor }}>{h.analysis?.overall_score || 0}</span>
                    <Badge variant="outline" style={{ borderColor: hColor, color: hColor }}>{hRec || 'N/A'}</Badge>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
