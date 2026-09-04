/**
 * TD-014 Modal Unification (Session #11.13):
 * This legacy <Modal /> component is now a thin facade over Radix UI Dialog
 * primitives. All 41+ consumers (RahazaWorkOrdersModule, InvoiceModule,
 * PaymentModule, etc.) continue to work without code changes, but now benefit
 * from full Radix a11y (focus trap, ESC-to-close, aria-labelledby /
 * aria-describedby, portal rendering, scroll lock, etc.).
 *
 * Visual styling (GlassCard, IconButton) is preserved for backward
 * compatibility — no UI changes for end users.
 *
 * Public API (unchanged):
 *   <Modal title="..." onClose={fn} size="sm|md|lg|xl|2xl">{children}</Modal>
 *
 * New optional props:
 *   description    — accessibility description (sr-only by default)
 *   open           — controlled open state (default: true while mounted)
 *   onOpenChange   — called with new open state from Radix (ESC / overlay click)
 *   disableOutsideClose — disable click-outside / ESC dismissal (default: false)
 */
import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { IconButton } from './IconButton';

const SIZE_CLASSES = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
  '2xl': 'max-w-5xl',
  // 2026-08-07: tabel lebar (matriks warna × ukuran, baris biaya HPP, BOM tech pack)
  // tidak terbaca di max-w-5xl — kolomnya terpotong. Tambahan, bukan perubahan.
  '3xl': 'max-w-7xl',
};

function Modal({
  title,
  children,
  onClose,
  size = 'md',
  description,
  open,
  onOpenChange,
  disableOutsideClose = false,
  ...rest
}) {
  // Forward caller-supplied data-testid to the rendered dialog surface so tests
  // can target the specific modal (legacy facade previously dropped this prop).
  const dataTestId = rest['data-testid'];
  // Backward-compat: legacy callers don't pass `open`/`onOpenChange` —
  // they unmount the element entirely. While mounted, treat as open=true.
  const isControlled = typeof open === 'boolean';
  const effectiveOpen = isControlled ? open : true;

  const handleOpenChange = React.useCallback(
    (next) => {
      // Surface Radix close events to legacy onClose contract
      if (!next && typeof onClose === 'function') onClose();
      if (typeof onOpenChange === 'function') onOpenChange(next);
    },
    [onClose, onOpenChange],
  );

  // Optional defensive prop: disable dismiss-on-overlay & ESC for critical flows
  const interactionProps = disableOutsideClose
    ? {
        onPointerDownOutside: (e) => e.preventDefault(),
        onEscapeKeyDown:      (e) => e.preventDefault(),
        onInteractOutside:    (e) => e.preventDefault(),
      }
    : {};

  const autoDescId = React.useId();
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;

  return (
    <DialogPrimitive.Root open={effectiveOpen} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className="fixed inset-0 z-50 bg-[var(--overlay-bg)] backdrop-blur-sm
                     data-[state=open]:animate-in data-[state=closed]:animate-out
                     data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />
        <DialogPrimitive.Content
          className={`fixed left-[50%] top-[50%] z-50 w-full ${sizeClass}
                      translate-x-[-50%] translate-y-[-50%] outline-none
                      data-[state=open]:animate-in data-[state=closed]:animate-out
                      data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0
                      data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95`}
          aria-describedby={autoDescId}
          data-testid={dataTestId}
          {...interactionProps}
        >
          <GlassCard hover={false} className="relative max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--glass-border)]">
              <DialogPrimitive.Title asChild>
                <h2 className="font-semibold text-foreground text-lg">{title}</h2>
              </DialogPrimitive.Title>
              <DialogPrimitive.Close asChild>
                <IconButton
                  label="Tutup"
                  className="text-muted-foreground hover:text-foreground transition-colors"
                  data-testid="modal-close"
                >
                  <X className="w-5 h-5" />
                </IconButton>
              </DialogPrimitive.Close>
            </div>
            {/* sr-only description for Radix a11y compliance */}
            <DialogPrimitive.Description id={autoDescId} className="sr-only">
              {description || `Dialog: ${title || 'content'}`}
            </DialogPrimitive.Description>
            <div className="overflow-y-auto flex-1 px-6 py-4">{children}</div>
          </GlassCard>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export default Modal;
