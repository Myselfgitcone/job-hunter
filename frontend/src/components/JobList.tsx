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
  onLoadMore?: () => void;
  hasMore?: boolean;
  loadingMore?: boolean;
}

export function JobList({ jobs, selectedId, onSelect, onSkip, onQualifyUpdated, emptyState, mode = "compact", onLoadMore, hasMore, loadingMore }: Props) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Reset handled by parent now (server-side pagination)

  // Infinite scroll — watch the sentinel div at the bottom
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          onLoadMore?.();
        }
      },
      { rootMargin: "300px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

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
  const localHasMore = visible < jobs.length;

  return (
    <>
      {jobs.map((job, i) => (
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

      {/* Loading spinner when fetching next page */}
      {loadingMore && (
        <div style={{ padding: "14px", textAlign: "center", fontSize: 11, color: "var(--tx-3)" }}>
          Loading more jobs…
        </div>
      )}
      {!hasMore && jobs.length > 0 && (
        <div style={{ padding: "14px", textAlign: "center", fontSize: 11, color: "var(--tx-3)", letterSpacing: "0.04em" }}>
          ✓ All {jobs.length} jobs loaded
        </div>
      )}
    </>
  );
}
