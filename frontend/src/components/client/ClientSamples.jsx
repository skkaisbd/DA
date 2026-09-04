import { useEffect, useState, useCallback, useRef } from 'react';
import { Sparkles, CheckCircle2, XCircle, Repeat, Loader2, MessageSquare, History, ImagePlus, X as XIcon } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { clientApi, fmtDate, SAMPLE_STATUS_LABEL } from './clientApi';

const FILTERS = [
  { id: 'all', label: 'Semua' },
  { id: 'submitted', label: 'Menunggu Approval' },
  { id: 'revision_requested', label: 'Revisi' },
  { id: 'approved', label: 'Disetujui' },
  { id: 'rejected', label: 'Ditolak' },
];

function StatusBadge({ status }) {
  const tone =
    status === 'approved'
      ? 'bg-emerald-100 text-emerald-700'
      : status === 'rejected'
      ? 'bg-red-100 text-red-700'
      : status === 'submitted'
      ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700'
      : status === 'revision_requested'
      ? 'bg-orange-100 dark:bg-orange-500/15 text-orange-300'
      : 'bg-foreground/10 text-foreground/65';
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium ${tone}`}>
      {SAMPLE_STATUS_LABEL[status] || status}
    </span>
  );
}

function ActionDialog({ open, onClose, mode, sample, token, onSuccess }) {
  const [reason, setReason] = useState('');
  const [changes, setChanges] = useState('');
  const [feedback, setFeedback] = useState('');
  const [photos, setPhotos] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (open) {
      setReason('');
      setChanges('');
      setFeedback('');
      setPhotos([]);
    }
  }, [open]);

  if (!open || !sample || !mode) return null;

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    if (photos.length + files.length > 5) {
      toast.error('Maksimal 5 foto');
      return;
    }
    setUploading(true);
    const uploaded = [];
    for (const f of files) {
      if (!f.type.startsWith('image/')) {
        toast.error(`${f.name} bukan file gambar`);
        continue;
      }
      if (f.size > 5 * 1024 * 1024) {
        toast.error(`${f.name} > 5MB`);
        continue;
      }
      try {
        const fd = new FormData();
        fd.append('file', f);
        const res = await fetch('/api/dewi/client-portal/uploads', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Upload gagal');
        uploaded.push(data.url);
      } catch (err) {
        toast.error(`${f.name}: ${err.message}`);
      }
    }
    setPhotos((p) => [...p, ...uploaded]);
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removePhoto = (url) => setPhotos((p) => p.filter((u) => u !== url));

  const submit = async () => {
    if (mode !== 'approve' && !reason.trim()) {
      toast.error('Alasan wajib diisi');
      return;
    }
    setSubmitting(true);
    try {
      const path =
        mode === 'approve'
          ? `/samples/${sample.id}/approve`
          : mode === 'reject'
          ? `/samples/${sample.id}/reject`
          : `/samples/${sample.id}/revision`;
      const body =
        mode === 'approve'
          ? { feedback }
          : mode === 'reject'
          ? { reason, changes_required: changes }
          : { reason, changes_required: changes, photos };
      await clientApi.request(path, { method: 'POST', token, body });
      toast.success(
        mode === 'approve'
          ? 'Sample disetujui'
          : mode === 'reject'
          ? 'Sample ditolak'
          : 'Permintaan revisi dikirim'
      );
      onSuccess();
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const title =
    mode === 'approve'
      ? 'Setujui Sample'
      : mode === 'reject'
      ? 'Tolak Sample'
      : 'Minta Revisi Sample';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      data-testid="client-sample-action-dialog"
    >
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl border border-foreground/10 bg-[hsl(var(--background))] p-6 shadow-xl">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-foreground/55 mt-1 font-mono">{sample.sample_code}</p>
          <p className="text-sm text-foreground/70 mt-0.5">{sample.product_name}</p>
        </div>

        {mode === 'approve' ? (
          <div className="space-y-1.5">
            <label className="text-xs uppercase tracking-wider text-foreground/50">
              Catatan Approval (opsional)
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Misal: Lanjutkan ke produksi mass."
              rows={3}
              className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
              data-testid="client-sample-approve-feedback"
            />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs uppercase tracking-wider text-foreground/50">
                Alasan <span className="text-red-700">*</span>
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={
                  mode === 'reject'
                    ? 'Misal: Bahan tidak sesuai spesifikasi yang disepakati.'
                    : 'Misal: Warna terlalu gelap, tolong revisi ke navy lebih terang.'
                }
                rows={3}
                className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
                data-testid="client-sample-reason-input"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs uppercase tracking-wider text-foreground/50">
                Perubahan yang Diperlukan (opsional)
              </label>
              <textarea
                value={changes}
                onChange={(e) => setChanges(e.target.value)}
                placeholder="Detail perubahan teknis, ukuran, warna, dll."
                rows={2}
                className="w-full rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
                data-testid="client-sample-changes-input"
              />
            </div>
            {mode === 'revision' && (
              <div className="space-y-1.5">
                <label className="text-xs uppercase tracking-wider text-foreground/50 flex items-center justify-between">
                  <span>Foto Referensi (opsional, max 5)</span>
                  <span className="text-foreground/40 normal-case tracking-normal">{photos.length}/5</span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {photos.map((url) => (
                    <div
                      key={url}
                      className="relative w-16 h-16 rounded-lg border border-foreground/10 overflow-hidden bg-foreground/[0.04]"
                    >
                      <img src={url} alt="upload" className="w-full h-full object-cover" />
                      <button
                        type="button"
                        onClick={() => removePhoto(url)}
                        className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-foreground flex items-center justify-center hover:bg-red-500"
                        data-testid={`client-sample-remove-photo-${url.split('/').pop()}`}
                      >
                        <XIcon size={11} />
                      </button>
                    </div>
                  ))}
                  {photos.length < 5 && (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="w-16 h-16 rounded-lg border border-dashed border-foreground/15 bg-foreground/[0.02] hover:bg-foreground/[0.06] flex items-center justify-center text-foreground/55 transition disabled:opacity-50"
                      data-testid="client-sample-upload-photo-btn"
                    >
                      {uploading ? <Loader2 size={16} className="animate-spin" /> : <ImagePlus size={18} />}
                    </button>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                  data-testid="client-sample-upload-photo-input"
                />
                <p className="text-[10px] text-foreground/45">
                  Format JPG/PNG/WebP, maksimal 5MB per foto.
                </p>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Batal
          </Button>
          <Button
            onClick={submit}
            disabled={submitting}
            className={`gap-1.5 ${
              mode === 'approve'
                ? 'bg-emerald-500 hover:bg-emerald-600 text-foreground'
                : mode === 'reject'
                ? 'bg-red-500 hover:bg-red-600 text-foreground'
                : 'bg-amber-500 hover:bg-amber-600 text-foreground'
            }`}
            data-testid="client-sample-action-submit"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
            {mode === 'approve' ? 'Setujui' : mode === 'reject' ? 'Tolak' : 'Kirim Revisi'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function SampleDetailDrawer({ open, onClose, sample, token, refresh }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionMode, setActionMode] = useState(null);

  useEffect(() => {
    if (!open || !sample) return;
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const d = await clientApi.request(`/samples/${sample.id}`, { token });
        if (!cancel) setDetail(d);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [open, sample, token]);

  if (!open || !sample) return null;

  const canAct = detail && ['submitted', 'revision_requested'].includes(detail.status);

  return (
    <div className="fixed inset-0 z-40 flex justify-end" data-testid="client-sample-drawer">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full md:max-w-2xl bg-[hsl(var(--background))] border-l border-foreground/10 overflow-y-auto">
        <div className="sticky top-0 z-10 bg-[hsl(var(--background))]/95 backdrop-blur border-b border-foreground/10 px-6 py-4 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Detail Sample
            </div>
            <div className="text-base font-semibold text-foreground font-mono">
              {sample.sample_code}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-foreground/5"
            data-testid="client-sample-drawer-close"
          >
            <XCircle size={18} />
          </button>
        </div>

        {loading || !detail ? (
          <div className="p-10 text-center text-foreground/50">Memuat detail...</div>
        ) : (
          <div className="p-6 space-y-5">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <StatusBadge status={detail.status} />
                {detail.revision_number > 0 && (
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-orange-100 dark:bg-orange-500/15 text-orange-300">
                    Revisi #{detail.revision_number}
                  </span>
                )}
              </div>
              <h2 className="text-xl font-bold text-foreground">{detail.product_name}</h2>
              {detail.description && (
                <p className="text-sm text-foreground/65 mt-1">{detail.description}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Bahan
                </div>
                <div className="font-medium text-foreground">{detail.fabric_used || '-'}</div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Warna
                </div>
                <div className="font-medium text-foreground">{detail.color_used || '-'}</div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Ukuran Target
                </div>
                <div className="font-medium text-foreground">{detail.target_size || '-'}</div>
              </div>
              <div className="rounded-xl border border-foreground/10 p-3">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45">
                  Jumlah Sample
                </div>
                <div className="font-medium text-foreground">{detail.sample_qty} pcs</div>
              </div>
            </div>

            {detail.notes && (
              <div className="rounded-xl border border-foreground/10 p-3 text-sm">
                <div className="text-[10px] uppercase tracking-wider text-foreground/45 mb-1">
                  Catatan dari Tim Produksi
                </div>
                <div className="text-foreground/85">{detail.notes}</div>
              </div>
            )}

            {detail.photos?.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-2">
                  Foto Sample
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {detail.photos.map((p, i) => (
                    <div
                      key={i}
                      className="aspect-square rounded-lg border border-foreground/10 bg-foreground/[0.04] overflow-hidden flex items-center justify-center"
                    >
                      <img
                        src={p}
                        alt={`Sample ${i}`}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detail.approval_feedback && detail.status === 'approved' && (
              <div className="rounded-xl border border-emerald-500/25 bg-emerald-100 dark:bg-emerald-500/5 p-3 text-sm">
                <div className="flex items-center gap-2 text-emerald-700 mb-1">
                  <CheckCircle2 size={14} />
                  <span className="text-xs font-medium">Disetujui</span>
                  <span className="text-[10px] text-foreground/50">
                    {detail.approved_at && `· ${fmtDate(detail.approved_at)}`}
                  </span>
                </div>
                <div className="text-foreground/85">{detail.approval_feedback}</div>
              </div>
            )}

            {detail.rejection_reason && detail.status === 'rejected' && (
              <div className="rounded-xl border border-red-500/25 bg-red-100 dark:bg-red-500/5 p-3 text-sm">
                <div className="flex items-center gap-2 text-red-700 mb-1">
                  <XCircle size={14} />
                  <span className="text-xs font-medium">Ditolak</span>
                </div>
                <div className="text-foreground/85">{detail.rejection_reason}</div>
              </div>
            )}

            {detail.revisions?.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <History size={14} className="text-foreground/55" />
                  <span className="text-[11px] uppercase tracking-wider text-foreground/50">
                    Riwayat Revisi ({detail.revisions.length})
                  </span>
                </div>
                <div className="space-y-2">
                  {detail.revisions.map((r) => (
                    <div
                      key={r.id}
                      className="rounded-xl border border-foreground/10 p-3 text-sm"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-orange-300">
                          Revisi #{r.revision_number}
                        </span>
                        <span className="text-[10px] text-foreground/45">
                          {fmtDate(r.created_at)} · {r.requested_by}
                        </span>
                      </div>
                      <div className="text-foreground/85">{r.reason}</div>
                      {r.changes_required && (
                        <div className="text-foreground/65 text-xs mt-1">
                          → {r.changes_required}
                        </div>
                      )}
                      {r.photos?.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {r.photos.map((p, i) => (
                            <a
                              key={i}
                              href={p}
                              target="_blank"
                              rel="noreferrer"
                              className="block w-12 h-12 rounded border border-foreground/10 overflow-hidden bg-foreground/[0.04]"
                            >
                              <img src={p} alt={`rev ${i}`} className="w-full h-full object-cover" />
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {canAct && (
              <div className="sticky bottom-0 -mx-6 -mb-6 px-6 py-4 bg-[hsl(var(--background))]/95 backdrop-blur border-t border-foreground/10 flex flex-wrap gap-2">
                <Button
                  className="flex-1 gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-foreground"
                  onClick={() => setActionMode('approve')}
                  data-testid="client-sample-btn-approve"
                >
                  <CheckCircle2 size={15} />
                  Setujui
                </Button>
                <Button
                  variant="outline"
                  className="flex-1 gap-1.5 border-orange-500/40 text-orange-300 hover:bg-orange-100 dark:bg-orange-500/10"
                  onClick={() => setActionMode('revision')}
                  data-testid="client-sample-btn-revision"
                >
                  <Repeat size={15} />
                  Minta Revisi
                </Button>
                <Button
                  variant="outline"
                  className="flex-1 gap-1.5 border-red-500/40 text-red-700 hover:bg-red-100 dark:bg-red-500/10"
                  onClick={() => setActionMode('reject')}
                  data-testid="client-sample-btn-reject"
                >
                  <XCircle size={15} />
                  Tolak
                </Button>
              </div>
            )}
          </div>
        )}

        <ActionDialog
          open={Boolean(actionMode)}
          mode={actionMode}
          sample={detail}
          token={token}
          onClose={() => setActionMode(null)}
          onSuccess={() => {
            refresh();
            setActionMode(null);
            // Re-fetch the detail
            (async () => {
              try {
                const d = await clientApi.request(`/samples/${sample.id}`, { token });
                setDetail(d);
              } catch (e) {}
            })();
          }}
        />
      </div>
    </div>
  );
}

export default function ClientSamples({ token }) {
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [active, setActive] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = filter === 'all' ? '/samples' : `/samples?status=${filter}`;
      const data = await clientApi.request(path, { token });
      setSamples(data);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filter, token]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6" data-testid="client-samples">
      <div>
        <div className="text-xs uppercase tracking-[0.18em] text-foreground/45 mb-1">
          Sample & Approval
        </div>
        <h1 className="text-3xl font-bold text-foreground">Sample Produksi</h1>
        <p className="text-sm text-foreground/55 mt-1">
          Tinjau detail sample dan berikan keputusan untuk melanjutkan produksi.
        </p>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            data-testid={`client-samples-filter-${f.id}`}
            className={`px-3 py-1.5 text-xs rounded-full whitespace-nowrap transition ${
              filter === f.id
                ? 'bg-[hsl(var(--primary))] text-foreground font-medium'
                : 'bg-foreground/5 text-foreground/65 hover:bg-foreground/10'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-xl bg-foreground/[0.05]" />
          ))}
        </div>
      ) : samples.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-foreground/10 p-12 text-center">
          <Sparkles size={32} className="mx-auto text-foreground/30 mb-2" />
          <p className="text-sm text-foreground/50">Tidak ada sample untuk filter ini.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="client-samples-list">
          {samples.map((s) => {
            const needsAction = ['submitted', 'revision_requested'].includes(s.status);
            return (
              <button
                key={s.id}
                onClick={() => setActive(s)}
                data-testid={`client-sample-card-${s.id}`}
                className={`text-left rounded-2xl border p-4 transition ${
                  needsAction
                    ? 'border-amber-400 dark:border-amber-400/30 bg-amber-400/5 hover:bg-amber-400/10'
                    : 'border-foreground/10 bg-foreground/[0.03] hover:bg-foreground/[0.05]'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-xs font-mono text-foreground/55">{s.sample_code}</span>
                  <StatusBadge status={s.status} />
                </div>
                <div className="text-base font-medium text-foreground line-clamp-1">
                  {s.product_name}
                </div>
                <div className="text-xs text-foreground/55 mt-1">
                  {s.fabric_used || 'Bahan -'} · {s.color_used || 'Warna -'} ·{' '}
                  Ukuran {s.target_size || '-'}
                </div>
                <div className="flex items-center justify-between mt-3 text-xs text-foreground/50">
                  <span className="flex items-center gap-1">
                    <MessageSquare size={12} />
                    {s.revision_number || 0} revisi
                  </span>
                  <span>{fmtDate(s.created_at)}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <SampleDetailDrawer
        open={Boolean(active)}
        sample={active}
        token={token}
        refresh={load}
        onClose={() => setActive(null)}
      />
    </div>
  );
}
