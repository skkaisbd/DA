/**
 * LiveSessionDialog — form input/ubah SESI LIVE (F16).
 *
 * Kenapa layar ini baru ada sekarang: audit 2026-08-11 menemukan
 * `marketing_live_sessions_routes.py` hanya punya endpoint GET — sesi live tidak
 * bisa dicatat lewat aplikasi, padahal di situlah bertemunya omzet toko, jam
 * kerja host, dan performa produk.
 *
 * Dua aturan yang ditegakkan dan terlihat di form:
 *   · TOKO wajib, lalu HOST dipilih dari daftar yang SUDAH di-assign ke toko itu.
 *     Server menolak host yang belum di-assign — supaya jam kerja & bayarannya
 *     tidak dibebankan ke toko yang tidak memakainya.
 *   · Engagement / conversion / AOV dihitung, tidak diketik.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Video, Loader2, Calculator } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import { MarketingAccountSelect, MarketingHostSelect } from './pickers/MarketingPickers';
import LiveSessionProductsEditor from './LiveSessionProductsEditor';

const API = process.env.REACT_APP_BACKEND_URL;
const STATUS_LABEL = {
  scheduled: 'Dijadwalkan', live: 'Sedang Live',
  completed: 'Selesai', cancelled: 'Dibatalkan',
};
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

const EMPTY = {
  account_id: '', host_id: '', session_date: '', title: '', start_time: '',
  duration_minutes: '', peak_viewers: '', total_viewers: '', likes: '',
  comments: '', shares: '', orders: '', revenue: '', units_sold: '',
  products_featured: '', status: 'completed', notes_text: '',
};

export default function LiveSessionDialog({ open, onClose, onSaved, token, session }) {
  const { toast } = useToast();
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  // F18#3 — rincian produk ikut satu form/satu simpan.
  const [lines, setLines] = useState([]);

  useEffect(() => {
    if (!open) return;
    if (session) {
      setForm({
        ...EMPTY, ...session,
        session_date: String(session.session_date || '').slice(0, 10),
        notes_text: '',
      });
      // rincian yang sudah ada dimuat supaya menyimpan sesi tidak menghapusnya
      (async () => {
        try {
          const r = await axios.get(
            `${API}/api/marketing/live/sessions/${session.id}/products`, { headers: authH });
          setLines(r.data?.data?.products || []);
        } catch (e) { setLines([]); }
      })();
    } else {
      setForm({ ...EMPTY, session_date: new Date().toISOString().slice(0, 10) });
      setLines([]);
    }
  }, [open, session, authH]);

  const set = (k) => (e) => setForm((f) => ({
    ...f, [k]: e?.target ? e.target.value : e,
  }));
  const n = (k) => Number(form[k] || 0);
  const derived = {
    engagement: n('total_viewers')
      ? ((n('likes') + n('comments') + n('shares')) / n('total_viewers') * 100) : 0,
    conversion: n('total_viewers') ? (n('orders') / n('total_viewers') * 100) : 0,
    aov: n('orders') ? (n('revenue') / n('orders')) : 0,
    rpm: n('duration_minutes') ? (n('revenue') / n('duration_minutes')) : 0,
  };

  const submit = async () => {
    if (!form.account_id || !form.host_id) {
      toast({ title: 'Toko dan host wajib dipilih', variant: 'destructive' }); return;
    }
    if (!form.session_date || !form.title) {
      toast({ title: 'Tanggal & judul sesi wajib', variant: 'destructive' }); return;
    }
    setSaving(true);
    try {
      const num = ['duration_minutes', 'peak_viewers', 'total_viewers', 'likes',
        'comments', 'shares', 'orders', 'revenue', 'units_sold', 'products_featured'];
      const payload = { ...form };
      num.forEach((k) => { payload[k] = Number(form[k] || 0); });
      // F18#3 — rincian produk dikirim bersama sesinya. Baris tanpa produk
      // (baris kosong yang belum diisi) tidak dikirim, bukan disimpan setengah.
      payload.products = (lines || [])
        .filter((l) => l.catalog_item_id)
        .map((l) => ({
          catalog_item_id: l.catalog_item_id,
          units_sold: Number(l.units_sold || 0),
          revenue: Number(l.revenue || 0),
          orders: Number(l.orders || 0),
          notes: l.notes || '',
        }));
      if (session?.id) {
        await axios.put(`${API}/api/marketing/live/sessions/${session.id}`, payload, { headers: authH });
      } else {
        await axios.post(`${API}/api/marketing/live/sessions`, payload, { headers: authH });
      }
      toast({ title: session?.id ? 'Sesi live diperbarui' : 'Sesi live disimpan' });
      onSaved?.();
      onClose?.();
    } catch (e) {
      toast({
        title: 'Gagal menyimpan',
        description: e.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Video className="w-4 h-4" />
            {session?.id ? 'Ubah Sesi Live' : 'Catat Sesi Live'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <MarketingAccountSelect token={token} value={form.account_id}
              onChange={(v) => {
                // Ganti toko ⇒ rincian produk lama (milik katalog toko lain) tidak
                // sah lagi; dibersihkan di sini supaya penolakan server tidak
                // datang sebagai kejutan saat menyimpan.
                setForm((f) => ({ ...f, account_id: v, host_id: '' }));
                setLines([]);
              }}
              testId="live-account-select" />
            <MarketingHostSelect token={token} accountId={form.account_id}
              value={form.host_id} onChange={(v) => setForm((f) => ({ ...f, host_id: v }))}
              testId="live-host-select" />
            <div>
              <label className="text-xs font-medium mb-1 block">Tanggal Sesi <span className="text-red-500">*</span></label>
              <Input type="date" value={form.session_date} onChange={set('session_date')}
                className="h-9" data-testid="live-date" />
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Jam Mulai</label>
              <Input type="time" value={form.start_time} onChange={set('start_time')}
                className="h-9" data-testid="live-start" />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs font-medium mb-1 block">Judul / Tema Sesi <span className="text-red-500">*</span></label>
              <Input value={form.title} onChange={set('title')}
                placeholder="Live Gamis Malam — Flash Sale" className="h-9" data-testid="live-title" />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {[['duration_minutes', 'Durasi (menit)'], ['peak_viewers', 'Penonton Puncak'],
              ['total_viewers', 'Total Penonton'], ['likes', 'Likes'],
              ['comments', 'Komentar'], ['shares', 'Shares'],
              ['orders', 'Jumlah Order'], ['revenue', 'Revenue (Rp)'],
              ['units_sold', 'Item Terjual'], ['products_featured', 'Produk Dibawakan']]
              .map(([k, l]) => (
                <div key={k}>
                  <label className="text-xs font-medium mb-1 block">{l}</label>
                  <Input type="number" min="0" value={form[k]} onChange={set(k)}
                    className="h-9 tabular-nums" data-testid={`live-${k}`} />
                </div>
              ))}
            <div>
              <label className="text-xs font-medium mb-1 block">Status</label>
              <Select value={form.status} onValueChange={set('status')}>
                <SelectTrigger className="h-9" data-testid="live-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="rounded-[var(--radius-sm)] border border-border bg-muted/40 p-3">
            <p className="text-xs font-medium flex items-center gap-1.5 mb-2">
              <Calculator className="w-3.5 h-3.5" /> Dihitung otomatis (tidak bisa diketik)
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs" data-testid="live-derived">
              <div><span className="text-muted-foreground">Engagement</span><br /><b>{derived.engagement.toFixed(2)}%</b></div>
              <div><span className="text-muted-foreground">Conversion</span><br /><b>{derived.conversion.toFixed(2)}%</b></div>
              <div><span className="text-muted-foreground">AOV</span><br /><b>{rp(derived.aov.toFixed(0))}</b></div>
              <div><span className="text-muted-foreground">Revenue / menit</span><br /><b>{rp(derived.rpm.toFixed(0))}</b></div>
            </div>
          </div>

          <LiveSessionProductsEditor
            token={token} accountId={form.account_id} lines={lines}
            onChange={setLines} sessionRevenue={n('revenue')} disabled={saving}
          />

          <div>
            <label className="text-xs font-medium mb-1 block">Catatan sesi</label>
            <Textarea value={form.notes_text} onChange={set('notes_text')} rows={2}
              placeholder="mis. kendala jaringan menit 40, produk X paling laku…"
              data-testid="live-notes" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving} data-testid="live-save">
            {saving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            {session?.id ? 'Simpan perubahan' : 'Simpan'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
