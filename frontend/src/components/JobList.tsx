import type { Job, QualifyResult } from "../types";
import { JobCard } from "./JobCard";
import { useState, useEffect } from "react";

const PAGE_SIZE = 60;

interface Props {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onSkip?: (id: string) => void;
  onQualifyUpdated?: (id: string, r: QualifyResult) => void;
  emptyState?: string;
  mode?: "compact" | "cards";
}

export function JobList({ jobs, selectedId, onSelect, onSkip, onQualifyUpdated, emptyState, mode = "compact" }: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);

  // Reset pagination when jobs list changes (filter applied etc.)
  useEffect(() => { setVisible(PAGE_SIZE); }, [jobs.length]);

  if (jobs.length === 0) {
    return (
      <div className="empty" style={{ minHeight: 200 }}>
        <div className="empty-inner">
          <div className="empty-ico">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
            </svg>
          </div>
          <h3>No jobs found</h3>
          <p>{emptyState || "Try adjusting your filters"}</p>
        </div>
      </div>
    );
  }

  const shown = jobs.slice(0, visible);
  const hasMore = visible < jobs.length;

  return (
    <>
      {shown.map((job, i) => (
        <JobCard
          key={job.id}
          job={job}
          index={i}
          selected={selectedId === job.id}
          mode={mode}
          onClick={() => onSelect(job.id)}
          onSkip={onSkip}
        />
      ))}
      {hasMore && (
        <div style={{ padding: "16px 12px", textAlign: "center" }}>
          <button
            id="load-more-jobs"
            onClick={() => setVisible(v => v + PAGE_SIZE)}
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 8,
              color: "var(--tx-2)",
              fontSize: 12,
              fontWeight: 600,
              padding: "8px 20px",
              cursor: "pointer",
              width: "100%",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
          >
            ↓ Load more ({jobs.length - visible} remaining)
          </button>
        </div>
      )}
    </>
  );
}
