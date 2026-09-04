/**
 * CategoriesTab — Asset category configuration with COA mapping
 * Extracted from AssetManagementPortal.jsx during Phase 4 refactor.
 */
import { Button } from '@/components/ui/button';
import { Edit } from 'lucide-react';

export function CategoriesTab({ categories, onEditCategory }) {
  return (
    <>
      <div className="mb-3">
        <p className="text-sm text-muted-foreground">
          Konfigurasi kategori aset dan mapping ke Chart of Accounts (COA) untuk integrasi finance
        </p>
      </div>
      <div className="rounded-xl border overflow-hidden">
        <table className="w-full" data-testid="category-table">
          <thead className="bg-muted/40">
            <tr>
              {['Kode','Nama','Umur Manfaat','Metode Depresiasi','COA Aset','COA Depresiasi',''].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {categories.map(c => (
              <tr key={c.id} className="hover:bg-muted/30 transition-colors" data-testid={`category-row-${c.id}`}>
                <td className="px-4 py-2.5 text-xs font-mono">{c.code}</td>
                <td className="px-4 py-2.5 text-sm font-medium">{c.name}</td>
                <td className="px-4 py-2.5 text-sm">{c.useful_life_years} tahun</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground">
                  {c.depr_method === 'straight_line' ? 'Garis Lurus' : 'Saldo Menurun'}
                </td>
                <td className="px-4 py-2.5 text-xs">
                  {c.coa_asset_account ? (
                    <span className="text-emerald-600 font-mono">{c.coa_asset_account}</span>
                  ) : (
                    <span className="text-muted-foreground italic">Belum diset</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs">
                  {c.coa_depreciation_account ? (
                    <span className="text-amber-600 font-mono">{c.coa_depreciation_account}</span>
                  ) : (
                    <span className="text-muted-foreground italic">Belum diset</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  <Button variant="ghost" size="sm"
                    onClick={() => onEditCategory?.(c)}
                    data-testid={`edit-cat-btn-${c.id}`}>
                    <Edit size={14} className="mr-1" /> Konfigurasi
                  </Button>
                </td>
              </tr>
            ))}
            {categories.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-muted-foreground text-sm">Belum ada kategori terdaftar</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
