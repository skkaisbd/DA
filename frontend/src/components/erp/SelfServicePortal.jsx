import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { User, Calendar, FileText, AlertCircle, Loader2, ChevronRight, Building2, Link as LinkIcon, MapPin } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_COLORS = {
  hadir:  'bg-green-100 text-green-800',
  izin:   'bg-blue-100 text-blue-800',
  sakit:  'bg-yellow-100 text-yellow-800',
  alfa:   'bg-red-100 text-red-800',
  cuti:   'bg-purple-100 text-purple-800',
  libur:  'bg-muted text-foreground',
};

function formatCurrency(n) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n || 0);
}

export default function SelfServicePortal({ user, headers, onNavigate }) {
  const { toast } = useToast();
  const [profile, setProfile] = useState(null);
  const [attendance, setAttendance] = useState(null);
  const [payslips, setPayslips] = useState(null);
  const [loading, setLoading] = useState(true);
  const [attFrom, setAttFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10);
  });
  const [attTo, setAttTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [tab, setTab] = useState('kehadiran');

  const loadProfile = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/rahaza/self/profile`, { headers });
      setProfile(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  const loadAttendance = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/rahaza/self/attendance`, { headers, params: { from: attFrom, to: attTo } });
      setAttendance(data);
    } catch (e) {
      if (e.response?.status === 409) {
        // not linked
        setAttendance({ error: e.response.data.detail });
      }
    }
  }, [headers, attFrom, attTo]);

  const loadPayslips = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/rahaza/self/payslips`, { headers });
      setPayslips(data);
    } catch (e) {
      if (e.response?.status === 409) {
        setPayslips({ error: e.response.data.detail });
      }
    }
  }, [headers]);

  useEffect(() => { loadProfile(); }, [loadProfile]);
  useEffect(() => { if (tab === 'kehadiran') loadAttendance(); }, [tab, loadAttendance]);
  useEffect(() => { if (tab === 'payslip') loadPayslips(); }, [tab, loadPayslips]);

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
    </div>
  );

  const notLinked = !profile?.is_linked;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Profile Card */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
              <User className="w-7 h-7 text-primary" />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-semibold">{user?.name || 'Pengguna'}</h2>
              <p className="text-sm text-muted-foreground">{user?.email} · <span className="capitalize">{user?.role}</span></p>
              {profile?.employee && (
                <div className="flex items-center gap-2 mt-1">
                  <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm">{profile.employee.name} · {profile.employee.employee_code} · {profile.employee.job_title}</span>
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              {profile?.is_linked
                ? <Badge className="bg-green-100 text-green-800 border-green-200"><LinkIcon className="w-3 h-3 mr-1" /> Terhubung</Badge>
                : <Badge variant="outline" className="text-yellow-700 border-yellow-300">Belum Terhubung</Badge>
              }
              {/* FASE 15: JANGAN pakai window.location — itu keluar dari SPA,
                  memuat ulang halaman penuh, dan terasa seperti login ulang.
                  Navigasi in-app ke modul 'portal-absen'. */}
              <Button data-testid="absen-now-btn" size="sm"
                onClick={() => (onNavigate ? onNavigate('portal-absen') : window.location.assign('/absen'))}>
                <MapPin className="w-4 h-4 mr-1.5" /> Absen Sekarang
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {notLinked && (
        <Card className="border-yellow-200 bg-yellow-50">
          <CardContent className="pt-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-yellow-800">Akun Belum Terhubung ke Data Karyawan</p>
                <p className="text-sm text-yellow-700 mt-0.5">
                  Untuk melihat kehadiran dan payslip, minta Admin HR untuk menghubungkan akun Anda ke data karyawan melalui menu Manajemen Pengguna.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full">
          <TabsTrigger value="kehadiran" className="flex-1"><Calendar className="w-4 h-4 mr-2" /> Kehadiran Saya</TabsTrigger>
          <TabsTrigger value="payslip" className="flex-1"><FileText className="w-4 h-4 mr-2" /> Payslip Saya</TabsTrigger>
        </TabsList>

        <TabsContent value="kehadiran" className="mt-4">
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="flex items-center gap-2 text-sm">
              <label className="text-muted-foreground">Dari:</label>
              <input type="date" value={attFrom} onChange={e => setAttFrom(e.target.value)} className="border rounded px-2 py-1 text-sm bg-background" />
            </div>
            <div className="flex items-center gap-2 text-sm">
              <label className="text-muted-foreground">Sampai:</label>
              <input type="date" value={attTo} onChange={e => setAttTo(e.target.value)} className="border rounded px-2 py-1 text-sm bg-background" />
            </div>
            <Button variant="outline" size="sm" onClick={loadAttendance}>Tampilkan</Button>
          </div>

          {attendance?.error ? (
            <div className="text-center py-8 text-muted-foreground">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>{attendance.error}</p>
            </div>
          ) : attendance ? (
            <>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4">
                {Object.entries(attendance.summary || {}).map(([k, v]) => (
                  <Card key={k}><CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground capitalize">{k}</p>
                    <p className="text-xl font-bold">{v}</p>
                  </CardContent></Card>
                ))}
              </div>
              <p className="text-sm text-muted-foreground mb-3">Total jam kerja: <strong>{attendance.total_hours_worked} jam</strong></p>
              <div className="rounded-lg border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">Tanggal</th>
                      <th className="text-left px-4 py-2 font-medium">Status</th>
                      <th className="text-left px-4 py-2 font-medium">Masuk</th>
                      <th className="text-left px-4 py-2 font-medium">Keluar</th>
                      <th className="text-right px-4 py-2 font-medium">Jam Kerja</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attendance.records?.map(r => (
                      <tr key={r.id || r.date} className="border-t hover:bg-muted/30">
                        <td className="px-4 py-2">{r.date}</td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[r.status] || STATUS_COLORS.hadir}`}>{r.status}</span>
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">{r.clock_in || r.check_in || '-'}</td>
                        <td className="px-4 py-2 text-muted-foreground">{r.clock_out || r.check_out || '-'}</td>
                        <td className="px-4 py-2 text-right">{r.hours_worked || '-'}</td>
                      </tr>
                    ))}
                    {!attendance.records?.length && (
                      <tr><td colSpan={5} className="text-center py-8 text-muted-foreground">Tidak ada data kehadiran</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : <div className="text-center py-8 text-muted-foreground">Memuat...</div>}
        </TabsContent>

        <TabsContent value="payslip" className="mt-4">
          {payslips?.error ? (
            <div className="text-center py-8 text-muted-foreground">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>{payslips.error}</p>
            </div>
          ) : payslips ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Skema gaji: <strong className="capitalize">{(payslips.pay_scheme || payslips.wage_scheme)?.replace('_', ' ')}</strong> · {payslips.total_slips} payslip
              </p>
              {payslips.slips?.map(slip => (
                <Card key={slip.id} className="hover:shadow-sm transition-shadow">
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{slip.run_period_label || slip.period_from?.slice(0, 7)}</p>
                        <p className="text-xs text-muted-foreground">{slip.period_from?.slice(0, 10)} s/d {slip.period_to?.slice(0, 10)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-bold text-green-700">{formatCurrency(slip.net_pay)}</p>
                        <p className="text-xs text-muted-foreground">Gross: {formatCurrency(slip.gross_pay)}</p>
                      </div>
                      <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-3">
                      <div className="text-xs">
                        <p className="text-muted-foreground">Pendapatan</p>
                        <p className="font-medium">{formatCurrency(slip.gross_pay)}</p>
                      </div>
                      <div className="text-xs">
                        <p className="text-muted-foreground">Potongan</p>
                        {/* FASE 20 — `slip.total_deductions` tidak ada di payslip
                            (backend menulis `deductions_total`) ⇒ selalu Rp 0. */}
                        <p className="font-medium text-red-600">-{formatCurrency(slip.deductions_total ?? slip.total_deductions)}</p>
                      </div>
                      <div className="text-xs">
                        <p className="text-muted-foreground">Take Home</p>
                        <p className="font-bold text-green-700">{formatCurrency(slip.net_pay)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {!payslips.slips?.length && (
                <div className="text-center py-8 text-muted-foreground">
                  <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>Belum ada payslip tersedia.</p>
                </div>
              )}
            </div>
          ) : <div className="text-center py-8 text-muted-foreground">Memuat...</div>}
        </TabsContent>
      </Tabs>
    </div>
  );
}
