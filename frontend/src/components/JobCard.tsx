import React, { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import type { Job } from "../types";
import { JOB_STATUSES, STATUS_COLORS as _ST_COLORS } from "../types";
import { CompanyLogo, AtsLogo, Spinner } from "./primitives";
import { api } from "../api";
import { isAILeadership, coarseExpBand } from "../roles";

const EXP_TRAYS = ["0-2","2-4","4-5","5-6","6-7","7-8","8-10","10-13","13-15","15+"];

// Pills for every status except "new" (new shows no pill). Derived from the
// shared status config so labels/colors never drift.
const STATUS_LABEL: Record<string, { label: string; bg: string; color: string }> =
  Object.fromEntries(JOB_STATUSES.filter(s => s.id !== "new")
    .map(s => [s.id, { label: s.label, bg: s.color + "1f", color: s.color }]));

// Status → color for left border
const STATUS_COLOR: Record<string, string> = _ST_COLORS;

// The six qualify checks, in the order the screener weighs them.
const QUAL_ROWS: [string, string][] = [
  ["job_category", "Role match"], ["skills_match", "Skills"], ["experience", "Years"],
  ["sponsorship", "Sponsorship"], ["location", "Location"], ["seniority", "Seniority"],
];

const POINT_MAX: [string, string, number][] = [
  ["tools", "JD tools", 30], ["duties", "Duties", 15], ["title", "Title", 5], ["orphans", "Orphans", 10],
  ["numbers", "Numbers", 10], ["readability", "Readability", 10], ["page_fit", "Page fit", 10], ["proof", "Proof", 10],
];

/** Anchors a fixed panel under (or above) a badge, clamped to the viewport. */
function popStyle(anchor: DOMRect, width: number, height: number): React.CSSProperties {
  const left = Math.max(8, Math.min(anchor.right - width, window.innerWidth - width - 8));
  const below = anchor.bottom + 6;
  return {
    position: "fixed", left, width, zIndex: 9999,
    ...(below + height < window.innerHeight ? { top: below } : { bottom: window.innerHeight - anchor.top + 6 }),
  };
}

/** Hover panel behind the tailored-resume badge: gates, where points went, fixes, missing tools. */
function ResumePopover({ job, anchor, onEnter, onLeave }: { job: Job; anchor: DOMRect; onEnter: () => void; onLeave: () => void }) {
  const gs = job.gate_scores || null;
  const overall = typeof gs?.overall === "number" ? gs.overall : null;
  const rs = overall ?? job.ats_score_after ?? 0;
  const cls = rs >= 70 ? "high" : rs >= 50 ? "mid" : "low";
  const review = job.needs_review === true;
  const tone = review ? "bad" : "ok";
  const gates: [string, any][] = gs ? [["ATS", gs.ats], ["Recruiter", gs.recruiter], ["Hiring manager", gs.hiring_manager]] : [];
  const pts = gs?.points || null;
  const weak = (k: string, max: number) => pts && typeof pts[k] === "number" && pts[k] < max * 0.6;
  const cov = gs?.coverage_target;
  const fixes = (gs?.top_fixes || []).slice(0, 3);
  const allMissing = gs?.missing || [];
  const missing = allMissing.slice(0, 8);
  return createPortal(
    <div className={`qual-pop ${tone}`} style={popStyle(anchor, 372, 340)} onMouseDown={e => e.stopPropagation()}
         onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <div className="qual-pop-head">
        <span className={`qual-pop-score ${cls}`}>{rs}{overall == null && <small>%</small>}</span>
        <div className="qual-pop-verdict">
          <span className={`qual-pop-chip ${tone}`}>{review ? "Needs review" : "Ready to apply"}</span>
          <span className="qual-pop-count">
            {overall != null ? "Tailored resume score" : "ATS keyword match"}
            {job.ats_score_before != null ? ` · base ${job.ats_score_before} → tailored ${rs}` : ""}
          </span>
        </div>
      </div>
      {gates.length > 0 && (
        <div className="qual-pop-rows">
          {gates.map(([label, g]) => {
            const v = typeof g?.score === "number" ? g.score : null;
            if (v == null) return null;
            return (
              <div key={label} className="qual-pop-gate">
                <span className="qual-pop-label">{label}</span>
                <span className="qual-pop-bar"><i style={{ width: `${Math.max(0, Math.min(100, v))}%` }} className={v >= 70 ? "high" : v >= 50 ? "mid" : "low"} /></span>
                <span className="qual-pop-gate-v">{v}</span>
                {g?.note && <span className="qual-pop-note">{g.note}</span>}
              </div>
            );
          })}
        </div>
      )}
      {pts && (
        <div className="qual-pop-pts">
          {POINT_MAX.map(([k, label, max]) => typeof pts[k] === "number" && (
            <span key={k} className={`qual-pop-pt${weak(k, max) ? " weak" : ""}`}>
              <b>{Math.round(pts[k])}</b>/{max} {label}
            </span>
          ))}
        </div>
      )}
      {cov && typeof cov.need === "number" && cov.need > 0 && (
        <div className="qual-pop-cov">
          {cov.have} of {cov.need} JD tools earned a bullet · 90% target {cov.met ? "met" : "missed"}
        </div>
      )}
      {fixes.length > 0 && (
        <div className="qual-pop-miss">
          <div className="qual-pop-label">What to fix</div>
          <ol className="qual-pop-fixes">{fixes.map((f, i) => <li key={i}>{f}</li>)}</ol>
        </div>
      )}
      {missing.length > 0 && (
        <div className="qual-pop-miss">
          <div className="qual-pop-label">JD tools not in the resume</div>
          <div className="qual-pop-chips">
            {missing.map(m => <span key={m} className="qual-pop-kw">{m}</span>)}
            {allMissing.length > 8 && <span className="qual-pop-kw more">+{allMissing.length - 8}</span>}
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}

/** Hover panel behind the match pill: every check, its reason, and the keyword gaps. */
function QualifyPopover({ qr, anchor, onEnter, onLeave }: { qr: any; anchor: DOMRect; onEnter: () => void; onLeave: () => void }) {
  const crit = (qr?.criteria && typeof qr.criteria === "object") ? qr.criteria : {};
  const missing: string[] = qr?.overlap?.missing || [];
  const style = popStyle(anchor, 372, 300);
  const rows = QUAL_ROWS.filter(([k]) => crit[k]);
  const passed = rows.filter(([k]) => crit[k].pass).length;
  const failed = rows.filter(([k]) => !crit[k].pass).map(([, label]) => label);
  const tone = qr.qualified ? "ok" : "bad";
  return createPortal(
    <div className={`qual-pop ${tone}`} style={style} onMouseDown={e => e.stopPropagation()}
         onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <div className="qual-pop-head">
        <span className={`qual-pop-score ${scoreClass(qr.score ?? 0)}`}>{qr.score}<small>%</small></span>
        <div className="qual-pop-verdict">
          <span className={`qual-pop-chip ${tone}`}>{qr.qualified ? "Qualified" : "Not qualified"}</span>
          <span className="qual-pop-count">{passed} of {rows.length} checks pass{failed.length ? ` · blocked by ${failed.join(", ")}` : ""}</span>
        </div>
      </div>
      {qr.summary && <p className="qual-pop-sum">{qr.summary}</p>}
      <div className="qual-pop-rows">
        {rows.map(([key, label]) => {
          const c = crit[key];
          return (
            <div key={key} className={`qual-pop-row ${c.pass ? "ok" : "bad"}`}>
              <span className="qual-pop-ico" aria-hidden="true">{c.pass ? "✓" : "✕"}</span>
              <span className="qual-pop-label">{label}</span>
              <span className="qual-pop-note">{c.note}</span>
            </div>
          );
        })}
      </div>
      {missing.length > 0 && (
        <div className="qual-pop-miss">
          <div className="qual-pop-label">Not in your profile</div>
          <div className="qual-pop-chips">
            {missing.slice(0, 8).map(m => <span key={m} className="qual-pop-kw">{m}</span>)}
            {missing.length > 8 && <span className="qual-pop-kw more">+{missing.length - 8}</span>}
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}

// Source → CSS var
const SRC_VAR: Record<string, string> = {
  Greenhouse: "--src-greenhouse", Lever: "--src-lever", Ashby: "--src-ashby",
  Workday: "--src-workday", HiringCafe: "--src-hiringcafe",
};

// Posted date stamp: "06/11" — extracted directly from UTC ISO string so date
// matches what the filter buttons show (FJ stores date-only jobs as T00:00:00Z).
function fmtPosted(iso: string): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return "";
  return `${m[2]}/${m[3]}`;
}

// "X ago" = when WE scraped it (our fetch time) — not FantasticJobs'
// posted/index time. All jobs from one hourly scrape share this, so they read
// the same age; that's intended.
function bestPostedTs(job: Job): string {
  return job.scraped_at || job.posted_at || "";
}

// Relative time: "just now", "50min ago", "5hrs ago", "3d ago", "2mo ago".
function relTime(iso: string): string {
  if (!iso) return "";
  const t = Date.parse(iso.replace(" ", "T"));
  if (!t) return "";
  const mins = Math.floor((Date.now() - t) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}hr${hrs > 1 ? "s" : ""} ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function scoreClass(s: number): string {
  return s >= 80 ? "high" : s >= 65 ? "mid" : "low";
}

// Animated score ring (matches design ScoreRing)
function ScoreRing({ value, size = 64, stroke = 6 }: { value: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const [off, setOff] = useState(circ);
  useEffect(() => {
    const t = setTimeout(() => setOff(circ * (1 - value / 100)), 80);
    return () => clearTimeout(t);
  }, [value, circ]);
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7c3aed" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        <circle className="ring-bg" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        <circle className="ring-fg" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke}
          strokeDasharray={circ} strokeDashoffset={off} />
      </svg>
      <div className="ring-val">{value}<small>%</small></div>
    </div>
  );
}

interface Props {
  job: Job;
  selected: boolean;
  onClick: () => void;
  onSkip?: (id: string) => void;
  onUpdate?: (id: string, patch: Partial<Job>) => void;
  mode?: "compact" | "cards";
  index?: number;
  tailoring?: boolean;   // resume tailor in flight for this job — show spinner badge
  checked?: boolean;                    // multi-select for batch tailoring
  onToggleCheck?: (id: string) => void;
  onDefer?: (id: string, deferred: boolean) => void;   // soft "move to bottom of day"
}

export function JobCard({ job, selected, onClick, onSkip, onUpdate, mode = "compact", index = 0, tailoring = false, checked = false, onToggleCheck, onDefer }: Props) {
  const [editingExp, setEditingExp] = useState(false);
  const [qualAnchor, setQualAnchor] = useState<DOMRect | null>(null);   // hover panel behind the match pill
  // Closing is delayed so the cursor can travel from the pill to the panel (a portal
  // outside the card) without the panel vanishing; entering the panel cancels the close.
  const qualClose = useRef<number | null>(null);
  const qualHold = () => { if (qualClose.current) { window.clearTimeout(qualClose.current); qualClose.current = null; } };
  const [resAnchor, setResAnchor] = useState<DOMRect | null>(null);     // hover panel behind the tailored-score badge
  const qualOpen = (e: React.MouseEvent) => { qualHold(); setResAnchor(null); setQualAnchor((e.currentTarget as HTMLElement).getBoundingClientRect()); };
  const resOpen = (e: React.MouseEvent) => { qualHold(); setQualAnchor(null); setResAnchor((e.currentTarget as HTMLElement).getBoundingClientRect()); };
  const qualRelease = () => { qualHold(); qualClose.current = window.setTimeout(() => { setQualAnchor(null); setResAnchor(null); }, 180); };
  useEffect(() => qualHold, []);
  const expRef = useRef<HTMLSelectElement>(null);
  const qr      = job.qualify_result as any;
  const score   = qr?.score ?? null;
  const posted  = relTime(bestPostedTs(job));
  const stColor = STATUS_COLOR[job.status] || "var(--st-new)";
  const srcVar  = SRC_VAR[job.source];
  // NEW = only the last hour by OUR scrape time (i.e. this scrape's batch).
  // After an hour it drops; the next scrape's fresh jobs light up as NEW again.
  const isNew   = job.status === "new" && !!job.scraped_at && (Date.now() - new Date(job.scraped_at).getTime()) < 3600000;
  const isRemote = job.remote || (job.location || "").toLowerCase().includes("remote");

  // ── Cards mode: redesigned card (title left, "X% Match" top-right, meta row) ──
  if (mode === "cards") {
    // AI/DS Leadership jobs show FJ's 4 coarse bands (0-2/2-5/5-10/10+); others
    // show our fine tray. Coarse hides the "~inferred" marker (it's coarse anyway).
    const _lead = isAILeadership(job.title);
    const _expVal = job.experience_level ? (_lead ? coarseExpBand(job.experience_level) : job.experience_level) : "";
    const expStr = _expVal ? `${job.experience_level_inferred && !_lead ? "~" : ""}${_expVal} yr` : "";
    const stItem = STATUS_LABEL[job.status];
    return (
      <div className={`jcard${selected ? " sel" : ""}${checked ? " checked" : ""}`}
        onClick={onClick} onMouseLeave={qualRelease}
        style={{ animationDelay: `${Math.min(index, 12) * 20}ms`, ...(job.deferred ? { opacity: 0.5 } : {}) } as React.CSSProperties}>

        {onDefer && (
          <button className={`defer-quick${job.deferred ? " on" : ""}`}
            title={job.deferred ? "Restore — bring back up" : "Later — move to bottom of today"}
            onClick={e => { e.stopPropagation(); onDefer(job.id, !job.deferred); }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              {job.deferred ? <path d="M12 19V5M5 12l7-7 7 7" /> : <path d="M12 5v14M5 12l7 7 7-7" />}
            </svg>
          </button>
        )}
        {onSkip && (
          <button className="skip-quick" title="Skip (s)" onClick={e => { e.stopPropagation(); onSkip(job.id); }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        )}

        <div className="jcard-row">
          {onToggleCheck && (
            <button className={`jcard-check${checked ? " on" : ""}`} title="Select for batch tailoring"
              onClick={e => { e.stopPropagation(); onToggleCheck(job.id); }}>
              {checked && <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>}
            </button>
          )}
          <div className="jcard-logo"><CompanyLogo url={job.url} company={job.company} size={40} /></div>
          <div className="jcard-body">
            <div className="jcard-titlerow">
              <span className="jcard-title" title={job.title}>{job.title}</span>
              {isNew && <span className="jcard-new">NEW</span>}
              {tailoring && <span className="jcard-tailoring"><Spinner size={10} color="#7c3aed" /> Tailoring</span>}
              {isRemote && (
                <span className="jcard-remote">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></svg>
                  Remote
                </span>
              )}
            </div>
            <div className="jcard-company">{job.company}</div>
            <div className="jcard-loc">
              <svg className="jcard-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></svg>
              <span className="jcard-loctext">{job.location || "Remote"}</span>
            </div>
            <div className="jcard-metaline">
              {editingExp ? (
                <select ref={expRef} defaultValue={job.experience_level ?? ""} onClick={e => e.stopPropagation()} onBlur={() => setEditingExp(false)}
                  onChange={async e => { const val = e.target.value; setEditingExp(false); try { await api.setExpLevel(job.id, val); onUpdate?.(job.id, { experience_level: val, experience_level_inferred: false } as any); } catch {} }}
                  style={{ fontSize: 11, padding: "1px 4px", borderRadius: 5, border: "1px solid var(--violet)", background: "var(--bg-2)", color: "var(--tx-2)" }}>
                  {EXP_TRAYS.map(t => <option key={t} value={t}>{t}yr</option>)}
                </select>
              ) : expStr && (
                <span className="jcard-mtext">{expStr}
                  <button className="jcard-expedit" title="Edit years of experience" onClick={e => { e.stopPropagation(); setEditingExp(true); setTimeout(() => expRef.current?.focus(), 50); }}>✏</button>
                </span>
              )}
              {expStr && job.source !== "FantasticJobs" && <span className="jcard-dot">•</span>}
              {job.source !== "FantasticJobs" && <span className="jcard-mtext">{job.source}</span>}
            </div>
          </div>
          <div className="jcard-right">
            <div className="jcard-badges">
              {/* AI Match % is a "worth tailoring?" triage signal — once a
                  tailored score exists the decision is made, so hide the %. */}
              {score !== null && job.ats_score_after == null && (job.gate_scores?.overall == null)
                && <span className={`jcard-matchpill ${scoreClass(score)}`}
                         onMouseEnter={qualOpen}>{score}%</span>}
              {qualAnchor && qr && <QualifyPopover qr={qr} anchor={qualAnchor} onEnter={qualHold} onLeave={qualRelease} />}
              {(() => {
                // Tailored resume score — overall gate blend, else raw ATS.
                const overall = typeof job.gate_scores?.overall === "number" ? job.gate_scores.overall : null;
                const rs = overall ?? job.ats_score_after;
                if (rs == null) return null;
                const cls = rs >= 70 ? "high" : rs >= 50 ? "mid" : "low";
                return <span className={`jcard-resume ${cls}${job.needs_review ? " review" : ""}`} onMouseEnter={resOpen}>{overall != null ? "★" : "📄"} {rs}{overall != null ? "" : "%"}</span>;
              })()}
              {resAnchor && <ResumePopover job={job} anchor={resAnchor} onEnter={qualHold} onLeave={qualRelease} />}
              {stItem && <span className="jcard-status" style={{ background: stItem.bg, color: stItem.color }}>{stItem.label}</span>}
            </div>
            {posted && (
              <span className="jcard-time">
                <svg className="jcard-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
                {posted}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`jobcard${selected ? " sel" : ""}`}
      onClick={onClick} onMouseLeave={qualRelease}
      style={{
        "--st-color": stColor,
        animationDelay: `${Math.min(index, 12) * 20}ms`,
        ...(checked ? { boxShadow: "inset 0 0 0 1.6px var(--violet)", background: "rgba(124,58,237,0.05)" } : {}),
        ...(job.deferred ? { opacity: 0.5 } : {}),
      } as React.CSSProperties}
    >
      {/* Multi-select checkbox (batch tailoring) */}
      {onToggleCheck && (
        <div onClick={(e) => { e.stopPropagation(); onToggleCheck(job.id); }}
          title="Select for batch tailoring"
          style={{ display: "flex", alignItems: "center", flexShrink: 0, cursor: "pointer", paddingRight: 2 }}>
          <span style={{
            width: 16, height: 16, borderRadius: 4, display: "grid", placeItems: "center", flexShrink: 0,
            border: checked ? "none" : "1.5px solid var(--line-hi)",
            background: checked ? "var(--violet)" : "transparent",
          }}>
            {checked && <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>}
          </span>
        </div>
      )}

      {/* Company logo */}
      <div className="logo" style={{ flexShrink: 0 }}>
        <CompanyLogo url={job.url} company={job.company} size={34} />
      </div>

      {/* Main content */}
      <div className="jc-main">
        <div className="jc-title-row">
          <span className="jc-title">{job.title}</span>
          {isNew && <span className="badge-new">new</span>}
          {tailoring && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10.5, fontWeight: 700,
              padding: "1px 8px", borderRadius: 999, background: "rgba(124,58,237,0.12)", color: "#7c3aed",
              border: "1px solid rgba(124,58,237,0.35)", whiteSpace: "nowrap", flexShrink: 0 }}>
              <Spinner size={10} color="#7c3aed" /> Tailoring
            </span>
          )}
        </div>
        <div className="jc-sub">
          <span className="co">{job.company}</span>
          <span className="sep" />
          <span className="loc">{job.location || "Remote"}</span>
        </div>
      </div>

      {/* Right: score badge + status + resume ATS + time */}
      <div className="jc-right">
        {/* opens on pill hover, closes on card leave: the hover-only skip /
            defer buttons sit on top of the pill and would fire a leave */}
        {score !== null ? (
          <span className={`score-badge ${scoreClass(score)}`}
                onMouseEnter={qualOpen}>{score}%</span>
        ) : null}
        {qualAnchor && qr && <QualifyPopover qr={qr} anchor={qualAnchor} onEnter={qualHold} onLeave={qualRelease} />}
        {resAnchor && <ResumePopover job={job} anchor={resAnchor} onEnter={qualHold} onLeave={qualRelease} />}
        {STATUS_LABEL[job.status] && (
          <span style={{
            fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
            background: STATUS_LABEL[job.status].bg,
            color: STATUS_LABEL[job.status].color,
            marginTop: score !== null ? 3 : 0, display: "block", textAlign: "center",
          }}>{STATUS_LABEL[job.status].label}</span>
        )}
        {(() => {
          // Prefer the overall (ATS + recruiter + hiring-manager blend) so the
          // card headline matches the Resume Score panel. Fall back to the raw
          // ATS coverage when no gate scores exist yet.
          const overall = typeof job.gate_scores?.overall === "number" ? job.gate_scores.overall : null;
          const s = overall ?? job.ats_score_after;
          if (s == null) return null;
          return (
            <span onMouseEnter={resOpen} style={{
              fontSize: 10, fontWeight: 700, padding: "2px 5px", borderRadius: 4,
              background: s >= 70 ? "rgba(124,58,237,0.10)" : s >= 50 ? "rgba(234,179,8,0.12)" : "rgba(239,68,68,0.10)",
              color: s >= 70 ? "var(--violet)" : s >= 50 ? "#b45309" : "#dc2626",
              border: `1px solid ${s >= 70 ? "rgba(124,58,237,0.25)" : s >= 50 ? "rgba(234,179,8,0.3)" : "rgba(239,68,68,0.2)"}`,
              marginTop: 3, display: "block", textAlign: "center",
            }}>{overall != null ? "★" : "📄"} {s}{overall != null ? "" : "%"}</span>
          );
        })()}
        {mode === "compact" && <span className="jc-time">{posted}</span>}
      </div>

      {/* Soft-defer — move to bottom of the day (↓), or restore (↑) if deferred.
          Distinct from Skip (✕ = permanent remove). */}
      {onDefer && (
        <button className={`defer-quick${job.deferred ? " on" : ""}`}
          title={job.deferred ? "Restore — bring back up" : "Later — move to bottom of today"}
          onClick={e => { e.stopPropagation(); onDefer(job.id, !job.deferred); }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            {job.deferred ? <path d="M12 19V5M5 12l7-7 7 7" /> : <path d="M12 5v14M5 12l7 7 7-7" />}
          </svg>
        </button>
      )}

      {/* Quick skip */}
      {onSkip && (
        <button className="skip-quick" title="Skip (s)"
          onClick={e => { e.stopPropagation(); onSkip(job.id); }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}
