/**
 * AdsEntryDialog — form input/ubah BIAYA IKLAN per toko (F16).
 *
 * Kenapa layar ini baru ada sekarang: audit 2026-08-11 menemukan
 * `marketing_ads_routes.py` hanya punya endpoint GET, sehingga biaya iklan
 * **tidak pernah bisa dimasukkan lewat aplikasi**. Semua angka ROAS/CPA/CTR yang
 * dilihat manajemen berasal dari data demo yang tak bisa diperbarui.
 *
 * Dua aturan yang terlihat langsung di form ini:
 *   · TOKO wajib dipilih — belanja iklan tanpa toko tidak bisa dibandingkan
 *     dengan omzet toko mana pun.
 *   · CTR / CPC / CPA / ROAS / CVR TIDAK bisa diketik. Ditampilkan sebagai hasil
 *     hitungan hidup, dan yang tersimpan adalah hitungan SERVER — supaya tidak
 *     ada laporan yang mencampur angka ketikan dengan angka hitungan.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Megaphone, Loader2, Calculator } from 'lucide-react';
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
import { MarketingAccountSelect } from './pickers/MarketingPickers';

const API = process.env.REACT_APP_BACKEND_URL;

const AD_PLATFORM_LABEL = {
  shopee_ads: 'Shopee Ads', tiktok_ads: 'TikTok Ads', meta_ads: 'Meta Ads',
  google_ads: 'Google Ads', affiliate: 'Affiliate', lainnya: 'Lainnya',
};
const STATUS_LABEL = { active: 'Aktif', paused: 'Dijeda', ended: 'Selesai' };

const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

const EMPTY = {
  account_id: '', date: '', campaign_name: '', campaign_id: '',
  ad_platform: 'shopee_ads', ad_type: '', spend: '', impressions: '',
  clicks: '', conversions: '', revenue: '', status: 'active', notes: '',
};

export default function AdsEntryDialog({ open, onClose, onSaved, token, entry }) {
  const { toast } = useToast();
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (entry) {
      setForm({
        ...EMPTY, ...entry,
        date: String(entry.date || '').slice(0, 10),
        spend: entry.spend ?? '', impressions: entry.impressions ?? '',
        clicks: entry.clicks ?? '', conversions: entry.conversions ?? '',
        revenue: entry.revenue ?? '',
      });
    } else {
      setForm({ ...EMPTY, date: new Date().toISOString().slice(0, 10) });
    }
  }, [open, entry]);

  const set = (k) => (e) => setForm((f) => ({
    ...f, [k]: e?.target ? e.target.value : e,
  }));

  const n = (k) => Number(form[k] || 0);
  const derived = {
    ctr: n('impressions') ? (n('clicks') / n('impressions') * 100) : 0,
    cpc: n('clicks') ? (n('spend') / n('clicks')) : 0,
    cpa: n('conversions') ? (n('spend') / n('conversions')) : 0,
    roas: n('spend') ? (n('revenue') / n('spend')) : 0,
    cvr: n('clicks') ? (n('conversions') / n('clicks') * 100) : 0,
  };

  const submit = async () => {
    if (!form.account_id) { toast({ title: 'Pilih toko dulu', variant: 'destructive' }); return; }
    if (!form.date || !form.campaign_name) {
      toast({ title: 'Tanggal & nama kampanye wajib', variant: 'destructive' }); return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        spend: Number(form.spend || 0), impressions: Number(form.impressions || 0),
        clicks: Number(form.clicks || 0), conversions: Number(form.conversions || 0),
        revenue: Number(form.revenue || 0),
      };
      if (entry?.id) {
        delete payload.account_id;
        await axios.put(`${API}/api/marketing/ads/campaigns/${entry.id}`, payload, { headers: authH });
      } else {
        await axios.post(`${API}/api/marketing/ads/campaigns`, payload, { headers: authH });
      }
      toast({ title: entry?.id ? 'Data iklan diperbarui' : 'Biaya iklan disimpan' });
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
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Megaphone className="w-4 h-4" />
            {entry?.id ? 'Ubah Biaya Iklan' : 'Input Biaya Iklan'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {entry?.id ? (
              <div>
                <label className="text-xs font-medium mb-1 block">Toko / Akun</label>
                <Input value={entry.account_name || '—'} disabled className="h-9" />
                <p className="text-[11px] text-muted-foreground mt-1">
                  Toko tidak bisa dipindah setelah tersimpan — buat baris baru bila salah toko.
                </p>
              </div>
            ) : (
              <MarketingAccountSelect token={token} value={form.account_id}
                onChange={(v) => setForm((f) => ({ ...f, account_id: v }))}
                testId="ads-account-select" />
            )}
            <div>
              <label className="text-xs font-medium mb-1 block">Tanggal <span className="text-red-500">*</span></label>
              <Input type="date" value={form.date} onChange={set('date')}
                className="h-9" data-testid="ads-date" />
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Nama Kampanye <span className="text-red-500">*</span></label>
              <Input value={form.campaign_name} onChange={set('campaign_name')}
                placeholder="Flash Sale Gamis Agustus" className="h-9" data-testid="ads-campaign" />
            </div>
            <div>
              <label className="text-xs font-medium mb-1 block">Saluran Iklan</label>
              <Select value={form.ad_platform} onValueChange={set('ad_platform')}>
                <SelectTrigger className="h-9" data-testid="ads-platform"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(AD_PLATFORM_LABEL).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {[['spend', 'Biaya Iklan (Rp)'], ['revenue', 'Revenue dari Iklan (Rp)'],
              ['impressions', 'Impresi'], ['clicks', 'Klik'], ['conversions', 'Konversi']].map(([k, l]) => (
                <div key={k}>
                  <label className="text-xs font-medium mb-1 block">{l}</label>
                  <Input type="number" min="0" value={form[k]} onChange={set(k)}
                    className="h-9 tabular-nums" data-testid={`ads-${k}`} />
                </div>
              ))}
            <div>
              <label className="text-xs font-medium mb-1 block">Status</label>
              <Select value={form.status} onValueChange={set('status')}>
                <SelectTrigger className="h-9" data-testid="ads-status"><SelectValue /></SelectTrigger>
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
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs" data-testid="ads-derived">
              <div><span className="text-muted-foreground">CTR</span><br /><b>{derived.ctr.toFixed(2)}%</b></div>
              <div><span className="text-muted-foreground">CPC</span><br /><b>{rp(derived.cpc.toFixed(0))}</b></div>
              <div><span className="text-muted-foreground">CPA</span><br /><b>{rp(derived.cpa.toFixed(0))}</b></div>
              <div><span className="text-muted-foreground">ROAS</span><br /><b>{derived.roas.toFixed(2)}x</b></div>
              <div><span className="text-muted-foreground">CVR</span><br /><b>{derived.cvr.toFixed(2)}%</b></div>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium mb-1 block">Catatan</label>
            <Textarea value={form.notes} onChange={set('notes')} rows={2}
              placeholder="mis. tes kreatif baru, target audiens…" data-testid="ads-notes" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Batal</Button>
          <Button onClick={submit} disabled={saving} data-testid="ads-save">
            {saving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            {entry?.id ? 'Simpan perubahan' : 'Simpan'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
