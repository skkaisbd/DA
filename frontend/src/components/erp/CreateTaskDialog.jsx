import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { GlassInput } from '@/components/ui/glass';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, X, Loader2, UserCheck, Zap } from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

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

// Roles yang relevan untuk Marketing portal (untuk filter staff dropdown)
const MARKETING_ROLES = [
  'admin', 'owner', 'superadmin',
  'manager_marketing', 'manager_toko',
  'pic_marketing', 'pic_toko',
  'staff_marketing', 'marketing_kol', 'cs_staff',
];

export function CreateTaskDialog({ open, onOpenChange, onCreated, token, accounts = [] }) {
  const [submitting, setSubmitting] = useState(false);
  const [staffList, setStaffList] = useState([]);
  const [staffLoading, setStaffLoading] = useState(false);
  const [form, setForm] = useState({
    title: '',
    description: '',
    task_type: 'data_entry',
    priority: 'medium',
    assigned_to: '',
    account_id: '',
    due_date: '',
    checklist: [],
    // Actionable task fields
    related_entity: '',  // '' | sales_data | return | review | manual_check
    action_type: '',     // '' | submit_form | approve_reject | review_content | manual_check
    related_entity_id: '',  // optional UUID
  });
  const [newChecklistItem, setNewChecklistItem] = useState('');

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  // Fetch staff list for assignment dropdown
  const fetchStaff = useCallback(async () => {
    setStaffLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('role', MARKETING_ROLES.join(','));
      params.append('status', 'active');
      const res = await fetch(`${API}/api/auth/users?${params.toString()}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setStaffList(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      // silent — fallback to empty list
    } finally {
      setStaffLoading(false);
    }
  }, [headers]);

  useEffect(() => {
    if (open) {
      fetchStaff();
    } else {
      // reset on close
      setForm({
        title: '',
        description: '',
        task_type: 'data_entry',
        priority: 'medium',
        assigned_to: '',
        account_id: '',
        due_date: '',
        checklist: [],
        related_entity: '',
        action_type: '',
        related_entity_id: '',
      });
      setNewChecklistItem('');
    }
  }, [open, fetchStaff]);

  const addChecklist = () => {
    if (!newChecklistItem.trim()) return;
    setForm(f => ({ ...f, checklist: [...f.checklist, { item: newChecklistItem.trim(), completed: false }] }));
    setNewChecklistItem('');
  };

  const removeChecklist = (idx) => {
    setForm(f => ({ ...f, checklist: f.checklist.filter((_, i) => i !== idx) }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) {
      toast.error('Judul task wajib diisi');
      return;
    }

    // Validation: data_entry tasks should have account
    if (form.task_type === 'data_entry' && !form.account_id) {
      toast.error('Task tipe "Input Data" wajib pilih Akun Platform');
      return;
    }

    setSubmitting(true);
    try {
      // Auto-determine action_type from related_entity if not set
      let action_type = form.action_type;
      if (!action_type && form.related_entity) {
        const mapping = {
          'sales_data': 'submit_form',
          'return': 'approve_reject',
          'review': 'review_content',
          'manual_check': 'manual_check',
        };
        action_type = mapping[form.related_entity] || 'manual_check';
      }

      // Build related_form_data for pre-fill
      let related_form_data = null;
      if (form.related_entity === 'sales_data' && form.account_id) {
        related_form_data = {
          account_id: form.account_id,
          date: new Date().toISOString().split('T')[0],
        };
      }

      const payload = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        task_type: form.task_type,
        priority: form.priority,
        assigned_to: form.assigned_to || null,
        account_id: form.account_id || null,
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        checklist: form.checklist,
        recurrence: 'one-time',
        related_entity: form.related_entity || null,
        related_entity_id: form.related_entity_id || null,
        related_form_data,
        action_type: action_type || null,
      };

      const res = await fetch(`${API}/api/marketing/tasks`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal membuat task');
      }

      toast.success('Task berhasil dibuat');
      onOpenChange(false);
      if (onCreated) onCreated();
    } catch (err) {
      toast.error(err.message || 'Gagal membuat task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="create-task-dialog">
        <DialogHeader>
          <DialogTitle>Buat Task Baru</DialogTitle>
          <DialogDescription>
            Isi detail task untuk staff marketing. Task akan masuk ke kolom <b>To Do</b>.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="task-title">Judul Task <span className="text-red-400">*</span></Label>
            <GlassInput
              id="task-title"
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="Contoh: Input Sales Harian Shopee Official"
              data-testid="task-title-input"
              required
            />
          </div>

          <div>
            <Label htmlFor="task-desc">Deskripsi</Label>
            <Textarea
              id="task-desc"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Detail langkah-langkah / catatan..."
              rows={3}
              data-testid="task-desc-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Tipe</Label>
              <Select
                value={form.task_type}
                onValueChange={v => setForm(f => ({ ...f, task_type: v }))}
              >
                <SelectTrigger data-testid="task-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TASK_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Prioritas</Label>
              <Select
                value={form.priority}
                onValueChange={v => setForm(f => ({ ...f, priority: v }))}
              >
                <SelectTrigger data-testid="task-priority-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map(p => (
                    <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>
                <UserCheck className="w-3.5 h-3.5 inline mr-1" />
                Assign Ke Staff
              </Label>
              <Select
                value={form.assigned_to || 'unassigned'}
                onValueChange={v => setForm(f => ({ ...f, assigned_to: v === 'unassigned' ? '' : v }))}
              >
                <SelectTrigger data-testid="task-assigned-select">
                  <SelectValue placeholder={staffLoading ? 'Memuat...' : 'Pilih staff...'} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">— Belum di-assign —</SelectItem>
                  {staffList.length === 0 && !staffLoading && (
                    <SelectItem value="no-staff" disabled>
                      Belum ada staff marketing aktif
                    </SelectItem>
                  )}
                  {staffList.map(staff => (
                    <SelectItem key={staff.id} value={staff.id}>
                      <span className="font-medium">{staff.name || staff.email}</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        ({staff.role})
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="task-due">Due Date</Label>
              <GlassInput
                id="task-due"
                type="datetime-local"
                value={form.due_date}
                onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))}
                data-testid="task-due-input"
              />
            </div>
          </div>

          <div>
            <Label>
              Akun / Toko Marketplace
              {form.task_type === 'data_entry' && <span className="text-red-400 ml-1">*</span>}
            </Label>
            <Select
              value={form.account_id || 'none'}
              onValueChange={v => setForm(f => ({ ...f, account_id: v === 'none' ? '' : v }))}
            >
              <SelectTrigger data-testid="task-account-select">
                <SelectValue placeholder={accounts.length === 0 ? 'Belum ada akun — buat di Manage Accounts' : 'Pilih akun...'} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">— Tidak terkait akun —</SelectItem>
                {accounts.map(acc => (
                  <SelectItem key={acc.id} value={acc.id}>
                    {acc.account_name} ({acc.platform})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.task_type === 'data_entry' && !form.account_id && (
              <p className="text-xs text-amber-500 mt-1">
                Task tipe Input Data wajib pilih akun marketplace
              </p>
            )}
          </div>

          {/* ── ACTIONABLE TASK LINKAGE ── */}
          <div className="rounded-md border border-blue-500/30 bg-blue-500/5 p-3 space-y-3">
            <div>
              <Label className="text-xs flex items-center gap-1">
                <Zap className="w-3 h-3" />
                In-System Action (Opsional)
              </Label>
              <p className="text-[11px] text-muted-foreground mt-0.5 mb-2">
                Pilih jika task perlu eksekusi aksi langsung dari Kanban (bukan sekadar reminder).
              </p>
              <Select
                value={form.related_entity || 'none'}
                onValueChange={v => setForm(f => ({ ...f, related_entity: v === 'none' ? '' : v }))}
              >
                <SelectTrigger data-testid="task-action-entity-select">
                  <SelectValue placeholder="Pilih tipe action..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">— Tanpa action (reminder only) —</SelectItem>
                  <SelectItem value="sales_data">📊 Submit Sales Data</SelectItem>
                  <SelectItem value="return">📦 Approve / Reject Return</SelectItem>
                  <SelectItem value="review">⭐ Reply Review</SelectItem>
                  <SelectItem value="manual_check">✅ Manual Check</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Show related_entity_id input if action needs existing entity */}
            {(form.related_entity === 'return' || form.related_entity === 'review') && (
              <div>
                <Label className="text-xs">
                  ID {form.related_entity === 'return' ? 'Return' : 'Review'} *
                </Label>
                <GlassInput
                  value={form.related_entity_id}
                  onChange={e => setForm(f => ({ ...f, related_entity_id: e.target.value }))}
                  placeholder={`UUID ${form.related_entity} yang akan di-action`}
                  data-testid="task-entity-id-input"
                />
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Copy ID dari modul {form.related_entity === 'return' ? 'Returns & Refunds' : 'Rating & Review'}.
                </p>
              </div>
            )}

            {form.related_entity === 'sales_data' && form.account_id && (
              <p className="text-[11px] text-emerald-400">
                ✓ Akun terpilih akan jadi pre-fill untuk form sales data. Staff cukup isi revenue/orders di Kanban.
              </p>
            )}
          </div>

          <div>
            <Label>Checklist</Label>
            <div className="flex gap-2 mb-2">
              <GlassInput
                value={newChecklistItem}
                onChange={e => setNewChecklistItem(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addChecklist(); } }}
                placeholder="Tambah item checklist..."
                data-testid="checklist-input"
              />
              <Button type="button" onClick={addChecklist} size="sm" variant="outline" data-testid="checklist-add-btn">
                <Plus className="w-4 h-4" />
              </Button>
            </div>
            {form.checklist.length > 0 && (
              <ul className="space-y-1 max-h-32 overflow-auto">
                {form.checklist.map((c, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                    <span className="text-sm flex-1 truncate">{c.item}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={() => removeChecklist(i)}
                      data-testid={`checklist-remove-${i}`}
                    >
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
            <Button type="submit" disabled={submitting} data-testid="task-submit-btn">
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Buat Task
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
