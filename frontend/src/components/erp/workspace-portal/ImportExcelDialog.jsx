/**
 * ImportExcelDialog — 2-step Excel import (preview → column mapping → import).
 *
 * Step 1: upload .xlsx/.xls → backend returns column suggestions + preview rows.
 * Step 2: user can rename columns, change types, toggle include, then submit.
 */
import { useState, useRef } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  FileSpreadsheet, Upload, Download, Loader2,
} from 'lucide-react';

import { API, apicall } from './utils';

export default function ImportExcelDialog({ open, onClose, token, onImported }) {
  const [step, setStep] = useState(1);   // 1 = upload, 2 = mapping
  const [preview, setPreview] = useState(null);   // { columns, preview_rows, total_rows, file_name }
  const [mapping, setMapping] = useState([]);     // [{ original_name, key, name, type, include }]
  const [docName, setDocName] = useState('');
  const [fileData, setFileData] = useState(null); // base64
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef(null);

  const reset = () => {
    setStep(1); setPreview(null); setMapping([]);
    setDocName(''); setFileData(null);
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.match(/\.xlsx?$/i)) { toast.error('File harus .xlsx atau .xls'); return; }
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const res = await fetch(`${API}/api/workspace/documents/preview-excel`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Preview gagal');
      setPreview(data);
      setDocName(file.name.replace(/\.[^.]+$/, ''));
      setMapping(data.columns.map((c) => ({
        ...c, key: c.suggested_key, name: c.suggested_name,
      })));

      // Also read as base64 for final import
      const reader = new FileReader();
      reader.onload = () => setFileData(reader.result.split(',')[1]);
      reader.readAsDataURL(file);

      setStep(2);
    } catch (e) {
      toast.error(e.message || 'Upload gagal');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleImport = async () => {
    const included = mapping.filter((m) => m.include);
    if (included.length === 0) { toast.error('Pilih minimal satu kolom'); return; }
    setImporting(true);
    try {
      const doc = await apicall('POST', '/api/workspace/documents/import-excel-mapped', token, {
        file_data: fileData, column_mapping: mapping,
        doc_name: docName || 'Import Excel',
      });
      toast.success(`${doc.content?.rows?.length || 0} baris berhasil diimport ke "${doc.name}"`);
      onImported(doc); onClose(); reset();
    } catch (e) {
      toast.error(e.message || 'Import gagal');
    } finally {
      setImporting(false);
    }
  };

  const updateMapping = (idx, field, value) => {
    setMapping((prev) => prev.map((m, i) => i === idx ? { ...m, [field]: value } : m));
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { onClose(); reset(); } }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col" data-testid="import-excel-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload size={16} />Import Excel
            <span className="text-xs font-normal text-muted-foreground">Langkah {step} dari 2</span>
          </DialogTitle>
          <div className="flex gap-1 mt-2">
            {[1, 2].map((s) => (
              <div key={s} className={`h-1 flex-1 rounded-full ${step >= s ? 'bg-primary' : 'bg-muted'}`} />
            ))}
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 overflow-auto">
          {step === 1 && (
            <div className="flex flex-col items-center justify-center py-10 gap-4">
              <div className="w-16 h-16 rounded-2xl bg-emerald-100 flex items-center justify-center">
                <FileSpreadsheet size={32} className="text-emerald-600" />
              </div>
              <div className="text-center">
                <p className="font-medium">Pilih file Excel untuk diimport</p>
                <p className="text-sm text-muted-foreground mt-1">Format yang didukung: .xlsx, .xls</p>
              </div>
              <Button onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="excel-file-btn">
                {uploading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Upload size={14} className="mr-1" />}
                {uploading ? 'Membaca file...' : 'Pilih File Excel'}
              </Button>
              <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={handleFileSelect} className="hidden" />
            </div>
          )}

          {step === 2 && preview && (
            <div className="space-y-4 p-1">
              {/* Summary */}
              <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                <FileSpreadsheet size={20} className="text-emerald-600" />
                <div>
                  <p className="text-sm font-medium">{preview.file_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {preview.total_rows} baris data · {preview.columns.length} kolom
                  </p>
                </div>
              </div>

              {/* Doc name */}
              <div>
                <label className="text-sm font-medium mb-1 block">Nama Dokumen</label>
                <Input value={docName} onChange={(e) => setDocName(e.target.value)}
                  placeholder="Nama spreadsheet..." data-testid="excel-doc-name" />
              </div>

              {/* Column Mapping */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium">Mapping Kolom</p>
                  <div className="flex gap-2">
                    <button className="text-xs text-primary"
                      onClick={() => setMapping((prev) => prev.map((m) => ({ ...m, include: true })))}>Pilih semua</button>
                    <span className="text-muted-foreground">·</span>
                    <button className="text-xs text-muted-foreground"
                      onClick={() => setMapping((prev) => prev.map((m) => ({ ...m, include: false })))}>Hapus semua</button>
                  </div>
                </div>
                <div className="border rounded-lg overflow-hidden">
                  <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-muted/40 text-xs font-medium text-muted-foreground border-b">
                    <div className="col-span-1">Import</div>
                    <div className="col-span-3">Kolom Excel</div>
                    <div className="col-span-4">Nama di Spreadsheet</div>
                    <div className="col-span-2">Tipe</div>
                    <div className="col-span-2">Contoh Data</div>
                  </div>
                  {mapping.map((m, idx) => (
                    <div key={idx}
                      className={`grid grid-cols-12 gap-2 px-3 py-2 items-center border-b last:border-0 text-sm ${!m.include ? 'opacity-50' : ''}`}>
                      <div className="col-span-1">
                        <input type="checkbox" checked={m.include}
                          onChange={(e) => updateMapping(idx, 'include', e.target.checked)}
                          className="rounded" />
                      </div>
                      <div className="col-span-3 text-xs text-muted-foreground truncate" title={m.original_name}>
                        {m.original_name}
                      </div>
                      <div className="col-span-4">
                        <Input value={m.name}
                          onChange={(e) => updateMapping(idx, 'name', e.target.value)}
                          className="h-7 text-xs" disabled={!m.include} />
                      </div>
                      <div className="col-span-2">
                        <Select value={m.type}
                          onValueChange={(v) => updateMapping(idx, 'type', v)} disabled={!m.include}>
                          <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="text">Teks</SelectItem>
                            <SelectItem value="number">Angka</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="col-span-2 text-xs text-muted-foreground truncate">
                        {preview.preview_rows[0]?.[m.original_name] || '-'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Data Preview */}
              <div>
                <p className="text-sm font-medium mb-2">Preview Data (10 baris pertama)</p>
                <div className="border rounded-lg overflow-x-auto">
                  <table className="text-xs w-full">
                    <thead className="bg-muted/40">
                      <tr>
                        {mapping.filter((m) => m.include).map((m) => (
                          <th key={m.original_name}
                            className="px-3 py-2 text-left font-medium border-b border-r last:border-r-0 whitespace-nowrap">
                            {m.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.preview_rows.map((row, ri) => (
                        <tr key={ri} className="border-b last:border-0 hover:bg-muted/20">
                          {mapping.filter((m) => m.include).map((m) => (
                            <td key={m.original_name}
                              className="px-3 py-1.5 border-r last:border-r-0 whitespace-nowrap max-w-[120px] truncate">
                              {row[m.original_name] || ''}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </ScrollArea>

        <DialogFooter className="gap-2 pt-3 border-t">
          {step === 2 && (
            <Button variant="outline" onClick={() => { setStep(1); setPreview(null); }} disabled={importing}>
              ← Kembali
            </Button>
          )}
          <Button variant="outline" onClick={() => { onClose(); reset(); }}
            disabled={importing || uploading}>Batal</Button>
          {step === 2 && (
            <Button onClick={handleImport}
              disabled={importing || mapping.filter((m) => m.include).length === 0}
              data-testid="excel-import-submit">
              {importing ? <Loader2 size={14} className="animate-spin mr-1" /> : <Download size={14} className="mr-1" />}
              {importing ? 'Mengimport...' : `Import ${mapping.filter((m) => m.include).length} Kolom`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
