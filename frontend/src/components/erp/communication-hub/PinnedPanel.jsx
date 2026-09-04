/**
 * PinnedPanel — collapsible panel showing pinned messages in the active channel.
 */
import { Pin, X } from 'lucide-react';

export default function PinnedPanel({ pinnedMessages, isAdmin, onUnpin, onClose }) {
  if (!pinnedMessages || pinnedMessages.length === 0) return null;

  return (
    <div
      className="border-b bg-amber-100 dark:bg-amber-500/5 px-4 py-2 space-y-1.5 max-h-40 overflow-y-auto"
      data-testid="pinned-messages-panel"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-amber-600 flex items-center gap-1.5">
          <Pin size={12} /> {pinnedMessages.length} Pesan Di-Pin
        </span>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
      </div>
      {pinnedMessages.map((pm) => (
        <div key={pm.id} className="flex items-start gap-2 text-xs bg-card rounded-lg px-3 py-2 border">
          <Pin size={11} className="text-amber-500 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <span className="font-medium text-foreground">{pm.sender_name}</span>
            <span className="text-muted-foreground ml-2 truncate block">
              {pm.content || '📎 Lampiran'}
            </span>
          </div>
          {isAdmin && (
            <button
              onClick={() => onUnpin(pm.id)}
              className="text-muted-foreground hover:text-destructive shrink-0"
              title="Unpin"
            >
              <X size={12} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
