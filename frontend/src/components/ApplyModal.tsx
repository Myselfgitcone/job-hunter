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

  useEffect(() => {
    let alive = true;
    api.getApplyForm(job.id)
      .then(f => { if (alive) { setForm(f); setAnswers(f.answers || {}); } })
      .catch(e => { if (alive) { setForm({ supported: false, apply_url: job.url, reason: e.message }); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [job.id]);

  const missingRequired = (form?.fields || [])
    .filter(f => f.required && f.type !== "file" && !(answers[f.key] || "").trim());

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

  const copyAll = () => {
    const lines = (form?.fields || [])
      .filter(f => f.type !== "file")
      .map(f => `${f.label}: ${answers[f.key] || ""}`);
    navigator.clipboard.writeText(lines.join("\n"));
    onToast("Answers copied — paste into the ATS form", "success");
  };

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "7px 10px", fontSize: 13, borderRadius: 8,
    border: "1px solid var(--line)", background: "var(--bg-main)", color: "var(--tx-1)",
  };

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 2000, background: "rgba(0,0,0,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 560, maxWidth: "92vw", maxHeight: "86vh", display: "flex", flexDirection: "column",
        background: "var(--bg-surface)", border: "1px solid var(--line)", borderRadius: 16,
        boxShadow: "0 12px 30px -10px rgba(0,0,0,0.5)", overflow: "hidden",
        animation: "modalIn 200ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontSize: 14.5, fontWeight: 700, color: "var(--tx-1)" }}>
            Auto-Apply — {job.title}
          </span>
          {form?.ats && (
            <span style={{ fontSize: 10.5, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
              background: "rgba(59,130,246,0.12)", color: "#3b82f6" }}>
              {ATS_NAMES[form.ats] || form.ats}
            </span>
          )}
          {form?.dry_run && form?.method === "auto" && (
            <span title="Dry-run is ON: submit validates the payload but sends nothing. Turn off in Settings."
              style={{ fontSize: 10.5, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
                background: "rgba(245,158,11,0.14)", color: "#d97706", display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Ic d={I.shield} size={11} color="#d97706" /> DRY RUN
            </span>
          )}
          <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "var(--tx-3)" }}>
            <Ic d={I.x} size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 18, overflowY: "auto", flex: 1 }}>
          {loading && <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--tx-2)", fontSize: 13 }}><Spinner size={14} /> Loading application form…</div>}

          {!loading && form && !form.supported && (
            <div style={{ fontSize: 13, color: "var(--tx-2)", lineHeight: 1.6 }}>
              <p style={{ margin: 0, marginBottom: 10 }}>
                Direct apply isn't available for this job{form.reason ? <> — {form.reason}</> : null}.
              </p>
              <a href={form.apply_url} target="_blank" rel="noreferrer"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, color: "#3b82f6", textDecoration: "none" }}>
                <Ic d={I.link} size={13} /> Open the job page and apply there
              </a>
            </div>
          )}

          {!loading && form?.supported && (
            <>
              {form.method === "manual" && (
                <div style={{ fontSize: 12.5, color: "#d97706", background: "rgba(245,158,11,0.10)",
                  border: "1px solid rgba(245,158,11,0.25)", borderRadius: 10, padding: "8px 12px", marginBottom: 14, lineHeight: 1.5 }}>
                  {ATS_NAMES[form.ats || ""] || "This ATS"} has no third-party submit path — review your answers below,
                  copy them, and finish on the ATS page. Your resume PDF downloads from the Tailored Resume buttons.
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {(form.fields || []).map(f => f.type === "file" ? null : (
                  <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--tx-2)" }}>
                      {f.label}{f.required && <span style={{ color: "#f87171" }}> *</span>}
                    </span>
                    {f.type === "textarea" ? (
                      <textarea rows={3} style={{ ...inputStyle, resize: "vertical" }}
                        value={answers[f.key] || ""}
                        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))} />
                    ) : (f.type === "select" || f.type === "boolean" || f.type === "multiselect") && f.options?.length ? (
                      <select style={inputStyle} value={answers[f.key] || ""}
                        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))}>
                        <option value="">— select —</option>
                        {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    ) : (
                      <input style={inputStyle} value={answers[f.key] || ""}
                        onChange={e => setAnswers(a => ({ ...a, [f.key]: e.target.value }))} />
                    )}
                  </label>
                ))}
              </div>

              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16, fontSize: 12.5, color: "var(--tx-2)", cursor: "pointer" }}>
                <input type="checkbox" checked={useTailored} disabled={!job.tailored_resume}
                  onChange={e => setUseTailored(e.target.checked)} />
                Attach tailored resume {job.tailored_resume ? "(recommended)" : "— none yet, base resume will be used"}
              </label>
              <p style={{ fontSize: 11.5, color: "var(--tx-3)", margin: "10px 0 0", lineHeight: 1.5 }}>
                Answers you type here are remembered and pre-filled the next time any company asks the
                same question. Standard answers (visa, relocation, salary…) come from Profile → Application Answers.
              </p>
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && form?.supported && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 18px", borderTop: "1px solid var(--line)" }}>
            <a href={form.apply_url} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 600, color: "var(--tx-2)", textDecoration: "none" }}>
              <Ic d={I.link} size={13} /> Open ATS page
            </a>
            <button onClick={copyAll} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 600,
              background: "none", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 12px", cursor: "pointer", color: "var(--tx-2)" }}>
              <Ic d={I.copy} size={13} /> Copy answers
            </button>
            {form.method === "auto" && (
              <button onClick={submit} disabled={submitting}
                style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 700,
                  background: form.dry_run ? "rgba(245,158,11,0.14)" : "rgba(16,185,129,0.14)",
                  color: form.dry_run ? "#d97706" : "#10b981",
                  border: `1px solid ${form.dry_run ? "rgba(245,158,11,0.4)" : "rgba(16,185,129,0.4)"}`,
                  borderRadius: 8, padding: "7px 16px", cursor: "pointer", opacity: submitting ? 0.6 : 1 }}>
                {submitting ? <Spinner size={13} /> : <Ic d={I.send} size={13} color={form.dry_run ? "#d97706" : "#10b981"} />}
                {form.dry_run ? "Validate (dry run)" : "Submit application"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
