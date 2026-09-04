import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles, RefreshCw, AlertTriangle, AlertCircle, Info, CheckCircle2,
  ArrowRight, X, ChevronRight, Lightbulb,
} from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { IconButton } from './IconButton';

/* ─── PT Rahaza ERP · NextActionWidget (Phase 16.2) ───────────────────────────
   Menampilkan kartu "apa yang harus dikerjakan selanjutnya" berdasarkan
   hasil rule engine backend (/api/rahaza/next-actions).

   Props:
     - token: JWT
     - portal: 'production' | 'management' | 'warehouse' | 'finance' | 'hr'
     - onNavigate(moduleId, params?): navigate ke modul saat CTA ditekan
     - onOpenSetupWizard: callback untuk action id='setup-empty' (cta_module='__setup_wizard__')
     - autoRefreshMs: default 60000 (1 menit)
     - maxCards: default 5

   Fitur UX:
     - Dismissible per-card (simpan di localStorage 4 jam snooze)
     - Severity color coding
     - Empty state positif "Tidak ada yang perlu ditindaklanjuti"
     - Refresh manual dengan animasi
───────────────────────────────────────────────────────────────────────────── */

const SEVERITY_META = {
  error: {
    icon: AlertCircle,
    bg: 'bg-[hsl(var(--destructive)/0.08)]',
    border: 'border-[hsl(var(--destructive)/0.30)]',
    iconColor: 'text-[hsl(var(--destructive))]',
    tag: 'bg-[hsl(var(--destructive)/0.15)] text-[hsl(var(--destructive))]',
    label: 'Kritikal',
  },
  warning: {
    icon: AlertTriangle,
    bg: 'bg-amber-400/8 dark:bg-amber-400/10',
    border: 'border-amber-300/30',
    iconColor: 'text-amber-500 dark:text-amber-300',
    tag: 'bg-amber-400/15 text-amber-600 dark:text-amber-300',
    label: 'Perlu Perhatian',
  },
  info: {
    icon: Info,
    bg: 'bg-[hsl(var(--primary)/0.06)]',
    border: 'border-[hsl(var(--primary)/0.25)]',
    iconColor: 'text-[hsl(var(--primary))]',
    tag: 'bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]',
    label: 'Saran',
  },
  success: {
    icon: CheckCircle2,
    bg: 'bg-emerald-400/8 dark:bg-emerald-400/10',
    border: 'border-emerald-300/30',
    iconColor: 'text-emerald-500 dark:text-emerald-300',
    tag: 'bg-emerald-400/15 text-emerald-600 dark:text-emerald-300',
    label: 'OK',
  },
};

const SNOOZE_MS = 4 * 60 * 60 * 1000; // 4 jam

function getSnoozedIds() {
  try {
    const raw = localStorage.getItem('rahaza_nae_snooze') || '{}';
    const obj = JSON.parse(raw);
    const now = Date.now();
    const fresh = {};
    Object.entries(obj).forEach(([id, ts]) => {
      if (now - ts < SNOOZE_MS) fresh[id] = ts;
    });
    localStorage.setItem('rahaza_nae_snooze', JSON.stringify(fresh));
    return new Set(Object.keys(fresh));
  } catch {
    return new Set();
  }
}

function snoozeId(id) {
  try {
    const raw = localStorage.getItem('rahaza_nae_snooze') || '{}';
    const obj = JSON.parse(raw);
    obj[id] = Date.now();
    localStorage.setItem('rahaza_nae_snooze', JSON.stringify(obj));
  } catch {
    /* ignore */
  }
}

export function NextActionWidget({
  token,
  portal = 'production',
  onNavigate,
  onOpenSetupWizard,
  autoRefreshMs = 60_000,
  maxCards = 5,
}) {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState('');
  const [snoozedTick, setSnoozedTick] = useState(0);
  const [expanded, setExpanded] = useState(null); // card id yang sedang di-expand "why"

  const fetchActions = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/rahaza/next-actions?portal=${portal}&limit=12`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setActions(data.actions || []);
        setLastUpdated(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }));
      }
    } catch (e) {
      /* fail silent */
    } finally {
      setLoading(false);
    }
  }, [token, portal]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  useEffect(() => {
    if (!autoRefreshMs) return;
    const id = setInterval(fetchActions, autoRefreshMs);
    return () => clearInterval(id);
  }, [fetchActions, autoRefreshMs]);

  const snoozedIds = getSnoozedIds();
  const visibleActions = actions
    .filter((a) => !snoozedIds.has(a.id))
    .slice(0, maxCards);

  const handleCTA = (card) => {
    if (card.cta_module === '__setup_wizard__') {
      onOpenSetupWizard?.();
      return;
    }
    if (onNavigate && card.cta_module) {
      onNavigate(card.cta_module, card.cta_params);
    }
  };

  const handleSnooze = (id) => {
    snoozeId(id);
    setSnoozedTick((x) => x + 1);
  };

  // Empty positive state
  if (!loading && visibleActions.length === 0) {
    return (
      <GlassPanel
        className="p-4 border-[hsl(var(--primary)/0.15)]"
        data-testid="next-action-widget-empty"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-400/10 border border-emerald-300/25 grid place-items-center flex-shrink-0">
            <CheckCircle2 className="w-4.5 h-4.5 text-emerald-500 dark:text-emerald-300" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-foreground">Semua terkendali</div>
            <div className="text-xs text-muted-foreground">Tidak ada tindakan mendesak. Terus pantau line board dan dashboard.</div>
          </div>
          <IconButton
            label="Muat ulang tindakan"
            onClick={fetchActions}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 p-1 rounded"
            data-testid="next-action-refresh-empty"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </IconButton>
        </div>
      </GlassPanel>
    );
  }

  return (
    <div className="space-y-2" data-testid="next-action-widget">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.25)] grid place-items-center">
            <Sparkles className="w-3.5 h-3.5 text-[hsl(var(--primary))]" />
          </div>
          <span className="text-sm font-semibold text-foreground">Yang Perlu Ditindaklanjuti</span>
          {visibleActions.length > 0 && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]">
              {visibleActions.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastUpdated && (
            <span className="text-[10px] text-muted-foreground">{lastUpdated}</span>
          )}
          <IconButton
            label="Muat ulang tindakan"
            onClick={fetchActions}
            disabled={loading}
            className="p-1 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground disabled:opacity-50"
            data-testid="next-action-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </IconButton>
        </div>
      </div>

      {/* Loading state */}
      {loading && visibleActions.length === 0 && (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <GlassPanel key={i} className="p-3 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[var(--glass-bg)]" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-1/2 rounded bg-[var(--glass-bg)]" />
                  <div className="h-2 w-3/4 rounded bg-[var(--glass-bg)]" />
                </div>
              </div>
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Cards */}
      <div className="space-y-2">
        {visibleActions.map((a) => {
          const meta = SEVERITY_META[a.severity] || SEVERITY_META.info;
          const Icon = meta.icon;
          const isExpanded = expanded === a.id;
          return (
            <GlassPanel
              key={a.id}
              className={`p-3 border ${meta.border} ${meta.bg} transition-colors`}
              data-testid={`nae-card-${a.id}`}
            >
              <div className="flex items-start gap-3">
                <div className={`w-9 h-9 rounded-xl ${meta.tag.split(' ')[0]} grid place-items-center flex-shrink-0 border ${meta.border}`}>
                  <Icon className={`w-4 h-4 ${meta.iconColor}`} strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-foreground leading-tight">{a.title}</span>
                        <span className={`text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${meta.tag}`}>
                          {meta.label}
                        </span>
                      </div>
                      {a.description && (
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{a.description}</p>
                      )}
                    </div>
          <button
            onClick={() => handleSnooze(a.id)}
            className="p-1 rounded hover:bg-[var(--glass-bg-hover)] text-muted-foreground/60 hover:text-muted-foreground flex-shrink-0"
            title="Sembunyikan 4 jam"
            aria-label="Sembunyikan 4 jam"
            data-testid={`nae-snooze-${a.id}`}
          >
            <X className="w-3.5 h-3.5" />
          </button>
                  </div>

                  {/* Why expandable */}
                  {a.why && (
                    <button
                      onClick={() => setExpanded(isExpanded ? null : a.id)}
                      className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/80 hover:text-foreground mt-1.5"
                      data-testid={`nae-why-${a.id}`}
                    >
                      <Lightbulb className="w-3 h-3" />
                      {isExpanded ? 'Tutup penjelasan' : 'Kenapa ini penting?'}
                      <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                    </button>
                  )}
                  {isExpanded && a.why && (
                    <p className="mt-1.5 text-[11px] text-muted-foreground leading-relaxed border-l-2 border-[var(--glass-border)] pl-2">
                      {a.why}
                    </p>
                  )}

                  {/* CTA */}
                  <div className="flex items-center justify-end mt-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleCTA(a)}
                      className="h-7 px-2.5 text-xs border border-[var(--glass-border)] hover:border-[hsl(var(--primary)/0.4)]"
                      data-testid={`nae-cta-${a.id}`}
                    >
                      {a.cta_label || 'Buka'}
                      <ArrowRight className="w-3 h-3 ml-1" />
                    </Button>
                  </div>
                </div>
              </div>
            </GlassPanel>
          );
        })}
      </div>
    </div>
  );
}

export default NextActionWidget;
