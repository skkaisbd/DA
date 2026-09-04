import { useEffect, useState } from 'react';
import MasterDataCRUD from './MasterDataCRUD';

const WAGE_SCHEMES = [
  { value: 'borongan_pcs', label: 'Borongan Hasil (per pcs)' },
  { value: 'borongan_jam', label: 'Borongan Waktu (per jam)' },
  { value: 'mingguan',     label: 'Gaji Mingguan' },
  { value: 'bulanan',      label: 'Gaji Bulanan' },
];

const CONTRACT_TYPES = [
  { value: 'PKWT',    label: 'PKWT (Kontrak)' },
  { value: 'PKWTT',   label: 'PKWTT (Tetap)' },
  { value: 'Magang',  label: 'Magang / Percobaan' },
  { value: 'Tetap',   label: 'Karyawan Tetap' },
];

const DEPARTMENTS = [
  'Produksi', 'QC', 'Gudang/WMS', 'HRD', 'Finance/Accounting',
  'Marketing', 'IT', 'Administrasi', 'Manajemen', 'Lainnya',
];

const JOB_TITLES = [
  'Operator Cutting', 'Operator CMT-Sewing', 'Operator QC', 'Operator Finishing', 'Operator Packing',
  'Operator Washer', 'Operator Sontek', 'Supervisor', 'Staff Gudang', 'Staff Admin', 'Lainnya',
];

export default function RahazaEmployeesModule({ token }) {
  const [locs, setLocs] = useState([]);
  const [employees, setEmployees] = useState([]);

  useEffect(() => {
    fetch('/api/rahaza/locations', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then(setLocs).catch(() => {});
  }, [token]);

  // Load employees for "Atasan" dropdown
  useEffect(() => {
    fetch('/api/rahaza/employees?limit=500', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : [])
      .then((list) => setEmployees(Array.isArray(list) ? list : (list.items || list.rows || [])))
      .catch(() => {});
  }, [token]);

  const locOptions = locs.filter(l => l.active).map(l => ({ value: l.id, label: `${l.code} · ${l.name}` }));
  const managerOptions = employees
    .filter(e => e.active !== false)
    .map(e => ({
      value: e.id,
      label: `${e.employee_code} — ${e.name}${e.job_title ? ` (${e.job_title})` : ''}`,
    }));

  return (
    <MasterDataCRUD
      title="Karyawan & Operator"
      description="Master karyawan (operator mesin, supervisor, staff). Skema gaji (borongan/mingguan/bulanan) dipakai oleh portal HR. Field 'Atasan' dipakai untuk approval kenaikan gaji."
      endpoint="/api/rahaza/employees"
      token={token}
      testIdPrefix="rahaza-employee"
      ieKey="employees"
      columns={[
        { key: 'employee_code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'department', label: 'Divisi', render: v => v || '-' },
        { key: 'job_title', label: 'Jabatan' },
        { key: 'manager_name', label: 'Atasan', render: v => v || '—' },
        { key: 'contract_type', label: 'Kontrak', render: v => v || '-' },
        { key: 'wage_scheme', label: 'Skema Gaji',
          render: v => (WAGE_SCHEMES.find(s => s.value === v)?.label) || v },
      ]}
      fields={[
        { key: 'employee_code', label: 'Kode Karyawan', required: true, placeholder: 'Contoh: EMP-001' },
        { key: 'name', label: 'Nama Lengkap', required: true },
        { key: 'department', label: 'Divisi/Departemen', type: 'select', options: DEPARTMENTS.map(d => ({ value: d, label: d })) },
        { key: 'job_title', label: 'Jabatan', type: 'select', options: JOB_TITLES.map(j => ({ value: j, label: j })) },
        { key: 'manager_id', label: 'Atasan (Manager)', type: 'select', options: managerOptions,
          help: 'Atasan yang akan approve usulan kenaikan gaji untuk karyawan ini.' },
        { key: 'location_id', label: 'Lokasi Utama', type: 'select', options: locOptions },
        { key: 'phone', label: 'No. Telepon', placeholder: 'Opsional' },
        { key: 'contract_type', label: 'Tipe Kontrak', type: 'select', options: CONTRACT_TYPES },
        { key: 'contract_start_date', label: 'Tgl Mulai Kontrak', type: 'date' },
        { key: 'contract_end_date', label: 'Tgl Berakhir Kontrak', type: 'date', help: 'Wajib untuk PKWT / Magang' },
        { key: 'wage_scheme', label: 'Skema Gaji', type: 'select', options: WAGE_SCHEMES, required: true },
        { key: 'base_rate', label: 'Rate / Base (Rp)', type: 'number',
          help: 'Untuk borongan pcs = Rp/pcs, borongan jam = Rp/jam, mingguan/bulanan = total Rp.' },
      ]}
      defaultItem={{ employee_code: '', name: '', department: '', job_title: 'Operator CMT-Sewing', manager_id: '', location_id: '', phone: '', contract_type: 'PKWT', contract_start_date: '', contract_end_date: '', wage_scheme: 'borongan_pcs', base_rate: 0 }}
    />
  );
}
