import { useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { API } from './utils';

export default function ScriptModal({ script, accounts, authH, onClose, onSuccess }) {
  const isEdit = !!script;
  const [form, setForm] = useState({
    title: script?.title || '',
    category: script?.category || 'opening',
    account_id: script?.account_id || '',
    script_text: script?.script_text || '',
    language: script?.language || 'indonesia',
    products_applicable: script?.products_applicable || [],
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.script_text) {
      toast.error('Title dan script text wajib diisi');
      return;
    }

    setSaving(true);
    try {
      const url = isEdit
        ? `${API}/api/marketing/livehost/scripts/${script.id}`
        : `${API}/api/marketing/livehost/scripts`;
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, account_id: form.account_id || null }),
      });

      if (res.ok) {
        toast.success(isEdit ? 'Script berhasil diupdate' : 'Script berhasil dibuat');
        onSuccess();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal menyimpan script');
      }
    } catch (e) {
      toast.error('Gagal menyimpan script');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Script' : 'Add Script'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs font-semibold">Title *</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              className="mt-1 h-9"
              placeholder="e.g., Opening Script - Fashion Live"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm((f) => ({ ...f, category: v }))}>
                <SelectTrigger className="mt-1 h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="opening">Opening</SelectItem>
                  <SelectItem value="demo">Demo/Product</SelectItem>
                  <SelectItem value="promo">Promo</SelectItem>
                  <SelectItem value="closing">Closing</SelectItem>
                  <SelectItem value="faq">FAQ</SelectItem>
                  <SelectItem value="objection_handling">Objection Handling</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold">Language</Label>
              <Select value={form.language} onValueChange={(v) => setForm((f) => ({ ...f, language: v }))}>
                <SelectTrigger className="mt-1 h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="indonesia">Indonesia</SelectItem>
                  <SelectItem value="english">English</SelectItem>
                  <SelectItem value="mandarin">Mandarin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold">Account (Optional)</Label>
            <Select
              value={form.account_id || 'global'}
              onValueChange={(v) => setForm((f) => ({ ...f, account_id: v === 'global' ? '' : v }))}
            >
              <SelectTrigger className="mt-1 h-9">
                <SelectValue placeholder="Global (All Accounts)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">Global (All Accounts)</SelectItem>
                {accounts.map((acc) => (
                  <SelectItem key={acc.id} value={acc.id}>
                    {acc.account_name} ({acc.platform})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-semibold">Script Text *</Label>
            <Textarea
              value={form.script_text}
              onChange={(e) => setForm((f) => ({ ...f, script_text: e.target.value }))}
              className="mt-1 text-sm"
              rows={6}
              placeholder="Tulis script lengkap di sini..."
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Batal
            </Button>
            <Button type="submit" disabled={saving}>
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
