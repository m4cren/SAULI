"use client";

import BrandFrame from "@/app/components/BrandFrame";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function HomeActions() {
  const { startFound } = useKiosk();
  return <main className="mx-auto flex min-h-[min(100dvh,720px)] max-w-[1160px] flex-col justify-center px-5 py-10 sm:px-12">
    <div className="mb-10"><BrandFrame /><p className="mt-2 text-base sm:text-lg">Secure Automated Unit for Lost Item</p></div>
    <h1 className="text-[clamp(30px,4vw,42px)] font-semibold leading-tight tracking-[0.02em] text-[#092a2f]">What would you like to do?</h1>
    <p className="mb-9 text-lg sm:text-2xl">Choose one option to begin.</p>
    <div className="grid gap-4 md:grid-cols-2">
      <button type="button" onClick={startFound} className="flex min-h-40 items-center gap-5 rounded-2xl border-2 border-[#d5d5d5] bg-white p-6 text-left transition-colors hover:border-[#0b474f] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[#0b474f]"><span className="flex size-[84px] shrink-0 items-center justify-center rounded-[20px] bg-[#d1dddd] text-[#0b474f]"><Icon name="camera" size={46} /></span><span className="flex-1"><strong className="block text-xl text-[#092a2f] sm:text-2xl">Scan a found item</strong><span className="mt-1 block text-sm leading-snug sm:text-base">Capture two sides, add where it was found, and save its details for search matching.</span></span><span aria-hidden="true" className="text-2xl text-[#0b474f]">→</span></button>
      <div aria-disabled="true" className="flex min-h-40 items-center gap-5 rounded-2xl border-2 border-[#d5d5d5] bg-[#f5f5f5] p-6 text-left text-[#666]"><span className="flex size-[84px] shrink-0 items-center justify-center rounded-[20px] bg-[#e5e5e5]"><Icon name="search" size={46} /></span><span className="flex-1"><strong className="block text-xl sm:text-2xl">Station retrieval</strong><span className="mt-1 block text-sm leading-snug sm:text-base">Container and QR integration will be available in a later phase.</span></span></div>
    </div>
    <p className="mt-5 text-xs text-[#666]">Only safe personal items can be submitted. Do not scan loose money, wet or perishable items, hazardous items, or prohibited items.</p>
  </main>;
}
