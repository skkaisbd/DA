import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 — konsolidasi master "Produk & Tim" Produksi -> 1 hub bertab.
const RahazaModelsAndBOMModule = lazy(() => import('../RahazaModelsAndBOMModule'));
const ProductionWorkspaceMaster = lazy(() => import('../ProductionWorkspaceMaster'));
const RahazaEmployeesModule    = lazy(() => import('../RahazaEmployeesModule'));

export default function ProductionMasterProductHub(props) {
  return (
    <HubTabs
      hubId="prod-master-product-hub"
      title="Master Produk"
      subtitle="Data produk & tim: Produk & BOM, Lokasi Kerja, dan Operator & Skill."
      tabs={[
        { key: 'products', label: 'Produk & BOM', Component: RahazaModelsAndBOMModule },
        { key: 'workspace', label: 'Lokasi Kerja', Component: ProductionWorkspaceMaster },
        { key: 'operators', label: 'Operator & Skill', Component: RahazaEmployeesModule },
      ]}
      {...props}
    />
  );
}
