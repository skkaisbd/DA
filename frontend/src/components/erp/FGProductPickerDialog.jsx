/**
 * FGProductPickerDialog — Reusable modal untuk memilih produk dari Master FG
 * (rahaza_materials, type='fg').
 * 
 * Digunakan di:
 *   - CatalogManagementModule (saat tambah item ke katalog)
 *   - LiveSessionModule (saat pick produk untuk live session)
 *   - DiscountCampaignModule (multi-select untuk produk yang didiskon)
 *   - SampleDeliveryModule (saat pilih item untuk sample)
 * 
 * Props:
 *   - open, onOpenChange: dialog state
 *   - onSelect(fg): callback when FG dipilih (single mode)
 *   - onSelectMultiple(fgs[]): callback when multi-select confirmed
 *   - multiple: boolean (default false)
 *   - token: auth token
 *   - excludeIds: array of FG ids untuk di-exclude (e.g. yang sudah ada di catalog)
 *   - title, description: custom modal text
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Search, Package, Loader2, AlertCircle, CheckCircle2, X } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const stockBadgeVariant = (qty) => {
  if (qty <= 0) return { variant: 'destructive', label: 'Habis' };
  if (qty <= 10) return { variant: 'outline', label: `Low (${qty})` };
  return { variant: 'default', label: `Stok: ${qty}` };
};

export function FGProductPickerDialog({
  open,
  onOpenChange,
  onSelect,
  onSelectMultiple,
  multiple = false,
  token,
  excludeIds = [],
  title = 'Pilih Produk dari Master FG',
  description = 'Pilih produk Finished Goods (FG) yang sudah ada di Inventory untuk ditambahkan ke katalog.',
}) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }),
    [token]
  );

  // Debounce search query (300ms)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  // Fetch FG products
  const fetchFG = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit: 50 };
      if (debouncedQuery) params.q = debouncedQuery;
      const res = await axios.get(`${API}/api/marketing/catalogs/fg-products`, {
        headers: authH,
        params,
      });
      const list = res.data?.data || [];
      // Filter out excluded ids
      const filtered = excludeIds.length > 0
        ? list.filter(f => !excludeIds.includes(f.id))
        : list;
      setItems(filtered);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setItems([]);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authH, debouncedQuery]);

  useEffect(() => {
    if (open) {
      fetchFG();
      setSelectedIds(new Set());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, debouncedQuery]);

  const handleItemClick = (fg) => {
    if (multiple) {
      const newSelected = new Set(selectedIds);
      if (newSelected.has(fg.id)) {
        newSelected.delete(fg.id);
      } else {
        newSelected.add(fg.id);
      }
      setSelectedIds(newSelected);
    } else {
      // Single select: immediately call onSelect & close
      if (onSelect) onSelect(fg);
      onOpenChange(false);
    }
  };

  const confirmMultiSelect = () => {
    const selectedFGs = items.filter(f => selectedIds.has(f.id));
    if (onSelectMultiple) onSelectMultiple(selectedFGs);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col" data-testid="fg-picker-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="w-5 h-5" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cari berdasarkan kode atau nama FG..."
            className="pl-9"
            data-testid="fg-picker-search"
            autoFocus
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Results */}
        <ScrollArea className="flex-1 max-h-[50vh] -mx-2">
          <div className="px-2 space-y-2">
            {loading && (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Memuat FG produk...
              </div>
            )}
            {error && !loading && (
              <div className="flex items-center gap-2 p-4 rounded-md bg-destructive/10 text-destructive">
                <AlertCircle className="w-4 h-4" /> {error}
              </div>
            )}
            {!loading && !error && items.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <Package className="w-10 h-10 mx-auto opacity-30 mb-2" />
                <p>Tidak ada produk FG yang cocok.</p>
                <p className="text-xs mt-1">
                  Hubungi tim Inventory untuk menambah FG di Inventory Module.
                </p>
              </div>
            )}
            {!loading && items.map((fg) => {
              const sb = stockBadgeVariant(fg.stock_qty);
              const isSelected = selectedIds.has(fg.id);
              return (
                <button
                  type="button"
                  key={fg.id}
                  onClick={() => handleItemClick(fg)}
                  className={`w-full text-left p-3 rounded-md border transition-all
                    ${isSelected
                      ? 'border-primary bg-primary/5 ring-1 ring-primary'
                      : 'border-border hover:border-primary/50 hover:bg-muted/50'
                    }`}
                  data-testid={`fg-picker-item-${fg.code}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {multiple && isSelected && (
                          <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                        )}
                        <span className="font-semibold text-sm truncate">{fg.name}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <code className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">
                          {fg.code}
                        </code>
                        {fg.color && <span>Warna: {fg.color}</span>}
                        {fg.unit && <span>Unit: {fg.unit}</span>}
                      </div>
                    </div>
                    <Badge variant={sb.variant} className="flex-shrink-0">
                      {sb.label}
                    </Badge>
                  </div>
                </button>
              );
            })}
          </div>
        </ScrollArea>

        <DialogFooter className="flex items-center justify-between gap-2">
          <div className="flex-1 text-xs text-muted-foreground">
            {multiple && `${selectedIds.size} dipilih`}
            {!multiple && `${items.length} produk ditampilkan`}
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Batal
          </Button>
          {multiple && (
            <Button
              onClick={confirmMultiSelect}
              disabled={selectedIds.size === 0}
              data-testid="fg-picker-confirm"
            >
              Pilih {selectedIds.size > 0 ? `(${selectedIds.size})` : ''}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
