/**
 * HRATSModule — Rekrutmen & ATS (Actionable Pipeline)
 * Features:
 *  - Actionable stage transitions (Interview form, Offer form, screening notes)
 *  - CV upload (file or URL)
 *  - Interview scheduling + scoring
 *  - Offer management
 *  - Auto-onboarding on Hired
 *  - Full candidate detail with tabs
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import {
  Briefcase, Users, TrendingUp, Plus, Search, RefreshCw,
  X, Clock, Star, Phone, Mail, Eye,
  BarChart3, AlertCircle, Pencil, Trash2, UserCheck,
  CheckCircle2, ChevronDown, Calendar, Bookmark, BookmarkCheck,
  Upload, Link2, FileText, MessageSquare, Send, ChevronRight,
  Video, MapPin, Award, DollarSign, ArrowRight, ClipboardCheck
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const BASE = process.env.REACT_APP_BACKEND_URL;
const api = (path, opts = {}) =>
  fetch(`${BASE}/api/dewi/recruitment${path}`, { cache: 'no-store', ...opts });

const fmtDate = d =>
  d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';
const fmtCurrency = n =>
  n ? new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(n) : 'Negosiasi';

const STAGES = ['Lamaran Masuk','Screening CV','Interview HR','Interview User','Offering','Hired','Rejected'];

const STAGE_CFG = {
  'Lamaran Masuk':  { color: '#6366f1', bg: '#6366f115', icon: FileText },
  'Screening CV':   { color: '#3b82f6', bg: '#3b82f615', icon: Eye },
  'Interview HR':   { color: '#8b5cf6', bg: '#8b5cf615', icon: MessageSquare },
  'Interview User': { color: '#f59e0b', bg: '#f59e0b15', icon: Users },
  'Offering':       { color: '#14b8a6', bg: '#14b8a615', icon: DollarSign },
  'Hired':          { color: '#10b981', bg: '#10b98115', icon: CheckCircle2 },
  'Rejected':       { color: '#ef4444', bg: '#ef444415', icon: X },
};
const JOB_STATUS = {
  open:    'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-400/20',
  closed:  'bg-muted dark:bg-slate-400/15 text-muted-foreground border-border dark:border-slate-400/20',
  draft:   'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-400/20',
  on_hold: 'bg-orange-50 dark:bg-orange-400/15 text-orange-600 dark:text-orange-400 border-orange-300 dark:border-orange-400/20',
};

function StageBadge({ stage }) {
  const c = STAGE_CFG[stage] || { color: '#64748b', bg: '#64748b15' };
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: c.bg, color: c.color }}>{stage}</span>
  );
}
function RatingStars({ rating = 0, onRate }) {
  return (
    <div className="flex gap-0.5">
      {[1,2,3,4,5].map(s => (
        <Star key={s} className="w-3 h-3 cursor-pointer" onClick={() => onRate && onRate(s)}
          fill={s <= rating ? '#f59e0b' : 'none'} stroke={s <= rating ? '#f59e0b' : '#64748b'} />
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// STAGE ACTION MODAL
// ────────────────────────────────────────────────────────────────────────────
function StageActionModal({ candidate, targetStage, headers, onSuccess, onClose }) {
  const [form, setForm] = useState({
    notes: '',
    scheduled_at: '',
    interviewer: '',
    mode: 'Tatap Muka',
    type: targetStage,
    salary: '',
    allowances: '',
    start_date: '',
    contract_type: 'PKWTT',
    position: candidate?.job_title || '',
    rejection_reason: 'Tidak memenuhi kualifikasi',
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      // Add stage-specific data before moving
      if (targetStage === 'Interview HR' || targetStage === 'Interview User') {
        if (form.scheduled_at) {
          await api(`/candidates/${candidate.candidate_id}/interviews`, {
            method: 'POST', headers,
            body: JSON.stringify({
              type: targetStage,
              scheduled_at: form.scheduled_at,
              interviewer: form.interviewer,
              mode: form.mode,
              notes: form.notes,
            }),
          });
        }
      }
      if (targetStage === 'Offering') {
        await api(`/candidates/${candidate.candidate_id}`, {
          method: 'PUT', headers,
          body: JSON.stringify({
            offer: {
              salary: parseFloat(form.salary) || 0,
              allowances: form.allowances,
              start_date: form.start_date,
              contract_type: form.contract_type,
              position: form.position,
              offered_at: new Date().toISOString(),
            },
          }),
        });
      }
      // Advance the stage
      const r = await api(`/candidates/${candidate.candidate_id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ stage: targetStage, stage_note: form.notes || form.rejection_reason || '' }),
      });
      const d = await r.json();
      if (d.ok) {
        toast.success(targetStage === 'Hired'
          ? 'Kandidat diterima! Onboarding otomatis dibuat.'
          : `Kandidat dipindahkan ke "${targetStage}"`);
        onSuccess();
      }
    } catch (e) {
      toast.error('Gagal memperbarui');
    } finally { setSaving(false); }
  };

  const isInterview = targetStage === 'Interview HR' || targetStage === 'Interview User';
  const isOffer = targetStage === 'Offering';
  const isHired = targetStage === 'Hired';
  const isReject = targetStage === 'Rejected';

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <StageBadge stage={candidate?.stage} />
                <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
                <StageBadge stage={targetStage} />
              </div>
              <p className="font-semibold text-foreground mt-1">{candidate?.name}</p>
            </div>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-3">
            {/* Screening CV */}
            {targetStage === 'Screening CV' && (
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan Screening</label>
                <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-24 resize-none"
                  placeholder="Kualifikasi yang terpenuhi, poin penting dari CV..." />
              </div>
            )}

            {/* Interview */}
            {isInterview && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Tanggal & Waktu *</label>
                    <input type="datetime-local" value={form.scheduled_at} onChange={e => setForm(p => ({...p, scheduled_at: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Mode Interview</label>
                    <select value={form.mode} onChange={e => setForm(p => ({...p, mode: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>Tatap Muka</option><option>Video Call</option><option>Phone</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Interviewer</label>
                  <input value={form.interviewer} onChange={e => setForm(p => ({...p, interviewer: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
                    placeholder="Nama interviewer" />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan tambahan</label>
                  <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-16 resize-none"
                    placeholder="Topik yang akan dibahas, persiapan khusus..." />
                </div>
              </>
            )}

            {/* Offering */}
            {isOffer && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Gaji Ditawarkan (Rp)</label>
                    <input type="number" value={form.salary} onChange={e => setForm(p => ({...p, salary: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
                      placeholder="3000000" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Tipe Kontrak</label>
                    <select value={form.contract_type} onChange={e => setForm(p => ({...p, contract_type: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="PKWTT">PKWTT (Tetap)</option>
                      <option value="PKWT">PKWT (Kontrak)</option>
                      <option value="Magang">Magang</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Mulai Bekerja</label>
                    <input type="date" value={form.start_date} onChange={e => setForm(p => ({...p, start_date: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Posisi</label>
                    <input value={form.position} onChange={e => setForm(p => ({...p, position: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Tunjangan / Benefit</label>
                  <input value={form.allowances} onChange={e => setForm(p => ({...p, allowances: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
                    placeholder="BPJS, transport, makan, dll." />
                </div>
              </>
            )}

            {/* Hired */}
            {isHired && (
              <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                  <span className="font-semibold text-emerald-700 dark:text-emerald-400">Konfirmasi Penerimaan</span>
                </div>
                <p className="text-sm text-emerald-700 dark:text-emerald-400">
                  <strong>{candidate?.name}</strong> akan ditandai sebagai karyawan diterima.
                  Sistem akan otomatis membuat:
                </p>
                <ul className="mt-2 space-y-1 text-sm text-emerald-700 dark:text-emerald-400">
                  <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 shrink-0" />Data karyawan baru</li>
                  <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 shrink-0" />Checklist onboarding</li>
                </ul>
                <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
                  className="mt-3 w-full px-3 py-2 rounded-lg border border-emerald-200 dark:border-emerald-500/30 bg-white/50 dark:bg-emerald-500/5 text-sm h-16 resize-none"
                  placeholder="Catatan penerimaan (opsional)" />
              </div>
            )}

            {/* Rejected */}
            {isReject && (
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Alasan Penolakan</label>
                <select value={form.rejection_reason} onChange={e => setForm(p => ({...p, rejection_reason: e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm mb-2">
                  <option>Tidak memenuhi kualifikasi</option>
                  <option>Gaji tidak sesuai</option>
                  <option>Posisi sudah diisi</option>
                  <option>Hasil interview kurang</option>
                  <option>Mengundurkan diri</option>
                </select>
                <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-16 resize-none"
                  placeholder="Catatan tambahan (opsional)" />
              </div>
            )}
          </div>

          <div className="flex gap-3 mt-5">
            <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
            <button onClick={handleSubmit} disabled={saving}
              className={`flex-1 h-10 rounded-xl text-sm font-semibold disabled:opacity-50 transition-opacity ${
                isReject ? 'bg-red-500 text-white' : isHired ? 'bg-emerald-500 text-white' : 'bg-[hsl(var(--primary))] text-foreground'
              }`}>
              {saving ? 'Menyimpan...' : isHired ? 'Terima Kandidat' : isReject ? 'Tolak' : 'Lanjutkan'}
            </button>
          </div>

          {/* Mock email notice */}
          {candidate?.email && (
            <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
              <Mail className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-blue-700 dark:text-blue-400">Email notifikasi akan dikirim ke <strong>{candidate.email}</strong></p>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-400/20 text-amber-700 dark:text-amber-400 font-medium shrink-0">MOCK</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// INTERVIEW RESULT MODAL
// ────────────────────────────────────────────────────────────────────────────
function InterviewResultModal({ interview, candidateId, headers, onSuccess, onClose }) {
  const [form, setForm] = useState({
    status: interview?.status || 'done',
    result: interview?.result || '',
    score: interview?.score || '',
    notes: interview?.notes || '',
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await api(`/candidates/${candidateId}/interviews/${interview.interview_id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({
          status: form.status,
          result: form.result,
          score: form.score ? parseInt(form.score, 10) : null,
          notes: form.notes,
        }),
      });
      toast.success('Hasil interview disimpan');
      onSuccess();
    } catch { toast.error('Gagal menyimpan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Hasil Interview</h3>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center"><X className="w-4 h-4" /></button>
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Hasil</label>
                <select value={form.result} onChange={e => setForm(p => ({...p, result: e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                  <option value="">Pilih hasil</option>
                  <option value="pass">Lulus</option>
                  <option value="fail">Tidak Lulus</option>
                  <option value="hold">On Hold</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Skor (1-100)</label>
                <input type="number" min="0" max="100" value={form.score} onChange={e => setForm(p => ({...p, score: e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" placeholder="75" />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan Interviewer</label>
              <textarea value={form.notes} onChange={e => setForm(p => ({...p, notes: e.target.value}))}
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-20 resize-none" />
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={onClose} className="flex-1 h-9 rounded-xl border border-[var(--glass-border)] text-sm">Batal</button>
            <button onClick={handleSubmit} disabled={saving}
              className="flex-1 h-9 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
              {saving ? 'Simpan...' : 'Simpan'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// CANDIDATE DETAIL MODAL (Enhanced with tabs)
// ────────────────────────────────────────────────────────────────────────────
function CandidateDetailModal({ candidate: initCandidate, headers, jobs, onStageAction, onRefresh, onClose }) {
  const [candidate, setCandidate] = useState(initCandidate);
  const [detailTab, setDetailTab] = useState('info');
  const [stageAction, setStageAction] = useState(null);
  const [interviewResult, setInterviewResult] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [cvInput, setCvInput] = useState({ url: candidate?.cv_url || '', mode: 'url' });
  const [uploadingCV, setUploadingCV] = useState(false);
  const fileRef = useRef(null);

  const refreshCandidate = async () => {
    try {
      const r = await api(`/candidates/${candidate.candidate_id}`, { headers, cache: 'no-store' });
      const d = await r.json();
      if (d.ok) { setCandidate(d.candidate); onRefresh(); }
    } catch (_e) { /* ignore */ }
  };

  const handleAddNote = async () => {
    if (!noteText.trim()) return;
    setSavingNote(true);
    try {
      await api(`/candidates/${candidate.candidate_id}/notes`, {
        method: 'POST', headers,
        body: JSON.stringify({ text: noteText }),
      });
      setNoteText('');
      refreshCandidate();
    } catch { toast.error('Gagal tambah catatan'); }
    finally { setSavingNote(false); }
  };

  const handleCVSave = async () => {
    setUploadingCV(true);
    try {
      if (cvInput.mode === 'url') {
        await api(`/candidates/${candidate.candidate_id}/upload-cv`, {
          method: 'POST', headers,
          body: JSON.stringify({ cv_url: cvInput.url }),
        });
      }
      toast.success('CV disimpan');
      refreshCandidate();
    } catch { toast.error('Gagal menyimpan CV'); }
    finally { setUploadingCV(false); }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('File terlalu besar. Maks 5MB'); return; }
    setUploadingCV(true);
    try {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const base64 = e.target.result.split(',')[1];
        await api(`/candidates/${candidate.candidate_id}/upload-cv`, {
          method: 'POST', headers,
          body: JSON.stringify({ cv_data: base64, cv_filename: file.name, cv_size: file.size }),
        });
        toast.success('CV berhasil diupload');
        refreshCandidate();
        setUploadingCV(false);
      };
      reader.readAsDataURL(file);
    } catch { toast.error('Gagal upload CV'); setUploadingCV(false); }
  };

  const handleRating = async (rating) => {
    await api(`/candidates/${candidate.candidate_id}`, {
      method: 'PUT', headers,
      body: JSON.stringify({ rating }),
    });
    setCandidate(p => ({...p, rating}));
    onRefresh();
  };

  const ivStatusColor = {
    scheduled: 'text-blue-600 dark:text-blue-400',
    done: 'text-emerald-600 dark:text-emerald-400',
    cancelled: 'text-red-600 dark:text-red-400',
    no_show: 'text-orange-600 dark:text-orange-400',
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl max-w-2xl w-full max-h-[88vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="p-5 border-b border-[var(--glass-border)] shrink-0">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[hsl(var(--primary)/0.15)] flex items-center justify-center text-primary text-lg font-bold shrink-0">
                {candidate.name?.[0]?.toUpperCase()}
              </div>
              <div>
                <h2 className="text-lg font-bold text-foreground">{candidate.name}</h2>
                <p className="text-sm text-muted-foreground">{candidate.job_title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <StageBadge stage={candidate.stage} />
                  <RatingStars rating={candidate.rating} onRate={handleRating} />
                </div>
              </div>
            </div>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Stage Actions */}
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <span className="text-xs text-muted-foreground">Pindahkan ke:</span>
            {STAGES.filter(s => s !== candidate.stage && s !== 'Rejected').slice(0, 3).map(s => {
              const cfg = STAGE_CFG[s];
              return (
                <button key={s} onClick={() => setStageAction(s)}
                  className="text-xs px-3 py-1 rounded-lg border font-medium transition-all hover:opacity-80"
                  style={{ borderColor: cfg?.color + '60', color: cfg?.color, background: cfg?.bg }}>
                  <span>{s}</span>
                </button>
              );
            })}
            {candidate.stage !== 'Rejected' && (
              <button onClick={() => setStageAction('Rejected')}
                className="text-xs px-3 py-1 rounded-lg border border-red-300 dark:border-red-400/30 text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-400/10 font-medium">
                Tolak
              </button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 p-3 border-b border-[var(--glass-border)] shrink-0 overflow-x-auto">
          {[['info','Info'],['cv','CV & Dokumen'],['interviews','Wawancara'],['offer','Penawaran'],['notes','Catatan'],['emails','Email']].map(([k,l]) => (
            <button key={k} onClick={() => setDetailTab(k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                detailTab === k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}>{l}
              {k === 'interviews' && candidate.interviews?.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-[hsl(var(--primary)/0.15)] text-primary">{candidate.interviews.length}</span>
              )}
              {k === 'emails' && candidate.email_logs?.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-blue-100 dark:bg-blue-400/20 text-blue-600 dark:text-blue-400">{candidate.email_logs.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-5">
          {/* INFO */}
          {detailTab === 'info' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="flex items-center gap-2"><Mail className="w-4 h-4 text-muted-foreground shrink-0" /><span>{candidate.email || '—'}</span></div>
                <div className="flex items-center gap-2"><Phone className="w-4 h-4 text-muted-foreground shrink-0" /><span>{candidate.phone || '—'}</span></div>
                <div><span className="text-muted-foreground">Pendidikan:</span> {candidate.education || '—'}</div>
                <div><span className="text-muted-foreground">Pengalaman:</span> {candidate.experience_years} tahun</div>
                <div><span className="text-muted-foreground">Sumber:</span> {candidate.source || '—'}</div>
                <div><span className="text-muted-foreground">Melamar:</span> {fmtDate(candidate.applied_at)}</div>
                {candidate.address && <div className="col-span-2"><span className="text-muted-foreground">Alamat:</span> {candidate.address}</div>}
              </div>
              {candidate.skills?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Skill</p>
                  <div className="flex flex-wrap gap-1.5">
                    {candidate.skills.map(s => <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-[var(--nav-pill-active)] text-muted-foreground">{s}</span>)}
                  </div>
                </div>
              )}
              {/* Timeline */}
              {candidate.timeline?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Timeline</p>
                  <div className="space-y-2">
                    {[...candidate.timeline].reverse().map((t, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: STAGE_CFG[t.stage]?.color || '#64748b' }} />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">{t.stage}</p>
                          <p className="text-xs text-muted-foreground">{fmtDate(t.date)} · {t.by}</p>
                          {t.note && <p className="text-xs text-muted-foreground italic mt-0.5">&quot;{t.note}&quot;</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* CV & DOKUMEN */}
          {detailTab === 'cv' && (
            <div className="space-y-4">
              {/* Existing CV */}
              {(candidate.cv_url || candidate.cv_filename) && (
                <div className="p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">CV Tersimpan</p>
                  {candidate.cv_filename && (
                    <div className="flex items-center gap-2">
                      <FileText className="w-5 h-5 text-primary" />
                      <span className="text-sm font-medium">{candidate.cv_filename}</span>
                      {candidate.cv_data && (
                        <a href={`data:application/pdf;base64,${candidate.cv_data}`} download={candidate.cv_filename}
                          className="ml-auto text-xs px-2 py-1 rounded-lg bg-[hsl(var(--primary)/0.15)] text-primary hover:opacity-80">
                          Download
                        </a>
                      )}
                    </div>
                  )}
                  {candidate.cv_url && (
                    <div className="flex items-center gap-2">
                      <Link2 className="w-5 h-5 text-primary" />
                      <a href={candidate.cv_url} target="_blank" rel="noreferrer"
                        className="text-sm text-primary hover:underline truncate">{candidate.cv_url}</a>
                    </div>
                  )}
                </div>
              )}

              {/* Upload / Link */}
              <div className="p-4 rounded-xl border border-dashed border-[var(--glass-border)] space-y-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Upload / Perbarui CV</p>
                <div className="flex gap-2">
                  <button onClick={() => setCvInput(p => ({...p, mode: 'url'}))}
                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-all ${cvInput.mode === 'url' ? 'bg-[var(--nav-pill-active)] text-foreground border-[var(--glass-border)]' : 'border-[var(--glass-border)] text-muted-foreground'}`}>
                    <Link2 className="w-3.5 h-3.5 inline mr-1" />Link URL
                  </button>
                  <button onClick={() => setCvInput(p => ({...p, mode: 'file'}))}
                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-all ${cvInput.mode === 'file' ? 'bg-[var(--nav-pill-active)] text-foreground border-[var(--glass-border)]' : 'border-[var(--glass-border)] text-muted-foreground'}`}>
                    <Upload className="w-3.5 h-3.5 inline mr-1" />Upload File
                  </button>
                </div>

                {cvInput.mode === 'url' ? (
                  <div className="flex gap-2">
                    <input value={cvInput.url} onChange={e => setCvInput(p => ({...p, url: e.target.value}))}
                      placeholder="https://drive.google.com/..." 
                      className="flex-1 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                    <button onClick={handleCVSave} disabled={uploadingCV || !cvInput.url}
                      className="h-9 px-3 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium disabled:opacity-50">
                      {uploadingCV ? '...' : 'Simpan'}
                    </button>
                  </div>
                ) : (
                  <div>
                    <input type="file" ref={fileRef} className="hidden" accept=".pdf,.doc,.docx"
                      onChange={e => handleFileUpload(e.target.files?.[0])} />
                    <button onClick={() => fileRef.current?.click()} disabled={uploadingCV}
                      className="w-full h-20 rounded-xl border-2 border-dashed border-[var(--glass-border)] flex flex-col items-center justify-center gap-1 hover:border-[hsl(var(--primary)/0.5)] transition-colors disabled:opacity-50">
                      <Upload className="w-5 h-5 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">{uploadingCV ? 'Mengupload...' : 'Klik untuk pilih file (PDF, max 5MB)'}</span>
                    </button>
                  </div>
                )}
              </div>

              {candidate.portfolio_url && (
                <div className="flex items-center gap-2 text-sm">
                  <Link2 className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Portfolio:</span>
                  <a href={candidate.portfolio_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">{candidate.portfolio_url}</a>
                </div>
              )}
            </div>
          )}

          {/* WAWANCARA */}
          {detailTab === 'interviews' && (
            <div className="space-y-3">
              {candidate.interviews?.length === 0 || !candidate.interviews ? (
                <div className="text-center py-8">
                  <MessageSquare className="w-10 h-10 mx-auto mb-2 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">Belum ada jadwal interview</p>
                  <p className="text-xs text-muted-foreground mt-1">Pindahkan kandidat ke &quot;Interview HR&quot; untuk menjadwalkan</p>
                </div>
              ) : (
                candidate.interviews.map(iv => (
                  <div key={iv.interview_id} className="p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{iv.type}</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                          {iv.mode === 'Video Call' ? <Video className="w-3.5 h-3.5" /> : <MapPin className="w-3.5 h-3.5" />}
                          <span>{iv.mode}</span>
                          {iv.interviewer && <><span>·</span><span>{iv.interviewer}</span></>}
                        </div>
                      </div>
                      <div className="text-right">
                        <span className={`text-xs font-medium ${ivStatusColor[iv.status] || 'text-muted-foreground'}`}>
                          {iv.status === 'scheduled' ? 'Terjadwal' : iv.status === 'done' ? 'Selesai' : iv.status === 'cancelled' ? 'Dibatalkan' : 'No Show'}
                        </span>
                        {iv.score != null && <p className="text-xs text-muted-foreground">Skor: {iv.score}/100</p>}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" />{fmtDate(iv.scheduled_at)}</span>
                      {iv.result && (
                        <span className={`px-2 py-0.5 rounded-full font-medium ${
                          iv.result === 'pass' ? 'bg-emerald-50 dark:bg-emerald-400/10 text-emerald-600 dark:text-emerald-400' :
                          iv.result === 'fail' ? 'bg-red-50 dark:bg-red-400/10 text-red-600 dark:text-red-400' :
                          'bg-amber-50 dark:bg-amber-400/10 text-amber-600 dark:text-amber-400'
                        }`}>{iv.result === 'pass' ? 'Lulus' : iv.result === 'fail' ? 'Tidak Lulus' : 'On Hold'}</span>
                      )}
                      {iv.status === 'scheduled' && (
                        <button onClick={() => setInterviewResult(iv)}
                          className="text-xs px-2 py-0.5 rounded-lg bg-[hsl(var(--primary)/0.15)] text-primary hover:opacity-80 font-medium">
                          Isi Hasil
                        </button>
                      )}
                    </div>
                    {iv.notes && <p className="text-xs text-muted-foreground mt-2 italic">&quot;{iv.notes}&quot;</p>}
                  </div>
                ))
              )}
            </div>
          )}

          {/* PENAWARAN */}
          {detailTab === 'offer' && (
            <div className="space-y-3">
              {candidate.offer ? (
                <div className="p-5 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Award className="w-5 h-5 text-primary" />
                    <p className="font-semibold text-foreground">Detail Penawaran</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div><span className="text-muted-foreground">Gaji:</span><p className="font-semibold text-emerald-600 dark:text-emerald-400">{fmtCurrency(candidate.offer.salary)}</p></div>
                    <div><span className="text-muted-foreground">Tipe Kontrak:</span><p className="font-medium">{candidate.offer.contract_type || '—'}</p></div>
                    <div><span className="text-muted-foreground">Mulai Kerja:</span><p className="font-medium">{fmtDate(candidate.offer.start_date)}</p></div>
                    <div><span className="text-muted-foreground">Posisi:</span><p className="font-medium">{candidate.offer.position || candidate.job_title || '—'}</p></div>
                    {candidate.offer.allowances && <div className="col-span-2"><span className="text-muted-foreground">Tunjangan:</span><p className="font-medium">{candidate.offer.allowances}</p></div>}
                  </div>
                  <p className="text-xs text-muted-foreground">Ditawarkan: {fmtDate(candidate.offer.offered_at)}</p>
                </div>
              ) : (
                <div className="text-center py-8">
                  <DollarSign className="w-10 h-10 mx-auto mb-2 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">Belum ada penawaran</p>
                  <p className="text-xs text-muted-foreground mt-1">Pindahkan kandidat ke tahap &quot;Offering&quot; untuk membuat penawaran</p>
                </div>
              )}
              {candidate.onboarding_checklist_id && (
                <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20">
                  <div className="flex items-center gap-2">
                    <ClipboardCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                    <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">Onboarding telah dibuat</p>
                  </div>
                  <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">ID: {candidate.onboarding_checklist_id}</p>
                </div>
              )}
            </div>
          )}

          {/* CATATAN */}
          {detailTab === 'notes' && (
            <div className="space-y-3">
              <div className="space-y-2">
                {(candidate.activity_notes || []).length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">Belum ada catatan</p>
                ) : (
                  [...(candidate.activity_notes || [])].reverse().map(n => (
                    <div key={n.note_id} className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                      <p className="text-sm text-foreground">{n.text}</p>
                      <p className="text-xs text-muted-foreground mt-1">{n.by} · {fmtDate(n.created_at)}</p>
                    </div>
                  ))
                )}
              </div>
              <div className="flex gap-2">
                <input value={noteText} onChange={e => setNoteText(e.target.value)} placeholder="Tambah catatan..."
                  className="flex-1 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm"
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAddNote(); }}} />
                <button onClick={handleAddNote} disabled={savingNote || !noteText.trim()}
                  className="h-9 w-9 rounded-lg bg-[hsl(var(--primary))] text-foreground flex items-center justify-center disabled:opacity-50">
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* EMAIL HISTORY */}
          {detailTab === 'emails' && (
            <div className="space-y-3">
              {/* Mock banner */}
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                <AlertCircle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
                <p className="text-xs text-amber-700 dark:text-amber-400">Integrasi email belum aktif — email tersimpan di log (MOCK). Email tidak benar-benar terkirim.</p>
              </div>

              {!candidate.email_logs?.length ? (
                <div className="text-center py-8">
                  <Mail className="w-10 h-10 mx-auto mb-2 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">Belum ada email terkirim</p>
                  <p className="text-xs text-muted-foreground mt-1">Email otomatis dikirim saat stage kandidat berubah</p>
                </div>
              ) : (
                [...candidate.email_logs].reverse().map(log => (
                  <div key={log.log_id} className="rounded-xl border border-[var(--glass-border)] overflow-hidden">
                    {/* Email header */}
                    <div className="flex items-start justify-between p-4 bg-[var(--glass-bg)]">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <StageBadge stage={log.stage} />
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-400/20 text-amber-700 dark:text-amber-400 font-medium">MOCK</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-400/20 text-emerald-700 dark:text-emerald-400">Terkirim</span>
                        </div>
                        <p className="text-sm font-semibold text-foreground truncate">{log.subject}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">Ke: {log.to} · {fmtDate(log.sent_at)} · Oleh: {log.sent_by}</p>
                      </div>
                    </div>
                    {/* Email body */}
                    <div className="p-4 border-t border-[var(--glass-border)] bg-[var(--card-surface)]">
                      <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed font-mono">{log.body}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Talent pool footer */}
        <div className="p-4 border-t border-[var(--glass-border)] shrink-0">
          <button onClick={async () => {
            await api(`/talent-pool/${candidate.candidate_id}/toggle`, { method: 'POST', headers });
            setCandidate(p => ({...p, is_talent_pool: !p.is_talent_pool}));
            onRefresh();
            toast.success(candidate.is_talent_pool ? 'Dikeluarkan dari Talent Pool' : 'Ditambahkan ke Talent Pool');
          }} className={`w-full py-2 px-4 rounded-xl border text-sm font-medium flex items-center justify-center gap-2 transition-all ${
            candidate.is_talent_pool
              ? 'border-emerald-400 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
              : 'border-amber-400 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
          }`} data-testid="toggle-talent-pool-btn">
            {candidate.is_talent_pool ? <><BookmarkCheck className="w-4 h-4" />Dalam Talent Pool</> : <><Bookmark className="w-4 h-4" />Masukkan ke Talent Pool</>}
          </button>
        </div>
      </div>

      {stageAction && (
        <StageActionModal
          candidate={candidate}
          targetStage={stageAction}
          headers={headers}
          onSuccess={() => { setStageAction(null); refreshCandidate(); }}
          onClose={() => setStageAction(null)}
        />
      )}
      {interviewResult && (
        <InterviewResultModal
          interview={interviewResult}
          candidateId={candidate.candidate_id}
          headers={headers}
          onSuccess={() => { setInterviewResult(null); refreshCandidate(); }}
          onClose={() => setInterviewResult(null)}
        />
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// PIPELINE KANBAN
// ────────────────────────────────────────────────────────────────────────────
function PipelineView({ pipeline, onViewCandidate }) {
  const stages = STAGES.filter(s => s !== 'Rejected');
  return (
    <div className="overflow-x-auto pb-4 -mx-1 px-1">
      <div className="flex gap-3 min-w-max">
        {stages.map(stage => {
          const col = pipeline?.[stage] || { count: 0, candidates: [] };
          const cfg = STAGE_CFG[stage];
          const StageIcon = cfg?.icon || Briefcase;
          return (
            <div key={stage} className="w-60 flex-shrink-0">
              <div className="flex items-center justify-between mb-2 px-1">
                <div className="flex items-center gap-1.5">
                  <StageIcon className="w-3.5 h-3.5" style={{ color: cfg?.color }} />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{stage}</span>
                </div>
                <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: cfg?.bg, color: cfg?.color }}>{col.count}</span>
              </div>
              <div className="space-y-2 min-h-[60px]">
                {col.candidates.map(c => (
                  <div key={c.candidate_id}
                    className="p-3 rounded-xl bg-[var(--card-surface)] border border-[var(--glass-border)] cursor-pointer hover:border-[hsl(var(--primary)/0.3)] hover:shadow-sm transition-all group"
                    onClick={() => onViewCandidate(c)}
                    data-testid={`pipeline-card-${c.candidate_id}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary)/0.15)] flex items-center justify-center text-primary text-xs font-bold">
                        {c.name?.[0]?.toUpperCase() || 'K'}
                      </div>
                      <RatingStars rating={c.rating} />
                    </div>
                    <p className="text-sm font-semibold text-foreground leading-tight">{c.name}</p>
                    <p className="text-xs text-muted-foreground mb-2">{c.job_title}</p>
                    {c.cv_url || c.cv_filename ? (
                      <div className="flex items-center gap-1 text-[10px] text-primary mb-1.5">
                        <FileText className="w-3 h-3" /><span>CV tersedia</span>
                      </div>
                    ) : null}
                    {c.interviews?.length > 0 && (
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground mb-1.5">
                        <Calendar className="w-3 h-3" /><span>{c.interviews.length} interview</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-[10px] text-muted-foreground">{c.source}</span>
                      <span className="text-[10px] text-muted-foreground">{fmtDate(c.applied_at)}</span>
                    </div>
                    <div className="mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={e => { e.stopPropagation(); onViewCandidate(c); }}
                        className="w-full text-[10px] py-1 rounded-lg border border-[var(--glass-border)] text-muted-foreground hover:text-foreground">
                        Lihat Detail & Aksi
                      </button>
                    </div>
                  </div>
                ))}
                {col.candidates.length === 0 && (
                  <div className="h-16 rounded-xl border border-dashed border-[var(--glass-border)] flex items-center justify-center">
                    <span className="text-xs text-muted-foreground/50">Kosong</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// MAIN MODULE
// ────────────────────────────────────────────────────────────────────────────
export default function HRATSModule({ token }) {
  const [tab, setTab] = useState('pipeline');
  const [jobs, setJobs] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [talentPool, setTalentPool] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showJobForm, setShowJobForm] = useState(false);
  const [showCandForm, setShowCandForm] = useState(false);
  const [editJob, setEditJob] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [filterJobId, setFilterJobId] = useState('');
  const [q, setQ] = useState('');
  const [talentSearch, setTalentSearch] = useState('');
  const [jobForm, setJobForm] = useState({ title: '', department: '', location: 'Bandung', type: 'Full-time', level: 'Staff', salary_min: 0, salary_max: 0, headcount: 1, description: '', status: 'open', deadline: '' });
  const [candForm, setCandForm] = useState({ name: '', email: '', phone: '', job_id: '', source: 'Walk-in', education: 'SMA/SMK', experience_years: 0, notes: '', cv_url: '', gender: '', address: '' });
  const [saving, setSaving] = useState(false);
  const [cvFile, setCvFile] = useState(null);
  const cvFileRef = useRef(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  // ── Effects (async IIFE pattern)
  useEffect(() => {
    (async () => {
      setLoading(true); setError(null);
      try {
        const [jRes, pRes, aRes] = await Promise.all([
          api(`/jobs?limit=50`, { headers }),
          api(`/pipeline`, { headers }),
          api(`/analytics`, { headers }),
        ]);
        const [jd, pd, ad] = await Promise.all([jRes.json(), pRes.json(), aRes.json()]);
        setJobs(jd.jobs || []);
        setPipeline(pd.pipeline || null);
        setAnalytics(ad);
      } catch (e) { setError(e.message); }
      finally { setLoading(false); }
    })();
  }, [headers]);

  useEffect(() => {
    if (tab !== 'candidates') return;
    (async () => {
      try {
        const r = await api(`/candidates?limit=100${filterJobId ? `&job_id=${filterJobId}` : ''}`, { headers });
        const d = await r.json();
        setCandidates(d.candidates || []);
      } catch (_e) { /* ignore */ }
    })();
  }, [tab, filterJobId, headers]);

  useEffect(() => {
    if (tab !== 'talent_pool') return;
    (async () => {
      try {
        const r = await api(`/talent-pool${talentSearch ? `?search=${encodeURIComponent(talentSearch)}` : ''}`, { headers });
        const d = await r.json();
        setTalentPool(d.candidates || []);
      } catch (_e) { /* ignore */ }
    })();
  }, [tab, talentSearch, headers]);

  const refresh = useCallback(async () => {
    try {
      const [pRes, aRes, jRes] = await Promise.all([
        api(`/pipeline${filterJobId ? `?job_id=${filterJobId}` : ''}`, { headers }),
        api(`/analytics`, { headers }),
        api(`/jobs?limit=50`, { headers }),
      ]);
      const [pd, ad, jd] = await Promise.all([pRes.json(), aRes.json(), jRes.json()]);
      setPipeline(pd.pipeline || null);
      setAnalytics(ad);
      setJobs(jd.jobs || []);
      if (tab === 'candidates') {
        const r = await api(`/candidates?limit=100${filterJobId ? `&job_id=${filterJobId}` : ''}`, { headers });
        const d = await r.json();
        setCandidates(d.candidates || []);
      }
      if (tab === 'talent_pool') {
        const r = await api(`/talent-pool${talentSearch ? `?search=${encodeURIComponent(talentSearch)}` : ''}`, { headers });
        const d = await r.json();
        setTalentPool(d.candidates || []);
      }
    } catch (_e) { /* ignore */ }
  }, [headers, filterJobId, tab, talentSearch]);

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await api(`/seed`, { method: 'POST', headers });
      await refresh();
      toast.success('Data demo dimuat');
    } catch { toast.error('Gagal muat demo'); }
    finally { setSeeding(false); }
  };

  const openJobForm = (j = null) => {
    setEditJob(j);
    setJobForm(j ? { title: j.title, department: j.department, location: j.location, type: j.type, level: j.level, salary_min: j.salary_min, salary_max: j.salary_max, headcount: j.headcount, description: j.description, status: j.status, deadline: j.deadline ? j.deadline.slice(0, 10) : '' }
      : { title: '', department: '', location: 'Bandung', type: 'Full-time', level: 'Staff', salary_min: 0, salary_max: 0, headcount: 1, description: '', status: 'open', deadline: '' });
    setShowJobForm(true);
  };

  const handleSaveJob = async () => {
    setSaving(true);
    try {
      if (editJob) {
        await api(`/jobs/${editJob.job_id}`, { method: 'PUT', headers, body: JSON.stringify(jobForm) });
      } else {
        await api(`/jobs`, { method: 'POST', headers, body: JSON.stringify(jobForm) });
      }
      setShowJobForm(false);
      await refresh();
      toast.success(editJob ? 'Lowongan diperbarui' : 'Lowongan dibuat');
    } catch { toast.error('Gagal menyimpan'); } finally { setSaving(false); }
  };

  const handleSaveCand = async () => {
    setSaving(true);
    try {
      const r = await api(`/candidates`, { method: 'POST', headers, body: JSON.stringify(candForm) });
      const d = await r.json();
      if (d.ok && cvFile) {
        const reader = new FileReader();
        reader.onload = async (e) => {
          const base64 = e.target.result.split(',')[1];
          await api(`/candidates/${d.candidate.candidate_id}/upload-cv`, {
            method: 'POST', headers,
            body: JSON.stringify({ cv_data: base64, cv_filename: cvFile.name, cv_size: cvFile.size }),
          });
        };
        reader.readAsDataURL(cvFile);
      }
      setShowCandForm(false);
      setCvFile(null);
      await refresh();
      toast.success('Kandidat ditambahkan');
    } catch { toast.error('Gagal menambah kandidat'); } finally { setSaving(false); }
  };

  const filteredCandidates = useMemo(() =>
    candidates.filter(c => !q || c.name?.toLowerCase().includes(q.toLowerCase()) || c.email?.toLowerCase().includes(q.toLowerCase())),
  [candidates, q]);
  const { page, setPage, totalPages, total, paged } = useClientPagination(filteredCandidates, 10);

  if (loading) return (
    <div className="space-y-4 p-4" data-testid="hr-ats-skeleton">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{Array.from({length:4}).map((_,i) => <Skeleton key={i} className="h-20 rounded-xl" />)}</div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );

  return (
    <div className="space-y-5" data-testid="hr-ats-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Briefcase className="w-6 h-6 text-primary" />Rekrutmen & ATS</h1>
          <p className="text-sm text-muted-foreground">Pipeline kandidat actionable — dari lamaran hingga onboarding</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleSeed} disabled={seeding}
            className="h-9 px-3 rounded-lg border border-dashed border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground">
            {seeding ? 'Memuat...' : 'Muat Demo'}
          </button>
          <button onClick={refresh} className="h-9 w-9 rounded-lg border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => openJobForm()}
            className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Buat Lowongan
          </button>
        </div>
      </div>

      {/* KPI */}
      {analytics && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Lowongan Buka', value: analytics.summary?.open_jobs, color: '#10b981', icon: Briefcase },
            { label: 'Total Kandidat', value: analytics.summary?.total_candidates, color: '#6366f1', icon: Users },
            { label: 'Sudah Diterima', value: analytics.summary?.hired, color: '#10b981', icon: UserCheck },
            { label: 'Conversion Rate', value: `${analytics.summary?.conversion_rate || 0}%`, color: '#8b5cf6', icon: TrendingUp },
          ].map((k, i) => (
            <GlassCard key={i} hover={false} className="p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${k.color}20`, border: `1px solid ${k.color}35` }}>
                <k.icon className="w-5 h-5" style={{ color: k.color }} />
              </div>
              <div>
                <p className="text-xl font-bold text-foreground">{k.value}</p>
                <p className="text-xs text-muted-foreground">{k.label}</p>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[var(--nav-pill-bg)] border border-[var(--glass-border)] w-fit flex-wrap">
        {[['pipeline','Pipeline'],['jobs','Lowongan'],['candidates','Kandidat'],['talent_pool','Talent Pool'],['analytics','Analitik']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${tab === k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            data-testid={`ats-tab-${k}`}>{l}</button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 text-sm text-red-700 dark:text-red-400">
          <AlertCircle className="w-4 h-4" />{error}
        </div>
      )}

      {/* PIPELINE */}
      {tab === 'pipeline' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <SmartNativeSelect value={filterJobId} onChange={e => setFilterJobId(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
              <option value="">Semua Lowongan</option>
              {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
            </SmartNativeSelect>
            <button onClick={() => setShowCandForm(true)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] text-sm text-muted-foreground hover:text-foreground flex items-center gap-1.5">
              <Plus className="w-4 h-4" /> Tambah Kandidat
            </button>
            <span className="text-xs text-muted-foreground ml-auto hidden md:block">Klik kartu untuk aksi</span>
          </div>
          {pipeline ? <PipelineView pipeline={pipeline} onViewCandidate={setSelectedCandidate} />
            : <div className="text-center py-12 text-muted-foreground text-sm">Belum ada kandidat. Tambah kandidat atau muat data demo.</div>}
        </div>
      )}

      {/* JOBS */}
      {tab === 'jobs' && (
        <div className="space-y-4">
          {jobs.length === 0 ? <div className="text-center py-12 text-muted-foreground text-sm">Belum ada lowongan</div> : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {jobs.map(j => (
                <GlassCard key={j.job_id} hover className="p-5 group" data-testid={`job-card-${j.job_id}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${JOB_STATUS[j.status] || JOB_STATUS.draft}`}>{j.status === 'open' ? 'Buka' : j.status}</span>
                      <h3 className="font-semibold text-foreground mt-1">{j.title}</h3>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                        <span>{j.location}</span><span>·</span><span>{j.department}</span><span>·</span><span>{j.type}</span>
                      </div>
                    </div>
                    <button onClick={() => openJobForm(j)} className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)] text-muted-foreground opacity-0 group-hover:opacity-100">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex gap-3">
                      <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" />{j.candidate_count || 0}</span>
                      <span className="flex items-center gap-1"><UserCheck className="w-3.5 h-3.5" />{j.hired_count || 0}</span>
                    </div>
                    <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />Deadline: {fmtDate(j.deadline)}</span>
                  </div>
                  <div className="mt-2 text-xs font-medium text-primary">
                    {j.salary_min && j.salary_max ? `${fmtCurrency(j.salary_min)} – ${fmtCurrency(j.salary_max)}` : 'Gaji: Negosiasi'}
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* CANDIDATES */}
      {tab === 'candidates' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-48 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)]">
              <Search className="w-4 h-4 text-muted-foreground" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Cari kandidat..."
                className="flex-1 bg-transparent text-sm focus:outline-none" />
            </div>
            <SmartNativeSelect value={filterJobId} onChange={e => setFilterJobId(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
              <option value="">Semua Lowongan</option>
              {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
            </SmartNativeSelect>
            <button onClick={() => setShowCandForm(true)} className="h-9 px-3 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm flex items-center gap-1">
              <Plus className="w-4 h-4" /> Tambah
            </button>
          </div>
          <GlassCard hover={false} className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr>{['Nama','Posisi','Stage','CV','Rating','Lamaran'].map(h =>
                    <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">{h}</th>)}
                    <th className="px-4 py-3"></th></tr>
                </thead>
                <tbody className="divide-y divide-[var(--glass-border)]">
                  {paged.map(c => (
                    <tr key={c.candidate_id} className="hover:bg-[var(--glass-bg-hover)] cursor-pointer" onClick={() => setSelectedCandidate(c)}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-[hsl(var(--primary)/0.15)] flex items-center justify-center text-xs font-bold text-primary">{c.name?.[0]}</div>
                          <div><p className="font-medium">{c.name}</p><p className="text-xs text-muted-foreground">{c.email}</p></div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{c.job_title}</td>
                      <td className="px-4 py-3"><StageBadge stage={c.stage} /></td>
                      <td className="px-4 py-3">
                        {c.cv_url || c.cv_filename ? <FileText className="w-4 h-4 text-primary" /> : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                      <td className="px-4 py-3"><RatingStars rating={c.rating} /></td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{fmtDate(c.applied_at)}</td>
                      <td className="px-4 py-3">
                        <button onClick={e => { e.stopPropagation(); setSelectedCandidate(c); }}
                          className="p-1.5 rounded hover:bg-foreground/10 text-muted-foreground">
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              {filteredCandidates.length === 0 && <div className="py-10 text-center text-sm text-muted-foreground">Belum ada kandidat</div>}
            </div>
          </GlassCard>
        </div>
      )}

      {/* TALENT POOL */}
      {tab === 'talent_pool' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input value={talentSearch} onChange={e => setTalentSearch(e.target.value)} placeholder="Cari nama, posisi, skill..."
                className="w-full pl-9 pr-3 h-9 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" data-testid="talent-pool-search" />
            </div>
            <span className="text-sm text-muted-foreground">{talentPool.length} kandidat</span>
          </div>
          {talentPool.length > 0 ? (
            <GlassCard hover={false} className="overflow-hidden p-0">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-[var(--glass-border)] text-xs text-muted-foreground">
                  {['Kandidat','Posisi','Stage','Kontak','Ditambahkan',''].map(h => <th key={h} className="text-left px-4 py-3">{h}</th>)}
                </tr></thead>
                <tbody className="divide-y divide-[var(--glass-border)]">
                  {talentPool.map(c => (
                    <tr key={c.candidate_id} className="hover:bg-foreground/5">
                      <td className="px-4 py-3"><div className="font-medium">{c.name}</div><div className="text-xs text-muted-foreground">{c.education}</div>{c.rating > 0 && <RatingStars rating={c.rating} />}</td>
                      <td className="px-4 py-3"><div>{c.position_applied || c.job_title || '—'}</div><div className="text-xs text-muted-foreground">{c.source}</div></td>
                      <td className="px-4 py-3"><StageBadge stage={c.stage} /></td>
                      <td className="px-4 py-3"><div className="text-xs">{c.phone || '—'}</div><div className="text-xs text-muted-foreground">{c.email || '—'}</div></td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{c.talent_pool_added_at ? fmtDate(c.talent_pool_added_at) : '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1">
                          <button onClick={() => setSelectedCandidate(c)} className="p-1.5 rounded hover:bg-foreground/10 text-muted-foreground"><Eye className="w-4 h-4" /></button>
                          <button onClick={async () => { await api(`/talent-pool/${c.candidate_id}/toggle`, { method: 'POST', headers }); refresh(); toast.success('Dikeluarkan dari pool'); }}
                            className="p-1.5 rounded hover:bg-red-100 dark:hover:bg-red-500/10 text-red-700 dark:text-red-400" data-testid={`remove-talent-pool-${c.candidate_id}`}>
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </GlassCard>
          ) : <GlassCard hover={false} className="py-16 text-center"><Users className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" /><p className="text-muted-foreground">Talent Pool kosong</p></GlassCard>}
        </div>
      )}

      {/* ANALYTICS */}
      {tab === 'analytics' && analytics && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-primary" />Funnel Pipeline</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={analytics.pipeline_stages} layout="vertical" margin={{ left: 80 }}>
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="stage" tick={{ fontSize: 10 }} width={80} />
                <Tooltip contentStyle={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }} />
                <Bar dataKey="count" radius={[0,4,4,0]}>
                  {(analytics.pipeline_stages || []).map((s, i) => <Cell key={i} fill={STAGE_CFG[s.stage]?.color || '#6366f1'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>
          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-primary" />Sumber Kandidat</h3>
            <div className="space-y-2">
              {(analytics.source_breakdown || []).map((s, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-xs w-20 text-muted-foreground truncate">{s.source}</span>
                  <div className="flex-1 h-2 rounded-full bg-[var(--glass-border)] overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(s.count / (analytics.summary?.total_candidates || 1)) * 100}%`, background: ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6'][i % 5] }} />
                  </div>
                  <span className="text-xs font-medium w-6 text-right">{s.count}</span>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* CANDIDATE DETAIL MODAL */}
      {selectedCandidate && (
        <CandidateDetailModal
          candidate={selectedCandidate}
          headers={headers}
          jobs={jobs}
          onStageAction={() => {}}
          onRefresh={refresh}
          onClose={() => setSelectedCandidate(null)}
        />
      )}

      {/* JOB FORM */}
      {showJobForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">{editJob ? 'Edit Lowongan' : 'Buat Lowongan Baru'}</h2>
                <button onClick={() => setShowJobForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]"><X className="w-4 h-4" /></button>
              </div>
              <div className="space-y-3">
                <div><label className="text-xs font-medium text-muted-foreground block mb-1">Judul Posisi *</label>
                  <input value={jobForm.title} onChange={e => setJobForm(p => ({...p, title: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Departemen</label>
                    <input value={jobForm.department} onChange={e => setJobForm(p => ({...p, department: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Lokasi</label>
                    <input value={jobForm.location} onChange={e => setJobForm(p => ({...p, location: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Tipe</label>
                    <select value={jobForm.type} onChange={e => setJobForm(p => ({...p, type: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>Full-time</option><option>Part-time</option><option>Contract</option><option>Magang</option>
                    </select></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Level</label>
                    <select value={jobForm.level} onChange={e => setJobForm(p => ({...p, level: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>Staff</option><option>Senior</option><option>Supervisor</option><option>Manager</option>
                    </select></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Gaji Min (Rp)</label>
                    <input type="number" value={jobForm.salary_min} onChange={e => setJobForm(p => ({...p, salary_min: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Gaji Max (Rp)</label>
                    <input type="number" value={jobForm.salary_max} onChange={e => setJobForm(p => ({...p, salary_max: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Headcount</label>
                    <input type="number" min={1} value={jobForm.headcount} onChange={e => setJobForm(p => ({...p, headcount: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Deadline</label>
                    <input type="date" value={jobForm.deadline} onChange={e => setJobForm(p => ({...p, deadline: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div className="col-span-2"><label className="text-xs font-medium text-muted-foreground block mb-1">Status</label>
                    <select value={jobForm.status} onChange={e => setJobForm(p => ({...p, status: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="open">Buka</option><option value="draft">Draft</option><option value="on_hold">Tunda</option><option value="closed">Tutup</option>
                    </select></div>
                </div>
                <div><label className="text-xs font-medium text-muted-foreground block mb-1">Deskripsi</label>
                  <textarea value={jobForm.description} onChange={e => setJobForm(p => ({...p, description: e.target.value}))}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-20 resize-none" /></div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => setShowJobForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm">Batal</button>
                <button onClick={handleSaveJob} disabled={saving || !jobForm.title}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
                  {saving ? 'Menyimpan...' : editJob ? 'Simpan' : 'Buat'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CANDIDATE FORM */}
      {showCandForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">Tambah Kandidat</h2>
                <button onClick={() => setShowCandForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]"><X className="w-4 h-4" /></button>
              </div>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2"><label className="text-xs font-medium text-muted-foreground block mb-1">Nama Lengkap *</label>
                    <input value={candForm.name} onChange={e => setCandForm(p => ({...p, name: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Email</label>
                    <input value={candForm.email} onChange={e => setCandForm(p => ({...p, email: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">No. HP</label>
                    <input value={candForm.phone} onChange={e => setCandForm(p => ({...p, phone: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Lowongan</label>
                    <SmartNativeSelect value={candForm.job_id} onChange={e => setCandForm(p => ({...p, job_id: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="">Pilih lowongan</option>
                      {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
                    </SmartNativeSelect></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Sumber</label>
                    <select value={candForm.source} onChange={e => setCandForm(p => ({...p, source: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>Walk-in</option><option>Jobstreet</option><option>LinkedIn</option><option>Referral</option><option>Website</option>
                    </select></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Pendidikan</label>
                    <select value={candForm.education} onChange={e => setCandForm(p => ({...p, education: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>SMA/SMK</option><option>D3</option><option>S1</option><option>S2</option>
                    </select></div>
                  <div><label className="text-xs font-medium text-muted-foreground block mb-1">Pengalaman (tahun)</label>
                    <input type="number" min={0} value={candForm.experience_years} onChange={e => setCandForm(p => ({...p, experience_years: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" /></div>
                </div>
                {/* CV Upload */}
                <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" />CV / Resume</p>
                  <input value={candForm.cv_url} onChange={e => setCandForm(p => ({...p, cv_url: e.target.value}))} placeholder="Link CV (Google Drive, dll.)"
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">atau</span>
                    <input type="file" ref={cvFileRef} className="hidden" accept=".pdf,.doc,.docx" onChange={e => setCvFile(e.target.files?.[0] || null)} />
                    <button type="button" onClick={() => cvFileRef.current?.click()}
                      className="h-8 px-3 rounded-lg border border-dashed border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5">
                      <Upload className="w-3.5 h-3.5" />{cvFile ? cvFile.name : 'Upload file PDF'}
                    </button>
                    {cvFile && <button onClick={() => setCvFile(null)} className="text-xs text-red-600 dark:text-red-400"><X className="w-3.5 h-3.5" /></button>}
                  </div>
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => setShowCandForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm">Batal</button>
                <button onClick={handleSaveCand} disabled={saving || !candForm.name}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
                  {saving ? 'Menambahkan...' : 'Tambah Kandidat'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
