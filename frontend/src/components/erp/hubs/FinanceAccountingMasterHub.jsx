import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 — konsolidasi master akuntansi -> 1 hub bertab.
const RahazaCOAModule             = lazy(() => import('../RahazaCOAModule'));
const RahazaPostingProfilesModule = lazy(() => import('../RahazaPostingProfilesModule'));
const EmployeeExpenseGLMappingModule = lazy(() => import('../EmployeeExpenseGLMappingModule'));
const EmployeeExpenseCategoryMasterModule = lazy(() => import('../EmployeeExpenseCategoryMasterModule'));
const RahazaPeriodsModule         = lazy(() => import('../RahazaPeriodsModule'));
const AdminSetupPanelModule       = lazy(() => import('../AdminSetupPanelModule'));
const RahazaCoaAutoModule         = lazy(() => import('../RahazaCoaAutoModule'));

export default function FinanceAccountingMasterHub(props) {
  return (
    <HubTabs
      hubId="fin-accounting-master-hub"
      title="Master Akuntansi"
      subtitle="Konfigurasi akuntansi: Bagan Akun, Profil Posting, Pemetaan GL, Kategori Expense, Periode, Setup."
      tabs={[
        { key: 'coa', label: 'Bagan Akun', Component: RahazaCOAModule },
        { key: 'posting', label: 'Profil Posting', Component: RahazaPostingProfilesModule },
        { key: 'coa-auto', label: 'Auto Akun (Subledger)', Component: RahazaCoaAutoModule },
        { key: 'glmap', label: 'Pemetaan GL', Component: EmployeeExpenseGLMappingModule },
        { key: 'expcat', label: 'Kategori Expense', Component: EmployeeExpenseCategoryMasterModule },
        { key: 'periods', label: 'Periode', Component: RahazaPeriodsModule },
        { key: 'setup', label: 'Setup Akuntansi', Component: AdminSetupPanelModule },
      ]}
      {...props}
    />
  );
}
