/**
 * MaklonBuyerCatalogPicker — Phase M1
 * Dialog picker untuk memilih artikel dari Buyer Catalog saat membuat Maklon PO.
 *
 * Props:
 *  - open: boolean
 *  - clientId: string (REQUIRED) — fetch hanya artikel buyer ini
 *  - headers: { Authorization, Content-Type }
 *  - onClose: () => void
 *  - onPick: (catalogItem) => void  // dipanggil ketika user pilih item
 */
import { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, BookOpen, Tag, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const fmtRp = formatRupiah;

export default function MaklonBuyerCatalogPicker({ open, clientId, headers, onClose, onPick }) {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchItems = useCallback(async () => {
    if (!open) return;
    if (!clientId) {
      setItems([]);
      return;
    }
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      qs.append('client_id', clientId);
      qs.append('status', 'active');
      if (search.trim()) qs.append('search', search.trim());
      const r = await fetch(`/api/dewi/maklon/buyer-catalog?${qs.toString()}`, { headers });
      if (r.ok) setItems(await r.json());
      else toast.error('Gagal memuat Buyer Catalog');
    } catch (_e) {
      toast.error('Gagal memuat Buyer Catalog');
    } finally {
      setLoading(false);
    }
  }, [open, clientId, headers, search]);

  useEffect(() => {
    if (open) fetchItems();
  }, [fetchItems, open]);

  const pick = (it) => {
    onPick?.(it);
    onClose?.();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
        data-testid="buyer-catalog-picker-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-violet-400" />
            Pilih dari Buyer Catalog
          </DialogTitle>
        </DialogHeader>

        {!clientId ? (
          <div className="text-center py-10 text-foreground/40 text-sm">
            Pilih buyer (klien) terlebih dahulu di form PO sebelum memilih artikel.
          </div>
        ) : (
          <>
            <div className="relative my-3">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground/40" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Cari artikel / ref / nama..."
                className="pl-8 h-9"
                data-testid="buyer-catalog-picker-search"
                autoFocus
              />
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {loading ? (
                <div className="text-center py-8 text-foreground/40 text-sm">Memuat...</div>
              ) : items.length === 0 ? (
                <div className="text-center py-8 text-foreground/40 text-sm">
                  Tidak ada artikel untuk buyer ini.
                  <br />
                  <span className="text-xs">Tambahkan di menu Buyer Catalog terlebih dahulu.</span>
                </div>
              ) : (
                items.map((it) => (
                  <button
                    key={it.id}
                    type="button"
                    onClick={() => pick(it)}
                    className="w-full text-left p-3 rounded-lg border border-border/60 bg-foreground/[0.03] hover:bg-violet-500/10 hover:border-violet-400/30 transition-all group"
                    data-testid={`buyer-catalog-picker-item-${it.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          <span className="font-semibold text-sm text-foreground">{it.product_name}</span>
                          <span className="text-[10px] bg-violet-500/15 text-violet-600 dark:text-violet-300 px-1.5 py-0.5 rounded font-mono border border-violet-400/25">
                            {it.artikel_code}
                          </span>
                          {it.buyer_ref_code && (
                            <span className="text-[10px] bg-foreground/5 text-foreground/65 px-1.5 py-0.5 rounded font-mono">
                              ↳ {it.buyer_ref_code}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-foreground/55 flex items-center gap-2 flex-wrap">
                          <span><Tag className="w-3 h-3 inline mr-0.5" /> {it.category || 'Uncategorized'}</span>
                          <span className="text-foreground/30">•</span>
                          <span>
                            CMT: <strong className="text-amber-600 dark:text-amber-400">{fmtRp(it.default_cmt_price)}</strong>
                          </span>
                          {(it.color_options?.length > 0 || it.size_options?.length > 0) && (
                            <>
                              <span className="text-foreground/30">•</span>
                              <span className="text-foreground/55">
                                {(it.color_options || []).length} warna · {(it.size_options || []).length} size
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                      <CheckCircle2 className="w-4 h-4 text-violet-500 dark:text-violet-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="flex justify-end mt-3">
              <Button variant="outline" onClick={onClose} size="sm" data-testid="buyer-catalog-picker-close">
                Tutup
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
