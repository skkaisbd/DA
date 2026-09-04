import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// T3.9 — rnd-costing + rnd-hpp → 1 hub
const RnDCostingTab = lazy(() => import('../RnDCostingTab'));
const RnDHPPCalculatorModule = lazy(() => import('../RnDHPPCalculatorModule'));

export default function RnDCostingHub(props) {
  return (
    <HubTabs
      hubId="rnd-costing-hub"
      tabs={[
        { key: 'costing', label: 'Sample Costing', Component: RnDCostingTab },
        { key: 'hpp', label: 'HPP Calculator', Component: RnDHPPCalculatorModule },
      ]}
      {...props}
    />
  );
}
