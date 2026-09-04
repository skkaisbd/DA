import { useEffect, useState } from 'react';
import MasterDataCRUD from './MasterDataCRUD';

/**
 * RahazaLinesModule — Navigation Refinement
 *
 * Line = tim/kelompok yang mengerjakan semua proses secara berurutan.
 * Line TIDAK lagi terikat pada satu proses. Process_id menjadi opsional
 * (hanya sebagai informasi default, bukan filter eksekusi).
 * Proses ditentukan dari ASSIGNMENT saat assign line ke operator.
 */
export default function RahazaLinesModule({ token }) {
  const [locs, setLocs] = useState([]);

  useEffect(() => {
    const h = { Authorization: `Bearer ${token}` };
    fetch('/api/rahaza/locations', { headers: h }).then(r => r.ok ? r.json() : []).then(setLocs).catch(() => {});
  }, [token]);

  const locOptions = locs.filter(l => l.active).map(l => ({ value: l.id, label: `${l.code} · ${l.name}` }));

  return (
    <MasterDataCRUD
      title="Line Produksi"
      description="Line = tim/kelompok yang mengerjakan semua proses secara berurutan. 1 line bisa punya banyak operator di proses berbeda. Proses ditentukan saat assign operator, bukan saat membuat line."
      endpoint="/api/rahaza/lines"
      token={token}
      testIdPrefix="rahaza-line"
      ieKey="lines"
      columns={[
        { key: 'code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'location_name', label: 'Lokasi', render: v => v || '-' },
        { key: 'capacity_per_hour', label: 'Kapasitas / jam', render: v => v ? `${v} pcs` : '-' },
        { key: 'notes', label: 'Catatan', render: v => v || '-' },
      ]}
      fields={[
        { key: 'code', label: 'Kode Line', required: true, placeholder: 'Contoh: LN-01, LINE-A' },
        { key: 'name', label: 'Nama Line', placeholder: 'Contoh: Line 1, Tim Alpha' },
        { key: 'location_id', label: 'Lokasi (Zona/Gedung)', type: 'select', options: locOptions },
        { key: 'capacity_per_hour', label: 'Kapasitas per jam (pcs)', type: 'number', placeholder: 'Opsional' },
        { key: 'notes', label: 'Catatan' },
      ]}
      defaultItem={{ code: '', name: '', location_id: '', capacity_per_hour: 0, notes: '' }}
    />
  );
}
