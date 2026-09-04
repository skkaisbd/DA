/**
 * HRPerformanceHub.jsx
 * Consolidation #14: Performance Management — KPI + Annual Review + 360° Feedback
 * Replaces: hr-kpi + hr-performance + hr-360-feedback (3 sidebar entries → 1)
 * Effort: 12h | Risk: Low
 */
import React, { useState } from 'react';
import { Target, TrendingUp, MessageSquare } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import HRKPIModule          from './HRKPIModule';
import HRPerformanceModule  from './HRPerformanceModule';
import HR360FeedbackModule  from './HR360FeedbackModule';

export default function HRPerformanceHub({ token, user }) {
  const [activeTab, setActiveTab] = useState('kpi');

  return (
    <div className="h-full" data-testid="hr-performance-hub">
      {/* Hub Header */}
      <div className="px-4 md:px-6 py-4 border-b bg-background">
        <h1 className="text-xl font-bold tracking-tight">Performance Management</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          KPI operasional bulanan, annual performance review, dan 360° feedback karyawan
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
        <div className="px-4 md:px-6 pt-4 border-b bg-background">
          <TabsList className="h-9">
            <TabsTrigger value="kpi" className="gap-1.5" data-testid="tab-kpi">
              <Target size={13} />
              KPI Bulanan
            </TabsTrigger>
            <TabsTrigger value="review" className="gap-1.5" data-testid="tab-annual-review">
              <TrendingUp size={13} />
              Annual Review
            </TabsTrigger>
            <TabsTrigger value="feedback" className="gap-1.5" data-testid="tab-360-feedback">
              <MessageSquare size={13} />
              360° Feedback
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="kpi" className="flex-1 overflow-auto m-0">
          <HRKPIModule token={token} />
        </TabsContent>
        <TabsContent value="review" className="flex-1 overflow-auto m-0">
          <HRPerformanceModule token={token} />
        </TabsContent>
        <TabsContent value="feedback" className="flex-1 overflow-auto m-0">
          <HR360FeedbackModule token={token} user={user} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
