import { useState, useEffect, useRef } from "react";
import { api } from "../api";

interface Props {
  onSuccess: (user: { id: string; email: string; name: string }) => void;
}

/* ── Real Job Hunter logo: bullseye target ── */
function BullseyeLogo({ size = 40, color = "#2563eb" }: { size?: number; color?: string }) {
  const r = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      {/* Outer ring */}
      <circle cx={r} cy={r} r={r - 2} stroke={color} strokeWidth={size * 0.065} fill="none" />
      {/* Inner dot */}
      <circle cx={r} cy={r} r={r * 0.28} fill={color} />
    </svg>
  );
}

/* ── Animated pulse rings (right panel decoration) ── */
function PulseRings() {
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} style={{
          position: "absolute",
          width: i * 140, height: i * 140,
          borderRadius: "50%",
          border: "1px solid rgba(255,255,255,0.07)",
          animation: `ringPulse 4s ease-in-out ${i * 0.6}s infinite`,
        }} />
      ))}
      <style>{`
        @keyframes ringPulse {
          0%, 100% { opacity: 0.4; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.04); }
        }
      `}</style>
    </div>
  );
}

/* ── Animated number counter ── */
function Counter({ to, duration = 1600 }: { to: number; duration?: number }) {
  const [val, setVal] = useState(0);
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (!to) return;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(to * eased));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [to, duration]);
  return <>{val.toLocaleString()}</>;
}

export function Auth({ onSuccess }: Props) {
  const [mode, setMode]             = useState<"login" | "register">("login");
  const [email, setEmail]           = useState("");
  const [password, setPassword]     = useState("");
  const [name, setName]             = useState("");
  const [error, setError]           = useState("");
  const [loading, setLoading]       = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [jobCount, setJobCount]     = useState<number>(
    parseInt(localStorage.getItem("jh_job_count") || "0", 10)
  );

  useEffect(() => {
    const BASE = (import.meta.env.VITE_API_URL || "");
    fetch(`${BASE}/api/jobs/count`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.count) {
          setJobCount(d.count);
          localStorage.setItem("jh_job_count", String(d.count));
        }
      })
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      if (mode === "register") {
        if (!name.trim())        { setError("Full name is required"); setLoading(false); return; }
        if (password.length < 8) { setError("Password must be at least 8 characters"); setLoading(false); return; }
      }
      const result = mode === "login"
        ? await api.auth.login(email, password)
        : await api.auth.register(email, password, name);
      localStorage.setItem("jh_token", result.token);
      localStorage.setItem("jh_user", JSON.stringify(result.user));
      onSuccess(result.user);
    } catch (e: any) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "'Inter', system-ui, sans-serif", overflow: "hidden" }}>

      {/* ══════════════════════════════════════════
          LEFT — Clean white form panel
      ══════════════════════════════════════════ */}
      <div style={{
        flex: 1, background: "#fff",
        display: "flex", flexDirection: "column",
        padding: "0 0 0 0", overflowY: "auto",
      }}>
        {/* Top bar with logo */}
        <div style={{ padding: "28px 40px 0", display: "flex", alignItems: "center", gap: 12 }}>
          <BullseyeLogo size={36} color="#2563eb" />
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.03em", color: "#0f172a", lineHeight: 1 }}>
              Job <span style={{ color: "#2563eb" }}>Hunter</span>
            </div>
            <div style={{ fontSize: 9, letterSpacing: "0.15em", color: "#94a3b8", textTransform: "uppercase", marginTop: 2, fontWeight: 600 }}>
              Hunt Smarter, Not Harder
            </div>
          </div>
        </div>

        {/* Form area — centered vertically */}
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "32px 40px" }}>
          <div style={{ width: "100%", maxWidth: 380 }}>

            {/* Heading */}
            <h1 style={{ fontSize: 28, fontWeight: 800, color: "#0f172a", margin: "0 0 6px", letterSpacing: "-0.03em" }}>
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p style={{ fontSize: 14, color: "#64748b", margin: "0 0 28px", lineHeight: 1.5 }}>
              {mode === "login"
                ? "Sign in to your AI job search dashboard."
                : "Start finding and winning jobs with AI."}
            </p>

            {/* Tab toggle */}
            <div style={{
              display: "flex", background: "#f1f5f9",
              borderRadius: 12, padding: 4, marginBottom: 28,
            }}>
              {(["login", "register"] as const).map(m => (
                <button key={m} type="button"
                  onClick={() => { setMode(m); setError(""); setShowForgot(false); }}
                  style={{
                    flex: 1, height: 38, borderRadius: 9, border: "none",
                    fontSize: 13.5, fontWeight: 600, cursor: "pointer",
                    transition: "all .2s cubic-bezier(0.34,1.56,0.64,1)",
                    background: mode === m ? "#fff" : "transparent",
                    color: mode === m ? "#0f172a" : "#94a3b8",
                    boxShadow: mode === m ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
                  }}>
                  {m === "login" ? "Sign In" : "Register"}
                </button>
              ))}
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              {mode === "register" && (
                <FormField label="Full Name">
                  <Input type="text" value={name} onChange={e => setName(e.target.value)}
                    placeholder="Jane Smith" required autoFocus />
                </FormField>
              )}

              <FormField label="Email Address">
                <Input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com" required autoFocus={mode === "login"} />
              </FormField>

              <FormField label="Password" right={
                mode === "login" ? (
                  <button type="button" onClick={() => setShowForgot(f => !f)}
                    style={{ background: "none", border: "none", fontSize: 12.5, color: "#2563eb", cursor: "pointer", padding: 0, fontFamily: "inherit", fontWeight: 500 }}>
                    Forgot password?
                  </button>
                ) : undefined
              }>
                <Input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder={mode === "register" ? "At least 8 characters" : "Your password"} required />
              </FormField>

              {showForgot && mode === "login" && (
                <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 10, padding: "12px 14px", fontSize: 12.5, color: "#1e40af", lineHeight: 1.65 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
                    🔑 Reset your password
                  </div>
                  <div style={{ color: "#3b82f6", marginBottom: 8 }}>Run in your terminal (backend folder):</div>
                  <code style={{ display: "block", background: "#dbeafe", padding: "7px 10px", borderRadius: 7, fontSize: 11, color: "#1e3a8a", fontFamily: "monospace", letterSpacing: "0.01em" }}>
                    python reset_password.py
                  </code>
                </div>
              )}

              {error && (
                <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "11px 14px", fontSize: 13, color: "#dc2626", display: "flex", alignItems: "center", gap: 8 }}>
                  ⚠️ {error}
                </div>
              )}

              <button type="submit" disabled={loading} style={{
                height: 48, borderRadius: 12, border: "none",
                background: "linear-gradient(135deg, #1d4ed8 0%, #2563eb 50%, #0284c7 100%)",
                color: "#fff", fontSize: 15, fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.75 : 1,
                boxShadow: "0 4px 20px rgba(37,99,235,0.4)",
                transition: "all .15s", letterSpacing: "-0.01em",
                fontFamily: "inherit", marginTop: 4,
              }}>
                {loading
                  ? (mode === "login" ? "Signing in…" : "Creating account…")
                  : (mode === "login" ? "Sign In →" : "Create Account →")}
              </button>
            </form>

            <p style={{ textAlign: "center", fontSize: 13, color: "#94a3b8", marginTop: 22, marginBottom: 0 }}>
              {mode === "login" ? "No account? " : "Already registered? "}
              <button type="button"
                onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
                style={{ background: "none", border: "none", color: "#2563eb", fontWeight: 600, cursor: "pointer", fontSize: 13, padding: 0, fontFamily: "inherit" }}>
                {mode === "login" ? "Register free" : "Sign in"}
              </button>
            </p>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════
          RIGHT — Brand panel
      ══════════════════════════════════════════ */}
      <div style={{
        width: "50%", flexShrink: 0,
        background: "linear-gradient(155deg, #0c1a3a 0%, #0f2051 45%, #081020 100%)",
        display: "flex", flexDirection: "column",
        justifyContent: "center",
        position: "relative", overflow: "hidden",
        padding: "52px 64px",
      }}>
        <PulseRings />

        {/* Big logo mark */}
        <div style={{ position: "relative", zIndex: 1, marginBottom: 36 }}>
          <div style={{
            width: 160, height: 160,
            borderRadius: "50%",
            background: "rgba(37,99,235,0.1)",
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid rgba(37,99,235,0.25)",
            boxShadow: "0 0 80px rgba(37,99,235,0.3), 0 0 160px rgba(37,99,235,0.1)",
          }}>
            <BullseyeLogo size={100} color="#3b82f6" />
          </div>
        </div>

        {/* Headline */}
        <div style={{ position: "relative", zIndex: 1, maxWidth: 420 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.18em", color: "#3b82f6", textTransform: "uppercase", marginBottom: 14 }}>
            Hunt Smarter, Not Harder
          </div>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: "#fff", lineHeight: 1.15, letterSpacing: "-0.03em", margin: "0 0 14px" }}>
            Wake up to interviews,<br />
            <span style={{ color: "#60a5fa" }}>not job boards.</span>
          </h2>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.45)", lineHeight: 1.75, margin: "0 0 36px" }}>
            Job Hunter scrapes thousands of openings every night,
            qualifies the ones that fit you, and helps you apply — automatically.
          </p>

          {/* Feature bullets */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 40 }}>
            {[
              { icon: "🎯", text: "AI qualifies every match with a 0–100 fit score" },
              { icon: "📝", text: "Resume tailored to each job in one click" },
              { icon: "⚡", text: "Auto Apply — review & submit (coming soon)" },
              { icon: "📊", text: "Track everything: kanban, dashboard, reminders" },
            ].map(f => (
              <div key={f.text} style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>{f.icon}</span>
                <span style={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>{f.text}</span>
              </div>
            ))}
          </div>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 0, borderRadius: 14, overflow: "hidden", border: "1px solid rgba(255,255,255,0.08)" }}>
            <div style={{ flex: 1, padding: "18px 14px", textAlign: "center", background: "rgba(255,255,255,0.04)" }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#fff", letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>
                {jobCount > 0 ? <><Counter to={jobCount} />+</> : "—"}
              </div>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 3, fontWeight: 500 }}>Jobs indexed</div>
            </div>
            <div style={{ flex: 1, padding: "18px 14px", textAlign: "center", background: "rgba(255,255,255,0.04)", borderLeft: "1px solid rgba(255,255,255,0.07)" }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#93c5fd", letterSpacing: "-0.01em" }}>Greenhouse</div>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 3 }}>Lever · Ashby · more</div>
            </div>
            <div style={{ flex: 1, padding: "18px 14px", textAlign: "center", background: "rgba(255,255,255,0.04)", borderLeft: "1px solid rgba(255,255,255,0.07)" }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#4ade80" }}>⚡ Auto Apply</div>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 3 }}>Coming soon</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Helpers ── */
function FormField({ label, children, right }: { label: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>{label}</label>
        {right}
      </div>
      {children}
    </div>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const [focused, setFocused] = useState(false);
  return (
    <input
      {...props}
      onFocus={e => { setFocused(true); props.onFocus?.(e); }}
      onBlur={e => { setFocused(false); props.onBlur?.(e); }}
      style={{
        width: "100%", height: 46, padding: "0 14px",
        borderRadius: 10, fontSize: 14,
        background: focused ? "#fff" : "#f8fafc",
        border: focused ? "1.5px solid #2563eb" : "1.5px solid #e2e8f0",
        boxShadow: focused ? "0 0 0 3px rgba(37,99,235,0.1)" : "none",
        color: "#0f172a", outline: "none",
        fontFamily: "'Inter', system-ui, sans-serif",
        transition: "all .15s",
        boxSizing: "border-box",
      }}
    />
  );
}
