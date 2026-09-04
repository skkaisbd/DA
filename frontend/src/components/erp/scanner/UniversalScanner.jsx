/**
 * UniversalScanner.jsx — SSOT untuk semua barcode/QR scanning di ERP
 * Sprint A.1 — Konsolidasi 5 scanner menjadi 1
 *
 * Variants:
 *   - 'inline'  → Input field + tombol kamera (keyboard wedge auto-detect)
 *   - 'modal'   → Modal penuh dengan tab Kamera + Manual
 *   - 'button'  → Tombol kamera kecil saja (buka modal)
 *
 * Props:
 *   onScan(code, source)  — dipanggil dengan kode hasil scan
 *   variant               — 'inline' | 'modal' | 'button'
 *   open                  — (modal) apakah modal terlihat
 *   onClose               — (modal/button) fungsi tutup
 *   title                 — (modal) judul modal
 *   placeholder           — teks placeholder
 *   label                 — label atas input (inline)
 *   disabled              — boolean
 *   autoFocus             — boolean (inline)
 *   inputClassName        — className tambahan untuk input
 */
import { useState, useRef, useCallback, useEffect, useId } from 'react';
import {
  Camera, Keyboard, X, AlertTriangle, Loader2, Scan, ScanLine
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import Modal from '../Modal';
import { useCameraScanner } from './useScanner';

// ─── Internal: Camera + Manual modal contents ─────────────────────────────────
function ScannerModalContent({ onScan, onClose, title = 'Scan Barcode' }) {
  const uid = useId().replace(/:/g, '_');
  const elementId = `universal-qr-${uid}`;
  const [tab, setTab]           = useState('camera');
  const [manual, setManual]     = useState('');
  const [scanLoading, setScanLoading] = useState(false);

  const {
    cameraState, setCameraState, cameraError, startCamera, stopCamera
  } = useCameraScanner({ elementId });

  const handleDetected = useCallback(async (code, source) => {
    setScanLoading(true);
    try {
      await stopCamera();
      onScan(code, source);
      onClose?.();
    } finally {
      setScanLoading(false);
    }
  }, [onScan, onClose, stopCamera]);

  // Auto-start camera when on camera tab
  useEffect(() => {
    if (tab !== 'camera') return;
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      await startCamera(handleDetected);
    })();
    return () => { cancelled = true; };
  }, [tab, startCamera, handleDetected]);

  // Stop camera when switching away
  const switchTab = async (next) => {
    if (next === tab) return;
    if (tab === 'camera') await stopCamera();
    setManual('');
    setTab(next);
    if (next === 'camera') setCameraState('starting');
  };

  const onManualSubmit = async (e) => {
    e?.preventDefault();
    const code = manual.trim();
    if (!code) return;
    await handleDetected(code, 'manual');
  };

  return (
    <div className="space-y-3" data-testid="universal-scanner-content">
      {/* Tab switcher */}
      <div className="inline-flex rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-1 w-full">
        <button
          type="button"
          onClick={() => switchTab('camera')}
          className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-semibold transition-colors ${
            tab === 'camera'
              ? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))]'
              : 'text-muted-foreground hover:text-foreground'
          }`}
          data-testid="scanner-tab-camera"
        >
          <Camera className="w-3.5 h-3.5" /> Kamera
        </button>
        <button
          type="button"
          onClick={() => switchTab('manual')}
          className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-semibold transition-colors ${
            tab === 'manual'
              ? 'bg-[hsl(var(--primary)/0.15)] text-[hsl(var(--primary))]'
              : 'text-muted-foreground hover:text-foreground'
          }`}
          data-testid="scanner-tab-manual"
        >
          <Keyboard className="w-3.5 h-3.5" /> Input Manual
        </button>
      </div>

      {/* Camera tab */}
      {tab === 'camera' && (
        <div className="space-y-2">
          <div className="rounded-xl overflow-hidden border border-[var(--glass-border)]">
            <div
              id={elementId}
              className="w-full aspect-square bg-black/85"
              data-testid="scanner-viewport"
            />
          </div>
          <div className="text-center text-[11px] text-muted-foreground">
            {cameraState === 'starting' && (
              <span className="inline-flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Memulai kamera...
              </span>
            )}
            {cameraState === 'scanning' && 'Arahkan kamera ke QR code / barcode.'}
            {scanLoading && (
              <span className="inline-flex items-center gap-1 text-[hsl(var(--primary))]">
                <Loader2 className="w-3 h-3 animate-spin" /> Memproses...
              </span>
            )}
          </div>
          {cameraError && (
            <div
              className="bg-red-50 dark:bg-red-400/10 border border-red-300/20 rounded-lg p-2.5 text-xs text-red-600 dark:text-red-300 flex items-start gap-2"
              data-testid="scanner-camera-error"
            >
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>
                {cameraError}
                <button
                  type="button"
                  onClick={() => switchTab('manual')}
                  className="ml-2 underline font-semibold"
                  data-testid="scanner-switch-manual-cta"
                >
                  Pakai input manual
                </button>
              </span>
            </div>
          )}
        </div>
      )}

      {/* Manual tab */}
      {tab === 'manual' && (
        <form onSubmit={onManualSubmit} className="space-y-2" data-testid="scanner-manual-form">
          <label className="block text-xs font-medium text-foreground/70">Nomor / Kode</label>
          <Input
            autoFocus
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="Ketik atau scan..."
            className="font-mono"
            data-testid="scanner-manual-input"
          />
          <Button
            type="submit"
            disabled={scanLoading || !manual.trim()}
            className="w-full h-11"
            data-testid="scanner-manual-submit"
          >
            {scanLoading ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Memproses...
              </span>
            ) : 'Konfirmasi Kode'}
          </Button>
        </form>
      )}

      <div className="text-[10px] text-muted-foreground text-center">
        Tips: tekan{' '}
        <kbd className="px-1 py-0.5 border border-[var(--glass-border)] rounded bg-[var(--glass-bg)]">
          Input Manual
        </kbd>{' '}
        kalau kamera bermasalah.
      </div>
    </div>
  );
}

// ─── Modal Variant ────────────────────────────────────────────────────────────
function ScannerModal({ open, onClose, onScan, title = 'Scan Barcode' }) {
  if (!open) return null;
  return (
    <Modal
      onClose={onClose}
      title={title}
      size="sm"
      data-testid="universal-scanner-modal"
    >
      <ScannerModalContent onScan={onScan} onClose={onClose} title={title} />
    </Modal>
  );
}

// ─── Inline Variant ───────────────────────────────────────────────────────────
// Input dengan tombol kamera. Keyboard wedge auto-detected.
function ScannerInline({
  onScan, placeholder = 'Scan atau ketik barcode...', label, disabled,
  autoFocus = false, inputClassName = '', 'data-testid': testId
}) {
  const [value, setValue]       = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const inputRef                = useRef(null);
  const lastTsRef               = useRef(0);
  const isScannerRef            = useRef(false);
  const timerRef                = useRef(null);

  const WEDGE_INTERVAL = 30;
  const MIN_LEN = 3;

  const fireScan = useCallback((code) => {
    if (!code.trim()) return;
    setValue('');
    onScan?.(code.trim(), 'inline');
  }, [onScan]);

  const handleKeyDown = (e) => {
    const now = Date.now();
    const interval = now - lastTsRef.current;
    lastTsRef.current = now;

    if (e.key === 'Enter') {
      const code = value.trim();
      if (code.length >= MIN_LEN) {
        e.preventDefault();
        fireScan(code);
      }
      return;
    }
    if (e.key.length === 1 && interval < WEDGE_INTERVAL) {
      isScannerRef.current = true;
    }
    if (isScannerRef.current) {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const code = inputRef.current?.value?.trim() || '';
        if (code.length >= MIN_LEN) fireScan(code);
        isScannerRef.current = false;
      }, 150);
    }
  };

  // Camera modal onScan callback
  const handleModalScan = (code) => {
    setValue(code);
    setModalOpen(false);
    onScan?.(code, 'camera');
  };

  return (
    <>
      {label && (
        <label className="block text-xs font-medium text-foreground/70 mb-1">{label}</label>
      )}
      <div className="relative flex items-center gap-1" data-testid={testId || 'universal-scanner-inline'}>
        <Input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus={autoFocus}
          className={`font-mono pr-10 ${inputClassName}`}
          data-testid="scanner-inline-input"
        />
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          disabled={disabled}
          title="Buka kamera scanner"
          className="absolute right-2 text-muted-foreground hover:text-[hsl(var(--primary))] transition-colors disabled:opacity-40"
          data-testid="scanner-camera-btn"
        >
          <ScanLine className="w-4 h-4" />
        </button>
      </div>
      <ScannerModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onScan={handleModalScan}
        title="Scan Barcode"
      />
    </>
  );
}

// ─── Button Variant ───────────────────────────────────────────────────────────
// Hanya tombol yang membuka modal
function ScannerButton({
  onScan, title = 'Scan Barcode', label, disabled, size = 'sm', variant: btnVariant = 'outline',
  'data-testid': testId, className = ''
}) {
  const [open, setOpen] = useState(false);
  const handleScan = (code, source) => {
    setOpen(false);
    onScan?.(code, source);
  };
  return (
    <>
      <Button
        type="button"
        variant={btnVariant}
        size={size}
        onClick={() => setOpen(true)}
        disabled={disabled}
        className={`gap-1.5 ${className}`}
        data-testid={testId || 'scanner-button'}
      >
        <Scan className="w-3.5 h-3.5" />
        {label || 'Scan'}
      </Button>
      <ScannerModal open={open} onClose={() => setOpen(false)} onScan={handleScan} title={title} />
    </>
  );
}

// ─── Main Export ──────────────────────────────────────────────────────────────
/**
 * UniversalScanner — SSOT scanner component
 *
 * @example inline:
 *   <UniversalScanner variant="inline" onScan={code => handleScan(code)} />
 *
 * @example modal:
 *   <UniversalScanner variant="modal" open={showScanner} onClose={() => setShowScanner(false)}
 *     onScan={code => { setShowScanner(false); process(code); }} />
 *
 * @example button:
 *   <UniversalScanner variant="button" onScan={code => fill(code)} label="Scan SKU" />
 */
export default function UniversalScanner({
  variant = 'inline',
  onScan,
  open,
  onClose,
  title,
  placeholder,
  label,
  disabled,
  autoFocus,
  inputClassName,
  size,
  btnVariant,
  className,
  'data-testid': testId,
}) {
  if (variant === 'modal') {
    return (
      <ScannerModal
        open={open}
        onClose={onClose}
        onScan={onScan}
        title={title}
      />
    );
  }
  if (variant === 'button') {
    return (
      <ScannerButton
        onScan={onScan}
        title={title}
        label={label}
        disabled={disabled}
        size={size}
        variant={btnVariant}
        className={className}
        data-testid={testId}
      />
    );
  }
  // default: 'inline'
  return (
    <ScannerInline
      onScan={onScan}
      placeholder={placeholder}
      label={label}
      disabled={disabled}
      autoFocus={autoFocus}
      inputClassName={inputClassName}
      data-testid={testId}
    />
  );
}

// Named exports for convenience
export { ScannerModal, ScannerInline, ScannerButton, ScannerModalContent };
