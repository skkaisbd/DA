/**
 * KOL & Creator Management Module (Phase 5)
 * Admin view: Daftar Creator, Performa Live, Catalog & Requests, Leaderboard
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Users, Video, ShoppingBag, Trophy, Plus, Edit2, Trash2, Check, X, RefreshCw,
  ChevronDown, Star, TrendingUp, Eye, Package, Search, Filter, Target, Award,
  UserPlus, Settings, ExternalLink, BarChart2, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import PaginationBar from './PaginationBar';
import CreatorIncentivePanel from './marketing/CreatorIncentivePanel';
import CreatorWeeklyReportPanel from './marketing/CreatorWeeklyReportPanel';
import { AccountBadge, getPlatformConfig } from './marketing/AccountBadge';
import { ActiveAccountBar } from './marketing/ActiveAccountBar';
import { useActiveMarketingAccount } from '@/hooks/useActiveMarketingAccount';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── helpers ─────────────────────────────────────────────────────────────────
const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const fmtRp = (n) => `Rp ${fmt(n)}`;

const PLATFORM_COLORS = {
  shopee: 'bg-orange-100 dark:bg-orange-500/20 text-orange-600 dark:text-orange-400 border-orange-400 dark:border-orange-500/30',
  tiktokshop: 'bg-black/30 text-pink-600 dark:text-pink-400 border-pink-400 dark:border-pink-500/30',
  tokopedia: 'bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 border-green-400 dark:border-green-500/30',
};

const STATUS_BADGE = {
  active: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30',
  inactive: 'bg-muted dark:bg-zinc-500/20 text-muted-foreground dark:text-zinc-400 border-border dark:border-zinc-500/30',
  pending: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 border-amber-400 dark:border-amber-500/30',
  approved: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-400 dark:border-emerald-500/30',
  rejected: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border-red-400 dark:border-red-500/30',
};

function Badge({ cls, children }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {children}
    </span>
  );
}

function KPIBar({ label, value, target, unit = '' }) {
  const pct = target ? Math.min(100, Math.round((value / target) * 100)) : 0;
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-foreground font-medium">{unit}{fmt(value)} / {unit}{fmt(target)} ({pct}%)</span>
      </div>
      <div className="h-1.5 rounded-full bg-foreground/10">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Creator Form Modal ───────────────────────────────────────────────────────
function CreatorFormModal({ token, accounts, onClose, onSaved, editCreator }) {
  const isEdit = !!editCreator;
  const [form, setForm] = useState({
    name: editCreator?.name || '',
    creator_code: editCreator?.creator_code || '',
    login_email: editCreator?.login_email || '',
    login_password: '',
    // SESI #34 — tipe kreator & domisili. Kreator tipe `new` BELUM punya akun
    // portal: pemilik menegaskan datanya diinput manual dari portal marketing,
    // jadi email/password boleh kosong untuk tipe ini.
    creator_type: editCreator?.creator_type || 'new',
    domicile: editCreator?.domicile || '',
    domicile_detail: editCreator?.domicile_detail || '',
    phone: editCreator?.phone || '',
    platforms: editCreator?.platforms || {},
    assigned_account_ids: editCreator?.assigned_account_ids || [],
    kpi_targets: editCreator?.kpi_targets || { monthly_revenue: 0, monthly_sessions: 0, monthly_viewers: 0 },
    notes: editCreator?.notes || '',
  });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setKpi = (k, v) => setForm(f => ({ ...f, kpi_targets: { ...f.kpi_targets, [k]: Number(v) } }));
  const setPlatform = (k, v) => setForm(f => ({ ...f, platforms: { ...f.platforms, [k]: v } }));

  const toggleAccount = (id) => {
    const ids = form.assigned_account_ids.includes(id)
      ? form.assigned_account_ids.filter(x => x !== id)
      : [...form.assigned_account_ids, id];
    set('assigned_account_ids', ids);
  };

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name || !form.creator_code) {
      toast.error('Nama dan kode creator wajib diisi');
      return;
    }
    // Akun portal hanya wajib untuk kreator kontrak/continue. Tipe `new` sengaja
    // boleh tanpa akun (keputusan pemilik) — tetapi kalau emailnya diisi,
    // passwordnya harus ada, kalau tidak akunnya mustahil dipakai login.
    if (form.creator_type !== 'new' && !form.login_email) {
      toast.error('Kreator kontrak/continue butuh email login untuk akses portal');
      return;
    }
    if (!isEdit && form.login_email && !form.login_password) {
      toast.error('Email diisi — password wajib minimal 6 karakter');
      return;
    }
    setSaving(true);
    try {
      const url = isEdit ? `${API}/api/marketing/kol/creators/${editCreator.id}` : `${API}/api/marketing/kol/creators`;
      const method = isEdit ? 'PUT' : 'POST';
      const body = { ...form };
      if (isEdit && !body.login_password) delete body.login_password;
      const r = await fetch(url, { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      toast.success(isEdit ? 'Creator diupdate' : 'Creator berhasil dibuat');
      onSaved();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center p-4 overflow-auto">
      <div className="bg-[hsl(var(--card))] border border-foreground/10 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-auto">
        <div className="p-6 border-b border-foreground/10 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{isEdit ? 'Edit Creator' : 'Tambah Creator Baru'}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={20} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Nama Creator *</label>
              <input data-testid="creator-name-input" value={form.name} onChange={e => set('name', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="Ayu Dewi" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Kode Creator *</label>
              <input data-testid="creator-code-input" value={form.creator_code} onChange={e => set('creator_code', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="KOL-001" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Tipe Kreator *</label>
              <select data-testid="creator-type-select" value={form.creator_type}
                onChange={e => set('creator_type', e.target.value)}
                className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm">
                <option value="new">Kreator New (tanpa akun portal)</option>
                <option value="kontrak">Kreator Kontrak (dapat insentif)</option>
                <option value="continue">Kreator Continue (dapat insentif)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Domisili (Kota/Kab.)</label>
              <input data-testid="creator-domicile-input" value={form.domicile}
                onChange={e => set('domicile', e.target.value)}
                className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm"
                placeholder="Bandung" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Alamat Domisili</label>
              <input data-testid="creator-domicile-detail-input" value={form.domicile_detail}
                onChange={e => set('domicile_detail', e.target.value)}
                className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm"
                placeholder="Kec. Coblong, Jl. ..." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Email Login {form.creator_type === 'new' ? '(opsional)' : '*'}
              </label>
              <input data-testid="creator-email-input" type="email" value={form.login_email} onChange={e => set('login_email', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="creator@email.com" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">{isEdit ? 'Password Baru (kosongkan jika tidak diubah)' : 'Password *'}</label>
              <input data-testid="creator-password-input" type="password" value={form.login_password} onChange={e => set('login_password', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="Min 6 karakter" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">No. HP</label>
              <input value={form.phone} onChange={e => set('phone', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="08..." />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">TikTok Handle</label>
              <input value={form.platforms?.tiktok || ''} onChange={e => setPlatform('tiktok', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="@handle" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Shopee Handle</label>
              <input value={form.platforms?.shopee || ''} onChange={e => setPlatform('shopee', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="nama_toko" />
            </div>
          </div>
          {/* KPI Targets */}
          <div>
            <label className="block text-sm font-medium mb-2">Target KPI Bulanan</label>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Revenue (Rp)</label>
                <input type="number" value={form.kpi_targets.monthly_revenue} onChange={e => setKpi('monthly_revenue', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="50000000" />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Sesi Live</label>
                <input type="number" value={form.kpi_targets.monthly_sessions} onChange={e => setKpi('monthly_sessions', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="12" />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Total Penonton</label>
                <input type="number" value={form.kpi_targets.monthly_viewers} onChange={e => setKpi('monthly_viewers', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="80000" />
              </div>
            </div>
          </div>
          {/* Assign Accounts */}
          <div>
            <label className="block text-sm font-medium mb-2">Assign ke Akun</label>
            <div className="flex flex-wrap gap-2">
              {accounts.map(acc => (
                <button
                  key={acc.id}
                  type="button"
                  onClick={() => toggleAccount(acc.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs border transition-all ${
                    form.assigned_account_ids.includes(acc.id)
                      ? 'bg-violet-500/30 border-violet-400 text-violet-600 dark:text-violet-300'
                      : 'bg-foreground/5 border-foreground/10 text-muted-foreground hover:border-foreground/20'
                  }`}
                >
                  {acc.account_name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">Catatan</label>
            <textarea value={form.notes} onChange={e => set('notes', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm resize-none" rows={2} placeholder="Catatan tambahan..." />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-foreground/10 text-sm hover:bg-foreground/5 transition-colors">Batal</button>
            <button data-testid="save-creator-btn" type="submit" disabled={saving} className="flex-1 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium transition-colors disabled:opacity-50">
              {saving ? 'Menyimpan...' : isEdit ? 'Simpan Perubahan' : 'Buat Creator'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Session Form Modal ───────────────────────────────────────────────────────
function SessionFormModal({ token, creators, accounts, onClose, onSaved }) {
  const [form, setForm] = useState({
    creator_id: '', account_id: '', date: new Date().toISOString().split('T')[0],
    platform: 'tiktokshop', session_name: '', duration_minutes: 90,
    viewers: 0, peak_viewers: 0, revenue: 0, orders: 0, notes: '',
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  // Filter akun hanya ke yang di-assign ke creator yang dipilih
  const selectedCreator = creators.find(c => c.id === form.creator_id);
  const assignedIds = selectedCreator?.assigned_account_ids || [];
  const availableAccounts = assignedIds.length > 0
    ? accounts.filter(a => assignedIds.includes(a.id))
    : accounts;

  // Auto-clear account jika tidak lagi tersedia setelah creator berganti
  useEffect(() => {
    if (form.account_id && availableAccounts.length > 0 &&
        !availableAccounts.find(a => a.id === form.account_id)) {
      set('account_id', '');
    }
  }, [form.creator_id]); // eslint-disable-line

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.creator_id || !form.account_id) { toast.error('Pilih creator dan akun'); return; }
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/marketing/kol/sessions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, viewers: Number(form.viewers), peak_viewers: Number(form.peak_viewers), revenue: Number(form.revenue), orders: Number(form.orders), duration_minutes: Number(form.duration_minutes) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      toast.success('Sesi berhasil dicatat');
      onSaved();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center p-4 overflow-auto">
      <div className="bg-[hsl(var(--card))] border border-foreground/10 rounded-2xl w-full max-w-lg">
        <div className="p-5 border-b border-foreground/10 flex items-center justify-between">
          <h2 className="text-base font-semibold">Catat Sesi Live</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Creator *</label>
              <SmartNativeSelect value={form.creator_id} onChange={e => set('creator_id', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm">
                <option value="">Pilih Creator</option>
                {creators.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Akun *</label>
              <SmartNativeSelect value={form.account_id} onChange={e => set('account_id', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm">
                <option value="">Pilih Akun</option>
                {availableAccounts.map(a => {
                  const cfg = getPlatformConfig(a.platform);
                  return <option key={a.id} value={a.id}>{cfg.icon} {a.account_name} ({cfg.label})</option>;
                })}
              </SmartNativeSelect>
              {form.creator_id && assignedIds.length === 0 && (
                <p className="text-[10px] text-amber-700 dark:text-amber-400 mt-1">Creator belum di-assign ke akun manapun</p>
              )}
              {form.account_id && availableAccounts.find(a => a.id === form.account_id) && (() => {
                const acc = availableAccounts.find(a => a.id === form.account_id);
                const cfg = getPlatformConfig(acc.platform);
                return (
                  <div className={`mt-1.5 flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-medium ${cfg.bg} ${cfg.border} ${cfg.text}`}>
                    {cfg.icon} Input ke: {acc.account_name}
                  </div>
                );
              })()}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Tanggal</label>
              <input type="date" value={form.date} onChange={e => set('date', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Platform</label>
              <select value={form.platform} onChange={e => set('platform', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm">
                <option value="tiktokshop">TikTok Shop</option>
                <option value="shopee">Shopee Live</option>
                <option value="tokopedia">Tokopedia</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Durasi (menit)</label>
              <input type="number" value={form.duration_minutes} onChange={e => set('duration_minutes', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5">Nama Sesi</label>
            <input value={form.session_name} onChange={e => set('session_name', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="Live Sesi Malam" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Revenue (Rp)</label>
              <input type="number" value={form.revenue} onChange={e => set('revenue', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Orders</label>
              <input type="number" value={form.orders} onChange={e => set('orders', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Penonton</label>
              <input type="number" value={form.viewers} onChange={e => set('viewers', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Peak Penonton</label>
              <input type="number" value={form.peak_viewers} onChange={e => set('peak_viewers', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-foreground/10 text-sm hover:bg-foreground/5">Batal</button>
            <button data-testid="save-session-btn" type="submit" disabled={saving} className="flex-1 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium disabled:opacity-50">
              {saving ? 'Menyimpan...' : 'Catat Sesi'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Catalog Form Modal ───────────────────────────────────────────────────────
function CatalogFormModal({ token, accounts, onClose, onSaved }) {
  const [form, setForm] = useState({ account_id: '', fg_product_id: '', product_name: '', sku: '', category: '', unit_price: 0, description: '', is_active: true });
  const [fgSearch, setFgSearch] = useState('');
  const [fgProducts, setFgProducts] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!fgSearch) return;
      try {
        const r = await fetch(`${API}/api/marketing/kol/fg-products?search=${encodeURIComponent(fgSearch)}`, { headers: { Authorization: `Bearer ${token}` } });
        const d = await r.json();
        setFgProducts(Array.isArray(d) ? d : []);
      } catch { setFgProducts([]); }
    }, 400);
    return () => clearTimeout(t);
  }, [fgSearch, token]);

  function selectFg(p) {
    set('fg_product_id', p.id);
    set('product_name', p.name || p.code);
    set('sku', p.code || '');
    setFgSearch(p.name || p.code);
    setFgProducts([]);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.account_id || !form.product_name || !form.sku) { toast.error('Akun, nama produk, dan SKU wajib diisi'); return; }
    setSaving(true);
    try {
      const r = await fetch(`${API}/api/marketing/kol/catalog`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, unit_price: Number(form.unit_price) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal menyimpan');
      toast.success('Produk ditambahkan ke katalog');
      onSaved();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-foreground/60 z-50 flex items-center justify-center p-4">
      <div className="bg-[hsl(var(--card))] border border-foreground/10 rounded-2xl w-full max-w-lg">
        <div className="p-5 border-b border-foreground/10 flex items-center justify-between">
          <h2 className="text-base font-semibold">Tambah Produk ke Katalog</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5">Akun *</label>
            <SmartNativeSelect value={form.account_id} onChange={e => set('account_id', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm">
              <option value="">Pilih Akun</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.account_name}</option>)}
            </SmartNativeSelect>
          </div>
          <div className="relative">
            <label className="block text-xs font-medium mb-1.5">Cari Produk FG (dari Produksi)</label>
            <input
              value={fgSearch}
              onChange={e => setFgSearch(e.target.value)}
              className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm"
              placeholder="Ketik nama/kode produk jadi..."
            />
            {fgProducts.length > 0 && (
              <div className="absolute top-full left-0 right-0 bg-[hsl(var(--card))] border border-foreground/10 rounded-lg mt-1 z-10 max-h-40 overflow-auto">
                {fgProducts.map(p => (
                  <button key={p.id} type="button" onClick={() => selectFg(p)} className="w-full text-left px-3 py-2 text-sm hover:bg-foreground/5 flex items-center justify-between">
                    <span>{p.name} ({p.code})</span>
                    <span className="text-xs text-emerald-600 dark:text-emerald-400">{fmt(p.stock_qty)} pcs</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Nama Produk *</label>
              <input value={form.product_name} onChange={e => set('product_name', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="Kemeja Batik Modern" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">SKU *</label>
              <input value={form.sku} onChange={e => set('sku', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="SKU-001" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1.5">Kategori</label>
              <input value={form.category} onChange={e => set('category', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" placeholder="Kemeja, Celana, dll" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5">Harga (Rp)</label>
              <input type="number" value={form.unit_price} onChange={e => set('unit_price', e.target.value)} className="w-full bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-foreground/10 text-sm hover:bg-foreground/5">Batal</button>
            <button data-testid="save-catalog-btn" type="submit" disabled={saving} className="flex-1 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium disabled:opacity-50">
              {saving ? 'Menyimpan...' : 'Tambah ke Katalog'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN MODULE
// ══════════════════════════════════════════════════════════════════════════════
export default function KOLCreatorModule({ token }) {
  const [tab, setTab] = useState('creators');
  const [creators, setCreators] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [requests, setRequests] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const { activeAccount: activeAccountCtx, setActiveAccount: setActiveAccountCtx } = useActiveMarketingAccount();
  const filterAccountId = activeAccountCtx?.id || '';
  const setFilterAccountId = (id) => {
    const acc = accounts.find(a => a.id === id);
    setActiveAccountCtx(acc || null);
  };
  const [showCreatorForm, setShowCreatorForm] = useState(false);
  const [editCreator, setEditCreator] = useState(null);
  // SESI #34 — insentif per kreator (konfigurasi + tracker pcs) & pembuatan akun
  // portal untuk kreator yang belum punya (penyebab "tidak bisa login").
  const [incentiveCreator, setIncentiveCreator] = useState(null);
  const [showSessionForm, setShowSessionForm] = useState(false);
  const [showCatalogForm, setShowCatalogForm] = useState(false);
  const [leaderMonth, setLeaderMonth] = useState(new Date().toISOString().slice(0, 7));
  // Per-month creator targets: { creator_id → target doc }
  const [creatorTargets, setCreatorTargets] = useState({});

  // Pagination state
  const [creatorPage, setCreatorPage] = useState(1);
  const [creatorPagination, setCreatorPagination] = useState(null);
  const [requestPage, setRequestPage] = useState(1);
  const [requestPagination, setRequestPagination] = useState(null);
  const ITEMS_PER_PAGE = 10;

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const load = useCallback(async () => {
    setLoading(true);
    const now = new Date();
    const cy = now.getFullYear(), cm = now.getMonth() + 1;
    try {
      const [crRes, ac, sess, reqs, cat, lb, tgtsRaw] = await Promise.all([
        fetch(`${API}/api/marketing/kol/creators?page=${creatorPage}&limit=${ITEMS_PER_PAGE}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/accounts`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/kol/sessions`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/kol/requests?page=${requestPage}&limit=${ITEMS_PER_PAGE}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/kol/catalog`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/kol/leaderboard?month=${leaderMonth}`, { headers }).then(r => r.json()),
        fetch(`${API}/api/marketing/targets/creator?year=${cy}&month=${cm}`, { headers }).then(r => r.ok ? r.json() : []),
      ]);
      // Handle paginated creators response
      if (crRes?.creators) {
        setCreators(crRes.creators);
        setCreatorPagination(crRes.pagination || null);
      } else {
        setCreators(Array.isArray(crRes) ? crRes : []);
        setCreatorPagination(null);
      }
      // Handle paginated requests response
      if (reqs?.requests) {
        setRequests(reqs.requests);
        setRequestPagination(reqs.pagination || null);
      } else {
        setRequests(Array.isArray(reqs) ? reqs : []);
        setRequestPagination(null);
      }
      setAccounts(Array.isArray(ac) ? ac.filter(a => a.status === 'active') : []);
      setSessions(Array.isArray(sess) ? sess : []);
      setCatalog(Array.isArray(cat) ? cat : []);
      setLeaderboard(lb?.leaderboard || []);
      // Build creator targets map: { creator_id → target }
      const tMap = {};
      if (Array.isArray(tgtsRaw)) tgtsRaw.forEach(t => { tMap[t.creator_id] = t; });
      setCreatorTargets(tMap);
    } catch (err) { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  }, [headers, leaderMonth, creatorPage, requestPage]);

  useEffect(() => { load(); }, [load]);

  async function seedDemo() {
    try {
      const r = await fetch(`${API}/api/marketing/kol/seed-demo`, { method: 'POST', headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail);
      toast.success(`Demo seeded: ${d.creators_created} creators, ${d.sessions_created} sessions`);
      load();
    } catch (err) { toast.error(err.message); }
  }

  async function handleApproveRequest(id) {
    try {
      const r = await fetch(`${API}/api/marketing/kol/requests/${id}/approve`, { method: 'POST', headers });
      if (!r.ok) throw new Error((await r.json()).detail);
      toast.success('Request disetujui');
      load();
    } catch (err) { toast.error(err.message); }
  }

  async function handleRejectRequest(id) {
    const reason = prompt('Alasan penolakan:');
    if (!reason) return;
    try {
      const r = await fetch(`${API}/api/marketing/kol/requests/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST', headers });
      if (!r.ok) throw new Error((await r.json()).detail);
      toast.success('Request ditolak');
      load();
    } catch (err) { toast.error(err.message); }
  }

  async function handleDeleteSession(id) {
    if (!confirm('Hapus sesi ini?')) return;
    try {
      const r = await fetch(`${API}/api/marketing/kol/sessions/${id}`, { method: 'DELETE', headers });
      if (!r.ok) throw new Error((await r.json()).detail);
      toast.success('Sesi dihapus');
      load();
    } catch (err) { toast.error(err.message); }
  }

  async function handleDeactivateCreator(id) {
    if (!confirm('Nonaktifkan creator ini?')) return;
    try {
      const r = await fetch(`${API}/api/marketing/kol/creators/${id}`, { method: 'DELETE', headers });
      if (!r.ok) throw new Error((await r.json()).detail);
      toast.success('Creator dinonaktifkan');
      load();
    } catch (err) { toast.error(err.message); }
  }

  async function handleRemoveCatalog(id) {
    if (!confirm('Hapus produk dari katalog?')) return;
    try {
      const r = await fetch(`${API}/api/marketing/kol/catalog/${id}`, { method: 'DELETE', headers });
      if (!r.ok) throw new Error((await r.json()).detail);
      toast.success('Produk dinonaktifkan dari katalog');
      load();
    } catch (err) { toast.error(err.message); }
  }

  const filteredCreators = creators.filter(c => {
    const matchSearch = !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.creator_code.toLowerCase().includes(search.toLowerCase());
    const matchStatus = !filterStatus || c.status === filterStatus;
    const matchAccount = !filterAccountId || (c.assigned_account_ids || []).includes(filterAccountId);
    return matchSearch && matchStatus && matchAccount;
  });

  const pendingRequests = requests.filter(r => r.status === 'pending');
  const TABS = [
    { id: 'creators', label: 'Daftar Creator', icon: Users },
    { id: 'performance', label: 'Performa Live', icon: Video },
    { id: 'catalog', label: 'Katalog & Request', icon: ShoppingBag, badge: pendingRequests.length || null },
    { id: 'leaderboard', label: 'Leaderboard', icon: Trophy },
    { id: 'weekly', label: 'Rapor Mingguan', icon: BarChart2 },
  ];

  const { page, setPage, totalPages, total, paged } = useClientPagination(sessions, 10);
  return (
    <div data-testid="kol-creator-module" className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">KOL & Creator Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Kelola creator, performa live, dan permintaan produk
          </p>
        </div>
        <div className="flex gap-2">
          <button
            data-testid="seed-demo-btn"
            onClick={seedDemo}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-foreground/10 text-sm hover:bg-foreground/5 transition-colors"
          >
            <RefreshCw size={14} />
            Seed Demo
          </button>
          {tab === 'creators' && (
            <button
              data-testid="add-creator-btn"
              onClick={() => { setEditCreator(null); setShowCreatorForm(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium transition-colors"
            >
              <UserPlus size={16} />
              Tambah Creator
            </button>
          )}
          {tab === 'performance' && (
            <button
              data-testid="add-session-btn"
              onClick={() => setShowSessionForm(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium transition-colors"
            >
              <Plus size={16} />
              Catat Sesi
            </button>
          )}
          {tab === 'catalog' && (
            <button
              data-testid="add-catalog-btn"
              onClick={() => setShowCatalogForm(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-sm font-medium transition-colors"
            >
              <Plus size={16} />
              Tambah Produk
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-foreground/5 rounded-xl w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === t.id ? 'bg-violet-600 text-foreground shadow-lg' : 'text-muted-foreground hover:text-foreground hover:bg-foreground/5'
            }`}
          >
            <t.icon size={15} />
            {t.label}
            {t.badge ? (
              <span className="absolute -top-1 -right-1 bg-amber-500 text-foreground text-xs rounded-full w-4 h-4 flex items-center justify-center">
                {t.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {loading && <div className="text-center py-12 text-muted-foreground">Memuat data...</div>}

      {/* ═══ TAB: CREATORS ═══ */}
      {!loading && tab === 'creators' && (
        <div className="space-y-4">
          {/* Active Account Bar */}
          <ActiveAccountBar
            accounts={accounts}
            activeAccount={accounts.find(a => a.id === filterAccountId) || null}
            onAccountChange={(acc) => setFilterAccountId(acc ? acc.id : '')}
            hint="Filter creator by akun:"
          />

          {/* Filters */}
          <div className="flex gap-3 flex-wrap">
            <div className="relative flex-1 max-w-xs">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                data-testid="creator-search"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-foreground/5 border border-foreground/10 rounded-lg pl-9 pr-3 py-2 text-sm"
                placeholder="Cari creator..."
              />
            </div>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              className="bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Semua Status</option>
              <option value="active">Aktif</option>
              <option value="inactive">Nonaktif</option>
            </select>
          </div>

          {filteredCreators.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Users className="mx-auto mb-3 opacity-30" size={40} />
              <p className="text-sm">Belum ada creator. Klik "Tambah Creator" atau "Seed Demo" untuk memulai.</p>
            </div>
          ) : (
            <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {filteredCreators.map(creator => (
                <div
                  key={creator.id}
                  data-testid="creator-card"
                  className="bg-foreground/[0.03] border border-foreground/[0.08] rounded-2xl p-5 hover:border-violet-400 dark:border-violet-500/30 transition-all group"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center text-foreground font-bold text-sm">
                        {creator.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-semibold text-sm">{creator.name}</div>
                        <div className="text-xs text-muted-foreground">{creator.creator_code}</div>
                      </div>
                    </div>
                    <Badge cls={STATUS_BADGE[creator.status]}>{creator.status}</Badge>
                  </div>

                  {/* Platform handles */}
                  <div className="flex gap-1.5 flex-wrap mb-2">
                    {Object.entries(creator.platforms || {}).filter(([, v]) => v).map(([k, v]) => (
                      <span key={k} className="text-xs bg-foreground/5 border border-foreground/10 rounded px-2 py-0.5 text-muted-foreground">
                        {k}: {v}
                      </span>
                    ))}
                  </div>

                  {/* Assigned accounts badges */}
                  <div className="flex gap-1 flex-wrap mb-3">
                    {(creator.assigned_account_ids || []).length > 0 ? (
                      creator.assigned_account_ids.map(id => {
                        const acc = accounts.find(a => a.id === id);
                        return acc ? <AccountBadge key={id} account={acc} size="xs" /> : null;
                      })
                    ) : (
                      <span className="text-[10px] text-muted-foreground italic px-1">Belum di-assign ke akun</span>
                    )}
                  </div>

                  {/* This month stats */}
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="bg-foreground/5 rounded-lg p-2 text-center">
                      <div className="text-xs text-muted-foreground">Sesi</div>
                      <div className="font-bold text-sm">{creator.this_month?.sessions || 0}</div>
                    </div>
                    <div className="bg-foreground/5 rounded-lg p-2 text-center">
                      <div className="text-xs text-muted-foreground">Revenue</div>
                      <div className="font-bold text-xs text-emerald-600 dark:text-emerald-400">{fmtRp(creator.this_month?.revenue || 0)}</div>
                    </div>
                    <div className="bg-foreground/5 rounded-lg p-2 text-center">
                      <div className="text-xs text-muted-foreground">Penonton</div>
                      <div className="font-bold text-sm">{fmt(creator.this_month?.viewers || 0)}</div>
                    </div>
                  </div>

                  {/* KPI progress — per-bulan (jika ada) atau global */}
                  {(() => {
                    const mt = creatorTargets[creator.id];
                    const revTgt  = mt?.revenue_target  || creator.kpi_targets?.monthly_revenue  || 0;
                    const sessTgt = mt?.sessions_target || creator.kpi_targets?.monthly_sessions || 0;
                    if (!revTgt && !sessTgt) return null;
                    return (
                      <div className="space-y-1.5 mt-2 pt-2 border-t border-foreground/5">
                        {revTgt > 0 && (
                          <KPIBar label="Revenue" value={creator.this_month?.revenue || 0} target={revTgt} unit="Rp " />
                        )}
                        {sessTgt > 0 && (
                          <KPIBar label="Sesi" value={creator.this_month?.sessions || 0} target={sessTgt} />
                        )}
                        {mt && mt.viewers_target > 0 && (
                          <KPIBar label="Viewers" value={creator.this_month?.viewers || 0} target={mt.viewers_target} />
                        )}
                        {mt && (
                          <p className="text-[9px] text-violet-600 dark:text-violet-400 text-right mt-0.5">target bulanan</p>
                        )}
                      </div>
                    );
                  })()}

                  <div className="flex flex-wrap items-center gap-1.5 mt-2 text-[10px]">
                    <span className="px-1.5 py-0.5 rounded-full bg-foreground/5 uppercase"
                      data-testid={`creator-type-badge-${creator.creator_code}`}>
                      {creator.creator_type || 'new'}
                    </span>
                    {creator.domicile ? (
                      <span className="px-1.5 py-0.5 rounded-full bg-foreground/5">{creator.domicile}</span>
                    ) : null}
                    {/* Kreator tanpa akun portal DIKATAKAN, bukan dibiarkan
                        gagal login diam-diam. */}
                    {creator.login_email ? (
                      <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600">
                        akun portal siap
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600"
                        data-testid={`creator-no-portal-${creator.creator_code}`}>
                        belum ada akun portal
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2 mt-3 pt-3 border-t border-foreground/5">
                    <button
                      data-testid="edit-creator-btn"
                      onClick={() => { setEditCreator(creator); setShowCreatorForm(true); }}
                      className="flex-1 text-xs py-1.5 rounded-lg border border-foreground/10 hover:bg-foreground/5 transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Edit2 size={12} /> Edit
                    </button>
                    <button
                      data-testid={`creator-incentive-btn-${creator.creator_code}`}
                      onClick={() => setIncentiveCreator(creator)}
                      className="flex-1 text-xs py-1.5 rounded-lg border border-foreground/10 hover:bg-foreground/5 transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Target size={12} /> Insentif
                    </button>
                    <button
                      onClick={() => handleDeactivateCreator(creator.id)}
                      className="flex-1 text-xs py-1.5 rounded-lg border border-red-300 dark:border-red-500/20 text-red-700 dark:text-red-400 hover:bg-red-100 dark:bg-red-500/10 transition-colors flex items-center justify-center gap-1.5"
                    >
                      <Trash2 size={12} /> Nonaktifkan
                    </button>
                  </div>
                </div>
              ))}
            </div>
            {creatorPagination && (
              <PaginationBar
                pagination={creatorPagination}
                onPageChange={(p) => setCreatorPage(p)}
              />
            )}
            </>
          )}
        </div>
      )}

      {/* ═══ TAB: PERFORMANCE ═══ */}
      {!loading && tab === 'performance' && (
        <div className="space-y-4">
          {sessions.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Video className="mx-auto mb-3 opacity-30" size={40} />
              <p className="text-sm">Belum ada sesi live. Klik "Catat Sesi" untuk mulai.</p>
            </div>
          ) : (
            <div className="overflow-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
              <table className="w-full text-sm">
                <thead className="bg-foreground/[0.03]">
                  <tr>
                    {['Tanggal', 'Creator', 'Akun', 'Durasi', 'Penonton', 'Revenue', 'Orders', 'Aksi'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paged.map(s => (
                    <tr key={s.id} data-testid="session-row" className="border-t border-foreground/5 hover:bg-foreground/[0.02]">
                      <td className="px-4 py-3 text-xs">{s.date}</td>
                      <td className="px-4 py-3 font-medium">{s.creator_name}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.account_name}</td>
                      <td className="px-4 py-3 text-xs">{s.duration_minutes}m</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <Eye size={12} className="text-muted-foreground" />
                          {fmt(s.viewers)}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-medium text-emerald-600 dark:text-emerald-400">{fmtRp(s.revenue)}</td>
                      <td className="px-4 py-3">{fmt(s.orders)}</td>
                      <td className="px-4 py-3">
                        <button onClick={() => handleDeleteSession(s.id)} className="text-red-700 dark:text-red-400 hover:text-red-600 dark:text-red-300 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
            </div>
          )}
        </div>
      )}

      {/* ═══ TAB: CATALOG & REQUESTS ═══ */}
      {!loading && tab === 'catalog' && (
        <div className="space-y-6">
          {/* Pending Requests */}
          {pendingRequests.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center text-foreground text-xs">{pendingRequests.length}</span>
                Request Pending Persetujuan
              </h3>
              <div className="space-y-2">
                {pendingRequests.map(req => (
                  <div key={req.id} data-testid="request-row" className="flex items-center justify-between bg-amber-100 dark:bg-amber-500/5 border border-amber-300 dark:border-amber-500/20 rounded-xl p-4">
                    <div>
                      <div className="font-medium text-sm">{req.product_name} <span className="text-xs text-muted-foreground">({req.sku})</span></div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {req.creator_name} · {req.quantity_requested} pcs · Stok: {fmt(req.current_stock)} pcs
                        {req.purpose && ` · ${req.purpose}`}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        data-testid="approve-request-btn"
                        onClick={() => handleApproveRequest(req.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-400 dark:border-emerald-500/30 text-xs hover:bg-emerald-500/30 transition-colors"
                      >
                        <Check size={12} /> Setujui
                      </button>
                      <button
                        data-testid="reject-request-btn"
                        onClick={() => handleRejectRequest(req.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border border-red-400 dark:border-red-500/30 text-xs hover:bg-red-500/30 transition-colors"
                      >
                        <X size={12} /> Tolak
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* All Requests History */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <ShoppingBag size={15} />
              Semua Request {requestPagination ? `(${requestPagination.total})` : `(${requests.length})`}
            </h3>
            {requests.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground text-sm">Belum ada request dari creator.</div>
            ) : (
              <>
              <div className="overflow-auto rounded-xl border border-[var(--glass-border)] bg-[var(--card-surface)] shadow-[var(--shadow-card)]">
                <table className="w-full text-sm">
                  <thead className="bg-foreground/[0.03]">
                    <tr>
                      {['Creator', 'Produk', 'Qty', 'Stok Saat Req', 'Stok Sekarang', 'Tujuan', 'Status', 'Diulas'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map(req => (
                      <tr key={req.id} className="border-t border-foreground/5 hover:bg-foreground/[0.02]">
                        <td className="px-4 py-3 font-medium text-sm">{req.creator_name}</td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-sm">{req.product_name}</div>
                          <div className="text-xs text-muted-foreground">{req.sku}</div>
                        </td>
                        <td className="px-4 py-3">{req.quantity_requested} pcs</td>
                        <td className="px-4 py-3 text-xs">{fmt(req.stock_at_request)} pcs</td>
                        <td className="px-4 py-3 text-xs">
                          <span className={req.current_stock >= req.quantity_requested ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}>
                            {fmt(req.current_stock)} pcs
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{req.purpose || '-'}</td>
                        <td className="px-4 py-3"><Badge cls={STATUS_BADGE[req.status]}>{req.status}</Badge></td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{req.reviewed_by || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {requestPagination && (
                <PaginationBar
                  pagination={requestPagination}
                  onPageChange={(p) => setRequestPage(p)}
                />
              )}
              </>
            )}
          </div>

          {/* Catalog */}
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Package size={15} />
              Katalog Produk ({catalog.filter(c => c.is_active).length} aktif)
            </h3>
            {catalog.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">Belum ada produk di katalog. Klik "Tambah Produk".</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {catalog.map(item => (
                  <div key={item.id} data-testid="catalog-item" className={`border rounded-xl p-4 ${item.is_active ? 'border-foreground/[0.08] bg-foreground/[0.03]' : 'border-foreground/[0.04] bg-foreground/[0.01] opacity-50'}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="font-medium text-sm">{item.product_name}</div>
                        <div className="text-xs text-muted-foreground">{item.sku}</div>
                      </div>
                      <button onClick={() => handleRemoveCatalog(item.id)} className="text-muted-foreground hover:text-red-700 dark:text-red-400 transition-colors">
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">{fmtRp(item.unit_price)}</span>
                      <span className={`text-xs ${item.stock_qty > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                        Stok: {fmt(item.stock_qty)} pcs
                      </span>
                    </div>
                    {item.category && (
                      <div className="mt-2">
                        <span className="text-xs bg-foreground/5 border border-foreground/10 rounded px-2 py-0.5 text-muted-foreground">{item.category}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ═══ TAB: RAPOR MINGGUAN ═══ */}
      {!loading && tab === 'weekly' && (
        <CreatorWeeklyReportPanel token={token} />
      )}

      {/* ═══ TAB: LEADERBOARD ═══ */}
      {!loading && tab === 'leaderboard' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="text-sm text-muted-foreground">Bulan:</label>
            <input
              type="month"
              value={leaderMonth}
              onChange={e => setLeaderMonth(e.target.value)}
              className="bg-foreground/5 border border-foreground/10 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          {leaderboard.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Trophy className="mx-auto mb-3 opacity-30" size={40} />
              <p className="text-sm">Belum ada data performa untuk periode ini.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {leaderboard.map(entry => (
                <div
                  key={entry.creator_id}
                  data-testid="leaderboard-row"
                  className={`flex items-center gap-4 p-4 rounded-2xl border transition-all ${
                    entry.rank === 1 ? 'bg-amber-100 dark:bg-amber-500/10 border-amber-400 dark:border-amber-500/30' :
                    entry.rank === 2 ? 'bg-muted dark:bg-zinc-400/10 border-border dark:border-zinc-400/30' :
                    entry.rank === 3 ? 'bg-orange-600/10 border-orange-600/30' :
                    'bg-foreground/[0.03] border-foreground/[0.08]'
                  }`}
                >
                  {/* Rank */}
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg flex-shrink-0 ${
                    entry.rank === 1 ? 'bg-amber-500 text-foreground' :
                    entry.rank === 2 ? 'bg-muted text-foreground' :
                    entry.rank === 3 ? 'bg-orange-600 text-foreground' :
                    'bg-foreground/10 text-muted-foreground'
                  }`}>
                    {entry.rank <= 3 ? ['🥇', '🥈', '🥉'][entry.rank - 1] : entry.rank}
                  </div>

                  {/* Creator info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{entry.name}</span>
                      <span className="text-xs text-muted-foreground">{entry.creator_code}</span>
                    </div>
                    <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                      <span>{entry.total_sessions} sesi</span>
                      <span>{fmt(entry.total_viewers)} penonton</span>
                      <span>{fmt(entry.total_orders)} orders</span>
                    </div>
                  </div>

                  {/* Revenue + KPI */}
                  <div className="text-right flex-shrink-0">
                    <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{fmtRp(entry.total_revenue)}</div>
                    {entry.kpi_revenue_pct !== null && (
                      <div className={`text-xs font-medium ${entry.kpi_revenue_pct >= 100 ? 'text-emerald-600 dark:text-emerald-400' : entry.kpi_revenue_pct >= 50 ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400'}`}>
                        {entry.kpi_revenue_pct}% dari target
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {incentiveCreator && (
        <CreatorIncentivePanel token={token} creator={incentiveCreator}
          onClose={() => { setIncentiveCreator(null); load(); }} />
      )}
      {showCreatorForm && (
        <CreatorFormModal
          token={token}
          accounts={accounts}
          editCreator={editCreator}
          onClose={() => { setShowCreatorForm(false); setEditCreator(null); }}
          onSaved={() => { setShowCreatorForm(false); setEditCreator(null); load(); }}
        />
      )}
      {showSessionForm && (
        <SessionFormModal
          token={token}
          creators={creators.filter(c => c.status === 'active')}
          accounts={accounts}
          onClose={() => setShowSessionForm(false)}
          onSaved={() => { setShowSessionForm(false); load(); }}
        />
      )}
      {showCatalogForm && (
        <CatalogFormModal
          token={token}
          accounts={accounts}
          onClose={() => setShowCatalogForm(false)}
          onSaved={() => { setShowCatalogForm(false); load(); }}
        />
      )}
    </div>
  );
}
