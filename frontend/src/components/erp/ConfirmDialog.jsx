import { AlertTriangle } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';

export default function ConfirmDialog({ title, message, onConfirm, onCancel, type = 'danger' }) {
  const styles = {
    danger: {
      icon: 'bg-red-50 dark:bg-red-400/15 text-red-700 dark:text-red-400',
      btn: 'bg-destructive hover:brightness-110 text-destructive-foreground',
      label: 'Hapus'
    },
    warning: {
      icon: 'bg-amber-50 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400',
      btn: 'bg-amber-500 hover:brightness-110 text-foreground',
      label: 'Lanjutkan'
    }
  };
  const s = styles[type] || styles.danger;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm" onClick={onCancel} />
      <GlassCard hover={false} className="relative w-full max-w-sm p-6">
        <div className={`w-12 h-12 rounded-full ${s.icon} flex items-center justify-center mx-auto mb-4`}>
          <AlertTriangle className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-foreground text-center">{title}</h3>
        <p className="text-sm text-muted-foreground text-center mt-2 leading-relaxed">{message}</p>
        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel}
            className="flex-1 border border-[var(--glass-border)] py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-[var(--glass-bg-hover)] transition-colors"
          >
            Batal
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-all ${s.btn}`}
          >
            {s.label}
          </button>
        </div>
      </GlassCard>
    </div>
  );
}
