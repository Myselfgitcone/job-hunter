import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";

type Msg = { id: number; sender: "user" | "admin"; text: string; created_at: string };
type Thread = { user_id: string; name: string; email: string; unread: number; last: { text: string; sender: string; created_at: string } | null };

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

// Floating Help & Chat panel — user talks to admin; admin sees all threads.
export default function ChatPanel({ isAdmin, onClose, onRead }: {
  isAdmin: boolean; onClose: () => void; onRead: () => void;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThread, setActiveThread] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    try {
      if (isAdmin) {
        const t = await api.adminChatThreads();
        setThreads(t);
        if (activeThread) setMsgs(await api.adminChatMessages(activeThread));
      } else {
        setMsgs(await api.chatMessages());
      }
      onRead(); // reading clears the unread badge server-side
    } catch { /* transient network — next poll retries */ }
  }, [isAdmin, activeThread, onRead]);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000); // poll every 12s while open
    return () => clearInterval(t);
  }, [load]);

  // Auto-scroll to newest message
  const lastId = msgs.length ? msgs[msgs.length - 1].id : 0;
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lastId, activeThread]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      if (isAdmin) {
        if (!activeThread) return;
        await api.adminChatSend(activeThread, text);
      } else {
        await api.chatSend(text);
      }
      setDraft("");
      await load();
      draftRef.current?.focus();
    } catch { /* keep draft so nothing is lost */ }
    finally { setSending(false); }
  };

  const showThreadList = isAdmin && !activeThread;

  return (
    <div style={{
      position: "fixed", bottom: 18, left: 18, zIndex: 8000,
      width: 360, height: 480, display: "flex", flexDirection: "column",
      background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 14,
      boxShadow: "0 12px 40px rgba(0,0,0,.25)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid var(--line)", flexShrink: 0 }}>
        {isAdmin && activeThread && (
          <button onClick={() => { setActiveThread(null); setMsgs([]); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--tx-2)", fontSize: 16, padding: 0 }}>←</button>
        )}
        <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--tx)" }}>
          {isAdmin
            ? (activeThread ? (threads.find(t => t.user_id === activeThread)?.name || "Chat") : "Help & Chat — Threads")
            : "Help & Chat"}
        </span>
        {!isAdmin && <span style={{ fontSize: 11, color: "var(--tx-3)" }}>· admin replies here</span>}
        <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "var(--tx-3)", fontSize: 16, padding: 0 }}>✕</button>
      </div>

      {/* Body */}
      {showThreadList ? (
        <div style={{ flex: 1, overflowY: "auto" }}>
          {threads.length === 0 && (
            <div style={{ padding: "40px 20px", textAlign: "center", fontSize: 12.5, color: "var(--tx-3)" }}>No conversations yet</div>
          )}
          {threads.map(t => (
            <button key={t.user_id} onClick={() => { setActiveThread(t.user_id); setMsgs([]); }}
              style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left",
                padding: "10px 14px", background: "none", border: "none", borderBottom: "1px solid var(--line)", cursor: "pointer" }}>
              <div style={{ width: 32, height: 32, borderRadius: 999, background: "rgba(124,58,237,0.15)", color: "var(--violet)",
                display: "grid", placeItems: "center", fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                {(t.name || "?").slice(0, 1).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--tx)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.name}</div>
                {t.last && <div style={{ fontSize: 11.5, color: "var(--tx-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {t.last.sender === "admin" ? "You: " : ""}{t.last.text}
                </div>}
              </div>
              {t.unread > 0 && (
                <span style={{ minWidth: 18, height: 18, borderRadius: 999, background: "#7c3aed", color: "#fff",
                  fontSize: 10.5, fontWeight: 700, display: "grid", placeItems: "center", padding: "0 5px", flexShrink: 0 }}>{t.unread}</span>
              )}
            </button>
          ))}
        </div>
      ) : (
        <>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            {msgs.length === 0 && (
              <div style={{ margin: "auto", textAlign: "center", fontSize: 12.5, color: "var(--tx-3)", padding: "0 24px" }}>
                {isAdmin ? "No messages in this thread yet." : "Questions or issues? Message the admin here — replies show up in this window."}
              </div>
            )}
            {msgs.map(m => {
              const mine = isAdmin ? m.sender === "admin" : m.sender === "user";
              return (
                <div key={m.id} style={{ display: "flex", flexDirection: "column", alignItems: mine ? "flex-end" : "flex-start" }}>
                  <div style={{
                    maxWidth: "82%", padding: "8px 12px", borderRadius: 12, fontSize: 12.5, lineHeight: 1.5,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    background: mine ? "var(--violet)" : "var(--bg-elevated)",
                    color: mine ? "#fff" : "var(--tx)",
                    border: mine ? "none" : "1px solid var(--line)",
                    borderBottomRightRadius: mine ? 4 : 12, borderBottomLeftRadius: mine ? 12 : 4,
                  }}>{m.text}</div>
                  <span style={{ fontSize: 9.5, color: "var(--tx-3)", marginTop: 2 }}>
                    {!mine && (isAdmin ? "" : "Admin · ")}{fmtTime(m.created_at)}
                  </span>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 8, padding: "10px 12px", borderTop: "1px solid var(--line)", flexShrink: 0 }}>
            <textarea
              ref={draftRef}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Type a message… (Enter to send)"
              rows={1}
              style={{ flex: 1, resize: "none", padding: "8px 12px", borderRadius: 10, border: "1px solid var(--line)",
                background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 12.5, outline: "none", fontFamily: "inherit", maxHeight: 90 }}
            />
            <button onClick={send} disabled={sending || !draft.trim()}
              style={{ padding: "0 16px", borderRadius: 10, border: "none", cursor: draft.trim() ? "pointer" : "default",
                background: draft.trim() ? "var(--violet)" : "var(--bg-elevated)", color: draft.trim() ? "#fff" : "var(--tx-3)",
                fontSize: 12.5, fontWeight: 600 }}>
              {sending ? "…" : "Send"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
