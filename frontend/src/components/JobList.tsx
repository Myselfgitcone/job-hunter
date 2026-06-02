import type { Job, QualifyResult } from "../types";
import { JobCard } from "./JobCard";

interface Props {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onQualifyUpdated?: (id: string, r: QualifyResult) => void;
}

export function JobList({ jobs, selectedId, onSelect, onQualifyUpdated }: Props) {
  return (
    <div className="divide-y divide-slate-800/50">
      {jobs.map(job => (
        <JobCard
          key={job.id}
          job={job}
          selected={job.id === selectedId}
          onClick={() => onSelect(job.id)}
          onQualifyUpdated={onQualifyUpdated}
        />
      ))}
    </div>
  );
}
