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

/* ── Splash Screen ── */
function SplashScreen({ onDone }: { onDone: () => void }) {
  const [ready, setReady] = useState(false);
  const [exit, setExit] = useState(false);

  const finish = () => { setExit(true); setTimeout(onDone, 520); };

  useEffect(() => {
    const t1 = setTimeout(() => setReady(true), 60);
    const t2 = setTimeout(finish, 3200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const PARTICLE_COUNT = 22;
  const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
    angle: (i / PARTICLE_COUNT) * 360,
    dist: 130 + (i % 6) * 30,
    i,
  }));

  return (
    <div
      className={`splash${ready ? " splash-ready" : ""}${exit ? " exit" : ""}`}
      onClick={finish}
    >
      <div className="splash-glow" />
      <div className="splash-grid-bg" />
      <div className="splash-particles">
        {particles.map(p => (
          <span key={p.i} className="splash-particle" style={{
            ["--sp-a" as any]: `${p.angle}deg`,
            ["--sp-d" as any]: `${p.dist}px`,
            ["--sp-delay" as any]: `${p.i * 0.03}s`,
            ["--sp-drift-delay" as any]: `${p.i * 0.05}s`,
          }} />
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
          <h1 className="splash-brand">Job <span className="splash-hl">Hunter</span></h1>
          <p className="splash-tagline">Hunt Smarter, Not Harder</p>
        </div>
        <div className="splash-progress"><i className="splash-progress-bar" /></div>

        {/* Built by Jay badge */}
        <div style={{
          marginTop: 20, display: "inline-flex", alignItems: "center", gap: 6,
          background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 20, padding: "5px 14px",
        }}>
          <span style={{ color: "#a78bfa", fontSize: 12 }}>✦</span>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: "rgba(255,255,255,0.65)", letterSpacing: ".06em" }}>Built by Jay</span>
        </div>
      </div>

      <div className="splash-skip">Click anywhere to skip</div>
    </div>
  );
}

/* ── Main Auth component ── */
export default function Auth({ onSuccess }: Props) {
  const [showSplash, setShowSplash] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName]         = useState("");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  const [showForgot, setShowForgot]     = useState(false);
  const [forgotEmail, setForgotEmail]   = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSent, setForgotSent]     = useState(false);

  const [resetToken, setResetToken]       = useState<string | null>(null);
  const [resetPw, setResetPw]             = useState("");
  const [resetConfirm, setResetConfirm]   = useState("");
  const [resetDone, setResetDone]         = useState(false);
  const [resetEmail, setResetEmail]       = useState("");

  const [jobCount, setJobCount] = useState(() => parseInt(localStorage.getItem("jh_job_count") || "0") || 0);
  const [liveStats, setLiveStats] = useState<any>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tok = params.get("reset_token");
    if (tok) { setResetToken(tok); window.history.replaceState({}, "", "/"); }
  }, []);

  useEffect(() => {
    fetch(`${BASE}/api/jobs/count`).then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.count) { setJobCount(d.count); localStorage.setItem("jh_job_count", String(d.count)); } }).catch(() => {});
    fetch(`${BASE}/api/stats/today`).then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLiveStats(d); }).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || (mode === "register" && !name)) return;
    setLoading(true); setError("");

    try {
      const result = mode === "login"
        ? await api.auth.login(email, password)
        : await api.auth.register(email, password, name);

      if (result?.token && result?.user) {
        localStorage.setItem("jh_token", result.token);
        localStorage.setItem("jh_user", JSON.stringify(result.user));
        onSuccess(result.user);
      }
    } catch (err: any) {
      setError(err.message || "Authentication failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  const getPasswordStrength = (pass: string) => {
    if (!pass) return 0;
    let score = 0;
    if (pass.length > 7) score++;
    if (/[A-Z]/.test(pass) && /[a-z]/.test(pass)) score++;
    if (/[0-9]/.test(pass)) score++;
    if (/[^A-Za-z0-9]/.test(pass)) score++;
    if (pass.length > 12) score++;
    return score; // 0 to 5
  };
  const pwdScore = getPasswordStrength(password);
  const pwdColors = ["#e2e8f0", "#ef4444", "#f59e0b", "#eab308", "#22c55e", "#10b981"];
  const pwdLabels = ["", "Weak", "Fair", "Good", "Strong", "Excellent"];

  const S = styles;

  return (
    <>
      {showSplash && <SplashScreen onDone={() => setShowSplash(false)} />}

      {/* RESET PASSWORD */}
      {resetToken && (
        <div style={S.page}>
          <div style={S.resetCard}>
            <Brand />
            {resetDone ? (
              <div style={{ textAlign: "center", paddingTop: 8 }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>✅</div>
                <div style={S.heading}>Password reset!</div>
                <p style={S.sub}>You can now sign in{resetEmail ? ` as ${resetEmail}` : ""}.</p>
                <button style={S.btn} onClick={() => setResetToken(null)}>Go to Sign In →</button>
              </div>
            ) : (
              <>
                <div style={S.heading}>Set new password</div>
                <p style={S.sub}>Enter a new password for your account.</p>
                {error && <div style={S.errBox}>⚠️ {error}</div>}
                <Field label="New Password">
                  <input style={S.input} type="password" value={resetPw} onChange={e => setResetPw(e.target.value)} placeholder="At least 8 characters" autoFocus />
                </Field>
                <Field label="Confirm Password">
                  <input style={S.input} type="password" value={resetConfirm} onChange={e => setResetConfirm(e.target.value)} placeholder="Repeat new password" />
                </Field>
                <button style={{ ...S.btn, marginTop: 8, opacity: loading ? 0.7 : 1 }} disabled={loading}
                  onClick={async () => {
                    setError("");
                    if (resetPw.length < 8) { setError("Password must be at least 8 characters"); return; }
                    if (resetPw !== resetConfirm) { setError("Passwords don't match"); return; }
                    setLoading(true);
                    try { const r = await api.auth.resetPassword(resetToken!, resetPw); setResetEmail(r.email||""); setResetDone(true); }
                    catch (e: any) { setError(e.message||"Something went wrong"); }
                    finally { setLoading(false); }
                  }}>
                  {loading ? "Resetting…" : "Reset Password →"}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* MAIN LOGIN */}
      {!resetToken && (
        <div style={S.page}>

          {/* ── LEFT: Brand / Features ── */}
          <div style={S.aside} className="auth-panel">
            <Brand light />

            <h1 style={{
              fontSize: 60, fontWeight: 900, lineHeight: 1.06,
              letterSpacing: "-.04em", marginBottom: 20,
              background: "linear-gradient(135deg, #0f172a 0%, #7c3aed 60%, #06b6d4 100%)",
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
            }}>Hunt smarter,<br />not harder.</h1>
            <p style={{
              fontSize: 17, color: "#475569", lineHeight: 1.7,
              maxWidth: "38ch", marginBottom: 0,
            }}>
              Scrape thousands of roles, auto-score every match against your profile,
              and tailor your resume in one click — all from one keyboard-first workspace.
            </p>

            {/* What's waiting for you */}
            <div style={{ marginTop: 32 }}>
              <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "#94a3b8", marginBottom: 22 }}>
                What's waiting for you
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
                {[
                  {
                    icon: "🕐",
                    title: "Auto-scrape on your schedule",
                    desc: "New jobs arrive every hour automatically, or trigger a run anytime with one click.",
                    badge: null,
                  },
                  {
                    icon: "🎯",
                    title: "AI fit score on every job",
                    desc: "Each job card shows a 0–100 match score. Filter by threshold — only open what's worth it.",
                    badge: null,
                  },
                  {
                    icon: "📄",
                    title: "Resume tailored per job",
                    desc: "ATS score before & after. Keywords rewritten for each specific JD.",
                    badge: null,
                  },
                  {
                    icon: "⚡",
                    title: "Auto Apply",
                    desc: "Review, tailor & submit — your application queue, managed for you.",
                    badge: "Coming Soon",
                  },
                ].map(f => (
                  <div key={f.title} style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                    <div style={{ ...S.featureIco, width: 48, height: 48, fontSize: 22, flexShrink: 0 }}>{f.icon}</div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
                        <span style={{ fontSize: 18, fontWeight: 700, color: "#0f172a" }}>{f.title}</span>
                        {f.badge && (
                          <span style={{ fontSize: 11, fontWeight: 700, background: "rgba(124,58,237,0.12)", color: "#7c3aed", border: "1px solid rgba(124,58,237,0.28)", borderRadius: 6, padding: "3px 10px", letterSpacing: ".04em", textTransform: "uppercase" }}>
                            {f.badge}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 15.5, color: "#64748b", lineHeight: 1.65 }}>{f.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>


            {/* LIVE grid */}
            <div style={{ marginTop: 36 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: ".14em", textTransform: "uppercase", color: "#64748b" }}>Live</span>
                <span style={{ position: "relative", display: "inline-flex", width: 10, height: 10 }}>
                  <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#22c55e", animation: "livePip2 1.4s ease-in-out infinite" }} />
                  <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#22c55e" }} />
                </span>
                <style>{`
                  @keyframes livePip2{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(2.4);opacity:0}}
                  .auth-panel::-webkit-scrollbar { display: none; }
                  .auth-panel { scrollbar-width: none; -ms-overflow-style: none; }
                `}</style>
              </div>
              <div style={S.liveGrid}>
                {[
                  { value: liveStats?.last_scrape_mins_ago != null ? (liveStats.last_scrape_mins_ago < 60 ? `${liveStats.last_scrape_mins_ago}m ago` : `${Math.round(liveStats.last_scrape_mins_ago/60)}h ago`) : "—", label: "Last scrape", color: "#64748b" },
                  { value: jobCount > 0 ? <><Counter to={jobCount} />+</> : "6,831+", label: "Jobs scraped", color: "#7c3aed" },
                  { value: liveStats?.added_today ?? "0", label: "New today", color: "#06b6d4" },
                  { value: "10+", label: "Job boards", color: "#f59e0b" },
                  { value: "⚡", label: "Auto Apply", color: "#10b981" },
                ].map((s, i) => (
                  <div key={s.label} style={{ ...S.liveCell, borderLeft: i > 0 ? "1px solid rgba(0,0,0,0.07)" : "none", padding: "16px 8px" }}>
                    <div style={{ ...S.liveCellVal, fontSize: 26, color: s.color, fontWeight: 900 }}>{s.value}</div>
                    <div style={{ ...S.liveCellLabel, fontSize: 12 }}>{s.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── RIGHT: Form ── */}
          <div style={{ ...S.formSide, position: "relative" }} className="auth-panel">
            {/* Bottom-right credit */}
            <div style={{
              position: "absolute", bottom: 20, right: 24,
              display: "flex", alignItems: "center", gap: 5,
            }}>
              <span style={{ color: "#7c3aed", fontSize: 13 }}>✦</span>
              <span style={{
                fontSize: 12, fontWeight: 700, letterSpacing: ".05em",
                background: "linear-gradient(120deg, #7c3aed, #06b6d4)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
              }}>Built by Jay</span>
            </div>

            <div style={S.card}>

              {/* Premium heading block */}
              <div style={{ marginBottom: 32 }}>

                {/* Tagline */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                    background: "#7c3aed", boxShadow: "0 0 10px rgba(124,58,237,0.7)",
                  }} />
                  <span style={{
                    fontSize: 11.5, fontWeight: 700, letterSpacing: ".18em",
                    textTransform: "uppercase", color: "#7c3aed",
                  }}>Welcome</span>
                </div>

                {/* Main title — very big */}
                <h1 style={{
                  fontSize: 52, fontWeight: 800, letterSpacing: "-.03em",
                  color: "#0f172a", margin: "0 0 16px", lineHeight: 1.12,
                }}>
                  Your digital career agent is
                  <br />
                  <em style={{
                    fontFamily: "Georgia, 'Times New Roman', serif",
                    fontStyle: "italic", fontWeight: 400,
                    color: "#7c3aed", letterSpacing: "-.01em",
                  }}>fully prepared.</em>
                </h1>

                {/* Subtext */}
                <p style={{ fontSize: 15, color: "#64748b", margin: 0, lineHeight: 1.7 }}>
                  Access your current dashboard or register in under 30 seconds
                  to begin your automated outreach campaign immediately.
                </p>
              </div>


              {/* Tab toggle */}
              <div style={S.tabs}>
                <div style={{ ...S.tabPill, transform: mode === "register" ? "translateX(100%)" : "translateX(0)" }} />
                {(["login", "register"] as const).map(m => (
                  <button key={m} type="button"
                    style={{ ...S.tabBtn, color: mode === m ? "#fff" : "#64748b" }}
                    onClick={() => { setMode(m); setError(""); setShowForgot(false); }}>
                    {m === "login" ? "Login" : "Register"}
                  </button>
                ))}
              </div>


              <div style={{ display: "flex", gap: 10, marginTop: 24, marginBottom: 16 }}>
                <button type="button" onClick={() => window.location.href = `${BASE}/api/auth/google/login?action=${mode}`} style={{ flex: 1, height: 44, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, color: "#0f172a", fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: "0 1px 2px rgba(0,0,0,0.05)", transition: "background 0.2s" }} onMouseOver={e => e.currentTarget.style.background = "#f8fafc"} onMouseOut={e => e.currentTarget.style.background = "#fff"}>
                  <img src="https://www.svgrepo.com/show/475656/google-color.svg" width={18} alt="Google" /> Google
                </button>
                <button type="button" onClick={() => window.location.href = `${BASE}/api/auth/github/login?action=${mode}`} style={{ flex: 1, height: 44, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, color: "#0f172a", fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: "0 1px 2px rgba(0,0,0,0.05)", transition: "background 0.2s" }} onMouseOver={e => e.currentTarget.style.background = "#f8fafc"} onMouseOut={e => e.currentTarget.style.background = "#fff"}>
                  <svg width={18} viewBox="0 0 98 96" xmlns="http://www.w3.org/2000/svg"><path fillRule="evenodd" clipRule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z" fill="#24292f"/></svg> GitHub
                </button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
                <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
                <div style={{ fontSize: 12, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>Or continue with email</div>
                <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
              </div>

              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Full Name — always reserves space, hidden in login mode */}
                <div style={{
                  overflow: "hidden",
                  maxHeight: mode === "register" ? "80px" : "0px",
                  opacity: mode === "register" ? 1 : 0,
                  transition: "max-height 0.25s ease, opacity 0.2s ease",
                }}>
                  <Field label="Full Name">
                    <input style={S.input} type="text" value={name} onChange={e => setName(e.target.value)}
                      placeholder="Your name" required={mode === "register"} autoFocus={mode === "register"} />
                  </Field>
                </div>


                <Field label="Email">
                  <input style={S.input} type="email" value={email} onChange={e => setEmail(e.target.value)}
                    placeholder="alex@hey.com" required autoFocus={mode === "login"} />
                </Field>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <label style={S.label}>Password</label>
                    {mode === "login" && (
                      <button type="button" style={S.forgotLink} onClick={() => setShowForgot(f => !f)}>
                        Forgot password?
                      </button>
                    )}
                  </div>
                  <input style={S.input} type="password" value={password} onChange={e => setPassword(e.target.value)}
                    placeholder={mode === "register" ? "At least 8 characters" : "••••••••"} required />
                  {mode === "register" && password.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ display: "flex", gap: 4, height: 4, marginBottom: 6 }}>
                        {[1, 2, 3, 4, 5].map(i => (
                          <div key={i} style={{ flex: 1, borderRadius: 2, background: i <= pwdScore ? pwdColors[pwdScore] : "#e2e8f0", transition: "background 0.3s" }} />
                        ))}
                      </div>
                      <div style={{ fontSize: 12, color: pwdColors[pwdScore], fontWeight: 500, textAlign: "right" }}>
                        {pwdLabels[pwdScore]}
                      </div>
                    </div>
                  )}
                </div>

                {/* Forgot password panel */}
                {showForgot && mode === "login" && (
                  <div style={S.forgotBox}>
                    {forgotSent ? (
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 26, marginBottom: 6 }}>📬</div>
                        <div style={{ fontWeight: 700, fontSize: 13, color: "#1e40af", marginBottom: 4 }}>Check your inbox!</div>
                        <div style={{ fontSize: 12.5, color: "#3b82f6", lineHeight: 1.6 }}>
                          If <strong>{forgotEmail}</strong> is registered, a reset link is on its way.
                        </div>
                        <button type="button" style={{ marginTop: 8, fontSize: 12, color: "#2563eb", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}
                          onClick={() => { setForgotSent(false); setForgotEmail(""); }}>Try a different email</button>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontWeight: 700, fontSize: 12.5, color: "#1e40af", marginBottom: 8 }}>🔑 Reset your password</div>
                        <div style={{ display: "flex", gap: 8 }}>
                          <input type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                            placeholder="your@email.com" style={{ ...S.input, flex: 1, height: 36, fontSize: 13 }} />
                          <button type="button" disabled={forgotLoading}
                            onClick={async () => {
                              if (!forgotEmail.trim()) return;
                              setForgotLoading(true);
                              try { await api.auth.forgotPassword(forgotEmail.trim()); setForgotSent(true); }
                              catch { setForgotSent(true); }
                              finally { setForgotLoading(false); }
                            }}
                            style={{ height: 36, padding: "0 14px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#7c3aed,#06b6d4)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: forgotLoading ? "not-allowed" : "pointer", whiteSpace: "nowrap", opacity: forgotLoading ? 0.7 : 1 }}>
                            {forgotLoading ? "Sending…" : "Send Link"}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {error && <div style={S.errBox}>⚠️ {error}</div>}

                <button type="submit" disabled={loading} style={{ ...S.btn, opacity: loading ? 0.75 : 1 }}>
                  {loading
                    ? (mode === "login" ? "Signing in…" : "Creating account…")
                    : (mode === "login" ? "Sign In ↵" : "Create Account →")}
                </button>
              </form>

              <p style={{ textAlign: "center", fontSize: 13, color: "#94a3b8", marginTop: 18 }}>
                {mode === "login" ? "New here? " : "Already registered? "}
                <button type="button" style={{ background: "none", border: "none", color: "#7c3aed", fontWeight: 600, cursor: "pointer", fontSize: 13 }}
                  onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setShowForgot(false); }}>
                  {mode === "login" ? "Create an account" : "Sign in"}
                </button>
              </p>

            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ── Brand mark ── */
function Brand({ light }: { light?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: light ? 40 : 28 }}>
      <svg width="44" height="44" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="14" stroke="#7c3aed" strokeWidth="2.5" fill="none" />
        <circle cx="16" cy="16" r="5" fill="#7c3aed" />
      </svg>
      <div>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-.02em", color: "#0f172a" }}>
          Job <span style={{ color: "#7c3aed" }}>Hunter</span>
        </div>
      </div>


    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={styles.label}>{label}</label>
      {children}
    </div>
  );
}

/* ── Styles ── */
const styles = {
  page: {
    display: "flex", height: "100%", overflowY: "auto", fontFamily: "'Inter', system-ui, sans-serif",
    background: "#f8f7f4", flexWrap: "wrap",
  } as React.CSSProperties,

  aside: {
    flex: "1 1 500px", minWidth: 320,
    background: "linear-gradient(135deg, #ede9fe 0%, #f0f9ff 40%, #f8f7f4 100%)",
    padding: "52px 60px",
    display: "flex", flexDirection: "column", justifyContent: "center",
    borderRight: "1px solid rgba(0,0,0,0.07)",
    boxSizing: "border-box" as const,
  } as React.CSSProperties,

  hero: {
    fontSize: 38, fontWeight: 900, color: "#0f172a",
    lineHeight: 1.15, letterSpacing: "-.03em", marginBottom: 14,
  } as React.CSSProperties,

  heroSub: {
    fontSize: 14, color: "#475569", lineHeight: 1.65, maxWidth: "36ch",
  } as React.CSSProperties,

  featureIco: {
    width: 34, height: 34, borderRadius: 10,
    background: "rgba(124,58,237,0.10)", border: "1px solid rgba(124,58,237,0.18)",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: 16, flexShrink: 0,
  } as React.CSSProperties,

  statNum: {
    fontSize: 28, fontWeight: 900, color: "#7c3aed",
    letterSpacing: "-.03em", lineHeight: 1,
  } as React.CSSProperties,

  statLabel: {
    fontSize: 11.5, color: "#94a3b8", marginTop: 3, fontWeight: 500,
  } as React.CSSProperties,

  liveGrid: {
    display: "flex", borderRadius: 10, overflow: "hidden",
    border: "1px solid rgba(0,0,0,0.08)", background: "#fff",
  } as React.CSSProperties,

  liveCell: {
    flex: 1, padding: "11px 6px", textAlign: "center" as const,
  },

  liveCellVal: {
    fontSize: 16, fontWeight: 800, color: "#0f172a",
    letterSpacing: "-.02em", lineHeight: 1.2,
  } as React.CSSProperties,

  liveCellLabel: {
    fontSize: 10, color: "#94a3b8", marginTop: 3, fontWeight: 500, lineHeight: 1.3,
  } as React.CSSProperties,

  formSide: {
    flex: "1 1 400px", minWidth: 320,
    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
    padding: "60px 40px", background: "#f8f7f4",
    boxSizing: "border-box" as const,
  } as React.CSSProperties,

  card: {
    width: "100%", maxWidth: 480,
  } as React.CSSProperties,

  resetCard: {
    background: "#fff", borderRadius: 20, padding: "40px 44px",
    width: "100%", maxWidth: 420, boxShadow: "0 8px 40px rgba(0,0,0,0.10)",
    margin: "auto",
  } as React.CSSProperties,

  tabs: {
    position: "relative" as const, display: "flex",
    background: "#f1f5f9", borderRadius: 12, padding: 4, marginBottom: 24,
    overflow: "hidden",
  },

  tabPill: {
    position: "absolute" as const, top: 4, left: 4,
    width: "calc(50% - 4px)", height: "calc(100% - 8px)",
    background: "linear-gradient(120deg, #7c3aed, #06b6d4)",
    borderRadius: 9, transition: "transform .25s cubic-bezier(.34,1.56,.64,1)",
    boxShadow: "0 4px 14px rgba(124,58,237,0.3)",
  } as React.CSSProperties,

  tabBtn: {
    flex: 1, padding: "13px", border: "none", background: "transparent",
    fontSize: 15, fontWeight: 600, cursor: "pointer", borderRadius: 9,
    transition: "color .18s", zIndex: 1, position: "relative" as const,
  },

  label: {
    display: "block", fontSize: 14, fontWeight: 600,
    color: "#374151", marginBottom: 8,
  } as React.CSSProperties,

  input: {
    width: "100%", height: 54, padding: "0 18px",
    borderRadius: 12, fontSize: 15.5,
    background: "#fff", border: "1.5px solid #e2e8f0",
    color: "#0f172a", outline: "none",
    fontFamily: "'Inter', system-ui, sans-serif",
    transition: "border-color .15s, box-shadow .15s",
    boxSizing: "border-box" as const,
  },

  btn: {
    width: "100%", height: 54, borderRadius: 14, border: "none",
    background: "linear-gradient(120deg, #7c3aed 0%, #06b6d4 100%)",
    color: "#fff", fontSize: 16, fontWeight: 700,
    cursor: "pointer", letterSpacing: "-.01em",
    boxShadow: "0 4px 24px rgba(124,58,237,0.4)",
    transition: "all .15s", fontFamily: "inherit",
  } as React.CSSProperties,

  forgotLink: {
    background: "none", border: "none", fontSize: 12.5,
    color: "#7c3aed", cursor: "pointer", fontWeight: 600,
    fontFamily: "inherit", padding: 0,
  } as React.CSSProperties,

  forgotBox: {
    background: "#eff6ff", border: "1px solid #bfdbfe",
    borderRadius: 10, padding: "14px 16px",
  } as React.CSSProperties,

  errBox: {
    background: "#fef2f2", border: "1px solid #fecaca",
    borderRadius: 10, padding: "11px 14px",
    fontSize: 13, color: "#dc2626",
  } as React.CSSProperties,

  heading: {
    fontSize: 24, fontWeight: 800, color: "#0f172a",
    letterSpacing: "-.03em", marginBottom: 6,
  } as React.CSSProperties,

  sub: {
    fontSize: 14, color: "#64748b", marginBottom: 20, lineHeight: 1.5,
  } as React.CSSProperties,
};
