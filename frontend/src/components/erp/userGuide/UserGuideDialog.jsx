import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { BookOpen } from 'lucide-react';
import UserGuideContent from './UserGuideContent';

/**
 * Modal versi UserGuide untuk dipakai di PortalSelector & dimanapun.
 * Full-screen-ish (max 6xl) — sidebar + content layout.
 */
export default function UserGuideDialog({ open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="!max-w-6xl w-[95vw] !p-0 gap-0 !rounded-2xl bg-[var(--glass-bg)] border border-[var(--glass-border)] backdrop-blur-xl overflow-hidden"
        data-testid="user-guide-dialog"
      >
        <VisuallyHidden>
          <DialogTitle>Panduan Penggunaan ERP</DialogTitle>
          <DialogDescription>Manual lengkap CV. Dewi Aditya — overview, portal, skenario, dan tips.</DialogDescription>
        </VisuallyHidden>
        {/* Header bar */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[var(--glass-border)] bg-gradient-to-r from-[hsl(var(--primary)/0.06)] to-transparent">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.30)] grid place-items-center">
              <BookOpen className="w-4 h-4 text-[hsl(var(--primary))]" strokeWidth={2.2} />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground leading-tight">Panduan Penggunaan ERP</p>
              <p className="text-[11px] text-foreground/50 leading-tight">CV. Dewi Aditya · Versi 1.0 · 2026</p>
            </div>
          </div>
          {/* Built-in close button is already provided by DialogContent (top-right) */}
        </div>

        {/* Content */}
        <UserGuideContent embedded />
      </DialogContent>
    </Dialog>
  );
}
