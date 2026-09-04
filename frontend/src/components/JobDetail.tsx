import { useState, useEffect, useRef } from "react";
import type { Job, JobStatus } from "../types";
import { STATUS_LABELS, STATUS_COLORS as ST_COLORS, APPLIED_STAGES } from "../types";
import { api, downloadFile } from "../api";
import { ATSBar, Spinner, CompanyLogo, AtsLogo } from "./primitives";
import { checkVisa } from "../utils/visaCheck";

// ── Resume-score bands + submit thresholds — all tuning lives here ──────────
const SUBMIT_AT = 70;   // overall >= this  → "Submit — application-ready"
const REACH_AT  = 60;   // overall 60-69    → "Borderline"; below → "Don't submit"

const SCORE_BANDS: { min: number; label: string; color: string }[] = [
  { min: 90, label: "Outstanding", color: "#16a34a" },
  { min: 85, label: "Excellent",   color: "#22c55e" },
  { min: 80, label: "Best",        color: "#4ade80" },
  { min: 75, label: "Very Good",   color: "#3b82f6" },
  { min: 70, label: "Good",        color: "#eab308" },
  { min: 60, label: "Fair",        color: "#f59e0b" },
  { min: 0,  label: "Needs Work",  color: "#ef4444" },
];

function scoreRating(o: number) {
  return SCORE_BANDS.find(b => o >= b.min) ?? SCORE_BANDS[SCORE_BANDS.length - 1];
}

function submitRec(o: number) {
  if (o >= SUBMIT_AT) return { t: "✓ Submit — application-ready", bg: "rgba(34,197,94,0.14)", fg: "#16a34a", bd: "rgba(34,197,94,0.4)" };
  if (o >= REACH_AT)  return { t: "Borderline — your call",       bg: "rgba(245,158,11,0.14)", fg: "#d97706", bd: "rgba(245,158,11,0.4)" };
  return { t: "✕ Don’t submit yet — improve", bg: "rgba(239,68,68,0.12)", fg: "#dc2626", bd: "rgba(239,68,68,0.35)" };
}

// Visa / work-authorization red flags surfaced from the JD text.
// Uses the shared checkVisa scanner (citizenship, GC, no-sponsorship,
// "no H1B/OPT", "GC or citizen only", clearances) so an F1/OPT/H1B
// candidate can see at a glance NOT to apply.
function detectDisqualifiers(jd: string): string[] {
  return checkVisa(jd || "").reasons;
}

function relTimeDetail(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso.replace(/(\.\d{3})\d+/, "$1")).getTime();
  if (isNaN(diff)) return "";
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Animated ScoreRing matching design spec
function ScoreRingDetail({ value, size = 64, stroke = 6 }: { value?: number | null; size?: number; stroke?: number }) {
  const r    = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const [off, setOff] = useState(circ);
  useEffect(() => {
    if (value == null) {
      setOff(circ);
      return;
    }
    const t = setTimeout(() => setOff(circ * (1 - value / 100)), 80);
    return () => clearTimeout(t);
  }, [value, circ]);
  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <defs>
          <linearGradient id="ringGradDetail" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7c3aed" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        <circle className="ring-bg" cx={size/2} cy={size/2} r={r} fill="none" strokeWidth={stroke} />
        {value != null && (
          <circle className="ring-fg" cx={size/2} cy={size/2} r={r} fill="none" strokeWidth={stroke}
            stroke="url(#ringGradDetail)"
            strokeDasharray={circ} strokeDashoffset={off} />
        )}
      </svg>
      <div className="ring-val">{value != null ? <>{value}<small>%</small></> : <span style={{color: "var(--tx-faint)"}}>—</span>}</div>
    </div>
  );
}

// ── SVG icon helper ───────────────────────────────────────────────────────────
function Ic({ d, size = 16, color, style }: { d: string; size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}
const I = {
  map:        '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
  waves:      '<path d="M2 8c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2"/><path d="M2 14c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2"/>',
  link:       '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  clock:      '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  eye:        '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  star:       '<path d="m12 3 2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.2l1-5.9L3.5 9.2l5.9-.8z"/>',
  target:     '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  sparkles:   '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/>',
  check:      '<path d="M20 6 9 17l-5-5"/>',
  checkCircle:'<circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/>',
  xCircle:    '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  chevDown:   '<path d="m6 9 6 6 6-6"/>',
  refresh:    '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  download:   '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M5 21h14"/>',
  copy:       '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  zap:        '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  fileText:   '<path d="M14 3v5h5"/><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M8 13h8M8 17h6"/>',
  grip:       '<circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/>',
  briefcase:  '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
  building:   '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M9 21v-4h6v4"/><path d="M8 7h1M12 7h1M16 7h1M8 11h1M12 11h1M16 11h1M8 15h1M16 15h1"/>',
  folder:     '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  alert:      '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  clip:       '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
};

const TABS = [
  { id: "jobdetails", label: "Job Details" },
  { id: "resume",     label: "Resume" },
  { id: "cover",      label: "Cover Letter" },
];


const STATUS_COLORS: Record<string, string> = ST_COLORS;  // shared config in types.ts

function srcColorFn(source: string): string {
  const m: Record<string, string> = {
    Greenhouse: "#16a34a", Lever:  "#059669", Ashby:  "#0891b2",
    HiringCafe: "#b45309", Google: "#2563eb", Apple:  "#475569",
    Meta:       "#4f46e5", Netflix:"#dc2626", Workday:"#7c3aed",
    BambooHR:   "#c2410c", Recruitee:"#be185d",
  };
  return m[source] || "var(--text-secondary)";
}

// ── Status dropdown ────────────────────────────────────────────────────────────
// Interview sub-stages, nested under a single "Interview ▸" parent item.
const INTERVIEW_STAGES = ["screening", "assessment", "interview", "final"];
function StatusDropdown({ status, onChange }: { status: string; onChange: (s: string) => void }) {
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setSub(false); } };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const pick = (s: string) => { onChange(s); setOpen(false); setSub(false); };
  const Item = ({ s }: { s: string }) => (
    <button onClick={() => pick(s)} className={`menu-item${status === s ? " sel" : ""}`}>
      <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[s], flexShrink: 0 }} />
      {STATUS_LABELS[s] || s}
    </button>
  );
  const inInterview = INTERVIEW_STAGES.includes(status);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} className="act" style={{ height: 30, fontSize: 12 }}>
        <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[status] || "var(--tx-3)" }} />
        {STATUS_LABELS[status] || status} <Ic d={I.chevDown} size={13} />
      </button>
      {open && (
        <div className="menu" style={{ minWidth: 170 }}>
          <Item s="new" />
          <Item s="applied" />
          {/* Interview parent — click toggles the inline sub-stages (stays open) */}
          <button onClick={(e) => { e.stopPropagation(); setSub(v => !v); }}
            className={`menu-item${inInterview ? " sel" : ""}`}
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS.interview, flexShrink: 0 }} />
              Interview{inInterview ? ` · ${STATUS_LABELS[status]}` : ""}
            </span>
            <span style={{ color: "var(--tx-3)", fontSize: 12, marginLeft: 8 }}>{sub ? "▾" : "▸"}</span>
          </button>
          {sub && INTERVIEW_STAGES.map(s => (
            <button key={s} onClick={() => pick(s)} className={`menu-item${status === s ? " sel" : ""}`}
              style={{ paddingLeft: 26 }}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[s], flexShrink: 0 }} />
              {STATUS_LABELS[s] || s}
            </button>
          ))}
          <Item s="skipped" />
        </div>
      )}
    </div>
  );
}

// ── Section title — icon badge + label, shared by Job Info / Company Info / Job Description
function SectionTitle({ icon, children, color = "#7c3aed", bg = "rgba(124,58,237,0.10)" }: {
  icon: string; children: React.ReactNode; color?: string; bg?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <div style={{
        width: 22, height: 22, borderRadius: 7, background: bg,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <Ic d={icon} size={12} color={color} />
      </div>
      <span style={{
        fontSize: 13.5, fontWeight: 700, color, letterSpacing: "0.01em",
        background: bg, padding: "3px 10px", borderRadius: 6,
      }}>{children}</span>
    </div>
  );
}

// ── Job Info panel ────────────────────────────────────────────────────────────
function JobInfoTab({ job }: { job: Job }) {
  const postedTs = job.posted_at || job.scraped_at || "";
  const postedLabel = relTimeDetail(postedTs);
  const hcOrig = (job as any).hc_original_date || "";
  const hcOrigLabel = hcOrig ? relTimeDetail(hcOrig) : "";
  const showOriginal = hcOrig && hcOrigLabel && hcOrigLabel !== postedLabel;

  const visaOk = job.visa_sponsorship === true;

  // Posted is now just another tile in the row — the oversized standalone
  // hero block wasted vertical space. HC's "originally posted" estimate
  // (when different) folds into the tile's hover tooltip instead of its
  // own visible line.
  const postedTitle = showOriginal ? `Originally ${hcOrigLabel} (HC estimate)` : undefined;

  const fields: { label: string; value: string; title?: string; hide?: boolean }[] = [
    { label: "Posted",     value: postedLabel || "Unknown", title: postedTitle },
    { label: "Location",   value: job.location || "" },
    { label: "Work Type",  value: job.remote || (job.location||"").toLowerCase().includes("remote") ? "Remote" : "Onsite" },
    { label: "Employment", value: job.employment_type || "", hide: !job.employment_type },
    { label: "Experience", value: job.experience_level ? `${job.experience_level} yrs` : "", hide: !job.experience_level },
    { label: "Salary",     value: job.salary || "", hide: !job.salary },
    { label: "Expires",    value: job.job_expiry ? new Date(job.job_expiry).toLocaleDateString("en-US", { timeZone: "America/New_York" }) : "", hide: !job.job_expiry },
    { label: "Sponsorship", value: visaOk ? "Mentioned" : "Not mentioned" },
  ].filter(f => !f.hide && f.value);

  // Helper: one field tile — bordered chip, label muted above, value below.
  // Fixed single-line value with ellipsis + title tooltip keeps every tile
  // the same height regardless of content length ("Cupertino, California,
  // United States" no longer wraps and breaks row alignment).
  const Field = ({ label, value, title }: { label: string; value: string; title?: string }) => (
    <div style={{
      display: "flex", flexDirection: "column", gap: 3, minWidth: 0,
      background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)",
      borderRadius: 10, padding: "7px 11px",
    }}>
      <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.06em", color: "var(--tx-3)" }}>{label}</span>
      <span
        title={title || value}
        style={{
          fontSize: 13, color: "var(--tx-1)", fontWeight: 600, lineHeight: 1.25,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}
      >{value}</span>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 2 }}>

      {/* Fields — all in one line, equal width, no wrap. Open Application
          link removed — the Apply button in the top action bar covers it.
          Sponsorship is the last tile, always shown (Mentioned / Not mentioned). */}
      <div style={{ display: "flex", flexWrap: "nowrap", gap: 8 }}>
        {fields.map(f => <div key={f.label} style={{ flex: "1 1 0", minWidth: 0 }}><Field label={f.label} value={f.value} title={f.title} /></div>)}
      </div>
    </div>
  );
}

// ── Company Info panel ─────────────────────────────────────────────────────────
function CompanyInfoTab({ job }: { job: Job }) {
  let careerDomain = "";
  try { careerDomain = new URL(job.url).hostname.replace("www.", ""); } catch {}

  const funding = job.company_funding && job.company_funding > 0
    ? job.company_funding >= 1_000_000_000
      ? `$${(job.company_funding / 1_000_000_000).toFixed(1)}B`
      : `$${(job.company_funding / 1_000_000).toFixed(0)}M`
    : "";

  const companyFields: { label: string; value: string; link?: boolean; hide?: boolean }[] = [
    { label: "Industry",     value: job.company_industry || "", hide: !job.company_industry },
    { label: "Headquarters", value: job.company_hq      || "", hide: !job.company_hq },
    { label: "Company Size", value: job.company_size     || "", hide: !job.company_size },
    { label: "Funding",      value: funding,                    hide: !funding },
    { label: "ATS Platform", value: job.source },
    { label: "Career Page",  value: careerDomain, link: true,   hide: !careerDomain },
  ].filter(f => !f.hide && f.value);

  // Matches JobInfoTab's tile treatment — bordered chip, single-line
  // ellipsis truncation so a long value never wraps and breaks row height.
  const Field = ({ label, value, link }: { label: string; value: string; link?: boolean }) => (
    <div style={{
      display: "flex", flexDirection: "column", gap: 3, minWidth: 0,
      background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)",
      borderRadius: 10, padding: "7px 11px",
    }}>
      <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const, letterSpacing: "0.06em", color: "var(--tx-3)" }}>{label}</span>
      {link
        ? <a href={job.url} target="_blank" rel="noreferrer" title={value} style={{ fontSize: 13, color: "var(--accent)", textDecoration: "none", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</a>
        : <span title={value} style={{ fontSize: 13, color: "var(--tx-1)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</span>
      }
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 2 }}>


      {/* Fields — all in one line, equal width, no wrap */}
      <div style={{ display: "flex", flexWrap: "nowrap", gap: 8 }}>
        {companyFields.map(f => <div key={f.label} style={{ flex: "1 1 0", minWidth: 0 }}><Field label={f.label} value={f.value} link={f.link} /></div>)}
      </div>
    </div>
  );
}


// ── Description tab ────────────────────────────────────────────────────────────
function DescriptionTab({ job, onUpdate, onToast }: { job: Job; onUpdate: (p: Partial<Job>) => void; onToast: (m: string, t?: "success"|"error") => void }) {
  const [fetching, setFetching] = useState(false);
  const [pasteMode, setPasteMode] = useState(false);
  const [pasted, setPasted] = useState("");

  const handleFetchJd = async () => {
    setFetching(true);
    try {
      const r = await api.fetchJd(job.id);
      if (r.description) { 
        const updates: any = { description: r.description };
        if (r.date) updates.posted_at = r.date;
        onUpdate(updates); 
        onToast("Description fetched", "success"); 
      }
    } catch { onToast("Fetch failed — try pasting JD manually", "error"); }
    finally { setFetching(false); }
  };

  const handlePasteSave = async () => {
    if (!pasted.trim()) return;
    try {
      await api.saveDescription(job.id, pasted);
      onUpdate({ description: pasted }); setPasteMode(false); setPasted("");
      onToast("Description saved", "success");
    } catch { onToast("Save failed", "error"); }
  };

  const desc = job.description || "";

  if (pasteMode) {
    return (
      <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Paste Job Description</span>
          <button className="btn btn-ghost" onClick={() => setPasteMode(false)} style={{ height: 28, fontSize: 12 }}>Cancel</button>
        </div>
        <textarea value={pasted} onChange={e => setPasted(e.target.value)}
          placeholder="Paste the full job description here…"
          style={{ minHeight: 320, fontSize: 13, lineHeight: 1.6, padding: 14, borderRadius: 12 }} />
        <button className="btn btn-accent" onClick={handlePasteSave} disabled={!pasted.trim()} style={{ height: 36, width: 140 }}>
          <Ic d={I.check} size={14} /> Save JD
        </button>
      </div>
    );
  }

  if (!desc) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 20px", gap: 16, textAlign: "center" }}>
        <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>No description available yet</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-accent" onClick={handleFetchJd} disabled={fetching} style={{ height: 36 }}>
            {fetching ? <Spinner size={13} color="#fff" /> : <Ic d={I.link} size={14} />} {fetching ? "Fetching…" : "Fetch from URL"}
          </button>
          <button className="btn btn-ghost" onClick={() => setPasteMode(true)} style={{ height: 36 }}>
            <Ic d={I.clip} size={14} /> Paste JD
          </button>
        </div>
      </div>
    );
  }
  const isHtml = /<\s*(p|div|ul|li|br|strong|em|h[1-6])\b/i.test(desc);

  const jdBtnStyle = (color: string, bg: string): React.CSSProperties => ({
    height: 30, fontSize: 11, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 5,
    padding: "0 12px", borderRadius: 7, border: `1.5px solid ${color}`, background: bg,
    color, cursor: "pointer", transition: "opacity .15s",
  });
  const actionsRow = (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <button onClick={handleFetchJd} disabled={fetching} style={jdBtnStyle("#0ea5e9", "rgba(14,165,233,0.08)")}>
        {fetching ? <Spinner size={11} /> : <Ic d={I.refresh} size={12} />} Refresh JD
      </button>
      <button onClick={() => setPasteMode(true)} style={jdBtnStyle("#8b5cf6", "rgba(139,92,246,0.08)")}>
        <Ic d={I.clip} size={12} /> Paste JD
      </button>
      <button onClick={async () => {
        let plain: string;
        if (/<[a-zA-Z]/.test(desc)) {
          const tmp = document.createElement("div");
          tmp.innerHTML = desc;
          tmp.querySelectorAll("script, style, noscript").forEach(el => el.remove());
          plain = (tmp.textContent || "").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
        } else {
          plain = desc.trim();
        }
        try { await navigator.clipboard.writeText(plain); onToast("JD copied!", "success"); }
        catch { onToast("Copy failed — try selecting text manually", "error"); }
      }} style={jdBtnStyle("#10b981", "rgba(16,185,129,0.08)")}>
        <Ic d={I.copy} size={12} /> Copy JD
      </button>
    </div>
  );

  // Partial JD warning: plain text under 800 chars = likely AI summary fallback
  const isPartial = !isHtml && desc.length < 800;

  // HTML description — render directly with scoped styles
  if (isHtml) {
    return (
      <div>
        {actionsRow}
        <div
          className="jd-body jd-html"
          dangerouslySetInnerHTML={{ __html: desc }}
        />
      </div>
    );
  }

  // Plain text / markdown description
  const lines = desc.split("\n");
  const rendered: JSX.Element[] = [];
  let list: JSX.Element[] = [];
  const flush = (k: number) => {
    if (list.length) { rendered.push(<ul key={"ul" + k} style={{ margin: "4px 0 12px", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>{list}</ul>); list = []; }
  };
  lines.forEach((ln, i) => {
    if (ln.startsWith("## ") || ln.startsWith("# ")) {
      flush(i); rendered.push(<h3 key={i} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: "20px 0 8px", textTransform: "uppercase", letterSpacing: "0.04em" }}>{ln.replace(/^#+\s+/, "")}</h3>);
    } else if (ln.startsWith("- ") || ln.startsWith("• ")) {
      list.push(<li key={i} style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>{ln.slice(2)}</li>);
    } else if (!ln.trim()) { flush(i); }
    else { flush(i); rendered.push(<p key={i} style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.65, margin: "0 0 10px" }}>{ln}</p>); }
  });
  flush(9999);
  return (
    <div>
      {actionsRow}
      {isPartial && (
        <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)", fontSize: 12.5, color: "#92400e", display: "flex", alignItems: "center", gap: 8 }}>
          ⚠️ Partial JD — this is an AI-extracted summary, not the full description. Click <b>Refresh JD</b> to fetch the full text, or <b>Paste JD</b> to add it manually.
        </div>
      )}
      <div className="jd-body">{rendered}</div>
    </div>
  );
}

// ── Tailored resume — structured document view ──────────────────────────────
// Parses the plain-text tailored resume into name/contact/sections so it
// renders like an actual resume document instead of a monospace text dump.
type ResumeJobBlock = { header: string; bullets: string[]; techLine: string };
type ResumeSection  = { title: string; kind: "experience" | "skills" | "plain"; lines: string[]; jobs: ResumeJobBlock[] };
type ParsedResume    = { name: string; contact: string; sections: ResumeSection[] };

function _isAllCapsHeader(line: string): boolean {
  const s = line.trim().replace(/:$/, "");
  return s.length > 3 && s === s.toUpperCase() && /[A-Z]/.test(s) && !s.startsWith("•");
}

function parseResumeDoc(text: string): ParsedResume {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i++;
  const name = (lines[i] || "").trim();
  i++;
  while (i < lines.length && !lines[i].trim()) i++;
  const contact = (lines[i] && !_isAllCapsHeader(lines[i])) ? lines[i].trim() : "";
  if (contact) i++;

  const sections: ResumeSection[] = [];
  let cur: ResumeSection | null = null;
  let curJob: ResumeJobBlock | null = null;

  const pushJob = () => { if (curJob) { cur!.jobs.push(curJob); curJob = null; } };
  const closeSection = () => { pushJob(); if (cur) sections.push(cur); cur = null; };

  for (; i < lines.length; i++) {
    const raw = lines[i];
    const s = raw.trim();
    if (_isAllCapsHeader(s)) {
      closeSection();
      const title = s.replace(/:$/, "");
      const kind: ResumeSection["kind"] =
        title.includes("EXPERIENCE") ? "experience" :
        title.includes("SKILL") ? "skills" : "plain";
      cur = { title, kind, lines: [], jobs: [] };
      continue;
    }
    if (!cur) continue; // stray lines before first header — ignore
    if (cur.kind === "experience") {
      if (!s) continue;
      if (/^Technolog/i.test(s)) { if (curJob) curJob.techLine = s; continue; }
      if (s.includes(" @ ") && !s.startsWith("•")) {
        pushJob();
        curJob = { header: s, bullets: [], techLine: "" };
        continue;
      }
      if (curJob) {
        if (s.startsWith("•")) curJob.bullets.push(s.slice(1).trim());
        else curJob.header += " " + s; // wrapped header (e.g. location on its own line)
      }
      continue;
    }
    cur.lines.push(raw);
  }
  closeSection();

  return { name, contact, sections };
}

const _RESUME_ACCENT = "#7c3aed";

function ResumeSkillsBlock({ lines }: { lines: string[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {lines.filter(l => l.trim()).map((l, i) => {
        const idx = l.indexOf(":");
        const label = idx > -1 ? l.slice(0, idx).trim() : "";
        const rest  = idx > -1 ? l.slice(idx + 1).trim() : l.trim();
        const items = rest.split(",").map(x => x.trim()).filter(Boolean);
        return (
          <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
            {label && <span style={{ fontSize: 11.5, fontWeight: 700, color: "var(--text-primary)", minWidth: 170, flexShrink: 0 }}>{label}</span>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {items.map((it, j) => (
                <span key={j} style={{ fontSize: 11.5, padding: "2px 8px", borderRadius: 999, background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}>{it}</span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ResumeJobBlockView({ job }: { job: ResumeJobBlock }) {
  // Header shape: "Title @ Company | City, State          Date – Date"
  const m = job.header.match(/^(.*?)\s+@\s+(.*?)(?:\s{2,}|\t)([A-Za-z].*(?:–|-|Present).*)?$/);
  let left = job.header, dates = "";
  if (m) {
    dates = (m[3] || "").trim();
    left = `${m[1].trim()} @ ${m[2].trim()}`;
  }
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--text-primary)" }}>{left}</span>
        {dates && <span style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "var(--f-mono, monospace)", whiteSpace: "nowrap" }}>{dates}</span>}
      </div>
      <ul style={{ margin: "6px 0 0", padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: 5 }}>
        {job.bullets.map((b, i) => (
          <li key={i} style={{ fontSize: 12.5, lineHeight: 1.6, color: "var(--text-secondary)" }}>{b}</li>
        ))}
      </ul>
      {job.techLine && (
        <div style={{ marginTop: 7, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
          <span style={{ fontWeight: 600 }}>{job.techLine.split(":")[0]}:</span>{job.techLine.split(":").slice(1).join(":")}
        </div>
      )}
    </div>
  );
}

function ResumeDocView({ text }: { text: string }) {
  const parsed = parseResumeDoc(text);
  if (!parsed.name) {
    // Fallback — unparseable format, show raw text rather than an empty page
    return <pre className="mono" style={{ fontSize: 11.5, lineHeight: 1.7, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>{text}</pre>;
  }
  return (
    <div style={{
      background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 14,
      padding: "32px 40px", width: "100%", boxSizing: "border-box",
    }}>
      <div style={{ textAlign: "center", marginBottom: 18 }}>
        <div style={{ fontSize: 21, fontWeight: 800, color: "var(--text-primary)", letterSpacing: "0.01em" }}>{parsed.name}</div>
        {parsed.contact && <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{parsed.contact}</div>}
      </div>
      {parsed.sections.map((sec, i) => (
        <div key={i} style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: 11.5, fontWeight: 700, color: _RESUME_ACCENT, letterSpacing: "0.08em",
            paddingBottom: 5, marginBottom: 12, borderBottom: `2px solid ${_RESUME_ACCENT}33`,
          }}>{sec.title}</div>
          {sec.kind === "experience" && sec.jobs.map((jb, j) => <ResumeJobBlockView key={j} job={jb} />)}
          {sec.kind === "skills" && <ResumeSkillsBlock lines={sec.lines} />}
          {sec.kind === "plain" && (
            <ul style={{ margin: 0, padding: sec.lines.some(l => l.trim().startsWith("•")) ? "0 0 0 18px" : 0, display: "flex", flexDirection: "column", gap: 5, listStyle: sec.lines.some(l => l.trim().startsWith("•")) ? "disc" : "none" }}>
              {sec.lines.filter(l => l.trim()).map((l, k) => (
                <li key={k} style={{ fontSize: 12.5, lineHeight: 1.65, color: "var(--text-secondary)" }}>{l.trim().replace(/^•\s*/, "")}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Resume tab ─────────────────────────────────────────────────────────────────
function ResumeTab({ job, tailoring, startedAt, onTailor, onCancel, onToast, onUpdate }: {
  job: Job; tailoring: boolean; startedAt?: number | null; onTailor: () => void; onCancel: () => void;
  onToast: (m: string, t?: "success" | "error") => void;
  onUpdate: (patch: Partial<Job>) => void;
}) {
  // Hooks MUST be at top level — never inside conditionals
  const [editing, setEditing] = useState(false);
  const [draft, setDraft]     = useState("");
  const [saving, setSaving]   = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!tailoring) {
      setElapsed(0);
      return;
    }
    // Anchor to the real tailor start time from App state — a local ref
    // resets to 0 whenever this tab unmounts/remounts (tab switching)
    const start = startedAt ?? Date.now();
    setElapsed(Math.floor((Date.now() - start) / 1000));
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [tailoring, startedAt]);

  if (!job.tailored_resume && !tailoring) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 20px", gap: 18, textAlign: "center" }}>
        <div style={{ width: 64, height: 64, borderRadius: 999, background: "rgba(139,92,246,0.1)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid rgba(139,92,246,0.25)" }}>
          <Ic d={I.sparkles} size={28} color="var(--purple)" />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>No tailored resume yet</div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>Generate an ATS-optimized resume for this role</div>
        </div>
        <button className="btn btn-accent" onClick={onTailor} style={{ height: 40, padding: "0 20px", width: 240, justifyContent: "center" }}>
          <Ic d={I.sparkles} size={15} /> Tailor with AI
        </button>
      </div>
    );
  }
  if (tailoring) {
    const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const ss = String(elapsed % 60).padStart(2, "0");
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "80px 20px", gap: 14 }}>
        <div style={{ position: "relative", width: 60, height: 60 }}>
          <Spinner size={60} color="var(--accent)" />
          <div style={{
            position: "absolute", inset: 0, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 11, fontWeight: 700,
            color: "var(--accent)", fontFamily: "var(--f-mono, monospace)",
            letterSpacing: "0.04em",
          }}>
            {mm}:{ss}
          </div>
        </div>
        <div style={{ fontSize: 13.5, color: "var(--text-secondary)" }}>Tailoring resume with AI…</div>
        <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
          {elapsed < 60 ? "Usually takes 1–3 minutes" : elapsed < 120 ? "Still working — almost there…" : "Taking longer than usual — complex resume"}
        </div>
        <button
          onClick={onCancel}
          style={{ marginTop: 4, fontSize: 12.5, fontWeight: 500, color: "var(--text-muted)", background: "none", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: "6px 18px", cursor: "pointer" }}
        >
          Cancel
        </button>
      </div>
    );
  }
  // ATS before/after is no longer rendered on this tab — the score still
  // computes server-side and drives the job-card badge, min-ATS filter, and
  // sort-by-ATS.

  // Surface qualify disqualifiers — AI already scored these, just not shown here
  const qr = (job.qualify_result as any) ?? null;
  const disqualifiers: string[] = [];
  if (qr?.criteria && typeof qr.criteria === "object" && !Array.isArray(qr.criteria)) {
    const failKeys = ["sponsorship", "location", "experience", "seniority"];
    for (const key of failKeys) {
      const c = qr.criteria[key];
      if (c && c.pass === false) {
        disqualifiers.push(`${key.replace(/_/g, " ").replace(/\b\w/g, (x: string) => x.toUpperCase())}: ${c.note}`);
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
      {/* "Review before applying" is moot once the job is applied/interviewing —
          show the flags only while the job is still new. */}
      {disqualifiers.length > 0 && job.status === "new" && (
        <div style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#f87171", marginBottom: 2 }}>⚠ Qualify flags — review before applying</div>
          {disqualifiers.map((d, i) => <div key={i} style={{ fontSize: 12.5, color: "#fca5a5" }}>{d}</div>)}
        </div>
      )}
      {/* Review gate banners — DISABLED by user request.
          Backend always sends needs_review=false now, so these never fired
          anyway; commented out here too so the JSX doesn't silently depend
          on that. Uncomment both blocks to restore the green/red banner. */}
      {/* {job.needs_review === true && (
        <div style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.35)", borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#fbbf24", marginBottom: 2 }}>🔴 Needs review — read this resume before applying</div>
          {(job.review_reasons || []).slice(0, 6).map((r, i) => <div key={i} style={{ fontSize: 12.5, color: "#fcd34d" }}>{r}</div>)}
        </div>
      )}
      {job.needs_review === false && job.tailored_resume && (
        <div style={{ background: "rgba(34,197,94,0.07)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 10, padding: "8px 14px", fontSize: 12.5, color: "#4ade80", fontWeight: 600 }}>
          🟢 Auto-approved — passed all quality checks, safe to apply
        </div>
      )} */}
      {/* TOP ROW — Detected Context (left) + Resume Score & downloads (right) */}
      <div style={{ display: "flex", gap: 18, alignItems: "flex-start", marginBottom: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {job.tailor_context && (() => {
            const c = job.tailor_context!;
            const cloud = (c.target_cloud || "None").trim();
            const swapped = cloud === "AWS" || cloud === "Azure" || cloud === "GCP";
            const chip = (label: string, tone: "blue" | "green" | "muted") => {
              const bg = tone === "blue" ? "#3b82f6" : tone === "green" ? "#16a34a" : "#d97706";
              return (
                <span key={label} style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
                  background: bg, color: "#fff", whiteSpace: "nowrap" }}>{label}</span>
              );
            };
            const row = (title: string, items: string[], tone: "blue" | "green" | "muted") => (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: 6 }}>{title}</div>
                {items.length
                  ? <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{items.map(t => chip(t, tone))}</div>
                  : <div style={{ fontSize: 12, color: "var(--text-muted)" }}>none</div>}
              </div>
            );
            return (
              <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 12, padding: "14px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)" }}>Detected Context</span>
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Target cloud:</span>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: swapped ? "#38bdf8" : "var(--text-muted)" }}>
                    {swapped ? cloud : cloud === "Multi" ? "Multi-cloud" : "None"}
                  </span>
                  <span style={{ fontSize: 10.5, color: "var(--tx-2, #a9adba)" }}>
                    {swapped
                      ? `— Jobs 1 & 2 converted to ${cloud}, older roles keep their real cloud`
                      : "— no swap; every job keeps its real cloud, JD tools layered on top"}
                  </span>
                </div>
                {row("JD target tools", c.target_tools || [], "blue")}
                {row("Already in resume", c.present || [], "green")}
                {row("Missing", c.missing || [], "muted")}
              </div>
            );
          })()}
          {/* Tailored resume, directly under the context band — fills the
              left column so there is no dead space beside the score panel. */}
          <div style={{ display: "flex", flexDirection: "column", marginTop: 4 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)" }}>Tailored Resume</div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {typeof job.generation_seconds === "number" && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    Generated in {(() => {
                      const m = Math.floor(job.generation_seconds / 60), s = job.generation_seconds % 60;
                      return m > 0 ? `${m}min ${s}sec` : `${s}sec`;
                    })()}
                  </span>
                )}
              {!editing ? (
                <button className="btn btn-ghost" style={{ fontSize: 11, height: 28, padding: "0 10px" }}
                  onClick={() => { setDraft(job.tailored_resume || ""); setEditing(true); }}>
                  ✏️ Edit
                </button>
              ) : (
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 11, height: 28, padding: "0 10px" }}
                    onClick={() => setEditing(false)}>
                    Cancel
                  </button>
                  <button className="btn btn-accent" style={{ fontSize: 11, height: 28, padding: "0 12px" }}
                    disabled={saving}
                    onClick={async () => {
                      setSaving(true);
                      try {
                        await api.saveTailoredResume(job.id, draft);
                        onUpdate({ tailored_resume: draft } as any);
                        setEditing(false);
                        onToast("Resume saved", "success");
                      } catch (e: any) {
                        onToast(e.message || "Save failed", "error");
                      } finally { setSaving(false); }
                    }}>
                    {saving ? "Saving…" : "💾 Save"}
                  </button>
                </div>
              )}
              </div>
            </div>
            {editing ? (
              <textarea
                value={draft}
                onChange={e => setDraft(e.target.value)}
                style={{ flex: 1, width: "100%", background: "var(--bg-surface)", border: "1px solid var(--purple)", borderRadius: 12, padding: 18, fontSize: 11.5, lineHeight: 1.7, color: "var(--text-primary)", resize: "vertical", minHeight: 420, fontFamily: "var(--f-mono, monospace)", outline: "none", boxSizing: "border-box" }}
              />
            ) : (
              <div style={{ width: "100%" }}>
                <ResumeDocView text={job.tailored_resume || ""} />
              </div>
            )}
            {(job.ats_quality?.count ?? 0) > 0 && (
              <div title={(job.ats_quality?.fragments || []).map(f => `• ${f}`).join("\n")}
                style={{ marginTop: 10, padding: "9px 12px", borderRadius: 10, fontSize: 12, lineHeight: 1.45,
                  background: "rgba(245,158,11,0.09)", border: "1px solid rgba(245,158,11,0.3)", color: "#d97706", fontWeight: 600 }}>
                ⚠ {job.ats_quality!.count} bullet{job.ats_quality!.count > 1 ? "s" : ""} look cut off — hover to see, edit before applying
              </div>
            )}
          </div>
        </div>

        <div style={{ width: 240, flexShrink: 0, position: "sticky", top: 16, alignSelf: "flex-start", display: "flex", flexDirection: "column", gap: 12 }}>
          {job.gate_scores && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 8 }}>Resume Score</div>
              <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 12, padding: 16 }}>
                {([
                  ["ATS", job.gate_scores.ats, "#22c55e"],
                  ["Recruiter", job.gate_scores.recruiter, "#3b82f6"],
                  ["Hiring Manager", job.gate_scores.hiring_manager, "#a855f7"],
                ] as const).map(([label, gate, color]) => gate && (
                  <div key={label} style={{ marginBottom: 14 }} title={gate.note || ""}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 6 }}>
                      <span style={{ color: "var(--text-muted)" }}>{label}</span>
                      <span className="mono" style={{ color, fontWeight: 600 }}>{gate.score}</span>
                    </div>
                    <ATSBar score={gate.score} height={6} color={color} />
                  </div>
                ))}
                {typeof job.gate_scores.overall === "number" && (() => {
                  const o = job.gate_scores.overall;
                  const rating = scoreRating(o);
                  const rec = submitRec(o);
                  return (
                    <div style={{ marginTop: 4, textAlign: "center", padding: "10px 0 0", borderTop: "1px solid var(--border-subtle)" }}>
                      <span style={{ fontSize: 22, fontWeight: 700, color: rating.color }}>{o}</span>
                      <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 4 }}>overall</span>
                      <div style={{ marginTop: 4, fontSize: 12, fontWeight: 700, color: rating.color, letterSpacing: "0.03em" }}>{rating.label}</div>
                      <div style={{ marginTop: 8, fontSize: 11.5, fontWeight: 700, padding: "5px 10px", borderRadius: 8,
                        background: rec.bg, color: rec.fg, border: `1px solid ${rec.bd}` }}>{rec.t}</div>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 8 }}>Download</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <button className="btn" style={{ background: "rgba(239,68,68,0.12)", color: "#f87171", border: "1px solid rgba(239,68,68,0.3)" }}
                onClick={() => downloadFile(api.pdfUrl(job.id), "resume.pdf").catch(e => onToast(e.message, "error"))}><Ic d={I.download} size={14} /> PDF</button>
              <button className="btn" style={{ background: "rgba(59,130,246,0.12)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.3)" }}
                onClick={() => downloadFile(api.docxUrl(job.id), "resume.docx").catch(e => onToast(e.message, "error"))}><Ic d={I.download} size={14} /> DOCX</button>
              <button className="btn" style={{ background: "rgba(34,197,94,0.12)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.3)" }}
                onClick={() => { navigator.clipboard.writeText(editing ? draft : (job.tailored_resume || "")); onToast("Copied!", "success"); }}><Ic d={I.copy} size={14} /> Copy</button>
              <button className="btn btn-accent"
                onClick={() => downloadFile(api.savePackageUrl(job.id), "package.zip").catch(e => onToast(e.message, "error"))}>
                <Ic d={I.folder} size={14} /> Save Package
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Cover Letter tab ───────────────────────────────────────────────────────────
function CoverTab({ job, generating, onGenerate, onChange, onToast }: {
  job: Job; generating: boolean; onGenerate: () => void;
  onChange: (v: string) => void; onToast: (m: string, t?: "success" | "error") => void;
}) {
  if (!job.cover_letter && !generating) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 20px", gap: 18, textAlign: "center" }}>
        <div style={{ width: 64, height: 64, borderRadius: 999, background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border-subtle)" }}>
          <Ic d={I.fileText} size={26} color="var(--text-muted)" />
        </div>
        <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>No cover letter yet for this role</div>
        <button className="btn btn-accent" onClick={onGenerate} style={{ height: 40, padding: "0 20px", width: 260, justifyContent: "center" }}>
          <Ic d={I.sparkles} size={15} /> Generate Cover Letter
        </button>
      </div>
    );
  }
  if (generating) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "80px 0", gap: 12, color: "var(--text-muted)" }}><Spinner size={24} color="var(--accent)" /> Writing…</div>;

  return (
    <div>
      <div className="tailor-note">
        <Ic d={I.sparkles} size={15} />
        AI-drafted cover letter for {job.company}. Edit freely or copy as-is.
      </div>
      <div className="cover-card">
        <textarea className="cover-text" value={job.cover_letter || ""} onChange={e => onChange(e.target.value)}
          style={{ width: "100%", minHeight: 280, fontSize: 13.5, lineHeight: 1.7, background: "transparent", border: "none", color: "var(--tx-2)", fontFamily: "var(--f-ui)", resize: "vertical" }} />
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
        <button className="act ai" onClick={() => { navigator.clipboard.writeText(job.cover_letter || ""); onToast("Cover letter copied", "success"); }}>
          <Ic d={I.copy} size={14} /> Copy letter
        </button>
        <button className="act" onClick={() => downloadFile(api.coverPdfUrl(job.id), "cover_letter.pdf").catch(e => onToast(e.message, "error"))}>
          <Ic d={I.download} size={14} /> PDF
        </button>
        <button className="act" onClick={() => downloadFile(api.coverDocxUrl(job.id), "cover_letter.docx").catch(e => onToast(e.message, "error"))}>
          <Ic d={I.download} size={14} /> DOCX
        </button>
        <button className="act ghost" onClick={onGenerate}>
          <Ic d={I.sparkles} size={14} /> Regenerate
        </button>
      </div>
    </div>
  );
}

// ── Notes tab ──────────────────────────────────────────────────────────────────
function NotesTab({ job, onUpdate, onToast }: {
  job: Job; onUpdate: (patch: Partial<Job>) => void; onToast: (m: string, t?: "success" | "error") => void;
}) {
  const [notes, setNotes] = useState(job.notes || "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { setNotes(job.notes || ""); }, [job.id]);

  const handleNotes = (v: string) => {
    setNotes(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try { await api.saveNotes(job.id, v); } catch {}
    }, 800);
  };

  return (
    <div>
      <textarea
        className="notes-area"
        value={notes}
        onChange={e => handleNotes(e.target.value)}
        placeholder="Add private notes — recruiter name, referral, salary expectations…"
      />
      <div style={{ fontSize: 11.5, color: "var(--tx-faint)", marginTop: 8, display: "flex", alignItems: "center", gap: 6 }}>
        <Ic d={I.briefcase} size={13} /> Notes auto-save locally and stay private to you.
      </div>
    </div>
  );
}

// ── Info tab: job info + company info side by side, notes at bottom ───────────
function InfoTab({ job, onUpdate, onToast }: {
  job: Job; onUpdate: (patch: Partial<Job>) => void; onToast: (m: string, t?: "success" | "error") => void;
}) {
  const sectionLabel = (text: string) => (
    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 4 }}>{text}</div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Job + Company info side by side */}
      <div style={{ display: "flex", gap: 36, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 300 }}>
          {sectionLabel("Job Info")}
          <JobInfoTab job={job} />
        </div>
        <div style={{ flex: 1, minWidth: 300 }}>
          {sectionLabel("Company Info")}
          <CompanyInfoTab job={job} />
        </div>
      </div>

      {/* Notes */}
      <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 20, marginTop: 16 }}>
        {sectionLabel("Notes")}
        <div style={{ marginTop: 10 }}>
          <NotesTab job={job} onUpdate={onUpdate} onToast={onToast} />
        </div>
      </div>
    </div>
  );
}

// ── Main JobDetail ─────────────────────────────────────────────────────────────
export function JobDetail({ job, tab, setTab, onUpdate, onToast, busy, busyJobId, busyStartedAt, tailorRuns, runAction, onCancel }: {
  job: Job | null; tab: string; setTab: (t: string) => void;
  onUpdate: (patch: Partial<Job>) => void;
  onToast: (m: string, t?: "success" | "error") => void;
  busy: string | null; busyJobId: string | null; busyStartedAt?: number | null;
  tailorRuns: Record<string, number>; runAction: (a: string) => void; onCancel: (jobId?: string) => void;
}) {
  if (!job) {
    return (
      <div className="detail-pane">
        <div className="empty">
          <div className="empty-inner">
            <div className="empty-ico">
              <Ic d={I.briefcase} size={28} />
            </div>
            <h3>No job selected</h3>
            <p>Select a job from the list to view details, run AI analysis, and tailor your resume.</p>
          </div>
        </div>
      </div>
    );
  }

  const tabHasContent: Record<string, boolean> = {
    resume: !!job.tailored_resume,
    cover: !!job.cover_letter,
    info: !!(job.notes || job.deadline || job.interview_date),
  };

  const handleStatusChange = async (s: string) => {
    try { await api.setStatus(job.id, s as JobStatus); onUpdate({ status: s as JobStatus }); onToast("Marked as " + s, "success"); }
    catch (e: any) { onToast(e.message, "error"); }
  };

  const scoreNum = (job.qualify_result as any)?.score ?? null;
  const circumference = 2 * Math.PI * 26;
  const offset = scoreNum != null ? circumference * (1 - scoreNum / 100) : circumference;

  // Which resume formats have already been pulled for THIS job. Mirrors the
  // Apply → Applied feedback: a glance shows what you already downloaded.
  // Per-browser (localStorage) — a download is a local act, not app state.
  const [grabbed, setGrabbed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try { setGrabbed(JSON.parse(localStorage.getItem(`jh_dl_${job.id}`) || "{}")); }
    catch { setGrabbed({}); }
  }, [job.id]);
  const markGrabbed = (fmt: string) => {
    setGrabbed(g => {
      const next = { ...g, [fmt]: true };
      try { localStorage.setItem(`jh_dl_${job.id}`, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  };

  // On-demand qualify: jobs outside the auto-qualify scope show "–" — click
  // the ring to score just this one (single cheap model call).
  const [qualifying, setQualifying] = useState(false);
  const runQualify = async () => {
    if (qualifying || scoreNum != null) return;
    setQualifying(true);
    try {
      const res = await api.qualifyJob(job.id);
      onUpdate({ qualify_result: res } as any);
      onToast("AI match scored", "success");
    } catch (e: any) { onToast(e.message || "Qualify failed", "error"); }
    finally { setQualifying(false); }
  };

  return (
    <div className="detail-pane">
        {/* Header — stays pinned; only the tab content below scrolls */}
        <div className="detail-head">
          <div className="dh-top">
            <div className="dh-logo">
              <CompanyLogo url={job.url} company={job.company} size={50} />
            </div>
            <div className="dh-info">
              <h1 className="dh-title">{job.title}</h1>
              <div className="dh-co">
                <span className="co-name">{job.company}</span>
                {job.location && (
                  <span className="meta-i"><Ic d={I.map} size={13} />{job.location}</span>
                )}
                {(job.remote || (job.location || "").toLowerCase().includes("remote")) && (
                  <span className="badge-remote">Remote</span>
                )}
                {job.salary && (
                  <span className="meta-i"><Ic d={I.briefcase} size={13} />{job.salary}</span>
                )}
              </div>
              <div className="dh-co" style={{ marginTop: 4 }}>
                <span className="badge-src">
                  <AtsLogo source={job.source} size={13} />
                  {job.source}
                </span>
                {(job.posted_at || job.scraped_at) && (
                  <span className="meta-i"><Ic d={I.clock} size={13} />{relTimeDetail(job.posted_at || job.scraped_at!)}</span>
                )}
              </div>
            </div>

            {/* Score ring — pre-tailor triage only. Once a tailored resume score
                exists the fit decision is made, so the ring disappears (same
                rule as the card's match pill). Clickable when unscored. */}
            {job.ats_score_after == null && job.gate_scores?.overall == null && (
              <div className="dh-score"
                onClick={runQualify}
                title={scoreNum != null ? "AI match score" : "Not scored yet — click to score this job"}
                style={scoreNum == null ? { cursor: "pointer" } : undefined}>
                {qualifying ? <Spinner size={28} /> : <ScoreRingDetail value={scoreNum} />}
                <span className="ring-label">{qualifying ? "Scoring…" : scoreNum != null ? "AI Match" : "Score now"}</span>
              </div>
            )}
          </div>

          {/* Actions — an applied-stage job is past the apply/tailor decisions,
              so those calls-to-action disappear; the posting link, the stage
              dropdown, and the resume downloads remain. */}
          <div className="actions">
            <a href={job.url} target="_blank" rel="noreferrer"
              className={APPLIED_STAGES.includes(job.status) ? "act" : "act primary"}
              style={{ textDecoration: "none" }}
              title="Open the application page">
              <Ic d={I.link} size={14} /> {APPLIED_STAGES.includes(job.status) ? "Job Posting" : "Apply"}
            </a>
            {!APPLIED_STAGES.includes(job.status) && (
              <button onClick={() => runAction("resume")} disabled={!!tailorRuns[job.id]} className="act ai"
                title={Object.keys(tailorRuns).length ? `${Object.keys(tailorRuns).length} tailoring in parallel` : undefined}>
                {tailorRuns[job.id] ? <><Spinner size={13} /> Tailoring…</> : <><Ic d={I.sparkles} size={14} /> Tailor Resume</>}
              </button>
            )}
            {/* Middle group: status actions, gapped away from the apply/tailor pair.
                "Mark Applied" is hidden on stages past applied — moving back is
                the dropdown's job, not a headline button. */}
            {(!APPLIED_STAGES.includes(job.status) || job.status === "applied") && (
              <button
                className="act"
                style={{ marginLeft: 18, ...(job.status === "applied" ? {
                  background: "rgba(16,185,129,0.12)", borderColor: "var(--st-applied)", color: "var(--st-applied)",
                } : {}) }}
                onClick={() => handleStatusChange(job.status === "applied" ? "new" : "applied")}
              >
                <Ic d={I.checkCircle} size={14} /> {job.status === "applied" ? "Applied" : "Mark Applied"}
              </button>
            )}
            {!APPLIED_STAGES.includes(job.status) && (
              <button
                className="act"
                onClick={() => handleStatusChange(job.status === "skipped" ? "new" : "skipped")}
                style={job.status === "skipped" ? {
                  background: "rgba(93,99,112,0.15)", borderColor: "var(--st-skipped)", color: "var(--st-skipped)",
                } : undefined}
              >
                <Ic d={I.xCircle} size={14} /> {job.status === "skipped" ? "Skipped" : "Skip"}
              </button>
            )}
            <StatusDropdown status={job.status} onChange={handleStatusChange} />
            {/* Right group: Tailored Resume downloads — only once a resume exists */}
            {job.tailored_resume && !tailorRuns[job.id] && (
              <div style={{ display: "inline-flex", alignItems: "stretch", height: 32, borderRadius: 8, overflow: "hidden",
                marginLeft: "auto",
                border: "1px solid rgba(124,58,237,0.35)", background: "rgba(124,58,237,0.07)" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "0 10px", fontSize: 11,
                  fontWeight: 700, color: "#7c3aed", borderRight: "1px solid rgba(124,58,237,0.25)" }}>
                  <Ic d={I.download} size={12} color="#7c3aed" /> Tailored Resume
                </span>
                {([
                  ["PDF",  () => downloadFile(api.pdfUrl(job.id), "resume.pdf").then(() => markGrabbed("PDF")).catch(e => onToast(e.message, "error"))],
                  ["DOCX", () => downloadFile(api.docxUrl(job.id), "resume.docx").then(() => markGrabbed("DOCX")).catch(e => onToast(e.message, "error"))],
                ] as [string, () => void][]).map(([label, fn]) => {
                  const done = !!grabbed[label];
                  return (
                    <button key={label} onClick={fn}
                      title={done ? `${label} already downloaded for this job — click to download again` : `Download ${label}`}
                      style={{ padding: "0 11px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                        background: done ? "rgba(16,185,129,0.14)" : "transparent",
                        color: done ? "#10b981" : "var(--tx-2)", border: "none",
                        borderRight: "1px solid rgba(124,58,237,0.18)",
                        display: "inline-flex", alignItems: "center", gap: 4 }}
                      onMouseOver={e => { e.currentTarget.style.background = done ? "rgba(16,185,129,0.22)" : "rgba(124,58,237,0.14)"; if (!done) e.currentTarget.style.color = "#7c3aed"; }}
                      onMouseOut={e => { e.currentTarget.style.background = done ? "rgba(16,185,129,0.14)" : "transparent"; if (!done) e.currentTarget.style.color = "var(--tx-2)"; }}>
                      {done && <Ic d={I.checkCircle} size={12} />}{label}
                    </button>
                  );
                })}
                <button onClick={() => { navigator.clipboard.writeText(job.tailored_resume || ""); markGrabbed("Copy"); onToast("Resume copied", "success"); }}
                  title={grabbed.Copy ? "Already copied for this job — click to copy again" : "Copy resume text"}
                  style={{ padding: "0 11px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                    background: grabbed.Copy ? "rgba(16,185,129,0.14)" : "transparent",
                    color: grabbed.Copy ? "#10b981" : "var(--tx-2)", border: "none",
                    display: "inline-flex", alignItems: "center", gap: 4 }}
                  onMouseOver={e => { e.currentTarget.style.background = grabbed.Copy ? "rgba(16,185,129,0.22)" : "rgba(124,58,237,0.14)"; if (!grabbed.Copy) e.currentTarget.style.color = "#7c3aed"; }}
                  onMouseOut={e => { e.currentTarget.style.background = grabbed.Copy ? "rgba(16,185,129,0.14)" : "transparent"; if (!grabbed.Copy) e.currentTarget.style.color = "var(--tx-2)"; }}>
                  <Ic d={grabbed.Copy ? I.checkCircle : I.copy} size={13} /> {grabbed.Copy ? "Copied" : "Copy"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Disqualifier banner */}
        {detectDisqualifiers(job.description || "").map(label => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", background: "#FEF2F2", borderBottom: "1px solid #FECACA", color: "#B91C1C", fontSize: 12.5, fontWeight: 500 }}>
            <span style={{ fontSize: 15 }}>⚠️</span> {label}
          </div>
        ))}

        {/* Top-level tabs */}
        <div className="tabs">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} className={`tab${tab === t.id ? " on" : ""}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content — the only scrolling region. Jump back to top when the
            selected job (or tab) changes — otherwise the next job opens at the
            previous job's scroll position. */}
        <div className="detail-scroll" ref={el => {
          if (el && (el as any)._jhKey !== `${job.id}|${tab}`) {
            (el as any)._jhKey = `${job.id}|${tab}`;
            el.scrollTop = 0;
          }
        }}>
        <div className="tab-body">
          {tab === "jobdetails" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {/* Job Info, Company Info, Job Description — stacked, each full width.
                  Side-by-side previously left a ragged gap under Job Info whenever
                  Company Info ran taller (e.g. a long Benefits list). */}
              <div>
                <SectionTitle icon={I.briefcase} color="#3b82f6" bg="rgba(59,130,246,0.10)">Job Info</SectionTitle>
                <JobInfoTab job={job} />
              </div>
              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 18, marginTop: 18 }}>
                <SectionTitle icon={I.building} color="#d97706" bg="rgba(217,119,6,0.10)">Company Info</SectionTitle>
                <CompanyInfoTab job={job} />
              </div>
              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 18, marginTop: 18 }}>
                <SectionTitle icon={I.fileText} color="#10b981" bg="rgba(16,185,129,0.10)">Job Description</SectionTitle>
                <DescriptionTab job={job} onUpdate={onUpdate} onToast={onToast} />
              </div>

            </div>
          )}
          {tab === "resume"   && (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <ResumeTab job={job} tailoring={!!tailorRuns[job.id]} startedAt={tailorRuns[job.id] || null} onTailor={() => runAction("resume")} onCancel={() => onCancel(job.id)} onToast={onToast} onUpdate={onUpdate} />
            </div>
          )}
          {tab === "cover"    && <CoverTab job={job} generating={busy === "cover" && busyJobId === job.id} onGenerate={() => runAction("cover")} onChange={v => onUpdate({ cover_letter: v })} onToast={onToast} />}
        </div>

      </div>
    </div>
  );
}
