import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 — konsolidasi 6 laporan keuangan inti -> 1 hub bertab.
const RahazaTrialBalanceModule  = lazy(() => import('../RahazaTrialBalanceModule'));
const RahazaGeneralLedgerModule = lazy(() => import('../RahazaGeneralLedgerModule'));
const RahazaPnLModule           = lazy(() => import('../RahazaPnLModule'));
const RahazaBalanceSheetModule  = lazy(() => import('../RahazaBalanceSheetModule'));
const RahazaCashFlowModule      = lazy(() => import('../RahazaCashFlowModule'));
const RahazaAPAgingModule       = lazy(() => import('../RahazaAPAgingModule'));

export default function FinanceReportsHub(props) {
  return (
    <HubTabs
      hubId="fin-reports-hub"
      title="Laporan Keuangan"
      subtitle="Satu pintu laporan inti: Neraca Saldo, Buku Besar, Laba Rugi, Neraca, Arus Kas, Aging Hutang."
      tabs={[
        { key: 'tb', label: 'Neraca Saldo', Component: RahazaTrialBalanceModule },
        { key: 'gl', label: 'Buku Besar', Component: RahazaGeneralLedgerModule },
        { key: 'pnl', label: 'Laba Rugi', Component: RahazaPnLModule },
        { key: 'bs', label: 'Neraca', Component: RahazaBalanceSheetModule },
        { key: 'cashflow', label: 'Arus Kas', Component: RahazaCashFlowModule },
        { key: 'apaging', label: 'Aging Hutang', Component: RahazaAPAgingModule },
      ]}
      {...props}
    />
  );
}
