import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";

function calcYears(start: string, end: string) {
  if (!start) return "";
  const parseDate = (d: string) => {
    if (!d || d.toLowerCase() === "present") return new Date();
    const parsed = new Date(d);
    return isNaN(parsed.getTime()) ? null : parsed;
  };
  const s = parseDate(start);
  const e = parseDate(end);
  if (!s || !e) return "";
  const diffMonths = (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth());
  if (diffMonths < 0) return "";
  return `${(diffMonths / 12).toFixed(1)} yrs`;
}

// ── SVG icon helper ───────────────────────────────────────────────────────────
function Ic({ d, size = 16, color }: { d: string; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0 }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}
const I = {
  user:     '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 14 0v1"/>',
  briefcase:'<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
  doc:      '<path d="M14 3v5h5"/><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M8 13h8M8 17h6"/>',
  bolt:     '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  target:   '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  check:    '<path d="M20 6 9 17l-5-5"/>',
  x:        '<path d="M18 6 6 18M6 6l12 12"/>',
  upload:   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  mail:     '<path d="M4 7.00005L10.2 11.65C11.2667 12.45 12.7333 12.45 13.8 11.65L20 7"/><rect x="3" y="5" width="18" height="14" rx="2"/>',
  phone:    '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
  mapPin:   '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  linkedin: '<path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/>',
  github:   '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>',
  chevronUp: '<polyline points="18 15 12 9 6 15"/>',
  chevronDown: '<polyline points="6 9 12 15 18 9"/>',
  undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 00-9-9 9 9 0 00-6 2.3L3 13"/>',
  redo: '<path d="M21 7v6h-6"/><path d="M3 17a9 9 0 019-9 9 9 0 016 2.3l3 2.7"/>',
};

// ── Field primitive ───────────────────────────────────────────────────────────
function Field({ label, value, onChange, type, placeholder, full, readOnly, innerIcon }: {
  label: React.ReactNode; value: string; onChange?: (v: string) => void;
  type?: string; placeholder?: string; full?: boolean; readOnly?: boolean; innerIcon?: React.ReactNode;
}) {
  return (
    <label className={`field${full ? " full" : ""}`}>
      <span className="field-label">{label}</span>
      <div style={{ position: "relative" }}>
        {innerIcon && (
          <div style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "#6b7280", display: "flex", pointerEvents: "none" }}>
            {innerIcon}
          </div>
        )}
        <input 
          type={type || "text"} value={value} 
          onChange={e => onChange?.(e.target.value)} 
          placeholder={placeholder} 
          readOnly={readOnly}
          style={{
            ...(readOnly ? { background: "rgba(255,255,255,0.03)", color: "#9ca3af", cursor: "default", outline: "none", border: "1px solid rgba(255,255,255,0.05)" } : {}),
            ...(innerIcon ? { paddingLeft: 34 } : {})
          }}
        />
      </div>
    </label>
  );
}

// ── RepeatCard ────────────────────────────────────────────────────────────────
function RepeatCard({ children, onRemove, index, title, expanded = true, onToggle }: { children: React.ReactNode; onRemove: () => void; index: number; title?: string; expanded?: boolean; onToggle?: (v: boolean) => void }) {
  const [localExpanded, setLocalExpanded] = useState(expanded);
  const isExpanded = onToggle ? expanded : localExpanded;
  const toggle = () => {
    if (onToggle) onToggle(!isExpanded);
    else setLocalExpanded(!isExpanded);
  };

  return (
    <div className="repeat-card">
      <span className="repeat-num">{String(index + 1).padStart(2, "0")}</span>
      <div className="repeat-body" style={{ display: isExpanded ? "flex" : "none" }}>{children}</div>
      {!isExpanded && (
        <div style={{ flex: 1, padding: "9px 0", color: "#4b5563", fontWeight: 500, fontSize: 14 }}>
          {title || "Untitled"}
        </div>
      )}
      <div className="repeat-actions">
        <button className="repeat-act" onClick={toggle} title={isExpanded ? "Collapse" : "Expand"}>
          <Ic d={isExpanded ? I.chevronUp : I.chevronDown} size={15} />
        </button>
        <button className="repeat-act red" onClick={onRemove} title="Remove">
          <Ic d={I.x} size={15} />
        </button>
      </div>
    </div>
  );
}

// ── TagInput ──────────────────────────────────────────────────────────────────
function TagInput({ tags, setTags, placeholder, suggestions }: {
  tags: string[]; setTags: (t: string[]) => void; placeholder?: string; suggestions?: string[];
}) {
  const [val, setVal] = useState("");
  const add = (t: string) => { t = t.trim(); if (t && !tags.includes(t)) setTags([...tags, t]); setVal(""); };
  return (
    <div>
      <div className="taginput" onClick={e => (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus()}>
        {tags.map(t => (
          <span className="tag-pill" key={t}>
            {t}
            <button onClick={() => setTags(tags.filter(x => x !== t))}><Ic d={I.x} size={11} /></button>
          </span>
        ))}
        <input value={val} onChange={e => setVal(e.target.value)} placeholder={tags.length ? "" : placeholder}
          onKeyDown={e => {
            if (e.key === "Enter") { e.preventDefault(); add(val); }
            else if (e.key === "Backspace" && !val && tags.length) setTags(tags.slice(0, -1));
          }} />
      </div>
      {suggestions && (
        <div className="tag-suggest">
          {suggestions.filter(s => !tags.includes(s)).map(s => (
            <button key={s} className="tag-sg" onClick={() => add(s)}>+ {s}</button>
          ))}
        </div>
      )}
    </div>
  );
}

const VISA_OPTIONS = ["US Citizen", "Green Card", "H1B", "OPT / CPT", "TN Visa", "Need Sponsorship"];

export function Profile() {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDeleteAccount = async () => {
    setIsDeleting(true);
    try {
      await api.deleteAccount();
      localStorage.removeItem("jh_token");
      localStorage.removeItem("jh_user");
      window.location.reload();
    } catch (err: any) {
      alert("Failed to delete account: " + err.message);
      setIsDeleting(false);
      setShowDeleteModal(false);
    }
  };

  const [profile, _setProfile] = useState<any>({
    personal: { firstName: "", lastName: "", email: "", phone: "", address: "", linkedin: "", github: "", visa: "" },
    experience: [] as any[],
    education: [] as any[],
    projects: [] as any[],
    skills: [] as string[],
    certifications: [] as string[],
  });

  // ── History & Auto-Save State ────────────────────────────────────────────────
  const [past, setPast] = useState<any[]>([]);
  const [future, setFuture] = useState<any[]>([]);
  const lastPushRef = useRef(Date.now());
  const initialLoadRef = useRef(true);
  
  const [saveStatus, setSaveStatus] = useState<"saved" | "unsaved" | "saving">("saved");
  const saveTimeoutRef = useRef<number | null>(null);

  const setProfile = useCallback((valOrFn: any) => {
    _setProfile((prev: any) => {
      const next = typeof valOrFn === "function" ? valOrFn(prev) : valOrFn;
      const now = Date.now();
      if (now - lastPushRef.current > 800) setPast(p => [...p, prev].slice(-50));
      lastPushRef.current = now;
      setFuture([]);
      return next;
    });
  }, []);

  const undo = useCallback(() => {
    setPast(p => {
      if (p.length === 0) return p;
      const newPast = [...p]; const prev = newPast.pop();
      _setProfile((current: any) => { setFuture(f => [current, ...f].slice(0, 50)); return prev; });
      return newPast;
    });
  }, []);

  const redo = useCallback(() => {
    setFuture(f => {
      if (f.length === 0) return f;
      const newFuture = [...f]; const next = newFuture.shift();
      _setProfile((current: any) => { setPast(p => [...p, current].slice(-50)); return next; });
      return newFuture;
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName.toLowerCase();
      if (tag === "input" || tag === "textarea") return; // Let native handle it
      if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
      if ((e.ctrlKey || e.metaKey) && e.key === "y") { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [undo, redo]);

  useEffect(() => {
    if (initialLoadRef.current) return;
    setSaveStatus("unsaved");
    if (saveTimeoutRef.current) window.clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = window.setTimeout(async () => {
      setSaveStatus("saving");
      try {
        const payload = {
          name: [profile.personal.firstName, profile.personal.lastName].filter(Boolean).join(" "),
          email: profile.personal.email, phone: profile.personal.phone, address: profile.personal.address,
          linkedin: profile.personal.linkedin, github: profile.personal.github, visa_status: profile.personal.visa,
          experience: profile.experience.map((e: any) => ({
            role: e.title, company: e.company, start_date: e.start, end_date: e.end,
            bullets: e.desc ? e.desc.split("\n").map((b: string) => b.replace(/^[\s•\-\.]*/, "").trim()).filter(Boolean) : [], years: 0,
            expanded: e.expanded !== false,
          })),
          education: profile.education.map((e: any) => ({ ...e, expanded: e.expanded !== false })),
          projects: profile.projects.map((pr: any) => ({ name: pr.name, description: pr.stack || pr.desc, url: pr.url, expanded: pr.expanded !== false })),
          skills: profile.skills, certifications: profile.certifications,
        };
        await api.saveProfile(payload as any);
        setSaveStatus("saved");
      } catch { setSaveStatus("unsaved"); }
    }, 1500);
    return () => window.clearTimeout(saveTimeoutRef.current!);
  }, [profile]);
  // ─────────────────────────────────────────────────────────────────────────────
  const [parsing, setParsing] = useState(false);
  const [parseTime, setParseTime] = useState(0);
  const [parseError, setParseError] = useState("");
  const [namePermutations, setNamePermutations] = useState<{first: string, last: string}[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    api.getProfile().then((p: any) => {
      if (p) {
        // Map API profile format to design format
        const exp = (p.experience || []).map((e: any) => ({
          title: e.role || e.title || "", company: e.company || "",
          start: e.start_date || e.start || "", end: e.end_date || e.end || "Present",
          desc: (e.bullets || []).map((b: string) => b.replace(/^[\s•\-\.]*/, "• ")).join("\n") || e.desc || "",
          expanded: e.expanded !== false,
        }));
        const edu = (p.education || []).map((e: any) => ({
          degree: e.degree || "", school: e.school || "", year: e.year || "", gpa: e.gpa || "",
          expanded: e.expanded !== false,
        }));
        const proj = (p.projects || []).map((pr: any) => ({
          name: pr.name || "", stack: pr.stack || pr.description || "", desc: pr.description || "", url: pr.url || "",
          expanded: pr.expanded !== false,
        }));
        
        const nameParts = (p.name || "").split(" ");
        const first = nameParts[0] || "";
        const last = nameParts.length > 1 ? nameParts.slice(1).join(" ") : "";

        _setProfile({
          personal: {
            firstName: first, lastName: last, 
            email: p.email || "", phone: p.phone || "",
            address: p.address || p.location || "", linkedin: p.linkedin || "", github: p.github || "",
            visa: p.visa_status || "",
          },
          experience: exp, education: edu, projects: proj,
          skills: p.skills || [],
          certifications: p.certifications || [],
        });
        setTimeout(() => { initialLoadRef.current = false; }, 100);
      }
    }).catch(() => {});
  }, []);

  const pset = (k: string, v: string) => setProfile((p: any) => ({ ...p, personal: { ...p.personal, [k]: v } }));
  const updateAt = (key: "experience" | "education" | "projects", i: number, k: string, v: string) =>
    setProfile((p: any) => ({ ...p, [key]: p[key].map((x: any, j: number) => j === i ? { ...x, [k]: v } : x) }));

  const clearAll = () => {
    if (!window.confirm("Are you sure you want to clear your entire profile? This cannot be undone until you save again.")) return;
    setProfile({
      personal: { firstName: "", lastName: "", email: "", phone: "", address: "", linkedin: "", github: "", visa: "" },
      experience: [], education: [], projects: [], skills: [], certifications: [],
    });
  };

  const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);
  useEffect(() => {
    api.getSettings().then((s: any) => setHasApiKey(!!(s && s.ai_api_key))).catch(() => {});
  }, []);

  const handleUploadClick = () => {
    if (hasApiKey === false) {
      setParseError("No AI API key found! Please go to Settings and add your API key before uploading a resume.");
      return;
    }
    fileRef.current?.click();
  };



  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;

    setParsing(true);
    setParseError("");
    setParseTime(0);
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(() => setParseTime(t => t + 1), 1000);
    try {
      const parsed = await api.parseResume(file);
      if (parsed) {
        const exp = (parsed.experience || []).map((e: any) => ({
          title:   e.role || e.title || "",
          company: e.company || "",
          start:   e.start_date || e.start || "",
          end:     e.end_date || e.end || "Present",
          desc:    Array.isArray(e.bullets) ? e.bullets.map((b: string) => b.replace(/^[\s•\-\.]*/, "• ")).join("\n") : (e.desc || ""),
        }));
        const edu = (parsed.education || []).map((e: any) => ({
          degree: e.degree || "",
          school: e.school || "",
          year:   e.year || "",
          gpa:    e.gpa || "",
        }));
        const proj = (parsed.projects || []).map((pr: any) => ({
          name:  pr.name || "",
          stack: pr.stack || pr.description || "",
          desc:  pr.description || "",
          url:   pr.url || "",
        }));
        
        const nameParts = (parsed.name || "").split(" ").filter(Boolean);
        const first = nameParts[0] || "";
        const last = nameParts.length > 1 ? nameParts.slice(1).join(" ") : "";

        if (nameParts.length >= 3) {
          const perms = [];
          for (let i = 1; i < nameParts.length; i++) {
            perms.push({ first: nameParts.slice(0, i).join(" "), last: nameParts.slice(i).join(" ") });
          }
          setNamePermutations(perms);
        } else {
          setNamePermutations([]);
        }

        setProfile((prev: any) => ({
          ...prev,
          personal: {
            ...prev.personal,
            firstName: first           || prev.personal.firstName,
            lastName:  last            || prev.personal.lastName,
            email:    parsed.email     || prev.personal.email,
            phone:    parsed.phone     || prev.personal.phone,
            address:  parsed.location  || prev.personal.address,
            linkedin: parsed.linkedin  || prev.personal.linkedin,
            github:   parsed.github    || prev.personal.github,
          },
          summary:    parsed.summary   || prev.summary || "",
          experience: exp.length   ? exp   : prev.experience,
          education:  edu.length   ? edu   : prev.education,
          projects:   proj.length  ? proj  : prev.projects,
          skills:     parsed.skills?.length ? parsed.skills : prev.skills,
          certifications: parsed.certifications?.length ? parsed.certifications : prev.certifications,
        }));
      }
    } catch (err: any) {
      setParseError(err?.message || "Resume parse failed. Check AI key in Settings.");
    } finally { 
      setParsing(false); 
      if (timerRef.current) window.clearInterval(timerRef.current);
    }
    e.target.value = "";
  };


  const P = profile;

  return (
    <div className="form-scroll">
      <div className="form-inner">
        <div className="form-head">
          <div>
            <h1 className="dash-title">My Profile</h1>
            <p className="dash-sub">The source your AI tailoring and scoring pull from</p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="act primary" onClick={handleUploadClick} disabled={parsing} style={{ height: 38, padding: "0 16px" }}>
                {parsing ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    Parsing…
                    <div style={{ width: 22, height: 22, borderRadius: "50%", background: "rgba(255,255,255,0.2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: "bold" }}>
                      {parseTime}s
                    </div>
                  </div>
                ) : <><Ic d={I.upload} size={15} /> Upload Resume</>}
              </button>
              <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" style={{ display: "none" }} onChange={handleUpload} />
              
              <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--grad-soft)", padding: "6px 12px", borderRadius: 8, border: "1px solid rgba(124,58,237,0.25)", boxShadow: "0 1px 2px rgba(124,58,237,0.05)", height: 38, boxSizing: "border-box" }}>
                <div style={{ display: "flex", gap: 2 }}>
                  <button onClick={undo} disabled={past.length === 0} style={{ background: "transparent", border: "none", color: past.length === 0 ? "rgba(124,58,237,0.3)" : "#4f46e5", cursor: past.length === 0 ? "default" : "pointer", padding: "4px 6px", borderRadius: 4, transition: "background 0.2s" }} title="Undo (Ctrl+Z)" onMouseOver={e => e.currentTarget.style.background = past.length === 0 ? "transparent" : "rgba(124,58,237,0.1)"} onMouseOut={e => e.currentTarget.style.background = "transparent"}><Ic d={I.undo} size={15} /></button>
                  <button onClick={redo} disabled={future.length === 0} style={{ background: "transparent", border: "none", color: future.length === 0 ? "rgba(124,58,237,0.3)" : "#4f46e5", cursor: future.length === 0 ? "default" : "pointer", padding: "4px 6px", borderRadius: 4, transition: "background 0.2s" }} title="Redo (Ctrl+Y)" onMouseOver={e => e.currentTarget.style.background = future.length === 0 ? "transparent" : "rgba(124,58,237,0.1)"} onMouseOut={e => e.currentTarget.style.background = "transparent"}><Ic d={I.redo} size={15} /></button>
                </div>
                <div style={{ width: 1, height: 16, background: "rgba(124,58,237,0.15)" }} />
                <div style={{ fontSize: 13, color: saveStatus === "unsaved" ? "#d97706" : saveStatus === "saving" ? "#3b82f6" : "#059669", display: "flex", alignItems: "center", gap: 6, width: 70, justifyContent: "flex-end", fontWeight: 500 }}>
                  {saveStatus === "unsaved" && "Unsaved"}
                  {saveStatus === "saving" && "Saving..."}
                  {saveStatus === "saved" && <><Ic d={I.check} size={14} /> Saved</>}
                </div>
              </div>
            </div>
            {parseError && (
              <div style={{ fontSize: 12, color: "#f87171", background: "rgba(248,113,113,.08)", border: "1px solid rgba(248,113,113,.2)", borderRadius: 7, padding: "6px 12px", maxWidth: 380, textAlign: "right" }}>
                ⚠ {parseError}
              </div>
            )}
          </div>
        </div>

        {/* Personal Info */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.user} size={16} /> Personal Info</div>
          {namePermutations.length > 0 && (
            <div style={{ background: "rgba(59, 130, 246, 0.06)", border: "1px solid rgba(59, 130, 246, 0.15)", borderRadius: 8, padding: 12, marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 13, color: "#2563eb", fontWeight: 500 }}>Multi-word name detected. How should we split it?</span>
                <button onClick={() => setNamePermutations([])} style={{ background: "transparent", border: "none", color: "#3b82f6", cursor: "pointer", padding: 0 }}><Ic d={I.x} size={14} /></button>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {namePermutations.map((p, i) => (
                  <button key={i} onClick={() => {
                    setProfile((prev: any) => ({ ...prev, personal: { ...prev.personal, firstName: p.first, lastName: p.last } }));
                    setNamePermutations([]);
                  }} style={{ display: "flex", gap: 6, alignItems: "center", textAlign: "left", padding: "6px 12px", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 6, cursor: "pointer", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                    <span style={{ color: "#6b7280", fontSize: 12 }}>First:</span> <span style={{ color: "#111827", fontSize: 13, fontWeight: 500 }}>{p.first}</span>
                    <span style={{ color: "#6b7280", fontSize: 12, marginLeft: 6 }}>Last:</span> <span style={{ color: "#111827", fontSize: 13, fontWeight: 500 }}>{p.last}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="field-grid">
            <Field label="First name"   value={P.personal.firstName} onChange={v => pset("firstName", v)} />
            <Field label="Last name"    value={P.personal.lastName}  onChange={v => pset("lastName", v)} />
            <Field 
              label={<><span style={{display: "inline-flex", alignItems: "center", gap: 4}}><Ic d={I.mail} size={13} /> Email</span></>} 
              type="email" value={P.personal.email} onChange={v => pset("email", v)} 
            />
            <Field 
              label={<><span style={{display: "inline-flex", alignItems: "center", gap: 4}}><Ic d={I.phone} size={13} /> Phone</span></>} 
              value={P.personal.phone} onChange={v => pset("phone", v)} 
            />
            <Field 
              label={<><span style={{display: "inline-flex", alignItems: "center", gap: 4}}><Ic d={I.mapPin} size={13} /> Address</span></>} 
              value={P.personal.address} onChange={v => pset("address", v)} placeholder="City, State, Country" 
            />
            <label className="field">
              <span className="field-label">Visa status</span>
              <select value={P.personal.visa} onChange={e => pset("visa", e.target.value)}>
                <option value="" disabled>Select visa status</option>
                {VISA_OPTIONS.map(o => <option key={o}>{o}</option>)}
              </select>
            </label>
            <Field 
              label="LinkedIn" value={P.personal.linkedin} onChange={v => pset("linkedin", v)} 
              innerIcon={<Ic d={I.linkedin} size={16} />} placeholder="linkedin.com/in/..." 
            />
            <Field 
              label="GitHub" value={P.personal.github} onChange={v => pset("github", v)} 
              innerIcon={<Ic d={I.github} size={16} />} placeholder="github.com/..." 
            />
          </div>
        </section>

        {/* Work Experience */}
        <section className="form-section">
          <div className="section-label">
            <Ic d={I.briefcase} size={16} /> Work Experience
            <button className="add-btn" onClick={() => setProfile((p: any) => ({ ...p, experience: [...p.experience, { title: "", company: "", start: "", end: "Present", desc: "" }] }))}>
              + Add Experience
            </button>
          </div>
          {P.experience.map((e: any, i: number) => (
            <RepeatCard key={i} index={i} expanded={e.expanded} onToggle={v => updateAt("experience", i, "expanded", v as any)} title={e.title || e.company ? `${e.title}${e.title && e.company ? ' at ' : ''}${e.company}` : "New Experience"} onRemove={() => setProfile((p: any) => ({ ...p, experience: p.experience.filter((_: any, j: number) => j !== i) }))}>
              <div className="field-grid">
                <Field label="Job Title" value={e.title}   onChange={v => updateAt("experience", i, "title", v)} />
                <Field label="Company"   value={e.company} onChange={v => updateAt("experience", i, "company", v)} />
                <div style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "1fr 1fr 100px", gap: 14 }}>
                  <Field label="Start Date" value={e.start}  onChange={v => updateAt("experience", i, "start", v)} placeholder="Jan 2021" />
                  <Field label="End Date"   value={e.end}    onChange={v => updateAt("experience", i, "end", v)} placeholder="Present" />
                  <Field label="Total Exp"  value={calcYears(e.start, e.end)} placeholder="-" readOnly />
                </div>
              </div>
              <label className="field full">
                <span className="field-label">Description</span>
                <textarea value={e.desc} onChange={ev => updateAt("experience", i, "desc", ev.target.value)} />
              </label>
            </RepeatCard>
          ))}
        </section>

        {/* Education */}
        <section className="form-section">
          <div className="section-label">
            <Ic d={I.doc} size={16} /> Education
            <button className="add-btn" onClick={() => setProfile((p: any) => ({ ...p, education: [...p.education, { degree: "", school: "", year: "", gpa: "" }] }))}>
              + Add Education
            </button>
          </div>
          {P.education.map((e: any, i: number) => (
            <RepeatCard key={i} index={i} expanded={e.expanded} onToggle={v => updateAt("education", i, "expanded", v as any)} title={e.degree || e.school ? `${e.degree}${e.degree && e.school ? ' at ' : ''}${e.school}` : "New Education"} onRemove={() => setProfile((p: any) => ({ ...p, education: p.education.filter((_: any, j: number) => j !== i) }))}>
              <div className="field-grid">
                <Field label="Degree"           value={e.degree} onChange={v => updateAt("education", i, "degree", v)} />
                <Field label="School / University" value={e.school} onChange={v => updateAt("education", i, "school", v)} />
                <Field label="Year" value={e.year} onChange={v => updateAt("education", i, "year", v)} />
                <Field label="GPA"  value={e.gpa}  onChange={v => updateAt("education", i, "gpa", v)} />
              </div>
            </RepeatCard>
          ))}
        </section>

        {/* Projects */}
        <section className="form-section">
          <div className="section-label">
            <Ic d={I.bolt} size={16} /> Projects
            <button className="add-btn" onClick={() => setProfile((p: any) => ({ ...p, projects: [...p.projects, { name: "", stack: "", desc: "", url: "" }] }))}>
              + Add Project
            </button>
          </div>
          {P.projects.map((e: any, i: number) => (
            <RepeatCard key={i} index={i} expanded={e.expanded} onToggle={v => updateAt("projects", i, "expanded", v as any)} title={e.name || "New Project"} onRemove={() => setProfile((p: any) => ({ ...p, projects: p.projects.filter((_: any, j: number) => j !== i) }))}>
              <div className="field-grid">
                <Field label="Project Name" value={e.name}  onChange={v => updateAt("projects", i, "name", v)} />
                <Field label="Tech Stack"   value={e.stack} onChange={v => updateAt("projects", i, "stack", v)} />
                <Field label="URL"          value={e.url}   onChange={v => updateAt("projects", i, "url", v)} full />
              </div>
              <label className="field full">
                <span className="field-label">Description</span>
                <textarea value={e.desc} onChange={ev => updateAt("projects", i, "desc", ev.target.value)} />
              </label>
            </RepeatCard>
          ))}
        </section>

        <section className="form-section">
          <div className="section-label"><Ic d={I.target} size={16} /> Skills</div>
          <TagInput tags={P.skills} setTags={t => setProfile((p: any) => ({ ...p, skills: t }))}
            placeholder="Add a skill and press Enter…"
            suggestions={["Python","SQL","React","AWS","Docker"]} />
        </section>

        {/* Certifications */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.doc} size={16} /> Certifications</div>
          <TagInput tags={P.certifications} setTags={t => setProfile((p: any) => ({ ...p, certifications: t }))}
            placeholder="Add a certification and press Enter…"
            suggestions={["AWS Certified Solutions Architect", "Certified Kubernetes Administrator", "PMP"]} />
        </section>

        <section className="form-section" style={{ border: "1px solid rgba(239, 68, 64, 0.3)", background: "rgba(239, 68, 64, 0.02)" }}>
          <div className="section-label" style={{ color: "#ef4440" }}>
            <Ic d={I.x} size={16} /> Danger Zone
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 13, color: "var(--tx-2)" }}>
              Permanently delete your account and all associated data. This action cannot be undone.
            </div>
            <button className="act" onClick={() => setShowDeleteModal(true)} style={{ background: "#ef4440", color: "#fff", border: "none" }}>
              Delete Account
            </button>
          </div>
        </section>

        <div className="form-foot" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button className="act" onClick={clearAll} style={{ background: "rgba(239,68,64,0.1)", color: "#ef4440", border: "1px solid rgba(239,68,64,0.2)" }}>
            Clear All
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--grad-soft)", padding: "6px 12px", borderRadius: 8, border: "1px solid rgba(124,58,237,0.25)", boxShadow: "0 1px 2px rgba(124,58,237,0.05)", height: 38, boxSizing: "border-box" }}>
            <div style={{ display: "flex", gap: 2 }}>
              <button onClick={undo} disabled={past.length === 0} style={{ background: "transparent", border: "none", color: past.length === 0 ? "rgba(124,58,237,0.3)" : "#4f46e5", cursor: past.length === 0 ? "default" : "pointer", padding: "4px 6px", borderRadius: 4, transition: "background 0.2s" }} title="Undo (Ctrl+Z)" onMouseOver={e => e.currentTarget.style.background = past.length === 0 ? "transparent" : "rgba(124,58,237,0.1)"} onMouseOut={e => e.currentTarget.style.background = "transparent"}><Ic d={I.undo} size={15} /></button>
              <button onClick={redo} disabled={future.length === 0} style={{ background: "transparent", border: "none", color: future.length === 0 ? "rgba(124,58,237,0.3)" : "#4f46e5", cursor: future.length === 0 ? "default" : "pointer", padding: "4px 6px", borderRadius: 4, transition: "background 0.2s" }} title="Redo (Ctrl+Y)" onMouseOver={e => e.currentTarget.style.background = future.length === 0 ? "transparent" : "rgba(124,58,237,0.1)"} onMouseOut={e => e.currentTarget.style.background = "transparent"}><Ic d={I.redo} size={15} /></button>
            </div>
            <div style={{ width: 1, height: 16, background: "rgba(124,58,237,0.15)" }} />
            <div style={{ fontSize: 13, color: saveStatus === "unsaved" ? "#d97706" : saveStatus === "saving" ? "#3b82f6" : "#059669", display: "flex", alignItems: "center", gap: 6, width: 70, justifyContent: "flex-end", fontWeight: 500 }}>
              {saveStatus === "unsaved" && "Unsaved"}
              {saveStatus === "saving" && "Saving..."}
              {saveStatus === "saved" && <><Ic d={I.check} size={14} /> Saved</>}
            </div>
          </div>
        </div>
      </div>

      {showDeleteModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
          <div style={{ background: "var(--glass-hi)", backdropFilter: "blur(22px)", border: "1px solid var(--glass-border)", borderRadius: 20, padding: "32px", maxWidth: 440, width: "100%", boxShadow: "var(--sh-pop)", animation: "modalIn 220ms var(--ease)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <div style={{ width: 44, height: 44, borderRadius: 13, background: "rgba(239,68,64,0.1)", display: "flex", alignItems: "center", justifyContent: "center", color: "#ef4440" }}>
                <Ic d={I.x} size={24} />
              </div>
              <div>
                <div style={{ fontFamily: "var(--f-display)", fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em", color: "#ef4440" }}>Delete Account?</div>
                <div style={{ fontSize: 13, color: "var(--tx-3)", marginTop: 2 }}>This action is permanent</div>
              </div>
            </div>
            <div style={{ fontSize: 14, color: "var(--tx-2)", lineHeight: 1.6, marginBottom: 24 }}>
              Are you sure you want to delete your account? All your profile data, tailored resumes, and saved jobs will be permanently wiped from our database.
              <br /><br />
              <strong>You will need to register as a fresh user to use the app again.</strong>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={handleDeleteAccount} disabled={isDeleting} className="btn" style={{ flex: 1, height: 42, fontSize: 13.5, borderRadius: 11, background: "#ef4440", color: "#fff", border: "none" }}>
                {isDeleting ? "Deleting..." : "Yes, Delete Everything"}
              </button>
              <button onClick={() => setShowDeleteModal(false)} disabled={isDeleting} className="btn btn-subtle" style={{ height: 42, padding: "0 18px", borderRadius: 11 }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
