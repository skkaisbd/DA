/**
 * CreatePRDialog — Procurement Request creation form with line items.
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { apicall, fmtCurrency } from '../utils';

export function CreatePRDialog({ open, onClose, token, onCreated }) {
  const initialForm = {
    title: '', description: '', justification: '', priority: 'medium',
    request_type: 'asset', department: '',
    items: [{ name: '', specification: '', qty: 1, unit: 'pcs', estimated_price: '', notes: '' }],
  };
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  // Reset form whenever dialog re-opens (clear stale data)
  useEffect(() => {
    if (open) {
      setForm(initialForm);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const setItem = (idx, k, v) => setForm(p => ({
    ...p,
    items: p.items.map((it, i) => i === idx ? { ...it, [k]: v } : it),
  }));

  const addItem = () => setForm(p => ({ ...p, items: [...p.items, { name: '', specification: '', qty: 1, unit: 'pcs', estimated_price: '', notes: '' }] }));
  const removeItem = (idx) => setForm(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }));

  const totalEst = form.items.reduce((s, i) => s + (Number(i.estimated_price) || 0) * (Number(i.qty) || 1), 0);

  const isValid = form.title.trim() !== '' && form.items.every(i => i.name && i.name.trim() !== '');

  const isDirty =
    form.title.trim() !== '' ||
    form.description.trim() !== '' ||
    form.justification.trim() !== '' ||
    form.department.trim() !== '' ||
    form.items.some(i => (i.name || '').trim() !== '' || (i.specification || '').trim() !== '' || Number(i.estimated_price) > 0);

  const safeClose = () => {
    if (loading) return; // tidak boleh close saat submit
    if (isDirty) {
      if (!window.confirm('Form berisi data yang belum disimpan. Yakin ingin menutup?')) return;
    }
    onClose();
  };

  const submit = async () => {
    if (!form.title.trim()) { toast.error('Judul wajib diisi'); return; }
    if (form.items.some(i => !i.name)) { toast.error('Nama item wajib diisi'); return; }
    setLoading(true);
    try {
      const data = await apicall('POST', '/api/procurement/requests', token, {
        ...form,
        items: form.items.map(i => ({ ...i, qty: Number(i.qty) || 1, estimated_price: Number(i.estimated_price) || 0 })),
      });
      if (data.id) {
        toast.success(`PR ${data.request_number} berhasil dibuat`);
        // Close dialog FIRST so UI updates immediately, then trigger reload.
        onClose();
        // defer onCreated to next tick so dialog close animation can start
        setTimeout(() => onCreated && onCreated(data), 0);
      } else {
        toast.error(data.detail || 'Gagal membuat request');
      }
    } catch {
      toast.error('Gagal membuat request');
    } finally {
      setLoading(false);
    }
  };

  // Ctrl/Cmd + Enter to submit
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!loading && isValid) submit();
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) safeClose(); }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" onKeyDown={handleKeyDown} data-testid="create-pr-dialog">
        <DialogHeader>
          <DialogTitle>Buat Request Pengadaan</DialogTitle>
          <DialogDescription>Ajukan permintaan pengadaan baru beserta daftar item, estimasi harga, dan prioritas.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <Input placeholder="Judul request... *" value={form.title}
            onChange={e => set('title', e.target.value)} data-testid="pr-title-input" autoFocus />
          <div className="grid grid-cols-3 gap-2">
            <Select value={form.priority} onValueChange={v => set('priority', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Prioritas Rendah</SelectItem>
                <SelectItem value="medium">Prioritas Sedang</SelectItem>
                <SelectItem value="high">Prioritas Tinggi</SelectItem>
                <SelectItem value="urgent">Mendesak</SelectItem>
              </SelectContent>
            </Select>
            <Select value={form.request_type} onValueChange={v => set('request_type', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="asset">Aset</SelectItem>
                <SelectItem value="consumable">Habis Pakai</SelectItem>
                <SelectItem value="service">Jasa/Layanan</SelectItem>
                <SelectItem value="other">Lainnya</SelectItem>
              </SelectContent>
            </Select>
            <Input placeholder="Departemen" value={form.department}
              onChange={e => set('department', e.target.value)} />
          </div>
          <Input placeholder="Justifikasi kebutuhan..." value={form.justification}
            onChange={e => set('justification', e.target.value)} />

          {/* Items */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium">Daftar Item</p>
              <Button variant="outline" size="sm" onClick={addItem}><Plus size={12} className="mr-1" /> Tambah</Button>
            </div>
            <div className="space-y-2">
              {form.items.map((item, idx) => (
                <div key={idx} className="bg-muted/40 rounded-lg p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <Input placeholder={`Item ${idx + 1} *`} value={item.name}
                      onChange={e => setItem(idx, 'name', e.target.value)} className="flex-1" />
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500" onClick={() => removeItem(idx)}
                      disabled={form.items.length === 1}><X size={14} /></Button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <Input placeholder="Qty" type="number" value={item.qty}
                      onChange={e => setItem(idx, 'qty', e.target.value)} />
                    <Input placeholder="Satuan (pcs)" value={item.unit}
                      onChange={e => setItem(idx, 'unit', e.target.value)} />
                    <Input placeholder="Est. Harga (Rp)" type="number" value={item.estimated_price}
                      onChange={e => setItem(idx, 'estimated_price', e.target.value)} />
                  </div>
                  <Input placeholder="Spesifikasi / catatan" value={item.specification}
                    onChange={e => setItem(idx, 'specification', e.target.value)} />
                </div>
              ))}
            </div>
            <div className="mt-2 text-right text-sm">
              Total Estimasi: <span className="font-bold">{fmtCurrency(totalEst)}</span>
            </div>
          </div>
        </div>
        <DialogFooter className="flex items-center !justify-between gap-2">
          <span className="text-[10px] text-muted-foreground italic hidden sm:inline">
            Tip: tekan Ctrl+Enter untuk submit cepat
          </span>
          <div className="flex gap-2 ml-auto">
            <Button variant="outline" onClick={safeClose} disabled={loading} data-testid="create-pr-cancel">Batal</Button>
            <Button onClick={submit} disabled={loading || !isValid} data-testid="create-pr-submit">
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  Menyimpan...
                </span>
              ) : 'Buat Request'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
