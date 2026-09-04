/**
 * Dashboard Atoms — Tahap 2 (Dashboard Modernization)
 *
 * Komponen reusable untuk semua dashboard: StatCard, ChartCard, GlassTooltip,
 * HeroCrystalCard (3D prism CSS accent per Ref B), DonutProgress, TrendDelta.
 * Semua mengikuti design tokens di index.css + dual-theme (dark + light).
 */
import { cn } from '@/lib/utils';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

/* ───────────────────────────────────────────────────────────────────────── */
/*  TrendDelta — chip kecil menampilkan delta + arrow                        */
/* ───────────────────────────────────────────────────────────────────────── */
export function TrendDelta({ value, suffix = '%', neutralThreshold = 0.01 }) {
  if (value === null || value === undefined) return null;
  const v = Number(value);
  const neutral = Math.abs(v) < neutralThreshold;
  const positive = v > 0;
  const Icon = neutral ? Minus : positive ? ArrowUp : ArrowDown;
  const color = neutral
    ? 'text-foreground/50'
    : positive
      ? 'text-[hsl(var(--success))]'
      : 'text-[hsl(var(--destructive))]';
  return (
    <span className={cn('inline-flex items-center gap-0.5 text-xs font-semibold', color)}>
      <Icon className="w-3 h-3" strokeWidth={2.5} />
      {Math.abs(v).toLocaleString('id-ID', { maximumFractionDigits: 1 })}{suffix}
    </span>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  StatCard — KPI card premium dengan icon, trend delta, sub-text            */
/* ───────────────────────────────────────────────────────────────────────── */
export function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  trend,
  accent = 'primary', // primary | success | warning | info | mint
  className,
  testId,
  onClick,
}) {
  const accentMap = {
    primary: { bg: 'bg-[hsl(var(--primary)/0.12)]', border: 'border-[hsl(var(--primary)/0.25)]', icon: 'text-[hsl(var(--primary))]' },
    success: { bg: 'bg-[hsl(var(--success)/0.12)]', border: 'border-[hsl(var(--success)/0.22)]', icon: 'text-[hsl(var(--success))]' },
    warning: { bg: 'bg-[hsl(var(--warning)/0.12)]', border: 'border-[hsl(var(--warning)/0.22)]', icon: 'text-[hsl(var(--warning))]' },
    info:    { bg: 'bg-[hsl(var(--info)/0.12)]',    border: 'border-[hsl(var(--info)/0.22)]',    icon: 'text-[hsl(var(--info))]' },
    mint:    { bg: 'bg-[hsl(var(--accent)/0.22)]',  border: 'border-[hsl(var(--accent)/0.35)]',  icon: 'text-[hsl(var(--accent-foreground))]' },
  };
  const a = accentMap[accent] || accentMap.primary;
  const Component = onClick ? 'button' : 'div';
  return (
    <Component
      onClick={onClick}
      data-testid={testId}
      className={cn(
        'relative rounded-[var(--radius-lg)] border p-4 text-left flex flex-col h-full min-h-[120px]',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)] shadow-[var(--shadow-card)]',
        onClick && 'transition-[transform,box-shadow,background-color] duration-200 ease-smooth-out hover:bg-[var(--card-surface-hover)] hover:shadow-[var(--shadow-glow-blue)] hover:-translate-y-0.5 cursor-pointer',
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] uppercase tracking-wider text-foreground/50 font-semibold">{label}</p>
          <p className="text-3xl font-bold text-foreground mt-1.5 leading-none tracking-tight">{value}</p>
          {sub && <p className="text-xs text-foreground/50 mt-1.5 truncate">{sub}</p>}
        </div>
        {Icon && (
          <div className={cn('w-10 h-10 rounded-[12px] border grid place-items-center shrink-0', a.bg, a.border)}>
            <Icon className={cn('w-4 h-4', a.icon)} strokeWidth={2} />
          </div>
        )}
      </div>
      {trend !== undefined && trend !== null && (
        <div className="mt-auto pt-3 border-t border-[var(--glass-border)] flex items-center gap-2">
          <TrendDelta value={trend.value} suffix={trend.suffix || '%'} />
          {trend.label && <span className="text-xs text-foreground/50">{trend.label}</span>}
        </div>
      )}
    </Component>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  ChartCard — wrapper untuk chart dengan title + actions                    */
/* ───────────────────────────────────────────────────────────────────────── */
export function ChartCard({ title, subtitle, actions, children, className, testId }) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'rounded-[var(--radius-lg)] border p-5',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)] shadow-[var(--shadow-card)]',
        className
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          {title && <h3 className="text-sm font-semibold text-foreground tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-foreground/50 mt-0.5">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  GlassTooltip — custom tooltip untuk Recharts                              */
/* ───────────────────────────────────────────────────────────────────────── */
export function GlassTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] px-3 py-2">
      {label && <p className="text-xs font-semibold text-foreground mb-1.5">{label}</p>}
      <div className="space-y-1">
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: p.color || p.fill }} />
            <span className="text-foreground/60">{p.name}:</span>
            <span className="font-semibold text-foreground tabular-nums">
              {formatter ? formatter(p.value) : (p.value ?? 0).toLocaleString('id-ID')}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  HeroCrystalCard — hero card dengan 3D prism CSS accent (Ref B inspired)   */
/*  Tampilan: big heading + supporting copy + crystal illustration (pure CSS) */
/* ───────────────────────────────────────────────────────────────────────── */
export function HeroCrystalCard({ eyebrow, title, description, children, className, testId, actions }) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'relative overflow-hidden rounded-[var(--radius-xl)] border p-6 lg:p-8',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-card)]',
        className
      )}
    >
      {/* Ambient glow (blue-mint, sesuai Ref B) */}
      <div
        aria-hidden="true"
        className="absolute -top-16 -right-16 w-72 h-72 rounded-full blur-[96px] opacity-40 pointer-events-none"
        style={{ background: 'radial-gradient(circle, hsl(var(--accent)), transparent 70%)' }}
      />
      <div
        aria-hidden="true"
        className="absolute -bottom-20 -left-10 w-72 h-72 rounded-full blur-[90px] opacity-30 pointer-events-none"
        style={{ background: 'radial-gradient(circle, hsl(var(--primary)), transparent 70%)' }}
      />

      {/* CSS-only crystal/prism accent — geometric stacked shapes */}
      <div aria-hidden="true" className="absolute top-6 right-6 w-32 h-32 hidden lg:block pointer-events-none">
        <div className="relative w-full h-full">
          <div className="absolute inset-0 rotate-12 rounded-3xl bg-gradient-to-br from-[hsl(var(--accent))] to-[hsl(var(--primary))] opacity-70 shadow-2xl" />
          <div className="absolute inset-2 -rotate-6 rounded-2xl bg-gradient-to-tr from-[hsl(var(--primary)/0.6)] to-[hsl(var(--info))] opacity-50" />
          <div className="absolute inset-6 rotate-45 rounded-xl bg-foreground/[0.15] backdrop-blur-sm border border-foreground/30" />
        </div>
      </div>

      <div className="relative z-10 flex items-start justify-between gap-4 flex-wrap">
        <div className="max-w-2xl">
          {eyebrow && <p className="text-[11px] uppercase tracking-[0.18em] text-foreground/60 font-semibold mb-2">{eyebrow}</p>}
          {title && <h1 className="text-3xl lg:text-4xl font-bold text-foreground tracking-tight leading-[1.05]">{title}</h1>}
          {description && <p className="text-sm text-foreground/60 mt-3 leading-relaxed">{description}</p>}
          {children && <div className="mt-5">{children}</div>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  DonutProgress — ring chart pure SVG untuk single % value                 */
/* ───────────────────────────────────────────────────────────────────────── */
export function DonutProgress({ value = 0, size = 140, stroke = 12, label, sub, accent = 'primary' }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const r = (size - stroke) / 2;
  const C = 2 * Math.PI * r;
  const offset = C * (1 - pct / 100);
  const colorVar = accent === 'success' ? 'var(--success)' : accent === 'warning' ? 'var(--warning)' : 'var(--primary)';

  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke="currentColor"
          strokeWidth={stroke}
          fill="none"
          className="text-[var(--glass-border)]"
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke={`hsl(${colorVar})`}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={C}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 800ms cubic-bezier(0.16, 1, 0.3, 1)' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <p className="text-3xl font-bold text-foreground leading-none tracking-tight">{pct.toFixed(0)}<span className="text-lg text-foreground/50">%</span></p>
          {label && <p className="text-[10px] uppercase tracking-wider text-foreground/50 mt-1">{label}</p>}
          {sub && <p className="text-[10px] text-foreground/40 mt-0.5">{sub}</p>}
        </div>
      </div>
    </div>
  );
}

/* Shared chart colors (reference only — components should use CSS vars via style) */
export const CHART_PALETTE = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
];
