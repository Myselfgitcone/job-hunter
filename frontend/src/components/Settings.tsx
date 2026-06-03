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

  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);

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
    <div className="flex items-center justify-center h-40 text-slate-500 text-sm">
      <Loader2 size={18} className="animate-spin mr-2" /> Loading…
    </div>
  );

  const activeP = PROVIDERS.find(p => p.value === form.ai_provider) ?? PROVIDERS[0];

  return (
    <div className="max-w-4xl space-y-8 p-8">
      {/* Header + Save */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold" style={{color:'var(--text-primary)'}}>Settings</h2>
          <p className="text-sm mt-0.5" style={{color:'var(--text-muted)'}}>AI provider · job sources · schedule</p>
        </div>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-all"
          style={{background:'var(--accent)',color:'#fff',opacity:saving?0.6:1}}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>

      {/* AI Providers — all in one */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider" style={{color:'var(--text-muted)'}}>AI Provider</h3>
        <p className="text-xs" style={{color:'var(--text-muted)'}}>Select which provider to use. Enter its API key. Only one is active at a time.</p>
        <div className="space-y-2">
          {PROVIDERS.map(p => {
            const isActive = form.ai_provider === p.value;
            return (
            <div key={p.value}
                className="border rounded-xl p-4 transition-all cursor-pointer"
                style={{
                  borderColor: isActive ? 'var(--accent)' : 'var(--border-default)',
                  background: isActive ? 'var(--bg-selected)' : 'var(--bg-elevated)',
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
                        style={{flex:1}}
                      >
                        {p.models.map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                      <input
                        type="text"
                        value={form.ai_model}
                        onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
                        placeholder="or type custom model ID"
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
      <section className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BotMessageSquare size={15} style={{color:'#2CA5E0'}} />
            <h3 className="text-xs font-semibold uppercase tracking-wider" style={{color:'var(--text-muted)'}}>Telegram Notifications</h3>
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
        <div className="grid gap-3" style={{gridTemplateColumns:'1fr 1fr'}}>
          <div>
            <label className="block text-[11px] font-medium mb-1.5" style={{color:'var(--text-muted)'}}>Bot Token</label>
            <div className="relative">
              <input
                type={showTgToken ? "text" : "password"}
                value={tgToken}
                onChange={e => setTgToken(e.target.value)}
                placeholder={tgConfigured ? "••••••• (saved)" : "1234567890:ABCDEFabcdef..."}
                style={{width:'100%', paddingRight:36}}
              />
              <button onClick={() => setShowTgToken(s => !s)}
                className="absolute right-2.5 top-2.5" style={{color:'var(--text-muted)'}}>
                {showTgToken ? <EyeOff size={14}/> : <Eye size={14}/>}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-medium mb-1.5" style={{color:'var(--text-muted)'}}>Chat ID</label>
            <input type="text" value={tgChatId} onChange={e => setTgChatId(e.target.value)}
              placeholder="123456789" style={{width:'100%'}} />
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

        {/* Alert types */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px]" style={{color:'var(--text-muted)'}}>Alerts:</span>
          {['New jobs scraped', 'Job → Interview', 'Daily summary (8am)'].map(a => (
            <span key={a} className="text-[10px] px-2 py-0.5 rounded-full"
              style={{background:'var(--bg-elevated)', border:'1px solid var(--border-subtle)', color:'var(--text-secondary)'}}>
              {a}
            </span>
          ))}
        </div>
      </section>

      {/* ── Schedule ─────────────────────────────────────────────────── */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider" style={{color:'var(--text-muted)'}}>Auto-Scrape Schedule</h3>
        {schedulerStatus && (
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-1.5 h-1.5 rounded-full ${schedulerStatus.running ? "bg-green-400" : "bg-red-400"}`} />
            <span className="text-slate-400">{schedulerStatus.running ? "Running" : "Stopped"}</span>
            {schedulerStatus.jobs?.[0]?.next_run && (
              <span className="text-slate-500">· Next: {new Date(schedulerStatus.jobs[0].next_run).toLocaleString()}</span>
            )}
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            placeholder="0 * * * *"
            style={{flex:1, fontFamily:'monospace'}}
          />
          <button onClick={handleCronSave}
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
            style={{background:'var(--bg-elevated)',border:'1px solid var(--border-default)',color:'var(--text-primary)'}}>
            Update
          </button>
        </div>
        {cronMsg && <p className="text-xs text-green-400">{cronMsg}</p>}
        <p className="text-[11px]" style={{color:'var(--text-muted)'}}>
          <code>0 * * * *</code> = every 1h · <code>0 */6 * * *</code> = every 6h · <code>0 8 * * *</code> = daily 8am
        </p>
      </section>
    </div>
  );
}
