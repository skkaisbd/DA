/**
 * ImportFromModuleDialog — import data from another system module
 * (Asset Management or Procurement Requests) into a new spreadsheet.
 *
 * User picks: source module, target doc name, optional status/department filters,
 * and which fields to include.
 */
import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Package, Download, Loader2 } from 'lucide-react';

import {
  apicall, ASSET_FIELDS, PROCUREMENT_FIELDS, DEF_ASSET_FIELDS, DEF_PR_FIELDS,
} from './utils';

export default function ImportFromModuleDialog({ open, onClose, token, onImported }) {
  const [module, setModule] = useState('assets');
  const [docName, setDocName] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deptFilter, setDeptFilter] = useState('');
  const [selFields, setSelFields] = useState(DEF_ASSET_FIELDS);
  const [importing, setImporting] = useState(false);

  const allFields = module === 'assets' ? ASSET_FIELDS : PROCUREMENT_FIELDS;

  useEffect(() => {
    setSelFields(module === 'assets' ? DEF_ASSET_FIELDS : DEF_PR_FIELDS);
    setStatusFilter('');
    setDeptFilter('');
  }, [module]);

  const handleImport = async () => {
    if (selFields.length === 0) { toast.error('Pilih minimal satu kolom'); return; }
    setImporting(true);
    try {
      const filters = {};
      if (statusFilter) filters.status = statusFilter;
      if (deptFilter) filters.department = deptFilter;
      const data = await apicall('POST', '/api/workspace/documents/import-from-module', token, {
        module, name: docName || undefined, filters, fields: selFields,
      });
      toast.success(`${data.imported_count} data berhasil diimport ke "${data.name}"`);
      onImported(data);
      onClose();
    } catch (e) {
      toast.error(e.message || 'Import gagal');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md" data-testid="import-module-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package size={16} />Import dari Modul Sistem
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Modul Sumber</label>
            <Select value={module} onValueChange={setModule}>
              <SelectTrigger data-testid="import-module-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="assets">Manajemen Aset</SelectItem>
                <SelectItem value="procurement">Pengadaan (PR)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Nama Dokumen (opsional)</label>
            <Input placeholder="Biarkan kosong untuk nama otomatis..."
              value={docName} onChange={(e) => setDocName(e.target.value)}
              data-testid="import-doc-name" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Filter Status</label>
              <Input placeholder="Semua status" value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)} className="text-sm h-8" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Filter Departemen</label>
              <Input placeholder="Semua dept." value={deptFilter}
                onChange={(e) => setDeptFilter(e.target.value)} className="text-sm h-8" />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-muted-foreground">Pilih Kolom</label>
              <button className="text-xs text-primary"
                onClick={() => setSelFields(allFields.map((f) => f.key))}>Pilih semua</button>
            </div>
            <div className="grid grid-cols-2 gap-1 max-h-40 overflow-y-auto border rounded-md p-2">
              {allFields.map((f) => (
                <label key={f.key} className="flex items-center gap-1.5 text-xs cursor-pointer hover:bg-muted/30 rounded px-1 py-0.5">
                  <input type="checkbox" checked={selFields.includes(f.key)}
                    onChange={() => setSelFields((prev) =>
                      prev.includes(f.key) ? prev.filter((k) => k !== f.key) : [...prev, f.key]
                    )}
                    className="rounded" />
                  {f.label}
                </label>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={importing}>Batal</Button>
          <Button onClick={handleImport}
            disabled={importing || selFields.length === 0}
            data-testid="import-module-submit">
            {importing ? <Loader2 size={14} className="animate-spin mr-1" /> : <Download size={14} className="mr-1" />}
            {importing ? 'Mengimport...' : `Import ${module === 'assets' ? 'Aset' : 'Pengadaan'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
