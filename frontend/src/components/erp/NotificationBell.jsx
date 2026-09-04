/**
 * NotificationBell — versi ringkas + popup detail (revisi owner 2026-07-27).
 *
 * MASALAH LAMA: bel langsung menumpahkan seluruh daftar notifikasi tanpa
 * kategori, sehingga user tidak tahu notifikasi itu datang dari portal mana dan
 * dropdown-nya jadi panjang.
 *
 * SEKARANG:
 *   · Dropdown bel = RINGKAS — hitungan per kategori (portal sumber) + 3 notifikasi terbaru.
 *   · Tombol "Lihat Semua" membuka POPUP penuh: filter kategori, tandai dibaca,
 *     dan lompat ke modul terkait.
 *   · Kategori & hak terima diatur backend (/api/notifications/categories),
 *     mengikuti konfigurasi admin (matriks kategori × role) + pembisuan per user.
 */
import { useCallback, useEffect, useState } from 'react';
import { Bell, X, CheckCheck, ArrowRight, Loader2, BellOff, Settings2 } from 'lucide-react';
import Modal from './Modal';
import NotificationPrefsDialog from './NotificationPrefsDialog';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const CAT_TONE = {
  // "Untuk Saya" = notifikasi yang dialamatkan langsung ke pengguna ini
  personal: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  warehouse: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  production: 'bg-sky-50 text-sky-700 border-sky-200',
  cutting: 'bg-orange-50 text-orange-700 border-orange-200',
  maklon: 'bg-violet-50 text-violet-700 border-violet-200',
  finance: 'bg-teal-50 text-teal-700 border-teal-200',
  hr: 'bg-amber-50 text-amber-700 border-amber-200',
  toko: 'bg-pink-50 text-pink-700 border-pink-200',
  accessories: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  assets: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  rnd: 'bg-purple-50 text-purple-700 border-purple-200',
  sysadmin: 'bg-slate-100 text-slate-700 border-slate-300',
};

function timeAgo(iso) {
  if (!iso) return '';
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return 'baru saja';
  if (d < 3600) return `${Math.floor(d / 60)} menit lalu`;
  if (d < 86400) return `${Math.floor(d / 3600)} jam lalu`;
  return `${Math.floor(d / 86400)} hari lalu`;
}

function CatChip({ cat, label, count, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-medium
        ${active ? 'ring-2 ring-[hsl(var(--primary)/0.35)]' : ''} ${CAT_TONE[cat] || CAT_TONE.sysadmin}`}
      data-testid={`notif-cat-${cat}`}
    >
      {label}
      <span className="tabular-nums font-semibold">{count}</span>
    </button>
  );
}

export function NotificationBell({ token, onNavigateModule }) {
  const [open, setOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [sum, setSum] = useState({ categories: [], latest: [], total_unread: 0, total: 0 });
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);

  const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const loadSummary = useCallback(async () => {
    if (!token) return;
    try {
      const r = await fetch(`${BACKEND_URL}/api/notifications/categories`, { headers: h });
      if (r.ok) setSum(await r.json());
    } catch { /* diam: bel tidak boleh merusak halaman */ }
     
  }, [token]);

  const loadItems = useCallback(async (cat) => {
    setLoading(true);
    try {
      const qs = cat ? `?category=${cat}` : '';
      const r = await fetch(`${BACKEND_URL}/api/notifications/categorized${qs}`, { headers: h });
      if (r.ok) setItems((await r.json()).items || []);
    } finally { setLoading(false); }
     
  }, [token]);

  useEffect(() => {
    loadSummary();
    const t = setInterval(loadSummary, 60000);
    return () => clearInterval(t);
  }, [loadSummary]);

  const markRead = async (id) => {
    try {
      await fetch(`${BACKEND_URL}/api/notifications/unified/${id}/mark-read`, { method: 'POST', headers: h });
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, read: true } : x)));
      loadSummary();
    } catch { /* ignore */ }
  };

  const markAll = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/notifications/unified/mark-all-read`, { method: 'POST', headers: h });
      setItems((xs) => xs.map((x) => ({ ...x, read: true })));
      loadSummary();
    } catch { /* ignore */ }
  };

  const openDetail = () => {
    setOpen(false);
    setDetailOpen(true);
    setFilter('');
    loadItems('');
  };

  const goto = (n) => {
    if (!n.link_module) return;
    markRead(n.id);
    setDetailOpen(false);
    onNavigateModule?.(n.link_module);
  };

  const unread = sum.total_unread || 0;
  const cats = (sum.categories || []).filter((c) => c.total > 0);

  return (
    <>
      <div className="relative">
        <button
          onClick={() => { setOpen((o) => !o); loadSummary(); }}
          className="relative grid place-items-center h-9 w-9 rounded-full border border-[var(--glass-border)] bg-[var(--card-surface)] text-foreground/60 hover:text-foreground hover:bg-[var(--nav-pill-active)] transition-colors"
          data-testid="notification-bell-btn"
          aria-label="Notifikasi"
        >
          <Bell className="w-4 h-4" />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold grid place-items-center"
                  data-testid="notification-unread-badge">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </button>

        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden="true" />
            <div className="absolute right-0 mt-2 w-[340px] z-50 rounded-xl border border-[var(--glass-border)] bg-[var(--popover-surface)] shadow-[var(--shadow-soft)] overflow-hidden"
                 data-testid="notification-dropdown">
              <div className="flex items-center justify-between px-3 py-2.5 border-b border-[var(--glass-border)]">
                <div>
                  <p className="text-sm font-semibold text-foreground">Notifikasi</p>
                  <p className="text-[11px] text-muted-foreground">
                    {unread} belum dibaca dari {sum.total || 0} total
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => { setOpen(false); setPrefsOpen(true); }}
                          className="p-1.5 rounded-lg hover:bg-[var(--nav-pill-active)]"
                          title="Atur notifikasi saya" data-testid="notification-prefs-btn">
                    <Settings2 className="w-3.5 h-3.5 text-foreground/50" />
                  </button>
                  <button onClick={() => setOpen(false)} className="p-1 rounded-lg hover:bg-[var(--nav-pill-active)]" aria-label="Tutup">
                    <X className="w-3.5 h-3.5 text-foreground/50" />
                  </button>
                </div>
              </div>

              <div className="px-3 py-2.5 border-b border-[var(--glass-border)]">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Per Portal
                </p>
                {cats.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Tidak ada notifikasi.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5" data-testid="notif-category-chips">
                    {cats.map((c) => (
                      <CatChip key={c.key} cat={c.key} label={c.label} count={c.unread || c.total}
                               onClick={() => { setOpen(false); setDetailOpen(true); setFilter(c.key); loadItems(c.key); }} />
                    ))}
                  </div>
                )}
              </div>

              <div className="max-h-[220px] overflow-y-auto">
                {(sum.latest || []).length === 0 ? (
                  <div className="px-3 py-8 text-center">
                    <BellOff className="w-6 h-6 mx-auto text-muted-foreground/40" />
                    <p className="text-xs text-muted-foreground mt-2">Belum ada notifikasi.</p>
                  </div>
                ) : (
                  (sum.latest || []).map((n) => (
                    <div key={n.id} className="px-3 py-2 border-b border-[var(--glass-border)] last:border-0">
                      <div className="flex items-start gap-2">
                        <span className={`mt-0.5 shrink-0 px-1.5 py-0.5 rounded border text-[9px] font-semibold ${CAT_TONE[n.category] || CAT_TONE.sysadmin}`}>
                          {(sum.categories.find((c) => c.key === n.category) || {}).label || n.category}
                        </span>
                        <div className="min-w-0">
                          <p className={`text-xs truncate ${n.read ? 'text-muted-foreground' : 'text-foreground font-medium'}`}>{n.title}</p>
                          <p className="text-[10px] text-muted-foreground">{timeAgo(n.created_at)}</p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <button onClick={openDetail}
                className="w-full py-2.5 text-xs font-medium text-[hsl(var(--primary))] hover:bg-[var(--nav-pill-active)] border-t border-[var(--glass-border)] inline-flex items-center justify-center gap-1"
                data-testid="notification-see-all">
                Lihat Semua <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </>
        )}
      </div>

      {detailOpen && (
        <Modal title="Pusat Notifikasi" size="xl" onClose={() => setDetailOpen(false)}>
          <div className="space-y-3" data-testid="notification-detail-modal">
            <div className="flex flex-wrap items-center gap-1.5">
              <button onClick={() => { setFilter(''); loadItems(''); }}
                className={`px-2.5 py-1 rounded-full border text-[11px] font-medium ${!filter ? 'bg-[hsl(var(--primary))] text-white border-transparent' : 'bg-[var(--card-surface)] border-[var(--glass-border)] text-foreground/70'}`}
                data-testid="notif-filter-all">
                Semua ({sum.total || 0})
              </button>
              {(sum.categories || []).map((c) => (
                <CatChip key={c.key} cat={c.key} label={c.label} count={c.total} active={filter === c.key}
                         onClick={() => { setFilter(c.key); loadItems(c.key); }} />
              ))}
              <div className="flex-1" />
              <button onClick={() => setPrefsOpen(true)}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-xs text-foreground hover:bg-[var(--nav-pill-active)]"
                data-testid="notif-open-prefs">
                <Settings2 className="w-3.5 h-3.5" /> Notifikasi saya
              </button>
              <button onClick={markAll}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--card-surface)] text-xs text-foreground hover:bg-[var(--nav-pill-active)]"
                data-testid="notif-mark-all">
                <CheckCheck className="w-3.5 h-3.5" /> Tandai semua dibaca
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)] bg-[var(--card-surface)]">
              {loading ? (
                <div className="py-12 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" /></div>
              ) : items.length === 0 ? (
                <div className="py-12 text-center">
                  <BellOff className="w-7 h-7 mx-auto text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground mt-2">Tidak ada notifikasi pada kategori ini.</p>
                </div>
              ) : items.map((n) => (
                <div key={n.id}
                     className={`px-3 py-2.5 flex items-start gap-3 ${n.read ? '' : 'bg-[hsl(var(--primary)/0.04)]'}`}
                     data-testid="notif-row">
                  <span className={`mt-0.5 shrink-0 px-1.5 py-0.5 rounded border text-[10px] font-semibold ${CAT_TONE[n.category] || CAT_TONE.sysadmin}`}>
                    {n.category_label || n.category}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm ${n.read ? 'text-muted-foreground' : 'text-foreground font-medium'}`}>{n.title}</p>
                    {(n.message || n.body) && (
                      <p className="text-xs text-muted-foreground mt-0.5">{n.message || n.body}</p>
                    )}
                    <p className="text-[10px] text-muted-foreground mt-1">{timeAgo(n.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {n.link_module && (
                      <button onClick={() => goto(n)} className="text-[11px] text-[hsl(var(--primary))] hover:underline">Buka</button>
                    )}
                    {!n.read && (
                      <button onClick={() => markRead(n.id)} className="text-[11px] text-muted-foreground hover:text-foreground">Tandai</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Modal>
      )}
      {prefsOpen && (
        <NotificationPrefsDialog
          token={token}
          onClose={() => setPrefsOpen(false)}
          onSaved={() => { loadSummary(); if (detailOpen) loadItems(filter); }}
        />
      )}
    </>
  );
}

export default NotificationBell;
