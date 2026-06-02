import { useState } from "react";
import type { Job, JobStatus } from "../types";
import { srcColor } from "./primitives";

const COLS = [
  { id: "new",       label: "New",       color: "var(--st-new)" },
  { id: "applied",   label: "Applied",   color: "var(--st-applied)" },
  { id: "interview", label: "Interview", color: "var(--st-interview)" },
  { id: "skipped",   label: "Skipped",   color: "#5b6377" },
];

interface Props {
  jobs: Job[];
  onStatusChange: (id: string, status: string) => void;
  onSelect: (id: string) => void;
}

export function Kanban({ jobs, onStatusChange, onSelect }: Props) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);

  const onDragStart = (e: React.DragEvent, id: string) => { setDraggingId(id); e.dataTransfer.effectAllowed = "move"; };
  const onDragEnd = () => { setDraggingId(null); setOverCol(null); };
  const onDrop = (colId: string) => { if (draggingId) onStatusChange(draggingId, colId); setDraggingId(null); setOverCol(null); };

  return (
    <div style={{ flex: 1, display: "flex", gap: 14, padding: 18, overflowX: "auto", overflowY: "hidden", height: "100%" }}>
      {COLS.map(col => {
        const colJobs = jobs.filter(j => j.status === col.id);
        const isOver = overCol === col.id;
        const showDrop = isOver && draggingId && jobs.find(j => j.id === draggingId)?.status !== col.id;
        return (
          <div key={col.id}
            onDragOver={e => { e.preventDefault(); setOverCol(col.id); }}
            onDragLeave={e => { if (e.currentTarget === e.target) setOverCol(null); }}
            onDrop={() => onDrop(col.id)}
            style={{ width: 288, flexShrink: 0, display: "flex", flexDirection: "column", height: "100%" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 4px 12px" }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, background: col.color, boxShadow: (col.id === "interview" || col.id === "applied") ? "0 0 6px " + col.color : "none" }} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>{col.label}</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--bg-elevated)", borderRadius: 999, padding: "1px 7px" }}>{colJobs.length}</span>
            </div>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9, padding: 9, borderRadius: 12, overflowY: "auto", background: isOver ? "rgba(59,130,246,0.05)" : "var(--bg-surface)", border: isOver ? "1.5px dashed rgba(59,130,246,0.5)" : "1px solid var(--border-subtle)", transition: "all 120ms ease" }}>
              {colJobs.map(job => (
                <KanbanCard key={job.id} job={job} dragging={draggingId === job.id} onDragStart={onDragStart} onDragEnd={onDragEnd} onOpen={onSelect} />
              ))}
              {showDrop && <div style={{ border: "1.5px dashed rgba(59,130,246,0.5)", borderRadius: 10, padding: 14, textAlign: "center", fontSize: 12, color: "#60a5fa", fontWeight: 500 }}>Drop here</div>}
              {colJobs.length === 0 && !isOver && <div style={{ textAlign: "center", padding: "20px 0", fontSize: 11.5, color: "var(--text-disabled)" }}>No jobs</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function KanbanCard({ job, dragging, onDragStart, onDragEnd, onOpen }: { job: Job; dragging: boolean; onDragStart: (e: React.DragEvent, id: string) => void; onDragEnd: () => void; onOpen: (id: string) => void; }) {
  return (
    <div draggable onDragStart={e => onDragStart(e, job.id)} onDragEnd={onDragEnd}
      style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)", borderRadius: 10, padding: "12px 13px", cursor: "grab", position: "relative", opacity: dragging ? 0.4 : 1, boxShadow: "0 1px 3px rgba(0,0,0,0.3)", transition: "border-color 120ms ease" }}>
      <button onClick={() => onOpen(job.id)}
        style={{ position: "absolute", top: 9, right: 10, fontSize: 10, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 2, padding: "2px 6px", borderRadius: 4 }}>
        open
      </button>
      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35, paddingRight: 44, marginBottom: 5 }}>{job.title}</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>{job.company}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {job.location && <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{job.location}</span>}
        {job.remote && <span style={{ fontSize: 10, color: "#2dd4bf", fontWeight: 500 }}>Remote</span>}
      </div>
      <div style={{ marginTop: 9 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: srcColor(job.source) }}>{job.source}</span>
      </div>
    </div>
  );
}
