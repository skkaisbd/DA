import { useState, useEffect, useCallback } from 'react';
import SmartNativeSelect from '@/components/ui/smart-native-select';
import { Download, Filter, Calendar, Users, Clock, DollarSign, TrendingUp, TrendingDown, FileSpreadsheet } from 'lucide-react';
import { GlassCard, GlassInput } from '@/components/ui/glass';
import { Button } from '@/components/ui/button';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { toast } from 'sonner';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

function StatCard({ title, value, subtitle, icon: Icon, trend, trendValue }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs text-muted-foreground mb-1">{title}</p>
          <p className="text-2xl font-bold text-foreground">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          {trend && (
            <div className={`flex items-center gap-1 mt-2 text-xs ${trend === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
              {trend === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              <span>{trendValue}</span>
            </div>
          )}
        </div>
        {Icon && (
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="w-5 h-5 text-primary" />
          </div>
        )}
      </div>
    </GlassCard>
  );
}

export default function RahazaHRReportsModule({ token }) {
  const [activeTab, setActiveTab] = useState('attendance');
  const [loading, setLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  
  // Filters
  const [dateFrom, setDateFrom] = useState(() => {
    const date = new Date();
    date.setDate(1);
    return date.toISOString().split('T')[0];
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split('T')[0]);
  const [departmentId, setDepartmentId] = useState('');
  const [locationId, setLocationId] = useState('');
  const [shiftId, setShiftId] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [periodCode, setPeriodCode] = useState('');

  // Master data
  const [departments, setDepartments] = useState([]);
  const [locations, setLocations] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [payrollRuns, setPayrollRuns] = useState([]);

  // Report data
  const [attendanceData, setAttendanceData] = useState(null);
  const [overtimeData, setOvertimeData] = useState(null);
  const [payrollData, setPayrollData] = useState(null);
  const [turnoverData, setTurnoverData] = useState(null);

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // Fetch master data
  useEffect(() => {
    const fetchMasterData = async () => {
      try {
        const [deptRes, locRes, shiftRes, empRes, payrollRes] = await Promise.all([
          fetch(`${API_BASE}/api/rahaza/locations`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/rahaza/locations`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/rahaza/shifts`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/rahaza/employees?limit=500`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/rahaza/payroll-runs`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);

        if (deptRes.ok) {
          const data = await deptRes.json();
          setDepartments(Array.isArray(data) ? data : data.items || []);
        }
        if (locRes.ok) {
          const data = await locRes.json();
          setLocations(Array.isArray(data) ? data : data.items || []);
        }
        if (shiftRes.ok) {
          const data = await shiftRes.json();
          setShifts(Array.isArray(data) ? data : data.items || []);
        }
        if (empRes.ok) {
          const data = await empRes.json();
          setEmployees((Array.isArray(data) ? data : data.items || []).filter(e => e.active));
        }
        if (payrollRes.ok) {
          const data = await payrollRes.json();
          setPayrollRuns(Array.isArray(data) ? data : data.items || []);
        }
      } catch (e) {
        console.error('Failed to fetch master data:', e);
      }
    };
    fetchMasterData();
  }, [token]);

  // Fetch report data based on active tab
  const fetchReportData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('from_date', dateFrom);
      if (dateTo) params.append('to_date', dateTo);
      if (departmentId) params.append('department_id', departmentId);
      if (locationId) params.append('location_id', locationId);
      if (shiftId) params.append('shift_id', shiftId);
      if (employeeId) params.append('employee_id', employeeId);
      if (periodCode) params.append('period_code', periodCode);

      let endpoint = '';
      switch (activeTab) {
        case 'attendance':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/attendance-summary?${params}`;
          break;
        case 'overtime':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/overtime-summary?${params}`;
          break;
        case 'payroll':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/payroll-summary?${params}`;
          break;
        case 'turnover':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/turnover?${params}`;
          break;
        default:
          return;
      }

      const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
      const res = await fetch(endpoint, { headers: h });
      if (res.ok) {
        const data = await res.json();
        switch (activeTab) {
          case 'attendance':
            setAttendanceData(data);
            break;
          case 'overtime':
            setOvertimeData(data);
            break;
          case 'payroll':
            setPayrollData(data);
            break;
          case 'turnover':
            setTurnoverData(data);
            break;
        }
      } else {
        toast.error('Gagal memuat data laporan');
      }
    } catch (e) {
      console.error('Failed to fetch report:', e);
      toast.error('Terjadi kesalahan saat memuat laporan');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, dateFrom, dateTo, departmentId, locationId, shiftId, employeeId, periodCode, token]);

  useEffect(() => {
    fetchReportData();
  }, [fetchReportData]);

  const exportExcel = async () => {
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('from_date', dateFrom);
      if (dateTo) params.append('to_date', dateTo);
      if (departmentId) params.append('department_id', departmentId);
      if (locationId) params.append('location_id', locationId);
      if (shiftId) params.append('shift_id', shiftId);
      if (employeeId) params.append('employee_id', employeeId);
      if (periodCode) params.append('period_code', periodCode);

      let endpoint = '';
      switch (activeTab) {
        case 'attendance':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/attendance-summary.xlsx?${params}`;
          break;
        case 'overtime':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/overtime-summary.xlsx?${params}`;
          break;
        case 'payroll':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/payroll-summary.xlsx?${params}`;
          break;
        case 'turnover':
          endpoint = `${API_BASE}/api/rahaza/hr/reports/turnover.xlsx?${params}`;
          break;
        default:
          return;
      }

      const res = await fetch(endpoint, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `hr_report_${activeTab}_${dateFrom}_${dateTo}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        toast.success('File Excel berhasil diunduh');
      } else {
        toast.error('Gagal export Excel');
      }
    } catch (e) {
      console.error('Export failed:', e);
      toast.error('Terjadi kesalahan saat export');
    }
  };

  return (
    <div className="space-y-5" data-testid="hr-reports-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Laporan SDM & Analytics</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Analisis kehadiran, overtime, payroll, dan turnover karyawan dengan visualisasi data.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowFilters(!showFilters)} size="sm">
            <Filter className="w-4 h-4 mr-1.5" />
            {showFilters ? 'Sembunyikan' : 'Tampilkan'} Filter
          </Button>
          <Button onClick={exportExcel} disabled={loading} data-testid="export-excel-btn">
            <Download className="w-4 h-4 mr-1.5" />
            Export Excel
          </Button>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <GlassCard className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Dari Tanggal</label>
              <GlassInput
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                data-testid="filter-date-from"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Sampai Tanggal</label>
              <GlassInput
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                data-testid="filter-date-to"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Department</label>
              <SmartNativeSelect
                value={departmentId}
                onChange={e => setDepartmentId(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="filter-department"
              >
                <option value="">Semua Department</option>
                {departments.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </SmartNativeSelect>
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Location</label>
              <SmartNativeSelect
                value={locationId}
                onChange={e => setLocationId(e.target.value)}
                className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                data-testid="filter-location"
              >
                <option value="">Semua Lokasi</option>
                {locations.map(l => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </SmartNativeSelect>
            </div>
            {activeTab !== 'turnover' && (
              <>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Shift</label>
                  <SmartNativeSelect
                    value={shiftId}
                    onChange={e => setShiftId(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                    data-testid="filter-shift"
                  >
                    <option value="">Semua Shift</option>
                    {shifts.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </SmartNativeSelect>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">Karyawan</label>
                  <SmartNativeSelect
                    value={employeeId}
                    onChange={e => setEmployeeId(e.target.value)}
                    className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                    data-testid="filter-employee"
                  >
                    <option value="">Semua Karyawan</option>
                    {employees.map(emp => (
                      <option key={emp.id} value={emp.id}>{`${emp.employee_code} - ${emp.name}`}</option>
                    ))}
                  </SmartNativeSelect>
                </div>
              </>
            )}
            {activeTab === 'payroll' && (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Periode Payroll</label>
                <SmartNativeSelect
                  value={periodCode}
                  onChange={e => setPeriodCode(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--glass-border)] bg-[var(--input-surface)] text-sm text-foreground"
                  data-testid="filter-period"
                >
                  <option value="">Latest</option>
                  {payrollRuns.map(pr => (
                    <option key={pr.id} value={pr.period_code}>{pr.period_code}</option>
                  ))}
                </SmartNativeSelect>
              </div>
            )}
          </div>
        </GlassCard>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-[var(--glass-border)]">
        <button
          onClick={() => setActiveTab('attendance')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'attendance'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          data-testid="tab-attendance"
        >
          <Calendar className="w-4 h-4 inline mr-1.5" />
          Kehadiran
        </button>
        <button
          onClick={() => setActiveTab('overtime')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'overtime'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          data-testid="tab-overtime"
        >
          <Clock className="w-4 h-4 inline mr-1.5" />
          Overtime
        </button>
        <button
          onClick={() => setActiveTab('payroll')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'payroll'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          data-testid="tab-payroll"
        >
          <DollarSign className="w-4 h-4 inline mr-1.5" />
          Payroll
        </button>
        <button
          onClick={() => setActiveTab('turnover')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'turnover'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
          data-testid="tab-turnover"
        >
          <Users className="w-4 h-4 inline mr-1.5" />
          Turnover
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
        </div>
      )}

      {/* Attendance Report */}
      {!loading && activeTab === 'attendance' && attendanceData && (
        <div className="space-y-5">
          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Total Karyawan"
              value={attendanceData.aggregates.total_employees}
              icon={Users}
            />
            <StatCard
              title="Total Hadir"
              value={attendanceData.aggregates.total_hadir}
              subtitle={`${attendanceData.aggregates.avg_attendance_rate}% avg rate`}
              icon={Calendar}
            />
            <StatCard
              title="Total Izin/Cuti"
              value={attendanceData.aggregates.total_izin + attendanceData.aggregates.total_cuti + attendanceData.aggregates.total_sakit}
              subtitle={`Izin: ${attendanceData.aggregates.total_izin}, Cuti: ${attendanceData.aggregates.total_cuti}, Sakit: ${attendanceData.aggregates.total_sakit}`}
              icon={FileSpreadsheet}
            />
            <StatCard
              title="Alpha"
              value={attendanceData.aggregates.total_alfa}
              subtitle={`Terlambat: ${attendanceData.aggregates.total_terlambat}`}
              icon={TrendingDown}
            />
          </div>

          {/* Chart */}
          <GlassCard className="p-6">
            <h3 className="text-lg font-semibold mb-4">Trend Kehadiran Harian</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={attendanceData.chart_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" stroke="var(--muted-foreground)" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} />
                <YAxis stroke="var(--muted-foreground)" tick={{ fill: 'var(--muted-foreground)' }} />
                <Tooltip contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)' }} />
                <Legend />
                <Line type="monotone" dataKey="hadir" stroke="#10b981" name="Hadir" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="izin" stroke="#f59e0b" name="Izin" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="sakit" stroke="#3b82f6" name="Sakit" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="cuti" stroke="#8b5cf6" name="Cuti" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="alfa" stroke="#ef4444" name="Alpha" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </GlassCard>

          {/* Detail Table */}
          <GlassCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-3 pl-4 font-semibold">Karyawan</th>
                    <th className="pb-3 font-semibold">Department</th>
                    <th className="pb-3 font-semibold text-right">Hadir</th>
                    <th className="pb-3 font-semibold text-right">Izin</th>
                    <th className="pb-3 font-semibold text-right">Sakit</th>
                    <th className="pb-3 font-semibold text-right">Cuti</th>
                    <th className="pb-3 font-semibold text-right">Alpha</th>
                    <th className="pb-3 pr-4 font-semibold text-right">Rate %</th>
                  </tr>
                </thead>
                <tbody className="text-foreground">
                  {attendanceData.summary.map((emp, idx) => (
                    <tr key={emp.employee_id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                      <td className="py-3 pl-4">
                        <div className="font-medium">{emp.employee_name}</div>
                        <div className="text-xs text-muted-foreground">{emp.employee_code}</div>
                      </td>
                      <td className="py-3 text-xs">{emp.department_name || '-'}</td>
                      <td className="py-3 text-right font-mono">{emp.hadir}</td>
                      <td className="py-3 text-right font-mono">{emp.izin}</td>
                      <td className="py-3 text-right font-mono">{emp.sakit}</td>
                      <td className="py-3 text-right font-mono">{emp.cuti}</td>
                      <td className="py-3 text-right font-mono">{emp.alpha}</td>
                      <td className="py-3 pr-4 text-right font-semibold">
                        <span className={emp.attendance_rate >= 90 ? 'text-emerald-400' : emp.attendance_rate >= 80 ? 'text-amber-400' : 'text-red-400'}>
                          {emp.attendance_rate}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Overtime Report */}
      {!loading && activeTab === 'overtime' && overtimeData && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StatCard
              title="Total Karyawan OT"
              value={overtimeData.aggregates.total_employees_with_ot}
              icon={Users}
            />
            <StatCard
              title="Total OT Hours"
              value={`${overtimeData.aggregates.total_ot_hours} jam`}
              icon={Clock}
            />
            <StatCard
              title="Avg OT per Employee"
              value={`${overtimeData.aggregates.avg_ot_per_emp} jam`}
              icon={TrendingUp}
            />
          </div>

          <GlassCard className="p-6">
            <h3 className="text-lg font-semibold mb-4">Trend Overtime Harian</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={overtimeData.chart_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" stroke="var(--muted-foreground)" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} />
                <YAxis stroke="var(--muted-foreground)" tick={{ fill: 'var(--muted-foreground)' }} label={{ value: 'Hours', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)' }} />
                <Tooltip contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)' }} />
                <Bar dataKey="ot_hours" fill="#3b82f6" name="OT Hours" />
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>

          <GlassCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-3 pl-4 font-semibold">Karyawan</th>
                    <th className="pb-3 font-semibold">Department</th>
                    <th className="pb-3 font-semibold text-right">Total OT (jam)</th>
                    <th className="pb-3 font-semibold text-right">OT Days</th>
                    <th className="pb-3 pr-4 font-semibold text-right">Avg OT/Day</th>
                  </tr>
                </thead>
                <tbody className="text-foreground">
                  {overtimeData.summary.map((emp, idx) => (
                    <tr key={emp.employee_id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                      <td className="py-3 pl-4">
                        <div className="font-medium">{emp.employee_name}</div>
                        <div className="text-xs text-muted-foreground">{emp.employee_code}</div>
                      </td>
                      <td className="py-3 text-xs">{emp.department_name || '-'}</td>
                      <td className="py-3 text-right font-mono font-semibold">{emp.total_ot_hours}</td>
                      <td className="py-3 text-right font-mono">{emp.ot_days}</td>
                      <td className="py-3 pr-4 text-right font-mono">{emp.avg_ot_per_day}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Payroll Report */}
      {!loading && activeTab === 'payroll' && payrollData && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard
              title="Total Karyawan"
              value={payrollData.aggregates.total_employees}
              icon={Users}
            />
            <StatCard
              title="Total Kotor"
              value={`Rp ${(payrollData.aggregates.total_gross / 1000000).toFixed(1)}M`}
              subtitle={`Rp ${payrollData.aggregates.total_gross.toLocaleString('id-ID')}`}
              icon={DollarSign}
            />
            <StatCard
              title="Total Potongan"
              value={`Rp ${(payrollData.aggregates.total_deductions / 1000000).toFixed(1)}M`}
              icon={TrendingDown}
            />
            <StatCard
              title="Total Bersih"
              value={`Rp ${(payrollData.aggregates.total_net / 1000000).toFixed(1)}M`}
              subtitle={`Avg: Rp ${(payrollData.aggregates.avg_net / 1000).toFixed(0)}K`}
              icon={DollarSign}
            />
          </div>

          <GlassCard className="p-6">
            <h3 className="text-lg font-semibold mb-4">Breakdown Salary Components</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={[
                    { name: 'Pendapatan Kotor', value: payrollData.chart_data.gross_salary },
                    { name: 'Potongan', value: payrollData.chart_data.deductions },
                  ]}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {[0, 1].map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)' }} formatter={(value) => `Rp ${value.toLocaleString('id-ID')}`} />
              </PieChart>
            </ResponsiveContainer>
          </GlassCard>

          <GlassCard>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--glass-border)]">
                  <tr className="text-left text-muted-foreground">
                    <th className="pb-3 pl-4 font-semibold">Karyawan</th>
                    <th className="pb-3 font-semibold">Department</th>
                    <th className="pb-3 font-semibold text-right">Kotor</th>
                    <th className="pb-3 font-semibold text-right">Potongan</th>
                    <th className="pb-3 font-semibold text-right">Bersih</th>
                    <th className="pb-3 pr-4 font-semibold text-right">Att. Days</th>
                  </tr>
                </thead>
                <tbody className="text-foreground">
                  {payrollData.summary.map((emp, idx) => (
                    <tr key={emp.employee_id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                      <td className="py-3 pl-4">
                        <div className="font-medium">{emp.employee_name}</div>
                        <div className="text-xs text-muted-foreground">{emp.employee_code}</div>
                      </td>
                      <td className="py-3 text-xs">{emp.department_name || '-'}</td>
                      <td className="py-3 text-right font-mono">Rp {emp.gross_salary.toLocaleString('id-ID')}</td>
                      <td className="py-3 text-right font-mono text-red-400">Rp {emp.total_deductions.toLocaleString('id-ID')}</td>
                      <td className="py-3 text-right font-mono font-semibold text-emerald-400">Rp {emp.net_salary.toLocaleString('id-ID')}</td>
                      <td className="py-3 pr-4 text-right font-mono">{emp.attendance_days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Turnover Report */}
      {!loading && activeTab === 'turnover' && turnoverData && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard
              title="New Hires"
              value={turnoverData.aggregates.new_hires_count}
              icon={Users}
              trend="up"
              trendValue="New employees"
            />
            <StatCard
              title="Resignations"
              value={turnoverData.aggregates.resignations_count}
              icon={Users}
              trend="down"
              trendValue="Left"
            />
            <StatCard
              title="Active Employees"
              value={turnoverData.aggregates.active_employees}
              icon={Users}
            />
            <StatCard
              title="Turnover Rate"
              value={`${turnoverData.aggregates.turnover_rate}%`}
              icon={TrendingUp}
            />
          </div>

          <GlassCard className="p-6">
            <h3 className="text-lg font-semibold mb-4">Trend Hires & Resignations (Monthly)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={turnoverData.chart_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="month" stroke="var(--muted-foreground)" tick={{ fill: 'var(--muted-foreground)' }} />
                <YAxis stroke="var(--muted-foreground)" tick={{ fill: 'var(--muted-foreground)' }} />
                <Tooltip contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)' }} />
                <Legend />
                <Bar dataKey="hires" fill="#10b981" name="New Hires" />
                <Bar dataKey="resignations" fill="#ef4444" name="Resignations" />
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <GlassCard>
              <div className="p-4 border-b border-[var(--glass-border)]">
                <h3 className="font-semibold">New Hires ({turnoverData.new_hires.length})</h3>
              </div>
              <div className="overflow-x-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr className="text-left text-muted-foreground">
                      <th className="py-2 pl-4 font-semibold">Code</th>
                      <th className="py-2 font-semibold">Name</th>
                      <th className="py-2 pr-4 font-semibold">Join Date</th>
                    </tr>
                  </thead>
                  <tbody className="text-foreground">
                    {turnoverData.new_hires.map((emp, idx) => (
                      <tr key={emp.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                        <td className="py-2 pl-4 font-mono text-xs">{emp.employee_code}</td>
                        <td className="py-2 text-xs">{emp.name}</td>
                        <td className="py-2 pr-4 text-xs">{new Date(emp.join_date).toLocaleDateString('id-ID')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>

            <GlassCard>
              <div className="p-4 border-b border-[var(--glass-border)]">
                <h3 className="font-semibold">Resignations ({turnoverData.resignations.length})</h3>
              </div>
              <div className="overflow-x-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="border-b border-[var(--glass-border)]">
                    <tr className="text-left text-muted-foreground">
                      <th className="py-2 pl-4 font-semibold">Code</th>
                      <th className="py-2 font-semibold">Name</th>
                      <th className="py-2 pr-4 font-semibold">Resign Date</th>
                    </tr>
                  </thead>
                  <tbody className="text-foreground">
                    {turnoverData.resignations.map((emp, idx) => (
                      <tr key={emp.id} className={`border-b border-[var(--glass-border)] ${idx % 2 === 0 ? 'bg-[var(--glass-bg)]/30' : ''}`}>
                        <td className="py-2 pl-4 font-mono text-xs">{emp.employee_code}</td>
                        <td className="py-2 text-xs">{emp.name}</td>
                        <td className="py-2 pr-4 text-xs">{new Date(emp.resign_date).toLocaleDateString('id-ID')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </div>
        </div>
      )}
    </div>
  );
}
