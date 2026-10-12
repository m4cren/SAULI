"use client";

import { useEffect, useRef } from "react";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { assignedCompartment, wrongCompartment } from "../_data/mockKioskData";
import { useKiosk } from "../_hooks/useKioskFlow";
import DesktopTestControls from "./DesktopTestControls";

export default function StatusModal({ type }: { type: "cancel" | "wrongPlacement" | "wrongItem" }) {
  const kiosk = useKiosk();
  const modalRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(modalRef.current?.querySelectorAll<HTMLElement>("button, summary") ?? []).filter((item) => !item.hasAttribute("disabled"));
    (focusable()[0] ?? modalRef.current)?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (!items.length) { event.preventDefault(); return; }
      if (event.shiftKey && index <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
      else if (!event.shiftKey && index === items.length - 1) { event.preventDefault(); items[0].focus(); }
    }
    document.addEventListener("keydown", trap, true);
    return () => { document.removeEventListener("keydown", trap, true); document.body.style.overflow = oldOverflow; previousFocus?.focus(); };
  }, []);

  const cancel = type === "cancel";
  const wrongPlacement = type === "wrongPlacement";
  const intended = kiosk.state.validatedRetrieval;
  return <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/45 p-4">
    <div ref={modalRef} tabIndex={-1} role="alertdialog" aria-modal="true" aria-labelledby="kiosk-modal-title" aria-describedby="kiosk-modal-description" className="w-full max-w-[600px] rounded-xl bg-white p-5 text-center shadow-xl sm:p-8">
      <span className={`mx-auto flex size-16 items-center justify-center rounded-full ${cancel ? "bg-[#ffedcc] text-[#a26b13]" : "bg-[#f4e1e1] text-red-600"}`}><Icon name={cancel ? "warning" : "close"} size={36} /></span>
      <h2 id="kiosk-modal-title" className="mt-5 text-2xl font-semibold">{cancel ? "Cancel and return home" : wrongPlacement ? "Wrong compartment detected" : "Wrong Item Retrieved"}</h2>
      <p id="kiosk-modal-description" className="mt-2 text-sm text-[#444]">{cancel ? "Your selected images and entered details will be discarded from this browser session." : wrongPlacement ? `The item was placed in ${wrongCompartment} instead of ${assignedCompartment}.` : "The removed item is not the authorized item. Return it to its original position before continuing."}</p>
      {type === "wrongItem" && <>
        <div className="mt-5 overflow-hidden rounded-lg border border-[#d5d5d5] text-left text-sm">
          <div className="flex justify-between gap-4 border-b border-[#d5d5d5] p-3"><span>Lifted item</span><strong>Unverified</strong></div>
          <div className="flex justify-between gap-4 p-3"><span>Your item</span><strong>{intended?.slot_code ?? "Assigned position"} · {intended?.item_summary ?? "Confirmed item"}</strong></div>
        </div>
        <div className="mt-4 rounded-lg border border-red-300 bg-[#ffe4e4] p-4 text-left text-sm text-red-700"><strong>Return the item to its original position.</strong><p className="mt-1">The door remains in the simulated open state. Your item remains in {intended?.slot_code ?? "its assigned position"}.</p></div>
        <p role="status" className="mt-4 flex items-center justify-center gap-2 text-xs text-[#52676a]"><span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-[#c9dede] border-t-[#0b474f]" />Waiting for item return…</p>
        <DesktopTestControls inModal />
      </>}
      {wrongPlacement && <><p className="mt-5 text-sm">Remove it from {wrongCompartment}, then place it in {assignedCompartment}.</p><DesktopTestControls inModal /></>}
      {cancel && <div className="mt-7 flex flex-col gap-2 sm:flex-row"><Button type="button" variant="outline" onClick={kiosk.stay} className="flex-1">Keep working</Button><Button type="button" onClick={kiosk.reset} className="flex-1">Discard and return home</Button></div>}
    </div>
  </div>;
}
