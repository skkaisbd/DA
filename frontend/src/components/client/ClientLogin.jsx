import { useState } from 'react';
import { motion } from 'framer-motion';
import { Eye, EyeOff, LogIn, Loader2, Shirt } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clientApi } from './clientApi';

export default function ClientLogin({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await clientApi.request('/auth/login', {
        method: 'POST',
        body: { email, password },
      });
      clientApi.saveSession(data.token, data.user);
      onLogin(data.token, data.user);
    } catch (err) {
      setError(err.message || 'Login gagal');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-stretch bg-[hsl(var(--background))] noise-overlay"
      data-testid="client-login-page"
    >
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between px-16 py-16 relative overflow-hidden bg-gradient-to-br from-[hsl(var(--primary))]/15 via-transparent to-transparent">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex items-center gap-3 mb-10">
            <div className="w-12 h-12 rounded-2xl bg-[hsl(var(--primary))]/25 border border-[hsl(var(--primary))]/40 flex items-center justify-center">
              <Shirt size={24} className="text-[hsl(var(--primary))]" strokeWidth={2.2} />
            </div>
            <div className="text-xs uppercase tracking-[0.18em] text-foreground/50">
              Portal Klien Maklon
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tight text-foreground leading-tight mb-5">
            Pantau order maklon Anda<br />
            <span className="text-[hsl(var(--primary))]">secara real-time.</span>
          </h1>
          <p className="text-lg text-foreground/60 max-w-md leading-relaxed">
            Lihat progress produksi, approve sample, akses laporan QC, dan kelola invoice — semuanya dalam satu portal aman milik CV. Dewi Aditya.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="grid grid-cols-3 gap-4 max-w-md"
        >
          {[
            { label: 'Order Tracking', detail: 'Stage by stage' },
            { label: 'Sample Approval', detail: 'Direct feedback' },
            { label: 'Invoice & Bayar', detail: 'Aging clear' },
          ].map((f) => (
            <div
              key={f.label}
              className="rounded-xl border border-foreground/10 bg-foreground/5 px-3 py-4"
            >
              <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-1">
                {f.detail}
              </div>
              <div className="text-sm font-medium text-foreground">{f.label}</div>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Right login form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-16">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="w-full max-w-md"
        >
          <div className="lg:hidden text-center mb-8">
            <div className="w-14 h-14 rounded-2xl bg-[hsl(var(--primary))]/25 border border-[hsl(var(--primary))]/40 flex items-center justify-center mx-auto mb-4">
              <Shirt size={26} className="text-[hsl(var(--primary))]" />
            </div>
            <h1 className="text-2xl font-bold text-foreground">Portal Klien Maklon</h1>
            <p className="text-sm text-foreground/50 mt-1">CV. Dewi Aditya</p>
          </div>

          <div className="rounded-2xl border border-foreground/10 bg-foreground/[0.03] backdrop-blur p-8">
            <h2
              className="text-xl font-semibold text-foreground mb-1"
              data-testid="client-login-title"
            >
              Masuk Portal Klien
            </h2>
            <p className="text-sm text-foreground/50 mb-6">
              Gunakan email dan password yang diberikan tim CV. Dewi Aditya.
            </p>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-400/10 border border-red-300/20 rounded-xl p-3 mb-4"
              >
                <p className="text-red-300 text-sm" data-testid="client-login-error">
                  {error}
                </p>
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs uppercase tracking-wider text-foreground/50 mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="klien@perusahaanmu.id"
                  className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] px-4 py-3 text-foreground placeholder-foreground/30 focus:outline-none focus:border-[hsl(var(--primary))]/60 transition"
                  data-testid="client-login-email"
                />
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider text-foreground/50 mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] px-4 py-3 pr-11 text-foreground placeholder-foreground/30 focus:outline-none focus:border-[hsl(var(--primary))]/60 transition"
                    data-testid="client-login-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-foreground/40 hover:text-foreground/70"
                    data-testid="client-login-toggle-password"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                disabled={loading}
                className="w-full gap-2"
                data-testid="client-login-submit"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
                {loading ? 'Memproses...' : 'Masuk Portal'}
              </Button>
            </form>

            <div className="mt-6 pt-6 border-t border-foreground/10">
              <p className="text-xs text-foreground/50 leading-relaxed">
                Belum punya akun portal? Hubungi admin CV. Dewi Aditya untuk
                mendapatkan kredensial akses Anda.
              </p>
            </div>
          </div>

          <div className="mt-6 text-center">
            <a
              href="/"
              className="text-xs text-foreground/40 hover:text-foreground/70"
              data-testid="client-login-internal-link"
            >
              Login internal staff →
            </a>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
