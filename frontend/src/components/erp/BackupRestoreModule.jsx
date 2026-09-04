import { useState, useEffect, useCallback } from 'react';
import { Database, Download, Trash2, RefreshCw, AlertTriangle, CheckCircle2, Clock, HardDrive, Calendar, FileUp, CheckSquare, Square } from 'lucide-react';
import { GlassCard } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { PageHeader, StatTile } from './moduleAtoms';
import { useToast } from '@/hooks/use-toast';
import { downloadBackup, uploadBackup, listCollections, restoreSelective } from './backupRestoreHelpers';
import DatabaseCollectionsPanel from './DatabaseCollectionsPanel';
import { formatRupiah } from '@/lib/format';

const fmt = formatRupiah;
const formatDate = (isoStr) => {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  return d.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
};

export default function BackupRestoreModule({ token }) {
  const [backups, setBackups] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(null);
  const [restoreTarget, setRestoreTarget] = useState(null);
  // Rincian kegagalan restore (sebab + saran + log) — ditampilkan di dialog,
  // bukan cuma toast, supaya user tahu APA yang salah dan APA yang harus dilakukan.
  const [restoreError, setRestoreError] = useState(null);
  const [selectiveRestore, setSelectiveRestore] = useState(null);
  const [collections, setCollections] = useState([]);
  const [selectedCollections, setSelectedCollections] = useState([]);
  const [restoreMode, setRestoreMode] = useState('overwrite');
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState(null);
  // Tautan unduh manual — jaring pengaman kalau browser memblokir unduhan
  // otomatis (preview berjalan di dalam iframe).
  const [downloadHint, setDownloadHint] = useState(null);
  const [tab, setTab] = useState('backup');
  const { toast } = useToast();
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchBackups = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/admin/backup/list', { headers });
      if (r.ok) {
        const data = await r.json();
        setBackups(data.backups || []);
      } else {
        toast({ title: 'Error', description: 'Gagal memuat daftar backup', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal memuat data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const fetchConfig = useCallback(async () => {
    try {
      const r = await fetch('/api/admin/backup/config', { headers });
      if (r.ok) setConfig(await r.json());
    } catch (e) {
      // Silent fail
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    fetchBackups();
    fetchConfig();
  }, [fetchBackups, fetchConfig]);

  const createBackup = async () => {
    setProcessing('create');
    try {
      const r = await fetch('/api/admin/backup/create', {
        method: 'POST',
        headers,
        body: JSON.stringify({ notify: true })
      });
      if (r.ok) {
        const data = await r.json();
        toast({
          title: 'Backup Dimulai',
          description: `Backup '${data.backup_name}' sedang diproses di background. Anda akan menerima notifikasi saat selesai.`
        });
        setTimeout(fetchBackups, 3000); // Refresh after 3 seconds
      } else {
        const err = await r.json();
        toast({ title: 'Error', description: err.detail || 'Gagal membuat backup', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal membuat backup', variant: 'destructive' });
    } finally {
      setProcessing(null);
    }
  };

  const restoreBackup = async () => {
    if (!restoreTarget) return;
    setProcessing('restore');
    setRestoreError(null);
    try {
      const r = await fetch('/api/admin/backup/restore', {
        method: 'POST',
        headers,
        body: JSON.stringify({ backup_id: restoreTarget.backup_id, confirm: true })
      });
      if (r.ok) {
        toast({
          title: 'Restore Berhasil',
          description: `Database berhasil di-restore dari '${restoreTarget.backup_name}'. Halaman akan di-reload...`
        });
        setRestoreTarget(null);
        setTimeout(() => window.location.reload(), 2000);
        return;
      }
      // GAGAL — backend mengirim detail terstruktur:
      // { message, reason, hint, returncode, log_lines[], log_path }
      // (dulu hanya "Restore failed: " tanpa sebab apa pun).
      let info = {};
      try {
        const body = await r.json();
        const d = body?.detail;
        info = typeof d === 'string' ? { reason: d } : (d || {});
      } catch (parseErr) {
        info = { reason: `Server mengirim respons yang tidak bisa dibaca (${parseErr?.message || 'gagal parse JSON'}).` };
      }
      const err = {
        message: info.message || `Restore gagal (HTTP ${r.status})`,
        reason: info.reason || 'Server tidak mengirim rincian sebab kegagalan.',
        hint: info.hint || '',
        returncode: info.returncode ?? null,
        logLines: Array.isArray(info.log_lines) ? info.log_lines : [],
        logPath: info.log_path || ''
      };
      setRestoreError(err);
      toast({ title: 'Restore Gagal', description: err.reason, variant: 'destructive' });
    } catch (e) {
      const err = {
        message: 'Restore gagal',
        reason: `Tidak bisa menghubungi server: ${e?.message || e}`,
        hint: 'Periksa status backend (sudo supervisorctl status backend) lalu coba lagi.',
        returncode: null,
        logLines: [],
        logPath: ''
      };
      setRestoreError(err);
      toast({ title: 'Restore Gagal', description: err.reason, variant: 'destructive' });
    } finally {
      setProcessing(null);
      // Dialog SENGAJA dibiarkan terbuka saat gagal agar rincian sebab terbaca.
    }
  };

  const deleteBackup = async (backup) => {
    if (!window.confirm(`Hapus backup '${backup.backup_name}'?`)) return;
    setProcessing(backup.backup_id);
    try {
      const r = await fetch(`/api/admin/backup/${backup.backup_id}`, {
        method: 'DELETE',
        headers
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: `Backup '${backup.backup_name}' berhasil dihapus` });
        fetchBackups();
      } else {
        toast({ title: 'Error', description: 'Gagal menghapus backup', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Gagal menghapus backup', variant: 'destructive' });
    } finally {
      setProcessing(null);
    }
  };

  const cleanup = async () => {
    if (!window.confirm(`Hapus semua backup yang lebih lama dari ${config?.retention_days || 30} hari?`)) return;
    setProcessing('cleanup');
    try {
      const r = await fetch('/api/admin/backup/cleanup', {
        method: 'POST',
        headers
      });
      if (r.ok) {
        toast({ title: 'Sukses', description: 'Cleanup berhasil' });
        fetchBackups();
      } else {
        toast({ title: 'Error', description: 'Cleanup gagal', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Error', description: 'Cleanup gagal', variant: 'destructive' });
    } finally {
      setProcessing(null);
    }
  };

  const handleDownload = async (backup) => {
    setProcessing(backup.backup_id);
    setDownloadHint(null);
    toast({ title: 'Menyiapkan unduhan...', description: `${backup.backup_name}.zip` });
    const result = await downloadBackup(backup.backup_id, token);
    setProcessing(null);
    if (result.ok) {
      // Preview dijalankan di dalam iframe; unduhan otomatis BISA diblokir browser.
      // Karena itu tautan langsung selalu ditampilkan sebagai jalan pasti.
      if (result.url) {
        setDownloadHint({ name: `${backup.backup_id}.zip`, url: result.url });
        toast({
          title: 'Unduhan dimulai di tab baru',
          description: 'Jika tab tidak terbuka, klik tautan "Unduh manual" yang muncul di bawah judul.',
        });
      } else {
        toast({ title: 'Sukses', description: 'Backup berhasil diunduh' });
      }
    } else {
      if (result.url) setDownloadHint({ name: `${backup.backup_id}.zip`, url: result.url });
      toast({ title: 'Error', description: result.error || 'Download gagal', variant: 'destructive' });
    }
  };

  // Unggah LANGSUNG jalan saat berkas dipilih (dulu perlu klik tombol kedua yang
  // sering terlewat) + progress persen + input di-reset supaya memilih berkas
  // yang SAMA dua kali tetap memicu unggahan.
  const handleUpload = async (file) => {
    if (!file) {
      toast({ title: 'Error', description: 'Pilih file ZIP terlebih dahulu', variant: 'destructive' });
      return;
    }
    setUploadFile(file);
    setProcessing('upload');
    setUploadProgress(0);
    setUploadStage('menyiapkan');
    const sizeMb = (file.size / 1048576).toFixed(1);
    toast({ title: 'Mengunggah...', description: `${file.name} (${sizeMb} MB)` });

    const result = await uploadBackup(file, token, (percent, stage) => {
      setUploadProgress(percent);
      setUploadStage(stage);
    });

    setProcessing(null);
    setUploadFile(null);
    setUploadProgress(0);
    setUploadStage(null);
    const input = document.getElementById('backup-upload-input');
    if (input) input.value = '';

    if (result.ok) {
      toast({
        title: 'Upload berhasil',
        description: `${result.backup_name} — ${result.collections_found ?? '?'} koleksi `
          + `(database '${result.database_in_backup ?? '-'}'). Pakai "Pilih" atau "Restore All" untuk memulihkan.`,
      });
      fetchBackups();
    } else {
      toast({ title: 'Upload gagal', description: result.error || 'Upload gagal', variant: 'destructive' });
    }
  };

  const openSelectiveRestore = async (backup) => {
    setProcessing(backup.backup_id);
    const result = await listCollections(backup.backup_id, token);
    setProcessing(null);
    if (result.error) {
      toast({ title: 'Error', description: result.error, variant: 'destructive' });
      return;
    }
    setCollections(result.collections || []);
    setSelectedCollections([]);
    setRestoreMode('overwrite');
    setSelectiveRestore(backup);
  };

  const toggleCollection = (collectionName) => {
    setSelectedCollections(prev =>
      prev.includes(collectionName)
        ? prev.filter(c => c !== collectionName)
        : [...prev, collectionName]
    );
  };

  const selectAllCollections = () => {
    setSelectedCollections(collections.map(c => c.name));
  };

  const clearSelections = () => {
    setSelectedCollections([]);
  };

  const confirmSelectiveRestore = async () => {
    if (selectedCollections.length === 0) {
      toast({ title: 'Error', description: 'Pilih minimal 1 collection', variant: 'destructive' });
      return;
    }
    setProcessing('selective-restore');
    const result = await restoreSelective(selectiveRestore.backup_id, selectedCollections, restoreMode, token);
    setProcessing(null);
    if (result.ok) {
      toast({
        title: 'Restore Selesai',
        description: `${result.total_restored}/${result.total_requested} collections berhasil di-restore`
      });
      setSelectiveRestore(null);
    } else {
      toast({ title: 'Error', description: result.error || 'Restore gagal', variant: 'destructive' });
    }
  };

  const latestBackup = backups[0];
  const totalSize = backups.reduce((sum, b) => {
    const sizeStr = b.size || '0';
    const sizeNum = parseFloat(sizeStr.replace(/[^0-9.]/g, ''));
    return sum + (sizeStr.includes('G') ? sizeNum * 1024 : sizeNum);
  }, 0);

  return (
    <div className="space-y-5" data-testid="backup-restore-page">
      <PageHeader
        icon={Database}
        eyebrow="Portal Management · System"
        title="Database Backup & Restore"
        subtitle="Kelola backup database untuk disaster recovery. Backup otomatis berjalan setiap hari jam 02:00 WIB."
        actions={
          <>
            <input
              type="file"
              accept=".zip,application/zip"
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);   // langsung unggah, tanpa klik kedua
              }}
              style={{ display: 'none' }}
              id="backup-upload-input"
            />
            <Button
              variant="outline"
              onClick={() => document.getElementById('backup-upload-input').click()}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="backup-upload"
              disabled={processing === 'upload'}
            >
              <FileUp className="w-3.5 h-3.5 mr-1.5" />
              {processing === 'upload'
                ? `Mengunggah ${uploadProgress}%${uploadStage ? ` · ${uploadStage}` : ''}`
                : 'Upload ZIP'}
            </Button>
            <Button
              variant="ghost"
              onClick={fetchBackups}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="backup-refresh"
              disabled={loading}
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Muat Ulang
            </Button>
            <Button
              onClick={createBackup}
              className="h-9"
              data-testid="backup-create"
              disabled={processing === 'create'}
            >
              <Database className="w-3.5 h-3.5 mr-1.5" />
              {processing === 'create' ? 'Membuat...' : 'Buat Backup'}
            </Button>
          </>
        }
      />

      {processing === 'upload' && (
        <GlassCard className="p-4" data-testid="backup-upload-progress">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="font-medium text-foreground">
              Mengunggah {uploadFile?.name || 'berkas'}
              {uploadFile ? ` (${(uploadFile.size / 1048576).toFixed(1)} MB)` : ''}
            </span>
            <span className="text-muted-foreground">
              {uploadProgress}%{uploadStage ? ` · ${uploadStage}` : ''}
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Berkas &gt; 8 MB diunggah berpotong 5 MB agar tidak tertolak proxy. Jangan tutup halaman ini.
          </p>
        </GlassCard>
      )}

      {downloadHint && (
        <GlassCard className="p-4 border-blue-500/30 bg-blue-500/5" data-testid="backup-download-link">
          <div className="flex items-start gap-3">
            <Download className="w-5 h-5 text-blue-300 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <div className="font-semibold text-foreground mb-0.5">Unduhan siap: {downloadHint.name}</div>
              <div className="text-muted-foreground">
                Unduhan otomatis bisa diblokir browser saat aplikasi dibuka di dalam frame.
                Kalau berkas belum turun,{' '}
                <a
                  href={downloadHint.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-300 underline font-medium"
                  data-testid="backup-download-manual"
                >
                  klik di sini untuk unduh manual
                </a>{' '}
                (tautan berlaku 15 menit).
              </div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setDownloadHint(null)}>Tutup</Button>
          </div>
        </GlassCard>
      )}

      <div className="flex gap-1 p-1 rounded-lg bg-muted/40 w-fit" data-testid="backup-tabs">
        {[['backup', 'Backup & Restore'], ['collections', 'Koleksi Database']].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`backup-tab-${k}`}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              tab === k ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'collections' && <DatabaseCollectionsPanel token={token} />}

      {tab === 'backup' && (<>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <StatTile label="Total Backups" value={backups.length} />
        <StatTile label="Latest Backup" value={latestBackup ? formatDate(latestBackup.created_at).split(',')[0] : '-'} accent="primary" />
        <StatTile label="Total Size" value={`${totalSize.toFixed(1)} MB`} />
        <StatTile label="Retention" value={`${config?.retention_days || 30} Hari`} accent="warning" />
      </div>

      {config && (
        <GlassCard className="p-4 bg-blue-500/5 border-blue-500/30">
          <div className="flex items-start gap-3">
            <Clock className="w-5 h-5 text-blue-300 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="text-sm font-semibold text-foreground mb-1">Automated Backup Schedule</div>
              <div className="text-sm text-muted-foreground">
                <div>• Schedule: <span className="text-blue-300 font-medium">{config.auto_backup_schedule}</span></div>
                <div>• Retention: <span className="text-blue-300 font-medium">{config.retention_days} hari</span> (backup otomatis dihapus setelah periode ini)</div>
                <div>• Storage: <span className="text-blue-300 font-medium">{config.storage_type === 'local_filesystem' ? 'Local Filesystem' : config.storage_type}</span></div>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={cleanup}
              disabled={processing === 'cleanup'}
              data-testid="backup-cleanup"
            >
              {processing === 'cleanup' ? 'Processing...' : 'Cleanup Old Backups'}
            </Button>
          </div>
        </GlassCard>
      )}

      <GlassCard className="p-4">
        <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
          <HardDrive className="w-5 h-5" />
          Backup History ({backups.length})
        </h3>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Memuat...</div>
        ) : backups.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Belum ada backup. Tekan "Buat Backup" untuk membuat backup pertama.
          </div>
        ) : (
          <div className="space-y-3">
            {backups.map(backup => (
              <div
                key={backup.backup_id}
                className="flex items-center gap-4 p-4 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] hover:bg-[var(--glass-border)]/30 transition"
                data-testid={`backup-item-${backup.backup_id}`}
              >
                <Database className="w-8 h-8 text-primary flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm font-semibold text-foreground truncate">
                      {backup.backup_name}
                    </span>
                    {backup.status === 'success' ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-300 flex-shrink-0" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-yellow-300 flex-shrink-0" />
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {formatDate(backup.created_at)}
                    </span>
                    <span className="flex items-center gap-1">
                      <HardDrive className="w-3 h-3" />
                      {backup.size}
                    </span>
                    {backup.database && (
                      <span className="px-2 py-0.5 rounded bg-primary/10 text-primary">
                        {backup.database}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDownload(backup)}
                    disabled={processing === backup.backup_id}
                    className="text-blue-300 hover:text-blue-200 hover:bg-blue-500/10"
                    data-testid={`backup-download-${backup.backup_id}`}
                    title="Download as ZIP"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openSelectiveRestore(backup)}
                    disabled={processing === backup.backup_id}
                    data-testid={`backup-selective-${backup.backup_id}`}
                    title="Selective Restore"
                  >
                    <CheckSquare className="w-3.5 h-3.5 mr-1" />
                    Pilih
                  </Button>
                  <Button
                    size="sm"
                    variant="default"
                    onClick={() => { setRestoreError(null); setRestoreTarget(backup); }}
                    disabled={processing === 'restore'}
                    data-testid={`backup-restore-${backup.backup_id}`}
                    title="Full Restore"
                  >
                    <Download className="w-3.5 h-3.5 mr-1" />
                    Restore All
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => deleteBackup(backup)}
                    disabled={processing === backup.backup_id}
                    className="text-red-300 hover:text-red-200 hover:bg-red-500/10"
                    data-testid={`backup-delete-${backup.backup_id}`}
                  >
                    {processing === backup.backup_id ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
      </>)}

      {restoreTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => { setRestoreTarget(null); setRestoreError(null); }}>
          <GlassCard className="p-6 max-w-lg w-full" onClick={e => e.stopPropagation()} data-testid="restore-dialog">
            <div className="flex items-start gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0" />
              <div>
                <h2 className="text-xl font-bold text-foreground">⚠️ Konfirmasi Restore Database</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Tindakan ini akan <span className="text-red-300 font-semibold">MENGGANTI seluruh database saat ini</span> dengan backup yang dipilih.
                  Semua perubahan setelah backup akan hilang!
                </p>
              </div>
            </div>
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4">
              <div className="text-sm space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Backup:</span>
                  <span className="font-mono font-semibold">{restoreTarget.backup_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Dibuat:</span>
                  <span className="font-semibold">{formatDate(restoreTarget.created_at)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Size:</span>
                  <span className="font-semibold">{restoreTarget.size}</span>
                </div>
              </div>
            </div>
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 mb-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-yellow-300 flex-shrink-0 mt-0.5" />
                <div className="text-xs text-yellow-200">
                  <strong>PERINGATAN:</strong> Proses restore akan:
                  <ul className="list-disc list-inside mt-1 space-y-0.5">
                    <li>Menghapus database saat ini</li>
                    <li>Restore data dari backup</li>
                    <li>Restart semua services</li>
                    <li>Durasi: 30 detik - 5 menit (tergantung ukuran database)</li>
                  </ul>
                </div>
              </div>
            </div>
            {restoreError && (
              <div
                className="bg-red-50 dark:bg-red-950/40 border border-red-300 dark:border-red-500/50 rounded-lg p-4 mb-4"
                data-testid="restore-error-panel"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  <div className="text-xs text-red-900 dark:text-red-100 space-y-2 w-full min-w-0">
                    <div className="font-bold text-sm text-red-800 dark:text-red-200" data-testid="restore-error-title">
                      {restoreError.message}
                    </div>
                    <div>
                      <span className="font-semibold">Sebab: </span>
                      <span data-testid="restore-error-reason">{restoreError.reason}</span>
                    </div>
                    {restoreError.hint && (
                      <div>
                        <span className="font-semibold">Saran perbaikan: </span>
                        <span data-testid="restore-error-hint">{restoreError.hint}</span>
                      </div>
                    )}
                    {(restoreError.returncode !== null && restoreError.returncode !== undefined) && (
                      <div>
                        <span className="font-semibold">Kode keluar proses: </span>
                        <code className="font-mono">{restoreError.returncode}</code>
                      </div>
                    )}
                    {restoreError.logLines && restoreError.logLines.length > 0 && (
                      <details>
                        <summary className="cursor-pointer font-semibold select-none">
                          Log teknis ({restoreError.logLines.length} baris)
                        </summary>
                        <pre
                          className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all bg-red-100 dark:bg-black/60 text-red-900 dark:text-red-100 border border-red-200 dark:border-red-500/30 rounded p-2 text-[10px] leading-relaxed"
                          data-testid="restore-error-log"
                        >{restoreError.logLines.join('\n')}</pre>
                      </details>
                    )}
                    {restoreError.logPath && (
                      <div className="text-red-800 dark:text-red-200/90">
                        Log lengkap: <code className="font-mono break-all">{restoreError.logPath}</code>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                onClick={() => { setRestoreTarget(null); setRestoreError(null); }}
                className="border border-[var(--glass-border)]"
                data-testid="restore-cancel"
                disabled={processing === 'restore'}
              >
                Batal
              </Button>
              <Button
                variant="destructive"
                onClick={restoreBackup}
                disabled={processing === 'restore'}
                data-testid="restore-confirm"
              >
                {processing === 'restore' ? (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    Restoring...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    Konfirmasi Restore
                  </>
                )}
              </Button>
            </div>
          </GlassCard>
        </div>
      )}

      {selectiveRestore && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setSelectiveRestore(null)}>
          <GlassCard className="p-6 max-w-3xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()} data-testid="selective-restore-dialog">
            <h2 className="text-xl font-bold text-foreground mb-4">Selective Restore: {selectiveRestore.backup_name}</h2>
            
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-4">
              <div className="text-sm">
                <div className="font-semibold mb-2">Pilih collection yang ingin di-restore:</div>
                <div className="flex gap-3 mb-2">
                  <Button size="sm" variant="outline" onClick={selectAllCollections} data-testid="select-all-collections">
                    Pilih Semua ({collections.length})
                  </Button>
                  <Button size="sm" variant="ghost" onClick={clearSelections}>
                    Clear ({selectedCollections.length} selected)
                  </Button>
                </div>
                <div className="text-xs text-muted-foreground">
                  Selected: {selectedCollections.length} / {collections.length} collections
                </div>
              </div>
            </div>

            <div className="mb-4">
              <label className="text-sm font-semibold text-foreground mb-2 block">Restore Mode:</label>
              <div className="flex gap-3">
                <button
                  onClick={() => setRestoreMode('overwrite')}
                  className={`flex-1 p-3 rounded-lg border text-left transition ${
                    restoreMode === 'overwrite'
                      ? 'border-primary bg-primary/10'
                      : 'border-[var(--glass-border)] hover:border-primary/50'
                  }`}
                  data-testid="mode-overwrite"
                >
                  <div className="font-semibold text-sm">Overwrite (Drop & Restore)</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Hapus collection yang ada, lalu restore dari backup (default)
                  </div>
                </button>
                <button
                  onClick={() => setRestoreMode('merge')}
                  className={`flex-1 p-3 rounded-lg border text-left transition ${
                    restoreMode === 'merge'
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-[var(--glass-border)] hover:border-emerald-500/50'
                  }`}
                  data-testid="mode-merge"
                >
                  <div className="font-semibold text-sm">Merge (Insert Only)</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Tambahkan data dari backup tanpa menghapus data existing
                  </div>
                </button>
              </div>
            </div>

            <div className="border border-[var(--glass-border)] rounded-lg p-4 max-h-96 overflow-y-auto">
              <div className="space-y-2">
                {collections.map(collection => (
                  <div
                    key={collection.name}
                    onClick={() => toggleCollection(collection.name)}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition ${
                      selectedCollections.includes(collection.name)
                        ? 'border-primary bg-primary/10'
                        : 'border-[var(--glass-border)] hover:border-primary/30'
                    }`}
                    data-testid={`collection-${collection.name}`}
                  >
                    {selectedCollections.includes(collection.name) ? (
                      <CheckSquare className="w-5 h-5 text-primary flex-shrink-0" />
                    ) : (
                      <Square className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-sm font-semibold truncate">{collection.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {collection.document_count} docs · {collection.size_mb} MB
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2 justify-end mt-6">
              <Button
                variant="ghost"
                onClick={() => setSelectiveRestore(null)}
                className="border border-[var(--glass-border)]"
                data-testid="selective-cancel"
                disabled={processing === 'selective-restore'}
              >
                Batal
              </Button>
              <Button
                onClick={confirmSelectiveRestore}
                disabled={processing === 'selective-restore' || selectedCollections.length === 0}
                data-testid="selective-confirm"
              >
                {processing === 'selective-restore' ? (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                    Restoring...
                  </>
                ) : (
                  <>
                    <CheckSquare className="w-4 h-4 mr-2" />
                    Restore {selectedCollections.length} Collections ({restoreMode})
                  </>
                )}
              </Button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
