import { useState } from "react";
import { api } from "../api";

interface Props {
  user: { name: string; email: string };
  onComplete: () => void;
}

const ROLES = [
  "Software Engineer", "Backend Engineer", "Frontend Engineer", "Full Stack Developer",
  "Data Engineer", "Analytics Engineer", "Data Scientist", "ML / AI Engineer",
  "DevOps / SRE / Platform Engineer", "Security Engineer", "Cloud Engineer",
  "Quantitative Analyst", "Financial Analyst", "Risk Analyst", "Trading / Investment",
  "Product Manager", "Program Manager", "Project Manager", "Product Analyst",
  "UX / Product Designer", "UI Designer", "UX Researcher",
  "Research Scientist", "Research Engineer",
  "Marketing Analyst", "Growth Engineer", "Business Analyst",
  "Engineering Manager", "Technical Lead", "Director of Engineering",
];

const COUNTRIES = ["USA", "India", "UK", "Canada", "Germany", "Australia", "Remote"];

const VISA_OPTIONS = [
  "US Citizen / Green Card",
  "H1B",
  "F1 / OPT",
  "L1 / Other Visa",
  "Outside US",
];

const STEPS = [
  { label: "Roles", icon: "🎯" },
  { label: "Location", icon: "🌍" },
  { label: "Resume", icon: "📄" },
  { label: "AI Key", icon: "🤖" },
];

export function Onboarding({ user, onComplete }: Props) {
  const [step, setStep]           = useState(0);
  const [roles, setRoles]         = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>(["USA", "Remote"]);
  const [visa, setVisa]           = useState("");
  const [resume, setResume]       = useState("");
  const [aiKey, setAiKey]         = useState("");
  const [aiModel, setAiModel]     = useState("anthropic/claude-sonnet-4-5");
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");

  const toggleRole    = (r: string) => setRoles(rs => rs.includes(r) ? rs.filter(x => x !== r) : [...rs, r]);
  const toggleCountry = (c: string) => setCountries(cs => cs.includes(c) ? cs.filter(x => x !== c) : [...cs, c]);

  const canNext = () => {
    if (step === 0) return roles.length > 0;
    if (step === 1) return countries.length > 0;
    return true; // Steps 2-3 are optional
  };

  const handleFinish = async () => {
    setSaving(true); setError("");
    try {
      await api.saveSettings({
        job_roles: roles,
        countries,
        profile_name: user.name,
        profile_visa: visa,
        resume,
        ai_api_key: aiKey || undefined,
        ai_model: aiModel,
        visa_filter: visa === "F1 / OPT" || visa === "H1B",
      } as any);
      onComplete();
    } catch (e: any) {
      setError(e.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const card: React.CSSProperties = {
    width: "100%", maxWidth: 620, margin: "0 20px",
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 24, padding: "44px 44px 36px",
    boxShadow: "0 32px 64px rgba(0,0,0,0.6)",
    position: "relative", zIndex: 1,
  };

  const chip = (label: string, active: boolean, onClick: () => void): React.ReactNode => (
    <button key={label} onClick={onClick} style={{
      height: 34, padding: "0 14px", borderRadius: 8, fontSize: 13, fontWeight: 500,
      cursor: "pointer", transition: "all 120ms", border: "1px solid",
      background: active ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.04)",
      borderColor: active ? "rgba(59,130,246,0.5)" : "rgba(255,255,255,0.1)",
      color: active ? "#93c5fd" : "#64748b",
      fontFamily: "inherit",
    }}
      onMouseEnter={e => { if (!active) { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.2)"; (e.currentTarget as HTMLButtonElement).style.color = "#94a3b8"; } }}
      onMouseLeave={e => { if (!active) { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.1)"; (e.currentTarget as HTMLButtonElement).style.color = "#64748b"; } }}
    >
      {active ? "✓ " : ""}{label}
    </button>
  );

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%)",
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      {/* Background glow */}
      <div style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "20%", left: "15%", width: 500, height: 500,
          background: "radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)",
          borderRadius: "50%", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "15%", right: "10%", width: 400, height: 400,
          background: "radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)",
          borderRadius: "50%", filter: "blur(60px)" }} />
      </div>

      <div style={card}>
        {/* Header */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ fontSize: 12, color: "#475569", marginBottom: 8, fontWeight: 500 }}>
            👋 Welcome, {user.name.split(" ")[0]}! Let's set up your job search.
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#f1f5f9", margin: 0, letterSpacing: "-0.02em" }}>
            {STEPS[step].icon} {["What roles are you looking for?", "Where do you want to work?", "Upload your resume", "Set up AI (optional)"][step]}
          </h1>
        </div>

        {/* Progress bar */}
        <div style={{ marginBottom: 36 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            {STEPS.map((s, i) => (
              <div key={s.label} style={{ flex: 1, height: 3, borderRadius: 999,
                background: i <= step ? "#3b82f6" : "rgba(255,255,255,0.08)",
                transition: "background 300ms" }} />
            ))}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            {STEPS.map((s, i) => (
              <div key={s.label} style={{ fontSize: 10, color: i <= step ? "#3b82f6" : "#334155", fontWeight: 500 }}>
                {s.label}
              </div>
            ))}
          </div>
        </div>

        {/* Step 0 — Roles */}
        {step === 0 && (
          <div>
            <p style={{ fontSize: 13, color: "#64748b", marginBottom: 20, marginTop: 0 }}>
              Select all roles you're open to. You can change these anytime in Settings.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {ROLES.map(r => chip(r, roles.includes(r), () => toggleRole(r)))}
            </div>
            {roles.length > 0 && (
              <div style={{ marginTop: 16, fontSize: 12, color: "#475569" }}>
                {roles.length} role{roles.length !== 1 ? "s" : ""} selected
              </div>
            )}
          </div>
        )}

        {/* Step 1 — Location */}
        {step === 1 && (
          <div>
            <p style={{ fontSize: 13, color: "#64748b", marginBottom: 20, marginTop: 0 }}>
              Select countries where you want to find jobs.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 28 }}>
              {COUNTRIES.map(c => chip(c, countries.includes(c), () => toggleCountry(c)))}
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#94a3b8", marginBottom: 10 }}>
                Visa / Work Authorization
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {VISA_OPTIONS.map(v => (
                  <button key={v} onClick={() => setVisa(visa === v ? "" : v)} style={{
                    height: 34, padding: "0 14px", borderRadius: 8, fontSize: 13, fontWeight: 500,
                    cursor: "pointer", transition: "all 120ms", border: "1px solid", fontFamily: "inherit",
                    background: visa === v ? "rgba(139,92,246,0.15)" : "rgba(255,255,255,0.04)",
                    borderColor: visa === v ? "rgba(139,92,246,0.5)" : "rgba(255,255,255,0.1)",
                    color: visa === v ? "#c4b5fd" : "#64748b",
                  }}>
                    {visa === v ? "✓ " : ""}{v}
                  </button>
                ))}
              </div>
              {(visa === "F1 / OPT" || visa === "H1B") && (
                <div style={{ marginTop: 14, background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)",
                  borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#93c5fd" }}>
                  💡 Visa filter will be enabled — jobs requiring US citizenship or security clearance will be hidden automatically.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 2 — Resume */}
        {step === 2 && (
          <div>
            <p style={{ fontSize: 13, color: "#64748b", marginBottom: 16, marginTop: 0 }}>
              Paste your resume text below. The AI uses this to tailor applications and generate cover letters.
              You can also add it later in Settings.
            </p>
            <textarea
              value={resume}
              onChange={e => setResume(e.target.value)}
              placeholder={"Paste your resume text here...\n\nExample:\nJane Smith | jane@example.com\n\nExperience:\n  Software Engineer @ Stripe (2022–Present)\n  • Built payment processing APIs handling $1B+ daily...\n\nSkills: Python, TypeScript, PostgreSQL, AWS, Docker..."}
              style={{
                width: "100%", height: 280, borderRadius: 12, padding: 14, fontSize: 13, lineHeight: 1.6,
                background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                color: "#e2e8f0", resize: "vertical", outline: "none", boxSizing: "border-box",
                fontFamily: "monospace",
              }}
            />
            <div style={{ marginTop: 10, fontSize: 12, color: "#475569" }}>
              {resume.length > 0
                ? `✓ ${resume.split(/\s+/).filter(Boolean).length} words — AI will use this for all tailoring`
                : "Skip for now — you can add your resume in Settings → My Resume"}
            </div>
          </div>
        )}

        {/* Step 3 — AI Key */}
        {step === 3 && (
          <div>
            <p style={{ fontSize: 13, color: "#64748b", marginBottom: 20, marginTop: 0 }}>
              Add your AI API key to enable resume tailoring, cover letters, and job qualification.
              Skip this if you don't have one yet — you can add it anytime in Settings.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#94a3b8", marginBottom: 8 }}>
                  AI Provider
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  {[
                    { id: "openrouter", label: "OpenRouter", note: "Recommended — access all models" },
                    { id: "anthropic", label: "Anthropic", note: "Claude models directly" },
                  ].map(p => (
                    <button key={p.id} onClick={() => setAiModel(p.id === "anthropic" ? "claude-sonnet-4-5" : "anthropic/claude-sonnet-4-5")}
                      style={{
                        flex: 1, padding: "12px 14px", borderRadius: 10, border: "1px solid",
                        background: aiModel.includes("claude-sonnet-4-5") && (p.id === "openrouter") === aiModel.includes("/")
                          ? "rgba(59,130,246,0.12)" : "rgba(255,255,255,0.04)",
                        borderColor: aiModel.includes("claude-sonnet-4-5") && (p.id === "openrouter") === aiModel.includes("/")
                          ? "rgba(59,130,246,0.4)" : "rgba(255,255,255,0.1)",
                        cursor: "pointer", textAlign: "left", fontFamily: "inherit",
                      }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>{p.label}</div>
                      <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>{p.note}</div>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#94a3b8", marginBottom: 8 }}>
                  API Key
                </label>
                <input
                  type="password" value={aiKey} onChange={e => setAiKey(e.target.value)}
                  placeholder="sk-or-... or sk-ant-..."
                  style={{
                    width: "100%", height: 44, borderRadius: 10, border: "1px solid rgba(255,255,255,0.1)",
                    background: "rgba(255,255,255,0.06)", color: "#f1f5f9", fontSize: 14,
                    padding: "0 14px", outline: "none", boxSizing: "border-box", fontFamily: "monospace",
                  }}
                />
              </div>
              <div style={{ background: "rgba(16,185,129,0.07)", border: "1px solid rgba(16,185,129,0.2)",
                borderRadius: 10, padding: "12px 16px", fontSize: 12, color: "#6ee7b7" }}>
                🔒 Your API key is stored securely and only used for your own AI requests. Never shared.
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 20, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)",
            borderRadius: 10, padding: "11px 14px", fontSize: 13, color: "#fca5a5" }}>
            {error}
          </div>
        )}

        {/* Nav buttons */}
        <div style={{ display: "flex", gap: 10, marginTop: 32, justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 8 }}>
            {step > 0 && (
              <button onClick={() => setStep(s => s - 1)} style={{
                height: 42, padding: "0 20px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.1)",
                background: "transparent", color: "#94a3b8", cursor: "pointer",
                fontSize: 14, fontFamily: "inherit", fontWeight: 500,
              }}>← Back</button>
            )}
            {step >= 2 && (
              <button onClick={step === 3 ? handleFinish : () => setStep(s => s + 1)} style={{
                height: 42, padding: "0 20px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)",
                background: "rgba(255,255,255,0.04)", color: "#64748b", cursor: "pointer",
                fontSize: 14, fontFamily: "inherit",
              }}>
                {step === 3 ? "Skip & Finish" : "Skip this step"}
              </button>
            )}
          </div>
          <button
            onClick={step === 3 ? handleFinish : () => setStep(s => s + 1)}
            disabled={!canNext() || saving}
            style={{
              height: 44, padding: "0 28px", borderRadius: 12, border: "none",
              background: canNext() && !saving
                ? "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)"
                : "rgba(59,130,246,0.3)",
              color: "#fff", fontSize: 15, fontWeight: 600,
              cursor: canNext() && !saving ? "pointer" : "not-allowed",
              boxShadow: canNext() ? "0 4px 16px rgba(59,130,246,0.3)" : "none",
              transition: "all 150ms", fontFamily: "inherit",
            }}>
            {saving ? "Saving..." : step === 3 ? "Finish Setup →" : "Continue →"}
          </button>
        </div>
      </div>
    </div>
  );
}
