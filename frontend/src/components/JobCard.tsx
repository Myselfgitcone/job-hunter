import { useState } from "react";
import { MapPin, Wifi, Clock, Bell, ShieldAlert } from "lucide-react";
import type { Job, JobStatus, QualifyResult } from "../types";
import { ATSBar, CompanyLogo, srcColor } from "./primitives";

interface Props {
  job: Job;
  selected: boolean;
  onClick: () => void;
  index?: number;
  isFresh?: boolean;
  onQualifyUpdated?: (id: string, result: QualifyResult) => void;
}

const STATUS_PILL: Record<string, { bg: string; fg: string; label: string }> = {
  new:       { bg: "rgba(96,165,250,0.14)", fg: "#60a5fa", label: "New" },
  applied:   { bg: "rgba(34,197,94,0.14)",  fg: "#4ade80", label: "Applied" },
  interview: { bg: "rgba(167,139,250,0.18)", fg: "#c4b5fd", label: "Interview" },
  skipped:   { bg: "rgba(255,255,255,0.06)", fg: "#6b7280", label: "Skipped" },
};

function timeAgo(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}



export function JobCard({ job, selected, onClick, index = 0, isFresh = false }: Props) {
  const sp = STATUS_PILL[job.status] || STATUS_PILL.new;
  const qr = job.qualify_result;
  const posted = timeAgo(job.posted_at || job.scraped_at);

  return (
    <div
      onClick={onClick}
      className={`job-card${isFresh ? " fresh" : ""}`}
      style={{
        position: "relative",
        padding: "13px 16px 14px",
        cursor: "pointer",
        background: selected ? "var(--bg-selected)" : "transparent",
        boxShadow: selected ? "var(--selected-glow)" : "none",
        borderRadius: selected ? 10 : 0,
        margin: selected ? "0 6px" : 0,
        transition: "background 120ms ease",
        animation: `cardIn 260ms ease both`,
        animationDelay: `${Math.min(index, 12) * 30}ms`,
      }}
    >
      {selected && (
        <span style={{ position: "absolute", left: 0, top: 12, bottom: 12, width: 2, borderRadius: 999, background: "var(--accent)" }} />
      )}

      <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>

          {/* Logo + company row */}
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 7 }}>
            <CompanyLogo url={job.url} company={job.company} size={18} />
            <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.company}</span>
            <span style={{ fontSize: 10, fontWeight: 600, color: srcColor(job.source), flexShrink: 0 }}>{job.source}</span>
          </div>

          {/* Title + status */}
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {job.title}
            </div>
            <span className="pill" style={{ background: sp.bg, color: sp.fg, flexShrink: 0 }}>
              {sp.label}
            </span>
          </div>

          {/* Priority */}
          {job.priority === 2 && (
            <div style={{ marginTop: 5 }}>
              <span className="pill" style={{ background: "rgba(239,68,68,0.16)", color: "#f87171" }}>URGENT</span>
            </div>
          )}
          {job.priority === 1 && (
            <div style={{ marginTop: 5 }}>
              <span className="pill" style={{ background: "rgba(245,158,11,0.16)", color: "#fbbf24" }}>HIGH</span>
            </div>
          )}



          {/* Location + remote + time */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
            {job.location && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11, color: "var(--text-muted)" }}>
                <MapPin size={10} /> {job.location}
              </span>
            )}
            {job.remote && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "#2dd4bf", fontWeight: 500 }}>
                <Wifi size={10} /> Remote
              </span>
            )}
            {posted && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>
                <Clock size={9} /> {posted}
              </span>
            )}
          </div>

          {/* Salary */}
          {job.salary && (
            <div style={{ fontSize: 11, color: "#4ade80", fontWeight: 600, marginTop: 6 }}>{job.salary}</div>
          )}

          {/* Applied follow-up */}
          {job.status === "applied" && job.applied_at && (() => {
            const daysAgo = Math.floor((Date.now() - new Date(job.applied_at).getTime()) / 86400000);
            const needsFollowUp = daysAgo >= 7;
            return (
              <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6, fontSize: 10, color: needsFollowUp ? "#fb923c" : "#60a5fa" }}>
                {needsFollowUp ? <Bell size={9} /> : <Clock size={9} />}
                {needsFollowUp ? `Follow up — applied ${daysAgo}d ago` : `Applied ${daysAgo === 0 ? "today" : `${daysAgo}d ago`}`}
              </div>
            );
          })()}

          {/* ATS bar */}
          {job.ats_score_after !== null && job.ats_score_after !== undefined && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
              <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", width: 24 }}>ATS</span>
              <ATSBar score={job.ats_score_after} height={3} showPct />
            </div>
          )}

          {/* Qualify badge */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 9, flexWrap: "wrap" }}>
            {qr ? (
              qr.qualified ? (
                <span className="pill" style={{ background: "rgba(34,197,94,0.14)", color: "#4ade80" }}>
                  ✓ Qualified {qr.score}%
                </span>
              ) : (
                <span className="pill" style={{ background: "rgba(239,68,68,0.14)", color: "#f87171" }}>
                  ✕ Not Qualified
                </span>
              )
            ) : (
              <span className="pill" style={{ background: "rgba(255,255,255,0.04)", color: "var(--text-muted)" }}>
                Not analyzed
              </span>
            )}
            {!!(job as any).visaFlag && (
              <span className="pill" style={{ background: "rgba(239,68,68,0.12)", color: "#f87171", border: "1px solid rgba(239,68,68,0.25)" }}>
                <ShieldAlert size={9} /> Citizenship req
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
