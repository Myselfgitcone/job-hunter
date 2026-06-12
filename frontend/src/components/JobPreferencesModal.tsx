import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { Icon as Ic } from './primitives';

const I = { x: '<path d="M18 6 6 18M6 6l12 12"/>' };

let externalRolesCache: string[] = [];
let fetchingExternalRoles = false;

const ALL_ROLES = [
  // Data & Analytics
  "Data Engineer", "Data Analyst", "Data Scientist", "Data Architect", "Database Administrator", "Analytics Engineer", "Business Intelligence Analyst", "Machine Learning Engineer", "AI Engineer", "MLOps Engineer", "Data Analytics Manager", "Big Data Engineer",
  
  // Software Engineering
  "Software Engineer", "Backend Engineer", "Frontend Engineer", "Full Stack Engineer", "Web Developer", "Mobile Developer", "iOS Developer", "Android Developer", "Firmware Engineer", "Embedded Systems Engineer", "Game Developer", "QA Engineer", "Test Automation Engineer", "SDET",

  // Product & Project Management
  "Product Manager", "Project Manager", "Scrum Master", "Product Owner", "Technical Program Manager", "Program Manager", "Business Analyst", "Agile Coach", "Release Manager",

  // IT, Cloud & Infrastructure
  "DevOps Engineer", "Site Reliability Engineer", "Cloud Architect", "Security Engineer", "Network Engineer", "Systems Administrator", "IT Manager", "Help Desk Technician", "IT Support Specialist", "Information Security Analyst", "Cloud Engineer",

  // Design & UX
  "UI Designer", "UX Designer", "Product Designer", "Graphic Designer", "Web Designer", "Art Director", "Creative Director", "UX Researcher", "Interaction Designer",

  // Sales & Account Management
  "Sales Associate", "Sales Manager", "Sales Assistant", "Sales Engineer", "Sales Representative", "Sales Director", "Account Executive", "Account Manager", "Key Account Manager", "Business Development Manager", "Business Development Representative", "Sales Development Representative", "VP of Sales", "Customer Success Manager",

  // Marketing
  "Marketing Manager", "Marketing Director", "Digital Marketing Specialist", "SEO Specialist", "Content Creator", "Content Manager", "Social Media Manager", "Product Marketing Manager", "Growth Hacker", "Copywriter",

  // Finance & HR
  "Financial Analyst", "Accountant", "Finance Manager", "Human Resources Manager", "HR Generalist", "Recruiter", "Talent Acquisition Specialist", "Operations Manager"
];

// Role families the scraper targets — mirrors TITLE_FILTER in
// backend/scrapers/fantasticjobs.py. Clicking a family selects all its roles.
export const ROLE_GROUPS: { group: string; items: string[] }[] = [
  // "Data Engineer" chip = wide net: any title with both data + engineer
  { group: "Data Engineer",         items: ["Data Engineer", "ETL Developer", "Data Platform", "Data Warehouse", "Data Architect", "Database Engineer", "Database Developer", "SQL Developer", "Software Engineer (Data)"] },
  { group: "Data Analyst",          items: ["Data Analyst", "Data Analytics", "Analytics Engineer", "Reporting Analyst"] },
  { group: "Business Intelligence", items: ["Business Intelligence", "BI Developer", "BI Analyst", "BI Engineer", "Power BI", "Tableau"] },
  // DevOps/SRE + Security scraping disabled — uncomment here AND in
  // backend/scrapers/fantasticjobs.py TITLE_FILTER to re-enable
  // { group: "DevOps / SRE",          items: ["DevOps", "SRE", "Site Reliability", "Platform Engineer", "Cloud Engineer"] },
  // { group: "Security",              items: ["Security Engineer", "Security Analyst", "SOC Analyst", "Cybersecurity", "Infosec", "Application Security"] },
  // "Java" = word-boundary match on title, catches ALL java titles incl. "Software Engineer (Java)"
  { group: "Java",                  items: ["Java", "Spring Boot", "Jakarta"] },
];

// Hierarchical selector: group header click = select/deselect entire family
function RoleGroupSelector({ selected, onChange }: { selected: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggleItem = (it: string) =>
    onChange(selected.includes(it) ? selected.filter(x => x !== it) : [...selected, it]);
  const toggleGroup = (g: { group: string; items: string[] }) => {
    const allOn = g.items.every(i => selected.includes(i));
    if (allOn) onChange(selected.filter(x => !g.items.includes(x)));
    else onChange([...selected, ...g.items.filter(i => !selected.includes(i))]);
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
      {ROLE_GROUPS.map(g => {
        const selCount = g.items.filter(i => selected.includes(i)).length;
        const allOn = selCount === g.items.length;
        const isOpen = open[g.group] ?? false;
        return (
          <div key={g.group} style={{ border: "1px solid var(--line)", borderRadius: 10, overflow: "hidden", background: "var(--bg-elevated)" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              <button onClick={() => toggleGroup(g)}
                style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
                <span style={{ width: 16, height: 16, borderRadius: 4, flexShrink: 0, display: "grid", placeItems: "center",
                  border: allOn ? "none" : "1.5px solid var(--line-hi)",
                  background: allOn ? "var(--violet)" : selCount > 0 ? "rgba(124,58,237,0.25)" : "transparent" }}>
                  {(allOn || selCount > 0) && (
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round"><path d={allOn ? "M20 6 9 17l-5-5" : "M5 12h14"} /></svg>
                  )}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--tx)" }}>{g.group}</span>
                {selCount > 0 && (
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--violet)", background: "rgba(124,58,237,0.1)", padding: "1px 7px", borderRadius: 999 }}>
                    {selCount}/{g.items.length}
                  </span>
                )}
              </button>
              <button onClick={() => setOpen(o => ({ ...o, [g.group]: !isOpen }))}
                style={{ background: "none", border: "none", cursor: "pointer", padding: "9px 12px", color: "var(--tx-3)", display: "flex" }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                  style={{ transition: "transform .15s", transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)" }}><path d="M6 9l6 6 6-6" /></svg>
              </button>
            </div>
            {isOpen && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "2px 12px 10px 36px" }}>
                {g.items.map(it => {
                  const on = selected.includes(it);
                  return (
                    <button key={it} onClick={() => toggleItem(it)}
                      style={{ fontSize: 12, fontWeight: 500, padding: "4px 11px", borderRadius: 999, cursor: "pointer",
                        border: on ? "1px solid rgba(124,58,237,0.4)" : "1px dashed var(--line-hi)",
                        background: on ? "var(--grad-soft)" : "transparent",
                        color: on ? "var(--violet)" : "var(--tx-3)" }}>
                      {on ? "✓ " : "+ "}{it}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TagInput({ tags, setTags, placeholder, suggestions, externalSuggestions = [] }: {
  tags: string[]; setTags: (t: string[]) => void; placeholder?: string; suggestions?: string[]; externalSuggestions?: string[];
}) {
  const [val, setVal] = useState("");
  const add = (t: string) => { t = t.trim(); if (t && !tags.includes(t)) setTags([...tags, t]); setVal(""); };
  
  const displaySuggestions = React.useMemo(() => {
    if (!val.trim()) {
      return [];  // grouped family selector below handles discovery
    }
    const lower = val.toLowerCase();
    
    let localMatches = (suggestions || []).filter(s => s.toLowerCase().includes(lower) && !tags.includes(s));
    
    // If we need more matches, search the massive external dictionary
    if (localMatches.length < 8 && externalSuggestions.length > 0) {
      const extMatches = externalSuggestions
        .filter(s => s.toLowerCase().includes(lower))
        // Convert to Title Case to look nice
        .map(s => s.replace(/\b\w/g, c => c.toUpperCase()))
        .filter(s => !tags.includes(s) && !localMatches.includes(s));
        
      localMatches = [...localMatches, ...extMatches];
    }
    
    return localMatches.slice(0, 10);
  }, [val, suggestions, tags, externalSuggestions]);

  return (
    <div style={{ width: "100%" }}>
      <div 
        className="taginput" 
        onClick={e => (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus()}
        style={{ 
          display: 'flex', flexWrap: 'wrap', gap: 8, padding: 12, 
          background: 'var(--bg-base-2)', border: '1px solid var(--line)', 
          borderRadius: 'var(--r-md)', minHeight: 48, cursor: 'text',
          transition: 'border-color 0.2s, box-shadow 0.2s'
        }}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--violet)'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(124,58,237,0.15)'; }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--line)'; e.currentTarget.style.boxShadow = 'none'; }}
      >
        {tags.map(t => (
          <span className="tag-pill" key={t} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--grad-soft)', color: 'var(--violet)', padding: '4px 10px', borderRadius: 999, fontSize: 12.5, fontWeight: 600, border: '1px solid rgba(124,58,237,0.2)' }}>
            {t}
            <button onClick={() => setTags(tags.filter(x => x !== t))} style={{ background: 'none', border: 'none', color: 'inherit', opacity: 0.7, padding: 0, cursor: 'pointer', display: 'flex' }} onMouseOver={e => e.currentTarget.style.opacity = '1'} onMouseOut={e => e.currentTarget.style.opacity = '0.7'}>
              <Ic name="x" size={12} />
            </button>
          </span>
        ))}
        <input 
          value={val} onChange={e => setVal(e.target.value)} placeholder={tags.length ? "" : placeholder}
          style={{ flex: 1, minWidth: 120, background: 'none', border: 'none', color: 'var(--tx)', fontSize: 13.5, outline: 'none' }}
          onKeyDown={e => {
            if (e.key === "Enter") { e.preventDefault(); add(val); }
            else if (e.key === "Backspace" && !val && tags.length) setTags(tags.slice(0, -1));
          }} 
        />
      </div>
      {displaySuggestions.length > 0 && (
        <div className="tag-suggest" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          {displaySuggestions.map(s => (
            <button key={s} className="tag-sg" onClick={() => add(s)} style={{ background: 'var(--bg-elevated)', border: '1px dashed var(--line)', color: 'var(--tx-3)', padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 500, cursor: 'pointer', transition: 'all 0.2s' }} onMouseOver={e => { e.currentTarget.style.color = 'var(--violet)'; e.currentTarget.style.borderColor = 'var(--violet)'; e.currentTarget.style.background = 'var(--grad-soft)'; }} onMouseOut={e => { e.currentTarget.style.color = 'var(--tx-3)'; e.currentTarget.style.borderColor = 'var(--line)'; e.currentTarget.style.background = 'var(--bg-elevated)'; }}>
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function JobPreferencesModal({
  open,
  onClose,
  onToast,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onToast: (msg: string, type?: "success" | "error") => void;
  onSaved: (newSettings: any) => void;
}) {
  const [roles, setRoles] = useState<string[]>([]);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [loading, setLoading] = useState(true);
  const [extRoles, setExtRoles] = useState<string[]>(externalRolesCache);
  const settingsRef = React.useRef<any>(null);
  const popRef = React.useRef<HTMLDivElement>(null);
  const saveTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedRef = React.useRef(false);

  useEffect(() => {
    if (open) {
      setLoading(true);
      loadedRef.current = false;
      setSaveState("idle");
      api.getSettings().then((s: any) => {
        if (!s) return;
        settingsRef.current = s;
        const r = Array.isArray(s.job_roles) ? s.job_roles : JSON.parse(s.job_roles || "[]");
        setRoles(r);
      }).finally(() => { setLoading(false); loadedRef.current = true; });

      // Fetch massive job dictionary if not cached
      if (externalRolesCache.length === 0 && !fetchingExternalRoles) {
        fetchingExternalRoles = true;
        fetch("https://raw.githubusercontent.com/jneidel/job-titles/master/job-titles.json")
          .then(res => res.json())
          .then(data => {
            if (data && data["job-titles"]) {
              externalRolesCache = data["job-titles"];
              setExtRoles(externalRolesCache);
            }
          })
          .catch(err => console.error("Failed to load massive roles dict", err));
      } else if (externalRolesCache.length > 0) {
        setExtRoles(externalRolesCache);
      }
    }
  }, [open]);

  // Auto-save: debounce 600ms after any role change
  useEffect(() => {
    if (!open || loading || !loadedRef.current) return;
    setSaveState("saving");
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        const s = settingsRef.current || {};
        await api.saveSettings({ ...s, job_roles: roles } as any);
        onSaved({ ...s, job_roles: roles });
        setSaveState("saved");
      } catch {
        setSaveState("idle");
        onToast("Failed to save preferences", "error");
      }
    }, 600);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles]);

  // Close on click outside the popover
  useEffect(() => {
    if (!open) return;
    const fn = (e: MouseEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div ref={popRef} style={{ position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 1000, background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 16, width: 420, boxShadow: "0 12px 30px -10px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)", animation: "modalIn 200ms cubic-bezier(0.16, 1, 0.3, 1)", overflow: "hidden",
        // Never grow past the viewport — header/footer stay pinned, middle scrolls
        maxHeight: "calc(100vh - 110px)", display: "flex", flexDirection: "column" }}>
        
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "24px 28px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 44, height: 44, borderRadius: 14, background: "var(--grad-soft)", border: "1px solid rgba(124,58,237,0.2)", color: "var(--violet)", boxShadow: "0 4px 20px -4px rgba(124,58,237,0.3)" }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></svg>
            </div>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--tx)", margin: 0, letterSpacing: "-0.02em" }}>Job Preferences</h2>
              <p style={{ margin: "4px 0 0 0", fontSize: 13, color: "var(--tx-3)" }}>Tailor your job feed to your exact career goals.</p>
            </div>
          </div>
          <button onClick={onClose} style={{ background: "var(--bg-elevated)", border: "1px solid var(--line)", color: "var(--tx-2)", cursor: "pointer", display: "flex", padding: 8, borderRadius: 10, transition: "all 0.2s" }} onMouseOver={e => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--tx)"; }} onMouseOut={e => { e.currentTarget.style.background = "var(--bg-elevated)"; e.currentTarget.style.color = "var(--tx-2)"; }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div style={{ padding: "0 28px 28px", overflowY: "auto", flex: 1, minHeight: 0 }}>
          {loading ? (
            <div style={{ color: "var(--tx-3)", fontSize: 14, padding: "20px 0" }}>Loading preferences...</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label style={{ fontSize: 13.5, fontWeight: 600, color: "var(--tx)", display: "flex", alignItems: "center", gap: 6 }}>
                Target Roles
                <span style={{ background: "rgba(124,58,237,0.1)", color: "var(--violet)", padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700 }}>{roles.length} selected</span>
              </label>
              <TagInput
                tags={roles}
                setTags={setRoles}
                placeholder="Type a role and press Enter…"
                suggestions={ALL_ROLES}
                externalSuggestions={extRoles}
              />
              <RoleGroupSelector selected={roles} onChange={setRoles} />
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "14px 28px", borderTop: "1px solid var(--line)", background: "var(--bg-base)", boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)", flexShrink: 0 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: saveState === "saved" ? "#16a34a" : "var(--tx-3)" }}>
            {saveState === "saving" ? "Saving…" : saveState === "saved" ? "✓ Saved" : "Changes save automatically"}
          </span>
          <button onClick={onClose} style={{ height: 38, padding: "0 22px", borderRadius: 10, background: "var(--grad)", border: "none", color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: "0 4px 14px 0 rgba(124,58,237,0.39)" }}>
            Done
          </button>
        </div>

      </div>
    </>
  );
}
