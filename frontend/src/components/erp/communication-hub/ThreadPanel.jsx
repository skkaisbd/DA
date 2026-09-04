/**
 * ThreadPanel — Slack-style nested-reply side drawer (Session 28).
 *
 * Loads the root message + all replies via GET /api/comm/messages/{id}/thread.
 * Listens to `thread:newReply` window CustomEvent dispatched by the parent
 * shell when a `thread_reply` WS event arrives, to append in real-time.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, X, MessagesSquare, ArrowLeft } from 'lucide-react';

import { apicall } from './utils';
import MessageItem from './MessageItem';

export default function ThreadPanel({
  token, rootMessage, currentUserId, isAdmin,
  onClose, onReact, onEdit, onDelete, onPin, onUnpin, onLightbox,
  onThreadReplyAdded, onRootCountUpdated,
}) {
  const [thread, setThread] = useState(null);
  const [loading, setLoading] = useState(true);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  const loadThread = useCallback(async () => {
    if (!rootMessage?.id) return;
    setLoading(true);
    try {
      const data = await apicall('GET', `/api/comm/messages/${rootMessage.id}/thread`, token);
      setThread(data);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'auto' }), 50);
    } catch {
      toast.error('Gagal memuat thread');
    } finally {
      setLoading(false);
    }
  }, [rootMessage?.id, token]);

  useEffect(() => { loadThread(); }, [loadThread]);

  // External: parent dispatches `thread:newReply` on WS thread_reply event
  useEffect(() => {
    if (!rootMessage) return;
    const handler = (ev) => {
      if (ev.detail?.root_id !== rootMessage.id) return;
      const reply = ev.detail?.reply;
      if (!reply) return;
      setThread((prev) => {
        if (!prev) return prev;
        if (prev.replies.find((r) => r.id === reply.id)) return prev;
        return { ...prev, replies: [...prev.replies, reply], reply_count: (prev.reply_count || 0) + 1 };
      });
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 30);
    };
    window.addEventListener('thread:newReply', handler);
    return () => window.removeEventListener('thread:newReply', handler);
  }, [rootMessage]);

  const submit = async () => {
    const text = inputText.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      const r = await apicall('POST', `/api/comm/messages/${rootMessage.id}/thread/reply`, token, { content: text });
      if (r?.id) {
        setThread((prev) => prev ? {
          ...prev,
          replies: prev.replies.find((x) => x.id === r.id) ? prev.replies : [...prev.replies, r],
          reply_count: (prev.reply_count || 0) + 1,
        } : prev);
        setInputText('');
        onThreadReplyAdded?.(r);
        onRootCountUpdated?.(rootMessage.id, (thread?.reply_count || 0) + 1, r.sender_name);
        setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 30);
      }
    } catch {
      toast.error('Gagal kirim reply');
    } finally {
      setSending(false);
    }
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  if (!rootMessage) return null;

  return (
    <div
      data-testid="thread-panel"
      className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] bg-card border-l shadow-2xl flex flex-col"
      role="complementary"
      aria-label="Thread panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            data-testid="thread-panel-close"
            className="p-1.5 -ml-1.5 rounded hover:bg-muted text-muted-foreground"
            aria-label="Tutup thread"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h3 className="text-sm font-semibold flex items-center gap-1.5">
              <MessagesSquare size={14} className="text-primary" /> Thread
            </h3>
            <p className="text-[11px] text-muted-foreground">{thread?.reply_count || 0} balasan</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-muted text-muted-foreground sm:hidden"
          aria-label="Tutup"
        >
          <X size={16} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto py-3" data-testid="thread-panel-body">
        {loading && (
          <div className="text-center py-8 text-sm text-muted-foreground" data-testid="thread-loading">
            Memuat thread...
          </div>
        )}
        {!loading && thread && (
          <>
            {/* Root message */}
            <div className="border-b pb-3 mb-2">
              <MessageItem
                msg={thread.root}
                currentUserId={currentUserId}
                token={token}
                onReact={onReact}
                onReply={() => {}}
                onEdit={onEdit}
                onDelete={onDelete}
                onPin={onPin}
                onUnpin={onUnpin}
                isAdmin={isAdmin}
                onLightbox={onLightbox}
                onOpenThread={null}
                isInThread={true}
              />
            </div>
            {/* Divider */}
            <div className="flex items-center gap-2 px-4 mb-1 text-[11px] text-muted-foreground">
              <span className="font-medium">{thread.reply_count} balasan</span>
              <div className="flex-1 h-px bg-border" />
            </div>
            {/* Replies */}
            {thread.replies.map((r) => (
              <MessageItem
                key={r.id}
                msg={r}
                currentUserId={currentUserId}
                token={token}
                onReact={onReact}
                onReply={() => {}}
                onEdit={onEdit}
                onDelete={onDelete}
                onPin={null}
                onUnpin={null}
                isAdmin={isAdmin}
                onLightbox={onLightbox}
                onOpenThread={null}
                isInThread={true}
              />
            ))}
            {thread.replies.length === 0 && (
              <div className="text-center py-6 text-sm text-muted-foreground" data-testid="thread-empty-replies">
                Belum ada balasan. Mulai diskusi di bawah.
              </div>
            )}
            <div ref={endRef} />
          </>
        )}
      </div>

      {/* Reply input */}
      <div className="border-t px-3 py-2 shrink-0">
        <div className="flex items-end gap-2">
          <Textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={onKey}
            placeholder="Balas di thread..."
            data-testid="thread-input"
            rows={1}
            className="resize-none min-h-9 max-h-32 text-sm"
            disabled={sending}
          />
          <Button
            onClick={submit}
            disabled={sending || !inputText.trim()}
            data-testid="thread-send-button"
            size="sm"
            className="h-9 shrink-0"
          >
            <Send size={14} />
          </Button>
        </div>
      </div>
    </div>
  );
}
