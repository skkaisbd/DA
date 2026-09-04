/**
 * LiveHost Portal — Mobile-First Standalone App
 *
 * Route: /livehost
 * Auth: Separate JWT with audience='livehost-portal'
 * Realtime: Server-Sent Events via /api/marketing/livehost/portal/notifications/stream
 *
 * Phase 4 (Session 28) — DA25 ERP
 *
 * Features:
 *  - Login (standalone, separate token storage)
 *  - Today's shift + clock-in / clock-out
 *  - My weekly shifts
 *  - Scripts viewer
 *  - Training viewer + self-complete
 *  - Real-time notifications (SSE)
 *  - Profile view + logout
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  LogOut, Radio, Calendar, FileText, GraduationCap, Bell, User,
  Play, Square, Clock, MapPin, ChevronRight, RefreshCw, CheckCircle2,
  CircleDot, AlertCircle, Award, Video, Mic2, Trophy,
  X, ArrowLeft, BadgeCheck, Loader2
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;
const TOKEN_KEY = 'livehost_portal_token';
const HOST_KEY = 'livehost_portal_host';

// ─── Utils ────────────────────────────────────────────────────────────────────
const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const fmtRp = (n) => `Rp ${fmt(n)}`;

const formatDate = (isoOrDate, withTime = false) => {
  if (!isoOrDate) return '—';
  try {
    const d = typeof isoOrDate === 'string' ? new Date(isoOrDate) : isoOrDate;
    if (Number.isNaN(d.getTime())) return String(isoOrDate);
    const opts = withTime
      ? { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
      : { day: '2-digit', month: 'short', year: 'numeric' };
    return d.toLocaleString('id-ID', opts);
  } catch { return String(isoOrDate); }
};

const formatTimeOnly = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  } catch { return '—'; }
};

const todayISO = () => new Date().toISOString().slice(0, 10);

// ─── Session helpers ──────────────────────────────────────────────────────────
const session = {
  save: (token, host) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(HOST_KEY, JSON.stringify(host));
  },
  load: () => {
    const token = localStorage.getItem(TOKEN_KEY);
    const hostRaw = localStorage.getItem(HOST_KEY);
    let host = null;
    try { host = hostRaw ? JSON.parse(hostRaw) : null; } catch { host = null; }
    return { token, host };
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(HOST_KEY);
  },
};

// ─── API helper (auto-auth) ───────────────────────────────────────────────────
async function apiCall(token, path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  let body;
  try { body = await res.json(); } catch { body = null; }
  if (!res.ok) {
    const err = new Error(body?.detail || `Request gagal (${res.status})`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

// ═══════════════════════════════════════════════════════════════════════════════
// LOGIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════
function LiveHostLogin({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) { setError('Email & password wajib diisi'); return; }
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${API}/api/marketing/livehost/portal/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Login gagal');
      const hostObj = d.host || {};
      const host = {
        host_id: hostObj.id,
        host_name: hostObj.name,
        email: hostObj.email,
        phone: hostObj.phone,
        employment_type: hostObj.employment_type,
      };
      session.save(d.token, host);
      onLogin(d.token, host);
      toast.success(`Selamat datang, ${host.host_name || 'Host'}!`);
    } catch (err) {
      setError(err.message || 'Login gagal');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      data-testid="livehost-login-page"
      className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-teal-50 via-background to-emerald-50"
    >
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-500 mb-4 shadow-xl">
            <Radio size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-foreground tracking-tight">LiveHost Portal</h1>
          <p className="text-sm text-muted-foreground mt-1">Portal Host Live Streaming</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-card backdrop-blur-xl border border-border rounded-2xl p-6 shadow-2xl"
          data-testid="livehost-login-form"
        >
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block uppercase tracking-wide">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="host@example.com"
                autoComplete="username"
                disabled={loading}
                data-testid="livehost-login-email"
                className="w-full px-3.5 py-2.5 rounded-lg bg-background border border-border text-foreground placeholder:text-muted-foreground text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/40 focus:border-teal-500/40 transition"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block uppercase tracking-wide">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                disabled={loading}
                data-testid="livehost-login-password"
                className="w-full px-3.5 py-2.5 rounded-lg bg-background border border-border text-foreground placeholder:text-muted-foreground text-sm focus:outline-none focus:ring-2 focus:ring-teal-500/40 focus:border-teal-500/40 transition"
              />
            </div>

            {error && (
              <div
                data-testid="livehost-login-error"
                className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              data-testid="livehost-login-submit"
              className="w-full py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-medium hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 transition shadow-lg flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Radio size={16} />}
              {loading ? 'Masuk...' : 'Masuk ke Portal'}
            </button>
          </div>
        </form>

        <p className="text-center text-xs text-muted-foreground mt-6">
          DA25 ERP — LiveHost Portal · v1.0
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHIFTS TAB
// ═══════════════════════════════════════════════════════════════════════════════
function SalesInputModal({ token, shift, onClose, onSaved }) {
  const [form, setForm] = useState({
    revenue: shift.revenue || 0,
    orders: shift.orders || 0,
    viewers: shift.viewers || 0,
    peak_viewers: shift.peak_viewers || 0,
    items: (shift.items_promoted || []).join(', '),
    challenges_faced: shift.challenges_faced || '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setSaving(true);
    try {
      await apiCall(token, `/api/marketing/livehost/shifts/${shift.id}/performance`, {
        method: 'POST',
        body: JSON.stringify({
          shift_id: shift.id,
          platform: shift.platform || 'shopee',
          revenue: Number(form.revenue) || 0,
          orders: Number(form.orders) || 0,
          viewers: Number(form.viewers) || 0,
          peak_viewers: Number(form.peak_viewers) || 0,
          items_promoted: form.items.split(',').map((s) => s.trim()).filter(Boolean),
          challenges_faced: form.challenges_faced,
          notes: form.notes,
        }),
      });
      toast.success('Penjualan tersimpan & otomatis masuk ke Sales Marketing');
      onSaved();
    } catch (e) {
      toast.error(e.message || 'Gagal menyimpan penjualan');
    } finally { setSaving(false); }
  };

  const NumField = ({ label, k }) => (
    <div>
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">{label}</label>
      <input
        type="number" min="0" inputMode="numeric"
        value={form[k]}
        onChange={(e) => set(k, e.target.value)}
        data-testid={`sales-input-${k}`}
        className="mt-1 w-full h-10 px-3 rounded-lg bg-card border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center" data-testid="sales-input-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={saving ? undefined : onClose} />
      <div className="relative w-full sm:max-w-md bg-background rounded-t-2xl sm:rounded-2xl border border-border shadow-2xl max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 bg-background/95 backdrop-blur px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Trophy size={18} className="text-teal-600" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">Input Penjualan Shift</h3>
              <p className="text-[11px] text-muted-foreground">{shift.account_name} · {formatDate(shift.date)}</p>
            </div>
          </div>
          <button onClick={onClose} disabled={saving} className="p-1.5 rounded-lg hover:bg-foreground/10 text-muted-foreground" data-testid="sales-modal-close">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Omzet / Revenue (Rp)</label>
            <input
              type="number" min="0" inputMode="numeric"
              value={form.revenue}
              onChange={(e) => set('revenue', e.target.value)}
              data-testid="sales-input-revenue"
              className="mt-1 w-full h-11 px-3 rounded-lg bg-card border border-border text-base font-semibold text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
            <p className="text-[11px] text-teal-600 mt-1">{fmtRp(Number(form.revenue) || 0)}</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <NumField label="Orders" k="orders" />
            <NumField label="Viewers" k="viewers" />
            <NumField label="Peak" k="peak_viewers" />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Produk Dipromosikan</label>
            <input
              type="text"
              value={form.items}
              onChange={(e) => set('items', e.target.value)}
              placeholder="Pisahkan dgn koma: Kaos, Celana"
              data-testid="sales-input-items"
              className="mt-1 w-full h-10 px-3 rounded-lg bg-card border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Kendala</label>
            <textarea
              rows={2}
              value={form.challenges_faced}
              onChange={(e) => set('challenges_faced', e.target.value)}
              placeholder="Kendala saat live (opsional)"
              data-testid="sales-input-challenges"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Catatan</label>
            <textarea
              rows={2}
              value={form.notes}
              onChange={(e) => set('notes', e.target.value)}
              placeholder="Catatan tambahan (opsional)"
              data-testid="sales-input-notes"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
        </div>

        <div className="sticky bottom-0 bg-background/95 backdrop-blur px-4 py-3 border-t border-border flex gap-2">
          <button onClick={onClose} disabled={saving} className="flex-1 py-2.5 rounded-lg bg-foreground/5 text-sm font-medium text-muted-foreground hover:bg-foreground/10 transition">
            Batal
          </button>
          <button onClick={submit} disabled={saving} data-testid="sales-submit-button"
            className="flex-1 py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-semibold hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 transition shadow-md flex items-center justify-center gap-2">
            {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
            Simpan
          </button>
        </div>
      </div>
    </div>
  );
}


function ShiftsTab({ token, host, onRefreshNotif }) {
  const [shifts, setShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [clockBusy, setClockBusy] = useState(null); // shift_id while busy
  const [salesShift, setSalesShift] = useState(null); // shift for sales input modal

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch this month's shifts
      const data = await apiCall(token, '/api/marketing/livehost/portal/my-shifts');
      setShifts(Array.isArray(data?.shifts) ? data.shifts : []);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat shift');
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const clock = useCallback(async (shift, action) => {
    setClockBusy(shift.id);
    try {
      const r = await apiCall(token, '/api/marketing/livehost/portal/clock', {
        method: 'POST',
        body: JSON.stringify({ shift_id: shift.id, action }),
      });
      toast.success(r.message || (action === 'clock_in' ? 'Clock in berhasil' : 'Clock out berhasil'));
      await load();
      if (onRefreshNotif) onRefreshNotif();
    } catch (e) {
      toast.error(e.message || 'Aksi clock gagal');
    } finally { setClockBusy(null); }
  }, [token, load, onRefreshNotif]);

  const today = todayISO();
  const todayShifts = shifts.filter(s => s.date === today);
  const upcomingShifts = shifts.filter(s => s.date > today).slice(0, 5);
  const pastShifts = shifts.filter(s => s.date < today).slice(0, 10);

  if (loading) {
    return (
      <div className="p-6 text-center" data-testid="shifts-loading">
        <Loader2 className="animate-spin mx-auto text-teal-600" size={28} />
        <p className="text-sm text-muted-foreground mt-3">Memuat shift...</p>
      </div>
    );
  }

  return (
    <div className="pb-24" data-testid="shifts-tab">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Shift Saya</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{shifts.length} shift bulan ini</p>
        </div>
        <button
          onClick={load}
          data-testid="shifts-refresh-button"
          className="p-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-muted-foreground transition"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Today */}
      {todayShifts.length > 0 && (
        <div className="px-4 mb-5" data-testid="today-shifts-section">
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
            <h3 className="text-xs uppercase tracking-wide font-semibold text-teal-600">Hari Ini</h3>
          </div>
          <div className="space-y-3">
            {todayShifts.map(s => (
              <TodayShiftCard key={s.id} shift={s} busy={clockBusy === s.id} onClock={clock} onInputSales={setSalesShift} />
            ))}
          </div>
        </div>
      )}

      {todayShifts.length === 0 && (
        <div className="px-4 mb-5">
          <div
            className="rounded-xl bg-card border border-border p-5 text-center"
            data-testid="no-shift-today"
          >
            <Calendar className="mx-auto text-muted-foreground mb-2" size={24} />
            <p className="text-sm text-muted-foreground">Tidak ada shift hari ini</p>
            <p className="text-xs text-muted-foreground mt-1">Cek shift mendatang di bawah</p>
          </div>
        </div>
      )}

      {/* Upcoming */}
      {upcomingShifts.length > 0 && (
        <div className="px-4 mb-5" data-testid="upcoming-shifts-section">
          <h3 className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">
            Mendatang
          </h3>
          <div className="space-y-2">
            {upcomingShifts.map(s => <ShiftRow key={s.id} shift={s} />)}
          </div>
        </div>
      )}

      {/* Past */}
      {pastShifts.length > 0 && (
        <div className="px-4" data-testid="past-shifts-section">
          <h3 className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">
            Selesai (10 terakhir)
          </h3>
          <div className="space-y-2">
            {pastShifts.map(s => <ShiftRow key={s.id} shift={s} muted onInputSales={setSalesShift} />)}
          </div>
        </div>
      )}

      {shifts.length === 0 && (
        <div className="px-4 py-12 text-center" data-testid="shifts-empty-state">
          <Calendar className="mx-auto text-foreground/70 mb-3" size={36} />
          <p className="text-sm text-muted-foreground">Belum ada shift dijadwalkan</p>
          <p className="text-xs text-muted-foreground mt-1">Admin akan men-assign shift untuk Anda</p>
        </div>
      )}

      {salesShift && (
        <SalesInputModal
          token={token}
          shift={salesShift}
          onClose={() => setSalesShift(null)}
          onSaved={async () => { setSalesShift(null); await load(); if (onRefreshNotif) onRefreshNotif(); }}
        />
      )}
    </div>
  );
}

const ShiftStatusBadge = ({ status }) => {
  const map = {
    scheduled:   { c: 'bg-slate-100 text-slate-700 border-slate-300',     l: 'Scheduled' },
    on_time:     { c: 'bg-emerald-100 text-emerald-700 border-emerald-300', l: 'On Time' },
    late:        { c: 'bg-amber-100 text-amber-700 border-amber-300', l: 'Terlambat' },
    no_show:     { c: 'bg-red-100 text-red-700 border-red-300',         l: 'Tidak Hadir' },
    completed:   { c: 'bg-teal-100 text-teal-700 border-teal-300',     l: 'Selesai' },
  };
  const cfg = map[status] || map.scheduled;
  return (
    <span
      data-testid={`shift-status-badge-${status}`}
      className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border ${cfg.c}`}
    >
      {cfg.l}
    </span>
  );
}

function TodayShiftCard({ shift, busy, onClock, onInputSales }) {
  const hasClockIn = !!shift.clock_in_time;
  const hasClockOut = !!shift.clock_out_time;
  const canClockIn = !hasClockIn;
  const canClockOut = hasClockIn && !hasClockOut;
  const status = shift.attendance_status;
  const hasSales = Number(shift.revenue) > 0 || !!shift.reviewed_at;

  return (
    <div
      className="rounded-xl bg-gradient-to-br from-teal-50 via-card to-card border border-teal-200 p-4"
      data-testid={`today-shift-card-${shift.id}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-base font-semibold text-foreground capitalize">{shift.shift_type}</span>
            <ShiftStatusBadge status={status} />
          </div>
          <p className="text-xs text-muted-foreground">
            {shift.shift_start_time} – {shift.shift_end_time}
            {' · '}
            <span className="text-muted-foreground">{shift.account_name || 'Account'}</span>
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Durasi</p>
          <p className="text-sm text-teal-600 font-medium">
            {Math.round((shift.scheduled_duration_minutes || 0) / 60 * 10) / 10} jam
          </p>
        </div>
      </div>

      {/* Clock display */}
      <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
        <div className="rounded-lg bg-accent border border-border px-2.5 py-1.5">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Clock In</p>
          <p className="text-foreground font-medium mt-0.5" data-testid={`shift-${shift.id}-clock-in-display`}>
            {hasClockIn ? formatTimeOnly(shift.clock_in_time) : '—'}
          </p>
        </div>
        <div className="rounded-lg bg-accent border border-border px-2.5 py-1.5">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Clock Out</p>
          <p className="text-foreground font-medium mt-0.5" data-testid={`shift-${shift.id}-clock-out-display`}>
            {hasClockOut ? formatTimeOnly(shift.clock_out_time) : '—'}
          </p>
        </div>
      </div>

      {/* Action button */}
      {canClockIn && (
        <button
          onClick={() => onClock(shift, 'clock_in')}
          disabled={busy}
          data-testid={`clock-in-button-${shift.id}`}
          className="w-full py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-foreground text-sm font-medium hover:from-teal-600 hover:to-emerald-600 disabled:opacity-60 transition shadow-md flex items-center justify-center gap-2"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          Clock In
        </button>
      )}
      {canClockOut && (
        <button
          onClick={() => onClock(shift, 'clock_out')}
          disabled={busy}
          data-testid={`clock-out-button-${shift.id}`}
          className="w-full py-2.5 rounded-lg bg-amber-500/90 text-zinc-900 text-sm font-semibold hover:bg-amber-500 disabled:opacity-60 transition shadow-md flex items-center justify-center gap-2"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} />}
          Clock Out
        </button>
      )}
      {hasClockIn && hasClockOut && (
        <div className="space-y-2">
          <div
            data-testid={`shift-${shift.id}-completed-badge`}
            className="w-full py-2 rounded-lg bg-accent border border-border text-sm text-muted-foreground text-center flex items-center justify-center gap-2"
          >
            <CheckCircle2 size={14} className="text-teal-600" /> Shift selesai
          </div>
          {hasSales && (
            <div className="flex items-center justify-between rounded-lg bg-teal-50 border border-teal-200 px-3 py-2" data-testid={`shift-${shift.id}-sales-summary`}>
              <span className="text-[11px] text-teal-700 uppercase tracking-wide font-semibold">Penjualan</span>
              <span className="text-sm font-semibold text-teal-700">{fmtRp(shift.revenue)} · {shift.orders || 0} order</span>
            </div>
          )}
          <button
            onClick={() => onInputSales(shift)}
            data-testid={`input-sales-button-${shift.id}`}
            className="w-full py-2.5 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 text-white text-sm font-semibold hover:from-teal-600 hover:to-emerald-600 transition shadow-md flex items-center justify-center gap-2"
          >
            <Trophy size={16} /> {hasSales ? 'Edit Penjualan' : 'Input Penjualan'}
          </button>
        </div>
      )}
    </div>
  );
}

function ShiftRow({ shift, muted, onInputSales }) {
  const hasClockOut = !!shift.clock_out_time;
  const hasSales = Number(shift.revenue) > 0 || !!shift.reviewed_at;
  return (
    <div
      className={`rounded-lg border border-border p-3 ${muted ? 'bg-accent/50' : 'bg-card'}`}
      data-testid={`shift-row-${shift.id}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm text-foreground font-medium capitalize">{shift.shift_type}</span>
            <ShiftStatusBadge status={shift.attendance_status} />
          </div>
          <p className="text-[11px] text-muted-foreground truncate">
            {formatDate(shift.date)} · {shift.shift_start_time}–{shift.shift_end_time}
            {' · '}{shift.account_name || 'Account'}
          </p>
        </div>
        {shift.revenue > 0 && (
          <div className="text-right ml-2">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Revenue</p>
            <p className="text-xs text-teal-600 font-medium">{fmtRp(shift.revenue)}</p>
          </div>
        )}
      </div>
      {hasClockOut && onInputSales && (
        <button
          onClick={() => onInputSales(shift)}
          data-testid={`input-sales-button-${shift.id}`}
          className="mt-2 w-full py-1.5 rounded-lg border border-teal-300 text-teal-700 bg-teal-50 hover:bg-teal-100 text-xs font-medium transition flex items-center justify-center gap-1.5"
        >
          <Trophy size={13} /> {hasSales ? 'Edit Penjualan' : 'Input Penjualan'}
        </button>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCRIPTS TAB
// ═══════════════════════════════════════════════════════════════════════════════
function ScriptsTab({ token }) {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiCall(token, '/api/marketing/livehost/portal/scripts');
      setScripts(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat script');
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const categories = Array.from(new Set(scripts.map(s => s.category).filter(Boolean)));
  const filtered = filter === 'all' ? scripts : scripts.filter(s => s.category === filter);

  if (selected) {
    return (
      <ScriptDetail script={selected} onBack={() => setSelected(null)} />
    );
  }

  if (loading) {
    return (
      <div className="p-6 text-center" data-testid="scripts-loading">
        <Loader2 className="animate-spin mx-auto text-teal-600" size={28} />
        <p className="text-sm text-muted-foreground mt-3">Memuat script...</p>
      </div>
    );
  }

  return (
    <div className="pb-24" data-testid="scripts-tab">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Library Script</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{scripts.length} script tersedia</p>
        </div>
        <button
          onClick={load}
          data-testid="scripts-refresh-button"
          className="p-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-muted-foreground transition"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Category chips */}
      {categories.length > 0 && (
        <div className="px-4 py-2 overflow-x-auto whitespace-nowrap flex gap-2 -mx-0">
          <button
            onClick={() => setFilter('all')}
            data-testid="script-filter-all"
            className={`text-xs px-3 py-1.5 rounded-full border transition ${
              filter === 'all'
                ? 'bg-teal-100 border-teal-500/40 text-teal-200'
                : 'bg-foreground/5 border-border text-muted-foreground hover:bg-foreground/10'
            }`}
          >
            Semua ({scripts.length})
          </button>
          {categories.map(c => {
            const n = scripts.filter(s => s.category === c).length;
            return (
              <button
                key={c}
                onClick={() => setFilter(c)}
                data-testid={`script-filter-${c}`}
                className={`text-xs px-3 py-1.5 rounded-full border transition capitalize ${
                  filter === c
                    ? 'bg-teal-100 border-teal-500/40 text-teal-200'
                    : 'bg-foreground/5 border-border text-muted-foreground hover:bg-foreground/10'
                }`}
              >
                {String(c).replace(/_/g, ' ')} ({n})
              </button>
            );
          })}
        </div>
      )}

      <div className="px-4 mt-2 space-y-2">
        {filtered.map(s => (
          <button
            key={s.id}
            onClick={() => setSelected(s)}
            data-testid={`script-card-${s.id}`}
            className="w-full text-left rounded-xl bg-card border border-border hover:border-teal-400 hover:bg-card p-3.5 transition group"
          >
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <FileText size={14} className="text-teal-600 shrink-0" />
                  <span className="text-sm font-medium text-foreground truncate">{s.title}</span>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 leading-snug">
                  {s.script_text}
                </p>
                <div className="flex items-center gap-1.5 mt-2">
                  <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent/60 text-foreground capitalize">
                    {String(s.category || '').replace(/_/g, ' ')}
                  </span>
                  {s.language && (
                    <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent/60 text-foreground">
                      {s.language}
                    </span>
                  )}
                </div>
              </div>
              <ChevronRight size={16} className="text-muted-foreground group-hover:text-teal-600 transition shrink-0" />
            </div>
          </button>
        ))}

        {filtered.length === 0 && (
          <div className="px-4 py-12 text-center" data-testid="scripts-empty-state">
            <FileText className="mx-auto text-foreground/70 mb-3" size={36} />
            <p className="text-sm text-muted-foreground">Belum ada script tersedia</p>
          </div>
        )}
      </div>
    </div>
  );
}

function ScriptDetail({ script, onBack }) {
  return (
    <div className="pb-24" data-testid="script-detail-page">
      <div className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur border-b border-border px-4 py-3 flex items-center gap-3">
        <button
          onClick={onBack}
          data-testid="script-detail-back-button"
          className="p-2 -ml-2 rounded-lg hover:bg-foreground/5 text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-foreground truncate">{script.title}</h2>
          <p className="text-[11px] text-muted-foreground capitalize">
            {String(script.category || '').replace(/_/g, ' ')} · {script.language || '—'}
          </p>
        </div>
      </div>
      <div className="px-4 py-4">
        <div className="rounded-xl bg-card border border-border p-4">
          <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed" data-testid="script-content">
            {script.script_text}
          </p>
        </div>
        {Array.isArray(script.products_applicable) && script.products_applicable.length > 0 && (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-wide font-semibold text-muted-foreground mb-2">Produk Terkait</p>
            <div className="flex flex-wrap gap-1.5">
              {script.products_applicable.map(p => (
                <span
                  key={p}
                  className="text-xs px-2 py-1 rounded-full bg-teal-100 border border-teal-300 text-teal-200 capitalize"
                  data-testid={`script-product-${p}`}
                >
                  {p.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRAINING TAB
// ═══════════════════════════════════════════════════════════════════════════════
function TrainingTab({ token }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiCall(token, '/api/marketing/livehost/portal/training');
      setList(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat training');
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const complete = useCallback(async (progressId) => {
    setBusyId(progressId);
    try {
      const r = await apiCall(token, `/api/marketing/livehost/portal/training/${progressId}/complete`, {
        method: 'POST',
      });
      toast.success(r?.message || 'Training selesai!');
      await load();
    } catch (e) {
      toast.error(e.message || 'Gagal menyelesaikan training');
    } finally { setBusyId(null); }
  }, [token, load]);

  if (loading) {
    return (
      <div className="p-6 text-center" data-testid="training-loading">
        <Loader2 className="animate-spin mx-auto text-teal-600" size={28} />
        <p className="text-sm text-muted-foreground mt-3">Memuat training...</p>
      </div>
    );
  }

  const pending = list.filter(t => t.status !== 'completed');
  const completed = list.filter(t => t.status === 'completed');

  return (
    <div className="pb-24" data-testid="training-tab">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Training Saya</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {completed.length} selesai · {pending.length} tersedia
          </p>
        </div>
        <button
          onClick={load}
          data-testid="training-refresh-button"
          className="p-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-muted-foreground transition"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Pending */}
      {pending.length > 0 && (
        <div className="px-4 mb-5">
          <h3 className="text-xs uppercase tracking-wide font-semibold text-amber-700 mb-2">
            Belum Selesai
          </h3>
          <div className="space-y-2">
            {pending.map(p => (
              <TrainingCard
                key={p.id}
                progress={p}
                busy={busyId === p.id}
                onComplete={() => complete(p.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Completed */}
      {completed.length > 0 && (
        <div className="px-4">
          <h3 className="text-xs uppercase tracking-wide font-semibold text-teal-600 mb-2">
            Selesai ({completed.length})
          </h3>
          <div className="space-y-2">
            {completed.map(p => (
              <TrainingCard key={p.id} progress={p} readonly />
            ))}
          </div>
        </div>
      )}

      {list.length === 0 && (
        <div className="px-4 py-12 text-center" data-testid="training-empty-state">
          <GraduationCap className="mx-auto text-foreground/70 mb-3" size={36} />
          <p className="text-sm text-muted-foreground">Belum ada training di-assign</p>
        </div>
      )}
    </div>
  );
}

function TrainingCard({ progress, readonly, busy, onComplete }) {
  const t = progress.training_detail || {};
  const isCompleted = progress.status === 'completed';
  return (
    <div
      className={`rounded-xl border p-3.5 ${
        isCompleted
          ? 'bg-teal-100 border-teal-300'
          : 'bg-card border-border'
      }`}
      data-testid={`training-card-${progress.id}`}
    >
      <div className="flex items-start gap-3">
        <div className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${
          isCompleted ? 'bg-teal-100 text-teal-600' : 'bg-accent/60 text-foreground'
        }`}>
          {isCompleted ? <Award size={16} /> : <GraduationCap size={16} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-medium text-foreground">{progress.training_title || t.title}</span>
            {isCompleted && <BadgeCheck size={14} className="text-teal-600" />}
          </div>
          {t.description && (
            <p className="text-xs text-muted-foreground line-clamp-2 leading-snug mb-1.5">
              {t.description}
            </p>
          )}
          <div className="flex items-center gap-2 flex-wrap text-[10px]">
            {t.category && (
              <span className="px-1.5 py-0.5 rounded bg-accent/60 text-foreground uppercase tracking-wide capitalize">
                {String(t.category).replace(/_/g, ' ')}
              </span>
            )}
            {t.content_type && (
              <span className="px-1.5 py-0.5 rounded bg-accent/60 text-foreground uppercase tracking-wide">
                {t.content_type}
              </span>
            )}
            {t.duration_minutes && (
              <span className="px-1.5 py-0.5 rounded bg-accent/60 text-foreground inline-flex items-center gap-1">
                <Clock size={9} /> {t.duration_minutes} mnt
              </span>
            )}
            {t.is_required && !isCompleted && (
              <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-300 uppercase tracking-wide">
                Wajib
              </span>
            )}
          </div>
          {isCompleted && progress.completed_at && (
            <p className="text-[10px] text-teal-600 mt-1.5">
              Selesai {formatDate(progress.completed_at)}
            </p>
          )}
          {!isCompleted && !readonly && (
            <button
              onClick={onComplete}
              disabled={busy}
              data-testid={`training-complete-button-${progress.id}`}
              className="mt-2.5 px-3 py-1.5 rounded-lg bg-teal-100 border border-teal-400 text-teal-200 text-xs font-medium hover:bg-teal-100 dark:bg-teal-500/25 disabled:opacity-50 transition inline-flex items-center gap-1.5"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
              Tandai Selesai
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// NOTIFICATIONS TAB
// ═══════════════════════════════════════════════════════════════════════════════
function NotificationsTab({ token, notifications, unreadCount, onMarkAllRead, onMarkRead, onRefresh }) {
  return (
    <div className="pb-24" data-testid="notifications-tab">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground tracking-tight">Notifikasi</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {unreadCount > 0 ? `${unreadCount} belum dibaca` : 'Semua sudah dibaca'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            data-testid="notifications-refresh-button"
            className="p-2 rounded-lg bg-foreground/5 hover:bg-foreground/10 text-muted-foreground transition"
          >
            <RefreshCw size={16} />
          </button>
          {unreadCount > 0 && (
            <button
              onClick={onMarkAllRead}
              data-testid="notifications-mark-all-read"
              className="px-3 py-1.5 rounded-lg bg-teal-100 border border-teal-400 text-teal-200 text-xs font-medium hover:bg-teal-100 dark:bg-teal-500/25 transition"
            >
              Mark all read
            </button>
          )}
        </div>
      </div>

      <div className="px-4 space-y-2">
        {notifications.length === 0 && (
          <div className="py-12 text-center" data-testid="notifications-empty-state">
            <Bell className="mx-auto text-foreground/70 mb-3" size={36} />
            <p className="text-sm text-muted-foreground">Belum ada notifikasi</p>
            <p className="text-xs text-muted-foreground mt-1">Notifikasi shift & training akan muncul di sini</p>
          </div>
        )}

        {notifications.map(n => (
          <NotificationRow
            key={n.id}
            notif={n}
            onMarkRead={() => n.id && !String(n.id).startsWith('derived-') && onMarkRead(n.id)}
          />
        ))}
      </div>
    </div>
  );
}

function NotificationRow({ notif, onMarkRead }) {
  const sevMap = {
    info:    { c: 'text-teal-600 bg-teal-100 border-teal-300', Icon: CircleDot },
    success: { c: 'text-emerald-700 bg-emerald-100 dark:bg-emerald-500/10 border-emerald-300', Icon: CheckCircle2 },
    warning: { c: 'text-amber-700 bg-amber-100 dark:bg-amber-500/10 border-amber-300', Icon: AlertCircle },
    error:   { c: 'text-red-700 bg-red-100 border-red-300', Icon: AlertCircle },
  };
  const cfg = sevMap[notif.severity] || sevMap.info;
  const Icon = cfg.Icon;
  return (
    <div
      onClick={notif.read ? undefined : onMarkRead}
      data-testid={`notification-row-${notif.id}`}
      className={`rounded-xl border p-3 transition cursor-pointer ${
        notif.read
          ? 'bg-accent/40 border-border'
          : 'bg-accent/70 border-teal-300 hover:border-teal-500/40'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center border ${cfg.c}`}>
          <Icon size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-medium text-foreground truncate">{notif.title}</span>
            {!notif.read && <span className="inline-block w-1.5 h-1.5 rounded-full bg-teal-400" />}
          </div>
          <p className="text-xs text-muted-foreground leading-snug">{notif.message}</p>
          <p className="text-[10px] text-muted-foreground mt-1.5">
            {formatDate(notif.created_at, true)}
          </p>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PROFILE TAB
// ═══════════════════════════════════════════════════════════════════════════════
function ProfileTab({ token, host, onLogout }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiCall(token, '/api/marketing/livehost/portal/my-profile');
      setProfile(data);
    } catch (e) {
      toast.error(e.message || 'Gagal memuat profile');
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="p-6 text-center" data-testid="profile-loading">
        <Loader2 className="animate-spin mx-auto text-teal-600" size={28} />
        <p className="text-sm text-muted-foreground mt-3">Memuat profile...</p>
      </div>
    );
  }

  const p = profile || {};
  return (
    <div className="pb-24" data-testid="profile-tab">
      {/* Header card */}
      <div className="px-4 pt-6 pb-5">
        <div className="rounded-2xl bg-gradient-to-br from-teal-500/15 via-zinc-900/80 to-zinc-900/80 border border-teal-300 p-5 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-500 mb-3 shadow-lg">
            <Radio size={26} className="text-foreground" />
          </div>
          <h2 className="text-lg font-semibold text-foreground" data-testid="profile-host-name">{p.name || host.host_name}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{p.email || host.email}</p>
          <div className="flex items-center justify-center gap-2 mt-3">
            <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-teal-100 text-teal-200 border border-teal-400 capitalize">
              {p.employment_type || '—'}
            </span>
            {p.hourly_rate > 0 && (
              <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-accent/60 text-foreground">
                {fmtRp(p.hourly_rate)}/jam
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Info rows */}
      <div className="px-4 space-y-2 mb-4">
        <InfoRow icon={User} label="Nama" value={p.name || '—'} testid="profile-info-name" />
        <InfoRow icon={Mic2} label="Phone" value={p.phone || '—'} testid="profile-info-phone" />
        <InfoRow icon={Video} label="Bahasa" value={(p.language_skills || []).join(', ') || '—'} testid="profile-info-language" />
        <InfoRow icon={Trophy} label="Expertise" value={(p.product_expertise || []).join(', ') || '—'} testid="profile-info-expertise" />
        <InfoRow
          icon={MapPin}
          label="Account di-assign"
          value={Array.isArray(p.assigned_accounts) && p.assigned_accounts.length > 0
            ? p.assigned_accounts.map(a => a.account_name).join(', ')
            : '—'}
          testid="profile-info-accounts"
        />
      </div>

      {/* Logout */}
      <div className="px-4">
        <button
          onClick={onLogout}
          data-testid="profile-logout-button"
          className="w-full py-3 rounded-xl bg-red-100 border border-red-400 dark:border-red-500/30 text-red-700 hover:bg-red-100 dark:bg-red-500/25 text-sm font-medium transition flex items-center justify-center gap-2"
        >
          <LogOut size={16} /> Keluar
        </button>
      </div>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value, testid }) {
  return (
    <div
      className="rounded-xl bg-card border border-border px-3.5 py-2.5 flex items-center gap-3"
      data-testid={testid}
    >
      <div className="shrink-0 w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-teal-600">
        <Icon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className="text-sm text-foreground truncate">{value}</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN SHELL (with SSE + bottom nav)
// ═══════════════════════════════════════════════════════════════════════════════
function LiveHostShell({ token, host, onLogout }) {
  const [tab, setTab] = useState('shifts');
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const sseRef = useRef(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await apiCall(token, '/api/marketing/livehost/portal/notifications');
      setNotifications(Array.isArray(data?.notifications) ? data.notifications : []);
      setUnreadCount(data?.unread_count || 0);
    } catch (e) {
      // silent fail; SSE will keep working
      console.warn('[notif] fetch failed', e.message);
    }
  }, [token]);

  // Initial fetch
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // SSE connection
  useEffect(() => {
    if (!token) return;
    // Close previous
    if (sseRef.current) {
      try { sseRef.current.close(); } catch { /* noop */ }
      sseRef.current = null;
    }

    const url = `${API}/api/marketing/livehost/portal/notifications/stream?token=${encodeURIComponent(token)}`;
    let es;
    try {
      es = new EventSource(url);
      sseRef.current = es;
    } catch (e) {
      console.warn('[sse] failed to open', e);
      return;
    }

    es.addEventListener('ready', () => {
      // connected
    });
    es.addEventListener('notification', (ev) => {
      try {
        const n = JSON.parse(ev.data);
        setNotifications(prev => [n, ...prev].slice(0, 100));
        setUnreadCount(c => c + 1);
        toast(n.title || 'Notifikasi baru', {
          description: n.message,
        });
      } catch { /* noop */ }
    });
    es.addEventListener('ping', () => { /* heartbeat */ });
    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do
    };

    return () => {
      try { es.close(); } catch { /* noop */ }
    };
  }, [token]);

  const onMarkRead = useCallback(async (notifId) => {
    if (!notifId || String(notifId).startsWith('derived-')) return;
    try {
      await apiCall(token, `/api/marketing/livehost/portal/notifications/${notifId}/read`, {
        method: 'POST',
      });
      setNotifications(prev => prev.map(n => n.id === notifId ? { ...n, read: true } : n));
      setUnreadCount(c => Math.max(0, c - 1));
    } catch (e) {
      toast.error(e.message || 'Gagal menandai sebagai dibaca');
    }
  }, [token]);

  const onMarkAllRead = useCallback(async () => {
    try {
      await apiCall(token, '/api/marketing/livehost/portal/notifications/mark-all-read', {
        method: 'POST',
      });
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
      toast.success('Semua notifikasi ditandai dibaca');
    } catch (e) {
      toast.error(e.message || 'Gagal mark all read');
    }
  }, [token]);

  return (
    <div
      data-testid="livehost-portal-shell"
      className="min-h-screen text-foreground bg-gradient-to-br from-teal-50 via-background to-emerald-50"
    >
      {/* Top header */}
      <header className="sticky top-0 z-20 bg-card/95 backdrop-blur border-b border-border px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-emerald-500 flex items-center justify-center shadow-md">
            <Radio size={15} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground leading-none">LiveHost Portal</h1>
            <p className="text-[10px] text-muted-foreground mt-0.5" data-testid="header-host-name">
              {host?.host_name || 'Host'}
            </p>
          </div>
        </div>
        <button
          onClick={() => setTab('notifications')}
          data-testid="header-notifications-button"
          className="relative p-2 rounded-lg bg-accent hover:bg-accent/80 text-foreground transition"
        >
          <Bell size={16} />
          {unreadCount > 0 && (
            <span
              data-testid="notification-badge"
              className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full bg-teal-500 text-[9px] font-bold text-white flex items-center justify-center"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>
      </header>

      {/* Tab content */}
      <main className="max-w-md mx-auto" data-testid="portal-main-content">
        {tab === 'shifts'        && <ShiftsTab token={token} host={host} onRefreshNotif={fetchNotifications} />}
        {tab === 'scripts'       && <ScriptsTab token={token} />}
        {tab === 'training'      && <TrainingTab token={token} />}
        {tab === 'notifications' && (
          <NotificationsTab
            token={token}
            notifications={notifications}
            unreadCount={unreadCount}
            onMarkAllRead={onMarkAllRead}
            onMarkRead={onMarkRead}
            onRefresh={fetchNotifications}
          />
        )}
        {tab === 'profile'       && <ProfileTab token={token} host={host} onLogout={onLogout} />}
      </main>

      {/* Bottom tab bar (mobile-first) */}
      <nav
        data-testid="bottom-tab-nav"
        className="fixed bottom-0 inset-x-0 z-30 bg-card/95 backdrop-blur border-t border-border px-2 py-1.5"
      >
        <div className="max-w-md mx-auto grid grid-cols-5 gap-1">
          <TabButton id="shifts"        label="Shift"        icon={Calendar}      tab={tab} setTab={setTab} />
          <TabButton id="scripts"       label="Script"       icon={FileText}      tab={tab} setTab={setTab} />
          <TabButton id="training"      label="Training"     icon={GraduationCap} tab={tab} setTab={setTab} />
          <TabButton id="notifications" label="Notif"        icon={Bell}          tab={tab} setTab={setTab} badge={unreadCount} />
          <TabButton id="profile"       label="Profile"      icon={User}          tab={tab} setTab={setTab} />
        </div>
      </nav>
    </div>
  );
}

function TabButton({ id, label, icon: Icon, tab, setTab, badge }) {
  const active = tab === id;
  return (
    <button
      onClick={() => setTab(id)}
      data-testid={`tab-button-${id}`}
      className={`relative flex flex-col items-center justify-center gap-0.5 py-1.5 rounded-lg transition ${
        active
          ? 'text-teal-600 bg-teal-50'
          : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      <Icon size={18} />
      <span className="text-[10px] font-medium">{label}</span>
      {badge > 0 && (
        <span className="absolute top-0.5 right-2.5 min-w-[14px] h-[14px] px-1 rounded-full bg-teal-500 text-[8px] font-bold text-white flex items-center justify-center">
          {badge > 9 ? '9+' : badge}
        </span>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════════════════════
export default function LiveHostPortalApp() {
  const [token, setToken] = useState(null);
  const [host, setHost] = useState(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    const s = session.load();
    if (s.token && s.host) {
      setToken(s.token);
      setHost(s.host);
    }
    setBootstrapped(true);
  }, []);

  const handleLogin = useCallback((tokenData, hostData) => {
    setToken(tokenData);
    setHost(hostData);
  }, []);

  const handleLogout = useCallback(() => {
    session.clear();
    setToken(null);
    setHost(null);
    toast.success('Berhasil keluar');
  }, []);

  if (!bootstrapped) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="animate-spin text-teal-600" size={28} />
      </div>
    );
  }

  if (!token || !host) {
    return <LiveHostLogin onLogin={handleLogin} />;
  }

  return <LiveHostShell token={token} host={host} onLogout={handleLogout} />;
}
