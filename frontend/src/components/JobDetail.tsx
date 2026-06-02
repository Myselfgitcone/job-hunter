import { useState, useEffect, useRef } from "react";
import type { Job, JobStatus, QualifyResult } from "../types";
import { api } from "../api";
import { GaugeRing, ATSBar, Spinner, CompanyLogo } from "./primitives";

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
  { id: "description", label: "Description" },
  { id: "qualify",     label: "Qualify" },
  { id: "resume",      label: "Tailored Resume" },
  { id: "fit",         label: "Fit & Tips" },
  { id: "cover",       label: "Cover Letter" },
];

const STATUS_COLORS: Record<string, string> = {
  new: "var(--st-new)", applied: "var(--st-applied)", interview: "var(--st-interview)", skipped: "#5b6377",
};

function srcColorFn(source: string): string {
  const m: Record<string, string> = {
    Greenhouse: "#4ade80", Lever: "#34d399", Ashby: "#22d3ee",
    Workday: "#a78bfa", BambooHR: "#fb923c", Recruitee: "#f472b6",
    HiringCafe: "#facc15", Google: "#60a5fa", Apple: "#94a3b8",
    Meta: "#818cf8", Netflix: "#ef4444",
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
      <button onClick={() => setOpen(!open)} className="btn btn-subtle" style={{ height: 28, fontSize: 12 }}>
        <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[status] || "var(--text-muted)" }} />
        {labels[status] || status} <Ic d={I.chevDown} size={13} />
      </button>
      {open && (
        <div style={{ position: "absolute", top: 34, left: 0, zIndex: 20, background: "var(--bg-elevated)", border: "1px solid var(--border-default)", borderRadius: 10, padding: 4, boxShadow: "var(--card-shadow)", minWidth: 140 }}>
          {Object.entries(labels).map(([s, l]) => (
            <button key={s} onClick={() => { onChange(s); setOpen(false); }}
              style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "7px 10px", borderRadius: 7, fontSize: 12.5, color: "var(--text-secondary)", textAlign: "left" }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: STATUS_COLORS[s] }} /> {l}
            </button>
          ))}
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
      if (r.description) { onUpdate({ description: r.description }); onToast("Description fetched", "success"); }
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
  const criteriaMap = Object.entries(qr.criteria || {}).map(([key, val]) => ({
    name: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
    pass: val.pass, note: val.note,
  }));
  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", marginBottom: 22 }}>
        <GaugeRing score={qr.score} pass={qr.qualified} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 6 }}>Summary</div>
          <p style={{ fontSize: 14, fontStyle: "italic", color: "var(--text-secondary)", lineHeight: 1.6 }}>{qr.summary}</p>
          <button onClick={onRun} disabled={running} className="btn btn-ghost" style={{ marginTop: 14, height: 30 }}>
            {running ? <><Spinner size={12} /> Re-analyzing…</> : <><Ic d={I.refresh} size={13} /> Re-run</>}
          </button>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {criteriaMap.map((c, i) => (
          <div key={i} style={{ padding: "12px 14px", borderRadius: 10, background: c.pass ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)", border: `1px solid ${c.pass ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <Ic d={c.pass ? I.checkCircle : I.xCircle} size={16} color={c.pass ? "#4ade80" : "#f87171"} />
              <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" }}>{c.name}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, paddingLeft: 24 }}>{c.note}</div>
          </div>
        ))}
      </div>
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
          <a href={api.pdfUrl(job.id)} target="_blank" rel="noreferrer" className="btn btn-ghost"><Ic d={I.download} size={14} /> PDF</a>
          <a href={api.docxUrl(job.id)} target="_blank" rel="noreferrer" className="btn btn-ghost"><Ic d={I.download} size={14} /> DOCX</a>
          <button className="btn btn-ghost" onClick={() => { navigator.clipboard.writeText(job.tailored_resume || ""); onToast("Copied!", "success"); }}><Ic d={I.copy} size={14} /> Copy</button>
          <a href={api.savePackageUrl(job.id)} download className="btn btn-subtle" style={{ textDecoration: "none" }}>
            <Ic d={I.folder} size={14} /> Save Package
          </a>
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
    <div style={{ maxWidth: 720, display: "flex", flexDirection: "column" }}>
      <textarea value={job.cover_letter || ""} onChange={e => onChange(e.target.value)}
        style={{ minHeight: 320, lineHeight: 1.7, fontSize: 13.5, padding: 18, borderRadius: 12 }} />
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="btn btn-ghost" onClick={() => { navigator.clipboard.writeText(job.cover_letter || ""); onToast("Copied!", "success"); }}><Ic d={I.copy} size={14} /> Copy</button>
        <button className="btn btn-ghost" onClick={onGenerate}><Ic d={I.refresh} size={14} /> Regenerate</button>
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
    <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>Deadline</span>
          <input type="date" defaultValue={job.deadline || ""} onChange={e => onUpdate({ deadline: e.target.value })} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>Interview Date</span>
          <input type="date" defaultValue={job.interview_date || ""} onChange={e => onUpdate({ interview_date: e.target.value })} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>Priority</span>
          <select defaultValue={job.priority ?? 0} onChange={e => onUpdate({ priority: Number(e.target.value) })}>
            <option value={0}>Normal</option>
            <option value={1}>High</option>
            <option value={2}>Urgent</option>
          </select>
        </label>
      </div>
      <div>
        <textarea value={notes} onChange={e => handleNotes(e.target.value)}
          placeholder="Add notes about this role — recruiter contacts, prep, questions to ask…"
          style={{ minHeight: 240, fontSize: 13.5, lineHeight: 1.6, padding: 16, borderRadius: 12 }} />
        <div style={{ textAlign: "right", fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>Auto-saves</div>
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
      <section style={{ flex: 1, background: "var(--bg-base)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14 }}>
        <Ic d={I.briefcase} size={52} color="var(--text-disabled)" style={{ opacity: 0.4 }} />
        <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Select a job to view details</div>
      </section>
    );
  }

  const tabHasContent: Record<string, boolean> = {
    resume: !!job.tailored_resume, cover: !!job.cover_letter,
    notes: !!job.notes, qualify: !!job.qualify_result, fit: !!job.fit_analysis,
  };

  const handleStatusChange = async (s: string) => {
    try { await api.setStatus(job.id, s as JobStatus); onUpdate({ status: s as JobStatus }); onToast("Marked as " + s, "success"); }
    catch (e: any) { onToast(e.message, "error"); }
  };

  return (
    <section style={{ flex: 1, minWidth: 0, background: "var(--bg-base)", display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ flexShrink: 0, padding: "16px 24px 0", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em", lineHeight: 1.3 }}>{job.title}</h1>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
              <CompanyLogo url={job.url} company={job.company} size={22} />
              <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 500 }}>{job.company}</span>
              {job.location && <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, color: "var(--text-muted)" }}><Ic d={I.map} size={12} />{job.location}</span>}
              {job.remote && <span className="pill" style={{ background: "rgba(45,212,191,0.12)", color: "#2dd4bf" }}><Ic d={I.waves} size={11} /> Remote</span>}
              {job.salary && <span style={{ fontSize: 12.5, fontWeight: 600, color: "#4ade80" }}>{job.salary}</span>}
              <span style={{ fontSize: 11, fontWeight: 600, color: srcColorFn(job.source) }}>{job.source}</span>
            </div>
          </div>
          <a href={job.url} target="_blank" rel="noreferrer" className="btn btn-accent" style={{ height: 36, flexShrink: 0, textDecoration: "none" }}>
            <Ic d={I.link} size={14} /> Apply Now
          </a>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{job.posted_at ? "Posted " + new Date(job.posted_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : ""}</span>
          <div style={{ flex: 1 }} />
          <button onClick={() => api.verifyJob(job.id).then(r => onToast(r.alive ? "Job is live ✓" : "Job may be closed", r.alive ? "success" : "error"))} className="btn btn-ghost" style={{ height: 28, fontSize: 12, border: "none" }}>
            <Ic d={I.eye} size={13} /> Verify Live
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 12, marginBottom: 12 }}>
          <span style={{ fontSize: 11.5, color: "var(--text-muted)", alignSelf: "center" }}>Mark as:</span>
          {[{ s: "applied", l: "Applied" }, { s: "interview", l: "Interview" }, { s: "skipped", l: "Skip" }].map(a => (
            <button key={a.s} onClick={() => handleStatusChange(a.s)} className="btn btn-ghost"
              style={{ height: 28, fontSize: 12, background: job.status === a.s ? "var(--bg-hover)" : "transparent" }}>
              {a.l}
            </button>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2 }}>
          {TABS.map(t => {
            const active = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                style={{ position: "relative", padding: "10px 12px 12px", fontSize: 13, fontWeight: 500, color: active ? "var(--text-primary)" : "var(--text-muted)", transition: "color 120ms ease", display: "flex", alignItems: "center", gap: 6 }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.color = "var(--text-secondary)"; }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.color = "var(--text-muted)"; }}>
                {t.label}
                {tabHasContent[t.id] && <span style={{ width: 5, height: 5, borderRadius: 999, background: active ? "var(--accent)" : "var(--text-muted)" }} />}
                {active && <span style={{ position: "absolute", left: 8, right: 8, bottom: 0, height: 2, borderRadius: 999, background: "var(--accent)" }} />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "22px 24px 32px" }}>
        {tab === "description" && <DescriptionTab job={job} onUpdate={onUpdate} onToast={onToast} />}
        {tab === "qualify"     && <QualifyTab job={job} running={busy === "qualify"} onRun={() => runAction("qualify")} />}
        {tab === "resume"      && <ResumeTab job={job} tailoring={busy === "resume"} onTailor={() => runAction("resume")} onToast={onToast} />}
        {tab === "fit"         && <FitTab job={job} running={busy === "fit"} onRun={() => runAction("fit")} />}
        {tab === "cover"       && <CoverTab job={job} generating={busy === "cover"} onGenerate={() => runAction("cover")} onChange={v => onUpdate({ cover_letter: v })} onToast={onToast} />}
      </div>
    </section>
  );
}
