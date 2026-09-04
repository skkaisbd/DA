/**
 * useCommWebSocket — manages the WebSocket connection to /api/comm/ws.
 *
 * Provides:
 *  - wsConnected: boolean state
 *  - wsRef: ref to the active WebSocket (for sendTyping calls)
 *
 * Calls back `onEvent(payload)` for every parsed message so the shell can
 * update state for: new_message, reaction_update, message_edited/deleted/
 * pinned/unpinned, thread_reply, presence, typing, channel_added.
 *
 * Automatic reconnect after 3 s; cleanup on unmount.
 */
import { useEffect, useRef, useState } from 'react';

export default function useCommWebSocket(token, onEvent) {
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const cancelledRef = useRef(false);
  const onEventRef = useRef(onEvent);

  // Keep latest handler in ref so reconnects always use the freshest closure
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    if (!token) return;
    cancelledRef.current = false;

    const connect = () => {
      if (cancelledRef.current) return;
      const base = (process.env.REACT_APP_BACKEND_URL || '')
        .replace(/^https:/i, 'wss:')
        .replace(/^http:/i, 'ws:');
      const url = `${base}/api/comm/ws?token=${encodeURIComponent(token)}`;

      let ws;
      try { ws = new WebSocket(url); } catch { return; }
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelledRef.current) { ws.close(); return; }
        setWsConnected(true);
      };

      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data);
          onEventRef.current?.(payload);
        } catch {
          /* ignore malformed payload */
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (!cancelledRef.current) {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };
      ws.onerror = () => setWsConnected(false);
    };

    connect();
    return () => {
      cancelledRef.current = true;
      clearTimeout(reconnectRef.current);
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, [token]);

  return { wsConnected, wsRef };
}
