/**
 * DisposalApprovalInbox — List disposal requests untuk Admin/Finance/Manager.
 * Section component (not a dialog) embedded in the Disposal tab.
 * Extracted from AssetManagementPortal.jsx (Phase 2 refactor)
 */
import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { apicall, fmtCurrency, fmtDate } from '../utils';

export function DisposalApprovalInbox({ token, userRole, onRefresh }) {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState('pending');
  const [reviewDialog, setReviewDialog] = useState(null); // { req, action: 'approve'|'reject' }
  const [notes, setNotes] = useState('');
  const [processing, setProcessing] = useState(false);
  const canReview = ['admin','superadmin','finance','manager'].includes(userRole);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apicall('GET', `/api/assets/disposal-requests?status=${filterStatus}`, token);
      if (Array.isArray(data)) setRequests(data);
    } catch { toast.error('Gagal memuat permintaan disposal'); }
    finally { setLoading(false); }
  }, [token, filterStatus]);

  useEffect(() => { load(); }, [load]);

  const handleReview = async () => {
    if (!reviewDialog) return;
    const { req, action } = reviewDialog;
    if (!notes.trim() && action === 'reject') { toast.error('Catatan wajib diisi saat menolak'); return; }
    setProcessing(true);
    try {
      const data = await apicall('PATCH', `/api/assets/disposal-requests/${req.id}/${action}`, token, { notes });
      if (data?.ok !== undefined) {
        toast.success(action === 'approve' ? '✅ Disposal disetujui & jurnal dibuat' : '❌ Disposal ditolak');
        setReviewDialog(null); setNotes('');
        load(); onRefresh?.();
      } else {
        toast.error(data?.detail || 'Gagal proses');
      }
    } catch { toast.error('Gagal proses'); }
    finally { setProcessing(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-sm font-semibold flex-1">Permintaan Disposal Aset</p>
        {['pending','approved','rejected','all'].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${filterStatus === s ? 'bg-primary text-primary-foreground border-primary' : 'text-muted-foreground hover:text-foreground'}`}>
            {s === 'pending' ? 'Menunggu' : s === 'approved' ? 'Disetujui' : s === 'rejected' ? 'Ditolak' : 'Semua'}
          </button>
        ))}
        <Button variant="outline" size="sm" onClick={load}><RefreshCw size={14} /></Button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-muted-foreground text-sm">Memuat...</div>
      ) : requests.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground text-sm">
          Tidak ada permintaan disposal {filterStatus !== 'all' ? `dengan status "${filterStatus === 'pending' ? 'menunggu' : filterStatus}"` : ''}
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map(req => (
            <Card key={req.id} className={`border-l-4 ${req.status === 'pending' ? 'border-l-amber-500' : req.status === 'approved' ? 'border-l-emerald-500' : 'border-l-red-500'}`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-sm truncate">{req.asset_name}</p>
                      <span className="text-xs text-muted-foreground font-mono">{req.asset_number}</span>
                      <Badge variant={req.status === 'pending' ? 'outline' : req.status === 'approved' ? 'default' : 'destructive'} className="text-[10px] shrink-0">
                        {req.status === 'pending' ? 'Menunggu' : req.status === 'approved' ? 'Disetujui' : 'Ditolak'}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 mt-2 text-xs text-muted-foreground">
                      <span>NBV: <strong className="text-foreground">{fmtCurrency(req.nbv || 0)}</strong></span>
                      <span>Nilai Jual: <strong className="text-foreground">{fmtCurrency(req.disposal_value || 0)}</strong></span>
                      <span>Tanggal: {fmtDate(req.disposal_date)}</span>
                      <span>Diminta: {fmtDate(req.requested_at)}</span>
                    </div>
                    <p className="text-xs mt-1.5 text-foreground/80">"{req.reason}"</p>
                    <p className="text-xs text-muted-foreground mt-1">Oleh: {req.requested_by_name}</p>
                    {req.review_notes && (
                      <p className="text-xs mt-1 text-muted-foreground italic">Catatan reviewer: {req.review_notes}</p>
                    )}
                  </div>
                  {canReview && req.status === 'pending' && (
                    <div className="flex gap-2 shrink-0">
                      <Button size="sm" variant="outline"
                        className="text-destructive border-destructive/30 hover:bg-destructive/10"
                        onClick={() => { setReviewDialog({ req, action: 'reject' }); setNotes(''); }}
                        data-testid={`reject-disposal-${req.id}`}>
                        Tolak
                      </Button>
                      <Button size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700 text-foreground"
                        onClick={() => { setReviewDialog({ req, action: 'approve' }); setNotes(''); }}
                        data-testid={`approve-disposal-${req.id}`}>
                        Setujui
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Review Dialog */}
      {reviewDialog && (
        <Dialog open={!!reviewDialog} onOpenChange={() => setReviewDialog(null)}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>{reviewDialog.action === 'approve' ? '✅ Setujui Disposal' : '❌ Tolak Disposal'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="bg-muted/40 rounded-lg p-3 text-xs space-y-1">
                <p className="font-medium">{reviewDialog.req.asset_name}</p>
                <p className="text-muted-foreground">NBV: {fmtCurrency(reviewDialog.req.nbv || 0)}</p>
              </div>
              {reviewDialog.action === 'approve' && (
                <div className="bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/20 rounded-lg p-2 text-xs text-amber-700">
                  ⚠️ Menyetujui akan <strong>langsung melepas aset</strong> dan membuat jurnal Finance.
                </div>
              )}
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Catatan {reviewDialog.action === 'reject' ? '(wajib)' : '(opsional)'}
                </label>
                <textarea
                  className="w-full border rounded-md px-3 py-2 text-sm mt-1 min-h-[70px] bg-background resize-none"
                  placeholder={reviewDialog.action === 'approve' ? 'Catatan persetujuan...' : 'Alasan penolakan...'}
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReviewDialog(null)}>Batal</Button>
              <Button
                onClick={handleReview}
                disabled={processing}
                className={reviewDialog.action === 'approve' ? 'bg-emerald-600 hover:bg-emerald-700 text-foreground' : 'bg-destructive hover:bg-destructive/90 text-destructive-foreground'}
              >
                {processing ? 'Memproses...' : reviewDialog.action === 'approve' ? 'Ya, Setujui' : 'Ya, Tolak'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
