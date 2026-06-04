import React from "react";
import type { Job, QualifyResult } from "../types";
import { CompanyLogo, srcColor, ATSBar, Icon } from "./primitives";

interface Props {
  job: Job;
  selected: boolean;
  onClick: () => void;
  index?: number;
  isFresh?: boolean;
  onQualifyUpdated?: (id: string, result: QualifyResult) => void;
}

const STATUS_PILL: Record<string, { bg: string; fg: string; label: string }> = {
  new:       { bg: "rgba(100,116,139,0.18)", fg: "#94a3b8", label: "New" },
  applied:   { bg: "rgba(59,130,246,0.18)",  fg: "#60a5fa", label: "Applied" },
  interview: { bg: "rgba(16,185,129,0.18)",  fg: "#34d399", label: "Interview" },
  skipped:   { bg: "rgba(255,255,255,0.05)", fg: "#5b6377", label: "Skipped" },
};

function timeAgo(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso.replace(/(\.\d{3})\d+/, "$1")).getTime();
  if (isNaN(diff)) return "";
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function JobCard({ job, selected, onClick, index = 0, isFresh = false }: Props) {
  const qr     = job.qualify_result;
  const posted = timeAgo(job.posted_at || job.scraped_at);
  const sc     = srcColor(job.source);
  const isRemote = job.remote || (job.location || "").toLowerCase().includes("remote");
  const sp     = STATUS_PILL[job.status] || STATUS_PILL.new;
  const atsScore = qr?.score ?? job.ats_score_after ?? null;

  return (
    <div
      onClick={onClick}
      className={isFresh ? "fresh" : ""}
      style={{
        position: "relative", padding: "13px 16px 14px", cursor: "pointer",
        background: selected ? "var(--bg-selected)" : "transparent",
        boxShadow: selected ? "var(--selected-glow)" : "none",
        borderRadius: selected ? 10 : 0,
        margin: selected ? "0 6px" : 0,
        transition: "background 120ms ease",
        animation: `cardIn 260ms ease both`,
        animationDelay: `${Math.min(index, 12) * 30}ms`,
      }}
    >
      {selected && <span style={{ position: "absolute", left: 0, top: 12, bottom: 12, width: 2, borderRadius: 999, background: "var(--accent)" }} />}

      <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
        {/* Company logo */}
        <div style={{ flexShrink: 0, marginTop: 1 }}>
          <CompanyLogo url={job.url} company={job.company} size={28} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Title + status pill */}
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {job.title}
            </div>
            <span className="pill" style={{ background: sp.bg, color: sp.fg, flexShrink: 0 }}>{sp.label}</span>
          </div>

          {/* Company + source */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6, gap: 8 }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {job.company}
            </span>
            <span style={{ fontSize: 10, fontWeight: 600, color: sc, flexShrink: 0 }}>{job.source}</span>
          </div>

          {/* Location + remote + time */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
            {job.location && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11, color: "var(--text-muted)" }}>
                <Icon name="mapPin" size={11} /> {job.location}
              </span>
            )}
            {isRemote && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "#2dd4bf", fontWeight: 500 }}>
                <Icon name="waves" size={11} /> Remote
              </span>
            )}
            {posted && (
              <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>
                <Icon name="clock" size={10} /> {posted}
              </span>
            )}
          </div>

          {/* ATS bar */}
          {atsScore != null && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
              <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", width: 26 }}>ATS</span>
              <ATSBar score={atsScore} height={3} showPct />
            </div>
          )}

          {/* Qualify badge */}
          {qr && (
            <div style={{ marginTop: 8 }}>
              {qr.qualified ? (
                <span className="pill" style={{ background: "rgba(34,197,94,0.14)", color: "#4ade80" }}>
                  <Icon name="check" size={10} /> Qualified {qr.score}%
                </span>
              ) : (
                <span className="pill" style={{ background: "rgba(239,68,68,0.14)", color: "#f87171" }}>
                  <Icon name="x" size={10} /> Not Qualified
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
