import { useState, useEffect, useRef } from "react";
import { api } from "../api";

const BASE = (import.meta as any).env?.VITE_API_URL || "";

interface Props {
  onSuccess: (user: { id: string; email: string; name: string }) => void;
}

/* ── Animated number counter ── */
function Counter({ to, duration = 1400 }: { to: number; duration?: number }) {
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

/* ── New Splash Screen ── */
function SplashScreen({ onDone }: { onDone: () => void }) {
  const [ready, setReady] = useState(false);
  const [exit, setExit] = useState(false);

  const finish = () => {
    setExit(true);
    setTimeout(onDone, 520);
  };

  useEffect(() => {
    const t1 = setTimeout(() => setReady(true), 60);
    const t2 = setTimeout(finish, 3200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const PARTICLE_COUNT = 22;
  const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => {
    const angle = (i / PARTICLE_COUNT) * 360;
    const dist = 130 + (i % 6) * 30;
    return { angle, dist, i };
  });

  return (
    <div
      className={`splash${ready ? " splash-ready" : ""}${exit ? " exit" : ""}`}
      onClick={finish}
    >
      <div className="splash-glow" />
      <div className="splash-grid-bg" />

      <div className="splash-particles">
        {particles.map(p => (
          <span
            key={p.i}
            className="splash-particle"
            style={{
              ["--sp-a" as any]: `${p.angle}deg`,
              ["--sp-d" as any]: `${p.dist}px`,
              ["--sp-delay" as any]: `${p.i * 0.03}s`,
              ["--sp-drift-delay" as any]: `${p.i * 0.05}s`,
            }}
          />
        ))}
      </div>

      <div className="splash-center">
        <div className="splash-target">
          <svg viewBox="0 0 120 120">
            <circle className="splash-ring" cx="60" cy="60" r="46" />
            <circle className="splash-bull" cx="60" cy="60" r="15" />
          </svg>
          <span className="splash-lock-ring" />
          <span className="splash-lock-ring splash-lock-ring-2" />
        </div>

        <div className="splash-word">
          <h1 className="splash-brand">
            Job <span className="splash-hl">Hunter</span>
          </h1>
          <p className="splash-tagline">Hunt Smarter, Not Harder</p>
        </div>

        <div className="splash-progress">
          <i className="splash-progress-bar" />
        </div>
      </div>

      <div className="splash-skip">Click anywhere to skip</div>
    </div>
  );
}

/* ── Main Auth component ── */
export default function Auth({ onSuccess }: Props) {
  const [showSplash, setShowSplash] = useState(() => !localStorage.getItem("jh_splash_done"));
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName]       = useState("");
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);

  // forgot password
  const [showForgot, setShowForgot]   = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSent, setForgotSent]   = useState(false);

  // reset password (from email link)
  const [resetToken, setResetToken]     = useState<string | null>(null);
  const [resetPw, setResetPw]           = useState("");
  const [resetConfirm, setResetConfirm] = useState("");
  const [resetDone, setResetDone]       = useState(false);
  const [resetEmail, setResetEmail]     = useState("");

  // live stats
  const [jobCount, setJobCount]   = useState(() => parseInt(localStorage.getItem("jh_job_count") || "0") || 0);
  const [liveStats, setLiveStats] = useState<any>(null);

  // parse reset token from URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tok = params.get("reset_token");
    if (tok) { setResetToken(tok); window.history.replaceState({}, "", "/"); }
  }, []);

  // fetch live stats
  useEffect(() => {
    fetch(`${BASE}/api/jobs/count`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.count) { setJobCount(d.count); localStorage.setItem("jh_job_count", String(d.count)); } })
      .catch(() => {});
    fetch(`${BASE}/api/stats/today`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLiveStats(d); })
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

  const handleSplashDone = () => {
    localStorage.setItem("jh_splash_done", "1");
    setShowSplash(false);
  };

  return (
    <>
      {showSplash && <SplashScreen onDone={handleSplashDone} />}

      {/* ── RESET PASSWORD PAGE ── */}
      {resetToken && (
        <div className="auth">
          <div className="auth-main" style={{ flex: 1 }}>
            <div className="auth-card">
              <div className="auth-brand" style={{ marginBottom: 28 }}>
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <circle cx="14" cy="14" r="12" stroke="#2563eb" strokeWidth="2.5" fill="none"/>
                  <circle cx="14" cy="14" r="4.5" fill="#2563eb"/>
                </svg>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-.02em" }}>
                    Job <span style={{ color: "#3b82f6" }}>Hunter</span>
                  </div>
                </div>
              </div>

              {resetDone ? (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                  <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
                  <div className="auth-card-title">Password reset!</div>
                  <p className="auth-card-sub">
                    You can now sign in with your new password{resetEmail ? ` (${resetEmail})` : ""}.
                  </p>
                  <button className="auth-submit" onClick={() => setResetToken(null)}>
                    Go to Sign In →
                  </button>
                </div>
              ) : (
                <>
                  <h1 className="auth-card-title">Set new password</h1>
                  <p className="auth-card-sub">Enter a new password for your account.</p>
                  {error && <div className="auth-err" style={{ marginBottom: 16 }}>⚠️ {error}</div>}
                  <div className="auth-form">
                    <div className="auth-field">
                      <label className="auth-label">New Password</label>
                      <input className="auth-input" type="password" value={resetPw}
                        onChange={e => setResetPw(e.target.value)} placeholder="At least 8 characters" autoFocus />
                    </div>
                    <div className="auth-field">
                      <label className="auth-label">Confirm Password</label>
                      <input className="auth-input" type="password" value={resetConfirm}
                        onChange={e => setResetConfirm(e.target.value)} placeholder="Repeat new password" />
                    </div>
                    <button className="auth-submit" disabled={loading} onClick={async () => {
                      setError("");
                      if (resetPw.length < 8) { setError("Password must be at least 8 characters"); return; }
                      if (resetPw !== resetConfirm) { setError("Passwords don't match"); return; }
                      setLoading(true);
                      try {
                        const r = await api.auth.resetPassword(resetToken!, resetPw);
                        setResetEmail(r.email || "");
                        setResetDone(true);
                      } catch (e: any) { setError(e.message || "Something went wrong"); }
                      finally { setLoading(false); }
                    }}>
                      {loading ? "Resetting…" : "Reset Password →"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── MAIN LOGIN / REGISTER ── */}
      {!resetToken && (
        <div className="auth">

          {/* LEFT — Hero + Features panel */}
          <div className="auth-aside">
            {/* Brand */}
            <div className="auth-brand">
              <svg width="30" height="30" viewBox="0 0 30 30" fill="none">
                <circle cx="15" cy="15" r="13" stroke="#3b82f6" strokeWidth="2.5" fill="none"/>
                <circle cx="15" cy="15" r="5" fill="#2563eb"/>
              </svg>
              <div>
                <div style={{ fontFamily: "var(--f-display)", fontWeight: 700, fontSize: 16, letterSpacing: "-.02em", lineHeight: 1.1 }}>
                  Job <span style={{ color: "#3b82f6" }}>Hunter</span>
                </div>
                <div style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--tx-3)", marginTop: 2 }}>
                  Hunt Smarter
                </div>
              </div>
            </div>

            {/* Hero headline */}
            <h2 className="auth-hero">
              Your AI-powered<br />
              <span style={{ background: "var(--grad)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
                job search engine
              </span>
            </h2>
            <p className="auth-hero-sub">
              Auto-scrape, AI scoring, resume tailoring — all in one dashboard built for serious job seekers.
            </p>

            {/* Features */}
            <ul className="auth-features">
              {[
                {
                  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>,
                  title: "Auto-scrape on your schedule",
                  desc: "New jobs arrive every hour automatically, or trigger a run anytime with one click.",
                },
                {
                  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/></svg>,
                  title: "AI fit score on every job",
                  desc: "Each job card shows a 0–100 match score. Filter by threshold.",
                },
                {
                  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/></svg>,
                  title: "Resume tailored per job",
                  desc: "ATS score before & after. Keywords rewritten for each specific JD.",
                },
                {
                  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
                  title: "Auto Apply — Coming Soon",
                  desc: "Review, tailor & submit — your application queue, managed for you.",
                },
              ].map(f => (
                <li key={f.title}>
                  <div className="auth-feat-ico">{f.icon}</div>
                  <div>
                    <div style={{ fontWeight: 600, color: "var(--tx)", marginBottom: 2 }}>{f.title}</div>
                    <div style={{ fontSize: 12.5, color: "var(--tx-3)", lineHeight: 1.5 }}>{f.desc}</div>
                  </div>
                </li>
              ))}
            </ul>

            {/* Live stats */}
            <div className="auth-stats">
              <div className="auth-stat">
                <b>{jobCount > 0 ? <><Counter to={jobCount} />+</> : "—"}</b>
                <span>Jobs scraped</span>
              </div>
              <div className="auth-stat">
                <b>{liveStats ? liveStats.added_today : "—"}</b>
                <span>Added today</span>
              </div>
              <div className="auth-stat">
                <b>10+</b>
                <span>Job boards</span>
              </div>
            </div>
          </div>

          {/* RIGHT — Login form */}
          <div className="auth-main">
            <div className="auth-card">
              <h1 className="auth-card-title">
                {mode === "login" ? "Welcome back" : "Create account"}
              </h1>
              <p className="auth-card-sub">
                {mode === "login"
                  ? "Sign in to your AI job search dashboard."
                  : "Start finding and winning jobs with AI."}
              </p>

              {/* Tab toggle with animated pill */}
              <div className="auth-tabs">
                <div className={`auth-tab-pill${mode === "register" ? " auth-tab-right" : ""}`} />
                <button
                  type="button"
                  className={mode === "login" ? "auth-tab-on" : ""}
                  onClick={() => { setMode("login"); setError(""); setShowForgot(false); }}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  className={mode === "register" ? "auth-tab-on" : ""}
                  onClick={() => { setMode("register"); setError(""); setShowForgot(false); }}
                >
                  Register
                </button>
              </div>

              {/* Form */}
              <form className="auth-form" onSubmit={handleSubmit}>
                {mode === "register" && (
                  <div className="auth-field">
                    <label className="auth-label">Full Name</label>
                    <input className="auth-input" type="text" value={name}
                      onChange={e => setName(e.target.value)} placeholder="Jagadish Reddy" required autoFocus />
                  </div>
                )}

                <div className="auth-field">
                  <label className="auth-label">Email Address</label>
                  <input className="auth-input" type="email" value={email}
                    onChange={e => setEmail(e.target.value)} placeholder="you@example.com"
                    required autoFocus={mode === "login"} />
                </div>

                <div className="auth-field">
                  <div className="auth-pass-row">
                    <label className="auth-label">Password</label>
                    {mode === "login" && (
                      <button type="button" className="auth-forgot"
                        onClick={() => setShowForgot(f => !f)}>
                        Forgot password?
                      </button>
                    )}
                  </div>
                  <input className="auth-input" type="password" value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder={mode === "register" ? "At least 8 characters" : "Your password"} required />
                </div>

                {/* Forgot password panel */}
                {showForgot && mode === "login" && (
                  <div style={{ background: "rgba(37,99,235,.08)", border: "1px solid rgba(37,99,235,.22)", borderRadius: "var(--r)", padding: "14px 16px" }}>
                    {forgotSent ? (
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 28, marginBottom: 8 }}>📬</div>
                        <div style={{ fontWeight: 700, fontSize: 13, color: "var(--tx)", marginBottom: 4 }}>Check your inbox!</div>
                        <div style={{ fontSize: 12.5, color: "var(--tx-2)", lineHeight: 1.6 }}>
                          If <strong>{forgotEmail}</strong> is registered, a reset link is on its way.
                        </div>
                        <button type="button" style={{ marginTop: 10, fontSize: 12, color: "var(--cyan)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}
                          onClick={() => { setForgotSent(false); setForgotEmail(""); }}>
                          Try a different email
                        </button>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontWeight: 700, fontSize: 12.5, color: "var(--tx)", marginBottom: 10 }}>🔑 Reset your password</div>
                        <div style={{ display: "flex", gap: 8 }}>
                          <input type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                            placeholder="your@email.com" className="auth-input" style={{ flex: 1, height: 36 }} />
                          <button type="button" disabled={forgotLoading}
                            onClick={async () => {
                              if (!forgotEmail.trim()) return;
                              setForgotLoading(true);
                              try { await api.auth.forgotPassword(forgotEmail.trim()); setForgotSent(true); }
                              catch { setForgotSent(true); }
                              finally { setForgotLoading(false); }
                            }}
                            style={{ height: 36, padding: "0 14px", borderRadius: "var(--r-sm)", border: "none", background: "var(--grad)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: forgotLoading ? "not-allowed" : "pointer", whiteSpace: "nowrap", opacity: forgotLoading ? 0.7 : 1 }}>
                            {forgotLoading ? "Sending…" : "Send Link"}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {error && <div className="auth-err">⚠️ {error}</div>}

                <button type="submit" className="auth-submit" disabled={loading}>
                  {loading
                    ? (mode === "login" ? "Signing in…" : "Creating account…")
                    : (mode === "login" ? "Sign In →" : "Create Account →")}
                </button>
              </form>

              <div className="auth-foot">
                {mode === "login" ? "No account? " : "Already registered? "}
                <button type="button"
                  onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setShowForgot(false); }}>
                  {mode === "login" ? "Register free" : "Sign in"}
                </button>
              </div>
            </div>
          </div>

        </div>
      )}
    </>
  );
}
