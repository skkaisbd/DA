import React from 'react';
import DataImportWizard from './marketing/DataImportWizard';

/**
 * Pusat Impor Data Marketing — SATU pintu, TANPA AI.
 *
 * F0.6 (2026-08-12) — dua mesin impor lama DIHAPUS TOTAL (keputusan owner):
 *   · `routes/universal_import.py` + `ImportCenterPage`/`SmartImportEditorPage`
 *     (AI menebak jenis data; menulis ke koleksi tujuan yang SALAH
 *      `marketing_discount_campaigns`/`marketing_sample_shipments`, dan `sales_data`
 *      jatuh ke `marketing_import_sales_data` yang tidak pernah dibaca layar mana pun;
 *      tanpa `account_id`; tanpa dedupe ⇒ commit 2× = data dobel)
 *   · `routes/marketing_import.py` + `SmartImportModule` (khusus rekap sales; bentuk
 *     dokumen `metrics{}` versi ke-3 yang berbeda dari input manual)
 *
 * Sisanya satu jalur resmi: `DataImportWizard` → `/api/marketing/data-import/*`
 * (pilih jenis data → pilih toko → template → periksa pemetaan → pratinjau → commit
 *  → rollback). Tombol AI hanya MENGUSULKAN pemetaan untuk kolom yang belum terpetakan
 * dan tidak pernah menimpa hasil exact/sinonim/manual.
 */
export default function ImportCenterModule({ token, user }) {
  return (
    <div className="w-full" data-testid="import-center">
      <DataImportWizard token={token} user={user} />
    </div>
  );
}
