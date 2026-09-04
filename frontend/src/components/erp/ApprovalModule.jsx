import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, Eye, FileText, RefreshCw, AlertCircle, ArrowRight, History } from 'lucide-react';
import Modal from './Modal';
import PaginationLite, { useClientPagination } from '@/components/ui/pagination-lite';
import { formatRupiah } from '@/lib/format';

const STATUS_COLORS = {
  Pending: 'bg-amber-100 text-amber-700 border border-amber-200',
  Approved: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
  Rejected: 'bg-red-100 text-red-700 border border-red-200',
};

const STATUS_ICONS = {
  Pending: Clock,
  Approved: CheckCircle,
  Rejected: XCircle,
};

const fmt = formatRupiah;
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';

export default function ApprovalModule({ token, userRole }) {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('Pending');
  const [searchQuery, setSearchQuery] = useState('');
  const [showDetail, setShowDetail] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState('');

  const canApprove = ['superadmin', 'admin'].includes(userRole);

  useEffect(() => {
    fetchRequests();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStatus]);

  const fetchRequests = async () => {
    setLoading(true);
    try {
      let url = '/api/invoice-edit-requests?';
      const params = [];
      if (filterStatus) params.push(`status=${filterStatus}`);
      if (searchQuery) params.push(`q=${encodeURIComponent(searchQuery)}`);
      const res = await fetch(url + params.join('&'), {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      setRequests(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Error fetching requests:', e);
      setRequests([]);
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (req) => {
    setSelectedRequest(req);
    setApprovalNotes('');
    setShowDetail(true);
  };

  const handleApprove = async () => {
    if (!selectedRequest) return;
    if (!confirm(`Approve request edit untuk invoice ${selectedRequest.invoice_number}?`)) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/api/invoice-edit-requests/${selectedRequest.id}/approve`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ approval_notes: approvalNotes })
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || data.error || data.message || 'Gagal approve request');
      } else {
        alert('Request approved! Invoice telah diupdate.');
        setShowDetail(false);
        fetchRequests();
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedRequest) return;
    if (!approvalNotes.trim()) {
      alert('Catatan/alasan reject wajib diisi');
      return;
    }
    if (!confirm(`Reject request edit untuk invoice ${selectedRequest.invoice_number}?`)) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/api/invoice-edit-requests/${selectedRequest.id}/reject`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ approval_notes: approvalNotes })
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || data.error || data.message || 'Gagal reject request');
      } else {
        alert('Request rejected');
        setShowDetail(false);
        fetchRequests();
      }
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setActionLoading(false);
    }
  };

  const compareField = (field, before, after) => {
    const beforeVal = before?.[field];
    const afterVal = after?.[field];
    if (JSON.stringify(beforeVal) === JSON.stringify(afterVal)) {
      return null; // No change
    }
    return { before: beforeVal, after: afterVal };
  };

  const renderComparison = () => {
    if (!selectedRequest) return null;
    const before = selectedRequest.before_snapshot || {};
    const after = selectedRequest.after_snapshot || {};

    const changes = [];

    // Compare discount
    const discountChange = compareField('discount', before, after);
    if (discountChange) {
      changes.push(
        <div key="discount" className="grid grid-cols-2 gap-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-xs text-red-600 font-medium mb-1">BEFORE - Diskon</p>
            <p className="font-bold text-red-700">{fmt(discountChange.before)}</p>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            <p className="text-xs text-emerald-600 font-medium mb-1">AFTER - Diskon</p>
            <p className="font-bold text-emerald-700">{fmt(discountChange.after)}</p>
          </div>
        </div>
      );
    }

    // Compare notes
    const notesChange = compareField('notes', before, after);
    if (notesChange) {
      changes.push(
        <div key="notes" className="grid grid-cols-2 gap-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-xs text-red-600 font-medium mb-1">BEFORE - Catatan</p>
            <p className="text-sm text-foreground">{notesChange.before || '-'}</p>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            <p className="text-xs text-emerald-600 font-medium mb-1">AFTER - Catatan</p>
            <p className="text-sm text-foreground">{notesChange.after || '-'}</p>
          </div>
        </div>
      );
    }

    // Compare total_amount
    const totalChange = compareField('total_amount', before, after);
    if (totalChange) {
      changes.push(
        <div key="total" className="grid grid-cols-2 gap-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-xs text-red-600 font-medium mb-1">BEFORE - Total Amount</p>
            <p className="font-bold text-red-700 text-lg">{fmt(totalChange.before)}</p>
          </div>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            <p className="text-xs text-emerald-600 font-medium mb-1">AFTER - Total Amount</p>
            <p className="font-bold text-emerald-700 text-lg">{fmt(totalChange.after)}</p>
          </div>
        </div>
      );
    }

    // Compare invoice_items
    const itemsChange = compareField('invoice_items', before, after);
    if (itemsChange) {
      changes.push(
        <div key="items" className="space-y-3">
          <h4 className="font-semibold text-foreground">Perubahan Item Invoice</h4>
          <div className="grid grid-cols-2 gap-4">
            {/* BEFORE */}
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-xs text-red-600 font-medium mb-2">BEFORE</p>
              <div className="space-y-1.5">
                {(itemsChange.before || []).map((item, idx) => (
                  <div key={idx} className="bg-[var(--card-surface)] rounded p-2 text-xs border border-red-100">
                    <p className="font-medium text-foreground">{item.product_name}</p>
                    <p className="text-muted-foreground font-mono">{item.sku} · {item.size}/{item.color}</p>
                    <div className="flex justify-between mt-1">
                      <span>Qty: <strong>{item.invoice_qty}</strong></span>
                      <span>Subtotal: <strong>{fmt(item.subtotal || 0)}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* AFTER */}
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
              <p className="text-xs text-emerald-600 font-medium mb-2">AFTER</p>
              <div className="space-y-1.5">
                {(itemsChange.after || []).map((item, idx) => (
                  <div key={idx} className="bg-[var(--card-surface)] rounded p-2 text-xs border border-emerald-100">
                    <p className="font-medium text-foreground">{item.product_name}</p>
                    <p className="text-muted-foreground font-mono">{item.sku} · {item.size}/{item.color}</p>
                    <div className="flex justify-between mt-1">
                      <span>Qty: <strong>{item.invoice_qty}</strong></span>
                      <span>Subtotal: <strong>{fmt(item.subtotal || 0)}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      );
    }

    return changes.length > 0 ? changes : <p className="text-muted-foreground text-sm text-center py-4">Tidak ada perubahan terdeteksi</p>;
  };

  const filtered = requests;

  const { page, setPage, totalPages, total, paged } = useClientPagination(filtered, 10);
  return (
    <div className="space-y-6" data-testid="approval-module">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground" data-testid="approval-module-title">Invoice Edit Approval</h1>
          <p className="text-muted-foreground text-sm mt-1">Review dan approve/reject request perubahan invoice dari admin</p>
        </div>
        <button
          onClick={fetchRequests}
          className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg text-sm hover:bg-[var(--glass-bg)]"
          data-testid="approval-refresh-button"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {/* Info */}
      <div className="bg-primary/10 border border-primary/20 rounded-xl p-4 text-sm text-primary">
        <div className="flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-semibold">Approval Workflow:</p>
            <p className="mt-1">1. Admin ERP membuat <strong>Request Edit Invoice</strong> (invoice tidak langsung berubah).</p>
            <p>2. Superadmin/Admin review request → <strong>Setujui</strong> (invoice auto-update + histori tercatat) atau <strong>Tolak</strong>.</p>
            <p>3. Semua perubahan tersimpan di <strong>Invoice Change History</strong> untuk audit trail.</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1">
          {['Pending', 'Approved', 'Rejected', ''].map(status => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-3 py-1.5 rounded-lg text-sm border ${filterStatus === status ? 'bg-teal-600 text-foreground border-teal-600' : 'border-border text-muted-foreground hover:bg-[var(--glass-bg)]'}`}
              data-testid={`filter-status-${status || 'all'}`}
            >
              {status || 'Semua'}
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <input
            type="text"
            placeholder="Cari invoice number, requester..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchRequests()}
            className="px-3 py-1.5 border border-border rounded-lg text-sm w-72"
            data-testid="approval-search-input"
          />
        </div>
      </div>

      {/* Request List */}
      {loading ? (
        <div className="text-center py-16" data-testid="approval-loading">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-muted-foreground" />
          <p className="text-muted-foreground">Memuat...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground" data-testid="approval-empty">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">Tidak ada request ditemukan</p>
        </div>
      ) : (
        <div className="bg-[var(--card-surface)] rounded-xl border border-border overflow-hidden shadow-sm" data-testid="approval-list">
          <table className="w-full text-sm">
            <thead className="bg-[var(--glass-bg)] border-b">
              <tr>
                {['Status', 'No. Invoice', 'PO Number', 'Kategori', 'Ringkasan Perubahan', 'Requested By', 'Requested At', 'Aksi'].map(h => (
                  <th key={h} className="text-left px-3 py-3 text-xs font-semibold text-muted-foreground uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paged.map(req => {
                const StatusIcon = STATUS_ICONS[req.status] || Clock;
                return (
                  <tr key={req.id} className="hover:bg-[var(--glass-bg)]" data-testid="approval-request-row">
                    <td className="px-3 py-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[req.status] || 'bg-secondary text-muted-foreground'}`}>
                        <StatusIcon className="w-3 h-3" />
                        {req.status}
                      </span>
                    </td>
                    <td className="px-3 py-3 font-bold text-primary">{req.invoice_number}</td>
                    <td className="px-3 py-3 font-mono text-xs text-muted-foreground">{req.po_number || '-'}</td>
                    <td className="px-3 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs ${req.invoice_category === 'VENDOR' ? 'bg-amber-100 text-amber-700' : 'bg-primary/15 text-primary'}`}>
                        {req.invoice_category}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-foreground max-w-xs">
                      <div className="truncate" title={req.change_summary}>{req.change_summary}</div>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">
                      <p className="font-medium">{req.requested_by_name}</p>
                      <p className="text-xs text-muted-foreground">{req.requested_by}</p>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground text-xs">{fmtDate(req.requested_at)}</td>
                    <td className="px-3 py-3">
                      <button
                        onClick={() => openDetail(req)}
                        className="flex items-center gap-1 px-3 py-1.5 bg-teal-600 text-foreground rounded-lg text-xs hover:bg-teal-700"
                        data-testid="approval-view-detail-button"
                      >
                        <Eye className="w-3.5 h-3.5" /> Detail
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <PaginationLite page={page} totalPages={totalPages} total={total} onPageChange={setPage} className="px-1" />
        </div>
      )}

      {/* Detail Modal */}
      {showDetail && selectedRequest && (
        <Modal
          title={`Request Edit: ${selectedRequest.invoice_number}`}
          onClose={() => setShowDetail(false)}
          size="xl"
        >
          <div className="space-y-5" data-testid="approval-detail-modal">
            {/* Meta Info */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-[var(--glass-bg)] rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Status</p>
                <div className="mt-1">
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[selectedRequest.status]}`}>
                    {selectedRequest.status}
                  </span>
                </div>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Requested By</p>
                <p className="font-medium text-sm mt-0.5">{selectedRequest.requested_by_name}</p>
                <p className="text-xs text-muted-foreground">{selectedRequest.requested_by}</p>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg p-3">
                <p className="text-xs text-muted-foreground">Requested At</p>
                <p className="font-medium text-sm mt-0.5">{fmtDate(selectedRequest.requested_at)}</p>
              </div>
            </div>

            {/* Change Summary */}
            <div className="bg-primary/10 border border-primary/20 rounded-lg p-3">
              <p className="text-xs text-primary font-semibold mb-1">Ringkasan Perubahan</p>
              <p className="text-sm text-primary">{selectedRequest.change_summary}</p>
            </div>

            {/* Comparison */}
            <div>
              <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                <ArrowRight className="w-5 h-5 text-teal-600" />
                Perbandingan Before & After
              </h3>
              <div className="space-y-4">
                {renderComparison()}
              </div>
            </div>

            {/* Approval Notes (if already approved/rejected) */}
            {selectedRequest.status !== 'Pending' && selectedRequest.approval_notes && (
              <div className="bg-[var(--glass-bg)] border border-border rounded-lg p-3">
                <p className="text-xs text-muted-foreground font-semibold mb-1">Catatan Approval/Reject</p>
                <p className="text-sm text-foreground">{selectedRequest.approval_notes}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Oleh: {selectedRequest.approved_by_name} pada {fmtDate(selectedRequest.approved_at)}
                </p>
              </div>
            )}

            {/* Action: Approve/Reject (only for Pending) */}
            {selectedRequest.status === 'Pending' && canApprove && (
              <div className="border-t border-border pt-4">
                <label className="block text-sm font-medium text-foreground mb-2">Catatan Approval/Reject (opsional untuk approve, wajib untuk reject)</label>
                <textarea
                  rows="3"
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm mb-3"
                  value={approvalNotes}
                  onChange={(e) => setApprovalNotes(e.target.value)}
                  placeholder="Contoh: Approved sesuai kesepakatan dengan customer..."
                  data-testid="approval-notes-textarea"
                />
                <div className="flex gap-3">
                  <button
                    onClick={handleApprove}
                    disabled={actionLoading}
                    className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 text-foreground py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
                    data-testid="approve-button"
                  >
                    <CheckCircle className="w-4 h-4" />
                    {actionLoading ? 'Processing...' : 'Approve'}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={actionLoading}
                    className="flex-1 flex items-center justify-center gap-2 bg-red-600 text-foreground py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
                    data-testid="reject-button"
                  >
                    <XCircle className="w-4 h-4" />
                    {actionLoading ? 'Processing...' : 'Reject'}
                  </button>
                </div>
              </div>
            )}

            {/* Link to Invoice */}
            <div className="border-t border-border pt-3">
              <p className="text-xs text-muted-foreground mb-2">Quick Link</p>
              <button
                onClick={() => {
                  setShowDetail(false);
                  // In a real app, navigate to invoice detail
                  alert(`Navigasi ke invoice detail: ${selectedRequest.invoice_number} (implementasi bisa ditambahkan via parent callback)`);
                }}
                className="flex items-center gap-2 px-3 py-1.5 bg-primary text-foreground rounded-lg text-xs hover:brightness-110"
                data-testid="view-invoice-link"
              >
                <FileText className="w-3.5 h-3.5" /> Lihat Invoice {selectedRequest.invoice_number}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
