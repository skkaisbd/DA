import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// IA v2.1 fase-2 — konsolidasi kontrol akses Manajemen -> 1 hub bertab.
// 2026-08-06 — tab "Hak Akses" (matriks raksasa) DIHAPUS. Owner bingung karena
// ada dua tempat mengatur akses. Sekarang semua konfigurasi peran/portal/menu/izin
// ada di satu modul: RoleManagementModule ("Peran & Hak Akses").
const UserManagementModule = lazy(() => import('../UserManagementModule'));
const RoleManagementModule = lazy(() => import('../RoleManagementModule'));

export default function ManagementAccessHub(props) {
  return (
    <HubTabs
      hubId="mgmt-access-hub"
      title="Kontrol Akses"
      subtitle="Kelola pengguna dan peran (portal, menu, izin aksi) dalam satu tempat."
      tabs={[
        { key: 'users', label: 'Pengguna', Component: UserManagementModule },
        { key: 'roles', label: 'Peran & Hak Akses', Component: RoleManagementModule },
      ]}
      {...props}
    />
  );
}
