/**
 * MarketingTaskHubModule.jsx
 * Consolidation #10: Kanban Board + Approval Inbox + Task Templates
 * Replaces: marketing-tasks + marketing-approvals + marketing-templates (3 → 1)
 */
import React, { useState, useEffect } from 'react';
import { LayoutGrid, ClipboardCheck, FileCog } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import TaskManagementModule from './TaskManagementModule';
import ApprovalInboxModule from './ApprovalInboxModule';
import TaskTemplatesModule from './TaskTemplatesModule';

const API = process.env.REACT_APP_BACKEND_URL;

export default function MarketingTaskHubModule({ token }) {
  const [pendingCount, setPendingCount] = useState(0);
  const [activeTab, setActiveTab] = useState('kanban');

  useEffect(() => {
    // Fetch pending approval count for badge
    fetch(`${API}/api/marketing/tasks?status=pending_approval&limit=1`, {
      headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          const count = data?.pagination?.total ?? (data?.tasks?.length ?? 0);
          setPendingCount(count);
        }
      })
      .catch(() => {});
  }, [token]);

  return (
    <div className="h-full" data-testid="marketing-task-hub">
      {/* Hub Header */}
      <div className="px-4 md:px-6 py-4 border-b bg-background">
        <h1 className="text-xl font-bold tracking-tight">Task Management</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Kelola task harian, approval workflow, dan template task berulang dalam satu dashboard
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
        <div className="px-4 md:px-6 pt-4 border-b bg-background">
          <TabsList className="h-9">
            <TabsTrigger value="kanban" className="gap-1.5" data-testid="tab-kanban">
              <LayoutGrid size={13} />
              Kanban Board
            </TabsTrigger>
            <TabsTrigger value="approvals" className="gap-1.5" data-testid="tab-approvals">
              <ClipboardCheck size={13} />
              Pending Approval
              {pendingCount > 0 && (
                <Badge variant="destructive" className="ml-1 h-4 min-w-4 px-1 text-[10px]">
                  {pendingCount}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="templates" className="gap-1.5" data-testid="tab-templates">
              <FileCog size={13} />
              Task Templates
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="kanban" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <TaskManagementModule token={token} />
        </TabsContent>
        <TabsContent value="approvals" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <ApprovalInboxModule token={token} />
        </TabsContent>
        <TabsContent value="templates" className="flex-1 overflow-auto m-0 p-4 md:p-6">
          <TaskTemplatesModule token={token} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
