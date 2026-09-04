import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, FileText, ChevronDown, ChevronUp, AlertCircle, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n || 0);
}

/** BUG-3 (2026-07-26): karyawan sama sekali TIDAK punya cara mengunduh slip
 *  gajinya sendiri — endpoint PDF menolak 403 "Hubungi HR" dan layar ini tidak
 *  punya tombol apa pun. Slip gaji adalah dokumen milik karyawan (dipakai untuk
 *  pengajuan kredit dsb), jadi unduhan mandiri kini tersedia. */
function SlipDetail({ slip, token }) {
  const [open, setOpen] = useState(false);
  const [dl, setDl] = useState(false);
  const { toast } = useToast();

  const download = async (e) => {
    e.stopPropagation();
    setDl(true);
    try {
      const r = await fetch(`${API}/api/rahaza/payslips/${slip.id}/pdf`, {
        headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) {
        const msg = await r.json().catch(() => ({}));
        throw new Error(msg.detail || `HTTP ${r.status}`);
      }
      const blob = await r.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = `slip_gaji_${slip.period_from || ''}_${slip.period_to || ''}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(href);
      toast({ title: 'Slip gaji diunduh', description: 'PDF tersimpan di perangkat Anda.' });
    } catch (err) {
      toast({ title: 'Gagal mengunduh slip', description: String(err.message), variant: 'destructive' });
    } finally { setDl(false); }
  };

  return (
    <Card className="hover:shadow-sm transition-shadow">
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center justify-between gap-3">
          <button
            data-testid={`slip-toggle-${slip.id}`}
            className="flex-1 text-left"
            onClick={() => setOpen(v => !v)}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-sm">{slip.period_from?.slice(0, 7) || 'N/A'}</p>
                <p className="text-xs text-muted-foreground">{slip.period_from?.slice(0, 10)} s/d {slip.period_to?.slice(0, 10)}</p>
              </div>
              <div className="text-right">
                <p className="font-bold text-green-700 text-base">{fmt(slip.net_pay)}</p>
                <p className="text-xs text-muted-foreground">Take Home</p>
              </div>
            </div>
          </button>
          <Button size="sm" variant="outline" onClick={download} disabled={dl}
            data-testid={`slip-download-${slip.id}`}>
            {dl ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            <span className="ml-1.5 hidden sm:inline">PDF</span>
          </Button>
          <button type="button" aria-label="Buka rincian slip" onClick={() => setOpen(v => !v)}>
            {open ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </button>
        </div>

        {open && (
          <div className="mt-4 pt-4 border-t space-y-3">
            {/* Ringkasan Kehadiran */}
            {(slip.days_hadir !== undefined || slip.days_hadir != null) && (
              <div className="bg-muted dark:bg-slate-800/30 rounded-lg p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-2">REKAP KEHADIRAN</p>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div>
                    <p className="text-muted-foreground">Hari Hadir</p>
                    <p className="font-bold text-emerald-600">{slip.days_hadir ?? '-'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Total Jam</p>
                    <p className="font-bold">{slip.total_hours_worked ?? '-'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Lembur (jam)</p>
                    <p className="font-bold text-amber-600">{slip.overtime_hours ?? slip.source_refs?.overtime_hours ?? '-'}</p>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-3 text-sm">
              <div className="bg-green-50 rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Gaji Pokok</p>
                {/* FASE 20 — dulu `slip.base_salary` & `slip.total_deductions`: dua
                    field itu TIDAK ADA di payslip (backend menulis `earnings_total`
                    dan `deductions_total`), jadi slip gaji milik karyawan sendiri
                    selalu menampilkan Rp 0 untuk Gaji Pokok & Total Potongan —
                    padahal Take Home-nya benar. Fallback nama lama dipertahankan
                    untuk payslip lama di DB produksi. */}
                <p className="font-semibold mt-1">{fmt(slip.earnings_total ?? slip.base_salary)}</p>
              </div>
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Total Pendapatan</p>
                <p className="font-semibold mt-1">{fmt(slip.gross_pay)}</p>
              </div>
              <div className="bg-red-50 rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Total Potongan</p>
                <p className="font-semibold mt-1 text-red-600">-{fmt(slip.deductions_total ?? slip.total_deductions)}</p>
              </div>
            </div>

            {slip.earnings?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2">PENDAPATAN</p>
                <div className="space-y-1">
                  {slip.earnings.map((e, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-muted-foreground">{e.name}</span>
                      <span>{fmt(e.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {slip.deductions?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2">POTONGAN</p>
                <div className="space-y-1">
                  {slip.deductions.map((d, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-muted-foreground">{d.name}</span>
                      <span className="text-red-600">-{fmt(d.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-between font-bold text-sm border-t pt-3">
              <span>Take Home Pay</span>
              <span className="text-green-700 text-base">{fmt(slip.net_pay)}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function PortalSayaPayslip({ user, headers, token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/api/portal-saya/me/payslips`, { headers });
      setData(d);
    } catch (e) {
      if (e.response?.status === 409) {
        setData({ error: e.response.data.detail });
      }
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
  );

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-5">
      <h2 className="text-lg font-bold">Slip Gaji Saya</h2>

      {data?.error ? (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-amber-800">{data.error}</p>
          </CardContent>
        </Card>
      ) : data ? (
        <>
          <Card className="bg-primary/5 border-primary/20">
            <CardContent className="pt-4 flex items-center gap-4">
              <FileText className="w-8 h-8 text-primary" />
              <div>
                <p className="font-semibold">{data.employee_name || data.employee}</p>
                <p className="text-sm text-muted-foreground">{data.payslips?.length || data.items?.length || 0} slip gaji tersedia</p>
              </div>
            </CardContent>
          </Card>

          {(data.payslips?.length === 0 || data.items?.length === 0) && (
            <div className="text-center py-10 text-muted-foreground">
              <FileText className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>Belum ada slip gaji.</p>
            </div>
          )}

          <div className="space-y-3">
            {(data.payslips || data.items || []).map(slip => <SlipDetail key={slip.id || slip.run_id} slip={slip} token={token} />)}
          </div>
        </>
      ) : null}
    </div>
  );
}
