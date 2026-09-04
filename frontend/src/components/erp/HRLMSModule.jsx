import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import {
  BookOpen, Plus, Search, Filter, Users, Clock, Award, TrendingUp,
  ChevronRight, Play, CheckCircle2, Circle, BarChart3, RefreshCw,
  Pencil, Trash2, X, BookMarked, Video, FileText, HelpCircle,
  GraduationCap, Star, AlertCircle, Eye, UserPlus, ChevronDown, Check
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Skeleton } from '@/components/ui/skeleton';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = (path, opts = {}) => fetch(`${BACKEND_URL}/api/dewi/lms${path}`, opts);
const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';
const fmtPct = v => `${v ?? 0}%`;

const STATUS_CONFIG = {
  enrolled:    { label: 'Terdaftar',    color: 'bg-blue-50 dark:bg-blue-400/15 text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-400/20' },
  in_progress: { label: 'Berjalan',    color: 'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-400/20' },
  completed:   { label: 'Selesai',     color: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-400/20' },
  failed:      { label: 'Gagal',       color: 'bg-red-50 dark:bg-red-400/15 text-red-700 dark:text-red-400 border-red-300 dark:border-red-400/20' },
  draft:       { label: 'Draft',       color: 'bg-muted dark:bg-slate-400/15 text-muted-foreground border-border dark:border-slate-400/20' },
  active:      { label: 'Aktif',       color: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-400/20' },
  archived:    { label: 'Diarsipkan', color: 'bg-muted dark:bg-slate-400/15 text-muted-foreground border-border dark:border-slate-400/20' },
};

const MATERIAL_TYPE_CONFIG = {
  text:  { label: 'Teks',    icon: FileText,   color: '#6366f1' },
  video: { label: 'Video',   icon: Video,      color: '#ec4899' },
  pdf:   { label: 'PDF',     icon: BookMarked, color: '#ef4444' },
  slides:{ label: 'Slides',  icon: BookOpen,   color: '#f59e0b' },
  quiz:  { label: 'Quiz',    icon: HelpCircle, color: '#10b981' },
};

const LEVEL_CONFIG = {
  Beginner:     { label: 'Pemula',       color: '#10b981' },
  Intermediate: { label: 'Menengah',     color: '#f59e0b' },
  Advanced:     { label: 'Lanjutan',     color: '#ef4444' },
};

const CATEGORY_COLORS = [
  '#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#14b8a6','#ec4899'
];

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${cfg.color}`}>{cfg.label}</span>
  );
}

function ProgressRing({ pct, size = 48 }) {
  const r = (size / 2) - 4;
  const circ = 2 * Math.PI * r;
  const dash = ((pct ?? 0) / 100) * circ;
  const color = pct >= 100 ? '#10b981' : pct > 0 ? '#6366f1' : '#475569';
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size/2} cy={size/2} r={r} stroke="rgba(100,116,139,0.2)" strokeWidth={4} fill="none" />
      <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth={4} fill="none"
        strokeDasharray={circ} strokeDashoffset={circ - dash}
        strokeLinecap="round" style={{ transition: 'stroke-dashoffset 0.5s ease' }}
      />
    </svg>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function HRLMSModule({ token }) {
  const [tab, setTab] = useState('courses'); // courses | enrollments | analytics
  const [courses, setCourses] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [q, setQ] = useState('');
  const [filterCat, setFilterCat] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [selected, setSelected] = useState(null); // course detail
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ title: '', description: '', category: 'Umum', level: 'Beginner', duration_hours: 4, instructor: '', pass_score: 75, status: 'draft' });
  const [saving, setSaving] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [cRes, aRes] = await Promise.all([
        API(`/courses?limit=50`, { headers }),
        API(`/analytics`, { headers }),
      ]);
      const [cData, aData] = await Promise.all([cRes.json(), aRes.json()]);
      setCourses(cData.courses || []);
      setAnalytics(aData);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [headers]);

  const fetchEnrollments = useCallback(async () => {
    try {
      const r = await API(`/enrollments?limit=50`, { headers });
      const d = await r.json();
      setEnrollments(d.enrollments || []);
    } catch {}
  }, [headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => { if (tab === 'enrollments') fetchEnrollments(); }, [tab, fetchEnrollments]);

  const handleSeed = async () => {
    setSeeding(true);
    await API(`/seed`, { method: 'POST', headers });
    setSeeding(false);
    fetchAll();
  };

  const openForm = (c = null) => {
    setEditing(c);
    setForm(c ? { title: c.title, description: c.description, category: c.category, level: c.level,
      duration_hours: c.duration_hours, instructor: c.instructor, pass_score: c.pass_score, status: c.status }
      : { title: '', description: '', category: 'Umum', level: 'Beginner', duration_hours: 4, instructor: '', pass_score: 75, status: 'draft' });
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) {
        await API(`/courses/${editing.course_id}`, { method: 'PUT', headers, body: JSON.stringify(form) });
      } else {
        await API(`/courses`, { method: 'POST', headers, body: JSON.stringify(form) });
      }
      setShowForm(false);
      fetchAll();
    } catch {} finally { setSaving(false); }
  };

  const handleDelete = async (cid) => {
    if (!window.confirm('Yakin hapus kursus ini?')) return;
    await API(`/courses/${cid}`, { method: 'DELETE', headers });
    fetchAll();
    if (selected?.course_id === cid) setSelected(null);
  };

  const filtered = useMemo(() => courses.filter(c => {
    if (filterCat && c.category !== filterCat) return false;
    if (filterStatus && c.status !== filterStatus) return false;
    if (q && !c.title.toLowerCase().includes(q.toLowerCase()) && !c.description.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  }), [courses, q, filterCat, filterStatus]);

  const categories = useMemo(() => [...new Set(courses.map(c => c.category))], [courses]);
  const { page, setPage, totalPages, total, paged } = useClientPagination(enrollments, 10);

  if (loading) return (
    <div className="space-y-4 p-4" data-testid="hr-lms-skeleton">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
      </div>
    </div>
  );

  return (
    <div className="space-y-5" data-testid="hr-lms-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <GraduationCap className="w-6 h-6 text-primary" />
            Learning Management System
          </h1>
          <p className="text-muted-foreground text-sm">Manajemen kursus, materi, dan progress karyawan</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleSeed} disabled={seeding}
            className="h-9 px-3 rounded-lg border border-dashed border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground transition-colors"
            data-testid="lms-seed-btn">
            {seeding ? 'Memuat...' : 'Muat Demo'}
          </button>
          <button onClick={() => openForm()} data-testid="lms-add-btn"
            className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Kursus Baru
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[var(--nav-pill-bg)] border border-[var(--glass-border)] w-fit">
        {[['courses','Daftar Kursus'],['enrollments','Pendaftaran'],['analytics','Analitik']].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 ${
              tab === k ? 'bg-[var(--nav-pill-active)] text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`} data-testid={`lms-tab-${k}`}>{l}</button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 text-sm text-red-700 dark:text-red-400">
          <AlertCircle className="w-4 h-4" />{error}
        </div>
      )}

      {/* ─── COURSES TAB ──────────────────────────────────── */}
      {tab === 'courses' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-56 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)]">
              <Search className="w-4 h-4 text-muted-foreground" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Cari kursus..."
                className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="lms-search" />
            </div>
            <SmartNativeSelect value={filterCat} onChange={e => setFilterCat(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" data-testid="lms-filter-cat">
              <option value="">Semua Kategori</option>
              {categories.map(c => <option key={c}>{c}</option>)}
            </SmartNativeSelect>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
              <option value="">Semua Status</option>
              <option value="active">Aktif</option>
              <option value="draft">Draft</option>
              <option value="archived">Diarsipkan</option>
            </select>
            <button onClick={fetchAll} className="h-9 w-9 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] flex items-center justify-center text-muted-foreground hover:text-foreground">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>

          {/* Course Grid */}
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <GraduationCap className="w-10 h-10 text-muted-foreground/30" />
              <p className="text-muted-foreground text-sm">Belum ada kursus. Klik "Kursus Baru" atau "Muat Demo".</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map(c => (
                <GlassCard key={c.course_id} hover className="p-5 cursor-pointer group" onClick={() => setSelected(c)} data-testid={`course-card-${c.course_id}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                        style={{ background: `${CATEGORY_COLORS[categories.indexOf(c.category) % CATEGORY_COLORS.length]}20`, border: `1px solid ${CATEGORY_COLORS[categories.indexOf(c.category) % CATEGORY_COLORS.length]}35` }}>
                        <BookOpen className="w-5 h-5" style={{ color: CATEGORY_COLORS[categories.indexOf(c.category) % CATEGORY_COLORS.length] }} />
                      </div>
                      <div>
                        <StatusBadge status={c.status} />
                        <div className="text-xs text-muted-foreground mt-0.5">{c.category}</div>
                      </div>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={e => { e.stopPropagation(); openForm(c); }}
                        className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)] text-muted-foreground hover:text-foreground">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={e => { e.stopPropagation(); handleDelete(c.course_id); }}
                        className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-red-50 dark:bg-red-400/10 text-muted-foreground hover:text-red-700 dark:text-red-400">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <h3 className="font-semibold text-foreground text-sm mb-1 line-clamp-2 group-hover:text-primary transition-colors">{c.title}</h3>
                  <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{c.description}</p>

                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />{c.duration_hours}j</span>
                      <span style={{ color: LEVEL_CONFIG[c.level]?.color }}>{LEVEL_CONFIG[c.level]?.label || c.level}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" />{c.enrollment_count || 0}</span>
                      <span className="flex items-center gap-1"><Award className="w-3.5 h-3.5" />{c.completion_count || 0}</span>
                    </div>
                  </div>

                  {(c.enrollment_count > 0) && (
                    <div className="mt-3">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-muted-foreground">Completion rate</span>
                        <span className="font-medium">{Math.round((c.completion_count || 0) / (c.enrollment_count || 1) * 100)}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-[var(--glass-border)] overflow-hidden">
                        <div className="h-full rounded-full bg-[hsl(var(--primary))]" style={{ width: `${Math.round((c.completion_count || 0) / (c.enrollment_count || 1) * 100)}%` }} />
                      </div>
                    </div>
                  )}
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── ENROLLMENTS TAB ──────────────────────────────── */}
      {tab === 'enrollments' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{enrollments.length} total enrollment</p>
            <button onClick={fetchEnrollments} className="h-8 px-3 rounded-lg border border-[var(--glass-border)] text-xs flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>
          <GlassCard hover={false} className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr>
                    {['Karyawan','Kursus','Status','Progress','Nilai','Sertifikat','Terdaftar'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--glass-border)]">
                  {paged.map(e => (
                    <tr key={e.enrollment_id} className="hover:bg-[var(--glass-bg-hover)] transition-colors">
                      <td className="px-4 py-3 font-medium text-foreground">{e.employee_name}</td>
                      <td className="px-4 py-3 text-muted-foreground max-w-xs truncate">{e.course_title}</td>
                      <td className="px-4 py-3"><StatusBadge status={e.status} /></td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-[var(--glass-border)] overflow-hidden">
                            <div className="h-full rounded-full bg-[hsl(var(--primary))]" style={{ width: `${e.progress_pct || 0}%` }} />
                          </div>
                          <span className="text-xs font-medium">{e.progress_pct || 0}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {e.quiz_score != null ? <span className="text-sm font-bold" style={{ color: e.passed ? '#10b981' : '#ef4444' }}>{e.quiz_score}</span> : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        {e.certificate_issued ? (
                          <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400"><Award className="w-3.5 h-3.5" />{e.certificate_no}</span>
                        ) : <span className="text-muted-foreground text-xs">—</span>}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{fmtDate(e.enrolled_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              {enrollments.length === 0 && (
                <div className="py-12 text-center text-muted-foreground text-sm">Belum ada pendaftaran</div>
              )}
            </div>
          </GlassCard>
        </div>
      )}

      {/* ─── ANALYTICS TAB ───────────────────────────────── */}
      {tab === 'analytics' && analytics && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { label: 'Total Kursus', value: analytics.summary?.total_courses, icon: BookOpen, color: '#6366f1' },
              { label: 'Total Pendaftar', value: analytics.summary?.total_enrollments, icon: Users, color: '#10b981' },
              { label: 'Sudah Selesai', value: analytics.summary?.completed, icon: CheckCircle2, color: '#10b981' },
              { label: 'Sedang Berjalan', value: analytics.summary?.in_progress, icon: Play, color: '#f59e0b' },
              { label: 'Sertifikat Diterbitkan', value: analytics.summary?.certificates_issued, icon: Award, color: '#8b5cf6' },
              { label: 'Completion Rate', value: `${analytics.summary?.completion_rate || 0}%`, icon: TrendingUp, color: '#14b8a6' },
            ].map((k, i) => (
              <GlassCard key={i} hover={false} className="p-5 flex items-start gap-4">
                <div className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0" style={{ background: `${k.color}20`, border: `1px solid ${k.color}35` }}>
                  <k.icon className="w-5 h-5" style={{ color: k.color }} />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-2xl font-bold text-foreground">{k.value}</p>
                </div>
              </GlassCard>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Category Breakdown */}
            <GlassCard hover={false} className="p-5">
              <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-primary" />Kursus per Kategori</h3>
              {(analytics.category_breakdown || []).length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={analytics.category_breakdown} layout="vertical" margin={{ left: 60 }}>
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={60} />
                    <Tooltip contentStyle={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 10, fontSize: 12 }} />
                    <Bar dataKey="count" radius={[0,4,4,0]}>
                      {(analytics.category_breakdown || []).map((_, i) => (
                        <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <p className="text-sm text-muted-foreground text-center py-8">Belum ada data</p>}
            </GlassCard>

            {/* Top Courses */}
            <GlassCard hover={false} className="p-5">
              <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><Star className="w-4 h-4 text-primary" />Kursus Paling Banyak Diminati</h3>
              <div className="space-y-3">
                {(analytics.top_courses || []).map((c, i) => (
                  <div key={c.course_id} className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{ background: `${CATEGORY_COLORS[i % CATEGORY_COLORS.length]}20`, color: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}>{i + 1}</div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{c.title}</p>
                      <p className="text-xs text-muted-foreground">{c.enrollment_count} pendaftar · {c.completion_count} selesai</p>
                    </div>
                  </div>
                ))}
                {(analytics.top_courses || []).length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Belum ada data</p>}
              </div>
            </GlassCard>
          </div>
        </div>
      )}

      {/* ─── COURSE DETAIL MODAL ──────────────────────────── */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <StatusBadge status={selected.status} />
                  <h2 className="text-xl font-bold text-foreground mt-2">{selected.title}</h2>
                  <p className="text-muted-foreground text-sm mt-1">{selected.description}</p>
                </div>
                <button onClick={() => setSelected(null)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
                <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                  <p className="text-lg font-bold">{selected.duration_hours}j</p>
                  <p className="text-xs text-muted-foreground">Durasi</p>
                </div>
                <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                  <p className="text-lg font-bold" style={{ color: LEVEL_CONFIG[selected.level]?.color }}>{LEVEL_CONFIG[selected.level]?.label || selected.level}</p>
                  <p className="text-xs text-muted-foreground">Level</p>
                </div>
                <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                  <p className="text-lg font-bold">{selected.enrollment_count || 0}</p>
                  <p className="text-xs text-muted-foreground">Pendaftar</p>
                </div>
                <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] text-center">
                  <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{selected.pass_score}%</p>
                  <p className="text-xs text-muted-foreground">Pass Score</p>
                </div>
              </div>
              {selected.instructor && (
                <div className="flex items-center gap-2 text-sm mb-4">
                  <Users className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Instruktur:</span>
                  <span className="font-medium">{selected.instructor}</span>
                </div>
              )}
              {selected.tags?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {selected.tags.map(t => (
                    <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-[var(--nav-pill-active)] text-muted-foreground">{t}</span>
                  ))}
                </div>
              )}
              {(selected.materials || []).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-3">Materi Kursus</h3>
                  <div className="space-y-2">
                    {selected.materials.map((m, i) => {
                      const tc = MATERIAL_TYPE_CONFIG[m.type] || MATERIAL_TYPE_CONFIG.text;
                      return (
                        <div key={m.material_id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${tc.color}20` }}>
                            <tc.icon className="w-4 h-4" style={{ color: tc.color }} />
                          </div>
                          <div className="flex-1">
                            <p className="text-sm font-medium">{m.title}</p>
                            <p className="text-xs text-muted-foreground">{tc.label} · {m.duration_minutes}m</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── ADD/EDIT FORM MODAL ──────────────────────────── */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">{editing ? 'Edit Kursus' : 'Buat Kursus Baru'}</h2>
                <button onClick={() => setShowForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Judul Kursus *</label>
                  <input value={form.title} onChange={e => setForm(p => ({...p, title: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" placeholder="Judul kursus" />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Deskripsi</label>
                  <textarea value={form.description} onChange={e => setForm(p => ({...p, description: e.target.value}))}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm resize-none h-20" placeholder="Deskripsi kursus" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Kategori</label>
                    <input value={form.category} onChange={e => setForm(p => ({...p, category: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" placeholder="e.g. K3, Orientasi" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Level</label>
                    <select value={form.level} onChange={e => setForm(p => ({...p, level: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option>Beginner</option><option>Intermediate</option><option>Advanced</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Durasi (jam)</label>
                    <input type="number" value={form.duration_hours} onChange={e => setForm(p => ({...p, duration_hours: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" min={1} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Pass Score (%)</label>
                    <input type="number" value={form.pass_score} onChange={e => setForm(p => ({...p, pass_score: +e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" min={0} max={100} />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Instruktur</label>
                  <input value={form.instructor} onChange={e => setForm(p => ({...p, instructor: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" placeholder="Nama instruktur" />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground block mb-1">Status</label>
                  <select value={form.status} onChange={e => setForm(p => ({...p, status: e.target.value}))}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                    <option value="draft">Draft</option><option value="active">Aktif</option><option value="archived">Diarsipkan</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setShowForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground hover:text-foreground">Batal</button>
                <button onClick={handleSave} disabled={saving || !form.title}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50">
                  {saving ? 'Menyimpan...' : (editing ? 'Simpan' : 'Buat Kursus')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
