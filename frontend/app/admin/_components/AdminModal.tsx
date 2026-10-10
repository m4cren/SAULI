"use client";

import { useEffect, useRef, type ReactNode } from "react";
import AdminIcon from "./AdminIcon";

export default function AdminModal({ title, description, children, onClose, className = "" }: { title: string; description?: string; children: ReactNode; onClose: () => void; className?: string }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const elements = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'));
      if (!elements.length) return;
      const first = elements[0]; const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); openerRef.current?.focus(); };
  }, []);
  return <div className="admin-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="admin-modal-title" aria-describedby={description ? "admin-modal-description" : undefined} className={`admin-modal ${className}`}>
      <button ref={closeRef} type="button" className="admin-modal-close" onClick={onClose} aria-label="Close dialog"><AdminIcon name="close" size={19} /></button>
      <div className="admin-modal-heading"><h2 id="admin-modal-title">{title}</h2>{description && <p id="admin-modal-description">{description}</p>}</div>
      {children}
    </div>
  </div>;
}
