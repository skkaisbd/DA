/**
 * Communication Hub Portal — orchestrator shell.
 *
 * [REFACTORED 2026-05-24 Session #10] was 1751 LOC monolith → now ~280 LOC shell.
 * All UI pieces live in ./communication-hub/* sub-modules:
 *   - utils.js (apicall, formatTime, initials, avatarColor, EMOJI_LIST)
 *   - Markdown.jsx (renderMarkdown)
 *   - dialogs.jsx (CreateChannelDialog, NewDMDialog)
 *   - MessageItem.jsx, ThreadPanel.jsx
 *   - Sidebar.jsx, ChatHeader.jsx, PinnedPanel.jsx, MessageList.jsx, Composer.jsx
 *   - ImageLightbox.jsx
 *   - useCommWebSocket.js (WS hook)
 *
 * External API (props) UNCHANGED: { token, user, isEmbedded, initialChannelId }
 * Default export name UNCHANGED: CommunicationHubPortal
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Hash, MessageSquare } from 'lucide-react';

import { apicall } from './communication-hub/utils';
import { CreateChannelDialog, NewDMDialog } from './communication-hub/dialogs';
import Sidebar from './communication-hub/Sidebar';
import ChatHeader from './communication-hub/ChatHeader';
import PinnedPanel from './communication-hub/PinnedPanel';
import MessageList from './communication-hub/MessageList';
import Composer from './communication-hub/Composer';
import ImageLightbox from './communication-hub/ImageLightbox';
import ThreadPanel from './communication-hub/ThreadPanel';
import useCommWebSocket from './communication-hub/useCommWebSocket';

export default function CommunicationHubPortal({ token, user, isEmbedded = false, initialChannelId = null }) {
  // ── Sidebar data ───────────────────────────────────────────────────────────
  const [channels, setChannels] = useState([]);
  const [archivedChannels, setArchivedChannels] = useState([]);
  const [conversations, setConversations] = useState([]);

  // ── Active view ────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState(null); // {type, id, name, otherUserId?}
  const [messages, setMessages] = useState([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  // ── Per-channel auxiliary state ────────────────────────────────────────────
  const [channelMembers, setChannelMembers] = useState([]);
  const [pinnedMessages, setPinnedMessages] = useState([]);
  const [showPinned, setShowPinned] = useState(false);

  // ── Realtime / presence ────────────────────────────────────────────────────
  const [onlineUsers, setOnlineUsers] = useState(new Set());
  const [typingUsers, setTypingUsers] = useState({});

  // ── UI dialogs / panels ────────────────────────────────────────────────────
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [showNewDM, setShowNewDM] = useState(false);
  const [replyTo, setReplyTo] = useState(null);
  const [threadRoot, setThreadRoot] = useState(null);
  const [lightboxImg, setLightboxImg] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // ── Refs ───────────────────────────────────────────────────────────────────
  const messagesEndRef = useRef(null);
  const typingTimerRef = useRef({});

  const currentUserId = user?.id || '';
  const isAdmin = ['admin', 'superadmin'].includes(user?.role);

  // ── Browser notification permission ────────────────────────────────────────
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  // ── Data loaders ───────────────────────────────────────────────────────────
  const loadChannels = useCallback(async () => {
    try { const d = await apicall('GET', '/api/comm/channels', token); if (Array.isArray(d)) setChannels(d); }
    catch { /* ignore */ }
  }, [token]);

  const loadArchivedChannels = useCallback(async () => {
    try { const d = await apicall('GET', '/api/comm/channels?include_archived=true', token); if (Array.isArray(d)) setArchivedChannels(d); }
    catch { /* ignore */ }
  }, [token]);

  const loadConversations = useCallback(async () => {
    try { const d = await apicall('GET', '/api/comm/conversations', token); if (Array.isArray(d)) setConversations(d); }
    catch { /* ignore */ }
  }, [token]);

  useEffect(() => { loadChannels(); loadConversations(); }, [loadChannels, loadConversations]);

  // ── Auto-select initial channel when embedded ──────────────────────────────
  useEffect(() => {
    if (isEmbedded && initialChannelId && channels.length > 0 && !activeView) {
      const channel = channels.find((ch) => ch.id === initialChannelId);
      if (channel) {
        setActiveView({ type: 'channel', id: channel.id, name: channel.name, description: channel.description });
      }
    }
  }, [isEmbedded, initialChannelId, channels, activeView]);

  // ── Load channel members + pinned on active channel change ─────────────────
  useEffect(() => {
    if (activeView?.type === 'channel') {
      apicall('GET', `/api/comm/channels/${activeView.id}/members`, token)
        .then((d) => { if (d?.members) setChannelMembers(d.members); })
        .catch(() => {});
      apicall('GET', `/api/comm/channels/${activeView.id}/pinned`, token)
        .then((d) => { if (Array.isArray(d)) setPinnedMessages(d); })
        .catch(() => {});
    } else {
      setPinnedMessages([]);
      setShowPinned(false);
    }
  }, [activeView, token]);

  // ── Load messages on view change ───────────────────────────────────────────
  useEffect(() => {
    if (!activeView) return;
    setLoadingMsgs(true);
    setMessages([]);
    const path = activeView.type === 'channel'
      ? `/api/comm/channels/${activeView.id}/messages?limit=50`
      : `/api/comm/conversations/${activeView.otherUserId}/messages?limit=50`;
    apicall('GET', path, token)
      .then((data) => {
        if (Array.isArray(data)) setMessages(data);
        setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'instant' }), 50);
      })
      .catch(() => {})
      .finally(() => setLoadingMsgs(false));
    apicall('POST', `/api/comm/read/${activeView.id}`, token).catch(() => {});
  }, [activeView?.id, activeView?.type, activeView?.otherUserId, token]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── WebSocket: one centralized event handler ───────────────────────────────
  const handleWsEvent = useCallback((payload) => {
    if (payload.type === 'new_message') {
      const { message, channel_id, conv_id, scope } = payload.data;
      // Notification for messages not from self
      if (message.sender_id !== currentUserId) {
        const isActiveChannel =
          (activeView?.type === 'channel' && activeView?.id === channel_id) ||
          (activeView?.type === 'dm' && conv_id);
        const title = message.sender_name || 'Pesan baru';
        const body = message.content?.slice(0, 80) || '📎 Lampiran';
        if (document.hidden) {
          if ('Notification' in window && Notification.permission === 'granted') {
            try { new Notification(title, { body, icon: '/logo192.png', tag: message.id }); } catch { /* */ }
          }
        } else if (!isActiveChannel) {
          toast(`💬 ${title}`, { description: body, duration: 4000 });
        }
      }
      // Append if in active view
      setActiveView((av) => {
        if (av) {
          const match =
            (av.type === 'channel' && channel_id && av.id === channel_id) ||
            (av.type === 'dm' && conv_id);
          if (match) {
            setMessages((prev) => prev.find((m) => m.id === message.id) ? prev : [...prev, message]);
            setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
            const refId = av.type === 'channel' ? channel_id : conv_id;
            apicall('POST', `/api/comm/read/${refId}`, token).catch(() => {});
          }
        }
        return av;
      });
      if (scope === 'channel') loadChannels(); else loadConversations();
    } else if (payload.type === 'reaction_update') {
      const { msg_id, reactions } = payload.data;
      setMessages((prev) => prev.map((m) => m.id === msg_id ? { ...m, reactions } : m));
    } else if (payload.type === 'message_edited') {
      const { msg_id, message } = payload.data;
      setMessages((prev) => prev.map((m) => m.id === msg_id ? { ...m, ...(message || {}) } : m));
    } else if (payload.type === 'message_deleted') {
      const { msg_id } = payload.data;
      setMessages((prev) => prev.filter((m) => m.id !== msg_id));
      setPinnedMessages((prev) => prev.filter((m) => m.id !== msg_id));
    } else if (payload.type === 'message_pinned') {
      const { msg_id } = payload.data;
      setActiveView((av) => {
        if (av?.type === 'channel') {
          apicall('GET', `/api/comm/channels/${av.id}/pinned`, token)
            .then((d) => { if (Array.isArray(d)) setPinnedMessages(d); }).catch(() => {});
          setMessages((prev) => prev.map((m) => m.id === msg_id ? { ...m, pinned: true } : m));
        }
        return av;
      });
      toast('📌 Pesan di-pin', { duration: 2000 });
    } else if (payload.type === 'message_unpinned') {
      const { msg_id } = payload.data;
      setPinnedMessages((prev) => prev.filter((m) => m.id !== msg_id));
      setMessages((prev) => prev.map((m) => m.id === msg_id ? { ...m, pinned: false } : m));
      toast('Pesan di-unpin', { duration: 2000 });
    } else if (payload.type === 'thread_reply') {
      const { reply, root_id, reply_count } = payload.data || {};
      if (!reply || !root_id) return;
      setMessages((prev) => prev.map((m) => m.id === root_id ? {
        ...m,
        thread_reply_count: reply_count ?? ((m.thread_reply_count || 0) + 1),
        thread_last_reply_at: reply.created_at,
        thread_last_reply_by: reply.sender_name,
      } : m));
      window.dispatchEvent(new CustomEvent('thread:newReply', { detail: { root_id, reply, reply_count } }));
    } else if (payload.type === 'presence') {
      const { user_id, online } = payload.data;
      setOnlineUsers((prev) => {
        const next = new Set(prev);
        if (online) next.add(user_id); else next.delete(user_id);
        return next;
      });
      setConversations((prev) => prev.map((c) =>
        c.other_user?.id === user_id ? { ...c, is_online: online } : c
      ));
    } else if (payload.type === 'typing') {
      const { user_id, user_name, channel_id: cid } = payload.data;
      const key = cid || 'dm';
      setTypingUsers((prev) => ({ ...prev, [key]: { user_id, user_name, ts: Date.now() } }));
      clearTimeout(typingTimerRef.current[key]);
      typingTimerRef.current[key] = setTimeout(() => {
        setTypingUsers((prev) => { const n = { ...prev }; delete n[key]; return n; });
      }, 3000);
    } else if (payload.type === 'channel_added') {
      loadChannels();
    }
  }, [activeView, currentUserId, token, loadChannels, loadConversations]);

  const { wsConnected, wsRef } = useCommWebSocket(token, handleWsEvent);

  // ── Message-action handlers ────────────────────────────────────────────────
  const handleReact = useCallback(async (msgId, emoji) => {
    try {
      const data = await apicall('POST', `/api/comm/messages/${msgId}/reaction`, token, { emoji });
      if (data.reactions !== undefined) {
        setMessages((prev) => prev.map((m) => m.id === msgId ? { ...m, reactions: data.reactions } : m));
      }
    } catch { /* */ }
  }, [token]);

  const handleEditMessage = useCallback(async (msgId, newContent) => {
    try {
      const data = await apicall('PATCH', `/api/comm/messages/${msgId}`, token, { content: newContent });
      if (data?.id) {
        setMessages((prev) => prev.map((m) => m.id === msgId ? { ...m, ...data } : m));
        toast.success('Pesan diperbarui');
        return true;
      }
      toast.error(data?.detail || 'Gagal mengedit pesan');
      return false;
    } catch {
      toast.error('Gagal mengedit pesan');
      return false;
    }
  }, [token]);

  const handleDeleteMessage = useCallback(async (msg) => {
    if (!window.confirm('Hapus pesan ini secara permanen?')) return;
    try {
      const data = await apicall('DELETE', `/api/comm/messages/${msg.id}`, token);
      if (data?.ok) {
        setMessages((prev) => prev.filter((m) => m.id !== msg.id));
        setPinnedMessages((prev) => prev.filter((m) => m.id !== msg.id));
        toast.success('Pesan dihapus');
      } else {
        toast.error(data?.detail || 'Gagal menghapus pesan');
      }
    } catch {
      toast.error('Gagal menghapus pesan');
    }
  }, [token]);

  const handlePinMessage = useCallback(async (msgId) => {
    try {
      const data = await apicall('POST', `/api/comm/messages/${msgId}/pin`, token);
      if (data?.ok) {
        setMessages((prev) => prev.map((m) => m.id === msgId ? { ...m, pinned: true } : m));
        if (activeView?.type === 'channel') {
          apicall('GET', `/api/comm/channels/${activeView.id}/pinned`, token)
            .then((d) => { if (Array.isArray(d)) setPinnedMessages(d); })
            .catch(() => {});
        }
        toast.success('📌 Pesan di-pin');
      } else {
        toast.error(data?.detail || 'Gagal pin pesan');
      }
    } catch { toast.error('Gagal pin pesan'); }
  }, [token, activeView]);

  const handleUnpinMessage = useCallback(async (msgId) => {
    try {
      const data = await apicall('DELETE', `/api/comm/messages/${msgId}/pin`, token);
      if (data?.ok) {
        setPinnedMessages((prev) => prev.filter((m) => m.id !== msgId));
        setMessages((prev) => prev.map((m) => m.id === msgId ? { ...m, pinned: false } : m));
        toast.success('Pesan di-unpin');
      } else {
        toast.error(data?.detail || 'Gagal unpin pesan');
      }
    } catch { toast.error('Gagal unpin pesan'); }
  }, [token]);

  const handleArchiveChannel = useCallback(async (channelId) => {
    if (!window.confirm('Arsipkan channel ini? Channel tidak akan muncul di daftar utama.')) return;
    try {
      const data = await apicall('PATCH', `/api/comm/channels/${channelId}/archive`, token);
      if (data?.ok) {
        setChannels((prev) => prev.filter((c) => c.id !== channelId));
        if (activeView?.id === channelId) setActiveView(null);
        loadArchivedChannels();
        toast.success('Channel diarsipkan');
      }
    } catch { toast.error('Gagal arsipkan channel'); }
  }, [token, activeView, loadArchivedChannels]);

  const handleUnarchiveChannel = useCallback(async (channelId) => {
    try {
      const data = await apicall('PATCH', `/api/comm/channels/${channelId}/unarchive`, token);
      if (data?.ok) {
        setArchivedChannels((prev) => prev.filter((c) => c.id !== channelId));
        loadChannels();
        toast.success('Channel dipulihkan dari arsip');
      }
    } catch { toast.error('Gagal unarchive channel'); }
  }, [token, loadChannels]);

  // ── Channel/DM selection ───────────────────────────────────────────────────
  const selectChannel = useCallback((ch) => {
    setActiveView({ type: 'channel', id: ch.id, name: ch.name, description: ch.description });
  }, []);

  const selectDM = useCallback((conv) => {
    const other = conv.other_user;
    setActiveView({ type: 'dm', id: conv.id, name: other?.name || 'DM', otherUserId: other?.id });
  }, []);

  const startDM = useCallback((otherUser) => {
    const existing = conversations.find((c) => c.other_user?.id === otherUser.id);
    if (existing) { selectDM(existing); return; }
    setActiveView({ type: 'dm', id: `new-${otherUser.id}`, name: otherUser.name, otherUserId: otherUser.id });
    setLoadingMsgs(true);
    apicall('GET', `/api/comm/conversations/${otherUser.id}/messages?limit=50`, token)
      .then((data) => {
        if (Array.isArray(data)) setMessages(data);
        loadConversations();
      })
      .catch(() => {})
      .finally(() => setLoadingMsgs(false));
  }, [conversations, token, selectDM, loadConversations]);

  // ── After Composer sends ──────────────────────────────────────────────────
  const handleMessageSent = useCallback((msg) => {
    setMessages((prev) => prev.find((m) => m.id === msg.id) ? prev : [...prev, msg]);
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  // ── Typing indicator broadcast ────────────────────────────────────────────
  const sendTyping = useCallback(() => {
    if (activeView?.type !== 'channel') return;
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'typing', channel_id: activeView.id })); } catch { /* */ }
    }
  }, [activeView, wsRef]);

  // ── Render ─────────────────────────────────────────────────────────────────
  const typingKey = activeView?.type === 'channel' ? activeView?.id : 'dm';
  const typingUser = typingUsers[typingKey];

  return (
    <div
      className={`flex ${isEmbedded ? 'h-full' : 'h-[calc(100vh-130px)]'} bg-[hsl(var(--background))] rounded-xl border overflow-hidden`}
      data-testid="comm-hub-portal"
    >
      {/* Sidebar */}
      {!sidebarCollapsed && !isEmbedded && (
        <Sidebar
          channels={channels}
          archivedChannels={archivedChannels}
          conversations={conversations}
          onlineUsers={onlineUsers}
          activeView={activeView}
          currentUserId={currentUserId}
          isAdmin={isAdmin}
          wsConnected={wsConnected}
          user={user}
          onSelectChannel={selectChannel}
          onSelectDM={selectDM}
          onShowCreateChannel={() => setShowCreateChannel(true)}
          onShowNewDM={() => setShowNewDM(true)}
          onRefresh={() => { loadChannels(); loadConversations(); }}
          onArchiveChannel={handleArchiveChannel}
          onUnarchiveChannel={handleUnarchiveChannel}
          onShowArchivedRequested={loadArchivedChannels}
        />
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 bg-[hsl(var(--background))]">
        {activeView ? (
          <>
            <ChatHeader
              activeView={activeView}
              isEmbedded={isEmbedded}
              sidebarCollapsed={sidebarCollapsed}
              onToggleSidebar={() => setSidebarCollapsed((p) => !p)}
              pinnedCount={pinnedMessages.length}
              showPinned={showPinned}
              onTogglePinned={() => setShowPinned((p) => !p)}
              wsConnected={wsConnected}
            />

            {showPinned && (
              <PinnedPanel
                pinnedMessages={pinnedMessages}
                isAdmin={isAdmin}
                onUnpin={handleUnpinMessage}
                onClose={() => setShowPinned(false)}
              />
            )}

            <MessageList
              messages={messages}
              loadingMsgs={loadingMsgs}
              currentUserId={currentUserId}
              isAdmin={isAdmin}
              token={token}
              activeViewType={activeView.type}
              onReact={handleReact}
              onReply={setReplyTo}
              onEdit={handleEditMessage}
              onDelete={handleDeleteMessage}
              onPin={handlePinMessage}
              onUnpin={handleUnpinMessage}
              onLightbox={setLightboxImg}
              onOpenThread={setThreadRoot}
              onNavigate={() => {}}
              typingUser={typingUser}
              messagesEndRef={messagesEndRef}
            />

            <Composer
              activeView={activeView}
              channelMembers={channelMembers}
              replyTo={replyTo}
              onClearReply={() => setReplyTo(null)}
              token={token}
              onMessageSent={handleMessageSent}
              onTyping={sendTyping}
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center p-8">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <MessageSquare size={28} className="text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-lg mb-1">Communication Hub</h3>
              <p className="text-sm text-muted-foreground max-w-xs">
                {isEmbedded
                  ? 'Pilih channel atau kontak dari sidebar "Communication" untuk mulai diskusi.'
                  : 'Pilih channel atau kontak dari sidebar untuk mulai berkomunikasi.'}
              </p>
            </div>
            {!isEmbedded && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowCreateChannel(true)} data-testid="empty-create-channel">
                  <Hash size={14} className="mr-1" /> Buat Channel
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowNewDM(true)} data-testid="empty-new-dm">
                  <MessageSquare size={14} className="mr-1" /> Pesan Langsung
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modals & overlays */}
      <CreateChannelDialog
        open={showCreateChannel}
        onClose={() => setShowCreateChannel(false)}
        token={token}
        onCreated={(ch) => { setChannels((prev) => [ch, ...prev]); selectChannel(ch); }}
      />
      <NewDMDialog
        open={showNewDM}
        onClose={() => setShowNewDM(false)}
        token={token}
        currentUserId={currentUserId}
        onStartDM={startDM}
      />

      <ImageLightbox image={lightboxImg} onClose={() => setLightboxImg(null)} />

      {threadRoot && (
        <ThreadPanel
          token={token}
          rootMessage={threadRoot}
          currentUserId={currentUserId}
          isAdmin={isAdmin}
          onClose={() => setThreadRoot(null)}
          onReact={handleReact}
          onEdit={handleEditMessage}
          onDelete={handleDeleteMessage}
          onPin={null}
          onUnpin={null}
          onLightbox={setLightboxImg}
          onRootCountUpdated={(rootId, count, lastReplyBy) => {
            setMessages((prev) => prev.map((m) => m.id === rootId ? {
              ...m,
              thread_reply_count: count,
              thread_last_reply_at: new Date().toISOString(),
              thread_last_reply_by: lastReplyBy,
            } : m));
          }}
        />
      )}
    </div>
  );
}
