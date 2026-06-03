import { useState, useEffect, useRef } from "react";
import { api } from "../api";

interface Props {
  onSuccess: (user: { id: string; email: string; name: string }) => void;
}

/* ── Bullseye logo ── */
function BullseyeLogo({ size = 36, color = "#2563eb" }: { size?: number; color?: string }) {
  const c = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      <circle cx={c} cy={c} r={c - 2.5} stroke={color} strokeWidth={size * 0.07} fill="none" />
      <circle cx={c} cy={c} r={c * 0.28} fill={color} />
    </svg>
  );
}

/* ── Animated number counter ── */
function Counter({ to, duration = 1400 }: { to: number; duration?: number }) {
  const [val, setVal] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (to === 0) return;
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
      setVal(Math.round(from + (to - from) * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
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

  // Fetch real job count (public — no auth needed just for count)
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
      .catch(() => {}); // silent — show cached or nothing
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
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        .auth-root * { box-sizing: border-box; }
        .auth-inp {
          width: 100%; height: 46px; padding: 0 14px;
          border-radius: 10px; font-size: 14px; font-family: inherit;
          background: #f8fafc; border: 1.5px solid #e2e8f0; color: #0f172a;
          outline: none; transition: all .15s;
        }
        .auth-inp:focus {
          background: #fff; border-color: #2563eb;
          box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
        }
        .auth-inp::placeholder { color: #cbd5e1; }
        .auth-btn-primary {
          width: 100%; height: 48px; border: none; border-radius: 12px;
          background: linear-gradient(135deg,#1e40af,#2563eb,#0284c7);
          color: #fff; font-size: 15px; font-weight: 700;
          cursor: pointer; letter-spacing: -0.01em; font-family: inherit;
          box-shadow: 0 4px 18px rgba(37,99,235,0.35);
          transition: all .15s; margin-top: 6px;
        }
        .auth-btn-primary:hover:not(:disabled) {
          box-shadow: 0 6px 26px rgba(37,99,235,0.5);
          transform: translateY(-1px);
        }
        .auth-btn-primary:disabled { opacity: .65; cursor: not-allowed; }
        .auth-tab { flex: 1; height: 38px; border: none; border-radius: 9px; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: all .2s; font-family: inherit; }
        .auth-feature-pill {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 5px 11px; border-radius: 20px;
          font-size: 11.5px; font-weight: 500; color: #475569;
          background: #f1f5f9; border: 1px solid #e2e8f0;
        }
      `}</style>

      <div className="auth-root" style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "linear-gradient(145deg, #f0f4ff 0%, #fafbff 55%, #f0fbff 100%)",
        fontFamily: "'Inter', system-ui, sans-serif", padding: "24px",
      }}>
        {/* Subtle background shapes */}
        <div style={{ position: "fixed", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: "-10%", right: "-5%", width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle,rgba(37,99,235,0.06) 0%,transparent 70%)" }} />
          <div style={{ position: "absolute", bottom: "-5%", left: "-5%", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle,rgba(14,165,233,0.06) 0%,transparent 70%)" }} />
        </div>

        {/* Card */}
        <div style={{
          position: "relative", zIndex: 1,
          width: "100%", maxWidth: 440,
          background: "#ffffff",
          borderRadius: 20, padding: "40px 40px 32px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 20px 60px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)",
        }}>

          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 30 }}>
            <BullseyeLogo size={38} color="#2563eb" />
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.03em", lineHeight: 1 }}>
                Job <span style={{ color: "#2563eb" }}>Hunter</span>
              </div>
              <div style={{ fontSize: 9, letterSpacing: "0.14em", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600, marginTop: 3 }}>
                Hunt Smarter, Not Harder
              </div>
            </div>
          </div>

          {/* Heading */}
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", margin: "0 0 5px", letterSpacing: "-0.03em" }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: "0 0 24px", lineHeight: 1.5 }}>
            {mode === "login"
              ? "Sign in to your AI job search dashboard"
              : "Start hunting smarter with AI"}
          </p>

          {/* Tab toggle */}
          <div style={{ display: "flex", background: "#f1f5f9", borderRadius: 12, padding: 4, marginBottom: 24, gap: 4 }}>
            {(["login", "register"] as const).map(m => (
              <button key={m} className="auth-tab"
                onClick={() => { setMode(m); setError(""); setShowForgot(false); }}
                style={{
                  background: mode === m ? "#fff" : "transparent",
                  color: mode === m ? "#0f172a" : "#94a3b8",
                  boxShadow: mode === m ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
                }}>
                {m === "login" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {mode === "register" && (
              <div>
                <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Full Name</label>
                <input className="auth-inp" type="text" value={name}
                  onChange={e => setName(e.target.value)} placeholder="Jane Smith" required autoFocus />
              </div>
            )}

            <div>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Email Address</label>
              <input className="auth-inp" type="email" value={email}
                onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required autoFocus={mode === "login"} />
            </div>

            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <label style={{ fontSize: 12.5, fontWeight: 600, color: "#374151" }}>Password</label>
                {mode === "login" && (
                  <button type="button" onClick={() => setShowForgot(f => !f)}
                    style={{ background: "none", border: "none", fontSize: 12, color: "#2563eb", cursor: "pointer", padding: 0, fontFamily: "inherit", fontWeight: 500 }}>
                    Forgot password?
                  </button>
                )}
              </div>
              <input className="auth-inp" type="password" value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={mode === "register" ? "At least 8 characters" : "Your password"} required />
            </div>

            {showForgot && mode === "login" && (
              <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 10, padding: "12px 14px", fontSize: 12.5, color: "#1e40af", lineHeight: 1.65 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>🔑 Reset your password</div>
                <code style={{ display: "block", background: "#dbeafe", padding: "7px 10px", borderRadius: 7, fontSize: 11, color: "#1e3a8a", fontFamily: "monospace" }}>
                  cd backend &amp;&amp; python reset_password.py
                </code>
              </div>
            )}

            {error && (
              <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "11px 14px", fontSize: 13, color: "#dc2626", display: "flex", alignItems: "center", gap: 8 }}>
                ⚠️ {error}
              </div>
            )}

            <button type="submit" className="auth-btn-primary" disabled={loading}>
              {loading
                ? (mode === "login" ? "Signing in…" : "Creating account…")
                : (mode === "login" ? "Sign In →" : "Create Account →")}
            </button>
          </form>

          {/* Switch mode */}
          <p style={{ textAlign: "center", fontSize: 13, color: "#94a3b8", margin: "18px 0 20px" }}>
            {mode === "login" ? "No account? " : "Already registered? "}
            <button type="button"
              onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
              style={{ background: "none", border: "none", color: "#2563eb", fontWeight: 600, cursor: "pointer", fontSize: 13, padding: 0, fontFamily: "inherit" }}>
              {mode === "login" ? "Register free" : "Sign in"}
            </button>
          </p>

          {/* Divider */}
          <div style={{ height: 1, background: "#f1f5f9", margin: "0 -8px 20px" }} />

          {/* Stats / features row */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
            {jobCount > 0 && (
              <span className="auth-feature-pill">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
                </svg>
                <Counter to={jobCount} /> jobs indexed
              </span>
            )}
            <span className="auth-feature-pill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round">
                <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
              </svg>
              Greenhouse · Lever · Ashby
            </span>
            <span className="auth-feature-pill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span style={{ color: "#10b981" }}>Auto Apply</span> coming soon
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
