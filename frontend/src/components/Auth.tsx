import { useState } from "react";
import { api } from "../api";

interface Props {
  onSuccess: (user: { id: string; email: string; name: string }) => void;
}

export function Auth({ onSuccess }: Props) {
  const [mode, setMode]       = useState<"login" | "register">("login");
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [name, setName]       = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  const switchMode = () => { setMode(m => m === "login" ? "register" : "login"); setError(""); };

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
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-base)", fontFamily: "var(--f-ui)", position: "relative",
    }}>
      {/* Background glow orbs */}
      <div style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
        <div style={{
          position: "absolute", top: "15%", left: "10%", width: 500, height: 500,
          background: "radial-gradient(circle, rgba(124,58,237,0.18) 0%, transparent 65%)",
          borderRadius: "50%", filter: "blur(70px)",
        }} />
        <div style={{
          position: "absolute", bottom: "15%", right: "10%", width: 420, height: 420,
          background: "radial-gradient(circle, rgba(6,182,212,0.12) 0%, transparent 65%)",
          borderRadius: "50%", filter: "blur(80px)",
        }} />
      </div>

      {/* Card */}
      <div style={{
        width: "100%", maxWidth: 420, margin: "0 20px",
        background: "var(--glass-hi)",
        backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)",
        border: "1px solid var(--glass-border)",
        borderRadius: "var(--r-xl)", padding: "44px 40px",
        boxShadow: "0 32px 64px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.06)",
        position: "relative", zIndex: 1,
      }}>

        {/* Brand mark */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 34 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 13,
            background: "var(--grad)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 6px 20px -4px var(--violet-glow)", flexShrink: 0,
          }}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: "var(--f-display)", fontSize: 18, fontWeight: 700, color: "var(--tx)", letterSpacing: "-0.02em", lineHeight: 1.2 }}>
              Job<span style={{ background: "var(--grad)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>Hunter</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--tx-3)", marginTop: 2 }}>AI-powered job search</div>
          </div>
        </div>

        {/* Tab toggle: Login | Register */}
        <div style={{
          position: "relative", display: "flex",
          background: "var(--bg-elevated)", border: "1px solid var(--line)",
          borderRadius: "var(--r)", padding: 4, marginBottom: 28,
        }}>
          {/* pill */}
          <div style={{
            position: "absolute", top: 4, left: 4,
            width: "calc(50% - 4px)", height: "calc(100% - 8px)",
            background: "var(--grad)", borderRadius: 6,
            boxShadow: "0 4px 14px -4px var(--violet-glow)",
            transform: mode === "register" ? "translateX(100%)" : "translateX(0)",
            transition: "transform 0.25s cubic-bezier(0.34,1.56,0.64,1)",
          }} />
          <button type="button" onClick={() => { setMode("login"); setError(""); }}
            style={{ flex: 1, padding: "9px", borderRadius: 6, fontSize: 13, fontWeight: 600,
              color: mode === "login" ? "#fff" : "var(--tx-3)", zIndex: 1, transition: "color .18s" }}>
            Sign In
          </button>
          <button type="button" onClick={() => { setMode("register"); setError(""); }}
            style={{ flex: 1, padding: "9px", borderRadius: 6, fontSize: 13, fontWeight: 600,
              color: mode === "register" ? "#fff" : "var(--tx-3)", zIndex: 1, transition: "color .18s" }}>
            Register
          </button>
        </div>

        {/* Heading */}
        <div style={{ marginBottom: 22 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--tx)", margin: 0, letterSpacing: "-0.02em", fontFamily: "var(--f-display)" }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p style={{ fontSize: 13, color: "var(--tx-3)", marginTop: 5, marginBottom: 0 }}>
            {mode === "login"
              ? "Sign in to your AI job search dashboard"
              : "Start finding and winning jobs with AI"}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "register" && (
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 6 }}>Full Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="Jane Smith" required autoFocus className="field" />
            </div>
          )}
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 6 }}>Email Address</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" required autoFocus={mode === "login"} className="field" />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--tx-2)", marginBottom: 6 }}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              required className="field" />
            {mode === "login" && (
              <div style={{ textAlign: "right", marginTop: 5 }}>
                <button type="button" onClick={() => setShowForgot(f => !f)} style={{
                  background: "none", border: "none", fontSize: 11.5,
                  color: showForgot ? "var(--violet)" : "var(--tx-3)", cursor: "pointer",
                  padding: 0, fontFamily: "inherit",
                }}>
                  {showForgot ? "Hide" : "Forgot password?"}
                </button>
              </div>
            )}
            {showForgot && mode === "login" && (
              <div style={{
                marginTop: 8,
                background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.2)",
                borderRadius: "var(--r-sm)", padding: "14px 16px", fontSize: 12, color: "var(--tx-2)",
                lineHeight: 1.7,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--violet)" }}>🔑 Reset your password</div>
                <div style={{ color: "var(--tx-3)", marginBottom: 10 }}>
                  Open a new terminal, navigate to the backend folder, and run:
                </div>
                <div style={{
                  background: "rgba(0,0,0,0.3)", borderRadius: 7, padding: "8px 12px",
                  fontFamily: "var(--f-mono)", fontSize: 11, color: "var(--tx)", marginBottom: 8,
                }}>
                  cd C:\Users\jagad\Downloads\job-hunter\backend{"\n"}
                  python reset_password.py
                </div>
                <div style={{ color: "var(--tx-3)", fontSize: 11 }}>
                  The tool will list all accounts and let you set a new password.
                </div>
              </div>
            )}
          </div>

          {error && (
            <div style={{
              background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: "var(--r-sm)", padding: "11px 14px", fontSize: 13, color: "#fca5a5",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ fontSize: 15 }}>⚠️</span> {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="auth-submit">
            {loading
              ? (mode === "login" ? "Signing in…" : "Creating account…")
              : (mode === "login" ? "Sign In →" : "Create Account →")}
          </button>
        </form>

        {/* Divider */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "22px 0" }}>
          <div style={{ flex: 1, height: 1, background: "var(--line)" }} />
          <span style={{ fontSize: 11, color: "var(--tx-3)" }}>
            {mode === "login" ? "New here?" : "Already have an account?"}
          </span>
          <div style={{ flex: 1, height: 1, background: "var(--line)" }} />
        </div>

        <button onClick={switchMode} style={{
          width: "100%", height: 40, borderRadius: "var(--r-sm)",
          border: "1px solid var(--line)",
          background: "var(--bg-elevated)",
          color: "var(--tx-3)", cursor: "pointer", fontSize: 13.5,
          fontWeight: 500, transition: "all 150ms", fontFamily: "inherit",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(124,58,237,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--violet)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--line)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--tx-3)"; }}
        >
          {mode === "login" ? "Create a free account" : "Sign in instead"}
        </button>

        {/* Feature list */}
        <div style={{ marginTop: 28, display: "flex", flexDirection: "column", gap: 7 }}>
          {[
            { icon: "🏢", text: "2,000+ companies across all industries" },
            { icon: "🤖", text: "AI resume tailoring + cover letters" },
            { icon: "📊", text: "ATS score + job qualification check" },
          ].map(f => (
            <div key={f.text} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 11.5, color: "var(--tx-3)" }}>
              <span style={{ fontSize: 13 }}>{f.icon}</span> {f.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
