/**
 * StatusBadge — Generic pill renderer driven by configMap (status → label/color).
 * Extracted from AssetManagementPortal.jsx (Phase 1 refactor)
 */

export function StatusBadge({ status, configMap }) {
  const cfg = configMap[status] || { label: status, color: 'bg-muted text-muted-foreground' };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}
