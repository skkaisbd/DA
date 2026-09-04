/**
 * VendorAccountsAdminModule — Admin kelola vendor CMT
 * Tab 1: Vendor Partners (entitas vendor)  — CRUD penuh (Tambah/Edit/Hapus)
 * Tab 2: Akun User Vendor (login credentials) — CRUD penuh (Tambah/Edit/Reset pw/Aktif/Hapus)
 * Tab 3: Semua Jobs lintas vendor — CRUD penuh (Buat/Edit/Hapus)
 */
import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  Users, Building2, Briefcase, Plus, Trash2, Pencil, KeyRound, Power,
  Loader2, RefreshCw, CheckCircle2, AlertCircle, ChevronDown, X, AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import ImportExportToolbar from './ImportExportToolbar';

const TABS = [
  { id: 'partners', label: 'Vendor Partner', icon: Building2 },
  { id: 'accounts', label: 'Akun Vendor', icon: Users },
  { id: 'jobs',     label: 'Semua Jobs', icon: Briefcase },
];

const JOB_STATUS_COLOR = {
  open:        'text-muted-foreground',
  in_progress: 'text-blue-600 dark:text-blue-400',
  done:        'text-green-700 dark:text-green-400',
  cancelled:   'text-red-700 dark:text-red-400',
};
const JOB_STATUS_OPTIONS = [
  { value: 'open',        label: 'Belum Mulai' },
  { value: 'in_progress', label: 'Berjalan' },
  { value: 'done',        label: 'Selesai' },
  { value: 'cancelled',   label: 'Dibatalkan' },
];

const INPUT_CLS = 'w-full px-3 py-2 rounded-lg bg-foreground/[0.08] border border-foreground/[0.15] text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50';

function Toast({ msg, type, onClose }) {
  return (
    <div className={`fixed top-5 right-5 z-[60] flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl border
      ${type==='ok' ? 'bg-green-100 dark:bg-green-500/20 border-green-400 dark:border-green-400/30 text-green-800 dark:text-green-200' : 'bg-red-100 dark:bg-red-500/20 border-red-400 dark:border-red-400/30 text-red-800 dark:text-red-200'}`}>
      {type==='ok' ? <CheckCircle2 className="w-5 h-5 shrink-0" /> : <AlertCircle className="w-5 h-5 shrink-0" />}
      <span className="text-sm font-medium">{msg}</span>
      <button onClick={onClose} className="ml-1"><X className="w-4 h-4" /></button>
    </div>
  );
}

// ── Reusable confirm dialog ────────────────────────────────────────────────────
function ConfirmDialog({ open, title, message, confirmLabel = 'Hapus', busy, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" data-testid="confirm-dialog">
      <div className="w-full max-w-md rounded-2xl bg-background border border-foreground/15 shadow-2xl p-5 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-500/15 flex items-center justify-center shrink-0">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h4 className="font-semibold text-foreground">{title}</h4>
            <p className="text-sm text-muted-foreground mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={busy} data-testid="confirm-cancel">Batal</Button>
          <Button size="sm" onClick={onConfirm} disabled={busy}
            className="bg-red-600 hover:bg-red-700 text-white" data-testid="confirm-ok">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Partners Tab ──────────────────────────────────────────────────────────────

function PartnersTab({ token, showToast }) {
  const [list,    setList]    = useState([]);
  const [loading, setLoading] = useState(true);
  const emptyForm = { name:'', code:'', contact_name:'', contact_phone:'', address:'', capacity_pcs:'', capacity_note:'' };
  const [form,    setForm]    = useState(emptyForm);
  const [editId,  setEditId]  = useState(null);      // null = create mode
  const [saving,  setSaving]  = useState(false);
  const [showForm,setShowForm]= useState(false);
  const [confirm, setConfirm] = useState(null);      // { partner } | null
  const [deleting,setDeleting]= useState(false);
  const [busyId,  setBusyId]  = useState(null);      // toggle active spinner
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await fetch('/api/vendor-portal/partners', { headers }); if (r.ok) setList(await r.json()); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); }, [load]);

  function openCreate() { setEditId(null); setForm(emptyForm); setShowForm(true); }
  function openEdit(p) {
    setEditId(p.id);
    setForm({ name:p.name||'', code:p.code||'', contact_name:p.contact_name||'', contact_phone:p.contact_phone||'', address:p.address||'', capacity_pcs:(p.capacity_pcs ?? '')===0?0:(p.capacity_pcs || ''), capacity_note:p.capacity_note||'' });
    setShowForm(true);
  }

  async function save(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const url = editId ? `/api/vendor-portal/partners/${editId}` : '/api/vendor-portal/partners';
      const method = editId ? 'PUT' : 'POST';
      const body = { ...form, capacity_pcs: form.capacity_pcs === '' ? null : Number(form.capacity_pcs) };
      const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal menyimpan.'); }
      showToast('ok', editId ? `Partner "${form.name}" diperbarui.` : `Partner "${form.name}" berhasil dibuat.`);
      setForm(emptyForm); setEditId(null); setShowForm(false); load();
    } catch(e) { showToast('err', e.message); }
    finally { setSaving(false); }
  }

  async function toggleActive(p) {
    setBusyId(p.id);
    try {
      let r;
      if (p.is_active === false) {
        // Reactivate via PUT is_active=true (I-VP-5)
        r = await fetch(`/api/vendor-portal/partners/${p.id}`, {
          method:'PUT', headers,
          body: JSON.stringify({ name:p.name||'', code:p.code||'', contact_name:p.contact_name||'',
                                 contact_phone:p.contact_phone||'', address:p.address||'', notes:p.notes||'', is_active:true }),
        });
      } else {
        // Soft deactivate via DELETE (guards: akun aktif / job berjalan)
        r = await fetch(`/api/vendor-portal/partners/${p.id}`, { method:'DELETE', headers });
      }
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal.'); }
      showToast('ok', p.is_active===false ? `Partner "${p.name}" diaktifkan.` : `Partner "${p.name}" dinonaktifkan.`);
      load();
    } catch(e) { showToast('err', e.message); }
    finally { setBusyId(null); }
  }

  async function doDelete() {
    if (!confirm?.partner) return;
    setDeleting(true);
    try {
      const r = await fetch(`/api/vendor-portal/partners/${confirm.partner.id}?hard=true`, { method:'DELETE', headers });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal menghapus.'); }
      showToast('ok', `Partner "${confirm.partner.name}" dihapus permanen.`);
      setConfirm(null); load();
    } catch(e) { showToast('err', e.message); }
    finally { setDeleting(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-foreground">Vendor Partner ({list.length})</h3>
        <div className="flex items-center gap-2">
          <ImportExportToolbar collectionKey="vendor_partners" label="Vendor CMT" onImported={load} />
          <Button size="sm" onClick={openCreate} data-testid="btn-add-partner">
            <Plus className="w-3.5 h-3.5 mr-1.5" /> Tambah Partner
          </Button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={save} className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3" data-testid="partner-form">
          <h4 className="text-sm font-semibold">{editId ? 'Edit Vendor' : 'Vendor Baru'}</h4>
          <div className="grid grid-cols-2 gap-3">
            {[['name','Nama Vendor *','text'],['code','Kode (opsional)','text'],
              ['contact_name','Nama Kontak','text'],['contact_phone','No. HP','tel']].map(([k,l,t]) => (
              <div key={k} className="space-y-1">
                <label className="text-[11px] text-muted-foreground uppercase font-semibold">{l}</label>
                <input type={t} value={form[k]} onChange={e=>setForm(p=>({...p,[k]:e.target.value}))}
                  data-testid={`partner-${k}`} className={INPUT_CLS} />
              </div>
            ))}
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-muted-foreground uppercase font-semibold">Alamat</label>
            <input value={form.address} onChange={e=>setForm(p=>({...p,address:e.target.value}))} className={INPUT_CLS} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Kapasitas Jahit (pcs)</label>
              <input type="number" min="0" value={form.capacity_pcs} onChange={e=>setForm(p=>({...p,capacity_pcs:e.target.value}))}
                data-testid="partner-capacity_pcs" className={INPUT_CLS} placeholder="mis. 200" />
              <p className="text-[10px] text-muted-foreground">Maksimum pcs yang bisa ditangani pada satu waktu (dipakai monitoring beban vs kapasitas).</p>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Catatan Kapasitas</label>
              <input value={form.capacity_note} onChange={e=>setForm(p=>({...p,capacity_note:e.target.value}))}
                data-testid="partner-capacity_note" className={INPUT_CLS} placeholder="mis. 2 lini jahit, kuat hoodie" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving} data-testid="partner-save">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : (editId ? 'Simpan Perubahan' : 'Simpan')}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={()=>{setShowForm(false);setEditId(null);}}>Batal</Button>
          </div>
        </form>
      )}

      {loading
        ? <div className="flex items-center justify-center py-8 gap-2 text-muted-foreground text-sm"><Loader2 className="w-4 h-4 animate-spin"/>Memuat...</div>
        : list.length === 0
          ? <p className="text-center py-8 text-sm text-muted-foreground">Belum ada vendor partner.</p>
          : (
            <div className="space-y-2" data-testid="partners-list">
              {list.map(p => (
                <div key={p.id} className="flex items-center gap-3 p-3 rounded-xl border border-foreground/10 bg-foreground/5">
                  <Building2 className="w-8 h-8 text-primary/60 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-foreground">{p.name}</span>
                      {p.code && <span className="text-[11px] text-primary/70 font-mono bg-primary/10 px-1.5 rounded">{p.code}</span>}
                    </div>
                    <p className="text-xs text-muted-foreground">{p.contact_name || '—'} · {p.contact_phone || '—'}</p>
                    <p className="text-xs text-muted-foreground/70">{p.job_count || 0} job · {p.account_count || 0} akun{(p.capacity_pcs > 0) ? ` · Kapasitas ${Number(p.capacity_pcs).toLocaleString('id-ID')} pcs` : ' · Kapasitas belum diisi'}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                    p.is_active !== false ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-300 dark:border-green-400/20' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-300 dark:border-red-400/20'
                  }`} data-testid={`partner-status-${p.id}`}>{p.is_active !== false ? 'Aktif' : 'Nonaktif'}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={()=>toggleActive(p)} title={p.is_active!==false ? 'Nonaktifkan' : 'Aktifkan'} disabled={busyId===p.id}
                      className="p-2 rounded-lg hover:bg-amber-500/10 text-muted-foreground hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                      data-testid={`partner-toggle-${p.id}`}>
                      {busyId===p.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Power className="w-4 h-4" />}
                    </button>
                    <button onClick={()=>openEdit(p)} title="Edit"
                      className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                      data-testid={`partner-edit-${p.id}`}>
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={()=>setConfirm({ partner:p })} title="Hapus permanen"
                      className="p-2 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 transition-colors"
                      data-testid={`partner-delete-${p.id}`}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
      }

      <ConfirmDialog
        open={!!confirm}
        title="Hapus Vendor Partner permanen?"
        message={confirm ? `Vendor "${confirm.partner.name}" akan dihapus permanen. Hanya bisa jika tidak punya job/akun apa pun. Untuk sekadar menonaktifkan, pakai tombol Power.` : ''}
        confirmLabel="Hapus permanen"
        busy={deleting}
        onConfirm={doDelete}
        onCancel={()=>setConfirm(null)}
      />
    </div>
  );
}

// ── Accounts Tab ──────────────────────────────────────────────────────────────

function AccountsTab({ token, showToast }) {
  const [list,     setList]     = useState([]);
  const [partners, setPartners] = useState([]);
  const [loading,  setLoading]  = useState(true);
  const emptyCreate = { email:'', name:'', password:'', partner_id:'' };
  const [form,     setForm]     = useState(emptyCreate);
  const [saving,   setSaving]   = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editAcc,  setEditAcc]  = useState(null);   // account being edited | null
  const [editForm, setEditForm] = useState({ name:'', partner_id:'', is_active:true, password:'' });
  const [savingEdit,setSavingEdit] = useState(false);
  const [confirm,  setConfirm]  = useState(null);   // { account } | null
  const [deleting, setDeleting] = useState(false);
  const [busyId,   setBusyId]   = useState(null);   // for toggle active spinner
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [accRes, parRes] = await Promise.all([
        fetch('/api/vendor-portal/accounts', { headers }),
        fetch('/api/vendor-portal/partners',  { headers }),
      ]);
      if (accRes.ok) setList(await accRes.json());
      if (parRes.ok) setPartners(await parRes.json());
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    if (!form.email || !form.name || !form.password || !form.partner_id) {
      showToast('err', 'Semua field wajib diisi.'); return;
    }
    setSaving(true);
    try {
      const r = await fetch('/api/vendor-portal/accounts', { method:'POST', headers, body: JSON.stringify(form) });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal membuat akun.'); }
      showToast('ok', `Akun vendor "${form.email}" berhasil dibuat.`);
      setForm(emptyCreate); setShowForm(false); load();
    } catch(e) { showToast('err', e.message); }
    finally { setSaving(false); }
  }

  function openEdit(u) {
    setEditAcc(u);
    setEditForm({ name:u.name||'', partner_id:u.cmt_vendor_id||'', is_active:u.is_active!==false, password:'' });
  }

  async function saveEdit(e) {
    e.preventDefault();
    if (!editForm.name.trim()) { showToast('err', 'Nama wajib diisi.'); return; }
    if (editForm.password && editForm.password.length < 6) { showToast('err', 'Password minimal 6 karakter.'); return; }
    setSavingEdit(true);
    try {
      const body = { name: editForm.name, partner_id: editForm.partner_id, is_active: editForm.is_active };
      if (editForm.password) body.password = editForm.password;
      const r = await fetch(`/api/vendor-portal/accounts/${editAcc.id}`, { method:'PUT', headers, body: JSON.stringify(body) });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal menyimpan.'); }
      const res = await r.json().catch(()=>({}));
      showToast('ok', res.password_reset ? 'Akun diperbarui + password direset.' : 'Akun diperbarui.');
      setEditAcc(null); load();
    } catch(e) { showToast('err', e.message); }
    finally { setSavingEdit(false); }
  }

  async function toggleActive(u) {
    setBusyId(u.id);
    try {
      const r = await fetch(`/api/vendor-portal/accounts/${u.id}`, { method:'PUT', headers, body: JSON.stringify({ is_active: u.is_active===false }) });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal.'); }
      showToast('ok', u.is_active===false ? 'Akun diaktifkan.' : 'Akun dinonaktifkan.');
      load();
    } catch(e) { showToast('err', e.message); }
    finally { setBusyId(null); }
  }

  async function doDelete() {
    if (!confirm?.account) return;
    setDeleting(true);
    try {
      const r = await fetch(`/api/vendor-portal/accounts/${confirm.account.id}?hard=true`, { method:'DELETE', headers });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal menghapus.'); }
      showToast('ok', `Akun "${confirm.account.email}" dihapus.`);
      setConfirm(null); load();
    } catch(e) { showToast('err', e.message); }
    finally { setDeleting(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-foreground">Akun Vendor ({list.length})</h3>
        <Button size="sm" onClick={() => setShowForm(!showForm)} data-testid="btn-add-account">
          <Plus className="w-3.5 h-3.5 mr-1.5" /> Tambah Akun
        </Button>
      </div>

      {showForm && (
        <form onSubmit={create} className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3" data-testid="account-form">
          <h4 className="text-sm font-semibold">Akun Vendor Baru</h4>
          <div className="space-y-1">
            <label className="text-[11px] text-muted-foreground uppercase font-semibold">Partner Vendor *</label>
            <div className="relative">
              <SmartNativeSelect value={form.partner_id} onChange={e=>setForm(p=>({...p,partner_id:e.target.value}))}
                data-testid="account-partner-select"
                className="w-full px-3 py-2 rounded-lg bg-foreground/[0.08] border border-foreground/[0.15] text-sm text-foreground appearance-none focus:outline-none focus:ring-2 focus:ring-primary/50">
                <option value="">— Pilih Partner —</option>
                {partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </SmartNativeSelect>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Nama Lengkap *</label>
              <input value={form.name} onChange={e=>setForm(p=>({...p,name:e.target.value}))} data-testid="account-name" className={INPUT_CLS} />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Email Login *</label>
              <input value={form.email} onChange={e=>setForm(p=>({...p,email:e.target.value}))} data-testid="account-email" className={INPUT_CLS} />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-muted-foreground uppercase font-semibold">Password *</label>
            <input type="password" value={form.password} onChange={e=>setForm(p=>({...p,password:e.target.value}))} data-testid="account-password" className={INPUT_CLS} />
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Buat Akun'}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={()=>setShowForm(false)}>Batal</Button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="flex justify-center py-8 gap-2 text-muted-foreground text-sm"><Loader2 className="w-4 h-4 animate-spin"/>Memuat...</div>
      ) : list.length === 0 ? (
        <p className="text-center py-8 text-sm text-muted-foreground">Belum ada akun vendor.</p>
      ) : (
        <div className="space-y-2" data-testid="accounts-list">
          {list.map(u => (
            <div key={u.id} className="flex items-center gap-3 p-3 rounded-xl border border-foreground/10 bg-foreground/5">
              <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center text-primary text-sm font-bold shrink-0">
                {u.name?.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm text-foreground">{u.name}</p>
                <p className="text-xs text-muted-foreground truncate">{u.email} · {u.partner_name}</p>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                u.is_active !== false ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-300 dark:border-green-400/20' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-300 dark:border-red-400/20'
              }`}>{u.is_active !== false ? 'Aktif' : 'Nonaktif'}</span>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={()=>toggleActive(u)} title={u.is_active!==false ? 'Nonaktifkan' : 'Aktifkan'} disabled={busyId===u.id}
                  className="p-2 rounded-lg hover:bg-amber-500/10 text-muted-foreground hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                  data-testid={`account-toggle-${u.id}`}>
                  {busyId===u.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Power className="w-4 h-4" />}
                </button>
                <button onClick={()=>openEdit(u)} title="Edit"
                  className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                  data-testid={`account-edit-${u.id}`}>
                  <Pencil className="w-4 h-4" />
                </button>
                <button onClick={()=>setConfirm({ account:u })} title="Hapus"
                  className="p-2 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 transition-colors"
                  data-testid={`account-delete-${u.id}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Edit account dialog */}
      {editAcc && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" data-testid="account-edit-dialog">
          <form onSubmit={saveEdit} className="w-full max-w-md rounded-2xl bg-background border border-foreground/15 shadow-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold text-foreground">Edit Akun Vendor</h4>
              <button type="button" onClick={()=>setEditAcc(null)}><X className="w-4 h-4 text-muted-foreground" /></button>
            </div>
            <p className="text-xs text-muted-foreground font-mono">{editAcc.email}</p>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Nama Lengkap *</label>
              <input value={editForm.name} onChange={e=>setEditForm(p=>({...p,name:e.target.value}))} data-testid="account-edit-name" className={INPUT_CLS} />
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold">Partner Vendor</label>
              <div className="relative">
                <SmartNativeSelect value={editForm.partner_id} onChange={e=>setEditForm(p=>({...p,partner_id:e.target.value}))}
                  data-testid="account-edit-partner"
                  className="w-full px-3 py-2 rounded-lg bg-foreground/[0.08] border border-foreground/[0.15] text-sm text-foreground appearance-none focus:outline-none focus:ring-2 focus:ring-primary/50">
                  <option value="">— Pilih Partner —</option>
                  {partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </SmartNativeSelect>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-[11px] text-muted-foreground uppercase font-semibold flex items-center gap-1"><KeyRound className="w-3 h-3" /> Reset Password (opsional)</label>
              <input type="password" value={editForm.password} onChange={e=>setEditForm(p=>({...p,password:e.target.value}))}
                placeholder="Kosongkan jika tidak diubah" data-testid="account-edit-password" className={INPUT_CLS} />
            </div>
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
              <input type="checkbox" checked={editForm.is_active} onChange={e=>setEditForm(p=>({...p,is_active:e.target.checked}))} data-testid="account-edit-active" className="w-4 h-4 accent-primary" />
              Akun aktif (bisa login)
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" size="sm" onClick={()=>setEditAcc(null)}>Batal</Button>
              <Button type="submit" size="sm" disabled={savingEdit} data-testid="account-edit-save">
                {savingEdit ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Simpan Perubahan'}
              </Button>
            </div>
          </form>
        </div>
      )}

      <ConfirmDialog
        open={!!confirm}
        title="Hapus Akun Vendor?"
        message={confirm ? `Akun "${confirm.account.email}" akan dihapus permanen dan tidak bisa login lagi.` : ''}
        busy={deleting}
        onConfirm={doDelete}
        onCancel={()=>setConfirm(null)}
      />
    </div>
  );
}

// ── Jobs Tab ──────────────────────────────────────────────────────────────────

function AllJobsTab({ token, showToast }) {
  const [jobs,    setJobs]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [partners, setPartners] = useState([]);
  const [models,   setModels]   = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [saving,   setSaving]   = useState(false);
  const emptyForm = { title: '', partner_id: '', model_id: '', qty_target: 0, process: 'SEWING', due_date: '', status: 'open' };
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState(null);
  const [confirm, setConfirm] = useState(null);   // { job } | null
  const [deleting, setDeleting] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jr, pr, mr] = await Promise.all([
        fetch('/api/vendor-portal/jobs', { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
        fetch('/api/vendor-portal/partners', { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
        fetch('/api/rahaza/models', { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
      ]);
      setJobs(jr || []); setPartners(pr || []); setModels((mr || []).filter(m => m.active !== false));
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); }, [load]);

  function openCreate() { setEditId(null); setForm(emptyForm); setShowForm(true); }
  function openEdit(j) {
    setEditId(j.id);
    setForm({ title:j.title||'', partner_id:j.partner_id||'', model_id:j.model_id||'', qty_target:j.qty_target||0, process:j.process||'SEWING', due_date:j.due_date||'', status:j.status||'open' });
    setShowForm(true);
  }

  const saveJob = async () => {
    if (!form.title || !form.partner_id) { showToast('err', 'Judul & vendor wajib diisi'); return; }
    setSaving(true);
    try {
      const url = editId ? `/api/vendor-portal/jobs/${editId}` : '/api/vendor-portal/jobs';
      const method = editId ? 'PUT' : 'POST';
      const body = { ...form, qty_target: Number(form.qty_target) || 0 };
      if (!editId) delete body.status;  // create menetapkan status default 'open'
      const r = await fetch(url, { method, headers, body: JSON.stringify(body) });
      if (!r.ok) { const e = await r.json().catch(() => ({})); showToast('err', e.detail || 'Gagal menyimpan job'); return; }
      showToast('ok', editId ? 'Job diperbarui' : 'Job dibuat');
      setForm(emptyForm); setEditId(null); setShowForm(false); load();
    } finally { setSaving(false); }
  };

  async function quickStatus(job, status) {
    try {
      const r = await fetch(`/api/vendor-portal/jobs/${job.id}`, { method:'PUT', headers, body: JSON.stringify({ status }) });
      if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail || 'Gagal'); }
      showToast('ok', 'Status job diperbarui');
      load();
    } catch(e) { showToast('err', e.message); }
  }

  async function doDelete() {
    if (!confirm?.job) return;
    setDeleting(true);
    try {
      const r = await fetch(`/api/vendor-portal/jobs/${confirm.job.id}`, { method:'DELETE', headers });
      if (!r.ok) { const er = await r.json().catch(()=>({})); throw new Error(er.detail || 'Gagal menghapus.'); }
      showToast('ok', `Job "${confirm.job.job_number}" dihapus.`);
      setConfirm(null); load();
    } catch(e) { showToast('err', e.message); }
    finally { setDeleting(false); }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-foreground">Semua Jobs ({jobs.length})</h3>
        <Button size="sm" onClick={openCreate} data-testid="job-create-toggle"><Plus className="w-4 h-4 mr-1" /> Buat Job</Button>
      </div>

      {showForm && (
        <div className="p-3 rounded-xl border border-primary/25 bg-primary/[0.04] space-y-2" data-testid="job-create-form">
          <h4 className="text-sm font-semibold">{editId ? 'Edit Job' : 'Job Baru'}</h4>
          <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
            placeholder="Judul job (cth: Jahit Sweater V-Neck 500 pcs)"
            className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground" data-testid="job-form-title" />
          <div className="grid grid-cols-2 gap-2">
            <SmartNativeSelect value={form.partner_id} onChange={e => setForm(p => ({ ...p, partner_id: e.target.value }))} data-testid="job-form-partner"
              className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground appearance-none">
              <option value="">— Pilih Vendor —</option>
              {partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </SmartNativeSelect>
            <SmartNativeSelect value={form.model_id} onChange={e => setForm(p => ({ ...p, model_id: e.target.value }))} data-testid="job-form-model"
              className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground appearance-none">
              <option value="">— Model (untuk Panduan Produksi) —</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.code} — {m.name}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <input type="number" value={form.qty_target} onChange={e => setForm(p => ({ ...p, qty_target: e.target.value }))}
              placeholder="Qty target" className="px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground" data-testid="job-form-qty" />
            <SmartNativeSelect value={form.process} onChange={e => setForm(p => ({ ...p, process: e.target.value }))} data-testid="job-form-process"
              className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground appearance-none">
              {['SEWING', 'FINISHING', 'QC', 'EMBROIDERY', 'CUTTING'].map(x => <option key={x} value={x}>{x}</option>)}
            </SmartNativeSelect>
            <input type="date" value={form.due_date} onChange={e => setForm(p => ({ ...p, due_date: e.target.value }))}
              className="px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground" data-testid="job-form-due" />
          </div>
          {editId && (
            <SmartNativeSelect value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value }))} data-testid="job-form-status"
              className="w-full px-3 py-2 rounded-lg bg-[var(--glass-bg)] border border-foreground/15 text-sm text-foreground appearance-none">
              {JOB_STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </SmartNativeSelect>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => {setShowForm(false);setEditId(null);}}>Batal</Button>
            <Button size="sm" onClick={saveJob} disabled={saving} data-testid="job-form-submit">{saving ? 'Menyimpan...' : (editId ? 'Simpan Perubahan' : 'Simpan Job')}</Button>
          </div>
        </div>
      )}

      {loading
        ? <div className="flex justify-center py-8 gap-2 text-muted-foreground text-sm"><Loader2 className="w-4 h-4 animate-spin"/>Memuat...</div>
        : jobs.length === 0
          ? <p className="text-center py-8 text-sm text-muted-foreground">Belum ada job.</p>
          : (
            <div className="space-y-2" data-testid="all-jobs-list">
              {jobs.map(j => {
                const pct = j.qty_target > 0 ? Math.round((j.qty_done || 0) / j.qty_target * 100) : 0;
                return (
                  <div key={j.id} className="p-3 rounded-xl border border-foreground/10 bg-foreground/5">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-xs text-primary">{j.job_number}</span>
                        <span className={`text-xs font-semibold ${JOB_STATUS_COLOR[j.status]}`}>
                          {j.status === 'open' ? 'Belum Mulai' : j.status === 'in_progress' ? 'Berjalan' : j.status === 'done' ? 'Selesai' : j.status === 'cancelled' ? 'Dibatalkan' : j.status}
                        </span>
                        {j.model_code && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary" data-testid={`job-model-${j.job_number}`}>{j.model_code}</span>}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-xs text-muted-foreground mr-1">{j.partner_name}</span>
                        <button onClick={()=>openEdit(j)} title="Edit"
                          className="p-1.5 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                          data-testid={`job-edit-${j.id}`}>
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={()=>setConfirm({ job:j })} title="Hapus"
                          className="p-1.5 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 transition-colors"
                          data-testid={`job-delete-${j.id}`}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="text-sm text-foreground mb-2">{j.title}</p>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                        <div className="h-full rounded-full bg-primary transition-all" style={{width:`${pct}%`}} />
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">{j.qty_done || 0}/{j.qty_target} pcs ({pct}%)</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )
      }

      <ConfirmDialog
        open={!!confirm}
        title="Hapus Job?"
        message={confirm ? `Job "${confirm.job.job_number} — ${confirm.job.title}" akan dihapus. Jika sudah ada laporan progress, hapus akan ditolak (batalkan job saja).` : ''}
        busy={deleting}
        onConfirm={doDelete}
        onCancel={()=>setConfirm(null)}
      />
    </div>
  );
}

// ── Main Admin Module ─────────────────────────────────────────────────────────

export default function VendorAccountsAdminModule({ token }) {
  const [tab,   setTab]   = useState('partners');
  const [toast, setToast] = useState(null);

  function showToast(type, msg) {
    // normalize: accept ('ok'|'err', msg)
    setToast({ type: type === 'ok' ? 'ok' : 'err', msg });
    setTimeout(() => setToast(null), 3500);
  }

  return (
    <div className="space-y-5 p-4 max-w-3xl mx-auto" data-testid="vendor-admin-module">
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={()=>setToast(null)} />}

      {/* Header */}
      <div className="flex items-center gap-2">
        <Users className="w-6 h-6 text-primary" />
        <div>
          <h1 className="text-xl font-bold text-foreground">Kelola Vendor CMT</h1>
          <p className="text-sm text-muted-foreground">Daftarkan vendor, buat akun login, dan pantau semua job — lengkap dengan Edit & Hapus.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-foreground/5 border border-foreground/10">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              data-testid={`tab-${t.id}`}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-all
                ${tab === t.id ? 'bg-primary text-white shadow' : 'text-muted-foreground hover:text-foreground hover:bg-foreground/5'}`}>
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {tab === 'partners' && <PartnersTab token={token} showToast={showToast} />}
      {tab === 'accounts' && <AccountsTab token={token} showToast={showToast} />}
      {tab === 'jobs'     && <AllJobsTab  token={token} showToast={showToast} />}
    </div>
  );
}
