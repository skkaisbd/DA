import { useState } from 'react';
import { Calculator, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GlassPanel, GlassInput } from '@/components/ui/glass';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { readNumber, FIELD } from '@/lib/materialFields';  // FASE 6.6-B

/**
 * RequirementsPreviewCard (Phase 7A Fase 1 — unified materials[])
 *
 * Kalkulasi kebutuhan material untuk quantity tertentu.
 * Membaca `preview.materials[]` (skema terunifikasi) dari
 * POST /api/rahaza/boms/{id}/requirements.
 *
 * Props:
 * - bom: BOM object (butuh id, model_code, size_code, version)
 * - token: JWT token
 */
const fmt = (n, dp = 3) => {
  const v = Number(n);
  if (!isFinite(v)) return '0';
  // Tampilkan desimal hanya bila perlu (aksesoris pcs biasanya bulat).
  return Number.isInteger(v) ? String(v) : v.toFixed(dp);
};

export const RequirementsPreviewCard = ({ bom, token }) => {
  const [qtyPcs, setQtyPcs] = useState('1000');
  const [rounding, setRounding] = useState('none');
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const calculateRequirements = async () => {
    if (!qtyPcs || parseFloat(qtyPcs) <= 0) {
      toast.error('Masukkan quantity yang valid');
      return;
    }
    if (!bom || !bom.id) {
      toast.error('Pilih BOM terlebih dahulu');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/rahaza/boms/${bom.id}/requirements`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ qty_pcs: parseFloat(qtyPcs), rounding }),
      });
      if (!res.ok) throw new Error('Gagal menghitung kebutuhan material');
      const data = await res.json();
      setPreview(data);
    } catch (err) {
      toast.error(err.message || 'Gagal menghitung kebutuhan');
    } finally {
      setLoading(false);
    }
  };

  const exportCSV = () => {
    if (!preview) return;
    let csv = 'Kategori,Tipe,Kode,Nama,Qty per pcs,Total Qty,Unit,Catatan\n';
    (preview.materials || []).forEach(m => {
      const cat = (m.category_name || '').replace(/"/g, '""');
      const name = (m.name || '').replace(/"/g, '""');
      const notes = (m.notes || '').replace(/"/g, '""');
      csv += `"${cat}",${m.material_type || ''},${m.code || ''},"${name}",${m.qty_per_pcs},${m.qty_total},${m.unit || ''},"${notes}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kebutuhan-material-${bom.model_code}-${bom.size_code}-v${bom.version}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
    toast.success('CSV berhasil diunduh');
  };

  const materials = preview?.materials || [];

  return (
    <GlassPanel className="p-5 space-y-5" data-testid="requirements-preview-card">
      <div>
        <h3 className="text-lg font-semibold text-foreground flex items-center gap-2 mb-1">
          <Calculator className="w-5 h-5 text-primary" />
          Preview Kebutuhan Material
        </h3>
        <p className="text-sm text-muted-foreground">
          Hitung kebutuhan material untuk produksi quantity tertentu
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <Label htmlFor="qty-pcs">Quantity (pcs) *</Label>
          <GlassInput
            id="qty-pcs"
            type="number"
            placeholder="1000"
            value={qtyPcs}
            onChange={e => setQtyPcs(e.target.value)}
            data-testid="requirements-qty-input"
          />
        </div>
        <div>
          <Label htmlFor="rounding">Pembulatan</Label>
          <Select value={rounding} onValueChange={setRounding}>
            <SelectTrigger id="rounding"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Tidak ada</SelectItem>
              <SelectItem value="ceil">Ke atas (ceil)</SelectItem>
              <SelectItem value="floor">Ke bawah (floor)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Button
        onClick={calculateRequirements}
        disabled={loading || !qtyPcs}
        className="w-full"
        data-testid="requirements-calculate-button"
      >
        {loading ? 'Menghitung...' : 'Hitung Kebutuhan'}
      </Button>

      {preview && (
        <div className="space-y-4 pt-4 border-t border-[var(--glass-border)]">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <div className="text-sm text-muted-foreground">Untuk produksi</div>
              <div className="text-2xl font-bold text-foreground font-mono">
                {preview.qty_pcs} pcs
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {preview.model_code} · {preview.size_code} · v{preview.version}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {readNumber(preview, FIELD.totalMaterialKg) > 0 && (
                <Badge variant="secondary" className="font-mono" data-testid="requirements-total-yarn">
                  Total bahan (kg): {readNumber(preview, FIELD.totalMaterialKg).toFixed(3)} kg
                </Badge>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={exportCSV}
                data-testid="requirements-export-csv-button"
              >
                <Download className="w-4 h-4 mr-2" />
                Export CSV
              </Button>
            </div>
          </div>

          {materials.length > 0 ? (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-foreground">Kebutuhan Material</h4>
                <Badge variant="secondary">{materials.length} item</Badge>
              </div>
              <div className="border border-[var(--glass-border)] rounded-lg overflow-hidden">
                <Table data-testid="requirements-preview-materials-table">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Kode</TableHead>
                      <TableHead>Nama</TableHead>
                      <TableHead>Kategori</TableHead>
                      <TableHead className="text-right">Qty/pcs</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead>Unit</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {materials.map((m, idx) => (
                      <TableRow key={idx} data-testid={`requirements-row-${idx}`}>
                        <TableCell className="font-mono text-xs">{m.code || '—'}</TableCell>
                        <TableCell>{m.name}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {m.category_name || m.material_type || '—'}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">{fmt(m.qty_per_pcs)}</TableCell>
                        <TableCell className="text-right font-mono font-semibold">{fmt(m.qty_total)}</TableCell>
                        <TableCell className="text-xs">{m.unit}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              BOM ini belum memiliki material.
            </div>
          )}
        </div>
      )}
    </GlassPanel>
  );
};
