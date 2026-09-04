/**
 * PRDetailDrawer — Procurement Request detail panel with approval workflow & timeline.
 * Extracted from AssetManagementPortal.jsx (Phase 3 refactor)
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';
import { ShoppingCart, Send, CheckCheck, X } from 'lucide-react';
import { toast } from 'sonner';
import { apicall, fmtCurrency, fmtDate } from '../utils';
import { StatusBadge } from '../components/StatusBadge';
import { PR_STATUS_CONFIG } from '../constants';

export function PRDetailDrawer({ pr, token, open, onClose, onRefresh, currentUser }) {
  const [loading, setLoading] = useState(false);
  const [comment, setComment] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  if (!pr) return null;

  const canApprove = ['submitted', 'dept_approved', 'finance_approved'].includes(pr.status);
  const canSubmit = pr.status === 'draft';
  const canCancel = ['draft', 'submitted'].includes(pr.status) &&
    (pr.requested_by === currentUser?.id || currentUser?.role === 'superadmin' || currentUser?.role === 'admin');

  const action = async (endpoint, body = {}) => {
    setLoading(true);
    try {
      const d = await apicall('POST', `/api/procurement/requests/${pr.id}/${endpoint}`, token, body);
      if (d.ok) { toast.success('Berhasil'); onRefresh(); onClose(); }
      else toast.error(d.detail || 'Gagal');
    } catch { toast.error('Gagal'); }
    finally { setLoading(false); }
  };

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:w-[480px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <ShoppingCart size={16} />
            <span className="truncate">{pr.title}</span>
          </SheetTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">{pr.request_number}</span>
            <StatusBadge status={pr.status} configMap={PR_STATUS_CONFIG} />
          </div>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* Info */}
          <div className="grid grid-cols-2 gap-2">
            {[
              ['Pemohon', pr.requested_by_name], ['Departemen', pr.department || '-'],
              ['Prioritas', pr.priority], ['Tipe', pr.request_type],
              ['Tgl Dibuat', fmtDate(pr.created_at)], ['Total Est.', fmtCurrency(pr.total_estimated)],
            ].map(([k, v]) => (
              <div key={k} className="bg-muted/40 rounded-lg p-2">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{k}</p>
                <p className="text-sm font-medium">{v}</p>
              </div>
            ))}
          </div>

          {pr.justification && (
            <div className="bg-muted/40 rounded-lg p-3">
              <p className="text-xs text-muted-foreground mb-1">Justifikasi</p>
              <p className="text-sm">{pr.justification}</p>
            </div>
          )}

          {/* Items */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Daftar Item</p>
            <div className="space-y-1">
              {(pr.items || []).map((item, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-3 bg-muted/40 rounded-lg">
                  <div>
                    <p className="text-sm font-medium">{item.name}</p>
                    {item.specification && <p className="text-xs text-muted-foreground">{item.specification}</p>}
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">{item.qty} {item.unit}</p>
                    <p className="text-sm font-medium">{fmtCurrency(item.total_price)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Timeline */}
          {(pr.approval_steps || []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Timeline Approval</p>
              <div className="relative pl-4 space-y-3">
                <div className="absolute left-2 top-1 bottom-1 w-px bg-border" />
                {pr.approval_steps.map((s, i) => (
                  <div key={s.id || i} className="relative pl-4">
                    <div className={`absolute left-0 top-1 w-3 h-3 rounded-full border-2 border-background ${
                      s.action === 'approved' ? 'bg-emerald-500' : s.action === 'rejected' ? 'bg-red-500' : 'bg-primary'
                    }`} />
                    <p className="text-sm font-medium">{s.actor_name} <span className="text-muted-foreground font-normal text-xs">– {s.action}</span></p>
                    {s.comment && <p className="text-xs text-muted-foreground">{s.comment}</p>}
                    <p className="text-[10px] text-muted-foreground">{s.timestamp ? new Date(s.timestamp).toLocaleString('id-ID') : ''}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <Separator />
          <div className="space-y-2">
            {canSubmit && (
              <Button className="w-full" size="sm" onClick={() => action('submit')} disabled={loading}>
                <Send size={14} className="mr-1" /> Submit untuk Approval
              </Button>
            )}
            {canApprove && !showRejectInput && (
              <div className="flex gap-2">
                <Button className="flex-1" size="sm" variant="default" onClick={() => action('approve', { comment })} disabled={loading}>
                  <CheckCheck size={14} className="mr-1" /> Approve
                </Button>
                <Button className="flex-1" size="sm" variant="destructive" onClick={() => setShowRejectInput(true)}>
                  <X size={14} className="mr-1" /> Tolak
                </Button>
              </div>
            )}
            {showRejectInput && (
              <div className="space-y-2">
                <Input placeholder="Alasan penolakan..." value={rejectReason}
                  onChange={e => setRejectReason(e.target.value)} />
                <div className="flex gap-2">
                  <Button variant="destructive" size="sm" className="flex-1"
                    onClick={() => action('reject', { reason: rejectReason })} disabled={loading}>
                    Konfirmasi Tolak
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setShowRejectInput(false)}>Batal</Button>
                </div>
              </div>
            )}
            {canCancel && (
              <Button variant="outline" size="sm" className="w-full text-red-500 hover:text-red-500"
                onClick={() => action('cancel')} disabled={loading}>
                Batalkan Request
              </Button>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
