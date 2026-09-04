/**
 * AccessBadge — small visual indicator of permission level on a document
 * (owner | admin | edit | view).
 */
import { ACCESS_CONFIG } from './utils';

export default function AccessBadge({ level }) {
  const cfg = ACCESS_CONFIG[level] || ACCESS_CONFIG.view;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${cfg.cls}`}
    >
      <Icon size={10} />
      {cfg.label}
    </span>
  );
}
