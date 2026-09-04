import { useState, useEffect, useCallback, useMemo } from 'react';
import { Barcode, Printer, Search, Trash2, RefreshCw, History, AlertTriangle,
  Factory, Package, Shirt, Plus } from 'lucide-react';
import { GlassCard, GlassPanel } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { apiGet, apiFetch } from '../../lib/api';

// FASE H-3 (2026-08-16) — "Buat Barcode".
// Kenapa layar ini ada: endpoint label bahan & barang jadi sudah lama tersedia
// dengan NOL pemanggil UI, jadi dari sudut pandang pemakai barcode gudang tidak
// bisa dicetak sama sekali. Nilai barcode SELALU kode master — tidak ada kotak
// untuk mengetik kode bebas, karena label yang kodenya dikarang akan discan
// menjadi item yang tidak ada di sistem (aturan F14).

const MAX_LABELS = 500;

const KINDS = [
  { id: 'material', label: 'Bahan & Aksesoris', icon: Package },
  { id: 'fg', label: 'Barang Jadi', icon: Shirt },
];

function KindTab({ kind, active, onClick }) {
  const Icon = kind.icon;
  return (
    <button
      onClick={() => onClick(kind.id)}
      data-testid={`barcode-tab-${kind.id}`}
      className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium border transition-colors ${
        active
          ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] border-transparent'
          : 'bg-[var(--glass-bg)] text-muted-foreground border-[var(--glass-border)] hover:text-foreground'
      }`}
    >
      <Icon className="w-4 h-4" /> {kind.label}
    </button>
  );
}

function CartRow({ row, onCopies, onRemove }) {
  return (
    <tr className={`border-t border-[var(--glass-border)] ${row.master_linked === false ? 'bg-red-50 dark:bg-red-500/10' : ''}`}
      data-testid={`barcode-cart-row-${row.code}`}>
      <td className="px-3 py-2 font-mono text-xs text-foreground">
        {row.code}
        {row.master_linked === false && (
          <div className="text-[10px] text-red-600 dark:text-red-400 font-sans mt-0.5"
            data-testid={`barcode-unlinked-${row.code}`}>
            Belum ada di master Barang Jadi — labelnya tidak bisa dicetak.
            {row.reason ? ` ${row.reason}` : ''}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{row.name}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {[row.color, row.size].filter(Boolean).join(' · ') || '—'}
      </td>
      <td className="px-3 py-2 text-right">
        <input type="number" min="1" max="200" value={row.copies}
          onChange={e => onCopies(row.code, e.target.value)}
          className="h-8 w-20 rounded-md border border-input bg-background px-2 text-right text-xs text-foreground"
          data-testid={`barcode-copies-${row.code}`} />
      </td>
      <td className="px-3 py-2 text-right">
        <button onClick={() => onRemove(row.code)} title="Hapus baris"
          className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-400/10 text-muted-foreground hover:text-red-600"
          data-testid={`barcode-remove-${row.code}`}>
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </td>
    </tr>
  );
}

export default function WMSBarcodeModule() {
  const [kind, setKind] = useState('material');
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [itemsMeta, setItemsMeta] = useState({ total: 0, returned: 0 });
  const [loadingItems, setLoadingItems] = useState(false);
  const [cart, setCart] = useState([]);
  const [includeStock, setIncludeStock] = useState(true);
  const [note, setNote] = useState('');
  const [pos, setPos] = useState([]);
  const [poId, setPoId] = useState('');
  const [poInfo, setPoInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [okMsg, setOkMsg] = useState('');
  const [history, setHistory] = useState([]);

  const loadItems = useCallback(async () => {
    setLoadingItems(true);
    try {
      const d = await apiGet(`/wms/barcode/items?kind=${kind}&q=${encodeURIComponent(q)}&limit=60`);
      setItems(d.items || []);
      setItemsMeta({ total: d.total || 0, returned: d.returned || 0 });
    } catch (e) { setError(e.message); } finally { setLoadingItems(false); }
  }, [kind, q]);

  const loadHistory = useCallback(async () => {
    try { setHistory(await apiGet('/wms/barcode/history?limit=15')); } catch { /* riwayat opsional */ }
  }, []);

  useEffect(() => { loadItems(); }, [loadItems]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => {
    apiGet('/wms/barcode/production-options?limit=40').then(setPos).catch(() => setPos([]));
  }, []);

  const totalLabels = useMemo(
    () => cart.reduce((s, r) => s + (Number(r.copies) || 0), 0), [cart]);
  const unlinked = useMemo(() => cart.filter(r => r.master_linked === false), [cart]);
  const overLimit = totalLabels > MAX_LABELS;

  const addItem = (it) => {
    setOkMsg('');
    setCart(prev => {
      const found = prev.find(r => r.code === it.code);
      if (found) return prev.map(r => r.code === it.code ? { ...r, copies: (Number(r.copies) || 0) + 1 } : r);
      return [...prev, {
        material_id: it.id, code: it.code, name: it.name, size: it.size,
        color: it.color, copies: 1, master_linked: true,
      }];
    });
  };

  const setCopies = (code, val) => setCart(prev => prev.map(
    r => r.code === code ? { ...r, copies: val === '' ? '' : Math.max(1, Math.min(200, Number(val) || 1)) } : r));
  const removeRow = (code) => setCart(prev => prev.filter(r => r.code !== code));

  const loadFromPO = async () => {
    if (!poId) return;
    setError(''); setOkMsg(''); setBusy(true);
    try {
      const d = await apiGet(`/wms/barcode/from-production?po_id=${encodeURIComponent(poId)}`);
      setKind('fg');
      setPoInfo(d);
      setCart((d.rows || []).map(r => ({ ...r, copies: Math.max(1, Math.min(200, r.copies || 1)) })));
      setOkMsg(`${(d.rows || []).length} artikel dari ${d.po_number} dimuat · ${d.total_copies} label mengikuti jumlah produksi`);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const printPdf = async () => {
    setError(''); setOkMsg(''); setBusy(true);
    try {
      const res = await apiFetch('/wms/barcode/batch-pdf', {
        method: 'POST',
        body: JSON.stringify({
          kind,
          rows: cart.filter(r => r.master_linked !== false)
            .map(r => ({ id: r.material_id || undefined, code: r.code, copies: Number(r.copies) || 1 })),
          include_stock: kind === 'material' ? includeStock : false,
          source: poInfo ? 'produksi' : 'manual',
          po_id: poInfo?.po_id || null,
          note,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(typeof err.detail === 'string' ? err.detail : `Gagal mencetak (HTTP ${res.status})`);
        return;
      }
      const jobNo = res.headers.get('X-Barcode-Job') || '';
      const labels = res.headers.get('X-Barcode-Labels') || totalLabels;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `barcode-${kind}-${jobNo || 'batch'}.pdf`;
      a.click();
      // Jangan cabut URL-nya seketika: di mesin lambat unduhan bisa dibatalkan
      // sebelum browser selesai membaca blob-nya.
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      setOkMsg(`${labels} label tercetak ke PDF · nomor cetak ${jobNo}`);
      loadHistory();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="wms-barcode-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Barcode className="w-6 h-6" /> Buat Barcode
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Cetak label barcode bahan/aksesoris & barang jadi. Kode barcode selalu diambil
            dari master — supaya label yang tertempel bisa discan menjadi item yang benar.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {KINDS.map(k => (
            <KindTab key={k.id} kind={k} active={kind === k.id} onClick={(id) => { setKind(id); setPoInfo(null); }} />
          ))}
        </div>
      </div>

      {/* Sumber otomatis: ikut produksi */}
      <GlassCard className="p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <Factory className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm text-foreground font-medium">Otomatis dari produksi</span>
          <SmartNativeSelect value={poId} onChange={e => setPoId(e.target.value)}
            className="h-9 px-3 text-sm min-w-[260px]" data-testid="barcode-po-select">
            <option value="">— Pilih PO produksi —</option>
            {pos.map(p => (
              <option key={p.id} value={p.id}>
                {p.po_number} · {p.business_type} · {p.total_qty} pcs
              </option>
            ))}
          </SmartNativeSelect>
          <Button onClick={loadFromPO} disabled={!poId || busy} data-testid="barcode-load-po-btn">
            <Plus className="w-4 h-4 mr-1.5" /> Ambil artikel & jumlahnya
          </Button>
          <span className="text-xs text-muted-foreground">
            Jumlah label mengikuti qty PO — tidak diketik ulang.
          </span>
        </div>
        {poInfo && (
          <div className="mt-3 text-xs text-muted-foreground" data-testid="barcode-po-info">
            Sumber: <b className="text-foreground">{poInfo.po_number}</b> ({poInfo.business_type}) ·
            {' '}{poInfo.rows?.length || 0} artikel · {poInfo.total_copies} label
            {poInfo.unlinked_count > 0 && (
              <span className="text-red-600 dark:text-red-400">
                {' '}· {poInfo.unlinked_count} artikel belum ada di master
              </span>
            )}
          </div>
        )}
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Pemilih dari master */}
        <GlassCard className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-foreground">Pilih dari master</h2>
            <span className="text-xs text-muted-foreground" data-testid="barcode-items-meta">
              {itemsMeta.returned} dari {itemsMeta.total} item
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input value={q} onChange={e => setQ(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') loadItems(); }}
                placeholder="Cari kode atau nama item…"
                className="h-9 w-full pl-8 pr-3 rounded-lg border border-input bg-background text-sm text-foreground"
                data-testid="barcode-search-input" />
            </div>
            <Button variant="ghost" onClick={loadItems} disabled={loadingItems}
              className="border border-[var(--glass-border)]" data-testid="barcode-search-btn">
              <RefreshCw className={`w-4 h-4 ${loadingItems ? 'animate-spin' : ''}`} />
            </Button>
          </div>
          <GlassPanel className="p-0 overflow-hidden max-h-[380px] overflow-y-auto">
            <table className="w-full text-sm">
              <tbody>
                {items.length === 0 ? (
                  <tr><td className="px-3 py-8 text-center text-sm text-muted-foreground"
                    data-testid="barcode-items-empty">
                    Tidak ada item yang cocok.
                  </td></tr>
                ) : items.map(it => (
                  <tr key={it.id} className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]">
                    <td className="px-3 py-2">
                      <div className="font-mono text-xs text-foreground">{it.code}</div>
                      <div className="text-xs text-muted-foreground">{it.name}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{it.unit}</td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="ghost" onClick={() => addItem(it)}
                        className="h-7 px-2 border border-[var(--glass-border)]"
                        data-testid={`barcode-add-${it.code}`}>
                        <Plus className="w-3.5 h-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GlassPanel>
        </GlassCard>

        {/* Daftar cetak */}
        <GlassCard className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h2 className="text-base font-semibold text-foreground">Daftar cetak</h2>
            <span className={`text-xs px-2 py-1 rounded-full border ${
              overLimit ? 'bg-red-50 dark:bg-red-500/10 border-red-300/40 text-red-600 dark:text-red-400'
                : 'bg-[var(--glass-bg)] border-[var(--glass-border)] text-muted-foreground'}`}
              data-testid="barcode-total-labels">
              {totalLabels} label · {cart.length} item
            </span>
          </div>

          <GlassPanel className="p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[var(--glass-bg)]">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-3 py-2">Kode</th>
                  <th className="px-3 py-2">Nama</th>
                  <th className="px-3 py-2">Varian</th>
                  <th className="px-3 py-2 text-right">Lembar</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {cart.length === 0 ? (
                  <tr><td colSpan={5} className="px-3 py-10 text-center" data-testid="barcode-cart-empty">
                    <Barcode className="w-8 h-8 mx-auto text-foreground/20 mb-2" strokeWidth={1.5} />
                    <div className="text-sm text-foreground/70">Belum ada item dipilih</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      Pilih dari master di sebelah, atau ambil otomatis dari PO produksi.
                    </div>
                  </td></tr>
                ) : cart.map(r => (
                  <CartRow key={r.code} row={r} onCopies={setCopies} onRemove={removeRow} />
                ))}
              </tbody>
            </table>
          </GlassPanel>

          {kind === 'material' && (
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={includeStock} onChange={e => setIncludeStock(e.target.checked)}
                data-testid="barcode-include-stock" />
              Cetak stok & lokasi di label
            </label>
          )}

          <input value={note} onChange={e => setNote(e.target.value)}
            placeholder="Catatan cetak (opsional) — mis. 'label rak B, giliran pagi'"
            className="h-9 w-full px-3 rounded-lg border border-input bg-background text-sm text-foreground"
            data-testid="barcode-note-input" />

          {unlinked.length > 0 && (
            <div className="flex items-start gap-2 text-xs bg-red-50 dark:bg-red-500/10 border border-red-300/40 rounded-lg px-3 py-2 text-red-700 dark:text-red-300"
              data-testid="barcode-unlinked-warning">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                {unlinked.length} artikel PO belum punya varian di master Barang Jadi, jadi
                labelnya TIDAK dicetak. Buat variannya dulu di Master Produk — mencetak barcode
                dengan kode yang tidak dikenal sistem hanya memindahkan masalahnya ke rak.
              </div>
            </div>
          )}
          {overLimit && (
            <div className="text-xs bg-red-50 dark:bg-red-500/10 border border-red-300/40 rounded-lg px-3 py-2 text-red-700 dark:text-red-300"
              data-testid="barcode-limit-warning">
              Total {totalLabels} label melebihi batas {MAX_LABELS} lembar per cetak.
              Kurangi jumlahnya atau cetak beberapa kali.
            </div>
          )}
          {error && (
            <div className="text-xs bg-red-50 dark:bg-red-500/10 border border-red-300/40 rounded-lg px-3 py-2 text-red-700 dark:text-red-300"
              data-testid="barcode-error">{error}</div>
          )}
          {okMsg && (
            <div className="text-xs bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-300/40 rounded-lg px-3 py-2 text-emerald-700 dark:text-emerald-300"
              data-testid="barcode-success">{okMsg}</div>
          )}

          <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" onClick={() => { setCart([]); setPoInfo(null); setOkMsg(''); setError(''); }}
              disabled={cart.length === 0} className="border border-[var(--glass-border)]"
              data-testid="barcode-clear-btn">Kosongkan</Button>
            <Button onClick={printPdf}
              disabled={busy || overLimit || cart.filter(r => r.master_linked !== false).length === 0}
              data-testid="barcode-print-btn">
              <Printer className="w-4 h-4 mr-1.5" /> {busy ? 'Menyiapkan…' : 'Cetak PDF'}
            </Button>
          </div>
        </GlassCard>
      </div>

      {/* Riwayat cetak */}
      <GlassCard className="p-0 overflow-hidden">
        <div className="px-4 py-3 flex items-center gap-2 border-b border-[var(--glass-border)]">
          <History className="w-4 h-4 text-muted-foreground" />
          <h2 className="text-base font-semibold text-foreground">Riwayat cetak</h2>
          <span className="text-xs text-muted-foreground">
            Menjawab “kenapa ada dua label berkode sama di gudang”.
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)]">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-2">No. Cetak</th>
                <th className="px-4 py-2">Jenis</th>
                <th className="px-4 py-2">Sumber</th>
                <th className="px-4 py-2 text-right">Item</th>
                <th className="px-4 py-2 text-right">Lembar</th>
                <th className="px-4 py-2">Oleh</th>
                <th className="px-4 py-2">Waktu</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground"
                  data-testid="barcode-history-empty">Belum ada riwayat cetak.</td></tr>
              ) : history.map(h => (
                <tr key={h.id} className="border-t border-[var(--glass-border)]"
                  data-testid={`barcode-history-${h.job_number}`}>
                  <td className="px-4 py-2 font-mono text-xs text-foreground">{h.job_number}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {h.kind === 'fg' ? 'Barang Jadi' : 'Bahan'}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {h.source === 'produksi' ? 'Dari produksi' : 'Manual'}
                  </td>
                  <td className="px-4 py-2 text-right text-xs text-foreground">{h.item_count}</td>
                  <td className="px-4 py-2 text-right text-xs font-semibold text-foreground">{h.total_labels}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{h.created_by_name || '—'}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {h.created_at ? new Date(h.created_at).toLocaleString('id-ID') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
