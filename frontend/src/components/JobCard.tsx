import { MapPin, Wifi, Clock, Bell } from "lucide-react";
import type { Job, QualifyResult } from "../types";
import { ATSBar, CompanyLogo, srcColor } from "./primitives";

interface Props {
  job: Job;
  selected: boolean;
  onClick: () => void;
  index?: number;
  isFresh?: boolean;
  onQualifyUpdated?: (id: string, result: QualifyResult) => void;
}

const STATUS_CONFIG: Record<string, { bg: string; fg: string; dot: string; label: string }> = {
  new:       { bg: "rgba(138,180,248,0.12)", fg: "#8ab4f8", dot: "#8ab4f8", label: "New" },
  applied:   { bg: "rgba(52,211,153,0.12)",  fg: "#34d399", dot: "#34d399", label: "Applied" },
  interview: { bg: "rgba(183,148,246,0.14)", fg: "#b794f6", dot: "#b794f6", label: "Interview 🎉" },
  skipped:   { bg: "rgba(255,255,255,0.05)", fg: "#6b7280", dot: "#4b5563", label: "Skipped" },
};

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "transparent";
  if (score >= 75) return "#34d399";
  if (score >= 50) return "#fdd663";
  return "#f28b82";
}

function titleChips(title: string): string[] {
  const keywords = [
    "Python","SQL","Spark","Kafka","Airflow","dbt","AWS","GCP","Azure","Snowflake",
    "Databricks","Tableau","Power BI","ML","AI","ETL","Scala","Java","Go","React",
    "Node","Kubernetes","Docker","Terraform","LLM","NLP","Analytics","BI",
    "Finance","SAP","Workday","Salesforce","DataOps","MLOps","Platform",
  ];
  const t = title.toLowerCase();
  return keywords.filter(k => t.includes(k.toLowerCase())).slice(0, 3);
}

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
  const sp     = STATUS_CONFIG[job.status] || STATUS_CONFIG.new;
  const qr     = job.qualify_result;
  const score  = qr?.score ?? null;
  const posted = timeAgo(job.posted_at || job.scraped_at);
  const chips  = titleChips(job.title);
  const accent = scoreColor(score);
  const color  = srcColor(job.source);

  return (
    <div
      onClick={onClick}
      className={`job-card${isFresh ? " fresh" : ""}`}
      style={{
        position: "relative",
        margin: "6px 8px",
        padding: "12px 14px",
        cursor: "pointer",
        borderRadius: 12,
        background: selected ? "var(--bg-selected)" : "var(--bg-surface)",
        boxShadow: selected
          ? "var(--selected-glow), var(--shadow-2)"
          : "var(--card-shadow)",
        border: selected
          ? "1px solid var(--accent)"
          : `1px solid var(--border-subtle)`,
        borderLeft: selected
          ? `3px solid var(--accent)`
          : accent !== "transparent"
          ? `3px solid ${accent}`
          : "1px solid var(--border-subtle)",
        transition: "box-shadow 160ms ease, border-color 160ms ease, background 160ms ease",
        animation: "cardIn 240ms cubic-bezier(0.2,0,0,1) both",
        animationDelay: `${Math.min(index, 12) * 20}ms`,
      }}
    >
      {/* Row 1: Logo + Company + Source badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 9 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8, flexShrink: 0, overflow: "hidden",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-subtle)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
        }}>
          <CompanyLogo url={job.url} company={job.company} size={26} />
        </div>

        <span style={{
          fontSize: 12, fontWeight: 500, color: "var(--text-secondary)",
          flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {job.company}
        </span>

        <span style={{
          fontSize: 9, fontWeight: 700, color,
          background: `${color}15`, border: `1px solid ${color}28`,
          borderRadius: 6, padding: "2px 7px",
          flexShrink: 0, letterSpacing: "0.04em", textTransform: "uppercase",
        }}>{job.source}</span>
      </div>

      {/* Row 2: Title + Status */}
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start", marginBottom: 8 }}>
        <div style={{
          fontSize: 13.5, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.35,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          letterSpacing: "-0.01em",
        }}>
          {job.title}
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 4, flexShrink: 0,
          background: sp.bg, color: sp.fg,
          borderRadius: 6, padding: "3px 8px",
          fontSize: 10, fontWeight: 600,
        }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: sp.dot, display: "inline-block" }} />
          {sp.label}
        </div>
      </div>

      {/* Row 3: Tech chips */}
      {chips.length > 0 && (
        <div style={{ display: "flex", gap: 4, marginBottom: 8, flexWrap: "wrap" }}>
          {chips.map(chip => (
            <span key={chip} style={{
              fontSize: 9.5, fontWeight: 500, padding: "2px 7px", borderRadius: 4,
              background: "var(--bg-elevated)", color: "var(--text-muted)",
              border: "1px solid var(--border-subtle)", letterSpacing: "0.02em",
            }}>{chip}</span>
          ))}
        </div>
      )}

      {/* Row 4: Meta */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {job.location && (
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10.5, color: "var(--text-muted)" }}>
            <MapPin size={9} /> {job.location}
          </span>
        )}
        {job.remote && (
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "#34d399", fontWeight: 600 }}>
            <Wifi size={9} /> Remote
          </span>
        )}
        {job.salary && (
          <span style={{
            fontSize: 10, fontWeight: 700, color: "#34d399",
            background: "rgba(52,211,153,0.10)", border: "1px solid rgba(52,211,153,0.20)",
            borderRadius: 4, padding: "2px 7px",
          }}>{job.salary}</span>
        )}
        {posted && (
          <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>
            <Clock size={9} /> {posted}
          </span>
        )}
      </div>

      {/* Applied follow-up */}
      {job.status === "applied" && job.applied_at && (() => {
        const daysAgo = Math.floor((Date.now() - new Date(job.applied_at).getTime()) / 86400000);
        const needsFollowUp = daysAgo >= 7;
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 7, fontSize: 10, color: needsFollowUp ? "#fb923c" : "var(--accent)", fontWeight: 500 }}>
            {needsFollowUp ? <Bell size={9} /> : <Clock size={9} />}
            {needsFollowUp ? `Follow up — applied ${daysAgo}d ago` : `Applied ${daysAgo === 0 ? "today" : `${daysAgo}d ago`}`}
          </div>
        );
      })()}

      {/* ATS bar */}
      {job.ats_score_after != null && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 9 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", width: 24 }}>ATS</span>
          <ATSBar score={job.ats_score_after} height={3} showPct />
        </div>
      )}

      {/* Qualify badge */}
      {qr && (
        <div style={{ marginTop: 9 }}>
          {qr.qualified ? (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 10.5, fontWeight: 600, padding: "3px 10px", borderRadius: 6,
              background: "rgba(52,211,153,0.12)", color: "#34d399",
              border: "1px solid rgba(52,211,153,0.22)",
            }}>✓ Qualified · {qr.score}%</span>
          ) : (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontSize: 10.5, fontWeight: 600, padding: "3px 10px", borderRadius: 6,
              background: "rgba(242,139,130,0.10)", color: "#f28b82",
              border: "1px solid rgba(242,139,130,0.22)",
            }}>✕ Not Qualified</span>
          )}
        </div>
      )}
    </div>
  );
}
