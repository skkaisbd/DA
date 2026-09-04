import { useState, useEffect, useCallback, useMemo } from 'react';
import { GlassCard } from '@/components/ui/glass';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Target, Calendar, TrendingUp, Award, FileText, AlertTriangle, Loader2, CheckCircle, Clock } from 'lucide-react';
import { IconButton } from '../IconButton';

const STATUS_COLOR = {
  pending: '#f59e0b',
  in_progress: '#3b82f6',
  completed: '#10b981',
  cancelled: '#64748b',
};

const STATUS_LABEL = {
  pending: 'Pending',
  in_progress: 'Sedang Berjalan',
  completed: 'Selesai',
  cancelled: 'Dibatalkan',
};

export default function MyAnnualReviewModule({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const fetchReview = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/portal-saya/annual-review`, { headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const result = await r.json();
      setData(result?.data || {});
    } catch (e) {
      toast.error(`Gagal memuat data: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchReview(); }, [fetchReview]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-10 h-10 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const employee = data?.employee || {};
  const assignments = data?.assignments || [];
  const reviews = data?.reviews || [];
  const cycles = data?.cycles || [];
  const kpis = data?.kpis || [];

  return (
    <div className="space-y-6 p-6" data-testid="my-annual-review-module">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Target className="w-5 h-5 text-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">My Annual Review</h1>
            <p className="text-sm text-muted-foreground">Penilaian kinerja tahunan dan tugas review</p>
          </div>
        </div>
        <IconButton icon={TrendingUp} onClick={fetchReview} disabled={loading} tooltip="Refresh" />
      </div>

      {/* Employee Info */}
      {employee.name && (
        <GlassCard className="p-6">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-foreground font-bold text-xl">
              {employee.name?.charAt(0)}
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold text-foreground">{employee.name}</h2>
              <p className="text-sm text-muted-foreground">{employee.job_title} • {employee.department}</p>
              <div className="flex items-center gap-2 mt-2">
                <Badge variant="outline">{employee.employee_code || employee.id}</Badge>
                <Badge variant="outline">{employee.grade || 'N/A'}</Badge>
              </div>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Active Cycles */}
      {cycles.length > 0 && (
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="w-5 h-5 text-blue-500" />
            <h2 className="text-lg font-semibold text-foreground">Periode Review Aktif</h2>
          </div>
          <div className="space-y-3">
            {cycles.map(cycle => {
              const sColor = STATUS_COLOR[cycle.status] || '#64748b';
              return (
                <div key={cycle.id} className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-foreground">{cycle.cycle_name}</h3>
                    <Badge style={{ background: sColor }}>{STATUS_LABEL[cycle.status]}</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <div>
                      <span className="font-medium">Mulai:</span> {new Date(cycle.start_date).toLocaleDateString('id-ID')}
                    </div>
                    <div>
                      <span className="font-medium">Selesai:</span> {new Date(cycle.end_date).toLocaleDateString('id-ID')}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}

      {/* Assignments */}
      {assignments.length > 0 && (
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <FileText className="w-5 h-5 text-emerald-500" />
            <h2 className="text-lg font-semibold text-foreground">Tugas Review Saya</h2>
          </div>
          <div className="space-y-2">
            {assignments.map(assign => {
              const sColor = STATUS_COLOR[assign.status] || '#64748b';
              const isReviewer = assign.reviewer_id === (employee.id || employee.employee_code);
              return (
                <div key={assign.id} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)] hover:bg-[var(--glass-hover)] transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {isReviewer ? <Award className="w-4 h-4 text-amber-500" /> : <Clock className="w-4 h-4 text-blue-500" />}
                        <span className="text-sm font-medium text-foreground">
                          {isReviewer ? `Review untuk: ${assign.employee_id}` : `Direview oleh: ${assign.reviewer_id}`}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">Periode: {assign.review_period}</p>
                    </div>
                    <Badge variant="outline" style={{ borderColor: sColor, color: sColor }}>{STATUS_LABEL[assign.status]}</Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}

      {/* Review History */}
      {reviews.length > 0 && (
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-indigo-500" />
            <h2 className="text-lg font-semibold text-foreground">Riwayat Penilaian</h2>
          </div>
          <div className="space-y-2">
            {reviews.map(review => (
              <div key={review.id} className="p-4 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <CheckCircle className="w-5 h-5 text-green-500" />
                    <div>
                      <p className="text-sm font-semibold text-foreground">Periode: {review.review_period || 'N/A'}</p>
                      <p className="text-xs text-muted-foreground">Submitted: {new Date(review.submitted_at).toLocaleDateString('id-ID')}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-foreground">{review.final_score || 0}</div>
                    <div className="text-xs text-muted-foreground">Skor Akhir</div>
                  </div>
                </div>
                {review.criteria_scores && Object.keys(review.criteria_scores).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-[var(--glass-border)]">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Detail Kriteria:</p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(review.criteria_scores).map(([k, v]) => (
                        <div key={k} className="text-xs flex items-center justify-between">
                          <span className="text-muted-foreground">{k}:</span>
                          <span className="font-semibold text-foreground">{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* KPI Assignments */}
      {kpis.length > 0 && (
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-5 h-5 text-purple-500" />
            <h2 className="text-lg font-semibold text-foreground">KPI Assignments</h2>
          </div>
          <div className="space-y-2">
            {kpis.map(kpi => (
              <div key={kpi.id} className="p-3 rounded-lg bg-[var(--glass)] border border-[var(--glass-border)]">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">{kpi.kpi_name || 'KPI'}</p>
                    <p className="text-xs text-muted-foreground">Target: {kpi.target_value} {kpi.unit}</p>
                  </div>
                  {kpi.actual_value !== undefined && (
                    <div className="text-right">
                      <div className="text-lg font-bold text-foreground">{kpi.actual_value}</div>
                      <div className="text-xs text-muted-foreground">Actual</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Empty State */}
      {assignments.length === 0 && reviews.length === 0 && cycles.length === 0 && kpis.length === 0 && (
        <GlassCard className="p-12">
          <div className="flex flex-col items-center justify-center text-center">
            <Target className="w-16 h-16 text-muted-foreground/40 mb-4" />
            <p className="text-sm text-muted-foreground">Belum ada data penilaian tahunan yang tersedia</p>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
