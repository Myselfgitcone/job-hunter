import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { Icon as Ic } from './primitives';

const I = { x: '<path d="M18 6 6 18M6 6l12 12"/>' };

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
            <button onClick={() => setTags(tags.filter(x => x !== t))}><Ic name="x" size={11} /></button>
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

  useEffect(() => {
    if (open) {
      setLoading(true);
      api.getSettings().then((s: any) => {
        if (!s) return;
        const r = Array.isArray(s.job_roles) ? s.job_roles : JSON.parse(s.job_roles || "[]");
        setRoles(r);
      }).finally(() => setLoading(false));
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
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(6px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24 }}>
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: "var(--r-lg)", width: "100%", maxWidth: 500, boxShadow: "var(--sh-pop)", animation: "modalIn 220ms var(--ease)", overflow: "hidden" }}>
        
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 32, height: 32, borderRadius: "var(--r-md)", background: "var(--bg-elevated)", border: "1px solid var(--line)", color: "var(--violet)" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></svg>
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--tx)", margin: 0 }}>Job Preferences</h2>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--tx-3)", cursor: "pointer", display: "flex", padding: 4 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div style={{ padding: "24px 20px" }}>
          {loading ? (
            <div style={{ color: "var(--tx-3)", fontSize: 14 }}>Loading...</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "var(--tx-2)" }}>Target Job Roles</label>
              <TagInput
                tags={roles}
                setTags={setRoles}
                placeholder="Add a target role…"
                suggestions={["Data Engineer", "Analytics Engineer", "ML Engineer", "Data Platform Engineer", "Backend Engineer"]}
              />
              <p style={{ fontSize: 12, color: "var(--tx-3)", margin: "4px 0 0 0", lineHeight: 1.4 }}>
                We use these roles to filter and score incoming jobs. Add all titles you are interested in.
              </p>
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, padding: "14px 20px", borderTop: "1px solid var(--line)", background: "var(--bg-base-2)" }}>
          <button onClick={onClose} className="btn btn-subtle" style={{ height: 36, padding: "0 16px", borderRadius: "var(--r-sm)" }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} className="btn btn-primary" style={{ height: 36, padding: "0 20px", borderRadius: "var(--r-sm)" }}>
            {saving ? "Saving..." : "Save Preferences"}
          </button>
        </div>

      </div>
    </div>
  );
}
