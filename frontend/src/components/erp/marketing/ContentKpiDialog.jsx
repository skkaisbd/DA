/**
 * ContentKpiDialog — INPUT KPI SATU KONTEN (manual, sesi #35).
 *
 * Kenapa baru ada sekarang: endpoint `POST /content-calendar/{id}/kpi` sudah lama
 * ada, tetapi TIDAK ADA satu layar pun yang memanggilnya — jadi seluruh angka
 * views/engagement/GMV konten hanya bisa lahir dari penyemai demo. Pemilik memilih
 * pengisian MANUAL oleh staf marketing (impor menyusul bila berkasnya dikirim).
 *
 * Dua aturan yang kelihatan di form ini:
 *   · Angka turunan (engagement, eng. rate, CVR, GMV/view, AOV) TIDAK bisa diketik —
 *     ditampilkan sebagai hitungan hidup, yang tersimpan adalah hitungan SERVER.
 *   · Tanpa LINK TERBIT, KPI tidak boleh disimpan (backend menolak 400): angka yang
 *     tidak bisa dicek ulang ke platform tidak layak masuk laporan.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, Calculator, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const FIELDS = [
  ['views', 'Views / tayangan'],
  ['likes', 'Likes'],
  ['comments', 'Komentar'],
  ['shares', 'Dibagikan'],
  ['saves', 'Disimpan'],
  ['watch_time_avg_sec', 'Rata-rata ditonton (detik)'],
  ['ctr', 'CTR (%)'],
  ['orders', 'Pesanan dari konten'],
  ['gmv', 'GMV (Rp)'],
];

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const fmtNum = (n) => new Intl.NumberFormat('id-ID').format(Math.round(n || 0));
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

export default function ContentKpiDialog({ open, onClose, onSaved, token, content }) {
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const [form, setForm] = useState({});
  const [url, setUrl] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !content) return;
    const k = content.kpi || {};
    setForm(Object.fromEntries(FIELDS.map(([f]) => [f, k[f] ?? ''])));
    setUrl(content.published_url || '');
  }, [open, content]);

  const set = (f, v) => setForm((p) => ({ ...p, [f]: v }));

  const derived = useMemo(() => {
    const views = num(form.views);
    const eng = num(form.likes) + num(form.comments) + num(form.shares);
    const orders = num(form.orders);
    const gmv = num(form.gmv);
    return {
      engagement: eng,
      engagement_rate: views > 0 ? (eng / views) * 100 : 0,
      cvr: views > 0 ? (orders / views) * 100 : 0,
      gmv_per_view: views > 0 ? gmv / views : 0,
      aov: orders > 0 ? gmv / orders : 0,
    };
  }, [form]);

  const save = async () => {
    if (!url.trim()) {
      toast.error('Link terbit wajib diisi — KPI tanpa link tidak bisa dicek ulang ke platform.');
      return;
    }
    setSaving(true);
    try {
      // Field yang dikosongkan dikirim `null` — server akan MEMPERTAHANKAN nilai
      // lamanya. Mengirim 0 untuk kolom yang tidak diisi akan menghapus angka yang
      // sudah benar (mis. GMV) tanpa pemakai sadar.
      const payload = Object.fromEntries(FIELDS.map(([f]) => {
        const raw = form[f];
        return [f, raw === '' || raw === null || raw === undefined ? null : num(raw)];
      }));
      await axios.post(`${API}/api/marketing/content-calendar/${content.id}/kpi`,
        { ...payload, published_url: url.trim(), source: 'manual' }, { headers: authH });
      toast.success('KPI konten tersimpan');
      onSaved?.();
      onClose?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Gagal menyimpan KPI konten');
    } finally { setSaving(false); }
  };

  if (!content) return null;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className="max-w-2xl" data-testid="content-kpi-dialog">
        <DialogHeader>
          <DialogTitle className="text-base">Isi KPI Konten</DialogTitle>
        </DialogHeader>

        <div className="text-xs text-muted-foreground -mt-2">
          <span className="font-semibold text-foreground">{content.title}</span>
          {' · '}{content.date}
          {content.content_type_label ? ` · ${content.content_type_label}` : ''}
          {content.account_name ? ` · ${content.account_name}` : ''}
          {content.creator_name ? ` · ${content.creator_name}` : ''}
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
            <Link2 size={11} /> Link terbit (wajib)
          </label>
          <Input value={url} onChange={(e) => setUrl(e.target.value)} className="h-8 text-xs"
            placeholder="https://…" data-testid="kpi-published-url" />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {FIELDS.map(([f, label]) => (
            <div key={f} className="space-y-1">
              <label className="text-[11px] text-muted-foreground">{label}</label>
              <Input type="number" min="0" step="any" className="h-8 text-xs"
                value={form[f] ?? ''} onChange={(e) => set(f, e.target.value)}
                data-testid={`kpi-input-${f}`} />
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-border bg-muted/40 p-3" data-testid="kpi-derived">
          <p className="text-[11px] font-semibold mb-1.5 flex items-center gap-1 text-foreground">
            <Calculator size={11} /> Dihitung sistem (tidak bisa diketik)
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px]">
            <div><span className="text-muted-foreground block">Engagement</span>
              {fmtNum(derived.engagement)}</div>
            <div><span className="text-muted-foreground block">Eng. rate</span>
              {derived.engagement_rate.toFixed(2)}%</div>
            <div><span className="text-muted-foreground block">CVR</span>
              {derived.cvr.toFixed(4)}%</div>
            <div><span className="text-muted-foreground block">GMV / view</span>
              {rp(derived.gmv_per_view.toFixed(0))}</div>
            <div><span className="text-muted-foreground block">AOV</span>
              {rp(derived.aov.toFixed(0))}</div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose} data-testid="kpi-cancel">Batal</Button>
          <Button size="sm" onClick={save} disabled={saving} data-testid="kpi-save">
            {saving ? <Loader2 size={13} className="animate-spin mr-1" /> : null} Simpan KPI
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
