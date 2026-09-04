import React, { lazy } from 'react';
import HubTabs from './HubTabs';

/**
 * RC-FLOW-UX (de-dup pintu, keputusan user 3b) — Konsolidasi 2 pintu expense di
 * Portal Keuangan menjadi SATU pintu ber-tab:
 *   - "Pengeluaran (Umum)"          → RahazaExpensesModule       (pengeluaran/petty cash perusahaan)
 *   - "Klaim Karyawan (Disbursement)" → EmployeeExpenseApprovalModule (approve + cairkan klaim karyawan → JE GL)
 *
 * Deep-link lama `fin-expense-settlement` tetap aman: di moduleRegistry ia dipetakan
 * ke makeRedirect('fin-expenses','settlement') sehingga membuka tab settlement.
 */
const RahazaExpensesModule          = lazy(() => import('../RahazaExpensesModule'));
const EmployeeExpenseApprovalModule = lazy(() => import('../EmployeeExpenseApprovalModule'));

export default function FinanceExpenseHub(props) {
  return (
    <HubTabs
      hubId="fin-expenses"
      title="Pengeluaran & Klaim Karyawan"
      subtitle="Pengeluaran umum perusahaan dan pencairan (disbursement) klaim biaya karyawan — satu pintu."
      tabs={[
        { key: 'pengeluaran', label: 'Pengeluaran (Umum)', Component: RahazaExpensesModule },
        { key: 'settlement', label: 'Klaim Karyawan (Disbursement)', Component: EmployeeExpenseApprovalModule },
      ]}
      {...props}
    />
  );
}
