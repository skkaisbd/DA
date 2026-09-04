/**
 * TransferAssetDialog — Transfer asset to new location/department/employee.
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apicall } from '../utils';

export function TransferAssetDialog({ open, onClose, token, asset, onTransferred }) {
  const [form, setForm] = useState({
    to_location: '', to_department: '', to_employee_id: '', to_employee_name: '', reason: '', notes: '',
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (asset) {
      setForm({
        to_location: asset.location || '',
        to_department: asset.department || '',
        to_employee_id: asset.assigned_to_id || '',
        to_employee_name: asset.assigned_to_name || '',
        reason: '', notes: '',
      });
    }
  }, [asset]);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.to_location.trim() && !form.to_department.trim() && !form.to_employee_id.trim()) {
      toast.error('Minimal 1 field harus diisi (lokasi/departemen/employee)');
      return;
    }
    setLoading(true);
    try {
      const data = await apicall('POST', `/api/assets/${asset.id}/transfer`, token, form);
      if (data.ok) {
        toast.success('Asset berhasil ditransfer');
        onTransferred();
        onClose();
      } else {
        toast.error(data.detail || 'Gagal transfer asset');
      }
    } catch { toast.error('Gagal transfer asset'); }
    finally { setLoading(false); }
  };

  if (!asset) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Transfer Asset</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {asset.asset_number} - {asset.name}
          </p>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="bg-muted/40 rounded-lg p-3 space-y-2 text-sm">
            <p className="text-xs font-semibold text-muted-foreground uppercase">Lokasi Saat Ini</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><span className="text-muted-foreground">Lokasi:</span> {asset.location || '-'}</div>
              <div><span className="text-muted-foreground">Dept:</span> {asset.department || '-'}</div>
              <div><span className="text-muted-foreground">Assigned:</span> {asset.assigned_to_name || '-'}</div>
            </div>
          </div>
          <Separator />
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Transfer Ke</p>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Lokasi Baru</label>
            <Input placeholder="Rak A-12, Gudang Utama..." value={form.to_location}
              onChange={e => set('to_location', e.target.value)} className="mt-1" data-testid="transfer-location-input" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Departemen Baru</label>
            <Input placeholder="Produksi, IT, Finance..." value={form.to_department}
              onChange={e => set('to_department', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Assign ke Employee (ID)</label>
            <Input placeholder="Employee ID" value={form.to_employee_id}
              onChange={e => set('to_employee_id', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Nama Employee</label>
            <Input placeholder="Nama lengkap" value={form.to_employee_name}
              onChange={e => set('to_employee_name', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Alasan Transfer *</label>
            <Input placeholder="Relokasi departemen, penugasan baru..." value={form.reason}
              onChange={e => set('reason', e.target.value)} className="mt-1" data-testid="transfer-reason-input" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Catatan (opsional)</label>
            <Input placeholder="Catatan tambahan..." value={form.notes}
              onChange={e => set('notes', e.target.value)} className="mt-1" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={loading} data-testid="submit-transfer-btn">
            {loading ? 'Mentransfer...' : 'Transfer Asset'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
