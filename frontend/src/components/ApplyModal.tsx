import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner } from "./primitives";
import type { Job } from "../types";

function Ic({ d, size = 16, color, style }: { d: string; size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color || "currentColor"} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }} dangerouslySetInnerHTML={{ __html: d }} />
  );
}

const I = {
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a7 7 0 0 1 14 0v1"/>',
  clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
  doc: '<path d="M14 3v5h5"/><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M8 13h8M8 17h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  sparkle: '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/>',
};

type FormField = {
  key: string; label: string; type: string; required: boolean;
  options?: Array<{ label: string; value: string }>;
};

type ApplyForm = {
  supported: boolean; ats?: string; method?: "auto" | "manual";
  fields?: FormField[]; answers?: Record<string, string>;
  apply_url: string; reason?: string;
  meta?: { title: string; location: string }; dry_run?: boolean;
};

const ATS_NAMES: Record<string, string> = {
  greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby",
};

// Section split: contact basics vs the employer's screening questions vs the
// optional self-ID survey — mirrors how the hosted forms themselves read.
const CONTACT_RE = /first name|last name|full name|^name$|email|phone|location|linkedin|github|portfolio|website|current company|preferred (first|last) name|pronoun/i;

function sectionOf(f: FormField): "contact" | "optional" | "questions" {
  if (f.label.startsWith("[Optional]")) return "optional";
  if (CONTACT_RE.test(f.label)) return "contact";
  return "questions";
}

export default function ApplyModal({ job, onClose, onToast, onUpdate }: {
  job: Job;
  onClose: () => void;
  onToast: (msg: string, type?: "success" | "error") => void;
  onUpdate: (patch: Partial<Job>) => void;
}) {
  const [form, setForm] = useState<ApplyForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [useTailored, setUseTailored] = useState(!!job.tailored_resume);
  const [drafting, setDrafting] = useState(false);
  const [aiKeys, setAiKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    api.getApplyForm(job.id)
      .then(f => { if (alive) { setForm(f); setAnswers(f.answers || {}); } })
      .catch(e => { if (alive) { setForm({ supported: false, apply_url: job.url, reason: e.message }); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [job.id]);

  const fields = (form?.fields || []).filter(f => f.type !== "file");
  const answered = fields.filter(f => (answers[f.key] || "").trim());
  const missingRequired = fields.filter(f => f.required && !(answers[f.key] || "").trim());
  const unanswered = fields.filter(f => !(answers[f.key] || "").trim() && !f.label.startsWith("[Optional]"));

  const submit = async () => {
    if (missingRequired.length) {
      onToast(`Fill required: ${missingRequired.map(f => f.label).join(", ")}`, "error");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.submitApplication(job.id, answers, useTailored);
      if (res.status === "submitted") {
        onToast("Application submitted ✓", "success");
        onUpdate({ status: "applied" });
        onClose();
      } else if (res.status === "dry_run") {
        onToast("Dry run OK — payload validated, nothing sent. Disable dry-run in Settings to submit live.", "success");
      } else if (res.status === "manual") {
        onToast("This board needs a manual apply (captcha or unsupported form) — opening the ATS page.", "error");
        window.open(res.apply_url || job.url, "_blank");
      } else {
        onToast(`Submit failed: ${String(res.detail || "unknown error")}`, "error");
      }
    } catch (e: any) {
      onToast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const draftWithAi = async () => {
    if (!unanswered.length) return;
    setDrafting(true);
    try {
      const qs = unanswered.map(f => ({
        key: f.key, label: f.label, type: f.type,
        options: f.options?.map(o => o.label),
      }));
      const res = await api.draftAiAnswers(job.id, qs);
      const merged: Record<string, string> = {};
      const marked = new Set(aiKeys);
      for (const [k, v] of Object.entries(res.answers)) {
        const field = form?.fields?.find(f => f.key === k);
        if (field?.options?.length) {
          const opt = field.options.find(o => o.label.trim().toLowerCase() === v.trim().toLowerCase());
          if (opt) { merged[k] = opt.value; marked.add(k); }
        } else {
          merged[k] = v; marked.add(k);
        }
      }
      if (Object.keys(merged).length) {
        setAnswers(a => ({ ...a, ...merged }));
        setAiKeys(marked);
        onToast(`AI drafted ${Object.keys(merged).length} answer(s) — review before submitting`, "success");
      } else {
        onToast("AI couldn't confidently answer these from your resume — fill them manually", "error");
      }
    } catch (e: any) {
      onToast(e.message, "error");
    } finally {
      setDrafting(false);
    }
  };

  const copyAll = () => {
    const lines = fields.map(f => {
      const v = answers[f.key] || "";
      const lab = f.options?.find(o => o.value === v)?.label ?? v;
      return `${f.label.replace(/^\[Optional\]\s*/, "")}: ${lab}`;
    });
    navigator.clipboard.writeText(lines.join("\n"));
    onToast("Answers copied — paste into the ATS form", "success");
  };

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "8px 11px", fontSize: 13, borderRadius: 9,
    border: "1px solid var(--line)", background: "var(--bg-main)", color: "var(--tx-1)",
  };

  const renderInput = (f: FormField) => {
    const missing = f.required && !(answers[f.key] || "").trim();
    const border = missing ? "1px solid rgba(245,158,11,0.55)" : (inputStyle.border as string);
    if (f.type === "textarea") return (
      <textarea rows={3} style={{ ...inputStyle, border, resize: "vertical" }}
        value={answers[f.key] || ""}
        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))} />
    );
    if ((f.type === "select" || f.type === "boolean" || f.type === "multiselect") && f.options?.length) return (
      <select style={{ ...inputStyle, border, color: answers[f.key] ? "var(--tx-1)" : "var(--tx-3)" }}
        value={answers[f.key] || ""}
        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))}>
        <option value="">— select —</option>
        {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
    return (
      <input style={{ ...inputStyle, border }} value={answers[f.key] || ""}
        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))} />
    );
  };

  const renderField = (f: FormField) => {
    const done = !!(answers[f.key] || "").trim();
    return (
      <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 5, minWidth: 0 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
          color: "var(--tx-2)", lineHeight: 1.4 }}>
          <span style={{ flex: 1 }}>
            {f.label.replace(/^\[Optional\]\s*/, "")}
            {f.required && <span style={{ color: "#f87171" }}> *</span>}
          </span>
          {aiKeys.has(f.key) && done && (
            <span style={{ fontSize: 9.5, fontWeight: 700, padding: "1px 7px", borderRadius: 8, flexShrink: 0,
              background: "rgba(124,58,237,0.13)", color: "#a78bfa", letterSpacing: ".03em" }}>AI DRAFT</span>
          )}
          {done && !aiKeys.has(f.key) && <Ic d={I.check} size={12} color="#10b981" />}
        </span>
        {renderInput(f)}
      </label>
    );
  };

  const Section = ({ icon, color, title, sub, extra, children }: {
    icon: string; color: string; title: string; sub?: string; extra?: React.ReactNode; children: React.ReactNode;
  }) => (
    <div style={{ borderRadius: 14, background: "var(--glass)", border: "1px solid var(--glass-border)",
      padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, display: "flex",
          alignItems: "center", justifyContent: "center", background: `${color}1a` }}>
          <Ic d={icon} size={14} color={color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "var(--f-display)", fontSize: 13.5, fontWeight: 600, color: "var(--tx-1)" }}>{title}</div>
          {sub && <div style={{ fontSize: 11, color: "var(--tx-3)", marginTop: 1 }}>{sub}</div>}
        </div>
        {extra}
      </div>
      {children}
    </div>
  );

  const contact = fields.filter(f => sectionOf(f) === "contact");
  const questions = fields.filter(f => sectionOf(f) === "questions");
  const optional = fields.filter(f => sectionOf(f) === "optional");
  const pct = fields.length ? Math.round(100 * answered.length / fields.length) : 0;

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 2000, background: "rgba(0,0,0,0.6)",
      backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 680, maxWidth: "94vw", maxHeight: "88vh", display: "flex", flexDirection: "column",
        background: "var(--bg-surface)", border: "1px solid var(--glass-border)", borderRadius: 18,
        boxShadow: "0 24px 60px -12px rgba(0,0,0,0.6)", overflow: "hidden",
        animation: "modalIn 220ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        {/* Header */}
        <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: "flex",
              alignItems: "center", justifyContent: "center",
              background: "var(--grad)", boxShadow: "0 2px 12px rgba(124,58,237,0.4)" }}>
              <Ic d={I.zap} size={16} color="#fff" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontFamily: "var(--f-display)", fontSize: 15.5, fontWeight: 700,
                  color: "var(--tx-1)", whiteSpace: "nowrap" }}>
                  Auto-Apply
                </span>
                {form?.ats && (
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 9px", borderRadius: 20,
                    background: "rgba(59,130,246,0.13)", color: "#60a5fa", letterSpacing: ".04em" }}>
                    {ATS_NAMES[form.ats] || form.ats}
                  </span>
                )}
                {form?.dry_run && form?.method === "auto" && (
                  <span title="Dry-run ON: submitting validates the payload but sends nothing. Turn off in Settings."
                    style={{ fontSize: 10, fontWeight: 700, padding: "2px 9px", borderRadius: 20,
                      background: "rgba(245,158,11,0.15)", color: "#fbbf24", display: "inline-flex",
                      alignItems: "center", gap: 4, letterSpacing: ".04em" }}>
                    <Ic d={I.shield} size={10} color="#fbbf24" /> DRY RUN
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: "var(--tx-3)", marginTop: 2, whiteSpace: "nowrap",
                overflow: "hidden", textOverflow: "ellipsis" }}>
                {job.title} · {job.company}{form?.meta?.location ? ` · ${form.meta.location}` : ""}
              </div>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer",
              color: "var(--tx-3)", padding: 6 }}>
              <Ic d={I.x} size={16} />
            </button>
          </div>

          {/* Progress */}
          {!loading && form?.supported && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11,
                color: "var(--tx-3)", marginBottom: 5 }}>
                <span>{answered.length}/{fields.length} answered</span>
                <span style={{ color: missingRequired.length ? "#fbbf24" : "#10b981", fontWeight: 600 }}>
                  {missingRequired.length ? `${missingRequired.length} required left` : "all required answered ✓"}
                </span>
              </div>
              <div style={{ height: 4, borderRadius: 4, background: "rgba(255,255,255,0.07)", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct}%`, borderRadius: 4,
                  background: missingRequired.length ? "linear-gradient(90deg,#f59e0b,#8b5cf6)" : "var(--grad)",
                  transition: "width .3s ease" }} />
              </div>
            </div>
          )}
        </div>

        {/* Body */}
        <div style={{ padding: 16, overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          {loading && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
              color: "var(--tx-2)", fontSize: 13, padding: "40px 0" }}>
              <Spinner size={16} /> Loading the application form…
            </div>
          )}

          {!loading && form && !form.supported && (
            <div style={{ textAlign: "center", padding: "28px 20px" }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--tx-1)", marginBottom: 6 }}>
                Direct apply isn't available for this job
              </div>
              <div style={{ fontSize: 12.5, color: "var(--tx-3)", marginBottom: 16, lineHeight: 1.5 }}>
                {form.reason || "The job URL doesn't point to a supported application system."}
              </div>
              <a href={form.apply_url} target="_blank" rel="noreferrer"
                style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 600,
                  color: "#fff", textDecoration: "none", background: "var(--grad)",
                  padding: "9px 18px", borderRadius: 10 }}>
                <Ic d={I.link} size={13} color="#fff" /> Open the job page & apply there
              </a>
            </div>
          )}

          {!loading && form?.supported && (
            <>
              {form.method === "manual" && (
                <div style={{ fontSize: 12, color: "#fbbf24", background: "rgba(245,158,11,0.08)",
                  border: "1px solid rgba(245,158,11,0.22)", borderRadius: 10, padding: "9px 13px", lineHeight: 1.5 }}>
                  {ATS_NAMES[form.ats || ""] || "This ATS"} has no direct submit path — review the pre-filled
                  answers, use <b>Copy answers</b>, and finish on the ATS page.
                </div>
              )}

              {contact.length > 0 && (
                <Section icon={I.user} color="#3b82f6" title="Your Details"
                  sub="Pre-filled from your profile">
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {contact.map(renderField)}
                  </div>
                </Section>
              )}

              {questions.length > 0 && (
                <Section icon={I.clipboard} color="#10b981" title="Employer Questions"
                  sub="From your Application Answers + learned answers"
                  extra={unanswered.length > 0 ? (
                    <button onClick={draftWithAi} disabled={drafting}
                      title="Drafts the remaining answers from your resume + this JD. You review everything."
                      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, fontWeight: 700,
                        background: "rgba(124,58,237,0.12)", border: "1px solid rgba(124,58,237,0.4)",
                        borderRadius: 8, padding: "5px 11px", cursor: "pointer", color: "#a78bfa",
                        opacity: drafting ? 0.6 : 1, flexShrink: 0 }}>
                      {drafting ? <Spinner size={12} /> : <Ic d={I.sparkle} size={12} color="#a78bfa" />}
                      AI draft {unanswered.length}
                    </button>
                  ) : undefined}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {questions.map(renderField)}
                  </div>
                </Section>
              )}

              {optional.length > 0 && (
                <Section icon={I.heart} color="#8b5cf6" title="Voluntary Self-Identification"
                  sub="Optional survey — confidential, leave blank to skip">
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {optional.map(renderField)}
                  </div>
                </Section>
              )}

              {/* Attachments — status follows the job's own required flags */}
              {(() => {
                const fileFields = (form.fields || []).filter(f => f.type === "file");
                const coverField = fileFields.find(f => /cover/i.test(f.label));
                const hasCover = !!(job.cover_letter || "").trim();
                const row = (ok: boolean, warn: boolean, text: string) => (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
                    color: warn ? "#fbbf24" : "var(--tx-2)" }}>
                    <span style={{ width: 16, textAlign: "center" }}>{ok ? "✓" : warn ? "⚠" : "—"}</span>
                    <span style={{ color: ok ? "#10b981" : undefined, flex: 1 }}>{text}</span>
                  </div>
                );
                return (
                  <Section icon={I.doc} color="#d97706" title="Attachments"
                    sub="What gets uploaded with this application">
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {row(true, false, useTailored && job.tailored_resume
                        ? "Resume — tailored PDF for this JD"
                        : "Resume — base resume PDF")}
                      {coverField && row(hasCover, coverField.required && !hasCover,
                        hasCover
                          ? "Cover letter — generated PDF attached"
                          : coverField.required
                            ? "Cover letter REQUIRED by this job — generate one on the Cover Letter tab first"
                            : "Cover letter — none generated (optional here)")}
                    </div>
                    <label style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, marginTop: 10,
                      color: "var(--tx-2)", cursor: job.tailored_resume ? "pointer" : "default" }}>
                      <input type="checkbox" checked={useTailored} disabled={!job.tailored_resume}
                        onChange={e => setUseTailored(e.target.checked)} />
                      Use the tailored resume {job.tailored_resume ? "" : "(none yet)"}
                    </label>
                    <p style={{ fontSize: 11, color: "var(--tx-3)", margin: "8px 0 0", lineHeight: 1.5 }}>
                      New answers you type here are remembered and pre-filled next time any company asks the same question.
                    </p>
                  </Section>
                );
              })()}
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && form?.supported && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px",
            borderTop: "1px solid var(--line)", background: "rgba(0,0,0,0.12)" }}>
            <a href={form.apply_url} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
                color: "var(--tx-2)", textDecoration: "none", padding: "7px 12px",
                border: "1px solid var(--line)", borderRadius: 9 }}>
              <Ic d={I.link} size={12} /> ATS page
            </a>
            <button onClick={copyAll}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
                background: "none", border: "1px solid var(--line)", borderRadius: 9, padding: "7px 12px",
                cursor: "pointer", color: "var(--tx-2)" }}>
              <Ic d={I.copy} size={12} /> Copy answers
            </button>
            {form.method === "auto" && (
              <button onClick={submit} disabled={submitting}
                style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 8,
                  fontSize: 13, fontWeight: 700, border: "none", borderRadius: 10, padding: "9px 20px",
                  cursor: "pointer", color: "#fff", opacity: submitting ? 0.65 : 1,
                  background: form.dry_run ? "linear-gradient(120deg,#d97706,#f59e0b)" : "var(--grad)",
                  boxShadow: form.dry_run ? "0 2px 14px rgba(245,158,11,0.35)" : "0 2px 14px rgba(124,58,237,0.4)" }}>
                {submitting ? <Spinner size={13} color="#fff" /> : <Ic d={form.dry_run ? I.shield : I.send} size={13} color="#fff" />}
                {form.dry_run ? "Validate (dry run)" : "Submit application"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
