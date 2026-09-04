import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 — konsolidasi master "Proses & Standar" Produksi -> 1 hub bertab.
const RahazaProcessesModule        = lazy(() => import('../RahazaProcessesModule'));
const RahazaSOPModule              = lazy(() => import('../RahazaSOPModule'));
// FASE 5: Kode Cacat (qc engine lama) diarsip.
const RahazaProductionCalendarModule = lazy(() => import('../RahazaProductionCalendarModule'));

export default function ProductionMasterProcessHub(props) {
  return (
    <HubTabs
      hubId="prod-master-process-hub"
      title="Master Proses"
      subtitle="Standar proses produksi: Proses, SOP, Kode Cacat, dan Kalender."
      tabs={[
        { key: 'processes', label: 'Proses', Component: RahazaProcessesModule },
        { key: 'sop', label: 'SOP', Component: RahazaSOPModule },
        { key: 'calendar', label: 'Kalender', Component: RahazaProductionCalendarModule },
      ]}
      {...props}
    />
  );
}
