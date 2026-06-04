import type { Job, QualifyResult } from "../types";
import { JobCard } from "./JobCard";
import { useState } from "react";

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
    </>
  );
}
