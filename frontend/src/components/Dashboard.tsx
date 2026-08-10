import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { api, downloadFile } from "../api";

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
// ── Monthly trend lines (SVG) ─────────────────────────────────────────────────
function MonthlyBars({ data }: { data: Array<{ m: string; scraped: number; applied: number; tailored: number }> }) {
  // ONE shared max across all 3 series, not one max per series. Per-series
  // maxes made bars incomparable to each other: if June happened to be the
  // peak month for Scraped(1500), Applied(18), AND Tailored(10), all three
  // rendered near 100% height simultaneously — implying rough parity
  // between numbers that are actually 100x apart. A single shared scale
  // (plus sqrt, so Applied/Tailored don't vanish next to Scraped's volume)
  // keeps bar height honestly meaningful both across months (same series)
  // AND across series (same month).
  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const globalMax = Math.max(...data.flatMap(d => [d.scraped, d.applied, d.tailored]), 1);
  const series: [string, string, string][] = [
    ["scraped",  "#6366f1", "Scraped"],
    ["applied",  "#3b82f6", "Applied"],
    ["tailored", "#7c3aed", "Tailored"],
  ];

  const W = 1000, H = 240, TOP = 10;
  const n = Math.max(data.length, 1);

  // Linear scale with uniform nice steps (1k, 2k, 3k...). The
  // axis top is the peak rounded UP to the next step, so the last gridline
  // sits at/above the tallest bar (peak 5.3k → lines at 1k..6k).
  const _mag = Math.pow(10, Math.floor(Math.log10(Math.max(globalMax / 8, 1))));
  const step = [1, 2, 5, 10].map(m => m * _mag).find(s => globalMax / s <= 8) || _mag * 10;
  const axisMax = Math.ceil(globalMax / step) * step;
  const levels: number[] = [];
  for (let v = step; v <= axisMax; v += step) levels.push(v);
  const y = (v: number) => H - (v / axisMax) * (H - TOP);
  const fmtLvl = (v: number) => v >= 1000 ? (v % 1000 === 0 ? v / 1000 + "k" : (v / 1000).toFixed(1) + "k") : String(v);

  // Grouped bars: 3 per month, centered in the month's band
  const band = W / n;
  const barW = Math.min(30, band / 5);
  const gap  = barW * 0.35;
  const groupW = 3 * barW + 2 * gap;

  const onMove = (e: React.MouseEvent) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    const idx = Math.floor(((e.clientX - box.left) / box.width) * n);
    setHover(Math.min(Math.max(idx, 0), n - 1));
  };
  const hp = hover != null ? data[hover] : null;
  const hoverLeftPct = hover != null ? ((hover + 0.5) / n) * 100 : 0;

  return (
    <div style={{ display: "flex", gap: 8 }}>
      {/* Y axis labels */}
      <div style={{ position: "relative", width: 34, height: 260, flexShrink: 0 }}>
        {levels.map(v => (
          <span key={v} style={{ position: "absolute", right: 4, top: `${(y(v) / H) * 100 * (240 / 260)}%`, transform: "translateY(-50%)",
            fontSize: 10, color: "var(--tx-3)", fontFamily: "var(--f-mono)" }}>{fmtLvl(v)}</span>
        ))}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div ref={wrapRef} style={{ position: "relative" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 240, display: "block" }}>
            {/* hover band */}
            {hover != null && (
              <rect x={hover * band} y={0} width={band} height={H} fill="rgba(124,58,237,0.06)" />
            )}
            {/* gridlines */}
            {levels.map(v => (
              <line key={v} x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1={0} x2={W} y1={H} y2={H} stroke="var(--line)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            {/* grouped bars */}
            {data.map((d, i) => {
              const gx = i * band + (band - groupW) / 2;
              return series.map(([k, c], s) => {
                const raw = (d as any)[k] as number;
                if (!raw) return null;
                const by = y(raw);
                return (
                  <rect key={`${i}${k}`} x={gx + s * (barW + gap)} y={by}
                    width={barW} height={Math.max(H - by, 3)} rx={3}
                    fill={c} opacity={hover == null || hover === i ? 1 : 0.45}
                    style={{ transition: "opacity .15s" }} />
                );
              });
            })}
          </svg>

          {/* tooltip — same style as Daily Activity */}
          {hp && (
            <div style={{ position: "absolute", top: 8, left: `${hoverLeftPct}%`,
              transform: hoverLeftPct > 70 ? "translateX(calc(-100% - 14px))" : "translateX(14px)",
              background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 10,
              boxShadow: "0 8px 24px rgba(0,0,0,.12)", padding: "10px 14px", pointerEvents: "none", zIndex: 5, whiteSpace: "nowrap" }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--tx)", marginBottom: 6 }}>{hp.m}</div>
              {series.map(([k, c, label]) => (
                <div key={k} style={{ fontSize: 12, color: "var(--tx-2)", display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
                  <i style={{ width: 9, height: 9, borderRadius: 3, background: c, display: "inline-block" }} />
                  {label}: <b>{((hp as any)[k] as number).toLocaleString()}</b>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* month labels + scraped total under each */}
        <div style={{ display: "flex", marginTop: 8 }}>
          {data.map((d, i) => (
            <div key={i} style={{ flex: "1 1 0", minWidth: 0, textAlign: "center" }}>
              <div style={{ fontSize: 11, color: hover === i ? "var(--tx)" : "var(--tx-3)", fontFamily: "var(--f-mono)" }}>{d.m}</div>
              <div style={{ fontSize: 10.5, fontWeight: 700, marginTop: 2,
                color: hover === i ? "#6366f1" : "var(--tx-3)" }}>
                {d.scraped >= 1000 ? (d.scraped / 1000).toFixed(1) + "k" : d.scraped}
              </div>
            </div>
          ))}
        </div>
      </div>
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

      {/* Chart body scrolls horizontally (Y axis stays pinned) — every day
          keeps a readable width instead of squeezing; scrollbar at bottom.
          overflowY MUST be hidden: overflow-x:auto silently forces
          overflow-y from visible to auto, so the hover tooltip's transient
          vertical overflow popped a scrollbar in/out, shifting the chart
          and making the hover jump. */}
      <div style={{ flex: 1, minWidth: 0, overflowX: "auto", overflowY: "hidden", paddingBottom: 6 }}>
      <div style={{ minWidth: n * 34 }}>
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
    </div>
  );
}

// ── Vertical bars ─────────────────────────────────────────────────────────────
function VBars({ data }: { data: Array<{ source: string; count: number; color: string }> }) {
  const max = Math.max(...data.map(d => d.count), 1);
  // Horizontal scroll: every source keeps a readable column width instead of
  // squeezing to fit — scrollbar sits at the card's bottom edge.
  return (
    <div style={{ overflowX: "auto", paddingBottom: 6 }}>
      <div className="vbars" style={{ minWidth: data.length * 84 }}>
        {data.map((d, i) => (
          <div className="vbar-col" key={i} style={{ minWidth: 72 }}>
            <div className="vbar-track">
              <div className="vbar-fill" style={{ height: (d.count / max * 100) + "%", background: d.color, transitionDelay: (i * 70) + "ms" }} />
            </div>
            <span className="vbar-val">{(d.count / 1000).toFixed(1)}k</span>
            <span className="vbar-label">{d.source}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Resume history list ───────────────────────────────────────────────────────
function _fmtFullDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso.replace(/(\.\d{3})\d+/, "$1")).toLocaleDateString("en-US",
      { timeZone: "America/New_York", month: "short", day: "numeric", year: "numeric" });
  } catch { return ""; }
}

// ResumeVar-style column: search, big cards, status pill, pagination
const QUICK_ACCENT = "#d97706";  // amber-600

function ResumeList({ title, accent, items, icon, badge, showDownloads }: {
  title: string; accent: string;
  items: Array<{ id?: string; company: string; title: string; when: string; whenFull: string; location: string; exp: string; source?: "job" | "quick"; cost?: number | null; tin?: number | null; tout?: number | null }>;
  icon: string; badge: string; showDownloads?: boolean;
}) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const PER = 10;
  const PATH: Record<string, string> = {
    applied:   '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    sparkles:  '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/>',
  };
  const filtered = items.filter(it => (it.title + " " + it.company).toLowerCase().includes(q.toLowerCase()));
  const pages = Math.max(1, Math.ceil(filtered.length / PER));
  const cur = Math.min(page, pages);
  const shown = filtered.slice((cur - 1) * PER, cur * PER);
  const pageBtn = (p: number) => (
    <button key={p} onClick={() => setPage(p)}
      style={{ minWidth: 30, height: 30, borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: "pointer",
        border: cur === p ? `1px solid ${accent}` : "1px solid var(--line)",
        background: cur === p ? accent + "18" : "transparent",
        color: cur === p ? accent : "var(--tx-2)" }}>{p}</button>
  );
  return (
    <div className="rh-col" style={{ minWidth: 0 }}>
      <div className="rh-head" style={{ color: accent }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: PATH[icon] || PATH.applied }} />
        {title}
        <span className="rh-count">{items.length}</span>
        <span style={{ marginLeft: 8, display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 10.5, padding: "1px 7px", borderRadius: 6, background: accent + "1c", color: accent, border: `1px solid ${accent}55` }}>✓ Tailored</span>
          <span style={{ fontSize: 10.5, padding: "1px 7px", borderRadius: 6, background: QUICK_ACCENT + "1c", color: QUICK_ACCENT, border: `1px solid ${QUICK_ACCENT}55` }}>⚡ Quick</span>
        </span>
      </div>

      <input value={q} onChange={e => { setQ(e.target.value); setPage(1); }}
        placeholder="Search by company or title"
        style={{ width: "100%", height: 38, padding: "0 14px", borderRadius: 10, border: "1px solid var(--line)",
          background: "var(--bg-elevated)", color: "var(--tx)", fontSize: 13, marginBottom: 10, outline: "none" }} />

      <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 120,
        maxHeight: 430, overflowY: "auto", paddingRight: 4,
        scrollbarWidth: "thin", scrollbarColor: "var(--line-hi) transparent" }}>
        {shown.length === 0 && <div style={{ padding: "24px 8px", fontSize: 12.5, color: "var(--tx-3)", textAlign: "center" }}>None yet</div>}
        {shown.map((it, i) => {
          const isQuick = it.source === "quick";
          const cardAccent = isQuick ? QUICK_ACCENT : accent;
          const cardBg = isQuick ? QUICK_ACCENT + "0d" : "var(--bg-elevated)";
          const dlUrls = it.id
            ? isQuick
              ? [
                  { label: "PDF",  url: api.quickHistoryPdfUrl(it.id),  file: "resume.pdf"  },
                  { label: "DOCX", url: api.quickHistoryDocxUrl(it.id), file: "resume.docx" },
                  { label: "JD",   url: api.quickHistoryJdUrl(it.id),   file: "jd.txt"      },
                ]
              : [
                  { label: "PDF",  url: api.pdfUrl(it.id),  file: "resume.pdf"  },
                  { label: "DOCX", url: api.docxUrl(it.id), file: "resume.docx" },
                  { label: "JD",   url: api.jdUrl(it.id),   file: "jd.txt"      },
                ]
            : [];
          return (
            <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "14px 16px",
              borderRadius: 12, border: `1px solid ${isQuick ? QUICK_ACCENT + "44" : "var(--line)"}`, background: cardBg }}>
              <span style={{ width: 34, height: 34, borderRadius: 9, flexShrink: 0, display: "grid", placeItems: "center",
                background: cardAccent + "18", color: cardAccent }}>
                {isQuick
                  ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                  : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3v5h5"/><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
                }
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div title={`${it.company}${it.title ? ` – ${it.title}` : ""}`}
                  style={{ fontSize: 13.5, fontWeight: 700, color: "var(--tx)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <span style={{ color: "var(--tx-3)", fontFamily: "var(--f-mono)", fontWeight: 600, marginRight: 6 }}>#{(cur - 1) * PER + i + 1}</span>
                  {it.company}{it.title ? ` – ${it.title}` : ""}
                </div>
                <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 4 }}>
                  {isQuick ? "Quick Tailor" : badge}: <b style={{ color: "var(--tx-2)" }}>{it.whenFull}</b>{it.when && <span> ({it.when})</span>}
                </div>
                {it.location && <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 2 }}>Location: {it.location}</div>}
                {it.exp && <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 2 }}>Exp Needed: {it.exp} yrs</div>}
              </div>
              <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                <span style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 10px", borderRadius: 999,
                  background: cardAccent + "1c", color: cardAccent }}>
                  {isQuick ? "⚡ Quick" : `✓ ${badge}`}
                </span>
                {typeof it.cost === "number" && (
                  <span title={`${(it.tin || 0).toLocaleString()} in / ${(it.tout || 0).toLocaleString()} out tokens`}
                    style={{ fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 999,
                      background: "#7c3aed14", color: "#7c3aed", fontFamily: "var(--f-mono)" }}>
                    ${it.cost.toFixed(3)}
                  </span>
                )}
                {showDownloads && dlUrls.length > 0 && (
                  <div style={{ display: "flex", gap: 5 }}>
                    {dlUrls.map(({ label, url, file }) => (
                      <button key={label} onClick={() => downloadFile(url, file)}
                        style={{ fontSize: 10.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6,
                          border: "1px solid var(--line)", background: "var(--bg-surface)",
                          color: "var(--tx-2)", cursor: "pointer" }}>
                        {label}
                      </button>
                    ))}
                  </div>
                )}
                {!isQuick && it.id && (
                  <a href={`#job=${it.id}`} title="Open job details"
                    style={{ fontSize: 10.5, fontWeight: 700, padding: "4px 12px", borderRadius: 6,
                      border: `1px solid ${cardAccent}55`, background: cardAccent + "14",
                      color: cardAccent, cursor: "pointer", textDecoration: "none" }}>
                    ↗ Open
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {pages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 12 }}>
          <button onClick={() => setPage(Math.max(1, cur - 1))} disabled={cur === 1}
            style={{ background: "none", border: "none", color: cur === 1 ? "var(--tx-faint)" : "var(--tx-2)", fontSize: 12.5, fontWeight: 600, cursor: cur === 1 ? "default" : "pointer" }}>‹ Previous</button>
          {pageBtn(1)}
          {cur > 3 && <span style={{ color: "var(--tx-3)" }}>…</span>}
          {[cur - 1, cur, cur + 1].filter(p => p > 1 && p < pages).map(pageBtn)}
          {cur < pages - 2 && <span style={{ color: "var(--tx-3)" }}>…</span>}
          {pages > 1 && pageBtn(pages)}
          <button onClick={() => setPage(Math.min(pages, cur + 1))} disabled={cur === pages}
            style={{ background: "none", border: "none", color: cur === pages ? "var(--tx-faint)" : "var(--tx-2)", fontSize: 12.5, fontWeight: 600, cursor: cur === pages ? "default" : "pointer" }}>Next ›</button>
        </div>
      )}
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
        Last scraped <b style={{ color: "var(--tx-2)", fontFamily: "var(--f-mono)" }}>{lastScrapedAt ? timeAgo(lastScrapedAt) : "never"}</b>
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

// ── Searchable user picker ────────────────────────────────────────────────────
function UserPicker({ users, selectedId, onSelect }: {
  users: any[]; selectedId: string | null; onSelect: (id: string | null) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [open, setOpen]   = React.useState(false);
  const ref               = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const selected = selectedId ? users.find(u => u.user?.id === selectedId) : null;
  const displayName = selected ? (selected.user?.name || selected.user?.email) : "All Users";

  const filtered = users.filter(u => {
    const q = query.toLowerCase();
    return (u.user?.name || "").toLowerCase().includes(q) || (u.user?.email || "").toLowerCase().includes(q);
  });

  const initials = (name: string) => name.split(" ").map((w: string) => w[0] || "").join("").slice(0, 2).toUpperCase();

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => { setOpen(o => !o); setQuery(""); }}
        style={{
          display: "flex", alignItems: "center", gap: 8, padding: "6px 12px",
          borderRadius: 8, border: "1px solid var(--line)", background: "var(--bg-elevated)",
          color: "var(--tx)", cursor: "pointer", fontFamily: "inherit", fontSize: 13, fontWeight: 600,
          minWidth: 160,
        }}
      >
        {selected && (
          <div style={{ width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg,#7c3aed,#6366f1)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 9, fontWeight: 700, flexShrink: 0 }}>
            {initials(selected.user?.name || selected.user?.email || "")}
          </div>
        )}
        <span style={{ flex: 1, textAlign: "left" }}>{displayName}</span>
        {selectedId && (
          <span onMouseDown={e => { e.stopPropagation(); onSelect(null); setQuery(""); }}
            style={{ fontSize: 14, color: "var(--tx-3)", lineHeight: 1, padding: "0 2px" }}>×</span>
        )}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
          style={{ color: "var(--tx-3)", transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }}>
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </button>

      {open && ReactDOM.createPortal(
        <div style={{
          position: "fixed",
          top: (() => { const r = ref.current?.getBoundingClientRect(); return (r?.bottom ?? 0) + 6; })(),
          left: (() => { const r = ref.current?.getBoundingClientRect(); return r?.left ?? 0; })(),
          width: Math.max(ref.current?.offsetWidth ?? 0, 320),
          background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14,
          boxShadow: "0 12px 32px rgba(15,23,42,0.16)", zIndex: 9999, overflow: "hidden",
        }}>
          {/* Search input */}
          <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid #f1f5f9" }}>
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by name…"
              style={{
                width: "100%", padding: "6px 10px", borderRadius: 7, border: "1px solid #e2e8f0",
                fontSize: 12.5, outline: "none", fontFamily: "inherit", boxSizing: "border-box" as const,
                color: "#0f172a",
              }}
            />
          </div>
          {/* Options */}
          <div style={{ maxHeight: 360, overflowY: "auto", padding: "6px" }}>
            {/* All Users option */}
            <button onMouseDown={() => { onSelect(null); setOpen(false); setQuery(""); }}
              style={{
                width: "100%", padding: "12px 12px", display: "flex", alignItems: "center", gap: 12,
                background: !selectedId ? "#f5f3ff" : "transparent", borderRadius: 10,
                border: "none", cursor: "pointer", textAlign: "left",
              }}
              onMouseEnter={e => { if (selectedId) e.currentTarget.style.background = "#f8fafc"; }}
              onMouseLeave={e => { if (selectedId) e.currentTarget.style.background = "transparent"; }}
            >
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#6366f1",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#fff", flexShrink: 0 }}>
                All
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>All Users</div>
                <div style={{ fontSize: 11.5, color: "#94a3b8" }}>Aggregate across everyone</div>
              </div>
            </button>
            {filtered.map(u => {
              const name = u.user?.name || u.user?.email || "";
              const isSelected = u.user?.id === selectedId;
              const chip = (bg: string, fg: string, text: string) => (
                <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 6, background: bg, color: fg }}>{text}</span>
              );
              return (
                <button key={u.user?.id}
                  onMouseDown={() => { onSelect(u.user?.id); setOpen(false); setQuery(""); }}
                  style={{
                    width: "100%", padding: "12px 12px", display: "flex", alignItems: "center", gap: 12,
                    background: isSelected ? "#f5f3ff" : "transparent", borderRadius: 10,
                    border: "none", cursor: "pointer", textAlign: "left",
                  }}
                  onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = "#f8fafc"; }}
                  onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = "transparent"; }}
                >
                  <div style={{ width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
                    background: "linear-gradient(135deg,#7c3aed,#6366f1)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "#fff", fontSize: 12.5, fontWeight: 700 }}>
                    {initials(name)}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
                    <div style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginBottom: 6 }}>{u.user?.email}</div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {chip("#eef2ff", "#4f46e5", `${u.tailored_total ?? u.tailored?.length ?? 0} tailored`)}
                      {chip("#ecfdf5", "#059669", `${u.applied_total ?? u.applied?.length ?? 0} applied`)}
                      {chip("#f5f3ff", "#7c3aed", `$${(u.spend_total ?? 0).toFixed(2)}`)}
                    </div>
                  </div>
                </button>
              );
            })}
            {filtered.length === 0 && (
              <div style={{ padding: "24px", fontSize: 13, color: "#94a3b8", textAlign: "center" }}>No users found</div>
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

export function Dashboard({ isAdmin = false }: { isAdmin?: boolean }) {
  const [data, setData]               = useState<any>(null);
  const [reminders, setReminders]     = useState<any[]>([]);
  const [usersData, setUsersData]     = useState<any[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [loading, setLoading]         = useState(true);
  const [monthFilter, setMonthFilter] = useState<string>(""); // "" until defaulted, then "all" or "YYYY-MM"

  // Reminders + per-user list load once.
  useEffect(() => {
    api.getReminders().then(setReminders).catch(() => {});
    if (isAdmin) {
      api.adminUsersAnalytics().then(setUsersData).catch(() => {});
    }
  }, [isAdmin]);

  // Analytics re-fetch whenever the admin picks a different user — the WHOLE
  // dashboard (stat cards, charts, timeline) then reflects that one user.
  useEffect(() => {
    setLoading(true);
    setData(null);
    api.getAnalytics(!isAdmin, isAdmin ? selectedUserId : null)
      .then(setData).catch(console.error).finally(() => setLoading(false));
  }, [isAdmin, selectedUserId]);

  // Default the Daily Activity view to the latest month (full 1st→end), not a
  // cross-month rolling window. Must stay ABOVE the early returns below so hook
  // order is stable. User can still switch to "All months" or any prior month.
  useEffect(() => {
    if (monthFilter) return;
    const tl = data?.timeline || [];
    const keys = (Array.from(new Set(tl.map((d: any) => (d.date || "").slice(0, 7)).filter(Boolean))) as string[]).sort();
    if (keys.length) setMonthFilter(keys[keys.length - 1]);
  }, [data, monthFilter]);

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
  const allUsersTailoredTotal = usersData.reduce((sum: number, u: any) => sum + (u.tailored_total ?? (u.tailored || []).length), 0);
  const allUsersAppliedTotal  = usersData.reduce((sum: number, u: any) => sum + (u.applied_total  ?? (u.applied  || []).length), 0);
  // Aggregate (all-users) totals only when admin AND no specific user picked.
  // With a user selected, `data` is already scoped to them by the backend.
  const aggregate = isAdmin && !selectedUserId;
  const applied = aggregate ? allUsersAppliedTotal : (st["applied"] || 0);
  const interview = st["interview"] || 0;
  const skipped = st["skipped"]   || 0;
  const newJobs = st["new"]       || 0;
  const tailored = aggregate
    ? allUsersTailoredTotal
    : (data.tailored_total ?? (data.tailored_jobs || []).length);

  const today = new Date().toISOString().slice(0, 10);
  const todayEntry = (data.timeline || []).find((d: any) => d.date === today);
  const scrapedToday = todayEntry?.scraped || 0;

  const stats = [
    { label: "Total Scraped", value: total,        delta: "+scraping",  grad: ["#475569","#64748b"] as [string,string] },
    { label: "Scraped Today", value: scrapedToday, delta: "new today",  grad: ["#6366f1","#818cf8"] as [string,string] },
    { label: "Applied",       value: applied,      delta: "+this week", grad: ["#3b82f6","#60a5fa"] as [string,string] },
    { label: "Interviews",    value: interview,    delta: "upcoming",   grad: ["#10b981","#34d399"] as [string,string] },
    { label: "AI Tailored",   value: tailored,     delta: "+this week", grad: ["#7c3aed","#a78bfa"] as [string,string] },
  ];

  // Tailored is a flag a job can carry WHILE still being New/Applied/etc --
  // not a mutually-exclusive status. It was previously listed as a 5th
  // additive slice here, double-counting those jobs and inflating the
  // donut's center total past the real Total Scraped count (2014 vs 1917).
  // It's already shown correctly as its own "AI Tailored" stat card above.
  const statusData = [
    { label: "New",       value: newJobs,   color: "#3b82f6" },
    { label: "Applied",   value: applied,   color: "#10b981" },
    { label: "Interview", value: interview, color: "#f59e0b" },
    { label: "Skipped",   value: skipped,   color: "#64748b" },
  ];

  // Monthly data — drop leading empty months (Mar/Apr/May before any activity)
  // so the bar chart starts at the first month with real data (June onward).
  const _monthlyAll = (data.monthly || []).map((d: any) => ({
    m: d.month || d.m || "",
    scraped: d.scraped || 0,
    applied: d.applied || 0,
    tailored: d.tailored || 0,
  }));
  const _firstMonthIdx = _monthlyAll.findIndex((d: any) => d.scraped > 0 || d.applied > 0 || d.tailored > 0);
  const monthly = _firstMonthIdx > 0 ? _monthlyAll.slice(_firstMonthIdx) : _monthlyAll;

  // 30-day activity — start at the first day with data (no empty left tail)
  const fullTimeline = data.timeline || [];
  const firstDataIdx = fullTimeline.findIndex((d: any) => (d.scraped || 0) > 0 || (d.applied || 0) > 0);
  const timeline = firstDataIdx > 0 && fullTimeline.length - firstDataIdx >= 2
    ? fullTimeline.slice(firstDataIdx)
    : fullTimeline;

  // Month dropdown — derived from whatever months actually appear in the raw
  // (untrimmed) timeline, so picking a month shows that month's full data,
  // not just whatever survived the "trim empty leading days" logic above.
  const _MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const monthKeys = Array.from(new Set(fullTimeline.map((d: any) => (d.date || "").slice(0, 7)).filter(Boolean))) as string[];
  monthKeys.sort();
  const monthOptions = monthKeys.map(key => {
    const [, mm] = key.split("-").map(Number);
    return { key, label: `${_MONTH_NAMES[(mm || 1) - 1]} ${key.slice(0, 4)}` };
  });
  // Month view = the FULL calendar month, day 1 → last day, with missing days
  // zero-filled so the axis always spans e.g. Aug 1–31 (not just days with data).
  const displayTimeline = (monthFilter === "all" || !monthFilter)
    ? timeline
    : (() => {
        const [yy, mm] = monthFilter.split("-").map(Number);
        const daysInMonth = new Date(yy, mm, 0).getDate();  // mm is 1-based → day 0 of next month
        const byDate = new Map(
          fullTimeline.filter((d: any) => (d.date || "").startsWith(monthFilter)).map((d: any) => [d.date, d])
        );
        const full = Array.from({ length: daysInMonth }, (_, i) => {
          const date = `${monthFilter}-${String(i + 1).padStart(2, "0")}`;
          return byDate.get(date) || { date, scraped: 0, applied: 0 };
        });
        // Trim the trailing run of empty days (e.g. future days in the current
        // month that haven't been scraped yet) — keep 1st → last day with data.
        let last = full.length - 1;
        const _has = (d: any) => (d.scraped || 0) > 0 || (d.applied || 0) > 0;
        while (last > 0 && !_has(full[last])) last--;
        return full.slice(0, last + 1);
      })();

  // Source bars
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
  const appliedJobs  = (data.applied_jobs  || []).map((j: any) => ({
    company: j.company, title: j.title, location: j.location || "", exp: j.experience_level || "",
    when: timeAgo(j.applied_at || j.scraped_at), whenFull: _fmtFullDate(j.applied_at || j.scraped_at),
  }));
  const jobTailored = (data.tailored_jobs || []).map((j: any) => ({
    id: j.id, company: j.company, title: j.title, location: j.location || "", exp: j.experience_level || "",
    when: timeAgo(j.tailored_at || j.scraped_at), whenFull: _fmtFullDate(j.tailored_at || j.scraped_at),
    source: "job" as const, tailored_at: j.tailored_at || j.scraped_at || "",
  }));
  const quickTailored = (data.quick_tailored_jobs || []).map((j: any) => ({
    id: j.id, company: j.company, title: "", location: "", exp: "",
    when: timeAgo(j.tailored_at), whenFull: _fmtFullDate(j.tailored_at),
    source: "quick" as const, tailored_at: j.tailored_at || "",
  }));
  const tailoredJobs = [...jobTailored, ...quickTailored]
    .sort((a, b) => (b.tailored_at > a.tailored_at ? 1 : -1));

  // When admin selects a specific user, switch to their data
  const selectedUser = selectedUserId ? usersData.find((u: any) => u.user?.id === selectedUserId) : null;

  const visibleTailored = selectedUser
    ? (selectedUser.tailored || [])
        .map((j: any) => ({
          id: j.id, company: j.company, title: j.title, location: j.location,
          exp: j.experience_level,
          when: timeAgo(j.tailored_at), whenFull: _fmtFullDate(j.tailored_at),
          source: j.source as "job" | "quick", tailored_at: j.tailored_at || "",
          cost: j.tailor_cost, tin: j.tailor_tokens_in, tout: j.tailor_tokens_out,
        }))
        .sort((a: any, b: any) => (b.tailored_at > a.tailored_at ? 1 : -1))
    : tailoredJobs;

  const visibleApplied = selectedUser
    ? (selectedUser.applied || []).map((j: any) => ({
        company: j.company, title: j.title, location: j.location, exp: j.experience_level,
        when: timeAgo(j.applied_at), whenFull: _fmtFullDate(j.applied_at),
      }))
    : appliedJobs;

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
            <p className="dash-sub">
              {isAdmin && selectedUser
                ? `Viewing ${selectedUser.user?.name || selectedUser.user?.email}`
                : isAdmin ? "All users — job search at a glance" : "Your job search at a glance"}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {isAdmin && usersData.length > 0 && (
              <UserPicker users={usersData} selectedId={selectedUserId} onSelect={setSelectedUserId} />
            )}
            <ScrapeStatus lastScrapedAt={data.last_scraped_at} />
          </div>
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

        {/* Chart grid — Row 1: Monthly Trends (2/3) + Status Breakdown (1/3) */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 14, marginBottom: 14 }}>
          <div className="chart-card">
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

          <div className="chart-card" style={{ display: "flex", flexDirection: "column" }}>
            <div className="chart-head"><span className="chart-title">Status Breakdown</span></div>
            {statusData.some(d => d.value > 0)
              ? <>
                  <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
                    <Donut data={statusData.filter(d => d.value > 0)} />
                  </div>
                  <div className="donut-legend">
                    {statusData.map(s => (
                      <span key={s.label}><i style={{ background: s.color }} />{s.label} <b>{s.value}</b></span>
                    ))}
                  </div>
                </>
              : <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No jobs tracked yet</div>
            }
          </div>
        </div>

        {/* Row 2: Daily Activity full width */}
        <div style={{ marginBottom: 14 }}>
          <div className="chart-card">
            <div className="chart-head">
              <span className="chart-title">Daily Activity{monthFilter !== "all" ? ` — ${monthOptions.find(m => m.key === monthFilter)?.label || ""}` : ""}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <div className="legend">
                  <span><i style={{ background: "#7c3aed" }} />Scraped</span>
                  <span><i style={{ background: "#3b82f6" }} />Applications</span>
                </div>
                <select value={monthFilter} onChange={e => setMonthFilter(e.target.value)}
                  style={{ fontSize: 12, padding: "5px 10px", borderRadius: 8, border: "1px solid var(--line)",
                    background: "var(--bg-surface)", color: "var(--tx-2)", cursor: "pointer" }}>
                  <option value="all">All months</option>
                  {monthOptions.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </div>
            </div>
            {displayTimeline.length > 0
              ? <AreaChart scrape={displayTimeline.map((d: any) => d.scraped || 0)} applied={displayTimeline.map((d: any) => d.applied || 0)} points={displayTimeline} />
              : <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No activity data for this period</div>
            }
          </div>
        </div>

        {/* Row 3 (admin only): Jobs by Source — full width, scrolls horizontally.
            Jobs by Country card removed (USA-only now, nothing to compare). */}
        {isAdmin && (
          <div style={{ marginBottom: 14 }}>
            <div className="chart-card">
              <div className="chart-head"><span className="chart-title">Jobs by Source</span></div>
              {bySource.length > 0
                ? <VBars data={bySource} />
                : <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--tx-3)", fontSize: 12 }}>No source data yet</div>
              }
            </div>
          </div>
        )}

        {/* Resume history — with user dropdown for admin */}
        <div className="resume-history">
          <div className="rh-section-head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span>Resume History</span>
            {isAdmin && usersData.length > 0 && (
              <span title={selectedUser ? "This user's total AI tailoring spend" : "All users' total AI tailoring spend"}
                style={{ fontSize: 12.5, fontWeight: 700, padding: "6px 12px", borderRadius: 999,
                  background: "#7c3aed14", color: "#7c3aed" }}>
                AI spend: ${(selectedUser
                  ? (selectedUser.spend_total || 0)
                  : usersData.reduce((s: number, u: any) => s + (u.spend_total || 0), 0)
                ).toFixed(2)}
              </span>
            )}
          </div>
          <div className="rh-cols">
            <ResumeList title="Applied Resumes"  accent="#10b981" items={visibleApplied}  icon="applied"  badge="Applied"  />
            <ResumeList title="Tailored Resumes" accent="#7c3aed" items={visibleTailored} icon="sparkles" badge="Tailored" showDownloads />
          </div>
        </div>

      </div>
    </div>
  );
}
