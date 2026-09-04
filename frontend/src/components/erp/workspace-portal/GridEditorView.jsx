/**
 * GridEditorView — the spreadsheet editor (header + formula bar + formatting
 * toolbar + DataGrid + footer + nested dialogs).
 *
 * Used by WorkspacePortal when a document is selected.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DataGrid, SelectColumn } from 'react-data-grid';
import 'react-data-grid/lib/styles.css';
import {
  ChevronRight, Edit3, Share2, Download, History, Save, Plus, Columns, Trash2,
  Loader2, AlertCircle, Check, Lock,
} from 'lucide-react';

import {
  API, apicall, canEdit, canShare, evaluateFormula,
} from './utils';
import AccessBadge from './AccessBadge';
import FormulaBar from './FormulaBar';
import FormattingToolbar from './FormattingToolbar';
import ShareDialog from './ShareDialog';
import { ManageColumnsDialog } from './ColumnsDialog';
import VersionHistoryDrawer from './VersionHistoryDrawer';

export default function GridEditorView({ document: initDoc, token, onBack, onUpdated }) {
  const [doc, setDoc] = useState(initDoc);
  const [rows, setRows] = useState([]);
  const [columns, setColumns] = useState([]);
  const [formatting, setFormatting] = useState({});
  const [selectedRows, setSelectedRows] = useState(() => new Set());
  const [selectedCell, setSelectedCell] = useState(null);   // { rowId, colKey, rawVal }
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState('saved');
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');
  const [showShare, setShowShare] = useState(false);
  const [showManageCols, setShowManageCols] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [exporting, setExporting] = useState(false);
  const saveTimerRef = useRef(null);
  const isReadOnly = !canEdit(doc?.access_level);

  useEffect(() => {
    if (initDoc) {
      setDoc(initDoc);
      const content = initDoc.content || {};
      setColumns(content.columns || []);
      setRows(content.rows || []);
      setFormatting(content.formatting || {});
      setSaveStatus('saved');
    }
  }, [initDoc]);

  // ── Save ──
  const handleSave = useCallback(async (rowsToSave, colsToSave, fmtToSave) => {
    if (isReadOnly) return;
    setSaving(true);
    setSaveStatus('saving');
    try {
      await apicall('PUT', `/api/workspace/documents/${doc.id}`, token, {
        content: { columns: colsToSave, rows: rowsToSave, formatting: fmtToSave },
      });
      setSaveStatus('saved');
      if (onUpdated) onUpdated();
    } catch {
      toast.error('Gagal auto-save');
      setSaveStatus('pending');
    } finally {
      setSaving(false);
    }
  }, [doc, token, onUpdated, isReadOnly]);

  const queueSave = useCallback((r, c, f) => {
    setSaveStatus('pending');
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => handleSave(r, c, f), 2000);
  }, [handleSave]);

  const manualSave = async () => {
    clearTimeout(saveTimerRef.current);
    await handleSave(rows, columns, formatting);
    // Save version snapshot
    try {
      await apicall('POST', `/api/workspace/documents/${doc.id}/versions`, token, {
        content: { columns, rows, formatting },
      });
    } catch { /* non-critical */ }
  };

  // ── Rows ──
  const handleRowsChange = (newRows) => {
    if (isReadOnly) return;
    setRows(newRows);
    queueSave(newRows, columns, formatting);
  };

  const handleAddRow = () => {
    if (isReadOnly) return;
    const newRow = { id: `row_${Date.now()}` };
    columns.forEach((col) => { newRow[col.key] = ''; });
    const newRows = [...rows, newRow];
    setRows(newRows);
    queueSave(newRows, columns, formatting);
  };

  const handleDeleteSelected = () => {
    if (isReadOnly || selectedRows.size === 0) return;
    if (!window.confirm(`Hapus ${selectedRows.size} baris?`)) return;
    const newRows = rows.filter((r) => !selectedRows.has(r.id));
    setRows(newRows);
    setSelectedRows(new Set());
    queueSave(newRows, columns, formatting);
    toast.success(`${selectedRows.size} baris dihapus`);
  };

  // ── Columns ──
  const handleAddColumn = (colDef) => {
    if (isReadOnly) return;
    const newCols = [...columns, colDef];
    const newRows = rows.map((r) => ({ ...r, [colDef.key]: '' }));
    setColumns(newCols);
    setRows(newRows);
    queueSave(newRows, newCols, formatting);
    toast.success(`Kolom "${colDef.name}" ditambahkan`);
  };

  const handleDeleteColumn = (key) => {
    if (isReadOnly) return;
    const newCols = columns.filter((c) => c.key !== key);
    const newRows = rows.map((r) => { const nr = { ...r }; delete nr[key]; return nr; });
    const newFmt = Object.fromEntries(
      Object.entries(formatting).filter(([k]) => !k.includes(`:${key}`))
    );
    setColumns(newCols);
    setRows(newRows);
    setFormatting(newFmt);
    queueSave(newRows, newCols, newFmt);
  };

  // ── Cell Formatting ──
  const handleFormat = (fmtKey, fmtVal) => {
    const newFmt = { ...formatting, [fmtKey]: fmtVal };
    setFormatting(newFmt);
    queueSave(rows, columns, newFmt);
  };

  // ── Cell update (from formula bar) ──
  const handleUpdateCell = (rowId, colKey, val) => {
    const newRows = rows.map((r) => r.id === rowId ? { ...r, [colKey]: val } : r);
    setRows(newRows);
    queueSave(newRows, columns, formatting);
  };

  // ── Rename ──
  const startRename = () => {
    if (canEdit(doc?.access_level)) {
      setNewName(doc.name);
      setRenaming(true);
    }
  };

  const commitRename = async () => {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === doc.name) { setRenaming(false); return; }
    try {
      await apicall('PUT', `/api/workspace/documents/${doc.id}`, token, { name: trimmed });
      setDoc((prev) => ({ ...prev, name: trimmed }));
      if (onUpdated) onUpdated();
      toast.success('Nama diperbarui');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setRenaming(false);
    }
  };

  // ── Export Excel ──
  const handleExportExcel = async () => {
    setExporting(true);
    try {
      const response = await fetch(`${API}/api/workspace/documents/${doc.id}/export-excel`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Export gagal');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = window.document.createElement('a');
      a.href = url;
      a.download = `${doc.name.replace(/ /g, '_')}.xlsx`;
      window.document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      window.document.body.removeChild(a);
      toast.success('File Excel berhasil didownload');
    } catch {
      toast.error('Gagal export Excel');
    } finally {
      setExporting(false);
    }
  };

  // ── Build DataGrid columns (memoized) ──
  const gridColumns = useMemo(() => [
    ...(!isReadOnly ? [SelectColumn] : []),
    ...columns.map((col) => ({
      key: col.key,
      name: col.name,
      editable: !isReadOnly,
      resizable: true,
      width: col.width || 150,
      renderCell: ({ row, column }) => {
        const rawVal = row[column.key];
        const fmtKey = `${row.id}:${column.key}`;
        const fmt = formatting[fmtKey] || {};
        const displayVal = typeof rawVal === 'string' && rawVal.startsWith('=')
          ? evaluateFormula(rawVal, rows, column.key)
          : rawVal;
        const isSelected = selectedCell?.rowId === row.id && selectedCell?.colKey === column.key;
        return (
          <div
            style={{
              fontWeight: fmt.bold ? 'bold' : 'normal',
              fontStyle: fmt.italic ? 'italic' : 'normal',
              color: fmt.color || undefined,
              backgroundColor: fmt.bgColor || undefined,
              textAlign: fmt.align || 'left',
              width: '100%', height: '100%',
              padding: '0 8px',
              display: 'flex', alignItems: 'center',
              outline: isSelected ? '2px solid hsl(var(--primary))' : 'none',
            }}
            onClick={() => setSelectedCell({ rowId: row.id, colKey: column.key, rawVal })}
          >
            {String(displayVal ?? '')}
          </div>
        );
      },
    })),
  ], [columns, formatting, selectedCell, rows, isReadOnly]);

  const saveIndicator = isReadOnly ? null : (
    <span className="text-xs flex items-center gap-1" data-testid="save-status">
      {saveStatus === 'saving' && <><Loader2 size={11} className="animate-spin" /><span className="text-muted-foreground">Menyimpan...</span></>}
      {saveStatus === 'pending' && <><AlertCircle size={11} className="text-amber-500" /><span className="text-amber-600">Belum disimpan</span></>}
      {saveStatus === 'saved' && <><Check size={11} className="text-emerald-500" /><span className="text-muted-foreground">Tersimpan</span></>}
    </span>
  );

  return (
    <div className="flex flex-col h-full" data-testid="grid-editor-view">
      {/* Header */}
      <div className="border-b bg-card px-4 py-3 shrink-0">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2 min-w-0">
            <Button variant="ghost" size="sm" onClick={onBack} className="shrink-0" data-testid="back-btn">
              <ChevronRight size={16} className="rotate-180" />
            </Button>
            {renaming ? (
              <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenaming(false); }}
                onBlur={commitRename} autoFocus
                className="h-7 text-sm font-semibold w-64" data-testid="rename-input" />
            ) : (
              <div className="flex items-center gap-1.5 min-w-0">
                <h2 className="text-base font-semibold truncate" data-testid="doc-title">{doc?.name}</h2>
                {canEdit(doc?.access_level) && (
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0 shrink-0"
                    onClick={startRename} data-testid="rename-btn"><Edit3 size={12} /></Button>
                )}
              </div>
            )}
            <AccessBadge level={doc?.access_level} />
          </div>
          <div className="flex gap-2 shrink-0">
            {isReadOnly && (
              <span className="flex items-center gap-1 text-xs text-amber-600 border border-amber-200 bg-amber-50 px-2 py-1 rounded-md">
                <Lock size={12} />Hanya Lihat
              </span>
            )}
            {saveIndicator}
            {canShare(doc?.access_level) && (
              <Button variant="outline" size="sm" onClick={() => setShowShare(true)} data-testid="share-btn">
                <Share2 size={14} className="mr-1" />Share
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={handleExportExcel} disabled={exporting} data-testid="export-excel-btn">
              {exporting ? <Loader2 size={14} className="animate-spin mr-1" /> : <Download size={14} className="mr-1" />}
              Excel
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowVersions(true)} data-testid="version-history-btn">
              <History size={14} className="mr-1" />Versi
            </Button>
          </div>
        </div>

        {/* Edit Toolbar */}
        {!isReadOnly && (
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" onClick={manualSave} disabled={saving || saveStatus === 'saved'} data-testid="manual-save-btn">
              {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />}
              {saving ? 'Menyimpan...' : 'Simpan'}
            </Button>
            <Button size="sm" variant="outline" onClick={handleAddRow} data-testid="add-row-btn">
              <Plus size={14} className="mr-1" />Baris Baru
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowManageCols(true)} data-testid="manage-cols-btn">
              <Columns size={14} className="mr-1" />Kolom
            </Button>
            {selectedRows.size > 0 && (
              <Button size="sm" variant="destructive" onClick={handleDeleteSelected} data-testid="delete-rows-btn">
                <Trash2 size={14} className="mr-1" />Hapus {selectedRows.size} Baris
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Formula Bar */}
      <FormulaBar selectedCell={selectedCell} rows={rows} onUpdateCell={handleUpdateCell} readOnly={isReadOnly} />

      {/* Formatting Toolbar */}
      <FormattingToolbar selectedCell={selectedCell} formatting={formatting} onFormat={handleFormat} readOnly={isReadOnly} />

      {/* Grid */}
      <div className="flex-1 overflow-hidden">
        {gridColumns.length === 0 && !isReadOnly ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <Columns size={40} className="opacity-30" />
            <p className="text-sm">Belum ada kolom.</p>
            <Button size="sm" variant="outline" onClick={() => setShowManageCols(true)}>
              <Plus size={14} className="mr-1" />Tambah Kolom
            </Button>
          </div>
        ) : (
          <DataGrid
            columns={gridColumns}
            rows={rows}
            rowKeyGetter={(row) => row.id}
            onRowsChange={handleRowsChange}
            selectedRows={selectedRows}
            onSelectedRowsChange={setSelectedRows}
            className="h-full"
            style={{
              '--rdg-background-color': 'hsl(var(--background))',
              '--rdg-header-background-color': 'hsl(var(--muted))',
              '--rdg-row-hover-background-color': 'hsl(var(--accent))',
              '--rdg-border-color': 'hsl(var(--border))',
              '--rdg-color': 'hsl(var(--foreground))',
              '--rdg-selection-color': 'hsl(var(--primary))',
              height: '100%',
            }}
            data-testid="data-grid"
          />
        )}
      </div>

      {/* Footer */}
      <div className="border-t bg-card px-4 py-2 shrink-0 flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {rows.length} baris · {columns.length} kolom
          {selectedRows.size > 0 && ` · ${selectedRows.size} dipilih`}
        </p>
        {isReadOnly && (
          <p className="text-xs text-amber-500 flex items-center gap-1">
            <Lock size={11} />Mode baca saja
          </p>
        )}
      </div>

      {/* Dialogs */}
      <ShareDialog open={showShare} onClose={() => setShowShare(false)} document={doc} token={token}
        onShared={(u) => setDoc((prev) => ({ ...prev, ...u }))} />
      <ManageColumnsDialog open={showManageCols} onClose={() => setShowManageCols(false)}
        columns={columns} onDelete={handleDeleteColumn} onAdd={handleAddColumn} />
      <VersionHistoryDrawer open={showVersions} onClose={() => setShowVersions(false)}
        docId={doc?.id} token={token}
        onRestored={async () => {
          const updated = await apicall('GET', `/api/workspace/documents/${doc.id}`, token);
          setDoc(updated);
          setColumns(updated.content?.columns || []);
          setRows(updated.content?.rows || []);
          setFormatting(updated.content?.formatting || {});
          setSaveStatus('saved');
        }}
      />
    </div>
  );
}
