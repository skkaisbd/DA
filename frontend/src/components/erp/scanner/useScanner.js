/**
 * useScanner.js — Universal Scanner Hook (Sprint A.1)
 * SSOT untuk semua scanner logic: camera lifecycle, keyboard wedge detection.
 *
 * Keyboard wedge detection:
 *   - Saat keystroke interval < 30ms DAN panjang >= 4 karakter → tandai sebagai scanner input
 *   - Pada Enter → trigger onScan
 */
import { useEffect, useRef, useState, useCallback, useId } from 'react';

// ─── Camera Hook ─────────────────────────────────────────────────────────────
export function useCameraScanner({ elementId, onScan, enabled = false }) {
  const scannerRef = useRef(null);
  const [cameraState, setCameraState] = useState('idle');
  // idle | starting | scanning | blocked | unsupported | stopping
  const [cameraError, setCameraError] = useState('');

  const stopCamera = useCallback(async () => {
    try {
      if (scannerRef.current) {
        const inst = scannerRef.current;
        scannerRef.current = null;
        if (inst.isScanning) {
          try { await inst.stop(); } catch (_) { /* noop */ }
        }
        try { await inst.clear(); } catch (_) { /* noop */ }
      }
    } catch (_) { /* noop */ }
    setCameraState('idle');
  }, []);

  const startCamera = useCallback(async (onDetected) => {
    setCameraError('');
    setCameraState('starting');
    try {
      const el = document.getElementById(elementId);
      if (!el) {
        setCameraState('unsupported');
        setCameraError('Scanner element tidak ditemukan.');
        return;
      }
      if (scannerRef.current) await stopCamera();

      // Dynamic import to avoid bundle bloat if not used
      const { Html5Qrcode } = await import('html5-qrcode');

      let cameras = [];
      try {
        cameras = await Html5Qrcode.getCameras();
      } catch {
        setCameraState('blocked');
        setCameraError('Kamera tidak dapat diakses. Pastikan izin kamera diberikan.');
        return;
      }
      if (!cameras || cameras.length === 0) {
        setCameraState('unsupported');
        setCameraError('Tidak ada kamera terdeteksi di perangkat ini.');
        return;
      }

      // Prefer back camera
      const preferred =
        cameras.find((c) => /back|environment|rear/i.test(c.label)) ||
        cameras[cameras.length - 1] ||
        cameras[0];

      const instance = new Html5Qrcode(elementId, { verbose: false });
      scannerRef.current = instance;

      const config = {
        fps: 10,
        qrbox: (w, h) => {
          const minEdge = Math.min(w, h);
          const box = Math.floor(minEdge * 0.7);
          return { width: box, height: box };
        },
        aspectRatio: 1.0,
      };

      let handled = false;
      await instance.start(
        preferred.id,
        config,
        async (decodedText) => {
          if (handled) return;
          handled = true;
          try { await instance.pause(true); } catch (_) { /* noop */ }
          onDetected(decodedText, 'camera');
        },
        () => { /* ignore per-frame errors */ },
      );
      setCameraState('scanning');
    } catch (e) {
      setCameraState('blocked');
      setCameraError(e?.message || 'Tidak bisa memulai scanner. Cek izin kamera.');
    }
  }, [elementId, stopCamera]);

  // Cleanup on unmount
  useEffect(() => () => { stopCamera(); }, [stopCamera]);

  return { cameraState, setCameraState, cameraError, startCamera, stopCamera };
}

// ─── Keyboard Wedge Hook ─────────────────────────────────────────────────────
// Keyboard wedge scanners emit chars at < 30ms intervals.
// Detects this pattern and fires onScan(code) on Enter.
export function useKeyboardWedge({ onScan, enabled = true }) {
  const bufferRef  = useRef('');
  const lastTsRef  = useRef(0);
  const isScanRef  = useRef(false);
  const timerRef   = useRef(null);
  const INTERVAL   = 30;   // ms — if < this → scanner hardware
  const MIN_LEN    = 3;    // min chars to consider a scanner read
  const FLUSH_WAIT = 150;  // ms after last key to auto-flush (no Enter)

  const flush = useCallback(() => {
    const code = bufferRef.current.trim();
    bufferRef.current = '';
    isScanRef.current = false;
    lastTsRef.current = 0;
    if (code.length >= MIN_LEN && onScan) onScan(code, 'wedge');
  }, [onScan]);

  const handleKeyDown = useCallback((e) => {
    if (!enabled) return;
    const now = Date.now();
    const interval = now - lastTsRef.current;
    lastTsRef.current = now;

    if (e.key === 'Enter') {
      if (bufferRef.current.trim().length >= MIN_LEN) {
        e.preventDefault();
        flush();
      }
      return;
    }

    if (e.key === 'Escape') {
      bufferRef.current = '';
      isScanRef.current = false;
      return;
    }

    // Only accumulate printable single chars
    if (e.key.length !== 1) return;

    // If interval < threshold → scanner hardware
    if (interval < INTERVAL) isScanRef.current = true;

    bufferRef.current += e.key;

    // Reset auto-flush timer
    if (timerRef.current) clearTimeout(timerRef.current);
    if (isScanRef.current) {
      timerRef.current = setTimeout(flush, FLUSH_WAIT);
    }
  }, [enabled, flush]);

  return { handleKeyDown };
}
