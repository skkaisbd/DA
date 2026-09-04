import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import TipTapEditor from '@/components/ui/TipTapEditor';
import PaginationBar from '@/components/ui/PaginationBar';
import PushNotificationToggle from '@/components/erp/PushNotificationToggle';
import {
  Loader2, Plus, Trash2, Edit3, Save, X, CheckSquare, Square, Bell,
  Calendar, Link as LinkIcon, StickyNote, ChevronLeft, ChevronRight,
  Pin, PinOff, Star, Clock, AlertTriangle, Repeat, LayoutGrid, GripVertical
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

// ── Module catalog for Quick Links ───────────────────────────────────────────
const MODULE_CATALOG = [
  { id: 'dashboard', label: 'Dashboard Utama', portal: 'management' },
  { id: 'self-dashboard', label: 'Kehadiran & Payslip', portal: 'self' },
  { id: 'portal-dashboard', label: 'Dashboard Saya', portal: 'self' },
  { id: 'portal-cuti', label: 'Cuti & Izin Saya', portal: 'self' },
  { id: 'portal-payslip', label: 'Slip Gaji Saya', portal: 'self' },
  { id: 'kpi-portal', label: 'KPI Saya', portal: 'self' },
  { id: 'production-dashboard', label: 'Dashboard Produksi', portal: 'production' },
  { id: 'wms-accessories', label: 'WMS Aksesoris', portal: 'warehouse' },
  { id: 'finance-dashboard', label: 'Dashboard Keuangan', portal: 'finance' },
  { id: 'hris-dashboard', label: 'Dashboard HR', portal: 'hr' },
  { id: 'marketing-dashboard', label: 'Dashboard Marketing', portal: 'marketing' },
  { id: 'maklon-dashboard', label: 'Dashboard Maklon', portal: 'maklon' },
];

const PRIORITY_CFG = {
  high:   { label: 'Tinggi', color: 'bg-red-100 text-red-700 border-red-200' },
  medium: { label: 'Sedang', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  low:    { label: 'Rendah', color: 'bg-green-100 text-green-700 border-green-200' },
};

const NOTE_COLORS = ['#ffffff', '#fef9c3', '#dcfce7', '#dbeafe', '#fce7f3', '#ede9fe', '#ffedd5'];

// ═══════════════════════════════════════════════════════════════════
// NOTEPAD
// ═══════════════════════════════════════════════════════════════════
function WorkspaceNotepad({ headers }) {
  const { toast } = useToast();
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeNote, setActiveNote] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editColor, setEditColor] = useState('#ffffff');
  const [saving, setSaving] = useState(false);
  const autoSaveRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/portal/notes`, { headers });
      setNotes(data.items || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const openNote = (note) => {
    setActiveNote(note);
    setEditTitle(note.title);
    setEditContent(note.content);
    setEditColor(note.color || '#ffffff');
  };

  const newNote = async () => {
    try {
      const { data } = await axios.post(`${API}/api/portal/notes`, { title: 'Catatan Baru', content: '' }, { headers });
      setNotes(prev => [data, ...prev]);
      openNote(data);
    } catch (e) {
      toast({ title: 'Gagal membuat catatan.', variant: 'destructive' });
    }
  };

  const saveNote = async () => {
    if (!activeNote) return;
    setSaving(true);
    try {
      const { data } = await axios.put(`${API}/api/portal/notes/${activeNote.id}`, {
        title: editTitle, content: editContent, color: editColor,
      }, { headers });
      setNotes(prev => prev.map(n => n.id === data.id ? data : n));
      setActiveNote(data);
    } catch (e) {
      toast({ title: 'Gagal menyimpan.', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  // Auto-save after 2 seconds of inactivity
  useEffect(() => {
    if (!activeNote) return;
    clearTimeout(autoSaveRef.current);
    autoSaveRef.current = setTimeout(saveNote, 2000);
    return () => clearTimeout(autoSaveRef.current);
  }, [editTitle, editContent, editColor]); // eslint-disable-line

  const deleteNote = async (id) => {
    if (!window.confirm('Hapus catatan ini?')) return;
    try {
      await axios.delete(`${API}/api/portal/notes/${id}`, { headers });
      setNotes(prev => prev.filter(n => n.id !== id));
      if (activeNote?.id === id) setActiveNote(null);
      toast({ title: 'Catatan dihapus.' });
    } catch (e) {
      toast({ title: 'Gagal.', variant: 'destructive' });
    }
  };

  const togglePin = async (note) => {
    try {
      const { data } = await axios.put(`${API}/api/portal/notes/${note.id}`,
        { is_pinned: !note.is_pinned }, { headers });
      setNotes(prev => prev.map(n => n.id === data.id ? data : n));
    } catch (e) { console.error(e); }
  };

  const pinned = notes.filter(n => n.is_pinned);
  const unpinned = notes.filter(n => !n.is_pinned);

  if (loading) return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin" /></div>;

  return (
    <div className="flex gap-4 h-[580px]">
      {/* Sidebar */}
      <div className="w-56 flex-shrink-0 flex flex-col gap-2">
        <Button data-testid="btn-new-note" size="sm" className="w-full" onClick={newNote}>
          <Plus className="w-4 h-4 mr-1" /> Catatan Baru
        </Button>
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {pinned.length > 0 && (
            <p className="text-xs text-muted-foreground px-1 pt-1">PINNED</p>
          )}
          {pinned.map(n => (
            <NoteItem key={n.id} note={n} active={activeNote?.id === n.id}
              onOpen={() => openNote(n)} onDelete={deleteNote} onPin={togglePin} />
          ))}
          {unpinned.length > 0 && pinned.length > 0 && (
            <p className="text-xs text-muted-foreground px-1 pt-1">CATATAN</p>
          )}
          {unpinned.map(n => (
            <NoteItem key={n.id} note={n} active={activeNote?.id === n.id}
              onOpen={() => openNote(n)} onDelete={deleteNote} onPin={togglePin} />
          ))}
          {notes.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">Belum ada catatan</p>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 flex flex-col gap-2 min-w-0">
        {activeNote ? (
          <>
            <div className="flex items-center gap-2">
              <input
                data-testid="note-title-input"
                className="flex-1 border rounded-lg px-3 py-2 text-sm font-semibold focus:ring-2 focus:ring-primary/30 outline-none"
                value={editTitle}
                onChange={e => setEditTitle(e.target.value)}
                placeholder="Judul catatan..."
              />
              <div className="flex items-center gap-1">
                {NOTE_COLORS.map(c => (
                  <button key={c} type="button"
                    onClick={() => setEditColor(c)}
                    className={`w-5 h-5 rounded-full border-2 transition-transform ${editColor === c ? 'border-primary scale-125' : 'border-border'}`}
                    style={{ backgroundColor: c }} />
                ))}
              </div>
              <Button data-testid="btn-save-note" size="sm" variant="outline" onClick={saveNote} disabled={saving}>
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              </Button>
            </div>
            <div style={{ backgroundColor: editColor }} className="flex-1 rounded-lg overflow-hidden">
              <TipTapEditor value={editContent} onChange={setEditContent} minHeight={240} />
            </div>
            <p className="text-xs text-muted-foreground text-right">Auto-save aktif · Terakhir disimpan: {activeNote.updated_at?.slice(0, 16).replace('T', ' ')}</p>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground flex-col gap-3">
            <StickyNote className="w-12 h-12 opacity-30" />
            <p className="text-sm">Pilih catatan atau buat catatan baru</p>
            <Button size="sm" onClick={newNote}><Plus className="w-4 h-4 mr-1" /> Catatan Baru</Button>
          </div>
        )}
      </div>
    </div>
  );
}

function NoteItem({ note, active, onOpen, onDelete, onPin }) {
  return (
    <div
      data-testid={`note-item-${note.id}`}
      onClick={onOpen}
      className={`group flex items-start justify-between p-2 rounded-lg cursor-pointer text-sm transition-colors
        ${active ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted/60'}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          {note.is_pinned && <Pin className="w-2.5 h-2.5 text-primary flex-shrink-0" />}
          <p className="font-medium truncate text-xs">{note.title}</p>
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5"
          dangerouslySetInnerHTML={{ __html: note.content?.replace(/<[^>]+>/g, ' ').slice(0, 40) || '' }}
        />
      </div>
      <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ml-1">
        <button onClick={e => { e.stopPropagation(); onPin(note); }}
          className="p-0.5 rounded hover:bg-primary/20">
          {note.is_pinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
        </button>
        <button onClick={e => { e.stopPropagation(); onDelete(note.id); }}
          className="p-0.5 rounded hover:bg-red-100 text-red-700 dark:text-red-500">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TODO LIST
// ═══════════════════════════════════════════════════════════════════
function WorkspaceTodo({ headers }) {
  const { toast } = useToast();
  const [todos, setTodos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('active');
  const [showForm, setShowForm] = useState(false);
  const [skip, setSkip] = useState(0);
  const [total, setTotal] = useState(0);
  const LIMIT = 20;
  const [form, setForm] = useState({ title: '', priority: 'medium', due_date: '', notes: '' });

  const load = useCallback(async () => {
    try {
      const params = { skip, limit: LIMIT };
      if (filter === 'active') params.done = false;
      if (filter === 'done') params.done = true;
      const { data } = await axios.get(`${API}/api/portal/todos`, { headers, params });
      setTodos(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers, filter, skip]);

  useEffect(() => { load(); }, [load]);

  const addTodo = async () => {
    if (!form.title.trim()) { toast({ title: 'Judul wajib diisi.', variant: 'destructive' }); return; }
    try {
      const { data } = await axios.post(`${API}/api/portal/todos`, form, { headers });
      setTodos(prev => [data, ...prev]);
      setForm({ title: '', priority: 'medium', due_date: '', notes: '' });
      setShowForm(false);
    } catch (e) {
      toast({ title: 'Gagal.', variant: 'destructive' });
    }
  };

  const toggleDone = async (todo) => {
    try {
      const { data } = await axios.put(`${API}/api/portal/todos/${todo.id}`, { done: !todo.done }, { headers });
      setTodos(prev => filter === 'all' ? prev.map(t => t.id === data.id ? data : t) : prev.filter(t => t.id !== todo.id));
    } catch (e) { console.error(e); }
  };

  const deleteTodo = async (id) => {
    try {
      await axios.delete(`${API}/api/portal/todos/${id}`, { headers });
      setTodos(prev => prev.filter(t => t.id !== id));
    } catch (e) { toast({ title: 'Gagal.', variant: 'destructive' }); }
  };

  const isOverdue = (t) => t.due_date && !t.done && t.due_date < new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {['active', 'done', 'all'].map(f => (
            <button key={f} onClick={() => { setFilter(f); setSkip(0); }}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors
                ${filter === f ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}>
              {f === 'active' ? 'Aktif' : f === 'done' ? 'Selesai' : 'Semua'}
            </button>
          ))}
        </div>
        <Button data-testid="btn-add-todo" size="sm" onClick={() => setShowForm(v => !v)}>
          <Plus className="w-4 h-4 mr-1" /> Tambah
        </Button>
      </div>

      {showForm && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="pt-4 space-y-3">
            <input data-testid="todo-title-input"
              className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="Apa yang perlu dikerjakan?" autoFocus
              value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && addTodo()}
            />
            <div className="flex gap-2 items-center flex-wrap">
              <select data-testid="todo-priority-select"
                className="border rounded-lg px-2 py-1.5 text-xs outline-none"
                value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                <option value="high">Tinggi</option>
                <option value="medium">Sedang</option>
                <option value="low">Rendah</option>
              </select>
              <input type="date" data-testid="todo-due-date"
                className="border rounded-lg px-2 py-1.5 text-xs outline-none"
                value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
              <Button data-testid="btn-save-todo" size="sm" onClick={addTodo}>Simpan</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}><X className="w-4 h-4" /></Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin" /></div> : (
        <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
          {todos.length === 0 && (
            <div className="text-center py-10 text-muted-foreground">
              <CheckSquare className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Tidak ada tugas {filter === 'done' ? 'selesai' : filter === 'active' ? 'aktif' : ''}.</p>
            </div>
          )}
          {todos.map(todo => {
            const cfg = PRIORITY_CFG[todo.priority] || PRIORITY_CFG.medium;
            const overdue = isOverdue(todo);
            return (
              <div key={todo.id} data-testid={`todo-item-${todo.id}`}
                className={`flex items-center gap-3 p-3 rounded-lg border hover:shadow-sm transition-all
                  ${todo.done ? 'bg-muted/30 opacity-60' : overdue ? 'border-red-200 bg-red-50' : 'bg-background'}`}>
                <button onClick={() => toggleDone(todo)} className="flex-shrink-0">
                  {todo.done
                    ? <CheckSquare className="w-5 h-5 text-primary" />
                    : <Square className="w-5 h-5 text-muted-foreground hover:text-primary" />
                  }
                </button>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${todo.done ? 'line-through text-muted-foreground' : ''}`}>
                    {todo.title}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${cfg.color}`}>{cfg.label}</span>
                    {todo.due_date && (
                      <span className={`text-xs flex items-center gap-1 ${overdue ? 'text-red-600' : 'text-muted-foreground'}`}>
                        {overdue && <AlertTriangle className="w-3 h-3" />}
                        <Clock className="w-3 h-3" /> {todo.due_date}
                      </span>
                    )}
                  </div>
                </div>
                <button onClick={() => deleteTodo(todo.id)} className="p-1 rounded hover:bg-red-100 text-muted-foreground hover:text-red-600 flex-shrink-0">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}
      <PaginationBar total={total} skip={skip} limit={LIMIT} onPageChange={setSkip} className="pt-1" />
    </div>
  );
}
// ═══════════════════════════════════════════════════════════════════
// REMINDERS
// ═══════════════════════════════════════════════════════════════════
function WorkspaceReminder({ headers }) {
  const { toast } = useToast();
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const [skip, setSkip] = useState(0);
  const [total, setTotal] = useState(0);
  const LIMIT = 20;
  const [form, setForm] = useState({
    title: '', description: '', remind_at: '', recurrence: 'once',
    whatsapp_enabled: false, whatsapp_number: '',
  });

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/portal/reminders`, { headers, params: { show_done: showDone, skip, limit: LIMIT } });
      setReminders(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers, showDone, skip]);

  useEffect(() => { load(); }, [load]);

  const addReminder = async () => {
    if (!form.title.trim()) { toast({ title: 'Judul wajib diisi.', variant: 'destructive' }); return; }
    try {
      const { data } = await axios.post(`${API}/api/portal/reminders`, form, { headers });
      setReminders(prev => [data, ...prev]);
      setForm({ title: '', description: '', remind_at: '', recurrence: 'once', whatsapp_enabled: false, whatsapp_number: '' });
      setShowForm(false);
      toast({ title: 'Reminder ditambahkan.' });
    } catch (e) {
      toast({ title: 'Gagal.', variant: 'destructive' });
    }
  };

  const markDone = async (id) => {
    try {
      await axios.put(`${API}/api/portal/reminders/${id}`, { is_done: true }, { headers });
      setReminders(prev => prev.filter(r => r.id !== id));
    } catch (e) { console.error(e); }
  };

  const deleteReminder = async (id) => {
    try {
      await axios.delete(`${API}/api/portal/reminders/${id}`, { headers });
      setReminders(prev => prev.filter(r => r.id !== id));
    } catch (e) { toast({ title: 'Gagal.', variant: 'destructive' }); }
  };

  const isPast = (r) => r.remind_at && r.remind_at < new Date().toISOString();

  const RECUR_LABEL = { once: 'Sekali', daily: 'Harian', weekly: 'Mingguan' };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={showDone} onChange={e => setShowDone(e.target.checked)} className="rounded" />
          Tampilkan selesai
        </label>
        <Button data-testid="btn-add-reminder" size="sm" onClick={() => setShowForm(v => !v)}>
          <Plus className="w-4 h-4 mr-1" /> Tambah Reminder
        </Button>
      </div>

      {showForm && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-4 space-y-3">
            <input data-testid="reminder-title-input"
              className="w-full border rounded-lg px-3 py-2 text-sm outline-none"
              placeholder="Judul reminder..." autoFocus
              value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs font-medium mb-1 block">Waktu Pengingat</label>
                <input type="datetime-local" data-testid="reminder-datetime"
                  className="w-full border rounded-lg px-2 py-1.5 text-xs outline-none"
                  value={form.remind_at} onChange={e => setForm(f => ({ ...f, remind_at: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs font-medium mb-1 block">Pengulangan</label>
                <select data-testid="reminder-recurrence"
                  className="w-full border rounded-lg px-2 py-1.5 text-xs outline-none"
                  value={form.recurrence} onChange={e => setForm(f => ({ ...f, recurrence: e.target.value }))}>
                  <option value="once">Sekali</option>
                  <option value="daily">Harian</option>
                  <option value="weekly">Mingguan</option>
                </select>
              </div>
            </div>
            <textarea className="w-full border rounded-lg px-3 py-2 text-xs outline-none resize-none"
              rows={2} placeholder="Deskripsi (opsional)..."
              value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
            <div className="bg-white rounded-lg p-3 border">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={form.whatsapp_enabled}
                  onChange={e => setForm(f => ({ ...f, whatsapp_enabled: e.target.checked }))} />
                <span className="font-medium">Kirim via WhatsApp</span>
                <Badge variant="outline" className="text-xs">Segera Hadir</Badge>
              </label>
              {form.whatsapp_enabled && (
                <input className="mt-2 w-full border rounded px-2 py-1 text-xs outline-none"
                  placeholder="08xx-xxxx-xxxx" value={form.whatsapp_number}
                  onChange={e => setForm(f => ({ ...f, whatsapp_number: e.target.value }))} />
              )}
            </div>
            <div className="flex gap-2">
              <Button data-testid="btn-save-reminder" size="sm" onClick={addReminder}>Simpan</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}><X className="w-4 h-4" /></Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin" /></div> : (
        <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
          {reminders.length === 0 && (
            <div className="text-center py-10 text-muted-foreground">
              <Bell className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Belum ada reminder.</p>
            </div>
          )}
          {reminders.map(r => (
            <div key={r.id} data-testid={`reminder-item-${r.id}`}
              className={`flex items-start gap-3 p-3 rounded-lg border transition-all
                ${r.is_done ? 'opacity-50 bg-muted/30' : isPast(r) ? 'border-amber-300 bg-amber-50' : 'bg-background'}`}>
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0
                ${isPast(r) && !r.is_done ? 'bg-amber-100' : 'bg-primary/10'}`}>
                <Bell className={`w-4 h-4 ${isPast(r) && !r.is_done ? 'text-amber-600' : 'text-primary'}`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{r.title}</p>
                {r.description && <p className="text-xs text-muted-foreground mt-0.5">{r.description}</p>}
                <div className="flex items-center gap-2 mt-1">
                  {r.remind_at && (
                    <span className="text-xs text-muted-foreground">
                      {r.remind_at?.slice(0, 16).replace('T', ' ')}
                    </span>
                  )}
                  {r.recurrence !== 'once' && (
                    <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded flex items-center gap-1">
                      <Repeat className="w-3 h-3" /> {RECUR_LABEL[r.recurrence]}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex gap-1">
                {!r.is_done && (
                  <button onClick={() => markDone(r.id)}
                    className="p-1 rounded hover:bg-green-100 text-muted-foreground hover:text-green-600">
                    <CheckSquare className="w-4 h-4" />
                  </button>
                )}
                <button onClick={() => deleteReminder(r.id)}
                  className="p-1 rounded hover:bg-red-100 text-muted-foreground hover:text-red-600">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <PaginationBar total={total} skip={skip} limit={LIMIT} onPageChange={s => { setSkip(s); setShowDone(showDone); }} className="pt-1" />

      {/* Browser Push Notification opt-in */}
      <div className="pt-4 border-t">
        <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
          <Bell className="w-3.5 h-3.5" /> Notifikasi Push Browser
        </p>
        <PushNotificationToggle headers={headers} />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// PERSONAL CALENDAR
// ═══════════════════════════════════════════════════════════════════
function WorkspaceCalendar({ headers }) {
  const { toast } = useToast();
  const today = new Date();
  const [currentDate, setCurrentDate] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', time: '', description: '', color: '#6366f1' });

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));

  const getMonthBounds = () => {
    const from = new Date(year, month, 1).toISOString().slice(0, 10);
    const to = new Date(year, month + 1, 0).toISOString().slice(0, 10);
    return { from, to };
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { from, to } = getMonthBounds();
      const { data } = await axios.get(`${API}/api/portal/calendar/combined`, {
        headers, params: { from, to }
      });
      setEvents(data.events || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers, year, month]); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  const addEvent = async () => {
    if (!form.title.trim() || !selectedDate) { toast({ title: 'Isi judul event.', variant: 'destructive' }); return; }
    try {
      const { data } = await axios.post(`${API}/api/portal/calendar`, {
        ...form, date: selectedDate,
      }, { headers });
      setEvents(prev => [...prev, data]);
      setShowForm(false);
      setForm({ title: '', time: '', description: '', color: '#6366f1' });
      toast({ title: 'Event ditambahkan.' });
    } catch (e) {
      toast({ title: 'Gagal.', variant: 'destructive' });
    }
  };

  const deleteEvent = async (id) => {
    try {
      await axios.delete(`${API}/api/portal/calendar/${id}`, { headers });
      setEvents(prev => prev.filter(e => e.id !== id));
    } catch (e) { toast({ title: 'Gagal.', variant: 'destructive' }); }
  };

  // Build calendar grid
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const MONTHS = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
  const DAYS = ['Min','Sen','Sel','Rab','Kam','Jum','Sab'];
  const todayStr = today.toISOString().slice(0, 10);

  const getDateStr = (d) => `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

  const getEventsForDay = (d) => {
    const ds = getDateStr(d);
    return events.filter(e => e.date === ds || (e.end_date && e.date <= ds && e.end_date >= ds));
  };

  const selectedEvents = selectedDate ? events.filter(e =>
    e.date === selectedDate || (e.end_date && e.date <= selectedDate && e.end_date >= selectedDate)
  ) : [];

  const EVENT_COLORS = {
    personal: '#6366f1', leave: '#22c55e', overtime: '#8b5cf6', reminder: '#f59e0b',
  };

  return (
    <div className="space-y-3">
      {/* Calendar header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{MONTHS[month]} {year}</h3>
        <div className="flex gap-1">
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={prevMonth}><ChevronLeft className="w-4 h-4" /></Button>
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={nextMonth}><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-3 flex-wrap text-xs">
        {Object.entries({ personal: 'Event', leave: 'Cuti', overtime: 'Lembur', reminder: 'Reminder' }).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: EVENT_COLORS[k] }} />
            {v}
          </span>
        ))}
      </div>

      {/* Grid */}
      <div className="rounded-xl border overflow-hidden">
        <div className="grid grid-cols-7 bg-muted/50">
          {DAYS.map(d => <div key={d} className="py-1.5 text-center text-xs font-semibold text-muted-foreground">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {cells.map((d, i) => {
            if (!d) return <div key={i} className="h-16 bg-muted/20 border-r border-b border-border/40" />;
            const ds = getDateStr(d);
            const dayEvents = getEventsForDay(d);
            const isToday = ds === todayStr;
            const isSelected = ds === selectedDate;
            return (
              <div key={i}
                data-testid={`cal-day-${ds}`}
                onClick={() => { setSelectedDate(ds); setShowForm(false); }}
                className={`h-16 border-r border-b border-border/40 p-1 cursor-pointer transition-colors
                  ${isSelected ? 'bg-primary/10' : isToday ? 'bg-blue-50' : 'hover:bg-muted/40'}`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium mb-0.5
                  ${isToday ? 'bg-primary text-foreground' : ''}`}>
                  {d}
                </div>
                <div className="flex flex-col gap-0.5 overflow-hidden">
                  {dayEvents.slice(0, 2).map((ev, j) => (
                    <div key={j} className="text-xs px-1 rounded truncate"
                      style={{ backgroundColor: (ev.color || EVENT_COLORS[ev.type] || '#6366f1') + '22',
                               color: ev.color || EVENT_COLORS[ev.type] || '#6366f1' }}>
                      {ev.title}
                    </div>
                  ))}
                  {dayEvents.length > 2 && <div className="text-xs text-muted-foreground pl-1">+{dayEvents.length - 2}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected day panel */}
      {selectedDate && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>{selectedDate}</span>
              <Button data-testid="btn-add-event" size="sm" variant="outline" onClick={() => setShowForm(v => !v)}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Tambah Event
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {showForm && (
              <div className="space-y-2 p-3 bg-primary/5 rounded-lg">
                <input data-testid="event-title-input"
                  className="w-full border rounded px-3 py-1.5 text-sm outline-none"
                  placeholder="Judul event..." autoFocus
                  value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
                <div className="flex gap-2">
                  <input type="time" className="border rounded px-2 py-1.5 text-sm outline-none"
                    value={form.time} onChange={e => setForm(f => ({ ...f, time: e.target.value }))} />
                  <input type="color" className="border rounded px-1 py-1 h-9 w-10 cursor-pointer"
                    value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} />
                  <Button data-testid="btn-save-event" size="sm" onClick={addEvent}>Simpan</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}><X className="w-4 h-4" /></Button>
                </div>
              </div>
            )}
            {selectedEvents.length === 0 && !showForm && (
              <p className="text-sm text-muted-foreground text-center py-3">Tidak ada event hari ini.</p>
            )}
            {selectedEvents.map((ev, i) => (
              <div key={i} className="flex items-center gap-2 p-2 rounded-lg border">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: ev.color || EVENT_COLORS[ev.type] || '#6366f1' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{ev.title}</p>
                  {ev.time && <p className="text-xs text-muted-foreground">{ev.time}</p>}
                </div>
                {ev.type === 'personal' && (
                  <button onClick={() => deleteEvent(ev.id)}
                    className="p-1 rounded hover:bg-red-100 text-muted-foreground hover:text-red-600">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
                {ev.type !== 'personal' && (
                  <Badge variant="outline" className="text-xs capitalize">{ev.type}</Badge>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// QUICK LINKS
// ═══════════════════════════════════════════════════════════════════
function WorkspaceQuickLinks({ headers, onNavigate }) {
  const { toast } = useToast();
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ module_id: '', label: '', portal: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/portal/quick-links`, { headers });
      setLinks(data.items || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const addLink = async () => {
    if (!form.module_id) { toast({ title: 'Pilih modul.', variant: 'destructive' }); return; }
    const mod = MODULE_CATALOG.find(m => m.id === form.module_id);
    try {
      const { data } = await axios.post(`${API}/api/portal/quick-links`, {
        module_id: form.module_id,
        label: form.label || mod?.label || form.module_id,
        portal: mod?.portal || '',
      }, { headers });
      setLinks(prev => [...prev, data]);
      setShowAdd(false);
      setForm({ module_id: '', label: '', portal: '' });
    } catch (e) {
      toast({ title: 'Gagal menambah quick link.', variant: 'destructive' });
    }
  };

  const removeLink = async (id) => {
    try {
      await axios.delete(`${API}/api/portal/quick-links/${id}`, { headers });
      setLinks(prev => prev.filter(l => l.id !== id));
    } catch (e) { toast({ title: 'Gagal.', variant: 'destructive' }); }
  };

  const onDragEnd = async (result) => {
    if (!result.destination) return;
    const from = result.source.index;
    const to = result.destination.index;
    if (from === to) return;

    // Optimistic UI update
    const reordered = Array.from(links);
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    setLinks(reordered);

    // Persist new order to backend
    setSaving(true);
    try {
      const items = reordered.map((l, i) => ({ id: l.id, order_seq: i }));
      await axios.put(`${API}/api/portal/quick-links/reorder`, items, { headers });
    } catch (e) {
      toast({ title: 'Gagal menyimpan urutan.', variant: 'destructive' });
      load(); // revert
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-sm text-muted-foreground">Pin shortcut modul favorit Anda.</p>
          {links.length > 1 && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <GripVertical className="w-3 h-3" /> Seret untuk mengubah urutan
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {saving && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
          <Button data-testid="btn-add-quicklink" size="sm" onClick={() => setShowAdd(v => !v)}>
            <Plus className="w-4 h-4 mr-1" /> Tambah Pin
          </Button>
        </div>
      </div>

      {showAdd && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="pt-4 space-y-3">
            <div>
              <label className="text-xs font-medium mb-1 block">Pilih Modul</label>
              <select data-testid="quicklink-module-select"
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none"
                value={form.module_id}
                onChange={e => {
                  const mod = MODULE_CATALOG.find(m => m.id === e.target.value);
                  setForm(f => ({ ...f, module_id: e.target.value, label: mod?.label || '' }));
                }}>
                <option value="">-- Pilih --</option>
                {MODULE_CATALOG.map(m => (
                  <option key={m.id} value={m.id}>{m.label} ({m.portal})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Label (opsional)</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm outline-none"
                placeholder="Nama tampilan..."
                value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
            </div>
            <div className="flex gap-2">
              <Button data-testid="btn-save-quicklink" size="sm" onClick={addLink}>Tambah</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}><X className="w-4 h-4" /></Button>
            </div>
          </CardContent>
        </Card>
      )}

      {links.length === 0 && (
        <div className="text-center py-10 text-muted-foreground">
          <LinkIcon className="w-10 h-10 mx-auto mb-2 opacity-30" />
          <p className="text-sm">Belum ada quick link. Tambah shortcut modul favorit!</p>
        </div>
      )}

      <DragDropContext onDragEnd={onDragEnd}>
        <Droppable droppableId="quick-links" direction="horizontal">
          {(provided, snapshot) => (
            <div
              ref={provided.innerRef}
              {...provided.droppableProps}
              className={`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 ${snapshot.isDraggingOver ? 'bg-primary/5 rounded-xl p-2 transition-colors' : ''}`}
            >
              {links.map((l, index) => (
                <Draggable key={l.id} draggableId={l.id} index={index}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.draggableProps}
                      data-testid={`quicklink-${l.id}`}
                      className={`group relative rounded-xl border bg-background p-4 hover:shadow-md hover:border-primary/30 transition-all
                        ${snapshot.isDragging ? 'shadow-lg border-primary/40 rotate-1 scale-105 z-50' : 'cursor-pointer'}`}
                      onClick={() => !snapshot.isDragging && onNavigate && onNavigate(l.module_id)}
                    >
                      {/* Drag handle */}
                      <div
                        {...provided.dragHandleProps}
                        className="absolute top-2 left-2 p-1 rounded opacity-0 group-hover:opacity-60 hover:opacity-100 text-muted-foreground cursor-grab active:cursor-grabbing transition-opacity"
                        onClick={e => e.stopPropagation()}
                        title="Seret untuk mengubah urutan"
                      >
                        <GripVertical className="w-3.5 h-3.5" />
                      </div>

                      <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center mb-3">
                        <LayoutGrid className="w-5 h-5 text-primary" />
                      </div>
                      <p className="text-sm font-medium leading-tight">{l.label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 capitalize">{l.portal}</p>

                      {/* Remove button */}
                      <button
                        onClick={e => { e.stopPropagation(); removeLink(l.id); }}
                        className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 text-muted-foreground hover:text-red-600 transition-opacity">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </Draggable>
              ))}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MAIN WORKSPACE HUB
// ═══════════════════════════════════════════════════════════════════
export default function WorkspaceHub({ user, headers, onNavigate }) {
  const [wsTab, setWsTab] = useState('notepad');

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center">
          <Star className="w-5 h-5 text-foreground" />
        </div>
        <div>
          <h2 className="text-lg font-bold">Ruang Kerja Saya</h2>
          <p className="text-xs text-muted-foreground">Catatan, tugas, pengingat, kalender & tautan cepat — pribadi</p>
        </div>
      </div>

      <Tabs value={wsTab} onValueChange={setWsTab}>
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="notepad" data-testid="ws-tab-notepad" className="flex items-center gap-1.5">
            <StickyNote className="w-4 h-4" /> Notepad
          </TabsTrigger>
          <TabsTrigger value="todo" data-testid="ws-tab-todo" className="flex items-center gap-1.5">
            <CheckSquare className="w-4 h-4" /> Todo
          </TabsTrigger>
          <TabsTrigger value="reminder" data-testid="ws-tab-reminder" className="flex items-center gap-1.5">
            <Bell className="w-4 h-4" /> Reminder
          </TabsTrigger>
          <TabsTrigger value="calendar" data-testid="ws-tab-calendar" className="flex items-center gap-1.5">
            <Calendar className="w-4 h-4" /> Kalender
          </TabsTrigger>
          <TabsTrigger value="quicklinks" data-testid="ws-tab-quicklinks" className="flex items-center gap-1.5">
            <LinkIcon className="w-4 h-4" /> Quick Links
          </TabsTrigger>
        </TabsList>

        <TabsContent value="notepad" className="mt-4">
          <WorkspaceNotepad headers={headers} />
        </TabsContent>
        <TabsContent value="todo" className="mt-4">
          <WorkspaceTodo headers={headers} />
        </TabsContent>
        <TabsContent value="reminder" className="mt-4">
          <WorkspaceReminder headers={headers} />
        </TabsContent>
        <TabsContent value="calendar" className="mt-4">
          <WorkspaceCalendar headers={headers} />
        </TabsContent>
        <TabsContent value="quicklinks" className="mt-4">
          <WorkspaceQuickLinks headers={headers} onNavigate={onNavigate} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
