/**
 * DataCard / DataTableShell / StatCard
 * ============================================================================
 * Komponen permukaan standar untuk seluruh modul ERP.
 *
 * Latar masalah (laporan owner, light mode):
 *   - Tabel dibungkus `bg-foreground/5` → di light mode itu ≈ 5% hitam di atas
 *     latar terang, jadi kartu "hilang" dan baris menyatu dengan halaman.
 *   - Tombol memakai warna mentah (`bg-blue-500`) + `text-foreground`, sehingga
 *     tidak konsisten dengan token brand dan kontrasnya buruk.
 *
 * Semua komponen di sini WAJIB memakai design token:
 *   --card-surface, --glass-border, --shadow-card, --radius-*,
 *   hsl(var(--primary)), hsl(var(--foreground)), hsl(var(--muted-foreground)).
 */
import React from 'react';
import { cn } from '@/lib/utils';

/* ══════════════════════════════════════════════════════════════════════════
   DataCard — permukaan kartu solid (putih di light, glass di dark)
   ══════════════════════════════════════════════════════════════════════════ */
export const DataCard = React.forwardRef(function DataCard(
  { children, className, padded = false, as: As = 'div', ...props },
  ref
) {
  return (
    <As
      ref={ref}
      className={cn(
        'relative rounded-[var(--radius-lg)] border',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'shadow-[var(--shadow-card)]',
        'text-[hsl(var(--foreground))]',
        padded && 'p-4 sm:p-5',
        className
      )}
      {...props}
    >
      {children}
    </As>
  );
});

/* ══════════════════════════════════════════════════════════════════════════
   DataCardHeader — judul + deskripsi + slot aksi di kanan
   ══════════════════════════════════════════════════════════════════════════ */
export const DataCardHeader = ({ title, description, actions, icon: Icon, className, ...props }) => (
  <div
    className={cn(
      'flex flex-wrap items-start justify-between gap-3 px-4 sm:px-5 py-3.5',
      'border-b border-[var(--glass-border)]',
      className
    )}
    {...props}
  >
    <div className="min-w-0">
      <div className="flex items-center gap-2">
        {Icon ? <Icon size={16} className="text-[hsl(var(--primary))] shrink-0" aria-hidden="true" /> : null}
        <h3 className="text-sm font-semibold text-[hsl(var(--foreground))] truncate">{title}</h3>
      </div>
      {description ? (
        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5">{description}</p>
      ) : null}
    </div>
    {actions ? <div className="flex items-center gap-2 shrink-0">{actions}</div> : null}
  </div>
);

/* ══════════════════════════════════════════════════════════════════════════
   DataTableShell — pembungkus tabel: kartu + scroll horizontal + sticky head
   Pemakaian:
     <DataTableShell>
       <table className="w-full text-sm"> ... </table>
     </DataTableShell>
   ══════════════════════════════════════════════════════════════════════════ */
export const DataTableShell = ({
  children,
  className,
  scrollClassName,
  maxHeight,
  stickyHeader = true,
  ...props
}) => (
  <div
    className={cn(
      'relative rounded-[var(--radius-lg)] border overflow-hidden',
      'bg-[var(--card-surface)] border-[var(--glass-border)]',
      'shadow-[var(--shadow-card)]',
      className
    )}
    data-table-shell="true"
    {...props}
  >
    <div
      className={cn('overflow-x-auto', maxHeight && 'overflow-y-auto', scrollClassName)}
      style={maxHeight ? { maxHeight } : undefined}
      data-sticky-head={stickyHeader ? 'true' : undefined}
    >
      {children}
    </div>
  </div>
);

/* ══════════════════════════════════════════════════════════════════════════
   StatCard — kartu KPI standar (putih + aksen tipis di kiri)
   tone: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'neutral'
   ══════════════════════════════════════════════════════════════════════════ */
const TONE_ACCENT = {
  primary: 'hsl(var(--primary))',
  success: 'hsl(var(--success))',
  warning: 'hsl(var(--warning))',
  danger: 'hsl(var(--destructive))',
  info: 'hsl(var(--info))',
  neutral: 'hsl(var(--muted-foreground))',
};

export const StatCard = ({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'primary',
  compact = false,
  className,
  'data-testid': testId,
  ...props
}) => {
  const accent = TONE_ACCENT[tone] || TONE_ACCENT.primary;
  return (
    <div
      data-testid={testId}
      className={cn(
        'relative overflow-hidden rounded-[var(--radius-lg)] border',
        'bg-[var(--card-surface)] border-[var(--glass-border)]',
        'shadow-[var(--shadow-card)]',
        compact ? 'p-3 pl-4' : 'p-4 pl-5',
        className
      )}
      {...props}
    >
      {/* aksen kiri tipis — pengganti blok pastel penuh */}
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1"
        style={{ backgroundColor: accent }}
      />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p
            className={cn(
              'font-bold truncate text-[hsl(var(--foreground))]',
              compact ? 'text-lg' : 'text-2xl'
            )}
          >
            {value}
          </p>
          <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5 truncate">{label}</p>
          {hint ? (
            <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-1 truncate">{hint}</p>
          ) : null}
        </div>
        {Icon ? (
          <span
            className="grid place-items-center h-8 w-8 rounded-[var(--radius-sm)] shrink-0"
            style={{ backgroundColor: `color-mix(in srgb, ${accent} 12%, transparent)`, color: accent }}
          >
            <Icon size={16} aria-hidden="true" />
          </span>
        ) : null}
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════════════════════════════════════
   EmptyRow — baris kosong standar di dalam tabel
   ══════════════════════════════════════════════════════════════════════════ */
export const EmptyRow = ({ colSpan = 1, message = 'Belum ada data', icon: Icon }) => (
  <tr>
    <td colSpan={colSpan} className="py-10 text-center">
      <div className="flex flex-col items-center gap-2 text-[hsl(var(--muted-foreground))]">
        {Icon ? <Icon size={26} className="opacity-50" aria-hidden="true" /> : null}
        <span className="text-sm">{message}</span>
      </div>
    </td>
  </tr>
);

export default DataCard;
