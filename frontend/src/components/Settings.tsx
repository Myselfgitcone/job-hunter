import { useState, useEffect } from "react";
import { api } from "../api";
import { ROLE_GROUPS } from "./JobPreferencesModal";

// ── User management (admin): approve signups + assign role families ───────────
function UsersPanel({ onToast, onChanged }: { onToast: (m: string, t?: any) => void; onChanged: () => void }) {
  const [users, setUsers] = useState<any[]>([]);
  const [editing, setEditing] = useState<string | null>(null);   // user id with role picker open
  const [draftRoles, setDraftRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const PER = 10;

  const load = () => api.adminUsers().then(setUsers).catch(() => {});
  useEffect(() => { load(); }, []);

  const openPicker = (u: any) => { setEditing(u.id); setDraftRoles(u.job_roles || []); };

  const toggleFamily = (items: string[]) => {
    const allOn = items.every(i => draftRoles.includes(i));
    setDraftRoles(allOn ? draftRoles.filter(r => !items.includes(r))
                        : [...draftRoles, ...items.filter(i => !draftRoles.includes(i))]);
  };

  const confirm = async (u: any, approve: boolean) => {
    setBusy(true);
    try {
      await api.adminUpdateUser(u.id, { ...(approve ? { status: "approved" } : {}), job_roles: draftRoles });
      onToast(approve ? `${u.email} approved` : "Roles updated", "success");
      setEditing(null); load(); onChanged();
    } catch (e: any) { onToast(e.message, "error"); }
    finally { setBusy(false); }
  };

  const revoke = async (u: any) => {
    if (!window.confirm(`Revoke access for ${u.email}? They'll be locked out until re-approved.`)) return;
    try { await api.adminUpdateUser(u.id, { status: "pending" }); onToast("Access revoked", "success"); load(); onChanged(); }
    catch (e: any) { onToast(e.message, "error"); }
  };

  const remove = async (u: any) => {
    if (!window.confirm(`PERMANENTLY delete ${u.email}? Their account, settings, profile and job statuses are removed. This cannot be undone.`)) return;
    try { await api.adminDeleteUser(u.id); onToast(`${u.email} deleted`, "success"); load(); onChanged(); }
    catch (e: any) { onToast(e.message, "error"); }
  };

  const sorted = [...users].sort((a, b) => (a.status === "pending" ? -1 : 1) - (b.status === "pending" ? -1 : 1));
  const filtered = sorted.filter(u => (u.name + " " + u.email).toLowerCase().includes(q.toLowerCase()));
  const pages = Math.max(1, Math.ceil(filtered.length / PER));
  const cur = Math.min(page, pages);
  const shown = filtered.slice((cur - 1) * PER, cur * PER);

  return (
    <section className="form-section">
      <div className="section-label">
        <Ic d={'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'} size={16} /> Users
        <span style={{ marginLeft: 6, fontSize: 11.5, color: "var(--tx-3)", fontWeight: 600 }}>{users.length}</span>
        {users.some(u => u.status === "pending") && (
          <span style={{ marginLeft: 8, background: "#dc2626", color: "#fff", fontSize: 10.5, fontWeight: 700, borderRadius: 999, padding: "2px 8px" }}>
            {users.filter(u => u.status === "pending").length} pending
          </span>
        )}
      </div>
      <input value={q} onChange={e => { setQ(e.target.value); setPage(1); }}
        placeholder="Search by name or email"
        style={{ width: "100%", height: 38, padding: "0 14px", borderRadius: 10, border: "1px solid var(--line)",
          background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 13, marginBottom: 10, outline: "none" }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 440, overflowY: "auto",
        paddingRight: 4, scrollbarWidth: "thin", scrollbarColor: "var(--line-hi) transparent" }}>
        {shown.map(u => (
          <div key={u.id} style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "12px 14px",
            background: u.status === "pending" ? "rgba(220,38,38,0.04)" : "var(--bg-elevated)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--tx)" }}>
                  {u.name || u.email.split("@")[0]}
                  {u.is_admin && <span style={{ marginLeft: 8, fontSize: 10.5, color: "var(--violet)", fontWeight: 700 }}>ADMIN</span>}
                </div>
                <div style={{ fontSize: 12, color: "var(--tx-3)" }}>{u.email} · joined {(u.created_at || "").slice(0, 10) || "—"}</div>
                {u.is_admin ? (
                  <div style={{ fontSize: 11, color: "var(--tx-3)", marginTop: 6 }}>Sees all jobs (admin — preferences only slice the personal feed)</div>
                ) : u.job_roles.length > 0 ? (
                  u.status === "pending" ? (
                    // Show family names for pending users so admin sees "Requested: Data Engineer, BI"
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: "#d97706", marginRight: 2 }}>Requested:</span>
                      {ROLE_GROUPS
                        .filter(g => g.items.some(i => u.job_roles.includes(i)))
                        .map(g => (
                          <span key={g.group} style={{ fontSize: 10.5, padding: "2px 10px", borderRadius: 999, fontWeight: 600, background: "rgba(217,119,6,0.1)", color: "#d97706" }}>
                            {g.group}
                          </span>
                        ))}
                    </div>
                  ) : (
                    <div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                        {u.job_roles.slice(0, 6).map((r: string) => (
                          <span key={r} style={{ fontSize: 10.5, padding: "2px 8px", borderRadius: 999, background: "rgba(124,58,237,0.1)", color: "var(--violet)", fontWeight: 600 }}>{r}</span>
                        ))}
                        {u.job_roles.length > 6 && <span style={{ fontSize: 10.5, color: "var(--tx-3)" }}>+{u.job_roles.length - 6} more</span>}
                      </div>
                      {/* Role request from approved user */}
                      {(u.role_request || []).length > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 10.5, fontWeight: 700, color: "#d97706" }}>Requesting:</span>
                          {ROLE_GROUPS.filter(g => g.items.some(i => (u.role_request || []).includes(i))).map(g => (
                            <span key={g.group} style={{ fontSize: 10.5, padding: "2px 10px", borderRadius: 999, fontWeight: 600, background: "rgba(217,119,6,0.1)", color: "#d97706" }}>{g.group}</span>
                          ))}
                          <button onClick={async () => { await api.adminUpdateUser(u.id, { grant_role_request: true }); onToast("Role granted", "success"); load(); }}
                            style={{ fontSize: 10.5, fontWeight: 700, padding: "2px 10px", borderRadius: 999, border: "1px solid #16a34a", background: "rgba(22,163,74,0.1)", color: "#16a34a", cursor: "pointer" }}>
                            Grant
                          </button>
                          <button onClick={async () => { await api.adminUpdateUser(u.id, { dismiss_role_request: true }); onToast("Request dismissed", "success"); load(); }}
                            style={{ fontSize: 10.5, fontWeight: 700, padding: "2px 10px", borderRadius: 999, border: "1px solid var(--line-hi)", background: "transparent", color: "var(--tx-3)", cursor: "pointer" }}>
                            Dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  )
                ) : u.status === "pending" ? (
                  <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>No role preference stated</div>
                ) : null}
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
                background: u.status === "approved" ? "rgba(22,163,74,0.12)" : "rgba(220,38,38,0.1)",
                color: u.status === "approved" ? "#16a34a" : "#dc2626" }}>
                {u.status === "approved" ? "Approved" : "Pending"}
              </span>
              {!u.is_admin && (
                <div style={{ display: "flex", gap: 6 }}>
                  {u.status === "pending"
                    ? <button className="act primary" style={{ height: 28, fontSize: 12 }} onClick={() => openPicker(u)}>Approve</button>
                    : <>
                        <button className="act" style={{ height: 28, fontSize: 12 }} onClick={() => openPicker(u)}>Edit Roles</button>
                        <button className="act fail" style={{ height: 28, fontSize: 12, color: "var(--tx-error, #dc2626)" }} onClick={() => revoke(u)}>Revoke</button>
                      </>}
                  <button title="Delete permanently" onClick={() => remove(u)}
                    style={{ height: 28, width: 30, borderRadius: 8, border: "1px solid rgba(220,38,38,0.35)", background: "rgba(220,38,38,0.06)", color: "#dc2626", cursor: "pointer", display: "grid", placeItems: "center" }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              )}
            </div>

            {editing === u.id && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)", marginBottom: 8 }}>
                  Assign role families — they will only see jobs matching these:
                  {u.status === "pending" && u.job_roles.length > 0 && (
                    <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 500, color: "#d97706" }}>
                      (pre-filled from user's request)
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {ROLE_GROUPS.map(g => {
                    const on = g.items.every(i => draftRoles.includes(i));
                    return (
                      <button key={g.group} onClick={() => toggleFamily(g.items)}
                        style={{ fontSize: 12.5, fontWeight: 600, padding: "6px 14px", borderRadius: 999, cursor: "pointer",
                          border: on ? "1px solid var(--violet)" : "1px dashed var(--line-hi)",
                          background: on ? "rgba(124,58,237,0.12)" : "transparent",
                          color: on ? "var(--violet)" : "var(--tx-2)" }}>
                        {on ? "✓ " : "+ "}{g.group}
                      </button>
                    );
                  })}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button className="act primary" disabled={busy || draftRoles.length === 0}
                    onClick={() => confirm(u, u.status === "pending")}>
                    {u.status === "pending" ? "Approve with these roles" : "Save roles"}
                  </button>
                  <button className="act" onClick={() => setEditing(null)}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        ))}
        {users.length === 0 && <div style={{ fontSize: 12.5, color: "var(--tx-3)", padding: "10px 0" }}>Loading users…</div>}
        {users.length > 0 && filtered.length === 0 && <div style={{ fontSize: 12.5, color: "var(--tx-3)", padding: "10px 0" }}>No users match "{q}"</div>}
      </div>

      {pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 12 }}>
          <button onClick={() => setPage(Math.max(1, cur - 1))} disabled={cur === 1}
            style={{ background: "none", border: "none", color: cur === 1 ? "var(--tx-faint)" : "var(--tx-2)", fontSize: 12.5, fontWeight: 600, cursor: cur === 1 ? "default" : "pointer" }}>‹ Previous</button>
          {Array.from({ length: pages }, (_, i) => i + 1)
            .filter(p => p === 1 || p === pages || Math.abs(p - cur) <= 1)
            .map((p, idx, arr) => (
              <span key={p} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {idx > 0 && arr[idx - 1] !== p - 1 && <span style={{ color: "var(--tx-3)" }}>…</span>}
                <button onClick={() => setPage(p)}
                  style={{ minWidth: 30, height: 30, borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                    border: cur === p ? "1px solid var(--violet)" : "1px solid var(--line)",
                    background: cur === p ? "rgba(124,58,237,0.12)" : "transparent",
                    color: cur === p ? "var(--violet)" : "var(--tx-2)" }}>{p}</button>
              </span>
            ))}
          <button onClick={() => setPage(Math.min(pages, cur + 1))} disabled={cur === pages}
            style={{ background: "none", border: "none", color: cur === pages ? "var(--tx-faint)" : "var(--tx-2)", fontSize: 12.5, fontWeight: 600, cursor: cur === pages ? "default" : "pointer" }}>Next ›</button>
        </div>
      )}
    </section>
  );
}

// ── SVG icon helper ───────────────────────────────────────────────────────────
function Ic({ d, size = 16, color }: { d: string; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0 }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}
const I = {
  target:   '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  sparkles: '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/>',
  bell:     '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  clock:    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check:    '<path d="M20 6 9 17l-5-5"/>',
  x:        '<path d="M18 6 6 18M6 6l12 12"/>',
  enter:    '<path d="M9 10l-5 5 5 5"/><path d="M4 15h12a4 4 0 0 0 4-4V4"/>',
  skip:     '<path d="M5 4l10 8-10 8z"/><path d="M19 5v14"/>',
  eye:      '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff:   '<path d="M17.9 17.9A10 10 0 0 1 2 12 10 10 0 0 1 12 2"/><path d="M3 3l18 18"/><path d="M9.9 4.2A10 10 0 0 1 22 12a10 10 0 0 1-1.2 4.8"/>',
};

// ── Toggle ────────────────────────────────────────────────────────────────────
function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button className={`toggle${on ? " on" : ""}`} onClick={onClick}>
      <span className="toggle-knob" />
    </button>
  );
}



const AI_PROVIDERS: Record<string, { models: {id: string, name: string}[]; keyUrl: string }> = {
  "OpenRouter":  { 
    models: [
      { id: "anthropic/claude-sonnet-4.6", name: "Claude 4.6 Sonnet (Best + Recommended)" },
      { id: "anthropic/claude-opus-4-8", name: "Claude 4.8 Opus (Balanced)" },
      { id: "anthropic/claude-haiku-4.5", name: "Claude 4.5 Haiku" },
      { id: "openai/gpt-5", name: "GPT-5" },
      { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash" },
      { id: "google/gemini-2.5-flash-lite", name: "Gemini 2.5 Lite" }
    ], 
    keyUrl: "openrouter.ai/keys" 
  },
  "Nvidia NIM":  { models: [{id: "nvidia/llama-3.1-nemotron-70b", name: "Llama 3.1 Nemotron 70B"}], keyUrl: "build.nvidia.com" },
  "Anthropic":   { models: [{id: "claude-3-5-sonnet-latest", name: "Claude 3.5 Sonnet"}], keyUrl: "console.anthropic.com/settings/keys" },
};

const CRON_PRESETS: Record<string, string> = {
  "0 * * * *":   "Every 1 hour",
  "0 */6 * * *": "Every 6 hours",
  "0 9 * * *":   "Every day at 9:00 AM",
  "0 9 * * 1":   "Every Monday at 9:00 AM",
};

export function Settings({ onToast }: { onToast?: (m: string, t?: any) => void }) {
  const toast = onToast || ((m: string) => console.log(m));


  const [visaFilter, setVisaFilter] = useState(false);
  const [expFilter, setExpFilter]   = useState(false);

  const [provider, setProvider] = useState("OpenRouter");
  const [modelParse, setModelParse] = useState("google/gemini-2.5-flash-lite");
  const [modelTailor, setModelTailor] = useState("anthropic/claude-sonnet-4.6");
  const [modelQualify, setModelQualify] = useState("anthropic/claude-sonnet-4.6");
  const [modelCoverLetter, setModelCoverLetter] = useState("anthropic/claude-sonnet-4.6");
  const [apiKey, setApiKey]     = useState("");
  const [joboApiKey, setJoboApiKey] = useState("");
  const [showKey, setShowKey]   = useState(false);

  const [botToken, setBotToken]   = useState("");
  const [chatId, setChatId]       = useState("");
  const [showToken, setShowToken] = useState(false);
  const [testState, setTestState] = useState<null | "loading" | "ok" | "fail">(null);

  const [cron, setCron]       = useState("0 * * * *");
  const [scraping, setScraping] = useState(false);
  const [jdFix, setJdFix] = useState<{ running: boolean; total: number; done: number; fixed: number; failed: number } | null>(null);
  const [qualHealth, setQualHealth] = useState<{ admin_settings_found: boolean; api_key_set: boolean; profile_set: boolean; qualify_model: string | null; scored_jobs: number; pending_jobs: number; running: boolean } | null>(null);

  useEffect(() => {
    api.getSettings().then((s: any) => {
      if (!s) return;
      setVisaFilter(!!s.visa_filter);
      setExpFilter(!!s.level_filter);
      setProvider(s.ai_provider || "OpenRouter");
      setModelParse(s.ai_model_parse || "google/gemini-2.5-flash-lite");
      setModelTailor(s.ai_model_tailor || "anthropic/claude-sonnet-4.6");
      setModelQualify(s.ai_model_qualify || "anthropic/claude-sonnet-4.6");
      setModelCoverLetter(s.ai_model_cover_letter || "anthropic/claude-sonnet-4.6");
      setApiKey(s.ai_api_key || "");
      setJoboApiKey(s.jobo_api_key || "");
      setBotToken(s.telegram_bot_token || "");
      setChatId(s.telegram_chat_id || "");
      setCron(s.auto_scrape_cron || "0 * * * *");
    }).catch(() => {});
    api.qualifyHealth().then(setQualHealth).catch(() => {});
  }, []);

  const saveSettings = async () => {
    try {
      await api.saveSettings({
        visa_filter: visaFilter, level_filter: expFilter,
        ai_provider: provider, ai_api_key: apiKey,
        jobo_api_key: joboApiKey,
        ai_model_parse: modelParse, ai_model_tailor: modelTailor,
        ai_model_qualify: modelQualify, ai_model_cover_letter: modelCoverLetter,
        telegram_bot_token: botToken, telegram_chat_id: chatId,
        auto_scrape_cron: cron,

      } as any);
      toast("Settings saved", "success");
    } catch { toast("Save failed", "error"); }
  };

  const testTelegram = async () => {
    setTestState("loading");
    try {
      await (api as any).testTelegram(botToken, chatId);
      setTestState("ok");
      toast("Test message sent to Telegram", "success");
    } catch {
      setTestState("fail");
      toast("Telegram test failed — check token & chat ID", "error");
    }
  };

  const runNow = async () => {
    if (scraping) return;
    setScraping(true);
    toast("Manual scrape started", "info" as any);
    try { await (api as any).runScraperNow(); toast("+jobs found", "success"); }
    catch { toast("Scrape failed", "error"); }
    finally { setScraping(false); }
  };

  const runJdFix = async () => {
    if (jdFix?.running) return;
    try {
      await api.fixDescriptions();
      toast("JD cleanup started", "info" as any);
      setJdFix({ running: true, total: 0, done: 0, fixed: 0, failed: 0 });
      const poll = setInterval(async () => {
        try {
          const s = await api.fixDescriptionsStatus();
          setJdFix(s);
          if (!s.running) {
            clearInterval(poll);
            toast(`JD cleanup done — ${s.fixed} fixed, ${s.failed} failed of ${s.total}`, "success");
          }
        } catch { clearInterval(poll); }
      }, 3000);
    } catch (e: any) { toast(e.message, "error"); }
  };

  const cronDesc = CRON_PRESETS[cron] || "Custom schedule";

  return (
    <div className="form-scroll">
      <div className="form-inner">
        <div className="form-head">
          <div>
            <h1 className="dash-title">Settings</h1>
            <p className="dash-sub">Targeting, AI, notifications and scheduling</p>
          </div>
          <button className="save-btn" onClick={saveSettings}>
            <Ic d={I.check} size={15} /> Save Settings
          </button>
        </div>

        {/* User approval & role assignment (admin page) */}
        <UsersPanel onToast={toast} onChanged={() => {}} />

        {/* AI Configuration */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.sparkles} size={16} /> AI Configuration</div>
          <label className="field">
            <span className="field-label">Provider</span>
            <div className="seg-tabs">
              {Object.keys(AI_PROVIDERS).map(p => (
                <button key={p} className={provider === p ? "on" : ""}
                  onClick={() => setProvider(p)}>{p}</button>
              ))}
            </div>
          </label>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">API Key</span>
              <div className="input-reveal">
                <input type={showKey ? "text" : "password"} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-…" />
                <button onClick={() => setShowKey(s => !s)}>{showKey ? "Hide" : "Show"}</button>
              </div>
              <a className="field-link" href={`https://${AI_PROVIDERS[provider]?.keyUrl}`} target="_blank" rel="noreferrer">
                Get your API key →
              </a>
            </label>
          </div>
          <div className="field-grid" style={{ marginTop: 12 }}>
            <label className="field">
              <span className="field-label">Resume Parsing Model</span>
              <select value={modelParse} onChange={e => setModelParse(e.target.value)}>
                {provider === "OpenRouter" ? (
                  <>
                    <option value="google/gemini-2.5-flash-lite">Gemini 2.5 Lite (Best + Recommended)</option>
                  </>
                ) : (
                  AI_PROVIDERS[provider]?.models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)
                )}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Tailoring Model</span>
              <select value={modelTailor} onChange={e => setModelTailor(e.target.value)}>
                {AI_PROVIDERS[provider]?.models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Job Qualification Model</span>
              <select value={modelQualify} onChange={e => setModelQualify(e.target.value)}>
                {AI_PROVIDERS[provider]?.models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Cover Letter Model</span>
              <select value={modelCoverLetter} onChange={e => setModelCoverLetter(e.target.value)}>
                {AI_PROVIDERS[provider]?.models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          </div>
        </section>

        {/* Telegram */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.bell} size={16} /> Telegram Notifications</div>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">Bot Token</span>
              <div className="input-reveal">
                <input type={showToken ? "text" : "password"} value={botToken} onChange={e => setBotToken(e.target.value)} placeholder="123456:ABC-DEF…" />
                <button onClick={async () => {
                  // Field holds the mask — fetch the real token (admin-only) on reveal
                  if (!showToken && botToken.includes("•")) {
                    try { const r = await api.revealTelegramToken(); if (r.token) setBotToken(r.token); } catch {}
                  }
                  setShowToken(s => !s);
                }}>{showToken ? "Hide" : "Show"}</button>
              </div>
            </label>
            <label className="field">
              <span className="field-label">Chat ID</span>
              <input type="text" value={chatId} onChange={e => setChatId(e.target.value)} placeholder="-1001234567890" />
            </label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
            <button className="act ai" onClick={testTelegram} disabled={testState === "loading"}>
              {testState === "loading" ? <span className="mini-spin" /> : <Ic d={I.enter} size={14} />}
              Send
            </button>
            {testState === "ok"   && <span className="test-res ok"><Ic d={I.check} size={13} /> Delivered</span>}
            {testState === "fail" && <span className="test-res fail"><Ic d={I.x} size={13} /> Failed</span>}
          </div>
        </section>

        {/* Scheduler */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.clock} size={16} /> Auto-Scrape Scheduler</div>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">Cron Expression</span>
              <input type="text" value={cron} onChange={e => setCron(e.target.value)} style={{ fontFamily: "var(--f-mono)" }} placeholder="0 * * * *" />
            </label>
            <div className="field">
              <span className="field-label">Schedule</span>
              <div className="cron-info">
                <span className="cron-desc">{cronDesc}</span>
                <span className="cron-next">Next run <b>soon</b></span>
              </div>
            </div>
          </div>
          <div className="cron-presets">
            {Object.entries(CRON_PRESETS).map(([c, d]) => (
              <button key={c} className={`cron-chip${cron === c ? " on" : ""}`} onClick={() => setCron(c)}>{d}</button>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
            <button className="act" onClick={saveSettings}><Ic d={I.check} size={14} /> Update Schedule</button>
            <button className={`act primary${scraping ? " running" : ""}`} onClick={runNow} style={scraping ? { animation: "pulseBtn 1.4s ease-in-out infinite" } : {}}>
              <Ic d={I.skip} size={14} /> {scraping ? "Running…" : "Run Now"}
            </button>
            <button className="act fail" style={{ color: "var(--tx-error)", borderColor: "var(--tx-error)" }} onClick={async () => {
              if (!confirm("Delete ALL jobs? Cannot be undone.")) return;
              try { const r = await api.clearAllJobs(); toast("Cleared " + r.deleted + " jobs", "success"); setTimeout(() => window.location.reload(), 1500); }
              catch (e: any) { toast(e.message, "error"); }
            }}>
              <Ic d={I.x} size={14} /> Clear All Jobs
            </button>
            <button className="act" onClick={runJdFix} disabled={!!jdFix?.running}>
              <Ic d={I.check} size={14} /> {jdFix?.running ? `Fixing JDs… ${jdFix.done}/${jdFix.total || "?"}` : "Fix Broken JDs"}
            </button>
            {scraping && <span className="test-res" style={{ color: "var(--tx-3)" }}><span className="mini-spin" /> scraping sources…</span>}
          </div>

          {/* Auto-qualify health */}
          {qualHealth && (
            <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 10, background: "var(--bg-elevated)", border: "1px solid var(--line)", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", fontSize: 12.5 }}>
              <span style={{ fontWeight: 700, color: "var(--tx)" }}>Auto-Qualify</span>
              <span style={{ color: qualHealth.api_key_set ? "#16a34a" : "#dc2626", fontWeight: 600 }}>
                {qualHealth.api_key_set ? "✓ API key" : "✗ API key missing"}
              </span>
              <span style={{ color: qualHealth.profile_set ? "#16a34a" : "#dc2626", fontWeight: 600 }}>
                {qualHealth.profile_set ? "✓ Profile" : "✗ Profile missing"}
              </span>
              <span style={{ color: "var(--tx-2)" }}>Scored: <b>{qualHealth.scored_jobs}</b></span>
              <span style={{ color: "var(--tx-2)" }}>Pending: <b>{qualHealth.pending_jobs}</b></span>
              {qualHealth.running && <span style={{ color: "var(--violet)", fontWeight: 600 }}>running…</span>}
              <button className="act" style={{ height: 26, fontSize: 11.5 }}
                disabled={qualHealth.running || !qualHealth.api_key_set || !qualHealth.profile_set}
                onClick={async () => {
                  try { await api.qualifyAll(); toast("Qualify started in background", "success"); }
                  catch (e: any) { toast(e.message, "error"); }
                }}>
                Run Qualify Now
              </button>
            </div>
          )}
        </section>

        <div className="form-foot">
          <button className="save-btn" onClick={saveSettings}>
            <Ic d={I.check} size={15} /> Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
