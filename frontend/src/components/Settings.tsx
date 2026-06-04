import { useState, useEffect } from "react";
import { api } from "../api";
import type { Settings as SettingsType } from "../types";
import { Save, Loader2, Eye, EyeOff, CheckCircle2, Send, BotMessageSquare } from "lucide-react";

const PROVIDERS = [
  {
    value: "openrouter",
    label: "OpenRouter",
    url: "https://openrouter.ai/keys",
    placeholder: "sk-or-...",
    hint: "One key → Claude, Gemini, Llama, DeepSeek. Free models available.",
    models: [
      "anthropic/claude-sonnet-4-5",
      "anthropic/claude-3-haiku",
      "google/gemini-flash-1.5",
      "meta-llama/llama-3.3-70b-instruct",
      "mistralai/mistral-7b-instruct:free",
      "deepseek/deepseek-chat",
    ],
  },
  {
    value: "nvidia",
    label: "Nvidia NIM",
    url: "https://integrate.api.nvidia.com",
    placeholder: "nvapi-...",
    hint: "Nvidia-hosted models. High quality, free tier available.",
    models: [
      "nvidia/llama-3.1-nemotron-70b-instruct",
      "meta/llama-3.1-70b-instruct",
      "mistralai/mistral-large",
    ],
  },
  {
    value: "anthropic",
    label: "Anthropic",
    url: "https://console.anthropic.com/settings/keys",
    placeholder: "sk-ant-...",
    hint: "Direct Claude API. Best quality, paid only.",
    models: [
      "claude-sonnet-4-6",
      "claude-haiku-4-5-20251001",
      "claude-opus-4-7",
    ],
  },
];

export function Settings() {
  const [form, setForm] = useState<SettingsType>({
    resume: "", ai_provider: "openrouter", ai_api_key: "",
    ai_model: "anthropic/claude-sonnet-4-5",
    adzuna_app_id: "", adzuna_app_key: "", jobo_api_key: "",
  });
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [saved, setSaved]       = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [tgToken,   setTgToken]   = useState("");
  const [tgChatId,  setTgChatId]  = useState("");
  const [tgTesting, setTgTesting] = useState(false);
  const [tgStatus,  setTgStatus]  = useState<{ok:boolean;msg:string}|null>(null);
  const [tgConfigured, setTgConfigured] = useState(false);
  const [showTgToken, setShowTgToken] = useState(false);
  const [cronExpr, setCronExpr] = useState("0 * * * *");
  const [cronMsg, setCronMsg]   = useState("");
  const [scraping, setScraping] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<string>("");
  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);
  // Change password
  const [pwCurrent, setPwCurrent]   = useState("");
  const [pwNew, setPwNew]           = useState("");
  const [pwConfirm, setPwConfirm]   = useState("");
  const [pwSaving, setPwSaving]     = useState(false);
  const [pwMsg, setPwMsg]           = useState<{ok: boolean; text: string} | null>(null);

  useEffect(() => {
    api.getSettings().then(data => {
      setForm(data);
      if ((data as any).auto_scrape_cron) setCronExpr((data as any).auto_scrape_cron);
      setTgConfigured(!!(data as any).telegram_configured);
      if ((data as any).telegram_chat_id) setTgChatId((data as any).telegram_chat_id);
      setLoading(false);
    });
    api.getSchedulerStatus().then(setSchedulerStatus).catch(() => {});
  }, []);

  const handleRunNow = async () => {
    setScraping(true); setScrapeResult("");
    try {
      await api.runScraperNow();
      setScrapeResult("✅ Scraper triggered! Check Railway logs — takes 3–5 min.");
    } catch (e: any) {
      setScrapeResult(`❌ ${e.message}`);
    } finally {
      setScraping(false);
    }
  };

  const handleTgTest = async () => {
    if (!tgToken || !tgChatId) { setTgStatus({ok:false, msg:"Enter both token and chat ID first"}); return; }
    setTgTesting(true); setTgStatus(null);
    try {
      const res = await api.testTelegram(tgToken, tgChatId);
      setTgStatus({ok: res.ok, msg: res.message});
      if (res.ok) setTgConfigured(true);
    } catch(e: any) {
      setTgStatus({ok: false, msg: e.message});
    } finally {
      setTgTesting(false);
    }
  };


  const handleSave = async () => {
    setSaving(true); setSaved(false);
    try {
      await api.saveSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };

  const handleCronSave = async () => {
    setCronMsg("");
    try {
      await api.updateSchedulerCron(cronExpr);
      setCronMsg("✓ Updated");
      api.getSchedulerStatus().then(setSchedulerStatus).catch(() => {});
    } catch (e: any) { setCronMsg(e.message); }
  };

  if (loading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height: 160, color: "var(--tx-3)", fontSize: 14, gap: 8 }}>
      <Loader2 size={18} className="animate-spin" /> Loading…
    </div>
  );

  const activeP = PROVIDERS.find(p => p.value === form.ai_provider) ?? PROVIDERS[0];

  return (
    <div style={{ overflowY: "auto", padding: "24px", flex: 1 }}>
      <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 0 }}>

      {/* ── Security — Change Password ── */}
      <section style={{ background: "var(--glass-hi,rgba(255,255,255,0.04))", border: "1px solid var(--glass-border,rgba(255,255,255,0.08))", borderRadius: 16, padding: "24px 28px", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <span style={{ fontSize: 18 }}>🔐</span>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--tx)" }}>Security</div>
            <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 1 }}>Change your account password</div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div style={{ gridColumn: "1/-1" }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)", display: "block", marginBottom: 5 }}>Current Password</label>
            <input type="password" value={pwCurrent} onChange={e => setPwCurrent(e.target.value)} placeholder="Your current password"
              style={{ width: "100%", height: 40, border: "1.5px solid var(--glass-border)", borderRadius: 9, padding: "0 12px", fontSize: 13, outline: "none", background: "var(--surface)", boxSizing: "border-box", fontFamily: "inherit", color: "var(--tx)" }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)", display: "block", marginBottom: 5 }}>New Password</label>
            <input type="password" value={pwNew} onChange={e => setPwNew(e.target.value)} placeholder="Min 8 characters"
              style={{ width: "100%", height: 40, border: "1.5px solid var(--glass-border)", borderRadius: 9, padding: "0 12px", fontSize: 13, outline: "none", background: "var(--surface)", boxSizing: "border-box", fontFamily: "inherit", color: "var(--tx)" }} />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)", display: "block", marginBottom: 5 }}>Confirm New Password</label>
            <input type="password" value={pwConfirm} onChange={e => setPwConfirm(e.target.value)} placeholder="Repeat new password"
              style={{ width: "100%", height: 40, border: "1.5px solid var(--glass-border)", borderRadius: 9, padding: "0 12px", fontSize: 13, outline: "none", background: "var(--surface)", boxSizing: "border-box", fontFamily: "inherit", color: "var(--tx)" }} />
          </div>
        </div>
        {pwMsg && (
          <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 9, fontSize: 13, fontWeight: 500,
            background: pwMsg.ok ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
            color: pwMsg.ok ? "#16a34a" : "#dc2626",
            border: `1px solid ${pwMsg.ok ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}` }}>
            {pwMsg.ok ? "✅" : "⚠️"} {pwMsg.text}
          </div>
        )}
        <button disabled={pwSaving} onClick={async () => {
          setPwMsg(null);
          if (!pwCurrent) { setPwMsg({ok:false, text:"Enter your current password"}); return; }
          if (pwNew.length < 8) { setPwMsg({ok:false, text:"New password must be at least 8 characters"}); return; }
          if (pwNew !== pwConfirm) { setPwMsg({ok:false, text:"New passwords don't match"}); return; }
          setPwSaving(true);
          try {
            await api.auth.changePassword(pwCurrent, pwNew);
            setPwMsg({ok:true, text:"Password changed successfully!"});
            setPwCurrent(""); setPwNew(""); setPwConfirm("");
          } catch(e:any) { setPwMsg({ok:false, text: e.message || "Failed to change password"}); }
          finally { setPwSaving(false); }
        }} style={{ marginTop: 16, height: 40, padding: "0 20px", borderRadius: 9, border: "none",
          background: "var(--grad)", color: "#fff", fontSize: 13, fontWeight: 700,
          cursor: pwSaving ? "not-allowed" : "pointer", opacity: pwSaving ? 0.7 : 1,
          boxShadow: "0 4px 14px -4px var(--violet-glow)" }}>
          {pwSaving ? "Saving…" : "Update Password"}
        </button>
      </section>

      {/* Header + Save */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h2 style={{ fontFamily: "var(--f-display)", fontSize: 18, fontWeight: 700, color: "var(--tx)", margin: 0, letterSpacing: "-0.02em" }}>Settings</h2>
          <p style={{ fontSize: 13, color: "var(--tx-3)", marginTop: 4, marginBottom: 0 }}>AI provider · job sources · schedule</p>
        </div>
        <button onClick={handleSave} disabled={saving}
          style={{
            display:"inline-flex", alignItems:"center", gap:7,
            height:36, padding:"0 20px",
            borderRadius:"var(--r-sm)",
            background: saving ? "rgba(124,58,237,0.5)" : "var(--grad)",
            color:"#fff", fontSize:13, fontWeight:600, border:"none",
            opacity: saving ? 0.7 : 1, cursor: saving ? "not-allowed" : "pointer",
            boxShadow: saving ? "none" : "0 4px 14px -4px var(--violet-glow)",
            transition: "all .14s",
          }}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>

      {/* AI Providers */}
      <section style={{
        background: "var(--bg-surface)", border: "1px solid var(--line)",
        borderRadius: "var(--r-lg)", padding: 20, marginBottom: 16,
      }}>
        <h3 style={{ fontFamily: "var(--f-display)", fontSize: 14, fontWeight: 600, color: "var(--tx)", marginBottom: 6, marginTop: 0 }}>AI Provider</h3>
        <p style={{ fontSize: 12.5, color: "var(--tx-3)", marginBottom: 14, marginTop: 0 }}>Select which provider to use. Enter its API key. Only one is active at a time.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {PROVIDERS.map(p => {
            const isActive = form.ai_provider === p.value;
            return (
            <div key={p.value}
                style={{
                  border: `1px solid ${isActive ? "var(--violet)" : "var(--line)"}`,
                  borderRadius: "var(--r-sm)",
                  padding: 14, transition: "all .13s", cursor: "pointer",
                  background: isActive ? "rgba(124,58,237,0.08)" : "var(--bg-elevated)",
                }}
                onClick={() => setForm(f => ({ ...f, ai_provider: p.value, ai_model: p.models[0] }))}
            >
                {/* Row 1: radio + name + hint */}
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center`}
                    style={{borderColor: isActive ? 'var(--accent)' : 'var(--border-default)'}}>
                    {isActive && <div className="w-2 h-2 rounded-full" style={{background:'var(--accent)'}} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold" style={{color:'var(--text-primary)'}}>{p.label}</span>
                      <a href={p.url} target="_blank" rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="text-[10px] hover:underline" style={{color:'var(--accent)'}}>Get key →</a>
                    </div>
                    <p className="text-xs mt-0.5" style={{color:'var(--text-muted)'}}>{p.hint}</p>
                  </div>
                </div>

                {/* Row 2: API key + model (only when active) */}
                {isActive && (
                  <div className="mt-3 space-y-2 pl-7" onClick={e => e.stopPropagation()}>
                    {/* API Key */}
                    <div className="relative">
                      <input
                        type={showKeys[p.value] ? "text" : "password"}
                        value={form.ai_api_key}
                        onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))}
                        placeholder={p.placeholder}
                        className="field"
                        style={{width:'100%'}}
                      />
                      <button
                        onClick={() => setShowKeys(s => ({ ...s, [p.value]: !s[p.value] }))}
                        className="absolute right-2.5 top-2.5"
                        style={{color:'var(--text-muted)'}}
                      >
                        {showKeys[p.value] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    {/* Model selector */}
                    <div className="flex gap-2 items-center">
                      <select
                        value={form.ai_model}
                        onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
                        className="field"
                        style={{flex:1}}
                      >
                        {p.models.map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                      <input
                        type="text"
                        value={form.ai_model}
                        onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
                        placeholder="or type custom model ID"
                        className="field"
                        style={{flex:1}}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>


      {/* ── Telegram Notifications ───────────────────────────────────── */}
      <section style={{
        background: "var(--bg-surface)", border: "1px solid var(--line)",
        borderRadius: "var(--r-lg)", padding: 20, marginBottom: 16,
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <BotMessageSquare size={15} style={{color:'#2CA5E0'}} />
            <h3 style={{ fontFamily: "var(--f-display)", fontSize: 14, fontWeight: 600, color: "var(--tx)", margin: 0 }}>Telegram Notifications</h3>
          </div>
          {tgConfigured && (
            <span className="flex items-center gap-1 text-[10px] font-semibold px-2.5 py-1 rounded-full"
              style={{background:'rgba(52,211,153,0.12)', border:'1px solid rgba(52,211,153,0.3)', color:'#34d399'}}>
              <CheckCircle2 size={10}/> Connected
            </span>
          )}
        </div>

        {/* Setup steps */}
        <div className="rounded-xl p-4 space-y-3" style={{background:'var(--bg-elevated)', border:'1px solid var(--border-default)'}}>
          <p className="text-[11px] font-semibold uppercase tracking-wider" style={{color:'var(--text-muted)'}}>Setup — 2 steps</p>
          {[
            { n:1, text: <>Search <code style={{background:'var(--bg-surface)',padding:'1px 5px',borderRadius:4}}>@BotFather</code> on Telegram → send <code style={{background:'var(--bg-surface)',padding:'1px 5px',borderRadius:4}}>/newbot</code> → copy the <strong>token</strong></> },
            { n:2, text: <>Search <code style={{background:'var(--bg-surface)',padding:'1px 5px',borderRadius:4}}>@userinfobot</code> → send any message → copy your <strong>Chat ID</strong></> },
          ].map(s => (
            <div key={s.n} className="flex items-start gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                style={{background:'rgba(42,165,224,0.15)', border:'1px solid rgba(42,165,224,0.3)', color:'#2CA5E0'}}>
                {s.n}
              </span>
              <p className="text-xs leading-relaxed" style={{color:'var(--text-secondary)'}}>{s.text}</p>
            </div>
          ))}
        </div>

        {/* Inputs */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12, marginTop: 12 }}>
          <div>
            <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: "var(--tx-2)", marginBottom: 6 }}>Bot Token</label>
            <div style={{ position: "relative" }}>
              <input
                type={showTgToken ? "text" : "password"}
                value={tgToken}
                onChange={e => setTgToken(e.target.value)}
                placeholder={tgConfigured ? "••••••• (saved)" : "1234567890:ABCDEFabcdef..."}
                className="field"
                style={{width:'100%', paddingRight:36}}
              />
              <button onClick={() => setShowTgToken(s => !s)}
                style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: "var(--tx-3)" }}>
                {showTgToken ? <EyeOff size={14}/> : <Eye size={14}/>}
              </button>
            </div>
          </div>
          <div>
            <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: "var(--tx-2)", marginBottom: 6 }}>Chat ID</label>
            <input type="text" value={tgChatId} onChange={e => setTgChatId(e.target.value)}
              placeholder="123456789" className="field" style={{width:'100%'}} />
          </div>
        </div>

        {/* Test button + status */}
        <div className="flex items-center gap-3">
          <button onClick={handleTgTest} disabled={tgTesting}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: tgConfigured ? 'rgba(52,211,153,0.12)' : 'rgba(42,165,224,0.12)',
              border: `1px solid ${tgConfigured ? 'rgba(52,211,153,0.35)' : 'rgba(42,165,224,0.35)'}`,
              color: tgConfigured ? '#34d399' : '#2CA5E0',
              opacity: tgTesting ? 0.7 : 1,
            }}>
            {tgTesting
              ? <><Loader2 size={13} className="animate-spin"/> Testing…</>
              : <><Send size={13}/> {tgConfigured ? "Re-test" : "Test & Connect"}</>}
          </button>
          {tgStatus && (
            <span className="text-xs font-medium flex items-center gap-1.5"
              style={{color: tgStatus.ok ? '#34d399' : '#f87171'}}>
              {tgStatus.ok ? <CheckCircle2 size={12}/> : '⚠️'} {tgStatus.msg}
            </span>
          )}
        </div>
      </section>

      {/* ── Schedule ─────────────────────────────────────────────────── */}
      <section style={{
        background: "var(--bg-surface)", border: "1px solid var(--line)",
        borderRadius: "var(--r-lg)", padding: 20, marginBottom: 16,
      }}>
        <h3 style={{ fontFamily: "var(--f-display)", fontSize: 14, fontWeight: 600, color: "var(--tx)", marginBottom: 14, marginTop: 0 }}>Auto-Scrape Schedule</h3>
        {schedulerStatus && (
          <div className="flex items-center gap-2 text-xs mb-3">
            <span className={`w-1.5 h-1.5 rounded-full ${schedulerStatus.running ? "bg-green-400" : "bg-red-400"}`} />
            <span className="text-slate-400">{schedulerStatus.running ? "Running" : "Stopped"}</span>
            {schedulerStatus.jobs?.[0]?.next_run && (
              <span className="text-slate-500">· Next: {new Date(schedulerStatus.jobs[0].next_run).toLocaleString()}</span>
            )}
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            placeholder="0 * * * *"
            className="field"
            style={{flex:1, fontFamily:'var(--f-mono)'}}
          />
          <button onClick={handleCronSave}
            style={{
              height: 38, padding: "0 16px",
              borderRadius: "var(--r-sm)", fontSize: 13, fontWeight: 500,
              background: "var(--bg-elevated)", border: "1px solid var(--line)",
              color: "var(--tx-2)", cursor: "pointer", transition: "all .13s", whiteSpace: "nowrap",
            }}>
            Update
          </button>
          <button onClick={handleRunNow} disabled={scraping}
            style={{
              height: 38, padding: "0 16px",
              borderRadius: "var(--r-sm)", fontSize: 13, fontWeight: 600,
              background: "var(--grad)", color: "#fff", border: "none",
              opacity: scraping ? 0.7 : 1, cursor: scraping ? "wait" : "pointer",
              boxShadow: "0 4px 14px -4px var(--violet-glow)", whiteSpace: "nowrap",
              transition: "all .13s",
            }}>
            {scraping ? <><Loader2 size={13} className="animate-spin inline mr-1"/>Running…</> : '▶ Run Now'}
          </button>
        </div>
        {cronMsg && <p className="text-xs text-green-400">{cronMsg}</p>}
        {scrapeResult && <p className="text-xs" style={{color: scrapeResult.startsWith('✅') ? '#34d399' : '#f87171'}}>{scrapeResult}</p>}
        <p className="text-[11px]" style={{color:'var(--text-muted)'}}>
          <code>0 * * * *</code> = every 1h · <code>0 */6 * * *</code> = every 6h · <code>0 8 * * *</code> = daily 8am
        </p>
      </section>
      </div>
    </div>
  );
}
