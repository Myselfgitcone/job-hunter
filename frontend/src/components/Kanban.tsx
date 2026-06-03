import { useState } from "react";
import type { Job } from "../types";
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
    <div style={{
      display: "flex", gap: 14, padding: 18,
      overflowX: "auto", flex: 1, minHeight: 0,
    }}>
      {COLS.map(col => {
        const colJobs = jobs.filter(j => j.status === col.id);
        const isOver = overCol === col.id;
        const showDrop = isOver && draggingId && jobs.find(j => j.id === draggingId)?.status !== col.id;
        return (
          <div key={col.id}
            onDragOver={e => { e.preventDefault(); setOverCol(col.id); }}
            onDragLeave={e => { if (e.currentTarget === e.target) setOverCol(null); }}
            onDrop={() => onDrop(col.id)}
            style={{
              minWidth: 240, flex: 1,
              display: "flex", flexDirection: "column",
              background: isOver ? "rgba(124,58,237,0.05)" : "var(--bg-surface)",
              border: isOver ? "1.5px dashed rgba(124,58,237,0.45)" : "1px solid var(--line)",
              borderRadius: "var(--r-lg)",
              transition: "all 120ms ease",
            }}>

            {/* Column header */}
            <div style={{
              padding: "12px 14px",
              borderBottom: "1px solid var(--line)",
              display: "flex", alignItems: "center", gap: 8,
              flexShrink: 0,
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: 999,
                background: col.color, flexShrink: 0,
                boxShadow: (col.id === "interview" || col.id === "applied") ? `0 0 6px ${col.color}` : "none",
              }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--tx)" }}>{col.label}</span>
              <span style={{
                marginLeft: "auto",
                fontSize: 11, fontFamily: "var(--f-mono)", color: "var(--tx-3)",
                background: "var(--bg-elevated)", borderRadius: 999, padding: "1px 8px",
                border: "1px solid var(--line)",
              }}>{colJobs.length}</span>
            </div>

            {/* Cards area */}
            <div style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
              {colJobs.map(job => (
                <KanbanCard
                  key={job.id} job={job}
                  dragging={draggingId === job.id}
                  onDragStart={onDragStart} onDragEnd={onDragEnd} onOpen={onSelect}
                />
              ))}
              {showDrop && (
                <div style={{
                  margin: "6px 8px",
                  border: "1.5px dashed rgba(124,58,237,0.5)", borderRadius: "var(--r-sm)",
                  padding: 14, textAlign: "center", fontSize: 12,
                  color: "var(--violet)", fontWeight: 500,
                }}>Drop here</div>
              )}
              {colJobs.length === 0 && !isOver && (
                <div style={{
                  textAlign: "center", padding: "24px 0",
                  fontSize: 11.5, color: "var(--tx-faint)",
                }}>No jobs</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function KanbanCard({ job, dragging, onDragStart, onDragEnd, onOpen }: {
  job: Job; dragging: boolean;
  onDragStart: (e: React.DragEvent, id: string) => void;
  onDragEnd: () => void;
  onOpen: (id: string) => void;
}) {
  return (
    <div
      draggable onDragStart={e => onDragStart(e, job.id)} onDragEnd={onDragEnd}
      style={{
        margin: "6px 8px", padding: "11px 12px",
        background: "var(--bg-elevated)",
        border: "1px solid var(--line)",
        borderRadius: "var(--r-sm)",
        cursor: "grab", position: "relative",
        opacity: dragging ? 0.4 : 1,
        boxShadow: "0 1px 3px rgba(0,0,0,.3)",
        transition: "border-color 120ms ease, box-shadow 120ms ease",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--line-hi)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--sh-1)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--line)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 1px 3px rgba(0,0,0,.3)";
      }}
    >
      <button onClick={() => onOpen(job.id)}
        style={{
          position: "absolute", top: 9, right: 10,
          fontSize: 10, color: "var(--tx-3)",
          display: "flex", alignItems: "center", gap: 2,
          padding: "2px 6px", borderRadius: 4,
          border: "1px solid var(--line)", background: "var(--bg-surface)",
          cursor: "pointer", transition: "all .12s",
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--violet)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(124,58,237,0.3)"; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--tx-3)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--line)"; }}
      >
        open
      </button>
      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35, paddingRight: 44, marginBottom: 5, color: "var(--tx)" }}>{job.title}</div>
      <div style={{ fontSize: 12, color: "var(--tx-2)", marginBottom: 8 }}>{job.company}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {job.location && <span style={{ fontSize: 10.5, color: "var(--tx-3)" }}>{job.location}</span>}
        {job.remote && <span style={{ fontSize: 10, color: "var(--cyan)", fontWeight: 500 }}>Remote</span>}
      </div>
      <div style={{ marginTop: 9 }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: srcColor(job.source) }}>{job.source}</span>
      </div>
    </div>
  );
}
