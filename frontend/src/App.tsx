import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import type { Job, JobStatus, QualifyResult } from "./types";
import { api } from "./api";
import { checkVisa } from "./utils/visaCheck";
import { isLevelMatch } from "./utils/levelCheck";
import { JobCard } from "./components/JobCard";
import { Dashboard } from "./components/Dashboard";
import { Kanban } from "./components/Kanban";
import { QuickTailor } from "./components/QuickTailor";
import { Profile } from "./components/Profile";
import { Settings } from "./components/Settings";
import { JobDetail } from "./components/JobDetail";
import { Toasts, useToasts, Spinner } from "./components/primitives";

type View = "jobs" | "dashboard" | "profile" | "settings";
type ViewMode = "list" | "kanban";
type Filters = { posted: string; country: string; locType: string; source: string; status: string };

const COUNTRIES = ["All Countries", "USA", "India", "Remote"];
const SOURCES = ["All Sources","Greenhouse","Lever","Ashby","HiringCafe","Google","Apple","Meta","Netflix"];
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
  const [lastScrapedTs, setLastScrapedTs] = useState<string>("");  // ISO timestamp
  const [lastScrapedDisplay, setLastScrapedDisplay] = useState("");

  // Live-update "X min ago" every 30s
  useEffect(() => {
    if (!lastScrapedTs) return;
    const update = () => setLastScrapedDisplay(timeAgo(lastScrapedTs));
    update();
    const iv = setInterval(update, 30000);
    return () => clearInterval(iv);
  }, [lastScrapedTs]);
  const [tailorOpen, setTailorOpen] = useState(false);
  const [busy, setBusy]             = useState<string | null>(null);
  const [showWelcome, setShowWelcome] = useState(() => !localStorage.getItem("jh_welcomed"));
  const { toasts, toast }           = useToasts();
  const searchRef                   = useRef<HTMLInputElement>(null);
  const [profileName, setProfileName]     = useState("");
  const [profileVisa, setProfileVisa]     = useState("");
  useEffect(() => {
    api.getProfile().then((p: any) => {
      if (p?.name) setProfileName(p.name);
      if (p?.visa_status) setProfileVisa(p.visa_status);
    }).catch(() => {});
  }, []);
  const initials = profileName
    ? profileName.split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  const [filters, setFilters]       = useState<Filters>({
    posted: "72h", country: "All Countries", locType: "Any", source: "All Sources", status: "all",
  });

  const setF = (k: keyof Filters, v: string) => setFilters(f => ({ ...f, [k]: v }));

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

  const filterJob = useCallback((j: Job) =>
    checkVisa(j.title + " " + (j.description || "")).eligible && isLevelMatch(j.title), []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try { const raw = await api.getJobs(); const f = raw.filter(filterJob); setJobs(f); setAllJobs(f); }
    catch {} finally { setLoading(false); }
  }, [filterJob]);

  useEffect(() => { loadJobs(); }, [loadJobs]);
  useEffect(() => {
    api.getSettings().then((s: any) => { if (s.last_scraped_at) setLastScrapedTs(s.last_scraped_at); }).catch(() => {});
  }, []);

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

  const filteredJobs = useMemo(() => {
    const now = Date.now();
    const postedCutoff: Record<string, number> = { "24h": 24*3600000, "48h": 48*3600000, "72h": 72*3600000, "7d": 7*24*3600000 };
    const cutoffMs = postedCutoff[filters.posted] ?? Infinity;

    // Robust ISO parse — strips microseconds Python adds (e.g. .123456 → .123)
    const parseMs = (s: string): number | null => {
      if (!s) return null;
      const clean = s.replace(/(\.\d{3})\d+/, "$1");  // trim sub-ms digits
      const t = new Date(clean).getTime();
      return isNaN(t) ? null : t;
    };

    return jobs.filter(j => {
      if (filters.status !== "all" && j.status !== filters.status) return false;
      if (filters.country !== "All Countries" && j.country !== filters.country) return false;
      if (filters.locType === "Remote" && !j.remote) return false;
      if (filters.locType === "Onsite" && j.remote) return false;
      if (filters.source !== "All Sources" && j.source !== filters.source) return false;
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
  const filtersActive = filters.posted !== "72h" || filters.country !== "All Countries" || filters.locType !== "Any" || filters.source !== "All Sources" || filters.status !== "all";
  const navItems = [
    { id: "jobs", label: "Jobs", ic: IC.search },
    { id: "dashboard", label: "Dashboard", ic: IC.dash },
    { id: "profile", label: "My Profile", ic: IC.user },
    { id: "settings", label: "Settings", ic: IC.settings },
  ];

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <aside style={{ width: 208, flexShrink: 0, background: "var(--bg-surface)", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", height: "100%" }}>
        <div style={{ height: 52, flexShrink: 0, display: "flex", alignItems: "center", gap: 9, padding: "0 14px", borderBottom: "1px solid var(--border-subtle)" }}>
          <div style={{ width: 26, height: 26, borderRadius: 7, background: "linear-gradient(135deg,var(--accent),#1d4ed8)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 12px rgba(59,130,246,0.4)" }}>
            <Ic d={IC.target} size={14} color="#fff" />
          </div>
          <div style={{ lineHeight: 1.2 }}>
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em" }}>Job Hunter</div>
            <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Data Engineer</div>
          </div>
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
        {view === "jobs" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "0 14px 16px", borderTop: "1px solid var(--border-subtle)", marginTop: 2 }}>
            <span className="section-label">Posted Time</span>
            <div style={{ display: "flex", gap: 2, background: "var(--bg-base)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 2 }}>
              {["24h","48h","72h"].map(o => <button key={o} onClick={() => setF("posted", o)} className={"seg-btn" + (filters.posted === o ? " active" : "")}>{o}</button>)}
            </div>
            <span className="section-label">Country</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {COUNTRIES.map(c => {
                const active = filters.country === c;
                const count = c === "All Countries" ? allJobs.length : allJobs.filter(j => j.country === c).length;
                return <button key={c} onClick={() => setF("country", c)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: 28, padding: "0 8px", borderRadius: 6, fontSize: 12, color: active ? "var(--text-primary)" : "var(--text-secondary)", background: active ? "var(--bg-elevated)" : "transparent", transition: "all 120ms ease" }}><span>{c}</span><span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>{count}</span></button>;
              })}
            </div>
            <span className="section-label">Location Type</span>
            <div style={{ display: "flex", gap: 4 }}>
              {["Any","Remote","Onsite"].map(o => <button key={o} onClick={() => setF("locType", o)} className={"pill-btn" + (filters.locType === o ? " active" : "")}>{o}</button>)}
            </div>
            <span className="section-label">Source</span>
            <select value={filters.source} onChange={e => setF("source", e.target.value)} style={{ width: "100%", fontSize: 12, height: 32 }}>
              {SOURCES.map(s => <option key={s} value={s}>{s === "All Sources" ? "All Sources (" + allJobs.length + ")" : s + " (" + (sourceCounts[s] || 0) + ")"}</option>)}
            </select>
            <span className="section-label">Status</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {STATUS_ROWS.map(s => {
                const active = filters.status === s.id;
                return <button key={s.id} onClick={() => setF("status", s.id)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: 30, padding: "0 8px", borderRadius: 8, fontSize: 12.5, color: active ? "var(--text-primary)" : "var(--text-secondary)", background: active ? "var(--bg-elevated)" : "transparent", transition: "all 120ms ease" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ width: 7, height: 7, borderRadius: 999, background: s.color }} />{s.label}</span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>{statusCounts[s.id] || 0}</span>
                </button>;
              })}
            </div>
            {filtersActive && <button onClick={() => setFilters({ posted: "72h", country: "All Countries", locType: "Any", source: "All Sources", status: "all" })} className="clear-btn" style={{ marginTop: 14, fontSize: 11, color: "var(--text-muted)", padding: "4px 6px", borderRadius: 6, transition: "all 120ms ease" }}>Clear filters</button>}
          </div>
        )}
        {view !== "jobs" && <div style={{ flex: 1 }} />}
        <div style={{ flexShrink: 0, padding: "10px 12px", borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{ width: 26, height: 26, borderRadius: 999, background: "linear-gradient(135deg,#8b5cf6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#fff", flexShrink: 0 }}>{initials}</div>
          <div style={{ lineHeight: 1.2, overflow: "hidden", flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{profileName.split(" ")[0] || "Your Name"}</div>
            {profileVisa && <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{profileVisa}</div>}
          </div>
          <button
            onClick={() => setIsDark(d => !d)}
            title={isDark ? "Switch to Light" : "Switch to Dark"}
            style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)", transition: "all 120ms ease", fontSize: 14 }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-elevated)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; }}
          >
            {isDark ? "☀️" : "🌙"}
          </button>
        </div>
      </aside>

      {view === "dashboard" && <div style={{ flex: 1, overflow: "hidden" }}><Dashboard /></div>}
      {view === "profile"   && <div style={{ flex: 1, overflowY: "auto" }}><Profile /></div>}
      {view === "settings"  && <div style={{ flex: 1, overflowY: "auto" }}><Settings /></div>}

      {view === "jobs" && viewMode === "kanban" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
          <Topbar scraping={scraping} scrapeMsg={scrapeMsg} lastScraped={lastScrapedDisplay} onScrape={handleScrape} count={filteredJobs.length} viewMode={viewMode} setViewMode={setViewMode} IC={IC} />
          <Kanban jobs={filteredJobs} onStatusChange={(id, s) => handleStatusChange(id, s as JobStatus)} onSelect={id => { setViewMode("list"); handleSelect(id); }} />
        </div>
      )}

      {view === "jobs" && viewMode === "list" && (
        <>
          <section style={{ width: 380, flexShrink: 0, background: "var(--bg-base)", borderRight: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", height: "100%" }}>
            <Topbar scraping={scraping} scrapeMsg={scrapeMsg} lastScraped={lastScrapedDisplay} onScrape={handleScrape} count={filteredJobs.length} viewMode={viewMode} setViewMode={setViewMode} IC={IC} />
            <div style={{ flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 14px 0" }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{filteredJobs.length} jobs</span>
                <button onClick={handleClearAll} className="btn btn-ghost btn-danger" style={{ height: 24, padding: "0 8px", fontSize: 11, border: "none" }}><Ic d={IC.trash} size={12} /> Clear All</button>
              </div>
              <div style={{ padding: "8px 14px 10px" }}>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <Ic d={IC.search} size={15} color="var(--text-muted)" style={{ position: "absolute", left: 11, pointerEvents: "none" }} />
                  <input ref={searchRef} type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search jobs, companies..." style={{ paddingLeft: 34, paddingRight: 44, height: 36, fontSize: 13 }} />
                  <span className="mono" style={{ position: "absolute", right: 10, fontSize: 10, color: "var(--text-muted)", border: "1px solid var(--border-default)", borderRadius: 4, padding: "1px 5px", pointerEvents: "none" }}>Ctrl+K</span>
                </div>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", paddingBottom: 16 }}>
              {loading ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "40%", gap: 10, color: "var(--text-muted)" }}><Spinner size={18} /> Loading...</div>
              ) : filteredJobs.length === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60%", gap: 12, padding: 24, textAlign: "center" }}>
                  <Ic d={IC.search} size={34} color="var(--text-disabled)" />
                  <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>No jobs match your filters</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{allJobs.length === 0 ? "Click Scrape Now to fetch jobs" : "Try clearing filters"}</div>
                </div>
              ) : filteredJobs.map((job, i) => (
                <div key={job.id}>
                  <JobCard job={job} index={i} selected={selectedId === job.id} isFresh={false} onClick={() => handleSelect(job.id)} onQualifyUpdated={(id, r) => updateJob(id, { qualify_result: r })} />
                  {i < filteredJobs.length - 1 && selectedId !== job.id && selectedId !== filteredJobs[i + 1]?.id && <div style={{ height: 1, background: "var(--border-subtle)", margin: "0 16px" }} />}
                </div>
              ))}
            </div>
          </section>
          <JobDetail job={selectedJob} tab={tab} setTab={setTab} onUpdate={(patch: Partial<Job>) => selectedJob && updateJob(selectedJob.id, patch)} onToast={toast} busy={busy} runAction={runAction} />
        </>
      )}

      <QuickTailor open={tailorOpen} onClose={() => setTailorOpen(false)} onToast={toast} />
      <Toasts toasts={toasts} />

      {/* Welcome modal — first time only */}
      {showWelcome && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 16, padding: "36px 40px", maxWidth: 520, width: "100%", boxShadow: "0 24px 80px rgba(0,0,0,0.5)" }}>
            {/* Logo + title */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: "linear-gradient(135deg,var(--accent),#1d4ed8)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 20px rgba(59,130,246,0.4)" }}>
                <Ic d={IC.target} size={20} color="#fff" />
              </div>
              <div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>Welcome to Job Hunter</div>
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

function Topbar({ scraping, scrapeMsg, lastScraped, onScrape, count, viewMode, setViewMode, IC }: {
  scraping: boolean; scrapeMsg: string; lastScraped: string; onScrape: () => void;
  count: number; viewMode: string; setViewMode: (m: ViewMode) => void; IC: Record<string,string>;
}) {
  return (
    <div style={{ height: 48, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", borderBottom: "1px solid var(--border-subtle)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button className="btn btn-accent" onClick={onScrape} disabled={scraping} style={{ height: 30 }}>
          {scraping ? <Spinner size={13} color="#fff" /> : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.refresh }} />}
          {scraping ? "Scraping..." : "Scrape Now"}
        </button>
        {scrapeMsg && !scraping && <span style={{ fontSize: 11, fontWeight: 600, color: "#4ade80" }}>{scrapeMsg}</span>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {lastScraped && <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-muted)" }}><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: IC.clock }} /> {lastScraped}</span>}
        <div style={{ display: "flex", gap: 2, background: "var(--bg-elevated)", borderRadius: 8, padding: 2, border: "1px solid var(--border-subtle)" }}>
          {([["list", IC.list], ["kanban", IC.kanban]] as [string, string][]).map(([m, d]) => (
            <button key={m} onClick={() => setViewMode(m as ViewMode)} style={{ width: 28, height: 24, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", color: viewMode === m ? "var(--text-primary)" : "var(--text-muted)", background: viewMode === m ? "var(--bg-hover)" : "transparent", transition: "all 120ms ease" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: d }} />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
