import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// PHASE B (6.1.4 #2) — 5 menu HR expense/travel → 1 hub "Expense & Perjalanan Dinas".
const EmployeeExpenseModule          = lazy(() => import('../EmployeeExpenseModule'));
const EmployeeTravelModule           = lazy(() => import('../EmployeeTravelModule'));
const EmployeeTravelSettlementModule = lazy(() => import('../EmployeeTravelSettlementModule'));
const EmployeeExpenseApprovalModule  = lazy(() => import('../EmployeeExpenseApprovalModule'));
const EmployeePerDiemAdminModule     = lazy(() => import('../EmployeePerDiemAdminModule'));

export default function HRExpenseTravelHub(props) {
  return (
    <HubTabs
      hubId="hr-expense-hub"
      title="Expense & Perjalanan Dinas"
      subtitle="Klaim biaya, perjalanan dinas, settlement, approval, dan konfigurasi per-diem — satu pintu."
      tabs={[
        { key: 'claims', label: 'Klaim Biaya Saya', Component: EmployeeExpenseModule },
        { key: 'travel', label: 'Perjalanan Dinas Saya', Component: EmployeeTravelModule },
        { key: 'settlement', label: 'Settlement Perjalanan', Component: EmployeeTravelSettlementModule },
        { key: 'approval', label: 'Approval Klaim & Dinas', Component: EmployeeExpenseApprovalModule },
        { key: 'perdiem', label: 'Konfigurasi Per Diem', Component: EmployeePerDiemAdminModule },
      ]}
      {...props}
    />
  );
}
