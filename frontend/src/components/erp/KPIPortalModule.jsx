import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Target, CheckCircle2, Clock, Star, Award, ChevronRight,
  AlertCircle, Loader2, Send, BookOpen, BarChart3, RefreshCw,
  ArrowLeft, TrendingUp, Users, UserCheck, Trophy,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import KPIGamificationTab, { BadgeChip } from './KPIGamificationTab';

const API = process.env.REACT_APP_BACKEND_URL;
const kpi = (path, opts = {}) => fetch(`${API}/api/dewi/kpi${path}`, opts);

const GRADE_CFG = {
  A: { bg: 'from-emerald-600 to-emerald-400', text: 'text-emerald-100', label: 'Sangat Baik', raise: 'Naik Gaji 10%' },
  B: { bg: 'from-blue-600 to-blue-400', text: 'text-blue-100', label: 'Baik', raise: 'Save / Perpanjang Kontrak (7%)' },
  C: { bg: 'from-amber-600 to-amber-400', text: 'text-amber-100', label: 'Cukup', raise: 'Mediasi / Evaluasi' },
  D: { bg: 'from-orange-600 to-orange-400', text: 'text-orange-100', label: 'Kurang', raise: 'Cut Off' },
  E: { bg: 'from-red-600 to-red-400', text: 'text-red-100', label: 'Sangat Kurang', raise: 'Cut Off' },
};

const EVAL_TYPE_CFG = {
  self: { label: 'Self-Assessment', desc: 'Penilaian diri sendiri', icon: BookOpen, color: 'border-indigo-500/40 bg-indigo-100 dark:bg-indigo-500/10', badge: 'text-indigo-600 dark:text-indigo-400' },
  peer: { label: 'Peer Review', desc: 'Menilai rekan kerja (anonim)', icon: Users, color: 'border-sky-500/40 bg-sky-100 dark:bg-sky-500/10', badge: 'text-sky-600 dark:text-sky-400' },
  supervisor_to_staff: { label: 'Supervisor → Staff', desc: 'Penilaian supervisor untuk Anda', icon: UserCheck, color: 'border-amber-500/40 bg-amber-100 dark:bg-amber-500/10', badge: 'text-amber-700 dark:text-amber-400' },
  staff_to_supervisor: { label: 'Staff → Supervisor', desc: 'Menilai atasan Anda (anonim)', icon: ChevronRight, color: 'border-violet-500/40 bg-violet-100 dark:bg-violet-500/10', badge: 'text-violet-600 dark:text-violet-400' },
};

const STATUS_ICON = {
  submitted: <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />,
  draft: <Clock className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0" />,
  not_started: <AlertCircle className="w-4 h-4 text-muted-foreground shrink-0" />,
};

function ScoreBar({ score, color = 'bg-indigo-500' }) {
  const pct = Math.min(100, Math.max(0, score || 0));
  return (
    <div className="w-full bg-foreground/5 rounded-full h-2">
      <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function KPIPortalModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [view, setView] = useState('list'); // list | form | results | achievement
  const [periods, setPeriods] = useState([]);
  const [myResults, setMyResults] = useState([]);
  const [currentPeriod, setCurrentPeriod] = useState(null);
  const [formData, setFormData] = useState(null); // {period, forms_to_fill, questions_by_type, ...}
  const [activeForm, setActiveForm] = useState(null); // form item being filled
  const [answers, setAnswers] = useState({}); // {question_id: score}
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedResult, setSelectedResult] = useState(null);

  const loadPeriods = useCallback(async () => {
    try {
      const r = await kpi('/my/periods', { headers });
      const d = await r.json();
      setPeriods(d.periods || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  const loadResults = useCallback(async () => {
    try {
      const r = await kpi('/my/results', { headers });
      const d = await r.json();
      setMyResults(d.results || []);
    } catch (e) { console.error(e); }
  }, [headers]);

  useEffect(() => {
    Promise.all([loadPeriods(), loadResults()]).finally(() => setLoading(false));
  }, [loadPeriods, loadResults]);

  const openForms = async (period) => {
    setCurrentPeriod(period);
    setLoading(true);
    try {
      const r = await kpi(`/my/forms/${period.period_id}`, { headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal memuat form'); return; }
      setFormData(d);
      setView('form');
    } catch (e) {
      toast.error('Gagal memuat form');
    } finally {
      setLoading(false);
    }
  };

  const startForm = (formItem) => {
    setActiveForm(formItem);
    setAnswers({});
  };

  const handleAnswer = (qid, score) => {
    setAnswers(prev => ({ ...prev, [qid]: score }));
  };

  const handleSaveDraft = async () => {
    if (!activeForm) return;
    await submitForm(false);
  };

  const handleSubmitForm = async () => {
    const questions = formData?.questions_by_type?.[activeForm.eval_type] || [];
    const unanswered = questions.filter(q => !answers[q.question_id]);
    if (unanswered.length > 0) {
      if (!window.confirm(`Masih ada ${unanswered.length} pertanyaan yang belum dijawab. Lanjutkan submit?`)) return;
    }
    setSubmitting(true);
    try {
      await submitForm(true);
      toast.success('Form berhasil disubmit!');
      setActiveForm(null);
      // Reload form data
      const r = await kpi(`/my/forms/${currentPeriod.period_id}`, { headers });
      const d = await r.json();
      setFormData(d);
    } finally {
      setSubmitting(false);
    }
  };

  const submitForm = async (isSubmit) => {
    const answersArr = Object.entries(answers).map(([question_id, score]) => ({ question_id, score }));
    const r = await kpi('/submissions', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        period_id: currentPeriod.period_id,
        eval_type: activeForm.eval_type,
        evaluatee_id: activeForm.evaluatee_id,
        answers: answersArr,
        submit: isSubmit,
      }),
    });
    const d = await r.json();
    if (!r.ok) { toast.error(d.detail || 'Gagal'); throw new Error(d.detail); }
    return d;
  };

  const openResult = async (period) => {
    try {
      const r = await kpi(`/my/result/${period.period_id}`, { headers });
      const d = await r.json();
      if (!r.ok) { toast.error(d.detail || 'Gagal'); return; }
      setSelectedResult(d);
      setView('results');
    } catch (e) { toast.error('Gagal memuat hasil'); }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400" />
    </div>
  );

  // ── VIEW: RESULT DETAIL ──────────────────────────────
  if (view === 'results' && selectedResult) {
    const res = selectedResult.result;
    const g = GRADE_CFG[res?.grade];
    return (
      <div className="space-y-5 p-4">
        <Button variant="ghost" size="sm" onClick={() => { setView('list'); setSelectedResult(null); }}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Kembali
        </Button>

        {!selectedResult.published ? (
          <div className="text-center py-12 text-muted-foreground">
            <Clock className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p className="font-medium">Hasil KPI sedang diproses</p>
            <p className="text-sm mt-1">{selectedResult.message}</p>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Main grade card */}
            <div className={`rounded-2xl bg-gradient-to-br ${g?.bg || 'from-slate-700 to-slate-600'} p-6 text-center text-foreground`}>
              <div className="text-6xl font-black mb-1">{res.kpi_final?.toFixed(1) || '—'}</div>
              <div className="text-sm opacity-80 mb-3">KPI Final</div>
              {res.grade && (
                <div className="inline-flex items-center gap-2 bg-black/20 px-4 py-2 rounded-full">
                  <Award className="w-4 h-4" />
                  <span className="font-bold">Grade {res.grade} — {g?.label}</span>
                </div>
              )}
              {g?.raise && (
                <div className="text-sm opacity-80 mt-2">{g.raise}</div>
              )}
            </div>

            {/* Component breakdown */}
            <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4 space-y-4">
              <p className="text-sm font-semibold text-muted-foreground">Rincian Komponen</p>
              {[
                { label: 'Perform', weight: '60%', score: res.perform_score, color: 'bg-blue-500' },
                { label: 'Attitude', weight: '20%', score: res.attitude_score, color: 'bg-violet-500' },
                { label: 'Absensi', weight: '20%', score: res.absensi_score, color: 'bg-emerald-500' },
              ].map(c => (
                <div key={c.label} className="space-y-1.5">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">{c.label} <span className="text-xs">({c.weight})</span></span>
                    <span className="font-bold">{c.score != null ? c.score.toFixed(1) : '—'}</span>
                  </div>
                  <ScoreBar score={c.score} color={c.color} />
                </div>
              ))}
            </div>

            {/* Attitude breakdown */}
            {res.attitude_detail?.component_scores && (
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                <p className="text-sm font-semibold text-muted-foreground mb-3">Rincian Attitude (360°)</p>
                <div className="space-y-2">
                  {[
                    { key: 'self', label: 'Self-Assessment', weight: '20%' },
                    { key: 'peer', label: 'Peer Review', weight: '20%' },
                    { key: 'supervisor_to_staff', label: 'Supervisor → Anda', weight: '35%' },
                    { key: 'staff_to_supervisor', label: 'Anda → Atasan', weight: '25%' },
                  ].map(c => {
                    const s = res.attitude_detail.component_scores[c.key];
                    return (
                      <div key={c.key} className="flex justify-between text-xs">
                        <span className="text-muted-foreground">{c.label} ({c.weight})</span>
                        <span className={s != null ? 'font-medium' : 'text-muted-foreground'}>
                          {s != null ? s.toFixed(1) : 'Belum ada'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Absensi breakdown */}
            {res.absensi_detail?.breakdown && (
              <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                <p className="text-sm font-semibold text-muted-foreground mb-3">Rincian Absensi</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(res.absensi_detail.breakdown).filter(([, v]) => v > 0).map(([k, v]) => (
                    <div key={k} className="flex justify-between bg-foreground/5 rounded px-2 py-1">
                      <span className="capitalize text-muted-foreground">{k}</span>
                      <span className="font-medium">{v} hari</span>
                    </div>
                  ))}
                  <div className="flex justify-between bg-foreground/5 rounded px-2 py-1 col-span-2">
                    <span className="text-muted-foreground">Total Tidak Hadir</span>
                    <span className="font-medium">{res.absensi_detail.absent_days} / {res.absensi_detail.working_days} hari kerja</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── VIEW: FORM FILLING ────────────────────────────────
  if (view === 'form' && formData) {
    // Show form list first, then individual form
    if (!activeForm) {
      const allForms = [...(formData.forms_to_fill || []), ...(formData.supervisor_forms || [])];
      const completedForms = allForms.filter(f => f.status === 'submitted').length;

      return (
        <div className="space-y-5 p-4">
          <Button variant="ghost" size="sm" onClick={() => setView('list')}>
            <ArrowLeft className="w-4 h-4 mr-1" /> Kembali
          </Button>

          <div>
            <h2 className="font-bold text-lg text-foreground">{formData.period?.name}</h2>
            <p className="text-sm text-muted-foreground">
              {formData.period?.period_from} s.d. {formData.period?.period_to}
            </p>
            <div className="flex items-center gap-2 mt-2">
              <div className="flex-1 bg-foreground/5 rounded-full h-2">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all"
                  style={{ width: `${allForms.length > 0 ? (completedForms / allForms.length) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs text-muted-foreground">{completedForms}/{allForms.length} selesai</span>
            </div>
          </div>

          <div className="space-y-3">
            {formData.forms_to_fill?.map((f, i) => {
              const cfg = EVAL_TYPE_CFG[f.eval_type] || {};
              const Icon = cfg.icon || Target;
              return (
                <div key={i}
                  className={`rounded-xl border ${cfg.color} p-4 flex items-center justify-between`}>
                  <div className="flex items-center gap-3">
                    {STATUS_ICON[f.status] || STATUS_ICON.not_started}
                    <div>
                      <div className="font-medium text-sm">{cfg.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {f.eval_type === 'self' ? 'Untuk diri sendiri' :
                          f.eval_type === 'peer' ? `Menilai: ${f.evaluatee_name}` :
                            f.eval_type === 'staff_to_supervisor' ? 'Menilai atasan Anda (anonim)' : cfg.desc}
                      </div>
                    </div>
                  </div>
                  <Button size="sm" variant="outline" className="h-8 text-xs shrink-0"
                    disabled={f.status === 'submitted'}
                    onClick={() => startForm(f)}
                    data-testid={`start-form-${f.eval_type}`}>
                    {f.status === 'submitted' ? 'Selesai' : f.status === 'draft' ? 'Lanjutkan' : 'Mulai'}
                  </Button>
                </div>
              );
            })}

            {formData.supervisor_forms?.length > 0 && (
              <>
                <div className="text-xs font-semibold text-muted-foreground pt-2">Form Supervisor</div>
                {formData.supervisor_forms.map((f, i) => {
                  const cfg = EVAL_TYPE_CFG[f.eval_type] || {};
                  return (
                    <div key={`sup-${i}`}
                      className={`rounded-xl border ${cfg.color} p-4 flex items-center justify-between`}>
                      <div className="flex items-center gap-3">
                        {STATUS_ICON[f.status] || STATUS_ICON.not_started}
                        <div>
                          <div className="font-medium text-sm">Penilaian untuk {f.evaluatee_name}</div>
                          <div className="text-xs text-muted-foreground">Supervisor → Staff</div>
                        </div>
                      </div>
                      <Button size="sm" variant="outline" className="h-8 text-xs shrink-0"
                        disabled={f.status === 'submitted'}
                        onClick={() => startForm(f)}>
                        {f.status === 'submitted' ? 'Selesai' : 'Isi Form'}
                      </Button>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </div>
      );
    }

    // Show single form questions
    const questions = formData.questions_by_type?.[activeForm.eval_type] || [];
    const categories = [...new Set(questions.map(q => q.category))];
    const answeredCount = Object.keys(answers).filter(qid =>
      questions.find(q => q.question_id === qid)
    ).length;

    return (
      <div className="space-y-5 p-4">
        <Button variant="ghost" size="sm" onClick={() => setActiveForm(null)}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Kembali ke Daftar Form
        </Button>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h2 className="font-bold text-lg">
              {EVAL_TYPE_CFG[activeForm.eval_type]?.label}
            </h2>
            {activeForm.is_anonymous && (
              <span className="text-xs bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-300 px-2 py-0.5 rounded-full">Anonim</span>
            )}
          </div>
          {activeForm.eval_type === 'peer' && (
            <p className="text-sm text-muted-foreground">Menilai: <strong>{activeForm.evaluatee_name}</strong></p>
          )}
          <div className="text-xs text-muted-foreground">
            {answeredCount}/{questions.length} pertanyaan dijawab
          </div>
          <div className="w-full bg-foreground/5 rounded-full h-1.5">
            <div className="h-full bg-indigo-500 rounded-full transition-all"
              style={{ width: `${questions.length > 0 ? (answeredCount / questions.length) * 100 : 0}%` }} />
          </div>
        </div>

        <div className="space-y-6">
          {categories.map(cat => {
            const catQs = questions.filter(q => q.category === cat);
            return (
              <div key={cat}>
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  {cat}
                </div>
                <div className="space-y-4">
                  {catQs.map((q, qi) => (
                    <div key={q.question_id} className="rounded-xl border border-foreground/10 bg-foreground/5 p-4">
                      <p className="text-sm text-foreground/90 mb-3 leading-relaxed">{q.question_text}</p>
                      <div className="flex gap-2" data-testid={`question-${qi}`}>
                        {[1, 2, 3, 4, 5].map(score => (
                          <button
                            key={score}
                            onClick={() => handleAnswer(q.question_id, score)}
                            className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all border ${
                              answers[q.question_id] === score
                                ? 'bg-indigo-500 border-indigo-400 text-foreground scale-105 shadow-lg shadow-indigo-500/30'
                                : 'border-foreground/10 bg-foreground/5 text-muted-foreground hover:bg-foreground/10 hover:border-foreground/20'
                            }`}
                          >
                            {score}
                          </button>
                        ))}
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-1 px-1">
                        <span>Sangat Tidak Setuju</span>
                        <span>Sangat Setuju</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex gap-3 pb-6">
          <Button variant="outline" className="flex-1" onClick={handleSaveDraft} disabled={submitting}>
            Simpan Draft
          </Button>
          <Button className="flex-1 bg-indigo-600 hover:bg-indigo-700" onClick={handleSubmitForm} disabled={submitting}
            data-testid="submit-form-btn">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Send className="w-4 h-4 mr-1" />}
            Submit Form
          </Button>
        </div>
      </div>
    );
  }

  // ── VIEW: ACHIEVEMENT ────────────────────────────────
  if (view === 'achievement') {
    return (
      <div className="space-y-5 p-4">
        <Button variant="ghost" size="sm" onClick={() => setView('list')}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Kembali
        </Button>
        <div>
          <h2 className="font-bold text-xl flex items-center gap-2">
            <Trophy className="w-5 h-5 text-yellow-500" /> Pencapaian Saya
          </h2>
          <p className="text-sm text-muted-foreground mt-1">Badge dan penghargaan yang telah Anda raih</p>
        </div>
        <KPIGamificationTab token={token} periods={periods} isHR={false} />
      </div>
    );
  }

  // ── VIEW: MAIN LIST ───────────────────────────────────
  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-bold text-xl flex items-center gap-2">
            <Target className="w-5 h-5 text-indigo-600 dark:text-indigo-400" /> KPI Saya
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">Isi form & lihat hasil penilaian Anda</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setView('achievement')} className="gap-1 text-yellow-600 border-yellow-500/40 hover:bg-yellow-100 dark:bg-yellow-500/10">
            <Trophy className="w-3.5 h-3.5" /> Pencapaian
          </Button>
          <Button variant="ghost" size="sm" onClick={() => { loadPeriods(); loadResults(); }}>
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Active periods */}
      {periods.filter(p => p.status === 'open').length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Form Aktif</p>
          {periods.filter(p => p.status === 'open').map(p => (
            <div key={p.period_id}
              className="rounded-xl border border-indigo-400 dark:border-indigo-500/30 bg-indigo-100 dark:bg-indigo-500/5 p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-foreground">{p.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {p.period_from} s.d. {p.period_to}
                  </div>
                  {p.my_submitted_forms > 0 && (
                    <div className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">
                      {p.my_submitted_forms} form sudah disubmit
                    </div>
                  )}
                </div>
                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700 shrink-0"
                  onClick={() => openForms(p)}
                  data-testid="open-kpi-form-btn">
                  Isi Form
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Results history */}
      {myResults.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Riwayat Hasil KPI</p>
          {myResults.map(r => {
            const g = GRADE_CFG[r.grade];
            return (
              <div key={r.result_id}
                className="rounded-xl border border-foreground/10 bg-foreground/5 p-4 flex items-center justify-between"
                data-testid={`kpi-result-${r.period_id}`}>
                <div className="space-y-1">
                  <div className="font-medium text-sm">{r.period_name}</div>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-black text-indigo-600 dark:text-indigo-400">{r.kpi_final?.toFixed(1)}</span>
                    {r.grade && (
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full bg-gradient-to-r ${g?.bg} text-foreground`}>
                        Grade {r.grade}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Perform: {r.perform_score?.toFixed(1)} · Attitude: {r.attitude_score?.toFixed(1)} · Absensi: {r.absensi_score?.toFixed(1)}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => openResult(r)}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {/* Past / closed periods without published results */}
      {periods.filter(p => p.status !== 'open').length > 0 && myResults.length === 0 && (
        <div className="rounded-xl border border-foreground/10 bg-foreground/5 p-4 text-center">
          <Clock className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm text-muted-foreground">Hasil KPI sedang diproses oleh HR</p>
        </div>
      )}

      {periods.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Target className="w-12 h-12 mx-auto mb-3 opacity-25" />
          <p className="font-medium">Belum ada periode KPI</p>
          <p className="text-xs mt-1">HR akan membuka periode KPI saat tersedia</p>
        </div>
      )}
    </div>
  );
}
