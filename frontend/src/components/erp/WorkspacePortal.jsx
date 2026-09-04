/**
 * WorkspacePortal — thin orchestrator shell.
 *
 * [REFACTORED 2026-05-24 Session #10] was 1364 LOC monolith → now ~180 LOC shell.
 *
 * All UI pieces live in `./workspace-portal/*`:
 *   utils.js, AccessBadge, ShareDialog, ColumnsDialog (AddColumnDialog + ManageColumnsDialog),
 *   ImportExcelDialog, ImportFromModuleDialog, VersionHistoryDrawer,
 *   FormulaBar, FormattingToolbar, DocCard, NewDocForm, GridEditorView.
 *
 * External API (props) UNCHANGED: { token, user }
 * Default export name UNCHANGED: WorkspacePortal
 *
 * Consumed by: CollaborationPortal, WorkspaceTab, StudyGroupDetail, moduleRegistry (lazy).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  FileSpreadsheet, Plus, Search, Users, RefreshCw,
  Package, Upload, Loader2,
} from 'lucide-react';

import {
  API, apicall, canShare,
} from './workspace-portal/utils';
import DocCard from './workspace-portal/DocCard';
import NewDocForm from './workspace-portal/NewDocForm';
import ShareDialog from './workspace-portal/ShareDialog';
import ImportExcelDialog from './workspace-portal/ImportExcelDialog';
import ImportFromModuleDialog from './workspace-portal/ImportFromModuleDialog';
import GridEditorView from './workspace-portal/GridEditorView';

export default function WorkspacePortal({ token /*, user */ }) {
  const [documents, setDocuments] = useState({ owned: [], shared: [] });
  const [loading, setLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showNewDoc, setShowNewDoc] = useState(false);
  const [showImportExcel, setShowImportExcel] = useState(false);
  const [showImportModule, setShowImportModule] = useState(false);
  const [shareTarget, setShareTarget] = useState(null);
  const [importingExcel, setImportingExcel] = useState(false);
  const fileInputRef = useRef(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apicall('GET', '/api/workspace/documents', token);
      setDocuments(data);
    } catch {
      toast.error('Gagal memuat dokumen');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadDocuments(); }, [loadDocuments]);

  const handleDocOpen = async (docId) => {
    try {
      const doc = await apicall('GET', `/api/workspace/documents/${docId}`, token);
      setSelectedDoc(doc);
    } catch (e) {
      toast.error(e.message || 'Gagal membuka dokumen');
    }
  };

  const handleDocDelete = async (docId, docName) => {
    if (!window.confirm(`Hapus "${docName}"?`)) return;
    try {
      await apicall('DELETE', `/api/workspace/documents/${docId}`, token);
      toast.success('Dokumen dihapus');
      loadDocuments();
    } catch (e) {
      toast.error(e.message);
    }
  };

  // Quick Excel import (old 1-step, kept for quick action)
  const handleQuickExcelImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.match(/\.xlsx?$/i)) { toast.error('File harus .xlsx atau .xls'); return; }
    setImportingExcel(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API}/api/workspace/documents/import-excel`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const doc = await res.json();
      if (!res.ok) throw new Error(doc.detail || 'Import gagal');
      toast.success(`Excel berhasil diimport: "${doc.name}"`);
      loadDocuments();
      setSelectedDoc(doc);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setImportingExcel(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const filteredOwned = documents.owned.filter((d) =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const filteredShared = documents.shared.filter((d) =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Editor view (when a doc is selected)
  if (selectedDoc) {
    return (
      <GridEditorView
        document={selectedDoc}
        token={token}
        onBack={() => setSelectedDoc(null)}
        onUpdated={loadDocuments}
      />
    );
  }

  // Index view
  return (
    <div
      className="h-full flex flex-col bg-gradient-to-br from-background via-background to-muted/20"
      data-testid="workspace-portal"
    >
      {/* Header */}
      <div className="border-b bg-card/50 backdrop-blur-sm shrink-0">
        <div className="p-6 pb-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold">Workspace Spreadsheet</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Kelola dokumen & editor spreadsheet kolaboratif
              </p>
            </div>
            <Button onClick={() => setShowNewDoc(true)} data-testid="new-doc-btn">
              <Plus size={16} className="mr-1" />Spreadsheet Baru
            </Button>
          </div>
          <div className="relative max-w-md">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Cari dokumen..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
              data-testid="doc-search"
            />
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-6">
          {loading ? (
            <div className="text-center py-12">
              <Loader2 size={32} className="animate-spin mx-auto text-muted-foreground" />
              <p className="text-sm text-muted-foreground mt-2">Memuat dokumen...</p>
            </div>
          ) : (
            <>
              {/* Quick Actions */}
              <div className="grid grid-cols-3 gap-4">
                <Card className="cursor-pointer hover:bg-accent/50 hover:shadow-md transition-all border-dashed"
                  onClick={() => setShowNewDoc(true)} data-testid="quick-new-spreadsheet">
                  <CardContent className="p-5 text-center">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mx-auto mb-2">
                      <Plus size={20} className="text-primary" />
                    </div>
                    <p className="text-sm font-medium">Spreadsheet Baru</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Mulai dari kosong</p>
                  </CardContent>
                </Card>

                <Card className="cursor-pointer hover:bg-accent/50 hover:shadow-md transition-all border-dashed"
                  onClick={() => setShowImportExcel(true)} data-testid="quick-import-excel">
                  <CardContent className="p-5 text-center">
                    <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center mx-auto mb-2">
                      {importingExcel
                        ? <Loader2 size={20} className="text-emerald-600 animate-spin" />
                        : <Upload size={20} className="text-emerald-600" />}
                    </div>
                    <p className="text-sm font-medium">Import Excel</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Preview + mapping kolom</p>
                  </CardContent>
                </Card>
                <input type="file" ref={fileInputRef} onChange={handleQuickExcelImport}
                  accept=".xlsx,.xls" className="hidden" />

                <Card className="cursor-pointer hover:bg-accent/50 hover:shadow-md transition-all border-dashed"
                  onClick={() => setShowImportModule(true)} data-testid="quick-import-module">
                  <CardContent className="p-5 text-center">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center mx-auto mb-2">
                      <Package size={20} className="text-blue-600" />
                    </div>
                    <p className="text-sm font-medium">Import dari Modul</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Aset, Pengadaan</p>
                  </CardContent>
                </Card>
              </div>

              {/* My Documents */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-base font-semibold flex items-center gap-2">
                    <FileSpreadsheet size={17} className="text-primary" />
                    Dokumen Saya
                    <Badge variant="secondary" className="text-xs">{filteredOwned.length}</Badge>
                  </h2>
                  <Button variant="ghost" size="sm" onClick={loadDocuments} className="h-7">
                    <RefreshCw size={13} />
                  </Button>
                </div>
                {filteredOwned.length === 0 ? (
                  <Card>
                    <CardContent className="p-10 text-center">
                      <FileSpreadsheet size={40} className="mx-auto text-muted-foreground/30 mb-3" />
                      <p className="text-sm text-muted-foreground">
                        {searchQuery ? 'Tidak ada dokumen yang cocok' : 'Belum ada dokumen.'}
                      </p>
                      {!searchQuery && (
                        <Button size="sm" variant="outline" className="mt-3" onClick={() => setShowNewDoc(true)}>
                          <Plus size={13} className="mr-1" />Buat Sekarang
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                ) : (
                  <div className="grid gap-2.5">
                    {filteredOwned.map((doc) => (
                      <DocCard
                        key={doc.id}
                        doc={doc}
                        onOpen={handleDocOpen}
                        onDelete={handleDocDelete}
                        onShare={() => setShareTarget(doc)}
                        showDelete
                        showShare
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Shared with Me */}
              {filteredShared.length > 0 && (
                <div>
                  <h2 className="text-base font-semibold mb-3 flex items-center gap-2">
                    <Users size={17} className="text-blue-600" />Dibagikan ke Saya
                    <Badge variant="secondary" className="text-xs">{filteredShared.length}</Badge>
                  </h2>
                  <div className="grid gap-2.5">
                    {filteredShared.map((doc) => (
                      <DocCard
                        key={doc.id}
                        doc={doc}
                        onOpen={handleDocOpen}
                        onDelete={handleDocDelete}
                        onShare={() => setShareTarget(doc)}
                        showDelete={doc.is_owner}
                        showShare={canShare(doc.access_level)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </ScrollArea>

      {/* Dialogs */}
      <Dialog open={showNewDoc} onOpenChange={(v) => !v && setShowNewDoc(false)}>
        <DialogContent className="sm:max-w-sm" data-testid="new-doc-dialog">
          <DialogHeader><DialogTitle>Spreadsheet Baru</DialogTitle></DialogHeader>
          <NewDocForm
            token={token}
            onCreated={(doc) => { loadDocuments(); setSelectedDoc(doc); setShowNewDoc(false); }}
            onClose={() => setShowNewDoc(false)}
          />
        </DialogContent>
      </Dialog>

      <ImportExcelDialog
        open={showImportExcel}
        onClose={() => setShowImportExcel(false)}
        token={token}
        onImported={(doc) => { loadDocuments(); setSelectedDoc(doc); }}
      />
      <ImportFromModuleDialog
        open={showImportModule}
        onClose={() => setShowImportModule(false)}
        token={token}
        onImported={(doc) => { loadDocuments(); setSelectedDoc(doc); }}
      />
      <ShareDialog
        open={!!shareTarget}
        onClose={() => setShareTarget(null)}
        document={shareTarget}
        token={token}
        onShared={() => loadDocuments()}
      />
    </div>
  );
}
