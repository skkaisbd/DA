import { useEffect, useState } from 'react';
import MasterDataCRUD from './MasterDataCRUD';

export default function RahazaLocationsModule({ token }) {
  const [locs, setLocs] = useState([]);
  useEffect(() => {
    fetch('/api/rahaza/locations', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then(setLocs).catch(() => {});
  }, [token]);

  const gedungOptions = locs.filter(l => l.type === 'gedung' && l.active).map(l => ({ value: l.id, label: l.name }));

  return (
    <MasterDataCRUD
      title="Gedung & Zona"
      description="Lokasi fisik PT Rahaza: gedung utama dan zona di dalamnya (produksi/gudang)."
      endpoint="/api/rahaza/locations"
      token={token}
      testIdPrefix="rahaza-location"
      ieKey="locations"
      columns={[
        { key: 'code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'type', label: 'Tipe', render: v => v === 'gedung' ? 'Gedung' : 'Zona' },
        { key: 'parent_name', label: 'Induk (Gedung)', render: v => v || '-' },
      ]}
      fields={[
        { key: 'code', label: 'Kode', required: true, placeholder: 'Contoh: GED-C atau ZNA-QC' },
        { key: 'name', label: 'Nama', required: true, placeholder: 'Contoh: Gedung C / Zona QC' },
        { key: 'type', label: 'Tipe', type: 'select', required: true,
          options: [{ value: 'gedung', label: 'Gedung' }, { value: 'zona', label: 'Zona' }] },
        { key: 'parent_id', label: 'Induk Gedung (khusus Zona)', type: 'select',
          options: gedungOptions, help: 'Isi hanya jika tipe = Zona.' },
      ]}
      defaultItem={{ code: '', name: '', type: 'zona', parent_id: '' }}
    />
  );
}
