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

export default function TrainingModal({ training, authH, onClose, onSuccess }) {
  const isEdit = !!training;
  const [form, setForm] = useState({
    title: training?.title || '',
    category: training?.category || 'product_knowledge',
    description: training?.description || '',
    content_type: training?.content_type || 'video',
    duration_minutes: training?.duration_minutes || 0,
    is_required: training?.is_required ?? true,
    expiry_months: training?.expiry_months || null,
    passing_score: training?.passing_score || null,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.description) {
      toast.error('Title dan description wajib diisi');
      return;
    }

    setSaving(true);
    try {
      const url = isEdit
        ? `${API}/api/marketing/livehost/training/${training.id}`
        : `${API}/api/marketing/livehost/training`;
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (res.ok) {
        toast.success(isEdit ? 'Training berhasil diupdate' : 'Training berhasil dibuat');
        onSuccess();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Gagal menyimpan training');
      }
    } catch (e) {
      toast.error('Gagal menyimpan training');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Training' : 'Add Training'}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs font-semibold">Title *</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              className="mt-1 h-9"
              placeholder="e.g., Product Knowledge 101"
            />
          </div>

          <div>
            <Label className="text-xs font-semibold">Category</Label>
            <Select value={form.category} onValueChange={(v) => setForm((f) => ({ ...f, category: v }))}>
              <SelectTrigger className="mt-1 h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="product_knowledge">Product Knowledge</SelectItem>
                <SelectItem value="platform_rules">Platform Rules</SelectItem>
                <SelectItem value="engagement">Engagement Techniques</SelectItem>
                <SelectItem value="sales_techniques">Sales Techniques</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-semibold">Description *</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="mt-1 text-sm"
              rows={3}
              placeholder="Deskripsi training..."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Content Type</Label>
              <Select value={form.content_type} onValueChange={(v) => setForm((f) => ({ ...f, content_type: v }))}>
                <SelectTrigger className="mt-1 h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="video">Video</SelectItem>
                  <SelectItem value="pdf">PDF</SelectItem>
                  <SelectItem value="quiz">Quiz</SelectItem>
                  <SelectItem value="external_link">External Link</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold">Duration (minutes)</Label>
              <Input
                type="number"
                min="0"
                value={form.duration_minutes}
                onChange={(e) => setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))}
                className="mt-1 h-9"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs font-semibold">Passing Score (%) - Optional</Label>
              <Input
                type="number"
                min="0"
                max="100"
                value={form.passing_score || ''}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    passing_score: e.target.value ? Number(e.target.value) : null,
                  }))
                }
                className="mt-1 h-9"
                placeholder="For quiz only"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold">Expiry (months) - Optional</Label>
              <Input
                type="number"
                min="0"
                value={form.expiry_months || ''}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    expiry_months: e.target.value ? Number(e.target.value) : null,
                  }))
                }
                className="mt-1 h-9"
                placeholder="Re-certification"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.is_required}
              onChange={(e) => setForm((f) => ({ ...f, is_required: e.target.checked }))}
              className="rounded"
            />
            <Label className="text-xs font-medium cursor-pointer">Required Training</Label>
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
