import { useState, useEffect, useRef } from "react";
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
  return `(${(diffMonths / 12).toFixed(1)} yrs)`;
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
};

// ── Field primitive ───────────────────────────────────────────────────────────
function Field({ label, value, onChange, type, placeholder, full }: {
  label: React.ReactNode; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; full?: boolean;
}) {
  return (
    <label className={`field${full ? " full" : ""}`}>
      <span className="field-label">{label}</span>
      <input type={type || "text"} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </label>
  );
}

// ── RepeatCard ────────────────────────────────────────────────────────────────
function RepeatCard({ children, onRemove, index }: { children: React.ReactNode; onRemove: () => void; index: number }) {
  return (
    <div className="repeat-card">
      <span className="repeat-num">{String(index + 1).padStart(2, "0")}</span>
      <div className="repeat-body">{children}</div>
      <button className="repeat-del" onClick={onRemove} title="Remove"><Ic d={I.x} size={14} /></button>
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
  const [profile, setProfile] = useState<any>({
    personal: { firstName: "", middleName: "", lastName: "", email: "", phone: "", address: "", linkedin: "", github: "", visa: "" },
    experience: [] as any[],
    education: [] as any[],
    projects: [] as any[],
    skills: [] as string[],
    certifications: [] as string[],
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [parseTime, setParseTime] = useState(0);
  const [parseError, setParseError] = useState("");
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
        }));
        const edu = (p.education || []).map((e: any) => ({
          degree: e.degree || "", school: e.school || "", year: e.year || "", gpa: e.gpa || "",
        }));
        const proj = (p.projects || []).map((pr: any) => ({
          name: pr.name || "", stack: pr.stack || pr.description || "", desc: pr.description || "", url: pr.url || "",
        }));
        
        const nameParts = (p.name || "").split(" ");
        const first = nameParts[0] || "";
        const last = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
        const middle = nameParts.length > 2 ? nameParts.slice(1, -1).join(" ") : "";

        setProfile({
          personal: {
            firstName: first, middleName: middle, lastName: last, 
            email: p.email || "", phone: p.phone || "",
            address: p.address || p.location || "", linkedin: p.linkedin || "", github: p.github || "",
            visa: p.visa_status || "",
          },
          experience: exp, education: edu, projects: proj,
          skills: p.skills || [],
          certifications: p.certifications || [],
        });
      }
    }).catch(() => {});
  }, []);

  const pset = (k: string, v: string) => setProfile((p: any) => ({ ...p, personal: { ...p.personal, [k]: v } }));
  const updateAt = (key: "experience" | "education" | "projects", i: number, k: string, v: string) =>
    setProfile((p: any) => ({ ...p, [key]: p[key].map((x: any, j: number) => j === i ? { ...x, [k]: v } : x) }));

  const clearAll = () => {
    if (!window.confirm("Are you sure you want to clear your entire profile? This cannot be undone until you save again.")) return;
    setProfile({
      personal: { firstName: "", middleName: "", lastName: "", email: "", phone: "", address: "", linkedin: "", github: "", visa: "" },
      experience: [], education: [], projects: [], skills: [], certifications: [],
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      // Map back to API format
      const payload = {
        name: [profile.personal.firstName, profile.personal.middleName, profile.personal.lastName].filter(Boolean).join(" "),
        email: profile.personal.email,
        phone: profile.personal.phone, address: profile.personal.address,
        linkedin: profile.personal.linkedin, github: profile.personal.github,
        visa_status: profile.personal.visa,
        experience: profile.experience.map((e: any) => ({
          role: e.title, company: e.company, start_date: e.start, end_date: e.end,
          bullets: e.desc ? e.desc.split("\n").map((b: string) => b.replace(/^[\s•\-\.]*/, "").trim()).filter(Boolean) : [], years: 0,
        })),
        education: profile.education,
        projects: profile.projects.map((pr: any) => ({ name: pr.name, description: pr.stack || pr.desc, url: pr.url })),
        skills: profile.skills,
        certifications: profile.certifications,
      };
      await api.saveProfile(payload as any);
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch {} finally { setSaving(false); }
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
        
        const nameParts = (parsed.name || "").split(" ");
        const first = nameParts[0] || "";
        const last = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
        const middle = nameParts.length > 2 ? nameParts.slice(1, -1).join(" ") : "";

        setProfile((prev: any) => ({
          ...prev,
          personal: {
            ...prev.personal,
            firstName: first           || prev.personal.firstName,
            middleName: middle         || prev.personal.middleName,
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
              <button className="act" onClick={() => fileRef.current?.click()} disabled={parsing} style={{ height: 38 }}>
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
              <button className="save-btn" onClick={save} disabled={saving}>
                <Ic d={I.check} size={15} /> {saved ? "Saved!" : saving ? "Saving…" : "Save Profile"}
              </button>
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
          <div className="field-grid">
            <Field label="First Name"   value={P.personal.firstName} onChange={v => pset("firstName", v)} />
            <Field label="Middle Name"  value={P.personal.middleName} onChange={v => pset("middleName", v)} />
            <Field label="Last Name"    value={P.personal.lastName}  onChange={v => pset("lastName", v)} />
            <Field label="Email"        type="email" value={P.personal.email} onChange={v => pset("email", v)} />
            <Field label="Phone"        value={P.personal.phone}     onChange={v => pset("phone", v)} />
            <Field label="Address"      value={P.personal.address}   onChange={v => pset("address", v)} placeholder="City, State, Country" />
            <Field label="LinkedIn URL" value={P.personal.linkedin}  onChange={v => pset("linkedin", v)} />
            <Field label="GitHub URL"   value={P.personal.github}    onChange={v => pset("github", v)} />
            <label className="field">
              <span className="field-label">Visa Status</span>
              <select value={P.personal.visa} onChange={e => pset("visa", e.target.value)}>
                <option value="" disabled>Select Visa Status</option>
                {VISA_OPTIONS.map(o => <option key={o}>{o}</option>)}
              </select>
            </label>
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
            <RepeatCard key={i} index={i} onRemove={() => setProfile((p: any) => ({ ...p, experience: p.experience.filter((_: any, j: number) => j !== i) }))}>
              <div className="field-grid">
                <Field label="Job Title" value={e.title}   onChange={v => updateAt("experience", i, "title", v)} />
                <Field label="Company"   value={e.company} onChange={v => updateAt("experience", i, "company", v)} />
                <Field label="Start Date" value={e.start}  onChange={v => updateAt("experience", i, "start", v)} placeholder="Jan 2021" />
                <Field 
                  label={<span>End Date <span style={{ color: "#60a5fa", marginLeft: 6, fontWeight: 500 }}>{calcYears(e.start, e.end)}</span></span>} 
                  value={e.end} onChange={v => updateAt("experience", i, "end", v)} placeholder="Present" 
                />
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
            <RepeatCard key={i} index={i} onRemove={() => setProfile((p: any) => ({ ...p, education: p.education.filter((_: any, j: number) => j !== i) }))}>
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
            <RepeatCard key={i} index={i} onRemove={() => setProfile((p: any) => ({ ...p, projects: p.projects.filter((_: any, j: number) => j !== i) }))}>
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

        <div className="form-foot" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button className="act" onClick={clearAll} style={{ background: "rgba(239,68,64,0.1)", color: "#ef4440", border: "1px solid rgba(239,68,64,0.2)" }}>
            Clear All
          </button>
          <button className="save-btn" onClick={save} disabled={saving}>
            <Ic d={I.check} size={15} /> {saved ? "Saved!" : saving ? "Saving…" : "Save Profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
