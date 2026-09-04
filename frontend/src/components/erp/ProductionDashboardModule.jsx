/**
 * ProductionDashboardModule — Dashboard Produksi (layar tunggal)
 *
 * FASE IA-1 (2026-07-26) — dua tab DIHAPUS karena melanggar "1 pintu = 1 tujuan"
 * (docs/PROPOSAL_IA_PRODUKSI.md §3):
 *   - tab "Monitoring" merender komponen yang SAMA dengan pintu menu
 *     "Tracking Produksi" (`prod-monitoring`).
 *   - tab "AI Insight" merender komponen yang sama dengan pintu "Estimasi AI"
 *     (`prod-ai-insights`).
 *
 * 2026-07-27 — isi dashboard DIGANTI: WIP per proses internal
 * (Cutting→Sewing→Finishing→QC→Packing) sudah tidak mencerminkan kenyataan
 * (jahit di vendor CMT, cutting punya portal sendiri) dan selalu bernilai nol.
 * Sekarang menampilkan perjalanan barang: Rencana PO → Cutting → Di Vendor CMT
 * → Terima & QC → Permak → Serah Terima FG (sumber: GET /api/prod/dashboard).
 */
import { Suspense } from 'react';
import ProductionDashboardOverview from './ProductionDashboardOverview';

const Spinner = () => (
  <div className="flex items-center justify-center h-48">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[hsl(var(--primary))]" />
  </div>
);

export default function ProductionDashboardModule({ token, user, headers, userRole, hasPerm, onNavigate, moduleId }) {
  return (
    <div className="space-y-4" data-testid="production-dashboard">
      <Suspense fallback={<Spinner />}>
        <ProductionDashboardOverview
          token={token}
          user={user}
          headers={headers}
          userRole={userRole}
          onNavigate={onNavigate}
        />
      </Suspense>
    </div>
  );
}
