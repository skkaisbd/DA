import { useEffect, useState } from 'react';
import MasterDataCRUD from './MasterDataCRUD';

const STATUS_OPTIONS = [
  { value: 'idle', label: 'Idle' },
  { value: 'active', label: 'Aktif (sedang digunakan)' },
  { value: 'maintenance', label: 'Maintenance' },
];

export default function RahazaMachinesModule({ token }) {
  const [locs, setLocs] = useState([]);
  useEffect(() => {
    fetch('/api/rahaza/locations', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then(setLocs).catch(() => {});
  }, [token]);

  const locOptions = locs.filter(l => l.active).map(l => ({ value: l.id, label: `${l.code} · ${l.name}` }));

  return (
    <MasterDataCRUD
      title="Mesin Rajut"
      description="Daftar mesin rajut di seluruh gedung. Kapasitas berkembang 10 → 40 mesin."
      endpoint="/api/rahaza/machines"
      token={token}
      testIdPrefix="rahaza-machine"
      columns={[
        { key: 'code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'machine_type', label: 'Tipe' },
        { key: 'gauge', label: 'Gauge' },
        { key: 'location_name', label: 'Lokasi', render: v => v || '-' },
        { key: 'status', label: 'Status Mesin',
          render: v => {
            const map = { idle: 'Idle', active: 'Aktif', maintenance: 'Maintenance' };
            return map[v] || v;
          } },
      ]}
      fields={[
        { key: 'code', label: 'Kode', required: true, placeholder: 'Contoh: MR-01' },
        { key: 'name', label: 'Nama', placeholder: 'Opsional, default = Kode' },
        { key: 'machine_type', label: 'Tipe Mesin', placeholder: 'Contoh: Rajut Flat, Circular, dsb' },
        { key: 'gauge', label: 'Gauge', placeholder: 'Contoh: 7G / 12G' },
        { key: 'location_id', label: 'Lokasi', type: 'select', options: locOptions },
        { key: 'status', label: 'Status Mesin', type: 'select', options: STATUS_OPTIONS },
      ]}
      defaultItem={{ code: '', name: '', machine_type: 'Rajut', gauge: '', location_id: '', status: 'idle' }}
    />
  );
}
