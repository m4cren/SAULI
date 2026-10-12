"use client";

import { useEffect, useRef } from "react";
import Icon from "@/app/components/Icon";

export default function WrongItemWarning({ slotCode }: { slotCode: string }) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => { dialog.current?.focus(); }, []);

  return <div className="fixed inset-y-0 left-1/2 z-50 flex w-full max-w-[428px] -translate-x-1/2 items-center justify-center bg-black/45 p-5 backdrop-blur-[3px]">
    <div ref={dialog} tabIndex={-1} role="alertdialog" aria-modal="true" aria-labelledby="wrong-item-title" aria-describedby="wrong-item-description" className="w-full rounded-xl bg-white p-5 text-center shadow-xl focus:outline-none">
      <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-[#f8e2e2] text-red-600"><Icon name="close" size={35} /></div>
      <p className="mt-3 text-[10px] font-bold uppercase tracking-[0.1em] text-red-600">Unexpected item removal</p>
      <h2 id="wrong-item-title" className="mt-2 text-2xl font-semibold">Wrong item detected</h2>
      <p id="wrong-item-description" className="mt-2 text-sm">An item other than your confirmed item was lifted. Please return it before continuing.</p>
      <div className="mt-5 rounded-lg border border-[#ddd] text-left text-sm">
        <div className="flex justify-between gap-3 border-b border-[#ddd] px-3 py-3"><span>Lifted item</span><strong>Unverified</strong></div>
        <div className="flex justify-between gap-3 px-3 py-3"><span>Your item</span><strong>{slotCode}</strong></div>
      </div>
      <div className="mt-4 rounded-lg border border-red-300 bg-[#ffe7e7] p-3 text-left text-sm text-red-700"><strong>Return the item to its original position.</strong><p className="mt-1 text-xs">The kiosk will resume this retrieval when the return is recorded.</p></div>
      <p role="status" className="mt-5 flex items-center justify-center gap-2 text-xs text-[#52676a]"><span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-[#c9dede] border-t-[#0b474f]" />Waiting for the item to be returned…</p>
    </div>
  </div>;
}
