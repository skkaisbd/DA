import { useState, useEffect, useCallback } from 'react';
import { Plus, Edit2, Trash2, Users, Search, X, Eye, EyeOff } from 'lucide-react';
import PaginationLite, { useClientPagination } from '../ui/pagination-lite';

export default function BuyersModule({ token, userRole }) {
  const [buyers, setBuyers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [form, setForm] = useState({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' });
  const [search, setSearch] = useState('');
  const [showPw, setShowPw] = useState({});

  // RC-UI-03: search filter + client-side pagination (10/hal)
  const filteredBuyers = search
    ? buyers.filter(b => `${b.buyer_code || ''} ${b.buyer_name || ''} ${b.contact_person || ''} ${b.phone || ''} ${b.login_email || ''}`.toLowerCase().includes(search.toLowerCase()))
    : buyers;
  const { page, setPage, totalPages, total, paged } = useClientPagination(filteredBuyers, 10);

  const fetchBuyers = useCallback(async () => {
    setLoading(true);
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      const res = await fetch(`/api/buyers${params}`, { headers: { Authorization: `Bearer ${token}` } });
      setBuyers(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token, search]);

  useEffect(() => { fetchBuyers(); }, [fetchBuyers]);

  const handleSave = async () => {
    const method = editItem ? 'PUT' : 'POST';
    const url = editItem ? `/api/buyers/${editItem.id}` : '/api/buyers';
    try {
      const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(form)
      });
      if (res.ok) { fetchBuyers(); setShowForm(false); setEditItem(null); setForm({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' }); }
      else { const d = await res.json(); alert(d.detail || 'Error'); }
    } catch (e) { console.error(e); }
  };

  const handleEdit = (item) => {
    setEditItem(item);
    setForm({ buyer_code: item.buyer_code || '', buyer_name: item.buyer_name || '', contact_person: item.contact_person || '', phone: item.phone || '', address: item.address || '', email: item.email || '' });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus buyer ini? Akun portal buyer juga akan dihapus.')) return;
    await fetch(`/api/buyers/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    fetchBuyers();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Data Buyer</h2>
          <p className="text-muted-foreground text-sm mt-1">Kelola master data buyer — akun portal buyer otomatis dibuat</p>
        </div>
        <button onClick={() => { setShowForm(true); setEditItem(null); setForm({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' }); }}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-foreground rounded-lg text-sm font-medium hover:brightness-110 transition" data-testid="add-buyer-btn">
          <Plus className="w-4 h-4" /> Tambah Buyer
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-[var(--card-surface)] max-w-md">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari buyer..."
               className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="buyer-search" />
        {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-muted-foreground" /></button>}
      </div>

      {/* Table */}
      <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[var(--glass-bg)] border-b border-border">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Kode</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nama Buyer</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Contact</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Phone</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Email Login</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Password</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="7" className="text-center py-8 text-muted-foreground">Memuat...</td></tr>
            ) : filteredBuyers.length === 0 ? (
              <tr><td colSpan="7" className="text-center py-8 text-muted-foreground">Belum ada buyer</td></tr>
            ) : paged.map(b => (
              <tr key={b.id} className="border-b border-border hover:bg-[var(--glass-bg)]">
                <td className="px-4 py-3 font-medium text-foreground">{b.buyer_code || '-'}</td>
                <td className="px-4 py-3 font-medium">{b.buyer_name}</td>
                <td className="px-4 py-3">{b.contact_person || '-'}</td>
                <td className="px-4 py-3">{b.phone || '-'}</td>
                <td className="px-4 py-3 text-primary text-xs">{b.login_email || '-'}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-mono">{showPw[b.id] ? b.buyer_password_plain || '-' : '********'}</span>
                    <button onClick={() => setShowPw(p => ({...p, [b.id]: !p[b.id]}))} className="text-muted-foreground hover:text-muted-foreground">
                      {showPw[b.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleEdit(b)} className="p-1 hover:bg-[var(--glass-bg-hover)] rounded"><Edit2 className="w-4 h-4 text-muted-foreground" /></button>
                  {userRole === 'superadmin' && (
                    <button onClick={() => handleDelete(b.id)} className="p-1 hover:bg-red-50 rounded ml-1"><Trash2 className="w-4 h-4 text-red-700 dark:text-red-500" /></button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-3" />
      </div>

      {/* Modal Form */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-[var(--card-surface)] rounded-2xl shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-foreground mb-4">{editItem ? 'Edit Buyer' : 'Tambah Buyer'}</h3>
            <p className="text-sm text-muted-foreground mb-4">Akun portal buyer akan otomatis dibuat</p>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Kode Buyer *</label>
                <input value={form.buyer_code} onChange={e => setForm({...form, buyer_code: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="BYR-001" data-testid="buyer-code" />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Nama Buyer *</label>
                <input value={form.buyer_name} onChange={e => setForm({...form, buyer_name: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="PT Buyer Corp" data-testid="buyer-name" />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Contact Person</label>
                <input value={form.contact_person} onChange={e => setForm({...form, contact_person: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="John Doe" />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Telepon</label>
                <input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="08123456789" />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Alamat</label>
                <textarea value={form.address} onChange={e => setForm({...form, address: e.target.value})}
                          className="w-full border rounded-lg px-3 py-2 text-sm" rows="2" placeholder="Alamat lengkap..." />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2 border rounded-lg text-sm text-muted-foreground hover:bg-[var(--glass-bg)]">Batal</button>
              <button onClick={handleSave} disabled={!form.buyer_code || !form.buyer_name} className="flex-1 py-2 bg-primary text-foreground rounded-lg text-sm hover:brightness-110 disabled:opacity-50" data-testid="save-buyer-btn">Simpan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
