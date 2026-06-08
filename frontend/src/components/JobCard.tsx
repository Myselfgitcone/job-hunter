import React, { useEffect, useState } from "react";
import type { Job } from "../types";
import { CompanyLogo } from "./primitives";

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

function relTime(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso.replace(/(\.\d{3})\d+/, "$1")).getTime();
  if (isNaN(diff) || diff < 0) return "";
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
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
  mode?: "compact" | "cards";
  index?: number;
}

export function JobCard({ job, selected, onClick, onSkip, mode = "compact", index = 0 }: Props) {
  const qr      = job.qualify_result as any;
  const score   = qr?.score ?? null;
  const posted  = relTime(job.posted_at || job.scraped_at || "");
  const stColor = STATUS_COLOR[job.status] || "var(--st-new)";
  const srcVar  = SRC_VAR[job.source];
  const isNew   = job.status === "new" && !!job.posted_at && (Date.now() - new Date(job.posted_at).getTime()) < 24 * 3600000;
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
          <div className="jc-tags">
            <span className="badge-src">
              <span className="sw" style={{ background: srcVar ? `var(${srcVar})` : "var(--tx-3)" }} />
              {job.source}
            </span>
            <span className="sep" style={{ background: "var(--tx-faint)" }} />
            <span className="jc-time">{posted}</span>
          </div>
        )}
      </div>

      {/* Right: score badge + time */}
      <div className="jc-right">
        {score !== null ? (
          <span className={`score-badge ${scoreClass(score)}`}>{score}%</span>
        ) : null}
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
