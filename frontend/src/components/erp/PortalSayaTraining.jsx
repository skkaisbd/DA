import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, BookOpen, CheckCircle2, Clock, Award, AlertCircle, Download } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CFG = {
  completed: { label: 'Selesai', color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
  enrolled:  { label: 'Sedang Belajar', color: 'bg-blue-100 text-blue-800', icon: Clock },
  pending:   { label: 'Belum Mulai', color: 'bg-muted text-foreground', icon: BookOpen },
};

export default function PortalSayaTraining({ user, headers }) {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState({});

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/api/portal/training`, { headers });
      setData(d);
    } catch (e) {
      if (e.response?.status === 409) setData({ error: e.response.data.detail });
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const downloadCertificate = async (item) => {
    const id = item.id;
    setDownloading(p => ({ ...p, [id]: true }));
    try {
      const res = await axios.get(`${API}/api/portal/training/${id}/certificate`, {
        headers,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `sertifikat_${item.course_title?.replace(/ /g, '_') || 'kursus'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: 'Sertifikat berhasil diunduh.' });
    } catch (e) {
      toast({ title: 'Gagal mengunduh sertifikat.', description: e.response?.data?.detail, variant: 'destructive' });
    } finally {
      setDownloading(p => ({ ...p, [id]: false }));
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>
  );

  if (data?.error) return (
    <div className="p-6 max-w-2xl mx-auto">
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="pt-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-amber-800">{data.error}</p>
        </CardContent>
      </Card>
    </div>
  );

  const total = data?.total || 0;
  const completed = data?.items?.filter(i => i.status === 'completed').length || 0;
  const pct = total ? Math.round(completed / total * 100) : 0;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      <h2 className="text-lg font-bold">Training & LMS Saya</h2>

      {/* Summary card */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="pt-5">
          <div className="flex items-center gap-4">
            <div className="relative w-16 h-16">
              <svg className="w-16 h-16 -rotate-90" viewBox="0 0 40 40">
                <circle cx="20" cy="20" r="15" fill="none" stroke="#e2e8f0" strokeWidth="4" />
                <circle cx="20" cy="20" r="15" fill="none" stroke="#6366f1" strokeWidth="4"
                  strokeDasharray={`${pct * 0.942} 94.2`} strokeLinecap="round" />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">{pct}%</span>
            </div>
            <div>
              <p className="font-bold text-lg">{completed} / {total} Kursus Selesai</p>
              <p className="text-sm text-muted-foreground">{data?.employee}</p>
              {completed > 0 && (
                <p className="text-xs text-green-600 mt-0.5 flex items-center gap-1">
                  <Award className="w-3 h-3" /> {completed} sertifikat tersedia untuk diunduh
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {total === 0 && (
        <div className="text-center py-10 text-muted-foreground">
          <BookOpen className="w-10 h-10 mx-auto mb-2 opacity-30" />
          <p>Belum ada enrollment training.</p>
        </div>
      )}

      <div className="grid gap-3">
        {data?.items?.map((item, i) => {
          const cfg = STATUS_CFG[item.status] || STATUS_CFG.pending;
          const Icon = cfg.icon;
          const isCompleted = item.status === 'completed';
          return (
            <Card key={i} className="hover:shadow-sm transition-shadow" data-testid={`training-card-${i}`}>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    isCompleted ? 'bg-green-100' : 'bg-primary/10'
                  }`}>
                    {isCompleted
                      ? <CheckCircle2 className="w-5 h-5 text-green-600" />
                      : <BookOpen className="w-5 h-5 text-primary" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2 flex-wrap">
                      <div className="flex-1">
                        <p className="font-medium text-sm">{item.course_title || '(Kursus tidak ada)'}</p>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>
                            <Icon className="w-3 h-3 inline mr-1" />{cfg.label}
                          </span>
                          {item.course_category && (
                            <span className="text-xs text-muted-foreground">{item.course_category}</span>
                          )}
                        </div>
                      </div>
                      {isCompleted && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => downloadCertificate(item)}
                          disabled={downloading[item.id]}
                          data-testid={`btn-cert-${i}`}
                          className="h-8 text-xs border-green-300 text-green-700 hover:bg-green-50 shrink-0"
                        >
                          {downloading[item.id]
                            ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Loading...</>
                            : <><Download className="w-3 h-3 mr-1" /> Sertifikat</>}
                        </Button>
                      )}
                    </div>
                    {item.progress_pct !== undefined && !isCompleted && (
                      <div className="mt-2">
                        <div className="flex justify-between text-xs text-muted-foreground mb-1">
                          <span>Progress</span>
                          <span>{item.progress_pct || 0}%</span>
                        </div>
                        <div className="w-full bg-muted rounded-full h-1.5">
                          <div
                            className="bg-primary h-1.5 rounded-full transition-all"
                            style={{ width: `${item.progress_pct || 0}%` }}
                          />
                        </div>
                      </div>
                    )}
                    {item.completed_at && (
                      <div className="flex items-center gap-1 mt-1 text-xs text-green-600">
                        <Award className="w-3 h-3" /> Selesai: {item.completed_at?.slice(0, 10)}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
