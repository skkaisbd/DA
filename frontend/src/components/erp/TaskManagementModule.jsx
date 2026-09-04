import { useState, useEffect, useCallback, useMemo } from 'react';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import { CheckSquare, Plus, RefreshCw, Filter, X, Zap, AlertTriangle } from 'lucide-react';
import { GlassPanel, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from '@/components/ui/alert-dialog';
import { PageHeader } from './moduleAtoms';
import PaginationBar from './PaginationBar';
import { TaskCard } from './TaskCard';
import { CreateTaskDialog } from './CreateTaskDialog';
import { TaskDetailDrawer } from './TaskDetailDrawer';
import { toast } from 'sonner';

const COLUMNS = [
  { id: 'to_do', title: 'To Do', color: 'bg-muted/10 border-border/30' },
  { id: 'in_progress', title: 'In Progress', color: 'bg-blue-500/10 border-blue-500/30' },
  { id: 'pending_approval', title: 'Pending Approval', color: 'bg-yellow-500/10 border-yellow-500/30' },
  { id: 'done', title: 'Done', color: 'bg-emerald-500/10 border-emerald-500/30' },
];

export default function TaskManagementModule({ token }) {
  const [loading, setLoading] = useState(true);
  const [taskPage, setTaskPage] = useState(1);
  const [taskPagination, setTaskPagination] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [columns, setColumns] = useState({});
  const [accounts, setAccounts] = useState([]);
  const [filter, setFilter] = useState({ priority: 'all', account_id: 'all' });
  const [showFilters, setShowFilters] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailTaskId, setDetailTaskId] = useState(null);
  // Guard: bypass dialog untuk drag actionable task ke done tanpa eksekusi
  const [bypassConfirm, setBypassConfirm] = useState(null); // { task, newStatus }

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token]
  );

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch('/api/marketing/accounts?status=active', { headers });
      if (res.ok) {
        setAccounts(await res.json());
      }
    } catch (e) {
      // silent fail
    }
  }, [headers]);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter.priority !== 'all') params.append('priority', filter.priority);
      if (filter.account_id !== 'all') params.append('account_id', filter.account_id);
      params.append('page', String(taskPage));
      params.append('limit', '20');

      const res = await fetch(`/api/marketing/tasks?${params.toString()}`, { headers });
      if (res.ok) {
        const data = await res.json();
        // Handle paginated or legacy response
        const taskList = data?.tasks || (Array.isArray(data) ? data : []);
        setTasks(taskList);
        setTaskPagination(data?.pagination || null);
        const grouped = COLUMNS.reduce((acc, col) => {
          acc[col.id] = taskList.filter(t => t.status === col.id);
          return acc;
        }, {});
        setColumns(grouped);
      }
    } catch (e) {
      toast.error('Gagal memuat tasks');
    } finally {
      setLoading(false);
    }
  }, [headers, filter, taskPage]);

  useEffect(() => {
    fetchAccounts();
    fetchTasks();
  }, [fetchAccounts, fetchTasks]);

  const handleDragEnd = async (result) => {
    const { source, destination, draggableId } = result;
    if (!destination) return;
    if (source.droppableId === destination.droppableId && source.index === destination.index) return;

    const newStatus = destination.droppableId;
    const taskId    = draggableId;

    // Cari task object
    const task = tasks.find(t => t.id === taskId);

    // Guard: jika drag ke 'done' dan task adalah actionable + belum dieksekusi → tanya konfirmasi
    if (
      newStatus === 'done' &&
      task?.action_type && task.action_type !== 'manual_check' &&
      !task.action_executed_at
    ) {
      setBypassConfirm({ task, newStatus });
      return; // Batalkan drag, kembalikan ke posisi semula
    }

    await _applyStatusChange(taskId, newStatus, source, destination);
  };

  const _applyStatusChange = async (taskId, newStatus, source, destination) => {
    // Optimistic update
    const newColumns = { ...columns };
    const sourceColId = source?.droppableId || Object.keys(newColumns).find(k => newColumns[k].some(t => t.id === taskId));
    const destColId   = newStatus;

    const sourceCol = [...(newColumns[sourceColId] || [])];
    const destCol   = sourceColId === destColId ? sourceCol : [...(newColumns[destColId] || [])];

    const srcIdx    = source?.index ?? sourceCol.findIndex(t => t.id === taskId);
    const destIdx   = destination?.index ?? destCol.length;

    const [movedTask] = sourceCol.splice(srcIdx, 1);
    movedTask.status = newStatus;
    destCol.splice(destIdx, 0, movedTask);

    if (sourceColId !== destColId) {
      newColumns[sourceColId] = sourceCol;
    }
    newColumns[destColId] = destCol;
    setColumns(newColumns);

    try {
      const res = await fetch(`/api/marketing/tasks/${taskId}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error('Update failed');
      const label =
        newStatus === 'pending_approval' ? 'Task dikirim untuk approval' :
        newStatus === 'done'             ? 'Task selesai ✅' : 'Status task diupdate';
      toast.success(label);
    } catch (e) {
      toast.error('Gagal update task');
      fetchTasks();
    }
  };

  const totalCount = tasks.length;
  const overdueCount = useMemo(
    () =>
      tasks.filter(
        t => t.due_date && new Date(t.due_date) < new Date() && t.status !== 'done' && t.status !== 'cancelled'
      ).length,
    [tasks]
  );

  const resetFilter = () => setFilter({ priority: 'all', account_id: 'all' });
  const hasActiveFilter = filter.priority !== 'all' || filter.account_id !== 'all';

  return (
    <div className="space-y-5" data-testid="task-management-page">
      <PageHeader
        icon={CheckSquare}
        eyebrow="Portal Marketing · Task Management"
        title="Kanban Board"
        subtitle="Kelola task harian, mingguan, bulanan dengan approval workflow"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={fetchTasks} variant="outline" size="sm" data-testid="refresh-tasks-btn">
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button
              onClick={() => setShowFilters(s => !s)}
              variant={showFilters || hasActiveFilter ? 'default' : 'outline'}
              size="sm"
              data-testid="toggle-filters-btn"
            >
              <Filter className="w-3.5 h-3.5 mr-1.5" />
              Filter
              {hasActiveFilter && (
                <Badge variant="outline" className="ml-2 h-4 px-1 text-[10px]">
                  {(filter.priority !== 'all' ? 1 : 0) + (filter.account_id !== 'all' ? 1 : 0)}
                </Badge>
              )}
            </Button>
            <Button onClick={() => setCreateOpen(true)} size="sm" data-testid="create-task-button">
              <Plus className="w-3.5 h-3.5 mr-1.5" /> Buat Task
            </Button>
          </div>
        }
      />

      {/* Stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <GlassPanel className="p-3">
          <div className="text-xs text-muted-foreground uppercase tracking-wider">Total</div>
          <div className="text-xl font-bold tabular-nums">{totalCount}</div>
        </GlassPanel>
        {COLUMNS.map(col => (
          <GlassPanel key={col.id} className="p-3">
            <div className="text-xs text-muted-foreground uppercase tracking-wider truncate">{col.title}</div>
            <div className="text-xl font-bold tabular-nums">{columns[col.id]?.length || 0}</div>
            {col.id === 'to_do' && overdueCount > 0 && (
              <div className="text-xs text-red-400 mt-0.5">{overdueCount} overdue</div>
            )}
          </GlassPanel>
        ))}
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <GlassPanel className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[160px]">
              <Label className="text-xs">Prioritas</Label>
              <Select value={filter.priority} onValueChange={v => setFilter(f => ({ ...f, priority: v }))}>
                <SelectTrigger data-testid="filter-priority"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-[200px]">
              <Label className="text-xs">Akun</Label>
              <Select value={filter.account_id} onValueChange={v => setFilter(f => ({ ...f, account_id: v }))}>
                <SelectTrigger data-testid="filter-account"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua Akun</SelectItem>
                  {accounts.map(acc => (
                    <SelectItem key={acc.id} value={acc.id}>{acc.account_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasActiveFilter && (
              <Button variant="ghost" size="sm" onClick={resetFilter} data-testid="reset-filter-btn">
                <X className="w-3.5 h-3.5 mr-1" /> Reset
              </Button>
            )}
          </div>
        </GlassPanel>
      )}

      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading tasks...</div>
      ) : (
        <>
          <DragDropContext onDragEnd={handleDragEnd}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {COLUMNS.map(column => (
                <div key={column.id} data-testid={`column-${column.id}`}>
                  <div className={`mb-3 p-3 rounded-lg border ${column.color}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm">{column.title}</span>
                      <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-foreground/10">
                        {columns[column.id]?.length || 0}
                      </span>
                    </div>
                  </div>

                  <Droppable droppableId={column.id} isDropDisabled={false} isCombineEnabled={false} ignoreContainerClipping={false}>
                    {(provided, snapshot) => (
                      <div
                        ref={provided.innerRef}
                        {...provided.droppableProps}
                        className={`space-y-2 min-h-[200px] p-2 rounded-lg transition-colors ${
                          snapshot.isDraggingOver
                            ? 'bg-primary/5 border border-primary/30'
                            : 'border border-transparent'
                        }`}
                      >
                        {columns[column.id]?.length === 0 && (
                          <div className="text-center text-xs text-muted-foreground py-6 italic">
                            {snapshot.isDraggingOver ? 'Drop di sini...' : 'Tidak ada task'}
                          </div>
                        )}
                        {columns[column.id]?.map((task, index) => (
                          <Draggable key={task.id} draggableId={task.id} index={index}>
                            {(provided, snapshot) => (
                              <div
                                ref={provided.innerRef}
                                {...provided.draggableProps}
                                {...provided.dragHandleProps}
                                style={provided.draggableProps.style}
                                onClick={() => {
                                  if (!snapshot.isDragging) setDetailTaskId(task.id);
                                }}
                              >
                                <TaskCard
                                  task={task}
                                  isDragging={snapshot.isDragging}
                                  onRefresh={fetchTasks}
                                  token={token}
                                  accounts={accounts}
                                  onViewDetail={(id) => setDetailTaskId(id)}
                                />
                              </div>
                            )}
                          </Draggable>
                        ))}
                        {provided.placeholder}
                      </div>
                    )}
                  </Droppable>
                </div>
              ))}
            </div>
          </DragDropContext>
          {taskPagination && (
            <PaginationBar
              pagination={taskPagination}
              onPageChange={(p) => setTaskPage(p)}
              className="mt-3"
            />
          )}
        </>
      )}

      <CreateTaskDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={fetchTasks}
        token={token}
        accounts={accounts}
      />

      <TaskDetailDrawer
        taskId={detailTaskId}
        open={!!detailTaskId}
        onOpenChange={(o) => !o && setDetailTaskId(null)}
        onUpdated={fetchTasks}
        token={token}
      />

      {/* Guard: konfirmasi saat drag actionable task ke Done tanpa eksekusi */}
      <AlertDialog open={!!bypassConfirm} onOpenChange={(o) => !o && setBypassConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-amber-500" />
              Task Belum Dieksekusi
            </AlertDialogTitle>
            <AlertDialogDescription>
              <strong>"{bypassConfirm?.task?.title}"</strong> memiliki aksi sistem
              (<span className="font-mono text-xs">{bypassConfirm?.task?.action_type}</span>) yang
              belum dijalankan. Jika ditandai Done tanpa eksekusi, data tidak akan tersimpan ke sistem.
              <br /><br />
              Pilih tindakan:
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col sm:flex-row gap-2">
            <AlertDialogCancel onClick={() => setBypassConfirm(null)}>
              Batal (Buka Drawer)
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-amber-500 hover:bg-amber-600"
              onClick={() => {
                // Open drawer instead so user can execute action
                setDetailTaskId(bypassConfirm.task.id);
                setBypassConfirm(null);
              }}
            >
              <Zap size={14} className="mr-1.5" /> Eksekusi Sekarang
            </AlertDialogAction>
            <AlertDialogAction
              className="bg-muted text-muted-foreground hover:bg-muted/80"
              onClick={async () => {
                const t = bypassConfirm;
                setBypassConfirm(null);
                await _applyStatusChange(t.task.id, t.newStatus, null, null);
              }}
            >
              Tandai Done Manual
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
