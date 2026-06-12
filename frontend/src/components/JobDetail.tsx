import { useState, useEffect, useRef } from "react";
import type { Job, JobStatus } from "../types";
import { api, downloadFile } from "../api";
import { ATSBar, Spinner, CompanyLogo, AtsLogo } from "./primitives";

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
  folder:     '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  alert:      '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  clip:       '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
};

const TABS = [
  { id: "description", label: "Job Description" },
  { id: "info",        label: "Job & Company Info" },
  { id: "qualify",     label: "Qualify" },
  { id: "resume",      label: "Resume & Fit" },
  { id: "cover",       label: "Cover Letter" },
];

const STATUS_COLORS: Record<string, string> = {
  new: "var(--st-new)", applied: "var(--st-applied)", interview: "var(--st-interview)", skipped: "#5b6377",
};

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
function StatusDropdown({ status, onChange }: { status: string; onChange: (s: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const labels: Record<string, string> = { new: "New", applied: "Applied", interview: "Interview", skipped: "Skipped" };
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(!open)} className="act" style={{ height: 30, fontSize: 12 }}>
        <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[status] || "var(--tx-3)" }} />
        {labels[status] || status} <Ic d={I.chevDown} size={13} />
      </button>
      {open && (
        <div className="menu" style={{ minWidth: 140 }}>
          {Object.entries(labels).map(([s, l]) => (
            <button key={s} onClick={() => { onChange(s); setOpen(false); }} className={`menu-item${status === s ? " sel" : ""}`}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[s], flexShrink: 0 }} />
              {l}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Job Info tab ───────────────────────────────────────────────────────────────
function JobInfoTab({ job }: { job: Job }) {
  const postedTs = job.posted_at || job.scraped_at || "";
  const postedLabel = relTimeDetail(postedTs);
  const hcOrig = (job as any).hc_original_date || "";
  const hcOrigLabel = hcOrig ? relTimeDetail(hcOrig) : "";
  const showOriginal = hcOrig && hcOrigLabel && hcOrigLabel !== postedLabel;

  // FJ semantics: false = JD doesn't mention sponsorship (NOT a refusal)
  const visaVal = job.visa_sponsorship === true ? "✓ Sponsorship mentioned in JD"
                : job.visa_sponsorship === false ? "Not mentioned in JD — ask recruiter" : "—";
  const visaColor = job.visa_sponsorship === true ? "#16a34a" : "var(--tx-2)";

  const rows: [string, string, string?][] = [
    ["Location",      job.location || "—"],
    ["Country",       job.country  || "—"],
    ["Work Type",     job.remote || (job.location||"").toLowerCase().includes("remote") ? "Remote" : job.employment_type ? "" : "Onsite"],
    ["Employment",    job.employment_type || "—"],
    ["Experience",    job.experience_level ? `${job.experience_level} yrs` : "—"],
    ["Salary",        job.salary   || "—"],
    ["Source",        job.source   || "—"],
    ["Expires",       job.job_expiry ? new Date(job.job_expiry).toLocaleDateString("en-US", { timeZone: "America/New_York" }) : "—"],
  ];

  return (
    <div style={{ padding: "10px 0 20px", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Posted date */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 13, color: "var(--tx-3)", fontWeight: 500 }}>Posted</span>
        <span style={{ fontSize: 22, fontWeight: 700, color: "var(--tx-1)" }}>
          {postedLabel || "Unknown"}
        </span>
        {showOriginal && (
          <span style={{ fontSize: 12, color: "var(--tx-3)" }}>
            Originally posted: {hcOrigLabel} (HC estimate)
          </span>
        )}
      </div>

      {/* Visa sponsorship — highlight */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 10,
        background: job.visa_sponsorship === true ? "rgba(22,163,74,0.08)" : "var(--bg-2)" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: visaColor }}>{visaVal}</span>
        <span style={{ fontSize: 12, color: "var(--tx-3)" }}>Visa Sponsorship</span>
      </div>

      {/* Metadata grid */}
      <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "10px 16px" }}>
        {rows.filter(([,v]) => v).map(([k, v]) => (
          <>
            <span key={k+"-k"} style={{ fontSize: 13, color: "var(--tx-3)", fontWeight: 500 }}>{k}</span>
            <span key={k+"-v"} style={{ fontSize: 13, color: "var(--tx-1)" }}>{v}</span>
          </>
        ))}
      </div>

      {/* Apply link */}
      <a href={job.url} target="_blank" rel="noreferrer"
        style={{ fontSize: 13, color: "var(--accent)", wordBreak: "break-all", textDecoration: "none" }}>
        {job.url}
      </a>
    </div>
  );
}

// ── Company Info tab ───────────────────────────────────────────────────────────
function CompanyInfoTab({ job }: { job: Job }) {
  let careerDomain = "";
  try { careerDomain = new URL(job.url).hostname.replace("www.", ""); } catch {}

  const logoSrc = job.logo_url || "";
  const funding = job.company_funding && job.company_funding > 0
    ? job.company_funding >= 1_000_000_000
      ? `$${(job.company_funding / 1_000_000_000).toFixed(1)}B`
      : `$${(job.company_funding / 1_000_000).toFixed(0)}M`
    : "";

  const companyRows: [string, string][] = [
    ["Headquarters", job.company_hq      || "—"],
    ["Industry",     job.company_industry || "—"],
    ["Size",         job.company_size     || "—"],
    ["Funding",      funding              || "—"],
    ["ATS Platform", job.source],
    ["Career Page",  careerDomain],
  ];

  return (
    <div style={{ padding: "10px 0 20px", display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Company hero */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {logoSrc
          ? <img src={logoSrc} alt={job.company} style={{ width: 56, height: 56, borderRadius: 10, objectFit: "contain", background: "var(--bg-2)", padding: 4 }} />
          : <CompanyLogo url={job.url} company={job.company} size={56} />
        }
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: "var(--tx-1)" }}>{job.company}</span>
          {job.company_industry && <span style={{ fontSize: 12, color: "var(--tx-3)" }}>{job.company_industry}</span>}
        </div>
      </div>

      {/* Company details */}
      <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "10px 16px" }}>
        {companyRows.map(([k, v]) => (
          <>
            <span key={k+"-k"} style={{ fontSize: 13, color: "var(--tx-3)", fontWeight: 500 }}>{k}</span>
            {k === "Career Page"
              ? <a key={k+"-v"} href={job.url} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: "var(--accent)", textDecoration: "none" }}>{v}</a>
              : <span key={k+"-v"} style={{ fontSize: 13, color: "var(--tx-1)" }}>{v}</span>
            }
          </>
        ))}
      </div>

      {/* Benefits */}
      {job.benefits && job.benefits.length > 0 && (
        <div>
          <span style={{ fontSize: 13, color: "var(--tx-3)", fontWeight: 500, display: "block", marginBottom: 8 }}>Benefits</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {job.benefits.map((b, i) => (
              <span key={i} style={{ fontSize: 12, padding: "3px 8px", borderRadius: 6, background: "var(--bg-2)", color: "var(--tx-2)" }}>{b}</span>
            ))}
          </div>
        </div>
      )}
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

  const actionsRow = (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <button className="btn btn-ghost" onClick={handleFetchJd} disabled={fetching} style={{ height: 28, fontSize: 11 }}>
        {fetching ? <Spinner size={11} /> : <Ic d={I.refresh} size={12} />} Refresh JD
      </button>
      <button className="btn btn-ghost" onClick={() => setPasteMode(true)} style={{ height: 28, fontSize: 11 }}>
        <Ic d={I.clip} size={12} /> Paste JD
      </button>
      <button className="btn btn-ghost" onClick={() => { navigator.clipboard.writeText(desc); onToast("JD copied!", "success"); }} style={{ height: 28, fontSize: 11 }}>
        <Ic d={I.copy} size={12} /> Copy JD
      </button>
    </div>
  );

  // HTML description — render directly with scoped styles
  if (isHtml) {
    return (
      <div style={{ maxWidth: 720 }}>
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
    <div style={{ maxWidth: 720 }}>
      {actionsRow}
      <div className="jd-body">{rendered}</div>
    </div>
  );
}

// ── Qualify tab ────────────────────────────────────────────────────────────────
function QualifyTab({ job, running, onRun }: { job: Job; running: boolean; onRun: () => void }) {
  const qr = job.qualify_result;
  if (!qr) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 20px", gap: 18, textAlign: "center" }}>
        <div style={{ width: 64, height: 64, borderRadius: 999, background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border-subtle)" }}>
          <Ic d={I.target} size={28} color="var(--text-muted)" />
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>No qualification yet</div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>Run qualification to see your match score</div>
        </div>
        <button className="btn btn-accent" onClick={onRun} disabled={running} style={{ height: 40, padding: "0 20px", fontSize: 13.5, width: 280, justifyContent: "center" }}>
          {running ? <><Spinner size={14} color="#fff" /> Analyzing with AI…</> : <><Ic d={I.sparkles} size={15} /> Run Qualification Analysis</>}
        </button>
      </div>
    );
  }
  // Handle both array-of-tuples format and object format
  const criteriaList: Array<{ state: string; name: string; detail: string; weight?: string }> = [];
  if (Array.isArray(qr.criteria)) {
    qr.criteria.forEach((c: any) => {
      if (Array.isArray(c)) criteriaList.push({ state: c[0], name: c[1], detail: c[2], weight: c[3] });
      else criteriaList.push({ state: c.pass ? "pass" : "fail", name: c.name || c.key, detail: c.note, weight: c.weight });
    });
  } else if (qr.criteria && typeof qr.criteria === "object") {
    Object.entries(qr.criteria).forEach(([key, val]: [string, any]) => {
      criteriaList.push({ state: val.pass ? "pass" : "fail", name: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()), detail: val.note });
    });
  }

  return (
    <div>
      <div className="qual-hero">
        <div className="qual-score">
          <div className="qual-num">{qr.score}<small>/100</small></div>
          <div className={`qual-flag ${qr.qualified ? "yes" : "no"}`}>
            <Ic d={qr.qualified ? I.check : I.xCircle} size={12} />
            {qr.qualified ? "Qualified" : "Not qualified"}
          </div>
        </div>
        <div className="qual-meta">
          <div className="qual-verdict">{(qr as any).verdict || (qr.qualified ? "Good Match" : "Partial Match")}</div>
          <p className="qual-summary">{qr.summary}</p>
          <button onClick={onRun} disabled={running} className="act ghost" style={{ marginTop: 14, height: 30 }}>
            {running ? <><Spinner size={12} /> Re-analyzing…</> : <><Ic d={I.refresh} size={13} /> Re-run</>}
          </button>
        </div>
      </div>
      {criteriaList.length > 0 && (
        <>
          <div className="crit-list-label">Criteria breakdown</div>
          {criteriaList.map((c, i) => (
            <div key={i} className="crit">
              <div className={`crit-ico ${c.state === "pass" ? "pass" : c.state === "partial" ? "partial" : "fail"}`}>
                <Ic d={c.state === "pass" ? I.check : c.state === "partial" ? I.chevDown : I.xCircle} size={12} />
              </div>
              <div className="crit-main">
                <div className="crit-name">{c.name}</div>
                <div className="crit-detail">{c.detail}</div>
              </div>
              {c.weight && <div className="crit-weight">{c.weight}</div>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Resume tab ─────────────────────────────────────────────────────────────────
function ResumeTab({ job, tailoring, onTailor, onToast }: {
  job: Job; tailoring: boolean; onTailor: () => void; onToast: (m: string, t?: "success" | "error") => void;
}) {
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
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "80px 20px", gap: 14 }}>
        <Spinner size={28} color="var(--accent)" /><div style={{ fontSize: 13.5, color: "var(--text-secondary)" }}>Tailoring resume with AI…</div>
      </div>
    );
  }
  const before = job.ats_score_before ?? 45;
  const after  = job.ats_score_after ?? before;
  return (
    <div style={{ display: "flex", gap: 18, maxWidth: 980 }}>
      <div style={{ flex: 1.5, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 8 }}>Tailored Resume</div>
        <pre className="mono" style={{ flex: 1, background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 12, padding: 18, fontSize: 11.5, lineHeight: 1.7, color: "var(--text-secondary)", overflow: "auto", whiteSpace: "pre-wrap", maxHeight: 500 }}>{job.tailored_resume}</pre>
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button className="btn btn-ghost" onClick={() => downloadFile(api.pdfUrl(job.id), "resume.pdf").catch(e => onToast(e.message, "error"))}><Ic d={I.download} size={14} /> PDF</button>
          <button className="btn btn-ghost" onClick={() => downloadFile(api.docxUrl(job.id), "resume.docx").catch(e => onToast(e.message, "error"))}><Ic d={I.download} size={14} /> DOCX</button>
          <button className="btn btn-ghost" onClick={() => { navigator.clipboard.writeText(job.tailored_resume || ""); onToast("Copied!", "success"); }}><Ic d={I.copy} size={14} /> Copy</button>
          <button className="btn btn-subtle" onClick={() => downloadFile(api.savePackageUrl(job.id), "package.zip").catch(e => onToast(e.message, "error"))}>
            <Ic d={I.folder} size={14} /> Save Package
          </button>
        </div>

        {/* ATS keywords */}
        {(job.ats_keywords_matched?.length > 0 || job.ats_keywords_missing?.length > 0) && (
          <div style={{ marginTop: 14, display: "flex", gap: 12 }}>
            {job.ats_keywords_matched?.length > 0 && (
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#4ade80", marginBottom: 6 }}>✓ Matched Keywords</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {job.ats_keywords_matched.map((k: string) => (
                    <span key={k} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 999, background: "rgba(34,197,94,0.12)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.2)" }}>{k}</span>
                  ))}
                </div>
              </div>
            )}
            {job.ats_keywords_missing?.length > 0 && (
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#f87171", marginBottom: 6 }}>✗ Missing Keywords</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {job.ats_keywords_missing.map((k: string) => (
                    <span key={k} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 999, background: "rgba(239,68,68,0.12)", color: "#f87171", border: "1px solid rgba(239,68,68,0.2)" }}>{k}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <div style={{ width: 220, flexShrink: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 8 }}>ATS Score</div>
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 12, padding: 16 }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}><span>Before</span><span className="mono">{before}%</span></div>
            <ATSBar score={before} height={6} color="#64748b" />
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 6 }}><span style={{ color: "#4ade80", fontWeight: 600 }}>After</span><span className="mono" style={{ color: "#4ade80" }}>{after}%</span></div>
            <ATSBar score={after} height={6} color="#22c55e" />
          </div>
          <div style={{ marginTop: 16, textAlign: "center", padding: "10px 0", borderTop: "1px solid var(--border-subtle)" }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: "#4ade80" }}>+{after - before}</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 4 }}>pts</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Fit tab ────────────────────────────────────────────────────────────────────
function FitTab({ job, running, onRun }: { job: Job; running: boolean; onRun: () => void }) {
  const [openTip, setOpenTip] = useState(-1);
  const fitAnalysis = job.fit_analysis;
  const tips = job.interview_tips || [];

  if (!fitAnalysis && !running) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "60px 20px", gap: 18, textAlign: "center" }}>
        <div style={{ width: 64, height: 64, borderRadius: 999, background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border-subtle)" }}>
          <Ic d={I.zap} size={26} color="var(--text-muted)" />
        </div>
        <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>Run analysis to see your fit and interview prep tips</div>
        <button className="btn btn-accent" onClick={onRun} style={{ height: 40, padding: "0 20px", width: 240, justifyContent: "center" }}>
          {running ? <><Spinner size={14} color="#fff" /> Analyzing…</> : <><Ic d={I.zap} size={15} /> Analyze Fit</>}
        </button>
      </div>
    );
  }
  if (running) return <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "80px 0", gap: 12, color: "var(--text-muted)" }}><Spinner size={24} color="var(--accent)" /> Analyzing…</div>;

  return (
    <div style={{ maxWidth: 760 }}>
      {fitAnalysis && (
        <>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            <Ic d={I.checkCircle} size={16} color="#4ade80" /> Why You're a Strong Fit
          </div>
          <div style={{ background: "rgba(34,197,94,0.05)", borderLeft: "3px solid #22c55e", borderRadius: "0 10px 10px 0", padding: "14px 16px", marginBottom: 28 }}>
            <p style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.7 }}>{fitAnalysis}</p>
          </div>
        </>
      )}
      {tips.length > 0 && (
        <>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <Ic d={I.zap} size={16} color="#fbbf24" /> Interview Prep Tips
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {tips.map((tip: string, i: number) => {
              const isOpen = openTip === i;
              return (
                <div key={i} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 10, overflow: "hidden" }}>
                  <button onClick={() => setOpenTip(isOpen ? -1 : i)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 14, padding: "12px 14px", textAlign: "left" }}>
                    <span className="mono" style={{ fontSize: 18, fontWeight: 600, color: "var(--text-disabled)", width: 26 }}>{String(i + 1).padStart(2, "0")}</span>
                    <span style={{ flex: 1, fontSize: 13.5, fontWeight: 500, color: "var(--text-primary)" }}>{tip}</span>
                    <Ic d={I.chevDown} size={16} color="var(--text-muted)" style={{ transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 200ms ease" }} />
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}
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
      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
        <button className="act ai" onClick={() => { navigator.clipboard.writeText(job.cover_letter || ""); onToast("Cover letter copied", "success"); }}>
          <Ic d={I.copy} size={14} /> Copy letter
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
export function JobDetail({ job, tab, setTab, onUpdate, onToast, busy, runAction }: {
  job: Job | null; tab: string; setTab: (t: string) => void;
  onUpdate: (patch: Partial<Job>) => void;
  onToast: (m: string, t?: "success" | "error") => void;
  busy: string | null; runAction: (a: string) => void;
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
    resume: !!(job.tailored_resume || job.fit_analysis),
    cover: !!job.cover_letter,
    qualify: !!job.qualify_result,
    info: !!(job.notes || job.deadline || job.interview_date),
  };

  const handleStatusChange = async (s: string) => {
    try { await api.setStatus(job.id, s as JobStatus); onUpdate({ status: s as JobStatus }); onToast("Marked as " + s, "success"); }
    catch (e: any) { onToast(e.message, "error"); }
  };

  const scoreNum = (job.qualify_result as any)?.score ?? null;
  const circumference = 2 * Math.PI * 26;
  const offset = scoreNum != null ? circumference * (1 - scoreNum / 100) : circumference;

  return (
    <div className="detail-pane">
      <div className="detail-scroll">
        {/* Header */}
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
                <span className="badge-src">
                  <AtsLogo source={job.source} size={13} />
                  {job.source}
                </span>
                {(job.posted_at || job.scraped_at) && (
                  <span className="meta-i"><Ic d={I.clock} size={13} />{relTimeDetail(job.posted_at || job.scraped_at!)}</span>
                )}
              </div>
            </div>

            {/* Score ring */}
            <div className="dh-score">
              <ScoreRingDetail value={scoreNum} />
              <span className="ring-label">AI Match</span>
            </div>
          </div>

          {/* Actions */}
          <div className="actions">
            <a href={job.url} target="_blank" rel="noreferrer" className="act primary" style={{ textDecoration: "none" }}>
              <Ic d={I.link} size={14} /> Apply
            </a>
            <button onClick={() => runAction("resume")} disabled={!!busy} className="act ai">
              {busy === "resume" ? <><Spinner size={13} /> Tailoring…</> : <><Ic d={I.sparkles} size={14} /> Tailor Resume</>}
            </button>
            <button onClick={() => runAction("qualify")} disabled={!!busy} className="act ai">
              {busy === "qualify" ? <><Spinner size={13} /> Analyzing…</> : <><Ic d={I.target} size={14} /> Qualify</>}
            </button>
            <button className="act" onClick={() => handleStatusChange("applied")}>
              <Ic d={I.checkCircle} size={14} /> Mark Applied
            </button>
            <StatusDropdown status={job.status} onChange={handleStatusChange} />
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {TABS.map(t => {
            const active = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)} className={`tab${active ? " on" : ""}`}>
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <div className="tab-body">
          {tab === "description" && <DescriptionTab job={job} onUpdate={onUpdate} onToast={onToast} />}
          {tab === "info"     && <InfoTab job={job} onUpdate={onUpdate} onToast={onToast} />}
          {tab === "qualify"  && <QualifyTab job={job} running={busy === "qualify"} onRun={() => runAction("qualify")} />}
          {tab === "resume"   && (
            <div style={{ display: "flex", flexDirection: "column" }}>
              <ResumeTab job={job} tailoring={busy === "resume"} onTailor={() => runAction("resume")} onToast={onToast} />
              <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 20, marginTop: 24 }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 12 }}>Fit & Tips</div>
                <FitTab job={job} running={busy === "fit"} onRun={() => runAction("fit")} />
              </div>
            </div>
          )}
          {tab === "cover"    && <CoverTab job={job} generating={busy === "cover"} onGenerate={() => runAction("cover")} onChange={v => onUpdate({ cover_letter: v })} onToast={onToast} />}
        </div>
      </div>
    </div>
  );
}
