import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// PHASE B (6.1.4 #5) — modul desain & dokumentasi RnD → 1 hub "Desain & Tech Pack".
const RnDStylesTab      = lazy(() => import('../RnDStylesTab'));
const RnDVariantModule  = lazy(() => import('../RnDVariantModule'));
const RnDSizeMappingModule = lazy(() => import('../RnDSizeMappingModule'));
const RnDTechPackModule = lazy(() => import('../RnDTechPackModule'));
const RnDPatternModule  = lazy(() => import('../RnDPatternModule'));
const RnDRevisionsTab   = lazy(() => import('../RnDRevisionsTab'));

export default function RnDDesignHub(props) {
  return (
    <HubTabs
      hubId="rnd-design-hub"
      title="Desain & Tech Pack"
      subtitle="Style, varian, tech pack, pola & marking, dan revisi — alur dokumentasi desain dalam satu pintu."
      tabs={[
        { key: 'styles', label: 'Style & Tech Pack', Component: RnDStylesTab },
        { key: 'variants', label: 'Varian Produk', Component: RnDVariantModule },
        { key: 'sizemap', label: 'Padankan Ukuran', Component: RnDSizeMappingModule },
        { key: 'techpack', label: 'Tech Pack Manager', Component: RnDTechPackModule },
        { key: 'patterns', label: 'Pola & Marking', Component: RnDPatternModule },
        { key: 'revisions', label: 'Revisi & Approval', Component: RnDRevisionsTab },
      ]}
      {...props}
    />
  );
}
