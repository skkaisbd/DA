/**
 * MessageList — the scrolling message thread area.
 *
 * Handles three render states: loading, empty, normal list.
 * Also renders the typing indicator if any.
 */
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageSquare } from 'lucide-react';

import MessageItem from './MessageItem';

export default function MessageList({
  messages,
  loadingMsgs,
  currentUserId,
  isAdmin,
  token,
  activeViewType,
  onReact,
  onReply,
  onEdit,
  onDelete,
  onPin,
  onUnpin,
  onLightbox,
  onOpenThread,
  onNavigate,
  typingUser,
  messagesEndRef,
}) {
  return (
    <ScrollArea className="flex-1">
      <div className="py-4 space-y-1" data-testid="message-thread">
        {loadingMsgs ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin h-6 w-6 rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare size={32} className="mx-auto text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">Belum ada pesan. Mulai percakapan!</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageItem
              key={msg.id}
              msg={msg}
              currentUserId={currentUserId}
              isAdmin={isAdmin}
              token={token}
              onNavigate={onNavigate}
              onReact={onReact}
              onReply={onReply}
              onEdit={onEdit}
              onDelete={onDelete}
              onPin={activeViewType === 'channel' ? onPin : null}
              onUnpin={activeViewType === 'channel' ? onUnpin : null}
              onLightbox={onLightbox}
              onOpenThread={onOpenThread}
            />
          ))
        )}
        {typingUser && (
          <div className="px-4 py-1 flex items-center gap-2">
            <div className="flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <span className="text-xs text-muted-foreground">
              {typingUser.user_name} sedang mengetik...
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </ScrollArea>
  );
}
