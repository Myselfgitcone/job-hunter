import type { Job, QualifyResult } from "../types";
import { JobCard } from "./JobCard";
import { useState, useEffect, useRef } from "react";

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
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Reset pagination when job list changes (e.g. filter applied)
  useEffect(() => { setVisible(PAGE_SIZE); }, [jobs.length]);

  // Infinite scroll — watch the sentinel div at the bottom
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisible(v => Math.min(v + PAGE_SIZE, jobs.length));
        }
      },
      { rootMargin: "200px" } // start loading 200px before hitting the bottom
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [jobs.length]);

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

      {/* Sentinel — invisible div that triggers loading more when scrolled into view */}
      <div ref={sentinelRef} style={{ height: 1 }} />

      {/* Subtle loading indicator */}
      {hasMore && (
        <div style={{
          padding: "12px",
          textAlign: "center",
          fontSize: 11,
          color: "var(--tx-3)",
          letterSpacing: "0.04em",
        }}>
          Showing {visible} of {jobs.length} jobs…
        </div>
      )}
    </>
  );
}
