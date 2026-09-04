import { useState, useMemo, useEffect } from 'react';
import { Sheet, SheetContent, SheetOverlay } from '@/components/ui/sheet';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import {
  HelpCircle, X, Image as ImageIcon, BookOpen, MousePointerClick,
  Lightbulb, AlertTriangle, PlayCircle, ChevronRight, Sparkles,
} from 'lucide-react';
import { getModuleHelp, MODULES_WITH_DIAGRAM } from './moduleHelpData';
import { DIAGRAMS } from './Illustrations';
import { SCENARIOS } from './guideData';

/**
 * Drawer Help untuk modul saat ini.
 * Menampilkan: pengenalan, screenshot, tombol+aksi, tips, scenario terkait, tour trigger.
 */
export default function ModuleHelpDrawer({ open, onOpenChange, moduleId, onStartTour }) {
  const help = useMemo(() => getModuleHelp(moduleId), [moduleId]);
  const [imgError, setImgError] = useState(false);
  const Diagram = MODULES_WITH_DIAGRAM[moduleId] ? DIAGRAMS[MODULES_WITH_DIAGRAM[moduleId]] : null;

  // Reset image error when module changes (Session #11.17: was useMemo, now useEffect — side effect, not memoization)
  useEffect(() => { setImgError(false); }, [moduleId]);

  if (!help) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetOverlay className="bg-foreground/40 backdrop-blur-sm" />
        <SheetContent className="!max-w-md w-full sm:!max-w-md overflow-y-auto z-[60]" data-testid="module-help-drawer">
          <VisuallyHidden>
            <DialogPrimitive.Title>Bantuan Modul</DialogPrimitive.Title>
            <DialogPrimitive.Description>Bantuan tidak tersedia untuk modul ini.</DialogPrimitive.Description>
          </VisuallyHidden>
          <div className="text-center py-12">
            <HelpCircle className="w-10 h-10 mx-auto text-foreground/30 mb-3" />
            <p className="text-sm text-foreground/60">Bantuan untuk modul ini belum tersedia.</p>
            <p className="text-xs text-foreground/40 mt-2">Buka <strong>Panduan Penggunaan</strong> di Portal Selector untuk panduan lengkap.</p>
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  const Icon = help.icon || HelpCircle;
  const hasScenarios = help.relatedScenarios?.length > 0;
  const hasTour = help.tour?.length > 0;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetOverlay className="bg-foreground/40 backdrop-blur-sm z-[59]" />
      <SheetContent
        className="!max-w-md sm:!max-w-md md:!max-w-lg w-full overflow-y-auto p-0 bg-[var(--card-surface)] border-l border-[var(--glass-border)] z-[60]"
        data-testid="module-help-drawer"
      >
        <VisuallyHidden>
          <DialogPrimitive.Title>Bantuan: {help.title}</DialogPrimitive.Title>
          <DialogPrimitive.Description>{help.purpose}</DialogPrimitive.Description>
        </VisuallyHidden>

        {/* Header */}
        <div className="sticky top-0 z-10 bg-gradient-to-b from-[hsl(var(--primary)/0.12)] to-transparent border-b border-[var(--glass-border)] px-5 py-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.30)] grid place-items-center shrink-0">
              <Icon className="w-5 h-5 text-[hsl(var(--primary))]" strokeWidth={2.2} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-[hsl(var(--primary))] font-bold">Bantuan Modul</p>
              <h2 className="text-base font-bold text-foreground leading-tight mt-0.5">{help.title}</h2>
              {help.whoUses && (
                <p className="text-[11px] text-foreground/50 mt-0.5">Pengguna: {help.whoUses}</p>
              )}
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="w-8 h-8 rounded-lg grid place-items-center text-foreground/50 hover:text-foreground hover:bg-foreground/10 transition-colors shrink-0"
              aria-label="Tutup bantuan"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Tour CTA */}
          {hasTour && (
            <button
              onClick={() => { onOpenChange(false); setTimeout(() => onStartTour?.(help.tour), 300); }}
              className="w-full flex items-center gap-3 p-3 rounded-xl bg-gradient-to-r from-violet-500/15 to-fuchsia-500/15 border border-violet-400 dark:border-violet-500/30 hover:border-violet-500/50 transition-colors group"
              data-testid="help-start-tour-btn"
            >
              <div className="w-9 h-9 rounded-lg bg-violet-100 dark:bg-violet-500/20 grid place-items-center shrink-0">
                <Sparkles className="w-4 h-4 text-violet-500" />
              </div>
              <div className="text-left flex-1">
                <p className="text-sm font-semibold text-foreground">Mulai Tour Interaktif</p>
                <p className="text-[11px] text-foreground/55">Sistem akan highlight tombol satu per satu</p>
              </div>
              <ChevronRight className="w-4 h-4 text-foreground/40 group-hover:text-violet-500 group-hover:translate-x-0.5 transition-all" />
            </button>
          )}

          {/* Purpose */}
          <section>
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
              <BookOpen className="w-3.5 h-3.5" /> Tujuan Halaman
            </h3>
            <p className="text-sm text-foreground/80 leading-relaxed">{help.purpose}</p>
          </section>

          {/* Screenshot */}
          {help.screenshot && !imgError && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
                <ImageIcon className="w-3.5 h-3.5" /> Tampilan Halaman
              </h3>
              <div className="rounded-xl border border-[var(--glass-border)] bg-foreground/[0.02] overflow-hidden">
                <img
                  src={help.screenshot}
                  alt={`Screenshot ${help.title}`}
                  className="w-full h-auto block"
                  onError={() => setImgError(true)}
                  data-testid="help-screenshot"
                />
              </div>
            </section>
          )}

          {/* Diagram */}
          {Diagram && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
                <Sparkles className="w-3.5 h-3.5" /> Diagram Konsep
              </h3>
              <Diagram />
            </section>
          )}

          {/* Sections breakdown */}
          {help.sections?.length > 0 && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
                <BookOpen className="w-3.5 h-3.5" /> Bagian Halaman
              </h3>
              <ul className="space-y-1.5">
                {help.sections.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-foreground/75">
                    <span className="w-5 h-5 rounded-full bg-[hsl(var(--primary)/0.10)] text-[hsl(var(--primary))] grid place-items-center text-[10px] font-bold shrink-0 mt-0.5">{i + 1}</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Buttons */}
          {help.buttons?.length > 0 && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
                <MousePointerClick className="w-3.5 h-3.5" /> Tombol & Aksi
              </h3>
              <div className="space-y-2">
                {help.buttons.map((btn, i) => {
                  const BIcon = btn.icon || MousePointerClick;
                  return (
                    <div key={i} className="rounded-lg border border-[var(--glass-border)] bg-foreground/[0.02] p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-7 h-7 rounded-lg bg-[hsl(var(--primary)/0.10)] grid place-items-center">
                          <BIcon className="w-3.5 h-3.5 text-[hsl(var(--primary))]" strokeWidth={2.2} />
                        </div>
                        <span className="text-sm font-semibold text-foreground">{btn.label}</span>
                      </div>
                      <p className="text-xs text-foreground/70 ml-9 leading-relaxed">{btn.action}</p>
                      {btn.when && (
                        <p className="text-[11px] text-foreground/45 ml-9 mt-1 italic">Kapan dipakai: {btn.when}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Tips */}
          {help.tips?.length > 0 && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-600 mb-2">
                <Lightbulb className="w-3.5 h-3.5" /> Tips
              </h3>
              <div className="rounded-xl border border-amber-400 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/5 p-3 space-y-1.5">
                {help.tips.map((t, i) => (
                  <p key={i} className="text-xs text-foreground/75 leading-relaxed flex items-start gap-1.5">
                    <span className="text-amber-500 shrink-0">•</span>
                    <span>{t}</span>
                  </p>
                ))}
              </div>
            </section>
          )}

          {/* Warnings */}
          {help.warnings?.length > 0 && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-red-600 mb-2">
                <AlertTriangle className="w-3.5 h-3.5" /> Penting
              </h3>
              <div className="rounded-xl border border-red-400 dark:border-red-500/30 bg-red-100 dark:bg-red-500/5 p-3 space-y-1.5">
                {help.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-foreground/75 leading-relaxed flex items-start gap-1.5">
                    <span className="text-red-500 shrink-0">!</span>
                    <span>{w}</span>
                  </p>
                ))}
              </div>
            </section>
          )}

          {/* Related scenarios */}
          {hasScenarios && (
            <section>
              <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-foreground/60 mb-2">
                <PlayCircle className="w-3.5 h-3.5" /> Skenario Terkait
              </h3>
              <div className="space-y-1.5">
                {help.relatedScenarios.map((sid) => {
                  const sc = SCENARIOS.find((s) => s.id === sid);
                  if (!sc) return null;
                  return (
                    <div
                      key={sid}
                      className="rounded-lg border border-cyan-300 dark:border-cyan-500/20 bg-cyan-100 dark:bg-cyan-500/5 p-2.5 flex items-start gap-2"
                    >
                      <div className="w-7 h-7 rounded-md bg-cyan-100 dark:bg-cyan-500/15 border border-cyan-400 dark:border-cyan-500/30 grid place-items-center shrink-0">
                        <span className="text-[10px] font-black text-cyan-600">{sc.code}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-foreground">{sc.title}</p>
                        <p className="text-[11px] text-foreground/55 mt-0.5 line-clamp-2">{sc.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="text-[10px] text-foreground/45 mt-2 italic">
                Buka Panduan Penggunaan (📖) untuk lihat skenario lengkap dengan langkah & pre-requisite.
              </p>
            </section>
          )}
        </div>

        {/* Close button (built-in by Sheet, but we hide and use custom in header) */}
      </SheetContent>
    </Sheet>
  );
}
