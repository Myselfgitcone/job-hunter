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
    value: "groq",
    label: "Groq",
    url: "https://console.groq.com/keys",
    placeholder: "gsk_...",
    hint: "Fast inference, free tier. Best for quick tailoring.",
    models: [
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "mixtral-8x7b-32768",
      "gemma2-9b-it",
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
          <h2 className="text-lg font-semibold text-white">Settings</h2>
          <p className="text-sm text-slate-500 mt-0.5">AI provider · job sources · schedule</p>
        </div>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>

      {/* AI Providers — all in one */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">AI Provider</h3>
        <p className="text-xs text-slate-500">Select which provider to use. Enter its API key. Only one is active at a time.</p>
        <div className="space-y-2">
          {PROVIDERS.map(p => {
            const isActive = form.ai_provider === p.value;
            return (
              <div key={p.value}
                className={`border rounded-xl p-4 transition-all cursor-pointer ${
                  isActive
                    ? "border-blue-500/60 bg-blue-950/20"
                    : "border-slate-700/60 bg-slate-800/40 hover:border-slate-600"
                }`}
                onClick={() => setForm(f => ({ ...f, ai_provider: p.value, ai_model: p.models[0] }))}
              >
                {/* Row 1: radio + name + hint */}
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center ${
                    isActive ? "border-blue-400" : "border-slate-600"
                  }`}>
                    {isActive && <div className="w-2 h-2 rounded-full bg-blue-400" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-semibold ${isActive ? "text-white" : "text-slate-300"}`}>{p.label}</span>
                      <a href={p.url} target="_blank" rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="text-[10px] text-blue-400 hover:underline">Get key →</a>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{p.hint}</p>
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
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 pr-9 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => setShowKeys(s => ({ ...s, [p.value]: !s[p.value] }))}
                        className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                      >
                        {showKeys[p.value] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    {/* Model */}
                    <div className="flex gap-2">
                      <select
                        value={form.ai_model}
                        onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
                        className="flex-1 bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                      >
                        {p.models.map(m => <option key={m} value={m}>{m}</option>)}
                      </select>
                      <input
                        type="text"
                        value={form.ai_model}
                        onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
                        placeholder="custom model ID"
                        className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-blue-500"
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
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Auto-Scrape Schedule</h3>
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
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-blue-500"
            placeholder="0 * * * *"
          />
          <button onClick={handleCronSave}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-sm text-white rounded-lg transition-colors whitespace-nowrap">
            Update
          </button>
        </div>
        {cronMsg && <p className="text-xs text-green-400">{cronMsg}</p>}
        <p className="text-[11px] text-slate-600">
          <code>0 * * * *</code> = every 1h · <code>0 */6 * * *</code> = every 6h · <code>0 8 * * *</code> = daily 8am
        </p>
      </section>
    </div>
  );
}
