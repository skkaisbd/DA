import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-3 — konsolidasi KOL & Kreator Marketing -> 1 hub bertab.
const KOLCreatorModule    = lazy(() => import('../KOLCreatorModule'));
const KREATORRequestModule = lazy(() => import('../KREATORRequestModule'));
const KOLLeaderboardModule = lazy(() => import('../marketing/KOLLeaderboardModule'));

export default function MarketingKOLHub(props) {
  return (
    <HubTabs
      hubId="marketing-kol-hub"
      title="KOL & Kreator"
      subtitle="Kelola KOL/kreator, permintaan kolaborasi, dan leaderboard performa."
      tabs={[
        { key: 'manage', label: 'Kelola KOL', Component: KOLCreatorModule },
        { key: 'requests', label: 'Permintaan Kreator', Component: KREATORRequestModule },
        { key: 'leaderboard', label: 'Leaderboard', Component: KOLLeaderboardModule },
      ]}
      {...props}
    />
  );
}
