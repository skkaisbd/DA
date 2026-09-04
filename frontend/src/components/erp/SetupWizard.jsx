import { useState, useEffect, useCallback } from 'react';
import {
  Wand2, CheckCircle2, Circle, ArrowRight, ArrowLeft, X, Sparkles,
  MapPin, ListChecks, Timer, Factory, Users, Package, ClipboardList,
  Loader2, Rocket, SkipForward, Info,
} from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

/* ─── PT Rahaza ERP · SetupWizard (Phase 16.1) ────────────────────────────────
   First-run wizard untuk pabrik baru. 7 langkah dengan opsi "Isi Contoh Cepat"
   yang seed sample data via backend.

   Props:
     - open: bool
     - token: JWT
     - onClose: () => void — tutup modal (skip / dismiss by user)
     - onNavigate(moduleId): buka modul master terkait
     - onComplete: () => void — dipanggil saat wizard dianggap selesai

   Flow:
     1. Intro
     2..8. Cek per master data (Lokasi, Proses, Shift, Line, Karyawan, Model+Size, BOM)
        - Tiap langkah tampilkan status (done/pending) + tombol "Buka Modul"
     9. Selesai — saran buat Order pertama

   Fitur:
     - Polling status tiap 3 detik saat wizard terbuka → deteksi saat user
       balik dari modul master & status berubah
     - Tombol "Isi Contoh Cepat" (1-klik seed sample data)
     - Tombol "Lewati" (skip 24 jam) dan "Jangan tampilkan lagi" (dismiss)
───────────────────────────────────────────────────────────────────────────── */

const STEP_META = [
  {
    key: 'intro',
    label: 'Pengantar',
    icon: Rocket,
    headline: 'Selamat datang di CV. Dewi Aditya',
    description:
      'Sebelum Anda dapat mencatat produksi, sistem butuh beberapa data dasar. Wizard ini akan memandu 7 langkah singkat. Anda bisa lewati kapan saja.',
  },
  {
    key: 'locations',
    label: 'Gedung & Lokasi',
    icon: MapPin,
    headline: 'Gedung & Lokasi',
    description:
      'Tempat kerja & gudang. Contoh: Gedung A, Zona Rajut, Gudang Benang. Sistem sudah menyediakan default 6 lokasi — Anda hanya perlu verifikasi atau tambah sesuai pabrik Anda.',
    module: 'prod-locations',
  },
  {
    key: 'processes',
    label: 'Proses Produksi',
    icon: ListChecks,
    headline: 'Proses Produksi (8 langkah default)',
    description:
      'Urutan proses: Cutting → CMT-Sewing → Finishing → QC → Packing, plus rework. Sudah di-seed otomatis; biasanya tidak perlu diubah kecuali ada proses khusus.',
    module: 'prod-processes',
  },
  {
    key: 'shifts',
    label: 'Shift Kerja',
    icon: Timer,
    headline: 'Shift Kerja',
    description:
      'Jam kerja operator. Default: Shift 1 (07–15) dan Shift 2 (15–23). Sesuaikan bila pabrik Anda pakai 3 shift atau jam berbeda.',
    module: 'prod-shifts',
  },
  {
    key: 'lines',
    label: 'Line Produksi',
    icon: Factory,
    headline: 'Line Produksi',
    description:
      'Satu line = satu kelompok mesin/meja untuk proses tertentu. Contoh: LN-RAJUT-01 untuk proses Rajut. Minimal butuh 1 line per proses aktif.',
    module: 'prod-lines',
  },
  {
    key: 'employees',
    label: 'Karyawan & Operator',
    icon: Users,
    headline: 'Karyawan / Operator',
    description:
      'Setiap orang yang akan login Operator View atau tercatat sebagai pelaksana kerja. Minimal 1 operator per line agar output bisa dikaitkan ke orang.',
    module: 'prod-employees',
  },
  {
    key: 'models_sizes',
    label: 'Model & Size',
    icon: Package,
    headline: 'Model Produk & Size',
    description:
      'Model = desain sweater/produk (SWEATER-BASIC). Size = ukuran (S/M/L/XL). Kombinasi Model × Size menentukan BOM dan Work Order.',
    module: 'prod-models',
    moduleSecondary: 'prod-sizes',
  },
  {
    key: 'boms',
    label: 'BOM',
    icon: ClipboardList,
    headline: 'Bill of Materials (BOM)',
    description:
      'Daftar benang & aksesoris per Model × Size. BOM dipakai Work Order untuk hitung kebutuhan material. Pastikan minimal 1 BOM sudah lengkap.',
    module: 'prod-bom',
  },
  {
    key: 'demo_order',
    label: 'Order Pertama',
    icon: Sparkles,
    headline: 'Siap Mulai!',
    description:
      'Master data sudah lengkap. Langkah terakhir: buat Order produksi pertama Anda, lalu generate Work Order, issue material, dan mulai catat output.',
    module: 'prod-orders',
  },
];

function StatusIcon({ done }) {
  return done ? (
    <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-300" />
  ) : (
    <Circle className="w-4 h-4 text-muted-foreground/50" />
  );
}

export function SetupWizard({ open, token, onClose, onNavigate, onComplete }) {
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const fetchStatus = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch('/api/rahaza/setup/status', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setStatus(await res.json());
    } catch (e) {
      /* fail silent */
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Load status saat wizard terbuka + polling tiap 3 detik
  useEffect(() => {
    if (!open) return;
    fetchStatus();
    const id = setInterval(fetchStatus, 3000);
    return () => clearInterval(id);
  }, [open, fetchStatus]);

  // Escape key → close wizard (UX improvement)
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose?.();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const handleSeedSample = async () => {
    setSeeding(true);
    try {
      const res = await fetch('/api/rahaza/setup/seed-sample', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Gagal seed sample data');
        return;
      }
      const data = await res.json();
      toast.success('Sample data berhasil dibuat. Sistem siap dieksplorasi!');
      await fetchStatus();
      // Jump ke langkah terakhir
      setStep(STEP_META.length - 1);
      // auto-refresh caller (dashboard) via onComplete
      onComplete?.();
    } catch (e) {
      toast.error('Error: ' + e.message);
    } finally {
      setSeeding(false);
    }
  };

  const handleSkip = async () => {
    try {
      await fetch('/api/rahaza/setup/skip', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      /* ignore */
    }
    onClose?.();
  };

  const handleDismiss = async () => {
    try {
      await fetch('/api/rahaza/setup/dismiss', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      /* ignore */
    }
    onClose?.();
  };

  const handleOpenModule = (moduleId) => {
    if (!moduleId) return;
    onNavigate?.(moduleId);
    onClose?.(); // tutup wizard saat navigate
  };

  if (!open) return null;

  const steps = STEP_META;
  const currentMeta = steps[step] || steps[0];
  const CurrentIcon = currentMeta.icon;

  // Derive done status per step from backend
  const isStepDone = (key) => {
    if (!status) return false;
    if (key === 'intro') return true;
    const s = (status.steps || []).find((x) => x.key === key);
    return !!(s && s.done);
  };

  const doneCount = steps.filter((s) => isStepDone(s.key)).length;
  const totalRequired = steps.filter((s) => s.key !== 'intro').length;

  const isLastStep = step === steps.length - 1;
  const canGoNext = step < steps.length - 1;
  const canGoPrev = step > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={handleSkip}
      data-testid="setup-wizard-overlay"
    >
      <GlassCard
        hover={false}
        className="w-full max-w-3xl max-h-[92vh] overflow-hidden flex flex-col p-0"
        onClick={(e) => e.stopPropagation()}
        data-testid="setup-wizard-modal"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.25)] grid place-items-center flex-shrink-0">
              <Wand2 className="w-5 h-5 text-[hsl(var(--primary))]" />
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">Setup Wizard Produksi</h2>
              <p className="text-xs text-muted-foreground">
                Langkah {step + 1} dari {steps.length} · Progress: {doneCount}/{totalRequired}
              </p>
            </div>
          </div>
          <button
            onClick={handleSkip}
            className="p-1.5 rounded-lg hover:bg-[var(--glass-bg-hover)] text-muted-foreground hover:text-foreground"
            data-testid="setup-wizard-close"
            aria-label="Tutup wizard"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Progress rail */}
        <div className="px-6 py-3 border-b border-[var(--glass-border)]">
          <div className="flex items-center gap-1 overflow-x-auto">
            {steps.map((s, idx) => {
              const done = isStepDone(s.key);
              const active = idx === step;
              return (
                <button
                  key={s.key}
                  onClick={() => setStep(idx)}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px] whitespace-nowrap transition-colors
                    ${active
                      ? 'bg-[hsl(var(--primary)/0.12)] text-foreground border border-[hsl(var(--primary)/0.35)]'
                      : 'text-muted-foreground hover:bg-[var(--glass-bg-hover)] hover:text-foreground border border-transparent'
                    }`}
                  data-testid={`setup-step-${s.key}`}
                >
                  <StatusIcon done={done} />
                  <span>{idx + 1}. {s.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex items-start gap-4 mb-4">
            <div className="w-12 h-12 rounded-2xl bg-[hsl(var(--primary)/0.10)] border border-[hsl(var(--primary)/0.25)] grid place-items-center flex-shrink-0">
              <CurrentIcon className="w-6 h-6 text-[hsl(var(--primary))]" strokeWidth={1.8} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-bold text-foreground">{currentMeta.headline}</h3>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{currentMeta.description}</p>
            </div>
          </div>

          {/* Intro screen: offer sample data */}
          {step === 0 && (
            <div className="space-y-3">
              <GlassPanel className="p-4 border border-[hsl(var(--primary)/0.25)] bg-[hsl(var(--primary)/0.04)]">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[hsl(var(--primary)/0.15)] grid place-items-center flex-shrink-0">
                    <Sparkles className="w-4 h-4 text-[hsl(var(--primary))]" />
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-foreground">Pilihan Cepat: Isi Data Contoh</div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Ingin eksplorasi dulu? Klik tombol di bawah untuk membuat <b>2 line</b>, <b>3 operator</b>, <b>1 model demo + 4 size + BOM</b>, dan <b>1 order internal</b> secara instan. Aman — Anda bisa edit/hapus kapan saja.
                    </p>
                    <Button
                      onClick={handleSeedSample}
                      disabled={seeding}
                      className="mt-3 h-9"
                      data-testid="setup-seed-sample-btn"
                    >
                      {seeding ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Membuat...
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-4 h-4 mr-2" /> Isi Contoh Cepat
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </GlassPanel>
              <div className="text-center text-xs text-muted-foreground">
                atau klik <b>Mulai</b> untuk ikuti langkah satu per satu
              </div>
            </div>
          )}

          {/* Master step: show current count + open module button */}
          {step > 0 && (
            <div className="space-y-3">
              <GlassPanel className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusIcon done={isStepDone(currentMeta.key)} />
                    <div>
                      <div className="text-sm font-semibold text-foreground">
                        {isStepDone(currentMeta.key) ? 'Sudah Terisi' : 'Belum Ada'}
                      </div>
                      {status && (status.steps || []).find((s) => s.key === currentMeta.key) && (
                        <div className="text-[11px] text-muted-foreground">
                          Jumlah saat ini: {(status.steps.find((s) => s.key === currentMeta.key)?.count) ?? 0}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {currentMeta.module && (
                      <Button
                        variant="ghost"
                        onClick={() => handleOpenModule(currentMeta.module)}
                        className="h-9 border border-[var(--glass-border)]"
                        data-testid={`setup-open-${currentMeta.key}`}
                      >
                        Buka Modul <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    )}
                    {currentMeta.moduleSecondary && (
                      <Button
                        variant="ghost"
                        onClick={() => handleOpenModule(currentMeta.moduleSecondary)}
                        className="h-9 border border-[var(--glass-border)]"
                      >
                        Size <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    )}
                  </div>
                </div>
              </GlassPanel>

              <div className="flex items-start gap-2 p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <Info className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                <p className="text-[11px] text-muted-foreground">
                  Setelah Anda menambahkan data di modul, wizard akan otomatis mendeteksi perubahan. Kembali ke sini kapan saja lewat notifikasi "Next Actions" di dashboard.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-[var(--glass-border)] flex items-center justify-between gap-2 bg-[var(--glass-bg)]">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={handleDismiss}
              className="h-8 text-xs text-muted-foreground hover:text-foreground"
              data-testid="setup-dismiss-btn"
            >
              Jangan tampilkan lagi
            </Button>
            <Button
              variant="ghost"
              onClick={handleSkip}
              className="h-8 text-xs text-muted-foreground hover:text-foreground"
              data-testid="setup-skip-btn"
            >
              <SkipForward className="w-3 h-3 mr-1" /> Lewati (24 jam)
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={!canGoPrev}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="setup-prev-btn"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Sebelumnya
            </Button>
            {canGoNext ? (
              <Button
                onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}
                className="h-9"
                data-testid="setup-next-btn"
              >
                {step === 0 ? 'Mulai' : 'Selanjutnya'} <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            ) : (
              <Button
                onClick={handleDismiss}
                className="h-9"
                data-testid="setup-finish-btn"
              >
                <CheckCircle2 className="w-4 h-4 mr-1.5" /> Selesai
              </Button>
            )}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

export default SetupWizard;
