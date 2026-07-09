import { useState, useEffect, useRef } from "react";
import { api } from "../api";

type AiMsg = { id: number; role: "user" | "assistant"; text: string; created_at: string };

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

const VIOLET = "#7c3aed";
const GRAD = "linear-gradient(135deg, #7c3aed 0%, #6d28d9 60%, #5b21b6 100%)";

// Standalone floating AI Assistant — resume-grounded Q&A ("can I apply?").
export default function AssistantPanel({ onClose }: { onClose: () => void }) {
  const [msgs, setMsgs] = useState<AiMsg[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [thinking, setThinking] = useState(false);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.assistantMessages().then(d => {
      setMsgs(d.messages);
      setRemaining(d.remaining);
    }).catch(() => {});
  }, []);

  const lastId = msgs.length ? msgs[msgs.length - 1].id : 0;
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lastId, thinking]);

  const send = async () => {
    const text = draft.trim();
    if (!text || thinking) return;
    setMsgs(m => [...m, { id: Date.now(), role: "user", text, created_at: new Date().toISOString() }]);
    setDraft("");
    setThinking(true);
    try {
      const r = await api.assistantAsk(text);
      setMsgs(m => [...m, { id: Date.now() + 1, role: "assistant", text: r.answer, created_at: new Date().toISOString() }]);
      setRemaining(r.remaining);
    } catch (e: any) {
      setMsgs(m => [...m, { id: Date.now() + 1, role: "assistant", text: `⚠️ ${e.message || "Something went wrong — try again."}`, created_at: new Date().toISOString() }]);
    } finally {
      setThinking(false);
      draftRef.current?.focus();
    }
  };

  return (
    <div style={{
      position: "fixed", bottom: 18, left: 18, zIndex: 8000,
      width: 400, height: 560, display: "flex", flexDirection: "column",
      background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 16,
      boxShadow: "0 18px 50px rgba(0,0,0,.30)", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "13px 16px", background: GRAD, flexShrink: 0 }}>
        <div style={{ width: 34, height: 34, borderRadius: 999, background: "rgba(255,255,255,0.18)",
          display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/>
          </svg>
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>AI Assistant</div>
          <div style={{ fontSize: 10.5, color: "rgba(255,255,255,0.85)" }}>
            Answers from your resume{remaining != null && <> · {remaining} left today</>}
          </div>
        </div>
        <button onClick={onClose} title="Close"
          style={{ marginLeft: "auto", background: "rgba(255,255,255,0.15)", border: "none", cursor: "pointer", color: "#fff",
            width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center", fontSize: 13, padding: 0 }}>✕</button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "14px 14px 10px", background: "var(--bg-elevated)" }}>
        {msgs.length === 0 && !thinking && (
          <div style={{ margin: "48px auto 0", textAlign: "center", color: "var(--tx-3)", padding: "0 26px" }}>
            <div style={{ fontSize: 30, marginBottom: 10 }}>✦</div>
            <div style={{ fontSize: 12.5, lineHeight: 1.65 }}>
              Ask anything about your job hunt — grounded in <b>your resume</b>.
              <br /><br />
              Paste a job description and ask <i>"can I apply for this role?"</i> — you'll get a YES / STRETCH / NO verdict with reasons, missing skills, and any sponsorship blockers.
            </div>
          </div>
        )}
        {msgs.map(m => {
          const mine = m.role === "user";
          return (
            <div key={m.id} style={{ display: "flex", flexDirection: "column", alignItems: mine ? "flex-end" : "flex-start", marginTop: 8 }}>
              <div style={{
                maxWidth: "84%", padding: "8px 13px", fontSize: 12.5, lineHeight: 1.55,
                whiteSpace: "pre-wrap", wordBreak: "break-word",
                background: mine ? GRAD : "var(--bg-surface)",
                color: mine ? "#fff" : "var(--tx)",
                border: mine ? "none" : "1px solid var(--line)",
                borderRadius: 14,
                borderBottomRightRadius: mine ? 5 : 14,
                borderBottomLeftRadius: mine ? 14 : 5,
                boxShadow: mine ? "0 2px 8px rgba(124,58,237,0.25)" : "0 1px 3px rgba(0,0,0,0.06)",
              }}>{m.text}</div>
              <span style={{ fontSize: 9.5, color: "var(--tx-3)", marginTop: 3, padding: "0 4px" }}>{fmtTime(m.created_at)}</span>
            </div>
          );
        })}
        {thinking && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, color: "var(--tx-3)", fontSize: 12 }}>
            <span style={{ width: 14, height: 14, border: "2px solid var(--line)", borderTopColor: VIOLET, borderRadius: 999, display: "inline-block", animation: "spin 0.8s linear infinite" }} />
            Analyzing against your resume…
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 8, padding: "10px 12px",
        borderTop: "1px solid var(--line)", background: "var(--bg-surface)", flexShrink: 0 }}>
        <textarea
          ref={draftRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Paste a JD or ask a question…"
          rows={1}
          style={{ flex: 1, resize: "none", padding: "9px 14px", borderRadius: 20, border: "1px solid var(--line)",
            background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 12.5, outline: "none",
            fontFamily: "inherit", maxHeight: 110, lineHeight: 1.4 }}
        />
        <button onClick={send} disabled={thinking || !draft.trim()} title="Send"
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
    </div>
  );
}
