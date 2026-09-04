
import { useState, useEffect } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Plus, Pencil, UserX, UserCheck, Trash2, Link as LinkIcon } from 'lucide-react';
import axios from 'axios';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import ImportExportToolbar from './ImportExportToolbar';

const SYSTEM_ROLES = ['admin', 'vendor', 'buyer', 'superadmin'];
const API = process.env.REACT_APP_BACKEND_URL;

export default function UserManagementModule({ token }) {
  const [users, setUsers] = useState([]);
  const [customRoles, setCustomRoles] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [buyersList, setBuyersList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'admin', status: 'active', vendor_id: '', buyer_id: '', customer_name: '' });
  const [showLinkModal, setShowLinkModal] = useState(null); // user to link
  const [linkEmployeeId, setLinkEmployeeId] = useState('');
  const [linkLoading, setLinkLoading] = useState(false);

  const headers = { Authorization: `Bearer ${token}` };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchUsers(); fetchRoles(); fetchVendors(); fetchBuyers(); fetchEmployees(); }, []);

  const fetchUsers = async () => {
    setLoading(true);
    const res = await fetch('/api/users', { headers });
    const data = await res.json();
    setUsers(Array.isArray(data) ? data : []);
    setLoading(false);
  };

  const fetchRoles = async () => {
    try {
      const res = await fetch('/api/roles', { headers });
      const data = await res.json();
      setCustomRoles(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const fetchVendors = async () => {
    try {
      const res = await fetch('/api/garments', { headers });
      const data = await res.json();
      setVendors(Array.isArray(data) ? data.filter(v => v.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  const fetchBuyers = async () => {
    try {
      const res = await fetch('/api/buyers', { headers });
      const data = await res.json();
      setBuyersList(Array.isArray(data) ? data.filter(b => b.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  const fetchEmployees = async () => {
    try {
      const { data } = await axios.get(`${API}/api/rahaza/employees`, { headers });
      setEmployees(Array.isArray(data) ? data : (data.items || data.rows || []));
    } catch (e) { console.error(e); }
  };

  const handleLinkEmployee = async () => {
    if (!showLinkModal) return;
    setLinkLoading(true);
    try {
      await axios.put(`${API}/api/rahaza/self/admin/link-employee`, {
        user_id: showLinkModal.id,
        employee_id: linkEmployeeId || null,
      }, { headers });
      setShowLinkModal(null);
      fetchUsers();
    } catch (e) {
      alert(e.response?.data?.detail || 'Gagal menghubungkan.');
    } finally { setLinkLoading(false); }
  };

  // All available roles: system + custom
  const allRoles = [...SYSTEM_ROLES, ...customRoles.map(r => r.name)];

  const openCreate = () => {
    setEditData(null);
    setForm({ name: '', email: '', password: '', role: 'admin', status: 'active', vendor_id: '', buyer_id: '', customer_name: '' });
    setShowModal(true);
  };

  const openEdit = (row) => {
    setEditData(row);
    setForm({ name: row.name, email: row.email, password: '', role: row.role, status: row.status, 
              vendor_id: row.vendor_id || '', buyer_id: row.buyer_id || '', customer_name: row.customer_name || '' });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = { ...form };
    if (editData && !payload.password) delete payload.password;
    // Set customer_name from buyer if buyer role
    if (payload.role === 'buyer' && payload.buyer_id) {
      const buyer = buyersList.find(b => b.id === payload.buyer_id);
      if (buyer) payload.customer_name = buyer.buyer_name;
    }
    const url = editData ? `/api/users/${editData.id}` : '/api/users';
    const method = editData ? 'PUT' : 'POST';
    await fetch(url, {
      method, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload)
    });
    setShowModal(false);
    fetchUsers();
  };

  const toggleStatus = async (row) => {
    const newStatus = row.status === 'active' ? 'inactive' : 'active';
    await fetch(`/api/users/${row.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ status: newStatus })
    });
    fetchUsers();
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    await fetch(`/api/users/${confirmDelete.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    setConfirmDelete(null);
    fetchUsers();
  };

  const roleColors = {
    superadmin: 'bg-purple-100 text-purple-700', admin: 'bg-primary/15 text-primary',
    vendor: 'bg-emerald-100 text-emerald-700', buyer: 'bg-amber-100 text-amber-700',
    production: 'bg-cyan-100 text-cyan-700', finance: 'bg-orange-100 text-orange-700',
    management: 'bg-secondary text-foreground',
  };

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  const columns = [
    { key: 'avatar', label: '', render: (_, row) => (
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-foreground text-sm font-bold ${
        row.role === 'vendor' ? 'bg-emerald-600' : row.role === 'buyer' ? 'bg-amber-600' : 'bg-primary'
      }`}>{row.name?.[0]?.toUpperCase()}</div>
    )},
    { key: 'name', label: 'Nama' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role', render: (v) => (
      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${roleColors[v] || 'bg-indigo-100 text-indigo-700'}`}>{v}</span>
    )},
    { key: 'vendor_id', label: 'Link', render: (v, row) => {
      if (row.role === 'vendor' && v) return <span className="text-xs text-emerald-600">Vendor: {v.substring(0, 8)}...</span>;
      if (row.role === 'buyer' && row.buyer_id) return <span className="text-xs text-amber-600">Buyer: {row.customer_name || row.buyer_id?.substring(0, 8)}</span>;
      return '-';
    }},
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    { key: 'created_at', label: 'Dibuat', render: (v) => formatDate(v) },
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      row.role !== 'superadmin' ? (
        <div className="flex items-center gap-1">
          <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-primary/10 text-primary" title="Edit"><Pencil className="w-4 h-4" /></button>
          <button onClick={() => toggleStatus(row)}
            className={`p-1.5 rounded ${row.status === 'active' ? 'hover:bg-amber-50 text-amber-700 dark:text-amber-500' : 'hover:bg-emerald-50 text-emerald-600'}`}
            title={row.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}>
            {row.status === 'active' ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
          </button>
          <button
            onClick={() => { setShowLinkModal(row); setLinkEmployeeId(row.employee_id || ''); }}
            className={`p-1.5 rounded hover:bg-blue-50 ${row.employee_id ? 'text-blue-600' : 'text-muted-foreground'}`}
            title={row.employee_id ? 'Terhubung ke karyawan' : 'Hubungkan ke karyawan'}>
            <LinkIcon className="w-4 h-4" />
          </button>
          <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-700 dark:text-red-500" title="Hapus"><Trash2 className="w-4 h-4" /></button>
        </div>
      ) : <span className="text-xs text-muted-foreground italic">Protected</span>
    )}
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Manajemen User</h1>
          <p className="text-muted-foreground text-sm mt-1">Kelola pengguna, role, dan hak akses sistem</p>
        </div>
        <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Mode Superadmin
        </span>
      </div>

      {/* Role Legend */}
      <div className="flex flex-wrap gap-2">
        {[...Object.entries(roleColors), ...customRoles.map(r => [r.name, 'bg-indigo-100 text-indigo-700'])].map(([role, color]) => (
          <span key={role} className={`px-3 py-1 rounded-full text-xs font-medium capitalize ${color}`}>{role}</span>
        ))}
      </div>

      <DataTable columns={columns} data={users} searchKeys={['name', 'email', 'role']}
        showExport={false}
        actions={
          <div className="flex items-center gap-2">
            <ImportExportToolbar collectionKey="users" label="Pengguna Sistem" onImported={fetchUsers} />
            <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110" data-testid="add-user-btn">
              <Plus className="w-4 h-4" /> Tambah User
            </button>
          </div>
        }
      />

      {showModal && (
        <Modal title={editData ? 'Edit User' : 'Tambah User'} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Nama Lengkap *</label>
              <input required className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                value={form.name} onChange={e => setForm({...form, name: e.target.value})} data-testid="user-name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Email *</label>
              <input required type="email" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                value={form.email} onChange={e => setForm({...form, email: e.target.value})} data-testid="user-email" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Password {editData && <span className="text-muted-foreground text-xs">(kosongkan jika tidak diubah)</span>}
              </label>
              <input type="password" className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                value={form.password} onChange={e => setForm({...form, password: e.target.value})}
                placeholder={editData ? '--------' : 'Minimal 6 karakter'} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Role *</label>
                <select className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={form.role} onChange={e => setForm({...form, role: e.target.value})} data-testid="user-role">
                  <optgroup label="System Roles">
                    {SYSTEM_ROLES.map(r => <option key={r} value={r} className="capitalize">{r}</option>)}
                  </optgroup>
                  {customRoles.length > 0 && (
                    <optgroup label="Custom Roles">
                      {customRoles.map(r => <option key={r.name} value={r.name}>{`${r.name} (${(r.permissions || []).length} perms)`}</option>)}
                    </optgroup>
                  )}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Status</label>
                <select className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
            </div>

            {/* Vendor link for vendor role */}
            {form.role === 'vendor' && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Link ke Vendor</label>
                <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={form.vendor_id} onChange={e => setForm({...form, vendor_id: e.target.value})}>
                  <option value="">— Pilih Vendor —</option>
                  {vendors.map(v => <option key={v.id} value={v.id}>{`${v.garment_name} (${v.garment_code})`}</option>)}
                </SmartNativeSelect>
              </div>
            )}

            {/* Buyer link for buyer role */}
            {form.role === 'buyer' && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Link ke Buyer</label>
                <SmartNativeSelect className="w-full border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  value={form.buyer_id} onChange={e => {
                    const buyer = buyersList.find(b => b.id === e.target.value);
                    setForm({...form, buyer_id: e.target.value, customer_name: buyer?.buyer_name || ''});
                  }}>
                  <option value="">— Pilih Buyer —</option>
                  {buyersList.map(b => <option key={b.id} value={b.id}>{`${b.buyer_name} (${b.buyer_code})`}</option>)}
                </SmartNativeSelect>
              </div>
            )}

            <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700">
              {form.role === 'vendor' && 'Catatan: Akun vendor biasanya dibuat otomatis dari Data Vendor/Garmen'}
              {form.role === 'buyer' && 'Catatan: Akun buyer biasanya dibuat otomatis dari Data Buyer'}
              {!['vendor', 'buyer'].includes(form.role) && `Password default: User@123 | Role: ${form.role}`}
            </div>

            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-primary text-foreground py-2 rounded-lg text-sm font-medium hover:brightness-110" data-testid="save-user-btn">
                {editData ? 'Simpan Perubahan' : 'Tambah User'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-border py-2 rounded-lg text-sm hover:bg-[var(--glass-bg)]">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus User?"
          message={`User "${confirmDelete.name}" (${confirmDelete.email}) akan dihapus permanen.`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {/* Link Employee Modal */}
      {showLinkModal && (
        <div className="fixed inset-0 bg-foreground/40 flex items-center justify-center z-50">
          <div className="bg-background rounded-xl p-6 max-w-sm w-full mx-4 shadow-xl">
            <h3 className="font-semibold text-lg mb-1">Hubungkan ke Karyawan</h3>
            <p className="text-sm text-muted-foreground mb-4">User: <strong>{showLinkModal.name}</strong></p>
            <label className="block text-sm font-medium mb-1">Pilih Karyawan</label>
            <SmartNativeSelect
              className="w-full border rounded-lg px-3 py-2 text-sm bg-background mb-4"
              value={linkEmployeeId}
              onChange={e => setLinkEmployeeId(e.target.value)}
            >
              <option value="">— Tidak terhubung —</option>
              {employees.map(emp => (
                <option key={emp.id} value={emp.id}>
                  {emp.employee_code} — {emp.name} ({emp.job_title})
                </option>
              ))}
            </SmartNativeSelect>
            <div className="flex gap-2">
              <button
                onClick={handleLinkEmployee}
                disabled={linkLoading}
                className="flex-1 bg-primary text-foreground py-2 rounded-lg text-sm font-medium hover:brightness-110 disabled:opacity-50"
              >
                {linkLoading ? 'Menyimpan...' : 'Simpan'}
              </button>
              <button
                onClick={() => setShowLinkModal(null)}
                className="flex-1 border py-2 rounded-lg text-sm hover:bg-muted"
              >
                Batal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
