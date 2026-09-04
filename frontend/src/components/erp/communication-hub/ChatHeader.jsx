/**
 * ChatHeader — active channel/DM header with sidebar-toggle + pinned badge + WS status.
 */
import { Badge } from '@/components/ui/badge';
import {
  Hash, MessageSquare, ChevronDown, ChevronRight, WifiOff, Pin,
} from 'lucide-react';

export default function ChatHeader({
  activeView,
  isEmbedded,
  sidebarCollapsed,
  onToggleSidebar,
  pinnedCount,
  showPinned,
  onTogglePinned,
  wsConnected,
}) {
  if (!activeView) return null;

  return (
    <div className="px-4 py-3 border-b bg-[hsl(var(--card))] flex items-center gap-3 shrink-0">
      {!isEmbedded && (
        <button
          className="text-muted-foreground hover:text-foreground"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
        >
          {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
        </button>
      )}
      {activeView.type === 'channel' ? (
        <Hash size={16} className="text-muted-foreground" />
      ) : (
        <MessageSquare size={16} className="text-muted-foreground" />
      )}
      <div className="flex-1 min-w-0">
        <h3 className="font-semibold text-sm">{activeView.name}</h3>
        {activeView.description && (
          <p className="text-xs text-muted-foreground truncate">{activeView.description}</p>
        )}
      </div>
      {activeView.type === 'channel' && pinnedCount > 0 && (
        <button
          className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border transition-colors ${
            showPinned
              ? 'bg-amber-100 dark:bg-amber-500/10 border-amber-500/40 text-amber-600'
              : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
          }`}
          onClick={onTogglePinned}
          data-testid="pinned-messages-btn"
          title="Pesan di-pin"
        >
          <Pin size={12} />
          <span>{pinnedCount} pin</span>
        </button>
      )}
      {!wsConnected && (
        <Badge variant="destructive" className="text-[10px] flex items-center gap-1">
          <WifiOff size={10} /> Terputus
        </Badge>
      )}
    </div>
  );
}
