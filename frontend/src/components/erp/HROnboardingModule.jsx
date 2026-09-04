/**
 * HROnboardingModule — Onboarding Karyawan (Improved)
 * Features:
 *  - Custom activities: add/delete tasks to running checklist
 *  - Template builder: full CRUD with task editor
 *  - Task completion with notes
 *  - Checklist status management (pause/resume)
 *  - Rich checklist detail with descriptions & assigned_to
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { GlassCard } from '@/components/ui/glass';
import {
  UserPlus, CheckCircle2, Circle, AlertCircle, RefreshCw, Plus, X,
  Clock, Users, ClipboardList, User, Pencil, Trash2, Calendar,
  BarChart3, BookOpen, ChevronDown, ChevronRight, Settings,
  GripVertical, Check, PlayCircle, PauseCircle, SquareCheckBig
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

const BASE = process.env.REACT_APP_BACKEND_URL;
const api = (path, opts = {}) =>
  fetch(`${BASE}/api/dewi/onboarding${path}`, { cache: 'no-store', ...opts });

const fmtDate = d =>
  d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';

const STATUS_CFG = {
  active:    { label: 'Aktif',    color: 'bg-blue-50 dark:bg-blue-400/15 text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-400/20' },
  completed: { label: 'Selesai', color: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-400/20' },
  paused:    { label: 'Ditunda', color: 'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-400/20' },
  in_progress: { label: 'Berjalan', color: 'bg-blue-50 dark:bg-blue-400/15 text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-400/20' },
};

const CATEGORIES = ['HR', 'IT', 'Legal', 'Keselamatan', 'Training', 'Administrasi', 'Kustom', 'Umum'];
const CAT_COLORS = { HR: '#6366f1', IT: '#10b981', Legal: '#f59e0b', Keselamatan: '#ef4444', Training: '#8b5cf6', Administrasi: '#14b8a6', Kustom: '#f97316', Umum: '#64748b', default: '#64748b' };

function StatusBadge({ status }) {
  const c = STATUS_CFG[status] || STATUS_CFG.active;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${c.color}`}>{c.label}</span>;
}

function ProgressBar({ pct }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">Progress</span>
        <span className="font-semibold">{pct || 0}%</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--glass-border)] overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct || 0}%`, background: pct >= 100 ? '#10b981' : 'hsl(var(--primary))' }} />
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// TASK COMPLETION NOTE MODAL
// ────────────────────────────────────────────────────────────────────────────
function TaskNoteModal({ task, checklistId, headers, onSuccess, onClose }) {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleComplete = async () => {
    setSaving(true);
    try {
      const r = await api(`/checklists/${checklistId}/tasks/${task.task_id}`, {
        method: 'PUT', headers, body: JSON.stringify({ status: 'done', notes }),
      });
      const d = await r.json();
      if (d.ok) { toast.success('Tugas diselesaikan'); onSuccess(d.checklist); }
    } catch { toast.error('Gagal'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-foreground">Selesaikan Tugas</h3>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center"><X className="w-4 h-4" /></button>
          </div>
          <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] mb-3">
            <p className="text-sm font-medium text-foreground">{task.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{task.category} · {task.assigned_to && `PIC: ${task.assigned_to}`}</p>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground block mb-1">Catatan Penyelesaian (opsional)</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Apa yang dilakukan, temuan, atau kendala..."
              className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-20 resize-none" />
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={onClose} className="flex-1 h-9 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
            <button onClick={handleComplete} disabled={saving}
              className="flex-1 h-9 rounded-xl bg-emerald-500 text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-1.5">
              <Check className="w-4 h-4" />{saving ? '...' : 'Selesai'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// ADD CUSTOM TASK MODAL
// ────────────────────────────────────────────────────────────────────────────
function AddTaskModal({ checklistId, headers, onSuccess, onClose }) {
  const [form, setForm] = useState({ title: '', description: '', category: 'Kustom', assigned_to: '', day: 0, due_date: '' });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!form.title.trim()) { toast.error('Judul tugas diperlukan'); return; }
    setSaving(true);
    try {
      const payload = { ...form };
      if (!payload.due_date) delete payload.due_date;
      const r = await api(`/checklists/${checklistId}/tasks`, {
        method: 'POST', headers, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (d.ok) { toast.success('Aktivitas ditambahkan'); onSuccess(d.checklist); }
    } catch (_e) { toast.error('Gagal menambah aktivitas'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-foreground">Tambah Aktivitas Kustom</h3>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center"><X className="w-4 h-4" /></button>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Nama Aktivitas *</label>
              <input value={form.title} onChange={e => setForm(p => ({...p, title: e.target.value}))} placeholder="Contoh: Meeting perkenalan dengan tim Finance"
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" autoFocus />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Deskripsi</label>
              <textarea value={form.description} onChange={e => setForm(p => ({...p, description: e.target.value}))} placeholder="Penjelasan detail aktivitas..."
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm h-16 resize-none" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Kategori</label>
                <select value={form.category} onChange={e => setForm(p => ({...p, category: e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Hari ke-</label>
                <input type="number" min={0} value={form.day} onChange={e => setForm(p => ({...p, day: +e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">PIC / Penanggung Jawab</label>
                <input value={form.assigned_to} onChange={e => setForm(p => ({...p, assigned_to: e.target.value}))} placeholder="HR / IT / Manager / Nama"
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Deadline (Tanggal)</label>
                <input type="date" value={form.due_date} onChange={e => setForm(p => ({...p, due_date: e.target.value}))}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
              </div>
            </div>
          </div>
          <div className="flex gap-3 mt-5">
            <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
            <button onClick={handleSave} disabled={saving || !form.title.trim()}
              className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
              {saving ? 'Menyimpan...' : 'Tambah Aktivitas'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// CHECKLIST DETAIL
// ────────────────────────────────────────────────────────────────────────────
function ChecklistDetail({ cl: initCl, headers, onUpdate, onClose }) {
  const [cl, setCl] = useState(initCl);
  const [expandedTask, setExpandedTask] = useState(null);
  const [completingTask, setCompletingTask] = useState(null);
  const [addingTask, setAddingTask] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);

  const handleUpdate = (updated) => {
    setCl(updated);
    onUpdate(updated);
  };

  const handleToggleTask = async (task) => {
    if (task.status === 'pending' || task.status === 'skipped') {
      // Show notes modal before completing
      setCompletingTask(task);
    } else {
      // Toggle back to pending directly
      try {
        const r = await api(`/checklists/${cl.checklist_id}/tasks/${task.task_id}`, {
          method: 'PUT', headers, body: JSON.stringify({ status: 'pending' }),
        });
        const d = await r.json();
        if (d.ok) handleUpdate(d.checklist);
      } catch { toast.error('Gagal'); }
    }
  };

  const handleDeleteTask = async (task) => {
    if (!window.confirm(`Hapus aktivitas "${task.title}"?`)) return;
    try {
      const r = await api(`/checklists/${cl.checklist_id}/tasks/${task.task_id}`, { method: 'DELETE', headers });
      const d = await r.json();
      if (d.ok) { handleUpdate(d.checklist); toast.success('Aktivitas dihapus'); }
    } catch { toast.error('Gagal menghapus'); }
  };

  const handleStatusChange = async (newStatus) => {
    setSavingStatus(true);
    try {
      const r = await api(`/checklists/${cl.checklist_id}`, {
        method: 'PUT', headers, body: JSON.stringify({ status: newStatus }),
      });
      const d = await r.json();
      if (d.ok) { handleUpdate(d.checklist); toast.success(`Status diubah ke: ${STATUS_CFG[newStatus]?.label}`); }
    } catch { toast.error('Gagal mengubah status'); }
    finally { setSavingStatus(false); }
  };

  const byCategory = useMemo(() => {
    const acc = {};
    (cl.tasks || []).forEach(t => {
      const cat = t.category || 'Umum';
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(t);
    });
    return acc;
  }, [cl.tasks]);

  const doneTasks = (cl.tasks || []).filter(t => t.status === 'done').length;
  const totalTasks = (cl.tasks || []).length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-foreground">{cl.employee_name}</h2>
          <p className="text-sm text-muted-foreground">{cl.employee_position} · {cl.employee_dept}</p>
        </div>
        <StatusBadge status={cl.status} />
      </div>

      <ProgressBar pct={cl.progress_pct} />

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{doneTasks}</p>
          <p className="text-xs text-muted-foreground">Selesai</p>
        </div>
        <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          <p className="text-lg font-bold">{totalTasks}</p>
          <p className="text-xs text-muted-foreground">Total Tugas</p>
        </div>
        <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          <p className="text-sm font-medium">{cl.buddy || '—'}</p>
          <p className="text-xs text-muted-foreground">Buddy</p>
        </div>
        <div className="p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          <p className="text-sm font-medium">{fmtDate(cl.target_completion)}</p>
          <p className="text-xs text-muted-foreground">Target</p>
        </div>
      </div>

      {/* Checklist Controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          {cl.status === 'active' || cl.status === 'in_progress' ? (
            <button onClick={() => handleStatusChange('paused')} disabled={savingStatus}
              className="h-8 px-3 rounded-lg border border-amber-300 dark:border-amber-400/30 text-amber-700 dark:text-amber-400 text-xs flex items-center gap-1.5 hover:bg-amber-50 dark:hover:bg-amber-400/10 disabled:opacity-50">
              <PauseCircle className="w-3.5 h-3.5" />Tunda
            </button>
          ) : cl.status === 'paused' ? (
            <button onClick={() => handleStatusChange('active')} disabled={savingStatus}
              className="h-8 px-3 rounded-lg border border-blue-300 dark:border-blue-400/30 text-blue-600 dark:text-blue-400 text-xs flex items-center gap-1.5 hover:bg-blue-50 dark:hover:bg-blue-400/10 disabled:opacity-50">
              <PlayCircle className="w-3.5 h-3.5" />Lanjutkan
            </button>
          ) : null}
          {cl.status !== 'completed' && cl.progress_pct === 100 && (
            <button onClick={() => handleStatusChange('completed')} disabled={savingStatus}
              className="h-8 px-3 rounded-lg border border-emerald-300 dark:border-emerald-400/30 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-1.5 hover:bg-emerald-50 dark:hover:bg-emerald-400/10 disabled:opacity-50">
              <SquareCheckBig className="w-3.5 h-3.5" />Tandai Selesai
            </button>
          )}
        </div>
        <button onClick={() => setAddingTask(true)}
          className="h-8 px-3 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium flex items-center gap-1.5 hover:opacity-90">
          <Plus className="w-3.5 h-3.5" />Tambah Aktivitas
        </button>
      </div>

      {/* Tasks by Category */}
      {Object.entries(byCategory).map(([cat, tasks]) => (
        <div key={cat}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full" style={{ background: CAT_COLORS[cat] || CAT_COLORS.default }} />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{cat}</span>
            <span className="text-xs text-muted-foreground">({tasks.filter(t => t.status === 'done').length}/{tasks.length})</span>
          </div>
          <div className="space-y-1.5">
            {tasks.map(t => {
              const isExpanded = expandedTask === t.task_id;
              return (
                <div key={t.task_id}
                  className={`rounded-xl border transition-all ${t.status === 'done' ? 'border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-500/5' : 'border-[var(--glass-border)] bg-[var(--glass-bg)]'}`}>
                  <div className="flex items-center gap-3 p-3">
                    {/* Toggle checkbox */}
                    <button onClick={() => handleToggleTask(t)}
                      className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-all"
                      style={{ background: t.status === 'done' ? '#10b98120' : 'transparent', border: `2px solid ${t.status === 'done' ? '#10b981' : '#475569'}` }}>
                      {t.status === 'done' && <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />}
                    </button>

                    {/* Title & meta */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm ${t.status === 'done' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>{t.title}</p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5 flex-wrap">
                        <span>Hari ke-{t.day}</span>
                        {t.assigned_to && <span className="flex items-center gap-0.5"><User className="w-3 h-3" />{t.assigned_to}</span>}
                        {t.due_date && (
                          <span className={`flex items-center gap-0.5 ${
                            t.status !== 'done' && new Date(t.due_date) < new Date()
                              ? 'text-red-500 dark:text-red-400 font-medium'
                              : ''
                          }`}>
                            <Calendar className="w-3 h-3" />{fmtDate(t.due_date)}
                          </span>
                        )}
                        {t.is_custom && <span className="px-1.5 py-0.5 rounded-full bg-orange-100 dark:bg-orange-400/10 text-orange-700 dark:text-orange-400">Kustom</span>}
                        {t.status === 'done' && t.completed_at && <span className="text-emerald-600 dark:text-emerald-400">· Selesai {fmtDate(t.completed_at)}</span>}
                      </div>
                    </div>

                    {/* Expand & Delete */}
                    <div className="flex items-center gap-1 shrink-0">
                      {(t.description || t.notes || t.completed_by) && (
                        <button onClick={() => setExpandedTask(isExpanded ? null : t.task_id)}
                          className="w-6 h-6 rounded-md hover:bg-foreground/10 flex items-center justify-center text-muted-foreground">
                          {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {t.is_custom && (
                        <button onClick={() => handleDeleteTask(t)}
                          className="w-6 h-6 rounded-md hover:bg-red-100 dark:hover:bg-red-400/10 flex items-center justify-center text-muted-foreground hover:text-red-600 dark:hover:text-red-400">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="px-3 pb-3 pt-0 ml-9 space-y-1.5">
                      {t.description && (
                        <div className="text-xs text-muted-foreground bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)]">
                          {t.description}
                        </div>
                      )}
                      {t.notes && (
                        <div className="text-xs bg-emerald-50 dark:bg-emerald-400/5 rounded-lg px-3 py-2 border border-emerald-200 dark:border-emerald-400/20">
                          <span className="text-emerald-700 dark:text-emerald-400 font-medium">Catatan: </span>
                          <span className="text-emerald-700 dark:text-emerald-300">{t.notes}</span>
                        </div>
                      )}
                      {t.completed_by && <p className="text-xs text-muted-foreground">Diselesaikan oleh: {t.completed_by}</p>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Modals */}
      {completingTask && (
        <TaskNoteModal
          task={completingTask} checklistId={cl.checklist_id} headers={headers}
          onSuccess={(updated) => { setCompletingTask(null); handleUpdate(updated); }}
          onClose={() => setCompletingTask(null)}
        />
      )}
      {addingTask && (
        <AddTaskModal
          checklistId={cl.checklist_id} headers={headers}
          onSuccess={(updated) => { setAddingTask(false); handleUpdate(updated); }}
          onClose={() => setAddingTask(false)}
        />
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// TEMPLATE TASK ROW
// ────────────────────────────────────────────────────────────────────────────
function TemplateTaskRow({ task, onDelete, onEdit, index }) {
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ day: task.day, assigned_to: task.assigned_to || '' });

  const handleSave = () => {
    onEdit(task.task_id || String(index), editForm);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="p-3 rounded-xl border-2 border-[hsl(var(--primary)/0.4)] bg-[hsl(var(--primary)/0.03)] space-y-2">
        <p className="text-xs font-semibold text-foreground truncate">{task.title}</p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Deadline (Hari ke-)</label>
            <input type="number" min={0} value={editForm.day} onChange={e => setEditForm(p => ({...p, day: +e.target.value}))}
              className="w-full h-8 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">PIC / Penanggung Jawab</label>
            <input value={editForm.assigned_to} onChange={e => setEditForm(p => ({...p, assigned_to: e.target.value}))}
              placeholder="HR / IT / Karyawan" className="w-full h-8 px-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={() => setEditing(false)} className="h-7 px-3 text-xs text-muted-foreground hover:text-foreground">Batal</button>
          <button onClick={handleSave}
            className="h-7 px-3 text-xs bg-[hsl(var(--primary))] text-foreground rounded-lg font-medium">Simpan</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 p-2.5 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] group">
      <GripVertical className="w-3.5 h-3.5 text-muted-foreground/30 shrink-0" />
      <div className="w-2 h-2 rounded-full shrink-0" style={{ background: CAT_COLORS[task.category] || CAT_COLORS.default }} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{task.title}</p>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{task.category}</span>
          <span>·</span>
          <span className="flex items-center gap-0.5"><Clock className="w-3 h-3" />Hari ke-{task.day}</span>
          {task.assigned_to && <><span>·</span><span className="flex items-center gap-0.5"><User className="w-3 h-3" />{task.assigned_to}</span></>}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={() => { setEditForm({ day: task.day, assigned_to: task.assigned_to || '' }); setEditing(true); }}
          className="w-6 h-6 rounded-md hover:bg-[var(--nav-pill-active)] flex items-center justify-center text-muted-foreground"
          title="Edit deadline & PIC">
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button onClick={() => onDelete(task.task_id || index)}
          className="w-6 h-6 rounded-md hover:bg-red-100 dark:hover:bg-red-400/10 flex items-center justify-center text-muted-foreground hover:text-red-600 dark:hover:text-red-400">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// TEMPLATE EDITOR MODAL
// ────────────────────────────────────────────────────────────────────────────
function TemplateEditorModal({ template, headers, onSuccess, onClose }) {
  const isNew = !template?.template_id;
  const [meta, setMeta] = useState({
    name: template?.name || '',
    dept: template?.dept || 'Semua',
    description: template?.description || '',
    duration_days: template?.duration_days || 30,
    is_default: template?.is_default || false,
  });
  const [tasks, setTasks] = useState(template?.tasks?.map((t, i) => ({ task_id: t.task_id || `tmp-${i}`, ...t })) || []);
  const [addTaskForm, setAddTaskForm] = useState({ title: '', category: 'HR', assigned_to: 'HR', day: 1, description: '' });
  const [showAddTask, setShowAddTask] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleAddTask = () => {
    if (!addTaskForm.title.trim()) return;
    const newTask = { task_id: `tmp-${Date.now()}`, ...addTaskForm };
    setTasks(p => [...p, newTask].sort((a, b) => a.day - b.day));
    setAddTaskForm({ title: '', category: 'HR', assigned_to: 'HR', day: 1, description: '' });
    setShowAddTask(false);
  };

  const handleDeleteTask = (taskId) => {
    setTasks(p => p.filter(t => t.task_id !== taskId && t !== taskId));
  };

  const handleEditTask = (taskId, updates) => {
    setTasks(p => p.map(t => t.task_id === taskId ? { ...t, ...updates } : t));
  };

  const handleSave = async () => {
    if (!meta.name.trim()) { toast.error('Nama template diperlukan'); return; }
    setSaving(true);
    try {
      const body = { ...meta, tasks };
      let r;
      if (isNew) {
        r = await api(`/templates`, { method: 'POST', headers, body: JSON.stringify(body) });
      } else {
        r = await api(`/templates/${template.template_id}`, { method: 'PUT', headers, body: JSON.stringify(body) });
      }
      const d = await r.json();
      if (d.ok) {
        toast.success(isNew ? 'Template dibuat' : 'Template diperbarui');
        onSuccess();
      }
    } catch { toast.error('Gagal menyimpan'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="p-5 border-b border-[var(--glass-border)] shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">{isNew ? 'Buat Template Baru' : `Edit: ${template.name}`}</h2>
            <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--nav-pill-active)] flex items-center justify-center"><X className="w-4 h-4" /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="text-xs font-medium text-muted-foreground block mb-1">Nama Template *</label>
              <input value={meta.name} onChange={e => setMeta(p => ({...p, name: e.target.value}))} placeholder="Contoh: Onboarding Operator Produksi"
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Departemen</label>
              <input value={meta.dept} onChange={e => setMeta(p => ({...p, dept: e.target.value}))} placeholder="Semua / Produksi / HR..."
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Durasi (hari)</label>
              <input type="number" min={1} value={meta.duration_days} onChange={e => setMeta(p => ({...p, duration_days: +e.target.value}))}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-muted-foreground block mb-1">Deskripsi</label>
              <textarea value={meta.description} onChange={e => setMeta(p => ({...p, description: e.target.value}))} rows={2}
                className="w-full px-3 py-2 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm resize-none" />
            </div>
            <div className="col-span-2 flex items-center gap-2">
              <input type="checkbox" id="is_default" checked={meta.is_default} onChange={e => setMeta(p => ({...p, is_default: e.target.checked}))}
                className="w-4 h-4 rounded" />
              <label htmlFor="is_default" className="text-sm text-muted-foreground">Jadikan template default (dipakai otomatis saat candidate di-hire)</label>
            </div>
          </div>

          {/* Tasks */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Daftar Aktivitas</p>
                <p className="text-xs text-muted-foreground">{tasks.length} aktivitas · Diurutkan berdasarkan hari</p>
              </div>
              <button onClick={() => setShowAddTask(!showAddTask)}
                className="h-8 px-3 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium flex items-center gap-1.5">
                <Plus className="w-3.5 h-3.5" />Tambah Aktivitas
              </button>
            </div>

            {showAddTask && (
              <div className="mb-3 p-4 rounded-xl border-2 border-dashed border-[hsl(var(--primary)/0.4)] bg-[hsl(var(--primary)/0.03)] space-y-2">
                <p className="text-xs font-semibold text-primary">Aktivitas Baru</p>
                <div className="grid grid-cols-2 gap-2">
                  <div className="col-span-2">
                    <input value={addTaskForm.title} onChange={e => setAddTaskForm(p => ({...p, title: e.target.value}))} placeholder="Nama aktivitas *"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" autoFocus />
                  </div>
                  <select value={addTaskForm.category} onChange={e => setAddTaskForm(p => ({...p, category: e.target.value}))}
                    className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                    {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                  </select>
                  <input value={addTaskForm.assigned_to} onChange={e => setAddTaskForm(p => ({...p, assigned_to: e.target.value}))} placeholder="PIC (HR/IT/Karyawan)"
                    className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-muted-foreground whitespace-nowrap">Hari ke-</label>
                    <input type="number" min={0} value={addTaskForm.day} onChange={e => setAddTaskForm(p => ({...p, day: +e.target.value}))}
                      className="flex-1 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <input value={addTaskForm.description} onChange={e => setAddTaskForm(p => ({...p, description: e.target.value}))} placeholder="Deskripsi (opsional)"
                    className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                </div>
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setShowAddTask(false)} className="h-8 px-3 rounded-lg border border-[var(--glass-border)] text-xs text-muted-foreground">Batal</button>
                  <button onClick={handleAddTask} disabled={!addTaskForm.title.trim()}
                    className="h-8 px-3 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium disabled:opacity-50">Tambah</button>
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              {tasks.length === 0 ? (
                <div className="text-center py-6 text-muted-foreground text-sm border border-dashed border-[var(--glass-border)] rounded-xl">
                  Belum ada aktivitas. Klik &quot;Tambah Aktivitas&quot; untuk mulai.
                </div>
              ) : (
                tasks.map((t, i) => <TemplateTaskRow key={t.task_id || i} task={t} index={i} onDelete={handleDeleteTask} onEdit={handleEditTask} />)
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[var(--glass-border)] shrink-0 flex gap-3">
          <button onClick={onClose} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
          <button onClick={handleSave} disabled={saving || !meta.name.trim()}
            className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
            {saving ? 'Menyimpan...' : isNew ? 'Buat Template' : 'Simpan Perubahan'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// MAIN MODULE
// ────────────────────────────────────────────────────────────────────────────
export default function HROnboardingModule({ token }) {
  const [tab, setTab] = useState('checklists');
  const [checklists, setChecklists] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [editTemplate, setEditTemplate] = useState(undefined);  // undefined=closed, null=new, obj=edit
  const [form, setForm] = useState({ employee_id: '', employee_name: '', employee_dept: '', employee_position: '', template_id: '', buddy: '', supervisor: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  // ── Effects
  useEffect(() => {
    (async () => {
      setLoading(true); setError(null);
      try {
        const [clRes, tRes, aRes] = await Promise.all([
          api(`/checklists?limit=50`, { headers }),
          api(`/templates`, { headers }),
          api(`/analytics`, { headers }),
        ]);
        const [cl, tpl, an] = await Promise.all([clRes.json(), tRes.json(), aRes.json()]);
        setChecklists(cl.checklists || []);
        setTemplates(tpl.templates || []);
        setAnalytics(an);
      } catch (e) { setError(e.message); }
      finally { setLoading(false); }
    })();
  }, [headers]);

  const refreshAll = async () => {
    try {
      const [clRes, tRes, aRes] = await Promise.all([
        api(`/checklists?limit=50`, { headers }),
        api(`/templates`, { headers }),
        api(`/analytics`, { headers }),
      ]);
      const [cl, tpl, an] = await Promise.all([clRes.json(), tRes.json(), aRes.json()]);
      setChecklists(cl.checklists || []);
      setTemplates(tpl.templates || []);
      setAnalytics(an);
    } catch (_e) { /* ignore */ }
  };

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await api(`/seed`, { method: 'POST', headers });
      await refreshAll();
      toast.success('Data demo dimuat');
    } catch { toast.error('Gagal'); }
    finally { setSeeding(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api(`/checklists`, { method: 'POST', headers, body: JSON.stringify(form) });
      setShowForm(false);
      await refreshAll();
      toast.success('Onboarding checklist dibuat');
    } catch { toast.error('Gagal membuat checklist'); } finally { setSaving(false); }
  };

  const handleUpdateChecklist = (updated) => {
    setChecklists(prev => prev.map(c => c.checklist_id === updated.checklist_id ? updated : c));
    setSelected(updated);
  };

  const handleDeleteTemplate = async (tplId, name) => {
    if (!window.confirm(`Hapus template "${name}"?`)) return;
    try {
      await api(`/templates/${tplId}`, { method: 'DELETE', headers });
      await refreshAll();
      toast.success('Template dihapus');
    } catch { toast.error('Gagal menghapus'); }
  };

  const filtered = useMemo(() =>
    checklists.filter(c => {
      if (filterStatus && c.status !== filterStatus) return false;
      if (q && !c.employee_name?.toLowerCase().includes(q.toLowerCase())) return false;
      return true;
    }),
  [checklists, q, filterStatus]);

  if (loading) return (
    <div className="space-y-4 p-4" data-testid="hr-onboarding-skeleton">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{Array.from({length:4}).map((_,i) => <Skeleton key={i} className="h-20 rounded-xl" />)}</div>
      <Skeleton className="h-48 rounded-xl" />
    </div>
  );

  return (
    <div className="space-y-5" data-testid="hr-onboarding-module">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><UserPlus className="w-6 h-6 text-primary" />Onboarding Karyawan</h1>
          <p className="text-sm text-muted-foreground">Checklist onboarding dengan aktivitas kustom & template builder</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleSeed} disabled={seeding}
            className="h-9 px-3 rounded-lg border border-dashed border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground">
            {seeding ? 'Memuat...' : 'Muat Demo'}
          </button>
          <button onClick={refreshAll} className="h-9 w-9 rounded-lg border border-[var(--glass-border)] flex items-center justify-center text-muted-foreground hover:text-foreground">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => setShowForm(true)} data-testid="onboarding-add-btn"
            className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium hover:opacity-90 flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Onboarding Baru
          </button>
        </div>
      </div>

      {/* Stats */}
      {analytics && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { label: 'Total', value: analytics.summary?.total, color: '#6366f1' },
            { label: 'Aktif', value: analytics.summary?.active, color: '#3b82f6' },
            { label: 'Selesai', value: analytics.summary?.completed, color: '#10b981' },
            { label: 'Overdue', value: analytics.summary?.overdue, color: '#ef4444' },
            { label: 'Avg Progress', value: `${analytics.summary?.avg_progress || 0}%`, color: '#8b5cf6' },
          ].map((k, i) => (
            <GlassCard key={i} hover={false} className="p-4 text-center">
              <p className="text-2xl font-bold" style={{ color: k.color }}>{k.value}</p>
              <p className="text-xs text-muted-foreground mt-1">{k.label}</p>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-[var(--nav-pill-bg)] border border-[var(--glass-border)] w-fit">
        {[['checklists','Checklist'],['analytics','Analitik'],['templates','Template Builder']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${tab === k ? 'bg-[var(--nav-pill-active)] text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{l}</button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-400/20 text-sm text-red-700 dark:text-red-400">
          <AlertCircle className="w-4 h-4" />{error}
        </div>
      )}

      {/* CHECKLISTS */}
      {tab === 'checklists' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-48 h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)]">
              <User className="w-4 h-4 text-muted-foreground" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Cari karyawan..."
                className="flex-1 bg-transparent text-sm focus:outline-none" />
            </div>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
              className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
              <option value="">Semua Status</option>
              <option value="active">Aktif</option>
              <option value="in_progress">Berjalan</option>
              <option value="completed">Selesai</option>
              <option value="paused">Ditunda</option>
            </select>
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <ClipboardList className="w-10 h-10 text-muted-foreground/30" />
              <p className="text-muted-foreground text-sm">Belum ada checklist onboarding</p>
              <button onClick={() => setShowForm(true)} className="h-8 px-4 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium">Buat Onboarding Baru</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {filtered.map(cl => (
                <GlassCard key={cl.checklist_id} hover className="p-5 cursor-pointer" onClick={() => setSelected(cl)} data-testid={`checklist-card-${cl.checklist_id}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[hsl(var(--primary)/0.15)] flex items-center justify-center text-primary font-bold">
                        {cl.employee_name?.[0]?.toUpperCase() || 'K'}
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">{cl.employee_name}</p>
                        <p className="text-xs text-muted-foreground">{cl.employee_position} · {cl.employee_dept}</p>
                      </div>
                    </div>
                    <StatusBadge status={cl.status} />
                  </div>
                  <ProgressBar pct={cl.progress_pct} />
                  <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <ClipboardList className="w-3.5 h-3.5" />{cl.completed_tasks}/{cl.total_tasks} selesai
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5" />Target: {fmtDate(cl.target_completion)}
                    </span>
                  </div>
                  {cl.buddy && <p className="text-xs text-muted-foreground mt-1.5">Buddy: {cl.buddy}</p>}
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ANALYTICS */}
      {tab === 'analytics' && analytics && (
        <div className="space-y-5">
          <GlassCard hover={false} className="p-5">
            <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><ClipboardList className="w-4 h-4 text-primary" />Onboarding Terbaru</h3>
            <div className="space-y-3">
              {(analytics.recent || []).map(cl => (
                <div key={cl.checklist_id} className="flex items-center gap-3 p-3 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] cursor-pointer hover:border-[hsl(var(--primary)/0.3)]"
                  onClick={() => { setTab('checklists'); setSelected(cl); }}>
                  <div className="w-8 h-8 rounded-full bg-[hsl(var(--primary)/0.15)] flex items-center justify-center text-primary text-sm font-bold">
                    {cl.employee_name?.[0]?.toUpperCase() || 'K'}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium">{cl.employee_name}</p>
                    <p className="text-xs text-muted-foreground">{cl.employee_position}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold">{cl.progress_pct}%</p>
                    <StatusBadge status={cl.status} />
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* TEMPLATE BUILDER */}
      {tab === 'templates' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">Template Onboarding</p>
              <p className="text-xs text-muted-foreground">{templates.length} template tersedia</p>
            </div>
            <button onClick={() => setEditTemplate(null)}
              className="h-9 px-4 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium flex items-center gap-1.5 hover:opacity-90">
              <Plus className="w-4 h-4" />Template Baru
            </button>
          </div>

          {templates.length === 0 ? (
            <div className="text-center py-12">
              <BookOpen className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-muted-foreground text-sm">Belum ada template</p>
              <button onClick={() => setEditTemplate(null)} className="mt-3 h-8 px-4 rounded-lg bg-[hsl(var(--primary))] text-foreground text-xs font-medium">Buat Template Pertama</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {templates.map(t => (
                <GlassCard key={t.template_id} hover={false} className="p-5">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <h3 className="font-semibold text-foreground">{t.name}</h3>
                        {t.is_default && <span className="text-xs px-2 py-0.5 rounded-full bg-[hsl(var(--primary)/0.15)] text-primary border border-[hsl(var(--primary)/0.3)]">Default</span>}
                      </div>
                      <p className="text-xs text-muted-foreground">{t.description}</p>
                    </div>
                    <div className="flex gap-1 shrink-0 ml-2">
                      <button onClick={() => setEditTemplate(t)}
                        className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)] text-muted-foreground">
                        <Settings className="w-3.5 h-3.5" />
                      </button>
                      {!t.is_default && (
                        <button onClick={() => handleDeleteTemplate(t.template_id, t.name)}
                          className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-red-100 dark:hover:bg-red-400/10 text-muted-foreground hover:text-red-600 dark:hover:text-red-400">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-muted-foreground mt-3 mb-3">
                    <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" />{t.dept}</span>
                    <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />{t.duration_days} hari</span>
                    <span className="flex items-center gap-1"><ClipboardList className="w-3.5 h-3.5" />{(t.tasks || []).length} tugas</span>
                  </div>

                  {/* Category summary */}
                  {t.tasks?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries((t.tasks || []).reduce((acc, task) => {
                        const cat = task.category || 'Umum';
                        acc[cat] = (acc[cat] || 0) + 1;
                        return acc;
                      }, {})).map(([cat, count]) => (
                        <span key={cat} className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                          style={{ background: `${CAT_COLORS[cat] || CAT_COLORS.default}20`, color: CAT_COLORS[cat] || CAT_COLORS.default }}>
                          {cat} ({count})
                        </span>
                      ))}
                    </div>
                  )}

                  <button onClick={() => setEditTemplate(t)}
                    className="mt-3 w-full h-8 rounded-lg border border-[var(--glass-border)] text-xs text-muted-foreground hover:text-foreground hover:border-[hsl(var(--primary)/0.3)] transition-colors flex items-center justify-center gap-1.5">
                    <Pencil className="w-3.5 h-3.5" />Edit Aktivitas
                  </button>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      )}

      {/* CHECKLIST DETAIL MODAL */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl max-w-2xl w-full max-h-[88vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-bold text-lg">Detail Onboarding</h2>
                <button onClick={() => setSelected(null)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]"><X className="w-4 h-4" /></button>
              </div>
              <ChecklistDetail cl={selected} headers={headers} onUpdate={handleUpdateChecklist} onClose={() => setSelected(null)} />
            </div>
          </div>
        </div>
      )}

      {/* CREATE CHECKLIST MODAL */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--card-surface)] rounded-2xl border border-[var(--glass-border)] shadow-2xl w-full max-w-lg">
            <div className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold">Buat Onboarding Baru</h2>
                <button onClick={() => setShowForm(false)} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--nav-pill-active)]"><X className="w-4 h-4" /></button>
              </div>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Nama Karyawan *</label>
                    <input value={form.employee_name} onChange={e => setForm(p => ({...p, employee_name: e.target.value}))} placeholder="Nama lengkap"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Jabatan</label>
                    <input value={form.employee_position} onChange={e => setForm(p => ({...p, employee_position: e.target.value}))} placeholder="Jabatan"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Departemen</label>
                    <input value={form.employee_dept} onChange={e => setForm(p => ({...p, employee_dept: e.target.value}))} placeholder="Departemen"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Buddy</label>
                    <input value={form.buddy} onChange={e => setForm(p => ({...p, buddy: e.target.value}))} placeholder="Nama buddy"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Supervisor</label>
                    <input value={form.supervisor} onChange={e => setForm(p => ({...p, supervisor: e.target.value}))} placeholder="Nama supervisor"
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm" />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-muted-foreground block mb-1">Template</label>
                    <SmartNativeSelect value={form.template_id} onChange={e => setForm(p => ({...p, template_id: e.target.value}))}
                      className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm">
                      <option value="">Gunakan Default</option>
                      {templates.map(t => <option key={t.template_id} value={t.template_id}>{t.name}{t.is_default ? ' (Default)' : ''}</option>)}
                    </SmartNativeSelect>
                  </div>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setShowForm(false)} className="flex-1 h-10 rounded-xl border border-[var(--glass-border)] text-sm text-muted-foreground">Batal</button>
                <button onClick={handleSave} disabled={saving || !form.employee_name}
                  className="flex-1 h-10 rounded-xl bg-[hsl(var(--primary))] text-foreground text-sm font-medium disabled:opacity-50">
                  {saving ? 'Membuat...' : 'Buat Checklist'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TEMPLATE EDITOR MODAL */}
      {editTemplate !== undefined && (
        <TemplateEditorModal
          template={editTemplate}
          headers={headers}
          onSuccess={() => { setEditTemplate(undefined); refreshAll(); }}
          onClose={() => setEditTemplate(undefined)}
        />
      )}
    </div>
  );
}
