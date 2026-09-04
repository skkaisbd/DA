/**
 * NavItem — single sidebar nav item renderer.
 *
 * Supports:
 *   - regular module buttons (clickable, calls onModuleChange)
 *   - external links (item.external + item.href)
 *   - non-clickable section headers (item.isHeader)
 *   - collapsed mode (icon-only)
 *   - active highlight (left indicator + bg)
 *   - badges (text or dot in collapsed mode)
 *   - indent levels (item.indent = 1, 2, ...)
 */

// Badge color mapping — user-friendly labels with semantic colors
const BADGE_STYLE = {
  RESMI:  'bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',     // Sumber data resmi/utama
  BARU:   'bg-sky-100 dark:bg-sky-500/15 text-sky-600 dark:text-sky-400',              // Fitur baru
  HUB:    'bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400',        // Pusat/hub modul
  AI:     'bg-purple-100 dark:bg-purple-500/15 text-purple-600 dark:text-purple-400',        // AI-powered
  BETA:   'bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400',          // Masih dalam pengembangan
  VENDOR: 'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400',        // Portal vendor/mitra
  NEW:    'bg-sky-100 dark:bg-sky-500/15 text-sky-600 dark:text-sky-400',              // Alias BARU (fallback)
  SELF:   'bg-orange-100 dark:bg-orange-500/15 text-orange-600 dark:text-orange-400',        // Legacy alias VENDOR
};

function BadgeChip({ badge }) {
  const style = BADGE_STYLE[badge] ?? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))]';
  return (
    <span className={`ml-auto text-[10px] font-semibold px-1.5 py-0.5 rounded leading-none ${style}`}>
      {badge}
    </span>
  );
}

export default function NavItem({ item, isActive, collapsed, onModuleChange, setMobileOpen }) {
  // Handle header items (non-clickable category headers with emoji)
  if (item.isHeader) {
    if (collapsed) {
      // In collapsed mode, show just a separator
      return <div className="mx-2 my-2 h-px bg-[var(--glass-border)]" aria-hidden="true" />;
    }
    return (
      <div
        className="px-3 pt-3 pb-1.5 flex items-center gap-1.5"
        data-testid={`nav-header-${item.id}`}
      >
        <span className="text-[11px] font-semibold tracking-wide text-foreground/70">{item.label}</span>
      </div>
    );
  }

  const Icon = item.icon;
  const indentClass = item.indent ? `ml-${item.indent * 4}` : '';

  // External links
  if (item.external && item.href) {
    if (collapsed) {
      return (
        <a
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className="relative w-full grid place-items-center h-10 rounded-xl transition-colors duration-150 text-foreground/60 hover:bg-[var(--glass-bg-hover)] hover:text-foreground"
          title={item.label}
          data-testid={`nav-item-${item.id}`}
        >
          <Icon className="w-4 h-4" />
        </a>
      );
    }
    return (
      <a
        href={item.href}
        target="_blank"
        rel="noopener noreferrer"
        className={`relative w-full flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-[background-color,color] duration-150 text-foreground/60 hover:bg-[var(--glass-bg-hover)] hover:text-foreground/85 ${indentClass}`}
        data-testid={`nav-item-${item.id}`}
      >
        <Icon className="w-4 h-4 shrink-0" strokeWidth={2} />
        <span className="truncate">{item.label}</span>
        {item.badge && (
          <BadgeChip badge={item.badge} />
        )}
      </a>
    );
  }

  // Module button (collapsed)
  if (collapsed) {
    return (
      <button
        onClick={() => {
          onModuleChange(item.id);
          setMobileOpen?.(false);
        }}
        className={`relative w-full grid place-items-center h-10 rounded-xl transition-colors duration-150
          ${
            isActive
              ? 'bg-[var(--nav-pill-active)] text-[hsl(var(--primary))]'
              : 'text-foreground/60 hover:bg-[var(--glass-bg-hover)] hover:text-foreground'
          }`}
        title={item.label}
        data-testid={`nav-item-${item.id}`}
      >
        {isActive && (
          <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-[hsl(var(--primary))]" />
        )}
        <Icon className="w-4 h-4" />
        {item.badge && (
          <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-[hsl(var(--primary))]" />
        )}
      </button>
    );
  }

  // Module button (expanded)
  return (
    <button
      onClick={() => {
        onModuleChange(item.id);
        setMobileOpen?.(false);
      }}
      className={`relative w-full flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm
        transition-[background-color,color] duration-150 ease-smooth-out
        ${
          isActive
            ? 'bg-[var(--nav-pill-active)] text-foreground'
            : 'text-foreground/60 hover:bg-[var(--glass-bg-hover)] hover:text-foreground/85'
        }
        ${indentClass}`}
      data-testid={`nav-item-${item.id}`}
    >
      {isActive && (
        <span
          className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-[hsl(var(--primary))]"
          aria-hidden="true"
        />
      )}
      <Icon
        className={`w-4 h-4 shrink-0 ${isActive ? 'text-[hsl(var(--primary))]' : ''}`}
        strokeWidth={2}
      />
      <span className="truncate">{item.label}</span>
      {item.badge && (
        <BadgeChip badge={item.badge} />
      )}
    </button>
  );
}
