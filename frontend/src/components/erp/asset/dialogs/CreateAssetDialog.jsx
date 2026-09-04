/**
 * CreateAssetDialog — Form to register new asset (incl. warranty & insurance).
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apicall } from '../utils';
import DocNumberField, { useDocNumberPolicy, docNumberPayload } from '../../docnum/DocNumberField';

export function CreateAssetDialog({ open, onClose, token, categories, onCreated }) {
  const [form, setForm] = useState({
    name: '', category_id: '', purchase_date: new Date().toISOString().slice(0, 10),
    purchase_cost: '', residual_value: '', useful_life_months: '',
    serial_number: '', brand: '', model: '', location: '', department: '', notes: '',
    // Warranty
    warranty_expiry_date: '', warranty_provider: '', warranty_terms: '',
    // Insurance
    insurance_policy_number: '', insurance_provider: '', insurance_expiry_date: '', insurance_value: '',
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  // SESI #27 — kebijakan penomoran Nomor Aset Inventaris. `KATEGORI` mengikuti
  // kategori terpilih supaya pratinjau nomor = nomor yang benar-benar akan lahir.
  const catCode = (categories || []).find(c => c.id === form.category_id)?.code || '';
  const numPolicy = useDocNumberPolicy('dewi_assets.asset_number', token,
                                       { KATEGORI: catCode });
  const [assetNo, setAssetNo] = useState('');

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Nama aset wajib diisi'); return; }
    if (!form.purchase_cost || Number(form.purchase_cost) <= 0) { toast.error('Harga beli harus > 0'); return; }
    setLoading(true);
    try {
      const data = await apicall('POST', '/api/assets', token, {
        ...form,
        ...docNumberPayload(numPolicy, 'asset_number', assetNo),
        purchase_cost: Number(form.purchase_cost),
        residual_value: form.residual_value ? Number(form.residual_value) : undefined,
        useful_life_months: form.useful_life_months ? Number(form.useful_life_months) : undefined,
      });
      if (data.id) {
        toast.success(`Aset ${data.asset_number} berhasil didaftarkan`);
        onCreated(data); onClose();
      } else {
        toast.error(data.detail || 'Gagal mendaftarkan aset');
      }
    } catch { toast.error('Gagal mendaftarkan aset'); }
    finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Daftarkan Aset Baru</DialogTitle>
          <DialogDescription>Isi data aset baru: nama, kategori, harga beli, garansi & asuransi (opsional).</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 py-2">
          <div className="col-span-2">
            <label className="text-xs font-medium text-muted-foreground">Nama Aset *</label>
            <Input placeholder="Laptop Dell XPS 13..." value={form.name}
              onChange={e => set('name', e.target.value)} className="mt-1" data-testid="asset-name-input" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Kategori</label>
            <Select value={form.category_id} onValueChange={v => set('category_id', v)}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Pilih kategori..." />
              </SelectTrigger>
              <SelectContent>
                {categories.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Tanggal Beli *</label>
            <Input type="date" value={form.purchase_date}
              onChange={e => set('purchase_date', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Harga Beli (Rp) *</label>
            <Input type="number" placeholder="5000000" value={form.purchase_cost}
              onChange={e => set('purchase_cost', e.target.value)} className="mt-1" data-testid="asset-cost-input" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Nilai Residu (Rp)</label>
            <Input type="number" placeholder="Otomatis 5%" value={form.residual_value}
              onChange={e => set('residual_value', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Umur Manfaat (bulan)</label>
            <Input type="number" placeholder="Dari kategori" value={form.useful_life_months}
              onChange={e => set('useful_life_months', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">No. Seri</label>
            <Input placeholder="SN-XXXX" value={form.serial_number}
              onChange={e => set('serial_number', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Merek / Merk</label>
            <Input placeholder="Dell, Lenovo, dll" value={form.brand}
              onChange={e => set('brand', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Model</label>
            <Input placeholder="XPS 13 9310" value={form.model}
              onChange={e => set('model', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Lokasi</label>
            <Input placeholder="Ruang IT, Lantai 2" value={form.location}
              onChange={e => set('location', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Departemen</label>
            <Input placeholder="IT, Produksi, dll" value={form.department}
              onChange={e => set('department', e.target.value)} className="mt-1" />
          </div>
          <div className="col-span-2">
            <label className="text-xs font-medium text-muted-foreground">Catatan</label>
            <Input placeholder="Catatan tambahan..." value={form.notes}
              onChange={e => set('notes', e.target.value)} className="mt-1" />
          </div>

          {/* Warranty Section */}
          <div className="col-span-2 pt-2 border-t">
            <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">🛡️ Garansi (Opsional)</p>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Tanggal Expired Garansi</label>
            <Input type="date" value={form.warranty_expiry_date}
              onChange={e => set('warranty_expiry_date', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Provider Garansi</label>
            <Input placeholder="Dell Support, Astra, dll" value={form.warranty_provider}
              onChange={e => set('warranty_provider', e.target.value)} className="mt-1" />
          </div>
          <div className="col-span-2">
            <label className="text-xs font-medium text-muted-foreground">Syarat Garansi</label>
            <Input placeholder="On-site 3 tahun, sparepart gratis" value={form.warranty_terms}
              onChange={e => set('warranty_terms', e.target.value)} className="mt-1" />
          </div>

          {/* Insurance Section */}
          <div className="col-span-2 pt-2 border-t">
            <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">🔒 Asuransi (Opsional)</p>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">No. Polis Asuransi</label>
            <Input placeholder="POL-2026-XXXX" value={form.insurance_policy_number}
              onChange={e => set('insurance_policy_number', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Provider Asuransi</label>
            <Input placeholder="Jasindo, Asuransi Jaya, dll" value={form.insurance_provider}
              onChange={e => set('insurance_provider', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Tanggal Expired Asuransi</label>
            <Input type="date" value={form.insurance_expiry_date}
              onChange={e => set('insurance_expiry_date', e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Nilai Pertanggungan (Rp)</label>
            <Input type="number" placeholder="50000000" value={form.insurance_value}
              onChange={e => set('insurance_value', e.target.value)} className="mt-1" />
          </div>
        </div>
        <div className="pb-1">
          <DocNumberField
            policy={numPolicy} value={assetNo} onChange={setAssetNo}
            testId="asset-inv-docnum" label="Nomor Aset" />
        </div>
        <p className="text-xs text-muted-foreground">*Journal pembelian akan dibuat otomatis sebagai draft.</p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={loading} data-testid="create-asset-submit">
            {loading ? 'Menyimpan...' : 'Daftarkan Aset'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
