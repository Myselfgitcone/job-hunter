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

function TagInput({ tags, setTags, placeholder, suggestions, externalSuggestions = [] }: {
  tags: string[]; setTags: (t: string[]) => void; placeholder?: string; suggestions?: string[]; externalSuggestions?: string[];
}) {
  const [val, setVal] = useState("");
  const add = (t: string) => { t = t.trim(); if (t && !tags.includes(t)) setTags([...tags, t]); setVal(""); };
  
  const displaySuggestions = React.useMemo(() => {
    if (!val.trim()) {
      return ["Data Engineer", "Software Engineer", "Product Manager", "Backend Engineer", "Full Stack Engineer"].filter(s => !tags.includes(s));
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
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [extRoles, setExtRoles] = useState<string[]>(externalRolesCache);

  useEffect(() => {
    if (open) {
      setLoading(true);
      api.getSettings().then((s: any) => {
        if (!s) return;
        const r = Array.isArray(s.job_roles) ? s.job_roles : JSON.parse(s.job_roles || "[]");
        setRoles(r);
      }).finally(() => setLoading(false));

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

  if (!open) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const s: any = await api.getSettings();
      await api.saveSettings({
        ...s,
        job_roles: roles,
      } as any);
      onToast("Job Preferences saved", "success");
      onSaved({ ...s, job_roles: roles });
      onClose();
    } catch {
      onToast("Failed to save preferences", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 999 }} onClick={onClose} />
      <div style={{ position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 1000, background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 16, width: 420, boxShadow: "0 12px 30px -10px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)", animation: "modalIn 200ms cubic-bezier(0.16, 1, 0.3, 1)", overflow: "hidden" }}>
        
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

        <div style={{ padding: "0 28px 28px" }}>
          {loading ? (
            <div style={{ color: "var(--tx-3)", fontSize: 14, padding: "20px 0" }}>Loading preferences...</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label style={{ fontSize: 13.5, fontWeight: 600, color: "var(--tx)", display: "flex", alignItems: "center", gap: 6 }}>
                Target Roles
                <span style={{ background: "rgba(124,58,237,0.1)", color: "var(--violet)", padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700 }}>{roles.length} / 5</span>
              </label>
              <TagInput
                tags={roles}
                setTags={setRoles}
                placeholder="Type a role and press Enter…"
                suggestions={ALL_ROLES}
                externalSuggestions={extRoles}
              />
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, padding: "18px 28px", borderTop: "1px solid var(--line)", background: "var(--bg-base)", boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)" }}>
          <button onClick={onClose} style={{ height: 40, padding: "0 20px", borderRadius: 10, background: "transparent", border: "1px solid var(--line)", color: "var(--tx-2)", fontSize: 14, fontWeight: 600, cursor: "pointer", transition: "all 0.2s" }} onMouseOver={e => { e.currentTarget.style.background = "var(--bg-elevated)"; e.currentTarget.style.color = "var(--tx)"; }} onMouseOut={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--tx-2)"; }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} style={{ height: 40, padding: "0 24px", borderRadius: 10, background: "var(--grad)", border: "none", color: "#fff", fontSize: 14, fontWeight: 600, cursor: saving ? "default" : "pointer", opacity: saving ? 0.7 : 1, boxShadow: "0 4px 14px 0 rgba(124,58,237,0.39)", transition: "transform 0.1s" }} onMouseDown={e => !saving && (e.currentTarget.style.transform = "scale(0.97)")} onMouseUp={e => !saving && (e.currentTarget.style.transform = "scale(1)")} onMouseLeave={e => !saving && (e.currentTarget.style.transform = "scale(1)")}>
            {saving ? "Saving..." : "Save Preferences"}
          </button>
        </div>

      </div>
    </>
  );
}
