import { useState } from "react";
import { api } from "../api";

interface Props {
  onSuccess: (user: { id: string; email: string; name: string }) => void;
}

export function Auth({ onSuccess }: Props) {
  const [mode, setMode]         = useState<"login" | "register">("login");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [name, setName]         = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [showForgot, setShowForgot] = useState(false);

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

  const inp: React.CSSProperties = {
    width: "100%", height: 44, padding: "0 14px",
    borderRadius: 10, fontSize: 14,
    background: "#f8fafc", border: "1.5px solid #e2e8f0",
    color: "#0f172a", outline: "none", fontFamily: "inherit",
    transition: "border-color .15s, box-shadow .15s",
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── LEFT PANEL: Branding ── */}
      <div style={{
        width: "42%", flexShrink: 0,
        background: "linear-gradient(145deg, #0f0c29, #302b63, #24243e)",
        display: "flex", flexDirection: "column",
        justifyContent: "space-between",
        padding: "48px 52px",
        position: "relative", overflow: "hidden",
      }}>
        {/* Background glow */}
        <div style={{ position: "absolute", top: "20%", left: "30%", width: 380, height: 380, borderRadius: "50%", background: "radial-gradient(circle, rgba(124,58,237,0.35) 0%, transparent 70%)", filter: "blur(60px)", pointerEvents: "none" }} />
        <div style={{ position: "absolute", bottom: "15%", right: "-10%", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle, rgba(6,182,212,0.2) 0%, transparent 70%)", filter: "blur(50px)", pointerEvents: "none" }} />

        {/* Logo */}
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: "linear-gradient(135deg, #8b5cf6, #06b6d4)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 8px 24px rgba(124,58,237,0.5)" }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              </svg>
            </div>
            <span style={{ fontSize: 20, fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>
              Job<span style={{ background: "linear-gradient(90deg,#8b5cf6,#22d3ee)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Hunter</span>
            </span>
          </div>
        </div>

        {/* Center content */}
        <div style={{ position: "relative", zIndex: 1 }}>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: "#fff", lineHeight: 1.15, letterSpacing: "-0.03em", marginBottom: 16 }}>
            Find your next<br />
            <span style={{ background: "linear-gradient(90deg,#a78bfa,#22d3ee)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>dream job</span><br />
            with AI.
          </h2>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.55)", lineHeight: 1.7, maxWidth: 320 }}>
            Scrape thousands of jobs, qualify matches, tailor your resume — all automatically.
          </p>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 32, marginTop: 40 }}>
            {[
              { n: "6,800+", label: "Jobs indexed" },
              { n: "10+", label: "Job boards" },
              { n: "AI", label: "Powered" },
            ].map(s => (
              <div key={s.label}>
                <div style={{ fontSize: 22, fontWeight: 800, color: "#fff", letterSpacing: "-0.02em" }}>{s.n}</div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", marginTop: 2 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ position: "relative", zIndex: 1, fontSize: 12, color: "rgba(255,255,255,0.3)" }}>
          Your personal AI job search assistant
        </div>
      </div>

      {/* ── RIGHT PANEL: Form ── */}
      <div style={{
        flex: 1, background: "#ffffff",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "40px 48px",
        overflowY: "auto",
      }}>
        <div style={{ width: "100%", maxWidth: 400 }}>

          {/* Heading */}
          <div style={{ marginBottom: 32 }}>
            <h1 style={{ fontSize: 26, fontWeight: 800, color: "#0f172a", margin: 0, letterSpacing: "-0.03em" }}>
              {mode === "login" ? "Welcome back" : "Create account"}
            </h1>
            <p style={{ fontSize: 14, color: "#64748b", marginTop: 6, marginBottom: 0 }}>
              {mode === "login"
                ? "Sign in to your job search dashboard"
                : "Set up your account and start hunting"}
            </p>
          </div>

          {/* Tab toggle */}
          <div style={{
            display: "flex", background: "#f1f5f9", borderRadius: 10,
            padding: 4, marginBottom: 28, gap: 4,
          }}>
            {(["login", "register"] as const).map(m => (
              <button key={m} type="button" onClick={() => { setMode(m); setError(""); }}
                style={{
                  flex: 1, height: 36, borderRadius: 8, fontSize: 13.5, fontWeight: 600,
                  border: "none", cursor: "pointer", transition: "all .18s",
                  background: mode === m ? "#fff" : "transparent",
                  color: mode === m ? "#0f172a" : "#94a3b8",
                  boxShadow: mode === m ? "0 1px 4px rgba(0,0,0,0.12)" : "none",
                }}>
                {m === "login" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {mode === "register" && (
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Full Name</label>
                <input type="text" value={name} onChange={e => setName(e.target.value)}
                  placeholder="Jane Smith" required autoFocus
                  style={inp}
                  onFocus={e => { e.currentTarget.style.borderColor = "#8b5cf6"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(139,92,246,0.12)"; }}
                  onBlur={e => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.boxShadow = "none"; }}
                />
              </div>
            )}

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Email Address</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com" required autoFocus={mode === "login"}
                style={inp}
                onFocus={e => { e.currentTarget.style.borderColor = "#8b5cf6"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(139,92,246,0.12)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Password</label>
                {mode === "login" && (
                  <button type="button" onClick={() => setShowForgot(f => !f)}
                    style={{ background: "none", border: "none", fontSize: 12, color: "#8b5cf6", cursor: "pointer", padding: 0, fontFamily: "inherit" }}>
                    Forgot password?
                  </button>
                )}
              </div>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
                required
                style={inp}
                onFocus={e => { e.currentTarget.style.borderColor = "#8b5cf6"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(139,92,246,0.12)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.boxShadow = "none"; }}
              />

              {showForgot && mode === "login" && (
                <div style={{ marginTop: 10, padding: "12px 14px", background: "#faf5ff", border: "1px solid #e9d5ff", borderRadius: 8, fontSize: 12.5, color: "#6b21a8", lineHeight: 1.6 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Reset password</div>
                  <div style={{ color: "#7e22ce", marginBottom: 6 }}>Run this in your terminal:</div>
                  <code style={{ display: "block", background: "#f3e8ff", padding: "6px 10px", borderRadius: 6, fontSize: 11, color: "#581c87", fontFamily: "monospace" }}>
                    cd backend && python reset_password.py
                  </code>
                </div>
              )}
            </div>

            {error && (
              <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "12px 14px", fontSize: 13, color: "#dc2626", display: "flex", alignItems: "center", gap: 8 }}>
                <span>⚠️</span> {error}
              </div>
            )}

            <button type="submit" disabled={loading} style={{
              width: "100%", height: 46, borderRadius: 10, border: "none",
              background: "linear-gradient(135deg, #7c3aed, #06b6d4)",
              color: "#fff", fontSize: 15, fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
              boxShadow: "0 4px 18px rgba(124,58,237,0.35)",
              transition: "all .15s", marginTop: 4,
              fontFamily: "inherit",
            }}
              onMouseEnter={e => { if (!loading) e.currentTarget.style.boxShadow = "0 6px 24px rgba(124,58,237,0.5)"; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = "0 4px 18px rgba(124,58,237,0.35)"; }}
            >
              {loading
                ? (mode === "login" ? "Signing in…" : "Creating account…")
                : (mode === "login" ? "Sign In →" : "Create Account →")}
            </button>
          </form>

          <p style={{ textAlign: "center", fontSize: 13, color: "#94a3b8", marginTop: 24 }}>
            {mode === "login" ? "Don't have an account? " : "Already have an account? "}
            <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
              style={{ background: "none", border: "none", color: "#7c3aed", fontWeight: 600, cursor: "pointer", fontSize: 13, padding: 0, fontFamily: "inherit" }}>
              {mode === "login" ? "Register" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
