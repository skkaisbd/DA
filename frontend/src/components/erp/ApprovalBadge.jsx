/**
 * ApprovalBadge — Badge aksi yang perlu disetujui di TopBar
 *
 * Menampilkan jumlah item yang memerlukan tindakan pengguna:
 *   - PR menunggu persetujuan
 *   - AP Invoice belum dibayar
 *   - HR requests pending
 *
 * Diperbarui setiap 60 detik via polling.
 * Klik untuk buka dropdown ringkasan + navigasi ke modul terkait.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
  ClipboardList, ShoppingCart, Hourglass, Users, ChevronRight, X
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const ICON_MAP = {
  'shopping-cart': ShoppingCart,
  'hourglass':     Hourglass,
  'users':         Users,
};

export function ApprovalBadge({ token, onNavigateModule }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const popoverRef = useRef(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/approval-inbox/badge`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setData(await res.json());
    } catch (_) {
      // silent
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refresh();
    const id = setInterval(refresh, 60000);
    return () => clearInterval(id);
  }, [token, refresh]);

  // Tutup saat klik di luar
  useEffect(() => {
    const handler = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const total = data?.total || 0;
  const categories = data?.categories || [];

  // Sembunyikan jika tidak ada data atau tidak ada kategori yang relevan
  if (!data || categories.length === 0) return null;

  const handleCategoryClick = (moduleId) => {
    if (moduleId && onNavigateModule) {
      onNavigateModule(moduleId);
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={popoverRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative inline-flex items-center justify-center h-11 w-11 min-h-[44px] min-w-[44px] rounded-full border bg-[var(--nav-pill-bg)] border-[var(--glass-border)] text-foreground/70 hover:text-foreground hover:bg-[var(--nav-pill-active)] transition-[background-color,color,transform] duration-200 ease-brand active:scale-95"
        aria-label={`Approval inbox${total > 0 ? ` (${total} item)` : ''}`}
        title="Approval Inbox"
        data-testid="approval-badge-btn"
      >
        <ClipboardList className="w-4 h-4" strokeWidth={2} />
        {total > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 h-4 min-w-[16px] px-1 rounded-full bg-[hsl(var(--warning))] text-[hsl(var(--warning-foreground,_0_0%_0%))] text-[10px] font-bold leading-4 text-center shadow"
            data-testid="approval-badge-count"
            aria-hidden="true"
          >
            {total > 99 ? '99+' : total}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute top-full right-0 mt-2 w-72 rounded-[var(--radius-md)] border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] z-50 overflow-hidden"
          data-testid="approval-badge-popover"
          role="region"
          aria-label="Approval inbox"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)]">
            <div className="flex items-center gap-2">
              <ClipboardList className="w-4 h-4 text-[hsl(var(--warning))]" />
              <h3 className="text-sm font-semibold text-foreground">Approval Inbox</h3>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded text-foreground/50 hover:text-foreground"
              aria-label="Tutup"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Kategori */}
          <div className="py-1.5">
            {categories.map((cat) => {
              const Icon = ICON_MAP[cat.icon] || ClipboardList;
              const hasItems = cat.count > 0;
              return (
                <button
                  key={cat.key}
                  onClick={() => handleCategoryClick(cat.module_id)}
                  className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-[var(--glass-bg-hover)] transition-colors duration-150 group"
                  data-testid={`approval-category-${cat.key}`}
                >
                  <div className="flex items-center gap-2.5">
                    <div className={`p-1.5 rounded-md ${hasItems
                        ? 'bg-[hsl(var(--warning)/0.15)] text-[hsl(var(--warning))]'
                        : 'bg-[var(--glass-bg)] text-foreground/40'
                      }`}>
                      <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                    </div>
                    <div className="text-left">
                      <p className={`text-xs font-medium ${hasItems ? 'text-foreground' : 'text-foreground/50'}`}>
                        {cat.label}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {hasItems ? (
                      <span className="inline-flex items-center justify-center h-5 min-w-[20px] px-1.5 rounded-full bg-[hsl(var(--warning))] text-[hsl(var(--warning-foreground,_0_0%_0%))] text-[10px] font-bold shadow-sm">
                        {cat.count}
                      </span>
                    ) : (
                      <span className="text-[10px] text-foreground/30 font-medium">—</span>
                    )}
                    <ChevronRight className="w-3 h-3 text-foreground/30 group-hover:text-foreground/60 transition-colors" />
                  </div>
                </button>
              );
            })}
          </div>

          {/* Footer */}
          {total === 0 && (
            <div className="px-4 py-3 border-t border-[var(--glass-border)]">
              <p className="text-[11px] text-foreground/40 text-center">Tidak ada item yang perlu tindakan</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
