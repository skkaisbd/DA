import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-2 — konsolidasi pengaturan sistem Manajemen -> 1 hub bertab.
// IA v4 (FASE IA-2) — tab "Backup" DIKELUARKAN dari hub ini: Backup & Restore kini
// pintu sendiri (`mgmt-backup-restore`) di Portal Administrasi Sistem. Alasannya
// backup adalah aksi berisiko + sering dipakai saat darurat, jadi tidak boleh
// terkubur sebagai tab ke-5. Menyisakannya di sini juga akan melanggar guard
// NAV-DUPTAB (satu isi, dua pintu).
//
// SESI #19 — DUA tab PDF ("PDF: Kolom Tabel" + "PDF: Surat & TTD") DISATUKAN jadi
// satu tab "PDF & Kop Surat". Keluhan pemilik: "cek ada dua halaman berbeda ui
// ux-nya jelas". Keduanya mengatur SATU dokumen dari dua tempat (kolom di layar
// pertama, kop & tanda tangan di layar kedua) sehingga tidak ada satu pun tempat
// yang bisa menjawab "seperti apa surat jalan saya nanti?". Layar penggantinya
// punya pratinjau PDF di sampingnya.
const CompanySettingsModule   = lazy(() => import('../CompanySettingsModule'));
const PdfTemplateStudio       = lazy(() => import('../pdf/PdfTemplateStudio'));
const IntegrationSettingsModule = lazy(() => import('../IntegrationSettingsModule'));

export default function ManagementSystemHub(props) {
  return (
    <HubTabs
      hubId="mgmt-system-hub"
      title="Pengaturan Sistem"
      subtitle="Konfigurasi perusahaan, template dokumen PDF, dan integrasi API."
      tabs={[
        { key: 'company', label: 'Perusahaan', Component: CompanySettingsModule },
        { key: 'pdf', label: 'PDF & Kop Surat', Component: PdfTemplateStudio },
        { key: 'api', label: 'API Keys', Component: IntegrationSettingsModule },
      ]}
      {...props}
    />
  );
}
