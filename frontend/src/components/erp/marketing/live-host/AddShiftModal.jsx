import { useState, useEffect } from 'react';
import { Clock, Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { getPlatformConfig } from '../AccountBadge';
import { API } from './utils';

export default function AddShiftModal({ hosts, accounts, authH, onClose, onSuccess }) {
  const [form, setForm] = useState({
    host_id: '',
    account_id: '',
    date: new Date().toISOString().split('T')[0],
    shift_type: 'morning',
    shift_start_time: '09:00',
    shift_end_time: '13:00',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  const selectedHost = hosts.find((h) => h.id === form.host_id);
  const hostAssignedIds = (selectedHost?.assigned_accounts || []).map((a) => a.id);
  const availableAccounts =
    hostAssignedIds.length > 0 ? accounts.filter((a) => hostAssignedIds.includes(a.id)) : accounts;

  useEffect(() => {
    if (
      form.account_id &&
      availableAccounts.length > 0 &&
      !availableAccounts.find((a) => a.id === form.account_id)
    ) {
      setForm((f) => ({ ...f, account_id: '' }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.host_id]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.host_id || !form.account_id || !form.date) {
      toast.error('LiveHost, account, dan tanggal wajib diisi');
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/shifts`, {
        method: 'POST',
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (res.ok) {
        toast.success('Shift berhasil dibuat');
        onSuccess();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal membuat shift');
      }
    } catch (e) {
      toast.error('Gagal membuat shift');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock size={18} className="text-primary" />
            Tambah Shift Baru
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs font-semibold">LiveHost *</Label>
            <Select value={form.host_id} onValueChange={(v) => setForm((f) => ({ ...f, host_id: v }))}>
              <SelectTrigger className="mt-1 h-9" data-testid="select-host">
                <SelectValue placeholder="Pilih LiveHost" />
              </SelectTrigger>
              <SelectContent>
                {hosts.map((h) => (
                  <SelectItem key={h.id} value={h.id}>
                    {h.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-semibold">Platform Account *</Label>
            <Select value={form.account_id} onValueChange={(v) => setForm((f) => ({ ...f, account_id: v }))}>
              <SelectTrigger className="mt-1 h-9" data-testid="select-account">
                <SelectValue placeholder="Pilih Account" />
              </SelectTrigger>
              <SelectContent>
                {availableAccounts.map((a) => {
                  const cfg = getPlatformConfig(a.platform);
                  return (
                    <SelectItem key={a.id} value={a.id}>
                      {cfg.icon} {a.account_name} ({cfg.label})
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
            {form.host_id && hostAssignedIds.length === 0 && (
              <p className="text-[10px] text-amber-500 mt-1">
                Host belum di-assign ke akun manapun. Edit host untuk menambah assignment.
              </p>
            )}
            {form.account_id &&
              availableAccounts.find((a) => a.id === form.account_id) &&
              (() => {
                const acc = availableAccounts.find((a) => a.id === form.account_id);
                const cfg = getPlatformConfig(acc.platform);
                return (
                  <div
                    className={`mt-1.5 flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-medium ${cfg.bg} ${cfg.border} ${cfg.text}`}
                  >
                    {cfg.icon} Shift untuk: {acc.account_name}
                  </div>
                );
              })()}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Tanggal *</Label>
              <Input
                type="date"
                value={form.date}
                onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                className="mt-1 h-9"
                data-testid="input-date"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Shift Type</Label>
              <Select value={form.shift_type} onValueChange={(v) => setForm((f) => ({ ...f, shift_type: v }))}>
                <SelectTrigger className="mt-1 h-9" data-testid="select-shift-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="morning">Morning</SelectItem>
                  <SelectItem value="afternoon">Afternoon</SelectItem>
                  <SelectItem value="evening">Evening</SelectItem>
                  <SelectItem value="night">Night</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Start Time</Label>
              <Input
                type="time"
                value={form.shift_start_time}
                onChange={(e) => setForm((f) => ({ ...f, shift_start_time: e.target.value }))}
                className="mt-1 h-9"
                data-testid="input-start-time"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">End Time</Label>
              <Input
                type="time"
                value={form.shift_end_time}
                onChange={(e) => setForm((f) => ({ ...f, shift_end_time: e.target.value }))}
                className="mt-1 h-9"
                data-testid="input-end-time"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="mt-1 text-sm"
              rows={2}
              placeholder="Catatan shift..."
              data-testid="input-shift-notes"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="submit-shift">
              {saving ? (
                <>
                  <Loader2 size={14} className="mr-1.5 animate-spin" />
                  Menyimpan...
                </>
              ) : (
                <>
                  <Save size={14} className="mr-1.5" />
                  Simpan
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
