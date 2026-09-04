/**
 * BulkImportDialog — Upload CSV/Excel, preview, column mapping, import.
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Upload, Download } from 'lucide-react';
import { toast } from 'sonner';
import { API } from '../utils';

export function BulkImportDialog({ open, onClose, token, categories, onImported }) {
  const [step, setStep] = useState(1); // 1=upload, 2=mapping, 3=result
  const [loading, setLoading] = useState(false);
  const [previewData, setPreviewData] = useState(null); // { columns, preview, total_rows }
  const [mapping, setMapping] = useState({});  // assetField → csvColumn
  const [categoryId, setCategoryId] = useState('');
  const [result, setResult] = useState(null);
  const [rawRows, setRawRows] = useState([]);
  const fileRef = useRef(null);

  const ASSET_FIELDS = [
    { key: 'name', label: 'Nama Aset*', required: true },
    { key: 'purchase_date', label: 'Tanggal Beli* (YYYY-MM-DD)', required: true },
    { key: 'purchase_cost', label: 'Harga Beli*', required: true },
    { key: 'useful_life_months', label: 'Masa Manfaat (bulan)' },
    { key: 'residual_value', label: 'Nilai Residu' },
    { key: 'serial_number', label: 'No. Seri' },
    { key: 'brand', label: 'Merek' },
    { key: 'model', label: 'Model' },
    { key: 'location', label: 'Lokasi' },
    { key: 'department', label: 'Departemen' },
    { key: 'notes', label: 'Catatan' },
    { key: 'warranty_expiry_date', label: 'Expired Garansi' },
    { key: 'warranty_provider', label: 'Provider Garansi' },
    { key: 'insurance_policy_number', label: 'No. Polis Asuransi' },
    { key: 'insurance_provider', label: 'Provider Asuransi' },
    { key: 'insurance_expiry_date', label: 'Expired Asuransi' },
    { key: 'insurance_value', label: 'Nilai Pertanggungan' },
  ];

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch(`${API}/api/assets/bulk-import/preview`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Gagal parse file');
      setPreviewData(data);
      // Auto-map: try to match column names to asset fields
      const autoMap = {};
      ASSET_FIELDS.forEach(f => {
        const match = data.columns.find(c =>
          c.toLowerCase().replace(/[^a-z0-9]/g,'') === f.key.toLowerCase().replace(/[^a-z0-9]/g,'')
          || c.toLowerCase().includes(f.key.toLowerCase())
        );
        if (match) autoMap[f.key] = match;
      });
      setMapping(autoMap);
      setStep(2);
    } catch (err) {
      toast.error(err.message || 'Gagal upload file');
    } finally {
      setLoading(false);
    }
  };

  const downloadTemplate = () => {
    const url = `${API}/api/assets/bulk-import/template`;
    const a = document.createElement('a');
    a.href = url;
    a.setAttribute('download', 'template_import_aset.xlsx');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const reset = () => {
    setStep(1); setPreviewData(null); setMapping({}); setCategoryId('');
    setResult(null); setRawRows([]);
    if (fileRef.current) fileRef.current.value = '';
  };

  // When previewData arrives, also fetch full raw rows for import execution
  useEffect(() => {
    if (previewData && fileRef.current?.files[0]) {
      const file = fileRef.current.files[0];
      const reader = new FileReader();
      reader.onload = async () => {
        // Note: the redesigned flow re-uploads the file in handleImportWithFile.
        // rawRows kept for legacy compatibility only.
      };
      reader.readAsArrayBuffer(file);
    }
  }, [previewData]);

  // Re-upload file for full data
  const handleImportWithFile = async () => {
    if (!categoryId) { toast.error('Pilih kategori terlebih dahulu'); return; }
    const requiredMaps = ['name', 'purchase_date', 'purchase_cost'];
    if (requiredMaps.some(k => !mapping[k])) {
      toast.error('Mapping kolom Name, Tanggal Beli, dan Harga Beli wajib diisi');
      return;
    }
    const file = fileRef.current?.files[0];
    if (!file) { toast.error('File tidak ditemukan, ulangi upload'); return; }
    setLoading(true);
    try {
      const execForm = new FormData();
      execForm.append('file', file);
      execForm.append('mapping', JSON.stringify(mapping));
      execForm.append('category_id', categoryId);
      const execR = await fetch(`${API}/api/assets/bulk-import/execute-file`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: execForm,
      });
      const data = await execR.json();
      if (!execR.ok) throw new Error(data.detail || 'Gagal import');
      setResult(data);
      setStep(3);
      if (data.created_count > 0) onImported?.();
      toast.success(`✅ ${data.created_count} aset berhasil diimport`);
    } catch (err) {
      toast.error(err.message || 'Gagal import');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload size={18} /> Bulk Import Aset dari CSV/Excel
          </DialogTitle>
          <DialogDescription>Unggah file CSV/Excel berisi data aset; sistem akan validasi, mapping kolom, lalu import.</DialogDescription>
        </DialogHeader>

        {/* Step Indicator */}
        <div className="flex items-center gap-2 text-xs mb-2">
          {['Upload File', 'Column Mapping', 'Hasil'].map((s, i) => (
            <span key={s} className={`flex items-center gap-1 ${step === i+1 ? 'text-primary font-semibold' : step > i+1 ? 'text-emerald-600' : 'text-muted-foreground'}`}>
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] border ${step === i+1 ? 'border-primary bg-primary text-primary-foreground' : step > i+1 ? 'border-emerald-500 bg-emerald-500 text-foreground' : 'border-muted-foreground'}`}>{i+1}</span>
              {s}
              {i < 2 && <span className="text-muted-foreground ml-1">›</span>}
            </span>
          ))}
        </div>

        {/* Step 1: Upload */}
        {step === 1 && (
          <div className="space-y-4">
            <div className="bg-muted/40 rounded-lg p-4 text-sm space-y-1">
              <p className="font-medium">Panduan:</p>
              <p className="text-muted-foreground">Upload file CSV atau Excel (.xlsx). Kolom wajib: <strong>Nama Aset, Tanggal Beli, Harga Beli</strong>.</p>
            </div>
            <Button variant="outline" className="w-full" onClick={downloadTemplate}>
              <Download size={14} className="mr-2" /> Download Template Excel
            </Button>
            <div
              className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:bg-muted/20 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={32} className="mx-auto text-muted-foreground mb-2" />
              <p className="text-sm font-medium">Klik untuk pilih file</p>
              <p className="text-xs text-muted-foreground mt-1">CSV atau Excel (.xlsx, .xls)</p>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={handleFileUpload}
            />
            {loading && <p className="text-xs text-muted-foreground text-center">Memproses file...</p>}
          </div>
        )}

        {/* Step 2: Mapping */}
        {step === 2 && previewData && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Total: <strong>{previewData.total_rows}</strong> baris ditemukan</span>
              <Button variant="ghost" size="sm" onClick={() => setStep(1)}>← Ganti File</Button>
            </div>
            {/* Preview table */}
            <div className="overflow-x-auto rounded border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40">
                  <tr>{previewData.columns.map(c => <th key={c} className="px-2 py-1.5 text-left font-medium truncate max-w-[100px]">{c}</th>)}</tr>
                </thead>
                <tbody>
                  {previewData.preview.map((row, ri) => (
                    <tr key={ri} className="border-t">
                      {previewData.columns.map(c => <td key={c} className="px-2 py-1 truncate max-w-[100px]" title={row[c]}>{row[c] || '-'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Category selector */}
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Kategori Aset*</label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger><SelectValue placeholder="Pilih kategori..." /></SelectTrigger>
                <SelectContent>
                  {categories.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {/* Column mapping */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-2">Mapping Kolom</label>
              <div className="grid grid-cols-2 gap-2">
                {ASSET_FIELDS.map(f => (
                  <div key={f.key} className="flex items-center gap-2">
                    <span className="text-xs w-40 shrink-0">{f.label}</span>
                    <Select value={mapping[f.key] || '__none__'} onValueChange={v => setMapping(p => ({...p, [f.key]: v === '__none__' ? '' : v}))}>
                      <SelectTrigger className="h-7 text-xs"><SelectValue placeholder="- abaikan -" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">- abaikan -</SelectItem>
                        {previewData.columns.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep(1)}>Kembali</Button>
              <Button onClick={handleImportWithFile} disabled={loading}>
                {loading ? 'Mengimport...' : `Import ${previewData.total_rows} Aset`}
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Step 3: Result */}
        {step === 3 && result && (
          <div className="space-y-4 text-center py-4">
            <div className="text-4xl">{result.error_count === 0 ? '✅' : '⚠️'}</div>
            <p className="text-lg font-bold">Import Selesai</p>
            <div className="grid grid-cols-2 gap-3 max-w-xs mx-auto text-sm">
              <div className="bg-emerald-100 dark:bg-emerald-500/10 rounded-lg p-3">
                <p className="text-2xl font-bold text-emerald-600">{result.created_count}</p>
                <p className="text-xs text-muted-foreground">Berhasil diimport</p>
              </div>
              <div className="bg-destructive/10 rounded-lg p-3">
                <p className="text-2xl font-bold text-destructive">{result.error_count}</p>
                <p className="text-xs text-muted-foreground">Gagal</p>
              </div>
            </div>
            {result.errors?.length > 0 && (
              <div className="text-left bg-muted/40 rounded-lg p-3 space-y-1 max-h-32 overflow-y-auto">
                <p className="text-xs font-medium">Detail Error:</p>
                {result.errors.map((e, i) => (
                  <p key={i} className="text-xs text-destructive">Baris {e.row}: {e.error}</p>
                ))}
              </div>
            )}
            <div className="flex gap-2 justify-center">
              <Button variant="outline" onClick={() => { reset(); onClose(); }}>Tutup</Button>
              <Button onClick={() => { reset(); }}>Import Lagi</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
