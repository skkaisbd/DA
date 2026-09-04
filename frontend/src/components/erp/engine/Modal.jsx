
import { X } from 'lucide-react';

export default function Modal({ title, children, onClose, size = 'md' }) {
  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    // FASE E: dibutuhkan form yang punya TABEL banyak kolom (mis. dispatch ke
    // buyer: Order · Lolos QC · Hasil Permak · Sudah Dikirim · Sisa · Qty Kirim).
    // Di `xl` kolomnya terpaksa membungkus sampai 3 baris per sel sehingga
    // angkanya justru sulit dibandingkan — padahal membandingkan angka itulah
    // gunanya tabel ini.
    '2xl': 'max-w-6xl',
    '3xl': 'max-w-[88rem]',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={`relative w-full ${sizes[size]} bg-card rounded-xl shadow-2xl max-h-[90vh] flex flex-col`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/60">
          <h2 className="font-semibold text-foreground text-lg">{title}</h2>
          <button onClick={onClose} className="text-muted-foreground/70 hover:text-muted-foreground transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-6 py-4">
          {children}
        </div>
      </div>
    </div>
  );
}
