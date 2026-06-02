import { useState, useEffect } from "react";
import { api } from "../api";
import type { Settings as SettingsType } from "../types";
import { Save, Loader2, Eye, EyeOff } from "lucide-react";

const PROVIDERS = [
  { value: "openrouter", label: "OpenRouter", url: "https://openrouter.ai/keys", placeholder: "sk-or-..." },
  { value: "groq",       label: "Groq (free)", url: "https://console.groq.com/keys", placeholder: "gsk_..." },
  { value: "nvidia",     label: "Nvidia NIM",  url: "https://integrate.api.nvidia.com", placeholder: "nvapi-..." },
  { value: "anthropic",  label: "Anthropic (direct)", url: "https://console.anthropic.com/settings/keys", placeholder: "sk-ant-..." },
];

const MODELS: Record<string, string[]> = {
  openrouter: [
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-3-haiku",
    "google/gemini-flash-1.5",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct:free",
    "deepseek/deepseek-chat",
  ],
  groq: [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
  ],
  nvidia: [
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "meta/llama-3.1-70b-instruct",
    "mistralai/mistral-large",
  ],
  anthropic: [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-7",
  ],
};

export function Settings() {
  const [form, setForm] = useState<SettingsType>({
    resume: "",
    ai_provider: "openrouter",
    ai_api_key: "",
    ai_model: "anthropic/claude-sonnet-4-5",
    adzuna_app_id: "",
    adzuna_app_key: "",
    jobo_api_key: "",
  });
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [msg, setMsg]                 = useState("");
  const [showKey, setShowKey]         = useState(false);
  const [cronExpr, setCronExpr]       = useState("0 * * * *");
  const [cronMsg, setCronMsg]         = useState("");
  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);

  useEffect(() => {
    api.getSettings().then(data => {
      setForm(data);
      if ((data as any).auto_scrape_cron) setCronExpr((data as any).auto_scrape_cron);
      setLoading(false);
    });
    api.getSchedulerStatus().then(setSchedulerStatus).catch(() => {});
  }, []);

  const handleCronSave = async () => {
    setCronMsg("");
    try {
      await api.updateSchedulerCron(cronExpr);
      setCronMsg("✓ Schedule updated");
      api.getSchedulerStatus().then(setSchedulerStatus).catch(() => {});
    } catch (e: any) { setCronMsg(e.message); }
  };

  const handleProviderChange = (provider: string) => {
    const defaultModel = MODELS[provider]?.[0] ?? "";
    setForm(f => ({ ...f, ai_provider: provider, ai_model: defaultModel }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      await api.saveSettings(form);
      setMsg("Saved.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-500 text-sm">
        <Loader2 size={18} className="animate-spin mr-2" /> Loading…
      </div>
    );
  }

  const activeProvider = PROVIDERS.find(p => p.value === form.ai_provider) ?? PROVIDERS[0];
  const modelList = MODELS[form.ai_provider] ?? [];

  return (
    <div className="max-w-2xl space-y-8 p-8">
      <div>
        <h2 className="text-lg font-semibold text-white">Settings</h2>
        <p className="text-sm text-slate-500 mt-0.5">AI provider, API keys, and your base resume</p>
      </div>

      {/* AI Provider */}
      <section className="space-y-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">AI Provider</h3>

        {/* Provider tabs */}
        <div className="flex gap-2 flex-wrap">
          {PROVIDERS.map(p => (
            <button
              key={p.value}
              onClick={() => handleProviderChange(p.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                form.ai_provider === p.value
                  ? "bg-blue-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* API Key */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {activeProvider.label} API Key
            <a
              href={activeProvider.url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-2 text-blue-400 hover:underline"
            >
              Get key →
            </a>
          </label>
          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={form.ai_api_key}
              onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))}
              placeholder={activeProvider.placeholder}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-9 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => setShowKey(v => !v)}
              className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
            >
              {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>

        {/* Model */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Model</label>
          <div className="flex gap-2">
            <select
              value={form.ai_model}
              onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
              className="flex-1 bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              {modelList.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <input
              type="text"
              value={form.ai_model}
              onChange={e => setForm(f => ({ ...f, ai_model: e.target.value }))}
              placeholder="or type custom model ID"
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-blue-500"
            />
          </div>
          <p className="text-xs text-slate-600 mt-1">Dropdown picks preset. Right field for custom model IDs.</p>
        </div>

        {form.ai_provider === "groq" && (
          <p className="text-xs text-green-600 bg-green-950/30 border border-green-900/40 rounded px-3 py-2">
            Groq free tier: fast, no cost for most models. Best for quick tailoring.
          </p>
        )}
        {form.ai_provider === "openrouter" && (
          <p className="text-xs text-blue-600 bg-blue-950/20 border border-blue-900/30 rounded px-3 py-2">
            OpenRouter: access Claude, Gemini, Llama, DeepSeek all from one key. "...free" suffix models cost $0.
          </p>
        )}
      </section>

      {/* Active Sources */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Job Sources</h3>
        <div className="grid grid-cols-2 gap-2">
          {[
            { name: "Greenhouse",  count: "2,550 boards", color: "text-green-400" },
            { name: "Lever",       count: "189 companies", color: "text-emerald-400" },
            { name: "Ashby",       count: "911 companies", color: "text-cyan-400" },
            { name: "HiringCafe",  count: "985+ jobs",    color: "text-yellow-400" },
            { name: "Google Jobs", count: "direct API",   color: "text-blue-400" },
            { name: "Apple Jobs",  count: "direct API",   color: "text-slate-400" },
            { name: "Meta Jobs",   count: "direct API",   color: "text-indigo-400" },
            { name: "Netflix Jobs",count: "direct API",   color: "text-red-400" },
          ].map(s => (
            <div key={s.name} className="flex items-center justify-between bg-slate-800/60 border border-slate-700/60 rounded-lg px-3 py-2">
              <span className={`text-xs font-medium ${s.color}`}>{s.name}</span>
              <span className="text-[10px] text-slate-500">{s.count}</span>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-slate-600">No API keys needed for any of these sources. Auto-deduplicated.</p>
      </section>

      {/* Resume sync note */}
      <section className="space-y-2">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Resume</h3>
        <div className="flex items-start gap-3 bg-slate-800/50 border border-slate-700/60 rounded-lg px-4 py-3">
          <div className="flex-1">
            <p className="text-sm text-slate-300 font-medium">Managed in My Profile</p>
            <p className="text-xs text-slate-500 mt-0.5">Upload your resume in Profile → AI uses it automatically for tailoring. No need to paste text here.</p>
          </div>
          <a href="#" onClick={e => { e.preventDefault(); (window as any).__navToProfile?.(); }}
            className="text-xs text-blue-400 hover:text-blue-300 whitespace-nowrap mt-0.5">
            Go to Profile →
          </a>
        </div>
      </section>

      {/* Auto-scrape scheduler */}
      <section className="space-y-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Auto-Scrape Schedule</h3>
        {schedulerStatus && (
          <p className="text-xs text-slate-500">
            Status: <span className={schedulerStatus.running ? "text-green-400" : "text-red-400"}>{schedulerStatus.running ? "Running" : "Stopped"}</span>
            {schedulerStatus.jobs?.[0]?.next_run && (
              <> · Next run: <span className="text-slate-300">{new Date(schedulerStatus.jobs[0].next_run).toLocaleString()}</span></>
            )}
          </p>
        )}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="block text-xs text-slate-400 mb-1">Cron expression</label>
            <input
              value={cronExpr}
              onChange={e => setCronExpr(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-blue-500"
              placeholder="0 */6 * * *"
            />
            <p className="text-[11px] text-slate-600 mt-1">Examples: <code>0 */6 * * *</code> = every 6h · <code>0 8 * * *</code> = daily 8am · <code>0 8,20 * * *</code> = 8am & 8pm</p>
          </div>
          <button onClick={handleCronSave} className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-sm text-white rounded-lg transition-colors whitespace-nowrap">
            Update Schedule
          </button>
        </div>
        {cronMsg && <p className="text-xs text-green-400">{cronMsg}</p>}
      </section>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save Settings
        </button>
        {msg && <span className="text-xs text-slate-400">{msg}</span>}
      </div>
    </div>
  );
}
