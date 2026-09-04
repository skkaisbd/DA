import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// T3.3 — fin-journal-entry + fin-journal-list → 1 modul 2 tab
const RahazaJournalEntryModule = lazy(() => import('../RahazaJournalEntryModule'));
const RahazaJournalListModule = lazy(() => import('../RahazaJournalListModule'));

export default function FinanceJournalHub(props) {
  return (
    <HubTabs
      hubId="fin-journal-hub"
      tabs={[
        { key: 'entry', label: 'Jurnal Umum', Component: RahazaJournalEntryModule },
        { key: 'list', label: 'Daftar Jurnal', Component: RahazaJournalListModule },
      ]}
      {...props}
    />
  );
}
