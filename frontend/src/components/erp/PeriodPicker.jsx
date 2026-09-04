/**
 * PeriodPicker — universal period filter untuk dashboard (Phase 13.3).
 *
 * Presets: Hari Ini, 7 hari, 30 hari, 90 hari, Bulan Ini, Bulan Lalu,
 *          Tahun Ini (YTD), Custom.
 *
 * Props:
 *   value: { preset, from, to, compare? }
 *   onChange: (newValue) => void
 *   compareEnabled: boolean — tampilkan toggle "vs periode sebelumnya"
 */
import { useState, useRef, useEffect, useMemo } from 'react';
import { Calendar, ChevronDown, Check, GitCompare } from 'lucide-react';
import { cn } from '@/lib/utils';

function iso(d) { return d.toISOString().slice(0, 10); }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0); }

function resolvePreset(preset) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  switch (preset) {
    case 'today':     return { from: iso(today), to: iso(today) };
    case '7d':        return { from: iso(addDays(today, -6)), to: iso(today) };
    case '30d':       return { from: iso(addDays(today, -29)), to: iso(today) };
    case '90d':       return { from: iso(addDays(today, -89)), to: iso(today) };
    case 'month':     return { from: iso(startOfMonth(today)), to: iso(today) };
    case 'last-month':{
      const last = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      return { from: iso(last), to: iso(endOfMonth(last)) };
    }
    case 'ytd':       return { from: `${today.getFullYear()}-01-01`, to: iso(today) };
    default:          return { from: null, to: null };
  }
}

const PRESETS = [
  { key: 'today',      label: 'Hari Ini' },
  { key: '7d',         label: '7 Hari' },
  { key: '30d',        label: '30 Hari' },
  { key: '90d',        label: '90 Hari' },
  { key: 'month',      label: 'Bulan Ini' },
  { key: 'last-month', label: 'Bulan Lalu' },
  { key: 'ytd',        label: 'Tahun Ini' },
  { key: 'custom',     label: 'Custom' },
];

export function PeriodPicker({ value, onChange, compareEnabled = true, testId = 'period-picker' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const preset = value?.preset || '30d';
  const from = value?.from || resolvePreset(preset).from;
  const to = value?.to || resolvePreset(preset).to;

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const currentLabel = useMemo(() => {
    const p = PRESETS.find(x => x.key === preset);
    if (preset === 'custom') return `${from || '…'} → ${to || '…'}`;
    return p?.label || 'Periode';
  }, [preset, from, to]);

  const pick = (key) => {
    if (key === 'custom') {
      onChange({ ...value, preset: 'custom', from: from || iso(new Date()), to: to || iso(new Date()) });
      return;
    }
    const r = resolvePreset(key);
    onChange({ ...value, preset: key, ...r });
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref} data-testid={testId}>
      <button
        onClick={() => setOpen(o => !o)}
        className="h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-xs text-foreground hover:bg-[var(--glass-bg-hover)] flex items-center gap-2 min-w-[160px]"
        data-testid={`${testId}-trigger`}
        aria-label="Pilih periode"
      >
        <Calendar className="w-3.5 h-3.5 text-foreground/50" />
        <span className="flex-1 text-left truncate">{currentLabel}</span>
        <ChevronDown className={cn('w-3.5 h-3.5 text-foreground/50 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1.5 w-[280px] rounded-lg border border-[var(--glass-border)] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] shadow-[var(--shadow-soft)] z-30 p-2">
          <div className="grid grid-cols-2 gap-1 mb-2">
            {PRESETS.map(p => (
              <button
                key={p.key}
                onClick={() => pick(p.key)}
                className={cn(
                  'h-8 px-2 rounded text-[11px] font-medium text-left transition-colors',
                  preset === p.key
                    ? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))]'
                    : 'text-foreground/70 hover:text-foreground hover:bg-[var(--glass-bg-hover)]'
                )}
                data-testid={`${testId}-preset-${p.key}`}
              >
                {preset === p.key && <Check className="inline w-3 h-3 mr-1" />}
                {p.label}
              </button>
            ))}
          </div>
          {preset === 'custom' && (
            <div className="space-y-1.5 pt-2 border-t border-[var(--glass-border)]">
              <label className="block text-[10px] uppercase tracking-wider text-foreground/50 font-semibold">Rentang</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="date" value={from || ''}
                  onChange={(e) => onChange({ ...value, preset: 'custom', from: e.target.value, to })}
                  className="flex-1 h-8 px-2 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-[11px]"
                  aria-label="Tanggal mulai"
                  data-testid={`${testId}-from`}
                />
                <span className="text-foreground/40">–</span>
                <input
                  type="date" value={to || ''}
                  onChange={(e) => onChange({ ...value, preset: 'custom', from, to: e.target.value })}
                  className="flex-1 h-8 px-2 rounded border border-[var(--glass-border)] bg-[var(--input-surface)] text-[11px]"
                  aria-label="Tanggal akhir"
                  data-testid={`${testId}-to`}
                />
              </div>
            </div>
          )}
          {compareEnabled && (
            <div className="pt-2 mt-2 border-t border-[var(--glass-border)]">
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-foreground/80 hover:text-foreground">
                <input
                  type="checkbox"
                  checked={!!value?.compare}
                  onChange={(e) => onChange({ ...value, compare: e.target.checked })}
                  className="cursor-pointer"
                  data-testid={`${testId}-compare`}
                />
                <GitCompare className="w-3 h-3" />
                Bandingkan dengan periode sebelumnya
              </label>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
