/**
 * Creator Portal — Mobile-First Standalone App
 *
 * Route: /creator
 * Auth: Separate JWT with audience='creator-portal'
 *
 * UI selaras dengan LiveHost Portal (mobile-first, bottom-nav, tema teal/emerald,
 * kartu, toast Sonner).
 *
 * Fitur:
 *  - Login (standalone, separate token storage)
 *  - Dashboard: KPI + sesi terbaru
 *  - Katalog & Request produk
 *  - Input Sesi (self-report penjualan) -> otomatis masuk Sales Marketing
 *  - Performa Saya (rekap bulanan + progress KPI)
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import {
  LogOut, User, Video, ShoppingBag, Target, RefreshCw, Eye, TrendingUp,
  Package, X, Plus, Loader2, CheckCircle2, Calendar, Trophy,
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;
const CREATOR_TOKEN_KEY = 'creator_portal_token';
const CREATOR_USER_KEY = 'creator_portal_user';

const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const fmtRp = (n) => `Rp ${fmt(n)}`;
const todayISO = () => new Date().toISOString().split('T')[0];
const formatDate = (d) => {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return String(d); }
};

// ─── API helper (parity with LiveHost portal) ─────────────────────────────────
async function apiCall(token, path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ─── Storage helpers ──────────────────────────────────────────────────────────
const creatorSession = {
  save: (token, user) => {
    localStorage.setItem(CREATOR_TOKEN_KEY, token);
    localStorage.setItem(CREATOR_USER_KEY, JSON.stringify(user));
  },
  load: () => {
    const token = localStorage.getItem(CREATOR_TOKEN_KEY);
    const user = localStorage.getItem(CREATOR_USER_KEY);
    return { token, user: user ? JSON.parse(user) : null };
  },
  clear: () => {
    localStorage.removeItem(CREATOR_TOKEN_KEY);
    localStorage.removeItem(CREATOR_USER_KEY);
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// LOGIN
// ═══════════════════════════════════════════════════════════════════════════════
function CreatorLoginPage({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) { setError('Email dan password wajib diisi'); return; }
    setLoading(true); setError('');
    try {
      const r = await fetch(`${API}/api/marketing/creator-portal/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Login gagal');
      const u = { creator_id: d.creator_id, creator_name: d.creator_name, creator_code: d.creator_code };
      creatorSession.save(d.token, u);
      onLogin(d.token, u);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div
      data-testid="creator-login-page"
      className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-teal-50 via-background to-emerald-50"
    >
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-500 mb-4 shadow-xl">
            <Video size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Creator Portal</h1>
          <p className="text-sm text-muted-foreground mt-1">Portal untuk KOL &amp; Creator</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-card border border-border rounded-2xl p-6 shadow-xl">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Email</label>
              <input
                data-testid="creator-login-email" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)} autoComplete="username"
                className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
                placeholder="email@creator.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Password</label>
              <input
                data-testid="creator-login-password" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
                className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div data-testid="creator-login-error" className="text-red-700 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
            <button
              data-testid="creator-login-btn" type="submit" disabled={loading}
              className="w-full py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-medium hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 transition shadow-lg flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <User size={16} />}
              {loading ? 'Masuk...' : 'Masuk ke Portal'}
            </button>
          </div>
        </form>

        <p className="text-center text-xs text-muted-foreground mt-5">Butuh akun? Hubungi admin marketing.</p>
      </div>
    </div>
  );
}

// ─── KPI Card ──────────────────────────────────────────────────────────────────
function KPICard({ label, actual, target, unit = '' }) {
  const pct = target ? Math.min(100, Math.round((actual / target) * 100)) : 0;
  const bar = pct >= 80 ? 'from-emerald-500 to-teal-400' : pct >= 50 ? 'from-amber-500 to-amber-400' : 'from-rose-500 to-rose-400';
  return (
    <div className="bg-card border border-border rounded-2xl p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="text-xl font-bold text-foreground mb-1">{unit}{fmt(actual)}</div>
      <div className="text-[11px] text-muted-foreground mb-2">Target: {unit}{fmt(target)}</div>
      <div className="h-1.5 rounded-full bg-muted">
        <div className={`h-full rounded-full bg-gradient-to-r ${bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[11px] text-right mt-1 font-medium text-teal-600">{pct}%</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════
function CreatorDashboard({ token, creator }) {
  const [kpi, setKpi] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kpiRes, perfRes] = await Promise.all([
        apiCall(token, '/api/marketing/creator-portal/my-kpi'),
        apiCall(token, '/api/marketing/creator-portal/my-performance'),
      ]);
      setKpi(kpiRes); setPerformance(perfRes);
    } catch { toast.error('Gagal memuat data'); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Loading label="Memuat data..." />;

  const targets = kpi?.kpi_targets || {};
  const actuals = kpi?.actuals || {};
  const sessions = performance?.sessions || [];

  return (
    <div data-testid="creator-dashboard" className="pb-24 px-4 pt-4 space-y-5">
      <div>
        <h2 className="text-xs uppercase tracking-wide font-semibold text-teal-600 mb-2">KPI Bulan Ini — {kpi?.month}</h2>
        <div className="grid grid-cols-1 gap-3">
          <KPICard label="Revenue" actual={actuals.monthly_revenue} target={targets.monthly_revenue} unit="Rp " />
          <div className="grid grid-cols-2 gap-3">
            <KPICard label="Sesi Live" actual={actuals.monthly_sessions} target={targets.monthly_sessions} />
            <KPICard label="Penonton" actual={actuals.monthly_viewers} target={targets.monthly_viewers} />
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">Sesi Live Terbaru</h2>
        {sessions.length === 0 ? (
          <EmptyState icon={Video} text="Belum ada sesi live bulan ini." />
        ) : (
          <div className="space-y-2">
            {sessions.slice(0, 5).map((s) => <SessionRow key={s.id} s={s} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function SessionRow({ s }) {
  return (
    <div data-testid="creator-session-row" className="flex items-center justify-between bg-card border border-border rounded-xl p-3.5">
      <div className="min-w-0">
        <div className="font-medium text-sm text-foreground truncate">{s.session_name || s.date}</div>
        <div className="text-[11px] text-muted-foreground mt-0.5">
          {formatDate(s.date)} · {s.platform || '—'} · {fmt(s.viewers)} penonton
        </div>
      </div>
      <div className="text-right ml-2">
        <div className="text-teal-600 font-semibold text-sm">{fmtRp(s.revenue)}</div>
        <div className="text-[11px] text-muted-foreground">{fmt(s.orders)} orders</div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// KATALOG & REQUEST
// ═══════════════════════════════════════════════════════════════════════════════
function CreatorCatalogPage({ token }) {
  const [catalog, setCatalog] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [requestingItem, setRequestingItem] = useState(null);
  const [reqForm, setReqForm] = useState({ quantity_requested: 1, purpose: '', notes: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [catRes, reqRes] = await Promise.all([
        apiCall(token, '/api/marketing/creator-portal/catalog'),
        apiCall(token, '/api/marketing/creator-portal/my-requests'),
      ]);
      setCatalog(Array.isArray(catRes) ? catRes : []);
      setMyRequests(Array.isArray(reqRes) ? reqRes : []);
    } catch { toast.error('Gagal memuat katalog'); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  async function submitRequest() {
    if (!requestingItem) return;
    setSaving(true);
    try {
      await apiCall(token, '/api/marketing/creator-portal/requests', {
        method: 'POST',
        body: JSON.stringify({
          account_id: requestingItem.account_id, catalog_item_id: requestingItem.id,
          quantity_requested: Number(reqForm.quantity_requested),
          purpose: reqForm.purpose, notes: reqForm.notes,
        }),
      });
      toast.success('Request berhasil dikirim ke admin');
      setRequestingItem(null); setReqForm({ quantity_requested: 1, purpose: '', notes: '' });
      load();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  }

  const STATUS = { pending: 'text-amber-600', approved: 'text-teal-600', rejected: 'text-rose-600' };

  if (loading) return <Loading label="Memuat katalog..." />;

  return (
    <div data-testid="creator-catalog" className="pb-24 px-4 pt-4 space-y-5">
      <div>
        <h2 className="text-xs uppercase tracking-wide font-semibold text-teal-600 mb-2">Katalog Produk ({catalog.length})</h2>
        {catalog.length === 0 ? (
          <EmptyState icon={Package} text="Belum ada produk di katalog." />
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {catalog.map((item) => (
              <div key={item.id} data-testid="catalog-product-card" className="bg-card border border-border rounded-2xl p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground truncate">{item.product_name}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">SKU: {item.sku}</div>
                  </div>
                  {item.category && (
                    <span className="text-[10px] bg-muted border border-border rounded px-2 py-0.5 text-muted-foreground shrink-0 ml-2">{item.category}</span>
                  )}
                </div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-teal-600 font-semibold text-sm">{fmtRp(item.unit_price)}</span>
                  <span className={`text-xs font-medium ${item.stock_qty > 0 ? 'text-teal-600' : 'text-rose-600'}`}>
                    Stok: {fmt(item.stock_qty)} pcs
                  </span>
                </div>
                <button
                  data-testid="request-item-btn" onClick={() => setRequestingItem(item)} disabled={item.stock_qty === 0}
                  className="w-full py-2 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-medium hover:from-teal-600 hover:to-emerald-600 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {item.stock_qty === 0 ? 'Stok Habis' : 'Request Produk'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">Request Saya ({myRequests.length})</h2>
        {myRequests.length === 0 ? (
          <EmptyState icon={ShoppingBag} text="Belum ada request." />
        ) : (
          <div className="space-y-2">
            {myRequests.map((req) => (
              <div key={req.id} data-testid="my-request-row" className="flex items-center justify-between bg-card border border-border rounded-xl p-3.5">
                <div className="min-w-0">
                  <div className="font-medium text-sm text-foreground truncate">{req.product_name} <span className="text-muted-foreground text-xs">({req.sku})</span></div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">{req.quantity_requested} pcs · {req.purpose || '-'}</div>
                </div>
                <div className="text-right ml-2">
                  <span className={`font-medium text-sm capitalize ${STATUS[req.status] || 'text-muted-foreground'}`}>{req.status}</span>
                  {req.rejection_reason && <div className="text-[11px] text-rose-600 mt-0.5">{req.rejection_reason}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {requestingItem && (
        <ModalSheet title="Request Produk" onClose={() => setRequestingItem(null)} icon={ShoppingBag}
          footer={(
            <>
              <button onClick={() => setRequestingItem(null)} className="flex-1 py-2.5 rounded-lg bg-foreground/5 text-sm font-medium text-muted-foreground hover:bg-foreground/10">Batal</button>
              <button data-testid="submit-request-btn" onClick={submitRequest} disabled={saving}
                className="flex-1 py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-semibold hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 flex items-center justify-center gap-2">
                {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />} Kirim
              </button>
            </>
          )}
        >
          <div className="bg-muted rounded-xl p-3 mb-3">
            <div className="font-medium text-foreground text-sm">{requestingItem.product_name}</div>
            <div className="text-xs text-muted-foreground mt-1">SKU: {requestingItem.sku} · Stok: {fmt(requestingItem.stock_qty)} pcs</div>
          </div>
          <Field label="Jumlah yang Diminta *">
            <input data-testid="req-quantity-input" type="number" min="1" max={requestingItem.stock_qty}
              value={reqForm.quantity_requested} onChange={(e) => setReqForm((f) => ({ ...f, quantity_requested: e.target.value }))}
              className={inputCls} />
          </Field>
          <Field label="Tujuan Promo">
            <input data-testid="req-purpose-input" value={reqForm.purpose} onChange={(e) => setReqForm((f) => ({ ...f, purpose: e.target.value }))}
              placeholder="Flash sale, review, giveaway..." className={inputCls} />
          </Field>
          <Field label="Catatan Tambahan">
            <textarea rows={2} value={reqForm.notes} onChange={(e) => setReqForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Catatan untuk admin..." className={inputCls} />
          </Field>
        </ModalSheet>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SESI (Self-report) — parity dengan Input Penjualan LiveHost
// ═══════════════════════════════════════════════════════════════════════════════
function CreatorSessionsPage({ token }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showInput, setShowInput] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiCall(token, '/api/marketing/creator-portal/my-sessions');
      setSessions(Array.isArray(data) ? data : []);
    } catch { toast.error('Gagal memuat sesi'); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="creator-sessions" className="pb-28 px-4 pt-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Sesi Live Saya</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{sessions.length} sesi tercatat</p>
        </div>
        <button onClick={load} data-testid="sessions-refresh" className="p-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-muted-foreground transition">
          <RefreshCw size={16} />
        </button>
      </div>

      <button
        onClick={() => setShowInput(true)} data-testid="open-input-session-button"
        className="w-full py-3 rounded-xl bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-semibold hover:from-teal-600 hover:to-emerald-600 transition shadow-md flex items-center justify-center gap-2"
      >
        <Plus size={18} /> Input Sesi / Penjualan
      </button>

      {loading ? <Loading label="Memuat sesi..." /> : (
        sessions.length === 0 ? (
          <EmptyState icon={Video} text="Belum ada sesi. Klik 'Input Sesi' untuk mencatat penjualan live Anda." />
        ) : (
          <div className="space-y-2">{sessions.map((s) => <SessionRow key={s.id} s={s} />)}</div>
        )
      )}

      {showInput && (
        <SessionInputModal token={token} onClose={() => setShowInput(false)}
          onSaved={() => { setShowInput(false); load(); }} />
      )}
    </div>
  );
}

function SessionInputModal({ token, onClose, onSaved }) {
  const [accounts, setAccounts] = useState([]);
  const [form, setForm] = useState({
    account_id: '', date: todayISO(), platform: 'shopee', session_name: '',
    revenue: 0, orders: 0, viewers: 0, peak_viewers: 0, duration_minutes: 0, items: '', notes: '',
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    (async () => {
      try {
        const accs = await apiCall(token, '/api/marketing/creator-portal/my-accounts');
        setAccounts(Array.isArray(accs) ? accs : []);
        if (Array.isArray(accs) && accs.length === 1) set('account_id', accs[0].id);
      } catch { /* silent */ }
    })();
  }, [token]);

  const submit = async () => {
    if (!form.account_id) { toast.error('Pilih akun terlebih dahulu'); return; }
    if (!form.date) { toast.error('Tanggal wajib diisi'); return; }
    setSaving(true);
    try {
      await apiCall(token, '/api/marketing/creator-portal/sessions', {
        method: 'POST',
        body: JSON.stringify({
          account_id: form.account_id, date: form.date, platform: form.platform,
          session_name: form.session_name || undefined,
          duration_minutes: Number(form.duration_minutes) || 0,
          revenue: Number(form.revenue) || 0, orders: Number(form.orders) || 0,
          viewers: Number(form.viewers) || 0, peak_viewers: Number(form.peak_viewers) || 0,
          items_promoted: form.items.split(',').map((s) => s.trim()).filter(Boolean),
          notes: form.notes,
        }),
      });
      toast.success('Sesi tersimpan & otomatis masuk ke Sales Marketing');
      onSaved();
    } catch (e) { toast.error(e.message || 'Gagal menyimpan sesi'); }
    finally { setSaving(false); }
  };

  return (
    <ModalSheet title="Input Sesi / Penjualan" onClose={saving ? undefined : onClose} icon={Trophy}
      footer={(
        <>
          <button onClick={onClose} disabled={saving} className="flex-1 py-2.5 rounded-lg bg-foreground/5 text-sm font-medium text-muted-foreground hover:bg-foreground/10">Batal</button>
          <button onClick={submit} disabled={saving} data-testid="session-submit-button"
            className="flex-1 py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-semibold hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 flex items-center justify-center gap-2">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />} Simpan
          </button>
        </>
      )}
    >
      <Field label="Akun *">
        <SmartNativeSelect data-testid="session-input-account" value={form.account_id} onChange={(e) => set('account_id', e.target.value)} className={inputCls}>
          <option value="">— Pilih akun —</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.account_name} ({a.platform})</option>)}
        </SmartNativeSelect>
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Tanggal *">
          <input type="date" data-testid="session-input-date" value={form.date} onChange={(e) => set('date', e.target.value)} className={inputCls} />
        </Field>
        <Field label="Platform">
          <select data-testid="session-input-platform" value={form.platform} onChange={(e) => set('platform', e.target.value)} className={inputCls}>
            <option value="shopee">Shopee</option>
            <option value="tiktokshop">TikTokShop</option>
            <option value="tokopedia">Tokopedia</option>
          </select>
        </Field>
      </div>
      <Field label="Nama Sesi">
        <input data-testid="session-input-name" value={form.session_name} onChange={(e) => set('session_name', e.target.value)} placeholder="cth: Live Sore Flash Sale" className={inputCls} />
      </Field>
      <Field label="Omzet / Revenue (Rp)">
        <input type="number" min="0" inputMode="numeric" data-testid="session-input-revenue" value={form.revenue} onChange={(e) => set('revenue', e.target.value)} className={inputCls} />
        <p className="text-[11px] text-teal-600 mt-1">{fmtRp(Number(form.revenue) || 0)}</p>
      </Field>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Orders"><input type="number" min="0" data-testid="session-input-orders" value={form.orders} onChange={(e) => set('orders', e.target.value)} className={inputCls} /></Field>
        <Field label="Viewers"><input type="number" min="0" data-testid="session-input-viewers" value={form.viewers} onChange={(e) => set('viewers', e.target.value)} className={inputCls} /></Field>
        <Field label="Peak"><input type="number" min="0" data-testid="session-input-peak" value={form.peak_viewers} onChange={(e) => set('peak_viewers', e.target.value)} className={inputCls} /></Field>
      </div>
      <Field label="Produk Dipromosikan">
        <input data-testid="session-input-items" value={form.items} onChange={(e) => set('items', e.target.value)} placeholder="Pisahkan dgn koma: Kaos, Celana" className={inputCls} />
      </Field>
      <Field label="Catatan">
        <textarea rows={2} data-testid="session-input-notes" value={form.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Catatan (opsional)" className={inputCls} />
      </Field>
    </ModalSheet>
  );
}

function CreatorWeeklyCard({ token }) {
  const [weekEnd, setWeekEnd] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const d = await apiCall(token,
          `/api/marketing/creator-portal/my-weekly-report?week_end=${weekEnd}`);
        setData(d);
      } catch { /* rapor mingguan opsional — jangan matikan halaman performa */ }
      finally { setLoading(false); }
    })();
  }, [token, weekEnd]);

  // Kreator harus bisa membuka pekan yang rapornya DIKIRIM admin, bukan hanya
  // 7 hari terakhir dari hari ini — kalau tidak, rapor yang diterima lewat email
  // tidak pernah bisa dicocokkan dengan layar. Tetapi maju ke pekan yang BELUM
  // terjadi dilarang: angka 0 di pekan masa depan akan dibaca sebagai "performa
  // saya nol".
  const todayStr = new Date().toISOString().slice(0, 10);
  const atCurrentWeek = weekEnd >= todayStr;
  const shiftWeek = (days) => {
    const d = new Date(`${weekEnd}T00:00:00`);
    d.setDate(d.getDate() + days);
    const next = d.toISOString().slice(0, 10);
    setWeekEnd(next > todayStr ? todayStr : next);
  };

  const r = data?.report;
  const p = data?.period || {};

  return (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-3" data-testid="creator-weekly-card">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wide font-semibold text-teal-600">Rapor Mingguan</h3>
        <div className="flex items-center gap-1">
          <button onClick={() => shiftWeek(-7)} data-testid="creator-weekly-prev"
            className="px-2 py-1 rounded-lg border border-border text-[11px] text-foreground">‹ pekan lalu</button>
          <button onClick={() => shiftWeek(7)} disabled={atCurrentWeek}
            data-testid="creator-weekly-next"
            className={`px-2 py-1 rounded-lg border border-border text-[11px] ${atCurrentWeek
              ? 'text-muted-foreground opacity-40 cursor-not-allowed' : 'text-foreground'}`}>
            pekan depan ›</button>
        </div>
      </div>
      <div className="text-[10px] text-muted-foreground">
        7 hari bergulir: {p.start || '—'} s/d {p.end || weekEnd}
      </div>

      {loading || !r ? (
        <div className="text-xs text-muted-foreground py-2">Memuat rapor…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              ['Konten', `${r.contents} (${r.posted} tayang)`],
              ['Views', fmt(r.views)],
              ['Engagement', `${fmt(r.engagement)} (${r.engagement_rate}%)`],
              ['GMV (platform)', fmtRp(r.gmv_kpi)],
              ['Omzet pesanan', fmtRp(r.order_revenue)],
              ['Pcs pekan ini', `${r.pcs_week} pcs`],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-muted/50 px-3 py-2">
                <div className="text-[10px] text-muted-foreground">{k}</div>
                <div className="font-semibold text-foreground">{v}</div>
              </div>
            ))}
          </div>
          {r.contents === 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-700"
              data-testid="creator-weekly-idle">
              Belum ada konten pada pekan ini — angka 0 di atas bukan berarti performa turun,
              memang belum ada yang diposting.
            </div>
          )}
          {r.incentive_eligible && (
            <div className="rounded-lg border border-border px-3 py-2 text-xs">
              <div className="text-[10px] text-muted-foreground">
                Insentif periode {r.incentive_period?.start} s/d {r.incentive_period?.end}
              </div>
              <div className="text-foreground">
                {r.pcs_period} pcs{r.target_pcs ? ` / target ${r.target_pcs} pcs (${r.target_progress_pct}%)` : ''}
                {' · '}<span className="font-semibold">{fmtRp(r.incentive_total)}</span>
              </div>
            </div>
          )}
          {(r.top_contents || []).length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Konten teratas</div>
              {r.top_contents.map((c) => (
                <div key={c.id} className="flex items-center justify-between text-xs gap-2">
                  <span className="truncate text-foreground">{c.title}</span>
                  <span className="text-muted-foreground shrink-0">{fmt(c.views)} views</span>
                </div>
              ))}
            </div>
          )}
          {(data.data_notes || []).length > 0 && (
            <ul className="list-disc pl-4 space-y-0.5 text-[10px] text-muted-foreground">
              {data.data_notes.slice(0, 3).map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PERFORMA
// ═══════════════════════════════════════════════════════════════════════════════
function CreatorPerformancePage({ token }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const d = await apiCall(token, `/api/marketing/creator-portal/my-performance?month=${month}`);
        setData(d);
      } catch { toast.error('Gagal memuat performa'); }
      finally { setLoading(false); }
    })();
  }, [token, month]);

  if (loading) return <Loading label="Memuat performa..." />;

  const sessions = data?.sessions || [];
  const summary = data?.summary || {};
  const kpi = data?.kpi_targets || {};
  const progress = data?.kpi_progress || {};

  const bars = [
    { show: kpi.monthly_revenue > 0, label: 'Revenue', txt: `${fmtRp(summary.total_revenue)} / ${fmtRp(kpi.monthly_revenue)}`, pct: progress.revenue_pct, grad: 'from-teal-500 to-emerald-500' },
    { show: kpi.monthly_sessions > 0, label: 'Sesi Live', txt: `${summary.total_sessions} / ${kpi.monthly_sessions}`, pct: progress.sessions_pct, grad: 'from-sky-500 to-cyan-500' },
    { show: kpi.monthly_viewers > 0, label: 'Penonton', txt: `${fmt(summary.total_viewers)} / ${fmt(kpi.monthly_viewers)}`, pct: progress.viewers_pct, grad: 'from-emerald-500 to-teal-500' },
  ].filter((b) => b.show);

  return (
    <div data-testid="creator-performance" className="pb-24 px-4 pt-4 space-y-5">
      <div className="flex items-center gap-2">
        <Calendar size={15} className="text-muted-foreground" />
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground" />
      </div>

      <CreatorWeeklyCard token={token} />

      <div className="grid grid-cols-2 gap-3">
        {[
          { label: 'Total Sesi', value: fmt(summary.total_sessions), icon: Video },
          { label: 'Total Revenue', value: fmtRp(summary.total_revenue), icon: TrendingUp },
          { label: 'Total Penonton', value: fmt(summary.total_viewers), icon: Eye },
          { label: 'Total Orders', value: fmt(summary.total_orders), icon: ShoppingBag },
        ].map((card) => (
          <div key={card.label} className="bg-card border border-border rounded-2xl p-4 text-center">
            <card.icon size={18} className="mx-auto mb-2 text-teal-600" />
            <div className="text-base font-bold text-foreground">{card.value}</div>
            <div className="text-[11px] text-muted-foreground">{card.label}</div>
          </div>
        ))}
      </div>

      {bars.length > 0 && (
        <div className="bg-card border border-border rounded-2xl p-4 space-y-4">
          <h3 className="text-xs uppercase tracking-wide font-semibold text-teal-600">Progress KPI</h3>
          {bars.map((b) => (
            <div key={b.label}>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-muted-foreground">{b.label}</span>
                <span className="text-foreground">{b.txt} ({b.pct || 0}%)</span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div className={`h-full rounded-full bg-gradient-to-r ${b.grad} transition-all`} style={{ width: `${Math.min(100, b.pct || 0)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <h3 className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">Riwayat Sesi ({sessions.length})</h3>
        {sessions.length === 0 ? (
          <EmptyState icon={Video} text="Belum ada sesi bulan ini." />
        ) : (
          <div className="space-y-2">{sessions.map((s) => <SessionRow key={s.id} s={s} />)}</div>
        )}
      </div>
    </div>
  );
}

// ─── Shared small components ─────────────────────────────────────────────────
const inputCls = 'mt-1 w-full h-10 px-3 rounded-lg bg-background border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400';

function Field({ label, children }) {
  return (
    <div className="mb-2">
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}

function Loading({ label }) {
  return (
    <div className="p-8 text-center" data-testid="creator-loading">
      <Loader2 className="animate-spin mx-auto text-teal-600" size={26} />
      <p className="text-sm text-muted-foreground mt-3">{label}</p>
    </div>
  );
}

function EmptyState({ icon: Icon, text }) {
  return (
    <div className="rounded-xl bg-card border border-border p-6 text-center">
      <Icon className="mx-auto text-muted-foreground mb-2" size={26} />
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}

function ModalSheet({ title, icon: Icon, onClose, children, footer }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center" data-testid="creator-modal-sheet">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-background rounded-t-2xl sm:rounded-2xl border border-border shadow-2xl max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 bg-background/95 backdrop-blur px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            {Icon && <Icon size={18} className="text-teal-600" />}
            <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-foreground/10 text-muted-foreground" data-testid="creator-modal-close"><X size={18} /></button>
        </div>
        <div className="p-4">{children}</div>
        {footer && <div className="sticky bottom-0 bg-background/95 backdrop-blur px-4 py-3 border-t border-border flex gap-2">{footer}</div>}
      </div>
    </div>
  );
}

function TabButton({ id, label, icon: Icon, tab, setTab, badge }) {
  const active = tab === id;
  return (
    <button
      onClick={() => setTab(id)} data-testid={`creator-nav-${id}`}
      className={`relative flex flex-col items-center justify-center gap-0.5 py-1.5 rounded-lg transition ${active ? 'text-teal-600 bg-teal-50' : 'text-muted-foreground hover:text-foreground'}`}
    >
      <Icon size={18} />
      <span className="text-[10px] font-medium">{label}</span>
      {badge > 0 && (
        <span data-testid="creator-catalog-badge" className="absolute top-0.5 right-2.5 min-w-[14px] h-[14px] px-1 rounded-full bg-teal-500 text-[8px] font-bold text-white flex items-center justify-center">
          {badge > 9 ? '9+' : badge}
        </span>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════════════════════
export default function CreatorPortalApp() {
  const [token, setToken] = useState(null);
  const [creator, setCreator] = useState(null);
  const [tab, setTab] = useState('dashboard');
  const [catalogBadge, setCatalogBadge] = useState(0);

  useEffect(() => {
    const { token: t, user: u } = creatorSession.load();
    if (t && u) { setToken(t); setCreator(u); }
  }, []);

  useEffect(() => {
    if (!token) return;
    const lastSeen = localStorage.getItem('creator_requests_last_seen') || '2000-01-01T00:00:00Z';
    (async () => {
      try {
        const reqs = await apiCall(token, '/api/marketing/creator-portal/my-requests');
        const n = Array.isArray(reqs) ? reqs.filter((r) => r.status !== 'pending' && r.reviewed_at > lastSeen).length : 0;
        setCatalogBadge(n);
      } catch { /* silent */ }
    })();
  }, [token]);

  const setTabAndBadge = useCallback((id) => {
    setTab(id);
    if (id === 'catalog') { setCatalogBadge(0); localStorage.setItem('creator_requests_last_seen', new Date().toISOString()); }
  }, []);

  function handleLogin(t, u) { setToken(t); setCreator(u); setTab('dashboard'); }
  function handleLogout() { creatorSession.clear(); setToken(null); setCreator(null); }

  if (!token || !creator) return <CreatorLoginPage onLogin={handleLogin} />;

  return (
    <div data-testid="creator-portal-shell" className="min-h-screen text-foreground bg-gradient-to-br from-teal-50 via-background to-emerald-50">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-card/95 backdrop-blur border-b border-border px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-emerald-500 flex items-center justify-center shadow-md">
            <Video size={15} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground leading-none">Creator Portal</h1>
            <p className="text-[10px] text-muted-foreground mt-0.5" data-testid="creator-header-name">
              {creator.creator_name} · {creator.creator_code}
            </p>
          </div>
        </div>
        <button data-testid="creator-logout-btn" onClick={handleLogout} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition">
          <LogOut size={14} /> Keluar
        </button>
      </header>

      {/* Content */}
      <main className="max-w-md mx-auto" data-testid="creator-main-content">
        {tab === 'dashboard' && <CreatorDashboard token={token} creator={creator} />}
        {tab === 'catalog' && <CreatorCatalogPage token={token} />}
        {tab === 'sessions' && <CreatorSessionsPage token={token} />}
        {tab === 'performance' && <CreatorPerformancePage token={token} />}
      </main>

      {/* Bottom nav (mobile-first, parity dgn LiveHost) */}
      <nav data-testid="creator-bottom-nav" className="fixed bottom-0 inset-x-0 z-30 bg-card/95 backdrop-blur border-t border-border px-2 py-1.5">
        <div className="max-w-md mx-auto grid grid-cols-4 gap-1">
          <TabButton id="dashboard" label="Dashboard" icon={Target} tab={tab} setTab={setTabAndBadge} />
          <TabButton id="catalog" label="Katalog" icon={ShoppingBag} tab={tab} setTab={setTabAndBadge} badge={catalogBadge} />
          <TabButton id="sessions" label="Input Sesi" icon={Video} tab={tab} setTab={setTabAndBadge} />
          <TabButton id="performance" label="Performa" icon={TrendingUp} tab={tab} setTab={setTabAndBadge} />
        </div>
      </nav>
    </div>
  );
}
