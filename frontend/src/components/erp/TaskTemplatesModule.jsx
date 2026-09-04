import { useState, useEffect, useCallback } from 'react';
import { FileCog, Plus, RefreshCw, Pencil, Power, PowerOff, Loader2, Clock } from 'lucide-react';
import { GlassCard, GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PageHeader } from './moduleAtoms';
import { toast } from 'sonner';
import { X } from 'lucide-react';

const FREQUENCIES = [
  { value: 'daily', label: 'Setiap Hari' },
  { value: 'weekly', label: 'Mingguan' },
  { value: 'monthly', label: 'Bulanan' },
  { value: 'one-time', label: 'Sekali (One-time)' },
];

const TASK_TYPES = [
  { value: 'data_entry', label: 'Input Data' },
  { value: 'review', label: 'Review' },
  { value: 'analysis', label: 'Analisis' },
  { value: 'reporting', label: 'Reporting' },
  { value: 'operational', label: 'Operasional' },
];

const PRIORITIES = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const DAYS = [
  { value: 'monday', label: 'Sen' },
  { value: 'tuesday', label: 'Sel' },
  { value: 'wednesday', label: 'Rab' },
  { value: 'thursday', label: 'Kam' },
  { value: 'friday', label: 'Jum' },
  { value: 'saturday', label: 'Sab' },
  { value: 'sunday', label: 'Min' },
];

function TemplateFormDialog({ open, onOpenChange, template, onSaved, token }) {
  const isEdit = !!template;
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    template_name: '',
    title: '',
    description: '',
    task_type: 'data_entry',
    priority: 'medium',
    recurrence: 'daily',
    time: '09:00',
    days_of_week: [],
    day_of_month: 1,
    auto_create: true,
    default_assigned_role: 'staff',
    is_active: true,
    checklist_template: [],
  });
  const [newChecklistItem, setNewChecklistItem] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  useEffect(() => {
    if (open && template) {
      const cfg = template.recurrence_config || {};
      setForm({
        template_name: template.template_name || '',
        title: template.title || '',
        description: template.description || '',
        task_type: template.task_type || 'data_entry',
        priority: template.priority || 'medium',
        recurrence: template.recurrence || 'daily',
        time: cfg.time || '09:00',
        days_of_week: cfg.days_of_week || [],
        day_of_month: cfg.day_of_month || 1,
        auto_create: cfg.auto_create !== false,
        default_assigned_role: template.default_assigned_role || 'staff',
        is_active: template.is_active !== false,
        checklist_template: template.checklist_template || [],
      });
    } else if (open && !template) {
      setForm({
        template_name: '',
        title: '',
        description: '',
        task_type: 'data_entry',
        priority: 'medium',
        recurrence: 'daily',
        time: '09:00',
        days_of_week: [],
        day_of_month: 1,
        auto_create: true,
        default_assigned_role: 'staff',
        is_active: true,
        checklist_template: [],
      });
      setNewChecklistItem('');
    }
  }, [open, template]);

  const toggleDay = (day) => {
    setForm(f => ({
      ...f,
      days_of_week: f.days_of_week.includes(day)
        ? f.days_of_week.filter(d => d !== day)
        : [...f.days_of_week, day],
    }));
  };

  const addChecklist = () => {
    if (!newChecklistItem.trim()) return;
    setForm(f => ({ ...f, checklist_template: [...f.checklist_template, newChecklistItem.trim()] }));
    setNewChecklistItem('');
  };

  const removeChecklist = (idx) => {
    setForm(f => ({ ...f, checklist_template: f.checklist_template.filter((_, i) => i !== idx) }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.template_name.trim()) {
      toast.error('Nama template wajib diisi');
      return;
    }
    if (!form.title.trim()) {
      toast.error('Judul task wajib diisi');
      return;
    }

    setSubmitting(true);
    try {
      const recurrence_config = {
        frequency: form.recurrence,
        time: form.time,
        auto_create: form.auto_create,
      };
      if (form.recurrence === 'weekly') {
        recurrence_config.days_of_week = form.days_of_week;
      } else if (form.recurrence === 'monthly') {
        recurrence_config.day_of_month = parseInt(form.day_of_month, 10);
      }

      const payload = {
        template_name: form.template_name.trim(),
        title: form.title.trim(),
        description: form.description.trim() || null,
        task_type: form.task_type,
        priority: form.priority,
        recurrence: form.recurrence,
        recurrence_config,
        default_assigned_role: form.default_assigned_role,
        is_active: form.is_active,
        checklist_template: form.checklist_template,
      };

      const url = isEdit
        ? `/api/marketing/task-templates/${template.id}`
        : '/api/marketing/task-templates';
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, { method, headers, body: JSON.stringify(payload) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal menyimpan template');
      }

      toast.success(isEdit ? 'Template berhasil diupdate' : 'Template berhasil dibuat');
      onOpenChange(false);
      if (onSaved) onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto" data-testid="template-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Template Task' : 'Buat Template Task'}</DialogTitle>
          <DialogDescription>
            Template untuk membuat task otomatis berulang sesuai jadwal.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="tpl-name">Nama Template <span className="text-red-400">*</span></Label>
            <GlassInput
              id="tpl-name"
              value={form.template_name}
              onChange={e => setForm(f => ({ ...f, template_name: e.target.value }))}
              placeholder="Input Sales Harian Shopee"
              data-testid="tpl-name-input"
              required
            />
          </div>

          <div>
            <Label htmlFor="tpl-title">Judul Task <span className="text-red-400">*</span></Label>
            <GlassInput
              id="tpl-title"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Input Sales Harian - Shopee Official Store"
              data-testid="tpl-title-input"
              required
            />
          </div>

          <div>
            <Label htmlFor="tpl-desc">Deskripsi</Label>
            <Textarea
              id="tpl-desc"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={2}
              data-testid="tpl-desc-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Tipe</Label>
              <Select value={form.task_type} onValueChange={v => setForm(f => ({ ...f, task_type: v }))}>
                <SelectTrigger data-testid="tpl-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TASK_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Prioritas</Label>
              <Select value={form.priority} onValueChange={v => setForm(f => ({ ...f, priority: v }))}>
                <SelectTrigger data-testid="tpl-priority-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Recurrence</Label>
              <Select value={form.recurrence} onValueChange={v => setForm(f => ({ ...f, recurrence: v }))}>
                <SelectTrigger data-testid="tpl-recurrence-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {FREQUENCIES.map(fr => <SelectItem key={fr.value} value={fr.value}>{fr.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="tpl-time">Waktu</Label>
              <GlassInput
                id="tpl-time"
                type="time"
                value={form.time}
                onChange={e => setForm(f => ({ ...f, time: e.target.value }))}
                data-testid="tpl-time-input"
              />
            </div>
          </div>

          {form.recurrence === 'weekly' && (
            <div>
              <Label>Hari (multi-pilih)</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {DAYS.map(d => (
                  <Button
                    key={d.value}
                    type="button"
                    size="sm"
                    variant={form.days_of_week.includes(d.value) ? 'default' : 'outline'}
                    onClick={() => toggleDay(d.value)}
                    data-testid={`day-toggle-${d.value}`}
                  >
                    {d.label}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {form.recurrence === 'monthly' && (
            <div>
              <Label htmlFor="tpl-day-of-month">Tanggal di Bulan (1-31)</Label>
              <GlassInput
                id="tpl-day-of-month"
                type="number"
                min="1"
                max="31"
                value={form.day_of_month}
                onChange={e => setForm(f => ({ ...f, day_of_month: e.target.value }))}
                data-testid="tpl-day-month-input"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Default Assigned Role</Label>
              <Select value={form.default_assigned_role} onValueChange={v => setForm(f => ({ ...f, default_assigned_role: v }))}>
                <SelectTrigger data-testid="tpl-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="staff">Staff Marketing</SelectItem>
                  <SelectItem value="pic">PIC Marketing</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-3">
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.auto_create}
                  onCheckedChange={(v) => setForm(f => ({ ...f, auto_create: v }))}
                  data-testid="tpl-auto-switch"
                />
                <Label>Auto-create</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.is_active}
                  onCheckedChange={(v) => setForm(f => ({ ...f, is_active: v }))}
                  data-testid="tpl-active-switch"
                />
                <Label>Active</Label>
              </div>
            </div>
          </div>

          <div>
            <Label>Checklist Template</Label>
            <div className="flex gap-2 mb-2">
              <GlassInput
                value={newChecklistItem}
                onChange={e => setNewChecklistItem(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addChecklist(); } }}
                placeholder="Tambah item checklist..."
                data-testid="tpl-checklist-input"
              />
              <Button type="button" onClick={addChecklist} size="sm" variant="outline">
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            {form.checklist_template.length > 0 && (
              <ul className="space-y-1 max-h-32 overflow-auto">
                {form.checklist_template.map((c, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                    <span className="text-sm flex-1 truncate">{c}</span>
                    <Button type="button" variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => removeChecklist(i)}>
                      <X className="w-3 h-3" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              Batal
            </Button>
            <Button type="submit" disabled={submitting} data-testid="tpl-submit-btn">
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {isEdit ? 'Simpan' : 'Buat Template'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function TaskTemplatesModule({ token }) {
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTpl, setEditTpl] = useState(null);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/marketing/task-templates', { headers });
      if (res.ok) {
        setTemplates(await res.json());
      }
    } catch (e) {
      toast.error('Gagal memuat template');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const toggleActive = async (tpl) => {
    try {
      // For deactivate use DELETE; for activate, PUT with is_active=true
      if (tpl.is_active) {
        const res = await fetch(`/api/marketing/task-templates/${tpl.id}`, {
          method: 'DELETE', headers,
        });
        if (!res.ok) throw new Error('Gagal nonaktifkan');
        toast.success('Template dinonaktifkan');
      } else {
        const payload = {
          template_name: tpl.template_name,
          title: tpl.title,
          description: tpl.description,
          task_type: tpl.task_type,
          recurrence: tpl.recurrence,
          recurrence_config: tpl.recurrence_config,
          default_assigned_role: tpl.default_assigned_role,
          priority: tpl.priority,
          checklist_template: tpl.checklist_template || [],
          is_active: true,
        };
        const res = await fetch(`/api/marketing/task-templates/${tpl.id}`, {
          method: 'PUT', headers, body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Gagal aktifkan');
        toast.success('Template diaktifkan');
      }
      fetchTemplates();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const recurrenceLabel = (tpl) => {
    const cfg = tpl.recurrence_config || {};
    if (tpl.recurrence === 'daily') return `Harian @ ${cfg.time || '09:00'}`;
    if (tpl.recurrence === 'weekly') return `Mingguan (${(cfg.days_of_week || []).join(', ') || '-'}) @ ${cfg.time || '09:00'}`;
    if (tpl.recurrence === 'monthly') return `Bulanan tgl ${cfg.day_of_month || 1} @ ${cfg.time || '09:00'}`;
    return 'One-time';
  };

  return (
    <div className="space-y-5" data-testid="task-templates-module">
      <PageHeader
        icon={FileCog}
        eyebrow="Portal Marketing · Templates"
        title="Task Templates"
        subtitle="Konfigurasi template task berulang (daily/weekly/monthly) dengan auto-create scheduler"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={fetchTemplates} variant="outline" size="sm" data-testid="refresh-templates-btn">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button onClick={() => { setEditTpl(null); setDialogOpen(true); }} size="sm" data-testid="create-template-btn">
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Buat Template
            </Button>
          </div>
        }
      />

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : templates.length === 0 ? (
        <GlassCard className="p-12 text-center">
          <FileCog className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <p className="text-muted-foreground mb-4">Belum ada template task</p>
          <Button size="sm" onClick={() => { setEditTpl(null); setDialogOpen(true); }} data-testid="create-first-template-btn">
            <Plus className="w-4 h-4 mr-2" /> Buat Template Pertama
          </Button>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {templates.map(tpl => (
            <GlassCard key={tpl.id} className={`p-4 ${!tpl.is_active ? 'opacity-60' : ''}`} data-testid={`template-row-${tpl.id}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-base font-semibold text-foreground">{tpl.template_name}</h3>
                    <Badge variant="outline" className={tpl.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-muted/10 text-muted-foreground'}>
                      {tpl.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mb-2">{tpl.title}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {recurrenceLabel(tpl)}</span>
                    <span>·</span>
                    <Badge variant="outline" className="text-xs">{tpl.task_type}</Badge>
                    <Badge variant="outline" className="text-xs">{tpl.priority}</Badge>
                    <Badge variant="outline" className="text-xs">{tpl.default_assigned_role}</Badge>
                  </div>
                  {tpl.checklist_template?.length > 0 && (
                    <div className="text-xs text-muted-foreground mt-2">
                      Checklist items: {tpl.checklist_template.length}
                    </div>
                  )}
                </div>

                <div className="flex flex-col gap-2 shrink-0">
                  <Button size="sm" variant="outline" onClick={() => { setEditTpl(tpl); setDialogOpen(true); }} data-testid={`edit-tpl-${tpl.id}`}>
                    <Pencil className="w-3 h-3 mr-1" /> Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => toggleActive(tpl)}
                    className={tpl.is_active ? 'text-orange-400' : 'text-emerald-400'}
                    data-testid={`toggle-tpl-${tpl.id}`}
                  >
                    {tpl.is_active ? (
                      <><PowerOff className="w-3 h-3 mr-1" /> Disable</>
                    ) : (
                      <><Power className="w-3 h-3 mr-1" /> Enable</>
                    )}
                  </Button>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      <TemplateFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        template={editTpl}
        onSaved={fetchTemplates}
        token={token}
      />
    </div>
  );
}
