import { useRef, useState, useEffect, useCallback } from "react";
import type { Job, QualifyResult } from "../types";
import { JobCard } from "./JobCard";

const CARD_HEIGHT = 155; // px — approximate height of one JobCard
const OVERSCAN    = 5;   // extra cards to render above/below viewport

interface Props {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onQualifyUpdated?: (id: string, r: QualifyResult) => void;
  emptyState?: string;
}

export function JobList({ jobs, selectedId, onSelect, onQualifyUpdated, emptyState }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop]     = useState(0);
  const [viewHeight, setViewHeight]   = useState(600);

  // Track container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setViewHeight(el.clientHeight));
    ro.observe(el);
    setViewHeight(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  const onScroll = useCallback(() => {
    setScrollTop(containerRef.current?.scrollTop ?? 0);
  }, []);

  // When selectedId changes, scroll that card into view
  useEffect(() => {
    if (!selectedId) return;
    const idx = jobs.findIndex(j => j.id === selectedId);
    if (idx === -1) return;
    const el = containerRef.current;
    if (!el) return;
    const top = idx * CARD_HEIGHT;
    const bot = top + CARD_HEIGHT;
    if (top < el.scrollTop || bot > el.scrollTop + el.clientHeight) {
      el.scrollTo({ top: top - viewHeight / 2 + CARD_HEIGHT / 2, behavior: "smooth" });
    }
  }, [selectedId, jobs]);

  const totalHeight = jobs.length * CARD_HEIGHT;

  // Empty state
  if (jobs.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "70%", gap: 12, padding: 24, textAlign: "center" }}>
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="var(--text-disabled)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>No jobs match your filters</div>
        {emptyState && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{emptyState}</div>}
      </div>
    );
  }

  // Visible window
  const startIdx = Math.max(0, Math.floor(scrollTop / CARD_HEIGHT) - OVERSCAN);
  const endIdx   = Math.min(jobs.length - 1, Math.ceil((scrollTop + viewHeight) / CARD_HEIGHT) + OVERSCAN);

  const visibleJobs = jobs.slice(startIdx, endIdx + 1);
  const paddingTop  = startIdx * CARD_HEIGHT;
  const paddingBot  = Math.max(0, (jobs.length - endIdx - 1) * CARD_HEIGHT);

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      style={{ flex: 1, overflowY: "auto", paddingBottom: 16, position: "relative" }}
    >
      {/* Spacer so scrollbar height is correct */}
      <div style={{ height: totalHeight, position: "relative" }}>
        <div style={{ position: "absolute", top: paddingTop, left: 0, right: 0 }}>
          {visibleJobs.map((job, relIdx) => {
            const i = startIdx + relIdx;
            return (
              <div key={job.id}>
                <JobCard
                  job={job}
                  index={relIdx}   // small index → snappy animation
                  selected={selectedId === job.id}
                  isFresh={false}
                  onClick={() => onSelect(job.id)}
                  onQualifyUpdated={onQualifyUpdated ? (id, r) => onQualifyUpdated(id, r) : undefined}
                />
                {i < jobs.length - 1 &&
                  selectedId !== job.id &&
                  selectedId !== jobs[i + 1]?.id && (
                    <div style={{ height: 1, background: "var(--border-subtle)", margin: "0 16px" }} />
                  )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
