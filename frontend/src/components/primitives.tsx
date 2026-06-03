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

// ── Source color helper ───────────────────────────────────────────────────────
export function srcColor(source: string): string {
  const map: Record<string, string> = {
    Greenhouse: "#16a34a", Lever:  "#059669", Ashby:  "#0891b2",
    HiringCafe: "#b45309", Google: "#2563eb", Apple:  "#475569",
    Meta:       "#4f46e5", Netflix:"#dc2626", Workday:"#7c3aed",
    BambooHR:   "#c2410c", Recruitee:"#be185d",
  };
  return map[source] || "var(--text-secondary)";
}
