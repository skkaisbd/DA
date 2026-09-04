/**
 * BuyerCatalogSelect — pemilih artikel dari **Katalog Buyer** (maklon).
 *
 * ══════════════════════════════════════════════════════════════════════════
 * KENAPA KOMPONEN INI PUNYA "MODE PRODUK BARU" — DAN KENAPA ITU BUKAN CELAH
 * ══════════════════════════════════════════════════════════════════════════
 * Aturan F14b berbunyi: form tidak boleh meminta orang MENGETIK sesuatu yang
 * sudah punya master. Untuk **penawaran maklon (quote)** aturan itu perlu satu
 * kejujuran tambahan: penawaran sering dibuat JUSTRU untuk artikel yang belum
 * ada di katalog — itulah alasan orang meminta penawaran. Melarang teks bebas
 * di sini akan membuat staf memilih artikel yang MIRIP supaya form mau lanjut,
 * dan penawaran akan menempel pada artikel yang salah. Itu lebih buruk daripada
 * teks bebas yang jujur.
 *
 * Maka: DUA mode yang dipilih secara sadar, bukan satu kotak ketik yang diam.
 *   · **Dari Katalog Buyer** (utama) — artikel yang SUDAH ada; nama, kategori,
 *     dan bahan mengikuti katalog, jadi satu artikel tidak punya tiga ejaan.
 *   · **Artikel baru** — teks bebas, TAPI ditandai `is_new_article: true`
 *     sehingga penawaran untuk artikel yang belum terdaftar bisa DIHITUNG
 *     (dan ditindaklanjuti: didaftarkan ke katalog kalau jadi order).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { BookMarked, PlusCircle, Loader2 } from 'lucide-react';
import axios from 'axios';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';

const API = process.env.REACT_APP_BACKEND_URL;
const NEW = '__BARU__';

export default function BuyerCatalogSelect({
  token,
  value,                 // catalog_id ('' kalau mode artikel baru)
  newName = '',          // nama artikel saat mode baru
  onPick,                // (catalogItem|null) => void
  onNewName,             // (string) => void
  label = 'Artikel (dari Katalog Buyer)',
  testId = 'buyer-catalog-select',
  className = '',
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState(value ? 'catalog' : 'new');

  const authH = useMemo(
    () => ({
      Authorization: `Bearer ${token
        || localStorage.getItem('erp_token')
        || localStorage.getItem('client_token') || ''}`,
    }),
    [token],
  );

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/api/dewi/maklon/buyer-catalog`, {
          headers: authH, params: { status: 'active', limit: 300 },
        });
        if (alive) setItems(Array.isArray(r.data) ? r.data : (r.data?.items || []));
      } catch {
        if (alive) setItems([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [authH]);

  return (
    <div className={className} data-testid={`${testId}-wrap`}>
      <Label className="flex items-center gap-1.5 text-xs font-medium">
        <BookMarked className="w-3.5 h-3.5 text-muted-foreground" />
        {label}<span className="text-red-500">*</span>
      </Label>

      <Select
        value={mode === 'new' ? NEW : (value || '')}
        onValueChange={(v) => {
          if (v === NEW) { setMode('new'); onPick?.(null); return; }
          setMode('catalog');
          onPick?.(items.find((i) => i.id === v) || null);
        }}
        disabled={loading}
      >
        <SelectTrigger className="mt-1 h-9 bg-background" data-testid={testId}>
          <SelectValue placeholder={loading
            ? 'Memuat katalog buyer…' : 'Pilih artikel…'} />
        </SelectTrigger>
        <SelectContent className="max-h-72">
          <SelectItem value={NEW}>
            <span className="flex items-center gap-1.5">
              <PlusCircle className="w-3.5 h-3.5" />
              Artikel baru (belum ada di katalog buyer)
            </span>
          </SelectItem>
          {items.map((i) => (
            <SelectItem key={i.id} value={i.id}>
              <span className="font-mono text-[11px] text-muted-foreground mr-1.5">
                {i.artikel_code}
              </span>
              {i.product_name}
              {i.client_name ? (
                <span className="text-muted-foreground"> · {i.client_name}</span>
              ) : null}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {loading && (
        <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
          <Loader2 className="w-3 h-3 animate-spin" />Memuat katalog buyer…
        </p>
      )}

      {mode === 'new' && (
        <div className="mt-2">
          <Input
            className="h-9 text-sm bg-background"
            placeholder="Nama artikel baru — mis. Kaos Premium Cotton Combed 30s"
            value={newName}
            onChange={(e) => onNewName?.(e.target.value)}
            data-testid={`${testId}-new-name`}
          />
          <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
            Ditandai <b>artikel baru</b>. Kalau penawaran ini jadi order,
            daftarkan artikelnya ke <b>Katalog Buyer</b> supaya penawaran
            berikutnya tidak mengetik ulang nama yang sama dengan ejaan berbeda.
          </p>
        </div>
      )}
    </div>
  );
}
