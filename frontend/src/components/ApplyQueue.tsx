import { useState } from "react";
import type { Job } from "../types";

// ── Apply queue ───────────────────────────────────────────────────────────────
// Walk a list of jobs one at a time: open the application (armed with #jh=1 so
// the extension auto-fills + attaches the resume), you review and submit, then
// mark it and move on. One click per job instead of hunting for each form.
//
// Each "Open" is driven by a real click so the browser never blocks the tab —
// deliberately not a burst of background tabs.

interface Props {
  jobs: Job[];                       // the queued jobs, in order
  onClose: () => void;
  onApplied: (jobId: string) => void;
  onSkip: (jobId: string) => void;
}

export function ApplyQueue({ jobs, onClose, onApplied, onSkip }: Props) {
  const [i, setI] = useState(0);
  const [opened, setOpened] = useState(false);

  const job = jobs[i];
  const done = i >= jobs.length;

  const advance = () => { setOpened(false); setI(n => n + 1); };

  const open = () => {
    if (!job) return;
    const url = job.url + (job.url.includes("#") ? "&" : "#") + "jh=" + job.id;
    window.open(url, "_blank", "noopener");
    setOpened(true);
  };

  return (
    <div style={{
      position: "fixed", left: "50%", bottom: 22, transform: "translateX(-50%)", zIndex: 200,
      width: "min(680px, calc(100vw - 40px))",
      background: "var(--bg-surface)", border: "1px solid var(--line-hi)",
      borderRadius: 14, boxShadow: "0 18px 50px rgba(0,0,0,0.45)", overflow: "hidden",
    }}>
      {/* Progress */}
      <div style={{ height: 3, background: "var(--line)" }}>
        <div style={{ height: "100%", width: `${(Math.min(i, jobs.length) / jobs.length) * 100}%`,
          background: "linear-gradient(90deg,#7c3aed,#06b6d4)", transition: "width .3s" }} />
      </div>

      <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 14 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase",
          color: "var(--tx-3)", fontFamily: "var(--f-mono)", flexShrink: 0 }}>
          {done ? "Queue done" : `${i + 1} / ${jobs.length}`}
        </span>

        {done ? (
          <>
            <span style={{ flex: 1, fontSize: 13, color: "var(--tx-1)" }}>
              Finished all {jobs.length} — nice work.
            </span>
            <button className="act primary" onClick={onClose}>Close</button>
          </>
        ) : (
          <>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--tx-1)", whiteSpace: "nowrap",
                overflow: "hidden", textOverflow: "ellipsis" }}>{job.title}</div>
              <div style={{ fontSize: 11.5, color: "var(--tx-3)", whiteSpace: "nowrap",
                overflow: "hidden", textOverflow: "ellipsis" }}>
                {job.company}{job.location ? ` · ${job.location}` : ""}
              </div>
            </div>

            {!opened ? (
              <button className="act primary" onClick={open} style={{ flexShrink: 0 }}>
                Open &amp; fill →
              </button>
            ) : (
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <button className="act" onClick={open} title="Reopen this application">Reopen</button>
                <button className="act primary"
                  onClick={() => { onApplied(job.id); advance(); }}>
                  Applied ✓
                </button>
              </div>
            )}
            <button className="act ghost" onClick={() => { onSkip(job.id); advance(); }}
              style={{ flexShrink: 0 }}>Skip</button>
            <button onClick={onClose} title="Close queue"
              style={{ background: "none", border: "none", color: "var(--tx-3)", cursor: "pointer",
                fontSize: 18, lineHeight: 1, flexShrink: 0, padding: "0 2px" }}>×</button>
          </>
        )}
      </div>

      {opened && !done && (
        <div style={{ padding: "0 16px 11px", fontSize: 11.5, color: "var(--tx-3)" }}>
          Opened in a new tab. If it's the job posting, click <b>Apply</b> there — the form
          fills itself once it loads. Review, submit on the ATS, then hit <b>Applied ✓</b>.
        </div>
      )}
    </div>
  );
}
