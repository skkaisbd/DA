/**
 * AssetScannerModal — Thin wrapper di atas UniversalScanner
 * Sprint A.1: Refactored to use UniversalScanner SSOT.
 * Business logic (asset lookup + lokasi update) tetap di sini.
 */
import { useState, useCallback } from 'react';
import UniversalScanner from './scanner/UniversalScanner';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

export default function AssetScannerModal({ token, onScanned, onClose }) {
  const [loading,  setLoading]  = useState(false);
  const [scanError, setScanError] = useState('');

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const resolveAsset = useCallback(async (code) => {
    const cleaned = String(code || '').trim().toUpperCase();
    if (!cleaned) throw new Error('Kode asset kosong');
    // FASE 20 — dulu '/api/dewi/assets/by-code/{code}', yang (a) tidak pernah ada
    // di backend dan (b) menunjuk DOMAIN YANG SALAH: `dewi_assets` (aset karyawan,
    // koleksi `da_assets`, berkunci `asset_code`). Pemanggil scanner ini adalah
    // `AssetManagementPortal` yang bekerja di domain ASET TETAP ('/api/assets',
    // koleksi `dewi_assets`, berkunci `asset_number`) — terbukti dari handler
    // `onScanned` yang membaca `asset.asset_number` & `asset.location`.
    // Endpoint yang tepat sudah tersedia dan memang dibuat untuk ini:
    //   GET /api/assets/scan-by-number/{asset_number}
    const res = await fetch(
      `${API}/api/assets/scan-by-number/${encodeURIComponent(cleaned)}`,
      { headers }
    );
    if (res.status === 404) throw new Error(`Asset "${cleaned}" tidak ditemukan`);
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).detail || ''; } catch (_) { /* noop */ }
      throw new Error(detail || `Gagal mengambil asset (HTTP ${res.status})`);
    }
    return await res.json();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleScan = useCallback(async (code, source) => {
    setScanError('');
    setLoading(true);
    try {
      const asset = await resolveAsset(code);
      // Domain aset tetap memakai field `name` (bukan `asset_name`) — tanpa ini
      // toast selalu jatuh ke kode mentah walau asetnya berhasil ditemukan.
      toast.success(`Asset ditemukan: ${asset.name || asset.asset_name || code}`);
      if (onScanned) onScanned(asset, { payload: code, source });
      onClose?.();
    } catch (e) {
      setScanError(e.message || 'Gagal mengambil asset');
      toast.error(e.message || 'Gagal mengambil asset');
    } finally {
      setLoading(false);
    }
  }, [resolveAsset, onScanned, onClose]);

  return (
    <>
      <UniversalScanner
        variant="modal"
        open={true}
        onClose={onClose}
        title="Scan Asset"
        onScan={loading ? undefined : handleScan}
        data-testid="asset-scanner-modal"
      />
      {scanError && (
        <div className="fixed bottom-4 right-4 z-[9999] bg-red-500/20 border border-red-300/30 rounded-lg p-3 text-xs text-red-200 max-w-xs shadow-xl">
          {scanError}
        </div>
      )}
    </>
  );
}
