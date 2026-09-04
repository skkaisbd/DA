import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// T3.6 — 3 modul Marketing Live → 1 hub
const LiveSessionModule = lazy(() => import('../marketing/LiveSessionModule'));
const LiveSessionAnalyticsDashboard = lazy(() => import('../marketing/LiveSessionAnalyticsDashboard'));
const LiveHostModule = lazy(() => import('../marketing/LiveHostModule'));

export default function MarketingLiveHub(props) {
  return (
    <HubTabs
      hubId="marketing-live-hub"
      tabs={[
        { key: 'sessions', label: 'Live Sessions', Component: LiveSessionModule },
        { key: 'analytics', label: 'Analytics', Component: LiveSessionAnalyticsDashboard },
        { key: 'livehost', label: 'LiveHost Mgmt', Component: LiveHostModule },
      ]}
      {...props}
    />
  );
}
