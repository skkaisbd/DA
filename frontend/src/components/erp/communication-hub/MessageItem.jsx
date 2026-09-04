/**
 * MessageItem — single chat-message bubble (channel or DM).
 *
 * Renders:
 *   - sender avatar + name + relative timestamp + (edited) badge
 *   - reply-to preview
 *   - message content (markdown rendering or attachment list)
 *   - deep-link preview cards
 *   - hover toolbar (5 quick emoji + reply + thread + more menu with edit/delete/pin)
 *   - reaction chips
 *   - thread reply count badge
 *
 * Inline editing is supported via internal `editing` state; submitEdit calls
 * `onEdit(msgId, newContent)` provided by the parent.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  Paperclip, X, Reply, Pencil, Trash2, Check, MoreVertical, Pin, PinOff,
  MessagesSquare, ChevronRight,
} from 'lucide-react';

import LinkPreviewCard, { parseDeepLinks } from '../collaboration/shared/LinkPreview';
import { API, EMOJI_LIST, formatTime, initials, avatarColor } from './utils';
import { renderMarkdown } from './Markdown';

export default function MessageItem({
  msg, currentUserId, token, onNavigate,
  onReact, onReply, onEdit, onDelete, onPin, onUnpin,
  isAdmin, onLightbox, onOpenThread, isInThread,
}) {
  const isMine = msg.sender_id === currentUserId;
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(msg.content || '');

  const editable = isMine && (msg.message_type === 'text' || !msg.message_type) && !msg.attachments;
  const deletable = isMine || isAdmin;
  const pinnable = !msg.pinned && onPin;
  const unpinnable = msg.pinned && onUnpin;
  const isSystem = msg.sender_id === 'system' || msg.message_type === 'system_procurement';

  const submitEdit = async () => {
    const trimmed = editText.trim();
    if (!trimmed) {
      toast.error('Pesan tidak boleh kosong');
      return;
    }
    if (trimmed === (msg.content || '')) {
      setEditing(false);
      return;
    }
    const ok = await onEdit(msg.id, trimmed);
    if (ok) setEditing(false);
  };

  return (
    <div
      className={`group flex gap-3 px-4 py-1.5 hover:bg-muted/30 transition-colors rounded-lg ${
        isMine ? 'flex-row-reverse' : ''
      }`}
      data-testid="message-item"
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full ${avatarColor(msg.sender_id)} flex items-center justify-center text-xs font-bold text-foreground shrink-0 mt-1`}>
        {isSystem ? 'S' : initials(msg.sender_name)}
      </div>

      {/* Content */}
      <div className={`flex-1 min-w-0 ${isMine ? 'items-end' : 'items-start'} flex flex-col`}>
        {/* Header */}
        <div className={`flex items-baseline gap-2 mb-0.5 ${isMine ? 'flex-row-reverse' : ''}`}>
          <span className="text-xs font-semibold">
            {isMine ? 'Saya' : (isSystem ? 'System' : msg.sender_name)}
          </span>
          <span className="text-[10px] text-muted-foreground">{formatTime(msg.created_at)}</span>
          {msg.edited && <span className="text-[10px] text-muted-foreground italic">(diedit)</span>}
        </div>

        {/* Reply preview */}
        {msg.reply_to_preview && (
          <div className="text-xs text-muted-foreground bg-muted/50 px-2 py-1 rounded mb-1 border-l-2 border-primary/50 max-w-xs truncate">
            {msg.reply_to_preview}
          </div>
        )}

        {/* Bubble */}
        <div className={`relative rounded-2xl px-3 py-2 text-sm max-w-[75%] break-words ${
          isSystem
            ? 'bg-amber-100 dark:bg-amber-500/10 border border-amber-400 dark:border-amber-500/30 text-foreground'
            : isMine
              ? 'bg-[hsl(var(--primary)/0.15)] text-foreground rounded-tr-sm'
              : 'bg-muted/60 text-foreground rounded-tl-sm'
        }`}>
          {editing ? (
            <div className="space-y-2 min-w-[240px]">
              <Textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={3}
                className="text-sm"
                autoFocus
                data-testid="message-edit-input"
              />
              <div className="flex gap-2 justify-end">
                <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setEditText(msg.content || ''); }} data-testid="message-edit-cancel">
                  <X size={14} className="mr-1" /> Batal
                </Button>
                <Button size="sm" onClick={submitEdit} data-testid="message-edit-save">
                  <Check size={14} className="mr-1" /> Simpan
                </Button>
              </div>
            </div>
          ) : msg.attachments && msg.attachments.length > 0 ? (
            <div className="space-y-2">
              {msg.attachments.map((att, idx) => {
                const isImage = att.content_type?.startsWith('image/');
                return (
                  <div key={idx}>
                    {isImage ? (
                      <button
                        className="block text-left"
                        onClick={() => onLightbox({ url: `${API}${att.file_url}`, name: att.file_name })}
                      >
                        <img
                          src={`${API}${att.file_url}`}
                          alt={att.file_name}
                          className="rounded-lg max-w-full max-h-64 object-cover border cursor-zoom-in hover:opacity-90 transition-opacity"
                        />
                        <span className="text-xs text-muted-foreground mt-1 block">{att.file_name}</span>
                      </button>
                    ) : (
                      <a href={`${API}${att.file_url}`} target="_blank" rel="noreferrer"
                        className="flex items-center gap-2 text-primary hover:underline">
                        <Paperclip size={14} />
                        <span className="truncate max-w-[200px]">{att.file_name}</span>
                        <span className="text-xs text-muted-foreground">
                          ({Math.round(att.file_size / 1024)} KB)
                        </span>
                      </a>
                    )}
                  </div>
                );
              })}
              {msg.content && msg.content !== `📎 ${msg.attachments[0].file_name}` && (
                <span className="whitespace-pre-wrap text-sm">{renderMarkdown(msg.content)}</span>
              )}
            </div>
          ) : msg.message_type === 'file' ? (
            <a href={`${API}${msg.file_url}`} target="_blank" rel="noreferrer"
              className="flex items-center gap-2 text-primary hover:underline">
              <Paperclip size={14} />
              <span className="truncate max-w-[200px]">{msg.file_name || 'Lampiran'}</span>
            </a>
          ) : (
            <span className="whitespace-pre-wrap text-sm leading-relaxed">{renderMarkdown(msg.content)}</span>
          )}

          {/* Deep Link Preview Cards */}
          {!editing && msg.content && (() => {
            const links = parseDeepLinks(msg.content);
            if (!links.length) return null;
            return (
              <div className="mt-1 space-y-1">
                {links.map((link, idx) => (
                  <LinkPreviewCard key={idx} link={link} onNavigate={onNavigate} token={token} />
                ))}
              </div>
            );
          })()}

          {/* Hover toolbar (reactions + reply + thread + more menu) */}
          {!editing && !isSystem && (
            <div className={`absolute -top-8 ${isMine ? 'right-0' : 'left-0'} hidden group-hover:flex bg-card border rounded-full shadow-lg px-2 py-1 gap-1 z-10`}>
              {EMOJI_LIST.slice(0, 5).map((e) => (
                <button key={e} className="text-base hover:scale-125 transition-transform"
                  onClick={() => onReact(msg.id, e)}>{e}</button>
              ))}
              <button className="text-muted-foreground hover:text-foreground ml-1"
                onClick={() => onReply(msg)} data-testid="message-reply-btn">
                <Reply size={14} />
              </button>

              {!isInThread && onOpenThread && (
                <button
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => onOpenThread(msg)}
                  data-testid="message-thread-btn"
                  title="Buka thread"
                >
                  <MessagesSquare size={14} />
                </button>
              )}

              {(editable || deletable || pinnable || unpinnable) && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      className="text-muted-foreground hover:text-foreground"
                      data-testid="message-more-btn"
                      aria-label="More actions"
                    >
                      <MoreVertical size={14} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align={isMine ? 'end' : 'start'} className="w-44">
                    {editable && (
                      <DropdownMenuItem
                        onClick={() => { setEditing(true); setEditText(msg.content || ''); }}
                        data-testid="message-edit-action"
                      >
                        <Pencil size={14} className="mr-2" /> Edit pesan
                      </DropdownMenuItem>
                    )}
                    {pinnable && (
                      <DropdownMenuItem onClick={() => onPin(msg.id)} data-testid="message-pin-action">
                        <Pin size={14} className="mr-2" /> Pin pesan
                      </DropdownMenuItem>
                    )}
                    {unpinnable && (
                      <DropdownMenuItem onClick={() => onUnpin(msg.id)} data-testid="message-unpin-action">
                        <PinOff size={14} className="mr-2" /> Unpin pesan
                      </DropdownMenuItem>
                    )}
                    {(editable || pinnable || unpinnable) && deletable && <DropdownMenuSeparator />}
                    {deletable && (
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onClick={() => onDelete(msg)}
                        data-testid="message-delete-action"
                      >
                        <Trash2 size={14} className="mr-2" /> Hapus pesan
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          )}
        </div>

        {/* Reactions */}
        {msg.reactions && Object.keys(msg.reactions).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {Object.entries(msg.reactions).map(([emoji, users]) => (
              <button
                key={emoji}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                  users.includes(currentUserId)
                    ? 'bg-primary/15 border-primary/40 text-primary'
                    : 'bg-muted/50 border-border hover:bg-muted'
                }`}
                onClick={() => onReact(msg.id, emoji)}
              >
                {emoji} {users.length}
              </button>
            ))}
          </div>
        )}

        {/* Thread reply count badge */}
        {!isInThread && (msg.thread_reply_count || 0) > 0 && onOpenThread && (
          <button
            onClick={() => onOpenThread(msg)}
            data-testid={`message-thread-badge-${msg.id}`}
            className="mt-1.5 inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-primary/30 bg-primary/5 text-primary hover:bg-primary/10 transition-colors group/thread"
          >
            <MessagesSquare size={12} />
            <span className="font-semibold">{msg.thread_reply_count}</span>
            <span className="text-foreground/60">
              {msg.thread_reply_count === 1 ? 'balasan' : 'balasan'}
            </span>
            {msg.thread_last_reply_by && (
              <span className="text-muted-foreground hidden sm:inline">
                · Terakhir oleh {msg.thread_last_reply_by}
              </span>
            )}
            <ChevronRight size={11} className="text-muted-foreground group-hover/thread:translate-x-0.5 transition-transform" />
          </button>
        )}
      </div>
    </div>
  );
}
