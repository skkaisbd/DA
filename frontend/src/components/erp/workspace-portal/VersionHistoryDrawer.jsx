/**
 * VersionHistoryDrawer — lists saved snapshots of a document, with restore.
 *
 * The most recent version is highlighted with a "Terbaru" badge and is NOT
 * restorable (it's already current). All older versions show a Restore button.
 */
import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { History, Loader2, RotateCcw } from 'lucide-react';

import { apicall, fmtIso } from './utils';

export default function VersionHistoryDrawer({ open, onClose, docId, token, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(null);

  useEffect(() => {
    if (open && docId) {
      setLoading(true);
      apicall('GET', `/api/workspace/documents/${docId}/versions`, token)
        .then(setVersions)
        .catch(() => toast.error('Gagal memuat versi'))
        .finally(() => setLoading(false));
    }
  }, [open, docId, token]);

  const handleRestore = async (v) => {
    if (!window.confirm(`Restore ke "${v.label}"? Perubahan yang belum disimpan akan hilang.`)) return;
    setRestoring(v.id);
    try {
      await apicall('POST', `/api/workspace/documents/${docId}/versions/${v.id}/restore`, token, {});
      toast.success(`Berhasil restore ke ${v.label}`);
      onRestored();
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setRestoring(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="version-history-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History size={16} />Riwayat Versi
          </DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        ) : versions.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            Belum ada versi tersimpan.<br />
            <span className="text-xs">Klik "Simpan" untuk membuat snapshot versi.</span>
          </p>
        ) : (
          <ScrollArea className="max-h-96">
            <div className="space-y-2 pr-1">
              {versions.map((v, idx) => (
                <div key={v.id}
                  className={`flex items-center justify-between p-3 rounded-lg border ${
                    idx === 0 ? 'border-primary/40 bg-primary/5' : 'hover:bg-muted/30'
                  }`}>
                  <div>
                    <p className="text-sm font-medium">{v.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {fmtIso(v.saved_at)} · {v.saved_by_name}
                    </p>
                  </div>
                  <div className="flex gap-2 items-center">
                    {idx === 0 && <Badge variant="secondary" className="text-xs">Terbaru</Badge>}
                    {idx !== 0 && (
                      <Button variant="outline" size="sm" className="h-7 text-xs"
                        disabled={restoring === v.id}
                        onClick={() => handleRestore(v)}
                        data-testid={`restore-version-${idx}`}>
                        {restoring === v.id
                          ? <Loader2 size={12} className="animate-spin mr-1" />
                          : <RotateCcw size={12} className="mr-1" />}
                        Restore
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="w-full">Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
