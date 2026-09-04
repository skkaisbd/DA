
import { useState, useEffect, useRef } from 'react';
import { Paperclip, Upload, Trash2, Download, File, FileImage, FileSpreadsheet, Archive } from 'lucide-react';
import { apiGet, apiPost, apiDelete } from '../../../lib/api';

function getFileIcon(ext) {
  if (['jpg','jpeg','png','webp','gif'].includes(ext)) return <FileImage className="w-4 h-4 text-blue-500" />;
  if (['xlsx','xls','csv'].includes(ext)) return <FileSpreadsheet className="w-4 h-4 text-emerald-600" />;
  if (['zip','rar'].includes(ext)) return <Archive className="w-4 h-4 text-amber-600" />;
  return <File className="w-4 h-4 text-muted-foreground" />;
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export default function FileAttachmentPanel({ token, entityType, entityId, userRole }) {
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef();

  const isSuperAdmin = userRole === 'superadmin';

  useEffect(() => {
    if (entityId) fetchAttachments();
  }, [entityId]);

  const fetchAttachments = async () => {
    try {
      const data = await apiGet(`/attachments?entity_type=${entityType}&entity_id=${entityId}`);
      setAttachments(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); setAttachments([]); }
  };

  const uploadFile = async (file) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity_type', entityType);
    formData.append('entity_id', entityId);
    try {
      const data = await apiPost('/upload', formData);
      setAttachments(prev => [...prev, data]);
    } catch (e) {
      alert('Upload gagal: ' + e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach(uploadFile);
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files || []);
    files.forEach(uploadFile);
  };

  const handleDelete = async (att) => {
    if (!confirm(`Hapus file "${att.original_name}"?`)) return;
    try {
      await apiDelete(`/upload?id=${att.id}`);
      setAttachments(prev => prev.filter(a => a.id !== att.id));
    } catch (e) {
      alert(e.message || 'Gagal menghapus');
    }
  };

  if (!entityId) {
    return (
      <div className="border border-dashed border-border rounded-lg p-4 text-center text-sm text-muted-foreground/70">
        Simpan record terlebih dahulu untuk menambahkan lampiran.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground/90 flex items-center gap-2">
          <Paperclip className="w-4 h-4" /> Lampiran ({attachments.length})
        </h4>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Upload className="w-3.5 h-3.5" />
          {uploading ? 'Mengupload...' : 'Upload File'}
        </button>
        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileChange}
          accept=".pdf,.jpg,.jpeg,.png,.webp,.xlsx,.xls,.zip" />
      </div>

      <div
        className={`border-2 border-dashed rounded-lg p-3 text-center text-xs transition-colors ${
          dragOver ? 'border-blue-400 bg-blue-50' : 'border-border bg-muted/40'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <Upload className="w-4 h-4 mx-auto mb-1 text-muted-foreground/70" />
        <span className="text-muted-foreground/70">Drag & drop file di sini atau klik tombol Upload</span>
        <br />
        <span className="text-muted-foreground/50">PDF, JPG, PNG, XLSX, ZIP — maks. 10MB</span>
      </div>

      {attachments.length > 0 && (
        <div className="space-y-1.5">
          {attachments.map(att => (
            <div key={att.id} className="flex items-center gap-2 p-2 bg-card border border-border rounded-lg">
              {getFileIcon(att.file_ext)}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-foreground/90 truncate">{att.original_name}</p>
                <p className="text-xs text-muted-foreground/70">{formatSize(att.size)} • {new Date(att.uploaded_at).toLocaleDateString('id-ID')} • {att.uploaded_by}</p>
              </div>
              <a
                href={att.public_path}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1 rounded hover:bg-blue-50 text-blue-500"
                title="Download"
              >
                <Download className="w-3.5 h-3.5" />
              </a>
              <button
                type="button"
                onClick={() => handleDelete(att)}
                className="p-1 rounded hover:bg-red-50 text-red-400"
                title="Hapus"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
