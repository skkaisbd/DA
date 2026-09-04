/**
 * RahazaAttendanceApprovalModule — HR Approval Queue untuk Absen Otomatis
 * 
 * Menampilkan daftar absen yang perlu persetujuan HR:
 * - Out-of-range (di luar zona kantor)
 * - Face mismatch (AI tidak berhasil verifikasi wajah)
 * - Pending approval lainnya
 * 
 * HR dapat: Approve / Reject dengan catatan
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function RahazaAttendanceApprovalModule({ token }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10);
  });
  const [toDate, setToDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: statusFilter });
      if (fromDate) params.set('from_date', fromDate);
      if (toDate) params.set('to_date', toDate);
      const res = await axios.get(`${BACKEND}/api/rahaza/attendance/approvals?${params}`, { headers });
      setRecords(res.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, fromDate, toDate, headers]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  const handleApprove = async (rec) => {
    setApprovalLoading(true);
    try {
      await axios.post(`${BACKEND}/api/rahaza/attendance/approvals/${rec.id}/approve`, { notes: approvalNotes }, { headers });
      setMsg({ type: 'success', text: 'Absen disetujui.' });
      setSelectedRecord(null);
      setApprovalNotes('');
      await loadRecords();
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || 'Gagal menyetujui' });
    } finally { setApprovalLoading(false); }
  };

  const handleReject = async (rec) => {
    if (!approvalNotes.trim()) { setMsg({ type: 'error', text: 'Catatan wajib diisi untuk penolakan.' }); return; }
    setApprovalLoading(true);
    try {
      await axios.post(`${BACKEND}/api/rahaza/attendance/approvals/${rec.id}/reject`, { notes: approvalNotes }, { headers });
      setMsg({ type: 'success', text: 'Absen ditolak.' });
      setSelectedRecord(null);
      setApprovalNotes('');
      await loadRecords();
    } catch (e) {
      setMsg({ type: 'error', text: e.response?.data?.detail || 'Gagal menolak' });
    } finally { setApprovalLoading(false); }
  };

  const fmtTime = (ts) => { try { return new Date(ts).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }); } catch { return '-'; } };
  const fmtDate = (d) => { try { return new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }); } catch { return d; } };

  const statusColors = {
    pending: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
    approved: 'bg-green-100 text-green-700 border border-green-200',
    rejected: 'bg-red-100 text-red-700 border border-red-200',
    auto_approved: 'bg-blue-100 text-blue-700 border border-blue-200',
  };

  const geoColors = {
    in_range: 'text-green-600',
    out_of_range: 'text-red-600',
    not_verified: 'text-muted-foreground',
  };

  const methodLabel = {
    selfie_geo_ai: '📸 Selfie+AI',
    webauthn: '🖐️ Biometrik',
    device_zkteco: '🔌 Device',
    manual: '📝 Manual',
  };

  const pendingCount = records.filter(r => r.approval_status === 'pending').length;
  const { page, setPage, totalPages, total, paged } = useClientPagination(records, 10);

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <span>PORTAL SDM</span><span>›</span><span>KEHADIRAN</span>
          </div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <span>✅</span> Approval Absen Otomatis
            {pendingCount > 0 && <span className="bg-red-500 text-foreground text-xs px-2 py-0.5 rounded-full">{pendingCount}</span>}
          </h2>
          <p className="text-muted-foreground text-sm mt-1">Review dan setujui/tolak absen yang flagged (luar zona, mismatch wajah, dll)</p>
        </div>
      </div>

      {/* Message */}
      {msg && (
        <div className={`rounded-lg px-4 py-3 text-sm ${msg.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {msg.text}
          <button onClick={() => setMsg(null)} className="ml-2 opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Filters */}
      <div className="bg-card border rounded-xl p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Status</label>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="w-full border rounded-lg px-2.5 py-2 text-sm bg-background"
            >
              <option value="pending">Menunggu Approval</option>
              <option value="approved">Disetujui</option>
              <option value="rejected">Ditolak</option>
              <option value="auto_approved">Auto Approved</option>
              <option value="all">Semua</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Dari Tanggal</label>
            <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
              className="w-full border rounded-lg px-2.5 py-2 text-sm bg-background" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Sampai Tanggal</label>
            <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
              className="w-full border rounded-lg px-2.5 py-2 text-sm bg-background" />
          </div>
          <div className="flex items-end">
            <button onClick={loadRecords} className="w-full bg-primary text-primary-foreground rounded-lg px-3 py-2 text-sm hover:bg-primary/90 transition-colors">
              🔄 Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-card border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <div className="text-4xl mb-3">✅</div>
            <p className="font-medium">Tidak ada data untuk filter ini</p>
            <p className="text-sm mt-1">{statusFilter === 'pending' ? 'Semua absen sudah disetujui/ditolak' : 'Belum ada absen dalam periode ini'}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b">
                <tr className="text-left">
                  <th className="px-4 py-3 text-muted-foreground font-medium">Karyawan</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Tanggal</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Masuk / Pulang</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Metode</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Geo</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Wajah</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Status</th>
                  <th className="px-4 py-3 text-muted-foreground font-medium">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(rec => (
                  <tr key={rec.id} className="border-b hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium">{rec.employee_name || '-'}</div>
                      <div className="text-xs text-muted-foreground">{rec.employee_code} · {rec.department}</div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{fmtDate(rec.date)}</td>
                    <td className="px-4 py-3">
                      <div className="text-green-600">{fmtTime(rec.clock_in)}</div>
                      <div className="text-orange-500">{rec.clock_out ? fmtTime(rec.clock_out) : '-'}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs">{methodLabel[rec.attendance_method] || rec.attendance_method || 'manual'}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-medium ${geoColors[rec.geo_status] || 'text-muted-foreground'}`}>
                        {rec.geo_status === 'in_range' ? '📍 Dalam' : rec.geo_status === 'out_of_range' ? `⚠️ Luar (${rec.geo_distance_m}m)` : '–'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {rec.face_match_status === 'checked' ? (
                        <span className={`text-xs ${rec.face_match_score >= 0.65 ? 'text-green-600' : 'text-red-700 dark:text-red-500'}`}>
                          {rec.face_match_score >= 0.65 ? '✓' : '✗'} {Math.round((rec.face_match_score || 0) * 100)}%
                        </span>
                      ) : rec.face_match_status === 'biometric_verified' ? (
                        <span className="text-xs text-blue-600">🖐️ Biometrik</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">–</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColors[rec.approval_status] || 'bg-muted text-muted-foreground'}`}>
                        {rec.approval_status === 'pending' ? '⏳ Pending' :
                         rec.approval_status === 'approved' ? '✓ Disetujui' :
                         rec.approval_status === 'rejected' ? '✗ Ditolak' :
                         rec.approval_status === 'auto_approved' ? '🤖 Auto' : rec.approval_status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {rec.approval_status === 'pending' && (
                        <button
                          onClick={() => { setSelectedRecord(rec); setApprovalNotes(''); setMsg(null); }}
                          className="text-xs bg-primary/10 hover:bg-primary/20 text-primary px-2.5 py-1 rounded-lg transition-colors"
                        >
                          Review
                        </button>
                      )}
                      {rec.approval_notes && rec.approval_status !== 'pending' && (
                        <span className="text-xs text-muted-foreground" title={rec.approval_notes}>📝 Ada catatan</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-4" />
      </div>

      {/* Approval Dialog */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4">
          <div className="bg-card border rounded-2xl w-full max-w-md shadow-xl space-y-4 p-6">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-lg">Review Absen</h3>
              <button onClick={() => setSelectedRecord(null)} className="text-muted-foreground hover:text-foreground">✕</button>
            </div>

            {/* Details */}
            <div className="bg-muted/30 rounded-xl p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Karyawan</span>
                <span className="font-medium">{selectedRecord.employee_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Tanggal</span>
                <span>{fmtDate(selectedRecord.date)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Jam Masuk</span>
                <span className="text-green-600">{fmtTime(selectedRecord.clock_in)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Geolokasi</span>
                <span className={selectedRecord.geo_status === 'in_range' ? 'text-green-600' : 'text-orange-500'}>
                  {selectedRecord.geo_status === 'in_range' ? '✓ Dalam zona' :
                   selectedRecord.geo_status === 'out_of_range' ? `✗ Luar zona (${selectedRecord.geo_distance_m || 0}m)` : 'Tidak diverifikasi'}
                </span>
              </div>
              {selectedRecord.face_match_status === 'checked' && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Verifikasi Wajah</span>
                  <span className={selectedRecord.face_match_score >= 0.65 ? 'text-green-600' : 'text-red-700 dark:text-red-500'}>
                    {selectedRecord.face_match_score >= 0.65 ? '✓ Cocok' : '✗ Tidak Cocok'} ({Math.round((selectedRecord.face_match_score || 0) * 100)}%)
                  </span>
                </div>
              )}
              {selectedRecord.face_match_reason && (
                <div className="text-xs text-muted-foreground italic">"{selectedRecord.face_match_reason}"</div>
              )}
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Catatan (opsional untuk approve, wajib untuk tolak)</label>
              <textarea
                value={approvalNotes}
                onChange={e => setApprovalNotes(e.target.value)}
                placeholder="Misal: Dimaklumi karena karyawan sedang WFH / tugas luar"
                rows={3}
                className="w-full border rounded-lg px-3 py-2 text-sm bg-background resize-none"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => handleReject(selectedRecord)}
                disabled={approvalLoading}
                className="flex-1 bg-red-100 dark:bg-red-500/10 hover:bg-red-100 dark:bg-red-500/20 text-red-600 border border-red-200 font-semibold py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50"
              >
                ✗ Tolak
              </button>
              <button
                onClick={() => handleApprove(selectedRecord)}
                disabled={approvalLoading}
                className="flex-1 bg-green-600 hover:bg-green-500 text-foreground font-semibold py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50"
              >
                {approvalLoading ? '...' : '✓ Setujui'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
