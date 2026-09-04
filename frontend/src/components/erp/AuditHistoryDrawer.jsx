/**
 * AuditHistoryDrawer — Phase 12.3
 *
 * Props:
 *   - open, onClose
 *   - token
 *   - entityType: 'rahaza_order' | 'rahaza_work_order' | ...
 *   - entityId: UUID
 *   - entityLabel: string untuk header drawer (misal "Order ORD-001")
 *
 * Menampilkan timeline audit dengan diff per field.
 */
import { useEffect, useState } from 'react';
import { X, Clock, User as UserIcon, Plus, Pencil, Trash2, ArrowRightLeft, CheckCircle2 } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const ACTION_ICON = {
  create:        Plus,
  update:        Pencil,
  delete:        Trash2,
  status_change: ArrowRightLeft,
  confirm:       CheckCircle2,
};
const ACTION_COLOR = {
  create:        'text-[hsl(var(--success))]',
  update:        'text-[hsl(var(--info,195_82%_55%))]',
  delete:        'text-[hsl(var(--destructive))]',
  status_change: 'text-[hsl(var(--warning))]',
  confirm:       'text-[hsl(var(--primary))]',
};
const ACTION_LABEL = {
  create:        'Dibuat',
  update:        'Diubah',
  delete:        'Dihapus',
  status_change: 'Ubah status',
  confirm:       'Dikonfirmasi',
};

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
}
function fmtValue(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return String(v);
}

export function AuditHistoryDrawer({ open, onClose, token, entityType, entityId, entityLabel }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !entityType || !entityId || !token) return;
    let active = true;
    setLoading(true);
    fetch(`${BACKEND_URL}/api/audit-logs?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}&limit=100`,
      { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => { if (active) setItems(d.items || []); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, entityType, entityId, token]);

  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] pointer-events-auto animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className="fixed top-0 right-0 bottom-0 w-full max-w-[480px] bg-[var(--popover-surface)] backdrop-blur-[var(--glass-blur-strong)] border-l border-[var(--glass-border)] shadow-[var(--shadow-soft)] z-[70] pointer-events-auto flex flex-col animate-in slide-in-from-right duration-200"
        role="dialog"
        aria-label="Riwayat Perubahan"
        data-testid="audit-drawer"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--glass-border)] shrink-0">
          <div>
            <h2 className="text-base font-semibold text-foreground">Riwayat Perubahan</h2>
            {entityLabel && <p className="text-[11px] text-foreground/50 mt-0.5">{entityLabel}</p>}
          </div>
          <button
            onClick={onClose}
            className="h-9 w-9 rounded-full text-foreground/60 hover:text-foreground hover:bg-[var(--nav-pill-active)] flex items-center justify-center"
            aria-label="Tutup"
            data-testid="audit-drawer-close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[hsl(var(--primary))]" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-20 text-xs text-foreground/50">
              <Clock className="w-8 h-8 mx-auto mb-2 text-foreground/20" strokeWidth={1.5} />
              <p>Belum ada riwayat tercatat</p>
            </div>
          ) : (
            <div className="relative">
              {/* Timeline vertical line */}
              <div className="absolute left-[11px] top-2 bottom-2 w-px bg-[var(--glass-border)]" aria-hidden="true" />
              <ol className="space-y-5">
                {items.map((log) => {
                  const Icon = ACTION_ICON[log.action] || Pencil;
                  const color = ACTION_COLOR[log.action] || 'text-foreground/60';
                  const label = ACTION_LABEL[log.action] || log.action;
                  const diffEntries = log.diff ? Object.entries(log.diff) : [];
                  return (
                    <li key={log.id} className="relative pl-8">
                      <div className={`absolute left-0 top-0 w-[22px] h-[22px] rounded-full border-2 border-[var(--glass-border)] bg-[var(--card-surface)] flex items-center justify-center ${color}`}>
                        <Icon className="w-3 h-3" strokeWidth={2} />
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className={`text-xs font-semibold ${color}`}>{label}</span>
                          <span className="text-[10px] text-foreground/50">{fmtTime(log.timestamp)}</span>
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-foreground/70">
                          <UserIcon className="w-3 h-3 shrink-0" />
                          <span className="truncate">{log.user_name || '—'}</span>
                          {log.user_role && <span className="text-foreground/40">· {log.user_role}</span>}
                        </div>
                        {diffEntries.length > 0 && (
                          <div className="mt-2 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2 text-[11px] space-y-1.5">
                            {diffEntries.slice(0, 8).map(([field, { before, after }]) => (
                              <div key={field} className="flex items-start gap-2">
                                <span className="font-mono text-[10px] text-foreground/50 shrink-0 mt-0.5">{field}</span>
                                <div className="flex-1 min-w-0">
                                  <span className="text-[hsl(var(--destructive))] line-through">{fmtValue(before)}</span>
                                  <span className="mx-1 text-foreground/40">→</span>
                                  <span className="text-[hsl(var(--success))]">{fmtValue(after)}</span>
                                </div>
                              </div>
                            ))}
                            {diffEntries.length > 8 && (
                              <p className="text-[10px] text-foreground/50">+ {diffEntries.length - 8} field lagi</p>
                            )}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
