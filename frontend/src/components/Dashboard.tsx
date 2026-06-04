import { useEffect, useState } from "react";
import { api } from "../api";

// ── StatCard with count-up animation ─────────────────────────────────────────
function StatCard({ stat }: { stat: { label: string; value: number; delta: string; grad: [string, string] } }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    let raf: number;
    const start = performance.now(); const dur = 900;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      setN(Math.round(stat.value * e));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [stat.value]);
  return (
    <div className="stat-card">
      <div className="stat-glow" style={{ background: `linear-gradient(135deg, ${stat.grad[0]}, ${stat.grad[1]})` }} />
      <div className="stat-label">{stat.label}</div>
      <div className="stat-value">{n.toLocaleString()}</div>
      <div className="stat-delta">{stat.delta}</div>
    </div>
  );
}

// ── Donut chart (SVG) ─────────────────────────────────────────────────────────
function Donut({ data }: { data: Array<{ label: string; value: number; color: string }> }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const R = 52, C = 2 * Math.PI * R, gap = 2;
  let offset = 0;
  const [show, setShow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setShow(true), 100); return () => clearTimeout(t); }, []);
  return (
    <div className="donut-wrap">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <g transform="rotate(-90 70 70)">
          {data.map((d, i) => {
            const frac = d.value / total;
            const len = show ? frac * C - gap : 0;
            const dash = `${len} ${C - len}`;
            const el = (
              <circle key={i} cx="70" cy="70" r={R} fill="none" stroke={d.color} strokeWidth="14"
                strokeDasharray={dash} strokeDashoffset={-offset}
                style={{ transition: "stroke-dasharray .9s var(--ease), stroke-dashoffset .9s var(--ease)" }} />
            );
            offset += show ? frac * C : 0;
            return el;
          })}
        </g>
      </svg>
      <div className="donut-center">
        <b>{total}</b><span>tracked</span>
      </div>
    </div>
  );
}

// ── Monthly bars (CSS animated) ───────────────────────────────────────────────
function MonthlyBars({ data }: { data: Array<{ m: string; scraped: number; applied: number; tailored: number }> }) {
  const max = Math.max(...data.map(d => d.scraped), 1);
  const series: [string, string][] = [["scraped","#6366f1"],["applied","#3b82f6"],["tailored","#7c3aed"]];
  return (
    <div className="mbars">
      {data.map((d, i) => (
        <div className="mbar-col" key={i}>
          <div className="mbar-stack">
            {series.map(([k, c]) => {
              const v = k === "scraped" ? (d as any)[k] / max : ((d as any)[k] / 40);
              return <div key={k} className="mbar" style={{ height: Math.max(3, v * 100) + "%", background: c, "--d": (i * 60) + "ms" } as React.CSSProperties} title={`${k}: ${(d as any)[k]}`} />;
            })}
          </div>
          <span className="mbar-label">{d.m}</span>
        </div>
      ))}
    </div>
  );
}

// ── Area chart (SVG) ─────────────────────────────────────────────────────────
function AreaChart({ scrape, applied }: { scrape: number[]; applied: number[] }) {
  const w = 520, h = 120, max = Math.max(...scrape, 1);
  const pts = (arr: number[], scale: number) =>
    arr.map((v, i) => `${(i / (arr.length - 1)) * w},${h - (v / max) * h * scale}`);
  const line = pts(scrape, 0.92);
  const area = `0,${h} ${line.join(" ")} ${w},${h}`;
  const appLine = pts(applied.map(v => v * 3), 0.92);
  return (
    <svg className="area-chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(124,58,237,.4)" />
          <stop offset="100%" stopColor="rgba(124,58,237,0)" />
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#areaGrad)" />
      <polyline points={line.join(" ")} fill="none" stroke="#7c3aed" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <polyline points={appLine.join(" ")} fill="none" stroke="#22d3ee" strokeWidth="2" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// ── Horizontal bars ───────────────────────────────────────────────────────────
function HBars({ data }: { data: Array<{ country: string; count: number }> }) {
  const max = Math.max(...data.map(d => d.count), 1);
  return (
    <div className="hbars">
      {data.map((d, i) => (
        <div className="hbar-row" key={i}>
          <span className="hbar-label">{d.country}</span>
          <div className="hbar-track">
            <div className="hbar-fill" style={{ width: (d.count / max * 100) + "%", transitionDelay: (i * 70) + "ms" }} />
          </div>
          <span className="hbar-val">{d.count.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

// ── Vertical bars ─────────────────────────────────────────────────────────────
function VBars({ data }: { data: Array<{ source: string; count: number; color: string }> }) {
  const max = Math.max(...data.map(d => d.count), 1);
  return (
    <div className="vbars">
      {data.map((d, i) => (
        <div className="vbar-col" key={i}>
          <div className="vbar-track">
            <div className="vbar-fill" style={{ height: (d.count / max * 100) + "%", background: `var(${d.color})`, transitionDelay: (i * 70) + "ms" }} />
          </div>
          <span className="vbar-val">{(d.count / 1000).toFixed(1)}k</span>
          <span className="vbar-label">{d.source}</span>
        </div>
      ))}
    </div>
  );
}

// ── Resume history list ───────────────────────────────────────────────────────
function ResumeList({ title, accent, items, icon }: {
  title: string; accent: string;
  items: Array<{ company: string; title: string; when: string; location: string }>;
  icon: string;
}) {
  const PATH: Record<string, string> = {
    applied:   '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    sparkles:  '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/>',
  };
  return (
    <div className="rh-col">
      <div className="rh-head" style={{ color: accent }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: PATH[icon] || PATH.applied }} />
        {title}
        <span className="rh-count">{items.length}</span>
      </div>
      <div className="rh-list">
        {items.map((it, i) => (
          <div className="rh-item" key={i}>
            <span className="rh-num" style={{ color: accent, borderColor: accent + "55", background: accent + "18" }}>{i + 1}</span>
            <div className="rh-main">
              <div className="rh-title">{it.title}</div>
              <div className="rh-sub">{it.company} · {it.location}</div>
            </div>
            <span className="rh-when">{it.when}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function timeAgo(iso: string) {
  if (!iso) return "";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return ""; }
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export function Dashboard() {
  const [data, setData]       = useState<any>(null);
  const [reminders, setReminders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAnalytics().then(setData).catch(console.error).finally(() => setLoading(false));
    api.getReminders().then(setReminders).catch(() => {});
  }, []);

  if (loading) return (
    <div className="dash-scroll"><div className="dash-inner" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, color: "var(--tx-3)" }}>
        <div className="tm-spinner" />
        <span style={{ fontSize: 13 }}>Loading dashboard…</span>
      </div>
    </div></div>
  );
  if (!data) return null;

  // Map API data to design shape
  const st      = data.by_status || {};
  const total   = data.total || 0;
  const applied = st["applied"]   || 0;
  const interview = st["interview"] || 0;
  const skipped = st["skipped"]   || 0;
  const newJobs = st["new"]       || 0;
  const tailored = (data.tailored_jobs || []).length;

  const stats = [
    { label: "Total Scraped", value: total,     delta: "+scraping", grad: ["#475569","#64748b"] as [string,string] },
    { label: "New Jobs",      value: newJobs,   delta: "pending",   grad: ["#6366f1","#818cf8"] as [string,string] },
    { label: "Applied",       value: applied,   delta: "+this week", grad: ["#3b82f6","#60a5fa"] as [string,string] },
    { label: "Interviews",    value: interview, delta: "upcoming",   grad: ["#10b981","#34d399"] as [string,string] },
    { label: "AI Tailored",   value: tailored,  delta: "+this week", grad: ["#7c3aed","#a78bfa"] as [string,string] },
  ];

  const statusData = [
    { label: "New",       value: newJobs,   color: "#3b82f6" },
    { label: "Applied",   value: applied,   color: "#10b981" },
    { label: "Interview", value: interview, color: "#f59e0b" },
    { label: "Tailored",  value: tailored,  color: "#7c3aed" },
    { label: "Skipped",   value: skipped,   color: "#64748b" },
  ].filter(d => d.value > 0);

  // Monthly data
  const monthly = (data.monthly || []).map((d: any) => ({
    m: d.month || d.m || "",
    scraped: d.scraped || 0,
    applied: d.applied || 0,
    tailored: d.tailored || 0,
  }));

  // 30-day activity
  const timeline = data.timeline || [];
  const activity = timeline.map((d: any) => d.scraped || 0);
  const activityApplied = timeline.map((d: any) => d.applied || 0);

  // Country/source bars
  const byCountry = (data.by_country || []).map(([country, count]: [string, number]) => ({ country, count }));
  const bySource  = (data.by_source  || []).map(([source, count]: [string, number]) => ({
    source, count,
    color: `--src-${source.toLowerCase().replace(/\s/g,"")}`,
  }));

  // Resume history
  const appliedJobs  = (data.applied_jobs  || []).map((j: any) => ({ company: j.company, title: j.title, when: timeAgo(j.applied_at || j.scraped_at), location: j.location || "" }));
  const tailoredJobs = (data.tailored_jobs || []).map((j: any) => ({ company: j.company, title: j.title, when: timeAgo(j.tailored_at || j.scraped_at), location: j.location || "" }));

  // Reminders mapped
  const remList = (reminders || []).map((r: any) => ({
    kind: r.kind || "followup",
    title: r.title, detail: r.detail,
    when: r.when, tag: r.tag, urgent: !!r.urgent,
  }));

  const REMINDER_ICON: Record<string, string> = {
    interview: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
    deadline:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    followup:  '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  };

  return (
    <div className="dash-scroll">
      <div className="dash-inner">

        {/* Header */}
        <div className="dash-head">
          <div>
            <h1 className="dash-title">Dashboard</h1>
            <p className="dash-sub">Your job search at a glance</p>
          </div>
          <div className="dash-updated"><span className="live-pip" />Updated {timeAgo(data.last_scraped_at || "")} ago</div>
        </div>

        {/* Stat cards */}
        <div className="stat-row">
          {stats.map(s => <StatCard key={s.label} stat={s} />)}
        </div>

        {/* Reminders */}
        {remList.length > 0 && (
          <div className="reminders">
            <div className="rem-head">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>
              </svg>
              Reminders
            </div>
            <div className="rem-list">
              {remList.map((r, i) => (
                <div className={`rem-card${r.urgent ? " urgent" : ""}`} key={i}>
                  <div className={`rem-ico ${r.kind}`}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: REMINDER_ICON[r.kind] || REMINDER_ICON.followup }} />
                  </div>
                  <div className="rem-main">
                    <div className="rem-title">{r.title}</div>
                    <div className="rem-detail">{r.detail}</div>
                  </div>
                  <div className="rem-right">
                    <span className="rem-when">{r.when}</span>
                    <span className={`rem-tag${r.urgent ? " urgent" : ""}`}>{r.tag}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chart grid */}
        <div className="chart-grid">
          {monthly.length > 0 && (
            <div className="chart-card span2">
              <div className="chart-head">
                <span className="chart-title">Monthly Trends</span>
                <div className="legend">
                  <span><i style={{ background: "#6366f1" }} />Scraped</span>
                  <span><i style={{ background: "#3b82f6" }} />Applied</span>
                  <span><i style={{ background: "#7c3aed" }} />Tailored</span>
                </div>
              </div>
              <MonthlyBars data={monthly} />
            </div>
          )}

          {statusData.length > 0 && (
            <div className="chart-card">
              <div className="chart-head"><span className="chart-title">Status Breakdown</span></div>
              <Donut data={statusData} />
              <div className="donut-legend">
                {statusData.map(s => (
                  <span key={s.label}><i style={{ background: s.color }} />{s.label} <b>{s.value}</b></span>
                ))}
              </div>
            </div>
          )}

          {activity.length > 1 && (
            <div className="chart-card span3">
              <div className="chart-head">
                <span className="chart-title">30-Day Activity</span>
                <div className="legend">
                  <span><i style={{ background: "#7c3aed" }} />Scraped</span>
                  <span><i style={{ background: "#22d3ee" }} />Applications</span>
                </div>
              </div>
              <AreaChart scrape={activity} applied={activityApplied} />
            </div>
          )}

          {byCountry.length > 0 && (
            <div className="chart-card span2">
              <div className="chart-head"><span className="chart-title">Jobs by Country</span></div>
              <HBars data={byCountry} />
            </div>
          )}

          {bySource.length > 0 && (
            <div className="chart-card">
              <div className="chart-head"><span className="chart-title">Jobs by Source</span></div>
              <VBars data={bySource} />
            </div>
          )}
        </div>

        {/* Resume history */}
        {(appliedJobs.length > 0 || tailoredJobs.length > 0) && (
          <div className="resume-history">
            <div className="rh-section-head">Resume History</div>
            <div className="rh-cols">
              <ResumeList title="Applied Resumes"  accent="#10b981" items={appliedJobs}  icon="applied"   />
              <ResumeList title="Tailored Resumes" accent="#7c3aed" items={tailoredJobs} icon="sparkles"  />
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
