import { useState, useEffect, useCallback, useMemo } from 'react';
import { ClipboardCheck, RefreshCw, CheckCircle, XCircle, Loader2, AlertCircle, Clock } from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { PageHeader } from './moduleAtoms';
import { TaskDetailDrawer } from './TaskDetailDrawer';
import { toast } from 'sonner';

const priorityColors = {
  high: 'bg-red-500/10 text-red-400 border-red-500/30',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
  low: 'bg-green-500/10 text-green-400 border-green-500/30',
};

function RejectDialog({ open, onOpenChange, onConfirm }) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) setReason('');
  }, [open]);

  const handleConfirm = async () => {
    if (!reason.trim()) {
      toast.error('Alasan reject wajib diisi');
      return;
    }
    setSubmitting(true);
    await onConfirm(reason.trim());
    setSubmitting(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="reject-dialog">
        <DialogHeader>
          <DialogTitle>Reject Task</DialogTitle>
          <DialogDescription>
            Berikan alasan penolakan. Task akan dikembalikan ke status <b>In Progress</b> dengan catatan ini.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="reject-reason">Alasan</Label>
          <Textarea
            id="reject-reason"
            value={reason}
            onChange={e => setReason(e.target.value)}
            rows={3}
            placeholder="Contoh: Data revenue tidak sesuai dengan yang ada di Shopee Seller Center."
            data-testid="reject-reason-input"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Batal</Button>
          <Button
            onClick={handleConfirm}
            disabled={submitting}
            className="bg-red-500 hover:bg-red-600"
            data-testid="confirm-reject-btn"
          >
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Reject Task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ApprovalInboxModule({ token }) {
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [actioning, setActioning] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [detailTaskId, setDetailTaskId] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/marketing/tasks?status=pending_approval', { headers });
      if (res.ok) {
        const data = await res.json();
        // API returns paginated {tasks: [], pagination: {}} — extract the array
        setTasks(data?.tasks || (Array.isArray(data) ? data : []));
      }
    } catch (e) {
      toast.error('Gagal memuat task pending approval');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchPending();
  }, [fetchPending]);

  const handleApprove = async (task) => {
    setActioning(task.id);
    try {
      const res = await fetch(`/api/marketing/tasks/${task.id}/approve`, {
        method: 'POST',
        headers,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal approve');
      }
      toast.success(`Task "${task.title}" approved`);
      fetchPending();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setActioning(null);
    }
  };

  const handleReject = async (reason) => {
    if (!rejectTarget) return;
    try {
      const res = await fetch(`/api/marketing/tasks/${rejectTarget.id}/reject?reason=${encodeURIComponent(reason)}`, {
        method: 'POST',
        headers,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gagal reject');
      }
      toast.success(`Task "${rejectTarget.title}" rejected`);
      setRejectTarget(null);
      fetchPending();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-';

  return (
    <div className="space-y-5" data-testid="approval-inbox-module">
      <PageHeader
        icon={ClipboardCheck}
        eyebrow="Portal Marketing · Approvals"
        title="Approval Inbox"
        subtitle="Review task yang sudah disubmit oleh staff marketing"
        actions={
          <Button onClick={fetchPending} variant="outline" size="sm" data-testid="refresh-approvals-btn">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
          </Button>
        }
      />

      <GlassPanel className="p-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex items-center justify-center">
            <Clock className="w-5 h-5 text-yellow-400" />
          </div>
          <div>
            <div className="text-2xl font-bold tabular-nums" data-testid="pending-count">{tasks.length}</div>
            <div className="text-xs text-muted-foreground uppercase tracking-wider">Pending Approval</div>
          </div>
        </div>
      </GlassPanel>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : tasks.length === 0 ? (
        <GlassCard className="p-12 text-center">
          <CheckCircle className="w-16 h-16 mx-auto mb-4 text-emerald-400 opacity-50" />
          <p className="text-muted-foreground">Tidak ada task yang menunggu approval. 🎉</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {tasks.map(task => {
            const isOverdue = task.due_date && new Date(task.due_date) < new Date();
            return (
              <GlassCard
                key={task.id}
                className={`p-4 ${isOverdue ? 'border-red-500/30' : ''}`}
                data-testid={`approval-row-${task.task_code}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-muted-foreground">{task.task_code}</span>
                      <Badge variant="outline" className={priorityColors[task.priority]}>{task.priority}</Badge>
                      {isOverdue && (
                        <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/30">
                          <AlertCircle className="w-3 h-3 mr-1" /> Overdue
                        </Badge>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setDetailTaskId(task.id)}
                      className="text-left text-base font-semibold text-foreground hover:text-primary transition-colors mb-1 line-clamp-2 cursor-pointer w-full"
                      data-testid={`approval-title-${task.task_code}`}
                    >
                      {task.title}
                    </button>
                    {task.description && (
                      <p className="text-sm text-muted-foreground line-clamp-2 mb-2">{task.description}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                      {task.due_date && <span>Due: {fmtDate(task.due_date)}</span>}
                      {task.assigned_to && <span>Assigned: {task.assigned_to.slice(0, 10)}…</span>}
                      {task.checklist?.length > 0 && (
                        <span>
                          Checklist: {task.checklist.filter(c => c.completed).length}/{task.checklist.length}
                        </span>
                      )}
                    </div>
                    {task.completion_notes && (
                      <div className="mt-2 px-3 py-2 rounded-md bg-[var(--glass-bg)] border border-[var(--glass-border)] text-xs">
                        <span className="text-muted-foreground">Catatan: </span>
                        <span>{task.completion_notes}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-2 shrink-0">
                    <Button
                      size="sm"
                      onClick={() => handleApprove(task)}
                      disabled={actioning === task.id}
                      className="bg-emerald-500 hover:bg-emerald-600"
                      data-testid={`approve-btn-${task.task_code}`}
                    >
                      {actioning === task.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <><CheckCircle className="w-3.5 h-3.5 mr-1" /> Approve</>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setRejectTarget(task)}
                      disabled={actioning === task.id}
                      className="text-red-400 hover:bg-red-500/10"
                      data-testid={`reject-btn-${task.task_code}`}
                    >
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Reject
                    </Button>
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      <RejectDialog
        open={!!rejectTarget}
        onOpenChange={(o) => !o && setRejectTarget(null)}
        onConfirm={handleReject}
      />

      <TaskDetailDrawer
        taskId={detailTaskId}
        open={!!detailTaskId}
        onOpenChange={(o) => !o && setDetailTaskId(null)}
        onUpdated={fetchPending}
        token={token}
      />
    </div>
  );
}
