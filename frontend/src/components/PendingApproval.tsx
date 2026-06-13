import { useEffect, useState } from "react";
import { api } from "../api";
import { ROLE_GROUPS } from "./JobPreferencesModal";

export default function PendingApproval({ email, isRevoked, onApproved, onLogout }: {
  email: string;
  isRevoked?: boolean;
  onApproved: () => void;
  onLogout: () => void;
}) {
  const [step, setStep] = useState<"loading" | "pick-role" | "waiting" | "revoked">("loading");
  const [selected, setSelected] = useState<string>(""); // family group name
  const [saving, setSaving] = useState(false);

  // Check if roles already set (email signup) or empty (OAuth)
  useEffect(() => {
    if (isRevoked) { setStep("revoked"); return; }
    api.getSettings().then((s: any) => {
      const roles: string[] = s.job_roles || [];
      setStep(roles.length > 0 ? "waiting" : "pick-role");
    }).catch(() => setStep("pick-role"));
  }, [isRevoked]);

  // Poll every 30s for approval (waiting or revoked — admin can re-approve either)
  useEffect(() => {
    if (step !== "waiting" && step !== "revoked") return;
    const t = setInterval(async () => {
      try {
        const me = await api.auth.me() as any;
        if ((me.status || "approved") === "approved") onApproved();
      } catch {}
    }, 30000);
    return () => clearInterval(t);
  }, [step, onApproved]);

  const submitRole = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const group = ROLE_GROUPS.find(g => g.group === selected);
      const roles = group ? group.items : [];
      await (api as any).saveSettings({ job_roles: roles });
      setStep("waiting");
    } catch {}
    finally { setSaving(false); }
  };

  if (step === "loading") {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
        <div style={{ fontSize: 13, color: "var(--tx-3)" }}>Loading…</div>
      </div>
    );
  }

  if (step === "pick-role") {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
        <div style={{ maxWidth: 460, width: "100%", padding: "0 24px" }}>

          {/* Icon */}
          <div style={{ width: 64, height: 64, margin: "0 auto 20px", borderRadius: 18, display: "grid", placeItems: "center",
            background: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.25)" }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
            </svg>
          </div>

          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--tx)", marginBottom: 8, textAlign: "center" }}>
            What role are you looking for?
          </h1>
          <p style={{ fontSize: 13.5, color: "var(--tx-2)", lineHeight: 1.6, marginBottom: 20, textAlign: "center" }}>
            Admin uses this to assign your job feed on approval.
          </p>

          {/* Single-select role cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
            {ROLE_GROUPS.map(g => {
              const on = selected === g.group;
              return (
                <button key={g.group} type="button" onClick={() => setSelected(g.group)}
                  style={{
                    display: "flex", alignItems: "center", gap: 14,
                    padding: "14px 18px", borderRadius: 12, cursor: "pointer",
                    border: on ? "2px solid var(--violet)" : "1.5px solid var(--line)",
                    background: on ? "rgba(124,58,237,0.07)" : "var(--bg-elevated)",
                    textAlign: "left", fontFamily: "inherit", transition: "all 0.15s",
                  }}>
                  {/* Radio dot */}
                  <span style={{
                    width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
                    border: on ? "5px solid var(--violet)" : "2px solid var(--line-hi)",
                    background: on ? "var(--violet)" : "transparent",
                    transition: "all 0.15s",
                  }} />
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: on ? "var(--violet)" : "var(--tx)" }}>{g.group}</div>
                    <div style={{ fontSize: 11.5, color: "var(--tx-3)", marginTop: 2 }}>
                      {g.items.slice(0, 3).join(", ")}{g.items.length > 3 ? ` +${g.items.length - 3} more` : ""}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Note */}
          <p style={{ fontSize: 12, color: "var(--tx-3)", lineHeight: 1.6, marginBottom: 20, textAlign: "center" }}>
            Select your primary role. Need access to more roles? Request from admin after approval.
          </p>

          <button onClick={submitRole} disabled={!selected || saving}
            style={{
              width: "100%", height: 48, borderRadius: 12, border: "none",
              background: selected ? "linear-gradient(120deg,#7c3aed,#06b6d4)" : "var(--line)",
              color: selected ? "#fff" : "var(--tx-3)",
              fontSize: 15, fontWeight: 700, cursor: selected ? "pointer" : "not-allowed",
              fontFamily: "inherit", transition: "all 0.15s",
              opacity: saving ? 0.7 : 1,
            }}>
            {saving ? "Saving…" : "Submit Request →"}
          </button>

          <div style={{ textAlign: "center", marginTop: 14 }}>
            <button onClick={onLogout}
              style={{ background: "none", border: "none", color: "var(--tx-3)", fontSize: 12.5, cursor: "pointer", fontFamily: "inherit" }}>
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (step === "revoked") {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
        <div style={{ textAlign: "center", maxWidth: 420, padding: 32 }}>
          <div style={{ width: 72, height: 72, margin: "0 auto 20px", borderRadius: 20, display: "grid", placeItems: "center",
            background: "rgba(220,38,38,0.1)", border: "1px solid rgba(220,38,38,0.3)" }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#dc2626", marginBottom: 10 }}>Access Revoked</h1>
          <p style={{ fontSize: 14, color: "var(--tx-2)", lineHeight: 1.6, marginBottom: 6 }}>
            Your account <b>{email}</b> has been locked by the admin.
          </p>
          <p style={{ fontSize: 12.5, color: "var(--tx-3)", marginBottom: 24 }}>
            Contact the admin to get your access restored. This page checks automatically — you'll be let in once re-approved.
          </p>
          <button onClick={onLogout}
            style={{ height: 38, padding: "0 22px", borderRadius: 10, border: "1px solid rgba(220,38,38,0.4)", background: "rgba(220,38,38,0.06)",
              color: "#dc2626", fontSize: 13.5, fontWeight: 600, cursor: "pointer" }}>
            Sign out
          </button>
        </div>
      </div>
    );
  }

  // step === "waiting"
  return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
      <div style={{ textAlign: "center", maxWidth: 420, padding: 32 }}>
        <div style={{ width: 72, height: 72, margin: "0 auto 20px", borderRadius: 20, display: "grid", placeItems: "center",
          background: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.25)" }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--violet)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
          </svg>
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--tx)", marginBottom: 10 }}>Waiting for Approval</h1>
        <p style={{ fontSize: 14, color: "var(--tx-2)", lineHeight: 1.6, marginBottom: 6 }}>
          Your account <b>{email}</b> has been created and is waiting for the admin to approve it and assign your job roles.
        </p>
        <p style={{ fontSize: 12.5, color: "var(--tx-3)", marginBottom: 24 }}>
          This page checks automatically — you'll be let in the moment you're approved.
        </p>
        <button onClick={onLogout}
          style={{ height: 38, padding: "0 22px", borderRadius: 10, border: "1px solid var(--line)", background: "transparent",
            color: "var(--tx-2)", fontSize: 13.5, fontWeight: 600, cursor: "pointer" }}>
          Sign out
        </button>
      </div>
    </div>
  );
}
