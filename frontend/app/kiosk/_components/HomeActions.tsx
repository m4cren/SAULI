"use client";

import BrandFrame from "@/app/components/BrandFrame";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";
import DesktopTestControls from "./DesktopTestControls";

export default function HomeActions() {
  const { startFound, startRetrieve, availableCount } = useKiosk();
  return <main className="mx-auto flex min-h-[min(100dvh,720px)] max-w-[1160px] flex-col justify-center px-5 py-10 sm:px-12">
    <div className="mb-10"><BrandFrame /><p className="mt-2 text-base sm:text-lg">Secure Automated Unit for Lost Item</p></div>
    <h1 className="text-[clamp(30px,4vw,42px)] font-semibold leading-tight tracking-[0.02em] text-[#092a2f]">What would you like to do?</h1><p className="mb-9 text-lg sm:text-2xl">Choose one option to begin.</p>
    <div className="grid gap-4 md:grid-cols-2">
      <button type="button" onClick={startFound} className="flex min-h-40 items-center gap-5 rounded-2xl border-2 border-[#d5d5d5] bg-white p-6 text-left transition-colors hover:border-[#0b474f] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[#0b474f]"><span className="flex size-[84px] shrink-0 items-center justify-center rounded-[20px] bg-[#d1dddd] text-[#0b474f]"><Icon name="camera" size={46} /></span><span className="flex-1"><strong className="block text-xl text-[#092a2f] sm:text-2xl">Scan a found item</strong><span className="mt-1 block text-sm leading-snug sm:text-base">Capture two sides, identify its size, then store it in an available position.</span></span><span aria-hidden="true" className="text-2xl text-[#0b474f]">→</span></button>
      <button type="button" onClick={startRetrieve} className="flex min-h-40 items-center gap-5 rounded-2xl border-2 border-[#d5d5d5] bg-white p-6 text-left transition-colors hover:border-[#0b474f] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[#0b474f]"><span className="flex size-[84px] shrink-0 items-center justify-center rounded-[20px] bg-[#d1dddd] text-[#0b474f]"><Icon name="search" size={46} /></span><span className="flex-1"><strong className="block text-xl text-[#092a2f] sm:text-2xl">Retrieve my item</strong><span className="mt-1 block text-sm leading-snug sm:text-base">Upload the one-time QR image shown on your phone to view the correct position.</span></span><span aria-hidden="true" className="text-2xl text-[#0b474f]">→</span></button>
    </div>
    <div className="mt-5 grid gap-2 rounded-xl border-2 border-[#d5d5d5] px-4 py-3 text-xs sm:grid-cols-2"><p><strong>Accepted:</strong> safe personal items that fit a pocket-size or medium-size compartment.</p><p><strong>Not accepted:</strong> loose money, oversized, wet or perishable items, hazardous items, and prohibited items.</p></div>
    <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[#666]"><span>{availableCount} of 15 positions available in this prototype.</span><DesktopTestControls /></div>
  </main>;
}
