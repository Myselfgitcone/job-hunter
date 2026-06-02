import { useState, useEffect, useRef } from "react";
import { api } from "../api";
import type { ProfileData, ProfileExperience, ProfileEducation, ProfileProject } from "../types";
import { Plus, Trash2, Save, Loader2, CheckCircle2, User, Briefcase, GraduationCap, FolderOpen, Zap, Award, Upload, ChevronDown, ChevronRight } from "lucide-react";

const MONTHS: Record<string, number> = {
  jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11,
  january:0,february:1,march:2,april:3,june:5,july:6,august:7,september:8,october:9,november:10,december:11,
};

function parseDate(s: string): Date | null {
  if (!s) return null;
  const low = s.trim().toLowerCase();
  if (low === "present" || low === "current" || low === "now") return new Date();
  // "Sep 2023" or "09/2023" or "2023-09"
  const m1 = low.match(/([a-z]+)\s+(\d{4})/);
  if (m1 && MONTHS[m1[1]] !== undefined) return new Date(+m1[2], MONTHS[m1[1]], 1);
  const m2 = low.match(/(\d{1,2})[\/\-](\d{4})/);
  if (m2) return new Date(+m2[2], +m2[1] - 1, 1);
  const m3 = low.match(/(\d{4})[\/\-](\d{1,2})/);
  if (m3) return new Date(+m3[1], +m3[2] - 1, 1);
  return null;
}

function calcYears(start: string, end: string): number | null {
  const s = parseDate(start);
  const e = parseDate(end);
  if (!s || !e) return null;
  const months = (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth());
  return Math.round((months / 12) * 10) / 10;
}

const EMPTY_PROFILE: ProfileData = {
  name: "", email: "", phone: "", location: "", visa_status: "",
  experience: [], education: [], projects: [],
  skills: [], certifications: [],
};

const EMPTY_EXP: ProfileExperience = { role: "", company: "", start_date: "", end_date: "", years: 0, bullets: [""] };
const EMPTY_EDU: ProfileEducation = { degree: "", school: "", year: "" };
const EMPTY_PRJ: ProfileProject = { name: "", description: "" };

const INPUT = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500";
const LABEL = "block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1";
const SECTION = "bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4";

export function Profile() {
  const [profile, setProfile] = useState<ProfileData>(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [skillInput, setSkillInput] = useState("");
  const [certInput, setCertInput] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleCollapse = (key: string) =>
    setCollapsed(s => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });

  useEffect(() => {
    api.getProfile()
      .then(p => { if (p && Object.keys(p).length) setProfile(p); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await api.saveProfile(profile);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };

  const uploadResume = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setParsing(true);
    try {
      const parsed = await api.parseResume(file);
      // Recalculate years from dates — AI often miscalculates
      const experience = (parsed.experience || []).map(e => {
        const computed = calcYears(e.start_date || "", e.end_date || "");
        return { ...e, years: computed ?? e.years ?? 0 };
      });
      setProfile(p => ({
        name:           parsed.name           || p.name,
        email:          parsed.email          || p.email,
        phone:          parsed.phone          || p.phone,
        location:       parsed.location       || p.location,
        visa_status:    p.visa_status,
        experience:     experience.length          ? experience        : p.experience,
        education:      parsed.education?.length   ? parsed.education  : p.education,
        projects:       parsed.projects?.length    ? parsed.projects   : p.projects,
        skills:         parsed.skills?.length      ? parsed.skills     : p.skills,
        certifications: parsed.certifications?.length ? parsed.certifications : p.certifications,
      }));
    } catch (err: any) {
      alert(err.message || "Failed to parse resume");
    } finally {
      setParsing(false);
    }
  };

  const set = (key: keyof ProfileData, val: unknown) =>
    setProfile(p => ({ ...p, [key]: val }));

  // ── Experience ──
  const addExp = () => set("experience", [...profile.experience, { ...EMPTY_EXP, bullets: [""] }]);
  const rmExp = (i: number) => set("experience", profile.experience.filter((_, j) => j !== i));
  const setExp = (i: number, patch: Partial<ProfileExperience>) =>
    set("experience", profile.experience.map((e, j) => j === i ? { ...e, ...patch } : e));
  const addBullet = (i: number) =>
    setExp(i, { bullets: [...(profile.experience[i].bullets || []), ""] });
  const setBullet = (i: number, bi: number, val: string) =>
    setExp(i, { bullets: profile.experience[i].bullets.map((b, bj) => bj === bi ? val : b) });
  const rmBullet = (i: number, bi: number) =>
    setExp(i, { bullets: profile.experience[i].bullets.filter((_, bj) => bj !== bi) });

  // ── Education ──
  const addEdu = () => set("education", [...profile.education, { ...EMPTY_EDU }]);
  const rmEdu = (i: number) => set("education", profile.education.filter((_, j) => j !== i));
  const setEdu = (i: number, patch: Partial<ProfileEducation>) =>
    set("education", profile.education.map((e, j) => j === i ? { ...e, ...patch } : e));

  // ── Projects ──
  const addPrj = () => set("projects", [...profile.projects, { ...EMPTY_PRJ }]);
  const rmPrj = (i: number) => set("projects", profile.projects.filter((_, j) => j !== i));
  const setPrj = (i: number, patch: Partial<ProfileProject>) =>
    set("projects", profile.projects.map((e, j) => j === i ? { ...e, ...patch } : e));

  // ── Skills ──
  const addSkill = (val: string) => {
    const s = val.trim();
    if (s && !profile.skills.includes(s)) set("skills", [...profile.skills, s]);
    setSkillInput("");
  };
  const rmSkill = (s: string) => set("skills", profile.skills.filter(x => x !== s));

  // ── Certs ──
  const addCert = (val: string) => {
    const s = val.trim();
    if (s && !profile.certifications.includes(s)) set("certifications", [...profile.certifications, s]);
    setCertInput("");
  };
  const rmCert = (s: string) => set("certifications", profile.certifications.filter(x => x !== s));

  if (loading) return (
    <div className="flex items-center justify-center h-40 text-slate-500 text-sm">
      <Loader2 size={18} className="animate-spin mr-2" /> Loading…
    </div>
  );

  const totalYears = profile.experience.reduce((s, e) => s + (e.years || 0), 0);

  return (
    <div className="max-w-4xl space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Your Profile</h2>
          {totalYears > 0 && <p className="text-xs text-slate-500 mt-0.5">{totalYears} yrs total experience</p>}
        </div>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={uploadResume} />
          <button onClick={() => fileRef.current?.click()} disabled={parsing}
            className="flex items-center gap-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 text-sm rounded-lg font-medium transition-colors border border-slate-600">
            {parsing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {parsing ? "Parsing…" : "Upload Resume"}
          </button>
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors">
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saved ? "Saved!" : "Save Profile"}
          </button>
        </div>
      </div>

      {/* Personal Info */}
      <div className={SECTION}>
        <div className="flex items-center gap-2 mb-1">
          <User size={14} className="text-blue-400" />
          <span className="text-sm font-semibold text-white">Personal Info</span>
        </div>
        <div className="grid grid-cols-4 gap-3">
          {(["name","email","phone","location"] as const).map(k => (
            <div key={k}>
              <label className={LABEL}>{k}</label>
              <input value={(profile as any)[k]} onChange={e => set(k, e.target.value)}
                className={INPUT} placeholder={k === "location" ? "New York, NY" : ""} />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-4 gap-3 mt-3">
          <div>
            <label className={LABEL}>Visa / Work Status</label>
            <input value={profile.visa_status} onChange={e => set("visa_status", e.target.value)}
              className={INPUT} placeholder="F1 / OPT, US Citizen, H1B…" />
          </div>
        </div>
      </div>

      {/* Experience */}
      <div className={SECTION}>
        <div className="flex items-center justify-between">
          <button onClick={() => toggleCollapse("exp")} className="flex items-center gap-2 text-left">
            {collapsed.has("exp") ? <ChevronRight size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
            <Briefcase size={14} className="text-violet-400" />
            <span className="text-sm font-semibold text-white">Experience</span>
            <span className="text-xs text-slate-500">({profile.experience.length})</span>
          </button>
          {!collapsed.has("exp") && <button onClick={addExp} className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300">
            <Plus size={12} /> Add Role
          </button>}
        </div>
        {!collapsed.has("exp") && profile.experience.length === 0 && (
          <p className="text-xs text-slate-600 text-center py-4">No experience added yet</p>
        )}
        {!collapsed.has("exp") && profile.experience.map((exp, i) => (
          <div key={i} className="border border-slate-700 rounded-lg p-4 space-y-3">
            <div className="grid grid-cols-5 gap-2">
              <div className="col-span-2">
                <label className={LABEL}>Role / Title</label>
                <input value={exp.role} onChange={e => setExp(i, { role: e.target.value })}
                  className={INPUT} placeholder="Senior Data Engineer" />
              </div>
              <div className="col-span-2">
                <label className={LABEL}>Company</label>
                <input value={exp.company} onChange={e => setExp(i, { company: e.target.value })}
                  className={INPUT} placeholder="Cargill" />
              </div>
              <div className="col-span-1" />
            </div>
            <div className="grid grid-cols-5 gap-2">
              <div className="col-span-2">
                <label className={LABEL}>Start Date</label>
                <input value={exp.start_date}
                  onChange={e => {
                    const start_date = e.target.value;
                    const computed = calcYears(start_date, exp.end_date);
                    setExp(i, { start_date, ...(computed !== null ? { years: computed } : {}) });
                  }}
                  className={INPUT} placeholder="Sep 2023" />
              </div>
              <div className="col-span-2">
                <label className={LABEL}>End Date</label>
                <input value={exp.end_date}
                  onChange={e => {
                    const end_date = e.target.value;
                    const computed = calcYears(exp.start_date, end_date);
                    setExp(i, { end_date, ...(computed !== null ? { years: computed } : {}) });
                  }}
                  className={INPUT} placeholder="Present" />
              </div>
              <div>
                <label className={LABEL}>Years (auto)</label>
                <input type="number" step="0.5" min="0" value={exp.years}
                  onChange={e => setExp(i, { years: parseFloat(e.target.value) || 0 })}
                  className={INPUT} />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className={LABEL}>Key Bullet Points</label>
                <button onClick={() => addBullet(i)} className="text-[10px] text-blue-400 hover:text-blue-300">+ Add</button>
              </div>
              {(exp.bullets || []).map((b, bi) => (
                <div key={bi} className="flex gap-2 mb-1.5 items-start">
                  <textarea value={b}
                    onChange={e => {
                      setBullet(i, bi, e.target.value);
                      e.target.style.height = "auto";
                      e.target.style.height = e.target.scrollHeight + "px";
                    }}
                    ref={el => {
                      if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
                    }}
                    rows={1}
                    className={INPUT + " flex-1 resize-none leading-snug overflow-hidden"}
                    placeholder="Led pipeline migration to Spark…" />
                  <button onClick={() => rmBullet(i, bi)} className="text-slate-600 hover:text-red-400 mt-2">
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
            <button onClick={() => rmExp(i)} className="text-[11px] text-red-500 hover:text-red-400 flex items-center gap-1">
              <Trash2 size={11} /> Remove Role
            </button>
          </div>
        ))}
      </div>

      {/* Education */}
      <div className={SECTION}>
        <div className="flex items-center justify-between">
          <button onClick={() => toggleCollapse("edu")} className="flex items-center gap-2 text-left">
            {collapsed.has("edu") ? <ChevronRight size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
            <GraduationCap size={14} className="text-green-400" />
            <span className="text-sm font-semibold text-white">Education</span>
            <span className="text-xs text-slate-500">({profile.education.length})</span>
          </button>
          {!collapsed.has("edu") && <button onClick={addEdu} className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300">
            <Plus size={12} /> Add
          </button>}
        </div>
        {!collapsed.has("edu") && profile.education.map((edu, i) => (
          <div key={i} className="grid grid-cols-3 gap-2 items-end">
            <div>
              <label className={LABEL}>Degree</label>
              <input value={edu.degree} onChange={e => setEdu(i, { degree: e.target.value })}
                className={INPUT} placeholder="M.S. Information Systems" />
            </div>
            <div>
              <label className={LABEL}>School</label>
              <input value={edu.school} onChange={e => setEdu(i, { school: e.target.value })}
                className={INPUT} placeholder="Saint Louis University" />
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <label className={LABEL}>Year</label>
                <input value={edu.year} onChange={e => setEdu(i, { year: e.target.value })}
                  className={INPUT} placeholder="2018" />
              </div>
              <button onClick={() => rmEdu(i)} className="text-slate-600 hover:text-red-400 mt-5">
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
        {!collapsed.has("edu") && profile.education.length === 0 && <p className="text-xs text-slate-600 text-center py-2">No education added</p>}
      </div>

      {/* Projects */}
      <div className={SECTION}>
        <div className="flex items-center justify-between">
          <button onClick={() => toggleCollapse("prj")} className="flex items-center gap-2 text-left">
            {collapsed.has("prj") ? <ChevronRight size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
            <FolderOpen size={14} className="text-amber-400" />
            <span className="text-sm font-semibold text-white">Projects</span>
            <span className="text-xs text-slate-500">({profile.projects.length})</span>
          </button>
          {!collapsed.has("prj") && <button onClick={addPrj} className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300">
            <Plus size={12} /> Add
          </button>}
        </div>
        {!collapsed.has("prj") && profile.projects.map((prj, i) => (
          <div key={i} className="flex gap-2 items-start">
            <div className="grid grid-cols-2 gap-2 flex-1">
              <input value={prj.name} onChange={e => setPrj(i, { name: e.target.value })}
                className={INPUT} placeholder="Real-time Pipeline" />
              <input value={prj.description} onChange={e => setPrj(i, { description: e.target.value })}
                className={INPUT} placeholder="Kafka → Spark → Snowflake ingestion system" />
            </div>
            <button onClick={() => rmPrj(i)} className="text-slate-600 hover:text-red-400 mt-1.5">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        {!collapsed.has("prj") && profile.projects.length === 0 && <p className="text-xs text-slate-600 text-center py-2">No projects added</p>}
      </div>

      {/* Skills */}
      <div className={SECTION}>
        <button onClick={() => toggleCollapse("skills")} className="flex items-center gap-2 mb-1 w-full text-left">
          {collapsed.has("skills") ? <ChevronRight size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
          <Zap size={14} className="text-yellow-400" />
          <span className="text-sm font-semibold text-white">Skills</span>
          <span className="text-xs text-slate-500">({profile.skills.length})</span>
        </button>
        {!collapsed.has("skills") && <>
          <div className="flex flex-wrap gap-1.5 min-h-[32px]">
            {profile.skills.map(s => (
              <span key={s} className="flex items-center gap-1 px-2 py-0.5 bg-slate-700 text-slate-200 text-xs rounded-full">
                {s}
                <button onClick={() => rmSkill(s)} className="text-slate-500 hover:text-red-400">×</button>
              </span>
            ))}
          </div>
          <input value={skillInput}
            onChange={e => setSkillInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addSkill(skillInput); } }}
            className={INPUT} placeholder="Type skill + Enter (Python, Spark, AWS…)" />
          <p className="text-[10px] text-slate-600">Press Enter or comma to add</p>
        </>}
      </div>

      {/* Certifications */}
      <div className={SECTION}>
        <button onClick={() => toggleCollapse("certs")} className="flex items-center gap-2 mb-1 w-full text-left">
          {collapsed.has("certs") ? <ChevronRight size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
          <Award size={14} className="text-cyan-400" />
          <span className="text-sm font-semibold text-white">Certifications</span>
          <span className="text-xs text-slate-500">({profile.certifications.length})</span>
        </button>
        {!collapsed.has("certs") && <>
          <div className="flex flex-wrap gap-1.5 min-h-[32px]">
            {profile.certifications.map(c => (
              <span key={c} className="flex items-center gap-1 px-2 py-0.5 bg-slate-700 text-slate-200 text-xs rounded-full">
                {c}
                <button onClick={() => rmCert(c)} className="text-slate-500 hover:text-red-400">×</button>
              </span>
            ))}
          </div>
          <input value={certInput}
            onChange={e => setCertInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addCert(certInput); } }}
            className={INPUT} placeholder="AWS Solutions Architect, Databricks DE…" />
        </>}
      </div>

      <button onClick={save} disabled={saving}
        className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-xl font-medium transition-colors">
        {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
        {saved ? "Saved!" : "Save Profile"}
      </button>
    </div>
  );
}
