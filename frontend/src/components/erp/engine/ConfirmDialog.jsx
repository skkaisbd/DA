
import { AlertTriangle } from 'lucide-react';

export default function ConfirmDialog({ title, message, onConfirm, onCancel, type = 'danger' }) {
  const styles = {
    danger: {
      icon: 'bg-red-100 text-red-600',
      btn: 'bg-red-600 hover:bg-red-700 text-white',
      label: 'Hapus'
    },
    warning: {
      icon: 'bg-amber-100 text-amber-600',
      btn: 'bg-amber-600 hover:bg-amber-700 text-white',
      label: 'Lanjutkan'
    }
  };
  const s = styles[type] || styles.danger;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} />
      <div className="relative w-full max-w-sm bg-card rounded-2xl shadow-2xl p-6">
        <div className={`w-12 h-12 rounded-full ${s.icon} flex items-center justify-center mx-auto mb-4`}>
          <AlertTriangle className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-foreground text-center">{title}</h3>
        <p className="text-sm text-muted-foreground text-center mt-2 leading-relaxed">{message}</p>
        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel}
            className="flex-1 border border-border py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted/60 transition-colors"
          >
            Batal
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors ${s.btn}`}
          >
            {s.label}
          </button>
        </div>
      </div>
    </div>
  );
}
