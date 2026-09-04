/**
 * Bandingkan Revisi Style — berdampingan (2026-08-07).
 *
 * Permintaan owner: "bisa bandingkan revisi style side-by-side supaya perubahan
 * terlihat jelas sebelum diputuskan". Dipakai di dua tempat:
 *   · Portal RnD → Desain & Tech Pack → tab Revisi
 *   · Portal Manajemen → Ringkasan & Approval RnD → dialog Detail (sebelum approve)
 *
 * Sumber data: GET /api/dewi/rnd/styles/{id}/revisions/compare?left=&right=
 * ('current' = kondisi style sekarang).
 */
import { useCallback, useEffect, useState } from 'react';
import { X, RefreshCw, ImageOff, GitCompare, ArrowRight, Plus, Minus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';

const API = process.env.REACT_APP_BACKEND_URL || '';

export const authImageUrl = (url, token) => {
  if (!url) return '';
  if (!url.startsWith('/api/')) return url;
  return `${API}${url}${url.includes('?') ? '&' : '?'}auth=${encodeURIComponent(token || '')}`;
};

const fmtDate = (v) => (v ? new Date(v).toLocaleString('id-ID') : '—');

function SideSelect({ label, value, options, onChange, testId }) {
  return (
    <div className="min-w-0 flex-1">
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
        className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function PhotoStrip({ images, token, testId }) {
  if (!images?.length) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-dashed px-3 py-4 text-xs text-muted-foreground"
           data-testid={`${testId}-empty`}>
        <ImageOff className="h-4 w-4" /> Tidak ada foto pada versi ini
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2" data-testid={testId}>
      {images.map((img, i) => (
        <a key={img.id || i} href={authImageUrl(img.url, token)} target="_blank" rel="noreferrer"
           className="group overflow-hidden rounded-lg border" title={img.caption || 'Buka gambar'}>
          <img src={authImageUrl(img.url, token)} alt={img.caption || `Foto ${i + 1}`} loading="lazy"
               className="h-28 w-full object-cover transition-transform duration-200 group-hover:scale-105" />
          {img.caption && (
            <p className="truncate px-2 py-1 text-[10px] text-muted-foreground">{img.caption}</p>
          )}
        </a>
      ))}
    </div>
  );
}

export default function RnDRevisionCompare({ token, styleId, initialLeft = '', onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (left, right) => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (left) qs.set('left', left);
      if (right) qs.set('right', right);
      const res = await fetch(
        `${API}/api/dewi/rnd/styles/${styleId}/revisions/compare${qs.toString() ? `?${qs}` : ''}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setData(body);
    } catch (e) {
      toast.error('Gagal memuat perbandingan revisi', { description: e.message });
    } finally {
      setLoading(false);
    }
  }, [styleId, token]);

  useEffect(() => { load(initialLeft, ''); }, [load, initialLeft]);

  const options = data?.available || [];
  const leftId = data?.left?.id || '';
  const rightId = data?.right?.id || '';
  const noHistory = !loading && (data?.total_revisions || 0) === 0;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-foreground/50 p-4"
         data-testid="rnd-revision-compare">
      <div className="mt-6 w-full max-w-5xl rounded-xl border bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-base font-bold text-foreground">
              <GitCompare className="h-4 w-4 text-primary" /> Bandingkan Revisi Style
            </h2>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              <span className="font-mono">{data?.style?.style_code || '—'}</span>
              {data?.style?.style_name ? ` · ${data.style.style_name}` : ''}
              {data ? ` · ${data.total_revisions} revisi tercatat` : ''}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" disabled={loading} data-testid="rnd-compare-refresh"
                    onClick={() => load(leftId, rightId)}>
              <RefreshCw className={loading ? 'animate-spin' : ''} />
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} data-testid="rnd-compare-close">
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div className="space-y-4 p-5">
          {loading && !data ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-16 rounded-lg" />)}
            </div>
          ) : noHistory ? (
            <div className="py-10 text-center" data-testid="rnd-compare-empty">
              <GitCompare className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-foreground">Belum ada revisi tercatat</p>
              <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
                Riwayat terbentuk otomatis setiap style disimpan atau foto desain
                ditambahkan/dihapus di Portal RnD.
              </p>
            </div>
          ) : (
            <>
              {/* Pemilih versi */}
              <div className="flex flex-wrap items-end gap-3">
                <SideSelect label="Versi A (lama)" value={leftId} options={options}
                            testId="rnd-compare-left-select"
                            onChange={(v) => load(v, rightId)} />
                <ArrowRight className="mb-2 h-4 w-4 shrink-0 text-muted-foreground" />
                <SideSelect label="Versi B (baru)" value={rightId} options={options}
                            testId="rnd-compare-right-select"
                            onChange={(v) => load(leftId, v)} />
                <Badge variant={data?.changed_count ? 'default' : 'secondary'} className="mb-2 text-[11px]"
                       data-testid="rnd-compare-changed-count">
                  {data?.changed_count || 0} field berubah
                </Badge>
              </div>

              {/* Meta tiap versi */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {[['A', data?.left, 'rnd-compare-meta-left'], ['B', data?.right, 'rnd-compare-meta-right']]
                  .map(([tag, side, tid]) => (
                    <div key={tag} className="rounded-lg border px-3 py-2" data-testid={tid}>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Versi {tag}
                      </p>
                      <p className="truncate text-sm font-semibold text-foreground">{side?.label}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {fmtDate(side?.created_at)}
                        {side?.created_by_name ? ` · oleh ${side.created_by_name}` : ''}
                        {side?.source === 'auto' ? ' · otomatis' : side?.source === 'live' ? ' · kondisi terkini' : ''}
                      </p>
                      {side?.changes_summary && (
                        <p className="mt-1 text-[11px] italic text-muted-foreground">{side.changes_summary}</p>
                      )}
                      {side && !side.has_snapshot && (
                        <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">
                          Revisi lama tanpa snapshot — hanya ringkasan perubahan yang tersedia.
                        </p>
                      )}
                    </div>
                  ))}
              </div>

              {/* Tabel diff */}
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full min-w-max text-xs" data-testid="rnd-compare-table">
                  <thead className="bg-[var(--glass-bg)]">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">FIELD</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">VERSI A</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted-foreground">VERSI B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.fields || []).map((f) => (
                      <tr key={f.key}
                          className={`border-t ${f.changed ? 'bg-amber-500/10' : ''}`}
                          data-testid={`rnd-compare-row-${f.key}`}>
                        <td className="px-3 py-2 font-medium text-foreground/80">
                          {f.label}
                          {f.changed && (
                            <span className="ml-2 rounded border border-amber-500/40 px-1 text-[10px] text-amber-600 dark:text-amber-400">
                              berubah
                            </span>
                          )}
                        </td>
                        <td className={`max-w-[320px] px-3 py-2 ${f.changed ? 'text-destructive' : 'text-muted-foreground'}`}>
                          {f.left || '—'}
                        </td>
                        <td className={`max-w-[320px] px-3 py-2 ${f.changed ? 'font-semibold text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                          {f.right || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Foto berdampingan */}
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">Foto Desain</h3>
                  {(data?.images?.added || []).length > 0 && (
                    <Badge variant="outline" className="border-emerald-500/40 text-[11px] text-emerald-600 dark:text-emerald-400"
                           data-testid="rnd-compare-img-added">
                      <Plus className="mr-0.5 h-3 w-3" />{data.images.added.length} foto baru
                    </Badge>
                  )}
                  {(data?.images?.removed || []).length > 0 && (
                    <Badge variant="outline" className="border-destructive/40 text-[11px] text-destructive"
                           data-testid="rnd-compare-img-removed">
                      <Minus className="mr-0.5 h-3 w-3" />{data.images.removed.length} foto dihapus
                    </Badge>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[11px] font-semibold text-muted-foreground">Versi A</p>
                    <PhotoStrip images={data?.images?.left} token={token} testId="rnd-compare-photos-left" />
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="mb-2 text-[11px] font-semibold text-muted-foreground">Versi B</p>
                    <PhotoStrip images={data?.images?.right} token={token} testId="rnd-compare-photos-right" />
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
