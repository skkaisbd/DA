/**
 * Analytics Tab - LiveHost Performance Analytics
 */

import { useState, useEffect, useCallback } from 'react';
import { BarChart3, RefreshCw, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const API = process.env.REACT_APP_BACKEND_URL;
const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
const fmtRp = (n) => `Rp ${fmt(n)}`;

export default function AnalyticsTab({ authH }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [hostPerformance, setHostPerformance] = useState([]);
  const [shiftAnalysis, setShiftAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const [perfRes, shiftRes] = await Promise.all([
        fetch(`${API}/api/marketing/livehost/analytics/host-performance?month=${month}`, { headers: authH }),
        fetch(`${API}/api/marketing/livehost/analytics/shift-analysis?month=${month}`, { headers: authH }),
      ]);

      if (perfRes.ok) {
        const perfData = await perfRes.json();
        setHostPerformance(perfData.performance || []);
      }

      if (shiftRes.ok) {
        const shiftData = await shiftRes.json();
        setShiftAnalysis(shiftData);
      }
    } catch (e) {
      toast.error('Gagal memuat analytics');
    } finally {
      setLoading(false);
    }
  }, [authH, month]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  const changeMonth = (offset) => {
    const [year, mon] = month.split('-').map(Number);
    const date = new Date(year, mon - 1 + offset, 1);
    setMonth(date.toISOString().slice(0, 7));
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(hostPerformance, 10);
  return (
    <div className="space-y-6">
      {/* Month Selector */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => changeMonth(-1)} className="h-9">
            <ChevronLeft size={14} />
          </Button>
          <Input
            type="month"
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="w-40 h-9"
            data-testid="analytics-month-selector"
          />
          <Button variant="outline" size="sm" onClick={() => changeMonth(1)} className="h-9">
            <ChevronRight size={14} />
          </Button>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAnalytics} className="h-9">
          <RefreshCw size={14} className="mr-1.5" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* Host Performance Table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Host Performance - {month}</CardTitle>
            </CardHeader>
            <CardContent>
              {hostPerformance.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <BarChart3 size={40} className="mx-auto mb-2 opacity-40" />
                  <p className="text-sm">Belum ada data performance untuk bulan ini</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="host-performance-table">
                    <thead>
                      <tr className="border-b bg-muted/30">
                        <th className="px-4 py-3 text-left text-xs font-semibold">Rank</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold">LiveHost</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Shifts</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Hours</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Revenue</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Orders</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Viewers</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold">Avg Rev/Shift</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {paged.map((host, idx) => (
                        <tr key={host.host_id} className="hover:bg-muted/30">
                          <td className="px-4 py-3 text-center">
                            {idx === 0 && <span className="text-lg">🥇</span>}
                            {idx === 1 && <span className="text-lg">🥈</span>}
                            {idx === 2 && <span className="text-lg">🥉</span>}
                            {idx > 2 && <span className="text-muted-foreground">#{idx + 1}</span>}
                          </td>
                          <td className="px-4 py-3 font-medium">{host.host_name}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{host.total_shifts}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{host.total_hours.toFixed(1)}</td>
                          <td className="px-4 py-3 text-right tabular-nums font-medium">{fmtRp(host.total_revenue)}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{fmt(host.total_orders)}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{fmt(host.total_viewers)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                            {fmtRp(host.avg_revenue_per_shift)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Shift Analysis */}
          {shiftAnalysis && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* By Shift Type */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Performance by Shift Type</CardTitle>
                </CardHeader>
                <CardContent>
                  {shiftAnalysis.by_shift_type.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">No data</p>
                  ) : (
                    <div className="space-y-3">
                      {shiftAnalysis.by_shift_type.map(shift => (
                        <div key={shift.shift_type} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                          <div>
                            <p className="text-sm font-medium capitalize">{shift.shift_type}</p>
                            <p className="text-xs text-muted-foreground">{shift.count} shifts</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold">{fmtRp(shift.avg_revenue)}</p>
                            <p className="text-xs text-muted-foreground">avg/shift</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* By Day of Week */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Performance by Day of Week</CardTitle>
                </CardHeader>
                <CardContent>
                  {shiftAnalysis.by_day_of_week.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">No data</p>
                  ) : (
                    <div className="space-y-3">
                      {shiftAnalysis.by_day_of_week.map(day => (
                        <div key={day.day} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                          <div>
                            <p className="text-sm font-medium">{day.day}</p>
                            <p className="text-xs text-muted-foreground">{day.count} shifts</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold">{fmtRp(day.avg_revenue)}</p>
                            <p className="text-xs text-muted-foreground">avg/shift</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
