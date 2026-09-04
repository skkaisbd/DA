import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { FileText, Upload, Trash2, FileCheck, AlertTriangle, Loader2, Download, Calendar } from 'lucide-react';
import { IconButton } from '../IconButton';

const DOC_TYPE_LABEL = {
  ktp: 'KTP',
  ijazah: 'Ijazah',
  sertifikat: 'Sertifikat',
  kontrak: 'Kontrak Kerja',
  other: 'Lainnya',
};

const DOC_TYPE_COLOR = {
  ktp: '#3b82f6',
  ijazah: '#10b981',
  sertifikat: '#f59e0b',
  kontrak: '#ef4444',
  other: '#64748b',
};

export default function MyDocumentsModule({ token }) {
  const [documents, setDocuments] = useState([]);
  const [hrDocuments, setHrDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [formData, setFormData] = useState({ title: '', doc_type: 'other', description: '', file_url: '', file_name: '', expiry_date: '' });

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token]);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/documents`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setDocuments(data?.data?.my_documents || []);
      setHrDocuments(data?.data?.hr_issued || []);
    } catch (e) {
      toast.error(`Gagal memuat dokumen: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  const handleUpload = async () => {
    if (!formData.title) {
      toast.error('Judul dokumen harus diisi');
      return;
    }
    setUploading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/documents`, {
        method: 'POST',
        headers,
        body: JSON.stringify(formData),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Dokumen berhasil diupload!');
      setShowUploadDialog(false);
      setFormData({ title: '', doc_type: 'other', description: '', file_url: '', file_name: '', expiry_date: '' });
      fetchDocuments();
    } catch (e) {
      toast.error(`Upload gagal: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId) => {
    if (!confirm('Hapus dokumen ini?')) return;
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/documents/${docId}`, {
        method: 'DELETE',
        headers,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      toast.success('Dokumen dihapus');
      fetchDocuments();
    } catch (e) {
      toast.error(`Hapus gagal: ${e.message}`);
    }
  };

  const isExpiringSoon = (expiryDate) => {
    if (!expiryDate) return false;
    const exp = new Date(expiryDate);
    const now = new Date();
    const diffDays = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
    return diffDays >= 0 && diffDays <= 30;
  };

  const isExpired = (expiryDate) => {
    if (!expiryDate) return false;
    return new Date(expiryDate) < new Date();
  };

  return (
    <div className="space-y-6 p-6" data-testid="my-documents-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <FileText className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Dokumen Saya</h1>
            <p className="text-sm text-muted-foreground">Kelola dokumen personal dan lihat dokumen dari HR</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <IconButton icon={Upload} onClick={fetchDocuments} disabled={loading} tooltip="Refresh" />
          <Button onClick={() => setShowUploadDialog(true)}>
            <Upload className="w-4 h-4 mr-2" /> Upload Dokumen
          </Button>
        </div>
      </div>

      {/* My Documents */}
      <GlassCard className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            <h2 className="text-lg font-semibold text-foreground">Dokumen Pribadi</h2>
          </div>
          <Badge variant="outline">{documents.length} dokumen</Badge>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center">
            <FileText className="w-12 h-12 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">Belum ada dokumen yang diupload</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {documents.map(doc => {
              const docColor = DOC_TYPE_COLOR[doc.doc_type] || DOC_TYPE_COLOR.other;
              const expiringSoon = isExpiringSoon(doc.expiry_date);
              const expired = isExpired(doc.expiry_date);
              return (
                <div key={doc.id} className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)] transition-colors">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FileText className="w-4 h-4 shrink-0" style={{ color: docColor }} />
                        <h3 className="text-sm font-semibold text-foreground truncate">{doc.title}</h3>
                      </div>
                      <Badge variant="outline" style={{ borderColor: docColor, color: docColor }} className="text-xs">
                        {DOC_TYPE_LABEL[doc.doc_type] || doc.doc_type}
                      </Badge>
                    </div>
                    <IconButton icon={Trash2} variant="ghost" size="sm" onClick={() => handleDelete(doc.id)} tooltip="Hapus" />
                  </div>
                  {doc.description && <p className="text-xs text-muted-foreground mb-2">{doc.description}</p>}
                  {doc.file_name && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                      <FileCheck className="w-3 h-3" />
                      <span className="truncate">{doc.file_name}</span>
                    </div>
                  )}
                  {doc.expiry_date && (
                    <div className="flex items-center gap-2 text-xs">
                      <Calendar className="w-3 h-3" />
                      <span className={expired ? 'text-red-500 font-medium' : expiringSoon ? 'text-amber-500 font-medium' : 'text-muted-foreground'}>
                        Berlaku s/d: {new Date(doc.expiry_date).toLocaleDateString('id-ID')}
                      </span>
                      {expired && <Badge variant="destructive" className="text-xs">Expired</Badge>}
                      {expiringSoon && !expired && <Badge variant="outline" className="text-xs border-amber-500 text-amber-500">Segera Habis</Badge>}
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground mt-2">
                    Upload: {new Date(doc.created_at).toLocaleDateString('id-ID')}
                  </div>
                  {doc.file_url && (
                    <Button variant="outline" size="sm" className="w-full mt-3" onClick={() => window.open(doc.file_url, '_blank')}>
                      <Download className="w-3 h-3 mr-2" /> Download
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>

      {/* HR Issued Documents */}
      {hrDocuments.length > 0 && (
        <GlassCard className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-emerald-500" />
              <h2 className="text-lg font-semibold text-foreground">Dokumen dari HR</h2>
            </div>
            <Badge variant="outline">{hrDocuments.length} dokumen</Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {hrDocuments.map(doc => (
              <div key={doc.id} className="p-4 rounded-lg bg-[var(--glass)] border border-emerald-300 dark:border-emerald-500/20">
                <div className="flex items-start gap-3 mb-2">
                  <FileCheck className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-foreground">{doc.title || doc.document_type}</h3>
                    <p className="text-xs text-muted-foreground">Diterbitkan: {new Date(doc.issued_at).toLocaleDateString('id-ID')}</p>
                  </div>
                </div>
                {doc.file_url && (
                  <Button variant="outline" size="sm" className="w-full" onClick={() => window.open(doc.file_url, '_blank')}>
                    <Download className="w-3 h-3 mr-2" /> Download
                  </Button>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Upload Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Dokumen Baru</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Judul Dokumen *</Label>
              <Input placeholder="Misal: KTP Asli" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} />
            </div>
            <div>
              <Label>Tipe Dokumen</Label>
              <Select value={formData.doc_type} onValueChange={v => setFormData({ ...formData, doc_type: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(DOC_TYPE_LABEL).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Deskripsi (Opsional)</Label>
              <Textarea placeholder="Catatan tambahan..." value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} rows={2} />
            </div>
            <div>
              <Label>URL File (Opsional)</Label>
              <Input placeholder="https://..." value={formData.file_url} onChange={e => setFormData({ ...formData, file_url: e.target.value })} />
            </div>
            <div>
              <Label>Nama File (Opsional)</Label>
              <Input placeholder="dokumen.pdf" value={formData.file_name} onChange={e => setFormData({ ...formData, file_name: e.target.value })} />
            </div>
            <div>
              <Label>Tanggal Kadaluarsa (Opsional)</Label>
              <Input type="date" value={formData.expiry_date} onChange={e => setFormData({ ...formData, expiry_date: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUploadDialog(false)}>Batal</Button>
            <Button onClick={handleUpload} disabled={uploading}>
              {uploading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Menyimpan...</> : <><Upload className="w-4 h-4 mr-2" /> Upload</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
