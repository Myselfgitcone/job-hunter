import { useMemo, useState } from "react";
import type { Job } from "../types";

// O2Ten curated-list view: color-coded collapsible category groups with
// compact rows; clicking a row opens the standard detail panel. The curated
// doc has no companies, so the section name (stored in j.company) is the
// group key. Skipped rows are filtered upstream like everywhere else.

function skillsOf(j: Job): string {
  const m = (j.description || "").match(/Skills:\s*([^\n]+)/);
  return m ? m[1].trim() : "";
}

export default function O2TenList({ jobs, selectedId, onSelect }: {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, Job[]>();
    for (const j of jobs) {
      const k = (j.company || "General").trim();
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(j);
    }
    // biggest categories first; inside a group: new first, applied sink
    for (const arr of m.values())
      arr.sort((a, b) => (a.status === "applied" ? 1 : 0) - (b.status === "applied" ? 1 : 0));
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [jobs]);

  const [closed, setClosed] = useState<Record<string, boolean>>({});

  if (!jobs.length)
    return <div style={{ padding: 40, textAlign: "center", color: "var(--tx-3)", fontSize: 13 }}>
      No O2Ten jobs yet — they arrive with the hourly scrape on publishing days.
    </div>;

  const totalApplied = jobs.filter(j => j.status === "applied").length;
  const allClosed = groups.length > 0 && groups.every(([g]) => closed[g]);
  // Stable per-category hue — same category, same color, every day.
  const hueOf = (s: string) => {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
    return h;
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 2px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
        border: "1px solid var(--line)", borderRadius: 12, background: "var(--bg-elevated)" }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--tx)" }}>
          {jobs.length} links · {groups.length} categories{totalApplied ? ` · ✓ ${totalApplied} applied` : ""}
        </span>
        <button type="button"
          onClick={() => setClosed(allClosed ? {} : Object.fromEntries(groups.map(([g]) => [g, true])))}
          style={{ marginLeft: "auto", fontSize: 11.5, fontWeight: 700, padding: "4px 12px", borderRadius: 8,
            cursor: "pointer", fontFamily: "inherit", border: "1px solid var(--line)",
            background: "var(--bg-surface)", color: "var(--tx-2)", whiteSpace: "nowrap" }}>
          {allClosed ? "Expand all" : "Collapse all"}
        </button>
      </div>
      {groups.map(([section, items]) => {
        const isClosed = !!closed[section];
        const appliedN = items.filter(j => j.status === "applied").length;
        const hue = hueOf(section);
        return (
          <div key={section} style={{ border: `1px solid hsla(${hue},60%,50%,0.35)`, borderRadius: 12, background: "var(--bg-surface)", overflow: "hidden" }}>
            <button type="button"
              onClick={() => setClosed(c => ({ ...c, [section]: !isClosed }))}
              style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "11px 14px",
                background: `hsla(${hue},65%,50%,0.10)`, border: "none", cursor: "pointer", fontFamily: "inherit", textAlign: "left" }}>
              <span style={{ fontSize: 12, color: `hsl(${hue},55%,45%)`, transform: isClosed ? "rotate(-90deg)" : "none", transition: "transform .15s" }}>▼</span>
              <span style={{ fontSize: 13.5, fontWeight: 700, color: `hsl(${hue},55%,42%)` }}>{section}</span>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: "#fff", background: `hsl(${hue},55%,48%)`, padding: "1px 8px", borderRadius: 999 }}>{items.length}</span>
              {appliedN > 0 && (
                <span style={{ fontSize: 11, fontWeight: 600, color: "#16a34a" }}>✓ {appliedN} applied</span>
              )}
            </button>
            {!isClosed && (
              <div>
                {items.map(j => {
                  const applied = j.status === "applied";
                  const skills = skillsOf(j);
                  const sel = j.id === selectedId;
                  return (
                    <div key={j.id} onClick={() => onSelect(j.id)}
                      style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                        padding: "8px 14px", borderTop: "1px solid var(--line)",
                        background: sel ? "rgba(124,58,237,0.07)" : "transparent",
                        borderLeft: sel ? "3px solid var(--violet)" : "3px solid transparent",
                        opacity: applied ? 0.75 : 1 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: applied ? "#16a34a" : "var(--tx)" }}>
                          {applied ? "✓ " : ""}{j.title}
                        </div>
                        {skills && (
                          <div style={{ fontSize: 11.5, color: "var(--tx-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {skills}
                          </div>
                        )}
                      </div>
                      {applied && <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", whiteSpace: "nowrap" }}>Applied</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
