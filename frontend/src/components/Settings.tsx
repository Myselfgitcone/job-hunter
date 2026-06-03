import { useState, useEffect } from "react";
import { api } from "../api";
import type { Settings as SettingsType } from "../types";
import { Save, Loader2, Eye, EyeOff, CheckCircle2 } from "lucide-react";

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
  const [cronExpr, setCronExpr] = useState("0 * * * *");
  const [cronMsg, setCronMsg]   = useState("");
  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);

  useEffect(() => {
    api.getSettings().then(data => {
      setForm(data);
      if ((data as any).auto_scrape_cron) setCronExpr((data as any).auto_scrape_cron);
      setLoading(false);
    });
    api.getSchedulerStatus().then(setSchedulerStatus).catch(() => {});
  }, []);

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


      {/* Schedule */}
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
