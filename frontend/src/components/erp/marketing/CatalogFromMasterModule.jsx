/**
 * CatalogFromMasterModule — ISI KATALOG TOKO DARI MASTER PRODUK INTERNAL.
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * Jalur yang sudah ada hanya bisa menambah **satu varian ke satu katalog** per
 * aksi. Untuk 9 toko × puluhan varian itu ratusan klik — dan yang terjadi di
 * lapangan bukan "staf sabar", melainkan **katalog dibiarkan kosong**. Katalog
 * kosong berarti item pesanan hasil impor tidak bisa ditautkan ke master, jadi
 * **HPP dan marjin per pesanan tidak bisa dihitung sama sekali**.
 *
 * Karena itu layar ini: pilih produk master (kiri) → pilih toko tujuan (kanan) →
 * satu tombol. HPP, kategori, berat, dan harga resmi SELALU dibawa dari master
 * (tidak ada kolom untuk mengetiknya di sini — itulah cara "HPP Rp 0" lahir).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Layers, Search, Store, PackagePlus, Loader2, RefreshCw, CheckCircle2,
  AlertTriangle, Info, ChevronDown, ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { PageHeader } from '../moduleAtoms';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

export default function CatalogFromMasterModule({ token, onAssigned }) {
  const [q, setQ] = useState('');
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [pickedFg, setPickedFg] = useState({});      // fg_material_id → true
  const [pickedAcc, setPickedAcc] = useState({});    // account_id → true
  const [open, setOpen] = useState({});              // model_id → expanded
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [priceMode, setPriceMode] = useState('master');   // 'master' | 'kosong'
  const [alertQty, setAlertQty] = useState('10');

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const jsonHeaders = useMemo(
    () => ({ ...headers, 'Content-Type': 'application/json' }), [headers]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/api/marketing/accounts?status=active`, { headers });
        const b = await r.json().catch(() => ({}));
        setAccounts(Array.isArray(b) ? b : (b.accounts || b.data || []));
      } catch { setAccounts([]); }
    })();
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set('q', q.trim());
      const only = Object.keys(pickedAcc).filter((k) => pickedAcc[k]);
      if (only.length === 1) qs.set('account_id', only[0]);
      const r = await fetch(`${API}/api/marketing/catalogs/master-products?${qs}`, { headers });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal memuat master produk');
      setProducts(b.products || []);
      setOpen((prev) => {
        const next = { ...prev };
        (b.products || []).slice(0, 3).forEach((p) => { next[p.model_id] = next[p.model_id] ?? true; });
        return next;
      });
    } catch (e) {
      toast.error(e.message, { duration: 9000 });
      setProducts([]);
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, q, JSON.stringify(pickedAcc)]);

  useEffect(() => { load(); }, [load]);

  const fgCount = Object.values(pickedFg).filter(Boolean).length;
  const accCount = Object.values(pickedAcc).filter(Boolean).length;

  const toggleModel = (p, on) => {
    setPickedFg((prev) => {
      const next = { ...prev };
      p.variants.forEach((v) => {
        if (on && !v.in_catalog) next[v.fg_material_id] = true;
        if (!on) delete next[v.fg_material_id];
      });
      return next;
    });
  };

  const submit = async () => {
    if (!accCount) { toast.error('Pilih dulu toko tujuannya'); return; }
    if (!fgCount) { toast.error('Pilih dulu produk/varian yang dijual'); return; }
    setBusy(true);
    setResult(null);
    try {
      const r = await fetch(`${API}/api/marketing/catalogs/assign-from-master`, {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          account_ids: Object.keys(pickedAcc).filter((k) => pickedAcc[k]),
          fg_material_ids: Object.keys(pickedFg).filter((k) => pickedFg[k]),
          price_mode: priceMode,
          stock_alert_threshold: Number(alertQty) >= 0 ? Number(alertQty) : 10,
        }),
      });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal mengisi katalog');
      setResult(b);
      toast.success(b.message, { duration: 10000 });
      setPickedFg({});
      load();
      onAssigned?.();
    } catch (e) {
      toast.error(e.message, { duration: 10000 });
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="catalog-from-master-module">
      <PageHeader
        eyebrow="PORTAL MARKETING · KATALOG"
        title="Isi Katalog dari Master Produk"
        subtitle="Pilih produk yang dijual, tempelkan ke beberapa toko sekaligus — HPP & harga resmi ikut dari master"
        icon={Layers}
        actions={(
          <Button variant="outline" size="sm" onClick={load} data-testid="cfm-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Muat Ulang
          </Button>
        )}
      />

      <div className="rounded-[var(--radius-md)] border border-blue-500/30 bg-blue-500/5 p-3">
        <p className="text-xs flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 mt-px shrink-0 text-blue-500" />
          <span>
            Katalog toko adalah jembatan antara <b>pesanan marketplace</b> dan <b>master produk</b>.
            Tanpa itu, item pesanan hasil impor tidak punya HPP sehingga <b>marjin per pesanan
            tidak bisa dihitung</b>. HPP, kategori, berat, dan harga resmi selalu diambil dari
            master — tidak ada kolom untuk mengetiknya di sini.
          </span>
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── TOKO TUJUAN ─────────────────────────────────────────────── */}
        <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold flex items-center gap-1.5">
              <Store className="w-4 h-4" /> Toko tujuan
            </p>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" className="h-7 text-[11px]"
                onClick={() => setPickedAcc(Object.fromEntries(accounts.map((a) => [a.id, true])))}
                data-testid="cfm-all-stores">Semua</Button>
              <Button size="sm" variant="ghost" className="h-7 text-[11px]"
                onClick={() => setPickedAcc({})}>Kosongkan</Button>
            </div>
          </div>
          <div className="space-y-1.5 max-h-[360px] overflow-y-auto">
            {accounts.map((a) => (
              <label key={a.id}
                className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-border
                  px-2 py-1.5 cursor-pointer hover:border-[hsl(var(--primary))]"
                data-testid={`cfm-store-${a.account_code}`}>
                <Checkbox checked={!!pickedAcc[a.id]}
                  onCheckedChange={(v) => setPickedAcc((p) => ({ ...p, [a.id]: !!v }))} />
                <span className="text-xs flex-1">{a.account_name}</span>
                <Badge variant="outline" className="text-[10px]">{a.platform}</Badge>
              </label>
            ))}
            {accounts.length === 0 && (
              <p className="text-xs text-muted-foreground">Belum ada toko aktif.</p>
            )}
          </div>
        </div>

        {/* ── MASTER PRODUK ───────────────────────────────────────────── */}
        <div className="lg:col-span-2 rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <p className="text-sm font-semibold">Master produk internal</p>
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Cari kode / nama produk / kategori…"
                data-testid="cfm-search"
                className="w-full h-9 pl-8 pr-3 rounded-[var(--radius-sm)] border border-border
                  bg-[hsl(var(--background))] text-sm text-foreground
                  placeholder:text-muted-foreground focus:outline-none
                  focus:ring-2 focus:ring-[hsl(var(--primary))]" />
            </div>
          </div>

          {loading ? (
            <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          ) : products.length === 0 ? (
            <div className="py-10 text-center" data-testid="cfm-empty">
              <AlertTriangle className="w-7 h-7 mx-auto text-amber-500 mb-2" />
              <p className="text-sm font-medium">Belum ada produk master yang cocok.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Master produk (model + varian FG) dibuat di modul <b>R&amp;D / Master Produk</b> —
                katalog toko hanya menempelkan produk yang sudah ada di sana.
              </p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[430px] overflow-y-auto" data-testid="cfm-product-list">
              {products.map((p) => {
                const expanded = !!open[p.model_id];
                const selectable = p.variants.filter((v) => !v.in_catalog);
                const allPicked = selectable.length > 0
                  && selectable.every((v) => pickedFg[v.fg_material_id]);
                return (
                  <div key={p.model_id} className="rounded-[var(--radius-sm)] border border-border">
                    <div className="flex items-center gap-2 px-2 py-2">
                      <button type="button" onClick={() => setOpen((o) => ({ ...o, [p.model_id]: !expanded }))}
                        className="text-muted-foreground" data-testid={`cfm-toggle-${p.code}`}>
                        {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>
                      <Checkbox checked={allPicked} disabled={selectable.length === 0}
                        onCheckedChange={(v) => toggleModel(p, !!v)}
                        data-testid={`cfm-model-${p.code}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold truncate">
                          <span className="font-mono text-muted-foreground mr-1.5">{p.code}</span>
                          {p.name}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {p.category_name || 'tanpa kategori'} · HPP {rp(p.hpp)} ·
                          harga resmi {rp(p.retail_price_master)} ·
                          {' '}{p.variant_count} varian
                          {p.in_catalog_count > 0 && ` · ${p.in_catalog_count} sudah di katalog`}
                        </p>
                      </div>
                      {p.hpp === 0 && (
                        <Badge className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                          HPP belum ada
                        </Badge>
                      )}
                    </div>
                    {expanded && (
                      <div className="border-t border-border overflow-x-auto">
                        <table className="w-full text-[11px]">
                          <thead className="bg-muted/50"><tr>
                            {['', 'Kode varian', 'Warna', 'Ukuran', 'HPP', 'Stok jual', 'Status'].map((h) => (
                              <th key={h} className="px-2 py-1.5 text-left font-semibold">{h}</th>))}
                          </tr></thead>
                          <tbody>
                            {p.variants.map((v) => (
                              <tr key={v.fg_material_id} className="border-t border-border">
                                <td className="px-2 py-1">
                                  <Checkbox checked={!!pickedFg[v.fg_material_id]}
                                    disabled={v.in_catalog}
                                    onCheckedChange={(c) => setPickedFg((pf) => {
                                      const n = { ...pf };
                                      if (c) n[v.fg_material_id] = true; else delete n[v.fg_material_id];
                                      return n;
                                    })}
                                    data-testid={`cfm-variant-${v.code}`} />
                                </td>
                                <td className="px-2 py-1 font-mono">{v.code}</td>
                                <td className="px-2 py-1">{v.color || '—'}</td>
                                <td className="px-2 py-1">{v.size_code || '—'}</td>
                                <td className="px-2 py-1 tabular-nums">{rp(v.hpp)}</td>
                                <td className="px-2 py-1 tabular-nums">
                                  {v.sellable_stock > 0
                                    ? v.sellable_stock
                                    : <span className="text-amber-500">0 (habis)</span>}
                                </td>
                                <td className="px-2 py-1">
                                  {v.in_catalog
                                    ? <span className="text-emerald-500 flex items-center gap-1">
                                      <CheckCircle2 className="w-3 h-3" /> sudah di katalog
                                    </span>
                                    : <span className="text-muted-foreground">belum</span>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-[var(--radius-md)] border border-border bg-[hsl(var(--card))] p-3
        flex flex-wrap items-center justify-between gap-3 sticky bottom-2">
        <div className="space-y-1.5">
          <p className="text-xs" data-testid="cfm-selection-summary">
            <b>{fgCount}</b> varian produk × <b>{accCount}</b> toko
            {fgCount && accCount ? ` = ${fgCount * accCount} item katalog akan dibuat` : ''}
            {' · '}<span className="text-muted-foreground">
              varian yang sudah ada di katalog otomatis dilewati
            </span>
          </p>
          {/* Harga jual awal & batas peringatan stok — keduanya diterima backend.
              Ditaruh di layar supaya tidak ada keputusan diam-diam: toko yang
              harganya berbeda per kanal butuh mulai dari 0 lalu diisi per toko. */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5">
              <Label className="text-[11px] text-muted-foreground">Harga jual awal</Label>
              <Select value={priceMode} onValueChange={setPriceMode}>
                <SelectTrigger className="h-8 w-[230px] text-xs" data-testid="cfm-price-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="master">Harga resmi dari master produk</SelectItem>
                  <SelectItem value="kosong">Kosongkan (isi per toko nanti)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-1.5">
              <Label className="text-[11px] text-muted-foreground">Peringatan stok di bawah</Label>
              <input type="number" min="0" step="1" value={alertQty}
                onChange={(e) => setAlertQty(e.target.value)}
                data-testid="cfm-alert-qty"
                className="h-8 w-20 px-2 rounded-[var(--radius-sm)] border border-border
                  bg-[hsl(var(--background))] text-xs text-foreground tabular-nums
                  focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]" />
              <span className="text-[11px] text-muted-foreground">pcs</span>
            </div>
          </div>
        </div>
        <Button onClick={submit} disabled={busy || !fgCount || !accCount}
          data-testid="cfm-submit">
          {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            : <PackagePlus className="w-4 h-4 mr-2" />}
          Tambahkan ke katalog toko
        </Button>
      </div>

      {result && (
        <div className="rounded-[var(--radius-md)] border border-emerald-500/40 bg-emerald-500/5 p-3"
          data-testid="cfm-result">
          <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400 mb-2">
            {result.message}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead className="bg-muted/60"><tr>
                {['Toko', 'Katalog', 'Baru', 'Sudah ada', 'Ditolak'].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left font-semibold">{h}</th>))}
              </tr></thead>
              <tbody>
                {(result.results || []).map((r) => (
                  <tr key={r.account_id} className="border-t border-border">
                    <td className="px-2 py-1">{r.account_name}</td>
                    <td className="px-2 py-1">
                      {r.catalog_name}{r.catalog_created && (
                        <Badge className="ml-1 text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                          baru dibuat
                        </Badge>)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-emerald-600">{r.created}</td>
                    <td className="px-2 py-1 tabular-nums text-amber-600">{r.skipped}</td>
                    <td className="px-2 py-1 tabular-nums text-red-600">{r.rejected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(result.results || []).some((r) => r.rejected > 0) && (
            <ul className="mt-2 space-y-0.5">
              {(result.results || []).flatMap((r) => (r.notes || [])
                .filter((n) => n.action === 'ditolak')
                .map((n, i) => (
                  <li key={`${r.account_id}-${i}`} className="text-[11px] text-red-500">
                    {r.account_name}: {n.why}
                  </li>
                )))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
