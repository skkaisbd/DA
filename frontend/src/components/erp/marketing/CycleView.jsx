/**
 * CycleView — LAYAR SIKLUS MARKETING (F5.5): target → anggaran → omzet dalam SATU layar.
 *
 * KENAPA LAYAR INI ADA
 * --------------------
 * Sebelum F5, satu bulan kerja dibaca dari tiga layar berbeda (Target, Anggaran,
 * Laporan) yang masing-masing menghitung sendiri. Di rapat, tiga layar itu bisa
 * menyebut tiga kesimpulan berbeda untuk toko yang sama — dan tidak ada cara
 * membuktikan mana yang dipakai mengambil keputusan.
 *
 * Layar ini membaca SATU endpoint (`/api/marketing/cycle/overview`) yang angkanya
 * dihitung `core/marketing_cycle.py`. Total & peringkat dihitung di backend, bukan
 * di browser: kalau layar menjumlah sendiri, lampiran export bisa berbeda dari yang
 * dilihat di rapat.
 *
 * Yang WAJIB tetap terlihat (jangan dihapus saat merapikan tampilan):
 *  · DUA angka omzet (produk & order amount) + label "sebelum potongan platform";
 *  · `pace` (bagian bulan yang sudah berjalan) di samping capaian — tanpa pace,
 *    "capaian 60%" pada tanggal 3 dibaca sebagai gagal;
 *  · cakupan HPP di samping marjin — marjin tanpa cakupan adalah angka yang menipu;
 *  · **omzet BRUTO dan omzet SETELAH RETUR berdampingan** (keputusan pemilik sesi
 *    #9). Bruto adalah angka lama yang dipakai target/capaian/ROAS — jangan
 *    diganti dengan net "supaya lebih benar": lampiran rapat yang sudah beredar
 *    memakai bruto, dan menggeser artinya diam-diam adalah cara tercepat membuat
 *    dua kesimpulan untuk satu bulan. Nilai retur juga membawa CAKUPAN: hari yang
 *    rekapnya diimpor/diketik tidak tahu soal retur — itu belum diketahui, bukan nol;
 *  · status kunci periode + siapa yang menutup;
 *  · catatan kejujuran data (apa yang TIDAK diketahui angka ini).
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Target, Wallet, TrendingUp, TrendingDown, RefreshCw, Loader2, Lock, Unlock,
  AlertTriangle, Info, Save, Table2, LayoutGrid, Download, Eye, CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { formatRupiah } from '@/lib/format';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtRp = formatRupiah;
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));
const pct = (n) => `${Number(n || 0).toFixed(1)}%`;
const VIEW_KEY = 'marketing_cycle_view';

const CAT_LABEL = {
  ads: 'Ads / Iklan', kol: 'KOL (fee tetap)', komisi: 'Komisi kreator',
  livehost: 'Live Host', sample: 'Sample', diskon: 'Diskon / Promo',
};

// Label PENDEK khusus sel tabel. Judul penuh ("Omzet jauh di bawah pace target")
// membungkus jadi 3 baris dan membuat SATU baris tabel dua kali lebih tinggi dari
// baris lain — tabel yang tinggi baris­nya tidak seragam tidak bisa dipindai mata.
// Teks penuh tetap ada di papan "Perlu perhatian", di tooltip, dan di dialog Detail.
const FLAG_SHORT = {
  target_behind: 'tertinggal target',
  target_missing: 'target kosong',
  budget_warning: 'anggaran 80%',
  budget_overrun: 'anggaran lewat',
  budget_overrun_category: 'kategori lewat',
  budget_unplanned_category: 'tanpa rencana',
  budget_missing: 'rencana kosong',
  hpp_coverage_low: 'HPP belum lengkap',
};

function SevBadge({ severity, children }) {
  const cls = severity === 'red'
    ? 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300 border-red-400 dark:border-red-500/40'
    : severity === 'yellow'
      ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-400 dark:border-amber-500/40'
      : 'bg-sky-100 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-400 dark:border-sky-500/40';
  return <Badge variant="outline" className={`text-[10px] ${cls}`}>{children}</Badge>;
}

function Bar({ value, reference, over }) {
  return (
    <div className="relative h-1.5 bg-muted rounded-full overflow-hidden mt-1">
      <div className={`h-full ${over ? 'bg-red-500' : 'bg-primary'}`}
        style={{ width: `${Math.min(Math.max(value || 0, 0), 100)}%` }} />
      {reference != null && (
        <span className="absolute top-0 h-full w-[2px] bg-foreground/60"
          style={{ left: `${Math.min(Math.max(reference, 0), 100)}%` }} title={`pace ${pct(reference)}`} />
      )}
    </div>
  );
}

/* ─── Dialog: SET TARGET ─────────────────────────────────────────────────────
   Penolakan backend (423 periode tertutup) DITAHAN DI DALAM dialog. Toast 5
   detik membuat tombol Simpan tampak rusak tanpa keterangan. */
function TargetDialog({ open, onOpenChange, row, period, token, onSaved }) {
  const [form, setForm] = useState({ revenue_target: '', orders_target: '', notes: '', reason: '' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open && row) {
      setErr('');
      setForm({
        revenue_target: row.target?.revenue || '',
        orders_target: row.target?.orders || '',
        notes: row.target?.notes || '',
        // Alasan TIDAK dibawa dari nilai lama: ia menjelaskan perubahan KALI INI.
        reason: '',
      });
    }
  }, [open, row]);

  const save = async () => {
    setSaving(true); setErr('');
    try {
      const [y, m] = period.split('-');
      const res = await fetch(`${API}/api/marketing/targets`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: row.account.id, year: Number(y), month: Number(m),
          revenue_target: parseFloat(form.revenue_target) || 0,
          orders_target: parseInt(form.orders_target, 10) || 0,
          notes: form.notes || null,
          reason: form.reason || null,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(body.detail || `Gagal simpan (HTTP ${res.status})`); return; }
      toast.success(`Target ${row.account.account_name} ${period} disimpan`);
      onOpenChange(false); onSaved();
    } catch (e) { setErr(e.message || 'Gagal simpan'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cycle-target-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Target size={16} className="text-primary" /> Target — {row?.account?.account_name}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">Periode {period}</p>
        </DialogHeader>
        {err && (
          <div className="rounded-md border border-red-400 dark:border-red-500/40 bg-red-100 dark:bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-300"
            data-testid="cycle-target-error">{err}</div>
        )}
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Target Omzet (Rp)</Label>
            <Input type="number" min={0} value={form.revenue_target} className="mt-1 h-9"
              data-testid="cycle-target-revenue"
              onChange={(e) => setForm((f) => ({ ...f, revenue_target: e.target.value }))} />
          </div>
          <div>
            <Label className="text-xs">Target Jumlah Pesanan</Label>
            <Input type="number" min={0} value={form.orders_target} className="mt-1 h-9"
              data-testid="cycle-target-orders"
              onChange={(e) => setForm((f) => ({ ...f, orders_target: e.target.value }))} />
          </div>
          <div>
            <Label className="text-xs">Catatan (opsional)</Label>
            <Input value={form.notes} className="mt-1 h-9"
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
          </div>
          <div>
            <Label className="text-xs">Alasan perubahan (opsional, masuk jejak)</Label>
            <Input value={form.reason} className="mt-1 h-9"
              placeholder="mis. target diturunkan karena stok warna utama habis"
              data-testid="cycle-target-reason"
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
            <p className="text-[10px] text-muted-foreground mt-1">
              Alasan tampil di layar <b>Jejak Perubahan</b> bersama nilai lama → baru.
              Tanpa alasan, enam bulan kemudian jejaknya hanya bisa menjawab
              "berapa", bukan "kenapa".
            </p>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Capaian dibandingkan dengan <b>pace</b> (bagian bulan yang sudah berjalan),
            bukan dengan target penuh — supaya awal bulan tidak selalu tampak gagal.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cycle-target-cancel">Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="cycle-target-save">
            {saving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
            Simpan Target
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Dialog: RENCANA ANGGARAN per kategori ───────────────────────────────── */
function BudgetDialog({ open, onOpenChange, row, period, token, onSaved, categories }) {
  const [form, setForm] = useState({});
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open && row) {
      setErr('');
      setReason('');
      const plan = row.budget?.plan || {};
      const f = {};
      (categories || []).forEach((c) => { f[c] = plan[c] || ''; });
      setForm(f);
    }
  }, [open, row, categories]);

  const total = (categories || []).reduce((s, c) => s + (parseFloat(form[c]) || 0), 0);

  const save = async () => {
    setSaving(true); setErr('');
    try {
      const budget_by_category = {};
      (categories || []).forEach((c) => { budget_by_category[c] = parseFloat(form[c]) || 0; });
      const res = await fetch(`${API}/api/marketing/budget`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: row.account.id, period, budget_by_category,
          reason: reason || '' }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(body.detail || `Gagal simpan (HTTP ${res.status})`); return; }
      toast.success(`Rencana anggaran ${row.account.account_name} disimpan`);
      onOpenChange(false); onSaved();
    } catch (e) { setErr(e.message || 'Gagal simpan'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cycle-budget-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet size={16} className="text-primary" /> Rencana Anggaran — {row?.account?.account_name}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">Periode {period}</p>
        </DialogHeader>
        {err && (
          <div className="rounded-md border border-red-400 dark:border-red-500/40 bg-red-100 dark:bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-300"
            data-testid="cycle-budget-error">{err}</div>
        )}
        <div className="space-y-2">
          {(categories || []).map((c) => {
            const cat = (row?.budget?.categories || []).find((x) => x.category === c) || {};
            return (
              <div key={c} className="flex items-center gap-2">
                <Label className="text-xs w-36">{CAT_LABEL[c] || c}</Label>
                <Input type="number" min={0} value={form[c] ?? ''} className="h-8 text-right"
                  data-testid={`cycle-budget-input-${c}`}
                  onChange={(e) => setForm((f) => ({ ...f, [c]: e.target.value }))} />
                <span className="text-[10px] text-muted-foreground w-40 text-right">
                  terpakai {fmtRp(cat.spend)}{cat.mode === 'auto' ? ' (auto)' : ''}
                </span>
              </div>
            );
          })}
          <div className="flex justify-between border-t pt-2 text-sm font-semibold">
            <span>Total rencana</span><span data-testid="cycle-budget-total">{fmtRp(total)}</span>
          </div>
          <div className="pt-1">
            <Label className="text-xs">Alasan perubahan (opsional, masuk jejak)</Label>
            <Input value={reason} className="mt-1 h-9"
              placeholder="mis. anggaran iklan ditambah untuk kejar target akhir bulan"
              data-testid="cycle-budget-reason"
              onChange={(e) => setReason(e.target.value)} />
          </div>
          <p className="text-[11px] text-muted-foreground">
            Kategori bertanda <b>auto</b> realisasinya dihitung sistem dari data sumber
            (pesanan, data iklan, shift live host) — tidak perlu dicatat manual.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="cycle-budget-save">
            {saving ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Save size={14} className="mr-1" />}
            Simpan Rencana
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Dialog: TUTUP / BUKA PERIODE ───────────────────────────────────────────
   Alasan WAJIB: angka yang dibekukan (atau dibuka kembali) harus bisa
   dipertanggungjawabkan — jejaknya masuk marketing_change_log. */
function LockDialog({ open, onOpenChange, row, period, token, onSaved }) {
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const locked = !!row?.locked;
  const action = locked ? 'reopen' : 'close';

  useEffect(() => { if (open) { setReason(''); setErr(''); } }, [open]);

  const save = async () => {
    if (!reason.trim()) { setErr('Alasan wajib diisi.'); return; }
    setSaving(true); setErr('');
    try {
      const res = await fetch(`${API}/api/marketing/periods/lock`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: row.account.id, period, action, reason }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(body.detail || `Gagal (HTTP ${res.status})`); return; }
      toast.success(body.message || 'Berhasil');
      onOpenChange(false); onSaved();
    } catch (e) { setErr(e.message || 'Gagal'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cycle-lock-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {locked ? <Unlock size={16} className="text-amber-500" /> : <Lock size={16} className="text-primary" />}
            {locked ? 'Buka Periode' : 'Tutup Periode'} — {row?.account?.account_name}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">Periode {period}</p>
        </DialogHeader>
        {err && (
          <div className="rounded-md border border-red-400 dark:border-red-500/40 bg-red-100 dark:bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-300"
            data-testid="cycle-lock-error">{err}</div>
        )}
        <div className="space-y-3">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
            {locked
              ? 'Membuka periode berarti angka yang sudah dirapatkan bisa berubah lagi. Semua perubahan sesudah ini tercatat beserta nama Anda.'
              : 'Menutup periode membekukan target, anggaran, rekap harian, dan commit impor bulan ini (ditolak dengan HTTP 423). Ini yang membuat notulen rapat dan sistem tetap sama.'}
          </div>
          <div>
            <Label className="text-xs">Alasan (wajib)</Label>
            <Input value={reason} className="mt-1 h-9" data-testid="cycle-lock-reason"
              placeholder={locked ? 'mis. koreksi pesanan yang terlambat masuk' : 'mis. sudah dirapatkan 5 Agustus'}
              onChange={(e) => setReason(e.target.value)} />
          </div>
          {(row?.lock?.history || []).length > 0 && (
            <div className="text-[11px] text-muted-foreground space-y-1" data-testid="cycle-lock-history">
              <p className="font-semibold text-foreground">Riwayat kunci</p>
              {(row.lock.history || []).slice(-5).reverse().map((h, i) => (
                <p key={i}>
                  {h.action === 'close' ? 'Ditutup' : 'Dibuka'} oleh {h.by_name} — {h.reason || 'tanpa alasan'}
                </p>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cycle-lock-cancel">Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="cycle-lock-submit"
            variant={locked ? 'outline' : 'default'}>
            {saving ? <Loader2 size={14} className="mr-1 animate-spin" />
              : locked ? <Unlock size={14} className="mr-1" /> : <Lock size={14} className="mr-1" />}
            {locked ? 'Buka Periode' : 'Tutup Periode'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ─── F6.4 — JEJAK PERUBAHAN (siapa mengubah target, dari berapa ke berapa) ─── */
function ChangeLogPanel({ accountId, period, token }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${API}/api/marketing/periods/change-log`
          + `?account_id=${accountId}&period=${period}&limit=20`,
          { headers: { Authorization: `Bearer ${token}` } });
        const j = res.ok ? await res.json() : {};
        if (alive) setRows(j.entries || []);
      } catch { if (alive) setRows([]); }
    })();
    return () => { alive = false; };
  }, [accountId, period, token]);
  const label = (a) => ({
    target_create: 'Target dibuat', target_update: 'Target diubah',
    budget_upsert: 'Rencana anggaran diubah', period_close: 'Periode ditutup',
    period_reopen: 'Periode dibuka',
  }[a] || a);
  const money = (v) => (typeof v === 'number' ? fmtRp(v) : String(v ?? '—'));
  return (
    <div className="rounded-md border border-border p-3" data-testid="cycle-changelog">
      <p className="text-xs font-semibold mb-1">Jejak perubahan — siapa mengubah apa</p>
      {rows === null ? <p className="text-[11px] text-muted-foreground">memuat…</p>
        : rows.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">
            Belum ada perubahan tercatat untuk bulan ini.
          </p>
        ) : (
          <ul className="space-y-1 text-[11px]">
            {rows.map((r) => (
              <li key={r.id} className="text-foreground">
                <span className="font-semibold">{label(r.action)}</span>
                {' oleh '}{r.actor_name || '—'}
                {r.actor_role ? <span className="text-muted-foreground"> ({r.actor_role})</span> : null}
                {(r.before?.revenue_target != null || r.after?.revenue_target != null) && (
                  <span className="text-muted-foreground">
                    {' — omzet '}{money(r.before?.revenue_target)}{' → '}{money(r.after?.revenue_target)}
                  </span>
                )}
                {r.reason ? <span className="text-muted-foreground">{` · alasan: ${r.reason}`}</span> : null}
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}

/* ─── Dialog: DETAIL satu toko (rincian anggaran + bukti + catatan) ───────── */
function DetailDialog({ open, onOpenChange, row, period, token }) {
  if (!row) return null;
  const b = row.budget || {};
  const m = row.margin || {};
  const src = {};
  (row.spend_sources || []).forEach((s) => { src[s.category] = s; });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="cycle-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye size={16} className="text-primary" /> {row.account.account_name} — {period}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {row.account.account_code} · {row.account.platform} · basis omzet: {row.revenue_basis}
          </p>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <GlassCard className="p-3"><p className="text-[10px] text-muted-foreground">Omzet produk</p>
              <p className="text-sm font-bold">{fmtRp(row.actual?.revenue_product)}</p></GlassCard>
            <GlassCard className="p-3"><p className="text-[10px] text-muted-foreground">Order amount</p>
              <p className="text-sm font-bold">{fmtRp(row.actual?.revenue_order_amount)}</p></GlassCard>
            <GlassCard className="p-3"><p className="text-[10px] text-muted-foreground">Diskon penjual</p>
              <p className="text-sm font-bold">{fmtRp(row.actual?.seller_discount)}</p></GlassCard>
            <GlassCard className="p-3"><p className="text-[10px] text-muted-foreground">Harga coret (bruto)</p>
              <p className="text-sm font-bold">{fmtRp(row.actual?.gross_before_discount)}</p></GlassCard>
          </div>

          {/* ── SESI #9 — RETUR: dua angka omzet berdampingan ──────────────── */}
          <div className="rounded-md border border-border p-3" data-testid="cycle-detail-returns">
            <p className="text-xs font-semibold mb-1">Omzet bruto vs omzet setelah retur</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div>
                <p className="text-[10px] text-muted-foreground">Omzet bruto (dipakai target)</p>
                <p className="text-sm font-bold">{fmtRp(row.actual?.revenue_gross ?? row.actual?.revenue)}</p>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground">Pesanan retur</p>
                <p className="text-sm font-bold">{fmtNum(row.actual?.returned_orders)}
                  <span className="text-[10px] text-muted-foreground"> · {fmtNum(row.actual?.returned_units)} pcs</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground">Nilai retur</p>
                <p className="text-sm font-bold text-amber-700 dark:text-amber-300">
                  {fmtRp(row.actual?.returned_amount)}
                  <span className="text-[10px] text-muted-foreground"> ({pct(row.actual?.returns_pct)})</span>
                </p>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground">Omzet setelah retur</p>
                <p className="text-sm font-bold">{fmtRp(row.actual?.revenue_net_returns)}</p>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5">
              {row.returns?.label_gross}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {row.returns?.label_net}
            </p>
            {row.returns?.coverage?.complete === false && (
              <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                Cakupan data retur {pct(row.returns?.coverage?.coverage_pct)} hari
                ({fmtNum(row.returns?.coverage?.days_known)}/{fmtNum(row.returns?.coverage?.days_total)}) —
                hari yang rekapnya diimpor/diketik tidak membawa informasi retur, jadi
                nilai retur di atas adalah <b>batas bawah</b>, bukan angka final.
              </p>
            )}
            {row.returns?.over_returned && (
              <p className="text-[11px] text-red-600 mt-1">
                Nilai retur MELEBIHI omzet bulan ini — biasanya pesanannya dibuat bulan
                sebelumnya lalu diretur bulan ini.
              </p>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold mb-1">Anggaran per kategori — rencana vs realisasi</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="cycle-detail-budget-table">
                <thead className="bg-muted/50">
                  <tr>
                    {['Kategori', 'Sumber', 'Rencana', 'Terpakai', 'Manual', 'Auto', 'Sisa', 'Pakai %', 'Bukti']
                      .map((h) => <th key={h} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(b.categories || []).map((c) => (
                    <tr key={c.category} data-testid={`cycle-detail-cat-${c.category}`}>
                      <td className="px-2 py-1.5">{CAT_LABEL[c.category] || c.category}</td>
                      <td className="px-2 py-1.5">
                        <Badge variant="outline" className="text-[9px]">{c.mode}</Badge>
                      </td>
                      <td className="px-2 py-1.5">{fmtRp(c.plan)}</td>
                      <td className="px-2 py-1.5 font-semibold">{fmtRp(c.spend)}</td>
                      <td className="px-2 py-1.5">{fmtRp(c.manual)}</td>
                      <td className="px-2 py-1.5">{fmtRp(c.auto)}</td>
                      <td className={`px-2 py-1.5 ${c.variance < 0 ? 'text-red-600' : ''}`}>{fmtRp(c.variance)}</td>
                      <td className="px-2 py-1.5">{pct(c.used_pct)}</td>
                      <td className="px-2 py-1.5 text-muted-foreground">{src[c.category]?.evidence || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-3">
            <div className="rounded-md border border-border p-3">
              <p className="text-xs font-semibold mb-1">Marjin kotor</p>
              <p className="text-sm">{fmtRp(m.gross_profit)} · {pct(m.gross_margin_pct)}</p>
              <p className="text-[11px] text-muted-foreground mt-1">
                HPP {fmtRp(m.hpp)} · cakupan HPP <b>{pct(m.hpp_coverage_pct)}</b>
                {' '}({fmtNum(m.units_covered)}/{fmtNum(m.units_total)} unit)
              </p>
              {!m.trustworthy && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                  Cakupan HPP di bawah 80% — marjin ini belum bisa dipercaya untuk mengambil keputusan harga.
                </p>
              )}
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs font-semibold mb-1">ROI</p>
              <p className="text-sm">
                ROAS {Number(row.roi?.roas || 0).toFixed(2)}
                {' · '}
                {row.roi?.reliable
                  ? `ROI ${pct(row.roi?.roi_pct)}`
                  : <span className="text-muted-foreground">ROI belum bisa dihitung</span>}
              </p>
              <p className="text-[11px] text-muted-foreground mt-1">
                Belanja {fmtRp(row.roi?.spend)} = {pct(row.roi?.spend_of_revenue_pct)} dari omzet
              </p>
              {!row.roi?.reliable && row.roi?.reliability_note && (
                <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-1"
                  data-testid="cycle-roi-note">{row.roi.reliability_note}</p>
              )}
            </div>
          </div>

          {(row.flags || []).length > 0 && (
            <div className="space-y-1" data-testid="cycle-detail-flags">
              <p className="text-xs font-semibold">Peringatan</p>
              {(row.flags || []).map((f, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  <SevBadge severity={f.severity}>{f.code}</SevBadge>
                  <span className="text-foreground">{f.title} — {f.message}</span>
                </div>
              ))}
            </div>
          )}

          <ChangeLogPanel accountId={row.account.id} period={period} token={token} />

          <div className="rounded-md border border-border bg-muted/40 p-3" data-testid="cycle-detail-notes">
            <p className="text-xs font-semibold mb-1 flex items-center gap-1">
              <Info size={12} /> Catatan kejujuran data
            </p>
            <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted-foreground">
              {(row.data_notes || []).map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ══════════════════════════════════════════════════════════════════════════ */
export default function CycleView({ token, period, monthLabel, scope = 'marketing' }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) || 'table'; } catch { return 'table'; }
  });
  const [onlyAttention, setOnlyAttention] = useState(false);
  const [target, setTarget] = useState(null);
  const [budget, setBudget] = useState(null);
  const [lockRow, setLockRow] = useState(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => { try { localStorage.setItem(VIEW_KEY, view); } catch { /* storage diblokir */ } }, [view]);

  const load = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/marketing/cycle/overview?period=${period}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      toast.error(`Gagal memuat siklus: ${e.message}`);
      setData(null);
    } finally { setLoading(false); }
  }, [period, token]);

  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => {
    const all = data?.rows || [];
    if (!onlyAttention) return all;
    return all.filter((r) => (r.flags || []).some((f) => f.severity === 'red' || f.severity === 'yellow'));
  }, [data, onlyAttention]);

  const t = data?.totals || {};
  const prog = data?.progress || {};

  const exportCsv = () => {
    const head = ['Toko', 'Kode', 'Platform', 'Kunci', 'Target omzet', 'Omzet produk',
      'Omzet order amount', 'Nilai retur', 'Pesanan retur', 'Omzet setelah retur',
      'Capaian %', 'Pace %', 'Target prorata', 'Proyeksi akhir bulan',
      'Pesanan', 'Target pesanan', 'Unit', 'AOV', 'Rencana anggaran', 'Terpakai', 'Sisa',
      'Pakai %', 'Marjin %', 'Cakupan HPP %', 'ROAS', 'Peringatan'];
    const lines = [head.join(';')];
    (data?.rows || []).forEach((r) => {
      lines.push([
        r.account.account_name, r.account.account_code, r.account.platform,
        r.locked ? 'terkunci' : 'terbuka',
        r.target?.revenue, r.actual?.revenue_product, r.actual?.revenue_order_amount,
        r.actual?.returned_amount, r.actual?.returned_orders, r.actual?.revenue_net_returns,
        r.achievement?.revenue_pct, r.achievement?.pace_pct, r.achievement?.prorata_target,
        r.achievement?.run_rate, r.actual?.orders, r.target?.orders, r.actual?.units,
        r.actual?.aov, r.budget?.total_plan, r.budget?.total_spend, r.budget?.total_remaining,
        r.budget?.total_used_pct, r.margin?.gross_margin_pct, r.margin?.hpp_coverage_pct,
        r.roi?.roas, (r.flags || []).map((f) => f.code).join('|'),
      ].join(';'));
    });
    const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `siklus-marketing-${period}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const HEADS = ['Toko', 'Kunci', 'Target omzet', 'Omzet produk', 'Omzet order amount',
    'Nilai retur', 'Setelah retur',
    'Capaian', 'Pace', 'Target s/d hari ini', 'Proyeksi akhir bulan', 'Pesanan', 'Unit',
    'AOV', 'Rencana anggaran', 'Terpakai', 'Sisa', 'Pakai %', 'Marjin %', 'Cakupan HPP',
    'ROAS', 'Peringatan', 'Aksi'];

  return (
    <div className="space-y-4" data-testid="cycle-view">
      {/* ── KPI gabungan ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-3" data-testid="cycle-kpi">
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Target omzet</p>
          <p className="text-base font-bold">{fmtRp(t.target_revenue)}</p>
          <p className="text-[10px] text-muted-foreground">
            {t.accounts_with_target || 0}/{t.accounts || 0} toko punya target
          </p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Omzet produk</p>
          <p className="text-base font-bold">{fmtRp(t.revenue_product)}</p>
          <p className="text-[10px] text-muted-foreground">order amount {fmtRp(t.revenue_order_amount)}</p>
        </GlassCard>
        {/* SESI #9 — kartu BARU. Bruto di kartu sebelah TIDAK berubah; ini angka
            kedua yang diminta pemilik (omzet sesudah barang diretur). */}
        <GlassCard className="p-4" data-testid="cycle-kpi-returns">
          <p className="text-xs text-muted-foreground">Setelah retur</p>
          <p className="text-base font-bold">{fmtRp(t.revenue_net_returns)}</p>
          <p className="text-[10px] text-muted-foreground">
            {(t.returned_orders || 0) > 0
              ? <>retur {fmtNum(t.returned_orders)} pesanan · {fmtRp(t.returned_amount)} ({pct(t.returns_pct)})</>
              : 'tidak ada retur bulan ini'}
          </p>
          {t.returns_coverage_complete === false && (
            <p className="text-[10px] text-amber-700 dark:text-amber-300 mt-0.5">
              ada hari yang rekapnya diimpor/diketik ⇒ retur BELUM DIKETAHUI (bukan nol)
            </p>
          )}
        </GlassCard>
        <GlassCard className={`p-4 ${(t.revenue_pct || 0) >= (t.pace_pct || 0)
          ? 'border-emerald-400 dark:border-emerald-500/30' : 'border-amber-400 dark:border-amber-500/30'}`}>
          <p className="text-xs text-muted-foreground">Capaian vs pace</p>
          <p className="text-base font-bold">{pct(t.revenue_pct)} <span className="text-xs text-muted-foreground">/ {pct(t.pace_pct)}</span></p>
          <Bar value={t.revenue_pct} reference={t.pace_pct} />
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Anggaran terpakai</p>
          <p className="text-base font-bold">{fmtRp(t.total_spend)}</p>
          <p className="text-[10px] text-muted-foreground">dari rencana {fmtRp(t.total_plan)} · {pct(t.total_used_pct)}</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Marjin kotor</p>
          <p className="text-base font-bold">{fmtRp(t.gross_profit)}</p>
          <p className="text-[10px] text-muted-foreground">cakupan HPP {pct(t.hpp_coverage_pct)}</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs text-muted-foreground">Sisa hari bulan ini</p>
          <p className="text-base font-bold">
            {Math.max((prog.days_total || 0) - (prog.days_elapsed || 0), 0)} hari
          </p>
          <p className="text-[10px] text-muted-foreground">
            {prog.days_elapsed}/{prog.days_total} hari berjalan · {monthLabel}
          </p>
        </GlassCard>
      </div>

      {/* label kejujuran + toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground max-w-2xl" data-testid="cycle-label">
          {data?.label}
        </p>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant={onlyAttention ? 'default' : 'outline'} className="h-8 text-xs"
            onClick={() => setOnlyAttention((v) => !v)} data-testid="cycle-filter-attention">
            <AlertTriangle size={12} className="mr-1" />
            Hanya perlu perhatian ({(data?.attention || []).length})
          </Button>
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={exportCsv}
            data-testid="cycle-export-csv">
            <Download size={12} className="mr-1" /> CSV
          </Button>
          <div className="flex rounded-md border border-border overflow-hidden">
            <button type="button" onClick={() => setView('table')} data-testid="cycle-view-table"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 ${view === 'table'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <Table2 size={12} /> Tabel
            </button>
            <button type="button" onClick={() => setView('grid')} data-testid="cycle-view-grid"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 ${view === 'grid'
                ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground'}`}>
              <LayoutGrid size={12} /> Kartu
            </button>
          </div>
          <Button size="sm" variant="outline" className="h-8" onClick={load} disabled={loading}
            data-testid="cycle-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {/* papan perlu perhatian — diurutkan backend (merah dulu) */}
      {(data?.attention || []).length > 0 && (
        <Card data-testid="cycle-attention-board">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-amber-500" />
              Perlu perhatian — {t.flags_red || 0} merah · {t.flags_yellow || 0} kuning
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-1.5">
            {(data.attention || []).slice(0, 8).map((a) => (
              <button key={a.account_id} type="button"
                onClick={() => setDetail((data.rows || []).find((r) => r.account.id === a.account_id))}
                className="w-full text-left rounded-md border border-border bg-background hover:bg-muted/40 px-3 py-2"
                data-testid={`cycle-attention-${a.account_code}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-foreground">{a.account_name}</span>
                  <span className="flex flex-wrap gap-1">
                    {a.flags.map((f, i) => <SevBadge key={i} severity={f.severity}>{f.title}</SevBadge>)}
                  </span>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* ── TABEL / KARTU ────────────────────────────────────────────────── */}
      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">
          <Loader2 className="mx-auto animate-spin mb-2" size={20} /> Menghitung siklus semua toko…
        </div>
      ) : !rows.length ? (
        <div className="py-12 text-center text-muted-foreground text-sm" data-testid="cycle-empty">
          {onlyAttention ? 'Tidak ada toko yang perlu perhatian bulan ini.'
            : 'Belum ada toko aktif untuk periode ini.'}
        </div>
      ) : view === 'table' ? (
        <div className="rounded-lg border border-border overflow-x-auto bg-background">
          <table className="w-full text-xs" data-testid="cycle-table">
            <thead className="bg-muted/60">
              <tr>{HEADS.map((h) => (
                <th key={h} className="px-2.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
              ))}</tr>
            </thead>
            <tbody className="divide-y [&_td]:align-top">
              {rows.map((r) => {
                const ach = r.achievement || {};
                const b = r.budget || {};
                const m = r.margin || {};
                const behind = (r.flags || []).some((f) => f.code === 'target_behind');
                const over = (b.total_spend || 0) > (b.total_plan || 0) && (b.total_plan || 0) > 0;
                return (
                  <tr key={r.account.id} className="hover:bg-muted/30"
                    data-testid={`cycle-row-${r.account.account_code}`}>
                    <td className="px-2.5 py-2">
                      <div className="font-semibold text-foreground">{r.account.account_name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {r.account.account_code} · {r.account.platform}
                      </div>
                    </td>
                    <td className="px-2.5 py-2">
                      {r.locked
                        ? <Badge variant="outline" className="text-[9px] border-amber-400 text-amber-700 dark:text-amber-300">
                          <Lock size={9} className="mr-1" />Terkunci</Badge>
                        : <Badge variant="outline" className="text-[9px] text-muted-foreground">Terbuka</Badge>}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {r.target?.exists ? fmtRp(r.target.revenue)
                        : <span className="text-muted-foreground">belum diisi</span>}
                    </td>
                    <td className="px-2.5 py-2 font-semibold whitespace-nowrap">{fmtRp(r.actual?.revenue_product)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap text-muted-foreground">{fmtRp(r.actual?.revenue_order_amount)}</td>
                    {/* SESI #9 — nilai retur & omzet setelah retur (kolom BARU) */}
                    <td className="px-2.5 py-2 whitespace-nowrap"
                      data-testid={`cycle-returned-${r.account.account_code}`}>
                      {(r.actual?.returned_orders || 0) > 0
                        ? <span className="text-amber-700 dark:text-amber-300">
                          {fmtRp(r.actual?.returned_amount)}
                          <span className="text-[10px] text-muted-foreground"> · {fmtNum(r.actual?.returned_orders)} pesanan</span>
                        </span>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-2.5 py-2 whitespace-nowrap font-semibold"
                      data-testid={`cycle-net-${r.account.account_code}`}>
                      {fmtRp(r.actual?.revenue_net_returns)}
                      {(r.actual?.returns_pct || 0) > 0 && (
                        <span className="text-[10px] text-muted-foreground"> (−{pct(r.actual?.returns_pct)})</span>
                      )}
                    </td>
                    <td className="px-2.5 py-2 min-w-[92px]">
                      <span className={behind ? 'text-red-600 font-semibold' : 'font-semibold'}>{pct(ach.revenue_pct)}</span>
                      <Bar value={ach.revenue_pct} reference={ach.pace_pct} over={behind} />
                    </td>
                    <td className="px-2.5 py-2 text-muted-foreground">{pct(ach.pace_pct)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(ach.prorata_target)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(ach.run_rate)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">
                      {fmtNum(r.actual?.orders)}
                      {r.target?.orders ? <span className="text-muted-foreground"> / {fmtNum(r.target.orders)}</span> : null}
                    </td>
                    <td className="px-2.5 py-2">{fmtNum(r.actual?.units)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(r.actual?.aov)}</td>
                    <td className="px-2.5 py-2 whitespace-nowrap">{fmtRp(b.total_plan)}</td>
                    <td className={`px-2.5 py-2 whitespace-nowrap ${over ? 'text-red-600 font-semibold' : ''}`}>{fmtRp(b.total_spend)}</td>
                    <td className={`px-2.5 py-2 whitespace-nowrap ${(b.total_remaining || 0) < 0 ? 'text-red-600' : ''}`}>{fmtRp(b.total_remaining)}</td>
                    <td className="px-2.5 py-2">{pct(b.total_used_pct)}</td>
                    <td className="px-2.5 py-2">{pct(m.gross_margin_pct)}</td>
                    <td className="px-2.5 py-2">
                      <span className={m.trustworthy ? 'text-emerald-600' : 'text-amber-600'}>
                        {pct(m.hpp_coverage_pct)}
                      </span>
                    </td>
                    <td className="px-2.5 py-2">{Number(r.roi?.roas || 0).toFixed(2)}</td>
                    <td className="px-2.5 py-2">
                      <div className="flex flex-wrap gap-1 w-[168px]">
                        {(r.flags || []).length === 0
                          ? <span className="text-emerald-600 flex items-center gap-1 whitespace-nowrap"><CheckCircle2 size={11} /> aman</span>
                          : <>
                            {/* Maksimal 2 badge supaya baris tabel tidak menjadi
                                dua kali lebih tinggi dari baris lain (4 badge yang
                                membungkus membuat seluruh baris melebar & sulit
                                dipindai). Sisanya diringkas "+N" dan lengkapnya
                                ada di dialog Detail. */}
                            {(r.flags || []).slice(0, 2).map((f, i) => (
                              <span key={i} title={`${f.title} — ${f.message}`} className="whitespace-nowrap">
                                <SevBadge severity={f.severity}>
                                  {FLAG_SHORT[f.code] || f.code}
                                </SevBadge>
                              </span>
                            ))}
                            {(r.flags || []).length > 2 && (
                              <button type="button" onClick={() => setDetail(r)}
                                title={(r.flags || []).slice(2).map((f) => f.title).join(' · ')}
                                className="text-[10px] underline text-muted-foreground hover:text-foreground"
                                data-testid={`cycle-flags-more-${r.account.account_code}`}>
                                +{(r.flags || []).length - 2} lagi
                              </button>
                            )}
                          </>}
                      </div>
                    </td>
                    <td className="px-2.5 py-2">
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]"
                          onClick={() => setTarget(r)} data-testid={`cycle-set-target-${r.account.account_code}`}>
                          <Target size={10} className="mr-0.5" />Target
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]"
                          onClick={() => setBudget(r)} data-testid={`cycle-set-budget-${r.account.account_code}`}>
                          <Wallet size={10} className="mr-0.5" />Anggaran
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]"
                          onClick={() => setLockRow(r)} data-testid={`cycle-lock-${r.account.account_code}`}>
                          {r.locked ? <Unlock size={10} /> : <Lock size={10} />}
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]"
                          onClick={() => setDetail(r)} data-testid={`cycle-detail-${r.account.account_code}`}>
                          <Eye size={10} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="cycle-grid">
          {rows.map((r) => {
            const ach = r.achievement || {};
            const b = r.budget || {};
            const behind = (r.flags || []).some((f) => f.code === 'target_behind');
            return (
              <Card key={r.account.id} data-testid={`cycle-card-${r.account.account_code}`}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-sm">{r.account.account_name}</CardTitle>
                      <p className="text-[10px] text-muted-foreground">
                        {r.account.account_code} · {r.account.platform}
                      </p>
                    </div>
                    {r.locked
                      ? <Badge variant="outline" className="text-[9px] border-amber-400 text-amber-700 dark:text-amber-300">Terkunci</Badge>
                      : <Badge variant="outline" className="text-[9px] text-muted-foreground">Terbuka</Badge>}
                  </div>
                </CardHeader>
                <CardContent className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between"><span className="text-muted-foreground">Target</span>
                    <span>{r.target?.exists ? fmtRp(r.target.revenue) : 'belum diisi'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Omzet produk</span>
                    <span className="font-semibold">{fmtRp(r.actual?.revenue_product)}</span></div>
                  {/* SESI #9 — retur juga terlihat pada tampilan kartu */}
                  <div className="flex justify-between"><span className="text-muted-foreground">Setelah retur</span>
                    <span className="font-semibold">
                      {fmtRp(r.actual?.revenue_net_returns)}
                      {(r.actual?.returned_orders || 0) > 0 && (
                        <span className="text-[10px] text-amber-700 dark:text-amber-300">
                          {' '}(retur {fmtNum(r.actual?.returned_orders)} · {fmtRp(r.actual?.returned_amount)})
                        </span>
                      )}
                    </span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Capaian / pace</span>
                    <span className={behind ? 'text-red-600 font-semibold' : ''}>
                      {pct(ach.revenue_pct)} / {pct(ach.pace_pct)}</span></div>
                  <Bar value={ach.revenue_pct} reference={ach.pace_pct} over={behind} />
                  <div className="flex justify-between"><span className="text-muted-foreground">Anggaran</span>
                    <span>{fmtRp(b.total_spend)} / {fmtRp(b.total_plan)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Marjin (cakupan HPP)</span>
                    <span>{pct(r.margin?.gross_margin_pct)} ({pct(r.margin?.hpp_coverage_pct)})</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">ROAS</span>
                    <span>{Number(r.roi?.roas || 0).toFixed(2)}</span></div>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {(r.flags || []).length === 0
                      ? <span className="text-emerald-600 text-[10px] flex items-center gap-1"><CheckCircle2 size={10} /> aman</span>
                      : (r.flags || []).map((f, i) => (
                        <span key={i} title={f.message}>
                          <SevBadge severity={f.severity}>{f.title}</SevBadge>
                        </span>
                      ))}
                  </div>
                  <div className="flex flex-wrap gap-1 pt-1.5">
                    <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]" onClick={() => setTarget(r)}>
                      <Target size={10} className="mr-0.5" />Target
                    </Button>
                    <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]" onClick={() => setBudget(r)}>
                      <Wallet size={10} className="mr-0.5" />Anggaran
                    </Button>
                    <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]" onClick={() => setLockRow(r)}>
                      {r.locked ? <Unlock size={10} /> : <Lock size={10} />}
                    </Button>
                    <Button size="sm" variant="outline" className="h-6 px-1.5 text-[10px]" onClick={() => setDetail(r)}>
                      <Eye size={10} />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* ringkasan bawah — arah yang harus dibaca sebelum keluar layar */}
      {!loading && rows.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3 text-[11px] text-muted-foreground"
          data-testid="cycle-footer-note">
          <p className="flex items-center gap-1 text-foreground font-semibold mb-1">
            {(t.revenue_pct || 0) >= (t.pace_pct || 0)
              ? <TrendingUp size={12} className="text-emerald-600" />
              : <TrendingDown size={12} className="text-red-600" />}
            {(t.revenue_pct || 0) >= (t.pace_pct || 0)
              ? 'Gabungan semua toko sedang di atas pace target.'
              : 'Gabungan semua toko sedang di bawah pace target.'}
          </p>
          <p>
            Angka di layar ini dihitung backend dari satu sumber (rekap harian turunan +
            pesanan + data iklan + shift live host). Realisasi anggaran bertanda
            <b> auto</b> tidak ditulis sebagai entri belanja, jadi tidak akan dobel dengan
            catatan manual. {scope === 'management' ? 'Tampilan Manajemen: semua toko.' : ''}
          </p>
        </div>
      )}

      <TargetDialog open={!!target} onOpenChange={(v) => !v && setTarget(null)}
        row={target} period={period} token={token} onSaved={load} />
      <BudgetDialog open={!!budget} onOpenChange={(v) => !v && setBudget(null)}
        row={budget} period={period} token={token} onSaved={load}
        categories={data?.categories || []} />
      <LockDialog open={!!lockRow} onOpenChange={(v) => !v && setLockRow(null)}
        row={lockRow} period={period} token={token} onSaved={load} />
      <DetailDialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}
        row={detail} period={period} token={token} />
    </div>
  );
}
