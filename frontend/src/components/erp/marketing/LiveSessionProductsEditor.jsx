/**
 * LiveSessionProductsEditor — RINCIAN PRODUK PER SESI LIVE (F18#3).
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * Sesudah live selesai, pertanyaan pertama pemilik toko selalu sama: "tadi barang
 * mana yang paling laku?" — karena jawabannya menentukan apa yang dibawakan besok
 * dan berapa yang disiapkan gudang. Sebelum ini aplikasi tidak bisa menjawab:
 * endpoint `live/analytics/product-performance` membaca `products[]` yang TIDAK
 * PUNYA SATU PUN JALAN PENGISIAN, jadi laporannya selalu kosong.
 *
 * DUA KEPUTUSAN YANG TERLIHAT DI LAYAR INI
 *   · Produk DIPILIH dari katalog toko (bukan diketik). Nama, SKU, dan HPP ikut
 *     master, supaya "produk terlaris" tidak terpecah karena beda ejaan.
 *   · Rekonsiliasi ditampilkan HIDUP: jumlah rincian vs omzet sesi. Rincian yang
 *     melebihi omzet sesi berarti uang dihitung dua kali — dan itu ditolak server,
 *     jadi lebih baik terlihat di sini sebelum tombol simpan ditekan.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2, Package, AlertTriangle, CheckCircle2, Loader2, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
/**
 * Persen dengan pembulatan SAMA seperti server (`core.marketing_live_products.pct`).
 * Sebelumnya baris rekonsiliasi menghitung sendiri dan membulatkan ke bilangan
 * bulat, sehingga satu angka cakupan tampil "69%" di sini, "69.5%" di kolom
 * tabel, dan "70%" di pesan server — pada dialog yang SAMA.
 */
const fmtPct = (v) => {
  const f = Math.round((Number(v) || 0) * 10) / 10;
  return Number.isInteger(f) ? `${f}%` : `${f.toFixed(1)}%`;
};

function authHeader(token) {
  return { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` };
}

export function reconcileLocal(lines, sessionRevenue) {
  const totalRevenue = lines.reduce((a, l) => a + num(l.revenue), 0);
  const totalUnits = lines.reduce((a, l) => a + num(l.units_sold), 0);
  const sRev = num(sessionRevenue);
  const over = sRev > 0 && totalRevenue > sRev * 1.02;
  const unallocated = Math.max(sRev - totalRevenue, 0);
  const coverage = sRev > 0 ? Math.round((totalRevenue / sRev) * 1000) / 10 : 0;
  return { totalRevenue, totalUnits, sRev, over, unallocated, coverage };
}

/** Baris rincian: produk (select katalog) + unit + omzet. */
function Row({ items, line, onChange, onRemove, index, disabled }) {
  const item = items.find((i) => i.id === line.catalog_item_id) || null;
  const priceAvg = num(line.units_sold) ? num(line.revenue) / num(line.units_sold) : 0;
  const margin = item ? num(line.revenue) - num(item.hpp) * num(line.units_sold) : null;

  return (
    <tr className="border-b last:border-0 align-top" data-testid={`lp-row-${index}`}>
      <td className="px-2 py-2 min-w-[220px]">
        <Select
          value={line.catalog_item_id || ''}
          onValueChange={(v) => onChange({ ...line, catalog_item_id: v })}
          disabled={disabled || items.length === 0}
        >
          <SelectTrigger className="h-8 text-xs" data-testid={`lp-item-${index}`}>
            <SelectValue placeholder={items.length ? 'Pilih produk katalog…' : 'Katalog kosong'} />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            {items.map((i) => (
              <SelectItem key={i.id} value={i.id}>
                <span className="font-mono text-[11px] text-muted-foreground mr-1.5">{i.sku}</span>
                {i.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {item && (
          <p className="text-[10px] text-muted-foreground mt-1">
            HPP master {rp(item.hpp)} · harga jual {rp(item.harga_jual || item.price)}
          </p>
        )}
      </td>
      <td className="px-2 py-2 w-[110px]">
        <Input type="number" min="0" className="h-8 text-xs tabular-nums"
          value={line.units_sold ?? ''} disabled={disabled}
          data-testid={`lp-units-${index}`}
          onChange={(e) => onChange({ ...line, units_sold: e.target.value })} />
      </td>
      <td className="px-2 py-2 w-[150px]">
        <Input type="number" min="0" className="h-8 text-xs tabular-nums"
          value={line.revenue ?? ''} disabled={disabled}
          data-testid={`lp-revenue-${index}`}
          onChange={(e) => onChange({ ...line, revenue: e.target.value })} />
      </td>
      <td className="px-2 py-2 w-[110px]">
        <Input type="number" min="0" className="h-8 text-xs tabular-nums"
          value={line.orders ?? ''} disabled={disabled}
          data-testid={`lp-orders-${index}`}
          onChange={(e) => onChange({ ...line, orders: e.target.value })} />
      </td>
      <td className="px-2 py-2 text-xs tabular-nums text-muted-foreground whitespace-nowrap">
        {rp(Math.round(priceAvg))}
        {margin !== null && (
          <div className={margin >= 0 ? 'text-emerald-600' : 'text-red-600'}>
            margin {rp(Math.round(margin))}
          </div>
        )}
      </td>
      <td className="px-2 py-2">
        <Button variant="ghost" size="sm" className="h-7 px-2 text-red-600"
          disabled={disabled} data-testid={`lp-remove-${index}`}
          onClick={onRemove}>
          <Trash2 size={13} />
        </Button>
      </td>
    </tr>
  );
}

export default function LiveSessionProductsEditor({
  token, accountId, lines, onChange, sessionRevenue = 0, disabled = false,
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!accountId) { setItems([]); return; }
      setLoading(true);
      try {
        const cats = await axios.get(`${API}/api/marketing/catalogs`, {
          headers: authHeader(token), params: { account_id: accountId },
        });
        const list = cats.data?.catalogs || cats.data?.data || [];
        const all = [];
        for (const c of list) {
          const r = await axios.get(`${API}/api/marketing/catalogs/${c.id}/items`, {
            headers: authHeader(token), params: { page_size: 200 },
          });
          all.push(...(r.data?.items || r.data?.data || []));
        }
        if (alive) setItems(all);
      } catch (e) {
        if (alive) setItems([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [token, accountId]);

  const rec = useMemo(() => reconcileLocal(lines || [], sessionRevenue),
    [lines, sessionRevenue]);

  const setLine = (i, next) => {
    const copy = [...lines];
    copy[i] = next;
    onChange(copy);
  };
  const removeLine = (i) => onChange(lines.filter((_, idx) => idx !== i));
  const addLine = () => onChange([...(lines || []),
    { catalog_item_id: '', units_sold: '', revenue: '', orders: '' }]);

  const dupe = useMemo(() => {
    const seen = new Set();
    for (const l of lines || []) {
      if (!l.catalog_item_id) continue;
      if (seen.has(l.catalog_item_id)) return true;
      seen.add(l.catalog_item_id);
    }
    return false;
  }, [lines]);

  return (
    <div className="rounded-[var(--radius-sm)] border border-border bg-card"
      data-testid="live-products-editor">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b bg-muted/40">
        <p className="text-xs font-medium flex items-center gap-1.5">
          <Package className="w-3.5 h-3.5" /> Rincian Produk Terjual
          <span className="text-muted-foreground font-normal">
            — menjawab “barang mana yang paling laku saat live”
          </span>
        </p>
        <Button size="sm" variant="outline" className="h-7" onClick={addLine}
          disabled={disabled || !accountId} data-testid="live-products-add">
          <Plus size={13} className="mr-1" /> Tambah produk
        </Button>
      </div>

      {!accountId ? (
        <p className="px-3 py-4 text-xs text-muted-foreground">
          Pilih toko dulu — produk hanya boleh diambil dari katalog toko itu.
        </p>
      ) : loading ? (
        <p className="px-3 py-4 text-xs text-muted-foreground flex items-center gap-1.5">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Memuat katalog toko…
        </p>
      ) : items.length === 0 ? (
        <p className="px-3 py-4 text-xs text-amber-700 dark:text-amber-400 flex items-start gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" />
          Katalog toko ini masih kosong. Isi dulu di <b className="mx-1">Manajemen Katalog</b>
          — rincian live harus menunjuk produk master supaya bisa dijumlahkan per produk.
        </p>
      ) : (lines || []).length === 0 ? (
        <div className="px-3 py-4 text-xs text-muted-foreground flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 mt-px shrink-0" />
          <span>
            Belum ada rincian. Tekan <b>Tambah produk</b> untuk mencatat apa saja yang
            laku di sesi ini — atau impor massal lewat
            <b> Impor Data → Rincian Produk per Sesi Live</b>. Total sesi tetap terhitung
            tanpa rincian, hanya laporan per produk yang kosong.
          </span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/20">
                {['Produk (katalog toko)', 'Unit terjual', 'Omzet (Rp)', 'Order', 'Harga rata-rata', ''].map((h) => (
                  <th key={h} className="px-2 py-1.5 text-left text-[11px] font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => (
                <Row key={l.id || `new-${i}`} items={items} line={l} index={i}
                  disabled={disabled}
                  onChange={(n) => setLine(i, n)} onRemove={() => removeLine(i)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Rekonsiliasi — satu tempat, angka sama dengan yang dipakai server */}
      {(lines || []).length > 0 && (
        <div className="px-3 py-2 border-t space-y-1.5" data-testid="live-products-recon">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs tabular-nums">
            <span>Rincian: <b>{rec.totalUnits}</b> unit · <b>{rp(rec.totalRevenue)}</b></span>
            <span className="text-muted-foreground">Omzet sesi: {rp(rec.sRev)}</span>
            {rec.sRev > 0 && !rec.over && (
              <span className="text-muted-foreground">
                Belum terinci: <b>{rp(rec.unallocated)}</b> ({fmtPct(rec.coverage)} terinci)
              </span>
            )}
          </div>
          {rec.sRev > 0 && (
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div className={`h-full ${rec.over ? 'bg-red-500' : 'bg-emerald-500'}`}
                style={{ width: `${Math.min(rec.coverage, 100)}%` }} />
            </div>
          )}
          {dupe && (
            <p className="text-[11px] text-red-600 flex items-start gap-1">
              <AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" />
              Ada produk yang sama dua kali. Gabungkan jadi satu baris — kalau dobel,
              “produk terlaris” menghitungnya dua kali.
            </p>
          )}
          {rec.over && (
            <p className="text-[11px] text-red-600 flex items-start gap-1">
              <AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" />
              Rincian ({rp(rec.totalRevenue)}) MELEBIHI omzet sesi ({rp(rec.sRev)}).
              Salah satunya keliru — server akan menolak sampai diperbaiki.
            </p>
          )}
          {!rec.over && rec.sRev > 0 && rec.unallocated <= Math.max(rec.sRev * 0.02, 1) && (
            <p className="text-[11px] text-emerald-600 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> Rincian sudah menjelaskan seluruh omzet sesi.
            </p>
          )}
          {rec.sRev <= 0 && rec.totalRevenue > 0 && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400">
              Omzet sesi masih Rp 0 sementara rincian sudah {rp(rec.totalRevenue)}.
              Isi omzet sesi, atau pakai tombol <b>Samakan total sesi</b> sesudah disimpan.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
