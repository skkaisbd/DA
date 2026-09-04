import { useState } from 'react';
import { motion } from 'framer-motion';
import { Eye, EyeOff, LogIn, Loader2 } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import apiFetch from '@/lib/apiFetch';

export default function Login({ onLogin }) {
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
      const data = await apiFetch('/auth/login', {
        method: 'POST',
        body: { email, password },
        token: null, // No token needed for login
        skipOnUnauthorized: true, // Prevent premature logout on 401 during login
      });
      // 2026-08-05 (RBAC): `portals` & `hidden_modules` dikirim server di level
      // atas respons — ikutkan ke objek user supaya App menyimpan akses efektif.
      onLogin(data.token, {
        ...data.user,
        portals: data.portals || [],
        hidden_modules: data.hidden_modules || data.user?.hidden_modules || [],
      });
    } catch (err) {
      setError(err.detail || err.message || 'Login gagal');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ambient noise-overlay flex" data-testid="login-page">
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-center px-16 xl:px-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[hsl(174,70%,55%)]/10 via-transparent to-transparent" />
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="relative z-10"
        >
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-2xl bg-[hsl(var(--primary))]/20 border border-[hsl(var(--primary))]/30 flex items-center justify-center">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="hsl(174, 70%, 55%)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.38 3.46 16 2 12 5.5 8 2 3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>
              </svg>
            </div>
          </div>
          <h1 className="text-5xl xl:text-6xl font-bold tracking-tight text-foreground mb-4 leading-tight">
            Sistem<br />
            <span className="text-[hsl(var(--primary))]">CV. Dewi Aditya</span>
          </h1>
          <p className="text-lg text-foreground/60 max-w-md leading-relaxed">
            Sistem ERP terintegrasi untuk Online Shop, Maklon, dan SDM — Cutting · CMT · QC · Packing, WIP real-time, dan manajemen KOL/Kreator.
          </p>
          <div className="mt-12 flex items-center gap-6 text-sm text-foreground/40">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[hsl(var(--success))]" />
              <span>Sistem Online</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[hsl(var(--primary))]" />
              <span>Koneksi Aman</span>
            </div>
          </div>
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
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <div className="w-14 h-14 rounded-2xl bg-[hsl(var(--primary))]/20 border border-[hsl(var(--primary))]/30 flex items-center justify-center mx-auto mb-4">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="hsl(174, 70%, 55%)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20.38 3.46 16 2 12 5.5 8 2 3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-foreground">CV. Dewi Aditya</h1>
          </div>

          <GlassCard hover={false} className="p-8">
            <h2 className="text-xl font-semibold text-foreground mb-1" data-testid="login-title">Masuk</h2>
            <p className="text-sm text-foreground/50 mb-6">Masukkan kredensial Anda untuk mengakses sistem</p>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-400/10 border border-red-300/20 rounded-xl p-3 mb-4"
              >
                <p className="text-red-200 text-sm" data-testid="login-error">{error}</p>
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-foreground/70 mb-2">Email</label>
                <GlassInput
                  type="email"
                  required
                  placeholder="admin@garment.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  data-testid="login-email-input"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground/70 mb-2">Kata Sandi</label>
                <div className="relative">
                  <GlassInput
                    type={showPassword ? 'text' : 'password'}
                    required
                    placeholder="Masukkan kata sandi"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="pr-10"
                    data-testid="login-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-foreground/40 hover:text-foreground/70 transition-colors"
                    data-testid="login-toggle-password"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 rounded-xl bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:brightness-110 font-medium text-sm transition-all duration-200"
                data-testid="login-submit-button"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <LogIn className="w-4 h-4 mr-2" />
                    Masuk
                  </>
                )}
              </Button>
            </form>
          </GlassCard>

          <p className="text-center text-xs text-foreground/30 mt-6">
            CV. Dewi Aditya &copy; {new Date().getFullYear()}
          </p>
        </motion.div>
      </div>
    </div>
  );
}
