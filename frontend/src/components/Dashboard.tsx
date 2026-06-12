import React, { useEffect, useState } from "react";
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
const _MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function _fmtDay(iso: string): string {
  // "2026-06-12" -> "Jun 12" (string parsing — timezone-safe)
  const [, m, d] = iso.split("-").map(Number);
  return `${_MONTHS[(m || 1) - 1]} ${d}`;
}

// ResumeVar-style activity chart: y-axis, gridlines, smooth curves, dots,
// styled hover tooltip with a vertical guide. No chart library.
function AreaChart({ scrape, applied, points }: { scrape: number[]; applied: number[]; points?: any[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const pts = points || [];
  const n = Math.max(pts.length, 2);

  // Nice y-axis max (1/2/5 × 10^k above the data peak)
  const peak = Math.max(...scrape, ...applied, 4);
  const pow = Math.pow(10, Math.floor(Math.log10(peak)));
  const niceMax = [1, 2, 5, 10].map(m => m * pow).find(m => m >= peak) || peak;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => Math.round(niceMax * f));

  const W = 1000, H = 300;
  const x = (i: number) => (i / (n - 1)) * W;
  const y = (v: number) => 8 + (1 - v / niceMax) * (H - 16);

  // Smooth path (Catmull-Rom → cubic bezier)
  const smooth = (vals: number[]) => {
    const P = vals.map((v, i) => [x(i), y(v)]);
    if (P.length < 2) return "";
    let d = `M ${P[0][0]} ${P[0][1]}`;
    for (let i = 0; i < P.length - 1; i++) {
      const p0 = P[Math.max(i - 1, 0)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(i + 2, P.length - 1)];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${p2[0]} ${p2[1]}`;
    }
    return d;
  };
  const scrapePath = smooth(scrape);
  const appliedPath = smooth(applied);
  const areaPath = `${scrapePath} L ${W} ${H} L 0 ${H} Z`;

  const dot = (cx: number, cy: number, color: string, sw: number, key: string) => (
    <path key={key} d={`M ${cx} ${cy} l 0 0.01`} stroke={color} strokeWidth={sw}
      strokeLinecap="round" vectorEffect="non-scaling-stroke" fill="none" />
  );

  const onMove = (e: React.MouseEvent) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    const idx = Math.round(((e.clientX - box.left) / box.width) * (n - 1));
    setHover(Math.min(Math.max(idx, 0), n - 1));
  };

  const hp = hover != null ? pts[hover] : null;
  const hoverLeftPct = hover != null ? (hover / (n - 1)) * 100 : 0;

  return (
    <div style={{ display: "flex", gap: 8 }}>
      {/* Y axis */}
      <div style={{ position: "relative", width: 30, height: 300, flexShrink: 0 }}>
        {ticks.map(t => (
          <span key={t} style={{ position: "absolute", right: 4, top: `${(y(t) / H) * 100}%`, transform: "translateY(-50%)",
            fontSize: 10.5, color: "var(--tx-3)", fontFamily: "var(--f-mono)" }}>{t}</span>
        ))}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div ref={wrapRef} style={{ position: "relative" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 300, display: "block" }}>
            <defs>
              <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgba(124,58,237,.35)" />
                <stop offset="100%" stopColor="rgba(124,58,237,0)" />
              </linearGradient>
            </defs>
            {/* gridlines */}
            {ticks.map(t => (
              <line key={t} x1={0} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            <path d={areaPath} fill="url(#areaGrad)" />
            <path d={scrapePath} fill="none" stroke="#7c3aed" strokeWidth="3" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            <path d={appliedPath} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            {/* hover guide */}
            {hover != null && (
              <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--tx-3)" strokeWidth="1" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
            )}
            {/* dots */}
            {scrape.map((v, i) => dot(x(i), y(v), "#7c3aed", hover === i ? 13 : 9, `s${i}`))}
            {applied.map((v, i) => dot(x(i), y(v), "#3b82f6", hover === i ? 11 : 7, `a${i}`))}
          </svg>

          {/* styled tooltip */}
          {hp && (
            <div style={{ position: "absolute", top: 12, left: `${hoverLeftPct}%`,
              transform: hoverLeftPct > 70 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
              background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 10,
              boxShadow: "0 8px 24px rgba(0,0,0,.12)", padding: "10px 14px", pointerEvents: "none", zIndex: 5, whiteSpace: "nowrap" }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--tx)", marginBottom: 6 }}>{_fmtDay(hp.date || hp.label)}</div>
              <div style={{ fontSize: 12, color: "var(--tx-2)", display: "flex", alignItems: "center", gap: 6 }}>
                <i style={{ width: 9, height: 9, borderRadius: 3, background: "#7c3aed", display: "inline-block" }} />
                Scraped: <b>{hp.scraped}</b>{hp.scraped_usa != null && <span style={{ color: "var(--tx-3)" }}>(US {hp.scraped_usa} / IN {hp.scraped_india ?? 0})</span>}
              </div>
              <div style={{ fontSize: 12, color: "var(--tx-2)", display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
                <i style={{ width: 9, height: 9, borderRadius: 3, background: "#3b82f6", display: "inline-block" }} />
                Applied: <b>{hp.applied}</b>
              </div>
            </div>
          )}
        </div>

        {/* Date axis — horizontal, full names; cells are zero-width so labels
            can never blow up the dashboard grid */}
        {pts.length > 1 && (
          <div style={{ display: "flex", marginTop: 8, height: pts.length > 16 ? 34 : 18 }}>
            {pts.map((p, i) => (
              <span key={i} style={{ flex: "1 1 0", minWidth: 0, display: "flex", justifyContent: "center", overflow: "visible" }}>
                <span style={{ fontSize: pts.length > 16 ? 10 : 11.5, color: hover === i ? "var(--tx)" : "var(--tx-3)",
                  fontFamily: "var(--f-mono)", whiteSpace: "nowrap",
                  transform: pts.length > 16 ? "rotate(-45deg)" : "none" }}>
                  {_fmtDay(p.date || p.label)}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
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
            <div className="vbar-fill" style={{ height: (d.count / max * 100) + "%", background: d.color, transitionDelay: (i * 70) + "ms" }} />
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
        {items.length === 0 && <div style={{ padding: "16px 8px", fontSize: 12, color: "var(--tx-3)" }}>None yet</div>}
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

// "Last scraped Xmin ago" + live countdown to the next hourly scrape
function ScrapeStatus({ lastScrapedAt }: { lastScrapedAt?: string }) {
  const [nowTs, setNowTs] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const next = new Date(nowTs);
  next.setMinutes(60, 0, 0);
  const diff = Math.max(0, next.getTime() - nowTs);
  const mm = String(Math.floor(diff / 60000)).padStart(2, "0");
  const ss = String(Math.floor((diff % 60000) / 1000)).padStart(2, "0");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "flex-end", fontSize: 12, color: "var(--tx-3)" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span className="live-pip" />
        Last scraped <b style={{ color: "var(--tx-2)", fontFamily: "var(--f-mono)" }}>{lastScrapedAt ? `${timeAgo(lastScrapedAt)} ago` : "never"}</b>
      </span>
      <span>Next scrape in <b style={{ color: "var(--tx-2)", fontFamily: "var(--f-mono)" }}>{mm}:{ss}</b></span>
    </div>
  );
}

function timeAgo(iso: string) {
  if (!iso) return "";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}min ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return ""; }
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export function Dashboard({ isAdmin = false }: { isAdmin?: boolean }) {
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
  ];

  // Monthly data
  const monthly = (data.monthly || []).map((d: any) => ({
    m: d.month || d.m || "",
    scraped: d.scraped || 0,
    applied: d.applied || 0,
    tailored: d.tailored || 0,
  }));

  // 30-day activity — start at the first day with data (no empty left tail)
  const fullTimeline = data.timeline || [];
  const firstDataIdx = fullTimeline.findIndex((d: any) => (d.scraped || 0) > 0 || (d.applied || 0) > 0);
  const timeline = firstDataIdx > 0 && fullTimeline.length - firstDataIdx >= 2
    ? fullTimeline.slice(firstDataIdx)
    : fullTimeline;
  const activity = timeline.map((d: any) => d.scraped || 0);
  const activityApplied = timeline.map((d: any) => d.applied || 0);

  // Country/source bars
  const byCountry = (data.by_country || []).map(([country, count]: [string, number]) => ({ country, count }));
  const SRC_COLORS: Record<string, string> = {
    greenhouse:  "#22c55e",
    ashby:       "#ef4444",
    lever:       "#8b5cf6",
    workday:     "#f59e0b",
    hiringcafe:  "#ec4899",
    linkedin:    "#3b82f6",
    indeed:      "#f97316",
    greenhouse_job_board: "#22c55e",
  };
  const bySource  = (data.by_source  || []).map(([source, count]: [string, number]) => ({
    source, count,
    color: SRC_COLORS[source.toLowerCase().replace(/\s/g,"")] || "#6366f1",
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
          <ScrapeStatus lastScrapedAt={data.last_scraped_at} />
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
          <div className="chart-card span2">
            <div className="chart-head">
              <span className="chart-title">Monthly Trends</span>
              <div className="legend">
                <span><i style={{ background: "#6366f1" }} />Scraped</span>
                <span><i style={{ background: "#3b82f6" }} />Applied</span>
                <span><i style={{ background: "#7c3aed" }} />Tailored</span>
              </div>
            </div>
            {monthly.length > 0
              ? <MonthlyBars data={monthly} />
              : <div style={{ height: 150, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No data yet — scrape to populate</div>
            }
          </div>

          <div className="chart-card">
            <div className="chart-head"><span className="chart-title">Status Breakdown</span></div>
            {statusData.some(d => d.value > 0)
              ? <>
                  <Donut data={statusData.filter(d => d.value > 0)} />
                  <div className="donut-legend">
                    {statusData.map(s => (
                      <span key={s.label}><i style={{ background: s.color }} />{s.label} <b>{s.value}</b></span>
                    ))}
                  </div>
                </>
              : <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No jobs tracked yet</div>
            }
          </div>

          <div className="chart-card span3">
            <div className="chart-head">
              <span className="chart-title">30-Day Activity</span>
              <div className="legend">
                <span><i style={{ background: "#7c3aed" }} />Scraped</span>
                <span><i style={{ background: "#22d3ee" }} />Applications</span>
              </div>
            </div>
            {activity.length > 1
              ? <AreaChart scrape={activity} applied={activityApplied} points={timeline} />
              : <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No activity data yet</div>
            }
          </div>

          {/* Country/Source are scraper-ops metrics — admin only; users get a
              clean dashboard: stats, trends, status, 30-day activity */}
          {isAdmin && (
            <div className="chart-card">
              <div className="chart-head"><span className="chart-title">Jobs by Country</span></div>
              {byCountry.length > 0
                ? <HBars data={byCountry} />
                : <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No country data yet</div>
              }
            </div>
          )}

          {isAdmin && (
            <div className="chart-card span2">
              <div className="chart-head"><span className="chart-title">Jobs by Source</span></div>
              {bySource.length > 0
                ? <VBars data={bySource} />
                : <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No source data yet</div>
              }
            </div>
          )}
        </div>

        {/* Resume history — always show */}
        <div className="resume-history">
          <div className="rh-section-head">Resume History</div>
          <div className="rh-cols">
            <ResumeList title="Applied Resumes"  accent="#10b981" items={appliedJobs}  icon="applied"   />
            <ResumeList title="Tailored Resumes" accent="#7c3aed" items={tailoredJobs} icon="sparkles"  />
          </div>
        </div>

      </div>
    </div>
  );
}
