import { useState, useEffect, useCallback } from 'react';
import {
  Clock, Plus, RefreshCw, ChevronLeft, ChevronRight, Loader2,
  UserCheck, UserX, BarChart3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { API, fmtRp } from './utils';
import { AttendanceBadge } from './Badges';
import AddShiftModal from './AddShiftModal';
import RecordPerformanceModal from './RecordPerformanceModal';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

export default function ShiftsTab({ authH }) {
  const [shifts, setShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, total: 0, limit: 50 });
  const [filters, setFilters] = useState({
    host_id: 'all',
    account_id: '',
    date_from: '',
    date_to: '',
    attendance_status: 'all',
  });
  const [hosts, setHosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [showAddShiftModal, setShowAddShiftModal] = useState(false);
  const [showPerformanceModal, setShowPerformanceModal] = useState(false);
  const [selectedShift, setSelectedShift] = useState(null);

  const fetchShifts = useCallback(
    async (page = 1) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ page, limit: 50 });
        Object.entries(filters).forEach(([key, val]) => {
          if (val && val !== 'all') params.append(key, val);
        });

        const res = await fetch(`${API}/api/marketing/livehost/shifts?${params}`, { headers: authH });
        if (res.ok) {
          const data = await res.json();
          setShifts(data.shifts || []);
          setPagination(data.pagination || { page: 1, total: 0, limit: 50 });
        }
      } catch (e) {
        toast.error('Gagal memuat data shift');
      } finally {
        setLoading(false);
      }
    },
    [authH, filters]
  );

  const fetchHosts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/marketing/livehost?status=active`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setHosts(data);
      }
    } catch (e) {}
  }, [authH]);

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/marketing/accounts?status=active`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      }
    } catch (e) {}
  }, [authH]);

  useEffect(() => {
    fetchShifts();
    fetchHosts();
    fetchAccounts();
  }, [fetchShifts, fetchHosts, fetchAccounts]);

  const handleClockAction = async (shift, action) => {
    try {
      const res = await fetch(`${API}/api/marketing/livehost/clock`, {
        method: 'POST',
        headers: { ...authH, 'Content-Type': 'application/json' },
        body: JSON.stringify({ shift_id: shift.id, action }),
      });

      if (res.ok) {
        const data = await res.json();
        toast.success(data.message);
        fetchShifts(pagination.page);
      } else {
        const err = await res.json();
        toast.error(err.detail || `Gagal ${action}`);
      }
    } catch (e) {
      toast.error(`Gagal ${action}`);
    }
  };

  const { page, setPage, totalPages, total, paged } = useClientPagination(shifts, 10);
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3 items-end justify-between">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 w-full">
          <div>
            <Label className="text-xs mb-1">LiveHost</Label>
            <Select value={filters.host_id} onValueChange={(v) => setFilters((f) => ({ ...f, host_id: v }))}>
              <SelectTrigger className="h-9" data-testid="filter-host">
                <SelectValue placeholder="Semua Host" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Host</SelectItem>
                {hosts.map((h) => (
                  <SelectItem key={h.id} value={h.id}>
                    {h.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs mb-1">Dari Tanggal</Label>
            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
              className="h-9"
              data-testid="filter-date-from"
            />
          </div>
          <div>
            <Label className="text-xs mb-1">Sampai Tanggal</Label>
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
              className="h-9"
              data-testid="filter-date-to"
            />
          </div>
          <div>
            <Label className="text-xs mb-1">Status</Label>
            <Select
              value={filters.attendance_status}
              onValueChange={(v) => setFilters((f) => ({ ...f, attendance_status: v }))}
            >
              <SelectTrigger className="h-9" data-testid="filter-attendance">
                <SelectValue placeholder="Semua Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Status</SelectItem>
                <SelectItem value="scheduled">Scheduled</SelectItem>
                <SelectItem value="on_time">On Time</SelectItem>
                <SelectItem value="late">Late</SelectItem>
                <SelectItem value="no_show">No Show</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex gap-2 w-full sm:w-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchShifts(pagination.page)}
            className="h-9"
            data-testid="refresh-shifts"
          >
            <RefreshCw size={14} className="mr-1.5" />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowAddShiftModal(true)} className="h-9" data-testid="add-shift-btn">
            <Plus size={14} className="mr-1.5" />
            Tambah Shift
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={28} className="animate-spin text-muted-foreground" />
        </div>
      ) : shifts.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Clock size={40} className="text-muted-foreground opacity-40" />
            <p className="font-medium">Belum ada shift</p>
            <Button size="sm" onClick={() => setShowAddShiftModal(true)}>
              <Plus size={14} className="mr-1.5" />
              Tambah Shift
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="shifts-table">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="px-4 py-3 text-left text-xs font-semibold">Tanggal</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">LiveHost</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">Shift</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">Waktu</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">Performance</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {paged.map((shift) => (
                      <tr key={shift.id} className="hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3 font-medium">{shift.date}</td>
                        <td className="px-4 py-3">{shift.host_name}</td>
                        <td className="px-4 py-3 capitalize">{shift.shift_type}</td>
                        <td className="px-4 py-3 text-xs tabular-nums">
                          {shift.shift_start_time} - {shift.shift_end_time}
                        </td>
                        <td className="px-4 py-3">
                          <AttendanceBadge status={shift.attendance_status} />
                        </td>
                        <td className="px-4 py-3">
                          {shift.revenue > 0 ? (
                            <div className="text-xs">
                              <div className="font-medium">{fmtRp(shift.revenue)}</div>
                              <div className="text-muted-foreground">{shift.orders} orders</div>
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            {shift.attendance_status === 'scheduled' && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-8 text-xs"
                                onClick={() => handleClockAction(shift, 'clock_in')}
                                data-testid={`clock-in-${shift.id}`}
                              >
                                <UserCheck size={12} className="mr-1" />
                                Clock In
                              </Button>
                            )}
                            {(shift.attendance_status === 'on_time' || shift.attendance_status === 'late') &&
                              !shift.clock_out_time && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-8 text-xs"
                                  onClick={() => handleClockAction(shift, 'clock_out')}
                                  data-testid={`clock-out-${shift.id}`}
                                >
                                  <UserX size={12} className="mr-1" />
                                  Clock Out
                                </Button>
                              )}
                            {shift.attendance_status === 'completed' && shift.revenue === 0 && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-8 text-xs"
                                onClick={() => {
                                  setSelectedShift(shift);
                                  setShowPerformanceModal(true);
                                }}
                                data-testid={`record-performance-${shift.id}`}
                              >
                                <BarChart3 size={12} className="mr-1" />
                                Record
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
              </div>
            </CardContent>
          </Card>

          {pagination.total_pages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Showing {shifts.length} of {pagination.total} shifts
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchShifts(pagination.page - 1)}
                  disabled={!pagination.has_prev}
                >
                  <ChevronLeft size={14} />
                </Button>
                <span className="text-sm">
                  Page {pagination.page} of {pagination.total_pages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchShifts(pagination.page + 1)}
                  disabled={!pagination.has_next}
                >
                  <ChevronRight size={14} />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {showAddShiftModal && (
        <AddShiftModal
          hosts={hosts}
          accounts={accounts}
          authH={authH}
          onClose={() => setShowAddShiftModal(false)}
          onSuccess={() => {
            setShowAddShiftModal(false);
            fetchShifts(pagination.page);
          }}
        />
      )}

      {showPerformanceModal && selectedShift && (
        <RecordPerformanceModal
          shift={selectedShift}
          authH={authH}
          onClose={() => {
            setShowPerformanceModal(false);
            setSelectedShift(null);
          }}
          onSuccess={() => {
            setShowPerformanceModal(false);
            setSelectedShift(null);
            fetchShifts(pagination.page);
          }}
        />
      )}
    </div>
  );
}
