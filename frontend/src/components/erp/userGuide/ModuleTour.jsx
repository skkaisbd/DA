import { useState, useEffect, useLayoutEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, X, Sparkles } from 'lucide-react';

/**
 * Lightweight tour overlay tanpa external library.
 * Steps: [{ selector, title, content, position?: 'top'|'bottom'|'left'|'right' }]
 *
 * Behavior:
 *  - Find element by selector. Kalau tidak ada, skip ke step berikutnya.
 *  - Highlight dengan box-shadow ring di sekitar element.
 *  - Tooltip muncul disamping element (auto-position kalau tidak fit).
 *  - Tombol Prev / Next / Skip / Selesai.
 */
export default function ModuleTour({ steps, onClose }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [bbox, setBbox] = useState(null);
  const step = steps?.[stepIndex];
  const total = steps?.length || 0;

  const updatePosition = useCallback(() => {
    if (!step?.selector) return setBbox(null);
    let el = null;
    try {
      el = document.querySelector(step.selector);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[ModuleTour] Invalid selector:', step.selector, err);
      return setBbox(null);
    }
    if (!el) return setBbox(null);
    const rect = el.getBoundingClientRect();
    setBbox({
      top: rect.top, left: rect.left, width: rect.width, height: rect.height,
    });
    // Scroll into view
    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  }, [step]);

  useLayoutEffect(() => {
    updatePosition();
    const handler = () => updatePosition();
    window.addEventListener('resize', handler);
    window.addEventListener('scroll', handler, true);
    return () => {
      window.removeEventListener('resize', handler);
      window.removeEventListener('scroll', handler, true);
    };
  }, [updatePosition]);

  // ESC = close
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIndex]);

  if (!steps?.length || !step) return null;

  const next = () => {
    if (stepIndex < total - 1) setStepIndex((i) => i + 1);
    else onClose?.();
  };
  const prev = () => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  };

  // Compute tooltip position
  let tooltipStyle = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };
  if (bbox) {
    const pos = step.position || 'auto';
    const margin = 16;
    const tooltipWidth = 360;
    const tooltipHeight = 180;
    let top, left;
    const wantBottom = pos === 'bottom' || (pos === 'auto' && bbox.top < window.innerHeight / 2);
    if (wantBottom) top = bbox.top + bbox.height + margin;
    else top = bbox.top - tooltipHeight - margin;

    left = bbox.left + bbox.width / 2 - tooltipWidth / 2;
    // Clamp horizontally
    left = Math.max(16, Math.min(left, window.innerWidth - tooltipWidth - 16));
    // Clamp vertically
    top = Math.max(16, Math.min(top, window.innerHeight - tooltipHeight - 16));
    tooltipStyle = { top: `${top}px`, left: `${left}px`, transform: 'none', width: `${tooltipWidth}px` };
  }

  // Highlight box (around target)
  const ringStyle = bbox
    ? {
        top: `${bbox.top - 6}px`,
        left: `${bbox.left - 6}px`,
        width: `${bbox.width + 12}px`,
        height: `${bbox.height + 12}px`,
      }
    : null;

  return (
    <div className="fixed inset-0 z-[100]" data-testid="module-tour-overlay">
      {/* Dim background */}
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" onClick={onClose} />

      {/* Element ring highlight */}
      {ringStyle && (
        <div
          className="fixed pointer-events-none rounded-xl ring-4 ring-violet-500/70 shadow-[0_0_0_9999px_rgba(0,0,0,0.55)] transition-all duration-300"
          style={ringStyle}
        />
      )}

      {/* Tooltip card */}
      <div
        className="fixed bg-[var(--card-surface)] border border-violet-500/40 rounded-2xl shadow-2xl p-4 z-10 transition-all duration-200"
        style={tooltipStyle}
        data-testid="module-tour-tooltip"
      >
        <div className="flex items-start gap-2 mb-2">
          <div className="w-8 h-8 rounded-lg bg-violet-100 dark:bg-violet-500/15 border border-violet-400 dark:border-violet-500/30 grid place-items-center shrink-0">
            <Sparkles className="w-4 h-4 text-violet-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase tracking-wider text-violet-600 font-bold">
              Step {stepIndex + 1} dari {total}
            </p>
            <h4 className="text-sm font-bold text-foreground leading-tight">{step.title}</h4>
          </div>
          <button
            onClick={onClose}
            className="text-foreground/40 hover:text-foreground p-1"
            data-testid="tour-close-btn"
            aria-label="Tutup tour"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-foreground/75 leading-relaxed mb-3">{step.content}</p>
        {!bbox && step.selector && (
          <p className="text-[10px] text-amber-600 italic mb-2">
            (Elemen tidak ditemukan di halaman ini — mungkin perlu scroll atau aksi lain)
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          <button
            onClick={prev}
            disabled={stepIndex === 0}
            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-foreground/60 hover:text-foreground hover:bg-foreground/5 disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-1"
            data-testid="tour-prev-btn"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Sebelumnya
          </button>
          {/* Progress dots */}
          <div className="flex items-center gap-1">
            {steps.map((_, i) => (
              <span
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-all ${
                  i === stepIndex ? 'bg-violet-500 w-4' : 'bg-foreground/20'
                }`}
              />
            ))}
          </div>
          <button
            onClick={next}
            className="px-3 py-1.5 rounded-lg bg-violet-500 hover:bg-violet-600 text-foreground text-xs font-semibold inline-flex items-center gap-1 transition-colors"
            data-testid="tour-next-btn"
          >
            {stepIndex === total - 1 ? 'Selesai' : 'Lanjut'} <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
