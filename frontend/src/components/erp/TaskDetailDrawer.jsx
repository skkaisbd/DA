import { useState, useEffect, useMemo } from 'react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { GlassInput } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Save, Trash2, CheckCircle, AlertCircle, Send, Zap, Link2 } from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const PRIORITIES = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const STATUSES = [
  { value: 'to_do', label: 'To Do' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'pending_approval', label: 'Pending Approval' },
  { value: 'done', label: 'Done' },
  { value: 'cancelled', label: 'Cancelled' },
];

export function TaskDetailDrawer({ taskId, open, onOpenChange, onUpdated, token }) {
  const [task, setTask] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);
  const [actionData, setActionData] = useState({});
  const [actionExecuting, setActionExecuting] = useState(false);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  useEffect(() => {
    if (open && taskId) {
      fetchTask();
    } else {
      setTask(null);
      setForm(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, taskId]);

  const fetchTask = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/tasks/${taskId}`, { headers });
      if (!res.ok) throw new Error('Task tidak ditemukan');
      const data = await res.json();
      setTask(data);
      // Pre-fill actionData from related_form_data if exists
      setActionData(data.related_form_data || {});
      setForm({
        title: data.title || '',
        description: data.description || '',
        priority: data.priority || 'medium',
        status: data.status || 'to_do',
        due_date: data.due_date ? new Date(data.due_date).toISOString().slice(0, 16) : '',
        completion_notes: data.completion_notes || '',
        checklist: data.checklist || [],
      });
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ── Execute task action ──
  const handleExecuteAction = async () => {
    if (!task) return;
    const actionType = task.action_type;
    const related = task.related_entity;

    // Validation per action_type
    if (actionType === 'submit_form' && related === 'sales_data') {
      if (!actionData.revenue && actionData.revenue !== 0) {
        toast.error('Revenue wajib diisi'); return;
      }
    }
    if (actionType === 'approve_reject' && !actionData.decision) {
      toast.error('Pilih Approve atau Reject dulu'); return;
    }
    if (actionType === 'review_content' && !actionData.response_text) {
      toast.error('Tulis balasan dulu'); return;
    }

    setActionExecuting(true);
    try {
      const res = await fetch(`${API}/api/marketing/tasks/${taskId}/complete-action`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          action_data: actionData,
          completion_notes: form?.completion_notes || '',
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Action gagal');
      toast.success(data.message || 'Action berhasil dieksekusi');
      if (onUpdated) onUpdated();
      fetchTask();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setActionExecuting(false);
    }
  };

  const toggleChecklist = (idx) => {
    setForm(f => ({
      ...f,
      checklist: f.checklist.map((c, i) => i === idx ? { ...c, completed: !c.completed } : c),
    }));
  };

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        priority: form.priority,
        status: form.status,
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        completion_notes: form.completion_notes,
        checklist: form.checklist,
      };
      const res = await fetch(`${API}/api/marketing/tasks/${taskId}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Gagal menyimpan');
      toast.success('Task berhasil disimpan');
      if (onUpdated) onUpdated();
      fetchTask();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitForApproval = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/tasks/${taskId}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ status: 'pending_approval' }),
      });
      if (!res.ok) throw new Error('Gagal submit untuk approval');
      toast.success('Task dikirim untuk approval');
      if (onUpdated) onUpdated();
      fetchTask();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Yakin batalkan task ini?')) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/tasks/${taskId}`, {
        method: 'DELETE',
        headers,
      });
      if (!res.ok) throw new Error('Gagal menghapus');
      toast.success('Task dibatalkan');
      if (onUpdated) onUpdated();
      onOpenChange(false);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto" data-testid="task-detail-drawer">
        <SheetHeader>
          <SheetTitle>Detail Task</SheetTitle>
          <SheetDescription>
            {task?.task_code && <span className="font-mono text-xs">{task.task_code}</span>}
          </SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : !form ? (
          <div className="text-center py-12 text-muted-foreground">Task tidak tersedia</div>
        ) : (
          <div className="space-y-4 mt-4">
            {/* Status badges */}
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline">{form.status}</Badge>
              {task?.approval_status && (
                <Badge variant="outline" className={
                  task.approval_status === 'approved' ? 'bg-emerald-500/10 text-emerald-400' :
                  task.approval_status === 'rejected' ? 'bg-red-500/10 text-red-400' :
                  'bg-yellow-500/10 text-yellow-400'
                }>
                  Approval: {task.approval_status}
                </Badge>
              )}
              {task?.action_type && task?.related_entity && (
                <Badge variant="outline" className="bg-blue-500/10 text-blue-400">
                  <Link2 className="w-3 h-3 mr-1" />
                  {task.related_entity} • {task.action_type}
                </Badge>
              )}
            </div>

            {/* ── ACTIONABLE TASK SECTION ── */}
            {task?.action_type && task.status !== 'done' && task.status !== 'cancelled' && (
              <div className="rounded-lg border-2 border-blue-500/30 bg-blue-500/5 p-4 space-y-3" data-testid="task-action-panel">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-blue-500" />
                  <h3 className="font-semibold text-sm">In-System Action</h3>
                </div>

                {/* Submit Sales Data Form */}
                {task.action_type === 'submit_form' && task.related_entity === 'sales_data' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">
                      Isi data penjualan untuk akun terkait. Submit akan auto-save & trigger health score update.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Revenue (Rp) *</Label>
                        <GlassInput
                          type="number"
                          min={0}
                          value={actionData.revenue ?? ''}
                          onChange={e => setActionData(d => ({ ...d, revenue: parseFloat(e.target.value) || 0 }))}
                          placeholder="0"
                          data-testid="action-revenue-input"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Orders</Label>
                        <GlassInput
                          type="number"
                          min={0}
                          value={actionData.orders ?? ''}
                          onChange={e => setActionData(d => ({ ...d, orders: parseInt(e.target.value) || 0 }))}
                          placeholder="0"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Visitors</Label>
                        <GlassInput
                          type="number"
                          min={0}
                          value={actionData.visitors ?? ''}
                          onChange={e => setActionData(d => ({ ...d, visitors: parseInt(e.target.value) || 0 }))}
                          placeholder="0"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Tanggal</Label>
                        <GlassInput
                          type="date"
                          value={actionData.date || ''}
                          onChange={e => setActionData(d => ({ ...d, date: e.target.value }))}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Approve/Reject (Return, Refund) */}
                {task.action_type === 'approve_reject' && task.related_entity === 'return' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">
                      Putuskan apakah return request ini disetujui atau ditolak.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant={actionData.decision === 'approve' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setActionData(d => ({ ...d, decision: 'approve' }))}
                        className={actionData.decision === 'approve' ? 'bg-emerald-600 hover:bg-emerald-700' : ''}
                        data-testid="action-approve-btn"
                      >
                        <CheckCircle className="w-4 h-4 mr-1" /> Approve
                      </Button>
                      <Button
                        type="button"
                        variant={actionData.decision === 'reject' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setActionData(d => ({ ...d, decision: 'reject' }))}
                        className={actionData.decision === 'reject' ? 'bg-red-600 hover:bg-red-700' : ''}
                        data-testid="action-reject-btn"
                      >
                        <AlertCircle className="w-4 h-4 mr-1" /> Reject
                      </Button>
                    </div>
                    <div>
                      <Label className="text-xs">Alasan (opsional)</Label>
                      <Textarea
                        rows={2}
                        value={actionData.reason || ''}
                        onChange={e => setActionData(d => ({ ...d, reason: e.target.value }))}
                        placeholder="Tulis alasan keputusan..."
                      />
                    </div>
                  </div>
                )}

                {/* Review Reply */}
                {task.action_type === 'review_content' && task.related_entity === 'review' && (
                  <div className="space-y-2">
                    <Label className="text-xs">Balasan Review *</Label>
                    <Textarea
                      rows={3}
                      value={actionData.response_text || ''}
                      onChange={e => setActionData(d => ({ ...d, response_text: e.target.value }))}
                      placeholder="Terima kasih atas review-nya..."
                      data-testid="action-review-reply"
                    />
                  </div>
                )}

                {/* Manual check */}
                {task.action_type === 'manual_check' && (
                  <p className="text-xs text-muted-foreground">
                    Tandai task selesai setelah pengecekan manual selesai.
                  </p>
                )}

                <Button
                  onClick={handleExecuteAction}
                  disabled={actionExecuting}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                  data-testid="action-execute-btn"
                >
                  {actionExecuting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
                  Eksekusi & Tandai Selesai
                </Button>
              </div>
            )}

            {task?.action_executed_at && task.action_result && (
              <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 p-3 text-xs">
                <p className="font-semibold text-emerald-400 mb-1">
                  <CheckCircle className="w-3 h-3 inline mr-1" />
                  Action telah dieksekusi
                </p>
                <p className="text-muted-foreground">{task.action_result.message}</p>
              </div>
            )}

            <div>
              <Label>Judul</Label>
              <GlassInput
                value={form.title}
                onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                data-testid="detail-title-input"
              />
            </div>

            <div>
              <Label>Deskripsi</Label>
              <Textarea
                rows={3}
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                data-testid="detail-desc-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Status</Label>
                <Select value={form.status} onValueChange={v => setForm(f => ({ ...f, status: v }))}>
                  <SelectTrigger data-testid="detail-status-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Prioritas</Label>
                <Select value={form.priority} onValueChange={v => setForm(f => ({ ...f, priority: v }))}>
                  <SelectTrigger data-testid="detail-priority-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label>Due Date</Label>
              <GlassInput
                type="datetime-local"
                value={form.due_date}
                onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))}
                data-testid="detail-due-input"
              />
            </div>

            {form.checklist && form.checklist.length > 0 && (
              <div>
                <Label>Checklist ({form.checklist.filter(c => c.completed).length}/{form.checklist.length})</Label>
                <ul className="space-y-1 mt-1">
                  {form.checklist.map((c, i) => (
                    <li key={i} className="flex items-center gap-2 px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                      <Checkbox
                        checked={c.completed}
                        onCheckedChange={() => toggleChecklist(i)}
                        data-testid={`detail-checklist-${i}`}
                      />
                      <span className={`text-sm flex-1 ${c.completed ? 'line-through text-muted-foreground' : ''}`}>
                        {c.item}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <Label>Completion Notes</Label>
              <Textarea
                rows={2}
                value={form.completion_notes}
                onChange={e => setForm(f => ({ ...f, completion_notes: e.target.value }))}
                placeholder="Catatan saat task selesai..."
                data-testid="detail-notes-input"
              />
            </div>

            <div className="pt-4 border-t border-[var(--glass-border)] space-y-2">
              <div className="flex gap-2">
                <Button onClick={handleSave} disabled={saving} className="flex-1" data-testid="detail-save-btn">
                  {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                  Simpan
                </Button>
                {form.status !== 'pending_approval' && form.status !== 'done' && form.status !== 'cancelled' && (
                  <Button
                    onClick={handleSubmitForApproval}
                    disabled={saving}
                    variant="outline"
                    data-testid="detail-submit-approval-btn"
                  >
                    <Send className="w-4 h-4 mr-2" />
                    Submit Approval
                  </Button>
                )}
              </div>
              <Button
                onClick={handleDelete}
                disabled={saving}
                variant="outline"
                className="w-full text-red-400 hover:bg-red-500/10"
                data-testid="detail-cancel-btn"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Batalkan Task
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
