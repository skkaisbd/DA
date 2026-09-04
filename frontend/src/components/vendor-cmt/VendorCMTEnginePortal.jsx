/**
 * VendorCMTEnginePortal — Portal Vendor CMT (Engine SOMMERVILLE, FASE 5)
 * Route: /vendor-cmt — login khusus role cmt_vendor, lalu render
 * VendorPortalApp (engine baru): receiving, inspeksi, material requests,
 * jobs, progress, defect, buyer shipments, serial, variance, reminders.
 */
import { useEffect, useState } from 'react';
import { Truck, Lock, Mail, Loader2 } from 'lucide-react';
import VendorPortalApp from '../erp/engine/VendorPortalApp';

const API = process.env.REACT_APP_BACKEND_URL;

export default function VendorCMTEnginePortal() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [checking, setChecking] = useState(true);
  const [form, setForm] = useState({ email: '', password: '' });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem('erp_token');
    const u = localStorage.getItem('erp_user');
    if (t && u) {
      try {
        const parsed = JSON.parse(u);
        if (parsed?.role === 'cmt_vendor') { setToken(t); setUser(parsed); }
      } catch (e) { /* ignore */ }
    }
    setChecking(false);
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setErr(''); setLoading(true);
    try {
      const r = await fetch(`${API}/api/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Login gagal');
      const tok = data.token || data.access_token;
      // FASE 22 — JANGAN buat jalan buntu. Dulu akun non-vendor yang benar
      // kredensialnya tetap DITOLAK di sini ("Akun ini bukan akun Vendor CMT")
      // tanpa jalan keluar: sesudah vendor logout, layar ini yang muncul,
      // sehingga admin/owner TERKUNCI di form login vendor (harus tahu trik
      // hapus localStorage). Sekarang: sesi tetap dipakai lalu dialihkan ke
      // aplikasi utama sesuai perannya.
      if (data.user?.role !== 'cmt_vendor') {
        localStorage.setItem('erp_token', tok);
        localStorage.setItem('erp_user', JSON.stringify(data.user));
        setErr('Akun ini bukan Vendor CMT — mengalihkan ke aplikasi utama…');
        window.location.replace('/');
        return;
      }
      localStorage.setItem('erp_token', tok);
      localStorage.setItem('erp_user', JSON.stringify(data.user));
      setToken(tok); setUser(data.user);
    } catch (ex) { setErr(ex.message); }
    finally { setLoading(false); }
  };

  const handleLogout = () => {
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
    localStorage.removeItem('erp_portal');
    setToken(null); setUser(null);
    // Muat ulang ke akar aplikasi: kalau hanya state lokal yang dibersihkan,
    // App.js masih memegang `user` role cmt_vendor → komponen ini terus
    // dirender dan pengguna terperangkap di form login vendor.
    window.location.replace('/');
  };

  const backToMainApp = () => {
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
    localStorage.removeItem('erp_portal');
    window.location.replace('/');
  };

  if (checking) return null;

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-emerald-950 px-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-2xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-emerald-600 rounded-xl flex items-center justify-center">
              <Truck className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">Portal Vendor CMT</h1>
              <p className="text-xs text-muted-foreground">CV. Dewi Aditya — Engine Produksi</p>
            </div>
          </div>
          <form onSubmit={handleLogin} className="space-y-4">
            {err && <div data-testid="vendor-login-error" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</div>}
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Email</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <input data-testid="vendor-login-email" required type="email" className="w-full border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="cmtvendor@dewiaditya.id" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <input data-testid="vendor-login-password" required type="password" className="w-full border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="••••••••" />
              </div>
            </div>
            <button data-testid="vendor-login-submit" disabled={loading} type="submit"
              className="w-full bg-emerald-600 text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-emerald-700 transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />} Masuk Portal Vendor
            </button>
          </form>
          <button type="button" onClick={backToMainApp} data-testid="vendor-login-back-main"
            className="mt-4 w-full text-center text-xs text-muted-foreground hover:text-emerald-700 underline">
            Bukan vendor CMT? Masuk ke aplikasi utama
          </button>
        </div>
      </div>
    );
  }

  return <VendorPortalApp user={user} token={token} onLogout={handleLogout} />;
}
