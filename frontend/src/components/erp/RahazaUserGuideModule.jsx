import { BookOpen } from 'lucide-react';
import UserGuideContent from './userGuide/UserGuideContent';

/**
 * Module wrapper untuk Panduan Penggunaan (Portal Manajemen).
 * Menggunakan komponen visual rich UserGuideContent yang sama dengan UserGuideDialog
 * (yang dipakai di PortalSelector).
 */
export default function RahazaUserGuideModule() {
  return (
    <div className="space-y-4" data-testid="user-guide-page">
      {/* Page header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary)/0.15)] border border-[hsl(var(--primary)/0.30)] grid place-items-center">
            <BookOpen className="w-5 h-5 text-[hsl(var(--primary))]" strokeWidth={2.2} />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-foreground">Panduan Penggunaan ERP</h2>
            <p className="text-sm text-foreground/55 mt-0.5">
              Manual lengkap dengan ikon, skenario, dan pre-requisite yang jelas
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-foreground/45 bg-[var(--glass-bg)] border border-[var(--glass-border)] px-3 py-1.5 rounded-xl">
          <BookOpen className="w-3.5 h-3.5" />
          <span>Versi 2.5 · April 2026</span>
        </div>
      </div>

      {/* Rich-visual content */}
      <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-bg)] overflow-hidden">
        <UserGuideContent />
      </div>
    </div>
  );
}
