import { useEffect } from "react";
import { api } from "../api";

// Full-screen gate for accounts awaiting admin approval.
// Polls /api/auth/me every 30s and lets the user through automatically
// the moment the admin approves them.
export default function PendingApproval({ email, onApproved, onLogout }: {
  email: string;
  onApproved: () => void;
  onLogout: () => void;
}) {
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const me = await api.auth.me() as any;
        if ((me.status || "approved") === "approved") onApproved();
      } catch { /* token problems handled globally */ }
    }, 30000);
    return () => clearInterval(t);
  }, [onApproved]);

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
