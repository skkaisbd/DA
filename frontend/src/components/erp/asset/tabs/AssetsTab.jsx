/**
 * AssetsTab — Asset list with search/filter/pagination
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 */
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, RefreshCw, ChevronRight } from 'lucide-react';
import { STATUS_CONFIG } from '../constants';
import { fmtCurrency } from '../utils';
import { StatusBadge } from '../components/StatusBadge';

export function AssetsTab({
  assetSearch, setAssetSearch,
  assetStatus, setAssetStatus,
  assets, loading, assetPagination,
  loadAssets, onAssetClick,
}) {
  return (
    <>
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Cari aset..." className="pl-8" value={assetSearch}
            onChange={e => setAssetSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadAssets()}
            data-testid="asset-search-input" />
        </div>
        <Select value={assetStatus || 'all'} onValueChange={v => setAssetStatus(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-40" data-testid="asset-status-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua Status</SelectItem>
            <SelectItem value="active">Aktif</SelectItem>
            <SelectItem value="on_loan">Dipinjam</SelectItem>
            <SelectItem value="in_maintenance">Pemeliharaan</SelectItem>
            <SelectItem value="lost">Hilang</SelectItem>
            <SelectItem value="disposed">Dilepas</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={() => loadAssets()} data-testid="asset-search-btn">
          <RefreshCw size={14} className="mr-1" /> Cari
        </Button>
      </div>

      <div className="rounded-xl border overflow-hidden">
        <table className="w-full" data-testid="asset-table">
          <thead className="bg-muted/40">
            <tr>
              {['No. Aset','Nama','Kategori','Harga Beli','NBV','Status','Ditugaskan ke',''].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-3 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8 text-muted-foreground text-sm">Memuat...</td></tr>
            ) : assets.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-8 text-muted-foreground text-sm">Tidak ada aset ditemukan</td></tr>
            ) : (
              assets.map(a => (
                <tr key={a.id} className="hover:bg-muted/30 cursor-pointer transition-colors"
                  onClick={() => onAssetClick?.(a)}
                  data-testid={`asset-row-${a.id}`}>
                  <td className="px-3 py-2.5 text-xs font-mono text-muted-foreground">{a.asset_number}</td>
                  <td className="px-3 py-2.5 text-sm font-medium">{a.name}</td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{a.category_name}</td>
                  <td className="px-3 py-2.5 text-sm">{fmtCurrency(a.purchase_cost)}</td>
                  <td className="px-3 py-2.5 text-sm text-emerald-600 font-medium">
                    {fmtCurrency((a.purchase_cost || 0) - (a.accumulated_depreciation || 0))}
                  </td>
                  <td className="px-3 py-2.5"><StatusBadge status={a.status} configMap={STATUS_CONFIG} /></td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{a.assigned_to_name || '-'}</td>
                  <td className="px-3 py-2.5">
                    <Button variant="ghost" size="icon" className="h-7 w-7">
                      <ChevronRight size={14} />
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {assetPagination.total > 0 && (
        <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
          <span>Total: {assetPagination.total} aset</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={assetPagination.page <= 1}
              onClick={() => loadAssets(assetPagination.page - 1)}
              data-testid="asset-page-prev">Sebelumnya</Button>
            <span className="self-center">{assetPagination.page} / {assetPagination.total_pages}</span>
            <Button variant="outline" size="sm" disabled={assetPagination.page >= assetPagination.total_pages}
              onClick={() => loadAssets(assetPagination.page + 1)}
              data-testid="asset-page-next">Selanjutnya</Button>
          </div>
        </div>
      )}
    </>
  );
}
