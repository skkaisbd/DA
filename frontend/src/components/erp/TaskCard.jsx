import { useState } from 'react';
import { Clock, User, CheckCircle, AlertCircle, MoreVertical, ExternalLink, Zap } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { AccountBadge } from './marketing/AccountBadge';
import { toast } from 'sonner';

const priorityColors = {
  high: 'bg-red-500/10 text-red-400 border-red-500/30',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
  low: 'bg-green-500/10 text-green-400 border-green-500/30',
};

const taskTypeLabels = {
  data_entry: 'Input Data',
  review: 'Review',
  analysis: 'Analisis',
  reporting: 'Reporting',
  operational: 'Operasional',
};

export function TaskCard({ task, isDragging, onRefresh, token, accounts = [], onViewDetail }) {
  const [loading, setLoading] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Resolve akun dari ID
  const account = task.account_id ? accounts.find(a => a.id === task.account_id) : null;

  // Apakah task ini action-based (bukan sekadar reminder)
  const isActionable = task.action_type && task.action_type !== 'manual_check';
  const actionExecuted = !!task.action_executed_at;

  const handleApprove = async () => {
    if (!confirm('Approve task ini?')) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/marketing/tasks/${task.id}/approve`, {
        method: 'POST',
        headers
      });
      if (res.ok) {
        toast.success('Task approved');
        if (onRefresh) onRefresh();
      }
    } catch (e) {
      toast.error('Gagal approve task');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    const reason = prompt('Alasan reject:');
    if (!reason) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/marketing/tasks/${task.id}/reject?reason=${encodeURIComponent(reason)}`, {
        method: 'POST',
        headers
      });
      if (res.ok) {
        toast.success('Task rejected');
        if (onRefresh) onRefresh();
      }
    } catch (e) {
      toast.error('Gagal reject task');
    } finally {
      setLoading(false);
    }
  };

  const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== 'done';

  return (
    <GlassCard
      className={`p-3 cursor-grab active:cursor-grabbing transition-all ${
        isDragging ? 'shadow-lg rotate-2 scale-105' : ''
      } ${isOverdue ? 'border-red-500/50' : ''} ${
        isActionable && !actionExecuted ? 'border-blue-500/40' : ''
      }`}
      data-testid={`task-card-${task.task_code}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            <span className="text-xs font-mono text-muted-foreground">{task.task_code}</span>
            {isOverdue && <AlertCircle className="w-3 h-3 text-red-400 shrink-0" />}
            {/* ⚡ Actionable indicator */}
            {isActionable && (
              <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                actionExecuted
                  ? 'bg-emerald-500/10 text-emerald-500'
                  : 'bg-blue-500/15 text-blue-500 border border-blue-500/30'
              }`}>
                <Zap size={9} />
                {actionExecuted ? 'Done' : 'Action'}
              </span>
            )}
          </div>
          <h4 className="text-sm font-semibold text-foreground line-clamp-2">{task.title}</h4>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 shrink-0">
              <MoreVertical className="w-3 h-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onViewDetail?.(task.id)}>
              <ExternalLink className="w-3 h-3 mr-2" />
              Detail
            </DropdownMenuItem>
            {task.status === 'pending_approval' && (
              <>
                <DropdownMenuItem onClick={handleApprove} disabled={loading}>
                  <CheckCircle className="w-3 h-3 mr-2 text-emerald-400" />
                  Approve
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleReject} disabled={loading}>
                  <AlertCircle className="w-3 h-3 mr-2 text-red-400" />
                  Reject
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Description */}
      {task.description && (
        <p className="text-xs text-muted-foreground mb-2 line-clamp-2">{task.description}</p>
      )}

      {/* Account Badge */}
      {account && (
        <div className="mb-2">
          <AccountBadge account={account} size="xs" />
        </div>
      )}

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-1 mb-2">
        <Badge variant="outline" className={priorityColors[task.priority]}>
          {task.priority}
        </Badge>
        <Badge variant="outline" className="text-xs">
          {taskTypeLabels[task.task_type] || task.task_type}
        </Badge>
      </div>

      {/* Checklist Progress */}
      {task.checklist && task.checklist.length > 0 && (
        <div className="mb-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span>Checklist</span>
            <span>
              {task.checklist.filter(c => c.completed).length}/{task.checklist.length}
            </span>
          </div>
          <div className="h-1 bg-[var(--glass-bg)] rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{
                width: `${(task.checklist.filter(c => c.completed).length / task.checklist.length) * 100}%`
              }}
            />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-[var(--glass-border)]">
        <div className="flex items-center gap-1">
          {task.due_date && (
            <div className={`flex items-center gap-1 ${isOverdue ? 'text-red-400' : ''}`}>
              <Clock className="w-3 h-3" />
              {new Date(task.due_date).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })}
            </div>
          )}
        </div>
        {task.assigned_to && (
          <div className="flex items-center gap-1">
            <User className="w-3 h-3" />
            <span className="truncate max-w-[80px]">{task.assigned_to.slice(0, 8)}</span>
          </div>
        )}
      </div>

      {/* Approval Status */}
      {task.approval_status && (
        <div className="mt-2 pt-2 border-t border-[var(--glass-border)]">
          <span className="text-xs text-muted-foreground">
            Status Approval: <span className="font-semibold">{task.approval_status}</span>
          </span>
        </div>
      )}
    </GlassCard>
  );
}
