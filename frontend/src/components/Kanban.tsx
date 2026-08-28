import { useRef, useState } from "react";
import type { Job } from "../types";
import { JOB_STATUSES } from "../types";
import { srcColor } from "./primitives";

const COLS = JOB_STATUSES;  // shared status config (types.ts)

// Hover-preview state: which job + where to float the card.
interface Hover { job: Job; x: number; y: number; }

function fmtDate(s: string): string {
  if (!s) return "";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

function jdSnippet(j: Job): string {
  const txt = (j.description || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return txt.length > 380 ? txt.slice(0, 380) + "…" : txt;
}

interface Props {
  jobs: Job[];
  onStatusChange: (id: string, status: string) => void;
  onSelect: (id: string) => void;
}

export function Kanban({ jobs, onStatusChange, onSelect }: Props) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const hoverTimer = useRef<number | null>(null);

  const onDragStart = (e: React.DragEvent, id: string) => { setDraggingId(id); setHover(null); e.dataTransfer.effectAllowed = "move"; };
  const onDragEnd = () => { setDraggingId(null); setOverCol(null); };
  const onDrop = (colId: string) => { if (draggingId) onStatusChange(draggingId, colId); setDraggingId(null); setOverCol(null); };

  const startHover = (job: Job, el: HTMLElement) => {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => {
      if (draggingId) return;
      const r = el.getBoundingClientRect();
      const W = 340;
      let x = r.right + 10;
      if (x + W > window.innerWidth - 8) x = r.left - W - 10;
      const y = Math.max(10, Math.min(r.top, window.innerHeight - 330));
      setHover({ job, x, y });
    }, 300);
  };
  const endHover = () => {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    setHover(null);
  };

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
                  onHoverStart={startHover} onHoverEnd={endHover}
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

      {/* Floating hover preview — appears after a short dwell, never steals the mouse */}
      {hover && !draggingId && (
        <div style={{
          position: "fixed", left: hover.x, top: hover.y, width: 340, zIndex: 80,
          pointerEvents: "none",
          background: "var(--bg-surface)", border: "1px solid var(--line-hi)",
          borderRadius: 12, padding: "12px 14px", boxShadow: "var(--sh-2, 0 8px 28px rgba(0,0,0,.4))",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
            <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--tx)", lineHeight: 1.3 }}>{hover.job.title}</div>
            {hover.job.qualify_result?.score != null && (
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--violet)", whiteSpace: "nowrap" }}>
                {hover.job.qualify_result.score}%
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--tx-2)", margin: "3px 0 8px" }}>
            {hover.job.company}{hover.job.location ? ` · ${hover.job.location}` : ""}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            <Chip>{hover.job.remote ? "Remote" : "Onsite / Hybrid"}</Chip>
            {hover.job.salary && <Chip>{hover.job.salary}</Chip>}
            {fmtDate(hover.job.posted_at) && <Chip>Posted {fmtDate(hover.job.posted_at)}</Chip>}
            <Chip><span style={{ color: srcColor(hover.job.source), fontWeight: 600 }}>{hover.job.source}</span></Chip>
            {hover.job.ats_score_after != null && <Chip>★ {hover.job.ats_score_after}</Chip>}
          </div>
          {jdSnippet(hover.job) && (
            <div style={{ fontSize: 11.5, color: "var(--tx-3)", lineHeight: 1.55 }}>{jdSnippet(hover.job)}</div>
          )}
          <div style={{ fontSize: 10.5, color: "var(--tx-faint)", marginTop: 8 }}>Click card for full details</div>
        </div>
      )}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      fontSize: 10.5, color: "var(--tx-2)", padding: "2px 8px", borderRadius: 999,
      border: "1px solid var(--line)", background: "var(--bg-elevated)", whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

function KanbanCard({ job, dragging, onDragStart, onDragEnd, onOpen, onHoverStart, onHoverEnd }: {
  job: Job; dragging: boolean;
  onDragStart: (e: React.DragEvent, id: string) => void;
  onDragEnd: () => void;
  onOpen: (id: string) => void;
  onHoverStart: (job: Job, el: HTMLElement) => void;
  onHoverEnd: () => void;
}) {
  return (
    <div
      draggable onDragStart={e => onDragStart(e, job.id)} onDragEnd={onDragEnd}
      onClick={() => onOpen(job.id)}
      style={{
        margin: "6px 8px", padding: "11px 12px",
        background: "var(--bg-elevated)",
        border: "1px solid var(--line)",
        borderRadius: "var(--r-sm)",
        cursor: "pointer", position: "relative",
        opacity: dragging ? 0.4 : 1,
        boxShadow: "0 1px 3px rgba(0,0,0,.3)",
        transition: "border-color 120ms ease, box-shadow 120ms ease",
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.borderColor = "var(--line-hi)";
        el.style.boxShadow = "var(--sh-1)";
        onHoverStart(job, el);
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.borderColor = "var(--line)";
        el.style.boxShadow = "0 1px 3px rgba(0,0,0,.3)";
        onHoverEnd();
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35, marginBottom: 5, color: "var(--tx)" }}>{job.title}</div>
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
