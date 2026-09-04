/**
 * UniversalScanPortal.jsx
 *
 * Floating scan button yang bisa diakses dari mana saja di ERP.
 * Scan barcode/QR → resolve ke entity (Asset/Bundle/Material/WO/PO/Roll/DO)
 * Tampilkan result card dengan quick actions.
 *
 * Usage (di PortalShell):
 *   <UniversalScanPortal token={token} onNavigate={setModule} />
 */
import { useState, useCallback, useEffect } from 'react';
import {
  ScanLine, X, CheckCircle2, AlertTriangle, Loader2, Clock,
  Package, Box, Layers, ClipboardList, ShoppingCart, Columns, Truck, History,
} from 'lucide-react';
import { ScannerModalContent } from './UniversalScanner';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

// ─── Entity type config ───────────────────────────────────────────────────────
const ENTITY_CFG = {
  asset:          { icon: Package,       color: 'text-blue-600 dark:text-blue-400',    bg: 'bg-blue-50 dark:bg-blue-400/10',    border: 'border-blue-300 dark:border-blue-400/20',    label: 'Aset' },
  bundle:         { icon: Box,           color: 'text-purple-600 dark:text-purple-400',  bg: 'bg-purple-50 dark:bg-purple-400/10',  border: 'border-purple-300 dark:border-purple-400/20',  label: 'Bundle Produksi' },
  material:       { icon: Layers,        color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-400/10', border: 'border-emerald-300 dark:border-emerald-400/20', label: 'Material' },
  work_order:     { icon: ClipboardList, color: 'text-orange-600 dark:text-orange-400',  bg: 'bg-orange-50 dark:bg-orange-400/10',  border: 'border-orange-300 dark:border-orange-400/20',  label: 'Work Order' },
  purchase_order: { icon: ShoppingCart,  color: 'text-indigo-600 dark:text-indigo-400',  bg: 'bg-indigo-50 dark:bg-indigo-400/10',  border: 'border-indigo-300 dark:border-indigo-400/20',  label: 'Purchase Order' },
  fabric_roll:    { icon: Columns,       color: 'text-yellow-600 dark:text-yellow-400',  bg: 'bg-yellow-50 dark:bg-yellow-400/10',  border: 'border-yellow-300 dark:border-yellow-400/20',  label: 'Roll Kain' },
  delivery_order: { icon: Truck,         color: 'text-sky-600 dark:text-sky-400',     bg: 'bg-sky-50 dark:bg-sky-400/10',     border: 'border-sky-300 dark:border-sky-400/20',     label: 'Delivery Order' },
};

// ─── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  if (!status) return null;
  const STATUS_COLOR = {
    active: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-300', available: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-300',
    in_use: 'bg-blue-50 dark:bg-blue-400/15 text-blue-600 dark:text-blue-300',       in_stock: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-300',
    draft: 'bg-zinc-50 dark:bg-zinc-400/15 text-zinc-300',         inactive: 'bg-zinc-50 dark:bg-zinc-400/15 text-zinc-300',
    maintenance: 'bg-yellow-50 dark:bg-yellow-400/15 text-yellow-600 dark:text-yellow-300',
    completed: 'bg-sky-50 dark:bg-sky-400/15 text-sky-600 dark:text-sky-300',       done: 'bg-sky-50 dark:bg-sky-400/15 text-sky-600 dark:text-sky-300',
    rejected: 'bg-red-50 dark:bg-red-400/15 text-red-600 dark:text-red-300',        cancelled: 'bg-red-50 dark:bg-red-400/15 text-red-600 dark:text-red-300',
    in_progress: 'bg-orange-50 dark:bg-orange-400/15 text-orange-600 dark:text-orange-300',
    approved: 'bg-emerald-50 dark:bg-emerald-400/15 text-emerald-600 dark:text-emerald-300',
  };
  const cls = STATUS_COLOR[status] || 'bg-zinc-50 dark:bg-zinc-400/15 text-zinc-300';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

// ─── Scan Result Card ─────────────────────────────────────────────────────────
function ScanResultCard({ result, onAction, onScanAgain }) {
  const cfg = ENTITY_CFG[result.entity_type] || ENTITY_CFG.asset;
  const Icon = cfg.icon;

  return (
    <div className={`rounded-2xl border ${cfg.border} ${cfg.bg} p-4 space-y-3`} data-testid="scan-result-card">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${cfg.bg} border ${cfg.border}`}>
          <Icon size={18} className={cfg.color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] font-bold uppercase tracking-widest ${cfg.color}`}>
              {cfg.label}
            </span>
            <StatusBadge status={result.status} />
          </div>
          <p className="text-sm font-semibold text-foreground mt-0.5 truncate">{result.display_name}</p>
          <p className="text-xs text-zinc-500 font-mono">{result.entity_number}</p>
        </div>
      </div>

      {/* Meta */}
      {result.meta && Object.keys(result.meta).length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(result.meta).map(([k, v]) => (
            <div key={k} className="bg-black/20 rounded-lg px-2 py-1.5">
              <div className="text-[10px] text-zinc-500">{k}</div>
              <div className="text-xs text-zinc-200 font-medium truncate" title={v}>{v || '—'}</div>
            </div>
          ))}
        </div>
      )}

      {/* Quick Actions */}
      {result.quick_actions?.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {result.quick_actions.map((qa) => (
            <button
              key={qa.id}
              onClick={() => onAction(qa)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border ${cfg.border} ${cfg.color} hover:${cfg.bg} transition-colors`}
              data-testid={`quick-action-${qa.id}`}
            >
              {qa.label}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={onScanAgain}
        className="w-full py-2 text-xs font-medium text-zinc-400 hover:text-foreground border border-white/10 rounded-xl transition-colors"
        data-testid="scan-again-btn"
      >
        Scan Lagi
      </button>
    </div>
  );
}

// ─── Not Found Card ───────────────────────────────────────────────────────────
function NotFoundCard({ code, onScanAgain }) {
  return (
    <div className="rounded-2xl border border-red-300 dark:border-red-500/20 bg-red-50 dark:bg-red-400/5 p-4 space-y-3" data-testid="scan-not-found-card">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 bg-red-50 dark:bg-red-400/10 border border-red-300 dark:border-red-500/20">
          <AlertTriangle size={18} className="text-red-700 dark:text-red-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">Kode Tidak Ditemukan</p>
          <p className="text-xs text-zinc-500 font-mono mt-0.5">{code}</p>
        </div>
      </div>
      <p className="text-xs text-zinc-400">
        Kode ini tidak cocok dengan aset, bundle, material, WO, PO, roll kain, atau delivery order yang terdaftar.
      </p>
      <button
        onClick={onScanAgain}
        className="w-full py-2 text-xs font-medium text-zinc-400 hover:text-foreground border border-white/10 rounded-xl transition-colors"
        data-testid="scan-again-btn-notfound"
      >
        Scan Lagi
      </button>
    </div>
  );
}

// ─── History Item ─────────────────────────────────────────────────────────────
function HistoryItem({ item }) {
  const cfg = ENTITY_CFG[item.entity_type];
  const Icon = cfg?.icon || Package;
  const time = new Date(item.scanned_at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  return (
    <div className="flex items-center gap-2.5 py-1.5 border-b border-foreground/5 last:border-0">
      {item.found ? (
        <div className={`w-6 h-6 rounded-md flex-shrink-0 flex items-center justify-center ${cfg?.bg || 'bg-foreground/5'}`}>
          <Icon size={11} className={cfg?.color || 'text-zinc-400'} />
        </div>
      ) : (
        <div className="w-6 h-6 rounded-md flex-shrink-0 flex items-center justify-center bg-red-50 dark:bg-red-400/10">
          <X size={11} className="text-red-700 dark:text-red-400" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-200 truncate">
          {item.display_name || item.raw_code}
        </p>
        {item.entity_number && item.entity_number !== item.display_name && (
          <p className="text-[10px] text-zinc-500 font-mono">{item.entity_number}</p>
        )}
      </div>
      <span className="text-[10px] text-zinc-600 flex-shrink-0">{time}</span>
    </div>
  );
}

// ─── Main Portal ──────────────────────────────────────────────────────────────
export default function UniversalScanPortal({ token, onNavigate }) {
  const [open, setOpen]               = useState(false);
  const [scanning, setScanning]       = useState(false);
  const [resolving, setResolving]     = useState(false);
  const [result, setResult]           = useState(null);     // null | {found, ...}
  const [history, setHistory]         = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const headers = { Authorization: `Bearer ${token}` };

  const loadHistory = useCallback(async () => {
    if (!token) return;
    setHistoryLoading(true);
    try {
      const r = await axios.get(`${API}/api/scan/history?limit=20`, { headers });
      setHistory(r.data || []);
    } catch (_) { /* noop */ }
    finally { setHistoryLoading(false); }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const openPortal = () => {
    setOpen(true);
    setResult(null);
    setScanning(true);
    setShowHistory(false);
    loadHistory();
  };

  const closePortal = () => {
    setOpen(false);
    setScanning(false);
    setResult(null);
    setShowHistory(false);
  };

  const handleScan = useCallback(async (code) => {
    if (!code.trim()) return;
    setScanning(false);
    setResolving(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/api/scan/resolve`, { code }, { headers });
      setResult(r.data);
      loadHistory();
    } catch (e) {
      setResult({ found: false, raw_code: code });
    } finally {
      setResolving(false);
    }
  }, [token, loadHistory]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAction = (qa) => {
    if (qa.module && onNavigate) {
      onNavigate(qa.module);
      closePortal();
    }
  };

  const scanAgain = () => {
    setResult(null);
    setScanning(true);
  };

  // Keyboard shortcut: Ctrl+Shift+S
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'S') {
        e.preventDefault();
        if (open) closePortal();
        else openPortal();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={openPortal}
        title="Universal Scan (Ctrl+Shift+S)"
        className="fixed bottom-6 right-6 z-40 w-12 h-12 rounded-full bg-indigo-600 hover:bg-indigo-500 text-foreground shadow-lg shadow-indigo-500/30 flex items-center justify-center transition-all hover:scale-110 active:scale-95"
        data-testid="universal-scan-fab"
      >
        <ScanLine size={20} />
      </button>

      {/* Portal modal */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
          onClick={(e) => e.target === e.currentTarget && closePortal()}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-foreground/40 backdrop-blur-sm" onClick={closePortal} />

          {/* Panel */}
          <div className="relative w-full sm:max-w-md bg-zinc-900 border border-white/10 rounded-t-3xl sm:rounded-2xl shadow-2xl overflow-hidden"
            data-testid="universal-scan-portal"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 pt-5 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-100 dark:bg-indigo-500/15 border border-indigo-300 dark:border-indigo-500/20 flex items-center justify-center">
                  <ScanLine size={15} className="text-indigo-600 dark:text-indigo-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">Universal Scan</p>
                  <p className="text-[10px] text-zinc-500">Asset • Bundle • Material • WO • PO • Roll • DO</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setShowHistory(!showHistory); if (!showHistory) loadHistory(); }}
                  className={`w-8 h-8 rounded-xl flex items-center justify-center transition-colors ${showHistory ? 'bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400' : 'text-zinc-500 hover:text-foreground hover:bg-foreground/5'}`}
                  data-testid="scan-history-toggle"
                  title="Riwayat Scan"
                >
                  <History size={14} />
                </button>
                <button onClick={closePortal} className="w-8 h-8 rounded-xl text-zinc-400 hover:text-foreground hover:bg-foreground/5 flex items-center justify-center">
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="px-5 pb-6 space-y-4 max-h-[80vh] overflow-y-auto">
              {/* History panel */}
              {showHistory && (
                <div className="bg-foreground/5 border border-white/10 rounded-xl p-3">
                  <p className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
                    <History size={12} /> Riwayat Scan Terakhir
                  </p>
                  {historyLoading ? (
                    <div className="flex items-center gap-2 text-xs text-zinc-500 py-2">
                      <Loader2 size={12} className="animate-spin" /> Memuat...
                    </div>
                  ) : history.length === 0 ? (
                    <p className="text-xs text-zinc-500 py-2">Belum ada riwayat scan.</p>
                  ) : (
                    <div>
                      {history.map((h) => <HistoryItem key={h.id} item={h} />)}
                    </div>
                  )}
                </div>
              )}

              {/* Scanner (camera/manual) — inline content, no nested modal */}
              {scanning && !resolving && (
                <div data-testid="universal-scan-scanner-area">
                  {/* onClose=undefined: portal has its own close button; we don't want scanner to close the whole portal */}
                  <ScannerModalContent onScan={handleScan} onClose={undefined} title="Scan Barcode / QR Code" />
                </div>
              )}

              {/* Resolving state */}
              {resolving && (
                <div className="flex items-center justify-center gap-3 py-10" data-testid="scan-resolving">
                  <Loader2 size={20} className="animate-spin text-indigo-600 dark:text-indigo-400" />
                  <p className="text-sm text-zinc-300">Mengidentifikasi...</p>
                </div>
              )}

              {/* Result */}
              {!scanning && !resolving && result && (
                result.found
                  ? <ScanResultCard result={result} onAction={handleAction} onScanAgain={scanAgain} />
                  : <NotFoundCard code={result.raw_code} onScanAgain={scanAgain} />
              )}
            </div>

            {/* Keyboard hint */}
            <div className="px-5 pb-4 text-center">
              <p className="text-[10px] text-zinc-600">
                Shortcut:{' '}
                <kbd className="px-1.5 py-0.5 bg-foreground/5 border border-white/10 rounded text-zinc-500">Ctrl</kbd>
                {' + '}
                <kbd className="px-1.5 py-0.5 bg-foreground/5 border border-white/10 rounded text-zinc-500">Shift</kbd>
                {' + '}
                <kbd className="px-1.5 py-0.5 bg-foreground/5 border border-white/10 rounded text-zinc-500">S</kbd>
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
