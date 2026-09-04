/**
 * ImportExportToolbar — reusable Export (CSV/XLSX) + Import (dry-run → commit)
 * control, driven by the backend /api/data-transfer registry.
 *
 * Usage:
 *   <ImportExportToolbar collectionKey="materials" onImported={reload} />
 *
 * Renders nothing if the current user has no export access to the key
 * (backend RBAC via /registry). The Import button appears only when the
 * table is importable AND the user is allowed to import.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Download, Upload, FileSpreadsheet, FileText, Loader2,
  CheckCircle2, AlertTriangle, X, ArrowRightLeft,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiGet, apiPost, apiDownload } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog';

// module-level cache so we hit /registry once per session
let _registryPromise = null;
function loadRegistry() {
  if (!_registryPromise) {
    _registryPromise = apiGet('/data-transfer/registry')
      .then((d) => d.tables || [])
      .catch(() => []);
  }
  return _registryPromise;
}

export default function ImportExportToolbar({ collectionKey, label, onImported, size = 'sm' }) {
  const [entry, setEntry] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    loadRegistry().then((tables) => {
      if (alive) setEntry(tables.find((t) => t.key === collectionKey) || null);
    });
    return () => { alive = false; };
  }, [collectionKey]);

  const doExport = async (fmt) => {
    setExporting(true);
    try {
      await apiDownload(`/data-transfer/export/${collectionKey}?format=${fmt}`, `${collectionKey}.${fmt === 'csv' ? 'csv' : 'xlsx'}`);
      toast.success(`Export ${fmt.toUpperCase()} berhasil diunduh`);
    } catch (e) {
      toast.error(`Export gagal: ${e.message || e}`);
    } finally {
      setExporting(false);
    }
  };

  if (!entry) return null;

  return (
    <div className="flex items-center gap-2" data-testid={`ie-toolbar-${collectionKey}`}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size={size} disabled={exporting} data-testid={`ie-export-${collectionKey}`}>
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            <span className="ml-1.5">Ekspor</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => doExport('xlsx')} data-testid={`ie-export-xlsx-${collectionKey}`}>
            <FileSpreadsheet className="h-4 w-4 mr-2 text-emerald-600" /> Excel (.xlsx)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => doExport('csv')} data-testid={`ie-export-csv-${collectionKey}`}>
            <FileText className="h-4 w-4 mr-2 text-blue-600" /> CSV (.csv)
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {entry.importable && (
        <Button variant="outline" size={size} onClick={() => setImportOpen(true)} data-testid={`ie-import-${collectionKey}`}>
          <Upload className="h-4 w-4" />
          <span className="ml-1.5">Impor</span>
        </Button>
      )}

      {importOpen && (
        <ImportDialog
          collectionKey={collectionKey}
          label={label || entry.label}
          keyFields={entry.key_fields}
          onClose={() => setImportOpen(false)}
          onDone={() => { setImportOpen(false); onImported && onImported(); }}
        />
      )}
    </div>
  );
}

function Chip({ tone, icon: Icon, children }) {
  const tones = {
    slate: 'bg-muted text-foreground',
    green: 'bg-emerald-500/15 text-emerald-600',
    blue: 'bg-blue-500/15 text-blue-600',
    amber: 'bg-amber-500/15 text-amber-600',
    red: 'bg-red-500/15 text-red-600',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold ${tones[tone] || tones.slate}`}>
      {Icon && <Icon className="h-3.5 w-3.5" />}{children}
    </span>
  );
}

function ImportDialog({ collectionKey, label, keyFields, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dropActive, setDropActive] = useState(false);

  const downloadTemplate = async (fmt) => {
    try {
      await apiDownload(`/data-transfer/template/${collectionKey}?format=${fmt}`, `template_${collectionKey}.${fmt === 'csv' ? 'csv' : 'xlsx'}`);
    } catch (e) {
      toast.error(`Gagal unduh template: ${e.message || e}`);
    }
  };

  const runDryRun = useCallback(async (f) => {
    setBusy(true);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const res = await apiPost(`/data-transfer/import/${collectionKey}?mode=dry_run`, fd);
      setPreview(res);
    } catch (e) {
      toast.error(`Gagal membaca file: ${e.message || e}`);
    } finally {
      setBusy(false);
    }
  }, [collectionKey]);

  const onFile = (f) => {
    if (!f) return;
    setFile(f);
    runDryRun(f);
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiPost(`/data-transfer/import/${collectionKey}?mode=commit`, fd);
      toast.success(`Impor sukses: ${res.inserted} baru, ${res.updated} diperbarui`);
      onDone();
    } catch (e) {
      toast.error(`Impor gagal: ${e.message || e}`);
    } finally {
      setBusy(false);
    }
  };

  const canCommit = preview && preview.valid > 0 && preview.invalid === 0 && !busy;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl bg-card">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-5 w-5 text-primary" /> Impor {label}
          </DialogTitle>
          <DialogDescription>
            Unduh template, isi datanya, lalu unggah. Sistem akan mengecek dulu (dry-run) sebelum Anda konfirmasi.
            Key untuk update: <b>{(keyFields || []).join(' + ') || '-'}</b> (baris dengan key yang sudah ada akan diperbarui).
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Template:</span>
          <Button variant="outline" size="sm" onClick={() => downloadTemplate('xlsx')} data-testid="ie-template-xlsx">
            <FileSpreadsheet className="h-4 w-4 mr-1.5 text-emerald-600" /> Excel
          </Button>
          <Button variant="outline" size="sm" onClick={() => downloadTemplate('csv')} data-testid="ie-template-csv">
            <FileText className="h-4 w-4 mr-1.5 text-blue-600" /> CSV
          </Button>
        </div>

        {/* Dropzone */}
        <label
          onDragOver={(e) => { e.preventDefault(); setDropActive(true); }}
          onDragLeave={() => setDropActive(false)}
          onDrop={(e) => { e.preventDefault(); setDropActive(false); onFile(e.dataTransfer.files?.[0]); }}
          className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 cursor-pointer transition-colors ${dropActive ? 'border-primary bg-primary/5' : 'border-border bg-muted/30'}`}
          data-testid="ie-dropzone"
        >
          <Upload className="h-6 w-6 text-muted-foreground" />
          <div className="text-sm text-foreground">
            {file ? <b>{file.name}</b> : 'Tarik file ke sini atau klik untuk pilih (.xlsx / .csv)'}
          </div>
          <input type="file" accept=".csv,.xlsx" className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])} data-testid="ie-file-input" />
        </label>

        {busy && !preview && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Memproses file…</div>
        )}

        {preview && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Chip tone="slate">Total: {preview.total_rows}</Chip>
              <Chip tone="green" icon={CheckCircle2}>Valid: {preview.valid}</Chip>
              <Chip tone="blue">Baru: {preview.would_insert}</Chip>
              <Chip tone="amber">Update: {preview.would_update}</Chip>
              {preview.invalid > 0 && <Chip tone="red" icon={AlertTriangle}>Invalid: {preview.invalid}</Chip>}
            </div>

            {preview.invalid > 0 && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
                <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-red-600">
                  <AlertTriangle className="h-4 w-4" /> {preview.invalid} baris bermasalah — perbaiki dulu sebelum impor
                </div>
                <div className="max-h-40 overflow-auto text-xs">
                  {preview.preview_invalid.map((r, i) => (
                    <div key={i} className="border-b border-border/50 py-1">
                      <span className="font-mono text-muted-foreground">Baris {r.row}:</span>{' '}
                      <span className="text-red-600">{(r.errors || []).join('; ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {preview.valid > 0 && (
              <div className="rounded-lg border border-border p-2">
                <div className="mb-1 text-xs font-semibold text-muted-foreground">Pratinjau baris valid (maks 100)</div>
                <div className="max-h-48 overflow-auto text-xs">
                  {preview.preview_valid.slice(0, 100).map((r, i) => (
                    <div key={i} className="flex items-center gap-2 border-b border-border/40 py-1">
                      <span className={`rounded px-1.5 text-[10px] font-bold ${r.action === 'insert' ? 'bg-blue-500/15 text-blue-600' : 'bg-amber-500/15 text-amber-600'}`}>
                        {r.action === 'insert' ? 'BARU' : 'UPDATE'}
                      </span>
                      <span className="truncate text-foreground">{Object.values(r.data).slice(0, 4).join(' · ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}><X className="h-4 w-4 mr-1" /> Batal</Button>
          <Button onClick={commit} disabled={!canCommit} data-testid="ie-commit-btn">
            {busy ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-1.5" />}
            Impor {preview ? `${preview.valid} baris` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
