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
import Auth from "./components/Auth";
import { Onboarding } from "./components/Onboarding";

type View = "jobs" | "dashboard" | "profile" | "settings";
type ViewMode = "list" | "kanban";
type Filters = { posted: string; countries: string[]; locTypes: string[]; sources: string[]; status: string; role: string; exps: string[]; categories: string[]; minScore: number; };

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
  moon:     "<path d=\"M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z\"/>",
  sun:      "<circle cx=\"12\" cy=\"12\" r=\"4\"/><path d=\"M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4\"/>",
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
  const [listMode, setListMode]     = useState<"compact"|"cards">("compact");
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
    posted: "72h", countries: [], locTypes: [], sources: [], status: "all", role: "", exps: [], categories: [], minScore: 0,
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

  const sourceCounts = useMemo(() => {
    const m: Record<string, number> = {};
    allJobs.forEach(j => { m[j.source] = (m[j.source] || 0) + 1; });
    return m;
  }, [allJobs]);

  // Dynamic source list — sorted by count, only sources that have jobs
  const DEFAULT_SOURCES = [
    "Greenhouse", "Lever", "Ashby", "Workday", "HiringCafe",
  ];

  const SOURCES = useMemo(() => {
    const scraped = Object.entries(sourceCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([src]) => src);
    const merged = [...scraped, ...DEFAULT_SOURCES.filter(s => !scraped.includes(s))];
    return merged;
  }, [sourceCounts]);

  const DEFAULT_COUNTRIES = ["India", "USA"];
  const COUNTRIES = useMemo(() => {
    const counts: Record<string, number> = {};
    allJobs.forEach(j => { if (j.country) counts[j.country] = (counts[j.country] || 0) + 1; });
    const scraped = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => c);
    const merged = [...scraped, ...DEFAULT_COUNTRIES.filter(c => !scraped.includes(c))];
    return merged;
  }, [allJobs]);


  const filteredJobs = useMemo(() => {
    const now = Date.now();
    const GRACE = 6 * 3600000;
    const postedCutoff: Record<string, number> = {
      "24h": 24*3600000 + GRACE, "48h": 48*3600000 + GRACE,
      "72h": 72*3600000 + GRACE, "7d":  7*24*3600000 + GRACE,
    };
    const cutoffMs = postedCutoff[filters.posted] ?? Infinity;
    const parseMs = (s: string): number | null => {
      if (!s) return null;
      const t = new Date(s.replace(/(\.\d{3})\d+/, "$1")).getTime();
      return isNaN(t) ? null : t;
    };

    const CAT_TERMS: Record<string, string[]> = {
      Engineering: ["engineer","developer","devops","sre","platform","infrastructure","backend","frontend","fullstack"],
      Data:        ["data","analytics","analyst","scientist","ml","machine learning","ai","etl","pipeline","bi"],
      Product:     ["product manager","pm","product owner","program manager"],
      Design:      ["design","ux","ui","figma","creative"],
    };

    return jobs.filter(j => {
      if (myRolesOnly && userSettings?.job_roles?.length) {
        const roles: string[] = Array.isArray(userSettings.job_roles)
          ? userSettings.job_roles : JSON.parse(userSettings.job_roles || '[]');
        if (roles.length > 0) {
          const title = j.title.toLowerCase();
          if (!roles.some((r: string) => title.includes(r.toLowerCase().split(' ')[0]) || title.includes(r.toLowerCase()))) return false;
        }
      }
      if (filters.categories.length > 0) {
        const terms = filters.categories.flatMap(c => CAT_TERMS[c] || []);
        if (!terms.some(t => j.title.toLowerCase().includes(t))) return false;
      }
      if (filters.role.trim() && !j.title.toLowerCase().includes(filters.role.toLowerCase())) return false;
      if (filters.exps.length > 0) {
        const t = j.title.toLowerCase();
        const EXP: Record<string,RegExp> = { Entry:/(entry|junior|jr\.?|associate|intern)/i, Mid:/(mid|\bii\b|\b2\b|intermediate)/i, Senior:/(senior|sr\.?|lead|principal|staff)/i, Lead:/(lead|principal|staff|director)/i };
        if (!filters.exps.some(e => EXP[e]?.test(t))) return false;
      }
      if (filters.minScore > 0) {
        const score = (j.qualify_result as any)?.score ?? null;
        if (score === null || score < filters.minScore) return false;
      }
      if (filters.status !== "all" && j.status !== filters.status) return false;
      if (filters.countries.length > 0 && !filters.countries.includes(j.country || "")) return false;
      if (filters.locTypes.length > 0) {
        const isRemote = j.remote || (j.location || "").toLowerCase().includes("remote");
        if (!((filters.locTypes.includes("Remote") && isRemote) || (filters.locTypes.includes("Onsite") && !isRemote) || (filters.locTypes.includes("Hybrid") && (j.location || "").toLowerCase().includes("hybrid")))) return false;
      }
      if (filters.sources.length > 0 && !filters.sources.includes(j.source)) return false;
      if (cutoffMs !== Infinity) {
        const t = parseMs(j.posted_at) ?? parseMs(j.scraped_at);
        if (t !== null && now - t > cutoffMs) return false;
      }
      if (search.trim()) { const q = search.toLowerCase(); if (!j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false; }
      return true;
    });
  }, [jobs, filters, search, myRolesOnly, userSettings]);

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
    setFilters({ posted: "72h", countries: [], locTypes: [], sources: [], status: "all", role: "", exps: [], categories: [], minScore: 0 });
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
  const filtersActive = filters.posted !== "72h" || filters.countries.length > 0 || filters.locTypes.length > 0 || filters.sources.length > 0 || filters.status !== "all" || filters.role !== "" || filters.exps.length > 0 || filters.categories.length > 0 || filters.minScore > 0 || search.trim() !== "";
  const navItems = [
    { id: "jobs",      label: "Jobs",       ic: IC.search   },
    { id: "dashboard", label: "Dashboard",  ic: IC.dash     },
    { id: "profile",   label: "My Profile", ic: IC.user     },
    { id: "settings",  label: "Settings",   ic: IC.settings },
    { id: "tailor",    label: "Quick Tailor", ic: IC.sparkles },
  ];

  // ── Auth gate ────────────────────────────────────────────────────────────
  if (!isAuthenticated) {
    return <Auth onSuccess={(user: { id: string; email: string; name: string }) => {
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
    <div className="app">
      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        {/* Brand */}
        <div className="brand">
          <div className="brand-mark"><span className="brand-dot" /></div>
          <div className="brand-text">
            <div className="brand-name">Job <span className="hl">Hunter</span></div>
            <div className="brand-sub">Hunt Smarter, Not Harder</div>
          </div>
        </div>

        {/* Nav */}
        <div className="nav-label">Workspace</div>
        <nav className="nav-group">
          {navItems.map(n => {
            const active = view === n.id;
            return (
              <a key={n.id} onClick={() => handleNav(n.id)}
                className={`nav-item${active ? " active" : ""}`} style={{ cursor: "pointer" }}>
                <Ic d={n.ic} size={16} />
                {n.label}
                {n.id === "jobs" && <span className="nav-count">{filteredJobs.length}</span>}
              </a>
            );
          })}
        </nav>

        <div className="sidebar-spacer" />

        {/* Quick actions hint */}
        <div className="cmd-hint" onClick={() => { setView("jobs"); setTimeout(() => searchRef.current?.focus(), 0); }}>
          <Ic d={IC.search} size={14} />
          Quick actions
          <span className="kbd" style={{ marginLeft: "auto" }}>⌘K</span>
        </div>

        {/* Theme toggle */}
        <div className="theme-switch">
          <button className={isDark ? "on" : ""} onClick={() => setIsDark(true)}>
            <Ic d={IC.moon} size={14} /> Dark
          </button>
          <button className={!isDark ? "on" : ""} onClick={() => setIsDark(false)}>
            <Ic d={IC.sun} size={14} /> Light
          </button>
        </div>

        {/* User card */}
        <div className="user-card">
          <div className="user-av">{initials}</div>
          <div className="user-meta">
            <div className="user-name">{profileName.split(" ")[0] || currentUser?.email?.split("@")[0] || "User"}</div>
            <div className="user-mail">{userSettings?.profile_visa || currentUser?.email || "Job Hunter"}</div>
          </div>
          <button className="user-logout" onClick={handleLogout} title="Sign out">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ── */}
      <div className="main">
        {view === "dashboard" && <Dashboard />}
        {view === "profile"   && <Profile />}
        {view === "settings"  && <Settings />}

        {view === "jobs" && (
          <>
            <Topbar
              totalJobs={allJobs.length}
              scraping={scraping} scrapeMsg={scrapeMsg} lastScraped={lastScrapedDisplay}
              onScrape={handleScrape} count={filteredJobs.length}
              viewMode={viewMode} setViewMode={setViewMode} IC={IC}
              filters={filters} setF={setF} toggleArr={toggleArr}
              SOURCES={SOURCES.filter(s => s !== "All Sources")}
              COUNTRIES={COUNTRIES.filter(c => c !== "All Countries")}
              setMinScore={(v: number) => setFilters(f => ({ ...f, minScore: v }))}
              allJobs={allJobs} sourceCounts={sourceCounts}
              filtersActive={filtersActive} search={search} setSearch={setSearch}
              searchRef={searchRef} onClearAll={handleResetFilters}
              myRolesOnly={myRolesOnly} setMyRolesOnly={setMyRolesOnly}
              userRoles={Array.isArray(userSettings?.job_roles) ? userSettings.job_roles : JSON.parse(userSettings?.job_roles || '[]')}
            />
              {scraping && (
              <div className="scrape-banner">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: "spin .9s linear infinite", flexShrink: 0 }} dangerouslySetInnerHTML={{ __html: IC.refresh }} />
                Scraping sources for new roles…
                <div className="bar"><i /></div>
              </div>
            )}
          {viewMode === "kanban" ? (
              <Kanban jobs={filteredJobs} onStatusChange={(id, s) => handleStatusChange(id, s as JobStatus)} onSelect={id => { setViewMode("list"); handleSelect(id); }} />
            ) : (
              <div className="jobs-body">
                <div className="list-pane">
                  <div className="list-head">
                    <span className="sort">
                      Sorted by <b style={{ color: "var(--tx-2)" }}>match score</b>
                    </span>
                    <div className="seg" style={{ padding: 2 }}>
                      <button className={listMode === "compact" ? "on" : ""} title="Compact rows" onClick={() => setListMode("compact")}>
                        <Ic d={IC.list} size={15} />
                      </button>
                      <button className={listMode === "cards" ? "on" : ""} title="Padded cards" onClick={() => setListMode("cards")}>
                        <Ic d='<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>' size={15} />
                      </button>
                    </div>
                  </div>
                  <div className={`list-scroll${listMode === "cards" ? " cards" : ""}`}>
                    {loading ? (
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "40%", gap: 10, color: "var(--tx-3)" }}><Spinner size={18} /> Loading...</div>
                    ) : (
                      <JobList
                        jobs={filteredJobs}
                        selectedId={selectedId}
                        onSelect={handleSelect}
                        onSkip={id => handleStatusChange(id, "skipped")}
                        onQualifyUpdated={(id, r) => updateJob(id, { qualify_result: r })}
                        emptyState={allJobs.length === 0 ? "Click Scrape Now to fetch jobs" : "Try clearing filters"}
                        mode={listMode}
                      />
                    )}
                  </div>
                  <div className="kbd-hint-row">
                    <span className="grp"><span className="kbd">j</span><span className="kbd">k</span> navigate</span>
                    <span className="grp"><span className="kbd">↵</span> open</span>
                    <span className="grp"><span className="kbd">s</span> skip</span>
                    <span className="grp" style={{ marginLeft: "auto" }}><span className="kbd">⌘K</span> search</span>
                  </div>
                </div>
                <JobDetail job={selectedJob} tab={tab} setTab={setTab} onUpdate={(patch: Partial<Job>) => selectedJob && updateJob(selectedJob.id, patch)} onToast={toast} busy={busy} runAction={runAction} />
              </div>
            )}
          </>
        )}
      </div>

      <QuickTailor open={tailorOpen} onClose={() => setTailorOpen(false)} onToast={toast} />
      <Toasts toasts={toasts} />

      {/* Welcome modal — first time only */}
      {showWelcome && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
          <div style={{ background: "var(--glass-hi)", backdropFilter: "blur(22px)", border: "1px solid var(--glass-border)", borderRadius: 20, padding: "36px 40px", maxWidth: 520, width: "100%", boxShadow: "var(--sh-pop)", animation: "modalIn 220ms var(--ease)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 13, marginBottom: 24 }}>
              <div style={{ width: 44, height: 44, borderRadius: 13, background: "var(--grad)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 6px 20px -6px var(--violet-glow)" }}>
                <Ic d={IC.target} size={22} color="#fff" />
              </div>
              <div>
                <div style={{ fontFamily: "var(--f-display)", fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em" }}>Welcome to Job<span style={{ color: "var(--cyan)" }}>.</span>Hunter</div>
                <div style={{ fontSize: 13, color: "var(--tx-3)", marginTop: 2 }}>Your AI-powered job search assistant</div>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 24 }}>
              {[
                { step: "1", icon: IC.settings, color: "#8b5cf6", title: "Add your AI API key", desc: "Settings → pick OpenRouter, Nvidia NIM, or Anthropic → paste your key. Required for all AI features." },
                { step: "2", icon: IC.user, color: "#06b6d4", title: "Set up your Profile", desc: "Upload your resume — AI extracts experience, skills, education automatically into your profile." },
                { step: "3", icon: IC.refresh, color: "#10b981", title: "Scrape & apply", desc: "Click 'Scrape Now' to fetch fresh jobs. AI qualifies each one. Tailor resume per job in one click." },
              ].map(s => (
                <div key={s.step} style={{ display: "flex", gap: 13, alignItems: "flex-start" }}>
                  <div style={{ width: 34, height: 34, borderRadius: 9, background: `${s.color}20`, border: `1px solid ${s.color}40`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Ic d={s.icon} size={15} color={s.color} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--tx)", marginBottom: 3 }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: "var(--tx-2)", lineHeight: 1.55 }}>{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 9, padding: "10px 14px", marginBottom: 22, fontSize: 12, color: "#34d399" }}>
              ⚡ Jobs auto-fetch every hour 24/7 — even when your laptop is off (Railway cloud).
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => { localStorage.setItem("jh_welcomed", "1"); setShowWelcome(false); setView("settings"); }}
                className="btn btn-accent" style={{ flex: 1, height: 42, fontSize: 13.5, borderRadius: 11 }}>
                Add API Key →
              </button>
              <button onClick={() => { localStorage.setItem("jh_welcomed", "1"); setShowWelcome(false); }}
                className="btn btn-subtle" style={{ height: 42, padding: "0 18px", borderRadius: 11 }}>
                Skip
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── FilterDropdown ─────────────────────────────────────────────────────────────
function FilterDropdown({ label, options, selected, onToggle, countMap }: {
  label: string; options: string[]; selected: string[];
  onToggle: (val: string) => void; countMap?: Record<string, number>;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);
  const isActive = selected.length > 0;
  const displayLabel = isActive ? (selected.length === 1 ? selected[0] : `${selected[0]} +${selected.length - 1}`) : label;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className={`chip${isActive ? " on" : ""}`} onClick={() => setOpen(o => !o)}>
        {displayLabel}
        {isActive && <span className="fb-count">{selected.length}</span>}
        <svg className="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      {open && (
        <div className="menu" style={{ minWidth: 190, maxHeight: 280, overflowY: "auto" }}>
          {options.map(opt => {
            const checked = selected.includes(opt);
            return (
              <label key={opt} className={`menu-item${checked ? " sel" : ""}`}>
                <input type="checkbox" checked={checked} onChange={() => onToggle(opt)} style={{ display: "none" }} />
                <svg className="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6 9 17l-5-5"/></svg>
                <span style={{ flex: 1 }}>{opt}</span>
                {countMap?.[opt] != null && <span style={{ fontSize: 10.5, color: "var(--tx-3)", fontFamily: "var(--f-mono)" }}>{countMap[opt]}</span>}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Topbar + FilterBar ─────────────────────────────────────────────────────────
function Topbar({ scraping, scrapeMsg, lastScraped, onScrape, count, totalJobs, viewMode, setViewMode, IC,
  filters, setF, toggleArr, SOURCES, COUNTRIES, allJobs, sourceCounts,
  filtersActive, search, setSearch, searchRef, onClearAll,
  myRolesOnly, setMyRolesOnly, userRoles, setMinScore }: {
  scraping: boolean; scrapeMsg: string; lastScraped: string; onScrape: () => void;
  count: number; totalJobs?: number; viewMode: string; setViewMode: (m: ViewMode) => void; IC: Record<string,string>;
  filters: Filters; setF: (k: "posted"|"status"|"role", v: string) => void;
  toggleArr: (k: "categories"|"exps"|"locTypes"|"countries"|"sources", val: string) => void;
  SOURCES: string[]; COUNTRIES: string[]; allJobs: Job[]; sourceCounts: Record<string,number>;
  filtersActive: boolean; search: string; setSearch: (v: string) => void;
  searchRef: React.RefObject<HTMLInputElement>; onClearAll: () => void;
  myRolesOnly: boolean; setMyRolesOnly: (v: boolean) => void; userRoles: string[];
  setMinScore: (v: number) => void;
}) {
  const countryCounts = React.useMemo(() => {
    const m: Record<string,number> = {};
    allJobs.forEach(j => { if (j.country) m[j.country] = (m[j.country] || 0) + 1; });
    return m;
  }, [allJobs]);

  return (
    <>
      {/* ── TOP BAR ── */}
      <div className="topbar">
        <button className={`scrape-btn${scraping ? " running" : ""}`} onClick={onScrape} disabled={scraping}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.refresh }} />
          {scraping ? "Scraping…" : "Scrape Now"}
        </button>
        {scrapeMsg && !scraping && <span style={{ fontSize: 12, fontWeight: 600, color: "var(--st-applied)" }}>{scrapeMsg}</span>}
        <div className="meta">
          <div className="live-pip" />
          {lastScraped ? <><span>Last scraped</span><b>{lastScraped}</b></> : <span>Never scraped</span>}
          {totalJobs != null && totalJobs > 0 && <><span className="dot-sep" /><span><b className="mono">{totalJobs.toLocaleString()}</b> jobs indexed</span></>}
        </div>
        <div className="topbar-right">
          <div className="job-count"><b>{count}</b> jobs</div>
          <div className="seg">
            {([["list", IC.list], ["kanban", IC.kanban]] as [string,string][]).map(([m, d]) => (
              <button key={m} className={viewMode === m ? "on" : ""} onClick={() => setViewMode(m as ViewMode)} title={m}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: d }} />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── FILTER BAR ── */}
      <div className="filterbar">
        {userRoles.length > 0 && (
          <button className={`chip${myRolesOnly ? " on" : ""}`} onClick={() => setMyRolesOnly(!myRolesOnly)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.target }} />
            {myRolesOnly ? userRoles[0] : "All Roles"}
          </button>
        )}
        <div className="fb-divider" />
        <div className="search-wrap">
          <svg className="s-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.search }} />
          <input ref={searchRef} className="search-input" type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search jobs, companies…" />
          {!search && <span className="kbd s-kbd">⌘K</span>}
        </div>
        <div className="fb-divider" />
        <FilterDropdown label="Category" options={["Engineering","Data","Product","Design"]} selected={filters.categories} onToggle={v => toggleArr("categories", v)} />
        <FilterDropdown label="Level"    options={["Entry","Mid","Senior","Lead"]}           selected={filters.exps}       onToggle={v => toggleArr("exps", v)} />
        <FilterDropdown label="Type"     options={["Remote","Onsite","Hybrid"]}              selected={filters.locTypes}   onToggle={v => toggleArr("locTypes", v)} />
        <FilterDropdown label="Country"  options={COUNTRIES} selected={filters.countries}    onToggle={v => toggleArr("countries", v)} countMap={countryCounts} />
        <FilterDropdown label="Source"   options={SOURCES}   selected={filters.sources}      onToggle={v => toggleArr("sources", v)} countMap={sourceCounts} />
        <div className="fb-divider" />
        <div className="segchips score">
          {([0, 60, 70, 80, 90] as const).map(v => (
            <button key={v} className={filters.minScore === v ? "on" : ""} onClick={() => setMinScore(v)}>
              {v === 0 ? "Any" : `≥${v}%`}
            </button>
          ))}
        </div>
        <div className="segchips">
          {(["24h","48h","72h","7d"] as const).map(o => (
            <button key={o} className={filters.posted === o ? "on" : ""} onClick={() => setF("posted", o)}>{o}</button>
          ))}
        </div>
        {filtersActive && (() => {
          const n = [filters.categories.length, filters.exps.length, filters.locTypes.length,
            filters.countries.length, filters.sources.length, search.trim() ? 1 : 0].reduce((a,b) => a+b, 0);
          return (
            <button className="clear-btn" onClick={onClearAll}>
              <span className="n">{n}</span> Clear
            </button>
          );
        })()}
      </div>
    </>
  );
}
