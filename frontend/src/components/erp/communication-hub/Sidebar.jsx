/**
 * Sidebar — left navigation showing channels + DMs + archived channels.
 *
 * Owns its own UI state (collapsed sections, archived-list visibility).
 * Communicates with parent via callbacks for selection / archive / create.
 */
import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import {
  Hash, Plus, MessageSquare, ChevronDown, ChevronRight, RefreshCw,
  Archive, ArchiveRestore, MoreHorizontal,
} from 'lucide-react';

import { initials, avatarColor } from './utils';

export default function Sidebar({
  channels,
  archivedChannels,
  conversations,
  onlineUsers,
  activeView,
  currentUserId,
  isAdmin,
  wsConnected,
  user,
  onSelectChannel,
  onSelectDM,
  onShowCreateChannel,
  onShowNewDM,
  onRefresh,
  onArchiveChannel,
  onUnarchiveChannel,
  onShowArchivedRequested,
}) {
  const [channelsExpanded, setChannelsExpanded] = useState(true);
  const [dmsExpanded, setDmsExpanded] = useState(true);
  const [showArchived, setShowArchived] = useState(false);

  return (
    <aside className="w-72 border-r bg-[hsl(var(--card))] flex flex-col shrink-0">
      {/* Sidebar header */}
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-primary" />
          <span className="font-semibold text-sm">Communication Hub</span>
        </div>
        <div className="flex items-center gap-1">
          <div
            className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-red-500'}`}
            title={wsConnected ? 'Terhubung' : 'Terputus'}
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onRefresh}>
                <RefreshCw size={12} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Perbarui</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {/* Channels section */}
        <div className="px-2 py-2">
          <button
            className="flex items-center gap-1 w-full px-2 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
            onClick={() => setChannelsExpanded((p) => !p)}
          >
            {channelsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Channels
            <span className="ml-auto">
              <Badge variant="secondary" className="text-[10px] px-1.5 h-4">{channels.length}</Badge>
            </span>
          </button>
          {channelsExpanded && (
            <div className="mt-1 space-y-0.5">
              {channels.map((ch) => {
                const unread = ch.unread_count || 0;
                const active = activeView?.id === ch.id && activeView?.type === 'channel';
                const canArchive = isAdmin || ch.created_by === currentUserId;
                return (
                  <div key={ch.id} className="relative group/ch">
                    <button
                      className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                        active ? 'bg-primary/15 text-primary font-medium' : 'hover:bg-muted/60 text-foreground'
                      }`}
                      onClick={() => onSelectChannel(ch)}
                      data-testid={`channel-item-${ch.id}`}
                    >
                      <Hash size={14} className="shrink-0 text-muted-foreground" />
                      <span className="truncate flex-1 text-left">{ch.name}</span>
                      {unread > 0 && (
                        <Badge className="ml-auto text-[10px] px-1.5 h-4 bg-primary text-primary-foreground">
                          {unread}
                        </Badge>
                      )}
                    </button>
                    {canArchive && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground opacity-0 group-hover/ch:opacity-100 transition-opacity p-0.5 rounded">
                            <MoreHorizontal size={12} />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem
                            onClick={() => onArchiveChannel(ch.id)}
                            className="text-amber-600 focus:text-amber-600"
                            data-testid={`archive-channel-${ch.id}`}
                          >
                            <Archive size={12} className="mr-2" /> Arsipkan Channel
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                );
              })}
              <button
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                onClick={onShowCreateChannel}
                data-testid="create-channel-btn"
              >
                <Plus size={14} />
                <span>Buat Channel</span>
              </button>

              {/* Archived Channels */}
              <button
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                onClick={() => {
                  setShowArchived((p) => !p);
                  if (!showArchived) onShowArchivedRequested?.();
                }}
                data-testid="archived-channels-toggle"
              >
                {showArchived ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Archive size={12} className="text-muted-foreground" />
                <span>Channel Diarsipkan ({archivedChannels.length})</span>
              </button>
              {showArchived && archivedChannels.map((ch) => (
                <div key={ch.id} className="relative group/arch">
                  <button
                    className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:bg-muted/40 transition-colors"
                    onClick={() => onSelectChannel(ch)}
                  >
                    <Hash size={14} className="shrink-0" />
                    <span className="truncate flex-1 text-left line-through">{ch.name}</span>
                    <Archive size={10} className="shrink-0" />
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground opacity-0 group-hover/arch:opacity-100 transition-opacity p-0.5 rounded">
                        <MoreHorizontal size={12} />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem onClick={() => onUnarchiveChannel(ch.id)} data-testid={`unarchive-channel-${ch.id}`}>
                        <ArchiveRestore size={12} className="mr-2" /> Pulihkan Channel
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator className="mx-2" />

        {/* DMs */}
        <div className="px-2 py-2">
          <button
            className="flex items-center gap-1 w-full px-2 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
            onClick={() => setDmsExpanded((p) => !p)}
          >
            {dmsExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Pesan Langsung
            <span className="ml-auto">
              <Badge variant="secondary" className="text-[10px] px-1.5 h-4">{conversations.length}</Badge>
            </span>
          </button>
          {dmsExpanded && (
            <div className="mt-1 space-y-0.5">
              {conversations.map((conv) => {
                const other = conv.other_user || {};
                const unread = conv.unread_count || 0;
                const isOnline = conv.is_online || onlineUsers.has(other.id);
                const active = activeView?.id === conv.id && activeView?.type === 'dm';
                return (
                  <button
                    key={conv.id}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                      active ? 'bg-primary/15 text-primary font-medium' : 'hover:bg-muted/60 text-foreground'
                    }`}
                    onClick={() => onSelectDM(conv)}
                    data-testid={`dm-item-${conv.id}`}
                  >
                    <div className="relative shrink-0">
                      <div className={`w-6 h-6 rounded-full ${avatarColor(other.id)} flex items-center justify-center text-[10px] font-bold text-foreground`}>
                        {initials(other.name)}
                      </div>
                      <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-card ${
                        isOnline ? 'bg-emerald-500' : 'bg-muted-foreground/40'
                      }`} />
                    </div>
                    <span className="truncate flex-1 text-left text-sm">{other.name}</span>
                    {unread > 0 && (
                      <Badge className="ml-auto text-[10px] px-1.5 h-4 bg-primary text-primary-foreground">
                        {unread}
                      </Badge>
                    )}
                  </button>
                );
              })}
              <button
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                onClick={onShowNewDM}
                data-testid="new-dm-btn"
              >
                <Plus size={14} />
                <span>Pesan Baru</span>
              </button>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Current user */}
      <div className="px-3 py-2 border-t flex items-center gap-2">
        <div className="relative">
          <div className={`w-7 h-7 rounded-full ${avatarColor(currentUserId)} flex items-center justify-center text-[10px] font-bold text-foreground`}>
            {initials(user?.name)}
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-card bg-emerald-500" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium truncate">{user?.name}</p>
          <p className="text-[10px] text-muted-foreground">Online</p>
        </div>
      </div>
    </aside>
  );
}
