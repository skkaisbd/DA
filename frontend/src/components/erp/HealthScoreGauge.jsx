/**
 * HealthScoreGauge — circular progress untuk display health score 0-100.
 * Pure SVG, no external deps.
 */
export function HealthScoreGauge({ score = 0, size = 120, strokeWidth = 10, label = 'Health Score' }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const safe = Math.min(100, Math.max(0, score));
  const offset = circumference - (safe / 100) * circumference;

  const colorFor = (s) => {
    if (s >= 80) return 'text-emerald-400';
    if (s >= 60) return 'text-yellow-400';
    if (s >= 40) return 'text-orange-400';
    return 'text-red-400';
  };

  const strokeColor = colorFor(safe);
  const ringColor = (safe >= 80) ? '#34d399' : (safe >= 60) ? '#facc15' : (safe >= 40) ? '#fb923c' : '#f87171';

  return (
    <div className="flex flex-col items-center justify-center" data-testid="health-score-gauge">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={strokeWidth}
            fill="none"
            className="text-foreground/10"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={ringColor}
            strokeWidth={strokeWidth}
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 600ms ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className={`text-3xl font-bold tabular-nums ${strokeColor}`}>{safe}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">/ 100</div>
        </div>
      </div>
      {label && <div className="text-xs text-muted-foreground mt-2">{label}</div>}
    </div>
  );
}
