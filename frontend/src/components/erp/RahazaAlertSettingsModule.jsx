import { useState, useEffect, useCallback } from 'react';
import {
  Siren, Activity, ShieldAlert, Package, PlayCircle, Save, RefreshCw,
  AlertTriangle, CheckCircle2, Sliders, Bell, Eye, Info, Zap, XCircle,
} from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from './moduleAtoms';
import { toast } from 'sonner';

/* ─── PT Rahaza ERP · Alert Settings (Phase 18A) ──────────────────────────
   Admin configures the 3 rule-engine thresholds and can manually evaluate
   (preview / publish) alerts. The background task auto-evaluates every
   `check_interval_seconds` on the backend.
──────────────────────────────────────────────────────────────────────── */

const RULE_META = {
  behind_target: {
    icon: Activity,
    label: 'Behind Target',
    tone: 'text-amber-400',
    bg: 'bg-amber-400/10',
    border: 'border-amber-300/25',
  },
  qc_fail_spike: {
    icon: ShieldAlert,
    label: 'QC Fail Spike',
    tone: 'text-red-400',
    bg: 'bg-red-400/10',
    border: 'border-red-300/25',
  },
  low_stock: {
    icon: Package,
    label: 'Low Stock',
    tone: 'text-[hsl(var(--primary))]',
    bg: 'bg-[hsl(var(--primary)/0.1)]',
    border: 'border-[hsl(var(--primary)/0.25)]',
  },
};

function sevColor(sev) {
  if (sev === 'error') return 'text-red-300 bg-red-400/10 border-red-300/30';
  if (sev === 'warning') return 'text-amber-300 bg-amber-400/10 border-amber-300/30';
  if (sev === 'success') return 'text-emerald-300 bg-emerald-400/10 border-emerald-300/30';
  return 'text-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.1)] border-[hsl(var(--primary)/0.25)]';
}

export default function RahazaAlertSettingsModule({ token }) {
  const [settings, setSettings] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [dirty, setDirty] = useState(false);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/rahaza/alerts/settings', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setDirty(false);
      } else {
        toast.error('Gagal memuat setting alert');
      }
    } catch (e) {
      toast.error('Error: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchPreview = useCallback(async () => {
    try {
      const res = await fetch('/api/rahaza/alerts/preview', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setPreview(await res.json());
      }
    } catch (e) {
      // silent
    }
  }, [token]);

  useEffect(() => { fetchSettings(); fetchPreview(); }, [fetchSettings, fetchPreview]);

  const updateField = (key, value) => {
    setSettings((s) => ({ ...s, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const res = await fetch('/api/rahaza/alerts/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setDirty(false);
        toast.success('Setting alert tersimpan');
        fetchPreview();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Gagal menyimpan');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleEvaluate = async () => {
    setEvaluating(true);
    try {
      const res = await fetch('/api/rahaza/alerts/evaluate', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const c = data.counts || {};
        const total = (c.behind_target || 0) + (c.qc_fail_spike || 0) + (c.low_stock || 0);
        const published = c.published || 0;
        if (total === 0) {
          toast.success('Semua rule hijau — tidak ada kondisi alert saat ini');
        } else {
          toast.success(
            `${total} kondisi terdeteksi · ${published} notifikasi dikirim`,
            { description: 'Cek bell di pojok kanan atas untuk detail.' }
          );
        }
        setPreview(data);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Evaluate gagal');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setEvaluating(false);
    }
  };

  if (loading || !settings) {
    return (
      <div className="space-y-4" data-testid="alert-settings-loading">
        <PageHeader title="Memuat setting alert..." />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="alert-settings-module">
      <PageHeader
        icon={Siren}
        eyebrow="Produksi · Alert Engine"
        title="Setting Alert Engine"
        description="Atur ambang alert otomatis untuk 3 kondisi produksi: line behind target, QC fail spike, dan stok material rendah. Sistem memeriksa kondisi ini secara periodik dan mengirim notifikasi realtime ke supervisor & manager."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => { fetchSettings(); fetchPreview(); }}
              className="h-9 border border-[var(--glass-border)]"
              data-testid="alert-settings-reload"
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Muat Ulang
            </Button>
            <Button
              onClick={handleEvaluate}
              disabled={evaluating}
              className="h-9"
              data-testid="alert-settings-evaluate"
            >
              <PlayCircle className={`w-4 h-4 mr-1.5 ${evaluating ? 'animate-pulse' : ''}`} />
              {evaluating ? 'Mengevaluasi…' : 'Evaluasi Sekarang'}
            </Button>
            <Button
              onClick={handleSave}
              disabled={!dirty || saving}
              variant={dirty ? 'default' : 'outline'}
              className="h-9"
              data-testid="alert-settings-save"
            >
              <Save className={`w-4 h-4 mr-1.5 ${saving ? 'animate-pulse' : ''}`} />
              {saving ? 'Menyimpan…' : dirty ? 'Simpan Perubahan' : 'Tersimpan'}
            </Button>
          </div>
        }
      />

      {/* Enable switch */}
      <GlassPanel className={`p-4 border flex items-center justify-between gap-4 ${settings.enabled ? 'border-emerald-300/30 bg-emerald-400/[0.03]' : 'border-[var(--glass-border)] opacity-90'}`}>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl grid place-items-center border ${settings.enabled ? 'bg-emerald-400/12 border-emerald-300/30' : 'bg-muted/30 border-[var(--glass-border)]'}`}>
            {settings.enabled ? <Zap className="w-5 h-5 text-emerald-400" /> : <XCircle className="w-5 h-5 text-foreground/40" />}
          </div>
          <div>
            <Label className="text-sm font-bold text-foreground">
              Alert Engine {settings.enabled ? 'Aktif' : 'Non-aktif'}
            </Label>
            <div className="text-[11px] text-foreground/60">
              {settings.enabled
                ? `Sistem memeriksa rule setiap ${Math.round((settings.check_interval_seconds || 300) / 60)} menit dan mengirim notifikasi otomatis.`
                : 'Background evaluator berhenti. Anda masih bisa evaluate manual.'}
            </div>
          </div>
        </div>
        <Switch
          checked={!!settings.enabled}
          onCheckedChange={(v) => updateField('enabled', v)}
          data-testid="alert-settings-enabled-switch"
        />
      </GlassPanel>

      {/* Three rule cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Rule 1: Behind Target */}
        <RuleCard
          meta={RULE_META.behind_target}
          title="Behind Target"
          description="Alert ketika output harian suatu line di bawah persentase target."
          thresholdLabel="Ambang output minimum"
          thresholdHint={`Fire bila actual/target < ${Math.round((settings.behind_target_pct || 0.7) * 100)}%`}
          testId="rule-behind-target"
        >
          <PercentSlider
            value={settings.behind_target_pct || 0.7}
            onChange={(v) => updateField('behind_target_pct', v)}
            testId="slider-behind-target"
          />
        </RuleCard>

        {/* Rule 2: QC Fail Spike */}
        <RuleCard
          meta={RULE_META.qc_fail_spike}
          title="QC Fail Spike"
          description="Alert ketika rasio QC fail melewati ambang dalam window waktu tertentu."
          thresholdLabel="Ambang fail rate"
          thresholdHint={`Fire bila fail > ${Math.round((settings.qc_spike_pct || 0.15) * 100)}% dalam ${settings.qc_spike_window_min || 60} menit`}
          testId="rule-qc-spike"
        >
          <PercentSlider
            value={settings.qc_spike_pct || 0.15}
            onChange={(v) => updateField('qc_spike_pct', v)}
            testId="slider-qc-spike"
          />
          <div className="grid grid-cols-2 gap-2 mt-3">
            <div>
              <Label className="text-[10px] text-foreground/60">Window (menit)</Label>
              <Input
                type="number"
                min="5"
                max="1440"
                value={settings.qc_spike_window_min || 60}
                onChange={(e) => updateField('qc_spike_window_min', parseInt(e.target.value) || 60)}
                className="h-8 text-xs"
                data-testid="input-qc-window"
              />
            </div>
            <div>
              <Label className="text-[10px] text-foreground/60">Min events</Label>
              <Input
                type="number"
                min="1"
                value={settings.qc_spike_min_events || 5}
                onChange={(e) => updateField('qc_spike_min_events', parseInt(e.target.value) || 5)}
                className="h-8 text-xs"
                data-testid="input-qc-min-events"
              />
            </div>
          </div>
        </RuleCard>

        {/* Rule 3: Low Stock */}
        <RuleCard
          meta={RULE_META.low_stock}
          title="Low Stock"
          description="Alert ketika stok material turun di bawah persen dari nilai minimum."
          thresholdLabel="Ambang stok kritis"
          thresholdHint={`Fire error bila stok < ${Math.round((settings.low_stock_pct_of_min || 0.2) * 100)}% dari min_stock`}
          testId="rule-low-stock"
        >
          <PercentSlider
            value={settings.low_stock_pct_of_min || 0.2}
            onChange={(v) => updateField('low_stock_pct_of_min', v)}
            testId="slider-low-stock"
          />
        </RuleCard>
      </div>

      {/* Interval setting */}
      <GlassCard className="p-4" hover={false}>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-xl grid place-items-center bg-[hsl(var(--primary)/0.12)] border border-[hsl(var(--primary)/0.25)]">
            <Sliders className="w-4 h-4 text-[hsl(var(--primary))]" />
          </div>
          <div>
            <Label className="text-sm font-bold text-foreground">Interval Evaluasi Otomatis</Label>
            <div className="text-[11px] text-foreground/60">Seberapa sering background task memeriksa rule (detik).</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Input
            type="number"
            min="30"
            max="86400"
            step="30"
            value={settings.check_interval_seconds || 300}
            onChange={(e) => updateField('check_interval_seconds', parseInt(e.target.value) || 300)}
            className="h-9 max-w-[180px]"
            data-testid="input-check-interval"
          />
          <span className="text-xs text-foreground/70">
            = setiap <b>{Math.round((settings.check_interval_seconds || 300) / 60)} menit</b>
            {(settings.check_interval_seconds || 300) < 60 && ' (min 30 detik)'}
          </span>
        </div>
      </GlassCard>

      {/* Live preview panel */}
      <GlassCard className="p-4" hover={false} data-testid="alert-preview-panel">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl grid place-items-center bg-amber-400/12 border border-amber-300/30">
              <Eye className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <Label className="text-sm font-bold text-foreground">Preview Alert Saat Ini</Label>
              <div className="text-[11px] text-foreground/60">
                Kondisi yang AKAN menjadi alert jika klik "Evaluasi Sekarang" (tanpa publish).
              </div>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchPreview}
            className="h-8 border border-[var(--glass-border)]"
            data-testid="alert-preview-refresh"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
          </Button>
        </div>

        {/* KPI strip */}
        {preview && (
          <div className="grid grid-cols-3 gap-2 mb-3">
            {Object.entries(RULE_META).map(([key, meta]) => {
              const Icon = meta.icon;
              const count = (preview.counts || {})[key] || 0;
              return (
                <div key={key} className={`p-2.5 rounded-lg border flex items-center gap-2 ${meta.bg} ${meta.border}`}>
                  <Icon className={`w-4 h-4 ${meta.tone}`} />
                  <div className="min-w-0">
                    <div className="text-[9px] uppercase tracking-wider font-semibold text-foreground/55">{meta.label}</div>
                    <div className={`text-base font-bold ${count > 0 ? meta.tone : 'text-foreground/50'}`}>
                      {count}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Alert list */}
        {preview && (preview.preview || []).length === 0 ? (
          <div className="text-center py-6">
            <CheckCircle2 className="w-9 h-9 text-emerald-400 mx-auto mb-2" />
            <div className="text-sm font-semibold text-foreground">Semua rule hijau</div>
            <div className="text-xs text-foreground/55 mt-1">
              Tidak ada kondisi yang melanggar ambang saat ini.
            </div>
          </div>
        ) : preview ? (
          <div className="space-y-2">
            {(preview.preview || []).map((a, i) => (
              <div
                key={`${a.type}-${i}`}
                className={`p-3 rounded-lg border flex items-start gap-3 ${sevColor(a.severity)}`}
                data-testid={`preview-alert-${i}`}
              >
                <div className="w-7 h-7 rounded-lg grid place-items-center bg-[var(--glass-bg)] border border-[var(--glass-border)] flex-shrink-0">
                  {a.severity === 'error'
                    ? <AlertTriangle className="w-3.5 h-3.5" />
                    : a.severity === 'warning'
                      ? <AlertTriangle className="w-3.5 h-3.5" />
                      : <Info className="w-3.5 h-3.5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm">{a.title}</span>
                    <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-full border border-current/40">
                      {a.type}
                    </span>
                  </div>
                  <div className="text-xs text-foreground/75 mt-0.5">{a.message}</div>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-3 flex items-center gap-2 text-[10px] text-foreground/45 italic border-t border-[var(--glass-border)] pt-2">
          <Bell className="w-3 h-3" />
          <span>
            Notifikasi yang di-publish akan muncul di bell pojok kanan atas (realtime via SSE) dan di daftar notifikasi.
          </span>
        </div>
      </GlassCard>
    </div>
  );
}

// ─── Subcomponents ──────────────────────────────────────────────────────────
function RuleCard({ meta, title, description, thresholdLabel, thresholdHint, children, testId }) {
  const Icon = meta.icon;
  return (
    <GlassCard className="p-4" hover={false} data-testid={testId}>
      <div className="flex items-start gap-3 mb-3">
        <div className={`w-10 h-10 rounded-xl grid place-items-center border flex-shrink-0 ${meta.bg} ${meta.border}`}>
          <Icon className={`w-5 h-5 ${meta.tone}`} />
        </div>
        <div className="min-w-0 flex-1">
          <Label className="text-sm font-bold text-foreground">{title}</Label>
          <div className="text-[11px] text-foreground/65 leading-relaxed mt-0.5">{description}</div>
        </div>
      </div>
      <div className="space-y-2">
        <div>
          <Label className="text-[10px] text-foreground/55 uppercase tracking-wider font-semibold">{thresholdLabel}</Label>
          <div className="text-[11px] text-foreground/65 italic">{thresholdHint}</div>
        </div>
        {children}
      </div>
    </GlassCard>
  );
}

function PercentSlider({ value, onChange, testId }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <Slider
          value={[pct]}
          min={1}
          max={99}
          step={1}
          onValueChange={(v) => onChange((v?.[0] || 0) / 100)}
          className="flex-1"
          data-testid={testId}
        />
        <div className="flex items-center gap-1 flex-shrink-0">
          <Input
            type="number"
            min="1"
            max="99"
            value={pct}
            onChange={(e) => {
              const n = Math.max(1, Math.min(99, parseInt(e.target.value) || 0));
              onChange(n / 100);
            }}
            className="w-14 h-7 text-center text-xs"
          />
          <span className="text-xs text-foreground/60">%</span>
        </div>
      </div>
    </div>
  );
}
