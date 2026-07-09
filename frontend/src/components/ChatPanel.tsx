import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";

type Msg = { id: number; sender: "user" | "admin"; text: string; created_at: string; seen?: boolean };
type Thread = { user_id: string; name: string; email: string; unread: number; active?: boolean; last: { text: string; sender: string; created_at: string } | null };

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}
function fmtDay(iso: string): string {
  try {
    const d = new Date(iso);
    const today = new Date();
    const yest = new Date(); yest.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yest.toDateString())  return "Yesterday";
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch { return ""; }
}

const VIOLET = "#7c3aed";
const GRAD = "linear-gradient(135deg, #7c3aed 0%, #6d28d9 60%, #5b21b6 100%)";

function Avatar({ name, size = 30, active }: { name: string; size?: number; active?: boolean }) {
  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      <div style={{ width: size, height: size, borderRadius: 999, background: "rgba(124,58,237,0.14)",
        color: VIOLET, display: "grid", placeItems: "center", fontSize: size * 0.42, fontWeight: 700 }}>
        {(name || "?").slice(0, 1).toUpperCase()}
      </div>
      {active != null && (
        <span style={{ position: "absolute", right: -1, bottom: -1, width: 9, height: 9, borderRadius: 999,
          background: active ? "#22c55e" : "#9ca3af", border: "2px solid var(--bg-surface)" }} />
      )}
    </div>
  );
}

// Floating Help & Chat panel — user talks to admin; admin sees all threads.
export default function ChatPanel({ isAdmin, adminActive, onClose, onRead }: {
  isAdmin: boolean; adminActive?: boolean; onClose: () => void; onRead: () => void;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [allUsers, setAllUsers] = useState<Thread[]>([]);   // admin: every user, for search/new-thread
  const [query, setQuery] = useState("");
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
    const t = setInterval(load, 3000); // poll every 3s while open — near-live feel
    return () => clearInterval(t);
  }, [load]);

  // Admin: full user list once per open, so search can find users with no thread yet
  useEffect(() => {
    if (!isAdmin) return;
    api.adminChatUsers().then(us => setAllUsers(us.map((u: any) => ({ ...u, unread: 0, last: null })))).catch(() => {});
  }, [isAdmin]);

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
  const openThread = isAdmin
    ? (threads.find(t => t.user_id === activeThread) || allUsers.find(u => u.user_id === activeThread))
    : null;
  const peerActive = isAdmin ? !!openThread?.active : !!adminActive;
  const headerTitle = isAdmin
    ? (activeThread ? (openThread?.name || "Chat") : "Help & Chat")
    : "Help & Chat";

  // Search: matching threads first, then users without a thread ("start new")
  const q = query.trim().toLowerCase();
  const matches = (t: Thread) => !q || (t.name || "").toLowerCase().includes(q) || (t.email || "").toLowerCase().includes(q);
  const shownThreads = threads.filter(matches);
  const threadIds = new Set(threads.map(t => t.user_id));
  const newChatUsers = q ? allUsers.filter(u => !threadIds.has(u.user_id) && matches(u)) : [];

  // "Seen" shows only under my LATEST message (standard chat UX)
  const lastMineIdx = (() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const mine = isAdmin ? msgs[i].sender === "admin" : msgs[i].sender === "user";
      if (mine) return i;
    }
    return -1;
  })();

  return (
    <div style={{
      position: "fixed", bottom: 18, left: 18, zIndex: 8000,
      width: 372, height: 520, display: "flex", flexDirection: "column",
      background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 16,
      boxShadow: "0 18px 50px rgba(0,0,0,.30)", overflow: "hidden",
    }}>
      {/* Header — gradient */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "13px 16px", background: GRAD, flexShrink: 0 }}>
        {isAdmin && activeThread && (
          <button onClick={() => { setActiveThread(null); setMsgs([]); }} title="Back to threads"
            style={{ background: "rgba(255,255,255,0.15)", border: "none", cursor: "pointer", color: "#fff",
              width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center", fontSize: 14, padding: 0 }}>←</button>
        )}
        <div style={{ width: 34, height: 34, borderRadius: 999, background: "rgba(255,255,255,0.18)",
          display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {headerTitle}
          </div>
          {(!showThreadList) && (
            <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10.5, color: "rgba(255,255,255,0.85)" }}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: peerActive ? "#4ade80" : "rgba(255,255,255,0.45)", display: "inline-block" }} />
              {isAdmin ? (peerActive ? "Active now" : "Offline") : (peerActive ? "Admin is online" : "Admin is away — replies when back")}
            </div>
          )}
          {showThreadList && (
            <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.85)" }}>
              {threads.length} conversation{threads.length === 1 ? "" : "s"}
            </div>
          )}
        </div>
        <button onClick={onClose} title="Close"
          style={{ marginLeft: "auto", background: "rgba(255,255,255,0.15)", border: "none", cursor: "pointer", color: "#fff",
            width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center", fontSize: 13, padding: 0 }}>✕</button>
      </div>

      {/* Body */}
      {showThreadList ? (
        <div style={{ flex: 1, overflowY: "auto", background: "var(--bg-elevated)", display: "flex", flexDirection: "column" }}>
          {/* Search — finds existing threads AND any user to start a new chat */}
          <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--line)", background: "var(--bg-surface)", flexShrink: 0 }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search users by name or email…"
              style={{ width: "100%", height: 34, padding: "0 14px", borderRadius: 18, border: "1px solid var(--line)",
                background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 12.5, outline: "none", boxSizing: "border-box" }}
            />
          </div>
          {shownThreads.length === 0 && newChatUsers.length === 0 && (
            <div style={{ padding: "60px 24px", textAlign: "center", color: "var(--tx-3)" }}>
              <div style={{ fontSize: 30, marginBottom: 10 }}>💬</div>
              <div style={{ fontSize: 12.5 }}>{q ? "No users match that search." : <>No conversations yet.<br/>Search a user above to start one.</>}</div>
            </div>
          )}
          {shownThreads.map(t => (
            <button key={t.user_id} onClick={() => { setActiveThread(t.user_id); setMsgs([]); setQuery(""); }}
              style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left",
                padding: "12px 16px", background: "var(--bg-surface)", border: "none", borderBottom: "1px solid var(--line)", cursor: "pointer", flexShrink: 0 }}>
              <Avatar name={t.name} size={36} active={!!t.active} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 650, color: "var(--tx)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.name}</span>
                  {t.last && <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--tx-3)", flexShrink: 0 }}>{fmtDay(t.last.created_at)}</span>}
                </div>
                {t.last && (
                  <div style={{ fontSize: 11.5, color: t.unread > 0 ? "var(--tx)" : "var(--tx-3)", fontWeight: t.unread > 0 ? 600 : 400,
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 2 }}>
                    {t.last.sender === "admin" ? "You: " : ""}{t.last.text}
                  </div>
                )}
              </div>
              {t.unread > 0 && (
                <span style={{ minWidth: 19, height: 19, borderRadius: 999, background: VIOLET, color: "#fff",
                  fontSize: 10.5, fontWeight: 700, display: "grid", placeItems: "center", padding: "0 5px", flexShrink: 0 }}>{t.unread}</span>
              )}
            </button>
          ))}
          {newChatUsers.length > 0 && (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em",
                color: "var(--tx-3)", padding: "10px 16px 5px", flexShrink: 0 }}>Start new chat</div>
              {newChatUsers.map(u => (
                <button key={u.user_id} onClick={() => { setActiveThread(u.user_id); setMsgs([]); setQuery(""); }}
                  style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left",
                    padding: "10px 16px", background: "var(--bg-surface)", border: "none", borderBottom: "1px solid var(--line)", cursor: "pointer", flexShrink: 0 }}>
                  <Avatar name={u.name} size={32} active={!!u.active} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--tx)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{u.name}</div>
                    <div style={{ fontSize: 10.5, color: "var(--tx-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{u.email}</div>
                  </div>
                  <span style={{ fontSize: 11, color: VIOLET, fontWeight: 600, flexShrink: 0 }}>Message →</span>
                </button>
              ))}
            </>
          )}
        </div>
      ) : (
        <>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "14px 14px 10px", display: "flex", flexDirection: "column", gap: 3,
            background: "var(--bg-elevated)" }}>
            {msgs.length === 0 && (
              <div style={{ margin: "auto", textAlign: "center", color: "var(--tx-3)", padding: "0 28px" }}>
                <div style={{ fontSize: 30, marginBottom: 10 }}>👋</div>
                <div style={{ fontSize: 12.5, lineHeight: 1.6 }}>
                  {isAdmin ? "No messages in this thread yet." : "Hi! Questions, issues, or feedback — drop a message and the admin will get back to you."}
                </div>
              </div>
            )}
            {msgs.map((m, idx) => {
              const mine = isAdmin ? m.sender === "admin" : m.sender === "user";
              const prev = msgs[idx - 1];
              const newDay = !prev || fmtDay(prev.created_at) !== fmtDay(m.created_at);
              const sameSenderAsPrev = prev && prev.sender === m.sender && !newDay;
              return (
                <div key={m.id}>
                  {newDay && (
                    <div style={{ textAlign: "center", margin: "10px 0 8px" }}>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--tx-3)", background: "var(--bg-surface)",
                        border: "1px solid var(--line)", borderRadius: 999, padding: "3px 10px" }}>{fmtDay(m.created_at)}</span>
                    </div>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", alignItems: mine ? "flex-end" : "flex-start",
                    marginTop: sameSenderAsPrev ? 2 : 8 }}>
                    <div style={{
                      maxWidth: "80%", padding: "8px 13px", fontSize: 12.5, lineHeight: 1.55,
                      whiteSpace: "pre-wrap", wordBreak: "break-word",
                      background: mine ? GRAD : "var(--bg-surface)",
                      color: mine ? "#fff" : "var(--tx)",
                      border: mine ? "none" : "1px solid var(--line)",
                      borderRadius: 14,
                      borderBottomRightRadius: mine ? 5 : 14,
                      borderBottomLeftRadius: mine ? 14 : 5,
                      boxShadow: mine ? "0 2px 8px rgba(124,58,237,0.25)" : "0 1px 3px rgba(0,0,0,0.06)",
                    }}>{m.text}</div>
                    <span style={{ fontSize: 9.5, color: "var(--tx-3)", marginTop: 3, padding: "0 4px" }}>
                      {fmtTime(m.created_at)}
                      {mine && idx === lastMineIdx && (
                        <span style={{ marginLeft: 5, color: m.seen ? "#22c55e" : "var(--tx-3)", fontWeight: 600 }}>
                          {m.seen ? "Seen ✓✓" : "Sent ✓"}
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Composer */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, padding: "10px 12px",
            borderTop: "1px solid var(--line)", background: "var(--bg-surface)", flexShrink: 0 }}>
            <textarea
              ref={draftRef}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Type a message…"
              rows={1}
              style={{ flex: 1, resize: "none", padding: "9px 14px", borderRadius: 20, border: "1px solid var(--line)",
                background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 12.5, outline: "none",
                fontFamily: "inherit", maxHeight: 90, lineHeight: 1.4 }}
            />
            <button onClick={send} disabled={sending || !draft.trim()} title="Send"
              style={{ width: 36, height: 36, borderRadius: 999, border: "none", flexShrink: 0,
                cursor: draft.trim() ? "pointer" : "default",
                background: draft.trim() ? GRAD : "var(--bg-elevated)",
                color: draft.trim() ? "#fff" : "var(--tx-3)",
                display: "grid", placeItems: "center",
                boxShadow: draft.trim() ? "0 2px 8px rgba(124,58,237,0.35)" : "none" }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>
              </svg>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
