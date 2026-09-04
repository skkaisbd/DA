/**
 * PageHeader \u2014 Tahap 3 Module Polish atom.
 * Hero kecil untuk CRUD modules: title + subtitle (optional) + actions.
 * Konsisten di seluruh modul, dual-theme aware.
 */
import { cn } from '@/lib/utils';

export function PageHeader({ icon: Icon, eyebrow, title, subtitle, actions, className, testId }) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'relative rounded-[var(--radius-lg)] border px-5 lg:px-7 py-5',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)] shadow-[var(--shadow-card)]',
        'overflow-hidden',
        className
      )}
    >
      {/* Ambient accent glow (subtle) */}
      <div
        aria-hidden="true"
        className="absolute -top-10 -right-10 w-52 h-52 rounded-full blur-[80px] opacity-30 pointer-events-none"
        style={{ background: 'radial-gradient(circle, hsl(var(--primary)), transparent 70%)' }}
      />
      <div className="relative flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 flex-1 flex items-start gap-3">
          {Icon && (
            <div className="hidden sm:grid place-items-center w-10 h-10 rounded-[12px] bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.22)] shrink-0">
              <Icon className="w-4.5 h-4.5 text-[hsl(var(--primary))]" strokeWidth={2} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            {eyebrow && <p className="text-[10px] uppercase tracking-[0.16em] text-foreground/50 font-semibold mb-1">{eyebrow}</p>}
            <h1 className="text-xl lg:text-2xl font-bold text-foreground tracking-tight leading-tight">{title}</h1>
            {subtitle && <p className="text-sm text-foreground/55 mt-1 leading-relaxed">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
    </div>
  );
}

/**
 * StatTile — smaller KPI tile untuk summary di atas tabel (Tahap 3).
 * Lebih ringan dari StatCard, tanpa icon box.
 *
 * Phase 12.4 — Drill-down: bila `onClick` prop diberikan, tile jadi button
 * dengan hover/focus states supaya user bisa klik untuk navigasi detail.
 */
export function StatTile({ label, value, accent = 'default', className, testId, suffix, onClick, hint }) {
  const colors = {
    default: 'text-foreground',
    primary: 'text-[hsl(var(--primary))]',
    success: 'text-[hsl(var(--success))]',
    warning: 'text-[hsl(var(--warning))]',
    danger:  'text-[hsl(var(--destructive))]',
    muted:   'text-foreground/60',
  };
  const isClickable = !!onClick;
  const Tag = isClickable ? 'button' : 'div';
  return (
    <Tag
      data-testid={testId}
      onClick={onClick}
      type={isClickable ? 'button' : undefined}
      title={isClickable ? (hint || 'Klik untuk lihat detail') : undefined}
      className={cn(
        'rounded-[var(--radius-md)] border px-4 py-3 text-left w-full',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)]',
        isClickable && 'cursor-pointer transition-[transform,border-color,box-shadow] duration-150 ease-out hover:border-[hsl(var(--primary)/0.45)] hover:-translate-y-[1px] hover:shadow-[var(--shadow-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] active:scale-[0.98]',
        className
      )}
    >
      <p className="text-[10px] uppercase tracking-wider text-foreground/50 font-semibold">{label}</p>
      <p className={cn('text-xl font-bold tracking-tight mt-1', colors[accent] || colors.default)}>
        {value}{suffix && <span className="text-sm text-foreground/50 ml-1">{suffix}</span>}
      </p>
      {isClickable && hint && (
        <p className="text-[10px] text-foreground/40 mt-1 truncate">{hint} →</p>
      )}
    </Tag>
  );
}

/**
 * StatusBadge \u2014 pill badge untuk status lifecycle (draft/sent/paid/finalized/etc).
 * Auto-map common statuses to colors; accepts custom tone override.
 */
export function StatusBadge({ status, tone, className, testId }) {
  const s = (status || '').toLowerCase();
  const autoTone =
    s === 'draft' ? 'muted' :
    s === 'sent' || s === 'released' || s === 'in_production' || s === 'confirmed' ? 'info' :
    s === 'partial_paid' || s === 'partial' ? 'warning' :
    s === 'paid' || s === 'finalized' || s === 'completed' || s === 'issued' ? 'success' :
    s === 'overdue' || s === 'cancelled' || s === 'rejected' ? 'danger' :
    s === 'hadir' ? 'success' :
    s === 'izin' || s === 'sakit' || s === 'cuti' || s === 'libur' ? 'info' :
    s === 'alfa' ? 'danger' :
    'default';
  const final = tone || autoTone;
  const toneClass = {
    default: 'bg-[var(--glass-bg)] text-foreground/70 border-[var(--glass-border)]',
    muted:   'bg-[var(--glass-bg)] text-foreground/50 border-[var(--glass-border)]',
    info:    'bg-[hsl(var(--info)/0.12)] text-[hsl(var(--info))] border-[hsl(var(--info)/0.22)]',
    success: 'bg-[hsl(var(--success)/0.12)] text-[hsl(var(--success))] border-[hsl(var(--success)/0.22)]',
    warning: 'bg-[hsl(var(--warning)/0.12)] text-[hsl(var(--warning))] border-[hsl(var(--warning)/0.22)]',
    danger:  'bg-[hsl(var(--destructive)/0.12)] text-[hsl(var(--destructive))] border-[hsl(var(--destructive)/0.25)]',
    primary: 'bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))] border-[hsl(var(--primary)/0.25)]',
  }[final] || 'bg-[var(--glass-bg)] text-foreground/70';
  return (
    <span
      data-testid={testId}
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border',
        toneClass,
        className
      )}
    >
      {status || '-'}
    </span>
  );
}

/**
 * EmptyState \u2014 konsisten empty state untuk semua modul.
 */
export function EmptyState({ icon: Icon, title, description, action, className, testId }) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'flex flex-col items-center justify-center py-16 px-6 text-center',
        className
      )}
    >
      {Icon && (
        <div className="mb-4 w-14 h-14 rounded-2xl bg-[var(--glass-bg)] border border-[var(--glass-border)] grid place-items-center">
          <Icon className="w-6 h-6 text-foreground/40" strokeWidth={1.5} />
        </div>
      )}
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {description && <p className="text-xs text-foreground/50 mt-1 max-w-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
