/**
 * EditCategoryDialog — Edit asset category & COA mapping.
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apicall } from '../utils';

export function EditCategoryDialog({ open, onClose, token, category, onUpdated }) {
  const [form, setForm] = useState({
    name: '', code: '', useful_life_years: 5, depr_method: 'straight_line',
    coa_asset_account: '', coa_depreciation_account: '',
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (category) {
      setForm({
        name: category.name || '',
        code: category.code || '',
        useful_life_years: category.useful_life_years || 5,
        depr_method: category.depr_method || 'straight_line',
        coa_asset_account: category.coa_asset_account || '',
        coa_depreciation_account: category.coa_depreciation_account || '',
      });
    }
  }, [category]);

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Nama kategori wajib diisi'); return; }
    setLoading(true);
    try {
      const data = await apicall('PUT', `/api/assets/categories/${category.id}`, token, form);
      if (data.ok) {
        toast.success('Kategori berhasil diupdate');
        onUpdated();
        onClose();
      } else {
        toast.error(data.detail || 'Gagal update kategori');
      }
    } catch { toast.error('Gagal update kategori'); }
    finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Edit Kategori Aset</DialogTitle></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Nama Kategori *</label>
              <Input placeholder="Peralatan IT" value={form.name}
                onChange={e => set('name', e.target.value)} className="mt-1" data-testid="cat-name-input" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Kode</label>
              <Input placeholder="IT" value={form.code}
                onChange={e => set('code', e.target.value)} className="mt-1" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Umur Manfaat (tahun)</label>
              <Input type="number" value={form.useful_life_years}
                onChange={e => set('useful_life_years', e.target.value)} className="mt-1" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Metode Depresiasi</label>
              <Select value={form.depr_method} onValueChange={v => set('depr_method', v)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="straight_line">Garis Lurus</SelectItem>
                  <SelectItem value="double_declining">Saldo Menurun</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <Separator className="my-3" />
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Mapping Chart of Accounts (COA)</p>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Akun COA Aset</label>
            <Input placeholder="Contoh: 1500 - Aset Tetap" value={form.coa_asset_account}
              onChange={e => set('coa_asset_account', e.target.value)} className="mt-1" data-testid="coa-asset-input" />
            <p className="text-[10px] text-muted-foreground mt-1">Akun untuk mencatat pembelian aset kategori ini</p>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Akun COA Depresiasi</label>
            <Input placeholder="Contoh: 1590 - Akumulasi Depresiasi" value={form.coa_depreciation_account}
              onChange={e => set('coa_depreciation_account', e.target.value)} className="mt-1" data-testid="coa-depr-input" />
            <p className="text-[10px] text-muted-foreground mt-1">Akun untuk mencatat akumulasi depresiasi</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={loading} data-testid="save-category-btn">
            {loading ? 'Menyimpan...' : 'Simpan Perubahan'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
