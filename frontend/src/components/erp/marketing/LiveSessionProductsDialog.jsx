/**
 * LiveSessionProductsDialog — isi/ubah rincian produk untuk SATU sesi live yang
 * sudah tersimpan (dipanggil dari tombol “Rincian” pada tabel Live Sessions).
 *
 * Terpisah dari dialog sesi supaya alur nyatanya terlayani: sesi biasanya dicatat
 * segera sesudah live (angka total dari dasbor platform), sedangkan rincian per
 * produk baru dimasukkan belakangan saat laporan produk keluar.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Package, Loader2, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import LiveSessionProductsEditor from './LiveSessionProductsEditor';

const API = process.env.REACT_APP_BACKEND_URL;
const rp = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;

export default function LiveSessionProductsDialog({
  open, onClose, onSaved, token, session,
}) {
  const { toast } = useToast();
  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }), [token]);
  const [lines, setLines] = useState([]);
  const [recon, setRecon] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sessionRevenue, setSessionRevenue] = useState(0);

  const load = useCallback(async () => {
    if (!session?.id) return;
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/api/marketing/live/sessions/${session.id}/products`, { headers: authH });
      const d = r.data?.data || {};
      setLines(d.products || []);
      setRecon(d.reconciliation || null);
      setSessionRevenue(d.reconciliation?.session_revenue ?? session.revenue ?? 0);
    } catch (e) {
      toast({
        title: 'Gagal memuat rincian produk',
        description: e.response?.data?.detail || e.message, variant: 'destructive',
      });
    } finally { setLoading(false); }
  }, [session, authH, toast]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        products: (lines || [])
          .filter((l) => l.catalog_item_id)
          .map((l) => ({
            catalog_item_id: l.catalog_item_id,
            units_sold: Number(l.units_sold || 0),
            revenue: Number(l.revenue || 0),
            orders: Number(l.orders || 0),
            notes: l.notes || '',
          })),
      };
      const r = await axios.put(
        `${API}/api/marketing/live/sessions/${session.id}/products`, payload,
        { headers: authH });
      setRecon(r.data?.data?.reconciliation || null);
      setLines(r.data?.data?.products || []);
      toast({ title: 'Rincian produk disimpan' });
      onSaved?.();
    } catch (e) {
      toast({
        title: 'Gagal menyimpan rincian',
        description: e.response?.data?.detail || e.message, variant: 'destructive',
      });
    } finally { setSaving(false); }
  };

  const syncTotals = async () => {
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/api/marketing/live/sessions/${session.id}/products/sync-session-totals`,
        {}, { headers: authH });
      const d = r.data?.data || {};
      setSessionRevenue(d.after?.revenue ?? sessionRevenue);
      setRecon(d.reconciliation || null);
      toast({
        title: 'Total sesi disamakan dengan rincian',
        description: `${rp(d.before?.revenue)} → ${rp(d.after?.revenue)}`,
      });
      onSaved?.();
    } catch (e) {
      toast({
        title: 'Gagal menyamakan total sesi',
        description: e.response?.data?.detail || e.message, variant: 'destructive',
      });
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="w-4 h-4" /> Rincian Produk — {session?.title || 'Sesi Live'}
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {session?.account_name} · {String(session?.session_date || '').slice(0, 10)}
            {' · '}omzet sesi <b>{rp(sessionRevenue)}</b>
          </p>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground">
            <Loader2 className="animate-spin" size={22} />
          </div>
        ) : (
          <LiveSessionProductsEditor
            token={token} accountId={session?.account_id} lines={lines}
            onChange={setLines} sessionRevenue={sessionRevenue} disabled={saving}
          />
        )}

        {recon?.message && (
          <p className="text-xs text-muted-foreground" data-testid="lp-server-message">
            {recon.message}
          </p>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>Tutup</Button>
          <Button variant="outline" onClick={syncTotals} disabled={saving || !lines.length}
            data-testid="lp-sync-totals" title="Tulis total rincian ke omzet/order sesi">
            <Scale className="w-3.5 h-3.5 mr-1.5" /> Samakan total sesi
          </Button>
          <Button onClick={save} disabled={saving} data-testid="lp-save">
            {saving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            Simpan rincian
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
