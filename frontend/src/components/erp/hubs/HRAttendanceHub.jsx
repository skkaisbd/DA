import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// PHASE B (6.1.4 #3) — 3 menu absensi → 1 hub "Absensi".
const RahazaAttendanceModule         = lazy(() => import('../RahazaAttendanceModule'));
const RahazaAutoAttendanceModule     = lazy(() => import('../RahazaAutoAttendanceModule'));
const RahazaAttendanceApprovalModule = lazy(() => import('../RahazaAttendanceApprovalModule'));

export default function HRAttendanceHub(props) {
  return (
    <HubTabs
      hubId="hr-attendance-hub"
      title="Absensi & Clock In/Out"
      subtitle="Absensi harian manual, absen otomatis, dan approval absen — satu pintu."
      tabs={[
        { key: 'manual', label: 'Absensi Harian (Manual)', Component: RahazaAttendanceModule },
        { key: 'auto', label: 'Absen Otomatis', Component: RahazaAutoAttendanceModule },
        { key: 'approval', label: 'Approval Absen', Component: RahazaAttendanceApprovalModule },
      ]}
      {...props}
    />
  );
}
