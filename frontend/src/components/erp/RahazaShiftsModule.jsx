import MasterDataCRUD from './MasterDataCRUD';

export default function RahazaShiftsModule({ token }) {
  return (
    <MasterDataCRUD
      title="Shift Kerja"
      description="Konfigurasi shift produksi. Jam mulai/selesai terhubung ke perhitungan borongan waktu dan absensi."
      endpoint="/api/rahaza/shifts"
      token={token}
      testIdPrefix="rahaza-shift"
      ieKey="shifts"
      columns={[
        { key: 'code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'start_time', label: 'Mulai' },
        { key: 'end_time', label: 'Selesai' },
      ]}
      fields={[
        { key: 'code', label: 'Kode', required: true, placeholder: 'Contoh: S3' },
        { key: 'name', label: 'Nama', required: true, placeholder: 'Contoh: Shift 3 Malam' },
        { key: 'start_time', label: 'Jam Mulai', type: 'time' },
        { key: 'end_time', label: 'Jam Selesai', type: 'time' },
      ]}
      defaultItem={{ code: '', name: '', start_time: '', end_time: '' }}
    />
  );
}
