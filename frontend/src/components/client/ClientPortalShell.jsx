import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  ShoppingBag,
  Sparkles,
  Receipt,
  UserRound,
  LogOut,
  Shirt,
  KeyRound,
  Menu,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { clientApi } from './clientApi';
import ClientDashboard from './ClientDashboard';
import ClientOrders from './ClientOrders';
import ClientSamples from './ClientSamples';
import ClientInvoices from './ClientInvoices';
import ClientProfile from './ClientProfile';
import ClientChangePasswordDialog from './ClientChangePasswordDialog';

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'orders', label: 'Order Saya', icon: ShoppingBag },
  { id: 'samples', label: 'Sample & Approval', icon: Sparkles },
  { id: 'invoices', label: 'Invoice & Bayar', icon: Receipt },
  { id: 'profile', label: 'Profil', icon: UserRound },
];

export default function ClientPortalShell({ token: initialToken, user: initialUser, onLogout }) {
  const [token, setToken] = useState(initialToken);
  const [user, setUser] = useState(initialUser);
  const [activeView, setActiveView] = useState('dashboard');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [pwdDialogOpen, setPwdDialogOpen] = useState(false);
  const [badges, setBadges] = useState({ samples: 0, invoices: 0 });

  // Force password change on first login
  useEffect(() => {
    if (user?.must_change_password) {
      setPwdDialogOpen(true);
    }
  }, [user]);

  // Fetch badge counts on mount and every 60s
  useEffect(() => {
    async function fetchBadges() {
      try {
        const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/dewi/client-portal/badge-counts`, {
          headers: { Authorization: `Bearer ${initialToken}` },
        });
        if (r.ok) setBadges(await r.json());
      } catch { /* silent */ }
    }
    fetchBadges();
    const interval = setInterval(fetchBadges, 60000);
    return () => clearInterval(interval);
  }, [initialToken]);

  const refreshMe = useCallback(async () => {
    try {
      const data = await clientApi.request('/auth/me', { token });
      setUser((u) => ({ ...u, ...data.user }));
      const sess = clientApi.loadSession();
      if (sess) clientApi.saveSession(sess.token, { ...sess.user, ...data.user });
    } catch (e) {
      // token may be invalid, force logout
      handleLogout();
    }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLogout = useCallback(() => {
    clientApi.clearSession();
    setToken(null);
    setUser(null);
    if (onLogout) onLogout();
  }, [onLogout]);

  const handlePasswordChanged = useCallback(() => {
    toast.success('Password berhasil diubah. Silakan gunakan password baru pada login berikutnya.');
    setPwdDialogOpen(false);
    refreshMe();
  }, [refreshMe]);

  const ActiveView = (() => {
    switch (activeView) {
      case 'orders':
        return <ClientOrders token={token} />;
      case 'samples':
        return <ClientSamples token={token} />;
      case 'invoices':
        return <ClientInvoices token={token} />;
      case 'profile':
        return <ClientProfile token={token} user={user} />;
      case 'dashboard':
      default:
        return <ClientDashboard token={token} onNavigate={setActiveView} />;
    }
  })();

  return (
    <div
      className="min-h-screen flex bg-[hsl(var(--background))] noise-overlay"
      data-testid="client-portal-shell"
    >
      {/* Sidebar — desktop */}
      <aside className="hidden lg:flex w-64 flex-col border-r border-foreground/10 bg-foreground/[0.02]">
        <div className="px-6 py-6 border-b border-foreground/10">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl bg-[hsl(var(--primary))]/20 border border-[hsl(var(--primary))]/30 flex items-center justify-center">
              <Shirt size={18} className="text-[hsl(var(--primary))]" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-foreground/45">
                Portal Klien
              </div>
              <div className="text-sm font-semibold text-foreground leading-tight">
                CV. Dewi Aditya
              </div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveView(item.id)}
                data-testid={`client-nav-${item.id}`}
                className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition ${
                  active
                    ? 'bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] font-medium'
                    : 'text-foreground/65 hover:text-foreground hover:bg-foreground/5'
                }`}
              >
                <Icon size={17} />
                <span>{item.label}</span>
                {/* Notification Badge */}
                {item.id === 'samples' && badges.samples > 0 && (
                  <span data-testid="badge-samples" className="ml-auto min-w-[18px] h-[18px] rounded-full bg-red-500 text-foreground text-[10px] font-bold flex items-center justify-center px-1">
                    {badges.samples > 9 ? '9+' : badges.samples}
                  </span>
                )}
                {item.id === 'invoices' && badges.invoices > 0 && (
                  <span data-testid="badge-invoices" className="ml-auto min-w-[18px] h-[18px] rounded-full bg-red-500 text-foreground text-[10px] font-bold flex items-center justify-center px-1">
                    {badges.invoices > 9 ? '9+' : badges.invoices}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-foreground/10 space-y-2">
          <div className="px-3 py-2 rounded-lg bg-foreground/5">
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Klien
            </div>
            <div className="text-sm font-medium text-foreground truncate">
              {user?.client_name || '-'}
            </div>
            <div className="text-xs text-foreground/45 truncate">{user?.email}</div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPwdDialogOpen(true)}
            className="w-full justify-start gap-2 text-foreground/65"
            data-testid="client-change-password-btn"
          >
            <KeyRound size={15} />
            Ubah Password
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="w-full justify-start gap-2 text-foreground/65 hover:text-red-600"
            data-testid="client-logout-btn"
          >
            <LogOut size={15} />
            Keluar
          </Button>
        </div>
      </aside>

      {/* Mobile topbar */}
      <div className="lg:hidden fixed top-0 inset-x-0 z-40 border-b border-foreground/10 bg-[hsl(var(--background))]/85 backdrop-blur-md">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[hsl(var(--primary))]/20 flex items-center justify-center">
              <Shirt size={16} className="text-[hsl(var(--primary))]" />
            </div>
            <div className="text-sm font-semibold text-foreground">Portal Klien</div>
          </div>
          <button
            onClick={() => setMobileNavOpen((s) => !s)}
            className="p-2 rounded-lg hover:bg-foreground/5"
            aria-label="Toggle menu"
            data-testid="client-mobile-menu-toggle"
          >
            {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <AnimatePresence>
          {mobileNavOpen && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-foreground/10"
            >
              <div className="px-3 py-2 space-y-1">
                {NAV.map((item) => {
                  const Icon = item.icon;
                  const active = activeView === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        setActiveView(item.id);
                        setMobileNavOpen(false);
                      }}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition ${
                        active
                          ? 'bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] font-medium'
                          : 'text-foreground/70'
                      }`}
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
                <div className="pt-2 border-t border-foreground/10 space-y-1">
                  <button
                    onClick={() => {
                      setPwdDialogOpen(true);
                      setMobileNavOpen(false);
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-foreground/65"
                  >
                    <KeyRound size={15} />
                    Ubah Password
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-red-600"
                  >
                    <LogOut size={15} />
                    Keluar
                  </button>
                </div>
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </div>

      {/* Main content */}
      <main className="flex-1 lg:ml-0 mt-14 lg:mt-0">
        <div className="max-w-6xl mx-auto px-5 lg:px-10 py-6 lg:py-10">
          <AnimatePresence mode="wait">
            {user?.must_change_password ? (
              <motion.div
                key="must-change-password"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2 }}
                data-testid="client-must-change-gate"
                className="max-w-md mx-auto text-center py-20"
              >
                <h2 className="text-xl font-semibold text-foreground mb-2">
                  Ganti Password Terlebih Dahulu
                </h2>
                <p className="text-sm text-muted-foreground mb-5">
                  Demi keamanan akun, silakan ganti password sekali-pakai Anda sebelum mengakses portal.
                </p>
                <button
                  onClick={() => setPwdDialogOpen(true)}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium bg-foreground text-background"
                  data-testid="client-must-change-open-btn"
                >
                  Ganti Password
                </button>
              </motion.div>
            ) : (
              <motion.div
                key={activeView}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2 }}
              >
                {ActiveView}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      <ClientChangePasswordDialog
        open={pwdDialogOpen}
        forced={Boolean(user?.must_change_password)}
        token={token}
        onClose={() => {
          if (!user?.must_change_password) setPwdDialogOpen(false);
        }}
        onSuccess={handlePasswordChanged}
      />
    </div>
  );
}
