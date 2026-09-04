import { useState } from 'react';
import { User, Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { API } from './utils';

export default function AddEditHostModal({ host, accounts, authH, onClose, onSuccess }) {
  const isEdit = !!host;
  const [form, setForm] = useState({
    name: host?.name || '',
    email: host?.email || '',
    password: '',
    phone: host?.phone || '',
    employment_type: host?.employment_type || 'part_time',
    hourly_rate: host?.hourly_rate || 0,
    shift_preferences: host?.shift_preferences || [],
    language_skills: host?.language_skills || [],
    product_expertise: host?.product_expertise || [],
    assigned_account_ids: host?.assigned_account_ids || [],
    status: host?.status || 'active',
    notes: host?.notes || '',
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email) {
      toast.error('Nama dan email wajib diisi');
      return;
    }
    if (!isEdit && !form.password) {
      toast.error('Password wajib diisi untuk LiveHost baru');
      return;
    }

    setSaving(true);
    try {
      const payload = { ...form };
      if (isEdit && !form.password) {
        delete payload.password;
      }

      const url = isEdit ? `${API}/api/marketing/livehost/${host.id}` : `${API}/api/marketing/livehost`;
      const method = isEdit ? 'PATCH' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        toast.success(isEdit ? 'LiveHost berhasil diupdate' : 'LiveHost berhasil ditambahkan');
        onSuccess();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal menyimpan LiveHost');
      }
    } catch (e) {
      toast.error('Gagal menyimpan LiveHost');
    } finally {
      setSaving(false);
    }
  };

  const toggleArrayItem = (field, value) => {
    const current = form[field] || [];
    if (current.includes(value)) {
      setForm((f) => ({ ...f, [field]: current.filter((v) => v !== value) }));
    } else {
      setForm((f) => ({ ...f, [field]: [...current, value] }));
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User size={18} className="text-primary" />
            {isEdit ? 'Edit LiveHost' : 'Tambah LiveHost Baru'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Nama *</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                className="mt-1 h-9"
                placeholder="Nama LiveHost"
                data-testid="input-name"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Email *</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                className="mt-1 h-9"
                placeholder="email@example.com"
                data-testid="input-email"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Password {!isEdit && '*'}</Label>
              <Input
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                className="mt-1 h-9"
                placeholder={isEdit ? 'Kosongkan jika tidak diubah' : 'Password login'}
                data-testid="input-password"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Phone</Label>
              <Input
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                className="mt-1 h-9"
                placeholder="08xxx"
                data-testid="input-phone"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Employment Type</Label>
              <Select value={form.employment_type} onValueChange={(v) => setForm((f) => ({ ...f, employment_type: v }))}>
                <SelectTrigger className="mt-1 h-9" data-testid="select-employment">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full_time">Full Time</SelectItem>
                  <SelectItem value="part_time">Part Time</SelectItem>
                  <SelectItem value="freelance">Freelance</SelectItem>
                  <SelectItem value="contract">Contract</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold">Hourly Rate (Rp)</Label>
              <Input
                type="number"
                min="0"
                step="1000"
                value={form.hourly_rate}
                onChange={(e) => setForm((f) => ({ ...f, hourly_rate: Number(e.target.value) }))}
                className="mt-1 h-9"
                data-testid="input-hourly-rate"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold mb-2 block">Shift Preferences</Label>
            <div className="flex flex-wrap gap-2">
              {['morning', 'afternoon', 'evening', 'night'].map((shift) => (
                <button
                  key={shift}
                  type="button"
                  onClick={() => toggleArrayItem('shift_preferences', shift)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    (form.shift_preferences || []).includes(shift)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                  }`}
                  data-testid={`shift-${shift}`}
                >
                  {shift.charAt(0).toUpperCase() + shift.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold mb-2 block">Language Skills</Label>
            <div className="flex flex-wrap gap-2">
              {['indonesia', 'english', 'mandarin'].map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => toggleArrayItem('language_skills', lang)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    (form.language_skills || []).includes(lang)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                  }`}
                  data-testid={`lang-${lang}`}
                >
                  {lang.charAt(0).toUpperCase() + lang.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold mb-2 block">Product Expertise</Label>
            <div className="flex flex-wrap gap-2">
              {['fashion', 'electronics', 'food', 'beauty', 'health', 'home'].map((prod) => (
                <button
                  key={prod}
                  type="button"
                  onClick={() => toggleArrayItem('product_expertise', prod)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    (form.product_expertise || []).includes(prod)
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                  }`}
                  data-testid={`product-${prod}`}
                >
                  {prod.charAt(0).toUpperCase() + prod.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold mb-2 block">Assigned Platform Accounts</Label>
            <div className="max-h-32 overflow-y-auto border rounded-lg p-2 space-y-1">
              {accounts.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-2">Belum ada platform account</p>
              ) : (
                accounts.map((acc) => (
                  <label key={acc.id} className="flex items-center gap-2 p-2 rounded hover:bg-muted/50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={(form.assigned_account_ids || []).includes(acc.id)}
                      onChange={() => toggleArrayItem('assigned_account_ids', acc.id)}
                      className="rounded"
                      data-testid={`account-${acc.id}`}
                    />
                    <span className="text-xs flex-1">{acc.account_name}</span>
                    <Badge variant="outline" className="text-xs">
                      {acc.platform}
                    </Badge>
                  </label>
                ))
              )}
            </div>
          </div>

          {isEdit && (
            <div>
              <Label className="text-xs font-semibold">Status</Label>
              <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
                <SelectTrigger className="mt-1 h-9" data-testid="select-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="on_leave">On Leave</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div>
            <Label className="text-xs font-semibold">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="mt-1 text-sm"
              rows={3}
              placeholder="Catatan tambahan..."
              data-testid="input-notes"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="submit-host">
              {saving ? (
                <>
                  <Loader2 size={14} className="mr-1.5 animate-spin" />
                  Menyimpan...
                </>
              ) : (
                <>
                  <Save size={14} className="mr-1.5" />
                  {isEdit ? 'Update' : 'Simpan'}
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
