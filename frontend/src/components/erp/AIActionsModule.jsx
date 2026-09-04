import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  CheckSquare, Plus, Edit2, Trash2, RefreshCw, Search, Clock, AlertTriangle,
  CheckCircle2, X, Save, Loader2, Calendar, User, Sparkles, Target,
  Brain, AlertCircle, Flame, Gauge,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CFG = {
  open:        { label: 'Terbuka',    color: 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-300',       icon: AlertCircle },
  in_progress: { label: 'Dikerjakan', color: 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-300',     icon: Clock },
  done:        { label: 'Selesai',    color: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300', icon: CheckCircle2 },
  dismissed:   { label: 'Diabaikan',  color: 'bg-muted dark:bg-slate-500/20 text-foreground/70',     icon: X },
};

const PRIORITY_CFG = {
  low:      { label: 'Rendah',  color: 'text-muted-foreground',  icon: Gauge },
  medium:   { label: 'Sedang',  color: 'text-blue-600 dark:text-blue-400',   icon: Target },
  high:     { label: 'Tinggi',  color: 'text-amber-700 dark:text-amber-400',  icon: AlertTriangle },
  critical: { label: 'Kritis',  color: 'text-red-700 dark:text-red-400',    icon: Flame },
};

const SOURCE_CFG = {
  'daily-summary':    { label: 'Ringkasan Harian',    color: 'bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-300' },
  'root-cause':       { label: 'Root Cause',          color: 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-300' },
  'predictive-delay': { label: 'Prediksi Delay',      color: 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300' },
  'chat':             { label: 'AI Chat',             color: 'bg-teal-100 dark:bg-teal-500/10 text-teal-600 dark:text-teal-300' },
  'manual':           { label: 'Manual',              color: 'bg-muted dark:bg-slate-500/10 text-foreground/70' },
};

export default function AIActionsModule({ token }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);
  const [items, setItems] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [stats, setStats] = useState({});
  const [tab, setTab] = useState('open');
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [editDialog, setEditDialog] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const statusParam = tab === 'all' ? '' : `status=${tab}`;
      const srcParam = sourceFilter ? `&source=${sourceFilter}` : '';
      const [r1, r2, r3] = await Promise.all([
        fetch(`${API}/api/dewi/ai-actions?${statusParam}${srcParam}`, { headers }),
        // FASE 20 — dulu '/api/rahaza/master/employees' (tidak pernah ada di backend
        // ⇒ 404 senyap). Endpoint yang benar mengembalikan {total, items:[...]},
        // jadi `items` WAJIB ikut dibaca — kalau tidak, dropdown karyawan tetap
        // kosong walau HTTP-nya 200.
        fetch(`${API}/api/rahaza/employees?active_only=true&limit=500`, { headers }),
        fetch(`${API}/api/dewi/ai-actions/stats`, { headers }),
      ]);
      const d1 = await r1.json();
      const d2 = await r2.json();
      const d3 = await r3.json();
      setItems(d1.actions || []);
      setEmployees(Array.isArray(d2) ? d2 : d2.items || d2.rows || d2.employees || []);
      setStats(d3 || {});
    } catch (e) {
      toast.error('Gagal memuat: ' + (e.message || e));
    } finally { setLoading(false); }
  }, [headers, tab, sourceFilter]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form) => {
    const isEdit = !!form.action_id;
    const url = isEdit
      ? `${API}/api/dewi/ai-actions/${form.action_id}`
      : `${API}/api/dewi/ai-actions`;
    const r = await fetch(url, { method: isEdit ? 'PUT' : 'POST', headers, body: JSON.stringify(form) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast.error(d.detail || 'Gagal simpan'); return; }
    toast.success(isEdit ? 'Task diupdate' : 'Task dibuat');
    setEditDialog(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus action item ini?')) return;
    const r = await fetch(`${API}/api/dewi/ai-actions/${id}`, { method: 'DELETE', headers });
    if (!r.ok) { toast.error('Gagal hapus'); return; }
    toast.success('Task dihapus');
    load();
  };

  const handleStatusChange = async (action, newStatus) => {
    const r = await fetch(`${API}/api/dewi/ai-actions/${action.action_id}`, {
      method: 'PUT', headers, body: JSON.stringify({ status: newStatus }),
    });
    if (!r.ok) { toast.error('Gagal update status'); return; }
    toast.success(`Status: ${STATUS_CFG[newStatus]?.label}`);
    load();
  };

  const filtered = items.filter(a =>
    search
      ? a.title.toLowerCase().includes(search.toLowerCase()) ||
        (a.description || '').toLowerCase().includes(search.toLowerCase())
      : true
  );

  const todayISO = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6 p-6" data-testid="ai-actions-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Brain className="w-6 h-6 text-purple-600 dark:text-purple-400" /> AI Action Items
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Rekomendasi AI yang disimpan sebagai task & di-track sampai selesai
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="ai-actions-refresh">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setEditDialog({})} data-testid="ai-actions-add">
            <Plus className="w-4 h-4 mr-1" /> Task Manual
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Terbuka" value={stats.open || 0} icon={AlertCircle} color="text-blue-600 dark:text-blue-400" />
        <StatCard label="Dikerjakan" value={stats.in_progress || 0} icon={Clock} color="text-amber-700 dark:text-amber-400" />
        <StatCard label="Selesai" value={stats.done || 0} icon={CheckCircle2} color="text-emerald-600 dark:text-emerald-400" />
        <StatCard label="Due < 3 Hari" value={stats.due_soon || 0} icon={Calendar} color="text-orange-600 dark:text-orange-400" />
        <StatCard label="Overdue" value={stats.overdue || 0} icon={Flame} color="text-red-700 dark:text-red-400" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Cari task..." className="pl-9 h-9" />
        </div>
        <Select value={sourceFilter || 'all'} onValueChange={v => setSourceFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-44 h-9"><SelectValue placeholder="Semua Sumber" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Sumber</SelectItem>
            {Object.entries(SOURCE_CFG).map(([k, c]) => <SelectItem key={k} value={k}>{c.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-5 w-full max-w-xl">
          <TabsTrigger value="open" className="text-xs">Terbuka</TabsTrigger>
          <TabsTrigger value="in_progress" className="text-xs">Dikerjakan</TabsTrigger>
          <TabsTrigger value="done" className="text-xs">Selesai</TabsTrigger>
          <TabsTrigger value="dismissed" className="text-xs">Diabaikan</TabsTrigger>
          <TabsTrigger value="all" className="text-xs">Semua</TabsTrigger>
        </TabsList>

        <TabsContent value={tab} className="mt-4">
          {loading && (
            <div className="text-center py-10">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>Belum ada task di kategori ini</p>
              <p className="text-xs mt-1">Gunakan tombol "Simpan sebagai Task" di AI Insights untuk menyimpan rekomendasi AI.</p>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filtered.map(a => (
              <ActionCard
                key={a.action_id}
                action={a}
                isOverdue={a.due_date && a.due_date < todayISO && !['done', 'dismissed'].includes(a.status)}
                onEdit={() => setEditDialog(a)}
                onDelete={() => handleDelete(a.action_id)}
                onStatusChange={(s) => handleStatusChange(a, s)}
              />
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {editDialog !== null && (
        <ActionDialog
          initial={editDialog}
          employees={employees}
          onSave={handleSave}
          onClose={() => setEditDialog(null)}
        />
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="rounded-xl border border-foreground/10 bg-foreground/5 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground uppercase tracking-wide">{label}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <div className={`text-2xl font-bold mt-1 ${color}`}>{value}</div>
    </div>
  );
}

function ActionCard({ action, isOverdue, onEdit, onDelete, onStatusChange }) {
  const s = STATUS_CFG[action.status] || STATUS_CFG.open;
  const p = PRIORITY_CFG[action.priority] || PRIORITY_CFG.medium;
  const src = SOURCE_CFG[action.source] || SOURCE_CFG.manual;
  const PriIcon = p.icon;
  const StatIcon = s.icon;

  return (
    <div className={`rounded-xl border p-4 transition-colors hover:bg-foreground/5 ${isOverdue ? 'border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5' : 'border-foreground/10 bg-foreground/5'}`}
      data-testid={`action-card-${action.action_id}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${src.color}`}>{src.label}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1 ${s.color}`}>
              <StatIcon className="w-3 h-3" /> {s.label}
            </span>
            <span className={`text-[10px] flex items-center gap-1 ${p.color}`}>
              <PriIcon className="w-3 h-3" /> {p.label}
            </span>
            {isOverdue && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-300">OVERDUE</span>}
          </div>
          <h3 className="font-semibold text-sm leading-tight">{action.title}</h3>
          {action.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{action.description}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground mb-3 flex-wrap">
        {action.assignee_name && (
          <span className="flex items-center gap-1"><User className="w-3 h-3" /> {action.assignee_name}</span>
        )}
        {action.due_date && (
          <span className={`flex items-center gap-1 ${isOverdue ? 'text-red-700 dark:text-red-400 font-semibold' : ''}`}>
            <Calendar className="w-3 h-3" /> {action.due_date}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-foreground/5 pt-2">
        <div className="flex gap-1">
          {action.status === 'open' && (
            <Button size="sm" variant="ghost" className="h-7 text-xs text-amber-700 dark:text-amber-400"
              onClick={() => onStatusChange('in_progress')}
              data-testid={`action-start-${action.action_id}`}>
              <Clock className="w-3 h-3 mr-1" /> Mulai
            </Button>
          )}
          {(action.status === 'open' || action.status === 'in_progress') && (
            <Button size="sm" variant="ghost" className="h-7 text-xs text-emerald-600 dark:text-emerald-400"
              onClick={() => onStatusChange('done')}
              data-testid={`action-done-${action.action_id}`}>
              <CheckCircle2 className="w-3 h-3 mr-1" /> Selesai
            </Button>
          )}
          {action.status !== 'dismissed' && action.status !== 'done' && (
            <Button size="sm" variant="ghost" className="h-7 text-xs text-muted-foreground"
              onClick={() => onStatusChange('dismissed')}
              data-testid={`action-dismiss-${action.action_id}`}>
              <X className="w-3 h-3 mr-1" /> Abaikan
            </Button>
          )}
        </div>
        <div className="flex gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onEdit}>
            <Edit2 className="w-3 h-3" />
          </Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-700 dark:text-red-400" onClick={onDelete}>
            <Trash2 className="w-3 h-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function ActionDialog({ initial, employees, onSave, onClose }) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    source: 'manual',
    priority: 'medium',
    assignee_id: '',
    due_date: '',
    notes: '',
    ...initial,
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { toast.error('Judul wajib diisi'); return; }
    setSaving(true);
    await onSave(form);
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{form.action_id ? 'Edit Task' : 'Task AI Baru'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label>Judul <span className="text-red-700 dark:text-red-400">*</span></Label>
            <Input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Contoh: Investigasi QC fail rate line A" required data-testid="action-title" />
          </div>

          <div className="space-y-1">
            <Label>Deskripsi / Rekomendasi AI</Label>
            <Textarea value={form.description} rows={4}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Paste rekomendasi AI di sini..." />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Prioritas</Label>
              <Select value={form.priority} onValueChange={v => setForm(f => ({ ...f, priority: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Rendah</SelectItem>
                  <SelectItem value="medium">Sedang</SelectItem>
                  <SelectItem value="high">Tinggi</SelectItem>
                  <SelectItem value="critical">Kritis</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Sumber</Label>
              <Select value={form.source} onValueChange={v => setForm(f => ({ ...f, source: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="daily-summary">Ringkasan Harian</SelectItem>
                  <SelectItem value="root-cause">Root Cause</SelectItem>
                  <SelectItem value="predictive-delay">Prediksi Delay</SelectItem>
                  <SelectItem value="chat">AI Chat</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label>Penanggung Jawab (Assignee)</Label>
            <Select value={form.assignee_id || 'none'} onValueChange={v => {
              const id = v === 'none' ? '' : v;
              const emp = employees.find(e => e.id === id);
              setForm(f => ({ ...f, assignee_id: id, assignee_name: emp?.name || '' }));
            }}>
              <SelectTrigger><SelectValue placeholder="Pilih karyawan..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— Tidak ditugaskan —</SelectItem>
                {employees.slice(0, 100).map(e => (
                  <SelectItem key={e.id} value={e.id}>{`${e.employee_code} — ${e.name}`}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Batas Waktu (opsional)</Label>
            <Input type="date" value={form.due_date}
              onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
          </div>

          {form.action_id && (
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={v => setForm(f => ({ ...f, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="open">Terbuka</SelectItem>
                  <SelectItem value="in_progress">Dikerjakan</SelectItem>
                  <SelectItem value="done">Selesai</SelectItem>
                  <SelectItem value="dismissed">Diabaikan</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1">
            <Label>Catatan</Label>
            <Textarea value={form.notes} rows={2}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              <X className="w-4 h-4 mr-1" /> Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="action-save">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
              Simpan
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
