/**
 * LiveHost Management Module — Thin Shell (Orchestrator)
 *
 * Refactored from monolithic 2328-LOC file (Session #11) into 11 sub-components in
 * `./live-host/*`. This shell only:
 *   - Holds the active tab state
 *   - Builds the Authorization header (memoized)
 *   - Routes tabs to extracted sub-components or pre-existing tab modules
 *
 * External API (preserved):
 *   - Default export `LiveHostModule`
 *   - Props: { token }
 *
 * Sub-components live in `./live-host/`:
 *   - LiveHostsTab.jsx + AddEditHostModal.jsx
 *   - ShiftsTab.jsx + AddShiftModal.jsx + RecordPerformanceModal.jsx
 *   - CalendarTab.jsx (placeholder)
 *   - ScriptsTab.jsx + ScriptModal.jsx
 *   - TrainingTab.jsx + TrainingModal.jsx + AssignTrainingModal.jsx
 *   - utils.js, Badges.jsx (shared)
 *
 * Pre-existing tabs (UNCHANGED):
 *   - AnalyticsTab (./AnalyticsTab)
 *   - PaymentTab (./PaymentTab)
 */

import { useState, useMemo } from 'react';
import {
  Users, Clock, Calendar, Video, TrendingUp, BarChart3, DollarSign,
} from 'lucide-react';
import AnalyticsTab from './AnalyticsTab';
import PaymentTab from './PaymentTab';
import LiveHostsTab from './live-host/LiveHostsTab';
import ShiftsTab from './live-host/ShiftsTab';
import CalendarTab from './live-host/CalendarTab';
import ScriptsTab from './live-host/ScriptsTab';
import TrainingTab from './live-host/TrainingTab';

export default function LiveHostModule({ token }) {
  const [activeTab, setActiveTab] = useState('hosts'); // hosts | shifts | calendar | scripts | training | analytics | payment
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }),
    [token]
  );

  return (
    <div className="min-h-screen bg-background p-4 md:p-6" data-testid="livehost-module">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Users size={24} className="text-primary" />
          LiveHost Management
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Kelola live host, shift scheduling, dan performance tracking
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl mb-6 overflow-x-auto">
        {[
          { id: 'hosts', label: 'Live Hosts', icon: Users },
          { id: 'shifts', label: 'Shift Management', icon: Clock },
          { id: 'calendar', label: 'Calendar View', icon: Calendar },
          { id: 'scripts', label: 'Script Library', icon: Video },
          { id: 'training', label: 'Training', icon: TrendingUp },
          { id: 'analytics', label: 'Analytics', icon: BarChart3 },
          { id: 'payment', label: 'Payment', icon: DollarSign },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors flex-1 justify-center whitespace-nowrap ${
              activeTab === tab.id
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`tab-${tab.id}`}
          >
            <tab.icon size={15} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'hosts' && <LiveHostsTab authH={authH} />}
      {activeTab === 'shifts' && <ShiftsTab authH={authH} />}
      {activeTab === 'calendar' && <CalendarTab authH={authH} />}
      {activeTab === 'scripts' && <ScriptsTab authH={authH} />}
      {activeTab === 'training' && <TrainingTab authH={authH} />}
      {activeTab === 'analytics' && <AnalyticsTab authH={authH} />}
      {activeTab === 'payment' && <PaymentTab authH={authH} />}
    </div>
  );
}
