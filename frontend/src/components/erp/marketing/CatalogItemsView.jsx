/**
 * CatalogItemsView — TAB "ITEM" KATALOG (F4.4).
 *
 * KENAPA LAYAR INI DITULIS ULANG
 * ------------------------------
 * Tabel item lama hanya punya **5 kolom** (Produk · Harga · Stok · Status · Aksi),
 * dan "Status" di situ artinya STOK (tersedia/rendah/habis). Pertanyaan yang
 * sebenarnya dibawa marketing ke layar ini tidak bisa dijawab sama sekali:
 *   · produk mana yang **belum tayang** di toko?          (tidak ada datanya)
 *   · mana yang **ditolak platform** dan kenapa?          (tidak ada datanya)
 *   · marjinnya berapa, HPP-nya dari mana?                (tidak ditampilkan)
 *   · harga kita beda berapa dari harga resmi master?      (tidak ditampilkan)
 *   · fotonya ada?                                        (tidak ditampilkan)
 * Semua data itu SUDAH ada di respons endpoint — hanya tidak pernah dipakai. Layar
 * ini menampilkannya (20 kolom) plus dua tampilan (Tabel default & Kartu) sesuai
 * aturan UI plan.md, aksi massal, dan pengelola foto (foto master R&D baca-saja +
 * foto marketplace yang bisa diurutkan).
 *
 * SATU HAL YANG SENGAJA TIDAK DIBUAT MASSAL: **Tayangkan**. Setiap produk punya
 * URL sendiri; tombol massal yang mengisi satu URL untuk banyak produk akan
 * melahirkan "bukti tayang" yang salah — lebih buruk daripada tidak ada bukti.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Table2, LayoutGrid, ExternalLink, Image as ImageIcon, Upload, Trash2, Edit2,
  Rocket, Download, Loader2, AlertTriangle, CheckCircle2, XCircle, Archive,
  RotateCcw, Clock, Link2, Star, ChevronUp, ChevronDown, Coins, ArrowRightLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { GlassInput } from '@/components/ui/glass';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL || '';
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const VIEW_KEY = 'catalog_items_view';   // pilihan tampilan bertahan antar sesi

const STATUS_CFG = {
  DRAFT: { label: 'Draft', cls: 'bg-slate-100 text-slate-700 dark:bg-slate-500/20 dark:text-slate-300' },
  PRE_ORDER: { label: 'Pre-order', cls: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300' },
  ACTIVE: { label: 'Aktif', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' },
  HABIS: { label: 'Habis', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' },
  NONAKTIF: { label: 'Nonaktif', cls: 'bg-muted text-muted-foreground' },
  DITOLAK: { label: 'Ditolak', cls: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300' },
};

const COLUMNS = [
  'Foto', 'SKU', 'Nama', 'Varian', 'Kategori', 'Status', 'Penayangan', 'Harga jual',
  'Harga coret', 'Harga resmi master', 'HPP (sumber)', 'Marjin Rp', 'Marjin %',
  'Stok jual (live)', 'Reserved', 'Sinkron', 'Tautan master', 'URL produk',
  'Terakhir sinkron', 'Aksi',
];

function Thumb({ url, alt }) {
  if (!url) {
    return (
      <div className="w-10 h-10 rounded-[var(--radius-sm)] border border-border
        bg-muted flex items-center justify-center" title="Belum ada foto">
        <ImageIcon className="w-4 h-4 text-muted-foreground" />
      </div>
    );
  }
  return (
    <img src={`${API}${url.startsWith('/') ? url : `/${url}`}`} alt={alt || ''}
      className="w-10 h-10 rounded-[var(--radius-sm)] border border-border object-cover"
      onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
  );
}

function StatusBadge({ row }) {
  const cfg = STATUS_CFG[row.catalog_status] || STATUS_CFG.DRAFT;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${cfg.cls}`}
      title={row.catalog_status_reason || ''}
      data-testid={`item-status-${row.sku}`}>
      {cfg.label}
    </span>
  );
}

/* ── Dialog: tayangkan (butuh URL sebagai bukti) ─────────────────────────────── */
function PublishDialog({ open, onOpenChange, item, catalogId, headers, onDone }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open) { setUrl(item?.platform_url || ''); setErr(''); }
  }, [open, item]);

  const save = async () => {
    setBusy(true); setErr('');
    try {
      const r = await fetch(
        `${API}/api/marketing/catalogs/${catalogId}/items/${item.id}/publish`,
        { method: 'POST', headers, body: JSON.stringify({ platform_url: url }) });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal menandai tayang');
      toast.success(b.message, { duration: 8000 });
      onOpenChange(false);
      onDone?.();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="publish-dialog">
        <DialogHeader>
          <DialogTitle>Tandai tayang — {item?.name}</DialogTitle>
          <DialogDescription>
            Tempel <b>URL produk di marketplace</b> sebagai bukti tayang. Tanpa tautan,
            status “tayang” tidak bisa diperiksa siapa pun — dan saat komplain pembeli
            masuk, tidak ada cara cepat membuka produknya.
          </DialogDescription>
        </DialogHeader>
        <div>
          <Label className="text-xs">URL produk</Label>
          <GlassInput value={url} onChange={(e) => { setUrl(e.target.value); setErr(''); }}
            placeholder="https://tokopedia.com/toko/nama-produk"
            data-testid="publish-url" />
        </div>
        {err && (
          <div className="rounded-[var(--radius-sm)] border border-red-500/40 bg-red-500/10
            p-2.5 text-xs text-red-700 dark:text-red-300 flex items-start gap-2"
            data-testid="publish-error">
            <XCircle className="w-4 h-4 mt-px shrink-0" /><span>{err}</span>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}
            data-testid="publish-cancel">Batal</Button>
          <Button onClick={save} disabled={busy} data-testid="publish-save">
            {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Tandai tayang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Dialog: alasan (tolak / arsip / turunkan) ───────────────────────────────── */
function ReasonDialog({ open, onOpenChange, title, describe, required, onSubmit }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  useEffect(() => { if (open) { setReason(''); setErr(''); } }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="reason-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{describe}</DialogDescription>
        </DialogHeader>
        <div>
          <Label className="text-xs">Alasan {required && <span className="text-red-500">*</span>}</Label>
          <GlassInput value={reason} onChange={(e) => { setReason(e.target.value); setErr(''); }}
            data-testid="reason-input" />
        </div>
        {err && (
          <p className="text-xs text-red-600 dark:text-red-400" data-testid="reason-error">{err}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}
            data-testid="reason-cancel">Batal</Button>
          <Button disabled={busy} data-testid="reason-submit"
            onClick={async () => {
              if (required && !reason.trim()) { setErr('Alasan wajib diisi.'); return; }
              setBusy(true);
              try { await onSubmit(reason.trim()); onOpenChange(false); }
              catch (e) { setErr(e.message); } finally { setBusy(false); }
            }}>
            {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Dialog: kelola foto ─────────────────────────────────────────────────────── */
function PhotoDialog({ open, onOpenChange, item, catalogId, token, headers, onDone }) {
  const [row, setRow] = useState(item);
  const [busy, setBusy] = useState('');
  useEffect(() => { setRow(item); }, [item]);
  if (!row) return null;

  const imgs = row.images || [];
  const master = row.master_images || [];

  const upload = async (file) => {
    if (!file) return;
    setBusy('upload');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(
        `${API}/api/marketing/catalogs/${catalogId}/items/${row.id}/photos`,
        { method: 'POST', headers: { Authorization: headers.Authorization }, body: fd });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal mengunggah foto');
      setRow((s) => ({ ...s, images: [...(s.images || []), b.url] }));
      toast.success('Foto marketplace diunggah');
      onDone?.();
    } catch (e) { toast.error(e.message, { duration: 8000 }); } finally { setBusy(''); }
  };

  const act = async (path, body, okMsg, patch) => {
    setBusy(path);
    try {
      const r = await fetch(
        `${API}/api/marketing/catalogs/${catalogId}/items/${row.id}/${path}`,
        { method: 'POST', headers, body: JSON.stringify(body) });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(b.detail || 'Gagal');
      setRow((s) => ({ ...s, ...(patch ? patch(b) : {}) }));
      toast.success(okMsg || b.message);
      onDone?.();
    } catch (e) { toast.error(e.message, { duration: 8000 }); } finally { setBusy(''); }
  };

  const reorder = (urls) => act('photos/reorder', { urls },
    'Urutan foto disimpan', (b) => ({ images: b.images }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="photo-dialog">
        <DialogHeader>
          <DialogTitle>Foto — {row.name}</DialogTitle>
          <DialogDescription>
            <b>Foto master</b> datang dari R&amp;D (baca-saja). <b>Foto marketplace</b> milik
            marketing; yang <b>paling atas dipakai sebagai foto utama</b> di semua layar.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold mb-1.5">
              Foto master dari R&amp;D ({master.length})
            </p>
            {master.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">
                Produk ini belum punya foto di master. Foto desain diunggah tim R&amp;D pada
                Style, lalu ikut terbawa saat produk dipromosikan ke master.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2" data-testid="photo-master-list">
                {master.map((m) => (
                  <div key={m.url} className="relative">
                    <Thumb url={m.url} alt={m.caption} />
                    <Badge variant="outline" className="absolute -bottom-2 left-0 text-[9px]">
                      {m.from === 'rnd_style' ? 'R&D' : 'master'}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-border pt-3">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-semibold">Foto marketplace ({imgs.length})</p>
              <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer
                rounded-[var(--radius-sm)] border border-border px-2 py-1 hover:bg-muted/50">
                {busy === 'upload' ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Upload className="w-3.5 h-3.5" />}
                Unggah foto
                <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                  data-testid="photo-upload-input"
                  onChange={(e) => upload(e.target.files?.[0])} />
              </label>
            </div>
            {imgs.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">
                Belum ada foto versi marketplace. Selama belum ada, layar memakai foto master
                sebagai foto utama.
              </p>
            ) : (
              <ul className="space-y-1.5" data-testid="photo-marketplace-list">
                {imgs.map((u, i) => (
                  <li key={u} className="flex items-center gap-2 rounded-[var(--radius-sm)]
                    border border-border px-2 py-1.5">
                    <Thumb url={u} alt="" />
                    <span className="text-[11px] flex-1 truncate">{u.split('/').pop()}</span>
                    {i === 0 && (
                      <Badge className="text-[9px] bg-emerald-100 text-emerald-700
                        dark:bg-emerald-500/20 dark:text-emerald-300">
                        <Star className="w-2.5 h-2.5 mr-1" /> utama
                      </Badge>
                    )}
                    <Button size="icon" variant="ghost" className="h-7 w-7" disabled={i === 0}
                      title="Naikkan (jadikan lebih utama)"
                      data-testid={`photo-up-${i}`}
                      onClick={() => {
                        const n = [...imgs]; [n[i - 1], n[i]] = [n[i], n[i - 1]]; reorder(n);
                      }}>
                      <ChevronUp className="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7"
                      disabled={i === imgs.length - 1} title="Turunkan"
                      data-testid={`photo-down-${i}`}
                      onClick={() => {
                        const n = [...imgs]; [n[i + 1], n[i]] = [n[i], n[i + 1]]; reorder(n);
                      }}>
                      <ChevronDown className="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7"
                      title="Hapus foto" data-testid={`photo-remove-${i}`}
                      onClick={() => act('photos/remove', { url: u }, 'Foto dihapus',
                        () => ({ images: imgs.filter((x) => x !== u) }))}>
                      <Trash2 className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}
            data-testid="photo-close">Tutup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════ */
export default function CatalogItemsView({
  catalog, token, items, stockSummary, statusOptions,
  filters, onFilterChange, onEdit, onDelete, onReload,
}) {
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  const [picked, setPicked] = useState({});
  const [publishItem, setPublishItem] = useState(null);
  const [photoItem, setPhotoItem] = useState(null);
  const [reason, setReason] = useState(null);   // {title, describe, required, run}
  const [busy, setBusy] = useState('');
  const pg = useClientPagination(items, view === 'table' ? 10 : 12);

  const headers = useMemo(() => ({
    Authorization: `Bearer ${token || localStorage.getItem('erp_token')}`,
    'Content-Type': 'application/json',
  }), [token]);

  useEffect(() => {
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* storage penuh/diblokir */ }
  }, [view]);
  useEffect(() => { setPicked({}); }, [catalog?.id]);

  const pickedIds = useMemo(
    () => Object.keys(picked).filter((k) => picked[k]), [picked]);
  const byStatus = stockSummary?.by_status || {};

  const call = useCallback(async (path, body, method = 'POST') => {
    const r = await fetch(`${API}/api/marketing/catalogs/${catalog.id}/${path}`,
      { method, headers, body: body ? JSON.stringify(body) : undefined });
    const b = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(b.detail || 'Gagal menyimpan perubahan');
    return b;
  }, [catalog?.id, headers]);

  const itemAction = async (item, path, body, label, method = 'POST') => {
    setBusy(item.id + path);
    try {
      const b = await call(`items/${item.id}/${path}`, body, method);
      toast.success(b.message || label, { duration: 7000 });
      onReload?.();
    } catch (e) { toast.error(e.message, { duration: 9000 }); } finally { setBusy(''); }
  };

  const bulk = async (action, reasonText = '') => {
    setBusy(`bulk-${action}`);
    try {
      const b = await call('items/bulk-transition',
        { item_ids: pickedIds, action, reason: reasonText });
      toast.success(b.message, { duration: 8000 });
      setPicked({});
      onReload?.();
    } catch (e) { toast.error(e.message, { duration: 9000 }); } finally { setBusy(''); }
  };

  const exportCsv = () => {
    if (!items.length) { toast.info('Tidak ada baris untuk diunduh'); return; }
    const head = COLUMNS.slice(0, -1);
    const body = items.map((r) => [
      r.primary_image || '', r.sku, r.name, r.variant_info || '', r.category_name || '',
      r.catalog_status, r.publish_state, r.harga_jual, r.harga_coret,
      r.retail_price_master,
      `${r.hpp_effective ?? r.hpp} (${r.hpp_source_effective || r.hpp_source})`,
      r.margin_status === 'belum_bisa_diukur' ? 'belum bisa diukur' : r.margin,
      r.margin_status === 'belum_bisa_diukur' ? 'belum bisa diukur' : r.margin_pct,
      r.available ?? '', r.fg_reserved ?? '', r.in_sync ? 'ya' : 'tidak',
      r.fg_code || r.link_type || '', r.platform_url || '',
      (r.last_stock_sync || '').slice(0, 16),
    ]);
    const csv = [head, ...body]
      .map((l) => l.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `katalog-${(catalog?.name || 'item').replace(/\s+/g, '-').toLowerCase()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const RowActions = ({ r }) => (
    <div className="flex items-center justify-end gap-0.5">
      {r.publish_state !== 'published' && r.publish_state !== 'archived' && (
        <Button size="icon" variant="ghost" className="h-7 w-7" title="Tandai tayang"
          data-testid={`item-publish-${r.sku}`} onClick={() => setPublishItem(r)}>
          <Rocket className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        </Button>
      )}
      {r.publish_state === 'published' && (
        <Button size="icon" variant="ghost" className="h-7 w-7" title="Turunkan dari tayang"
          data-testid={`item-unpublish-${r.sku}`}
          disabled={busy === r.id + 'unpublish'}
          onClick={() => setReason({
            title: `Turunkan dari tayang — ${r.name}`,
            describe: 'Item kembali menjadi DRAFT. Boleh diisi alasannya supaya tim tahu kenapa.',
            required: false,
            run: (why) => itemAction(r, 'unpublish', { reason: why }, 'Diturunkan'),
          })}>
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>
      )}
      <Button size="icon" variant="ghost" className="h-7 w-7"
        title={r.is_preorder ? 'Lepas tanda pre-order' : 'Tandai pre-order'}
        data-testid={`item-preorder-${r.sku}`}
        onClick={() => itemAction(r, 'preorder',
          { is_preorder: !r.is_preorder }, 'Pre-order diperbarui')}>
        <Clock className={`w-3.5 h-3.5 ${r.is_preorder ? 'text-purple-600 dark:text-purple-400' : ''}`} />
      </Button>
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Kelola foto"
        data-testid={`item-photos-${r.sku}`} onClick={() => setPhotoItem(r)}>
        <ImageIcon className="w-3.5 h-3.5" />
      </Button>
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Segarkan dari master"
        data-testid={`item-refresh-${r.sku}`}
        disabled={busy === r.id + 'refresh-from-master'}
        onClick={() => itemAction(r, 'refresh-from-master', null, 'Disegarkan dari master')}>
        <Link2 className="w-3.5 h-3.5" />
      </Button>
      {/* dua aksi ini SUDAH ADA sebelum F4 (per baris) — dipertahankan supaya tidak
          ada fitur yang hilang saat tabel ditulis ulang */}
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Tarik ulang HPP dari master"
        data-testid={`item-refresh-hpp-${r.sku}`}
        disabled={busy === r.id + 'refresh-hpp'}
        onClick={() => itemAction(r, 'refresh-hpp', null, 'HPP disegarkan')}>
        <Coins className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
      </Button>
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Sinkron stok dari FG"
        data-testid={`item-sync-stock-${r.sku}`}
        disabled={busy === r.id + 'sync-fg-stock'}
        onClick={() => itemAction(r, 'sync-fg-stock', null, 'Stok disinkronkan', 'PUT')}>
        <ArrowRightLeft className="w-3.5 h-3.5" />
      </Button>
      {r.publish_state === 'archived' ? (
        <Button size="icon" variant="ghost" className="h-7 w-7" title="Kembalikan dari arsip"
          data-testid={`item-restore-${r.sku}`}
          onClick={() => itemAction(r, 'restore', { reason: '' }, 'Dikembalikan')}>
          <RotateCcw className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
        </Button>
      ) : (
        <Button size="icon" variant="ghost" className="h-7 w-7" title="Arsipkan"
          data-testid={`item-archive-${r.sku}`}
          onClick={() => setReason({
            title: `Arsipkan — ${r.name}`,
            describe: 'Item tidak ditawarkan lagi (NONAKTIF), tetapi TIDAK dihapus supaya '
              + 'riwayat pesanannya tetap utuh.',
            required: false,
            run: (why) => itemAction(r, 'archive', { reason: why }, 'Diarsipkan'),
          })}>
          <Archive className="w-3.5 h-3.5" />
        </Button>
      )}
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Tandai ditolak platform"
        data-testid={`item-reject-${r.sku}`}
        onClick={() => setReason({
          title: `Ditolak platform — ${r.name}`,
          describe: 'Alasan WAJIB: hanya alasan yang membuat tim tahu apa yang harus diperbaiki.',
          required: true,
          run: (why) => itemAction(r, 'reject', { reason: why }, 'Ditandai ditolak'),
        })}>
        <XCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
      </Button>
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Ubah item"
        data-testid={`item-edit-${r.sku}`} onClick={() => onEdit?.(r)}>
        <Edit2 className="w-3.5 h-3.5" />
      </Button>
      <Button size="icon" variant="ghost" className="h-7 w-7" title="Hapus item"
        data-testid={`item-delete-${r.sku}`} onClick={() => onDelete?.(r)}>
        <Trash2 className="w-3.5 h-3.5 text-red-700 dark:text-red-400" />
      </Button>
    </div>
  );

  return (
    <div className="space-y-3" data-testid="catalog-items-view">
      {/* ── ringkas per status: bisa diklik jadi filter ─────────────────────── */}
      <div className="flex flex-wrap items-center gap-1.5" data-testid="catalog-status-chips">
        <span className="text-[11px] text-muted-foreground mr-1">Status:</span>
        {(statusOptions || []).map((o) => {
          const on = (filters.catalogStatus || []).includes(o.value);
          const n = byStatus[o.value] ?? 0;
          return (
            <button key={o.value} type="button"
              data-testid={`catalog-chip-${o.value}`}
              title={o.label}
              onClick={() => {
                const cur = filters.catalogStatus || [];
                onFilterChange({
                  catalogStatus: on ? cur.filter((x) => x !== o.value) : [...cur, o.value],
                });
              }}
              className={`text-[11px] rounded-full px-2.5 py-1 border transition
                ${on ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/10 font-semibold'
                  : 'border-border hover:border-[hsl(var(--primary))]'}`}>
              {STATUS_CFG[o.value]?.label || o.value} ({n})
            </button>
          );
        })}
        {(filters.catalogStatus || []).length > 0 && (
          <button type="button" className="text-[11px] underline text-muted-foreground"
            onClick={() => onFilterChange({ catalogStatus: [] })}
            data-testid="catalog-chip-clear">bersihkan</button>
        )}
      </div>

      {/* ── baris alat: penayangan · foto · urutan · tampilan · CSV ─────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <select className="text-xs rounded border border-border bg-[hsl(var(--background))]
          text-foreground px-2 py-1.5" data-testid="catalog-filter-publish"
          value={filters.publishState || ''}
          onChange={(e) => onFilterChange({ publishState: e.target.value })}>
          <option value="">Semua penayangan</option>
          <option value="draft">Belum tayang</option>
          <option value="published">Tayang</option>
          <option value="rejected">Ditolak</option>
          <option value="archived">Diarsipkan</option>
        </select>
        <select className="text-xs rounded border border-border bg-[hsl(var(--background))]
          text-foreground px-2 py-1.5" data-testid="catalog-filter-photo"
          value={filters.hasPhoto || ''}
          onChange={(e) => onFilterChange({ hasPhoto: e.target.value })}>
          <option value="">Foto: semua</option>
          <option value="true">Punya foto</option>
          <option value="false">Tanpa foto</option>
        </select>
        <select className="text-xs rounded border border-border bg-[hsl(var(--background))]
          text-foreground px-2 py-1.5" data-testid="catalog-sort"
          value={`${filters.sort || 'name'}:${filters.order || 'asc'}`}
          onChange={(e) => {
            const [s, o] = e.target.value.split(':');
            onFilterChange({ sort: s, order: o });
          }}>
          <option value="name:asc">Nama A→Z</option>
          <option value="status:asc">Status</option>
          <option value="price:desc">Harga tertinggi</option>
          <option value="margin:desc">Marjin tertinggi</option>
          <option value="margin:asc">Marjin terendah</option>
          <option value="stock:asc">Stok paling sedikit</option>
          <option value="updated:desc">Terakhir diubah</option>
        </select>

        <div className="ml-auto flex items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={exportCsv} data-testid="catalog-export-csv">
            <Download className="w-3.5 h-3.5 mr-1.5" /> CSV
          </Button>
          <div className="inline-flex rounded-[var(--radius-sm)] border border-border overflow-hidden">
            <button type="button" onClick={() => setView('table')}
              data-testid="catalog-view-table"
              className={`px-2 py-1.5 text-xs inline-flex items-center gap-1
                ${view === 'table' ? 'bg-[hsl(var(--primary))] text-white' : 'bg-[hsl(var(--card))]'}`}>
              <Table2 className="w-3.5 h-3.5" /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')}
              data-testid="catalog-view-grid"
              className={`px-2 py-1.5 text-xs inline-flex items-center gap-1
                ${view === 'grid' ? 'bg-[hsl(var(--primary))] text-white' : 'bg-[hsl(var(--card))]'}`}>
              <LayoutGrid className="w-3.5 h-3.5" /> Kartu
            </button>
          </div>
        </div>
      </div>

      {/* ── aksi massal ─────────────────────────────────────────────────────── */}
      {pickedIds.length > 0 && (
        <div className="rounded-[var(--radius-md)] border border-[hsl(var(--primary))]/40
          bg-[hsl(var(--primary))]/5 p-2.5 flex flex-wrap items-center gap-2"
          data-testid="catalog-bulk-bar">
          <span className="text-xs font-semibold">{pickedIds.length} item dipilih</span>
          <Button size="sm" variant="outline" disabled={!!busy}
            data-testid="bulk-unpublish"
            onClick={() => bulk('unpublish')}>Turunkan</Button>
          <Button size="sm" variant="outline" disabled={!!busy}
            data-testid="bulk-preorder"
            onClick={() => bulk('preorder')}>Tandai pre-order</Button>
          <Button size="sm" variant="outline" disabled={!!busy}
            data-testid="bulk-unpreorder"
            onClick={() => bulk('unpreorder')}>Lepas pre-order</Button>
          <Button size="sm" variant="outline" disabled={!!busy}
            data-testid="bulk-archive"
            onClick={() => setReason({
              title: `Arsipkan ${pickedIds.length} item`,
              describe: 'Item tidak ditawarkan lagi (NONAKTIF) tetapi tidak dihapus.',
              required: false,
              run: (why) => bulk('archive', why),
            })}>Arsipkan</Button>
          <Button size="sm" variant="outline" disabled={!!busy}
            data-testid="bulk-reject"
            onClick={() => setReason({
              title: `Tandai ${pickedIds.length} item DITOLAK platform`,
              describe: 'Alasan WAJIB — dipakai tim untuk memperbaiki listing.',
              required: true,
              run: (why) => bulk('reject', why),
            })}>Tandai ditolak</Button>
          <span className="text-[11px] text-muted-foreground">
            “Tayangkan” tidak ada di aksi massal: setiap produk punya URL sendiri.
          </span>
          <Button size="sm" variant="ghost" className="ml-auto"
            onClick={() => setPicked({})} data-testid="bulk-clear">Bersihkan pilihan</Button>
        </div>
      )}

      {/* ── TABEL (default) ─────────────────────────────────────────────────── */}
      {view === 'table' && (
        <div className="rounded-[var(--radius-md)] border border-border overflow-x-auto
          bg-[hsl(var(--card))]">
          <table className="w-full text-xs" data-testid="catalog-items-table">
            <thead className="bg-muted/60">
              <tr>
                <th className="px-2 py-2 w-8">
                  <Checkbox
                    checked={pg.paged.length > 0 && pg.paged.every((r) => picked[r.id])}
                    onCheckedChange={(v) => {
                      const n = { ...picked };
                      pg.paged.forEach((r) => { if (v) n[r.id] = true; else delete n[r.id]; });
                      setPicked(n);
                    }}
                    data-testid="catalog-select-page" />
                </th>
                {COLUMNS.map((h) => (
                  <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pg.paged.map((r) => (
                <tr key={r.id} className="border-t border-border hover:bg-muted/30"
                  data-testid={`catalog-item-row-${r.sku}`}>
                  <td className="px-2 py-1.5">
                    <Checkbox checked={!!picked[r.id]}
                      onCheckedChange={(v) => setPicked((p) => {
                        const n = { ...p }; if (v) n[r.id] = true; else delete n[r.id]; return n;
                      })}
                      data-testid={`catalog-select-${r.sku}`} />
                  </td>
                  <td className="px-2.5 py-1.5"><Thumb url={r.primary_image} alt={r.name} /></td>
                  <td className="px-2.5 py-1.5 font-mono whitespace-nowrap">{r.sku}</td>
                  <td className="px-2.5 py-1.5 min-w-[160px]">{r.name}</td>
                  <td className="px-2.5 py-1.5 text-muted-foreground">{r.variant_info || '—'}</td>
                  <td className="px-2.5 py-1.5">{r.category_name || '—'}</td>
                  <td className="px-2.5 py-1.5"><StatusBadge row={r} /></td>
                  <td className="px-2.5 py-1.5">
                    <span className="text-[11px]">{r.publish_state_label || r.publish_state}</span>
                    {r.publish_state_inferred && (
                      <span className="ml-1 text-[10px] text-amber-600 dark:text-amber-400"
                        title="Disimpulkan sistem dari ada/tidaknya URL produk — belum dikonfirmasi manusia">
                        (turunan)
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums whitespace-nowrap">{rp(r.harga_jual)}</td>
                  <td className="px-2.5 py-1.5 tabular-nums whitespace-nowrap text-muted-foreground">
                    {r.harga_coret ? rp(r.harga_coret) : '—'}
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums whitespace-nowrap">
                    {r.retail_price_master ? rp(r.retail_price_master) : '—'}
                    {!!r.price_delta_vs_master && (
                      <span className={`ml-1 text-[10px] ${r.price_delta_vs_master > 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-red-600 dark:text-red-400'}`}>
                        ({r.price_delta_vs_master > 0 ? '+' : ''}{rp(r.price_delta_vs_master)})
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums whitespace-nowrap">
                    {rp(r.hpp_effective ?? r.hpp)}
                    <span className="ml-1 text-[10px] text-muted-foreground">
                      ({r.hpp_source_effective === 'fg_fifo_avg' ? 'batch FIFO'
                        : r.hpp_source_effective === 'fg_master' ? 'master FG'
                        : r.hpp_source_effective === 'catalog_manual' ? 'ketikan katalog'
                        : 'belum ada'})
                    </span>
                  </td>
                  {/* SESI #37 — HPP tidak diketahui ⇒ lencana, BUKAN 0%/100%.
                      Kolom margin dulu menampilkan 100% untuk item tanpa HPP,
                      yaitu item yang untung-ruginya justru tidak diketahui. */}
                  <td className="px-2.5 py-1.5 tabular-nums whitespace-nowrap">
                    {r.margin_status === 'belum_bisa_diukur'
                      ? <span className="text-muted-foreground">—</span>
                      : rp(r.margin)}
                  </td>
                  <td className={`px-2.5 py-1.5 tabular-nums ${Number(r.margin_pct) < 0
                    ? 'text-red-600 dark:text-red-400 font-semibold' : ''}`}>
                    {r.margin_status === 'belum_bisa_diukur' ? (
                      <span title={r.margin_reason}
                        data-testid={`catalog-margin-unknown-${r.sku || r.id}`}
                        className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300 whitespace-nowrap">
                        belum bisa diukur
                      </span>
                    ) : `${r.margin_pct}%`}
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums">
                    {r.available === null || r.available === undefined
                      ? <span className="text-muted-foreground">—</span>
                      : <span className={Number(r.available) <= 0
                        ? 'text-amber-600 dark:text-amber-400 font-semibold' : ''}>
                        {Number(r.available).toLocaleString('id-ID')}
                      </span>}
                  </td>
                  <td className="px-2.5 py-1.5 tabular-nums text-muted-foreground">
                    {r.fg_reserved ?? 0}
                  </td>
                  <td className="px-2.5 py-1.5">
                    {r.in_sync
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" title="Angka simpanan sama dengan stok jual" />
                      : <AlertTriangle className="w-3.5 h-3.5 text-amber-500"
                        title={r.attention_reason || 'Angka simpanan berbeda dari stok jual'} />}
                  </td>
                  <td className="px-2.5 py-1.5 whitespace-nowrap">
                    {r.fg_code
                      ? <span className="font-mono text-[11px]">{r.fg_code}</span>
                      : <span className="text-amber-600 dark:text-amber-400 text-[11px]">belum tertaut</span>}
                  </td>
                  <td className="px-2.5 py-1.5">
                    {r.platform_url
                      ? <a href={r.platform_url} target="_blank" rel="noreferrer"
                        className="text-[hsl(var(--primary))] inline-flex items-center gap-1">
                        buka <ExternalLink className="w-3 h-3" />
                      </a>
                      : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-2.5 py-1.5 whitespace-nowrap text-muted-foreground">
                    {(r.last_stock_sync || '').slice(0, 10) || '—'}
                  </td>
                  <td className="px-2.5 py-1.5"><RowActions r={r} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
            onPageChange={pg.setPage} className="px-3" />
        </div>
      )}

      {/* ── KARTU ───────────────────────────────────────────────────────────── */}
      {view === 'grid' && (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            data-testid="catalog-items-grid">
            {pg.paged.map((r) => (
              <div key={r.id} className="rounded-[var(--radius-md)] border border-border
                bg-[hsl(var(--card))] p-3 space-y-2" data-testid={`catalog-item-card-${r.sku}`}>
                <div className="flex items-start gap-2">
                  <Checkbox checked={!!picked[r.id]}
                    onCheckedChange={(v) => setPicked((p) => {
                      const n = { ...p }; if (v) n[r.id] = true; else delete n[r.id]; return n;
                    })} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold truncate" title={r.name}>{r.name}</p>
                    <p className="text-[11px] font-mono text-muted-foreground">{r.sku}</p>
                  </div>
                  <StatusBadge row={r} />
                </div>
                {r.primary_image ? (
                  <img src={`${API}${r.primary_image}`} alt={r.name}
                    className="w-full h-32 object-cover rounded-[var(--radius-sm)] border border-border" />
                ) : (
                  <div className="w-full h-32 rounded-[var(--radius-sm)] border border-border
                    bg-muted flex flex-col items-center justify-center text-muted-foreground">
                    <ImageIcon className="w-6 h-6 mb-1" />
                    <span className="text-[10px]">belum ada foto</span>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-1 text-[11px]">
                  <span className="text-muted-foreground">Harga jual</span>
                  <span className="text-right tabular-nums font-semibold">{rp(r.harga_jual)}</span>
                  <span className="text-muted-foreground">HPP</span>
                  <span className="text-right tabular-nums">{rp(r.hpp_effective ?? r.hpp)}</span>
                  <span className="text-muted-foreground">Marjin</span>
                  <span className="text-right tabular-nums">
                    {r.margin_status === 'belum_bisa_diukur' ? (
                      <span title={r.margin_reason}
                        className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300">
                        belum bisa diukur
                      </span>
                    ) : `${rp(r.margin)} · ${r.margin_pct}%`}
                  </span>
                  <span className="text-muted-foreground">Stok jual</span>
                  <span className="text-right tabular-nums">
                    {r.available === null || r.available === undefined ? '—' : Number(r.available).toLocaleString('id-ID')}
                  </span>
                  <span className="text-muted-foreground">Kategori</span>
                  <span className="text-right truncate">{r.category_name || '—'}</span>
                </div>
                <p className="text-[10px] text-muted-foreground">{r.catalog_status_reason}</p>
                <RowActions r={r} />
              </div>
            ))}
          </div>
          <PaginationLite page={pg.page} totalPages={pg.totalPages} total={pg.total}
            onPageChange={pg.setPage} pageSize={12} />
        </div>
      )}

      {items.length === 0 && (
        <div className="py-10 text-center" data-testid="catalog-items-empty">
          <AlertTriangle className="w-7 h-7 mx-auto text-amber-500 mb-2" />
          <p className="text-sm font-medium">Tidak ada item yang cocok dengan saringan ini.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Kosongkan saringan status/penayangan di atas, atau isi katalog lewat tab
            <b> Isi dari Master</b>.
          </p>
        </div>
      )}

      <PublishDialog open={!!publishItem} onOpenChange={(o) => !o && setPublishItem(null)}
        item={publishItem} catalogId={catalog?.id} headers={headers} onDone={onReload} />
      <PhotoDialog open={!!photoItem} onOpenChange={(o) => !o && setPhotoItem(null)}
        item={photoItem} catalogId={catalog?.id} token={token} headers={headers}
        onDone={onReload} />
      <ReasonDialog open={!!reason} onOpenChange={(o) => !o && setReason(null)}
        title={reason?.title} describe={reason?.describe} required={reason?.required}
        onSubmit={async (why) => { await reason.run(why); }} />
    </div>
  );
}
