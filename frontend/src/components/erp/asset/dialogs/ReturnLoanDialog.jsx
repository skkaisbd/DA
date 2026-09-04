/**
 * ReturnLoanDialog — Terima kembali aset yang dipinjam (ACC-3).
 *
 * Kondisi saat kembali menentukan status aset setelahnya:
 *   Baik   → aset kembali `Aktif` (siap dipinjam lagi)
 *   Rusak  → aset jadi `Pemeliharaan` + otomatis dibuatkan catatan maintenance
 *            (supaya kerusakan tidak hilang jejak)
 *   Hilang → aset jadi `Hilang` (tidak bisa dipinjam, perlu tindak lanjut)
 */
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { AlertTriangle } from 'lucide-react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { apicall } from '../utils';

const today = () => new Date().toISOString().slice(0, 10);

const CONDITION_HINT = {
  good: 'Aset akan kembali berstatus Aktif dan siap dipinjam lagi.',
  damaged: 'Aset akan berstatus Pemeliharaan dan otomatis dibuatkan catatan perbaikan.',
  lost: 'Aset akan berstatus Hilang dan tidak bisa dipinjam lagi sampai ada tindak lanjut.',
};

export function ReturnLoanDialog({ open, onClose, token, loan, onReturned }) {
  const [form, setForm] = useState({ return_date: today(), condition: 'good', return_notes: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open) {
      setForm({ return_date: today(), condition: 'good', return_notes: '' });
      setErr('');
    }
  }, [open, loan]);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!loan) return;
    if (form.condition !== 'good' && !form.return_notes.trim()) {
      setErr('Catatan wajib diisi untuk kondisi rusak/hilang (untuk jejak audit).');
      return;
    }
    setSaving(true); setErr('');
    try {
      const d = await apicall('POST', `/api/assets/loans/${loan.id}/return`, token, form);
      toast.success(`${loan.asset_number} dikembalikan (kondisi: ${form.condition})`);
      onReturned?.(d);
      onClose();
    } catch (e) {
      setErr(e.message || 'Gagal mencatat pengembalian');
    } finally { setSaving(false); }
  };

  if (!loan) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md" data-testid="asset-loan-return-dialog">
        <DialogHeader>
          <DialogTitle>Kembalikan Aset</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {loan.loan_number} · {loan.asset_number} — {loan.asset_name}
            <br />Dipinjam oleh <strong>{loan.borrower_name}</strong>
            {loan.borrower_divisi ? ` (${loan.borrower_divisi})` : ''} sejak {loan.loan_date}
          </p>
        </DialogHeader>

        {loan.is_overdue && (
          <div className="text-xs bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 text-amber-800 dark:text-amber-300 rounded-lg px-3 py-2 flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            Terlambat <strong>{loan.days_overdue} hari</strong> dari target kembali {loan.expected_return_date}.
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Tanggal Kembali *</label>
            <Input type="date" value={form.return_date} onChange={e => set('return_date', e.target.value)}
              data-testid="asset-return-date" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Kondisi Aset *</label>
            <SmartNativeSelect value={form.condition} onChange={e => set('condition', e.target.value)}
              className="w-full" searchable={false} data-testid="asset-return-condition">
              <option value="good">Baik — siap dipakai lagi</option>
              <option value="damaged">Rusak — perlu perbaikan</option>
              <option value="lost">Hilang — tidak kembali</option>
            </SmartNativeSelect>
            <p className="text-[11px] text-muted-foreground mt-1">{CONDITION_HINT[form.condition]}</p>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Catatan {form.condition !== 'good' && <span className="text-red-600">*</span>}
            </label>
            <Input value={form.return_notes} onChange={e => set('return_notes', e.target.value)}
              placeholder={form.condition === 'good' ? 'opsional' : 'jelaskan kerusakan / kronologi hilang'}
              data-testid="asset-return-notes" />
          </div>
          {err && (
            <div className="text-sm text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-500/10 rounded-lg px-3 py-2"
              data-testid="asset-return-error">{err}</div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving} data-testid="asset-return-submit">
            {saving ? 'Menyimpan...' : 'Kembalikan'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
