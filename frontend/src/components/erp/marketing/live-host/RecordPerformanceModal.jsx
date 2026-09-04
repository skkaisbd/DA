import { useState } from 'react';
import { BarChart3, Plus, X, Save, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { API } from './utils';

export default function RecordPerformanceModal({ shift, authH, onClose, onSuccess }) {
  const [form, setForm] = useState({
    shift_id: shift.id,
    platform: shift.platform || 'shopee',
    viewers: 0,
    peak_viewers: 0,
    revenue: 0,
    orders: 0,
    items_promoted: [],
    script_adherence_score: null,
    challenges_faced: '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [itemInput, setItemInput] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    setSaving(true);
    try {
      const res = await fetch(`${API}/api/marketing/livehost/shifts/${shift.id}/performance`, {
        method: 'POST',
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (res.ok) {
        toast.success('Performance berhasil dicatat');
        onSuccess();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal mencatat performance');
      }
    } catch (e) {
      toast.error('Gagal mencatat performance');
    } finally {
      setSaving(false);
    }
  };

  const addItem = () => {
    if (itemInput.trim()) {
      setForm((f) => ({ ...f, items_promoted: [...f.items_promoted, itemInput.trim()] }));
      setItemInput('');
    }
  };

  const removeItem = (index) => {
    setForm((f) => ({ ...f, items_promoted: f.items_promoted.filter((_, i) => i !== index) }));
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BarChart3 size={18} className="text-primary" />
            Record Shift Performance
          </DialogTitle>
          <p className="text-sm text-muted-foreground">
            {shift.host_name} - {shift.date} ({shift.shift_start_time}-{shift.shift_end_time})
          </p>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs font-semibold">Platform</Label>
            <Select value={form.platform} onValueChange={(v) => setForm((f) => ({ ...f, platform: v }))}>
              <SelectTrigger className="mt-1 h-9" data-testid="select-platform">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="shopee">Shopee</SelectItem>
                <SelectItem value="tiktokshop">TikTokShop</SelectItem>
                <SelectItem value="tokopedia">Tokopedia</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Viewers</Label>
              <Input
                type="number"
                min="0"
                value={form.viewers}
                onChange={(e) => setForm((f) => ({ ...f, viewers: Number(e.target.value) }))}
                className="mt-1 h-9"
                data-testid="input-viewers"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Peak Viewers</Label>
              <Input
                type="number"
                min="0"
                value={form.peak_viewers}
                onChange={(e) => setForm((f) => ({ ...f, peak_viewers: Number(e.target.value) }))}
                className="mt-1 h-9"
                data-testid="input-peak-viewers"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Revenue (Rp)</Label>
              <Input
                type="number"
                min="0"
                step="1000"
                value={form.revenue}
                onChange={(e) => setForm((f) => ({ ...f, revenue: Number(e.target.value) }))}
                className="mt-1 h-9"
                data-testid="input-revenue"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Orders</Label>
              <Input
                type="number"
                min="0"
                value={form.orders}
                onChange={(e) => setForm((f) => ({ ...f, orders: Number(e.target.value) }))}
                className="mt-1 h-9"
                data-testid="input-orders"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs font-semibold">Items Promoted</Label>
            <div className="mt-1 flex gap-2">
              <Input
                value={itemInput}
                onChange={(e) => setItemInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addItem())}
                placeholder="Nama produk"
                className="h-9"
                data-testid="input-item"
              />
              <Button type="button" size="sm" onClick={addItem} className="h-9">
                <Plus size={14} />
              </Button>
            </div>
            {form.items_promoted.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {form.items_promoted.map((item, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">
                    {item}
                    <button
                      type="button"
                      onClick={() => removeItem(i)}
                      className="ml-1 hover:text-red-600"
                    >
                      <X size={10} />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div>
            <Label className="text-xs font-semibold">Script Adherence Score (0-100)</Label>
            <Input
              type="number"
              min="0"
              max="100"
              value={form.script_adherence_score || ''}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  script_adherence_score: e.target.value ? Number(e.target.value) : null,
                }))
              }
              className="mt-1 h-9"
              placeholder="Optional"
              data-testid="input-script-score"
            />
          </div>

          <div>
            <Label className="text-xs font-semibold">Challenges Faced</Label>
            <Textarea
              value={form.challenges_faced}
              onChange={(e) => setForm((f) => ({ ...f, challenges_faced: e.target.value }))}
              className="mt-1 text-sm"
              rows={2}
              placeholder="Kendala yang dihadapi saat live..."
              data-testid="input-challenges"
            />
          </div>

          <div>
            <Label className="text-xs font-semibold">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="mt-1 text-sm"
              rows={2}
              placeholder="Catatan tambahan..."
              data-testid="input-performance-notes"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Batal
            </Button>
            <Button type="submit" disabled={saving} data-testid="submit-performance">
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
