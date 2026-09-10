import React, { useEffect } from "react";
import ReactDOM from "react-dom";

/** Centered dialog used by the auth page's "How it works" / "About" links.
 *  Closes on Escape or a click on the backdrop. */
export function Modal({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; width?: number }) {
  useEffect(() => {
    if (!open) return;
    const kd = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", kd);
    return () => document.removeEventListener("keydown", kd);
  }, [open, onClose]);
  if (!open) return null;
  return ReactDOM.createPortal(
    <div className="au-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="au-modal" style={{ width: `min(${width}px, calc(var(--au-vw) * .94))` }}>
        <div className="au-modal-head">
          <div className="au-modal-title">{title}</div>
          <button type="button" aria-label="Close" onClick={onClose}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
