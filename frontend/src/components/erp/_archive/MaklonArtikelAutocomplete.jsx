/**
 * MaklonArtikelAutocomplete — Phase M2.4 + M2.3
 *
 * Combobox autocomplete untuk field "Artikel" di MaklonPOModule items grid.
 * Fitur:
 *   - Debounced search (200ms) ke /api/dewi/maklon/buyer-catalog?client_id=&search=
 *   - Saran HANYA artikel ACTIVE milik client yang dipilih
 *   - Pilih item → callback `onPick(catalogItem)` (fill artikel + cmt_rate + buyer_catalog_id)
 *   - Inline drift warning badge (jika item.buyer_catalog_id ada & cmt_rate_per_pcs beda dari default)
 *
 * Props:
 *   value          — string artikel saat ini
 *   onChange       — (newArtikelString) => void   (free typing tetap diperbolehkan)
 *   onPick         — (catalogItem) => void
 *   clientId       — string | required untuk fetch saran
 *   currentRate    — float (cmt_rate_per_pcs row ini) untuk drift check
 *   currentCatalogId — string | null (kalau item ini sudah ter-link)
 *   headers        — Authorization headers
 *   disabled       — boolean
 *   onClearCatalogLink — () => void  (clear buyer_catalog_id link)
 */
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { BookOpen, Sparkles, AlertTriangle, ShieldAlert, CheckCircle2, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { formatRupiah } from '@/lib/format';

const fmtRp = formatRupiah;

export default function MaklonArtikelAutocomplete({
  value,
  onChange,
  onPick,
  clientId,
  currentRate,
  currentCatalogId,
  headers,
  disabled,
  onClearCatalogLink,
  testIdPrefix = 'artikel-autocomplete',
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [drift, setDrift] = useState(null);
  const debounceRef = useRef(null);
  const wrapperRef = useRef(null);

  // ── Fetch suggestions (debounced) ────────────────────────────────────────
  const fetchSuggestions = useCallback(async (query) => {
    if (!clientId) {
      setSuggestions([]);
      return;
    }
    try {
      const qs = new URLSearchParams();
      qs.append('client_id', clientId);
      qs.append('status', 'active');
      if (query && query.trim()) qs.append('search', query.trim());
      qs.append('limit', '8');
      const r = await fetch(`/api/dewi/maklon/buyer-catalog?${qs.toString()}`, { headers });
      if (r.ok) {
        const data = await r.json();
        setSuggestions(data);
      } else {
        setSuggestions([]);
      }
    } catch (_e) {
      setSuggestions([]);
    }
  }, [clientId, headers]);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 200);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [value, open, fetchSuggestions]);

  // ── Drift check (inline) ─────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function check() {
      if (!currentCatalogId || !currentRate || Number(currentRate) <= 0) {
        if (!cancelled) setDrift(null);
        return;
      }
      try {
        const r = await fetch(
          `/api/dewi/maklon/buyer-catalog/${currentCatalogId}/check-drift`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({ actual_price: Number(currentRate) }),
          }
        );
        if (r.ok) {
          const d = await r.json();
          if (!cancelled) setDrift(d);
        }
      } catch (_e) {
        // silent
      }
    }
    // Debounce drift check to avoid spamming on every keystroke
    const t = setTimeout(check, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [currentCatalogId, currentRate, headers]);

  // ── Close dropdown on outside click ──────────────────────────────────────
  useEffect(() => {
    function handler(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSelect = (item) => {
    onPick?.(item);
    setOpen(false);
    setActiveIdx(-1);
  };

  const handleKeyDown = (e) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(suggestions.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      if (activeIdx >= 0 && suggestions[activeIdx]) {
        e.preventDefault();
        handleSelect(suggestions[activeIdx]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  // ── Drift visual state ───────────────────────────────────────────────────
  const driftBadge = useMemo(() => {
    if (!drift || drift.severity === 'ok') return null;
    const isBlock = drift.severity === 'block';
    return {
      icon: isBlock ? ShieldAlert : AlertTriangle,
      color: isBlock
        ? 'bg-red-500/15 text-red-300 border-red-400/30'
        : 'bg-amber-500/15 text-amber-300 border-amber-400/30',
      label: `${drift.drift_pct > 0 ? '+' : ''}${drift.drift_pct}%`,
      tip: drift.message,
      severity: drift.severity,
    };
  }, [drift]);

  return (
    <div className="relative w-full" ref={wrapperRef} data-testid={`${testIdPrefix}-wrapper`}>
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <Input
            value={value || ''}
            onChange={(e) => {
              onChange?.(e.target.value);
              if (!open) setOpen(true);
            }}
            onFocus={() => {
              if (clientId) setOpen(true);
            }}
            onKeyDown={handleKeyDown}
            placeholder={clientId ? 'Ketik / pilih artikel...' : 'Pilih klien dulu'}
            disabled={disabled || !clientId}
            className={`h-7 text-xs bg-foreground/5 border-border w-32 pr-6 ${
              currentCatalogId ? 'border-violet-400/40 bg-violet-500/5' : ''
            }`}
            data-testid={`${testIdPrefix}-input`}
            autoComplete="off"
          />
          {currentCatalogId && (
            <BookOpen className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-violet-400" />
          )}
        </div>

        {/* Clear link button */}
        {currentCatalogId && !disabled && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="w-6 h-6 shrink-0 text-foreground/40 hover:text-red-400"
            onClick={onClearCatalogLink}
            title="Lepas link Buyer Catalog (jadi freestyle)"
            data-testid={`${testIdPrefix}-clear-link`}
          >
            <X className="w-3 h-3" />
          </Button>
        )}
      </div>

      {/* Drift Badge inline */}
      {driftBadge && (
        <div
          className={`mt-1 inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded border ${driftBadge.color}`}
          title={driftBadge.tip}
          data-testid={`${testIdPrefix}-drift-badge`}
          data-severity={driftBadge.severity}
        >
          <driftBadge.icon className="w-2.5 h-2.5" />
          {driftBadge.label}
        </div>
      )}

      {/* Match badge (rate sama dengan default) */}
      {currentCatalogId && drift && drift.severity === 'ok' && Number(currentRate) > 0 && (
        <div
          className="mt-1 inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded border bg-emerald-500/10 text-emerald-300 border-emerald-400/25"
          data-testid={`${testIdPrefix}-drift-ok`}
        >
          <CheckCircle2 className="w-2.5 h-2.5" />
          match
        </div>
      )}

      {/* Suggestions dropdown */}
      {open && clientId && suggestions.length > 0 && (
        <div
          className="absolute z-50 left-0 mt-1 w-72 max-h-64 overflow-y-auto rounded-lg border border-border bg-popover backdrop-blur-md shadow-xl"
          data-testid={`${testIdPrefix}-dropdown`}
        >
          <div className="px-2 py-1.5 border-b border-border/60 flex items-center gap-1.5 text-[10px] text-foreground/55">
            <Sparkles className="w-3 h-3 text-violet-400" />
            Saran dari Buyer Catalog
          </div>
          {suggestions.map((s, idx) => (
            <button
              key={s.id}
              type="button"
              className={`w-full text-left px-2 py-1.5 text-xs border-b border-foreground/[0.04] last:border-b-0 transition-colors ${
                idx === activeIdx
                  ? 'bg-violet-500/15 text-violet-700 dark:text-violet-100'
                  : 'hover:bg-foreground/5 text-foreground/85'
              }`}
              onClick={() => handleSelect(s)}
              onMouseEnter={() => setActiveIdx(idx)}
              data-testid={`${testIdPrefix}-item-${s.id}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-violet-600 dark:text-violet-300 text-[10px] bg-violet-500/15 px-1 py-px rounded">
                      {s.artikel_code}
                    </span>
                    <span className="truncate font-medium">{s.product_name}</span>
                  </div>
                  <div className="text-[10px] text-foreground/55 mt-0.5">
                    CMT default: <strong className="text-amber-600 dark:text-amber-400">{fmtRp(s.default_cmt_price)}</strong>
                    {s.buyer_ref_code && <span className="ml-1.5 text-foreground/45">· {s.buyer_ref_code}</span>}
                  </div>
                </div>
                <BookOpen className="w-3 h-3 text-violet-500 dark:text-violet-400 shrink-0 opacity-60" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Empty state ketika ada query tapi tidak ada match */}
      {open && clientId && value && suggestions.length === 0 && (
        <div
          className="absolute z-50 left-0 mt-1 w-72 rounded-lg border border-border bg-popover backdrop-blur-md shadow-xl px-3 py-2"
          data-testid={`${testIdPrefix}-empty`}
        >
          <div className="text-[10px] text-foreground/55 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-violet-500/70 dark:text-violet-400/60" />
            Tidak ada artikel cocok di Buyer Catalog
          </div>
          <div className="text-[10px] text-foreground/45 mt-0.5">
            Ketik bebas atau tambahkan artikel di Buyer Catalog dulu.
          </div>
        </div>
      )}
    </div>
  );
}
