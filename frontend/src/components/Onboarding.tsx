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
  { label: "Roles",    icon: "🎯" },
  { label: "Location", icon: "🌍" },
  { label: "Resume",   icon: "📄" },
  { label: "AI Key",   icon: "🤖" },
];

// Gradient-fill SVG checkmark
const Check = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

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
    return true;
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

  // Chip helper
  const Chip = ({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) => (
    <button key={label} onClick={onClick} style={{
      height: 32, padding: "0 13px", borderRadius: "var(--r-sm)", fontSize: 12.5, fontWeight: 500,
      cursor: "pointer", transition: "all 120ms", border: "1px solid", fontFamily: "inherit",
      background: active ? "rgba(124,58,237,0.15)" : "var(--bg-elevated)",
      borderColor: active ? "rgba(139,92,246,0.5)" : "var(--line)",
      color: active ? "var(--violet)" : "var(--tx-3)",
    }}>
      {active ? "✓ " : ""}{label}
    </button>
  );

  const STEP_TITLES = [
    "What roles are you looking for?",
    "Where do you want to work?",
    "Upload your resume",
    "Set up AI (optional)",
  ];

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-base)", fontFamily: "var(--f-ui)", position: "relative",
    }}>
      {/* Background glow */}
      <div style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        <div style={{
          position: "absolute", top: "20%", left: "15%", width: 500, height: 500,
          background: "radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 65%)",
          borderRadius: "50%", filter: "blur(80px)",
        }} />
        <div style={{
          position: "absolute", bottom: "15%", right: "10%", width: 400, height: 400,
          background: "radial-gradient(circle, rgba(6,182,212,0.10) 0%, transparent 65%)",
          borderRadius: "50%", filter: "blur(70px)",
        }} />
      </div>

      <div style={{
        width: "100%", maxWidth: 640, margin: "0 20px",
        background: "var(--glass-hi)",
        backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)",
        border: "1px solid var(--glass-border)",
        borderRadius: "var(--r-xl)", padding: "44px 44px 36px",
        boxShadow: "0 32px 64px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)",
        position: "relative", zIndex: 1,
      }}>

        {/* Thin gradient progress bar */}
        <div style={{ marginBottom: 30 }}>
          <div style={{ height: 3, borderRadius: 999, background: "var(--line)", position: "relative", overflow: "hidden" }}>
            <div style={{
              position: "absolute", top: 0, left: 0, height: "100%",
              width: `${((step + 1) / STEPS.length) * 100}%`,
              background: "var(--grad)",
              borderRadius: 999, transition: "width 0.4s cubic-bezier(0.4,0,0.2,1)",
            }} />
          </div>

          {/* Step indicators */}
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 14, gap: 8 }}>
            {STEPS.map((s, i) => {
              const done   = i < step;
              const active = i === step;
              return (
                <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: 999, flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: done || active ? "var(--grad)" : "var(--bg-elevated)",
                    border: done || active ? "none" : "1px solid var(--line)",
                    boxShadow: active ? "0 0 12px var(--violet-glow)" : "none",
                    transition: "all 0.25s",
                    fontSize: 11, fontWeight: 700,
                    color: done || active ? "#fff" : "var(--tx-3)",
                  }}>
                    {done ? <Check /> : i + 1}
                  </div>
                  <span style={{ fontSize: 11.5, fontWeight: active ? 600 : 400, color: active ? "var(--tx)" : done ? "var(--tx-2)" : "var(--tx-3)", transition: "color 0.2s" }}>
                    {s.label}
                  </span>
                  {i < STEPS.length - 1 && (
                    <div style={{ flex: 1, height: 1, background: i < step ? "rgba(139,92,246,0.3)" : "var(--line)", marginLeft: 4 }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 12, color: "var(--tx-3)", marginBottom: 6, fontWeight: 500 }}>
            👋 Welcome, {user.name.split(" ")[0]}! Let's set up your job search.
          </div>
          <h1 style={{ fontFamily: "var(--f-display)", fontSize: 22, fontWeight: 700, color: "var(--tx)", margin: 0, letterSpacing: "-0.02em" }}>
            {STEPS[step].icon} {STEP_TITLES[step]}
          </h1>
        </div>

        {/* Step 0 — Roles */}
        {step === 0 && (
          <div>
            <p style={{ fontSize: 13, color: "var(--tx-3)", marginBottom: 20, marginTop: 0 }}>
              Select all roles you're open to. You can change these anytime in Settings.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
              {ROLES.map(r => <Chip key={r} label={r} active={roles.includes(r)} onClick={() => toggleRole(r)} />)}
            </div>
            {roles.length > 0 && (
              <div style={{ marginTop: 14, fontSize: 12, color: "var(--tx-3)" }}>
                {roles.length} role{roles.length !== 1 ? "s" : ""} selected
              </div>
            )}
          </div>
        )}

        {/* Step 1 — Location */}
        {step === 1 && (
          <div>
            <p style={{ fontSize: 13, color: "var(--tx-3)", marginBottom: 20, marginTop: 0 }}>
              Select countries where you want to find jobs.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginBottom: 28 }}>
              {COUNTRIES.map(c => <Chip key={c} label={c} active={countries.includes(c)} onClick={() => toggleCountry(c)} />)}
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 10 }}>
                Visa / Work Authorization
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                {VISA_OPTIONS.map(v => (
                  <button key={v} onClick={() => setVisa(visa === v ? "" : v)} style={{
                    height: 32, padding: "0 13px", borderRadius: "var(--r-sm)", fontSize: 12.5, fontWeight: 500,
                    cursor: "pointer", transition: "all 120ms", border: "1px solid", fontFamily: "inherit",
                    background: visa === v ? "rgba(139,92,246,0.15)" : "var(--bg-elevated)",
                    borderColor: visa === v ? "rgba(139,92,246,0.5)" : "var(--line)",
                    color: visa === v ? "var(--violet)" : "var(--tx-3)",
                  }}>
                    {visa === v ? "✓ " : ""}{v}
                  </button>
                ))}
              </div>
              {(visa === "F1 / OPT" || visa === "H1B") && (
                <div style={{
                  marginTop: 14, background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.2)",
                  borderRadius: "var(--r-sm)", padding: "10px 14px", fontSize: 12, color: "var(--violet)",
                }}>
                  💡 Visa filter will be enabled — jobs requiring US citizenship or security clearance will be hidden automatically.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 2 — Resume */}
        {step === 2 && (
          <div>
            <p style={{ fontSize: 13, color: "var(--tx-3)", marginBottom: 16, marginTop: 0 }}>
              Paste your resume text below. The AI uses this to tailor applications and generate cover letters.
              You can also add it later in Settings.
            </p>
            <textarea
              value={resume}
              onChange={e => setResume(e.target.value)}
              placeholder={"Paste your resume text here...\n\nExample:\nJane Smith | jane@example.com\n\nExperience:\n  Software Engineer @ Stripe (2022–Present)\n  • Built payment processing APIs handling $1B+ daily...\n\nSkills: Python, TypeScript, PostgreSQL, AWS, Docker..."}
              style={{
                width: "100%", height: 260, borderRadius: "var(--r-sm)", padding: 14, fontSize: 13, lineHeight: 1.6,
                background: "var(--bg-elevated)", border: "1px solid var(--line)",
                color: "var(--tx)", resize: "vertical", outline: "none", boxSizing: "border-box",
                fontFamily: "var(--f-mono)", transition: "border-color .14s",
              }}
              onFocus={e => { e.currentTarget.style.borderColor = "var(--violet)"; }}
              onBlur={e => { e.currentTarget.style.borderColor = "var(--line)"; }}
            />
            <div style={{ marginTop: 10, fontSize: 12, color: "var(--tx-3)" }}>
              {resume.length > 0
                ? `✓ ${resume.split(/\s+/).filter(Boolean).length} words — AI will use this for all tailoring`
                : "Skip for now — you can add your resume in Settings → My Resume"}
            </div>
          </div>
        )}

        {/* Step 3 — AI Key */}
        {step === 3 && (
          <div>
            <p style={{ fontSize: 13, color: "var(--tx-3)", marginBottom: 20, marginTop: 0 }}>
              Add your AI API key to enable resume tailoring, cover letters, and job qualification.
              Skip this if you don't have one yet — you can add it anytime in Settings.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 8 }}>
                  AI Provider
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  {[
                    { id: "openrouter", label: "OpenRouter", note: "Recommended — access all models" },
                    { id: "anthropic",  label: "Anthropic",  note: "Claude models directly" },
                  ].map(p => {
                    const isSelected = p.id === "openrouter" ? aiModel.includes("/") : !aiModel.includes("/");
                    return (
                      <button key={p.id}
                        onClick={() => setAiModel(p.id === "anthropic" ? "claude-sonnet-4-5" : "anthropic/claude-sonnet-4-5")}
                        style={{
                          flex: 1, padding: "12px 14px", borderRadius: "var(--r-sm)", border: "1px solid",
                          background: isSelected ? "rgba(124,58,237,0.12)" : "var(--bg-elevated)",
                          borderColor: isSelected ? "rgba(139,92,246,0.4)" : "var(--line)",
                          cursor: "pointer", textAlign: "left", fontFamily: "inherit", transition: "all .14s",
                        }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--tx)" }}>{p.label}</div>
                        <div style={{ fontSize: 11, color: "var(--tx-3)", marginTop: 2 }}>{p.note}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 8 }}>
                  API Key
                </label>
                <input
                  type="password" value={aiKey} onChange={e => setAiKey(e.target.value)}
                  placeholder="sk-or-... or sk-ant-..."
                  className="field"
                  style={{ fontFamily: "var(--f-mono)" }}
                />
              </div>
              <div style={{
                background: "rgba(16,185,129,0.07)", border: "1px solid rgba(16,185,129,0.2)",
                borderRadius: "var(--r-sm)", padding: "12px 16px", fontSize: 12, color: "#6ee7b7",
              }}>
                🔒 Your API key is stored securely and only used for your own AI requests. Never shared.
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{
            marginTop: 20, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)",
            borderRadius: "var(--r-sm)", padding: "11px 14px", fontSize: 13, color: "#fca5a5",
          }}>
            {error}
          </div>
        )}

        {/* Nav buttons */}
        <div style={{ display: "flex", gap: 10, marginTop: 32, justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 8 }}>
            {step > 0 && (
              <button onClick={() => setStep(s => s - 1)} style={{
                height: 40, padding: "0 18px", borderRadius: "var(--r-sm)",
                border: "1px solid var(--line)", background: "transparent",
                color: "var(--tx-3)", cursor: "pointer", fontSize: 13.5, fontFamily: "inherit", fontWeight: 500,
                transition: "all .13s",
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--tx-2)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--line-hi)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--tx-3)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--line)"; }}
              >← Back</button>
            )}
            {step >= 2 && (
              <button onClick={step === 3 ? handleFinish : () => setStep(s => s + 1)} style={{
                height: 40, padding: "0 18px", borderRadius: "var(--r-sm)",
                border: "1px solid var(--line)", background: "transparent",
                color: "var(--tx-3)", cursor: "pointer", fontSize: 13, fontFamily: "inherit",
              }}>
                {step === 3 ? "Skip & Finish" : "Skip this step"}
              </button>
            )}
          </div>
          <button
            onClick={step === 3 ? handleFinish : () => setStep(s => s + 1)}
            disabled={!canNext() || saving}
            style={{
              height: 40, padding: "0 26px", borderRadius: "var(--r-sm)", border: "none",
              background: canNext() && !saving ? "var(--grad)" : "rgba(124,58,237,0.3)",
              color: "#fff", fontSize: 13.5, fontWeight: 600,
              cursor: canNext() && !saving ? "pointer" : "not-allowed",
              boxShadow: canNext() ? "0 4px 14px -4px var(--violet-glow)" : "none",
              transition: "all 150ms", fontFamily: "inherit",
            }}>
            {saving ? "Saving…" : step === 3 ? "Finish Setup →" : "Continue →"}
          </button>
        </div>
      </div>
    </div>
  );
}
