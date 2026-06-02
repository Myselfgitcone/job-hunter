import { useEffect, useState } from "react";

// ── Company Logo ──────────────────────────────────────────────────────────────

// Module-level cache — survives re-renders, avoids duplicate Clearbit calls
const _domainCache = new Map<string, string>();

async function _resolveDomain(company: string): Promise<string> {
  if (_domainCache.has(company)) return _domainCache.get(company)!;
  try {
    const res = await fetch(
      `https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(company)}`
    );
    if (res.ok) {
      const data: Array<{ name: string; domain: string; logo: string }> = await res.json();
      if (data?.[0]?.domain) {
        _domainCache.set(company, data[0].domain);
        return data[0].domain;
      }
    }
  } catch {}
  // Fallback: strip non-alpha chars from company name and guess .com
  const fallback = `${company.toLowerCase().replace(/[^a-z0-9]/g, "")}.com`;
  _domainCache.set(company, fallback);
  return fallback;
}

function _Initials({ company, size }: { company: string; size: number }) {
  const letter = company.trim()[0]?.toUpperCase() || "?";
  const hue = [...company].reduce((n, c) => n + c.charCodeAt(0), 0) % 360;
  return (
    <div style={{
      width: size, height: size, borderRadius: 5,
      background: `hsl(${hue},48%,42%)`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.52, fontWeight: 700, color: "#fff",
      flexShrink: 0, letterSpacing: "-0.02em",
    }}>{letter}</div>
  );
}

export function CompanyLogo({ url: _url, company, size = 20 }: { url: string; company: string; size?: number }) {
  const [domain, setDomain] = useState<string>(() => _domainCache.get(company) ?? "");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (_domainCache.has(company)) {
      setDomain(_domainCache.get(company)!);
      return;
    }
    _resolveDomain(company).then(setDomain);
  }, [company]);

  if (!domain || failed) return <_Initials company={company} size={size} />;

  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt=""
      width={size}
      height={size}
      style={{ borderRadius: 5, objectFit: "contain", flexShrink: 0 }}
      onError={() => setFailed(true)}
    />
  );
}

// ── Spinner ──────────────────────────────────────────────────────────────────
export function Spinner({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <span
      className="spinner"
      style={{ width: size, height: size, borderColor: `${color}40`, borderTopColor: color }}
    />
  );
}

// ── ATS Bar ──────────────────────────────────────────────────────────────────
export function ATSBar({
  score, height = 4, showPct = false, color = "var(--accent)",
}: { score: number; height?: number; showPct?: boolean; color?: string }) {
  const [w, setW] = useState(0);
  useEffect(() => { const t = setTimeout(() => setW(score), 60); return () => clearTimeout(t); }, [score]);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
      <div style={{ flex: 1, height, background: "rgba(255,255,255,0.08)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 999, transition: "width 500ms cubic-bezier(.4,0,.2,1)" }} />
      </div>
      {showPct && (
        <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", minWidth: 30, textAlign: "right" }}>
          {score}%
        </span>
      )}
    </div>
  );
}

// ── Gauge Ring ────────────────────────────────────────────────────────────────
export function GaugeRing({ score, pass, size = 132 }: { score: number; pass: boolean; size?: number }) {
  const r = (size - 16) / 2;
  const c = 2 * Math.PI * r;
  const [draw, setDraw] = useState(0);
  useEffect(() => { const t = setTimeout(() => setDraw(score), 80); return () => clearTimeout(t); }, [score]);
  const color = pass ? "#22c55e" : "#ef4444";
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color}
          strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (draw / 100) * c}
          style={{ transition: "stroke-dashoffset 800ms cubic-bezier(.4,0,.2,1)", filter: `drop-shadow(0 0 6px ${color}55)` }}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
          {score}<span style={{ fontSize: 16, color: "var(--text-secondary)" }}>%</span>
        </div>
        <div style={{ fontSize: 11, fontWeight: 600, color, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {pass ? "Qualified" : "Not Qualified"}
        </div>
      </div>
    </div>
  );
}

// ── Toast system ──────────────────────────────────────────────────────────────
export interface ToastItem { id: number; msg: string; type: "success" | "error"; }

export function Toasts({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.type === "success" ? "✓" : "✕"} {t.msg}
        </div>
      ))}
    </div>
  );
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toast = (msg: string, type: "success" | "error" = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3000);
  };
  return { toasts, toast };
}

// ── Source color helper ───────────────────────────────────────────────────────
export function srcColor(source: string): string {
  const map: Record<string, string> = {
    Greenhouse: "#4ade80", Lever: "#34d399", Ashby: "#22d3ee",
    Workday: "#a78bfa", BambooHR: "#fb923c", Recruitee: "#f472b6",
    HiringCafe: "#facc15", Google: "#60a5fa", Apple: "#94a3b8",
    Meta: "#818cf8", Netflix: "#ef4444",
  };
  return map[source] || "var(--text-muted)";
}
