/**
 * Glass v2 — per design_guidelines.md
 *
 * Atom komponen untuk sistem glassmorphism.
 * Rule penting: tidak ada `transition-all` (dilarang di design guidelines).
 * Hanya transisi specific property (bg, border, shadow, opacity, transform).
 */
import { cn } from '@/lib/utils';

/**
 * GlassCard — panel glass standar (lebih kuat dari v1).
 * Hover: bg + shadow glow halus + naik 2px (hanya jika hover=true).
 */
export const GlassCard = ({ children, className, hover = true, as: As = 'div', ...props }) => {
  return (
    <As
      className={cn(
        'relative rounded-[var(--radius-lg)] border',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)] backdrop-saturate-[1.25]',
        'shadow-[var(--shadow-card)]',
        hover && [
          // Specific-prop transitions only (NO transition-all)
          'transition-[background-color,border-color,box-shadow,transform] duration-200 ease-brand',
          'hover:bg-[var(--card-surface-hover)]',
          'hover:shadow-[var(--shadow-glow-blue)]',
          'hover:-translate-y-0.5',
        ],
        className
      )}
      {...props}
    >
      {children}
    </As>
  );
};

/**
 * GlassPanel — panel glass tanpa hover effect, untuk sub-sections.
 */
export const GlassPanel = ({ children, className, as: As = 'div', ...props }) => {
  return (
    <As
      className={cn(
        'rounded-[var(--radius-md)] border',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)]',
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.10)]',
        className
      )}
      {...props}
    >
      {children}
    </As>
  );
};

/**
 * GlassTable — wrapper untuk tabel. Tabel panjang → jangan blur di dalam row, hanya wrapper.
 */
export const GlassTable = ({ children, className, ...props }) => {
  return (
    <div
      className={cn(
        'rounded-[var(--radius-lg)] border overflow-hidden',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'backdrop-blur-[var(--glass-blur)]',
        'shadow-[var(--shadow-card)]',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * GlassInput — text input dengan background glass halus.
 * Focus ring sudah otomatis dari global :focus-visible.
 */
export const GlassInput = ({ className, ...props }) => {
  return (
    <input
      className={cn(
        'flex h-10 w-full rounded-[var(--radius-sm)] border px-3 py-2',
        'bg-[var(--input-surface)] border-[var(--glass-border)]',
        'text-sm text-foreground placeholder:text-muted-foreground',
        'disabled:opacity-60 disabled:cursor-not-allowed',
        'transition-[background-color,border-color] duration-150 ease-brand',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-transparent',
        className
      )}
      {...props}
    />
  );
};

/**
 * PillButton — pill-shaped button untuk top nav & CTA utama.
 * Variants: primary (filled), ghost (glass), solid (solid dark pill).
 */
export const PillButton = ({ children, className, variant = 'ghost', active = false, as: As = 'button', ...props }) => {
  const variantClasses = {
    primary: 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-[var(--shadow-glow-blue)] hover:brightness-110',
    ghost:   'bg-[var(--nav-pill-bg)] text-foreground/70 hover:bg-[var(--nav-pill-active)] hover:text-foreground border border-[var(--glass-border)]',
    solid:   'bg-[var(--nav-pill-active)] text-foreground shadow-[var(--shadow-glow-blue)]',
  };
  return (
    <As
      className={cn(
        'relative inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium',
        'transition-[background-color,color,box-shadow,transform] duration-200 ease-brand',
        active ? variantClasses.solid : variantClasses[variant] || variantClasses.ghost,
        className
      )}
      {...props}
    >
      {children}
    </As>
  );
};

/**
 * IconBadge — squircle icon container (28px default) untuk top nav / side nav.
 */
export const IconBadge = ({ children, className, size = 28, active = false, ...props }) => {
  return (
    <span
      style={{ width: size, height: size }}
      className={cn(
        'inline-grid place-items-center rounded-[12px] shrink-0',
        'border border-[var(--glass-border)]',
        active
          ? 'bg-[hsl(var(--primary)/0.18)] text-[hsl(var(--primary))]'
          : 'bg-[var(--card-surface)] text-foreground/70',
        'transition-[background-color,color] duration-200 ease-brand',
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
