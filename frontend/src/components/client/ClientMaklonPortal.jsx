/**
 * ClientMaklonPortal — Tracking read-only untuk klien maklon (FASE 5)
 * Route: /klien-maklon — login role klien_maklon (main ERP auth),
 * data via /api/maklon-client/pos (+ /{po_id}/tracking). TANPA tombol write.
 */
import { useEffect, useState, useCallback } from 'react';
import { Shirt, Lock, Mail, Loader2, ArrowLeft, LogOut, PackageCheck, Truck } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

async function cget(path, token) {
  const r = await fetch(`${API}/api${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

function Bar({ pct }) {
  return (
    <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
      <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${Math.min(100, pct || 0)}%` }} />
    </div>
  );
}

export default function ClientMaklonPortal() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [form, setForm] = useState({ email: '', password: '' });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [pos, setPos] = useState([]);
  const [tracking, setTracking] = useState(null);
  const [fetchErr, setFetchErr] = useState('');

  useEffect(() => {
    const t = localStorage.getItem('erp_token');
    const u = localStorage.getItem('erp_user');
    if (t && u) {
      try {
        const parsed = JSON.parse(u);
        if (parsed?.role === 'klien_maklon') { setToken(t); setUser(parsed); }
      } catch (e) { /* ignore */ }
    }
  }, []);

  const loadPos = useCallback(async (tok) => {
    try { setFetchErr(''); setPos(await cget('/maklon-client/pos', tok)); }
    catch (e) { setFetchErr(e.message); }
  }, []);

  useEffect(() => { if (token) loadPos(token); }, [token, loadPos]);

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
      // FASE 22 — sama seperti Portal Vendor: jangan buat jalan buntu untuk akun
      // non-klien (dulu ditolak tanpa jalan keluar sesudah klien logout).
      if (data.user?.role !== 'klien_maklon') {
        localStorage.setItem('erp_token', tok);
        localStorage.setItem('erp_user', JSON.stringify(data.user));
        setErr('Akun ini bukan klien maklon — mengalihkan ke aplikasi utama…');
        window.location.replace('/');
        return;
      }
      localStorage.setItem('erp_token', tok);
      localStorage.setItem('erp_user', JSON.stringify(data.user));
      setToken(tok); setUser(data.user);
    } catch (ex) { setErr(ex.message); }
    finally { setLoading(false); }
  };

  const openTracking = async (poId) => {
    try { setTracking(await cget(`/maklon-client/pos/${poId}/tracking`, token)); }
    catch (e) { setFetchErr(e.message); }
  };

  const logout = () => {
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
    localStorage.removeItem('erp_portal');
    setToken(null); setUser(null); setPos([]); setTracking(null);
    window.location.replace('/');
  };

  const backToMainApp = () => {
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
    localStorage.removeItem('erp_portal');
    window.location.replace('/');
  };

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-950 px-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-2xl p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center"><Shirt className="w-6 h-6 text-white" /></div>
            <div>
              <h1 className="text-lg font-bold text-foreground">Tracking Maklon</h1>
              <p className="text-xs text-muted-foreground">CV. Dewi Aditya — Portal Klien</p>
            </div>
          </div>
          <form onSubmit={handleLogin} className="space-y-4">
            {err && <div data-testid="client-login-error" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</div>}
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Email</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <input data-testid="client-login-email" required type="email" className="w-full border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="klienmaklon@dewiaditya.id" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground/90 mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                <input data-testid="client-login-password" required type="password" className="w-full border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="••••••••" />
              </div>
            </div>
            <button data-testid="client-login-submit" disabled={loading} type="submit"
              className="w-full bg-indigo-600 text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />} Masuk
            </button>
          </form>
          <button type="button" onClick={backToMainApp} data-testid="client-login-back-main"
            className="mt-4 w-full text-center text-xs text-muted-foreground hover:text-indigo-700 underline">
            Bukan klien maklon? Masuk ke aplikasi utama
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/40">
      <header className="bg-indigo-900 text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shirt className="w-6 h-6" />
          <div>
            <h1 className="font-bold text-sm">Tracking Produksi Maklon</h1>
            <p className="text-xs text-indigo-300">{user.name}</p>
          </div>
        </div>
        <button data-testid="client-logout-btn" onClick={logout} className="flex items-center gap-2 text-sm text-indigo-200 hover:text-white">
          <LogOut className="w-4 h-4" /> Keluar
        </button>
      </header>

      <main className="max-w-5xl mx-auto p-6">
        {fetchErr && <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{fetchErr}</div>}

        {!tracking ? (
          <div data-testid="client-po-list">
            <h2 className="text-base font-semibold text-foreground mb-4">Purchase Order Anda</h2>
            {pos.length === 0 && <p className="text-sm text-muted-foreground italic">Belum ada PO maklon.</p>}
            <div className="grid gap-4">
              {pos.map(po => (
                <button key={po.po_id} data-testid={`client-po-${po.po_number}`} onClick={() => openTracking(po.po_id)}
                  className="text-left bg-card rounded-xl border border-border p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono font-semibold text-sm text-foreground">{po.po_number}</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700">{po.status}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-3 text-xs text-muted-foreground mb-2">
                    <span>Order: <strong className="text-foreground">{po.total_ordered}</strong> pcs</span>
                    <span>Produksi: <strong className="text-foreground">{po.total_produced}</strong></span>
                    <span>Dikirim: <strong className="text-foreground">{po.total_shipped}</strong></span>
                    <span>Diterima: <strong className="text-foreground">{po.total_received}</strong></span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Bar pct={po.progress_pct} />
                    <span className="text-xs font-semibold text-emerald-600 w-10 text-right">{po.progress_pct}%</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div data-testid="client-po-tracking">
            <button data-testid="client-tracking-back" onClick={() => setTracking(null)} className="flex items-center gap-1 text-sm text-indigo-600 hover:text-indigo-800 mb-4">
              <ArrowLeft className="w-4 h-4" /> Kembali ke daftar PO
            </button>
            <div className="bg-card rounded-xl border border-border p-5 mb-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-mono font-bold text-foreground">{tracking.po_number}</h2>
                <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700">{tracking.status}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-muted-foreground border-b border-border">
                    <th className="py-2 pr-3">Produk</th><th className="py-2 pr-3">SKU</th><th className="py-2 pr-3">Order</th>
                    <th className="py-2 pr-3">Produksi</th><th className="py-2 pr-3">Dikirim</th><th className="py-2 pr-3">Diterima</th><th className="py-2">Progress</th>
                  </tr></thead>
                  <tbody>
                    {(tracking.items || []).map(it => (
                      <tr key={it.po_item_id} className="border-b border-border/60">
                        <td className="py-2 pr-3 text-foreground">{it.product_name} <span className="text-xs text-muted-foreground">{it.size}/{it.color}</span></td>
                        <td className="py-2 pr-3 font-mono text-xs">{it.sku}</td>
                        <td className="py-2 pr-3">{it.ordered_qty}</td>
                        <td className="py-2 pr-3">{it.produced_qty}</td>
                        <td className="py-2 pr-3">{it.shipped_qty}</td>
                        <td className="py-2 pr-3">{it.received_qty}</td>
                        <td className="py-2 w-32"><div className="flex items-center gap-2"><Bar pct={it.progress_pct} /><span className="text-xs">{it.progress_pct}%</span></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="bg-card rounded-xl border border-border p-5">
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2"><Truck className="w-4 h-4 text-indigo-500" /> Pengiriman Bertahap (Surat Jalan)</h3>
              {(tracking.dispatches || []).length === 0 && <p className="text-sm text-muted-foreground italic">Belum ada pengiriman.</p>}
              <div className="space-y-3">
                {(tracking.dispatches || []).map((d, i) => (
                  <div key={i} className="border border-border rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs font-semibold text-foreground">{d.shipment_number} — dispatch #{d.dispatch_seq}</span>
                      <span className="flex items-center gap-1 text-xs text-emerald-600"><PackageCheck className="w-3.5 h-3.5" />{d.status}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{(d.dispatch_date || '').slice(0, 10)} — total {d.total_qty} pcs</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
