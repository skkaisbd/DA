/**
 * AccountBadge & PlatformBadge
 * Reusable colored badge components untuk platform accounts.
 * Dipakai di semua modul Portal Marketing.
 */

export const PLATFORM_CONFIG = {
  shopee: {
    label: 'Shopee',
    icon: '🛍️',
    bg: 'bg-orange-100 dark:bg-orange-500/15',
    text: 'text-orange-500',
    border: 'border-orange-400 dark:border-orange-500/30',
    dot: 'bg-orange-400',
  },
  tiktokshop: {
    label: 'TikTok',
    icon: '🎵',
    bg: 'bg-pink-100 dark:bg-pink-500/15',
    text: 'text-pink-500',
    border: 'border-pink-400 dark:border-pink-500/30',
    dot: 'bg-pink-400',
  },
  tokopedia: {
    label: 'Tokopedia',
    icon: '🟢',
    bg: 'bg-emerald-100 dark:bg-emerald-500/15',
    text: 'text-emerald-600',
    border: 'border-emerald-400 dark:border-emerald-500/30',
    dot: 'bg-emerald-400',
  },
  lazada: {
    label: 'Lazada',
    icon: '🔵',
    bg: 'bg-blue-100 dark:bg-blue-500/15',
    text: 'text-blue-500',
    border: 'border-blue-400 dark:border-blue-500/30',
    dot: 'bg-blue-400',
  },
  blibli: {
    label: 'Blibli',
    icon: '🔷',
    bg: 'bg-sky-100 dark:bg-sky-500/15',
    text: 'text-sky-500',
    border: 'border-sky-400 dark:border-sky-500/30',
    dot: 'bg-sky-400',
  },
};

const DEFAULT_CONFIG = {
  label: 'Platform',
  icon: '🏪',
  bg: 'bg-muted dark:bg-gray-500/15',
  text: 'text-muted-foreground/80',
  border: 'border-border dark:border-gray-500/30',
  dot: 'bg-muted',
};

export function getPlatformConfig(platform) {
  return PLATFORM_CONFIG[(platform || '').toLowerCase()] || DEFAULT_CONFIG;
}

const SIZE_CLASSES = {
  xs: 'text-[10px] px-1.5 py-0.5 gap-1',
  sm: 'text-xs px-2 py-0.5 gap-1.5',
  md: 'text-sm px-2.5 py-1 gap-2',
};

/**
 * AccountBadge — badge berwarna sesuai platform
 * Props:
 *   account  : { account_name, platform, account_code? }
 *   size     : 'xs' | 'sm' | 'md'
 *   showIcon : bool (default true)
 */
export function AccountBadge({ account, size = 'sm', showIcon = true }) {
  if (!account) return null;
  const cfg = getPlatformConfig(account.platform);
  const sz = SIZE_CLASSES[size] || SIZE_CLASSES.sm;

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium whitespace-nowrap
        ${cfg.bg} ${cfg.text} ${cfg.border} ${sz}`}
    >
      {showIcon && <span>{cfg.icon}</span>}
      <span className="truncate max-w-[140px]">{account.account_name}</span>
    </span>
  );
}

/**
 * PlatformBadge — badge platform saja (tanpa nama akun)
 */
export function PlatformBadge({ platform, size = 'sm' }) {
  const cfg = getPlatformConfig(platform);
  const sz = SIZE_CLASSES[size] || SIZE_CLASSES.sm;

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border font-medium
      ${cfg.bg} ${cfg.text} ${cfg.border} ${sz}`}
    >
      {cfg.icon} {cfg.label}
    </span>
  );
}
