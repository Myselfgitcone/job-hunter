import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import type { Job, JobStatus, QualifyResult } from "./types";
import { api } from "./api";

import JobPreferencesModal from './components/JobPreferencesModal';
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
// Matches design's filter shape exactly (INTERACTIONS.md)
type Filters = {
  q: string;
  category: string[];
  level: string[];
  type: string[];
  country: string[];
  source: string[];
  score: "any" | "60" | "70" | "80" | "90";
  time: "any" | "24" | "48" | "72" | "168";
  hcAge: "any" | "fresh" | "recent" | "old";  // HiringCafe original post age filter
};

function Ic({ d, size = 16, color, style }: { d: string; size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}

const IC: Record<string,string> = {
  target:   "<circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"5\"/><circle cx=\"12\" cy=\"12\" r=\"1\"/>",
  dash:     "<polyline points=\"3 3 3 21 21 21\"/><polyline points=\"3 16 10 9 14 13 21 6\"/>",
  user:     "<circle cx=\"12\" cy=\"8\" r=\"4\"/><path d=\"M4 21v-1a7 7 0 0 1 14 0v1\"/>",
  settings: "<circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z\"/>",
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
    if (m < 60) return m + "min ago";
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

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const userStr = urlParams.get('user');
    if (token && userStr) {
      try {
        const parsedUser = JSON.parse(decodeURIComponent(userStr));
        localStorage.setItem("jh_token", token);
        localStorage.setItem("jh_user", JSON.stringify(parsedUser));
        window.history.replaceState({}, document.title, window.location.pathname);
        setCurrentUser(parsedUser);
        setIsAuthenticated(true);
      } catch (e) {
        console.error("Failed to parse OAuth user data", e);
      }
    }
  }, []);

  const getInitialView = (): View => {
    const hash = window.location.hash.replace("#", "");
    return ["jobs", "dashboard", "profile", "settings"].includes(hash) ? (hash as View) : "jobs";
  };
  const [view, setView]             = useState<View>(getInitialView);

  useEffect(() => {
    window.location.hash = view;
  }, [view]);

  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (["jobs", "dashboard", "profile", "settings"].includes(hash)) setView(hash as View);
    };
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  const [viewMode, setViewMode]     = useState<ViewMode>("list");
  const [listMode, setListMode]     = useState<"compact"|"cards">("cards");
  const [sortBy, setSortBy]         = useState<"score"|"date">("score");
  const [jobs, setJobs]             = useState<Job[]>([]);
  const [allJobs, setAllJobs]       = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab]               = useState("overview");
  const [loading, setLoading]       = useState(false);
  const [scraping, setScraping]     = useState(false);
  const [scrapeMsg, setScrapeMsg]   = useState("");
  const [lastScrapedTs, setLastScrapedTs] = useState<string>("");
  const [lastScrapedDisplay, setLastScrapedDisplay] = useState("");
  const scrapePollerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshJob = useCallback(async (id: string) => {
    try {
      const updated = await api.getJob(id);
      setJobs(prev => prev.map(j => j.id === id ? { ...j, ...updated } : j));
      setAllJobs(prev => prev.map(j => j.id === id ? { ...j, ...updated } : j));
    } catch {}
  }, []);

  // Lazy-load the full job description when a job is selected
  useEffect(() => {
    if (selectedId) {
      const j = allJobs.find(x => x.id === selectedId);
      if (j && !j.description) {
        refreshJob(selectedId);
      }
    }
  }, [selectedId, allJobs, refreshJob]);

  // Live-update "X min ago" every 30s
  useEffect(() => {
    if (!lastScrapedTs) return;
    const update = () => setLastScrapedDisplay(timeAgo(lastScrapedTs));
    update();
    const iv = setInterval(update, 30000);
    return () => clearInterval(iv);
  }, [lastScrapedTs]);

  // Cleanup scrape poller on unmount
  useEffect(() => {
    return () => { if (scrapePollerRef.current) clearInterval(scrapePollerRef.current); };
  }, []);

  const [visaFilter, setVisaFilter] = useState(false);
  const [expFilter,  setExpFilter]  = useState(false);

  // Load user settings on auth
  useEffect(() => {
    if (!isAuthenticated) return;
    api.getSettings().then((s: any) => {
      setUserSettings(s);
      if (s.last_scraped_at) setLastScrapedTs(s.last_scraped_at);
      setVisaFilter(!!s.visa_filter);
      setExpFilter(!!s.level_filter);
    }).catch(() => {});
  }, [isAuthenticated]);

  // Persist visa/exp filter toggles to settings whenever they change
  const saveFilterToggle = useCallback((visa: boolean, exp: boolean) => {
    api.saveSettings({ visa_filter: visa, level_filter: exp } as any).catch(() => {});
  }, []);

  const [tailorOpen, setTailorOpen] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("jh_sidebar") === "1");
  const [busy, setBusy]             = useState<string | null>(null);
  const [showWelcome, setShowWelcome] = useState(() => !localStorage.getItem("jh_welcomed"));
  const { toasts, toast }           = useToasts();

  useEffect(() => { localStorage.setItem("jh_sidebar", sidebarCollapsed ? "1" : "0"); }, [sidebarCollapsed]);
  const searchRef                   = useRef<HTMLInputElement>(null);

  // Dynamic user display from auth
  const profileName = currentUser?.name || userSettings?.profile_name || "";
  const userRole = (() => {
    const roles = Array.isArray(userSettings?.job_roles) ? userSettings.job_roles : JSON.parse(userSettings?.job_roles || "[]");
    return roles[0] || "My Role";
  })();
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

  const DEFAULT_FILTERS: Filters = { q: "", category: [], level: [], type: [], country: [], source: [], score: "any", time: "any", hcAge: "any" };
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [myRolesOnly, setMyRolesOnly] = useState(false);
  const [activeRoleView, setActiveRoleView] = useState<string>("");

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

  const loadJobs = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try { const raw = await api.getJobs(); setJobs(raw); setAllJobs(raw); }
    catch {} finally { setLoading(false); }
  }, [isAuthenticated]);

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
    const parseMs = (s: string): number | null => {
      if (!s) return null;
      const t = new Date(s.replace(/(\.\d{3})\d+/, "$1")).getTime();
      return isNaN(t) ? null : t;
    };
    return jobs.filter(j => {
      // 1. Base Pool (Job Preferences)
      const rawRoles = userSettings?.job_roles;
      if (rawRoles) {
        const roles: string[] = Array.isArray(rawRoles) ? rawRoles : JSON.parse(rawRoles || "[]");
        if (roles.length > 0) {
          const title = j.title.toLowerCase();
          const desc = (j.description || "").toLowerCase();
          const matchesAnyRole = roles.some((r: string) => {
            const term = r.toLowerCase().trim();
            if (term === "bi") return /\bbi\b/.test(title) || /\bbi\b/.test(desc);
            return title.includes(term) || desc.includes(term);
          });
          if (!matchesAnyRole) return false;

          // 2. View Filter (Dropdown)
          if (myRolesOnly && activeRoleView) {
            if (!title.includes(activeRoleView.toLowerCase())) return false;
          }
        }
      }
      // q — free text (design: title + company)
      if (filters.q && !(j.title + " " + j.company).toLowerCase().includes(filters.q.toLowerCase())) return false;
      // category
      if (filters.category.length) {
        const CAT: Record<string, string[]> = {
          Engineering: ["engineer","developer","devops","sre","platform","infrastructure","backend","frontend","fullstack"],
          Data:        ["data","analytics","analyst","scientist","ml","machine learning","ai","etl","pipeline","bi"],
          Product:     ["product","pm ","product owner","program manager"],
          Design:      ["design","ux","ui","figma","creative"],
        };
        const terms = filters.category.flatMap(c => CAT[c] || []);
        if (!terms.some(t => j.title.toLowerCase().includes(t))) return false;
      }
      // level
      if (filters.level.length) {
        const t = j.title.toLowerCase();
        const EXP: Record<string, RegExp> = {
          Entry: /(entry|junior|jr\.?|associate|intern)/i,
          Mid: /(mid|\bii\b|\b2\b|intermediate)/i,
          Senior: /(senior|sr\.?)/i,
          Lead: /(lead|principal|staff|director)/i,
        };
        if (!filters.level.some(e => EXP[e]?.test(t))) return false;
      }
      // type: Remote→job.remote, Onsite→!remote, Hybrid→type===Hybrid
      if (filters.type.length) {
        const isRemote = j.remote || (j.location || "").toLowerCase().includes("remote");
        const ok = filters.type.some(t =>
          (t === "Remote" && isRemote) || (t === "Onsite" && !isRemote) || (t === "Hybrid" && (j.location || "").toLowerCase().includes("hybrid")));
        if (!ok) return false;
      }
      // country
      if (filters.country.length && !filters.country.includes(j.country || "")) return false;
      // source
      if (filters.source.length && !filters.source.includes(j.source)) return false;
      // score
      if (filters.score !== "any") {
        const sc = (j.qualify_result as any)?.score ?? null;
        if (sc === null || sc < parseInt(filters.score)) return false;
      }
      // time (posted within N hours)
      if (filters.time !== "any") {
        const t = parseMs(j.posted_at) ?? parseMs(j.scraped_at);
        if (t !== null && now - t > parseInt(filters.time) * 3600000 + 6 * 3600000) return false;
      }
      // hcAge: filter HiringCafe jobs by original estimated post age
      if (filters.hcAge !== "any" && j.source === "HiringCafe") {
        const orig = parseMs(j.hc_original_date);
        if (orig !== null) {
          const ageDays = (now - orig) / 86400000;
          if (filters.hcAge === "fresh"  && ageDays > 14)  return false;
          if (filters.hcAge === "recent" && ageDays > 90)  return false;
          if (filters.hcAge === "old"    && ageDays <= 90) return false;
        }
      }
      // Visa filter — only relevant for USA jobs (India roles don't require US visa sponsorship)
      if (visaFilter && j.country === "USA" && j.visa_sponsorship === false) return false;
      // Level filter — hide overqualified roles
      if (expFilter  && !isLevelMatch(j.title)) return false;
      return true;
    }).sort((a, b) => {
      if (sortBy === "score") {
        const scoreA = (a.qualify_result as any)?.score ?? -1;
        const scoreB = (b.qualify_result as any)?.score ?? -1;
        if (scoreA !== scoreB) return scoreB - scoreA;
      }
      // Date sort (fallback for score, or primary for date)
      const tA = parseMs(a.posted_at) ?? parseMs(a.scraped_at) ?? 0;
      const tB = parseMs(b.posted_at) ?? parseMs(b.scraped_at) ?? 0;
      return tB - tA;
    });
  }, [jobs, filters, myRolesOnly, activeRoleView, userSettings, sortBy, visaFilter, expFilter]);

  const selectedJob = jobs.find(j => j.id === selectedId) || null;

  useEffect(() => {
    if (viewMode === "list" && filteredJobs.length && !filteredJobs.find(j => j.id === selectedId))
      setSelectedId(filteredJobs[0].id);
  }, [filteredJobs, viewMode, selectedId]);

  const updateJob = (id: string, patch: Partial<Job>) =>
    setJobs(js => js.map(j => j.id === id ? { ...j, ...patch } : j));

  const handleScrape = async () => {
    if (scraping) return;
    setScraping(true);
    setScrapeMsg("");
    const tsBeforeScrape = lastScrapedTs;
    try {
      const r = await api.scrape();
      setScrapeMsg("Running");
      toast(r.message || "Scrape started — button unlocks when done", "success");
      // Poll every 10s until last_scraped_at changes → scrape finished
      if (scrapePollerRef.current) clearInterval(scrapePollerRef.current);
      scrapePollerRef.current = setInterval(async () => {
        try {
          const s = await api.getSettings();
          const newTs: string = (s as any).last_scraped_at || "";
          if (newTs && newTs !== tsBeforeScrape) {
            clearInterval(scrapePollerRef.current!);
            scrapePollerRef.current = null;
            setLastScrapedTs(newTs);
            setScraping(false);
            setScrapeMsg("");
            toast("Scrape complete! New jobs loaded.", "success");
            loadJobs();
          }
        } catch { /* ignore poll errors */ }
      }, 10_000);
    } catch (e: any) {
      setScrapeMsg(e.message);
      toast(e.message, "error");
      setScraping(false);
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Delete ALL jobs? Cannot be undone.")) return;
    try { const r = await api.clearAllJobs(); setJobs([]); setAllJobs([]); setSelectedId(null); toast("Cleared " + r.deleted + " jobs", "success"); }
    catch (e: any) { toast(e.message, "error"); }
  };

  const handleResetFilters = () => { setFilters(DEFAULT_FILTERS); setMyRolesOnly(false); };

  const handleStatusChange = async (id: string, status: JobStatus) => {
    await api.setStatus(id, status); updateJob(id, { status }); toast("Moved to " + status, "success");
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

  const handleSelect = (id: string) => { setSelectedId(id); setTab("overview"); };
  // Expose nav to Settings component for "Go to Profile" link
  useEffect(() => { (window as any).__navToProfile = () => setView("profile"); }, []);
  const handleNav = (v: string) => { if (v === "tailor") { setTailorOpen(true); return; } setView(v as View); };
  const activeFilterCount = filters.category.length + filters.level.length + filters.type.length + filters.country.length + filters.source.length + (filters.score !== "any" ? 1 : 0);
  const filtersActive = activeFilterCount > 0 || filters.q !== "" || !myRolesOnly;
  const isAdmin = currentUser?.email?.toLowerCase() === "jaggubhai8766@gmail.com";
  
  const navItems = [
    { id: "jobs",      label: "Jobs",         ic: IC.search   },
    { id: "dashboard", label: "Dashboard",    ic: IC.dash     },
    { id: "profile",   label: "My Profile",   ic: IC.user     },
    ...(isAdmin ? [{ id: "settings",  label: "Settings",     ic: IC.settings }] : []),
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
      {!sidebarCollapsed && (
        <aside className="sidebar">
          {/* Brand */}
          <div className="brand" style={{ justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
              <div className="brand-mark" style={{ flexShrink: 0 }}><span className="brand-dot" /></div>
              <div className="brand-text">
                <div className="brand-name">Job <span className="hl">Hunter</span></div>
                <div className="brand-sub">Hunt Smarter, Not Harder</div>
              </div>
            </div>
            <button onClick={() => setSidebarCollapsed(true)} className="collapse-btn" title="Close sidebar" style={{ flexShrink: 0 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M9 3v18"/></svg>
            </button>
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
      )}

      {/* ── MAIN CONTENT ── */}
      <div className="main">
        {sidebarCollapsed && view !== "jobs" && (
          <div style={{ display: "flex", alignItems: "center", height: 58, borderBottom: "1px solid var(--line)", padding: "0 18px", flexShrink: 0, background: "var(--bg-surface)" }}>
            <div style={{ display: "flex", alignItems: "center", width: 230, flexShrink: 0 }}>
              <button onClick={() => setSidebarCollapsed(false)} className="collapse-btn" title="Open sidebar" style={{ marginRight: 16 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M9 3v18"/></svg>
              </button>
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <div className="brand-mark" style={{ width: 26, height: 26, borderRadius: 8, flexShrink: 0 }}><span className="brand-dot" /></div>
                <div className="brand-text">
                  <div className="brand-name" style={{ margin: 0, fontSize: 16 }}>Job <span className="hl">Hunter</span></div>
                  <div className="brand-sub">Hunt Smarter, Not Harder</div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {view === "dashboard" && <Dashboard />}
        {view === "profile"   && <Profile />}
        {view === "settings"  && (isAdmin ? <Settings onToast={toast} /> : <div style={{padding: 40, color: "#f87171", fontSize: 16}}>Restricted Access. Only the Master Admin can view Settings.</div>)}

        {view === "jobs" && (
          <>
            <Topbar
              scraping={scraping} lastScraped={lastScrapedDisplay}
              onScrape={handleScrape} count={filteredJobs.length}
              totalJobs={allJobs.length}
              viewMode={viewMode} setViewMode={setViewMode} IC={IC}
              isAdmin={isAdmin} onOpenPreferences={() => setPreferencesOpen(true)}
              userRoles={userSettings?.job_roles ? (Array.isArray(userSettings.job_roles) ? userSettings.job_roles : JSON.parse(userSettings.job_roles)) : []}
              sidebarCollapsed={sidebarCollapsed}
              setSidebarCollapsed={setSidebarCollapsed}
              preferencesNode={
                <JobPreferencesModal 
                  open={preferencesOpen} 
                  onClose={() => setPreferencesOpen(false)} 
                  onToast={toast}
                  onSaved={(s) => setUserSettings(s)}
                />
              }
            />
            <FilterBar
              filters={filters} setFilters={setFilters}
              role={userRole} roleOn={myRolesOnly} setRoleOn={setMyRolesOnly}
              activeRoleView={activeRoleView} setActiveRoleView={setActiveRoleView}
              searchRef={searchRef}
              COUNTRIES={COUNTRIES}
              visaFilter={visaFilter} setVisaFilter={(v) => { setVisaFilter(v); saveFilterToggle(v, expFilter); }}
              expFilter={expFilter}   setExpFilter={(v) => { setExpFilter(v); saveFilterToggle(visaFilter, v); }}
              isAdmin={isAdmin} userRoles={userSettings?.job_roles ? (Array.isArray(userSettings.job_roles) ? userSettings.job_roles : JSON.parse(userSettings.job_roles)) : []}
              sidebarCollapsed={sidebarCollapsed}
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
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--tx-3)", whiteSpace: "nowrap" }}>
                      Sorted by:
                      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                        <select 
                          value={sortBy} 
                          onChange={e => setSortBy(e.target.value as "score"|"date")}
                          style={{ appearance: "none", background: "var(--bg-elevated)", border: "1px solid var(--line)", borderRadius: 6, color: "var(--tx)", fontWeight: 600, padding: "3px 22px 3px 10px", cursor: "pointer", outline: "none", fontFamily: "inherit", fontSize: 12.5, boxShadow: "0 1px 2px rgba(0,0,0,0.05)" }}
                        >
                          <option value="score">Match Score</option>
                          <option value="date">Date Posted</option>
                        </select>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ position: "absolute", right: 7, color: "var(--tx-3)", pointerEvents: "none" }}><path d="m6 9 6 6 6-6"/></svg>
                      </div>
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

function countPanelFilters(f: { category: string[]; level: string[]; type: string[]; country: string[]; source: string[]; score: string; hcAge?: string }) {
  return f.category.length + f.level.length + f.type.length + f.country.length + f.source.length + (f.score !== "any" ? 1 : 0) + (f.hcAge && f.hcAge !== "any" ? 1 : 0);
}

// ── Topbar (exact match to shell.jsx TopBar) ────────────────────────────────────
function Topbar({ scraping, lastScraped, onScrape, count, totalJobs, viewMode, setViewMode, IC, isAdmin, onOpenPreferences, userRoles, sidebarCollapsed, setSidebarCollapsed, preferencesNode }: {
  scraping: boolean; lastScraped: string; onScrape: () => void;
  count: number; totalJobs: number; viewMode: string; setViewMode: (m: ViewMode) => void;
  IC: Record<string, string>; isAdmin: boolean; onOpenPreferences?: () => void; userRoles?: string[];
  sidebarCollapsed: boolean; setSidebarCollapsed: (v: boolean) => void;
  preferencesNode?: React.ReactNode;
}) {
  return (
    <div className="topbar" style={{ paddingLeft: sidebarCollapsed ? 18 : 20 }}>
      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
        {sidebarCollapsed && (
          <div style={{ display: "flex", alignItems: "center", width: 230, flexShrink: 0 }}>
            <button onClick={() => setSidebarCollapsed(false)} className="collapse-btn" title="Open sidebar" style={{ marginRight: 16 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M9 3v18"/></svg>
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <div className="brand-mark" style={{ width: 26, height: 26, borderRadius: 8, flexShrink: 0 }}><span className="brand-dot" /></div>
              <div className="brand-text">
                <div className="brand-name" style={{ margin: 0, fontSize: 16 }}>Job <span className="hl">Hunter</span></div>
                <div className="brand-sub">Hunt Smarter, Not Harder</div>
              </div>
            </div>
          </div>
        )}
        <div style={{ position: "relative" }}>
          <div 
            onClick={onOpenPreferences} 
            style={{ display: "inline-flex", alignItems: "center", background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 10, padding: 4, cursor: "pointer", transition: "all 0.2s", boxShadow: "var(--sh-sm)" }}
            onMouseOver={e => { e.currentTarget.style.borderColor = "rgba(124,58,237,0.4)"; e.currentTarget.style.boxShadow = "0 4px 14px -2px rgba(124,58,237,0.12)"; }}
            onMouseOut={e => { e.currentTarget.style.borderColor = "var(--line)"; e.currentTarget.style.boxShadow = "var(--sh-sm)"; }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px 4px 6px", color: "var(--tx)", fontSize: 13, fontWeight: 600 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.target }} />
              Job Preferences
            </div>
            
            <div style={{ width: 1, height: 18, background: "var(--line)", margin: "0 6px 0 2px" }} />

            <div style={{ display: "flex", alignItems: "center", gap: 6, paddingRight: 6 }}>
              {userRoles && userRoles.length > 0 ? (
                userRoles.map(role => (
                  <span key={role} style={{ background: "var(--bg-elevated)", border: "1px solid var(--line)", color: "var(--tx-2)", fontSize: 11.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6 }}>
                    {role}
                  </span>
                ))
              ) : (
                <span style={{ fontSize: 12, color: "var(--tx-3)", padding: "0 6px", fontWeight: 500 }}>All jobs shown</span>
              )}
            </div>
          </div>
          {preferencesNode}
        </div>
      </div>

      <div className="meta">
        {isAdmin && (
          <>
            <button className={`scrape-btn${scraping ? " running" : ""}`} onClick={onScrape} disabled={scraping} style={{ height: 26, padding: "0 10px", fontSize: 12, borderRadius: 6, marginRight: 8 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.refresh }} />
              {scraping ? "Scraping…" : "Scrape Now"}
            </button>
            <span className="dot-sep" style={{ marginRight: 8 }} />
          </>
        )}
        <div className="live-pip" />
        Last scraped <b>{lastScraped || "never"}</b>
        <span className="dot-sep" />
        <span className="job-count"><b>{totalJobs.toLocaleString()}</b> jobs indexed</span>
      </div>
      <div className="topbar-right">
        <div className="job-count"><b>{count}</b> shown</div>
        <div className="seg">
          <button className={viewMode === "list" ? "on" : ""} onClick={() => setViewMode("list")} title="List view">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.list }} />
          </button>
          <button className={viewMode === "kanban" ? "on" : ""} onClick={() => setViewMode("kanban")} title="Kanban view">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.kanban }} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── FilterBar (exact match to shell.jsx FilterBar) ──────────────────────────────
// ── All department groups (Category) ─────────────────────────────────────────
const DEPT_GROUPS: { group: string; items: string[] }[] = [
  { group: "Technology",                items: ["Software Engineering","Data Engineering","ML / AI Engineering","DevOps / Infrastructure","Mobile Engineering","QA / Testing","Cybersecurity","IT Support","Systems Administration"] },
  { group: "Data and Analytics",        items: ["Data Science","Data Analysis","Business Intelligence","Analytics Engineering","Data Architecture","Database Administration"] },
  { group: "Design and Creative",       items: ["UX Design","UI Design","Product Design","Graphic Design","Creative and Art Services","UX Research","Motion Design"] },
  { group: "Product",                   items: ["Product Management","Technical Product Management","Program Management"] },
  { group: "Business Operations",       items: ["Project Management","Business Operations","Finance and Accounting","Legal and Compliance","Human Resources","Administrative Support","Strategy and Consulting"] },
  { group: "Sales and Marketing",       items: ["Sales","Marketing","Business Development","Content and Communications","Public Affairs","Account Management"] },
  { group: "Healthcare",                items: ["Healthcare Services - Advanced Practice","Healthcare Services - Allied Health","Healthcare Services - Nursing","Healthcare Administration","Pharmacy","Mental Health"] },
  { group: "Education",                 items: ["Teaching and Instruction","Curriculum and Training","Educational Administration","Academic Research"] },
  { group: "Customer and Social Services", items: ["Customer Success","Customer Support","Social Work","Community Services","Non-Profit"] },
  { group: "Research and Development",  items: ["R&D Engineering","Scientific Research","Lab Services","Product Research"] },
  { group: "Skilled Trades",            items: ["Construction","Mechanical","Electrical","Repair and Maintenance","Labor"] },
  { group: "Transportation and Logistics", items: ["Logistics","Supply Chain","Fleet Management","Warehousing","Delivery"] },
  { group: "Quality and Safety",        items: ["Quality Assurance","Regulatory Compliance","Environment Health and Safety","Risk Management"] },
  { group: "Food and Hospitality",      items: ["Food Service","Restaurant Management","Hotel and Lodging","Event Management"] },
  { group: "Protective Services",       items: ["Law Enforcement","Security","Fire Services","Emergency Management"] },
  { group: "Custodial Services",        items: ["Facilities Management","Janitorial","Groundskeeping"] },
];

// ── Accordion section (collapsible filter group) ──────────────────────────────
function AccordionSection({ label, count, children, defaultOpen = false }: {
  label: string; count: number; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="acc-section">
      <button className="acc-head" onClick={() => setOpen(o => !o)}>
        <span className="acc-label">{label}</span>
        {count > 0 && <span className="acc-count">{count}</span>}
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
          style={{ marginLeft: count > 0 ? 4 : "auto", transition: "transform .15s", transform: open ? "rotate(0deg)" : "rotate(-90deg)", flexShrink: 0 }}>
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </button>
      {open && <div className="acc-body">{children}</div>}
    </div>
  );
}

// ── Department selector (nested: dept group → items) ─────────────────────────
function DeptSelector({ selected, onChange }: { selected: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = React.useState("");
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>(
    Object.fromEntries(DEPT_GROUPS.map(g => [g.group, true]))
  );
  const toggleItem = (item: string) => onChange(selected.includes(item) ? selected.filter(x => x !== item) : [...selected, item]);
  const toggleGroup = (g: string) => setCollapsed(c => ({ ...c, [g]: !c[g] }));
  const expandAll   = () => setCollapsed(Object.fromEntries(DEPT_GROUPS.map(g => [g.group, false])));
  const collapseAll = () => setCollapsed(Object.fromEntries(DEPT_GROUPS.map(g => [g.group, true])));
  const filtered = q.trim()
    ? DEPT_GROUPS.map(g => ({ ...g, items: g.items.filter(i => i.toLowerCase().includes(q.toLowerCase())) })).filter(g => g.items.length > 0)
    : DEPT_GROUPS;
  return (
    <div className="dept-sel">
      <div className="dept-search-wrap">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", color:"var(--tx-3)", pointerEvents:"none" }}>
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input className="dept-search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search departments…" />
      </div>
      {!q && (
        <div className="dept-actions">
          <button onClick={expandAll}>↓ Expand All</button>
          <button onClick={collapseAll}>↑ Collapse All</button>
          {selected.length > 0 && <button className="dept-clear" onClick={() => onChange([])}>Clear ({selected.length})</button>}
        </div>
      )}
      <div className="dept-groups">
        {filtered.map(({ group, items }) => {
          const selCount = items.filter(i => selected.includes(i)).length;
          return (
            <div className="dept-group" key={group}>
              <button className="dept-group-head" onClick={() => toggleGroup(group)}>
                <span>{group}</span>
                {selCount > 0 && <span className="dept-sel-count">{selCount}</span>}
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                  style={{ marginLeft: selCount > 0 ? 4 : "auto", transition:"transform .15s", transform: collapsed[group] ? "rotate(-90deg)" : "rotate(0deg)", flexShrink: 0 }}>
                  <path d="M6 9l6 6 6-6"/>
                </svg>
              </button>
              {!collapsed[group] && (
                <div className="dept-items">
                  {items.map(item => (
                    <label key={item} className={`fp-check${selected.includes(item) ? " on" : ""}`} onClick={() => toggleItem(item)}>
                      <span className="fp-box">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6 9 17l-5-5"/></svg>
                      </span>
                      {item}
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FilterBar({ filters, setFilters, role, roleOn, setRoleOn, activeRoleView, setActiveRoleView, searchRef, COUNTRIES, visaFilter, setVisaFilter, expFilter, setExpFilter, isAdmin, userRoles, sidebarCollapsed }: {
  filters: Filters; setFilters: React.Dispatch<React.SetStateAction<Filters>>;
  role: string; roleOn: boolean; setRoleOn: (v: boolean) => void;
  activeRoleView: string; setActiveRoleView: (v: string) => void;
  searchRef: React.RefObject<HTMLInputElement>; COUNTRIES: string[];
  visaFilter: boolean; setVisaFilter: (v: boolean) => void;
  expFilter: boolean; setExpFilter: (v: boolean) => void;
  isAdmin: boolean; userRoles?: string[];
  sidebarCollapsed?: boolean;
}) {
  const set = (k: keyof Filters, v: any) => setFilters(f => ({ ...f, [k]: v }));
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState({ category: [] as string[], level: [] as string[], type: [] as string[], country: [] as string[], source: [] as string[], score: "any" as string });
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (open) setDraft({ category: filters.category, level: filters.level, type: filters.type, country: filters.country, source: filters.source, score: filters.score });
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, [open]);

  const toggle = (key: keyof typeof draft, val: string) => setDraft(d => {
    const arr = d[key] as string[];
    return { ...d, [key]: arr.includes(val) ? arr.filter((x: string) => x !== val) : [...arr, val] };
  });
  const resetAll = () => setDraft({ category: [], level: [], type: [], country: [], source: [], score: "any" });
  const apply = () => { setFilters(f => ({ ...f, ...draft, score: draft.score as Filters["score"] })); setOpen(false); };

  const committed = countPanelFilters(filters);
  const draftCount = countPanelFilters(draft);
  const timeOpts: [Filters["time"], string][] = [["any","Any"],["24","24h"],["48","48h"],["72","72h"],["168","7d"]];
  const groups: [keyof typeof draft, string, string[]][] = [
    ["level",    "Experience Level", ["Internship","Entry Level","Mid Level","Senior","Lead"]],
    ["type",     "Work Type",["Remote","Onsite","Hybrid"]],
    ...(isAdmin ? [["source", "Source", ["Greenhouse","Lever","Ashby","Workday","HiringCafe"]] as [keyof typeof draft, string, string[]]] : []),
    ["country",  "Country",  COUNTRIES.length ? COUNTRIES : ["USA","Canada","United Kingdom","Germany","France","India","Remote"]],
  ];
  const scoreOpts: [string, string][] = [["any","Any"],["60","≥60%"],["70","≥70%"],["80","≥80%"],["90","≥90%"]];

  return (
    <div className="filterbar" style={{ paddingLeft: sidebarCollapsed ? 248 : 20 }}>
      {/* Role chip - hybrid toggle/dropdown */}
      {userRoles && userRoles.length > 0 && (
        <div className="chip" style={{ display: "flex", alignItems: "center", padding: 0, opacity: roleOn ? 1 : 0.6, background: roleOn ? "var(--bg-hover)" : "transparent", transition: "opacity 0.2s" }}>
          <button onClick={() => {
            const nextState = !roleOn;
            setRoleOn(nextState);
            if (!nextState) setActiveRoleView("");
          }} style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 8px 0 10px", height: "100%", background: "none", border: "none", cursor: "pointer", color: "var(--tx)", borderRight: "1px solid var(--line)", borderTopLeftRadius: "var(--r-sm)", borderBottomLeftRadius: "var(--r-sm)" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--violet)" }}>
              <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>
            </svg>
            My Role:
          </button>
          <select 
            value={activeRoleView} 
            onChange={(e) => {
              setActiveRoleView(e.target.value);
              if (e.target.value) setRoleOn(true);
            }}
            style={{ background: "none", border: "none", color: "var(--violet)", fontWeight: 600, padding: "0 10px 0 8px", cursor: "pointer", outline: "none", height: "100%", fontFamily: "inherit", fontSize: 13 }}
          >
            <option value="">All My Roles</option>
            {userRoles.map((r: string) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      )}

      {/* Search */}
      <div className="search-wrap">
        <svg className="s-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input ref={searchRef} className="search-input" type="text" value={filters.q} onChange={e => set("q", e.target.value)} placeholder="Search titles, companies…" />

      </div>

      {/* Single Filters button + panel */}
      <div ref={ref}>
        <button className={`filters-btn${committed > 0 ? " has" : ""}`} onClick={() => setOpen(o => !o)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 4h18l-7 8v6l-4 2v-8z"/>
          </svg>
          Filters
          {committed > 0 && <span className="fb-count">{committed}</span>}
          <svg className="caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        {open && (
          <div className="filter-panel">
            <div className="fp-head">
              <span className="fp-title">Filters</span>
              <button className="fp-reset" onClick={resetAll}>Reset all</button>
            </div>
            <div className="fp-accordion">
              <AccordionSection label="Department" count={draft.category.length}>
                <DeptSelector selected={draft.category} onChange={v => setDraft(d => ({ ...d, category: v }))} />
              </AccordionSection>
              {groups.map(([key, label, opts]) => (
                <AccordionSection key={key} label={label} count={(draft[key] as string[]).length}>
                  <div className="acc-opts">
                    {opts.map(o => {
                      const arr = draft[key] as string[];
                      return (
                        <label key={o} className={`fp-check${arr.includes(o) ? " on" : ""}`} onClick={() => toggle(key, o)}>
                          <span className="fp-box">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6 9 17l-5-5"/></svg>
                          </span>
                          {o}
                        </label>
                      );
                    })}
                  </div>
                </AccordionSection>
              ))}
              <AccordionSection label="Match Score" count={draft.score !== "any" ? 1 : 0}>
                <div className="acc-opts acc-pills">
                  {scoreOpts.map(([v, l]) => (
                    <label key={v} className={`fp-radio${draft.score === v ? " on" : ""}`} onClick={() => setDraft(d => ({ ...d, score: v }))}>
                      <span className="fp-dot" />{l}
                    </label>
                  ))}
                </div>
              </AccordionSection>
            </div>
            <div className="fp-toggles">
              <div className="fp-toggle-row">
                <div>
                  <div className="fp-toggle-name">Visa filter</div>
                  <div className="fp-toggle-desc">Only show roles that sponsor visas</div>
                </div>
                <button className={`toggle${visaFilter ? " on" : ""}`} onClick={() => setVisaFilter(!visaFilter)}>
                  <span className="toggle-knob" />
                </button>
              </div>
              <div className="fp-toggle-row">
                <div>
                  <div className="fp-toggle-name">Experience filter</div>
                  <div className="fp-toggle-desc">Hide overqualified roles (Principal, Director, VP+)</div>
                </div>
                <button className={`toggle${expFilter ? " on" : ""}`} onClick={() => setExpFilter(!expFilter)}>
                  <span className="toggle-knob" />
                </button>
              </div>
            </div>
            <div className="fp-foot">
              <span className="fp-summary"><b>{draftCount}</b> filter{draftCount === 1 ? "" : "s"} selected</span>
              <button className="fp-apply" onClick={apply}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6 9 17l-5-5"/></svg>
                Apply filters
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="fb-divider" />
      <span className="fb-time-label">Posted</span>
      <div className="segchips">
        {timeOpts.map(([v, l]) => (
          <button key={v} className={filters.time === v ? "on" : ""} onClick={() => set("time", v)}>{l}</button>
        ))}
      </div>

      <div className="fb-divider" />
      <span className="fb-time-label">HC Job Age</span>
      <div className="segchips">
        {([ ["any","Any"], ["fresh","Fresh ≤14d"], ["recent","Recent ≤90d"], ["old","Old 90d+"] ] as [Filters["hcAge"], string][]).map(([v, l]) => (
          <button key={v} className={filters.hcAge === v ? "on" : ""} onClick={() => set("hcAge", v)}>{l}</button>
        ))}
      </div>
    </div>
  );
}
