"use client";

import { useEffect, useRef } from "react";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { assignedCompartment, retrievedItem, wrongCompartment } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";
import DesktopTestControls from "./DesktopTestControls";

export default function StatusModal({ type }: { type: "cancel" | "wrongPlacement" | "wrongItem" }) {
  const kiosk = useKiosk();
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(modalRef.current?.querySelectorAll<HTMLElement>("button, summary, input, [tabindex]:not([tabindex='-1'])") ?? []).filter((item) => !item.hasAttribute("disabled"));
    (focusable()[0] ?? modalRef.current)?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); return; }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
      else if (!event.shiftKey && index === items.length - 1) { event.preventDefault(); items[0].focus(); }
    }
    document.addEventListener("keydown", trap, true);
    return () => { document.removeEventListener("keydown", trap, true); document.body.style.overflow = oldOverflow; (previousFocus?.closest("details")?.querySelector("summary") ?? previousFocus)?.focus(); };
  }, []);

  const cancel = type === "cancel";
  const wrongPlacement = type === "wrongPlacement";
  return <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/45 p-4"><div ref={modalRef} tabIndex={-1} role="alertdialog" aria-modal="true" aria-labelledby="kiosk-modal-title" aria-describedby="kiosk-modal-description" className="w-full max-w-[600px] rounded-xl bg-white p-5 text-center shadow-xl sm:p-8"><span className={`mx-auto flex size-16 items-center justify-center rounded-full ${cancel ? "bg-[#ffedcc] text-[#a26b13]" : "bg-[#f4e1e1] text-red-600"}`}><Icon name={cancel ? "warning" : "close"} size={36} /></span><p className={`mt-2 text-xs font-bold uppercase ${cancel ? "text-[#a26b13]" : "text-red-600"}`}>{cancel ? "Discard this session?" : "Unexpected weight change"}</p><h2 id="kiosk-modal-title" className="mt-5 text-2xl font-semibold">{cancel ? "Cancel and return home" : wrongPlacement ? "Wrong compartment detected" : "Wrong item detected"}</h2><p id="kiosk-modal-description" className="mt-1 text-sm text-[#444]">{cancel ? "Your selected images and entered details will be discarded from this browser session." : wrongPlacement ? `The item was placed in ${wrongCompartment} instead of ${assignedCompartment}.` : `An item was lifted from ${wrongCompartment}. Please return it before continuing.`}</p>{!cancel && <><dl className="mt-5 overflow-hidden rounded-lg border border-[#ccc] text-left text-sm"><div className="flex justify-between gap-3 border-b border-[#ccc] p-3"><dt>{wrongPlacement ? "Assigned compartment" : "Lifted from"}</dt><dd className="font-semibold">{wrongPlacement ? assignedCompartment : `${wrongCompartment} · Keychain`}</dd></div><div className="flex justify-between gap-3 p-3"><dt>{wrongPlacement ? "Detected compartment" : "Your item"}</dt><dd className="font-semibold">{wrongPlacement ? wrongCompartment : `${assignedCompartment} · ${retrievedItem}`}</dd></div></dl><div className="mt-5 flex items-start gap-2 rounded-lg border border-red-300 bg-[#ffe4e4] p-3 text-left text-red-700"><Icon name="warning" size={24} className="shrink-0" /><div><strong>{wrongPlacement ? `Remove the item from ${wrongCompartment}` : `Return the keychain to ${wrongCompartment}`}</strong><p className="text-xs">{wrongPlacement ? `Then place it in the highlighted compartment ${assignedCompartment}.` : "The sensor will confirm when it is safely back."}</p></div></div><p role="status" className="mt-5 text-sm text-[#555]">{wrongPlacement ? "Waiting for placement correction…" : "Waiting for item to be returned…"}</p><DesktopTestControls inModal /></>}{cancel && <div className="mt-7 flex flex-col gap-2 sm:flex-row"><Button type="button" variant="outline" onClick={kiosk.stay} className="flex-1">Keep working</Button><Button type="button" onClick={kiosk.reset} className="flex-1">Discard and return home</Button></div>}</div></div>;
}
