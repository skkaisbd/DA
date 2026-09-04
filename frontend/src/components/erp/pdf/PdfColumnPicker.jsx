/**
 * PdfColumnPicker — "kolom mana yang dicetak?" (W2, sesi #29)
 * ═══════════════════════════════════════════════════════════════════════════
 * KELUHAN PEMILIK yang melahirkan komponen ini (verbatim): *"PDF masih belum
 * lengkap … untuk produksi ada data no serial namun di pdf tidak ada pilihannya,
 * jadi saya ingin semua data collection bisa di export juga dan bisa di pilih
 * user"*.
 *
 * Faktanya: daftar kolom (termasuk **Serial No**) SUDAH ada di SSOT backend
 * `data/pdf_doc_registry`, tetapi satu-satunya cara memilihnya adalah lewat layar
 * SETELAN (template PDF / konfigurasi bernama). Orang yang sedang mencetak satu
 * dokumen tidak punya pintu apa pun — jadi kolom itu praktis tidak pernah dipakai.
 *
 * Komponen ini menyediakan pintunya TEPAT DI TEMPAT CETAK:
 *   · daftar kolom dibaca dari `GET /api/pdf-export-columns?type=<docType>`
 *     (SSOT yang sama dengan yang dipakai PDF-nya — mustahil beda pendapat);
 *   · kolom WAJIB ditandai & tidak bisa dilepas (tanpa nomor baris dokumen tak terbaca);
 *   · pilihan DIINGAT per jenis dokumen (localStorage) supaya tidak perlu
 *     mencentang ulang setiap kali mencetak;
 *   · hasilnya dikirim ke backend sebagai `?cols=a,b,c` — berlaku SEKALI CETAK,
 *     tidak mengubah setelan global milik orang lain.
 */
import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2, RotateCcw } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';

const API = process.env.REACT_APP_BACKEND_URL || '';
const lsKey = (docType) => `pdfcols:${docType}`;

export function usePdfColumnChoice(docType) {
  const read = useCallback(() => {
    try {
      const raw = localStorage.getItem(lsKey(docType));
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }, [docType]);
  return read;
}

export function PdfColumnPicker({
  docType, token, open, onOpenChange, onConfirm,
  title = 'Pilih Kolom yang Dicetak',
  confirmLabel = 'Cetak PDF',
  hint,
  defaultKeys,
}) {
  const [cols, setCols] = useState([]);
  const [checked, setChecked] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const defKey = Array.isArray(defaultKeys) ? defaultKeys.join(',') : '';

  useEffect(() => {
    if (!open || !docType) return;
    let alive = true;
    (async () => {
      setLoading(true); setErr('');
      try {
        const r = await fetch(`${API}/api/pdf-export-columns?type=${encodeURIComponent(docType)}`, {
          headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
        });
        const d = await r.json().catch(() => ({}));
        if (!alive) return;
        const list = Array.isArray(d.columns) ? d.columns : [];
        setCols(list);
        // Pilihan tersimpan → dipakai; kalau belum ada, default = SEMUA kolom
        // (perilaku lama), supaya tidak ada dokumen yang mendadak kehilangan kolom.
        let saved = null;
        try {
          const raw = localStorage.getItem(lsKey(docType));
          saved = raw ? JSON.parse(raw) : null;
        } catch { saved = null; }
        const keys = list.map(c => c.key);
        const req = list.filter(c => c.required).map(c => c.key);
        // Tanpa pilihan tersimpan: pakai `defaultKeys` bila layar pemanggil
        // menentukannya (mis. Surat Jalan CMT default = versi kirim murni),
        // kalau tidak SEMUA kolom (perilaku lama) supaya tidak ada dokumen yang
        // mendadak kehilangan kolom.
        const def = defKey ? defKey.split(',') : [];
        const fallback = def.length
          ? keys.filter(k => def.includes(k) || req.includes(k))
          : keys;
        const initial = Array.isArray(saved) && saved.length
          ? keys.filter(k => saved.includes(k) || req.includes(k))
          : fallback;
        setChecked(new Set(initial));
        if (!list.length) setErr('Jenis dokumen ini belum punya daftar kolom di katalog PDF.');
      } catch (e) {
        if (alive) setErr(e.message || 'Gagal memuat daftar kolom');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [open, docType, token, defKey]);

  const toggle = (key, required) => {
    if (required) return;
    setChecked(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const selectAll = () => setChecked(new Set(cols.map(c => c.key)));
  const clearAll = () => setChecked(new Set(cols.filter(c => c.required).map(c => c.key)));

  const confirm = () => {
    const picked = cols.filter(c => checked.has(c.key) || c.required).map(c => c.key);
    try { localStorage.setItem(lsKey(docType), JSON.stringify(picked)); } catch { /* penyimpanan diblokir */ }
    onOpenChange?.(false);
    onConfirm?.(picked);
  };

  const total = cols.length;
  const picked = cols.filter(c => checked.has(c.key) || c.required).length;

  return (
    <Dialog open={!!open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="pdf-column-picker">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText size={18} /> {title}
          </DialogTitle>
          <DialogDescription>
            {hint || 'Centang kolom yang ingin tercetak. Pilihan ini diingat untuk cetakan berikutnya dan tidak mengubah setelan global.'}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="animate-spin mx-auto mb-2" size={18} /> Memuat daftar kolom…
          </div>
        ) : err ? (
          <div className="py-6 text-sm text-amber-700 dark:text-amber-300" data-testid="pdf-picker-error">{err}</div>
        ) : (
          <>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary" data-testid="pdf-picker-count">{picked}/{total} kolom</Badge>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={selectAll} data-testid="pdf-picker-all">
                Pilih semua
              </Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={clearAll} data-testid="pdf-picker-clear">
                <RotateCcw size={12} className="mr-1" /> Hanya yang wajib
              </Button>
            </div>
            <div className="max-h-[46vh] overflow-y-auto grid grid-cols-1 sm:grid-cols-2 gap-1.5 py-1">
              {cols.map(c => {
                const on = checked.has(c.key) || c.required;
                return (
                  <label
                    key={c.key}
                    className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-sm cursor-pointer transition-colors
                      ${on ? 'border-primary/40 bg-primary/5' : 'border-border hover:bg-foreground/5'}
                      ${c.required ? 'opacity-80 cursor-not-allowed' : ''}`}
                    data-testid={`pdf-col-${c.key}`}
                  >
                    <Checkbox
                      checked={on}
                      disabled={!!c.required}
                      onCheckedChange={() => toggle(c.key, c.required)}
                    />
                    <span className="flex-1">{c.label}</span>
                    {c.required && <span className="text-[10px] text-muted-foreground">wajib</span>}
                  </label>
                );
              })}
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange?.(false)} data-testid="pdf-picker-cancel">
            Batal
          </Button>
          <Button onClick={confirm} disabled={loading || !!err} data-testid="pdf-picker-confirm">
            <FileText size={14} className="mr-1" /> {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PdfColumnPicker;
