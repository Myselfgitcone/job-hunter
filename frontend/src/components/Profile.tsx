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
  name: "", email: "", phone: "", location: "", address: "",
  linkedin: "", github: "", website: "", visa_status: "",
  experience: [], education: [], projects: [],
  skills: [], certifications: [],
};

const EMPTY_EXP: ProfileExperience = { role: "", company: "", start_date: "", end_date: "", years: 0, bullets: [""] };
const EMPTY_EDU: ProfileEducation = { degree: "", school: "", year: "" };
const EMPTY_PRJ: ProfileProject = { name: "", description: "" };

const INPUT = { width: '100%' } as React.CSSProperties;
const LABEL: React.CSSProperties = { display:'block', fontSize:10, fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:4 };
const CARD: React.CSSProperties = { background:'var(--bg-elevated)', border:'1px solid var(--border-default)', borderRadius:12, padding:20 };

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
        address:        p.address,
        linkedin:       p.linkedin,
        github:         p.github,
        website:        p.website,
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
    <div style={{maxWidth:900, padding:32, display:'flex', flexDirection:'column', gap:24, overflowY:'auto', flex:1}}>
      {/* Header */}
      <div style={{display:'flex', alignItems:'center', justifyContent:'space-between'}}>
        <div>
          <h2 style={{fontSize:18, fontWeight:600, color:'var(--text-primary)', margin:0}}>Your Profile</h2>
          {totalYears > 0 && <p style={{fontSize:12, color:'var(--text-muted)', marginTop:2}}>{totalYears} yrs total experience</p>}
        </div>
        <div style={{display:'flex', alignItems:'center', gap:8}}>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" style={{display:'none'}} onChange={uploadResume} />
          <button onClick={() => fileRef.current?.click()} disabled={parsing}
            style={{display:'flex', alignItems:'center', gap:6, padding:'7px 14px', borderRadius:8, fontSize:13, fontWeight:500,
              background:'var(--bg-elevated)', border:'1px solid var(--border-default)', color:'var(--text-primary)', cursor:'pointer', opacity:parsing?0.6:1}}>
            {parsing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {parsing ? "Parsing…" : "Upload Resume"}
          </button>
          <button onClick={save} disabled={saving}
            style={{display:'flex', alignItems:'center', gap:6, padding:'7px 16px', borderRadius:8, fontSize:13, fontWeight:500,
              background:'var(--accent)', color:'#fff', border:'none', cursor:'pointer', opacity:saving?0.6:1}}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saved ? "Saved!" : "Save Profile"}
          </button>
        </div>
      </div>

      {/* Personal Info */}
      <div style={CARD}>
        <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:12}}>
          <User size={14} style={{color:'var(--accent)'}} />
          <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Personal Info</span>
        </div>
        {/* Row 1: name, email, phone */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10, marginBottom:10}}>
          {([['name','Full Name','Jagad...'], ['email','Email','you@email.com'], ['phone','Phone','+1 (555) 000-0000']] as const).map(([k, label, ph]) => (
            <div key={k}>
              <label style={LABEL}>{label}</label>
              <input value={(profile as any)[k]} onChange={e => set(k as any, e.target.value)} placeholder={ph} style={INPUT} />
            </div>
          ))}
        </div>
        {/* Row 2: location, address */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:10}}>
          <div>
            <label style={LABEL}>City / Location</label>
            <input value={profile.location} onChange={e => set('location', e.target.value)} placeholder="New York, NY" style={INPUT} />
          </div>
          <div>
            <label style={LABEL}>Full Address</label>
            <input value={profile.address} onChange={e => set('address', e.target.value)} placeholder="123 Main St, New York, NY 10001" style={INPUT} />
          </div>
        </div>
        {/* Row 3: LinkedIn, GitHub, Visa */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10}}>
          <div>
            <label style={LABEL}>LinkedIn URL</label>
            <input value={profile.linkedin} onChange={e => set('linkedin', e.target.value)} placeholder="linkedin.com/in/yourname" style={INPUT} />
          </div>
          <div>
            <label style={LABEL}>GitHub URL</label>
            <input value={profile.github} onChange={e => set('github', e.target.value)} placeholder="github.com/yourname" style={INPUT} />
          </div>
          <div>
            <label style={LABEL}>Visa / Work Status</label>
            <input value={profile.visa_status} onChange={e => set('visa_status', e.target.value)} placeholder="F1/OPT, H1B, US Citizen…" style={INPUT} />
          </div>
        </div>

      </div>

      {/* Experience */}
      <div style={CARD}>
        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12}}>
          <button onClick={() => toggleCollapse('exp')} style={{display:'flex', alignItems:'center', gap:8, background:'none', border:'none', cursor:'pointer', padding:0}}>
            {collapsed.has('exp') ? <ChevronRight size={14} style={{color:'var(--text-muted)'}} /> : <ChevronDown size={14} style={{color:'var(--text-muted)'}} />}
            <Briefcase size={14} style={{color:'#a78bfa'}} />
            <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Experience</span>
            <span style={{fontSize:12, color:'var(--text-muted)'}}>({profile.experience.length})</span>
          </button>
          {!collapsed.has('exp') && <button onClick={addExp} style={{fontSize:12, color:'var(--accent)', background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', gap:4}}><Plus size={12} /> Add Role</button>}
        </div>
        {!collapsed.has('exp') && profile.experience.length === 0 && <p style={{fontSize:12, color:'var(--text-muted)', textAlign:'center', padding:'16px 0'}}>No experience added yet</p>}
        {!collapsed.has('exp') && profile.experience.map((exp, i) => (
          <div key={i} style={{border:'1px solid var(--border-default)', borderRadius:10, padding:14, marginBottom:10}}>
            <div style={{display:'grid', gridTemplateColumns:'2fr 2fr 1fr', gap:8, marginBottom:8}}>
              <div><label style={LABEL}>Role / Title</label><input value={exp.role} onChange={e => setExp(i, { role: e.target.value })} placeholder="Senior Data Engineer" style={INPUT} /></div>
              <div><label style={LABEL}>Company</label><input value={exp.company} onChange={e => setExp(i, { company: e.target.value })} placeholder="Cargill" style={INPUT} /></div>
              <div />
            </div>
            <div style={{display:'grid', gridTemplateColumns:'2fr 2fr 1fr', gap:8, marginBottom:8}}>
              <div><label style={LABEL}>Start Date</label>
                <input value={exp.start_date} onChange={e => { const start_date=e.target.value; const computed=calcYears(start_date,exp.end_date); setExp(i,{start_date,...(computed!==null?{years:computed}:{})}); }} placeholder="Sep 2023" style={INPUT} /></div>
              <div><label style={LABEL}>End Date</label>
                <input value={exp.end_date} onChange={e => { const end_date=e.target.value; const computed=calcYears(exp.start_date,end_date); setExp(i,{end_date,...(computed!==null?{years:computed}:{})}); }} placeholder="Present" style={INPUT} /></div>
              <div><label style={LABEL}>Years (auto)</label>
                <input type="number" step="0.5" min="0" value={exp.years} onChange={e => setExp(i, { years: parseFloat(e.target.value)||0 })} style={INPUT} /></div>
            </div>
            <div>
              <div style={{display:'flex', justifyContent:'space-between', marginBottom:4}}>
                <label style={LABEL}>Key Bullet Points</label>
                <button onClick={() => addBullet(i)} style={{fontSize:11, color:'var(--accent)', background:'none', border:'none', cursor:'pointer'}}>+ Add</button>
              </div>
              {(exp.bullets||[]).map((b,bi) => (
                <div key={bi} style={{display:'flex', gap:6, marginBottom:6, alignItems:'flex-start'}}>
                  <textarea value={b} onChange={e => { setBullet(i,bi,e.target.value); e.target.style.height='auto'; e.target.style.height=e.target.scrollHeight+'px'; }}
                    ref={el => { if(el){el.style.height='auto';el.style.height=el.scrollHeight+'px';} }}
                    rows={1} style={{...INPUT, flex:1, resize:'none', lineHeight:1.4, overflow:'hidden'}} placeholder="Led pipeline migration to Spark…" />
                  <button onClick={() => rmBullet(i,bi)} style={{color:'var(--text-muted)', background:'none', border:'none', cursor:'pointer', marginTop:8}}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
            <button onClick={() => rmExp(i)} style={{fontSize:12, color:'#f87171', background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', gap:4, marginTop:4}}><Trash2 size={11} /> Remove Role</button>
          </div>
        ))}
      </div>

      {/* Education */}
      <div style={CARD}>
        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12}}>
          <button onClick={() => toggleCollapse('edu')} style={{display:'flex', alignItems:'center', gap:8, background:'none', border:'none', cursor:'pointer', padding:0}}>
            {collapsed.has('edu') ? <ChevronRight size={14} style={{color:'var(--text-muted)'}} /> : <ChevronDown size={14} style={{color:'var(--text-muted)'}} />}
            <GraduationCap size={14} style={{color:'#34d399'}} />
            <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Education</span>
            <span style={{fontSize:12, color:'var(--text-muted)'}}>({profile.education.length})</span>
          </button>
          {!collapsed.has('edu') && <button onClick={addEdu} style={{fontSize:12, color:'var(--accent)', background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', gap:4}}><Plus size={12} /> Add</button>}
        </div>
        {!collapsed.has('edu') && profile.education.map((edu,i) => (
          <div key={i} style={{display:'grid', gridTemplateColumns:'1fr 1fr auto', gap:8, alignItems:'flex-end', marginBottom:8}}>
            <div><label style={LABEL}>Degree</label><input value={edu.degree} onChange={e => setEdu(i,{degree:e.target.value})} placeholder="M.S. Information Systems" style={INPUT} /></div>
            <div><label style={LABEL}>School</label><input value={edu.school} onChange={e => setEdu(i,{school:e.target.value})} placeholder="Saint Louis University" style={INPUT} /></div>
            <div style={{display:'flex', gap:8, alignItems:'flex-end'}}>
              <div><label style={LABEL}>Year</label><input value={edu.year} onChange={e => setEdu(i,{year:e.target.value})} placeholder="2025" style={{...INPUT, width:80}} /></div>
              <button onClick={() => rmEdu(i)} style={{color:'var(--text-muted)', background:'none', border:'none', cursor:'pointer', marginBottom:2}}><Trash2 size={13} /></button>
            </div>
          </div>
        ))}
        {!collapsed.has('edu') && profile.education.length === 0 && <p style={{fontSize:12, color:'var(--text-muted)', textAlign:'center', padding:'10px 0'}}>No education added</p>}
      </div>

      {/* Projects */}
      <div style={CARD}>
        <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:12}}>
          <button onClick={() => toggleCollapse('prj')} style={{display:'flex', alignItems:'center', gap:8, background:'none', border:'none', cursor:'pointer', padding:0}}>
            {collapsed.has('prj') ? <ChevronRight size={14} style={{color:'var(--text-muted)'}} /> : <ChevronDown size={14} style={{color:'var(--text-muted)'}} />}
            <FolderOpen size={14} style={{color:'#fbbf24'}} />
            <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Projects</span>
            <span style={{fontSize:12, color:'var(--text-muted)'}}>({profile.projects.length})</span>
          </button>
          {!collapsed.has('prj') && <button onClick={addPrj} style={{fontSize:12, color:'var(--accent)', background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', gap:4}}><Plus size={12} /> Add</button>}
        </div>
        {!collapsed.has('prj') && profile.projects.map((prj,i) => (
          <div key={i} style={{display:'flex', gap:8, marginBottom:8, alignItems:'flex-start'}}>
            <div style={{display:'grid', gridTemplateColumns:'1fr 2fr', gap:8, flex:1}}>
              <input value={prj.name} onChange={e => setPrj(i,{name:e.target.value})} placeholder="Real-time Pipeline" style={INPUT} />
              <input value={prj.description} onChange={e => setPrj(i,{description:e.target.value})} placeholder="Kafka → Spark → Snowflake ingestion system" style={INPUT} />
            </div>
            <button onClick={() => rmPrj(i)} style={{color:'var(--text-muted)', background:'none', border:'none', cursor:'pointer', marginTop:6}}><Trash2 size={13} /></button>
          </div>
        ))}
        {!collapsed.has('prj') && profile.projects.length === 0 && <p style={{fontSize:12, color:'var(--text-muted)', textAlign:'center', padding:'10px 0'}}>No projects added</p>}
      </div>

      {/* Skills */}
      <div style={CARD}>

        <button onClick={() => toggleCollapse('skills')} style={{display:'flex', alignItems:'center', gap:8, background:'none', border:'none', cursor:'pointer', padding:0, marginBottom:10, width:'100%', textAlign:'left'}}>
          {collapsed.has('skills') ? <ChevronRight size={14} style={{color:'var(--text-muted)'}} /> : <ChevronDown size={14} style={{color:'var(--text-muted)'}} />}
          <Zap size={14} style={{color:'#facc15'}} />
          <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Skills</span>
          <span style={{fontSize:12, color:'var(--text-muted)'}}>({profile.skills.length})</span>
        </button>
        {!collapsed.has('skills') && <>
          <div style={{display:'flex', flexWrap:'wrap', gap:6, minHeight:32, marginBottom:8}}>
            {profile.skills.map(s => (
              <span key={s} style={{display:'flex', alignItems:'center', gap:4, padding:'3px 10px', background:'var(--accent-tonal)', color:'var(--accent)', fontSize:12, borderRadius:999, border:'1px solid var(--accent)'}}>
                {s}
                <button onClick={() => rmSkill(s)} style={{color:'var(--text-muted)', background:'none', border:'none', cursor:'pointer', fontSize:14, lineHeight:1}}>×</button>
              </span>
            ))}
          </div>
          <input value={skillInput} onChange={e => setSkillInput(e.target.value)}
            onKeyDown={e => { if (e.key==='Enter'||e.key===','){e.preventDefault();addSkill(skillInput);} }}
            placeholder="Type skill + Enter (Python, Spark, AWS…)" style={INPUT} />
          <p style={{fontSize:11, color:'var(--text-muted)', marginTop:4}}>Press Enter or comma to add</p>
        </> }
      </div>

      {/* Certifications */}

      <div style={CARD}>
        <button onClick={() => toggleCollapse('certs')} style={{display:'flex', alignItems:'center', gap:8, background:'none', border:'none', cursor:'pointer', padding:0, marginBottom:10, width:'100%', textAlign:'left'}}>
          {collapsed.has('certs') ? <ChevronRight size={14} style={{color:'var(--text-muted)'}} /> : <ChevronDown size={14} style={{color:'var(--text-muted)'}} />}
          <Award size={14} style={{color:'#22d3ee'}} />
          <span style={{fontSize:13, fontWeight:600, color:'var(--text-primary)'}}>Certifications</span>
          <span style={{fontSize:12, color:'var(--text-muted)'}}>({profile.certifications.length})</span>
        </button>
        {!collapsed.has('certs') && <>
          <div style={{display:'flex', flexWrap:'wrap', gap:6, minHeight:32, marginBottom:8}}>
            {profile.certifications.map(c => (
              <span key={c} style={{display:'flex', alignItems:'center', gap:4, padding:'3px 10px', background:'var(--bg-surface)', color:'var(--text-primary)', fontSize:12, borderRadius:999, border:'1px solid var(--border-default)'}}>
                {c}
                <button onClick={() => rmCert(c)} style={{color:'var(--text-muted)', background:'none', border:'none', cursor:'pointer', fontSize:14, lineHeight:1}}>×</button>
              </span>
            ))}
          </div>
          <input value={certInput} onChange={e => setCertInput(e.target.value)}
            onKeyDown={e => { if (e.key==='Enter'||e.key===','){e.preventDefault();addCert(certInput);} }}
            placeholder="AWS Solutions Architect, Databricks DE…" style={INPUT} />
        </> }
      </div>

      <button onClick={save} disabled={saving}
        style={{width:'100%', display:'flex', alignItems:'center', justifyContent:'center', gap:8,
          padding:'10px 0', background:'var(--accent)', color:'#fff', border:'none',
          borderRadius:10, fontSize:13, fontWeight:500, cursor:'pointer', opacity:saving?0.6:1}}>
        {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
        {saved ? "Saved!" : "Save Profile"}
      </button>
    </div>
  );
}
