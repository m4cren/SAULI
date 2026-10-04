"use client";

import { useEffect, useRef } from "react";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";

export default function WrongItemModal({ onReturned }: { onReturned: () => void }) {
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const priorFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const priorOverflow = document.body.style.overflow;
    const background = [document.querySelector("header"), document.querySelector('nav[aria-label="Main navigation"]')]
      .filter((element): element is HTMLElement => element instanceof HTMLElement)
      .map((element) => ({ element, inert: element.inert, ariaHidden: element.getAttribute("aria-hidden") }));
    background.forEach(({ element }) => { element.inert = true; element.setAttribute("aria-hidden", "true"); });
    document.body.style.overflow = "hidden";
    buttonRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape" || event.key === "Tab") {
        event.preventDefault();
        event.stopPropagation();
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKey, true);
    return () => {
      document.removeEventListener("keydown", handleKey, true);
      document.body.style.overflow = priorOverflow;
      background.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
      priorFocus?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4">
      <div role="dialog" aria-modal="true" aria-labelledby="wrong-item-title" aria-describedby="wrong-item-description" className="w-full max-w-[348px] rounded-[13px] bg-white px-[14px] py-[20px] text-center shadow-xl">
        <div className="mx-auto flex size-[65px] items-center justify-center rounded-full bg-[#f4e2e2] text-red-600"><Icon name="close" size={31} strokeWidth={2.7} /></div>
        <p className="mt-2 text-[12px] font-bold text-red-600">UNEXPECTED WEIGHT CHANGE</p>
        <h2 id="wrong-item-title" className="mt-7 text-[22px] font-bold">Wrong item detected</h2>
        <p id="wrong-item-description" className="mx-auto mt-1 max-w-[280px] text-[15px] leading-snug tracking-[0.06em] text-[#555]">An item was lifted from P-06. Please return it before continuing.</p>
        <dl className="mt-5 overflow-hidden rounded-[10px] border border-[var(--sauli-border)] text-left text-[13px]"><div className="flex justify-between gap-2 border-b border-[var(--sauli-border)] p-3"><dt>Lifted from</dt><dd className="text-right font-semibold">P-06 · Keychain</dd></div><div className="flex justify-between gap-2 p-3"><dt>Your item</dt><dd className="text-right font-semibold">P-05 · Black leather wallet</dd></div></dl>
        <div className="mt-5 flex gap-2 rounded-[9px] border border-red-300 bg-[#ffe3e3] p-3 text-left text-red-700"><Icon name="warning" size={23} className="shrink-0" /><div><p className="text-[16px] font-bold">Return the item to P-06</p><p className="text-[11px]">The sensor will confirm when it is safely back.</p></div></div>
        <p aria-live="assertive" className="mt-5 text-[12px] text-[#555]">Waiting for item to be returned…</p>
        <Button ref={buttonRef} type="button" onClick={onReturned} className="mt-5 w-full text-sm">Simulate item returned</Button>
      </div>
    </div>
  );
}
