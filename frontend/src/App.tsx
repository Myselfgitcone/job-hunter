import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import type { Job, JobStatus, QualifyResult } from "./types";
import { api } from "./api";
import { checkVisa } from "./utils/visaCheck";
import { isLevelMatch } from "./utils/levelCheck";
import { JobCard } from "./components/JobCard";
import { JobList } from "./components/JobList";
import { Dashboard } from "./components/Dashboard";
import { Kanban } from "./components/Kanban";
import { QuickTailor } from "./components/QuickTailor";
import { Profile } from "./components/Profile";
import { Settings } from "./components/Settings";
import { JobDetail } from "./components/JobDetail";
import { Toasts, useToasts, Spinner } from "./components/primitives";
import { Auth } from "./components/Auth";
import { Onboarding } from "./components/Onboarding";

type View = "jobs" | "dashboard" | "profile" | "settings";
type ViewMode = "list" | "kanban";
type Filters = { posted: string; countries: string[]; locTypes: string[]; sources: string[]; status: string; role: string; exps: string[]; categories: string[]; };

// SOURCES and COUNTRIES are now dynamic — built from actual jobs (see useMemo below)
// SOURCES is now dynamic — built from actual jobs (see useMemo below)
const STATUS_ROWS = [
  { id: "all",       label: "All",       color: "var(--st-new)" },
  { id: "new",       label: "New",       color: "var(--st-new)" },
  { id: "applied",   label: "Applied",   color: "var(--st-applied)" },
  { id: "interview", label: "Interview", color: "var(--st-interview)" },
  { id: "skipped",   label: "Skipped",   color: "#5b6377" },
];

function Ic({ d, size = 16, color, style }: { d: string; size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}

const IC: Record<string,string> = {
  target:   "<circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"5\"/><circle cx=\"12\" cy=\"12\" r=\"1\"/>",
  dash:     "<rect x=\"3\" y=\"3\" width=\"7\" height=\"9\" rx=\"1\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"5\" rx=\"1\"/><rect x=\"14\" y=\"12\" width=\"7\" height=\"9\" rx=\"1\"/><rect x=\"3\" y=\"16\" width=\"7\" height=\"5\" rx=\"1\"/>",
  user:     "<circle cx=\"12\" cy=\"8\" r=\"4\"/><path d=\"M4 21v-1a7 7 0 0 1 14 0v1\"/>",
  settings: "<circle cx=\"12\" cy=\"12\" r=\"3\"/>",
  sparkles: "<path d=\"M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z\"/>",
  refresh:  "<path d=\"M21 12a9 9 0 1 1-3-6.7L21 8\"/><path d=\"M21 3v5h-5\"/>",
  clock:    "<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 7v5l3 2\"/>",
  list:     "<path d=\"M8 6h13M8 12h13M8 18h13\"/><circle cx=\"3.5\" cy=\"6\" r=\"1\"/><circle cx=\"3.5\" cy=\"12\" r=\"1\"/><circle cx=\"3.5\" cy=\"18\" r=\"1\"/>",
  kanban:   "<rect x=\"3\" y=\"4\" width=\"5\" height=\"16\" rx=\"1\"/><rect x=\"10\" y=\"4\" width=\"5\" height=\"11\" rx=\"1\"/><rect x=\"17\" y=\"4\" width=\"4\" height=\"14\" rx=\"1\"/>",
  search:   "<circle cx=\"11\" cy=\"11\" r=\"7\"/><path d=\"m21 21-4.3-4.3\"/>",
  trash:    "<path d=\"M4 7h16\"/><path d=\"M9 7V5h6v2\"/><path d=\"M6 7l1 13h10l1-13\"/>",
};

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return m + "m ago";
    const h = Math.floor(m / 60);
    if (h < 24) return h + "h ago";
    return Math.floor(h / 24) + "d ago";
  } catch { return ""; }
}

export default function App() {
  // ── Auth state ────────────────────────────────────────────────────────────
  const _storedUser = localStorage.getItem("jh_user");
  const [currentUser, setCurrentUser] = useState<{ id: string; email: string; name: string } | null>(
    _storedUser ? JSON.parse(_storedUser) : null
  );
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem("jh_token"));
  const [showOnboarding, setShowOnboarding]   = useState(false);
  const [userSettings, setUserSettings]       = useState<any>(null);

  const [view, setView]             = useState<View>("jobs");
  const [viewMode, setViewMode]     = useState<ViewMode>("list");
  const [jobs, setJobs]             = useState<Job[]>([]);
  const [allJobs, setAllJobs]       = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab]               = useState("description");
  const [search, setSearch]         = useState("");
  const [loading, setLoading]       = useState(false);
  const [scraping, setScraping]     = useState(false);
  const [scrapeMsg, setScrapeMsg]   = useState("");
  const [lastScrapedTs, setLastScrapedTs] = useState<string>("");
  const [lastScrapedDisplay, setLastScrapedDisplay] = useState("");

  // Live-update "X min ago" every 30s
  useEffect(() => {
    if (!lastScrapedTs) return;
    const update = () => setLastScrapedDisplay(timeAgo(lastScrapedTs));
    update();
    const iv = setInterval(update, 30000);
    return () => clearInterval(iv);
  }, [lastScrapedTs]);

  // Load user settings on auth
  useEffect(() => {
    if (!isAuthenticated) return;
    api.getSettings().then((s: any) => {
      setUserSettings(s);
      if (s.last_scraped_at) setLastScrapedTs(s.last_scraped_at);
    }).catch(() => {});
  }, [isAuthenticated]);

  const [tailorOpen, setTailorOpen] = useState(false);
  const [busy, setBusy]             = useState<string | null>(null);
  const [showWelcome, setShowWelcome] = useState(() => !localStorage.getItem("jh_welcomed"));
  const { toasts, toast }           = useToasts();
  const searchRef                   = useRef<HTMLInputElement>(null);

  // Dynamic user display from auth
  const profileName = currentUser?.name || userSettings?.profile_name || "";
  const initials    = profileName
    ? profileName.split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  const handleLogout = () => {
    localStorage.removeItem("jh_token");
    localStorage.removeItem("jh_user");
    setIsAuthenticated(false);
    setCurrentUser(null);
    setUserSettings(null);
    setJobs([]); setAllJobs([]);
  };

  const [filters, setFilters] = useState<Filters>({
    posted: "72h", countries: [], locTypes: [], sources: [], status: "all", role: "", exps: [], categories: [],
  });
  const [myRolesOnly, setMyRolesOnly] = useState(true);

  const setF = (k: "posted" | "status" | "role", v: string) => setFilters(f => ({ ...f, [k]: v }));
  const toggleArr = (k: "categories"|"exps"|"locTypes"|"countries"|"sources", val: string) =>
    setFilters(f => ({
      ...f,
      [k]: (f[k] as string[]).includes(val)
        ? (f[k] as string[]).filter(v => v !== val)
        : [...(f[k] as string[]), val],
    }));

  // ── Theme toggle ──────────────────────────────────────────────────────────
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem("jh_theme");
    return saved ? saved === "dark" : true; // default dark
  });
  useEffect(() => {
    document.documentElement.classList.toggle("light", !isDark);
    localStorage.setItem("jh_theme", isDark ? "dark" : "light");
  }, [isDark]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setView("jobs"); setViewMode("list");
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, []);

  // Visa / level filters — opt-in based on user's own settings
  const filterJob = useCallback((j: Job) => {
    if (userSettings?.visa_filter  && !checkVisa(j.title + " " + (j.description || "")).eligible) return false;
    if (userSettings?.level_filter && !isLevelMatch(j.title)) return false;
    return true;
  }, [userSettings]);

  const loadJobs = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try { const raw = await api.getJobs(); const f = raw.filter(filterJob); setJobs(f); setAllJobs(f); }
    catch {} finally { setLoading(false); }
  }, [filterJob, isAuthenticated]);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  const statusCounts = useMemo(() => {
    const c: Record<string, number> = { all: allJobs.length, new: 0, applied: 0, interview: 0, skipped: 0 };
    allJobs.forEach(j => { if (c[j.status] !== undefined) c[j.status]++; });
    return c;
  }, [allJobs]);

  const sourceCounts = useMemo(() => {
    const m: Record<string, number> = {};
    allJobs.forEach(j => { m[j.source] = (m[j.source] || 0) + 1; });
    return m;
  }, [allJobs]);

  // Dynamic source list — sorted by count, only sources that have jobs
  const SOURCES = useMemo(() => {
    const srcs = Object.entries(sourceCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([src]) => src);
    return ["All Sources", ...srcs];
  }, [sourceCounts]);

  // Dynamic country list — built from actual job data
  const COUNTRIES = useMemo(() => {
    const counts: Record<string, number> = {};
    allJobs.forEach(j => { if (j.country) counts[j.country] = (counts[j.country] || 0) + 1; });
    const countries = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => c);
    return ["All Countries", ...countries];
  }, [allJobs]);

  const filteredJobs = useMemo(() => {
    const now = Date.now();
    // Add 6h grace buffer so "48h" catches jobs posted ~2 days ago
    // (Workday/scrapers may record post time hours before we scrape it)
    const GRACE = 6 * 3600000; // 6 hours
    const postedCutoff: Record<string, number> = {
      "24h": 24*3600000 + GRACE,
      "48h": 48*3600000 + GRACE,
      "72h": 72*3600000 + GRACE,
      "7d":  7*24*3600000 + GRACE,
    };
    const cutoffMs = postedCutoff[filters.posted] ?? Infinity;

    // Robust ISO parse — strips microseconds Python adds (e.g. .123456 → .123)
    const parseMs = (s: string): number | null => {
      if (!s) return null;
      const clean = s.replace(/(\.\d{3})\d+/, "$1");  // trim sub-ms digits
      const t = new Date(clean).getTime();
      return isNaN(t) ? null : t;
    };

    const CAT_TERMS: Record<string, string[]> = {
      Engineering: ["engineer","developer","devops","sre","platform","infrastructure","backend","frontend","fullstack"],
      Data:        ["data","analytics","analyst","scientist","ml","machine learning","ai","etl","pipeline","bi"],
      Product:     ["product manager","pm","product owner","program manager"],
      Design:      ["design","ux","ui","figma","creative"],
    };

    return jobs.filter(j => {
      // My Roles filter — only show jobs matching user's configured roles
      if (myRolesOnly && userSettings?.job_roles?.length) {
        const roles: string[] = Array.isArray(userSettings.job_roles)
          ? userSettings.job_roles
          : JSON.parse(userSettings.job_roles || '[]');
        if (roles.length > 0) {
          const title = j.title.toLowerCase();
          const matched = roles.some((r: string) =>
            title.includes(r.toLowerCase().split(' ')[0]) ||
            title.includes(r.toLowerCase())
          );
          if (!matched) return false;
        }
      }
      // Categories (multi-select — empty = all)
      if (filters.categories.length > 0) {
        const terms = filters.categories.flatMap(c => CAT_TERMS[c] || []);
        if (!terms.some(t => j.title.toLowerCase().includes(t))) return false;
      }
      if (filters.role.trim()) {
        if (!j.title.toLowerCase().includes(filters.role.toLowerCase())) return false;
      }
      // Exp levels (multi-select)
      if (filters.exps.length > 0) {
        const t = j.title.toLowerCase();
        const EXP: Record<string,RegExp> = {
          Entry:  /(entry|junior|jr\.?|associate|intern)/i,
          Mid:    /(mid|\bii\b|\b2\b|intermediate)/i,
          Senior: /(senior|sr\.?|lead|principal|staff)/i,
          Lead:   /(lead|principal|staff|director)/i,
        };
        if (!filters.exps.some(e => EXP[e]?.test(t))) return false;
      }
      if (filters.status !== "all" && j.status !== filters.status) return false;
      // Countries (multi-select)
      if (filters.countries.length > 0 && !filters.countries.includes(j.country || "")) return false;
      // Work type (multi-select)
      if (filters.locTypes.length > 0) {
        const isRemote = j.remote || (j.location || "").toLowerCase().includes("remote");
        const matchRemote = filters.locTypes.includes("Remote") && isRemote;
        const matchOnsite = filters.locTypes.includes("Onsite") && !isRemote;
        const matchHybrid = filters.locTypes.includes("Hybrid") && (j.location || "").toLowerCase().includes("hybrid");
        if (!matchRemote && !matchOnsite && !matchHybrid) return false;
      }
      // Sources (multi-select)
      if (filters.sources.length > 0 && !filters.sources.includes(j.source)) return false;
      // Time filter — posted_at first (actual job post date), scraped_at as fallback
      if (cutoffMs !== Infinity) {
        const t = parseMs(j.posted_at) ?? parseMs(j.scraped_at);
        if (t !== null && now - t > cutoffMs) return false;
        // if both null (no date at all), let job through
      }
      if (search.trim()) { const q = search.toLowerCase(); if (!j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false; }
      return true;
    });
  }, [jobs, filters, search]);

  const selectedJob = jobs.find(j => j.id === selectedId) || null;

  useEffect(() => {
    if (viewMode === "list" && filteredJobs.length && !filteredJobs.find(j => j.id === selectedId))
      setSelectedId(filteredJobs[0].id);
  }, [filteredJobs, viewMode, selectedId]);

  const updateJob = (id: string, patch: Partial<Job>) =>
    setJobs(js => js.map(j => j.id === id ? { ...j, ...patch } : j));

  const handleScrape = async () => {
    if (scraping) return; setScraping(true); setScrapeMsg("");
    try {
      const r = await api.scrape();
      setScrapeMsg("+" + r.new_jobs + " new"); setLastScrapedTs(new Date().toISOString()); setLastScrapedDisplay("just now");
      await loadJobs(); toast("Found " + r.new_jobs + " new jobs", "success");
    } catch (e: any) { setScrapeMsg(e.message); toast(e.message, "error"); }
    finally { setScraping(false); }
  };

  const handleClearAll = async () => {
    if (!confirm("Delete ALL jobs? Cannot be undone.")) return;
    try { const r = await api.clearAllJobs(); setJobs([]); setAllJobs([]); setSelectedId(null); toast("Cleared " + r.deleted + " jobs", "success"); }
    catch (e: any) { toast(e.message, "error"); }
  };

  // Resets only filters — does NOT delete any jobs
  const handleResetFilters = () => {
    setFilters({ posted: "72h", countries: [], locTypes: [], sources: [], status: "all", role: "", exps: [], categories: [] });
    setSearch("");
    setMyRolesOnly(true);
  };

  const handleStatusChange = async (id: string, status: JobStatus) => {
    await api.setStatus(id, status); updateJob(id, { status }); toast("Moved to " + status, "success");
  };

  const refreshJob = async (id: string) => {
    try { const updated = await api.getJob(id); updateJob(id, updated); } catch {}
  };

  const runAction = async (action: string) => {
    if (!selectedJob || busy) return; setBusy(action);
    try {
      if (action === "qualify") {
        const r = await api.qualifyJob(selectedJob.id);
        updateJob(selectedJob.id, { qualify_result: r });
        toast("Qualification complete", "success");
      } else if (action === "resume") {
        const r = await api.tailor(selectedJob.id);
        updateJob(selectedJob.id, {
          tailored_resume: r.tailored_resume,
          ats_score_before: r.ats_before?.score ?? null,
          ats_score_after:  r.ats_after?.score ?? null,
          ats_keywords_matched: r.ats_after?.matched ?? [],
          ats_keywords_missing: r.ats_after?.missing ?? [],
        });
        toast("Resume tailored", "success");
      } else if (action === "fit") {
        const r = await api.tailor(selectedJob.id);
        updateJob(selectedJob.id, { fit_analysis: r.fit_analysis, interview_tips: r.interview_tips });
        toast("Fit analysis ready", "success");
      } else if (action === "cover") {
        const r = await api.generateCoverLetter(selectedJob.id);
        updateJob(selectedJob.id, { cover_letter: r.cover_letter });
        toast("Cover letter generated", "success");
      }
      await refreshJob(selectedJob.id);
    } catch (e: any) { toast(e.message || "Failed", "error"); }
    finally { setBusy(null); }
  };

  const handleSelect = (id: string) => { setSelectedId(id); setTab("description"); };
  // Expose nav to Settings component for "Go to Profile" link
  useEffect(() => { (window as any).__navToProfile = () => setView("profile"); }, []);
  const handleNav = (v: string) => { if (v === "tailor") { setTailorOpen(true); return; } setView(v as View); };
  const filtersActive = filters.posted !== "72h" || filters.countries.length > 0 || filters.locTypes.length > 0 || filters.sources.length > 0 || filters.status !== "all" || filters.role !== "" || filters.exps.length > 0 || filters.categories.length > 0 || search.trim() !== "";
  const navItems = [
    { id: "jobs", label: "Jobs", ic: IC.search },
    { id: "dashboard", label: "Dashboard", ic: IC.dash },
    { id: "profile", label: "My Profile", ic: IC.user },
    { id: "settings", label: "Settings", ic: IC.settings },
  ];

  // ── Auth gate ────────────────────────────────────────────────────────────
  if (!isAuthenticated) {
    return <Auth onSuccess={(user) => {
      setCurrentUser(user);
      setIsAuthenticated(true);
      // Check if new user → show onboarding
      api.getSettings().then((s: any) => {
        setUserSettings(s);
        if (!s.resume && !s.profile_name) setShowOnboarding(true);
      }).catch(() => setShowOnboarding(true));
    }} />;
  }

  if (showOnboarding && currentUser) {
    return <Onboarding
      user={currentUser}
      onComplete={() => {
        setShowOnboarding(false);
        api.getSettings().then((s: any) => setUserSettings(s)).catch(() => {});
        loadJobs();
      }}
    />;
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <aside style={{ width: 208, flexShrink: 0, background: "var(--bg-surface)", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", height: "100%" }}>
        <div style={{ height: 62, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, borderBottom: "1px solid var(--border-subtle)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <circle cx="11" cy="11" r="8.5" stroke="#3b82f6" strokeWidth="2.2"/>
              <circle cx="11" cy="11" r="2.8" fill="#3b82f6"/>
            </svg>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.01em" }}>
              <span style={{ color: "var(--text-primary)" }}>Job </span>
              <span style={{ color: "#3b82f6" }}>Hunter</span>
            </div>
          </div>
          <div style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Hunt Smarter, Not Harder</div>
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 2, padding: "10px 10px 8px" }}>
          {navItems.map(n => {
            const active = view === n.id;
            return (
              <button key={n.id} onClick={() => handleNav(n.id)} className="nav-item"
                style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, height: 36, padding: "0 12px", borderRadius: 8, fontSize: 13, fontWeight: 500, textAlign: "left", width: "100%", color: active ? "var(--text-primary)" : "var(--text-secondary)", background: active ? "var(--bg-selected)" : "transparent", transition: "all 120ms ease" }}>
                {active && <span style={{ position: "absolute", left: 0, top: 7, bottom: 7, width: 2, borderRadius: 999, background: "var(--accent)" }} />}
                <Ic d={n.ic} size={16} color={active ? "var(--accent)" : "var(--text-muted)"} />
                {n.label}
              </button>
            );
          })}
          <button onClick={() => setTailorOpen(true)} className="nav-item"
            style={{ display: "flex", alignItems: "center", gap: 10, height: 36, padding: "0 12px", borderRadius: 8, fontSize: 13, fontWeight: 500, textAlign: "left", width: "100%", color: "var(--purple)", background: "transparent", transition: "all 120ms ease" }}>
            <Ic d={IC.sparkles} size={16} color="var(--purple)" /> Quick Tailor
          </button>
        </nav>
        <div style={{ flex: 1 }} />
        <div style={{ flexShrink: 0, padding: "10px 12px", borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{ width: 26, height: 26, borderRadius: 999, background: "linear-gradient(135deg,#8b5cf6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#fff", flexShrink: 0 }}>{initials}</div>
          <div style={{ lineHeight: 1.2, overflow: "hidden", flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{profileName.split(" ")[0] || currentUser?.email?.split("@")[0] || "User"}</div>
            <div style={{ fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{userSettings?.profile_visa || "Job Hunter"}</div>
          </div>
          <button
            onClick={() => setIsDark(d => !d)}
            title={isDark ? "Switch to Light" : "Switch to Dark"}
            style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)", transition: "all 120ms ease", fontSize: 13 }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-elevated)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; }}
          >
            {isDark ? "☀️" : "🌙"}
          </button>
          <button
            onClick={handleLogout}
            title="Sign out"
            style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)", transition: "all 120ms ease", fontSize: 13 }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(239,68,68,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "#f87171"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border-subtle)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; }}
          >⏻</button>
        </div>
      </aside>

      {view === "dashboard" && <div style={{ flex: 1, overflow: "hidden" }}><Dashboard /></div>}
      {view === "profile"   && <div style={{ flex: 1, overflowY: "auto" }}><Profile /></div>}
      {view === "settings"  && <div style={{ flex: 1, overflowY: "auto" }}><Settings /></div>}

      {view === "jobs" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
          {/* Full-width top bar: scrape + filters */}
          <Topbar
            scraping={scraping} scrapeMsg={scrapeMsg} lastScraped={lastScrapedDisplay}
            onScrape={handleScrape} count={filteredJobs.length}
            viewMode={viewMode} setViewMode={setViewMode} IC={IC}
            filters={filters} setF={setF} toggleArr={toggleArr}
            SOURCES={SOURCES.filter(s => s !== "All Sources")}
            COUNTRIES={COUNTRIES.filter(c => c !== "All Countries")}
            allJobs={allJobs} sourceCounts={sourceCounts}
            filtersActive={filtersActive} search={search} setSearch={setSearch}
            searchRef={searchRef} onClearAll={handleResetFilters}
            myRolesOnly={myRolesOnly} setMyRolesOnly={setMyRolesOnly}
            userRoles={Array.isArray(userSettings?.job_roles) ? userSettings.job_roles : JSON.parse(userSettings?.job_roles || '[]')}
          />
          {/* Content row */}
          {viewMode === "kanban" ? (
            <Kanban jobs={filteredJobs} onStatusChange={(id, s) => handleStatusChange(id, s as JobStatus)} onSelect={id => { setViewMode("list"); handleSelect(id); }} />
          ) : (
            <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
              <section style={{ width: 370, flexShrink: 0, background: "var(--bg-base)", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", height: "100%" }}>
                <div style={{ flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 14px", borderBottom: "1px solid var(--border-subtle)" }}>
                  <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{filteredJobs.length} jobs</span>
                  <button onClick={handleClearAll} className="btn btn-ghost btn-danger" style={{ height: 24, padding: "0 8px", fontSize: 11, border: "none" }}><Ic d={IC.trash} size={12} /> Clear All</button>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                  {loading ? (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "40%", gap: 10, color: "var(--text-muted)" }}><Spinner size={18} /> Loading...</div>
                  ) : (
                    <JobList
                      jobs={filteredJobs}
                      selectedId={selectedId}
                      onSelect={handleSelect}
                      onQualifyUpdated={(id, r) => updateJob(id, { qualify_result: r })}
                      emptyState={allJobs.length === 0 ? "Click Scrape Now to fetch jobs" : "Try clearing filters"}
                    />
                  )}
                </div>
              </section>
              <JobDetail job={selectedJob} tab={tab} setTab={setTab} onUpdate={(patch: Partial<Job>) => selectedJob && updateJob(selectedJob.id, patch)} onToast={toast} busy={busy} runAction={runAction} />
            </div>
          )}
        </div>
      )}

      <QuickTailor open={tailorOpen} onClose={() => setTailorOpen(false)} onToast={toast} />
      <Toasts toasts={toasts} />

      {/* Welcome modal — first time only */}
      {showWelcome && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 16, padding: "36px 40px", maxWidth: 520, width: "100%", boxShadow: "0 24px 80px rgba(0,0,0,0.5)" }}>
            {/* Logo + title */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
              <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
                <circle cx="22" cy="22" r="17" stroke="#3b82f6" strokeWidth="3.5"/>
                <circle cx="22" cy="22" r="5.5" fill="#3b82f6"/>
              </svg>
              <div>
                <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em" }}>
                  <span style={{ color: "var(--text-primary)" }}>Welcome to Job </span>
                  <span style={{ color: "#3b82f6" }}>Hunter</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>Your AI-powered job search assistant</div>
              </div>
            </div>

            {/* Steps */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 28 }}>
              {[
                { step: "1", icon: IC.settings, color: "#60a5fa", title: "Add your AI API key", desc: "Settings → pick OpenRouter, Nvidia NIM, or Anthropic → paste your key. Required for all AI features." },
                { step: "2", icon: IC.user, color: "#818cf8", title: "Set up your Profile", desc: "Upload your resume — AI extracts experience, skills, education automatically into your profile." },
                { step: "3", icon: IC.refresh, color: "#4ade80", title: "Scrape & apply", desc: "Click 'Scrape Now' to fetch fresh jobs. AI qualifies each one. Tailor resume per job in one click." },
              ].map(s => (
                <div key={s.step} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: `${s.color}22`, border: `1px solid ${s.color}44`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Ic d={s.icon} size={15} color={s.color} />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Auto-scrape note */}
            <div style={{ background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.2)", borderRadius: 8, padding: "10px 14px", marginBottom: 24, fontSize: 12, color: "#4ade80" }}>
              ⚡ Jobs auto-fetch every hour 24/7 — even when your laptop is off (Railway cloud).
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={() => { localStorage.setItem("jh_welcomed", "1"); setShowWelcome(false); setView("settings"); }}
                style={{ flex: 1, height: 40, borderRadius: 10, background: "var(--accent)", color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer", border: "none" }}
              >
                Add API Key →
              </button>
              <button
                onClick={() => { localStorage.setItem("jh_welcomed", "1"); setShowWelcome(false); }}
                style={{ height: 40, padding: "0 18px", borderRadius: 10, background: "transparent", color: "var(--text-muted)", fontSize: 13, cursor: "pointer", border: "1px solid var(--border-subtle)" }}
              >
                Skip
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type TopbarProps = {
  scraping: boolean; scrapeMsg: string; lastScraped: string; onScrape: () => void;
  count: number; viewMode: string; setViewMode: (m: ViewMode) => void; IC: Record<string,string>;
  filters: Filters;
  setF: (k: "posted" | "status" | "role", v: string) => void;
  toggleArr: (k: "categories"|"exps"|"locTypes"|"countries"|"sources", val: string) => void;
  SOURCES: string[]; COUNTRIES: string[]; allJobs: Job[];
  sourceCounts: Record<string,number>;
  filtersActive: boolean; search: string; setSearch: (v: string) => void;
  searchRef: React.RefObject<HTMLInputElement>; onClearAll: () => void;
  myRolesOnly: boolean; setMyRolesOnly: (v: boolean) => void; userRoles: string[];
};

// ── FilterDropdown: checkbox multi-select popover ─────────────────────────────
function FilterDropdown({
  label, options, selected, onToggle, countMap,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (val: string) => void;
  countMap?: Record<string, number>;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const isActive = selected.length > 0;
  const displayLabel = isActive
    ? selected.length === 1 ? selected[0] : `${selected[0]} +${selected.length - 1}`
    : label;

  return (
    <div ref={ref} style={{ position: "relative", flex: 1, minWidth: 0 }}>
      {/* M3 Filter Chip */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", height: 30, borderRadius: 8, padding: "0 10px",
          fontSize: 11.5, fontWeight: isActive ? 600 : 400,
          border: isActive ? "1px solid var(--accent)" : "1px solid var(--border-default)",
          background: isActive ? "var(--accent-tonal)" : "var(--bg-elevated)",
          color: isActive ? "var(--accent)" : "var(--text-secondary)",
          cursor: "pointer", outline: "none", display: "flex", alignItems: "center",
          justifyContent: "space-between", gap: 4,
          transition: "all 150ms cubic-bezier(0.2,0,0,1)",
          whiteSpace: "nowrap", overflow: "hidden",
          boxShadow: isActive ? "none" : "var(--shadow-1)",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1, textAlign: "left" }}>
          {displayLabel}
        </span>
        {isActive && (
          <span style={{
            background: "var(--accent)", color: "#fff",
            borderRadius: 999, fontSize: 9, fontWeight: 700,
            padding: "1px 5px", flexShrink: 0,
          }}>{selected.length}</span>
        )}
      </button>

      {/* M3 Menu surface */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 200,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-default)",
          borderRadius: 12, padding: "6px 0",
          boxShadow: "var(--shadow-3)",
          minWidth: 200, maxHeight: 280, overflowY: "auto",
        }}>
          {options.map(opt => {
            const checked = selected.includes(opt);
            return (
              <label
                key={opt}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 14px", cursor: "pointer",
                  fontSize: 13, lineHeight: 1,
                  color: checked ? "var(--accent)" : "var(--text-primary)",
                  background: checked ? "var(--accent-tonal)" : "transparent",
                  transition: "background 80ms ease",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(opt)}
                  style={{ accentColor: "var(--accent)", width: 14, height: 14, flexShrink: 0, cursor: "pointer" }}
                />
                <span style={{ flex: 1, fontWeight: checked ? 500 : 400 }}>{opt}</span>
                {countMap?.[opt] != null && (
                  <span style={{
                    fontSize: 10.5, color: checked ? "var(--accent)" : "var(--text-muted)",
                    fontWeight: checked ? 600 : 400, marginLeft: "auto",
                  }}>{countMap[opt]}</span>
                )}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Topbar({ scraping, scrapeMsg, lastScraped, onScrape, count, viewMode, setViewMode, IC,
  filters, setF, toggleArr, SOURCES, COUNTRIES, allJobs, sourceCounts,
  filtersActive, search, setSearch, searchRef, onClearAll,
  myRolesOnly, setMyRolesOnly, userRoles }: TopbarProps) {

  const countryCounts = React.useMemo(() => {
    const m: Record<string,number> = {};
    allJobs.forEach(j => { if (j.country) m[j.country] = (m[j.country] || 0) + 1; });
    return m;
  }, [allJobs]);

  return (
    <div style={{ flexShrink: 0, borderBottom: "1px solid var(--border-default)", background: "var(--bg-surface)", boxShadow: "var(--shadow-1)" }}>
      {/* Row 1: Scrape + view toggle */}
      <div style={{ height: 48, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px", borderBottom: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="btn btn-accent" onClick={onScrape} disabled={scraping} style={{ height: 32, fontSize: 13, letterSpacing: "0.02em" }}>
            {scraping ? <Spinner size={13} color="#fff" /> : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.refresh }} />}
            {scraping ? "Scraping..." : "Scrape Now"}
          </button>
          {scrapeMsg && !scraping && <span style={{ fontSize: 12, fontWeight: 600, color: "#34d399" }}>{scrapeMsg}</span>}
          {lastScraped && <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.clock }} />{lastScraped}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{count} jobs</span>
          <div style={{ display: "flex", gap: 2, background: "var(--bg-elevated)", borderRadius: 10, padding: 3, border: "1px solid var(--border-default)", boxShadow: "var(--shadow-1)" }}>
            {([["list", IC.list], ["kanban", IC.kanban]] as [string, string][]).map(([m, d]) => (
              <button key={m} onClick={() => setViewMode(m as ViewMode)} style={{ width: 30, height: 26, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", color: viewMode === m ? "var(--accent)" : "var(--text-muted)", background: viewMode === m ? "var(--accent-tonal)" : "transparent", transition: "all 150ms cubic-bezier(0.2,0,0,1)" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: d }} />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Row 2: M3 Filter chips */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 12px", height: 48, overflowX: "auto" }}>

        {/* My Roles chip */}
        {userRoles.length > 0 && (
          <button onClick={() => setMyRolesOnly(!myRolesOnly)} style={{
            height: 30, padding: "0 12px", borderRadius: 8, fontSize: 11.5, fontWeight: 600, flexShrink: 0,
            border: myRolesOnly ? "1px solid var(--accent)" : "1px solid var(--border-default)",
            background: myRolesOnly ? "var(--accent-tonal)" : "var(--bg-elevated)",
            color: myRolesOnly ? "#93c5fd" : "var(--text-muted)",
            cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
            transition: "all 150ms ease", whiteSpace: "nowrap",
          }}>
            {myRolesOnly ? "🎯" : "🌐"} {myRolesOnly ? userRoles[0] : "All"}
          </button>
        )}

        <div style={{ width: 1, height: 18, background: "var(--border-subtle)", flexShrink: 0, margin: "0 2px" }} />

        {/* Search */}
        <div style={{ position: "relative", flex: 1.5, minWidth: 0 }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--text-muted)" }} dangerouslySetInnerHTML={{ __html: IC.search }} />
          <input ref={searchRef} type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            style={{
              width: "100%", paddingLeft: 24, paddingRight: 8, height: 28, fontSize: 11,
              borderRadius: 6, boxSizing: "border-box" as any,
              border: search ? "1px solid rgba(59,130,246,0.5)" : "1px solid var(--border-subtle)",
              background: search ? "rgba(59,130,246,0.06)" : "var(--bg-elevated)",
              color: "var(--text-primary)", outline: "none",
            }} />
        </div>

        <div style={{ width: 1, height: 18, background: "var(--border-subtle)", flexShrink: 0, margin: "0 2px" }} />

        {/* Multi-select filter dropdowns */}
        <FilterDropdown label="Category"  options={["Engineering","Data","Product","Design"]}           selected={filters.categories} onToggle={v => toggleArr("categories", v)} />
        <FilterDropdown label="Level"     options={["Entry","Mid","Senior","Lead"]}                     selected={filters.exps}       onToggle={v => toggleArr("exps", v)} />
        <FilterDropdown label="Type"      options={["Remote","Onsite","Hybrid"]}                        selected={filters.locTypes}   onToggle={v => toggleArr("locTypes", v)} />
        <FilterDropdown label="Country" options={
          COUNTRIES.length > 0 ? COUNTRIES :
          ["USA","Canada","UK","India","Remote","Australia","Germany","Singapore","Netherlands","Ireland"]
        } selected={filters.countries} onToggle={v => toggleArr("countries", v)} countMap={countryCounts} />
        <FilterDropdown label="Source" options={
          SOURCES.length > 0 ? SOURCES :
          ["Greenhouse","Workday","Lever","LinkedIn","Dice","Ashby","SmartRecruiters","BambooHR","Recruitee","Workable","Remotive","Google","Indeed","TheMuse"]
        } selected={filters.sources} onToggle={v => toggleArr("sources", v)} countMap={sourceCounts} />

        <div style={{ width: 1, height: 18, background: "var(--border-subtle)", flexShrink: 0, margin: "0 2px" }} />

        {/* Posted chips */}
        <div style={{ display: "flex", gap: 2, background: "var(--bg-elevated)", borderRadius: 6, padding: 2, border: "1px solid var(--border-subtle)", flexShrink: 0 }}>
          {(["24h","48h","72h","7d"] as const).map(o => (
            <button key={o} onClick={() => setF("posted", o)} style={{
              height: 22, padding: "0 8px", borderRadius: 4, fontSize: 11, fontWeight: 500,
              border: "none", cursor: "pointer", transition: "all 100ms ease",
              background: filters.posted === o ? "var(--accent)" : "transparent",
              color: filters.posted === o ? "#fff" : "var(--text-muted)",
            }}>{o}</button>
          ))}
        </div>

        {/* Clear */}
        {filtersActive && (() => {
          const n = [filters.categories.length, filters.exps.length, filters.locTypes.length,
            filters.countries.length, filters.sources.length, search.trim() ? 1 : 0].reduce((a,b) => a+b, 0);
          return (
            <button onClick={onClearAll} style={{
              height: 28, padding: "0 9px", borderRadius: 6, fontSize: 11, fontWeight: 600,
              border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.08)",
              color: "#f87171", cursor: "pointer", flexShrink: 0,
              display: "flex", alignItems: "center", gap: 4,
            }}>
              <span style={{ background: "rgba(239,68,68,0.2)", borderRadius: 999, width: 15, height: 15, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9 }}>{n}</span>
              Clear
            </button>
          );
        })()}
      </div>
    </div>
  );
}
