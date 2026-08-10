import { useState, useEffect, useRef, useCallback } from "react";
import { api, fetchPdfBlobUrl } from "../api";
import { ROLE_GROUPS } from "./JobPreferencesModal";

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

// ── Application Answers (auto-apply) ─────────────────────────────────────────
// One-time form: standard screening answers reused on every Auto-Apply.
type AAField = { key: string; label: string; options?: string[]; hint?: string };

const US_STATES = ["Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut","Delaware","District of Columbia","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada","New Hampshire","New Jersey","New Mexico","New York","North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island","South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont","Virginia","Washington","West Virginia","Wisconsin","Wyoming"];

const AA_GROUPS: Array<{ title: string; icon: string; color: string; desc: string; fields: AAField[] }> = [
  {
    title: "Work eligibility", icon: "shieldCheck", color: "#3b82f6",
    desc: "Visa & work authorization — asked on almost every application.",
    fields: [
      { key: "work_authorized",  label: "Legally authorized to work in the US?", options: ["Yes", "No"] },
      { key: "need_sponsorship", label: "Need visa sponsorship (now or later)?", options: ["Yes", "No"],
        hint: "On a work visa / OPT → Yes.  Citizen or Green Card → No." },
      { key: "citizenship",      label: "Citizenship / work status", options: [
        "U.S. Citizen", "U.S. Permanent Resident (Green Card)",
        "Non-U.S. citizen authorized to work in the U.S.",
        "Non-U.S. citizen requiring sponsorship"] },
      { key: "age_18",           label: "18 years or older?", options: ["Yes", "No"], hint: "Almost always Yes" },
      { key: "clearance",        label: "Security clearance", options: [
        "None", "Confidential", "Secret", "Top Secret", "TS/SCI"], hint: "Most people: None" },
    ],
  },
  {
    title: "Yes / No screening", icon: "check", color: "#10b981",
    desc: "Common gate questions. Set your usual answer once — a safe default is suggested.",
    fields: [
      { key: "relocation",         label: "Open to relocating?", options: ["Yes", "No"] },
      { key: "onsite_ok",          label: "Willing to work on-site / hybrid / commute?", options: ["Yes", "No"], hint: "Most people: Yes" },
      { key: "background_check",   label: "OK with a background check?", options: ["Yes", "No"], hint: "Most people: Yes" },
      { key: "drug_test",          label: "OK with a drug test?", options: ["Yes", "No"], hint: "Most people: Yes" },
      { key: "convicted",          label: "Ever been convicted of a crime?", options: ["No", "Yes"], hint: "Answer honestly" },
      { key: "degree",             label: "Bachelor's degree or higher?", options: ["Yes", "No"] },
      { key: "currently_employed", label: "Currently employed?", options: ["Yes", "No"] },
      { key: "previously_worked",  label: "Worked at this company before?", options: ["No", "Yes"], hint: "Usually No" },
      { key: "noncompete",         label: "Bound by a non-compete?", options: ["No", "Yes"], hint: "Usually No" },
    ],
  },
  {
    title: "Pay, timing & location", icon: "sliders", color: "#0ea5e9",
    desc: "Dropped into matching salary / availability / location questions.",
    fields: [
      { key: "salary",           label: "Expected salary", hint: "Tip: \"Open / Negotiable\"" },
      { key: "start_date",       label: "When can you start?", hint: "e.g. \"2 weeks\" or \"Immediately\"" },
      { key: "years_experience", label: "Total years of experience", hint: "Auto-filled from your resume" },
      { key: "state",            label: "US state you live in", options: US_STATES },
      { key: "zip",              label: "Zip code" },
      { key: "how_heard",        label: "\"How did you hear about us?\"", options: [
        "LinkedIn", "Indeed", "Company careers site", "Google search", "Referral", "Other"] },
      { key: "referral",         label: "Referral name (if any)", hint: "Usually blank" },
    ],
  },
  {
    title: "Name & pronouns", icon: "user", color: "#d97706",
    desc: "Used only when a form asks for a preferred name or pronouns.",
    fields: [
      { key: "preferred_first",  label: "Preferred first name", hint: "Blank = use your legal name" },
      { key: "preferred_last",   label: "Preferred last name", hint: "Blank = use your legal name" },
      { key: "pronouns",         label: "Pronouns", options: [
        "he/him", "she/her", "they/them", "Prefer not to say"] },
    ],
  },
  {
    title: "Optional diversity survey", icon: "heart", color: "#8b5cf6",
    desc: "The voluntary EEO survey at the bottom of US applications. Confidential, does not affect hiring. Leave any blank to skip.",
    fields: [
      { key: "demo_gender",      label: "Gender identity", options: [
        "Man", "Woman", "Non-binary", "Decline to self-identify"] },
      { key: "demo_race",        label: "Race / ethnicity", options: [
        "South Asian", "East Asian", "Asian", "Black or African American",
        "Hispanic or Latino", "White", "American Indian or Alaska Native",
        "Native Hawaiian or Other Pacific Islander", "Two or More Races",
        "Decline to self-identify"] },
      { key: "demo_veteran",     label: "Veteran status", options: [
        "I am not a protected veteran",
        "I identify as one or more of the classifications of a protected veteran",
        "I don't wish to answer"] },
      { key: "demo_disability",  label: "Disability status", options: [
        "No, I do not have a disability and have not had one in the past",
        "Yes, I have a disability, or have had one in the past",
        "I do not want to answer"] },
    ],
  },
];

const AA_ICONS: Record<string, string> = {
  shieldCheck: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 14 0v1"/>',
  heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  brain: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>',
};

function YesNoPill({ value, options, onChange }: {
  value: string; options: string[]; onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "inline-flex", gap: 0, borderRadius: 9, overflow: "hidden",
      border: "1px solid var(--line)", height: 36, width: "fit-content" }}>
      {options.map(o => {
        const on = value === o;
        return (
          <button key={o} onClick={() => onChange(on ? "" : o)} type="button"
            style={{ padding: "0 18px", fontSize: 13, fontWeight: 600, cursor: "pointer", border: "none",
              background: on ? (o === "Yes" ? "rgba(16,185,129,0.16)" : "rgba(239,68,64,0.13)") : "transparent",
              color: on ? (o === "Yes" ? "#10b981" : "#f87171") : "var(--tx-3)",
              borderRight: "1px solid var(--line)", transition: "all .12s" }}>
            {o}
          </button>
        );
      })}
      <span style={{ display: "inline-flex", alignItems: "center", padding: "0 10px", fontSize: 11,
        color: value ? "var(--tx-3)" : "#d97706", fontWeight: 500 }}>
        {value ? "" : "not set"}
      </span>
    </div>
  );
}

type CustomQA = { group: string; q: string; a: string };

function ApplicationAnswers() {
  const [values, setValues] = useState<Record<string, any>>({});
  const [memory, setMemory] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<"" | "saving" | "saved" | "error">("");

  useEffect(() => {
    api.getApplyProfile()
      .then(r => { setValues(r.values || {}); setMemory(r.memory || {}); })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const setVal = (k: string, v: string) => { setValues(s => ({ ...s, [k]: v })); setDirty(true); };

  const customs: CustomQA[] = Array.isArray(values.custom) ? values.custom : [];
  const setCustoms = (next: CustomQA[]) => { setValues(s => ({ ...s, custom: next })); setDirty(true); };
  const addCustom = (group: string) => setCustoms([...customs, { group, q: "", a: "" }]);
  const editCustom = (idx: number, patch: Partial<CustomQA>) =>
    setCustoms(customs.map((c, i) => i === idx ? { ...c, ...patch } : c));
  const removeCustom = (idx: number) => setCustoms(customs.filter((_, i) => i !== idx));

  const save = async () => {
    setSaveState("saving");
    try {
      await api.saveApplyProfile({ values });
      setSaveState("saved"); setDirty(false);
      setTimeout(() => setSaveState(""), 2500);
    } catch { setSaveState("error"); }
  };

  const forgetAnswer = (k: string) => {
    const next = { ...memory };
    delete next[k];
    setMemory(next);
    api.saveApplyProfile({ memory: next }).catch(() => {});
  };

  // Counter covers built-in fields AND user-added rows; recomputed every
  // render so it moves the moment any answer changes.
  const allFields = AA_GROUPS.flatMap(g => g.fields);
  const customsComplete = customs.filter(c => c.q.trim() && c.a.trim()).length;
  const totalCount = allFields.length + customs.length;
  const filledCount = allFields.filter(f => (values[f.key] || "").trim()).length + customsComplete;

  if (!loaded) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, animation: "cardIn 240ms var(--ease)" }}>
      {/* Hero / save bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 20px",
        borderRadius: "var(--r-lg)", background: "var(--glass)", border: "1px solid var(--glass-border)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "var(--f-display)", fontSize: 16, fontWeight: 700, color: "var(--tx-1)" }}>
            Fill once, applied everywhere
          </div>
          <div style={{ fontSize: 12.5, color: "var(--tx-3)", marginTop: 3, lineHeight: 1.5 }}>
            Auto-Apply matches these answers onto any company's questions — however they word them.
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontFamily: "var(--f-mono)", fontSize: 20, fontWeight: 700,
            color: filledCount === totalCount ? "#10b981" : "var(--violet)" }}>
            {filledCount}<span style={{ fontSize: 12, color: "var(--tx-3)" }}>/{totalCount}</span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--tx-3)", textTransform: "uppercase", letterSpacing: ".06em" }}>answered</div>
        </div>
        <button className="act ai" onClick={save} disabled={saveState === "saving" || !dirty}
          style={{ height: 38, padding: "0 18px", opacity: dirty || saveState === "saving" ? 1 : 0.55 }}>
          {saveState === "saving" ? "Saving…" : saveState === "saved" && !dirty ? "✓ Saved" : "Save Answers"}
        </button>
      </div>
      {saveState === "error" && (
        <div style={{ fontSize: 12.5, color: "#f87171", fontWeight: 600, padding: "0 4px" }}>Save failed — try again</div>
      )}

      {/* Grouped cards */}
      {AA_GROUPS.map(g => (
        <div key={g.title} style={{ borderRadius: "var(--r-lg)", background: "var(--glass)",
          border: "1px solid var(--glass-border)", padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: "flex", alignItems: "center",
              justifyContent: "center", background: `${g.color}1a`, color: g.color }}>
              <Ic d={AA_ICONS[g.icon]} size={17} color={g.color} />
            </div>
            <div>
              <div style={{ fontFamily: "var(--f-display)", fontSize: 14.5, fontWeight: 600, color: "var(--tx-1)" }}>{g.title}</div>
              <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 2, lineHeight: 1.45 }}>{g.desc}</div>
            </div>
          </div>
          <div className="field-grid">
            {g.fields.map(f => (
              <label key={f.key} className="field">
                <span className="field-label">{f.label}</span>
                {f.options && f.options.length <= 2 ? (
                  <YesNoPill value={values[f.key] || ""} options={f.options} onChange={v => setVal(f.key, v)} />
                ) : f.options ? (
                  <select value={values[f.key] || ""} onChange={e => setVal(f.key, e.target.value)}
                    style={{ color: values[f.key] ? undefined : "var(--tx-3)" }}>
                    <option value="">— select —</option>
                    {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    {/* keep a saved custom value visible even if not in the list */}
                    {values[f.key] && !f.options.includes(values[f.key]) && (
                      <option value={values[f.key]}>{values[f.key]}</option>
                    )}
                  </select>
                ) : (
                  <input value={values[f.key] || ""} placeholder={f.hint || ""}
                    onChange={e => setVal(f.key, e.target.value)} />
                )}
                {/* Guidance under yes/no + dropdowns (inputs already use hint as placeholder) */}
                {f.hint && f.options && (
                  <span style={{ fontSize: 11, color: "var(--tx-3)", marginTop: 5, display: "block", lineHeight: 1.4 }}>{f.hint}</span>
                )}
              </label>
            ))}

            {/* User-added Q&A — rendered as normal grid cells: editable
                question sits where the label sits, answer box below */}
            {customs.map((c, idx) => c.group !== g.title ? null : (
              <div key={`c${idx}`} className="field">
                <span className="field-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input value={c.q} placeholder="Type the question…"
                    onChange={e => editCustom(idx, { q: e.target.value })}
                    style={{ flex: 1, background: "none", border: "none", outline: "none",
                      borderRadius: 0, height: "auto", padding: "1px 0",
                      fontSize: 12, fontWeight: 600, color: "var(--tx-2)" }} />
                  <button onClick={() => removeCustom(idx)} title="Remove"
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--tx-3)",
                      flexShrink: 0, padding: 0, display: "flex" }}>
                    <Ic d={I.x} size={13} />
                  </button>
                </span>
                <input value={c.a} placeholder="Your answer"
                  onChange={e => editCustom(idx, { a: e.target.value })} />
              </div>
            ))}
          </div>

          <button onClick={() => addCustom(g.title)}
            style={{ marginTop: 12, display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5,
              fontWeight: 600, cursor: "pointer", color: g.color, background: `${g.color}12`,
              border: `1px dashed ${g.color}55`, borderRadius: 9, padding: "7px 14px" }}>
            ＋ Add more
          </button>
        </div>
      ))}

      {/* Learned answers */}
      <div style={{ borderRadius: "var(--r-lg)", background: "var(--glass)",
        border: "1px solid var(--glass-border)", padding: "18px 20px" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: Object.keys(memory).length ? 14 : 0 }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: "flex", alignItems: "center",
            justifyContent: "center", background: "rgba(34,211,238,0.10)", color: "var(--cyan)" }}>
            <Ic d={AA_ICONS.brain} size={17} color="#22d3ee" />
          </div>
          <div>
            <div style={{ fontFamily: "var(--f-display)", fontSize: 14.5, fontWeight: 600, color: "var(--tx-1)" }}>
              Learned Answers <span style={{ fontFamily: "var(--f-mono)", fontSize: 12, color: "var(--cyan)" }}>({Object.keys(memory).length})</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 2, lineHeight: 1.45 }}>
              Unusual questions you answer in the Auto-Apply popup land here automatically and refill on the next form that asks the same thing.
            </div>
          </div>
        </div>
        {Object.keys(memory).length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(memory).map(([q, a]) => (
              <div key={q} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5, padding: "8px 12px",
                background: "rgba(0,0,0,0.18)", border: "1px solid var(--line)", borderRadius: 9 }}>
                <span style={{ color: "var(--tx-3)", flex: 1, lineHeight: 1.4 }}>{q}</span>
                <b style={{ color: "var(--tx-1)", whiteSpace: "nowrap", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{a}</b>
                <button onClick={() => forgetAnswer(q)} title="Forget this answer"
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--tx-3)", flexShrink: 0 }}>
                  <Ic d={I.x} size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Inline PDF preview of the user's saved base resume (what tailoring uses).
function BaseResumePreview() {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const urlRef = useRef("");
  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const u = await fetchPdfBlobUrl(api.baseResumePdfUrl());
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = u; setUrl(u);
    } catch (e: any) {
      setErr(e?.message || "Could not load preview");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); return () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }; }, [load]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", minHeight: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 700, color: "var(--tx-2)", letterSpacing: ".04em", textTransform: "uppercase" }}>
          <Ic d={I.doc} size={16} /> Base Resume
        </span>
        <button onClick={load} title="Reload preview"
          style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--bg-elevated)", color: "var(--tx-2)", cursor: "pointer" }}>↻ Refresh</button>
      </div>
      {loading && <div style={{ padding: 24, textAlign: "center", color: "var(--tx-3)", fontSize: 13 }}>Loading preview…</div>}
      {err && !loading && <div style={{ padding: 16, fontSize: 13, color: "#dc2626" }}>{err}</div>}
      {url && !loading && !err && (
        <iframe title="Base Resume" src={url}
          style={{ width: "100%", flex: 1, minHeight: 460, border: "1px solid var(--line)", borderRadius: 10, background: "#fff" }} />
      )}
    </div>
  );
}

export function Profile() {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  // Sub-page: "resume" = the resume profile, "answers" = Application Answers.
  // Resume sections stay mounted (display:none) so unsaved edits survive tab flips.
  const [profileTab, setProfileTab] = useState<"resume" | "answers">("resume");
  const [isDeleting, setIsDeleting] = useState(false);

  // Role access state
  const [myRoles, setMyRoles] = useState<string[]>([]);
  const [roleRequest, setRoleRequest] = useState<string[]>([]);
  const [showRolePicker, setShowRolePicker] = useState(false);
  const [rolePickerSel, setRolePickerSel] = useState("");
  const [roleReqSaving, setRoleReqSaving] = useState(false);
  const [roleReqDone, setRoleReqDone] = useState(false);

  useEffect(() => {
    api.getSettings().then((s: any) => {
      setMyRoles(s.job_roles || []);
      setRoleRequest(s.role_request || []);
    }).catch(() => {});
  }, []);

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
    summary: "",
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
          first_name: profile.personal.firstName,
          last_name: profile.personal.lastName,
          name: [profile.personal.firstName, profile.personal.lastName].filter(Boolean).join(" "),
          email: profile.personal.email, phone: profile.personal.phone, address: profile.personal.address,
          linkedin: profile.personal.linkedin, github: profile.personal.github, visa_status: profile.personal.visa,
          experience: profile.experience.map((e: any) => ({
            role: e.title, company: e.company, location: e.location || "", start_date: e.start, end_date: e.end,
            bullets: e.desc ? e.desc.split("\n").map((b: string) => b.replace(/^[\s•\-\.]*/, "").trim()).filter(Boolean) : [], years: 0,
            expanded: e.expanded !== false,
          })),
          education: profile.education.map((e: any) => ({ ...e, expanded: e.expanded !== false })),
          projects: profile.projects.map((pr: any) => ({ name: pr.name, description: pr.stack || pr.desc, url: pr.url, expanded: pr.expanded !== false })),
          summary: profile.summary || "",
          skills: [...new Set(profile.skills.map((s: string) => s.trim()).filter(Boolean))],
          certifications: [...new Set(profile.certifications.map((s: string) => s.trim()).filter(Boolean))],
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
          location: e.location || "",
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
        
        const first = p.first_name || (p.name || "").split(" ")[0] || "";
        const last = p.last_name || ((p.name || "").split(" ").length > 1 ? (p.name || "").split(" ").slice(1).join(" ") : "");

        _setProfile({
          personal: {
            firstName: first, lastName: last,
            email: p.email || "", phone: p.phone || "",
            address: p.address || p.location || "", linkedin: p.linkedin || "", github: p.github || "",
            visa: p.visa_status || "",
          },
          summary: p.summary || "",
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

  const clearAll = async () => {
    if (!window.confirm("Are you sure you want to clear your entire profile? This cannot be undone until you save again.")) return;
    const empty = {
      personal: { firstName: "", lastName: "", email: "", phone: "", address: "", linkedin: "", github: "", visa: "" },
      summary: "",
      experience: [], education: [], projects: [], skills: [], certifications: [],
    };
    setProfile(empty);
    try {
      setSaveStatus("saving");
      await api.saveProfile({ first_name: "", last_name: "", name: "", email: "", phone: "", address: "", linkedin: "", github: "", visa_status: "", experience: [], education: [], projects: [], summary: "", skills: [], certifications: [] } as any);
      setSaveStatus("saved");
    } catch { setSaveStatus("unsaved"); }
  };

  const handleUploadClick = () => {
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
          location: e.location || "",
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
          skills:     parsed.skills?.length ? [...new Set((parsed.skills as string[]).map((s: string) => s.trim()).filter(Boolean))] : prev.skills,
          certifications: parsed.certifications?.length ? [...new Set((parsed.certifications as string[]).map((s: string) => s.trim()).filter(Boolean))] : prev.certifications,
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
      <div className="form-inner" style={profileTab === "resume"
        ? { maxWidth: "none", display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }
        : undefined}>
        <div className="form-head">
          <div>
            <h1 className="dash-title">My Profile</h1>
            <p className="dash-sub">The source your AI tailoring and scoring pull from</p>
          </div>
          <div style={{ display: profileTab === "resume" ? "flex" : "none", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
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

        {/* Sub-page tabs — segmented control */}
        <div style={{ display: "inline-flex", gap: 4, marginBottom: 24, padding: 4,
          borderRadius: 12, background: "var(--glass)", border: "1px solid var(--glass-border)" }}>
          {([["resume", I.doc, "Resume Profile"], ["answers", I.bolt, "Application Answers"]] as const).map(([id, icon, label]) => {
            const on = profileTab === id;
            return (
              <button key={id} onClick={() => setProfileTab(id)}
                style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 18px",
                  fontSize: 13, fontWeight: 600, cursor: "pointer", border: "none", borderRadius: 9,
                  background: on ? "var(--grad)" : "transparent",
                  color: on ? "#fff" : "var(--tx-2)",
                  boxShadow: on ? "0 2px 10px rgba(124,58,237,0.35)" : "none",
                  transition: "all .15s" }}>
                <Ic d={icon} size={14} color={on ? "#fff" : undefined} /> {label}
              </button>
            );
          })}
        </div>

        {profileTab === "answers" && <ApplicationAnswers />}

        <div style={{ display: profileTab === "resume" ? "flex" : "none", gap: 24, alignItems: "stretch", flex: 1, minHeight: 0 }}>
        {/* LEFT: editable profile form — scrolls independently */}
        <div style={{ flex: 1, minWidth: 0, overflowY: "auto", paddingRight: 10 }}>

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

        {/* Professional Summary */}
        <section className="form-section">
          <div className="section-label"><Ic d={I.doc} size={16} /> Professional Summary</div>
          <textarea
            value={profile.summary}
            onChange={e => setProfile((p: any) => ({ ...p, summary: e.target.value }))}
            placeholder="Write a 2–4 sentence professional summary highlighting your expertise, years of experience, and key strengths. This will appear at the top of every tailored resume."
            rows={4}
            style={{ width: "100%", resize: "vertical", minHeight: 90 }}
          />
        </section>

        {/* Work Experience */}
        <section className="form-section">
          <div className="section-label">
            <Ic d={I.briefcase} size={16} /> Work Experience
            <button className="add-btn" onClick={() => setProfile((p: any) => ({ ...p, experience: [...p.experience, { title: "", company: "", location: "", start: "", end: "Present", desc: "" }] }))}>
              + Add Experience
            </button>
          </div>
          {P.experience.map((e: any, i: number) => (
            <RepeatCard key={i} index={i} expanded={e.expanded} onToggle={v => updateAt("experience", i, "expanded", v as any)} title={e.title || e.company ? `${e.title}${e.title && e.company ? ' at ' : ''}${e.company}` : "New Experience"} onRemove={() => setProfile((p: any) => ({ ...p, experience: p.experience.filter((_: any, j: number) => j !== i) }))}>
              <div className="field-grid">
                <Field label="Job Title" value={e.title}   onChange={v => updateAt("experience", i, "title", v)} />
                <Field label="Company"   value={e.company} onChange={v => updateAt("experience", i, "company", v)} />
                <Field
                  label={<><span style={{display: "inline-flex", alignItems: "center", gap: 4}}><Ic d={I.mapPin} size={13} /> Location</span></>}
                  value={e.location || ""} onChange={v => updateAt("experience", i, "location", v)}
                  placeholder="City, State" full
                />
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

        {/* My Job Access */}
        <div style={{ marginTop: 32, paddingTop: 24, borderTop: "1px solid var(--glass-border)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--tx-2)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
            My Job Access
          </div>

          {/* Current roles */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "var(--tx-3)", marginBottom: 6 }}>Assigned roles:</div>
            {myRoles.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {ROLE_GROUPS.filter(g => g.items.some(i => myRoles.includes(i))).map(g => (
                  <span key={g.group} style={{ fontSize: 12, padding: "3px 10px", borderRadius: 999, background: "rgba(124,58,237,0.1)", color: "var(--violet)", fontWeight: 600, border: "1px solid rgba(124,58,237,0.2)" }}>
                    {g.group}
                  </span>
                ))}
              </div>
            ) : (
              <span style={{ fontSize: 12, color: "var(--tx-3)" }}>No roles assigned yet</span>
            )}
          </div>

          {/* Pending request */}
          {roleRequest.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(217,119,6,0.07)", border: "1px solid rgba(217,119,6,0.2)" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
              <span style={{ fontSize: 12.5, color: "#d97706", fontWeight: 600 }}>
                Request pending: {ROLE_GROUPS.filter(g => g.items.some(i => roleRequest.includes(i))).map(g => g.group).join(", ")}
              </span>
            </div>
          )}

          {/* Request button / picker */}
          {roleReqDone ? (
            <div style={{ fontSize: 12.5, color: "#059669", fontWeight: 600 }}>Request sent — admin will review it.</div>
          ) : !showRolePicker ? (
            <button onClick={() => setShowRolePicker(true)}
              style={{ fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 8, cursor: "pointer",
                border: "1px dashed var(--violet)", background: "rgba(124,58,237,0.05)", color: "var(--violet)", fontFamily: "inherit" }}>
              + Request additional role
            </button>
          ) : (
            <div style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "14px 16px", marginTop: 4 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)", marginBottom: 10 }}>
                Select role to request:
                <span style={{ marginLeft: 6, fontWeight: 400, color: "var(--tx-3)" }}>Need more? Contact admin after this is granted.</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {ROLE_GROUPS
                  .filter(g => !g.items.some(i => myRoles.includes(i))) // only show roles not already assigned
                  .map(g => {
                    const on = rolePickerSel === g.group;
                    return (
                      <button key={g.group} type="button" onClick={() => setRolePickerSel(on ? "" : g.group)}
                        style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 8, cursor: "pointer",
                          border: on ? "1.5px solid var(--violet)" : "1px solid var(--line)",
                          background: on ? "rgba(124,58,237,0.07)" : "var(--bg-elevated)",
                          textAlign: "left", fontFamily: "inherit" }}>
                        <span style={{ width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                          border: on ? "5px solid var(--violet)" : "2px solid var(--line-hi)",
                          background: on ? "var(--violet)" : "transparent" }} />
                        <span style={{ fontSize: 13, fontWeight: 600, color: on ? "var(--violet)" : "var(--tx)" }}>{g.group}</span>
                      </button>
                    );
                  })}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button disabled={!rolePickerSel || roleReqSaving}
                  onClick={async () => {
                    if (!rolePickerSel) return;
                    setRoleReqSaving(true);
                    try {
                      const group = ROLE_GROUPS.find(g => g.group === rolePickerSel);
                      await api.requestRole(group ? group.items : []);
                      setRoleRequest(group ? group.items : []);
                      setRoleReqDone(true);
                      setShowRolePicker(false);
                    } catch {}
                    finally { setRoleReqSaving(false); }
                  }}
                  style={{ height: 34, padding: "0 18px", borderRadius: 8, border: "none",
                    background: rolePickerSel ? "linear-gradient(120deg,#7c3aed,#06b6d4)" : "var(--line)",
                    color: rolePickerSel ? "#fff" : "var(--tx-3)", fontSize: 13, fontWeight: 600,
                    cursor: rolePickerSel ? "pointer" : "not-allowed", fontFamily: "inherit",
                    opacity: roleReqSaving ? 0.7 : 1 }}>
                  {roleReqSaving ? "Sending…" : "Send Request"}
                </button>
                <button onClick={() => { setShowRolePicker(false); setRolePickerSel(""); }}
                  style={{ height: 34, padding: "0 14px", borderRadius: 8, border: "1px solid var(--line)",
                    background: "transparent", color: "var(--tx-2)", fontSize: 13, fontWeight: 600,
                    cursor: "pointer", fontFamily: "inherit" }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Danger Zone */}
        <div style={{ marginTop: 40, paddingTop: 24, borderTop: "1px solid var(--glass-border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ color: "#ef4440", fontSize: 14, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
            <Ic d={I.x} size={16} /> Danger Zone
          </div>
          <div style={{ background: "rgba(239, 68, 64, 0.04)", border: "1px solid rgba(239, 68, 64, 0.2)", borderRadius: 12, padding: "20px 24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 13.5, color: "var(--tx-2)" }}>
              Permanently delete your account and all associated data.<br/>
              <span style={{ color: "var(--tx-3)", fontSize: 12.5, marginTop: 4, display: "inline-block" }}>This action cannot be undone. You will lose all saved jobs, tailored resumes, and settings.</span>
            </div>
            <button className="btn" onClick={() => setShowDeleteModal(true)} style={{ background: "#ef4440", color: "#fff", border: "none", height: 38, padding: "0 16px", borderRadius: 8, fontSize: 13, fontWeight: 500, boxShadow: "0 2px 8px rgba(239,68,64,0.3)", cursor: "pointer" }}>
              Delete Account
            </button>
          </div>
        </div>
        </div>{/* end LEFT form column */}

        {/* RIGHT: static base-resume PDF preview — stays put while the left
            column scrolls; ~half width so the resume renders large. */}
        <div style={{ flex: "0 0 48%", minWidth: 520, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <BaseResumePreview />
        </div>
        </div>{/* end resume-tab container */}
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
