import { useEffect, useState } from "react";

// ── Company Logo ──────────────────────────────────────────────────────────────

// Module-level cache — survives re-renders, avoids duplicate Clearbit calls
const _domainCache = new Map<string, string>();

// Known domain overrides — saves a network call for very common companies
const KNOWN_DOMAINS: Record<string, string> = {
  "nvidia": "nvidia.com", "google": "google.com", "apple": "apple.com",
  "meta": "meta.com", "microsoft": "microsoft.com", "amazon": "amazon.com",
  "netflix": "netflix.com", "tesla": "tesla.com", "stripe": "stripe.com",
  "openai": "openai.com", "anthropic": "anthropic.com", "uber": "uber.com",
  "airbnb": "airbnb.com", "linkedin": "linkedin.com", "salesforce": "salesforce.com",
  "adobe": "adobe.com", "intel": "intel.com", "cisco": "cisco.com",
  "oracle": "oracle.com", "ibm": "ibm.com", "sap": "sap.com",
  "jpmorgan chase": "jpmorganchase.com", "goldman sachs": "goldmansachs.com",
  "morgan stanley": "morganstanley.com", "wells fargo": "wellsfargo.com",
  "bank of america": "bankofamerica.com", "deloitte": "deloitte.com",
  "mckinsey": "mckinsey.com", "accenture": "accenture.com",
  "servicenow": "servicenow.com", "workday": "workday.com",
  "snowflake": "snowflake.com", "databricks": "databricks.com",
  "palantir": "palantir.com", "coinbase": "coinbase.com",
  "qualcomm": "qualcomm.com", "broadcom": "broadcom.com",
  "lam research": "lamresearch.com", "applied materials": "appliedmaterials.com",
  "general motors": "gm.com", "ford": "ford.com", "boeing": "boeing.com",
  "lockheed martin": "lockheedmartin.com", "jpmorgan": "jpmorganchase.com",
};

// Extract company domain directly from the ATS job URL — most reliable source
function extractDomainFromUrl(url: string): string | null {
  if (!url) return null;
  try {
    // Greenhouse: boards.greenhouse.io/{slug}/jobs/...
    const gh = url.match(/boards\.greenhouse\.io\/([^/?#]+)/);
    if (gh) return `${gh[1]}.com`;

    // Lever: jobs.lever.co/{slug}/...
    const lv = url.match(/jobs\.lever\.co\/([^/?#]+)/);
    if (lv) return `${lv[1]}.com`;

    // Ashby: jobs.ashbyhq.com/{slug}/...
    const ash = url.match(/(?:jobs\.)?ashbyhq\.com\/([^/?#]+)/);
    if (ash) return `${ash[1]}.com`;

    // Workday: {slug}.wd1/wd5.myworkdayjobs.com/...
    const wd = url.match(/([^.]+)\.wd\d+\.myworkdayjobs\.com/);
    if (wd) return `${wd[1]}.com`;

    // Bamboo: {slug}.bamboohr.com
    const bh = url.match(/([^.]+)\.bamboohr\.com/);
    if (bh) return `${bh[1]}.com`;

    // SmartRecruiters: jobs.smartrecruiters.com/{CompanyName}
    const sr = url.match(/jobs\.smartrecruiters\.com\/([^/?#]+)/);
    if (sr) return `${sr[1].toLowerCase()}.com`;
  } catch {}
  return null;
}

async function _resolveDomain(url: string, company: string): Promise<string> {
  const cacheKey = url || company;
  if (_domainCache.has(cacheKey)) return _domainCache.get(cacheKey)!;

  // Step 1: Extract from URL — most reliable, instant, no network
  const fromUrl = extractDomainFromUrl(url);
  if (fromUrl) {
    _domainCache.set(cacheKey, fromUrl);
    return fromUrl;
  }

  // Step 2: Known company → domain map (instant, no network)
  const key = company.toLowerCase().trim();
  for (const [k, domain] of Object.entries(KNOWN_DOMAINS)) {
    if (key.includes(k)) {
      _domainCache.set(cacheKey, domain);
      return domain;
    }
  }

  // Step 3: Clearbit autocomplete (network, but accurate for well-known companies)
  try {
    const res = await fetch(
      `https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(company)}`
    );
    if (res.ok) {
      const data: Array<{ name: string; domain: string; logo: string }> = await res.json();
      // Only use if name roughly matches to avoid wrong company logos
      if (data?.[0]?.domain) {
        const returned = data[0].name.toLowerCase();
        const asked    = company.toLowerCase();
        const isMatch  = returned.includes(asked.split(" ")[0]) || asked.includes(returned.split(" ")[0]);
        if (isMatch) {
          _domainCache.set(cacheKey, data[0].domain);
          return data[0].domain;
        }
      }
    }
  } catch {}

  // Step 4: Fallback to initials (don't guess domain for obscure companies)
  _domainCache.set(cacheKey, "");
  return "";
}

function _Initials({ company, size }: { company: string; size: number }) {
  const words = company.trim().split(/\s+/);
  const letters = words.length >= 2
    ? (words[0][0] + words[1][0]).toUpperCase()
    : (company.trim().slice(0, 2)).toUpperCase();
  const hue = [...company].reduce((n, c) => n + c.charCodeAt(0), 0) % 360;
  return (
    <div style={{
      width: size, height: size, borderRadius: 7,
      background: `linear-gradient(135deg, hsl(${hue},52%,38%), hsl(${hue},48%,28%))`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.42, fontWeight: 700, color: "#fff",
      flexShrink: 0, letterSpacing: "-0.01em",
      border: "1px solid rgba(255,255,255,0.08)",
    }}>{letters}</div>
  );
}

export function CompanyLogo({ url, company, size = 28 }: { url: string; company: string; size?: number }) {
  const cacheKey = url || company;
  const [domain, setDomain] = useState<string>(() => _domainCache.get(cacheKey) ?? "");
  const [stage, setStage] = useState<"clearbit" | "favicon" | "initials">("clearbit");

  useEffect(() => {
    setStage("clearbit");
    if (_domainCache.has(cacheKey)) {
      setDomain(_domainCache.get(cacheKey)!);
      return;
    }
    _resolveDomain(url, company).then(setDomain);
  }, [cacheKey]);

  if (!domain || stage === "initials") return <_Initials company={company} size={size} />;

  // Tier 1: Clearbit hi-res logo (128×128 PNG, proper brand logo)
  if (stage === "clearbit") {
    return (
      <img
        src={`https://logo.clearbit.com/${domain}`}
        alt={company}
        width={size}
        height={size}
        style={{ borderRadius: 7, objectFit: "contain", flexShrink: 0, background: "#fff", padding: 1 }}
        onError={() => setStage("favicon")}
      />
    );
  }

  // Tier 2: Google favicon (fallback)
  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt=""
      width={size}
      height={size}
      style={{ borderRadius: 7, objectFit: "contain", flexShrink: 0 }}
      onError={() => setStage("initials")}
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

// ── Icon component ────────────────────────────────────────────────────────────
const ICON_PATHS: Record<string, string> = {
  search:       '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  briefcase:    '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
  dashboard:    '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  user:         '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 14 0v1"/>',
  sparkles:     '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/>',
  settings:     '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
  mapPin:       '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
  clock:        '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check:        '<path d="M20 6 9 17l-5-5"/>',
  checkCircle:  '<circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/>',
  xCircle:      '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  x:            '<path d="M18 6 6 18M6 6l12 12"/>',
  chevronDown:  '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  plus:         '<path d="M12 5v14M5 12h14"/>',
  externalLink: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  star:         '<path d="m12 3 2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.2l1-5.9L3.5 9.2l5.9-.8z"/>',
  download:     '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M5 21h14"/>',
  copy:         '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  calendar:     '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  zap:          '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  alert:        '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  target:       '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  waves:        '<path d="M2 8c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/><path d="M2 14c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2"/>',
  refresh:      '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  trash:        '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
  list:         '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
  kanban:       '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="11" rx="1"/><rect x="17" y="4" width="4" height="14" rx="1"/>',
  eye:          '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  fileText:     '<path d="M14 3v5h5"/><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M8 13h8M8 17h6"/>',
  award:        '<circle cx="12" cy="9" r="6"/><path d="M9 14.5 8 22l4-2 4 2-1-7.5"/>',
  phone:        '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  mail:         '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  grip:         '<circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/>',
};

export function Icon({
  name, size = 16, color, style, strokeWidth = 2,
}: {
  name: string; size?: number; color?: string;
  style?: React.CSSProperties; strokeWidth?: number;
}) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke={color || "currentColor"}
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }}
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] || "" }}
    />
  );
}

// ── Source color helper ───────────────────────────────────────────────────────
export function srcColor(source: string): string {
  const map: Record<string, string> = {
    Greenhouse: "#22c55e", Lever:  "#10b981", Ashby:  "#8b5cf6",
    HiringCafe: "#ec4899", Google: "#3b82f6", Apple:  "#94a3b8",
    Meta:       "#0ea5e9", Netflix:"#ef4444", Workday:"#f59e0b",
    BambooHR:   "#84cc16", Recruitee:"#ec4899",
  };
  return map[source] || "var(--text-secondary)";
}
