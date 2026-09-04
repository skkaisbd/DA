
import { useState, useRef } from 'react';
import { Upload, Download, FileSpreadsheet, Loader2, CheckCircle, AlertCircle, X } from 'lucide-react';

export default function ImportExportPanel({ token, importType, exportType, exportFilters = {}, onImportSuccess }) {
  const [showImportModal, setShowImportModal] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [exporting, setExporting] = useState(false);
  const fileRef = useRef(null);

  const downloadTemplate = async () => {
    if (!importType) return;
    try {
      const res = await fetch(`/api/import-template?type=${importType}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Gagal download template');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `template_${importType}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Gagal download template: ' + err.message);
    }
  };

  const handleImport = async (e) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return alert('Pilih file terlebih dahulu');

    setImporting(true);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('type', importType);
      formData.append('file', file);

      const res = await fetch('/api/import-data', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Import gagal');
      setImportResult(data);
      if (onImportSuccess) onImportSuccess();
    } catch (err) {
      setImportResult({ error: err.message });
    } finally {
      setImporting(false);
    }
  };

  const handleExport = async () => {
    if (!exportType) return;
    setExporting(true);
    try {
      const params = new URLSearchParams({ type: exportType });
      Object.entries(exportFilters).forEach(([k, v]) => { if (v) params.set(k, v); });
      
      const res = await fetch(`/api/export-excel?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || 'Export gagal');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export_${exportType}_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Export gagal: ' + err.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <div className="flex gap-2">
        {importType && (
          <button
            onClick={() => { setShowImportModal(true); setImportResult(null); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-foreground rounded-lg hover:bg-green-700 text-sm font-medium transition-colors"
          >
            <Upload className="w-4 h-4" />
            Import
          </button>
        )}
        {exportType && (
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-foreground rounded-lg hover:bg-emerald-700 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSpreadsheet className="w-4 h-4" />}
            Export Excel
          </button>
        )}
      </div>

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-[var(--overlay-bg)] flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--card-surface)] rounded-xl shadow-[0_12px_40px_rgba(0,0,0,0.25)] max-w-lg w-full max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="text-lg font-bold text-foreground">
                <Upload className="w-5 h-5 inline mr-2 text-green-600" />
                Import Data
              </h3>
              <button onClick={() => setShowImportModal(false)} className="text-muted-foreground hover:text-muted-foreground/60">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* Template Download */}
              <div className="bg-primary/10 border border-primary/20 rounded-lg p-3">
                <p className="text-sm text-blue-800 mb-2">
                  <strong>Langkah 1:</strong> Download template Excel terlebih dahulu
                </p>
                <button
                  onClick={downloadTemplate}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-foreground rounded-lg hover:brightness-110 text-sm font-medium"
                >
                  <Download className="w-4 h-4" />
                  Download Template
                </button>
              </div>

              {/* File Upload */}
              <form onSubmit={handleImport} className="space-y-3">
                <div className="bg-muted border border-border rounded-lg p-3">
                  <p className="text-sm text-foreground mb-2">
                    <strong>Langkah 2:</strong> Isi template dan upload file
                  </p>
                  <input
                    type="file"
                    ref={fileRef}
                    accept=".xlsx,.xls"
                    className="block w-full text-sm text-foreground/80 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
                  />
                </div>

                <button
                  type="submit"
                  disabled={importing}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 text-foreground rounded-lg hover:bg-green-700 font-medium disabled:opacity-50 transition-colors"
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Mengimport...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Upload & Import
                    </>
                  )}
                </button>
              </form>

              {/* Import Result */}
              {importResult && (
                <div className={`border rounded-lg p-3 ${importResult.error ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
                  {importResult.error ? (
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-5 h-5 text-red-700 dark:text-red-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-bold text-red-800">Import Gagal</p>
                        <p className="text-sm text-red-700">{importResult.error}</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <CheckCircle className="w-5 h-5 text-green-600" />
                        <p className="text-sm font-bold text-green-800">Import Berhasil!</p>
                      </div>
                      <div className="text-sm text-green-700 space-y-1">
                        {importResult.imported_products !== undefined && (
                          <p>✅ {importResult.imported_products} produk diimport</p>
                        )}
                        {importResult.imported_variants !== undefined && (
                          <p>✅ {importResult.imported_variants} varian diimport</p>
                        )}
                        {importResult.imported_garments !== undefined && (
                          <p>✅ {importResult.imported_garments} vendor diimport</p>
                        )}
                        {importResult.imported_pos !== undefined && (
                          <p>✅ {importResult.imported_pos} PO diimport</p>
                        )}
                        {importResult.imported_items !== undefined && (
                          <p>✅ {importResult.imported_items} item PO diimport</p>
                        )}
                        {importResult.skipped > 0 && (
                          <p className="text-yellow-700">⚠️ {importResult.skipped} baris dilewati (kosong)</p>
                        )}
                        {importResult.errors?.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-green-200">
                            <p className="font-medium text-yellow-700 mb-1">⚠️ {importResult.errors.length} peringatan:</p>
                            <ul className="list-disc list-inside text-xs text-yellow-700 max-h-32 overflow-auto">
                              {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                            </ul>
                          </div>
                        )}
                        {/* Show vendor accounts if garments import */}
                        {importResult.vendor_accounts?.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-green-200">
                            <p className="font-medium text-green-800 mb-1">Akun Vendor yang Dibuat:</p>
                            <div className="max-h-40 overflow-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="text-left">
                                    <th className="pb-1">Vendor</th>
                                    <th className="pb-1">Email</th>
                                    <th className="pb-1">Password</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {importResult.vendor_accounts.map((acc, i) => (
                                    <tr key={i} className="border-t border-green-200">
                                      <td className="py-1">{acc.garment_name}</td>
                                      <td className="py-1 font-mono">{acc.email}</td>
                                      <td className="py-1 font-mono">{acc.password}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
