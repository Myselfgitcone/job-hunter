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

  const inp: React.CSSProperties = {
    width: "100%", height: 44, borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.1)",
    background: "rgba(255,255,255,0.06)", color: "#f1f5f9",
    fontSize: 14, padding: "0 14px", outline: "none",
    boxSizing: "border-box", transition: "border-color 150ms",
    fontFamily: "inherit",
  };
  const lbl: React.CSSProperties = {
    display: "block", fontSize: 12, fontWeight: 500,
    color: "#94a3b8", marginBottom: 6,
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%)",
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      {/* Background glow orbs */}
      <div style={{ position: "fixed", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
        <div style={{ position: "absolute", top: "15%", left: "10%", width: 400, height: 400,
          background: "radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%)",
          borderRadius: "50%", filter: "blur(60px)" }} />
        <div style={{ position: "absolute", bottom: "15%", right: "10%", width: 500, height: 500,
          background: "radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)",
          borderRadius: "50%", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", top: "60%", left: "50%", width: 300, height: 300,
          background: "radial-gradient(circle, rgba(16,185,129,0.06) 0%, transparent 70%)",
          borderRadius: "50%", filter: "blur(60px)", transform: "translateX(-50%)" }} />
      </div>

      {/* Card */}
      <div style={{
        width: "100%", maxWidth: 440, margin: "0 20px",
        background: "rgba(255,255,255,0.03)",
        backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 24, padding: "44px 40px",
        boxShadow: "0 32px 64px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05)",
        position: "relative", zIndex: 1,
      }}>

        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 36 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 14,
            background: "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 0 24px rgba(59,130,246,0.45)", flexShrink: 0, fontSize: 20,
          }}>🎯</div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#f1f5f9", letterSpacing: "-0.02em", lineHeight: 1.2 }}>
              Job <span style={{ color: "#3b82f6" }}>Hunter</span>
            </div>
            <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>AI-powered job search for everyone</div>
          </div>
        </div>

        {/* Heading */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#f1f5f9", margin: 0, letterSpacing: "-0.02em" }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", marginTop: 6, marginBottom: 0 }}>
            {mode === "login"
              ? "Sign in to your AI job search dashboard"
              : "Start finding and winning jobs with AI"}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {mode === "register" && (
            <div>
              <label style={lbl}>Full Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="Jane Smith" required autoFocus style={inp} />
            </div>
          )}
          <div>
            <label style={lbl}>Email Address</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" required autoFocus={mode === "login"} style={inp} />
          </div>
          <div>
            <label style={lbl}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              required style={inp} />
            {mode === "login" && (
              <div style={{ textAlign: "right", marginTop: 4 }}>
                <button type="button" onClick={() => setShowForgot(f => !f)} style={{
                  background: "none", border: "none", fontSize: 12,
                  color: showForgot ? "#3b82f6" : "#475569", cursor: "pointer",
                  padding: 0, fontFamily: "inherit", textDecoration: "underline",
                }}>
                  {showForgot ? "Hide" : "Forgot password?"}
                </button>
              </div>
            )}
            {showForgot && mode === "login" && (
              <div style={{
                background: "rgba(59,130,246,0.07)", border: "1px solid rgba(59,130,246,0.2)",
                borderRadius: 10, padding: "14px 16px", fontSize: 12, color: "#93c5fd",
                lineHeight: 1.7,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 6, color: "#bfdbfe" }}>🔑 Reset your password</div>
                <div style={{ color: "#64748b", marginBottom: 10 }}>
                  Open a new terminal, navigate to the backend folder, and run:
                </div>
                <div style={{
                  background: "rgba(0,0,0,0.3)", borderRadius: 7, padding: "8px 12px",
                  fontFamily: "monospace", fontSize: 11, color: "#e2e8f0", marginBottom: 8,
                }}>
                  cd C:\Users\jagad\Downloads\job-hunter\backend{"\n"}
                  python reset_password.py
                </div>
                <div style={{ color: "#475569", fontSize: 11 }}>
                  The tool will list all accounts and let you set a new password.
                </div>
              </div>
            )}
          </div>

          {error && (
            <div style={{
              background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: 10, padding: "11px 14px", fontSize: 13, color: "#fca5a5",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ fontSize: 16 }}>⚠️</span> {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            height: 46, borderRadius: 12, border: "none",
            cursor: loading ? "not-allowed" : "pointer",
            background: loading
              ? "rgba(59,130,246,0.5)"
              : "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",
            color: "#fff", fontSize: 15, fontWeight: 600,
            letterSpacing: "-0.01em", transition: "all 150ms",
            opacity: loading ? 0.8 : 1,
            boxShadow: loading ? "none" : "0 4px 20px rgba(59,130,246,0.35)",
            fontFamily: "inherit", marginTop: 4,
          }}>
            {loading
              ? (mode === "login" ? "Signing in..." : "Creating account...")
              : (mode === "login" ? "Sign In →" : "Create Account →")}
          </button>
        </form>

        {/* Divider */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "24px 0" }}>
          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.06)" }} />
          <span style={{ fontSize: 11, color: "#475569" }}>
            {mode === "login" ? "New here?" : "Already have an account?"}
          </span>
          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.06)" }} />
        </div>

        <button onClick={switchMode} style={{
          width: "100%", height: 42, borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.08)",
          background: "rgba(255,255,255,0.03)",
          color: "#94a3b8", cursor: "pointer", fontSize: 14,
          fontWeight: 500, transition: "all 150ms", fontFamily: "inherit",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(59,130,246,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "#3b82f6"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.08)"; (e.currentTarget as HTMLButtonElement).style.color = "#94a3b8"; }}
        >
          {mode === "login" ? "Create a free account" : "Sign in instead"}
        </button>

        {/* Features */}
        <div style={{ marginTop: 32, display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            { icon: "🏢", text: "2,000+ companies across all industries" },
            { icon: "🤖", text: "AI resume tailoring + cover letters" },
            { icon: "📊", text: "ATS score + job qualification check" },
          ].map(f => (
            <div key={f.text} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "#475569" }}>
              <span style={{ fontSize: 14 }}>{f.icon}</span> {f.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
