import { useState, useEffect } from 'react';
import { BookOpen, Briefcase, ListChecks, Video, Image as ImageIcon, PlayCircle, ArrowLeft, AlertCircle, Loader2, Package } from 'lucide-react';
import { apiGet } from '../../../lib/api';

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';
const token = () => localStorage.getItem('erp_token') || '';
const fileUrl = (p) => `${BACKEND}/api/files/${p}?auth=${encodeURIComponent(token())}`;

function ytId(url) {
  const m = String(url || '').match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([\w-]{11})/);
  return m ? m[1] : null;
}

/**
 * VendorProductionGuide (Portal Vendor CMT) — READ ONLY.
 *
 * RELATION FIX: sekarang membaca pekerjaan NYATA vendor dari `/production-jobs`
 * (koleksi production_jobs, scoped vendor_id di backend) — bukan lagi `vendor_jobs`
 * yang kosong. Panduan Produksi di-resolve dari SUMBER YANG BENAR via
 * `/production-jobs/{id}/production-guide`:
 *   - Maklon  → dewi_maklon_buyer_catalog (SOP yang diinput di ERP Katalog Buyer)
 *   - Internal→ rahaza_models
 * Endpoint mengembalikan `guides[]` (bisa >1 artikel per job).
 */
export default function VendorProductionGuide() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // job
  const [guide, setGuide] = useState(null);
  const [guideLoading, setGuideLoading] = useState(false);
  const [lightbox, setLightbox] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await apiGet('/production-jobs');
        const list = Array.isArray(data) ? data : (data?.items || data?.data || []);
        if (alive) setJobs(list);
      } catch (_e) {
        if (alive) setJobs([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const openGuide = async (job) => {
    setSelected(job);
    setGuide(null);
    setGuideLoading(true);
    try {
      const data = await apiGet(`/production-jobs/${job.id}/production-guide`);
      setGuide(data);
    } catch (_e) {
      setGuide({ has_guide: false, guides: [], message: 'Gagal memuat panduan.' });
    } finally {
      setGuideLoading(false);
    }
  };

  const renderGuideCard = (g, gi) => {
    const photos = g.image_paths || [];
    const steps = g.sop_steps || [];
    const videos = g.reference_videos || [];
    const refImages = g.reference_images || [];
    const empty = photos.length === 0 && steps.length === 0 && videos.length === 0 && refImages.length === 0 && !g.hero_image_url;
    const badge = g.source_type === 'buyer_catalog' ? 'Katalog Buyer' : 'Model Internal';
    return (
      <div key={gi} className="rounded-2xl border border-border bg-card p-4 space-y-5" data-testid={`vendor-guide-article-${gi}`}>
        <div className="flex items-center gap-2 flex-wrap border-b border-border pb-3">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            <Package className="w-3.5 h-3.5" /> {badge}
          </span>
          {g.code && <span className="font-mono text-xs text-muted-foreground">{g.code}</span>}
          <span className="text-sm font-semibold text-foreground">{g.name}</span>
        </div>

        {g.description && <p className="text-sm text-muted-foreground">{g.description}</p>}

        {g.hero_image_url && (
          <img src={g.hero_image_url} alt="produk" onClick={() => setLightbox(g.hero_image_url)}
            className="w-40 h-40 rounded-lg object-cover border border-border cursor-zoom-in hover:ring-2 hover:ring-primary/40" />
        )}

        {photos.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5"><ImageIcon className="w-4 h-4 text-primary" /> Foto Produk</h3>
            <div className="flex flex-wrap gap-2" data-testid="vendor-guide-photos">
              {photos.map((p) => (
                <img key={p} src={fileUrl(p)} alt="produk" onClick={() => setLightbox(fileUrl(p))}
                  className="w-24 h-24 rounded-lg object-cover border border-border cursor-zoom-in hover:ring-2 hover:ring-primary/40" />
              ))}
            </div>
          </section>
        )}

        {steps.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5"><ListChecks className="w-4 h-4 text-primary" /> Tata Cara Produksi ({steps.length} langkah)</h3>
            <ol className="space-y-2" data-testid="vendor-guide-steps">
              {steps.map((s, i) => (
                <li key={s.id || i} className="flex gap-3 rounded-xl border border-border bg-muted/30 p-3">
                  <span className="w-7 h-7 rounded-full bg-primary/15 text-primary text-sm font-bold flex items-center justify-center shrink-0">{s.seq || i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground">{s.title || `Langkah ${i + 1}`}</div>
                    {s.description && <div className="text-sm text-muted-foreground whitespace-pre-line mt-0.5">{s.description}</div>}
                  </div>
                  {s.image_path && (
                    <img src={fileUrl(s.image_path)} alt="langkah" onClick={() => setLightbox(fileUrl(s.image_path))}
                      className="w-20 h-20 rounded-lg object-cover border border-border cursor-zoom-in shrink-0" />
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}

        {videos.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5"><Video className="w-4 h-4 text-primary" /> Referensi Video</h3>
            <div className="flex flex-wrap gap-3" data-testid="vendor-guide-videos">
              {videos.map((v, i) => {
                const yid = ytId(v.url);
                return (
                  <a key={i} href={v.url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-2 rounded-xl border border-border bg-muted/30 p-2 hover:bg-muted/60 max-w-[260px]">
                    {yid
                      ? <div className="relative w-20 h-14 shrink-0"><img src={`https://img.youtube.com/vi/${yid}/mqdefault.jpg`} alt="yt" className="w-20 h-14 rounded object-cover" /><PlayCircle className="w-6 h-6 text-white absolute inset-0 m-auto drop-shadow" /></div>
                      : <div className="w-20 h-14 rounded bg-muted flex items-center justify-center shrink-0"><PlayCircle className="w-6 h-6 text-muted-foreground" /></div>}
                    <span className="text-sm text-foreground truncate">{v.title || v.url}</span>
                  </a>
                );
              })}
            </div>
          </section>
        )}

        {refImages.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-1.5"><ImageIcon className="w-4 h-4 text-primary" /> Gambar Referensi</h3>
            <div className="flex flex-wrap gap-2" data-testid="vendor-guide-refimages">
              {refImages.map((v, i) => (
                <a key={i} href={v.url} target="_blank" rel="noreferrer" title={v.caption}>
                  <img src={v.url} alt={v.caption || 'ref'} className="w-24 h-24 rounded-lg object-cover border border-border hover:ring-2 hover:ring-primary/40" />
                </a>
              ))}
            </div>
          </section>
        )}

        {empty && (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            Panduan Produksi untuk artikel ini belum diisi. Admin/PPIC dapat mengisi SOP di
            {g.source_type === 'buyer_catalog' ? ' Katalog Buyer → Panduan Produksi.' : ' Master Produk → Panduan.'}
          </div>
        )}
      </div>
    );
  };

  // ── Detail view ────────────────────────────────────────────────────────────
  if (selected) {
    const guides = guide?.guides || [];
    return (
      <div className="space-y-5">
        <button onClick={() => { setSelected(null); setGuide(null); }}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground" data-testid="guide-back">
          <ArrowLeft className="w-4 h-4" /> Kembali ke daftar
        </button>

        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-primary" /> Panduan Produksi
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {selected.job_number}
            {selected.po_number ? <> · <span className="font-mono">{selected.po_number}</span></> : null}
          </p>
        </div>

        {guideLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm py-10 justify-center">
            <Loader2 className="w-5 h-5 animate-spin" /> Memuat panduan...
          </div>
        ) : !guide?.has_guide ? (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-700 flex items-start gap-2" data-testid="guide-no-model">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {guide?.message || 'Belum ada panduan produksi untuk pekerjaan ini.'}
          </div>
        ) : (
          <div className="space-y-4" data-testid="vendor-guide-content">
            {guides.map((g, gi) => renderGuideCard(g, gi))}
          </div>
        )}

        {lightbox && (
          <div className="fixed inset-0 z-[200] bg-black/80 flex items-center justify-center p-6" onClick={() => setLightbox(null)} data-testid="vendor-guide-lightbox">
            <img src={lightbox} alt="preview" className="max-w-full max-h-full rounded-lg object-contain" />
          </div>
        )}
      </div>
    );
  }

  // ── List view ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-primary" /> Panduan Produksi
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Cara & tahapan pembuatan artikel untuk pekerjaan yang ditugaskan ke Anda. Pilih pekerjaan untuk melihat SOP, video, & gambar referensi.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /> Memuat...</div>
      ) : jobs.length === 0 ? (
        <div className="bg-card rounded-xl border border-border p-12 text-center" data-testid="guide-empty">
          <Briefcase className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
          <p className="text-muted-foreground font-medium">Belum ada pekerjaan yang ditugaskan</p>
          <p className="text-xs text-muted-foreground/70 mt-1">Panduan produksi akan muncul setelah pekerjaan produksi dibuat untuk vendor Anda.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="guide-jobs-list">
          {jobs.map((j) => {
            const isMaklon = (j.business_type || 'maklon') !== 'internal';
            return (
              <button key={j.id} onClick={() => openGuide(j)}
                className="w-full text-left p-4 rounded-xl border border-border bg-card hover:border-primary/40 hover:bg-muted/40 transition-colors flex items-center justify-between gap-3"
                data-testid={`guide-job-${j.job_number}`}>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-primary">{j.job_number}</span>
                    {j.po_number && <span className="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">{j.po_number}</span>}
                    <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${isMaklon ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>{isMaklon ? 'Maklon' : 'Internal'}</span>
                    {j.status && <span className="text-[11px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">{j.status}</span>}
                  </div>
                  <p className="text-sm text-foreground mt-1">{j.customer_name || j.vendor_name || 'Pekerjaan Produksi'}</p>
                  {j.item_count != null && <p className="text-xs text-muted-foreground mt-0.5">{j.item_count} item · target {j.total_available || j.total_ordered || 0} pcs</p>}
                </div>
                <span className="flex items-center gap-1 text-sm text-primary shrink-0"><BookOpen className="w-4 h-4" /> Lihat Panduan</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
