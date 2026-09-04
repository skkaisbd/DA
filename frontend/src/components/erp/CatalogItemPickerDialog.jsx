/**
 * CatalogItemPickerDialog — F9b · pemilih produk dari KATALOG untuk layar Order.
 *
 * KENAPA KOMPONEN INI ADA
 * -----------------------
 * Sejak keputusan **K-8a**, order WAJIB menunjuk produk yang benar-benar ada di
 * katalog & tertaut Master Produk. Server menolak SKU asal-ketik dengan HTTP 400
 * ("SKU tidak dikenal — pilih produk dari katalog"). Selama layar order masih
 * meminta staf MENGETIK SKU, alur buat-order manual praktis mentok: hampir semua
 * yang diketik ditolak, dan staf tidak punya cara melihat SKU yang sah.
 *
 * Komponen ini menggantikan ketik-manual dengan pilih-dari-daftar, memakai
 * `GET /api/marketing/catalog-items/search` (lintas katalog) yang mengembalikan
 * **stok jual LIVE** (K-6a/K-7a) + alasan bila sebuah item tidak boleh dijual.
 *
 * Keputusan pemilik (2026-08-10): item yang tidak bisa dijual **tetap ditampilkan**
 * tetapi tidak bisa diklik + alasannya ditulis. Menyembunyikannya membuat staf
 * bertanya "kok produk saya hilang?" dan tidak tahu apa yang harus diperbaiki.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Search, ShoppingBag, Loader2, AlertCircle, AlertTriangle, X, Store, Layers,
} from 'lucide-react';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;

const STOCK_TONE = {
  in_stock: 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30',
  low_stock: 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/30',
  out_of_stock: 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 border-red-300 dark:border-red-500/30',
  unlinked: 'bg-muted text-muted-foreground border-border',
};

export function CatalogItemPickerDialog({
  open,
  onOpenChange,
  onSelect,
  token,
  excludeIds = [],
  platform = '',
  title = 'Pilih Produk dari Katalog',
  description = 'Stok yang ditampilkan adalah stok jual LIVE (sudah dikurangi pesanan lain, tanpa stok karantina). Produk yang tidak bisa dijual tetap terlihat beserta alasannya.',
}) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({ sellable: 0, blocked: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }),
    [token],
  );

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '40' });
      if (debounced) params.set('q', debounced);
      if (platform) params.set('platform', platform);
      const r = await fetch(`${API}/api/marketing/catalog-items/search?${params}`, { headers });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Gagal memuat produk katalog');
      setRows(d.items || []);
      setCounts(d.counts || { sellable: 0, blocked: 0 });
    } catch (e) {
      setError(e.message);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [headers, debounced, platform]);

  useEffect(() => {
    if (open) fetchRows();
  }, [open, fetchRows]);

  const visible = rows.filter(r => !excludeIds.includes(r.catalog_item_id));

  const pick = (row) => {
    if (!row.sellable) return;
    if (onSelect) onSelect(row);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col bg-card" data-testid="catalog-item-picker">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-foreground">
            <ShoppingBag className="w-5 h-5" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Cari nama produk, SKU, atau varian…"
            className="pl-9"
            data-testid="catalog-item-picker-search"
            autoFocus
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Kosongkan pencarian"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <ScrollArea className="flex-1 max-h-[52vh] -mx-2">
          <div className="px-2 space-y-2">
            {loading && (
              <div className="flex items-center justify-center py-10 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Memuat produk katalog…
              </div>
            )}

            {error && !loading && (
              <div className="flex items-center gap-2 p-4 rounded-md bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300"
                data-testid="catalog-item-picker-error">
                <AlertCircle className="w-4 h-4" /> {error}
              </div>
            )}

            {!loading && !error && visible.length === 0 && (
              <div className="text-center py-10 text-muted-foreground" data-testid="catalog-item-picker-empty">
                <ShoppingBag className="w-10 h-10 mx-auto opacity-30 mb-2" />
                <p className="text-foreground">Tidak ada produk katalog yang cocok.</p>
                <p className="text-xs mt-1">
                  Tambahkan produk di <b>Katalog Produk</b> (tombol “Tambah dari FG”) supaya
                  bisa dijual lewat order.
                </p>
              </div>
            )}

            {!loading && visible.map((row) => {
              const tone = STOCK_TONE[row.stock_live_status] || STOCK_TONE.unlinked;
              const stokLabel = row.available === null || row.available === undefined
                ? 'stok tak terhitung'
                : `${Number(row.available).toLocaleString('id-ID')} siap jual`;
              return (
                <button
                  type="button"
                  key={row.catalog_item_id}
                  onClick={() => pick(row)}
                  disabled={!row.sellable}
                  aria-disabled={!row.sellable}
                  title={row.block_reason || 'Pilih produk ini'}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    row.sellable
                      ? 'border-border bg-background hover:border-primary/50 hover:bg-muted/50 cursor-pointer'
                      : 'border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/5 opacity-80 cursor-not-allowed'
                  }`}
                  data-testid={`catalog-item-picker-row-${row.sku}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm text-foreground truncate">{row.name}</div>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <code className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono text-foreground">
                          {row.sku}
                        </code>
                        {row.category_code && (
                          <span className="inline-flex items-center gap-1">
                            <span className="font-mono text-[10px] px-1 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300">
                              {row.category_code}
                            </span>
                            {row.category_name}
                          </span>
                        )}
                        {row.variant_info && <span>· {row.variant_info}</span>}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-[11px] text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <Store className="w-3 h-3" /> {row.account_name || row.platform || '—'}
                          {row.catalog_name ? ` · ${row.catalog_name}` : ''}
                        </span>
                        {row.variant_sku && (
                          <span className="inline-flex items-center gap-1">
                            <Layers className="w-3 h-3" /> FG:{row.variant_sku}
                          </span>
                        )}
                      </div>
                      {!row.sellable && row.block_reason && (
                        <div className="flex items-start gap-1.5 mt-2 text-[11px] text-amber-800 dark:text-amber-200"
                          data-testid={`catalog-item-picker-blocked-${row.sku}`}>
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                          <span>{row.block_reason}</span>
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-semibold text-sm text-emerald-600 dark:text-emerald-400">
                        {fmtRp(row.harga_jual)}
                      </div>
                      <Badge variant="outline" className={`mt-1 text-[10px] ${tone}`}>
                        {stokLabel}
                      </Badge>
                      {row.hpp > 0 && row.harga_jual > 0 && (
                        <div className="text-[10px] text-muted-foreground mt-1"
                          title="Margin = harga jual − HPP">
                          margin {fmtRp(row.margin)} ({row.margin_pct}%)
                        </div>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </ScrollArea>

        <DialogFooter className="flex items-center justify-between gap-2">
          <div className="flex-1 text-xs text-muted-foreground" data-testid="catalog-item-picker-counts">
            <span className="text-emerald-700 dark:text-emerald-300 font-medium">{counts.sellable || 0}</span> bisa dijual
            {' · '}
            <span className="text-amber-700 dark:text-amber-300 font-medium">{counts.blocked || 0}</span> bermasalah
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="catalog-item-picker-close">
            Tutup
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default CatalogItemPickerDialog;
