import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-2 — konsolidasi penggajian SDM -> 1 hub bertab.
const PayrollDashboardModule       = lazy(() => import('../PayrollDashboardModule'));
const RahazaPayrollProfilesModule  = lazy(() => import('../RahazaPayrollProfilesModule'));
const RahazaPayrollAllowancesModule = lazy(() => import('../RahazaPayrollAllowancesModule'));
const RahazaSalaryAdjustmentModule = lazy(() => import('../RahazaSalaryAdjustmentModule'));
const RahazaPayrollRunModule       = lazy(() => import('../RahazaPayrollRunModule'));

export default function HRPayrollHub(props) {
  return (
    <HubTabs
      hubId="hr-payroll-hub"
      title="Penggajian"
      subtitle="Satu pintu payroll: Dashboard, Profil Gaji, Tunjangan, Penyesuaian, Proses Gaji."
      tabs={[
        { key: 'dashboard', label: 'Dashboard', Component: PayrollDashboardModule },
        { key: 'profiles', label: 'Profil Gaji', Component: RahazaPayrollProfilesModule },
        { key: 'allowances', label: 'Tunjangan', Component: RahazaPayrollAllowancesModule },
        { key: 'adjustments', label: 'Penyesuaian', Component: RahazaSalaryAdjustmentModule },
        { key: 'run', label: 'Proses Gaji', Component: RahazaPayrollRunModule },
      ]}
      {...props}
    />
  );
}
