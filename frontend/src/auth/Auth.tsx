// Auth page: intro splash, left hero (headline, feature rows, laptop
// illustration, live stats), right login / register / reset card.
// Drawn at a 1728×911 reference and zoomed to fit the screen (see zoom.ts).
import React, { useEffect, useState } from "react";
import { api, BASE } from "../api";
import { ROLE_GROUPS } from "../components/JobPreferencesModal";
import { Modal } from "./Modal";
import "./auth.css";

export type AuthUser = { id: string; email: string; name: string; status?: string };
type Mode = "login" | "register";

const STRENGTH = ["", "Weak", "Fair", "Good", "Strong", "Excellent"];
const STRENGTH_C = ["#E2E8F0", "#EF4444", "#F59E0B", "#EAB308", "#22C55E", "#10B981"];
function strength(p: string) { let s = 0; if (p.length > 7) s++; if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++; if (/\d/.test(p)) s++; if (/[^A-Za-z0-9]/.test(p)) s++; if (p.length > 12) s++; return s; }

const I = {
  spark: <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z" /><circle cx="19" cy="4" r="1.6" /><circle cx="5" cy="19" r="1.2" /></svg>,
  search: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>,
  bars: <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="12" width="4" height="8" rx="1" /><rect x="10" y="7" width="4" height="13" rx="1" /><rect x="16" y="3" width="4" height="17" rx="1" /></svg>,
  doc: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>,
  bolt: <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 3 14h8l-1 8 10-12h-8l1-8z" /></svg>,
  clock: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>,
  file: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5" /></svg>,
  db: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></svg>,
  userplus: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="10" cy="8" r="4" /><path d="M3 21c0-3.9 3.1-7 7-7s7 3.1 7 7M19 8v6M16 11h6" /></svg>,
  mail: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>,
  lock: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>,
  user: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" /></svg>,
  brief: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18" /></svg>,
  arrow: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>,
  google: <svg width="20" height="20" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.6 12.3c0-.8-.1-1.5-.2-2.2H12v4.2h6c-.3 1.4-1 2.6-2.2 3.4v2.8h3.6c2.1-1.9 3.2-4.8 3.2-8.2z" /><path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.6-2.8c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.6H2.1v2.9C4 20.5 7.7 23 12 23z" /><path fill="#FBBC05" d="M5.8 14c-.2-.7-.4-1.4-.4-2.1s.1-1.4.4-2.1V6.9H2.1C1.4 8.4 1 10.1 1 11.9s.4 3.5 1.1 5l3.7-2.9z" /><path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.2-3.2C17.5 2.1 15 1 12 1 7.7 1 4 3.5 2.1 6.9L5.8 9.8c.9-2.7 3.3-4.4 6.2-4.4z" /></svg>,
  github: <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.4-4-1.4-.5-1.4-1.3-1.8-1.3-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .5z" /></svg>,
};

export default function Auth({ onSuccess }: { onSuccess: (u: AuthUser) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [pw, setPw] = useState(""); const [family, setFamily] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const [forgot, setForgot] = useState(false); const [forgotSent, setForgotSent] = useState(false); const [forgotEmail, setForgotEmail] = useState("");
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [resetPw, setResetPw] = useState(""); const [resetPw2, setResetPw2] = useState(""); const [resetDone, setResetDone] = useState("");
  const [stats, setStats] = useState<{ count?: number; added_today?: number; last_scrape_mins_ago?: number }>({});
  const [info, setInfo] = useState<"how" | "about" | null>(null);
  const [splash, setSplash] = useState(() => !new URLSearchParams(window.location.search).get("reset_token"));

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const t = q.get("reset_token"); const e = q.get("error");
    if (t) setResetToken(t); if (e) setErr(e);
    if (t || e) window.history.replaceState({}, "", window.location.pathname + window.location.hash);
    fetch(`${BASE}/api/jobs/count`).then(r => r.json()).then(r => setStats(s => ({ ...s, count: r.count }))).catch(() => {});
    fetch(`${BASE}/api/stats/today`).then(r => r.json()).then(r => setStats(s => ({ ...s, ...r }))).catch(() => {});
  }, []);

  const submit = async () => {
    setErr("");
    if (mode === "register" && !name.trim()) return setErr("Enter your full name");
    if (!email.trim() || !pw) return setErr("Email and password are required");
    setBusy(true);
    try {
      const roles = ROLE_GROUPS.find(g => g.group === family)?.items ?? [];
      const r = mode === "login" ? await api.auth.login(email.trim(), pw) : await api.auth.register(email.trim(), pw, name.trim(), roles);
      localStorage.setItem("jh_token", r.token); localStorage.setItem("jh_user", JSON.stringify(r.user));
      onSuccess(r.user);
    } catch (e: any) { setErr(e?.message || "Something went wrong"); }
    finally { setBusy(false); }
  };
  const sendForgot = async () => { setBusy(true); try { await api.auth.forgotPassword((forgotEmail || email).trim()); } catch { /* no enumeration */ } finally { setBusy(false); setForgotSent(true); } };
  const doReset = async () => {
    setErr("");
    if (resetPw.length < 8) return setErr("Password must be at least 8 characters");
    if (resetPw !== resetPw2) return setErr("Passwords don't match");
    setBusy(true);
    try { const r = await api.auth.resetPassword(resetToken!, resetPw); setResetDone(r.email || "your account"); } catch (e: any) { setErr(e?.message || "Reset failed"); } finally { setBusy(false); }
  };
  const oauth = (p: "google" | "github") => { window.location.href = `${BASE}/api/auth/${p}/login?action=${mode}`; };
  const switchMode = (m: Mode) => { setMode(m); setErr(""); setForgot(false); };
  const s = strength(pw);

  const card = resetToken ? (
    <div className="au-card">
      <span className="au-eyebrow">Reset password</span>
      {resetDone ? <>
        <h2>You're all set.</h2><p className="sub">Password updated for <b>{resetDone}</b>. Sign in to continue.</p>
        <button className="au-cta" onClick={() => { setResetToken(null); setResetDone(""); }}>Go to Sign In {I.arrow}</button>
      </> : <>
        <h2>Choose a new password</h2><p className="sub">At least 8 characters. Mix letters, numbers and symbols for a strong one.</p>
        <Field label="New password" icon={I.lock}><input type="password" autoFocus value={resetPw} onChange={e => setResetPw(e.target.value)} placeholder="••••••••" /></Field>
        <Field label="Confirm password" icon={I.lock}><input type="password" value={resetPw2} onChange={e => setResetPw2(e.target.value)} onKeyDown={e => e.key === "Enter" && doReset()} placeholder="••••••••" /></Field>
        {err && <div className="au-err">{err}</div>}
        <button className="au-cta" onClick={doReset} disabled={busy}>{busy ? "Resetting…" : <>Reset Password {I.arrow}</>}</button>
      </>}
    </div>
  ) : (
    <div className={`au-card${mode === "register" ? " reg" : ""}`}>
      <span className="au-eyebrow"><i className="dot" />Welcome</span>
      <h2>Your digital career agent is<br /><em>fully prepared.</em></h2>
      <p className="sub">Access your current dashboard or register in under 30 seconds to begin your automated outreach campaign immediately.</p>
      <div className="au-switch"><button type="button" className={mode === "login" ? "on" : ""} onClick={() => switchMode("login")}>Login</button><button type="button" className={mode === "register" ? "on" : ""} onClick={() => switchMode("register")}>Register</button></div>
      {mode === "login" ? <>
        <button type="button" className="au-oauth" onClick={() => oauth("google")}>{I.google} Continue with Google</button>
        <button type="button" className="au-oauth" onClick={() => oauth("github")}>{I.github} Continue with GitHub</button>
      </> : <div className="au-row2"><button type="button" className="au-oauth" onClick={() => oauth("google")}>{I.google} Google</button><button type="button" className="au-oauth" onClick={() => oauth("github")}>{I.github} GitHub</button></div>}
      <div className="au-or">Or continue with email</div>
      {mode === "register" ? <div className="au-row2"><Field label="Full name" icon={I.user}><input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="Alex Johnson" autoComplete="name" /></Field><Field label="Email" icon={I.mail}><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="alex@hey.com" autoComplete="email" /></Field></div>
        : <Field label="Email" icon={I.mail}><input type="email" autoFocus value={email} onChange={e => setEmail(e.target.value)} placeholder="alex@hey.com" autoComplete="email" /></Field>}
      <Field label="Password" icon={I.lock} right={mode === "login" && !forgot ? <button type="button" onClick={() => { setForgot(true); setForgotSent(false); setForgotEmail(email); }}>Forgot password?</button> : undefined}>
        <input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder={mode === "register" ? "At least 8 characters" : "••••••••"} autoComplete={mode === "login" ? "current-password" : "new-password"} onKeyDown={e => e.key === "Enter" && submit()} />
      </Field>
      {mode === "register" && pw && <div className="au-strength"><div className="bars">{[1, 2, 3, 4, 5].map(i => <i key={i} style={{ background: i <= s ? STRENGTH_C[s] : undefined }} />)}</div><span style={{ color: STRENGTH_C[s] }}>{STRENGTH[s]}</span></div>}
      {mode === "register" && <Field label="Primary role family" icon={I.brief}><select value={family} onChange={e => setFamily(e.target.value)}><option value="">Choose a role family…</option>{ROLE_GROUPS.map(g => <option key={g.group} value={g.group}>{g.group}</option>)}</select></Field>}
      {forgot && <div className="au-info">
        {forgotSent ? <><b>📬 Check your inbox!</b>If <b>{forgotEmail || email}</b> is registered, a reset link is on its way.<button type="button" style={{ alignSelf: "flex-start", color: "#7c3aed", fontWeight: 700 }} onClick={() => setForgotSent(false)}>Try a different email</button></>
          : <><b>Reset your password</b><div className="au-input plain" style={{ display: "flex", gap: 8 }}><input type="email" value={forgotEmail} onChange={e => setForgotEmail(e.target.value)} placeholder="you@example.com" style={{ height: 46 }} /><button type="button" className="au-cta" style={{ width: 130, height: 46, marginTop: 0, flexShrink: 0 }} onClick={sendForgot} disabled={busy || !(forgotEmail || email)}>Send link</button></div><button type="button" style={{ alignSelf: "flex-start", color: "#64748B", fontWeight: 600 }} onClick={() => setForgot(false)}>Cancel</button></>}
      </div>}
      {err && <div className="au-err">{err}</div>}
      <button className="au-cta" onClick={submit} disabled={busy}>{busy ? (mode === "login" ? "Signing in…" : "Creating account…") : <>{mode === "login" ? "Sign In" : "Create Account"} {I.arrow}</>}</button>
      <div className="au-foot">{mode === "login" ? <>New here? <button type="button" onClick={() => switchMode("register")}>Create an account</button></> : <>Already registered? <button type="button" onClick={() => switchMode("login")}>Sign in</button></>}</div>
      <div className="au-priv">{I.lock} Your resume and account information stay private.</div>
    </div>
  );

  return (
    <div className="au">
      {splash && <Splash onDone={() => setSplash(false)} />}
      <section className="au-left">
        <div className="au-bg"><div className="au-shape tl" /><div className="au-shape mid" /></div>
        <div className="au-logo"><span className="mark">{I.spark}</span><span className="name">Job <b>Hunter</b></span></div>
        <h1 className="au-h1">Hunt smarter,<br /><span className="grad">not harder.</span></h1>
        <p className="au-lead">Scrape thousands of roles, auto-score every match against your profile, and tailor your resume in one click — all from one keyboard-first workspace.</p>
        <div className="au-band">
          <div className="au-feats">
            <Feat tile="blue" icon={I.search} title="Auto-scrape on your schedule">New jobs arrive every hour automatically, or trigger a run anytime with one click.</Feat>
            <Feat tile="purple" icon={I.bars} title="AI match score on every job">Instantly see how well each role matches your profile.</Feat>
            <Feat tile="mint" icon={I.doc} title="Resume tailored per job">Generate an ATS-optimized resume for each specific role.</Feat>
            <Feat tile="orange" icon={I.bolt} title="Auto Apply" badge="Coming soon">Review, tailor &amp; submit — your application queue, managed for you.</Feat>
          </div>
          <div className="au-art" aria-hidden>
            <div className="au-note">Same you.<br />Bigger opportunities.<svg width="70" height="52" viewBox="0 0 70 52" fill="none" stroke="#7c3aed" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M62 4c-4 22-18 36-44 42" /><path d="m26 36-8 10 12 4" /></svg></div>
            <img src="/auth/hero.png" alt="" />
          </div>
        </div>
        <div className="au-live">
          <div className="head"><span className="live-pill"><span className="dot" />LIVE</span><span className="rt">{I.clock}Jobs updated in real time</span></div>
          <div className="grid">
            <Stat icon={I.clock} n={stats.last_scrape_mins_ago != null ? `${stats.last_scrape_mins_ago}min ago` : "—"} dark l="Last updated" />
            <Stat icon={I.file} n={stats.count != null ? `${stats.count.toLocaleString()}+` : "17,000+"} l="Total jobs scraped" />
            <Stat icon={I.db} n="10+" l="Sources tracked" />
            <Stat icon={I.userplus} n={stats.added_today != null ? String(stats.added_today) : "—"} l="Added today" />
          </div>
        </div>
      </section>

      <section className="au-right">
        <div className="au-bg"><div className="au-shape tr" /><div className="au-shape br" /></div>
        <div className="au-mobile-logo"><span className="mark">{I.spark}</span><span className="name">Job <b>Hunter</b></span></div>
        <nav className="au-nav"><button onClick={() => { switchMode("login"); document.querySelector<HTMLInputElement>(".au-card input")?.focus(); }}>Find Jobs</button><button onClick={() => setInfo("how")}>How It Works</button><button onClick={() => setInfo("about")}>About</button></nav>
        {card}
      </section>

      <Modal open={info === "how"} onClose={() => setInfo(null)} title="How it works" width={720}><HowItWorks /></Modal>
      <Modal open={info === "about"} onClose={() => setInfo(null)} title="About Job Hunter" width={640}><AboutText /></Modal>
    </div>
  );
}

/** Intro splash: particles, spark mark, brand, progress bar; click anywhere to skip. */
function Splash({ onDone }: { onDone: () => void }) {
  const [ready, setReady] = useState(false); const [exit, setExit] = useState(false);
  const finish = () => { setExit(true); setTimeout(onDone, 520); };
  useEffect(() => { const t1 = setTimeout(() => setReady(true), 60); const t2 = setTimeout(finish, 3200); return () => { clearTimeout(t1); clearTimeout(t2); }; }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const N = 22;
  return (
    <div className={`splash${ready ? " splash-ready" : ""}${exit ? " exit" : ""}`} onClick={finish}>
      <div className="splash-glow" /><div className="splash-grid-bg" />
      <div className="splash-particles">{Array.from({ length: N }, (_, i) => <span key={i} className="splash-particle" style={{ ["--sp-a" as any]: `${(i / N) * 360}deg`, ["--sp-d" as any]: `${130 + (i % 6) * 30}px`, ["--sp-delay" as any]: `${i * 0.03}s`, ["--sp-drift-delay" as any]: `${i * 0.05}s` }} />)}</div>
      <div className="splash-center">
        <div className="splash-target">
          <svg className="splash-spark" viewBox="0 0 60 60"><circle cx="30" cy="30" r="30" fill="#0f0f1a" /><path d="M30 9 L32.5 24 L46 27.5 L32.5 31 L30 46 L27.5 31 L14 27.5 L27.5 24 Z" fill="white" /><path d="M44 12 L45.2 16.8 L50 18 L45.2 19.2 L44 24 L42.8 19.2 L38 18 L42.8 16.8 Z" fill="#22d3ee" /></svg>
          <span className="splash-lock-ring" /><span className="splash-lock-ring splash-lock-ring-2" />
        </div>
        <div className="splash-word"><h1 className="splash-brand">Job <span className="splash-hl">Hunter</span></h1><p className="splash-tagline">Hunt Smarter, Not Harder</p></div>
        <div className="splash-progress"><i className="splash-progress-bar" /></div>
        <div className="splash-credit"><span>✦</span>Built by Jay</div>
      </div>
      <div className="splash-skip">Click anywhere to skip</div>
    </div>
  );
}

function HowItWorks() {
  return <ol className="au-modal-text" style={{ paddingLeft: 22, display: "flex", flexDirection: "column", gap: 14 }}>
    <li><b>Scrape.</b> Every hour Job Hunter pulls fresh roles from 10+ ATS platforms and boards into one feed, filtered to the role families you pick.</li>
    <li><b>Score.</b> Each job is matched against your resume profile: sponsorship, location, experience and skills, with a plain-English summary.</li>
    <li><b>Tailor.</b> One click writes an ATS-optimized resume for that exact job, checked by a three-gate score (ATS, recruiter, hiring manager) before you see it.</li>
    <li><b>Apply.</b> Download PDF / DOCX, generate a cover letter, track status from applied to final interview.</li>
  </ol>;
}
function AboutText() { return <p className="au-modal-text">Job Hunter is a private, keyboard-first job search workspace built by Jay. Accounts are approved by the admin, and your resume, answers and tailored documents are never shared. Beta — expect frequent improvements.</p>; }
function Feat({ tile, icon, title, badge, children }: { tile: string; icon: React.ReactNode; title: string; badge?: string; children: React.ReactNode }) {
  return <div className="au-feat"><span className={`tile ${tile}`}>{icon}</span><div><h3>{title}{badge && <span className="au-soon">{badge}</span>}</h3><p>{children}</p></div></div>;
}
function Stat({ icon, n, l, dark }: { icon: React.ReactNode; n: string; l: string; dark?: boolean }) {
  return <div className="au-stat"><span className="ic">{icon}</span><div><div className={`n${dark ? " dark" : ""}`}><CountUp text={n} /></div><div className="l">{l}</div></div></div>;
}
/** Counts the leading number in `text` up from 0 over ~1s; keeps prefix/suffix (e.g. "17,349+", "12min ago"). */
function CountUp({ text }: { text: string }) {
  const m = text.match(/^([^\d]*)([\d,]+)(.*)$/);
  const target = m ? parseInt(m[2].replace(/,/g, ""), 10) : NaN;
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!m || isNaN(target)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    const t0 = Date.now(); const dur = 1100;
    const id = window.setInterval(() => { const p = Math.min(1, (Date.now() - t0) / dur); setV(Math.round(target * (1 - Math.pow(1 - p, 3)))); if (p >= 1) window.clearInterval(id); }, 24);
    return () => window.clearInterval(id);
  }, [target]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!m || isNaN(target)) return <>{text}</>;
  return <>{m[1]}{v.toLocaleString()}{m[3]}</>;
}
function Field({ label, icon, right, children }: { label: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }) {
  return <div className="au-field"><div className="lbl"><span>{label}</span>{right}</div><div className={`au-input${icon ? "" : " plain"}`}>{icon}{children}</div></div>;
}
