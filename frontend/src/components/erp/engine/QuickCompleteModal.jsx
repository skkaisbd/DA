/**
 * QuickCompleteModal.jsx
 *
 * One-click wizard that executes the FULL production flow for a PO:
 *   1. Vendor Shipment
 *   2. Terima Shipment
 *   3. Inspeksi Material
 *   4. Production Job
 *   5. Progress Produksi (100%)
 *   6. Buyer Shipment
 *   7. Status PO → Completed
 */
import { useState } from 'react';
import {
  Zap, X, Truck, ClipboardCheck, Factory, TrendingUp,
  Package, CheckCircle2, AlertTriangle, Loader2, ChevronRight,
  Info, SkipForward, RefreshCcw, Check
} from 'lucide-react';
import { apiPost } from '../../../lib/api';
import { toast } from 'sonner';

const STEP_META = [
  { step: 1, icon: Truck,         label: 'Vendor Shipment',          desc: 'Buat pengiriman material dari vendor ke produksi' },
  { step: 2, icon: CheckCircle2,  label: 'Terima Shipment',           desc: 'Tandai shipment sebagai diterima' },
  { step: 3, icon: ClipboardCheck,label: 'Inspeksi Material',         desc: 'Rekam semua material diterima tanpa defect' },
  { step: 4, icon: Factory,       label: 'Production Job',            desc: 'Buat job produksi dari shipment' },
  { step: 5, icon: TrendingUp,    label: 'Progress Produksi (100%)', desc: 'Rekam progres produksi 100% untuk semua item' },
  { step: 6, icon: Package,       label: 'Buyer Shipment',            desc: 'Buat shipment ke buyer untuk semua barang jadi' },
  { step: 7, icon: CheckCircle2,  label: 'PO → Completed',            desc: 'Tandai PO sebagai selesai' },
];

const STATUS_CLASS = {
  created:  'bg-green-100 text-green-700 border-green-200',
  done:     'bg-green-100 text-green-700 border-green-200',
  reused:   'bg-blue-100 text-blue-700 border-blue-200',
  skipped:  'bg-muted text-muted-foreground border-border',
  pending:  'bg-muted/40 text-muted-foreground border-border',
  running:  'bg-amber-50 text-amber-600 border-amber-200',
  error:    'bg-red-100 text-red-600 border-red-200',
};

const STATUS_LABEL = {
  created: 'Dibuat',
  done:    'Selesai',
  reused:  'Sudah ada (digunakan)',
  skipped: 'Dilewati',
  pending: 'Menunggu',
  running: 'Memproses...',
  error:   'Error',
};

// ─── Main component ──────────────────────────────────────────────────────────
export default function QuickCompleteModal({ po, onClose, onSuccess }) {
  const [phase, setPhase] = useState('confirm'); // confirm | running | result
  const [skipBuyerShipment, setSkipBuyerShipment] = useState(false);
  const [result, setResult] = useState(null);
  const [stepStatuses, setStepStatuses] = useState({});
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState(null);

  const totalItems = (po.items || []).reduce((s, i) => s + (Number(i.qty) || 0), 0);
  const vendorOk   = !!po.vendor_id;
  const itemsOk    = (po.items || []).length > 0 && totalItems > 0;
  const canRun     = vendorOk && itemsOk && !['Completed', 'Closed'].includes(po.status);

  // Animate steps after receiving result
  const animateSteps = async (steps) => {
    for (const s of steps) {
      setCurrentStep(s.step);
      setStepStatuses(prev => ({ ...prev, [s.step]: 'running' }));
      await delay(320);
      setStepStatuses(prev => ({ ...prev, [s.step]: s.status }));
      await delay(180);
    }
    setCurrentStep(0);
  };

  const handleRun = async () => {
    setPhase('running');
    setStepStatuses({});
    setError(null);
    // Show all steps as pending first
    const init = {};
    STEP_META.forEach(m => { init[m.step] = 'pending'; });
    setStepStatuses(init);

    try {
      const data = await apiPost(`/production-pos/${po.id}/quick-complete`, {
        skip_buyer_shipment: skipBuyerShipment,
      });
      setResult(data);
      await animateSteps(data.steps);
      setPhase('result');
      onSuccess?.();
      toast.success(`PO ${po.po_number} berhasil di-Quick Complete!`);
    } catch (e) {
      setError(e.message || 'Terjadi kesalahan');
      setPhase('error');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-card rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/60 bg-gradient-to-r from-violet-600 to-blue-600">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-card/20 rounded-lg">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-bold text-white text-lg leading-tight">Quick Complete</p>
              <p className="text-violet-200 text-xs">{po.po_number}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-card/20 transition-colors text-white"
            data-testid="quick-complete-close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">

          {/* ── CONFIRM phase ── */}
          {phase === 'confirm' && (
            <>
              {/* Pre-flight checks */}
              <div className="space-y-2">
                <p className="text-sm font-semibold text-foreground/90 mb-2">Status PO</p>
                {[
                  { ok: itemsOk,  pass: `${(po.items||[]).length} item, total ${totalItems} pcs`, fail: 'PO tidak memiliki item / qty = 0' },
                  { ok: vendorOk, pass: `Vendor: ${po.vendor_name || po.vendor_id}`, fail: 'Vendor belum ditetapkan' },
                  { ok: !['Completed','Closed'].includes(po.status), pass: `Status: ${po.status}`, fail: `PO sudah ${po.status}` },
                ].map((chk, i) => (
                  <div key={i} className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border text-sm ${
                    chk.ok ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'
                  }`}>
                    {chk.ok
                      ? <Check className="w-4 h-4 text-green-600 flex-shrink-0" />
                      : <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />}
                    {chk.ok ? chk.pass : chk.fail}
                  </div>
                ))}
              </div>

              {/* Flow preview */}
              <div>
                <p className="text-sm font-semibold text-foreground/90 mb-2">Langkah yang akan dijalankan</p>
                <div className="border border-border rounded-xl overflow-hidden divide-y divide-border/60">
                  {STEP_META.filter(m => !(skipBuyerShipment && m.step === 6)).map((m, idx, arr) => (
                    <div key={m.step} className="flex items-start gap-3 px-4 py-3 bg-card hover:bg-muted/60/50">
                      <div className="flex items-center justify-center w-6 h-6 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex-shrink-0 mt-0.5">
                        {m.step}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">{m.label}</p>
                        <p className="text-xs text-muted-foreground/70 mt-0.5">{m.desc}</p>
                      </div>
                      {idx < arr.length - 1 && <ChevronRight className="w-4 h-4 text-muted-foreground/50 flex-shrink-0 mt-1" />}
                    </div>
                  ))}
                </div>
              </div>

              {/* Options */}
              <div className="flex items-start gap-3 bg-muted/40 border border-border rounded-xl p-4">
                <input
                  type="checkbox"
                  id="skip-buyer"
                  checked={skipBuyerShipment}
                  onChange={e => setSkipBuyerShipment(e.target.checked)}
                  className="mt-0.5 w-4 h-4 accent-violet-600 cursor-pointer"
                  data-testid="skip-buyer-checkbox"
                />
                <label htmlFor="skip-buyer" className="cursor-pointer">
                  <p className="text-sm font-medium text-foreground/90">Lewati Buyer Shipment</p>
                  <p className="text-xs text-muted-foreground/70 mt-0.5">Centang jika tidak ingin langsung membuat buyer shipment</p>
                </label>
              </div>

              {/* Warning */}
              <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-xl p-4">
                <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700">
                  Quick Complete akan membuat semua data produksi secara otomatis dengan asumsi <strong>100% material diterima, 0 defect</strong>. Langkah yang sudah ada akan digunakan ulang (tidak digandakan).
                </p>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-2.5 border-2 border-border rounded-xl text-sm font-medium text-foreground/90 hover:bg-muted/60 transition-colors"
                >
                  Batal
                </button>
                <button
                  onClick={handleRun}
                  disabled={!canRun}
                  data-testid="quick-complete-run-btn"
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white text-sm font-bold hover:from-violet-700 hover:to-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg"
                >
                  <Zap className="w-4 h-4" />
                  Jalankan Quick Complete
                </button>
              </div>
            </>
          )}

          {/* ── RUNNING phase ── */}
          {(phase === 'running') && (
            <div className="space-y-3">
              <div className="flex items-center justify-center gap-3 py-4">
                <Loader2 className="w-6 h-6 text-violet-600 animate-spin" />
                <p className="text-sm font-semibold text-foreground/90">Memproses alur produksi...</p>
              </div>
              <StepList stepStatuses={stepStatuses} currentStep={currentStep} skipBuyerShipment={skipBuyerShipment} />
            </div>
          )}

          {/* ── RESULT phase ── */}
          {phase === 'result' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4">
                <CheckCircle2 className="w-7 h-7 text-green-500 flex-shrink-0" />
                <div>
                  <p className="font-bold text-green-800 text-lg">Berhasil!</p>
                  <p className="text-sm text-green-600">{result.message}</p>
                </div>
              </div>
              <StepList stepStatuses={stepStatuses} skipBuyerShipment={skipBuyerShipment} />
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Nomor Job', value: result.job_number },
                  { label: 'Total Item', value: `${result.total_items} pcs` },
                ].map(kv => (
                  <div key={kv.label} className="bg-muted/40 border border-border rounded-xl p-3 text-center">
                    <p className="text-xs text-muted-foreground">{kv.label}</p>
                    <p className="font-bold text-foreground mt-1">{kv.value || '—'}</p>
                  </div>
                ))}
              </div>
              <button
                onClick={onClose}
                className="w-full px-4 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white text-sm font-bold hover:from-violet-700 hover:to-blue-700 transition-all"
                data-testid="quick-complete-done-btn"
              >
                Selesai
              </button>
            </div>
          )}

          {/* ── ERROR phase ── */}
          {phase === 'error' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
                <AlertTriangle className="w-6 h-6 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold text-red-800">Gagal</p>
                  <p className="text-sm text-red-600 mt-1">{error}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <button onClick={onClose} className="flex-1 px-4 py-2.5 border-2 border-border rounded-xl text-sm font-medium text-foreground/90 hover:bg-muted/60">Tutup</button>
                <button
                  onClick={() => { setPhase('confirm'); setError(null); }}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-violet-600 text-white text-sm font-bold hover:bg-violet-700"
                >
                  <RefreshCcw className="w-4 h-4" /> Coba Lagi
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Step list sub-component ───────────────────────────────────────────────────
function StepList({ stepStatuses, currentStep, skipBuyerShipment }) {
  return (
    <div className="border border-border rounded-xl overflow-hidden divide-y divide-border/60">
      {STEP_META.map(m => {
        const st = stepStatuses[m.step] || 'pending';
        const isSkipped = skipBuyerShipment && m.step === 6;
        const effectiveSt = isSkipped ? 'skipped' : st;
        const isCurrent = currentStep === m.step;
        const Icon = m.icon;
        const badgeCls = STATUS_CLASS[effectiveSt] || STATUS_CLASS.pending;
        return (
          <div
            key={m.step}
            className={`flex items-center gap-3 px-4 py-3 transition-colors ${
              isCurrent ? 'bg-amber-50' : 'bg-card'
            }`}
          >
            <div className={`flex items-center justify-center w-7 h-7 rounded-full flex-shrink-0 border ${badgeCls}`}>
              {isCurrent
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : effectiveSt === 'created' || effectiveSt === 'done'
                  ? <Check className="w-3.5 h-3.5" />
                  : effectiveSt === 'skipped'
                    ? <SkipForward className="w-3.5 h-3.5" />
                    : <Icon className="w-3.5 h-3.5" />
              }
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{m.label}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium flex-shrink-0 ${badgeCls}`}>
              {isCurrent ? 'Memproses...' : STATUS_LABEL[effectiveSt]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Helper ────────────────────────────────────────────────────────────────────
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
