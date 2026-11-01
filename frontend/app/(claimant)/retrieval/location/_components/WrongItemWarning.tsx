"use client";

import { useEffect, useRef } from "react";
import Icon from "@/app/components/Icon";

export default function WrongItemWarning({ slotCode, itemSummary }: { slotCode: string; itemSummary: string }) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.focus();
    const keepFocusInWarning = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      event.preventDefault();
      dialog.current?.focus();
    };
    document.addEventListener("keydown", keepFocusInWarning);
    return () => {
      document.removeEventListener("keydown", keepFocusInWarning);
      previousFocus?.focus();
    };
  }, []);

  return <div className="fixed inset-y-0 left-1/2 z-50 flex w-full max-w-[428px] -translate-x-1/2 items-center justify-center bg-[#071a22]/60 p-5 backdrop-blur-[3px]">
    <div ref={dialog} tabIndex={-1} role="alertdialog" aria-modal="true" aria-labelledby="wrong-item-title" aria-describedby="wrong-item-description" className="w-full rounded-[24px] bg-white p-5 text-center shadow-[0_22px_55px_rgba(0,0,0,0.22)] focus:outline-none">
      <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-[#fce7e7] text-red-600"><Icon name="close" size={36} /></div>
      <p className="mt-4 text-xs font-bold uppercase tracking-[0.08em] text-red-600">Unexpected weight change</p>
      <h2 id="wrong-item-title" className="mt-2 text-2xl font-bold text-[#102d35]">Wrong item detected</h2>
      <p id="wrong-item-description" className="mt-2 text-sm text-[#536775]">An item other than yours was lifted. Please return it before continuing.</p>
      <div className="mt-5 overflow-hidden rounded-xl border border-[#d8e2e5] text-left text-sm">
        <div className="flex justify-between gap-3 border-b border-[#d8e2e5] px-3 py-3"><span className="text-[#627280]">Lifted item</span><strong className="text-right">Unverified</strong></div>
        <div className="flex justify-between gap-3 px-3 py-3"><span className="shrink-0 text-[#627280]">Your item</span><strong className="min-w-0 break-words text-right">{slotCode} · {itemSummary}</strong></div>
      </div>
      <div className="mt-4 rounded-xl border border-red-300 bg-[#ffe7e7] p-4 text-left text-sm text-red-700"><strong>Return the item to its original position.</strong><p className="mt-1 text-xs">The kiosk will resume this retrieval when the return is recorded.</p></div>
      <p role="status" className="mt-5 flex items-center justify-center gap-2 text-xs text-[#52676a]"><span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-[#c9dede] border-t-[#0b474f]" />Waiting for the item to be returned…</p>
    </div>
  </div>;
}
