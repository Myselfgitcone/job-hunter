import type { Job, QualifyResult } from "../types";
import { CompanyLogo, srcColor } from "./primitives";

interface Props {
  job: Job;
  selected: boolean;
  onClick: () => void;
  index?: number;
  isFresh?: boolean;
  onQualifyUpdated?: (id: string, result: QualifyResult) => void;
}

const STATUS_COLOR: Record<string, string> = {
  new:       "var(--st-new)",
  applied:   "var(--st-applied)",
  interview: "var(--st-interview)",
  skipped:   "var(--st-skipped)",
};

function scoreClass(score: number | null | undefined): string {
  if (score == null) return "low";
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "low";
}

function logoColor(company: string): string {
  const colors = [
    "linear-gradient(135deg,#7c3aed,#6d28d9)",
    "linear-gradient(135deg,#0891b2,#0e7490)",
    "linear-gradient(135deg,#059669,#047857)",
    "linear-gradient(135deg,#dc2626,#b91c1c)",
    "linear-gradient(135deg,#d97706,#b45309)",
    "linear-gradient(135deg,#7c3aed,#06b6d4)",
    "linear-gradient(135deg,#db2777,#be185d)",
    "linear-gradient(135deg,#2563eb,#1d4ed8)",
  ];
  let hash = 0;
  for (let i = 0; i < company.length; i++) hash = (hash * 31 + company.charCodeAt(i)) % colors.length;
  return colors[hash];
}

function timeAgo(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function JobCard({ job, selected, onClick, index = 0, isFresh = false }: Props) {
  const qr    = job.qualify_result;
  const score = qr?.score ?? null;
  const posted = timeAgo(job.posted_at || job.scraped_at);
  const stColor = STATUS_COLOR[job.status] || STATUS_COLOR.new;
  const isRemote = job.remote || (job.location || "").toLowerCase().includes("remote");

  return (
    <div
      onClick={onClick}
      className={`jobcard${selected ? " sel" : ""}${isFresh ? " fresh" : ""}`}
      style={{
        "--st-color": stColor,
        animationDelay: `${Math.min(index, 12) * 18}ms`,
      } as React.CSSProperties}
    >
      {/* Company logo */}
      <div className="logo" style={{ background: logoColor(job.company) }}>
        <CompanyLogo url={job.url} company={job.company} size={24} />
      </div>

      {/* Main info */}
      <div className="jc-main">
        <div className="jc-title-row">
          <span className="jc-title">{job.title}</span>
        </div>
        <div className="jc-sub">
          <span className="co">{job.company}</span>
          {job.location && (
            <>
              <span className="sep" />
              <span className="loc">{job.location}</span>
            </>
          )}
          {isRemote && (
            <>
              <span className="sep" />
              <span className="badge-remote">Remote</span>
            </>
          )}
        </div>
        {/* Source badge */}
        <div style={{ marginTop: 3 }}>
          <span className="badge-src">
            <span className="sw" style={{ background: srcColor(job.source) }} />
            {job.source}
          </span>
        </div>
      </div>

      {/* Right column */}
      <div className="jc-right">
        {posted && <span className="jc-time">{posted}</span>}
        {score != null && (
          <span className={`score-badge ${scoreClass(score)}`}>
            {score}%
          </span>
        )}
        {isFresh && <span className="badge-new">New</span>}
      </div>
    </div>
  );
}
