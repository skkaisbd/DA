/**
 * MasterProductSelect — SATU pemilih produk dari MASTER (`rahaza_models`).
 *
 * ══════════════════════════════════════════════════════════════════════════
 * KENAPA KOMPONEN INI ADA (temuan pemilik 2026-08-14)
 * ══════════════════════════════════════════════════════════════════════════
 * Layar **Launching Produk** meminta staf MENGETIK nama produk / bahan / model
 * sebagai teks bebas — padahal yang diluncurkan adalah produk **milik DA
 * sendiri** yang sudah terdaftar di master (`rahaza_models` + varian FG).
 *
 * Akibatnya bukan soal kenyamanan mengetik:
 *   1. `_auto_create_fg_from_launch()` membuat BARANG JADI BARU dari teks yang
 *      diketik ⇒ produk yang sama lahir dua kali di master stok dengan dua kode
 *      berbeda. Stok, HPP, dan reservasi katalog pecah mengikutinya.
 *   2. Harga di rencana peluncuran tidak bisa dibandingkan dengan harga resmi
 *      master maupun harga katalog toko — "kenapa harga di toko beda dengan
 *      rencana?" tidak punya jawaban.
 *   3. Ejaan = identitas. "Katun Linen Premium" vs "katun linen premium" adalah
 *      dua bahan berbeda bagi mesin; laporan per produk/bahan salah diam-diam.
 *
 * Sumbernya SATU: `GET /api/marketing/catalogs/master-products` — endpoint yang
 * sama yang dipakai layar **Katalog dari Master**, sehingga daftar produk di
 * Launching mustahil berbeda dengan daftar produk di Katalog.
 *
 * Sengaja **combobox ber-pencarian** (bukan `<Select>` biasa): master produk
 * tumbuh, dan dropdown 200 baris tanpa kotak cari adalah bentuk lain dari
 * "tidak bisa dipakai" yang diperbaiki F10.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Check, ChevronsUpDown, Package, Loader2, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

const API = process.env.REACT_APP_BACKEND_URL;

const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

/**
 * @param {string}   value      model_id terpilih
 * @param {function} onChange   (model|null) => void — DIKIRIM objek master utuh
 *                              supaya pemanggil tidak perlu menebak field.
 */
export default function MasterProductSelect({
  token,
  value,
  onChange,
  label = 'Produk (dari Master Produk)',
  required = true,
  testId = 'master-product-select',
  className = '',
  disabled = false,
  helpText,
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const authH = useMemo(
    // Kunci token yang dipakai app ini: `erp_token` (lihat `lib/apiFetch.js`).
    // `client_token` = portal klien. Prop `token` menang kalau diberikan.
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
      setError('');
      try {
        const r = await axios.get(`${API}/api/marketing/catalogs/master-products`, {
          headers: authH, params: { limit: 300 },
        });
        if (alive) setItems(r.data?.products || []);
      } catch (e) {
        if (alive) {
          setItems([]);
          setError('Master produk tidak bisa dibaca.');
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [authH]);

  const selected = items.find((i) => i.model_id === value) || null;

  return (
    <div className={className} data-testid={`${testId}-wrap`}>
      {label && (
        <Label className="flex items-center gap-1.5 text-xs font-medium">
          <Package className="w-3.5 h-3.5 text-muted-foreground" />
          {label}
          {required && <span className="text-red-500">*</span>}
        </Label>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled || loading}
            data-testid={testId}
            className="mt-1 w-full justify-between h-9 font-normal bg-background"
          >
            {loading ? (
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />Memuat master produk…
              </span>
            ) : selected ? (
              <span className="flex items-center gap-1.5 truncate">
                <span className="font-mono text-[11px] text-muted-foreground">{selected.code}</span>
                <span className="truncate">{selected.name}</span>
              </span>
            ) : (
              <span className="text-muted-foreground">Pilih produk dari master…</span>
            )}
            <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>

        <PopoverContent
          className="w-[--radix-popover-trigger-width] p-0 bg-popover border-border shadow-lg"
          align="start"
        >
          <Command
            filter={(val, search) =>
              val.toLowerCase().includes(String(search || '').toLowerCase()) ? 1 : 0
            }
          >
            <CommandInput placeholder="Cari kode / nama / kategori…" className="h-9"
              data-testid={`${testId}-search`} />
            <CommandList className="max-h-72">
              <CommandEmpty>
                <div className="px-3 py-4 text-xs text-muted-foreground text-left">
                  Tidak ada produk yang cocok.
                </div>
              </CommandEmpty>
              <CommandGroup>
                {items.map((p) => (
                  <CommandItem
                    key={p.model_id}
                    value={`${p.code} ${p.name} ${p.category_name || ''}`}
                    onSelect={() => { onChange?.(p); setOpen(false); }}
                    data-testid={`${testId}-opt-${p.code}`}
                    className="cursor-pointer"
                  >
                    <Check className={cn('mr-2 h-3.5 w-3.5',
                      value === p.model_id ? 'opacity-100' : 'opacity-0')} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[11px] text-muted-foreground">{p.code}</span>
                        <span className="truncate text-sm">{p.name}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 mt-0.5 text-[10px] text-muted-foreground">
                        {p.category_name && (
                          <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-normal">
                            {p.category_name}
                          </Badge>
                        )}
                        <span>HPP {rp(p.hpp)}</span>
                        <span>· Harga resmi {rp(p.retail_price_master)}</span>
                        <span>· {p.variant_count || 0} varian</span>
                      </div>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* Master kosong / tidak terbaca — katakan apa adanya + jalan keluarnya. */}
      {!loading && items.length === 0 && (
        <p className="mt-1 flex items-start gap-1.5 text-[11px] text-amber-700 dark:text-amber-400"
           data-testid={`${testId}-empty`}>
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
          <span>
            {error || 'Master Produk masih kosong.'} Daftarkan produknya dulu di
            <b> Master Produk</b> — supaya kode, HPP, dan harga resmi tidak perlu
            diketik ulang (dan tidak lahir barang jadi kembar).
          </span>
        </p>
      )}

      {/* Ringkasan master untuk produk terpilih — angka yang dipakai form. */}
      {selected && (
        <div className="mt-1.5 rounded-md border border-border bg-muted/50 px-2.5 py-1.5"
             data-testid={`${testId}-meta`}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>Kategori: <b className="text-foreground">{selected.category_name || '—'}</b></span>
            <span>HPP master: <b className="text-foreground">{rp(selected.hpp)}</b></span>
            <span>Harga resmi: <b className="text-foreground">{rp(selected.retail_price_master)}</b></span>
            <span>Varian: <b className="text-foreground">{selected.variant_count || 0}</b></span>
          </div>
        </div>
      )}

      {helpText && <p className="mt-1 text-[11px] text-muted-foreground">{helpText}</p>}
    </div>
  );
}
