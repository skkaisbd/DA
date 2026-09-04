import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-2 — konsolidasi cuti & lembur SDM -> 1 hub bertab.
const RahazaOvertimeModule  = lazy(() => import('../RahazaOvertimeModule'));
const RahazaLeaveModule     = lazy(() => import('../RahazaLeaveModule'));
const HRLeaveBalancesModule = lazy(() => import('../HRLeaveBalancesModule'));

export default function HRLeaveHub(props) {
  return (
    <HubTabs
      hubId="hr-leave-hub"
      title="Cuti & Lembur"
      subtitle="Pengajuan lembur, cuti, dan saldo cuti karyawan."
      tabs={[
        { key: 'overtime', label: 'Lembur', Component: RahazaOvertimeModule },
        { key: 'leave', label: 'Cuti', Component: RahazaLeaveModule },
        { key: 'balances', label: 'Saldo Cuti', Component: HRLeaveBalancesModule },
      ]}
      {...props}
    />
  );
}
