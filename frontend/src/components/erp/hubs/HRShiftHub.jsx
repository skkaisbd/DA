import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-2 — konsolidasi manajemen shift SDM -> 1 hub bertab.
const HRShiftManagementModule = lazy(() => import('../HRShiftManagementModule'));
const ShiftSchedulerModule    = lazy(() => import('../hr/ShiftSchedulerModule'));

export default function HRShiftHub(props) {
  return (
    <HubTabs
      hubId="hr-shift-hub"
      title="Shift"
      subtitle="Kelola definisi shift dan penjadwalannya."
      tabs={[
        { key: 'manage', label: 'Kelola Shift', Component: HRShiftManagementModule },
        { key: 'schedule', label: 'Jadwal Shift', Component: ShiftSchedulerModule },
      ]}
      {...props}
    />
  );
}
