import React, { useEffect, useState, useRef } from "react";
import type { Job } from "../types";
import { CompanyLogo, AtsLogo } from "./primitives";
import { api } from "../api";

const EXP_TRAYS = ["0-2","2-4","4-5","5-6","6-7","7-8","8-10","10-13","13-15","15+"];

const STATUS_LABEL: Record<string, { label: string; bg: string; color: string }> = {
  applied:   { label: "Applied",   bg: "rgba(99,102,241,0.12)",  color: "#6366f1" },
  interview: { label: "Interview", bg: "rgba(16,185,129,0.12)",  color: "#10b981" },
  skipped:   { label: "Skipped",   bg: "rgba(107,114,128,0.12)", color: "#6b7280" },
};

// Status → CSS var for left border
const STATUS_COLOR: Record<string, string> = {
  new:       "var(--st-new)",
  applied:   "var(--st-applied)",
  interview: "var(--st-interview)",
  skipped:   "var(--st-skipped)",
};

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
}

export function JobCard({ job, selected, onClick, onSkip, onUpdate, mode = "compact", index = 0 }: Props) {
  const [editingExp, setEditingExp] = useState(false);
  const expRef = useRef<HTMLSelectElement>(null);
  const qr      = job.qualify_result as any;
  const score   = qr?.score ?? null;
  const _postedRaw = fmtPosted(job.posted_at || job.scraped_at || "");
  const posted  = _postedRaw ? `Posted ${_postedRaw}` : "";
  const stColor = STATUS_COLOR[job.status] || "var(--st-new)";
  const srcVar  = SRC_VAR[job.source];
  const _newTs  = job.posted_at || job.scraped_at || "";
  const isNew   = job.status === "new" && !!_newTs && (Date.now() - new Date(_newTs).getTime()) < 24 * 3600000;
  const isRemote = job.remote || (job.location || "").toLowerCase().includes("remote");

  return (
    <div
      className={`jobcard${selected ? " sel" : ""}`}
      onClick={onClick}
      style={{
        "--st-color": stColor,
        animationDelay: `${Math.min(index, 12) * 20}ms`,
      } as React.CSSProperties}
    >
      {/* Company logo */}
      <div className="logo" style={{ flexShrink: 0 }}>
        <CompanyLogo url={job.url} company={job.company} size={34} />
      </div>

      {/* Main content */}
      <div className="jc-main">
        <div className="jc-title-row">
          <span className="jc-title">{job.title}</span>
          {isNew && <span className="badge-new">new</span>}
        </div>
        <div className="jc-sub">
          <span className="co">{job.company}</span>
          <span className="sep" />
          <span className="loc">{job.location || "Remote"}</span>
          {isRemote && mode === "cards" && <span className="badge-remote">Remote</span>}
        </div>
        {mode === "cards" && (
          <>
            <div className="jc-tags">
              {job.country === "USA" && job.visa_sponsorship === true && (
                <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 5, background: "rgba(22,163,74,0.12)", color: "#16a34a", fontWeight: 600 }}>Visa ✓</span>
              )}
              {job.country === "USA" && job.visa_sponsorship === false && (
                <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 5, background: "var(--bg-2)", color: "var(--tx-3)" }}>Visa not stated</span>
              )}
              {job.experience_level && !editingExp && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                  <span title={job.experience_level_inferred ? "AI-estimated — click ✏ to correct" : "From job description"} style={{
                    fontSize: 11, padding: "1px 6px", borderRadius: 5,
                    background: job.experience_level_inferred ? "rgba(124,58,237,0.07)" : "var(--bg-2)",
                    color: job.experience_level_inferred ? "var(--violet)" : "var(--tx-3)",
                    border: job.experience_level_inferred ? "1px dashed rgba(124,58,237,0.3)" : "none",
                  }}>{job.experience_level_inferred ? "~" : ""}{job.experience_level}yr</span>
                  <button title="Edit years of experience" onClick={e => { e.stopPropagation(); setEditingExp(true); setTimeout(() => expRef.current?.focus(), 50); }}
                    style={{ background: "none", border: "none", cursor: "pointer", padding: "0 1px", color: "var(--tx-3)", fontSize: 10, lineHeight: 1 }}>✏</button>
                </span>
              )}
              {editingExp && (
                <select ref={expRef} defaultValue={job.experience_level ?? ""}
                  onClick={e => e.stopPropagation()}
                  onBlur={() => setEditingExp(false)}
                  onChange={async e => {
                    const val = e.target.value;
                    setEditingExp(false);
                    try {
                      await api.setExpLevel(job.id, val);
                      onUpdate?.(job.id, { experience_level: val, experience_level_inferred: false } as any);
                    } catch {}
                  }}
                  style={{ fontSize: 11, padding: "1px 4px", borderRadius: 5, border: "1px solid var(--violet)", background: "var(--bg-2)", color: "var(--tx-2)" }}>
                  {EXP_TRAYS.map(t => <option key={t} value={t}>{t}yr</option>)}
                </select>
              )}
            </div>
            <div className="jc-tags" style={{ marginTop: 2 }}>
              {job.source !== "FantasticJobs" && (
                <span className="badge-src">
                  <AtsLogo source={job.source} size={11} />
                  {job.source}
                </span>
              )}
              <span className="jc-time">{posted}</span>
            </div>
          </>
        )}
      </div>

      {/* Right: score badge + status + resume ATS + time */}
      <div className="jc-right">
        {score !== null ? (
          <span className={`score-badge ${scoreClass(score)}`}>{score}%</span>
        ) : null}
        {STATUS_LABEL[job.status] && (
          <span style={{
            fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
            background: STATUS_LABEL[job.status].bg,
            color: STATUS_LABEL[job.status].color,
            marginTop: score !== null ? 3 : 0, display: "block", textAlign: "center",
          }}>{STATUS_LABEL[job.status].label}</span>
        )}
        {job.ats_score_after != null && (
          <span title={`ATS score after tailoring (before: ${job.ats_score_before ?? "?"}%)`} style={{
            fontSize: 10, fontWeight: 700, padding: "2px 5px", borderRadius: 4,
            background: job.ats_score_after >= 70 ? "rgba(34,197,94,0.12)" : job.ats_score_after >= 50 ? "rgba(234,179,8,0.12)" : "rgba(239,68,68,0.10)",
            color: job.ats_score_after >= 70 ? "#16a34a" : job.ats_score_after >= 50 ? "#b45309" : "#dc2626",
            border: `1px solid ${job.ats_score_after >= 70 ? "rgba(34,197,94,0.25)" : job.ats_score_after >= 50 ? "rgba(234,179,8,0.3)" : "rgba(239,68,68,0.2)"}`,
            marginTop: 3, display: "block", textAlign: "center",
          }}>📄 {job.ats_score_after}%</span>
        )}
        {mode === "compact" && <span className="jc-time">{posted}</span>}
      </div>

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
