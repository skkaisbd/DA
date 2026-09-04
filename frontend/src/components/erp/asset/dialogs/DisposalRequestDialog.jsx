/**
 * DisposalRequestDialog — Request disposal for high-value assets (requires approval).
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apicall, fmtCurrency } from '../utils';

export function DisposalRequestDialog({ open, onClose, token, asset, onRequested }) {
  const [form, setForm] = useState({
    disposal_date: new Date().toISOString().slice(0, 10),
    disposal_value: '',
    reason: '',
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  const nbv = asset ? (parseFloat(asset.purchase_cost || 0) - parseFloat(asset.accumulated_depreciation || 0)) : 0;

  const submit = async () => {
    if (!form.reason.trim()) { toast.error('Alasan disposal wajib diisi'); return; }
    setLoading(true);
    try {
      const data = await apicall('POST', `/api/assets/${asset.id}/request-disposal`, token, form);
      if (data?.id) {
        toast.success('Permintaan disposal dikirim untuk approval');
        onRequested?.();
        onClose();
      } else {
        toast.error(data?.detail || 'Gagal kirim permintaan');
      }
    } catch { toast.error('Gagal kirim permintaan'); }
    finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-amber-500">⚠️</span> Request Disposal Aset
          </DialogTitle>
        </DialogHeader>
        {asset && (
          <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20 rounded-lg p-3 text-sm space-y-1">
            <p className="font-medium">{asset.name}</p>
            <p className="text-muted-foreground text-xs">{asset.asset_number} · NBV: <strong className="text-amber-700">{fmtCurrency(nbv)}</strong></p>
            <p className="text-xs text-amber-700">⚠️ Aset bernilai tinggi — memerlukan approval Finance/Admin sebelum dilepas.</p>
          </div>
        )}
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Tanggal Pelepasan</label>
            <Input type="date" value={form.disposal_date} onChange={e => set('disposal_date', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Nilai Penjualan (Rp, isi 0 jika dibuang)</label>
            <Input type="number" placeholder="0" value={form.disposal_value} onChange={e => set('disposal_value', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Alasan Disposal *</label>
            <textarea
              className="w-full border rounded-md px-3 py-2 text-sm mt-1 min-h-[80px] bg-background resize-none"
              placeholder="Rusak total, tidak ekonomis diperbaiki..."
              value={form.reason}
              onChange={e => set('reason', e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={loading} className="bg-amber-600 hover:bg-amber-700 text-foreground">
            {loading ? 'Mengirim...' : 'Kirim Request'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
