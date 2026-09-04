import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// RC-IA-warehouse-1 (Opsi A) — konsolidasi 4 modul "STOK & AKURASI" gudang → 1 hub.
// Menghilangkan kebingungan "pintu mana yang benar" untuk stok yang sama (SSOT rahaza_material_stock / unified).
//   - Viewer Stok (Unified)  → UnifiedInventoryModule  (read-only, sumber gabungan)
//   - Stok & Pergerakan      → RahazaStockModule       (stok kanonik + receive/transfer/adjust rahaza SSOT)
//   - Opname                 → WMSOpnameScanModule    (Fase 4/5: scan-driven /api/wms/opname3 SSOT + finance)
//   - Penyesuaian (Adjust)   → InventoryScrapModule    (jalur adjust RESMI: rahaza/material-adjust + posting GL)
const UnifiedInventoryModule  = lazy(() => import('../UnifiedInventoryModule'));
const RahazaStockModule       = lazy(() => import('../RahazaStockModule'));
const WMSOpnameScanModule = lazy(() => import('../WMSOpnameScanModule'));  // Fase 4: opname scan-driven (SSOT + finance)
const InventoryScrapModule    = lazy(() => import('../InventoryScrapModule'));
// FASE 6.6-A: kesehatan & rekonsiliasi skema baris stok (baris warisan skema A/B/C).
const StockSchemaHealthModule = lazy(() => import('../StockSchemaHealthModule'));
// FASE E: "Posisi & Search" dilipat ke hub Stok & Akurasi (dari monolit Scanner Barcode).
const WMSPositionsTab = lazy(() => import('../WMSModule').then(m => ({ default: m.PositionsTab })));

export default function WMSStockHub(props) {
  return (
    <HubTabs
      hubId="wms-stock-hub"
      title="Stok & Akurasi"
      subtitle="Satu pintu: lihat stok, kelola pergerakan, opname, penyesuaian, dan posisi bin — semua terhubung SSOT."
      tabs={[
        { key: 'viewer', label: 'Viewer Stok (Unified)', Component: UnifiedInventoryModule },
        { key: 'stock', label: 'Stok & Pergerakan', Component: RahazaStockModule },
        { key: 'opname', label: 'Opname Stok', Component: WMSOpnameScanModule },
        { key: 'adjust', label: 'Penyesuaian (Adjustment)', Component: InventoryScrapModule },
        { key: 'positions', label: 'Posisi & Search', Component: WMSPositionsTab },
        { key: 'schema', label: 'Kesehatan Skema', Component: StockSchemaHealthModule },
      ]}
      {...props}
    />
  );
}
