import { useState, useEffect } from "react";
import { api } from "../api";

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
                <button onClick={() => setShowToken(s => !s)}>{showToken ? "Hide" : "Show"}</button>
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
              Send Test Message
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
            {scraping && <span className="test-res" style={{ color: "var(--tx-3)" }}><span className="mini-spin" /> scraping sources…</span>}
          </div>
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
